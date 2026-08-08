#!/usr/bin/env python3
"""Log the PR #457 R85-C rev2 float4-merge-epilogue re-port to W&B.

Every number comes back out of the JSON that the two analysers wrote, so the
W&B run and the research report cannot drift apart.

  python3 research/maple_r85c_epilogue_wandb.py \
      --wall /tmp/maple-r85c-epi/wall-off0.json \
      --wall-null /tmp/maple-r85c-epi/wall-off1.json \
      --kernel /tmp/maple-r85c-epi/kern-off0.json \
      --kernel-null /tmp/maple-r85c-epi/kern-off1.json \
      --logdir /tmp/maple-r85c-epi
"""
import argparse
import glob
import json
import os
import re

ENTITY = "wandb-applied-ai-team"
PROJECT = "mlxfast-maple"
PCT_PER_US_STEP = 0.015280
TOUCHED = ("sliding_fused_attn_ring", "full_fused_attn_grow")
DIVERGE_RE = re.compile(r"teacher-forced greedy tokens: (\d+) divergences")


def load(path):
    with open(path) as fh:
        return json.load(fh)


def token_identity(logdir):
    """Distinct teacher-forced token streams across all scored slots."""
    digests = {}
    for path in sorted(glob.glob(os.path.join(logdir, "[0-9]*.tokens"))):
        with open(path) as fh:
            digests.setdefault(fh.read(), []).append(os.path.basename(path))
    divergences = []
    for path in sorted(glob.glob(os.path.join(logdir, "[0-9]*.log"))):
        with open(path, errors="replace") as fh:
            m = DIVERGE_RE.search(fh.read())
        divergences.append(int(m.group(1)) if m else -1)
    return len(digests), list(digests.values()), divergences


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--wall", required=True)
    ap.add_argument("--wall-null", required=True)
    ap.add_argument("--kernel", required=True)
    ap.add_argument("--kernel-null", required=True)
    ap.add_argument("--logdir", required=True)
    ap.add_argument("--base-sha", required=True)
    ap.add_argument("--cand-sha", required=True)
    ap.add_argument("--predicted-us-step", type=float, default=18.6)
    ap.add_argument("--predicted-lo", type=float, default=12.9)
    ap.add_argument("--predicted-hi", type=float, default=24.3)
    ap.add_argument("--offline", action="store_true")
    args = ap.parse_args()

    wall, wall_null = load(args.wall), load(args.wall_null)
    kern, kern_null = load(args.kernel), load(args.kernel_null)
    n_streams, groups, divergences = token_identity(args.logdir)

    import wandb

    if args.offline:
        os.environ["WANDB_MODE"] = "offline"
    run = wandb.init(
        entity=ENTITY, project=PROJECT,
        name="maple-r85c-float4-merge-epilogue-report",
        job_type="paired-abba-timing",
        tags=["pr457", "r85-c", "rev2", "epilogue-report", "decode",
              "fused-attention", "m4pro"],
        config={
            "assignment_id": "maple-r85-c-placement-lever",
            "revision_id": "r85-c-rev2",
            "pr_number": 457,
            "base_sha": args.base_sha,
            "candidate_sha": args.cand_sha,
            "mechanism_commit_ported": "1aad492f",
            "original_pr": 205,
            "host": "AWS M4 Pro, Apple GPU generation 16",
            "kernels_touched": list(TOUCHED),
            "threadgroup_bytes_before": 16896,
            "threadgroup_bytes_after": 16896,
            "stores_per_lane_before": 8,
            "stores_per_lane_after": 2,
            "loads_per_lane_before": 8,
            "loads_per_lane_after": 2,
            "barriers_before": 3,
            "barriers_after": 3,
            "editable_bytes_delta": -454,
            "steps_per_run": wall["steady_steps"] + 1,
            "n_duplex": wall["n_duplex"],
            "pct_score_per_us_step": PCT_PER_US_STEP,
            "predicted_us_step": args.predicted_us_step,
            "predicted_ci95": [args.predicted_lo, args.predicted_hi],
        },
    )

    slot_tbl = wandb.Table(columns=["slot", "rep", "arm", "median_us_step",
                                    "trim10_us_step", "mean_us_step"])
    for s in wall["slots"]:
        slot_tbl.add_data(s["slot"], s["rep"], s["arm"], s["median"],
                          s["trimmed"], s["mean"])

    kern_tbl = wandb.Table(columns=["kernel", "base_us_step", "adj_us_step",
                                    "adj_ci_lo", "adj_ci_hi", "abs_us_step",
                                    "abs_ci_lo", "abs_ci_hi", "abs_sd",
                                    "touched"])
    for key, row in sorted(kern["labels"].items(),
                           key=lambda kv: -kv[1]["base_us_step"]):
        kern_tbl.add_data(key, row["base_us_step"], row["adj_us_step"],
                          row["adj_ci"][0], row["adj_ci"][1],
                          row["abs_us_step"], row["abs_ci"][0],
                          row["abs_ci"][1], row["abs_sd_us_step"],
                          any(t in key for t in TOUCHED))

    # Analyser sign convention: negative = candidate faster. Publish the win
    # as positive us/step saved so the score delta reads with the same sign.
    touched_saved = -sum(row["adj_us_step"] for key, row in kern["labels"].items()
                         if any(t in key for t in TOUCHED))
    med = wall["stats"]["median"]
    trim = wall["stats"]["trim10"]
    null_med = wall_null["stats"]["median"]

    summary = {
        "wall_median_saved_us_step": med["delta_us_step"],
        "wall_median_ci95_lo": med["ci95_lo"],
        "wall_median_ci95_hi": med["ci95_hi"],
        "wall_median_score_pct": med["score_pct"],
        "wall_trim10_saved_us_step": trim["delta_us_step"],
        "wall_trim10_score_pct": trim["score_pct"],
        "wall_null_saved_us_step": null_med["delta_us_step"],
        "wall_null_ci95_halfwidth": (null_med["ci95_hi"]
                                     - null_med["ci95_lo"]) / 2,
        "gpu_busy_adj_saved_us_step": -kern["busy_adj"]["us_step"],
        "gpu_busy_adj_ci95_lo": -kern["busy_adj"]["ci"][1],
        "gpu_busy_adj_ci95_hi": -kern["busy_adj"]["ci"][0],
        "gpu_busy_abs_saved_us_step": -kern["busy_abs"]["us_step"],
        "gpu_busy_null_adj_saved_us_step": -kern_null["busy_adj"]["us_step"],
        "touched_kernels_saved_us_step": touched_saved,
        "touched_kernels_score_pct": touched_saved * PCT_PER_US_STEP,
        "n_duplex": wall["n_duplex"],
        "n_duplex_null": wall_null["n_duplex"],
        "distinct_token_streams": n_streams,
        "max_teacher_forced_divergences": max(divergences),
        "bit_exact_argmax": n_streams == 1 and max(divergences) == 0,
        "predicted_us_step": args.predicted_us_step,
    }
    run.summary.update(summary)
    run.log({"slots": slot_tbl, "per_kernel": kern_tbl, **summary})
    print(json.dumps(summary, indent=2))
    print(f"token stream groups: {[len(g) for g in groups]}")
    print(f"run url: {run.url}")
    run.finish()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
