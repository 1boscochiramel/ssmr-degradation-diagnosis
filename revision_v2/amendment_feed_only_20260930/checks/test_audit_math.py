"""Synthetic physical/schedule fixtures only; no amendment outcomes are read."""
from pathlib import Path
import json
import numpy as np
from audit_math import blind_command,arm_key,account,difference,stats,require_unique_keys,array_close

checks=[]
def check(name,value):
 assert bool(value),name
 checks.append(name)
def rejects(name,fn):
 try:fn()
 except ValueError:checks.append(name)
 else:raise AssertionError(name)

t0=np.array([0.,10.,16.]);t1=np.array([10.,16.,31.]);u0=.0018;du=.0003
cmd=blind_command(t0,u0,du,10.,16.)
check('nominal-pulse-nominal schedule',np.array_equal(cmd,[u0,u0+du,u0]))
iv=dict(t_start=t0,t_end=t1,commanded_ethanol_mol_min=cmd,actual_ethanol_start=.8*cmd,actual_ethanol_end=.8*cmd,
        H2_start_mol_min=np.array([.5,.5,1.]),H2_end_mol_min=np.array([.5,1.,1.]))
cost,parts=account(iv,np.ones(3),np.ones(3))
check('switch-safe command amount',array_close(cost['commanded_ethanol_mol'],31*u0+6*du))
check('actual delivered feed differs from command',array_close(cost['actual_ethanol_mol'],.8*(31*u0+6*du)))
check('shortfall physical amount',cost['H2_shortfall_mol']==6.5)
check('total hydrogen amount',cost['H2_produced_mol']==24.5)
check('demand amount',cost['H2_demand_mol']==31.)
check('paired direction uses policy minus comparator',difference({k:3. for k in cost},{k:2. for k in cost})=={k:1. for k in cost})
check('identical physical accounts give zero',all(v==0 for v in difference(cost,cost).values()))
check('sample standard deviation',stats([1,3])==dict(mean=2.,std=float(np.sqrt(2)),min=1.,max=3.))
check('same case and stop select same arm regardless of unused call',arm_key('case',16.)==('case',16.))
rejects('reject wrong pulse end',lambda:blind_command(t0,u0,du,10.,17.))
rejects('reject wrong pulse start',lambda:blind_command(t0,u0,du,9.,16.))
rejects('reject wrong original stop',lambda:arm_key('case',20.))
rejects('reject invalid interval',lambda:account(dict(iv,t_end=t0),np.ones(3),np.ones(3)))
expected={('case','S1',0),('case','S1',1)}
rows=[dict(case='case',set='S1',trial=i) for i in [0,1]]
require_unique_keys(rows,['case','set','trial'],expected);checks.append('complete keys accepted')
rejects('reject duplicate',lambda:require_unique_keys(rows+[rows[0]],['case','set','trial'],expected))
rejects('reject missing',lambda:require_unique_keys(rows[:1],['case','set','trial'],expected))
rejects('reject wrong case',lambda:require_unique_keys([dict(case='other',set='S1',trial=i) for i in [0,1]],['case','set','trial'],expected))
check('wrong reported integral rejected',not array_close(cost['commanded_ethanol_mol'],cost['commanded_ethanol_mol']+du))
check('wrong contrast sign rejected',not array_close(1.,-1.))
out=dict(pass_=True,checks=checks,count=len(checks),scope='Analytic fixtures before amendment outcomes; no reactor validation')
out['pass']=out.pop('pass_')
(Path(__file__).resolve().parent/'math_selftest.json').write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2))
