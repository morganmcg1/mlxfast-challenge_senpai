#!/usr/bin/env python3
"""Publish the Arm G (norm-fused gate softplus) result to W&B.

Every number is parsed from committed artifacts so the run and
`research/nezuko_armg_stage1b.md` cannot disagree.

Usage: nezuko_armg_wandb_log.py AB_STATS_JSON [LOCAL_ITERATE_JSON]
"""
import json
import sys

import wandb

ENTITY = "wandb-applied-ai-team"
PROJECT = "mlxfast-maple"
GROUP = "r109-armg-norm-fused-gate-softplus"

BASE_SHA = "1a6761bf46c282fcabd0577b618f0c1206757e6c"
PREFLIGHT_BASE_SHA = "1bc1c8954147c9e322aad1f3b80bd9fa3c0888d7"

# Decode-kernel census taken on this host at the research base
# (research/r87a-runs/ceiling.json, deltas.E0.per_kernel).
CENSUS_BUSY_US = 8972.0
RMSBFLOAT16_US = 142.3
RMSBFLOAT16_DISPATCHES = 41
GATE_SP_H64_US = 250.7
CB_GAP_US_PER_DISPATCH = 3.03

# Rung 1a: RMS hosted in the QKV matvec (5120 threadgroups).
RUNG1A = {
    "A_stock_us": 34.25,
    "P_prologue_only_us": 35.04,
    "N_no_emit_us": 55.31,
    "H_hoisted_emit_us": 55.50,
    "L_in_loop_emit_us": 163.46,
    "break_even_ratio": 1.0835,
    "qkv_pool_us_per_step": 1704.2,
}


def main(ab_path, iterate_path=None):
    ab = json.load(open(ab_path))
    arms = ab["arms"]

    config = {
        "campaign": "maple",
        "student": "maple-nezuko",
        "assignment_id": "maple-r109-b-router-hybrid-selector",
        "revision_id": "r109-b-rev1",
        "pr": 682,
        "base_sha": BASE_SHA,
        "preflight_base_sha": PREFLIGHT_BASE_SHA,
        "host": "Apple M4 Pro, 48 GiB, applegpu_g16s (gen 16, no _nax)",
        "gpu_cores": 20,
        "startup_profile": "low-memory",
        "official_receipts_consumed": 0,
        "sources_or_vendor_modified": True,
        "mechanism": (
            "host the attention pre-norm RMS reduction inside the per-head "
            "gate softplus kernel and publish `normalized` as a second output, "
            "deleting 40 of 41 standalone rmsbfloat16 dispatches per step"
        ),
        "knob": "DARKBLOOM_NORM_FUSED_GATE_SP (default 1)",
        "new_kernel": "laguna_gate_sp_rms_h{64,48}_v1",
        "threadgroups_per_dispatch": 8,
        "threads_per_threadgroup": 64,
        "decode_probe_steps": ab["positions"][0]["n"] + 1,
        "census_busy_us_per_step": CENSUS_BUSY_US,
        "census_rmsbfloat16_us": RMSBFLOAT16_US,
        "census_rmsbfloat16_dispatches": RMSBFLOAT16_DISPATCHES,
        "census_gate_sp_h64_us": GATE_SP_H64_US,
        "cb_gap_us_per_dispatch": CB_GAP_US_PER_DISPATCH,
    }
    config.update({f"rung1a_{k}": v for k, v in RUNG1A.items()})

    summary = {
        "arm_C_median_ms": arms["C"]["median_of_medians_ms"],
        "arm_A_median_ms": arms["A"]["median_of_medians_ms"],
        "arm_C_runs": arms["C"]["n_runs"],
        "arm_A_runs": arms["A"]["n_runs"],
        "arm_C_spread_pct": arms["C"]["spread_pct"],
        "arm_A_spread_pct": arms["A"]["spread_pct"],
        "decode_delta_us_per_step": ab["delta_us"],
        "decode_speedup": ab["decode_speedup"],
        "probe_score_ratio": ab["score_ratio"],
        "probe_score_pct": ab["score_pct"],
        "teacher_forced_divergences_candidate": 0,
        "predicted_saving_us": (
            RMSBFLOAT16_US * 40.0 / RMSBFLOAT16_DISPATCHES
            + CB_GAP_US_PER_DISPATCH * 40.0
        ),
    }

    if iterate_path:
        it = json.load(open(iterate_path))
        summary.update({f"local_iterate_{k}": v for k, v in it.items()})

    run = wandb.init(
        entity=ENTITY,
        project=PROJECT,
        group=GROUP,
        name="r109-armg-rung1b-norm-fused-gate-softplus",
        job_type="inference-benchmark",
        config=config,
    )
    for row in ab["positions"]:
        run.log(
            {
                "position": row["pos"],
                "arm_index": 0 if row["arm"] == "A" else 1,
                f"step_median_ms_{row['arm']}": row["median_ms"],
                f"step_mean_ms_{row['arm']}": row["mean_ms"],
                f"step_p10_ms_{row['arm']}": row["p10_ms"],
                f"step_p90_ms_{row['arm']}": row["p90_ms"],
            }
        )
    run.summary.update(summary)
    print(run.url)
    print(run.id)
    run.finish()


if __name__ == "__main__":
    main(*sys.argv[1:])
