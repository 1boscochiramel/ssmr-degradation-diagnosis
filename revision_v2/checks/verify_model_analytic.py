"""Pre-evaluation analytic tests of author model against independent reference.

Only manufactured nonreactor observations are used. This is not calibration or
held-out scientific evaluation. Target module is imported only as code under test.
"""
from pathlib import Path
import hashlib,json,sys
import numpy as np
HERE=Path(__file__).resolve().parent;ROOT=HERE.parent
sys.path.insert(0,str(ROOT))
import revision_model as author
import reference_math as ref

issues=[];checks=[]
def need(ok,name):
    checks.append(name)
    if not ok:issues.append(name)
def close(x,y,name,atol=1e-9,rtol=1e-8):
    x=np.asarray(x);y=np.asarray(y)
    need(x.shape==y.shape and np.allclose(x,y,atol=atol,rtol=rtol),name)

for mode in [1,2]:
    cfg=author.sensor_settings(mode)
    for look in [16.,21.]:
        for sensor_set,features in author.SETS.items():
            rows,cov,info=author.observation_design(mode,look,sensor_set)
            counts=[len(np.arange(0,21.0001,cfg[f]['period_min'])) for f in features]
            sensors=np.repeat(features,counts);indices=np.concatenate([np.arange(n) for n in counts])
            sd=np.concatenate([np.full(n,cfg[f]['sd']) for f,n in zip(features,counts)])
            bb=np.concatenate([np.full(n,cfg[f]['bias_bound']) for f,n in zip(features,counts)])
            covariance=ref.raw_covariance(sensors,indices,sd,bb,{f:cfg[f]['phi'] for f in features})
            weights=np.zeros((len(rows),sum(counts)));offsets=dict(zip(features,np.cumsum([0,*counts[:-1]])))
            for i,(f,aq,w) in enumerate(rows):
                weights[i,offsets[f]:offsets[f]+len(w)]=w
                actual=info[i]
                independently_selected=(aq>actual['lo_min']+1e-9)&(aq<=actual['hi_min']+1e-9)&(aq+cfg[f]['delay_min']<=look+1e-9)
                expected=independently_selected.astype(float)/independently_selected.sum()
                close(w,expected,f'mode{mode}/{look}/{sensor_set}/{i}/causal weights',atol=0,rtol=0)
            close(cov,ref.aggregated_covariance(weights,covariance),f'mode{mode}/{look}/{sensor_set}/joint covariance',atol=1e-20,rtol=1e-11)
    # Exact raw draw regeneration on a manufactured deterministic feature frame.
    frame={'time_min':author.TIMES}
    for i,f in enumerate(author.FEATURES):frame[f]=(i+1)+author.TIMES*(i+1)*.001
    n=3;seed=117
    summary,exemplar=author.draw_summaries(frame,mode,n,seed)
    rng=np.random.default_rng(seed);raw={}
    for f in author.FEATURES:
        q=cfg[f];aq=np.arange(0,21.0001,q['period_min']);truth=np.interp(aq,frame['time_min'],frame[f])
        innovations=rng.standard_normal((n,len(aq)));noise=np.empty_like(innovations);noise[:,0]=innovations[:,0]
        for j in range(1,len(aq)):noise[:,j]=q['phi']*noise[:,j-1]+np.sqrt(1-q['phi']**2)*innovations[:,j]
        bias=rng.uniform(-1,1,(n,1))*q['bias_bound']
        # Author consumes these draws even when the optional scales are zero.
        rng.uniform(-1,1,(n,1));rng.normal(0,0,(n,1))
        raw[f]=truth[None,:]+bias+q['sd']*noise
        close(raw[f][0],exemplar[f]['value'],f'mode{mode}/{f}/raw exemplar',atol=1e-13,rtol=1e-13)
    for look in [16.,21.]:
        for ss in author.SETS:
            rows,_,_=author.observation_design(mode,look,ss)
            independently=np.asarray([sum(raw[f][:,j]*w[j] for j in range(len(w))) for f,_,w in rows]).T
            close(independently,summary[(look,ss)],f'mode{mode}/{look}/{ss}/raw summaries',atol=1e-13,rtol=1e-13)
    for active in [False,True]:
        bank=author.DiagnosticBank(mode,active)
        for look in [16.,21.]:
            for ss in author.SETS:
                rows,cov,_=author.observation_design(mode,look,ss)
                vectors={h:np.stack([bank.pred[h][f][:,np.rint(aq*10).astype(int)]@w for f,aq,w in rows],axis=1) for h in author.HYP}
                observations=np.asarray([vectors['H'][0]+np.sqrt(np.diag(cov))*.13*np.cos(np.arange(len(cov))+shift) for shift in range(2)])
                score,idx=bank.score(observations,look,ss)
                for j,h in enumerate(author.HYP):
                    expected=[ref.closest_bank(obs,vectors[h],cov) for obs in observations]
                    close(score[:,j],[x['score'] for x in expected],f'mode{mode}/{active}/{look}/{ss}/{h}/score',atol=1e-8,rtol=1e-8)
                    # Near-identical templates can have tied scores: chosen score,
                    # not floating-point arbitrary tied bank ID, is the invariant.
                    for i,x in enumerate(expected):close(x['all_scores'][idx[i,j]],x['score'],f'mode{mode}/{active}/{look}/{ss}/{h}/{i}/minimum',atol=1e-8,rtol=1e-8)

cases=np.asarray([[[0,0,2,2,2],[0,2,2,2,2]],[[0,2,2,2,2],[2,0,0,0,0]],[[2,2,2,2,2],[0,0,0,0,0]],[[0,0,0,0,0],[0,0,0,0,0]]],dtype=float)
d,t,alive=author.decide(cases,np.ones(5))
for i,x in enumerate(cases):
    expected=ref.sequential_decision(x,np.ones(5),[16,21],author.HYP)
    need(d[i]==expected['decision'] and t[i]==expected['time'],f'decision fixture {i}')
for n in [1,18,19,499]:
    expected=ref.rank_threshold(np.arange(n),.05)['threshold']
    need(author.rank_threshold(np.arange(n),.05)==expected,f'finite-rank fixture {n}')
out={'pass':not issues,'issues':issues,'checks':len(checks),'check_names':checks,'target_sha256':hashlib.sha256((ROOT/'revision_model.py').read_bytes()).hexdigest(),'scope':'Manufactured analytic fixtures only; no calibration/evaluation campaign outputs.'}
(HERE/'model_analytic_selftest.json').write_text(json.dumps(out,indent=2));print(json.dumps({k:v for k,v in out.items() if k!='check_names'},indent=2));raise SystemExit(bool(issues))
