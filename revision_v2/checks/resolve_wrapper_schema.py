"""Correct only a final-wrapper hash-record schema error after a completed audit.

The full numerical pass is preserved. Rehash its bound reports, primary batches,
source manifests and physical records before accepting the corrected historical
preservation comparison. No scientific acceptance function is changed or skipped
in the original completed run.
"""
from pathlib import Path
import datetime,hashlib,json

HERE=Path(__file__).resolve().parent;ROOT=HERE.parent;OLD=ROOT.parent
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text())
failed_path=HERE/'final_check_wrapper_schema_failure.json';d=read(failed_path);issues=[]
def need(ok,label):
 if not ok:issues.append(label)
prior=read(OLD/'full_rerun/checks/verification_final.json')
expected_errors={'Prior rerun output changed '+rel for rel in prior['fresh_output_hashes']}
need(d['complete'] and not d['computational_pass'],'Preserved completed wrapper failure')
need(set(d['issues'])==expected_errors and len(d['issues'])==len(expected_errors),'Failure limited exactly to prior-record schema comparisons')
for relative,value in prior['fresh_output_hashes'].items():
 need(isinstance(value,dict) and isinstance(value.get('sha256'),str),'Expected historical structured digest/'+relative)
 need(sha(OLD/'full_rerun/python_campaign'/relative)==value['sha256'],'Prior file preservation/'+relative)
for relative,value in d['bindings']['result_files'].items():
 if relative=='checks/run_revision_checks.py':continue
 need(sha(ROOT/relative)==value,'Completed-audit bound result unchanged/'+relative)
for section,filename in [('statistical','statistical_verification.json'),('policy','policy_verification.json')]:
 need(d['sections'][section]['pass'] and d['sections'][section]['issues']==0,'Completed numerical pass/'+section)
 need(sha(HERE/filename)==d['sections'][section]['report_sha256'],'Completed numerical report unchanged/'+section)
need(d['sections']['dynamic']['qualified_pass'] and d['dynamic_resolution']['pass'],'Qualified dynamic pass')
need(sha(HERE/'dynamic_resolution.json')==d['sections']['dynamic']['resolution_sha256'],'Dynamic resolution unchanged')
statistics=read(HERE/'statistical_verification.json')
for batch in statistics['batches']:
 for suffix,key in [('.json','source_hash'),('.npz','npz_hash')]:
  need(sha(ROOT/'results/batches'/(batch['id']+suffix))==batch[key],'Verified primary batch unchanged/'+batch['id']+suffix)
for filename in ['PROTOCOL_FREEZE.json','POLICY_AMENDMENT_FREEZE.json','dynamic_ENGINE_FREEZE.json']:
 for relative,value in read(ROOT/filename)['files'].items():need(sha(ROOT/relative)==value,'Frozen scientific source unchanged/'+relative)
for filename in ['MATH_FREEZE.json','INTEGRATION_FREEZE.json']:
 for relative,value in read(HERE/filename)['sha256'].items():need(sha(HERE/relative)==value,'Frozen acceptance unchanged/'+relative)
for relative,value in read(ROOT/'SOURCE_MANIFEST.json')['files'].items():need(sha(ROOT/'reference'/relative)==value,'Reference unchanged/'+relative)
state=read(ROOT/'dynamic_status.json')
for key,rec in state['tasks'].items():
 folder=ROOT/('dynamic_truth' if rec['kind']=='truth' else 'dynamic_branches')/key
 need(sha(folder/'metadata.json')==rec['metadata_sha256'],'Verified physical metadata unchanged/'+key)
 for relative,value in read(folder/'metadata.json')['output_hashes'].items():need(sha(folder/relative)==value,'Verified physical output unchanged/'+key+'/'+relative)
# The original full audit precedes this correction. No later edit to an
# unbound derivative file may be hidden by this packaging-only resolution.
completed=datetime.datetime.fromisoformat(d['created_utc']).timestamp()
for p in (ROOT/'results').rglob('*'):
 if p.is_file():need(p.stat().st_mtime<=completed,'Scientific file modified after full check/'+str(p.relative_to(ROOT)))
resolution=dict(schema='ssmr.wrapper-schema-resolution.v1',created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
 pass_=not issues,issues=issues,original_failure_sha256=sha(failed_path),
 error='Final wrapper compared SHA256 string to a structured digest record instead of its sha256 member.',
 correction='Compare exact digest string with value[sha256]; resolve supplied revision root to an absolute path.',
 scientific_acceptance_changed=False,prior_files_checked=len(prior['fresh_output_hashes']),
 primary_batch_pairs_rehashed=len(statistics['batches']),physical_records_rehashed=len(state['tasks']),
 preserved_completed_sections=['statistical','policy','qualified dynamic'],
 corrected_wrapper_sha256=sha(HERE/'run_revision_checks.py'))
resolution['pass']=resolution.pop('pass_')
(HERE/'WRAPPER_SCHEMA_RESOLUTION.json').write_text(json.dumps(resolution,indent=2))
if issues:print(json.dumps(resolution,indent=2));raise SystemExit(1)
d['created_utc']=resolution['created_utc'];d['computational_pass']=True;d['issues']=[]
d['wrapper_schema_resolution']=resolution
for relative in ['checks/run_revision_checks.py','checks/WRAPPER_SCHEMA_RESOLUTION.json','checks/final_check_wrapper_schema_failure.json','checks/resolve_wrapper_schema.py']:
 d['bindings']['result_files'][relative]=sha(ROOT/relative)
(HERE/'final_check.json').write_text(json.dumps(d,indent=2))
print(json.dumps({'complete':d['complete'],'computational_pass':d['computational_pass'],'qualified':d['qualified'],'issues':d['issues'],'coverage':d['coverage'],'diagnostic_headlines':d['scientific_results']['diagnostic_headlines']},indent=2))
