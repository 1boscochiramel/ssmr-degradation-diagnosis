"""Frozen independent raw-evidence checker for the dated feed-only amendment."""
from pathlib import Path
import argparse,datetime,hashlib,json
import numpy as np
import pandas as pd
from audit_math import MEASURES,account,array_close,blind_command,arm_key,stats

HERE=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text())
def csv(p):return pd.read_csv(p,float_precision='round_trip')
def array_sha(x):return hashlib.sha256(np.asarray(x,dtype='<f8').tobytes()).hexdigest()

def audit(root):
 root=Path(root).resolve();parent=root.parent;issues=[];bindings={};cache={}
 def need(ok,label):
  if not bool(ok):issues.append(label)
 def close(a,b,label):need(array_close(a,b),label)
 proto=read(root/'amendment_protocol.json');oldproto=read(parent/'protocol.json')
 frozen=read(root/'AMENDMENT_FREEZE.json');checker=read(root/'checks/CHECK_FREEZE.json')
 for rel,value in frozen['files'].items():need(sha(root/rel)==value,'Amendment frozen source/'+rel)
 for rel,value in checker['files'].items():need(sha(root/'checks'/rel)==value,'Frozen checker/'+rel)
 need(sha(root/'amendment_protocol.json')==checker['protocol_sha256'],'Checker protocol binding')
 need(sha(root/'run_feed_only.py')==checker['runner_sha256'],'Checker runner binding')
 inventory=read(root/'parent_inventory.json')
 for rel,value in inventory['files'].items():
  need(sha(parent/rel)==value['sha256'],'Parent preservation/'+rel)
  need((parent/rel).stat().st_size==value['bytes'],'Parent byte size/'+rel)
 need(proto['cases']==[c for c in oldproto['cases'] if c['policy']],'Complete original policy-case list')
 need(proto['sensor_sets']==list(oldproto['sensor_sets']),'Original sensor sets unchanged')
 need(proto['trials_per_cell']==oldproto['n_evaluation'],'Original trial denominator')
 need(proto['pulse_end_min']==oldproto['policy']['decision_times_min']==[16.,21.],'Original pulse-end schedules')
 need(proto['pulse_start_min']==oldproto['active_move_start_min']==10.,'Original pulse start')
 need(proto['increment_mol_min']==oldproto['active_feed_increment'],'Original pulse increment')
 need(proto['horizon_end_min']==oldproto['policy']['horizon_end_min']==31.,'Common horizon')
 need(proto['nominal_mol_min']=={'1':.0021,'2':.0018},'Original nominal commands')
 need(proto['measures']==list(MEASURES[:-1]),'Prespecified physical vector')
 need(proto['new_noise_draws']==0,'No new stochastic draws declared')
 for key,rel in [('original_protocol_sha256','protocol.json'),('original_engine_sha256','dynamics.py'),('original_final_check_sha256','checks/final_check.json')]:need(proto[key]==sha(parent/rel),'Parent binding/'+key)
 prior_check=read(parent/'checks/final_check.json')
 need(prior_check['complete'] and prior_check['computational_pass'] and prior_check['qualified'],'Parent qualified verification')
 need(prior_check['original_frozen_dynamic_gate_pass'] is False and prior_check['dynamic_resolution']['pass'],'Original export qualification retained')
 need(sha(root/'PROTOCOL_AMENDMENT.txt')==proto['amendment_text_sha256'],'Dated amendment text binding')
 status=read(root/'run_status.json');summary=read(root/'outputs/summary.json')
 complete=status['status']=='complete' and summary['complete'] is True
 need(complete,'Completed new execution')
 need(summary['freeze_sha256']==sha(root/'AMENDMENT_FREEZE.json'),'Summary freeze binding')
 need(summary['interpretation']==proto['interpretation'],'Summary interpretation unchanged')
 for rel,value in summary['files'].items():need(sha(root/rel)==value,'Summary output binding/'+rel)
 cases={c['id']:c for c in proto['cases']};expected_arms={(c,float(t)) for c in cases for t in proto['pulse_end_min']}
 need(proto['new_physical_arms']==len(expected_arms)==status['tasks']==summary['physical_arms'],'Complete fixed-arm count')
 need({p.name for p in (root/'branches').iterdir() if p.is_dir()}=={f'{c}_t{t:g}' for c,t in expected_arms},'Exact new branch folder inventory')
 frozen_time=datetime.datetime.fromisoformat(checker['created_utc'])
 def load(folder):
  folder=Path(folder)
  if folder not in cache:
   cache[folder]=(read(folder/'metadata.json'),csv(folder/'truth.csv'),csv(folder/'intervals.csv'))
  return cache[folder]
 def segment_account(folder,stop=None):
  meta,tr,iv=load(folder)
  if stop is not None:iv=iv[iv.t_end<=stop+1e-10].copy()
  ts=tr.time_min.to_numpy();ia=np.searchsorted(ts,iv.t_start.to_numpy());ib=np.searchsorted(ts,iv.t_end.to_numpy())
  need(np.all(ia<len(ts)) and np.all(ib<len(ts)),str(folder)+'/trace endpoint coverage')
  close(ts[ia],iv.t_start.to_numpy(),str(folder)+'/left time alignment');close(ts[ib],iv.t_end.to_numpy(),str(folder)+'/right time alignment')
  close(tr.true_H2_mol_min.to_numpy()[ia],iv.H2_start_mol_min.to_numpy(),str(folder)+'/H2 left endpoints')
  close(tr.true_H2_mol_min.to_numpy()[ib],iv.H2_end_mol_min.to_numpy(),str(folder)+'/H2 right endpoints')
  close(iv.actual_ethanol_start.to_numpy(),iv.commanded_ethanol_mol_min.to_numpy()*tr.feed_gain.to_numpy()[ia],str(folder)+'/actual feed left')
  close(iv.actual_ethanol_end.to_numpy(),iv.commanded_ethanol_mol_min.to_numpy()*tr.feed_gain.to_numpy()[ib],str(folder)+'/actual feed right')
  totals,amounts=account(iv,tr.demand_mol_min.to_numpy()[ia],tr.demand_mol_min.to_numpy()[ib])
  for name,want in amounts.items():close(iv[name].to_numpy(),want,str(folder)+'/raw interval amount/'+name)
  return totals,iv
 full_cache={}
 def full_account(case,end,folder,expected_command):
  key=(case,float(end),str(folder))
  if key in full_cache:return full_cache[key]
  source=parent/'dynamic_truth'/(case+'_active');pre,pi=segment_account(source,end);post,bi=segment_account(folder)
  close(bi.commanded_ethanol_mol_min.to_numpy(),np.full(len(bi),expected_command),str(folder)+'/fixed post-pulse command')
  close(np.asarray([pi.t_start.iloc[0],pi.t_end.iloc[-1],bi.t_start.iloc[0],bi.t_end.iloc[-1]]),np.asarray([0.,end,end,31.]),str(folder)+'/common horizon and join')
  alliv=pd.concat([pi,bi],ignore_index=True)
  close(alliv.t_end.to_numpy()[:-1],alliv.t_start.to_numpy()[1:],str(folder)+'/no gaps or overlap')
  close((alliv.t_end-alliv.t_start).to_numpy(),np.full(len(alliv),oldproto['solver']['sample_min']),str(folder)+'/original sample quadrature')
  result={m:pre[m]+post[m] for m in MEASURES};full_cache[key]=(result,pre,post,alliv);return full_cache[key]
 arm_rows=csv(root/'outputs/feed_only_arm_costs.csv')
 need(not arm_rows.duplicated(['case_id','pulse_end_min']).any() and set(zip(arm_rows.case_id,arm_rows.pulse_end_min))==expected_arms,'Fixed-arm cost keys')
 checked_arms=[];arm_costs={};arm_future={}
 for case,end in sorted(expected_arms):
  c=cases[case];u0=proto['nominal_mol_min'][str(c['mode'])];folder=root/'branches'/f'{case}_t{end:g}'
  archived=parent/'dynamic_branches'/f'{case}_active_t{end:g}_u0';source=parent/'dynamic_truth'/(case+'_active')
  meta,tr,iv=load(folder);am,atr,aiv=load(archived);pm,ptr,piv=load(source)
  for field in ['schema','scenario','settings','segments','source_hashes','parent_state_sha256','branch_initial_state_sha256','parent_decision_min','state_sha256','deterioration_semantics','quadrature']:
   need(meta[field]==am[field],str(folder)+'/archived metadata identity/'+field)
  need(meta['scenario']==pm['scenario'] and meta['settings']==oldproto['solver'],str(folder)+'/parent scenario and solver')
  need(meta['segments']==[[end,31.,u0]],str(folder)+'/blind continuation segment')
  for name,value in meta['output_hashes'].items():need(sha(folder/name)==value,str(folder)+'/new output hash/'+name)
  for name in ['truth.csv','intervals.csv']:need(sha(folder/name)==sha(archived/name),str(folder)+'/byte-exact replay/'+name)
  with np.load(folder/'states.npz') as nz,np.load(archived/'states.npz') as az,np.load(source/'states.npz') as pz:
   for name in ['states','time_min']:need(np.array_equal(nz[name],az[name]) and nz[name].dtype==az[name].dtype,str(folder)+'/exact replay/'+name)
   need(array_sha(nz['states'])==meta['state_sha256'],str(folder)+'/new state-array hash')
   ix=np.flatnonzero(np.isclose(pz['time_min'],end,atol=1e-12,rtol=0));need(len(ix)==1,str(folder)+'/unique saved parent state')
   need(array_sha(pz['states'][ix[0]])==meta['branch_initial_state_sha256'],str(folder)+'/exact intended solver input')
   need(array_sha(pz['states'])==meta['parent_state_sha256'],str(folder)+'/exact parent trajectory hash')
  exe=read(folder/'amendment_execution.json');need(datetime.datetime.fromisoformat(exe['started_utc'])>=frozen_time,str(folder)+'/fresh execution after checker freeze')
  need(exe['spec_sha256']==sha(root/'amendment_protocol.json') and exe['freeze_sha256']==sha(root/'AMENDMENT_FREEZE.json'),str(folder)+'/execution bindings')
  result,pre,post,alliv=full_account(case,end,folder,u0)
  close(alliv.commanded_ethanol_mol_min.to_numpy(),blind_command(alliv.t_start,u0,proto['increment_mol_min'],10.,end),str(folder)+'/complete blind command schedule')
  close(result['commanded_ethanol_mol'],u0*31+proto['increment_mol_min']*(end-10),str(folder)+'/analytic commanded amount')
  row=arm_rows[(arm_rows.case_id==case)&(arm_rows.pulse_end_min==end)].iloc[0].to_dict()
  expected_meta=dict(case_id=case,mode=c['mode'],true_h=c['h'],pulse_end_min=end,pulse_start_min=10.,post_pulse_command_mol_min=u0,parent_key=case+'_active',branch_path=f'branches/{case}_t{end:g}',archived_branch_path=f'dynamic_branches/{case}_active_t{end:g}_u0',start_min=0.,end_min=31.,decision_min=end,intervals=len(alliv))
  for name,value in expected_meta.items():
   need(row[name]==value,str(folder)+'/arm metadata/'+name);need(exe['arm'][name]==value,str(folder)+'/execution arm metadata/'+name)
  for name,value in result.items():close(row[name],value,str(folder)+'/fixed arm cost/'+name);close(exe['arm'][name],value,str(folder)+'/execution cost/'+name)
  arm_costs[(case,end)]=result;arm_future[(case,end)]=post;checked_arms.append(dict(expected_meta,**result))
 # Reconstruct original diagnostic physical costs from raw chosen branches.
 decisions=csv(parent/'results/policy_decisions.csv');decisions=decisions[decisions.active].copy()
 original=csv(parent/'results/policy_trials.csv');original=original[original.active].set_index(['case_id','set','trial_id'])
 expected_keys={(case,s,i) for case in cases for s in proto['sensor_sets'] for i in range(proto['trials_per_cell'])}
 keys=['case_id','set','trial_id'];need(not decisions.duplicated(keys).any() and set(map(tuple,decisions[keys].to_numpy()))==expected_keys,'Exact original active trial inventory')
 paired=csv(root/'outputs/paired_trials.csv');need(not paired.duplicated(keys).any() and set(map(tuple,paired[keys].to_numpy()))==expected_keys,'Exact paired trial inventory')
 paired=paired.set_index(keys);expected_rows=[]
 for r in decisions.to_dict('records'):
  case=r['case_id'];end=float(r['decision_min']);index=int(r['command_index']);c=cases[case];key=(case,r['set'],r['trial_id'])
  need(r['mode']==c['mode'] and r['true_h']==c['h'],'Original trial case metadata/'+str(key))
  u0=proto['nominal_mol_min'][str(c['mode'])];need(index in range(oldproto['policy']['command_points']),'Original command index/'+str(key))
  command=np.linspace(u0,.0024,oldproto['policy']['command_points'])[index];close(r['command_mol_min'],command,'Original command value/'+str(key))
  selected=arm_key(case,end);control=arm_costs[selected];folder=parent/'dynamic_branches'/f'{case}_active_t{end:g}_u{index}'
  policy,pre,post,iv=full_account(case,end,folder,command);saved=paired.loc[key];orig=original.loc[key]
  for name in ['mode','true_h','call','decision_min','command_index']:
   need(saved[name]==r[name],'Paired original decision metadata/'+str(key)+'/'+name)
  close(saved['command_mol_min'],r['command_mol_min'],'Paired original command/'+str(key))
  need(saved['branch_path']==f'branches/{case}_t{end:g}','Comparator selected only by case and original stop/'+str(key))
  new=dict(case_id=case,mode=c['mode'],true_h=c['h'],set=r['set'],trial_id=r['trial_id'],decision_min=end,command_index=index)
  for name in proto['measures']:
   delta=policy[name]-control[name]
   close(delta,post[name]-arm_future[selected][name],'Shared pulse prefix cancels/'+str(key)+'/'+name)
   close(orig[name],policy[name],'Original saved policy cost/'+str(key)+'/'+name)
   for prefix,value in [('diagnostic',policy[name]),('feed_only',control[name]),('difference',delta)]:
    close(saved[prefix+'_'+name],value,'Paired physical amount/'+str(key)+'/'+prefix+'_'+name);new[prefix+'_'+name]=value
  expected_rows.append(new)
 expected=pd.DataFrame(expected_rows);reported=csv(root/'outputs/paired_summary.csv')
 need(not reported.duplicated(['case_id','set']).any() and set(zip(reported.case_id,reported['set']))=={(c,s) for c in cases for s in proto['sensor_sets']},'Complete summary groups')
 reported=reported.set_index(['case_id','set']);checked_groups=[]
 for key,g in expected.groupby(['case_id','set'],sort=True):
  row=dict(case_id=key[0],set=key[1],mode=int(g.iloc[0]['mode']),true_h=g.iloc[0]['true_h'],trials=len(g),stop16_count=int((g.decision_min==16).sum()),stop21_count=int((g.decision_min==21).sum()),non_nominal_action_count=int((g.command_index!=0).sum()))
  saved=reported.loc[key]
  for name in ['mode','true_h','trials','stop16_count','stop21_count','non_nominal_action_count']:need(saved[name]==row[name],'Summary metadata/'+str(key)+'/'+name)
  for name in proto['measures']:
   for prefix in ['diagnostic','feed_only','difference']:
    for stat,value in stats(g[prefix+'_'+name]).items():
     field=prefix+'_'+name+'_'+('sd' if stat=='std' else stat);close(saved[field],value,'Summary arithmetic/'+str(key)+'/'+field);row[field]=value
  checked_groups.append(row)
 need(summary['paired_trial_rows']==len(expected_rows) and summary['paired_groups']==len(checked_groups),'Summary final counts')
 for p in sorted((root/'branches').rglob('*')):
  if p.is_file():bindings[p.relative_to(root).as_posix()]=sha(p)
 for rel in ['amendment_protocol.json','AMENDMENT_FREEZE.json','parent_inventory.json','checks/CHECK_FREEZE.json','outputs/summary.json','outputs/feed_only_arm_costs.csv','outputs/paired_trials.csv','outputs/paired_summary.csv','run_status.json']:bindings[rel]=sha(root/rel)
 return dict(schema='ssmr.feed-only-independent-check.v1',created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),complete=complete,pass_=not issues,issues=issues,
   coverage=dict(parent_files_preserved=len(inventory['files']),fixed_arms=len(checked_arms),paired_trials=len(expected_rows),paired_groups=len(checked_groups),new_noise_draws=0),
   parent_qualified_check_sha256=sha(parent/'checks/final_check.json'),parent_exact_export_gate_pass=False,qualified_parent_resolution_retained=True,
   fixed_arm_costs=checked_arms,paired_summary=checked_groups,bindings=bindings,
   scope='Outcome-aware dated amendment. Same-model internal computational verification. Fixed blind schedules separately reported; primary contrast is schedule-yoked downstream action, not an autonomous stopping policy, pure information value, economic benefit or physical validation.')

if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,default=HERE.parent);ap.add_argument('--out',type=Path,default=HERE/'verification.json');args=ap.parse_args()
 result=audit(args.root);result['pass']=result.pop('pass_');args.out.write_text(json.dumps(result,indent=2,allow_nan=False))
 print(json.dumps({k:result[k] for k in ['complete','pass','issues','coverage','scope']},indent=2));raise SystemExit(0 if result['pass'] else 1)
