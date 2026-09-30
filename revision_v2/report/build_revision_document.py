"""Build the scoped SSMR revision PDF from protocol and checked campaign outputs.

The default final mode refuses incomplete/unverified campaigns. --draft permits
layout engineering with explicit result placeholders; it never invents results.
Scientific evaluation and checking are deliberately outside this generator.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import fitz
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak,
    KeepTogether, Flowable,
)
from PIL import Image, ImageOps, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
NAVY = colors.HexColor('#133148')
TEAL = colors.HexColor('#007E83')
INK = colors.HexColor('#243848')
MUTED = colors.HexColor('#5D6D79')
PALE = colors.HexColor('#EAF4F4')
GREY = colors.HexColor('#F1F4F6')
AMBER = colors.HexColor('#A86419')
RED = colors.HexColor('#9A3341')
PAGE_W, PAGE_H = A4
WIDTH = PAGE_W - 100
SETS = ('S1', 'S3', 'S4')
HYP = {'C':'Catalyst deterioration', 'M':'Membrane deterioration',
       'F':'Feed-delivery loss', 'S':'Hydrogen-meter offset', 'H':'Healthy',
       'CM':'Combined catalyst/membrane'}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def clean(value):
    return str(value).replace('\u2011','-').replace('\u2013','-').replace('\u2014',' - ').replace('\u2212','-')


def esc(value):
    return html.escape(clean(value))


def load_json(path, optional=False):
    if optional and not path.exists():
        return None
    return json.loads(path.read_text(encoding='utf-8'))


def load_csv(path):
    if not path.exists():
        return []
    with path.open(encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(stream))


def num(row,key):
    value=row.get(key)
    return float(value) if value not in (None,'','nan','NaN') else None


def flag(value):
    if value in (True,'True','true','1',1): return True
    if value in (False,'False','false','0',0): return False
    raise ValueError('Not a boolean: '+repr(value))


def pct(value):
    return 'NA' if value is None else f'{100*value:.1f}%'


def rate_range(rows,key):
    vals=[num(r,key) for r in rows if num(r,key) is not None]
    return 'NA' if not vals else pct(min(vals))+' to '+pct(max(vals))


def styles():
    fontdir = Path('C:/Windows/Fonts')
    for face, name in [('Body','segoeui.ttf'), ('Bold','segoeuib.ttf'), ('Italic','segoeuii.ttf')]:
        pdfmetrics.registerFont(TTFont(face, str(fontdir/name)))
    pdfmetrics.registerFontFamily('Body', normal='Body', bold='Bold', italic='Italic', boldItalic='Bold')
    return {
        'body':ParagraphStyle('body',fontName='Body',fontSize=10.2,leading=14.5,textColor=INK,spaceAfter=9),
        'small':ParagraphStyle('small',fontName='Body',fontSize=8.7,leading=12,textColor=MUTED,spaceAfter=7),
        'table':ParagraphStyle('table',fontName='Body',fontSize=8.7,leading=11.6,textColor=INK),
        'th':ParagraphStyle('th',fontName='Bold',fontSize=8.6,leading=11.3,textColor=colors.white),
        'h1':ParagraphStyle('h1',fontName='Bold',fontSize=22,leading=27,textColor=NAVY,spaceAfter=15),
        'h2':ParagraphStyle('h2',fontName='Bold',fontSize=12,leading=16,textColor=TEAL,spaceBefore=6,spaceAfter=7),
        'kicker':ParagraphStyle('kicker',fontName='Bold',fontSize=9,leading=12,textColor=TEAL,spaceAfter=10),
        'title':ParagraphStyle('title',fontName='Bold',fontSize=30,leading=36,textColor=NAVY,spaceAfter=18),
        'subtitle':ParagraphStyle('subtitle',fontName='Body',fontSize=14,leading=20,textColor=MUTED,spaceAfter=19),
        'formula':ParagraphStyle('formula',fontName='Body',fontSize=11,leading=17,textColor=NAVY,backColor=GREY,borderPadding=11,spaceBefore=5,spaceAfter=13),
        'reference':ParagraphStyle('reference',fontName='Body',fontSize=8.7,leading=12.2,textColor=INK,spaceAfter=11),
    }


class Timeline(Flowable):
    def __init__(self):
        Flowable.__init__(self); self.width=WIDTH; self.height=135
    def draw(self):
        c=self.canv; x0=20; x1=self.width-20; y=70
        c.setStrokeColor(TEAL); c.setLineWidth(2); c.line(x0,y,x1,y)
        events=[(0,'0','Start baseline'),(10,'10','Feed move'),(16,'16','First decision'),(21,'21','Final acquisition'),(31,'31','Policy horizon')]
        for t,label,text in events:
            x=x0+(x1-x0)*t/31
            c.setFillColor(TEAL); c.circle(x,y,3.5,fill=1,stroke=0)
            c.setFillColor(NAVY); c.setFont('Bold',10); c.drawCentredString(x,y+12,label)
            c.setFillColor(MUTED); c.setFont('Body',8)
            words=text.split(' ')
            for j,w in enumerate(words): c.drawCentredString(x,y-19-j*10,w)
        c.setFont('Body',8.5); c.setFillColor(MUTED)
        c.drawString(x0,113,'Acquisition clock, minutes; deterioration continues throughout')
        c.drawString(x0,6,'After a decision, branch from the saved physical state and account to the common horizon.')


class PairedRates(Flowable):
    """Vector plot of exact per-cell correct singleton proportions."""
    def __init__(self,rows,cases):
        Flowable.__init__(self); self.width=WIDTH
        lookup={(r['case_id'],r['set'],flag(r['active'])):r for r in rows}
        self.pairs=[]
        for case in cases:
            if case['h'] not in ('C','M'): continue
            for s in SETS:
                a=lookup[(case['id'],s,True)]; b=lookup[(case['id'],s,False)]
                self.pairs.append((f'M{case["mode"]} {case["h"]} / {s}',num(b,'correct_singleton_rate'),num(a,'correct_singleton_rate')))
        self.height=44+16*len(self.pairs)
    def draw(self):
        c=self.canv; left=85; right=self.width-15; bottom=22; top=self.height-20
        for v in (0,.25,.5,.75,1):
            x=left+(right-left)*v; c.setStrokeColor(colors.HexColor('#D9E2E8')); c.setLineWidth(.4); c.line(x,bottom,x,top+4)
            c.setFillColor(MUTED); c.setFont('Body',8); c.drawCentredString(x,bottom-12,str(int(v*100)))
        for i,(label,b,a) in enumerate(self.pairs):
            y=top-i*16; xb=left+(right-left)*b; xa=left+(right-left)*a
            c.setFont('Body',8.4); c.setFillColor(INK); c.drawRightString(left-10,y-3,label)
            c.setStrokeColor(colors.HexColor('#B4C7D0'));c.setLineWidth(1.1);c.line(xb,y,xa,y)
            c.setFillColor(MUTED);c.circle(xb,y,2.7,fill=1,stroke=0)
            c.setFillColor(TEAL);c.circle(xa,y,2.7,fill=1,stroke=0)
        c.setFont('Body',8.2);c.setFillColor(MUTED);c.drawString(left,self.height-6,'Correct singleton calls (%)  |  Gray: passive  |  Teal: active')


class OutcomeBars(Flowable):
    """Unpooled outcome compositions for named Mode 1 central cases."""
    CATEGORIES=[('correct_singleton_rate','Correct',TEAL),('wrong_singleton_rate','Wrong',AMBER),
                ('inconclusive_rate','Inconclusive',colors.HexColor('#B6C4CF')),('incompatible_rate','Incompatible',RED)]
    def __init__(self,rows,cases):
        Flowable.__init__(self);self.width=WIDTH
        lookup={(r['case_id'],r['set'],flag(r['active'])):r for r in rows};self.rows=[]
        for case in cases:
            if case['mode']!=1 or case['h'] not in ('C','M'):continue
            for s in SETS:
                for a in (False,True):
                    r=lookup[(case['id'],s,a)]
                    self.rows.append((f'{case["h"]} / {s} / '+('active' if a else 'passive'),r))
        self.height=52+13*len(self.rows)
    def draw(self):
        c=self.canv;left=107;right=self.width-9;top=self.height-30;bottom=24
        legend_x=0
        for _,label,color in self.CATEGORIES:
            c.setFillColor(color);c.rect(legend_x,self.height-10,7,7,fill=1,stroke=0)
            c.setFillColor(INK);c.setFont('Body',8);c.drawString(legend_x+11,self.height-9,label);legend_x+=112
        for i,(label,row) in enumerate(self.rows):
            y=top-i*13;c.setFillColor(INK);c.setFont('Body',8);c.drawRightString(left-8,y+1,label)
            x=left
            for key,_,color in self.CATEGORIES:
                width=(right-left)*num(row,key);c.setFillColor(color);c.rect(x,y,width,8,fill=1,stroke=0);x+=width
        c.setFont('Body',8);c.setFillColor(MUTED)
        for v in (0,.25,.5,.75,1):c.drawCentredString(left+(right-left)*v,5,str(int(v*100))+'%')


class Document:
    def __init__(self,root,draft):
        self.root=root; self.draft=draft; self.s=styles(); self.story=[]; self.section=''
        self.protocol=load_json(root/'protocol.json')
        self.summary=load_json(root/'results/summary.json',True)
        self.check=load_json(root/'checks/final_check.json',True)
        self.diag=load_csv(root/'results/diagnosis_summary.csv')
        self.policy=load_csv(root/'results/policy_summary.csv')
        self.paired=load_csv(root/'results/policy_paired_differences.csv')
        self.qualified=False
        self.inputs={}
        for rel in ['protocol.json','PROTOCOL_FREEZE.json','POLICY_AMENDMENT_FREEZE.json','POLICY_AMENDMENT.txt','results/summary.json','results/diagnosis_summary.csv','results/policy_summary.csv','results/policy_paired_differences.csv','results/calibration.json','checks/final_check.json','revision_model.py','revision_policy.py','dynamics.py','SOURCE_NOTES.txt','sources/source_manifest.json']:
            f=root/rel
            if f.exists(): self.inputs[rel]=sha(f)
        self.verified,self.gate_issues=self.final_gate()
        if not draft and not self.verified:
            raise SystemExit('Final PDF refused: '+'; '.join(self.gate_issues))
        # Unchecked partial results never enter even a layout draft.
        self.show_results=self.verified
        self.claims=[]

    def final_gate(self):
        """Require completion, independent computational pass and current bindings."""
        issues=[]
        for rel in ['PROTOCOL_FREEZE.json','POLICY_AMENDMENT_FREEZE.json','dynamic_status.json','results/summary.json','results/diagnosis_summary.csv','results/policy_summary.csv','results/policy_paired_differences.csv','results/calibration.json','checks/final_check.json']:
            if not (self.root/rel).is_file(): issues.append('missing '+rel)
        if not issues:
            if self.summary.get('schema')!='ssmr.revision.summary.v2': issues.append('summary schema mismatch')
            if self.summary.get('complete') is not True: issues.append('campaign summary incomplete')
            for key,rel in [('protocol_sha256','protocol.json'),('design_freeze_sha256','PROTOCOL_FREEZE.json'),('policy_amendment_sha256','POLICY_AMENDMENT_FREEZE.json'),('calibration_sha256','results/calibration.json'),('dynamic_status_sha256','dynamic_status.json')]:
                if self.summary.get(key)!=sha(self.root/rel): issues.append('summary stale: '+key)
            for name,expected in self.summary.get('files',{}).items():
                file=self.root/'results'/name
                if not file.is_file() or sha(file)!=expected: issues.append('summary file hash mismatch: '+name)
            needed={'diagnosis_summary.csv','policy_summary.csv','policy_paired_differences.csv','policy_trials.csv','calibration.json'}
            if not needed.issubset(self.summary.get('files',{})): issues.append('summary file manifest incomplete')
            if self.summary.get('diagnosis_rows')!=len(self.diag): issues.append('diagnosis row count mismatch')
            if not self.diag or not self.policy or not self.paired: issues.append('empty results')
            if self.check.get('schema')!='ssmr.revision.independent-check.v2': issues.append('checker schema mismatch')
            if self.check.get('complete') is not True: issues.append('independent checker incomplete')
            if self.check.get('computational_pass') is not True: issues.append('independent computational checks did not pass')
            self.qualified=self.check.get('qualified') is True
            if self.qualified:
                resolution=self.check.get('dynamic_resolution',{})
                if self.check.get('original_frozen_dynamic_gate_pass') is not False:
                    issues.append('qualified release must preserve the failed frozen dynamic gate')
                if resolution.get('status')!='EXACT_INPUT_AND_BITWISE_REPLAY_CONFIRMED_WITH_INTERPOLATED_EXPORT_LIMITATION':
                    issues.append('unrecognized qualified dynamic resolution')
                if resolution.get('pass') is not True or resolution.get('source_and_original_results_unchanged') is not True:
                    issues.append('forensic resolution or preservation not confirmed')
                for name in ('forensic_freeze_sha256','forensic_result_sha256','original_verification_sha256','identity_verification_sha256'):
                    value=resolution.get(name)
                    if not value or value not in self.check.get('bindings',{}).get('result_files',{}).values():
                        issues.append('forensic evidence not bound: '+name)
                if not isinstance(resolution.get('affected_records'),int) or resolution['affected_records']<=0:
                    issues.append('forensic record coverage missing')
            elif self.check.get('original_frozen_dynamic_gate_pass') is False:
                issues.append('failed frozen gate lacks explicit qualified resolution')
            bindings=self.check.get('bindings',{})
            for key,rel in [('protocol_sha256','protocol.json'),('design_freeze_sha256','PROTOCOL_FREEZE.json'),('policy_amendment_freeze_sha256','POLICY_AMENDMENT_FREEZE.json'),('calibration_sha256','results/calibration.json'),('dynamic_status_sha256','dynamic_status.json'),('summary_sha256','results/summary.json')]:
                if bindings.get(key)!=sha(self.root/rel): issues.append('checker binding mismatch: '+key)
            bound_files=bindings.get('result_files',{})
            if not {'results/'+name for name in needed}.issubset(bound_files): issues.append('checker result-file bindings incomplete')
            for rel,expected in bound_files.items():
                f=self.root/rel
                if not f.is_file() or sha(f)!=expected: issues.append('checker result-file hash mismatch: '+rel)
                elif rel not in self.inputs: self.inputs[rel]=expected
        return not issues,issues

    def p(self,text,kind='body'):
        self.story.append(Paragraph(clean(text),self.s[kind]))

    def h(self,text): self.p(esc(text),'h2')

    def page(self,number,title):
        if self.story: self.story.append(PageBreak())
        self.p('SCIENTIFIC REVISION  /  '+number,'kicker'); self.p(esc(title),'h1')

    def table(self,headers,rows,widths=None):
        data=[[Paragraph(esc(h),self.s['th']) for h in headers]]
        for row in rows:
            data.append([Paragraph(esc(v),self.s['table']) for v in row])
        t=Table(data,colWidths=widths or [WIDTH/len(headers)]*len(headers),repeatRows=1,hAlign='LEFT')
        t.setStyle(TableStyle([
            ('BACKGROUND',(0,0),(-1,0),NAVY),('VALIGN',(0,0),(-1,-1),'TOP'),
            ('LEFTPADDING',(0,0),(-1,-1),8),('RIGHTPADDING',(0,0),(-1,-1),8),
            ('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),7),
            ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,GREY]),
            ('LINEBELOW',(0,0),(-1,0),.5,NAVY),('LINEBELOW',(0,-1),(-1,-1),.6,colors.HexColor('#C4D1D8')),
        ])); self.story.append(t); self.story.append(Spacer(1,11))

    def box(self,title,text,warn=False):
        color=AMBER if warn else TEAL
        content=[Paragraph(esc(title),ParagraphStyle('boxhead',parent=self.s['h2'],textColor=color)),Paragraph(clean(text),self.s['body'])]
        t=Table([[content]],colWidths=[WIDTH]); t.setStyle(TableStyle([
            ('BACKGROUND',(0,0),(-1,-1),colors.HexColor('#FCF4E9') if warn else PALE),
            ('BOX',(0,0),(-1,-1),.5,color),('LEFTPADDING',(0,0),(-1,-1),12),
            ('RIGHTPADDING',(0,0),(-1,-1),12),('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),4)]))
        self.story.append(t); self.story.append(Spacer(1,12))

    def placeholder(self,description):
        self.box('Results withheld in this draft',esc(description)+' No provisional value is presented as a completed finding.',True)

    def result_abstract(self):
        if not self.show_results:
            return 'The campaign does not yet have a completed final verification record. Diagnostic performance, stress-test outcomes and action consequences are therefore withheld in this draft.'
        s=self.summary
        ids={c['id'] for c in self.protocol['cases'] if c['policy'] and c['h'] in ('C','M')}
        central=[r for r in self.diag if r['group']=='covered_grid' and r['case_id'] in ids and r['set']=='S4']
        active=[r for r in central if flag(r['active'])];passive=[r for r in central if not flag(r['active'])]
        stressed=[r for r in self.diag if r['group']!='covered_grid' and flag(r['supported_label'])]
        worst=max(num(r,'true_rejected_rate') for r in stressed)
        return (f'The completed campaign includes {s["diagnosis_rows"]} diagnostic cells. With all sensor channels, correct-call fractions in the central catalyst/membrane scenarios ranged from {rate_range(passive,"correct_singleton_rate")} under passive acquisition and {rate_range(active,"correct_singleton_rate")} under active acquisition. The largest true-cause rejection fraction was {pct(s["maximum_covered_true_rejection_rate"])} on the covered grid and {pct(worst)} in the selected stress tests. These are fixed-scenario observations, not population guarantees. Physical feed-policy gains and costs are reported for the entire sequence; they do not isolate the value of information.')

    def qualification(self,short=False):
        if not self.show_results or not self.qualified:return
        if short:
            self.p('<b>Qualified verification:</b> the original exact exported-start-state byte gate remains failed. A separately checked replay explains the dense-output interpolation difference; the solver received the exact intended initial state. This is not an all-frozen-gates-pass release.','small')
            return
        d=self.check['dynamic_resolution']
        self.box('The original exact byte gate remains failed',
                 'The stored first sampled state is produced by the solver\'s dense interpolation. In the affected records, its tiny floating-point difference from the exact initial vector violates the original zero-tolerance exported-state test. That test and its failed reports are retained; no looser tolerance replaces them.',True)
        self.p(f'The separate forensic replay covered every affected record ({d["affected_records"]}). It checked that the ODE solver received the exact intended initial vector, regenerated the archived state arrays and CSV records exactly, and confirmed unchanged initial observables and hydrogen/ethanol accounts at float64 precision. The physical source and original results stayed frozen.')
        self.p('The final checker therefore records a qualified, post hoc computational resolution: the intended state continuity and reported quantities are supported, while exact identity of the exported first sample is not. The report does not relabel the original frozen test as passed or treat numerical smallness alone as evidence of harmlessness.')
        self.claims.append({'section':'qualified_verification','source':'checks/final_check.json','affected_records':d['affected_records'],'original_frozen_dynamic_gate_pass':False,'resolution':d['status']})

    def central_case_caption(self):
        groups={}
        for c in self.protocol['cases']:
            if c['policy'] and c['h'] in ('C','M'):
                key=(c['h'],c['drop'],c['controls']['rate_per_min'])
                groups.setdefault(key,[]).append(c['mode'])
        labels=[]
        for (h,drop,rate),modes in sorted(groups.items()):
            labels.append(f'{h} in Modes '+', '.join(map(str,sorted(modes)))+f': {100*drop:g}% anchor, decay {rate:g} per min')
        return '; '.join(labels)+'. Each anchor is the nominal quasi-steady map hydrogen drop at minute 10, not the actual dynamic loss. C denotes catalyst and M membrane deterioration.'

    def plain_guide(self):
        self.h('What changed')
        self.p('The diagnostic now sees noisy, delayed measurements and accounts for their correlation. Its thresholds are calibrated before independent evaluation. The operating policy issues a real feed command, and both hydrogen shortfall and ethanol use are counted through the same horizon.')
        self.h('What succeeded and what failed')
        if not self.show_results:
            self.p('The methods and reporting structure are prepared. The campaign and independent checks are not yet complete, so diagnosis performance and action benefits are withheld. No success or failure of the revised scientific method is inferred from this draft.')
        else:
            core=[r for r in self.diag if r['group']=='covered_grid']
            contradicted=[r for r in core if num(r,'true_rejected_ci_lo')>self.protocol['alpha']]
            self.p('The computational campaign completed and its final verification record is bound to the result files used here. '+self.result_abstract())
            self.qualification(short=True)
            if contradicted:
                self.p(f'In {len(contradicted)} covered-grid cells, the pointwise interval for true-cause rejection lay wholly above the nominal {pct(self.protocol["alpha"])} level. Those observed failures remain in the report; numerical verification does not remove them.','small')
                self.claims.append({'section':'opening_guide','claim':'covered cells with pointwise rejection interval wholly above alpha','value':len(contradicted)})
            else:
                self.p('No covered cell had a pointwise true-rejection interval wholly above the nominal level. This does not prove simultaneous or uniform performance across the map. Correct calls, abstentions and stress outcomes remain separate results.','small')
        self.h('Claims this evidence supports')
        self.p('A reproducible simulation study of a specific diagnostic experiment and feed policy, with explicit error rates, abstentions and whole-sequence physical trade-offs under declared assumptions.')
        self.h('Claims it does not support')
        self.p('Laboratory accuracy, a universally reliable diagnosis, an optimal feed experiment, economic payback or journal acceptance. Operational usefulness remains conditional on the physical trade-offs and an explicit decision objective.')

    def diagnosis_results(self):
        if not self.show_results:
            self.placeholder('This page will report checked per-stratum diagnosis outcomes for active and passive acquisition, including inconclusive and incompatible records.');return
        core=[r for r in self.diag if r['group']=='covered_grid']
        self.p('Per-cell rate ranges over covered truth strata. Each row spans distinct fixed scenarios; these ranges are not pooled rates or confidence intervals.','small')
        rows=[]
        for s in SETS:
            for a in (False,True):
                part=[r for r in core if r['set']==s and flag(r['active'])==a]
                rows.append([s,'Active' if a else 'Passive',rate_range(part,'correct_singleton_rate'),rate_range(part,'wrong_singleton_rate'),rate_range(part,'true_rejected_rate')])
                self.claims.append({'section':'diagnosis_ranges','filter':{'set':s,'active':a,'group':'covered_grid'},'displayed':rows[-1]})
        self.table(['Set','Acquisition','Correct call','Wrong call','True cause rejected'],rows,[36,79,130,121,WIDTH-366])
        self.h('Mode 1 central catalyst/membrane cases')
        self.story.append(OutcomeBars(core,[c for c in self.protocol['cases'] if c['policy']]))
        self.p(self.central_case_caption()+' Each bar is a fixed cell; none are pooled. Counts and pointwise intervals are retained in diagnosis_summary.csv.','small')

    def diagnosis_readout(self):
        if not self.show_results:
            self.placeholder('This page will interpret the checked catalyst/membrane and healthy cases, including correct-call denominators and conditional timing.');return
        core=[r for r in self.diag if r['group']=='covered_grid']
        lookup={(r['case_id'],r['set'],flag(r['active'])):r for r in core}
        cases=[c for c in self.protocol['cases'] if c['policy'] and c['h'] in ('C','M')]
        comparisons=[];rows=[];timings=[]
        for c in cases:
            for s in SETS:
                b=lookup[(c['id'],s,False)];a=lookup[(c['id'],s,True)]
                comparisons.append(num(a,'correct_singleton_rate')-num(b,'correct_singleton_rate'))
            b=lookup[(c['id'],'S4',False)];a=lookup[(c['id'],'S4',True)];n=int(a['n'])
            rows.append([f'M{c["mode"]} {c["h"]}',f'{int(b["correct_singleton"])}/{int(b["n"])}',f'{int(a["correct_singleton"])}/{n}',f'{int(a["wrong_singleton"])}/{n}',f'{int(a["inconclusive"])+int(a["incompatible"])}/{n}'])
            median=num(a,'median_correct_time_min')
            timings.append(f'M{c["mode"]} {c["h"]}: '+('no correct call' if median is None else f'{median:g} min among {int(a["correct_singleton"])}/{n} records'))
            self.claims.append({'section':'central_case_readout','case_id':c['id'],'set':'S4','passive':b,'active':a})
        better=sum(v>0 for v in comparisons);worse=sum(v<0 for v in comparisons);ties=sum(v==0 for v in comparisons)
        self.p(f'For the prespecified central catalyst and membrane cases across the sensor sets, active acquisition produced a higher observed correct-call fraction in {better} of {len(comparisons)} comparisons, a lower fraction in {worse}, and the same fraction in {ties}. These are paired scenario comparisons, not a significance test or a population success rate.')
        self.h('What happened with all sensor channels (S4)')
        self.p(self.central_case_caption(),'small')
        self.table(['Case','Passive correct','Active correct','Active wrong','Active no call'],rows,[53,109,109,105,WIDTH-376])
        self.p('All records remain in each denominator. No call combines inconclusive and model-incompatible outcomes, which remain separate in the result data. Case names identify operating mode and true catalyst (C) or membrane (M) deterioration; these are the policy-designated central scenarios, not cases chosen for favorable outcomes.','small')
        self.h('A diagnosis time is conditional on making a diagnosis')
        self.p('Active S4 median time among correct calls: '+'; '.join(timings)+'.')
        self.p('The general diagnosis-time column also includes wrong singleton calls. Neither timing median describes all episodes, and records without a call are not assigned a successful delay. A short conditional median cannot compensate for a small correct-call fraction.','small')
        healthy=[r for r in core if r['true_h']=='H']
        self.h('The healthy case remains a structural limit')
        self.p('The healthy reference overlaps the zero-fault limits of multiple candidate families. Across the checked healthy cells, correct healthy-singleton fractions were '+rate_range(healthy,'correct_singleton_rate')+', while inconclusive fractions were '+rate_range(healthy,'inconclusive_rate')+'. Healthy operation is therefore not automatically a uniquely diagnosable label in this model.')
        self.claims.append({'section':'central_case_comparison','higher':better,'lower':worse,'same':ties,'comparisons':len(comparisons)})

    def stress_results(self):
        if not self.show_results:
            self.placeholder('This page will report held-out parameter and model/noise stress results using unchanged thresholds. Failures remain part of the evidence.');return
        rows=[]
        groups=[g for g in sorted({r['group'] for r in self.diag}) if g not in ('covered_grid','out_of_family')]
        for g in groups:
            part=[r for r in self.diag if r['group']==g and flag(r['supported_label'])]
            if not part:continue
            worst=max(part,key=lambda r:num(r,'true_rejected_rate'))
            wrong=max(num(r,'wrong_singleton_rate') for r in part)
            rows.append([g.replace('_',' '),rate_range(part,'correct_singleton_rate'),pct(num(worst,'true_rejected_rate')),pct(num(worst,'true_rejected_ci_lo'))+' to '+pct(num(worst,'true_rejected_ci_hi')),pct(wrong)])
            self.claims.append({'section':'stress','group':g,'worst_rejection_case':{k:worst[k] for k in ('case_id','set','active')},'displayed':rows[-1]})
        self.p('Descriptive extrema across the declared cells in each stress family. The rejection interval belongs to the cell with the largest observed rejection rate; it is pointwise, not simultaneous.','small')
        self.table(['Stress family','Correct-call range','Max reject','Its pointwise 95% interval','Max wrong'],rows,[107,114,66,139,WIDTH-426])
        supported=[r for r in self.diag if r['group']!='covered_grid' and flag(r['supported_label'])]
        if supported:
            worst=max(supported,key=lambda r:num(r,'wrong_singleton_rate'))
            self.p('The largest observed wrong-call fraction among supported stress cells occurred for '+esc(worst['case_id'])+' / '+esc(worst['set'])+' / '+('active' if flag(worst['active']) else 'passive')+': '+pct(num(worst,'wrong_singleton_rate'))+'. This describes a checked failure boundary under '+esc(worst['group'].replace('_',' '))+', with the original thresholds retained.','small')
            self.claims.append({'section':'stress_wrong_boundary','cell':worst})
            rejected=max(supported,key=lambda r:num(r,'true_rejected_rate'))
            self.p('Rejection and wrong diagnosis are different failures. For '+esc(rejected['case_id'])+' / '+esc(rejected['set'])+' / '+('active' if flag(rejected['active']) else 'passive')+', the true cause was rejected in '+pct(num(rejected,'true_rejected_rate'))+' of records; '+pct(num(rejected,'incompatible_rate'))+' ended model-incompatible and '+pct(num(rejected,'wrong_singleton_rate'))+' produced a wrong singleton. Refusing a diagnosis can avoid a false label while still making the method unusable in that condition.','small')
            self.claims.append({'section':'stress_rejection_interpretation','cell':rejected})
        out=[r for r in self.diag if r['group']=='out_of_family']
        self.p('For out-of-family cases, the range of singleton-call fractions was '+rate_range([dict(r,singleton_rate=str(num(r,'correct_singleton_rate')+num(r,'wrong_singleton_rate'))) for r in out],'singleton_rate')+'. No singleton can establish a supported true-cause diagnosis for those combined or excluded causes.','small')

    def policy_results(self):
        if not self.show_results:
            self.placeholder('This page will report paired physical action outcomes from the common acquisition-plus-action horizon, with signed active-minus-passive differences.');return
        cases={c['id']:c for c in self.protocol['cases']}
        rows=[]
        for r in self.paired:
            case=cases[r['case_id']]
            if case['h'] not in ('C','M'):continue
            f=num(r,'H2_shortfall_mol_difference_mean')
            e=num(r,'actual_ethanol_mol_difference_mean')
            c=num(r,'commanded_ethanol_mol_difference_mean')
            rows.append([f'M{case["mode"]} {case["h"]}',r['set'],f'{1000*f:+.4f}',f'{1000*e:+.4f}',f'{1000*c:+.4f}'])
            self.claims.append({'section':'policy','case_id':r['case_id'],'set':r['set'],'displayed':rows[-1],'scale':'mol to mmol, x1000'})
        self.p('Paired mean active-minus-passive differences for the prespecified catalyst/membrane policy cases. All columns are amounts in mmol over the complete common horizon. A negative shortfall contrast is favorable for hydrogen delivery; ethanol contrasts remain separate.','small')
        self.p(self.central_case_caption(),'small')
        self.table(['Case','Set','H2 shortfall (mmol)','Actual ethanol (mmol)','Command ethanol (mmol)'],rows,[53,36,135,137,WIDTH-361])
        selected=[r for r in self.paired if cases[r['case_id']]['h'] in ('C','M')]
        reduced=[r for r in selected if num(r,'H2_shortfall_mol_difference_mean')<0]
        increased=[r for r in selected if num(r,'H2_shortfall_mol_difference_mean')>0]
        extra=sum(num(r,'actual_ethanol_mol_difference_mean')>0 for r in reduced)
        self.p(f'Active acquisition reduced mean physical hydrogen shortfall in {len(reduced)} of these {len(selected)} comparisons and increased it in {len(increased)}. Among the shortfall reductions, {extra} also used more delivered ethanol. These signs describe the tested feed rule and include the acquisition pulse; they do not establish an economic benefit.','small')
        self.claims.append({'section':'policy_signs','comparisons':len(selected),'shortfall_reduced':len(reduced),'shortfall_increased':len(increased),'reduced_with_more_ethanol':extra})
        self.p('Per-record outcomes are retained in results/policy_trials.csv. Per-case mean, standard deviation, minimum and maximum are in policy_summary.csv; paired contrasts are summarized in policy_paired_differences.csv. The spread across records is not the standard error of the reported mean.','small')

    def policy_readout(self):
        self.box('The comparison does not isolate information value',
                 'The active experiment itself adds feed. Its hydrogen effect can arise directly from that extra feed as well as from a changed diagnosis or later command. No matched feed-only, nondiagnostic comparator was included. The checked differences measure the whole acquisition-and-action sequence; they cannot establish the separate causal value of diagnostic information.',True)
        if not self.show_results:
            self.placeholder('This page will retain healthy and meter-bias physical consequences as well as deterioration cases.');return
        cases={c['id']:c for c in self.protocol['cases']};rows=[]
        for r in self.paired:
            c=cases[r['case_id']]
            if c['h'] not in ('H','S') or r['set']!='S4':continue
            h=num(r,'H2_shortfall_mol_difference_mean');e=num(r,'actual_ethanol_mol_difference_mean')
            rows.append([f'M{c["mode"]} '+('Healthy' if c['h']=='H' else 'Meter bias'),f'{1000*h:+.6g}',f'{1000*e:+.6g}'])
            self.claims.append({'section':'healthy_bias_physical_outcomes','case_id':c['id'],'set':'S4','displayed':rows[-1],'scale':'mol to mmol, x1000'})
        self.h('Healthy operation and meter bias: all sensor channels')
        self.table(['Prespecified S4 case','H2 shortfall difference (mmol)','Actual ethanol difference (mmol)'],rows,[151,174,WIDTH-325])
        self.p('Active minus passive; the acquisition pulse and post-decision command are both included. A near-zero shortfall difference with positive ethanol use is an added-feed cost without material recovery of unmet hydrogen demand. The meter-bias cases leave the physical plant healthy. All sensor sets and commanded-feed differences remain in the checked files.','small')
        extra=sum(num(r,'actual_ethanol_mol_difference_mean')>0 for r in self.paired)
        self.p(f'Across all {len(self.paired)} prespecified case/sensor policy comparisons, active acquisition used more actual ethanol in {extra}. The table prevents the useful deterioration examples from hiding consequences where the plant itself does not need restoration.')
        self.p('The repair to action accounting is concrete: each record issues a feed command, follows the actual fault trajectory, and measures hydrogen and ethanol over the same horizon. It supports physical trade-off statements. It does not supply maintenance effectiveness, service downtime, prices, economic net benefit or an information-specific value-of-information estimate.')
        self.h('The remaining policy limit')
        self.p('Less hydrogen shortfall with more ethanol is a trade-off, not an automatic net benefit. The policy uses fitted paths rather than a full uncertainty set over possible health histories. Retaining the true cause does not ensure that its selected template predicts future production accurately; the observed dynamic outcomes determine the claim.','small')
        self.claims.append({'section':'all_policy_ethanol_signs','comparisons':len(self.paired),'actual_ethanol_increased':extra})

    def content(self):
        p=self.protocol
        # 1: cover and abstract
        self.p('SSMR  /  MAJOR SCIENTIFIC REVISION  /  30 SEPTEMBER 2026','kicker')
        self.p('Diagnosing deterioration<br/>before choosing a feed action','title')
        self.p('Calibrated finite-grid diagnosis and physical action accounting in an ethanol membrane-reformer simulation','subtitle')
        self.box('DRAFT - campaign results not released' if self.draft else ('Completed revision with qualified verification' if self.qualified else 'Completed computational revision'),
                 'This is a revised simulation study and evidence report. It is not a journal acceptance decision or a laboratory validation. The original submission and its historical reviews remain preserved.',self.draft)
        self.plain_guide()
        # 2
        self.page('01','What changed, and why')
        self.h('Revised abstract')
        self.p('A decline in reported hydrogen production can arise from process deterioration, impaired feed delivery or measurement bias. This simulation study compares passive acquisition with a scheduled feed move using delayed observations, joint covariance and a finite bank of evolving fault paths. A sequential exclusion rule is calibrated on separate observation episodes. Bounded feed policies are assessed by dynamic hydrogen and ethanol accounts. '+self.result_abstract())
        self.p('The original review found a gap between deterministic separation and statistical diagnosis. Reproducing the original arithmetic did not close that gap. The revised procedure is restricted to declared model, noise and policy assumptions.','small')
        self.table(['Original concern','Revision implemented','Remaining boundary'],[
            ['Generating cause received a zero score','Fit every candidate to the same noisy observations','Performance is determined by held-out evaluation'],
            ['Shared-baseline covariance was omitted','Use absolute window means and the full within-instrument covariance','Cross-instrument dependence remains a declared independence assumption'],
            ['Threshold degrees of freedom were not justified','Calibrate maxima over the scheduled looks using finite-sample ranks','Protection applies only to covered finite truth strata and the stated noise law'],
            ['Equal action names implied zero consequence difference','Issue an actual feed command and integrate physical outcomes','No service cost, price or monetary payoff is invented'],
            ['A fixed-feed approximation supported the experiment claim','Simulate acquisition, ongoing deterioration and post-decision action','New evidence is Python simulation, not a new native or physical validation'],
        ],[112,204,WIDTH-316])
        self.h('Historical thresholds remain historical')
        self.p('The frozen original map and the later A1 amendment are prior evidence. Neither is presented here as a newly calibrated operating map. Their reproduction and chronology are retained in the preceding audit; the revised procedure has its own protocol, source freeze and checked outputs.')
        self.p('Active diagnosis is established methodology [3,4]. The candidate contribution is the bounded SSMR experiment and its action consequences. Whether it succeeds is an empirical result, not a premise of this document.')
        # 3
        self.page('02','Plant, candidate causes and dynamics')
        self.p('The physical truth trajectories use the staged benchmark equations and supplied initial state. Catalyst activity, membrane permeability and feed-delivery gain can evolve continuously during an episode. The diagnostic candidate bank uses evolving quasi-steady response templates; it is deliberately distinguished from the dynamic truth integration.')
        self.table(['ID','Meaning','How it enters the episode'],[
            ['C','Catalyst deterioration','Activity follows the declared time history'],['M','Membrane deterioration','Permeability follows the declared time history'],
            ['F','Feed-delivery loss','Actual ethanol differs from the commanded feed'],['S','Hydrogen-meter offset','The physical plant stays healthy; the hydrogen measurement is shifted'],
            ['H','Healthy','Reference physical process and measurement behavior'],['CM','Combined deterioration','A stress case outside the single-cause candidate family'],
        ],[36,141,WIDTH-177])
        self.h('Initial state and fault timing')
        self.p('Before acquisition, the supplied state is settled at the scenario health at time zero while that health is held fixed. Failure to meet the declared settling criterion is retained as a computational failure. Deterioration then evolves inside the ODE right-hand side. A feed event changes the input without resetting the physical state.')
        self.p('Scenario drop labels refer to a nominal quasi-steady map anchor at minute 10. They are not measured dynamic losses at that instant. Some anchors leave the declared response-map domain and are recorded as excluded before calibration. In particular, Mode 2 feed loss is investigated as an out-of-family stress; a map-domain restriction is not proof that feed loss is physically impossible.')
        self.p('The benchmark itself provides steady-state experimental model context [5,6]. This revision does not create new plant observations or validate evolving fault kinetics experimentally.','small')
        # 4
        self.page('03','Acquire observations before diagnosing')
        self.story.append(Timeline())
        self.p(f'The active acquisition raises commanded ethanol by {p["active_feed_increment"]:.4f} mol/min at minute {p["active_move_start_min"]:g}; passive acquisition keeps the baseline command. Scheduled diagnostic looks occur at minutes '+', '.join(f'{x:g}' for x in p['looks_min'])+'. All times refer to the acquisition clock, not elapsed time since a detected fault onset.')
        self.table(['Sensor set','Available quantities'],[
            ['S1','Hydrogen production rate'],['S3','S1 plus outlet temperature and retentate volumetric flow'],['S4','S3 plus four gas-composition channels'],
        ],[68,WIDTH-68])
        self.h('Causal sampling and paired comparisons')
        self.p('Each instrument is sampled on its stated schedule. A chromatograph result is usable only after its reporting delay, even when its gas sample was acquired earlier. Window means are built from the actual samples available at the decision look. Reusing those same instrument records across sensor sets preserves the pairing of comparisons.')
        self.p('The two acquisition policies use matched noise draws for each scenario; calibration and evaluation occupy separate seed namespaces. The deterministic truth path can be reused across independent noise records. That produces repeated simulated observation episodes of one fixed plant scenario, not independently observed physical plants.')
        self.box('Timing denominator matters','Report a diagnosis time only for records that produced a singleton call. The final acquisition time is not an imputed diagnosis time for records that remain inconclusive or model-incompatible.')
        # 5
        self.page('04','A joint observation model')
        self.p('The analysis uses absolute means over the prespecified time windows. This avoids constructing an apparently independent baseline and difference from the same samples. Serial correlation, a persistent instrument bias, and reuse of samples are retained in the covariance of the summaries.')
        self.p('For instrument j, let A<sub>j</sub> be the averaging matrix, K<sub>j</sub> the covariance of its raw serial noise, and b<sub>j</sub> the bound of its independent uniform record-level bias. The working covariance is:')
        self.p('C<sub>j</sub> = A<sub>j</sub>K<sub>j</sub>A<sub>j</sub><super>T</super> + (b<sub>j</sub><super>2</super>/3) 11<super>T</super>','formula')
        self.p('The bias is drawn once per instrument and record. Its uncertainty does not vanish when more readings are averaged. Within-instrument errors follow the declared stationary AR(1) model; different instruments are independent in the nominal model. The full summary covariance is block diagonal across those instrument blocks.')
        self.h('What nuisance treatment means here')
        self.p('The candidate score profiles over its finite severity/rate templates. Persistent measurement bias is integrated through a declared random-effect covariance and calibration distribution; the procedure does not explicitly estimate every bias and does not guarantee validity for an arbitrary fixed bias within the bound. Gaussian innovations plus uniform bias also do not make the entire summary exactly Gaussian.')
        self.h('Instrument assumptions remain visible')
        self.p('The benchmark identifies an Agilent 3000 A MicroGC and a Bronkhorst hydrogen flowmeter, but does not supply the latter\'s exact model/range or the covariance and repeatability needed here. A membrane-surface K-type thermocouple is mentioned; it is not a specified outlet-temperature instrument. All diagnostic noise and delay inputs remain simulation assumptions [6,7].')
        self.p('A manufacturer accuracy limit is not automatically an independent Gaussian standard deviation. Calibration bias, repeatability, drift, gain error and response delay require separate interpretation [7].')
        # 6
        self.page('05','Calibration and sequential decisions')
        self.p('At each look, every supported cause is compared with the observed summary using the minimum full-covariance Mahalanobis distance over its frozen finite template bank. The diagnostic function receives observations and the bank, not the generating cause or future measurements.')
        self.p('D<sub>h,l</sub>(z) = min<sub>q in bank(h)</sub> (z - m<sub>h,l,q</sub>)<super>T</super>C<sub>l</sub><super>-1</super>(z - m<sub>h,l,q</sub>)','formula')
        self.p(f'For each covered truth stratum, {p["n_calibration"]} independent calibration episodes provide the maximum true-cause score across both looks. With alpha = {p["alpha"]:.2f}, the threshold is the order statistic at rank ceil((n + 1)(1 - alpha)). The cause-specific threshold is the maximum over its included truth-stratum thresholds. No chi-square reference distribution is imposed.')
        self.table(['Decision condition','Recorded outcome'],[
            ['Exactly one cause remains at minute 16','Stop and retain that singleton decision'],['Zero or multiple causes remain at minute 16','Continue to minute 21'],
            ['Exactly one remains at minute 21','Report that singleton diagnosis'],['Multiple remain at minute 21','INCONCLUSIVE'],['No cause remains at minute 21','MODEL_INCOMPATIBLE'],
        ],[WIDTH*.57,WIDTH*.43])
        self.p('Membership is cumulative: a rejected cause cannot re-enter. Even an empty set at minute 16 waits until minute 21 under this declared rule. The calibrated maximum accounts for the scheduled looks on the acquisition path. The physical policy begins at the recorded decision time; its accounts include the elapsed acquisition period.')
        self.box('Scope of the rank argument','The bound is marginal over fresh calibration and test draws for each included fixed truth stratum under the stated observation law. It is not a uniform claim over continuous severity, arbitrary bias, unseen kinetics or distribution shift. A particular realized calibration threshold can still have empirical error above the nominal target. [1,2]')
        # 7
        self.page('06','Evaluation design and release criteria')
        cats=Counter(c['category'] for c in p['cases'])
        self.table(['Declared component','Protocol specification'],[
            ['Calibration',f'{p["n_calibration"]} independent observation episodes per included calibration stratum'],
            ['Nominal evaluation',f'{p["n_evaluation"]} independent observation episodes per declared evaluation cell'],
            ['Observation stresses',f'{p["n_stress"]} episodes per selected stress cell; thresholds unchanged'],
            ['Truth categories',', '.join(k.replace('_',' ')+': '+str(v) for k,v in cats.items())],
            ['Scope of replication','Independent observation episodes conditional on the specified deterministic truth path'],
        ],[139,WIDTH-139])
        self.p('These are protocol specifications, not completion counts. The frozen checker must confirm actual coverage, split independence, causality, covariance, scores, thresholds, decisions and physical accounts before final publication of the results.')
        self.h('Outcome measures')
        self.p('For each fixed evaluation cell, report true-cause rejection, wrong singleton diagnosis, correct singleton diagnosis, inconclusive outcome and empty-set incompatibility. Every simulated record stays in the denominator. Exact pointwise binomial intervals describe uncertainty from the independent episode repetitions, not from serial samples within an episode.')
        self.p('Configuration-trial totals are not counts of mutually independent experiments: acquisition policies share noise draws, and sensor sets reuse measurements. Independence applies within each cell for its interval; cross-configuration comparisons preserve the pairing.','small')
        self.p('Ranges across deterministic strata are descriptive ranges, not estimates of a population-wide rate. No scientific success is forced by the integrity gate: a reproduced false-rejection rate, poor power or unfavorable action trade-off can pass a computation check and still undermine the proposed procedure.')
        self.h('Separation of tuning and evaluation')
        self.p(esc(p['seed_rule']))
        self.p('Failures under distribution shifts are retained. Changing thresholds or selecting favorable cases after viewing held-out results would require a new versioned protocol and a fresh evaluation.')
        # 8
        self.page('07','Diagnosis results')
        self.diagnosis_results()
        self.h('How to read these results')
        self.p('Correct calls measure useful resolution; a low wrong-call rate can coexist with frequent abstention. True-cause rejection is measured at the actual stopping look and is separate from the final outcome.','small')
        self.page('08','What the diagnostic outcomes mean')
        self.diagnosis_readout()
        # 9
        self.page('09','Stress tests and failure boundaries')
        self.stress_results()
        self.h('What a stress failure means')
        self.p('The nominal covariance and thresholds stay unchanged under altered noise, bias, gain, kinetics and fault histories. A failure marks a boundary of this method. These selected cases do not establish exhaustive robustness to correlated instruments, unmodeled delays, plant variability or real aging. Numerical reproducibility does not remove a scientific failure.','small')
        # 10
        self.page('10','Actions are physical commands')
        self.p('After diagnosis, the revised policy selects a bounded ethanol command rather than an action name. For each retained fitted path, it finds the smallest command on a fixed grid predicted to restore the nominal healthy map output at baseline feed at the declared future sample times, ending at the common horizon. It then chooses the largest of those candidate-specific requirements.')
        self.p('If a retained candidate cannot meet the target on the grid, the policy uses the upper command bound and records infeasibility. An empty candidate set keeps the baseline command and records incompatibility. This is a bounded plug-in rule; it is neither an optimal controller nor a uniform safety guarantee.')
        self.p('Physical policy consequences are evaluated only for the preselected central cases under the nominal observation law. The stress tables test diagnosis with unchanged thresholds; they do not establish action-policy robustness under every noise, kinetic or combined-fault stress.','small')
        self.p('A recorded pre-evaluation amendment distinguishes that restoration target from the benchmark\'s rounded demand: the original comparison could increase feed even for a zero-fault prediction. The replacement policy was frozen before calibration/evaluation; physical shortfall still uses the benchmark demand. The original protocol and helper remain preserved.','small')
        self.table(['Physical account','Definition and interpretation'],[
            ['Hydrogen shortfall','Integral of max(demand - true production, 0), in mol'],['Hydrogen production','Integral of true production, in mol'],
            ['Commanded ethanol','Integral of the commanded flow, in mol'],['Actual ethanol','Integral of delivered flow, in mol; differs under a feed-delivery fault'],
            ['Active - passive difference','Signed paired contrast over the same truth, noise pairing and total horizon'],
        ],[139,WIDTH-139])
        self.h('Common horizon, continuous state')
        self.p(f'The accounts run from acquisition time zero to minute {p["policy"]["horizon_end_min"]:g}, including the diagnostic feed pulse. Each continuation begins from the exact saved ODE state at its decision time. Only the acquisition prefix before that decision is included; unused acquisition tails are excluded.')
        self.p('Command integrals follow the piecewise constant input intervals; true production and delivered-feed integrals use the declared endpoint quadrature within each segment. No integration interval bridges an unrepresented input discontinuity.')
        # 11
        self.page('11','Policy consequences and interpretation')
        self.policy_results()
        self.page('12','Separate physical benefit from information value')
        self.policy_readout()
        # 12
        self.page('13','Provenance, scope and next scientific step')
        prior=self.root.parent/'full_rerun/checks/final_check_suite.json'
        old=load_json(prior,True)
        self.h('Earlier native reproduction')
        if old and old.get('numeric_replay_pass') is True:
            self.p('The preceding full rerun reports successful numeric replay of the original study and retains machine-readable native MATLAB evidence. This closes the initial audit\'s missing-native-trajectory limitation for the covered baseline work. It does not establish statistical calibration of the old method or validate the new diagnosis procedure.')
            self.p('The native fine-grid record retained a diary/provenance limitation after disconnections. Source, state, solver-option and CSV checks were reported, while the absent diary was not silently converted into proof of execution provenance. A planned native repeat was not counted as completed evidence.','small')
            self.inputs['../full_rerun/checks/final_check_suite.json']=sha(prior)
        else:
            self.p('Earlier native reproduction is historical evidence and is not claimed complete from this document\'s current inputs. The revised method is evaluated separately.')
        self.h('New method evidence')
        self.p('The revised acquisition, covariance, calibration and physical policy campaign is Python-based. It is a new computational experiment using staged reference equations, not another native MATLAB reproduction or a plant trial. A separate AI agent using the same model family prepared the fresh checker implementation and review. This is internal numerical verification, not external journal peer review, cross-model review or physical validation.')
        self.h('The remaining scientific boundary')
        self.p('The useful endpoint is a reproducible, honestly scoped computational result: where a cause can be resolved, where the rule must abstain, where assumptions fail, and what the issued feed command actually does. Application-specific evidence can support a simulation paper without implying deployability or journal acceptance.')
        self.p('Before a rig claim, identify the actual instruments and settings, measure joint repeatability and time dependence, characterize bias and delays, and test the complete diagnosis/action sequence against independently observed deterioration. Before a broad optimality claim, compare credible alternative excitations and policies under explicit constraints and losses.')
        # 13
        self.page('14','Primary references and source limits')
        refs=[
            ('1','Dufour JM. Monte Carlo tests with nuisance parameters: A general approach to finite-sample inference and nonstandard asymptotics. Journal of Econometrics. 2006;133:443-477.','10.1016/j.jeconom.2005.06.007','General rank/nuisance-test foundation; no direct SSMR guarantee.'),
            ('2','Morris TP, White IR, Crowther MJ. Using simulation studies to evaluate statistical methods. Statistics in Medicine. 2019;38:2074-2102.','10.1002/sim.8086','Simulation design and Monte Carlo uncertainty.'),
            ('3','Scott JK, Findeisen R, Braatz RD, Raimondo DM. Input design for guaranteed fault diagnosis using zonotopes. Automatica. 2014;50:1580-1589.','10.1016/j.automatica.2014.03.016','Active input design for bounded linear model families.'),
            ('4','Raimondo DM, Marseglia GR, Braatz RD, Scott JK. Closed-loop input design for guaranteed fault diagnosis using set-valued observers. Automatica. 2016;74:107-117.','10.1016/j.automatica.2016.07.033','Closed-loop active diagnosis; different uncertainty assumptions.'),
            ('5','Serra M, Ocampo-Martinez C, Li M, Llorca J. Model predictive control for ethanol steam reformers with membrane separation. International Journal of Hydrogen Energy. 2017;42:1949-1961.','10.1016/j.ijhydene.2016.10.110','Membrane-reformer modeling and simulated control context.'),
            ('6','Arcila-Osorio M, Destro F, Ocampo-Martinez C, Llorca J, Braatz RD. A benchmark simulator for advanced control of ethanol steam reforming. Renewable Energy. 2026;256:124743.','10.1016/j.renene.2025.124743','Benchmark, steady-state validation and instrument description.'),
            ('7','JCGM. Evaluation of measurement data - Guide to the expression of uncertainty in measurement. JCGM 100:2008.','10.59161/JCGM100-2008E','Interpretation of specifications, uncertainty and distribution assumptions.'),
        ]
        for num,title,doi,limit in refs:
            self.p(f'<b>[{num}]</b> {esc(title)}<br/><link href="https://doi.org/{doi}" color="#007E83">doi:{doi}</link><br/><i>{esc(limit)}</i>','reference')
        self.p('A recent adjacent bibliographic lead is Santra, Koopman-PCE-based confidence-bounded fault diagnosis and recovery for hydrogen demand tracking in a membrane reactor, doi:10.1016/j.compchemeng.2026.109728. Only publisher-indexed abstract/metadata were accessible; no full-method comparison or performance endorsement is made. See SOURCE_NOTES.txt for primary URLs, inspected sections and access limits.','small')
        # 14
        self.page('APPENDIX A','Declared sensor and numerical assumptions')
        self.p('These settings are simulation inputs. Their display is not a claim that the named physical instruments attain these errors or time constants. SD denotes marginal per-sample random-error scale; the bias bound applies once per record.','small')
        rows=[]
        labels={'H2_mol_min':'H2 (mol/min)','T_out_K':'Outlet T (K)','waste_m3_min':'Retentate (m3/min)','y_H2':'H2 fraction','y_CH4':'CH4 fraction','y_CO':'CO fraction','y_CO2':'CO2 fraction'}
        for mode in ('1','2'):
            for f,v in p['observation_models'][mode].items():
                rows.append([mode,labels[f],f'{v["sd"]:.4g}',f'{v["bias_bound"]:.4g}',f'{v["period_min"]:g} / {v["delay_min"]:g}',f'{v["phi"]:g}'])
        self.table(['Mode','Quantity','SD','Bias bound','Period / delay (min)','AR(1)'],rows,[44,107,69,78,113,WIDTH-411])
        self.h('Integrator and state treatment')
        self.p('Solver: '+esc(p['solver']['method'])+'; axial discretization np = '+str(p['solver']['np'])+'; relative tolerance '+str(p['solver']['rtol'])+'; absolute tolerance '+str(p['solver']['atol'])+'; maximum step '+str(p['solver']['max_step_min'])+' min. Initialization and discontinuity handling follow the dynamic-engine contract.')
        self.p('Nominal model parameters are inherited from the staged public benchmark. These solver settings and repeatability checks are not a mesh-convergence demonstration. The run inventory retains raw trajectories, state snapshots, interval accounts, seed identities and intermediate diagnostic records.','small')
        # 15
        self.page('APPENDIX B','Qualified computational verification')
        if self.show_results:
            self.qualification()
        else:
            self.p('The final verification record is pending. A failed exact exported-start-state gate is being investigated by a separate frozen forensic replay. The original failed reports remain part of the evidence; this draft does not pre-accept a resolution.')
        self.h('What the internal checks can establish')
        self.p('The independent implementation checks recorded covariance, score and threshold arithmetic, seed separation, causal decisions, raw result summaries, and physical accounts. A separate AI agent using the same model family performed this internal check. It is not a proof of the process equations, an experimental validation, or external journal peer review.')
        self.p('A qualified resolution does not alter the scientific performance findings. Wrong calls, inconclusive records, model incompatibility, stress failures and unfavorable feed costs remain reportable results. A passed integrity check cannot turn them into evidence of reliable plant diagnosis.')
        self.page('APPENDIX C','Audit trail and reproducibility')
        self.h('Release status')
        self.p('DRAFT: final results are withheld. '+esc('; '.join(self.gate_issues)) if not self.show_results else ('Final release is qualified by the preserved exported-start-state failure and separately checked forensic resolution. Scientific limitations and stress failures remain visible.' if self.qualified else 'The final verification record supports release of the checked computational results. Scientific limitations and stress failures remain visible.'))
        self.h('Files that define this document')
        self.table(['Input','Purpose'],[
            ['protocol.json','Prespecified scenario, calibration, observation and policy rules'],['revision_model.py / dynamics.py','Implemented diagnosis and continuous physical truth/branching'],
            ['POLICY_AMENDMENT.txt / revision_policy.py','Preserved pre-evaluation correction to the restoration target'],
            ['results/diagnosis_summary.csv','Per-cell diagnostic counts, rates and uncertainty'],['results/policy_summary.csv','Per-policy physical outcome summaries'],
            ['results/policy_paired_differences.csv','Paired active-minus-passive physical contrasts'],
            ['results/summary.json','Campaign completion and selected checked result summary'],['checks/final_check.json','Independent numerical/integrity gate'],
            ['report/document_input_manifest.json','Exact input hashes and PDF/content hashes for this build'],
        ],[183,WIDTH-183])
        self.p('The PDF is generated from these inputs. A final build requires campaign completion, an explicit final checker acceptance with any qualification preserved, and matching current input hashes. The exact final-check file, result files and forensic bindings are recorded in the document manifest. Partial campaign numbers are not used to fill result pages. All pages are rendered for visual review and automatic text-bound checks.')
        self.h('Interpretation rules retained in every release')
        self.p('Pointwise episode-level intervals are not simultaneous guarantees across the scenario map. Descriptive ranges are not pooled population rates. Records without calls stay outside conditional timing summaries and are not assigned a successful delay. Out-of-family faults have no supported true cause label. Physical costs retain their own units; no assumed price-weighted benefit or isolated information value is reported.')
        self.p('The original archive, previous audit and complete rerun remain separate historical evidence. This revision does not rewrite their outcomes or manufacture a preregistration history. Source freezes demonstrate the recorded sequence only to the extent supported by the saved manifests and execution records.','small')

    def footer(self,canvas,doc):
        canvas.saveState(); canvas.setStrokeColor(colors.HexColor('#CAD7DF')); canvas.setLineWidth(.6)
        canvas.line(50,PAGE_H-39,PAGE_W-50,PAGE_H-39)
        canvas.setFillColor(MUTED); canvas.setFont('Body',8)
        canvas.drawString(50,PAGE_H-30,'SSMR | Scientific revision | Simulation evidence')
        canvas.drawRightString(PAGE_W-50,PAGE_H-30,'DRAFT - RESULTS WITHHELD' if self.draft else ('QUALIFIED COMPUTATIONAL REPORT' if self.qualified else 'CHECKED COMPUTATIONAL REPORT'))
        canvas.line(50,38,PAGE_W-50,38)
        canvas.drawString(50,25,'30 September 2026  |  Scope and limitations form part of every result')
        canvas.drawRightString(PAGE_W-50,25,str(doc.page))
        canvas.restoreState()

    def build(self):
        self.content()
        out=self.root/'output/pdf'; out.mkdir(parents=True,exist_ok=True)
        stem='SSMR_MAJOR_REVISION_DRAFT' if self.draft else 'SSMR_MAJOR_REVISION'
        pdf=out/(stem+'.pdf')
        doc=SimpleDocTemplate(str(pdf),pagesize=A4,rightMargin=50,leftMargin=50,topMargin=57,bottomMargin=52,
                              title='SSMR: diagnosing deterioration before choosing a feed action',author='Research revision and internal evidence review',pageCompression=1)
        doc.build(self.story,onFirstPage=self.footer,onLaterPages=self.footer)
        changed=[rel for rel,value in self.inputs.items() if not (self.root/rel).is_file() or sha(self.root/rel)!=value]
        if changed:raise SystemExit('Report inputs changed during generation: '+', '.join(changed))
        qa=self.root/'report/qa'/stem; qa.mkdir(parents=True,exist_ok=True)
        result=check_and_render(pdf,qa)
        manifest={'generated_utc':datetime.now(timezone.utc).isoformat(),'draft':self.draft,'verified_input_gate':self.verified,
                  'gate_issues':self.gate_issues,'inputs':self.inputs,'pdf':str(pdf),'pdf_sha256':sha(pdf),'qa':result,
                  'generator_sha256':sha(__file__),'claim_ledger':self.claims}
        (self.root/'report/document_input_manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
        print(json.dumps({'pdf':str(pdf),'pages':result['pages'],'bounds_pass':result['bounds_pass'],'draft':self.draft},indent=2))
        if not result['bounds_pass']: raise SystemExit('PDF text-bound QA failed')


def check_and_render(pdf,folder):
    doc=fitz.open(pdf); issues=[]; texts=[]; thumbs=[]
    for i,page in enumerate(doc):
        text=page.get_text(); texts.append(text)
        for block in page.get_text('dict')['blocks']:
            for line in block.get('lines',[]):
                for span in line['spans']:
                    x0,y0,x1,y1=span['bbox']
                    if x0 < 35 or y0 < 12 or x1 > page.rect.width-35 or y1 > page.rect.height-12:
                        issues.append({'page':i+1,'text':span['text'],'bbox':span['bbox']})
        png=folder/f'page_{i+1:02d}.png'; page.get_pixmap(matrix=fitz.Matrix(2,2),alpha=False).save(png)
        im=Image.open(png).convert('RGB'); im.thumbnail((397,562)); thumbs.append(im)
    for start in range(0,len(thumbs),6):
        group=thumbs[start:start+6]; sheet=Image.new('RGB',(834,3*590+20),'#dce3e7'); draw=ImageDraw.Draw(sheet)
        for j,im in enumerate(group):
            x=15+(j%2)*412; y=15+(j//2)*590; sheet.paste(im,(x,y)); draw.text((x+8,y+565),f'Page {start+j+1}',fill='black')
        sheet.save(folder/f'contact_{start//6+1:02d}.png')
    (folder/'extracted_text.txt').write_text('\n\n'.join(f'--- PAGE {i+1} ---\n{t}' for i,t in enumerate(texts)),encoding='utf-8')
    result={'pages':len(doc),'bounds_pass':not issues,'bounds_issues':issues,'rendered_all_pages':True,'visual_inspection':'PENDING HUMAN/AGENT IMAGE INSPECTION','minimum_body_size_pt':10.2}
    (folder/'qa.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    return result


def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--root',type=Path,default=ROOT); ap.add_argument('--draft',action='store_true')
    args=ap.parse_args(); Document(args.root,args.draft).build()


if __name__=='__main__': main()
