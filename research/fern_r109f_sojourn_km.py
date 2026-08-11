#!/usr/bin/env python3
"""fern r109-f: Kaplan-Meier sojourn of the ranked validation channel.

WHY KM AND NOT A MEAN OR A MEDIAN OF TERMINAL ROWS

The channel's per-row sojourn is the number that decides how many official draws
a campaign can still fire before a hard close. Every naive estimator of it that
this campaign has used so far is biased, in a knowable direction:

1. *Median over terminal rows created in the last N hours* is biased DOWN by
   right-censoring: a row created 40 min ago that is still `validating` will
   eventually contribute a long sojourn, but it is excluded from the sample
   precisely because it is long. At 12:24Z the six live rows had ages 159, 76,
   52, 41, 27 and 7 min against a "median" of 62 min from terminal rows -- three
   censored observations already exceeded the estimate, which is the signature of
   this bias.
2. *Median over rows that departed in the last N hours* is length-biased UP:
   sampling by departure time over-weights rows whose service straddled the
   window.
3. *Head-of-line age* is not a queue wait at all. Rows from different accounts
   are in service concurrently (6 simultaneously `validating` at 12:24Z), so the
   oldest live row is a straggler.
4. *Per-account createdAt gap* measures our own firing discipline, including
   idle time, not the channel.

Kaplan-Meier is the standard fix for (1): it uses each live row as a censored
observation at its current age instead of discarding it, so the survival curve
is estimated from all the information available at read time.

WHAT IT OUTPUTS

* S(t) = P(sojourn > t), and the KM median / p75.
* The decision table the campaign actually needs: for a candidate fired at time
  t_f, P(it resolves before close) = 1 - S(close - t_f). A row that has not gone
  terminal by close published no score, so this is the probability that a draw
  counts at all.

Usage:
  research/fern_r109f_sojourn_km.py <snapshot.json> [--hours 8] [--close 17:00]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json

TERMINAL = {"completed", "failed", "accepted", "rejected", "cancelled", "error"}


def ts(s):
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00")) if s else None


def kaplan_meier(obs):
    """obs = [(duration_minutes, event)] with event=1 terminal, 0 censored.

    Returns [(t, S(t))] as a right-continuous step function, S(0)=1.
    """
    obs = sorted(obs)
    n_at_risk = len(obs)
    curve = [(0.0, 1.0)]
    s = 1.0
    i = 0
    while i < len(obs):
        t = obs[i][0]
        tied = [o for o in obs if o[0] == t]
        d = sum(e for _, e in tied)          # events at t
        if d:
            s *= (1.0 - d / n_at_risk)
            curve.append((t, s))
        n_at_risk -= len(tied)
        i += len(tied)
    return curve


def s_at(curve, t):
    s = 1.0
    for tt, ss in curve:
        if tt <= t:
            s = ss
        else:
            break
    return s


def quantile(curve, p):
    """smallest t with S(t) <= 1-p, i.e. the KM p-quantile of sojourn."""
    for tt, ss in curve:
        if ss <= 1.0 - p:
            return tt
    return float("inf")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("snapshot")
    ap.add_argument("--hours", type=float, default=8.0)
    ap.add_argument("--close", default="17:00")
    args = ap.parse_args()

    rows = json.load(open(args.snapshot))["submissions"]
    now = dt.datetime.now(dt.timezone.utc)
    hh, mm = (int(x) for x in args.close.split(":"))
    close = now.replace(hour=hh, minute=mm, second=0, microsecond=0)

    obs, n_term, n_cens = [], 0, 0
    for r in rows:
        c = ts(r.get("createdAt"))
        if not c or (now - c).total_seconds() > args.hours * 3600:
            continue
        if r.get("status") in TERMINAL and r.get("updatedAt"):
            obs.append(((ts(r["updatedAt"]) - c).total_seconds() / 60.0, 1))
            n_term += 1
        else:
            obs.append(((now - c).total_seconds() / 60.0, 0))
            n_cens += 1

    print(f"read_at={now:%Y-%m-%dT%H:%M:%SZ}  window={args.hours:g}h"
          f"  observations={len(obs)} (terminal {n_term}, censored {n_cens})")
    if not obs:
        return 1
    km = kaplan_meier(obs)

    naive = sorted(d for d, e in obs if e == 1)
    naive_med = naive[len(naive) // 2] if naive else float("nan")
    print(f"\nnaive median over terminal rows only : {naive_med:6.1f} min  (biased DOWN)")
    print(f"Kaplan-Meier median sojourn          : {quantile(km, 0.50):6.1f} min")
    print(f"Kaplan-Meier p75                     : {quantile(km, 0.75):6.1f} min")
    print(f"Kaplan-Meier p90                     : {quantile(km, 0.90):6.1f} min")

    print("\n=== S(t) = P(sojourn > t) ===")
    for t in (15, 30, 45, 60, 75, 90, 120, 150, 180):
        print(f"  t={t:3d} min   S={s_at(km, t):5.3f}   P(resolved by t)={1 - s_at(km, t):5.3f}")

    print(f"\n=== fire-time decision table, close {close:%H:%MZ} ===")
    print("  fire at   budget   P(resolves before close)")
    t = now.replace(second=0, microsecond=0)
    while t <= close - dt.timedelta(minutes=15):
        budget = (close - t).total_seconds() / 60.0
        print(f"  {t:%H:%MZ}   {budget:6.0f}   {1 - s_at(km, budget):5.3f}")
        t += dt.timedelta(minutes=30)

    ours = [r for r in rows
            if r.get("solverUsername") == "morganmcg1" and r.get("status") not in TERMINAL]
    if ours:
        c = ts(ours[0]["createdAt"])
        age = (now - c).total_seconds() / 60.0
        # conditional on having survived to `age`
        s_age = s_at(km, age)
        print(f"\n=== our live row {ours[0]['id'][:8]} created {c:%H:%M:%SZ}, age {age:.0f} min ===")
        for extra in (15, 30, 45, 60, 90):
            s_tot = s_at(km, age + extra)
            cond = 1 - (s_tot / s_age if s_age else 0.0)
            print(f"  P(terminal within next {extra:3d} min | still live) = {cond:5.3f}"
                  f"   -> by {now + dt.timedelta(minutes=extra):%H:%MZ}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
