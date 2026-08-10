#!/usr/bin/env python3
"""Publish the R106-H channel-economics result to W&B.

Everything logged is parsed from the committed stage-a/b/c JSON, so the run and
`research/maple-nezuko-r106h-channel-economics.md` cannot disagree.

Usage: nezuko_r106h_wandb_log.py STAGE_A_JSON STAGE_B_JSON STAGE_C_JSON
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


def main(path_a, path_b, path_c):
    a = json.load(open(path_a))
    b = json.load(open(path_b))
    c = json.load(open(path_c))

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

    config = {
        "campaign": "maple",
        "student": "maple-nezuko",
        "assignment_id": "maple-r106-b-revert-residual-forensics",
        "revision_id": "r106-h-rev2",
        "pr": 616,
        "base_sha": "174107475ef88b976a2cc085af14cd9601e2e2bd",
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
        "verdict": "V-DRAWS with a downward correction; V-SESSION and V-DRIFT weak",
        "outcome_N_FIT": False,
        "outcome_V_DRAWS": True,
        "outcome_V_SESSION": True,
        "outcome_V_DRIFT": True,
        "outcome_V_BASELINE": True,
        "outcome_V_COMMON_prefill_beta_zero": True,
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
    }

    run = wandb.init(entity=ENTITY, project=PROJECT, group=GROUP,
                     job_type="receipt-forensics",
                     name="r106h-channel-economics",
                     notes=("V-DRAWS with a downward correction: the campaign's "
                            "3.2 %/draw is an order statistic; on unbiased "
                            "merit it is 1.19 %/draw, E=84 draws, 94 h at our "
                            "real 0.9/h share. One draw = 1.37 us/step of "
                            "decode at a 10-draw budget."),
                     config=config)

    ladder_t = wandb.Table(columns=[
        "label", "cs", "need_lnL_pct", "empirical_k", "empirical_n",
        "empirical_p", "empirical_ci_lo", "empirical_ci_hi",
        "p_draw_known_merit", "p_lo", "p_hi", "expected_draws",
        "hours_our_rate"])
    for r in c["C3_record_ladder"]:
        v = r["sigma_variants"]
        e = r["empirical"]
        ed = v["point"]["expected_draws_known_merit"]
        ladder_t.add_data(r["label"], r["cs"], r["need_lnL_pct"], e["k"],
                          e["n"], e["p"], e["ci"][0], e["ci"][1],
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

    run.log({
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
    main(sys.argv[1], sys.argv[2], sys.argv[3])
