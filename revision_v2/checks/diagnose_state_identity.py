"""Read-only independent input/export state identity audit; no acceptance relaxation."""
from pathlib import Path
import hashlib,json,collections
import numpy as np

ROOT=Path(__file__).resolve().parent.parent
def sha(x):return hashlib.sha256(np.asarray(x,dtype='<f8').tobytes()).hexdigest()
records=[];issues=[]
for directory in ['dynamic_truth','dynamic_branches']:
 for p in sorted((ROOT/directory).glob('*/metadata.json')):
  meta=json.loads(p.read_text());rec=json.loads((p.parent/'dynamic_record.json').read_text())
  with np.load(p.parent/'states.npz') as z:observed=z['states'][0].copy()
  if directory=='dynamic_truth':
   with np.load(p.parent/'precondition_states.npz') as z:expected=z['states'][-1].copy()
   claimed=meta['physical_state0_sha256'];also=meta['preconditioning']['state0_sha256']
   parent_ok=sha(expected)==claimed==also
  else:
   parent=ROOT/'dynamic_truth'/rec['result']['parent_key'];pm=json.loads((parent/'metadata.json').read_text())
   with np.load(parent/'states.npz') as z:
    ix=np.flatnonzero(np.isclose(z['time_min'],meta['parent_decision_min'],atol=1e-12,rtol=0));assert len(ix)==1
    expected=z['states'][ix[0]].copy();whole_hash=sha(z['states'])
   claimed=meta['branch_initial_state_sha256']
   parent_ok=pm['scenario']==meta['scenario'] and whole_hash==meta['parent_state_sha256'] and sha(expected)==claimed
  if not parent_ok:issues.append(rec['key']+'/intended-input provenance')
  difference=np.abs(expected-observed);mismatch=difference!=0
  spacings=np.abs(np.spacing(expected[mismatch]))
  records.append(dict(key=rec['key'],kind=rec['kind'],input_provenance_exact=bool(parent_ok),
    saved_first_equals_input=bool(np.array_equal(expected,observed)),different_components=int(mismatch.sum()),
    max_abs_difference=float(difference.max()),max_abs_difference_in_expected_ulps=float((difference[mismatch]/spacings).max()) if mismatch.any() else 0.0,
    differing_indices=np.flatnonzero(mismatch).tolist(),intended_input_sha256=sha(expected),exported_first_sha256=sha(observed)))
out=dict(schema='ssmr.state-input-export-diagnostic.v1',records_checked=len(records),
   input_provenance_pass=not issues,issues=issues,saved_first_exact_pass=all(x['saved_first_equals_input'] for x in records),
   affected_counts=dict(collections.Counter(x['kind'] for x in records if not x['saved_first_equals_input'])),
   max_abs_difference=max(x['max_abs_difference'] for x in records),
   max_abs_difference_in_expected_ulps=max(x['max_abs_difference_in_expected_ulps'] for x in records),records=records,
   scope='Exact input metadata/source identity and descriptive saved-export discrepancy only. No tolerance is introduced and the original exact-export gate remains failed.')
(ROOT/'checks/state_identity_diagnostic.json').write_text(json.dumps(out,indent=2));print(json.dumps({k:v for k,v in out.items() if k!='records'},indent=2))
