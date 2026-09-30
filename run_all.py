"""One command to rebuild every report, table and figure and run every verifier.
  python run_all.py          rebuild from saved outputs + verifiers (minutes)
  python run_all.py --full   also recompute maps, validation, regions (frozen and A1), M3, M6 (frozen, A2), M7 (hours)
Native MATLAB/Octave runs are documented, not automated (see README)."""
from pathlib import Path
import os, subprocess, sys

R = Path(__file__).resolve().parent / 'reformer_diag'
PY = sys.executable
FULL = '--full' in sys.argv


def step(cwd, *args, env=None):
    print(f'\n=== {cwd.relative_to(R.parent)}: {" ".join(args)}', flush=True)
    subprocess.run([PY, *args], cwd=cwd, check=True, env={**os.environ, **(env or {})})


if not (R.parent / 'upstream' / 'SSMR_simulator').exists():
    step(R.parent, 'get_upstream.py')
if FULL:
    step(R / 'diag', 'build_map.py', '1,2', '3')
    step(R / 'diag', 'validate.py')
    step(R / 'diag', 'distinguish.py')
    step(R / 'diag', 'distinguish.py', env={'THRESHOLD_MODE': 'A1'})
    step(R / 'diag', 'm3_case.py')
    for v in ('nominal', 'kinpert', 'np200'):
        step(R / 'diag', 'build_map2d.py', v, '3')
    step(R / 'estim', 'm6_estimator.py')
    step(R / 'estim', 'm6_estimator.py', env={'M6_Q_SD': '0.01', 'M6_SUFFIX': '_A2'})
    step(R / 'control', 'm7_controllers.py', '3')
step(R / 'diag', 'figures.py')
step(R / 'octave', 'compare.py')
step(R / 'octave', 'build_report.py')
step(R / 'octave', 'verify_report.py')
step(R / 'note', 'build_note.py')
step(R / 'note', 'verify_note.py')
print('\nrun_all: done (note PDF: run pdflatex twice on reformer_diag/note/note_v1.tex)')
