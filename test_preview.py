from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.request
import urllib.error
import server
from task_loop import TaskLoop

class Tests(unittest.TestCase):
    def test_separate_origin_only_serves_project(self):
        with tempfile.TemporaryDirectory() as folder:
            loop=TaskLoop(folder); task=loop.create('Preview',['index.html'])
            directory=Path(task['output']); directory.mkdir(parents=True)
            (directory/'index.html').write_text('<html><body>Preview</body></html>')
            (Path(folder)/'secret.txt').write_text('private')
            with patch.object(server,'TASKS',loop):
                preview=server.preview_task(task['id'])
                try:
                    url=preview['url']
                    self.assertNotIn(':8765/',url)
                    self.assertIn('Preview',urllib.request.urlopen(url).read().decode())
                    for path in ['api/integration','../../secret.txt']:
                        with self.assertRaises(urllib.error.HTTPError): urllib.request.urlopen(url.replace('index.html',path))
                finally:
                    http=server.PREVIEWS.pop(task['id']); http.shutdown();http.server_close()

if __name__=='__main__':unittest.main()
