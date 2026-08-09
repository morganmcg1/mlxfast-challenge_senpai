#!/usr/bin/env python3
"""Publish the r96-b Stage 1 certified-screen measurement to W&B.

  python3 research/frieren_r96b_wandb.py --results research/frieren-r96b-stage1-results.json

Stage 1 carries no kernel, so `router_us_per_step` is modelled from the byte
count with the host byte-time model rather than measured on a GPU timeline.
"""
import argparse
import json

import wandb

PROJECT = "mlxfast-maple"
ENTITY = "wandb-applied-ai-team"
SPARSE_LAYERS = 39
BASELINE_BYTES = 256 * 2048 * 2  # BF16 router plane, one layer-step

# M4 Pro byte-time model used for every r96 byte-price estimate on this host
DISPATCH_US = 3.97
BYTES_PER_US = 266.3e9 / 1e6
# realised score price of decode bytes on the ranked track
SCORE_PCT_PER_MB = 0.015224
# pre-registered go/no-go bar
BAR_NET_BYTES = 629146.0
BAR_A_P99 = 16
BAR_A_MAX = 64


def us_per_step(bytes_per_layer_step: float) -> float:
    return SPARSE_LAYERS * (DISPATCH_US + bytes_per_layer_step / BYTES_PER_US)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default="research/frieren-r96b-stage1-results.json")
    ap.add_argument("--step-us-total", type=float, required=True,
                    help="measured whole-model decode step time, microseconds")
    ap.add_argument("--commit", required=True)
    args = ap.parse_args()

    d = json.load(open(args.results))
    rows = d["rows"]
    prereg = [r for r in rows if not r["diagnostic"]]
    best = min(rows, key=lambda r: r["net_mean"])
    feasible = [r for r in rows
                if r["a_p99"] <= BAR_A_P99 and r["a_max"] <= BAR_A_MAX]
    best_feasible = min(feasible, key=lambda r: r["net_mean"]) if feasible else None

    run = wandb.init(
        entity=ENTITY, project=PROJECT,
        name="r96b-router-certified-screen-stage1",
        job_type="measurement",
        tags=["r96-b", "stage1", "router", "certified-screen", "no-go",
              "m4-pro", "no-kernel"],
        config=dict(
            assignment_id="maple-r96-b-router-certified-screen",
            revision_id="r96-b-rev1",
            commit=args.commit,
            host="apple-m4-pro-48gb",
            stage=1,
            layers=d["layers"],
            records_per_layer=d["records_per_layer"],
            routing_decisions=d["layers"] * d["records_per_layer"],
            baseline_bytes_per_layer_step=BASELINE_BYTES,
            bar_net_bytes=BAR_NET_BYTES,
            bar_ambiguous_p99=BAR_A_P99,
            bar_ambiguous_max=BAR_A_MAX,
            score_pct_per_mb=SCORE_PCT_PER_MB,
        ),
    )

    tbl = wandb.Table(columns=[
        "scheme", "bits", "group", "diagnostic",
        "router_bytes_per_step", "net_frac", "saving_mb_step", "score_pct",
        "net_resid_frac", "saving_resid_mb_step",
        "ambiguous_mean", "ambiguous_p99", "ambiguous_max", "ambiguous_zero_frac",
        "rho_share", "e1_wins_frac", "half_over_gap_median",
        "bound_looseness_median", "real_half_over_gap_median",
        "passes_bytes", "passes_ambiguity",
    ])
    for r in rows:
        tbl.add_data(
            r["scheme"], r["bits"], r["group"], r["diagnostic"],
            r["net_mean"], r["net_frac"], r["saving_mb_step"],
            r["saving_mb_step"] * SCORE_PCT_PER_MB,
            r["net_resid_frac"], r["saving_resid_mb_step"],
            r["a_mean"], r["a_p99"], r["a_max"], r["a_frac_zero"],
            r["rho_share"], r["e1_wins_frac"], r["half_over_gap_median"],
            r["bound_looseness_median"], r["real_half_over_gap_median"],
            r["net_mean"] <= BAR_NET_BYTES,
            r["a_p99"] <= BAR_A_P99 and r["a_max"] <= BAR_A_MAX,
        )
    run.log({"grid": tbl})

    base_us = us_per_step(BASELINE_BYTES)
    cand_us = us_per_step(best["net_mean"])
    summary = {
        "verdict_go": 0,
        "validation_exact_frac": d["validation_exact_frac"],
        # primary: best achievable certified router bytes, one layer-step
        "router_bytes_per_step": best["net_mean"],
        "router_bytes_per_step_baseline": float(BASELINE_BYTES),
        "router_bytes_per_step_frac": best["net_frac"],
        "router_us_per_step": cand_us,
        "router_us_per_step_baseline": base_us,
        "router_us_per_step_saving": base_us - cand_us,
        "step_us_total": args.step_us_total,
        "router_share_of_step": base_us / args.step_us_total,
        "saving_mb_step": best["saving_mb_step"],
        "projected_score_pct": best["saving_mb_step"] * SCORE_PCT_PER_MB,
        "ambiguous_experts_p99": best["a_p99"],
        "ambiguous_experts_max": best["a_max"],
        "ambiguous_experts_mean": best["a_mean"],
        "margin_p01": d["margin"]["p01"],
        "margin_p10": d["margin"]["p10"],
        "margin_median": d["margin"]["median"],
        "bound_looseness_median": best["bound_looseness_median"],
        "real_half_over_gap_median": best["real_half_over_gap_median"],
        "rho_share": best["rho_share"],
        "best_scheme": best["scheme"],
        "best_bits": best["bits"],
        "best_group": best["group"],
        "prereg_configs": len(prereg),
        "prereg_passing": 0,
    }
    if best_feasible is not None:
        summary.update({
            "feasible_router_bytes_per_step": best_feasible["net_mean"],
            "feasible_net_frac": best_feasible["net_frac"],
            "feasible_saving_mb_step": best_feasible["saving_mb_step"],
            "feasible_projected_score_pct":
                best_feasible["saving_mb_step"] * SCORE_PCT_PER_MB,
            "feasible_scheme": best_feasible["scheme"],
            "feasible_bits": best_feasible["bits"],
            "feasible_group": best_feasible["group"],
            "feasible_diagnostic": best_feasible["diagnostic"],
        })
    run.summary.update(summary)
    for k, v in sorted(summary.items()):
        print(f"{k}: {v}")
    print(f"\nrun: {run.url}\nid: {run.id}")
    run.finish()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
