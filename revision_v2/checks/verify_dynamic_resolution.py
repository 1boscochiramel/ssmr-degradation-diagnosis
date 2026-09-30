"""Post hoc provenance resolution, not a replacement for the failed exact-export gate.

No numerical tolerance is introduced. Check all archived input identities, then
require exact replayed states/CSV bytes and exact recorded solver-input hashes.
"""
from pathlib import Path
import hashlib,json,collections
import numpy as np

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def array_sha(x):return hashlib.sha256(np.asarray(x,dtype='<f8').tobytes()).hexdigest()
def read(path):return json.loads(Path(path).read_text())
def canonical_issue(value):return '/'.join(str(value).replace('\\','/').rsplit('/',2)[-2:])

def audit(root,corrected):
 root=Path(root);issues=[];records=[];affected={}
 def need(ok,label):
  if not ok:issues.append(label)
 frozen=read(root/'dynamic_FORENSIC_FREEZE.json');replay=read(root/'dynamic_forensic_summary.json')
 original=read(root/'checks/dynamic_verification.json')
 need(original['pass'] is False,'Original exact-output failure retained')
 need(corrected['pass'] is False,'Corrected exact-output failure retained')
 identity=read(root/'checks/DYNAMIC_IDENTITY_AMENDMENT.json');adapter=read(root/'checks/DYNAMIC_PORTABLE_ADAPTER.json')
 for name,want in [('verify_dynamic_records.py',identity['original_sha256']),('verify_dynamic_records_v2.py',identity['corrected_sha256']),
                   ('verify_dynamic_records_v3.py',adapter['checker_sha256']),('dynamic_source_resolver.py',adapter['resolver_sha256'])]:
  need(sha(root/'checks'/name)==want,'Versioned checker hash/'+name)
 for name,want in frozen['files'].items():need(sha(root/name)==want,'Forensic source hash/'+name)
 need(replay['freeze_sha256']==sha(root/'dynamic_FORENSIC_FREEZE.json'),'Forensic summary freeze binding')
 tasks={r['key']:r for r in frozen['tasks']};results={r['key']:r for r in replay['results']}
 need(len(tasks)==len(frozen['tasks']) and len(results)==len(replay['results']),'Unique forensic records')
 for directory in ['dynamic_truth','dynamic_branches']:
  for p in sorted((root/directory).glob('*/metadata.json')):
   meta=read(p);rec=read(p.parent/'dynamic_record.json');key=rec['key']
   with np.load(p.parent/'states.npz') as z:exported=z['states'][0].copy()
   if directory=='dynamic_truth':
    with np.load(p.parent/'precondition_states.npz') as z:intended=z['states'][-1].copy()
    need(array_sha(intended)==meta['physical_state0_sha256']==meta['preconditioning']['state0_sha256'],key+'/exact intended truth input')
   else:
    parent=root/'dynamic_truth'/rec['result']['parent_key'];pm=read(parent/'metadata.json')
    with np.load(parent/'states.npz') as z:
     ix=np.flatnonzero(np.isclose(z['time_min'],meta['parent_decision_min'],atol=1e-12,rtol=0))
     need(len(ix)==1,key+'/unique parent decision');intended=z['states'][ix[0]].copy()
     need(array_sha(z['states'])==meta['parent_state_sha256'],key+'/exact explicit parent hash')
    need(pm['scenario']==meta['scenario'],key+'/explicit parent scenario')
    need(array_sha(intended)==meta['branch_initial_state_sha256'],key+'/exact intended branch input')
   difference=float(np.max(np.abs(intended-exported)));same=np.array_equal(intended,exported)
   records.append(dict(key=key,kind=rec['kind'],exact_exported_first=bool(same),max_abs_difference=difference))
   if same:continue
   affected[key]=rec['kind'];need(key in tasks and key in results,key+'/forensic coverage')
   if key not in tasks or key not in results:continue
   task=tasks[key];rr=results[key];dest=root/'dynamic_forensic_results'/key
   need(read(dest/'forensic.json')==rr,key+'/summary equals per-record evidence')
   need(rr['passed'] is True and all(v is True for v in rr['checks'].values()),key+'/all frozen forensic conditions')
   for filename,field in [('metadata.json','metadata_sha256'),('states.npz','states_npz_sha256'),('truth.csv','truth_csv_sha256'),('intervals.csv','intervals_csv_sha256'),('dynamic_record.json','dynamic_record_sha256')]:
    need(sha(p.parent/filename)==task[field],key+'/original unchanged/'+filename)
   with np.load(p.parent/'states.npz') as z:archived=z['states'].copy()
   with np.load(dest/'regenerated_states.npz') as z:regenerated=z['states'].copy()
   need(np.array_equal(archived,regenerated),key+'/full state exact replay')
   need(array_sha(archived)==rr['archived_state_sha256']==rr['regenerated_state_sha256'],key+'/replayed array hash')
   for suffix in ['truth.csv','intervals.csv']:
    need(sha(p.parent/suffix)==sha(dest/('regenerated_'+suffix)),key+'/CSV byte exact replay/'+suffix)
   need(bool(rr['captures']),key+'/solver capture present')
   for capture in rr['captures']:
    need(capture['solver_first_equals_input'] is True and capture['input_sha256']==capture['solver_first_sha256'],key+'/exact recorded solver initial input')
   main=rr['first_main_solve'];need(len(main)==1,key+'/unique first main solve')
   if len(main)==1:
    need(main[0]['input_sha256']==main[0]['intended_sha256']==array_sha(intended),key+'/exact intended main input')
    need(main[0]['dense_sha256']==main[0]['archived_first_sha256']==array_sha(exported),key+'/exact dense export correspondence')
   need(rr['original_export_max_abs_difference']==difference,key+'/reported export difference')
 expected=set()
 for key,kind in affected.items():
  for suffix in (['precondition exact state0','physical state0 hash'] if kind=='truth' else ['exact branch state','branch hash']):expected.add(key+'/'+suffix)
 corrected_set={canonical_issue(i) for i in corrected['issues']}
 need(corrected_set==expected and len(corrected['issues'])==len(expected),'Only explained exact-export discrepancies remain')
 original_nonidentity=[i for i in original['issues'] if not i.endswith('/unchanged absolute-time scenario')]
 need({canonical_issue(i) for i in original_nonidentity}==expected and len(original_nonidentity)==len(expected),'Original failures fully retained/accounted for')
 need(set(tasks)==set(results)==set(affected),'Forensic affected inventory exactly matches independent reconstruction')
 need(replay['passed'] is True and replay['records']==len(affected),'Forensic completion')
 return dict(schema='ssmr.dynamic-qualified-resolution.v1',pass_=not issues,issues=issues,
  status='EXACT_INPUT_AND_BITWISE_REPLAY_CONFIRMED_WITH_INTERPOLATED_EXPORT_LIMITATION' if not issues else 'UNRESOLVED',
  original_frozen_gate_pass=False,identity_corrected_gate_pass=False,
  original_issue_count=len(original['issues']),identity_corrected_issue_count=len(corrected['issues']),
  affected_records=len(affected),affected_counts=dict(collections.Counter(affected.values())),records_checked=len(records),
  max_abs_export_difference=max(x['max_abs_difference'] for x in records),
  forensic_freeze_sha256=sha(root/'dynamic_FORENSIC_FREEZE.json'),forensic_result_sha256=sha(root/'dynamic_forensic_summary.json'),
  original_verification_sha256=sha(root/'checks/dynamic_verification.json'),
  source_and_original_results_unchanged=not issues,
  scope='Post hoc exact provenance resolution: actual solver input continuity and exact replay verified; exported dense-output first samples are not bit-identical to intended inputs. Original frozen failure retained. No relaxed tolerance, retuning, physical validation, or independent ODE implementation.')
