"""Independent final six-page note arithmetic, provenance and layout release checks."""
from pathlib import Path
import argparse,hashlib,json
from datetime import datetime,timezone
import pandas as pd
import numpy as np
import fitz
ROOT=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text())
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--visual-pages',required=True);args=ap.parse_args()
    issues=[]
    def need(ok,label):
        if not ok:issues.append(label)
    m=read(ROOT/'note/note_input_manifest.json');check=read(ROOT/'checks/verification.json')
    pdf=ROOT/'output/pdf/SSMR_SCIENTIFIC_NOTE_6_PAGES.pdf'
    need(check['pass'] and check['complete'] and not check['issues'],'Amendment computational verification')
    need(check['parent_exact_export_gate_pass'] is False and check['qualified_parent_resolution_retained'],'Original qualified failure retained')
    need(m['pdf_sha256']==sha(pdf),'Final PDF build hash')
    need(m['generator_sha256']==sha(ROOT/'note/build_note.py'),'Final generator hash')
    for p,h in m['inputs'].items():need(sha(p)==h,'Current document input/'+p)
    pages=fitz.open(pdf);need(len(pages)==6==m['pages'],'Exactly six pages')
    viewed=sorted({int(x) for x in args.visual_pages.split(',')})
    need(viewed==[1,2,3,4,5,6],'Every final page visually reviewed')
    text='\n'.join(p.get_text() for p in pages)
    need('\ufffd' not in text and '\x00' not in text,'No broken text glyphs')
    for number,p in enumerate(pages,1):
        need(len(p.get_text().strip())>150,'Nonempty page'+str(number))
        for b in p.get_text('dict')['blocks']:
            for line in b.get('lines',[]):
                for s in line['spans']:
                    x0,y0,x1,y1=s['bbox']
                    need(x0>=35 and x1<=p.rect.width-35 and y0>=12 and y1<=p.rect.height-12,'Page text bounds/'+str(number)+'/'+s['text'])
    need('kinetic' in pages[0].get_text().lower() and '100%' in pages[0].get_text(),'Kinetic failure foregrounded')
    need('same model' in text.lower() or 'same-model' in text.lower(),'Same-model checking disclosure')
    lit=read(ROOT/'note/literature_status.json')
    if lit['status']=='abstract_only':
        need('full text was not obtained or read' in text.lower(),'Uncompleted full-paper read explicit')
        need('provisional' in text.lower(),'Abstract comparison provisional')
    elif lit['status']=='full_text_reviewed':
        paper=read(ROOT/'literature/fulltext_access_manifest.json')
        need(paper['status']=='FULL_TEXT_REVIEWED' and paper['own_read_review_completed'],'Completed full-paper review record')
        need(sha(paper['pdf_path'])==paper['pdf_sha256'],'Exact supplied full-paper identity')
        need(paper['comparison_sentence']==lit['comparison_sentence'],'Full-paper comparison sentence')
        need('full text was not obtained or read' not in text.lower(),'Stale literature-access limitation removed')
    d=pd.read_csv(ROOT.parent/'results/diagnosis_summary.csv',float_precision='round_trip')
    s=pd.read_csv(ROOT/'outputs/paired_summary.csv',float_precision='round_trip')
    def cell(case,active,setname='S4'):
        part=d[(d.case_id==case)&(d.active==active)&(d['set']==setname)&(d['group']=='covered_grid')]
        assert len(part)==1
        return part.iloc[0]
    pct=lambda x:f'{100*x:.1f}%'
    checked=0
    for c in m['claims']:
        kind=c['kind']
        if kind=='feed_only_contrasts':
            for r in c['ledger']:
                if r.get('kind')=='central_S4_signs':
                    central=s[(s['set']=='S4')&s.case_id.isin(['m1_C_d05_r1','m1_M_d05_r1','m2_C_d05_r1','m2_M_d05_r1'])]
                    need(r['denominator']==len(central) and r['shortfall_reduced']==int((central.difference_H2_shortfall_mol_mean<0).sum()) and r['ethanol_increased']==int((central.difference_actual_ethanol_mol_mean>0).sum()),'Central S4 sign counts')
                    checked+=1;continue
                if r.get('kind')=='healthy_bias_S4_ranges_mmol':
                    controls=s[(s['set']=='S4')&s.case_id.isin(r['case_ids'])]
                    for key,col in [('ethanol','difference_actual_ethanol_mol_mean'),('shortfall','difference_H2_shortfall_mol_mean')]:
                        v=1000*controls[col]
                        need(np.allclose(r[key],[v.min(),v.max()],rtol=1e-13,atol=1e-14),'Control range/'+key)
                    checked+=1;continue
                if r.get('kind')=='negative_controls':
                    healthy=s[(s.case_id=='m2_H')&(s['set']=='S4')].iloc[0]
                    null=s[(s.case_id=='m2_S_d05_r0')&(s['set']=='S1')].iloc[0]
                    want={'m2_H_S4_H2_shortfall_difference_mmol':1000*healthy.difference_H2_shortfall_mol_mean,
                        'm2_H_S4_actual_ethanol_difference_mmol':1000*healthy.difference_actual_ethanol_mol_mean,
                        'm2_S_d05_r0_S1_non_nominal_action_count':int(null.non_nominal_action_count),
                        'm2_S_d05_r0_S1_H2_shortfall_difference_mmol':1000*null.difference_H2_shortfall_mol_mean}
                    for key,value in want.items():need(np.isclose(value,r[key],rtol=1e-13,atol=1e-14),'Control example/'+key)
                    checked+=1;continue
                row=s[(s.case_id==r['case_id'])&(s['set']==r['set'])].iloc[0]
                want=[1000*row[f] for f in ['feed_only_H2_shortfall_mol_mean','diagnostic_H2_shortfall_mol_mean','difference_H2_shortfall_mol_mean','difference_actual_ethanol_mol_mean']]
                need(np.allclose(want,r['columns_mmol'],rtol=1e-13,atol=1e-14),'Trade-off amounts/'+r['case_id'])
                need(int(row.trials)==r['trials']==1000,'Trade-off denominator/'+r['case_id'])
                checked+=1
        elif kind=='central_S4':
            p,a=cell(c['case'],False),cell(c['case'],True)
            want=[c['case'][:2].upper()+' '+c['case'][3],str(int(p.correct_singleton)),str(int(a.correct_singleton)),str(int(a.wrong_singleton)),str(int(a.inconclusive+a.incompatible))]
            need(want==c['displayed'],'Central table/'+c['case']);checked+=1
        elif kind=='Mode1_central_S1':
            for h,name in [('M','membrane_passive_active'),('C','catalyst_passive_active')]:
                want=[int(cell('m1_'+h+'_d05_r1',a,'S1').correct_singleton) for a in [False,True]]
                need(want==c[name],'Hydrogen-only finding/'+h)
            need(c['denominator_per_cell']==1000,'Hydrogen-only denominator');checked+=1
        elif kind=='kinetic_failure':
            part=d[d['group']=='kinetic_mismatch']
            need(len(c['records'])==len(part),'Kinetic failure coverage')
            need((part.correct_singleton==0).all() and (part.true_rejected==part.n).all(),'Kinetic headline');checked+=1
        elif kind=='stress':
            part=d[(d['group']==c['group'])&d.supported_label];worst=part.loc[part.true_rejected_rate.idxmax()]
            want=[c['group'].replace('_',' '),pct(part.correct_singleton_rate.min())+'-'+pct(part.correct_singleton_rate.max()),pct(worst.true_rejected_rate),pct(worst.true_rejected_ci_lo)+'-'+pct(worst.true_rejected_ci_hi),pct(part.wrong_singleton_rate.max())]
            need(want==c['displayed'],'Stress table/'+c['group']);checked+=1
        else:need(False,'Unrecognized claim ledger/'+kind)
    trade=read(ROOT/'note/amendment_table.json')
    control=s[(s.case_id=='m2_H')&(s['set']=='S4')].iloc[0]
    need(control.difference_H2_shortfall_mol_mean==0,'Mode2 healthy has zero shortfall change')
    need(np.isclose(1000*control.difference_actual_ethanol_mol_mean,.525,rtol=1e-12,atol=1e-14),'Mode2 healthy ethanol example')
    null=s[(s.case_id=='m2_S_d05_r0')&(s['set']=='S1')].iloc[0]
    need(null.non_nominal_action_count==0,'Meter-bias nominal-feed counterexample')
    need(null.difference_H2_shortfall_mol_min==0 and null.difference_H2_shortfall_mol_max==0,'Meter-bias zero-shortfall counterexample')
    # Earlier draft displayed ranges; current prose displays these two examples.
    # Range arithmetic remains independently checked in the claim ledger above.
    statements=[f'The Mode 2 healthy S4 case used {1000*control.difference_actual_ethanol_mol_mean:.4f} mmol more ethanol with exactly zero change in hydrogen shortfall.',
        'In the Mode 2 meter-bias S1 case, the diagnostic policy selected nominal feed for every record and did not change hydrogen shortfall.']
    normalized_pdf=' '.join(text.split())
    for statement in statements:
        need(statement in trade['counterexamples'],'Current control prose/'+statement)
        need(statement in normalized_pdf,'Current control statement printed/'+statement)
    result={'pass':not issues,'issues':issues,'pdf_sha256':sha(pdf),'amendment_check_sha256':sha(ROOT/'checks/verification.json'),
            'pages':len(pages),'visually_reviewed_pages':viewed,'numerical_claims_checked':checked,
            'full_paper_read_completed':lit['status']=='full_text_reviewed',
            'scope':'Release QA of six-page note; amendment computational pass; paper-access limitation remains explicit if unresolved.',
            'created_utc':datetime.now(timezone.utc).isoformat()}
    out=ROOT/'note/ROOT_RELEASE_QA.json';tmp=out.with_suffix('.tmp');tmp.write_text(json.dumps(result,indent=2)+'\n');tmp.replace(out)
    print(json.dumps(result,indent=2));return int(bool(issues))
if __name__=='__main__':raise SystemExit(main())
