"""Derive presentation inputs only from a completed passing amendment check."""
from __future__ import annotations
import argparse, csv, hashlib, json
from pathlib import Path

HERE=Path(__file__).resolve().parent
AMEND=HERE.parent
CENTRAL=['m1_C_d05_r1','m1_M_d05_r1','m2_C_d05_r1','m2_M_d05_r1']
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def js(p): return json.loads(Path(p).read_text(encoding='utf-8'))
def write(p,data):
    temp=p.with_suffix('.tmp'); temp.write_text(json.dumps(data,indent=2),encoding='utf-8'); temp.replace(p)
def amount(row,key): return float(row[key])*1000
def num(x): return f'{x:+.4f}' if abs(x)>=.00005 else f'{x:+.3g}'

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--check',required=True)
    args=ap.parse_args(); cp=AMEND/args.check
    check=js(cp)
    assert check.get('pass') is True and check.get('complete') is True and not check.get('issues'), 'Independent amendment check must complete and pass first'
    assert check['parent_qualified_check_sha256']==sha(AMEND.parent/'checks/final_check.json')
    assert check['parent_exact_export_gate_pass'] is False and check['qualified_parent_resolution_retained'] is True
    for path,digest in check['bindings'].items(): assert sha(AMEND/path)==digest, f'Stale checker binding: {path}'
    summary=js(AMEND/'outputs/summary.json'); assert summary['complete']
    for path,digest in summary['files'].items(): assert sha(AMEND/path)==digest
    with (AMEND/'outputs/paired_summary.csv').open(newline='',encoding='utf-8-sig') as f: allrows=list(csv.DictReader(f))
    assert len(allrows)==27 and all(int(x['trials'])==1000 for x in allrows)
    s4={x['case_id']:x for x in allrows if x['set']=='S4'}; assert len(s4)==9
    table=[]; claims=[]
    for case in CENTRAL:
        r=s4[case]
        val=[amount(r,'feed_only_H2_shortfall_mol_mean'),amount(r,'diagnostic_H2_shortfall_mol_mean'),amount(r,'difference_H2_shortfall_mol_mean'),amount(r,'difference_actual_ethanol_mol_mean')]
        table.append([case[:2].upper()+' '+case[3],f'{val[0]:.4f}',f'{val[1]:.4f}',num(val[2]),num(val[3])])
        claims.append({'case_id':case,'set':'S4','trials':1000,'columns_mmol':val})
    central=[s4[x] for x in CENTRAL]
    less=sum(float(r['difference_H2_shortfall_mol_mean'])<0 for r in central)
    extra=sum(float(r['difference_actual_ethanol_mol_mean'])>0 for r in central)
    interpretation=(f'In these four central S4 cases, the downstream diagnostic command reduced mean hydrogen shortfall in {less} cases and used more actual ethanol in {extra}. These are paired physical outcome vectors, not a significance test or net economic benefit.')
    counter=[s4[x] for x in ['m1_H','m2_H','m1_S_d05_r0','m2_S_d05_r0']]
    de=[amount(r,'difference_actual_ethanol_mol_mean') for r in counter]
    ds=[amount(r,'difference_H2_shortfall_mol_mean') for r in counter]
    healthy=s4['m2_H']
    unchanged=next(x for x in allrows if x['case_id']=='m2_S_d05_r0' and x['set']=='S1')
    assert float(healthy['difference_H2_shortfall_mol_mean'])==0
    # Raw CSV differences include roundoff near 1e-16 mol; do not call them bitwise zero.
    assert int(unchanged['non_nominal_action_count'])==0
    assert float(unchanged['difference_H2_shortfall_mol_mean'])==0
    counterexamples=(f'The Mode 2 healthy S4 case used {amount(healthy,"difference_actual_ethanol_mol_mean"):.4f} mmol more ethanol with exactly zero change in hydrogen shortfall. In the Mode 2 meter-bias S1 case, the diagnostic policy selected nominal feed for every record and did not change hydrogen shortfall. These examples prevent favorable deterioration results from being mistaken for a universal benefit or cost.')
    takeaway=(f'With the feed pulse and its end time matched, the later diagnostic action reduced mean hydrogen shortfall in {less} of the four central all-channel cases and increased ethanol use in {extra}.')
    bind=dict(check['bindings'])
    bind.update({p:sha(AMEND/p) for p in ['amendment_protocol.json','AMENDMENT_FREEZE.json','outputs/summary.json','outputs/paired_summary.csv','outputs/feed_only_arm_costs.csv','outputs/paired_trials.csv',args.check]})
    claims.append({'kind':'central_S4_signs','shortfall_reduced':less,'ethanol_increased':extra,'denominator':4})
    claims.append({'kind':'healthy_bias_S4_ranges_mmol','case_ids':[r['case_id'] for r in counter],'ethanol':[min(de),max(de)],'shortfall':[min(ds),max(ds)]})
    claims.append({'kind':'negative_controls','m2_H_S4_H2_shortfall_difference_mmol':0,'m2_H_S4_actual_ethanol_difference_mmol':amount(healthy,'difference_actual_ethanol_mol_mean'),'m2_S_d05_r0_S1_non_nominal_action_count':0,'m2_S_d05_r0_S1_H2_shortfall_difference_mmol':0})
    write(HERE/'amendment_table.json',{'checked':True,'check_path':args.check,'source_hashes':bind,'table_rows':table,'interpretation':interpretation,'counterexamples':counterexamples,'takeaway':takeaway,'claim_ledger':claims,'scope':'Four central S4 cases displayed; all27 case/set groups checked.'})
    access=js(AMEND/'literature/fulltext_access_manifest.json')
    assert access['status']=='FULL_TEXT_REVIEWED' and access['own_read_review_completed'] is True
    assert access['pages_read']==list(range(1,access['page_count']+1))
    assert sha(access['pdf_path'])==access['pdf_sha256']
    assert sha(AMEND/'literature/fulltext_review.txt')==access['fulltext_review_sha256']
    litbind={p:sha(AMEND/p) for p in ['literature/fulltext_review.txt','literature/fulltext_access_manifest.json','literature/prior_work_trace.txt']}
    litbind[access['pdf_path']]=access['pdf_sha256']
    write(HERE/'literature_status.json',{'status':'full_text_reviewed','full_paper_read_completed':True,'comparison_sentence':access['comparison_sentence'],'access_statement':'Santra\'s full paper was read. Its implemented case is specified in Section 6.1, p.11; the estimator and recovery design are in Sections 5-5.2, pp.8-9. This establishes a difference in study scope, not superior performance. Its simulations were not independently reproduced.','reference':'Santra S. Koopman-PCE-based confidence-bounded fault diagnosis and recovery for hydrogen demand tracking in a membrane reactor. Computers & Chemical Engineering (2026), 109728. doi:10.1016/j.compchemeng.2026.109728.','source_hashes':litbind})
    print(json.dumps({'presentation_inputs':'ready','table_rows':table,'interpretation':interpretation,'counterexamples':counterexamples}))

if __name__=='__main__': main()
