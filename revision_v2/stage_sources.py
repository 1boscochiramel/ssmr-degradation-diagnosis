"""Preserve verified model inputs separately from all revision implementation."""
from pathlib import Path
import hashlib, json, shutil

ROOT = Path(__file__).resolve().parent
SRC = ROOT.parent / 'full_rerun/python_campaign'
DST = ROOT / 'reference'

def main():
    manifest = {}
    for p in sorted(SRC.rglob('*')):
        if not p.is_file() or '__pycache__' in p.parts:
            continue
        rel = p.relative_to(SRC)
        keep = p.suffix in {'.py', '.yaml', '.m', '.mat'}
        keep |= rel.as_posix() in {
            'reformer_diag/diag/outputs_diag/map_mode1.csv',
            'reformer_diag/diag/outputs_diag/map_mode2.csv',
            'reformer_diag/diag/outputs_diag/map2d_nominal.csv',
            'reformer_diag/diag/outputs_diag/map2d_kinpert.csv',
            'reformer_diag/diag/outputs_diag/map2d_np200.csv',
            'LICENSE', 'CITATION.cff', 'CAMPAIGN_ENVIRONMENT.json', 'SOURCE_STAGING.json'}
        if not keep:
            continue
        data = p.read_bytes(); q = DST / rel
        q.parent.mkdir(parents=True, exist_ok=True)
        if q.exists() and q.read_bytes() != data:
            raise RuntimeError(f'Refusing to replace changed reference: {rel}')
        if not q.exists():
            shutil.copy2(p, q)
        manifest[rel.as_posix()] = hashlib.sha256(data).hexdigest()
    (ROOT / 'SOURCE_MANIFEST.json').write_text(json.dumps({
        'source': '../full_rerun/python_campaign',
        'status': 'Previously verified source and maps; not new simulations.',
        'files': manifest}, indent=2)+'\n', encoding='utf-8')
    print(f'Preserved {len(manifest)} source/input files without modifying prior evidence.')

if __name__ == '__main__':
    main()
