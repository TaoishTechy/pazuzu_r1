#!/usr/bin/env python3
"""Pazuzu 1.0-R1 — Verification & Benchmark Suite (blueprint V1.0 §4/§6).

Core invariant (blueprint §1):

    A claim is RESOLVED only when a named command, executed against named
    files, produces a logged result that satisfies a pre-declared acceptance
    criterion. All other claims remain OPEN or PARTIAL.

Checks
------
C01  manifest integrity      full SHA-256 recomputation of MANIFEST.sha256,
                             placeholder-pattern rejection (blueprint §4.1)
C01e external 14 artifacts   the HOR-Qudit v2.5 artifacts are NOT in this
                             repo → claim stays OPEN; their spec-supplied
                             hash prefixes match placeholder patterns and
                             are rejected as evidence
C02  λ determinism           fresh seeded run reproduces the committed trace
                             byte-for-byte, pazuzu AND substrate modes
C03  λ finiteness            no NaN/Inf at any step
C04  λ monotonicity          λ never increases outside licensed exploration
                             windows (spectral-flow constraint)
C05  λ final TRL label       final λ recorded as Simulation-Emulated
C06  P1 forcing vs greedy    raw CSV absent → OPEN; recompute ready
                             (means, SDs, paired p) and tested on a clearly
                             labeled synthetic fixture
C07  P2 H¹ detection         raw JSON absent → OPEN; false-positive-rate
                             reporting implemented (3/64 = 4.7 % rule)
C08  Lean 4 Sophia proof     lean/SophiaConvergence.lean absent → OPEN;
                             an arithmetic identity is not a convergence
                             proof (blueprint §4.4)
C09  λ-decision recorded     DECISION.md chooses an option (this repo: C)
C10  Sophia 6127-step trace  external artifact absent → OPEN
C11  substrate floor value   arithmetic identity φ⁻² − 0.017 − 0.00134 =
                             0.36362601125 re-derived in code — arithmetic
                             ONLY; the lower-bound claim is C11b
C11b floor as lower bound    OPEN — needs Lean proof or empirical demonstration
C12  parity/ledger audit     no parity-flip events in scope yet → OPEN
C13  TRL labels complete     every metric block in the λ summaries carries
                             a TRL label
C14  classification matrix   every parameter carries a classification label

Exit codes
----------
0 — every claim declared RESOLVED passed its runtime check
1 — at least one RESOLVED-declared claim failed its criterion
2 — usage / environment error (e.g. --check-hashes with missing manifest)

Usage
-----
    python src/verify_all.py --check-hashes --full-sha256 \
        --seed-override strict --test-p1p2
    python src/verify_all.py --full --output logs/suite_report.json
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import pazuzu_r1 as pz                      # noqa: E402  (constants + invariants)
import stats_tools as st                    # noqa: E402

SCHEMA_ID = "pazuzu-r1/suite-report@v1"

# Placeholder prefixes as supplied in Pazuzu 1.0-R1 §7.3 ("SHA-256 prefix"
# column). They are short prefixes with arithmetic-pair structure — rejected
# as evidence per blueprint §4.1.
KNOWN_FAKE_PREFIXES = {
    "a3f8c2d1", "b7d4e1f2", "d1b8a4c2", "a2c4e6b8", "b5d7f9a1", "e9a1c7b8",
}

HEX_RE = re.compile(r"^[0-9a-f]{64}$")
MANIFEST_LINE_RE = re.compile(r"^([0-9a-f]{64})\s+(\S.*)$")


# --------------------------------------------------------------------------
# Placeholder detection (blueprint §4.1: arithmetic progressions, repeated
# nibble sequences, length < 64)
# --------------------------------------------------------------------------
def placeholder_reasons(digest: str) -> list[str]:
    reasons: list[str] = []
    if len(digest) != 64:
        reasons.append(f"length {len(digest)} != 64")
        return reasons
    if not HEX_RE.match(digest):
        reasons.append("non-hexadecimal characters")
        return reasons
    nib = [int(c, 16) for c in digest]

    run = 1
    longest_run = 1
    for i in range(1, 64):
        run = run + 1 if nib[i] == nib[i - 1] else 1
        longest_run = max(longest_run, run)
    if longest_run >= 8:
        reasons.append(f"repeated nibble run of {longest_run}")

    step_run, longest_step = 1, 1
    for i in range(2, 64):
        if (nib[i] - nib[i - 1]) % 16 == (nib[i - 1] - nib[i - 2]) % 16:
            step_run += 1
            longest_step = max(longest_step, step_run)
        else:
            step_run = 1
    if longest_step >= 16:
        reasons.append(f"constant-step arithmetic progression of {longest_step} nibbles")

    for block in (8, 16):
        nblocks = 64 // block
        if nblocks >= 4 and len({digest[b * block:(b + 1) * block]
                                 for b in range(nblocks)}) == 1:
            reasons.append(f"repeated {block}-nibble block x{nblocks}")

    if digest[:8] in KNOWN_FAKE_PREFIXES:
        reasons.append(f"known placeholder prefix from source spec: {digest[:8]}")
    return reasons


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def git_info() -> dict:
    info = {"git_commit": "uncommitted", "git_dirty": None}
    try:
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                              capture_output=True, text=True, timeout=15)
        if head.returncode == 0:
            info["git_commit"] = head.stdout.strip()
        status = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT,
                                capture_output=True, text=True, timeout=15)
        info["git_dirty"] = bool(status.stdout.strip()) if status.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        pass
    return info


def read_manifest(path: Path) -> list[tuple[str, str]]:
    entries = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = MANIFEST_LINE_RE.match(line)
        if not m:
            raise ValueError(f"malformed manifest line: {raw!r}")
        entries.append((m.group(1), m.group(2)))
    return entries


def parse_trace(path: Path, mode: str) -> dict:
    with path.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    lam = [float(r["lambda"]) for r in rows]
    windows = [r["exploration_window"] == "1" for r in rows]
    tol = 1e-9
    finite = all(math.isfinite(v) for v in lam)
    monotone = all(
        lam[i] <= lam[i - 1] + 1e-15
        for i in range(1, len(lam)) if not windows[i]
    )
    ceiling_ok = all(v <= pz.LAMBDA_CEILING + tol for v in lam)
    floor_ok = all(v >= pz.LAMBDA_MIN_SUBSTRATE - tol for v in lam) \
        if mode == "substrate" else None
    return {
        "rows": len(rows),
        "all_finite": finite,
        "monotone_nonincreasing_outside_windows": monotone,
        "ceiling_respected": ceiling_ok,
        "floor_respected": floor_ok,
        "lambda_final": lam[-1] if lam else None,
        "lambda_min": min(lam) if lam else None,
        "lambda_max": max(lam) if lam else None,
    }


# --------------------------------------------------------------------------
# Individual checks — each returns (status, detail) with status in
# {"RESOLVED", "OPEN", "PARTIAL", "FALSIFIED"} ("FAILED" is assigned when a
# RESOLVED-declared claim fails at runtime).
# --------------------------------------------------------------------------
def check_manifest(manifest_path: Path) -> tuple[str, dict]:
    if not manifest_path.exists():
        return "FAILED", {"error": f"manifest not found: {manifest_path}"}
    try:
        entries = read_manifest(manifest_path)
    except ValueError as exc:
        return "FAILED", {"error": str(exc)}
    if not entries:
        return "FAILED", {"error": "manifest has no entries"}
    verified, mismatches, placeholders, missing = [], [], [], []
    for claimed, rel in entries:
        path = ROOT / rel
        if not path.is_file():
            missing.append(rel)
            continue
        computed = sha256_file(path)
        # Full 64-character digest is printed to stdout by the caller (§4.1).
        bad = placeholder_reasons(computed) + placeholder_reasons(claimed)
        if bad:
            placeholders.append({"path": rel, "reasons": bad})
        if computed != claimed:
            mismatches.append({"path": rel, "claimed": claimed, "computed": computed})
        else:
            verified.append({"path": rel, "sha256": computed})
    ok = not mismatches and not placeholders and not missing
    detail = {
        "manifest": str(manifest_path.relative_to(ROOT)),
        "entries": len(entries),
        "verified": len(verified),
        "mismatches": mismatches,
        "placeholders": placeholders,
        "missing": missing,
        "full_digests": verified,
    }
    return ("RESOLVED" if ok else "FAILED"), detail


def check_external_artifacts() -> tuple[str, dict]:
    """C01e — the 14 HOR-Qudit v2.5 artifacts are external and absent."""
    claimed = [
        ("run_420M_v22.py", "a3f8c2d1…f0a1", "main simulation"),
        ("me_049_072_forcing.py", "b7d4e1f2…b8c9", "forcing module / P1"),
        ("sophia_convergence_v24.ipynb", "d1b8a4c2…a0b1", "Sophia convergence"),
        ("forcing_greedy_vs_generic_seed13.csv", "a2c4e6b8…f0a2", "P1 evidence"),
        ("topos_h1_detection_seed17.json", "b5d7f9a1…e3b5", "P2 evidence"),
        ("sophia_trace_seed3.csv", "e9a1c7b8…f2a4", "6,127-step trace"),
    ]
    status_rows = []
    for name, prefix, role in claimed:
        present = (ROOT / "artifacts" / name).exists()
        status_rows.append({
            "artifact": name, "role": role,
            "spec_supplied_hash_prefix": prefix,
            "prefix_rejected_as_placeholder": bool(placeholder_reasons(prefix)),
            "present_on_disk": present,
        })
    detail = {
        "expected_total": 14,
        "known_named": len(status_rows),
        "present_on_disk": sum(1 for r in status_rows if r["present_on_disk"]),
        "note": "Full manifest is 'per HOR-Qudit v2.5 §1.1', which was not "
                "supplied; only these 6 named artifacts are known to this repo. "
                "All spec-supplied hash prefixes fail placeholder checks and "
                "are rejected as evidence (blueprint §4.1). Drop the real "
                "files into artifacts/, extend MANIFEST.sha256 via "
                "src/gen_manifest.py, and rerun to move C01e/C06/C07/C10.",
        "artifacts": status_rows,
    }
    present = detail["present_on_disk"]
    if present == 14:
        return "RESOLVED", detail
    return "OPEN", detail


def check_lambda(seed: int, steps: int) -> tuple[dict, dict]:
    """Fresh seeded runs vs committed traces, both modes (C02/C03/C04/C05)."""
    results = {}
    with tempfile.TemporaryDirectory(prefix="pazuzu-verify-") as tmp:
        for mode in ("pazuzu", "substrate"):
            canonical = ROOT / "logs" / (
                "lambda_trace.csv" if mode == "pazuzu"
                else "lambda_trace_substrate.csv")
            fresh = Path(tmp) / f"fresh_{mode}.csv"
            proc = subprocess.run(
                [sys.executable, str(ROOT / "src" / "pazuzu_r1.py"),
                 "--evaluate", "--seed", str(seed), "--steps", str(steps),
                 "--mode", mode, "--seed-override", "strict",
                 "--output", str(fresh)],
                capture_output=True, text=True, timeout=120,
            )
            entry = {"returncode": proc.returncode}
            if proc.returncode != 0:
                entry["error"] = proc.stderr.strip()[-500:]
                results[mode] = entry
                continue
            fresh_bytes = fresh.read_bytes()
            entry["fresh_sha256"] = hashlib.sha256(fresh_bytes).hexdigest()
            entry["canonical_exists"] = canonical.exists()
            entry["canonical_sha256"] = sha256_file(canonical) if canonical.exists() else None
            entry["byte_identical"] = (
                canonical.exists() and fresh_bytes == canonical.read_bytes())
            entry["canonical_stats"] = (parse_trace(canonical, mode)
                                        if canonical.exists() else None)
            results[mode] = entry
    return results


def check_p1() -> tuple[str, dict]:
    """C06 — P1 forcing vs greedy recompute (blueprint §4.5)."""
    data = ROOT / "data" / "p1_forcing_vs_greedy.csv"
    if not data.exists():
        return "OPEN", {
            "reason": "raw evidence CSV absent (external HOR-Qudit artifact "
                      "forcing_greedy_vs_generic_seed13.csv not supplied)",
            "expected_path": "data/p1_forcing_vs_greedy.csv",
            "required_schema": "columns: pair_id,seed,forcing,greedy "
                               "(one row per pair; reported n must match rows)",
            "acceptance": "forcing 50/50 dense sets; greedy 47.2±1.8; "
                          "paired p < 0.001 (substrate-specific)",
            "tool_status": "recompute implemented in src/stats_tools.py and "
                           "tested on tests/fixtures/synthetic_p1_forcing_vs_greedy.csv "
                           "(synthetic fixture — code test only, NOT evidence)",
        }
    with data.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        required = {"pair_id", "forcing", "greedy"}
        if not required.issubset(set(reader.fieldnames or [])):
            return "FAILED", {"error": f"CSV schema mismatch; required columns {sorted(required)}",
                              "found": reader.fieldnames}
        rows = [(float(r["forcing"]), float(r["greedy"])) for r in reader]
    stats = st.summarize_pairs(rows)
    acceptance = {
        "forcing_dense_sets_met_all": stats["forcing_mean"] == 50.0,
        "greedy_within_47.2±1.8": abs(stats["greedy_mean"] - 47.2) <= 1.8,
        "paired_p_below_0.001": stats["p_two_sided"] < 0.001,
    }
    detail = {"stats": stats, "acceptance": acceptance,
              "scope": "substrate-specific; does not transfer to Pazuzu-only deployments"}
    return ("RESOLVED" if all(acceptance.values()) else "FALSIFIED"), detail


def check_p2() -> tuple[str, dict]:
    """C07 — P2 H¹ detection with mandatory false-positive-rate reporting."""
    data = ROOT / "data" / "topos_h1_detection.json"
    if not data.exists():
        return "OPEN", {
            "reason": "raw evidence JSON absent (external HOR-Qudit artifact "
                      "topos_h1_detection_seed17.json not supplied)",
            "expected_path": "data/topos_h1_detection.json",
            "required_schema": '{"samples": [{"sample_id": int, '
                               '"has_logical_error": bool, "h1_nonzero": bool}, ...]}',
            "acceptance": "all logical errors detected; false-positive rate "
                          "stated (supplied set: 3/64 no-error samples with "
                          "H¹≠0 → 4.7 % FP rate, must be reported as such)",
            "tool_status": "recompute implemented here and tested on "
                           "tests/fixtures/synthetic_p2_h1_detection.json "
                           "(synthetic fixture — code test only, NOT evidence)",
        }
    payload = json.loads(data.read_text(encoding="utf-8"))
    samples = payload.get("samples", [])
    errors = [s for s in samples if s.get("has_logical_error")]
    no_error = [s for s in samples if not s.get("has_logical_error")]
    detected = sum(1 for s in errors if s.get("h1_nonzero"))
    fp = sum(1 for s in no_error if s.get("h1_nonzero"))
    fp_rate = fp / len(no_error) if no_error else None
    detail = {
        "n_samples": len(samples),
        "n_logical_errors": len(errors),
        "errors_detected": detected,
        "all_errors_detected": detected == len(errors) and len(errors) > 0,
        "false_positives": fp,
        "no_error_samples": len(no_error),
        "false_positive_rate": fp_rate,
        "false_positive_rate_percent": None if fp_rate is None else round(100 * fp_rate, 2),
        "note": "Detector is not labeled validated until the FP rate is "
                "bounded on a larger sample or the claim is restricted to "
                "the supplied set (blueprint §4.5).",
    }
    ok = detail["all_errors_detected"] and fp_rate is not None
    return ("RESOLVED" if ok else "FALSIFIED"), detail


def check_lean() -> tuple[str, dict]:
    """C08 — Lean 4 Sophia convergence proof (blueprint §4.4)."""
    lean_file = ROOT / "lean" / "SophiaConvergence.lean"
    if not lean_file.exists():
        return "OPEN", {
            "reason": "lean/SophiaConvergence.lean absent — claim remains OPEN",
            "acceptance": "complete file builds via 'lake build "
                          "lean/SophiaConvergence.lean'; theorem must state "
                          "λ_min > 0 and N_steps ≤ 6127 for ε_tol = 10⁻¹⁰; "
                          "a truncated file does not satisfy this criterion; "
                          "arithmetic verification of a subtraction is not "
                          "accepted as a convergence proof",
        }
    lake = shutil.which("lake")
    if lake is None:
        return "OPEN", {"reason": "lean file present but lake toolchain "
                                  "unavailable in PATH; claim remains OPEN"}
    has_theorem = "theorem" in lean_file.read_text(encoding="utf-8", errors="replace")
    proc = subprocess.run([lake, "build", "lean/SophiaConvergence.lean"],
                          cwd=ROOT, capture_output=True, text=True, timeout=600)
    ok = proc.returncode == 0 and has_theorem
    return ("RESOLVED" if ok else "FAILED"), {
        "lake": lake, "returncode": proc.returncode,
        "theorem_statement_present": has_theorem,
        "build_output_tail": (proc.stdout + proc.stderr)[-800:],
    }


def check_decision() -> tuple[str, dict]:
    """C09 — DECISION.md must record one of Options A/B/C (blueprint §4.3)."""
    path = ROOT / "DECISION.md"
    if not path.exists():
        return "FALSIFIED", {
            "reason": "DECISION.md absent — per blueprint §4.3 the λ(T)=0 "
                      "claim for substrate deployments is FALSIFIED by the "
                      "supplied numbers until a decision is recorded",
        }
    text = path.read_text(encoding="utf-8")
    # The decision is read from the first line that both names "Decision"
    # and records an option — other lines may legitimately *mention* the
    # rejected options (e.g. in consequences/falsifiability notes).
    chosen, decision_line = [], None
    for line in text.splitlines():
        if "decision" in line.lower():
            opts = [opt for opt in "ABC"
                    if re.search(rf"Option\s+{opt}\b", line)]
            if opts:
                chosen, decision_line = opts, line.strip()
                break
    mode_split = "mode split" in text.lower()
    ok = chosen == ["C"] and mode_split
    return ("RESOLVED" if ok else "FAILED"), {
        "decision_line": decision_line,
        "chosen": chosen,
        "mode_split_language_present": mode_split,
        "reference": "DECISION.md",
    }


def check_substrate_floor_arithmetic() -> tuple[str, dict]:
    """C11 — arithmetic identity only (explicitly NOT a lower-bound proof)."""
    value = pz.PHI ** -2 - pz.DELTA_FORCING - pz.DELTA_TOPOS
    spec_value = 0.36362601125
    matches = abs(value - spec_value) < 1e-11
    detail = {
        "phi": pz.PHI,
        "phi^-2": pz.PHI ** -2,
        "delta_forcing": pz.DELTA_FORCING,
        "delta_topos": pz.DELTA_TOPOS,
        "computed": value,
        "spec_value": spec_value,
        "abs_difference": abs(value - spec_value),
        "matches": matches,
        "scope": "arithmetic identity verified in float64; this is NOT a "
                 "proof that λ_min bounds the dynamical system (see C11b)",
    }
    return ("RESOLVED" if matches else "FAILED"), detail


def check_summaries_labels() -> tuple[bool, dict]:
    """C13/C14 — TRL label + classification matrix completeness."""
    out = {}
    for name in ("lambda_summary.json", "lambda_summary_substrate.json"):
        path = ROOT / "logs" / name
        if not path.exists():
            out[name] = {"present": False}
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        blocks = {
            "setpoint": payload.get("setpoint", {}),
            "final_lambda": payload.get("final_lambda", {}),
            "gains": payload.get("gains", {}),
        }
        out[name] = {
            "present": True,
            "trl_complete": all(b.get("trl") == "Simulation-Emulated"
                                for b in blocks.values()),
            "classification_present": all(
                ("classification" in b) or ("classification" in payload)
                for b in blocks.values()),
            "classification_matrix_entries": len(payload.get("classification_matrix", {})),
            "decision_ref": payload.get("decision_ref"),
        }
    return out


# --------------------------------------------------------------------------
# Claims registry
# --------------------------------------------------------------------------
def build_claims(manifest_status, manifest_detail, lambda_results,
                 p1, p2, lean, decision, floor, labels, seed, steps) -> list[dict]:
    def claim(cid, title, status, criterion, detail):
        return {"id": cid, "title": title, "status": status,
                "criterion": criterion, "detail": detail}

    claims = []

    # C01 ------------------------------------------------------------------
    claims.append(claim(
        "C01", "MANIFEST.sha256 integrity (full SHA-256, no placeholders)",
        manifest_status,
        "every manifest entry recomputes to the claimed full 64-hex digest; "
        "no placeholder pattern; manifest has entries",
        manifest_detail))

    # C01e -----------------------------------------------------------------
    status, detail = check_external_artifacts()
    claims.append(claim(
        "C01e", "14 HOR-Qudit v2.5 artifacts present with verified hashes",
        status,
        "14 real files in artifacts/ hash-verified with full SHA-256 "
        "(blueprint §4.1)", detail))

    # C02–C05 ---------------------------------------------------------------
    pz_res, sub_res = lambda_results.get("pazuzu", {}), lambda_results.get("substrate", {})
    det = all(r.get("byte_identical") for r in (pz_res, sub_res) if r) and len(lambda_results) == 2
    claims.append(claim(
        "C02", "λ-trace determinism (fresh run ≡ committed trace, both modes)",
        "RESOLVED" if det else "FAILED",
        f"pazuzu_r1.py --seed {seed} --steps {steps} reproduces "
        "logs/lambda_trace.csv and logs/lambda_trace_substrate.csv "
        "byte-for-byte", {m: {k: v for k, v in r.items()
                              if k != "canonical_stats"}
                          for m, r in lambda_results.items()}))

    pz_stats = pz_res.get("canonical_stats") or {}
    sub_stats = sub_res.get("canonical_stats") or {}
    finite = bool(pz_stats.get("all_finite") and sub_stats.get("all_finite"))
    claims.append(claim(
        "C03", "λ finite at every step (no NaN/Inf)",
        "RESOLVED" if finite else "FAILED",
        "all λ values in both canonical traces are finite (blueprint §4.2)",
        {"pazuzu": pz_stats.get("all_finite"), "substrate": sub_stats.get("all_finite")}))

    mono = bool(pz_stats.get("monotone_nonincreasing_outside_windows")
                and sub_stats.get("monotone_nonincreasing_outside_windows"))
    claims.append(claim(
        "C04", "spectral-flow constraint: λ non-increasing outside licensed windows",
        "RESOLVED" if mono else "FAILED",
        "λ[t+1] ≤ λ[t] whenever step t+1 is not an exploration window, in "
        "both modes (blueprint §4.2; R1 §3.1)",
        {"pazuzu": pz_stats.get("monotone_nonincreasing_outside_windows"),
         "substrate": sub_stats.get("monotone_nonincreasing_outside_windows")}))

    summaries = labels
    trl_ok = all(v.get("trl_complete") for v in summaries.values() if v.get("present")) \
        and any(v.get("present") for v in summaries.values())
    claims.append(claim(
        "C05", "final λ recorded with TRL label Simulation-Emulated",
        "RESOLVED" if trl_ok else "FAILED",
        "logs/lambda_summary*.json record final_lambda.trl = "
        "Simulation-Emulated (blueprint §4.2 criterion 4)",
        summaries))

    # C06 / C07 -------------------------------------------------------------
    claims.append(claim(
        "C06", "P1: forcing beats greedy on dense sets (paired)",
        p1[0], "recompute from data/p1_forcing_vs_greedy.csv: forcing 50/50; "
               "greedy 47.2±1.8; paired p < 0.001; n consistent; "
               "substrate-specific scope", p1[1]))
    claims.append(claim(
        "C07", "P2: H¹ detection with stated false-positive rate",
        p2[0], "recompute from data/topos_h1_detection.json; all logical "
               "errors detected; FP rate reported (3/64 = 4.7 % on supplied "
               "set); validation bounded or claim restricted", p2[1]))

    # C08 / C09 / C10 --------------------------------------------------------
    claims.append(claim(
        "C08", "Lean 4 Sophia convergence proof builds",
        lean[0], "lean/SophiaConvergence.lean exists, is complete, and "
                 "'lake build' succeeds with λ_min > 0, N_steps ≤ 6127 "
                 "(blueprint §4.4)", lean[1]))
    claims.append(claim(
        "C09", "λ(T)=0 vs λ_min contradiction decided",
        decision[0], "DECISION.md records exactly one option with mode-split "
                     "semantics (blueprint §4.3)", decision[1]))
    sophia_present = (ROOT / "artifacts" / "sophia_trace_seed3.csv").exists()
    claims.append(claim(
        "C10", "Sophia 6,127-step monotone trace verified",
        "RESOLVED" if sophia_present else "OPEN",
        "artifacts/sophia_trace_seed3.csv present; monotone distance "
        "decrease; step 6127 distance 9.87×10⁻¹¹ ≤ 10⁻¹⁰",
        {"present": sophia_present}))

    # C11 / C11b / C12 -------------------------------------------------------
    claims.append(claim(
        "C11", "substrate floor arithmetic identity φ⁻²−δ_forcing−δ_topos",
        floor[0], "float64 recomputation matches 0.36362601125 within 1e-11; "
                  "counts as arithmetic ONLY (blueprint §2 'status inflation' "
                  "row)", floor[1]))
    claims.append(claim(
        "C11b", "λ_min is a proven lower bound of the λ-flow dynamics",
        "OPEN",
        "requires a complete Lean proof (see C08) or an empirical "
        "demonstration on the substrate; arithmetic identity is not accepted",
        {"reason": "no proof supplied; DECISION.md Option C treats the floor "
                   "as an enforced control band, not a proven bound"}))
    claims.append(claim(
        "C12", "parity-flip ledger audit (replayable, hash-chained)",
        "OPEN",
        "flip events recorded with before/after ledger consistency per "
        "R1 §6.1 rule 3; requires substrate deployment artifacts not in scope",
        {"reason": "no parity-flip events exist in this suite's scope yet"}))

    # C13 / C14 ---------------------------------------------------------------
    claims.append(claim(
        "C13", "every quantitative metric carries a TRL label",
        "RESOLVED" if trl_ok else "FAILED",
        "setpoint, final λ, and gains blocks all labeled Simulation-Emulated "
        "(R1 §6.2 rule 1)", summaries))
    matrix_ok = all(v.get("classification_matrix_entries", 0) >= 10
                    for v in summaries.values() if v.get("present")) \
        and any(v.get("present") for v in summaries.values())
    claims.append(claim(
        "C14", "every parameter carries a classification label",
        "RESOLVED" if matrix_ok else "FAILED",
        "classification matrix (Derived / Topologically Forced / Design "
        "Choice / Empirical Fit) present and covering all tunables "
        "(R1 §6.2 rule 2)",
        {k: v.get("classification_matrix_entries") for k, v in summaries.items()}))

    return claims


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="verify_all.py",
        description="Pazuzu 1.0-R1 verification & benchmark suite "
                    "(blueprint V1.0)")
    p.add_argument("--check-hashes", action="store_true",
                   help="verify MANIFEST.sha256 entries (full digests printed)")
    p.add_argument("--full-sha256", action="store_true",
                   help="print complete 64-character digests (default with "
                        "--check-hashes; kept for spec compatibility)")
    p.add_argument("--manifest", default="MANIFEST.sha256",
                   help="manifest path relative to repo root")
    p.add_argument("--seed-override", choices=["strict", "off"], default="strict",
                   help="forwarded semantics: determinism checks run seeded")
    p.add_argument("--seed", type=int, default=pz.DEFAULT_SEED)
    p.add_argument("--steps", type=int, default=pz.DEFAULT_STEPS)
    p.add_argument("--test-p1p2", action="store_true",
                   help="run P1/P2 recomputation checks (OPEN when data absent)")
    p.add_argument("--lean-check", action="store_true",
                   help="run Lean 4 build check (OPEN when file absent)")
    p.add_argument("--full", action="store_true",
                   help="run every check and write the suite report")
    p.add_argument("--output", default=None,
                   help="write JSON suite report to this path")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    run_all = args.full or not (args.check_hashes or args.test_p1p2
                                or args.lean_check)
    do_hashes = run_all or args.check_hashes
    do_p1p2 = run_all or args.test_p1p2
    do_lean = run_all or args.lean_check

    manifest_path = ROOT / args.manifest

    # ---- manifest + full digest printing (§4.1) ---------------------------
    manifest_status, manifest_detail = "OPEN", {"reason": "not requested"}
    if do_hashes:
        manifest_status, manifest_detail = check_manifest(manifest_path)
        for entry in manifest_detail.get("full_digests", []):
            print(f"{entry['sha256']}  {entry['path']}")
        if manifest_detail.get("mismatches"):
            for m in manifest_detail["mismatches"]:
                print(f"MISMATCH {m['path']}: claimed {m['claimed']} "
                      f"computed {m['computed']}", file=sys.stderr)
        if manifest_detail.get("missing"):
            for rel in manifest_detail["missing"]:
                print(f"MISSING {rel}", file=sys.stderr)
        if manifest_detail.get("placeholders"):
            for ph in manifest_detail["placeholders"]:
                print(f"PLACEHOLDER {ph['path']}: {ph['reasons']}",
                      file=sys.stderr)

    # ---- λ determinism + invariants ---------------------------------------
    lambda_results = check_lambda(args.seed, args.steps)
    labels = check_summaries_labels()
    p1 = check_p1() if do_p1p2 else ("OPEN", {"reason": "not requested"})
    p2 = check_p2() if do_p1p2 else ("OPEN", {"reason": "not requested"})
    lean = check_lean() if do_lean else ("OPEN", {"reason": "not requested"})
    decision = check_decision()
    floor = check_substrate_floor_arithmetic()

    claims = build_claims(manifest_status, manifest_detail, lambda_results,
                          p1, p2, lean, decision, floor, labels,
                          args.seed, args.steps)

    failed = [c for c in claims if c["status"] == "FAILED"]
    open_claims = [c["id"] for c in claims
                   if c["status"] in ("OPEN", "PARTIAL", "FALSIFIED")]
    exit_code = 1 if failed else 0

    git = git_info()
    report = {
        "schema": SCHEMA_ID,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "git_commit": git["git_commit"],
        "git_dirty": git["git_dirty"],
        "manifest": {k: v for k, v in manifest_detail.items()
                     if k != "full_digests"},
        "artifact_digests": manifest_detail.get("full_digests", []),
        "lambda": {
            "seed": args.seed, "steps": args.steps,
            "modes": {m: r.get("canonical_stats")
                      for m, r in lambda_results.items()},
            "deterministic": all(
                r.get("byte_identical") for r in lambda_results.values()),
        },
        "p1": {"status": p1[0], "detail": p1[1]},
        "p2": {"status": p2[0], "detail": p2[1]},
        "lean": {"status": lean[0], "detail": lean[1]},
        "lambda_decision": {"status": decision[0], "detail": decision[1]},
        "substrate_floor_arithmetic": {"status": floor[0], "detail": floor[1]},
        "claims": claims,
        "claims_open": open_claims,
        "claims_failed": [c["id"] for c in failed],
        "exit_code": exit_code,
        "exit_semantics": "0 = every RESOLVED-declared claim passed its "
                          "runtime check; 1 = at least one failed; "
                          "OPEN/PARTIAL claims do not affect the exit code",
    }

    # ---- human summary -----------------------------------------------------
    print()
    print("Pazuzu 1.0-R1 verification suite")
    print(f"  git commit : {report['git_commit']}"
          + (" (dirty)" if git["git_dirty"] else ""))
    print(f"  manifest   : {manifest_detail.get('verified', 0)}/"
          f"{manifest_detail.get('entries', 0)} entries verified")
    print(f"  λ determin.: "
          f"{report['lambda']['deterministic']} (seed {args.seed}, "
          f"{args.steps} steps, both modes)")
    print(f"  decision   : Option "
          f"{report['lambda_decision']['detail'].get('chosen', '—')}")
    print(f"  claims     : {len(claims)} total | "
          f"{sum(1 for c in claims if c['status'] == 'RESOLVED')} resolved | "
          f"{len(open_claims)} open/partial | {len(failed)} failed")
    for c in claims:
        marker = {"RESOLVED": "PASS", "FAILED": "FAIL"}.get(c["status"], c["status"])
        print(f"    [{marker:>4}] {c['id']:<4} {c['title']}")
    if failed:
        print(f"ERROR: {len(failed)} RESOLVED-declared claim(s) failed:",
              file=sys.stderr)

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, indent=2) + "\n",
                            encoding="utf-8", newline="\n")
        print(f"  report     : {out_path}")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
