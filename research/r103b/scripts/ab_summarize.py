#!/usr/bin/env python3
"""Summarize the paired DARKBLOOM_ROUTER_WEIGHT_PREFETCH A/B legs.

Reads /tmp/r103b/ab/summary.tsv (tag rc pf decode_spt prefill_spt correct),
discards leg 1 as warm-up, and reports per-arm order statistics plus the
paired (pf1 - pf0) contrast in us/token.
"""
import re
import statistics
import sys

path = sys.argv[1] if len(sys.argv) > 1 else "/tmp/r103b/ab/summary.tsv"

legs = []
for line in open(path):
    line = line.strip()
    if not line:
        continue
    fields = dict(re.findall(r"(\w+)=([^\s]+)", line))
    tag = line.split()[0]
    n = int(re.match(r"leg(\d+)", tag).group(1))
    legs.append(
        {
            "leg": n,
            "pf": int(fields["pf"]),
            "rc": int(fields["rc"]),
            "decode": float(fields["decode_spt"]),
            "prefill": float(fields["prefill_spt"]),
            "correct": fields["correct"] == "True",
        }
    )

legs.sort(key=lambda r: r["leg"])
warmup = [r for r in legs if r["leg"] == 1]
body = [r for r in legs if r["leg"] > 1 and r["rc"] == 0 and r["correct"]]
bad = [r for r in legs if r["leg"] > 1 and not (r["rc"] == 0 and r["correct"])]

print(f"legs parsed      : {len(legs)}")
print(f"warm-up discarded: {[r['leg'] for r in warmup]}")
print(f"usable legs      : {len(body)}")
if bad:
    print(f"EXCLUDED (rc!=0 or incorrect): {[(r['leg'], r['rc'], r['correct']) for r in bad]}")
print()

for metric in ("decode", "prefill"):
    print(f"== {metric}_seconds_per_token ==")
    arms = {}
    for pf in (1, 0):
        vals = [r[metric] * 1e6 for r in body if r["pf"] == pf]
        arms[pf] = vals
        if not vals:
            print(f"  pf={pf}: no legs")
            continue
        sd = statistics.stdev(vals) if len(vals) > 1 else float("nan")
        print(
            f"  pf={pf}  K={len(vals):2d}  mean={statistics.mean(vals):10.1f} us"
            f"  median={statistics.median(vals):10.1f}  sd={sd:7.1f}"
            f"  min={min(vals):10.1f}  max={max(vals):10.1f}"
        )
    if arms.get(1) and arms.get(0):
        d = statistics.mean(arms[1]) - statistics.mean(arms[0])
        pooled = statistics.mean(arms[0])
        print(f"  unpaired mean delta (pf1 - pf0) = {d:+.1f} us  ({100 * d / pooled:+.3f} %)")
        # paired: leg 2k vs leg 2k+1 consecutive (pf1, pf0) couples
        by_leg = {r["leg"]: r for r in body}
        pairs = []
        for r in body:
            if r["pf"] != 1:
                continue
            mate = by_leg.get(r["leg"] + 1)
            if mate is not None and mate["pf"] == 0:
                pairs.append((r[metric] * 1e6, mate[metric] * 1e6))
        if pairs:
            diffs = [a - b for a, b in pairs]
            sd = statistics.stdev(diffs) if len(diffs) > 1 else float("nan")
            sem = sd / len(diffs) ** 0.5 if len(diffs) > 1 else float("nan")
            print(
                f"  paired  n={len(diffs):2d}  mean diff={statistics.mean(diffs):+.1f} us"
                f"  sd={sd:.1f}  sem={sem:.1f}"
                f"  ({100 * statistics.mean(diffs) / pooled:+.3f} %)"
            )
            print(f"  per-pair diffs: {[round(x, 1) for x in diffs]}")
    print()

print("all legs:")
for r in legs:
    print(
        f"  leg{r['leg']:02d} pf={r['pf']} rc={r['rc']} correct={r['correct']} "
        f"decode={r['decode'] * 1e6:.1f}us prefill={r['prefill'] * 1e6:.1f}us"
    )
