"""Fresh release checks of the PDF, its source bindings and displayed result tables.

Visual inspection is recorded only when the caller explicitly supplies all pages
after viewing their renders; automated bounds checks are not visual inspection.
"""
from pathlib import Path
import argparse
import hashlib
import json
from datetime import datetime, timezone
import fitz
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--visual-pages', required=True)
    args = parser.parse_args()
    issues = []
    def need(test, description):
        if not test:
            issues.append(description)
    docinfo = json.loads((ROOT / 'report/document_input_manifest.json').read_text())
    check = json.loads((ROOT / 'checks/final_check.json').read_text())
    pdf = ROOT / 'output/pdf/SSMR_MAJOR_REVISION.pdf'
    need(check.get('complete') is True and check.get('computational_pass') is True,
         'Completed computational verification, with its explicit qualification, is required')
    need(docinfo.get('draft') is False and docinfo.get('verified_input_gate') is True,
         'Final document mode and input gate')
    need(sha(pdf) == docinfo['pdf_sha256'], 'PDF checksum matches build record')
    for rel, expected in docinfo['inputs'].items():
        need(sha(ROOT / rel) == expected, 'Document source binding: ' + rel)
    need(sha(ROOT / 'report/build_revision_document.py') == docinfo['generator_sha256'],
         'Document generator unchanged after build')
    pages = fitz.open(pdf)
    viewed = sorted({int(x) for x in args.visual_pages.split(',')})
    need(viewed == list(range(1, len(pages) + 1)), 'Every rendered page visually reviewed')
    need(len(pages) == docinfo['qa']['pages'], 'Rendered page count')
    text = '\n'.join(page.get_text() for page in pages)
    need('Results withheld in this draft' not in text and 'DRAFT - RESULTS WITHHELD' not in text,
         'No unreleased draft results in final PDF')
    need('\ufffd' not in text and '\x00' not in text, 'No replacement/null glyphs')
    need('inconclusive' in text.lower(), 'Abstention remains visible')
    need('feed-only' in text.lower(), 'Information-attribution limitation remains visible')
    need('original' in text.lower() and 'remains failed' in text.lower(),
         'Retained original exact-export failure remains visible')
    for i, page in enumerate(pages, 1):
        need(len(page.get_text().strip()) > 100, 'No blank/near-empty page ' + str(i))
        for block in page.get_text('dict')['blocks']:
            for line in block.get('lines', []):
                for span in line['spans']:
                    x0, y0, x1, y1 = span['bbox']
                    need(x0 >= 35 and y0 >= 12 and x1 <= page.rect.width - 35 and y1 <= page.rect.height - 12,
                         f'Page {i} text bounds: {span["text"]}')
    # Rebuild published ranges and physical contrasts from the checked CSVs.
    d = pd.read_csv(ROOT / 'results/diagnosis_summary.csv', float_precision='round_trip')
    p = pd.read_csv(ROOT / 'results/policy_paired_differences.csv', float_precision='round_trip')
    protocol = json.loads((ROOT / 'protocol.json').read_text())
    cases = {c['id']: c for c in protocol['cases']}
    central_ids = [c['id'] for c in cases.values() if c['policy'] and c['h'] in ['C', 'M']]
    central = d[(d.case_id.isin(central_ids)) & (d['group'] == 'covered_grid')]
    central_delta = central.pivot(index=['case_id', 'set'], columns='active', values='correct_singleton_rate')
    central_delta = central_delta[True] - central_delta[False]
    selected_policy = p[p.case_id.isin(central_ids)]
    percent = lambda x: f'{100*x:.1f}%'
    def rate_range(frame, name):
        return percent(frame[name].min()) + ' to ' + percent(frame[name].max())
    def check_cell(saved, label):
        part = d[(d.case_id == saved['case_id']) & (d['set'] == saved['set']) &
                 (d.active == (saved['active'] == 'True')) &
                 (d['group'] == saved['group']) & (d.phase == saved['phase'])]
        need(len(part) == 1, label + ' unique source cell')
        if len(part) != 1:
            return
        row = part.iloc[0]
        for field, expected in saved.items():
            value = row[field]
            if expected == '':
                need(pd.isna(value), label + '/' + field)
            elif expected in ['True', 'False']:
                need(bool(value) == (expected == 'True'), label + '/' + field)
            elif isinstance(value, str):
                need(value == expected, label + '/' + field)
            else:
                need(np.isclose(float(value), float(expected), rtol=1e-12, atol=1e-15), label + '/' + field)
    claims_checked = 0
    for claim in docinfo['claim_ledger']:
        section = claim['section']
        if section == 'diagnosis_ranges':
            f = claim['filter']
            part = d[(d['group'] == f['group']) & (d['set'] == f['set']) & (d.active == f['active'])]
            expected = [f['set'], 'Active' if f['active'] else 'Passive',
                        rate_range(part, 'correct_singleton_rate'),
                        rate_range(part, 'wrong_singleton_rate'), rate_range(part, 'true_rejected_rate')]
            need(expected == claim['displayed'], 'Displayed diagnosis range: ' + str(f))
            claims_checked += 1
        elif section == 'policy':
            row = p[(p.case_id == claim['case_id']) & (p['set'] == claim['set'])].iloc[0]
            expected = [f'{1000*row[field]:+.4f}' for field in
                        ['H2_shortfall_mol_difference_mean', 'actual_ethanol_mol_difference_mean',
                         'commanded_ethanol_mol_difference_mean']]
            need(expected == claim['displayed'][-3:], 'Displayed physical contrast: ' + claim['case_id'] + '/' + claim['set'])
            claims_checked += 1
        elif section == 'stress':
            part = d[(d['group'] == claim['group']) & d.supported_label]
            worst = part.loc[part.true_rejected_rate.idxmax()]
            expected = [claim['group'].replace('_', ' '), rate_range(part, 'correct_singleton_rate'),
                        percent(worst.true_rejected_rate), percent(worst.true_rejected_ci_lo) + ' to ' + percent(worst.true_rejected_ci_hi),
                        percent(part.wrong_singleton_rate.max())]
            need(expected == claim['displayed'], 'Displayed stress result: ' + claim['group'])
            claims_checked += 1
        elif section == 'central_case_readout':
            check_cell(claim['passive'], section + '/passive')
            check_cell(claim['active'], section + '/active')
            claims_checked += 1
        elif section in ['stress_wrong_boundary', 'stress_rejection_interpretation']:
            check_cell(claim['cell'], section)
            subset = d[(d['group'] != 'covered_grid') & d.supported_label]
            field = 'wrong_singleton_rate' if section == 'stress_wrong_boundary' else 'true_rejected_rate'
            need(float(claim['cell'][field]) == subset[field].max(), section + ' maximum')
            claims_checked += 1
        elif section == 'central_case_comparison':
            expected = {'higher': int((central_delta > 0).sum()), 'lower': int((central_delta < 0).sum()),
                        'same': int((central_delta == 0).sum()), 'comparisons': len(central_delta)}
            need(all(claim[k] == v for k, v in expected.items()), section)
            claims_checked += 1
        elif section == 'healthy_bias_physical_outcomes':
            row = p[(p.case_id == claim['case_id']) & (p['set'] == claim['set'])].iloc[0]
            expected = [f'{1000*row[field]:+.6g}' for field in
                        ['H2_shortfall_mol_difference_mean', 'actual_ethanol_mol_difference_mean']]
            need(expected == claim['displayed'][-2:], section + '/' + claim['case_id'])
            claims_checked += 1
        elif section == 'policy_signs':
            h = selected_policy.H2_shortfall_mol_difference_mean
            e = selected_policy.actual_ethanol_mol_difference_mean
            expected = {'comparisons': len(h), 'shortfall_reduced': int((h < 0).sum()),
                        'shortfall_increased': int((h > 0).sum()),
                        'reduced_with_more_ethanol': int(((h < 0) & (e > 0)).sum())}
            need(all(claim[k] == v for k, v in expected.items()), section)
            claims_checked += 1
        elif section == 'all_policy_ethanol_signs':
            need(claim['comparisons'] == len(p) and claim['actual_ethanol_increased'] == int((p.actual_ethanol_mol_difference_mean > 0).sum()), section)
            claims_checked += 1
        elif section == 'qualified_verification':
            need(claim['affected_records'] == check['dynamic_resolution']['affected_records'] and
                 claim['original_frozen_dynamic_gate_pass'] is False and
                 claim['resolution'] == check['dynamic_resolution']['status'], section)
            claims_checked += 1
        elif section == 'opening_guide':
            need(claim['value'] == int(((d['group'] == 'covered_grid') & (d.true_rejected_ci_lo > protocol['alpha'])).sum()), section)
            claims_checked += 1
        else:
            need(False, 'Unrecognized unverified claim ledger section: ' + section)
    result = {'pass': not issues, 'issues': issues, 'pdf_sha256': sha(pdf),
              'final_check_sha256': sha(ROOT / 'checks/final_check.json'),
              'pages': len(pages), 'visually_reviewed_pages': viewed,
              'reviewer': 'root; fresh source-binding, extracted-text, numerical-table and rendered-page review',
              'result_claim_ledger_entries_recomputed': claims_checked,
              'scope': 'Document release QA; scientific scope and retained frozen-gate failure are inherited explicitly from the checked report.',
              'created_utc': datetime.now(timezone.utc).isoformat()}
    (ROOT / 'report/FINAL_RELEASE_QA.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
    return int(bool(issues))


if __name__ == '__main__':
    raise SystemExit(main())
