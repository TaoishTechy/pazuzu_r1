# DECISION — λ(T)=0 vs λ_min=0.363626 Contradiction

**Recorded:** 2026-11-06 (repo bootstrap)
**Required by:** Validation & Benchmark Suite Blueprint §4.3
**Supersedes:** nothing (first decision record)
**Status:** Active — referenced by `src/verify_all.py` (claim C09)

---

## Decision: Option C — mode split

> **Option C — Mode split:** Pazuzu-only deployments retain λ(T) = 0;
> HOR-Qudit substrate deployments use the positive floor. Claims are
> labeled by deployment mode.

The supplied materials simultaneously claim λ(T) = 0 as a boundary
condition and λ_min = 0.36362601125 as a positive lower bound under the
HOR-Qudit substrate. These cannot both be success conditions for the same
deployment (blueprint §4.3). Option C is chosen because it preserves both
original claims **with explicit mode labels** and matches the R1 spec's own
restriction that "the Sophia mapping is substrate-specific … not a
universal claim for every Pazuzu deployment" (Pazuzu 1.0-R1 §3.4).

## Mode table (binding for this repository)

| Deployment mode | λ target | Status | TRL |
|---|---|---|---|
| **pazuzu-only** | setpoint = 0; λ(T)=0 retained as the control target; λ decays toward zero and is governed to λ ≥ λ_floor = 10⁻⁹ (R1 audit #19), i.e. λ_dom ≈ 0 | Claim tracked (C02–C05 demonstrate the simulated decay); universal reachability claim remains out of scope | Simulation-Emulated |
| **HOR-Qudit substrate** | setpoint = λ_min = φ⁻² − δ_forcing − δ_topos = 0.36362601125; enforced band λ_min ≤ λ ≤ λ_ceiling | Floor value verified as an **arithmetic identity** (claim C11); floor as a *proven dynamical lower bound* is **OPEN** (claim C11b, blocked on C08) | Simulation-Emulated |

## Consequences

1. `src/pazuzu_r1.py --mode pazuzu` uses setpoint 0 with the R1 governance
   floor λ ≥ 10⁻⁹; `--mode substrate` uses the Sophia floor as setpoint and
   enforces λ ≥ λ_min (hard clamp, logged in the `clamp_floor` column).
   The pazuzu floor exists because a strict spectral-flow non-increase rule
   would otherwise let λ ratchet through zero and random-walk negative —
   the floor pins the controlled system at λ_dom ≈ 0, matching the R1
   Stage-5 invariant "λ_dom ≈ 0 under governance".
2. The verifier (`src/verify_all.py`) checks both modes and labels every
   λ-claim by mode. Cross-mode transfer of substrate results (P1, P2,
   Sophia) is prohibited (blueprint §7).
3. λ_min = 0.36362601125 is treated as an arithmetic identity
   (φ⁻² = 0.38196601125; minus the supplied bounds δ_forcing ≤ 1.70×10⁻²
   and δ_topos ≤ 1.34×10⁻³). **It is not accepted as a proven lower bound
   of the dynamical system.** A complete Lean 4 proof or an empirical
   demonstration would be required (blueprint §4.4).
4. Falsifiability (Pazuzu 1.0-R1 §8) is inherited per mode:
   - pazuzu mode falsified if λ_dom fails to approach zero under licensed
     control windows without external forcing;
   - substrate mode falsified if measured δ_forcing > 1.70×10⁻² or
     δ_topos > 1.34×10⁻³ on new seeds/samples, or if convergence needs
     > 6127 steps at ε_tol = 10⁻¹⁰.
5. Any future revision that retires the λ(T)=0 target (Option A) or
   re-scopes the floor (Option B) must replace this file and update
   `src/pazuzu_r1.py`, `src/verify_all.py` (claim C09), and
   `docs/CLAIMS.md` in the same commit.

## References

- Blueprint §4.3 (decision requirement), §7 (no cross-mode transfer)
- Pazuzu 1.0-R1 §3.1 (λ-flow), §3.4 (Sophia mapping note), §8 (falsifiability)
- `docs/CLAIMS.md` — C09 (this decision), C11 (arithmetic), C11b (lower bound)
