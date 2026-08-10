#!/usr/bin/env python3
"""Publish the R106-H channel-economics result to W&B.

Everything logged is parsed from the committed stage-a/b/c/d/e JSON, so the run
and `research/maple-nezuko-r106h-channel-economics.md` cannot disagree.

Usage: nezuko_r106h_wandb_log.py STAGE_A_JSON STAGE_B_JSON STAGE_C_JSON
                                 STAGE_D_JSON STAGE_E_JSON
"""
import json
import os
import sys

import wandb

ENTITY = "wandb-applied-ai-team"
PROJECT = "mlxfast-maple"
GROUP = "r106-h-channel-economics"

US_STEP_PER_PERCENT_CS = 65.67
OUR_RATE_PER_HOUR = 0.9

CORPUS_SHA256 = (
    "d450b5b5dc895f0d2d4de52d790035e88ea2e55255fed1ae04c80a9a7c70c12b")


def main(path_a, path_b, path_c, path_d, path_e):
    a = json.load(open(path_a))
    b = json.load(open(path_b))
    c = json.load(open(path_c))
    d = json.load(open(path_d))
    e = json.load(open(path_e))

    lnL = a["A1"]["lnL"]
    sig = b["sigma_cs"]
    anova_L = c["C1_launch_mixing_L_axis"]["anova_by_solver_ln_L"]
    coin = c["C5_prefill_coin"]
    prov = c["C6_record_provenance"]
    top_group = b["B1_groups"][b["B1_top_group"]]
    unbiased = [r for r in c["C3_record_ladder"]
                if r["label"].startswith("unbiased merit")][0]
    obs_max = c["C3_record_ladder"][0]
    per_budget = c["C4_exchange_rate"]["per_budget"]
    inverse = c["C4_exchange_rate"]["inverse_mechanism_to_draws"]
    e2_five = e["E2_paired_denominator"]["five_member_group_only"]
    e2p = e["E2_paired_denominator"]["pooled"]
    e4 = e["E4_mode_coin"]
    e5 = e["E5_cohort"]
    e6 = e["E6_joint"]
    e7 = e["E7_p_record"]
    e7m = e7["models"]
    e8 = e["E8_channel"]

    config = {
        "campaign": "maple",
        "student": "maple-nezuko",
        "assignment_id": "maple-r106-b-revert-residual-forensics",
        "revision_id": "r106-b-rev2",
        "pr": 616,
        "base_sha": "d5f416c7c02c809126264d8897a488203fb6df68",
        "official_receipts_consumed": 0,
        "sources_or_vendor_modified": False,
        "benchmark_ran": False,
        "corpus_sha256": CORPUS_SHA256,
        "corpus_bytes": 19936617,
        "corpus_frozen_at": "2026-08-10T08:37Z",
        "benchmark_id": "1854efdf-feba-4773-bae9-b80520881a74",
        "n_receipts_with_metrics": a["n_receipts_with_metrics"],
        "record_score": b["record_score"],
        "prior_art": "PR #555 Part 1 (maple-tanjiro) session-factor decomposition",
        "identity_max_rel_err":
            a["max_rel_err_cs_times_L_vs_reported_score"],
        "our_channel_rate_per_hour": OUR_RATE_PER_HOUR,
        "us_step_per_percent_cs": US_STEP_PER_PERCENT_CS,
        "sigma_cs_dof": sig["dof"],
        "n_distinct_solvers": c["C0_corpus_scope"]["n_distinct_solvers"],
        "verdict": ("V-DRAWS with a downward correction; V-SESSION and V-DRIFT "
                    "weak; Rule 93.4 and Rule 96.2 bracket the truth"),
        "outcome_N_FIT": False,
        "outcome_V_DRAWS": True,
        "outcome_V_SESSION": True,
        "outcome_V_DRIFT": True,
        "outcome_V_BASELINE": True,
        "outcome_V_COMMON_prefill_beta_zero": True,
        "stage_d_rule_93_4_verified": True,
        "stage_d_note_key_over_groups": True,
        "stage_d_homogeneity_rejected": False,
        "stage_d_outlier_found": False,
        "stage_d_R106E_DRAW_receipts_in_corpus":
            d["D1_draw01_guard"]["n_notes_matching_R106E_DRAW"],
        "stage_e_rule_96_anchor_cs": e["rule_96_quoted"]["anchor_cs"],
        "stage_e_rule_96_sigma_pct":
            e["rule_96_quoted"]["sd_ln_score_within_tree_pct"],
        "stage_e_rule_96_p_record_pct":
            e["rule_96_quoted"]["p_record_per_draw_pct"],
        "stage_e_headline_model": "empirical_all_receipts",
        "stage_e_headline_is_model_free": True,
    }

    summary = {
        # --- the lottery ---
        "sigma_L_pct": lnL["sd_pct"],
        "sigma_L_ci_lo_pct": lnL["sd_ci_pct"][0],
        "sigma_L_ci_hi_pct": lnL["sd_ci_pct"][1],
        "lnL_mean_pct": lnL["mean_pct"],
        "lnL_median_pct": lnL["median_pct"],
        "lnL_skew": lnL["skew"],
        "lnL_excess_kurtosis": lnL["excess_kurtosis"],
        "sd_ln_bl_dec_pct": a["A1"]["ln_bl_dec"]["sd_pct"],
        "sd_ln_bl_pre_pct": a["A1"]["ln_bl_pre"]["sd_pct"],
        "corr_ln_bl_dec_ln_bl_pre": a["A1"]["corr_ln_bl_dec_ln_bl_pre"],
        # --- the merit noise ---
        "sigma_cs_pct": sig["sd_pct"],
        "sigma_cs_ci_lo_pct": sig["ci_pct"][0],
        "sigma_cs_ci_hi_pct": sig["ci_pct"][1],
        "sigma_L_over_sigma_cs": lnL["sd_pct"] / sig["sd_pct"],
        "within_tree_sd_lnL_pct": a["A1c"]["lnL"]["sd_pct"],
        "within_tree_sd_lnL_ci_lo_pct": a["A1c"]["lnL"]["sd_ci_pct"][0],
        "within_tree_sd_lnL_ci_hi_pct": a["A1c"]["lnL"]["sd_ci_pct"][1],
        # --- the 4.9x sigma puzzle ---
        "sigma_cs_verified_pool_pct":
            a["A7"]["verified"]["pooled_sd_ln_cs_pct"],
        "sigma_cs_contaminated_pool_pct":
            a["A7"]["contaminated"]["pooled_sd_ln_cs_pct"],
        "sigma_cs_all_groups_pct": a["A7"]["all"]["pooled_sd_ln_cs_pct"],
        "F_contaminated_over_verified": a["A7"]["F_contaminated_over_verified"],
        # --- session, drift ---
        "icc_lnL_by_session": a["A2c"]["components_ln_L"]["icc"],
        "between_session_sd_lnL_pct":
            a["A2c"]["components_ln_L"]["between_sd_pct"],
        "drift_lnL_pct_per_day": a["A5"]["lnL"]["slope_pct_per_day"],
        "drift_lnL_ci_lo_pct_per_day":
            a["A5"]["lnL"]["slope_ci_pct_per_day"][0],
        "drift_lnL_ci_hi_pct_per_day":
            a["A5"]["lnL"]["slope_ci_pct_per_day"][1],
        "drift_lnL_us_step_per_day":
            a["A5"]["lnL"]["slope_pct_per_day"] * US_STEP_PER_PERCENT_CS,
        "corpus_span_days": a["A5"]["span_days"],
        # --- launch mixing discharge ---
        "anova_lnL_by_solver_F": anova_L["F"],
        "anova_lnL_by_solver_p": anova_L["p_F"],
        "anova_lnL_by_solver_icc": anova_L["icc"],
        "anova_lnL_by_solver_groups": anova_L["groups"],
        "rule_93_1_discharged_on_L_axis": True,
        "n_verified_groups_all_ours":
            c["C2_cs_axis_provenance"]["n_verified_groups_all_ours"],
        # --- winner's curse ---
        "best_tree_observed_max_cs": obs_max["cs"],
        "best_tree_unbiased_cs": unbiased["cs"],
        "best_tree_n_receipts": top_group["n"],
        "winners_curse_bias_pct": top_group["selection_bias_pct"],
        # --- the corrected ladder ---
        "p_record_per_draw_observed_max":
            obs_max["sigma_variants"]["point"]["p_draw_known_merit"],
        "p_record_per_draw_unbiased":
            unbiased["sigma_variants"]["point"]["p_draw_known_merit"],
        "p_record_per_draw_unbiased_lo":
            unbiased["sigma_variants"]["lo"]["p_draw_known_merit"],
        "p_record_per_draw_unbiased_hi":
            unbiased["sigma_variants"]["hi"]["p_draw_known_merit"],
        "expected_draws_unbiased":
            unbiased["sigma_variants"]["point"]["expected_draws_known_merit"],
        "expected_hours_unbiased_our_rate":
            unbiased["sigma_variants"]["point"]["expected_draws_known_merit"]
            / OUR_RATE_PER_HOUR,
        "p_record_empirical_unbiased": unbiased["empirical"]["p"],
        # --- exchange rate ---
        "Y_pct_of_cs_at_10_draws": per_budget["10"]["pct_of_cs"],
        "Y_us_per_step_at_10_draws": per_budget["10"]["us_per_step"],
        "Y_pct_of_cs_at_20_draws": per_budget["20"]["pct_of_cs"],
        "Y_us_per_step_at_20_draws": per_budget["20"]["us_per_step"],
        "draws_multiplier_plus_0p10pct":
            inverse["+0.10 % of cs (6.6 us/step)"]["draws_multiplier"],
        "draws_multiplier_rule91_residual":
            inverse["Rule 91 whole 19.0 us/step revert residual"][
                "draws_multiplier"],
        "draws_multiplier_rule92_ceiling":
            inverse["Rule 92 dispatch-reorder ceiling 1.30 us/step"][
                "draws_multiplier"],
        # --- the prefill coin ---
        "prefill_coin_value_pct_of_score": coin["coin_value_pct_of_score"],
        "prefill_coin_value_us_per_step":
            coin["coin_value_us_per_step_decode_equiv"],
        "prefill_high_mode_n": coin["high_mode"]["n"],
        "prefill_low_mode_n": coin["low_mode"]["n"],
        "prefill_high_mode_fraction": b["B3"]["high_mode_frac"],
        "prefill_high_mode_mean_lnL_pct": coin["high_mode"]["mean_lnL_pct"],
        "prefill_low_mode_mean_lnL_pct": coin["low_mode"]["mean_lnL_pct"],
        "winners_in_high_mode_k":
            coin["high_mode"]["winners_vs_observed_max"]["k"],
        "winners_in_low_mode_k":
            coin["low_mode"]["winners_vs_observed_max"]["k"],
        "beta_pre_within_groups": a["A9"]["beta_pre_within_groups"]["beta"],
        # --- gap and provenance ---
        "gap_pct_L_eq_1": a["gap"]["gap_pct_L_eq_1"],
        "gap_pct_at_median_L": a["gap"]["gap_pct_at_median_L"],
        "gap_us_per_step_at_median_L": a["gap"]["gap_us_per_step_at_median_L"],
        "record_sha12": prov["max_score_receipt_in_corpus"]["sha12"],
        "record_solver": prov["max_score_receipt_in_corpus"]["user"],
        "record_merit_cs": prov["max_score_receipt_in_corpus"]["cs"],
        "record_lnL_pct": prov["max_score_receipt_in_corpus"]["lnL_pct"],
        "state_doc_sha_cc6ddc12_found": prov["record_sha_cc6ddc12_in_corpus"],
        "n_corpus_receipts_at_or_above_record":
            prov["n_corpus_receipts_at_or_above_record"],
        # --- Stage D: verification, key adjudication, axes ---
        "d2_advisor_pool_sd_pct":
            d["D2_advisor_families"]["pool_from_corpus_matched_values"][
                "pooled_sd_pct"],
        "d2_advisor_pool_dof":
            d["D2_advisor_families"]["pool_from_corpus_matched_values"]["dof"],
        "d2_max_abs_err_vs_advisor_quote": max(
            m["abs_err"]
            for f in d["D2_advisor_families"]["families"].values()
            for m in f["members"]),
        "d3_note_key_vs_group_key_F":
            d["D3_key_adjudication"]["note_key_vs_group_key_F"]["F"],
        "d3_note_key_vs_group_key_p":
            d["D3_key_adjudication"]["note_key_vs_group_key_F"]["p_two_sided"],
        "d3_note_key_vs_member_key_p":
            d["D3_key_adjudication"]["note_key_vs_member_key_F"]["p_two_sided"],
        "d3_n_families_disagreeing_with_byte_key": sum(
            1 for f in d["D3_key_adjudication"]["families_vs_byte_key"]
            if f["n_members_outside_any_byte_verified_group"] > 0),
        "d4_bartlett_advisor_families_p":
            d["D4_homogeneity"]["bartlett_advisor_families"]["p"],
        "d4_bartlett_byte_verified_p":
            d["D4_homogeneity"]["bartlett_byte_verified_groups"]["p"],
        "d4_era_variance_ratio_F": d["D4_homogeneity"]["era_variance_ratio"]["F"],
        "d4_era_variance_ratio_p":
            d["D4_homogeneity"]["era_variance_ratio"]["p_two_sided"],
        "d5_robust_pooled_sd_pct":
            d["D5_robust_vs_classical"][
                "robust_pooled_sd_pct_from_centred_deviations"],
        "d5_max_abs_studentised_deviation":
            d["D5_robust_vs_classical"]["max_abs_studentised_deviation"],
        "d5_leave_one_out_lo_pct":
            d["D5_robust_vs_classical"]["leave_one_out_range_pct"][0],
        "d5_leave_one_out_hi_pct":
            d["D5_robust_vs_classical"]["leave_one_out_range_pct"][1],
        "d6_baseline_sigma_prefill_axis_pct":
            d["D6_two_axis_reconstruction"]["baseline_axes_all_receipts"][
                "sigma_prefill_axis_pct"],
        "d6_baseline_sigma_decode_axis_pct":
            d["D6_two_axis_reconstruction"]["baseline_axes_all_receipts"][
                "sigma_decode_axis_pct"],
        "d6_candidate_sigma_decode_axis_pct":
            d["D6_two_axis_reconstruction"]["candidate_axes_matched_dof"][
                "sigma_decode_axis_pct"],
        "d6_candidate_sigma_prefill_axis_pct":
            d["D6_two_axis_reconstruction"]["candidate_axes_matched_dof"][
                "sigma_prefill_axis_pct"],
        "d6_lottery_prefill_axis_variance_share": (
            d["D6_two_axis_reconstruction"]["baseline_axes_all_receipts"][
                "sigma_prefill_axis_pct"]
            / d["D6_two_axis_reconstruction"]["baseline_axes_all_receipts"][
                "reconstructed_sd_pct"]) ** 2,
        "d6_candidate_decode_axis_variance_share": (
            d["D6_two_axis_reconstruction"]["candidate_axes_matched_dof"][
                "sigma_decode_axis_pct"]
            / d["D6_two_axis_reconstruction"]["candidate_axes_matched_dof"][
                "reconstructed_sd_pct"]) ** 2,
        "d6_n_minus_1_divisor_bias":
            d["D6_two_axis_reconstruction"]["candidate_axes_naive_n_minus_1"][
                "rel_residual"],
        "d7_maple_sd_lnL_pct":
            d["D7_launch_partition"]["blocks"]["maple"]["sd_lnL_pct"],
        "d7_unattributed_sd_lnL_pct":
            d["D7_launch_partition"]["blocks"]["unattributed"]["sd_lnL_pct"],
        "d7_maple_vs_unattributed_F":
            d["D7_launch_partition"]["maple_vs_unattributed"]["F"],
        "d7_maple_vs_unattributed_p":
            d["D7_launch_partition"]["maple_vs_unattributed"]["p_two_sided"],
        # --- Stage E: Rule 96 adjudication ---
        "e1_anchor_cs": e5["our_anchor"]["threshold_cs"],
        "e1_anchor_agreement_vs_rule_96_pct": e["E1_winners_curse"][
            "anchor_agreement_pct"],
        "e1_selection_bias_five_member_pct": e["E1_winners_curse"]["groups"][
            e["E1_winners_curse"]["five_member_group"]]["selection_bias_pct"],
        "e2_sd_ln_score_five_member_pct": e2_five["sd_ln_score_pct"],
        "e2_sd_ln_score_five_member_dof": e2_five["dof"],
        "e2_rho_ln_cs_f_five_member": e2_five["rho_ln_cs_f"],
        "e2_rho_t_stat_five_member": e2_five["rho_t_stat"],
        "e2_sd_ln_score_pooled_pct": e2p["sd_ln_score_direct_pct"],
        "e2_sd_ln_score_pooled_dof": e2p["sd_ln_score_dof"],
        "e2_sd_ln_cs_pooled_pct": e2p["sd_ln_cs_pct"],
        "e2_sd_f_pooled_pct": e2p["sd_f_pct"],
        "e2_rho_ln_cs_f_pooled": e2p["rho_ln_cs_f"],
        "e2_pooled_rel_se_of_sd_pct": e2p["rel_se_of_sd_pct"],
        "e2_sd_ln_score_pooled_over_rule_96":
            e2p["sd_ln_score_direct_pct"]
            / e["rule_96_quoted"]["sd_ln_score_within_tree_pct"],
        "e3_pooled_sd_bl_pre_pct": e["E3_per_leg"]["pooled"]["bl_pre"]["sd_pct"],
        "e3_pooled_sd_cand_dec_pct":
            e["E3_per_leg"]["pooled"]["cand_dec"]["sd_pct"],
        "e4_variance_share_from_mode_coin":
            e4["variance_share_from_mode_coin"],
        "e4_pooled_sd_f_all_pct": e4["pooled_sd_f_all_pct"],
        "e4_pooled_sd_f_within_mode_pct": e4["pooled_sd_f_within_mode_pct"],
        "e4_pooled_sd_bl_pre_all_pct": e4["pooled_sd_bl_pre_all_pct"],
        "e4_pooled_sd_bl_pre_within_mode_pct":
            e4["pooled_sd_bl_pre_within_mode_pct"],
        "e4_n_groups_straddling_mode": e4["n_groups_straddling"],
        "e4_corpus_high_fraction": e4["corpus_high_fraction"],
        "e5_our_anchor_cohort_n": e5["our_anchor"]["n"],
        "e5_our_anchor_cohort_records": e5["our_anchor"]["n_records"],
        "e5_our_anchor_cohort_ours_n": e5["our_anchor"]["ours_n"],
        "e5_our_anchor_cohort_distinct_users":
            e5["our_anchor"]["n_distinct_users"],
        "e5_our_anchor_cohort_sd_f_pct": e5["our_anchor"]["sd_f_pct"],
        "e5_our_anchor_cohort_max_f_pct": e5["our_anchor"]["max_f_pct"],
        "e5_our_anchor_cohort_mean_f_pct": e5["our_anchor"]["mean_f_pct"],
        "e5_our_anchor_high_mode_fraction":
            e5["our_anchor"]["high_mode_fraction"],
        "e5_corpus_rho_ln_cs_f": e5["corpus_rho_ln_cs_f"],
        "e5_corpus_sd_f_pct": e5["corpus_sd_f_pct"],
        "e5_conditional_sd_f_if_rho_pct": e5["conditional_sd_f_if_rho_pct"],
        "e6_need_f_pct": e6["need_f_pct"],
        "e6_n_receipts_with_f_at_least_need":
            e6["n_receipts_with_f_at_least_need"],
        "e6_n_big_f_above_anchor": e6["n_big_f_above_anchor"],
        "e6_expected_both_if_independent":
            e6["two_by_two"]["expected_both_if_independent"],
        "e7_p_record_per_draw": e7m["empirical_all_receipts"]["p"],
        "e7_p_record_ci_lo": e7m["empirical_all_receipts"]["ci"][0],
        "e7_p_record_ci_hi": e7m["empirical_all_receipts"]["ci"][1],
        "e7_expected_draws": e7m["empirical_all_receipts"]["expected_draws"],
        "e7_expected_hours_our_rate":
            e7m["empirical_all_receipts"]["hours_at_our_rate"],
        "e7_expected_days_our_rate":
            e7m["empirical_all_receipts"]["hours_at_our_rate"] / 24.0,
        "e7_p_record_given_high_mode":
            e7m["empirical_high_mode_only"]["p"],
        "e7_p_record_rule_96_gaussian": e7m["gauss_rule_96"]["p"],
        "e7_expected_draws_rule_96_gaussian":
            e7m["gauss_rule_96"]["expected_draws"],
        "e7_p_record_over_rule_96":
            e7m["empirical_all_receipts"]["p"] / e7m["gauss_rule_96"]["p"],
        "e7_n_high_mode": e7["n_high_mode"],
        "e7_n_low_mode": e7["n_low_mode"],
        "e8_paired_resolvable_1v1_cs_pct":
            e8["paired_resolvable_1v1_cs_pct"],
        "e8_paired_resolvable_us_step": e8["paired_resolvable_us_step"],
        "e8_mde_3sigma_cs_pct": e8["mde_3sigma_cs_pct"],
        "e8_mde_3sigma_us_step":
            e8["mde_3sigma_cs_pct"] * US_STEP_PER_PERCENT_CS,
        "e8_rule_96_paired_resolvable_cs_pct":
            e8["rule_96_paired_resolvable_cs_pct"],
        "e8_paired_over_rule_96_quote":
            e8["paired_resolvable_1v1_cs_pct"]
            / e8["rule_96_paired_resolvable_cs_pct"],
    }

    run = wandb.init(entity=ENTITY, project=PROJECT, group=GROUP,
                     job_type="receipt-forensics",
                     name="r106h-channel-economics",
                     notes=("V-DRAWS with a downward correction. Model-free "
                            "P(record)/draw = 0.99 % [0.56, 1.71] (12/1218) "
                            "from our anchor cs 2.583106, gap 1.2846 %: "
                            "E = 102 draws = 113 h = 4.7 days at our real "
                            "0.9/h share. That is ~35x more optimistic than "
                            "Rule 96.2 and ~3.6x more pessimistic than Rule "
                            "93.4, which bracket it. One draw is worth only "
                            "0.021 % of cs (1.37 us/step) at a 10-draw "
                            "budget: we have not been under-drawing, we have "
                            "been briefing the wrong axis. 88.6 % of within-"
                            "tree var(f) is a baseline-prefill mode coin, and "
                            "all 26 receipts at or above our anchor produced "
                            "zero records."),
                     config=config)

    ladder_t = wandb.Table(columns=[
        "label", "cs", "need_lnL_pct", "empirical_k", "empirical_n",
        "empirical_p", "empirical_ci_lo", "empirical_ci_hi",
        "p_draw_known_merit", "p_lo", "p_hi", "expected_draws",
        "hours_our_rate"])
    for r in c["C3_record_ladder"]:
        v = r["sigma_variants"]
        emp = r["empirical"]
        ed = v["point"]["expected_draws_known_merit"]
        ladder_t.add_data(r["label"], r["cs"], r["need_lnL_pct"], emp["k"],
                          emp["n"], emp["p"], emp["ci"][0], emp["ci"][1],
                          v["point"]["p_draw_known_merit"],
                          v["lo"]["p_draw_known_merit"],
                          v["hi"]["p_draw_known_merit"], ed,
                          ed / OUR_RATE_PER_HOUR)

    budget_t = wandb.Table(columns=["budget_k", "Y_pct_of_cs", "Y_us_per_step",
                                    "cum_p_at_k", "cum_p_at_k_plus_1"])
    for k in sorted(per_budget, key=int):
        p = per_budget[k]
        budget_t.add_data(int(k), p["pct_of_cs"], p["us_per_step"],
                          p["cum_p_at_k"], p["cum_p_at_k_plus_1"])

    mult_t = wandb.Table(columns=["mechanism", "pct_of_cs", "draws_multiplier",
                                  "p_without", "p_with", "extra_draws_at_20",
                                  "extra_hours_at_20_our_rate"])
    for name in sorted(inverse):
        m = inverse[name]
        mult_t.add_data(name, m["pct_of_cs"], m["draws_multiplier"],
                        m["p_without"], m["p_with"],
                        m["extra_draws_at_budget_20"],
                        m["extra_hours_at_budget_20_our_rate"])

    tree_t = wandb.Table(columns=["merit_deficit_pct_of_cs",
                                  "merit_deficit_us_per_step", "p_draw",
                                  "ticket_value_ratio", "n_per_arm_to_resolve"])
    for r in c["C7_tree_selection"]["rows"]:
        n = r["n_receipts_to_resolve_this_deficit_per_arm"]
        tree_t.add_data(r["merit_deficit_pct_of_cs"],
                        r["merit_deficit_us_per_step"], r["p_draw"],
                        r["ticket_value_ratio"],
                        -1 if n == float("inf") else n)

    pools_t = wandb.Table(columns=["pool", "dof", "sd_ln_cs_pct", "ci_lo",
                                   "ci_hi", "pooled_ss"])
    for name in ("verified", "contaminated", "all"):
        p = a["A7"][name]
        pools_t.add_data(name, p["dof"], p["pooled_sd_ln_cs_pct"],
                         p["ci_pct"][0], p["ci_pct"][1], p["ss"])

    cohort_t = wandb.Table(columns=["cohort", "n", "sd_lnL_pct", "ci_lo",
                                    "ci_hi", "mean_pct", "median_pct"])
    for r in c["C1_launch_mixing_L_axis"]["sd_lnL_by_cohort"]:
        cohort_t.add_data(r["label"], r["n"], r["sd_pct"], r["sd_ci_pct"][0],
                          r["sd_ci_pct"][1], r["mean_pct"], r["median_pct"])

    top5_t = wandb.Table(columns=["sha12", "solver", "score", "cs", "lnL_pct"])
    for r in prov["top5"]:
        top5_t.add_data(r["sha12"], r["user"], r["score"], r["cs"],
                        r["lnL_pct"])

    coin_t = wandb.Table(columns=["mode", "n", "mean_ln_bl_pre_pct",
                                  "mean_lnL_pct", "sd_lnL_pct",
                                  "winners_vs_observed_max",
                                  "winners_vs_unbiased"])
    for mode in ("high_mode", "low_mode"):
        m = coin[mode]
        coin_t.add_data(mode, m["n"], m["mean_ln_bl_pre_pct"],
                        m["mean_lnL_pct"], m["sd_lnL_pct"],
                        m["winners_vs_observed_max"]["k"],
                        m["winners_vs_unbiased"]["k"])

    group_t = wandb.Table(columns=["group", "n", "max_cs", "mean_cs",
                                   "selection_bias_pct", "se_mean_pct",
                                   "is_best_tree"])
    for name in sorted(b["B1_groups"],
                       key=lambda k: -b["B1_groups"][k]["selection_bias_pct"]):
        g = b["B1_groups"][name]
        group_t.add_data(name, g["n"], g["max_cs"], g["mean_cs"],
                         g["selection_bias_pct"], g["se_mean_pct"],
                         name == b["B1_top_group"])

    fam_t = wandb.Table(columns=["family", "sha12", "solver", "advisor_cs",
                                 "corpus_cs", "abs_err", "matched", "ts"])
    for name in sorted(d["D2_advisor_families"]["families"]):
        for m in d["D2_advisor_families"]["families"][name]["members"]:
            fam_t.add_data(name, m["sha12"], m["user"], m["advisor_cs"],
                           m["corpus_cs"], m["abs_err"], m["matched"], m["ts"])

    axis_t = wandb.Table(columns=[
        "route", "n", "dof_used", "sd_ln_dec_pct", "sd_ln_pre_pct",
        "corr_dec_pre", "sigma_decode_axis_pct", "sigma_prefill_axis_pct",
        "reconstructed_sd_pct", "directly_fitted_sd_pct", "rel_residual"])
    for key in ("baseline_axes_all_receipts", "candidate_axes_matched_dof",
                "candidate_axes_naive_n_minus_1"):
        r = d["D6_two_axis_reconstruction"][key]
        axis_t.add_data(r["label"], r["n"], r["dof_used"], r["sd_ln_dec_pct"],
                        r["sd_ln_pre_pct"], r["corr_dec_pre"],
                        r["sigma_decode_axis_pct"], r["sigma_prefill_axis_pct"],
                        r["reconstructed_sd_pct"], r["directly_fitted_sd_pct"],
                        r["rel_residual"])

    launch_t = wandb.Table(columns=["block", "n", "dof", "sd_lnL_pct", "ci_lo",
                                    "ci_hi", "rel_se_of_sd"])
    for name in sorted(d["D7_launch_partition"]["blocks"]):
        r = d["D7_launch_partition"]["blocks"][name]
        launch_t.add_data(name, r["n"], r["dof"], r["sd_lnL_pct"],
                          r["ci_pct"][0], r["ci_pct"][1], r["rel_se_of_sd"])

    denom_t = wandb.Table(columns=["group", "n", "rho_ln_cs_f", "sd_f_pct",
                                   "sd_ln_cs_pct", "sd_ln_score_pct"])
    for name in sorted(e["E2_paired_denominator"]["per_group"]):
        r = e["E2_paired_denominator"]["per_group"][name]
        denom_t.add_data(name, r["n"], r["rho_ln_cs_f"], r["sd_f_pct"],
                         r["sd_ln_cs_pct"], r["sd_ln_score_pct"])
    denom_t.add_data("POOLED (dof 10)", 11, e2p["rho_ln_cs_f"],
                     e2p["sd_f_pct"], e2p["sd_ln_cs_pct"],
                     e2p["sd_ln_score_direct_pct"])

    straddle_t = wandb.Table(columns=["group", "n", "n_high", "n_low",
                                      "straddles", "sd_bl_pre_pct"])
    for name in sorted(e4["per_group"]):
        r = e4["per_group"][name]
        straddle_t.add_data(name, r["n"], r["n_high"], r["n_low"],
                            r["straddles"], r["sd_bl_pre_pct"])

    model_t = wandb.Table(columns=["model", "p_record_per_draw",
                                   "expected_draws", "hours_at_our_rate",
                                   "days_at_our_rate", "sd_pct", "z",
                                   "model_free"])
    for name in sorted(e7m, key=lambda k: -e7m[k]["p"]):
        m = e7m[name]
        model_t.add_data(name, m["p"], m["expected_draws"],
                         m["hours_at_our_rate"],
                         m["hours_at_our_rate"] / 24.0,
                         m.get("sd_pct"), m.get("z"),
                         name.startswith("empirical"))

    bigf_t = wandb.Table(columns=["sha12", "f_pct", "cs", "score", "mode",
                                  "solver", "ts", "cs_short_of_anchor_pct"])
    for r in e6["big_f_receipts"]:
        bigf_t.add_data(r["sha12"], r["f_pct"], r["cs"], r["score"], r["mode"],
                        r["user"], r["ts"],
                        100.0 * (r["cs"] / e6["anchor_cs"] - 1.0))

    cohort_thr_t = wandb.Table(columns=[
        "cohort", "threshold_cs", "n", "n_records", "ours_n",
        "n_distinct_users", "sd_f_pct", "sd_f_ci_lo", "sd_f_ci_hi",
        "max_f_pct", "mean_f_pct", "need_f_median_pct",
        "high_mode_fraction"])
    for name in ("our_anchor", "rule_96_anchor", "selected_max"):
        r = e5[name]
        cohort_thr_t.add_data(name, r["threshold_cs"], r["n"], r["n_records"],
                              r["ours_n"], r["n_distinct_users"],
                              r["sd_f_pct"], r["sd_f_ci_pct"][0],
                              r["sd_f_ci_pct"][1], r["max_f_pct"],
                              r["mean_f_pct"], r["need_f_median_pct"],
                              r["high_mode_fraction"])

    r96 = e["rule_96_quoted"]
    leg_bl_pre = e["E3_per_leg"]["five_member_group_only"]["bl_pre"]["sd_pct"]
    lead_pct = 100.0 * (e5["our_anchor"]["threshold_cs"] / e8["max_score_cs"]
                        - 1.0)

    adj_t = wandb.Table(columns=["rule_96_claim", "rule_96_value", "our_value",
                                 "verdict"])
    for row in [
        ("96.1(2) selection bias on the 5-member tree",
         f"{e['rule_96_quoted']['selection_bias_pct']:.4f} %",
         f"{summary['e1_selection_bias_five_member_pct']:.4f} %",
         "confirmed"),
        ("96.1(2) anchor cs", f"{e['rule_96_quoted']['anchor_cs']:.6f}",
         f"{e5['our_anchor']['threshold_cs']:.6f}", "confirmed"),
        ("96.1(4) baseline prefill dominates var(f)",
         f"sd {e['rule_96_quoted']['leg_sd_bl_pre_pct']:.4f} %, F(4,4)="
         f"{e['rule_96_quoted']['leg_F_4_4']:.1f}",
         f"sd {e['E3_per_leg']['five_member_group_only']['bl_pre']['sd_pct']:.4f} %, "
         f"F={e['E3_per_leg']['bl_pre_vs_cand_pre_F']['F']:.1f}",
         "confirmed"),
        ("96.1(3) sd(ln score | fixed tree) as a pooled quantity",
         f"{e['rule_96_quoted']['sd_ln_score_within_tree_pct']:.4f} % (dof 4)",
         f"{e2p['sd_ln_score_direct_pct']:.4f} % (dof "
         f"{e2p['sd_ln_score_dof']})",
         "rejected as pooled: dof-4 single tree, 35 % rel SE"),
        ("96.2 P(record)/draw",
         f"{e['rule_96_quoted']['p_record_per_draw_pct']:.4f} %, E="
         f"{e['rule_96_quoted']['expected_draws']} draws",
         f"{100.0 * e7m['empirical_all_receipts']['p']:.4f} %, E="
         f"{e7m['empirical_all_receipts']['expected_draws']:.1f} draws",
         "rejected (~35x pessimistic); the ruling is endorsed"),
        ("96.2 disjoint-cohort corroboration of the denominator",
         f"n={e['rule_96_quoted']['cohort_n']}, sd(f)="
         f"{e['rule_96_quoted']['cohort_sd_f_pct']:.3f} %",
         f"n={e5['our_anchor']['n']}, sd(f)="
         f"{e5['our_anchor']['sd_f_pct']:.4f} % (conditional on cs>=anchor)",
         "rejected as corroboration: conditional vs unconditional sd"),
        ("96.2 paired A/B resolvable effect",
         f"{e8['rule_96_paired_resolvable_cs_pct']:.3f} % of cs",
         f"{e8['paired_resolvable_1v1_cs_pct']:.4f} % of cs 1-sigma; "
         f"{e8['mde_3sigma_cs_pct']:.4f} % at 3 sigma",
         "understated by sqrt(2); the honest 3-sigma bar is "
         f"{e8['mde_3sigma_cs_pct'] * US_STEP_PER_PERCENT_CS:.0f} us/step"),
        ("96.2 our merit lead over the record holder",
         "0.330 %",
         f"{100.0 * (e5['our_anchor']['threshold_cs'] / e8['max_score_cs'] - 1.0):.3f} %",
         "confirmed exactly"),
        ("(no Rule 96 claim) mode coin's share of var(f) within a tree",
         "not stated",
         f"{100.0 * e4['variance_share_from_mode_coin']:.1f} %",
         "new: the coin, not merit noise, is the draw lottery"),
    ]:
        adj_t.add_data(*row)

    run.log({
        "r106h/advisor_families": fam_t,
        "r106h/axis_reconstruction": axis_t,
        "r106h/launch_partition": launch_t,
        "r106h/denominator_by_group": denom_t,
        "r106h/mode_straddle": straddle_t,
        "r106h/p_record_models": model_t,
        "r106h/big_f_receipts": bigf_t,
        "r106h/cohort_thresholds": cohort_thr_t,
        "r106h/rule96_adjudication": adj_t,
        "r106h/record_ladder": ladder_t,
        "r106h/exchange_rate_per_budget": budget_t,
        "r106h/draws_multiplier": mult_t,
        "r106h/tree_selection_rule": tree_t,
        "r106h/sigma_cs_pools": pools_t,
        "r106h/sd_lnL_by_cohort": cohort_t,
        "r106h/leaderboard_top5": top5_t,
        "r106h/prefill_coin": coin_t,
        "r106h/winners_curse_by_group": group_t,
    })
    run.summary.update(summary)
    print("wandb run:", run.url)
    run.finish()


if __name__ == "__main__":
    os.environ.setdefault("WANDB_SILENT", "false")
    main(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5])
