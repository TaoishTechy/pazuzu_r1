# Pazuzu 1.0-R1 — Validation & Benchmark Suite Blueprint

> Markdown transcription of `Pazuzu_R1_Validation_Benchmark_Suite_Blueprint.docx`
> (supplied 2026-11-06). Verbatim except heading/table formatting.

PAZUZU 1.0-R1
Validation and Benchmark Suite Blueprint
Executable Verification Protocol — Revision V1.0
Compiled: 2026-11-06 | Classification: Research | Status: Specification

## 1. Purpose and Scope

This blueprint specifies an executable validation and benchmark suite for Pazuzu 1.0-R1. It is written in response to a detailed critique demonstrating that prior synthesis documents treated truncated logs, prefix strings, arithmetic identities, and definitional statements as if they were verified measurements.

The suite is designed so that every claim is either (a) confirmed by code that runs against files on disk and produces a pass/fail result, or (b) explicitly marked OPEN. Definitions are recorded as definitions. They are not counted as resolved empirical claims.

Core invariant of the suite:

> A claim is RESOLVED only when a named command, executed against named files, produces a logged result that satisfies a pre-declared acceptance criterion. All other claims remain OPEN or PARTIAL.

## 2. Findings Addressed by This Suite

The suite directly addresses the following defects identified in the source materials:

| Defect | Required Response |
|---|---|
| Hash prefixes | Full SHA-256 of real files printed; arithmetic-progression strings rejected |
| Lean truncation | Either a complete Lean file that builds, or the claim marked OPEN |
| λ contradiction | Explicit decision: either λ(T)=0 is dropped for substrate mode, or λ_min is not a lower bound |
| P1/P2 overclaim | Raw data files required; false-positive rate reported; scope limited to substrate |
| 192-term padding | H_j must be defined operators or the sum is excluded from the operational definition |
| Status inflation | Definitional progress counted separately from empirical verification |

## 3. Required Deliverables

The following artifacts must exist on disk before any claim can move from OPEN to RESOLVED. Absence of any item leaves the associated claims OPEN.

### 3.1 Directory Layout

All paths are relative to the repository root.

- `artifacts/` — the 14 files whose full SHA-256 hashes are claimed
- `data/` — CSV/JSON evidence files with documented row counts
- `lean/SophiaConvergence.lean` — complete Lean 4 source (or claim OPEN)
- `src/pazuzu_r1.py` — executable PID / λ-flow implementation
- `src/verify_all.py` — hash and structural verification
- `tests/` — unit and integration tests with fixed seeds
- `logs/` — timestamped run logs containing full hashes and metrics
- `MANIFEST.sha256` — full hashes, one per line, format: `<64-hex> <path>`

### 3.2 File Requirements

Each claimed artifact must be a real file. Placeholder strings, truncated logs, and arithmetic progressions in hex are rejected by the verifier.

## 4. Verification Suite Specification

### 4.1 verify_all.py — Artifact Integrity

Command:

```bash
python verify_all.py --check-hashes --full-sha256 --manifest MANIFEST.sha256
```

Behavior:

- Read `MANIFEST.sha256`.
- For each entry, compute the full SHA-256 of the file on disk.
- Print the complete 64-character hex digest (not a prefix).
- Reject any digest that matches a known placeholder pattern (arithmetic progression in hex, repeated nibble sequences, or length < 64).
- Exit 0 only if all 14 files exist, hashes match, and no placeholder is detected.
- Exit non-zero otherwise; print the failing path and computed hash.

Acceptance criterion: exit code 0 and a log containing 14 full 64-character SHA-256 digests that do not match placeholder patterns.

### 4.2 pazuzu_r1.py — λ-Flow PID Controller

Command:

```bash
python pazuzu_r1.py --evaluate --seed 13 --steps 1000 --output logs/lambda_trace.csv
```

Required implementation:

- A discrete-time PID controller with the stated gains `K_p = φ^{-1}`, `K_i = φ^{-3}`, `K_d = φ^{-2}`.
- A state variable λ whose update is logged at every step.
- A safety clamp that enforces the spectral-flow constraint outside licensed windows.
- Deterministic behavior under `--seed-override strict`.

Acceptance criteria (all must hold):

- The CSV contains exactly the requested number of rows plus a header.
- λ is finite at every step (no NaN, no Inf).
- Under the safety constraint, λ does not increase in any non-exploratory window.
- The final λ is recorded with a TRL label of Simulation-Emulated.

This test demonstrates movement (or failure to move). It does not claim hardware measurement.

### 4.3 λ Contradiction Resolution

The materials simultaneously claim λ(T) = 0 as a boundary condition and λ_min = 0.363626 as a positive lower bound under the HOR-Qudit substrate. These cannot both be success conditions.

Required decision (one must be chosen and recorded in DECISION.md):

- **Option A — Substrate mode:** λ(T) = 0 is retired. The operational target becomes λ_min ≤ λ ≤ λ_ceiling, with the Sophia mapping treated as a formalization of a positive floor.
- **Option B — Arithmetic only:** λ_min = 0.363626 is recognized as an arithmetic identity (φ⁻² − 0.017 − 0.00134), not a proven lower bound on the dynamical system. The Lean claim is marked OPEN until a complete proof is supplied.
- **Option C — Mode split:** Pazuzu-only deployments retain λ(T) = 0; HOR-Qudit substrate deployments use the positive floor. Claims are labeled by deployment mode.

Until DECISION.md exists and is referenced by the verifier, the λ(T)=0 claim for substrate deployments is marked FALSIFIED by the supplied numbers.

### 4.4 Lean 4 Claim

If `lean/SophiaConvergence.lean` exists and is complete:

```bash
lake build lean/SophiaConvergence.lean
```

Acceptance: the build succeeds and the log contains the theorem statement that is claimed. A truncated file that ends mid-theorem does not satisfy this criterion.

If the file is absent or truncated, the claim remains OPEN. Arithmetic verification that a subtraction is positive is not accepted as a convergence proof.

### 4.5 P1 / P2 Data Requirements

**P1 (forcing vs greedy):**

- Raw CSV must exist with documented row count.
- The script must recompute the means, standard deviations, and paired p-value from the CSV.
- The reported n must match the file. Inconsistent n (100 vs 50) is a failure.
- Result is labeled substrate-specific; it does not transfer to Pazuzu-only deployments.

**P2 (H¹ detection):**

- Raw JSON must exist.
- False-positive rate must be reported. 3/64 no-error samples with H¹ ≠ 0 is a 4.7 % false-positive rate and must be stated as such.
- A detector is not labeled validated until the false-positive rate is bounded on a larger sample or the claim is restricted to the supplied set.

## 5. Benchmark Metrics

The following metrics are collected by the suite. Each carries a TRL label and a classification (Derived / Forced / Design Choice / Empirical Fit).

| Metric | Source | TRL | Classification |
|---|---|---|---|
| SHA-256 match count | verify_all.py | Artifact-Verified | Empirical Fit |
| λ final (sim) | pazuzu_r1.py | Simulation-Emulated | Empirical Fit |
| λ monotonicity | pazuzu_r1.py | Simulation-Emulated | Derived |
| PID step response | pazuzu_r1.py | Simulation-Emulated | Design Choice |
| P1 p-value | data CSV | Artifact-Verified | Empirical Fit |
| P2 false-positive rate | data JSON | Artifact-Verified | Empirical Fit |
| Lean build status | lake build | Formal Proof or OPEN | Derived |

## 6. Acceptance Protocol

A single command runs the full suite:

```bash
python verify_all.py --full --output logs/suite_report.json
```

The report JSON must contain:

- timestamp
- git commit hash (or explicit "uncommitted")
- full SHA-256 of every artifact
- λ-trace summary statistics
- P1 and P2 recomputed statistics
- Lean build status (or OPEN)
- λ-decision reference
- list of claims still OPEN

Exit code 0 means every claim that is marked RESOLVED in the report has an accompanying logged measurement. Exit code non-zero means at least one claimed-resolved item failed its criterion.

## 7. What This Suite Does Not Claim

- It does not claim hardware measurement of any quantity.
- It does not claim that the 192-term sum defines a unique operator until each H_j is given a domain and the sum is shown to converge in the operator norm.
- It does not transfer substrate-specific results (P1, P2, Sophia) to Pazuzu-only deployments.
- It does not resolve governance implementation items (RBAC, kill switch, bias audit) by writing requirements.
- It does not count a written definition as an empirical resolution.

## 8. Minimal First Deliverable

The smallest set of files that ends the cycle of additional tables is:

1. `MANIFEST.sha256` containing full hashes of real files.
2. `src/verify_all.py` that computes and prints those hashes and exits non-zero on mismatch or placeholder.
3. `src/pazuzu_r1.py` that runs a seeded PID loop and writes a λ-trace CSV.
4. `DECISION.md` that chooses Option A, B, or C for the λ contradiction.
5. A log from a single successful run of the two scripts.

Until these five items exist and pass, every quantitative claim in the prior synthesis remains OPEN.

## 9. Document Control

| Version | Date | Change |
|---|---|---|
| V1.0 | 2026-11-06 | Initial executable verification blueprint |

End of Blueprint.
