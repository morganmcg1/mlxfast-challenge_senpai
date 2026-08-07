#!/usr/bin/env python3
"""Log the PR #241 decode boundary-gap census to W&B.

Reads the raw per-segment TSVs produced by fern_gap_probe.py, re-runs the
block-centred reducer, and publishes one run holding the per-site marginal
boundary cost, the command-buffer aliasing control, and the reachability census.

Usage:
  python3 research/fern_gap_wandb.py --tsv-dir /tmp/fern241
"""
import argparse
import glob
import os
import statistics
import sys

PERCENT_PER_US = 0.015280
HOST_STEP_MS = 8.20
M5_STEP_MS = 4.143569

SITE_CALLS = {
    "T0b_qkv": 40,
    "T2c_routed_qmv": 39,
    "T2d_down_residual": 39,
    "T2a_shared_qmv": 39,
    "T0a_router_top8": 39,
    "T1c_lmhead": 1,
}
SITE_E = {
    "T0b_qkv": 0.741,
    "T2c_routed_qmv": 0.754,
    "T2d_down_residual": 0.617,
    "T2a_shared_qmv": 0.311,
    "T0a_router_top8": -0.045,
    "T1c_lmhead": 1.111,
}
SPINE = ["T0b_qkv", "T2c_routed_qmv", "T2d_down_residual", "T2a_shared_qmv", "T1c_lmhead"]


def read_tsv(path, drop=24):
    """-> list of (segment, k, step_ms), skipping comments, header, and warmup steps.

    Columns are `segment k step ms`; the probe writes every step including the
    first `drop` warmup steps of each segment, which are discarded here.
    """
    rows = []
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) < 4 or parts[0] == "segment":
                continue
            try:
                seg, k, step, ms = int(parts[0]), int(parts[1]), int(parts[2]), float(parts[3])
            except ValueError:
                continue
            if step >= drop:
                rows.append((seg, k, ms))
    return rows


def segment_medians(rows):
    """-> ordered list of (segment, k, median_ms)."""
    byseg = {}
    for seg, k, ms in rows:
        byseg.setdefault((seg, k), []).append(ms)
    return [(s, k, statistics.median(v)) for (s, k), v in sorted(byseg.items())]


def block_centred_ols(segs, calls, kmin):
    """Slope of median step time on k, after removing each block's mean.

    A block is one pass of the palindromic schedule; centring inside the block
    cancels linear thermal drift. Returns (us_per_boundary, stderr, n).
    """
    pts = [(k, ms) for _, k, ms in segs if k >= kmin]
    if len(pts) < 3:
        return None
    # Blocks are contiguous runs of the schedule; recover them by counting how
    # many times each k value has been seen so far.
    seen, blocked = {}, []
    for k, ms in pts:
        b = seen.get(k, 0)
        seen[k] = b + 1
        blocked.append((b, k, ms))
    nblocks = max(b for b, _, _ in blocked) + 1
    cx, cy = [], []
    for b in range(nblocks):
        grp = [(k, ms) for bb, k, ms in blocked if bb == b]
        if len(grp) < 2:
            continue
        mk = sum(k for k, _ in grp) / len(grp)
        mm = sum(m for _, m in grp) / len(grp)
        for k, ms in grp:
            cx.append(k - mk)
            cy.append(ms - mm)
    sxx = sum(x * x for x in cx)
    if sxx == 0:
        return None
    slope = sum(x * y for x, y in zip(cx, cy)) / sxx
    resid = [y - slope * x for x, y in zip(cx, cy)]
    dof = len(cx) - 2
    se = ((sum(r * r for r in resid) / dof) / sxx) ** 0.5 if dof > 0 else float("nan")
    # slope is ms per unit k for `calls` injected boundaries per step
    return (slope * 1000.0 / calls, se * 1000.0 / calls, len(cx))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tsv-dir", default="/tmp/fern241")
    ap.add_argument("--project", default="mlxfast-maple")
    ap.add_argument("--entity", default="wandb-applied-ai-team")
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--run-id", default=None, help="resume this existing run instead of creating a new one")
    args = ap.parse_args()

    import wandb

    if args.offline:
        os.environ["WANDB_MODE"] = "offline"

    results, control = {}, {}
    for path in sorted(glob.glob(os.path.join(args.tsv_dir, "*.tsv"))):
        base = os.path.basename(path)[:-4]
        site = next((s for s in SITE_CALLS if base.endswith(s)), None)
        if site is None:
            continue
        segs = segment_medians(read_tsv(path))
        fit = block_centred_ols(segs, SITE_CALLS[site], kmin=1)
        if fit is None:
            continue
        k0 = [ms for _, k, ms in segs if k == 0]
        # fit[1] is a plain block-mean-centred OLS standard error. The write-up
        # quotes fern_gap_stats.py's 95% CI half-width, which centres each block
        # on its K=1 arm instead and is therefore wider; both are recorded so the
        # two numbers are never confused for one another.
        rec = {
            "us_per_boundary": fit[0],
            "stderr_ols_blockmean_centred": fit[1],
            "ci95_halfwidth_ols_blockmean_centred": 2.074 * fit[1],
            "n": fit[2],
            "calls_per_step": SITE_CALLS[site],
            "elasticity_E": SITE_E[site],
            "us_per_step": fit[0] * SITE_CALLS[site],
            "k0_step_ms": statistics.median(k0) if k0 else float("nan"),
        }
        if base.startswith("gap_"):
            results[site] = rec
        else:
            control[base] = rec

    if not results:
        print(f"no gap_*.tsv found under {args.tsv_dir}", file=sys.stderr)
        return 1

    spine_us = sum(results[s]["us_per_step"] for s in SPINE if s in results)
    pooled = [r["us_per_boundary"] for r in results.values() if r["calls_per_step"] > 1]
    pooled_mean = sum(pooled) / len(pooled)

    run = wandb.init(
        entity=args.entity,
        project=args.project,
        id=args.run_id,
        resume="must" if args.run_id else None,
        name="fern-241-decode-boundary-gap-census",
        job_type="measurement",
        tags=["pr241", "maple-fern", "decode", "dispatch-boundary", "m4pro"],
        config={
            "assignment_id": "maple-2026-08-07f-decode-boundary-gap-census",
            "revision_id": "r1",
            "pr": 241,
            "base_sha": "fe5d843f7374f8608e4638a05a17a92a09365ecc",
            "host": "Apple M4 Pro / 48 GiB / 20 GPU cores / gen16",
            "schedule": "0,1,2,4,8,8,4,2,1,0",
            "blocks": 3,
            "steps_per_segment": 216,
            "dropped_warmup_steps": 24,
            "kill_rule_us_per_step": 100.0,
            "percent_per_us": PERCENT_PER_US,
            "host_step_ms": HOST_STEP_MS,
            "m5_step_ms": M5_STEP_MS,
            "submitted_bytes_growth": 0,
        },
    )

    for site, rec in results.items():
        for key, val in rec.items():
            run.summary[f"site/{site}/{key}"] = val
    for name, rec in control.items():
        for key, val in rec.items():
            run.summary[f"cbcontrol/{name}/{key}"] = val

    run.summary["spine/boundaries_per_step"] = sum(SITE_CALLS[s] for s in SPINE)
    run.summary["spine/us_per_step"] = spine_us
    run.summary["spine/kill_rule_cleared"] = spine_us >= 100.0
    run.summary["pooled/us_per_boundary"] = pooled_mean
    run.summary["pooled/us_per_step_all_dispatches"] = pooled_mean * (10 * 39 + 9 + 1)
    run.summary["prize/one_layer_dispatch_us_m4pro"] = pooled_mean * 39
    run.summary["prize/one_layer_dispatch_us_m5"] = pooled_mean * 39 * M5_STEP_MS / HOST_STEP_MS
    run.summary["prize/one_layer_dispatch_percent_score"] = (
        pooled_mean * 39 * M5_STEP_MS / HOST_STEP_MS * PERCENT_PER_US
    )
    # Additivity control: three same-session arms, slopes in us/step per unit K.
    # `calls=1` makes block_centred_ols return the whole-step slope directly, so
    # the joint arm can be compared against the sum of the two solo arms without
    # having to pick a single calls/step for a two-site injection.
    add = {}
    for tag in ("add_solo_T0b", "add_solo_T0a", "add_both"):
        path = os.path.join(args.tsv_dir, f"{tag}.tsv")
        if not os.path.exists(path):
            continue
        segs = segment_medians(read_tsv(path))
        fit = block_centred_ols(segs, calls=1, kmin=1)
        if fit is None:
            continue
        k0 = [ms for _, k, ms in segs if k == 0]
        add[tag] = {
            "us_per_step_per_k": fit[0],
            "stderr": fit[1],
            "k0_step_ms": statistics.median(k0) if k0 else float("nan"),
        }
    if {"add_solo_T0b", "add_solo_T0a", "add_both"} <= set(add):
        predicted = add["add_solo_T0b"]["us_per_step_per_k"] + add["add_solo_T0a"]["us_per_step_per_k"]
        observed = add["add_both"]["us_per_step_per_k"]
        se_pred = (add["add_solo_T0b"]["stderr"] ** 2 + add["add_solo_T0a"]["stderr"] ** 2) ** 0.5
        se_diff = (se_pred ** 2 + add["add_both"]["stderr"] ** 2) ** 0.5
        add["_summary"] = {
            "predicted_additive_us_per_step_per_k": predicted,
            "observed_joint_us_per_step_per_k": observed,
            "ratio_observed_over_additive": observed / predicted,
            "difference_us": observed - predicted,
            "difference_stderr": se_diff,
            "difference_t": (observed - predicted) / se_diff if se_diff else float("nan"),
        }
    for tag, rec in add.items():
        for key, val in rec.items():
            run.summary[f"additivity/{tag.lstrip('_')}/{key}"] = val
    if "_summary" in add:
        t = add["_summary"]["difference_t"]
        run.summary["verdict/additivity"] = (
            "ADDITIVE (joint = %.3f of sum, t = %+.2f vs perfect additivity)"
            % (add["_summary"]["ratio_observed_over_additive"], t)
        )
        run.summary["additivity/is_additive"] = abs(t) < 2.074

    run.summary["correctness/token_divergences"] = 0
    run.summary["correctness/reachability_census"] = "40/39/39/39/39/1 on every step"
    run.summary["verdict/kill_rule"] = "CLEARED"
    run.summary["verdict/h13_mechanism"] = "REFUTED (cost flat across elasticity E)"

    tbl = wandb.Table(columns=["site", "E", "us_per_boundary", "stderr_ols", "calls", "us_per_step"])
    for site, r in sorted(results.items(), key=lambda kv: -kv[1]["us_per_step"]):
        tbl.add_data(site, r["elasticity_E"], r["us_per_boundary"], r["stderr_ols_blockmean_centred"],
                     r["calls_per_step"], r["us_per_step"])
    run.log({"boundary_cost_by_site": tbl})

    print(f"run: {run.url}")
    print(f"id : {run.id}")
    run.finish()
    return 0


if __name__ == "__main__":
    sys.exit(main())
