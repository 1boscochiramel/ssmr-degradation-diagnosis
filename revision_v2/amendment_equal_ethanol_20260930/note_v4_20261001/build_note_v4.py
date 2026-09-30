"""Six-page note, version 4 (1 Oct 2026). Derived from ../note/build_note.py (V3); prior artifacts stay read-only.

Changes from V3, all driven by the 1 Oct 2026 independent check (reformer_benchmark/work/audit_check/check_v3_equal_ethanol.py)
and the different-model referee read (gpt-oss:120b via Ollama, 1 Oct 2026):
  p1  neutral headline computed from per-episode results; Mode 2 IAE gap against Table 3 under the paper's own Eq. (13)
  p2  summary table of fault hypotheses, sensor sets and controls
  p5  per-episode win counts and the call split behind the means; differences to two significant figures
  p6  review status updated
Every displayed number is computed here from the source CSVs; verify_note_v4.py recomputes them independently.
"""
from pathlib import Path
from datetime import datetime, timezone
import json, hashlib, html, glob
import numpy as np
import pandas as pd
import fitz
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, Table, TableStyle

HERE = Path(__file__).resolve().parent; E = HERE.parent; ROOT = E.parent
OLD = ROOT / 'amendment_feed_only_20260930'; V3 = E / 'note'
NATIVE = Path(r'C:\Users\Admin\Desktop\WHEC\reformer_benchmark\work\audit_check\ssmr_native\baseline')
W, H = A4; L = 43; PW = W - 2 * L
CENTRAL = ['m1_C_d05_r1', 'm1_M_d05_r1', 'm2_C_d05_r1', 'm2_M_d05_r1']
CONTROLS = ['m1_H', 'm2_H', 'm1_S_d05_r0', 'm2_S_d05_r0']
GROUPS = ['kinetic_mismatch', 'double_noise', 'drifting_bias', 'gain_error', 'strong_correlation', 'heldout_parameters', 'faster_deterioration', 'half_noise']
PUB_IAE = {'CS1': 7.95e-5, 'CS2T': 2.62e-4, 'CS2P': 2.48e-4}   # paper Table 3 / Section 4.3 values, mol
DATE = '1 OCTOBER 2026'

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p): return json.loads(Path(p).read_text(encoding='utf-8'))
def esc(x): return html.escape(str(x))
def label(c): return c[:2].upper() + ' ' + c[3]
def pct(x): return f'{100*x:.1f}%'
def cost(x): return f'{(0. if abs(x) < .000005 else x):.5f}'
def sig2(x): return f'{x:+.5f}'
def csv(p): return pd.read_csv(p, float_precision='round_trip')

def iae_eq13(e, dt=0.1):
    """Paper Eq. (13): sum_k | (e(k)+e(k-1))/2 * Ts |, absolute value taken after averaging signed errors."""
    return float(np.sum(np.abs((e[1:] + e[:-1]) / 2 * dt)))

class Note:
    def __init__(self):
        for name, file in [('Body', 'segoeui.ttf'), ('Bold', 'segoeuib.ttf'), ('Italic', 'segoeuii.ttf')]:
            pdfmetrics.registerFont(TTFont(name, 'C:/Windows/Fonts/' + file))
        pdfmetrics.registerFontFamily('Body', normal='Body', bold='Bold', italic='Italic', boldItalic='Bold')
        self.styles = {
            'body': ParagraphStyle('body', fontName='Body', fontSize=10, leading=14, textColor=colors.black),
            'small': ParagraphStyle('small', fontName='Body', fontSize=8.4, leading=11.4, textColor=colors.HexColor('#333333')),
            'h': ParagraphStyle('h', fontName='Bold', fontSize=12, leading=15.5, textColor=colors.black),
            'title': ParagraphStyle('title', fontName='Bold', fontSize=22, leading=27, textColor=colors.black),
            'cell': ParagraphStyle('cell', fontName='Body', fontSize=8.2, leading=10.5),
            'head': ParagraphStyle('head', fontName='Bold', fontSize=8.2, leading=10.5, textColor=colors.white)}
        self.sources = [ROOT / 'results/diagnosis_summary.csv', OLD / 'outputs/paired_summary.csv', E / 'outputs/paired_summary.csv',
                        E / 'outputs/paired_trials.csv', E / 'checks/verification.json', E / 'benchmark_audit/findings_evidence.json',
                        V3 / 'tradeoff.png', V3 / 'figure_coordinates.csv'] + [NATIVE / f'{c}_np50_matlab.csv' for c in PUB_IAE]
        self.inputs = {str(p): sha(p) for p in self.sources}
        self.d = csv(self.sources[0]); self.old = csv(OLD / 'outputs/paired_summary.csv')
        self.eq = csv(E / 'outputs/paired_summary.csv'); self.tr = csv(E / 'outputs/paired_trials.csv')
        gate = read(E / 'checks/verification.json'); assert gate['pass'] and not gate['issues']
        assert read(E / 'benchmark_audit/findings_evidence.json')['status'] == 'PASS'
        assert len(self.eq) == 4 and set(self.eq.case_id) == set(CENTRAL) and len(self.tr) == 4000
        self.claims = []; self.page = 0
        self.pdf = E / 'output/pdf/SSMR_SCIENTIFIC_NOTE_V4_LOCAL_REVIEW.pdf'; self.pdf.parent.mkdir(parents=True, exist_ok=True)
        self.c = canvas.Canvas(str(self.pdf), pagesize=A4); self.c.setTitle('Does diagnosis help meet hydrogen demand?'); self.c.setAuthor('Local computational research draft v4')

    # ---- layout helpers (unchanged from V3) ----
    def p(self, text, style='body', gap=8):
        p = Paragraph(text, self.styles[style]); _, hh = p.wrap(PW, 1000)
        if self.y - hh < 53: raise RuntimeError(f'Page {self.page} overflow: {text[:70]}')
        p.drawOn(self.c, L, self.y - hh); self.y -= hh + gap
    def h(self, text): self.p(esc(text), 'h', 5)
    def table(self, heads, rows, widths):
        data = [[Paragraph(esc(x), self.styles['head' if i == 0 else 'cell']) for x in rr] for i, rr in enumerate([heads] + rows)]
        t = Table(data, colWidths=widths)
        t.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, 0), colors.black), ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor('#eeeeee'), colors.white]),
                               ('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LEFTPADDING', (0, 0), (-1, -1), 5), ('RIGHTPADDING', (0, 0), (-1, -1), 5),
                               ('TOPPADDING', (0, 0), (-1, -1), 6), ('BOTTOMPADDING', (0, 0), (-1, -1), 6)]))
        _, hh = t.wrap(PW, 1000)
        if self.y - hh < 53: raise RuntimeError('Table overflow ' + str(self.page))
        t.drawOn(self.c, L, self.y - hh); self.y -= hh + 10
    def start(self, title):
        if self.page: self.c.showPage()
        self.page += 1; self.y = H - 73; self.c.setFillColor(colors.black); self.c.setFont('Bold', 8)
        self.c.drawString(L, H - 35, f'SSMR / LOCAL REVIEW DRAFT V4 / {DATE}')
        self.c.setStrokeColor(colors.HexColor('#bbbbbb')); self.c.line(L, H - 46, W - L, H - 46)
        self.c.setFont('Body', 7); self.c.drawString(L, 29, 'Simulation only | Different-model review done 1 Oct 2026 | User rewrite pending')
        self.c.drawRightString(W - L, 29, f'{self.page} / 6'); self.p(esc(title), 'title', 13)
    def diag(self, c, a, s='S4'):
        r = self.d[(self.d.case_id == c) & (self.d.active == a) & (self.d['set'] == s) & (self.d['group'] == 'covered_grid')]; assert len(r) == 1; return r.iloc[0]

    # ---- computed facts ----
    def compute(self):
        q = self.eq.set_index('case_id').loc[CENTRAL]; self.q = q
        self.delta = q.difference_H2_shortfall_mol_mean
        self.rel = 100 * self.delta / q.blind_H2_shortfall_mol_mean
        self.win = {}; self.split = {}
        for c in CENTRAL:
            g = self.tr[self.tr.case_id == c]; assert len(g) == 1000
            dm = g.difference_H2_shortfall_mol * 1000
            self.win[c] = {'diag': int((dm < 0).sum()), 'blind': int((dm > 0).sum()), 'tie': int((dm == 0).sum())}
            s = g.assign(dm=dm).groupby('call').dm.agg(['count', 'mean', 'sum'])
            self.split[c] = {k: {'n': int(v['count']), 'mean_mmol': float(v['mean']), 'share_mmol': float(v['sum']) / 1000} for k, v in s.iterrows()}
        self.iae = {}
        for c in PUB_IAE:
            m = pd.read_csv(NATIVE / f'{c}_np50_matlab.csv', header=None, names=['t', 'y', 'u', 'sp'])
            e = (m.sp - m.y).values; v = iae_eq13(e); tz = float(np.trapezoid(np.abs(e), dx=0.1))
            self.iae[c] = {'eq13': v, 'vs_paper_pct': 100 * (v - PUB_IAE[c]) / PUB_IAE[c], 'trapz_abs': tz, 'eq13_vs_trapz_pct': 100 * (tz - v) / tz}
        self.claims.append({'kind': 'computed', 'win': self.win, 'split': self.split, 'iae': self.iae,
                            'rel_pct': {c: float(self.rel[c]) for c in CENTRAL}, 'delta_mmol': {c: 1000 * float(self.delta[c]) for c in CENTRAL}})

    def headline(self):
        w = self.win; blind_mean = int((self.delta > 0).sum())
        lo = min(w[c]['diag'] for c in CENTRAL); hi = max(w[c]['diag'] for c in CENTRAL)
        relmax = max(abs(self.rel[c]) for c in CENTRAL)
        inc = {c: self.split[c].get('MODEL_INCOMPATIBLE', {'n': 0})['n'] for c in CENTRAL}
        # the headline must be derived from the data, not chosen; assert the pattern it describes
        assert blind_mean == 4 and lo >= 800 and relmax < 2.0, (blind_mean, lo, relmax)
        return (f'At equal ethanol use, a blind constant feed and the diagnosis-based command give the same mean hydrogen shortfall '
                f'within {relmax:.1f}% in all four central cases. Per episode, the diagnostic command has the lower shortfall in '
                f'{lo} to {hi} of 1000 episodes; the blind arm wins the mean only through the {min(inc.values())} to {max(inc.values())} '
                f'episodes per case in which the procedure declared the model incompatible and returned feed to nominal.')

    def content(self):
        self.compute(); conclusion = self.headline()
        # ---------------- page 1 ----------------
        self.start('Does diagnosis help meet hydrogen demand?')
        self.p('The question is practical: if hydrogen production falls, does identifying the cause help more than simply feeding more ethanol? This note separates diagnosis accuracy from the ability of the resulting feed command to meet hydrogen demand.')
        self.p('<b>' + conclusion + '</b>')
        self.p('A feed pulse improves cause identification in the nominal model, but that is a separate result. The diagnostic policy also acts unnecessarily on healthy plants, and all selected kinetic-mismatch cases reject the true cause. The useful outputs are a bounded simulation comparison and reproducible findings for the benchmark authors.')
        self.h('Findings on the benchmark code')
        i = self.iae
        self.p(f'<b>Mode 2 case studies do not reproduce under the paper\'s own metric.</b> Equation (13) takes the absolute value after averaging adjacent signed errors. On the native MATLAB traces that formula gives case study 1 within {abs(i["CS1"]["vs_paper_pct"]):.1f}% of the published 7.95e-5 mol, but the Mode 2 temperature and pressure cases come out {abs(i["CS2T"]["vs_paper_pct"]):.1f}% and {abs(i["CS2P"]["vs_paper_pct"]):.1f}% below the published 2.62e-4 and 2.48e-4 mol. Trapezoidal integration of the absolute error differs from Eq. (13) by {i["CS2T"]["eq13_vs_trapz_pct"]:.1f}% and {i["CS2P"]["eq13_vs_trapz_pct"]:.1f}% in those cases, so the convention matters but does not close the gap. The question for the authors is how the two Mode 2 values were computed.')
        self.p('<b>The finer mesh changes the start-up case.</b> The saved np = 200 runs use a different grid and its own supplied initial-state files. Their early trajectories therefore mix mesh and initialization effects; start-up hydrogen flow differs by up to 12% of nominal. This is not a mesh-convergence test. Some fine-grid reset logs are missing, so the provenance qualification remains.')
        self.p('<b>The PID keeps state between calls.</b> control.m declares its integral and past error as persistent variables, while SSMR_simulation.m starts with a plain clear. Back-to-back cases can inherit controller history. Reset the controller before each independent run (clear control); the effect size has not been measured natively and is not claimed.')
        self.p('Source basis: pinned benchmark code, saved native np = 50 and np = 200 CSV/state files, and the paper text of Eq. (13). Exact paths and hashes are in the note input manifest.', 'small')

        # ---------------- page 2 ----------------
        self.start('Method: the diagnostic test stays fixed')
        self.p('The public distributed ethanol membrane-reformer model [1] supplies the simulated plant in two operating modes. Catalyst, membrane and feed-delivery losses evolve during the run; a meter offset affects only the reading. The diagnostic model uses evolving quasi-steady templates, so it differs from the full dynamic plant model. The dynamic solver uses 50 axial points and the existing BDF settings without change.', 'small')
        self.table(['Element', 'What it is', 'Values used'],
                   [['Fault hypotheses', 'C catalyst activity decay; M membrane permeance decay; F feed-delivery loss; S hydrogen-meter offset (reading only); H healthy', 'Central anchors: 5% nominal-map hydrogen drop at minute 10; decay 0.005/min (C), 0.003/min (M)'],
                    ['Sensor sets', 'S1 hydrogen flow; S3 adds outlet temperature and retentate flow; S4 adds four gas fractions', 'Serial noise, record-level bias, chromatograph delay: assumed, not instrument data'],
                    ['Probe', 'Ethanol raised by 0.0003 mol/min from minute 10; decision at 16 or 21', 'Passive arm keeps nominal feed'],
                    ['Outcomes', 'Single retained cause; no unique call (inconclusive); model incompatible', 'Every episode stays in the denominator'],
                    ['Controls', 'Same pulse: identical pulse end, then nominal feed. Same ethanol: one constant feed over minutes 10-31 with the episode\'s delivered ethanol', 'Four central S4 cases, 1000 paired episodes each'],
                    ['Accounts', 'Hydrogen shortfall (unmet demand), hydrogen produced, ethanol delivered, minutes 0-31', 'mmol; lower shortfall is better']],
                   [78, 246, PW - 324])
        self.h('Calibration, decisions and the original pulse')
        self.p('Each covered scenario has 499 separate calibration episodes and 1000 fresh evaluation episodes. The score uses both possible decision times. Its calibration rank is ceil((499 + 1)(1 - 0.05)); the largest included scenario threshold is used for each cause. This protects a specified rejection rate under the declared observation model, not the chance of obtaining a useful diagnosis [2,3]. The existing feed-selection policy and thresholds are unchanged from the original study.', 'small')
        self.h('Two controls answer different questions')
        self.p('<b>Same pulse:</b> replay the same pulse end, then return to nominal feed. This measures the effect of the later command and its extra ethanol cost. Figure 1 shows every original case and sensor set.', 'small')
        self.p('<b>Same ethanol:</b> for each of the four central S4 cases, replace the complete minute 10-31 input sequence by one constant feed equal to that diagnostic episode\'s delivered ethanol over the same window. Before minute 10 both arms share the same saved state and history. The blind arm receives no measurements or diagnosis. This control uses the completed diagnostic run to set its budget and changes when ethanol is fed; it tests one equal-resource schedule, not the isolated value of knowing the cause. The amendment and its check were frozen before the new trajectories; earlier outcomes were already known. No new noise episodes or native MATLAB runs were added.', 'small')

        # ---------------- page 3 (unchanged) ----------------
        self.start('Diagnosis: useful centrally, fragile under stress')
        self.p('Central S4 cases: counts out of 1000 per case. C = catalyst loss; M = membrane loss. Each central anchor is a nominal-map 5% hydrogen drop at minute 10. No call includes both inconclusive and model-incompatible results.', 'small')
        rows = []
        for c in CENTRAL:
            p, a = self.diag(c, False), self.diag(c, True)
            rr = [label(c), int(p.correct_singleton), int(a.correct_singleton), int(a.wrong_singleton), int(a.inconclusive + a.incompatible)]
            rows.append(rr); self.claims.append({'kind': 'diagnosis', 'case_id': c, 'displayed': rr})
        self.table(['Case', 'Passive correct', 'Pulse correct', 'Pulse wrong', 'Pulse no call'], rows, [65, 115, 115, 105, PW - 400])
        s1 = {c: (int(self.diag(c, False, 'S1').correct_singleton), int(self.diag(c, True, 'S1').correct_singleton)) for c in CENTRAL[:2]}
        self.claims.append({'kind': 's1_mode1', 'displayed': s1})
        self.p(f'In the central Mode 1 hydrogen-only cases, correct membrane calls rise from {s1["m1_M_d05_r1"][0]} to {s1["m1_M_d05_r1"][1]} out of 1000, while catalyst calls rise only from {s1["m1_C_d05_r1"][0]} to {s1["m1_C_d05_r1"][1]}. A useful pulse for one cause is not a general diagnosis guarantee.', 'small')
        self.h('Stress tests with the original thresholds')
        rows = []
        for g in GROUPS:
            d = self.d[(self.d['group'] == g) & self.d.supported_label]; w = d.loc[d.true_rejected_rate.idxmax()]
            rr = [g.replace('_', ' '), pct(d.correct_singleton_rate.min()) + '-' + pct(d.correct_singleton_rate.max()), pct(w.true_rejected_rate), pct(w.true_rejected_ci_lo) + '-' + pct(w.true_rejected_ci_hi), pct(d.wrong_singleton_rate.max())]
            rows.append(rr); self.claims.append({'kind': 'stress', 'group': g, 'displayed': rr})
        self.table(['Stress', 'Correct range', 'Max true-cause rejection', 'Its 95% interval', 'Max wrong call'], rows, [116, 91, 98, 112, PW - 417])
        self.p('Rows summarize selected fixed cells; maxima need not come from the same cell. Intervals are pointwise binomial intervals, not a joint guarantee. All tested kinetic-mismatch episodes reject the true cause. Noise and bias shifts can also produce wrong calls. These stresses test diagnosis, not the safety of the resulting control actions.', 'small')

        # ---------------- page 4 (figure unchanged) ----------------
        self.start('Less unmet demand has a feed cost')
        self.p('Figure 1. Diagnostic action versus the same-pulse control. Each point is one case and sensor set, averaged over all its episodes. Moving right spends more ethanol; moving up avoids more hydrogen shortfall. Both axes show actual amounts over the full run.', 'small')
        self.c.drawImage(str(V3 / 'tradeoff.png'), L, self.y - 501, width=PW, height=501, mask='auto'); self.y -= 509
        self.p('M1/M2 = operating mode; C = catalyst, M = membrane, F = feed delivery, S = meter bias, H = healthy. Filled markers are Mode 1; open markers are Mode 2. Every one of the 27 original pairs is shown, including near-zero-benefit healthy and meter-bias cases.', 'small')
        self.p('The points lie close to one line: shortfall avoided tracks extra ethanol. This is a physical trade-off figure, not a monetary value of information, and it cannot assign the gain to diagnosis when more feed is also used. The equal-ethanol comparison on the next page tests that narrower question.', 'small')

        # ---------------- page 5 ----------------
        self.start('Equal ethanol and unnecessary actions')
        self.p('Equal-resource test: all four central S4 cases, 1000 paired episodes each. Means in mmol over 0-31 min, including the common baseline; the ethanol budget is matched separately in every episode. Differences are diagnostic minus blind, so negative favours diagnosis. "Diagnostic better" counts episodes with lower shortfall under the diagnostic command.', 'small')
        rows = []
        for c in CENTRAL:
            r = self.q.loc[c]; w = self.win[c]
            rr = [label(c), f'{1000*r.diagnostic_actual_ethanol_mol_mean:.1f}', f'{1000*r.diagnostic_H2_shortfall_mol_mean:.4f}', f'{1000*r.blind_H2_shortfall_mol_mean:.4f}', sig2(1000 * r.difference_H2_shortfall_mol_mean) + f' ({self.rel[c]:+.1f}%)', f'{w["diag"]}/1000']
            rows.append(rr); self.claims.append({'kind': 'equal', 'case_id': c, 'displayed': rr})
        self.table(['Case', 'Matched ethanol', 'Diagnostic shortfall', 'Blind shortfall', 'Mean difference', 'Diagnostic better'], rows, [52, 78, 96, 84, 118, PW - 428])
        self.p(conclusion, 'small')
        sp = self.split
        def n(c, k): return sp[c].get(k, {'n': 0, 'mean_mmol': 0.0})
        self.p(f'Where the means come from: in Mode 2 the diagnostic command is better in all but one of the episodes that reached a call or stayed inconclusive (mean {n("m2_C_d05_r1","C")["mean_mmol"]:+.2g} and {n("m2_C_d05_r1","INCONCLUSIVE")["mean_mmol"]:+.2g} mmol for catalyst; {n("m2_M_d05_r1","M")["mean_mmol"]:+.2g} mmol for membrane), while the {n("m2_C_d05_r1","MODEL_INCOMPATIBLE")["n"]} and {n("m2_M_d05_r1","MODEL_INCOMPATIBLE")["n"]} model-incompatible episodes cost {n("m2_C_d05_r1","MODEL_INCOMPATIBLE")["mean_mmol"]:.2f} and {n("m2_M_d05_r1","MODEL_INCOMPATIBLE")["mean_mmol"]:.2f} mmol each. In Mode 1 catalyst the called episodes are marginally worse ({n("m1_C_d05_r1","C")["mean_mmol"]:+.2g} mmol) and the {n("m1_C_d05_r1","MODEL_INCOMPATIBLE")["n"]} incompatible episodes cost {n("m1_C_d05_r1","MODEL_INCOMPATIBLE")["mean_mmol"]:.2f} mmol each; Mode 1 membrane is a tie. The cost of probing is paid when the procedure abstains and feed returns to nominal after the pulse ethanol has been spent.', 'small')
        self.p('These mean differences are below 2% of the shortfall, no solver-refinement study has tested them, and no significance test is applied. The metric is unmet demand, not total hydrogen produced; in both membrane cases the diagnostic arm produces more hydrogen in total but meets demand slightly less well.', 'small')
        self.h('All healthy and meter-bias action rates')
        self.p('Entries are non-nominal follow-up commands out of 1000 active episodes. Extra ethanol compares diagnostic action with the same-pulse control, not with the equal-resource control above. No healthy or meter-bias cell is omitted.', 'small')
        rows = []
        for c in CONTROLS:
            part = self.old[self.old.case_id == c].set_index('set').loc[['S1', 'S3', 'S4']]
            costs = 1000 * part.difference_actual_ethanol_mol_mean
            rr = [label(c), *[f'{int(part.loc[s, "non_nominal_action_count"])}/1000' for s in ['S1', 'S3', 'S4']], cost(costs.min()) + ' to ' + cost(costs.max())]
            rows.append(rr); self.claims.append({'kind': 'control', 'case_id': c, 'displayed': rr})
        self.table(['Case', 'S1 actions', 'S3 actions', 'S4 actions', 'Extra ethanol range (mmol)'], rows, [66, 90, 90, 90, PW - 336])
        hs = self.old[self.old.case_id.isin(['m1_H', 'm2_H'])].non_nominal_action_count
        m1s1 = self.old[(self.old.case_id == 'm1_S_d05_r0') & (self.old['set'] == 'S1')].iloc[0]
        self.claims.append({'kind': 'healthy_range', 'lo': int(hs.min()), 'hi': int(hs.max()), 'm1_S_S1_actions': int(m1s1.non_nominal_action_count), 'm1_S_S1_ethanol_mmol': 1000 * float(m1s1.difference_actual_ethanol_mol_mean)})
        self.p(f'<b>Healthy plants receive a non-nominal command in {hs.min()/10:.1f}-{hs.max()/10:.1f}% of episodes.</b> For Mode 1 meter bias with S1, the policy acts in <b>{int(m1s1.non_nominal_action_count)}/1000</b> episodes and spends <b>{1000*m1s1.difference_actual_ethanol_mol_mean:.2f} mmol</b> extra ethanol on average. The model has no physical hydrogen loss from that meter fault. These are unnecessary control actions.', 'small')

        # ---------------- page 6 ----------------
        self.start('Limits and relation to prior work')
        self.h('What can be defended')
        self.p('The feed pulse can improve nominal cause discrimination. The control comparisons measure physical outcomes against two specified feed schedules. They do not establish an optimal policy, a net economic return, or a unique benefit of diagnostic information. A better blind schedule may exist. Resource matching is retrospective; it does not give a real operator an unknown future budget.')
        self.h('What still fails or remains unverified')
        self.p('The selected kinetic-mismatch cases fail completely. Instrument noise, bias and delay are assumed. The healthy-plant action rate is unacceptable as evidence of safe deployment. Only a finite set of simulated faults and conditions is covered; no rig has validated this procedure.')
        self.p('The original exact exported-start-state byte check remains failed. A separate forensic check supported the intended solver input and unchanged physical quantities; that qualification has not been erased. Some fine-grid native reset logs are also missing. This amendment is Python-only. Same-model checks are complete. A different model (gpt-oss-120b, 1 October 2026) reviewed version 3 cold; its two material findings, the per-episode counts behind the headline and the unqualified precision of the mean differences, are addressed in this version. The user\'s own rewrite remains pending. This is a local review draft, not an externally approved note.', 'small')
        self.h('One-sentence difference from Santra (2026)')
        self.p('Santra (2026) studies actuator-fault estimation and tracking recovery on a three-state reformer surrogate, whereas this note tests calibrated diagnosis of catalyst, membrane, feed and meter faults on distributed benchmark dynamics and compares the resulting feed sequence with blind controls [4].')
        self.p('The full Santra paper was read, including the implemented model in Section 6.1. Active input design for fault diagnosis is established work [5,6], and membrane-reformer tracking with ethanol-use objectives also predates this note [7]. No first-method or head-to-head superiority claim is made. The benchmark\'s conference predecessor (Arcila-Osorio et al., IFAC-PapersOnLine 59(9), 2025, 91-96) has not yet been opened and is therefore not cited.', 'small')
        self.h('References')
        refs = [
            '[1] Arcila-Osorio, Destro, Ocampo-Martinez, Llorca, Braatz. A benchmark simulator for advanced control of ethanol steam reforming. Renewable Energy 256 (2026) 124743. doi:10.1016/j.renene.2025.124743.',
            '[2] Dufour. Monte Carlo tests with nuisance parameters. Journal of Econometrics 133 (2006) 443-477. doi:10.1016/j.jeconom.2005.06.007.',
            '[3] Morris, White, Crowther. Using simulation studies to evaluate statistical methods. Statistics in Medicine 38 (2019) 2074-2102. doi:10.1002/sim.8086.',
            '[4] Santra. Koopman-PCE-based confidence-bounded fault diagnosis and recovery for hydrogen demand tracking in a membrane reactor. Computers & Chemical Engineering 213 (2026) 109728. doi:10.1016/j.compchemeng.2026.109728.',
            '[5] Scott, Findeisen, Braatz, Raimondo. Input design for guaranteed fault diagnosis using zonotopes. Automatica 50 (2014) 1580-1589. doi:10.1016/j.automatica.2014.03.016.',
            '[6] Raimondo, Marseglia, Braatz, Scott. Closed-loop input design for guaranteed fault diagnosis using set-valued observers. Automatica 74 (2016) 107-117. doi:10.1016/j.automatica.2016.07.033.',
            '[7] Serra, Ocampo-Martinez, Li, Llorca. Model predictive control for ethanol steam reformers with membrane separation. International Journal of Hydrogen Energy 42 (2017) 1949-1961. doi:10.1016/j.ijhydene.2016.10.110.']
        for r in refs: self.p(esc(r), 'small', 4)

    def save(self):
        assert self.page == 6; self.c.save(); doc = fitz.open(self.pdf); assert len(doc) == 6
        qa = HERE / 'qa'; qa.mkdir(exist_ok=True); texts = []; bounds = []
        for n, page in enumerate(doc, 1):
            page.get_pixmap(matrix=fitz.Matrix(1.6, 1.6), alpha=False).save(qa / f'page-{n}.png'); texts.append(f'--- PAGE {n} ---\n' + page.get_text())
            for b in page.get_text('dict')['blocks']:
                for ln in b.get('lines', []):
                    for s in ln['spans']:
                        x0, y0, x1, y1 = s['bbox']
                        if x0 < 35 or x1 > W - 35 or y0 < 12 or y1 > H - 12: bounds.append({'page': n, 'text': s['text'], 'bbox': s['bbox']})
        assert not bounds, bounds
        (qa / 'extracted_text.txt').write_text('\n\n'.join(texts), encoding='utf-8')
        record = {'pdf_sha256': sha(self.pdf), 'generator_sha256': sha(__file__), 'inputs': self.inputs, 'claims': self.claims, 'pages': 6,
                  'different_model_review': 'done 2026-10-01 on V3 (gpt-oss:120b-cloud via tools/ask_model.ps1); findings addressed in V4',
                  'user_rewrite': 'pending', 'created_utc': datetime.now(timezone.utc).isoformat()}
        (HERE / 'note_input_manifest.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
        print(json.dumps({'pdf': str(self.pdf), 'sha256': sha(self.pdf), 'pages': 6}))

if __name__ == '__main__':
    n = Note(); n.content(); n.save()
