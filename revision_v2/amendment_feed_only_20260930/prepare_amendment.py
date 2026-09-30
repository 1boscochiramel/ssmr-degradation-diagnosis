"""Write the amendment specification and preservation inventory before execution."""
from pathlib import Path
import hashlib
import json
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent
PARENT = ROOT.parent
sys.path.insert(0,str(PARENT))
import dynamics
def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(name, data):
    path = ROOT/name
    if path.exists():
        raise RuntimeError('Refuse to overwrite amendment evidence: '+str(path))
    temp = path.with_suffix(path.suffix+'.tmp')
    temp.write_text(json.dumps(data,indent=2)+'\n',encoding='utf-8')
    temp.replace(path)

if __name__ == '__main__':
    parent = json.loads((PARENT/'protocol.json').read_text())
    cases = [c for c in parent['cases'] if c['policy']]
    save('amendment_protocol.json', {
        'schema':'ssmr.feed-only-amendment.v1',
        'date':'2026-09-30','created_utc':datetime.now(timezone.utc).isoformat(),
        'status':'Outcome-aware supplemental analysis; freeze before new comparison, not retrospective preregistration',
        'cases':cases,'pulse_start_min':10.0,'pulse_end_min':[16.0,21.0],
        'increment_mol_min':parent['active_feed_increment'],
        'horizon_end_min':parent['policy']['horizon_end_min'],
        'nominal_mol_min':{str(k):float(v) for k,v in dynamics.U_SS.items()},
        'sensor_sets':list(parent['sensor_sets']), 'trials_per_cell':1000,
        'measures':['H2_shortfall_mol','actual_ethanol_mol','commanded_ethanol_mol','H2_produced_mol'],
        'primary_contrast':'Original active diagnostic action minus feed-only with same original pulse end; all trials retained',
        'interpretation':'Schedule-yoked conditional downstream-action ablation; fixed16/21 controls separately reported; not total information value or economic benefit',
        'original_protocol_sha256':sha(PARENT/'protocol.json'),
        'original_engine_sha256':sha(PARENT/'dynamics.py'),
        'original_final_check_sha256':sha(PARENT/'checks/final_check.json'),
        'amendment_text_sha256':sha(ROOT/'PROTOCOL_AMENDMENT.txt'),
        'new_physical_arms':len(cases)*2,
        'new_noise_draws':0,
    })
    files = {}
    for p in sorted(PARENT.rglob('*')):
        if not p.is_file():continue
        rel=p.relative_to(PARENT)
        if rel.parts[0] in [ROOT.name,'.research','__pycache__']:continue
        if '__pycache__' in rel.parts or p.suffix in ['.pyc','.tmp']:continue
        if rel.as_posix() in ['board.jsonl','CONTEXT_GAPS.md']:continue
        files[rel.as_posix()]={'sha256':sha(p),'bytes':p.stat().st_size}
    save('parent_inventory.json',{'created_utc':datetime.now(timezone.utc).isoformat(),'files':files})
    print(json.dumps({'cases':len(cases),'arms':len(cases)*2,'preserved_files':len(files)}))
