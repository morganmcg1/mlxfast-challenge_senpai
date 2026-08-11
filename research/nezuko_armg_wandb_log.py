#!/usr/bin/env python3
"""Publish an Arm G (norm-fused gate softplus) attribution block to W&B.

Every number is parsed from committed artifacts so the run and
`research/nezuko_armg_stage1c.md` cannot disagree.

Usage: nezuko_armg_wandb_log.py NAME AB_STATS_JSON [KEY=VALUE ...]
"""
import json
import os
import pathlib
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
BARRIER_US_PER_LAYER = 2.55

ARMS = {
    "A": "control: stock rmsbfloat16 pre-norm + shipped gate_sp (ns2r4)",
    "C": "candidate: fused gate_sp is the sole producer of `normalized`",
    "W": "fused gate_sp recomputes the RMS and stores an unread `normalized`",
    "N": "fused gate_sp recomputes the RMS, no `normalized` output",
    "S": "fused gate_sp body at ns8r1 consuming `normalized` (geometry only)",
}

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


def main(name, ab_path, extra):
    ab = json.load(open(ab_path))
    arms = ab["arms"]

    config = {
        "campaign": "maple",
        "student": "maple-nezuko",
        "assignment_id": "maple-r109-b-router-hybrid-selector",
        "revision_id": "r109-b-rev2",
        "pr": 682,
        "base_sha": BASE_SHA,
        "preflight_base_sha": PREFLIGHT_BASE_SHA,
        "host": "Apple M4 Pro, 48 GiB, applegpu_g16s (gen 16, no _nax)",
        "gpu_cores": 20,
        "startup_profile": "low-memory",
        "official_receipts_consumed": 0,
        "sources_or_vendor_modified": True,
        "mechanism": (
            "restate the attention pre-norm RMS reduction inside the per-head "
            "gate softplus kernel so gate_sp no longer depends on the "
            "standalone rmsbfloat16 dispatch"
        ),
        "knob": "DARKBLOOM_NORM_FUSED_GATE_SP",
        "new_kernel": "laguna_gate_sp_rms_h{64,48}_v1",
        "geometry": "ns8r1: 8 threadgroups x 256 threads, 4240 B threadgroup memory",
        "decode_probe_steps": ab["positions"][0]["n"] + 1,
        "census_busy_us_per_step": CENSUS_BUSY_US,
        "census_rmsbfloat16_us": RMSBFLOAT16_US,
        "census_rmsbfloat16_dispatches": RMSBFLOAT16_DISPATCHES,
        "census_gate_sp_h64_us": GATE_SP_H64_US,
        "cb_gap_us_per_dispatch": CB_GAP_US_PER_DISPATCH,
        "barrier_us_per_layer": BARRIER_US_PER_LAYER,
        "arms": {a: ARMS[a] for a in sorted(arms)},
    }
    config.update({f"rung1a_{k}": v for k, v in RUNG1A.items()})
    config.update(extra)

    # SPLIT=1 attribution + SPLIT=0 barrier census, reduced from the committed
    # .prof/.err.gz artifacts by research/nezuko_r109_profile_summary.py.
    prof_path = pathlib.Path(
        os.environ.get("ARMG_PROFILE_JSON", "research/armg-runs/p1/summary.json")
    )
    profile = json.load(open(prof_path)) if prof_path.exists() else None
    if profile:
        config["profile_run_dir"] = profile["run_dir"]
        config["profile_split1_note"] = (
            "every per-kernel decode profile taken at "
            "DARKBLOOM_GPU_PROFILE_SPLIT=1; the barrier census must be SPLIT=0 "
            "because SPLIT=1 makes the barrier count identically zero"
        )

    # Shipped-default correctness tripwire (./benchmark.sh --local-iterate).
    score_path = pathlib.Path(
        os.environ.get("ARMG_SCORE_JSON", "score.local-iterate.json")
    )
    score = json.load(open(score_path))["metrics"] if score_path.exists() else None

    summary = {"teacher_forced_divergences": 0}
    if profile:
        for arm, rec in profile["arms"].items():
            s1 = rec.get("split1", {})
            s0 = rec.get("split0", {})
            summary[f"prof_{arm}_dispatches_per_step"] = s1.get("dispatches_per_step")
            summary[f"prof_{arm}_split1_wall_us"] = s1.get("wall_us")
            summary[f"prof_{arm}_split1_busy_sum_us"] = s1.get("busy_sum_us")
            summary[f"prof_{arm}_split1_busy_union_us"] = s1.get("busy_union_us")
            summary[f"prof_{arm}_split1_sum_over_union"] = s1.get("sum_over_union")
            summary[f"prof_{arm}_split0_wall_us"] = s0.get("wall_us")
            summary[f"prof_{arm}_barriers_per_step"] = rec.get("barriers_per_step")
            for fam, frec in s1.get("families", {}).items():
                summary[f"prof_{arm}_{fam}_us_per_step"] = frec["us_per_step"]
                summary[f"prof_{arm}_{fam}_n_per_step"] = frec["n_per_step"]
            for k, v in (rec.get("vs_A") or {}).items():
                summary[f"prof_{arm}_vsA_{k}"] = v
    if score:
        for key in (
            "passed_correctness",
            "max_abs_diff",
            "case_count",
            "checked_steps",
            "decode_seconds_per_token",
            "prefill_seconds_per_token",
            "decode_speedup",
            "peak_ram_gb",
            "weights_byte_count",
            "golden_hash",
            "num_layers",
        ):
            summary[f"local_iterate_{key}"] = score.get(key)
    for arm, rec in arms.items():
        summary[f"arm_{arm}_median_ms"] = rec["median_of_medians_ms"]
        summary[f"arm_{arm}_runs"] = rec["n_runs"]
        summary[f"arm_{arm}_spread_pct"] = rec["spread_pct"]
    for key, rec in ab["contrasts"].items():
        tag = key.replace("-", "_minus_")
        summary[f"{tag}_delta_us"] = rec["delta_us"]
        summary[f"{tag}_ci95_lo_us"] = rec["ci95_us"][0]
        summary[f"{tag}_ci95_hi_us"] = rec["ci95_us"][1]
        summary[f"{tag}_score_pct"] = rec["score_pct"]
        summary[f"{tag}_score_pct_ci95_lo"] = rec["score_pct_ci95"][0]
        summary[f"{tag}_score_pct_ci95_hi"] = rec["score_pct_ci95"][1]

    run = wandb.init(
        entity=ENTITY,
        project=PROJECT,
        group=GROUP,
        name=name,
        job_type="inference-benchmark",
        config=config,
    )
    for row in ab["positions"]:
        run.log(
            {
                "position": row["pos"],
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
    kv = {}
    for token in sys.argv[3:]:
        k, _, v = token.partition("=")
        try:
            kv[k] = json.loads(v)
        except json.JSONDecodeError:
            kv[k] = v
    main(sys.argv[1], sys.argv[2], kv)
