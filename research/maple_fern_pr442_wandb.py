#!/usr/bin/env python3
"""Publish the PR #442 router `uint2 simd_shuffle_xor` experiment record to W&B.

The result of this assignment is a per-kernel timing verdict, so the logged
metrics are IR-instruction counts, exactness/fault-injection mismatch counts,
and per-slot GPU microseconds. No GPU work happens here; the numbers come from
the runs recorded in research/maple-fern-pr442-router-uint2-shuffle.md.
"""
import statistics

import wandb

PROJECT = "mlxfast-maple"
ENTITY = "wandb-applied-ai-team"
BASE_SHA = "730e9c2be89a4ed8cf860e52f930f7ff222d4c95"

# Decode score sensitivity from the assignment calibration.
PCT_PER_US_STEP = 0.015280
CALLS_PER_STEP = 39
PROMOTION_BAR_US_STEP = 80.0

# (order, slot, rep, arm, us_per_call)
SLOTS = [
    ("off on ctl ctl on off", 1, 1, "off", 38.326),
    ("off on ctl ctl on off", 2, 1, "on", 38.372),
    ("off on ctl ctl on off", 3, 1, "ctl", 38.329),
    ("off on ctl ctl on off", 4, 1, "ctl", 38.311),
    ("off on ctl ctl on off", 5, 1, "on", 38.486),
    ("off on ctl ctl on off", 6, 1, "off", 38.440),
    ("off on ctl ctl on off", 7, 2, "off", 38.448),
    ("off on ctl ctl on off", 8, 2, "on", 38.325),
    ("off on ctl ctl on off", 9, 2, "ctl", 38.649),
    ("off on ctl ctl on off", 10, 2, "ctl", 38.351),
    ("off on ctl ctl on off", 11, 2, "on", 38.300),
    ("off on ctl ctl on off", 12, 2, "off", 38.391),
    ("off on ctl ctl on off", 13, 3, "off", 38.372),
    ("off on ctl ctl on off", 14, 3, "on", 38.481),
    ("off on ctl ctl on off", 15, 3, "ctl", 38.430),
    ("off on ctl ctl on off", 16, 3, "ctl", 38.346),
    ("off on ctl ctl on off", 17, 3, "on", 38.350),
    ("off on ctl ctl on off", 18, 3, "off", 38.398),
    ("on ctl off off ctl on", 1, 1, "on", 38.302),
    ("on ctl off off ctl on", 2, 1, "ctl", 38.375),
    ("on ctl off off ctl on", 3, 1, "off", 38.342),
    ("on ctl off off ctl on", 4, 1, "off", 38.374),
    ("on ctl off off ctl on", 5, 1, "ctl", 38.741),
    ("on ctl off off ctl on", 6, 1, "on", 38.372),
    ("on ctl off off ctl on", 7, 2, "on", 38.371),
    ("on ctl off off ctl on", 8, 2, "ctl", 38.383),
    ("on ctl off off ctl on", 9, 2, "off", 38.393),
    ("on ctl off off ctl on", 10, 2, "off", 38.370),
    ("on ctl off off ctl on", 11, 2, "ctl", 38.350),
    ("on ctl off off ctl on", 12, 2, "on", 38.833),
    ("on ctl off off ctl on", 13, 3, "on", 38.467),
    ("on ctl off off ctl on", 14, 3, "ctl", 38.368),
    ("on ctl off off ctl on", 15, 3, "off", 38.880),
    ("on ctl off off ctl on", 16, 3, "off", 38.370),
    ("on ctl off off ctl on", 17, 3, "ctl", 38.455),
    ("on ctl off off ctl on", 18, 3, "on", 38.323),
]

IR_CENSUS = [
    # variant, v2i32 shuffles per butterfly stage, i32 shuffles per stage
    ("shipped_on", 1, 0),
    ("shipped_ctl", 0, 2),
    ("shipped_off", 0, 2),
    ("faultA_offset8", 1, 0),
    ("faultB_swapped", 1, 0),
    ("cf_half_shuffles", 0, 1),
    ("cf_no_shuffles", 0, 0),
]

# arm, mismatching winners out of 16384, detection expected
EXACTNESS = [
    ("off", 0, False),
    ("on", 0, False),
    ("ctl", 0, False),
    ("faultA_offset8", 9324, True),
    ("faultB_swapped", 16384, True),
]

# variant, isolated-probe median us/step, delta vs off (%)
OFFLINE_PROBE = [
    ("off", 3849.8, 0.000),
    ("on", 3850.0, 0.040),
    ("ctl", 3858.1, 0.059),
    ("faultA_offset8", 3592.1, -6.761),
    ("faultB_swapped", 3860.8, 0.271),
    ("cf_half_shuffles", None, -0.255),
    ("cf_no_shuffles", None, -1.098),
]

config = {
    "assignment_id": "maple-2026-08-08b-router-uint2-shuffle",
    "revision_id": "r1",
    "pr_number": 442,
    "branch": "maple-fern/router-uint2-shuffle",
    "base_sha": BASE_SHA,
    "experiment_kind": "kernel_instruction_packing",
    "host": "M4 Pro, 20-core GPU, Apple GPU generation 16, 48 GiB (memory profile: low)",
    "guard_env": "DARKBLOOM_ROUTER_UINT2_SHUFFLE",
    "guard_default": "off",
    "arms": ["off", "on", "ctl"],
    "kernel": "laguna_routed_nvfp4_swiglu_qmv_packed_top8keys_r1_bf16_v2",
    "calls_per_decode_step": CALLS_PER_STEP,
    "kernel_share_of_decode_step_pct": 17.55,
    "submitted_paths": ["Sources/MLXFastModel/LagunaRuntimeModel.swift"],
    "editable_growth_bytes": 1772,
    "replication_target": "external promoted submission b9ccb0b (fyrsta7), +0.24..0.31% ranked-M5 decode",
    "timing_method": "per-dispatch GPU profile, DARKBLOOM_GPU_PROFILE_SPLIT=1, one worker process per slot",
    "abba_orders": ["off on ctl ctl on off", "on ctl off off ctl on"],
    "reps_per_order": 3,
    "decode_steps_per_slot": 33,
    "profiled_calls_per_slot": 1248,
    "pct_score_per_us_step": PCT_PER_US_STEP,
    "promotion_bar_us_step": PROMOTION_BAR_US_STEP,
}

run = wandb.init(
    entity=ENTITY,
    project=PROJECT,
    name="maple-fern-pr442-router-uint2-shuffle",
    job_type="kernel-timing",
    config=config,
    tags=["maple-fern", "pr-442", "router-top8", "simd-shuffle", "kill"],
)

ir_table = wandb.Table(columns=["variant", "v2i32_per_stage", "i32_per_stage", "total_per_stage"])
for name, v2, v1 in IR_CENSUS:
    ir_table.add_data(name, v2, v1, v2 + v1)
run.log({"ir_census": ir_table})

exact_table = wandb.Table(columns=["arm", "mismatching_winners", "total_winners", "detection_expected", "as_expected"])
for name, mism, expect in EXACTNESS:
    exact_table.add_data(name, mism, 16384, expect, (mism > 0) == expect)
    run.summary[f"exactness/{name}/mismatch"] = mism
run.log({"exactness_and_fault_injection": exact_table})

probe_table = wandb.Table(columns=["variant", "median_us_per_step", "delta_pct"])
for name, us, pct in OFFLINE_PROBE:
    probe_table.add_data(name, us, pct)
run.log({"offline_isolated_probe": probe_table})

slot_table = wandb.Table(columns=["order", "slot", "rep", "arm", "us_per_call", "us_per_step"])
for order, slot, rep, arm, us in SLOTS:
    slot_table.add_data(order, slot, rep, arm, us, us * CALLS_PER_STEP)
run.log({"abba_slots": slot_table})

by_arm = {}
for _, _, _, arm, us in SLOTS:
    by_arm.setdefault(arm, []).append(us)

baseline = statistics.fmean(by_arm["off"])
for arm, values in sorted(by_arm.items()):
    mean = statistics.fmean(values)
    run.summary[f"abba/{arm}/n"] = len(values)
    run.summary[f"abba/{arm}/us_per_call_mean"] = mean
    run.summary[f"abba/{arm}/us_per_call_sd"] = statistics.stdev(values)
    run.summary[f"abba/{arm}/delta_us_per_call"] = mean - baseline
    run.summary[f"abba/{arm}/delta_us_per_step"] = (mean - baseline) * CALLS_PER_STEP
    run.summary[f"abba/{arm}/delta_decode_score_pct"] = \
        -(mean - baseline) * CALLS_PER_STEP * PCT_PER_US_STEP

delta_us_step = (statistics.fmean(by_arm["on"]) - baseline) * CALLS_PER_STEP
run.summary.update({
    "verdict": "KILL",
    "verdict_reason": (
        "pooled n=12/arm, both ABBA orders agree; candidate -0.4 us/step with 95% CI "
        "[-5.3, +4.5] us/step, invariant control -0.1 us/step. The CI excludes the "
        "80 us/step promotion bar by ~15x."
    ),
    "primary/decode_delta_us_per_step": delta_us_step,
    "primary/decode_delta_score_pct": -delta_us_step * PCT_PER_US_STEP,
    "primary/decode_ci_low_us_per_step": -5.3,
    "primary/decode_ci_high_us_per_step": 4.5,
    "control/decode_delta_us_per_step":
        (statistics.fmean(by_arm["ctl"]) - baseline) * CALLS_PER_STEP,
    "correctness/drift_tripwire_checked_steps": 64,
    "correctness/drift_tripwire_passed_all_arms": True,
    "correctness/golden_hash":
        "b9509697c08a2cf3c2943a85f0b76e39c485c441794690fa76835b40a58d7a63",
    "correctness/equivalence_exact_steps": 8,
    "correctness/equivalence_prefill_max_abs_err": 0.125,
    "correctness/equivalence_prefill_preexisting_on_base": True,
    "correctness/timed_phase_token_divergences": 0,
    "correctness/timed_phase_slots_checked": 36,
    "fault_injection/arms": 3,
    "fault_injection/non_detections": 0,
    "mechanism/ideal_ceiling_pct_of_prologue": -0.255,
    "mechanism/all_shuffles_removed_pct_of_prologue": -1.098,
})

run.finish()
print(f"wandb run: {run.url}")
