"""Tests for src/stats_tools.py — validated against closed-form identities."""
from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import stats_tools as st  # noqa: E402


class TestBetainc(unittest.TestCase):
    def test_identity_a1_b1(self):
        for x in (0.0, 0.1, 0.5, 0.9, 1.0):
            self.assertAlmostEqual(st.betainc(1.0, 1.0, x), x, places=12)

    def test_identity_a1_b2(self):
        # I_x(1, 2) = 1 - (1-x)^2
        for x in (0.2, 0.5, 0.8):
            self.assertAlmostEqual(st.betainc(1.0, 2.0, x), 1.0 - (1.0 - x) ** 2,
                                   places=12)

    def test_symmetric_midpoint(self):
        self.assertAlmostEqual(st.betainc(0.5, 0.5, 0.5), 0.5, places=12)

    def test_complement(self):
        a, b, x = 2.5, 3.5, 0.3
        self.assertAlmostEqual(st.betainc(a, b, x) + st.betainc(b, a, 1.0 - x),
                               1.0, places=12)


class TestStudentT(unittest.TestCase):
    def test_df1_is_cauchy(self):
        # df=1 → Cauchy: two-sided p = 1 - (2/π)·atan(|t|)
        for t in (0.5, 1.0, 2.5, 10.0):
            expected = 1.0 - 2.0 * math.atan(abs(t)) / math.pi
            self.assertAlmostEqual(st.student_t_two_sided_p(t, 1), expected,
                                   places=10)

    def test_df2_closed_form(self):
        # df=2: two-sided p = t²/(2 + t²)... CDF: 1/2 + t/(2·sqrt(2+t²))
        for t in (0.7, 2.0, 4.0):
            tcdf = 0.5 + t / (2.0 * math.sqrt(2.0 + t * t))
            expected = 2.0 * (1.0 - tcdf)
            self.assertAlmostEqual(st.student_t_two_sided_p(t, 2), expected,
                                   places=10)

    def test_large_t_small_p(self):
        self.assertLess(st.student_t_two_sided_p(50.0, 10), 1e-10)


class TestPairedTTest(unittest.TestCase):
    def test_strong_effect(self):
        # 100 pairs, forcing 50 always, greedy ~ N(47.2, 1.8): p must be < 1e-6
        import random
        rng = random.Random(13)
        greedy = [max(40.0, min(50.0, rng.gauss(47.2, 1.8))) for _ in range(100)]
        diffs = [50.0 - g for g in greedy]
        res = st.paired_ttest(diffs)
        self.assertEqual(res["n"], 100)
        self.assertLess(res["p_two_sided"], 1e-6)
        self.assertAlmostEqual(res["mean"], sum(diffs) / 100, places=12)

    def test_null_data_not_significant(self):
        import random
        rng = random.Random(17)
        diffs = [rng.gauss(0.0, 1.0) for _ in range(60)]
        res = st.paired_ttest(diffs)
        self.assertGreater(res["p_two_sided"], 0.05)

    def test_zero_variance_zero_mean(self):
        res = st.paired_ttest([0.0] * 10)
        self.assertEqual(res["p_two_sided"], 1.0)

    def test_needs_two_pairs(self):
        with self.assertRaises(ValueError):
            st.paired_ttest([1.0])


class TestPermutation(unittest.TestCase):
    def test_strong_effect_significant(self):
        diffs = [2.8] * 40 + [1.0] * 10
        p = st.permutation_paired_p(diffs, n_perm=2000, seed=13)
        self.assertLess(p, 0.01)

    def test_deterministic(self):
        diffs = [0.3, -0.1, 0.7, 0.2, 0.9, -0.4, 0.5, 0.1]
        self.assertEqual(st.permutation_paired_p(diffs, n_perm=500, seed=3),
                         st.permutation_paired_p(diffs, n_perm=500, seed=3))


class TestSummarizePairs(unittest.TestCase):
    def test_matches_manual_computation(self):
        f = [50.0] * 5
        g = [47.0, 48.0, 46.0, 49.0, 47.0]
        s = st.summarize_pairs(list(zip(f, g)))
        self.assertEqual(s["n"], 5)
        self.assertEqual(s["forcing_mean"], 50.0)
        self.assertAlmostEqual(s["greedy_mean"], 47.4, places=12)
        self.assertAlmostEqual(s["mean_difference"], 2.6, places=12)


if __name__ == "__main__":
    unittest.main()
