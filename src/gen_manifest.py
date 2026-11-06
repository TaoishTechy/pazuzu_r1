#!/usr/bin/env python3
"""Regenerate MANIFEST.sha256 — full SHA-256 hashes, one per line.

Format (blueprint §3.1):  <64-hex> <path>

Path coverage: every git-tracked file at repository root EXCEPT the volatile
outputs that cannot be meaningfully self-hashed:

  * MANIFEST.sha256                (itself)
  * logs/suite_report.json         (contains timestamp + git commit)
  * logs/verify_run.log            (timestamped console log of a verify run)
  * logs/lambda_summary*.json      (contains wall-clock timestamp)

Everything else — including the deterministic λ-trace CSVs — is hashed in
full. Tracked-but-deleted files are skipped with a warning; untracked files
are ignored (add them with `git add` first).

Usage:  python src/gen_manifest.py > MANIFEST.sha256
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXCLUDED = {
    "MANIFEST.sha256",
    "logs/suite_report.json",
    "logs/verify_run.log",
    "logs/lambda_summary.json",
    "logs/lambda_summary_substrate.json",
}


def git_tracked_files() -> list[str]:
    try:
        out = subprocess.run(
            ["git", "ls-files", "-c"], cwd=ROOT, check=True, capture_output=True,
            text=True, timeout=30,
        ).stdout
        return [line for line in out.splitlines() if line]
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("WARNING: git unavailable or not a repo; falling back to walk "
              "(untracked files will be included)", file=sys.stderr)
        skip_dirs = {".git", "__pycache__", ".venv", ".pytest_cache"}
        files = []
        for p in sorted(ROOT.rglob("*")):
            if p.is_dir() or any(part in skip_dirs for part in p.parts):
                continue
            if p.name == ".DS_Store" or p.suffix == ".pyc":
                continue
            files.append(str(p.relative_to(ROOT)))
        return files


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    missing = []
    lines = []
    for rel in sorted(git_tracked_files()):
        if rel in EXCLUDED:
            continue
        path = ROOT / rel
        if not path.is_file():
            missing.append(rel)
            continue
        lines.append(f"{sha256_of(path)} {rel}")
    for rel in missing:
        print(f"WARNING: tracked but absent, skipped: {rel}", file=sys.stderr)
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
