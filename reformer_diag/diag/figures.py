"""Figures for M3/M4 (black-and-white readable: grey fills + letters/hatching, one y-axis each).
Reads outputs_diag/*.json|csv; writes outputs_diag/fig_*.pdf and .png."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

OUT = Path(__file__).resolve().parent / 'outputs_diag'
plt.rcParams.update({'font.size': 9, 'axes.spines.top': False, 'axes.spines.right': False,
                     'axes.grid': True, 'grid.color': '#dddddd', 'grid.linewidth': .6, 'figure.dpi': 150})
REG = {'DISTINGUISHABLE': ('D', '#ffffff'), 'SAME_ACTION': ('s', '#bdbdbd'),
       'DIFFERENT_ACTION': ('X', '#525252'), 'UNREACHABLE': ('', '#f0f0f0')}
HNAME = {'C': 'catalyst', 'M': 'membrane', 'F': 'feed shortfall', 'S': 'H2 sensor drift'}


def save(fig, name):
    for ext in ('pdf', 'png'):
        fig.savefig(OUT / f'{name}.{ext}', bbox_inches='tight')
    plt.close(fig)


def fig_map(suffix):
    d = pd.read_csv(OUT / f'regions{suffix}.csv')
    d = d[d.scale == 1.0]
    cols = [(s, mv) for s in ('S1', 'S2', 'S3', 'S4') for mv in (False, True)]
    fig, axes = plt.subplots(1, 2, figsize=(7.2, 4.4), sharey=True)
    for ax, mode in zip(axes, (1, 2)):
        rows = [(h, dr) for h in 'CMFS' for dr in (.01, .02, .05, .10, .20)]
        for i, (h, dr) in enumerate(rows):
            for j, (s, mv) in enumerate(cols):
                r = d[(d['mode'] == mode) & (d.true == h) & (d['drop'] == dr) & (d.set == s) & (d.move == mv)]
                reg = r.region.iloc[0] if len(r) else 'UNREACHABLE'
                letter, col = REG[reg]
                ax.add_patch(plt.Rectangle((j, i), 1, 1, facecolor=col, edgecolor='#999999', lw=.5))
                ax.text(j + .5, i + .5, letter, ha='center', va='center', fontsize=7,
                        color='white' if reg == 'DIFFERENT_ACTION' else 'black')
        ax.set_xlim(0, len(cols)); ax.set_ylim(len(rows), 0)
        ax.set_xticks(np.arange(len(cols)) + .5)
        ax.set_xticklabels([f'{s}{"+E" if mv else ""}' for s, mv in cols], rotation=60, fontsize=7)
        ax.set_yticks(np.arange(len(rows)) + .5)
        ax.set_yticklabels([f'{HNAME[h]} {int(dr*100)}%' for h, dr in rows], fontsize=7)
        ax.grid(False)
        ax.set_title(f'Mode {mode}' + (' (provisional: no native check at build time)' if mode == 2 and False else ''), fontsize=9)
    axes[0].set_ylabel('true cause and H2 drop at constant feed')
    fig.text(.5, -.06, 'D = distinguishable   s = indistinguishable, same action   X = indistinguishable, different action   blank = not reachable\n'
             'S1 = H2 flow; S2 = +outlet T; S3 = +waste flow; S4 = +micro-GC mole fractions; +E = bounded feed move (+0.0003 mol/min, 5 min)',
             ha='center', fontsize=7)
    fig.suptitle('Operating map' + (' (amendment A1: fixed threshold)' if suffix else ' (frozen threshold)'), fontsize=10)
    save(fig, f'fig_operating_map{suffix}')


def fig_voi(suffix):
    v = json.loads((OUT / f'voi{suffix}.json').read_text())
    labels = [f'{s}{e}' for s in ('S1', 'S2', 'S3', 'S4') for e in ('', '+E')]
    fig, axes = plt.subplots(1, 2, figsize=(7.2, 2.8), sharey=True)
    for ax, mode in zip(axes, (1, 2)):
        h2 = [1e6 * v[f'mode{mode}_scale1.0_{l}']['H2_shortfall_avoided_mol_min'] for l in labels]
        et = [1e6 * v[f'mode{mode}_scale1.0_{l}']['ethanol_excess_avoided_mol_min'] for l in labels]
        x = np.arange(len(labels))
        ax.bar(x - .2, h2, .38, color='#525252', label='H2 shortfall avoided')
        ax.bar(x + .2, et, .38, color='white', edgecolor='#252525', hatch='///', label='ethanol excess avoided')
        ax.set_xticks(x); ax.set_xticklabels(labels, rotation=45, fontsize=7)
        ax.set_title(f'Mode {mode}', fontsize=9)
        ax.axhline(0, color='black', lw=.6)
    axes[0].set_ylabel('avoided, micro-mol/min\n(mean over scenarios, vs S1)')
    axes[0].legend(fontsize=7, frameon=False)
    fig.suptitle('Value of information in operator units' + (' (A1)' if suffix else ' (frozen threshold)'), fontsize=10)
    save(fig, f'fig_voi{suffix}')


def fig_m3():
    r = json.loads((OUT / 'm3_case.json').read_text())
    ps = r['per_sensor_S4']
    names = [p['feature'].replace('_mol_min', '').replace('_m3_min', ' flow').replace('_K', '') for p in ps]
    lvl = [abs(p['residual_after_bias_in_sd']) for p in ps]
    mov = [abs(p['move_residual'] / p['move_sd_of_difference']) for p in ps]
    fig, ax = plt.subplots(figsize=(5.2, 2.8))
    x = np.arange(len(names))
    ax.bar(x - .2, lvl, .38, color='#bdbdbd', edgecolor='#252525', label='steady reading, after bias bound')
    ax.bar(x + .2, mov, .38, color='#252525', label='response to feed move')
    ax.axhline(2.576, color='black', ls='--', lw=.8)
    ax.text(len(names) - .5, 2.7, '2.58 sd', ha='right', fontsize=7)
    ax.set_xticks(x); ax.set_xticklabels(names, fontsize=8)
    ax.set_ylabel('|catalyst - membrane| in noise sd')
    ax.set_title('Mode 1, 5%% H2 drop: catalyst (a_c=%.3f) vs membrane (a_m=%.3f)' % (r['theta']['C'], r['theta']['M']), fontsize=9)
    ax.legend(fontsize=7, frameon=False)
    save(fig, 'fig_m3_residuals')
    tv = pd.DataFrame(r['time_view'])
    fig, ax = plt.subplots(figsize=(5.2, 2.6))
    ax.plot(tv.t_min, tv.a_c, 'k-', lw=2, label="catalyst activity, authors' schedule exp(-0.01 t)")
    ax.plot(tv.t_min, tv.a_m_matching, 'k--', lw=2, label='membrane factor giving identical H2')
    ax.set_xlabel('time (min)'); ax.set_ylabel('activity multiplier (-)')
    ax.set_title('Same H2 signal, very different underlying loss (Mode 1, constant feed)', fontsize=9)
    ax.legend(fontsize=7, frameon=False)
    save(fig, 'fig_m3_timeview')


def fig_v1():
    fig, ax = plt.subplots(figsize=(5.2, 2.6))
    for d, ls, lab in ((1, '-', 'catalyst schedule'), (2, '--', 'membrane schedule')):
        t = pd.read_csv(OUT / f'V1_dynamic_d{d}.csv')
        ax.plot(t.time_min, 1e4 * t.H2_dynamic_mol_min, 'k' + ls, lw=2, label=f'{lab}: full dynamics')
        ax.plot(t.time_min[::10], 1e4 * t.H2_quasisteady_mol_min[::10], 'ko', ms=4, mfc='white' if d == 1 else 'black',
                label=f'{lab}: quasi-steady map')
    ax.set_xlabel('time (min)'); ax.set_ylabel('permeate H2 (1e-4 mol/min)')
    ax.set_title('Validation V1: quasi-steady map vs full dynamics (Mode 1)', fontsize=9)
    ax.legend(fontsize=7, frameon=False)
    save(fig, 'fig_v1_validation')


if __name__ == '__main__':
    for suf in ('', '_A1'):
        fig_map(suf); fig_voi(suf)
    fig_m3(); fig_v1()
    print('figures written')
