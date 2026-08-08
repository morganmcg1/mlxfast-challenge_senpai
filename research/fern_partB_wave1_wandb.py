#!/usr/bin/env python3
"""Publish the Part B wave-1 byte-recovery record to W&B.

The result of this assignment is a byte measurement and a stop decision, so the
logged values are sizes, policy attribution, and gate verdicts. Nothing was
applied to the scored file and no GPU or timing work happens here.
"""
import wandb

PROJECT = "mlxfast-maple"
ENTITY = "wandb-applied-ai-team"
BASE_SHA = "5c491cf0634699e9969c8909cb4403c3f465cfe3"

# name, blocks, moved bytes -- each row adds one correction to the row above it
ATTRIBUTION = [
    ("A base (leaky) policy", 94, 28643),
    ("B + rule-idiom recognition", 81, 18167),
    ("C + DARKBLOOM_-only decl lookahead", 69, 15130),
    ("D + full HARD_KEEP decl lookahead", 69, 15130),
    ("E + ABSTRACT_HARD_LINES=8 (reverted)", 22, 5299),
    ("G C + ABSTRACT_HARD_LINES=4", 50, 11078),
    ("final C + bit-exact/pin-those idioms", 62, 12910),
]

config = {
    "assignment_id": "maple-2026-08-07s-lagunaruntimemodel-byte-recovery",
    "revision_id": "r1",
    "pr_number": 320,
    "branch": "maple-fern/lagunaruntimemodel-byte-recovery",
    "base_sha": BASE_SHA,
    "experiment_kind": "structural_byte_recovery",
    "host": "M4 Pro, Apple GPU generation 16, 48 GiB (memory profile: low)",
    "timing_measured": False,
    "applied_to_scored_file": False,
    "success_bar_net_bytes": 18000,
    "stop_threshold_net_bytes": 10000,
    "scored_file": "Sources/MLXFastModel/LagunaRuntimeModel.swift",
    "scored_file_unchanged_from_base": True,
}

run = wandb.init(
    entity=ENTITY,
    project=PROJECT,
    name="maple-fern-partB-wave1-byte-recovery",
    job_type="byte-recovery",
    config=config,
    tags=["maple-fern", "pr-320", "byte-recovery", "no-timing", "stopped"],
)

table = wandb.Table(columns=["configuration", "blocks", "moved_bytes"])
for name, blocks, moved in ATTRIBUTION:
    table.add_data(name, blocks, moved)
run.log({"attribution/policy_cost": table})

run.summary.update({
    # ---- the decision ----
    "verdict": "stopped below threshold; nothing applied",
    "net_bytes_recovered": 0,
    "net_bytes_available_ceiling": 9362,

    # ---- file and pool ----
    "file/base_bytes": 468336,
    "file/per_file_cap_bytes": 524288,
    "file/headroom_at_base_bytes": 55952,
    "file/cap_utilisation_at_base": 468336 / 524288,
    "pool/comment_blocks_total": 254,
    "pool/comment_pool_bytes": 120254,
    "pool/comment_pool_all_in_bytes": 120626,
    "pool/comment_pool_fraction_of_file": 120254 / 468336,
    "pool/literal_interior_lines": 5,
    "pool/literal_interior_bytes": 372,
    "pool/hard_keep_bytes": 82899,
    "pool/hard_keep_fraction": 82899 / 120254,
    "pool/rule_idiom_only_hard_keep_blocks": 12,
    "pool/rule_idiom_only_hard_keep_bytes": 12085,
    "pool/exactness_token_hard_keep_bytes": 7489,

    # ---- full plan (waves 1+2) ----
    "plan/blocks": 62,
    "plan/moved_bytes": 12910,
    "plan/pointer_bytes_added": 2659,
    "plan/net_bytes": 10251,
    "plan/pointer_overhead_fraction": 2659 / 12910,
    "plan/projected_size_bytes": 458085,
    "plan/projected_headroom_bytes": 66203,

    # ---- wave 1: what would have been applied ----
    "wave1/blocks": 54,
    "wave1/moved_bytes": 11765,
    "wave1/pointer_bytes_added": 2403,
    "wave1/net_bytes": 9362,
    "wave1/projected_size_bytes": 458974,
    "wave1/projected_headroom_bytes": 65314,
    "wave1/shortfall_vs_success_bar_bytes": 18000 - 9362,

    # ---- wave 2: deferred behind in-flight fences ----
    "wave2/blocks": 8,
    "wave2/bytes": 1145,
    "wave2/pr301_blocks": 3,
    "wave2/pr301_bytes": 308,
    "wave2/pr308_blocks": 3,
    "wave2/pr308_bytes": 414,
    "wave2/pr309_blocks": 3,
    "wave2/pr309_bytes": 498,
    "wave2/gutter_only_blocks": 3,
    "wave2/gutter_only_bytes": 258,

    # ---- mid-sentence abstract truncation (finding, not paid for) ----
    "midsentence/planned_blocks": 62,
    "midsentence/cuts_at_abstract_hard_lines_3": 50,
    "midsentence/cost_slack_1_bytes": 3560,
    "midsentence/cost_slack_5_bytes": 8531,
    "midsentence/cost_slack_1_fraction_of_wave1": 3560 / 9362,
    "midsentence/cost_slack_5_fraction_of_wave1": 8531 / 9362,

    # ---- editable budget ----
    "budget/current_bytes": 2849777,
    "budget/cap_bytes": 3000000,
    "budget/headroom_bytes": 150223,
    "budget/growth_bytes": 0,
    "budget/growth_cap_bytes": 262144,
    "budget/editable_file_count": 140,

    # ---- gate verdicts ----
    "gate/assignment_scope": "PASS",
    "gate/editable_budget": "PASS",
    "gate/dry_run_full_spec": "PASS",
    "gate/dry_run_wave1_spec": "PASS",
    "gate/dry_run_inject_rule_exit": 1,
    "gate/dry_run_inject_bytes_exit": 1,
    "gate/dry_run_inject_size_exit": 1,
    "gate/pin_audit": "PASS",
    "gate/pin_audit_pins_released": 0,
    "gate/docc_detach_mixed_style_runs": 0,
    "gate/comment_strip_check": "FAIL",
    "gate/comment_strip_fail_reason":
        "precondition structurally unsatisfiable: 212 triple-quote literals "
        "embed Metal source, 5 lines of which begin with //; residue IDENTICAL",
    "gate/setup_sh_exit": 0,
    "gate/local_iterate": "SKIPPED (vacuous: no source change)",
    "gate/drift_tripwire_64_step": "SKIPPED (vacuous: no source change)",
    "gate/upstream_equivalence": "SKIPPED (vacuous: no source change)",
})

run.finish()
print("wandb run:", run.url)
