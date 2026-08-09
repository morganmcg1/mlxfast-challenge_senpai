#!/usr/bin/env python3
"""Endgame arithmetic once 'accepted' is known to mean 'new GLOBAL record'.

The ladder is winner-take-all per receipt: the only event worth anything is
score > current global max.  This prices the remaining game.
"""
import json
import math
import os
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ART = os.path.join(HERE, "artifacts", "advisor-r103")
CORPUS = json.load(open(os.path.join(ART, "receipt-corpus-frozen.json")))
rows = sorted((r for r in CORPUS if r.get("score")), key=lambda r: r["ts"])

# --- tail of the global-best ladder ---------------------------------------
ladder, g = [], -1e9
for r in rows:
    if r["score"] > g:
        g = r["score"]
        ladder.append(r)
print(f"global-best ladder has {len(ladder)} rungs; last 12:")
for r in ladder[-12:]:
    print(f"  {r['ts']}  score={r['score']:.6f}  cs={r['cs']:.6f}  "
          f"L={r['L']:.6f}  {r['solver']:16s} {r.get('status')}")

rec = ladder[-1]
after = [r for r in rows if r["ts"] > rec["ts"]]
print(f"\nrecord set {rec['ts']} by {rec['solver']} at {rec['score']:.6f}")
print(f"receipts submitted by ANYONE since then: {len(after)}  "
      f"(none beat it)")
bysolv = defaultdict(int)
for r in after:
    bysolv[r["solver"]] += 1
print("  by solver: " + ", ".join(f"{k}={v}" for k, v in
                                  sorted(bysolv.items(), key=lambda kv: -kv[1])))
best_after = max(after, key=lambda r: r["score"])
print(f"  best score since the record: {best_after['score']:.6f} "
      f"({best_after['solver']}, cs={best_after['cs']:.6f}, "
      f"L={best_after['L']:.6f})")

# --- gap decomposition, us vs the record ----------------------------------
ours = [r for r in rows if r["solver"] == "morganmcg1"]
our_best = max(ours, key=lambda r: r["score"])
print(f"\nour best-ever score {our_best['score']:.6f} at {our_best['ts']} "
      f"(cs={our_best['cs']:.6f}, L={our_best['L']:.6f})")
print(f"  score gap to record : {100*math.log(rec['score']/our_best['score']):+.3f}%")
print(f"  cs   gap to record  : {100*math.log(rec['cs']/our_best['cs']):+.3f}% "
      f"(negative = we are AHEAD on merit)")
print(f"  L    gap to record  : {100*math.log(rec['L']/our_best['L']):+.3f}%")

HON = 2.583111   # honest mean cs of our best verified tree (r93-null quintuplet)
print(f"\nour honest best tree cs {HON:.6f}; record cs {rec['cs']:.6f} "
      f"=> we lead on cs by {100*math.log(HON/rec['cs']):+.3f}%")
Ls = sorted(r["L"] for r in rows)
medL = Ls[len(Ls) // 2]
needL = rec["score"] / HON
pct = 100.0 * sum(1 for x in Ls if x >= needL) / len(Ls)
print(f"  to take the record on our honest tree we need L >= {needL:.6f}; "
      f"{pct:.2f}% of all corpus draws reach that "
      f"({sum(1 for x in Ls if x >= needL)} of {len(Ls)})")

# --- how much cs work makes the record routine ----------------------------
SD = 0.004595            # measured within-tree sd(ln score), dof=14
US_PER_PCT = 65.67       # us/step per 1% of cs


def p_rec(mu_cs):
    z = (math.log(rec["score"]) - math.log(mu_cs * medL)) / SD
    return 0.5 * math.erfc(z / math.sqrt(2))


print("\ncs improvement needed, priced in T (us/step) and in receipts:")
print("  d(cs)%   dT us/step   p/record per receipt   receipts for 50%   for 90%")
for d in (0.0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0):
    mu = HON * math.exp(d / 100.0)
    p = p_rec(mu)
    n50 = math.log(0.5) / math.log(1 - p) if 0 < p < 1 else float("inf")
    n90 = math.log(0.1) / math.log(1 - p) if 0 < p < 1 else float("inf")
    print(f"  {d:5.2f}   {d*US_PER_PCT:9.1f}   {100*p:16.3f}%   "
          f"{n50:14.1f}   {n90:7.1f}")

print("\nbudgeted comparison at a realistic receipt budget:")
for budget in (6, 12, 24, 48):
    print(f"  {budget:3d} receipts:", end="")
    for d in (0.0, 0.5, 1.0, 1.5):
        p = p_rec(HON * math.exp(d / 100.0))
        print(f"   d={d:.1f}% -> P(record)={100*(1-(1-p)**budget):6.2f}%", end="")
    print()

# --- is L a lottery or a solver property? ---------------------------------
print("\nis L a lottery or a solver property?  mean/sd of ln L by solver "
      "(solvers with >=20 receipts):")
by = defaultdict(list)
for r in rows:
    by[r["solver"]].append(math.log(r["L"]))
gm = sum(x for v in by.values() for x in v) / sum(len(v) for v in by.values())
for sv, v in sorted(by.items(), key=lambda kv: -len(kv[1])):
    if len(v) < 20:
        continue
    m = sum(v) / len(v)
    s = math.sqrt(sum((x - m) ** 2 for x in v) / (len(v) - 1))
    se = s / math.sqrt(len(v))
    print(f"  {sv:20s} n={len(v):4d}  mean ln L = {100*m:+7.4f}%  "
          f"sd={100*s:.4f}%  se={100*se:.4f}%  z vs grand mean "
          f"{(m-gm)/se:+6.2f}")
print(f"  grand mean ln L = {100*gm:+.4f}%")
