#!/usr/bin/env python3
"""R119-B rev2: log the startup-memory-profile x gate 2x2 to W&B.

The rev1 ranked cells were measured on a 48 GiB host, which
Sources/MLXFastModel/RuntimeStartupMemoryPolicy.swift forces onto the
low-memory startup profile (MLX_MAX_OPS_PER_BUFFER=64, MLX_MAX_MB_PER_BUFFER=128,
MLX_BFS_MAX_WIDTH unset). The ranked M5 takes the full branch (200/200/50).
Rev2 repeats the same paired wall A/B with DARKBLOOM_STARTUP_MEMORY_PROFILE=full
and reports both cells side by side, so the profile x gate interaction is visible
instead of assumed.

Research-only; not on editablePaths.
  python3 research/edward_r119b_wandb_rev2.py --auto /tmp/r119b --full /tmp/r119b-full
"""
from __future__ import annotations

import argparse
import glob
import os
import re
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wandb  # noqa: E402

from edward_r119b_wandb import estimators, sh  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORDERS = ("abba", "baab")


def arm_means(paths, pool):
    """Mean of per-run median step wall, in microseconds, per arm."""
    _, samples, meta, med = estimators(paths, pool=pool)
    out = {}
    for arm in ("C", "F"):
        vals = [med[r] for r in sorted(samples) if meta[r][1] == arm]
        out[arm] = dict(n=len(vals), mean_us=1000.0 * float(np.mean(vals)) if vals else None)
    return out


def cell(out_dir):
    """All estimator rows for one profile cell, keyed by order then estimator."""
    paths = {o: os.path.join(out_dir, f"{o}_raw.csv") for o in ORDERS}
    present = {o: p for o, p in paths.items() if os.path.exists(p)}
    rows = {}
    for order, path in present.items():
        est, _, _, _ = estimators([path])
        rows[order] = dict(est=est, means=arm_means([path], pool=False))
    if len(present) == 2:
        est, _, _, _ = estimators(list(present.values()), pool=True)
        rows["pooled"] = dict(est=est, means=arm_means(list(present.values()), pool=True))
    return rows


def readback(patterns):
    """The three MLX command-buffer variables each worker actually saw."""
    seen: dict[str, set[str]] = {}
    notices = 0
    files = 0
    for pattern in patterns:
        for path in sorted(glob.glob(pattern)):
            files += 1
            text = open(path, errors="replace").read()
            notices += text.count("low-memory startup profile active")
            for m in re.finditer(r"ENVREADBACK (.+)", text):
                for field in m.group(1).split():
                    k, _, v = field.partition("=")
                    seen.setdefault(k, set()).add(v)
    return {k: sorted(v) for k, v in seen.items()}, notices, files


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--auto", default="/tmp/r119b")
    ap.add_argument("--full", default="/tmp/r119b-full")
    ap.add_argument("--envguard", default="/tmp/r119b-envguard")
    ap.add_argument("--name", default="r119b-gridappend-startup-profile-2x2")
    args = ap.parse_args()

    cells = {"auto": cell(args.auto), "full": cell(args.full)}
    guards = {
        # The rev1 auto cells predate the readback probe, so their per-run proof is
        # the low-memory notice; the readback values come from the same binary on
        # the same host in the envguard smoke pair.
        "auto": readback([os.path.join(args.auto, "*.err"),
                          os.path.join(args.envguard, "auto.werr")]),
        "full": readback([os.path.join(args.full, "*.err"),
                          os.path.join(args.envguard, "full.werr")]),
    }

    run = wandb.init(
        entity="wandb-applied-ai-team",
        project="mlxfast-maple",
        name=args.name,
        job_type="decode-kernel-fusion",
        tags=["r119-b", "grid-append", "startup-memory-profile", "command-buffer",
              "qmv", "maple-edward"],
        config={
            "assignment_id": "maple-r119-b-shared-routed-qmv-gridappend",
            "revision_id": "r119-b-rev2",
            "pr": 712,
            "branch": "maple-edward/r119-b-shared-routed-qmv-gridappend",
            "base_sha": "f8cb5c5be3a0480799088a8f7efd5808553dc20a",
            "commit": sh(["git", "rev-parse", "HEAD"]),
            "host": "Apple M4 Pro, 20 GPU cores, 48 GiB",
            "gpu_generation": 16,
            "env_switch": "DARKBLOOM_SHARED_ROUTED_QMV_FUSED",
            "profile_switch": "DARKBLOOM_STARTUP_MEMORY_PROFILE",
            "rank_axis": "end-to-end SPLIT=0 per-step decode wall",
            "design": "2x2 startup memory profile (auto/full) x gate (0/1), ABBA and BAAB reported separately",
        },
    )

    summary: dict = {}
    for profile, rows in cells.items():
        vals, notices, files = guards[profile]
        for k, v in vals.items():
            summary[f"guard/{profile}/{k}"] = ",".join(v)
        summary[f"guard/{profile}/low_memory_notices"] = notices
        summary[f"guard/{profile}/stderr_files_scanned"] = files
        for order, row in rows.items():
            base = row["means"]["C"]
            cand = row["means"]["F"]
            summary[f"wall/{profile}/{order}/n_per_arm"] = base["n"]
            summary[f"wall/{profile}/{order}/baseline_us_per_step"] = base["mean_us"]
            summary[f"wall/{profile}/{order}/candidate_us_per_step"] = cand["mean_us"]
            for key, e in row["est"].items():
                if key.startswith("raw_"):
                    summary[f"wall/{profile}/{order}/{key}/samples"] = e["samples"]
                    summary[f"wall/{profile}/{order}/{key}/median_ms"] = e["median_ms"]
                    summary[f"wall/{profile}/{order}/{key}/modes"] = e["modes"]
                    summary[f"wall/{profile}/{order}/{key}/bimodality"] = e["bimodality"]
                    continue
                summary[f"wall/{profile}/{order}/{key}/delta_us"] = e["delta_us"]
                summary[f"wall/{profile}/{order}/{key}/ci_lo_us"] = e["lo_us"]
                summary[f"wall/{profile}/{order}/{key}/ci_hi_us"] = e["hi_us"]
                summary[f"wall/{profile}/{order}/{key}/p"] = e["p"]
                summary[f"wall/{profile}/{order}/{key}/n"] = e["n"]
                summary[f"wall/{profile}/{order}/{key}/excludes_zero"] = bool(
                    e["lo_us"] * e["hi_us"] > 0)

    # Profile x gate interaction: does switching the command-buffer structure
    # change the sign or size of the gate effect, and does it move the wall at all?
    tbl = wandb.Table(columns=["order", "estimator", "delta_auto_us", "delta_full_us",
                               "interaction_us"])
    for order in list(ORDERS) + ["pooled"]:
        for key in ("block", "pair", "welch"):
            a = cells["auto"].get(order, {}).get("est", {}).get(key)
            f = cells["full"].get(order, {}).get("est", {}).get(key)
            if not a or not f:
                continue
            inter = f["delta_us"] - a["delta_us"]
            summary[f"interaction/{order}/{key}/delta_auto_us"] = a["delta_us"]
            summary[f"interaction/{order}/{key}/delta_full_us"] = f["delta_us"]
            summary[f"interaction/{order}/{key}/delta_full_minus_auto_us"] = inter
            tbl.add_data(order, key, a["delta_us"], f["delta_us"], inter)
    run.log({"profile_gate_interaction": tbl})

    for order in list(ORDERS) + ["pooled"]:
        a = cells["auto"].get(order, {}).get("means", {}).get("C", {}).get("mean_us")
        f = cells["full"].get(order, {}).get("means", {}).get("C", {}).get("mean_us")
        if a and f:
            summary[f"profile_shift/{order}/baseline_full_minus_auto_us"] = f - a
            summary[f"profile_shift/{order}/baseline_rel_pct"] = 100.0 * (f - a) / a

    run.summary.update(summary)
    for k in sorted(summary):
        print(f"{k}\t{summary[k]}")
    print(f"\nW&B run: {run.url}\nrun id: {run.id}")
    run.finish()


if __name__ == "__main__":
    main()
