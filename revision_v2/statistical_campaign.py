"""Calibrate and evaluate the frozen diagnostic/command policy on new ODE truth."""
from pathlib import Path
import os
for key in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):
    os.environ[key]='1'
import argparse, datetime, hashlib, json, platform
import numpy as np
import pandas as pd
from scipy.stats import beta
import revision_model as rm
from revision_policy import select_command

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'results'
SHA=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()

def write_json(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix(path.suffix+'.tmp')
    temp.write_text(json.dumps(data,indent=2,allow_nan=False)+'\n',encoding='utf-8');temp.replace(path)

def verify_freeze():
    freeze=json.loads((ROOT/'PROTOCOL_FREEZE.json').read_text())
    for name,h in freeze['files'].items():
        if SHA(ROOT/name)!=h:raise RuntimeError(f'Frozen file changed: {name}')
    amendment=json.loads((ROOT/'POLICY_AMENDMENT_FREEZE.json').read_text())
    for name,h in amendment['files'].items():
        if SHA(ROOT/name)!=h:raise RuntimeError(f'Frozen amendment changed: {name}')
    return json.loads((ROOT/'protocol.json').read_text())

def load_frame(case,active):
    directory=ROOT/'dynamic_truth'/f'{case["id"]}_{"active" if active else "passive"}'
    path=directory/'truth.csv'
    if not path.exists():raise RuntimeError(f'Required fresh dynamic truth missing: {path}')
    tr=pd.read_csv(path,float_precision='round_trip')
    for f in rm.FEATURES:tr[f]=tr['observed_'+f]
    return tr,directory

def bank_id(mode,active):return f'm{mode}_{"active" if active else "passive"}'

def export_bank(bank):
    ident=bank_id(bank.mode,bank.active); dest=OUT/'banks'/ident
    dest.mkdir(parents=True,exist_ok=True)
    data={'params_'+h:bank.params[h] for h in rm.HYP}; designs={}
    for (look,s),(L,origin,white,info,cov) in bank.cache.items():
        tag=f'{s}_{int(look)}'; data['covariance_'+tag]=cov
        for h in rm.HYP:data[f'vectors_{tag}_{h}']=white[h]@L.T+origin
        designs[tag]=info
    np.savez_compressed(dest/'bank.npz',**data)
    write_json(dest/'bank.json',dict(mode=bank.mode,active=bank.active,hypotheses=list(rm.HYP),
               npz_sha256=SHA(dest/'bank.npz'),designs=designs,model_sha256=SHA(ROOT/'revision_model.py')))

def batch(case,active,phase,bank,protocol,stress_index=None,noise_kwargs=None):
    stress_index=int(stress_index) if stress_index is not None else None
    extra=0 if stress_index is None else stress_index*1000
    seed=protocol['seed_base']+case['index']*100000+protocol['phase_offsets'][phase]+extra
    n=protocol['n_calibration'] if phase=='calibration' else protocol['n_evaluation'] if phase=='evaluation' else protocol['n_stress']
    stem=f'{case["id"]}_{"active" if active else "passive"}_{phase}'+('' if stress_index is None else f'_{stress_index}')
    directory=OUT/'batches';directory.mkdir(parents=True,exist_ok=True)
    meta_path=directory/(stem+'.json');npz_path=directory/(stem+'.npz')
    frame,truth_dir=load_frame(case,active)
    if meta_path.exists():
        meta=json.loads(meta_path.read_text())
        assert meta['npz_sha256']==SHA(npz_path) and meta['truth_sha256']==SHA(truth_dir/'truth.csv')
        assert meta['model_sha256']==SHA(ROOT/'revision_model.py')
        return meta
    summaries,exemplar=rm.draw_summaries(frame,case['mode'],n,seed,**(noise_kwargs or {}))
    values={'trial_id':np.arange(n,dtype=np.int64)}
    for s in rm.SETS:
        scores=[];indices=[]
        for look in rm.LOOKS:
            obs=summaries[(look,s)];score,idx=bank.score(obs,look,s)
            values[f'obs_{s}_{int(look)}']=obs;scores.append(score);indices.append(idx)
        values['scores_'+s]=np.stack(scores,1);values['indices_'+s]=np.stack(indices,1)
    for f,obs in exemplar.items():
        for k,v in obs.items():values[f'raw0_{f}_{k}']=v
    np.savez_compressed(npz_path,**values)
    meta=dict(case_id=case['id'],mode=case['mode'],true_hypothesis=case['h'],category=case['category'],
              active=bool(active),phase=phase,stress_index=stress_index,seed=seed,n=n,noise_kwargs=noise_kwargs or {},
              truth_dir=str(truth_dir.relative_to(ROOT)),truth_sha256=SHA(truth_dir/'truth.csv'),
              npz_path=str(npz_path.relative_to(ROOT)),npz_sha256=SHA(npz_path),
              model_sha256=SHA(ROOT/'revision_model.py'),protocol_sha256=SHA(ROOT/'protocol.json'),
              pipeline_sha256=SHA(__file__),policy_sha256=SHA(ROOT/'revision_policy.py'),
              rng='numpy.random.default_rng/PCG64',numpy_version=np.__version__,
              created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
    write_json(meta_path,meta)
    print(f'{phase} {stem} n={n}',flush=True)
    return meta

def calibrate(protocol):
    if not (ROOT/'checks/INTEGRATION_FREEZE.json').exists():
        raise RuntimeError('Independent integration check must be frozen before stochastic scoring.')
    if (OUT/'EVALUATION_FREEZE.json').exists():
        seal=json.loads((OUT/'EVALUATION_FREEZE.json').read_text())
        assert seal['calibration_sha256']==SHA(OUT/'calibration.json')
        print('Calibration already sealed for evaluation; retained unchanged.',flush=True)
        return
    banks={(m,a):rm.DiagnosticBank(m,a) for m in (1,2) for a in (False,True)}
    for b in banks.values():export_bank(b)
    strata=[]; thresholds={}
    for case in protocol['cases']:
        if case['category']!='covered_grid':continue
        for active in (False,True):
            meta=batch(case,active,'calibration',banks[(case['mode'],active)],protocol)
            data=np.load(ROOT/meta['npz_path'])
            for s in rm.SETS:
                hi=rm.HYP.index(case['h']); seqmax=data['scores_'+s][:,:,hi].max(1)
                q=rm.rank_threshold(seqmax,protocol['alpha'])
                key=f'{bank_id(case["mode"],active)}_{s}'
                if key not in thresholds:thresholds[key]={h:None for h in rm.HYP}
                old=thresholds[key][case['h']]
                thresholds[key][case['h']]=q if old is None else max(old,q)
                strata.append(dict(case_id=case['id'],mode=case['mode'],active=active,set=s,h=case['h'],n=meta['n'],
                                   k=int(np.ceil((meta['n']+1)*(1-protocol['alpha']))),threshold=q,npz_path=meta['npz_path']))
    for key,ths in thresholds.items():
        mode=int(key[1]);assert all(ths[h] is not None for h in protocol['support'][str(mode)])
    write_json(OUT/'calibration.json',dict(alpha=protocol['alpha'],thresholds=thresholds,strata=strata,
              support=protocol['support'],protocol_sha256=SHA(ROOT/'protocol.json'),
              method='Per-stratum order statistic of maximum score over looks; maximum across finite covered truth strata.',
              created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat()))

def interval(k,n):
    return (0. if k==0 else float(beta.ppf(.025,k,n-k+1)),1. if k==n else float(beta.ppf(.975,k+1,n-k)))

def evaluate(protocol):
    calibration=json.loads((OUT/'calibration.json').read_text())
    assert calibration['protocol_sha256']==SHA(ROOT/'protocol.json')
    # Persist threshold hash before generating independent evaluation data.
    seal=OUT/'EVALUATION_FREEZE.json'
    if not seal.exists():write_json(seal,dict(calibration_sha256=SHA(OUT/'calibration.json'),
                        created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat()))
    assert json.loads(seal.read_text())['calibration_sha256']==SHA(OUT/'calibration.json')
    banks={(m,a):rm.DiagnosticBank(m,a) for m in (1,2) for a in (False,True)}
    summaries=[]; policy_rows=[]; all_meta=[]
    for case in protocol['cases']:
        specs=[('evaluation',None,{},case['category'])]
        if case['policy']:
            for i,st in enumerate(protocol['observation_stress']):
                specs.append(('stress',i,{k:v for k,v in st.items() if k!='name'},st['name']))
        for active in (False,True):
            bank=banks[(case['mode'],active)]
            for phase,si,kw,group in specs:
                meta=batch(case,active,phase,bank,protocol,si,kw);all_meta.append(meta)
                d=np.load(ROOT/meta['npz_path']); decisions={}
                for s in rm.SETS:
                    key=f'{bank_id(case["mode"],active)}_{s}'
                    q=np.array([calibration['thresholds'][key][h] if calibration['thresholds'][key][h] is not None else -np.inf for h in rm.HYP])
                    calls,times,alive=rm.decide(d['scores_'+s],q)
                    n=meta['n']; supported=case['h'] in protocol['support'][str(case['mode'])] and group!='out_of_family'
                    singleton=np.isin(calls,rm.HYP);correct=singleton & (calls==case['h'])
                    wrong=singleton & (calls!=case['h'])
                    stop_index=np.where(times==16.,0,1)
                    rejected=(~alive[np.arange(n),stop_index,rm.HYP.index(case['h'])]) if supported else None
                    potential_rejected=(~alive[:,-1,rm.HYP.index(case['h'])]) if supported else None
                    row=dict(case_id=case['id'],mode=case['mode'],true_h=case['h'],nominal_drop=case['drop'],
                             active=active,set=s,group=group,phase=phase,n=n,supported_label=supported,
                             true_rejected=int(rejected.sum()) if supported else None,
                             potential_true_rejected_at21=int(potential_rejected.sum()) if supported else None,
                             correct_singleton=int(correct.sum()),wrong_singleton=int(wrong.sum()),
                             inconclusive=int((calls=='INCONCLUSIVE').sum()),incompatible=int((calls=='MODEL_INCOMPATIBLE').sum()),
                             early_singleton=int((singleton&(times==16.)).sum()),
                             median_diagnosis_time_min=float(np.median(times[singleton])) if singleton.any() else None,
                             median_correct_time_min=float(np.median(times[correct])) if correct.any() else None)
                    for field in ('true_rejected','correct_singleton','wrong_singleton','inconclusive','incompatible'):
                        k=row[field]
                        row[field+'_rate']=k/n if k is not None else None
                        lo,hi=interval(k,n) if k is not None else (None,None)
                        row[field+'_ci_lo']=lo;row[field+'_ci_hi']=hi
                    summaries.append(row)
                    decisions['calls_'+s]=calls;decisions['times_'+s]=times;decisions['alive_'+s]=alive
                    if case['policy'] and phase=='evaluation':
                        # Cache repeated fitted configurations; policy never reads true labels/states.
                        cache={}
                        for i in range(n):
                            li=0 if times[i]==16. else 1;mask=alive[i,li];idx=d['indices_'+s][i,li]
                            signature=(li,tuple(mask),tuple(idx))
                            if signature not in cache:cache[signature]=select_command(bank,float(times[i]),mask,idx)
                            ui,cannot=cache[signature]
                            policy_rows.append(dict(case_id=case['id'],mode=case['mode'],true_h=case['h'],active=active,
                                set=s,trial_id=i,call=calls[i],decision_min=float(times[i]),command_index=int(ui),
                                command_mol_min=float(rm.command_grid(case['mode'])[ui]),predicted_infeasible=bool(cannot)))
                decision_path=ROOT/meta['npz_path'].replace('.npz','_decisions.npz')
                np.savez_compressed(decision_path,**decisions)
    pd.DataFrame(summaries).to_csv(OUT/'diagnosis_summary.csv',index=False)
    pd.DataFrame(policy_rows).to_csv(OUT/'policy_decisions.csv',index=False)
    write_json(OUT/'batch_inventory.json',all_meta)
    print('Held-out evaluation complete; thresholds unchanged.',flush=True)

def policy_summary(protocol):
    decisions=pd.read_csv(OUT/'policy_decisions.csv')
    branches=pd.read_csv(ROOT/'branch_costs.csv')
    # Engine schema is explicit and adapted here before evaluation; no action outcomes fitted.
    keys=['case_id','active','decision_min','command_index']
    if any(k not in branches for k in keys):raise RuntimeError('Branch-cost schema mismatch: '+repr(branches.columns.tolist()))
    joined=decisions.merge(branches,on=keys,how='left',validate='many_to_one',suffixes=('','_truth'))
    measures=['H2_shortfall_mol','actual_ethanol_mol','commanded_ethanol_mol','H2_produced_mol']
    if joined[measures].isna().any().any():raise RuntimeError('Missing selected action trajectory; never silently drop a trial.')
    joined.to_csv(OUT/'policy_trials.csv',index=False)
    grouped=joined.groupby(['case_id','mode','true_h','active','set'],dropna=False)
    summary=grouped[measures].agg(['mean','std','min','max']).reset_index()
    summary.columns=['_'.join(x).strip('_') for x in summary.columns]
    summary.to_csv(OUT/'policy_summary.csv',index=False)
    paired=joined[joined.active==True].merge(joined[joined.active==False],on=['case_id','set','trial_id'],suffixes=('_active','_passive'),validate='one_to_one')
    for f in measures:paired[f+'_difference']=paired[f+'_active']-paired[f+'_passive']
    diffs=[f+'_difference' for f in measures]
    diff_summary=paired.groupby(['case_id','set'])[diffs].agg(['mean','std','min','max']).reset_index()
    diff_summary.columns=['_'.join(x).strip('_') for x in diff_summary.columns]
    diff_summary.to_csv(OUT/'policy_paired_differences.csv',index=False)
    diagnosis=pd.read_csv(OUT/'diagnosis_summary.csv')
    core=diagnosis[diagnosis.group=='covered_grid']
    summary_json=dict(schema='ssmr.revision.summary.v2',complete=True,
        protocol_sha256=SHA(ROOT/'protocol.json'),design_freeze_sha256=SHA(ROOT/'PROTOCOL_FREEZE.json'),
        policy_amendment_sha256=SHA(ROOT/'POLICY_AMENDMENT_FREEZE.json'),
        calibration_sha256=SHA(OUT/'calibration.json'),
        dynamic_status_sha256=SHA(ROOT/'dynamic_status.json'),
        diagnosis_rows=len(diagnosis),covered_grid_cells=len(core),policy_trial_rows=len(joined),
        maximum_covered_true_rejection_rate=float(core.true_rejected_rate.max()),
        maximum_covered_wrong_singleton_rate=float(core.wrong_singleton_rate.max()),
        maximum_covered_true_rejection_upper95=float(core.true_rejected_ci_hi.max()),
        minimum_covered_correct_singleton_rate=float(core.correct_singleton_rate.min()),
        created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        interpretation='Conditional simulation results under declared finite scenarios, observation assumptions and policy. Pointwise binomial intervals; paired policies share noise draws. No economic payback, laboratory accuracy or universal nuisance-space calibration claim.')
    summary_json['files']={p.name:SHA(p) for p in [OUT/'diagnosis_summary.csv',OUT/'policy_summary.csv',OUT/'policy_trials.csv',OUT/'policy_paired_differences.csv',OUT/'calibration.json']}
    write_json(OUT/'summary.json',summary_json)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('phase',choices=['calibrate','evaluate','policy','all']);args=parser.parse_args()
    protocol=verify_freeze();OUT.mkdir(exist_ok=True)
    write_json(OUT/'environment.json',dict(python=platform.python_version(),numpy=np.__version__,
               source_manifest_sha256=SHA(ROOT/'SOURCE_MANIFEST.json'),pipeline_sha256=SHA(__file__)))
    if args.phase in ('calibrate','all'):calibrate(protocol)
    if args.phase in ('evaluate','all'):evaluate(protocol)
    if args.phase in ('policy','all'):policy_summary(protocol)

if __name__=='__main__':main()
