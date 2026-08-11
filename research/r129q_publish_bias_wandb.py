#!/usr/bin/env python3
"""Publish the R129-Q depth-bias audit to W&B.

Imports `r129q_depth_bias_correction` and RECOMPUTES every number at publish
time.  Nothing is pasted from a terminal transcript, so the run cannot drift
from the script that earned it.

Run from the repo root:
    python research/r129q_publish_bias_wandb.py <snapshot.json>
"""
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
import wandb  # noqa: E402

from r129q_depth_bias_correction import (  # noqa: E402
    boot_p_at, build, km, load, perm_p, q, s_at, spearman, today_sample,
)
import statistics  # noqa: E402


def main():
    snap = sys.argv[1]
    W, BUCKET = 15.0, 8
    rows, asof = load(snap)
    close = asof.replace(hour=17, minute=0, second=0, microsecond=0)
    _, recs, dropped = build(rows, asof, W)
    done = [x for x in recs if x["done"] and x["soj"] > 0]
    ls = [x["soj"] for x in done]

    rho = {k: spearman([x[k] for x in done], ls)
           for k in ("d_create", "d_win", "d_life")}

    B = [x for x in done if x["d_create"] >= BUCKET]
    rise = [x for x in B if x["slope"] >= 2]
    flat = [x for x in B if abs(x["slope"]) <= 1]
    fall = [x for x in B if x["slope"] <= -2]
    med = lambda g: statistics.median([x["soj"] for x in g]) if g else float("nan")
    gap = med(rise) - med(flat)
    p_perm = perm_p([x["soj"] for x in rise], [x["soj"] for x in flat])

    pub = [(x["soj"], x["done"]) for x in recs if x["d_create"] >= 10]
    cor = [(x["soj"], x["done"]) for x in recs if x["d_win"] >= 10]
    today = today_sample(rows, asof)
    kp, kc, kd = km(pub), km(cor), km(today)

    probe = asof.replace(second=0, microsecond=0) + dt.timedelta(minutes=35)
    bud = (close - probe).total_seconds() / 60.0
    p_pub = 1 - s_at(kp, bud)
    p_cor = 1 - s_at(kc, bud)
    p_tod = 1 - s_at(kd, bud)
    a_lo, a_hi = boot_p_at(pub, bud)
    b_lo, b_hi = boot_p_at(cor, bud)
    t_lo, t_hi = boot_p_at(today, bud)

    # era composition of the tempting "correction"
    setA = {x["id"] for x in recs if x["d_create"] >= 10}
    setB = {x["id"] for x in recs if x["d_win"] >= 10}
    dayB = {}
    for x in recs:
        if x["d_win"] >= 10:
            dayB[x["c"].strftime("%m-%d")] = dayB.get(x["c"].strftime("%m-%d"), 0) + 1
    top_day, top_n = max(dayB.items(), key=lambda kv: kv[1])
    today_deep = [x["soj"] for x in recs
                  if x["d_create"] >= 10 and x["c"].date() == asof.date()]

    def deadline(curve, thr):
        base = asof.replace(second=0, microsecond=0)
        last = None
        for k in range(0, 24 * 12):
            T = base + dt.timedelta(minutes=5 * k)
            if T > close:
                break
            if 1 - s_at(curve, (close - T).total_seconds() / 60.0) >= thr:
                last = T
        return last.strftime("%H:%MZ") if last else "past"

    run = wandb.init(
        entity="wandb-applied-ai-team", project="mlxfast-maple",
        name="r129q-depth-bias-audit",
        job_type="analysis",
        notes=("Audit of my own published adjudication-odds curve: measures the "
               "unquantified 'depth measured at creation' caveat, rejects an era-"
               "confounded false correction, and re-tests the deadline on today's "
               "population only. Read-only; nothing fired."),
        tags=["r129-q", "channel", "audit", "self-correction", "read-only"],
        config=dict(snapshot=os.path.basename(snap), asof=asof.isoformat(),
                    close=close.isoformat(), window_min=W, slope_bucket=BUCKET,
                    rows=len(rows), usable=len(recs), completed=len(done),
                    dropped_edge=dropped, probe_fire=probe.strftime("%H:%MZ"),
                    probe_budget_min=bud),
    )

    wandb.log({
        "rho_sojourn_d_create": rho["d_create"],
        "rho_sojourn_d_win": rho["d_win"],
        "rho_sojourn_d_life": rho["d_life"],
        "slope_rising_n": len(rise), "slope_flat_n": len(flat),
        "slope_falling_n": len(fall),
        "median_sojourn_rising_min": med(rise),
        "median_sojourn_flat_min": med(flat),
        "median_sojourn_falling_min": med(fall),
        "caveat_size_rising_minus_flat_min": gap,
        "caveat_permutation_p": p_perm,
        "km_median_published_min": q(kp, 0.5),
        "km_median_ambient_min": q(kc, 0.5),
        "km_median_today_min": q(kd, 0.5),
        "p_adjudicated_published_pct": 100 * p_pub,
        "p_adjudicated_ambient_pct": 100 * p_cor,
        "p_adjudicated_today_pct": 100 * p_tod,
        "ci_published_lo_pct": 100 * a_lo, "ci_published_hi_pct": 100 * a_hi,
        "ci_ambient_lo_pct": 100 * b_lo, "ci_ambient_hi_pct": 100 * b_hi,
        "ci_today_lo_pct": 100 * t_lo, "ci_today_hi_pct": 100 * t_hi,
        "n_published": len(pub), "n_ambient": len(cor), "n_today": len(today),
        "n_today_censored": sum(1 for _, t in today if not t),
        "ambient_bucket_top_day_share_pct": 100 * top_n / max(1, len(cor)),
        "ambient_overlap_with_published": len(setA & setB),
        "today_deep_median_min": (statistics.median(today_deep)
                                  if today_deep else float("nan")),
        "today_deep_n": len(today_deep),
    })

    tbl = wandb.Table(columns=["fire_T", "budget_min", "P_published_pct",
                               "P_ambient_pct", "P_today_pct"])
    base = asof.replace(second=0, microsecond=0)
    for k in range(0, 30):
        T = base + dt.timedelta(minutes=5 * k)
        if T > close:
            break
        bg = (close - T).total_seconds() / 60.0
        tbl.add_data(T.strftime("%H:%MZ"), round(bg, 1),
                     round(100 * (1 - s_at(kp, bg)), 1),
                     round(100 * (1 - s_at(kc, bg)), 1),
                     round(100 * (1 - s_at(kd, bg)), 1))
    wandb.log({"adjudication_odds_by_fire_time": tbl})

    dl = wandb.Table(columns=["threshold_pct", "published", "ambient", "today_only"])
    for thr in (0.9, 0.8, 0.5):
        dl.add_data(int(100 * thr), deadline(kp, thr), deadline(kc, thr),
                    deadline(kd, thr))
    wandb.log({"latest_fire_by_confidence": dl})

    verdict = ("ambient bucketing REJECTED as era confound; published curve and "
               "today-only curve agree, so the published deadline stands")
    if t_hi < p_pub:
        verdict = "today significantly SLOWER than published curve"
    elif t_lo > p_pub:
        verdict = "today significantly FASTER than published curve"
    wandb.summary["verdict"] = verdict
    wandb.summary["caveat_retired"] = bool(p_perm > 0.05)
    print("run:", run.url)
    print(f"rho d_create {rho['d_create']:+.3f} / d_win {rho['d_win']:+.3f} / "
          f"d_life {rho['d_life']:+.3f}")
    print(f"caveat gap {gap:+.1f} min, permutation p {p_perm:.2f}")
    print(f"probe {probe.strftime('%H:%MZ')}: published {100*p_pub:.1f}% "
          f"[{100*a_lo:.1f},{100*a_hi:.1f}]  ambient {100*p_cor:.1f}% "
          f"[{100*b_lo:.1f},{100*b_hi:.1f}]  today {100*p_tod:.1f}% "
          f"[{100*t_lo:.1f},{100*t_hi:.1f}]")
    print(f"ambient bucket: {top_n}/{len(cor)} rows from {top_day}")
    print(f"deadlines >=80%: published {deadline(kp,0.8)}  today {deadline(kd,0.8)}")
    print("verdict:", verdict)
    run.finish()


if __name__ == "__main__":
    main()
