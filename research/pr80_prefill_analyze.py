#!/usr/bin/env python3
"""Aggregate the PR #80 counterbalanced prefill ABBA log into an arm verdict."""
import re
import sys
from statistics import mean, pstdev

LINE = re.compile(
    r"\[(?P<label>p\d\d-[A-Za-z]+)\].*?"
    r"prefill_ms_mean=(?P<mean>[\d.]+) "
    r"prefill_ms_sd=(?P<sd>[\d.]+) "
    r"prefill_ms_median=(?P<med>[\d.]+) "
    r"prefill_ms_min=(?P<min>[\d.]+)"
)

path = sys.argv[1]
visits = []
for raw in open(path, encoding="utf-8", errors="replace"):
    m = LINE.search(raw)
    if not m:
        continue
    pos, arm = m.group("label").split("-", 1)
    visits.append(
        dict(pos=pos, arm=arm, mean=float(m.group("mean")),
             sd=float(m.group("sd")), med=float(m.group("med")),
             mn=float(m.group("min")))
    )

print(f"{'pos':>4} {'arm':>4} {'mean_ms':>9} {'sd_ms':>7} {'median_ms':>10} {'min_ms':>9}")
for v in visits:
    print(f"{v['pos']:>4} {v['arm']:>4} {v['mean']:9.3f} {v['sd']:7.3f} "
          f"{v['med']:10.3f} {v['mn']:9.3f}")

scored = [v for v in visits if v["pos"] != "p00"]
arms = {}
for v in scored:
    arms.setdefault(v["arm"], []).append(v)

print()
for arm in sorted(arms):
    vs = arms[arm]
    ms = [v["mean"] for v in vs]
    meds = [v["med"] for v in vs]
    poss = [int(v["pos"][1:]) for v in vs]
    print(f"arm {arm}: n_visits={len(vs)} position_sum={sum(poss)} "
          f"mean_of_means={mean(ms):.3f} between_visit_sd={pstdev(ms):.3f} "
          f"mean_of_medians={mean(meds):.3f} best_visit={min(ms):.3f}")

if {"D", "S"} <= set(arms):
    d = mean(v["mean"] for v in arms["D"])
    s = mean(v["mean"] for v in arms["S"])
    sd_d = pstdev([v["mean"] for v in arms["D"]])
    sd_s = pstdev([v["mean"] for v in arms["S"]])
    # between-visit spread pooled, standard error over n visits per arm
    n = min(len(arms["D"]), len(arms["S"]))
    se = ((sd_d ** 2 + sd_s ** 2) / max(n - 1, 1)) ** 0.5
    delta = d - s
    print()
    print(f"D - S = {delta:+.3f} ms  ({100.0 * delta / s:+.3f}% of S)")
    print(f"pooled between-visit SE = {se:.3f} ms   |t| = "
          f"{abs(delta) / se if se else float('inf'):.2f}")
    print(f"95% CI (t-free, 2*SE) = [{delta - 2*se:+.3f}, {delta + 2*se:+.3f}] ms")
