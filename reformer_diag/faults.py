"""Scenario scaffolding; no diagnosis or operating-map evaluation.

The exponential rates come from the pinned upstream Parameters.m, d=1/d=2.
They are synthetic benchmark schedules, not experimentally established lifetimes.
"""
from dataclasses import dataclass
import numpy as np

@dataclass(frozen=True)
class BenchmarkActivity:
    family: str
    onset_min: float

    def multiplier(self,time_min):
        if self.family not in ('catalyst','membrane'): raise ValueError('Unknown activity family')
        if not np.isfinite(self.onset_min): raise ValueError('Explicit finite onset required')
        rate={'catalyst':.01,'membrane':.006}[self.family]
        time=np.asarray(time_min,dtype=float)
        if not np.isfinite(time).all(): raise ValueError('Finite times required')
        return np.exp(-rate*np.maximum(time-self.onset_min,0))

def sensor_drift(time_min, *, onset_min, slope_per_min):
    """Explicit hypothetical additive sensor drift; no manufacturer claim."""
    if not np.isfinite(onset_min) or not np.isfinite(slope_per_min): raise ValueError('Finite explicit drift settings required')
    t=np.asarray(time_min,dtype=float)
    if not np.isfinite(t).all(): raise ValueError('Finite times required')
    return slope_per_min*np.maximum(t-onset_min,0)

def feed_multiplier(time_min, *, onset_min, multiplier_after):
    """Explicit synthetic feed-composition/flow step; preserve basis in future protocol."""
    if not np.isfinite(onset_min) or not np.isfinite(multiplier_after) or multiplier_after<0:
        raise ValueError('Finite onset and nonnegative explicit multiplier required')
    t=np.asarray(time_min,dtype=float)
    if not np.isfinite(t).all(): raise ValueError('Finite times required')
    return np.where(t>=onset_min,multiplier_after,1.)
