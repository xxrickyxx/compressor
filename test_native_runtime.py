import os
from pathlib import Path
import unittest
from unittest.mock import patch
import runtime_support

class Tests(unittest.TestCase):
    def test_child_gets_dll_paths_without_mutating_parent(self):
        base={'PATH':r'C:\Windows\System32','UNCHANGED':'yes'}
        executable=Path(__file__).with_name('llama-server.exe')
        with patch.object(runtime_support.os,'name','nt'):
            env=runtime_support.native_environment(executable,base)
        self.assertEqual(base['PATH'],r'C:\Windows\System32')
        self.assertEqual(env['UNCHANGED'],'yes')
        self.assertIn(str(executable.parent.resolve()),env['PATH'])
        self.assertTrue(env['PATH'].endswith(base['PATH']))

    @unittest.skipUnless(os.name=='nt','Windows loader regression')
    def test_actual_executable_with_windows_only_path(self):
        # Optional local regression: no weights or server needed.
        root=Path(os.environ.get('COMP_NATIVE_TEST_ROOT',str(Path(__file__).parent)))
        executable=root/'runtime/llama/llama-server.exe'
        if not executable.is_file():self.skipTest('Optional official llama.cpp binaries not installed')
        env=dict(os.environ,PATH=os.pathsep.join([str(Path(os.environ['WINDIR'])/'System32'),os.environ['WINDIR']]))
        from subprocess import PIPE
        process=runtime_support.spawn_native([str(executable),'--version'],env=env,stdout=PIPE,stderr=PIPE)
        stdout,stderr=process.communicate(timeout=20)
        self.assertEqual(process.returncode,0,(stdout+stderr).decode(errors='replace'))
        self.assertIn(b'build',stdout+stderr)

if __name__=='__main__':unittest.main()
