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
import re
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
     7.210, 0.078, 7.350, 0.026, +0.139, +0.057, +0.221, 6.1),
    ("stage2", "on", "pairwise", "invariant_control_routed_qmv",
     38.817, 0.250, 38.368, 0.075, -0.449, None, None, None),
]
KERNEL_COLS = ["stage", "arm_a", "arm_b", "kernel", "mean_a_us", "sd_a_us",
               "mean_b_us", "sd_b_us", "delta_us", "ci95_lo_us", "ci95_hi_us",
               "df", "delta_us_per_step", "delta_percent_of_gpu_busy"]

RUN_COLS = ["run", "rep", "slot", "arm", "prefill_seconds_per_token",
            "decode_seconds_per_token", "passed_correctness", "checked_steps",
            "score", "passed", "error"]

# 128-step teacher-forced greedy-token tripwire on the uninstrumented worker,
# from research/shared-qmv-logs/drift-tripwire-128step.log.
TRIPWIRE_COLS = ["arm", "steps", "divergences", "step_mean_ms",
                 "seed_forward_ms", "worker_instrumented"]
TRIPWIRE = [
    ("off", 128, 0, 8.183, 547.26, False),
    ("on", 128, 0, 8.211, 547.46, False),
    ("pairwise", 128, 0, 8.179, 547.30, False),
]
# Every model-holding process this round ran the same teacher-forced comparison.
AGGREGATE_COLS = ["source", "processes", "steps_each", "comparisons",
                  "divergences"]
AGGREGATE = [
    ("stage1_kernel_abba", 12, 33, 396, 0),
    ("stage2_kernel_abba", 12, 33, 396, 0),
    ("stage2b_cancelled", 6, 33, 198, 0),
    ("drift_tripwire_128", 3, 128, 384, 0),
]

# Standing rule 16: a zero-divergence correctness result is only evidence once
# the same check is shown to catch a deliberately broken variant.
FAULT_LOG = "research/shared-qmv-logs/fault-injection.log"
FAULT_COLS = ["arm", "kind", "rc", "divergences", "first_divergence",
              "detected"]
FAULT_RE = re.compile(
    r"^(?P<tag>\S+)\s+rc=(?P<rc>-?\d+)\s+divergences=(?P<div>\S+)"
    r"(?:\s+first=(?P<first>.*))?$")


FREERUN_STEPS = 256
FREERUN_COLS = ["arm", "kind", "rc", "token_hash", "matches_off"]
FREERUN_RE = re.compile(
    r"^(?P<tag>\S+)\s+rc=(?P<rc>-?\d+)\s+hash=(?P<hash>\S+)$")


def load_fault(path):
    """Parse the fault-injection driver's summary lines, if archived."""
    if not os.path.exists(path):
        return []
    rows = []
    for line in open(path):
        m = FAULT_RE.match(line.strip())
        if not m:
            continue
        tag = m.group("tag")
        kind = "fault" if "-fault-" in tag else "control"
        try:
            div = int(m.group("div"))
        except ValueError:
            div = None
        # A control must find nothing; a fault arm must find something.
        detected = None if div is None else (
            div == 0 if kind == "control" else div > 0)
        rows.append((tag, kind, int(m.group("rc")), div,
                     (m.group("first") or "").strip(), detected))
    return rows


def load_freerun(path):
    """Parse the self-fed free-run trajectory hashes, if archived.

    Teacher forcing resets the trajectory every step, so it only compares
    single-step argmaxes. A free run compounds any difference, so two builds
    share a token hash only if every step agreed.
    """
    if not os.path.exists(path):
        return []
    raw = []
    for line in open(path):
        m = FREERUN_RE.match(line.strip())
        if m:
            raw.append((m.group("tag"), int(m.group("rc")), m.group("hash")))
    ref = next((h for t, _, h in raw if t.endswith("-off")), None)
    return [(tag, "fault" if "-fault-" in tag else "guard", rc, h,
             None if ref is None else h == ref) for tag, rc, h in raw]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("score_dirs", nargs="+")
    ap.add_argument("--run-name", default="maple-shared-qmv-twin-gap-stage3")
    ap.add_argument("--fault-log", default=FAULT_LOG)
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
            "reps": len(set((r["src"], r["rep"]) for r in rows)),
            "launch_dirs": sorted(set(r["src"] for r in rows)),
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
            f"{r['src']}/{os.path.basename(r['path']).replace('.score.json', '')}",
            r["rep"], slot, r["arm"], r["prefill_seconds_per_token"],
            r["decode_seconds_per_token"], bool(r["passed_correctness"]),
            r["checked_steps"], r["score"], bool(r["passed"]),
            r["error"] or "")

    n_pass = sum(1 for r in rows if r["passed_correctness"])
    # A cool-gate abort produces the same passed_correctness=False as a token
    # mismatch, so split them: only the second kind is a correctness result.
    cool_gate = [r for r in rows if not r["passed_correctness"]
                 and "cool-down gate" in (r["error"] or "")]
    mismatch = [r for r in rows if not r["passed_correctness"]
                and "cool-down gate" not in (r["error"] or "")]
    summary["correctness/runs"] = len(rows)
    summary["correctness/passed"] = n_pass
    summary["correctness/all_passed"] = n_pass == len(rows)
    summary["correctness/cool_gate_aborts"] = len(cool_gate)
    summary["correctness/token_mismatches"] = len(mismatch)
    summary["correctness/no_mismatch_in_completed_runs"] = not mismatch
    summary["correctness/checked_steps"] = max(
        r["checked_steps"] or 0 for r in rows)

    for key, label in S.AXES:
        by_arm = S.arm_values(rows, arms, key)
        for a in arms:
            xs = by_arm[a]
            summary[f"{key}/{a}/n"] = len(xs)
            if not xs:
                continue
            m, s = S.mean(xs), S.sd(xs)
            summary[f"{key}/{a}/mean"] = m
            summary[f"{key}/{a}/sd"] = s
            summary[f"{key}/{a}/se"] = s / math.sqrt(len(xs))
        for i, a in enumerate(arms):
            for b in arms[i + 1:]:
                xa, xb = by_arm[a], by_arm[b]
                if not xa or not xb:
                    continue
                d, hw, df = S.welch(xa, xb)
                base = S.mean(xa)
                tag = f"{key}/{a}_to_{b}"
                summary[f"{tag}/delta"] = d
                summary[f"{tag}/delta_percent"] = 100.0 * d / base
                summary[f"{tag}/df"] = df
                if not math.isnan(hw):
                    summary[f"{tag}/ci95_lo_percent"] = 100.0 * (d - hw) / base
                    summary[f"{tag}/ci95_hi_percent"] = 100.0 * (d + hw) / base

    tripwire_table = wandb.Table(columns=TRIPWIRE_COLS)
    for rec in TRIPWIRE:
        tripwire_table.add_data(*rec)
        summary[f"correctness/tripwire/{rec[0]}/divergences"] = rec[2]
    summary["correctness/tripwire/steps"] = TRIPWIRE[0][1]

    aggregate_table = wandb.Table(columns=AGGREGATE_COLS)
    for rec in AGGREGATE:
        aggregate_table.add_data(*rec)
    summary["correctness/aggregate/processes"] = sum(r[1] for r in AGGREGATE)
    summary["correctness/aggregate/comparisons"] = sum(r[3] for r in AGGREGATE)
    summary["correctness/aggregate/divergences"] = sum(r[4] for r in AGGREGATE)

    fault_rows = load_fault(args.fault_log)
    fault_table = wandb.Table(columns=FAULT_COLS)
    for rec in fault_rows:
        fault_table.add_data(*rec)
        summary[f"correctness/fault_injection/{rec[0]}/divergences"] = rec[3]
    if fault_rows:
        summary["correctness/fault_injection/arms"] = len(fault_rows)
        summary["correctness/fault_injection/all_as_expected"] = \
            all(r[5] for r in fault_rows)

    freerun_rows = load_freerun(args.fault_log)
    freerun_table = wandb.Table(columns=FREERUN_COLS)
    for rec in freerun_rows:
        freerun_table.add_data(*rec)
        summary[f"correctness/free_run/{rec[0]}/token_hash"] = rec[3]
    if freerun_rows:
        guards = [r for r in freerun_rows if r[1] == "guard"]
        faults = [r for r in freerun_rows if r[1] == "fault"]
        summary["correctness/free_run/arms"] = len(freerun_rows)
        summary["correctness/free_run/steps"] = FREERUN_STEPS
        summary["correctness/free_run/guards_bit_exact"] = \
            len(guards) > 1 and all(r[4] for r in guards)
        summary["correctness/free_run/faults_all_detected"] = \
            bool(faults) and all(r[4] is False for r in faults)

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

    run.log({"local_iterate_runs": run_table, "kernel_ab": kernel_table,
             "drift_tripwire_128step": tripwire_table,
             "correctness_aggregate": aggregate_table,
             "fault_injection": fault_table,
             "free_run_trajectory": freerun_table})
    run.summary.update(summary)
    print(f"logged {len(summary)} scalars, {len(rows)} runs -> {run.url}")
    print(f"run id: {run.id}")
    run.finish()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
