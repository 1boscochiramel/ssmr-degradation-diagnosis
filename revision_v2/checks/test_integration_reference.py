"""Pre-result synthetic integration fixtures and deliberate fault detections."""
from pathlib import Path
import os
for name in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS']:os.environ[name]='1'
import hashlib,json,sys
import numpy as np
HERE=Path(__file__).resolve().parent;ROOT=HERE.parent;sys.path.insert(0,str(ROOT))
import revision_model as author
import integration_reference as ref
from reference_math import rank_threshold,physical_intervals
protocol=json.loads((ROOT/'protocol.json').read_text());checks=[]
def close(a,b,name,atol=1e-13,rtol=1e-9):
    assert np.asarray(a).shape==np.asarray(b).shape and np.allclose(a,b,atol=atol,rtol=rtol),name
    checks.append(name)
for mode in [1,2]:
    for active in [False,True]:
        own=ref.build_bank(protocol,ROOT/f'reference/reformer_diag/diag/outputs_diag/map_mode{mode}.csv',mode,active)
        params,vectors,covs,infos=own;target=author.DiagnosticBank(mode,active)
        for h in ref.HYP:close(params[h],target.params[h],f'{mode}/{active}/{h}/parameters')
        for (look,ss),(l,origin,white,info,cov) in target.cache.items():
            close(covs[(ss,int(look))],cov,f'{mode}/{active}/{ss}/{look}/covariance',atol=1e-20,rtol=1e-10)
            assert infos[(ss,int(look))]==info
            for h in ref.HYP:close(vectors[(ss,int(look),h)],white[h]@l.T+origin,f'{mode}/{active}/{ss}/{look}/{h}/raw-map bank')
            y=np.array([origin+.2*np.sqrt(np.diag(cov))*np.sin(np.arange(len(cov))+j) for j in range(3)])
            scores,_=target.score(y,look,ss)
            for j,h in enumerate(ref.HYP):
                score,_=ref.scores_all(y,vectors[(ss,int(look),h)],cov)
                close(score,scores[:,j],f'{mode}/{active}/{ss}/{look}/{h}/scores',atol=1e-8,rtol=1e-7)
    frame={'time_min':author.TIMES}
    for j,f in enumerate(ref.FEATURES):frame[f]=(j+1)+author.TIMES*(j+1)*.001
    for kwargs in [{},{'noise_scale':2},{'fast_phi':.9,'gc_phi':.7},{'drift_scale':2},{'gain_sd':.01}]:
        expected,_,_=ref.regenerate(protocol,frame,mode,3,119,kwargs);actual,_=author.draw_summaries(frame,mode,3,119,**kwargs)
        for (look,ss),value in expected.items():close(value,actual[(look,ss)],f'{mode}/{kwargs}/{ss}/{look}/raw regeneration')
negative={}
negative['seed_overlap']=bool(set([1,2])&set([2,3]))
_,c,_=ref.design(protocol,1,21,'S1');wrong=c.copy();wrong[0,1]=wrong[1,0]=0
negative['omitted_cross_window_covariance']=not np.allclose(c,wrong,atol=1e-20,rtol=1e-10)
_,_,info=ref.design(protocol,1,16,'S4');wrong_gc={**info[-1],'available_min':[18.]}
negative['future_GC']=max(wrong_gc['available_min'])>16
negative['true_score_zero']=not np.isclose(4.,0.,atol=1e-8)
q=rank_threshold(np.arange(499),.05);negative['rank_off_by_one']=q['threshold']!=np.sort(np.arange(499))[q['rank']]
negative['dropped_inconclusive']=sum([1,2,3,4])!=9
negative['changed_headline']=4!=3
z=physical_intervals([0],[10],[.0022],[.0022],[.0022],[.0001],[.0001],[.0002],[.0002])
negative['same_action_zero_cost']=z['H2_shortfall_mol']!=0
negative['wrong_command_quadrature']=not np.isclose(z['command_ethanol_mol'],.021,atol=1e-13)
assert all(negative.values()),negative
negative={k:bool(v) for k,v in negative.items()}
out={'pass':True,'checks':len(checks),'negative_controls':negative,'model_sha256':hashlib.sha256((ROOT/'revision_model.py').read_bytes()).hexdigest(),'scope':'Manufactured input/analytic tests only, before calibration/evaluation; no scientific outcomes inspected.'}
(HERE/'integration_selftest.json').write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2))
