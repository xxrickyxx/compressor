import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import urllib.request
import urllib.error
from http.server import ThreadingHTTPServer
import server

class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        server.API_KEY='test-key-for-tests-only-0123456789'
        cls.http=ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
        cls.url=f'http://127.0.0.1:{cls.http.server_port}'
        threading.Thread(target=cls.http.serve_forever,daemon=True).start()
    @classmethod
    def tearDownClass(cls): cls.http.shutdown(); cls.http.server_close()
    def request(self,path,data=None,key=True):
        headers={'Content-Type':'application/json'}
        if key: headers['Authorization']='Bearer '+server.API_KEY
        req=urllib.request.Request(self.url+path,data=json.dumps(data).encode() if data is not None else None,headers=headers)
        return urllib.request.urlopen(req,timeout=5)
    def test_authentication(self):
        with self.assertRaises(urllib.error.HTTPError) as caught: self.request('/v1/models',key=False)
        self.assertEqual(caught.exception.code,401)
        with self.request('/health',key=False) as r: self.assertEqual(json.load(r)['status'],'ok')
        with self.assertRaises(urllib.error.HTTPError): self.request('/api/integration')
    def test_expired_ui_session_is_rejected_before_action(self):
        with patch.object(server,'launch') as launch:
            request=urllib.request.Request(self.url+'/api/run',data=b'{"action":"chat"}',headers={'X-App-Token':'old-session','Content-Type':'application/json'})
            with self.assertRaises(urllib.error.HTTPError) as caught: urllib.request.urlopen(request)
            self.assertEqual(caught.exception.code,403)
            self.assertEqual(json.load(caught.exception)['code'],'app_session_expired')
            launch.assert_not_called()
        with self.request('/',key=False) as response:
            self.assertEqual(response.headers['Cache-Control'],'no-store')
            self.assertIn("const TOKEN='"+server.TOKEN+"'",response.read().decode())
        with self.request('/session_api.js',key=False) as response:
            self.assertEqual(response.headers['Cache-Control'],'no-store')
            self.assertIn('createSessionApi',response.read().decode())
    def test_chat_and_stream(self):
        row={'id':'qwen3-0.6b-cmp','chat_supported':True,'archive':'test.cmp'}
        def fake_worker(data):
            self.assertEqual(data['context_window'],2048)
            server.update(answer='Ciao',result={'text':'Ciao','tokens':2,'prompt_tokens':3,'finish_reason':'stop'},busy=False)
        with patch.object(server,'models',return_value=[row]),patch.object(server,'worker',fake_worker):
            with self.request('/v1/models') as r: self.assertEqual(json.load(r)['data'][0]['id'],row['id'])
            payload={'model':row['id'],'messages':[{'role':'system','content':'Italiano'},{'role':'user','content':'Ciao'}],'max_tokens':2,'context_window':2048}
            with self.request('/v1/chat/completions',payload) as r:
                result=json.load(r)
                self.assertEqual(result['choices'][0]['message']['content'],'Ciao')
                self.assertEqual(result['usage']['total_tokens'],5)
            payload['stream']=True
            with self.request('/v1/chat/completions',payload) as r:
                raw=r.read().decode()
                self.assertIn('data: [DONE]',raw)
                events=[json.loads(line[6:]) for line in raw.splitlines() if line.startswith('data: {')]
                self.assertEqual(''.join(e['choices'][0]['delta'].get('content','') for e in events),'Ciao')
            payload['temperature']=.5
            with self.assertRaises(urllib.error.HTTPError) as caught: self.request('/v1/chat/completions',payload)
            self.assertEqual(caught.exception.code,400)
            payload.pop('temperature')
            payload['context_window']=True
            with self.assertRaises(urllib.error.HTTPError) as caught: self.request('/v1/chat/completions',payload)
            self.assertEqual(caught.exception.code,400)
    def test_actual_compression_job(self):
        with tempfile.TemporaryDirectory() as tmp:
            src=Path(tmp)/'source'; dst=Path(tmp)/'archive'
            src.write_bytes(b'API test'*10000)
            with self.request('/v1/jobs',{'action':'compress','source':str(src),'target':str(dst)}) as r:
                self.assertEqual(r.status,202); job_id=json.load(r)['id']
            deadline=time.monotonic()+5
            while time.monotonic()<deadline:
                with self.request('/v1/jobs/'+job_id) as r: state=json.load(r)
                if not state['busy']: break
                time.sleep(.02)
            self.assertFalse(state['busy']); self.assertIsNone(state['error'])
            self.assertEqual(state['result']['integrity'],'OK')
            server.Archive(dst).verify()
    def test_unload_respects_active_operation(self):
        with patch.dict(server.STATE,{'busy':True}):
            with self.assertRaises(ValueError): server.unload_engine()
        with patch.object(server,'ENGINE') as engine,patch.object(server,'ENGINE_KEY',('test','ram')),patch.dict(server.STATE,{'busy':False}):
            result=server.unload_engine()
            engine.close.assert_called_once()
            self.assertIsNone(server.ENGINE)
            self.assertTrue(result['unloaded'])

if __name__=='__main__': unittest.main()
