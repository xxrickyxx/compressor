import json
from pathlib import Path
import subprocess
import sys
import urllib.request
import webbrowser

root=Path(__file__).resolve().parent
runtime=root/'runtime.json'
try:
    url=json.loads(runtime.read_text())['url']
    if not url.startswith('http://127.0.0.1:'): raise ValueError('URL non locale')
    with urllib.request.urlopen(url,timeout=2) as response:
        if response.status!=200: raise ValueError('Server non disponibile')
    if json.loads(runtime.read_text()).get('version')!='0.3':
        raise ValueError('Avvio della versione aggiornata')
    webbrowser.open(url)
except Exception:
    python=Path.home()/'Desktop/matrix_ia/.venv/Scripts/python.exe'
    if not python.exists(): python=Path(sys.executable)
    with open(root/'server.log','a',encoding='utf8') as log:
        env=dict(__import__('os').environ,PYTHONIOENCODING='utf-8')
        subprocess.Popen([str(python),str(root/'server.py')],cwd=root,stdout=log,stderr=log,env=env,
                         creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
