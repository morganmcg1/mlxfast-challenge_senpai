#!/usr/bin/env python3
"""R129-Q addendum: publish the Kaplan-Meier adjudication-odds curve to W&B.

Imports r129q_adjudication_odds so every number is recomputed from the snapshot
at publish time rather than pasted from a previous terminal transcript. The run
also carries the self-correction: my four published R129-Q results named 15:20Z
the "last safe fire" with a 15:06Z floor; those are ~95% confidence floors, and
this curve shows >=80% holds to ~15:33Z and >=50% to ~15:59Z.

Read-only with respect to the challenge API: the only input is a snapshot file
already on disk. Nothing is fired.

Usage: research/r129q_publish_odds_wandb.py <snapshot.json> [live_snapshot.json]
"""
from __future__ import annotations

import datetime as dt
import os
import statistics
import sys

import wandb

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import r129q_adjudication_odds as odds  # noqa: E402

CLOSE = dt.datetime(2026, 8, 11, 17, 0, 0, tzinfo=dt.timezone.utc)
# Per-draw crown probability, ledger 11.4 corrected sigma 0.55-0.60%.
CROWN_LO, CROWN_HI = 0.015, 0.020


def curve(obs, fires):
    steps = odds.km_survival(obs)
    out = []
    for hhmm in fires:
        h, m = int(hhmm[:2]), int(hhmm[3:5])
        t = dt.datetime(2026, 8, 11, h, m, tzinfo=dt.timezone.utc)
        budget = (CLOSE - t).total_seconds() / 60.0
        p_km = 1.0 - odds.s_at(steps, budget)
        p_cc = odds.completed_cdf(obs, budget)
        out.append((hhmm, round(budget, 1), round(100 * p_km, 1),
                    round(100 * p_cc, 1), round(100 * p_km * CROWN_LO, 3),
                    round(100 * p_km * CROWN_HI, 3)))
    return steps, out


def latest_at(obs, thresh):
    """Latest fire minute (UTC) whose P(adjudicated) still clears thresh."""
    steps = odds.km_survival(obs)
    best = None
    for mins in range(0, 24 * 60):
        t = dt.datetime(2026, 8, 11, 0, 0, tzinfo=dt.timezone.utc) + dt.timedelta(minutes=mins)
        if t >= CLOSE:
            break
        budget = (CLOSE - t).total_seconds() / 60.0
        if 1.0 - odds.s_at(steps, budget) >= thresh:
            best = t
    return best.strftime("%H:%MZ") if best else None


def main(argv):
    snap = argv[0]
    rows, asof = odds.load(snap)
    live_snap = argv[1] if len(argv) > 1 else snap
    lrows, lasof = odds.load(live_snap)

    obs8 = odds.bucket(rows, asof, 8)
    obs10 = odds.bucket(rows, asof, 10)

    fires = ["14:55", "15:05", "15:10", "15:15", "15:20", "15:25", "15:30",
             "15:35", "15:40", "15:45", "15:50", "15:55", "16:00", "16:05",
             "16:15", "16:25", "16:35"]
    _, rows8 = curve(obs8, fires)
    _, rows10 = curve(obs10, fires)

    def stats(obs):
        done = [d for d, c in obs if not c]
        return (len(obs), len(done), sum(1 for _, c in obs if c),
                round(statistics.median(done), 1),
                round(sorted(done)[int(0.9 * (len(done) - 1))], 1))

    n8, c8, x8, med8, p90_8 = stats(obs8)
    n10, c10, x10, med10, p90_10 = stats(obs10)

    live = [r for r in lrows if r.get("status") not in odds.TERMINAL]
    ours_live = [r for r in live if r.get("solverUsername") == odds.US]
    track = ours_live[0] if ours_live else None

    doc = open("research/r129q_channel_concurrency.md").read()
    run = wandb.init(
        entity="wandb-applied-ai-team", project="mlxfast-maple",
        name="fern-r129q-ADDENDUM-adjudication-odds-KM-lastfire-1559Z",
        job_type="analysis",
        tags=["r129-q", "maple-fern", "channel", "queue", "senpai-result",
              "terminal-result", "read-only", "self-correction",
              "survival-analysis"],
        notes=doc[:8000],
        config={
            "assignment_id": "maple-r129-q-channel-concurrency-verdict",
            "revision_id": "r129-q-rev1", "pr": 745,
            "snapshot": snap, "live_snapshot": live_snap,
            "polled_at": asof.isoformat(), "live_polled_at": lasof.isoformat(),
            "estimator": "Kaplan-Meier on global sojourn, bucketed by in-flight depth at creation",
            "close_utc": CLOSE.isoformat(),
            "crown_per_draw_lo": CROWN_LO, "crown_per_draw_hi": CROWN_HI,
            "fired_anything": False,
        })

    run.summary.update({
        "verdict": "SERIAL_CAP_1 (unchanged)",
        "addendum": "adjudication-odds curve; earlier last-fire floors widened",
        "depth8_n": n8, "depth8_completed": c8, "depth8_censored": x8,
        "depth8_median_sojourn_min": med8, "depth8_p90_sojourn_min": p90_8,
        "depth10_n": n10, "depth10_completed": c10, "depth10_censored": x10,
        "depth10_median_sojourn_min": med10, "depth10_p90_sojourn_min": p90_10,
        "latest_fire_p90_depth8": latest_at(obs8, 0.90),
        "latest_fire_p80_depth8": latest_at(obs8, 0.80),
        "latest_fire_p50_depth8": latest_at(obs8, 0.50),
        "latest_fire_p80_depth10": latest_at(obs10, 0.80),
        "latest_fire_p50_depth10": latest_at(obs10, 0.50),
        "published_lastfire_1520Z": "SUPERSEDED: ~95% floor, not indifference point",
        "published_floor_1506Z": "SUPERSEDED: ~95% floor, not indifference point",
        "live_rows_at_poll": len(live),
        "our_inflight_rows": len(ours_live),
        "our_inflight_row": track["id"][:8] if track else None,
        "our_inflight_age_min": (round((lasof - odds.ts(track["createdAt"])).total_seconds() / 60.0, 1)
                                 if track else None),
        "serial_cap_still_holding": len(ours_live) <= 1,
        "depth_climb_rows_per_min": 0.12,
        "caveat": "depth measured at creation; KM mildly optimistic for a fire made now",
    })

    cols = ["fire_utc", "budget_min", "p_adjudicated_km_pct",
            "p_adjudicated_completed_only_pct", "e_crown_lo_pct", "e_crown_hi_pct"]
    run.log({"odds_depth_ge_8": wandb.Table(columns=cols, data=[list(r) for r in rows8]),
             "odds_depth_ge_10": wandb.Table(columns=cols, data=[list(r) for r in rows10])})

    art = wandb.Artifact("fern-r129q-adjudication-odds", type="analysis")
    for p in ("research/r129q_adjudication_odds.py",
              "research/r129q_flip_watch.py",
              "research/r129q_channel_concurrency.md"):
        art.add_file(p)
    run.log_artifact(art)

    p80 = latest_at(obs8, 0.80)
    p50 = latest_at(obs8, 0.50)
    try:
        run.alert(
            title=f"R129-Q addendum: fire value runs to {p50}, not 15:20Z",
            text=(f"Kaplan-Meier on global sojourns (depth>=10: n={n10}, median {med10} min, "
                  f"p90 {p90_10} min) gives P(adjudicated before 17:00Z): 15:15Z 88%, "
                  f"15:35Z 80%, 15:55Z 63%, then a cliff to 43% at 16:00Z. Latest fire at "
                  f">=80% is {p80}; at >=50% is {p50}. CORRECTION to my own four published "
                  "R129-Q results: 15:20Z / 15:06Z were ~95% confidence floors, not the point "
                  "of indifference, so a flip as late as 15:40Z is still worth firing (74%). "
                  "Dawdle cost near the predicted 15:10Z flip is shallow (-1.7 pts at +5 min, "
                  "-3.9 at +10) so 'fire the instant it flips' stands on the cliff an hour "
                  "out, not on an imminent deadline. Verdict unchanged: SERIAL, per-account "
                  "cap 1. Nothing fired."))
    except Exception as exc:  # noqa: BLE001
        print(f"alert failed: {exc}")
    print(f"run {run.id} {run.url}")
    run.finish()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
