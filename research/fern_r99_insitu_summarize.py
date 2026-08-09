#!/usr/bin/env python3
"""Summarize the ABBA in-situ A/B leg for the r99-e rung.

Reports the drift-cancelling ABBA contrast alongside the same-arm control
spread, so a candidate delta smaller than the control spread is visible as
such rather than being reported as an effect.
"""
import json
import re
import sys
from pathlib import Path

out = Path(sys.argv[1] if len(sys.argv) > 1 else "research/artifacts/fern-r99")
runs = []
for p in sorted(out.glob("insitu_*.json")):
    m = re.match(r"insitu_(base|cand)_(\d+)\.json$", p.name)
    if not m:
        continue
    d = json.load(open(p))["metrics"]
    runs.append(
        dict(
            arm=m.group(1),
            idx=int(m.group(2)),
            decode=d["decode_seconds_per_token"],
            prefill=d["prefill_seconds_per_token"],
            ok=d["passed_correctness"],
            diff=d["max_abs_diff"],
            ts=d["timestamp"],
        )
    )
runs.sort(key=lambda r: r["idx"])
if not runs:
    sys.exit("no insitu_*.json runs found")

print(f"{'idx':>3} {'arm':>5} {'decode us/tok':>14} {'prefill us/tok':>15} {'ok':>5} {'diff':>5}  ts")
for r in runs:
    print(
        f"{r['idx']:>3} {r['arm']:>5} {r['decode']*1e6:14.1f} {r['prefill']*1e6:15.1f} "
        f"{str(r['ok']):>5} {str(r['diff']):>5}  {r['ts']}"
    )

bad = [r for r in runs if not r["ok"] or r["diff"] != 0]
if bad:
    print(f"\nCORRECTNESS FAILURES: {[r['idx'] for r in bad]}")


def abba_blocks(rs):
    """Yield (base_mean, cand_mean) for each complete ABBA block."""
    for i in range(0, len(rs) - 3, 4):
        blk = rs[i : i + 4]
        if [b["arm"] for b in blk] != ["base", "cand", "cand", "base"]:
            continue
        yield blk


for metric in ("decode", "prefill"):
    print(f"\n--- {metric} ---")
    deltas = []
    for blk in abba_blocks(runs):
        b = (blk[0][metric] + blk[3][metric]) / 2
        c = (blk[1][metric] + blk[2][metric]) / 2
        deltas.append((c - b) * 1e6)
        print(
            f"  ABBA block {blk[0]['idx']}-{blk[3]['idx']}: "
            f"base={b*1e6:.1f} cand={c*1e6:.1f} delta={(c-b)*1e6:+.1f} us/tok "
            f"({(c-b)/b*100:+.3f} %)"
        )
    if deltas:
        mean = sum(deltas) / len(deltas)
        spread = max(deltas) - min(deltas)
        print(f"  ABBA delta mean = {mean:+.1f} us/tok over {len(deltas)} block(s); spread = {spread:.1f}")

    for arm in ("base", "cand"):
        vals = [r[metric] * 1e6 for r in runs if r["arm"] == arm]
        if len(vals) > 1:
            print(
                f"  same-arm control spread [{arm}] = {max(vals)-min(vals):.1f} us/tok "
                f"over {len(vals)} runs (min {min(vals):.1f}, max {max(vals):.1f})"
            )
