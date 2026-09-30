# Pre-run numerical-domain extension, authorized recovery

Authority: EXECUTION_AUTHORIZATION_20260929.md. Original failed files and gates remain unchanged.

Instrumentation found the first invalid BDF trial has positive temperatures and only tiny negative separator hydrogen values, saved in outputs/startup_diagnostic. This is not a negative accepted physical trajectory. The original real-domain square root fails on that trial.

Candidate: generate a separate model_numerical_extension.py from the frozen model.py, with exactly two source replacements. Remove the unconditional negative-separator-H2 guard, retaining the nonpositive-temperature guard; add a guard at negative original absolute tolerance (1e-5 mol/m3). Replace only the square-root argument c_H2*R*T by max(c_H2*R*T,0). This extends the zero-permeation branch into a narrow numerical trial domain. Leave all concentrations in transport/reaction/energy equations untouched. No state projection or altered initial arrays. Accepted-state checks in benchmark_cases.py remain unchanged. The extension is not claimed to be identical to MATLAB NonNegative handling.

Freeze the implementation and check hashes before integration. Checks first: exact equality of RHS and observables on supplied valid states for all modes and grids; finite RHS on the captured invalid trial; rejection of negative hydrogen beyond the original absolute tolerance; original model/config/acceptance hashes unchanged. Test these software properties without using paper targets.

Run original CS2T and CS2P with this separately labelled implementation and original settings. Continue independent grid/drift cases using original implementation. Original STEP and CS1 outputs stay primary; use extension for solver consistency on CS2T and original for STEP. Tight BDF/Radau settings stay as previously frozen. Each new failure stops that case and is preserved; other independent checks may proceed under renewed authorization. Do not fit constants or change original thresholds.

Native comparisons require actual original upstream execution. Report both exact source/options attempts and any native compatibility failure. A Python domain extension is not a native trace, not native equivalence and not grounds to release diagnosis gates.
