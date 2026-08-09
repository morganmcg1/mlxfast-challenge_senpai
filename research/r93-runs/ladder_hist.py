#!/usr/bin/env python3
"""Recover the historical M5 empty-dispatch ladder (n=0/100/400, EMPTY_TG=8)
from the public receipt corpus and fit its marginal per-dispatch cost."""
import json
import sys

CORPUS = sys.argv[1] if len(sys.argv) > 1 else (
    "research/r93-runs/receipts-20260809T024726Z.json")
LADDER = {"c3ce66ec": 0, "57306132": 100, "0411779d": 400}

R = json.load(open(CORPUS))
by = {r["id"]: r for r in R}
rows = sorted((n, by[i], i) for i, n in LADDER.items())

for n, r, i in rows:
    print(
        f"n={n:4d} id={i} ts={r['ts']} commit={r['commit']} solver={r['solver']} "
        f"cand_dec={r['cand_dec']*1e6:9.2f}us cand_pre={r['cand_pre']*1e6:8.3f}us "
        f"bl_dec={r['bl_dec']*1e6:9.2f} bl_pre={r['bl_pre']*1e6:8.3f} "
        f"dec_su={r['dec_su']:.4f} pre_su={r['pre_su']:.4f}")

b0 = rows[0][1]
base = b0["cand_dec"] * 1e6
print()
for n, r, _ in rows[1:]:
    d = r["cand_dec"] * 1e6 - base
    dp = r["cand_dec"] * (b0["bl_dec"] / r["bl_dec"]) * 1e6 - base
    print(f"n=0->{n:4d}: raw {d:8.2f}us -> {d/n:.4f} us/disp | "
          f"bl-normalised {dp:8.2f}us -> {dp/n:.4f} us/disp")

r100 = rows[1][1]
r400 = rows[2][1]
d = (r400["cand_dec"] - r100["cand_dec"]) * 1e6
print(f"seg 100->400: {d:.2f}us over 300 -> {d/300:.4f} us/disp")

xs = [n for n, _, _ in rows]
ys = [r["cand_dec"] * 1e6 for _, r, _ in rows]
m = len(xs)
mx = sum(xs) / m
my = sum(ys) / m
sl = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)
print(f"OLS(3pt, raw): slope={sl:.4f} us/disp intercept={my - sl*mx:.2f} us")

pre = [r["cand_pre"] * 1e6 for _, r, _ in rows]
print(f"prefill control: {pre} us/token "
      f"(spread {100*(max(pre)-min(pre))/min(pre):.3f} %)")
