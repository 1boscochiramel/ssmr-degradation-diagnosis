# SSMR degradation diagnosis: when is knowing the cause worth the measurement?

A reproducible extension of the SSMR ethanol-steam-reforming benchmark
(Arcila-Osorio, Destro, Ocampo-Martinez, Llorca, Braatz, *Renewable Energy* 256 (2026) 124743,
[doi:10.1016/j.renene.2025.124743](https://doi.org/10.1016/j.renene.2025.124743);
code: [arcmateo/SSMR_Benchmark](https://github.com/arcmateo/SSMR_Benchmark), MIT).

**Status: draft for the author's review (v0.1, 30 Sep 2026). Simulation only.** All claims are
scoped to the benchmark model, the authors' exponential deterioration mechanisms, Modes 1-2,
np = 50 and a declared noise model. No experimental, lifetime or savings claims.

## What is here

| milestone | what | entry point | report |
|---|---|---|---|
| M1 | Python port checked against the authors' code in **native MATLAB R2026a** and GNU Octave | `reformer_diag/octave/`, `reformer_diag/matlab_native/` | `reformer_diag/octave/M1_FINAL_REPORT.md` |
| M2 | measurement layer (noise, bias, delay, micro-GC sampling) and fault hypotheses | `reformer_diag/diag/PROTOCOL_2026-09-30_M2_M4.md` | protocol |
| M3 | worked ambiguity case: catalyst vs membrane loss, and the feed move that separates them | `reformer_diag/diag/m3_case.py` | `diag/outputs_diag/m3_case.json` |
| M4 | three-region operating map and value of information | `reformer_diag/diag/distinguish.py` | `diag/outputs_diag/regions*.csv`, `voi*.json`, figures |
| M5 | technical note v1 | `reformer_diag/note/note_v1.pdf` | `note/verify_note.py` |
| M6 | health estimators (MHE, EKF), held-out histories, model mismatch (v0) | `reformer_diag/estim/` | `estim/outputs/m6_summary*.json` |
| M7 | four controllers on the full dynamic model (v0) | `reformer_diag/control/` | `control/outputs/m7_runs.json` |

Every milestone has a protocol frozen and SHA-256-hashed **before** its results; amendments made
after seeing results are dated and labelled post-hoc, and the frozen result stays the primary
record. Failed checks are kept, not removed.

## Headline findings (details and scope in the reports)

- The Python port matches the authors' code run natively in MATLAB for STEP, CS1, CS2T and CS2P
  (largest H2 difference 0.0564% of nominal; largest IAE difference 0.141%).
- CS1 reproduces the paper's IAE; CS2T and CS2P do not, **in MATLAB too** (about -10.5% and
  -9.3%): the gap is between the released code and the paper, and for CS2T equals one 0.1-min
  sample of start-up error (post-hoc observation, a question for the authors).
- `control.m` keeps PID state in persistent variables that `clear` does not reset; running cases
  back to back in one MATLAB session changes results (use `clear control`).
- With the hydrogen flow alone, no degradation cause is distinguishable; a bounded six-minute
  +0.0003 mol/min ethanol step separates catalyst from membrane loss at a 5% H2 drop.

## Reproduce

```
python get_upstream.py          # clones the pinned upstream commit into ./upstream
python run_all.py               # rebuilds every report, table and figure from saved outputs and runs all verifiers
python run_all.py --full        # also recomputes maps, validation, regions, M3, M6, M7 (hours)
```
Requirements: Python 3.11+, numpy, scipy (>= 1.13), pandas, matplotlib, pyyaml; LaTeX for the note PDF.
Native runs are not automated: `reformer_diag/matlab_native/run_in_matlab_online.m` (MATLAB) and
`reformer_diag/octave/run_case.py` (GNU Octave).

## Licence and credit

This project: MIT (see LICENSE). The benchmark model, parameters and initial conditions are the
work of Arcila-Osorio et al. and are used under their MIT licence; they are fetched, not
redistributed. Parts of this code were drafted with AI assistance (Claude, Codex) and checked by
scripts and by the author.
