"""Schema-independent reconstruction used by the revised campaign checker.

No author model/diagnosis modules imported. Source inputs are the frozen JSON
protocol and raw steady maps. Subject to integration freeze before evaluation.
"""
import numpy as np
import pandas as pd
from scipy.interpolate import RectBivariateSpline
from scipy.optimize import brentq
from scipy.linalg import solve_triangular
from reference_math import raw_covariance,aggregated_covariance

FEATURES=['H2_mol_min','T_out_K','waste_m3_min','y_H2','y_CH4','y_CO','y_CO2']
HYP=['C','M','F','S','H'];SS={1:2.27354e-4,2:2.76379e-4};U0={1:.0021,2:.0018};UMIN=.0018;UMAX=.0024

def design(protocol,mode,look,sensor_set):
    settings=protocol['observation_models'][str(mode)]
    bins=protocol['measurement_windows_min'][:3 if look==16 else 4]
    rows=[];blocks=[];info=[]
    for feature in protocol['sensor_sets'][sensor_set]:
        cfg=settings[feature];times=np.arange(0.,21.0001,cfg['period_min']);arr=times+cfg['delay_min']
        w=[]
        for lo,hi in bins:
            mask=(times>lo+1e-9)&(times<=hi+1e-9)&(arr<=look+1e-9)
            if not mask.any():raise ValueError('Empty declared sensor window')
            weights=mask.astype(float)/mask.sum();w.append(weights);rows.append((feature,times,weights))
            info.append(dict(feature=feature,lo_min=lo,hi_min=hi,acquired_min=times[mask].tolist(),available_min=arr[mask].tolist(),weights=weights[mask].tolist()))
        k=raw_covariance([feature]*len(times),np.arange(len(times)),np.full(len(times),cfg['sd']),np.full(len(times),cfg['bias_bound']),cfg['phi'])
        blocks.append(aggregated_covariance(w,k))
    sizes=[len(x) for x in blocks];cov=np.zeros((sum(sizes),sum(sizes)));at=0
    for block in blocks:cov[at:at+len(block),at:at+len(block)]=block;at+=len(block)
    return rows,cov,info

def regenerate(protocol,frame,mode,n,seed,kwargs):
    """Recreate raw streams and both-look summaries from the frozen RNG recipe."""
    ns=kwargs.get('noise_scale',1.);bs=kwargs.get('bias_scale',1.);fp=kwargs.get('fast_phi',.6);gp=kwargs.get('gc_phi',.3)
    ds=kwargs.get('drift_scale',0.);gs=kwargs.get('gain_sd',0.)
    if set(kwargs)-{'noise_scale','bias_scale','fast_phi','gc_phi','drift_scale','gain_sd'}:raise ValueError('Unknown noise controls')
    rng=np.random.default_rng(seed);raw={};exemplar={};settings=protocol['observation_models'][str(mode)]
    for f in FEATURES:
        cfg=settings[f];aq=np.arange(0.,21.0001,cfg['period_min']);truth=np.interp(aq,frame['time_min'],frame[f])
        rho=gp if cfg['delay_min']>0 else fp
        innovations=rng.standard_normal((n,len(aq)));e=np.empty_like(innovations);e[:,0]=innovations[:,0]
        for j in range(1,len(aq)):e[:,j]=rho*e[:,j-1]+np.sqrt(1-rho*rho)*innovations[:,j]
        bias=rng.uniform(-1,1,(n,1))*cfg['bias_bound']*bs
        drift=rng.uniform(-1,1,(n,1))*cfg['bias_bound']*ds*(aq[None,:]/21)
        gain=rng.normal(0,gs,(n,1))
        raw[f]=truth[None,:]*(1+gain)+bias+drift+e*cfg['sd']*ns
        exemplar[f]=dict(value=raw[f][0],acquired_min=aq,available_min=aq+cfg['delay_min'],bias=bias[0,0])
    summaries={}
    for look in protocol['looks_min']:
        for sensor_set in protocol['sensor_sets']:
            rows,_,_=design(protocol,mode,look,sensor_set)
            # Explicit sample weighting makes the causal aggregation independent
            # of the author's raw-matrix multiplication implementation.
            summaries[(int(look),sensor_set)]=np.asarray([np.sum(raw[f][:,w>0]*w[w>0],axis=1) for f,_,w in rows]).T
    return summaries,exemplar,raw

def map_splines(path):
    df=pd.read_csv(path,float_precision='round_trip');good=df[(df.converged.astype(str)=='True')&(df.error.isna()|(df.error.astype(str)==''))]
    result={}
    for h,param,fixed in [('C','a_c','a_m'),('M','a_m','a_c')]:
        part=good[good[fixed]==1];aa=np.sort(part[param].unique());uu=np.sort(part.u_etoh.unique());sub={}
        for feature in FEATURES:
            values=np.array([[part[(part[param]==a)&(part.u_etoh==u)][feature].iloc[0] for u in uu] for a in aa])
            sub[feature]=RectBivariateSpline(aa,uu,values,kx=3,ky=3)
        result[h]=sub
    return result

def bank_parameters(mode,h,spl):
    if h=='H':return np.array([[1.,0.]])
    if h in ['C','M']:
        severity=np.linspace(.4,1,41);rates=np.unique(np.r_[np.linspace(0,.015,11),[0,.003,.005,.006,.01]])
    elif h=='F':severity=np.linspace(UMIN/U0[mode],1,31);rates=np.array([0,.0005,.001,.0015,.002,.003])
    else:severity=np.linspace(-.2*SS[mode],0,41);rates=SS[mode]*np.array([0,-.0002,-.0005,-.001,-.002])
    base=float(spl['C']['H2_mol_min'](1,U0[mode])[0,0]);roots=[]
    def predicted(theta):
        if h in ['C','M']:return float(spl[h]['H2_mol_min'](theta,U0[mode])[0,0])
        if h=='F':return float(spl['C']['H2_mol_min'](1,theta*U0[mode])[0,0])
        return base+theta
    lo,hi=(.4,1.) if h in ['C','M'] else ((UMIN/U0[mode],1.) if h=='F' else (-.2*SS[mode],0.))
    for drop in [.02,.05,.10]:
        def objective(theta):return predicted(theta)-base*(1-drop)
        if objective(lo)*objective(hi)<=0:roots.append(brentq(objective,lo,hi,xtol=1e-12))
    severity=np.unique(np.r_[severity,roots]);params=np.asarray([(a,k) for a in severity for k in rates])
    if h in ['C','M','F']:
        floor=UMIN/U0[mode] if h=='F' else .4
        params=params[params[:,0]*np.exp(-11*params[:,1])>=floor-1e-12]
    return params

def build_bank(protocol,map_path,mode,active):
    spl=map_splines(map_path);times=np.round(np.arange(0.,21.0001,.1),8)
    command=np.full(len(times),U0[mode]);command[(times>10.+1e-9)&active]+=protocol['active_feed_increment']
    params={};vectors={};covariances={};infos={}
    for h in HYP:
        p=bank_parameters(mode,h,spl);params[h]=p;a=p[:,0,None];rate=p[:,1,None]
        theta=np.minimum(1,a*np.exp(-rate*(times[None,:]-10))) if h in ['C','M','F'] else a+rate*(times[None,:]-10)
        health=theta if h in ['C','M'] else np.ones((len(p),len(times)));u=np.broadcast_to(command,health.shape).copy()
        if h=='F':u*=theta
        pred={f:spl[h if h in ['C','M'] else 'C'][f].ev(health.ravel(),u.ravel()).reshape(health.shape) for f in FEATURES}
        if h=='S':pred['H2_mol_min']+=theta
        for look in protocol['looks_min']:
            for ss in protocol['sensor_sets']:
                rows,cov,info=design(protocol,mode,look,ss);key=(ss,int(look));covariances[key]=cov;infos[key]=info
                vectors[(ss,int(look),h)]=np.stack([np.sum(pred[f][:,np.rint(aq[w>0]*10).astype(int)]*w[w>0],axis=1) for f,aq,w in rows],axis=1)
    return params,vectors,covariances,infos

def scores_all(obs,pred,cov):
    """Batched independent squared-distance identity, followed by direct minima."""
    origin=pred[0];l=np.linalg.cholesky(cov)
    z=solve_triangular(l,(obs-origin).T,lower=True).T;b=solve_triangular(l,(pred-origin).T,lower=True).T
    scores=np.empty(len(z));indices=np.empty(len(z),dtype=int);chosen=[]
    bn=np.sum(b*b,axis=1)
    for start in range(0,len(z),128):
        zz=z[start:start+128];zn=np.sum(zz*zz,axis=1);d=zn[:,None]+bn[None,:]-2*(zz@b.T)
        ix=np.argmin(d,axis=1);value=np.empty(len(zz))
        # Reconsider every template within a conservative arithmetic-error
        # envelope of the quadratic-identity minimum, then use direct norms.
        err=16*(z.shape[1]+1)*np.finfo(float).eps*(zn[:,None]+bn[None,:]+2*np.sqrt(zn[:,None]*bn[None,:]))
        for j in range(len(zz)):
            contenders=np.flatnonzero(d[j]<=d[j,ix[j]]+err[j]+err[j,ix[j]])
            direct=np.sum((b[contenders]-zz[j])**2,axis=1);best=int(np.argmin(direct))
            ix[j]=contenders[best];value[j]=direct[best]
        scores[start:start+len(zz)]=value;indices[start:start+len(zz)]=ix
    return scores,indices
