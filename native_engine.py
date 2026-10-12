"""Optional llama.cpp adapter. Quantized GGUF inference is separate from CMP."""
import json
import os
from pathlib import Path
import socket
import subprocess
import threading
import time
import urllib.request
import psutil
from context_limits import generation_budget,validate_context

class NativeEngine:
    mode='quant'
    def __init__(self,row,status,stop,context_window=1024):
        init_started=time.perf_counter()
        self.context_window=validate_context(context_window)
        from runtime_support import prepare_runtime,spawn_native
        prepare_runtime()
        from transformers import AutoTokenizer
        self.tokenizer=AutoTokenizer.from_pretrained(row['config_dir'],local_files_only=True)
        self.stop=stop;self.status=status
        sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1];sock.close()
        self.base=f'http://127.0.0.1:{port}'
        log=Path(row['executable']).parent/'native.log';self.log=log.open('ab')
        args=[row['executable'],'-m',row['archive'],'--host','127.0.0.1','--port',str(port),'-c',str(self.context_window),'-t','4','-ngl','0','--parallel','1','--no-webui','--jinja','--chat-template-kwargs','{"enable_thinking":false}']
        try:self.process=spawn_native(args,stdout=self.log,stderr=self.log)
        except OSError as error:
            self.log.close()
            raise RuntimeError('Impossibile avviare llama.cpp: '+str(error)) from error
        self.status('Preparazione motore quantizzato llama.cpp…')
        for _ in range(180):
            if stop.is_set():self.close();raise InterruptedError('Avvio motore annullato.')
            code=self.process.poll()
            if code is not None:
                self.close()
                status_code=code & 0xffffffff
                if status_code==0xc0000135:
                    raise RuntimeError('llama.cpp non trova una DLL del runtime Windows (0xC0000135). Verifica runtime/llama e il Microsoft Visual C++ Redistributable x64. Dettagli in runtime/llama/native.log.')
                if status_code==0xc000007b:
                    raise RuntimeError('llama.cpp ha caricato una DLL di architettura incompatibile (0xC000007B). Servono runtime e DLL x64.')
                raise RuntimeError(f'llama.cpp si è chiuso durante l’avvio (0x{status_code:08X}). Dettagli in runtime/llama/native.log.')
            try:
                with urllib.request.urlopen(self.base+'/health',timeout=1) as response:
                    if response.status==200:
                        self.init_seconds=time.perf_counter()-init_started;return
            except OSError:pass
            time.sleep(.5)
        self.close();raise ValueError('llama.cpp non è pronto. Consulta runtime/llama/native.log.')

    def generate(self,messages,max_tokens=64,on_text=None,context_window=1024):
        context_window=validate_context(context_window)
        prompt_tokens=len(self.tokenizer.apply_chat_template(messages,tokenize=True,add_generation_prompt=True,enable_thinking=False))
        maximum=generation_budget(prompt_tokens,max_tokens,context_window,self.context_window)
        self.status('Generazione con pesi quantizzati…')
        started=time.perf_counter();text='';count=0;finish='length';usage={};done=threading.Event();peak=[0]
        def monitor():
            while not done.wait(.1):
                if self.stop.is_set():
                    self.process.terminate();return
                try:peak[0]=max(peak[0],psutil.Process(self.process.pid).memory_info().rss+psutil.Process().memory_info().rss)
                except psutil.Error:return
        threading.Thread(target=monitor,daemon=True).start()
        request=urllib.request.Request(self.base+'/v1/chat/completions',data=json.dumps({'messages':messages,'max_tokens':maximum,'temperature':0,'stream':True,'stream_options':{'include_usage':True},'chat_template_kwargs':{'enable_thinking':False}}).encode(),headers={'Content-Type':'application/json'})
        try:
            with urllib.request.urlopen(request,timeout=120) as response:
                for line in response:
                    if self.stop.is_set():raise InterruptedError('Generazione annullata.')
                    if not line.startswith(b'data: '):continue
                    raw=line[6:].strip()
                    if raw==b'[DONE]':break
                    data=json.loads(raw)
                    if data.get('usage'):usage=data['usage']
                    for choice in data.get('choices',[]):
                        piece=choice.get('delta',{}).get('content','') or ''
                        text+=piece
                        if piece:count+=1
                        if on_text:on_text(text)
                        if choice.get('finish_reason'):finish=choice['finish_reason']
        except OSError:
            if self.stop.is_set():raise InterruptedError('Generazione annullata.')
            raise
        finally:done.set()
        if self.stop.is_set():raise InterruptedError('Generazione annullata.')
        if self.process.poll() is not None:raise RuntimeError('Motore llama.cpp interrotto; consulta runtime/llama/native.log.')
        count=usage.get('completion_tokens',count);prompt_tokens=usage.get('prompt_tokens',prompt_tokens);elapsed=time.perf_counter()-started
        return {'text':text,'tokens':count,'prompt_tokens':prompt_tokens,'seconds':elapsed,'tokens_s':count/max(elapsed,.001),'finish_reason':finish,'mode':'quant','backend':'llama.cpp','initial_load_seconds':self.init_seconds,'context_window':context_window,'context_used_tokens':prompt_tokens+count,'rss_peak_bytes':peak[0],'context_limited':maximum<max_tokens}

    def close(self):
        if self.process.poll() is None:
            self.process.terminate()
            try:self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:self.process.kill();self.process.wait()
        self.log.close()
