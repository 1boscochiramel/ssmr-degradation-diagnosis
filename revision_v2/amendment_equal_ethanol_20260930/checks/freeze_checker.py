"""Seal checker and input interface only before new amendment outcomes exist."""
from pathlib import Path
import ast
import datetime
import hashlib
import json

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def main():
    destination = HERE/'CHECK_FREEZE.json'
    if destination.exists(): raise RuntimeError('Refuse replacing checker freeze')
    if any((ROOT/p).exists() for p in ['branches', 'outputs', 'run_status.json', 'AMENDMENT_FREEZE.json']):
        raise RuntimeError('Freeze must precede root seal and all new execution evidence')
    math = json.loads((HERE/'math_selftest.json').read_text())
    plan = json.loads((HERE/'plan_verification.json').read_text())
    assert math['pass'] and not math['errors'] and not math['failures']
    assert plan['pass'] and not plan['issues'] and plan['complete'] is False
    for rel, digest in math['files'].items(): assert sha(HERE/rel) == digest, rel
    for path in HERE.glob('*.py'): ast.parse(path.read_text(encoding='utf-8'))
    for rel in ['prepare_equal_ethanol.py', 'run_equal_ethanol.py']:
        ast.parse((ROOT/rel).read_text(encoding='utf-8'))
    files = [p for p in HERE.iterdir() if p.is_file() and p.suffix in {'.py', '.txt', '.json'}]
    inputs = ['protocol.json', 'PROTOCOL_AMENDMENT.txt', 'prepare_equal_ethanol.py', 'run_equal_ethanol.py',
              'parent_inventory.json', 'schedule_inventory.json', 'trial_schedule_map.csv']
    data = dict(schema='ssmr.equal-ethanol-check-freeze.v1', created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                files={p.name: sha(p) for p in sorted(files)}, amendment_inputs={p: sha(ROOT/p) for p in inputs},
                new_outcomes_absent_at_freeze=True, engineering_math_pass=True, original_resource_plan_pass=True,
                prior_draft_failure_preserved='plan_verification_initial_failure.json',
                scope='Independent same-model checker frozen before new constant-feed trajectories. Exact source and solver-input identity; independent endpoint resource/shortfall arithmetic. No favorable outcome gate.')
    tmp = destination.with_suffix('.json.tmp')
    tmp.write_text(json.dumps(data, indent=2, allow_nan=False)+'\n', encoding='utf-8'); tmp.replace(destination)
    print(json.dumps({'frozen': True, 'created_utc': data['created_utc'], 'sha256': sha(destination), 'checker_files': len(data['files'])}, indent=2))

if __name__ == '__main__': main()
