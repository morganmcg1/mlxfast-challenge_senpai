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

Usage:
    fern_r109f_nvfp4_fusion_analyze.py [TAG ...]
    fern_r109f_nvfp4_fusion_analyze.py [TAG ...] --wandb --run-name NAME [--tags T ...]
"""

import argparse
import glob
import json
import os
import platform
import statistics
import subprocess

ART = os.path.join("research", "artifacts", "fern-r109f", "nvfp4-fusion")
NS_DECODE_REF = 0.013890
NS_PREFILL_REF = 0.0003845
DECODE_W = 0.75
PREFILL_W = 0.25
ENTITY = "wandb-applied-ai-team"
PROJECT = "mlxfast-maple"
AXES = ("decode", "prefill", "ns")

ARM_DESCRIPTION = {
    "A": "default: NVFP4-g16-4bit QKV/o_proj bank, fusion unreachable",
    "B": "DARKBLOOM_NATIVE_AFFINE_NVFP4=0: INT8-g32 bank, fusion live",
    "C": "NVFP4=0 plus FUSED_NORM_AFFINE_QKV=0: INT8-g32 bank, fusion off",
}

CONTRASTS = (
    ("C - A", "NVFP4 -> INT8 bank flip (confound)", "C", "A"),
    ("B - C", "fusion at matched quantization (the real question)", "B", "C"),
    ("B - A", "bundled toggle, as the advisor proposed it", "B", "A"),
)


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
        return arms
    print(f"=== {tag} ===")
    for arm in sorted(arms):
        reps = arms[arm]
        print(f"  arm {arm}  (n={len(reps)})  {ARM_DESCRIPTION.get(arm, '')}")
        for r in reps:
            print(
                f"    slot{r['slot']}  decode={r['decode']:.9f}  "
                f"prefill={r['prefill']:.9f}  ns={r['ns']:.6f}  "
                f"correct={r['correct']}  steps={r['steps']}"
            )
        for axis in AXES:
            s = stats([r[axis] for r in reps])
            print(
                f"    {axis:<8} mean={s['mean']:.9f} median={s['median']:.9f} "
                f"cv={s['cv']:.3f}%"
            )
        goldens = {r["golden"] for r in reps}
        correct = {r["correct"] for r in reps}
        print(f"    correctness: passed={correct} golden_hashes={len(goldens)} distinct")

    print("  contrasts (positive seconds = slower; positive ns = better):")
    for label, why, hi, lo in CONTRASTS:
        if hi not in arms or lo not in arms:
            print(f"    {label:<7} unavailable")
            continue
        print(f"    {label:<7} {why}")
        for axis in AXES:
            _, delta, band, na, nb = contrast(
                [r[axis] for r in arms[hi]], [r[axis] for r in arms[lo]], axis
            )
            print(
                f"      {axis:<8} {delta:+.3f}%  +/- {band:.3f}% (2sigma)  "
                f"n={na}/{nb}"
            )
    return arms


def sh(*args):
    try:
        return subprocess.run(
            args, capture_output=True, text=True, check=True
        ).stdout.strip()
    except Exception:
        return ""


def publish(per_tag, run_name, tags):
    import wandb

    run = wandb.init(
        entity=ENTITY,
        project=PROJECT,
        name=run_name,
        job_type="local-iterate-probe",
        tags=tags,
        config={
            "round": "r109-F",
            "probe": "lagunaNormAffineQKV fusion, decomposed",
            "arm/A": ARM_DESCRIPTION["A"],
            "arm/B": ARM_DESCRIPTION["B"],
            "arm/C": ARM_DESCRIPTION["C"],
            "harness/mode": "benchmark.sh --local-iterate",
            "harness/golden": "correctness_prompts/public_longcopy_gate_english_512_256.json",
            "harness/decode_steps": 128,
            "harness/checked_steps": 130,
            "host/chip": sh("sysctl", "-n", "machdep.cpu.brand_string"),
            "host/mem_bytes": int(sh("sysctl", "-n", "hw.memsize") or 0),
            "host/os": platform.platform(),
            "host/is_ranked_m5": False,
            "git/head": sh("git", "rev-parse", "HEAD"),
            "git/branch": sh("git", "rev-parse", "--abbrev-ref", "HEAD"),
            "claim/advisor_fusion_pct": 1.40,
            "claim/r91a_fusion_pct_upper_bound": 0.535,
            "bar/required_weighted_pct": 0.378,
            "submittable": False,
        },
        notes=(
            "Positive control only: arms B and C change numerics and are not "
            "submittable. C isolates the NVFP4->INT8 confound so that B-C "
            "prices the fusion at matched quantization."
        ),
    )

    slots = wandb.Table(
        columns=[
            "tag", "slot", "arm", "arm_description", "decode_s_per_token",
            "prefill_s_per_token", "ns", "passed_correctness", "checked_steps",
            "golden_hash",
        ]
    )
    arm_rows = wandb.Table(
        columns=["tag", "arm", "n", "axis", "mean", "median", "sd", "cv_pct"]
    )
    contrast_rows = wandb.Table(
        columns=[
            "tag", "contrast", "isolates", "axis", "delta_pct",
            "two_sigma_band_pct", "n_hi", "n_lo",
        ]
    )
    flat = {}
    for tag, arms in per_tag.items():
        for arm in sorted(arms):
            for r in arms[arm]:
                slots.add_data(
                    tag, r["slot"], arm, ARM_DESCRIPTION.get(arm, ""),
                    r["decode"], r["prefill"], r["ns"], r["correct"],
                    r["steps"], r["golden"],
                )
            for axis in AXES:
                s = stats([r[axis] for r in arms[arm]])
                arm_rows.add_data(
                    tag, arm, s["n"], axis, s["mean"], s["median"], s["sd"],
                    s["cv"],
                )
                flat[f"{tag}/{arm}/{axis}_mean"] = s["mean"]
                flat[f"{tag}/{arm}/{axis}_cv_pct"] = s["cv"]
                flat[f"{tag}/{arm}/n"] = s["n"]
        for label, why, hi, lo in CONTRASTS:
            if hi not in arms or lo not in arms:
                continue
            for axis in AXES:
                _, delta, band, na, nb = contrast(
                    [r[axis] for r in arms[hi]], [r[axis] for r in arms[lo]], axis
                )
                contrast_rows.add_data(tag, label, why, axis, delta, band, na, nb)
                key = label.replace(" - ", "_minus_")
                flat[f"{tag}/{key}/{axis}_delta_pct"] = delta
                flat[f"{tag}/{key}/{axis}_2sigma_pct"] = band

    run.log(
        {
            "probe/slots": slots,
            "probe/arms": arm_rows,
            "probe/contrasts": contrast_rows,
        }
    )
    run.summary.update(flat)
    print(f"WANDB_RUN_ID={run.id}")
    print(f"WANDB_RUN_URL={run.url}")
    run.finish()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("probe_tags", nargs="*", default=None)
    ap.add_argument("--wandb", action="store_true")
    ap.add_argument("--run-name")
    ap.add_argument("--tags", nargs="*", default=["r109-F", "nvfp4-fusion-probe"])
    args = ap.parse_args()

    probe_tags = args.probe_tags or ["pilot", "main"]
    per_tag = {}
    for tag in probe_tags:
        arms = report(tag)
        if arms:
            per_tag[tag] = arms

    if args.wandb:
        if not args.run_name:
            raise SystemExit("--wandb requires --run-name")
        if not per_tag:
            raise SystemExit("nothing to publish")
        publish(per_tag, args.run_name, args.tags)


if __name__ == "__main__":
    main()
