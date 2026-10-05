from pathlib import Path
import tempfile
import time
import tkinter as tk
from interfaccia import App

with tempfile.TemporaryDirectory() as tmp:
    src, arc, dst = [Path(tmp)/name for name in ('originale.bin','archivio.cmp','ricostruito.bin')]
    src.write_bytes(b'prova interfaccia\x00'*100000)
    root = tk.Tk()
    root.withdraw()
    app = App(root)
    def run(mode, source, target=''):
        app.mode.set(mode); app.source.set(str(source)); app.target.set(str(target))
        app.start()
        deadline=time.monotonic()+20
        while app.busy and time.monotonic()<deadline:
            root.update(); time.sleep(0.01)
        assert not app.busy, 'Timeout interfaccia'
        assert app.status.get()=='Completato.', app.log.get('1.0','end')
    run('Comprimi',src,arc)
    run('Verifica',arc)
    run('Ricostruisci',arc,dst)
    assert src.read_bytes()==dst.read_bytes()
    root.destroy()
print('Interfaccia: compressione, verifica e ricostruzione completate.')
