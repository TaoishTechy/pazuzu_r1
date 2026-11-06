# Claims Registry — Pazuzu 1.0-R1 Validation & Benchmark Suite

Human-readable mirror of the machine registry in `src/verify_all.py`
(`build_claims`). The authoritative live status is `logs/suite_report.json`
(`claims` array); this file records the state at repo bootstrap
(2026-11-06) and the resolution path for every OPEN claim.

> Blueprint §1 invariant: a claim is RESOLVED only when a named command,
> executed against named files, produces a logged result satisfying a
> pre-declared acceptance criterion.

## RESOLVED at bootstrap (verified by code in this repository)

| ID | Claim | Acceptance criterion | Evidence |
|---|---|---|---|
| **C01** | `MANIFEST.sha256` integrity | every entry recomputes to the claimed full 64-hex digest; no placeholder pattern (arithmetic progression, repeated nibbles, length ≠ 64); no missing file | `verify_all.py --check-hashes --full-sha256`; full digests printed to `logs/verify_run.log` |
| **C02** | λ-trace determinism | fresh `pazuzu_r1.py --seed 13 --steps 1000` run reproduces `logs/lambda_trace.csv` and `logs/lambda_trace_substrate.csv` **byte-for-byte** (both modes) | suite run; also `tests/test_pazuzu_r1.py` |
| **C03** | λ finite at every step | no NaN/Inf in either canonical trace | parsed at every suite run |
| **C04** | spectral-flow constraint | λ[t+1] ≤ λ[t] whenever step t+1 is outside a licensed exploration window, both modes (blueprint §4.2; R1 §3.1) | parsed at every suite run |
| **C05** | final λ carries TRL label | `final_lambda.trl == "Simulation-Emulated"` in `logs/lambda_summary*.json` | suite run |
| **C09** | λ(T)=0 vs λ_min contradiction decided | `DECISION.md` records exactly one blueprint option with mode-split semantics | `DECISION.md` → **Option C** |
| **C11** | substrate floor arithmetic identity | float64 recomputation of φ⁻² − 0.017 − 0.00134 matches 0.36362601125 within 1e-11 — **arithmetic only**, by design not a lower-bound proof | `verify_all.py` (always executed) |
| **C13** | TRL labels complete | setpoint / final-λ / gains blocks all labeled Simulation-Emulated (R1 §6.2 rule 1) | suite run |
| **C14** | classification matrix complete | ≥ 10 parameters labeled Derived / Forced / Design Choice / Empirical Fit (R1 §6.2 rule 2) | `logs/lambda_summary.json` → `classification_matrix` |

## OPEN at bootstrap (external evidence or proofs required)

| ID | Claim | Why OPEN | How to resolve |
|---|---|---|---|
| **C01e** | 14 HOR-Qudit v2.5 artifacts hash-verified | artifacts absent; spec-supplied hash prefixes are placeholders and rejected (blueprint §4.1) | supply real files to `artifacts/`, regenerate manifest, re-run suite (see `artifacts/README.md`) |
| **C06** | P1: forcing 50/50 vs greedy 47.2±1.8, paired p<0.001 | raw CSV `data/p1_forcing_vs_greedy.csv` absent | supply raw evidence; recompute is implemented + tested on synthetic fixture (`data/README.md`) |
| **C07** | P2: H¹ detection with stated FP rate (3/64 ≈ 4.7 %) | raw JSON `data/topos_h1_detection.json` absent | supply raw evidence; FP-rate reporting implemented |
| **C08** | Lean 4 Sophia proof (`N_steps ≤ 6127`, λ_min > 0) | `lean/SophiaConvergence.lean` absent; arithmetic identity explicitly not accepted (blueprint §4.4) | commit complete file + lakefile; `lake build` must succeed |
| **C10** | Sophia 6,127-step monotone trace (final distance 9.87×10⁻¹¹) | `artifacts/sophia_trace_seed3.csv` absent | supply artifact; verifier checks monotonicity + endpoint |
| **C11b** | λ_min is a *proven dynamical lower bound* | no proof supplied; DECISION.md Option C treats the floor as an enforced control band | blocked on C08 (Lean) or an empirical demonstration |
| **C12** | parity-flip ledger audit (replayable, hash-chained) | no parity-flip events exist in this suite's scope | requires substrate deployment artifacts; protocol per R1 §6.1 rule 3 |

## Statuses used

- **RESOLVED** — runtime check passed for a pre-declared criterion.
- **FAILED** — a RESOLVED-declared claim failed its criterion (suite exits 1).
- **OPEN / PARTIAL** — evidence absent or incomplete (does not affect exit code).
- **FALSIFIED** — a supplied number contradicts the claim (e.g. DECISION.md
  missing ⇒ substrate λ(T)=0 is FALSIFIED per blueprint §4.3).

## Exit-code semantics (blueprint §6)

`python src/verify_all.py --full` exits **0** iff every claim declared
RESOLVED passed its runtime check; **1** if any failed; **2** on usage
errors. OPEN/PARTIAL claims are listed in the report under
`claims_open` and never mask a failure.
