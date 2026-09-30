"""Read-only diagnosis of frozen v1 dense-output endpoint record differences."""
from collections import defaultdict
import json
from pathlib import Path
import numpy as np
import pandas as pd
import dynamics as d

ROOT = Path(__file__).resolve().parent


def load(folder):
    meta = json.loads((folder / 'metadata.json').read_text())
    with np.load(folder / 'states.npz', allow_pickle=False) as z:
        states, times = z['states'].copy(), z['time_min'].copy()
    return meta, states, times, pd.read_csv(folder / 'truth.csv', float_precision='round_trip')


def endpoint(meta, state, row):
    sc = d.Scenario(**meta['scenario'])
    ac, am, fg, bias = sc.health(float(row.time_min))
    p = d.DynamicParameters(*d.MODES[sc.mode][:2], 50, a_c=ac, a_m=am, kinetic_scales=sc.kinetic_scales)
    return d.observables(d.evaluate(state, np.array([row.command_mol_min * fg, row.water_mol_min]), p)[1])


def main():
    parents, groups, records, costs = {}, defaultdict(list), [], []
    for folder in sorted((ROOT / 'dynamic_truth').iterdir()):
        meta, states, times, trace = load(folder)
        with np.load(folder / 'precondition_states.npz', allow_pickle=False) as z:
            expected = z['states'][-1].copy()
        parents[folder.name] = (meta, states, times, trace)
        groups[meta['state_sha256']].append(folder.name)
        records.append(compare(folder.name, 'truth', meta, states, trace, expected))
    for folder in sorted((ROOT / 'dynamic_branches').iterdir()):
        meta, states, times, trace = load(folder)
        record = json.loads((folder / 'dynamic_record.json').read_text())
        parent_key = record['result']['parent_key']
        pm, px, pt, ptr = parents[parent_key]
        idx = np.flatnonzero(np.isclose(pt, meta['parent_decision_min'], atol=1e-12, rtol=0.))
        assert len(idx) == 1
        expected = px[idx[0]]
        result = compare(folder.name, 'branch', meta, states, trace, expected)
        result['parent_key'] = parent_key
        result['scenario_matches_explicit_parent'] = meta['scenario'] == pm['scenario']
        result['parent_hash_matches_explicit_parent'] = meta['parent_state_sha256'] == pm['state_sha256']
        records.append(result)
    changed = [r for r in records if not r['first_state_bitwise_equal_to_intended_y0']]
    by_kind = {kind: [r for r in changed if r['kind'] == kind] for kind in ('truth', 'branch')}
    result = {'scope': 'Read-only diagnosis; no frozen engine, records, gates or checker edits',
        'records_checked': len(records), 'changed_counts': {k: len(v) for k, v in by_kind.items()},
        'max_first_state_abs_difference': max(r['state_max_abs_difference'] for r in records),
        'max_endpoint_H2_abs_difference_mol_min': max(abs(r['endpoint_H2_difference_mol_min']) for r in records),
        'max_first_interval_H2_amount_difference_mol': max(abs(r['first_interval_H2_amount_difference_mol']) for r in records),
        'max_first_interval_shortfall_difference_mol': max(abs(r['first_interval_shortfall_difference_mol']) for r in records),
        'all_explicit_parent_scenarios_match': all(r.get('scenario_matches_explicit_parent', True) for r in records),
        'all_explicit_parent_hashes_match': all(r.get('parent_hash_matches_explicit_parent', True) for r in records),
        'same_physical_trajectory_hash_groups': [v for v in groups.values() if len(v) > 1],
        'records': records}
    (ROOT / 'dynamic_dense_diagnosis.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: v for k, v in result.items() if k not in ('records', 'same_physical_trajectory_hash_groups')}, indent=2))


def compare(key, kind, meta, states, trace, expected):
    difference = states[0] - expected
    correct = endpoint(meta, expected, trace.iloc[0])
    old = float(trace.iloc[0].true_H2_mol_min)
    new = correct['H2_mol_min']
    dt = float(trace.iloc[1].time_min - trace.iloc[0].time_min)
    demand = float(trace.iloc[0].demand_mol_min)
    return dict(key=key, kind=kind, first_state_bitwise_equal_to_intended_y0=bool(np.array_equal(states[0], expected)),
        state_differing_components=int(np.count_nonzero(difference)),
        state_max_abs_difference=float(np.max(np.abs(difference))),
        state_max_scaled_difference=float(np.max(np.abs(difference) / np.maximum(1., np.abs(expected)))),
        endpoint_H2_difference_mol_min=float(new - old),
        first_interval_H2_amount_difference_mol=float(.5 * dt * (new - old)),
        first_interval_shortfall_difference_mol=float(.5 * dt * (max(demand - new, 0.) - max(demand - old, 0.))),
        endpoint_feature_abs_differences={f: abs(float(correct[f]) - float(trace.iloc[0]['true_' + f])) for f in d.FEATURES})


if __name__ == '__main__':
    main()
