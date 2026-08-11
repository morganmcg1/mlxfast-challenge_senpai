#!/usr/bin/env python3
"""Publish the R125-C routed-expert-QMV threadgroup-granularity ladder to W&B.

Re-derives every statistic from the raw per-step CSV with the same trim/median
rule as research/edward_r125c_bootstrap.py, so the run's numbers cannot drift
from the memo's numbers. Every steady per-step wall sample is logged so the
palindromic arm order and any thermal drift stay inspectable.

Usage:
  python3 research/edward_r125c_wandb.py --csv research/maple-edward-r125c/ladder_raw.csv
"""
from __future__ import annotations

import argparse
import csv
import os
import random
import subprocess
from collections import defaultdict

import wandb

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRIM = 16
BOOT = 20000
SEED = 125
# Palindromic slot-balanced order actually executed by research/edward_r125c_ladder.sh.
ORDER = "ABDDBABDAADBDABBADADBBDADBAABDBADDAB"
ARM_THREADS = {"A": 64, "B": 128, "D": 256, "N": 64}


def median(xs):
    s = sorted(xs)
    n = len(s)
    return s[n // 2] if n % 2 else 0.5 * (s[n // 2 - 1] + s[n // 2])


def boot_ci(deltas, rng):
    stats = sorted(median([rng.choice(deltas) for _ in deltas]) for _ in range(BOOT))
    return stats[int(0.025 * BOOT)], stats[int(0.975 * BOOT)]


def sh(cmd):
    return subprocess.run(cmd, cwd=REPO, capture_output=True, text=True).stdout.strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=os.path.join(REPO, "research/maple-edward-r125c/ladder_raw.csv"))
    ap.add_argument("--runs-tsv", default=os.path.join(REPO, "research/maple-edward-r125c/ladder_runs.tsv"))
    args = ap.parse_args()

    per_block = defaultdict(list)   # (block, arm) -> [ms]
    per_run = defaultdict(list)     # run -> [ms]
    run_meta = {}                   # run -> (block, arm)
    steps = []
    with open(args.csv) as fh:
        for rec in csv.DictReader(fh):
            step, run = int(rec["step"]), int(rec["run"])
            arm, block, ms = rec["arm"], int(rec["block"]), float(rec["ms"])
            steps.append((run, step, arm, block, ms))
            if step <= TRIM:
                continue
            per_block[(block, arm)].append(ms)
            per_run[run].append(ms)
            run_meta[run] = (block, arm)

    divergences = 0
    n_runs = 0
    with open(args.runs_tsv) as fh:
        for rec in csv.DictReader(fh, delimiter="\t"):
            divergences += int(rec["divergences"])
            n_runs += 1

    arms = sorted({a for (_b, a) in per_block})
    blocks = sorted({b for (b, _a) in per_block})
    lvl = {k: median(v) * 1000.0 for k, v in per_block.items()}  # us/token

    rng = random.Random(SEED)
    contrasts = {}
    for arm in [a for a in arms if a != "A"]:
        deltas = [lvl[(b, arm)] - lvl[(b, "A")] for b in blocks]
        lo, hi = boot_ci(deltas, rng)
        neg = sum(1 for d in deltas if d < 0)
        base = sum(lvl[(b, "A")] for b in blocks) / len(blocks)
        contrasts[arm] = {
            "median_delta_us": median(deltas),
            "mean_delta_us": sum(deltas) / len(deltas),
            "ci95_lo_us": lo,
            "ci95_hi_us": hi,
            "covers_zero": lo <= 0.0 <= hi,
            "blocks_faster": neg,
            "blocks_slower": len(deltas) - neg,
            "relative_decode_pct": -100.0 * median(deltas) / base,
            "implied_phi": (base / (base + median(deltas))) ** 0.75,
            "per_block_delta_us": deltas,
        }

    # Same-arm null: within each block contrast the two byte-identical A runs.
    null_deltas = []
    for b in blocks:
        a_runs = sorted(r for r in per_run if run_meta[r] == (b, "A"))
        if len(a_runs) >= 2:
            lo_r, hi_r = a_runs[0], a_runs[-1]
            null_deltas.append((median(per_run[hi_r]) - median(per_run[lo_r])) * 1000.0)
    null_lo, null_hi = boot_ci(null_deltas, rng)

    run = wandb.init(
        project="mlxfast-maple",
        entity="wandb-applied-ai-team",
        name="r125c-routed-qmv-tg-granularity",
        job_type="kernel-ladder",
        tags=["r125-c", "routed-qmv", "threadgroup", "refuted", "m4pro"],
        config={
            "assignment_id": "maple-r125-c-expert-qmv-tg-granularity",
            "revision_id": "r125-c-rev1",
            "pr": 731,
            "base_sha": "a9de9e8f21188715f6d80ada4b581bcd50d4ec81",
            "head_sha": sh(["git", "rev-parse", "HEAD"]),
            "branch": "maple-edward/r125-c-expert-qmv-tg-granularity",
            "host": "Apple M4 Pro, 20 GPU cores, Apple GPU gen 16",
            "kernel": "lagunaRoutedSwiGLUQMVPackedTop8R1 (routed expert gate/up QMV)",
            "env_knob": "DARKBLOOM_ROUTED_QMV_TG",
            "compiled_default_threads": 64,
            "arms": {a: ARM_THREADS[a] for a in arms},
            "order": ORDER,
            "steps_per_run": 512,
            "trim_leading_steps": TRIM,
            "bootstrap_resamples": BOOT,
            "bootstrap_seed": SEED,
            "statistic": "median paired per-block delta",
            "n_runs": n_runs,
            "n_blocks": len(blocks),
            "DARKBLOOM_SHARED_ROUTED_QMV_FUSED": "0",
        },
    )

    for r, s, arm, block, ms in steps:
        wandb.log({
            "step/ms": ms,
            "step/us_per_token": ms * 1000.0,
            "step/index": s,
            "step/run": r,
            "step/block": block,
            "step/arm_threads": ARM_THREADS[arm],
            "step/steady": int(s > TRIM),
        })

    run_tbl = wandb.Table(columns=["run", "block", "arm", "threads", "median_us_per_token", "n_steady"])
    for r in sorted(per_run):
        b, a = run_meta[r]
        run_tbl.add_data(r, b, a, ARM_THREADS[a], median(per_run[r]) * 1000.0, len(per_run[r]))

    blk_tbl = wandb.Table(columns=["block"] + [f"{a}_us_per_token" for a in arms])
    for b in blocks:
        blk_tbl.add_data(b, *[lvl[(b, a)] for a in arms])

    ctr_tbl = wandb.Table(columns=[
        "arm", "threads", "median_delta_us", "ci95_lo_us", "ci95_hi_us",
        "covers_zero", "blocks_faster", "blocks_slower", "relative_decode_pct", "implied_phi",
    ])
    for a, c in contrasts.items():
        ctr_tbl.add_data(
            a, ARM_THREADS[a], c["median_delta_us"], c["ci95_lo_us"], c["ci95_hi_us"],
            c["covers_zero"], c["blocks_faster"], c["blocks_slower"],
            c["relative_decode_pct"], c["implied_phi"],
        )

    arm_level = {a: sum(lvl[(b, a)] for b in blocks) / len(blocks) for a in arms}
    summary = {
        "correctness/total_divergences": divergences,
        "correctness/runs_checked": n_runs,
        "correctness/tokens_checked": n_runs * 512,
        "correctness/bit_identical": divergences == 0,
        "verdict": "refuted",
        "landed": False,
        "default_build_identical_to_base": True,
        "table/per_run": run_tbl,
        "table/per_block": blk_tbl,
        "table/contrasts": ctr_tbl,
    }
    for a in arms:
        summary[f"arm/{a}_threads"] = ARM_THREADS[a]
        summary[f"arm/{a}_us_per_token"] = arm_level[a]
    for a, c in contrasts.items():
        for k in ("median_delta_us", "mean_delta_us", "ci95_lo_us", "ci95_hi_us",
                  "covers_zero", "blocks_faster", "blocks_slower",
                  "relative_decode_pct", "implied_phi"):
            summary[f"contrast/{a}_vs_A/{k}"] = c[k]

    # Primary metric contract: decode us/token, minimize. Candidate = best
    # non-reference rung (B, 128 threads); baseline = compiled default (A, 64).
    summary["null/same_arm_median_us"] = median(null_deltas)
    summary["null/same_arm_ci95_lo_us"] = null_lo
    summary["null/same_arm_ci95_hi_us"] = null_hi
    summary["null/same_arm_max_abs_us"] = max(abs(d) for d in null_deltas)
    summary["primary/name"] = "decode_us_per_token"
    summary["primary/direction"] = "minimize"
    summary["primary/baseline"] = arm_level["A"]
    summary["primary/candidate"] = arm_level["B"]
    summary["primary/delta"] = arm_level["B"] - arm_level["A"]
    run.summary.update(summary)

    art = wandb.Artifact("r125c-ladder", type="measurements")
    art.add_file(args.csv)
    art.add_file(args.runs_tsv)
    art.add_file(os.path.join(REPO, "research/maple-edward-r125c/bootstrap_report.txt"))
    art.add_file(os.path.join(REPO, "research/maple-edward-r125c-expert-qmv-tg-granularity.md"))
    run.log_artifact(art)

    print(f"run url: {run.url}")
    print(f"run id : {run.id}")
    run.finish()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
