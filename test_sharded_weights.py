import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
from compressione import compress
from engine import ShardedCompressedWeights

class Tests(unittest.TestCase):
    def create(self,root):
        for name in ('first','second'):
            header=json.dumps({name:{'dtype':'F32','shape':[2,2],'data_offsets':[0,16]}}).encode()
            raw=root/(name+'.safe')
            raw.write_bytes(struct.pack('<Q',len(header))+header+struct.pack('<4f',1,2,3,4))
            compress(raw,root/(name+'.cmp'))
        manifest={'format':'cmp-sharded-v1','shards':{'a':'first.cmp','b':'second.cmp'},'weight_map':{'first':'a','second':'b'}}
        path=root/'model.json'; path.write_text(json.dumps(manifest))
        return path,manifest
    def test_routes_and_closes(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); path,_=self.create(root)
            weights=ShardedCompressedWeights(path)
            self.assertEqual(set(weights.header),{'first','second'})
            with patch.object(weights.readers['b'],'tensor_rows',return_value='value') as read:
                self.assertEqual(weights.tensor_rows('second',1,1),'value')
                read.assert_called_once_with('second',1,1)
            weights.close()
            self.assertTrue(all(r.archive._mapping is None for r in weights.readers.values()))
    def test_rejects_wrong_map_and_outside_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); path,manifest=self.create(root)
            manifest['weight_map']['second']='a'; path.write_text(json.dumps(manifest))
            with self.assertRaises(ValueError): ShardedCompressedWeights(path)
            manifest['shards']['a']='../outside.cmp'; path.write_text(json.dumps(manifest))
            with self.assertRaises(ValueError): ShardedCompressedWeights(path)

if __name__=='__main__': unittest.main()
