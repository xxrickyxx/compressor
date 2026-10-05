"""Prova opzionale dello streaming contro il server reale già avviato."""
import json
from pathlib import Path
import time
import urllib.request

root=Path(__file__).resolve().parent
key=(root/'api-key.txt').read_text(encoding='utf8').strip()
base=json.loads((root/'runtime.json').read_text(encoding='utf8'))['url'].rstrip('/')
headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'}
request=urllib.request.Request(base+'/v1/models',headers=headers)
with urllib.request.urlopen(request,timeout=10) as response:
    models=json.load(response)['data']
assert any(model['id']=='qwen3-0.6b-cmp' for model in models)
payload={'model':'qwen3-0.6b-cmp','messages':[{'role':'user','content':'Scrivi soltanto la parola Ciao.'}],'max_tokens':4,'temperature':0,'stream':True}
request=urllib.request.Request(base+'/v1/chat/completions',data=json.dumps(payload).encode(),headers=headers)
started=time.perf_counter(); text=''; done=False; finish=None
with urllib.request.urlopen(request,timeout=180) as response:
    assert response.headers['Content-Type'].startswith('text/event-stream')
    for raw in response:
        line=raw.decode('utf8').strip()
        if line=='data: [DONE]': done=True; break
        if not line.startswith('data: '): continue
        event=json.loads(line[6:])
        assert 'error' not in event,event
        choice=event['choices'][0]
        text+=choice['delta'].get('content','')
        finish=choice['finish_reason'] or finish
        if choice['delta'].get('content'): print('Risposta ricevuta: '+text,flush=True)
assert done and finish in ('stop','length') and text.strip()
result={'text':text,'finish_reason':finish,'seconds':time.perf_counter()-started,'stream_completed':done,'server_started_from_cmd':True}
folder=root/'prove_modelli'; folder.mkdir(exist_ok=True)
(folder/'verifica_api_reale.json').write_text(json.dumps(result,indent=2),encoding='utf8')
print(json.dumps(result),flush=True)
