import copy
import math
import unittest
import numpy as np
from worldline.core import jsd, transport, taxonomy_cost, ilr, inverse_ilr, smoothed_counts, cluster_mentions, build_snapshot, js_contributions, Config
from worldline.demo import generate_windows


class MathematicalTests(unittest.TestCase):
    def test_js_identity_symmetry_bounds_and_relabeling(self):
        p, q = np.array([.1,.2,.7]), np.array([.7,.2,.1])
        self.assertEqual(jsd(p,p),0)
        self.assertAlmostEqual(jsd(p,q),jsd(q,p))
        self.assertAlmostEqual(jsd(p,q),jsd(p[[2,0,1]],q[[2,0,1]]))
        self.assertLessEqual(jsd(p,q),math.log(2))
        self.assertAlmostEqual(jsd([1,0],[0,1]),math.log(2))
        self.assertAlmostEqual(js_contributions(p,q).sum(),jsd(p,q))

    def test_invalid_distributions_fail(self):
        for bad in ([],[0,0],[-1,2],[float('nan'),1],[float('inf'),2]):
            with self.assertRaises(ValueError): jsd(bad,[.5,.5])
        with self.assertRaises(ValueError): smoothed_counts([0,0])

    def test_exact_transport_known_cost_and_identity(self):
        c = np.array([[0,.5,1],[.5,0,1],[1,1,0]])
        self.assertEqual(transport([.2,.3,.5],[.2,.3,.5],c),0)
        self.assertAlmostEqual(transport([1,0,0],[0,1,0],c),.5)
        self.assertAlmostEqual(transport([.5,.5,0],[0,.5,.5],c),.5)
        self.assertAlmostEqual(transport([1,0,0],[0,0,1],c),1)
        with self.assertRaises(ValueError): transport([1,0],[0,1],[[-1,0],[0,0]])

    def test_ilr_roundtrip(self):
        p = smoothed_counts([12,0,32,2,13,5])
        np.testing.assert_allclose(inverse_ilr(ilr(p)),p,atol=1e-12)
        with self.assertRaises(ValueError): ilr([0,1])

    def test_syndication_does_not_multiply_event_count(self):
        original = dict(id="a",title="Institution Alpha makes a synthetic announcement",date="2025-01-01",domain="science",source="a",entities=["Alpha"],region="X")
        copies = [dict(original,id=f"r{i}",source=f"source{i%3}") for i in range(101)]
        clusters = cluster_mentions(copies)
        self.assertEqual(len(clusters),1)
        self.assertEqual(clusters[0]["source_count"],3)
        self.assertEqual(cluster_mentions(copies),cluster_mentions(list(reversed(copies))))

    def test_near_duplicate_but_not_distinct_entity_or_day(self):
        a = dict(id="1",title="The synthetic research group Alpha announces a long detailed measurement of a regional climate signal today",date="2025-01-01",domain="climate",source="a",entities=["Alpha"],region="X")
        b = dict(a,id="2",title=a["title"] + " confirmed")
        self.assertEqual(len(cluster_mentions([a,b])),1)
        self.assertEqual(len(cluster_mentions([a,dict(b,entities=["Beta"])])),2)
        self.assertEqual(len(cluster_mentions([a,dict(b,date="2025-01-02")])),2)


class ChronologyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.windows = generate_windows()
        cls.snapshot = build_snapshot(cls.windows)

    def test_future_changes_do_not_revise_past(self):
        prefix = build_snapshot(self.windows[:130])
        self.assertEqual(prefix["history"],self.snapshot["history"][:100])

    def test_forecast_precedes_observation_and_covariance_is_prior(self):
        for row in self.snapshot["history"]:
            if row["forecast_train_through"]:
                self.assertLess(row["forecast_train_through"],row["date"])
            if row["surprise_raw"] is not None:
                self.assertGreaterEqual(row["covariance_prior_residuals"],20)
            if row["surprise_percentile"] is not None:
                self.assertGreaterEqual(row["calibration_n"],30)
                self.assertFalse(row["calibration_valid"])

    def test_change_observation_does_not_change_own_forecast(self):
        w = copy.deepcopy(self.windows[:130])
        w[-1]["counts"] = [1,90,1,1,1,1]
        altered = build_snapshot(w)["history"][-1]
        old = self.snapshot["history"][99]
        self.assertEqual(altered["forecast_shares"],old["forecast_shares"])
        self.assertNotEqual(altered["surprise_raw"],old["surprise_raw"])

    def test_dropouts_and_source_shifts_suppress(self):
        for t in [150,155,156,157,158,159,160]:
            row = self.snapshot["history"][t-30]
            self.assertFalse(row["coverage_ok"])
            self.assertEqual(row["alert"]["state"],"suppressed")
            self.assertIsNone(row["surprise_raw"])

    def test_injected_break_detected(self):
        rows = self.snapshot["history"]
        candidates = [r for r in rows if r["alert"]["state"] == "candidate"]
        self.assertTrue(any("2025-06-20" <= r["date"] <= "2025-06-28" for r in candidates))
        stable = [r["js_topic"] for r in rows if "2025-05-01" <= r["date"] <= "2025-05-15"]
        shifted = [r["js_topic"] for r in rows if "2025-06-20" <= r["date"] <= "2025-06-28"]
        self.assertGreater(np.mean(shifted),np.mean(stable)*3)

    def test_bad_reference_and_time_order_rejected(self):
        with self.assertRaises(ValueError): build_snapshot(self.windows[:20])
        with self.assertRaises(ValueError): build_snapshot(self.windows[::-1])
        bad = copy.deepcopy(self.windows[:40]); bad[1]["counts"] = [1]*6
        with self.assertRaises(ValueError): build_snapshot(bad)

    def test_empty_window_not_imputed_as_uniform(self):
        w = copy.deepcopy(self.windows[:130]); w[-1]["counts"]=[0]*6;w[-1]["sources"]={}
        row=build_snapshot(w)["history"][-1]
        self.assertIsNone(row["topic_shares"])
        self.assertIsNone(row["js_topic"])
        self.assertEqual(row["alert"]["state"],"suppressed")

if __name__ == '__main__': unittest.main()
