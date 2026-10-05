import json
from pathlib import Path
import time
from compressione import compress, Archive

def main():
    desktop = Path.home() / 'Desktop'
    output = desktop / 'compressione' / 'prove_modelli'
    output.mkdir(exist_ok=True)
    models = list((desktop / 'matrix_ia' / 'cache' / 'hub').rglob('*.safetensors'))
    models += list((desktop / 'matrix_ia' / 'cache' / 'hub').rglob('*.gguf'))
    models += [desktop / 'egemony' / 'models' / 'whisper-tiny' / 'model.bin']
    results = []
    for number, source in enumerate(models):
        if not source.is_file() or source.stat().st_size < 50000000: continue
        target = output / (f'{number}_' + source.name + '.cmp')
        print(f'Inizio: {source}', flush=True)
        start = time.perf_counter()
        meta = compress(source, target)
        compression_seconds = time.perf_counter()-start
        start = time.perf_counter()
        Archive(target).verify()
        verification_seconds = time.perf_counter()-start
        size = target.stat().st_size
        result = dict(source=str(source), archive=str(target), original_bytes=meta['size'],
                      compressed_bytes=size, saving_percent=100*(1-size/meta['size']),
                      compression_seconds=compression_seconds, verification_seconds=verification_seconds,
                      sha256=meta['sha256'], integrity='OK')
        results.append(result)
        (output / 'risultati.json').write_text(json.dumps(results, indent=2), encoding='utf8')
        rows = ['# Prove su modelli reali', '', 'Verifica completa CRC32 e SHA-256 per ogni archivio.', '',
                '| Modello | Originale MB | Archivio MB | Risparmio | Compressione s | Verifica s |',
                '|---|---:|---:|---:|---:|---:|']
        for r in results:
            label = 'Qwen3-0.6B' if 'Qwen' in r['source'] else ('BitNet GGUF' if '.gguf' in r['source'] else ('BitNet safetensors' if 'bitnet' in r['source'] else 'Whisper tiny'))
            rows.append(f"| {label} | {r['original_bytes']/1e6:.1f} | {r['compressed_bytes']/1e6:.1f} | {r['saving_percent']:.2f}% | {r['compression_seconds']:.1f} | {r['verification_seconds']:.1f} |")
        (output / 'RISULTATI.md').write_text('\n'.join(rows), encoding='utf8')
        print(json.dumps(result), flush=True)

if __name__ == '__main__': main()
