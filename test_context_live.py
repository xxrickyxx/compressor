"""Prova opzionale: prompt oltre 512 token contro il servizio già avviato."""
import json
from pathlib import Path
import time
import urllib.request

def main():
    root=Path(__file__).resolve().parent
    key=(root/'api-key.txt').read_text(encoding='utf8').strip()
    base=json.loads((root/'runtime.json').read_text(encoding='utf8'))['url'].rstrip('/')
    prompt='hello '*550+'\nRispondi con una sola parola.'
    payload={'model':'qwen3-0.6b-cmp','messages':[{'role':'user','content':prompt}],
             'context_window':1024,'max_tokens':1,'temperature':0}
    request=urllib.request.Request(base+'/v1/chat/completions',data=json.dumps(payload).encode(),
              headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'})
    started=time.perf_counter()
    with urllib.request.urlopen(request,timeout=600) as response: result=json.load(response)
    assert result['usage']['prompt_tokens']>512,result['usage']
    assert result['usage']['total_tokens']<=1024,result['usage']
    assert result['choices'][0]['message']['content']
    record={'prompt_tokens':result['usage']['prompt_tokens'],'total_tokens':result['usage']['total_tokens'],
            'answer':result['choices'][0]['message']['content'],'context_window':1024,'seconds':time.perf_counter()-started}
    (root/'prove_modelli/verifica_contesto.json').write_text(json.dumps(record,indent=2),encoding='utf8')
    print(json.dumps(record),flush=True)

if __name__=='__main__': main()
