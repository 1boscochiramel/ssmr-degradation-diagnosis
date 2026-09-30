"""Execute only the dated feed-only comparator with the original frozen model."""
import os
for name in ['OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS']:
    os.environ[name]='1'
from pathlib import Path
import sys
import json
import hashlib
import argparse
from datetime import datetime, timezone
from concurrent.futures import ProcessPoolExecutor
import time
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parent
PARENT=ROOT.parent
sys.path.insert(0,str(PARENT))
import dynamics
from dynamic_campaign import load_truth, verify_saved

def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def utc():return datetime.now(timezone.utc).isoformat()
def write_json(path,obj):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix(path.suffix+'.tmp')
    temp.write_text(json.dumps(obj,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    temp.replace(path)
def write_csv(path,frame):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix(path.suffix+'.tmp')
    frame.to_csv(temp,index=False,float_format='%.17g');temp.replace(path)
def verify_freeze():
    frozen=json.loads((ROOT/'AMENDMENT_FREEZE.json').read_text())
    for rel,value in frozen['files'].items():
        if sha(ROOT/rel)!=value:raise RuntimeError('Amendment freeze changed: '+rel)
    inv=json.loads((ROOT/'parent_inventory.json').read_text())
    for rel,value in inv['files'].items():
        if sha(PARENT/rel)!=value['sha256']:raise RuntimeError('Original evidence changed: '+rel)
    return frozen
def work(args):
    case,end,protocol=args
    key=f"{case['id']}_t{end:g}"
    folder=ROOT/'branches'/key
    if folder.exists():raise RuntimeError('New execution refuses existing output: '+str(folder))
    started=utc();clock=time.perf_counter()
    parent_key=case['id']+'_active'
    truth=load_truth(PARENT/'dynamic_truth'/parent_key)
    u=float(protocol['nominal_mol_min'][str(case['mode'])])
    branch=dynamics.continue_truth(truth,end,u,
             horizon_end_min=protocol['horizon_end_min'],output_dir=folder)
    record={'case_id':case['id'],'mode':case['mode'],'true_h':case['h'],
        'pulse_end_min':end,'pulse_start_min':protocol['pulse_start_min'],
        'post_pulse_command_mol_min':u,'parent_key':parent_key,
        'branch_path':folder.relative_to(ROOT).as_posix(),
        'archived_branch_path':f'dynamic_branches/{parent_key}_t{end:g}_u0',
        **dynamics.policy_cost(truth,branch)}
    write_json(folder/'amendment_execution.json',{
        'started_utc':started,'completed_utc':utc(),'wall_seconds':time.perf_counter()-clock,
        'spec_sha256':sha(ROOT/'amendment_protocol.json'),
        'freeze_sha256':sha(ROOT/'AMENDMENT_FREEZE.json'),
        'mode':'Fresh continuation integration; original physical prefix reused',
        'arm':record})
    print(json.dumps({'arm':key,'status':'integrated','wall_seconds':time.perf_counter()-clock}),flush=True)
    return record

def summarize(protocol,arms):
    original=pd.read_csv(PARENT/'results/policy_trials.csv',float_precision='round_trip')
    active=original[original.active].copy()
    assert len(active)==len(protocol['cases'])*len(protocol['sensor_sets'])*protocol['trials_per_cell']
    measures=protocol['measures']
    keep=['case_id','mode','true_h','set','trial_id','call','decision_min','command_index','command_mol_min']
    left=active[keep+measures].rename(columns={m:'diagnostic_'+m for m in measures})
    right=arms[['case_id','pulse_end_min','branch_path']+measures].rename(
        columns={'pulse_end_min':'decision_min',**{m:'feed_only_'+m for m in measures}})
    paired=left.merge(right,on=['case_id','decision_min'],validate='many_to_one',how='left')
    if paired.isna().any().any():raise RuntimeError('Incomplete paired comparator')
    for m in measures:paired['difference_'+m]=paired['diagnostic_'+m]-paired['feed_only_'+m]
    write_csv(ROOT/'outputs/paired_trials.csv',paired)
    summary=[]
    for (case_id,s),group in paired.groupby(['case_id','set'],sort=True):
        row={'case_id':case_id,'mode':int(group.iloc[0]['mode']),'true_h':group.iloc[0]['true_h'],
             'set':s,'trials':len(group),'stop16_count':int((group.decision_min==16).sum()),
             'stop21_count':int((group.decision_min==21).sum()),
             'non_nominal_action_count':int((group.command_index!=0).sum())}
        for m in measures:
            for kind in ['diagnostic','feed_only','difference']:
                a=group[kind+'_'+m].to_numpy()
                for stat,value in [('mean',np.mean(a)),('sd',np.std(a,ddof=1)),('min',np.min(a)),('max',np.max(a))]:
                    row[kind+'_'+m+'_'+stat]=float(value)
        summary.append(row)
    write_csv(ROOT/'outputs/paired_summary.csv',pd.DataFrame(summary))
    output_paths=['outputs/feed_only_arm_costs.csv','outputs/paired_trials.csv','outputs/paired_summary.csv']
    write_json(ROOT/'outputs/summary.json',{
       'complete':True,'completed_utc':utc(),'physical_arms':len(arms),
       'paired_trial_rows':len(paired),'paired_groups':len(summary),
       'freeze_sha256':sha(ROOT/'AMENDMENT_FREEZE.json'),
       'files':{p:sha(ROOT/p) for p in output_paths},
       'interpretation':protocol['interpretation'],
       'original_results_unchanged':True})

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--workers',type=int,choices=[1,2],default=2)
    args=parser.parse_args()
    freeze=verify_freeze()
    if (ROOT/'outputs/summary.json').exists():raise RuntimeError('Completed evidence already exists; do not overwrite')
    protocol=json.loads((ROOT/'amendment_protocol.json').read_text())
    tasks=[(c,float(t),protocol) for c in protocol['cases'] for t in protocol['pulse_end_min']]
    write_json(ROOT/'run_status.json',{'status':'running','started_utc':utc(),'tasks':len(tasks)})
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        arms=list(pool.map(work,tasks))
    arms=pd.DataFrame(arms)
    write_csv(ROOT/'outputs/feed_only_arm_costs.csv',arms)
    summarize(protocol,arms)
    verify_freeze()
    write_json(ROOT/'run_status.json',{'status':'complete','completed_utc':utc(),'tasks':len(tasks)})
    print(json.dumps({'status':'complete','arms':len(arms)}),flush=True)

if __name__=='__main__':main()
