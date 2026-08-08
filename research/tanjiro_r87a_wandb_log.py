#!/usr/bin/env python3
"""Publish the R87-A routed gate/up prefetch measurement campaign to W&B.

Consumes the JSON reports emitted by ``research/tanjiro-r87a-stats.py --json``
(one per measurement block) and logs arm-level totals, the mandatory
per-kernel delta table, and the score conversion. No GPU work happens here.

Usage:
  python3 research/tanjiro_r87a_wandb_log.py \
      --block control=research/r87a-runs/control.json \
      --block ladder=research/r87a-runs/ladder.json \
      --block ceiling=research/r87a-runs/ceiling.json \
      --verdict "A1 NULL"
"""
import argparse
import json

import wandb

ENTITY = "wandb-applied-ai-team"
PROJECT = "mlxfast-maple"
BASE_SHA = "3217f111142346e004f41fae611a8bede172a659"

# PR #460, same host, full harness: decode 12960.20 us/step, so one us/step of
# decode is worth this much score, before the advisor's kernel-local haircut.
SCORE_PCT_PER_US_STEP = 0.015280
KERNEL_LOCAL_HAIRCUT = 0.60  # advisor 5228464233: discount kernel-local by ~40%


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--block", action="append", default=[],
                    metavar="NAME=PATH", help="stats --json report to ingest")
    ap.add_argument("--verdict", required=True)
    ap.add_argument("--name", default="maple-tanjiro-r87a-routed-gateup-prefetch")
    ap.add_argument("--notes", default="")
    args = ap.parse_args()

    blocks = {}
    for spec in args.block:
        name, _, path = spec.partition("=")
        with open(path) as fh:
            blocks[name] = json.load(fh)

    run = wandb.init(
        entity=ENTITY,
        project=PROJECT,
        name=args.name,
        job_type="kernel-latency-ablation",
        config={
            "assignment_id": "maple-r87-a-routed-qmv-head-latency",
            "revision_id": "r87-a-rev1",
            "pr_number": 469,
            "branch": "maple-tanjiro/r87-routed-qmv-head-latency",
            "base_sha": BASE_SHA,
            "student": "maple-tanjiro",
            "host": "M4 Pro, 20 GPU cores, Apple GPU generation 16 (applegpu_g16s), "
                    "48 GiB unified (low-memory startup profile), macOS 26.5.2",
            "nax_kernels_reachable": False,
            "scored_file": "Sources/MLXFastModel/LagunaRuntimeModel.swift",
            "touched_kernel":
                "laguna_routed_nvfp4_swiglu_qmv_packed_top8keys_r1_bf16_v2",
            "knobs": [
                "DARKBLOOM_ROUTED_GATEUP_INPUT_PF",
                "DARKBLOOM_PROBE_ROUTED_GATEUP_BARRIERS",
                "DARKBLOOM_PROBE_ROUTED_EXPERT0_PF",
            ],
            "profiler": "DARKBLOOM_GPU_PROFILE=1 DARKBLOOM_GPU_PROFILE_SPLIT=1",
            "driver": "research/decode_probe.py --steps 200 --profile",
            "score_pct_per_us_step_decode": SCORE_PCT_PER_US_STEP,
            "kernel_local_haircut": KERNEL_LOCAL_HAIRCUT,
            "blocks": list(blocks),
        },
        tags=["maple-tanjiro", "pr-469", "r87-a", "routed-gate-up",
              "decode-latency", "m4pro-directional"],
        notes=args.notes,
    )

    for block, rep in blocks.items():
        arm_tbl = wandb.Table(columns=[
            "block", "arm", "n", "busy_sum_us", "busy_sum_sd",
            "busy_union_us", "wall_us", "wall_sd"])
        for arm, e in rep["arms"].items():
            arm_tbl.add_data(
                block, arm, e["n"],
                e["busy_sum_us"]["mean"], e["busy_sum_us"]["sd"],
                e["busy_union_us"]["mean"],
                e["wall_us"]["mean"], e["wall_us"]["sd"])
            for k in ("busy_sum_us", "busy_union_us", "wall_us"):
                run.summary[f"{block}/{arm}/{k}"] = e[k]["mean"]
            run.summary[f"{block}/{arm}/n"] = e["n"]
        run.log({f"{block}/arms": arm_tbl})

        kern_tbl = wandb.Table(columns=[
            "block", "arm", "kernel", "touched", "ref_us_per_step",
            "share_pct", "delta_us_per_step", "ci95_us"])
        for arm, d in rep["deltas"].items():
            for row in d["per_kernel"]:
                kern_tbl.add_data(
                    block, arm, row["kernel"], row["touched"], row["ref_us"],
                    row["share_pct"], row["delta_us"], row["ci95_us"])
            run.summary[f"{block}/{arm}/subtotal_touched_us"] = \
                d["subtotal_touched_us"]
            run.summary[f"{block}/{arm}/subtotal_untouched_giveback_us"] = \
                d["subtotal_untouched_us"]
            for k, v in d["totals"].items():
                run.summary[f"{block}/{arm}/delta_{k}"] = v["delta_us"]
                run.summary[f"{block}/{arm}/delta_{k}_ci95"] = v["ci95_us"]
            # End-to-end wall delta is the only quantity that converts to score.
            wall = d["totals"]["wall_us"]["delta_us"]
            run.summary[f"{block}/{arm}/score_pct_from_wall"] = \
                -wall * SCORE_PCT_PER_US_STEP
            run.summary[f"{block}/{arm}/score_pct_from_touched_haircut"] = \
                -d["subtotal_touched_us"] * KERNEL_LOCAL_HAIRCUT * \
                SCORE_PCT_PER_US_STEP
        run.log({f"{block}/per_kernel_delta": kern_tbl})

    run.summary["verdict"] = args.verdict
    print(run.url)
    run.finish()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
