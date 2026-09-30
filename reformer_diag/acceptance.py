"""Pre-run acceptance definitions. Keep failed results; never tune these to pass."""
import numpy as np
from scipy.optimize import least_squares


def tracking(trace,target,tolerance):
    t=trace[:,0]; e=trace[:,7]-trace[:,3]
    conventional=float(np.trapezoid(np.abs(e),t))
    literal=float(np.sum(np.abs((e[1:]+e[:-1])/2)*np.diff(t)))
    dev=100*abs(conventional-target)/abs(target)
    return {'published_iae_mol':target,'conventional_iae_mol':conventional,
            'paper_literal_iae_mol':literal,'relative_deviation_pct':dev,
            'status':'PASS' if dev<=tolerance else 'FAIL',
            'paper_literal_deviation_pct':100*abs(literal-target)/abs(target)}


def dynamics(dense,tau_target,delay_target,tolerance):
    _,unique=np.unique(np.round(dense[:,0],10),return_index=True)
    d=dense[np.sort(unique)]; t=d[:,0]; y=d[:,1]
    y0=float(y[(t>=1.8-1e-10)&(t<=2+1e-10)].mean())
    yf=float(y[(t>=3.8-1e-10)&(t<=4+1e-10)].mean())
    mask=(t>=2-1e-10)&(t<=4+1e-10)
    tx=t[mask]-2; yy=y[mask]
    def prediction(v): return y0+(yf-y0)*(1-np.exp(-np.maximum(tx-v[0],0)/v[1]))
    def residual(v): return (prediction(v)-yy)/max(abs(yf-y0),1e-15)
    fits=[]
    for start in ([.15,.25],[.05,.05],[.3,.5]):
        r=least_squares(residual,start,bounds=([0,.001],[1,2]),xtol=1e-12,ftol=1e-12,gtol=1e-12)
        fits.append({'start':start,'delay_min':float(r.x[0]),'tau_min':float(r.x[1]),'cost':float(r.cost),'success':bool(r.success)})
    best=min(fits,key=lambda z:z['cost']); delta=100*abs(best['tau_min']-tau_target)/tau_target
    errors=prediction([best['delay_min'],best['tau_min']])-yy
    return {**best,'all_starts':fits,'published_tau_min':tau_target,'published_delay_min':delay_target,
            'tau_deviation_pct':delta,'delay_deviation_pct':100*abs(best['delay_min']-delay_target)/delay_target,
            'fit_rmse_mol_min':float(np.sqrt(np.mean(errors**2))),'fit_max_residual_mol_min':float(np.max(np.abs(errors))),
            'bound_contact':bool(best['delay_min']<1e-7 or best['delay_min']>1-1e-7 or best['tau_min']<.0010001 or best['tau_min']>1.9999999),
            'status':'PASS' if delta<=tolerance else 'FAIL_DYNAMICS_REFERENCE_AMBIGUITY'}


def trajectory(trace,reference,nominal,uncertainty,tolerance,physical=False):
    t=trace[:,2] if physical else trace[:,0]
    y=trace[:,4] if physical else trace[:,3]
    valid=(t>=reference[0,0])&(t<=reference[-1,0])
    t=t[valid]; y=y[valid]
    ref=np.interp(t,reference[:,0],reference[:,1]); err=np.abs(y-ref)
    maxerr=float(err.max())
    # Bound uncertainty from axis quantization and local plotted slopes.
    slope=np.abs(np.diff(reference[:,1])/np.maximum(np.diff(reference[:,0]),1e-15)).max()
    bound=uncertainty['vertical_rounding_bound_mol_min']+slope*uncertainty['horizontal_rounding_bound_min']
    pct=100*maxerr/nominal; boundpct=100*bound/nominal
    state='PASS' if pct+boundpct<=tolerance else ('FAIL' if pct-boundpct>tolerance else 'UNRESOLVED_REFERENCE_PRECISION')
    return {'max_absolute_deviation_mol_min':maxerr,'max_nominal_deviation_pct':pct,
            'reference_uncertainty_bound_mol_min':float(bound),'status':state,'samples_compared':int(len(t)),
            'time_definition':'physical accepted endpoints' if physical else 'upstream display labels and last RHS output'}
