"""Generate per-case copies of the upstream SSMR_simulation.m with only the patches listed in
PROTOCOL_2026-09-29_M1_native_upstream.md (P1-P5). Every substitution must match exactly the
expected number of times, or generation stops. Writes cases/<CASE>_np<N>/run_case.m and
PATCHES.md (per-case diff summary and hashes)."""
from pathlib import Path
import hashlib, re, sys

HERE = Path(__file__).resolve().parent
UP = HERE.parent.parent / 'upstream' / 'SSMR_simulator'
SRC = UP / 'SSMR_simulation.m'

CASES = {
    'STEP': dict(Mode=1, Disturbance=0, Dist_time=1, initial_conditions=0, t=4, setpoint_profile=1, simulation_type=0),
    'CS1':  dict(Mode=1, Disturbance=0, Dist_time=1, initial_conditions=0, t=30, setpoint_profile=1, simulation_type=1),
    'CS2T': dict(Mode=2, Disturbance=1.1, Dist_time=5, initial_conditions=1, t=10, setpoint_profile=0, simulation_type=1),
    'CS2P': dict(Mode=2, Disturbance=2.2, Dist_time=5, initial_conditions=1, t=10, setpoint_profile=0, simulation_type=1),
}


def sub(text, pattern, repl, count, label, log, regex=False):
    n = len(re.findall(pattern, text, flags=re.M)) if regex else text.count(pattern)
    if n != count:
        sys.exit(f'{label}: expected {count} match(es), found {n}')
    text = re.sub(pattern, lambda m: repl, text, flags=re.M) if regex else text.replace(pattern, repl)
    log.append(f'{label}: {count} x `{pattern.strip()}` -> `{repl.strip()[:120]}`')
    return text


def build(case, np_, p6=False, v3=False, p7=False):
    cfg = CASES[case]
    text = SRC.read_text(encoding='utf-8')
    log = []
    # P1 configuration lines (anchored at line start)
    for key, val in list(cfg.items()) + [('np', np_)]:
        text = sub(text, rf'^{key} = [^;]*;', f'{key} = {val};', 1, f'P1 {key}', log, regex=True)
    # P2 path
    text = sub(text, "addpath('ICFull','ICH2O');",
               "UP = getenv('SSMR_UPSTREAM'); addpath(UP, fullfile(UP,'ICFull'), fullfile(UP,'ICH2O'));",
               1, 'P2 path', log)
    # P3 instrumentation after each state hand-over
    text = sub(text, '          x0c = x(end,:);\n',
               "          x0c = x(end,:);\n"
               "          fprintf('ROW %d %.17g %.17g %.17g %.1f\\n', k, y_output(k), u_output(k), y_sp(k), toc); fflush(stdout);\n",
               2, 'P3 instrumentation', log)
    # P4 save then skip plotting, after each toc
    save = ("      toc\n"
            "      out = [time(:), y_output(:), u_output(:), y_sp(:)];\n"
            "      dlmwrite('trajectory.csv', out, 'precision', 17);\n"
            "      save('-mat7-binary', 'final_state.mat', 'x0c', 'u');\n"
            "      fprintf('SAVED trajectory.csv rows=%d\\n', size(out,1)); fflush(stdout);\n"
            "      return;  % P4: plotting skipped (headless); figures redrawn from CSV\n")
    text = sub(text, '      toc\n', save, 2, 'P4 save+skip plots', log)
    # P5 STEP input (open-loop branch only: first ode15s call, which is not preceded by u_output)
    if case == 'STEP':
        call = '          [t,x] = ode15s(@(t,x)SSMR_function(t,x,u,p), [0 t_s], x0c, options);\n          y_output(k) = F_H2;\n          u_output(k) = u(1);\n'
        text = sub(text, call,
                   '          if (k-1)*t_s >= 2 - 1e-9, u(1) = 0.0024; end  % P5 STEP input\n' + call,
                   1, 'P5 STEP input', log)
    # P6 amendment (PROTOCOL_2026-09-30_P6_solver_amendment.md): supplied coloured FD Jacobian
    if p6:
        opt = "    'NonNegative', 1:8*2*np); % Options for the Solver\n"
        text = sub(text, opt, opt + "[P6S, P6G] = p6_pattern(Mode, np, P_in, T_in);  % P6\n", 1, 'P6 pattern', log)
        ode = '          [t,x] = ode15s(@(t,x)SSMR_function(t,x,u,p), [0 t_s], x0c, options);\n'
        if v3:
            ode_new = ode.replace('@(t,x)SSMR_function(t,x,u,p)', '@(t,x)p7_nonneg(t,x,u,p)') if p7 else ode
            text = sub(text, ode, ode_new.replace('x0c, options)', "x0c, odeset(options, 'Jacobian', @(tt,xx) p6_jacfun(xx, u, p, P6S, P6G), 'Mass', speye(numel(x0c)), 'MStateDependence', 'none'))"), 2, 'P6v3 jacobian function', log)
        else:
          text = sub(text, ode,
                   "          P6J = p6_jac(x0c(:), u, p, P6S, P6G);  % P6\n"
                   + ode.replace('x0c, options)', "x0c, odeset(options, 'Jacobian', P6J, 'Mass', speye(numel(x0c)), 'MStateDependence', 'none'))"),
                   2, 'P6 jacobian', log)
    folder = HERE / 'cases' / (f'{case}_np{np_}' + ('_p7' if p7 else '_p6v3' if v3 else '_p6' if p6 else ''))
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / 'run_case.m'
    if target.exists() and target.read_text(encoding='utf-8') != text:
        sys.exit(f'{target} exists with different content; preserve it')
    target.write_text(text, encoding='utf-8')
    return target, log, hashlib.sha256(text.encode()).hexdigest()


if __name__ == '__main__':
    lines = ['# Patches applied to upstream SSMR_simulation.m (generated by make_cases.py)', '',
             f'Upstream SSMR_simulation.m SHA-256: {hashlib.sha256(SRC.read_bytes()).hexdigest()}', '']
    variants = [('untouched', False, False, False), ('P6', True, False, False),
                ('P6v3', True, True, False), ('P7 (P6v3 + NonNegative emulation)', True, True, True)]
    for case in CASES:
        for np_ in (50, 200):
            for label, p6, v3, p7 in variants:
                target, log, h = build(case, np_, p6, v3, p7)
                lines += [f'## {case} np{np_} {label}', f'File: {target.relative_to(HERE).as_posix()}  SHA-256: {h}', '']
                lines += [f'- {l}' for l in log] + ['']
    (HERE / 'PATCHES.md').write_text('\n'.join(lines), encoding='utf-8')
    print('\n'.join(lines))
