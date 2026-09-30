"""Independent check of the V4 note: recompute every displayed number from the source CSVs and the native traces,
then assert the exact string appears in the PDF text. Does not import build_note_v4.py."""
from pathlib import Path
import re, json, sys
import numpy as np, pandas as pd, fitz

HERE = Path(__file__).resolve().parent; E = HERE.parent; ROOT = E.parent
OLD = ROOT / 'amendment_feed_only_20260930'
NATIVE = Path(r'C:\Users\Admin\Desktop\WHEC\reformer_benchmark\work\audit_check\ssmr_native\baseline')
PDF = E / 'output/pdf/SSMR_TECHNICAL_NOTE_V4.pdf'
CENTRAL = ['m1_C_d05_r1', 'm1_M_d05_r1', 'm2_C_d05_r1', 'm2_M_d05_r1']
PUB = {'CS1': 7.95e-5, 'CS2T': 2.62e-4, 'CS2P': 2.48e-4}

doc = fitz.open(PDF); assert len(doc) == 6
text = re.sub(r'\s+', ' ', ' '.join(p.get_text() for p in doc))
checks = []
def must(s, why):
    ok = s in text; checks.append((ok, s, why))
    return ok

# 1. equal-ethanol table and headline
s = pd.read_csv(E / 'outputs/paired_summary.csv', float_precision='round_trip').set_index('case_id').loc[CENTRAL]
t = pd.read_csv(E / 'outputs/paired_trials.csv', float_precision='round_trip'); assert len(t) == 4000
wins, inc, rel = {}, {}, {}
for c in CENTRAL:
    r = s.loc[c]; g = t[t.case_id == c]; assert len(g) == 1000
    d = g.difference_H2_shortfall_mol; wins[c] = int((d < 0).sum())
    inc[c] = int((g.call == 'MODEL_INCOMPATIBLE').sum()); rel[c] = 100 * r.difference_H2_shortfall_mol_mean / r.blind_H2_shortfall_mol_mean
    must(f'{1000*r.diagnostic_actual_ethanol_mol_mean:.1f}', f'{c} matched ethanol')
    must(f'{1000*r.diagnostic_H2_shortfall_mol_mean:.4f}', f'{c} diagnostic shortfall')
    must(f'{1000*r.blind_H2_shortfall_mol_mean:.4f}', f'{c} blind shortfall')
    must(f'{1000*r.difference_H2_shortfall_mol_mean:+.5f} ({rel[c]:+.1f}%)', f'{c} mean difference')
    must(f'{wins[c]}/1000', f'{c} diagnostic-better count')
    assert (d > 0).sum() == 1000 - wins[c] and (d == 0).sum() == 0
    # per-call split
    sp = g.assign(dm=d * 1000).groupby('call').dm.mean()
    if 'MODEL_INCOMPATIBLE' in sp: must(f'{sp["MODEL_INCOMPATIBLE"]:.2f}', f'{c} incompatible cost')
must(f'within {max(abs(v) for v in rel.values()):.1f}% in all four', 'headline relative bound')
must(f'in {min(wins.values())} to {max(wins.values())} of 1000 episodes', 'headline win range')
must(f'through the {min(inc.values())} to {max(inc.values())} episodes', 'headline incompatible range')
assert all(rel[c] > 0 for c in CENTRAL), 'blind arm must have the lower mean in all four for the headline wording'
for c, k in [('m2_C_d05_r1', 'C'), ('m2_C_d05_r1', 'INCONCLUSIVE'), ('m2_M_d05_r1', 'M'), ('m1_C_d05_r1', 'C')]:
    g = t[t.case_id == c]; v = 1000 * g[g.call == k].difference_H2_shortfall_mol.mean(); must(f'{v:+.2g}', f'{c} {k} mean')
# Mode 2: diagnostic better in every called/inconclusive episode
for c in ['m2_C_d05_r1', 'm2_M_d05_r1']:
    g = t[(t.case_id == c) & (t.call != 'MODEL_INCOMPATIBLE')]; assert (g.difference_H2_shortfall_mol >= 0).sum() <= 1, c
must('all but one of the episodes', 'Mode 2 all-but-one wording')

# 2. IAE under Eq. (13) on native traces
for c in PUB:
    m = pd.read_csv(NATIVE / f'{c}_np50_matlab.csv', header=None, names=['t', 'y', 'u', 'sp']); e = (m.sp - m.y).values
    eq13 = float(np.sum(np.abs((e[1:] + e[:-1]) / 2 * 0.1))); tz = float(np.trapezoid(np.abs(e), dx=0.1))
    gap = 100 * (eq13 - PUB[c]) / PUB[c]; conv = 100 * (tz - eq13) / tz
    if c == 'CS1': must(f'within {abs(gap):.1f}% of the published 7.95e-5', 'CS1 gap')
    else: must(f'{abs(gap):.1f}%', f'{c} gap vs paper'); must(f'{conv:.1f}%', f'{c} convention difference')
    assert (gap < 0) if c != 'CS1' else abs(gap) < 1

# 3. healthy / meter-bias table
o = pd.read_csv(OLD / 'outputs/paired_summary.csv', float_precision='round_trip')
for c in ['m1_H', 'm2_H', 'm1_S_d05_r0', 'm2_S_d05_r0']:
    part = o[o.case_id == c].set_index('set')
    for st in ['S1', 'S3', 'S4']: must(f'{int(part.loc[st, "non_nominal_action_count"])}/1000', f'{c} {st} actions')
hs = o[o.case_id.isin(['m1_H', 'm2_H'])].non_nominal_action_count
must(f'{hs.min()/10:.1f}-{hs.max()/10:.1f}% of episodes', 'healthy range')
m1s1 = o[(o.case_id == 'm1_S_d05_r0') & (o['set'] == 'S1')].iloc[0]
must(f'{1000*m1s1.difference_actual_ethanol_mol_mean:.2f} mmol', 'M1 S S1 ethanol')

# 4. diagnosis counts (page 3)
d = pd.read_csv(ROOT / 'results/diagnosis_summary.csv')
def row(c, a, st='S4'):
    r = d[(d.case_id == c) & (d.active == a) & (d['set'] == st) & (d['group'] == 'covered_grid')]; assert len(r) == 1; return r.iloc[0]
for c in CENTRAL:
    p, a = row(c, False), row(c, True)
    must(f'{int(p.correct_singleton)} {int(a.correct_singleton)} {int(a.wrong_singleton)} {int(a.inconclusive + a.incompatible)}', f'{c} diagnosis row')
must(f'from {int(row("m1_M_d05_r1", False, "S1").correct_singleton)} to {int(row("m1_M_d05_r1", True, "S1").correct_singleton)} out of 1000', 'S1 membrane')
must(f'from {int(row("m1_C_d05_r1", False, "S1").correct_singleton)} to {int(row("m1_C_d05_r1", True, "S1").correct_singleton)}', 'S1 catalyst')

fails = [c for c in checks if not c[0]]
for ok, sv, why in checks: print(('PASS ' if ok else 'FAIL ') + f'{why:40s} "{sv}"')
print(f'\n{len(checks) - len(fails)}/{len(checks)} checks pass; pdf sha256 prefix', __import__('hashlib').sha256(PDF.read_bytes()).hexdigest()[:16])
json.dump({'pdf': str(PDF), 'checks': [{'pass': a, 'string': b, 'why': c} for a, b, c in checks]}, open(HERE / 'VERIFY_V4.json', 'w'), indent=1)
sys.exit(1 if fails else 0)
