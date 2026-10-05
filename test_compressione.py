import os
from pathlib import Path
import tempfile
import unittest
from compressione import compress, decompress, Archive

class Tests(unittest.TestCase):
    def test_roundtrips_and_access(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for i, data in enumerate((b'', b'x', b'abc'*10000, os.urandom(20000), bytes(range(256))*100)):
                src, arc, dst = [root / f'{i}.{ext}' for ext in ('bin','cmp','out')]
                src.write_bytes(data)
                compress(src, arc, 4096)
                a = Archive(arc)
                a.verify()
                self.assertEqual(a.read_range(0,len(data)),data)
                self.assertEqual(a.read_range(len(data),0),b'')
                if len(data)>5000:
                    self.assertEqual(a.read_range(4000,1000),data[4000:5000])
                with self.assertRaises(ValueError): a.read_range(len(data),1)
                for j in range(len(a.meta['blocks'])):
                    self.assertEqual(a.block(j), data[j*4096:(j+1)*4096])
                decompress(arc, dst)
                self.assertEqual(dst.read_bytes(), data)
                with self.assertRaises(ValueError): decompress(arc, dst)
                a.close()
    def test_corruption(self):
        with tempfile.TemporaryDirectory() as tmp:
            src, arc = Path(tmp)/'src', Path(tmp)/'arc'
            src.write_bytes(os.urandom(8000))
            compress(src, arc, 4096)
            content = bytearray(arc.read_bytes()); content[10] ^= 1
            arc.write_bytes(content)
            with self.assertRaises(ValueError): Archive(arc).verify()
    def test_cancellation_cleans_partial_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            src, arc = root/'src', root/'arc'
            original=b'cancel test'*10000
            src.write_bytes(original)
            def cancel(done): raise ValueError('annullato')
            with self.assertRaises(ValueError): compress(src,arc,4096,progress=cancel)
            self.assertFalse(arc.exists())
            self.assertEqual(src.read_bytes(),original)
            self.assertEqual(len(list(root.iterdir())),1)

if __name__ == '__main__': unittest.main()
