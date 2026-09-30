"""Read-only cache identity guard before resuming the frozen stochastic runner.

Does not import the scientific runner, inspect stochastic arrays, change caches,
or assess scientific acceptance. A failure requires investigation, not deletion
or automatic rebuilding. Run when the previous writer has stopped.
"""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import importlib.metadata
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def differences(actual, expected):
    """Compare complete declared metadata fields, including types for integers."""
    return [key for key, value in expected.items()
            if key not in actual or actual[key] != value
            or isinstance(value, (bool, int)) and type(actual[key]) is not type(value)]


def check(root):
    root = Path(root).resolve()
    issues, checked = [], []
    hash_count = 0

    def issue(path, message):
        issues.append({'path': str(path), 'issue': message})

    def inside(relative):
        p = (root / str(relative).replace('\\', '/')).resolve()
        try:
            p.relative_to(root)
        except ValueError:
            issue(relative, 'Path leaves the revision workspace')
            return None
        return p

    def load(relative):
        p = inside(relative)
        try:
            return json.loads(p.read_text(encoding='utf-8')) if p else {}
        except (OSError, ValueError) as exc:
            issue(relative, 'Cannot read required JSON: ' + str(exc))
            return {}

    def hash_check(relative, expected):
        nonlocal hash_count
        p = inside(relative)
        if not p:
            return
        if not isinstance(expected, str) or len(expected) != 64:
            issue(relative, 'Missing or malformed expected SHA-256')
            return
        try:
            hash_count += 1
            if sha(p) != expected:
                issue(relative, 'SHA-256 differs from the recorded identity')
        except OSError as exc:
            issue(relative, 'Cannot hash required file: ' + str(exc))

    def stamp(value, path):
        try:
            parsed = dt.datetime.fromisoformat(value)
            if parsed.tzinfo is None:
                raise ValueError('timestamp is not timezone-aware')
            return parsed
        except (TypeError, ValueError) as exc:
            issue(path, 'Invalid UTC timestamp: ' + str(exc))
            return None

    protocol = load('protocol.json')
    for freeze_name in ['PROTOCOL_FREEZE.json', 'POLICY_AMENDMENT_FREEZE.json']:
        freeze = load(freeze_name)
        if not freeze.get('files'):
            issue(freeze_name, 'No frozen identities present')
        for name, expected in freeze.get('files', {}).items():
            hash_check(name, expected)
    integration = load('checks/INTEGRATION_FREEZE.json')
    for name, expected in integration.get('sha256', {}).items():
        hash_check('checks/' + name, expected)
    for name, field in [('statistical_campaign.py', 'statistical_pipeline_sha256'),
                        ('protocol.json', 'protocol_sha256'),
                        ('checks/MATH_FREEZE.json', 'math_freeze_sha256'),
                        ('checks/integration_selftest.json', 'synthetic_evidence_sha256')]:
        hash_check(name, integration.get(field))
    integration_time = stamp(integration.get('created_utc'), 'checks/INTEGRATION_FREEZE.json')
    source_manifest = load('SOURCE_MANIFEST.json')
    for name, expected in source_manifest.get('files', {}).items():
        hash_check('reference/' + name, expected)
    current_hashes = {}
    for field, name in [('protocol_sha256', 'protocol.json'), ('pipeline_sha256', 'statistical_campaign.py'),
                        ('policy_sha256', 'revision_policy.py'), ('model_sha256', 'revision_model.py')]:
        try:
            current_hashes[field] = sha(root / name)
        except OSError as exc:
            issue(name, str(exc))
    cases = {c['id']: c for c in protocol.get('cases', [])}
    if not cases or len(cases) != len(protocol.get('cases', [])):
        issue('protocol.json', 'Case identities missing or duplicated')

    seal_path = root / 'results/EVALUATION_FREEZE.json'
    seal = load('results/EVALUATION_FREEZE.json') if seal_path.exists() else {}
    seal_time = stamp(seal.get('created_utc'), seal_path) if seal else None
    if seal:
        hash_check('results/calibration.json', seal.get('calibration_sha256'))
    calibration_path = root / 'results/calibration.json'
    if calibration_path.exists():
        calibration_identity = load('results/calibration.json').get('protocol_sha256')
        if calibration_identity != current_hashes.get('protocol_sha256'):
            issue(calibration_path, 'Calibration protocol identity differs')

    batch_dir = root / 'results/batches'
    for meta_path in sorted(batch_dir.glob('*.json')):
        relative = meta_path.relative_to(root)
        meta = load(relative)
        case = cases.get(meta.get('case_id'))
        if case is None:
            issue(relative, 'Unknown case identity')
            continue
        phase = meta.get('phase')
        active = meta.get('active')
        if phase not in ['calibration', 'evaluation', 'stress'] or type(active) is not bool:
            issue(relative, 'Invalid phase or non-boolean activity')
            continue
        stress_index = meta.get('stress_index')
        noise = {}
        extra = 0
        if phase == 'stress':
            stress = protocol.get('observation_stress', [])
            if type(stress_index) is not int or not 0 <= stress_index < len(stress) or not case.get('policy'):
                issue(relative, 'Invalid stress index or ineligible stress case')
                continue
            noise = {k: v for k, v in stress[stress_index].items() if k != 'name'}
            extra = stress_index * 1000
        elif stress_index is not None:
            issue(relative, 'Non-stress batch has a stress index')
        if phase == 'calibration' and case.get('category') != 'covered_grid':
            issue(relative, 'Calibration batch is outside the covered grid')
        try:
            seed = protocol['seed_base'] + case['index'] * 100000 + protocol['phase_offsets'][phase] + extra
            count = protocol[{'calibration': 'n_calibration', 'evaluation': 'n_evaluation', 'stress': 'n_stress'}[phase]]
        except KeyError as exc:
            issue('protocol.json', 'Missing batch definition: ' + str(exc))
            continue
        activity = 'active' if active else 'passive'
        stem = f'{case["id"]}_{activity}_{phase}' + (f'_{stress_index}' if phase == 'stress' else '')
        truth_relative = f'dynamic_truth/{case["id"]}_{activity}'
        npz_relative = f'results/batches/{stem}.npz'
        expected = dict(case_id=case['id'], mode=case['mode'], true_hypothesis=case['h'],
                        category=case['category'], active=active, phase=phase,
                        stress_index=stress_index if phase == 'stress' else None,
                        seed=seed, n=count, noise_kwargs=noise,
                        rng='numpy.random.default_rng/PCG64',
                        numpy_version=importlib.metadata.version('numpy'), **current_hashes)
        bad = differences(meta, expected)
        if bad:
            issue(relative, 'Requested/frozen metadata mismatch: ' + ', '.join(bad))
        if meta_path.name != stem + '.json':
            issue(relative, 'Metadata filename does not match its case/split/activity')
        for field, wanted in [('truth_dir', truth_relative), ('npz_path', npz_relative)]:
            actual_path = inside(meta.get(field, '__missing__'))
            if actual_path != (root / wanted).resolve():
                issue(relative, field + ' differs from the canonical case/split path')
        hash_check(truth_relative + '/truth.csv', meta.get('truth_sha256'))
        hash_check(npz_relative, meta.get('npz_sha256'))
        created = stamp(meta.get('created_utc'), relative)
        if created and integration_time and created < integration_time:
            issue(relative, 'Batch predates integration freeze')
        if phase in ['evaluation', 'stress']:
            if not seal_time:
                issue(relative, 'Held-out batch has no valid evaluation freeze')
            elif created and created < seal_time:
                issue(relative, 'Held-out batch predates threshold seal')
        elif created and seal_time and created > seal_time:
            issue(relative, 'Calibration batch was written after evaluation freeze')
        checked.append(str(relative))
    # A concurrent writer may temporarily cause this failure. Wait for that writer;
    # never delete/rebuild the orphan to make the guard pass.
    for npz_path in batch_dir.glob('*.npz'):
        if not npz_path.name.endswith('_decisions.npz') and not npz_path.with_suffix('.json').exists():
            issue(npz_path.relative_to(root), 'NPZ has no completed metadata; active writer or incomplete cache')
    return dict(schema='ssmr.resume-metadata-guard.v1', pass_=not issues,
                checked_batch_metadata=len(checked), hashes_checked=hash_count,
                scope='Existing cache identities only; does not certify campaign completeness or scientific acceptance.',
                action_on_failure='Stop resume and investigate; this guard never changes, deletes or rebuilds caches.',
                issues=issues)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--out', type=Path, help='Optional new report; refuses to overwrite an existing file')
    args = parser.parse_args()
    result = check(args.root)
    result['pass'] = result.pop('pass_')
    result['guard_sha256'] = sha(Path(__file__))
    text = json.dumps(result, indent=2)
    if args.out:
        with args.out.open('x', encoding='utf-8') as stream:
            stream.write(text + '\n')
    print(text)
    return 0 if result['pass'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
