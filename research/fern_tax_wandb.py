#!/usr/bin/env python3
"""Log the PR #268 dispatch-tax battery to W&B.

PR #241 shipped two reducers that disagreed by ~6% because they centred
contrasts differently.  This file does NOT reimplement the estimator: it
imports the one in research/fern_tax_stats.py, so the W&B numbers and the
deliverable's numbers are the same numbers by construction.

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


def reduce_arm(path, x_kind):
    meta, rows = S.read_timing(path)
    ctr = S.read_counters(path + ".ctr.tsv")
    spin_ns = float(meta.get("spin_ns", 0))
    seg_k, per_seg = {}, {}
    for seg, k, ms in rows:
        seg_k[seg] = k
        per_seg.setdefault(seg, []).append(ms)
    segs = sorted(per_seg)
    med = {s: statistics.median(per_seg[s]) for s in segs}
    blen = S.block_length(seg_k, segs)
    n_blocks = len(segs) // blen

    def xval(s):
        if x_kind == "k":
            return float(seg_k[s])
        if x_kind == "spin_us":
            return seg_k[s] * 40 * spin_ns / 1e3
        if s not in ctr:
            return None
        return ctr[s][x_kind]

    pts = []
    for i, s in enumerate(segs):
        v = xval(s)
        if v is None:
            return None
        pts.append((i // blen, v, med[s] * 1e3))
    slope, se, df, n = S.fe_ols(pts, n_blocks)
    half = S.t95(df) * se if se == se else float("nan")
    base = [s for s in segs if seg_k[s] == min(seg_k.values())]
    bc = [ctr[s] for s in base if s in ctr]
    out = {
        "mode": meta.get("mode"), "bytes": int(meta.get("bytes", 0)),
        "x": x_kind, "slope_us": slope, "se_us": se, "ci95_half_us": half,
        "df": df, "n_points": n, "blocks": n_blocks, "block_len": blen,
        "divergences": int(meta.get("divergences", 0)),
        "baseline_ms": statistics.mean(med[s] for s in base),
    }
    if bc:
        for key in ("dispatch", "barrier", "commit", "encode"):
            out["baseline_" + key] = statistics.mean(c[key] for c in bc)
        out["baseline_gpu_ms"] = statistics.mean(c["gpu_ns"] for c in bc) / 1e6
        out["baseline_kernel_ms"] = statistics.mean(
            c["kernel_ns"] for c in bc) / 1e6
        out["baseline_span_ms"] = statistics.mean(
            c["span_ns"] for c in bc) / 1e6
        out["baseline_gpu_busy_frac"] = (out["baseline_gpu_ms"]
                                         / out["baseline_ms"])
    return out


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
                             "n_layers": S.N_LAYERS})
    table = wandb.Table(columns=[
        "arm", "mode", "bytes", "x", "slope_us", "se_us", "ci95_half_us",
        "df", "blocks", "divergences", "baseline_ms", "baseline_dispatch",
        "baseline_barrier", "baseline_commit", "baseline_gpu_ms",
        "baseline_kernel_ms", "baseline_gpu_busy_frac"])
    summary = {}
    for path in sorted(glob.glob(os.path.join(args.outdir, "*.tsv"))):
        if path.endswith(".ctr.tsv"):
            continue
        arm = os.path.basename(path)[:-4]
        kinds = ("k", "dispatch", "barrier")
        if "spin" in arm:
            kinds = kinds + ("spin_us",)
        for x_kind in kinds:
            r = reduce_arm(path, x_kind)
            if r is None:
                continue
            summary[f"{arm}/{x_kind}/slope_us"] = r["slope_us"]
            summary[f"{arm}/{x_kind}/ci95_half_us"] = r["ci95_half_us"]
            if x_kind == "dispatch":
                table.add_data(
                    arm, r["mode"], r["bytes"], x_kind, r["slope_us"],
                    r["se_us"], r["ci95_half_us"], r["df"], r["blocks"],
                    r["divergences"], r["baseline_ms"],
                    r.get("baseline_dispatch"), r.get("baseline_barrier"),
                    r.get("baseline_commit"), r.get("baseline_gpu_ms"),
                    r.get("baseline_kernel_ms"),
                    r.get("baseline_gpu_busy_frac"))
                summary[f"{arm}/baseline_ms"] = r["baseline_ms"]
                summary[f"{arm}/baseline_gpu_busy_frac"] = r.get(
                    "baseline_gpu_busy_frac")
    run.log({"arms": table})
    run.summary.update(summary)
    print(f"logged {len(summary)} scalars -> {run.url}")
    run.finish()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
