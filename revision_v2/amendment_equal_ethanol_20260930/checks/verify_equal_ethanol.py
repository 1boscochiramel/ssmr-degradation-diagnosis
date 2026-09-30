"""Independent frozen checker for the retrospective equal-ethanol benchmark."""
from pathlib import Path
import argparse
import datetime
import hashlib
import json
import sys
import traceback
import numpy as np
import pandas as pd
from audit_math import (MEASURES, CENTRAL, BUDGET_ATOL, BUDGET_RTOL, close,
                        budget_ok, constant_command, resource_key, stats)
from audit_records import Records, sha, array_sha, read, csv

HERE = Path(__file__).resolve().parent

def audit_plan(root):
    root = Path(root).resolve(); parent = root.parent
    issues = []
    def need(ok, label):
        if not bool(ok): issues.append(label)
    def cmp(got, want, label): need(close(got, want), label)
    proto, old = read(root/'protocol.json'), read(parent/'protocol.json')
    inventory = read(root/'parent_inventory.json')
    for rel, info in inventory['files'].items():
        p = parent/rel
        need(p.is_file() and sha(p) == info['sha256'], 'Preserved parent/'+rel)
        need(p.is_file() and p.stat().st_size == info['bytes'], 'Parent size/'+rel)
    required_parent = ['dynamics.py', 'protocol.json', 'revision_model.py', 'revision_policy.py',
                       'statistical_campaign.py', 'checks/final_check.json', 'results/calibration.json',
                       'results/policy_trials.csv', 'results/policy_decisions.csv', 'results/diagnosis_summary.csv',
                       'amendment_feed_only_20260930/checks/verification.json']
    need(all(p in inventory['files'] for p in required_parent), 'Parent inventory covers original method and results')
    prior = read(parent/'checks/final_check.json')
    need(prior['complete'] and prior['computational_pass'] and prior['qualified'], 'Original qualified verification retained')
    need(prior['original_frozen_dynamic_gate_pass'] is False and prior['dynamic_resolution']['pass'], 'Original export failure and resolution retained')
    for key, rel in [('original_engine_sha256', 'dynamics.py'), ('original_protocol_sha256', 'protocol.json'), ('original_final_check_sha256', 'checks/final_check.json')]:
        need(proto[key] == sha(parent/rel), 'Protocol source binding/'+key)
    need(proto['amendment_text_sha256'] == sha(root/'PROTOCOL_AMENDMENT.txt'), 'Dated protocol text bound')
    expected_cases = [next(c for c in old['cases'] if c['id'] == name) for name in CENTRAL]
    need(proto['cases'] == expected_cases, 'Prespecified central cases, no selection')
    need(proto['sensor_sets'] == ['S4'] and proto['trials_per_case'] == old['n_evaluation'] == 1000, 'Unchanged S4 evaluation population')
    need(proto['budget_window_min'] == proto['constant_command_window_min'] == [10., 31.], 'Resource and command windows')
    need(proto['reporting_window_min'] == [0., 31.], 'Full reporting horizon')
    need(proto['bounds_mol_min'] == [.0018, .0024], 'Original physical bounds')
    need(proto['budget_atol_mol'] == BUDGET_ATOL and proto['budget_rtol'] == BUDGET_RTOL, 'Predeclared resource tolerance')
    need(set(proto['measures']) == set(MEASURES) and len(proto['measures']) == len(MEASURES), 'Complete physical measure vector')
    need(proto['new_noise_draws'] == 0 and proto['original_export_qualification_retained'], 'No new draws or erased qualification')
    schedules = read(root/'schedule_inventory.json')
    plans = schedules['schedules']
    need(len({p['schedule_id'] for p in plans}) == len(plans), 'Unique schedule identifiers')
    need(len({(p['case_id'], p['budget_float_hex']) for p in plans}) == len(plans), 'Exact resource deduplication')
    by_key = {(p['case_id'], p['budget_float_hex']): p for p in plans}
    by_id = {p['schedule_id']: p for p in plans}
    keys = ['case_id', 'set', 'trial_id']
    expected_keys = {(c, 'S4', i) for c in CENTRAL for i in range(1000)}
    prepared = csv(root/'trial_schedule_map.csv')
    need(not prepared.duplicated(keys).any() and set(map(tuple, prepared[keys].to_numpy())) == expected_keys, 'Exact prepared trial inventory')
    prepared = prepared.set_index(keys)
    decisions = csv(parent/'results/policy_decisions.csv')
    decisions = decisions[decisions.active & (decisions['set'] == 'S4') & decisions.case_id.isin(CENTRAL)]
    original = csv(parent/'results/policy_trials.csv')
    original = original[original.active & (original['set'] == 'S4') & original.case_id.isin(CENTRAL)]
    for name, frame in [('decisions', decisions), ('policy costs', original)]:
        need(not frame.duplicated(keys).any() and set(map(tuple, frame[keys].to_numpy())) == expected_keys, 'Original complete population/'+name)
    original = original.set_index(keys)
    records = Records(need, old['solver'])
    case_info, cost_cache, rebuilt, used = {}, {}, [], set()
    for c in expected_cases:
        case = c['id']; folder = parent/'dynamic_truth'/(case+'_active')
        record = records.load(folder)
        pm = record['meta']; need(pm['scenario']['mode'] == c['mode'] and pm['scenario']['hypothesis'] == c['h'], case+'/source scenario')
        index = np.flatnonzero(record['times'] == 10.)
        need(len(index) == 1, case+'/unique saved t10')
        x0 = record['states'][index[0]].copy()
        with np.load(parent/'dynamic_truth'/(case+'_passive')/'states.npz', allow_pickle=False) as z:
            ip = np.flatnonzero(z['time_min'] == 10.)
            need(len(ip) == 1 and np.array_equal(x0, z['states'][ip[0]]), case+'/common active/passive t10 state')
        prefix = records.window(folder, 0., 10.)[0]
        case_info[case] = dict(source=folder, state10=x0, prefix=prefix, meta=pm, mode=c['mode'], true_h=c['h'])
        saved = schedules['case_info'][case]
        need(saved['parent_key'] == case+'_active' and saved['state10_sha256'] == array_sha(x0), case+'/prepared parent state')
        cmp(saved['demand'], record['trace'].demand_mol_min.iloc[0], case+'/prepared demand')
        for m in MEASURES: cmp(saved['prefix'][m], prefix[m], case+'/prepared prefix/'+m)
    for row in decisions.to_dict('records'):
        case = row['case_id']; key = (case, row['set'], row['trial_id'])
        saved, prior_row = prepared.loc[key], original.loc[key]
        info = case_info[case]; stop = float(row['decision_min']); ci = int(row['command_index'])
        need(stop in (16., 21.) and ci in range(old['policy']['command_points']), 'Original allowed decision/'+str(key))
        branch_key = f'{case}_active_t{stop:g}_u{ci}'
        need(prior_row['key'] == branch_key, 'Original selected branch/'+str(key))
        for field in ['mode', 'true_h', 'call', 'decision_min']:
            need(saved[field] == row[field] == prior_row[field], 'Preserved decision metadata/'+str(key)+'/'+field)
        need(saved['original_command_index'] == ci == prior_row.command_index, 'Preserved command index/'+str(key))
        need(saved['original_command_mol_min'] == prior_row.command_mol_min, 'Exact preserved policy-export command/'+str(key))
        cmp(saved['original_command_mol_min'], row['command_mol_min'], 'Historical command-export agreement/'+str(key))
        need(saved['original_branch_key'] == branch_key, 'Prepared original branch/'+str(key))
        if branch_key not in cost_cache:
            branch = parent/'dynamic_branches'/branch_key
            br = records.load(branch)
            need(br['meta']['scenario'] == info['meta']['scenario'], branch_key+'/absolute truth unchanged')
            need(br['meta']['parent_state_sha256'] == info['meta']['state_sha256'], branch_key+'/source parent hash')
            need(br['meta']['segments'] == [[stop, 31., float(row['command_mol_min'])]], branch_key+'/original chosen command')
            full, _ = records.joined(info['source'], stop, branch)
            window, _ = records.joined(info['source'], stop, branch, start=10.)
            cost_cache[branch_key] = full, window
        full, window = cost_cache[branch_key]
        budget = window['actual_ethanol_mol']; command = constant_command(budget)
        resource = resource_key(case, budget)
        need(resource in by_key, 'Raw budget has exactly matched arm/'+str(key))
        plan = by_key[resource]
        used.add(plan['schedule_id'])
        sid = case+'_b'+hashlib.sha256(budget.hex().encode('ascii')).hexdigest()[:16]
        need(plan['schedule_id'] == saved['schedule_id'] == sid, 'No rounded or clipped arm identity/'+str(key))
        need(saved['budget_float_hex'] == budget.hex() and float(saved['budget_10_31_mol']).hex() == budget.hex(), 'Exact planned raw resource/'+str(key))
        need(saved['constant_command_mol_min'] == command, 'Exact constant command/'+str(key))
        for m in MEASURES:
            for field, want in [('diagnostic_'+m, full[m]), ('diagnostic_10_31_'+m, window[m]), ('prefix_0_10_'+m, info['prefix'][m]), ('archived_reported_'+m, prior_row[m])]:
                cmp(saved[field], want, 'Prepared physical account/'+str(key)+'/'+field)
            cmp(prior_row[m], full[m], 'Archived original amount/'+str(key)+'/'+m)
            cmp(full[m]-window[m], info['prefix'][m], 'Original shared prefix/'+str(key)+'/'+m)
        rebuilt.append(dict(case_id=case, mode=row['mode'], true_h=row['true_h'], set='S4', trial_id=int(row['trial_id']),
                            call=row['call'], decision_min=stop, original_command_index=ci,
                            original_command_mol_min=float(prior_row.command_mol_min), original_branch_key=branch_key,
                            schedule_id=sid, budget_10_31_mol=budget, budget_float_hex=budget.hex(),
                            constant_command_mol_min=command, full=full, window=window))
    need(used == set(by_id), 'All and only declared physical arms used')
    for p in plans:
        info = case_info[p['case_id']]; budget = float.fromhex(p['budget_float_hex'])
        need(p['budget_10_31_mol'] == budget, p['schedule_id']+'/exact resource serialization')
        command = constant_command(budget)
        need(p['constant_command_mol_min'] == command and p['command_float_hex'] == command.hex(), p['schedule_id']+'/no command projection')
        need(p['parent_key'] == p['case_id']+'_active' and p['state10_sha256'] == array_sha(info['state10']), p['schedule_id']+'/planned common start')
        need(p['mode'] == info['mode'] and p['true_h'] == info['true_h'] and p['start_min'] == 10. and p['end_min'] == 31., p['schedule_id']+'/fixed schedule metadata')
    feasible = schedules['feasibility']
    need(feasible['all_within_original_bounds'] and feasible['unique_schedules'] == proto['unique_physical_schedules'] == len(plans), 'Complete arm inventory')
    need(feasible['paired_records'] == proto['paired_records'] == len(rebuilt) == 4000, 'Complete paired population')
    cmp(feasible['command_min'], min(p['constant_command_mol_min'] for p in plans), 'Command minimum')
    cmp(feasible['command_max'], max(p['constant_command_mol_min'] for p in plans), 'Command maximum')
    return dict(root=root, parent=parent, issues=issues, need=need, cmp=cmp, proto=proto, old=old, prior=prior,
                inventory=inventory, plans=plans, by_id=by_id, case_info=case_info, rebuilt=rebuilt, records=records)

def audit(root, plan_only=False):
    a = audit_plan(root)
    if plan_only:
        return dict(schema='ssmr.equal-ethanol-plan-check.v1', created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    pass_=not a['issues'], issues=a['issues'], complete=False,
                    coverage=dict(parent_files_preserved=len(a['inventory']['files']), unique_arms=len(a['plans']), paired_trials=len(a['rebuilt']), new_noise_draws=0),
                    scope='Pre-outcome original-resource, schedule and pairing check only; no new trajectory examined.')
    # The final-output interface is frozen with this checker before any new run.
    return audit_outcomes(a)

def audit_outcomes(a):
    root, parent = a['root'], a['parent']
    need, cmp, proto, records = a['need'], a['cmp'], a['proto'], a['records']
    frozen, ck = read(root/'AMENDMENT_FREEZE.json'), read(root/'checks/CHECK_FREEZE.json')
    for rel, value in frozen['files'].items(): need(sha(root/rel) == value, 'Root frozen file/'+rel)
    for rel, value in ck['files'].items(): need(sha(root/'checks'/rel) == value, 'Frozen checker file/'+rel)
    for rel, value in ck['amendment_inputs'].items(): need(sha(root/rel) == value, 'Checker-bound amendment input/'+rel)
    need(read(root/'checks/math_selftest.json')['pass'], 'Passed pre-outcome math fixtures')
    need(read(root/'checks/plan_verification.json')['pass'], 'Passed pre-outcome plan check')
    check_time = datetime.datetime.fromisoformat(ck['created_utc'])
    root_time = datetime.datetime.fromisoformat(frozen['created_utc'])
    need(root_time >= check_time, 'Root freeze follows checker freeze')
    status, summary = read(root/'run_status.json'), read(root/'outputs/summary.json')
    complete = status['status'] == 'complete' and summary['complete'] is True
    need(complete, 'All new physical executions complete')
    need(datetime.datetime.fromisoformat(status['started_utc']) >= root_time, 'Fresh campaign follows root freeze')
    need(summary['freeze_sha256'] == sha(root/'AMENDMENT_FREEZE.json'), 'Completed output freeze binding')
    need(summary['scope'] == proto['interpretation'] and summary['original_qualified_status_retained'], 'Output scope and qualification retained')
    for rel, value in summary['files'].items(): need(sha(root/rel) == value, 'Summary output hash/'+rel)
    need(set(summary['files']) == {'outputs/arm_costs.csv', 'outputs/paired_trials.csv', 'outputs/paired_summary.csv'}, 'Summary binds every result table')
    need({p.name for p in (root/'branches').iterdir() if p.is_dir()} == set(a['by_id']), 'Exact fresh branch inventory')
    arms = csv(root/'outputs/arm_costs.csv')
    need(not arms.schedule_id.duplicated().any() and set(arms.schedule_id) == set(a['by_id']), 'Complete arm table')
    arms = arms.set_index('schedule_id')
    need(status['completed'] == len(arms) and status['failed'] == 0, 'Complete status counts')
    status_records = {r['schedule_id']: r for r in status['records']}
    need(len(status_records) == len(status['records']) == len(arms) and set(status_records) == set(a['by_id']), 'Status has every arm once')
    sys.path.insert(0, str(parent))
    import dynamics as dyn
    checked_arms, arm_full, arm_window = [], {}, {}
    for p in a['plans']:
        sid = p['schedule_id']; folder = root/'branches'/sid
        need({x.name for x in folder.iterdir() if x.is_file()} == {'metadata.json', 'truth.csv', 'intervals.csv', 'states.npz', 'solver_input_capture.npz', 'solver_input_evidence.json', 'execution.json'}, sid+'/complete evidence inventory')
        r = records.load(folder); meta = r['meta']; info = a['case_info'][p['case_id']]
        need(meta['schema'] == 'ssmr.dynamic-continuation.v1', sid+'/continuation schema')
        need(meta['scenario'] == info['meta']['scenario'], sid+'/unchanged absolute-time truth')
        need(meta['source_hashes'] == info['meta']['source_hashes'], sid+'/unchanged scientific sources')
        need(meta['segments'] == [[10., 31., p['constant_command_mol_min']]], sid+'/constant blind command')
        need(meta['parent_state_sha256'] == info['meta']['state_sha256'], sid+'/correct original parent')
        need(meta['branch_initial_state_sha256'] == array_sha(info['state10']) and meta['parent_decision_min'] == 10., sid+'/exact intended common start')
        need(meta['deterioration_semantics'] == info['meta']['deterioration_semantics'] and meta['quadrature'] == info['meta']['quadrature'], sid+'/unchanged dynamics/accounting semantics')
        need(len(r['trace']) == 211 and len(r['intervals']) == 210 and r['times'][0] == 10. and r['times'][-1] == 31., sid+'/complete intervention trajectory')
        need(meta['diagnostics']['accepted_state_min'] >= -a['old']['solver']['atol'], sid+'/solver state admissibility')
        records.observables_from_states(folder, dyn)
        evidence = read(folder/'solver_input_evidence.json')
        with np.load(folder/'solver_input_capture.npz', allow_pickle=False) as z:
            need(set(z.files) == {'expected_parent_state', 'supplied_y0', 'solver_y_initial', 'dense_y_initial'}, sid+'/captured array schema')
            cap = {key: z[key].copy() for key in z.files}
        for key, value in cap.items(): need(value.shape == (800,) and np.isfinite(value).all(), sid+'/finite captured vector/'+key)
        need(np.array_equal(cap['expected_parent_state'], info['state10']), sid+'/capture identifies original saved state')
        need(np.array_equal(cap['supplied_y0'], info['state10']), sid+'/actual supplied solver input exact')
        need(np.array_equal(cap['solver_y_initial'], cap['supplied_y0']), sid+'/actual solver accepted initial vector exact')
        need(np.array_equal(cap['dense_y_initial'], r['states'][0]), sid+'/dense interpolation equals saved export')
        field_arrays = {'parent_state10_sha256': cap['expected_parent_state'], 'supplied_y0_sha256': cap['supplied_y0'],
                        'solver_y_initial_sha256': cap['solver_y_initial'], 'dense_y_initial_sha256': cap['dense_y_initial'],
                        'exported_first_state_sha256': r['states'][0]}
        for field, value in field_arrays.items(): need(evidence[field] == array_sha(value), sid+'/captured array hash/'+field)
        dense_exact = bool(np.array_equal(r['states'][0], cap['supplied_y0']))
        dense_diff = float(np.max(np.abs(r['states'][0]-cap['supplied_y0'])))
        for field, value in [('supplied_y0_equals_parent', True), ('solver_initial_equals_supplied', True),
                             ('exported_first_equals_supplied', dense_exact), ('dense_initial_equals_exported_first', True),
                             ('original_export_qualification_retained', True)]:
            need(evidence[field] is value, sid+'/honest solver identity flag/'+field)
        need(evidence['max_abs_exported_initial_difference'] == dense_diff, sid+'/explicit exported-state discrepancy')
        need(evidence['capture_npz_sha256'] == sha(folder/'solver_input_capture.npz'), sid+'/capture file hash')
        need(evidence['source_engine_sha256'] == sha(parent/'dynamics.py'), sid+'/captured source identity')
        need(evidence['solve_calls'] == 1 and evidence['t_span'] == [10., 31.] and evidence['method'] == 'BDF', sid+'/one unchanged solver call')
        for field, oldfield in [('rtol', 'rtol'), ('atol', 'atol'), ('max_step', 'max_step_min')]:
            need(evidence[field] == a['old']['solver'][oldfield], sid+'/captured solver option/'+field)
        exe = read(folder/'execution.json')
        need(exe['status'] == 'complete' and exe['record']['status'] == 'complete', sid+'/completed execution')
        need(datetime.datetime.fromisoformat(exe['started_utc']) >= root_time and datetime.datetime.fromisoformat(exe['completed_utc']) >= datetime.datetime.fromisoformat(exe['started_utc']), sid+'/fresh execution timestamps')
        need(exe['freeze_sha256'] == sha(root/'AMENDMENT_FREEZE.json') and exe['protocol_sha256'] == sha(root/'protocol.json'), sid+'/execution frozen inputs')
        need(exe['solver_input_evidence_sha256'] == sha(folder/'solver_input_evidence.json'), sid+'/execution capture binding')
        whole, full_intervals = records.joined(info['source'], 10., folder)
        window = records.window(folder, 10., 31.)[0]
        need(len(full_intervals) == 310, sid+'/common full horizon')
        for field in ['actual_ethanol_mol', 'commanded_ethanol_mol']:
            need(budget_ok(window[field], p['budget_10_31_mol']), sid+'/equal resource/'+field)
            need(budget_ok(window[field], p['constant_command_mol_min']*21.), sid+'/analytic constant resource/'+field)
        want_row = dict(p, status='complete', branch_path='branches/'+sid, reported_start_min=0., reported_end_min=31.,
                        budget_difference_actual_mol=window['actual_ethanol_mol']-p['budget_10_31_mol'],
                        budget_difference_commanded_mol=window['commanded_ethanol_mol']-p['budget_10_31_mol'],
                        exact_solver_input_pass=True, exported_first_state_exact=dense_exact)
        want_row.update({'blind_'+m: whole[m] for m in MEASURES})
        want_row.update({'blind_10_31_'+m: window[m] for m in MEASURES})
        for name, value in want_row.items():
            for label, saved in [('arm', arms.loc[sid]), ('execution', exe['record']), ('status', status_records[sid])]:
                if name == 'schedule_id' and label == 'arm': continue
                if name in p or isinstance(value, (str, bool)):
                    need(saved[name] == value, sid+'/'+label+' metadata/'+name)
                else: cmp(saved[name], value, sid+'/'+label+' physical value/'+name)
        checked_arms.append(dict(want_row, max_abs_exported_initial_difference=dense_diff,
                                 exported_start_semantics='Saved dense interpolation; exact solver input is separately checked'))
        arm_full[sid], arm_window[sid] = whole, window
    paired = csv(root/'outputs/paired_trials.csv')
    keys = ['case_id', 'set', 'trial_id']; expected_keys = {(c, 'S4', i) for c in CENTRAL for i in range(1000)}
    need(not paired.duplicated(keys).any() and set(map(tuple, paired[keys].to_numpy())) == expected_keys, 'Every original paired record present exactly once')
    paired = paired.set_index(keys)
    prepared = csv(root/'trial_schedule_map.csv').set_index(keys)
    rows = []
    for row in a['rebuilt']:
        key = (row['case_id'], row['set'], row['trial_id']); saved = paired.loc[key]; planrow = prepared.loc[key]
        for field in prepared.columns:
            need(saved[field] == planrow[field], 'Unchanged prepared trial in final table/'+str(key)+'/'+field)
        sid = row['schedule_id']; x = {k: v for k, v in row.items() if k not in ['full', 'window']}
        for prefix, oldcost, blind in [('', row['full'], arm_full[sid]), ('10_31_', row['window'], arm_window[sid])]:
            for m in MEASURES:
                for kind, value in [('diagnostic', oldcost[m]), ('blind', blind[m]), ('difference', oldcost[m]-blind[m])]:
                    field = kind+'_'+prefix+m
                    cmp(saved[field], value, 'Raw reconstructed paired value/'+str(key)+'/'+field); x[field] = value
                cmp(row['full'][m]-arm_full[sid][m], row['window'][m]-arm_window[sid][m], 'Shared prefix cancels/'+str(key)+'/'+m)
        need(budget_ok(arm_window[sid]['actual_ethanol_mol'], row['budget_10_31_mol']), 'Every trial actual resource matched/'+str(key))
        need(budget_ok(arm_window[sid]['commanded_ethanol_mol'], row['budget_10_31_mol']), 'Every trial commanded resource matched/'+str(key))
        rows.append(x)
    expected = pd.DataFrame(rows)
    reported = csv(root/'outputs/paired_summary.csv')
    need(not reported.duplicated(['case_id', 'set']).any() and set(zip(reported.case_id, reported['set'])) == {(c, 'S4') for c in CENTRAL}, 'Four complete summary groups')
    reported = reported.set_index(['case_id', 'set']); groups = []
    for key, group in expected.groupby(['case_id', 'set'], sort=True):
        out = dict(case_id=key[0], set=key[1], mode=int(group.iloc[0]['mode']), true_h=group.iloc[0]['true_h'],
                   trials=len(group), unique_schedules=int(group.schedule_id.nunique()),
                   stop16_count=int((group.decision_min == 16).sum()), stop21_count=int((group.decision_min == 21).sum()),
                   max_abs_ethanol_difference_mol=float(np.abs(group.difference_10_31_actual_ethanol_mol).max()),
                   max_abs_commanded_ethanol_difference_mol=float(np.abs(group.difference_10_31_commanded_ethanol_mol).max()),
                   constant_command_min_mol_min=float(group.constant_command_mol_min.min()),
                   constant_command_max_mol_min=float(group.constant_command_mol_min.max()))
        saved = reported.loc[key]
        for name, value in out.items():
            if name in ('case_id', 'set'): continue
            if isinstance(value, (int, str)): need(saved[name] == value, 'Group metadata/'+str(key)+'/'+name)
            else: cmp(saved[name], value, 'Group resources/'+str(key)+'/'+name)
        for prefix in ['', '10_31_']:
            for m in MEASURES:
                for kind in ['diagnostic', 'blind', 'difference']:
                    field = kind+'_'+prefix+m
                    for statistic, value in stats(group[field]).items():
                        name = field+'_'+statistic; cmp(saved[name], value, 'Group raw arithmetic/'+str(key)+'/'+name); out[name] = value
        for name, field in [('common_actual_ethanol_mol_mean', 'diagnostic_actual_ethanol_mol_mean'), ('common_ethanol_10_31_mol_mean', 'diagnostic_10_31_actual_ethanol_mol_mean')]:
            cmp(saved[name], out[field], 'Group common resource/'+str(key)+'/'+name); out[name] = out[field]
        groups.append(out)
    expected_coverage = dict(paired_records=len(rows), paired_groups=len(groups), unique_schedules=len(checked_arms),
                             max_abs_actual_budget_error_mol=float(np.abs(expected.difference_10_31_actual_ethanol_mol).max()),
                             max_abs_commanded_budget_error_mol=float(np.abs(expected.difference_10_31_commanded_ethanol_mol).max()), new_noise_draws=0)
    for name, value in expected_coverage.items():
        if isinstance(value, int): need(summary['coverage'][name] == value, 'Summary final coverage/'+name)
        else: cmp(summary['coverage'][name], value, 'Summary final resource residual/'+name)
    bindings = {}
    for p in sorted((root/'branches').rglob('*')):
        if p.is_file(): bindings[p.relative_to(root).as_posix()] = sha(p)
    for rel in ['protocol.json', 'PROTOCOL_AMENDMENT.txt', 'AMENDMENT_FREEZE.json', 'parent_inventory.json', 'schedule_inventory.json', 'trial_schedule_map.csv',
                'checks/CHECK_FREEZE.json', 'outputs/summary.json', 'outputs/arm_costs.csv', 'outputs/paired_trials.csv', 'outputs/paired_summary.csv', 'run_status.json']:
        bindings[rel] = sha(root/rel)
    return dict(schema='ssmr.equal-ethanol-independent-check.v1', created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                complete=complete, pass_=not a['issues'], issues=a['issues'],
                coverage=dict(parent_files_preserved=len(a['inventory']['files']), unique_arms=len(checked_arms), paired_trials=len(rows), paired_groups=len(groups), new_noise_draws=0),
                parent_qualified_check_sha256=sha(parent/'checks/final_check.json'), parent_exact_export_gate_pass=False, qualified_parent_resolution_retained=True,
                budget_tolerance=dict(atol_mol=BUDGET_ATOL, rtol=BUDGET_RTOL),
                maximum_actual_budget_error_mol=expected_coverage['max_abs_actual_budget_error_mol'],
                maximum_commanded_budget_error_mol=expected_coverage['max_abs_commanded_budget_error_mol'],
                exact_solver_input_pass=all(r['exact_solver_input_pass'] for r in checked_arms),
                dense_export_all_exact=all(r['exported_first_state_exact'] for r in checked_arms),
                arm_costs=checked_arms, paired_summary=groups, bindings=bindings,
                scope='Outcome-aware, retrospective resource-matched constant-feed benchmark. Same-model internal verification of source integrity, solver input, export consistency and physical accounting; no independent reactor solver, deployable universal blind policy, pure information value, economic superiority or plant validation.')

if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', type=Path, default=HERE.parent)
    ap.add_argument('--out', type=Path, default=HERE/'verification.json')
    ap.add_argument('--plan-only', action='store_true')
    args = ap.parse_args()
    try:
        result = audit(args.root, args.plan_only)
        result['pass'] = result.pop('pass_')
    except Exception as exc:
        traceback.print_exc()
        result = dict(schema='ssmr.equal-ethanol-independent-check.v1', complete=False, pass_=False,
                      issues=[type(exc).__name__+': '+str(exc)], traceback=traceback.format_exc())
        result['pass'] = result.pop('pass_')
    tmp = args.out.with_suffix(args.out.suffix+'.tmp')
    tmp.write_text(json.dumps(result, indent=2, allow_nan=False)+'\n', encoding='utf-8'); tmp.replace(args.out)
    print(json.dumps({k: result[k] for k in ['complete', 'pass', 'issues', 'coverage', 'scope'] if k in result}, indent=2))
    raise SystemExit(0 if result['pass'] else 1)
