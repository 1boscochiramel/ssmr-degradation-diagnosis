"""Add explicit read-only source relocation to the identity-only checker version."""
from pathlib import Path
import hashlib,json,datetime

here=Path(__file__).resolve().parent
old=here/'verify_dynamic_records_v2.py'
assert hashlib.sha256(old.read_bytes()).hexdigest()=='00e86dc5772549dcd6500c9b55b408eea8bd064fefcedf9f9f519ca1af891277'
text=old.read_text()
for before,after in [
 ('def audit_tree(root,more_roots=()):','def audit_tree(root,more_roots=(),source_resolver=lambda p:p):'),
 ("need(sha(name)==h,label+'/source hash/'+name)","need(sha(source_resolver(name))==h,label+'/source hash/'+name)"),
 ("initial=loadmat(meta['initial_condition'])['x0c'].ravel()","initial=loadmat(source_resolver(meta['initial_condition']))['x0c'].ravel()")]:
 assert text.count(before)==1
 text=text.replace(before,after)
new=here/'verify_dynamic_records_v3.py';new.write_text(text)
out=dict(schema='ssmr.dynamic-readonly-path-adapter.v1',created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
 parent_sha256=hashlib.sha256(old.read_bytes()).hexdigest(),checker_sha256=hashlib.sha256(new.read_bytes()).hexdigest(),
 resolver_sha256=hashlib.sha256((here/'dynamic_source_resolver.py').read_bytes()).hexdigest(),
 changes=['Optional source resolver applied only to source-file hashing and initial-condition file reading.'],
 numerical_gates_unchanged=True,records_unmodified=True)
(here/'DYNAMIC_PORTABLE_ADAPTER.json').write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2))
