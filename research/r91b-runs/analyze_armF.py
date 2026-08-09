"""Read the Arm R and Arm F receipts and report the four fields plus the
baseline-normalised R-F contrast.

The published score is a paired ratio against a per-session pinned baseline, so
a raw score difference confounds the code delta with the baseline draw. This
re-scores both arms at a common baseline to separate them.

usage: analyze_armF.py <receipt-armR.json> <receipt-armF.json> [baseline-drift.json]
"""

import json
import statistics
import sys


def load(path):
    d = json.load(open(path))
    return d.get("submission", d)


def score(dec_speedup, pre_speedup):
    return dec_speedup**0.75 * pre_speedup**0.25


def fields(sub, label):
    m = sub.get("officialMetrics") or {}
    print(f"===== {label} =====")
    print(f"  id                {sub.get('id')}")
    print(f"  commit            {sub.get('commit')}")
    print(f"  submittedAt       {sub.get('createdAt')}")
    print(f"  updatedAt         {sub.get('updatedAt')}")
    print("  --- field 1: correctness / gates ---")
    for k in (
        "passed_correctness",
        "max_abs_diff",
        "checked_steps",
        "case_count",
        "gpqa_ttft_passed",
        "semantic_gpqa_passed",
        "partial_result",
    ):
        print(f"    {k:24} {m.get(k)!r}")
    print(f"    {'rejectionReason':24} {sub.get('rejectionReason')!r}")
    print("  --- field 2: error ---")
    print(f"    {'error':24} {sub.get('error')!r}")
    print("  --- field 3: floors ---")
    for k in (
        "decode_speedup",
        "passed_decode_speedup_floor",
        "prefill_speedup",
        "passed_prefill_speedup_floor",
        "decode_seconds_per_token",
        "prefill_seconds_per_token",
        "baseline_decode_seconds_per_token",
        "baseline_prefill_seconds_per_token",
    ):
        print(f"    {k:36} {m.get(k)!r}")
    print("  --- field 4: ranking ---")
    print(f"    {'status':24} {sub.get('status')!r}")
    print(f"    {'improved':24} {sub.get('improved')!r}")
    print(f"    {'officialScore':24} {sub.get('officialScore')!r}")
    return m


BEST = 2.61650354381456


def main():
    r = load(sys.argv[1])
    f = load(sys.argv[2])
    mr = fields(r, "ARM R")
    print()
    mf = fields(f, "ARM F")
    print()

    sr, sf = r.get("officialScore"), f.get("officialScore")
    if sr is None or sf is None:
        print("one arm has no score yet; stopping")
        return

    print("===== as published (confounded by the baseline draw) =====")
    for lbl, s in (("Arm R", sr), ("Arm F", sf)):
        print(f"  {lbl}  {s:.10f}   vs best {BEST}: {s - BEST:+.10f} ({(s / BEST - 1) * 100:+.4f} %)")
    print(f"  R - F = {sr - sf:+.10f} ({(sr / sf - 1) * 100:+.4f} %)")

    print()
    print("===== baseline draws actually seen =====")
    for lbl, m in (("Arm R", mr), ("Arm F", mf)):
        print(
            f"  {lbl}  bl_dec={m['baseline_decode_seconds_per_token']:.12f} "
            f"bl_pre={m['baseline_prefill_seconds_per_token']:.12f}"
        )
    dd = mf["baseline_decode_seconds_per_token"] / mr["baseline_decode_seconds_per_token"] - 1
    dp = mf["baseline_prefill_seconds_per_token"] / mr["baseline_prefill_seconds_per_token"] - 1
    print(f"  F/R baseline decode  {dd * 100:+.4f} %")
    print(f"  F/R baseline prefill {dp * 100:+.4f} %")
    print(f"  score advantage F got purely from its draw: {(0.75 * dd + 0.25 * dp) * 100:+.4f} %")

    print()
    print("===== re-scored at a COMMON baseline (the code-only contrast) =====")
    if len(sys.argv) > 3:
        rows = json.load(open(sys.argv[3]))
        bd = statistics.fmean(x["baseline_decode_seconds_per_token"] for x in rows)
        bp = statistics.fmean(x["baseline_prefill_seconds_per_token"] for x in rows)
        src = f"population mean of n={len(rows)}"
    else:
        bd = mr["baseline_decode_seconds_per_token"]
        bp = mr["baseline_prefill_seconds_per_token"]
        src = "Arm R's own draw"
    print(f"  common baseline ({src}): bl_dec={bd:.12f} bl_pre={bp:.12f}")
    out = {}
    for lbl, m in (("Arm R", mr), ("Arm F", mf)):
        s = score(bd / m["decode_seconds_per_token"], bp / m["prefill_seconds_per_token"])
        out[lbl] = s
        print(f"  {lbl}  {s:.10f}")
    d = out["Arm R"] / out["Arm F"] - 1
    print(f"  R - F at common baseline = {out['Arm R'] - out['Arm F']:+.10f} ({d * 100:+.4f} %)")
    print("  (M4 preflight predicted R - F = +0.360 %; assignment M2 predicted +0.50 %)")

    print()
    print("===== candidate timings, the unconfounded quantity =====")
    for axis in ("decode_seconds_per_token", "prefill_seconds_per_token"):
        vr, vf = mr[axis], mf[axis]
        print(f"  {axis:30} R={vr:.15f} F={vf:.15f}  R vs F {(vf / vr - 1) * 100:+.4f} % (positive = R faster)")


main()
