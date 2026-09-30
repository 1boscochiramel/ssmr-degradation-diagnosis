"""Small review bundle; deliberately distinct from the complete raw-data archive."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,zipfile

ROOT=Path(__file__).resolve().parent
PARENT=ROOT.parent
DEST=PARENT.parent/'SSMR_SIX_PAGE_REVIEW_BUNDLE.zip'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text())
def main():
    qa=read(ROOT/'note/ROOT_RELEASE_QA.json')
    pdf=ROOT/'output/pdf/SSMR_SCIENTIFIC_NOTE_6_PAGES.pdf'
    if not qa['pass'] or qa['pdf_sha256']!=sha(pdf):raise RuntimeError('Final note QA required')
    if not qa['full_paper_read_completed']:raise RuntimeError('Full-paper reading is required for this final bundle')
    check=read(ROOT/'checks/verification.json')
    if not check['pass'] or not check['complete'] or check['issues']:raise RuntimeError('Frozen amendment audit required')
    note=read(ROOT/'note/note_input_manifest.json')
    for p,h in note['inputs'].items():
        if sha(p)!=h:raise RuntimeError('Document input changed: '+p)
    selected=[
        'PROTOCOL_AMENDMENT.txt','amendment_protocol.json','AMENDMENT_FREEZE.json','parent_inventory.json',
        'run_feed_only.py','prepare_amendment.py','verify_note_release.py','build_review_bundle.py',
        'run_status.json','user_reference_inventory.json','outputs/feed_only_arm_costs.csv','outputs/paired_summary.csv',
        'outputs/paired_trials.csv','outputs/summary.json',
        'checks/verification.json','checks/verification.log','checks/CHECK_SPEC.txt','checks/CHECK_FREEZE.json',
        'checks/audit_math.py','checks/test_audit_math.py','checks/verify_feed_only.py','checks/math_selftest.json',
        'note/build_note.py','note/prepare_note_inputs.py','note/amendment_table.json',
        'note/literature_status.json','note/note_input_manifest.json','note/FINAL_QA.json','note/ROOT_RELEASE_QA.json',
        'note/ROOT_RELEASE_QA_initial_failure.json','note/page1_wording_check.json',
        'literature/fulltext_review.txt','literature/fulltext_access_manifest.json','literature/prior_work_trace.txt','literature/ROOT_SOURCE_TRACE.json',
    ]
    items=[(pdf,'SSMR_SCIENTIFIC_NOTE_6_PAGES.pdf')]
    for rel in selected:
        p=ROOT/rel
        if not p.is_file():raise RuntimeError('Missing release input: '+rel)
        items.append((p,'amendment/'+rel))
    originals=['protocol.json','PROTOCOL_FREEZE.json','revision_model.py','revision_policy.py','dynamics.py',
        'SOURCE_MANIFEST.json','SOURCE_NOTES.txt','REPRODUCE.txt','results/diagnosis_summary.csv',
        'results/policy_paired_differences.csv','checks/final_check.json']
    for rel in originals:items.append((PARENT/rel,'original_review_sources/'+rel))
    entries={name:{'bytes':p.stat().st_size,'sha256':sha(p)} for p,name in items}
    instructions='''READ THE SIX-PAGE PDF FIRST

This small review bundle contains the note, the dated feed-only protocol,
all new paired trial amounts and summary tables, fixed-duration control costs,
check reports, and the code and source bindings used to produce them.
The note's main table uses four central all-sensor cases; the CSV files retain
every original policy case and sensor set in the amendment.

The full Santra (2026) paper supplied by the user was read. The source trace and
one-sentence comparison are included. Copyrighted paper PDFs, full-text dumps
and screenshots are excluded from this distributable bundle.

SCOPE OF REPRODUCIBILITY
This is a review/table supplement, NOT the complete raw-state archive.
The 18 new high-dimensional state arrays and the original stochastic arrays
are intentionally not included. The full raw amendment is retained locally in
major_revision_v2/amendment_feed_only_20260930/. SSMR_MAJOR_REVISION_V2.zip contains
the prior scientific evidence, but its release exclusions also omit internal
literature captures that the amendment's strict whole-parent inventory hashes.
The frozen full checker therefore requires the complete original local parent
tree and the new raw branches, in their original directory relationship; neither
this compact ZIP nor the earlier archive alone can satisfy its preservation
inventory. The original full archive remains unchanged.

To inspect tables, use amendment/outputs/. Differences are diagnostic action
minus feed-only with the same pulse end. Amounts in CSVs are mol; the note uses
mmol. Every trial remains in each denominator. The control schedules are blind,
but selecting the matched schedule uses the original diagnostic stopping time.
This is a downstream-action comparison, not total information value or a net
economic benefit. Both fixed-duration schedules are separately recorded.

To repeat the new continuations on this recorded host, use the complete original
parent tree, including its unchanged inventory-listed references. Create a
new direct child directory, copy only the amendment protocol, original-parent
inventory, runner, freeze and checker source files into it (not branches or
outputs), then run run_feed_only.py --workers 2 with the documented Python
environment. Run checks/verify_feed_only.py --root NEW_CHILD --out REPORT.json.
The original parent files must remain unchanged; the checker verifies their
hashes and reconstructs the original selected-action costs from raw evidence.
Original metadata also records host-absolute source paths. These replay steps
are a local-host procedure, not an automatically portable re-extraction recipe.
Exact replay checks are tied to the frozen source/runtime and are not a claim
of bit-identical results on different numerical platforms.

The original failed exported-start-state check remains explicitly qualified.
New comparator verification passed without changing it or the diagnostic method.
PACKAGE_MANIFEST.json inventories each bundled payload with SHA256.
'''
    manifest={'created_utc':datetime.now(timezone.utc).isoformat(),'scope':'Compact review supplement, not complete raw-state archive',
              'pdf_sha256':sha(pdf),'full_paper_read_completed':True,'files':entries}
    tmp=DEST.with_suffix('.zip.tmp')
    with zipfile.ZipFile(tmp,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for p,name in items:z.write(p,name)
        z.writestr('START_HERE.txt',instructions)
        z.writestr('PACKAGE_MANIFEST.json',json.dumps(manifest,indent=2))
    with zipfile.ZipFile(tmp) as z:
        if z.testzip():raise RuntimeError('ZIP CRC failure')
        for name,expected in entries.items():
            if hashlib.sha256(z.read(name)).hexdigest()!=expected['sha256']:raise RuntimeError('Archive mismatch '+name)
    tmp.replace(DEST)
    result={'pass':True,'path':str(DEST),'bytes':DEST.stat().st_size,'sha256':sha(DEST),
            'verified_payload_files':len(items),'pdf_sha256':sha(pdf),'created_utc':datetime.now(timezone.utc).isoformat()}
    (PARENT.parent/'SSMR_SIX_PAGE_REVIEW_BUNDLE_CHECK.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
if __name__=='__main__':main()
