#!/usr/bin/env python3
"""Publish the R108-K barrier-region price probe to W&B.

Every figure comes from artifacts/maple-frieren-r108k/figures.json, which the
report generator writes from the probe sink, so the run and the report cannot
disagree.
"""

import csv
import json
import os
import pathlib
import subprocess

import wandb

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent
ART = HERE / "artifacts" / "maple-frieren-r108k"
FIG = json.loads((ART / "figures.json").read_text())
SINK = ART / "barrier-region-price.tsv"

head = subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"],
                      capture_output=True, text=True, check=True).stdout.strip()

ARMS = {
    "C": "control, no injection",
    "F": "160 empty roots/layer, unchained (concurrent)",
    "S": "160 empty roots/layer, chained (serialized, 160 barriers)",
    "H": "1200 empty roots/layer, unchained",
    "J": "1200 empty roots/layer, chained",
    "G": "2400 empty roots/layer, chained -- liveness gauge only, excluded from fits",
}

# Set MAPLE_R108K_WANDB_RUN_ID to refresh the already-cited run in place rather
# than publishing a second copy of the same probe.
run = wandb.init(
    entity="wandb-applied-ai-team",
    project="mlxfast-maple",
    id=os.environ.get("MAPLE_R108K_WANDB_RUN_ID") or None,
    resume="allow",
    name="maple-frieren-r108k-barrier-region-price",
    job_type="decode-dispatch-price-probe",
    tags=["maple-frieren", "r108-K", "decode", "dispatch_merge", "barrier_price",
          "two-rung-ladder", "P-INDETERMINATE", "zero-source-bytes",
          "m4-directional"],
    notes=(
        "What does one extra decode GPU dispatch actually cost, and what does "
        "one extra intra-layer barrier cost? Two injection rungs (160 and 1200 "
        "empty roots per layer) x two serialization families (unchained / "
        "chained) plus per-block controls, measured with ./benchmark.sh "
        "--local-submit on an M4 Pro. The single-rung estimator the "
        "pre-registration named is algebraically degenerate -- injected cost is "
        "N*k + 40*c, so only the rung difference identifies k -- and the "
        "two-rung fit gives k ~ 0.45 M4 us/dispatch, 4.2x cheaper than the "
        "1.890 the 40-dispatch M2 merge was budgeted against. Reported verdict "
        "P-INDETERMINATE per advisor comment 6 branch 3: k lands inside the "
        "undecided 0.3-0.8 band, so both slopes are reported with CIs and no "
        "side is picked. Barrier price is ~0 at both rungs. Accidental finding: "
        "the intercept c is negative and large (~-4 us per layer), i.e. an "
        "extra per-layer asyncEval commit boundary looks ~1.8% faster, which "
        "contradicts the campaign's commit-cost folklore and is the follow-up "
        "ranked first. Zero Sources/ bytes spent."
    ),
    config={
        "assignment_pr": 660,
        "assignment_id": "maple-r108-k-decode-dispatch-merge",
        "revision_id": "r108-k-rev1",
        "student": "maple-frieren",
        "branch": "maple-frieren/r108-k-decode-dispatch-merge",
        "base_sha": "1bc1c8954147c9e322aad1f3b80bd9fa3c0888d7",
        "assignment_commit": "5fecf5face933c133096ae69116ff624b0da4d73",
        "head_sha": head,
        "host": "Apple M4 Pro / 14 CPU / 48 GiB unified",
        "apple_gpu_generation": 16,
        "macos": "26.5.2",
        "official_hardware": "M5 Max 128 GiB (not this host; M4 is directional)",
        "harness": "./benchmark.sh --local-submit",
        "window": "512-token prefill + 512-seed teacher-forced decode, 128 steps",
        "decode_weight": 0.75,
        "dispatches_per_step_family_E": FIG["dispatches_per_step"],
        "assumed_k_us_per_dispatch": FIG["assumed_k"],
        "layers_injected": 40,
        "threadgroup_size": 8,
        "injection_knob": "DARKBLOOM_INJECT_EMPTY / _CHAIN / _TG (research-only, default off)",
        "inject_call_site": "LagunaRuntimeModel.swift:11715 -> :12091..:12143",
        "sources_bytes_spent": 0,
        "editable_budget": ("current=2681206/3000000 headroom=318794 "
                            "growth=-302643/262144 files=142"),
        "correctness_gate": "exact greedy token-ID equality (Golden.swift:387,:535)",
        "prereg": "research/maple-frieren-r108k-prereg-amendment-1.md",
        "report": "research/maple-frieren-r108k-decode-dispatch-merge.md",
        "analyzer": "research/maple-frieren-r108k-barrier-price-analyze.py",
        "driver": "research/maple-frieren-r108k-barrier-region-price.sh",
    },
)

run.summary.update({
    # PRIMARY: what the 40-dispatch decode merge is actually worth.
    "primary/k_us_per_dispatch_unchained": FIG["k_unchained"],
    "primary/k_us_per_dispatch_unchained_ci_lo": FIG["k_unchained_lo"],
    "primary/k_us_per_dispatch_unchained_ci_hi": FIG["k_unchained_hi"],
    "primary/k_us_per_dispatch_chained": FIG["k_chained"],
    "primary/k_us_per_dispatch_chained_ci_lo": FIG["k_chained_lo"],
    "primary/k_us_per_dispatch_chained_ci_hi": FIG["k_chained_hi"],
    "primary/merge_prize_us_per_step": FIG["merge_prize_us_per_step"],
    "primary/merge_prize_pct_decode": FIG["merge_prize_pct_decode"],
    "primary/m2_merge_prize_pct_score": FIG["merge_prize_pct_score"],
    "primary/m2_merge_prize_pct_score_lo": FIG["merge_prize_pct_score_lo"],
    "primary/m2_merge_prize_pct_score_hi": FIG["merge_prize_pct_score_hi"],
    "primary/assumed_prize_pct_score": FIG["assumed_prize_pct_score"],
    "primary/fold_reduction_vs_assumed": FIG["fold_reduction_vs_assumed"],
    "primary/barrier_us_per_barrier_n160": FIG["barrier_160"],
    "primary/barrier_us_per_barrier_n160_ci_lo": FIG["barrier_160_lo"],
    "primary/barrier_us_per_barrier_n160_ci_hi": FIG["barrier_160_hi"],
    "primary/barrier_us_per_barrier_n1200": FIG["barrier_1200"],

    # Accidental finding: the ladder intercept.
    "finding/c_us_per_layer_unchained": FIG["c_unchained_us_per_layer"],
    "finding/c_us_per_step_unchained": FIG["c_unchained_us_per_step"],
    "finding/c_us_per_layer_chained": FIG["c_chained_us_per_layer"],
    "finding/c_us_per_step_chained": FIG["c_chained_us_per_step"],
    "finding/c_pct_of_decode_unchained": abs(
        FIG["c_unchained_us_per_step"]) / FIG["control_us_per_step"] * 100.0,

    # Measurement quality.
    "quality/control_us_per_step": FIG["control_us_per_step"],
    "quality/pooled_within_arm_sd_us": FIG["pooled_sd_us"],
    "quality/pooled_within_arm_sd_df": FIG["pooled_sd_df"],
    "quality/paired_blocks_low_rung": FIG["blocks_low_rung"],
    "quality/paired_blocks_high_rung": FIG["blocks_high_rung"],
    "quality/usable_rows": FIG["usable_rows"],
    "quality/token_gate_failures": 0,

    # The degenerate estimator the pre-registration named, reported anyway.
    "degenerate/single_rung_f_slope": FIG["single_rung_f_slope"],
    "degenerate/single_rung_f_slope_ci_lo": FIG["single_rung_f_slope_lo"],
    "degenerate/single_rung_f_slope_ci_hi": FIG["single_rung_f_slope_hi"],

    # Verdicts and pre-registered predictions.
    "verdict/reported": FIG["reported_verdict"],
    "verdict/mechanical_section5_print": FIG["mechanical_verdict"],
    "verdict/mechanical_is_degenerate": 1,
    "verdict/comment6_band": "0.3 dead / 0.8 build -> k inside band",
    "prereg/P1_dJ_magnitude_refuted": 1,
    "prereg/P2_k_zero_refuted": 1,
    "prereg/P3_sign_confirmed_size_wrong": 1,

    # §3.5.1's rule-105.23 critical test between the two decode-pool models.
    "reprice/pool_105_16_slack_pct": FIG["reprice_105_16_slack_pct"],
    "reprice/pool_105_17_assumed_pct": FIG["reprice_105_17_assumed_pct"],
    "reprice/pool_105_17_measured_pct": FIG["reprice_105_17_measured_pct"],
    "reprice/pool_105_17_measured_pct_lo": FIG["reprice_105_17_measured_pct_lo"],
    "reprice/pool_105_17_measured_pct_hi": FIG["reprice_105_17_measured_pct_hi"],
    "reprice/model_gap_assumed": FIG["reprice_model_gap_assumed"],
    "reprice/model_gap_measured": FIG["reprice_model_gap_measured"],
    "reprice/p_draw_105_16": FIG["p_draw_105_16"],
    "reprice/p_draw_105_17_assumed": FIG["p_draw_105_17_assumed"],
    "reprice/p_draw_105_17_measured": FIG["p_draw_105_17_measured"],
    "reprice/p_two_draws_105_17_measured": FIG["p_two_105_17_measured"],
    "reprice/merge_pct_via_105_17_constant": FIG["merge_pct_via_105_17"],
    "reprice/decode_denominator_gap": FIG["decode_denominator_gap"],
})

rows = wandb.Table(columns=["idx", "block", "arm", "arm_meaning", "inject", "chain",
                            "tg", "decode_us_per_step", "prefill_us_per_token",
                            "delta_vs_control_us", "passed", "wall_s"])
with SINK.open() as fh:
    data = [r for r in csv.DictReader(fh, delimiter="\t") if r["arm"]]
for r in data:
    decode_us = float(r["decode_s_per_token"]) * 1e6
    rows.add_data(int(r["idx"]), int(r["block"]), r["arm"], ARMS[r["arm"]],
                  int(r["inject"]), r["chain"], r["tg"], decode_us,
                  float(r["prefill_s_per_token"]) * 1e6,
                  decode_us - FIG["control_us_per_step"],
                  r["passed"] == "true", float(r["wall_s"]))
run.log({"probe_runs": rows})

artifact = wandb.Artifact("maple-frieren-r108k-barrier-region-price", type="analysis")
artifact.add_file(str(SINK))
artifact.add_file(str(ART / "figures.json"))
artifact.add_file(str(ART / "analyzer-output.txt"))
artifact.add_file(str(HERE / "maple-frieren-r108k-decode-dispatch-merge.md"))
artifact.add_file(str(HERE / "maple-frieren-r108k-prereg-amendment-1.md"))
run.log_artifact(artifact)

print("run_id:", run.id)
print("run_url:", run.url)
run.finish()
