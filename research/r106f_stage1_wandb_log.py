#!/usr/bin/env python3
"""Publish the R106-F' paired prefill speedup decomposition to W&B.

Metadata-only upload. Every number is replayed from committed evidence under
research/pr270-logs-r106f/ (stage0.calib.log, stage0.arith.log,
census.base.split1.log, census.cand.split1.log, stage1.paired.log). No GPU work
happens in this script.

Revision r106-f-rev2. Receipts consumed: 0.
"""

import wandb

PROJECT = "mlxfast-maple"
ENTITY = "wandb-applied-ai-team"

# --- Stage 0: clean (uninstrumented) ABBA walls on M4 Pro -------------------
S0_BASE_PREFILL_MS = 611.8590
S0_CAND_PREFILL_MS = 546.4080
S0_BASE_DECODE_MS = 23.0340
S0_CAND_DECODE_MS = 8.1240

# --- Ranked M5 anchors [M5-RCPT] -------------------------------------------
M5_BASE_DECODE_US = 13855.01
M5_CAND_DECODE_US = 4893.71
M5_BASE_PREFILL_MS = 190.706
M5_CAND_PREFILL_MS = 96.149

# stage, base_ms, base_pct, cand_ms, cand_pct, ratio, near_one, klass, live
STAGES = [
    ("B NVFP4 expert GEMM + epilogue", 238.025, 39.17, 256.290, 46.73, 0.929, True, 3, False),
    ("A dense BF16 attn proj (q,k,v,o,g)", 236.054, 38.85, 214.488, 39.11, 1.101, True, 2, True),
    ("C routing (sort/scatter/gather)", 65.773, 10.82, 40.287, 7.35, 1.633, False, None, None),
    ("D attention core (SDPA)", 28.777, 4.74, 22.946, 4.18, 1.254, False, None, None),
    ("F elementwise glue", 23.418, 3.85, 4.711, 0.86, 4.971, False, None, None),
    ("E norm + RoPE", 8.173, 1.35, 5.906, 1.08, 1.384, False, None, None),
    ("I GPU idle", 5.725, 0.94, 2.862, 0.52, 2.000, False, None, None),
    ("G lm_head + argmax", 1.697, 0.28, 0.952, 0.17, 1.783, False, None, None),
    ("TOTAL", 607.642, 100.00, 548.442, 100.00, 1.108, False, None, None),
]

# stage, base_ms, base_pct, cand_ms, cand_pct, ratio  (arangeuint32 -> stage B)
SENSITIVITY = [
    ("B NVFP4 expert GEMM + epilogue", 263.813, 43.42, 294.538, 53.70, 0.896),
    ("A dense BF16 attn proj (q,k,v,o,g)", 236.054, 38.85, 214.488, 39.11, 1.101),
    ("C routing (sort/scatter/gather)", 39.984, 6.58, 2.039, 0.37, 19.614),
    ("TOTAL", 607.642, 100.00, 548.442, 100.00, 1.108),
]

# family, base_excl_ms, cand_excl_ms, excl_ratio, base_raw_ms, cand_raw_ms,
# raw_ratio, base_gb, cand_gb
EXCLUSIVE = [
    ("steel_gemm_bf16", 208.877, 212.228, 0.984, 230.303, 218.533, 1.054, 4.658, 4.552),
    ("routed_gather_gemm", 15.726, 201.965, 0.078, 336.453, 265.444, 1.268, 20.122, 18.968),
    ("nvfp4_dense_qmm", 0.814, 20.007, 0.041, 183.365, 20.007, 9.165, 0.458, 0.652),
    ("sort_scatter", 3.501, 2.613, 1.340, 180.334, 76.612, 2.354, 2.534, 1.135),
    ("elementwise", 11.837, 4.695, 2.521, 36.594, 4.728, 7.740, 3.575, 1.632),
    ("attention_core", 28.727, 17.746, 1.619, 28.828, 28.146, 1.024, 0.713, 0.696),
    ("rms_norm", 6.160, 1.725, 3.571, 6.175, 1.747, 3.535, 0.695, 0.497),
    ("qk_norm_rope", 1.704, 4.159, 0.410, 2.449, 4.203, 0.583, 0.713, 0.768),
    ("moe_tail", 0.000, 2.555, None, 0.000, 2.555, None, 0.000, 0.878),
    ("router", 0.000, 0.674, None, 0.000, 0.673, None, 0.000, 0.012),
    ("lm_head", 0.019, 0.666, 0.029, 0.019, 0.666, 0.029, 0.000, 0.959),
    ("other", 1.678, 0.309, 5.430, 1.678, 0.309, 5.430, 0.411, 0.211),
]

# projection, N, K, gflop_per_layer, pct_of_stage_A_flops, m5_route,
# darkbloom_tile_fires, identical_in_both_trees
PROJECTIONS = [
    ("q_proj", 6144, 2048, 12.885, 42.71, "regular nax fused", False, True),
    ("o_proj", 2048, 6144, 12.885, 42.71, "nax split-K", True, False),
    ("k_proj", 1024, 2048, 2.147, 7.12, "regular nax fused", False, True),
    ("v_proj", 1024, 2048, 2.147, 7.12, "regular nax fused", False, True),
    ("g_proj", 48, 2048, 0.101, 0.33, "nax split-K", False, True),
]

# slice, m5_ms_above_floor, pct_score_partial, pct_score_total, clears_3sigma
CEILINGS = [
    ("stage A all above-floor", 12.30, 3.20, 4.65, True),
    ("untouched q/k/v/g sub-slice (57.29%)", 7.06, 1.84, 2.67, True),
    ("k/v-only sub-slice (14.24%)", 1.75, 0.46, 0.66, True),
]


def main():
    run = wandb.init(
        entity=ENTITY,
        project=PROJECT,
        name="r106f-prefill-speedup-decomposition",
        job_type="census",
        tags=[
            "r106-f-rev2",
            "prefill",
            "paired-baseline",
            "stage0-calibration",
            "V-UNTOUCHED",
            "m4-pro",
            "receipt-free",
        ],
        notes=(
            "R106-F' rev2. First measurement in this campaign of the pinned ranked "
            "baseline tree (15852ee5) against HEAD, same host/session, on Apple M4 Pro "
            "(GPU gen 16 => nax unavailable). Decode reproduces the ranked 2.8312x to "
            "+0.15%; prefill does NOT reproduce (1.1198x vs 1.9834x, -43.5%). Paired "
            "per-family prefill census attributes 78.02% of baseline M4 prefill time to "
            "stages with ~1.0x speedup (A dense BF16 attn proj 1.101x, B NVFP4 expert "
            "GEMM 0.929x). B is a class-3 M4 artifact (nax-gated). A is class 2 (never "
            "touched): 57.29% of its FLOPs provably run the identical kernel with "
            "identical tiles in both trees on M5. Verdict V-UNTOUCHED. Receipts: 0."
        ),
        config={
            "assignment_id": "maple-r106-f-prefill-nongemm-census",
            "revision_id": "r106-f-rev2",
            "pr_number": 620,
            "student": "maple-tanjiro",
            "base_sha": "3241e5e55b17a1902cac47b01f186f7281391ca5",
            "baseline_commit_ranked": "15852ee52858def42ddd4f32bca7e59d275e020e",
            "host": "Apple M4 Pro, 14 CPU, 48 GiB, macOS 26.5.2 (25F84)",
            "apple_gpu_generation": 16,
            "nax_available": False,
            "ranked_host": "Apple M5 Max, 128 GiB (gen 17, arch suffix 's')",
            "receipts_consumed": 0,
            # measurement protocol
            "stage0_order": "cand base base cand (ABBA)",
            "stage0_reps": 6,
            "stage0_decode_steps": 40,
            "stage0_settle_s": 20,
            "stage0_gpu_profile": False,
            "stage1_gpu_profile": True,
            "stage1_replicates": 1,
            "startup_memory_profile": "full",
            "prefill_tokens": 512,
            "near_band_lo": 0.85,
            "near_band_hi": 1.18,
            # score conversion conventions (both, named)
            "pct_score_per_ms_partial": 0.2592,
            "pct_score_per_ms_total": 0.3781,
            "sigma_delta_ms": 0.4497,
            "three_sigma_bar_ms": 1.35,
        },
    )

    stage_tbl = wandb.Table(
        columns=[
            "stage", "base_ms", "base_pct", "cand_ms", "cand_pct", "ratio",
            "near_one", "class", "live_under_rule_90",
        ],
        data=[list(r) for r in STAGES],
    )
    sens_tbl = wandb.Table(
        columns=["stage", "base_ms", "base_pct", "cand_ms", "cand_pct", "ratio"],
        data=[list(r) for r in SENSITIVITY],
    )
    excl_tbl = wandb.Table(
        columns=[
            "family", "base_excl_ms", "cand_excl_ms", "excl_ratio",
            "base_raw_ms", "cand_raw_ms", "raw_ratio", "base_gb", "cand_gb",
        ],
        data=[list(r) for r in EXCLUSIVE],
    )
    proj_tbl = wandb.Table(
        columns=[
            "projection", "N", "K", "gflop_per_layer", "pct_of_stage_A_flops",
            "m5_route", "darkbloom_tile_fires", "identical_in_both_trees",
        ],
        data=[list(r) for r in PROJECTIONS],
    )
    ceil_tbl = wandb.Table(
        columns=[
            "slice", "m5_ms_above_floor", "pct_score_partial",
            "pct_score_total", "clears_3sigma_bar",
        ],
        data=[list(r) for r in CEILINGS],
    )

    run.log({
        "prefill_stage_decomposition": stage_tbl,
        "prefill_stage_sensitivity_arange": sens_tbl,
        "exclusive_time_cross_check": excl_tbl,
        "stage_a_projection_routing": proj_tbl,
        "stage3_ceilings": ceil_tbl,
    })

    run.summary.update({
        # ---- Stage 0: the decisive calibration ----
        "s0_base_prefill_ms": S0_BASE_PREFILL_MS,
        "s0_cand_prefill_ms": S0_CAND_PREFILL_MS,
        "s0_base_decode_ms": S0_BASE_DECODE_MS,
        "s0_cand_decode_ms": S0_CAND_DECODE_MS,
        "m4_decode_speedup": 2.8353,
        "m4_prefill_speedup": 1.1198,
        "m5_decode_speedup": 2.8312,
        "m5_prefill_speedup": 1.9834,
        "decode_reproduction_error_pct": 0.15,
        "prefill_reproduction_error_pct": -43.54,
        "decode_reproduces": True,
        "prefill_reproduces": False,
        "m4_to_m5_factor_base_decode": 1.6626,
        "m4_to_m5_factor_cand_decode": 1.6601,
        "m4_to_m5_factor_base_prefill": 3.2084,
        "m4_to_m5_factor_cand_prefill": 5.6831,
        "m4_to_m5_prefill_cand_over_base": 1.771,
        "implied_cs_m5": 2.590188,
        "implied_cs_m4": 2.24784,
        "asymmetry_stat_m5_pct": 8.90,
        "asymmetry_stat_m4_pct": 23.23,
        "prize_log_gain_pct": 8.894,
        "prize_multiplicative_pct": 9.302,
        # ---- Stage 1 headline ----
        "headline_near_one_baseline_share_pct": 78.02,
        "headline_near_one_baseline_ms": 474.079,
        "headline_sensitivity_share_pct": 82.26,
        "headline_sensitivity_ms": 499.867,
        "base_instrumented_wall_ms": 607.644,
        "cand_instrumented_wall_ms": 548.441,
        "base_busy_union_pct": 99.1,
        "cand_busy_union_pct": 99.5,
        "base_command_buffers": 2126,
        "cand_command_buffers": 1066,
        "command_buffers_delta_pct": -49.9,
        "base_dispatches": 2637,
        "cand_dispatches": 1222,
        "dispatches_delta_pct": -53.7,
        "base_bound_gib": 31.552,
        "cand_bound_gib": 28.834,
        "bound_bytes_delta_pct": -8.6,
        "steel_gemm_bf16_n_base": 401,
        "steel_gemm_bf16_n_cand": 392,
        "attention_core_n_base": 40,
        "attention_core_n_cand": 40,
        "routed_gather_gemm_n_base": 117,
        "routed_gather_gemm_n_cand": 76,
        "ledger_closure_base_ms": -0.002,
        "ledger_closure_cand_ms": 0.001,
        "base_mixed_redistributed_ms": 97.026,
        "cand_mixed_redistributed_ms": 0.022,
        "instrument_cost_pct": 1.0,
        # ---- the exclusive-time cross-check that carries Stage 2 ----
        "stage_a_exclusive_ratio": 0.984,
        "stage_a_exclusive_base_ms": 208.877,
        "stage_a_exclusive_cand_ms": 212.228,
        # ---- cross-machine share check (circular; flagged) ----
        "stage_a_cand_share_m4_pct": 39.11,
        "stage_a_cand_share_m5_proj_pct": 39.45,
        "stage_a_cand_share_agreement_pct": 0.87,
        "stage_a_cand_share_check_is_circular": True,
        "proj_divergent_transfer_factor": 5.66,
        "overall_wall_factor_m4_to_m5": 5.70,
        "stage_a_base_share_m4_pct": 38.85,
        "stage_a_base_share_m5_proj_pct": 19.89,
        "m4_inflates_baseline_shares": True,
        # ---- Stage 2 ----
        "stage_a_class": 2,
        "stage_a_live_under_rule_90": True,
        "stage_b_class": 3,
        "stage_b_dead_on_arrival": True,
        "stage_a_untouched_flop_share_pct": 57.29,
        "stage_a_touched_projection": "o_proj",
        "stage_a_gflop_total": 1206.6,
        "stage_a_gflop_discrepancy_vs_probe_pct": 21.0,
        "prefill_nax_divergent_pct": 94.3,
        "decode_nax_invariant": True,
        # ---- Stage 3 ----
        "top_class2_item": (
            "shape-aware tile selection in steel_matmul_regular_axpby_nax "
            "(matmul.cpp:213-222) for narrow-N k/v_proj"
        ),
        "top_item_site": "Vendor/mlx-swift/.../backend/metal/matmul.cpp:213-222",
        "top_item_precedent": "darkbloom_steel_prefill_tile at matmul.cpp:674-677 (o_proj)",
        "kv_threadgroups_at_bn128": 64,
        "kv_threadgroups_at_bn64": 128,
        "stage_a_m5_proj_ms": 37.93,
        "stage_a_m5_floor_ms": 25.63,
        "stage_a_above_floor_ms": 12.30,
        "untouched_subslice_ms": 7.06,
        "kv_subslice_ms": 1.75,
        "bit_exact_bm_bn_wm_wn": True,
        "bit_exact_bk_or_splitk_partitions": False,
        "f1_fused_qkv_proposed": False,
        # ---- verdict + provenance ----
        "verdict": "V-UNTOUCHED",
        "verdict_qualified": True,
        "stopping_rule": "stages 1-2 complete + top class-2 item desk-priced",
        "frontier_strategy_consult_succeeded": False,
        "frontier_strategy_consult_task": "563209e9-b073-5aa7-916f-e6585fd3da2d",
        "split0_replicate_missing": True,
        "m5_paired_census_available": False,
        "submitted_surface_diff_bytes": 0,
        "deliverable": (
            "research/maple-tanjiro-r106f-prefill-speedup-decomposition.md"
        ),
    })

    print("wandb run id:", run.id)
    print("wandb run url:", run.url)
    run.finish()
    print("state: finished")


if __name__ == "__main__":
    main()
