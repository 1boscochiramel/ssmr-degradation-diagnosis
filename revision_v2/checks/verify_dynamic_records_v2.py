"""Independent integrity/arithmetic checks for dynamic-truth.v1 records.

Provisional until revision protocol freeze. Does not reimplement the reactor
equations or claim a second independent ODE simulation.
"""
from pathlib import Path
import argparse,hashlib,json
import numpy as np
import pandas as pd
from scipy.io import loadmat
from reference_math import physical_intervals

FEATURES=['H2_mol_min','T_out_K','waste_m3_min','y_H2','y_CH4','y_CO','y_CO2']
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def states_sha(x):return hashlib.sha256(np.asarray(x,dtype='<f8').tobytes()).hexdigest()

def audit_tree(root,more_roots=()):
    issues=[];records=[];parents={};pending=[]
    def need(ok,label):
        if not ok:issues.append(label)
    def close(a,b,label,atol=1e-13,rtol=1e-9):
        a=np.asarray(a);b=np.asarray(b)
        need(a.shape==b.shape and np.allclose(a,b,atol=atol,rtol=rtol,equal_nan=False),label)
    paths=[]
    for p in sorted(p for folder in [root,*more_roots] for p in Path(folder).rglob('metadata.json')):
        meta=json.loads(p.read_text())
        if meta.get('schema') in ['ssmr.dynamic-truth.v1','ssmr.dynamic-continuation.v1']:paths.append((p,meta))
    need(bool(paths),'No dynamic records')
    for p,meta in paths:
        label=str(p.parent);tr=pd.read_csv(p.parent/'truth.csv',float_precision='round_trip');iv=pd.read_csv(p.parent/'intervals.csv',float_precision='round_trip')
        with np.load(p.parent/'states.npz') as z:ts=z['time_min'].copy();xs=z['states'].copy()
        need(xs.shape==(len(tr),800),label+'/state shape');need(np.isfinite(xs).all(),label+'/finite states')
        close(ts,tr.time_min.to_numpy(),label+'/state times')
        need(states_sha(xs)==meta['state_sha256'],label+'/state hash')
        for name,h in meta['output_hashes'].items():need(sha(p.parent/name)==h,label+'/output hash/'+name)
        for name,h in meta['source_hashes'].items():need(sha(name)==h,label+'/source hash/'+name)
        dt=float(meta['settings']['sample_min']);close(np.diff(ts),np.full(len(ts)-1,dt),label+'/uniform sampling')
        need(np.isfinite(tr.select_dtypes('number').to_numpy()).all(),label+'/finite trace')
        need(np.isfinite(iv.select_dtypes('number').to_numpy()).all(),label+'/finite intervals')
        close(iv.t_start.to_numpy(),ts[:-1],label+'/interval starts');close(iv.t_end.to_numpy(),ts[1:],label+'/interval ends')
        sc=meta['scenario'];t=tr.time_min.to_numpy();ac=np.ones(len(t));am=ac.copy();fg=ac.copy();bias=np.zeros(len(t))
        h=sc['hypothesis']
        if h in ['C','M','F']:
            y=np.minimum(1,sc['theta10']*np.exp(-sc['rate_per_min']*(t-10)))
            if h=='C':ac=y
            elif h=='M':am=y
            else:fg=y
        elif h=='S':bias=sc['theta10']+sc['sensor_slope_per_min']*(t-10)
        elif h=='CM':
            ac=np.minimum(1,sc['theta_c10']*np.exp(-sc['rate_c_per_min']*(t-10)))
            am=np.minimum(1,sc['theta_m10']*np.exp(-sc['rate_m_per_min']*(t-10)))
        else:need(h=='H',label+'/known hypothesis')
        for col,v in [('a_c',ac),('a_m',am),('feed_gain',fg),('sensor_bias_mol_min',bias)]:close(tr[col].to_numpy(),v,label+'/'+col)
        for f in FEATURES:close(tr['observed_'+f].to_numpy(),tr['true_'+f].to_numpy()+(bias if f=='H2_mol_min' else 0),label+'/deterministic observation/'+f)
        close(tr.actual_ethanol_mol_min.to_numpy(),tr.command_mol_min.to_numpy()*fg,label+'/actual feed')
        need(bool(np.all((tr.command_mol_min>=.0018-1e-12)&(tr.command_mol_min<=.0024+1e-12))),label+'/command bounds')
        segments=meta['segments'];expected_command=np.empty(len(t));expected_next=np.empty(len(t));interval_command=np.empty(len(iv))
        for i,ti in enumerate(t):
            matches=[x for x in segments if x[0]-1e-10<=ti<=x[1]+1e-10]
            need(bool(matches),label+'/covered time')
            if matches:expected_command[i]=matches[0][2];expected_next[i]=matches[-1][2]
        for i,ti in enumerate(iv.t_start):
            matches=[x for x in segments if x[0]-1e-10<=ti<x[1]-1e-10]
            need(len(matches)==1,label+'/covered interval')
            if matches:interval_command[i]=matches[0][2]
        close(tr.command_mol_min.to_numpy(),expected_command,label+'/left event command')
        close(tr.command_next_mol_min.to_numpy(),expected_next,label+'/next event command')
        close(iv.commanded_ethanol_mol_min.to_numpy(),interval_command,label+'/interval command')
        close(iv.actual_ethanol_start.to_numpy(),interval_command*fg[:-1],label+'/actual interval start')
        close(iv.actual_ethanol_end.to_numpy(),interval_command*fg[1:],label+'/actual interval end')
        # H2 depends on the continuous state/health and agrees on either side
        # of a feed command event under the pinned permeation equation.
        close(iv.H2_start_mol_min.to_numpy(),tr.true_H2_mol_min.to_numpy()[:-1],label+'/H2 interval start')
        close(iv.H2_end_mol_min.to_numpy(),tr.true_H2_mol_min.to_numpy()[1:],label+'/H2 interval end')
        demand=tr.demand_mol_min.to_numpy();dts=iv.t_end.to_numpy()-iv.t_start.to_numpy()
        calc=physical_intervals(iv.t_start,iv.t_end,interval_command,iv.actual_ethanol_start,iv.actual_ethanol_end,iv.H2_start_mol_min,iv.H2_end_mol_min,demand[:-1],demand[1:])
        for field,key in [('commanded_ethanol_mol','command_ethanol_mol'),('actual_ethanol_mol','actual_ethanol_mol'),('H2_produced_mol','H2_produced_mol'),('H2_demand_mol','H2_demand_mol'),('H2_shortfall_mol','H2_shortfall_mol')]:close(np.asarray(float(iv[field].sum())),np.asarray(calc[key]),label+'/integral/'+field)
        close(iv.commanded_ethanol_mol.to_numpy(),interval_command*dts,label+'/interval feed exact')
        health_flag=(ac>=.4)&(ac<=1)&(am>=.4)&(am<=1);feed_flag=(tr.actual_ethanol_mol_min>=.0018-1e-12)&(tr.actual_ethanol_mol_min<=.0024+1e-12)
        need(np.array_equal(tr.health_in_map_domain.to_numpy(),health_flag),label+'/health domain flags');need(np.array_equal(tr.feed_in_map_domain.to_numpy(),feed_flag.to_numpy()),label+'/feed domain flags')
        if meta['schema']=='ssmr.dynamic-truth.v1':
            initial=loadmat(meta['initial_condition'])['x0c'].ravel()
            pre=meta.get('preconditioning')
            if pre is None:
                need(meta.get('initialization')=='healthy_ic_stress',label+'/explicit unconditioned stress label')
                close(xs[0],initial,label+'/unmodified initial condition',atol=0,rtol=0)
            else:
                pretr=pd.read_csv(p.parent/'precondition_trace.csv',float_precision='round_trip')
                with np.load(p.parent/'precondition_states.npz') as zz:px=zz['states'].copy();pt=zz['time_min'].copy()
                close(pt,pretr.precondition_time_min.to_numpy(),label+'/precondition times')
                close(px[0],initial,label+'/precondition starts at source IC',atol=0,rtol=0)
                close(px[-1],xs[0],label+'/precondition exact state0',atol=0,rtol=0)
                need(states_sha(px[0])==pre['starter_state_sha256'],label+'/precondition starter hash')
                need(states_sha(px[-1])==pre['state0_sha256'],label+'/precondition state0 hash')
                need(pre['physical_schedule_time_held_min']==0,label+'/precondition frozen time')
                for key,value in [('fixed_a_c',ac[0]),('fixed_a_m',am[0]),('fixed_feed_gain',fg[0])]:close(np.asarray(pre[key]),np.asarray(value),label+'/precondition/'+key)
                need(pre['maximum_minutes']==20 and pre['minimum_minutes']==2 and pre['comparison_spacing_min']==.5,label+'/precondition limits')
                atol_ref=dict(H2_mol_min=1e-12,T_out_K=1e-5,waste_m3_min=1e-12,y_H2=1e-8,y_CH4=1e-8,y_CO=1e-8,y_CO2=1e-8)
                need(pre['relative_tolerance']==1e-6 and pre['absolute_tolerances']==atol_ref,label+'/precondition frozen gates')
                first_pass=None
                for minute in range(2,int(round(pt[-1]))+1):
                    mid=pretr[np.isclose(pt,minute-.5)].iloc[0];end=pretr[np.isclose(pt,minute)].iloc[0]
                    dif=np.asarray([abs(end[f]-mid[f]) for f in FEATURES]);lim=np.asarray([atol_ref[f]+1e-6*max(abs(end[f]),abs(mid[f])) for f in FEATURES])
                    if np.all(dif<=lim):first_pass=minute;break
                need(first_pass is not None and first_pass==pre['minutes'] and first_pass==pt[-1],label+'/precondition first passing minute')
                need(pre['converged'] is True and pre['status']=='PASS',label+'/precondition completed')
                mid=pretr.iloc[-2];end=pretr.iloc[-1]
                for f in FEATURES:
                    close(np.asarray(pre['final_comparisons'][f]['absolute_difference']),np.asarray(abs(end[f]-mid[f])),label+'/precondition final difference/'+f)
                    close(np.asarray(pre['final_comparisons'][f]['limit']),np.asarray(atol_ref[f]+1e-6*max(abs(end[f]),abs(mid[f]))),label+'/precondition final limit/'+f)
            need(states_sha(xs[0])==meta['physical_state0_sha256'],label+'/physical state0 hash')
            parents[(meta['state_sha256'],json.dumps(sc,sort_keys=True))]=(ts,xs,sc)
        else:pending.append((label,meta,xs[0]))
        records.append({'folder':label,'schema':meta['schema'],'hypothesis':h,'mode':sc['mode'],'samples':len(tr),'integrals':calc,'health_outside_map_samples':int((~health_flag).sum()),'actual_feed_outside_map_samples':int((~feed_flag).sum())})
    for label,meta,x0 in pending:
        parent=parents.get((meta['parent_state_sha256'],json.dumps(meta['scenario'],sort_keys=True)));need(parent is not None,label+'/parent record present')
        if parent is not None:
            ts,xs,sc=parent;ix=np.flatnonzero(np.isclose(ts,meta['parent_decision_min'],atol=1e-12,rtol=0));need(len(ix)==1,label+'/parent time match')
            if len(ix)==1:close(x0,xs[ix[0]],label+'/exact branch state',atol=0,rtol=0)
            need(sc==meta['scenario'],label+'/unchanged absolute-time scenario')
        need(states_sha(x0)==meta['branch_initial_state_sha256'],label+'/branch hash')
    return {'pass':not issues,'issues':issues,'records':records,'scope':'Independent saved-state/source/command/covariate/physical-accounting audit; not an independent reactor-equation solver.'}

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,required=True);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args();out=audit_tree(a.root)
    a.out.write_text(json.dumps(out,indent=2));print(json.dumps({'pass':out['pass'],'issues':out['issues'],'records':len(out['records'])},indent=2));raise SystemExit(not out['pass'])
