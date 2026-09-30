"""Freeze the independent amendment checker before any new physical run."""
from pathlib import Path
import hashlib,json,datetime
HERE=Path(__file__).resolve().parent;ROOT=HERE.parent
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
if (HERE/'CHECK_FREEZE.json').exists():raise FileExistsError('Checker already frozen')
if (ROOT/'branches').exists() or (ROOT/'outputs').exists():raise RuntimeError('New amendment output exists before checker freeze')
selftest=json.loads((HERE/'math_selftest.json').read_text())
if not selftest['pass']:raise RuntimeError('Math selftest not passed')
files=['audit_math.py','verify_feed_only.py','test_audit_math.py','freeze_checker.py','CHECK_SPEC.txt','math_selftest.json','math_selftest_initial_failure.txt']
out=dict(schema='ssmr.feed-only-checker-freeze.v1',created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
 files={p:sha(HERE/p) for p in files},protocol_sha256=sha(ROOT/'amendment_protocol.json'),runner_sha256=sha(ROOT/'run_feed_only.py'),
 parent_inventory_sha256=sha(ROOT/'parent_inventory.json'),new_outcomes_present=False,
 chronology='Outcome-known amendment; checker frozen before new comparator integrations and new paired contrast outputs. Original parent outcomes already known and transparently retained.',
 tolerance='Exact state/time array and CSV replay; inherited physical-arithmetic absolute1e-13 plus relative1e-9. No favorable outcome or significance gate.',
 selftest_pass=True)
(HERE/'CHECK_FREEZE.json').write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2))
