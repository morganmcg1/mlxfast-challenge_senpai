#!/usr/bin/env python3
"""r100-B Part 1 companion: is the paired baseline re-measured per receipt?

Our two r99d M5 receipts 33 minutes apart carry a bit-identical bl_pre
(0.000368046387) but different bl_dec. If the official wrapper reuses one
baseline measurement across a window, then two receipts inside that window
inherit the *same* lottery draw and resubmission buys nothing. This checks the
r93 corpus for exactly repeated baseline values and how they cluster in time.
"""
import json
from collections import Counter, defaultdict
from datetime import datetime

CORPUS = "research/r93-runs/receipts-latest.json"


def main():
    rows = json.load(open(CORPUS))
    for r in rows:
        r["dt"] = datetime.strptime(r["ts"], "%Y-%m-%dT%H:%M:%SZ")
    rows.sort(key=lambda r: r["dt"])
    n = len(rows)

    for key in ("bl_dec", "bl_pre"):
        vals = [r[key] for r in rows]
        c = Counter(vals)
        distinct = len(c)
        dup = sum(v - 1 for v in c.values() if v > 1)
        print(f"\n[{key}] {n} receipts -> {distinct} distinct values "
              f"({100.0*distinct/n:.1f}%); {dup} receipts share a value "
              f"already seen")
        top = c.most_common(6)
        print(f"  most repeated: " +
              ", ".join(f"{v:.12g} x{k}" for v, k in top))
        # how tightly in time do identical values cluster?
        groups = defaultdict(list)
        for r in rows:
            groups[r[key]].append(r)
        spans, sizes = [], []
        for v, g in groups.items():
            if len(g) < 2:
                continue
            sizes.append(len(g))
            spans.append((g[-1]["dt"] - g[0]["dt"]).total_seconds() / 60.0)
        if spans:
            spans_sorted = sorted(spans)
            m = spans_sorted[len(spans_sorted) // 2]
            print(f"  {len(spans)} repeated values; group size "
                  f"max {max(sizes)} mean {sum(sizes)/len(sizes):.2f}; "
                  f"time span of a repeated value: median {m:.1f} min, "
                  f"max {max(spans):.0f} min")
            within60 = sum(1 for s in spans if s <= 60)
            print(f"  {within60}/{len(spans)} repeated values "
                  f"({100.0*within60/len(spans):.0f}%) span <= 60 min")

    # consecutive-receipt behaviour: does the very next receipt reuse it?
    same_pre = sum(1 for a, b in zip(rows, rows[1:])
                   if a["bl_pre"] == b["bl_pre"])
    same_dec = sum(1 for a, b in zip(rows, rows[1:])
                   if a["bl_dec"] == b["bl_dec"])
    print(f"\n[consecutive receipts] {n-1} adjacent pairs")
    print(f"  identical bl_pre in {same_pre} ({100.0*same_pre/(n-1):.1f}%)")
    print(f"  identical bl_dec in {same_dec} ({100.0*same_dec/(n-1):.1f}%)")

    gaps = [(b["dt"] - a["dt"]).total_seconds() / 60.0
            for a, b in zip(rows, rows[1:]) if a["bl_pre"] == b["bl_pre"]]
    if gaps:
        gaps.sort()
        print(f"  gap between consecutive receipts sharing bl_pre: "
              f"median {gaps[len(gaps)//2]:.1f} min, "
              f"p90 {gaps[int(0.9*len(gaps))]:.1f} min, max {max(gaps):.0f} min")

    # effective number of independent prefill draws in the window
    dist_pre = len({r["bl_pre"] for r in rows})
    print(f"\n[effective draws] {n} receipts carry only {dist_pre} distinct "
          f"bl_pre values => {n/dist_pre:.2f} receipts per independent "
          f"prefill lottery draw")


if __name__ == "__main__":
    main()
