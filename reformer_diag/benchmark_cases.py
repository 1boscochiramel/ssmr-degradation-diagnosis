"""Sampling/PID semantics of the upstream benchmark, with explicit time labels."""
from pathlib import Path
import time
import numpy as np
from scipy.integrate import solve_ivp
from scipy.io import loadmat
from model import Parameters,MODES,evaluate,jacobian_sparsity

ROOT=Path(__file__).resolve().parent


class PID:
    def __init__(self): self.integral=0.; self.previous=0.
    def step(self,dt,y,sp):
        ku=.1265; tau=.25
        e=sp-y; self.integral+=e*dt
        du=18*(.6*ku)*e+.01*((1.2*ku)/tau)*self.integral+(3*ku*tau)/40*(e-self.previous)/dt
        self.previous=e
        return du


def profile(ss,k,dt,kind):
    time=k*dt
    if kind==0: return ss
    if kind!=1: raise NotImplementedError('M1 uses original profiles 0 and 1 only')
    if 10<time<=15: return ss*1.15
    if 20<time<=25: return ss*.85
    return ss


def load_ic(mode,n,steam):
    folder='ICH2O' if steam else 'ICFull'
    name=f'Mode{mode}_np{n}'+('_H2O' if steam else '')+'.mat'
    src=ROOT.parent/'upstream/SSMR_simulator'/folder/name
    m=loadmat(src)
    assert int(m['np'][0,0])==n and m['x0c'].size==16*n
    return m['x0c'].ravel().copy(),m['u_ss'].ravel().copy(),str(src)


def simulate(name,case,settings):
    start=time.perf_counter(); n=case['np']; dt=settings['sample_min']
    x,u,source=load_ic(case['mode'],n,case.get('steam',False))
    pressure,temp,ss=MODES[case['mode']]
    pid=PID(); p=Parameters(pressure,temp,n)
    closed=case.get('closed_loop',False)
    rows=[]; dense=[]; diagnostics={'nfev':0,'njev':0,'nlu':0,'accepted_min':float(x.min()),'ic':source}
    callback={'last':None}
    sparsity=jacobian_sparsity(n)
    count=int(round(case['duration_min']/dt))+(1 if closed else 0)
    # Closed-loop legacy script loops over both endpoints, hence one extra interval.
    # Open-loop STEP/grid use exact physical horizons and explicit scheduled input.
    for index in range(count):
        k=index+1; t0=index*dt
        if closed:
            disturbance=case.get('disturbance',0)
            if k*dt>=case.get('disturbance_min',0)+.2:
                if disturbance==1.1: p=Parameters(pressure,temp*1.1,n)
                if disturbance==2.2: p=Parameters(pressure*.8,temp,n)
        elif t0>=case.get('step_min',float('inf'))-1e-12:
            u[0]=case['step_to_mol_min']
        sp=profile(ss,k,dt,case.get('profile',0))
        used=u.copy()
        def fun(t,y):
            f,obs=evaluate(y,used,p)
            callback['last']=obs['hydrogen_mol_min']
            return f
        sol=solve_ivp(fun,(0,dt),x,method=settings['method'],rtol=settings['rtol'],
             atol=settings['atol'],max_step=settings['max_step_min'],jac_sparsity=sparsity,dense_output=True)
        if not sol.success: raise RuntimeError(sol.message)
        last=callback['last']; x=sol.y[:,-1]
        endpoint=evaluate(x,used,p)[1]
        minimum=float(sol.y.min())
        if minimum < -settings['atol']:
            raise FloatingPointError(f'Accepted state {minimum} below -AbsTol')
        diagnostics['accepted_min']=min(diagnostics['accepted_min'],minimum)
        for metric in ('nfev','njev','nlu'): diagnostics[metric]+=getattr(sol,metric)
        rows.append([t0,t0,t0+dt,last,endpoint['hydrogen_mol_min'],used[0],used[1],sp,
                     endpoint['reformer_outlet_hydrogen_mol_m3'],endpoint['outlet_temperature_K']])
        if not closed:
            for tt in np.arange(0,dt+1e-10,settings['dense_sample_min']):
                yy=sol.sol(tt); obs=evaluate(yy,used,p)[1]
                dense.append([t0+tt,obs['hydrogen_mol_min'],used[0],obs['reformer_outlet_hydrogen_mol_m3']])
        if closed: u[0]=np.clip(u[0]+pid.step(dt,last,sp),.0018,.0024)
        if index%25==0: print(f'{name}: interval {index}/{count}',flush=True)
    diagnostics['wall_seconds']=time.perf_counter()-start
    return np.asarray(rows),np.asarray(dense),diagnostics
