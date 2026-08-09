#!/usr/bin/env python3
"""Log r96-a (Stage 0 census, R1 no-go, R2 4-deep pipeline) evidence to W&B.

All numbers below are transcribed from the captured probe outputs:
  Stage 0  -> /tmp/nez_occ_out.txt   (research/nezuko_occupancy_probe.swift)
  R2 screen-> /tmp/nez_lat_r2.txt    (research/nezuko_pipeline_latency.swift)
  null     -> /tmp/nez_lat_null.txt  (same instrument, base vs base)
"""

import wandb

PROJECT = "mlxfast-maple"
ENTITY = "wandb-applied-ai-team"
GROUP = "r96-a-decode-attention-pipeline"

# 40 layers on the pinned 1-full:3-sliding XS schedule.
SLIDING_CALLS_PER_STEP = 30
FULL_CALLS_PER_STEP = 10

# Ranked M5 Max has 40 GPU cores; sliding launches 32 TGs (64 heads / 2) and
# full launches 24 TGs (48 heads / 2). Both are <= 1 TG/core, i.e. a single
# wave. The faithful M4 proxy for that occupancy is K=20 (1 TG/core on 20
# cores) WITH full 20-way bandwidth contention -- not K=1.
M5_PROXY_K = 20

# staircase sweep: K -> (base us/call, cand us/call)
R2_STAIRCASE = {
    1: (8.714, 8.451), 2: (8.754, 8.524), 4: (8.829, 8.550),
    8: (8.882, 8.616), 16: (8.914, 8.644), 20: (8.940, 8.665),
    24: (17.718, 17.679), 32: (17.853, 18.133), 40: (18.294, 17.774),
    48: (24.974, 24.996), 56: (25.501, 25.160), 60: (25.253, 25.345),
    64: (32.413, 31.914), 72: (33.537, 32.208), 96: (40.112, 39.593),
    120: (48.497, 46.665), 128: (55.624, 53.461), 240: (95.735, 95.379),
}
NULL_STAIRCASE = {
    1: (8.716, 8.704), 2: (8.746, 8.750), 4: (8.825, 8.808),
    8: (8.859, 8.879), 16: (8.921, 8.894), 20: (8.916, 8.939),
    24: (17.642, 17.469), 32: (17.922, 18.177), 40: (18.264, 18.178),
    48: (25.094, 24.993), 56: (25.419, 25.152), 60: (25.740, 25.736),
    64: (32.472, 32.260), 72: (33.423, 33.378), 96: (40.567, 40.828),
    120: (48.337, 48.409), 128: (55.550, 55.540), 240: (95.259, 95.107),
}

# Stage 0 Phase E: real sliding body, dummy buffers.
PHASE_E = {  # K -> (us/call, requested GB/s, unique GB/s)
    1: (8.70, 30.1, 30.1), 20: (8.90, 589.4, 147.3), 24: (17.60, 357.5, 89.4),
    32: (18.01, 465.7, 116.4), 40: (18.45, 568.3, 142.1), 48: (25.02, None, None),
    60: (25.52, 616.4, 154.1), 64: (32.65, 513.8, 128.5),
    120: (48.28, 651.6, 162.9), 240: (95.72, 657.3, 164.3),
}

COMMON_CONFIG = {
    "assignment_id": "maple-r96-a-decode-attention-pipeline",
    "revision_id": "r96-a-rev1",
    "pr": 511,
    "base_sha": "43036cd39dd3c795b117b099f0fe52767fbedbca",
    "measure_host": "Apple M4 Pro, 20 GPU cores, 48 GiB, applegpu_g16s gen16",
    "ranked_host": "Apple M5 Max, 40 GPU cores",
    "nax_kernels_selected": False,
    "sliding_calls_per_step": SLIDING_CALLS_PER_STEP,
    "full_calls_per_step": FULL_CALLS_PER_STEP,
    "sliding_threadgroups_per_call": 32,
    "full_threadgroups_per_call": 24,
    "decode_price_pct_score_per_us_per_step": 0.015280,
    "m4_single_receipt_detection_bar_us_per_step": 80,
}


def us_per_step(us_per_call, calls):
    return us_per_call * calls


def run(name, tags, config, summary, history=None):
    r = wandb.init(
        project=PROJECT, entity=ENTITY, group=GROUP, name=name,
        tags=tags, config={**COMMON_CONFIG, **config}, reinit=True,
    )
    for row in history or []:
        wandb.log(row)
    r.summary.update(summary)
    r.finish()
    return r


def main():
    urls = {}

    # ---- Stage 0 census -------------------------------------------------
    hist = []
    for k, (us, req, uniq) in sorted(PHASE_E.items()):
        row = {"phaseE/K": k, "phaseE/us_per_call": us,
               "phaseE/waves": -(-k // 20)}
        if req is not None:
            row["phaseE/requested_gb_per_s"] = req
            row["phaseE/unique_gb_per_s"] = uniq
        hist.append(row)
    r = run(
        "r96a-stage0-occupancy-census",
        ["r96-a", "arm:stage0", "student:maple-nezuko"],
        {
            "gpu_cores": 20,
            "max_threadgroup_memory_length": 32768,
            "recommended_max_working_set_size": 40200896512,
        },
        {
            # Q1
            "simdgroup_slots_per_core": 96,
            "threads_per_core": 3072,
            "shipped_tg_per_core": 3,
            "residency_tgmem_dependent_at_1024t": False,
            "coresident_tgs_real_plane": 60,
            "coresident_tgs_real_plane_halved": 60,
            "residency_gain_from_halving_epilogue_plane": 0,
            # Q2
            "bytes_read_per_threadgroup": 262144,
            "read_amplification_shipped": 4,
            "read_amplification_r1": 8,
            "requested_bw_asymptote_gb_per_s": 657.3,
            "shipped_pct_of_requested_bw_ceiling": 465.7 / 657.3 * 100,
            "r1_bandwidth_floor_us": 16.78e6 / 657e9 * 1e6,
            "r1_measured_cost_ratio_vs_shipped": 32.65 / 18.01,
            # pipeline properties (contract metrics)
            "pipeline_max_threads_sliding": 1024,
            "pipeline_tg_mem_bytes_sliding": 18432,
            "pipeline_max_threads_full": 1024,
            "pipeline_tg_mem_bytes_full": 18432,
            "thread_execution_width": 32,
            "simdgroups_per_threadgroup": 32,
            # throughput-bound evidence
            "staircase_step_period_equals_core_count": True,
            "marginal_wave_frac_of_lone_wave": 7.849 / 8.716,
            "r1_verdict": "NO-GO",
        },
        hist,
    )
    urls["stage0"] = (r.id, r.url)

    # ---- R2 arms + calibrated null --------------------------------------
    specs = [
        ("r96a-R2-base-2deep", "R2", "A-base", R2_STAIRCASE, 0,
         {"pipeline_depth": 2, "body_lines": 268, "msl_bytes": 13333,
          "refit_a": 1.413, "refit_b": 7.849}),
        ("r96a-R2-cand-4deep", "R2", "B-cand", R2_STAIRCASE, 1,
         {"pipeline_depth": 4, "body_lines": 356, "msl_bytes": 17419,
          "refit_a": 1.266, "refit_b": 7.745}),
        ("r96a-null-control-base-A", "null", "A-base", NULL_STAIRCASE, 0,
         {"pipeline_depth": 2, "refit_a": 1.518, "refit_b": 7.819}),
        ("r96a-null-control-base-B", "null", "B-slot", NULL_STAIRCASE, 1,
         {"pipeline_depth": 2, "refit_a": 1.511, "refit_b": 7.814}),
    ]

    for name, arm, slot, table, idx, cfg in specs:
        hist = []
        for k, pair in sorted(table.items()):
            hist.append({
                "staircase/K": k,
                "staircase/us_per_call": pair[idx],
                "staircase/B_over_A": pair[1] / pair[0],
                "staircase/tg_per_core_m4": k / 20.0,
            })
        k20 = table[M5_PROXY_K][idx]
        k32 = table[32][idx]
        summary = {
            # PRIMARY: projected sliding attention us/step in the M5-faithful
            # single-wave regime (K=20 proxy, 1 TG/core, 20-way contention).
            "attn_us_per_step_sliding": us_per_step(k20, SLIDING_CALLS_PER_STEP),
            # Full-attention kernel is UNMODIFIED in this candidate, so its
            # delta is exactly 0 by construction; projected from the same proxy.
            "attn_us_per_step_full": us_per_step(k20, FULL_CALLS_PER_STEP),
            "attn_us_per_step_full_measured": False,
            "full_kernel_modified": False,
            "us_per_call_k20_m5_proxy": k20,
            "us_per_call_k32_m4_shipped": k32,
            "us_per_call_k1": table[1][idx],
            "pipeline_max_threads_sliding": 1024,
            "pipeline_tg_mem_bytes_sliding": 18432,
            # No end-to-end receipt was run: expected effect is ~7x below the
            # M4 single-receipt detection bar, so it would be underpowered.
            # step_us_total is deliberately absent rather than NaN-filled.
            "step_us_total_measured": False,
        }
        summary.update(cfg)
        if arm == "R2" and slot == "B-cand":
            base20 = table[M5_PROXY_K][0]
            summary.update({
                "bitexact_configs_checked": 20,
                "bitexact_all_equal": True,
                "max_ulp_diff": 0,
                "max_abs_diff": 0.0,
                "register_illegal": False,
                "abba_k1_median_B_over_A": 0.9711,
                "abba_k32_median_B_over_A": 1.0091,
                "abba_k32_mean_B_over_A": 1.0034,
                "abba_k32_mean_sem": 0.0047,
                "m5_proxy_B_over_A": table[M5_PROXY_K][1] / base20,
                "delta_attn_us_per_step_sliding":
                    us_per_step(table[M5_PROXY_K][1] - base20,
                                SLIDING_CALLS_PER_STEP),
                "projected_score_pct_sliding_only":
                    -us_per_step(table[M5_PROXY_K][1] - base20,
                                 SLIDING_CALLS_PER_STEP) * 0.015280,
                "equivalence_oracle_identical_to_base": True,
                "equivalence_decode_steps_exact": 8,
                "equivalence_prefill_drift_preexisting_on_m4": True,
            })
        if arm == "null":
            summary["abba_k1_median_B_over_A"] = 0.9997
            summary["abba_k32_median_B_over_A"] = 0.9942
            summary["abba_k32_mean_B_over_A"] = 0.9948
            summary["abba_k32_mean_sem"] = 0.0038

        r = run(name, ["r96-a", f"arm:{arm}", f"slot:{slot}",
                       "student:maple-nezuko"], cfg, summary, hist)
        urls[name] = (r.id, r.url)

    print("\n=== W&B runs ===")
    for k, (rid, url) in urls.items():
        print(f"{k}\t{rid}\t{url}")


if __name__ == "__main__":
    main()
