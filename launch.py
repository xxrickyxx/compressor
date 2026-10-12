"""Avvia solo un ambiente completo, senza fallback silenziosi."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.request
import webbrowser

ROOT=Path(__file__).resolve().parent
VERSION='0.6'

def environment_python():
    override=os.environ.get('COMPRESSOR_PYTHON')
    candidates=[Path(override)] if override else []
    candidates += [ROOT/'.venv/Scripts/python.exe',ROOT/'.venv/bin/python',Path(sys.executable)]
    for python in candidates:
        if not python.is_file(): continue
        probe=subprocess.run([str(python),'-c',"import importlib.util,sys; sys.exit(0 if all(importlib.util.find_spec(n) for n in ('torch','transformers','psutil','safetensors','zstandard')) else 1)"],
                  stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        if probe.returncode==0: return python
    raise RuntimeError('L’ambiente per l’inferenza non è pronto. Apri Configura.cmd nella cartella Compressione, poi riapri Avvia.cmd. Dettagli in setup.log.')

def main():
    runtime=ROOT/'runtime.json'
    try:
        saved=json.loads(runtime.read_text(encoding='utf8'))
        url=saved['url']
        if not url.startswith('http://127.0.0.1:'): raise ValueError('URL non locale')
        with urllib.request.urlopen(url+'health',timeout=2) as response: health=json.load(response)
        if saved.get('version')!=VERSION or health.get('version')!=VERSION: raise ValueError('Versione da aggiornare')
        if not health.get('inference_ready',False): raise RuntimeError('Il servizio già aperto usa un ambiente incompleto. Chiudi quel servizio e apri Configura.cmd, poi Avvia.cmd.')
        webbrowser.open(url); return
    except (OSError,ValueError,KeyError): pass
    python=environment_python()
    with open(ROOT/'server.log','a',encoding='utf8') as log:
        process=subprocess.Popen([str(python),str(ROOT/'server.py')],cwd=ROOT,stdout=log,stderr=log,
            env=dict(os.environ,PYTHONIOENCODING='utf-8'),creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    for _ in range(100):
        if process.poll() is not None: raise RuntimeError('Il servizio non si è avviato. Controlla server.log; la porta 8765 potrebbe essere già occupata.')
        try:
            saved=json.loads(runtime.read_text(encoding='utf8'))
            if saved.get('pid')==process.pid and saved.get('version')==VERSION: return
        except (OSError,ValueError): pass
        time.sleep(.1)
    raise RuntimeError('Il servizio sta impiegando troppo tempo. Controlla server.log.')

if __name__=='__main__':
    try: main()
    except Exception as exc:
        with open(ROOT/'launch-error.log','a',encoding='utf8') as f: f.write(str(exc)+'\n')
        try:
            import tkinter as tk
            from tkinter import messagebox
            root=tk.Tk(); root.withdraw(); messagebox.showerror('Compressione — avvio',str(exc),parent=root); root.destroy()
        except Exception: print(str(exc))
        sys.exit(1)
