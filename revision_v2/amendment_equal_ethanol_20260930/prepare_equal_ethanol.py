"""Read-only parent accounting, dated protocol staging, and pre-run freeze."""
from __future__ import annotations
import argparse, hashlib, json, math
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parent
PARENT=ROOT.parent
CASES=['m1_C_d05_r1','m1_M_d05_r1','m2_C_d05_r1','m2_M_d05_r1']
MEASURES=['actual_ethanol_mol','commanded_ethanol_mol','H2_produced_mol','H2_demand_mol','H2_shortfall_mol']
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def utc(): return datetime.now(timezone.utc).isoformat()
def js(p): return json.loads(Path(p).read_text(encoding='utf-8'))
def write_json(p,x):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);q=p.with_suffix(p.suffix+'.tmp')
    q.write_text(json.dumps(x,indent=2,allow_nan=False)+'\n',encoding='utf-8');q.replace(p)
def write_csv(p,x):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);q=p.with_suffix(p.suffix+'.tmp')
    x.to_csv(q,index=False,float_format='%.17g');q.replace(p)
def read_csv(p): return pd.read_csv(p,float_precision='round_trip')

def account(df,demand):
    """Full-precision endpoint reconstruction; never use stored integral columns."""
    times=list(zip(df.t_start,df.t_end))
    assert times and all(b>a for a,b in times)
    assert all(abs(times[i][1]-times[i+1][0])<1e-10 for i in range(len(times)-1))
    assert np.array_equal(df.command_start_mol_min.to_numpy(),df.command_end_mol_min.to_numpy())
    vals={k:[] for k in MEASURES}
    for r in df.itertuples(index=False):
        dt=float(r.t_end-r.t_start)
        vals['actual_ethanol_mol'].append(dt*(r.actual_ethanol_start+r.actual_ethanol_end)/2.)
        vals['commanded_ethanol_mol'].append(r.command_start_mol_min*dt)
        vals['H2_produced_mol'].append(.5*(r.H2_start_mol_min+r.H2_end_mol_min)*dt)
        vals['H2_demand_mol'].append(demand*dt)
        vals['H2_shortfall_mol'].append(.5*(max(demand-r.H2_start_mol_min,0.)+max(demand-r.H2_end_mol_min,0.))*dt)
    return {k:math.fsum(v) for k,v in vals.items()}

def prepare():
    if (ROOT/'AMENDMENT_FREEZE.json').exists(): raise RuntimeError('Frozen amendment cannot be restaged')
    prior=js(PARENT/'protocol.json')
    final=js(PARENT/'checks/final_check.json')
    assert final['complete'] and final['computational_pass'] and final['qualified']
    selected=read_csv(PARENT/'results/policy_trials.csv')
    selected=selected[selected.active & (selected['set']=='S4') & selected.case_id.isin(CASES)].copy()
    assert len(selected)==4000 and not selected.duplicated(['case_id','set','trial_id']).any()
    assert selected.groupby('case_id').size().to_dict()==dict.fromkeys(CASES,1000)
    assert set(selected.true_h)=={'C','M'}
    configs=[next(c for c in prior['cases'] if c['id']==name) for name in CASES]
    mapping=[]; schedules={}; original_cache={}; case_info={}
    for case in configs:
        key=case['id']+'_active'
        tr=read_csv(PARENT/'dynamic_truth'/key/'truth.csv')
        intervals=read_csv(PARENT/'dynamic_truth'/key/'intervals.csv')
        with np.load(PARENT/'dynamic_truth'/key/'states.npz',allow_pickle=False) as a:
            idx=np.flatnonzero(a['time_min']==10.); assert len(idx)==1
            start=a['states'][idx[0]].copy()
        with np.load(PARENT/'dynamic_truth'/(case['id']+'_passive')/'states.npz',allow_pickle=False) as a:
            idx=np.flatnonzero(a['time_min']==10.); assert len(idx)==1
            assert np.array_equal(start,a['states'][idx[0]])
        assert np.all(tr.feed_gain==1.)
        demand=float(tr.iloc[0].demand_mol_min)
        before=intervals.loc[intervals.t_end<=10.+1e-10]
        prefix=account(before,demand)
        u0=float(tr.iloc[0].command_mol_min)
        uprobe=float(tr.loc[tr.time_min==10.,'command_next_mol_min'].iloc[0])
        case_info[case['id']]={'parent_key':key,'demand':demand,'prefix':prefix,
            'state10_sha256':hashlib.sha256(start.astype('<f8').tobytes()).hexdigest(),
            'nominal_mol_min':u0,'original_probe_mol_min':uprobe}
        for row in selected.loc[selected.case_id==case['id']].itertuples(index=False):
            oldkey=str(row.key)
            if oldkey not in original_cache:
                suffix=read_csv(PARENT/'dynamic_branches'/oldkey/'intervals.csv')
                leading=intervals.loc[intervals.t_end<=float(row.decision_min)+1e-10]
                full=pd.concat([leading,suffix],ignore_index=True)
                window=full.loc[full.t_start>=10.-1e-10]
                assert len(window)==210 and window.iloc[0].t_start==10. and window.iloc[-1].t_end==31.
                assert np.array_equal(window.actual_ethanol_start.to_numpy(),window.command_start_mol_min.to_numpy())
                assert np.array_equal(window.actual_ethanol_end.to_numpy(),window.command_end_mol_min.to_numpy())
                original_cache[oldkey]={'full':account(full,demand),'window':account(window,demand)}
            costs=original_cache[oldkey]
            budget=costs['window']['actual_ethanol_mol']
            constant=budget/21.
            assert .0018<=constant<=.0024, f'Command outside original bounds: {constant}'
            sid=case['id']+'_b'+hashlib.sha256(budget.hex().encode('ascii')).hexdigest()[:16]
            physical={'schedule_id':sid,'case_id':case['id'],'mode':case['mode'],'true_h':case['h'],
                'parent_key':key,'start_min':10.,'end_min':31.,'budget_10_31_mol':budget,
                'budget_float_hex':budget.hex(),'constant_command_mol_min':constant,
                'command_float_hex':constant.hex(),'state10_sha256':case_info[case['id']]['state10_sha256']}
            if sid in schedules: assert schedules[sid]==physical
            else: schedules[sid]=physical
            rec={'case_id':case['id'],'mode':case['mode'],'true_h':case['h'],'set':'S4','trial_id':int(row.trial_id),
                'call':row.call,'decision_min':float(row.decision_min),'original_command_index':int(row.command_index),
                'original_command_mol_min':float(row.command_mol_min),'original_branch_key':oldkey,
                'schedule_id':sid,'budget_10_31_mol':budget,'budget_float_hex':budget.hex(),
                'constant_command_mol_min':constant}
            for m in MEASURES:
                rec['diagnostic_'+m]=costs['full'][m]
                rec['diagnostic_10_31_'+m]=costs['window'][m]
                rec['prefix_0_10_'+m]=prefix[m]
                if hasattr(row,m):
                    rec['archived_reported_'+m]=float(getattr(row,m))
                    assert math.isclose(rec['diagnostic_'+m],float(getattr(row,m)),rel_tol=1e-9,abs_tol=1e-13)
            mapping.append(rec)
    plans=sorted(schedules.values(),key=lambda x:x['schedule_id'])
    write_csv(ROOT/'trial_schedule_map.csv',pd.DataFrame(mapping).sort_values(['case_id','trial_id']))
    write_json(ROOT/'schedule_inventory.json',{'schema':'ssmr.equal-ethanol-schedules.v1','created_utc':utc(),'schedules':plans,'case_info':case_info,
        'deduplication':'Only exact (case_id, IEEE754 budget.hex()) equality; no tolerance merge, rounding or clipping',
        'feasibility':{'all_within_original_bounds':True,'command_min':min(x['constant_command_mol_min'] for x in plans),
            'command_max':max(x['constant_command_mol_min'] for x in plans),'unique_schedules':len(plans),'paired_records':len(mapping)}})
    protocol={'schema':'ssmr.equal-ethanol-amendment.v1','created_utc':utc(),'date':'2026-09-30',
        'status':'Outcome-aware supplemental control comparison, frozen before new trajectories; not preregistration',
        'cases':configs,'sensor_sets':['S4'],'trials_per_case':1000,'new_noise_draws':0,
        'budget_window_min':[10.,31.],'reporting_window_min':[0.,31.],'constant_command_window_min':[10.,31.],
        'budget_definition':'math.fsum of actual-feed endpoint trapezoids from original active acquisition [10,original stop] and original chosen continuation [original stop,31]',
        'command_definition':'Exact float budget_10_31_mol / 21.0; no clipping, rounding or actuator-grid restriction',
        'bounds_mol_min':[.0018,.0024],'budget_atol_mol':1e-12,'budget_rtol':1e-12,
        'measures':MEASURES,'primary_contrast':'Original diagnostic sequence minus equal-ethanol constant-feed control',
        'interpretation':'Retrospective resource-budget-conditioned control; feed profile changes. Not uniquely diagnostic information, optimized input, all blind controls, deployable ex-ante policy, or economic superiority.',
        'initial_state':'Exact saved common active/passive physical state at minute10; absolute health time continues unchanged',
        'instrumentation':'Read-only solve_ivp wrapper stores supplied y0 and solver sol.y[:,0] for exact identity; dense exported first sample equality is reported separately',
        'original_export_qualification_retained':True,'unique_physical_schedules':len(plans),'paired_records':4000,
        'original_engine_sha256':sha(PARENT/'dynamics.py'),'original_protocol_sha256':sha(PARENT/'protocol.json'),
        'original_final_check_sha256':sha(PARENT/'checks/final_check.json'),'amendment_text_sha256':sha(ROOT/'PROTOCOL_AMENDMENT.txt'),
        'resource_settings':{'workers_max':2,'blas_threads':1},
        'scientific_settings':'Inherited unmodified from saved truth metadata and original dynamics.py; no recalibration or retuning'}
    write_json(ROOT/'protocol.json',protocol)
    excluded={'__pycache__','.research',ROOT.name}
    files={}
    for p in sorted(PARENT.rglob('*')):
        rel=p.relative_to(PARENT)
        if not p.is_file() or any(x in excluded for x in rel.parts) or p.name=='board.jsonl' or p.suffix in {'.tmp','.pyc'}: continue
        files[rel.as_posix()]={'sha256':sha(p),'bytes':p.stat().st_size}
    write_json(ROOT/'parent_inventory.json',{'created_utc':utc(),'root':str(PARENT),'files':files,
        'exclusions':['new amendment directory','.research','board.jsonl','__pycache__','*.tmp','*.pyc'],
        'scope':'Preserve all other prior revision and feed-only amendment files byte-for-byte'})
    print(json.dumps({'prepared':True,'unique_schedules':len(plans),'paired_records':len(mapping),
        'bounds':[min(x['constant_command_mol_min'] for x in plans),max(x['constant_command_mol_min'] for x in plans)],'parent_files':len(files)}))

def freeze():
    path=ROOT/'AMENDMENT_FREEZE.json'
    if path.exists(): raise RuntimeError('Refuse replacing amendment freeze')
    ck=ROOT/'checks/CHECK_FREEZE.json'
    assert ck.exists(), 'Independent checker must freeze first'
    paths=['protocol.json','PROTOCOL_AMENDMENT.txt','prepare_equal_ethanol.py','run_equal_ethanol.py','parent_inventory.json','schedule_inventory.json','trial_schedule_map.csv','checks/CHECK_FREEZE.json']
    for p in (ROOT/'checks').glob('*'):
        if p.is_file() and p.suffix in {'.py','.txt'}: paths.append(p.relative_to(ROOT).as_posix())
    for rel,rec in js(ROOT/'parent_inventory.json')['files'].items(): assert sha(PARENT/rel)==rec['sha256'], rel
    write_json(path,{'schema':'ssmr.equal-ethanol-freeze.v1','created_utc':utc(),'files':{p:sha(ROOT/p) for p in sorted(set(paths))},
        'scope':'Freeze before new equal-ethanol integrations; original outcomes already known; no favorable result required'})
    print(json.dumps({'frozen':True,'sha256':sha(path),'files':len(set(paths))}))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','freeze']);args=p.parse_args()
    prepare() if args.action=='prepare' else freeze()
