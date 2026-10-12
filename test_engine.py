import json
from pathlib import Path
import shutil
import tempfile
import os
from types import SimpleNamespace
from runtime_support import import_torch
torch=import_torch()
from safetensors.torch import save_model,load_file,save_file
from transformers import Qwen3Config, Qwen3ForCausalLM
from compressione import compress
from engine import CompressedEngine

def main():
    torch.set_num_threads(2)
    torch.manual_seed(123)
    tokenizer_dir=Path(os.environ.get('COMP_TEST_TOKENIZER',str(Path(__file__).parent/'models/qwen3-0.6b')))
    if not tokenizer_dir.exists():
        tokenizer_dir=next((Path.home()/'Desktop/matrix_ia/cache/hub/models--Qwen--Qwen3-0.6B/snapshots').glob('*'))
    with tempfile.TemporaryDirectory() as temp:
        root=Path(temp)
        config=Qwen3Config(vocab_size=64,hidden_size=32,intermediate_size=64,num_hidden_layers=2,num_attention_heads=2,num_key_value_heads=1,head_dim=16,tie_word_embeddings=True)
        config.save_pretrained(root)
        for name in ('tokenizer.json','tokenizer_config.json','vocab.json','merges.txt'):
            shutil.copyfile(tokenizer_dir/name,root/name)
        baseline=Qwen3ForCausalLM(config).to(dtype=torch.bfloat16).eval()
        from transformers.models.qwen3.modeling_qwen3 import Qwen3RotaryEmbedding
        baseline.model.rotary_emb=Qwen3RotaryEmbedding(config,device='cpu')
        baseline.config._attn_implementation='eager'
        source=root/'model.safetensors'; archive=root/'model.cmp'
        save_model(baseline,str(source))
        compress(source,archive,4096)
        tensors=load_file(str(source))
        names=list(tensors); mid=len(names)//2
        mapping={}; parts={}
        for i,subset in enumerate((names[:mid],names[mid:])):
            part=root/f'part{i}.safetensors'; packed=root/f'part{i}.cmp'
            save_file({name:tensors[name] for name in subset},str(part)); compress(part,packed,4096)
            parts[part.name]=packed.name
            mapping.update({name:part.name for name in subset})
        manifest=root/'model.cmpmodel.json'
        manifest.write_text(json.dumps({'format':'cmp-sharded-v1','shards':parts,'weight_map':mapping}))
        for mode,chosen in (('direct',archive),('ram',archive),('direct',manifest),('ram',manifest)):
            engine=CompressedEngine(chosen,str(root),mode)
            # Safetensors save_model may choose lm_head as the canonical tied weight.
            with torch.inference_mode():
                ids=torch.tensor([[1,2,3]])
                ref=baseline(input_ids=ids,use_cache=True,logits_to_keep=1)
                actual=engine.model(input_ids=ids,use_cache=True,logits_to_keep=1)
                torch.testing.assert_close(actual.logits,ref.logits,rtol=0,atol=0)
                ref2=baseline(input_ids=torch.tensor([[4]]),past_key_values=ref.past_key_values,use_cache=True,logits_to_keep=1)
                actual2=engine.model(input_ids=torch.tensor([[4]]),past_key_values=actual.past_key_values,use_cache=True,logits_to_keep=1)
                torch.testing.assert_close(actual2.logits,ref2.logits,rtol=0,atol=0)
            if mode=='direct': assert all(p.device.type=='meta' for p in engine.model.parameters())
            else:
                assert all(p.device.type=='cpu' for p in engine.model.parameters())
                assert engine.model.lm_head.weight is engine.model.model.embed_tokens.weight
            class TestTokenizer:
                length=600
                def apply_chat_template(self,*args,**kwargs): return 'test'
                def __call__(self,*args,**kwargs):
                    ids=torch.ones((1,self.length),dtype=torch.long)
                    return SimpleNamespace(input_ids=ids,attention_mask=torch.ones_like(ids))
                def decode(self,tokens,**kwargs): return ','.join(str(t) for t in tokens)
            engine.tokenizer=TestTokenizer()
            result=engine.generate([{'role':'user','content':'test'}],max_tokens=1,context_window=1024)
            assert result['prompt_tokens']==600 and result['context_used_tokens']<=1024
            try: engine.generate([{'role':'user','content':'test'}],max_tokens=1,context_window=512)
            except ValueError: pass
            else: raise AssertionError('Un prompt fuori contesto deve essere rifiutato.')
            engine.tokenizer.length=127
            result=engine.generate([{'role':'user','content':'test'}],max_tokens=4,context_window=128)
            assert result['tokens']<=1 and result['context_limited']
            engine.close()
            print(f'{mode} {chosen.name}: logits identici, prompt da 600 token accettato, limite di contesto rispettato.',flush=True)

if __name__=='__main__': main()
