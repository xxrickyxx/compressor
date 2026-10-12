import json
import importlib.util
import os
from pathlib import Path
import secrets
import threading
import time
import traceback
import webbrowser
import argparse
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from chat_store import ChatStore, fit_history
from task_loop import TaskLoop
from compressione import compress, decompress, Archive
from context_limits import DEFAULT_CONTEXT,MAX_CONTEXT,validate_context

ROOT=Path(__file__).resolve().parent
TOKEN=secrets.token_urlsafe(32)
LOCK=threading.RLock()
STOP=threading.Event()
STATE={'busy':False,'phase':'Pronto','progress':0,'answer':'','result':None,'error':None}
ENGINE=None
ENGINE_KEY=None
JOBS={}
API_KEY=None
CHATS=ChatStore(ROOT/"data/chats.sqlite3")
TASKS=TaskLoop(ROOT/"outputs")
PREVIEWS={}

def preview_task(task_id):
    TASKS.load(task_id)
    directory=(TASKS.root/task_id/'site').resolve()
    if not directory.is_relative_to(TASKS.root.resolve()) or not (directory/'index.html').is_file():
        raise ValueError('Il progetto non contiene index.html.')
    if task_id not in PREVIEWS:
        class Preview(SimpleHTTPRequestHandler):
            def __init__(self,*args,**kwargs): super().__init__(*args,directory=str(directory),**kwargs)
            def log_message(self,*args): pass
            def translate_path(self,path):
                target=Path(super().translate_path(path)).resolve()
                return str(target if target.is_relative_to(directory) else directory/'__invalid__')
        if len(PREVIEWS)>=5:
            old=PREVIEWS.pop(next(iter(PREVIEWS))); old.shutdown(); old.server_close()
        task=TASKS.load(task_id)
        if task.get('project_kind')=='gym':
            from backend_runtime import Database,handler_for
            handler=handler_for(directory,Database(directory/'.data'))
        else:handler=Preview
        http=ThreadingHTTPServer(('127.0.0.1',0),handler)
        threading.Thread(target=http.serve_forever,daemon=True).start(); PREVIEWS[task_id]=http
    return {'url':f'http://127.0.0.1:{PREVIEWS[task_id].server_port}/index.html','credentials_file':str(directory/'.data/admin-credentials.json') if TASKS.load(task_id).get('project_kind')=='gym' else None}

def unload_engine():
    global ENGINE,ENGINE_KEY
    import gc
    import psutil
    with LOCK:
        if STATE['busy']: raise ValueError('Attendi la fine dell’operazione corrente prima di liberare la RAM.')
        before=psutil.Process().memory_info().rss
        if ENGINE and isinstance(getattr(getattr(ENGINE,"process",None),"pid",None),int):
            try:before+=psutil.Process(ENGINE.process.pid).memory_info().rss
            except psutil.Error:pass
        if ENGINE:
            ENGINE.close(); ENGINE=None; ENGINE_KEY=None
        gc.collect()
        after=psutil.Process().memory_info().rss
        return {'unloaded':True,'rss_before_bytes':before,'rss_after_bytes':after,'released_rss_bytes':max(0,before-after)}

def get_api_key():
    path=ROOT/'api-key.txt'
    if not path.exists():
        try:
            with path.open('x',encoding='utf8') as f: f.write(secrets.token_urlsafe(32))
        except FileExistsError: pass
    key=path.read_text(encoding='utf8').strip()
    if len(key)<24: raise ValueError('api-key.txt non contiene una chiave valida.')
    return key

def update(**values):
    with LOCK:
        STATE.update(values)
        if STATE.get('job_id') in JOBS: JOBS[STATE['job_id']].update(STATE)

def models():
    path=ROOT/'models.json'
    if not path.exists(): path=ROOT/'prove_modelli'/'risultati.json'
    try: rows=json.loads(path.read_text(encoding='utf8'))
    except (OSError,ValueError): rows=[]
    for row in rows:
        row.setdefault('id','qwen3-0.6b-cmp' if 'Qwen3' in row['source'] else Path(row['archive']).name)
        row.setdefault('label','Qwen3 · 0,6B' if 'Qwen' in row['source'] else ('BitNet · GGUF' if '.gguf' in row['source'] else 'BitNet · safetensors' if 'bitnet' in row['source'] else 'Whisper tiny'))
        row['chat_supported']=(row.get('model_type')=='qwen3' or 'Qwen3' in row['source']) and Path(row['archive']).exists()
        row['config_dir']=row.get('config_dir',str(Path(row['source']).parent))
        try:
            config=json.loads((Path(row['config_dir'])/'config.json').read_text(encoding='utf8'))
            row['max_context_tokens']=min(MAX_CONTEXT,config['max_position_embeddings'])
        except (OSError,ValueError,KeyError): row['max_context_tokens']=MAX_CONTEXT
    return rows

def launch(data):
    with LOCK:
        if STATE['busy']: raise ValueError('Attendi la fine dell’operazione corrente.')
        job_id=uuid.uuid4().hex
        STATE.update(busy=True,phase='Preparazione…',progress=0,answer='',result=None,error=None,job_id=job_id)
        JOBS[job_id]=dict(STATE)
        if len(JOBS)>20: del JOBS[next(iter(JOBS))]
        STOP.clear()
    threading.Thread(target=worker,args=(data,),daemon=True).start()
    return job_id

def worker(data):
    global ENGINE,ENGINE_KEY
    started=time.perf_counter()
    try:
        action=data['action']
        if action in ('chat','agent'):
            from engine import CompressedEngine
            import psutil
            available=[r for r in models() if r['chat_supported']]
            row=next((r for r in available if r['archive']==data.get('archive')),None)
            if row is None: raise ValueError('Seleziona l’archivio Qwen3 disponibile.')
            mode=data.get('mode','direct')
            if mode not in ('direct','ram'): raise ValueError('Modalità non valida.')
            native_context=validate_context(data.get('context_window',DEFAULT_CONTEXT))
            key=(row['archive'],'quant',native_context) if row.get('backend')=='llama.cpp' else (row['archive'],mode)
            if ENGINE_KEY!=key:
                if ENGINE:
                    ENGINE.close(); ENGINE=None; ENGINE_KEY=None
                    import gc; gc.collect()
                if row.get('backend')!='llama.cpp' and mode=='ram' and psutil.virtual_memory().available < row['original_bytes']+700*1024*1024:
                    raise ValueError('RAM libera insufficiente per la cache completa. Usa la modalità a strati o chiudi altri programmi.')
                update(phase='Preparazione motore Qwen3…')
                if row.get('backend')=='llama.cpp':
                    from native_engine import NativeEngine
                    ENGINE=NativeEngine(row,status=lambda text:update(phase=text),stop=STOP,context_window=native_context)
                else:
                    ENGINE=CompressedEngine(row['archive'],row['config_dir'],mode,status=lambda text:update(phase=text),stop=STOP)
                ENGINE_KEY=key
            context_window=validate_context(data.get('context_window',DEFAULT_CONTEXT))
            maximum=max(1,min(4096,int(data.get('max_tokens',48))))
            if action=='agent':
                task=TASKS.load(data['task_id']) if data.get('task_id') else TASKS.create(data.get('goal'),data.get('files'),data.get('project_kind'))
                def generate(items, limit):
                    fitted,_,_=fit_history(ENGINE.tokenizer,items,context_window,limit)
                    return ENGINE.generate(fitted,max_tokens=limit,on_text=lambda text:update(answer=text),context_window=context_window)
                result=TASKS.run(task,generate,STOP,update,data.get('steps',12),data.get('total_tokens',12000))
                update(task_id=task['id'])
            else:
                chat_id=data.get('conversation_id')
                memories=[]; dropped=0
                if chat_id:
                    text=data.get('prompt')
                    if not isinstance(text,str) or not text.strip(): raise ValueError('Messaggio vuoto.')
                    CHATS.append(chat_id,'user',text,{k:data.get(k) for k in ('archive','mode','context_window','max_tokens','recall')})
                    messages=CHATS.get(chat_id)['messages']
                    if data.get('recall'): memories=CHATS.recall(text,chat_id)
                    messages,dropped,recalled=fit_history(ENGINE.tokenizer,messages,context_window,maximum,memories)
                else:
                    messages=data.get('messages',[])
                    if not isinstance(messages,list) or not messages or len(messages)>2000 or any(not isinstance(m,dict) or m.get('role') not in ('system','user','assistant') or not isinstance(m.get('content'),str) for m in messages):
                        raise ValueError('Conversazione non valida.')
                    if sum(len(m['content']) for m in messages)>131072: raise ValueError('Conversazione troppo grande.')
                result=ENGINE.generate(messages,max_tokens=maximum,on_text=lambda text:update(answer=text),context_window=context_window)
                result['model']=row['label']
                if chat_id:
                    CHATS.append(chat_id,'assistant',result['text'])
                    result.update(conversation_id=chat_id,history_messages_omitted=dropped,memory_sources=list({m['id']:{'id':m['id'],'title':m['title']} for m in memories}.values()) if recalled else [])

        else:
            src=data['source']; dst=data.get('target','')
            if not Path(src).is_file(): raise ValueError('Il file di origine non esiste.')
            total=Path(src).stat().st_size if action=='compress' else Archive(src).meta['size']
            def progress(done):
                if STOP.is_set(): raise InterruptedError('Operazione annullata.')
                update(progress=100*done/max(total,1))
            if action=='compress':
                update(phase='Compressione in corso…')
                compress(src,dst,progress=progress,codec=data.get("codec","zlib"))
                update(phase='Verifica integrità…',progress=0)
                Archive(dst).verify(progress=progress)
                size=Path(dst).stat().st_size
                result={'original_bytes':total,'compressed_bytes':size,'saving_percent':100*(1-size/total) if total else 0,'archive':dst,'integrity':'OK'}
            elif action=='extract':
                update(phase='Ricostruzione e verifica…'); decompress(src,dst,progress=progress,codec=data.get("codec","zlib"))
                result={'file':dst,'integrity':'OK'}
            elif action=='verify':
                update(phase='Verifica integrità…'); Archive(src).verify(progress=progress)
                result={'file':src,'integrity':'OK'}
            else: raise ValueError('Operazione non riconosciuta.')
            result['seconds']=time.perf_counter()-started
        update(result=result,phase='Completato',progress=100)
    except Exception as exc:
        traceback.print_exc()
        update(error=str(exc),phase='Operazione interrotta')
        if ENGINE:
            ENGINE.close(); ENGINE=None; ENGINE_KEY=None
    finally: update(busy=False)

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def send(self,value,status=200):
        raw=json.dumps(value,ensure_ascii=False).encode('utf8')
        self.send_response(status); self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Cache-Control','no-store'); self.end_headers(); self.wfile.write(raw)
    def do_GET(self):
        path=urlparse(self.path).path
        if path=='/health':
            missing=[name for name in ('torch','transformers','psutil','safetensors','zstandard') if importlib.util.find_spec(name) is None]
            self.send({'status':'ok','version':'0.6','inference_ready':not missing,'missing_dependencies':missing}); return
        if path.startswith('/v1/') or path=='/openapi.json':
            if not self.authorized(): self.send({'error':{'message':'Chiave API non valida','type':'authentication_error'}},401); return
            if path=='/v1/models':
                self.send({'object':'list','data':[{'id':r['id'],'object':'model','owned_by':'local'} for r in models() if r['chat_supported']]})
            elif path.startswith('/v1/jobs/'):
                with LOCK: job=JOBS.get(path.rsplit('/',1)[-1]); job=dict(job) if job else None
                self.send(job if job else {'error':'Operazione non trovata'},200 if job else 404)
            elif path=='/openapi.json': self.send(json.loads((ROOT/'openapi.json').read_text(encoding='utf8')))
            else: self.send({'error':'Endpoint non trovato'},404)
            return
        if not self.local_client(): self.send({'error':'Interfaccia disponibile solo su questo computer'},403); return
        if path=='/':
            raw=(ROOT/'index.html').read_text(encoding='utf8').replace('__TOKEN__',TOKEN).encode('utf8')
            self.send_response(200); self.send_header('Content-Type','text/html; charset=utf-8'); self.send_header('Cache-Control','no-store'); self.end_headers(); self.wfile.write(raw)
        elif path=='/i18n.js':
            raw=(ROOT/'i18n.js').read_bytes(); self.send_response(200); self.send_header('Content-Type','text/javascript; charset=utf-8'); self.end_headers(); self.wfile.write(raw)
        elif self.headers.get('X-App-Token')!=TOKEN: self.send({'error':'Accesso non autorizzato'},403)
        elif path=='/api/state':
            import psutil
            with LOCK:
                snapshot=dict(STATE)
                snapshot['engine_mode']=ENGINE.mode if ENGINE else None
                snapshot['app_rss_bytes']=psutil.Process().memory_info().rss
                snapshot['engine_rss_bytes']=0
                if ENGINE and isinstance(getattr(getattr(ENGINE,'process',None),'pid',None),int):
                    try:snapshot['engine_rss_bytes']=psutil.Process(ENGINE.process.pid).memory_info().rss
                    except psutil.Error:pass
                snapshot['process_rss_bytes']=snapshot['app_rss_bytes']+snapshot['engine_rss_bytes']
            self.send(snapshot)
        elif path=='/api/models': self.send(models())
        elif path=='/api/chats': self.send(CHATS.list())
        elif path=='/api/chat':
            try: self.send(CHATS.get(parse_qs(urlparse(self.path).query).get('id',[''])[0]))
            except ValueError as exc: self.send({'error':str(exc)},404)
        elif path=='/api/tasks': self.send(TASKS.list())
        elif path=='/api/integration':
            available=[r for r in models() if r['chat_supported']]
            self.send({'base_url':f'http://127.0.0.1:{self.server.server_port}/v1','api_key':API_KEY,'model':available[0]['id'] if available else ''})
        else: self.send({'error':'Pagina non trovata'},404)
    def do_POST(self):
        if self.path.startswith('/v1/'):
            self.public_post(); return
        if not self.local_client(): self.send({'error':'Accesso solo locale'},403); return
        if self.headers.get('X-App-Token')!=TOKEN:
            self.send({'error':'Accesso non autorizzato'},403); return
        try:
            length=int(self.headers.get('Content-Length',0))
            if not 0<length<=1048576: raise ValueError('Richiesta troppo grande.')
            data=json.loads(self.rfile.read(length))
            if self.path=='/api/run': job_id=launch(data); self.send({'ok':True,'job_id':job_id})
            elif self.path=='/api/chats/create': self.send(CHATS.create())
            elif self.path=='/api/chats/restore':
                self.send(CHATS.restore(data.get('id')))
            elif self.path=='/api/chats/delete':
                if STATE['busy']: raise ValueError('Attendi la fine dell’operazione corrente.')
                CHATS.delete(data.get('id')); self.send({'ok':True})
            elif self.path=='/api/tasks/credentials':
                task=TASKS.load(data.get('id'))
                if task.get('project_kind')!='gym':raise ValueError('Il progetto non ha un backend gestito.')
                self.send(json.loads((TASKS.root/task['id']/'site/.data/admin-credentials.json').read_text()))
            elif self.path=='/api/tasks/upgrade':
                if STATE['busy']:raise ValueError('Attendi la fine dell’operazione corrente.')
                task=TASKS.load(data.get('id'));task['project_kind']='gym';TASKS.save(task);self.send(task)
            elif self.path=='/api/tasks/preview': self.send(preview_task(data.get('id')))
            elif self.path=='/api/stop': STOP.set(); self.send({'ok':True})
            elif self.path=='/api/unload': self.send(unload_engine())
            elif self.path=='/api/pick':
                import tkinter as tk
                from tkinter import filedialog
                root=tk.Tk(); root.withdraw(); root.attributes('-topmost',True)
                try:
                    if data.get('save'): value=filedialog.asksaveasfilename(parent=root,initialfile=data.get('name','modello.cmp'))
                    else: value=filedialog.askopenfilename(parent=root,initialdir=str(Path.home()/'Desktop'))
                finally: root.destroy()
                self.send({'path':value})
            else: self.send({'error':'Operazione non trovata'},404)
        except Exception as exc: self.send({'error':str(exc)},400)

    def local_client(self): return self.client_address[0] in ('127.0.0.1','::1')

    def authorized(self):
        value=self.headers.get('Authorization','')
        return API_KEY is not None and secrets.compare_digest(value,'Bearer '+API_KEY)

    def public_post(self):
        if not self.authorized(): self.send({'error':{'message':'Chiave API non valida','type':'authentication_error'}},401); return
        streaming=False
        job_id=None
        try:
            length=int(self.headers.get('Content-Length',0))
            if not 0<length<=1048576: raise ValueError('Richiesta troppo grande.')
            data=json.loads(self.rfile.read(length))
            if not isinstance(data,dict): raise ValueError('Serve un oggetto JSON.')
            if self.path=='/v1/jobs':
                if data.get('action') not in ('compress','extract','verify'): raise ValueError('Azione ammessa: compress, extract, verify.')
                job_id=launch(data); self.send({'id':job_id,'object':'job'},202); return
            if self.path.startswith('/v1/jobs/') and self.path.endswith('/cancel'):
                job_id=self.path.split('/')[3]
                with LOCK:
                    if STATE.get('job_id')!=job_id or not STATE['busy']: raise ValueError('Operazione non attiva.')
                    STOP.set()
                self.send({'id':job_id,'cancel_requested':True}); return
            if self.path!='/v1/chat/completions': self.send({'error':'Endpoint non trovato'},404); return
            row=next((r for r in models() if r['chat_supported'] and r['id']==data.get('model')),None)
            if row is None: raise ValueError('Modello non disponibile. Consulta GET /v1/models.')
            messages=data.get('messages')
            if not isinstance(messages,list) or not messages or len(messages)>200 or any(not isinstance(m,dict) or m.get('role') not in ('system','user','assistant') or not isinstance(m.get('content'),str) for m in messages):
                raise ValueError('messages deve contenere messaggi system/user/assistant con content testuale.')
            if sum(len(m['content']) for m in messages)>131072: raise ValueError('Conversazione troppo grande.')
            context_window=validate_context(data.get('context_window',DEFAULT_CONTEXT))
            mode=data.get('compression_mode','direct')
            if mode not in ('direct','ram'): raise ValueError('compression_mode deve essere direct o ram.')
            maximum=data.get('max_tokens',data.get('max_completion_tokens',48))
            if isinstance(maximum,bool) or not isinstance(maximum,int) or not 1<=maximum<=4096: raise ValueError('max_tokens deve essere compreso fra 1 e 4096.')
            if data.get('temperature',0)!=0: raise ValueError('Questa versione supporta solo temperature=0.')
            if any(data.get(k) for k in ('tools','tool_choice','response_format')): raise ValueError('Tools e formati strutturati non sono ancora supportati.')
            if data.get('n',1)!=1: raise ValueError('Questa versione supporta solo n=1.')
            if not isinstance(data.get('stream',False),bool): raise ValueError('stream deve essere booleano.')
            job_id=launch({'action':'chat','archive':row['archive'],'messages':messages,'mode':mode,'max_tokens':maximum,'context_window':context_window})
            created=int(time.time()); response_id='chatcmpl-'+job_id
            streaming=data.get('stream',False)
            sent=''
            if streaming:
                self.send_response(200); self.send_header('Content-Type','text/event-stream; charset=utf-8')
                self.send_header('Cache-Control','no-cache'); self.end_headers()
                self.event({'id':response_id,'object':'chat.completion.chunk','created':created,'model':row['id'],'choices':[{'index':0,'delta':{'role':'assistant'},'finish_reason':None}]})
            heartbeat=time.monotonic()
            while True:
                with LOCK: state=dict(JOBS[job_id])
                answer=state['answer']
                if streaming and answer.startswith(sent) and answer!=sent and not answer.endswith('\ufffd'):
                    delta=answer[len(sent):]; sent=answer
                    self.event({'id':response_id,'object':'chat.completion.chunk','created':created,'model':row['id'],'choices':[{'index':0,'delta':{'content':delta},'finish_reason':None}]})
                if not state['busy']: break
                if streaming and time.monotonic()-heartbeat>15:
                    self.wfile.write(b': keep-alive\n\n'); self.wfile.flush(); heartbeat=time.monotonic()
                time.sleep(.2)
            if state['error']: raise ValueError(state['error'])
            result=state['result']; finish=result.get('finish_reason','stop')
            if streaming:
                self.event({'id':response_id,'object':'chat.completion.chunk','created':created,'model':row['id'],'choices':[{'index':0,'delta':{},'finish_reason':finish}]})
                self.wfile.write(b'data: [DONE]\n\n'); self.wfile.flush()
            else:
                self.send({'id':response_id,'object':'chat.completion','created':created,'model':row['id'],
                  'choices':[{'index':0,'message':{'role':'assistant','content':result['text']},'finish_reason':finish}],
                  'usage':{'prompt_tokens':result.get('prompt_tokens',0),'completion_tokens':result['tokens'],'total_tokens':result.get('prompt_tokens',0)+result['tokens']}})
        except (BrokenPipeError,ConnectionResetError,ConnectionAbortedError):
            with LOCK:
                if job_id==STATE.get('job_id') and STATE['busy']: STOP.set()
        except Exception as exc:
            error={'error':{'message':str(exc),'type':'invalid_request_error'}}
            if streaming:
                try: self.event(error); self.wfile.write(b'data: [DONE]\n\n'); self.wfile.flush()
                except OSError: pass
            else: self.send(error,409 if 'corrente' in str(exc) else 400)

    def event(self,value):
        self.wfile.write(('data: '+json.dumps(value,ensure_ascii=False)+'\n\n').encode('utf8')); self.wfile.flush()

def main():
    global API_KEY
    args=argparse.ArgumentParser(description='Compressione: interfaccia e API locali')
    args.add_argument('--host',default='127.0.0.1'); args.add_argument('--port',type=int,default=8765); args.add_argument('--no-browser',action='store_true')
    options=args.parse_args()
    API_KEY=get_api_key()
    server=ThreadingHTTPServer((options.host,options.port),Handler)
    url=f'http://127.0.0.1:{server.server_port}/'
    (ROOT/'runtime.json').write_text(json.dumps({'url':url,'pid':os.getpid(),'version':'0.6'}),encoding='utf8')
    if not options.no_browser: webbrowser.open(url)
    print(url,flush=True)
    server.serve_forever()

if __name__=='__main__': main()
