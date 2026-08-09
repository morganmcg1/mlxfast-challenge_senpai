#!/usr/bin/env python3
"""Log one R91-B ranked-receipt arm to W&B.

Usage:
    python3 research/r91b-runs/log_wandb.py <arm> <receipt.json>

<receipt.json> is the raw receipt/metrics blob captured from `mlxfast`.
"""
import json
import sys

import wandb

LEADERBOARD_BEST = 2.61650354381456
# Renormalisation constants from the campaign's official-receipt reader.
NORM_DECODE = 0.013890
NORM_PREFILL = 0.0003845


def num(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def main():
    arm, path = sys.argv[1], sys.argv[2]
    blob = json.load(open(path))
    blob = blob.get("submission", blob)

    metrics = blob.get("officialMetrics") or blob.get("metrics") or blob
    score = num(blob.get("officialScore") or blob.get("score") or metrics.get("score"))
    dsu = num(metrics.get("decode_speedup"))
    psu = num(metrics.get("prefill_speedup"))
    dspt = num(metrics.get("decode_seconds_per_token"))
    pspt = num(metrics.get("prefill_seconds_per_token"))
    base_dspt = num(metrics.get("baseline_decode_seconds_per_token"))
    base_pspt = num(metrics.get("baseline_prefill_seconds_per_token"))

    summary = {
        "score": score,
        "decode_speedup": dsu,
        "prefill_speedup": psu,
        "decode_seconds_per_token": dspt,
        "prefill_seconds_per_token": pspt,
        "baseline_decode_seconds_per_token": base_dspt,
        "baseline_prefill_seconds_per_token": base_pspt,
        "passed_decode_speedup_floor": metrics.get("passed_decode_speedup_floor"),
        "passed_prefill_speedup_floor": metrics.get("passed_prefill_speedup_floor"),
        "decode_speedup_floor": num(metrics.get("decode_speedup_floor")),
        "prefill_speedup_floor": num(metrics.get("prefill_speedup_floor")),
        "passed_correctness": metrics.get("passed_correctness"),
        "checked_steps": metrics.get("checked_steps"),
        "case_count": metrics.get("case_count"),
        "max_abs_diff": metrics.get("max_abs_diff"),
        "first_failing_step": metrics.get("first_failing_step"),
        "gpqa_ttft_passed": metrics.get("gpqa_ttft_passed"),
        "gpqa_ttft_seconds": num(metrics.get("gpqa_ttft_seconds")),
        "semantic_gpqa_passed": metrics.get("semantic_gpqa_passed"),
        "semantic_gpqa_pass_count": metrics.get("semantic_gpqa_pass_count"),
        "partial_result": metrics.get("partial_result"),
        "peak_ram_gb": num(metrics.get("peak_ram_gb")),
        "status": blob.get("status"),
        "improved": blob.get("improved"),
        "submission_commit_sha": blob.get("submissionCommitSha"),
        "rejection_reason": blob.get("rejectionReason") or "",
        "error": metrics.get("error", blob.get("error", "")),
        "leaderboard_best": LEADERBOARD_BEST,
    }
    if score is not None:
        summary["score_minus_best"] = score - LEADERBOARD_BEST
        summary["score_minus_best_pct"] = 100.0 * (score / LEADERBOARD_BEST - 1.0)
    if dspt:
        summary["norm_decode_su"] = NORM_DECODE / dspt
    if pspt:
        summary["norm_prefill_su"] = NORM_PREFILL / pspt
        seed_ms = 512000.0 * pspt
        summary["seed_forward_ms"] = seed_ms
        if dspt:
            summary["steady_step_ms"] = 1000.0 * dspt - seed_ms
    if "norm_decode_su" in summary and "norm_prefill_su" in summary:
        summary["ns"] = summary["norm_decode_su"] ** 0.75 * summary["norm_prefill_su"] ** 0.25

    run = wandb.init(
        entity="wandb-applied-ai-team",
        project="mlxfast-maple",
        group="maple-r91b-ranked-base-receipt",
        name=f"r91b-arm{arm}-ranked-receipt",
        job_type="official-m5-receipt",
        config={
            "arm": arm,
            "assignment": "maple-r91-b-ranked-base-receipt",
            "revision": "r91-b-rev1",
            "student": "maple-tanjiro",
            "arm_source_commit": sys.argv[3] if len(sys.argv) > 3 else None,
            "service_commit": metrics.get("commit") or blob.get("submissionCommitSha"),
            "submission_id": blob.get("id") or blob.get("submission_id"),
            "host": "official M5 Max (ranked)",
            "zero_edit": True,
        },
    )
    run.log({k: v for k, v in summary.items() if isinstance(v, (int, float))})
    for key, value in summary.items():
        run.summary[key] = value
    print(run.url)
    run.finish()


if __name__ == "__main__":
    main()
