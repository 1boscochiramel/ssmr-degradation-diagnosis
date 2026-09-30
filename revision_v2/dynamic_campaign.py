"""Resumable frozen dynamic-truth and physical branch campaign.

No calibration or classification is implemented here. Launch requires the exact
frozen protocol hash supplied explicitly by the coordinator after checker freeze.
"""
from __future__ import annotations
import os
for _key in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS', 'VECLIB_MAXIMUM_THREADS'):
    os.environ[_key] = '1'

import argparse
from concurrent.futures import ProcessPoolExecutor, wait, FIRST_COMPLETED
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import time
import traceback
import numpy as np
import pandas as pd
import dynamics

ROOT = Path(__file__).resolve().parent
EXPECTED_ENGINE_SHA256 = 'c3873267636d2f3ae68d8d1dc968e248d66bed5dab79de45fa2f8ad158c77d27'


def utc():
    return datetime.now(timezone.utc).isoformat()


def digest(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def atomic_json(path, obj):
    path = Path(path)
    tmp = path.with_name(path.name + '.tmp')
    tmp.write_text(json.dumps(obj, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    tmp.replace(path)


def verify_source(protocol_path, protocol_hash):
    if digest(protocol_path) != protocol_hash:
        raise RuntimeError('Frozen protocol hash mismatch')
    if digest(ROOT / 'dynamics.py') != EXPECTED_ENGINE_SHA256:
        raise RuntimeError('Frozen dynamic engine hash mismatch')
    manifest = json.loads((ROOT / 'SOURCE_MANIFEST.json').read_text(encoding='utf-8'))
    for rel, expected in manifest['files'].items():
        if digest(ROOT / 'reference' / rel) != expected:
            raise RuntimeError(f'Immutable reference hash mismatch: {rel}')
    return {'protocol_sha256': protocol_hash, 'engine_sha256': EXPECTED_ENGINE_SHA256,
            'runner_sha256': digest(__file__), 'source_manifest_sha256': digest(ROOT / 'SOURCE_MANIFEST.json'),
            'reference_files_verified': len(manifest['files'])}


def verify_saved(folder):
    folder = Path(folder)
    meta = json.loads((folder / 'metadata.json').read_text(encoding='utf-8'))
    for path, expected in meta['source_hashes'].items():
        if digest(path) != expected:
            raise RuntimeError(f'Saved evidence source changed: {path}')
    for name, expected in meta.get('output_hashes', {}).items():
        if digest(folder / name) != expected:
            raise RuntimeError(f'Saved evidence output changed: {folder / name}')
    return meta


def load_truth(folder):
    folder = Path(folder)
    meta = verify_saved(folder)
    if meta['schema'] != 'ssmr.dynamic-truth.v1':
        raise RuntimeError(f'Not successful dynamic truth evidence: {folder}')
    trace = pd.read_csv(folder / 'truth.csv', float_precision='round_trip')
    with np.load(folder / 'states.npz', allow_pickle=False) as archive:
        states = archive['states'].copy()
        if not np.array_equal(archive['time_min'], trace.time_min.to_numpy()):
            raise RuntimeError(f'Trace/state time disagreement: {folder}')
    if sha256(states.astype('<f8').tobytes()).hexdigest() != meta['state_sha256']:
        raise RuntimeError(f'State checksum mismatch: {folder}')
    return dict(trace=trace, states=states,
        intervals=pd.read_csv(folder / 'intervals.csv', float_precision='round_trip'),
        scenario=meta['scenario'], metadata=meta,
        snapshots={str(t): states[np.flatnonzero(np.isclose(trace.time_min, t))[0]].copy()
                   for t in (10., 16., 21.) if np.isclose(trace.time_min, t).any()})


def _scientific_failure(exc):
    return isinstance(exc, (dynamics.PreconditioningFailure, dynamics.UnreachableScenario, FloatingPointError)) or (
        isinstance(exc, RuntimeError) and ('Required step size is less than spacing' in str(exc)
                                         or str(exc).startswith('Preconditioning ODE failed:')))


def _record_result(folder, record):
    folder.mkdir(parents=True, exist_ok=True)
    atomic_json(folder / 'dynamic_record.json', record)
    return record


def work(task, protocol):
    key, kind = task['key'], task['kind']
    folder = ROOT / ('dynamic_truth' if kind == 'truth' else 'dynamic_branches') / key
    started, tic = utc(), time.perf_counter()
    # Recovery can reuse only complete, hash-verified records from this frozen run.
    if (folder / 'dynamic_record.json').exists():
        record = json.loads((folder / 'dynamic_record.json').read_text(encoding='utf-8'))
        if record['status'] == 'complete':
            verify_saved(folder)
        if record['status'] == 'infrastructure_failure':
            raise RuntimeError(f'Prior infrastructure failure requires manual review: {folder}')
        return record
    if folder.exists():
        raise RuntimeError(f'Incomplete output directory preserved; manual review required: {folder}')
    try:
        case = task['case']
        if kind == 'truth':
            settings = {k: protocol['solver'][k] for k in ('sample_min', 'rtol', 'atol', 'max_step_min')}
            result = dynamics.run_truth(case['mode'], case['h'], case['drop'], task['active'],
                duration_min=max(protocol['looks_min']), move_mol_min=protocol['active_feed_increment'],
                controls=case['controls'], initialization='preconditioned', output_dir=folder, **settings)
            row = {'actual_dynamic_true_drop_at10': result['metadata']['actual_dynamic_true_drop_at10'],
                   'actual_dynamic_observed_drop_at10': result['metadata']['actual_dynamic_observed_drop_at10'],
                   'precondition_status': result['metadata']['preconditioning']['status'],
                   'precondition_minutes': result['metadata']['preconditioning']['minutes'],
                   'health_in_map_domain_all': bool(result['trace'].health_in_map_domain.all()),
                   'feed_in_map_domain_all': bool(result['trace'].feed_in_map_domain.all()),
                   'trace_rows': len(result['trace']),
                   'dynamic_integration_seconds': result['metadata']['diagnostics']['wall_seconds']}
        else:
            parent_folder = ROOT / 'dynamic_truth' / task['parent_key']
            truth = load_truth(parent_folder)
            result = dynamics.continue_truth(truth, task['decision_min'], task['command_mol_min'],
                horizon_end_min=protocol['policy']['horizon_end_min'], output_dir=folder)
            row = dynamics.policy_cost(truth, result)
            row.update(command_index=task['command_index'], command_mol_min=task['command_mol_min'],
                       parent_key=task['parent_key'], decision_time=task['decision_min'])
        record = dict(key=key, kind=kind, status='complete', case_id=case['id'], mode=case['mode'],
            h=case['h'], category=case['category'], active=task['active'], started_utc=started,
            finished_utc=utc(), wall_seconds=time.perf_counter() - tic,
            metadata_sha256=digest(folder / 'metadata.json'), result=row)
        return _record_result(folder, record)
    except Exception as exc:
        record = dict(key=key, kind=kind, status='scientific_failure' if _scientific_failure(exc) else 'infrastructure_failure',
            case_id=task['case']['id'], active=task['active'], started_utc=started, finished_utc=utc(),
            wall_seconds=time.perf_counter() - tic, error_type=type(exc).__name__, error=str(exc),
            traceback=traceback.format_exc())
        _record_result(folder, record)
        if not _scientific_failure(exc):
            raise
        return record


def run_stage(tasks, state, protocol, workers, status_path):
    pending = []
    for task in tasks:
        existing = state['tasks'].get(task['key'])
        if existing and existing['status'] in ('complete', 'scientific_failure', 'blocked_parent_failure'):
            if existing['status'] == 'complete':
                folder = ROOT / ('dynamic_truth' if task['kind'] == 'truth' else 'dynamic_branches') / task['key']
                verify_saved(folder)
                if digest(folder / 'metadata.json') != existing['metadata_sha256']:
                    raise RuntimeError(f'Stored metadata changed: {folder}')
            continue
        pending.append(task)
    if not pending:
        return
    with ProcessPoolExecutor(max_workers=workers) as pool:
        running = {}
        next_index = 0
        while next_index < len(pending) or running:
            while next_index < len(pending) and len(running) < workers:
                task = pending[next_index]
                next_index += 1
                previous = state['tasks'].get(task['key'])
                state['tasks'][task['key']] = dict(key=task['key'], kind=task['kind'], status='running',
                    submitted_utc=utc(), attempt=1 if previous is None else previous.get('attempt', 1) + 1)
                state['updated_utc'] = utc()
                atomic_json(status_path, state)
                running[pool.submit(work, task, protocol)] = task
            completed, _ = wait(running, timeout=30, return_when=FIRST_COMPLETED)
            for future in completed:
                task = running.pop(future)
                record = future.result()
                state['tasks'][task['key']] = record
                state['updated_utc'] = utc()
                atomic_json(status_path, state)
                print(json.dumps({k: record[k] for k in ('key', 'status', 'wall_seconds')}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--frozen-protocol-sha256', required=True)
    parser.add_argument('--workers', type=int, default=2, choices=(1, 2))
    parser.add_argument('--resume', action='store_true')
    args = parser.parse_args()
    protocol_path = ROOT / 'protocol.json'
    provenance = verify_source(protocol_path, args.frozen_protocol_sha256)
    protocol = json.loads(protocol_path.read_text(encoding='utf-8'))
    if protocol['solver']['method'] != 'BDF' or protocol['solver']['np'] != 50:
        raise RuntimeError('Protocol requests an unsupported solver or spatial grid')
    status_path = ROOT / 'dynamic_status.json'
    if status_path.exists():
        if not args.resume:
            raise RuntimeError('Existing dynamic status requires explicit --resume; never overwrite evidence')
        state = json.loads(status_path.read_text(encoding='utf-8'))
        if state['provenance'] != provenance:
            raise RuntimeError('Frozen campaign provenance changed on resume')
    else:
        if args.resume:
            raise RuntimeError('Cannot resume a campaign with no status record')
        if (ROOT / 'dynamic_truth').exists() or (ROOT / 'dynamic_branches').exists():
            raise RuntimeError('Fresh campaign destination already contains evidence')
        state = dict(schema='ssmr.dynamic-campaign.v1', started_utc=utc(), status='running',
            provenance=provenance, workers=args.workers, blas_threads=1,
            predeclared_excluded=protocol['excluded'], tasks={})
        atomic_json(status_path, state)
    truths = [dict(key=f"{c['id']}_{'active' if active else 'passive'}", kind='truth', case=c, active=active)
              for c in protocol['cases'] for active in (False, True)]
    branches = []
    try:
        run_stage(truths, state, protocol, args.workers, status_path)
        state['truth_stage_finished_utc'] = utc()
        atomic_json(status_path, state)
        print('All truth cases attempted; preparing physical policy branches.', flush=True)
        for task in truths:
            if not task['case']['policy']:
                continue
            commands = np.linspace(dynamics.U_SS[task['case']['mode']], dynamics.U_MAX,
                                   protocol['policy']['command_points'])
            for look in protocol['policy']['decision_times_min']:
                for index, command in enumerate(commands):
                    branch = dict(task, key=f"{task['key']}_t{look:g}_u{index}", kind='branch',
                        parent_key=task['key'], decision_min=float(look), command_index=index,
                        command_mol_min=float(command))
                    branches.append(branch)
                    if state['tasks'][task['key']]['status'] != 'complete':
                        state['tasks'][branch['key']] = dict(key=branch['key'], kind='branch',
                            status='blocked_parent_failure', parent_key=task['key'])
        atomic_json(status_path, state)
        run_stage(branches, state, protocol, args.workers, status_path)
        verify_source(protocol_path, args.frozen_protocol_sha256)
        rows = []
        for task in branches:
            record = state['tasks'][task['key']]
            rows.append(dict(key=task['key'], case_id=task['case']['id'], mode=task['case']['mode'],
                h=task['case']['h'], active=task['active'], status=record['status'],
                **record.get('result', {})))
        frame = pd.DataFrame(rows)
        tmp = ROOT / 'branch_costs.csv.tmp'
        frame.to_csv(tmp, index=False, float_format='%.17g')
        tmp.replace(ROOT / 'branch_costs.csv')
        statuses = [r['status'] for r in state['tasks'].values()]
        state.update(status='complete' if all(s == 'complete' for s in statuses) else 'complete_with_scientific_failures',
            finished_utc=utc(), expected_truths=len(truths), expected_branches=len(branches),
            status_counts={s: statuses.count(s) for s in sorted(set(statuses))},
            branch_costs_sha256=digest(ROOT / 'branch_costs.csv'))
        atomic_json(status_path, state)
        print(json.dumps({k: state[k] for k in ('status', 'expected_truths', 'expected_branches', 'status_counts')}), flush=True)
        return 0 if state['status'] == 'complete' else 2
    except Exception:
        state.update(status='infrastructure_failure', failed_utc=utc(), infrastructure_traceback=traceback.format_exc())
        atomic_json(status_path, state)
        raise


if __name__ == '__main__':
    raise SystemExit(main())
