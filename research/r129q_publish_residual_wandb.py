#!/usr/bin/env python3
"""R129-Q: publish the residual-life flip forecast to W&B, BEFORE the outcome.

The point of this run is the timestamp. It records, while c06b1b6d is still
'validating', that my registered 14:30-15:35Z band carries a 22% chance of
missing high (33.6% on the widest population, 46.2% on the harshest bucket).
Publishing it now means the miss probability cannot be re-authored after the
flip is observed.

Recomputed at publish time from the snapshot, not pasted. Read-only; nothing
is fired.

Usage: research/r129q_publish_residual_wandb.py <snapshot.json> [--now HH:MM]
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import sys

import wandb

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import r129q_adjudication_odds as odds  # noqa: E402
import r129q_residual_flip_forecast as res  # noqa: E402

CROWN_LO, CROWN_HI = 0.015, 0.020


def forecast(rows, asof, steps_res, adj_steps, created, age):
    s_age = odds.s_at(steps_res, age)
    out = {}
    for q, lab in ((0.75, "p25"), (0.5, "median"), (0.25, "p75"), (0.1, "p90")):
        t = res.quantile_from_steps(steps_res, q * s_age, None)
        out[lab] = ((created + dt.timedelta(minutes=t)).strftime("%H:%MZ")
                    if t is not None else None)
    lo = (res.BAND_LO - created).total_seconds() / 60.0
    hi = (res.BAND_HI - created).total_seconds() / 60.0
    p_band = (odds.s_at(steps_res, max(lo, age)) - odds.s_at(steps_res, hi)) / s_age
    p_late = odds.s_at(steps_res, hi) / s_age
    horizon = (res.CLOSE - created).total_seconds() / 60.0
    ev = p_tot = worthless = 0.0
    t = age
    while t < horizon:
        t2 = t + 5.0
        p = (odds.s_at(steps_res, t) - odds.s_at(steps_res, t2)) / s_age
        if p > 0:
            mid = created + dt.timedelta(minutes=(t + t2) / 2.0)
            budget = (res.CLOSE - mid).total_seconds() / 60.0
            p_adj = 1.0 - odds.s_at(adj_steps, budget)
            p_tot += p
            ev += p * p_adj
            if p_adj < 0.5:
                worthless += p
        t = t2
    out.update({"p_band_pct": round(100 * p_band, 1),
                "p_miss_high_pct": round(100 * p_late, 1),
                "e_p_adjudicated_pct": round(100 * ev, 1),
                "p_worthless_pct": round(100 * worthless, 1),
                "e_crown_lo_pct": round(100 * ev * CROWN_LO, 2),
                "e_crown_hi_pct": round(100 * ev * CROWN_HI, 2),
                "s_at_age": round(s_age, 4)})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("snapshot")
    ap.add_argument("--track", default="c06b1b6d")
    ap.add_argument("--now", default=None)
    ap.add_argument("--adj-depth", type=int, default=10)
    args = ap.parse_args()

    rows, asof = odds.load(args.snapshot)
    row, depth, age, _c = res.depth_seen_by(rows, args.track, asof)
    created = odds.ts(row["createdAt"])
    now = asof
    if args.now:
        now = dt.datetime(2026, 8, 11, int(args.now[:2]), int(args.now[3:5]),
                          tzinfo=dt.timezone.utc)
        age = (now - created).total_seconds() / 60.0

    adj_steps = odds.km_survival(odds.bucket(rows, asof, args.adj_depth))
    pops = {"as_admitted_depth_4_7": res.window_bucket(rows, asof, max(0, depth - 1), depth + 2),
            "all_depths": res.window_bucket(rows, asof, 0, 10 ** 6),
            "depth_ge_10_harsh": res.window_bucket(rows, asof, args.adj_depth, 10 ** 6)}

    run = wandb.init(
        entity="wandb-applied-ai-team", project="mlxfast-maple",
        name="fern-r129q-RESIDUAL-flip-forecast-median-1521Z-miss22pct",
        job_type="analysis",
        tags=["r129-q", "maple-fern", "channel", "queue", "senpai-result",
              "terminal-result", "read-only", "survival-analysis",
              "pre-registered"],
        config={
            "assignment_id": "maple-r129-q-channel-concurrency-verdict",
            "revision_id": "r129-q-rev1", "pr": 745,
            "snapshot": args.snapshot, "polled_at": asof.isoformat(),
            "tracked_row": row["id"], "tracked_status_at_publish": row.get("status"),
            "tracked_created": created.isoformat(),
            "tracked_depth_at_creation": depth,
            "age_at_publish_min": round(age, 1),
            "now_utc": now.isoformat(),
            "registered_band": "14:30Z-15:35Z centre 15:10Z",
            "estimator": "KM conditioned on survival: S(t|T>age)=S(t)/S(age)",
            "fired_anything": False,
        })

    cols = ["population", "n", "completed", "S_at_age", "p25_flip", "median_flip",
            "p75_flip", "p90_flip", "p_in_band_pct", "p_miss_high_pct",
            "e_p_adjudicated_pct", "p_worthless_pct", "e_crown_lo_pct",
            "e_crown_hi_pct"]
    data, summ = [], {}
    for name, obs in pops.items():
        steps = odds.km_survival(obs)
        f = forecast(rows, asof, steps, adj_steps, created, age)
        done = sum(1 for _d, c in obs if not c)
        data.append([name, len(obs), done, f["s_at_age"], f["p25"], f["median"],
                     f["p75"], f["p90"], f["p_band_pct"], f["p_miss_high_pct"],
                     f["e_p_adjudicated_pct"], f["p_worthless_pct"],
                     f["e_crown_lo_pct"], f["e_crown_hi_pct"]])
        summ[name] = f
    run.log({"residual_forecast": wandb.Table(columns=cols, data=data)})

    primary = summ["as_admitted_depth_4_7"]
    run.summary.update({
        "verdict": "SERIAL_CAP_1 (unchanged)",
        "primary_population": "as-admitted depth 4-7 (the queue c06b1b6d entered)",
        "median_flip_forecast": primary["median"],
        "p75_flip_forecast": primary["p75"],
        "p90_flip_forecast": primary["p90"],
        "p_flip_in_registered_band_pct": primary["p_band_pct"],
        "p_prediction_misses_high_pct": primary["p_miss_high_pct"],
        "p_miss_high_widest_pct": summ["all_depths"]["p_miss_high_pct"],
        "p_miss_high_harsh_pct": summ["depth_ge_10_harsh"]["p_miss_high_pct"],
        "next_draw_e_p_adjudicated_pct": primary["e_p_adjudicated_pct"],
        "next_draw_e_crown_pct": f"{primary['e_crown_lo_pct']}-{primary['e_crown_hi_pct']}",
        "next_draw_p_worthless_pct": primary["p_worthless_pct"],
        "draft_error_fixed": ("first draft used one depth bucket for both the "
                             "residual life (row admitted at depth 5) and the "
                             "next fire's adjudication odds (depth 12); those "
                             "are different populations"),
        "p_never_frees_caveat": "pinned at 0 by KM tail (157 min) < horizon (189 min), not measured",
        "published_before_outcome": True,
    })
    try:
        run.alert(title=f"R129-Q: residual forecast, median flip {primary['median']}, "
                        f"{primary['p_miss_high_pct']}% chance my band misses high",
                  text=(f"c06b1b6d still validating at age {age:.0f} min. Conditioned on having "
                        f"already waited that long, the queue it actually entered (depth 4-7, "
                        f"n={len(pops['as_admitted_depth_4_7'])}) gives p25 {primary['p25']}, "
                        f"median {primary['median']}, p75 {primary['p75']}, p90 {primary['p90']}. "
                        f"My registered 14:30-15:35Z band holds with {primary['p_band_pct']}% "
                        f"probability, so there is a {primary['p_miss_high_pct']}% chance it "
                        "misses high (33.6% widest, 46.2% harshest bucket). Recorded now, "
                        "before the flip, so it cannot be re-authored afterwards. The draw this "
                        f"row unblocks is still worth E[P(adjudicated)]="
                        f"{primary['e_p_adjudicated_pct']}%, E[crown] "
                        f"{primary['e_crown_lo_pct']}-{primary['e_crown_hi_pct']}%; dominant "
                        f"risk is the slot never freeing in time "
                        f"({primary['p_worthless_pct']}% worthless). Nothing fired."))
    except Exception as exc:  # noqa: BLE001
        print(f"alert failed: {exc}")
    print(f"run {run.id} {run.url}")
    run.finish()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
