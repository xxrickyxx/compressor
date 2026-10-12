import json
from pathlib import Path
import tempfile
import threading
import unittest
from chat_store import ChatStore, fit_history
from task_loop import TaskLoop, safe_path, validate_site, clean_file

class Tokenizer:
    def apply_chat_template(self, messages, **kwargs):
        return list(range(sum(len(m['content']) for m in messages)+10))

class Tests(unittest.TestCase):
    def test_durable_history_and_recall(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'history.sqlite3'; store=ChatStore(path)
            first=store.create(); second=store.create()
            store.append(first['id'],'user','Sito negozio biciclette Firenze')
            store.append(first['id'],'assistant','Colore preferito: verde')
            reopened=ChatStore(path)
            self.assertEqual(len(reopened.get(first['id'])['messages']),2)
            self.assertEqual(reopened.recall('biciclette Firenze',second['id'])[0]['id'],first['id'])
            self.assertEqual(reopened.recall('biciclette Firenze',first['id']),[])
            reopened.delete(first['id'])
            with self.assertRaises(ValueError): reopened.get(first['id'])
            self.assertEqual(reopened.recall('biciclette Firenze',second['id']),[])
            self.assertEqual(len(reopened.restore(first['id'])['messages']),2)
            reopened.append(first['id'],'user','奥罗拉网站的颜色是绿色。')
            self.assertTrue(reopened.recall('奥罗拉网站使用什么颜色？',second['id']))

    def test_context_keeps_current_question(self):
        messages=[{'role':'user','content':'x'*100},{'role':'assistant','content':'y'*100},{'role':'user','content':'Remember green'}]
        fitted,dropped,_=fit_history(Tokenizer(),messages,128,24)
        self.assertEqual(fitted[-1],messages[-1]); self.assertEqual(dropped,2)
        with self.assertRaises(ValueError): fit_history(Tokenizer(),[{'role':'user','content':'z'*200}],128,24)

    def test_loop_continuation_resume_and_validation(self):
        with tempfile.TemporaryDirectory() as folder:
            loop=TaskLoop(folder); task=loop.create('Two pages',['index.html','about.html'])
            replies=iter([{'text':'<html><body><a href="about.html">About</a>','tokens':8,'finish_reason':'length'},
                          {'text':'</body></html>','tokens':4,'finish_reason':'stop'},
                          {'text':'<html><body><a href="index.html">Home</a></body></html>','tokens':12,'finish_reason':'stop'}])
            def generate(messages,limit): return next(replies)
            task=loop.run(task,generate,threading.Event(),lambda **x:None,steps=1)
            self.assertEqual(task['status'],'paused_budget')
            self.assertFalse((Path(task['output'])/'index.html').exists())
            task=loop.run(loop.load(task['id']),generate,threading.Event(),lambda **x:None,steps=2)
            self.assertEqual(task['status'],'completed'); self.assertEqual(task['steps'],3)
            self.assertEqual(validate_site(task['output'],task['files']),[])
            (Path(task['output'])/'about.html').unlink()
            self.assertTrue(validate_site(task['output'],task['files']))

    def test_generated_wrappers_and_page_links(self):
        self.assertEqual(clean_file('script.js\n```javascript\ndocument.title="Aurora";\n```','script.js'),'document.title="Aurora";\n')
        self.assertEqual(clean_file('body{color:green}\n```\n\nindex.html\n```html\n<html></html>','style.css'),'body{color:green}\n')
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder)/'index.html').write_text('<html><body>Hello</body></html>')
            (Path(folder)/'about.html').write_text('<html><body>About</body></html>')
            (Path(folder)/'script.js').write_text('```javascript\nalert(1)')
            problems=validate_site(folder,['index.html','about.html','script.js'])
            self.assertTrue(any('Missing page link' in p for p in problems))
            self.assertTrue(any('Markdown fences' in p for p in problems))

    def test_loop_cannot_escape_and_cancellation_checkpoints(self):
        with tempfile.TemporaryDirectory() as folder:
            for name in ['../escape.html','C:/file.html','/absolute.html','a.exe','a\\b.html']:
                with self.assertRaises(ValueError): safe_path(folder,name)
            loop=TaskLoop(folder); task=loop.create('One page',['index.html'])
            stop=threading.Event(); stop.set()
            with self.assertRaises(InterruptedError): loop.run(task,lambda *x:None,stop,lambda **x:None)
            self.assertEqual(loop.load(task['id'])['status'],'paused')

if __name__=='__main__': unittest.main()
