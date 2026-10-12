"""Scoped file tools and trusted backend scaffolding; no model shell execution."""
import ast
import hashlib
import http.cookiejar
import json
from pathlib import Path
import shutil
import tempfile
import threading
import urllib.request
import urllib.error
from http.server import ThreadingHTTPServer
from backend_runtime import Database,handler_for

MANAGER='''<!doctype html><html lang="it"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Gestionale palestra</title><link rel="stylesheet" href="style.css"></head><body><nav><a href="index.html">Palestra</a><a href="gestionale.html">Gestionale</a></nav><main><small>IL TUO SPAZIO</small><h1>Lezioni, persone, progressi.</h1><p id="identity">Accedi o crea un account per prenotare le lezioni.</p><p id="notice" role="status"></p><section id="access" class="grid"><form id="login"><h2>Accedi</h2><label>Email<input name="email" type="email" required autocomplete="username"></label><label>Password<input name="password" type="password" required autocomplete="current-password"></label><button>Accedi</button></form><form id="register"><h2>Registrati</h2><label>Nome<input name="name" required maxlength="100"></label><label>Email<input name="email" type="email" required></label><label>Password<input name="password" type="password" required minlength="8" autocomplete="new-password"></label><button>Crea account</button></form></section><button id="logout" hidden>Esci</button><section><h2>Lezioni disponibili</h2><div id="lessons"></div></section><form id="lesson-form" hidden><h2>Nuova lezione</h2><div class="grid"><label>Titolo<input name="title" required maxlength="100"></label><label>Istruttore<input name="instructor" required maxlength="100"></label><label>Data e ora<input name="starts_at" type="datetime-local" required></label><label>Posti<input name="capacity" type="number" min="1" max="500" value="10" required></label></div><button>Crea lezione</button></form><section id="booking-section" hidden><h2>Prenotazioni</h2><div id="bookings"></div></section><section id="users-section" hidden><h2>Utenti registrati</h2><div id="users"></div></section><footer>Applicazione locale · dati salvati su questo computer</footer></main><script src="script.js"></script></body></html>'''
CSS=''' :root{color-scheme:dark;--bg:#10151b;--card:#1b232d;--lime:#c4f56c;--text:#edf3f7;--muted:#a5b4c3}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:16px system-ui,sans-serif}nav{display:flex;gap:24px;padding:24px 6vw;border-bottom:1px solid #34404d}a{color:var(--lime)}main{max-width:1100px;margin:auto;padding:48px 24px}h1{font-size:clamp(32px,5vw,62px);letter-spacing:-2px}h2{font-size:23px}small{letter-spacing:3px;color:var(--lime)}p,footer{color:var(--muted);line-height:1.7}.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:24px}form,section{margin:24px 0}form,.item{background:var(--card);border:1px solid #34404d;border-radius:16px;padding:24px}label{display:block;margin:12px 0;color:var(--muted)}input{display:block;width:100%;padding:12px;margin-top:8px;background:#10151b;color:var(--text);border:1px solid #526274;border-radius:8px;font:inherit}button{border:0;border-radius:8px;background:var(--lime);color:#14200c;padding:12px 20px;font:inherit;cursor:pointer;margin:8px 8px 8px 0}button:disabled{opacity:.4}.item{margin:12px 0}.item strong{display:block;margin-bottom:8px}#notice{color:var(--lime)}[hidden]{display:none!important}@media(max-width:700px){.grid{grid-template-columns:1fr}nav{flex-wrap:wrap;gap:12px}}'''
SCRIPT='''let me=null;const $=id=>document.getElementById(id);async function request(path,data,method='POST'){const response=await fetch('/api/'+path,{method:data?method:'GET',headers:{'Content-Type':'application/json','X-CSRF-Token':me?.csrf||''},body:data?JSON.stringify(data):undefined});const value=await response.json();if(!response.ok)throw Error(value.error||'Operazione non riuscita');return value}function notice(text){if($('notice'))$('notice').textContent=text}function item(container,title,details,buttons=[]){const box=document.createElement('div');box.className='item';const strong=document.createElement('strong');strong.textContent=title;const detail=document.createElement('p');detail.textContent=details;box.append(strong,detail);buttons.forEach(([text,action])=>{const button=document.createElement('button');button.textContent=text;button.onclick=async()=>{try{await action();notice('Operazione completata');await refresh()}catch(e){notice(e.message)}};box.append(button)});container.append(box)}async function refresh(){if(!$('lessons'))return;me=(await request('me')).user;$('identity').textContent=me?'Ciao '+me.name+' · '+(me.role==='admin'?'Amministratore':'Iscritto'):'Accedi o crea un account per prenotare.';$('access').hidden=!!me;$('logout').hidden=!me;$('lesson-form').hidden=me?.role!=='admin';$('booking-section').hidden=!me;$('users-section').hidden=me?.role!=='admin';$('lessons').textContent='';for(const l of await request('lessons')){const buttons=[];if(me&&l.booked<l.capacity)buttons.push(['Prenota',()=>request('bookings',{lesson_id:l.id})]);if(me?.role==='admin')buttons.push(['Elimina lezione',()=>request('lessons/'+l.id,{},'DELETE')]);item($('lessons'),l.title,l.instructor+' · '+l.starts_at.replace('T',' ')+' · '+l.booked+'/'+l.capacity+' posti',buttons)}if(me){$('bookings').textContent='';for(const b of await request('bookings'))item($('bookings'),b.title,b.name+' · '+b.starts_at,[['Annulla prenotazione',()=>request('bookings/'+b.id,{},'DELETE')]])}if(me?.role==='admin'){$('users').textContent='';for(const u of await request('users'))item($('users'),u.name,u.email+' · '+u.role)}}function bind(id,fn){if($(id))$(id).onsubmit=async e=>{e.preventDefault();try{await fn(Object.fromEntries(new FormData(e.target)));e.target.reset();await refresh()}catch(error){notice(error.message)}}}bind('login',async data=>{me=(await request('login',data)).user;notice('Accesso effettuato')});bind('register',async data=>{await request('register',data);notice('Account creato. Ora puoi accedere.')});bind('lesson-form',async data=>{data.capacity=Number(data.capacity);await request('lessons',data);notice('Lezione creata')});if($('logout'))$('logout').onclick=async()=>{try{await request('logout',{});me=null;await refresh()}catch(e){notice(e.message)}};refresh().catch(e=>notice(e.message));'''

class ProjectTools:
    def __init__(self, directory):self.directory=Path(directory).resolve();self.directory.mkdir(parents=True,exist_ok=True)
    def path(self,name):
        from task_loop import safe_path
        return safe_path(self.directory,name)
    def list_files(self):return [str(p.relative_to(self.directory)).replace('\\','/') for p in self.directory.rglob('*') if p.is_file() and '.data' not in p.parts][:200]
    def read_file(self,name):return self.path(name).read_text(encoding='utf8')[:16000]
    def write_file(self,name,text):
        if self.path(name)==self.directory/'backend.py':raise ValueError('Il runtime backend è gestito dal programma; modifica configurazione e interfaccia.')
        if not isinstance(text,str) or len(text)>500000:raise ValueError('File troppo grande.')
        target=self.path(name);target.parent.mkdir(parents=True,exist_ok=True);tmp=target.with_suffix(target.suffix+'.tmp');tmp.write_text(text,encoding='utf8');tmp.replace(target)
    def replace_text(self,name,old,new):
        text=self.read_file(name)
        if not old or text.count(old)!=1:raise ValueError('La porzione da modificare deve comparire una sola volta.')
        self.write_file(name,text.replace(old,new,1))
    def scaffold_backend(self,task):
        backend=Path(__file__).with_name('backend_runtime.py').read_text(encoding='utf8')
        target=self.path('backend.py')
        if target.exists() and target.read_text(encoding='utf8')!=backend:shutil.copyfile(target,self.directory/'.backend.previous.py')
        target.write_text(backend,encoding='utf8')
        task['backend_sha256']=hashlib.sha256(backend.encode()).hexdigest()
        files=['index.html','about.html','contact.html','style.css','script.js','gestionale.html','backend.py','README.md']
        pages={'index.html':('Palestra','Allenati, prenota, migliora.','Una palestra per muoverti con energia. Scopri le lezioni e prenota dal gestionale.'),'about.html':('Chi siamo','Il tuo allenamento, al tuo ritmo.','Istruttori, lezioni e una comunità dedicata al movimento.'),'contact.html':('Contatti','Iniziamo insieme.','Inserisci qui i contatti e gli orari della tua palestra prima di pubblicare il sito.')}
        for name,(title,heading,body) in pages.items():
            if not self.path(name).exists():self.write_file(name,'<!doctype html><html lang="it"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+title+'</title><link rel="stylesheet" href="style.css"></head><body><nav><a href="index.html">Palestra</a><a href="gestionale.html">Gestionale</a></nav><main><small>PALESTRA · STUDIO LOCALE</small><h1>'+heading+'</h1><p>'+body+'</p><a href="gestionale.html">Apri lezioni e prenotazioni ↗</a></main><script src="script.js"></script></body></html>')
        for name,text in [('style.css',CSS),('script.js',SCRIPT),('gestionale.html',MANAGER)]:
            if not self.path(name).exists():self.write_file(name,text)
        self.write_file('README.md','# Gestionale palestra locale\n\nAvvia `python backend.py` e apri http://127.0.0.1:8780/index.html. Dalla scheda Progetti di Compressione usa Anteprima per avviarlo senza terminale.\n\nIl primo avvio crea un amministratore. Credenziali in `.data/admin-credentials.json`, database in `.data/gym.sqlite3`. Cambia e conserva queste credenziali in modo sicuro. Iscritti: registrazione, login, prenotazione e annullamento. Amministratore: lezioni, elenco utenti e prenotazioni. Backend locale, non pubblicato su Internet. Per uso online servono HTTPS, recupero password, distribuzione e verifiche di produzione.\n')
        for name in files:
            if name not in task['files']:task['files'].append(name)
        task['done']=list(task['files']);task['pending']='';task['project_kind']='gym'
        task.setdefault('tool_log',[]).append({'tool':'scaffold_backend','files':files})
        return task

    def test_backend(self):
        return test_backend(self.directory)

def test_backend(directory):
    with tempfile.TemporaryDirectory(prefix='.checks-',dir=directory) as temporary:
        root=Path(temporary);database=Database(root/'.data');server=ThreadingHTTPServer(('127.0.0.1',0),handler_for(root,database))
        threading.Thread(target=server.serve_forever,daemon=True).start();base=f'http://127.0.0.1:{server.server_port}/api/'
        def client():return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        admin=client();member=client();other=client()
        def call(client,path,data=None,csrf='',method='POST'):
            request=urllib.request.Request(base+path,data=json.dumps(data).encode() if data is not None else None,method=method if data is not None else 'GET',headers={'Content-Type':'application/json','X-CSRF-Token':csrf})
            return json.load(client.open(request,timeout=10))
        try:
            credentials=json.loads((root/'.data/admin-credentials.json').read_text())
            adm=call(admin,'login',credentials)['user'];a=adm['csrf']
            first=call(member,'register',{'name':'Test member','email':'member@example.test','password':'test-password-123'})
            call(other,'register',{'name':'Other','email':'other@example.test','password':'test-password-456'})
            m=call(member,'login',{'email':'member@example.test','password':'test-password-123'})['user'];o=call(other,'login',{'email':'other@example.test','password':'test-password-456'})['user']
            lesson=call(admin,'lessons',{'title':'Test Pilates','instructor':'Test','starts_at':'2030-01-01T10:00','capacity':1},a)['id']
            booking=call(member,'bookings',{'lesson_id':lesson},m['csrf'])['id']
            for request in [(other,'bookings',{'lesson_id':lesson},o['csrf'],'POST'),(member,'lessons',{'title':'Forbidden'},m['csrf'],'POST'),(admin,'lessons',{},'wrong-csrf','POST'),(other,'bookings/'+str(booking),{},o['csrf'],'DELETE')]:
                try:call(*request)
                except urllib.error.HTTPError as error:assert error.code in (400,403)
                else:raise AssertionError('Permission/capacity checks failed')
            assert len(call(admin,'users'))==3;assert len(call(member,'bookings'))==1
            call(member,'bookings/'+str(booking),{},m['csrf'],'DELETE')
            assert not call(member,'bookings')
            reopened=Database(root/'.data')
            with reopened.connect() as db:assert db.execute('SELECT COUNT(*) FROM users').fetchone()[0]==3
            return {'passed':True,'checks':['registration','login','admin permissions','create lesson','booking','capacity limit','CSRF','booking ownership','cancellation','users list','SQLite persistence'],'database':'disposable test database; project data untouched'}
        finally:server.shutdown();server.server_close()
