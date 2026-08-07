#!/usr/bin/env python3
"""Log the PR #301 shared-expert QMV battery to W&B.

Every end-to-end number comes from `research/maple_shared_qmv_stage3_stats.py`,
so the W&B run and the deliverable report cannot drift apart. The kernel-level
Stage 1 / Stage 2 numbers are passed in explicitly because they were produced by
`research/maple_shared_qmv_kernel_stats.py` over GPU-profile logs that are too
large to keep in the repository; their digests are committed under
`research/shared-qmv-logs/`.

  python3 research/maple_shared_qmv_wandb.py /tmp/maple-shared-qmv-stage3-r*
"""
import argparse
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import maple_shared_qmv_stage3_stats as S  # noqa: E402

ENTITY = "wandb-applied-ai-team"
PROJECT = "mlxfast-maple"

# Kernel-level A/B results, from research/shared-qmv-logs/stage{1,2}.*.log.
# calls_per_step is the instrumented Stage 0 dispatch count for the changed
# kernel, so us_per_step is a count times a measured per-call delta.
CALLS_PER_STEP = 39
DECODE_STEP_WALL_MS = 9.825
GPU_BUSY_MS = 8.552
KERNEL_AB = [
    # stage, arm_a, arm_b, kernel, mean_a, sd_a, mean_b, sd_b, delta, lo, hi, df
    ("stage1", "off", "on", "laguna_shared_nvfp4_swiglu_qmv_rows1_bf16_v1",
     7.573, 0.120, 7.210, 0.070, -0.363, -0.495, -0.232, 8.1),
    ("stage1", "off", "on", "invariant_control_routed_qmv",
     None, None, None, None, +0.056, -0.563, +0.674, None),
    ("stage2", "on", "pairwise", "laguna_shared_nvfp4_swiglu_qmv_rows1_bf16_v1",
     7.210, 0.078, 7.350, 0.026, +0.140, +0.058, +0.222, 6.1),
    ("stage2", "on", "pairwise", "invariant_control_routed_qmv",
     38.817, 0.250, 38.368, 0.075, -0.449, None, None, None),
]
KERNEL_COLS = ["stage", "arm_a", "arm_b", "kernel", "mean_a_us", "sd_a_us",
               "mean_b_us", "sd_b_us", "delta_us", "ci95_lo_us", "ci95_hi_us",
               "df", "delta_us_per_step", "delta_percent_of_gpu_busy"]

RUN_COLS = ["run", "rep", "slot", "arm", "prefill_seconds_per_token",
            "decode_seconds_per_token", "passed_correctness", "checked_steps",
            "score", "passed"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("score_dirs", nargs="+")
    ap.add_argument("--run-name", default="maple-shared-qmv-twin-gap-stage3")
    ap.add_argument("--offline", action="store_true")
    args = ap.parse_args()

    rows = S.load(args.score_dirs)
    if not rows:
        raise RuntimeError("no score files found; refusing to publish")
    arms = []
    for r in rows:
        if r["arm"] not in arms:
            arms.append(r["arm"])

    import wandb
    if args.offline:
        os.environ["WANDB_MODE"] = "offline"
    run = wandb.init(
        entity=ENTITY, project=PROJECT, name=args.run_name,
        job_type="shared-qmv-twin-gap",
        config={
            "pr": 301,
            "assignment": "maple-2026-08-07o-shared-qmv-twin-gap",
            "revision": "r1",
            "branch": "maple-frieren/shared-qmv-twin-gap",
            "base_sha": "69178729b154cbb648ea0ce6152e92dbfdb17cc6",
            "host": "Mac16,11 M4 Pro 20c 48GiB macOS 26.5.2",
            "apple_gpu_generation": 16,
            "nax_reachable": False,
            "harness": "./benchmark.sh --local-iterate",
            "arms": arms,
            "order": "off on pairwise pairwise on off (palindromic ABBA)",
            "reps": len(set(r["rep"] for r in rows)),
            "runs": len(rows),
            "shared_qmv_calls_per_decode_step": CALLS_PER_STEP,
            "local_iterate_mde_percent": 0.73,
            "submitted_surface":
                "Sources/MLXFastModel/LagunaRuntimeModel.swift",
            "editable_growth_bytes": 7311,
        })

    summary = {}

    run_table = wandb.Table(columns=RUN_COLS)
    for r in rows:
        slot = ((r["idx"] - 1) % (2 * len(arms))) + 1
        run_table.add_data(
            os.path.basename(r["path"]).replace(".score.json", ""),
            r["rep"], slot, r["arm"], r["prefill_seconds_per_token"],
            r["decode_seconds_per_token"], bool(r["passed_correctness"]),
            r["checked_steps"], r["score"], bool(r["passed"]))

    n_pass = sum(1 for r in rows if r["passed_correctness"])
    summary["correctness/runs"] = len(rows)
    summary["correctness/passed"] = n_pass
    summary["correctness/all_passed"] = n_pass == len(rows)
    summary["correctness/checked_steps"] = max(
        r["checked_steps"] or 0 for r in rows)

    for key, label in S.AXES:
        by_arm = {a: [r[key] for r in rows if r["arm"] == a and r[key] is not None]
                  for a in arms}
        for a in arms:
            xs = by_arm[a]
            m, s = S.mean(xs), S.sd(xs)
            summary[f"{key}/{a}/mean"] = m
            summary[f"{key}/{a}/sd"] = s
            summary[f"{key}/{a}/se"] = s / math.sqrt(len(xs))
            summary[f"{key}/{a}/n"] = len(xs)
        for i, a in enumerate(arms):
            for b in arms[i + 1:]:
                d, hw, df = S.welch(by_arm[a], by_arm[b])
                base = S.mean(by_arm[a])
                tag = f"{key}/{a}_to_{b}"
                summary[f"{tag}/delta"] = d
                summary[f"{tag}/delta_percent"] = 100.0 * d / base
                summary[f"{tag}/ci95_lo_percent"] = 100.0 * (d - hw) / base
                summary[f"{tag}/ci95_hi_percent"] = 100.0 * (d + hw) / base
                summary[f"{tag}/df"] = df

    kernel_table = wandb.Table(columns=KERNEL_COLS)
    for rec in KERNEL_AB:
        per_step = rec[8] * CALLS_PER_STEP
        kernel_table.add_data(*rec, per_step,
                              100.0 * per_step / (GPU_BUSY_MS * 1000.0))
        if rec[3].startswith("laguna_shared"):
            tag = f"kernel/{rec[0]}/{rec[1]}_to_{rec[2]}"
            summary[f"{tag}/delta_us_per_call"] = rec[8]
            summary[f"{tag}/ci95_lo_us"] = rec[9]
            summary[f"{tag}/ci95_hi_us"] = rec[10]
            summary[f"{tag}/delta_percent"] = 100.0 * rec[8] / rec[4]
            summary[f"{tag}/delta_us_per_step"] = per_step
            summary[f"{tag}/percent_of_decode_wall"] = \
                100.0 * per_step / (DECODE_STEP_WALL_MS * 1000.0)

    # A run without both scored axes and the headline kernel delta would be
    # indistinguishable from a broken harness, so refuse to publish one.
    for key in ("decode_seconds_per_token/off/mean",
                "prefill_seconds_per_token/off/mean",
                "kernel/stage1/off_to_on/delta_us_per_call"):
        if key not in summary:
            raise RuntimeError(f"headline {key} missing; refusing to publish")

    run.log({"local_iterate_runs": run_table, "kernel_ab": kernel_table})
    run.summary.update(summary)
    print(f"logged {len(summary)} scalars, {len(rows)} runs -> {run.url}")
    print(f"run id: {run.id}")
    run.finish()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
