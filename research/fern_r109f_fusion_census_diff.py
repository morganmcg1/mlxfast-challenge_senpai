#!/usr/bin/env python3
"""Diff the DARKBLOOM_TRACE_FUSION dispatch-site censuses across probe arms."""
from __future__ import annotations

import pathlib
import sys

OUT_DIR = pathlib.Path("research/artifacts/fern-r109f/census")


def load(arm: str) -> set[str]:
    path = OUT_DIR / f"sites-{arm}.txt"
    if not path.exists():
        return set()
    return {line.strip() for line in path.read_text().splitlines() if line.strip()}


def main() -> int:
    arms = sys.argv[1:] or ["A", "B", "C"]
    census = {arm: load(arm) for arm in arms}
    missing = [a for a, s in census.items() if not s]
    if missing:
        print(f"missing or empty census for arms: {', '.join(missing)}")
    every = sorted(set().union(*census.values())) if census else []
    if not every:
        return 1

    width = max(len(s) for s in every)
    header = "  ".join(f"{a:>3}" for a in arms)
    print(f"{'dispatch site':<{width}}  {header}")
    print("-" * (width + 2 + len(header)))
    for site in every:
        marks = "  ".join(f"{'X' if site in census[a] else '.':>3}" for a in arms)
        print(f"{site:<{width}}  {marks}")

    for i in range(len(arms) - 1):
        left, right = arms[i], arms[i + 1]
        gone = sorted(census[left] - census[right])
        new = sorted(census[right] - census[left])
        print(f"\n=== {left} -> {right} ===")
        for site in gone:
            print(f"  VANISHED  {site}")
        for site in new:
            print(f"  APPEARED  {site}")
        if not gone and not new:
            print("  identical dispatch-site census")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
