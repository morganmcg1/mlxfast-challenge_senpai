#!/usr/bin/env python3
"""Log the PR #268 dispatch-tax attribution battery to W&B.

PR #241 shipped two reducers that disagreed by ~6% because they centred
contrasts differently.  This file does NOT reimplement the estimator: every
number comes from research/fern_tax_stats.py's fit(), so the W&B numbers and
the deliverable's numbers are the same numbers by construction.

  python3 research/fern_tax_wandb.py /tmp/fern268 --run-name tax-battery
"""
import argparse
import glob
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fern_tax_stats as S  # noqa: E402

PROJECT = "mlxfast-maple"
ENTITY = "wandb-applied-ai-team"

# (x, y) pairs worth a slope.  x=barrier vs x=dispatch decides whether the
# tax is a serialization cost or a launch cost; y=gpu_ms vs y=gap_ms decides
# whether it is GPU-paced (E2/E3/E4) or CPU-paced (E1).
GRID = [("dispatch", "ms"), ("barrier", "ms"), ("k", "ms"),
        ("dispatch", "gpu_ms"), ("dispatch", "gap_ms"),
        ("dispatch", "kernel_ms")]

# Arms that inject inside a decode layer at 8 KiB, i.e. the ones the verdict
# rests on.  The footprint (fat40_<bytes>) and pool (dist40_p<N>) sweeps vary
# a nuisance parameter on purpose and must not be pooled into the joint fit.
SITE_ARMS = ("chain40", "fat40_8k", "dist40_8k", "fan40",
             "fat40_8k_free", "dist40_8k_free")

TABLE_COLS = ["arm", "mode", "bytes", "pool", "anchor", "x", "y", "slope_us",
              "se_us", "ci95_half_us", "df", "n_points", "blocks",
              "divergences", "baseline_ms", "baseline_dispatch",
              "baseline_barrier", "baseline_commit", "baseline_encode",
              "baseline_gpu_ms", "baseline_kernel_ms", "baseline_span_ms",
              "baseline_gpu_busy_frac"]


def row(arm, r):
    m = r["meta"]
    return [arm, m.get("mode"), int(m.get("bytes", 0)), int(m.get("pool", 0)),
            int(m.get("anchor", 0)), r["x"], r["y"], r["slope_us"],
            r["se_us"], r["ci95_half_us"], r["df"], r["n_points"],
            r["blocks"], int(m.get("divergences", 0)), r["baseline_ms"]] + [
        r.get(k) for k in ("baseline_dispatch", "baseline_barrier",
                           "baseline_commit", "baseline_encode",
                           "baseline_gpu_ms", "baseline_kernel_ms",
                           "baseline_span_ms", "baseline_gpu_busy_frac")]


def pooled(paths, x_kind, y_kind="ms"):
    """One slope across several arms, fixed effect = (file, block)."""
    pts, base = [], []
    for fi, p in enumerate(paths):
        r = S.fit(p, x_kind, y_kind)
        if r is None:
            return None
        base.append(r["baseline_ms"])
        meta, rows_ = S.read_timing(p)
        ctr = S.read_counters(p + ".ctr.tsv")
        seg_k, per_seg = {}, {}
        for seg, k, ms in rows_:
            seg_k[seg] = k
            per_seg.setdefault(seg, []).append(ms)
        segs = sorted(per_seg)
        med = {s: statistics.median(per_seg[s]) for s in segs}
        blen = S.block_length(seg_k, segs)
        xv, yv = S.axes(meta, seg_k, med, ctr, x_kind, y_kind)
        for i, s in enumerate(segs):
            pts.append(((fi, i // blen), xv(s), yv(s)))
    nb = len({p[0] for p in pts})
    slope, se, df, n = S.fe_ols(pts, nb)
    half = S.t95(df) * se if se == se else float("nan")
    return {"slope_us": slope, "se_us": se, "ci95_half_us": half, "df": df,
            "n_points": n, "blocks": nb,
            "baseline_ms": statistics.mean(base)}


def joint_pooled(paths):
    """Price dispatch and barrier apart in one fit, FE = (file, block).

    Dispatch and barrier move together inside any single arm, so this is only
    identified because fan40 and the anchor-0 arms break the 1:1 ratio.
    """
    pts = []
    for fi, p in enumerate(paths):
        for b, d, x, y in S.joint_points(p):
            pts.append(((fi, b), d, x, y))
    nb = len({p[0] for p in pts})
    (bd, sd), (bb, sb), df, n = S.fe_ols2(pts, nb)
    t = S.t95(df)
    return {"dispatch_slope_us": bd, "dispatch_se_us": sd,
            "dispatch_ci95_half_us": t * sd,
            "barrier_slope_us": bb, "barrier_se_us": sb,
            "barrier_ci95_half_us": t * sb,
            "fusion_refund_us": bd + bb, "df": df, "n_points": n,
            "blocks": nb}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("outdir")
    ap.add_argument("--run-name", default="fern-dispatch-tax-battery")
    ap.add_argument("--offline", action="store_true")
    args = ap.parse_args()

    import wandb
    if args.offline:
        os.environ["WANDB_MODE"] = "offline"
    run = wandb.init(entity=ENTITY, project=PROJECT, name=args.run_name,
                     job_type="dispatch-tax-attribution",
                     config={"host": "M4 Pro 20c 48GiB", "pr": 268,
                             "assignment":
                             "maple-2026-08-07g-dispatch-tax-attribution",
                             "reducer": "within-block FE-OLS on segment "
                                        "medians (research/fern_tax_stats.py)",
                             "n_layers": S.N_LAYERS,
                             "percent_per_us_decode":
                             S.PERCENT_PER_US_DECODE})

    table = wandb.Table(columns=TABLE_COLS)
    summary, arms = {}, {}
    for path in sorted(glob.glob(os.path.join(args.outdir, "*.tsv"))):
        if path.endswith(".ctr.tsv"):
            continue
        arm = os.path.basename(path)[:-4]
        arms[arm] = path
        for x_kind, y_kind in GRID + ([("spin_us", "ms")]
                                      if "spin" in arm else []):
            r = S.fit(path, x_kind, y_kind)
            if r is None:
                continue
            table.add_data(*row(arm, r))
            tag = f"{arm}/{x_kind}" + ("" if y_kind == "ms" else f"/{y_kind}")
            summary[f"{tag}/slope_us"] = r["slope_us"]
            summary[f"{tag}/ci95_half_us"] = r["ci95_half_us"]
            if (x_kind, y_kind) == ("dispatch", "ms"):
                summary[f"{arm}/baseline_ms"] = r["baseline_ms"]
                summary[f"{arm}/baseline_dispatch"] = r.get("baseline_dispatch")
                summary[f"{arm}/baseline_barrier"] = r.get("baseline_barrier")
                summary[f"{arm}/baseline_gpu_busy_frac"] = r.get(
                    "baseline_gpu_busy_frac")

    # Headline: the in-chain family under both candidate regressors.  The
    # regressor that pools without scatter is the one that names the tax.
    family = [arms[a] for a in
              ("chain40", "fat40_8k", "dist40_8k", "fan40") if a in arms]
    if len(family) > 1:
        for x_kind in ("dispatch", "barrier"):
            r = pooled(family, x_kind)
            if r is None:
                continue
            summary[f"pooled_inchain/{x_kind}/slope_us"] = r["slope_us"]
            summary[f"pooled_inchain/{x_kind}/ci95_half_us"] = \
                r["ci95_half_us"]
            summary[f"pooled_inchain/{x_kind}/us_per_step_if_1_per_layer"] = \
                r["slope_us"] * S.N_LAYERS
            summary[f"pooled_inchain/{x_kind}/percent_score_if_1_per_layer"] \
                = r["slope_us"] * S.N_LAYERS * S.PERCENT_PER_US_DECODE

    # The decision number: what one fused dependent pair actually refunds.
    for tag, sel in (("joint_inchain", family),
                     ("joint_all_sites",
                      [arms[a] for a in SITE_ARMS if a in arms])):
        if len(sel) < 2:
            continue
        j = joint_pooled(sel)
        summary.update({f"{tag}/{k}": v for k, v in j.items()})
        summary[f"{tag}/n_arms"] = len(sel)

    run.log({"arms": table})
    run.summary.update(summary)
    print(f"logged {len(summary)} scalars, {len(arms)} arms -> {run.url}")
    run.finish()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
