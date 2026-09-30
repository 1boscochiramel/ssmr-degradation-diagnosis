"""Independent accounting primitives. No plant, policy or runner imports."""
import math
import numpy as np

MEASURES = ('H2_shortfall_mol', 'actual_ethanol_mol', 'commanded_ethanol_mol', 'H2_produced_mol', 'H2_demand_mol')
BUDGET_ATOL = 1e-12
BUDGET_RTOL = 1e-12
ARITH_ATOL = 1e-13
ARITH_RTOL = 1e-9
TIME_ATOL = 1e-10
U_MIN, U_MAX = .0018, .0024
CENTRAL = ('m1_C_d05_r1', 'm1_M_d05_r1', 'm2_C_d05_r1', 'm2_M_d05_r1')

def close(a, b, atol=ARITH_ATOL, rtol=ARITH_RTOL):
    a, b = np.asarray(a), np.asarray(b)
    return a.shape == b.shape and bool(np.allclose(a, b, atol=atol, rtol=rtol, equal_nan=False))

def budget_ok(actual, target):
    return close(actual, target, BUDGET_ATOL, BUDGET_RTOL)

def constant_command(budget, start=10., end=31.):
    if not np.isfinite([budget, start, end]).all() or end <= start:
        raise ValueError('Invalid resource or horizon')
    command = float(budget) / (end - start)
    if not U_MIN <= command <= U_MAX:
        raise ValueError('Matched resource is outside physical command bounds; do not clip')
    return command

def resource_key(case, budget):
    if case not in CENTRAL or not np.isfinite(budget) or budget <= 0:
        raise ValueError('Invalid case or resource')
    return case, float(budget).hex()

def account(intervals, demand_start, demand_end):
    """Rebuild endpoint-trapezoid amounts, never read saved integral columns."""
    a = np.asarray(intervals['t_start'], dtype=float)
    b = np.asarray(intervals['t_end'], dtype=float)
    dt = b - a
    cmd = np.asarray(intervals['commanded_ethanol_mol_min'], dtype=float)
    f0, f1 = (np.asarray(intervals[k], dtype=float) for k in ('actual_ethanol_start', 'actual_ethanol_end'))
    y0, y1 = (np.asarray(intervals[k], dtype=float) for k in ('H2_start_mol_min', 'H2_end_mol_min'))
    q0, q1 = np.asarray(demand_start, dtype=float), np.asarray(demand_end, dtype=float)
    if not len(dt) or not np.all(dt > 0) or not all(x.shape == dt.shape and np.isfinite(x).all() for x in (a, b, cmd, f0, f1, y0, y1, q0, q1)):
        raise ValueError('Invalid physical intervals')
    if len(dt) > 1 and not close(b[:-1], a[1:], TIME_ATOL, 0):
        raise ValueError('Gap or overlap in physical account')
    amounts = {
        'actual_ethanol_mol': dt * (f0 + f1) / 2,
        'commanded_ethanol_mol': dt * cmd,
        'H2_produced_mol': dt * (y0 + y1) / 2,
        'H2_demand_mol': dt * (q0 + q1) / 2,
        'H2_shortfall_mol': dt * (np.maximum(q0-y0, 0) + np.maximum(q1-y1, 0)) / 2,
    }
    return {k: math.fsum(map(float, v)) for k, v in amounts.items()}, amounts

def select_window(intervals, start, end):
    a, b = np.asarray(intervals['t_start']), np.asarray(intervals['t_end'])
    crossing = ((a < start-TIME_ATOL) & (b > start+TIME_ATOL)) | ((a < end-TIME_ATOL) & (b > end+TIME_ATOL))
    if crossing.any():
        raise ValueError('Resource boundary cuts a saved interval')
    ix = np.flatnonzero((a >= start-TIME_ATOL) & (b <= end+TIME_ATOL))
    if not len(ix) or not close([a[ix[0]], b[ix[-1]]], [start, end], TIME_ATOL, 0):
        raise ValueError('Incomplete requested physical window')
    return ix

def difference(diagnostic, control):
    return {k: float(diagnostic[k] - control[k]) for k in MEASURES}

def stats(values):
    x = np.asarray(values, dtype=float)
    if x.ndim != 1 or len(x) < 2 or not np.isfinite(x).all():
        raise ValueError('Invalid descriptive sample')
    return dict(mean=float(x.mean()), sd=float(x.std(ddof=1)), min=float(x.min()), max=float(x.max()))

def require_keys(rows, keys, expected):
    observed = [tuple(row[k] for k in keys) for row in rows]
    if len(observed) != len(set(observed)) or set(observed) != set(expected):
        raise ValueError('Missing, duplicate or extra pairing keys')
