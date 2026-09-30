"""Audit bounded-feed policy and whole-horizon physical outcomes independently."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
import integration_reference as ref
from reference_math import physical_intervals

def select(params,spl,mode,look,alive,indices):
    if not any(alive):return 0,True
    target=float(spl['C']['H2_mol_min'](1.,ref.U0[mode])[0,0]);floor=target-64*np.finfo(float).eps*abs(target)
    times=np.linspace(look,31,16);grid=np.linspace(ref.U0[mode],ref.UMAX,7);requirements=[];cannot=False
    for hi,h in enumerate(ref.HYP):
        if not alive[hi]:continue
        a,k=params[h][indices[hi]];theta=np.minimum(1,a*np.exp(-k*(times-10))) if h in ['C','M','F'] else np.ones(len(times))
        chosen=None
        for ui,command in enumerate(grid):
            if h in ['S','H']:values=np.full(len(times),float(spl['C']['H2_mol_min'](1,command)[0,0]))
            elif h=='F':
                actual=theta*command;values=spl['C']['H2_mol_min'].ev(np.ones(len(times)),actual) if np.all(actual>=ref.UMIN-1e-12) else np.full(len(times),-np.inf)
            else:values=spl[h]['H2_mol_min'].ev(theta,np.full(len(times),command)) if np.all(theta>=.4-1e-12) else np.full(len(times),-np.inf)
            if np.min(values)>=floor:chosen=ui;break
        if chosen is None:chosen=len(grid)-1;cannot=True
        requirements.append(chosen)
    return max(requirements),cannot

def audit(root):
    root=Path(root);out=root/'results';protocol=json.loads((root/'protocol.json').read_text());issues=[]
    def need(ok,where):
        if not ok:issues.append(where)
    def close(a,b,where):need(np.asarray(a).shape==np.asarray(b).shape and np.allclose(a,b,atol=1e-13,rtol=1e-9),where)
    def csv(p):return pd.read_csv(p,float_precision='round_trip')
    tables={};params={}
    for mode in [1,2]:
        tables[mode]=ref.map_splines(root/f'reference/reformer_diag/diag/outputs_diag/map_mode{mode}.csv')
        params[mode]={h:ref.bank_parameters(mode,h,tables[mode]) for h in ref.HYP}
    measures=['H2_shortfall_mol','actual_ethanol_mol','commanded_ethanol_mol','H2_produced_mol']
    branch_rows=[]
    for case in protocol['cases']:
        if not case['policy']:continue
        for active in [False,True]:
            parent=f'{case["id"]}_{"active" if active else "passive"}';prefix=csv(root/'dynamic_truth'/parent/'intervals.csv')
            for look in protocol['policy']['decision_times_min']:
                for ui,command in enumerate(np.linspace(ref.U0[case['mode']],ref.UMAX,protocol['policy']['command_points'])):
                    key=f'{parent}_t{look:g}_u{ui}';folder=root/'dynamic_branches'/key;tail=csv(folder/'intervals.csv')
                    joined=pd.concat([prefix[prefix.t_end<=look+1e-10],tail],ignore_index=True)
                    need(len(joined)==310 and abs(joined.t_start.iloc[0])<1e-12 and abs(joined.t_end.iloc[-1]-31)<1e-12,key+'/common horizon')
                    need(np.allclose(tail.commanded_ethanol_mol_min,command,atol=0,rtol=0),key+'/branch command')
                    # Demand is constant on each row; raw endpoint H2/feed supplies
                    # the independent quadrature, not the saved integral columns.
                    dt=joined.t_end-joined.t_start;demand=joined.H2_demand_mol/dt
                    calc=physical_intervals(joined.t_start,joined.t_end,joined.commanded_ethanol_mol_min,joined.actual_ethanol_start,joined.actual_ethanol_end,joined.H2_start_mol_min,joined.H2_end_mol_min,demand,demand)
                    calc['commanded_ethanol_mol']=calc.pop('command_ethanol_mol')
                    branch_rows.append(dict(case_id=case['id'],active=active,decision_min=look,command_index=ui,**calc))
    branch=pd.DataFrame(branch_rows).set_index(['case_id','active','decision_min','command_index'])
    saved_branch=csv(root/'branch_costs.csv').set_index(branch.index.names)
    need(len(saved_branch)==len(branch),'branch costs complete count')
    for key,row in branch.iterrows():
        need(key in saved_branch.index,'branch key '+str(key))
        if key in saved_branch.index:
            for f in measures:close(saved_branch.loc[key,f],row[f],'branch integral '+str(key)+'/'+f)
    decisions=csv(out/'policy_decisions.csv');keycols=['case_id','active','set','trial_id']
    need(not decisions.duplicated(keycols).any(),'unique policy trial IDs')
    trials=[];cache={}
    for case in protocol['cases']:
        if not case['policy']:continue
        for active in [False,True]:
            ident=f'{case["id"]}_{"active" if active else "passive"}_evaluation'
            with np.load(out/'batches'/(ident+'.npz')) as b,np.load(out/'batches'/(ident+'_decisions.npz')) as d:
                for ss in protocol['sensor_sets']:
                    data=decisions[(decisions.case_id==case['id'])&(decisions.active==active)&(decisions['set']==ss)].sort_values('trial_id')
                    need(np.array_equal(data.trial_id,np.arange(protocol['n_evaluation'])),ident+'/'+ss+'/complete policy rows')
                    for r in data.to_dict('records'):
                        i=r['trial_id'];look=float(d['times_'+ss][i]);li=0 if look==16 else 1;alive=d['alive_'+ss][i,li];indices=b['indices_'+ss][i,li]
                        signature=(case['mode'],look,tuple(alive),tuple(indices))
                        if signature not in cache:cache[signature]=select(params[case['mode']],tables[case['mode']],case['mode'],look,alive,indices)
                        ui,cannot=cache[signature]
                        need(r['command_index']==ui and r['predicted_infeasible']==cannot,ident+'/'+ss+f'/{i}/command policy')
                        need(r['call']==d['calls_'+ss][i] and r['decision_min']==look,ident+'/'+ss+f'/{i}/causal stop')
                        command=np.linspace(ref.U0[case['mode']],ref.UMAX,7)[ui];close(r['command_mol_min'],command,ident+'/'+ss+f'/{i}/command value')
                        values=branch.loc[(case['id'],active,look,ui)]
                        trials.append(dict(case_id=case['id'],mode=case['mode'],true_h=case['h'],active=active,set=ss,trial_id=i,**{f:values[f] for f in measures}))
    expected=pd.DataFrame(trials);reported=csv(out/'policy_trials.csv').set_index(keycols);exp=expected.set_index(keycols)
    need(len(reported)==len(exp) and not reported.index.duplicated().any(),'policy trial count/uniqueness')
    for f in measures:close(reported.reindex(exp.index)[f].to_numpy(),exp[f].to_numpy(),'policy trials/'+f)
    grouping=['case_id','mode','true_h','active','set'];summary=[]
    for key,g in expected.groupby(grouping):
        row=dict(zip(grouping,key))
        for f in measures:
            x=g[f].to_numpy();row.update({f+'_mean':np.mean(x),f+'_std':np.std(x,ddof=1),f+'_min':np.min(x),f+'_max':np.max(x)})
        summary.append(row)
    def compare_summary(rows,path,keys):
        saved=csv(path).set_index(keys);want=pd.DataFrame(rows).set_index(keys);need(len(saved)==len(want) and not saved.index.duplicated().any(),path.name+'/rows')
        for col in want.columns:close(saved.reindex(want.index)[col].to_numpy(),want[col].to_numpy(),path.name+'/'+col)
    compare_summary(summary,out/'policy_summary.csv',grouping)
    paired=expected[expected.active].merge(expected[~expected.active],on=['case_id','set','trial_id'],suffixes=('_active','_passive'),validate='one_to_one')
    pairs=[]
    for key,g in paired.groupby(['case_id','set']):
        row=dict(zip(['case_id','set'],key))
        for f in measures:
            x=(g[f+'_active']-g[f+'_passive']).to_numpy();row.update({f+'_difference_mean':np.mean(x),f+'_difference_std':np.std(x,ddof=1),f+'_difference_min':np.min(x),f+'_difference_max':np.max(x)})
        pairs.append(row)
    compare_summary(pairs,out/'policy_paired_differences.csv',['case_id','set'])
    return {'pass':not issues,'issues':issues,'branches':len(branch_rows),'policy_trials':len(trials),'policy_summary':summary,'paired_differences':pairs,
            'scope':'Physical-unit totals and paired descriptive differences only; no service/economic benefits or policy-optimality claim.'}
