#!/usr/bin/env python3
"""Aggregate the PR35 pure-configuration screen (research/frieren_pr35_pure.sh).

Each pass contributes the median of its per-step milliseconds. The screen runs
ON/OFF/OFF/ON per round, so the round contrast (mean OFF - mean ON) cancels a
monotone host drift; the pooled contrast ignores order.

  python3 research/frieren_pr35_pure_stats.py [/tmp/pr35_pure_%s.txt]
"""
import statistics
import sys

TEMPLATE = sys.argv[1] if len(sys.argv) > 1 else "/tmp/pr35_pure_%s.txt"
ROUNDS = (1, 2, 3)
ARMS = ("on_r", "off_r", "off_s", "on_s")


def median(name: str) -> float:
    with open(TEMPLATE % name) as fh:
        return statistics.median(float(line) for line in fh if line.strip())


passes = {f"{arm}{r}": median(f"{arm}{r}") for r in ROUNDS for arm in ARMS}
for name, value in passes.items():
    print(f"{name:8s} median {value:.4f} ms")

on = [passes[f"{a}{r}"] for r in ROUNDS for a in ("on_r", "on_s")]
off = [passes[f"{a}{r}"] for r in ROUNDS for a in ("off_r", "off_s")]
contrasts = [
    (passes[f"off_r{r}"] + passes[f"off_s{r}"]) / 2
    - (passes[f"on_r{r}"] + passes[f"on_s{r}"]) / 2
    for r in ROUNDS
]


def se(values: list[float]) -> float:
    return statistics.stdev(values) / len(values) ** 0.5


print(f"\nON  mean {statistics.mean(on):.4f} ms  stdev {statistics.stdev(on)*1e3:.1f} us")
print(f"OFF mean {statistics.mean(off):.4f} ms  stdev {statistics.stdev(off)*1e3:.1f} us")
pooled = statistics.mean(off) - statistics.mean(on)
pooled_se = (se(on) ** 2 + se(off) ** 2) ** 0.5
print(f"pooled  OFF-ON {pooled*1e3:+.1f} us  se {pooled_se*1e3:.1f} us")
print(
    f"round   OFF-ON {statistics.mean(contrasts)*1e3:+.1f} us  se {se(contrasts)*1e3:.1f} us"
    f"  per round {[round(c*1e3, 1) for c in contrasts]}"
)
print(f"relative {pooled / statistics.mean(off) * 100:+.3f}% of the OFF step")
