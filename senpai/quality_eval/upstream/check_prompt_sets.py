#!/usr/bin/env python3
"""Verify prompt-hash equality across downstream quality outputs.

Usage:
  python check_prompt_sets.py ARM_DIR [ARM_DIR ...]

Each ARM_DIR may contain outputs for MMLU-Pro, GPQA-Diamond, AIME, and GSM8K.
For every task found in any directory, the script requires that task in every
directory and compares all ``(id, prompt_sha)`` pairs. Tasks absent everywhere
are skipped.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


PATTERNS = {
    "mmlu_pro": ["mmlu_pro*.json"],
    "gpqa_diamond": ["gpqa_diamond*.json"],
    "aime": ["aime*.json", "*_aime_*.json"],
    "gsm8k": ["gsm8k*.json", "*gsm8k*.json"],
}

ROW_KEYS = {
    "mmlu_pro": "per_sample",
    "gpqa_diamond": "per_sample",
    "aime": "per_problem",
    "gsm8k": "per_problem",
}


def prompt_pairs(path: Path, row_key: str) -> tuple[tuple[str, str], ...]:
    data = json.loads(path.read_text())
    rows = data.get(row_key)
    if not isinstance(rows, list):
        raise ValueError(f"{path}: missing {row_key} list")
    pairs = []
    for row in rows:
        sid = str(row.get("id"))
        sha = row.get("prompt_sha")
        if not sha:
            raise ValueError(f"{path}: sample {sid} missing prompt_sha")
        pairs.append((sid, str(sha)))
    return tuple(sorted(pairs))


def files_for(arm_dir: Path, patterns: list[str]) -> list[Path]:
    out: set[Path] = set()
    for pattern in patterns:
        out.update(arm_dir.glob(pattern))
    return sorted(out)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("arm_dirs", nargs="+", type=Path)
    args = parser.parse_args()

    ok = True
    for task, patterns in PATTERNS.items():
        arm_files = [(arm_dir, files_for(arm_dir, patterns)) for arm_dir in args.arm_dirs]
        if not any(files for _, files in arm_files):
            print(f"[{task}] skipped (absent in every directory)")
            continue

        reference: tuple[tuple[str, str], ...] | None = None
        reference_file: Path | None = None
        for arm_dir, files in arm_files:
            if not files:
                print(f"[{task}] missing in {arm_dir}")
                ok = False
                continue
            for path in files:
                pairs = prompt_pairs(path, ROW_KEYS[task])
                if reference is None:
                    reference = pairs
                    reference_file = path
                    print(f"[{task}] reference {path} n={len(pairs)}")
                    continue
                if pairs != reference:
                    print(f"[{task}] MISMATCH {path} vs {reference_file}")
                    print(f"  n={len(pairs)} ref_n={len(reference)}")
                    ok = False
                else:
                    print(f"[{task}] ok {path} n={len(pairs)}")

    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
