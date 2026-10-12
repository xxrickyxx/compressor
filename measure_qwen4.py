"""Optional real 4B direct test; RAM test uses the same six short tasks as 1.7B."""
import argparse
import gc
import json
from pathlib import Path
import psutil
from engine import CompressedEngine

def main():
    args=argparse.ArgumentParser(); args.add_argument('--mode',choices=['direct','ram'],default='direct'); options=args.parse_args()
    root=Path(__file__).parent
    row=next(r for r in json.loads((root/'models.json').read_text(encoding='utf8')) if r.get('id')=='qwen3-4b-cmp')
    if options.mode=='ram' and psutil.virtual_memory().available<row['original_bytes']+700*1024*1024:
        raise ValueError('RAM disponibile insufficiente: libera il modello del servizio prima della prova.')
    engine=CompressedEngine(row['archive'],row['config_dir'],options.mode)
    try:
        result=engine.generate([{'role':'user','content':'Quanto fa 17 per 23? Rispondi soltanto con il numero.'}],max_tokens=4,context_window=1024)
        result.update(model=row['id'],original_bytes=row['original_bytes'],compressed_bytes=row['compressed_bytes'],saving_percent=row['saving_percent'])
        (root/'prove_modelli'/('qwen4_'+options.mode+'.json')).write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf8')
        print(json.dumps(result),flush=True)
    finally: engine.close(); del engine; gc.collect()

if __name__=='__main__': main()
