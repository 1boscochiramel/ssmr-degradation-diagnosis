"""M3 worked ambiguity case, protocol section 7 (fixed before results). Writes outputs_diag/m3_case.json."""
from pathlib import Path
import json
import numpy as np
from scipy.optimize import brentq
import distinguish as D
from hypotheses import Map, action, SS, U_SS, MOVE

OUT = Path(__file__).resolve().parent / 'outputs_diag'
MODE, DROP = 1, .05


def per_sensor(m, t1, a1, t2, a2, feats, n_move_fast, n_move_gc):
    rows = []
    for f in feats:
        s, B = D.noise(f, t1[f], MODE, 1.0)
        n1 = D.n_of(f, 'window')
        n2 = n_move_gc if f in D.GC else n_move_fast
        r = t1[f] - a1[f]
        rd = (t2[f] - t1[f]) - (a2[f] - a1[f])
        s2, _ = D.noise(f, t2[f], MODE, 1.0)
        sd = np.hypot(s / np.sqrt(n1), s2 / np.sqrt(n2))
        rows.append({'feature': f, 'truth_level1': t1[f], 'alt_level1': a1[f], 'residual': r, 'sd': s, 'bias_bound': B,
                     'residual_in_sd': r / s, 'residual_after_bias_in_sd': max(abs(r) - B, 0) / s,
                     'lambda_level1': n1 * (max(abs(r) - B, 0) / s) ** 2,
                     'truth_move_response': t2[f] - t1[f], 'alt_move_response': a2[f] - a1[f],
                     'move_residual': rd, 'move_sd_of_difference': sd, 'lambda_move': (rd / sd) ** 2})
    return rows


def lam_with(m, t1, t2, h_alt, feats, n_fast, n_gc, move=True):
    saved = dict(D.N_MOVE)
    D.N_MOVE.update(fast=n_fast, gc=n_gc)
    try:
        th, L = D.fit_alt(m, h_alt, U_SS[MODE], feats, t1, t2 if move else None, 1.0, move)
    finally:
        D.N_MOVE.clear(); D.N_MOVE.update(saved)
    return th, L


def main():
    m = Map(MODE); u0 = U_SS[MODE]
    thC = m.severity_for_drop('C', DROP, u0)
    thM = m.severity_for_drop('M', DROP, u0)
    thF = m.severity_for_drop('F', DROP, u0)
    thS = m.severity_for_drop('S', DROP, u0)
    t1, t2 = m.predict('C', thC, u0), m.predict('C', thC, u0 + MOVE)
    a1, a2 = m.predict('M', thM, u0), m.predict('M', thM, u0 + MOVE)
    res = {'mode': MODE, 'u_cmd': u0, 'move': MOVE, 'H2_drop_frac': DROP,
           'theta': {'C': thC, 'M': thM, 'F': thF, 'S_mol_min': thS},
           'actions': {h: action(m, h, th) for h, th in (('C', thC), ('M', thM), ('F', thF), ('S', thS))},
           'u_required': {h: m.u_required(h, th) for h, th in (('C', thC), ('M', thM), ('F', thF))},
           'per_sensor_S4': per_sensor(m, t1, a1, t2, a2, D.SETS['S4'], D.N_MOVE['fast'], D.N_MOVE['gc'])}
    # stopping rule per set, truth C (and symmetric truth M)
    rule = {}
    for truth, (tt1, tt2) in (('C', (t1, t2)), ('M', (a1, a2))):
        for sname, feats in D.SETS.items():
            k = 2 * len(feats)
            out = {}
            for tag, nf, ng in (('E5', 50, 1), ('E10', 100, 2)):
                thr_frozen = float(D.chi2.ppf(.99, max(k - 1, 1))); thr_a1 = float(D.chi2.ppf(.99, 1))
                lams = {}
                for h in ('C', 'M'):
                    if h == truth:
                        lams[h] = 0.0
                    else:
                        lams[h] = lam_with(m, tt1, tt2, h, feats, nf, ng)[1]
                out[tag] = {'lambda': lams, 'threshold_frozen': thr_frozen, 'threshold_A1': thr_a1}
            def decide(thr_key):
                for tag in ('E5', 'E10'):
                    alive = [h for h, L in out[tag]['lambda'].items() if L <= out[tag][thr_key]]
                    if len(alive) == 1:
                        return f'{tag}: declare {alive[0]}'
                return 'INCONCLUSIVE after E10'
            out['decision_frozen'] = decide('threshold_frozen')
            out['decision_A1'] = decide('threshold_A1')
            rule[f'truth_{truth}_{sname}'] = out
    res['stopping_rule_C_vs_M'] = rule
    # time view: authors' catalyst schedule and the membrane schedule giving identical H2
    tv = []
    for t in np.arange(0, 30.01, 1.0):
        ac = float(np.exp(-.01 * t))
        h = m.predict('C', ac, u0)['H2_mol_min']
        g = lambda a: m.predict('M', a, u0)['H2_mol_min'] - h
        am = 1.0 if t == 0 else brentq(g, .4, 1.0, xtol=1e-12)
        tv.append({'t_min': float(t), 'a_c': ac, 'H2_mol_min': h, 'a_m_matching': am})
    k_eq = -np.polyfit([r['t_min'] for r in tv], np.log([r['a_m_matching'] for r in tv]), 1)[0]
    res['time_view'] = tv
    res['membrane_equivalent_rate_per_min'] = float(k_eq)
    res['move_cost_ethanol_mol'] = MOVE * 6
    res['move_H2_extra_mol_min_under_C'] = t2['H2_mol_min'] - t1['H2_mol_min']
    res['move_H2_extra_mol_min_under_M'] = a2['H2_mol_min'] - a1['H2_mol_min']
    (OUT / 'm3_case.json').write_text(json.dumps(res, indent=2) + '\n')
    print(json.dumps({k: v for k, v in res.items() if k not in ('per_sensor_S4', 'time_view', 'stopping_rule_C_vs_M')}, indent=2))
    for k, v in rule.items():
        print(k, v['decision_frozen'], '|', v['decision_A1'], {t: {h: round(L, 2) for h, L in v[t]['lambda'].items()} for t in ('E5', 'E10')})
    for r in res['per_sensor_S4']:
        print(f"{r['feature']:14s} resid/sd {r['residual_in_sd']:+9.3f} after-bias {r['residual_after_bias_in_sd']:7.3f}  move-resid/sd {r['move_residual']/r['move_sd_of_difference']:+8.3f}")


if __name__ == '__main__':
    main()
