"""Run the frozen, retrospective equal-ethanol constant-feed comparison only."""
from __future__ import annotations
import os
for name in ['OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS']:
    os.environ[name]='1'
import argparse, hashlib, json, sys, time, traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parent
PARENT=ROOT.parent
sys.path.insert(0,str(PARENT))
import dynamics
from dynamic_campaign import load_truth
from prepare_equal_ethanol import account, MEASURES, sha, utc, js, write_json, write_csv, read_csv

def state_sha(a): return hashlib.sha256(np.asarray(a).astype('<f8').tobytes()).hexdigest()
def same_resource(a,b,p): return abs(a-b)<=p['budget_atol_mol']+p['budget_rtol']*abs(b)
def verify_freeze(expected=None):
    path=ROOT/'AMENDMENT_FREEZE.json'
    if expected is not None and sha(path)!=expected: raise RuntimeError('Requested freeze hash does not match')
    frozen=js(path)
    for rel,digest in frozen['files'].items():
        if sha(ROOT/rel)!=digest: raise RuntimeError('Amendment source changed: '+rel)
    for rel,rec in js(ROOT/'parent_inventory.json')['files'].items():
        if sha(PARENT/rel)!=rec['sha256']: raise RuntimeError('Preserved parent file changed: '+rel)
    return frozen

def work(plan):
    protocol=js(ROOT/'protocol.json')
    folder=ROOT/'branches'/plan['schedule_id']
    if folder.exists(): raise RuntimeError('Fresh evidence refuses existing path: '+str(folder))
    started=utc(); tic=time.perf_counter()
    capture=[]
    try:
        truth=load_truth(PARENT/'dynamic_truth'/plan['parent_key'])
        idx=np.flatnonzero(truth['trace'].time_min.to_numpy()==10.)
        assert len(idx)==1
        expected=truth['states'][idx[0]].copy()
        assert state_sha(expected)==plan['state10_sha256']
        original_solve=dynamics.solve_ivp
        def observed_solve(fun,t_span,y0,*args,**kwargs):
            supplied=np.asarray(y0).copy()
            # Forward the unchanged function, original y0 object, and every solver option.
            sol=original_solve(fun,t_span,y0,*args,**kwargs)
            initial=sol.y[:,0].copy()
            dense=sol.sol(float(t_span[0])).copy() if sol.sol is not None else None
            capture.append({'t_span':list(t_span),'method':kwargs.get('method'),
                'rtol':kwargs.get('rtol'),'atol':kwargs.get('atol'),'max_step':kwargs.get('max_step'),
                'supplied_y0':supplied,'solver_y_initial':initial,'dense_y_initial':dense})
            return sol
        dynamics.solve_ivp=observed_solve
        try:
            branch=dynamics.continue_truth(truth,10.,plan['constant_command_mol_min'],
                horizon_end_min=31.,output_dir=folder)
        finally:
            dynamics.solve_ivp=original_solve
        assert len(capture)==1, 'Exactly one unchanged BDF integration expected'
        cap=capture[0]
        np.savez_compressed(folder/'solver_input_capture.npz',expected_parent_state=expected,
            supplied_y0=cap['supplied_y0'],solver_y_initial=cap['solver_y_initial'],dense_y_initial=cap['dense_y_initial'])
        identities={
            'parent_state10_sha256':state_sha(expected),
            'supplied_y0_sha256':state_sha(cap['supplied_y0']),
            'solver_y_initial_sha256':state_sha(cap['solver_y_initial']),
            'dense_y_initial_sha256':state_sha(cap['dense_y_initial']),
            'exported_first_state_sha256':state_sha(branch['states'][0]),
            'supplied_y0_equals_parent':bool(np.array_equal(cap['supplied_y0'],expected)),
            'solver_initial_equals_supplied':bool(np.array_equal(cap['solver_y_initial'],cap['supplied_y0'])),
            'exported_first_equals_supplied':bool(np.array_equal(branch['states'][0],cap['supplied_y0'])),
            'dense_initial_equals_exported_first':bool(np.array_equal(cap['dense_y_initial'],branch['states'][0])),
            'max_abs_exported_initial_difference':float(np.max(np.abs(branch['states'][0]-cap['supplied_y0']))),
            'capture_npz_sha256':sha(folder/'solver_input_capture.npz'),
            'original_export_qualification_retained':True}
        write_json(folder/'solver_input_evidence.json',{'schema':'ssmr.equal-ethanol-solver-input.v1',
            'source_engine_sha256':sha(PARENT/'dynamics.py'),'solve_calls':len(capture),
            'forwarding':'Original fun,y0,args,kwargs passed without alteration; returned solution unchanged',
            't_span':cap['t_span'],'method':cap['method'],'rtol':cap['rtol'],'atol':cap['atol'],'max_step':cap['max_step'],**identities})
        assert identities['supplied_y0_equals_parent'] and identities['solver_initial_equals_supplied']
        assert identities['dense_initial_equals_exported_first']
        demand=float(truth['trace'].iloc[idx[0]].demand_mol_min)
        prefix=truth['intervals'].loc[truth['intervals'].t_end<=10.+1e-10]
        full=pd.concat([prefix,branch['intervals']],ignore_index=True)
        whole=account(full,demand); window=account(branch['intervals'],demand)
        assert len(branch['intervals'])==210 and len(full)==310
        assert same_resource(window['actual_ethanol_mol'],plan['budget_10_31_mol'],protocol)
        assert same_resource(window['commanded_ethanol_mol'],plan['budget_10_31_mol'],protocol)
        record={**plan,'status':'complete','branch_path':folder.relative_to(ROOT).as_posix(),
            'reported_start_min':0.,'reported_end_min':31.,'budget_difference_actual_mol':window['actual_ethanol_mol']-plan['budget_10_31_mol'],
            'budget_difference_commanded_mol':window['commanded_ethanol_mol']-plan['budget_10_31_mol'],
            'exact_solver_input_pass':True,'exported_first_state_exact':identities['exported_first_equals_supplied']}
        record.update({'blind_'+m:whole[m] for m in MEASURES})
        record.update({'blind_10_31_'+m:window[m] for m in MEASURES})
        write_json(folder/'execution.json',{'started_utc':started,'completed_utc':utc(),'wall_seconds':time.perf_counter()-tic,
            'freeze_sha256':sha(ROOT/'AMENDMENT_FREEZE.json'),'protocol_sha256':sha(ROOT/'protocol.json'),
            'status':'complete','record':record,'solver_input_evidence_sha256':sha(folder/'solver_input_evidence.json')})
        print(json.dumps({'schedule_id':plan['schedule_id'],'status':'complete','wall_seconds':time.perf_counter()-tic}),flush=True)
        return record
    except Exception as exc:
        folder.mkdir(parents=True,exist_ok=True)
        (folder/'error.txt').write_text(traceback.format_exc(),encoding='utf-8')
        failure={**plan,'status':'failed','error':str(exc),'error_type':type(exc).__name__,'branch_path':folder.relative_to(ROOT).as_posix()}
        write_json(folder/'execution.json',{'started_utc':started,'completed_utc':utc(),'status':'failed','record':failure})
        print(json.dumps({'schedule_id':plan['schedule_id'],'status':'failed','error':str(exc)}),flush=True)
        return failure

def summarize(arms):
    protocol=js(ROOT/'protocol.json')
    original=read_csv(ROOT/'trial_schedule_map.csv')
    columns=['schedule_id']+['blind_'+prefix+m for prefix in ['','10_31_'] for m in MEASURES]
    paired=original.merge(arms[columns],on='schedule_id',validate='many_to_one',how='left')
    assert len(paired)==4000 and not paired.isna().any().any()
    for prefix in ['','10_31_']:
        for m in MEASURES: paired['difference_'+prefix+m]=paired['diagnostic_'+prefix+m]-paired['blind_'+prefix+m]
    actual=np.abs(paired['difference_10_31_actual_ethanol_mol'].to_numpy())
    commanded=np.abs(paired['difference_10_31_commanded_ethanol_mol'].to_numpy())
    tolerance=protocol['budget_atol_mol']+protocol['budget_rtol']*np.abs(paired.budget_10_31_mol.to_numpy())
    assert np.all(actual<=tolerance) and np.all(commanded<=tolerance)
    write_csv(ROOT/'outputs/paired_trials.csv',paired)
    summary=[]
    for (case_id,s),group in paired.groupby(['case_id','set'],sort=True):
        row={'case_id':case_id,'mode':int(group.iloc[0]['mode']),'true_h':group.iloc[0]['true_h'],'set':s,
            'trials':len(group),'unique_schedules':int(group.schedule_id.nunique()),
            'stop16_count':int((group.decision_min==16).sum()),'stop21_count':int((group.decision_min==21).sum()),
            'max_abs_ethanol_difference_mol':float(np.max(np.abs(group.difference_10_31_actual_ethanol_mol))),
            'max_abs_commanded_ethanol_difference_mol':float(np.max(np.abs(group.difference_10_31_commanded_ethanol_mol))),
            'constant_command_min_mol_min':float(group.constant_command_mol_min.min()),
            'constant_command_max_mol_min':float(group.constant_command_mol_min.max())}
        for prefix in ['','10_31_']:
            for m in MEASURES:
                for kind in ['diagnostic','blind','difference']:
                    values=group[kind+'_'+prefix+m].to_numpy()
                    for stat,value in [('mean',np.mean(values)),('sd',np.std(values,ddof=1)),('min',np.min(values)),('max',np.max(values))]:
                        row[kind+'_'+prefix+m+'_'+stat]=float(value)
        row['common_actual_ethanol_mol_mean']=row['diagnostic_actual_ethanol_mol_mean']
        row['common_ethanol_10_31_mol_mean']=row['diagnostic_10_31_actual_ethanol_mol_mean']
        summary.append(row)
    write_csv(ROOT/'outputs/paired_summary.csv',pd.DataFrame(summary))
    return {'paired_records':len(paired),'paired_groups':len(summary),'unique_schedules':len(arms),
        'max_abs_actual_budget_error_mol':float(actual.max()),'max_abs_commanded_budget_error_mol':float(commanded.max()),
        'new_noise_draws':0}

def main():
    p=argparse.ArgumentParser();p.add_argument('--workers',type=int,choices=[1,2],default=2)
    p.add_argument('--frozen-amendment-sha256',required=True);args=p.parse_args()
    verify_freeze(args.frozen_amendment_sha256)
    if (ROOT/'run_status.json').exists() or (ROOT/'branches').exists() or (ROOT/'outputs').exists():
        raise RuntimeError('Fresh execution refuses existing status, branches or outputs; preserve prior evidence')
    schedules=js(ROOT/'schedule_inventory.json')['schedules']
    started=utc();tic=time.perf_counter(); records=[]
    write_json(ROOT/'run_status.json',{'status':'running','started_utc':started,'total_schedules':len(schedules),'completed':0,'failed':0,'records':[]})
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures={pool.submit(work,x):x['schedule_id'] for x in schedules}
        for future in as_completed(futures):
            record=future.result();records.append(record)
            write_json(ROOT/'run_status.json',{'status':'running','started_utc':started,'updated_utc':utc(),
                'total_schedules':len(schedules),'completed':sum(x['status']=='complete' for x in records),
                'failed':sum(x['status']=='failed' for x in records),'records':records})
    records.sort(key=lambda x:x['schedule_id'])
    write_csv(ROOT/'outputs/arm_costs.csv',pd.DataFrame(records))
    if any(x['status']!='complete' for x in records):
        write_json(ROOT/'outputs/summary.json',{'complete':False,'failed_schedules':[x for x in records if x['status']!='complete']})
        write_json(ROOT/'run_status.json',{'status':'failed','started_utc':started,'completed_utc':utc(),'records':records})
        raise RuntimeError('At least one arm failed; evidence retained, no paired completion claimed')
    coverage=summarize(pd.DataFrame(records))
    verify_freeze(args.frozen_amendment_sha256)
    paths=['outputs/arm_costs.csv','outputs/paired_trials.csv','outputs/paired_summary.csv']
    write_json(ROOT/'outputs/summary.json',{'complete':True,'completed_utc':utc(),'coverage':coverage,
        'files':{p:sha(ROOT/p) for p in paths},'freeze_sha256':sha(ROOT/'AMENDMENT_FREEZE.json'),
        'scope':js(ROOT/'protocol.json')['interpretation'],'original_qualified_status_retained':True})
    write_json(ROOT/'run_status.json',{'status':'complete','started_utc':started,'completed_utc':utc(),
        'wall_seconds':time.perf_counter()-tic,'completed':len(records),'failed':0,'records':records})
    print(json.dumps({'status':'complete',**coverage,'wall_seconds':time.perf_counter()-tic}),flush=True)

if __name__=='__main__':main()
