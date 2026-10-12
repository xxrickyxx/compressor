import os
from pathlib import Path
import tempfile
import unittest
from compressione import compress, Archive, decompress, MAGIC_V2

class Tests(unittest.TestCase):
    def test_zstd_exact_ranges_and_corruption(self):
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'weights'; packed=Path(folder)/'weights.cmp'; restored=Path(folder)/'restored'
            data=b'Qwen'*20000+os.urandom(20000)
            source.write_bytes(data); compress(source,packed,block_size=4096,codec='zstd')
            self.assertEqual(packed.read_bytes()[:8],MAGIC_V2)
            archive=Archive(packed); self.assertIn('zstd',[b[3] for b in archive.meta['blocks']])
            self.assertEqual(bytes(archive.read_range(4000,9000)),data[4000:13000]); archive.close()
            archive.verify(); decompress(packed,restored); self.assertEqual(restored.read_bytes(),data)
            first=next(b for b in archive.meta['blocks'] if b[3]=='zstd')
            with packed.open('r+b') as stream:
                stream.seek(first[0]+first[1]-1); old=stream.read(1); stream.seek(-1,1); stream.write(bytes([old[0]^255]))
            with self.assertRaises(ValueError): Archive(packed).verify()

if __name__=='__main__': unittest.main()
