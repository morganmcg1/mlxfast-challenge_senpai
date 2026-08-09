"""Publish the r97-c terminal evidence to W&B.

Values are transcribed from the two committed standalone Metal probes:
  research/nezuko_r97_simdsum_order_probe.swift   (Gate 0)
  research/nezuko_r97_split_ceiling_ladder.swift  (ceiling ladders)
"""

import wandb

SLIDING = [  # N, t, median us/call, recovery, ci_lo, ci_hi, predicted
    (32, 1, 10.092, 0.0000, 0.0000, 0.0000, 0.0000),
    (64, 2, 9.998, 0.0094, -0.0259, 0.0177, 0.0000),
    (128, 4, 8.790, 0.1290, 0.1023, 0.1372, 0.1250),
    (256, 8, 8.241, 0.1834, 0.1555, 0.1910, 0.1875),
    (512, 16, 8.239, 0.1836, 0.1866, 0.1935, 0.1875),
]
FULL = [
    (24, 1, 10.059, 0.0000, 0.0000, 0.0000, 0.0000),
    (48, 2, 7.699, 0.2346, 0.2307, 0.2363, 0.2500),
    (96, 4, 6.498, 0.3540, 0.3519, 0.3565, 0.3750),
    (192, 8, 6.493, 0.3545, 0.3527, 0.3564, 0.3750),
    (384, 16, 6.434, 0.3604, 0.3593, 0.3634, 0.3750),
]
# Independent rerun of the same binary; the tables above are the less
# favourable of the two and are what every verdict below is computed from.
CONFIRM = {
    "sliding_anchor_us": 10.160, "sliding_n64_recovery": 0.0181,
    "sliding_best_recovery": 0.1899,
    "full_anchor_us": 10.077, "full_best_recovery": 0.3623,
}
GATE0 = {  # variant -> (bitexact_fraction, max_ulp)
    "xor_ascending": (1.0, 0),
    "xor_descending": (0.38044, 98304),
    "shuffle_down_tree": (0.38044, 98304),
    "prefix_sequential": (0.27108, 66638),
    "two_level": (1.0, 0),
}

M5_DISPATCH, M4_DISPATCH = 2.3403, 1.2382
M5_SLIDING, M5_FULL, M4_SLIDING = 290.0, 100.0, 636.0
WAVE_DEP = 0.847
M5_DECODE_US = M5_SLIDING / 0.0746  # sliding holds its M4 decode share

run = wandb.init(
    project="mlxfast-maple",
    entity="wandb-applied-ai-team",
    name="r97-c-attn-two-stage-split-ceiling",
    job_type="kernel-probe",
    tags=["r97-c", "maple-nezuko", "attention", "ceiling-ladder", "no-go"],
    config={
        "assignment_id": "maple-r97-c-attn-two-stage-split",
        "revision_id": "r97-c-rev1",
        "pr": 528,
        "base_sha": "b78e7cdb80b5ae5f1cb1fdd39803322fb283ae5e",
        "host": "Apple M4 Pro / applegpu_g16s / 20 GPU cores / 48 GiB",
        "ranked_host": "Apple M5 Max / 40 GPU cores / gen 17",
        "ladder_blocks": 40,
        "iters_per_measure": 200,
        "bootstrap_resamples": 4000,
        "gate0_vectors": 200_000,
        "m5_us_per_dispatch": M5_DISPATCH,
        "m4_us_per_dispatch": M4_DISPATCH,
        "wave_dependent_share": WAVE_DEP,
        "bar_sliding_us_per_step": 120.0,
        "bar_full_us_per_step": 40.0,
        "runtime_implemented": False,
        "editable_path_growth_bytes": 0,
    },
)

# --- Gate 0 -----------------------------------------------------------------
gate0_pass = GATE0["xor_ascending"][0] == 1.0
run.summary["gate0_bitexact"] = gate0_pass
for name, (frac, ulp) in GATE0.items():
    run.summary[f"gate0_{name}_bitexact_frac"] = frac
    run.summary[f"gate0_{name}_max_ulp"] = ulp
run.summary["gate0_simd_sum_reduction_order"] = "ascending_xor_butterfly"

# --- ladders ----------------------------------------------------------------
tbl = wandb.Table(columns=["state", "N", "t", "sg_per_tg", "us_per_call",
                           "us_per_step", "recovery", "ci_lo", "ci_hi",
                           "predicted", "residual"])
for state, rows, calls, pairs in (("sliding", SLIDING, 30, 32),
                                  ("full", FULL, 10, 24)):
    for n, t, us, rec, lo, hi, pred in rows:
        tbl.add_data(state, n, t, 32 // t, us, us * calls,
                     rec, lo, hi, pred, rec - pred)
        run.log({f"{state}/N": n, f"{state}/us_per_call": us,
                 f"{state}/recovery": rec, f"{state}/predicted": pred})
run.log({"ceiling_ladder": tbl})

# The scored per-step attention cost of each *state*. No runtime split was
# built, so these are the shipped geometry measured by the ceiling probe.
run.summary["attn_us_per_step_sliding"] = SLIDING[0][2] * 30
run.summary["attn_us_per_step_full"] = FULL[0][2] * 10
run.summary["attn_us_per_step_sliding_runtime_measured"] = False
run.summary["attn_us_per_step_full_runtime_measured"] = False
run.summary["attn_us_per_step_source"] = "ceiling_probe_shipped_geometry"

for state, rows, calls in (("sliding", SLIDING, 30), ("full", FULL, 10)):
    best = max(rows, key=lambda r: r[3])
    run.summary[f"{state}_best_rung_N"] = best[0]
    run.summary[f"{state}_best_recovery_frac"] = best[3]
    run.summary[f"{state}_best_recovery_ci_hi"] = best[5]
    run.summary[f"attn_us_per_step_{state}_best_rung"] = best[2] * calls
    run.summary[f"{state}_max_shape_residual"] = max(
        abs(r[3] - r[6]) for r in rows)

# --- M5 projection and verdicts --------------------------------------------
gS = SLIDING[-1][3] * M5_SLIDING * WAVE_DEP
gF = FULL[-1][3] * M5_FULL * WAVE_DEP
cS, cF = 30 * M5_DISPATCH, 10 * M5_DISPATCH
net = gS + gF - cS - cF
run.summary.update({
    "m5_sliding_ceiling_gain_us": gS,
    "m5_sliding_dispatch_cost_us": cS,
    "m5_full_ceiling_gain_us": gF,
    "m5_full_dispatch_cost_us": cF,
    "m5_net_us_per_step": net,
    "m5_net_score_pct": net / M5_DECODE_US * 100 * 0.75,
    "m5_best_case_net_us_per_step": 58.0 + 40.0 - cS - cF,
    "score_sigma_pct": 0.6172,
    "partial_spill_mb_per_step": 39.9,
    "m4_over_m5_split_favourability": (
        (SLIDING[-1][3] * M4_SLIDING * WAVE_DEP) / (30 * M4_DISPATCH)) / (gS / cS),
    "verdict_gate0": "PASS",
    "verdict_sliding_split": "NO-GO",
    "verdict_full_split": "NO-GO",
    "verdict": "inconclusive_mechanism_falsified_below_bar",
})
run.summary.update({f"confirm_{k}": v for k, v in CONFIRM.items()})
run.summary["m5_net_us_per_step_confirm_run"] = (
    CONFIRM["sliding_best_recovery"] * M5_SLIDING * WAVE_DEP
    + CONFIRM["full_best_recovery"] * M5_FULL * WAVE_DEP - cS - cF)

print(f"run: {run.url}  id={run.id}")
run.finish()
