#!/usr/bin/env python3
"""Publish the r101-A decode pool model to W&B.

Reads only the artifacts produced by fern_r101_byte_audit.py,
fern_r101_pool_model.py and the fern_r101_bw_probe.swift job log; performs no
measurement of its own.

    python research/fern_r101_wandb_log.py
"""

from __future__ import annotations

import csv
import json
import pathlib
import re

import wandb

ART = pathlib.Path(__file__).resolve().parent / "artifacts" / "fern-r101"
ENTITY = "wandb-applied-ai-team"
PROJECT = "mlxfast-maple"


def read_tsv(path: pathlib.Path, delim: str = "\t") -> tuple[list[str], list[list[str]]]:
    rows = [r for r in csv.reader(path.open(), delimiter=delim) if r and not r[0].startswith("#")]
    return rows[0], rows[1:]


def numeric(v: str):
    try:
        return float(v)
    except ValueError:
        return v


def table(path: pathlib.Path, delim: str = "\t") -> wandb.Table:
    header, rows = read_tsv(path, delim)
    return wandb.Table(columns=header, data=[[numeric(c) for c in r] for r in rows])


def ladder_tables(path: pathlib.Path) -> dict[str, wandb.Table]:
    """Split the probe log into its four labelled arms."""
    arms: dict[str, list[list[str]]] = {}
    headers: dict[str, list[str]] = {}
    arm = None
    for line in path.read_text().splitlines():
        line = line.rstrip()
        if not line:
            continue
        if line.startswith("#"):
            m = re.search(r"arm=(\S+)", line)
            if m:
                arm = m.group(1)
                if arm in arms:
                    arm = f"{arm}_rule71"
                arms.setdefault(arm, [])
            continue
        if arm is None:
            continue
        cells = line.split("\t")
        if arm not in headers:
            headers[arm] = cells
        else:
            arms[arm].append([numeric(c) for c in cells])
    return {a: wandb.Table(columns=headers[a], data=rows) for a, rows in arms.items() if rows}


def main() -> None:
    model = json.loads((ART / "pool-model.json").read_text())
    pool = model["pool"]
    primary = model["map_primary"]
    receipts = model["receipt_validation"]

    run = wandb.init(
        entity=ENTITY,
        project=PROJECT,
        name="fern-r101-decode-pool-model",
        job_type="analysis",
        tags=["r101-A", "maple-fern", "pool-model", "bandwidth-census", "no-submitted-surface-delta"],
        config={
            "assignment_id": "maple-r101-a-decode-pool-model-rebuild",
            "revision_id": "r101-a-rev1",
            "pr": 561,
            "base_sha": "3567695bb196e92c37e940aaafcbfb9c2b6d61b9",
            "host": model["host"],
            "host_gpu_generation": "applegpu_g16s (Apple GPU gen 16, pre-NAX)",
            "probe_job_id": "4f4ee576-9715-49a4-be94-cbf00e3f027f",
            "probe_geometry_threadgroups": 40,
            "probe_geometry_tg_per_core": 2,
            "probe_geometry_threads_per_tg": 256,
            "probe_geometry_ilp": 8,
            "probe_geometry_grid": 10240,
            "probe_bytes_written_per_command_buffer": 163840,
            "probe_rounds": 15,
            "byte_epoch_census": "group-16 attn, lmhead 128.5MB, row-major attn scales",
            "byte_epoch_head": "group-32 attn, lmhead 109.182976MB, lane-major attn scales",
            "decode_denominator_wall_us": 4893.7,
            "decode_denominator_steady_state_us": 4141.5,
            "score_pct_per_us_step": 0.015228,
            "m5_ceiling_published_gbs": model["m5_ceiling_published_gbs"],
            "m5_ceiling_geometry_corrected_gbs": model["m5_ceiling_geometry_corrected_gbs"],
            "alpha_bandwidth": primary["alpha"],
            "beta_issue": primary["beta"],
            "bw_threshold_pct_of_peak": model["bw_threshold_pct"],
            "submitted_surface_byte_delta": 0,
        },
    )

    run.summary.update(
        {
            # P2 measured ceilings
            "measured_dram_read_ceiling_gbs": model["measured_ceiling_gbs"],
            "measured_sequential_ceiling_gbs": model["sequential_ceiling_gbs"],
            "theoretical_peak_gbs": model["theoretical_peak_gbs"],
            "measured_pct_of_theoretical": 100.0 * model["measured_ceiling_gbs"] / model["theoretical_peak_gbs"],
            "published_237p4_pct_of_measured_ceiling": 100.0 * 237.4 / model["sequential_ceiling_gbs"],
            "tanjiro_replica_gbs": 259.52,
            "tanjiro_replica_pct_of_measured_ceiling": 98.7,
            "llc_knee_mib_low": 16,
            "llc_knee_mib_high": 20,
            # P0
            "p0_rows_exceeding_peak": model["p0_rows_exceeding_peak"],
            "p0_rows_total": 8,
            "p0_injection_rows_exceeding_peak": 3,
            "p0_injection_rows_total": 3,
            "p0_census_rows_exceeding_peak": 0,
            "p0_receiptdiff_rows_exceeding_peak": 0,
            "p0_spearman_rho_E_vs_footprint": model["p0_spearman_rho"],
            # P3
            "pool_bw_us": primary["bw_us"],
            "pool_lat_us": primary["lat_us"],
            "pool_tail_us": primary["tail_us"],
            "predicted_m5_us": primary["predicted_us"],
            "target_m5_us": 4141.5,
            "residual_pct": primary["residual_pct"],
            "abs_residual_pct": abs(primary["residual_pct"]),
            # P3b
            "receipt_routed_residual_pct": receipts["routed"]["residual_pct"],
            "receipt_qkvo_residual_pct": receipts["qkvo"]["residual_pct"],
            "receipt_routed_m5_pct_peak": receipts["routed"]["pct_m5_peak"],
            "receipt_qkvo_m5_pct_peak": receipts["qkvo"]["pct_m5_peak"],
            # P4/P5
            "p5_families_clearing_vs_peak": len(model["p5_families_vs_peak"]),
            "p5_families_clearing_vs_best_achieved": len(model["p5_families_vs_best_achieved"]),
            "largest_headroom_family": pool[4]["family"],
            "largest_headroom_score_pct": max(p["headroom_score_pct"] for p in pool),
            "modelled_audited_m5_us": sum(p["m5_us"] for p in pool),
            # rule 70
            "rule70_routed_pct_peak_m4": 86.99069307570959,
            "rule70_best_dense_pct_peak_m4": 93.99569273659132,
            "rule70_best_achieved_pct_peak_m4": 97.36653443442448,
            "rule70_routed_gap_pp": 97.36653443442448 - 86.99069307570959,
        }
    )

    run.log(
        {
            "p0_impossibility": table(ART / "p0-impossibility.tsv"),
            "p0_e_column": table(ART / "p0-e-column.tsv"),
            "byte_audit": table(ART / "byte-audit.tsv"),
            "m5_pool_table": table(ART / "m5-pool-table.csv", ","),
            **{f"bw_{k}": v for k, v in ladder_tables(ART / "bw-ladder.tsv").items()},
        }
    )

    artifact = wandb.Artifact("fern-r101-decode-pool-model", type="analysis")
    for p in sorted(ART.iterdir()):
        artifact.add_file(str(p))
    run.log_artifact(artifact)

    print(f"run_id={run.id}\nurl={run.url}")
    run.finish()


if __name__ == "__main__":
    main()
