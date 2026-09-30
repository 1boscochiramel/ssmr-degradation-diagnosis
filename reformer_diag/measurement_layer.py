"""Measurement scaffolding. Explicit sensor settings; no plant-specific defaults.

Only generation sees declared truth signals. Consumers receive readings, never
the source states/fault labels. No identifiability experiment is run here.
"""
from dataclasses import dataclass
import numpy as np

@dataclass(frozen=True)
class Sensor:
    name: str
    unit: str
    sample_period_min: float
    delay_min: float
    noise_std: float
    bias: float

    def __post_init__(self):
        if not self.name or not self.unit: raise ValueError('name and unit required')
        if not all(np.isfinite(v) for v in [self.sample_period_min,self.delay_min,self.noise_std,self.bias]):
            raise ValueError('sensor settings must be finite')
        if self.sample_period_min<=0 or self.delay_min<0 or self.noise_std<0:
            raise ValueError('period must be positive; delay/noise cannot be negative')

@dataclass(frozen=True)
class Sample:
    sensor: str
    acquired_min: float
    available_min: float
    value: float
    unit: str

def generate_samples(times, values, sensor: Sensor, *, seed: int):
    t=np.asarray(times,dtype=float); y=np.asarray(values,dtype=float)
    if t.ndim!=1 or y.shape!=t.shape or len(t)<2 or not np.isfinite(t).all() or not np.isfinite(y).all():
        raise ValueError('finite one-dimensional matching source signal required')
    if not np.all(np.diff(t)>0): raise ValueError('strictly increasing acquisition time required')
    query=np.arange(t[0],t[-1]+1e-12,sensor.sample_period_min)
    # Interpolation is an explicit simulator-to-instrument transformation, never
    # interpolation of missing instrument observations back into truth states.
    observed=np.interp(query,t,y)+sensor.bias+np.random.default_rng(seed).normal(0,sensor.noise_std,len(query))
    return tuple(Sample(sensor.name,float(ts),float(ts+sensor.delay_min),float(v),sensor.unit) for ts,v in zip(query,observed))

def available_samples(samples, now_min):
    return tuple(s for s in samples if s.available_min<=now_min)
