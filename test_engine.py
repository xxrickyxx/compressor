import json
from pathlib import Path
import shutil
import tempfile
from runtime_support import import_torch
torch=import_torch()
from safetensors.torch import save_model
from transformers import Qwen3Config, Qwen3ForCausalLM
from compressione import compress
from engine import CompressedEngine

def main():
    torch.set_num_threads(2)
    torch.manual_seed(123)
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
        for mode in ('direct','ram'):
            engine=CompressedEngine(archive,str(root),mode)
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
            else: assert all(p.device.type=='cpu' for p in engine.model.parameters())
            engine.close()
            print(f'{mode}: logits prefill e token successivo identici al modello originale.',flush=True)

if __name__=='__main__': main()
