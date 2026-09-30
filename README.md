# SSMR degradation diagnosis: when is knowing the cause worth the measurement?

A reproducible extension of the SSMR ethanol-steam-reforming benchmark
(Arcila-Osorio, Destro, Ocampo-Martinez, Llorca, Braatz, *Renewable Energy* 256 (2026) 124743,
[doi:10.1016/j.renene.2025.124743](https://doi.org/10.1016/j.renene.2025.124743);
code: [arcmateo/SSMR_Benchmark](https://github.com/arcmateo/SSMR_Benchmark), MIT).

**Status: technical note v4 and code, v0.2 (1 Oct 2026). Simulation only.** All claims are scoped to the
benchmark model, the authors' exponential deterioration mechanisms, Modes 1-2, np = 50 and a declared
noise model. No experimental, lifetime or savings claims. The current six-page note is
[`revision_v2/amendment_equal_ethanol_20260930/output/pdf/SSMR_TECHNICAL_NOTE_V4.pdf`](revision_v2/amendment_equal_ethanol_20260930/output/pdf/SSMR_TECHNICAL_NOTE_V4.pdf);
every number in it is recomputed from the staged CSVs by
`revision_v2/amendment_equal_ethanol_20260930/note_v4_20261001/verify_note_v4.py` (56/56 checks).

The note is also at the repository root: [`SSMR_TECHNICAL_NOTE_V4.pdf`](SSMR_TECHNICAL_NOTE_V4.pdf).



- `reformer_diag/` : milestones M1-M7 of the first pass (Python port, native MATLAB and Octave
  checks, measurement layer, operating map, note v1, estimators, controllers). Table below.
- `revision_v2/` : the major revision (30 Sep - 1 Oct 2026): calibrated sequential-exclusion
  diagnosis on the full dynamic model with 1000 evaluation episodes per cell, stress tests, the
  feed policy, and two dated control amendments (same-pulse and equal-ethanol) with their frozen
  protocols, independent checkers and the note builders. `revision_v2/STAGING_MANIFEST.json` lists
  every staged file with its SHA-256 and names what is not redistributed (raw per-episode state
  arrays, kept on the author's machine; third-party paper PDFs).

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

## Headline findings (details and scope in the note and reports)

- **Equal ethanol:** a blind constant feed and the diagnosis-based command give the same mean
  hydrogen shortfall within 1.6% in all four central cases. Per episode the diagnostic command is
  better in 841-998 of 1000; the blind arm wins the mean only through the 0-18 episodes per case in
  which the procedure declared the model incompatible and returned feed to nominal. The cost of
  probing is paid when the procedure abstains.
- **Diagnosis:** the feed pulse raises correct calls in the central all-sensor cases (e.g. Mode 1
  catalyst 673 to 882 of 1000, Mode 2 catalyst 349 to 638) with zero wrong calls; hydrogen flow
  alone stays uninformative for catalyst loss (1 to 13 of 1000). All kinetic-mismatch cases reject
  the true cause; healthy plants receive a non-nominal command in about half of all episodes.
- **Benchmark code, three findings for the authors:** (1) under the paper's own Eq. (13) the
  native MATLAB run reproduces case study 1 within 0.2% but the two Mode 2 cases come out 13.4% and
  12.2% below Table 3; (2) `control.m` keeps PID state in persistent variables that `clear` does
  not reset, so back-to-back cases inherit controller history (`clear control`); (3) np = 200 uses
  its own initial-state files and changes start-up hydrogen flow by up to 12% of nominal, so the
  saved runs are not a mesh-convergence test.
- **First pass (M1):** the Python port matches the authors' code run natively in MATLAB for STEP,
  CS1, CS2T and CS2P (largest H2 difference 0.0564% of nominal).

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
redistributed. Parts of this code and of the note drafts were produced with AI assistance (Claude, Codex) and
checked by verification scripts, by a second model reading the note cold, and by the author, who is
responsible for every claim. Some scripts under `revision_v2/` carry absolute paths from the
author's machine; they document the recorded run and are not portable entry points (`run_all.py` is).
