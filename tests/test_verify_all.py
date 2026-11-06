"""Tests for src/verify_all.py — placeholder detection, manifest integrity,
P1/P2 recomputation on clearly-labeled SYNTHETIC fixtures, decision parsing."""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import verify_all as va  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures"


class TestPlaceholderDetection(unittest.TestCase):
    def test_known_fake_prefix_rejected(self):
        digest = hashlib.sha256(b"pazuzu").hexdigest()
        tampered = "a3f8c2d1" + digest[8:]
        self.assertTrue(va.placeholder_reasons(tampered))

    def test_repeated_block_rejected(self):
        self.assertTrue(va.placeholder_reasons("a3f8c2d1" * 8))

    def test_repeated_nibble_run_rejected(self):
        self.assertTrue(va.placeholder_reasons("0" * 64))

    def test_arithmetic_progression_rejected(self):
        self.assertTrue(va.placeholder_reasons("0123456789abcdef" * 4))

    def test_short_rejected(self):
        self.assertTrue(va.placeholder_reasons("a3f8c2d1"))

    def test_non_hex_rejected(self):
        self.assertTrue(va.placeholder_reasons("a3f8c2d1…" + "a" * 55))

    def test_real_digest_accepted(self):
        for blob in (b"pazuzu", b"hor-qudit", b"\x00\x01\x02"):
            digest = hashlib.sha256(blob).hexdigest()
            self.assertEqual(va.placeholder_reasons(digest), [], digest)


class TestManifestIntegrity(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="pazuzu-man-"))
        (self.tmp / "src").mkdir()
        (self.tmp / "src" / "a.txt").write_text("hello\n")
        (self.tmp / "src" / "b.txt").write_text("world\n")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write_manifest(self):
        lines = []
        for rel in ("src/a.txt", "src/b.txt"):
            digest = hashlib.sha256((self.tmp / rel).read_bytes()).hexdigest()
            lines.append(f"{digest} {rel}")
        (self.tmp / "MANIFEST.sha256").write_text("\n".join(lines) + "\n")

    def test_ok_manifest(self):
        self._write_manifest()
        with patch.object(va, "ROOT", self.tmp):
            status, detail = va.check_manifest(self.tmp / "MANIFEST.sha256")
        self.assertEqual(status, "RESOLVED")
        self.assertEqual(detail["verified"], 2)

    def test_tampered_file_detected(self):
        self._write_manifest()
        (self.tmp / "src" / "b.txt").write_text("tampered\n")
        with patch.object(va, "ROOT", self.tmp):
            status, detail = va.check_manifest(self.tmp / "MANIFEST.sha256")
        self.assertEqual(status, "FAILED")
        self.assertEqual(len(detail["mismatches"]), 1)
        self.assertEqual(detail["mismatches"][0]["path"], "src/b.txt")

    def test_placeholder_digest_in_manifest_detected(self):
        (self.tmp / "MANIFEST.sha256").write_text(
            f"{'a3f8c2d1' * 8} src/a.txt\n")
        with patch.object(va, "ROOT", self.tmp):
            status, detail = va.check_manifest(self.tmp / "MANIFEST.sha256")
        self.assertEqual(status, "FAILED")
        self.assertTrue(detail["placeholders"])

    def test_missing_entry_detected(self):
        digest = "0" * 64
        (self.tmp / "MANIFEST.sha256").write_text(f"{digest} src/gone.txt\n")
        with patch.object(va, "ROOT", self.tmp):
            status, detail = va.check_manifest(self.tmp / "MANIFEST.sha256")
        self.assertEqual(status, "FAILED")
        self.assertEqual(detail["missing"], ["src/gone.txt"])


class TestDecisionCheck(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="pazuzu-dec-"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write(self, text):
        (self.tmp / "DECISION.md").write_text(text)

    def test_option_c_accepted(self):
        self._write("# Decision\n**Decision: Option C — mode split.**\n")
        with patch.object(va, "ROOT", self.tmp):
            status, detail = va.check_decision()
        self.assertEqual(status, "RESOLVED")
        self.assertEqual(detail["chosen"], ["C"])

    def test_mentions_of_a_b_elsewhere_do_not_confuse(self):
        # Real-world shape: consequences may reference the rejected options.
        self._write(
            "# DECISION — contradiction\n\n"
            "## Decision: Option C — mode split\n\n"
            "5. A future revision that retires λ(T)=0 (Option A) or re-scopes "
            "the floor (Option B) must replace this file.\n")
        with patch.object(va, "ROOT", self.tmp):
            status, detail = va.check_decision()
        self.assertEqual(status, "RESOLVED")
        self.assertEqual(detail["chosen"], ["C"])

    def test_option_b_rejected_for_c_semantics(self):
        self._write("Decision: Option B — arithmetic only.\n")
        with patch.object(va, "ROOT", self.tmp):
            status, _ = va.check_decision()
        self.assertEqual(status, "FAILED")

    def test_missing_decision_falsified(self):
        with patch.object(va, "ROOT", self.tmp):
            status, _ = va.check_decision()
        self.assertEqual(status, "FALSIFIED")


class TestP1P2OnSyntheticFixtures(unittest.TestCase):
    """The fixtures are SYNTHETIC — they validate the recompute code paths
    only and are never cited as experimental evidence."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="pazuzu-p12-"))
        (self.tmp / "data").mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_p1_recompute_on_synthetic(self):
        shutil.copy(FIXTURES / "synthetic_p1_forcing_vs_greedy.csv",
                    self.tmp / "data" / "p1_forcing_vs_greedy.csv")
        with patch.object(va, "ROOT", self.tmp):
            status, detail = va.check_p1()
        self.assertEqual(status, "RESOLVED")
        self.assertEqual(detail["stats"]["n"], 100)
        self.assertEqual(detail["stats"]["forcing_mean"], 50.0)
        self.assertAlmostEqual(detail["stats"]["greedy_mean"], 47.2, delta=1.8)
        self.assertLess(detail["stats"]["p_two_sided"], 0.001)
        self.assertTrue(all(detail["acceptance"].values()))

    def test_p2_recompute_on_synthetic(self):
        shutil.copy(FIXTURES / "synthetic_p2_h1_detection.json",
                    self.tmp / "data" / "topos_h1_detection.json")
        with patch.object(va, "ROOT", self.tmp):
            status, detail = va.check_p2()
        self.assertEqual(status, "RESOLVED")
        self.assertTrue(detail["all_errors_detected"])
        self.assertAlmostEqual(detail["false_positive_rate"], 3.0 / 64.0,
                               places=12)
        self.assertAlmostEqual(detail["false_positive_rate_percent"], 4.7,
                               delta=0.01)

    def test_p1_open_without_data(self):
        with patch.object(va, "ROOT", self.tmp):
            status, detail = va.check_p1()
        self.assertEqual(status, "OPEN")
        self.assertIn("absent", detail["reason"])

    def test_p2_open_without_data(self):
        with patch.object(va, "ROOT", self.tmp):
            status, _ = va.check_p2()
        self.assertEqual(status, "OPEN")


class TestFloorArithmetic(unittest.TestCase):
    def test_identity_matches_spec(self):
        status, detail = va.check_substrate_floor_arithmetic()
        self.assertEqual(status, "RESOLVED")
        self.assertTrue(detail["matches"])
        self.assertLess(detail["abs_difference"], 1e-11)


if __name__ == "__main__":
    unittest.main()
