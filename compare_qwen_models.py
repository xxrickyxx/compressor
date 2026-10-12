"""Piccolo confronto riproducibile; non è una valutazione generale di qualità."""
import gc
import argparse
import json
from pathlib import Path
import re
import time
import psutil
from engine import CompressedEngine

TASKS=[
    ('moltiplicazione','Quanto fa 17 per 23? Rispondi soltanto con il numero.',{'391'}),
    ('sequenza','Completa la sequenza: 2, 4, 8, 16, ?. Rispondi soltanto con il numero.',{'32'}),
    ('logica','Anna è più alta di Bruno. Bruno è più alto di Carlo. Chi è il più alto? Rispondi soltanto con il nome.',{'anna'}),
    ('istruzione','Rispondi esattamente con queste due parole: COMPRESSORE OK',{'compressore ok'}),
    ('elementi_distinti','Da mele, pere, mele, banane restituisci gli elementi distinti in ordine di prima comparsa, separati da virgole. Nessun altro testo.',{'mele pere banane'}),
    ('traduzione','Traduci in inglese: Il gatto dorme. Scrivi soltanto la traduzione.',{'the cat sleeps','the cat is sleeping'}),
]

def normalize(text): return ' '.join(re.sub(r'[^\w\s]',' ',text.casefold()).split())

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--models',nargs='+',default=['qwen3-0.6b-cmp','qwen3-1.7b-cmp'])
    selected=parser.parse_args().models
    root=Path(__file__).resolve().parent
    rows=json.loads((root/'models.json').read_text(encoding='utf8'))
    output=root/'prove_modelli/confronto_qwen.json'
    results=json.loads(output.read_text(encoding='utf8')) if output.exists() else []
    for model_id in selected:
        row=next(r for r in rows if r.get('id')==model_id)
        available=psutil.virtual_memory().available
        if available < row['original_bytes']+700*1024*1024:
            raise RuntimeError(f'RAM libera insufficiente per il confronto in cache: {model_id}.')
        print('Preparazione '+model_id,flush=True)
        engine=CompressedEngine(row['archive'],row['config_dir'],'ram')
        try:
            answers=[]
            for name,prompt,expected in TASKS:
                result=engine.generate([{'role':'user','content':prompt}],max_tokens=24,context_window=1024)
                result['task']=name; result['prompt']=prompt; result['passed']=normalize(result['text']) in expected
                answers.append(result)
                print(json.dumps({'model':model_id,'task':name,'answer':result['text'],'passed':result['passed'],'seconds':round(result['seconds'],2)}),flush=True)
            total_tokens=sum(a['tokens'] for a in answers)
            total_seconds=sum(a['seconds'] for a in answers)
            result={'id':model_id,'label':row['label'],'mode':'ram','tests_passed':sum(a['passed'] for a in answers),
                    'tests_total':len(TASKS),'rss_peak_bytes':max(a['rss_peak_bytes'] for a in answers),
                    'tokens_s_including_first_load':total_tokens/total_seconds,
                    'warm_tokens_s':sum(a['tokens'] for a in answers[1:])/sum(a['seconds'] for a in answers[1:]),
                    'first_request_seconds':answers[0]['seconds'],'answers':answers,
                    'original_bytes':row['original_bytes'],'compressed_bytes':row['compressed_bytes'],'saving_percent':row['saving_percent']}
            results=[r for r in results if r['id']!=model_id]+[result]
            output.write_text(json.dumps(results,indent=2,ensure_ascii=False),encoding='utf8')
        finally:
            engine.close(); del engine; gc.collect()
    lines=['# Confronto Qwen3 locale', '', '12 ottobre 2026. Cache in RAM, CPU, generazione deterministica, contesto 1.024, massimo 24 token per risposta.',
           'Sei prove brevi: moltiplicazione, sequenza, confronto logico, istruzione esatta, deduplicazione e traduzione. Il punteggio non misura la qualità generale.', '',
           '| Modello | Esiti esatti | Picco RSS MB | Token/s dopo il primo caricamento | Risparmio file |', '|---|---:|---:|---:|---:|']
    for r in results:
        lines.append(f"| {r['label']} | {r['tests_passed']}/{r['tests_total']} | {r['rss_peak_bytes']/1e6:.1f} | {r['warm_tokens_s']:.2f} | {r['saving_percent']:.2f}% |")
    for r in results:
        lines.extend(['', '## '+r['label']])
        for a in r['answers']: lines.extend(['',f"**{a['task']}** — {'corretto' if a['passed'] else 'non corrispondente alla risposta attesa'}",'',a['text']])
    (root/'prove_modelli/CONFRONTO_QWEN.md').write_text('\n'.join(lines),encoding='utf8')
    print('Confronto completato.',flush=True)

if __name__=='__main__': main()
