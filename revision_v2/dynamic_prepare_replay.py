"""Prepare a new source-only replay tree without copying generated campaign data."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil


def prepare(source, destination):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if destination.exists():
        raise FileExistsError('Replay destination must not already exist')
    if destination == source or source.is_relative_to(destination):
        raise ValueError('Replay destination cannot contain the source artifact')
    required = {'dynamics.py', 'dynamic_campaign.py', 'dynamic_API.txt', 'revision_model.py',
                'revision_policy.py', 'statistical_campaign.py', 'protocol.json',
                'PROTOCOL_FREEZE.json', 'POLICY_AMENDMENT_FREEZE.json', 'SOURCE_MANIFEST.json',
                'dynamic_ENGINE_FREEZE.json', 'dynamic_prepare_replay.py', 'dynamic_portable_verify.py',
                'dynamic_environment.json', 'REPRODUCE.txt', 'checks/MATH_FREEZE.json',
                'checks/INTEGRATION_FREEZE.json', 'validate_resume.py',
                'dynamic_dense_diagnosis.py', 'dynamic_forensic_replay.py',
                'checks/DYNAMIC_IDENTITY_AMENDMENT.json', 'checks/DYNAMIC_PORTABLE_ADAPTER.json'}
    source_manifest = json.loads((source / 'SOURCE_MANIFEST.json').read_text(encoding='utf-8'))
    required.update('reference/' + name for name in source_manifest['files'])
    required.update(str(p.relative_to(source)).replace('\\', '/') for p in (source / 'checks').glob('*.py'))
    required.update(str(p.relative_to(source)).replace('\\', '/') for p in (source / 'checks').glob('*.txt'))
    for name in ('PROTOCOL_FREEZE.json', 'POLICY_AMENDMENT_FREEZE.json', 'dynamic_ENGINE_FREEZE.json'):
        freeze = json.loads((source / name).read_text(encoding='utf-8'))
        required.update(freeze['files'])
    for name in ('MATH_FREEZE.json', 'INTEGRATION_FREEZE.json'):
        freeze = json.loads((source / 'checks' / name).read_text(encoding='utf-8'))
        required.update('checks/' + rel for rel in freeze['sha256'])
        required.update('checks/' + rel for rel in freeze.get('analytic_evidence', []))
    # Retain pre-evaluation synthetic checker provenance required to interpret
    # the integration freeze, never the later campaign numerical audit reports.
    required.add('checks/integration_selftest.json')
    entries = {}
    for rel in sorted(required):
        p = PurePosixPath(rel)
        if p.is_absolute() or '..' in p.parts or any(':' in x for x in p.parts):
            raise ValueError('Unsafe source manifest path: ' + rel)
        old = source.joinpath(*p.parts)
        if not old.is_file():
            raise FileNotFoundError('Missing required replay source: ' + str(old))
        entries[rel] = hashlib.sha256(old.read_bytes()).hexdigest()
    prior_freeze = source / 'dynamic_FORENSIC_FREEZE.json'
    if not prior_freeze.is_file():
        prior_freeze = source / 'provenance_original/dynamic_FORENSIC_FREEZE.json'
    if not prior_freeze.is_file():
        raise FileNotFoundError('Original campaign forensic design provenance is missing')
    destination.mkdir(parents=True, exist_ok=False)
    for rel in entries:
        target = destination / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / rel, target)
        if hashlib.sha256(target.read_bytes()).hexdigest() != entries[rel]:
            raise RuntimeError('Copied source hash mismatch: ' + rel)
    # This freeze identifies the OLD run's specific metadata/array fingerprints.
    # Preserve its design history separately; a new forensic run must freeze its
    # own newly generated record identities and must not reuse this as a cache.
    provenance = destination / 'provenance_original'
    provenance.mkdir()
    shutil.copyfile(prior_freeze, provenance / prior_freeze.name)
    manifest = {'created_utc': datetime.now(timezone.utc).isoformat(), 'source_root': str(source),
                'destination_root': str(destination), 'source_file_hashes': entries,
                'campaign_outputs_copied': False,
                'preserved_run_specific_freeze': {'path': 'provenance_original/' + prior_freeze.name,
                    'sha256': hashlib.sha256(prior_freeze.read_bytes()).hexdigest(),
                    'active_replay_freeze': False},
                'note': 'Frozen reference maps are declared source inputs; copied synthetic checker reports are pre-evaluation provenance, not evidence that the new campaign ran.'}
    (destination / 'dynamic_STAGING.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument('--destination', type=Path, required=True)
    args = parser.parse_args()
    result = prepare(args.source, args.destination)
    print(json.dumps({'destination': result['destination_root'], 'files': len(result['source_file_hashes']),
                      'campaign_outputs_copied': result['campaign_outputs_copied']}, indent=2))
