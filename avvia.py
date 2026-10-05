from pathlib import Path
from compressione import compress, decompress, Archive

def path(prompt):
    return input(prompt).strip().strip('"')

while True:
    print('\nCOMPRESSIONE 0.1\n1. Comprimi un file\n2. Ricostruisci un file\n3. Verifica un archivio\n4. Informazioni\n0. Esci')
    choice = input('Scelta: ').strip()
    if choice == '0': break
    try:
        if choice == '1':
            src = path('Percorso del file originale: ')
            dst = path('Percorso archivio da creare (Invio = originale.cmp): ') or src + '.cmp'
            m = compress(src, dst)
            size = Path(dst).stat().st_size
            print(f"Completato: {dst}\nOriginale: {m['size']:,} byte\nArchivio: {size:,} byte")
            if m['size']: print(f"Risparmio: {100*(1-size/m['size']):.2f}%")
        elif choice == '2':
            src = path('Percorso archivio: ')
            dst = path('Percorso del file da ricostruire: ')
            decompress(src, dst)
            print('File ricostruito e verificato.')
        elif choice in ('3', '4'):
            a = Archive(path('Percorso archivio: '))
            if choice == '3':
                a.verify(); print('Integrità verificata.')
            else:
                print(f"File: {a.meta['name']}\nByte originali: {a.meta['size']:,}\nBlocchi: {len(a.meta['blocks'])}\nSHA-256: {a.meta['sha256']}")
    except Exception as exc:
        print(f'Operazione non completata: {exc}')
