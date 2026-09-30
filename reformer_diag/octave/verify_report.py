"""Verifier: rebuilds M1_FINAL_REPORT.md and asserts it is identical to the file on disk, then
re-derives key numbers independently of build_report.py and asserts they appear in the report."""
from pathlib import Path
import json, sys
import numpy as np

HERE = Path(__file__).resolve().parent
PKG = HERE.parent
sys.path.insert(0, str(HERE))
import build_report  # noqa: E402

text = (HERE / 'M1_FINAL_REPORT.md').read_text(encoding='utf-8')
assert build_report.build() == text, 'report on disk differs from a fresh rebuild'

ml = json.loads((PKG / 'matlab_native' / 'MATLAB_NATIVE_RESULTS.json').read_text())['fresh_session_results']
for c in ('STEP', 'CS1', 'CS2T', 'CS2P'):
    assert ml[c]['max_dH2_pct_nominal_vs_python'] <= .5 and ml[c]['max_dEtOH_pct_nominal'] <= .5, c
    assert f"{ml[c]['max_dH2_pct_nominal_vs_python']:.4f}" in text, c
for c in ('CS1', 'CS2T', 'CS2P'):
    assert ml[c]['IAE_rel_diff_pct'] <= 1.0, c
    # independent recomputation of the published-deviation from the transcribed IAE
    pub = {'CS1': 7.95e-5, 'CS2T': 2.62e-4, 'CS2P': 2.48e-4}[c]
    dev = 100 * (ml[c]['IAE_matlab_mol'] - pub) / pub
    assert abs(dev - ml[c]['matlab_vs_published_pct']) < .01, (c, dev)

# independent one-sample gap for CS2T from the Python result file
r = json.loads((PKG / 'outputs' / 'CS2T_extended' / 'result.json').read_text())['tracking']
ratio = (2.62e-4 - r['conventional_iae_mol']) / (2.76379e-4 * .1)
assert abs(ratio - .997) < .0005 and '| 0.997 |' in text, ratio

# independent STEP Octave vs Python max deviation
o = np.loadtxt(HERE / 'cases' / 'STEP_np50_p6' / 'wsl64' / 'trajectory.csv', delimiter=',')
p = np.loadtxt(PKG / 'outputs' / 'STEP' / 'trace.csv', delimiter=',', skiprows=1)
d = 100 * np.abs(o[:40, 1] - p[:, 3]).max() / 2.27354e-4
assert f'{d:.3f}' in text, d
print('verify_report: PASS (rebuild identical; MATLAB gates; published deviations; CS2T one-sample ratio; STEP Octave max)')
