Independent verification entry points

Run from the revision directory with the supplied compatible Python environment:
  python checks/run_revision_checks.py

If the supplied original archive or extracted prior audit is elsewhere:
  python checks/run_revision_checks.py --root ABSOLUTE_REVISION_PATH --prior-audit-root ABSOLUTE_PRIOR_PATH --original-archive-path ABSOLUTE_ZIP_PATH
The prior audit directory must contain full_rerun/ and the original extracted
ssmr-degradation-diagnosis/ directory. A historical ZIP must first be extracted.
The dynamic source/initial-condition reader explicitly remaps its recorded
artifact root to --root, validates the original file hashes, and changes no
metadata. All other data must retain the supplied relative directory structure.

The final check produces checks/final_check.json and the statistical, physical
policy, current dynamic and dynamic-resolution reports. This final wrapper is
for auditing the supplied recorded campaign, including its preserved failed
exact-export check and subsequent forensic evidence. Fresh-run verification
must use evidence from that fresh run. Copying the supplied forensic evidence
into a new simulation tree does not establish its provenance.

Frozen acceptance functions
MATH_FREEZE.json fixes the independent numerical/rank/covariance primitives.
INTEGRATION_FREEZE.json fixes raw observation regeneration, causal sampling,
scores, thresholds, sequential decisions, rates/confidence intervals, physical
action selection, interval integration and result aggregation checks. Statistical
and policy acceptance functions have not been tuned to the observed outcomes.
The mathematical checks preceded physical generation; integration checks were
frozen before stochastic calibration or held-out evaluation was generated.
Local file timestamps establish local chronology, not external preregistration.

Calibration only:
  python checks/verify_statistical.py --root . --phase calibration --out checks/calibration_verification.json
All diagnostic batches:
  python checks/verify_statistical.py --root . --phase all --out checks/statistical_verification.json
These reconstruct observations from the frozen RNG law and seeds, verify saved
raw exemplars, independently evaluate all score minima, and recompute all
reported counts and exact pointwise binomial intervals. A scientific failure
or inconclusive outcome does not make a correctly reconstructed result fail.

Dynamic exception retained, not erased
dynamic_verification.json is the original failed exact-output audit. The
original checker confused sensor-bias scenarios with healthy scenarios when
their physical state hashes were identical. verify_dynamic_records_v2.py adds
scenario identity to the lookup key; v3 additionally supports explicit read-only
source-path relocation. Every numerical and exact-state gate remains unchanged.

dynamic_verification_current.json preserves the remaining failure: dense-output
evaluation of a segment's first sample can differ from its exact supplied input.
verify_dynamic_resolution.py separately checks exact input provenance, exact
full regenerated state arrays, identical regenerated truth/interval CSV bytes,
and the forensic solver-input captures for every affected record. It also
requires every remaining issue to be precisely this export discrepancy and
checks that the original source/data bytes are unchanged.

A qualified final computational pass therefore does not mean that every
original frozen gate passed. The final JSON must expose qualified=true,
original_frozen_dynamic_gate_pass=false and the explicit dynamic_resolution.
The final report must disclose the limitation. No numeric tolerance was relaxed.

Scope
This is same-model internal verification of computation and record integrity.
It is not cross-model review, an independently coded reactor solver, physical
validation, instrument qualification, uniform nuisance-space coverage, proof of
optimal control, or a financial payback calculation. Noise replication around a
finite library of deterministic trajectories is not independent physical-run
replication. Calibration guarantees are limited to the declared finite covered
histories and nominal observation law; stress cases are reported separately.
