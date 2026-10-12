"""Pilot codec comparison on deterministic distributed 1 MiB model blocks."""
import hashlib
import json
import lzma
from pathlib import Path
import statistics
import time
import zlib
import zstandard
from compressione import Archive

def main():
    root=Path(__file__).resolve().parent
    registry=json.loads((root/'models.json').read_text(encoding='utf8'))
    results=[]
    for row in registry:
        if not (row.get('id')=='qwen3-0.6b-cmp' or '.gguf' in row['source']): continue
        archive=Archive(row['archive']); size=archive.meta['size']; block=1024*1024
        offsets=[int(i*(size-block)/31)//block*block for i in range(32)]
        samples=[bytes(archive.read_range(offset,block)) for offset in offsets]; archive.close()
        source_hash=hashlib.sha256(b''.join(samples)).hexdigest()
        zstd=zstandard.ZstdCompressor(level=3); zd=zstandard.ZstdDecompressor()
        codecs=[('DEFLATE/zlib6 (CMP payload)',lambda b:zlib.compress(b,6),zlib.decompress),
                ('Zstandard3',zstd.compress,zd.decompress),('XZ/LZMA2 preset3',lambda b:lzma.compress(b,preset=3),lzma.decompress)]
        for name,encode,decode in codecs:
            start=time.perf_counter(); encoded=[encode(b) for b in samples]; compression=time.perf_counter()-start
            timings=[]
            for _ in range(3):
                start=time.perf_counter()
                for source,packed in zip(samples,encoded):
                    if decode(packed)!=source: raise AssertionError('Roundtrip failed')
                timings.append(time.perf_counter()-start)
            packed_size=sum(min(len(b),len(raw)) for b,raw in zip(encoded,samples))
            result={'model':row.get('id','BitNet GGUF i2_s'),'codec':name,'sample_bytes':sum(map(len,samples)),
                    'packed_payload_bytes':packed_size,'saving_percent':100*(1-packed_size/sum(map(len,samples))),
                    'compression_mb_s':sum(map(len,samples))/compression/1e6,'decode_verify_mb_s':sum(map(len,samples))/statistics.median(timings)/1e6,
                    'offsets':offsets,'sample_sha256':source_hash,'roundtrip':'exact','zstd_version':zstandard.__version__}
            results.append(result); print(json.dumps(result),flush=True)
    path=root/'prove_modelli/codec_comparison.json'; path.write_text(json.dumps(results,indent=2),encoding='utf8')
    lines=['# Confronto codec: prova pilota','',
           '32 blocchi da 1 MiB distribuiti uniformemente per ciascun file, stesso campione per tutti i codec. Blocchi indipendenti, fallback raw se non conviene. Dimensioni solo payload: esclusi indici e framing CMP. Tempi non sono token/s. Misura pilota durante altre attività, non classifica controllata. SHA-256 e offset nel JSON; verifica byte per byte, tre decodifiche, mediana.',
           '', '| Modello | Codec | Risparmio campione | Compressione MB/s | Decodifica + confronto MB/s |','|---|---|---:|---:|---:|']
    for r in results: lines.append(f"| {r['model']} | {r['codec']} | {r['saving_percent']:.2f}% | {r['compression_mb_s']:.1f} | {r['decode_verify_mb_s']:.1f} |")
    lines.extend(['','Questi campioni non autorizzano a estrapolare il rapporto a tutto il modello, a tutte le quantizzazioni o a 500B. XZ e Zstd qui sono codec per blocchi, non benchmark di llama.cpp.'])
    (root/'CODEC_RESULTS.md').write_text('\n'.join(lines),encoding='utf8')

if __name__=='__main__': main()
