"""Distinguishability, regions, wrong-action costs and value of information (protocol sections 2-6).
Writes outputs_diag/map_results.json, regions.csv, voi.json, structural.json."""
from pathlib import Path
import itertools, json
import numpy as np
import pandas as pd
from scipy.optimize import minimize_scalar
from scipy.stats import chi2
from hypotheses import Map, action, SS, U_SS, U_MAX, MOVE

HERE = Path(__file__).resolve().parent
OUT = HERE / 'outputs_diag'
HYP = ['C', 'M', 'F', 'S']
DROPS = [.01, .02, .05, .10, .20]
FAST = ['H2_mol_min', 'T_out_K', 'waste_m3_min']
GC = ['y_H2', 'y_CH4', 'y_CO', 'y_CO2']
SETS = {'S1': ['H2_mol_min'], 'S2': ['H2_mol_min', 'T_out_K'], 'S3': FAST, 'S4': FAST + GC}
N_WINDOW = {'fast': 100, 'gc': 3}          # 10-min window, GC every 3 min with 3-min delay
N_MOVE = {'fast': 50, 'gc': 1}             # 5 min held after 1 min settling


def noise(f, value, mode, scale):
    """(sd, bias bound) per protocol section 2 table, times `scale`."""
    if f == 'H2_mol_min':
        return .005 * SS[mode] * scale, .005 * SS[mode] * scale
    if f == 'T_out_K':
        return .5 * scale, 1.0 * scale
    if f == 'waste_m3_min':
        return .01 * abs(value) * scale, .02 * abs(value) * scale
    return max(.01 * abs(value), .001) * scale, .02 * abs(value) * scale


def n_of(f, kind):
    return (N_WINDOW if kind == 'window' else N_MOVE)['gc' if f in GC else 'fast']


def lam(truth1, alt1, feats, mode, scale, truth2=None, alt2=None):
    """Lambda statistic: bias-robust level-1 term + bias-free difference term for the feed move."""
    L = 0.0
    for f in feats:
        s, B = noise(f, truth1[f], mode, scale)
        r = max(abs(truth1[f] - alt1[f]) - B, 0.0)
        L += n_of(f, 'window') * (r / s) ** 2
        if truth2 is not None:
            s2, _ = noise(f, truth2[f], mode, scale)
            sd = np.hypot(s / np.sqrt(n_of(f, 'window')), s2 / np.sqrt(n_of(f, 'move')))
            rd = (truth2[f] - truth1[f]) - (alt2[f] - alt1[f])
            L += (rd / sd) ** 2
    return L


import os
THRESHOLD_MODE = os.environ.get('THRESHOLD_MODE', 'frozen')   # 'A1' = fixed chi2_0.99(1), amendment A1


def threshold(k):
    return float(chi2.ppf(.99, 1 if THRESHOLD_MODE == 'A1' else max(k - 1, 1)))


def fit_alt(m, h_alt, u0, feats, truth1, truth2, scale, move):
    lo, hi = m.range(h_alt, u0)
    def obj(th):
        a1 = m.predict(h_alt, th, u0)
        a2 = m.predict(h_alt, th, u0 + MOVE) if move else None
        return lam(truth1, a1, feats, m.mode, scale, truth2, a2)
    grid = np.linspace(lo, hi, 200)
    vals = [obj(t) for t in grid]
    i = int(np.argmin(vals))
    a, b = grid[max(i - 1, 0)], grid[min(i + 1, len(grid) - 1)]
    r = minimize_scalar(obj, bounds=(a, b), method='bounded', options={'xatol': 1e-10 * max(abs(hi - lo), 1e-12)})
    best = (r.x, r.fun) if r.fun < vals[i] else (grid[i], vals[i])
    return float(best[0]), float(best[1])


def cost(m, h_true, th_true, h_alt, th_alt, u0):
    """(H2 shortfall mol/min, ethanol excess mol/min, unnecessary-intervention flag) for acting on (h_alt, th_alt)."""
    a_true, a_alt = action(m, h_true, th_true), action(m, h_alt, th_alt)
    if a_true == a_alt:
        return 0.0, 0.0, 0
    ss = SS[m.mode]
    if h_true == 'S':
        u = min(m.u_required(h_alt, th_alt), U_MAX)
        return 0.0, max(u - u0, 0.0), int(a_alt.startswith(('SERVICE', 'REPAIR')))
    if a_true == 'COMPENSATE':
        if a_alt == 'RECALIBRATE':
            return max(ss - m.true_h2(h_true, th_true, u0), 0.0), 0.0, 0
        return 0.0, 0.0, 1          # unnecessary service; no operator-unit cost defined (protocol gap, conservative)
    # truth needs service; any other action leaves the shortfall at the input bound
    return max(ss - m.true_h2(h_true, th_true, U_MAX), 0.0), 0.0, int(a_alt.startswith(('SERVICE', 'REPAIR')))


def evaluate_mode(mode, scale=1.0):
    m = Map(mode)
    u0 = U_SS[mode]
    rows = []
    for h, drop in itertools.product(HYP, DROPS):
        th = m.severity_for_drop(h, drop, u0)
        if th is None:
            for sname in SETS:
                for move in (False, True):
                    rows.append(dict(mode=mode, scale=scale, true=h, drop=drop, set=sname, move=move, region='UNREACHABLE'))
            continue
        t1 = m.predict(h, th, u0); t2 = m.predict(h, th, u0 + MOVE)
        a_true = action(m, h, th)
        for sname, feats in SETS.items():
            for move in (False, True):
                k = len(feats) * (2 if move else 1)
                thr = threshold(k)
                fits = {h: (th, 0.0)}
                for ha in HYP:
                    if ha != h:
                        fits[ha] = fit_alt(m, ha, u0, feats, t1, t2 if move else None, scale, move)
                alive = {ha: v for ha, v in fits.items() if v[1] <= thr}
                acts = {ha: action(m, ha, v[0]) for ha, v in alive.items()}
                if len(alive) == 1:
                    region = 'DISTINGUISHABLE'
                elif all(a == a_true for a in acts.values()):
                    region = 'SAME_ACTION'
                else:
                    region = 'DIFFERENT_ACTION'
                cs = [cost(m, h, th, ha, v[0], u0) for ha, v in alive.items()]
                rows.append(dict(mode=mode, scale=scale, true=h, drop=drop, theta=th, action=a_true, set=sname, move=move,
                                 k=k, threshold=thr, region=region, alive=','.join(sorted(alive)),
                                 lambdas=json.dumps({ha: round(v[1], 4) for ha, v in fits.items()}),
                                 fitted=json.dumps({ha: v[0] for ha, v in fits.items()}),
                                 exp_shortfall=float(np.mean([c[0] for c in cs])),
                                 exp_ethanol=float(np.mean([c[1] for c in cs])),
                                 exp_unnecessary=float(np.mean([c[2] for c in cs]))))
    return rows


def structural(mode):
    """Rank of the noise-scaled sensitivity matrix at nominal, per set, with and without the move."""
    m = Map(mode); u0 = U_SS[mode]
    params = [('C', 1.0, -1e-3), ('M', 1.0, -1e-3), ('F', 1.0, -1e-3), ('S', 0.0, -1e-3 * SS[mode])]
    base1, base2 = m.predict('C', 1.0, u0), m.predict('C', 1.0, u0 + MOVE)
    out = {}
    for sname, feats in SETS.items():
        for move in (False, True):
            cols = []
            for h, th, dth in params:
                p1, p2 = m.predict(h, th + dth, u0), m.predict(h, th + dth, u0 + MOVE)
                col = [(p1[f] - base1[f]) / noise(f, base1[f], mode, 1)[0] for f in feats]
                if move:
                    col += [((p2[f] - base2[f]) - (p1[f] - base1[f])) / noise(f, base2[f], mode, 1)[0] for f in feats]
                cols.append(np.array(col) / abs(dth))
            J = np.array(cols).T
            sv = np.linalg.svd(J, compute_uv=False)
            out[f'{sname}{"+E" if move else ""}'] = {'features': len(J), 'rank_1e-6': int((sv > 1e-6 * sv[0]).sum()),
                                                      'singular_values': [float(x) for x in sv]}
    return out


if __name__ == '__main__':
    OUT.mkdir(exist_ok=True)
    allrows, struct = [], {}
    for mode in (1, 2):
        struct[mode] = structural(mode)
        for scale in (1.0, .5, 2.0):
            allrows += evaluate_mode(mode, scale)
            print(f'mode {mode} scale {scale} done', flush=True)
    df = pd.DataFrame(allrows)
    SUF = '_A1' if THRESHOLD_MODE == 'A1' else ''
    df.to_csv(OUT / f'regions{SUF}.csv', index=False)
    (OUT / 'structural.json').write_text(json.dumps(struct, indent=2) + '\n')
    voi = {}
    for (mode, scale), d in df[df.region != 'UNREACHABLE'].groupby(['mode', 'scale']):
        base = d[(d.set == 'S1') & (~d.move)].set_index(['true', 'drop'])
        for (sname, move), g in d.groupby(['set', 'move']):
            g = g.set_index(['true', 'drop'])
            key = f'mode{mode}_scale{scale}_{sname}{"+E" if move else ""}'
            voi[key] = {'H2_shortfall_avoided_mol_min': float((base.exp_shortfall - g.exp_shortfall).mean()),
                        'ethanol_excess_avoided_mol_min': float((base.exp_ethanol - g.exp_ethanol).mean()),
                        'unnecessary_interventions_avoided': float((base.exp_unnecessary - g.exp_unnecessary).mean()),
                        'regions': g.region.value_counts().to_dict()}
    (OUT / f'voi{SUF}.json').write_text(json.dumps(voi, indent=2) + '\n')
    print(df[df.scale == 1.0].pivot_table(index=['mode', 'true', 'drop'], columns=['set', 'move'], values='region', aggfunc='first').to_string())
