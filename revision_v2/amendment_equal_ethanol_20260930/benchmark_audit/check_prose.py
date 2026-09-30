"""Verify human-readable numerical claims against this lane's checked evidence."""
from pathlib import Path
import hashlib,json
P=Path(__file__).resolve().parent
d=json.loads((P/'findings_evidence.json').read_text())
s=(P/'findings_for_note.txt').read_text()
checks=[]
def add(name,b): checks.append({'name':name,'pass':bool(b)})
add('source and arithmetic pass', d['status']=='PASS' and not d['issues'])
for row in d['integration_rule']:
    add(row['case']+' integration difference text',f"{row['difference_pct_conventional']:.2f}%" in s)
for row in d['mesh_sensitivity']:
    if row['case'].startswith('CS2'):
        add(row['case']+' mesh difference and timing',f"{row['max_H2_pct_nominal']:.2f}%" in s and str(row['at_display_min']) in s)
healthy=[r for r in d['negative_controls'] if r['active'] and r['true_h']=='H']
counts=[r['non_nominal_followup_commands'] for r in healthy]
add('healthy range',f'{min(counts)}-{max(counts)}' in s)
active=[r for r in d['negative_controls'] if r['active']]
add('all M1 shortfall changes below stated bound',all(abs(r['H2_shortfall_difference_vs_same_pulse_mmol'])<.00001 for r in active if r['mode']==1))
add('all M2 shortfall changes exactly zero',all(r['H2_shortfall_difference_vs_same_pulse_mmol']==0 for r in active if r['mode']==2))
row=next(r for r in active if r['case_id']=='m1_S_d05_r0' and r['set']=='S1')
add('M1 meterbias S1 action count',str(row['non_nominal_followup_commands']) in s)
add('M1 meterbias S1 extra ethanol',f"{row['extra_actual_ethanol_vs_same_pulse_mmol']:.5f}" in s)
add('native qualification', 'Fine-grid reset logs are incomplete' in s)
add('no numerical PID effect size','20.12' not in s)
add('roundtrip distinction',all(r['episodes']==1000 for r in active))
out={'pass':all(r['pass'] for r in checks),'checks':checks,'files':{f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in [P/'findings_for_note.txt',P/'findings_evidence.json',P/'SOURCE_TRACE.txt']}}
(P/'PROSE_QA.json').write_text(json.dumps(out,indent=2),encoding='utf-8')
print(json.dumps(out,indent=2));raise SystemExit(not out['pass'])
