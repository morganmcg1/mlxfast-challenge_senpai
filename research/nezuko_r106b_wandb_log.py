#!/usr/bin/env python3
"""Publish the R106-B Stage-0 revert-residual gate to W&B.

Everything logged is parsed from the committed `stage0-analysis.json`; nothing is
re-measured here, so the run and the report cannot disagree.

Usage: nezuko_r106b_wandb_log.py STAGE0_ANALYSIS_JSON
"""
import json
import os
import sys

import wandb

ENTITY = "wandb-applied-ai-team"
PROJECT = "mlxfast-maple"
GROUP = "r106-b-revert-residual-forensics"

CS_PER_US_STEP = 0.015228 / 100.0  # 1 us/step of decode is 0.015228 % of cs
US_STEP_PER_PERCENT_CS = 65.67

ARTIFACTS = {
    "receipt_corpus_frozen_json": (
        19936617,
        "d450b5b5dc895f0d2d4de52d790035e88ea2e55255fed1ae04c80a9a7c70c12b"),
    "stage0_analysis_json": (
        44430,
        "02fc1847f09252d344716d52b57f1fa060cbf21ea4b40e103c197c601e2ed908"),
    "replicate_identity_verified_json": (
        16221,
        "f064c482550e44954f18e654289589c30d4dbf9d348805a533a01e413045e0ff"),
    "stage0_preregistration_md": (
        8228,
        "f718daf66a0cb47ae6b570b8516901d43184eae832cfe6b349c05b0a70f91646"),
    "pull_corpus_py": (
        3236,
        "63e9494775c57d17b83c64d89041f8a307d88c9c5df90a7a9a8561414cd1ac7e"),
    "verify_replicates_py": (
        9455,
        "9933580d0500df5230e6dd418bf46ff5d7990969fb148bf89c36f4ac8fa92589"),
    "stage0_ci_py": (
        17223,
        "bc77c7a82aadff4ebd03cd87fda5bce53de996cd949ff6f981b6588fa6031b80"),
}


def main(path):
    d = json.load(open(path))
    gate = d["gate"]
    est = d["estimand"]
    day = d["day_decomposition"]
    sel = d["selection_diagnostic"]
    vi = d["verified_identity"]
    prim = {i["axis"]: i for i in gate["primary_intervals"]}

    config = {
        "campaign": "maple",
        "student": "maple-nezuko",
        "assignment_id": "maple-r106-b-revert-residual-forensics",
        "revision_id": "r106-b-rev1",
        "pr": 616,
        "base_sha": "8e8faf28635ad0bba81243ae98b56cd00eeac16d",
        "stage": "stage-0 only (hard gate stopped the round)",
        "official_receipts_consumed": 0,
        "rule_88_no_receipts": True,
        "sources_or_vendor_modified": False,
        "estimator": "SE = sd * sqrt(1/n_f + 1/n_r), Student-t 95%",
        "primary_pool": "DP-VERIFIED",
        "primary_pool_rationale":
            "narrowest defensible sigma, i.e. the hardest available test for N-0",
        "arm_frontier_sha": "bd33883eb89209c9714c8c570e399613ecbaa848",
        "arm_r_sha": "ef055b9b1956e8056267972308fd7deddd89649d",
        "n_frontier_receipts": est["n_frontier"],
        "n_arm_r_receipts": est["n_arm_r"],
        "arm_separation_hours": day["arm_separation_hours"],
        "prereg_deviation_declared": d["preregistration_deviation"]["declared"],
        "prereg_deviation_miss": d["preregistration_deviation"]["miss"],
        "prereg_deviation_substitute":
            d["preregistration_deviation"]["substitute"],
        "replicate_identity": vi["identity"],
        "benchmark_id": "1854efdf-feba-4773-bae9-b80520881a74",
        "corpus_receipts": d["inputs"]["corpus"]["receipts_with_metrics"],
    }
    for name, (nbytes, digest) in ARTIFACTS.items():
        config["artifact_%s_bytes" % name] = nbytes
        config["artifact_%s_sha256" % name] = digest

    run = wandb.init(entity=ENTITY, project=PROJECT, group=GROUP,
                     job_type="receipt-forensics",
                     name="r106b-stage0-revert-residual-gate",
                     notes=("Stage-0 confidence interval on the ~19 us/step "
                            "revert residual. Outcome N-0: both primary "
                            "intervals cover zero, so stages 1 and 2 were not "
                            "run and there is nothing to attribute."),
                     config=config)

    summary = {
        "outcome": gate["outcome"],
        "outcome_reason": gate["outcome_reason"],
        "residual_D_us_step": est["R_D_us"],
        "residual_T_us_step": est["R_T_us"],
        "residual_D_pct_cs": est["R_D_us"] * CS_PER_US_STEP * 100.0,
        "residual_T_pct_cs": est["R_T_us"] * CS_PER_US_STEP * 100.0,
        "dof_across_day": day["dof_across_day"],
        "n_groups_considered": vi["n_groups_considered"],
        "n_groups_verified": vi["n_groups_verified"],
        "n_groups_rejected_vendor_diff": len(vi["rejected"]),
        "selection_diag_D_range_us": sel["D_range_us"],
        "selection_diag_range_over_residual": sel["range_over_residual"],
        "selection_diag_n": sel["n"],
        "stage1_run": False,
        "stage2_run": False,
    }
    for axis, key in (("D", "ci_D"), ("T", "ci_T")):
        ci = prim[key]
        summary.update({
            "primary_%s_sd_us" % axis: ci["sd"],
            "primary_%s_se_us" % axis: ci["se"],
            "primary_%s_dof" % axis: ci["dof"],
            "primary_%s_ci_lo_us" % axis: ci["lo"],
            "primary_%s_ci_hi_us" % axis: ci["hi"],
            "primary_%s_half_width_us" % axis: ci["half_width"],
            "primary_%s_z" % axis: ci["z"],
            "primary_%s_covers_zero" % axis: ci["covers_zero"],
            "primary_%s_breakeven_sigma_us" % axis: ci["breakeven_sigma"],
            "primary_%s_mde_pct_cs" % axis:
                ci["half_width"] / US_STEP_PER_PERCENT_CS,
        })
    summary["primary_P_sd_us"] = d["pools"]["DP-VERIFIED"]["sd_P"]
    summary["decode_over_prefill_sd_ratio"] = (
        d["pools"]["DP-VERIFIED"]["sd_D"] / d["pools"]["DP-VERIFIED"]["sd_P"])
    run.summary.update(summary)

    pools = wandb.Table(columns=[
        "pool", "axis", "sd_us", "dof", "diff_us", "se_us", "t975",
        "ci_lo_us", "ci_hi_us", "z", "covers_zero", "breakeven_sigma_us",
        "estimable", "is_primary"])
    for name in sorted(d["pools"]):
        p = d["pools"][name]
        for axis, key in (("D", "ci_D"), ("T", "ci_T")):
            ci = p.get(key)
            if not ci:
                continue
            pools.add_data(name, axis, ci["sd"], ci["dof"], ci["diff"],
                           ci["se"], ci["t975"], ci["lo"], ci["hi"], ci["z"],
                           ci["covers_zero"], ci["breakeven_sigma"],
                           ci["estimable"], name == "DP-VERIFIED")

    spans = wandb.Table(columns=["group", "n", "first", "last"])
    for s in day["replicate_spans"]:
        spans.add_data(s["group"], s["n"], s["first"], s["last"])

    seldiag = wandb.Table(columns=["receipt_id8", "createdAt", "D_us_tok"])
    for r in sel["receipts"]:
        seldiag.add_data(r["id8"], r["ts"], r["D"])

    rejected = wandb.Table(columns=["group", "n", "n_problems",
                                    "first_problem"])
    for r in vi["rejected"]:
        probs = r["problems"]
        rejected.add_data(r["group"], r["n"], len(probs), probs[0])

    run.log({
        "stage0/pool_intervals": pools,
        "stage0/replicate_spans": spans,
        "stage0/selection_diagnostic": seldiag,
        "stage0/rejected_groups_vendor_diff": rejected,
    })
    print("wandb run:", run.url)
    run.finish()


if __name__ == "__main__":
    os.environ.setdefault("WANDB_SILENT", "false")
    main(sys.argv[1])
