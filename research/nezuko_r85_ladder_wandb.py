#!/usr/bin/env python3
"""Publish the R85-D injected-dispatch cost ladder to W&B.

    python3 research/nezuko_r85_ladder_wandb.py DIR [DIR ...]

Reads the same `bNN_sNNN_<arm>.steps` dumps as `nezuko_r85_ladder_fit.py`,
reuses its estimators, and logs the per-arm ladder table plus the fitted
slopes, intercepts and decision-table verdict.
"""
import math
import os
import platform
import re
import statistics
import subprocess
import sys
from pathlib import Path

import wandb

sys.path.insert(0, str(Path(__file__).resolve().parent))
from nezuko_r85_ladder_fit import LAYERS, load, ols, t95  # noqa: E402

# Advisor-supplied conversion for PR #458.
SCORE_PCT_PER_US_STEP = 0.015280


def fit(rows, mode):
    sub = [r for r in rows if r[2] == mode]
    ks = sorted({r[3] for r in sub})
    cell = {k: [r[4] for r in sub if r[3] == k] for k in ks}

    blocks = {}
    for b, _s, _md, k, v in sub:
        blocks.setdefault(b, []).append((k, v))
    xs, ys = [], []
    for _b, pts in blocks.items():
        bm = statistics.mean(v for _, v in pts)
        bx = statistics.mean(LAYERS * k for k, _ in pts)
        for k, v in pts:
            xs.append(LAYERS * k - bx)
            ys.append(v - bm)
    _a, slope, _sea, se_b, df, _r = ols(xs, ys)
    half = t95(df) * se_b

    xs2 = [LAYERS * r[3] for r in sub]
    ys2 = [r[4] for r in sub]
    icpt, raw_slope, se_a2, se_b2, df2, _r2 = ols(xs2, ys2)

    top = ks[len(ks) // 2:]
    dn = LAYERS * (top[-1] - top[0])
    top_secant = (statistics.median(cell[top[-1]])
                  - statistics.median(cell[top[0]])) / dn

    # K=0 runs a different code path (empty injected chain) and can carry a
    # one-time regime step that is not proportional to dispatch count.
    nz = [r for r in sub if r[3] > 0]
    icpt_nz, slope_nz, se_a3, se_b3, df3, _r3 = ols(
        [LAYERS * r[3] for r in nz], [r[4] for r in nz])

    return {
        "ks": ks, "cell": cell, "slope": slope, "ci_half": half, "df": df,
        "raw_slope": raw_slope, "raw_slope_ci": t95(df2) * se_b2,
        "intercept": icpt, "intercept_ci": t95(df2) * se_a2,
        "top_secant": top_secant, "n_runs": len(sub),
        "slope_nz": slope_nz, "slope_nz_ci": t95(df3) * se_b3,
        "step_nz": icpt_nz - statistics.median(cell[0]),
    }


CENSUS_RE = re.compile(
    r"wall=([\d.]+) ms gpu_busy_sum=([\d.]+) ms gpu_busy_union=([\d.]+) ms "
    r"gap=([\d.]+) ms .*cbs=([\d.]+) dispatches=([\d.]+)")


def census_rows(d):
    """Parse `<arm>.log` profile dumps written by research/nezuko_r85_census.sh."""
    out = []
    for p in sorted(Path(d).glob("[wt]*.log")):
        m = CENSUS_RE.search(p.read_text())
        if not m:
            continue
        arm = p.stem
        wall, bsum, bunion, gap, cbs, disp = (float(x) for x in m.groups())
        out.append({"arm": arm, "mode": "wide" if arm[0] == "w" else "tiny",
                    "k": int(arm[1:]), "wall_ms": wall, "busy_sum_ms": bsum,
                    "busy_union_ms": bunion, "overlap_ms": bsum - bunion,
                    "gap_ms": gap, "cbs": cbs, "dispatches": disp})
    return sorted(out, key=lambda r: (r["mode"] == "tiny", r["k"]))


def verdict(slope):
    if slope >= 2.0:
        return "H_strongly_supported", 2
    if slope >= 0.5:
        return "partial", 1
    return "H_refuted_close_family", 0


def main():
    dirs = sys.argv[1:]
    if not dirs:
        raise SystemExit(__doc__)
    rows = load(dirs)
    if not rows:
        raise SystemExit("no ladder runs found")

    wide, tiny = fit(rows, "w"), fit(rows, "t")
    headline = wide["slope"]
    label, code = verdict(headline)

    os.environ.setdefault("WANDB_DIR", "/tmp/nezuko-r85-wandb")
    os.makedirs(os.environ["WANDB_DIR"], exist_ok=True)
    chip = subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"],
                          capture_output=True, text=True).stdout.strip()

    run = wandb.init(
        project="mlxfast-maple",
        entity="wandb-applied-ai-team",
        name="nezuko-pr458-r85d-dispatch-cost-ladder",
        job_type="microbenchmark",
        tags=["pr458", "maple-nezuko", "r85-d", "dispatch-cost", "ladder"],
        config={
            "assignment_id": "maple-r85-d-dispatch-cost-ladder",
            "revision_id": "r85-d-rev1",
            "pr": 458,
            "base_sha": "cc5688d0dfd6347bde0efd624cd6e10fdd4cfd26",
            "host_chip": chip,
            "host_os": platform.mac_ver()[0],
            "apple_gpu_generation": 16,
            "nax_kernels_reachable": False,
            "layers": LAYERS,
            "ladder_k": wide["ks"],
            "steps_per_run": 400,
            "warmup_steps_dropped": 16,
            "blocks_palindromic": True,
            "unit_of_replication": "run_median_us_per_step",
            "wide_bytes_per_dispatch": 4096,
            "tiny_bytes_per_dispatch": 4,
            "predicted_slope_wide_us": 1.0,
            "predicted_slope_wide_ci80": [0.4, 2.0],
            "predicted_slope_tiny_us": 0.6,
            "predicted_slope_tiny_ci80": [0.15, 1.3],
            "score_pct_per_us_step": SCORE_PCT_PER_US_STEP,
        },
    )

    tbl = wandb.Table(columns=["mode", "K", "n_extra_dispatches", "n_runs",
                               "median_us_per_step", "sd_us", "delta_vs_k0_us",
                               "us_per_dispatch"])
    for mode, f in (("wide", wide), ("tiny", tiny)):
        base = statistics.median(f["cell"][0])
        for k in f["ks"]:
            vals = f["cell"][k]
            m = statistics.median(vals)
            n_extra = LAYERS * k
            tbl.add_data(mode, k, n_extra, len(vals), m,
                         statistics.stdev(vals) if len(vals) > 1 else 0.0,
                         m - base, (m - base) / n_extra if n_extra else 0.0)
    run.log({"ladder_table": tbl})

    census_dir = os.environ.get("R85_CENSUS_DIR")
    crows = census_rows(census_dir) if census_dir else []
    if crows:
        cols = ["arm", "mode", "k", "dispatches", "cbs", "wall_ms",
                "busy_sum_ms", "busy_union_ms", "overlap_ms", "gap_ms"]
        ctbl = wandb.Table(columns=cols)
        for r in crows:
            ctbl.add_data(*(r[c] for c in cols))
        run.log({"census_table": ctbl})

    se_w, se_t = wide["ci_half"] / 1.96, tiny["ci_half"] / 1.96
    diff = wide["slope"] - tiny["slope"]
    scalars = {
        "slope_wide_k_gt0_us": wide["slope_nz"],
        "slope_wide_k_gt0_ci95_half": wide["slope_nz_ci"],
        "slope_tiny_k_gt0_us": tiny["slope_nz"],
        "slope_tiny_k_gt0_ci95_half": tiny["slope_nz_ci"],
        "regime_step_wide_us_per_step": wide["step_nz"],
        "regime_step_tiny_us_per_step": tiny["step_nz"],
        "work_independent_us_lo": min(tiny["slope_nz"], tiny["top_secant"]),
        "work_independent_us_hi": max(tiny["slope"], tiny["top_secant"]),
        "slope_wide_us_per_dispatch": wide["slope"],
        "slope_wide_ci95_half": wide["ci_half"],
        "slope_tiny_us_per_dispatch": tiny["slope"],
        "slope_tiny_ci95_half": tiny["ci_half"],
        "slope_wide_minus_tiny_us": diff,
        "slope_wide_minus_tiny_ci95_half": 1.96 * math.hypot(se_w, se_t),
        "slope_ratio_wide_over_tiny": wide["slope"] / tiny["slope"],
        "top_secant_wide_us": wide["top_secant"],
        "top_secant_tiny_us": tiny["top_secant"],
        "intercept_wide_us_per_step": wide["intercept"],
        "intercept_tiny_us_per_step": tiny["intercept"],
        "raw_slope_wide_us": wide["raw_slope"],
        "raw_slope_tiny_us": tiny["raw_slope"],
        "n_runs_wide": wide["n_runs"],
        "n_runs_tiny": tiny["n_runs"],
        "decision_row_code": code,
        "headline_slope_us_per_dispatch": headline,
        "score_pct_per_dispatch_removed": headline * SCORE_PCT_PER_US_STEP,
    }
    if crows:
        c = {r["arm"]: r for r in crows}
        for mode, pre in (("wide", "w"), ("tiny", "t")):
            lo, hi = c[f"{pre}0"], c[f"{pre}64"]
            dn = hi["dispatches"] - lo["dispatches"]
            scalars[f"census_union_marginal_{mode}_us"] = (
                1e3 * (hi["busy_union_ms"] - lo["busy_union_ms"]) / dn)
            scalars[f"census_max_overlap_{mode}_ms"] = max(
                r["overlap_ms"] for r in crows if r["mode"] == mode)
        # w0..w32 hold the command-buffer count fixed while dispatches grow.
        w0, w32 = c["w0"], c["w32"]
        scalars["census_constant_cb_slope_wide_us"] = (
            1e3 * (w32["wall_ms"] - w0["wall_ms"])
            / (w32["dispatches"] - w0["dispatches"]))
        scalars["census_constant_cb_count"] = w0["cbs"]

    run.log(scalars)
    run.summary.update(scalars)
    run.summary["decision_row"] = label

    art = wandb.Artifact("pr458-r85d-dispatch-cost-ladder", type="benchmark")
    for d in dirs:
        for p in sorted(Path(d).glob("*.steps")):
            art.add_file(str(p), name=f"{Path(d).name}/{p.name}")
    if crows:
        for p in sorted(Path(census_dir).glob("[wt]*.log")):
            art.add_file(str(p), name=f"census/{p.name}")
    run.log_artifact(art)
    print(f"decision_row={label} headline={headline:.4f} us/dispatch")
    print(f"wandb run: {run.url}")
    run.finish()


if __name__ == "__main__":
    main()
