"""Independent reference arithmetic for the proposed revised audit.

Not frozen until the final protocol is agreed. No simulator or author statistic
module is imported. Inputs are raw matrices/records with explicit conventions.
"""
import math
import numpy as np
from scipy.stats import beta


def rank_threshold(scores, alpha):
    """Conservative split-rank threshold; ties retained by a strict > test."""
    x=np.asarray(scores,dtype=float)
    if x.ndim!=1 or len(x)==0 or not np.isfinite(x).all():
        raise ValueError('Calibration requires nonempty finite scalar scores')
    if not 0<alpha<1:raise ValueError('alpha must lie in (0,1)')
    # Round exact near-integers to avoid floating-point ceil off-by-one.
    z=(len(x)+1)*(1-alpha)
    k=int(round(z)) if abs(z-round(z))<1e-12 else math.ceil(z)
    return {'n':len(x),'rank':k,'threshold':float(np.sort(x)[k-1]) if k<=len(x) else math.inf}


def event_interval(k,n,confidence=.95):
    """Pointwise Clopper-Pearson two-sided interval and one-sided upper bound."""
    if not isinstance(k,(int,np.integer)) or not isinstance(n,(int,np.integer)) or not 0<=k<=n or n<1:
        raise ValueError('Counts must be integers with 0<=k<=n and n>0')
    tail=1-confidence
    return {'events':int(k),'n':int(n),'rate':k/n,
            'low':0. if k==0 else float(beta.ppf(tail/2,k,n-k+1)),
            'high':1. if k==n else float(beta.ppf(1-tail/2,k+1,n-k)),
            'upper_one_sided':1. if k==n else float(beta.ppf(confidence,k+1,n-k))}


def raw_covariance(sensor,indices,sigma,bias_bound,phi):
    """Stationary AR1 plus one independent Uniform[-B,B] bias per sensor.

    sigma and B may vary by row as fixed predetermined loadings. phi is either
    a common scalar or a mapping keyed by sensor. Sensors are independent.
    indices refer to generator sample order, not arrival order.
    """
    sensor=np.asarray(sensor);indices=np.asarray(indices,dtype=int)
    sigma=np.asarray(sigma,dtype=float);bias_bound=np.asarray(bias_bound,dtype=float)
    n=len(sensor)
    if any(len(x)!=n for x in [indices,sigma,bias_bound]):raise ValueError('Length mismatch')
    if (sigma<0).any() or (bias_bound<0).any():raise ValueError('Negative scale')
    out=np.zeros((n,n),dtype=float)
    for s in np.unique(sensor):
        sel=np.flatnonzero(sensor==s);rho=phi[s] if isinstance(phi,dict) else phi
        if not -1<rho<1:raise ValueError('Stationary phi must lie in (-1,1)')
        block=np.outer(sigma[sel],sigma[sel])*rho**np.abs(indices[sel,None]-indices[None,sel])
        block+=np.outer(bias_bound[sel],bias_bound[sel])/3
        out[np.ix_(sel,sel)]=block
    return out


def aggregated_covariance(weights,covariance):
    a=np.asarray(weights,dtype=float);k=np.asarray(covariance,dtype=float)
    if not np.allclose(k,k.T,atol=1e-13,rtol=1e-12):raise ValueError('Nonsymmetric raw covariance')
    return a@k@a.T


def closest_bank(observation,predictions,covariance):
    """Direct Cholesky residual score for every candidate-bank point."""
    y=np.asarray(observation,dtype=float);p=np.asarray(predictions,dtype=float);c=np.asarray(covariance,dtype=float)
    if p.ndim!=2 or p.shape[1]!=len(y):raise ValueError('Bank dimensions mismatch')
    if not np.isfinite(y).all() or not np.isfinite(p).all() or not np.isfinite(c).all():raise ValueError('Nonfinite score input')
    l=np.linalg.cholesky(c)
    e=np.linalg.solve(l,(y[None,:]-p).T)
    q=np.sum(e*e,axis=0);i=int(np.argmin(q))
    return {'index':i,'score':float(q[i]),'all_scores':q}


def sequential_decision(scores,thresholds,looks,labels):
    """Intersections across looks; early singleton; empty set classified finally."""
    z=np.asarray(scores,dtype=float);q=np.asarray(thresholds,dtype=float)
    if z.shape!=(len(looks),len(labels)) or q.shape!=(len(labels),):raise ValueError('Decision dimensions mismatch')
    alive=np.ones(len(labels),dtype=bool);history=[]
    for i,t in enumerate(looks):
        alive &= z[i]<=q
        survivors=[h for h,a in zip(labels,alive) if a];history.append(survivors)
        if len(survivors)==1:return {'decision':survivors[0],'time':float(t),'survivors':survivors,'history':history}
    return {'decision':'MODEL_INCOMPATIBLE' if not alive.any() else 'INCONCLUSIVE','time':float(looks[-1]),'survivors':history[-1],'history':history}


def physical_integrals(time,command,actual,h2,demand):
    """Endpoint trapezoids; supplied time axis must span the declared horizon."""
    t=np.asarray(time,dtype=float)
    arrays=[np.asarray(x,dtype=float) for x in [command,actual,h2,demand]]
    if len(t)<2 or not np.isfinite(t).all() or not (np.diff(t)>0).all():raise ValueError('Invalid time axis')
    if any(x.shape!=t.shape or not np.isfinite(x).all() for x in arrays):raise ValueError('Invalid physical array')
    u,ua,y,sp=arrays
    return {'command_ethanol_mol':float(np.trapezoid(u,t)),
            'actual_ethanol_mol':float(np.trapezoid(ua,t)),
            'H2_produced_mol':float(np.trapezoid(y,t)),
            'H2_demand_mol':float(np.trapezoid(sp,t)),
            'H2_shortfall_mol':float(np.trapezoid(np.maximum(sp-y,0),t)),
            'IAE_mol':float(np.trapezoid(np.abs(sp-y),t))}


def physical_intervals(start,end,command,actual_start,actual_end,h2_start,h2_end,demand_start,demand_end):
    """Switch-safe accounting: fixed command per interval, endpoint physics.

    H2/actual-rate trapezoids are the declared numerical quadrature, not an
    assertion of exact continuous-plant integrals. The command integral is
    exact for piecewise-constant actuation on these intervals.
    """
    arrays=[np.asarray(x,dtype=float) for x in [start,end,command,actual_start,actual_end,h2_start,h2_end,demand_start,demand_end]]
    t0,t1,u,a0,a1,y0,y1,s0,s1=arrays
    if any(x.shape!=t0.shape or not np.isfinite(x).all() for x in arrays):raise ValueError('Invalid interval arrays')
    if len(t0)==0 or not (t1>t0).all():raise ValueError('Empty/reversed intervals')
    if not np.allclose(t1[:-1],t0[1:],rtol=0,atol=1e-12):raise ValueError('Noncontiguous intervals')
    dt=t1-t0
    return {'command_ethanol_mol':float(np.sum(dt*u)),
            'actual_ethanol_mol':float(np.sum(dt*(a0+a1)/2)),
            'H2_produced_mol':float(np.sum(dt*(y0+y1)/2)),
            'H2_demand_mol':float(np.sum(dt*(s0+s1)/2)),
            'H2_shortfall_mol':float(np.sum(dt*(np.maximum(s0-y0,0)+np.maximum(s1-y1,0))/2)),
            'IAE_mol':float(np.sum(dt*(abs(s0-y0)+abs(s1-y1))/2))}
