"""Versioned local review packet; excludes large raw states and reference PDFs."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,zipfile
ROOT=Path(__file__).resolve().parent;PARENT=ROOT.parent;BASE=PARENT.parent
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def js(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def main():
    qa=js(ROOT/'note/RELEASE_QA.json');assert qa['pass'] and not qa['issues']
    pdf=ROOT/'output/pdf/SSMR_SCIENTIFIC_NOTE_V3_LOCAL_REVIEW.pdf';assert sha(pdf)==qa['pdf_sha256']
    items={pdf:'SSMR_SCIENTIFIC_NOTE_V3_LOCAL_REVIEW.pdf'}
    items[ROOT/'note/tradeoff.png']='equal_ethanol/note/tradeoff.png'
    for rel in ['protocol.json','PROTOCOL_AMENDMENT.txt','AMENDMENT_FREEZE.json','parent_inventory.json','schedule_inventory.json','trial_schedule_map.csv','prepare_equal_ethanol.py','run_equal_ethanol.py','run_status.json','build_local_packet.py']:
        items[ROOT/rel]='equal_ethanol/'+rel
    for folder in ['outputs','checks','benchmark_audit','note']:
        for p in sorted((ROOT/folder).rglob('*')):
            if p.is_file() and p.suffix in ['.csv','.json','.txt','.py'] and '__pycache__' not in p.parts:
                items[p]='equal_ethanol/'+p.relative_to(ROOT).as_posix()
    for p in sorted((ROOT/'branches').rglob('*')):
        if p.is_file() and p.name in ['truth.csv','intervals.csv','metadata.json','solver_input_evidence.json','execution.json','solver_input_capture.npz']:
            items[p]='equal_ethanol/'+p.relative_to(ROOT).as_posix()
    selected=['results/diagnosis_summary.csv','results/policy_trials.csv','results/policy_paired_differences.csv','protocol.json','PROTOCOL_FREEZE.json','dynamics.py','dynamic_campaign.py','revision_model.py','revision_policy.py','checks/final_check.json',
        'amendment_feed_only_20260930/PROTOCOL_AMENDMENT.txt','amendment_feed_only_20260930/outputs/paired_summary.csv','amendment_feed_only_20260930/outputs/paired_trials.csv','amendment_feed_only_20260930/outputs/feed_only_arm_costs.csv','amendment_feed_only_20260930/checks/verification.json','amendment_feed_only_20260930/literature/fulltext_access_manifest.json','amendment_feed_only_20260930/literature/fulltext_review.txt','amendment_feed_only_20260930/literature/prior_work_trace.txt']
    for rel in selected:items[PARENT/rel]='prior_sources/'+rel
    evidence=js(ROOT/'benchmark_audit/findings_evidence.json')
    for name in evidence['source_files']:
        p=Path(name)
        if p.suffix in ['.m','.mat','.csv'] and 'full_rerun' in p.parts:
            items[p]='benchmark_raw/'+p.relative_to(BASE/'full_rerun').as_posix()
    readme='''LOCAL REVIEW DRAFT - NOT CLEARED FOR EXTERNAL RELEASE

Start with the six-page PDF. It includes the equal-ethanol comparison, all healthy
and meter-bias action cells, the full 27-point monochrome trade-off figure, and
three qualified findings on the benchmark code. Different-model review and the
user's own rewrite remain pending. No message or publication has been sent.

The equal-ethanol arm is a retrospective resource-matched constant command from
minute10 to31. Its budget comes from each original diagnostic episode; it uses
no diagnosis or measurements during its own run. It changes feed timing and
removes the pulse. It cannot establish the isolated information value of diagnosis
or dominance over every blind schedule. Every original central S4 episode is kept.
Amounts in CSVs are mol. The note and figure use mmol. New difference columns mean
diagnostic minus blind; the figure shows the PRIOR same-pulse comparison with
shortfall sign reversed so positive means shortfall avoided.

Included: all new paired trial costs and summaries; all new interval/observation
CSV files and solver-input captures; code, freezes, check reports and source hashes;
prior table sources; primary benchmark .m code and saved native trace/state files
used for the three code findings. Copyrighted paper PDFs, extracted full texts,
paper screenshots and the large new states.npz arrays are excluded.

This is a local review packet, not a portable complete simulation archive. Full
ODE replay and the strict parent-preservation checker require the complete original
local directory tree and its recorded source paths. The unchanged prior archive
alone omits internal files covered by the whole-parent inventory. Full new raw states
remain in major_revision_v2/amendment_equal_ethanol_20260930/branches on this host.
Neither omitted records nor old failed gates have been relabelled as passing.

Review status: same-model arithmetic/source checks complete; different-model review
NOT DONE. tools/ask_model.ps1 defaults to a cloud model. It has NOT been called for
this revision under the user's local-only instruction. A future reviewer must
respect that restriction and choose an authorized review route.

PACKAGE_MANIFEST.json records SHA256 and size for each payload. The separate
CHECK report verifies CRC and every payload hash. No original PDF or ZIP is replaced.
'''
    review='''INDEPENDENT REVIEW REQUEST - LOCAL DRAFT

Read the complete six-page note before assessing the headline. Recompute the
numbers from the supplied CSVs; QA files are claims to inspect, not authorities.
1. Does the equal-ethanol constant-feed control match actual ethanol per episode,
   preserve all cases, and justify exactly the conclusion stated? Identify any
   residual confounding from retrospective budgets or changed timing.
2. Are healthy and meter-bias actions reported without favorable selection? Check
   M1 meter-bias S1 and the tiny nonzero Mode1 shortfall changes.
3. Are all 27 figure points correctly signed, in mmol, legible in black and white?
4. Do Eq13 integration, np200 initialization/mesh effects and PID persistence agree
   with primary code and raw records? Are provenance gaps preserved?
5. Does the Santra comparison match its implemented model, and do conclusions avoid
   novelty, safety, pure-information-value or economic claims unsupported by evidence?
Return material findings with exact source pointers, distinguishing verified,
unchecked and contradicted claims. Do not edit or publish anything. State the actual
review model and execution environment. This file does not authorize cloud transfer.
'''
    manifest={'created_utc':datetime.now(timezone.utc).isoformat(),'scope':'Local review packet; full-state replay remains on host','pdf_sha256':sha(pdf),'files':{name:{'sha256':sha(p),'bytes':p.stat().st_size} for p,name in items.items()}}
    dest=BASE/'SSMR_V3_LOCAL_REVIEW_PACKET.zip';tmp=dest.with_suffix('.zip.tmp')
    with zipfile.ZipFile(tmp,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for p,name in items.items():z.write(p,name)
        z.writestr('START_HERE.txt',readme);z.writestr('CROSS_MODEL_REVIEW_REQUEST.txt',review);z.writestr('PACKAGE_MANIFEST.json',json.dumps(manifest,indent=2))
    with zipfile.ZipFile(tmp) as z:
        assert z.testzip() is None
        for name,v in manifest['files'].items():assert hashlib.sha256(z.read(name)).hexdigest()==v['sha256']
    tmp.replace(dest)
    out={'pass':True,'path':str(dest),'bytes':dest.stat().st_size,'sha256':sha(dest),'payloads':len(items),'pdf_sha256':sha(pdf)}
    (BASE/'SSMR_V3_LOCAL_REVIEW_PACKET_CHECK.json').write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2))
if __name__=='__main__':main()
