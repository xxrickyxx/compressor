"""Prepara le dipendenze native prima di importare Torch su Windows."""
import ctypes
import os
from pathlib import Path
import sys
import subprocess
import threading

HANDLES=[]
LIBRARIES=[]
READY=False
SPAWN_LOCK=threading.Lock()

def runtime_paths():
    root=Path(__file__).resolve().parent
    bundled=Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies'
    return [root/'runtime/windows',Path(sys.base_prefix),bundled/'python',
            bundled/'native/jxrlib/jxrlib/bin',bundled/'native/poppler/Library/bin']

def native_environment(executable, environment=None):
    """Add trusted DLL paths to the child; AddDllDirectory is process-local."""
    env=dict(os.environ if environment is None else environment)
    if os.name!='nt':return env
    folders=[Path(executable).resolve().parent]+runtime_paths()
    paths=[str(path.resolve()) for path in folders if path.is_dir()]
    paths.extend(part for part in env.get('PATH','').split(os.pathsep) if part)
    seen=set(); unique=[]
    for path in paths:
        key=os.path.normcase(path)
        if key not in seen:seen.add(key);unique.append(path)
    env['PATH']=os.pathsep.join(unique)
    return env

def spawn_native(args, **kwargs):
    """Use the runtime folder and prevent loader errors from blocking in a dialog."""
    kwargs.setdefault('cwd',str(Path(args[0]).resolve().parent))
    kwargs['env']=native_environment(args[0],kwargs.get('env'))
    kwargs.setdefault('creationflags',getattr(subprocess,'CREATE_NO_WINDOW',0))
    if os.name!='nt':return subprocess.Popen(args,**kwargs)
    with SPAWN_LOCK:
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        previous=kernel.GetErrorMode()
        kernel.SetErrorMode(previous|0x0001|0x0002|0x8000)
        try:return subprocess.Popen(args,**kwargs)
        finally:kernel.SetErrorMode(previous)

def prepare_runtime():
    global READY
    if READY or os.name!='nt': return
    paths=runtime_paths()
    for path in paths:
        if path.is_dir(): HANDLES.append(os.add_dll_directory(str(path)))
    for name in ('vcruntime140.dll','vcruntime140_1.dll','msvcp140.dll'):
        candidates=[path/name for path in paths if (path/name).is_file()]
        loaded=False
        for path in candidates:
            try:
                LIBRARIES.append(ctypes.WinDLL(str(path))); loaded=True; break
            except OSError: continue
        if not loaded:
            try: LIBRARIES.append(ctypes.WinDLL(name))
            except OSError as exc:
                raise RuntimeError(f'Dipendenza Windows mancante: {name}. Installa il Microsoft Visual C++ Redistributable x64 ufficiale, poi riavvia Compressione.') from exc
    READY=True

def import_torch():
    prepare_runtime()
    import torch
    return torch

if __name__=='__main__':
    torch=import_torch()
    print(f'Torch {torch.__version__}: librerie native caricate correttamente.')
