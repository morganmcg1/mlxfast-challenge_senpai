#!/usr/bin/env python3
"""Log the r105-E decode bandwidth-efficiency verdict to W&B.

Reads the two committed r105-E artifacts (the A3 pattern-bandwidth probe JSON
and the A1/A4 per-family bandwidth ledger CSV) and publishes one run in
wandb-applied-ai-team/mlxfast-maple.

This is a census/analysis result, not a timed experiment: zero bytes changed
under Sources/ or Vendor/, and no official receipt was spent. Per-kernel label
microseconds obey rule 82b (shape only, never magnitude).
"""

import csv
import json
import os
import pathlib
from collections import defaultdict

import wandb

ROOT = pathlib.Path(__file__).resolve().parent
ART = ROOT / "artifacts" / "fern-r105e"
CSV_PATH = ART / "family-bandwidth-ledger.csv"
PROBE_PATH = ART / "pattern-bandwidth.json"
REPORT_PATH = ROOT / "maple-fern-r105e-decode-bandwidth-efficiency.md"

PROJECT = "mlxfast-maple"
ENTITY = "wandb-applied-ai-team"

PCT1_US = 65.67  # 1% of cs, in M5 decode microseconds per step


def load_ledger():
    with CSV_PATH.open() as fh:
        return list(csv.DictReader(fh))


def f(row, key):
    v = row[key]
    return float(v) if v not in ("", None) else None


def i(row, key):
    v = row[key]
    return int(v) if v not in ("", None) else None


def main():
    probe = json.loads(PROBE_PATH.read_text())
    rows = load_ledger()

    # A3 occupancy curve: best achieved GB/s at each total grid size.
    best_by_grid = defaultdict(float)
    for m in probe["measurements"]:
        if m["pattern"].startswith("stream"):
            best_by_grid[m["grid_threads"]] = max(
                best_by_grid[m["grid_threads"]], m["achieved_gbs"]
            )
    curve = sorted(best_by_grid.items())

    step_bytes = sum(i(r, "bytes_unique") for r in rows)
    label_total = sum(f(r, "label_us_m4") or 0.0 for r in rows)
    surplus_rows = [r for r in rows if (f(r, "surplus_us_m4") or 0.0) > 0]
    surplus_total = sum(f(r, "surplus_us_m4") for r in surplus_rows)
    bw_rows = [r for r in rows if r["regime"] == "BANDWIDTH"]
    lat_rows = [r for r in rows if r["regime"] == "LATENCY"]
    bw_surplus = sum(max(0.0, f(r, "surplus_us_m4") or 0.0) for r in bw_rows)
    m5_penalty = sum(f(r, "m5_occupancy_penalty_us") or 0.0 for r in bw_rows)
    lat_byte_pct = sum(f(r, "pct_of_step_bytes") for r in lat_rows)

    cfg = {
        "assignment_id": "maple-r105-e-decode-bandwidth-efficiency",
        "revision_id": "r105-e-rev1",
        "student": "maple-fern",
        "pr_number": 609,
        "branch": "maple-fern/r105-decode-bandwidth-efficiency",
        "base_sha": "1b312d24828f1c90ba80b41b6399e8e2c2f46bbd",
        "zero_byte_base_sha": "9274c2923e38c9bc3925cb6409fade962ad571de",
        "phase": "A_only_no_official_receipts",
        "host": "M4_Pro_20core_48GiB_applegpu_g16s",
        "ranked_host": "M5_Max_40core_128GiB",
        "trace_source": "105-C SPLIT=1 dispatch.tsv + r105-D byte census",
        "sources_vendor_bytes_changed": 0,
        "rule_82b": "label microseconds are shape-only, never magnitude",
        "one_pct_of_cs_us": PCT1_US,
        "effort_bar_us": 32.8,
        "record_bar_us": 94.4,
        "a5_completed": False,
        "a5_skip_reason": "assignment stopping rule: no family >= 32.8 us defensible surplus after A3",
    }

    summary = {
        # --- primary metric ---
        "primary/decode_recoverable_bandwidth_surplus_pct_of_cs": 1.548,
        "primary/baseline_pct_of_cs": 10.25,
        "primary/delta_pct_of_cs": 1.548 - 10.25,
        "primary/tightened_best_estimate_pct_of_cs": 0.545,
        "primary/tightened_best_estimate_us": 35.8,
        "primary/upper_bound_us": 101.6,
        "primary/verdict": "N-1",
        "primary/contradiction_flavour": "N-3",
        # --- A4 apportionment of the 10.25% (673.5 us/step on M5) ---
        "a4/total_us": 673.5,
        "a4/total_pct_of_cs": 10.257,
        "a4/D_pattern_us": 0.0,
        "a4/D_pattern_pct_of_cs": 0.0,
        "a4/D_pattern_share": 0.0,
        "a4/D_measurement_axis_us": 126.4,
        "a4/D_measurement_axis_pct_of_cs": 1.925,
        "a4/D_measurement_axis_share": 0.188,
        "a4/B_byte_model_us": 0.0,
        "a4/B_byte_model_pct_of_cs": 0.0,
        "a4/B_byte_model_share": 0.0,
        "a4/P_parallelism_us": 101.6,
        "a4/P_parallelism_pct_of_cs": 1.548,
        "a4/P_parallelism_share": 0.151,
        "a4/L_fixed_non_dram_us": 445.5,
        "a4/L_fixed_non_dram_pct_of_cs": 6.784,
        "a4/L_fixed_non_dram_share": 0.662,
        # --- A1 mixed-session reconciliation ---
        "a1/assignment_achieved_gbs_mixed": 210.5,
        "a1/assignment_gap_points_mixed": 12.9,
        "a1/matched_wall_axis_step_us_m4": 8233.0,
        "a1/matched_wall_axis_gbs": 203.0,
        "a1/matched_wall_axis_pct_of_266_3": 76.23,
        "a1/matched_gap_points": 10.07,
        "a1/naive_parity_pct_of_cs": 8.33,
        "a1/split1_busy_inflation_x": 1.074,
        "a1/label_vs_gpu_busy_residual_us": 0.3,
        # --- Amdahl fit T = B/BW + L ---
        "amdahl/m4_wall_step_us": 8233.0,
        "amdahl/m4_busy_nonsplit_step_us": 7940.0,
        "amdahl/m4_split1_label_step_us": 8528.3,
        "amdahl/m4_dram_term_us": 6404.6,
        "amdahl/m4_wall_L_us": 1828.4,
        "amdahl/m4_wall_efficiency_pct": 77.79,
        "amdahl/m5_step_us": 4141.5,
        "amdahl/m5_dram_term_us": 2773.1,
        "amdahl/m5_L_us": 1368.4,
        "amdahl/m5_efficiency_pct": 66.96,
        "amdahl/L5_over_L4_wall": 0.748,
        "amdahl/m5_counterfactual_with_m4_L_us": 4601.5,
        "amdahl/m5_counterfactual_efficiency_pct": 60.27,
        "amdahl/m5_better_than_transfer_predicts_points": 6.69,
        # --- A3 pattern probe ---
        "a3/reference_stream_gbs_rule80": probe["reference_stream_gbs_rule80"],
        "a3/stream_peak_gbs": probe["stream_peak_gbs"],
        "a3/stream_peak_pct_of_266_3": 100.0 * probe["stream_peak_gbs"] / 266.3,
        "a3/stream_tg64_peak_gbs": probe["stream_tg64_peak_gbs"],
        "a3/nvfp4_qmv_faithful_gbs": probe["nvfp4_qmv_faithful_gbs"],
        "a3/nvfp4_pct_of_266_3": 100.0 * probe["nvfp4_qmv_faithful_gbs"] / 266.3,
        "a3/nvfp4_pct_of_stream_peak": (
            100.0 * probe["nvfp4_qmv_faithful_gbs"] / probe["stream_peak_gbs"]
        ),
        "a3/saturation_grid_threads": 10240,
        "a3/saturation_threads_per_core": 512,
        "a3/activation_replay_amp_x": 2.88,
        "a3/activation_replay_cost_us": 0.45,
        "a3/activation_replay_cost_pct_of_step": 0.010,
        # --- A2 amplification (N-2 test) ---
        "a2/families_ge_1pct_bytes": 13,
        "a2/max_amplification_above_slc": 1.00,
        "a2/slc_estimate_mib": probe["slc_estimate_mib"],
        "a2/escape_paths": "qkv_h64, qkv_h48, oproj_h64, oproj_h48 only",
        # --- ledger rollup ---
        "ledger/families": len(rows),
        "ledger/step_bytes": step_bytes,
        "ledger/label_us_total_m4_split1_82b": round(label_total, 1),
        "ledger/aggregate_achieved_gbs": round(1e-3 * step_bytes / label_total, 2),
        "ledger/aggregate_pct_of_266_3": round(
            100.0 * (1e-3 * step_bytes / label_total) / 266.3, 2
        ),
        "ledger/pattern_ceiling_gbs": probe["nvfp4_qmv_faithful_gbs"],
        "ledger/saturated_step_floor_us_m4": 6404.6,
        "ledger/positive_surplus_us_total": round(surplus_total, 1),
        "ledger/positive_surplus_families": len(surplus_rows),
        "ledger/bandwidth_regime_surplus_us": round(bw_surplus, 1),
        "ledger/bandwidth_regime_families": len(bw_rows),
        "ledger/latency_regime_families": len(lat_rows),
        "ledger/latency_regime_pct_of_step_bytes": round(lat_byte_pct, 3),
        "ledger/m5_occupancy_penalty_us_bandwidth_only": round(m5_penalty, 1),
        # --- hypothesis outcomes ---
        "hyp/N1_no_recoverable_pool": True,
        "hyp/N2_amplification_is_the_gap": False,
        "hyp/N3_gap_is_not_dram_bound": "PARTIAL_66pct_is_fixed_non_dram_time",
        "hyp/rule_82b_admissible_for_this_question": True,
        "hyp/rule_82b_admissible_for_pricing_a_lever": False,
        # --- largest single-family lever (the stopping-rule test) ---
        "lever/largest_family": "nvfp4_qkv_h64",
        "lever/largest_family_us": 25.2,
        "lever/largest_family_pct_of_cs": 0.384,
        "lever/effort_bar_us": 32.8,
        "lever/clears_effort_bar": False,
    }

    run = wandb.init(
        entity=ENTITY,
        project=PROJECT,
        name="fern-r105e-decode-bandwidth-efficiency",
        job_type="census",
        tags=["r105-E", "maple-fern", "phase-A", "census", "no-timing", "N-1"],
        config=cfg,
        notes=(
            "Decode bandwidth-efficiency audit of the claimed 10.25%-of-cs 'recoverable "
            "bandwidth surplus'. Outcome N-1: the pool does not exist as a recoverable "
            "lever. 0% is access pattern (a faithful NVFP4 qmv replica reaches 99.2% of "
            "stream peak), 0% is the byte model, 18.8% is a busy-vs-wall measurement-axis "
            "artifact from mixing a SPLIT=1 census with a non-SPLIT busy total, <=15.1% is "
            "parallelism/occupancy, and 66.2% is fixed non-DRAM time that the trichotomy "
            "never offered as an option. No GPU timing of a candidate was run; zero bytes "
            "changed under Sources/ or Vendor/."
        ),
    )

    led = wandb.Table(
        columns=[
            "family", "n_dispatches", "bytes_unique", "pct_of_step_bytes",
            "grid_threads_per_dispatch", "threads_per_tg", "regime",
            "label_us_m4", "achieved_gbs_m4", "pct_of_266_3",
            "pct_of_pattern_ceiling", "floor_us_at_pattern_ceiling",
            "surplus_us_m4", "m5_occupancy_frac", "m5_occupancy_penalty_us",
            "m5_occupancy_penalty_pct_of_cs",
        ]
    )
    for r in sorted(rows, key=lambda x: -(f(x, "surplus_us_m4") or -1e9)):
        led.add_data(
            r["family"], i(r, "n_dispatches"), i(r, "bytes_unique"),
            f(r, "pct_of_step_bytes"), i(r, "grid_threads_per_dispatch"),
            i(r, "threads_per_tg"), r["regime"], f(r, "label_us_m4"),
            f(r, "achieved_gbs_m4"), f(r, "pct_of_266_3"),
            f(r, "pct_of_pattern_ceiling"), f(r, "floor_us_at_pattern_ceiling"),
            f(r, "surplus_us_m4"), f(r, "m5_occupancy_frac"),
            f(r, "m5_occupancy_penalty_us"), f(r, "m5_occupancy_penalty_pct_of_cs"),
        )
    run.log({"ledger/family_table": led})

    occ = wandb.Table(columns=["grid_threads", "threads_per_core_m4", "best_gbs",
                               "pct_of_266_3"])
    for g, gbs in curve:
        occ.add_data(g, g / probe["gpu_cores"], round(gbs, 2),
                     round(100.0 * gbs / 266.3, 2))
    run.log({"a3/occupancy_curve": occ})

    pat = wandb.Table(columns=["pattern", "threads_per_tg", "tg_per_core",
                               "grid_threads", "loads_in_flight", "bytes_read",
                               "us_med", "achieved_gbs", "pct_of_266_3"])
    for m in probe["measurements"]:
        pat.add_data(m["pattern"], m["threads_per_tg"], m["tg_per_core"],
                     m["grid_threads"], m["loads_in_flight"], m["bytes_read"],
                     m["us_med"], m["achieved_gbs"], m["pct_of_266_3"])
    run.log({"a3/pattern_measurements": pat})

    apport = wandb.Table(columns=["bucket", "trichotomy_letter", "us_per_step_m5",
                                  "pct_of_cs", "share_of_10_25"])
    for name, letter, us, pct, share in [
        ("access pattern", "D", 0.0, 0.000, 0.000),
        ("measurement axis (busy vs wall)", "D", 126.4, 1.925, 0.188),
        ("byte model", "B", 0.0, 0.000, 0.000),
        ("parallelism / occupancy", "P", 101.6, 1.548, 0.151),
        ("fixed non-DRAM time", "none (4th)", 445.5, 6.784, 0.662),
    ]:
        apport.add_data(name, letter, us, pct, share)
    run.log({"a4/apportionment": apport})

    for k, v in summary.items():
        run.summary[k] = v

    art = wandb.Artifact("fern-r105e-decode-bandwidth", type="census")
    art.add_file(str(CSV_PATH))
    art.add_file(str(PROBE_PATH))
    art.add_file(str(REPORT_PATH))
    run.log_artifact(art)

    print(f"run_id={run.id}")
    print(f"url={run.url}")
    run.finish()


if __name__ == "__main__":
    os.environ.setdefault("WANDB_SILENT", "false")
    main()
