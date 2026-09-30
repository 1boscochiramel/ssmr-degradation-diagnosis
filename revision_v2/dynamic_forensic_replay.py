"""Exact forensic replay of dense-output endpoint discrepancies; no relaxed gates."""
import os
for key in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS', 'VECLIB_MAXIMUM_THREADS'):
    os.environ[key] = '1'
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import traceback
import numpy as np
import pandas as pd
import dynamics as d
import dynamic_campaign as campaign

ROOT = Path(__file__).resolve().parent
FREEZE = ROOT / 'dynamic_FORENSIC_FREEZE.json'
OUT = ROOT / 'dynamic_forensic_results'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def array_sha(values):
    return hashlib.sha256(np.asarray(values, dtype='<f8').tobytes()).hexdigest()


def freeze():
    if FREEZE.exists() or OUT.exists():
        raise FileExistsError('Forensic destination/freeze already exists')
    diagnosis = json.loads((ROOT / 'dynamic_dense_diagnosis.json').read_text())
    tasks = []
    for rec in diagnosis['records']:
        if rec['first_state_bitwise_equal_to_intended_y0']:
            continue
        folder = ROOT / ('dynamic_truth' if rec['kind'] == 'truth' else 'dynamic_branches') / rec['key']
        tasks.append(dict(key=rec['key'], kind=rec['kind'],
            metadata_sha256=sha(folder / 'metadata.json'), states_npz_sha256=sha(folder / 'states.npz'),
            truth_csv_sha256=sha(folder / 'truth.csv'), intervals_csv_sha256=sha(folder / 'intervals.csv'),
            dynamic_record_sha256=sha(folder / 'dynamic_record.json')))
    if len(tasks) != 32:
        raise RuntimeError('Affected-record inventory differs from diagnosed32; stop before freeze')
    data = dict(frozen_utc=datetime.now(timezone.utc).isoformat(),
        scope='Forensic replay of original records; unchanged solver/model and no parameter/threshold fitting',
        exact_checks=['full regenerated state arrays identical to archived arrays',
            'full regenerated truth and interval CSV bytes identical to originals',
            'every solver output initial state identical to passed input',
            'first main solve input identical to intended precondition/explicit-parent state',
            'first main dense output identical to archived first state',
            'all seven recomputed initial features identical using intended exact state',
            'original exact exported-state failure remains explicitly false'],
        comparison_tolerance='None: numpy.array_equal, exact numeric equality, and SHA256 only',
        files={name: sha(ROOT / name) for name in ('dynamic_forensic_replay.py', 'dynamics.py',
            'dynamic_campaign.py', 'protocol.json', 'dynamic_dense_diagnosis.json')},
        tasks=tasks)
    FREEZE.write_text(json.dumps(data, indent=2) + '\n')
    print(json.dumps({'frozen': str(FREEZE), 'records': len(tasks), 'comparer_sha256': data['files']['dynamic_forensic_replay.py']}, indent=2))


def replay(task):
    folder = ROOT / ('dynamic_truth' if task['kind'] == 'truth' else 'dynamic_branches') / task['key']
    dest = OUT / task['key']
    dest.mkdir(parents=True, exist_ok=False)
    try:
        metadata = campaign.verify_saved(folder)
        record = json.loads((folder / 'dynamic_record.json').read_text())
        with np.load(folder / 'states.npz', allow_pickle=False) as z:
            archived = z['states'].copy()
        trace = pd.read_csv(folder / 'truth.csv', float_precision='round_trip')
        if task['kind'] == 'truth':
            with np.load(folder / 'precondition_states.npz', allow_pickle=False) as z:
                intended = z['states'][-1].copy()
            protocol = json.loads((ROOT / 'protocol.json').read_text())
            case = next(c for c in protocol['cases'] if c['id'] == record['case_id'])
        else:
            parent_key = record['result']['parent_key']
            parent = campaign.load_truth(ROOT / 'dynamic_truth' / parent_key)
            ix = np.flatnonzero(np.isclose(parent['trace'].time_min, metadata['parent_decision_min'], atol=1e-12, rtol=0.))
            if len(ix) != 1:
                raise RuntimeError('Ambiguous explicit parent decision state')
            intended = parent['states'][ix[0]].copy()
        original_solver = d.solve_ivp
        captures = []
        main_input = []

        def intercepted(fun, interval, y0, **kwargs):
            y0_copy = np.asarray(y0).copy()
            sol = original_solver(fun, interval, y0, **kwargs)
            dense_first = sol.sol(interval[0])
            capture = dict(interval=list(interval), function_qualname=fun.__qualname__,
                input_sha256=array_sha(y0_copy), solver_first_sha256=array_sha(sol.y[:, 0]),
                dense_first_sha256=array_sha(dense_first),
                solver_first_equals_input=bool(np.array_equal(sol.y[:, 0], y0_copy)),
                dense_first_equals_input=bool(np.array_equal(dense_first, y0_copy)))
            captures.append(capture)
            if not main_input and fun.__qualname__.startswith('_integrate.') and interval[0] == trace.time_min.iloc[0]:
                main_input.append(dict(input_matches_intended=bool(np.array_equal(y0_copy, intended)),
                    dense_matches_archived_first=bool(np.array_equal(dense_first, archived[0])),
                    input_sha256=array_sha(y0_copy), dense_sha256=array_sha(dense_first),
                    intended_sha256=array_sha(intended), archived_first_sha256=array_sha(archived[0])))
            return sol

        d.solve_ivp = intercepted
        try:
            if task['kind'] == 'truth':
                result = d.run_truth(case['mode'], case['h'], case['drop'], record['active'],
                    duration_min=max(protocol['looks_min']), move_mol_min=protocol['active_feed_increment'],
                    controls=case['controls'], initialization='preconditioned',
                    **{k: protocol['solver'][k] for k in ('sample_min', 'rtol', 'atol', 'max_step_min')})
            else:
                result = d.continue_truth(parent, metadata['parent_decision_min'],
                    record['result']['command_mol_min'], horizon_end_min=metadata['segments'][-1][1])
        finally:
            d.solve_ivp = original_solver
        np.savez_compressed(dest / 'regenerated_states.npz', states=result['states'])
        result['trace'].to_csv(dest / 'regenerated_truth.csv', index=False, float_format='%.17g')
        result['intervals'].to_csv(dest / 'regenerated_intervals.csv', index=False, float_format='%.17g')
        sc = d.Scenario(**metadata['scenario'])
        ac, am, fg, bias = sc.health(float(trace.time_min.iloc[0]))
        p = d.DynamicParameters(*d.MODES[sc.mode][:2], 50, a_c=ac, a_m=am, kinetic_scales=sc.kinetic_scales)
        row = trace.iloc[0]
        features = d.observables(d.evaluate(intended, np.array([row.command_mol_min * fg, row.water_mol_min]), p)[1])
        checks = dict(regenerated_full_states_equal_archived=bool(np.array_equal(result['states'], archived)),
            regenerated_truth_csv_identical=sha(dest / 'regenerated_truth.csv') == task['truth_csv_sha256'],
            regenerated_intervals_csv_identical=sha(dest / 'regenerated_intervals.csv') == task['intervals_csv_sha256'],
            all_solver_initial_states_equal_inputs=all(c['solver_first_equals_input'] for c in captures),
            first_main_input_matches_intended=len(main_input) == 1 and main_input[0]['input_matches_intended'],
            first_main_dense_matches_archived=len(main_input) == 1 and main_input[0]['dense_matches_archived_first'],
            intended_state_all_features_equal_archived=all(float(features[f]) == float(row['true_' + f]) for f in d.FEATURES),
            original_exact_exported_state_failure_preserved=not np.array_equal(archived[0], intended))
        out = dict(key=task['key'], kind=task['kind'], passed=all(checks.values()), checks=checks,
                   captures=captures, first_main_solve=main_input,
                   regenerated_state_sha256=array_sha(result['states']), archived_state_sha256=array_sha(archived),
                   original_export_max_abs_difference=float(np.max(np.abs(archived[0] - intended))))
        (dest / 'forensic.json').write_text(json.dumps(out, indent=2) + '\n')
        return out
    except Exception:
        error = dict(key=task['key'], kind=task['kind'], passed=False, traceback=traceback.format_exc())
        (dest / 'forensic.json').write_text(json.dumps(error, indent=2) + '\n')
        return error


def run():
    frozen = json.loads(FREEZE.read_text())
    for name, expected in frozen['files'].items():
        if sha(ROOT / name) != expected:
            raise RuntimeError('Forensic frozen file changed: ' + name)
    for task in frozen['tasks']:
        folder = ROOT / ('dynamic_truth' if task['kind'] == 'truth' else 'dynamic_branches') / task['key']
        for filename, key in [('metadata.json', 'metadata_sha256'), ('states.npz', 'states_npz_sha256'),
            ('truth.csv', 'truth_csv_sha256'), ('intervals.csv', 'intervals_csv_sha256'), ('dynamic_record.json', 'dynamic_record_sha256')]:
            if sha(folder / filename) != task[key]:
                raise RuntimeError('Archived forensic input changed: ' + str(folder / filename))
    OUT.mkdir(exist_ok=False)
    results = []
    with ProcessPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(replay, task) for task in frozen['tasks']]
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            print(json.dumps({'key': result['key'], 'passed': result['passed']}), flush=True)
    summary = dict(schema='ssmr.dense-forensic.v1', finished_utc=datetime.now(timezone.utc).isoformat(),
        passed=all(r['passed'] for r in results), records=len(results), freeze_sha256=sha(FREEZE),
        scope='Exact forensic replay proves source of original export discrepancy; original exact-output gate remains failed and original records unchanged',
        results=sorted(results, key=lambda r: r['key']))
    (ROOT / 'dynamic_forensic_summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps({'passed': summary['passed'], 'records': len(results)}, indent=2))
    return 0 if summary['passed'] else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('freeze', 'run'))
    args = parser.parse_args()
    if args.phase == 'freeze':
        freeze()
    else:
        raise SystemExit(run())
