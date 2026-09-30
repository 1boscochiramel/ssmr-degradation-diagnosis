from pathlib import Path
import datetime,hashlib,json,py_compile
HERE=Path(__file__).resolve().parent;ROOT=HERE.parent
target=HERE/'INTEGRATION_FREEZE.json'
if target.exists():raise SystemExit('Integration freeze already exists; refusing replacement')
if list((ROOT/'results/batches').glob('*.json')):raise SystemExit('Stochastic outputs already exist; cannot assert pre-scoring freeze')
if not json.loads((HERE/'integration_selftest.json').read_text())['pass']:raise SystemExit('Synthetic checks not passed')
files=['integration_reference.py','verify_statistical.py','verify_policy_records.py','verify_dynamic_records.py','test_integration_reference.py']
for f in files:py_compile.compile(str(HERE/f),doraise=True)
out={'created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'sha256':{f:hashlib.sha256((HERE/f).read_bytes()).hexdigest() for f in files},
     'math_freeze_sha256':hashlib.sha256((HERE/'MATH_FREEZE.json').read_bytes()).hexdigest(),
     'protocol_sha256':hashlib.sha256((ROOT/'protocol.json').read_bytes()).hexdigest(),
     'statistical_pipeline_sha256':hashlib.sha256((ROOT/'statistical_campaign.py').read_bytes()).hexdigest(),
     'synthetic_evidence_sha256':hashlib.sha256((HERE/'integration_selftest.json').read_bytes()).hexdigest(),
     'chronology':'Core math frozen before physical campaign. These raw-record/statistical/policy integration checks frozen before any stochastic calibration or evaluation was generated or inspected. Physical truths generated meanwhile; only engineering smoke inspected by checker so far. Final packaging/report-binding wrapper may follow without changing these acceptance functions.'}
target.write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2))
