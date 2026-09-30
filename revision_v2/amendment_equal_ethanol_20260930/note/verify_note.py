"""Independent document checks, specified before new experiment outcomes."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,json,hashlib
import pandas as pd
import numpy as np
import fitz
from PIL import Image
HERE=Path(__file__).resolve().parent; E=HERE.parent;ROOT=E.parent
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def js(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def csv(p):return pd.read_csv(p,float_precision='round_trip')
def label(c):return c[:2].upper()+' '+c[3]
def pct(x):return f'{100*x:.1f}%'
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--visual-pages',required=True);a=ap.parse_args();issues=[]
    def need(x,message):
        if not x:issues.append(message)
    m=js(HERE/'note_input_manifest.json');pdf=E/'output/pdf/SSMR_SCIENTIFIC_NOTE_V3_LOCAL_REVIEW.pdf'
    need(sha(pdf)==m['pdf_sha256'],'Current PDF identity');need(sha(HERE/'build_note.py')==m['generator_sha256'],'Current generator')
    for p,h in m['inputs'].items():need(sha(p)==h,'Current input '+p)
    freeze=js(HERE/'NOTE_CHECK_FREEZE.json')
    for rel,h in freeze['files'].items():need(sha(HERE/rel)==h,'Frozen release check '+rel)
    gate=js(E/'checks/verification.json');need(gate['pass'] and not gate['issues'],'Frozen scientific audit passed')
    need(gate['parent_exact_export_gate_pass'] is False and gate['qualified_parent_resolution_retained'],'Prior exact-export failure retained')
    need(js(E/'benchmark_audit/findings_evidence.json')['status']=='PASS','Code/source checks passed')
    doc=fitz.open(pdf);need(len(doc)==6,'Exactly six pages')
    viewed=sorted(set(int(x) for x in a.visual_pages.split(',')));need(viewed==list(range(1,7)),'Every page visually reviewed')
    text=' '.join(' '.join(p.get_text().split()) for p in doc)
    for term in ['different-model review','local review draft','retrospective','kinetic-mismatch','Equation (13)','persistent','np = 200','947/1000','1.0208','49.8-52.7%','0.5250','0.00001','141','920']:
        need(term.lower() in text.lower(),'Required content '+term)
    for term in ['Schedule-yoked','conditional action ablation','outcome-known amendment','right-hand sample','including the ethanol feed']:
        need(term.lower() not in text.lower(),'Stale or unsupported prose '+term)
    for n,p in enumerate(doc,1):
        need(len(p.get_text())>150,'Nonempty page '+str(n))
        for block in p.get_text('dict')['blocks']:
            for line in block.get('lines',[]):
                for span in line['spans']:
                    x0,y0,x1,y1=span['bbox'];need(x0>=35 and x1<=p.rect.width-35 and y0>=12 and y1<=p.rect.height-12,'Text bounds '+str(n)+' '+span['text'])
    need(len(doc[3].get_images())>=1,'Operator-unit figure on page 4')
    rgb=np.asarray(Image.open(HERE/'tradeoff.png').convert('RGB'));need(np.array_equal(rgb[:,:,0],rgb[:,:,1]) and np.array_equal(rgb[:,:,0],rgb[:,:,2]),'Monochrome figure')
    old=csv(ROOT/'amendment_feed_only_20260930/outputs/paired_summary.csv');coords=csv(HERE/'figure_coordinates.csv')
    merged=coords.merge(old,on=['case_id','set','trials'],validate='one_to_one');need(len(merged)==27,'All27 figure points')
    need(np.allclose(merged.extra_actual_ethanol_mmol,1000*merged.difference_actual_ethanol_mol_mean,rtol=1e-13,atol=1e-14),'Figure ethanol coordinates')
    need(np.allclose(merged.H2_shortfall_avoided_mmol,-1000*merged.difference_H2_shortfall_mol_mean,rtol=1e-13,atol=1e-14),'Figure shortfall coordinates')
    d=csv(ROOT/'results/diagnosis_summary.csv');eq=csv(E/'outputs/paired_summary.csv');checked=0
    def dr(c,active,s='S4'):
        p=d[(d.case_id==c)&(d.active==active)&(d['set']==s)&(d['group']=='covered_grid')];assert len(p)==1;return p.iloc[0]
    for claim in m['claims']:
        k=claim['kind'];rr=None
        if k=='equal_signs':
            need(claim['blind_less_shortfall']==int((eq.difference_H2_shortfall_mol_mean>0).sum()),'Blind win count')
            need(claim['diagnostic_less_shortfall']==int((eq.difference_H2_shortfall_mol_mean<0).sum()),'Diagnostic win count');need(claim['n']==len(eq)==4,'Fourcentral cases')
        elif k=='diagnosis':
            c=claim['case_id'];p,r=dr(c,False),dr(c,True);rr=[label(c),int(p.correct_singleton),int(r.correct_singleton),int(r.wrong_singleton),int(r.inconclusive+r.incompatible)]
        elif k=='stress':
            p=d[(d['group']==claim['group'])&d.supported_label];w=p.loc[p.true_rejected_rate.idxmax()]
            rr=[claim['group'].replace('_',' '),pct(p.correct_singleton_rate.min())+'-'+pct(p.correct_singleton_rate.max()),pct(w.true_rejected_rate),pct(w.true_rejected_ci_lo)+'-'+pct(w.true_rejected_ci_hi),pct(p.wrong_singleton_rate.max())]
        elif k=='equal':
            c=claim['case_id'];r=eq[eq.case_id==c].iloc[0];rr=[label(c),f'{1000*r.diagnostic_actual_ethanol_mol_mean:.4f}',f'{1000*r.diagnostic_H2_shortfall_mol_mean:.4f}',f'{1000*r.blind_H2_shortfall_mol_mean:.4f}',f'{1000*r.difference_H2_shortfall_mol_mean:+.4f}']
        elif k=='control':
            c=claim['case_id'];p=old[old.case_id==c].set_index('set').loc[['S1','S3','S4']];v=1000*p.difference_actual_ethanol_mol_mean
            rr=[label(c),*[f'{int(p.loc[s,"non_nominal_action_count"])}/1000' for s in ['S1','S3','S4']],f'{v.min():.4f} to {v.max():.4f}']
        else:need(False,'Unexpected claim kind '+k)
        if rr is not None:
            need(rr==claim['displayed'],'Recomputed row '+k+' '+str(claim.get('case_id',claim.get('group'))))
            for val in rr:need(str(val) in text,'Printed value '+str(val))
        checked+=1
    need(checked==21,'Complete claim ledger')
    need([int(dr('m1_M_d05_r1',v,'S1').correct_singleton) for v in [False,True]]==[141,920],'Hydrogen-only membrane statement')
    need([int(dr('m1_C_d05_r1',v,'S1').correct_singleton) for v in [False,True]]==[1,13],'Hydrogen-only catalyst statement')
    healthy=old[old.true_h=='H'];need(healthy.non_nominal_action_count.min()==498 and healthy.non_nominal_action_count.max()==527,'Healthy action range')
    bias=old[(old.case_id=='m1_S_d05_r0')&(old['set']=='S1')].iloc[0]
    need(bias.non_nominal_action_count==947 and np.isclose(1000*bias.difference_actual_ethanol_mol_mean,1.02075,atol=1e-12,rtol=1e-12),'Adverse meter-bias cell')
    ctrl=old[old.true_h.isin(['H','S'])];need((abs(1000*ctrl.difference_H2_shortfall_mol_mean)<.00001).all(),'Negligible shortfall bound')
    need((ctrl[ctrl['mode']==2].difference_H2_shortfall_mol_mean==0).all(),'Mode2 exact-zero statement')
    m2h=old[(old.case_id=='m2_H')&(old['set']=='S4')].iloc[0];need(np.isclose(1000*m2h.difference_actual_ethanol_mol_mean,.525,atol=1e-12,rtol=1e-12),'Healthy M2 ethanol')
    result={'pass':not issues,'issues':issues,'pages':len(doc),'visually_reviewed_pages':viewed,'table_claims_recomputed':checked,'figure_points_recomputed':len(merged),'pdf_sha256':sha(pdf),'freeze_sha256':sha(HERE/'NOTE_CHECK_FREEZE.json'),'different_model_review':'pending','user_rewrite':'pending','created_utc':datetime.now(timezone.utc).isoformat()}
    (HERE/'RELEASE_QA.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2));return bool(issues)
if __name__=='__main__':raise SystemExit(main())
