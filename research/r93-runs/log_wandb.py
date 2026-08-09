#!/usr/bin/env python3
"""Log one R93 official receipt (null replicate or ladder rung) to W&B.

Usage:
    python3 research/r93-runs/log_wandb.py <marker> <receipt.json> [source_commit]

`marker` is `null-<n>`, `ladder-K<k>` or `probe-<target>-<kind>-<n>`; the arm is derived
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

# Arm A reference, section 2.3 of RESULTS.md: mean and sd of the five
# machine-code-identical null receipts, in microseconds per token.
NULL_DECODE_US, NULL_DECODE_SD_US, NULL_N = 4910.9253, 14.4308, 5
NULL_PREFILL_US = 187.8717


def num(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_marker(marker: str):
    m = re.fullmatch(r"null-(\d+)", marker)
    if m:
        return "A", 0, int(m.group(1)), {}
    m = re.fullmatch(r"ladder-K(\d+)", marker)
    if m:
        return "B", int(m.group(1)), None, {}
    m = re.fullmatch(r"probe-(qkv|oproj|routed)-(fma|imad|ld8|ld16)-(\d+)", marker)
    if m:
        probe = {
            "probe_spec": "%s:%s:%s" % m.groups(),
            "probe_target": m.group(1),
            "probe_kind": m.group(2),
            "probe_n": int(m.group(3)),
        }
        return "C", 0, None, probe
    raise SystemExit(
        "marker must be null-<n>, ladder-K<k> or probe-<target>-<kind>-<n>, got %r" % marker
    )


def main():
    marker, path = sys.argv[1], sys.argv[2]
    arm, extra_dispatches, replicate, probe = parse_marker(marker)
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
    if probe and dspt:
        delta = 1e6 * dspt - NULL_DECODE_US
        # A single new draw against a mean of NULL_N, so the variance carries
        # both the draw and the reference mean.
        se = NULL_DECODE_SD_US * (1.0 + 1.0 / NULL_N) ** 0.5
        summary.update(
            probe,
            delta_decode_us_vs_null=delta,
            delta_decode_pct_vs_null=100.0 * delta / NULL_DECODE_US,
            delta_decode_t_vs_null=delta / se,
            delta_prefill_pct_vs_null=100.0 * (1e6 * pspt - NULL_PREFILL_US) / NULL_PREFILL_US,
        )
        if probe["probe_n"]:
            summary["delta_decode_us_per_injected_op"] = delta / probe["probe_n"]

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
            "empty_threadgroup": 8 if extra_dispatches else None,
            "replicate": replicate,
            **probe,
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
