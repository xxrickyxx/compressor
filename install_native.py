"""Optional official llama.cpp CPU runtime + official Qwen GGUF, pinned checksums."""
import hashlib
import json
from pathlib import Path
import zipfile
import requests
from huggingface_hub import HfApi,snapshot_download
from download_qwen17 import download_weights

def main():
    root=Path(__file__).parent; runtime=root/'runtime/llama'; runtime.mkdir(parents=True,exist_ok=True)
    release=requests.get('https://api.github.com/repos/ggml-org/llama.cpp/releases/tags/b11573',timeout=30);release.raise_for_status(); release=release.json()
    asset=next(a for a in release['assets'] if a['name'].endswith('bin-win-cpu-x64.zip'))
    response=requests.get(asset['browser_download_url'],timeout=120);response.raise_for_status()
    digest=hashlib.sha256(response.content).hexdigest()
    if asset.get('digest') and asset['digest']!='sha256:'+digest: raise ValueError('Runtime checksum mismatch')
    archive=runtime/'runtime.zip';archive.write_bytes(response.content)
    with zipfile.ZipFile(archive) as zipped:
        for member in zipped.infolist():
            if not (runtime/member.filename).resolve().is_relative_to(runtime.resolve()):raise ValueError('Invalid archive path')
        zipped.extractall(runtime)
    repo='Qwen/Qwen3-4B-GGUF'; info=HfApi().model_info(repo,files_metadata=True)
    file=next(f for f in info.siblings if f.rfilename.lower().endswith('q4_k_m.gguf'))
    folder=root/'models/qwen3-4b-gguf';folder.mkdir(parents=True,exist_ok=True)
    print(json.dumps({'repo':repo,'revision':info.sha,'file':file.rfilename,'bytes':file.size,'runtime':release['tag_name']}),flush=True)
    download_weights(repo,info.sha,file,folder)
    executable=next(runtime.rglob('llama-server.exe'))
    assets=root/'models/qwen3-4b'
    snapshot_download(repo_id='Qwen/Qwen3-4B',revision='1cfa9a7208912126459214e8b04321603b3df60c',local_dir=assets,allow_patterns=['config.json','generation_config.json','tokenizer_config.json','tokenizer.json','vocab.json','merges.txt','LICENSE','README.md'],max_workers=2)
    registry=root/'models.json'; rows=json.loads(registry.read_text(encoding='utf8')) if registry.exists() else []
    rows=[r for r in rows if r.get('id')!='qwen3-4b-q4-native']
    rows.append({'id':'qwen3-4b-q4-native','label':'Qwen3 · 4B Q4 · llama.cpp','backend':'llama.cpp','model_type':'qwen3',
        'source':str(folder/file.rfilename),'archive':str(folder/file.rfilename),'config_dir':str(root/'models/qwen3-4b'),
        'original_bytes':file.size,'compressed_bytes':file.size,'saving_percent':0,'integrity':'LFS SHA-256 verified',
        'executable':str(executable),'hf_repo':repo,'hf_revision':info.sha,'quantization':'Q4_K_M',
        'runtime_release':release['tag_name'],'runtime_sha256':digest})
    registry.write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf8')
    print('Native runtime and quantized model ready',flush=True)

if __name__=='__main__':main()
