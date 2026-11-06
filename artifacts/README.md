# artifacts/ — STATUS: OPEN (claim C01e)

The blueprint (§3.1, §4.1) requires the **14 HOR-Qudit v2.5 artifacts** whose
full SHA-256 hashes are claimed, as real files on disk, verified by
`src/verify_all.py --check-hashes --full-sha256`.

**They are not present in this repository.** The evidence was never supplied
to the repo bootstrap; the Pazuzu 1.0-R1 spec (§7.3) only names 6 of the 14
and cites hashes as short *prefixes* — which match the blueprint's
placeholder patterns (short prefixes, arithmetic-pair structure) and are
therefore **rejected as evidence**. The full manifest is "per HOR-Qudit v2.5
§1.1", which was not supplied either.

## Known named artifacts (from Pazuzu 1.0-R1 §7.3)

| Artifact | Spec-supplied "hash" (REJECTED as placeholder) | Role |
|---|---|---|
| `run_420M_v22.py` | `a3f8c2d1…f0a1` | Main simulation |
| `me_049_072_forcing.py` | `b7d4e1f2…b8c9` | Forcing module / P1 |
| `sophia_convergence_v24.ipynb` | `d1b8a4c2…a0b1` | Sophia convergence |
| `forcing_greedy_vs_generic_seed13.csv` | `a2c4e6b8…f0a2` | P1 evidence |
| `topos_h1_detection_seed17.json` | `b5d7f9a1…e3b5` | P2 evidence |
| `sophia_trace_seed3.csv` | `e9a1c7b8…f2a4` | 6,127-step trace |

(the remaining 8 artifact names are unknown to this repository)

## How to resolve C01e (and unlock C06/C07/C10)

1. Obtain the real artifact files and place them in this directory.
2. `python src/gen_manifest.py > MANIFEST.sha256` (hashes everything, in full).
3. `python src/verify_all.py --check-hashes --full-sha256` — full 64-character
   digests are printed and placeholder-checked.
4. `python src/verify_all.py --full --output logs/suite_report.json` —
   C01e moves to RESOLVED only when 14/14 files exist, hashes match, and no
   placeholder pattern is detected. C06/C07/C10 additionally require the raw
   evidence files in `data/` (see `data/README.md`).
