"""Analytic test of pre-evaluation target amendment; no policy-run outcomes."""
from pathlib import Path
import os
for name in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS']:os.environ[name]='1'
import hashlib,json,sys
import numpy as np
HERE=Path(__file__).resolve().parent;ROOT=HERE.parent;sys.path.insert(0,str(ROOT))
import revision_model as model
import revision_policy as target
from reference_math import physical_intervals
issues=[];rows=[]
for mode in [1,2]:
    for active in [False,True]:
        bank=model.DiagnosticBank(mode,active)
        indices=[]
        for h in model.HYP:
            pair=[0,0] if h=='S' else [1,0]
            ix=np.flatnonzero(np.all(bank.params[h]==np.asarray(pair),axis=1))
            if len(ix)!=1:raise AssertionError(f'No unique zero-fault template for {h}')
            indices.append(ix[0])
        for look in [16.,21.]:
            for hi,h in enumerate(model.HYP):
                alive=np.zeros(5,dtype=bool);alive[hi]=True
                command_index,cannot=target.select_command(bank,look,alive,indices)
                row=dict(mode=mode,active=active,look=look,h=h,command_index=command_index,predicted_infeasible=cannot)
                if command_index!=0 or cannot:issues.append(row)
                rows.append(row)
            ci,cannot=target.select_command(bank,look,np.ones(5,dtype=bool),indices)
            if ci!=0 or cannot:issues.append(dict(mode=mode,active=active,look=look,mixed_zero_fault=True))
base=physical_intervals([0],[10],[.0021],[.0021],[.0021],[.0002],[.0002],[.0002],[.0002])
other=physical_intervals([0],[10],[.0022],[.0022],[.0022],[.0002],[.0002],[.0002],[.0002])
delta=other['actual_ethanol_mol']-base['actual_ethanol_mol']
if abs(delta-.001)>1e-14:issues.append('Same-action label must not erase feed-command difference')
out={'pass':not issues,'issues':issues,'zero_fault_checks':rows,'physical_command_difference_mol':delta,
     'policy_sha256':hashlib.sha256((ROOT/'revision_policy.py').read_bytes()).hexdigest(),
     'amendment_sha256':hashlib.sha256((ROOT/'POLICY_AMENDMENT.txt').read_bytes()).hexdigest(),
     'scope':'Pre-evaluation analytic checks only; no stochastic/physical policy evaluation results used.'}
(HERE/'policy_amendment_check.json').write_text(json.dumps(out,indent=2));print(json.dumps({k:v for k,v in out.items() if k!='zero_fault_checks'},indent=2));raise SystemExit(bool(issues))
