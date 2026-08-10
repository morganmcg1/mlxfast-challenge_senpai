#!/usr/bin/env python3
"""Publish the R106-F prefill non-GEMM census to W&B.

Metadata-only upload: every number here is replayed from the committed census
evidence under research/pr270-logs-r106f/ (see research/r106f_nongemm_arith.py
and research/prefill_census_adjudicate.py). No GPU work happens in this script.
"""

import wandb

PROJECT = "mlxfast-maple"
ENTITY = "wandb-applied-ai-team"

WALL_MS = 548.386
M4_MMA_TFLOPS = 8.0
M4_DRAM_GBPS = 260.2
M5_PREFILL_MS = 97.895
M5_DRAM_GBPS = 546.2

# family, fair_ms, pct_wall, excl_ms, raw_ms, concurrency, gb_bound, gb_per_s,
# pct_dram_roof, gflop, tflop_per_s, pct_mma_roof, arithmetic_intensity,
# roofline_floor_ms, headroom_ms
FAMILIES = [
    ("routed_gather_gemm", 265.440, 48.4, 265.440, 265.440, 1.00, 18.968, 71.5, 27, 979.3, 3.69, 46.1, 51.6, 122.41, 143.03),
    ("steel_gemm_bf16", 214.513, 39.1, 212.256, 218.628, 1.02, 4.552, 21.2, 8, 1502.8, 7.01, 87.6, 330.1, 187.85, 26.66),
    ("attention_core", 28.133, 5.1, 28.133, 28.133, 1.00, 0.696, 24.7, 10, 156.8, 5.57, 69.7, 225.2, 19.60, 8.54),
    ("nvfp4_dense_qmm", 19.998, 3.6, 19.998, 19.998, 1.00, 0.652, 32.6, 13, 122.4, 6.12, 76.5, 187.7, 15.30, 4.70),
    ("elementwise", 4.710, 0.9, 4.698, 4.721, 1.00, 1.632, 346.5, 133, None, None, None, None, None, 0.0),
    ("qk_norm_rope", 4.194, 0.8, 4.191, 4.197, 1.00, 0.768, 183.1, 70, None, None, None, None, 2.95, 1.24),
    ("sort_scatter", 2.633, 0.5, 2.633, 2.633, 1.00, 1.134, 430.7, 166, None, None, None, None, None, 0.0),
    ("moe_tail", 2.539, 0.5, 2.539, 2.539, 1.00, 0.878, 345.8, 133, None, None, None, None, None, 0.0),
    ("rms_norm", 1.714, 0.3, 1.714, 1.735, 1.01, 0.497, 290.0, 111, None, None, None, None, None, 0.0),
    ("router", 0.673, 0.1, 0.673, 0.673, 1.00, 0.012, 17.8, 7, None, None, None, None, None, 0.0),
    ("lm_head", 0.667, 0.1, 0.667, 0.667, 1.00, 0.959, 1437.8, 553, None, None, None, None, None, 0.0),
    ("other", 0.311, 0.1, 0.311, 0.311, 1.00, 0.211, 678.5, 261, None, None, None, None, None, 0.0),
    ("MIXED", 0.022, 0.0, 0.022, 0.000, None, 0.000, None, None, None, None, None, None, None, None),
    ("GPU-idle (unattributed)", 2.839, 0.5, None, None, None, None, None, None, None, None, None, None, None, None),
]

# rank, lever, m4_ms, m5_ms, pct_score_low, pct_score_high, m5_live, note
TRIAGE = [
    (1, "fold per-head softplus gate into o_proj prologue (g2_Multiply, 40 calls)",
     1.328, 0.633, 0.164, 0.239, True,
     "straddles the 0.53-0.77 ms promotion bar; inside cross-session drift"),
    (2, "fold shared-expert silu-product into gather-GEMM epilogue (39 of 77 calls)",
     0.776, 0.370, 0.096, 0.140, True, "below the bar on its own"),
    (3, "both levers together", 2.104, 1.002, 0.260, 0.379, True,
     "only combination that clears the bar; two GEMM-epilogue edits"),
    (0, "g2_copy strided-view removal (76 calls, 1.689 ms M4)",
     1.689, 0.0, 0.0, 0.0, False,
     "M5-dead: fuse_swiglu epilogue already deletes it at gen>=17"),
    (0, "SwiGLU into gather-GEMM epilogue", 0.0, 0.0, 0.0, 0.0, False,
     "already shipped on M5 (fp_quantized_nax.h fuse_swiglu)"),
    (0, "weighted combine into moe_tail", 0.0, 0.0, 0.0, 0.0, False,
     "already fused (laguna_prefill_sorted_moe_tail_bf16_v1)"),
]


def main() -> None:
    run = wandb.init(
        entity=ENTITY,
        project=PROJECT,
        name="r106f-prefill-nongemm-census",
        job_type="census",
        tags=["r106-f", "prefill", "census", "maple-tanjiro", "pr620",
              "measurement-only", "N-GEMM-DOMINATES"],
        notes=("R106-F prefill non-GEMM census. Measurement-only round: the "
               "submitted surface is byte-identical to the assignment base. "
               "Report: research/maple-tanjiro-r106f-prefill-nongemm-census.md"),
        config={
            "assignment_id": "maple-r106-f-prefill-nongemm-census",
            "revision_id": "r106-f-rev1",
            "pr_number": 620,
            "student": "maple-tanjiro",
            "base_sha": "9d424c167eae0a98e4c8c03e57be2f937ae0744a",
            "assignment_head_sha": "9556689e37cc8066aa01975f9bdfe6d96584bb67",
            "host_chip": "Apple M4 Pro",
            "host_cpu_count": 14,
            "host_ram_gib": 48,
            "host_os": "macOS 26.5.2 (25F84)",
            "apple_gpu_generation": 16,
            "nax_available": False,
            "expert_aligned_gather_active": False,
            "expert_aligned_gather_blocker": "lagunaNAXAvailable requires GPU gen >= 17",
            "gather_kernel_observed": ("nvfp4_gather_qmm_rhs_nt_bfloat16_t_gs_16_b_4"
                                      "_bm_16_bn_32_bk_32_wm_1_wn_2"
                                      "_align_M_t_align_N_t_align_K_t"),
            "prefill_tokens": 512,
            "layers_total": 40,
            "layers_moe_full_length": 38,
            "layers_attention_full_length": 39,
            "hidden_size": 2048,
            "moe_intermediate": 512,
            "moe_experts": 256,
            "moe_top_k": 8,
            "q_heads_full": 48,
            "q_heads_sliding": 64,
            "kv_heads": 8,
            "head_dim": 128,
            "sliding_window": 512,
            "m4_mma_bf16_tflops": M4_MMA_TFLOPS,
            "m4_mma_ceiling_provenance": ("first principles 20 cores x 256 FLOP/clk x "
                                          "1.55-1.6 GHz; host_flop_ceiling.swift 28.76 "
                                          "rejected (CSE collapses 4 MMAs into 1)"),
            "m4_dram_gb_per_s": M4_DRAM_GBPS,
            "m4_machine_balance_flop_per_byte": 30.7,
            "m5_dram_gb_per_s": M5_DRAM_GBPS,
            "m5_prefill_ms_reference": M5_PREFILL_MS,
            "census_reps": 8,
            "census_top": 400,
            "census_split": 1,
            "gpuprof_records": 15313,
            "command_buffers": 1066,
            "dispatches": 1222,
            "worker_sha256": "1bbe7cb7fabdc1a6799ff234611733d9416a132a1c73738ca9f0c2d896f06c9a",
            "worker_bytes": 49209912,
            "receipts_consumed": 0,
            "candidate_probes_run": 0,
            "candidate_probes_allowed": 1,
        },
    )

    fam_table = wandb.Table(columns=[
        "family", "fair_ms", "pct_wall", "exclusive_ms", "raw_ms", "concurrency",
        "gb_bound", "gb_per_s", "pct_dram_roof", "gflop", "tflop_per_s",
        "pct_mma_roof", "arithmetic_intensity", "roofline_floor_ms", "headroom_ms",
    ])
    for row in FAMILIES:
        fam_table.add_data(*row)

    triage_table = wandb.Table(columns=[
        "rank", "lever", "m4_ms", "m5_ms", "pct_score_low", "pct_score_high",
        "m5_live", "note",
    ])
    for row in TRIAGE:
        triage_table.add_data(*row)

    run.log({
        "prefill_family_census": fam_table,
        "nongemm_triage": triage_table,
    })

    run.summary.update({
        # timing spine
        "prefill_wall_ms": WALL_MS,
        "prefill_warm_median_ms": 548.428,
        "prefill_load_s": 42.0,
        "prefill_warm_cv_pct": 0.0299,
        "busy_sum_pct_of_wall_after_arange_drop": 100.2,
        "busy_union_ms": 545.547,
        "gpu_idle_ms": 2.839,
        "gpu_idle_pct": 0.52,
        "serial_on_gpu": True,
        # headline partition
        "steel_gemm_ms": 214.513,
        "steel_gemm_pct": 39.12,
        "non_steel_gemm_pct": 60.88,
        "non_steel_gemm_ms": 333.873,
        "other_matmul_pct": 52.05,
        "attention_core_pct": 5.13,
        "true_non_matmul_glue_ms": 17.463,
        "true_non_matmul_glue_pct": 3.18,
        "matmul_three_family_pct": 91.17,
        "matmul_plus_attention_pct": 96.30,
        "non_mma_glue_plus_idle_pct": 3.70,
        "nongemm_framing_inflation_factor": 19.0,
        # glue physics
        "glue_gb_bound": 6.091,
        "glue_nominal_headroom_ms_m4": 1.87,
        "glue_nominal_headroom_ms_m5": 0.89,
        "glue_dram_addressable_headroom_ms_m4": 1.24,
        "glue_dram_addressable_headroom_ms_m5": 0.59,
        "glue_dram_addressable_pct_score_low": 0.153,
        "glue_dram_addressable_pct_score_high": 0.224,
        "promotion_bar_ms_low": 0.53,
        "promotion_bar_ms_high": 0.77,
        # M4 -> M5 non-transfer
        "m4_only_glue_ms": 2.445,
        "m4_only_glue_pct_of_glue": 14.0,
        "m5_relevant_glue_ms_m4_scale": 15.018,
        "m5_relevant_glue_ms": 7.154,
        "m5_relevant_glue_pct_of_m5_prefill": 7.31,
        # top candidate
        "top_candidate": "fold per-head softplus gate into o_proj prologue",
        "top_candidate_m4_ms": 1.328,
        "top_candidate_m5_ms": 0.633,
        "top_candidate_pct_score_low": 0.164,
        "top_candidate_pct_score_high": 0.239,
        "top_candidate_clears_bar": False,
        "gather_headroom_vs_top_candidate_ratio": 226.0,
        # verdict
        "verdict": "N-GEMM-DOMINATES",
        "stopping_rule": "census complete + N-GEMM-DOMINATES fired",
        "submitted_surface_diff_bytes": 0,
    })

    print("wandb run id:", run.id)
    print("wandb run url:", run.url)
    run.finish()
    print("state: finished")


if __name__ == "__main__":
    main()
