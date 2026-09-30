"""Continuous ODE truth for the revised diagnostic sequence.

This wrapper imports the immutable, verified Python equations. It does not draw
measurement noise or make classification decisions. Nominal drop means the
archived map loss at t=10, not an asserted dynamic endpoint loss.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from functools import lru_cache
from hashlib import sha256
import json
from pathlib import Path
import sys
import time

import numpy as np
import pandas as pd
from scipy.integrate import solve_ivp

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / 'reference/reformer_diag'
sys.path.insert(0, str(SOURCE))
sys.path.insert(0, str(SOURCE / 'diag'))
from model import MODES, evaluate, jacobian_sparsity  # noqa: E402
from benchmark_cases import load_ic  # noqa: E402
from faultmodel import FaultParameters, observables, KINF  # noqa: E402
from hypotheses import Map, FEATURES, U_SS, U_MIN, U_MAX  # noqa: E402

FEATURES = tuple(FEATURES)
DEFAULT_RATES = {'H': 0., 'C': .005, 'M': .003, 'F': .001, 'S': 0., 'CM': 0.}
PRECONDITION_REL_TOL = 1e-6
PRECONDITION_ABS_TOL = {'H2_mol_min': 1e-12, 'T_out_K': 1e-5,
                       'waste_m3_min': 1e-12, 'y_H2': 1e-8, 'y_CH4': 1e-8,
                       'y_CO': 1e-8, 'y_CO2': 1e-8}


class UnreachableScenario(ValueError):
    """The requested nominal-map loss has no supported severity."""


class PreconditioningFailure(RuntimeError):
    """Fixed-health initialization did not meet its predeclared convergence gate."""

    def __init__(self, evidence):
        super().__init__('Fixed-health initialization failed to converge within20 min')
        self.evidence = evidence


@dataclass(frozen=True)
class Scenario:
    mode: int
    hypothesis: str
    nominal_drop: float
    theta10: float
    rate_per_min: float
    sensor_slope_per_min: float = 0.
    theta_c10: float = 1.
    theta_m10: float = 1.
    rate_c_per_min: float = 0.
    rate_m_per_min: float = 0.
    kinetic_scales: tuple[float, ...] = (1., 1., 1., 1.)

    def health(self, t):
        """Absolute physical time; no reset at a decision or command event."""
        ac = am = fg = 1.
        bias = 0.
        if self.hypothesis in ('C', 'M', 'F'):
            value = min(1., self.theta10 * np.exp(-self.rate_per_min * (t - 10.)))
            if self.hypothesis == 'C': ac = value
            elif self.hypothesis == 'M': am = value
            else: fg = value
        elif self.hypothesis == 'S':
            bias = self.theta10 + self.sensor_slope_per_min * (t - 10.)
        elif self.hypothesis == 'CM':
            ac = min(1., self.theta_c10 * np.exp(-self.rate_c_per_min * (t - 10.)))
            am = min(1., self.theta_m10 * np.exp(-self.rate_m_per_min * (t - 10.)))
        return float(ac), float(am), float(fg), float(bias)


@dataclass
class DynamicParameters(FaultParameters):
    kinetic_scales: tuple[float, ...] = (1., 1., 1., 1.)

    @property
    def kinf(self):
        return KINF * self.a_c * np.asarray(self.kinetic_scales)


@lru_cache(maxsize=2)
def _map(mode):
    return Map(mode)


def make_scenario(mode, h, drop=.05, controls=None):
    """Resolve nominal-map anchor once; explicit controls are serialized.

    Supported controls: rate_per_min, theta10 (explicit off-grid/stress anchor),
    sensor_slope_per_min, kinetic_scales; CM requires theta_c10/theta_m10 and
    accepts rate_c_per_min/rate_m_per_min. No stochastic noise enters this API.
    """
    controls = dict(controls or {})
    h = {'healthy': 'H', 'combined': 'CM'}.get(h, h)
    if mode not in (1, 2) or h not in DEFAULT_RATES:
        raise ValueError('Supported modes are 1/2 and hypotheses H/C/M/F/S/CM')
    allowed = {'rate_per_min', 'theta10', 'sensor_slope_per_min', 'theta_c10',
               'theta_m10', 'rate_c_per_min', 'rate_m_per_min', 'kinetic_scales'}
    if set(controls) - allowed:
        raise ValueError(f'Unknown controls: {sorted(set(controls) - allowed)}')
    if not np.isfinite(drop) or not 0 <= drop < 1:
        raise ValueError('drop must be a finite fractional nominal H2 loss')
    if h == 'H':
        if drop != 0:
            raise ValueError('Healthy scenario requires drop=0')
        theta = 1.
    elif h == 'CM':
        if not {'theta_c10', 'theta_m10'} <= controls.keys():
            raise ValueError('CM stress requires explicit component theta_c10/theta_m10')
        theta = 1.
    else:
        theta = controls.get('theta10')
        if theta is None:
            theta = _map(mode).severity_for_drop(h, drop, U_SS[mode])
        if theta is None:
            raise UnreachableScenario(f'mode={mode},h={h},nominal_map_drop={drop} unreachable')
    scales = tuple(float(v) for v in controls.get('kinetic_scales', (1.,) * 4))
    if len(scales) != 4 or not all(np.isfinite(scales)) or min(scales) <= 0:
        raise ValueError('kinetic_scales needs four finite positive multipliers')
    scenario = Scenario(mode, h, float(drop), float(theta),
        float(controls.get('rate_per_min', DEFAULT_RATES[h])),
        float(controls.get('sensor_slope_per_min', 0.)),
        float(controls.get('theta_c10', 1.)), float(controls.get('theta_m10', 1.)),
        float(controls.get('rate_c_per_min', 0.)), float(controls.get('rate_m_per_min', 0.)), scales)
    vals = [scenario.theta10, scenario.rate_per_min, scenario.sensor_slope_per_min,
            scenario.theta_c10, scenario.theta_m10, scenario.rate_c_per_min, scenario.rate_m_per_min]
    if not np.isfinite(vals).all() or min(scenario.rate_per_min, scenario.rate_c_per_min, scenario.rate_m_per_min) < 0:
        raise ValueError('Controls must be finite; deterioration rates cannot be negative')
    if h in ('C', 'M', 'F') and not 0 < scenario.theta10 <= 1:
        raise ValueError('Physical theta10 must be in (0,1]')
    if h == 'CM' and not (0 < scenario.theta_c10 <= 1 and 0 < scenario.theta_m10 <= 1):
        raise ValueError('Combined health anchors must be in (0,1]')
    return scenario


def _hash(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def source_hashes(mode):
    files = [SOURCE / 'model.py', SOURCE / 'benchmark_cases.py',
             SOURCE / 'diag/faultmodel.py', SOURCE / 'diag/hypotheses.py',
             SOURCE / f'diag/outputs_diag/map_mode{mode}.csv',
             SOURCE.parent / f'upstream/SSMR_simulator/ICFull/Mode{mode}_np50.mat', Path(__file__)]
    return {str(p.resolve()): _hash(p) for p in files}


def _settings(sample_min=.1, rtol=1e-6, atol=1e-8, max_step_min=.1):
    if min(sample_min, rtol, atol, max_step_min) <= 0:
        raise ValueError('Sampling and solver tolerances must be positive')
    return dict(method='BDF', np=50, sample_min=float(sample_min), rtol=float(rtol),
                atol=float(atol), max_step_min=float(max_step_min))


def _precondition(scenario, settings):
    """Hold health at its physical t0 value; settling time does not age the fault."""
    tic = time.perf_counter()
    x, u, ic = load_ic(scenario.mode, 50, False)
    starter = x.copy()
    ac, am, fg, bias = scenario.health(0.)
    u = np.array([U_SS[scenario.mode] * fg, u[1]])
    P, T, _ = MODES[scenario.mode]
    p = DynamicParameters(P, T, 50, a_c=ac, a_m=am, kinetic_scales=scenario.kinetic_scales)
    sp = jacobian_sparsity(50)
    rows = [dict(precondition_time_min=0., **observables(evaluate(x, u, p)[1]))]
    states = [x.copy()]
    converged, comparisons = False, {}
    diag = dict(nfev=0, njev=0, nlu=0, accepted_state_min=float(x.min()))
    for minute in range(1, 21):
        sol = solve_ivp(lambda t, state: evaluate(state, u, p)[0], (minute - 1., float(minute)), x,
            method='BDF', rtol=settings['rtol'], atol=settings['atol'],
            max_step=settings['max_step_min'], jac_sparsity=sp, dense_output=True)
        if not sol.success:
            raise RuntimeError('Preconditioning ODE failed: ' + sol.message)
        diag['accepted_state_min'] = min(diag['accepted_state_min'], float(sol.y.min()))
        if sol.y.min() < -settings['atol']:
            raise FloatingPointError('Preconditioning accepted state below negative absolute tolerance')
        for key in ('nfev', 'njev', 'nlu'):
            diag[key] += int(getattr(sol, key))
        for tau in (minute - .5, float(minute)):
            state = sol.y[:, -1].copy() if tau == minute else sol.sol(tau)
            rows.append(dict(precondition_time_min=tau, **observables(evaluate(state, u, p)[1])))
            states.append(state.copy())
        x = sol.y[:, -1].copy()
        mid, end = rows[-2], rows[-1]
        comparisons = {f: {'absolute_difference': abs(end[f] - mid[f]),
                          'limit': PRECONDITION_ABS_TOL[f] + PRECONDITION_REL_TOL * max(abs(mid[f]), abs(end[f]))}
                       for f in FEATURES}
        if minute >= 2 and all(v['absolute_difference'] <= v['limit'] for v in comparisons.values()):
            converged = True
            break
    diag['wall_seconds'] = time.perf_counter() - tic
    meta = dict(status='PASS' if converged else 'FAIL', converged=converged, minutes=float(minute),
        physical_schedule_time_held_min=0., fixed_a_c=ac, fixed_a_m=am, fixed_feed_gain=fg,
        fixed_command_mol_min=U_SS[scenario.mode], fixed_actual_ethanol_mol_min=float(u[0]),
        maximum_minutes=20., minimum_minutes=2., comparison_spacing_min=.5,
        relative_tolerance=PRECONDITION_REL_TOL, absolute_tolerances=PRECONDITION_ABS_TOL,
        final_comparisons=comparisons, diagnostics=diag, starter_ic=ic,
        starter_state_sha256=sha256(starter.astype('<f8').tobytes()).hexdigest(),
        state0_sha256=sha256(x.astype('<f8').tobytes()).hexdigest())
    return dict(trace=pd.DataFrame(rows), states=np.asarray(states), state0=x, metadata=meta)


def _integrate(scenario, x0, segments, settings, demand_mol_min):
    tic = time.perf_counter()
    x = np.asarray(x0, dtype=float).copy()
    if x.shape != (800,) or not np.isfinite(x).all():
        raise ValueError('np50 initial state must contain 800 finite values')
    _, u0, _ = load_ic(scenario.mode, 50, False)
    P, T, _ = MODES[scenario.mode]
    sp = jacobian_sparsity(50)
    rows, states, intervals = [], [], []
    diag = dict(nfev=0, njev=0, nlu=0, accepted_state_min=float(x.min()))
    previous_end = None
    for segment_index, (a, b, command) in enumerate(segments):
        if b <= a or (previous_end is not None and abs(a - previous_end) > 1e-10):
            raise ValueError('Segments must be ordered, positive, and contiguous')
        if not U_MIN - 1e-12 <= command <= U_MAX + 1e-12:
            raise ValueError('Ethanol command is outside declared physical bounds')
        count = round((b - a) / settings['sample_min'])
        if abs(count * settings['sample_min'] - (b - a)) > 1e-9:
            raise ValueError('Segment duration must be an integer multiple of sample_min')
        grid = np.linspace(a, b, count + 1)

        def parameters(t):
            ac, am, fg, bias = scenario.health(t)
            p = DynamicParameters(P, T, 50, a_c=ac, a_m=am, kinetic_scales=scenario.kinetic_scales)
            u = np.array([command * fg, u0[1]])
            return p, u, (ac, am, fg, bias)

        def fun(t, state):
            p, u, _ = parameters(t)
            return evaluate(state, u, p)[0]

        sol = solve_ivp(fun, (a, b), x, method='BDF', rtol=settings['rtol'], atol=settings['atol'],
                        max_step=settings['max_step_min'], jac_sparsity=sp, dense_output=True)
        if not sol.success:
            raise RuntimeError(sol.message)
        diag['accepted_state_min'] = min(diag['accepted_state_min'], float(sol.y.min()))
        if sol.y.min() < -settings['atol']:
            raise FloatingPointError('Accepted model state below negative absolute tolerance')
        for key in ('nfev', 'njev', 'nlu'):
            diag[key] += int(getattr(sol, key))
        yy = sol.sol(grid).T
        local = []
        for t, state in zip(grid, yy):
            p, u, (ac, am, fg, bias) = parameters(float(t))
            o = observables(evaluate(state, u, p)[1])
            row = dict(time_min=float(t), a_c=ac, a_m=am, feed_gain=fg, sensor_bias_mol_min=bias,
                       command_mol_min=float(command), command_next_mol_min=float(command),
                       actual_ethanol_mol_min=float(u[0]), water_mol_min=float(u[1]),
                       demand_mol_min=float(demand_mol_min),
                       health_in_map_domain=bool(.4 <= ac <= 1 and .4 <= am <= 1),
                       feed_in_map_domain=bool(U_MIN - 1e-12 <= u[0] <= U_MAX + 1e-12))
            row.update({'true_' + f: float(o[f]) for f in FEATURES})
            row.update({'observed_' + f: float(o[f]) + (bias if f == 'H2_mol_min' else 0.) for f in FEATURES})
            local.append(row)
        if rows:
            # Preserve the pre-event observation while declaring the next command.
            rows[-1]['command_next_mol_min'] = float(command)
        rows.extend(local if not rows else local[1:])
        states.extend(yy if not states else yy[1:])
        for r0, r1 in zip(local[:-1], local[1:]):
            dt = r1['time_min'] - r0['time_min']
            h0, h1 = r0['true_H2_mol_min'], r1['true_H2_mol_min']
            u_start, u_end = r0['actual_ethanol_mol_min'], r1['actual_ethanol_mol_min']
            intervals.append(dict(t_start=r0['time_min'], t_end=r1['time_min'],
                commanded_ethanol_mol_min=float(command), command_start_mol_min=float(command),
                command_end_mol_min=float(command), actual_ethanol_start=u_start, actual_ethanol_end=u_end,
                actual_ethanol_mol=.5 * (u_start + u_end) * dt, commanded_ethanol_mol=command * dt,
                H2_start_mol_min=h0, H2_end_mol_min=h1, H2_produced_mol=.5 * (h0 + h1) * dt,
                H2_demand_mol=demand_mol_min * dt,
                H2_shortfall_mol=.5 * (max(demand_mol_min - h0, 0.) + max(demand_mol_min - h1, 0.)) * dt))
        x = sol.y[:, -1].copy()
        previous_end = b
    diag['wall_seconds'] = time.perf_counter() - tic
    return pd.DataFrame(rows), np.asarray(states), pd.DataFrame(intervals), diag


@lru_cache(maxsize=8)
def _healthy_at10(mode, sample_min, rtol, atol, max_step_min, initialization):
    sc = make_scenario(mode, 'H', 0.)
    settings = _settings(sample_min, rtol, atol, max_step_min)
    if initialization == 'preconditioned':
        pre = _precondition(sc, settings)
        if not pre['metadata']['converged']:
            raise PreconditioningFailure(pre)
        x = pre['state0']
    else:
        x, _, _ = load_ic(mode, 50, False)
    tr, _, _, _ = _integrate(sc, x, [(0., 10., U_SS[mode])],
                            settings, MODES[mode][2])
    return float(tr.iloc[-1]['true_H2_mol_min'])


def run_truth(mode, h, drop=.05, active=False, *, duration_min=21., move_mol_min=.0003,
              controls=None, sample_min=.1, rtol=1e-6, atol=1e-8, max_step_min=.1,
              demand_mol_min=None, initialization='preconditioned', output_dir=None):
    """Generate baseline 0-10 and continued truth through 16 or optional 21 min.

    Returns trace (DataFrame), states (array, one row per trace), intervals
    (DataFrame), scenario, metadata, and snapshots keyed by physical time.
    Features named true_* are physical, observed_* include only deterministic
    sensor bias; root acquisition adds noise and sampling/arrival metadata.
    """
    if duration_min < 10:
        raise ValueError('Diagnostic run must include the t10 passive decision')
    scenario = make_scenario(mode, h, drop, controls)
    settings = _settings(sample_min, rtol, atol, max_step_min)
    x, _, ic = load_ic(mode, 50, False)
    if initialization not in ('preconditioned', 'healthy_ic_stress'):
        raise ValueError('initialization must be preconditioned or explicitly healthy_ic_stress')
    pre = None
    if initialization == 'preconditioned':
        pre = _precondition(scenario, settings)
        if not pre['metadata']['converged']:
            if output_dir is not None:
                dest = Path(output_dir)
                dest.mkdir(parents=True, exist_ok=False)
                _save_preconditioning(pre, dest)
                (dest / 'metadata.json').write_text(json.dumps(dict(schema='ssmr.precondition-failure.v1',
                    scenario=asdict(scenario), source_hashes=source_hashes(mode), preconditioning=pre['metadata']),
                    indent=2, allow_nan=False) + '\n', encoding='utf-8')
            raise PreconditioningFailure(pre)
        x = pre['state0'].copy()
    u0 = U_SS[mode]
    u1 = float(np.clip(u0 + move_mol_min, U_MIN, U_MAX)) if active else u0
    segments = [(0., 10., u0)]
    if duration_min > 10:
        segments.append((10., float(duration_min), u1))
    demand = MODES[mode][2] if demand_mol_min is None else float(demand_mol_min)
    if not np.isfinite(demand) or demand < 0:
        raise ValueError('Demand must be finite and nonnegative')
    trace, states, intervals, diag = _integrate(scenario, x, segments, settings, demand)
    healthy10 = _healthy_at10(mode, sample_min, rtol, atol, max_step_min, initialization)
    row10 = trace.loc[np.isclose(trace.time_min, 10.)].iloc[0]
    metadata = dict(schema='ssmr.dynamic-truth.v1', settings=settings, initial_condition=ic,
        segments=segments, active=bool(active), source_hashes=source_hashes(mode), diagnostics=diag,
        initialization=initialization,
        initial_condition_semantics=('Fixed-health settling from supplied np50 IC; physical t0 follows convergence'
            if pre is not None else 'Explicit stress: supplied healthy np50 IC, without settling, despite possibly degraded health0'),
        preconditioning=None if pre is None else pre['metadata'],
        physical_state0_sha256=sha256(x.astype('<f8').tobytes()).hexdigest(),
        deterioration_semantics='Continuous absolute-time health inside ODE RHS; upper bound 1; no lower clipping',
        drop_semantics='nominal quasi-steady map H2 loss at t10; actual dynamic loss reported separately',
        healthy_dynamic_H2_at10=healthy10,
        actual_dynamic_true_drop_at10=1. - float(row10.true_H2_mol_min) / healthy10,
        actual_dynamic_observed_drop_at10=1. - float(row10.observed_H2_mol_min) / healthy10,
        event_semantics='t10 sample pre-move; command_next is post-event; interval records use post-event command',
        quadrature='Composite trapezoid on per-segment 0.1 min grid (or declared sample_min); positive shortfall endpoints',
        observed_semantics='Truth plus deterministic H2 sensor bias only; no measurement noise drawn',
        state_sha256=sha256(states.astype('<f8').tobytes()).hexdigest())
    result = dict(trace=trace, states=states, intervals=intervals, scenario=asdict(scenario), metadata=metadata)
    result['preconditioning'] = pre
    result['snapshots'] = {str(t): states[np.flatnonzero(np.isclose(trace.time_min, t))[0]].copy()
                           for t in (10., 16., 21.) if np.isclose(trace.time_min, t).any()}
    if output_dir is not None:
        save_truth(result, output_dir)
    return result


def continue_truth(truth, decision_min, command_mol_min, *, horizon_end_min=31., duration_min=None, output_dir=None):
    """Branch from an exact saved decision state; absolute health time continues."""
    trace = truth['trace']
    indices = np.flatnonzero(np.isclose(trace.time_min, decision_min, atol=1e-10, rtol=0.))
    if len(indices) != 1:
        raise ValueError('decision_min must identify exactly one saved state')
    scenario = Scenario(**truth['scenario'])
    settings = truth['metadata']['settings']
    x = truth['states'][indices[0]].copy()
    demand = float(trace.iloc[indices[0]].demand_mol_min)
    end = float(horizon_end_min if duration_min is None else decision_min + duration_min)
    segments = [(float(decision_min), end, float(command_mol_min))]
    tr, states, intervals, diag = _integrate(scenario, x, segments, settings, demand)
    metadata = dict(schema='ssmr.dynamic-continuation.v1', settings=settings, segments=segments,
        source_hashes=source_hashes(scenario.mode), diagnostics=diag,
        parent_state_sha256=truth['metadata']['state_sha256'],
        branch_initial_state_sha256=sha256(x.astype('<f8').tobytes()).hexdigest(),
        parent_decision_min=float(decision_min),
        deterioration_semantics=truth['metadata']['deterioration_semantics'],
        quadrature=truth['metadata']['quadrature'],
        state_sha256=sha256(states.astype('<f8').tobytes()).hexdigest())
    result = dict(trace=tr, states=states, intervals=intervals, scenario=asdict(scenario), metadata=metadata, snapshots={})
    if output_dir is not None:
        save_truth(result, output_dir)
    return result


def save_truth(result, output_dir):
    """Write new evidence only; refuse an existing destination."""
    dest = Path(output_dir)
    dest.mkdir(parents=True, exist_ok=False)
    result['trace'].to_csv(dest / 'truth.csv', index=False, float_format='%.17g')
    result['intervals'].to_csv(dest / 'intervals.csv', index=False, float_format='%.17g')
    np.savez_compressed(dest / 'states.npz', time_min=result['trace'].time_min.to_numpy(), states=result['states'])
    if result.get('preconditioning') is not None:
        _save_preconditioning(result['preconditioning'], dest)
    payload = dict(scenario=result['scenario'], **result['metadata'])
    payload['output_hashes'] = {p.name: _hash(p) for p in dest.iterdir() if p.is_file()}
    (dest / 'metadata.json').write_text(json.dumps(payload, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def _save_preconditioning(pre, dest):
    pre['trace'].to_csv(dest / 'precondition_trace.csv', index=False, float_format='%.17g')
    np.savez_compressed(dest / 'precondition_states.npz',
                        time_min=pre['trace'].precondition_time_min.to_numpy(), states=pre['states'])


def policy_cost(truth, continuation):
    """Account for the causal prefix plus chosen branch, discarding acquisition tail.

    All outputs are physical amounts over a common absolute clock; no financial
    conversion, service downtime, repair benefit, or lifecycle claim is implied.
    """
    decision = continuation['metadata']['parent_decision_min']
    if continuation['metadata']['parent_state_sha256'] != truth['metadata']['state_sha256']:
        raise ValueError('Continuation does not identify this parent trajectory')
    prefix = truth['intervals'].loc[truth['intervals'].t_end <= decision + 1e-10].copy()
    future = continuation['intervals'].copy()
    if prefix.empty or future.empty or abs(prefix.t_end.iloc[-1] - future.t_start.iloc[0]) > 1e-10:
        raise ValueError('Prefix and branch do not meet at the physical decision time')
    joined = pd.concat([prefix, future], ignore_index=True)
    fields = ('actual_ethanol_mol', 'commanded_ethanol_mol', 'H2_produced_mol',
              'H2_demand_mol', 'H2_shortfall_mol')
    values = {field: float(joined[field].sum()) for field in fields}
    return dict(start_min=float(joined.t_start.iloc[0]), end_min=float(joined.t_end.iloc[-1]),
                decision_min=float(decision), intervals=len(joined), **values)
