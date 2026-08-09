#!/usr/bin/env python3
"""Advisor round-103, part 3: is receipt cadence limited by the platform or by us?

Reads the raw receipt dump written by advisor_r103_candidate_noise.py and
measures inter-arrival gaps, per-hour platform throughput, and hour-of-day
coverage, for us and for the two highest-cadence competitors.

usage: advisor_r103_cadence_gaps.py <raw.json>
"""

import datetime as dt
import json
import statistics
import sys
from collections import Counter


def parse(ts):
    return dt.datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ")


def gaps_for(recs, solver, day=None):
    sub = [r for r in recs if r["solver"] == solver and (day is None or r["ts"][:10] == day)]
    sub.sort(key=lambda r: r["ts"])
    g = []
    for a, b in zip(sub, sub[1:]):
        g.append((parse(b["ts"]) - parse(a["ts"])).total_seconds() / 60.0)
    return sub, g


def main():
    recs = json.load(open(sys.argv[1]))

    print("=== platform-wide receipts per hour (all solvers), 2026-08-07 onward")
    c = Counter(r["ts"][:13] for r in recs if r["ts"] >= "2026-08-07")
    vals = [c[h] for h in sorted(c)]
    print(f"    hours with >=1 receipt: {len(vals)}   mean/hr {statistics.mean(vals):.2f}"
          f"   median/hr {statistics.median(vals):.1f}   max/hr {max(vals)}")

    print("\n=== hour-of-day coverage (how many distinct UTC hours a solver ever used)")
    for s in ("morganmcg1", "a-github-name", "lBroth", "metaspartan", "MyatKaung",
              "fyrsta7", "yudduy"):
        sub = [r for r in recs if r["solver"] == s]
        if not sub:
            continue
        hours = sorted({int(r["ts"][11:13]) for r in sub})
        print(f"    {s:16s} n={len(sub):4d}  distinct UTC hours used: {len(hours):2d}/24  {hours}")

    print("\n=== inter-receipt gaps, minutes")
    for s, day in (("morganmcg1", "2026-08-09"), ("morganmcg1", None),
                   ("a-github-name", "2026-08-03"), ("a-github-name", "2026-08-04"),
                   ("a-github-name", None), ("lBroth", None)):
        sub, g = gaps_for(recs, s, day)
        if len(g) < 2:
            continue
        g_same_day = [x for x in g if x < 240]
        span = (parse(sub[-1]["ts"]) - parse(sub[0]["ts"])).total_seconds() / 3600
        print(f"    {s:16s} {day or 'ALL':10s} n={len(sub):4d} span={span:6.1f}h"
              f"  median gap={statistics.median(g):6.1f}  min={min(g):5.1f}"
              f"  median(<4h gaps)={statistics.median(g_same_day) if g_same_day else float('nan'):6.1f}"
              f"  p10={sorted(g)[len(g)//10]:5.1f}")

    print("\n=== fastest observed back-to-back receipts by ANY single solver")
    bysolver = {}
    for r in recs:
        bysolver.setdefault(r["solver"], []).append(r)
    fastest = []
    for s, v in bysolver.items():
        v.sort(key=lambda r: r["ts"])
        for a, b in zip(v, v[1:]):
            d = (parse(b["ts"]) - parse(a["ts"])).total_seconds() / 60.0
            fastest.append((d, s, a["ts"], b["ts"]))
    fastest.sort()
    for d, s, t1, t2 in fastest[:12]:
        print(f"    {d:6.1f} min  {s:16s} {t1} -> {t2}")

    print("\n=== our idle time: UTC hours in the last 3 days with zero morganmcg1 receipts")
    ours = {r["ts"][:13] for r in recs if r["solver"] == "morganmcg1"}
    for day in ("2026-08-07", "2026-08-08", "2026-08-09"):
        used = sorted(int(h[11:13]) for h in ours if h[:10] == day)
        print(f"    {day}: {len(used):2d}/24 hours used  {used}")


if __name__ == "__main__":
    main()
