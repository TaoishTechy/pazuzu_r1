# Pazuzu 1.0-R1 — Validation & Benchmark Suite

Executable verification repository for **Pazuzu 1.0-R1 (HOR-Qudit)**, built
exactly to the supplied **Validation & Benchmark Suite Blueprint V1.0**
(`docs/source/Pazuzu_R1_Validation_Benchmark_Suite_Blueprint.md`).

<img width="1122" height="730" alt="image" src="https://github.com/user-attachments/assets/107ea1fc-36da-4f74-9da2-d836eb3690af" />


> **Core invariant (blueprint §1).** A claim is RESOLVED only when a named
> command, executed against named files, produces a logged result that
> satisfies a pre-declared acceptance criterion. All other claims remain
> OPEN or PARTIAL. Definitions are recorded as definitions and are never
> counted as resolved empirical claims.

**Is this AGI?** No. This repository is a verification harness for a
research specification. It implements a seeded PID λ-flow simulation and
the hash/claim discipline around it — nothing more.

---

## Status snapshot (2026-11-06, repo bootstrap)

| Status | Count | Claim IDs |
|---|---|---|
| RESOLVED (verified by code in this repo) | 9 | C01, C02, C03, C04, C05, C09, C11, C13, C14 |
| OPEN (external HOR-Qudit artifacts / proofs required) | 7 | C01e, C06, C07, C08, C10, C11b, C12 |

\* live counts are computed by the suite — see `logs/suite_report.json`
(`claims` array) and `docs/CLAIMS.md`.

Substrate-specific claims (P1 forcing-vs-greedy, P2 H¹ detection, the
Sophia 6,127-step trace, the 14 HOR-Qudit artifacts) are **not** present in
this repository: their evidence files were never supplied, and the
SHA-256 *prefixes* printed in the source spec match the blueprint's
placeholder patterns and are rejected as evidence. The recompute tooling is
implemented, unit-tested on clearly-labeled synthetic fixtures, and ready
the moment real evidence lands in `artifacts/` + `data/`.

## Quick start

```bash
# 1 — λ-flow simulation (pazuzu mode, seed 13, 1000 steps)
python src/pazuzu_r1.py --evaluate --seed 13 --steps 1000 \
    --output logs/lambda_trace.csv --snapshot logs/lambda_summary.json \
    --seed-override strict --trl-labels --classification-matrix

# 2 — full verification suite (hashes, determinism, P1/P2, Lean, claims)
python src/verify_all.py --full --output logs/suite_report.json

# 3 — unit + integration tests (fixed seeds, stdlib only)
python -m unittest discover -s tests -v
```

Requirements: **Python ≥ 3.10**, standard library only. No `pip install`.
(Lean checks additionally need the `lake` toolchain — absent file ⇒ claim
stays OPEN, never fails.)

## What is implemented (blueprint §8 minimal deliverable + §3.1 layout)

| Blueprint item | Where | State |
|---|---|---|
| `MANIFEST.sha256` — full hashes of real files | `MANIFEST.sha256` (regenerate with `src/gen_manifest.py`) | done |
| `src/verify_all.py` — full-SHA-256 verify, placeholder rejection, exit semantics | `src/verify_all.py` | done |
| `src/pazuzu_r1.py` — seeded PID λ-flow → λ-trace CSV | `src/pazuzu_r1.py` | done |
| `DECISION.md` — Option A/B/C | `DECISION.md` → **Option C (mode split)** | done |
| Log of a single successful run of both scripts | `logs/verify_run.log`, `logs/suite_report.json` | done |
| `artifacts/`, `data/`, `lean/`, `tests/`, `logs/` layout | present; `artifacts/`+`data/`+`lean/` hold OPEN markers | done |

### λ-flow controller (blueprint §4.2)

Discrete PID with the R1.2 critical constants `Kp=φ⁻¹, Ki=φ⁻³, Kd=φ⁻²`
(leaky integrator, anti-windup), λ-update
`dλ = −α·λ + β·u + η`, zero-mean white Gaussian η (σ=0.01, audit item 21),
safety clamps: **λ-ceiling 0.5**, **spectral-flow constraint** (λ never
increases outside licensed exploration windows — every 100 steps, length
10; clamp events logged per step), and **λ-floors**: the R1 governance floor
λ ≥ 10⁻⁹ in pazuzu mode (audit #19) and the Sophia floor
λ ≥ 0.36362601125 in substrate mode. Deterministic: the trace CSV is a
byte-identical pure function of `(seed, steps, mode, start_lambda)` —
re-proven at every suite run by re-executing and comparing SHA-256.

### Deployment modes (DECISION.md, Option C)

| Mode | Setpoint | Extra constraint |
|---|---|---|
| `--mode pazuzu` | 0 (λ(T)=0 control target) | ceiling + spectral-flow |
| `--mode substrate` | φ⁻² − 0.017 − 0.00134 = 0.36362601125 | ceiling + spectral-flow + floor |

## Repository layout

```
pazuzu_r1/
├── MANIFEST.sha256          full SHA-256 of every tracked content file
├── DECISION.md              λ contradiction → Option C (mode split)
├── README.md                this file
├── LICENSE                  MIT
├── requirements.txt         stdlib-only note (nothing to install)
├── src/
│   ├── pazuzu_r1.py         seeded PID λ-flow CLI (blueprint §4.2)
│   ├── verify_all.py        verification suite + claims report (§4.1/§6)
│   ├── stats_tools.py       dependency-free paired stats (t via betainc)
│   └── gen_manifest.py      MANIFEST.sha256 generator
├── tests/                   stdlib unittest, fixed seeds
│   └── fixtures/            SYNTHETIC P1/P2 fixtures (code tests only)
├── artifacts/               OPEN marker — 14 HOR-Qudit artifacts absent
├── data/                    OPEN marker — P1/P2 raw evidence absent (schemas documented)
├── lean/                    OPEN marker — SophiaConvergence.lean absent
├── logs/                    committed evidence: traces, summaries, run log, suite report
├── docs/
│   ├── CLAIMS.md            human-readable claims registry (mirrors the report)
│   ├── API_ROADMAP.md       24+8 function API plan (R1 §5) — next revision
│   └── source/              the four supplied spec documents + blueprint (verbatim)
└── .github/workflows/ci.yml unittest + verify_all --full on push/PR
```

## TRL & classification discipline

Every quantitative output carries `trl = Simulation-Emulated`
(HOR-Qudit v2.5 TRL table) and a classification
(Derived / Topologically Forced / Design Choice / Empirical Fit) —
mandatory per R1 §6.2. Nothing in this repository claims hardware
measurement, substrate-specific benefits, or a proven convergence bound.

## Maintaining the manifest

`MANIFEST.sha256` pins content files (the volatile report/log outputs are
deliberately excluded — see `src/gen_manifest.py`). After an *intentional*
edit:

```bash
python src/gen_manifest.py > MANIFEST.sha256
git add MANIFEST.sha256 && git commit -m "chore: refresh manifest"
```

An accidental drift is caught by `verify_all.py` (exit 1 with the failing
path and computed hash).

## CI

`.github/workflows/ci.yml` runs the unit tests and
`python src/verify_all.py --full` on every push/PR and uploads
`suite_report.json` as an artifact.

## Pushing to GitHub

The git history is prepared with `origin` pointing at
`git@github.com:TaoishTechy/pazuzu_r1.git`. After creating the (empty)
repository on GitHub:

```bash
git push -u origin main --tags        # SSH remote (default)
# or: git remote set-url origin https://github.com/TaoishTechy/pazuzu_r1.git
```

## License

MIT — see `LICENSE`. Note for provenance: the supplied R1 audit (item 137)
suggests Apache-2.0 "per HOR-Qudit"; **MIT is the maintainer's explicit
choice at repo bootstrap (2026-11-06)** and the discrepancy is recorded in
`docs/source/README.md`.

## Provenance

All four supplied specification documents (Pazuzu 1.0-R1 spec, original
audit + 144 Stage-5 proposals, R1-revised audit, Gap-Filling R1.2) and the
blueprint (`.docx` + markdown transcription) are preserved verbatim in
`docs/source/`. Where those documents conflict with the blueprint's
verification discipline, **the blueprint wins** in this repository.
