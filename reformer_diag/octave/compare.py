"""Compare untouched-upstream Octave runs (this lane) with the published IAE, the Python port and
the other lane's wrapper-Octave traces. Definitions frozen in
PROTOCOL_2026-09-29_M1_native_upstream.md; the IAE functions are the unchanged acceptance.py.
Writes COMPARISON.md and comparison.json. Missing inputs are reported as MISSING, not skipped."""
from pathlib import Path
import json, re, sys
import numpy as np
import yaml

HERE = Path(__file__).resolve().parent
PKG = HERE.parent
sys.path.insert(0, str(PKG))
from acceptance import tracking  # noqa: E402

CFG = yaml.safe_load((PKG / 'config.yaml').read_text())
TARGETS = CFG['paper_targets']
NOMINAL_H2 = {1: 2.27354e-4, 2: 2.76379e-4}          # `ss` in SSMR_simulation.m
NOMINAL_ETOH = {1: 0.0021, 2: 0.0018}                # u_ss(1) in ICFull/Mode{1,2}_np50.mat
MODE = {'STEP': 1, 'CS1': 1, 'CS2T': 2, 'CS2P': 2}
PROPOSED = {'h2_pct': 0.5, 'iae_pct': 1.0, 'etoh_pct': 0.5}   # proposed, not yet approved
PYTHON = {'STEP': ['STEP', 'STEP_BDF_tight', 'STEP_Radau_tight'], 'CS1': ['CS1'],
          'CS2T': ['CS2T_extended', 'CS2T_BDF_tight', 'CS2T_Radau_tight'], 'CS2P': ['CS2P_extended']}


def as_trace(time, y, u, ysp):
    """Map to the column layout acceptance.tracking reads: 0 display time, 3 H2, 5 ethanol, 7 set-point."""
    tr = np.zeros((len(time), 10))
    tr[:, 0], tr[:, 3], tr[:, 5], tr[:, 7] = time, y, u, ysp
    return tr


def load_upstream(csv):
    d = np.loadtxt(csv, delimiter=',')
    return as_trace(d[:, 0], d[:, 1], d[:, 2], d[:, 3])


def load_trace(csv):
    return np.loadtxt(csv, delimiter=',', skiprows=1)


def diff(a, b, mode):
    n = min(len(a), len(b))
    if n == 0:
        return None
    dy = np.max(np.abs(a[:n, 3] - b[:n, 3]))
    du = np.max(np.abs(a[:n, 5] - b[:n, 5]))
    out = {'rows_compared': n, 'rows_a': len(a), 'rows_b': len(b),
           'max_abs_dH2_mol_min': float(dy), 'max_dH2_pct_nominal': float(100 * dy / NOMINAL_H2[mode]),
           'max_abs_dEtOH_mol_min': float(du), 'max_dEtOH_pct_nominal': float(100 * du / NOMINAL_ETOH[mode]),
           'max_rel_dH2_pct': float(100 * np.max(np.abs(a[:n, 3] - b[:n, 3]) / np.maximum(np.abs(b[:n, 3]), 1e-12)))}
    ia = tracking(a[:n], 1.0, 0)['conventional_iae_mol']
    ib = tracking(b[:n], 1.0, 0)['conventional_iae_mol']
    out['iae_a_mol'], out['iae_b_mol'] = ia, ib
    out['iae_rel_diff_pct'] = float(100 * abs(ia - ib) / abs(ib)) if ib else None
    out['proposed_gate'] = 'PASS' if (out['max_dH2_pct_nominal'] <= PROPOSED['h2_pct'] and out['max_dEtOH_pct_nominal'] <= PROPOSED['etoh_pct']
                                      and (out['iae_rel_diff_pct'] or 0) <= PROPOSED['iae_pct']) else 'FAIL'
    return out


results = {}
for run in sorted(HERE.glob('cases/*/*/trajectory.csv')):
    case_np, runtime = run.parent.parent.name, run.parent.name
    case, np_, variant = re.fullmatch(r'(\w+?)_np(\d+)(?:_(\w+))?', case_np).groups()
    variant = variant or 'untouched'
    mode = MODE[case]
    up = load_upstream(run)
    r = {'case': case, 'np': int(np_), 'variant': variant, 'runtime': runtime, 'rows': len(up)}
    key = f'{case}_iae_mol'
    if key in TARGETS:
        r['vs_paper'] = tracking(up, TARGETS[key], CFG['thresholds']['tracking_relative_pct'])
    if case == 'STEP':
        y, t = up[:, 3], up[:, 0]
        y0, yf = y[(t >= 1.8) & (t < 2.0 + 1e-9)].mean(), y[t >= 3.8 - 1e-9].mean()
        thr = y0 + 0.632 * (yf - y0)
        i = int(np.argmax(y >= thr)) if yf > y0 else int(np.argmax(y <= thr))
        tc = t[i - 1] + (thr - y[i - 1]) * (t[i] - t[i - 1]) / (y[i] - y[i - 1])
        r['step_63pct_display_time_min'] = float(tc)
        r['step_63pct_note'] = ('Linear interpolation on 0.1-min display samples; y_output(k) is labelled '
                                'time (k-1)*t_s as in upstream plots. Coarse; not the dense FOPDT fit.')
    r['vs_python'] = {}
    if int(np_) == 50:
        for name in PYTHON[case]:
            f = PKG / 'outputs' / name / 'trace.csv'
            r['vs_python'][name] = diff(up, load_trace(f), mode) if f.exists() else 'MISSING'
    r['vs_wrapper_octave'] = {}
    if int(np_) == 50:
        for f in sorted(PKG.glob(f'matlab/native_outputs*/{case}_trace.csv')):
            r['vs_wrapper_octave'][f.parent.name] = diff(up, load_trace(f), mode)
    results[f'{case_np}/{runtime}'] = r

# runtime cross-check where a case ran in both runtimes
for case_np in sorted({k.split('/')[0] for k in results}):
    a, b = HERE / 'cases' / case_np / 'wsl64' / 'trajectory.csv', HERE / 'cases' / case_np / 'win113' / 'trajectory.csv'
    if a.exists() and b.exists():
        results[f'{case_np}/octave64_vs_octave113'] = diff(load_upstream(a), load_upstream(b), MODE[case_np.split('_np')[0]])
# variant cross-check within a case (e.g. P6 vs P7) on the same runtime or across runtimes
by_case = {}
for k, r in results.items():
    if 'case' in r:
        by_case.setdefault((r['case'], r['np']), []).append(k)
for (case, np_), keys in by_case.items():
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            a = HERE / 'cases' / keys[i] / 'trajectory.csv'
            b = HERE / 'cases' / keys[j] / 'trajectory.csv'
            results[f'{keys[i]} vs {keys[j]}'] = diff(load_upstream(a), load_upstream(b), MODE[case])

(HERE / 'comparison.json').write_text(json.dumps(results, indent=2) + '\n')

L = ['# Untouched-upstream Octave runs: comparison', '',
     'Generated by compare.py from comparison.json. Octave is not MATLAB. Proposed gates '
     f'(not yet approved by Bosco): max dH2 <= {PROPOSED["h2_pct"]}% of nominal, IAE difference <= {PROPOSED["iae_pct"]}%, '
     f'max dEtOH <= {PROPOSED["etoh_pct"]}% of nominal. Paper gate: IAE within 2% (approved). Rows are compared by '
     'sample index k, the same display-time convention in every source.', '']
for k, r in results.items():
    L.append(f'## {k}')
    if 'vs_paper' in r:
        p = r['vs_paper']
        L.append(f'- vs paper: IAE {p["conventional_iae_mol"]:.6g} mol (published {p["published_iae_mol"]:.3g}), '
                 f'deviation {p["relative_deviation_pct"]:.3f}% -> **{p["status"]}**; paper-literal formula deviation {p["paper_literal_deviation_pct"]:.3f}%')
    if 'step_63pct_display_time_min' in r:
        L.append(f'- STEP 63.2% crossing (display time): {r["step_63pct_display_time_min"]:.4f} min; {r["step_63pct_note"]}')
    for group in ('vs_python', 'vs_wrapper_octave'):
        for name, d in r.get(group, {}).items():
            if isinstance(d, dict):
                L.append(f'- {group} {name}: max dH2 {d["max_dH2_pct_nominal"]:.4f}% nominal, max dEtOH {d["max_dEtOH_pct_nominal"]:.4f}% nominal, '
                         f'IAE diff {d["iae_rel_diff_pct"]:.4f}%, rows {d["rows_compared"]}/{d["rows_a"]}/{d["rows_b"]} -> {d["proposed_gate"]}')
            else:
                L.append(f'- {group} {name}: {d}')
    if 'max_dH2_pct_nominal' in r:
        L.append(f'- max dH2 {r["max_dH2_pct_nominal"]:.4f}% nominal, IAE diff {r["iae_rel_diff_pct"]}% -> {r["proposed_gate"]}')
    L.append('')
(HERE / 'COMPARISON.md').write_text('\n'.join(L), encoding='utf-8')
print('\n'.join(L))
