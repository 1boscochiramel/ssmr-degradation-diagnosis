"""Final binding/report wrapper around the previously frozen acceptance functions."""
from pathlib import Path
import os
for name in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS']:os.environ[name]='1'
import argparse,datetime,hashlib,json,traceback
import numpy as np
from verify_statistical import audit as statistical_audit,clean
from verify_dynamic_records_v3 import audit_tree
from dynamic_source_resolver import make_resolver
from verify_dynamic_resolution import audit as resolution_audit
from verify_policy_records import audit as policy_audit

HERE=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text())
def write(p,data):
    tmp=p.with_suffix(p.suffix+'.tmp');tmp.write_text(json.dumps(clean(data),indent=2,allow_nan=False));tmp.replace(p)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,default=HERE.parent)
    ap.add_argument('--prior-audit-root',type=Path,help='Prior audit tree containing full_rerun and the original extracted submission; default parent of revision root')
    ap.add_argument('--original-archive-path',type=Path,default=Path('C:/Users/Admin/Downloads/ssmr-degradation-diagnosis_audit_2026-09-30.zip'))
    args=ap.parse_args();root=args.root.resolve()
    issues=[];sections={};coverage={};bindings={};complete=True;resolution={}
    def need(ok,label):
        if not ok:issues.append(label)
    protocol=read(root/'protocol.json');summary_path=root/'results/summary.json'
    required=[summary_path,root/'results/calibration.json',root/'results/diagnosis_summary.csv',root/'results/policy_trials.csv',root/'branch_costs.csv',root/'dynamic_status.json']
    missing=[str(p.relative_to(root)) for p in required if not p.exists()]
    if missing:
        write(HERE/'final_check.json',dict(schema='ssmr.revision.independent-check.v2',complete=False,computational_pass=False,issues=['Missing required completed outputs'],missing=missing,bindings={},coverage={},scope='Incomplete; no final scientific verdict from this checker.'))
        print(json.dumps({'status':'INCOMPLETE','missing':missing},indent=2));return 2
    state=read(root/'dynamic_status.json');summary=read(summary_path)
    complete=state.get('status')=='complete' and bool(summary.get('complete'))
    need(complete,'Dynamic/statistical completion not established')
    # Hashes bind the report to exact results. Local timestamps support a local
    # chronology only, not an externally authenticated preregistration claim.
    for name in ['PROTOCOL_FREEZE.json','POLICY_AMENDMENT_FREEZE.json','dynamic_ENGINE_FREEZE.json']:
        manifest=read(root/name)
        for relative,value in manifest['files'].items():need((root/relative).exists() and sha(root/relative)==value,name+'/'+relative)
    source=read(root/'SOURCE_MANIFEST.json')
    for relative,value in source['files'].items():need(sha(root/'reference'/relative)==value,'reference/'+relative)
    coverage['reference_files_preserved']=len(source['files'])
    for mp in (root/'results/batches').glob('*.json'):
        bm=read(mp);tag=f'{bm["case_id"]}_{"active" if bm["active"] else "passive"}'
        need(Path(bm['truth_dir'])==Path('dynamic_truth')/tag,'Batch canonical truth path '+mp.name)
        need(Path(bm['npz_path'])==Path('results/batches')/(mp.stem+'.npz'),'Batch canonical data path '+mp.name)
        need(bm.get('pipeline_sha256')==sha(root/'statistical_campaign.py'),'Batch pipeline identity '+mp.name)
        need(bm.get('policy_sha256')==sha(root/'revision_policy.py'),'Batch policy identity '+mp.name)
    expected_truths={f'{c["id"]}_{"active" if a else "passive"}':(c,a) for c in protocol['cases'] for a in [False,True]}
    truth_records=list((root/'dynamic_truth').glob('*/dynamic_record.json'))
    need({p.parent.name for p in truth_records}==set(expected_truths),'Exact truth-case inventory')
    for key,(case,active) in expected_truths.items():
        p=root/'dynamic_truth'/key
        if not (p/'metadata.json').exists():need(False,'Missing truth '+key);continue
        meta=read(p/'metadata.json');rec=read(p/'dynamic_record.json');sc=meta['scenario']
        need(rec['status']=='complete' and rec['case_id']==case['id'] and rec['active']==active,'Truth identity '+key)
        need(rec['metadata_sha256']==sha(p/'metadata.json'),'Truth metadata hash '+key)
        need(sc['mode']==case['mode'] and sc['hypothesis']==case['h'] and sc['nominal_drop']==case['drop'],'Truth scenario '+key)
        for field,value in case['controls'].items():need(sc[field]==value,'Truth control '+key+'/'+field)
        need(meta.get('initialization')=='preconditioned','Core initialization '+key)
        need(meta['settings']==protocol['solver'],'Solver settings '+key)
    coverage.update(truth_paths_expected=len(expected_truths),truth_paths_present=len(truth_records),branch_paths_expected=sum(c['policy'] for c in protocol['cases'])*2*len(protocol['policy']['decision_times_min'])*protocol['policy']['command_points'])
    coverage['branch_paths_present']=len(list((root/'dynamic_branches').glob('*/dynamic_record.json')))
    need(coverage['branch_paths_expected']==coverage['branch_paths_present'],'Branch inventory')
    # Preservation evidence from the completed earlier audit; read only.
    old=args.prior_audit_root or root.parent;inventory=read(old/'full_rerun/checks/BASELINE_INVENTORY.json')
    for rel,value in inventory['all_archived_hashes'].items():need(sha(old/'ssmr-degradation-diagnosis'/rel)==value,'Original submission changed '+rel)
    previous=read(old/'full_rerun/checks/verification_final.json')
    for rel,value in previous['fresh_output_hashes'].items():need(sha(old/'full_rerun/python_campaign'/rel)==value['sha256'],'Prior rerun output changed '+rel)
    original_zip=args.original_archive_path
    need(sha(original_zip)==inventory['archive_sha256'],'Original archive ZIP changed')
    coverage.update(original_submission_files_preserved=len(inventory['all_archived_hashes']),prior_rerun_data_files_preserved=len(previous['fresh_output_hashes']))
    for name,fn in [('dynamic',lambda:audit_tree(root/'dynamic_truth',(root/'dynamic_branches',),source_resolver=make_resolver(root))),('statistical',lambda:statistical_audit(root,'all')),('policy',lambda:policy_audit(root))]:
        try:
            section=fn()
            if 'pass_' in section:section['pass']=section.pop('pass_')
            destination=HERE/('dynamic_verification_current.json' if name=='dynamic' else name+'_verification.json')
            write(destination,section)
            sections[name]={'pass':section.get('pass',False),'issues':len(section.get('issues',[])),'report_sha256':sha(destination)}
            if name=='dynamic':
                resolution=resolution_audit(root,section)
                resolution['pass']=resolution.pop('pass_');resolution['identity_verification_sha256']=sha(destination)
                write(HERE/'dynamic_resolution.json',resolution)
                sections[name].update(pass_=resolution['pass'],qualified_pass=resolution['pass'],original_gate_pass=False,
                                     identity_corrected_gate_pass=section['pass'],resolution_sha256=sha(HERE/'dynamic_resolution.json'))
                sections[name]['pass']=sections[name].pop('pass_')
            need(sections[name]['pass'],name+' acceptance functions reported discrepancies')
        except Exception as exc:
            sections[name]={'pass':False,'error':repr(exc)};issues.append(name+' checker error: '+repr(exc));(HERE/(name+'_error.log')).write_text(traceback.format_exc())
    # Summary headline checks use independently reconstructed rows, never a
    # positive-performance gate. Failures remain valid scientific results.
    scientific={}
    if sections.get('statistical',{}).get('pass'):
        stats=read(HERE/'statistical_verification.json');rows=stats['recomputed_diagnosis_rows'];core=[x for x in rows if x['group']=='covered_grid']
        expected={'diagnosis_rows':len(rows),'covered_grid_cells':len(core),
                  'maximum_covered_true_rejection_rate':max(x['true_rejected_rate'] for x in core),
                  'maximum_covered_wrong_singleton_rate':max(x['wrong_singleton_rate'] for x in core),
                  'maximum_covered_true_rejection_upper95':max(x['true_rejected_ci_hi'] for x in core),
                  'minimum_covered_correct_singleton_rate':min(x['correct_singleton_rate'] for x in core)}
        for name,value in expected.items():need(np.isclose(summary[name],value,atol=1e-13,rtol=1e-9),'Summary headline '+name)
        coverage.update(stochastic_batches=len(stats['batches']),calibration_strata=stats['calibration_strata'],diagnosis_cells=len(rows))
        scientific['diagnostic_headlines']=expected
    if sections.get('policy',{}).get('pass'):
        pol=read(HERE/'policy_verification.json');need(summary['policy_trial_rows']==pol['policy_trials'],'Summary policy rows')
        coverage['policy_trials']=pol['policy_trials'];scientific['physical_policy_differences']=pol['paired_differences']
    for key,rel in [('protocol_sha256','protocol.json'),('design_freeze_sha256','PROTOCOL_FREEZE.json'),('calibration_sha256','results/calibration.json'),('dynamic_status_sha256','dynamic_status.json')]:need(summary[key]==sha(root/rel),'Summary source binding '+key)
    for rel,value in summary['files'].items():need(sha(root/'results'/rel)==value,'Summary result binding '+rel)
    bound_files=['results/summary.json','results/calibration.json','results/diagnosis_summary.csv','results/policy_trials.csv','results/policy_summary.csv','results/policy_paired_differences.csv','results/EVALUATION_FREEZE.json','dynamic_status.json','branch_costs.csv','checks/MATH_FREEZE.json','checks/INTEGRATION_FREEZE.json',
                 'dynamic_FORENSIC_FREEZE.json','dynamic_forensic_summary.json','checks/dynamic_resolution.json',
                 'checks/dynamic_verification.json','checks/dynamic_verification_current.json','checks/DYNAMIC_IDENTITY_AMENDMENT.json',
                 'checks/DYNAMIC_PORTABLE_ADAPTER.json','checks/verify_dynamic_resolution.py','checks/run_revision_checks.py']
    bindings={'protocol_sha256':sha(root/'protocol.json'),'design_freeze_sha256':sha(root/'PROTOCOL_FREEZE.json'),
              'policy_amendment_freeze_sha256':sha(root/'POLICY_AMENDMENT_FREEZE.json'),'calibration_sha256':sha(root/'results/calibration.json'),
              'dynamic_status_sha256':sha(root/'dynamic_status.json'),'summary_sha256':sha(summary_path),
              'result_files':{rel:sha(root/rel) for rel in bound_files}}
    final=dict(schema='ssmr.revision.independent-check.v2',created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),complete=complete,computational_pass=complete and not issues,
               issues=issues,bindings=bindings,coverage=coverage,sections=sections,scientific_results=scientific,
               qualified=True,original_frozen_dynamic_gate_pass=False,dynamic_resolution=resolution,
               scope='Same-model internal computational verification; rates/cost outcomes may fail scientific aims. Declared finite simulation scenarios and observation assumptions only; no physical validation, global nuisance guarantee, optimal-policy or economic-payback claim.')
    write(HERE/'final_check.json',final);print(json.dumps({k:v for k,v in final.items() if k not in ['bindings','scientific_results']},indent=2));return 0 if final['computational_pass'] else 1

if __name__=='__main__':raise SystemExit(main())
