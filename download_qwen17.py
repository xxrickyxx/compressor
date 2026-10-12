"""Scarica il checkpoint ufficiale, comprime senza perdita e registra Qwen3-1.7B."""
import json
import os
import hashlib
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import time
from huggingface_hub import HfApi,snapshot_download
import requests
from compressione import compress,Archive

def download_weights(repo,revision,file,folder):
    target=folder/file.rfilename
    expected_hash=file.lfs.sha256 if file.lfs else None
    def digest(path):
        h=hashlib.sha256()
        with path.open('rb') as stream:
            while chunk:=stream.read(4*1024*1024): h.update(chunk)
        return h.hexdigest()
    if target.exists() and target.stat().st_size==file.size:
        if not expected_hash or digest(target)==expected_hash: return
        raise ValueError('Il file già presente non corrisponde al checkpoint ufficiale.')
    temporary=target.with_suffix(target.suffix+'.download')
    with temporary.open('wb') as stream: stream.truncate(file.size)
    chunk_size=16*1024*1024
    ranges=[(start,min(file.size-1,start+chunk_size-1)) for start in range(0,file.size,chunk_size)]
    lock=threading.Lock(); completed=[0]; last=[-1]
    url=f'https://huggingface.co/{repo}/resolve/{revision}/{file.rfilename}'
    def fetch(part):
        start,end=part
        for attempt in range(3):
            try:
                with requests.get(url,headers={'Range':f'bytes={start}-{end}','Accept-Encoding':'identity'},stream=True,timeout=(30,90)) as response:
                    response.raise_for_status()
                    if response.status_code!=206 or response.headers.get('Content-Range')!=f'bytes {start}-{end}/{file.size}':
                        raise ValueError('Il server non ha restituito l’intervallo richiesto.')
                    written=0
                    with temporary.open('r+b') as stream:
                        stream.seek(start)
                        for data in response.iter_content(256*1024):
                            if written+len(data)>end-start+1: raise ValueError('Intervallo troppo lungo.')
                            stream.write(data); written+=len(data)
                    if written!=end-start+1: raise ValueError('Intervallo incompleto.')
                break
            except (requests.RequestException,ValueError):
                if attempt==2: raise
                time.sleep(attempt+1)
        with lock:
            completed[0]+=written
            percentage=int(100*completed[0]/file.size)
            if percentage//5!=last[0]:
                last[0]=percentage//5
                print(f'Download {file.rfilename}: {percentage}%',flush=True)
    with ThreadPoolExecutor(max_workers=8) as pool: list(pool.map(fetch,ranges))
    if expected_hash and digest(temporary)!=expected_hash: raise ValueError('SHA-256 del download non valido.')
    temporary.replace(target)

def main(size="1.7",codec="zlib"):
    tag="qwen3-"+size+"b"
    root=Path(__file__).resolve().parent
    repo='Qwen/Qwen3-'+size+'B'
    folder=root/'models'/tag
    archive=root/'prove_modelli'/(tag+'.cmpmodel.json')
    info=HfApi().model_info(repo,files_metadata=True)
    weights=[f.rfilename for f in info.siblings if f.rfilename.endswith('.safetensors')]
    names=['config.json','generation_config.json','tokenizer_config.json','tokenizer.json','vocab.json','merges.txt','LICENSE','README.md','model.safetensors.index.json']+weights
    print(json.dumps({'repo':repo,'revision':info.sha,'weight_files':[{ 'name':f.rfilename,'bytes':f.size} for f in info.siblings if f.rfilename.endswith('.safetensors')]}),flush=True)
    if not weights: raise ValueError('Il checkpoint non contiene safetensors.')
    folder.mkdir(parents=True,exist_ok=True)
    snapshot_download(repo_id=repo,revision=info.sha,local_dir=folder,allow_patterns=[name for name in names if not name.endswith('.safetensors')],max_workers=2)
    for file in info.siblings:
        if file.rfilename in weights: download_weights(repo,info.sha,file,folder)
    print('Download completato. Compressione…',flush=True)
    started=time.perf_counter()
    original_size=0; compressed_size=0; shards={}; checksums={}
    for weight_name in weights:
        source=folder/weight_name
        target=archive.parent/(tag+'-'+codec+'-'+weight_name+'.cmp')
        last=[-1]
        def progress(done):
            percentage=int(100*done/source.stat().st_size)
            if percentage//10!=last[0]:
                last[0]=percentage//10
                print(f'{weight_name}: {percentage}%',flush=True)
        if target.exists():
            parsed=Archive(target); parsed.verify(); meta=parsed.meta
        else:
            meta=compress(source,target,progress=progress,codec=codec)
            Archive(target).verify()
        expected=next(f.lfs.sha256 for f in info.siblings if f.rfilename==weight_name and f.lfs)
        if meta['sha256']!=expected: raise ValueError('Archivio diverso dal checkpoint ufficiale.')
        original_size+=meta['size']; compressed_size+=target.stat().st_size
        shards[weight_name]=target.name; checksums[weight_name]=meta['sha256']
    index=json.loads((folder/'model.safetensors.index.json').read_text(encoding='utf8'))
    manifest={'format':'cmp-sharded-v1','shards':shards,'weight_map':index['weight_map']}
    archive.write_text(json.dumps(manifest,indent=2),encoding='utf8')
    packed_total=compressed_size+archive.stat().st_size
    registry=root/'models.json'
    rows=json.loads(registry.read_text(encoding='utf8')) if registry.exists() else []
    rows=[r for r in rows if r.get('id')!=tag+'-cmp']
    rows.append({'id':tag+'-cmp','label':'Qwen3 · '+size+'B','model_type':'qwen3',
        'source':str(folder/'model.safetensors.index.json'),'config_dir':str(folder),'archive':str(archive),
        'original_bytes':original_size,'compressed_bytes':packed_total,'saving_percent':100*(1-packed_total/original_size),
        'integrity':'OK','hf_repo':repo,'hf_revision':info.sha})
    registry.write_text(json.dumps(rows,indent=2,ensure_ascii=False),encoding='utf8')
    result={'repo':repo,'revision':info.sha,'original_bytes':original_size,'compressed_bytes':packed_total,
            'saving_percent':100*(1-packed_total/original_size),'compression_and_verify_seconds':time.perf_counter()-started,'sha256':checksums}
    (root/'prove_modelli'/(tag+'_compression.json')).write_text(json.dumps(result,indent=2),encoding='utf8')
    print(json.dumps(result),flush=True)

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('--size',choices=['1.7','4'],default='1.7')
    parser.add_argument('--codec',choices=['zlib','zstd'],default='zlib')
    options=parser.parse_args()
    main(options.size,options.codec)
