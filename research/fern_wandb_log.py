#!/usr/bin/env python3
"""Publish the vendor byte-recovery experiment record to W&B.

Byte recovery is the result for this assignment, so the logged metrics are
sizes and gate verdicts rather than timings. No GPU work happens here.
"""
import wandb

PROJECT = "mlxfast-maple"
ENTITY = "wandb-applied-ai-team"
BASE_SHA = "63ab67c888e1892086b7b5b623de4dd0ebe68c90"

PART_A = [
    # name, base bytes, head bytes, residue bytes
    ("BatchKVCache", 43383, 37146, 29813),
    ("CompilableRotatingKVCache", 11445, 8418, 4770),
    ("CompiledDecode", 16147, 11686, 9276),
    ("CompilableKVCache", 12043, 9170, 6667),
    ("BaseConfiguration", 8535, 6859, 4786),
]

config = {
    "assignment_id": "maple-2026-08-07r-vendor-byte-recovery",
    "revision_id": "r1",
    "pr_number": 311,
    "branch": "maple-fern/vendor-byte-recovery",
    "base_sha": BASE_SHA,
    "experiment_kind": "structural_byte_recovery",
    "host": "M4 Pro, Apple GPU generation 16, 48 GiB (memory profile: low)",
    "timing_measured": False,
    "expected_timing_effect": "exactly zero (comments do not reach compiler output)",
    "part_a_files_submitted": 5,
    "part_b_file": "Sources/MLXFastModel/LagunaRuntimeModel.swift",
    "part_b_applied": False,
    "scored_file_sha256_before_and_after":
        "56d16941d61c5f1217faad6ef86dcc766b1632ac7078015702bc7f42a9434fcf",
}

run = wandb.init(
    entity=ENTITY,
    project=PROJECT,
    name="maple-fern-vendor-byte-recovery",
    job_type="byte-recovery",
    config=config,
    tags=["maple-fern", "pr-311", "byte-recovery", "no-timing"],
)

table = wandb.Table(
    columns=["file", "base_bytes", "head_bytes", "delta_bytes", "residue_bytes", "residue_identical"]
)
for name, base, head, residue in PART_A:
    table.add_data(name, base, head, head - base, residue, True)
    run.summary[f"part_a/{name}/base_bytes"] = base
    run.summary[f"part_a/{name}/head_bytes"] = head
    run.summary[f"part_a/{name}/delta_bytes"] = head - base

run.log({"part_a/per_file": table})

run.summary.update({
    # ---- Part A: applied ----
    "part_a/base_bytes_total": 304766,
    "part_a/head_bytes_total": 286492,
    "part_a/recovered_bytes": 18274,
    "part_a/target_bytes": 27965,
    "part_a/recovery_fraction_of_target": 18274 / 27965,
    "part_a/notes_files_created": 5,
    "part_a/darkbloom_sites_preserved_in_source": 6,
    "part_a/darkbloom_lines_leaked_into_notes": 0,

    # ---- editable budget ----
    "budget/current_bytes": 2849777,
    "budget/cap_bytes": 3000000,
    "budget/headroom_bytes": 150223,
    "budget/growth_bytes": -18274,
    "budget/growth_cap_bytes": 262144,
    "budget/editable_file_count": 140,
    "budget/editable_file_count_base": 140,

    # ---- Part B: planned only, never applied ----
    "part_b/file_bytes": 468336,
    "part_b/comment_pool_bytes": 120254,
    "part_b/comment_pool_fraction": 0.257,
    "part_b/comment_blocks_total": 254,
    "part_b/literal_interior_lines": 5,
    "part_b/literal_interior_bytes": 372,
    "part_b/hard_keep_bytes": 58837,
    "part_b/planned_blocks": 94,
    "part_b/moved_bytes": 28643,
    "part_b/pointer_bytes_added": 980,
    "part_b/net_recovery_bytes": 27663,
    "part_b/projected_size_bytes": 440673,
    "part_b/per_file_cap_bytes": 524288,
    "part_b/projected_cap_utilisation": 440673 / 524288,
    "part_b/headroom_before_bytes": 55952,
    "part_b/headroom_after_bytes": 83615,
    "part_b/headroom_gain_fraction": (83615 - 55952) / 55952,

    # wave 1 = unfenced blocks only (safe to land while #301/#308/#309 are open)
    "part_b/wave1/blocks": 86,
    "part_b/wave1/moved_bytes": 27196,
    "part_b/wave1/net_recovery_bytes": 26216,
    "part_b/wave1/projected_size_bytes": 442120,
    "part_b/wave1/headroom_after_bytes": 82168,
    "part_b/wave1/share_of_total_recovery": 26216 / 27663,

    # wave 2 = blocks fenced behind an in-flight PR's line ranges
    "part_b/wave2/blocks": 8,
    "part_b/wave2/bytes": 1447,
    "part_b/wave2/pr301_blocks": 2,
    "part_b/wave2/pr301_bytes": 233,
    "part_b/wave2/pr308_blocks": 1,
    "part_b/wave2/pr308_bytes": 277,
    "part_b/wave2/pr309_blocks": 5,
    "part_b/wave2/pr309_bytes": 937,

    # ---- gate verdicts ----
    "gate/comment_strip_check": "PASS",
    "gate/comment_strip_files_identical": 9,
    "gate/comment_strip_files_checked": 9,
    "gate/assignment_scope": "PASS",
    "gate/editable_budget": "PASS",
    "gate/docc_detach_mixed_style_runs": 0,
    "gate/part_b_dry_run": "PASS",
    "gate/worker_build_exit": 0,
    "gate/drift_tripwire_64_step": "PASS",
    "gate/drift_tripwire_checked_steps": 64,

    # equivalence oracle: identical verdict on candidate AND unchanged base
    "gate/upstream_equivalence_exit": 1,
    "gate/upstream_equivalence_exit_on_unchanged_base": 1,
    "gate/upstream_equivalence_prefill_max_abs_err": 0.125,
    "gate/upstream_equivalence_prefill_max_abs_err_base": 0.125,
    "gate/upstream_equivalence_prefill_mean_abs_err": 0.011933609,
    "gate/upstream_equivalence_prefill_mean_abs_err_base": 0.011933609,
    "gate/upstream_equivalence_exact_decode_steps": 8,
    "gate/upstream_equivalence_token_mismatches": 0,
    "gate/upstream_equivalence_attribution":
        "pre-existing non-M5 host divergence; candidate and unchanged base "
        "reports are identical to every printed digit",
})

run.finish()
print("wandb run:", run.url)
