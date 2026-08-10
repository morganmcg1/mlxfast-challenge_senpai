#!/usr/bin/env python3
"""Publish the R108-P dispatch removal/addition symmetry ledger to W&B.

The headline is a paired in-session ratio on one M4 Pro host: the price of
*removing* a decode dispatch (de-fusion ladder) divided by the price of
*adding* one (empty-kernel injection ladder). Both ladders share the same
zero rung, the same session, the same ABBA ordering and the same cool gate.
"""

import json
import statistics as st
import subprocess
import glob

import wandb

REPO = ("/Users/ec2-user/.senpai/native/mlxfast-maple-20260810-expansion/"
        "roles/student-maple-alphonse/workspace/target")
ART = f"{REPO}/research/artifacts/maple-alphonse-r108p"

RULE57 = 1.2382           # M4 "saturated" per-dispatch glue, rule 57
RULE57_CI = (1.2237, 1.2518)
RULE65 = 2.3403           # M5 addition price, rule 65
RULE65_CI = (2.2766, 2.4040)
K_DISPATCH = 1.890        # published third-regime multiplier
K_RESIDUE = 1.4998        # tanjiro's independent read
M4_SAT_ADD = 2.17         # R93 past-knee segment price, same host
M4_SAT_ADD_RANGE = (1.98, 2.36)
R93_CHORD_0_2400 = 1.300  # R93 0->2400 chord, means column
KNEE_K = 480
PCT_PER_M4_DISPATCH_US = 0.015228 * K_DISPATCH  # rule-65 pricing identity

head = subprocess.run(["git", "-C", REPO, "rev-parse", "HEAD"],
                      capture_output=True, text=True, check=True).stdout.strip()

fit = json.load(open(f"{ART}/fit.json"))
census = json.load(open(f"{ART}/dn-census.json"))
rows = [json.load(open(p))
        for p in sorted(glob.glob(f"{ART}/ladder/*.row.json"))]

d = fit["derived"]
rf = fit["removal_fit"]
ef = fit.get("e_free_fit") or {}
es = fit.get("e_sat_fit") or {}

by_arm = {}
for r in rows:
    by_arm.setdefault(r["arm"], []).append(r["decode"] * 1e6)
arm_mean = {a: st.mean(v) for a, v in by_arm.items()}
arm_sd = {a: (st.stdev(v) if len(v) > 1 else None) for a, v in by_arm.items()}
prefill = [r["prefill"] * 1e3 for r in rows]

removal = d["removal_price_us_per_dispatch_slope"]
removal_ci = d["removal_price_ci_slope"]
ratio_matched = d["ratio_removal_over_M4_saturated_addition"]
ratio_matched_range = d["ratio_removal_over_M4_saturated_addition_range"]
k_removal = RULE65 / removal
k_removal_range = [RULE65 / removal_ci[1], RULE65 / removal_ci[0]]
k_matched = d["k_dispatch_regime_matched"]

run = wandb.init(
    entity="wandb-applied-ai-team",
    project="mlxfast-maple",
    name="maple-alphonse-r108p-dispatch-removal-symmetry",
    job_type="paired-ladder-timing",
    tags=["maple-alphonse", "r108-P", "dispatch", "removal-price",
          "addition-price", "k_dispatch", "rule-57", "rule-65", "rule-68",
          "regime-matched", "M4-Pro", "diagnostic-not-candidate"],
    notes=(
        "Does removing a decode dispatch pay what adding one costs? "
        "Two ladders on one M4 Pro host share a zero rung: a de-fusion ladder "
        "(removal, dn = 0/40/117/158) and an empty-kernel injection ladder "
        "(addition, K = 0/276/1600). Naively the ratio is ~13x, but that is a "
        "regime artifact: the addition rung sits inside a free region that "
        "extends to K ~ 480 on this host. Regime-matched against R93's "
        "past-knee segment prices on the same host the ratio is ~1, i.e. "
        "symmetric within noise. Rule 57's 1.2382 us reproduces R93's "
        "0->2400 chord, so k_dispatch = 1.890 divides an M5 marginal price by "
        "an M4 chord and over-projects M5 fusion wins."
    ),
    config={
        "assignment_pr": 644,
        "assignment_id": "maple-r107-e-decode-oproj-amortisation",
        "revision_id": "r108-p-rev1",
        "branch": "maple-alphonse/r107-decode-oproj-amortisation",
        "base_sha": "705484b9e120d60a973d660fdbdd1ccc7cdfa124",
        "head_sha": head,
        "host": "M4 Pro, Apple GPU generation 16, 48 GiB (low-memory profile)",
        "is_ranked_host": False,
        "submitted_surface_changed": False,
        "timed_steps": 128,
        "seed_tokens": 512,
        "n_runs": len(rows),
        "knee_K_assumed": KNEE_K,
        "inject_empty_tg_default": 160,
        "r93_inject_empty_tg": 8,
        "forced_commits_per_step": 7,
        "dn_census": census.get("dn", {}),
        "dn_uncertainty": census["dn_uncertainty"],
    },
)

summary = {
    # PRIMARY: the removal price and the two ratios that answer the charge.
    "primary/removal_price_us_per_dispatch": removal,
    "primary/removal_price_ci_lo": removal_ci[0],
    "primary/removal_price_ci_hi": removal_ci[1],
    "primary/removal_fit_n": rf["n"],
    "primary/removal_fit_resid_sd_us_per_step": rf["resid_sd"],
    "primary/addition_price_at_operating_point": d["addition_price_operating_point"],
    "primary/ratio_naive_removal_over_addition": d[
        "ratio_removal_over_addition_operating_point"],
    "primary/ratio_regime_matched": ratio_matched,
    "primary/ratio_regime_matched_lo": ratio_matched_range[0],
    "primary/ratio_regime_matched_hi": ratio_matched_range[1],
    "primary/symmetric_within_noise": int(
        ratio_matched_range[0] <= 1.0 <= ratio_matched_range[1]),

    # The third-regime multiplier, four reads.
    "k/published_k_dispatch": K_DISPATCH,
    "k/k_removal_rule65_over_removal_slope": k_removal,
    "k/k_removal_lo": k_removal_range[0],
    "k/k_removal_hi": k_removal_range[1],
    "k/k_dispatch_regime_matched": k_matched,
    "k/k_dispatch_regime_matched_lo": d["k_dispatch_regime_matched_range"][0],
    "k/k_dispatch_regime_matched_hi": d["k_dispatch_regime_matched_range"][1],
    "k/k_residue_tanjiro": K_RESIDUE,
    "k/published_over_regime_matched": K_DISPATCH / k_matched,
    "k/overprojection_pct_at_1p890": 100.0 * (K_DISPATCH / k_matched - 1.0),

    # Rule 57 is a chord, not a saturated price.
    "rule57/published_us_per_dispatch": RULE57,
    "rule57/r93_chord_0_2400_us_per_dispatch": R93_CHORD_0_2400,
    "rule57/chord_matches_rule57": int(
        abs(R93_CHORD_0_2400 - RULE57) / RULE57 < 0.06),
    "rule57/r93_past_knee_segment_price": M4_SAT_ADD,
    "rule57/r93_past_knee_lo": M4_SAT_ADD_RANGE[0],
    "rule57/r93_past_knee_hi": M4_SAT_ADD_RANGE[1],
    "rule57/hinge_zero_crossing_K": 9.70 / RULE57,

    # Addition-ladder regimes measured this round.
    "addition/free_region_slope": ef.get("slope"),
    "addition/free_region_ci_lo": (ef.get("ci") or [None, None])[0],
    "addition/free_region_ci_hi": (ef.get("ci") or [None, None])[1],
    "addition/past_knee_secant": es.get("slope"),
    "addition/e1600_chord_us_per_dispatch": d.get(
        "addition_price_us_per_dispatch_e1600"),

    # Placebo: prefill is untouched by a decode-only injection.
    "placebo/prefill_ms_min": min(prefill),
    "placebo/prefill_ms_max": max(prefill),
    "placebo/prefill_ms_mean": st.mean(prefill),
    "placebo/prefill_ms_sd": st.stdev(prefill),
    "placebo/prefill_spread_pct": 100.0 * (max(prefill) - min(prefill))
                                  / st.mean(prefill),

    # Hygiene.
    "hygiene/all_runs_passed_correctness": int(all(r["passed"] for r in rows)),
    "hygiene/paired_within_session_only": 1,
    "hygiene/level_division_used": 0,
    "hygiene/is_submission_candidate": 0,

    # Planner pricing at the corrected multiplier.
    "planning/pct_score_per_M4_dispatch_us_at_1p890": PCT_PER_M4_DISPATCH_US,
    "planning/pct_score_per_M4_dispatch_us_at_regime_matched":
        0.015228 * k_matched,
    "planning/removal_pct_score_per_dispatch_regime_matched":
        removal * 0.015228 * k_matched,
}
for a, m in sorted(arm_mean.items()):
    summary[f"arm/{a}_us_per_step_mean"] = m
    summary[f"arm/{a}_n"] = len(by_arm[a])
    if arm_sd[a] is not None:
        summary[f"arm/{a}_us_per_step_sd"] = arm_sd[a]
run.summary.update(summary)

ladder = wandb.Table(columns=["session", "pos", "arm", "tag", "dn",
                              "us_per_step", "prefill_ms", "passed"])
dn_map = census.get("dn", {})
for r in rows:
    ladder.add_data(r["session"], r["pos"], r["arm"], r["tag"],
                    dn_map.get(r["arm"]), r["decode"] * 1e6,
                    r["prefill"] * 1e3, bool(r["passed"]))
run.log({"ladder_rows": ladder})

reads = wandb.Table(columns=["read", "value", "lo", "hi", "source"])
reads.add_data("k_dispatch as published", K_DISPATCH, None, None,
               "rule 65 / rule 57")
reads.add_data("k_dispatch regime-matched", k_matched,
               d["k_dispatch_regime_matched_range"][0],
               d["k_dispatch_regime_matched_range"][1], "R108-P")
reads.add_data("k_removal", k_removal, k_removal_range[0], k_removal_range[1],
               "R108-P")
reads.add_data("k_residue", K_RESIDUE, 1.4732, 1.5275, "#107-G tanjiro")
reads.add_data("bytes exponent alpha", 0.4369, None, None, "established")
reads.add_data("latency exponent beta", 0.5, None, None, "established")
run.log({"third_regime_reads": reads})

r93 = wandb.Table(columns=["segment", "us_per_dispatch", "regime"])
for seg, price in [("0->240", -0.43), ("240->480", -0.03), ("480->800", 0.58),
                   ("800->1200", 0.73), ("1200->1600", 1.98),
                   ("1600->2400", 2.36)]:
    r93.add_data(seg, price, "free" if price < 0.5 else "past-knee")
run.log({"r93_segment_prices_same_host": r93})

artifact = wandb.Artifact("maple-alphonse-r108p-ledger", type="analysis")
artifact.add_file(f"{ART}/fit.json")
artifact.add_file(f"{ART}/dn-census.json")
artifact.add_file(f"{ART}/results.md")
for p in sorted(glob.glob(f"{ART}/ladder/*.row.json")):
    artifact.add_file(p, name=f"ladder/{p.rsplit('/', 1)[1]}")
artifact.add_file(f"{REPO}/research/maple-alphonse-r108p-dispatch-removal-symmetry.md")
artifact.add_file(f"{REPO}/research/maple-alphonse-r108p-ladder.sh")
artifact.add_file(f"{REPO}/research/maple-alphonse-r108p-analyse.py")
run.log_artifact(artifact)

print("run:", run.url)
print("run_id:", run.id)
run.finish()
