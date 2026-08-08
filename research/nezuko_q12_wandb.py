#!/usr/bin/env python3
"""Publish the PR #441 decode router block tournament campaign to W&B.

    python3 research/nezuko_q12_wandb.py --abba /tmp/nezq12/stage4/orderA \
        --abba /tmp/nezq12/stage4/orderB --bitwise LOG --smoke DIR \
        [--prefill DIR] [--decision KILL] [--trim 0.05]

Imports `research/nezuko_q12_stats.py` so the published numbers are produced by
exactly the same estimator as the printed report, then attaches every raw
per-step trace, the bit-exactness transcript, and the in-situ reachability
stderr as one artifact.
"""
import argparse
import math
import os
import platform
import re
import statistics
import subprocess
import sys
from pathlib import Path

import wandb

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nezuko_q12_stats as Q  # noqa: E402

S = Q.S
ARMS = Q.S.ARMS


def load_all(outdirs, warmup, trim):
    runs = []
    for d, outdir in enumerate(outdirs):
        got = [r for r in S.load(outdir, warmup, trim) if r[1] > 0]
        runs += [(r[0], r[1] + 100 * d, *r[2:]) for r in got]
    runs.sort()
    return runs


def parse_bitwise(path):
    """-> flat metrics from the standalone Metal bit-exactness transcript."""
    out = {}
    if not path or not Path(path).exists():
        return out
    txt = Path(path).read_text(errors="replace")
    out["stage2/drift_guards_ok"] = len(
        re.findall(r"^drift guard OK: ", txt, re.M))
    prec = "unknown"
    for line in txt.splitlines():
        m = re.match(r"=== logits precision: (\S+) ===", line)
        if m:
            prec = m.group(1)
            continue
        m = re.match(r"\s+(\w+) rows=(\d+) arm=(\S+) mismatch_words=(\d+) "
                     r"mismatch_rows=(\d+) max_abs_diff=(\S+)", line)
        if m:
            cls, rows, arm, mw, mr, mad = m.groups()
            k = f"stage2/{prec}/{cls}/{arm}"
            out[f"{k}/rows"] = int(rows)
            out[f"{k}/mismatch_words"] = int(mw)
            out[f"{k}/mismatch_rows"] = int(mr)
            out[f"{k}/max_abs_diff"] = float(mad)
            continue
        m = re.match(r"\s+(\w+) (tourn_fault_\w+) mismatch_words=(\d+)", line)
        if m:
            cls, fault, mw = m.groups()
            out[f"stage2/{prec}/{cls}/{fault}/mismatch_words"] = int(mw)
    for key, pat in (
        ("stage2/on_control_mismatch_words",
         r"on-control .*mismatch_words:\s*(\d+)"),
        ("stage2/fault_drop8_mismatch_words",
         r"fault tourn_fault_drop8 mismatch_words:\s*(\d+)"),
        ("stage2/fault_flatdir_mismatch_words",
         r"fault tourn_fault_flatdir mismatch_words:\s*(\d+)"),
        ("stage2/candidate_mismatch_words",
         r"candidate total mismatch_words:\s*(\d+)"),
        ("stage2/candidate_mismatch_rows",
         r"candidate total mismatch_words:\s*\d+, mismatch_rows:\s*(\d+)"),
    ):
        m = re.search(pat, txt)
        if m:
            out[key] = int(m.group(1))
    m = re.search(r"^RESULT: (\S+)", txt, re.M)
    out["stage2/result"] = m.group(1) if m else "UNPARSED"
    out["stage2/valid"] = (
        out.get("stage2/candidate_mismatch_words", -1) == 0
        and out.get("stage2/on_control_mismatch_words", -1) == 0
        and out.get("stage2/fault_drop8_mismatch_words", 0) > 0
        and out.get("stage2/fault_flatdir_mismatch_words", 0) > 0)
    return out


def parse_smoke(dirpath):
    """-> per-arm in-situ trace reachability and divergence count."""
    out = {}
    if not dirpath or not Path(dirpath).exists():
        return out
    for arm in ARMS:
        log = Path(dirpath) / f"{arm}.log"
        err = Path(dirpath) / f"{arm}.err"
        if log.exists():
            m = re.search(r"greedy tokens: (\d+) divergences",
                          log.read_text(errors="replace"))
            out[f"stage3/{arm}/divergences"] = int(m.group(1)) if m else -1
        if err.exists():
            t = err.read_text(errors="replace")
            out[f"stage3/{arm}/tournament_trace_seen"] = bool(
                re.search(r"decode router top8 tournament arm=", t))
            out[f"stage3/{arm}/incumbent_trace_seen"] = bool(
                re.search(r"decode router top8 \(cast sink \+ norm sink\)", t))
    # The arm control is only interpretable if the trace fires exactly on the two
    # tournament arms and never on the reference arm.
    out["stage3/reachability_valid"] = (
        out.get("stage3/off/tournament_trace_seen") is False
        and out.get("stage3/on/tournament_trace_seen") is True
        and out.get("stage3/inert/tournament_trace_seen") is True)
    out["stage3/all_arms_clean"] = all(
        out.get(f"stage3/{a}/divergences", -1) == 0 for a in ARMS)
    return out


def parse_prefill(dirpath):
    """-> per-arm prefill milliseconds, the rule-17 second axis."""
    out, per = {}, {}
    if not dirpath or not Path(dirpath).exists():
        return out
    for log in sorted(Path(dirpath).glob("*.log")):
        arm = log.stem.rsplit("_", 1)[-1]
        m = re.search(r"^prefill .*?median=([\d.]+) ms",
                      log.read_text(errors="replace"), re.M)
        if m:
            per.setdefault(arm, []).append(float(m.group(1)))
    for arm, vals in per.items():
        out[f"prefill/{arm}/median_ms"] = statistics.mean(vals)
        out[f"prefill/{arm}/n"] = len(vals)
        out[f"prefill/{arm}/spread_ms"] = max(vals) - min(vals)
    if "off" in per:
        base = statistics.mean(per["off"])
        for arm, vals in per.items():
            out[f"prefill/{arm}/delta_vs_off_ms"] = statistics.mean(vals) - base
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--abba", action="append", default=[])
    ap.add_argument("--bitwise", default=None)
    ap.add_argument("--smoke", default=None)
    ap.add_argument("--prefill", default=None)
    ap.add_argument("--warmup", type=int, default=8)
    ap.add_argument("--trim", type=float, default=0.05)
    ap.add_argument("--decision", default="UNSET")
    args = ap.parse_args()

    runs = load_all(args.abba, args.warmup, args.trim)
    if not runs:
        print("no usable runs", file=sys.stderr)
        return 1
    blocks = sorted({r[1] for r in runs})
    effect, se_diff, odf, rsd = S.ols(runs, blocks)
    _, deltas = S.block_paired(runs, blocks)

    chip = subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"],
                          capture_output=True, text=True).stdout.strip()
    gpu_cores = subprocess.run(
        ["bash", "-c", "system_profiler SPDisplaysDataType 2>/dev/null | "
         "awk -F': ' '/Total Number of Cores/{print $2; exit}'"],
        capture_output=True, text=True).stdout.strip()

    os.environ.setdefault("WANDB_DIR", "/tmp/nezuko-q12-wandb")
    os.makedirs(os.environ["WANDB_DIR"], exist_ok=True)

    run = wandb.init(
        project="mlxfast-maple",
        entity="wandb-applied-ai-team",
        name="nezuko-q12-decode-router-block-tournament",
        job_type="decode-abba",
        tags=["pr441", "maple-nezuko", "decode-router-tournament", "barriers"],
        config={
            "assignment_id": "maple-2026-08-08a-decode-router-tournament",
            "revision_id": "r1",
            "pr": 441,
            "base_sha": "730e9c2be89a4ed8cf860e52f930f7ff222d4c95",
            "guard": "DARKBLOOM_DECODE_ROUTER_TOURNAMENT",
            "guard_default": "0 (off)",
            "host_chip": chip,
            "host_gpu_cores": gpu_cores,
            "host_os": platform.mac_ver()[0],
            "memory_profile": "low",
            "order_directions": len(args.abba),
            "blocks": len(blocks),
            "runs": len(runs),
            "steps_per_run_kept": runs[0][5],
            "warmup_steps_dropped": args.warmup,
            "upper_trim_frac": args.trim,
            "arms": ARMS,
            "dispatches_per_step": Q.DISPATCHES_PER_STEP,
            "pct_per_us_per_step_pr298": Q.DECODE_PCT_PER_US,
            # Barrier accounting is the whole mechanism under test: stage count
            # is held fixed at 36 and only the barrier count changes.
            "incumbent_stages": 36,
            "incumbent_cross_simd_stages": 6,
            "incumbent_threadgroup_barriers": 12,
            "tournament_stages": 15 + 21,
            "tournament_cross_simd_stages": 1,
            "tournament_threadgroup_barriers": 3,
            "tournament_phase1_blocks": 8,
            "tournament_phase1_width": 32,
            "tournament_phase2_candidates": 64,
            "kernel_body_us_of_470": "1.7-2.7 (4.70 census minus ~3.0 launch floor)",
        },
    )

    summary = {"residual_sd_us": rsd, "residual_df": odf, "decision": args.decision}
    ref_us = statistics.mean([r[3] for r in runs if r[2] == S.REF])
    pct_per_us = 100.0 / ref_us  # in-campaign anchor, same-session paired
    summary["ref_arm_mean_us"] = ref_us
    summary["pct_per_us_measured"] = pct_per_us
    for arm in ARMS:
        ms = [r[3] for r in runs if r[2] == arm]
        ws = [r[4] for r in runs if r[2] == arm]
        if ms:
            summary[f"arm/{arm}/mean_us"] = statistics.mean(ms)
            summary[f"arm/{arm}/n"] = len(ms)
            summary[f"arm/{arm}/sd_us"] = (statistics.stdev(ms) if len(ms) > 1
                                           else float("nan"))
            summary[f"arm/{arm}/within_run_sd_us"] = statistics.mean(ws)
    for name, a, b, _ in S.CONTRASTS:
        m = effect(a) - effect(b)
        se, _ = se_diff(a, b)
        h = S.t95(odf) * se
        key = f"contrast/{name}"
        summary[f"{key}/fe_mean_us"] = m
        summary[f"{key}/fe_se_us"] = se
        summary[f"{key}/fe_t"] = m / se if se else float("inf")
        summary[f"{key}/fe_ci_lo_us"] = m - h
        summary[f"{key}/fe_ci_hi_us"] = m + h
        summary[f"{key}/fe_us_per_call"] = m / Q.DISPATCHES_PER_STEP
        summary[f"{key}/fe_pct_of_decode"] = -m * pct_per_us
        d = deltas.get(name, [])
        if len(d) >= 2:
            bm = statistics.mean(d)
            bse = statistics.stdev(d) / math.sqrt(len(d))
            bh = S.t95(len(d) - 1) * bse
            summary[f"{key}/bp_mean_us"] = bm
            summary[f"{key}/bp_ci_lo_us"] = bm - bh
            summary[f"{key}/bp_ci_hi_us"] = bm + bh
    summary.update(parse_bitwise(args.bitwise))
    summary.update(parse_smoke(args.smoke))
    summary.update(parse_prefill(args.prefill))

    run.log({k: v for k, v in summary.items() if isinstance(v, (int, float, bool))})
    run.summary.update(summary)

    art = wandb.Artifact("pr441-decode-router-tournament", type="benchmark")
    for d, outdir in enumerate(args.abba):
        for p in sorted(Path(outdir).glob("*.steps")):
            art.add_file(str(p), name=f"abba/{Path(outdir).name}/{p.name}")
    if args.bitwise and Path(args.bitwise).exists():
        art.add_file(args.bitwise, name="stage2/bitwise.log")
    for sub, pat in ((args.smoke, "*"), (args.prefill, "*.log")):
        if sub and Path(sub).exists():
            for p in sorted(Path(sub).glob(pat)):
                if p.is_file():
                    art.add_file(str(p), name=f"{Path(sub).name}/{p.name}")
    run.log_artifact(art)

    print(f"WANDB_RUN_ID={run.id}")
    print(f"WANDB_RUN_URL={run.url}")
    run.finish()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
