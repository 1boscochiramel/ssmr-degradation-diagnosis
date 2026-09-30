"""2-D steady-state maps for M6/M7 (Mode 1): a_c x a_m x u, optionally np=200 or perturbed kinetics.
usage: build_map2d.py {nominal|np200|kinpert} workers
kinpert multiplies the four kinf by [1.1, 0.9, 1.2, 0.8] (declared test perturbation, not a physical claim)."""
from pathlib import Path
import csv, sys, time
from multiprocessing import Pool
import numpy as np

HERE = Path(__file__).resolve().parent
OUT = HERE / 'outputs_diag'
AC = [1.0, .9, .8, .7, .6, .5, .4]
AM = [1.0, .95, .9, .85, .8, .7, .6]
U = {'nominal': [.0018, .0021, .0024, .0027], 'np200': [.0021, .0024], 'kinpert': [.0021, .0024]}
KP = np.array([1.1, .9, 1.2, .8])


def work(args):
    variant, a_c, a_m, u = args
    import faultmodel as fm
    t0 = time.perf_counter()
    n = 200 if variant == 'np200' else 50
    if variant == 'kinpert':
        class KP_(fm.FaultParameters):
            @property
            def kinf(self):
                return fm.KINF * self.a_c * KP
        orig = fm.FaultParameters
        fm.FaultParameters = KP_
    try:
        o, _, info = fm.steady_state(1, a_c, a_m, u, n=n, max_min=15.0)
        row = {**info, **o, 'variant': variant, 'wall_s': round(time.perf_counter() - t0, 1), 'error': ''}
    except Exception as e:
        row = {'variant': variant, 'a_c': a_c, 'a_m': a_m, 'u_etoh': u, 'converged': False, 'error': repr(e)[:200],
               'wall_s': round(time.perf_counter() - t0, 1)}
    finally:
        if variant == 'kinpert':
            fm.FaultParameters = orig
    return row


if __name__ == '__main__':
    variant, workers = sys.argv[1], int(sys.argv[2])
    f = OUT / f'map2d_{variant}.csv'
    pts = [(variant, a, b, u) for a in AC for b in AM for u in U[variant]]
    if variant == 'np200':   # single-fault lines only (cost)
        pts = [p for p in pts if p[1] == 1.0 or p[2] == 1.0]
    done = set()
    if f.exists():
        with f.open() as fh:
            done = {(float(r['a_c']), float(r['a_m']), round(float(r['u_etoh']), 6)) for r in csv.DictReader(fh)}
    todo = [p for p in pts if (p[1], p[2], round(p[3], 6)) not in done]
    fields = ['variant', 'mode', 'np', 'a_c', 'a_m', 'u_etoh', 'u_water', 'converged', 'minutes', 'H2_mol_min', 'T_out_K',
              'waste_m3_min', 'y_H2', 'y_CH4', 'y_CO', 'y_CO2', 'wall_s', 'error']
    new = not f.exists()
    with f.open('a', newline='') as fh, Pool(workers) as pool:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction='ignore')
        if new:
            w.writeheader()
        for i, row in enumerate(pool.imap_unordered(work, todo), 1):
            w.writerow(row); fh.flush()
            print(f'{variant} {i}/{len(todo)} {row["a_c"]} {row["a_m"]} {row["u_etoh"]} {row.get("converged")} {row["wall_s"]}s {row["error"]}', flush=True)
