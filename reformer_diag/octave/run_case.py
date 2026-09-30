"""Run one generated upstream-script case under a named Octave runtime.
Usage: run_case.py CASE_npN {wsl64|win113}
Writes cases/<CASE_npN>/<runtime>/ : run.log, meta.json, trajectory.csv, final_state.mat.
Refuses to overwrite an existing run folder."""
from pathlib import Path
import hashlib, json, os, shutil, subprocess, sys, time

HERE = Path(__file__).resolve().parent
UP = HERE.parent.parent / 'upstream' / 'SSMR_simulator'
WIN_OCTAVE = HERE.parent.parent / 'runtime' / 'claude_octave11'


def wsl(p: Path) -> str:
    s = p.resolve().as_posix()
    return '/mnt/' + s[0].lower() + s[2:]


def find_win_octave():
    hits = sorted(WIN_OCTAVE.rglob('octave-cli.exe'))
    if not hits:
        sys.exit('Octave 11.3 portable not extracted yet')
    return hits[0]


case, runtime = sys.argv[1], sys.argv[2]
src = HERE / 'cases' / case / 'run_case.m'
run = HERE / 'cases' / case / runtime
if run.exists():
    sys.exit(f'{run} exists; preserve it')
run.mkdir(parents=True)
shutil.copy2(src, run / 'run_case.m')
if '_p6' in case or '_p7' in case:
    for helper in ('p6_pattern.m', 'p6_jac.m', 'p6_jacfun.m', 'p7_nonneg.m'):
        shutil.copy2(HERE / helper, run / helper)
    for cached in (HERE / 'pattern_cache').glob('p6_pattern_*.mat'):  # deterministic, from upstream RHS
        shutil.copy2(cached, run / cached.name)
if runtime == 'wsl64':
    cmd = ['wsl.exe', '-d', 'Ubuntu-22.04', '--cd', wsl(run), '--exec', 'env',
           f'SSMR_UPSTREAM={wsl(UP)}', 'OPENBLAS_NUM_THREADS=1', 'OMP_NUM_THREADS=1',
           'octave-cli', '--no-gui', '--quiet', '--eval', 'run_case']
    env = dict(os.environ, MSYS_NO_PATHCONV='1')
    label = 'GNU Octave 6.4.0, Ubuntu 22.04 WSL'
elif runtime == 'win113':
    exe = find_win_octave()
    cmd = [str(exe), '--no-gui', '--quiet', '--eval', 'run_case']
    env = dict(os.environ, SSMR_UPSTREAM=UP.resolve().as_posix(), OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1')
    label = 'GNU Octave 11.3.0 portable Windows'
else:
    sys.exit('runtime must be wsl64 or win113')
meta = {'case': case, 'runtime': label, 'is_matlab': False, 'command': cmd,
        'run_case_sha256': hashlib.sha256((run / 'run_case.m').read_bytes()).hexdigest(),
        'helper_sha256': {q.name: hashlib.sha256(q.read_bytes()).hexdigest() for q in sorted(run.glob('p6_*.m'))},
        'upstream_sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(UP.glob('*.m'))},
        'started': time.strftime('%Y-%m-%dT%H:%M:%S'), 'status': 'RUNNING'}
(run / 'meta.json').write_text(json.dumps(meta, indent=2) + '\n')
t0 = time.monotonic()
with (run / 'run.log').open('x', encoding='utf-8') as log:
    proc = subprocess.Popen(cmd, cwd=run, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, encoding='utf-8', errors='replace')
    for line in proc.stdout:
        log.write(line); log.flush()
    rc = proc.wait()
ok = rc == 0 and (run / 'trajectory.csv').exists()
meta.update(status='COMPLETED' if ok else 'FAILED', exit_code=rc, wall_seconds=round(time.monotonic() - t0, 1),
            finished=time.strftime('%Y-%m-%dT%H:%M:%S'))
(run / 'meta.json').write_text(json.dumps(meta, indent=2) + '\n')
(HERE / 'pattern_cache').mkdir(exist_ok=True)
for made in run.glob('p6_pattern_*.mat'):
    if not (HERE / 'pattern_cache' / made.name).exists():
        shutil.copy2(made, HERE / 'pattern_cache' / made.name)
print(json.dumps(meta, indent=2))
sys.exit(0 if ok else 1)
