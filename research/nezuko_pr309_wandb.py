#!/usr/bin/env python3
"""Publish the PR #309 persistent grid-stride QKV campaign to W&B.

    python3 research/nezuko_pr309_wandb.py ABBA_DIR STAGE0_DIR [--warmup 8] [--trim 0.05]

Re-uses `research/nezuko_pr309_stats.py` as a library so the numbers published
to W&B are byte-identical to the ones printed in the report, then attaches the
raw per-step traces, the Stage 0 geometry evidence and both negative controls
as a single artifact.
"""
import argparse
import importlib.util
import math
import os
import platform
import re
import statistics
import subprocess
import sys
from pathlib import Path

import wandb

ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location(
    "pr309_stats", ROOT / "research" / "nezuko_pr309_stats.py"
)
S = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(S)

# us/step -> percent of decode score, calibrated in PR #298 on this host.
PCT_PER_US = 0.015280


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("abba_dir")
    ap.add_argument("stage0_dir")
    ap.add_argument("--warmup", type=int, default=8)
    ap.add_argument("--trim", type=float, default=0.05)
    ap.add_argument("--decision", default="UNSET")
    args = ap.parse_args()

    runs = [r for r in S.load(args.abba_dir, args.warmup, args.trim) if r[1] > 0]
    if not runs:
        print("no usable runs", file=sys.stderr)
        return 1
    blocks = sorted({r[1] for r in runs})
    effect, se_diff, odf, rsd = S.ols(runs, blocks)
    _, deltas = S.block_paired(runs, blocks)

    chip = subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"],
                          capture_output=True, text=True).stdout.strip()
    gpu_cores = subprocess.run(
        ["bash", "-c",
         "system_profiler SPDisplaysDataType 2>/dev/null | "
         "awk -F': ' '/Total Number of Cores/{print $2; exit}'"],
        capture_output=True, text=True).stdout.strip()

    os.environ.setdefault("WANDB_DIR", "/tmp/nezuko-pr309-wandb")
    os.makedirs(os.environ["WANDB_DIR"], exist_ok=True)

    run = wandb.init(
        project="mlxfast-maple",
        entity="wandb-applied-ai-team",
        name="nezuko-pr309-persistent-gridstride-qkv",
        job_type="decode-abba",
        tags=["pr309", "maple-nezuko", "persistent-gridstride-qkv", "stage2"],
        config={
            "assignment_id": "maple-2026-08-07q-persistent-gridstride-qkv",
            "revision_id": "r1",
            "pr": 309,
            "base_sha": "63ab67c888e1892086b7b5b623de4dd0ebe68c90",
            "host_chip": chip,
            "host_gpu_cores": gpu_cores,
            "host_os": platform.mac_ver()[0],
            "memory_profile": "low",
            "blocks": len(blocks),
            "runs": len(runs),
            "steps_per_run_kept": runs[0][5],
            "warmup_steps_dropped": args.warmup,
            "upper_trim_frac": args.trim,
            "arms": S.ARMS,
            "simdgroups_per_tg": 16,
            "total_threadgroups_persistent": 128,
            "rows_h64": 10240,
            "rows_h48": 8192,
            "rows_per_sg_h64_persistent": 5,
            "rows_per_sg_h48_persistent": 4,
            "pct_per_us_per_step": PCT_PER_US,
        },
    )

    summary = {"residual_sd_us": rsd, "residual_df": odf}
    for arm in S.ARMS:
        ms = [r[3] for r in runs if r[2] == arm]
        if ms:
            summary[f"arm/{arm}/mean_us"] = statistics.mean(ms)
            summary[f"arm/{arm}/n"] = len(ms)
            summary[f"arm/{arm}/sd_us"] = (statistics.stdev(ms) if len(ms) > 1
                                           else float("nan"))
    for name, a, b, _ in S.CONTRASTS:
        m = effect(a) - effect(b)
        se, _df = se_diff(a, b)
        h = S.t95(odf) * se
        key = f"contrast/{name}"
        summary[f"{key}/fe_mean_us"] = m
        summary[f"{key}/fe_se_us"] = se
        summary[f"{key}/fe_t"] = m / se if se else float("inf")
        summary[f"{key}/fe_ci_lo_us"] = m - h
        summary[f"{key}/fe_ci_hi_us"] = m + h
        summary[f"{key}/fe_pct_of_decode"] = -m * PCT_PER_US
        d = deltas.get(name, [])
        if len(d) >= 2:
            bm = statistics.mean(d)
            bse = statistics.stdev(d) / math.sqrt(len(d))
            bh = S.t95(len(d) - 1) * bse
            summary[f"{key}/bp_mean_us"] = bm
            summary[f"{key}/bp_ci_lo_us"] = bm - bh
            summary[f"{key}/bp_ci_hi_us"] = bm + bh

    stage0 = Path(args.stage0_dir)
    diverge = {}
    for log in sorted(stage0.glob("*.log")):
        txt = log.read_text(errors="replace")
        m = re.search(r"teacher-forced greedy tokens: (\d+) divergences", txt)
        diverge[log.stem] = int(m.group(1)) if m else -1
    for tag, n in diverge.items():
        summary[f"stage0/divergences/{tag}"] = n
    summary["stage0/fault_control_diverged"] = diverge.get("neg_fault", -1) > 0
    summary["decision"] = args.decision

    run.log({k: v for k, v in summary.items() if isinstance(v, (int, float, bool))})
    run.summary.update(summary)

    art = wandb.Artifact("pr309-persistent-gridstride-qkv", type="benchmark")
    for p in sorted(Path(args.abba_dir).glob("*.steps")):
        art.add_file(str(p), name=f"abba/{p.name}")
    for p in sorted(stage0.glob("*.log")):
        art.add_file(str(p), name=f"stage0/{p.name}")
    run.log_artifact(art)

    print(f"WANDB_RUN_ID={run.id}")
    print(f"WANDB_RUN_URL={run.url}")
    run.finish()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
