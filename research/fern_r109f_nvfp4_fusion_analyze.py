#!/usr/bin/env python3
"""Analyse the decomposed A/B/C probe of the lagunaNormAffineQKV fusion.

The advisor's single DARKBLOOM_NATIVE_AFFINE_NVFP4=0 toggle bundles two
mechanisms: it flips the QKV and o_proj weight bank from NVFP4-g16-4bit to
affine-g32-INT8, and only as a side effect does it make the dead
lagunaNormAffineQKV fusion reachable. A B-minus-A contrast therefore cannot
attribute anything. The third arm C holds the bank at INT8 and switches the
fusion back off, so:

    C - A  prices the NVFP4 -> INT8 bank flip
    B - C  isolates the fusion at matched quantization   <-- the real question
    B - A  reproduces the bundled figure

Arm W is a warmup slot and is always excluded.

Usage: fern_r109f_nvfp4_fusion_analyze.py [TAG ...]
"""

import glob
import json
import os
import statistics
import sys

ART = os.path.join("research", "artifacts", "fern-r109f", "nvfp4-fusion")
NS_DECODE_REF = 0.013890
NS_PREFILL_REF = 0.0003845
DECODE_W = 0.75
PREFILL_W = 0.25


def normalized_score(decode, prefill):
    return (NS_DECODE_REF / decode) ** DECODE_W * (NS_PREFILL_REF / prefill) ** PREFILL_W


def load(tag):
    arms = {}
    for path in sorted(glob.glob(os.path.join(ART, f"{tag}-*-*.json"))):
        arm = os.path.basename(path).rsplit("-", 1)[1].split(".")[0]
        if arm == "W":
            continue
        with open(path) as fh:
            payload = json.load(fh)
        m = payload.get("metrics", payload)
        decode = m["decode_seconds_per_token"]
        prefill = m["prefill_seconds_per_token"]
        arms.setdefault(arm, []).append(
            {
                "slot": os.path.basename(path).split("-")[1],
                "decode": decode,
                "prefill": prefill,
                "ns": normalized_score(decode, prefill),
                "correct": m.get("passed_correctness"),
                "steps": m.get("checked_steps"),
                "golden": m.get("golden_hash"),
            }
        )
    return arms


def stats(values):
    n = len(values)
    mean = statistics.fmean(values)
    sd = statistics.stdev(values) if n > 1 else 0.0
    sem = sd / n**0.5 if n > 1 else 0.0
    return {
        "n": n,
        "mean": mean,
        "median": statistics.median(values),
        "sd": sd,
        "sem": sem,
        "cv": 100.0 * sd / mean if mean else 0.0,
    }


def contrast(num, den, axis):
    """Percentage change of num relative to den, with a propagated 2-sigma band.

    Sign convention: positive means num is the larger number. For seconds/token
    that is a slowdown; for ns it is an improvement.
    """
    a, b = stats(num), stats(den)
    delta = 100.0 * (a["mean"] / b["mean"] - 1.0)
    rel = 0.0
    if a["mean"] and b["mean"]:
        rel = ((2 * a["sem"] / a["mean"]) ** 2 + (2 * b["sem"] / b["mean"]) ** 2) ** 0.5
    band = 100.0 * rel
    return axis, delta, band, a["n"], b["n"]


def report(tag):
    arms = load(tag)
    if not arms:
        print(f"[{tag}] no artifacts under {ART}")
        return
    print(f"=== {tag} ===")
    for arm in sorted(arms):
        reps = arms[arm]
        print(f"  arm {arm}  (n={len(reps)})")
        for r in reps:
            print(
                f"    slot{r['slot']}  decode={r['decode']:.9f}  "
                f"prefill={r['prefill']:.9f}  ns={r['ns']:.6f}  "
                f"correct={r['correct']}  steps={r['steps']}"
            )
        for axis in ("decode", "prefill", "ns"):
            s = stats([r[axis] for r in reps])
            print(
                f"    {axis:<8} mean={s['mean']:.9f} median={s['median']:.9f} "
                f"cv={s['cv']:.3f}%"
            )
        goldens = {r["golden"] for r in reps}
        correct = {r["correct"] for r in reps}
        print(f"    correctness: passed={correct} golden_hashes={len(goldens)} distinct")

    pairs = [
        ("C - A", "NVFP4 -> INT8 bank flip (confound)", "C", "A"),
        ("B - C", "fusion at matched quantization (the real question)", "B", "C"),
        ("B - A", "bundled toggle, as the advisor proposed it", "B", "A"),
    ]
    print("  contrasts (positive seconds = slower; positive ns = better):")
    for label, why, hi, lo in pairs:
        if hi not in arms or lo not in arms:
            print(f"    {label:<7} unavailable")
            continue
        print(f"    {label:<7} {why}")
        for axis in ("decode", "prefill", "ns"):
            _, delta, band, na, nb = contrast(
                [r[axis] for r in arms[hi]], [r[axis] for r in arms[lo]], axis
            )
            print(
                f"      {axis:<8} {delta:+.3f}%  +/- {band:.3f}% (2sigma)  "
                f"n={na}/{nb}"
            )


def main():
    tags = sys.argv[1:] or ["pilot", "main"]
    for tag in tags:
        report(tag)


if __name__ == "__main__":
    main()
