from pathlib import Path
import tempfile
import threading
import unittest
from project_tools import ProjectTools
from task_loop import TaskLoop,validate_site

class Tests(unittest.TestCase):
    def test_backend_scaffold_and_http_workflow(self):
        with tempfile.TemporaryDirectory() as directory:
            loop=TaskLoop(directory);task=loop.create('Palestra con backend utenti e lezioni',['index.html','style.css','script.js'])
            def unexpected(*args):raise AssertionError('Trusted scaffold must not require model execution')
            result=loop.run(task,unexpected,threading.Event(),lambda **x:None)
            self.assertEqual(result['status'],'completed');self.assertTrue(result['backend_checks']['passed'])
            self.assertEqual(validate_site(result['output'],result['files']),[])
            self.assertIn('backend.py',result['files']);self.assertIn('gestionale.html',result['files'])
            tools=ProjectTools(result['output'])
            self.assertIn('backend.py',tools.list_files())
            tools.write_file('notes.txt','Before');tools.replace_text('notes.txt','Before','After')
            self.assertEqual(tools.read_file('notes.txt'),'After')
            for path in ['backend.py','./backend.py','../escape.py']:
                with self.assertRaises(ValueError):tools.write_file(path,'bad')
            with self.assertRaises(ValueError):tools.replace_text('notes.txt','missing','new')

    def test_model_can_use_scoped_tools(self):
        with tempfile.TemporaryDirectory() as directory:
            loop=TaskLoop(directory);task=loop.create('One page',['index.html'])
            outputs=iter([{'text':'{"tool":"list_files"}','tokens':4,'finish_reason':'stop'},
                          {'text':'{"tool":"write_file","path":"index.html","content":"<html><body>Hi</body></html>"}','tokens':20,'finish_reason':'stop'}])
            task=loop.run(task,lambda *x:next(outputs),threading.Event(),lambda **x:None,steps=2)
            self.assertEqual(task['status'],'completed');self.assertEqual(task['steps'],2)
            self.assertEqual([t['tool'] for t in task['tool_log']],['list_files','write_file'])

if __name__=='__main__':unittest.main()
