"""Independent arithmetic/source check on saved benchmark and policy evidence."""
from pathlib import Path
import argparse, datetime, hashlib, json
import numpy as np
import pandas as pd
from scipy.io import loadmat

HERE = Path(__file__).resolve().parent
R = HERE.parent.parent
B = R.parent
NATIVE = B / 'full_rerun/native_matlab'
UP = NATIVE / 'baseline/SSMR_Benchmark-c6280844404cbef38da8a893a095a734bc0d4815/SSMR_simulator'
PAIRED = R / 'amendment_feed_only_20260930/outputs/paired_trials.csv'
CASES = ['STEP', 'CS1', 'CS2T', 'CS2P']
NOMINAL = {1: .0021, 2: .0018}

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p, obj):
    q = p.with_suffix(p.suffix + '.tmp')
    q.write_text(json.dumps(obj, indent=2, allow_nan=False), encoding='utf-8')
    q.replace(p)
def inputs():
    out = [HERE/'CHECK_SPEC.txt', Path(__file__), R/'results/policy_trials.csv',
           PAIRED, R/'sources/benchmark.pdf', R/'sources/benchmark.txt',
           UP/'control.m', UP/'SSMR_simulation.m',
           B/'full_rerun/checks/native_provenance_final.json',
           B/'full_rerun/checks/native_git_identity.json']
    for case in CASES:
        for folder, csvname, matname in [('baseline', f'{case}_np50_matlab.csv', f'{case}_state.mat'),
                                      ('finegrid', f'{case}_np200.csv', f'{case}_np200_state.mat')]:
            out += [NATIVE/folder/csvname, NATIVE/folder/matname]
    for folder, n in [('baseline',50),('finegrid',200)]:
        src=next((NATIVE/folder).rglob('SSMR_simulator'))
        out += [src/f'ICFull/Mode1_np{n}.mat',src/f'ICH2O/Mode2_np{n}_H2O.mat']
    return out
def run():
    ap = argparse.ArgumentParser(); ap.add_argument('--freeze', action='store_true'); args=ap.parse_args()
    paths=inputs(); inventory={str(p):{'sha256':sha(p),'bytes':p.stat().st_size} for p in paths}
    frozen=HERE/'CHECK_FREEZE.json'
    if args.freeze:
        if frozen.exists(): raise RuntimeError('Existing freeze retained; refusing overwrite')
        write(frozen, {'at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
                       'scope':'Supplemental source and arithmetic check on prior observed evidence',
                       'files':inventory})
        print('FROZEN',sha(frozen)); return
    assert json.loads(frozen.read_text())['files']==inventory, 'Frozen inputs changed'
    issues=[]; checks=[]
    def ck(name, ok, detail=None):
        checks.append({'name':name,'pass':bool(ok),'detail':detail})
        if not ok: issues.append(name)
    ck('sign-crossing integration fixture', np.trapezoid(np.abs([-1.,1.]),[0.,1.])==1. and abs((-1.+1.)/2)==0.)
    iae=[]; mesh=[]; additional_sources={}
    provenance=json.loads((B/'full_rerun/checks/native_provenance_final.json').read_text())
    identity=json.loads((B/'full_rerun/checks/native_git_identity.json').read_text())
    for case in CASES:
        arrays=[]
        for n,folder,csvname,matname in [(50,'baseline',f'{case}_np50_matlab.csv',f'{case}_state.mat'),
                                       (200,'finegrid',f'{case}_np200.csv',f'{case}_np200_state.mat')]:
            csvpath=NATIVE/folder/csvname
            ar=np.loadtxt(csvpath,delimiter=','); arrays.append(ar)
            ck(f'{case}/{n}/shape and finite',ar.ndim==2 and ar.shape[1]==4 and np.isfinite(ar).all())
            ck(f'{case}/{n}/increasing time',np.all(np.diff(ar[:,0])>0))
            st=loadmat(NATIVE/folder/matname,simplify_cells=True)
            ck(f'{case}/{n}/saved np',int(st['np'])==n)
            saved=np.column_stack([st['time'],st['y_output'],st['u_output'],st['y_sp']])
            ck(f'{case}/{n}/CSV versus saved MATLAB arrays',ar.shape==saved.shape and np.allclose(ar,saved,rtol=0,atol=1e-12))
            src=next((NATIVE/folder).rglob('SSMR_simulator'))
            ic=next(src.rglob(str(st['ss_filename'])))
            additional_sources[str(ic)]={'sha256':sha(ic),'bytes':ic.stat().st_size}
            initial=loadmat(ic,simplify_cells=True)
            ck(f'{case}/{n}/first feed from supplied IC',np.isclose(ar[0,2],initial['u_ss'][0],rtol=0,atol=1e-15))
        b,f=arrays; ck(case+'/common recorded time grid',b.shape==f.shape and np.allclose(b[:,0],f[:,0],rtol=0,atol=1e-12))
        ss=.000227354 if case in ['STEP','CS1'] else .000276379
        diff=np.abs(b[:,1]-f[:,1]); i=int(np.argmax(diff)); later=b[:,0]>=1
        mesh.append({'case':case,'max_H2_pct_nominal':float(100*diff[i]/ss),
                     'at_display_min':float(b[i,0]),'after_one_min_max_pct_nominal':float(100*diff[later].max()/ss),
                     'np50_at_max_mol_min':float(b[i,1]),'np200_at_max_mol_min':float(f[i,1]),
                     'finegrid_reset_log_confirmed':provenance['finegrid']['cases'][case]['control_reset_in_execution_log'],
                     'interpretation':'Recorded sensitivity to mesh and supplied initial state. No grid-convergence claim.'})
        if case!='STEP':
            t=b[:,0];e=b[:,3]-b[:,1];conv=float(np.trapezoid(abs(e),t));literal=float(np.sum(abs((e[1:]+e[:-1])/2)*np.diff(t)))
            ck(case+'/literal no larger than conventional', literal<=conv+1e-15)
            iae.append({'case':case,'conventional_iae_mmol':1000*conv,'literal_equation13_mmol':1000*literal,
                        'difference_pct_conventional':100*(conv-literal)/conv,
                        'sign_changing_intervals':int(np.sum(e[1:]*e[:-1]<0))})
    control=(UP/'control.m').read_text();sim=(UP/'SSMR_simulation.m').read_text()
    markers=['persistent integral_error','persistent prev_error',
             'if isempty(integral_error) && isempty(prev_error)',
             'integral_error = integral_error + error*t_s;',
             'derivative_error = (error - prev_error)/t_s;',
             'deltau = kp*error + ki*integral_error + kd*derivative_error;', 'prev_error = error;']
    for m in markers: ck('source/'+m,m in control)
    ck('source/plain clear and no controller reset','clear; close all; clc;' in sim and 'clear control' not in sim)
    def delta(e, retained_integral, retained_previous):
        kp=18*(.6*.1265);ki=.01*((1.2*.1265)/.25);kd=(3*.1265*.25)/40;dt=.1
        return kp*e+ki*(retained_integral+e*dt)+kd*(e-retained_previous)/dt
    reset=delta(0.,0.,0.);retained=delta(0.,1e-4,0.)
    ck('zero current error with retained integral changes command',reset==0 and retained!=reset)
    source_locations={m:i+1 for i,line in enumerate(control.splitlines()) for m in markers if m in line}
    srcidentity=identity['baseline']['files']['SSMR_simulator/control.m']
    ck('controller bytes match earlier pinned Git blob check',sha(UP/'control.m')==srcidentity['pinned_git_blob_sha256'])
    policy=pd.read_csv(R/'results/policy_trials.csv');pair=pd.read_csv(PAIRED)
    negative=policy[policy.true_h.isin(['H','S'])].copy()
    keys=['case_id','set','trial_id']; join=negative[negative.active].merge(pair,on=keys,suffixes=('_original','_paired'),validate='one_to_one')
    ck('all active negative-control records joined',len(join)==12000)
    ck('paired diagnostic ethanol matches original',np.allclose(join.actual_ethanol_mol,join.diagnostic_actual_ethanol_mol,rtol=0,atol=1e-14))
    ck('paired diagnostic shortfall matches original',np.allclose(join.H2_shortfall_mol,join.diagnostic_H2_shortfall_mol,rtol=0,atol=1e-14))
    rows=[]
    for (case,active,sensor),g in negative.groupby(['case_id','active','set'],sort=True):
        mode=int(g['mode'].iloc[0]);nom=NOMINAL[mode];count=int(np.sum(np.abs(g.command_mol_min-nom)>1e-12));n=len(g)
        ck(f'{case}/{active}/{sensor}/complete denominator',n==1000 and set(g.trial_id)==set(range(1000)))
        record={'case_id':case,'mode':mode,'true_h':str(g.true_h.iloc[0]),'active':bool(active),'set':sensor,
                'episodes':n,'non_nominal_followup_commands':count,'action_rate_pct':100*count/n,
                'nominal_command_mol_min':nom,'mean_H2_shortfall_mmol':1000*float(g.H2_shortfall_mol.mean()),
                'call_counts':g.call.value_counts().to_dict()}
        if active:
            q=pair[(pair.case_id==case)&(pair['set']==sensor)]
            ck(f'{case}/{sensor}/paired denominator',len(q)==1000)
            record.update(extra_actual_ethanol_vs_same_pulse_mmol=1000*float(q.difference_actual_ethanol_mol.mean()),
                          H2_shortfall_difference_vs_same_pulse_mmol=1000*float(q.difference_H2_shortfall_mol.mean()))
        rows.append(record)
    ck('all healthy/meter-bias cells retained',len(rows)==24)
    frame=pd.DataFrame([{k:v for k,v in r.items() if k!='call_counts'} for r in rows])
    csvtmp=HERE/'negative_controls.csv.tmp';frame.to_csv(csvtmp,index=False);csvtmp.replace(HERE/'negative_controls.csv')
    out={'status':'PASS' if not issues else 'FAIL','new_native_MATLAB_run':False,'different_model_review':False,
         'source_files':inventory,'source_IC_files':additional_sources,'checks':checks,'issues':issues,
         'integration_rule':iae,'mesh_sensitivity':mesh,
         'PID_state':{'source_confirmed':all(m in control for m in markers),'locations':source_locations,
                      'simulation_start_line':3,'hypothetical_fixture_reset_delta':reset,
                      'hypothetical_fixture_retained_delta':retained,
                      'warning':'Fixture demonstrates source logic only; no native simulation effect size claimed. Earlier +20.12 percent figure was screenshot-transcribed and is not a raw-CSV paired replication here.'},
         'negative_controls':rows,
         'scope':'Independent arithmetic and source trace within same model family; no new simulation, no physical validation.'}
    write(HERE/'findings_evidence.json',out)
    print(json.dumps({'status':out['status'],'issues':issues,'integration_rule':iae,'mesh_sensitivity':mesh,
                      'active_negative_controls':[r for r in rows if r['active']]},indent=2))
    raise SystemExit(bool(issues))
if __name__=='__main__': run()
