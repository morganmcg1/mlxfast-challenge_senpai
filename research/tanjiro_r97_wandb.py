#!/usr/bin/env python3
"""Publish the R97-B prefill threadgroup-count campaign to W&B.

Consumes the paired ABBA A/B score receipts written by
``research/tanjiro-r97-ab.sh`` and the GPUPROF dispatch census written by
``research/tanjiro-r97-census.sh``. No GPU work happens here.

Usage:
  python3 research/tanjiro_r97_wandb.py \
      --ab-dir research/r97-logs --ab-prefix ab --ab-reps 4 \
      --census-off research/r97-logs/profile.off.log \
      --census-on  research/r97-logs/profile.on.log \
      --gate-off research/r97-logs/gate.1.off.json \
      --gate-on  research/r97-logs/gate.1.on.json \
      --verdict "P2+P2b GO"
"""
import argparse
import json
import os
import re
import statistics

import wandb

ENTITY = "wandb-applied-ai-team"
PROJECT = "mlxfast-maple"
BASE_SHA = "b78e7cdb80b5ae5f1cb1fdd39803322fb283ae5e"

# Rule-58 score conversion for this campaign: one millisecond off the 512-token
# prefill is worth this much normalised score, at the pinned calibration.
SCORE_PCT_PER_MS_PREFILL = 0.373
NORM_DECODE_NUM = 0.013890
NORM_PREFILL_NUM = 0.0003845


def read_score(path):
    with open(path) as fh:
        doc = json.load(fh)
    m = doc["metrics"]
    return {
        "prefill_ms": 512000.0 * m["prefill_seconds_per_token"],
        "decode_ms": 1000.0 * m["decode_seconds_per_token"],
        "prefill_spt": m["prefill_seconds_per_token"],
        "decode_spt": m["decode_seconds_per_token"],
        "score": doc["score"],
        "passed": doc["passed"],
        "passed_correctness": m["passed_correctness"],
        "max_abs_diff": m["max_abs_diff"],
        "golden_hash": m["golden_hash"],
        "decode_speedup": m.get("decode_speedup"),
        "prefill_speedup": m.get("prefill_speedup"),
    }


FAMILY_RE = re.compile(
    r"^\s+([a-z0-9_]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.-]+)\s+(\d+)\s*$")


def read_census(path):
    """Return (total_dispatches, {family: {"n": n, "ms": ms}})."""
    with open(path) as fh:
        text = fh.read()
    disp = [int(x) for x in re.findall(r"dispatches=\s*(\d+)", text)]
    families = {}
    in_family = False
    for line in text.splitlines():
        if line.strip().startswith("family") and "n/req" in line:
            in_family = True
            continue
        if not in_family:
            continue
        m = FAMILY_RE.match(line)
        if m:
            families[m.group(1)] = {"n": float(m.group(2)),
                                    "ms": float(m.group(3))}
    if not families:
        raise SystemExit(f"no GPUPROF family table found in {path}")
    return (disp[-1] if disp else None), families


def paired(vals_off, vals_on, key):
    d = [on[key] - off[key] for off, on in zip(vals_off, vals_on)]
    n = len(d)
    mean = statistics.fmean(d)
    sd = statistics.stdev(d) if n > 1 else float("nan")
    sem = sd / (n ** 0.5) if n > 1 else float("nan")
    return mean, sd, sem, n


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ab-dir", default="research/r97-logs")
    ap.add_argument("--ab-prefix", default="ab")
    ap.add_argument("--ab-reps", type=int, default=4)
    ap.add_argument("--census-off")
    ap.add_argument("--census-on")
    ap.add_argument("--gate-off")
    ap.add_argument("--gate-on")
    ap.add_argument("--verdict", required=True)
    ap.add_argument("--name", default="maple-tanjiro-r97b-prefill-tg-count")
    ap.add_argument("--notes", default="")
    args = ap.parse_args()

    offs, ons, reps_used = [], [], []
    for i in range(1, args.ab_reps + 1):
        po = os.path.join(args.ab_dir, f"{args.ab_prefix}.{i}.off.json")
        pn = os.path.join(args.ab_dir, f"{args.ab_prefix}.{i}.on.json")
        if not (os.path.exists(po) and os.path.exists(pn)):
            continue
        offs.append(read_score(po))
        ons.append(read_score(pn))
        reps_used.append(i)

    run = wandb.init(
        entity=ENTITY,
        project=PROJECT,
        name=args.name,
        job_type="prefill-dispatch-ablation",
        config={
            "assignment_id": "maple-r97-b-prefill-tg-count",
            "revision_id": "r97-b-rev1",
            "pr_number": 527,
            "branch": "maple-tanjiro/r97-prefill-tg-count",
            "base_sha": BASE_SHA,
            "student": "maple-tanjiro",
            "host": "M4 Pro, 20 GPU cores, Apple GPU generation 16, "
                    "48 GiB unified (low-memory startup profile), macOS 26.5.2",
            "nax_kernels_reachable": False,
            "scored_file": "Sources/MLXFastModel/LagunaRuntimeModel.swift",
            "mechanisms": {
                "P2": "DARKBLOOM_FUSED_QKV row-concatenated [Wq;Wk;Wv] bf16 "
                      "bank, prefill only",
                "P2b": "copy-free bank consumption in the four prefill "
                       "QK-norm+RoPE kernels via an explicit layout descriptor",
            },
            "knobs": ["DARKBLOOM_FUSED_QKV"],
            "ab_design": "ABBA alternating same-binary A/B, ./benchmark.sh "
                         "--local-iterate",
            "ab_reps": reps_used,
            "profiler": "DARKBLOOM_GPU_PROFILE=1 DARKBLOOM_GPU_PROFILE_SPLIT=1",
            "score_pct_per_ms_prefill": SCORE_PCT_PER_MS_PREFILL,
            "m5_regular_nax_tile": "bm=64 bn=128 bk=256 wm=2 wn=4",
        },
        tags=["maple-tanjiro", "pr-527", "r97-b", "fused-qkv", "prefill",
              "dispatch-count", "m4pro-directional"],
        notes=args.notes,
    )

    if offs:
        tbl = wandb.Table(columns=[
            "rep", "arm", "prefill_ms", "decode_ms", "score",
            "passed_correctness", "max_abs_diff", "golden_hash"])
        for i, off, on in zip(reps_used, offs, ons):
            for arm, e in (("off", off), ("on", on)):
                tbl.add_data(i, arm, e["prefill_ms"], e["decode_ms"],
                             e["score"], e["passed_correctness"],
                             e["max_abs_diff"], e["golden_hash"])
        run.log({"ab/reps": tbl})

        for key, label in (("prefill_ms", "prefill_ms_fused_qkv"),
                           ("decode_ms", "decode_ms_fused_qkv")):
            mean, sd, sem, n = paired(offs, ons, key)
            run.summary[f"{label}/delta_mean"] = mean
            run.summary[f"{label}/delta_sd"] = sd
            run.summary[f"{label}/delta_sem"] = sem
            run.summary[f"{label}/n_pairs"] = n
            run.summary[f"{label}/off_mean"] = statistics.fmean(
                e[key] for e in offs)
            run.summary[f"{label}/on_mean"] = statistics.fmean(
                e[key] for e in ons)

        pm, _, psem, _ = paired(offs, ons, "prefill_ms")
        run.summary["prefill_ms_fused_qkv/score_pct_local"] = \
            -pm * SCORE_PCT_PER_MS_PREFILL
        run.summary["prefill_ms_fused_qkv/score_pct_local_sem"] = \
            psem * SCORE_PCT_PER_MS_PREFILL
        run.summary["golden_hash_identical"] = len(
            {e["golden_hash"] for e in offs + ons}) == 1
        run.summary["all_arms_correct"] = all(
            e["passed_correctness"] for e in offs + ons)
        run.summary["max_abs_diff_max"] = max(e["max_abs_diff"]
                                              for e in offs + ons)

    if args.census_off and args.census_on:
        off_tot, off_fam = read_census(args.census_off)
        on_tot, on_fam = read_census(args.census_on)
        ctbl = wandb.Table(columns=[
            "family", "off_n", "on_n", "delta_n", "off_ms", "on_ms", "delta_ms"])
        for fam in sorted(set(off_fam) | set(on_fam)):
            o = off_fam.get(fam, {"n": 0.0, "ms": 0.0})
            n_ = on_fam.get(fam, {"n": 0.0, "ms": 0.0})
            ctbl.add_data(fam, o["n"], n_["n"], n_["n"] - o["n"],
                          o["ms"], n_["ms"], n_["ms"] - o["ms"])
        run.log({"census/families": ctbl})
        run.summary["census/dispatches_off"] = off_tot
        run.summary["census/dispatches_on"] = on_tot
        run.summary["census/dispatches_delta"] = on_tot - off_tot
        for fam in ("steel_gemm_bf16", "qk_norm_rope", "elementwise"):
            o = off_fam.get(fam, {"n": 0.0, "ms": 0.0})
            n_ = on_fam.get(fam, {"n": 0.0, "ms": 0.0})
            run.summary[f"census/{fam}/n_off"] = o["n"]
            run.summary[f"census/{fam}/n_on"] = n_["n"]
            run.summary[f"census/{fam}/ms_off"] = o["ms"]
            run.summary[f"census/{fam}/ms_on"] = n_["ms"]
            run.summary[f"census/{fam}/ms_delta"] = n_["ms"] - o["ms"]
        # The load-bearing P2b claim: P2 alone pushed qk_norm_rope to 119
        # dispatches; with P2b it must stay at the plain-path count.
        run.summary["census/p2b_copies_eliminated"] = (
            off_fam.get("qk_norm_rope", {}).get("n")
            == on_fam.get("qk_norm_rope", {}).get("n"))
        run.summary["census/qk_norm_rope_n_p2_only_prior_art"] = 119.0

    for tag, path in (("off", args.gate_off), ("on", args.gate_on)):
        if not path:
            continue
        with open(path) as fh:
            receipt = json.load(fh)
        g = receipt["metrics"]
        for k in ("passed_correctness", "max_abs_diff", "checked_steps",
                  "golden_hash", "weights_hash", "harness_hash",
                  "decode_seconds_per_token", "prefill_seconds_per_token",
                  "decode_speedup", "prefill_speedup",
                  "first_failing_step", "error"):
            if k in g:
                run.summary[f"gate/{tag}/{k}"] = g[k]
        run.summary[f"gate/{tag}/passed"] = receipt["passed"]
        run.summary[f"gate/{tag}/golden_drift_override"] = "unset"

    run.summary["verdict"] = args.verdict
    print(run.url)
    run.finish()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
