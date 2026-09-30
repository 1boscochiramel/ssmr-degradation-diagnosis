"""Pre-evaluation amendment: restore nominal healthy-map output, not rounded text.

Physical performance is still reported against the benchmark demand. No service
benefit or economic price is assumed. Original frozen select_command is retained
in revision_model.py; this versioned policy is explicitly selected by the runner.
"""
import numpy as np
import revision_model as rm

def select_command(bank,look,alive,indices,end_time=31.):
    mode=bank.mode;m=rm.Map(mode);grid=rm.command_grid(mode)
    if not np.any(alive):return 0,True
    target=m.base('C',1.,rm.U_SS[mode])['H2_mol_min']
    # Only floating-point evaluation roundoff, not a physical acceptance margin.
    comparison_floor=target-64*np.finfo(float).eps*abs(target)
    times=np.linspace(look,end_time,16); requirements=[];cannot=False
    for j,h in enumerate(rm.HYP):
        if not alive[j]:continue
        a,k=bank.fitted(h,indices[j])
        theta=np.minimum(1.,a*np.exp(-k*(times-10.))) if h in ('C','M','F') else np.ones_like(times)
        good=[]
        for ui,u in enumerate(grid):
            if h in ('H','S'):y=np.full_like(times,m.true_h2('S',0.,u))
            elif h=='F':
                actual=theta*u
                y=m.spl['C']['H2_mol_min'].ev(np.ones_like(times),actual) if np.all(actual>=rm.U_MIN-1e-12) else np.full_like(times,-np.inf)
            else:
                y=m.spl[h]['H2_mol_min'].ev(theta,np.full_like(times,u)) if np.all(theta>=.4-1e-12) else np.full_like(times,-np.inf)
            if np.min(y)>=comparison_floor:good.append(ui)
        if good:requirements.append(min(good))
        else:requirements.append(len(grid)-1);cannot=True
    return max(requirements),cannot
