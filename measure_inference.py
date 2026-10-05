"""Misura una breve risposta reale senza caricare il modello intero in RAM."""
import json
from pathlib import Path
from runtime_support import import_torch
from engine import CompressedEngine

root=Path(__file__).resolve().parent
rows=json.loads((root/'prove_modelli/risultati.json').read_text(encoding='utf8'))
row=next(r for r in rows if 'Qwen3' in r['source'])
engine=CompressedEngine(row['archive'],str(Path(row['source']).parent),'direct',status=lambda text:print(text,flush=True))
try:
    result=engine.generate([{'role':'user','content':'Scrivi soltanto la parola Ciao.'}],max_tokens=4)
    result['archive_bytes']=Path(row['archive']).stat().st_size
    result['original_bytes']=row['original_bytes']
    (root/'prove_modelli/memoria_inferenza.json').write_text(json.dumps(result,indent=2),encoding='utf8')
    print(json.dumps(result),flush=True)
finally: engine.close()
