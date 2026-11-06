# API Roadmap — Pazuzu API v1.0-R1 (24 core + 8 bridge functions)

Scope note: the repo bootstrap (this revision) implements the **validation &
benchmark suite** (blueprint-complete). The full programmatic API below is
specified in Pazuzu 1.0-R1 §5 and planned for v0.2. This roadmap records the
planned signatures so the audit criticism "signatures, inputs, outputs
missing" (item 42) is answered at the spec level already.

Core object: `Axiom` dataclass — `id, stmt, priority, depends_on, meta`
(R1 audit item 43 resolution). Persistence: append-only **hash-chained**
ledger with JSON import/export; λ-trajectory serialization as CSV (canonical,
this repo) plus JSONL/Parquet (R1 audit items 17/68).

## 5.1 Core Pazuzu API (24) — planned v0.2

| Group | Function | Planned signature | Notes |
|---|---|---|---|
| IO (4) | `load_json` | `(path: Path) -> Ledger` | schema-validated axiom objects |
| | `dump_json` | `(ledger: Ledger, path: Path) -> Sha256` | returns content hash for the manifest |
| | `import_yaml` | `(path: Path) -> Ledger` | optional dependency (pyyaml) |
| | `export_yaml` | `(ledger: Ledger, path: Path) -> Sha256` | |
| Axiom ops (5) | `add_axiom` | `(ledger, Axiom) -> Version` | semantic versioning (audit 44/65) |
| | `update_axiom` | `(ledger, id, patch) -> Version` | immutable history, rollback-able |
| | `remove_axiom` | `(ledger, id) -> Tombstone` | tombstone, never silent delete |
| | `get_axiom` | `(ledger, id) -> Axiom` | |
| | `search_axioms` | `(ledger, query) -> list[Axiom]` | id/stmt/meta substring + tag |
| Policy/paradox (5) | `set_policy` | `(ledger, Policy) -> None` | permission model required (audit 45) |
| | `detect_paradox` | `(ledger) -> list[Paradox]` | contradiction scan over depends_on |
| | `isolate` | `(ledger, id) -> Sandbox` | tiered routing: sandbox→shadow→limited→full |
| | `override` | `(ledger, id, reason) -> AuditEvent` | audit-trail mandatory (audit 73) |
| | `sandbox` | `(fn) -> SandboxContext` | |
| Graph/order (4) | `graph` | `(ledger) -> Graph` | NetworkX-compatible adjacency (audit 46) |
| | `topo` | `(graph) -> Order` | topological order; raises on cycle |
| | `cycles` | `(graph) -> list[Cycle]` | |
| | `impacts` | `(graph, id) -> set[Id]` | downstream impact set |
| Metrics/state (4) | `metrics` | `(run) -> Metrics` | every field TRL-labeled |
| | `snapshot` | `(state) -> Snapshot` | implemented for λ-flow in this repo |
| | `diff` | `(a: Snapshot, b: Snapshot) -> Diff` | |
| | `timeline` | `(ledger) -> list[Event]` | replayable from hash chain |
| Eval (2) | `plan` | `(goal, constraints) -> Plan` | |
| | `evaluate` | `(plan, harness) -> Result` | harness = this suite |

## 5.2 HOR-Qudit bridge API (8) — planned v0.2, provenance-only

Rule (R1 §5.2): `hor_*` functions **never silently promote HOR-Qudit
claims**; they attach provenance and TRL metadata, and they fail loudly when
evidence is absent.

| Function | Delegates to (today) | Behavior |
|---|---|---|
| `hor_sophia_converge()` | — | runs/checks a Sophia trace only when `artifacts/sophia_trace_seed3.csv` exists; enforces monotone distance + `N_steps ≤ 6127`; else raises `ClaimNotResolved(C10)` |
| `hor_verify_artifacts()` | `verify_all.check_manifest` | full SHA-256 + placeholder rejection (claim C01/C01e) |
| `hor_run_p1p2()` | `verify_all.check_p1 / check_p2` | recompute from raw data; substrate-specific labels; FP rate mandatory |
| `hor_lean_check()` | `verify_all.check_lean` | `lake build` gate; OPEN when file/toolchain absent |
| `hor_trl_label(metric)` | — | attaches TRL label; refuses unlabeled metrics downstream |
| `hor_classification_matrix()` | `pazuzu_r1.CLASSIFICATION_MATRIX` | Derived / Topologically Forced / Design Choice / Empirical Fit |
| `hor_security_audit()` | — | ZK (Groth16/BN254), TPM 2.0, PBFT `N=3f+1` checks — substrate deployment scope |
| `hor_hardware_plan()` | — | returns the Month 1–6 TRL-5 plan + pass/fail criteria as data; never converts simulation-emulated results into hardware-measured claims |

## Falsifiability hooks (already active in this repo)

The suite (not the API) is the current enforcement point: `src/verify_all.py`
fails loudly (exit 1) when a RESOLVED-declared claim breaks, and keeps every
substrate claim OPEN until real evidence exists — the exact behavior the
bridge API will inherit.
