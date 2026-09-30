"""Read-only raw record validation and physical accounting, without runner imports."""
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
from audit_math import account, close, select_window, TIME_ATOL, U_MIN, U_MAX

FEATURES = ('H2_mol_min', 'T_out_K', 'waste_m3_min', 'y_H2', 'y_CH4', 'y_CO', 'y_CO2')

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def array_sha(x):
    return hashlib.sha256(np.asarray(x, dtype='<f8').tobytes()).hexdigest()

def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))

def csv(path):
    return pd.read_csv(path, float_precision='round_trip')

class Records:
    def __init__(self, need, solver_settings):
        self.need, self.solver_settings = need, solver_settings
        self.cache = {}

    def cmp(self, got, want, label, atol=1e-13, rtol=1e-9):
        self.need(close(got, want, atol, rtol), label)

    def load(self, folder):
        folder = Path(folder)
        if folder in self.cache:
            return self.cache[folder]
        label = str(folder)
        meta = read(folder/'metadata.json')
        tr, iv = csv(folder/'truth.csv'), csv(folder/'intervals.csv')
        with np.load(folder/'states.npz', allow_pickle=False) as z:
            ts, states = z['time_min'].copy(), z['states'].copy()
        self.need(states.shape == (len(tr), 800), label+'/state shape')
        self.need(np.isfinite(states).all(), label+'/finite states')
        self.need(np.array_equal(ts, tr.time_min.to_numpy()), label+'/exact state/trace times')
        self.need(meta['state_sha256'] == array_sha(states), label+'/state checksum')
        self.need(meta['settings'] == self.solver_settings, label+'/unchanged solver settings')
        for name, value in meta['output_hashes'].items():
            self.need(sha(folder/name) == value, label+'/raw output hash/'+name)
        for name, value in meta['source_hashes'].items():
            self.need(sha(name) == value, label+'/unchanged source/'+name)
        self.need(np.isfinite(tr.select_dtypes('number').to_numpy()).all(), label+'/finite trace')
        self.need(np.isfinite(iv.select_dtypes('number').to_numpy()).all(), label+'/finite intervals')
        self.cmp(np.diff(ts), np.full(len(ts)-1, meta['settings']['sample_min']), label+'/sampling', TIME_ATOL, 0)
        self.cmp(iv.t_start.to_numpy(), ts[:-1], label+'/interval starts', TIME_ATOL, 0)
        self.cmp(iv.t_end.to_numpy(), ts[1:], label+'/interval ends', TIME_ATOL, 0)
        sc = meta['scenario']; h = sc['hypothesis']
        self.need(h in ('C', 'M'), label+'/declared C/M scope')
        health = np.minimum(1., sc['theta10'] * np.exp(-sc['rate_per_min']*(ts-10.)))
        ac, am = (health, np.ones(len(ts))) if h == 'C' else (np.ones(len(ts)), health)
        for field, want in [('a_c', ac), ('a_m', am), ('feed_gain', np.ones(len(ts))), ('sensor_bias_mol_min', np.zeros(len(ts)))]:
            self.cmp(tr[field].to_numpy(), want, label+'/'+field)
        self.need(np.array_equal(tr.feed_gain.to_numpy(), np.ones(len(ts))), label+'/exact absence of feed fault')
        cmd, nxt, interval_cmd = [], [], []
        for t in ts:
            seg = [s for s in meta['segments'] if s[0]-TIME_ATOL <= t <= s[1]+TIME_ATOL]
            if not seg: raise ValueError(label+'/uncovered trace time')
            cmd.append(seg[0][2]); nxt.append(seg[-1][2])
        for t in iv.t_start:
            seg = [s for s in meta['segments'] if s[0]-TIME_ATOL <= t < s[1]-TIME_ATOL]
            if len(seg) != 1: raise ValueError(label+'/ambiguous interval command')
            interval_cmd.append(seg[0][2])
        self.cmp(tr.command_mol_min.to_numpy(), np.asarray(cmd), label+'/event-left commands', 0, 0)
        self.cmp(tr.command_next_mol_min.to_numpy(), np.asarray(nxt), label+'/event-right commands', 0, 0)
        self.cmp(iv.commanded_ethanol_mol_min.to_numpy(), np.asarray(interval_cmd), label+'/interval commands', 0, 0)
        self.need(bool(((tr.command_mol_min >= U_MIN) & (tr.command_mol_min <= U_MAX)).all()), label+'/physical command bounds')
        self.cmp(tr.actual_ethanol_mol_min.to_numpy(), tr.command_mol_min.to_numpy(), label+'/actual trace feed', 0, 0)
        for field in ('actual_ethanol_start', 'actual_ethanol_end', 'command_start_mol_min', 'command_end_mol_min'):
            self.cmp(iv[field].to_numpy(), np.asarray(interval_cmd), label+'/'+field, 0, 0)
        for f in FEATURES:
            self.cmp(tr['observed_'+f].to_numpy(), tr['true_'+f].to_numpy(), label+'/unbiased noiseless export/'+f, 0, 0)
        self.cmp(iv.H2_start_mol_min.to_numpy(), tr.true_H2_mol_min.to_numpy()[:-1], label+'/H2 left endpoints')
        self.cmp(iv.H2_end_mol_min.to_numpy(), tr.true_H2_mol_min.to_numpy()[1:], label+'/H2 right endpoints')
        costs, amounts = account(iv, tr.demand_mol_min.to_numpy()[:-1], tr.demand_mol_min.to_numpy()[1:])
        for name, want in amounts.items():
            self.cmp(iv[name].to_numpy(), want, label+'/independent interval amount/'+name)
        health_flag = (ac >= .4) & (ac <= 1) & (am >= .4) & (am <= 1)
        self.need(np.array_equal(tr.health_in_map_domain.to_numpy(), health_flag), label+'/health domain flag')
        self.need(bool(tr.feed_in_map_domain.all()), label+'/feed domain flag')
        result = dict(folder=folder, meta=meta, trace=tr, intervals=iv, times=ts, states=states, costs=costs)
        self.cache[folder] = result
        return result

    def window(self, folder, start, end):
        r = self.load(folder)
        indices = select_window(r['intervals'], start, end)
        iv = r['intervals'].iloc[indices].copy()
        q = r['trace'].demand_mol_min.to_numpy()
        costs, _ = account(iv, q[indices], q[indices+1])
        return costs, iv, q[indices], q[indices+1]

    def joined(self, source, stop, branch, start=0., end=31.):
        pre = self.window(source, start, stop)
        post = self.window(branch, stop, end)
        iv = pd.concat([pre[1], post[1]], ignore_index=True)
        q0, q1 = np.concatenate([pre[2], post[2]]), np.concatenate([pre[3], post[3]])
        total, _ = account(iv, q0, q1)
        return total, iv

    def observables_from_states(self, folder, dyn):
        """Export-consistency check using pinned equations; never integrate an ODE."""
        r = self.load(folder); sc = r['meta']['scenario']; tr = r['trace']
        mode = sc['mode']; pressure, temperature, demand = dyn.MODES[mode]
        self.cmp(tr.demand_mol_min.to_numpy(), np.full(len(tr), demand), str(folder)+'/original H2 demand', 0, 0)
        _, ubase, _ = dyn.load_ic(mode, 50, False)
        self.cmp(tr.water_mol_min.to_numpy(), np.full(len(tr), ubase[1]), str(folder)+'/unchanged water input', 0, 0)
        out = []
        for state, row in zip(r['states'], tr.to_dict('records')):
            p = dyn.DynamicParameters(pressure, temperature, 50, a_c=row['a_c'], a_m=row['a_m'], kinetic_scales=tuple(sc['kinetic_scales']))
            _, values = dyn.evaluate(state, np.array([row['actual_ethanol_mol_min'], row['water_mol_min']]), p)
            out.append(dyn.observables(values))
        for f in FEATURES:
            self.cmp(tr['true_'+f].to_numpy(), np.array([o[f] for o in out]), str(folder)+'/state-derived '+f)
