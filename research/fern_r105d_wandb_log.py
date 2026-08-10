#!/usr/bin/env python3
"""Log the r105-D decode dispatch/occupancy census summary to W&B.

Reads the two committed artifacts produced by fern_r105d_census.py and
fern_r105d_bytes.py and publishes their summary statistics as one run in
wandb-applied-ai-team/mlxfast-maple.

This run records a static census, not a timed experiment: every number is
derived from the 105-C SPLIT=1 dispatch traces plus arithmetic. Per-kernel
label seconds obey rule 82b (shape only, never magnitude).
"""

import csv
import json
import os
import pathlib

import wandb

ART = pathlib.Path(__file__).resolve().parent / "artifacts" / "fern-r105d"
CSV_PATH = ART / "decode-dispatch-census.csv"
BYTES_PATH = ART / "decode-byte-census.json"
OCC_PATH = ART / "decode-occupancy-summary.json"

PROJECT = "mlxfast-maple"
ENTITY = "wandb-applied-ai-team"


def family_rows():
    with CSV_PATH.open() as fh:
        return [r for r in csv.DictReader(fh) if r["row_type"] == "family"]


def main():
    occ = json.loads(OCC_PATH.read_text())
    byt = json.loads(BYTES_PATH.read_text())
    fams = family_rows()

    cfg = {
        "assignment_id": "maple-r105-d-decode-dispatch-occupancy-census",
        "revision_id": "r105-d-rev1",
        "student": "maple-fern",
        "pr_number": 603,
        "branch": "maple-fern/r105-decode-dispatch-occupancy-census",
        "base_sha": "5f7861c0981278929c3ef43d54a6d5bca10a8659",
        "phase": "A_only_no_official_receipts",
        "host": "M4_Pro_20core_48GiB_applegpu_g16s",
        "ranked_host": "M5_Max_40core_128GiB",
        "trace_source": "105-C SPLIT=1 dispatch.tsv, 10 arms",
        "sources_vendor_bytes_changed": 0,
        "rule_82b": "label microseconds are shape-only, never magnitude",
    }

    roof = byt["roofline"]
    roll = byt["occupancy_rollup"]
    n = occ["dispatches_per_step"]

    summary = {
        # --- step structure (exact, from traces) ---
        "census/dispatches_per_step": n,
        "census/families": occ["distinct_families"],
        "census/tg_launches_per_step": occ["tg_launches_per_step"],
        "census/gpu_threads_per_step": occ["gpu_threads_per_step"],
        # --- occupancy rollup ---
        "occupancy/single_tg_dispatches": occ["single_tg_dispatches"],
        "occupancy/single_tg_frac": occ["single_tg_dispatches"] / n,
        "occupancy/sub_c40_dispatches": occ["sub_C40_dispatches"],
        "occupancy/sub_c40_frac": occ["sub_C40_dispatches"] / n,
        "occupancy/sub_c20_dispatches": occ["sub_C20_dispatches"],
        "occupancy/at_or_above_c40_dispatches": n - occ["sub_C40_dispatches"],
        "occupancy/waves_dispatch_C40_total": occ["waves_dispatch_C40_total"],
        "occupancy/waves_dispatch_C20_total": occ["waves_dispatch_C20_total"],
        "occupancy/waves_resident_C40_simdmodel_total": occ["waves_resident_C40_simdmodel_total"],
        # --- byte census ---
        "bytes/total_bytes_per_step": byt["step_bytes"],
        "bytes/total_mb_per_step": roof["step_bytes_MB"],
        "bytes/single_tg_bytes_per_step": byt["single_tg_family_bytes"],
        "bytes/single_tg_pct_of_step": byt["single_tg_pct_of_step_bytes"],
        "bytes/sub_c40_pct_of_step": roll["SUB_C40_all"]["pct_of_step_bytes"],
        "bytes/at_or_above_c40_pct_of_step": roll["AT_OR_ABOVE_C40"]["pct_of_step_bytes"],
        "bytes/r105d_tail_pct_of_step": byt["r105d_tail_pct_of_step"],
        # --- label-second shape (rule 82b: shape only, never magnitude) ---
        "label82b/single_tg_pct_of_label_total": roll["SINGLE_TG"]["pct_of_label_total"],
        "label82b/sub_c40_pct_of_label_total": roll["SUB_C40_all"]["pct_of_label_total"],
        "label82b/at_or_above_c40_pct_of_label_total": roll["AT_OR_ABOVE_C40"]["pct_of_label_total"],
        # --- roofline ---
        "roofline/m5_dram_floor_us": roof["m5_dram_floor_us"],
        "roofline/m5_dram_floor_pct_of_step": roof["m5_dram_floor_pct_of_step"],
        "roofline/m5_step_us": roof["m5_ranked_step_us"],
        "roofline/achieved_gb_per_s": roof["m5_achieved_gbs_at_ranked_step"],
        "roofline/unattributed_residual_us": roof["m5_headroom_above_dram_floor_us"],
        "roofline/unattributed_residual_pct_of_score": roof["m5_headroom_pct_score"],
        "roofline/single_tg_dram_floor_us": byt["single_tg_m5_dram_floor_us"],
        # --- mechanism bounds (the actual deliverable) ---
        "bound/rule65_nominal_all_dispatches_us": 954.842,
        "bound/rule65_nominal_all_dispatches_pct": 14.540,
        "bound/rule65_nominal_single_tg_us": 196.585,
        "bound/rule65_nominal_single_tg_pct": 2.993,
        "bound/rule65_nominal_rms_us": 95.952,
        "bound/rule65_nominal_rms_pct": 1.461,
        "bound/measured_elasticity_us_per_dispatch": 0.108,
        "bound/measured_single_tg_recoverable_us": 9.07,
        "bound/measured_single_tg_recoverable_pct_of_cs": 0.138,
        "bound/gate_pct_of_cs": 0.5,
        "bound/pr483_upper_bound_us": 35.02,
        "bound/pr483_upper_bound_pct": 0.535,
        # --- self-falsification ---
        "falsify/pr196_naive_sum_predicted_step_us": 63016.0,
        "falsify/pr196_naive_sum_over_prediction_x": 15.2,
        # --- verdict ---
        "verdict/outcome": "N-1_pool_does_not_exist",
        "verdict/a4_955us_is_additive": False,
        "verdict/headline_1_84_single_tg": "TRUE",
        "verdict/headline_2_203_sub_c40": "TRUE",
        "verdict/headline_3_327395_tg_launches": "TRUE",
        "verdict/headline_4_959us_rms_tax": "ARITHMETIC_TRUE_CAUSALLY_FALSE",
        "verdict/headline_5_prefill_misnomer": "TRUE_BUT_NO_LEVER",
    }

    run = wandb.init(
        entity=ENTITY,
        project=PROJECT,
        name="fern-r105d-decode-dispatch-occupancy-census",
        job_type="census",
        tags=["r105-D", "maple-fern", "phase-A", "census", "no-timing", "N-1"],
        config=cfg,
        notes=(
            "Static decode dispatch/occupancy/byte census for the 408-dispatch decode step. "
            "No GPU timing was run for this result; every number is trace-derived arithmetic "
            "plus previously measured in-repo elasticities. Outcome N-1: the single-TG "
            "occupancy pool does not exist as a recoverable lever."
        ),
    )

    tbl = wandb.Table(
        columns=[
            "family", "calls_per_step", "threadgroups", "threads_per_tg",
            "simdgroups_per_tg", "tg_launches_per_step", "occupancy_class_C40",
            "waves_dispatch_C40", "waves_dispatch_C20",
        ]
    )
    for r in sorted(fams, key=lambda x: -int(x["tg_launches"])):
        tbl.add_data(
            r["family"], int(r["calls_per_step"]), int(r["threadgroups"]),
            int(r["threads_per_tg"]), int(r["simdgroups_per_tg"]),
            int(r["tg_launches"]), r["occupancy_class_C40"],
            int(r["waves_dispatch_C40"]), int(r["waves_dispatch_C20"]),
        )
    run.log({"census/family_table": tbl})

    occ_tbl = wandb.Table(
        columns=["class", "dispatches", "pct_of_408", "bytes_per_step",
                 "pct_of_step_bytes", "label_us_m4_split1_82b", "pct_of_label_total"]
    )
    for k, v in roll.items():
        occ_tbl.add_data(
            k, v["dispatches"], v["pct_of_408_dispatches"], v["bytes_per_step"],
            v["pct_of_step_bytes"], v["label_us_m4_split1"], v["pct_of_label_total"],
        )
    run.log({"census/occupancy_rollup": occ_tbl})

    for k, v in summary.items():
        run.summary[k] = v

    art = wandb.Artifact("fern-r105d-decode-census", type="census")
    art.add_file(str(CSV_PATH))
    art.add_file(str(BYTES_PATH))
    art.add_file(str(OCC_PATH))
    run.log_artifact(art)

    print(f"run_id={run.id}")
    print(f"url={run.url}")
    run.finish()


if __name__ == "__main__":
    os.environ.setdefault("WANDB_SILENT", "false")
    main()
