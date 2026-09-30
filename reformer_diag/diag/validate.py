"""Validation gates V1 (quasi-steady vs full dynamics) and V2 (interpolation), protocol section 1.
Writes outputs_diag/validation.json and V1 traces. Gates are fixed in the protocol."""
from pathlib import Path
import json, sys
from multiprocessing import Pool
import numpy as np
from scipy.integrate import solve_ivp

HERE = Path(__file__).resolve().parent
OUT = HERE / 'outputs_diag'


def dynamic(d):
    """Authors' disturbance d (1 catalyst, 2 membrane) as upstream applies it: Parameters(time=k*t_s)."""
    from faultmodel import Parameters, MODES, evaluate, jacobian_sparsity, load_ic
    x, u, _ = load_ic(1, 50, False)
    u = np.array([.0021, u[1]])
    P, T, _ = MODES[1]
    sp = jacobian_sparsity(50)
    rows = []
    for k in range(1, 201):
        p = Parameters(P, T, 50, time=k * .1, disturbance=d)
        sol = solve_ivp(lambda t, y: evaluate(y, u, p)[0], (0, .1), x, method='BDF', rtol=1e-4, atol=1e-5,
                        max_step=.1, jac_sparsity=sp)
        if not sol.success:
            raise RuntimeError(sol.message)
        x = sol.y[:, -1]
        rows.append([k * .1, evaluate(x, u, p)[1]['hydrogen_mol_min']])
    return d, np.array(rows)


def direct(args):
    from faultmodel import steady_state
    line, a = args
    o, _, info = steady_state(1, a if line == 'C' else 1.0, a if line == 'M' else 1.0, .00215)
    return line, o, info


if __name__ == '__main__':
    from hypotheses import Map, SS, FEATURES
    with Pool(3) as pool:
        dyn = dict(pool.map(dynamic, [1, 2]))
        dirs = pool.map(direct, [('C', .85), ('M', .85)])
    m = Map(1)
    res = {'V1': {}, 'V2': {}}
    for d, h, rate in ((1, 'C', .01), (2, 'M', .006)):
        tr = dyn[d]
        pred = np.array([m.predict(h, np.exp(-rate * t), .0021)['H2_mol_min'] for t in tr[:, 0]])
        np.savetxt(OUT / f'V1_dynamic_d{d}.csv', np.c_[tr, pred], delimiter=',',
                   header='time_min,H2_dynamic_mol_min,H2_quasisteady_mol_min', comments='')
        mask = tr[:, 0] >= 1.0 - 1e-9
        dev = 100 * np.abs(tr[mask, 1] - pred[mask]) / SS[1]
        res['V1'][h] = {'max_dH2_pct_nominal': float(dev.max()), 'at_min': float(tr[mask, 0][dev.argmax()]),
                        'H2_drop_over_20min_pct': float(100 * (tr[0, 1] - tr[-1, 1]) / SS[1]),
                        'gate_pct': .5, 'status': 'PASS' if dev.max() <= .5 else 'FAIL'}
    for line, o, info in dirs:
        p = m.predict(line, .85, .00215)
        dH = 100 * abs(p['H2_mol_min'] - o['H2_mol_min']) / SS[1]
        res['V2'][line] = {'converged': info['converged'], 'dH2_pct_nominal': float(dH), 'gate_pct': .2,
                           'status': 'PASS' if dH <= .2 else 'FAIL',
                           'other_rel_diff_pct': {f: float(100 * abs(p[f] - o[f]) / abs(o[f])) for f in FEATURES}}
    (OUT / 'validation.json').write_text(json.dumps(res, indent=2) + '\n')
    print(json.dumps(res, indent=2))
