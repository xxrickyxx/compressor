"""Resumable static-file agent with explicit completion checks and finite budgets."""
import json
import re
import time
import uuid
import shutil
import subprocess
import os
import ast
from html import escape
from pathlib import Path, PurePosixPath
from html.parser import HTMLParser
from urllib.parse import urlsplit, unquote

ALLOWED={'.html','.css','.js','.json','.md','.svg','.txt','.py','.sql'}

def safe_path(root, name):
    if not isinstance(name,str) or not name or '\\' in name or ':' in name:
        raise ValueError('Nome file non valido.')
    relative=PurePosixPath(name)
    if relative.is_absolute() or any(p in ('..','.') for p in name.split('/')) or relative.suffix not in ALLOWED:
        raise ValueError('Il file deve restare nel progetto ed essere HTML, CSS, JS, JSON, Markdown, SVG o testo.')
    root=Path(root).resolve(); target=(root/name).resolve()
    if not target.is_relative_to(root): raise ValueError('Percorso fuori dal progetto.')
    return target

class References(HTMLParser):
    def __init__(self): super().__init__(); self.refs=[]
    def handle_starttag(self, tag, attrs):
        self.refs.extend(value for key,value in attrs if key in ('href','src') and value)

def clean_file(text, name):
    text=text.strip()
    headers=list(re.finditer(r'(?m)^(?:#{1,3}\s*)?([\w./ -]+\.(?:html|css|js|json|md|svg|txt))\s*$',text))
    matched=False
    for index,header in enumerate(headers):
        if header.group(1).strip()==name:
            text=text[header.end():headers[index+1].start() if index+1<len(headers) else len(text)].strip()
            matched=True
            break
    if headers and not matched: text=text[:headers[0].start()].strip()
    if text.split('\n',1)[0].strip()==name: text=text.split('\n',1)[1] if '\n' in text else ''
    text=re.sub(r'^```[^\n]*\n','',text)
    text=re.sub(r'\n```\s*$','',text)
    return text+'\n'

def connect_pages(root, files):
    """Deterministic scaffold repair: wire generated pages and shared assets."""
    repaired=[]
    for name in files:
        if not name.endswith('.html'): continue
        target=safe_path(root,name)
        if not target.is_file(): continue
        text=target.read_text(encoding='utf8'); parser=References(); parser.feed(text)
        destinations=set()
        for ref in parser.refs:
            url=urlsplit(ref)
            if not url.scheme and not url.netloc:
                destinations.add((Path(root)/unquote(url.path.lstrip('/')) if url.path.startswith('/') else target.parent/unquote(url.path)).resolve())
        missing=[]; assets=[]
        for other in files:
            dest=safe_path(root,other)
            if dest in destinations or other==name: continue
            relative=escape(os.path.relpath(dest,target.parent).replace('\\','/'),quote=True)
            if other.endswith('.html'): missing.append('<a href="'+relative+'">'+escape(Path(other).stem.title())+'</a>')
            if other.endswith('.css'): assets.append('<link rel="stylesheet" href="'+relative+'">')
            if other.endswith('.js'): assets.append('<script src="'+relative+'" defer></script>')
        if missing and re.search(r'<body\b[^>]*>',text,re.I):
            if re.search(r'</nav>',text,re.I):text=re.sub(r'</nav>',lambda m:' '+' '.join(missing)+m.group(0),text,count=1,flags=re.I)
            else:text=re.sub(r'(<body\b[^>]*>)',lambda m:m.group(1)+'\n<nav aria-label="Pages">'+' '.join(missing)+'</nav>',text,count=1,flags=re.I)
        text=re.sub(r'<nav aria-label="Pages">(.*?)</nav>\s*<nav>(.*?)</nav>',lambda m:'<nav>'+m.group(2)+' '+m.group(1)+'</nav>',text,flags=re.I|re.S)
        if assets and re.search(r'</head>',text,re.I):
            text=re.sub(r'</head>',lambda m:'\n'.join(assets)+'\n'+m.group(0),text,count=1,flags=re.I)
        original=target.read_text(encoding='utf8')
        if text!=original: target.write_text(text,encoding='utf8'); repaired.append(name)
    return repaired

def validate_site(root, files):
    problems=[]
    for name in files:
        target=safe_path(root,name)
        if not target.is_file() or not target.stat().st_size:
            problems.append('Missing or empty: '+name); continue
        text=target.read_text(encoding='utf8')
        if '```' in text: problems.append('Markdown fences in source: '+name)
        if name.endswith('.html'):
            if not re.search(r'</html>\s*$',text,re.I) or not all(re.search(tag,text,re.I) for tag in (r'<html\b',r'<body\b',r'</body>')): problems.append('Incomplete HTML: '+name)
            parser=References(); parser.feed(text)
            for page in files:
                if page.endswith('.html') and page!=name:
                    destination=safe_path(root,page)
                    links=[(target.parent/unquote(urlsplit(ref).path)).resolve() for ref in parser.refs if not urlsplit(ref).scheme and not ref.startswith('/')]
                    if destination not in links: problems.append('Missing page link: '+name+' -> '+page)
            for ref in parser.refs:
                url=urlsplit(ref)
                if url.scheme or url.netloc or not url.path: continue
                if url.path.startswith('/'): dest=(Path(root)/unquote(url.path.lstrip('/'))).resolve()
                else: dest=(target.parent/unquote(url.path)).resolve()
                if not dest.is_relative_to(Path(root).resolve()) or not dest.is_file(): problems.append('Broken reference: '+name+' -> '+ref)
        if name.endswith('.json'):
            try: json.loads(text)
            except ValueError: problems.append('Invalid JSON: '+name)
        if name.endswith('.py'):
            try:ast.parse(text)
            except SyntaxError:problems.append('Invalid Python syntax: '+name)
        if name.endswith('.js') and shutil.which('node'):
            checked=subprocess.run([shutil.which('node'),'--check',str(target)],capture_output=True,text=True,timeout=15)
            if checked.returncode: problems.append('Invalid JavaScript syntax: '+name)
    return list(dict.fromkeys(problems))

class TaskLoop:
    def __init__(self, root): self.root=Path(root)
    def save(self, task):
        path=self.root/task['id']/'task.json'; path.parent.mkdir(parents=True,exist_ok=True)
        tmp=path.with_suffix('.tmp'); tmp.write_text(json.dumps(task,ensure_ascii=False,indent=2),encoding='utf8'); tmp.replace(path)
    def load(self, task_id):
        if not re.fullmatch('[a-f0-9]{32}',str(task_id)): raise ValueError('Task non valido.')
        task=json.loads((self.root/task_id/'task.json').read_text(encoding='utf8'))
        expected=(self.root/task_id/'site').resolve()
        if task.get('id')!=task_id or Path(task['output']).resolve()!=expected or not expected.is_relative_to(self.root.resolve()):raise ValueError('Checkpoint con percorso non valido.')
        return task
    def list(self):
        if not self.root.exists(): return []
        return [{k:t.get(k) for k in ('id','goal','status','steps','output','problems','project_kind','backend_checks')} for p in sorted(self.root.glob('*/task.json'),key=lambda p:p.stat().st_mtime,reverse=True)[:50] for t in [json.loads(p.read_text(encoding='utf8'))]]
    def create(self, goal, files, project_kind=None):
        if not isinstance(goal,str) or not goal.strip() or len(goal)>8000: raise ValueError('Descrivi il progetto (massimo 8.000 caratteri).')
        if not isinstance(files,list) or not 1<=len(files)<=20 or len(set(files))!=len(files): raise ValueError('Indica da 1 a 20 file diversi.')
        task_id=uuid.uuid4().hex; output=self.root/task_id/'site'
        for name in files: safe_path(output,name)
        if project_kind is None: project_kind='gym' if re.search(r'palestr|gym|fitness',goal,re.I) and re.search(r'backend|gestional|utent|user|booking|prenot',goal,re.I) else 'static'
        if project_kind not in ('static','gym'):raise ValueError('Tipo progetto non supportato.')
        task={'id':task_id,'goal':goal,'files':files,'output':str(output),'status':'ready','steps':0,'tokens':0,'done':[],'pending':'','problems':[],'log':[],'project_kind':project_kind}
        self.save(task); return task
    def run(self, task, generate, stop, update, steps=12, total_tokens=12000):
        steps=int(steps); total_tokens=int(total_tokens)
        if not 1<=steps<=60 or not 128<=total_tokens<=64000: raise ValueError('Budget non valido: 1–60 passaggi, 128–64.000 token.')
        task['status']='running'; self.save(task)
        used=0
        tool_feedback=task.get('last_tool_result','')
        try:
            if stop.is_set():raise InterruptedError('Task sospeso; puoi riprenderlo.')
            from project_tools import ProjectTools
            tools=ProjectTools(task['output'])
            if not task.get('project_kind'):
                task['project_kind']='gym' if re.search(r'palestr|gym|fitness',task['goal'],re.I) and re.search(r'backend|gestional|utent|user|prenot',task['goal'],re.I) else 'static'
            if task.get('project_kind')=='gym':tools.scaffold_backend(task)
            def check_project():
                problems=validate_site(task['output'],task['files'])
                if not problems and task.get('project_kind')=='gym':
                    update(phase='Verifica database e API del backend…')
                    task['backend_checks']=tools.test_backend()
                    if stop.is_set():raise InterruptedError('Task sospeso; puoi riprenderlo.')
                    task.setdefault('tool_log',[]).append({'tool':'test_backend','passed':task['backend_checks']['passed']})
                    if not task['backend_checks']['passed']:problems.append('Backend API checks failed')
                return problems
            # Reconcile existing checkpoint files before asking the model to rewrite.
            for name in task['files']:
                target=safe_path(task['output'],name)
                if target.is_file(): target.write_text(clean_file(target.read_text(encoding='utf8'),name),encoding='utf8')
            repaired=connect_pages(task['output'],task['files'])
            if repaired: task['log'].append({'scaffold_repaired':repaired,'time':time.time()})
            if not check_project():
                task.update(done=list(task['files']),pending='',problems=[],status='completed')
                return task
            while used<steps and task['tokens']<total_tokens:
                if stop.is_set(): raise InterruptedError('Task sospeso; puoi riprenderlo.')
                remaining=[f for f in task['files'] if f not in task['done']]
                if not remaining:
                    for name in task['files']:
                        target=safe_path(task['output'],name)
                        if target.is_file():
                            text=target.read_text(encoding='utf8')
                            normalized=clean_file(text,name)
                            if normalized!=text: target.write_text(normalized,encoding='utf8')
                    repaired=connect_pages(task['output'],task['files'])
                    if repaired: task['log'].append({'scaffold_repaired':repaired,'time':time.time()})
                    task['problems']=check_project()
                    if not task['problems']: task['status']='completed'; break
                    # Rewrite the source file with a broken reference or invalid structure.
                    bad=next((f for f in task['files'] if any(p.partition(': ')[2].split(' -> ')[0]==f for p in task['problems'])),task['files'][0])
                    task['done'].remove(bad); remaining=[bad]; task['pending']=''
                name=remaining[0]
                instruction='Create a complete website. Output only the exact file content, no explanation and no markdown fences. Use relative links. All pages must link to the other HTML pages.\nGoal: '+task['goal']+'\nProject files: '+', '.join(task['files'])+'\nCurrent file: '+name
                instruction+='\nOptional tools: list_files, read_file(path), replace_text(path,old,new), write_file(path,content), check_project, test_backend. To call a tool output ONLY a JSON object with tool and its arguments. Files must belong to this project. Otherwise output the current file content.'
                if tool_feedback: instruction+='\nLast tool result: '+tool_feedback[-4000:]
                if task['problems']: instruction+='\nFix: '+'; '.join(task['problems'])
                if task['pending']:
                    instruction+='\nContinue the file from the exact last character below. Do not repeat any earlier characters. Prefix already saved:\n'+task['pending'][-5000:]
                instruction+='\nIMPORTANT: This turn outputs ONLY '+name+'. Do not output the other project files.'
                update(phase='Task: '+name,progress=100*len(task['done'])/len(task['files']),answer='',task_id=task['id'])
                result=generate([{'role':'user','content':instruction}],min(1024,total_tokens-task['tokens']))
                piece=result['text']
                if not task['pending'] and result['finish_reason']=='stop':
                    try: call=json.loads(piece)
                    except ValueError: call=None
                    if isinstance(call,dict) and call.get('tool'):
                        try:
                            command=call['tool'];path=call.get('path')
                            if command in ('read_file','write_file','replace_text') and path not in task['files']: raise ValueError('Tool: file fuori dal manifesto del progetto.')
                            if command=='list_files': value=tools.list_files()
                            elif command=='read_file': value=tools.read_file(path)
                            elif command=='write_file':
                                tools.write_file(path,call['content']);value='File saved'
                                if path not in task['done']:task['done'].append(path)
                            elif command=='replace_text': tools.replace_text(path,call['old'],call['new']);value='Replacement applied'
                            elif command=='check_project': value=check_project()
                            elif command=='test_backend' and task.get('project_kind')=='gym':value=tools.test_backend()
                            else:raise ValueError('Tool non supportato.')
                        except (ValueError,KeyError,OSError) as error:value={'error':str(error)}
                        tool_feedback=json.dumps(value,ensure_ascii=False);task['last_tool_result']=tool_feedback;task['tokens']+=result['tokens'];task['steps']+=1;used+=1
                        task.setdefault('tool_log',[]).append({'tool':command,'path':path});self.save(task);continue
                if not task['pending']: piece=re.sub(r'^\s*```[^\n]*\n','',piece)
                piece=re.sub(r'\n```\s*$','',piece)
                task['pending']+=piece; task['tokens']+=result['tokens']; task['steps']+=1; used+=1
                task['log'].append({'file':name,'tokens':result['tokens'],'finish_reason':result['finish_reason'],'time':time.time()})
                if len(task['pending'])>500000: raise ValueError('Il file supera il limite di 500 KB.')
                if result['finish_reason']=='stop' and task['pending'].strip():
                    target=safe_path(task['output'],name); target.parent.mkdir(parents=True,exist_ok=True)
                    target.write_text(clean_file(task['pending'],name),encoding='utf8'); task['done'].append(name); task['pending']=''
                if not piece.strip(): task['status']='needs_attention'; break
                self.save(task)
            if task['status']=='running':
                task['problems']=check_project()
                task['status']='completed' if len(task['done'])==len(task['files']) and not task['problems'] else 'paused_budget'
        except Exception:
            task['status']='paused'; raise
        finally: self.save(task)
        return task
