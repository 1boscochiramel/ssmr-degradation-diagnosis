"""M7 v0 controller comparison on the full dynamic Python plant (PROTOCOL_2026-09-30_M7.md).
Writes outputs/m7_runs.json and outputs/m7_traces/<scenario>_<controller>.csv."""
from pathlib import Path
import itertools, json, sys, time
import numpy as np
import pandas as pd
from scipy.integrate import solve_ivp
from scipy.interpolate import RegularGridInterpolator
from scipy.optimize import minimize, brentq, least_squares
from scipy.stats import chi2

HERE = Path(__file__).resolve().parent
PKG = HERE.parent
sys.path.insert(0, str(PKG)); sys.path.insert(0, str(PKG / 'diag'))
import faultmodel as fm  # noqa: E402
from benchmark_cases import PID, profile  # noqa: E402
OUT = HERE / 'outputs'; (OUT / 'm7_traces').mkdir(parents=True, exist_ok=True)
D = PKG / 'diag' / 'outputs_diag'
DT, SS, UMIN, UMAX = .1, 2.27354e-4, .0018, .0024
TAU, THETA = .0505, .2035                     # FOPDT fit of the Python STEP (outputs/STEP/result.json)
SD_H2 = .005 * SS
FEATS = ['H2_mol_min', 'T_out_K', 'waste_m3_min', 'y_H2', 'y_CH4', 'y_CO', 'y_CO2']
GC = FEATS[3:]


class Map3D:
    def __init__(self):
        d = pd.read_csv(D / 'map2d_nominal.csv'); d = d[d.converged.astype(str) == 'True']
        self.ac, self.am, self.u = (np.sort(d[c].unique()) for c in ('a_c', 'a_m', 'u_etoh'))
        self.f = {}
        for f in FEATS:
            g = d.pivot_table(index=['a_c', 'a_m', 'u_etoh'], values=f)[f]
            arr = np.array([[[g[(a, b, u)] for u in self.u] for b in self.am] for a in self.ac])
            self.f[f] = RegularGridInterpolator((self.ac, self.am, self.u), arr, method='cubic', bounds_error=False, fill_value=None)

    def __call__(self, a_c, a_m, u, f='H2_mol_min'):
        return float(self.f[f]([[a_c, a_m, u]])[0])


MAP = None


def scenario(name):
    if name == 'C1':
        return (lambda t: (1.0, np.exp(-.006 * t))), (lambda k: profile(SS, k, DT, 1)), 30.0
    if name == 'C2':
        return (lambda t: (np.exp(-.01 * t), 1.0)), (lambda k: SS), 30.0
    if name == 'C3':
        return (lambda t: (1.0, np.exp(-.006 * t))), (lambda k: SS * 1.15 if k * DT >= 5 else SS), 30.0
    raise ValueError(name)


class PIDorig:
    def __init__(self): self.p = PID()
    def __call__(self, k, y, sp, u, ctx): return float(np.clip(u + self.p.step(DT, y, sp), UMIN, UMAX)), None


class PItuned:
    def __init__(self):
        K = (MAP(1, 1, .00215) - MAP(1, 1, .00205)) / .0001
        tc = THETA
        self.Kc = TAU / (K * (tc + THETA)); self.Ti = min(TAU, 4 * (tc + THETA)); self.e1 = 0.0
        self.K = K
    def __call__(self, k, y, sp, u, ctx):
        e = sp - y
        du = self.Kc * ((e - self.e1) + DT / self.Ti * e); self.e1 = e
        return float(np.clip(u + du, UMIN, UMAX)), None


class MPC:
    def __init__(self, health=False):
        self.health = health; self.a = np.array([1.0, 1.0]); self.P = np.diag([.05 ** 2, .05 ** 2])
        self.ym = None; self.hist_u = [None, None]; self.d = 0.0; self.declared = None
        self.alpha = np.exp(-DT / TAU); self.nd = int(round(THETA / DT))
    def f(self, u):
        return MAP(self.a[0], self.a[1], u)
    def __call__(self, k, y, sp, u, ctx):
        if self.health and k % 10 == 0 and k > 0:
            self.a, self.P = mhe_update(ctx['meas'], k * DT, self.a, self.P)
        if self.ym is None:
            self.ym = self.f(u); self.hist_u = [u] * (self.nd + 1)
        # model update with the input applied nd steps ago
        self.ym = self.alpha * self.ym + (1 - self.alpha) * self.f(self.hist_u[0])
        self.d += (DT / .5) * ((y - self.ym) - self.d)
        # steady-state target and infeasibility declaration
        g = lambda uu: self.f(uu) + self.d - sp
        infeasible = g(UMAX) < 0
        if infeasible and self.declared is None:
            self.declared = k * DT
        N, blocks = 10, 3
        edges = np.linspace(0, N, blocks + 1).astype(int)
        hu = list(self.hist_u)
        def cost(v):
            seq = np.repeat(v, np.diff(edges))
            ym, J, prev, buf = self.ym, 0.0, u, hu[1:] + [seq[0]]
            for i in range(N):
                ui = buf[i] if i < len(buf) else seq[min(i - len(buf) + 1, N - 1)]
                ym = self.alpha * ym + (1 - self.alpha) * self.f(ui)
                J += ((ym + self.d - sp) / SD_H2) ** 2
            dus = np.diff(np.r_[u, v])
            return J + 10 * np.sum((dus / 1e-4) ** 2)
        x0 = np.full(blocks, u)
        r = minimize(cost, x0, bounds=[(UMIN, UMAX)] * blocks, method='L-BFGS-B', options={'maxiter': 60})
        unew = float(np.clip(r.x[0], UMIN, UMAX))
        if infeasible:
            unew = UMAX
        self.hist_u = self.hist_u[1:] + [unew]
        return unew, ('INFEASIBLE' if infeasible else None)


def mhe_update(meas, t, a, P):
    """M6-style MHE on the last 10 min, samples binned by feed (5e-5 mol/min bins)."""
    w = meas[(meas.t > t - 10) & (meas.t <= t) & (meas.avail <= t)]
    if len(w) < 20:
        return a, P
    w = w.assign(ub=(w.u / 5e-5).round() * 5e-5)
    g = w.groupby(['ub', 'f']).agg(mean=('value', 'mean'), n=('value', 'size'), u=('u', 'mean')).reset_index()
    nom = {f: MAP(1, 1, .0021, f) for f in FEATS}
    def nz(f):
        if f == 'H2_mol_min': return SD_H2, .005 * SS
        if f == 'T_out_K': return .5, 1.0
        if f == 'waste_m3_min': return .01 * nom[f], .02 * nom[f]
        return max(.01 * nom[f], .001), .02 * nom[f]
    P0 = P + np.eye(2) * .002 ** 2
    L0 = np.linalg.cholesky(np.linalg.inv(P0)); prior = a.copy()
    def res(th):
        r = [(row['mean'] - MAP(th[0], th[1], row.u, row.f)) / np.sqrt(nz(row.f)[0] ** 2 / row.n + nz(row.f)[1] ** 2 / 3)
             for _, row in g.iterrows()]
        return np.r_[r, L0.T @ (th - prior)]
    sol = least_squares(res, np.clip(a, [.4, .6], [1, 1]), bounds=([.4, .6], [1, 1]), diff_step=1e-4, max_nfev=30)
    return sol.x, np.linalg.pinv(sol.jac.T @ sol.jac)


def observe(obs):
    c = np.asarray(obs['waste_concentrations_mol_m3'], float); fr = c / c.sum()
    return {'H2_mol_min': obs['hydrogen_mol_min'], 'T_out_K': obs['outlet_temperature_K'], 'waste_m3_min': obs['waste_volume_m3_min'],
            'y_H2': fr[3], 'y_CH4': fr[2], 'y_CO': fr[4], 'y_CO2': fr[5]}


def run(args):
    global MAP
    scen, cname = args
    MAP = Map3D()
    health, sp_fn, T = scenario(scen)
    x, u0, _ = fm.load_ic(1, 50, False)
    u = float(u0[0]); water = u0[1]
    P, Tin, _ = fm.MODES[1]; sp_pat = fm.jacobian_sparsity(50)
    ctrl = {'PID-orig': PIDorig, 'PI-tuned': PItuned, 'MPC': lambda: MPC(False), 'MPC+health': lambda: MPC(True)}[cname]()
    rng = np.random.default_rng(7)
    rngS = np.random.default_rng(11)
    nom = None
    bias = None
    meas_rows = []
    rows = []; ctime = []; declared = None
    for k in range(1, int(T / DT) + 1):
        t0 = (k - 1) * DT
        a_c, a_m = health(k * DT)
        p = fm.FaultParameters(P, Tin, 50, a_c=a_c, a_m=a_m)
        uu = np.array([u, water])
        sol = solve_ivp(lambda t, y: fm.evaluate(y, uu, p)[0], (0, DT), x, method='BDF', rtol=1e-4, atol=1e-5, max_step=.1,
                        jac_sparsity=sp_pat)
        if not sol.success:
            raise RuntimeError(sol.message)
        x = sol.y[:, -1]
        o = observe(fm.evaluate(x, uu, p)[1])
        if nom is None:
            nom = dict(o)
            bias = {f: rngS.uniform(-1, 1) * (.02 * abs(nom[f]) if f != 'H2_mol_min' and f != 'T_out_K' else (1.0 if f == 'T_out_K' else .005 * SS)) for f in FEATS}
        y_meas = o['H2_mol_min'] + rng.normal(0, SD_H2)
        tt = k * DT
        for f in FEATS[:3]:
            sd = SD_H2 if f == 'H2_mol_min' else (.5 if f == 'T_out_K' else .01 * nom[f])
            meas_rows.append((tt, tt, u, f, o[f] + bias[f] + rngS.normal(0, sd)))
        if abs(tt / 3 - round(tt / 3)) < 1e-9:
            for f in GC:
                meas_rows.append((tt, tt + 3, u, f, o[f] + bias[f] + rngS.normal(0, max(.01 * nom[f], .001))))
        sp = sp_fn(k)
        ctx = {'meas': pd.DataFrame(meas_rows, columns=['t', 'avail', 'u', 'f', 'value'])} if cname == 'MPC+health' else {}
        c0 = time.perf_counter()
        unew, flag = ctrl(k, y_meas, sp, u, ctx)
        ctime.append(time.perf_counter() - c0)
        if flag == 'INFEASIBLE' and declared is None:
            declared = tt
        rows.append((tt, sp, o['H2_mol_min'], y_meas, u, a_c, a_m, flag or '',
                     getattr(ctrl, 'a', [np.nan, np.nan])[0], getattr(ctrl, 'a', [np.nan, np.nan])[1]))
        u = unew
    tr = pd.DataFrame(rows, columns=['t', 'sp', 'H2_true', 'H2_meas', 'u', 'a_c', 'a_m', 'flag', 'ac_hat', 'am_hat'])
    tr.to_csv(OUT / 'm7_traces' / f'{scen}_{cname}.csv', index=False)
    # true first infeasible time: demand above what u = UMAX can deliver at the true health (nominal map)
    t_inf = next((r.t for r in tr.itertuples() if MAP(r.a_c, max(r.a_m, .6), UMAX) < r.sp), None)
    t = tr.t.values
    short = np.trapezoid(np.clip(tr.sp - tr.H2_true, 0, None), t)
    res = {'scenario': scen, 'controller': cname,
           'H2_shortfall_mol': float(short), 'shortfall_frac_of_demand': float(short / np.trapezoid(tr.sp, t)),
           'IAE_mol': float(np.trapezoid(np.abs(tr.sp - tr.H2_true), t)),
           'ethanol_per_mol_H2': float(np.trapezoid(tr.u, t) / np.trapezoid(tr.H2_true, t)),
           'bound_violations': int(((tr.u < UMIN - 1e-12) | (tr.u > UMAX + 1e-12)).sum()),
           'mean_compute_ms_per_step': float(1e3 * np.mean(ctime)), 'max_compute_ms_per_step': float(1e3 * np.max(ctime)),
           'infeasible_declared_min': declared, 'true_first_infeasible_min': t_inf,
           'time_at_upper_bound_min': float(DT * (tr.u >= UMAX - 1e-12).sum())}
    print(json.dumps(res), flush=True)
    return res


if __name__ == '__main__':
    from multiprocessing import Pool
    cfgs = list(itertools.product(['C1', 'C2', 'C3'], ['PID-orig', 'PI-tuned', 'MPC', 'MPC+health']))
    with Pool(int(sys.argv[1]) if len(sys.argv) > 1 else 3) as pool:
        res = list(pool.imap_unordered(run, cfgs))
    (OUT / 'm7_runs.json').write_text(json.dumps(sorted(res, key=lambda r: (r['scenario'], r['controller'])), indent=2) + '\n')
    print(pd.DataFrame(res).sort_values(['scenario', 'controller']).to_string())
