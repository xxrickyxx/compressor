"""Optional end-to-end test with installed weights and the running local server."""
import json
import re
import time
import urllib.request
from pathlib import Path

def main():
    base='http://127.0.0.1:8765/'
    html=urllib.request.urlopen(base).read().decode()
    token=re.search("const TOKEN='([^']+)'",html).group(1)
    def api(path,data=None):
        request=urllib.request.Request(base+'api/'+path,data=json.dumps(data).encode() if data is not None else None,headers={'X-App-Token':token,'Content-Type':'application/json'})
        return json.load(urllib.request.urlopen(request,timeout=10))
    def wait(job):
        while True:
            state=api('state')
            if not state['busy']:
                if state['error']: raise RuntimeError(state['error'])
                return state['result']
            time.sleep(2)
    model=next(r for r in api('models') if r['id']=='qwen3-1.7b-cmp')
    chat=api('chats/create',{})
    common={'action':'chat','archive':model['archive'],'mode':'ram','conversation_id':chat['id'],'max_tokens':16,'context_window':1024}
    results=[]
    for prompt in ['Ricorda: il colore scelto per il sito Aurora è verde. Rispondi soltanto OK.','Qual è il colore scelto per il sito Aurora? Rispondi con una parola.']:
        job=api('run',dict(common,prompt=prompt)); result=wait(job); results.append(result)
        print(json.dumps({'prompt':prompt,'answer':result['text'],'seconds':result['seconds']}),flush=True)
    saved=api('chat?id='+chat['id'])
    assert len(saved['messages'])==4
    task={'action':'agent','archive':model['archive'],'mode':'ram','context_window':4096,'steps':8,'total_tokens':5000,
          'goal':'Create a minimal COMPLETE static website for Aurora bicycle workshop. Each file MUST be very short, under 100 tokens. Use three pages with nav links and one heading each. All HTML pages link style.css and script.js. CSS: dark background, lime text. JavaScript: set document title to Aurora. No images, no forms, no external links. Finish every HTML file with </html>.',
          'files':['index.html','about.html','contact.html','style.css','script.js']}
    api('run',task)
    result=wait(None)
    output={'chat_id':chat['id'],'chat_results':results,'task':result}
    Path('prove_modelli/live_features.json').write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({'task_id':result['id'],'status':result['status'],'done':result['done'],'steps':result['steps'],'output':result['output'],'problems':result['problems']}),flush=True)

if __name__=='__main__': main()
