"""Revised observation model and finite-bank profiled diagnostic score.

Absolute window means are used; all same-instrument covariance is retained.
The rank-calibrated score has no assumed chi-square degrees of freedom.
"""
from pathlib import Path
import os
for _key in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):
    os.environ.setdefault(_key, '1')
import sys, json
import numpy as np
from scipy.linalg import block_diag, cholesky, solve_triangular
from scipy.spatial.distance import cdist

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'reference/reformer_diag/diag'))
from hypotheses import Map, FEATURES, SS, U_SS, U_MIN, U_MAX, MOVE

HYP = ('C','M','F','S','H')
SETS = {'S1': FEATURES[:1], 'S3': FEATURES[:3], 'S4': FEATURES}
LOOKS = (16.,21.)
TIMES = np.round(np.arange(0.,21.0001,.1), 8)
GC = FEATURES[3:]

def sensor_settings(mode):
    nominal = Map(mode).base('C',1.,U_SS[mode])
    result = {}
    for f in FEATURES:
        if f == 'H2_mol_min': sd,b = .005*SS[mode],.005*SS[mode]
        elif f == 'T_out_K': sd,b = .5,1.
        elif f == 'waste_m3_min': sd,b = .01*abs(nominal[f]),.02*abs(nominal[f])
        else: sd,b = max(.01*abs(nominal[f]),.001),.02*abs(nominal[f])
        result[f] = dict(sd=sd,bias_bound=b,period_min=3. if f in GC else .1,
                         delay_min=3. if f in GC else 0.,phi=.3 if f in GC else .6)
    return result

def observation_design(mode, look, sensor_set):
    """Causal linear summaries and their full within-look covariance."""
    bins = [(0.,5.),(5.,10.),(11.,16.)] + ([(16.,21.)] if look == 21. else [])
    settings = sensor_settings(mode)
    blocks, rows, info = [], [], []
    for f in SETS[sensor_set]:
        cfg = settings[f]
        acquire = np.arange(0.,21.0001,cfg['period_min'])
        available = acquire + cfg['delay_min']
        a = np.array([((acquire>lo+1e-9)&(acquire<=hi+1e-9)&(available<=look+1e-9)).astype(float)
                      for lo,hi in bins])
        assert np.all(a.sum(1)>0), (f, look, a.sum(1))
        a /= a.sum(1)[:,None]
        r = cfg['phi'] ** np.abs(np.arange(len(acquire))[:,None]-np.arange(len(acquire))[None,:])
        cov = cfg['sd']**2 * a @ r @ a.T + cfg['bias_bound']**2/3.
        blocks.append(cov)
        for i,(lo,hi) in enumerate(bins):
            rows.append((f,acquire,a[i]))
            info.append(dict(feature=f,lo_min=lo,hi_min=hi,
                             acquired_min=acquire[a[i]>0].tolist(),
                             available_min=available[a[i]>0].tolist(),
                             weights=a[i,a[i]>0].tolist()))
    covariance = block_diag(*blocks)
    return rows,covariance,info

def summarize_truth(frame, mode, look, sensor_set):
    rows,_,_ = observation_design(mode,look,sensor_set)
    t = np.asarray(frame['time_min'])
    return np.array([w @ np.interp(acq,t,np.asarray(frame[f])) for f,acq,w in rows])

def draw_summaries(frame, mode, n, seed, *, noise_scale=1., bias_scale=1.,
                   fast_phi=.6, gc_phi=.3, drift_scale=0., gain_sd=0.):
    """Generate raw instrument samples first, then causal summaries at both looks.

    All sensor configurations/looks share exactly the same instrument draws.
    Latent bias is drawn once per record; GC records retain acquisition delay.
    """
    rng = np.random.default_rng(seed)
    t = np.asarray(frame['time_min'])
    raw, metadata = {}, {}
    for f,cfg in sensor_settings(mode).items():
        aq = np.arange(0.,21.0001,cfg['period_min'])
        y = np.interp(aq,t,np.asarray(frame[f]))
        phi = gc_phi if f in GC else fast_phi
        e = rng.standard_normal((n,len(aq)))
        for j in range(1,len(aq)):
            e[:,j] = phi*e[:,j-1]+np.sqrt(1-phi**2)*e[:,j]
        b = rng.uniform(-1,1,(n,1))*cfg['bias_bound']*bias_scale
        drift = rng.uniform(-1,1,(n,1))*cfg['bias_bound']*drift_scale*(aq[None,:]/21.)
        gain = rng.normal(0,gain_sd,(n,1))
        raw[f] = y[None,:]*(1+gain)+b+drift+e*cfg['sd']*noise_scale
        metadata[f] = dict(acquired_min=aq,available_min=aq+cfg['delay_min'],bias=b[:,0])
    summaries = {}
    for look in LOOKS:
        for s in SETS:
            rows,_,_ = observation_design(mode,look,s)
            summaries[(look,s)] = np.stack([raw[f] @ w for f,_,w in rows],axis=1)
    # Retain a raw exemplar; every other record can be regenerated from input hash and seed.
    exemplar = {f: dict(value=raw[f][0],**{k:v if k!='bias' else v[0] for k,v in metadata[f].items()}) for f in FEATURES}
    return summaries,exemplar

def bank_parameters(mode,h):
    m = Map(mode); u = U_SS[mode]
    if h == 'H': return np.array([[1.,0.]])
    if h in ('C','M'):
        severity = np.linspace(.4,1.,41)
        rate = np.unique(np.r_[np.linspace(0,.015,11),[0,.003,.005,.006,.01]])
    elif h == 'F':
        severity = np.linspace(U_MIN/u,1.,31)
        rate = np.array([0.,.0005,.001,.0015,.002,.003])
    else:
        severity = np.linspace(-.2*SS[mode],0.,41)
        rate = SS[mode]*np.array([0.,-.0002,-.0005,-.001,-.002])
    roots = [m.severity_for_drop(h,d,u) for d in (.02,.05,.10)]
    severity = np.unique(np.r_[severity,[x for x in roots if x is not None]])
    p = np.array([(a,k) for a in severity for k in rate])
    if h in ('C','M','F'):
        end = p[:,0]*np.exp(-p[:,1]*11.)
        floor = U_MIN/u if h=='F' else .4
        p = p[end>=floor-1e-12]
    return p

def predict_bank(mode,h,params,active):
    m = Map(mode)
    u = np.where(TIMES>10.+1e-9,U_SS[mode]+MOVE,U_SS[mode]) if active else np.full_like(TIMES,U_SS[mode])
    a,k = params[:,0,None],params[:,1,None]
    shape = (len(params),len(TIMES))
    if h in ('C','M','F'):
        theta = np.minimum(1.,a*np.exp(-k*(TIMES[None,:]-10.)))
    else:
        theta = a+k*(TIMES[None,:]-10.)
    line = h if h in ('C','M') else 'C'
    health = theta if h in ('C','M') else np.ones(shape)
    uu = np.broadcast_to(u,shape).copy()
    if h=='F': uu *= theta
    result = {}
    for f in FEATURES:
        result[f] = m.spl[line][f].ev(health.ravel(),uu.ravel()).reshape(shape)
    if h=='S': result['H2_mol_min'] += theta
    return result

class DiagnosticBank:
    def __init__(self,mode,active):
        self.mode,self.active = mode,active
        self.params = {h:bank_parameters(mode,h) for h in HYP}
        self.pred = {h:predict_bank(mode,h,self.params[h],active) for h in HYP}
        self.cache = {}
        for look in LOOKS:
            for s in SETS:
                rows,cov,info = observation_design(mode,look,s)
                L = cholesky(cov,lower=True)
                vectors = {}
                for h in HYP:
                    vectors[h] = np.stack([self.pred[h][f][:,np.rint(acq*10).astype(int)] @ w for f,acq,w in rows],axis=1)
                origin = vectors['H'][0]
                white = {h:solve_triangular(L,(v-origin).T,lower=True).T for h,v in vectors.items()}
                self.cache[(look,s)] = (L,origin,white,info,cov)

    def score(self,obs,look,sensor_set):
        L,origin,white,_,_ = self.cache[(look,sensor_set)]
        z = solve_triangular(L,(np.asarray(obs)-origin).T,lower=True).T
        scores,indices = [],[]
        for h in HYP:
            d = cdist(z,white[h],metric='sqeuclidean')
            idx = d.argmin(axis=1)
            scores.append(d[np.arange(len(d)),idx]); indices.append(idx)
        return np.stack(scores,1),np.stack(indices,1)

    def fitted(self,h,index):
        return self.params[h][int(index)]

def rank_threshold(scores,alpha=.05):
    vals = np.asarray(scores,float)
    k = int(np.ceil((len(vals)+1)*(1-alpha)))
    return float(np.sort(vals)[k-1]) if k<=len(vals) else float('inf')

def decide(score_sequence,thresholds):
    """First singleton is final; otherwise retain explicit final inconclusive/empty sets."""
    scores = np.asarray(score_sequence)
    alive = np.logical_and.accumulate(scores<=np.asarray(thresholds)[None,None,:],axis=1)
    n = len(scores)
    decision = np.full(n,'INCONCLUSIVE',dtype='<U20'); when = np.full(n,21.)
    for i,look in enumerate(LOOKS):
        mask = (decision=='INCONCLUSIVE') & (alive[:,i].sum(1)==1)
        decision[mask] = np.array(HYP)[alive[mask,i].argmax(1)]; when[mask] = look
    final_empty = (decision=='INCONCLUSIVE') & (alive[:,-1].sum(1)==0)
    decision[final_empty] = 'MODEL_INCOMPATIBLE'
    return decision,when,alive

def command_grid(mode):
    return np.linspace(U_SS[mode],U_MAX,7)

def select_command(bank,look,alive,indices,end_time=31.):
    """Max of minimum restoring commands for retained plug-in fitted candidates.

    No service/recalibration benefit or monetary cost is invented. This is a
    declared bounded-feed policy, not an optimal or uniformly safe controller.
    """
    mode = bank.mode; m = Map(mode); grid = command_grid(mode)
    if not np.any(alive): return 0,True
    times = np.linspace(look,end_time,16)
    requirements=[]; cannot=False
    for j,h in enumerate(HYP):
        if not alive[j]: continue
        a,k = bank.fitted(h,indices[j])
        theta = np.minimum(1.,a*np.exp(-k*(times-10.))) if h in ('C','M','F') else np.ones_like(times)
        good=[]
        for ui,u in enumerate(grid):
            if h in ('H','S'): y=np.full_like(times,m.true_h2('S',0.,u))
            elif h=='F':
                actual=theta*u
                y=m.spl['C']['H2_mol_min'].ev(np.ones_like(times),actual) if np.all(actual>=U_MIN-1e-12) else np.full_like(times,-np.inf)
            else:
                y=m.spl[h]['H2_mol_min'].ev(theta,np.full_like(times,u)) if np.all(theta>=.4-1e-12) else np.full_like(times,-np.inf)
            if np.min(y)>=SS[mode]*(1-1e-6): good.append(ui)
        if good: requirements.append(min(good))
        else: requirements.append(len(grid)-1); cannot=True
    return max(requirements),cannot

if __name__=='__main__':
    # Engineering-only analytic checks, no reactor/evaluation results.
    for mode in (1,2):
        for look in LOOKS:
            for s in SETS:
                _,cov,info=observation_design(mode,look,s)
                assert np.linalg.eigvalsh(cov).min()>0
                assert all(max(r['available_min'])<=look for r in info)
    assert rank_threshold([1,2,3],.05)==float('inf')
    print('Observation covariance/causality and finite-rank edge checks pass.')
