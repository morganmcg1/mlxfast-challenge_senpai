#!/usr/bin/env python3
"""Publish an R109-F paired local-submit timing family to W&B.

Consumes the same `score.local-submit.<family><n>.json` snapshots as
`research/fern_r109_timing_ledger.py` and writes one run per invocation into
wandb-applied-ai-team/mlxfast-maple, with a per-replicate table, per-family
dispersion summary, and (when more than one family is named) the paired
candidate-vs-baseline ratios.

The first named family is the reference/baseline.  Ratios are
baseline_seconds / candidate_seconds, so >1 means the candidate is faster.

Usage:
    python3 research/fern_r109_wandb_log.py --run-name fern-r109f-stage0-baseline \
        --tags r109-F stage-0 baseline --families base
"""

import argparse
import os
import platform
import subprocess

import wandb

from fern_r109_timing_ledger import load_families, paired, summarize

ENTITY = "wandb-applied-ai-team"
PROJECT = "mlxfast-maple"

# Ranked context, from the R109-F assignment brief.
LEADER_SCORE = 2.61650354
BEST_OWN_OFFICIAL_SCORE = 2.60664970  # receipt e27f1ce
BEST_OWN_OFFICIAL_COMMIT = "5c542169b5e6c295805f50fa65df3150816eb443"
REQUIRED_WEIGHTED_RATIO = 1.003780272
DECODE_ONLY_TIE_RATIO = 1.005043536
PREFILL_ONLY_TIE_RATIO = 1.015207047
DETECTION_FLOOR_PCT = 0.243  # two n=3 families, ns axis


def sh(*args):
    try:
        return subprocess.run(
            args, capture_output=True, text=True, check=True
        ).stdout.strip()
    except Exception:
        return ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-name", required=True)
    ap.add_argument("--families", nargs="+", required=True)
    ap.add_argument("--tags", nargs="*", default=[])
    ap.add_argument("--notes", default="")
    ap.add_argument("--job-type", default="local-timing")
    args = ap.parse_args()

    fams = load_families()
    missing = [f for f in args.families if f not in fams]
    if missing:
        raise SystemExit(f"missing families {missing}; have {sorted(fams)}")

    summaries = {f: summarize(f, fams[f]) for f in args.families}
    ref = summaries[args.families[0]]

    cfg = {
        "round": "r109-F",
        "arm": "maple-fern integration + submission",
        "host/chip": sh("sysctl", "-n", "machdep.cpu.brand_string"),
        "host/mem_bytes": int(sh("sysctl", "-n", "hw.memsize") or 0),
        "host/os": platform.platform(),
        "host/is_ranked_m5": False,
        "harness/mode": "benchmark.sh --local-submit",
        "harness/golden": "correctness_prompts/public_longcopy_gate_english_512_1024.json",
        "git/head": sh("git", "rev-parse", "HEAD"),
        "git/branch": sh("git", "rev-parse", "--abbrev-ref", "HEAD"),
        "bar/leader_score": LEADER_SCORE,
        "bar/best_own_official_score": BEST_OWN_OFFICIAL_SCORE,
        "bar/best_own_official_commit": BEST_OWN_OFFICIAL_COMMIT,
        "bar/required_weighted_ratio": REQUIRED_WEIGHTED_RATIO,
        "bar/decode_only_tie_ratio": DECODE_ONLY_TIE_RATIO,
        "bar/prefill_only_tie_ratio": PREFILL_ONLY_TIE_RATIO,
        "bar/detection_floor_pct": DETECTION_FLOOR_PCT,
        "families": args.families,
        "reference_family": args.families[0],
    }

    run = wandb.init(
        entity=ENTITY,
        project=PROJECT,
        name=args.run_name,
        job_type=args.job_type,
        tags=args.tags,
        config=cfg,
        notes=args.notes,
    )

    reps = wandb.Table(
        columns=[
            "family", "replicate", "commit", "timestamp",
            "decode_s_per_token", "prefill_s_per_token", "harness_score",
            "passed", "passed_correctness", "max_abs_diff", "peak_ram_gb",
            "golden_hash",
        ]
    )
    for fam in args.families:
        for r in fams[fam]:
            reps.add_data(
                fam, r["replicate"], r["commit"], r["timestamp"],
                r["decode"], r["prefill"], r["score"], r["passed"],
                r["correct"], r["max_abs_diff"], r["peak_ram_gb"],
                r["golden_hash"],
            )
    run.log({"ledger/replicates": reps})

    fam_table = wandb.Table(
        columns=[
            "family", "n", "decode_median", "decode_min", "decode_max",
            "decode_spread_pct", "prefill_median", "prefill_min",
            "prefill_max", "prefill_spread_pct", "all_correct",
            "max_abs_diff",
        ]
    )
    flat = {}
    for fam in args.families:
        s = summaries[fam]
        fam_table.add_data(
            fam, s["n"], s["decode_median"], s["decode_min"], s["decode_max"],
            s["decode_spread"] * 100, s["prefill_median"], s["prefill_min"],
            s["prefill_max"], s["prefill_spread"] * 100, s["all_correct"],
            s["max_abs_diff"],
        )
        flat[f"{fam}/n"] = s["n"]
        flat[f"{fam}/decode_median_s_per_token"] = s["decode_median"]
        flat[f"{fam}/prefill_median_s_per_token"] = s["prefill_median"]
        flat[f"{fam}/decode_spread_pct"] = s["decode_spread"] * 100
        flat[f"{fam}/prefill_spread_pct"] = s["prefill_spread"] * 100
        flat[f"{fam}/all_correct"] = int(s["all_correct"])
        flat[f"{fam}/max_abs_diff"] = s["max_abs_diff"]
    run.log({"ledger/families": fam_table})

    pair_table = wandb.Table(
        columns=[
            "candidate", "vs", "decode_ratio", "prefill_ratio",
            "weighted_ratio", "clears_required_ratio",
        ]
    )
    for fam in args.families[1:]:
        pr = paired(ref, summaries[fam])
        pair_table.add_data(
            fam, args.families[0], pr["decode_ratio"], pr["prefill_ratio"],
            pr["weighted_ratio"], pr["weighted_ratio"] >= REQUIRED_WEIGHTED_RATIO,
        )
        flat[f"pair/{fam}/decode_ratio"] = pr["decode_ratio"]
        flat[f"pair/{fam}/prefill_ratio"] = pr["prefill_ratio"]
        flat[f"pair/{fam}/weighted_ratio"] = pr["weighted_ratio"]
    if args.families[1:]:
        run.log({"ledger/pairs": pair_table})

    run.summary.update(flat)
    print(f"WANDB_RUN_ID={run.id}")
    print(f"WANDB_RUN_URL={run.url}")
    run.finish()


if __name__ == "__main__":
    os.environ.setdefault("WANDB_SILENT", "false")
    main()
