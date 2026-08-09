"""Log the R92-A Stage-1 barrier-hoist inventory to W&B.

Stage 1 is a source audit plus three SPLIT=1 decode censuses; there is no
training curve. The run records the inventory as a table, the live decode
census as a table, and the ceiling arithmetic as summary scalars.
"""

import wandb

PROJECT = "wandb-applied-ai-team/mlxfast-maple"

# (label, us_per_step, n_per_step, us_per_call) from the default arm census.
CENSUS = [
    ("routed_nvfp4_swiglu_qmv_packed_top8keys_r1_bf16_v2", 1497.7, 39, 38.40),
    ("decode_nvfp4_qkv_h64_r1_v1_lm1_pw1_se1_sd1", 1340.1, 30, 44.67),
    ("oproj_act_h64_v1_lm1_pw1_sc1_se1", 1117.7, 30, 37.26),
    ("routed_shared_nvfp4_down_residual_bf16_sh_stage4_v6", 858.9, 39, 22.02),
    ("sliding_fused_attn_ring_v1", 636.0, 30, 21.20),
    ("lmhead_int5_base_coarse_delta_bf16_v1", 420.3, 1, 420.27),
    ("decode_nvfp4_qkv_h48_r1_v1_lm1_pw1_se1_sd1", 362.8, 10, 36.28),
    ("residual_rms_router_bf16_2048_rpg8_keys_v1_pf1", 312.8, 39, 8.02),
    ("oproj_act_h48_v1_lm1_pw1_sc1_se1", 301.8, 10, 30.18),
    ("shared_nvfp4_swiglu_qmv_rows1_halved_bf16_v1", 287.1, 39, 7.36),
    ("dense_gate_up_swiglu_bf16_v1", 269.4, 1, 269.39),
    ("gate_sp_h64_v1", 248.0, 30, 8.27),
    ("full_fused_attn_grow_v1", 229.7, 10, 22.97),
    ("prefill_router_tournament_ordinal_norm_active64_v2", 185.5, 39, 4.76),
    ("rmsbfloat16", 141.9, 41, 3.46),
    ("dense_down_residual_bf16_v1", 133.8, 1, 133.77),
    ("gate_sp_h48_v1", 80.2, 10, 8.02),
    ("lmhead_exact_fused_int5_sparse_refine_v1", 77.0, 1, 76.98),
    ("argmax_bfloat16", 9.0, 1, 8.98),
    ("lmhead_exact_winner_bf16_midpoint_threshold_v1", 4.7, 1, 4.69),
    ("lmhead_coarse_argmax_stage1_v5", 4.1, 1, 4.08),
    ("decode_embedding_rope_atlas_bf16_2048_v2", 3.5, 1, 3.49),
    ("gather_frontbfloat16_int32_int_2", 3.4, 1, 3.41),
    ("residual_rms_bf16_2048_v1", 2.9, 1, 2.90),
]

# (site, symbol, kernel, verdict, dispatches_per_step, hoistable)
INVENTORY = [
    ("689", "prose", "-", "prose", 0, "n/a"),
    ("911", "prose", "-", "prose", 0, "n/a"),
    ("843", "lagunaNormReductionTail", "residual_rms_router_..._pf1 + residual_rms_bf16_2048_v1", "live", 40, "yes"),
    ("847", "lagunaNormReductionTail", "same", "live", 40, "yes"),
    ("854", "lagunaNormReductionTail", "same", "live", 40, "yes"),
    ("1094", "lagunaResidualRMSNormRouterSource", "residual_rms_router_..._pf1", "live", 39, "already hoisted (#475)"),
    ("1590", "lagunaSlidingFusedAttentionKernel", "sliding_fused_attn_ring_v1", "live", 30, "yes"),
    ("1740", "lagunaSlidingFusedAttentionKernel", "sliding_fused_attn_ring_v1", "live", 30, "no (threadgroup)"),
    ("1761", "lagunaSlidingFusedAttentionKernel", "sliding_fused_attn_ring_v1", "live", 30, "no (threadgroup)"),
    ("1764", "lagunaSlidingFusedAttentionKernel", "sliding_fused_attn_ring_v1", "live", 30, "no (threadgroup)"),
    ("2030", "lagunaFullFusedAttentionKernel", "full_fused_attn_grow_v1", "live", 10, "yes"),
    ("2224", "lagunaFullFusedAttentionKernel", "full_fused_attn_grow_v1", "live", 10, "no (threadgroup)"),
    ("2245", "lagunaFullFusedAttentionKernel", "full_fused_attn_grow_v1", "live", 10, "no (threadgroup)"),
    ("2248", "lagunaFullFusedAttentionKernel", "full_fused_attn_grow_v1", "live", 10, "no (threadgroup)"),
    ("3336", "lagunaFusedQKVProjectionSource", "fused_norm_qkv_projection_*", "dead", 0, "no"),
    ("3389", "lagunaFusedQKVProjectionSource", "fused_norm_qkv_projection_*", "dead", 0, "no"),
    ("3930", "lagunaGatedAffineOProjSource", "gated_affine_oproj_qmv_i8g32_*", "dead", 0, "no"),
    ("4203", "lagunaGatedAffineOProjNVFP4Source gateSetup", "(oproj_act_*)", "not emitted", 0, "no"),
    ("4990", "lagunaNormAffineQKVSource", "norm_affine_qkv_qmv_i8g32_*", "dead", 0, "no"),
    ("5042", "lagunaNormAffineQKVBody", "norm_affine_qkv_qmv_i8g32_*", "dead", 0, "no"),
    ("5056", "lagunaNormAffineQKVBody", "norm_affine_qkv_qmv_i8g32_*", "dead", 0, "no"),
    ("5065", "lagunaNormAffineQKVBody", "norm_affine_qkv_qmv_i8g32_*", "dead", 0, "no"),
    ("5243", "lagunaNormAffineQKVPrefetchSource", "norm_affine_qkv_qmv_i8g32_*", "dead", 0, "no"),
    ("5257", "lagunaNormAffineQKVPrefetchSource", "norm_affine_qkv_qmv_i8g32_*", "dead", 0, "no"),
    ("5266", "lagunaNormAffineQKVPrefetchSource", "norm_affine_qkv_qmv_i8g32_*", "dead", 0, "no"),
    ("8066", "lagunaRoutedDownReduceKernel", "routed_nvfp4_down_reduce_bf16_v2", "dead", 0, "no"),
    ("8309", "lagunaRoutedSharedDownResidualSource", "routed_shared_..._sh_stage4_v6", "live", 39, "yes"),
    ("8437", "lagunaRoutedSharedDownResidualStagedKernel", "routed_shared_... (non-sh twin)", "dead", 0, "no"),
]

# (arm, env value, kernel label, us_per_step, us_per_call)
ARMS = [
    ("A1 hoisted", 1, "residual_rms_router_bf16_2048_rpg8_keys_v1_pf1", 312.8, 8.02),
    ("A0 unhoisted", 0, "residual_rms_router_bf16_2048_rpg8_keys_v1", 318.5, 8.17),
    ("A5 placement control", 5, "residual_rms_router_bf16_2048_rpg8_keys_v1_pf1c", 323.5, 8.29),
]


def main() -> None:
    run = wandb.init(
        entity="wandb-applied-ai-team",
        project="mlxfast-maple",
        name="r92-a-stage1-barrier-hoist-inventory",
        job_type="audit",
        tags=["r92-a", "stage1", "barrier-hoist", "null-result", "m4pro"],
        config={
            "assignment_id": "maple-r92-a-barrier-hoist-generalization",
            "revision_id": "r92-a-rev1",
            "pr": 488,
            "base_sha": "8486638578a283de40369172f68c3a4d2d6a5365",
            "branch": "maple-nezuko/r92-barrier-hoist-generalization",
            "host": "M4 Pro applegpu_g16s (directional; ranked host is M5 Max)",
            "probe": "decode_probe.py --steps 80 --profile, DARKBLOOM_GPU_PROFILE_SPLIT=1",
            "stage_reached": 1,
            "stage2_entered": False,
            "stage3_entered": False,
            "editable_bytes_changed": 0,
        },
    )

    run.log(
        {
            "census/decode_labels": wandb.Table(
                columns=["kernel", "us_per_step", "dispatches_per_step", "us_per_call"],
                data=[list(r) for r in CENSUS],
            ),
            "inventory/barrier_sites": wandb.Table(
                columns=["line", "symbol", "kernel", "reachability", "dispatches_per_step", "hoistable"],
                data=[list(r) for r in INVENTORY],
            ),
            "router_arms/split1": wandb.Table(
                columns=["arm", "env_value", "kernel_label", "us_per_step", "us_per_call"],
                data=[list(r) for r in ARMS],
            ),
        }
    )

    run.summary.update(
        {
            # decode census
            "decode/wall_us_per_step": 9768.0,
            "decode/gpu_busy_us_per_step": 8528.0,
            "decode/dispatches_per_step": 406,
            "decode/distinct_labels": 24,
            "decode/teacher_forced_divergences": 0,
            # inventory outcome
            "sites/audited_total": 28,
            "sites/prose_excluded": 2,
            "sites/code": 26,
            "sites/dead_or_not_emitted": 16,
            "sites/live_not_hoistable": 6,
            "sites/already_hoisted_r475": 1,
            "sites/qualifying_edit_points": 5,
            "sites/qualifying_instantiations": 6,
            "sites/qualifying_material": 4,
            # coverage
            "coverage/material_us_per_step": 2037.4,
            "coverage/material_share_of_busy_pct": 23.9,
            "coverage/material_calls_per_step": 118,
            "coverage/no_barrier_trio_us_per_step": 4620.1,
            "coverage/no_barrier_trio_share_pct": 54.2,
            # calibration from #475 (paired ABBA nat, admissible)
            "calib/r475_nat_us_per_step": -6.85,
            "calib/r475_us_per_call": 0.1756,
            "calib/r475_frac_of_kernel_pct": 2.19,
            "calib/r475_phase_ceiling_us_per_step": 12.80,
            "calib/r475_capture_pct": 54.0,
            # ceiling estimators
            "ceiling/estimator_a_us_per_step": 20.3,
            "ceiling/estimator_b_captured_us_per_step": 24.1,
            "ceiling/estimator_b_uncaptured_us_per_step": 44.6,
            "ceiling/h1_bar_us_per_step": 80.0,
            "ceiling/estimator_a_pct_of_bar": 25.0,
            "ceiling/estimator_b_uncaptured_pct_of_bar": 56.0,
            "ceiling/required_us_per_call_for_h1": 0.678,
            "ceiling/required_multiple_of_router_win": 3.9,
            # score conversion
            "score/pct_per_us_per_step": 0.015280,
            "score/estimator_a_pct": 0.310,
            "score/h1_bar_pct": 1.222,
            # rule-44 router arm check (supporting only)
            "arms/a1_minus_a5_us_per_step": -10.7,
            "arms/a1_minus_a5_sigma_us_per_step": 4.7,
            "arms/split1_total_drift_us_per_step": 72.0,
            # verdict
            "verdict/h1_supported": False,
            "verdict/h0_supported": True,
        }
    )

    run.finish()
    print(f"W&B run: {run.url}")


if __name__ == "__main__":
    main()
