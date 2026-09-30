"""Hypothesis predictors from the quasi-steady map (protocol sections 1 and 3)."""
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.interpolate import RectBivariateSpline
from scipy.optimize import brentq

HERE = Path(__file__).resolve().parent
OUT = HERE / 'outputs_diag'
FEATURES = ['H2_mol_min', 'T_out_K', 'waste_m3_min', 'y_H2', 'y_CH4', 'y_CO', 'y_CO2']
U_MIN, U_MAX = .0018, .0024
U_SS = {1: .0021, 2: .0018}
SS = {1: 2.27354e-4, 2: 2.76379e-4}     # set-point `ss` in SSMR_simulation.m
MOVE = .0003                            # feed-move size, protocol section 2


class Map:
    def __init__(self, mode):
        df = pd.read_csv(OUT / f'map_mode{mode}.csv')
        self.mode = mode
        self.raw = df
        bad = df[(df['converged'].astype(str) != 'True') | df['error'].notna() & (df['error'].astype(str) != '')]
        self.bad = bad
        good = df.drop(bad.index)
        nominal = good[(good.a_c == 1) & (good.a_m == 1)]
        cat = good[good.a_m == 1]
        mem = pd.concat([good[(good.a_c == 1) & (good.a_m < 1)], nominal])
        self.spl = {'C': self._fit(cat, 'a_c'), 'M': self._fit(mem, 'a_m')}

    @staticmethod
    def _fit(d, col):
        a = np.sort(d[col].unique()); u = np.sort(d['u_etoh'].unique())
        out = {}
        for f in FEATURES:
            z = d.pivot_table(index=col, columns='u_etoh', values=f).reindex(index=a, columns=u).values
            if np.isnan(z).any():
                raise ValueError(f'map hole in {col} line for {f}; see map CSV (non-converged points are not interpolated over)')
            out[f] = RectBivariateSpline(a, u, z, kx=3, ky=3)
        return out

    def base(self, line, a, u):
        return {f: float(s(a, u)[0, 0]) for f, s in self.spl[line].items()}

    def predict(self, h, theta, u_cmd):
        """Observed feature vector under hypothesis h with severity theta at ethanol command u_cmd."""
        if h == 'C':
            return self.base('C', theta, u_cmd)
        if h == 'M':
            return self.base('M', theta, u_cmd)
        if h == 'F':
            return self.base('C', 1.0, theta * u_cmd)
        if h == 'S':
            o = self.base('C', 1.0, u_cmd)
            o['H2_mol_min'] += theta
            return o
        raise ValueError(h)

    def true_h2(self, h, theta, u_cmd):
        """True delivered H2 (sensor drift does not change the process)."""
        if h == 'S':
            return self.base('C', 1.0, u_cmd)['H2_mol_min']
        return self.predict(h, theta, u_cmd)['H2_mol_min']

    def range(self, h, u_cmd):
        if h in ('C', 'M'):
            return (.4, 1.0)
        if h == 'F':
            return (U_MIN / u_cmd, 1.0)
        if h == 'S':
            return (-.2 * SS[self.mode], 0.0)
        raise ValueError(h)

    def severity_for_drop(self, h, drop, u_cmd):
        """theta giving an observed H2 drop `drop` (fraction of nominal) at u_cmd; None if unreachable."""
        h0 = self.base('C', 1.0, u_cmd)['H2_mol_min']
        target = h0 * (1 - drop)
        lo, hi = self.range(h, u_cmd)
        g = lambda th: self.predict(h, th, u_cmd)['H2_mol_min'] - target
        if g(lo) * g(hi) > 0:
            return None
        return brentq(g, lo, hi, xtol=1e-12)

    def u_required(self, h, theta):
        """Command restoring TRUE H2 to the set-point; np.inf if not reachable at U_MAX."""
        target = SS[self.mode]
        if h == 'S':
            return U_SS[self.mode]
        if h == 'F':
            g0 = lambda u: self.base('C', 1.0, u)['H2_mol_min'] - target
            u0 = U_MIN if g0(U_MIN) >= 0 else brentq(g0, U_MIN, U_MAX, xtol=1e-12)
            return u0 / theta
        g = lambda u: self.base(h, theta, u)['H2_mol_min'] - target
        if g(U_MAX) < 0:
            return np.inf
        if g(U_MIN) >= 0:
            return U_MIN
        return brentq(g, U_MIN, U_MAX, xtol=1e-12)


def action(m, h, theta):
    if h == 'S':
        return 'RECALIBRATE'
    u = m.u_required(h, theta)
    if u <= U_MAX + 1e-12:
        return 'COMPENSATE'
    return {'C': 'SERVICE_CATALYST', 'M': 'SERVICE_MEMBRANE', 'F': 'REPAIR_FEED'}[h]
