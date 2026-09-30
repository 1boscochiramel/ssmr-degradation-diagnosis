# Amendment P6 to PROTOCOL_2026-09-29_M1_native_upstream.md: supplied Jacobian

Frozen 2026-09-30 before any P6 run. Authority: Bosco in chat, 2026-09-30, "everhting approaved
jsut give me final output", replying to the speed-up question (declared solver change, labelled).
This also approves the proposed comparison gates (0.5% nominal H2, 1% IAE, 0.5% nominal ethanol).

## Evidence that forced it

Untouched runs completed only interval 1 of 101 (293 s on Octave 6.4 WSL, 617 s on Octave 11.3
Windows); interval 2 of CS2P was unfinished after more than 25 min. Cause measured: upstream RHS
0.11 s per call in Octave; the default finite-difference Jacobian needs 800 calls per rebuild.
Both runs are preserved as ABANDONED_TOO_SLOW.

## The change (only this; P1-P5 unchanged)

1. Once per run, `p6_pattern.m` probes the sparsity of d(RHS)/dx of the UPSTREAM SSMR_function by
   one-at-a-time finite differences at the author-supplied ICFull and ICH2O states of the case's
   mode and grid; takes the union plus the diagonal; groups columns greedily so that no two
   columns in a group share a row (column colouring).
2. At the start of every 0.1-min interval, `p6_jac.m` computes the finite-difference Jacobian of
   the UPSTREAM SSMR_function at the current state and input using those groups (forward
   difference, step sqrt(eps)*max(|x_j|,1)), and passes it to ode15s as the constant
   'Jacobian' option for that interval.
3. RelTol 1e-4, AbsTol 1e-5, MaxStep 0.1, NonNegative, the model, PID, saturation, disturbance
   timing and output definition (y_output = F_H2 from the last RHS call made by ode15s) are
   unchanged. p6_jac is called before ode15s, so it cannot set the recorded F_H2.

## Why this does not change what is being computed

In a BDF method the Jacobian is used only in the Newton iteration matrix. Accepted steps must
still pass ode15s's own local error test at the unchanged tolerances. A less exact Jacobian
costs iterations or step rejections, not accuracy beyond tolerance. The Jacobian comes only from
the upstream Octave RHS; nothing from the Python port enters these runs. The residual difference
from untouched ode15s is at the level of solver tolerance and is reported, not assumed zero:
where the untouched interval 1 exists (CS2P, CS2T), P6 interval 1 is compared with it.

## Labels

Outputs say "upstream script + P6 supplied-Jacobian amendment, GNU Octave <version>". Never
"MATLAB", never "untouched".

## Revision P6v2 (2026-09-30, before any P6 result)

P6v1 stopped at the first ode15s call: Octave's ode15s with a constant 'Jacobian' matrix fails
(`operator +: nonconformant arguments (op1 is 800x800, op2 is 0x0)`) unless a mass matrix is
given. P6v2 adds 'Mass', speye(n), 'MStateDependence', 'none': the identity mass matrix leaves
dx/dt = f(t,x) mathematically unchanged. The failed v1 run folder is kept
(cases/CS2T_np50_p6/wsl64_p6v1_failed_mass).

P6v2 also: the cached pattern is stored as a sparse double (Octave 6.4 could not reload the sparse
logical it saved: `load: reading matrix data for 'S'`). Storage format only. Failed attempt kept
at cases/CS2T_np50_p6/wsl64_p6v2_failed_cacheload.

## Revision P6v3 (2026-09-30 01:45, before any P6 result beyond interval 1)

P6v2 (one constant Jacobian per 0.1-min interval) finished interval 1 of CS2T in 11.6 s but was
still on interval 2 (ethanol enters the steam-filled reactor) after 7 min: a Jacobian frozen
for the whole interval goes stale in that transient and ode15s cannot refresh it. P6v3 passes a
Jacobian FUNCTION (p6_jacfun.m -> p6_jac.m, same coloured differences of the upstream RHS), so
ode15s refreshes it whenever its own logic asks, as it does with its internal differences.
p6_jacfun saves and restores the global F_H2 so the recorded output remains the last RHS call
of the integration itself. Both v2 and v3 runs are kept and labelled; whichever completes is
reported, and where both complete they are compared.

## Amendment P7 (2026-09-30 01:55, before any Mode 2 result)

Evidence: neither Octave 6.4 nor 11.3 ode15s.m contains any NonNegative handling (grep of both
installed files), so the upstream request `'NonNegative', 1:8*2*np` is silently ignored, while
MATLAB's ode15s honours it. P6v3 on CS2T failed at t = 1.95e-7 min of interval 2 with
"corrector convergence failed repeatedly or with |h| = hmin" (steam-only start, ethanol enters).
P7 = P6v3 + p7_nonneg.m wrapping the RHS: for components with x <= 0, dx = max(dx, 0). This
emulates the documented purpose of NonNegative (solution components kept non-negative). MATLAB's
exact internal algorithm is proprietary and not verifiable here; P7 is labelled an emulation.
The Jacobian function still differentiates the unwrapped upstream RHS. Used for Mode 2 (steam
start) cases; Mode 1 cases run P6v2 unless they fail.
