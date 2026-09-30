# M1 native run of the UNTOUCHED upstream script under GNU Octave (Claude lane)

Frozen 2026-09-29 before any run in this lane. Hash in the sibling .sha256 file.

## Authority

Bosco, in chat, 2026-09-29: "use all reuired open source alternative to matlab and other
software and run it". This authorises installing and running open-source runtimes (GNU Octave)
and running the cases. It does not explicitly approve the new equivalence tolerances proposed
in the same session; results are reported against them and labelled "proposed, not yet
approved". The previously approved M1 gates (2% IAE, 5% time constant) are unchanged.

## Why this lane exists

The other session's native runs (outputs/native_execution/, Octave 6.4 in WSL) execute
`matlab/run_m1_case.m`, a re-implementation of the simulation loop that calls the upstream
functions. If the Python port and that wrapper share a misreading of the loop, their agreement
proves nothing. This lane runs the upstream `SSMR_simulation.m` itself, changing only the
lines listed below, in generated copies. The upstream folder is never written to.

## Runtimes

- R1: GNU Octave 6.4.0, Ubuntu 22.04 WSL (already installed; Ubuntu signed package).
- R2: GNU Octave 11.3.0 portable Windows build, octave-11.3.0-w64.zip, 855,208,207 bytes,
  SHA-256 b0e1bc72a87abe4e2a0cf7e76b7727d8fde5c99ec049c1576f095280c3e48e5a (GitHub release
  asset digest, checked 2026-09-29), extracted under reformer_benchmark/runtime/claude_octave11/.
- Neither is MATLAB. Octave's ode15s is a separate implementation; outputs are labelled
  "native Octave <version>", never "MATLAB".

## Cases (README / paper settings)

| Case | Mode | Disturbance | Dist_time | initial_conditions | t (min) | setpoint_profile | simulation_type | extra |
|---|---|---|---|---|---|---|---|---|
| STEP | 1 | 0 | 1 | 0 | 4 | 1 (unused open loop) | 0 | ethanol step, see P5 |
| CS1 | 1 | 0 | 1 | 0 | 30 | 1 | 1 | |
| CS2T | 2 | 1.1 | 5 | 1 | 10 | 0 | 1 | |
| CS2P | 2 | 2.2 | 5 | 1 | 10 | 0 | 1 | |

Each at np = 50; np = 200 only where run time allows (logged per case). Priority order:
CS2P np50, CS2T np50, CS1 np50, STEP np50, then np200.

## Patch list (applied by make_cases.py to a copy; each substitution asserted to match once)

- P1 configuration: the eight user-setting lines (Mode, Disturbance, Dist_time,
  initial_conditions, t, setpoint_profile, simulation_type, and np) set per the table above.
- P2 path: `addpath('ICFull','ICH2O');` becomes absolute paths to the upstream folder and its
  ICFull, ICH2O subfolders (read from env SSMR_UPSTREAM), so the copy runs outside upstream.
- P3 instrumentation: after each `x0c = x(end,:);` print one ROW line (k, y_output(k),
  u_output(k), y_sp(k), elapsed s) and flush. Prints only; no state or value changes.
- P4 output and headless: after each `toc`, write time, y_output, u_output, y_sp to CSV and
  final state to a MAT file, then `return` before the plotting block (headless Octave in WSL
  cannot render fonts; figures are redrawn from the CSV).
- P5 case definition (STEP only): in the open-loop branch, immediately before its ode15s call,
  `if (k-1)*t_s >= 2 - 1e-9, u(1) = 0.0024; end` (input changes at physical t = 2 min, the
  same convention as the other lane). The upstream script has no step mechanism; this is a
  case change, not a syntax fix. The alternative convention (k*t_s >= 2) is not run unless
  requested.

No other line changes. Solver options, parameters, PID, saturation, disturbance timing
(`k*t_s >= Dist_time + 0.2`) and the output definition (y_output = global F_H2 from the last
RHS call) are exactly upstream.

## Comparisons (computed after the runs; nothing tuned)

1. Upstream-Octave vs published: IAE (conventional trapezoid on y_output against y_sp, and the
   paper-literal formula, both as defined in acceptance.py), approved 2% gate.
2. Upstream-Octave vs the Python port (outputs/<case>/trace.csv) on matched sample index:
   max |dH2| as % of mode nominal H2 (proposed gate 0.5%), IAE relative difference (proposed
   1%), ethanol max |du| as % of nominal ethanol (proposed 0.5%).
3. Upstream-Octave vs the other lane's wrapper-Octave, same metrics, when both exist.
4. R1 vs R2 on any case run in both, same metrics (runtime cross-check, descriptive).

## Stop rules

A runtime error, non-finite state, or complex state stops that case; its log is kept. A
failed comparison is reported with its definition; no parameter, tolerance, or definition is
changed to pass. If upstream-Octave agrees with Python and both miss the paper, the discrepancy
is between the released code and the paper: draft one author question, send nothing.
