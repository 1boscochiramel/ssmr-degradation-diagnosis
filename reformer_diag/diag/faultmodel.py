"""Fault multipliers and steady states on the Python port (model.py is used unchanged).
Protocol: PROTOCOL_2026-09-30_M2_M4.md section 1."""
from dataclasses import dataclass
from pathlib import Path
import sys
import numpy as np
from scipy.integrate import solve_ivp

PKG = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PKG))
from model import Parameters, MODES, evaluate, jacobian_sparsity  # noqa: E402
from benchmark_cases import load_ic  # noqa: E402

KINF = np.array([2.1e4, 2e3, 1.9e4, 2e5])
PE0 = 2.25e-8 * 60
GC_SPECIES = {'H2': 3, 'CH4': 2, 'CO': 4, 'CO2': 5}   # index in the 7-species order


@dataclass
class FaultParameters(Parameters):
    """Parameters with explicit catalyst (a_c) and membrane (a_m) multipliers."""
    a_c: float = 1.0
    a_m: float = 1.0

    @property
    def kinf(self):
        return KINF * self.a_c

    @property
    def pe0(self):
        return PE0 * self.a_m


def observables(obs):
    c = np.asarray(obs['waste_concentrations_mol_m3'], dtype=float)
    frac = c / c.sum()
    out = {'H2_mol_min': obs['hydrogen_mol_min'], 'T_out_K': obs['outlet_temperature_K'],
           'waste_m3_min': obs['waste_volume_m3_min']}
    for name, i in GC_SPECIES.items():
        out[f'y_{name}'] = float(frac[i])
    return out


def steady_state(mode, a_c=1.0, a_m=1.0, u_etoh=None, n=50, x0=None, max_min=12.0):
    """Integrate to steady state; returns (observables dict, final state, info)."""
    x, u, _ = load_ic(mode, n, False)
    if x0 is not None:
        x = np.asarray(x0, dtype=float).copy()
    if u_etoh is not None:
        u = np.array([u_etoh, u[1]])
    pressure, temp, _ = MODES[mode]
    p = FaultParameters(pressure, temp, n, a_c=a_c, a_m=a_m)
    sp = jacobian_sparsity(n)
    fun = lambda t, y: evaluate(y, u, p)[0]
    t_done, h_hist, converged = 0.0, [], False
    while t_done < max_min:
        sol = solve_ivp(fun, (0, 1.0), x, method='BDF', rtol=1e-6, atol=1e-8, jac_sparsity=sp, dense_output=True)
        if not sol.success:
            raise RuntimeError(sol.message)
        h_mid = evaluate(sol.sol(0.5), u, p)[1]['hydrogen_mol_min']
        x = sol.y[:, -1]
        h_end = evaluate(x, u, p)[1]['hydrogen_mol_min']
        t_done += 1.0
        h_hist.append(h_end)
        if t_done >= 2.0 and abs(h_end - h_mid) <= 1e-6 * abs(h_end):
            converged = True
            break
    o = observables(evaluate(x, u, p)[1])
    info = {'converged': converged, 'minutes': t_done, 'u_etoh': float(u[0]), 'u_water': float(u[1]),
            'a_c': a_c, 'a_m': a_m, 'mode': mode, 'np': n}
    return o, x, info
