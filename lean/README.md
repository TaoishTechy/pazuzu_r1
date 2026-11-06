# lean/ — STATUS: OPEN (claim C08, blocking C11b)

The blueprint (§4.4) requires either a **complete Lean 4 source file** that
builds, or the Sophia-convergence claim marked OPEN. The file
`lean/SophiaConvergence.lean` was **not supplied** — the claim is OPEN.

## Acceptance criteria (blueprint §4.4)

```bash
lake build lean/SophiaConvergence.lean
```

- The build succeeds and the log contains the claimed theorem statement.
- The theorem must establish, for the stated dynamical conditions:
  - λ_min > 0 (the Sophia-point convergence target `S* = (φ⁻¹)¹²` mapped
    onto the substrate floor),
  - `N_steps ≤ 6127` for `ε_tol = 10⁻¹⁰`.
- **A truncated file that ends mid-theorem does not satisfy this criterion.**
- **Arithmetic verification that a subtraction is positive is not accepted
  as a convergence proof** — in particular,
  `φ⁻² − 0.017 − 0.00134 = 0.36362601125` is recorded in this repo only as
  an arithmetic identity (claim C11), never as a dynamical lower bound
  (claim C11b).

## Procedure once a proof exists

1. Commit the complete `lean/SophiaConvergence.lean` (plus a `lakefile.lean`
   / `lean-toolchain` if required).
2. `python src/verify_all.py --lean-check --full --output logs/suite_report.json`
3. C08 moves to RESOLVED only if `lake build` exits 0 and the theorem
   statement is present; C11b may then be re-evaluated against the proof.
