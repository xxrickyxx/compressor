"""Crea/ripara l'ambiente locale e recupera i soli asset del Qwen compresso."""
import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.request
import venv

ROOT=Path(__file__).resolve().parent
REVISION='c1899de289a04d12100db370d81485cdf75e47ca'
ASSETS=('config.json','generation_config.json','tokenizer_config.json','tokenizer.json','vocab.json','merges.txt','LICENSE','README.md')

def restore_assets():
    registry=ROOT/'models.json'
    legacy=ROOT/'prove_modelli/risultati.json'
    if not registry.exists() and not legacy.exists(): return
    rows=json.loads((registry if registry.exists() else legacy).read_text(encoding='utf8'))
    changed=False
    for row in rows:
        repo=row.get('hf_repo')
        if not repo and 'models--Qwen--Qwen3-0.6B' in row.get('source',''): repo='Qwen/Qwen3-0.6B'
        if repo not in ('Qwen/Qwen3-0.6B','Qwen/Qwen3-1.7B','Qwen/Qwen3-4B'): continue
        if not Path(row['archive']).is_file(): continue
        revision=row.get('hf_revision') or (REVISION if repo=='Qwen/Qwen3-0.6B' else 'main')
        folder=ROOT/'models'/repo.split('/')[-1].lower()
        folder.mkdir(parents=True,exist_ok=True)
        for name in ASSETS:
            target=folder/name
            if target.is_file(): continue
            print('Recupero '+name,flush=True)
            url=f'https://huggingface.co/{repo}/resolve/{revision}/{name}'
            with urllib.request.urlopen(url,timeout=120) as response: content=response.read()
            temporary=target.with_suffix(target.suffix+'.download')
            temporary.write_bytes(content); temporary.replace(target)
        row['config_dir']=str(folder)
        row['model_type']='qwen3'
        row['hf_repo']=repo
        row['hf_revision']=revision
        row.setdefault('id',repo.split('/')[-1].lower()+'-cmp')
        row.setdefault('label',repo.split('/')[-1])
        changed=True
    if changed:
        registry.write_text(json.dumps(rows,indent=2,ensure_ascii=False),encoding='utf8')

def main():
    env=ROOT/'.venv'
    python=env/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
    if not python.is_file():
        print('Creazione ambiente dedicato…',flush=True)
        venv.EnvBuilder(with_pip=True).create(env)
    with open(ROOT/'setup.log','a',encoding='utf8') as log:
        commands=[[str(python),'-m','pip','install','torch>=2.6,<3','--index-url','https://download.pytorch.org/whl/cpu'],
                  [str(python),'-m','pip','install','-r',str(ROOT/'requirements.txt')]]
        for command in commands:
            process=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf8',errors='replace')
            for line in process.stdout: print(line,end='',flush=True); log.write(line); log.flush()
            if process.wait(): raise RuntimeError('Installazione non completata. Dettagli in setup.log.')
        restore_assets()
        subprocess.run([str(python),str(ROOT/'runtime_support.py')],check=True)
        subprocess.run([str(python),'-c','import transformers,psutil,safetensors; print("Dipendenze inferenza verificate.")'],check=True)
    print('Configurazione completata. Apri Avvia.cmd.',flush=True)

if __name__=='__main__':
    try: main()
    except Exception as exc:
        print('Configurazione non completata: '+str(exc),flush=True)
        sys.exit(1)
