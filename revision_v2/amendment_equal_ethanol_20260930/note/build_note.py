"""Local revised six-page note. All prior artifacts remain read-only."""
from pathlib import Path
from datetime import datetime,timezone
import json,hashlib,html
import pandas as pd
import fitz
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph,Table,TableStyle

HERE=Path(__file__).resolve().parent; E=HERE.parent; ROOT=E.parent
OLD=ROOT/'amendment_feed_only_20260930'; W,H=A4; L=43; PW=W-2*L
CENTRAL=['m1_C_d05_r1','m1_M_d05_r1','m2_C_d05_r1','m2_M_d05_r1']
CONTROLS=['m1_H','m2_H','m1_S_d05_r0','m2_S_d05_r0']
GROUPS=['kinetic_mismatch','double_noise','drifting_bias','gain_error','strong_correlation','heldout_parameters','faster_deterioration','half_noise']
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def esc(x):return html.escape(str(x))
def label(c):return c[:2].upper()+' '+c[3]
def pct(x):return f'{100*x:.1f}%'
def cost(x):return f'{(0. if abs(x)<.000005 else x):.5f}'
def csv(p):return pd.read_csv(p,float_precision='round_trip')

class Note:
    def __init__(self):
        for name,file in [('Body','segoeui.ttf'),('Bold','segoeuib.ttf'),('Italic','segoeuii.ttf')]:pdfmetrics.registerFont(TTFont(name,'C:/Windows/Fonts/'+file))
        pdfmetrics.registerFontFamily('Body',normal='Body',bold='Bold',italic='Italic',boldItalic='Bold')
        self.styles={
            'body':ParagraphStyle('body',fontName='Body',fontSize=10,leading=14,textColor=colors.black),
            'small':ParagraphStyle('small',fontName='Body',fontSize=8.4,leading=11.4,textColor=colors.HexColor('#333333')),
            'h':ParagraphStyle('h',fontName='Bold',fontSize=12,leading=15.5,textColor=colors.black),
            'title':ParagraphStyle('title',fontName='Bold',fontSize=22,leading=27,textColor=colors.black),
            'cell':ParagraphStyle('cell',fontName='Body',fontSize=8.2,leading=10.5),
            'head':ParagraphStyle('head',fontName='Bold',fontSize=8.2,leading=10.5,textColor=colors.white)}
        self.sources=[ROOT/'results/diagnosis_summary.csv',ROOT/'results/policy_trials.csv',ROOT/'protocol.json',ROOT/'checks/final_check.json',OLD/'outputs/paired_summary.csv',OLD/'outputs/paired_trials.csv',OLD/'checks/verification.json',OLD/'literature/fulltext_access_manifest.json',OLD/'literature/fulltext_review.txt',OLD/'literature/prior_work_trace.txt',E/'outputs/paired_summary.csv',E/'outputs/paired_trials.csv',E/'checks/verification.json',E/'protocol.json',E/'benchmark_audit/findings_evidence.json',E/'benchmark_audit/findings_for_note.txt',HERE/'figure_coordinates.csv',HERE/'tradeoff.png',HERE/'NOTE_SPEC.json']
        self.sources.append(ROOT/'revision_model.py')
        self.inputs={str(p):sha(p) for p in self.sources}
        self.d=csv(self.sources[0]);self.old=csv(OLD/'outputs/paired_summary.csv');self.eq=csv(E/'outputs/paired_summary.csv')
        gate=read(E/'checks/verification.json');assert gate['pass'] and not gate['issues']
        assert read(E/'benchmark_audit/findings_evidence.json')['status']=='PASS'
        assert read(OLD/'literature/fulltext_access_manifest.json')['status']=='FULL_TEXT_REVIEWED'
        assert len(self.eq)==4 and set(self.eq.case_id)==set(CENTRAL)
        self.claims=[];self.page=0
        self.pdf=E/'output/pdf/SSMR_SCIENTIFIC_NOTE_V3_LOCAL_REVIEW.pdf';self.pdf.parent.mkdir(parents=True,exist_ok=True)
        self.c=canvas.Canvas(str(self.pdf),pagesize=A4);self.c.setTitle('Does diagnosis help meet hydrogen demand?');self.c.setAuthor('Local computational research draft')
    def p(self,text,style='body',gap=8):
        p=Paragraph(text,self.styles[style]);_,hh=p.wrap(PW,1000)
        if self.y-hh<53:raise RuntimeError(f'Page {self.page} overflow: {text[:70]}')
        p.drawOn(self.c,L,self.y-hh);self.y-=hh+gap
    def h(self,text):self.p(esc(text),'h',5)
    def table(self,heads,rows,widths):
        data=[[Paragraph(esc(x),self.styles['head' if i==0 else 'cell']) for x in rr] for i,rr in enumerate([heads]+rows)]
        t=Table(data,colWidths=widths);t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.black),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.HexColor('#eeeeee'),colors.white]),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),5),('RIGHTPADDING',(0,0),(-1,-1),5),('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6)]))
        _,hh=t.wrap(PW,1000)
        if self.y-hh<53:raise RuntimeError('Table overflow '+str(self.page))
        t.drawOn(self.c,L,self.y-hh);self.y-=hh+10
    def start(self,title):
        if self.page:self.c.showPage()
        self.page+=1;self.y=H-73;self.c.setFillColor(colors.black);self.c.setFont('Bold',8)
        self.c.drawString(L,H-35,'SSMR / LOCAL REVIEW DRAFT / 30 SEPTEMBER 2026')
        self.c.setStrokeColor(colors.HexColor('#bbbbbb'));self.c.line(L,H-46,W-L,H-46)
        self.c.setFont('Body',7);self.c.drawString(L,29,'Simulation only | User rewrite and different-model review pending')
        self.c.drawRightString(W-L,29,f'{self.page} / 6');self.p(esc(title),'title',13)
    def diag(self,c,a,s='S4'):
        r=self.d[(self.d.case_id==c)&(self.d.active==a)&(self.d['set']==s)&(self.d['group']=='covered_grid')];assert len(r)==1;return r.iloc[0]
    def content(self):
        q=self.eq.set_index('case_id').loc[CENTRAL]
        delta=q.difference_H2_shortfall_mol_mean
        blind_wins=int((delta>0).sum());diag_wins=int((delta<0).sum())
        self.claims.append({'kind':'equal_signs','blind_less_shortfall':blind_wins,'diagnostic_less_shortfall':diag_wins,'n':4})
        if blind_wins==4:
            conclusion='At equal ethanol use, the blind constant-feed arm had slightly less calculated mean hydrogen shortfall in all four central cases. These tests do not show a mean hydrogen-shortfall advantage from diagnosis over this simple feed schedule.'
        elif diag_wins==4:
            conclusion='At equal ethanol use, the diagnostic sequence had less hydrogen shortfall in all four central cases. This supports the sequence against the tested constant-feed schedule; it does not show that diagnosis beats every blind policy.'
        else:
            conclusion=f'At equal ethanol use, the blind constant-feed arm had less hydrogen shortfall in {blind_wins} cases and the diagnostic sequence in {diag_wins}. The result depends on the case; there is no uniform production advantage.'
        self.start('Does diagnosis help meet hydrogen demand?')
        self.p('The question is practical: if hydrogen production falls, does identifying the cause help more than simply feeding more ethanol? This note separates diagnosis accuracy from the ability of the resulting feed command to meet hydrogen demand.')
        self.p('<b>'+conclusion+'</b>')
        self.p('A feed pulse improves cause identification in the nominal model, but that is a separate result. The diagnostic policy also acts unnecessarily on healthy plants, and all selected kinetic-mismatch cases reject the true cause. The useful outputs are a bounded simulation comparison and reproducible findings for the benchmark authors.')
        self.h('Findings on the benchmark code')
        self.p('<b>IAE depends on the integration convention.</b> The paper\'s Equation (13) takes the absolute value after averaging adjacent signed errors. Trapezoidal integration of absolute error gives a different answer when the error changes sign. State the formula, sample times and interval when comparing controllers; this difference does not imply a different plant response.')
        self.p('<b>The finer mesh changes the start-up case.</b> The saved np = 200 runs use a different grid and its own supplied initial state than np = 50. Their early trajectories therefore mix mesh and initialization effects. This is not a mesh-convergence test. Some fine-grid reset logs are missing, so the provenance qualification remains.')
        self.p('<b>The PID keeps state between calls.</b> The controller stores its integral and past error in persistent variables, while the top-level script clears ordinary variables. Back-to-back cases can inherit controller history. Reset the controller before each independent run (for example, clear control in MATLAB); no new MATLAB rerun is claimed here.')
        self.p('Source basis: pinned benchmark code and saved native CSV/state files; see the local evidence packet for exact paths and checks. The screenshot-derived PID effect size is deliberately not quoted.','small')

        self.start('Method: the diagnostic test stays fixed')
        self.h('Plant and measurements')
        self.p('The public distributed ethanol membrane-reformer model [1] supplies the simulated plant in two operating modes. Catalyst, membrane and feed-delivery losses evolve during the run; a meter offset affects only the reading. The diagnostic model uses evolving quasi-steady templates, so it differs from the full dynamic plant model.')
        self.p('S1 measures hydrogen flow. S3 adds outlet temperature and retentate flow. S4 adds four gas fractions. Within-channel serial noise, record-level bias and chromatograph delay are simulated assumptions; nominal sensor channels are independent. These are not measured properties of a named rig. The dynamic solver uses 50 axial points and the existing BDF settings without change.','small')
        self.h('Calibration, decisions and the original pulse')
        self.p('Each covered scenario has 499 separate calibration episodes and 1000 fresh evaluation episodes. The score uses both possible decision times. Its calibration rank is ceil((499 + 1)(1 - 0.05)); the largest included scenario threshold is used for each cause. This protects a specified rejection rate under the declared observation model, not the chance of obtaining a useful diagnosis [2,3].')
        self.p('At minute 10 the active sequence raises ethanol by 0.0003 mol/min. It decides at minute 16, or continues until minute 21. A single retained cause gives a diagnosis; several give no unique call; none gives a model-incompatible result. Every episode stays in the denominator. The existing feed-selection policy and thresholds are unchanged.')
        self.h('Two controls answer different questions')
        self.p('<b>Same pulse:</b> replay the same pulse end, then return to nominal feed. This measures the effect of the later command and its extra ethanol cost. Figure 1 shows every original case and sensor set.')
        self.p('<b>Same ethanol:</b> for each of the four central S4 cases, replace the complete minute 10-31 input sequence by one constant feed. Set its amount equal to that diagnostic episode\'s delivered ethanol over the same window. Before minute 10, both arms share the same saved state and history. The blind arm receives no measurements or diagnosis.')
        self.p('The new control uses the completed diagnostic run to assign a matching resource budget. It also changes when ethanol is fed and removes the pulse. This tests one equal-resource time schedule, not the isolated value of knowing the cause. The dated amendment and check were frozen before its new trajectories; earlier outcomes were already known. No new noise episodes or native MATLAB runs were added.','small')

        self.start('Diagnosis: useful centrally, fragile under stress')
        self.p('Central S4 cases: counts out of 1000 per case. C = catalyst loss; M = membrane loss. Each central anchor is a nominal-map 5% hydrogen drop at minute 10. No call includes both inconclusive and model-incompatible results.','small')
        rows=[]
        for c in CENTRAL:
            p,a=self.diag(c,False),self.diag(c,True)
            rr=[label(c),int(p.correct_singleton),int(a.correct_singleton),int(a.wrong_singleton),int(a.inconclusive+a.incompatible)]
            rows.append(rr);self.claims.append({'kind':'diagnosis','case_id':c,'displayed':rr})
        self.table(['Case','Passive correct','Pulse correct','Pulse wrong','Pulse no call'],rows,[65,115,115,105,PW-400])
        self.p('In the central Mode 1 hydrogen-only cases, correct membrane calls rise from 141 to 920 out of 1000, while catalyst calls rise only from 1 to 13. A useful pulse for one cause is not a general diagnosis guarantee.','small')
        self.h('Stress tests with the original thresholds')
        rows=[]
        for g in GROUPS:
            d=self.d[(self.d['group']==g)&self.d.supported_label];w=d.loc[d.true_rejected_rate.idxmax()]
            rr=[g.replace('_',' '),pct(d.correct_singleton_rate.min())+'-'+pct(d.correct_singleton_rate.max()),pct(w.true_rejected_rate),pct(w.true_rejected_ci_lo)+'-'+pct(w.true_rejected_ci_hi),pct(d.wrong_singleton_rate.max())]
            rows.append(rr);self.claims.append({'kind':'stress','group':g,'displayed':rr})
        self.table(['Stress','Correct range','Max true-cause rejection','Its 95% interval','Max wrong call'],rows,[116,91,98,112,PW-417])
        self.p('Rows summarize selected fixed cells; maxima need not come from the same cell. Intervals are pointwise binomial intervals, not a joint guarantee. All tested kinetic-mismatch episodes reject the true cause. Noise and bias shifts can also produce wrong calls. These stresses test diagnosis, not the safety of the resulting control actions.','small')

        self.start('Less unmet demand has a feed cost')
        self.p('Figure 1. Diagnostic action versus the same-pulse control. Each point is one case and sensor set, averaged over all its episodes. Moving right spends more ethanol; moving up avoids more hydrogen shortfall. Both axes show actual amounts over the full run.','small')
        self.c.drawImage(str(HERE/'tradeoff.png'),L,self.y-501,width=PW,height=501,mask='auto');self.y-=509
        self.p('M1/M2 = operating mode; C = catalyst, M = membrane, F = feed delivery, S = meter bias, H = healthy. Filled markers are Mode 1; open markers are Mode 2. Every one of the 27 original pairs is shown, including near-zero-benefit healthy and meter-bias cases.','small')
        self.p('This is a physical trade-off figure, not a monetary value of information. It cannot assign the gain to diagnosis when more feed is also used. The equal-ethanol comparison on the next page tests that narrower question.','small')

        self.start('Equal ethanol and unnecessary actions')
        self.p('Equal-resource test: all four central S4 cases, 1000 paired episodes each. Means in mmol over 0-31 min, including the common baseline. The resource is matched separately in every episode; the table displays its mean. Lower shortfall is better.','small')
        rows=[]
        for c in CENTRAL:
            r=q.loc[c]
            rr=[label(c),f'{1000*r.diagnostic_actual_ethanol_mol_mean:.4f}',f'{1000*r.diagnostic_H2_shortfall_mol_mean:.4f}',f'{1000*r.blind_H2_shortfall_mol_mean:.4f}',f'{1000*r.difference_H2_shortfall_mol_mean:+.6f}']
            rows.append(rr);self.claims.append({'kind':'equal','case_id':c,'displayed':rr})
        self.table(['Case','Matched ethanol','Diagnostic H2 shortfall','Blind H2 shortfall','Diagnostic minus blind'],rows,[59,100,119,116,PW-394])
        self.p(conclusion,'small')
        self.p('Amounts are rounded. The M1 membrane mean difference is +0.000027 mmol, not exactly zero. Every case contains episodes favoring each arm. No solver-refinement study tested these small mean differences. This is not robust blind-policy superiority.','small')
        self.p('The metric is unmet demand, not total hydrogen produced. In both membrane cases the diagnostic arm produces more total hydrogen but has a slightly larger shortfall: extra production at the wrong time need not meet demand.','small')
        self.h('All healthy and meter-bias action rates')
        self.p('Entries are non-nominal follow-up commands out of 1000 active episodes. Extra ethanol compares diagnostic action with the same-pulse control, not with the equal-resource control above. No healthy or meter-bias cell is omitted.','small')
        rows=[]
        for c in CONTROLS:
            part=self.old[self.old.case_id==c].set_index('set').loc[['S1','S3','S4']]
            costs=1000*part.difference_actual_ethanol_mol_mean
            rr=[label(c),*[f'{int(part.loc[s,"non_nominal_action_count"])}/1000' for s in ['S1','S3','S4']],cost(costs.min())+' to '+cost(costs.max())]
            rows.append(rr);self.claims.append({'kind':'control','case_id':c,'displayed':rr})
        self.table(['Case','S1 actions','S3 actions','S4 actions','Extra ethanol range (mmol)'],rows,[66,90,90,90,PW-336])
        self.p('<b>Healthy plants receive a non-nominal command in 49.8-52.7% of episodes.</b> For Mode 1 meter bias with S1, the policy acts in <b>947/1000</b> episodes and spends <b>1.02075 mmol</b> extra ethanol on average. The model has no physical hydrogen loss from that meter fault.')
        self.p('Mode 2 healthy and meter-bias cells have exactly zero shortfall improvement. Mode 1 changes are below 0.00001 mmol, not exactly zero. The healthy Mode 2 S4 cost is 0.5250 mmol. Cost ranges are rounded to five decimals. These results reveal unnecessary control actions.','small')

        self.start('Limits and relation to prior work')
        self.h('What can be defended')
        self.p('The feed pulse can improve nominal cause discrimination. The control comparisons measure physical outcomes against two specified feed schedules. They do not establish an optimal policy, a net economic return, or a unique benefit of diagnostic information. A better blind schedule may exist. Resource matching is retrospective; it does not give a real operator an unknown future budget.')
        self.h('What still fails or remains unverified')
        self.p('The selected kinetic-mismatch cases fail completely. Instrument noise, bias and delay are assumed. The healthy-plant action rate is unacceptable as evidence of safe deployment. Only a finite set of simulated faults and conditions is covered; no rig has validated this procedure.')
        self.p('The original exact exported-start-state byte check remains failed. A separate forensic check supported the intended solver input and unchanged physical quantities; that qualification has not been erased. Some fine-grid native reset logs are also missing. This amendment is Python-only. Same-model checks are complete; different-model review and the user\'s own rewrite remain pending. This is a local review draft, not an externally approved note.','small')
        self.h('One-sentence difference from Santra (2026)')
        self.p('Santra (2026) studies actuator-fault estimation and tracking recovery on a three-state reformer surrogate, whereas this note tests calibrated diagnosis of catalyst, membrane, feed and meter faults on distributed benchmark dynamics and compares the resulting feed sequence with blind controls [4].')
        self.p('The full Santra paper was read, including the implemented model in Section 6.1. Active input design for fault diagnosis is established work [5,6], and membrane-reformer tracking with ethanol-use objectives also predates this note [7]. No first-method or head-to-head superiority claim is made.','small')
        self.h('References')
        refs=[
          '[1] Arcila-Osorio et al. A benchmark simulator for advanced control of ethanol steam reforming. Renewable Energy 256 (2026) 124743. doi:10.1016/j.renene.2025.124743.',
          '[2] Dufour. Monte Carlo tests with nuisance parameters. Journal of Econometrics 133 (2006) 443-477. doi:10.1016/j.jeconom.2005.06.007.',
          '[3] Morris, White, Crowther. Using simulation studies to evaluate statistical methods. Statistics in Medicine 38 (2019) 2074-2102. doi:10.1002/sim.8086.',
          '[4] Santra. Koopman-PCE-based confidence-bounded fault diagnosis and recovery for hydrogen demand tracking in a membrane reactor. Computers & Chemical Engineering (2026) 109728. doi:10.1016/j.compchemeng.2026.109728.',
          '[5] Scott et al. Input design for guaranteed fault diagnosis using zonotopes. Automatica 50 (2014) 1580-1589. doi:10.1016/j.automatica.2014.03.016.',
          '[6] Raimondo et al. Closed-loop input design for guaranteed fault diagnosis using set-valued observers. Automatica 74 (2016) 107-117. doi:10.1016/j.automatica.2016.07.033.',
          '[7] Serra, Ocampo-Martinez, Li, Llorca. Model predictive control for ethanol steam reformers with membrane separation. International Journal of Hydrogen Energy 42 (2017) 1949-1961. doi:10.1016/j.ijhydene.2016.10.110.'
        ]
        for r in refs:self.p(esc(r),'small',4)
    def save(self):
        assert self.page==6;self.c.save();doc=fitz.open(self.pdf);assert len(doc)==6
        qa=HERE/'qa';qa.mkdir(exist_ok=True);texts=[];bounds=[]
        for n,page in enumerate(doc,1):
            page.get_pixmap(matrix=fitz.Matrix(1.6,1.6),alpha=False).save(qa/f'page-{n}.png');texts.append(f'--- PAGE {n} ---\n'+page.get_text())
            for b in page.get_text('dict')['blocks']:
                for ln in b.get('lines',[]):
                    for s in ln['spans']:
                        x0,y0,x1,y1=s['bbox']
                        if x0<35 or x1>W-35 or y0<12 or y1>H-12:bounds.append({'page':n,'text':s['text'],'bbox':s['bbox']})
        assert not bounds,bounds
        (qa/'extracted_text.txt').write_text('\n\n'.join(texts),encoding='utf-8')
        record={'pdf_sha256':sha(self.pdf),'generator_sha256':sha(__file__),'inputs':self.inputs,'claims':self.claims,'pages':6,'bounds_issues':bounds,'different_model_review':'pending','user_rewrite':'pending','created_utc':datetime.now(timezone.utc).isoformat()}
        (HERE/'note_input_manifest.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
        print(json.dumps({'pdf':str(self.pdf),'sha256':sha(self.pdf),'pages':6}))
if __name__=='__main__':
    n=Note();n.content();n.save()
