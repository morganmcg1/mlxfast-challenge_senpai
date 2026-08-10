#!/usr/bin/env python3
"""Publish the r107-B routed gate/up depth-1 preload adjudication to W&B."""

import subprocess
import wandb

REPO = "/Users/ec2-user/.senpai/native/mlxfast-maple-20260810-expansion/roles/student-maple-alphonse/workspace/target"
ART = f"{REPO}/research/artifacts/maple-alphonse-r107b"

# Faithful TG=2048 rung, two independent 32-round sessions (64 alternating
# control/candidate rounds total). gain% > 0 means REMOVING the shipped
# depth-1 preload is faster.
SESSIONS = {
    "s1": {
        "utc": "2026-08-10T10:23:29Z",
        "defeat_gain_pct": -0.038, "defeat_ci_lo": -0.104, "defeat_ci_hi": +0.028,
        "defeat_even_pct": -0.029, "defeat_odd_pct": -0.046, "defeat_n_faster": 13,
        "defeat_noop_pct": -0.010, "defeat_null_pct": +0.025,
        "resident_gain_pct": +1.224, "resident_ci_lo": +1.166, "resident_ci_hi": +1.282,
        "resident_noop_pct": +0.157, "resident_null_pct": +0.306,
        "defeat_ref_us": 39.03, "resident_ref_us": 36.65,
    },
    "s2": {
        "utc": "2026-08-10T10:32:59Z",
        "defeat_gain_pct": -0.037, "defeat_ci_lo": -0.163, "defeat_ci_hi": +0.089,
        "defeat_even_pct": -0.108, "defeat_odd_pct": +0.034, "defeat_n_faster": 17,
        "defeat_noop_pct": -0.048, "defeat_null_pct": +0.173,
        "resident_gain_pct": +1.207, "resident_ci_lo": +1.113, "resident_ci_hi": +1.302,
        "resident_noop_pct": +0.242, "resident_null_pct": +0.274,
        "defeat_ref_us": 39.03, "resident_ref_us": 36.65,
    },
}

DISPATCHES_PER_TOKEN = 39  # sparse MoE layers, one routed gate/up dispatch each

head = subprocess.run(["git", "-C", REPO, "rev-parse", "HEAD"],
                      capture_output=True, text=True, check=True).stdout.strip()

run = wandb.init(
    entity="wandb-applied-ai-team",
    project="mlxfast-maple",
    name="maple-alphonse-r107b-routed-gateup-depth1-preload-adjudication",
    job_type="kernel-local-adjudication",
    tags=["maple-alphonse", "r107-B", "routed-gate-up", "prefetch", "pr454",
          "kernel-local-probe", "gate-closed", "null-result"],
    notes=(
        "Adjudicates PR #454's depth-1 four-K-block preload in the routed gate/up "
        "decode kernel. The mechanism is ALREADY SHIPPED and default-ON "
        "(DARKBLOOM_ROUTED_GATEUP_R1 != '0'), so the one-axis contrast is the "
        "revert direction: delete the preload, change nothing else. "
        "Verdict: hard null in the production-representative cache-defeated regime. "
        "No submitted-surface change; zero-byte diff."
    ),
    config={
        "assignment_pr": 630,
        "adjudicated_pr": 454,
        "branch": "maple-alphonse/r107-routed-prefetch-adjudication",
        "base_sha": "ca39d2163255a4fdda39609447328b76acd7f0a9",
        "head_sha": head,
        "host": "Apple M4 Pro / 20 GPU cores / 48 GiB",
        "gpu_architecture": "applegpu_g16s",
        "host_dram_peak_gb_s": 266.3,
        "kernel": "laguna_routed_nvfp4_swiglu_qmv_packed_top8keys_r1_bf16_v2",
        "kernel_swift_symbol": "lagunaRoutedSwiGLUQMVPackedTop8R1Kernel",
        "shipped_default_gate": "DARKBLOOM_ROUTED_GATEUP_R1 != 0 (ON)",
        "probe": "research/fern_r99_qmv_probe.swift (reused, Rule 58)",
        "instrument": "research/maple-alphonse-r107b-prefetch-adjudication.{py,sh}",
        "one_axis": "depth-1 preload present (shipped) vs absent (revert)",
        "arms": ["depth1_shipped(ref)", "noop_control(byte-identical)",
                 "depth0_oneaxis(candidate)", "fault_control"],
        "faithful_rung_threadgroups": 2048,
        "threads_per_threadgroup": 64,
        "rows_per_threadgroup": 2,
        "input_width": 2048,
        "block_width": 512,
        "k_trips": 4,
        "rounds_per_session": 32,
        "reps_per_round": 500,
        "sessions": 2,
        "total_alternating_rounds": 64,
        "kill_threshold_gain_pct": 0.5,
        "dispatches_per_decode_token": DISPATCHES_PER_TOKEN,
        "charged_window_launches": 4993,
        "surface_digest_sources_vendor": "b196bafa2d7738636837efa895fe2cc293a0633321b5c2845e708426656cf544",
        "submitted_surface_bytes_changed": 0,
        "occupancy_maxTotalThreadsPerThreadgroup_all_arms": 1024,
        "threadgroup_memory_bytes_all_arms": 0,
        "reference_drift_vs_fern_r99": "NONE",
    },
)

mean_defeat = (SESSIONS["s1"]["defeat_gain_pct"] + SESSIONS["s2"]["defeat_gain_pct"]) / 2
mean_resident = (SESSIONS["s1"]["resident_gain_pct"] + SESSIONS["s2"]["resident_gain_pct"]) / 2
ref_us = SESSIONS["s1"]["defeat_ref_us"]

# Widest CI across the two sessions, converted to per-token microseconds.
defeat_ci_hi = max(s["defeat_ci_hi"] for s in SESSIONS.values())
us_per_token = mean_defeat / 100.0 * ref_us * DISPATCHES_PER_TOKEN
us_per_token_ci_hi = defeat_ci_hi / 100.0 * ref_us * DISPATCHES_PER_TOKEN

summary = {
    # PRIMARY: kernel-local gain of removing the preload, cache-defeated,
    # faithful TG=2048 rung, mean of two independent sessions.
    "primary/kernel_local_gain_pct_defeat_tg2048": mean_defeat,
    "primary/gate_open": 0,
    "primary/kill_threshold_gain_pct": 0.5,
    "derived/depth_axis_us_per_decode_token": us_per_token,
    "derived/depth_axis_us_per_decode_token_ci_hi": us_per_token_ci_hi,
    "derived/promotion_bar_us_per_step": 68.7,
    "derived/depth_axis_fraction_of_promotion_bar": us_per_token / 68.7,
    "derived/depth_axis_fraction_of_bar_ci_hi": us_per_token_ci_hi / 68.7,
    "resident/kernel_local_gain_pct_tg2048": mean_resident,
    "attribution/fern_r99_template_gain_pct_defeat_tg2048": 1.824,
    "attribution/depth_axis_share_of_fern_r99_pct": mean_defeat / 1.824 * 100.0,
    "controls/fault_control_bitwise_gate_tripped": 1,
    "controls/equivalence_gate_passed_candidate": 1,
}
for key, s in SESSIONS.items():
    for field, value in s.items():
        if field == "utc":
            continue
        summary[f"{key}/{field}"] = value
run.summary.update(summary)

# Two-session replication table for the faithful rung.
table = wandb.Table(columns=[
    "session", "utc", "regime", "gain_pct", "ci95_lo", "ci95_hi",
    "even_order_pct", "odd_order_pct", "rounds_faster_of_32",
    "noop_control_pct", "same_session_null_pct", "ref_us_per_dispatch",
])
for key, s in SESSIONS.items():
    table.add_data(key, s["utc"], "defeat(cache-cold)", s["defeat_gain_pct"],
                   s["defeat_ci_lo"], s["defeat_ci_hi"], s["defeat_even_pct"],
                   s["defeat_odd_pct"], s["defeat_n_faster"], s["defeat_noop_pct"],
                   s["defeat_null_pct"], s["defeat_ref_us"])
    table.add_data(key, s["utc"], "resident(cache-warm)", s["resident_gain_pct"],
                   s["resident_ci_lo"], s["resident_ci_hi"], None, None, 32,
                   s["resident_noop_pct"], s["resident_null_pct"], s["resident_ref_us"])
run.log({"faithful_rung_tg2048": table})

artifact = wandb.Artifact("maple-alphonse-r107b-adjudication", type="kernel-probe")
artifact.add_dir(ART)
run.log_artifact(artifact)

print(f"wandb run: {run.url}")
print(f"wandb run id: {run.id}")
run.finish()
