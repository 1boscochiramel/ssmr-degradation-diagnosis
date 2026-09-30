"""Verifier for note_v1.tex: every printed number must appear in the tex, and key numbers are
re-derived here independently of build_note.py from the raw output files."""
from pathlib import Path
import json
import pandas as pd
HERE = Path(__file__).resolve().parent; PKG = HERE.parent; D = PKG / 'diag' / 'outputs_diag'
tex = (HERE / 'note_v1.tex').read_text(encoding='utf-8')
printed = json.loads((HERE / 'NUMBERS.json').read_text())['printed']
for k, v in printed.items():
    assert v in tex, (k, v)
ml = json.loads((PKG / 'matlab_native' / 'MATLAB_NATIVE_RESULTS.json').read_text())['fresh_session_results']
assert f"{max(ml[c]['max_dH2_pct_nominal_vs_python'] for c in ml if c in ('STEP','CS1','CS2T','CS2P')):.4f}" in tex
val = json.loads((D / 'validation.json').read_text())
assert all(val[g][k]['status'] == 'PASS' for g in ('V1', 'V2') for k in ('C', 'M'))
m3 = json.loads((D / 'm3_case.json').read_text())
assert all(v['decision_frozen'].endswith(k.split('_')[1]) for k, v in m3['stopping_rule_C_vs_M'].items()), 'stopping rule claim'
for name in ('regions.csv', 'regions_A1.csv'):
    r = pd.read_csv(D / name); r = r[r.scale == 1.0]
    assert ((r['drop'] == .01) & (r.region == 'DISTINGUISHABLE')).sum() == 0, 'no 1% distinguishable claim'
    assert ((r.set == 'S1') & (~r.move) & (r.region == 'DISTINGUISHABLE')).sum() == 0, 'S1 claim'
half = [int(((pd.read_csv(D / n).scale == .5) & (pd.read_csv(D / n)['drop'] == .01) & (pd.read_csv(D / n).region == 'DISTINGUISHABLE')).sum()) for n in ('regions.csv', 'regions_A1.csv')]
assert f'with half the noise, {half[0]} (frozen) and {half[1]} (A1)' in tex, half
v2 = json.loads((D / 'validation_mode2.json').read_text()); assert all(v2[k]['status'] == 'PASS' for k in ('C', 'M'))
voi = json.loads((D / 'voi_A1.json').read_text())
assert voi['mode1_scale1.0_S1+E']['ethanol_excess_avoided_mol_min'] > voi['mode1_scale1.0_S4']['ethanol_excess_avoided_mol_min'], 'move beats sensors claim'
print(f'verify_note: PASS ({len(printed)} printed numbers found; 8 claims re-derived)')
