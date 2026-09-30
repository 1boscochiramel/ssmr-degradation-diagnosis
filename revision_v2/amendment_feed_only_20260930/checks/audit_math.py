"""Independent physical accounting and blind schedule primitives; no model imports."""
import numpy as np

MEASURES=('H2_shortfall_mol','actual_ethanol_mol','commanded_ethanol_mol','H2_produced_mol','H2_demand_mol')
ATOL=1e-13
RTOL=1e-9

def array_close(a,b):
 a=np.asarray(a);b=np.asarray(b)
 return a.shape==b.shape and bool(np.allclose(a,b,atol=ATOL,rtol=RTOL,equal_nan=False))

def blind_command(t_start,baseline,increment,pulse_start,pulse_end):
 """The fixed schedule accepts no measurement, call, confidence or fitted value."""
 t=np.asarray(t_start,dtype=float)
 if pulse_end not in (16.,21.) or pulse_start!=10.:raise ValueError('Undeclared pulse schedule')
 return np.where((t>=pulse_start-1e-10)&(t<pulse_end-1e-10),baseline+increment,baseline)

def arm_key(case_id,original_stop):
 """Yoking uses the supplied original stop; it is not a new stopping rule."""
 if original_stop not in (16.,21.):raise ValueError('Undeclared original stop')
 return str(case_id),float(original_stop)

def account(intervals,demand_start,demand_end):
 dt=np.asarray(intervals['t_end'])-np.asarray(intervals['t_start'])
 if not np.all(dt>0):raise ValueError('Nonpositive physical interval')
 cmd=np.asarray(intervals['commanded_ethanol_mol_min'])
 a0=np.asarray(intervals['actual_ethanol_start']);a1=np.asarray(intervals['actual_ethanol_end'])
 y0=np.asarray(intervals['H2_start_mol_min']);y1=np.asarray(intervals['H2_end_mol_min'])
 q0=np.asarray(demand_start);q1=np.asarray(demand_end)
 if not all(x.shape==dt.shape and np.isfinite(x).all() for x in [cmd,a0,a1,y0,y1,q0,q1]):raise ValueError('Invalid interval data')
 arrays={
  'commanded_ethanol_mol':dt*cmd,
  'actual_ethanol_mol':dt*(a0+a1)/2,
  'H2_produced_mol':dt*(y0+y1)/2,
  'H2_demand_mol':dt*(q0+q1)/2,
  'H2_shortfall_mol':dt*(np.maximum(q0-y0,0)+np.maximum(q1-y1,0))/2,
 }
 return {k:float(v.sum()) for k,v in arrays.items()},arrays

def difference(policy,feed_only):
 return {name:float(policy[name]-feed_only[name]) for name in MEASURES}

def stats(values):
 x=np.asarray(values,dtype=float)
 if x.ndim!=1 or len(x)<2 or not np.isfinite(x).all():raise ValueError('Invalid descriptive sample')
 return {'mean':float(x.mean()),'std':float(x.std(ddof=1)),'min':float(x.min()),'max':float(x.max())}

def require_unique_keys(rows,keys,expected):
 observed=[tuple(r[k] for k in keys) for r in rows]
 if len(observed)!=len(set(observed)) or set(observed)!=set(expected):raise ValueError('Missing, duplicate or extra pairing keys')
