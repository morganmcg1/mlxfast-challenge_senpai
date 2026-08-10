#!/usr/bin/env python3
"""Publish the R107-E decode oproj row-amortisation ledger to W&B.

Rule 98.9: every issued-byte number in this ledger is cache-resident traffic.
Compulsory DRAM bytes are identical in all four arms by construction
(`weight_code_reread_factor == 1.0` everywhere), so no issued-byte delta is a
speedup claim. The only speed claims are the paired in-situ decode contrasts.
"""

import json
import os
import subprocess

import wandb

REPO = ("/Users/ec2-user/.senpai/native/mlxfast-maple-20260810-expansion/"
        "roles/student-maple-alphonse/workspace/target")
ART = f"{REPO}/research/artifacts/maple-alphonse-r107e"
ARMS = ("g0", "g1", "g2", "g3")

head = subprocess.run(["git", "-C", REPO, "rev-parse", "HEAD"],
                      capture_output=True, text=True, check=True).stdout.strip()

stats = json.load(open(f"{ART}/insitu-stats.json"))
traffic = json.load(open(f"{ART}/geom-traffic-model.json"))
air = json.load(open(f"{ART}/geom-air-ledger.json"))
loads = json.load(open(f"{ART}/geom-air-loads.json"))
roof = traffic["roofline"]
ceil = traffic["issue_ceiling"]
fit = traffic["regime_fit"]
t2d = traffic["t2d_comparison_column"]
dyn = loads["dynamic_loads_per_thread_per_k_block"]
dec, pla = stats["decode"], stats["prefill_placebo"]
# Rule 105: the 0.4 % bar lives in M5 us/step because the campaign price was
# fitted on an official M5 decode. Every verdict below is taken in % of cs after
# converting this host's measured us/step with k = alpha (bytes regime), never by
# comparing a raw M4 percentage against the bar.
bars = stats["bars"]
K_PRIMARY = bars["k_primary"]
BAR_PCT_CS = bars["solo_bar_pct_cs"]
SUMMAND_PCT_CS = bars["summand_bar_pct_cs"]
BAR_US_M4 = bars["solo_bar_us_per_step_m4"][K_PRIMARY]
SUMMAND_US_M4 = bars["summand_bar_us_per_step_m4"][K_PRIMARY]


def wins(rec: dict) -> bool:
    """A contrast is a shippable win only if it is faster (negative delta), the
    magnitude clears the solo bar in % of cs, and the CI excludes zero."""
    return bool(rec["mean_pct_cs"][K_PRIMARY] <= -BAR_PCT_CS and rec["excludes_zero"]
                and rec["ci95_pct_cs_primary"][1] < 0)


amort, tgshape = dec["contrasts"]["A_amortisation"], dec["contrasts"]["B_threadgroup_shape"]
best_arm = min(("g1", "g2", "g3"), key=lambda a: dec["contrasts"][f"{a}_vs_g0"]["mean_pct"])
best = dec["contrasts"][f"{best_arm}_vs_g0"]

v_amort, v_tgshape = wins(amort), wins(tgshape)
# The family already runs at 87.1% / 80.6% of the measured M4 Pro ceiling, so a
# 24% cut in *issued* bytes that buys no time says the binding constraint is not
# issue slots. That is the mechanistic reading of a null on factor A.
n_issue_bound = bool(not v_amort and amort["mean_pct_cs"][K_PRIMARY] > -BAR_PCT_CS
                     and ceil["utilisation_scaled_ceiling_pct_of_cs"] < BAR_PCT_CS)
n_amort = bool(not v_amort)
# N-ROOFLINE would fire if the family's whole remaining deficit were under the
# bar. It is not: 0.74-1.14% of cs is available, the arms just cannot take it.
n_roofline = bool(min(v[K_PRIMARY]
                      for v in roof["family_total_headroom_pct_of_cs"].values())
                  < BAR_PCT_CS)

run = wandb.init(
    entity="wandb-applied-ai-team",
    project="mlxfast-maple",
    name="maple-alphonse-r107e-decode-oproj-amortisation",
    job_type="paired-insitu-timing",
    tags=["maple-alphonse", "r107-E", "oproj_act_h64", "oproj_act_h48", "T3b",
          "T3c", "decode", "row-amortisation", "2x2-factorial", "abba-paired",
          "rule-98.9-cache-resident", "rule-81-both-references",
          "regime-fit-residual-scaling", "t2d-comparison-column-untouched"],
    notes=(
        "Does the decode NVFP4 oproj family lose time re-issuing cache-resident "
        "activation and scale traffic once per output row? Four arms in a 2x2 "
        "factorial of results_per_simdgroup {4,8} x rows_per_threadgroup {8,16}, "
        "timed as position-mirrored ABBA halves through ./benchmark.sh "
        "--local-iterate on one quiet M4 Pro. Raising rps 4->8 cuts issued bytes "
        "24.2% and ops-per-useful-FMA 13.6% with compulsory DRAM bytes held "
        "exactly fixed. The pre-timing roofline is the tight constraint: T3b+T3c "
        "already achieve 87.1%/80.6% of the measured 266.80 GB/s M4 Pro ceiling, "
        "so the entire remaining deficit is 0.96-1.31% of decode and the 0.4% "
        "bar needs 31-42% of it. A residual-scaling test on the two family dose "
        "points contradicts the premise before any arm is timed: the hypothesis "
        "predicts the non-byte residual scales with k_blocks (ratio 1.333), the "
        "observed ratio is 0.824, and the residual is better described as a fixed "
        "per-dispatch cost belonging to the closed dispatch-count family."
    ),
    config={
        "assignment_pr": 644,
        "assignment_id": "maple-r107-e-decode-oproj-amortisation",
        "revision_id": "r107-e-rev1",
        "branch": "maple-alphonse/r107-decode-oproj-amortisation",
        "base_sha": "2454cc01ea3afabac067f0a271e36901fea7d21c",
        "head_sha": head,
        "host": "Apple M4 Pro / 20 GPU cores / 14 CPU / 48 GiB",
        "gpu_architecture": "applegpu_g16s",
        "apple_gpu_generation": 16,
        "nax_available": False,
        "macos": "26.5.2 (25F84)",
        "hypothesis": "H-OPROJ-ISSUE",
        "kernel_generator": "lagunaGatedAffineOProjNVFP4Source",
        "live_kernel_dict": "lagunaActivatedOProjLaneMajorKernels",
        "knob": "DARKBLOOM_OPROJ_GEOM (unset|g1|g2|g3)",
        "arms": {a: traffic["factorial"]["cells"][a] for a in ARMS},
        "factorial_design": traffic["factorial"]["design"],
        "g0_air_identical_to_base_h64": air["g0_emission_identical_to_base"]["h64"],
        "g0_air_identical_to_base_h48": air["g0_emission_identical_to_base"]["h48"],
        "prefill_is_placebo_channel": True,
        "prefill_placebo_reason": ("decode oproj call site gated on gatePerHead && "
                                   "B==1 && L==1, LagunaRuntimeModel.swift:6355-6362"),
        # rule 105 unit contract: bar in % of cs, plus its conversion into the
        # units this host actually measures in, under both alpha candidates.
        "shippable_bar_pct_of_cs": BAR_PCT_CS,
        "shippable_bar_us_m5": roof["m5_bar_us"],
        "shippable_bar_us_per_step_m4": roof["shippable_bar_us_per_step_m4"],
        "summand_bar_pct_of_cs": SUMMAND_PCT_CS,
        "summand_bar_us_per_step_m4": roof["summand_bar_us_per_step_m4"],
        "k_regime": bars["k_regime_label"],
        "k_primary": K_PRIMARY,
        "price_pct_cs_per_m5_us_per_step": bars["price_pct_cs_per_m5_us_per_step"],
        "single_receipt_detection_bar_us_per_step_m4":
            bars["single_receipt_detection_bar_us_per_step_m4"],
        "epoch": "R107, base 2454cc01 (advisor advanced to 4e9a8e16, docs-only)",
        "m4_ceiling_gb_per_s": roof["m4_ceiling_gb_per_s"],
        "b_step_bytes": roof["b_step_bytes"],
        "m5_pool_provenance": ("alpha = 0.4369 / beta = 0.5 two-pool map, "
                               "residual -6.63%, #561"),
        "alpha_beta_degeneracy_caveat": roof["caveat"],
        "sessions": stats["sessions"],
        "n_runs": stats["n_runs"],
        "n_abba_pairs": stats["n_halves"],
        "n_forward_halves": stats["n_forward_halves"],
        "n_reverse_halves": stats["n_reverse_halves"],
        "submitted_surface_files": 1,
        "submitted_surface_file": "Sources/MLXFastModel/LagunaRuntimeModel.swift",
        "official_submissions_from_this_pr": 0,
        "instrument": ("research/maple-alphonse-r107e-{insitu.sh,"
                       "oproj-geom-census.py,traffic-model.py,air-loads.py,analyse.py}"),
        # Rule 99.3: pipeline names resolved statically from the name assembly at
        # LagunaRuntimeModel.swift:4599-4607 plus the MLX "custom_kernel_" prefix at
        # metal_kernel.cpp:289, with all three name flags at their default-on value.
        "pipeline_name_g0_h64": "custom_kernel_laguna_oproj_act_h64_v1_lm1_pw1_sc1_se1",
        "pipeline_name_g0_h48": "custom_kernel_laguna_oproj_act_h48_v1_lm1_pw1_sc1_se1",
        "pipeline_name_arm_suffix": "_g1 | _g2 | _g3 appended to the g0 name",
        "report": "research/maple-alphonse-r107e-decode-oproj-amortisation.md",
    },
)

summary = {
    # PRIMARY: paired in-situ decode contrasts. Negative = faster than shipped.
    "primary/amortisation_effect_pct": amort["mean_pct"],
    "primary/amortisation_ci95_lo_pct": amort["ci95_pct"][0],
    "primary/amortisation_ci95_hi_pct": amort["ci95_pct"][1],
    "primary/amortisation_excludes_zero": int(amort["excludes_zero"]),
    "primary/amortisation_sign_p": amort["sign_p"],
    "primary/threadgroup_shape_effect_pct": tgshape["mean_pct"],
    "primary/threadgroup_shape_ci95_lo_pct": tgshape["ci95_pct"][0],
    "primary/threadgroup_shape_ci95_hi_pct": tgshape["ci95_pct"][1],
    "primary/threadgroup_shape_excludes_zero": int(tgshape["excludes_zero"]),
    "primary/interaction_effect_pct": dec["contrasts"]["AB_interaction"]["mean_pct"],
    "primary/best_arm": best_arm,
    "primary/best_arm_effect_pct": best["mean_pct"],
    "primary/best_arm_clears_bar": int(wins(best)),
    "primary/any_arm_shippable": int(any(wins(dec["contrasts"][f"{a}_vs_g0"])
                                         for a in ("g1", "g2", "g3"))),
    "primary/bar_pct_of_cs": BAR_PCT_CS,
    "primary/bar_us_per_step_m4": BAR_US_M4,
    "primary/summand_bar_pct_of_cs": SUMMAND_PCT_CS,
    "primary/summand_bar_us_per_step_m4": SUMMAND_US_M4,
    # Rule 105.6: every measured quantity in both units. `*_us_per_step_m4` is
    # what this host measured; `*_pct_cs` is the converted campaign currency.
    "primary/amortisation_effect_us_per_step_m4": amort["mean_us_per_step_m4"],
    "primary/amortisation_ci95_lo_us_per_step_m4": amort["ci95_us_per_step_m4"][0],
    "primary/amortisation_ci95_hi_us_per_step_m4": amort["ci95_us_per_step_m4"][1],
    "primary/amortisation_effect_pct_cs": amort["mean_pct_cs"][K_PRIMARY],
    "primary/amortisation_ci95_lo_pct_cs": amort["ci95_pct_cs_primary"][0],
    "primary/amortisation_ci95_hi_pct_cs": amort["ci95_pct_cs_primary"][1],
    "primary/amortisation_mde_us_per_step_m4": amort["mde_us_per_step_m4"],
    "primary/best_arm_effect_us_per_step_m4": best["mean_us_per_step_m4"],
    "primary/best_arm_effect_pct_cs": best["mean_pct_cs"][K_PRIMARY],
    "primary/best_arm_best_case_gain_us_per_step_m4":
        best["best_case_gain_us_per_step_m4"],
    # Rule 105.7: the CI is the deliverable. A null is only informative if the
    # interval is tight enough to exclude a bar-sized *or* summand-sized gain.
    "primary/amortisation_mde_pct": amort["mde_pct"],
    "primary/amortisation_resolves_bar": int(amort["resolves_bar"]),
    "primary/amortisation_resolves_summand": int(amort["resolves_summand"]),
    "primary/amortisation_excludes_summand_sized_gain":
        int(amort["excludes_summand_sized_gain"]),
    "primary/amortisation_banks_as_summand": int(amort["banks_as_summand"]),
    "primary/best_arm_mde_pct": best["mde_pct"],
    "primary/best_arm_mde_us_per_step_m4": best["mde_us_per_step_m4"],
    "primary/best_arm_resolves_bar": int(best["resolves_bar"]),
    "primary/best_arm_resolves_summand": int(best["resolves_summand"]),
    "primary/best_arm_excludes_summand_sized_gain":
        int(best["excludes_summand_sized_gain"]),
    "primary/best_arm_banks_as_summand": int(best["banks_as_summand"]),
    "primary/any_arm_banks_as_summand": int(any(
        dec["contrasts"][f"{a}_vs_g0"]["banks_as_summand"]
        for a in ("g1", "g2", "g3"))),
    "primary/n_pairs_for_bar_best_arm": best["n_pairs_for_bar"] or -1,
    "primary/n_pairs_for_summand_best_arm": best["n_pairs_for_summand"] or -1,

    # Per-arm paired decode deltas.
    **{f"decode/{a}_vs_g0_pct": dec["contrasts"][f"{a}_vs_g0"]["mean_pct"]
       for a in ("g1", "g2", "g3")},
    **{f"decode/{a}_vs_g0_ci95_hi_pct": dec["contrasts"][f"{a}_vs_g0"]["ci95_pct"][1]
       for a in ("g1", "g2", "g3")},
    **{f"decode/{a}_vs_g0_us_per_step_m4":
       dec["contrasts"][f"{a}_vs_g0"]["mean_us_per_step_m4"]
       for a in ("g1", "g2", "g3")},
    **{f"decode/{a}_vs_g0_pct_cs": dec["contrasts"][f"{a}_vs_g0"]["mean_pct_cs"][K_PRIMARY]
       for a in ("g1", "g2", "g3")},
    **{f"decode/mean_s_{a}": dec["arm_means_s"][a] for a in ARMS},
    "decode/g0_mean_s": dec["g0_mean_s"],
    "decode/g0_cov_pct": dec["g0_cov_pct"],

    # PLACEBO: the same estimator on an axis the kernel provably cannot reach.
    "placebo/prefill_g0_mean_s": pla["g0_mean_s"],
    "placebo/prefill_g0_cov_pct": pla["g0_cov_pct"],
    "placebo/prefill_amortisation_effect_pct": pla["contrasts"]["A_amortisation"]["mean_pct"],
    "placebo/prefill_amortisation_effect_us_per_token_m4":
        pla["contrasts"]["A_amortisation"]["mean_us_per_token_m4"],
    "placebo/prefill_max_abs_arm_effect_pct": max(
        abs(pla["contrasts"][f"{a}_vs_g0"]["mean_pct"]) for a in ("g1", "g2", "g3")),
    "placebo/prefill_any_false_positive": int(any(
        pla["contrasts"][f"{a}_vs_g0"]["excludes_zero"] for a in ("g1", "g2", "g3"))),

    # ROOFLINE: what the family could give up at best, measured on this host.
    "roofline/t3b_m4_achieved_gb_per_s": roof["families"]["T3b_oproj_h64"]["m4_achieved_gb_per_s"],
    "roofline/t3b_m4_pct_of_ceiling": roof["families"]["T3b_oproj_h64"]["m4_pct_of_ceiling"],
    "roofline/t3b_m4_us_per_dispatch": roof["families"]["T3b_oproj_h64"]["m4_us_per_dispatch"],
    "roofline/t3b_pct_of_b_step": roof["families"]["T3b_oproj_h64"]["pct_of_b_step"],
    "roofline/t3b_headroom_us_vs_lmhead": roof["families"]["T3b_oproj_h64"]["headroom_us"]["lmhead"],
    "roofline/t3b_headroom_us_vs_dense_down": roof["families"]["T3b_oproj_h64"]["headroom_us"]["dense_down"],
    "roofline/t3c_m4_pct_of_ceiling": roof["families"]["T3c_oproj_h48"]["m4_pct_of_ceiling"],
    "roofline/t3c_m4_us_per_dispatch": roof["families"]["T3c_oproj_h48"]["m4_us_per_dispatch"],
    "roofline/t3c_pct_of_b_step": roof["families"]["T3c_oproj_h48"]["pct_of_b_step"],
    "roofline/family_headroom_pct_vs_lmhead":
        roof["family_total_headroom_pct_of_decode"]["lmhead"],
    "roofline/family_headroom_pct_vs_dense_down":
        roof["family_total_headroom_pct_of_decode"]["dense_down"],
    "roofline/family_headroom_pct_of_cs_vs_lmhead":
        roof["family_total_headroom_pct_of_cs"]["lmhead"][K_PRIMARY],
    "roofline/family_headroom_pct_of_cs_vs_dense_down":
        roof["family_total_headroom_pct_of_cs"]["dense_down"][K_PRIMARY],
    "roofline/deficit_fraction_needed_vs_lmhead":
        roof["fraction_of_deficit_needed_to_clear_bar"]["lmhead"][K_PRIMARY],
    "roofline/deficit_fraction_needed_vs_dense_down":
        roof["fraction_of_deficit_needed_to_clear_bar"]["dense_down"][K_PRIMARY],
    "roofline/summand_deficit_fraction_needed_vs_lmhead":
        roof["fraction_of_deficit_needed_to_clear_summand_bar"]["lmhead"][K_PRIMARY],
    "roofline/summand_deficit_fraction_needed_vs_dense_down":
        roof["fraction_of_deficit_needed_to_clear_summand_bar"]["dense_down"][K_PRIMARY],
    "roofline/local_whole_step_pct_of_ceiling": roof["local_pct_of_ceiling_whole_step"],
    # Rule 81: both published reference rates, because the >=10pp clause is met
    # under lmhead and fails under the fairer same-pattern dense_down.
    "roofline/rule81_reference_lmhead_us_t3b": 51.7,
    "roofline/rule81_reference_dense_down_us_t3b": 36.1,

    # ISSUE-SIDE model, cache-resident only (rule 98.9) - never a speed claim.
    "issued/h64_bytes_rps4": traffic["arms"]["g0"]["h64"]["issued_bytes_total"],
    "issued/h64_bytes_rps8": traffic["arms"]["g1"]["h64"]["issued_bytes_total"],
    "issued/h64_issued_reduction_pct": 100.0 * (
        traffic["arms"]["g1"]["h64"]["issued_bytes_total"]
        / traffic["arms"]["g0"]["h64"]["issued_bytes_total"] - 1.0),
    "issued/h64_over_compulsory_rps4": traffic["arms"]["g0"]["h64"]["issued_over_compulsory"],
    "issued/h64_over_compulsory_rps8": traffic["arms"]["g1"]["h64"]["issued_over_compulsory"],
    "issued/h64_activation_reread_rps4": traffic["arms"]["g0"]["h64"]["activation_reread_factor"],
    "issued/h64_activation_reread_rps8": traffic["arms"]["g1"]["h64"]["activation_reread_factor"],
    "issued/h64_ops_per_fma_rps4": traffic["arms"]["g0"]["h64"]["ops_per_fma"],
    "issued/h64_ops_per_fma_rps8": traffic["arms"]["g1"]["h64"]["ops_per_fma"],
    "issued/weight_code_reread_factor_all_arms": 1.0,
    "issued/compulsory_bytes_identical_across_arms": 1,
    "issued/grid_threads_rps4": traffic["arms"]["g0"]["h64"]["grid_threads"],
    "issued/grid_threads_rps8": traffic["arms"]["g1"]["h64"]["grid_threads"],

    # Static AIR census: instruction *sites*, not dynamic issue counts.
    "air/g0_emission_identical_to_base": int(
        all(air["g0_emission_identical_to_base"].values())),
    "air/all_eight_variants_compiled": 1,
    "air/ir_counts_flat_across_arms_loops_not_unrolled": 1,
    "air/device_load_sites": dyn["g0"]["device_load_sites_in_air"],
    "air/all_eight_air_digests_distinct": int(
        len({d["air_ir_sha256_16"] for d in loads["rule75_digests"].values()}) == 8),
    "air/no_spill_signature_all_variants": int(
        all(v["matches_expected"] for v in loads["spill_proxy"].values())),

    # Dynamic load census per thread per k-block, derived from the emitted IR.
    "air/issued_loads_rps4": dyn["g0"]["issued_total"],
    "air/issued_loads_rps8": dyn["g1"]["issued_total"],
    "air/issued_per_output_row_rps4": dyn["g0"]["issued_per_output_row"],
    "air/issued_per_output_row_rps8": dyn["g1"]["issued_per_output_row"],
    "air/issued_per_row_reduction_pct": 100.0 * (
        dyn["g1"]["issued_per_output_row"] / dyn["g0"]["issued_per_output_row"] - 1.0),
    "air/dram_per_output_row_all_arms": dyn["g0"]["dram_per_output_row"],
    "air/cache_resident_pct_rps4": dyn["g0"]["cache_resident_pct"],
    "air/cache_resident_pct_rps8": dyn["g1"]["cache_resident_pct"],

    # Regime fit T = B/BW + L. The premise of H-OPROJ-ISSUE predicts the residual
    # scales with k_blocks; the observed ratio has the opposite sign.
    "fit/free_two_point_bw_gb_per_s": fit["free_two_point_fit"]["bw_gb_per_s"],
    "fit/free_two_point_L_us": fit["free_two_point_fit"]["L_us_per_dispatch"],
    "fit/free_fit_exceeds_ceiling_pct": fit["free_two_point_fit"][
        "exceeds_measured_ceiling_by_pct"],
    "fit/residual_L_us_h64": fit["bw_pinned_at_measured_ceiling"][
        "T3b_oproj_h64"]["residual_L_us"],
    "fit/residual_L_us_h48": fit["bw_pinned_at_measured_ceiling"][
        "T3c_oproj_h48"]["residual_L_us"],
    "fit/residual_L_ratio_observed": fit["residual_scaling_test"][
        "residual_L_ratio_h64_over_h48"],
    "fit/residual_L_ratio_predicted_by_hypothesis": fit["residual_scaling_test"][
        "k_blocks_ratio_h64_over_h48"],
    "fit/residual_scaling_sign_opposite": int(
        fit["residual_scaling_test"]["observed_sign"] == "OPPOSITE"),
    "fit/residual_better_described_as_fixed_per_dispatch": int(
        fit["residual_scaling_test"]["better_described_as"] == "fixed_per_dispatch"),
    "fit/family_residual_us_per_step": fit["family_total_residual_us_per_step"],
    "fit/family_residual_pct_of_m5_step": fit["family_total_residual_pct_of_m5_step"],
    "fit/dose_curve_degenerate_bytes_vs_kblocks": int(
        fit["collinearity"]["verdict"].startswith("DEGENERATE")),
    "fit/bytes_per_k_block_spread": fit["collinearity"]["spread"],

    # Rule-100 issue-slot ceiling: the generous upper bound on factor A, priced
    # by crediting every removed instruction slot at the full FP32 fma issue rate.
    "ceiling/t3b_issue_slots_per_dispatch_g0":
        ceil["families"]["T3b_oproj_h64"]["issue_slots_per_dispatch_g0"],
    "ceiling/t3b_pct_of_measured_issue_peak":
        ceil["families"]["T3b_oproj_h64"]["pct_of_measured_issue_peak"],
    "ceiling/t3c_pct_of_measured_issue_peak":
        ceil["families"]["T3c_oproj_h48"]["pct_of_measured_issue_peak"],
    "ceiling/t3b_slots_removed_pct_g1":
        ceil["families"]["T3b_oproj_h64"]["arms"]["g1"]["slots_removed_pct"],
    "ceiling/t3b_ceiling_pct_of_cs_g1":
        ceil["families"]["T3b_oproj_h64"]["arms"]["g1"]["ceiling_pct_of_cs"],
    "ceiling/t3c_ceiling_pct_of_cs_g1":
        ceil["families"]["T3c_oproj_h48"]["arms"]["g1"]["ceiling_pct_of_cs"],
    "ceiling/best_arm_combined_pct_of_cs": ceil["best_arm_combined_ceiling_pct_of_cs"],
    "ceiling/clears_bar_at_full_issue_boundedness": int(ceil["ceiling_clears_bar"]),
    "ceiling/time_weighted_issue_utilisation_pct":
        ceil["time_weighted_issue_utilisation_pct"],
    "ceiling/utilisation_scaled_pct_of_cs": ceil["utilisation_scaled_ceiling_pct_of_cs"],
    "ceiling/clears_summand_bar_at_full_issue_boundedness":
        int(ceil["ceiling_clears_summand_bar"]),
    "ceiling/utilisation_scaled_clears_summand_bar":
        int(ceil["utilisation_scaled_clears_summand_bar"]),
    "ceiling/combined_us_per_step_m4":
        ceil["combined_ceiling_us_per_step_m4"][K_PRIMARY],
    "ceiling/utilisation_scaled_us_per_step_m4":
        ceil["utilisation_scaled_ceiling_us_per_step_m4"][K_PRIMARY],
    "ceiling/slot_cost_multiplier_needed_for_summand": ceil[
        "slot_cost_multiplier_needed_for_summand_at_measured_utilisation"],
    "ceiling/slot_cost_multiplier_needed": ceil[
        "slot_cost_multiplier_needed_at_measured_utilisation"],
    "ceiling/rule100_issue_per_s_reference": ceil["rule100_issue_per_s"],

    # T2d down-residual: comparison column only, kernel untouched by R107-E.
    "t2d/kernel_untouched": 1,
    "t2d/bytes_per_call": t2d["byte_identity"]["bytes_per_call"],
    "t2d/byte_identity_agrees_with_advisor": int(t2d["byte_identity"]["agrees"]),
    "t2d/pct_of_b_step": t2d["byte_identity"]["pct_of_b_step"],
    "t2d/activation_share_pct": t2d["lane_load_traffic"]["activation_share_pct"],
    "t2d/activation_reread_factor": t2d["activation_reread_factor"],
    "t2d/amortisation_factor": t2d["amortisation_factor"],
    "t2d/loads_per_unique_weight_byte": t2d["loads_per_unique_weight_byte"],
    "t2d/k_blocks": t2d["k_blocks"],

    # Preregistered outcomes.
    "outcome/V_AMORT": int(v_amort),
    "outcome/N_AMORT": int(n_amort),
    "outcome/V_TGSHAPE": int(v_tgshape),
    "outcome/N_ISSUE_BOUND": int(n_issue_bound),
    "outcome/N_ROOFLINE": int(n_roofline),
    "outcome/N_CORRECT": 0,
    "outcome/N_BUILD": 0,
    "outcome/all_arms_pass_local_correctness": 1,
}
run.summary.update(summary)

runs_t = wandb.Table(columns=["session", "pos", "arm", "half", "order",
                              "decode_s", "prefill_s", "passed"])
for h in stats["halves"]:
    for arm in ARMS:
        runs_t.add_data(h["session"], h["arm_pos"][arm], arm, h["half"], h["order"],
                        h["decode"][arm], h["prefill"][arm], True)
run.log({"insitu_runs": runs_t})

con_t = wandb.Table(columns=["axis", "contrast", "n_pairs", "mean_pct", "ci95_lo_pct",
                             "ci95_hi_pct", "excludes_zero", "sign_pos", "sign_p",
                             "forward_pct", "reverse_pct", "mde_pct", "resolves_bar",
                             "n_pairs_for_bar", "mean_us_per_token_m4",
                             "ci95_lo_us_per_token_m4", "ci95_hi_us_per_token_m4",
                             "priced_in_cs",
                             "mean_pct_cs", "ci95_lo_pct_cs", "ci95_hi_pct_cs",
                             "mde_us_per_token_m4", "resolves_summand",
                             "excludes_summand_sized_gain", "banks_as_summand"])
for axis, blk in (("decode", dec), ("prefill_placebo", pla)):
    for name, rec in blk["contrasts"].items():
        base = blk["g0_mean_s"]
        # the decode-fitted price must not be applied to the placebo axis, so
        # the %cs columns stay empty there (rule 105.6).
        cs = rec["mean_pct_cs"][K_PRIMARY] if rec["priced_in_cs"] else None
        cs_lo, cs_hi = (rec["ci95_pct_cs_primary"] if rec["priced_in_cs"]
                        else (None, None))
        con_t.add_data(axis, name, rec["n"], rec["mean_pct"], rec["ci95_pct"][0],
                       rec["ci95_pct"][1], rec["excludes_zero"], rec["sign_pos"],
                       rec["sign_p"],
                       100.0 * rec["by_order"].get("forward", float("nan")) / base,
                       100.0 * rec["by_order"].get("reverse", float("nan")) / base,
                       rec["mde_pct"], rec["resolves_bar"], rec["n_pairs_for_bar"],
                       rec["mean_us_per_token_m4"], rec["ci95_us_per_token_m4"][0],
                       rec["ci95_us_per_token_m4"][1], rec["priced_in_cs"],
                       cs, cs_lo, cs_hi,
                       rec["mde_us_per_token_m4"], rec["resolves_summand"],
                       rec["excludes_summand_sized_gain"], rec["banks_as_summand"])
run.log({"contrasts": con_t})

geom_t = wandb.Table(columns=["arm", "head", "rps", "num_simdgroups", "rows_per_tg",
                              "threads_per_tg", "threadgroups", "grid_threads",
                              "issued_MB", "issued_over_compulsory",
                              "act_reread", "ops_per_fma"])
for arm in ARMS:
    for head_k in ("h64", "h48"):
        m = traffic["arms"][arm][head_k]
        geom_t.add_data(arm, head_k, m["results_per_simdgroup"], m["num_simdgroups"],
                        m["rows_per_threadgroup"], m["threads_per_threadgroup"],
                        m["threadgroups"], m["grid_threads"],
                        m["issued_bytes_total"] / 1e6, m["issued_over_compulsory"],
                        m["activation_reread_factor"], m["ops_per_fma"])
run.log({"arm_geometry": geom_t})

roof_t = wandb.Table(columns=["family", "calls", "MB_per_step", "pct_of_B_step",
                              "m4_us_measured", "m4_us_per_dispatch", "m4_GB_s",
                              "m4_pct_of_ceiling", "headroom_us_vs_lmhead",
                              "headroom_us_vs_dense_down", "m5_us_modelled"])
for name, f in roof["families"].items():
    roof_t.add_data(name, f["calls"], f["head_bytes"] / 1e6, f["pct_of_b_step"],
                    f["m4_us_measured"], f["m4_us_per_dispatch"],
                    f["m4_achieved_gb_per_s"], f["m4_pct_of_ceiling"],
                    f["headroom_us"]["lmhead"], f["headroom_us"]["dense_down"],
                    f["m5_us_modelled"])
run.log({"roofline": roof_t})

loads_t = wandb.Table(columns=["arm", "issued_total", "reach_dram", "issued_per_output_row",
                               "dram_per_output_row", "cache_resident_pct",
                               "activation_bfloat", "gate_bfloat", "weight_codes_i32",
                               "scale_bases_i8", "scale_nibbles_i8"])
for arm in ARMS:
    d = dyn[arm]
    loads_t.add_data(arm, d["issued_total"], d["reach_dram"], d["issued_per_output_row"],
                     d["dram_per_output_row"], d["cache_resident_pct"],
                     d["activation_bfloat"], d["gate_bfloat"], d["weight_codes_i32"],
                     d["scale_bases_i8"], d["scale_nibbles_i8"])
run.log({"dynamic_load_census": loads_t})

dig_t = wandb.Table(columns=["variant", "metal_bytes", "metal_sha256_16", "air_ir_bytes",
                             "air_ir_sha256_16", "alloca_private_floats",
                             "expected_private_floats", "no_spill_signature"])
for variant, d in sorted(loads["rule75_digests"].items()):
    s = loads["spill_proxy"][variant]
    dig_t.add_data(variant, d["metal_bytes"], d["metal_sha256_16"], d["air_ir_bytes"],
                   d["air_ir_sha256_16"], s["alloca_private_floats"],
                   s["expected_result_plus_xthread"], s["matches_expected"])
run.log({"emission_digests": dig_t})

fit_t = wandb.Table(columns=["family", "bytes_time_us", "measured_us", "residual_L_us",
                             "residual_per_k_block_us"])
for name, f in fit["bw_pinned_at_measured_ceiling"].items():
    fit_t.add_data(name, f["bytes_time_us"], f["measured_us"], f["residual_L_us"],
                   f["residual_per_k_block_us"])
run.log({"regime_fit": fit_t})

ceil_t = wandb.Table(columns=["family", "arm", "issue_slots_per_dispatch",
                              "slots_removed_pct", "ceiling_us_per_dispatch",
                              "ceiling_m5_us_per_step", "ceiling_pct_of_cs",
                              "pct_of_measured_issue_peak"])
for name, f in ceil["families"].items():
    for arm, a in f["arms"].items():
        ceil_t.add_data(name, arm, a["issue_slots_per_dispatch"], a["slots_removed_pct"],
                        a["ceiling_us_per_dispatch"], a["ceiling_m5_us_per_step"],
                        a["ceiling_pct_of_cs"], f["pct_of_measured_issue_peak"])
run.log({"issue_slot_ceiling": ceil_t})

ledger_files = ["insitu-stats.json", "geom-traffic-model.json", "geom-air-ledger.json",
                "geom-air-loads.json"]

# Follow-up `occ2` session, if it ran. Factor A turned out to be exactly the
# inverse grid-thread count, so g4 halves results_per_simdgroup rather than
# doubling it: same axis, opposite direction, grid threads up instead of down.
occ2_path = f"{ART}/insitu-stats-occ2.json"
if os.path.exists(occ2_path):
    occ2 = json.load(open(occ2_path))
    o4 = occ2["decode"]["contrasts"]["g4_vs_g0"]
    o4p = occ2["prefill_placebo"]["contrasts"]["g4_vs_g0"]
    occ_t = wandb.Table(columns=["axis", "n_pairs", "mean_us_per_token_m4",
                                 "ci95_lo_us_per_token_m4", "ci95_hi_us_per_token_m4",
                                 "mean_pct", "excludes_zero", "sign_pos", "sign_neg",
                                 "mde_us_per_token_m4", "mean_pct_cs", "wins"])
    occ_t.add_data("decode", o4["n"], o4["mean_us_per_token_m4"],
                   o4["ci95_us_per_token_m4"][0], o4["ci95_us_per_token_m4"][1],
                   o4["mean_pct"], int(o4["excludes_zero"]), o4["sign_pos"],
                   o4["sign_neg"], o4["mde_us_per_token_m4"],
                   o4["mean_pct_cs"][K_PRIMARY], int(wins(o4)))
    occ_t.add_data("prefill_placebo", o4p["n"], o4p["mean_us_per_token_m4"],
                   o4p["ci95_us_per_token_m4"][0], o4p["ci95_us_per_token_m4"][1],
                   o4p["mean_pct"], int(o4p["excludes_zero"]), o4p["sign_pos"],
                   o4p["sign_neg"], o4p["mde_us_per_token_m4"], None, None)
    run.log({"occ2_g4_vs_g0": occ_t})
    run.summary.update({
        "occ2/n_pairs": o4["n"],
        "occ2/decode_effect_us_per_step_m4": o4["mean_us_per_token_m4"],
        "occ2/decode_ci95_lo_us_per_step_m4": o4["ci95_us_per_token_m4"][0],
        "occ2/decode_ci95_hi_us_per_step_m4": o4["ci95_us_per_token_m4"][1],
        "occ2/decode_effect_pct_cs": o4["mean_pct_cs"][K_PRIMARY],
        "occ2/decode_excludes_zero": int(o4["excludes_zero"]),
        "occ2/banks_as_summand": int(o4["banks_as_summand"]),
        "occ2/wins_solo_bar": int(wins(o4)),
        "occ2/placebo_prefill_effect_us_per_token_m4": o4p["mean_us_per_token_m4"],
    })
    ledger_files.append("insitu-stats-occ2.json")

artifact = wandb.Artifact("maple-alphonse-r107e-ledger", type="analysis")
for name in ledger_files:
    artifact.add_file(f"{ART}/{name}")
artifact.add_dir(f"{ART}/insitu", name="insitu")
artifact.add_file(f"{REPO}/research/maple-alphonse-r107e-decode-oproj-amortisation.md")
run.log_artifact(artifact)

print("run:", run.url)
print("run_id:", run.id)
run.finish()
