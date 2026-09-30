"""Version a presentation contract without changing the frozen scientific audit."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,shutil
P=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
old=P/'verify_note.py';new=P/'verify_note_v2.py'
assert not new.exists()
shutil.copyfile(P/'RELEASE_QA.json',P/'RELEASE_QA_precision_v1.json')
text=old.read_text(encoding='utf-8')
edits=[
    ("def pct(x):return f'{100*x:.1f}%'", "def pct(x):return f'{100*x:.1f}%'\ndef cost(x):return f'{(0. if abs(x)<.000005 else x):.5f}'"),
    ("NOTE_CHECK_FREEZE.json", "NOTE_CHECK_FREEZE_V2.json"),
    ("'1.0208'", "'1.02075'"),
    ("f'{1000*r.difference_H2_shortfall_mol_mean:+.4f}'", "f'{1000*r.difference_H2_shortfall_mol_mean:+.6f}'"),
    ("f'{v.min():.4f} to {v.max():.4f}'", "cost(v.min())+' to '+cost(v.max())")
]
for before,after in edits:
    assert before in text,before
    text=text.replace(before,after)
new.write_text(text,encoding='utf-8')
reason={'created_utc':datetime.now(timezone.utc).isoformat(),'reason':'Display-only revision after visual review: show six decimals for small equal-resource differences, five decimals for control ethanol ranges, and round sub-display residuals to unsigned zero. Print adverse bias cost consistently as1.02075mmol. Previous four-decimal rendering passed its unchanged release check but hid one small contrast and produced inconsistent half-rounding in text versus table.','unchanged':'All raw values, scientific protocol, solver, physical acceptance thresholds and frozen scientific checker remain unchanged.','previous_check_sha256':sha(old),'previous_qa_sha256':sha(P/'RELEASE_QA_precision_v1.json'),'previous_pdf_sha256':json.loads((P/'RELEASE_QA_precision_v1.json').read_text())['pdf_sha256']}
(P/'PRECISION_REVISION.json').write_text(json.dumps(reason,indent=2))
freeze={'created_utc':datetime.now(timezone.utc).isoformat(),'scope':'Presentation precision only; no scientific acceptance change; frozen before revised rendering','files':{name:sha(P/name) for name in ['NOTE_SPEC.json','verify_note.py','NOTE_CHECK_FREEZE.json','verify_note_v2.py','PRECISION_REVISION.json']}}
(P/'NOTE_CHECK_FREEZE_V2.json').write_text(json.dumps(freeze,indent=2));print(json.dumps(freeze,indent=2))
