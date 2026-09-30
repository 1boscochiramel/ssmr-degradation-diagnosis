"""Read-only hash verification after relocation; no recorded paths are rewritten.

This is an integrity/portability adapter, not a replacement for the frozen
scientific checks or an independent differential-equation solver.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath


def verify(root):
    root = Path(root).resolve()
    issues, checked, resolved = [], {}, set()

    def check(path, expected, label):
        path = Path(path)
        if not path.is_file():
            issues.append(label + ': missing file')
            return
        if path not in checked:
            checked[path] = hashlib.sha256(path.read_bytes()).hexdigest()
        if checked[path] != expected:
            issues.append(label + ': hash mismatch')

    def safe_relative(rel):
        p = PurePosixPath(str(rel).replace('\\', '/'))
        if p.is_absolute() or '..' in p.parts or any(':' in part for part in p.parts):
            raise ValueError('Unsafe relative provenance path: ' + str(rel))
        dest = root.joinpath(*p.parts).resolve()
        if not dest.is_relative_to(root):
            raise ValueError('Provenance path leaves artifact root')
        return dest

    manifest = json.loads((root / 'SOURCE_MANIFEST.json').read_text(encoding='utf-8'))
    for rel, expected in manifest['files'].items():
        check(safe_relative('reference/' + rel), expected, 'reference/' + rel)
    for name in ('PROTOCOL_FREEZE.json', 'POLICY_AMENDMENT_FREEZE.json', 'dynamic_ENGINE_FREEZE.json'):
        data = json.loads((root / name).read_text(encoding='utf-8'))
        for rel, expected in data['files'].items():
            check(safe_relative(rel), expected, name + '/' + rel)
    math_freeze = json.loads((root / 'checks/MATH_FREEZE.json').read_text(encoding='utf-8'))
    for rel, expected in math_freeze['sha256'].items():
        check(safe_relative('checks/' + rel), expected, 'math freeze/' + rel)
    counts = {}
    for directory in ('dynamic_truth', 'dynamic_branches'):
        records = sorted((root / directory).glob('*/metadata.json'))
        counts[directory] = len(records)
        for meta_path in records:
            meta = json.loads(meta_path.read_text(encoding='utf-8'))
            label = str(meta_path.parent.relative_to(root))
            wrapper = [name.replace('\\', '/') for name in meta['source_hashes']
                       if name.replace('\\', '/').endswith('/dynamics.py')]
            if len(wrapper) != 1:
                issues.append(label + ': ambiguous recorded source root')
                continue
            original_root = wrapper[0][:-len('/dynamics.py')]
            for recorded, expected in meta['source_hashes'].items():
                normalized = recorded.replace('\\', '/')
                if not normalized.startswith(original_root + '/'):
                    issues.append(label + ': source outside recorded artifact root')
                    continue
                rel = normalized[len(original_root) + 1:]
                path = safe_relative(rel)
                resolved.add(rel)
                check(path, expected, label + '/relocated source/' + rel)
            for rel, expected in meta['output_hashes'].items():
                if PurePosixPath(rel).name != rel:
                    issues.append(label + ': nonlocal output path')
                    continue
                check(meta_path.parent / rel, expected, label + '/output/' + rel)
    protocol = json.loads((root / 'protocol.json').read_text(encoding='utf-8'))
    status = json.loads((root / 'dynamic_status.json').read_text(encoding='utf-8'))
    expected_truths = len(protocol['cases']) * 2
    expected_branches = sum(c['policy'] for c in protocol['cases']) * 2 * len(protocol['policy']['decision_times_min']) * protocol['policy']['command_points']
    for name, number in [('dynamic_truth', expected_truths), ('dynamic_branches', expected_branches)]:
        if counts[name] != number:
            issues.append(f'{name}: expected {number} records, found {counts[name]}')
    if status['status'] != 'complete':
        issues.append('Campaign status is not complete')
    for key, rel in [('protocol_sha256', 'protocol.json'), ('engine_sha256', 'dynamics.py'),
                     ('runner_sha256', 'dynamic_campaign.py'), ('source_manifest_sha256', 'SOURCE_MANIFEST.json')]:
        check(root / rel, status['provenance'][key], 'campaign provenance/' + rel)
    check(root / 'branch_costs.csv', status['branch_costs_sha256'], 'branch costs')
    for key, entry in status['tasks'].items():
        if entry['status'] != 'complete':
            issues.append('Non-complete task: ' + key)
            continue
        directory = 'dynamic_truth' if entry['kind'] == 'truth' else 'dynamic_branches'
        check(root / directory / key / 'metadata.json', entry['metadata_sha256'], 'task metadata/' + key)
    return dict(schema='ssmr.portable-integrity.v1', created_utc=datetime.now(timezone.utc).isoformat(),
        artifact_root=str(root), passed=not issues, issues=issues, records=counts,
        unique_files_hashed=len(checked), remapped_source_paths=sorted(resolved),
        scope='Hash integrity and complete physical record inventory after explicit source-root remapping; no metadata edits, scientific acceptance changes, stochastic recalibration, or independent ODE solve.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    result = verify(args.root)
    args.out.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: result[k] for k in ('passed', 'issues', 'records', 'unique_files_hashed')}, indent=2))
    raise SystemExit(0 if result['passed'] else 1)
