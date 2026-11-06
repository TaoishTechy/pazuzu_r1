"""Unit and integration tests for src/pazuzu_r1.py (fixed seeds throughout)."""
from __future__ import annotations

import csv
import hashlib
import json
import math
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pazuzu_r1 as pz  # noqa: E402

SCRIPT = ROOT / "src" / "pazuzu_r1.py"


def run_cli(args, expect_ok=True):
    proc = subprocess.run([sys.executable, str(SCRIPT)] + args,
                          capture_output=True, text=True, timeout=120)
    if expect_ok and proc.returncode != 0:
        raise AssertionError(f"CLI failed ({proc.returncode}): {proc.stderr}")
    return proc


def read_trace(path: Path):
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)
    return reader.fieldnames, rows


class TestDeterminism(unittest.TestCase):
    def test_same_seed_byte_identical(self):
        with tempfile.TemporaryDirectory() as tmp:
            outs = []
            for i in range(2):
                out = Path(tmp) / f"trace_{i}.csv"
                run_cli(["--evaluate", "--seed", "13", "--steps", "500",
                         "--output", str(out)])
                outs.append(out.read_bytes())
            self.assertEqual(outs[0], outs[1])

    def test_different_seed_different_trace(self):
        with tempfile.TemporaryDirectory() as tmp:
            outs = []
            for seed in ("13", "42"):
                out = Path(tmp) / f"trace_{seed}.csv"
                run_cli(["--evaluate", "--seed", seed, "--steps", "200",
                         "--output", str(out)])
                outs.append(out.read_bytes())
            self.assertNotEqual(outs[0], outs[1])

    def test_simulate_is_pure(self):
        a = pz.simulate(seed=13, steps=100, mode="pazuzu")
        b = pz.simulate(seed=13, steps=100, mode="pazuzu")
        self.assertEqual(a, b)

    def test_invalid_steps_rejected(self):
        proc = run_cli(["--evaluate", "--steps", "0", "--output",
                        str(Path(tempfile.mkdtemp()) / "x.csv")],
                       expect_ok=False)
        self.assertEqual(proc.returncode, 2)


class TestAcceptanceCriteria(unittest.TestCase):
    """Blueprint §4.2 acceptance criteria."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="pazuzu-test-")
        cls.trace = Path(cls.tmp.name) / "lambda_trace.csv"
        cls.summary = Path(cls.tmp.name) / "lambda_summary.json"
        run_cli(["--evaluate", "--seed", "13", "--steps", "1000",
                 "--output", str(cls.trace),
                 "--snapshot", str(cls.summary),
                 "--seed-override", "strict",
                 "--trl-labels", "--classification-matrix"])
        cls.header, cls.rows = read_trace(cls.trace)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_row_count_plus_header(self):
        self.assertEqual(len(self.rows), 1000)          # data rows
        self.assertEqual(self.header, pz.CSV_COLUMNS)   # header row

    def test_lambda_finite_every_step(self):
        for row in self.rows:
            for col in ("lambda", "raw_dlambda", "error", "eta"):
                value = float(row[col])
                self.assertTrue(math.isfinite(value), f"step {row['step']} {col}")

    def test_monotone_outside_exploration_windows(self):
        lam = [float(r["lambda"]) for r in self.rows]
        windows = [r["exploration_window"] == "1" for r in self.rows]
        for i in range(1, len(lam)):
            if not windows[i]:
                self.assertLessEqual(lam[i], lam[i - 1] + 1e-15,
                                     f"λ increased into non-exploratory step {i}")

    def test_ceiling_respected(self):
        for row in self.rows:
            self.assertLessEqual(float(row["lambda"]), pz.LAMBDA_CEILING + 1e-12)

    def test_governance_floor_respected(self):
        # R1 audit #19: λ_floor = 1e-9 — without it, the strict non-increase
        # rule would let λ ratchet through zero and random-walk negative.
        for row in self.rows:
            self.assertGreaterEqual(float(row["lambda"]), pz.LAMBDA_FLOOR - 1e-12)

    def test_pazuzu_mode_decays_toward_zero(self):
        final = float(self.rows[-1]["lambda"])
        self.assertLess(abs(final), 0.05,
                        f"pazuzu-mode λ did not approach 0: {final}")

    def test_final_lambda_trl_label(self):
        summary = json.loads(self.summary.read_text(encoding="utf-8"))
        self.assertEqual(summary["final_lambda"]["trl"], "Simulation-Emulated")
        self.assertEqual(summary["final_lambda"]["classification"], "Empirical Fit")

    def test_summary_labels_and_decision_ref(self):
        summary = json.loads(self.summary.read_text(encoding="utf-8"))
        self.assertIn("Option C", summary["decision_ref"])
        self.assertGreaterEqual(len(summary["classification_matrix"]), 10)
        self.assertTrue(summary["invariants"]["all_finite"])
        self.assertTrue(summary["invariants"]["monotone_nonincreasing_outside_windows"])

    def test_trace_csv_sha256_recorded(self):
        summary = json.loads(self.summary.read_text(encoding="utf-8"))
        digest = hashlib.sha256(self.trace.read_bytes()).hexdigest()
        self.assertEqual(summary["trace_csv_sha256"], digest)


class TestSubstrateMode(unittest.TestCase):
    """DECISION.md Option C — substrate floor band."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="pazuzu-sub-")
        cls.trace = Path(cls.tmp.name) / "sub.csv"
        run_cli(["--evaluate", "--seed", "13", "--steps", "1000",
                 "--mode", "substrate", "--output", str(cls.trace)])
        cls.header, cls.rows = read_trace(cls.trace)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_floor_never_violated(self):
        for row in self.rows:
            self.assertGreaterEqual(float(row["lambda"]),
                                    pz.LAMBDA_MIN_SUBSTRATE - 1e-9)

    def test_setpoint_is_sophia_floor(self):
        # CSV floats are written with %.9e (10 significant digits), so the
        # round-tripped setpoint matches the floor to that precision only.
        self.assertAlmostEqual(float(self.rows[0]["setpoint"]),
                               pz.LAMBDA_MIN_SUBSTRATE, delta=1e-9)

    def test_final_lambda_in_band(self):
        final = float(self.rows[-1]["lambda"])
        self.assertGreaterEqual(final, pz.LAMBDA_MIN_SUBSTRATE - 1e-9)
        self.assertLessEqual(final, pz.LAMBDA_MIN_SUBSTRATE + 0.05)

    def test_arithmetic_identity(self):
        self.assertLess(abs(pz.LAMBDA_MIN_SUBSTRATE - 0.36362601125), 1e-11)


if __name__ == "__main__":
    unittest.main()
