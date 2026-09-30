"""Independent stochastic reconstruction and reporting audit. Freeze before scoring."""
from pathlib import Path
import os
for name in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS']:os.environ[name]='1'
import argparse,datetime,hashlib,json
import numpy as np
import pandas as pd
from scipy.linalg import solve_triangular
import integration_reference as ref
from reference_math import rank_threshold,event_interval,sequential_decision

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text())
def clean(x):
    if isinstance(x,dict):return {k:clean(v) for k,v in x.items()}
    if isinstance(x,(list,tuple)):return [clean(v) for v in x]
    if isinstance(x,np.generic):return clean(x.item())
    if isinstance(x,float) and not np.isfinite(x):return None
    return x

def audit(root,phase='all'):
    root=Path(root);protocol=read(root/'protocol.json');out=root/'results';issues=[];batches=[];metric_rows=[];bank_cache={};cal_expected=[]
    def need(ok,where,detail=None):
        if not ok:issues.append({'where':where,'detail':clean(detail)})
    def close(a,b,where,atol=1e-13,rtol=1e-9):
        aa=np.asarray(a);bb=np.asarray(b)
        ok=aa.shape==bb.shape and np.allclose(aa,bb,atol=atol,rtol=rtol,equal_nan=False)
        need(ok,where,{'fresh_shape':list(aa.shape),'reference_shape':list(bb.shape),'max_abs':float(np.max(abs(aa-bb))) if aa.shape==bb.shape and aa.size else None})
    for filename,hashkey,base in [('MATH_FREEZE.json','sha256',root/'checks'),('INTEGRATION_FREEZE.json','sha256',root/'checks'),('PROTOCOL_FREEZE.json','files',root)]:
        f=read(root/'checks'/filename) if filename!='PROTOCOL_FREEZE.json' else read(root/filename)
        for name,h in f[hashkey].items():need((base/name).is_file() and sha(base/name)==h,'frozen/'+name)
    integration_freeze=read(root/'checks/INTEGRATION_FREEZE.json')
    need(integration_freeze['statistical_pipeline_sha256']==sha(root/'statistical_campaign.py'),'frozen statistical pipeline')
    need(integration_freeze['protocol_sha256']==sha(root/'protocol.json'),'frozen integration protocol')
    cases={c['id']:c for c in protocol['cases']};expected=[]
    for case in protocol['cases']:
        for active in [False,True]:
            if case['category']=='covered_grid':expected.append((case,active,'calibration',None,{}))
            if phase!='calibration':
                expected.append((case,active,'evaluation',None,{}))
                if case['policy']:
                    expected += [(case,active,'stress',i,{k:v for k,v in st.items() if k!='name'}) for i,st in enumerate(protocol['observation_stress'])]
    expected_paths=[];seen_seeds={};saved_references={};calibration=read(out/'calibration.json')
    for mode in [1,2]:
        for active in [False,True]:
            ident=f'm{mode}_{"active" if active else "passive"}';bp=out/'banks'/ident
            meta=read(bp/'bank.json');need(sha(bp/'bank.npz')==meta['npz_sha256'],ident+'/bank hash')
            expected_bank=ref.build_bank(protocol,root/f'reference/reformer_diag/diag/outputs_diag/map_mode{mode}.csv',mode,active)
            params,vectors,covs,infos=expected_bank;bank_cache[(mode,active)]=expected_bank
            with np.load(bp/'bank.npz') as b:
                for h in ref.HYP:close(b['params_'+h],params[h],ident+'/params/'+h)
                for (ss,look,h),v in vectors.items():close(b[f'vectors_{ss}_{look}_{h}'],v,ident+f'/vectors/{ss}/{look}/{h}')
                for (ss,look),cov in covs.items():close(b[f'covariance_{ss}_{look}'],cov,ident+f'/covariance/{ss}/{look}',atol=1e-20,rtol=1e-10)
            need(meta['designs']=={f'{ss}_{look}':info for (ss,look),info in infos.items()},ident+'/causal design metadata')
    integration_time=datetime.datetime.fromisoformat(read(root/'checks/INTEGRATION_FREEZE.json')['created_utc'])
    for case,active,which,si,kwargs in expected:
        stem=f'{case["id"]}_{"active" if active else "passive"}_{which}'+('' if si is None else f'_{si}')
        mp=out/'batches'/(stem+'.json');expected_paths.append(mp.name)
        if not mp.exists():need(False,stem+'/missing batch');continue
        meta=read(mp);mode=case['mode'];n=protocol['n_'+which] if which!='stress' else protocol['n_stress']
        seed=protocol['seed_base']+case['index']*100000+protocol['phase_offsets'][which]+(0 if si is None else si*1000)
        for key,value in [('case_id',case['id']),('mode',mode),('active',active),('phase',which),('stress_index',si),('seed',seed),('n',n),('noise_kwargs',kwargs),('true_hypothesis',case['h']),('category',case['category'])]:need(meta.get(key)==value,stem+'/'+key)
        identity=(case['id'],which,si)
        need(seed not in seen_seeds or seen_seeds[seed]==identity,stem+'/seed reuse outside paired active/passive')
        seen_seeds[seed]=identity
        need(datetime.datetime.fromisoformat(meta['created_utc'])>=integration_time,stem+'/precedes checker freeze')
        need(meta['protocol_sha256']==sha(root/'protocol.json') and meta['model_sha256']==sha(root/'revision_model.py'),stem+'/source binding')
        need(meta['rng']=='numpy.random.default_rng/PCG64',stem+'/declared RNG')
        need(meta.get('numpy_version')==np.__version__,stem+'/RNG runtime version')
        path=root/meta['npz_path'];truth=root/meta['truth_dir']/'truth.csv'
        need(sha(path)==meta['npz_sha256'] and sha(truth)==meta['truth_sha256'],stem+'/input/output hashes')
        frame=pd.read_csv(truth,float_precision='round_trip')
        for f in ref.FEATURES:frame[f]=frame['observed_'+f]
        regenerated,exemplar,_=ref.regenerate(protocol,frame,mode,n,seed,kwargs)
        params,vectors,covs,infos=bank_cache[(mode,active)]
        with np.load(path) as z:
            need(np.array_equal(z['trial_id'],np.arange(n)),stem+'/complete trial IDs')
            for f,raw in exemplar.items():
                for field,value in raw.items():close(z[f'raw0_{f}_{field}'],value,stem+'/raw0/'+f+'/'+field)
            for ss in protocol['sensor_sets']:
                need(z['scores_'+ss].shape==(n,2,5) and z['indices_'+ss].shape==(n,2,5),stem+'/'+ss+'/score shape')
                for li,look in enumerate([16,21]):
                    obs=z[f'obs_{ss}_{look}'];close(obs,regenerated[(look,ss)],stem+f'/{ss}/{look}/regenerated summaries')
                    for hi,h in enumerate(ref.HYP):
                        value,idx=ref.scores_all(obs,vectors[(ss,look,h)],covs[(ss,look)])
                        close(z['scores_'+ss][:,li,hi],value,stem+f'/{ss}/{look}/{h}/minimum score',atol=1e-8,rtol=1e-7)
                        ix=z['indices_'+ss][:,li,hi];valid=(ix>=0)&(ix<len(params[h]));need(valid.all(),stem+f'/{ss}/{look}/{h}/fit indices')
                        if valid.all():
                            residual=obs-vectors[(ss,look,h)][ix];white=solve_triangular(np.linalg.cholesky(covs[(ss,look)]),residual.T,lower=True)
                            close(np.sum(white*white,axis=0),value,stem+f'/{ss}/{look}/{h}/chosen fit is minimum',atol=1e-8,rtol=1e-7)
                if which=='calibration':
                    hi=ref.HYP.index(case['h']);q=rank_threshold(z['scores_'+ss][:,:,hi].max(axis=1),protocol['alpha'])
                    cal_expected.append(dict(case_id=case['id'],mode=mode,active=active,set=ss,h=case['h'],n=n,k=q['rank'],threshold=q['threshold'],npz_path=meta['npz_path']))
                else:
                    key=f'm{mode}_{"active" if active else "passive"}_{ss}';q=np.array([calibration['thresholds'][key][h] if calibration['thresholds'][key][h] is not None else -np.inf for h in ref.HYP])
                    score=z['scores_'+ss];alive=np.logical_and.accumulate(score<=q[None,None,:],axis=1)
                    calls=np.full(n,'INCONCLUSIVE',dtype='<U20');times=np.full(n,21.)
                    # Independent per-record state machine, not the author's vectorized implementation.
                    for i in range(n):
                        rr=sequential_decision(score[i],q,[16,21],ref.HYP);calls[i]=rr['decision'];times[i]=rr['time']
                    with np.load(path.with_name(path.stem+'_decisions.npz')) as decision:
                        need(np.array_equal(calls,decision['calls_'+ss]),stem+'/'+ss+'/calls')
                        need(np.array_equal(times,decision['times_'+ss]),stem+'/'+ss+'/stopping times')
                        need(np.array_equal(alive,decision['alive_'+ss]),stem+'/'+ss+'/retained labels')
                    group=case['category'] if si is None else protocol['observation_stress'][si]['name']
                    supported=case['h'] in protocol['support'][str(mode)] and group!='out_of_family'
                    singleton=np.isin(calls,ref.HYP);correct=singleton&(calls==case['h']);wrong=singleton&(calls!=case['h']);stop=np.where(times==16,0,1)
                    rejected=~alive[np.arange(n),stop,ref.HYP.index(case['h'])] if supported else None
                    potential=~alive[:,-1,ref.HYP.index(case['h'])] if supported else None
                    row=dict(case_id=case['id'],mode=mode,true_h=case['h'],nominal_drop=case['drop'],active=active,set=ss,group=group,phase=which,n=n,supported_label=supported,
                             true_rejected=int(rejected.sum()) if supported else None,potential_true_rejected_at21=int(potential.sum()) if supported else None,
                             correct_singleton=int(correct.sum()),wrong_singleton=int(wrong.sum()),inconclusive=int((calls=='INCONCLUSIVE').sum()),incompatible=int((calls=='MODEL_INCOMPATIBLE').sum()),early_singleton=int((singleton&(times==16)).sum()),
                             median_diagnosis_time_min=float(np.median(times[singleton])) if singleton.any() else None,median_correct_time_min=float(np.median(times[correct])) if correct.any() else None)
                    for field in ['true_rejected','correct_singleton','wrong_singleton','inconclusive','incompatible']:
                        val=row[field];interval=event_interval(val,n) if val is not None else None
                        row[field+'_rate']=None if val is None else val/n
                        row[field+'_ci_lo']=None if val is None else interval['low'];row[field+'_ci_hi']=None if val is None else interval['high']
                    need(row['correct_singleton']+row['wrong_singleton']+row['inconclusive']+row['incompatible']==n,stem+'/'+ss+'/outcome partition')
                    if supported:need(bool(np.all(~wrong|rejected)),stem+'/'+ss+'/wrong singleton entails true rejection')
                    metric_rows.append(row)
        batches.append({'id':stem,'seed':seed,'n':n,'phase':which,'source_hash':sha(mp),'npz_hash':sha(path)})
        print(f'checked {stem}',flush=True)
    present_names=sorted(p.name for p in (out/'batches').glob('*.json') if phase!='calibration' or p.name.endswith('_calibration.json'))
    need(present_names==sorted(expected_paths),'batch inventory exact declared coverage')
    # No stored threshold is trusted: reselect ranks and cross-stratum maxima.
    need(len(cal_expected)==len(calibration['strata']),'calibration/stratum count')
    bykey={(r['case_id'],r['active'],r['set']):r for r in calibration['strata']}
    computed_thresholds={}
    for row in cal_expected:
        key=(row['case_id'],row['active'],row['set']);need(key in bykey,'calibration/missing stratum',key)
        if key in bykey:
            for field,value in row.items():need(bykey[key][field]==value,'calibration/'+str(key)+'/'+field)
        key=f'm{row["mode"]}_{"active" if row["active"] else "passive"}_{row["set"]}'
        d=computed_thresholds.setdefault(key,{h:None for h in ref.HYP});d[row['h']]=row['threshold'] if d[row['h']] is None else max(d[row['h']],row['threshold'])
    need(computed_thresholds==calibration['thresholds'],'calibration/max threshold reconstruction')
    if phase!='calibration':
        seal=read(out/'EVALUATION_FREEZE.json');need(seal['calibration_sha256']==sha(out/'calibration.json'),'evaluation/calibration seal')
        evaluation_time=datetime.datetime.fromisoformat(seal['created_utc'])
        for rec in batches:
            if rec['phase']!='calibration':need(datetime.datetime.fromisoformat(read(out/'batches'/(rec['id']+'.json'))['created_utc'])>=evaluation_time,rec['id']+'/precedes calibration seal')
        reported=pd.read_csv(out/'diagnosis_summary.csv',float_precision='round_trip');need(len(reported)==len(metric_rows),'summary/complete rows')
        keys=['case_id','active','set','group','phase'];need(not reported.duplicated(keys).any(),'summary/duplicate rows')
        rep=reported.set_index(keys)
        for row in metric_rows:
            key=tuple(row[k] for k in keys);need(key in rep.index,'summary/missing row',key)
            if key not in rep.index:continue
            saved=rep.loc[key]
            for field,value in row.items():
                if field in keys:continue
                actual=saved[field]
                if value is None:need(pd.isna(actual),'summary/'+str(key)+'/'+field)
                elif isinstance(value,(str,bool,int)):need(actual==value,'summary/'+str(key)+'/'+field)
                else:close(np.asarray(actual),np.asarray(value),'summary/'+str(key)+'/'+field)
    return dict(pass_=not issues,issues=issues,phase=phase,batches=batches,calibration_strata=len(cal_expected),recomputed_diagnosis_rows=metric_rows,
                scope='Full independent raw-noise regeneration, causal means/covariance, raw-map bank, scores, finite-rank thresholds, actual-stop outcomes and pointwise intervals. Scientific rates are retained, not pass targets.')

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1]);ap.add_argument('--phase',choices=['calibration','all'],default='all');ap.add_argument('--out',type=Path,required=True);a=ap.parse_args()
    result=audit(a.root,a.phase);result['pass']=result.pop('pass_');a.out.write_text(json.dumps(clean(result),indent=2,allow_nan=False));print(json.dumps({'pass':result['pass'],'issues':len(result['issues']),'batches':len(result['batches']),'out':str(a.out)},indent=2));raise SystemExit(not result['pass'])
