"""Write the study design before any calibration or evaluation is generated."""
from pathlib import Path
import json, hashlib, datetime
import numpy as np
from revision_model import Map, SS, U_SS, U_MIN, FEATURES, sensor_settings

ROOT = Path(__file__).resolve().parent

def make():
    if (ROOT/'PROTOCOL_FREEZE.json').exists():
        raise RuntimeError('Frozen protocol already exists; do not replace it.')
    cases=[]; excluded=[]
    for mode in (1,2):
        m=Map(mode)
        for h,rates in [('C',[0,.005,.01]),('M',[0,.003,.006]),('F',[0,.001,.002]),('S',[0,-.0002,-.001])]:
            for drop in (.02,.05,.10):
                theta=m.severity_for_drop(h,drop,U_SS[mode])
                for ri,rate in enumerate(rates):
                    ident=f'm{mode}_{h}_d{int(drop*100):02d}_r{ri}'
                    controls={'sensor_slope_per_min':rate*SS[mode]} if h=='S' else {'rate_per_min':rate}
                    reason=None
                    if theta is None: reason='Nominal-map anchor unreachable in declared input domain'
                    elif h in ('C','M','F') and theta*np.exp(-rate*11)<(U_MIN/U_SS[mode] if h=='F' else .4)-1e-12:
                        reason='Scheduled acquisition leaves the supported map domain before21'
                    if reason:
                        excluded.append(dict(id=ident,mode=mode,h=h,drop=drop,controls=controls,reason=reason));continue
                    central=drop==.05 and (ri==1 if h in ('C','M','F') else ri==0)
                    cases.append(dict(id=ident,mode=mode,h=h,drop=drop,controls=controls,
                                      category='covered_grid',policy=central))
        cases.append(dict(id=f'm{mode}_H',mode=mode,h='H',drop=0.,controls={},category='covered_grid',policy=True))
        for h,rate in [('C',.0075),('M',.0045),('F',.0015),('S',-.0005)]:
            for drop in (.035,.075):
                if m.severity_for_drop(h,drop,U_SS[mode]) is None:continue
                controls={'sensor_slope_per_min':rate*SS[mode]} if h=='S' else {'rate_per_min':rate}
                cases.append(dict(id=f'm{mode}_{h}_offgrid_d{int(drop*1000):03d}',mode=mode,h=h,drop=drop,
                                  controls=controls,category='heldout_parameters',policy=False))
        for h,rate in [('C',.005),('M',.003)]:
            cases.append(dict(id=f'm{mode}_{h}_kinetic',mode=mode,h=h,drop=.05,
                              controls={'rate_per_min':rate,'kinetic_scales':[1.1,.9,1.2,.8]},category='kinetic_mismatch',policy=False))
            cases.append(dict(id=f'm{mode}_{h}_fast',mode=mode,h=h,drop=.05,
                              controls={'rate_per_min':rate*3},category='faster_deterioration',policy=False))
        cases.append(dict(id=f'm{mode}_CM',mode=mode,h='CM',drop=.05,
                          controls={'theta_c10':m.severity_for_drop('C',.025,U_SS[mode]),
                                    'theta_m10':m.severity_for_drop('M',.025,U_SS[mode]),
                                    'rate_c_per_min':.005,'rate_m_per_min':.003},category='out_of_family',policy=False))
    cases.append(dict(id='m2_F_offdomain',mode=2,h='F',drop=.05,controls={'theta10':.95,'rate_per_min':.001},
                      category='out_of_family',policy=False))
    for i,c in enumerate(cases): c['index']=i
    protocol=dict(schema='ssmr.revision.protocol.v2',created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        scope='Simulation-only major revision; original submission and audit are preserved.',
        alpha=.05,n_calibration=499,n_evaluation=1000,n_stress=1000,
        seed_rule='batch_seed=20260930+case.index*100000+phase_offset; offsets calibration0,evaluation10000,stress20000+stress_index*1000. Same draws paired between active/passive; independent across phases.',
        seed_base=20260930,phase_offsets={'calibration':0,'evaluation':10000,'stress':20000},
        looks_min=[16.,21.],baseline_min=[0.,10.],active_move_start_min=10.,active_feed_increment=.0003,
        measurement_windows_min=[[0.,5.],[5.,10.],[11.,16.],[16.,21.]],
        sensor_sets={'S1':FEATURES[:1],'S3':FEATURES[:3],'S4':FEATURES},
        observation_models={str(m):sensor_settings(m) for m in (1,2)},
        stochastic_scope='Independent Gaussian AR1 innovations per instrument; one uniform persistent bias per instrument per record. Exact instruments/noise measurements absent; these are declared assumptions.',
        score='Minimum full-covariance Mahalanobis distance to frozen finite evolving quasi-steady template bank; absolute window means, causal historical GC samples; no chi-square reference and no truth-labelled zero score.',
        calibration='Within each covered finite truth stratum, calibrate maximum true-hypothesis score over both looks by order statistic ceil((n+1)*(1-alpha)); threshold per mode/activity/sensor/hypothesis is maximum across included strata. Membership is retained cumulatively (no reentry). Rank bound marginal over fresh calibration and test draws for each covered fixed truth; no continuum/misspecification guarantee.',
        stopping='First singleton at16 is final. Otherwise sample to21; final singleton is diagnosis, nonempty multiple set INCONCLUSIVE, empty MODEL_INCOMPATIBLE. Report no-call delays censored; time21 is acquisition completion, not diagnosis time.',
        support={'1':['C','M','F','S','H'],'2':['C','M','S','H']},
        diagnostic_reporting='Per-cell true rejection, wrong singleton, correct singleton, inconclusive and incompatible; exact pointwise binomial95% intervals. All trials in denominators. No pooled scenario-average disguised as population rate.',
        initial_state='Precondition supplied initial state at scheduled t0 health with health held fixed; then continuous deterioration inside unchanged ODE RHS. Preserve convergence evidence.',
        solver=dict(method='BDF',np=50,rtol=1e-6,atol=1e-8,max_step_min=.1,sample_min=.1),
        policy=dict(horizon_end_min=31.,decision_times_min=[16.,21.],command_points=7,
                    command_range='u0 to0.0024 inclusive',
                    rule='Maximum minimum-restoring grid command across retained fitted candidate paths to31; infeasible predictions choose upper bound and flagged; empty set keeps baseline and flags incompatibility. No monetary service/recalibration benefits assumed.',
                    report='Whole0..31 true hydrogen shortfall, produced H2, commanded and actual delivered ethanol; prefix+post-decision branch, diagnostic pulse included. Report paired active/passive policy differences and feed-shortfall tradeoff; no single scalar VOI/payback claim.',
                    selection='Predeclared central5% mid-rate C/M/F, constant S and H in covered modes; no outcome-based case selection.'),
        observation_stress=[dict(name='half_noise',noise_scale=.5),dict(name='double_noise',noise_scale=2.),
                            dict(name='strong_correlation',fast_phi=.9,gc_phi=.7),
                            dict(name='drifting_bias',drift_scale=2.),dict(name='gain_error',gain_sd=.01)],
        stress_scope='Frozen nominal thresholds/covariance used unchanged. Observation stresses use policy-selected core cases; physical stresses have independent parameter histories. All are outside exact covered-grid calibration unless stated. Combined/mode2F have no true supported label.',
        cases=cases,excluded=excluded,
        raw_evidence='All deterministic ODE traces, states, branch intervals; all stochastic summary vectors, candidate scores, fit indices, decisions, trial IDs and batch seeds; raw sample exemplars and deterministic regeneration.',
        success_rule='Computational integrity and arithmetic must pass frozen independent checks. Scientific calibration/power/cost failures retained; no mandatory positive benefit, no threshold changes after evaluation. Investigate only implementation defects with versioned reruns. No claim of laboratory validation, universal identifiability, optimal design, or economic payback.')
    p=ROOT/'protocol.json';p.write_text(json.dumps(protocol,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'cases':len(cases),'covered':sum(c['category']=='covered_grid' for c in cases),'excluded':len(excluded),'policy':sum(c['policy'] for c in cases),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}))
    return protocol

if __name__=='__main__':make()
