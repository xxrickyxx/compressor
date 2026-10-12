from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import launch

class Tests(unittest.TestCase):
    def test_refuses_incomplete_environment(self):
        with tempfile.TemporaryDirectory() as temp,patch.object(launch,'ROOT',Path(temp)),patch.object(launch.subprocess,'run') as probe:
            probe.return_value.returncode=1
            with self.assertRaisesRegex(RuntimeError,'Configura.cmd'): launch.environment_python()
    def test_prefers_local_environment(self):
        with tempfile.TemporaryDirectory() as temp,patch.object(launch,'ROOT',Path(temp)),patch.dict(launch.os.environ,{'COMPRESSOR_PYTHON':''}),patch.object(launch.subprocess,'run') as probe:
            python=Path(temp)/'.venv/Scripts/python.exe'
            python.parent.mkdir(parents=True); python.touch()
            probe.return_value.returncode=0
            self.assertEqual(launch.environment_python(),python)

if __name__=='__main__': unittest.main()
