"""Package checked research evidence without downloaded literature full texts."""
from pathlib import Path
import hashlib
import json
import zipfile
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent
DEST = ROOT.parent / 'SSMR_MAJOR_REVISION_V2.zip'


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def main():
    check = json.loads((ROOT / 'checks/final_check.json').read_text())
    if not check.get('complete') or not check.get('computational_pass'):
        raise RuntimeError('Do not label an unaccepted campaign as a final evidence release.')
    doc = json.loads((ROOT / 'report/document_input_manifest.json').read_text())
    if doc.get('draft') or not doc.get('verified_input_gate'):
        raise RuntimeError('Final document input gate missing.')
    final_pdf = ROOT / 'output/pdf/SSMR_MAJOR_REVISION.pdf'
    if sha(final_pdf) != doc['pdf_sha256']:
        raise RuntimeError('Final PDF differs from its bound document manifest.')
    qa = json.loads((ROOT / 'report/FINAL_RELEASE_QA.json').read_text())
    if not qa.get('pass') or qa.get('pdf_sha256') != sha(final_pdf):
        raise RuntimeError('Fresh final layout/content QA is required.')
    excluded_dirs = {'__pycache__', 'sources', 'dynamic_portability_smoke_source'}
    files = []
    for path in sorted(ROOT.rglob('*')):
        if not path.is_file():
            continue
        relative = path.relative_to(ROOT)
        if any(p in excluded_dirs for p in relative.parts):
            continue
        if 'DRAFT' in str(relative) or path.suffix in {'.pyc', '.tmp'}:
            continue
        files.append((path, 'major_revision_v2/' + relative.as_posix()))
    files.extend([
        (ROOT.parent / 'SSMR_EXTERNAL_AUDIT_AND_RERUN.zip', 'historical/SSMR_EXTERNAL_AUDIT_AND_RERUN.zip'),
        (Path('C:/Users/Admin/Downloads/ssmr-degradation-diagnosis_audit_2026-09-30.zip'), 'historical/original_submission.zip'),
    ])
    entries = {name: {'bytes': path.stat().st_size, 'sha256': sha(path)} for path, name in files}
    manifest = {'created_utc': datetime.now(timezone.utc).isoformat(), 'files': entries,
                'scope': 'Research evidence for the user; downloaded literature fulltexts excluded from current revision. Historical ZIPs are preserved unchanged.',
                'start_here': 'major_revision_v2/output/pdf/SSMR_MAJOR_REVISION.pdf',
                'reproduce': 'major_revision_v2/REPRODUCE.txt'}
    instructions = ('Read major_revision_v2/output/pdf/SSMR_MAJOR_REVISION.pdf first.\n'
                    'Use major_revision_v2/REPRODUCE.txt for reproducibility and scope.\n'
                    'PACKAGE_MANIFEST.json inventories every archived file with SHA256.\n'
                    'The two historical ZIPs are unmodified earlier evidence, not new runs.\n')
    temp = DEST.with_suffix('.zip.tmp')
    with zipfile.ZipFile(temp, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path, name in files:
            # These formats already compress their payloads; recompression only
            # adds release time while leaving the content/integrity unchanged.
            compression = zipfile.ZIP_STORED if path.suffix.lower() in {'.npz', '.pdf', '.png', '.jpg', '.jpeg', '.zip'} else zipfile.ZIP_DEFLATED
            archive.write(path, name, compress_type=compression)
        archive.writestr('PACKAGE_MANIFEST.json', json.dumps(manifest, indent=2))
        archive.writestr('START_HERE.txt', instructions)
    with zipfile.ZipFile(temp) as archive:
        bad = archive.testzip()
        if bad:
            raise RuntimeError('ZIP CRC failure: ' + bad)
        for name, expected in entries.items():
            h = hashlib.sha256()
            with archive.open(name) as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b''):
                    h.update(block)
            if h.hexdigest() != expected['sha256']:
                raise RuntimeError('Archive hash mismatch: ' + name)
    temp.replace(DEST)
    result = {'pass': True, 'path': str(DEST), 'bytes': DEST.stat().st_size,
              'sha256': sha(DEST), 'verified_payload_files': len(entries),
              'pdf_sha256': sha(final_pdf), 'created_utc': datetime.now(timezone.utc).isoformat()}
    (ROOT.parent / 'SSMR_MAJOR_REVISION_V2_PACKAGE_CHECK.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
