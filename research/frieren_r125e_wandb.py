#!/usr/bin/env python3
"""Log one R125-E stage (screen or confirm) to W&B as a table plus summaries.

  python3 research/frieren_r125e_wandb.py --name r125e-screen /tmp/r125e/p1_runs.tsv ...
"""
import argparse
import statistics

import wandb

from frieren_r125e_analyze import PCT_SCORE_PER_US, control_interp, load

PROJECT = "mlxfast-maple"
ENTITY = "wandb-applied-ai-team"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("tsv", nargs="+")
    ap.add_argument("--name", required=True)
    ap.add_argument("--stage", default="screen")
    ap.add_argument("--steps", type=int, default=224)
    args = ap.parse_args()

    runs = control_interp(load(args.tsv))
    wb = wandb.init(
        entity=ENTITY, project=PROJECT, name=args.name,
        job_type="decode-probe-sweep",
        config=dict(
            assignment="maple-r125-e-shipped-default-flag-sweep",
            revision="r125-e-rev1", stage=args.stage,
            host="M4Pro-14cpu-48gib", startup_profile="full",
            golden="public_longcopy_gate_english_512_256",
            steps=args.steps, seed_tokens=512,
            pct_score_per_us=PCT_SCORE_PER_US,
        ),
    )
    tbl = wandb.Table(columns=["pass", "run", "arm", "median_ms", "mean_ms",
                              "ctrl_ms", "delta_us", "pct_score", "divergences"])
    for r in runs:
        tbl.add_data(r["tag"], r["run"], r["arm"], r["median"], r["mean"],
                     r["ctrl"], r["delta_us"], -r["delta_us"] * PCT_SCORE_PER_US,
                     r["div"])
    wb.log({f"{args.stage}/runs": tbl})

    arms = {}
    for r in runs:
        arms.setdefault(r["arm"], []).append(r["delta_us"])
    summary = {}
    for arm, d in arms.items():
        summary[f"{args.stage}/{arm}/delta_us_mean"] = statistics.fmean(d)
        summary[f"{args.stage}/{arm}/n"] = len(d)
        summary[f"{args.stage}/{arm}/pct_score"] = -statistics.fmean(d) * PCT_SCORE_PER_US
    ctrl = [r["median"] for r in runs if r["arm"] == "C"]
    if len(ctrl) > 1:
        summary[f"{args.stage}/control_sd_us"] = statistics.stdev(ctrl) * 1000.0
    summary[f"{args.stage}/control_median_ms"] = statistics.fmean(ctrl)
    summary[f"{args.stage}/divergences_total"] = sum(
        int(r["div"]) for r in runs if r["div"].isdigit())
    wb.summary.update(summary)
    print(wb.url, wb.id)
    wb.finish()


if __name__ == "__main__":
    main()
