"""Six-page scientific note; original science is read-only and checked inputs gate release."""
from __future__ import annotations
import argparse, csv, hashlib, html, json
from datetime import datetime, timezone
from pathlib import Path

import fitz
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, Table, TableStyle

HERE=Path(__file__).resolve().parent
AMEND=HERE.parent
ROOT=AMEND.parent
OUT=AMEND/'output'/'pdf'
W,H=A4
L=43
PW=W-2*L
INK=colors.HexColor('#263D4A')
NAVY=colors.HexColor('#153A4B')
TEAL=colors.HexColor('#087D80')
PALE=colors.HexColor('#EDF5F5')
GREY=colors.HexColor('#F0F3F5')
MUTED=colors.HexColor('#5A6C77')
CENTRAL=['m1_C_d05_r1','m1_M_d05_r1','m2_C_d05_r1','m2_M_d05_r1']

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def js(p): return json.loads(Path(p).read_text(encoding='utf-8'))
def rows(p):
    with Path(p).open(encoding='utf-8-sig',newline='') as f: return list(csv.DictReader(f))
def esc(s): return html.escape(str(s).replace('\u2013','-').replace('\u2014',' - ').replace('\u2212','-'))
def f(r,k): return float(r[k])
def flag(x): return x in [True,'True','true','1',1]
def pct(x): return f'{100*x:.1f}%'
def label(s):
    return {'m1_H':'M1 healthy','m2_H':'M2 healthy','m1_S_d05_r0':'M1 meter bias','m2_S_d05_r0':'M2 meter bias'}.get(s,s.replace('m1_','M1 ').replace('m2_','M2 ').replace('_d05_r1',''))

class Note:
    def __init__(self):
        fontdir=Path('C:/Windows/Fonts')
        for family,file in [('Body','segoeui.ttf'),('Bold','segoeuib.ttf'),('Italic','segoeuii.ttf')]:
            pdfmetrics.registerFont(TTFont(family,str(fontdir/file)))
        pdfmetrics.registerFontFamily('Body',normal='Body',bold='Bold',italic='Italic',boldItalic='Bold')
        self.styles={
            'body':ParagraphStyle('body',fontName='Body',fontSize=10.2,leading=14.3,textColor=INK),
            'small':ParagraphStyle('small',fontName='Body',fontSize=8.6,leading=11.7,textColor=MUTED),
            'h':ParagraphStyle('h',fontName='Bold',fontSize=12.4,leading=16,textColor=TEAL),
            'title':ParagraphStyle('title',fontName='Bold',fontSize=24,leading=29,textColor=NAVY),
            'cell':ParagraphStyle('cell',fontName='Body',fontSize=8.7,leading=11.7,textColor=INK),
            'head':ParagraphStyle('head',fontName='Bold',fontSize=8.7,leading=11.7,textColor=colors.white),
        }
        self.diag=rows(ROOT/'results/diagnosis_summary.csv')
        self.inputs={}
        old=js(ROOT/'report/document_input_manifest.json')
        for rel in ['results/diagnosis_summary.csv','results/policy_paired_differences.csv','checks/final_check.json','protocol.json']:
            digest=sha(ROOT/rel)
            assert old['inputs'][rel]==digest, f'Original checked input changed: {rel}'
            self.inputs[str(ROOT/rel)]=digest
        gate=js(ROOT/'checks/final_check.json')
        assert gate['complete'] and gate['computational_pass'] and gate['qualified']
        self.trade=js(HERE/'amendment_table.json')
        self.lit=js(HERE/'literature_status.json')
        assert self.trade['checked'] is True
        for source,digest in self.trade['source_hashes'].items():
            path=AMEND/source
            assert sha(path)==digest, f'Stale amendment source: {source}'
            self.inputs[str(path)]=digest
        check=js(AMEND/self.trade['check_path'])
        assert check.get('pass') is True and check.get('complete') is True and not check.get('issues'), 'Amendment independent check must complete and PASS'
        assert check['parent_qualified_check_sha256']==sha(ROOT/'checks/final_check.json')
        assert check['parent_exact_export_gate_pass'] is False and check['qualified_parent_resolution_retained'] is True
        assert self.lit['status']=='full_text_reviewed' and self.lit['full_paper_read_completed'] is True
        for source,digest in self.lit.get('source_hashes',{}).items():
            path=AMEND/source
            assert sha(path)==digest, f'Stale literature note: {source}'
            self.inputs[str(path)]=digest
        for file in ['amendment_table.json','literature_status.json']:
            self.inputs[str(HERE/file)]=sha(HERE/file)
        self.claims=[{'kind':'feed_only_contrasts','ledger':self.trade['claim_ledger']}]
        OUT.mkdir(parents=True,exist_ok=True)
        self.pdf=OUT/'SSMR_SCIENTIFIC_NOTE_6_PAGES.pdf'
        self.c=canvas.Canvas(str(self.pdf),pagesize=A4)
        self.c.setTitle('SSMR diagnosis: calibrated simulation and feed-only comparison')
        self.c.setAuthor('Computational evidence note')
        self.page=0

    def p(self,text,style='body',gap=9):
        p=Paragraph(text,self.styles[style]); _,height=p.wrap(PW,1000)
        if self.y-height<52: raise RuntimeError(f'Page {self.page} overflow at {text[:70]}')
        p.drawOn(self.c,L,self.y-height); self.y-=height+gap
    def h(self,text): self.p(esc(text),'h',6)
    def table(self,headers,data,widths):
        cells=[[Paragraph(esc(v),self.styles['head' if i==0 else 'cell']) for v in row] for i,row in enumerate([headers]+data)]
        t=Table(cells,colWidths=widths,hAlign='LEFT')
        t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),NAVY),('ROWBACKGROUNDS',(0,1),(-1,-1),[PALE,colors.white]),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),6),('RIGHTPADDING',(0,0),(-1,-1),6),('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),7),('LINEBELOW',(0,-1),(-1,-1),.4,colors.HexColor('#D9E3E7'))]))
        _,height=t.wrap(PW,1000)
        if self.y-height<52: raise RuntimeError(f'Page {self.page} table overflow')
        t.drawOn(self.c,L,self.y-height); self.y-=height+12
    def start(self,title):
        if self.page: self.c.showPage()
        self.page+=1; self.y=H-73
        self.c.setFont('Bold',8); self.c.setFillColor(TEAL)
        self.c.drawString(L,H-36,'SSMR / SCIENTIFIC NOTE / 30 SEPTEMBER 2026')
        self.c.setStrokeColor(colors.HexColor('#D7E3E7')); self.c.line(L,H-46,W-L,H-46)
        self.c.setFont('Body',7.5); self.c.setFillColor(MUTED)
        self.c.drawString(L,29,'Simulation evidence | Qualified computational verification | No plant validation')
        self.c.drawRightString(W-L,29,f'{self.page} / 6')
        self.p(esc(title),'title',15)
    def row(self,case,active,setname='S4'):
        result=[r for r in self.diag if r['case_id']==case and flag(r['active'])==active and r['set']==setname and r['group']=='covered_grid']
        assert len(result)==1
        return result[0]

    def content(self):
        self.start('When does a feed move help diagnose deterioration?')
        k=[r for r in self.diag if r['group']=='kinetic_mismatch']
        assert k and all(f(r,'correct_singleton')==0 and f(r,'true_rejected')==f(r,'n') for r in k)
        self.claims.append({'kind':'kinetic_failure','records':[{field:r[field] for field in ['case_id','active','set','n','correct_singleton','true_rejected']} for r in k]})
        self.p('<b>The selected kinetic-mismatch tests failed completely: correct diagnosis was 0% and the true cause was rejected in 100% of episodes.</b> Under the declared nominal model, active feed acquisition improved diagnosis in selected central catalyst and membrane cases. The result is a bounded simulation finding, not evidence of reliable plant diagnosis.')
        self.h('The scientific question')
        self.p('Can a small, scheduled ethanol-feed increase distinguish catalyst deterioration, membrane deterioration, feed-delivery loss and a hydrogen-meter offset, when measurements are noisy, delayed and correlated? If a diagnosis changes the later feed command, what happens to hydrogen shortfall and ethanol use?')
        self.h('Direct takeaway')
        self.p('The usefulness depends strongly on the cause and sensor set. All-channel central results improve with the feed move, but hydrogen-only diagnosis can remain almost uninformative for catalyst loss. Nominal calibration does not protect against the tested kinetic and observation shifts.')
        self.p(esc(self.trade['takeaway']))
        self.h('What the new comparator adds')
        self.p('The amendment is a <b>comparison of the later feed action after the same pulse</b>. It holds the acquisition pulse and its end time fixed, then removes the diagnosis-based follow-up command. Separate records for pulses ending at minute 16 or 21 also document blind schedules.')
        self.p('The diagnostic method, thresholds, original trajectories and stochastic records are unchanged. This outcome-known amendment was specified after the original results were inspected; it is not retroactive preregistration or a new independent noise experiment.','small')

        self.start('Method: one frozen diagnostic experiment')
        self.h('Dynamic truth and scheduled acquisition')
        self.p('The staged public ethanol membrane-reformer equations generate continuous trajectories in two operating modes [1]. The physical state is preconditioned at the initial scenario health. Catalyst, membrane and feed-delivery health evolve inside the ODE; a meter offset changes the measurement only. The baseline runs to minute 10. Active acquisition raises ethanol by 0.0003 mol/min; passive acquisition retains baseline feed. Decisions occur at minutes 16 and 21. The ODE uses BDF, 50 axial points, relative tolerance 10<super>-6</super>, absolute tolerance 10<super>-8</super>, and maximum step 0.1 min.')
        self.h('Observations and candidate scores')
        self.p('S1 uses hydrogen rate; S3 adds outlet temperature and retentate flow; S4 adds four gas fractions. Measurements are usable only after their declared delays. The model includes within-instrument serial correlation, record-level uniform bias and shared-sample covariance; nominal instruments are independent. These errors and delays are assumed, not measured instrument specifications. Every candidate is fitted to the same observed window means using the minimum joint Mahalanobis score over a finite bank of evolving quasi-steady templates.')
        self.h('Calibration and held-out decisions')
        self.p('Each covered truth stratum supplies 499 independent calibration episodes. The score maximum across both looks is calibrated by the rank ceil((n + 1)(1 - 0.05)); a cause threshold is the largest included stratum threshold. Rejected causes cannot re-enter. A singleton stops the procedure; otherwise acquisition continues to minute 21, yielding a singleton, INCONCLUSIVE or MODEL_INCOMPATIBLE. Evaluation uses 1000 episodes per fixed cell, separate from calibration. The rank protection is marginal over calibration/test draws for included strata under the assumed observation law [2,3].')
        self.h('Commands, costs and the added control comparison')
        self.p('The existing plug-in policy chooses bounded feed from fitted retained paths. Physical accounts integrate true hydrogen shortfall and delivered ethanol over the common 0-31 min horizon, including the pulse. The amendment adds 18 continuations: nine prior policy cases, each with the active pulse ending exogenously at 16 or 21 min and nominal feed thereafter. Original active trial decisions select the matching pulse-end record for the conditional comparison; no recalibration or new stochastic trial is used.')

        self.start('Central diagnosis results')
        self.p('Four prespecified central cases, S4 (all seven channels). Each entry is a count out of 1000 observation episodes. These are separate fixed scenarios, not pooled population rates. C means catalyst and M membrane deterioration.','small')
        data=[]
        for case in CENTRAL:
            p,a=self.row(case,False),self.row(case,True)
            record=[label(case),str(int(f(p,'correct_singleton'))),str(int(f(a,'correct_singleton'))),str(int(f(a,'wrong_singleton'))),str(int(f(a,'inconclusive')+f(a,'incompatible')))]
            data.append(record)
            self.claims.append({'kind':'central_S4','case':case,'displayed':record})
        self.table(['Case','Passive correct','Active correct','Active wrong','Active no call'],data,[91,105,104,103,PW-403])
        self.p('All four anchors are a nominal-map 5% hydrogen loss at minute 10, not measured dynamic losses. Catalyst decay is 0.005/min and membrane decay is 0.003/min. No call combines inconclusive and model-incompatible outcomes; the underlying records keep them separate.','small')
        c0,c1=self.row(CENTRAL[0],False,'S1'),self.row(CENTRAL[0],True,'S1')
        m0,m1=self.row(CENTRAL[1],False,'S1'),self.row(CENTRAL[1],True,'S1')
        assert [int(f(x,'correct_singleton')) for x in [m0,m1,c0,c1]]==[141,920,1,13]
        self.claims.append({'kind':'Mode1_central_S1','membrane_passive_active':[141,920],'catalyst_passive_active':[1,13],'denominator_per_cell':1000})
        self.h('A hydrogen-only result is cause-specific')
        self.p('For the <b>Mode 1 central 5% cases only</b>, S1 correct diagnoses increased from <b>141 to 920 out of 1000</b> for membrane deterioration, but only from <b>1 to 13 out of 1000</b> for catalyst deterioration. This sentence does not describe Mode 2, all severities or every fault. A feed pulse is not sufficient to make the single hydrogen channel broadly diagnostic.')
        self.h('Interpretation')
        self.p('Wrong singleton calls, rejection of the true cause and failure to reach a call are different events. A small wrong-call rate can coexist with frequent abstention. Diagnostic time is conditional on reaching a singleton; an inconclusive record is not assigned a successful diagnosis at the final look.')
        self.p('The healthy state also overlaps the zero-fault limits of multiple candidate families, so unique healthy diagnosis is structurally difficult. The calibrated threshold controls a stated rejection event, not guaranteed resolution of the cause.','small')

        self.start('Stress failures delimit the result')
        self.p('The nominal thresholds are retained. Each row summarizes selected fixed stress cells; maxima may come from different cells. The interval is the pointwise 95% binomial interval for the maximum-rejection cell, not a simultaneous guarantee.','small')
        data=[]
        groups=['kinetic_mismatch','double_noise','drifting_bias','gain_error','strong_correlation','heldout_parameters','faster_deterioration','half_noise']
        for group in groups:
            rr=[r for r in self.diag if r['group']==group and flag(r['supported_label'])]
            worst=max(rr,key=lambda r:f(r,'true_rejected_rate'))
            vals=[f(r,'correct_singleton_rate') for r in rr]
            record=[group.replace('_',' '),pct(min(vals))+'-'+pct(max(vals)),pct(f(worst,'true_rejected_rate')),pct(f(worst,'true_rejected_ci_lo'))+'-'+pct(f(worst,'true_rejected_ci_hi')),pct(max(f(r,'wrong_singleton_rate') for r in rr))]
            data.append(record); self.claims.append({'kind':'stress','group':group,'displayed':record,'rejection_cell':{x:worst[x] for x in ['case_id','active','set']}})
        self.table(['Stress','Correct-call range','Max true-cause rejection','Its 95% interval','Max wrong call'],data,[117,95,102,111,PW-425])
        self.h('Reproducibility does not remove these failures')
        self.p('The kinetic tests can reject every candidate rather than force a wrong label. That protects against a false singleton in those records while leaving the method unusable for diagnosis there. Observation shifts can instead produce both high rejection and wrong calls. Combined faults and excluded feed-loss cases lie outside the supported cause family; no singleton can establish a correct supported label for them.')
        self.p('These selected stresses are not an exhaustive robustness study. The nominal finite-grid calibration does not transfer automatically to unseen kinetics, continuous severity, arbitrary fixed bias, cross-instrument dependence or real aging.','small')

        self.start('Physical trade-offs with the feed-only comparator')
        self.p('Four central cases, S4; mean amounts in mmol over 0-31 min. Each difference is diagnostic action minus the feed-only continuation with the same pulse end. Negative hydrogen shortfall means less unmet demand; extra ethanol remains a separate cost. The physical policy comparison uses nominal observation-law records; the stress results assess diagnosis only.','small')
        self.table(['Case','Feed-only H2 shortfall','Diagnostic H2 shortfall','H2 shortfall difference','Actual ethanol difference'],self.trade['table_rows'],[84,109,109,105,PW-407])
        self.p(esc(self.trade['interpretation']))
        self.h('Healthy and meter-bias counterexamples')
        self.p(esc(self.trade['counterexamples']))
        self.h('Match the pulse, then compare the later command')
        self.p('At each original active record\'s 16- or 21-minute stop, the comparator starts from the same physical state and returns to nominal feed until minute 31. Only the later feed command changes. Pulse durations come from the diagnostic runs, so this does not test a wholly diagnosis-free stopping policy or price diagnostic information.')
        self.p('Both fixed-end blind schedules are published separately in outputs/feed_only_arm_costs.csv. All nine policy cases and all three sensor sets are checked in the amendment tables; this display shows four central S4 cases. No price, maintenance benefit or scalar economic objective turns these physical vectors into a net-benefit claim.','small')

        self.start('Limits, provenance and scientific context')
        self.p('The main limit is model dependence: the selected kinetic-mismatch cases fail completely. Noise, bias and delays are simulation assumptions; their joint behavior has not been measured on a rig. The candidate bank is finite, the policy fits one path per retained cause, and the study establishes neither continuous-domain validity nor uniform action safety.')
        self.p('The dynamic calculation is Python-based; prior native MATLAB reproduction is historical evidence. The original exact exported-start-state byte gate remains failed. A separate frozen forensic replay established exact intended solver input, exact replay of the affected saved arrays, and unchanged reported physical quantities. Review used another AI agent from the same model family. This is qualified internal computational verification, not an all-frozen-gates-pass release, experimental validation or external journal review.','small')
        self.h('Relation to prior work')
        self.p('Active input design for fault diagnosis already exists [4]. '+esc(self.lit['comparison_sentence']))
        self.p(esc(self.lit['access_statement']),'small')
        self.h('Concise references')
        refs=[
            '[1] Arcila-Osorio M et al. A benchmark simulator for advanced control of ethanol steam reforming. Renewable Energy 256 (2026) 124743. doi:10.1016/j.renene.2025.124743.',
            '[2] Dufour JM. Monte Carlo tests with nuisance parameters. Journal of Econometrics 133 (2006) 443-477. doi:10.1016/j.jeconom.2005.06.007.',
            '[3] Morris TP, White IR, Crowther MJ. Using simulation studies to evaluate statistical methods. Statistics in Medicine 38 (2019) 2074-2102. doi:10.1002/sim.8086.',
            '[4] Scott JK et al. Input design for guaranteed fault diagnosis using zonotopes. Automatica 50 (2014) 1580-1589. doi:10.1016/j.automatica.2014.03.016.',
            '[5] '+self.lit['reference'],
        ]
        for r in refs: self.p(esc(r),'small',6)
        self.p('Reproducibility: original checked diagnosis/policy CSVs; amendment protocol, fixed-end blind costs and conditional contrasts; independent checks; this note\'s input hashes and claim ledger. No original method, threshold or stochastic record was retuned.','small')

    def save(self):
        assert self.page==6
        self.c.save()
        doc=fitz.open(self.pdf)
        assert len(doc)==6
        qa=HERE/'qa'; qa.mkdir(exist_ok=True)
        texts=[]; bounds=[]
        for i,page in enumerate(doc):
            page.get_pixmap(matrix=fitz.Matrix(1.6,1.6),alpha=False).save(qa/f'page-{i+1}.png')
            texts.append(f'--- PAGE {i+1} ---\n'+page.get_text())
            for b in page.get_text('dict')['blocks']:
                for line in b.get('lines',[]):
                    for s in line['spans']:
                        if s['bbox'][0]<0 or s['bbox'][1]<0 or s['bbox'][2]>W+.1 or s['bbox'][3]>H+.1: bounds.append({'page':i+1,'span':s})
        assert not bounds, bounds
        (qa/'extracted_text.txt').write_text('\n\n'.join(texts),encoding='utf-8')
        manifest={'generated_utc':datetime.now(timezone.utc).isoformat(),'pages':6,'original_qualified':True,'amendment_checked':True,'full_paper_read_completed':True,'inputs':self.inputs,'pdf_sha256':sha(self.pdf),'generator_sha256':sha(__file__),'claims':self.claims,'bounds_issues':bounds,'visual_review':'pending'}
        (HERE/'note_input_manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
        print(json.dumps({'pdf':str(self.pdf),'pages':len(doc),'pdf_sha256':sha(self.pdf),'bounds_issues':bounds}))

if __name__=='__main__':
    n=Note(); n.content(); n.save()
