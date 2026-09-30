# Response time: two explicit definitions

Descriptive reanalysis of preserved Python STEP output and the digitised published simulation curve. Neither is experimental validation.

| Curve | 63.2% crossing, absolute (min) | Elapsed from input (min) | Shared fitted dead time (min) | 63.2% rise AFTER dead time (min) | FOPDT fitted tau (min) |
|---|---:|---:|---:|---:|---:|
| python | 2.26124861 | 0.26124861 | 0.20346503 | 0.05778358 | 0.05047303 |
| paper | 2.25145757 | 0.25145757 | 0.19308318 | 0.05837439 | 0.05116719 |

The input step occurs at physical time 2 min. The direct threshold is baseline + 0.632*(final-baseline); baseline and final windows are 1.8-2.0 and 3.8-4.0 min. The first crossing is linearly interpolated. Both definitions use the same FOPDT-fitted delay on their own curve; the direct statistic is not an independent dead-time estimate. FOPDT fitting, starts, bounds, window and plateaus use the unchanged acceptance.py.

The ORIGINAL FAILED CRITERION used FOPDT fitted tau against the paper textual approximate tau of 0.25 min with the approved 5% tolerance. It did not use direct threshold crossing or elapsed time from the input step. That failed gate remains failed. No alternative target or tolerance replaces it.

The paper curve is vector-digitised and interpolated on the previously used sample grid. Displayed decimal places aid reproducibility, not a claim of experimental precision. Reference rounding bounds are in references/manifest.json. The printed approximate dynamics description may use a different convention; author/native evidence is still needed.
