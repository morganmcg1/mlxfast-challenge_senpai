#!/usr/bin/env python3
"""Render the cross-block per-kernel delta table (advisor deliverable: every
kernel >= 1% of decode busy time, all arms side by side with the end-to-end net)."""
import json

RUNS = "research/r87a-runs"


def per_kernel(block, arm):
    with open(f"{RUNS}/{block}.json") as fh:
        return {r["kernel"]: r for r in json.load(fh)["deltas"][arm]["per_kernel"]}


def totals(block, arm):
    with open(f"{RUNS}/{block}.json") as fh:
        d = json.load(fh)["deltas"][arm]
    return d


lad = {a: per_kernel("ladder", a) for a in ("PF1", "PF2", "PF3")}
ctl = {a: per_kernel("control", a) for a in ("B2", "B4")}
cei = per_kernel("ceiling", "E0")

cell = lambda r: f"{r['delta_us']:+.2f} ± {r['ci95_us']:.2f}" if r else "—"

rows = sorted(cei.values(), key=lambda r: -r["share_pct"])
keep = [r for r in rows if r["share_pct"] >= 1.0]

print("| kernel | share | T | PF1 steady | PF2 preamble | PF3 both | B2 | B4 | E0 ceiling |")
print("| --- | ---: | :-: | ---: | ---: | ---: | ---: | ---: | ---: |")
for r in keep:
    k = r["kernel"]
    print(
        f"| `{k}` | {r['share_pct']:.2f}% | {'**T**' if r['touched'] else ''} "
        f"| {cell(lad['PF1'].get(k))} | {cell(lad['PF2'].get(k))} | {cell(lad['PF3'].get(k))} "
        f"| {cell(ctl['B2'].get(k))} | {cell(ctl['B4'].get(k))} | {cell(r)} |"
    )

covered = sum(r["share_pct"] for r in keep)
print()
print(f"rows >=1%: {len(keep)} of {len(rows)} kernels; covering {covered:.2f}% of decode busy time")
print()
for label, block, arm in (
    ("PF1", "ladder", "PF1"), ("PF2", "ladder", "PF2"), ("PF3", "ladder", "PF3"),
    ("B2", "control", "B2"), ("B4", "control", "B4"), ("E0", "ceiling", "E0"),
):
    t = totals(block, arm)
    bs, wl = t["totals"]["busy_sum_us"], t["totals"]["wall_us"]
    print(
        f"| {label} | {t['subtotal_touched_us']:+.2f} | {t['subtotal_untouched_us']:+.2f} "
        f"| {bs['delta_us']:+.2f} ± {bs['ci95_us']:.2f} | {wl['delta_us']:+.2f} ± {wl['ci95_us']:.2f} |"
    )
