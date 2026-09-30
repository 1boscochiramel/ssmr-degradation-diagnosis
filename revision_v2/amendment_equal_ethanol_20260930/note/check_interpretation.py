"""Check the final numeric interpretation against already frozen-audited rows."""
from pathlib import Path
import json,hashlib
import pandas as pd
import fitz
P=Path(__file__).resolve().parent;E=P.parent
src=E/'outputs/paired_summary.csv';d=pd.read_csv(src,float_precision='round_trip')
checks={'all_four_means_diagnostic_minus_blind_positive':bool((d.difference_H2_shortfall_mol_mean>0).all()),
        'every_case_has_trials_favoring_each_arm':bool(((d.difference_H2_shortfall_mol_min<0)&(d.difference_H2_shortfall_mol_max>0)).all()),
        'four_cases':len(d)==4,
        'M1_membrane_displayed_small_difference':f'{1000*d.loc[d.case_id=="m1_M_d05_r1","difference_H2_shortfall_mol_mean"].iloc[0]:+.6f}'=='+0.000027'}
pdf=E/'output/pdf/SSMR_SCIENTIFIC_NOTE_V3_LOCAL_REVIEW.pdf'
t=' '.join(' '.join(p.get_text().split()) for p in fitz.open(pdf))
checks['mean_wording_and_no_refinement_limit_printed']='calculated mean hydrogen shortfall' in t and 'No solver-refinement study' in t
checks['mixed_trial_direction_printed']='Every case contains episodes favoring each arm.' in t
membrane=d[d.case_id.isin(['m1_M_d05_r1','m2_M_d05_r1'])]
checks['membrane_total_production_and_shortfall_both_higher']=bool(((membrane.difference_H2_produced_mol_mean>0)&(membrane.difference_H2_shortfall_mol_mean>0)).all())
checks['headline_limited_to_shortfall']='mean hydrogen-shortfall advantage' in t and 'do not show a production advantage' not in t
checks['total_production_distinction_printed']='The metric is unmet demand, not total hydrogen produced.' in t
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
out={'pass':all(checks.values()),'checks':checks,'source_sha256':sha(src),'pdf_sha256':sha(pdf),'scope':'Interpretation of existing checked values only; no changed scientific acceptance gate'}
(P/'INTERPRETATION_CHECK.json').write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2));assert out['pass']
