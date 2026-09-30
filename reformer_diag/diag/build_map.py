"""Compute the quasi-steady map (protocol section 1) in parallel; resumable.
Output: outputs_diag/map_mode{m}.csv (one row per grid point, converged flag kept)."""
from pathlib import Path
import csv, sys, time
from multiprocessing import Pool

HERE = Path(__file__).resolve().parent
OUT = HERE / 'outputs_diag'
AC = [1.0, .95, .9, .8, .7, .6, .5, .4]
AM = [.95, .9, .8, .7, .6, .5, .4]
U = [.0018, .0019, .0020, .0021, .0022, .0023, .0024]


def points(mode):
    pts = [(mode, a, 1.0, u) for a in AC for u in U] + [(mode, 1.0, a, u) for a in AM for u in U]
    return pts


def work(pt):
    from faultmodel import steady_state
    mode, a_c, a_m, u = pt
    t0 = time.perf_counter()
    try:
        o, _, info = steady_state(mode, a_c, a_m, u)
        row = {**info, **o, 'wall_s': round(time.perf_counter() - t0, 1), 'error': ''}
    except Exception as e:  # kept, never dropped
        row = {'mode': mode, 'a_c': a_c, 'a_m': a_m, 'u_etoh': u, 'converged': False, 'error': repr(e)[:200],
               'wall_s': round(time.perf_counter() - t0, 1)}
    return row


def main(modes, workers):
    OUT.mkdir(exist_ok=True)
    for mode in modes:
        f = OUT / f'map_mode{mode}.csv'
        done = set()
        if f.exists():
            with f.open() as fh:
                for r in csv.DictReader(fh):
                    done.add((int(r['mode']), float(r['a_c']), float(r['a_m']), float(r['u_etoh'])))
        todo = [p for p in points(mode) if (p[0], p[1], p[2], round(p[3], 6)) not in {(a, b, c, round(d, 6)) for a, b, c, d in done}]
        print(f'mode {mode}: {len(todo)} points to compute', flush=True)
        fields = ['mode', 'a_c', 'a_m', 'u_etoh', 'u_water', 'np', 'converged', 'minutes', 'H2_mol_min', 'T_out_K',
                  'waste_m3_min', 'y_H2', 'y_CH4', 'y_CO', 'y_CO2', 'wall_s', 'error']
        new = not f.exists()
        with f.open('a', newline='') as fh, Pool(workers) as pool:
            w = csv.DictWriter(fh, fieldnames=fields, extrasaction='ignore')
            if new:
                w.writeheader()
            for i, row in enumerate(pool.imap_unordered(work, todo), 1):
                w.writerow(row); fh.flush()
                print(f'mode {mode} {i}/{len(todo)} a_c={row["a_c"]} a_m={row["a_m"]} u={row["u_etoh"]} '
                      f'conv={row.get("converged")} {row["wall_s"]}s {row["error"]}', flush=True)


if __name__ == '__main__':
    main([int(m) for m in sys.argv[1].split(',')], int(sys.argv[2]))
