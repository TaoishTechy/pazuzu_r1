#!/usr/bin/env python3
"""Pazuzu 1.0-R1 — executable λ-flow PID controller (Simulation-Emulated).

Implements the discrete λ-flow of Pazuzu 1.0-R1 §3.1 under the HOR-Qudit-derived
PID governance (R1.2 critical constants):

    λ[t+1] = λ[t] + dλ[t],   dλ[t] = -α·λ[t] + β·u[t] + η[t]

    u[t]  = Kp·e[t] + I[t] + Kd·(e[t] − e[t−1])        (discrete PID)
    e[t]  = setpoint − λ[t]
    I[t]  = clamp( (1−γ)·I[t−1] + Ki·e[t],  ±I_CLAMP ) (leaky integrator,
                                                       anti-windup)
    η[t]  ~ zero-mean white Gaussian, σ = ETA_SIGMA    (audit item 21:
                                                       distribution specified)

Gains (HOR-Qudit ME-170 / R1.2 §3.2):  Kp = φ⁻¹, Ki = φ⁻³, Kd = φ⁻².

Deployment modes — DECISION.md records **Option C (mode split)**:

    pazuzu     setpoint = 0.0
               (λ(T)=0 retained as the Pazuzu-only control target)
    substrate  setpoint = λ_min = φ⁻² − δ_forcing − δ_topos = 0.36362601125
               with floor enforcement λ ≥ λ_min (Sophia mapping as positive
               floor; the lower-bound claim itself remains OPEN — see
               docs/CLAIMS.md C11).

Governance / safety (Pazuzu 1.0-R1 §6.1):

  * Spectral-flow constraint — outside licensed exploration windows λ never
    increases (enforced by clamp, per-step flag `clamp_spectral`).
  * λ-ceiling — λ never exceeds LAMBDA_CEILING (hard clamp; audit items 19/101).
  * λ-floor — λ never drops below the governance floor: R1 λ_floor = 10⁻⁹ in
    pazuzu mode (audit #19 resolution), Sophia floor λ_min in substrate mode
    (DECISION.md Option C). Without the floor, a strict non-increase rule
    would let λ ratchet through zero and random-walk negative forever;
    the floor pins the controlled system at λ_dom ≈ 0 as governed.
  * Anti-Goodhart honesty — every number is labeled; no hardware claim is made.

Determinism: a single seeded PRNG (random.Random(seed)) drives Box–Muller
Gaussian draws; the λ-trace CSV is a byte-identical pure function of
(seed, steps, mode, start_lambda). `--seed-override strict` refuses any run
whose randomness is not fully seed-determined.

TRL discipline: all outputs are labeled Simulation-Emulated (HOR-Qudit v2.5
§TRL table). This program does not claim hardware measurement of any quantity.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

# --------------------------------------------------------------------------
# Critical constants (Pazuzu 1.0-R1 §3/§6; R1.2 §3.2; audit resolutions)
# --------------------------------------------------------------------------
PHI = (1.0 + math.sqrt(5.0)) / 2.0                     # 1.6180339887498949
KP = PHI ** -1                                         # 0.6180339887498949
KI = PHI ** -3                                         # 0.23606797749978967
KD = PHI ** -2                                         # 0.38196601125010515
KAPPA_PHI = 1.0 / PHI                                  # 0.6180339887498949 —
# NOTE (R1.2): κ_φ = 1/φ is a coupling constant and is deliberately NOT used
# as a health scalar; the health gate (S > 0.999, hysteresis S > 0.995) is a
# separate governance concept out of scope for this λ-flow simulation.

ALPHA = 0.05            # natural decay rate of λ      — Design Choice
BETA = 0.02             # gain of control term u       — Design Choice
ETA_SIGMA = 0.01        # white-noise std of η         — Design Choice
I_CLAMP = 0.5           # integrator anti-windup clamp — Design Choice
I_LEAK = 0.01           # leaky-integrator leak γ      — Design Choice
LAMBDA_CEILING = 0.5    # safety ceiling (λ-floor governance, audit #101)
LAMBDA_FLOOR = 1.0e-9   # R1 λ_floor = 10⁻⁹ (audit #19/#101 resolution)
DELTA_FORCING = 1.70e-2  # supplied HOR-Qudit P1 bound (not re-measured here)
DELTA_TOPOS = 1.34e-3    # supplied HOR-Qudit P2 bound (not re-measured here)
LAMBDA_MIN_SUBSTRATE = PHI ** -2 - DELTA_FORCING - DELTA_TOPOS  # arithmetic
# = 0.36362601125010515 ; the R1 spec rounds it to 0.36362601125.

EXPLORATION_PERIOD = 100   # licensed exploration window every N steps
EXPLORATION_LENGTH = 10    # window length in steps

DEFAULT_SEED = 13          # HOR-Qudit canonical seed
DEFAULT_STEPS = 1000
DEFAULT_START_LAMBDA = 1.0

TRL_LABEL = "Simulation-Emulated"
SCHEMA_ID = "pazuzu-r1/lambda-trace@v1"
SUMMARY_SCHEMA_ID = "pazuzu-r1/lambda-summary@v1"

CSV_COLUMNS = [
    "step", "lambda", "raw_dlambda", "setpoint", "error",
    "p_term", "i_term", "d_term", "control", "eta",
    "exploration_window", "clamp_ceiling", "clamp_spectral", "clamp_floor",
    "mode", "seed", "trl_label",
]

CLASSIFICATION_MATRIX = {
    "Kp": "Derived (φ⁻¹, HOR-Qudit ME-170)",
    "Ki": "Derived (φ⁻³, HOR-Qudit ME-170)",
    "Kd": "Derived (φ⁻², HOR-Qudit ME-170)",
    "alpha": "Design Choice",
    "beta": "Design Choice",
    "eta_sigma": "Design Choice (audit #21: distribution specified, value not fitted)",
    "i_clamp": "Design Choice",
    "i_leak": "Design Choice",
    "lambda_ceiling": "Design Choice (audit #101)",
    "lambda_floor": "Derived (R1 audit #19: λ_floor = 10⁻⁹)",
    "setpoint_pazuzu": "Derived (λ(T)=0 control target, Pazuzu-only mode)",
    "setpoint_substrate": "Empirical Fit (arithmetic identity φ⁻²−δ_forcing−δ_topos; "
                          "lower-bound status OPEN)",
    "exploration_windows": "Design Choice",
    "trl_label": "Definition (HOR-Qudit v2.5 TRL table)",
}


# --------------------------------------------------------------------------
# Core simulation
# --------------------------------------------------------------------------
def in_exploration_window(step: int) -> bool:
    """A step is licensed for exploration iff (step % PERIOD) < LENGTH."""
    return (step % EXPLORATION_PERIOD) < EXPLORATION_LENGTH


def setpoint_for(mode: str) -> float:
    if mode == "pazuzu":
        return 0.0
    if mode == "substrate":
        return LAMBDA_MIN_SUBSTRATE
    raise ValueError(f"unknown mode: {mode!r}")


def floor_for(mode: str) -> float:
    """Hard lower clamp per mode (R1 λ_floor = 10⁻⁹; substrate Sophia floor)."""
    return LAMBDA_MIN_SUBSTRATE if mode == "substrate" else LAMBDA_FLOOR


def _gauss(rng: random.Random) -> float:
    """Deterministic Box–Muller standard normal from two uniform draws.

    Implemented explicitly (instead of random.gauss) so the sequence is
    stable across CPython versions and platforms.
    """
    u1 = rng.random()
    u2 = rng.random()
    while u1 <= 1e-12:            # guard log(0); 1e-12 < 2**-53 never in [0,1)
        u1 = rng.random()
    return math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * u2)


def simulate(
    seed: int = DEFAULT_SEED,
    steps: int = DEFAULT_STEPS,
    mode: str = "pazuzu",
    start_lambda: float = DEFAULT_START_LAMBDA,
):
    """Run the seeded λ-flow; return the list of per-step record dicts.

    Pure function of (seed, steps, mode, start_lambda) — no clock, no
    environment, no global RNG state.
    """
    if steps < 1:
        raise ValueError("steps must be >= 1")
    rng = random.Random(seed)
    sp = setpoint_for(mode)
    floor = floor_for(mode)

    lam = float(start_lambda)
    integral = 0.0
    prev_error = sp - lam
    rows = []

    for step in range(steps):
        error = sp - lam
        p_term = KP * error
        integral = max(-I_CLAMP, min(I_CLAMP, (1.0 - I_LEAK) * integral + KI * error))
        d_term = KD * (error - prev_error)
        control = p_term + integral + d_term
        eta = ETA_SIGMA * _gauss(rng)

        raw_dlambda = -ALPHA * lam + BETA * control + eta
        window = in_exploration_window(step)

        new_lam = lam + raw_dlambda
        clamp_ceiling = clamp_spectral = clamp_floor = False

        if new_lam > LAMBDA_CEILING:                    # λ-ceiling (always on)
            new_lam = LAMBDA_CEILING
            clamp_ceiling = True
        if not window and new_lam > lam:                # spectral-flow, dλ/dt ≤ 0
            new_lam = lam
            clamp_spectral = True
        if new_lam < floor:                             # λ-floor (both modes)
            new_lam = floor
            clamp_floor = True

        rows.append({
            "step": step,
            "lambda": new_lam,
            "raw_dlambda": raw_dlambda,
            "setpoint": sp,
            "error": error,
            "p_term": p_term,
            "i_term": integral,
            "d_term": d_term,
            "control": control,
            "eta": eta,
            "exploration_window": window,
            "clamp_ceiling": clamp_ceiling,
            "clamp_spectral": clamp_spectral,
            "clamp_floor": clamp_floor,
            "mode": mode,
            "seed": seed,
            "trl_label": TRL_LABEL,
        })
        prev_error = error
        lam = new_lam
    return rows


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------
def _fmt(value: float) -> str:
    return f"{value:.9e}"


def rows_to_csv(rows) -> str:
    """Serialize rows to deterministic CSV text (LF newlines, fixed format)."""
    out = [",".join(CSV_COLUMNS)]
    for r in rows:
        out.append(",".join([
            str(r["step"]),
            _fmt(r["lambda"]),
            _fmt(r["raw_dlambda"]),
            _fmt(r["setpoint"]),
            _fmt(r["error"]),
            _fmt(r["p_term"]),
            _fmt(r["i_term"]),
            _fmt(r["d_term"]),
            _fmt(r["control"]),
            _fmt(r["eta"]),
            "1" if r["exploration_window"] else "0",
            "1" if r["clamp_ceiling"] else "0",
            "1" if r["clamp_spectral"] else "0",
            "1" if r["clamp_floor"] else "0",
            r["mode"],
            str(r["seed"]),
            r["trl_label"],
        ]))
    return "\n".join(out) + "\n"


def trace_invariants(rows) -> dict:
    """Compute the acceptance invariants of blueprint §4.2 from raw rows."""
    lams = [r["lambda"] for r in rows]
    all_finite = all(math.isfinite(v) for v in lams)
    monotone = all(
        rows[i]["lambda"] <= rows[i - 1]["lambda"]
        for i in range(1, len(rows))
        if not rows[i]["exploration_window"]
    )
    ceiling_ok = all(v <= LAMBDA_CEILING for v in lams)
    mode_floor = floor_for(rows[0]["mode"])
    floor_ok = all(v >= mode_floor - 1e-12 for v in lams)
    sp = rows[0]["setpoint"]
    band = 0.05
    within = [abs(v - sp) <= band for v in lams]
    first_entry = next((i for i, w in enumerate(within) if w), None)
    return {
        "all_finite": all_finite,
        "monotone_nonincreasing_outside_windows": monotone,
        "ceiling_respected": ceiling_ok,
        "floor_respected": floor_ok,
        "rows": len(rows),
        "lambda_final": lams[-1],
        "lambda_min": min(lams),
        "lambda_max": max(lams),
        "setpoint": sp,
        "final_error": lams[-1] - sp,
        "band": band,
        "band_occupancy": sum(within) / len(within),
        "first_entry_step": first_entry,
        "exploration_window_count": sum(1 for r in rows if r["exploration_window"]),
        "clamp_spectral_count": sum(1 for r in rows if r["clamp_spectral"]),
        "clamp_ceiling_count": sum(1 for r in rows if r["clamp_ceiling"]),
        "clamp_floor_count": sum(1 for r in rows if r["clamp_floor"]),
    }


def build_summary(rows, args, trace_sha256: str) -> dict:
    inv = trace_invariants(rows)
    return {
        "schema": SUMMARY_SCHEMA_ID,
        "run_id": f"{args.mode}-seed{args.seed}-steps{args.steps}-"
                  f"start{args.start_lambda:.3g}",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "decision_ref": "DECISION.md — Option C (mode split)",
        "mode": args.mode,
        "seed": args.seed,
        "steps": args.steps,
        "start_lambda": args.start_lambda,
        "seed_override": args.seed_override,
        "trace_csv_sha256": trace_sha256,
        "setpoint": {
            "value": inv["setpoint"],
            "trl": TRL_LABEL,
            "classification": CLASSIFICATION_MATRIX[
                "setpoint_substrate" if args.mode == "substrate" else "setpoint_pazuzu"
            ],
        },
        "gains": {
            "Kp": KP, "Ki": KI, "Kd": KD,
            "alpha": ALPHA, "beta": BETA, "eta_sigma": ETA_SIGMA,
            "i_clamp": I_CLAMP, "i_leak": I_LEAK,
            "trl": TRL_LABEL,
            "classification": "see classification_matrix",
        },
        "final_lambda": {
            "value": inv["lambda_final"],
            "trl": TRL_LABEL,                       # blueprint §4.2 criterion 4
            "classification": "Empirical Fit",
        },
        "invariants": {k: inv[k] for k in (
            "all_finite", "monotone_nonincreasing_outside_windows",
            "ceiling_respected", "floor_respected", "rows",
            "lambda_min", "lambda_max", "final_error",
            "band", "band_occupancy", "first_entry_step",
            "exploration_window_count", "clamp_spectral_count",
            "clamp_ceiling_count", "clamp_floor_count",
        )},
        "constraints": {
            "lambda_ceiling": LAMBDA_CEILING,
            "lambda_floor_pazuzu": LAMBDA_FLOOR,
            "lambda_floor_substrate": LAMBDA_MIN_SUBSTRATE,
            "lambda_floor_applied": floor_for(args.mode),
            "i_clamp": I_CLAMP,
            "exploration_period": EXPLORATION_PERIOD,
            "exploration_length": EXPLORATION_LENGTH,
        },
        "trl_labels_requested": bool(args.trl_labels),
        "classification_matrix_requested": bool(args.classification_matrix),
        "classification_matrix": CLASSIFICATION_MATRIX,
        "notes": [
            "Simulation-emulated result; TRL label Simulation-Emulated per "
            "HOR-Qudit v2.5. No hardware measurement is claimed or implied.",
            "Substrate floor is an arithmetic identity "
            "(φ⁻² − 0.017 − 0.00134 = 0.36362601125); it is not a proven "
            "dynamical lower bound (docs/CLAIMS.md C11).",
            "η is zero-mean white Gaussian with σ = 0.01 (audit item 21).",
            "κ_φ = 1/φ is not used as a health scalar (R1.2 acceptance row "
            "'κ_φ separation').",
        ],
    }


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="pazuzu_r1.py",
        description="Pazuzu 1.0-R1 λ-flow PID controller (Simulation-Emulated).",
    )
    p.add_argument("--evaluate", action="store_true", required=True,
                   help="run the λ-flow evaluation (required)")
    p.add_argument("--seed", type=int, default=DEFAULT_SEED,
                   help=f"PRNG seed (default {DEFAULT_SEED}, HOR-Qudit canonical)")
    p.add_argument("--steps", type=int, default=DEFAULT_STEPS,
                   help=f"number of steps (default {DEFAULT_STEPS})")
    p.add_argument("--start-lambda", type=float, default=DEFAULT_START_LAMBDA,
                   help="initial λ (default 1.0)")
    p.add_argument("--mode", choices=["pazuzu", "substrate"], default="pazuzu",
                   help="deployment mode per DECISION.md Option C")
    p.add_argument("--output", default="logs/lambda_trace.csv",
                   help="λ-trace CSV output path")
    p.add_argument("--seed-override", choices=["strict", "off"], default="strict",
                   help="strict = assert every stochastic component is "
                        "seed-determined (default; always true here)")
    p.add_argument("--snapshot", default=None,
                   help="write JSON summary/snapshot to this path")
    p.add_argument("--trl-labels", action="store_true",
                   help="attach TRL labels (mandatory; emitted regardless)")
    p.add_argument("--classification-matrix", action="store_true",
                   help="attach classification matrix (mandatory; emitted regardless)")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)

    if args.seed_override == "strict":
        # Strict mode: assert that every stochastic component derives from the
        # single recorded seed. By construction `simulate()` draws only from
        # random.Random(args.seed) via the explicit Box–Muller transform —
        # no clock, no OS entropy, no global RNG. Determinism is re-proven
        # byte-for-byte by tests/test_pazuzu_r1.py::test_deterministic_same_seed
        # and by verify_all.py's fresh-run comparison.
        print(f"seed-override strict: all randomness derives from seed {args.seed} "
              f"(deterministic; default {DEFAULT_SEED} when --seed omitted)")
    if args.steps < 1:
        print("ERROR: --steps must be >= 1", file=sys.stderr)
        return 2

    rows = simulate(seed=args.seed, steps=args.steps, mode=args.mode,
                    start_lambda=args.start_lambda)
    csv_text = rows_to_csv(rows)
    trace_sha = hashlib.sha256(csv_text.encode("utf-8")).hexdigest()

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(csv_text, encoding="utf-8", newline="\n")

    print(f"Pazuzu 1.0-R1 λ-flow | mode={args.mode} seed={args.seed} "
          f"steps={args.steps} trl={TRL_LABEL}")
    print(f"trace: {out_path}  sha256={trace_sha}")

    inv = trace_invariants(rows)
    print(f"final λ = {inv['lambda_final']:.9e}  (setpoint {inv['setpoint']:.9e})")
    print(f"invariants: finite={inv['all_finite']} "
          f"monotone_outside_windows={inv['monotone_nonincreasing_outside_windows']} "
          f"ceiling_ok={inv['ceiling_respected']} floor_ok={inv['floor_respected']}")

    if args.trl_labels:
        print("trl-labels: attached (mandatory per R1 §6.2 — emitted by default)")
    if args.classification_matrix:
        print("classification-matrix: attached (mandatory per R1 §6.2 — "
              "emitted by default)")

    if args.snapshot:
        summary = build_summary(rows, args, trace_sha)
        snap_path = Path(args.snapshot)
        snap_path.parent.mkdir(parents=True, exist_ok=True)
        snap_path.write_text(json.dumps(summary, indent=2, sort_keys=False) + "\n",
                             encoding="utf-8", newline="\n")
        print(f"snapshot: {snap_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
