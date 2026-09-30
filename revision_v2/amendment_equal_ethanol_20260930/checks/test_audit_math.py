"""Known-value and rejection fixtures; no scientific result files are read."""
import datetime
import hashlib
import json
from pathlib import Path
import unittest
import numpy as np
from audit_math import (MEASURES, account, budget_ok, close, constant_command,
                        difference, require_keys, resource_key, select_window, stats)

def intervals():
    return {'t_start': np.array([10., 11.]), 't_end': np.array([11., 12.]),
            'commanded_ethanol_mol_min': np.array([.002, .002]),
            'actual_ethanol_start': np.array([.002, .002]),
            'actual_ethanol_end': np.array([.002, .002]),
            'H2_start_mol_min': np.array([0., 3.]),
            'H2_end_mol_min': np.array([3., 0.])}

class Fixtures(unittest.TestCase):
    def test_positive_shortfall_before_average(self):
        total, _ = account(intervals(), np.ones(2), np.ones(2))
        self.assertEqual(total['H2_shortfall_mol'], 1.)
    def test_hydrogen_production(self):
        total, _ = account(intervals(), np.ones(2), np.ones(2))
        self.assertEqual(total['H2_produced_mol'], 3.)
    def test_true_resource_not_command(self):
        iv = intervals(); iv['actual_ethanol_start'] *= .5; iv['actual_ethanol_end'] *= .5
        total, _ = account(iv, np.ones(2), np.ones(2))
        self.assertEqual(total['actual_ethanol_mol'], .002)
        self.assertEqual(total['commanded_ethanol_mol'], .004)
    def test_does_not_read_reported_amount(self):
        iv = intervals(); iv['H2_shortfall_mol'] = np.full(2, 900.)
        self.assertEqual(account(iv, np.ones(2), np.ones(2))[0]['H2_shortfall_mol'], 1.)
    def test_nonconstant_endpoint_actual_feed(self):
        iv = intervals(); iv['actual_ethanol_end'] = np.full(2, .004)
        self.assertEqual(account(iv, np.ones(2), np.ones(2))[0]['actual_ethanol_mol'], .006)
    def test_resource_exact_formula(self):
        self.assertEqual(constant_command(.042), .042/21.)
    def test_resource_accept_roundoff(self):
        self.assertTrue(budget_ok(.042+1e-15, .042))
    def test_resource_reject_mismatch(self):
        self.assertFalse(budget_ok(.042+1e-10, .042))
    def test_budget_does_not_include_preperiod(self):
        self.assertFalse(budget_ok(.062, .042))
    def test_reject_lower_bound_without_clipping(self):
        with self.assertRaises(ValueError): constant_command(.001*21)
    def test_reject_upper_bound_without_clipping(self):
        with self.assertRaises(ValueError): constant_command(.003*21)
    def test_reject_nan_budget(self):
        with self.assertRaises(ValueError): constant_command(float('nan'))
    def test_reject_bad_horizon(self):
        with self.assertRaises(ValueError): constant_command(.04, 31., 10.)
    def test_dedupe_only_exact_resource(self):
        b = .042
        self.assertNotEqual(resource_key('m1_C_d05_r1', b), resource_key('m1_C_d05_r1', np.nextafter(b, np.inf)))
    def test_no_merge_across_cases(self):
        self.assertNotEqual(resource_key('m1_C_d05_r1', .042), resource_key('m1_M_d05_r1', .042))
    def test_window_selection(self):
        self.assertTrue(np.array_equal(select_window(intervals(), 11., 12.), [1]))
    def test_reject_cut_interval(self):
        with self.assertRaises(ValueError): select_window(intervals(), 10.5, 12.)
    def test_reject_missing_window(self):
        with self.assertRaises(ValueError): select_window(intervals(), 9., 12.)
    def test_reject_gap(self):
        iv = intervals(); iv['t_start'][1] = 11.1
        with self.assertRaises(ValueError): account(iv, np.ones(2), np.ones(2))
    def test_reject_overlap(self):
        iv = intervals(); iv['t_start'][1] = 10.9
        with self.assertRaises(ValueError): account(iv, np.ones(2), np.ones(2))
    def test_reject_negative_duration(self):
        iv = intervals(); iv['t_end'][0] = 9.
        with self.assertRaises(ValueError): account(iv, np.ones(2), np.ones(2))
    def test_reject_nonfinite_endpoint(self):
        iv = intervals(); iv['H2_end_mol_min'][0] = np.inf
        with self.assertRaises(ValueError): account(iv, np.ones(2), np.ones(2))
    def test_difference_sign(self):
        self.assertEqual(difference({k: 2. for k in MEASURES}, {k: 3. for k in MEASURES}), {k: -1. for k in MEASURES})
    def test_sample_sd(self):
        out = stats([0., 2.]); self.assertEqual(out['mean'], 1.); self.assertEqual(out['sd'], np.sqrt(2.))
    def test_reject_nan_summary(self):
        with self.assertRaises(ValueError): stats([0., np.nan])
    def test_complete_pair_keys(self):
        require_keys([{'i': 0}, {'i': 1}], ['i'], {(0,), (1,)})
    def test_duplicate_pair_rejected(self):
        with self.assertRaises(ValueError): require_keys([{'i': 0}, {'i': 0}], ['i'], {(0,), (1,)})
    def test_missing_pair_rejected(self):
        with self.assertRaises(ValueError): require_keys([{'i': 0}], ['i'], {(0,), (1,)})
    def test_extra_pair_rejected(self):
        with self.assertRaises(ValueError): require_keys([{'i': 0}, {'i': 2}], ['i'], {(0,), (1,)})
    def test_close_rejects_shape_broadcast(self):
        self.assertFalse(close([1., 1.], 1.))

if __name__ == '__main__':
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Fixtures))
    here = Path(__file__).resolve().parent
    out = {'created_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
           'pass': result.wasSuccessful(), 'tests': result.testsRun,
           'failures': [(str(t), s) for t, s in result.failures],
           'errors': [(str(t), s) for t, s in result.errors],
           'files': {n: hashlib.sha256((here/n).read_bytes()).hexdigest() for n in ['audit_math.py', 'test_audit_math.py']}}
    p = here/'math_selftest.json'; tmp = p.with_suffix('.json.tmp')
    tmp.write_text(json.dumps(out, indent=2)+'\n', encoding='utf-8'); tmp.replace(p)
    raise SystemExit(0 if result.wasSuccessful() else 1)
