"""Record completed visual review for the exact rendered PDF, without rerendering."""
import argparse, hashlib, json, re
from datetime import datetime, timezone
from pathlib import Path
import fitz

HERE=Path(__file__).resolve().parent
AMEND=HERE.parent
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,j):
    q=p.with_suffix('.tmp'); q.write_text(json.dumps(j,indent=2),encoding='utf-8'); q.replace(p)

ap=argparse.ArgumentParser(); ap.add_argument('--expected-sha256',required=True); args=ap.parse_args()
pdf=AMEND/'output/pdf/SSMR_SCIENTIFIC_NOTE_6_PAGES.pdf'
assert sha(pdf)==args.expected_sha256
manifest_path=HERE/'note_input_manifest.json'
m=json.loads(manifest_path.read_text(encoding='utf-8'))
assert m['pdf_sha256']==args.expected_sha256 and m['pages']==6 and m['full_paper_read_completed'] is True
assert not m['bounds_issues']
for p,digest in m['inputs'].items(): assert sha(p)==digest, p
d=fitz.open(pdf); assert len(d)==6
text=' '.join(' '.join(p.get_text().split()) for p in d)
for phrase in ['selected kinetic-mismatch tests failed completely','141 to 920 out of 1000','1 to 13 out of 1000','nominal observation-law records','Pulse durations come from the diagnostic runs','same model family','full paper was read','three-state reformer surrogate']:
    assert phrase in text, phrase
for stale in ['From the accessible abstract','full text was not obtained','full-paper comparison remains open','all paired physical differences were zero']:
    assert stale not in text, stale
assert '\ufffd' not in text and '\u25a0' not in text
page_hashes={f'qa/page-{i}.png':sha(HERE/f'qa/page-{i}.png') for i in range(1,7)}
m['visual_review']='all six latest rendered pages inspected; no visual defects identified'
m['visual_reviewed_pages']=list(range(1,7)); write(manifest_path,m)
qa={'schema':'ssmr.six-page-note-author-qa.v1','created_utc':datetime.now(timezone.utc).isoformat(),'pass':True,'issues':[],
    'pdf_sha256':sha(pdf),'pages':6,'manually_inspected_pages':list(range(1,7)),'render_scale':1.6,
    'manual_visual_findings':'No clipped/overlapping text, broken glyphs, table overflow or unreadable labels identified on the six current page images.',
    'text_checks_pass':True,'bounds_issues':[],'full_paper_read_completed':True,'original_qualified_status_retained':True,
    'input_manifest_sha256':sha(manifest_path),'extracted_text_sha256':sha(HERE/'qa/extracted_text.txt'),'page_images_sha256':page_hashes,
    'scope':'Author visual/text QA and input identity checks; independent scientific amendment check and root release QA are separate.'}
write(HERE/'FINAL_QA.json',qa)
print(json.dumps({'pass':True,'pages':6,'pdf_sha256':sha(pdf),'manifest_sha256':sha(manifest_path)}))
