"""Small analytic fixtures for reference math, run before simulation evaluation."""
import json,math
from pathlib import Path
import numpy as np
import reference_math as r
passed=[]
def case(name,condition):
    assert condition,name
    passed.append(name)

case('rank includes n+1 correction',r.rank_threshold(np.arange(19),.05)=={'n':19,'rank':19,'threshold':18.})
case('insufficient calibration uses infinity',math.isinf(r.rank_threshold(np.arange(18),.05)['threshold']))
case('rank repeated-score ties retained',r.rank_threshold(np.ones(19),.05)['threshold']==1)
a=np.asarray([[1,0,0],[-1,.5,.5]])
k=r.raw_covariance(['H2']*3,[0,1,2],[1]*3,[0]*3,0)
case('shared baseline covariance negative',np.allclose(r.aggregated_covariance(a,k),[[1,-1],[-1,1.5]]))
k=r.raw_covariance(['H2']*3,[0,1,2],[1]*3,[math.sqrt(3)]*3,0)
case('constant bias persists only in level',np.allclose(r.aggregated_covariance(a,k),[[2,-1],[-1,1.5]]))
k=r.raw_covariance(['H2','H2','T'],[0,2,0],[2,2,1],[0,0,0],.5)
case('AR1 physical sample lag and independent sensors',np.allclose(k,[[4,1,0],[1,4,0],[0,0,1]]))
z=r.closest_bank([2,3],[[0,0],[1,1]],[[1,0],[0,4]])
case('nearest bank recomputed with nonzero true score',z['index']==1 and z['score']==2)
q=r.sequential_decision([[1,2],[0,0]],[1,1],[16,21],['C','M'])
case('strict rejection ties and causal early stop',q['decision']=='C' and q['time']==16 and len(q['history'])==1)
q=r.sequential_decision([[2,2],[0,0]],[1,1],[16,21],['C','M'])
case('excluded candidates cannot reenter',q['decision']=='MODEL_INCOMPATIBLE')
q=r.sequential_decision([[0,0],[0,0]],[1,1],[16,21],['C','M'])
case('multiple survivors are inconclusive',q['decision']=='INCONCLUSIVE')
z=r.physical_intervals([0,1],[1,2],[1,2],[1,2],[1,2],[.5,.5],[.5,.5],[1,1],[1,1])
case('switch-safe command total and H2 shortfall',z['command_ethanol_mol']==3 and z['actual_ethanol_mol']==3 and z['H2_shortfall_mol']==1)
z2=r.physical_intervals([0,1],[1,2],[1.1,2.1],[1.1,2.1],[1.1,2.1],[.5,.5],[.5,.5],[1,1],[1,1])
case('same action name cannot erase actual feed difference',abs(z2['actual_ethanol_mol']-z['actual_ethanol_mol']-.2)<1e-14)
ci=r.event_interval(0,100)
case('zero events is not zero upper risk',ci['rate']==0 and abs(ci['upper_one_sided']-(1-.05**.01))<1e-12)
out={'pass':True,'analytic_checks':passed,'count':len(passed),'scope':'Analytic math fixtures only. Full schema negative controls follow final protocol freeze; no scientific evaluation results inspected.'}
p=Path(__file__).with_name('reference_math_selftest.json');p.write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2))
