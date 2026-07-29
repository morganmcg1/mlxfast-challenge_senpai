#!/usr/bin/env python3
"""Summarize five-pass quality refresh outputs.

Usage:
  python summarize_five_pass.py runs/baseline runs/pr801 runs/ple

Each arm directory may contain pass_1 ... pass_5 subdirectories. The script
prints JSON with mean/stdev/count for the README-facing metrics.
"""
from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
from typing import Any


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def metric(path: Path, key: str) -> float | None:
    if not path.exists():
        return None
    value = read_json(path).get(key)
    return float(value) if isinstance(value, (int, float)) else None


def first_metric(paths: list[Path], key: str) -> float | None:
    for path in paths:
        value = metric(path, key)
        if value is not None:
            return value
    return None


def mean_or_none(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def pass_dirs(arm_dir: Path) -> list[Path]:
    passes = sorted(p for p in arm_dir.glob("pass_*") if p.is_dir())
    return passes or [arm_dir]


def summarize_values(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {"mean": None, "stdev": None, "n": 0}
    return {
        "mean": sum(values) / len(values),
        "stdev": statistics.stdev(values) if len(values) > 1 else 0.0,
        "n": len(values),
    }


def summarize_arm(arm_dir: Path) -> dict[str, Any]:
    rows: dict[str, list[float]] = {
        "ppl": [],
        "aime": [],
        "gpqa_sampled": [],
        "gpqa_greedy": [],
        "gpqa_ranked": [],
        "mmlu": [],
        "gsm8k": [],
    }
    for pass_dir in pass_dirs(arm_dir):
        values = {
            "ppl": metric(pass_dir / "ppl_summary.json", "ppl"),
            "aime": metric(pass_dir / "aime_greedy.json", "maj_k_accuracy"),
            "mmlu": metric(pass_dir / "mmlu_pro_greedy.json", "accuracy"),
            "gpqa_greedy": metric(pass_dir / "gpqa_diamond_greedy.json", "accuracy"),
            "gpqa_ranked": metric(
                pass_dir / "gpqa_diamond_ranked_greedy.json",
                "accuracy",
            ),
            "gsm8k": first_metric(sorted(pass_dir.glob("*gsm8k*_greedy*.json")), "accuracy"),
        }
        sampled = [
            value
            for value in (
                metric(path, "accuracy")
                for path in sorted(pass_dir.glob("gpqa_diamond_sampled_s*.json"))
            )
            if value is not None
        ]
        values["gpqa_sampled"] = mean_or_none(sampled)

        for name, value in values.items():
            if value is not None:
                rows[name].append(value)

    return {
        "arm": arm_dir.name,
        "path": str(arm_dir),
        "metrics": {name: summarize_values(values) for name, values in rows.items()},
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("arm_dirs", nargs="+", type=Path)
    args = parser.parse_args()

    payload = {"arms": [summarize_arm(path) for path in args.arm_dirs]}
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
