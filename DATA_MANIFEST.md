# Data manifest

Every array used, its origin, units and transformation. Nothing here is plant or experimental data.

| path (under reformer_diag/) | origin | units / content | transformation |
|---|---|---|---|
| (fetched) upstream/SSMR_simulator/ICFull/*.mat, ICH2O/*.mat | authors' benchmark, commit c628084 | x0c: 16*np states (mol/m3, K); u_ss (mol/min) | none (read only) |
| outputs/{STEP,CS1,CS2T_extended,CS2P_extended,...}/trace.csv, dense.csv, result.json | Python port (model.py), M1 | time (min), H2 (mol/min), ethanol, water (mol/min), set-point | CS2T/CS2P use the documented positivity extension (NUMERICAL_EXTENSION_PROTOCOL.md) |
| octave/cases/*/*/trajectory.csv | author script (patched copies, PATCHES.md) under GNU Octave 6.4 / 11.3 | time, y_output, u_output, y_sp | P6 supplied-Jacobian amendment where labelled |
| matlab_native/MATLAB_NATIVE_RESULTS.json | author script in native MATLAB R2026a (MATLAB Online), transcribed from screen | deviations (% of nominal), IAE (mol) | Python traces typed into MATLAB as integers (H2 x 1e10, EtOH x 1e9), checksummed; screenshots in evidence/ |
| diag/outputs_diag/map_mode{1,2}.csv | steady states of the Python port on a fault grid | H2 (mol/min), T_out (K), waste flow (m3/min), mole fractions | a_c scales all kinf; a_m scales pe0 |
| diag/outputs_diag/map2d_{nominal,kinpert,np200}.csv | 2-D steady-state grids (Mode 1) | as above | kinpert: kinf x [1.1, 0.9, 1.2, 0.8] (declared test perturbation); np200: fine grid, single-fault lines |
| diag/outputs_diag/V1_dynamic_d{1,2}.csv | full dynamic runs of the authors' disturbances 3 and 4 | H2 dynamic vs quasi-steady (mol/min) | none |
| diag/outputs_diag/regions*.csv, voi*.json, structural.json, m3_case.json | computed from the maps under the declared noise model | regions, Lambda statistics, mol/min | frozen threshold and amendment A1 |
| estim/outputs/m6_*.csv/json, m6_traces_*/ | simulated measurements (seeded) and estimator outputs | multipliers (-), covariances, calls | frozen v0 and amendment A2 |
| control/outputs/m7_runs.json, m7_traces/ | closed-loop runs on the full dynamic Python model | H2 (mol/min), u (mol/min), set-point | seeded measurement noise |

Not included: digitised curves of the paper's figures and the paper PDFs (copyright); they were used
only for screening in M1 and are not needed to rerun anything here.
