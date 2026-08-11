#!/usr/bin/env python3
"""R129-Q: residual-life forecast for the resident own row, and the value of the
draw it unblocks.

My registered prediction said c06b1b6d would go terminal in 14:30-15:35Z with
centre ~15:10Z. That band was set from a handful of own-account sojourns. This
recomputes it properly and, more importantly, answers the question that actually
matters now: the row has ALREADY survived a long time, so what is the residual
distribution, and is the draw it unblocks still worth firing?

Method
------
1. Sojourn observations from the global listing, bucketed by in-flight depth at
   creation (matching the depth c06b1b6d itself saw), right-censored rows kept.
2. Kaplan-Meier S(t). Condition on survival past the row's current age a:
   S(t | T > a) = S(t) / S(a). This is the honest residual forecast; because the
   hazard is not exponential, "it has waited 68 min" changes the answer.
3. Cross the residual flip-time distribution with the adjudication curve from
   r129q_adjudication_odds (P(a fire at time T is adjudicated before 17:00Z))
   to get E[P(adjudicated)] for the NEXT draw, and P(that draw is worthless).

Read-only: consumes an on-disk snapshot. Nothing is fired.

Usage: research/r129q_residual_flip_forecast.py <snapshot.json> [--track c06b1b6d]
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import r129q_adjudication_odds as odds  # noqa: E402

CLOSE = dt.datetime(2026, 8, 11, 17, 0, 0, tzinfo=dt.timezone.utc)
BAND_LO = dt.datetime(2026, 8, 11, 14, 30, tzinfo=dt.timezone.utc)
BAND_HI = dt.datetime(2026, 8, 11, 15, 35, tzinfo=dt.timezone.utc)


def depth_seen_by(rows, target_id, asof):
    """(row, depth at its creation, current age min) for the tracked row."""
    for k, dur, cens, r in odds.depth_at(rows, asof):
        if r["id"].startswith(target_id):
            return r, k, dur, cens
    return None, None, None, None


def quantile_from_steps(steps, s_target, cap):
    """Smallest t with S(t) <= s_target, else None (KM tail not reached)."""
    for t, s in steps:
        if s <= s_target:
            return t
    return None


def window_bucket(rows, asof, lo, hi):
    """Sojourns for rows admitted at in-flight depth in [lo, hi]."""
    return [(d, cens) for (k, d, cens, _r) in odds.depth_at(rows, asof)
            if lo <= k <= hi]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("snapshot")
    ap.add_argument("--track", default="c06b1b6d")
    ap.add_argument("--now", default=None, help="override 'now' as HH:MM (UTC)")
    ap.add_argument("--adj-depth", type=int, default=10,
                    help="depth bucket for the NEW fire's adjudication curve")
    ap.add_argument("--cur-depth", type=int, default=12,
                    help="current global in-flight depth, for the printout")
    args = ap.parse_args()

    rows, asof = odds.load(args.snapshot)
    row, depth, age, cens = depth_seen_by(rows, args.track, asof)
    if row is None:
        print(f"tracked row {args.track} not in snapshot")
        return 1
    created = odds.ts(row["createdAt"])
    now = asof
    if args.now:
        h, m = int(args.now[:2]), int(args.now[3:5])
        now = dt.datetime(2026, 8, 11, h, m, tzinfo=dt.timezone.utc)
        age = (now - created).total_seconds() / 60.0

    print(f"snapshot polled {asof:%H:%M:%SZ}   'now' = {now:%H:%M:%SZ}")
    print(f"tracked row {row['id'][:8]}  status={row.get('status')}  "
          f"created {created:%H:%M:%SZ}  depth at creation={depth}  "
          f"age now {age:.1f} min")
    print(f"note: {row.get('note', '')[:70]!r}")

    # Two DIFFERENT populations, which an earlier draft of this script wrongly
    # conflated:
    #  * residual life of the resident row -> rows admitted at ITS depth (5),
    #    because that is the queue it actually entered;
    #  * adjudication odds for a fire made NOW -> rows admitted at TODAY's depth
    #    (12), because that is the queue the next fire would enter.
    adj_obs = odds.bucket(rows, asof, args.adj_depth)
    adj_steps = odds.km_survival(adj_obs)
    print(f"\nadjudication curve for a NEW fire uses depth >= {args.adj_depth} "
          f"(n={len(adj_obs)}); current global in-flight is {args.cur_depth}")

    d = depth or 0
    pops = [(max(0, d - 1), d + 2, f"as-admitted depth {d} (window "
             f"{max(0, d - 1)}-{d + 2})"),
            (0, 10 ** 6, "all depths (widest, most data)"),
            (args.adj_depth, 10 ** 6, f"depth >= {args.adj_depth} (today's "
             "congestion, shown only for contrast)")]
    for lo, hi, label in pops:
        obs = window_bucket(rows, asof, lo, hi)
        if len(obs) < 20:
            print(f"\n== {label}: n={len(obs)} too thin, skipped ==")
            continue
        steps = odds.km_survival(obs)
        s_age = odds.s_at(steps, age)
        done = [x for x, c in obs if not c]
        surv = sum(1 for x, c in obs if x >= age)
        print(f"\n== residual population: {label}  n={len(obs)} "
              f"({len(done)} completed)  S({age:.0f} min)={s_age:.3f}  "
              f"{surv} of {len(obs)} lasted this long ==")
        if s_age <= 0:
            print("  KM has run to zero at this age: no comparable row lasted "
                  "this long, so the residual forecast is undefined (our row is "
                  "already an outlier for its depth).")
            continue

        # Residual quantiles: S(t)/S(age) = q  ->  S(t) = q * S(age).
        print("  residual life, conditional on having already waited "
              f"{age:.0f} min:")
        for q, lab in ((0.75, "p25"), (0.5, "median"), (0.25, "p75"),
                       (0.1, "p90")):
            t = quantile_from_steps(steps, q * s_age, None)
            if t is None:
                print(f"    {lab:>6}: beyond the KM tail (>{max(done):.0f} min total)")
            else:
                flip = created + dt.timedelta(minutes=t)
                print(f"    {lab:>6}: total {t:6.1f} min  -> flip {flip:%H:%MZ}"
                      f"  (+{t - age:5.1f} min from now)")

        # Probability the flip lands inside my registered band.
        lo = (BAND_LO - created).total_seconds() / 60.0
        hi = (BAND_HI - created).total_seconds() / 60.0
        p_band = (odds.s_at(steps, max(lo, age)) - odds.s_at(steps, hi)) / s_age
        p_late = odds.s_at(steps, hi) / s_age
        print(f"  P(flip within registered band {BAND_LO:%H:%M}-{BAND_HI:%H:%M}Z"
              f" | waited {age:.0f} min) = {100 * p_band:.1f}%")
        print(f"  P(flip AFTER {BAND_HI:%H:%MZ}, i.e. prediction misses high) = "
              f"{100 * p_late:.1f}%")

        # Value of the draw this row unblocks: integrate the adjudication curve
        # over the residual flip-time distribution, in 5-min cells.
        cells, p_tot, ev = [], 0.0, 0.0
        t = age
        while t < (CLOSE - created).total_seconds() / 60.0:
            t2 = t + 5.0
            p = (odds.s_at(steps, t) - odds.s_at(steps, t2)) / s_age
            if p > 0:
                mid = created + dt.timedelta(minutes=(t + t2) / 2.0)
                budget = (CLOSE - mid).total_seconds() / 60.0
                p_adj = 1.0 - odds.s_at(adj_steps, budget)
                cells.append((mid, p, p_adj))
                p_tot += p
                ev += p * p_adj
            t = t2
        horizon = (CLOSE - created).total_seconds() / 60.0
        p_never = odds.s_at(steps, horizon) / s_age
        tail = max(done)
        note = ""
        if tail < horizon:
            note = (f"  [KM tail ends at {tail:.0f} min < horizon {horizon:.0f} "
                    "min, so P(never frees) is pinned at 0 by construction, "
                    "not measured]")
        print(f"  next draw: P(slot frees before 17:00Z)={100 * p_tot:.1f}%, "
              f"P(never frees)={100 * p_never:.1f}%{note}")
        if p_tot > 0:
            print(f"  E[P(next fire adjudicated)] = {100 * ev:.1f}%  "
                  f"(= {100 * ev / p_tot:.1f}% conditional on the slot freeing)")
            print(f"  E[crown from that draw] = {100 * ev * 0.015:.2f}-"
                  f"{100 * ev * 0.020:.2f}%  (1.5-2.0% per adjudicated draw)")
        worthless = sum(p for mid, p, pa in cells if pa < 0.5) + p_never
        print(f"  P(next draw effectively worthless: frees after ~15:59Z or "
              f"not at all) = {100 * worthless:.1f}%")

    print("\nCAVEATS: depth is measured at creation, so the comparable set does "
          "not know about arrivals after each row was admitted; and conditioning "
          "on a long wait selects for whatever makes a row slow, which KM cannot "
          "see. Both push the true residual longer than printed here.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
