"""Compressione v0.1: archivio senza perdita con accesso a blocchi."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import tempfile
import zlib
import mmap
from bisect import bisect_right

MAGIC = b'CMPBLK01'
FOOT = struct.Struct('<Q8s')
END = b'CMPINDEX'
MAX_BLOCK = 16 * 1024 * 1024

def atomic_target(path):
    path = Path(path)
    if path.exists():
        raise ValueError('Il file di destinazione esiste già: scegli un altro nome.')
    fd, name = tempfile.mkstemp(prefix='.compressione-', dir=path.parent)
    return path, os.fdopen(fd, 'wb'), name

def publish(temp, target):
    # Windows rename refuses to replace an existing destination.
    if target.exists():
        raise ValueError('La destinazione esiste già.')
    os.rename(temp, target)

def compress(source, target, block_size=1024*1024, progress=None):
    if not 4096 <= block_size <= MAX_BLOCK:
        raise ValueError('Dimensione blocco ammessa: da 4096 a 16777216 byte.')
    dest, out, temp = atomic_target(target)
    try:
        digest = hashlib.sha256()
        blocks = []
        total = 0
        with open(source, 'rb') as src, out:
            out.write(MAGIC)
            while True:
                raw = src.read(block_size)
                if not raw:
                    break
                digest.update(raw)
                packed = zlib.compress(raw, 6)
                codec = 'zlib' if len(packed) < len(raw) else 'raw'
                data = packed if codec == 'zlib' else raw
                blocks.append([out.tell(), len(data), len(raw), codec, zlib.crc32(raw)])
                out.write(data)
                total += len(raw)
                if progress:
                    progress(total)
            meta = {'version': 1, 'name': Path(source).name, 'size': total,
                    'block_size': block_size, 'sha256': digest.hexdigest(), 'blocks': blocks}
            index = json.dumps(meta, separators=(',', ':')).encode('utf8')
            out.write(index)
            out.write(FOOT.pack(len(index), END))
        publish(temp, dest)
        return meta
    finally:
        out.close()
        if os.path.exists(temp):
            os.unlink(temp)

class Archive:
    def __init__(self, path):
        self.path = path
        with open(path, 'rb') as f:
            size = f.seek(0, 2)
            if size < len(MAGIC) + FOOT.size:
                raise ValueError('Archivio troppo corto.')
            f.seek(0)
            if f.read(8) != MAGIC:
                raise ValueError('Formato archivio non riconosciuto.')
            f.seek(-FOOT.size, 2)
            length, marker = FOOT.unpack(f.read(FOOT.size))
            if marker != END or length > min(size-24, 64*1024*1024):
                raise ValueError('Indice archivio non valido.')
            self.index_start = size-FOOT.size-length
            f.seek(self.index_start)
            self.meta = json.loads(f.read(length))
        m = self.meta
        if m['version'] != 1 or not 4096 <= m['block_size'] <= MAX_BLOCK:
            raise ValueError('Versione o blocchi non validi.')
        offset = 8
        total = 0
        for pos, stored, raw, codec, crc in m['blocks']:
            if pos != offset or not 0 < stored <= raw <= m['block_size'] or codec not in ('raw', 'zlib'):
                raise ValueError('Indice blocchi non valido.')
            offset += stored
            total += raw
        if offset != self.index_start or total != m['size']:
            raise ValueError('Dimensioni archivio non valide.')
        self.starts = []
        self._mapping = None
        self._mapped_file = None
        position = 0
        for entry in m['blocks']:
            self.starts.append(position)
            position += entry[2]

    def read_range(self, start, length):
        """Legge byte originali senza ricostruire il file intero."""
        if start < 0 or length < 0 or start + length > self.meta['size']:
            raise ValueError('Intervallo fuori dall’archivio.')
        result = bytearray(length)
        done = 0
        if self._mapping is None:
            self._mapped_file = open(self.path, 'rb')
            self._mapping = mmap.mmap(self._mapped_file.fileno(),0,access=mmap.ACCESS_READ)
        while done < length:
            number = bisect_right(self.starts, start + done) - 1
            raw = self.block(number, self._mapping)
            offset = start + done - self.starts[number]
            count = min(length - done, len(raw) - offset)
            result[done:done+count] = raw[offset:offset+count]
            done += count
        return result

    def close(self):
        if getattr(self,'_mapping',None) is not None:
            self._mapping.close(); self._mapping = None
        if getattr(self,'_mapped_file',None) is not None:
            self._mapped_file.close(); self._mapped_file = None

    def __del__(self):
        self.close()

    def block(self, number, stream=None):
        pos, stored, length, codec, crc = self.meta['blocks'][number]
        if stream is None:
            with open(self.path, 'rb') as f:
                return self.block(number, f)
        stream.seek(pos)
        data = stream.read(stored)
        if codec == 'zlib':
            decoder = zlib.decompressobj()
            data = decoder.decompress(data, length + 1)
            if not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
                raise ValueError('Blocco compresso danneggiato.')
        if len(data) != length or zlib.crc32(data) != crc:
            raise ValueError('Blocco danneggiato: verifica fallita.')
        return data

    def verify(self, output=None, progress=None):
        digest = hashlib.sha256()
        total = 0
        with open(self.path, 'rb') as f:
            for i in range(len(self.meta['blocks'])):
                data = self.block(i, f)
                digest.update(data)
                if output:
                    output.write(data)
                total += len(data)
                if progress:
                    progress(total)
        if digest.hexdigest() != self.meta['sha256']:
            raise ValueError('Verifica SHA-256 fallita.')

def decompress(source, target, progress=None):
    archive = Archive(source)
    dest, out, temp = atomic_target(target)
    try:
        with out:
            archive.verify(out, progress)
        publish(temp, dest)
    finally:
        out.close()
        if os.path.exists(temp):
            os.unlink(temp)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('comprimi')
    p.add_argument('origine'); p.add_argument('destinazione')
    p.add_argument('--blocco', type=int, default=1024*1024, help='Byte per blocco')
    p = sub.add_parser('estrai')
    p.add_argument('origine'); p.add_argument('destinazione')
    for command in ('verifica', 'info'):
        sub.add_parser(command).add_argument('archivio')
    p = sub.add_parser('blocco')
    p.add_argument('archivio'); p.add_argument('numero', type=int); p.add_argument('destinazione')
    args = parser.parse_args()
    try:
        if args.command == 'comprimi':
            m = compress(args.origine, args.destinazione, args.blocco)
            size = Path(args.destinazione).stat().st_size
            saving = 100*(1-size/m['size']) if m['size'] else 0
            print(f"Originale: {m['size']:,} byte; archivio: {size:,} byte; risparmio: {saving:.2f}%")
        elif args.command == 'estrai':
            decompress(args.origine, args.destinazione)
            print('File ricostruito e SHA-256 verificato.')
        elif args.command == 'verifica':
            Archive(args.archivio).verify(); print('Integrità verificata: tutti i blocchi e SHA-256 corretti.')
        elif args.command == 'info':
            m = Archive(args.archivio).meta.copy()
            m['blocks'] = len(m['blocks'])
            print(json.dumps(m, indent=2, ensure_ascii=False))
        else:
            data = Archive(args.archivio).block(args.numero)
            dest, out, temp = atomic_target(args.destinazione)
            try:
                with out: out.write(data)
                publish(temp, dest)
            finally:
                out.close()
                if os.path.exists(temp): os.unlink(temp)
            print('Blocco estratto e verificato.')
    except (OSError, ValueError, KeyError, IndexError, TypeError, zlib.error) as exc:
        parser.exit(1, f'Errore: {exc}\n')

if __name__ == '__main__':
    main()
