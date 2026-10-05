import argparse
import json
from pathlib import Path
from compressione import Archive

def main():
    parser=argparse.ArgumentParser(description='Registra un archivio Qwen3 per la chat/API.')
    parser.add_argument('--archive',required=True)
    parser.add_argument('--config-dir',required=True)
    parser.add_argument('--id',default='qwen3-0.6b-cmp')
    parser.add_argument('--label',default='Qwen3 compresso')
    args=parser.parse_args()
    config_dir=Path(args.config_dir).resolve(); archive=Path(args.archive).resolve()
    config=json.loads((config_dir/'config.json').read_text(encoding='utf8'))
    if config.get('model_type')!='qwen3': parser.error('Serve una configurazione Qwen3.')
    if not (config_dir/'tokenizer_config.json').exists(): parser.error('Tokenizer mancante.')
    parsed=Archive(archive); parsed.verify(); size=archive.stat().st_size
    path=Path(__file__).parent/'models.json'
    rows=json.loads(path.read_text(encoding='utf8')) if path.exists() else []
    if any(row['id']==args.id for row in rows): parser.error('ID già registrato. Usa un altro --id.')
    rows.append({'id':args.id,'label':args.label,'model_type':'qwen3','source':str(config_dir/'model.safetensors'),
                 'archive':str(archive),'original_bytes':parsed.meta['size'],'compressed_bytes':size,
                 'saving_percent':100*(1-size/parsed.meta['size']),'integrity':'OK'})
    path.write_text(json.dumps(rows,indent=2),encoding='utf8')
    print(f'Modello registrato: {args.id}')

if __name__=='__main__': main()
