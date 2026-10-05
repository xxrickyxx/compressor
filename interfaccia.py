"""Interfaccia grafica locale per Compressione."""
import os
from pathlib import Path
import queue
import threading
import time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from compressione import compress, decompress, Archive

class App:
    def __init__(self, root):
        self.root = root
        self.events = queue.Queue()
        self.cancel = threading.Event()
        self.busy = False
        root.title('Compressione — modelli e file')
        root.geometry('850x600')
        root.minsize(700, 500)
        style = ttk.Style(root)
        style.theme_use('clam')
        style.configure('TButton', padding=9)
        frame = ttk.Frame(root, padding=24)
        frame.pack(fill='both', expand=True)
        ttk.Label(frame, text='Compressione', font=('Segoe UI', 24, 'bold')).pack(anchor='w')
        ttk.Label(frame, text='Archivi senza perdita • lettura a blocchi • verifica di integrità').pack(anchor='w', pady=(0,20))
        self.source = tk.StringVar()
        self.target = tk.StringVar()
        self.mode = tk.StringVar(value='Comprimi')
        self.status = tk.StringVar(value='Scegli un file per iniziare.')
        ttk.Label(frame, text='Operazione').pack(anchor='w')
        self.combo = ttk.Combobox(frame, textvariable=self.mode, values=['Comprimi','Ricostruisci','Verifica'], state='readonly')
        self.combo.pack(anchor='w', pady=(4,12))
        self.combo.bind('<<ComboboxSelected>>', lambda e: self.suggest())
        self.entries = []
        self.buttons = []
        for label, variable, browse in [('File di origine',self.source,self.pick_source), ('File di destinazione',self.target,self.pick_target)]:
            ttk.Label(frame,text=label).pack(anchor='w')
            row = ttk.Frame(frame); row.pack(fill='x',pady=(4,12))
            entry = ttk.Entry(row,textvariable=variable); entry.pack(side='left',fill='x',expand=True)
            button = ttk.Button(row,text='Sfoglia…',command=browse); button.pack(side='right',padx=(8,0))
            self.entries.append(entry); self.buttons.append(button)
        actions = ttk.Frame(frame); actions.pack(fill='x',pady=6)
        self.go = ttk.Button(actions,text='Avvia',command=self.start); self.go.pack(side='left')
        self.stop = ttk.Button(actions,text='Annulla',command=self.cancel.set,state='disabled'); self.stop.pack(side='left',padx=8)
        ttk.Button(actions,text='Apri risultati delle prove',command=self.open_results).pack(side='right')
        self.bar = ttk.Progressbar(frame,maximum=100); self.bar.pack(fill='x',pady=(14,8))
        ttk.Label(frame,textvariable=self.status,wraplength=780).pack(anchor='w')
        self.log = tk.Text(frame,height=9,wrap='word',font=('Segoe UI',10),state='disabled')
        self.log.pack(fill='both',expand=True,pady=(14,0))
        ttk.Label(frame,text='Il risparmio dipende dal file. L’archivio va ricostruito prima di usarlo nei programmi attuali.',wraplength=780).pack(anchor='w',pady=(10,0))
        root.protocol('WM_DELETE_WINDOW',self.close)
        root.after(100,self.poll)

    def suggest(self):
        src = self.source.get().strip().strip('"')
        self.target.set(src+'.cmp' if self.mode.get()=='Comprimi' else src+'.ripristinato' if self.mode.get()=='Ricostruisci' else '')

    def pick_source(self):
        value = filedialog.askopenfilename(initialdir=str(Path.home()/'Desktop'),title='Scegli il modello o l’archivio')
        if value: self.source.set(value); self.suggest()

    def pick_target(self):
        value = filedialog.asksaveasfilename(initialfile=Path(self.target.get()).name,title='Scegli il nuovo file')
        if value: self.target.set(value)

    def open_results(self):
        folder = Path(__file__).parent/'prove_modelli'
        if folder.exists(): os.startfile(folder)
        else: messagebox.showinfo('Risultati','Non ci sono ancora prove salvate.')

    def start(self):
        if self.busy: return
        src = self.source.get().strip().strip('"')
        dst = self.target.get().strip().strip('"')
        mode = self.mode.get()
        if not Path(src).is_file(): messagebox.showerror('File','Scegli un file di origine valido.'); return
        if mode != 'Verifica' and (not dst or Path(dst).exists()):
            messagebox.showerror('Destinazione','Scegli un nuovo file di destinazione.'); return
        self.busy = True; self.cancel.clear(); self.bar['value'] = 0
        self.go.configure(state='disabled'); self.stop.configure(state='normal'); self.combo.configure(state='disabled')
        for widget in self.entries+self.buttons: widget.configure(state='disabled')
        self.status.set('Operazione in corso…')
        threading.Thread(target=self.work,args=(mode,src,dst),daemon=True).start()

    def work(self,mode,src,dst):
        start = time.perf_counter()
        try:
            total = Path(src).stat().st_size if mode=='Comprimi' else Archive(src).meta['size']
            def progress(done):
                if self.cancel.is_set(): raise ValueError('Operazione annullata.')
                self.events.put(('progress',100*done/max(total,1)))
            if mode=='Comprimi':
                m = compress(src,dst,progress=progress)
                self.events.put(('status','Compressione completata. Verifica dell’archivio…'))
                Archive(dst).verify(progress=progress)
                size = Path(dst).stat().st_size
                result = f'Archivio: {dst}\nOriginale: {total/1e6:.2f} MB → archivio: {size/1e6:.2f} MB\nRisparmio: {100*(1-size/total):.2f}%' if total else f'Archivio vuoto creato: {dst}'
            elif mode=='Ricostruisci':
                decompress(src,dst,progress=progress); result = f'File ricostruito: {dst}'
            else:
                Archive(src).verify(progress=progress); result = f'Archivio verificato: {src}'
            self.events.put(('done',f'{result}\nIntegrità SHA-256 corretta. Tempo totale: {time.perf_counter()-start:.1f} s'))
        except Exception as exc:
            self.events.put(('error',str(exc)))

    def poll(self):
        try:
            for _ in range(200):
                kind,value = self.events.get_nowait()
                if kind=='progress': self.bar['value']=value
                elif kind=='status': self.status.set(value)
                else:
                    self.busy=False; self.go.configure(state='normal'); self.stop.configure(state='disabled'); self.combo.configure(state='readonly')
                    for widget in self.entries+self.buttons: widget.configure(state='normal')
                    self.status.set('Completato.' if kind=='done' else 'Operazione interrotta o non completata.')
                    self.log.configure(state='normal'); self.log.insert('end',value+'\n\n'); self.log.see('end'); self.log.configure(state='disabled')
                    if kind=='done': self.bar['value']=100
        except queue.Empty: pass
        self.root.after(100,self.poll)

    def close(self):
        if self.busy:
            self.cancel.set(); self.status.set('Attendi l’annullamento prima di chiudere.')
        else: self.root.destroy()

if __name__=='__main__':
    root=tk.Tk(); App(root); root.mainloop()
