#!/usr/bin/env python3
"""Log one R93 official receipt (null replicate or ladder rung) to W&B.

Usage:
    python3 research/r93-runs/log_wandb.py <marker> <receipt.json> [source_commit]

`marker` is `null-<n>` or `ladder-K<k>`; the arm and the ladder rung are derived
from it so a mislabelled run is hard to produce.
"""
import json
import re
import sys

import wandb

# Renormalisation constants from the campaign's official-receipt reader: they
# convert a raw per-token timing into a speedup against one fixed baseline draw,
# which is the only cross-session comparison this campaign permits.
NORM_DECODE = 0.013890
NORM_PREFILL = 0.0003845


def num(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_marker(marker: str):
    m = re.fullmatch(r"null-(\d+)", marker)
    if m:
        return "A", 0, int(m.group(1))
    m = re.fullmatch(r"ladder-K(\d+)", marker)
    if m:
        return "B", int(m.group(1)), None
    raise SystemExit("marker must be null-<n> or ladder-K<k>, got %r" % marker)


def main():
    marker, path = sys.argv[1], sys.argv[2]
    arm, extra_dispatches, replicate = parse_marker(marker)
    blob = json.load(open(path))
    blob = blob.get("submission", blob)
    metrics = blob.get("officialMetrics") or blob.get("metrics") or blob

    dspt = num(metrics.get("decode_seconds_per_token"))
    pspt = num(metrics.get("prefill_seconds_per_token"))
    summary = {
        "arm": arm,
        "extra_decode_dispatches": extra_dispatches,
        "replicate": replicate,
        "score": num(blob.get("officialScore") or blob.get("score") or metrics.get("score")),
        "decode_speedup": num(metrics.get("decode_speedup")),
        "prefill_speedup": num(metrics.get("prefill_speedup")),
        "decode_seconds_per_token": dspt,
        "prefill_seconds_per_token": pspt,
        "baseline_decode_seconds_per_token": num(metrics.get("baseline_decode_seconds_per_token")),
        "baseline_prefill_seconds_per_token": num(metrics.get("baseline_prefill_seconds_per_token")),
        "passed_decode_speedup_floor": metrics.get("passed_decode_speedup_floor"),
        "passed_prefill_speedup_floor": metrics.get("passed_prefill_speedup_floor"),
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
        "rejection_reason": blob.get("rejectionReason") or "",
        "error": metrics.get("error", blob.get("error", "")),
        "created_at": blob.get("createdAt") or blob.get("created_at"),
    }
    if dspt:
        summary["decode_us_per_token"] = 1e6 * dspt
        summary["norm_decode_su"] = NORM_DECODE / dspt
    if pspt:
        summary["prefill_us_per_token"] = 1e6 * pspt
        summary["norm_prefill_su"] = NORM_PREFILL / pspt
    if "norm_decode_su" in summary and "norm_prefill_su" in summary:
        summary["ns"] = summary["norm_decode_su"] ** 0.75 * summary["norm_prefill_su"] ** 0.25

    run = wandb.init(
        entity="wandb-applied-ai-team",
        project="mlxfast-maple",
        group="maple-r93-a-m5-receipt-channel",
        name="r93-%s" % marker,
        job_type="official-m5-receipt",
        config={
            "arm": arm,
            "marker": "senpai-r93-%s" % marker,
            "extra_decode_dispatches": extra_dispatches,
            "empty_threadgroup": 8,
            "replicate": replicate,
            "assignment": "maple-r93-a-m5-receipt-channel",
            "revision": "r93-a-rev1",
            "student": "maple-tanjiro",
            "source_commit": sys.argv[3] if len(sys.argv) > 3 else None,
            "submission_id": blob.get("id") or blob.get("submission_id"),
            "host": "official M5 Max (ranked)",
        },
    )
    run.log({k: v for k, v in summary.items() if isinstance(v, (int, float))})
    for key, value in summary.items():
        run.summary[key] = value
    print(run.url)
    run.finish()


if __name__ == "__main__":
    main()
