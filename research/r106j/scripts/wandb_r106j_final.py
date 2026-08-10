#!/usr/bin/env python3
"""R106-J terminal W&B run: integration-tree result for PR #625.

Logs the primary metric (paired d(ln score) for candidate B / L3), the
integrated-tree delta (0 % of cs by construction), the Rule 105 re-pricing
table, and the gate/precondition evidence.
"""
import json
import os
import pathlib
import subprocess
import sys

import wandb

REPO = pathlib.Path(__file__).resolve().parents[3]
ART = REPO / "research" / "artifacts" / "maple-fern-r106j"


def sh(*args):
    return subprocess.run(
        args, cwd=REPO, capture_output=True, text=True
    ).stdout.strip()


head = sh("git", "rev-parse", "HEAD")
origin_main = sh("git", "rev-parse", "origin/main")
advisor_tip = "a30fa5f8c1f8a0d8996e951281cefe4c9d53f425"
surface_diff = sh(
    "git", "diff", "--numstat", advisor_tip, "HEAD",
    "--", "Sources/", "Vendor/", "benchmark.json", "Package.swift", "senpai/",
)

run = wandb.init(
    entity="wandb-applied-ai-team",
    project="mlxfast-maple",
    name="maple-fern-r106j-integration-tree-final",
    job_type="integration",
    tags=["r106j", "maple-fern", "pr625", "integration-tree",
          "N-INTEGRATED", "N-PACK", "retraction", "rule105"],
    notes=(
        "R106-J integration tree. No Stage-2 candidate cleared the 0.4 % of cs "
        "bar; integrated tree is byte-identical to advisor tip a30fa5f8 on the "
        "scored surface. Includes the max_abs_diff / golden_hash instrument "
        "retraction and the Rule 105 re-pricing of L3 and pf0."
    ),
    config={
        "assignment_id": "maple-r106-i-prefill-traversal-byte-census",
        "revision_id": "r106-i-rev2",
        "pr_number": 625,
        "branch": "maple-fern/r106-prefill-traversal-census",
        "head_sha": head,
        "build_verified_sha": "2127e436049b5f3586e1c38f9904e4705fbf405e",
        "advisor_base_sha": advisor_tip,
        "origin_main_sha": origin_main,
        "host": "Apple M4 Pro, 20 GPU cores, 48 GiB, applegpu_g16s (gen 16)",
        "promotion_bar_pct_cs": 0.4,
        "decode_price_pct_cs_per_us_step": 0.015228,
        "rule105_alpha": 0.4369,
        "rule105_beta": 0.5,
        "official_receipts_spent": 0,
    },
)

# ---- primary: candidate B (L3 packing default flip) paired ABBA, 10 blocks ----
wandb.log({
    "primary/d_ln_score_pct": 0.0328,
    "primary/d_ln_score_ci_lo_pct": -0.2338,
    "primary/d_ln_score_ci_hi_pct": 0.2994,
    "primary/d_ln_score_sd_pct": 0.3727,
    "primary/d_ln_decode_pct": -0.0686,
    "primary/d_ln_decode_ci_lo_pct": -0.3921,
    "primary/d_ln_decode_ci_hi_pct": 0.2550,
    "primary/d_ln_prefill_pct": 0.0745,
    "primary/d_ln_prefill_ci_lo_pct": -0.3955,
    "primary/d_ln_prefill_ci_hi_pct": 0.5446,
    "primary/blocks": 10,
    "primary/complete_runs": 42,
    "primary/blocks_positive": 6,
    "primary/bar_cleared": 0,
})

# monotone shrinkage of the estimate as blocks accumulated
for nblocks, est in [(4, 0.1889), (8, 0.0920), (10, 0.0328)]:
    wandb.log({"shrinkage/blocks": nblocks,
               "shrinkage/d_ln_score_pct": est})

# ---- integrated tree ----
wandb.log({
    "integrated/pct_cs_delta": 0.0,
    "integrated/surface_diff_lines": len(surface_diff.splitlines()),
    "integrated/surface_bytes": 2681206,
    "integrated/surface_budget": 3000000,
    "integrated/surface_headroom": 318794,
    "integrated/surface_files": 142,
    "integrated/growth_vs_advisor_tip": 0,
    "integrated/growth_vs_origin_main": -302643,
    "integrated/candidates_landed": 0,
    "integrated/candidates_considered": 7,
})

# ---- Rule 105 re-pricing ----
wandb.log({
    "rule105/L3_as_published_pct": 0.562,
    "rule105/L3_after_units_alpha_pct": 0.2455,
    "rule105/L3_after_debias_alpha_pct": 0.1966,
    "rule105/L3_after_debias_alpha_lo_pct": 0.1751,
    "rule105/L3_after_debias_beta_pct": 0.2251,
    "rule105/L3_total_overcredit_factor": 2.86,
    "rule105/L3_measured_here_pct": 0.0328,
    "rule105/pf0_as_published_pct": 0.53,
    "rule105/pf0_repriced_alpha_pct": 0.2301,
    "rule105/pf0_repriced_beta_pct": 0.2633,
    "rule105/stack_L3_pf0_on_paper_pct": 0.4267,
    "rule105/stack_L3_pf0_on_measured_pct": 0.2629,
})

# ---- gates ----
wandb.log({
    "gates/build_rc": 0,
    "gates/build_wall_s": 260,
    "gates/passed": 1,
    "gates/passed_correctness": 1,
    "gates/checked_steps": 130,
    "gates/case_count": 1,
    "gates/runs_audited": 43,
    "gates/runs_all_green": 1,
    "gates/submit_preconditions_pass": 12,
    "gates/submit_preconditions_fail": 0,
    "gates/darkbloom_expert_down_bn_set": 0,
    "gates/darkbloom_qmv_wide_codes_set": 0,
})

run.summary.update({
    "verdict": "N-INTEGRATED",
    "sub_verdicts": "N-T1, N-PACK, N-UNROLL-PREEMPTED",
    "bar_cleared": False,
    "recommendation": "Hold our tree; take no draw (consistent with Rule 101.2)",
    "integrated_tree_equals_advisor_tip": surface_diff == "",
    "retractions": "max_abs_diff (hard-coded 0 at 5 sites); "
                   "golden_hash (sha256 of golden fixture input file)",
    "head_sha": head,
})

print(json.dumps({
    "run_id": run.id,
    "run_path": f"{run.entity}/{run.project}/{run.id}",
    "url": run.url,
    "head": head,
    "surface_diff_empty": surface_diff == "",
}, indent=2))

run.finish()

out = ART / "wandb_final_run.json"
out.write_text(json.dumps({
    "run_id": run.id,
    "url": run.url,
    "entity": run.entity,
    "project": run.project,
    "head": head,
}, indent=2) + "\n")
print(f"wrote {out}", file=sys.stderr)
