"""Engineering-only interface/continuity/cost checks, not held-out evaluation."""
import json
from pathlib import Path
import time
import numpy as np
from dynamics import FEATURES, Scenario, run_truth, continue_truth, source_hashes

ROOT = Path(__file__).resolve().parent


def main():
    dest = ROOT / 'dynamic_smoke_results' / time.strftime('%Y%m%dT%H%M%S')
    dest.mkdir(parents=True, exist_ok=False)
    before = source_hashes(1)
    t = time.perf_counter()
    print('Engineering healthy active 0..21 start', flush=True)
    truth = run_truth(1, 'H', 0., active=True, output_dir=dest / 'healthy_active')
    print(f'Healthy done in {time.perf_counter()-t:.3f}s', flush=True)
    t = time.perf_counter()
    print('Engineering causal branch16..31 start', flush=True)
    branch = continue_truth(truth, 16., .0021, output_dir=dest / 'branch16')
    print(f'Branch done in {time.perf_counter()-t:.3f}s', flush=True)
    sc = Scenario(1, 'C', .037, .91, .0021)
    checks = {}
    tr = truth['trace']; iv = truth['intervals']; br = branch['trace']
    expected_rows = round(21. / .1) + 1
    checks['inclusive_uniform_samples'] = len(tr) == expected_rows and tr.time_min.is_unique
    checks['all_seven_features'] = all('true_' + f in tr and 'observed_' + f in tr for f in FEATURES)
    checks['states_match_sample_count_by800'] = truth['states'].shape == (expected_rows, 800)
    row10 = tr.loc[np.isclose(tr.time_min, 10.)].iloc[0]
    checks['causal_t10_command'] = row10.command_mol_min == .0021 and row10.command_next_mol_min == .0024
    checks['command_integral_exact'] = abs(iv.commanded_ethanol_mol.sum() - (.0021 * 10 + .0024 * 11)) < 1e-14
    checks['branch_initial_state_exact'] = np.array_equal(branch['states'][0], truth['snapshots']['16.0'])
    checks['branch_absolute_clock'] = br.time_min.iloc[0] == 16 and br.time_min.iloc[-1] == 31
    checks['branch_constant_command_integral'] = abs(branch['intervals'].commanded_ethanol_mol.sum() - .0021 * 15) < 1e-14
    checks['health_continues_after_decision'] = abs(sc.health(21)[0] / sc.health(16)[0] - np.exp(-.0021 * 5)) < 1e-14
    checks['finite_outputs'] = np.isfinite(tr.select_dtypes(include='number')).all().all() and np.isfinite(truth['states']).all()
    checks['source_unchanged'] = before == source_hashes(1)
    checks['preconditioning_converged'] = truth['preconditioning']['metadata']['converged']
    checks['physical_initial_state_matches_preconditioning'] = np.array_equal(truth['states'][0], truth['preconditioning']['states'][-1])
    report = {'purpose': 'engineering smoke only, not a calibration or held-out performance experiment',
              'checks': {k: bool(v) for k, v in checks.items()}, 'all_pass': bool(all(checks.values())),
              'truth_integration_seconds': truth['metadata']['diagnostics']['wall_seconds'],
              'branch_integration_seconds': branch['metadata']['diagnostics']['wall_seconds'],
              'source_hashes': before}
    (dest / 'smoke.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2), flush=True)
    if not report['all_pass']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
