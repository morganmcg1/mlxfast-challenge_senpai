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


def counts(path: Path, correct_key: str, total_key: str) -> tuple[int, int] | None:
    if not path.exists():
        return None
    payload = read_json(path)
    correct = payload.get(correct_key)
    total = payload.get(total_key)
    if (
        not isinstance(correct, int)
        or isinstance(correct, bool)
        or not isinstance(total, int)
        or isinstance(total, bool)
        or total < 1
        or not 0 <= correct <= total
    ):
        return None
    return correct, total


def first_counts(
    paths: list[Path],
    correct_key: str,
    total_key: str,
) -> tuple[int, int] | None:
    for path in paths:
        value = counts(path, correct_key, total_key)
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
        "overall_score": [],
    }
    aggregate_components: dict[str, dict[str, int]] = {}
    per_pass_overall: list[dict[str, Any]] = []
    for pass_index, pass_dir in enumerate(pass_dirs(arm_dir), start=1):
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

        component_counts = {
            "mmlu": counts(
                pass_dir / "mmlu_pro_greedy.json",
                "n_correct",
                "n_expected",
            ),
            "gpqa_greedy": counts(
                pass_dir / "gpqa_diamond_greedy.json",
                "n_correct",
                "n_expected",
            ),
            "gpqa_sampled": first_counts(
                sorted(pass_dir.glob("gpqa_diamond_sampled_s*.json")),
                "n_correct",
                "n_expected",
            ),
            "aime": counts(
                pass_dir / "aime_greedy.json",
                "n_correct_maj",
                "n_problems",
            ),
            "gsm8k": first_counts(
                sorted(pass_dir.glob("*gsm8k*_greedy*.json")),
                "n_correct",
                "n_problems",
            ),
        }
        present_counts = {
            name: value for name, value in component_counts.items() if value is not None
        }
        if present_counts:
            correct = sum(value[0] for value in present_counts.values())
            total = sum(value[1] for value in present_counts.values())
            values["overall_score"] = correct / total
            per_pass_overall.append(
                {
                    "pass": pass_index,
                    "correct": correct,
                    "total": total,
                    "score": correct / total,
                    "components": {
                        name: {
                            "correct": value[0],
                            "total": value[1],
                            "score": value[0] / value[1],
                        }
                        for name, value in present_counts.items()
                    },
                }
            )
            for name, value in present_counts.items():
                aggregate = aggregate_components.setdefault(
                    name,
                    {"correct": 0, "total": 0},
                )
                aggregate["correct"] += value[0]
                aggregate["total"] += value[1]

        for name, value in values.items():
            if value is not None:
                rows[name].append(value)

    overall_correct = sum(value["correct"] for value in aggregate_components.values())
    overall_total = sum(value["total"] for value in aggregate_components.values())
    return {
        "arm": arm_dir.name,
        "path": str(arm_dir),
        "metrics": {name: summarize_values(values) for name, values in rows.items()},
        "overall_score": (
            {
                "correct": overall_correct,
                "total": overall_total,
                "score": overall_correct / overall_total,
                "components": {
                    name: {
                        **value,
                        "score": value["correct"] / value["total"],
                    }
                    for name, value in aggregate_components.items()
                },
                "passes": per_pass_overall,
            }
            if overall_total
            else None
        ),
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
