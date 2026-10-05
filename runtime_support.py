"""Prepara le dipendenze native prima di importare Torch su Windows."""
import ctypes
import os
from pathlib import Path
import sys

HANDLES=[]
LIBRARIES=[]
READY=False

def prepare_runtime():
    global READY
    if READY or os.name!='nt': return
    root=Path(__file__).resolve().parent
    bundled=Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies'
    paths=[root/'runtime/windows',Path(sys.base_prefix),bundled/'python',
           bundled/'native/jxrlib/jxrlib/bin',bundled/'native/poppler/Library/bin']
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
