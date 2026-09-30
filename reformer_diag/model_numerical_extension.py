"""Faithful vectorized port of the pinned MIT-licensed SSMR MATLAB equations.

Upstream authors: Arcila-Osorio et al. See CITATION.cff and upstream/LICENSE.
AI-generated implementation draft for Bosco; fidelity is evaluated, not assumed.
"""
from dataclasses import dataclass
import numpy as np
from scipy.sparse import csr_matrix

STOICH=np.array([[-1,-1,0,0],[0,0,-1,-3],[0,1,0,0],[1,1,1,5],[0,1,-1,0],[0,0,1,2],[1,0,0,-1]],dtype=float)
CP_COEFF=np.array([
 [17.690,.14953,8.9481e-5,-1.9738e-7,8.3175e-11],
 [34.047,-9.6506e-3,3.2998e-5,-2.0447e-8,4.3023e-12],
 [38.387,-7.3663e-2,2.9098e-4,-2.6384e-7,8.0067e-11],
 [17.639,6.7005e-2,-1.3148e-4,1.0588e-7,-2.9180e-11],
 [29.006,2.4923e-3,-1.8644e-5,4.7989e-8,-2.8726e-11],
 [19.022,7.9629e-2,-7.3706e-5,3.7457e-8,-8.1330e-12],
 [24.528,7.6013e-2,1.3625e-4,-1.9994e-7,7.5955e-11]])
MODES={1:(4.,773.15,2.27354e-4),2:(6.,823.15,2.76379e-4),3:(8.,873.15,5.81357e-4)}


@dataclass
class Parameters:
    pressure_bar:float
    temperature:float
    np:int=50
    time:float=0.
    disturbance:int=0
    R:float=8.31432
    Patm:float=101325.
    Tref:float=773.15
    U:float=1500.
    diameter:float=.022
    length:float=.23
    separator_length:float=.076
    membrane_diameter:float=.125*.0254
    membrane_thickness:float=3e-5

    @property
    def pressure(self): return self.pressure_bar*1e5
    @property
    def area(self): return np.pi*self.diameter**2/4
    @property
    def dz1(self): return (self.length-self.separator_length)/self.np
    @property
    def dz2(self): return self.separator_length/self.np
    @property
    def kinf(self): return np.array([2.1e4,2e3,1.9e4,2e5])* (np.exp(-.01*self.time) if self.disturbance==1 else 1.)
    @property
    def pe0(self): return 2.25e-8*60*(np.exp(-.006*self.time) if self.disturbance==2 else 1.)


def heat_capacities(t):
    return sum(CP_COEFF[:,i,None]*t[None,:]**i for i in range(5))


def evaluate(x,u,p):
    """Return RHS and observables. No clipping or hidden numerical repairs."""
    z=np.asarray(x).reshape(2,8,p.np)
    c,t=z[0,:7],z[0,7]
    c2,t2=z[1,:7],z[1,7]
    if np.any(c2[3] < -1e-5):
        raise FloatingPointError("Separator hydrogen below original AbsTol; domain extension refused")
    if np.any(t<=0) or np.any(t2<=0):
        raise FloatingPointError('Nonpositive temperature or negative separator hydrogen encountered; no clipping applied')
    feed=np.r_[u,np.zeros(5)]
    cin=feed/feed.sum()*p.pressure/(p.R*p.temperature)
    vin=p.R*p.temperature/(p.area*p.pressure)*feed.sum()
    ea=np.array([7e4,1.3e5,7e4,9.8e4])
    kr=p.kinf[:,None]*np.exp(-ea[:,None]*(1/(p.R*t[None,:])-1/(p.R*p.Tref)))
    partial=c*p.R*t/1e5
    wgs=np.exp(4577.8/t-4.33)
    rates=kr*np.array([partial[0]/(7.96+5.82*(p.pressure_bar-1)),partial[0],
        partial[4]*partial[1]-partial[5]*partial[3]/wgs,partial[6]*partial[1]**3])
    ftot=feed.sum()+p.area*p.dz1*np.cumsum(rates[0]+2*rates[1]+3*rates[3])
    v=p.R*t/(p.pressure*p.area)*ftot
    flux=c*v
    dc=STOICH@rates-(flux-np.c_[vin*cin,flux[:,:-1]])/p.dz1
    cp=heat_capacities(t); cv=cp-p.R
    hr=-np.array([64600,49875,-41166,109136])@rates
    grad=(t-np.r_[p.temperature,t[:-1]])/p.dz1
    dt=(p.U*(4/p.diameter)*(p.temperature-t)+hr-(cp*c).sum(axis=0)*v*grad)/(cv*c).sum(axis=0)
    permeation=.32*p.pe0*np.exp(-8800/(p.R*t2))* (np.pi*p.membrane_diameter*p.dz2/p.membrane_thickness) * (np.sqrt(np.maximum(c2[3]*p.R*t2,0.))-np.sqrt(p.Patm))
    permeation=np.maximum(permeation,0.)  # Explicit upstream physical reverse-flow cutoff.
    sep_feed=p.area*v[-1]*c[:,-1].sum()
    f2=sep_feed-np.cumsum(permeation)
    v2=p.R*t2/(p.pressure*p.area)*f2
    flux2=c2*v2
    dc2=-(flux2-np.c_[v[-1]*c[:,-1],flux2[:,:-1]])/p.dz2
    loss=permeation/(p.area*p.dz2)
    dc2[3]-=loss
    cp2=heat_capacities(t2); cv2=cp2-p.R
    grad2=(t2-np.r_[t[-1],t2[:-1]])/p.dz1  # Preserve upstream dz1 in separator energy equation.
    dt2=(p.U*(4/p.diameter)*(p.temperature-t2)-(cp2*c2).sum(axis=0)*v2*grad2-loss*cv2[3]*t2)/(cv2*c2).sum(axis=0)
    rhs=np.stack([np.vstack([dc,dt]),np.vstack([dc2,dt2])]).ravel()
    obs={'hydrogen_mol_min':float(permeation.sum()),'outlet_temperature_K':float(t2[-1]),
         'waste_volume_m3_min':float(p.area*v2[-1]),'waste_concentrations_mol_m3':c2[:,-1].copy(),
         'reformer_outlet_hydrogen_mol_m3':float(c[3,-1])}
    if not np.isfinite(rhs).all(): raise FloatingPointError('Nonfinite model derivative')
    return rhs,obs


def jacobian_sparsity(n):
    # Conservative dependency pattern: upstream reaction cells affect downstream
    # cumulative velocities; separator fluxes depend on preceding separator cells.
    stage=np.repeat(np.arange(2),8*n)
    position=np.tile(np.arange(n),16)+stage*n
    mask=position[None,:]<=position[:,None]
    return csr_matrix(mask)
