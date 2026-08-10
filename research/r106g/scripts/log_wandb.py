#!/usr/bin/env python3
"""Log the R106-G redundant-read / fusion census to W&B."""
import json
import os

import wandb

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
ART = os.path.join(REPO, "research", "artifacts", "fern-r106g")

B_STEP = 1671402432
GATE_PCT_B = 1.2
DECODE_PCT_PER_US = 0.015228
SLC_BYTES = 25165824


def load(name):
    with open(os.path.join(ART, name)) as f:
        return json.load(f)


census = load("read_census.json")
roundtrip = load("roundtrip_census.json")
stage3 = load("stage3_triage.json")

s = census["summary"]
trav = s["traversal"]
bind = s["binding"]
b1b = roundtrip["stage1b_broadcast"]

combined_bytes = trav["redundant_bytes_upper_bound"] + roundtrip[
    "stage2_roundtrip_total_bytes_saved_if_all_fused"
]
combined_pct_B = 100.0 * combined_bytes / B_STEP
combined_us = combined_pct_B * s["us_per_pct_B"]

run = wandb.init(
    project="mlxfast-maple",
    entity="wandb-applied-ai-team",
    name="r106g-redundant-read-census",
    job_type="analysis",
    tags=["r106-g", "maple-fern", "pr619", "dag", "fusion", "N-ONCE"],
    config={
        "assignment_id": "maple-r106-g-redundant-read-fusion-census",
        "revision_id": "r106-g-rev1",
        "pr": 619,
        "base_sha": "9d424c167eae0a98e4c8c03e57be2f937ae0744a",
        "host": "Apple M4 Pro 48GiB (applegpu_g16s gen=16)",
        "instrument": "research/r106c/scripts/trace_dag.patch",
        "B_step_bytes": B_STEP,
        "gate_pct_B": GATE_PCT_B,
        "gate_bytes": s["gate_bytes"],
        "us_per_pct_B": s["us_per_pct_B"],
        "pct_cs_per_pct_B": s["pct_cs_per_pct_B"],
        "decode_pct_per_us": DECODE_PCT_PER_US,
        "slc_bytes": SLC_BYTES,
        "trace_correctness": "expected_token==actual_token==902, logit_delta=0",
        "dispatches_per_step": s["period_dispatches"],
        "command_buffers_per_step": s["command_buffers"],
        "barriers_per_step": s["observed_barriers"],
    },
)

run.summary.update(
    {
        # Stage 1 -- binding extent (over-count, never a byte claim)
        "binding_total_bytes_read": bind["total_bytes_read_with_multiplicity"],
        "binding_distinct_bytes": bind["distinct_bytes_touched"],
        "binding_ratio": bind["ratio"],
        "binding_ranges_read_more_than_once": bind["n_ranges_read_more_than_once"],
        # Stage 1 -- traversal (the real byte claim)
        "traversal_distinct_bytes": trav["distinct_bytes_traversed"],
        "traversal_redundant_bytes_upper_bound": trav["redundant_bytes_upper_bound"],
        "traversal_ratio_upper_bound": trav["ratio_upper_bound"],
        "traversal_ratio_upper_bound_above_slc": trav["ratio_upper_bound_dram_only"],
        "traversal_redundant_pct_of_B": trav["redundant_pct_of_B"],
        "traversal_redundant_us_per_step": trav["redundant_us_per_step"],
        "traversal_redundant_pct_of_cs": trav["redundant_pct_of_cs"],
        "traversal_clears_gate": trav["clears_gate"],
        "bytes_provably_read_once": 1661717366,
        "pct_B_provably_read_once": 99.4205,
        # Stage 1.3 -- SLC residency split
        "multi_read_buffers": s["buffers_multi_read"]["n"],
        "multi_read_buffers_above_slc": s["buffers_multi_read"]["n_above_slc"],
        "multi_read_bytes_above_slc": s["buffers_multi_read"]["bytes_above_slc"],
        # Stage 1b -- intra-dispatch broadcast re-reads
        "stage1b_issue_level_reads_bytes": b1b["issue_level_read_bytes"],
        "stage1b_issue_level_multiple_of_B": b1b["issue_level_read_bytes"] / B_STEP,
        "stage1b_distinct_broadcast_working_set": b1b["distinct_broadcast_operand_bytes"],
        "stage1b_broadcast_pct_of_B": b1b["distinct_pct_of_B"],
        "stage1b_largest_broadcast_operand_bytes": b1b["largest_broadcast_operand_bytes"],
        # Stage 2 -- intermediate round trips
        "stage2_intermediate_buffers": s["intermediates"]["n_buffers"],
        "stage2_intermediate_bytes": s["intermediates"]["bytes"],
        "stage2_intermediates_above_slc": s["intermediates"]["n_above_slc"],
        "stage2_write_read_pairs": roundtrip["stage2_n_pairs"],
        "stage2_family_pairs": len(roundtrip["stage2_table"]),
        "stage2_bytes_if_all_fused": roundtrip[
            "stage2_roundtrip_total_bytes_saved_if_all_fused"
        ],
        "stage2_pct_of_B": roundtrip["stage2_pct_of_B"],
        "stage2_us_per_step": roundtrip["stage2_us_per_step"],
        "stage2_pct_of_cs": roundtrip["stage2_pct_of_cs"],
        "stage2_shortfall_factor": stage3["shortfall_factor"],
        # Stage 3 -- legality / editability triage
        "stage3_n_editable_paths": stage3["n_editable_paths"],
        "stage3_candidates_outside_editable_paths": 0,
        "stage3_blocked_pairs": 3,
        "stage3_geometry_identical_pairs": 1,
        # Combined ceiling and verdict
        "combined_ceiling_bytes": combined_bytes,
        "combined_ceiling_pct_of_B": combined_pct_B,
        "combined_ceiling_us_per_step": combined_us,
        "combined_gate_shortfall_factor": (GATE_PCT_B / 100.0 * B_STEP)
        / combined_bytes,
        "primary_metric_read_multiplicity_ratio": trav["ratio_upper_bound"],
        "verdict": "N-ONCE (99.42 % of B provably read exactly once; "
        "combined fusion ceiling 2.19x below gate)",
        "fusion_implemented": False,
        "official_receipts_used": 0,
    }
)

art = wandb.Artifact("r106g-redundant-read-census", type="analysis")
for name in (
    "read_census.json",
    "roundtrip_census.json",
    "family_breakdown.json",
    "stage3_triage.json",
    "trace_report.json",
):
    art.add_file(os.path.join(ART, name))
art.add_file(
    os.path.join(REPO, "research", "maple-fern-r106g-redundant-read-census.md")
)
for name in (
    "read_census.py",
    "roundtrip_census.py",
    "family_breakdown.py",
    "stage3_triage.py",
):
    art.add_file(os.path.join(HERE, name))
run.log_artifact(art)

print(run.url)
run.finish()
