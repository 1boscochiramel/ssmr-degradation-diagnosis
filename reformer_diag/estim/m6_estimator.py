"""M6 v0: MHE and EKF health estimators on held-out deterioration histories (PROTOCOL_2026-09-30_M6.md).
Writes outputs/m6_runs.csv, outputs/m6_summary.json, outputs/m6_traces/*.csv (one per run)."""
from pathlib import Path
import itertools, json, sys
import numpy as np
import pandas as pd
from scipy.interpolate import RectBivariateSpline, CubicSpline
from scipy.optimize import least_squares
from scipy.stats import chi2

HERE = Path(__file__).resolve().parent
D = HERE.parent / 'diag' / 'outputs_diag'
import os as _os0
OUT = HERE / 'outputs'
TRACE_DIR = OUT / ('m6_traces' + (_os0.environ.get('M6_SUFFIX', '') or '_frozen')); TRACE_DIR.mkdir(parents=True, exist_ok=True)
FAST = ['H2_mol_min', 'T_out_K', 'waste_m3_min']
GC = ['y_H2', 'y_CH4', 'y_CO', 'y_CO2']
FEATS = FAST + GC
U0, U1 = .0021, .0024
SS = 2.27354e-4
DT = .1
T_END = 60.0
Z = 2.58
import os as _os
Q_SD = float(_os.environ.get('M6_Q_SD', '0.002'))   # random-walk sd per min; frozen v0 = 0.002; amendment A2 = 0.01


class Map2D:
    """Bicubic in (a_c, a_m) at each feed level; `lines` mode for single-fault np200 truth."""
    def __init__(self, csv, lines=False):
        d = pd.read_csv(csv)
        d = d[d.converged.astype(str) == 'True']
        self.lines = lines
        self.s = {}
        for u in (U0, U1):
            du = d[np.isclose(d.u_etoh, u)]
            if lines:
                c = du[du.a_m == 1.0].sort_values('a_c'); m = du[du.a_c == 1.0].sort_values('a_m')
                self.s[u] = {f: (CubicSpline(c.a_c, c[f]), CubicSpline(m.a_m, m[f])) for f in FEATS}
            else:
                ac = np.sort(du.a_c.unique()); am = np.sort(du.a_m.unique())
                self.s[u] = {f: RectBivariateSpline(ac, am, du.pivot_table(index='a_c', columns='a_m', values=f)
                                                    .reindex(index=ac, columns=am).values, kx=3, ky=3) for f in FEATS}

    def __call__(self, a_c, a_m, u):
        if self.lines:
            if a_m != 1.0 and a_c != 1.0:
                raise ValueError('np200 truth covers single faults only')
            return {f: float(sp[1](a_m) if a_c == 1.0 and a_m != 1.0 else sp[0](a_c)) for f, sp in self.s[u].items()}
        return {f: float(sp(a_c, a_m)[0, 0]) for f, sp in self.s[u].items()}


def noise(f, nominal):
    """(sd, bias bound) from the M2-M4 table, relative terms evaluated at nominal readings."""
    if f == 'H2_mol_min':
        return .005 * SS, .005 * SS
    if f == 'T_out_K':
        return .5, 1.0
    if f == 'waste_m3_min':
        return .01 * nominal[f], .02 * nominal[f]
    return max(.01 * nominal[f], .001), .02 * nominal[f]


HIST = {
    'H1': lambda t: (np.exp(-.01 * t), 1.0, 0.0),
    'H2': lambda t: (1.0, np.exp(-.006 * t), 0.0),
    'H3': lambda t: (1.0 - .4 * t / 60, 1.0, 0.0),
    'H4': lambda t: (1.0, .9 if t >= 20 else 1.0, 0.0),
    'H5': lambda t: (1.0, 1.0, 0.0),
    'H6': lambda t: (1.0, 1.0, -.0002 * SS * max(t - 10, 0)),
    'H7': lambda t: (np.exp(-.005 * t), np.exp(-.003 * t), 0.0)}
CORRECT = {'H1': {'CATALYST'}, 'H3': {'CATALYST'}, 'H2': {'MEMBRANE'}, 'H4': {'MEMBRANE'}, 'H5': {'HEALTHY'},
           'H6': {'NOT_ESTABLISHED', 'HEALTHY'}, 'H7': {'BOTH'}}


def feed(t, active):
    if not active:
        return U0
    k = (t - 14) % 20
    return U1 if t >= 14 and k < 6 else U0


def simulate_measurements(truth, hist, active, seed, nominal):
    rng = np.random.default_rng(seed)
    bias = {f: rng.uniform(-1, 1) * noise(f, nominal)[1] for f in FEATS}
    rows = []
    last_change = -99
    prev_u = None
    for i in range(int(T_END / DT) + 1):
        t = round(i * DT, 6)
        u = feed(t, active)
        if u != prev_u:
            last_change = t; prev_u = u
        a_c, a_m, drift = HIST[hist](t)
        y = truth(a_c, a_m, u)
        y['H2_mol_min'] += drift
        settled = t - last_change >= 1.0 - 1e-9
        for f in FAST:
            rows.append((t, t, u, f, y[f] + bias[f] + rng.normal(0, noise(f, nominal)[0]), settled))
        if abs(t / 3 - round(t / 3)) < 1e-9:
            for f in GC:
                rows.append((t, t + 3.0, u, f, y[f] + bias[f] + rng.normal(0, noise(f, nominal)[0]), settled))
    return pd.DataFrame(rows, columns=['t', 'avail', 'u', 'f', 'value', 'settled'])


def classify(a, P, h2_low, consistent=True):
    sd = np.sqrt(np.clip(np.diag(P), 1e-12, None))
    zc, zm = (1 - a[0]) / sd[0], (1 - a[1]) / sd[1]
    if zc > Z and zm > Z:
        c = 'BOTH'
    elif zc > Z:
        c = 'CATALYST'
    elif zm > Z:
        c = 'MEMBRANE'
    else:
        return 'NOT_ESTABLISHED' if h2_low else 'HEALTHY'
    return c if consistent else 'NOT_ESTABLISHED'


def h2_low_test(meas, t, nominal):
    w = meas[(meas.f == 'H2_mol_min') & (meas.t > t - 10) & (meas.t <= t) & (meas.u == U0) & meas.settled]
    if len(w) == 0:
        return False
    sd, B = noise('H2_mol_min', nominal)
    return (nominal['H2_mol_min'] - w.value.mean()) > 3 * sd / np.sqrt(len(w)) + B


def run_mhe(model, meas, nominal):
    a = np.array([1.0, 1.0]); P = np.diag([.05 ** 2, .05 ** 2])
    q = Q_SD ** 2
    out = []
    lo, hi = np.array([.4, .6]), np.array([1.0, 1.0])
    for t in np.arange(1.0, T_END + 1e-9, 1.0):
        w = meas[(meas.t > t - 10) & (meas.t <= t) & (meas.avail <= t) & meas.settled]
        g = w.groupby(['u', 'f']).value.agg(['mean', 'count']).reset_index()
        P0 = P + np.eye(2) * q * 1.0
        L0 = np.linalg.cholesky(np.linalg.inv(P0))
        prior = a.copy()
        def res(th):
            r = []
            for _, row in g.iterrows():
                sd, B = noise(row.f, nominal)
                v = sd ** 2 / row['count'] + B ** 2 / 3
                r.append((row['mean'] - model(th[0], th[1], row.u)[row.f]) / np.sqrt(v))
            return np.r_[r, L0.T @ (th - prior)]
        sol = least_squares(res, np.clip(a, lo, hi), bounds=(lo, hi), diff_step=1e-4)
        a = sol.x
        J = sol.jac
        P = np.linalg.pinv(J.T @ J)
        rdata = sol.fun[:-2]
        dof = max(len(rdata) - 2, 1)
        consistent = float(np.sum(rdata ** 2)) <= chi2.ppf(.99, dof)
        out.append((t, a[0], a[1], P[0, 0], P[1, 1], P[0, 1], classify(a, P, h2_low_test(meas, t, nominal), consistent),
                    float(np.sum(rdata ** 2)), dof))
    return pd.DataFrame(out, columns=['t', 'a_c', 'a_m', 'P00', 'P11', 'P01', 'call', 'chi2', 'dof'])


def run_ekf(model, meas, nominal):
    a = np.array([1.0, 1.0]); P = np.diag([.05 ** 2, .05 ** 2]); q = Q_SD ** 2
    lo, hi = np.array([.4, .6]), np.array([1.0, 1.0])
    out = []
    m = meas[meas.settled].sort_values('avail')
    for t in np.arange(1.0, T_END + 1e-9, 1.0):
        batch = m[(m.avail > t - 1.0) & (m.avail <= t)]
        P = P + np.eye(2) * q * 1.0
        for _, s in batch.iterrows():
            sd, B = noise(s.f, nominal)
            R = sd ** 2 + B ** 2 / 3
            y0 = model(a[0], a[1], s.u)[s.f]
            H = np.zeros(2)
            for j in range(2):
                d = np.zeros(2); d[j] = 1e-4
                ap, am_ = np.clip(a + d, lo, hi), np.clip(a - d, lo, hi)
                H[j] = (model(ap[0], ap[1], s.u)[s.f] - model(am_[0], am_[1], s.u)[s.f]) / (ap[j] - am_[j])
            S = H @ P @ H + R
            K = P @ H / S
            a = np.clip(a + K * (s.value - y0), lo, hi)
            P = (np.eye(2) - np.outer(K, H)) @ P
        out.append((t, a[0], a[1], P[0, 0], P[1, 1], P[0, 1], classify(a, P, h2_low_test(meas, t, nominal)), np.nan, np.nan))
    return pd.DataFrame(out, columns=['t', 'a_c', 'a_m', 'P00', 'P11', 'P01', 'call', 'chi2', 'dof'])


def evaluate(tr, hist):
    after = tr[tr.t >= 20]
    inside = []
    for _, r in after.iterrows():
        a_c, a_m, _ = HIST[hist](r.t)
        P = np.array([[r.P00, r.P01], [r.P01, r.P11]])
        d = np.array([r.a_c - a_c, r.a_m - min(max(a_m, .6), 1.0)])
        try:
            inside.append(float(d @ np.linalg.solve(P, d)) <= chi2.ppf(.95, 2))
        except np.linalg.LinAlgError:
            inside.append(False)
    ok = tr.call.isin(CORRECT[hist]).values
    t_ok = np.nan
    for i in range(len(ok)):
        if ok[i:].all():
            t_ok = float(tr.t.iloc[i]); break
    return {'final_call': tr.call.iloc[-1], 'final_correct': bool(ok[-1]), 'calibration_95': float(np.mean(inside)),
            'time_to_sustained_correct_min': t_ok}


_G = {}
import os
TRUTHS = os.environ.get('M6_TRUTHS', 'nominal,kinpert').split(',')
SUFFIX = os.environ.get('M6_SUFFIX', '')


def _init():
    _G['est'] = Map2D(D / 'map2d_nominal.csv')
    _G['truths'] = {'nominal': _G['est'], 'kinpert': Map2D(D / 'map2d_kinpert.csv')}
    if TRUTHS and 'np200' in TRUTHS:
        _G['truths']['np200'] = Map2D(D / 'map2d_np200.csv', lines=True)
    _G['nominal'] = _G['est'](1.0, 1.0, U0)


def _one(cfg):
    tname, hist, active, est, seed = cfg
    meas = simulate_measurements(_G['truths'][tname], hist, active, 1000 + seed, _G['nominal'])
    tr = (run_mhe if est == 'MHE' else run_ekf)(_G['est'], meas, _G['nominal'])
    key = f'{tname}_{hist}_{"active" if active else "passive"}_{est}_s{seed}'
    tr.to_csv(TRACE_DIR / f'{key}.csv', index=False)
    return {'truth': tname, 'history': hist, 'excitation': 'active' if active else 'passive', 'estimator': est,
            'seed': seed, **evaluate(tr, hist)}


def main(workers=3, seeds=3):
    from multiprocessing import Pool
    truths = TRUTHS
    cfgs = [c for c in itertools.product(truths, HIST, (False, True), ('MHE', 'EKF'), range(seeds))
            if not (c[0] == 'np200' and c[1] in ('H6', 'H7'))]
    with Pool(workers, initializer=_init) as pool:
        rows = []
        for r in pool.imap_unordered(_one, cfgs):
            rows.append(r)
            print(r['truth'], r['history'], r['excitation'], r['estimator'], r['seed'], r['final_call'], r['final_correct'],
                  round(r['calibration_95'], 2), r['time_to_sustained_correct_min'], flush=True)
    df = pd.DataFrame(rows).sort_values(['truth', 'history', 'excitation', 'estimator', 'seed'])
    df.to_csv(OUT / f'm6_runs{SUFFIX}.csv', index=False)
    summ = df.groupby(['truth', 'excitation', 'estimator']).agg(accuracy=('final_correct', 'mean'),
                                                                 calibration=('calibration_95', 'mean'),
                                                                 median_time=('time_to_sustained_correct_min', 'median')).reset_index()
    (OUT / f'm6_summary{SUFFIX}.json').write_text(summ.to_json(orient='records', indent=2))
    print(summ.to_string())
    fails = df[~df.final_correct].groupby(['truth', 'history', 'excitation', 'estimator']).final_call.agg(lambda s: ','.join(sorted(set(s))))
    print('FAILURES (kept):'); print(fails.to_string())
    (OUT / f'm6_failures{SUFFIX}.txt').write_text(fails.to_string())


if __name__ == '__main__':
    main()
