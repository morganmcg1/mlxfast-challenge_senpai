#!/usr/bin/env python3
"""Publish the r97-d rule-58 falsification test to W&B (research only).

  python3 research/frieren_r97_wandb_log.py \
      --summary research/r97-runs/stage1/analysis.json \
      --stage0 research/r97-runs/stage0/gates.json

Logs one run per ladder rung (so the response curve is plottable) plus one
summary run carrying the estimate, its interval, and both terminal gates.
"""
import argparse
import json
import os

import wandb

PROJECT = os.environ.get("WANDB_PROJECT", "mlxfast-maple")
ENTITY = os.environ.get("WANDB_ENTITY", "wandb-applied-ai-team")
TAGS = ["maple", "student:maple-frieren", "pr531", "r97-d", "rule58"]


def init(name, job_type, config, notes=""):
    wandb_dir = os.environ.get("WANDB_DIR", "/tmp/r97/wandb")
    os.makedirs(wandb_dir, exist_ok=True)
    return wandb.init(
        dir=wandb_dir, entity=ENTITY, project=PROJECT, name=name, notes=notes,
        job_type=job_type, tags=TAGS, config=config, reinit=True,
    )


def put(run, mapping):
    for k, v in mapping.items():
        run.summary[k] = v if isinstance(v, (int, float, bool)) else json.dumps(v)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--summary", required=True, help="frieren_r97_analyze.py --json output")
    ap.add_argument("--stage0", help="stage 0 gate json")
    ap.add_argument("--prefix", default="r97d")
    ap.add_argument("--summary-only", action="store_true",
                    help="publish only the summary run (per-rung runs already logged)")
    args = ap.parse_args()

    with open(args.summary) as fh:
        a = json.load(fh)
    stage0 = {}
    if args.stage0 and os.path.exists(args.stage0):
        with open(args.stage0) as fh:
            stage0 = json.load(fh)

    common = {
        "host": "m4pro-48gb",
        "instrument": "DARKBLOOM_INJECT_PREFILL_MATMULS",
        "submitted_bytes_changed": 0,
        "prompt_tokens": a["runs"][0].get("prompt_tokens"),
        "decode_steps": a["runs"][0].get("decode_steps"),
        "predicted_R": a["predicted_R"],
    }

    for r in [] if args.summary_only else sorted(a["runs"], key=lambda x: x["idx"]):
        run = init(f"{args.prefix}-run{r['idx']:02d}-n{r['rung']}", "ladder-run",
                   {**common, "rung": r["rung"], "block": r["block"],
                    "order_index": r["idx"]})
        put(run, {
            "decode_us_per_step": r["D"],
            "prefill_us_per_token": r["P"],
            "passed_correctness": r["passed"],
            "seed_forward_ms_logged": r.get("seed_ms") or 0.0,
            "mean_step_ms": r.get("mean_step_ms") or 0.0,
            "seed_implied_ms": r.get("seed_implied_ms") or 0.0,
            "prefill_window_ms": r.get("prefill_total_ms") or 0.0,
            "decode_us_per_step_if_steps_only": r.get("D_if_steps_only") or 0.0,
        })
        run.finish()

    run = init(f"{args.prefix}-summary", "rule58-falsification", common,
               notes="Does the 512-token seed prefill run inside the decode "
                     "timer? Response ratio dD/dP of output-neutral "
                     "prefill-only work.")
    put(run, {
        "rule58_response_ratio": a["R"],
        "rule58_response_ratio_ci_low": a["ci_low"],
        "rule58_response_ratio_ci_high": a["ci_high"],
        "rule58_prediction_h58": a["predicted_R"],
        "rule58_prediction_h0": 0,
        "rule58_prediction_brief": 16,
        "rule58_within_run_implied_over_window": a["within_run_implied_over_window"],
        "verdict_pass": a["pass"],
        **{f"verdict_{k}": v for k, v in a["verdict"].items()},
        "per_rung": a["per_rung"],
        **{f"estimator_{k}": v for k, v in a["estimators"].items()},
        **{f"gate0_{k}": v for k, v in stage0.items()},
        "gate0_prefill_only": stage0.get("gate0a_prefill_only"),
        "gate0_bitexact": stage0.get("gate0b_bitexact"),
    })
    for rung, m in sorted(a["per_rung"].items(), key=lambda kv: int(kv[0])):
        run.log({
            "rung": int(rung),
            "rule58_delta_decode_us_per_step": m["dD_us"],
            "rule58_delta_prefill_us_per_token": m["dP_us"],
            "rule58_response_ratio_at_rung": m["ratio"] if m["ratio"] == m["ratio"] else 0.0,
        })
    run.finish()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
