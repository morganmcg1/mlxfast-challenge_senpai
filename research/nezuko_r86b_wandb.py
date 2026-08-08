#!/usr/bin/env python3
"""Publish the R86-B in-situ boundary-price ladder to W&B.

    python3 research/nezuko_r86b_wandb.py DIR [DIR ...]

Reads the same `bNN_sNNN_<arm>.steps` dumps as `nezuko_r86b_fit.py` and reuses
its estimators, so the published numbers cannot drift from the fit report.
"""
import os
import platform
import statistics
import subprocess
import sys
from pathlib import Path

import wandb

sys.path.insert(0, str(Path(__file__).resolve().parent))
from nezuko_r86b_fit import (  # noqa: E402
    LAYERS, PCT_PER_US, load_ladder, load_size, ols, t95,
)

PROJECT = "mlxfast-maple"
ENTITY = "wandb-applied-ai-team"


def fit_mode(rows, mode):
    """Within-block-centred slope (us per inserted boundary) plus raw fit."""
    sub = [r for r in rows if r[2] == mode]
    if not sub:
        return None
    ins = sorted({r[3] for r in sub})
    cell = {a: [r[4] for r in sub if r[3] == a] for a in ins}

    blocks = {}
    for b, _s, _m, a, v in sub:
        blocks.setdefault(b, []).append((a, v))
    xs, ys = [], []
    for pts in blocks.values():
        bm = statistics.mean(v for _, v in pts)
        bx = statistics.mean(LAYERS * a for a, _ in pts)
        for a, v in pts:
            xs.append(LAYERS * a - bx)
            ys.append(v - bm)
    slope = half = float("nan")
    if len(xs) > 2 and len({x for x in xs}) > 1:
        _a, slope, _sea, se_b, df = ols(xs, ys)
        half = t95(df) * se_b

    raw = [(LAYERS * r[3], r[4]) for r in sub]
    icpt, raw_slope = float("nan"), float("nan")
    if len({x for x, _ in raw}) > 1:
        icpt, raw_slope, _sa, _sb, _df = ols([x for x, _ in raw],
                                             [y for _, y in raw])
    return {
        "mode": mode, "inserts": ins, "cell": cell,
        "slope_us_per_boundary": slope, "slope_ci95_half": half,
        "raw_slope_us_per_boundary": raw_slope, "raw_intercept_us": icpt,
        "n_runs": len(sub),
    }


def main():
    dirs = sys.argv[1:]
    if not dirs:
        raise SystemExit(__doc__)
    lad = load_ladder(dirs)
    siz = load_size(dirs)
    if not lad and not siz:
        raise SystemExit("no runs found")

    head = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True,
                          text=True).stdout.strip()
    cfg = {
        "experiment": "R86-B in-situ boundary price",
        "assignment_id": "maple-r86-b-insitu-boundary-price",
        "revision_id": "r86-b-rev1",
        "pr": 462,
        "base_sha": "7687c2e44e6975c181444ca8d3d151ee30480a72",
        "head_sha": head,
        "host_machine": platform.machine(),
        "host_platform": platform.platform(),
        "host_note": "Apple M4 Pro 48 GiB; ranked hardware is M5 Max (_nax "
                     "kernels unreachable here)",
        "decoder_layers": LAYERS,
        "score_pct_per_us_step": PCT_PER_US,
        "warmup_steps_dropped": 16,
        "n_ladder_runs": len(lad),
        "n_size_runs": len(siz),
    }
    run = wandb.init(entity=ENTITY, project=PROJECT, job_type="ladder",
                     name=f"r86b-insitu-boundary-{os.getpid()}",
                     tags=["r86-b", "pr462", "maple-nezuko", "m4-directional"],
                     config=cfg)

    tbl = wandb.Table(columns=["kind", "mode", "inserts", "k", "block", "slot",
                               "median_us_per_step"])
    for b, s, m, a, v in lad:
        tbl.add_data("ladder", m, a, LAYERS * a, b, s, v)
    for b, s, w, a, v in siz:
        tbl.add_data("size", f"z{w}", a, LAYERS * a, b, s, v)
    run.log({"runs": tbl})

    fits = {m: fit_mode(lad, m) for m in ("w", "t", "o")}
    summary = {}
    for m, f in fits.items():
        if not f:
            continue
        name = {"w": "wide", "t": "tiny", "o": "off"}[m]
        summary[f"{name}/slope_us_per_boundary"] = f["slope_us_per_boundary"]
        summary[f"{name}/slope_ci95_half"] = f["slope_ci95_half"]
        summary[f"{name}/raw_slope_us_per_boundary"] = f["raw_slope_us_per_boundary"]
        summary[f"{name}/raw_intercept_us"] = f["raw_intercept_us"]
        summary[f"{name}/n_runs"] = f["n_runs"]
        for a, vals in f["cell"].items():
            summary[f"{name}/median_us_k{LAYERS*a}"] = statistics.median(vals)
            summary[f"{name}/n_k{LAYERS*a}"] = len(vals)

    w, t = fits.get("w"), fits.get("t")
    if w and t:
        d = w["slope_us_per_boundary"] - t["slope_us_per_boundary"]
        half = (w["slope_ci95_half"] ** 2 + t["slope_ci95_half"] ** 2) ** 0.5
        summary["d_us_per_boundary"] = d
        summary["d_ci95_half"] = half
        summary["d_ci95_lo"] = d - half
        summary["d_ci95_hi"] = d + half
        summary["d_pct_score_per_boundary"] = d * PCT_PER_US
        summary["ratio_wide_over_tiny"] = (
            w["slope_us_per_boundary"] / t["slope_us_per_boundary"]
            if t["slope_us_per_boundary"] else float("nan"))
        for n in (40, 120, 240):
            summary[f"repriced_pct_score_{n}_boundaries"] = n * d * PCT_PER_US
        summary["verdict"] = ("GO" if d >= 1.00 else
                              "PARTIAL" if d >= 0.35 else "NO-GO")
    run.summary.update(summary)
    print(f"logged {len(lad)} ladder + {len(siz)} size runs -> {run.url}")
    run.finish()


if __name__ == "__main__":
    main()
