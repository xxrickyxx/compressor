"""Inferenza Qwen3 con pesi letti direttamente dai blocchi CMP."""
import json
import math
import struct
import threading
import time
from pathlib import Path
from compressione import Archive
from runtime_support import import_torch
from context_limits import DEFAULT_CONTEXT,validate_context,generation_budget

class CompressedWeights:
    def __init__(self, path):
        self.archive = Archive(path)
        size = struct.unpack('<Q', self.archive.read_range(0, 8))[0]
        if size > 16*1024*1024 or size + 8 > self.archive.meta['size']:
            raise ValueError('Serve un archivio CMP di un file safetensors.')
        self.header = json.loads(self.archive.read_range(8, size))
        self.start = 8 + size
        self.bytes_read = 0

    def tensor(self, name):
        return self.tensor_rows(name)

    def tensor_rows(self, name, start=0, count=None):
        torch=import_torch()
        item = self.header[name]
        types = {'BF16':torch.bfloat16,'F16':torch.float16,'F32':torch.float32}
        dtype = types.get(item['dtype'])
        if dtype is None: raise ValueError(f"Precisione non supportata: {item['dtype']}")
        begin, end = item['data_offsets']
        elements = math.prod(item['shape'])
        item_size=torch.empty((),dtype=dtype).element_size()
        if end-begin != elements*item_size:
            raise ValueError('Forma del tensore non valida.')
        shape=list(item['shape'])
        if count is not None:
            if len(shape)!=2 or not 0<=start<shape[0] or not 0<count<=shape[0]-start: raise ValueError('Intervallo righe non valido.')
            stride=shape[1]*item_size
            begin+=start*stride; end=begin+count*stride; shape[0]=count
        raw = self.archive.read_range(self.start+begin,end-begin)
        # Release mapped pages after each tensor/chunk, keeping only the current
        # decoded computation buffer resident in this process.
        self.archive.close()
        self.bytes_read += len(raw)
        return torch.frombuffer(raw,dtype=dtype).reshape(shape)

    def close(self):
        self.archive.close()

class ShardedCompressedWeights:
    """Indice di più archivi safetensors, con accesso diretto al tensore."""
    def __init__(self,path):
        path=Path(path).resolve()
        if path.stat().st_size>16*1024*1024: raise ValueError('Indice modello troppo grande.')
        manifest=json.loads(path.read_text(encoding='utf8'))
        if manifest.get('format')!='cmp-sharded-v1': raise ValueError('Indice modello non riconosciuto.')
        self.readers={}
        self.header={}
        self.weight_map=manifest['weight_map']
        try:
            for source,filename in manifest['shards'].items():
                archive=(path.parent/filename).resolve()
                if not archive.is_relative_to(path.parent): raise ValueError('L’archivio deve restare nella cartella dell’indice.')
                self.readers[source]=CompressedWeights(archive)
            actual={}
            for source,reader in self.readers.items():
                for name,item in reader.header.items():
                    if name=='__metadata__': continue
                    if name in actual: raise ValueError('Tensore duplicato fra gli archivi.')
                    actual[name]=source
                    self.header[name]=item
            if actual!=self.weight_map: raise ValueError('L’indice dei tensori non corrisponde agli archivi.')
        except Exception:
            self.close(); raise

    @property
    def bytes_read(self): return sum(reader.bytes_read for reader in self.readers.values())

    def tensor(self,name): return self.tensor_rows(name)

    def tensor_rows(self,name,start=0,count=None):
        return self.readers[self.weight_map[name]].tensor_rows(name,start,count)

    def close(self):
        for reader in self.readers.values(): reader.close()

def open_compressed_weights(path):
    return ShardedCompressedWeights(path) if Path(path).suffix=='.json' else CompressedWeights(path)

class CompressedEngine:
    def __init__(self, archive, config_dir, mode='direct', status=None, stop=None):
        torch=import_torch()
        from transformers import AutoConfig, AutoModelForCausalLM, AutoTokenizer
        self.stop = stop or threading.Event()
        self.status = status or (lambda text: None)
        self.mode = mode
        self.decoded_peak_bytes=0
        self.weights = open_compressed_weights(archive)
        self.config_dir = Path(config_dir)
        config = AutoConfig.from_pretrained(config_dir,local_files_only=True,trust_remote_code=False)
        if config.model_type != 'qwen3':
            raise ValueError('Il motore diretto di questa versione supporta Qwen3 safetensors.')
        torch.set_num_threads(max(1,min(4,torch.get_num_threads())))
        with torch.device('meta'):
            self.model = AutoModelForCausalLM.from_config(config,torch_dtype=torch.bfloat16,attn_implementation='eager')
        self.model.eval()
        # RoPE contiene buffer derivati, non pesi salvati nel checkpoint.
        from transformers.models.qwen3.modeling_qwen3 import Qwen3RotaryEmbedding
        self.model.model.rotary_emb = Qwen3RotaryEmbedding(config,device='cpu')
        self.tokenizer = AutoTokenizer.from_pretrained(config_dir,local_files_only=True,trust_remote_code=False)
        groups = [('model.embed_tokens',self.model.model.embed_tokens)]
        groups += [(f'model.layers.{i}',layer) for i,layer in enumerate(self.model.model.layers)]
        groups += [('model.norm',self.model.model.norm),('lm_head',self.model.lm_head)]
        self.groups = groups
        self.loaded = set()
        self.handles = []
        if mode=='direct':
            embedding_name='model.embed_tokens.weight' if 'model.embed_tokens.weight' in self.weights.header else 'lm_head.weight'
            output_name=embedding_name if config.tie_word_embeddings else ('lm_head.weight' if 'lm_head.weight' in self.weights.header else embedding_name)
            engine=self
            class RowEmbedding(torch.nn.Module):
                def forward(self,ids):
                    engine.status('Lettura delle sole righe di embedding necessarie…')
                    flat=ids.reshape(-1); unique,inverse=torch.unique(flat,sorted=True,return_inverse=True)
                    values=[]
                    for token in unique.tolist():
                        if engine.stop.is_set(): raise InterruptedError('Generazione annullata.')
                        values.append(engine.weights.tensor_rows(embedding_name,token,1))
                    engine.decoded_peak_bytes=max(engine.decoded_peak_bytes,2*sum(v.numel()*v.element_size() for v in values))
                    table=torch.cat(values,dim=0)
                    return table[inverse].reshape(*ids.shape,config.hidden_size)
            class ChunkedHead(torch.nn.Module):
                def forward(self,hidden):
                    engine.status('Calcolo dell’uscita a blocchi…')
                    rows=engine.weights.header[output_name]['shape'][0]
                    logits=torch.empty((*hidden.shape[:-1],rows),dtype=hidden.dtype,device=hidden.device)
                    for start in range(0,rows,2048):
                        if engine.stop.is_set(): raise InterruptedError('Generazione annullata.')
                        count=min(2048,rows-start)
                        weight=engine.weights.tensor_rows(output_name,start,count)
                        engine.decoded_peak_bytes=max(engine.decoded_peak_bytes,weight.numel()*weight.element_size())
                        logits[...,start:start+count]=torch.nn.functional.linear(hidden,weight)
                        del weight
                    return logits
            self.model.model.embed_tokens=RowEmbedding()
            self.model.lm_head=ChunkedHead()
            groups=[group for group in groups if group[0] not in ('model.embed_tokens','lm_head')]
        for prefix,module in groups:
            self.handles.append(module.register_forward_pre_hook(self.loader(prefix)))
            if mode == 'direct':
                self.handles.append(module.register_forward_hook(self.release(prefix)))

    def loader(self, prefix):
        def hook(module,args):
            if self.stop.is_set(): raise InterruptedError('Generazione annullata.')
            if prefix in self.loaded: return
            if prefix=='lm_head' and self.model.config.tie_word_embeddings:
                module.weight=self.model.model.embed_tokens.weight
                self.loaded.add(prefix)
                return
            self.status(f'Lettura dall’archivio: {prefix}')
            state = {}
            for name,param in module.named_parameters():
                full = prefix+'.'+name
                if full == 'lm_head.weight' and full not in self.weights.header and self.model.config.tie_word_embeddings:
                    full = 'model.embed_tokens.weight'
                elif full == 'model.embed_tokens.weight' and full not in self.weights.header and self.model.config.tie_word_embeddings:
                    full = 'lm_head.weight'
                state[name] = self.weights.tensor(full)
                if self.stop.is_set(): raise InterruptedError('Generazione annullata.')
            module.load_state_dict(state,strict=True,assign=True)
            self.loaded.add(prefix)
            self.decoded_peak_bytes=max(self.decoded_peak_bytes,sum(p.numel()*p.element_size() for p in self.model.parameters() if p.device.type!='meta'))
        return hook

    def release(self,prefix):
        def hook(module,args,output):
            module.to('meta')
            self.loaded.discard(prefix)
        return hook

    def generate(self,messages,max_tokens=64,on_text=None,context_window=DEFAULT_CONTEXT):
        torch=import_torch()
        import psutil
        process=psutil.Process()
        rss_start=process.memory_info().rss
        peak=[rss_start]
        monitor_done=threading.Event()
        def monitor():
            while not monitor_done.wait(.1): peak[0]=max(peak[0],process.memory_info().rss)
        text = self.tokenizer.apply_chat_template(messages,tokenize=False,add_generation_prompt=True,enable_thinking=False)
        inputs = self.tokenizer(text,return_tensors='pt')
        context_window=validate_context(context_window,self.model.config.max_position_embeddings)
        requested_max_tokens=max_tokens
        max_tokens=generation_budget(inputs.input_ids.shape[1],max_tokens,context_window,self.model.config.max_position_embeddings)
        ids = inputs.input_ids
        mask = inputs.attention_mask
        past = None
        generated = []
        prompt_tokens=ids.shape[1]
        finish_reason='length'
        started = time.perf_counter()
        eos = self.model.generation_config.eos_token_id
        eos = set(eos if isinstance(eos,list) else [eos])
        threading.Thread(target=monitor,daemon=True).start()
        try:
            with torch.inference_mode():
                for _ in range(max_tokens):
                    if self.stop.is_set(): raise InterruptedError('Generazione annullata.')
                    output = self.model(input_ids=ids,attention_mask=mask,past_key_values=past,use_cache=True,logits_to_keep=1)
                    past = output.past_key_values
                    token = int(output.logits[0,-1].argmax())
                    if token in eos:
                        finish_reason='stop'
                        break
                    generated.append(token)
                    answer = self.tokenizer.decode(generated,skip_special_tokens=True)
                    if on_text: on_text(answer)
                    ids = torch.tensor([[token]],dtype=torch.long)
                    mask = torch.cat([mask,torch.ones((1,1),dtype=mask.dtype)],dim=1)
                    del output
        finally:
            peak[0]=max(peak[0],process.memory_info().rss)
            monitor_done.set()
        elapsed=time.perf_counter()-started
        return {'text':self.tokenizer.decode(generated,skip_special_tokens=True), 'tokens':len(generated),
                'seconds':elapsed,'tokens_s':len(generated)/max(elapsed,0.001),
                'weight_bytes_read':self.weights.bytes_read,'mode':self.mode,
                'prompt_tokens':prompt_tokens,'finish_reason':finish_reason,
                'context_window':context_window,'context_used_tokens':prompt_tokens+len(generated),
                'context_limited':max_tokens<requested_max_tokens,
                'rss_start_bytes':rss_start,'rss_peak_bytes':peak[0],
                'decoded_weight_peak_bytes':self.decoded_peak_bytes}

    def close(self):
        for handle in self.handles: handle.remove()
        self.model.to('meta')
        self.loaded.clear()
        self.weights.close()
