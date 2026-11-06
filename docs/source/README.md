# docs/source — Provenance

This directory preserves the **user-supplied source materials** this repository was
built from, unmodified, so every downstream claim is traceable.

| File | Origin | Contents |
|---|---|---|
| `Pazuzu_1.0_R1_HOR-Qudit.md` | Supplied paste, part 1 (verbatim) | Pazuzu 1.0-R1 (HOR-Qudit) consolidated specification: two-layer architecture, `H_crit^(R1)`, Sophia mapping, Axiom set v1.0-R1, API v1.0-R1 (24 + 8), governance, acceptance protocol, falsifiability conditions, security stack, risks. |
| `Pazuzu_1.0_FULL_Audit_and_Stage5_Proposals.md` | Supplied paste, part 2 (verbatim) | Original Pazuzu 1.0 FULL audit: 144 shortcomings, 96 enhancements, 144 Stage-5 proposals. |
| `Pazuzu_1.0_FULL_Audit_R1.md` | Supplied paste, part 3 (verbatim) | Audit revised for R1: all 144 + 96 + 144 items tracked with R1 status (RESOLVED / PARTIAL / OPEN / SUPERSEDED / SUBSTRATE-SPECIFIC) and resolution notes. |
| `144_Point_Enhancement_Gap_Filling_R1.2.md` | Supplied paste, part 4 (verbatim) | Gap-filling report R1.2: six-domain enhancement tracking, critical-constants table, acceptance protocol. |
| `Pazuzu_R1_Validation_Benchmark_Suite_Blueprint.docx` | Supplied file (original) | Executable Verification Protocol V1.0 — the authoritative build spec for this repository. |
| `Pazuzu_R1_Validation_Benchmark_Suite_Blueprint.md` | Markdown transcription of the docx | Same content, formatted for reading/diffing. Verbatim except heading/table markup. |

**Splitting note.** The paste concatenated four documents; they were separated at
their `# ` top-level headings by `scripts/split_sources.py` (run once at repo
bootstrap; kept out of the repo). Only trailing `---` separator runs were
stripped; no wording was changed.

**Classification.** Source headers state: Research/Integration. HOR-Qudit-derived
portions retain "Restricted" handling if used operationally.

**Known discrepancy (recorded, not resolved here).** The R1 audit (item 137)
suggests Apache-2.0 "per HOR-Qudit"; this repository ships **MIT** per the
maintainer's explicit license choice at bootstrap (2026-11-06). See `LICENSE`
and `README.md`.
