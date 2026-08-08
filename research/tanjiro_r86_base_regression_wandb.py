#!/usr/bin/env python3
"""Log the R86-A base-vs-best-ever regression diagnosis to W&B.

Timings are read straight out of the `benchmark.sh --local-iterate` logs written
by `research/tanjiro-r86-matched-pair.sh`, so the W&B run and
`research/tanjiro-r86-base-decode-regression.md` cannot drift apart.

  python3 research/tanjiro_r86_base_regression_wandb.py research/r86-pair-results
"""
import argparse
import glob
import json
import math
import os
import re
import statistics
import sys

import wandb

ENTITY = "wandb-applied-ai-team"
PROJECT = "mlxfast-maple"

BASE_SHA = "f64456dd2dc503af080dca65bddfb922164c7bc5"
FRONTIER_SHA = "149212f78ef630da4e00f1123420fc6250e5e9a9"

# Ranked M5 receipts. Neither was measured in this session; both are quoted from
# the official submission records named in PR #460.
M5 = {
    "leaderboard_bar_submission": "cc6ddc1",
    "leaderboard_bar_score": 2.6165035,
    "our_best_ever_submission": "97a5090c",
    "our_best_ever_score": 2.58882784082067,
    "base_control_submission": "25b0b722",
    "base_control_score": 2.55158458026643,
    "base_prefill_speedup": 1.921890350333331,
    "frontier_prefill_speedup": 2.001471,
    "base_decode_speedup": 2.804381476645093,
    "frontier_decode_speedup": 2.820684,
    "base_prefill_seconds_per_token": 0.000190980224609375,
    "base_decode_seconds_per_token": 0.0049335732421875,
    "seed_forward_seconds": 0.097782,
}

# Non-comment, non-blank changed lines between BASE_SHA and FRONTIER_SHA over the
# 97 editablePaths, with the static verdict from the note's sections 3 and 4.
STATIC_COLS = ["path", "noncomment_changed_lines", "cluster", "verdict"]
STATIC = [
    ("MLXLMCommon/BaseConfiguration.swift", 0, "assigned-decode", "comment-only"),
    ("MLXLMCommon/BatchKVCache.swift", 0, "assigned-decode", "comment-only"),
    ("MLXLMCommon/CompilableKVCache.swift", 0, "assigned-decode", "comment-only"),
    ("MLXLMCommon/CompilableRotatingKVCache.swift", 0, "assigned-decode", "comment-only"),
    ("MLXLMCommon/CompiledDecode.swift", 0, "assigned-decode", "comment-only"),
    ("MLXLMCommon/Evaluate.swift", 0, "assigned-decode", "comment-only"),
    ("MLXLMCommon/KVCache.swift", 0, "assigned-decode", "comment-only"),
    ("MLXLMCommon/RoPEApplication.swift", 0, "assigned-decode", "comment-only"),
    ("MLXFastModel/LagunaConfig.swift", 0, "other", "comment-only"),
    ("MLXFastModel/LagunaRuntimeWeights.swift", 0, "other", "comment-only"),
    ("MLXFastModel/LagunaLmHeadPrune.swift", 0, "other", "array-literal reflow"),
    ("MLXFastTransform/Transform.swift", 55, "other", "gemma4-only branch; inert for Laguna"),
    ("MLXFastModel/LagunaRuntimeModel.swift", 492, "carrier", "only live behavioural difference"),
    ("mlx/backend/metal/matmul.cpp", -1, "nax", "DARKBLOOM_STEEL_REGULAR_SKINNY_TILE default OFF"),
    ("mlx/backend/metal/quantized.cpp", -1, "nax", "EXPERT_BK128 default OFF; NAX_GATHER_PROBE default 0"),
    ("mlx/backend/metal/kernels/fp_quantized_nax.h", -1, "nax", "probe scaffolding if-constexpr dead; kWideLoadShapeOk widened, BK=128 only"),
    ("mlx-generated/fp_quantized_nax.cpp", -1, "nax", "same as header; runtime-JIT source 132 lines longer"),
    ("MLXFastTransform/AffineMetadataCoding.swift", 438, "artifact", "mlxfast reset refill of a 0-line stub"),
    ("MLXFastTransform/TiedHeadMetadataCoding.swift", 401, "artifact", "mlxfast reset refill of a 0-line stub"),
]

# Cluster decomposition of the one carrier file (note section 5).
CLUSTER_COLS = ["cluster", "region", "lines", "present_in", "verdict"]
CLUSTERS = [
    ("A", "lagunaFullFusedAttentionKernel softmax reduction", 14, "both differ",
     "only viable carrier of the -3.98% prefill loss"),
    ("B", "LagunaFullParamsMemoStore", 40, "base only",
     "decode win added after 97a5090c"),
    ("C", "lagunaSharedSwiGLUQMVRows1Kernel + pairwise scales", 132, "base only",
     "decode win added after 97a5090c"),
    ("D", "PR #27 M5 hardware-constant instrument", 258, "frontier only",
     "self-described as deliberately slowing; inert at defaults; must not be re-imported"),
]

RUN_COLS = ["arm", "rep", "slot", "prefill_seconds_per_token",
            "decode_seconds_per_token", "golden_hash", "passed_correctness",
            "checked_steps"]

# Slot order actually executed by tanjiro-r86-matched-pair.sh (ABBA-ordered).
SLOT = {("rev", 1): 1, ("base", 1): 2, ("base", 2): 3,
        ("rev", 2): 4, ("rev", 3): 5, ("base", 3): 6}


def parse_arm(log_path, json_path):
    text = open(log_path).read()
    prefill = float(re.findall(r"prefill_seconds_per_token=([0-9.]+)", text)[-1])
    decode = float(re.findall(r"decode_seconds_per_token=([0-9.]+)", text)[-1])
    metrics = json.load(open(json_path))["metrics"]
    return prefill, decode, metrics


def ci95_of_difference(a, b):
    """Two-sample t interval on mean(a) - mean(b) with a pooled variance."""
    na, nb = len(a), len(b)
    df = na + nb - 2
    sp2 = ((na - 1) * statistics.variance(a) + (nb - 1) * statistics.variance(b)) / df
    se = math.sqrt(sp2 * (1.0 / na + 1.0 / nb))
    # t(0.975, df=4); the design is fixed at n=3 per arm.
    tcrit = {4: 2.776, 6: 2.447, 8: 2.306}[df]
    delta = statistics.mean(a) - statistics.mean(b)
    return delta, delta - tcrit * se, delta + tcrit * se, math.sqrt(sp2), se


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("results_dir")
    args = ap.parse_args()

    rows, series = [], {"base": {"prefill": [], "decode": []},
                        "rev": {"prefill": [], "decode": []}}
    hashes = set()
    for log_path in sorted(glob.glob(os.path.join(args.results_dir, "*.log"))):
        arm, rep = re.match(r"(base|rev)-r(\d)\.log", os.path.basename(log_path)).groups()
        rep = int(rep)
        json_path = log_path[:-4] + ".json"
        prefill, decode, metrics = parse_arm(log_path, json_path)
        series[arm]["prefill"].append(prefill * 1e6)
        series[arm]["decode"].append(decode * 1e6)
        hashes.add(metrics["golden_hash"])
        rows.append([arm, rep, SLOT[(arm, rep)], prefill, decode,
                     metrics["golden_hash"], metrics["passed_correctness"],
                     metrics["checked_steps"]])

    if len(hashes) != 1:
        sys.exit(f"golden hashes diverged across arms: {hashes}")

    summary = {"golden_hash": hashes.pop(), "golden_hash_identical_all_arms": True}
    for axis in ("decode", "prefill"):
        a, b = series["base"][axis], series["rev"][axis]
        delta, lo, hi, sd, se = ci95_of_difference(a, b)
        summary.update({
            f"m4_{axis}_base_mean_us": statistics.mean(a),
            f"m4_{axis}_rev_mean_us": statistics.mean(b),
            f"m4_{axis}_delta_us": delta,
            f"m4_{axis}_delta_ci95_lo_us": lo,
            f"m4_{axis}_delta_ci95_hi_us": hi,
            f"m4_{axis}_pooled_sd_us": sd,
            f"m4_{axis}_se_of_difference_us": se,
        })

    # M5 receipt arithmetic: score = decode^0.75 * prefill^0.25.
    prefill_loss = 1.0 - M5["base_prefill_speedup"] / M5["frontier_prefill_speedup"]
    decode_loss = 1.0 - M5["base_decode_speedup"] / M5["frontier_decode_speedup"]
    decode_us = M5["base_decode_seconds_per_token"] * 1e6 * decode_loss
    # Share of the decode pass spent in the shared 512-token seed forward.
    sigma = M5["seed_forward_seconds"] / (128 * M5["base_decode_seconds_per_token"])
    summary.update({
        "m5_prefill_loss_pct": 100 * prefill_loss,
        "m5_decode_loss_pct": 100 * decode_loss,
        "m5_decode_loss_us_per_step": decode_us,
        "m5_score_loss_pp": 100 * (0.75 * decode_loss + 0.25 * prefill_loss),
        "m5_prefill_share_of_score_loss_pct":
            100 * 0.25 * prefill_loss / (0.75 * decode_loss + 0.25 * prefill_loss),
        "m5_seed_forward_share_of_decode": sigma,
        "m5_pure_seed_forward_predicted_decode_loss_pct": 100 * sigma * prefill_loss,
        "m4_decode_resolution_us": summary["m4_decode_delta_ci95_hi_us"]
            - summary["m4_decode_delta_us"],
        "m4_underpowered_factor": (summary["m4_decode_delta_ci95_hi_us"]
            - summary["m4_decode_delta_us"]) / decode_us,
        "gap_to_leaderboard_bar_after_full_recovery_pct":
            100 * (1.0 - M5["our_best_ever_score"] / M5["leaderboard_bar_score"]),
    })

    run = wandb.init(
        entity=ENTITY, project=PROJECT,
        name="tanjiro-r86-base-decode-regression",
        job_type="diagnosis",
        config={
            "assignment_id": "maple-r86-a-base-decode-regression",
            "revision_id": "r86-a-rev1",
            "pr": 460,
            "base_sha": BASE_SHA,
            "frontier_reconstruction_sha": FRONTIER_SHA,
            "reconstruction_method": "mlxfast reset <submission> -f (not fern's harness)",
            "host": "Apple M4 Pro, 20 cores, Apple GPU generation 16 (no _nax)",
            "design": "matched pair, ABBA-ordered, 3 repeats/arm, flips only LagunaRuntimeModel.swift",
            "local_allow_golden_drift": "unset",
            "MLXFAST_LOCAL_FAN_PROMPT": 0,
            "real_differing_editable_files": 17,
            "assignment_claimed_differing_files": 11,
            **M5,
        },
    )
    run.summary.update(summary)
    run.log({"runs": wandb.Table(columns=RUN_COLS, data=rows),
             "static_classification": wandb.Table(columns=STATIC_COLS, data=STATIC),
             "carrier_clusters": wandb.Table(columns=CLUSTER_COLS, data=CLUSTERS)})
    print(run.url)
    run.finish()


if __name__ == "__main__":
    main()
