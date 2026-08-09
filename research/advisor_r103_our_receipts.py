#!/usr/bin/env python3
"""Round-103: our own receipt cadence vs the leader's, and the two-lever model.

Input: /tmp/r103-receipts.json produced by advisor_r103_receipt_cadence.py
(records: id, solver, ts, cs, score, L, status).
"""
import json
import math
import sys
from collections import Counter

RECORD = 2.61650354381456
US = "morganmcg1"
LEADER = "a-github-name"

recs = json.loads(open(sys.argv[1] if len(sys.argv) > 1 else "/tmp/r103-receipts.json").read())
Ls = sorted(r["L"] for r in recs)
n = len(Ls)


def p_record(cs):
    need = RECORD / cs
    return sum(1 for x in Ls if x >= need) / n


for who in (US, LEADER):
    sub = sorted((r for r in recs if r["solver"] == who), key=lambda r: r["ts"] or "")
    print(f"\n===== {who}: n={len(sub)}")
    byday = Counter((r["ts"] or "")[:10] for r in sub)
    best = 0.0
    print(f"  {'day':12s} {'n':>3s} {'best_cs_that_day':>16s} {'running_best':>12s} {'P/draw@runbest':>14s}")
    for d in sorted(byday):
        dd = [r for r in sub if (r["ts"] or "")[:10] == d]
        bd = max(r["cs"] for r in dd)
        best = max(best, bd)
        print(f"  {d:12s} {len(dd):3d} {bd:16.6f} {best:12.6f} {p_record(best)*100:13.3f}%")
    print(f"  overall best cs = {max(r['cs'] for r in sub):.6f}")
    print(f"  overall best score = {max(r['score'] for r in sub):.6f}")
    print(f"  best L drawn = {max(r['L'] for r in sub):.6f} ({(max(r['L'] for r in sub)-1)*100:+.3f}%)")
    # realised cumulative record probability given each receipt's own cs
    q = 1.0
    for r in sub:
        q *= 1 - p_record(r["cs"])
    print(f"  realised cumulative P(record) over this solver's actual draws = {(1-q)*100:.2f}%")

print("\n\n===== Two-lever table: P(at least one record) = 1-(1-p(cs))^N")
cslist = [2.575633, 2.582286, 2.585060, 2.588362, 2.590559, 2.591868, 2.60, 2.61]
print(f"  {'cs':>10s} {'p/draw':>8s} " + " ".join(f"{f'N={N}':>8s}" for N in (1, 5, 10, 20, 40, 80, 160)))
for cs in cslist:
    p = p_record(cs)
    row = " ".join(f"{(1-(1-p)**N)*100:7.2f}%" for N in (1, 5, 10, 20, 40, 80, 160))
    print(f"  {cs:10.6f} {p*100:7.3f}% {row}")

print("\n===== marginal value of one extra receipt vs +0.1% cs, at each level")
for cs in cslist:
    p0 = p_record(cs)
    p1 = p_record(cs * 1.001)
    print(f"  cs={cs:.6f}: p={p0*100:6.3f}%  +0.1%cs -> {p1*100:6.3f}%  (x{p1/max(p0,1e-9):.2f})")

# how many of the corpus's top-cs receipts belong to whom
top = sorted(recs, key=lambda r: -r["cs"])[:25]
print("\n===== corpus top-25 by cs")
for i, r in enumerate(top, 1):
    print(f"  {i:2d} {r['solver'][:22]:22s} cs={r['cs']:.6f} score={r['score']:.6f} L={r['L']:.6f} {r['ts'][:10]}")
