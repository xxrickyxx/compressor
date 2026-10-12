"""Trusted local gym backend, used by project tools and standalone generated apps."""
import argparse
from contextlib import contextmanager
from datetime import datetime
import hashlib
import json
from pathlib import Path
import secrets
import sqlite3
import time
from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import urlparse

class Database:
    def __init__(self, root):
        self.root=Path(root); self.root.mkdir(parents=True,exist_ok=True)
        self.path=self.root/'gym.sqlite3'
        with self.connect() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY,name TEXT NOT NULL,email TEXT UNIQUE NOT NULL,salt TEXT NOT NULL,password TEXT NOT NULL,role TEXT NOT NULL DEFAULT 'member');
              CREATE TABLE IF NOT EXISTS lessons(id INTEGER PRIMARY KEY,title TEXT NOT NULL,instructor TEXT NOT NULL,starts_at TEXT NOT NULL,capacity INTEGER NOT NULL);
              CREATE TABLE IF NOT EXISTS bookings(id INTEGER PRIMARY KEY,user_id INTEGER REFERENCES users(id),lesson_id INTEGER REFERENCES lessons(id) ON DELETE CASCADE,UNIQUE(user_id,lesson_id));
              CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY,user_id INTEGER REFERENCES users(id),csrf TEXT,expires REAL);''')
            first=db.execute('SELECT COUNT(*) FROM users WHERE role="admin"').fetchone()[0]==0
        if first:
            password=secrets.token_urlsafe(18)
            self.register('Amministratore','admin@localhost',password,'admin')
            (self.root/'admin-credentials.json').write_text(json.dumps({'email':'admin@localhost','password':password}),encoding='utf8')

    @contextmanager
    def connect(self):
        db=sqlite3.connect(self.path,timeout=10);db.row_factory=sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            with db: yield db
        finally:db.close()

    def register(self,name,email,password,role='member'):
        if not isinstance(name,str) or not name.strip() or len(name)>100:raise ValueError('Nome non valido.')
        if not isinstance(email,str) or '@' not in email or len(email)>200:raise ValueError('Email non valida.')
        if not isinstance(password,str) or not 8<=len(password)<=256:raise ValueError('La password deve avere da 8 a 256 caratteri.')
        salt=secrets.token_hex(16); digest=hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(salt),300000).hex()
        with self.connect() as db:
            try:return db.execute('INSERT INTO users(name,email,salt,password,role) VALUES(?,?,?,?,?)',(name.strip(),email.strip().lower(),salt,digest,role)).lastrowid
            except sqlite3.IntegrityError:raise ValueError('Email già registrata.')

    def login(self,email,password):
        if not isinstance(email,str) or not isinstance(password,str) or len(password)>256:raise ValueError('Credenziali non valide.')
        with self.connect() as db:
            user=db.execute('SELECT * FROM users WHERE email=?',(email.lower().strip(),)).fetchone()
            salt=bytes.fromhex(user['salt']) if user else bytes(16)
            digest=hashlib.pbkdf2_hmac('sha256',password.encode(),salt,300000).hex()
            if not user or not secrets.compare_digest(digest,user['password']):raise ValueError('Credenziali non valide.')
            token=secrets.token_urlsafe(32);csrf=secrets.token_urlsafe(24)
            db.execute('DELETE FROM sessions WHERE expires<?',(time.time(),))
            db.execute('INSERT INTO sessions VALUES(?,?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),user['id'],csrf,time.time()+28800))
            return token,{'id':user['id'],'name':user['name'],'email':user['email'],'role':user['role'],'csrf':csrf}

def handler_for(directory,database):
    directory=Path(directory).resolve()
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self,*args,**kwargs):super().__init__(*args,directory=str(directory),**kwargs)
        def log_message(self,*args):pass
        def translate_path(self,path):
            target=Path(super().translate_path(path)).resolve()
            if not target.is_relative_to(directory) or any(part.startswith('.') for part in target.relative_to(directory).parts):return str(directory/'__invalid__')
            return str(target)
        def response(self,value,status=200,cookie=None):
            raw=json.dumps(value,ensure_ascii=False).encode();self.send_response(status)
            self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            if cookie:self.send_header('Set-Cookie',cookie)
            self.end_headers();self.wfile.write(raw)
        def user(self):
            cookies=dict(item.strip().split('=',1) for item in self.headers.get('Cookie','').split(';') if '=' in item)
            token=cookies.get('gym_session','')
            with database.connect() as db:
                row=db.execute('SELECT u.id,u.name,u.email,u.role,s.csrf FROM users u JOIN sessions s ON u.id=s.user_id WHERE s.token=? AND s.expires>?',(hashlib.sha256(token.encode()).hexdigest(),time.time())).fetchone()
            return dict(row) if row else None
        def do_GET(self):
            path=urlparse(self.path).path
            if not path.startswith('/api/'):
                # Backend/database/credentials are never public assets.
                if path.endswith(('.py','.sqlite3','.json','.sql')):self.send_error(403);return
                return super().do_GET()
            user=self.user()
            with database.connect() as db:
                if path=='/api/me':self.response({'user':user});return
                if path=='/api/lessons':
                    self.response([dict(r) for r in db.execute('SELECT l.*,COUNT(b.id) AS booked FROM lessons l LEFT JOIN bookings b ON b.lesson_id=l.id GROUP BY l.id ORDER BY starts_at')]);return
                if not user:self.response({'error':'Accedi prima di continuare.'},401);return
                if path=='/api/bookings':
                    sql='SELECT b.id,b.user_id,b.lesson_id,l.title,l.starts_at,u.name FROM bookings b JOIN lessons l ON l.id=b.lesson_id JOIN users u ON u.id=b.user_id'
                    self.response([dict(r) for r in db.execute(sql+(' ORDER BY l.starts_at' if user['role']=='admin' else ' WHERE b.user_id=? ORDER BY l.starts_at'),() if user['role']=='admin' else (user['id'],))]);return
                if path=='/api/users' and user['role']=='admin':self.response([dict(r) for r in db.execute('SELECT id,name,email,role FROM users ORDER BY id')]);return
            self.response({'error':'Risorsa non disponibile.'},404)
        def do_POST(self):self.mutate('POST')
        def do_DELETE(self):self.mutate('DELETE')
        def do_PATCH(self):self.mutate('PATCH')
        def mutate(self,method):
            try:
                origin=self.headers.get('Origin')
                if origin and origin!=f'http://127.0.0.1:{self.server.server_port}':self.response({'error':'Origine non valida.'},403);return
                length=int(self.headers.get('Content-Length',0))
                if not 0<length<=16384 or self.headers.get('Content-Type','').split(';')[0]!='application/json':raise ValueError('Richiesta JSON non valida.')
                data=json.loads(self.rfile.read(length));path=urlparse(self.path).path
                if not isinstance(data,dict):raise ValueError('Serve un oggetto JSON.')
                if path=='/api/register' and method=='POST':
                    identifier=database.register(data.get('name'),data.get('email'),data.get('password'));self.response({'id':identifier},201);return
                if path=='/api/login' and method=='POST':
                    token,user=database.login(data.get('email'),data.get('password'));self.response({'user':user},cookie='gym_session='+token+'; HttpOnly; SameSite=Strict; Path=/; Max-Age=28800');return
                user=self.user()
                if not user:self.response({'error':'Accesso richiesto.'},401);return
                if not secrets.compare_digest(self.headers.get('X-CSRF-Token',''),user['csrf']):self.response({'error':'Token della sessione non valido.'},403);return
                with database.connect() as db:
                    if path=='/api/logout':
                        db.execute('DELETE FROM sessions WHERE user_id=? AND csrf=?',(user['id'],user['csrf']));db.commit();self.response({'ok':True},cookie='gym_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0');return
                    if path=='/api/lessons' and method=='POST':
                        if user['role']!='admin':self.response({'error':'Permesso amministratore richiesto.'},403);return
                        title=data.get('title','');instructor=data.get('instructor','');starts=data.get('starts_at','');capacity=data.get('capacity',10)
                        if not all(isinstance(v,str) and 1<=len(v)<=100 for v in [title,instructor,starts]) or isinstance(capacity,bool) or not isinstance(capacity,int) or not 1<=capacity<=500:raise ValueError('Dati della lezione non validi.')
                        datetime.fromisoformat(starts)
                        identifier=db.execute('INSERT INTO lessons(title,instructor,starts_at,capacity) VALUES(?,?,?,?)',(title,instructor,starts,capacity)).lastrowid;db.commit();self.response({'id':identifier},201);return
                    if path.startswith('/api/lessons/') and method=='DELETE' and user['role']=='admin':
                        db.execute('DELETE FROM lessons WHERE id=?',(int(path.rsplit('/',1)[-1]),));db.commit();self.response({'ok':True});return
                    if path=='/api/bookings' and method=='POST':
                        lesson=int(data['lesson_id']);member=int(data.get('user_id',user['id']))
                        if member!=user['id'] and user['role']!='admin':self.response({'error':'Permesso negato.'},403);return
                        db.execute('BEGIN IMMEDIATE')
                        row=db.execute('SELECT capacity FROM lessons WHERE id=?',(lesson,)).fetchone()
                        if not row:raise ValueError('Lezione non trovata.')
                        if db.execute('SELECT COUNT(*) FROM bookings WHERE lesson_id=?',(lesson,)).fetchone()[0]>=row['capacity']:raise ValueError('Lezione completa.')
                        identifier=db.execute('INSERT INTO bookings(user_id,lesson_id) VALUES(?,?)',(member,lesson)).lastrowid;db.commit();self.response({'id':identifier},201);return
                    if path.startswith('/api/bookings/') and method=='DELETE':
                        identifier=int(path.rsplit('/',1)[-1]);row=db.execute('SELECT user_id FROM bookings WHERE id=?',(identifier,)).fetchone()
                        if not row or (row['user_id']!=user['id'] and user['role']!='admin'):self.response({'error':'Prenotazione non disponibile.'},403);return
                        db.execute('DELETE FROM bookings WHERE id=?',(identifier,));db.commit();self.response({'ok':True});return
                self.response({'error':'Operazione non disponibile.'},404)
            except (ValueError,KeyError,sqlite3.IntegrityError):self.response({'error':'Dati non validi, duplicati o posti esauriti.'},400)
    return Handler

def main():
    args=argparse.ArgumentParser();args.add_argument('--port',type=int,default=8780);options=args.parse_args()
    root=Path(__file__).resolve().parent
    database=Database(root/'.data')
    server=ThreadingHTTPServer(('127.0.0.1',options.port),handler_for(root,database))
    print(f'http://127.0.0.1:{server.server_port}/index.html',flush=True);server.serve_forever()

if __name__=='__main__':main()
