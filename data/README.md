# data/ — STATUS: OPEN (claims C06, C07)

The blueprint (§4.5) requires **raw evidence files** with documented row
counts before the P1/P2 claims may move from OPEN to RESOLVED. None are
present: the corresponding HOR-Qudit artifacts
(`forcing_greedy_vs_generic_seed13.csv`, `topos_h1_detection_seed17.json`)
were never supplied to this repository.

The recompute tooling is implemented and unit-tested — on **synthetic**
fixtures in `tests/fixtures/` that exist only to test the code paths and are
never cited as evidence.

## P1 — forcing vs greedy (claim C06)

Expected file: `data/p1_forcing_vs_greedy.csv`

Required schema (one row per paired run):

```
pair_id,seed,forcing,greedy
1,13,50.0,47.0
...
```

The verifier recomputes: forcing mean, greedy mean and SD, mean paired
difference, paired two-sided p-value (`src/stats_tools.py`, exact via the
regularized incomplete beta function) and a seeded permutation cross-check.

Acceptance (substrate-specific; does **not** transfer to Pazuzu-only
deployments): forcing meets 50/50 dense sets; greedy 47.2 ± 1.8; paired
p < 0.001. **The reported n must match the file's row count — an
inconsistency (e.g. 100 vs 50) is a failure** (blueprint §4.5).

## P2 — H¹ detection (claim C07)

Expected file: `data/topos_h1_detection.json`

Required schema:

```json
{"samples": [{"sample_id": 1, "has_logical_error": false, "h1_nonzero": false},
             ...]}
```

The verifier recomputes: number of logical errors, detection count, and the
**false-positive rate** = (no-error samples with H¹ ≠ 0) / (no-error samples).
On the supplied set this is 3/64 ≈ **4.7 %** and must be stated as such. A
detector is not labeled validated until the FP rate is bounded on a larger
sample or the claim is restricted to the supplied set (blueprint §4.5).

## Procedure once real evidence exists

1. Drop the raw files here with the schemas above.
2. `python src/verify_all.py --test-p1p2 --full --output logs/suite_report.json`
3. Claims move RESOLVED only if the recomputed statistics satisfy the
   acceptance criteria; otherwise they are marked **FALSIFIED** (R1 §8) —
   which is a legitimate, recorded outcome.
