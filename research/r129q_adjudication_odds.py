#!/usr/bin/env python3
"""fern R129-Q: P(a row fired at time T is ADJUDICATED before the 17:00Z close).

R129-Q's verdict gives the campaign a gate ("fire the instant our resident row
flips") but not a value: a draw that is still `validating` at 17:00Z scores
nothing, so the second draw is worth p_win x P(adjudicated in time), and that
second factor collapses as the close approaches.  This script computes it from
the channel's own history, conditioned on how deep the global queue is, which is
the only covariate that has ever predicted sojourn on this feed (contention, not
compute: benchmark_wall_seconds has median 46 s against 17-113 min sojourns).

Two estimators, deliberately:

  * COMPLETED-ONLY -- the empirical CDF of sojourns among rows that finished.
    This is optimistically biased at high depth, because the slow rows created
    recently are still resident and so contribute no sojourn.  It is the number
    an unwary reader would compute.
  * KAPLAN-MEIER -- treats every still-`validating` row as right-censored at its
    current age, which is exactly what it is.  This is the honest one.

Reporting both, and their gap, is the point: if they disagree the campaign
should plan on the KM number, and the size of the disagreement measures how much
of the current queue is unresolved tail.

Read-only: reads a saved snapshot from disk, issues no API call, fires nothing.

usage: r129q_adjudication_odds.py <snapshot.json> [--depth 12] [--close 17:00]
"""
import argparse
import datetime as dt
import json
import statistics
import sys

TERMINAL = {"rejected", "failed", "accepted", "promoted"}
US = "morganmcg1"
P_WIN_LO, P_WIN_HI = 0.015, 0.020   # per-draw crown probability, ledger 11.4


def ts(s):
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


def load(path):
    with open(path) as f:
        doc = json.load(f)
    rows = doc["submissions"]
    asof = ts(doc["polled_at"]) if "polled_at" in doc else max(
        ts(r["updatedAt"]) for r in rows)
    return rows, asof


def depth_at(rows, asof):
    """For each row: (depth at its creation, sojourn or age, censored?)."""
    spans = []
    for r in rows:
        a = ts(r["createdAt"])
        term = r.get("status") in TERMINAL
        b = ts(r["updatedAt"]) if term else asof
        spans.append((a, b, term, r))
    out = []
    for a, b, term, r in spans:
        k = sum(1 for (a2, b2, _t2, r2) in spans
                if r2 is not r and a2 <= a < b2)
        dur = (b - a).total_seconds() / 60.0
        out.append((k, dur, not term, r))
    return out


def km_survival(obs):
    """Kaplan-Meier S(t) from [(duration, censored)]; returns step list."""
    events = sorted(obs, key=lambda x: x[0])
    n = len(events)
    at_risk = n
    s = 1.0
    steps = [(0.0, 1.0)]
    i = 0
    while i < n:
        t = events[i][0]
        same = [e for e in events if e[0] == t]
        d = sum(1 for e in same if not e[1])
        if d and at_risk > 0:
            s *= (1 - d / at_risk)
            steps.append((t, s))
        at_risk -= len(same)
        i += len(same)
    return steps


def s_at(steps, t):
    s = 1.0
    for tt, ss in steps:
        if tt <= t:
            s = ss
        else:
            break
    return s


def completed_cdf(obs, t):
    done = [d for d, cens in obs if not cens]
    if not done:
        return float("nan")
    return sum(1 for d in done if d <= t) / len(done)


def bucket(rows, asof, kmin, days=None):
    data = depth_at(rows, asof)
    if days is not None:
        cut = asof - dt.timedelta(days=days)
        data = [x for x in data if ts(x[3]["createdAt"]) >= cut]
    return [(d, cens) for (k, d, cens, _r) in data if k >= kmin]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("snapshot")
    ap.add_argument("--depth", type=int, default=12,
                    help="current global in-flight depth")
    ap.add_argument("--close", default="17:00")
    ap.add_argument("--anchor", default="15:10",
                    help="expected flip time, anchor for the dawdle cost")
    a = ap.parse_args()

    rows, asof = load(a.snapshot)
    hh, mm = (int(x) for x in a.close.split(":"))
    close = asof.replace(hour=hh, minute=mm, second=0, microsecond=0)
    print(f"snapshot {a.snapshot}")
    print(f"rows {len(rows)}   as-of {asof.isoformat()}   close {close.isoformat()}")

    live = [r for r in rows if r.get("status") not in TERMINAL]
    ours = [r for r in live if r.get("solverUsername") == US]
    print(f"live now: {len(live)} global, {len(ours)} ours "
          f"({[r['id'][:8] for r in ours]})")
    ages = sorted(round((asof - ts(r["createdAt"])).total_seconds() / 60, 1)
                  for r in live)
    print(f"resident ages (min): {ages}")

    for kmin in (max(0, a.depth - 4), a.depth - 2, a.depth):
        obs = bucket(rows, asof, kmin)
        done = [d for d, c in obs if not c]
        cens = [d for d, c in obs if c]
        if len(done) < 10:
            print(f"\n== depth >= {kmin}: only {len(done)} completed, skipped ==")
            continue
        steps = km_survival(obs)
        print(f"\n== rows admitted at global depth >= {kmin}: "
              f"n={len(obs)} ({len(done)} completed, {len(cens)} censored) ==")
        print(f"  completed-only sojourn median {statistics.median(done):.1f} min, "
              f"p90 {sorted(done)[int(0.9*(len(done)-1))]:.1f} min")
        km_med = next((t for t, s in steps if s <= 0.5), None)
        print(f"  KM median {km_med if km_med else 'beyond observation'}")
        print(f"  {'fire at':>8} {'budget':>7} {'P(adj) completed':>17} "
              f"{'P(adj) KM':>10} {'E[crown] KM':>13}")
        t = close - dt.timedelta(minutes=125)
        while t <= close - dt.timedelta(minutes=20):
            budget = (close - t).total_seconds() / 60.0
            p_c = completed_cdf(obs, budget)
            p_km = 1.0 - s_at(steps, budget)
            print(f"  {t.strftime('%H:%MZ'):>8} {budget:>6.0f}m "
                  f"{100*p_c:>16.1f}% {100*p_km:>9.1f}% "
                  f"{100*P_WIN_LO*p_km:>6.2f}-{100*P_WIN_HI*p_km:.2f}%")
            t += dt.timedelta(minutes=10)

    # headline bucket: deep enough to be like today, wide enough to estimate
    kmin = max(0, a.depth - 2)
    obs = bucket(rows, asof, kmin)
    if len([d for d, c in obs if not c]) >= 10:
        steps = km_survival(obs)
        hh2, mm2 = (int(x) for x in a.anchor.split(":"))
        anchor = close.replace(hour=hh2, minute=mm2)
        print(f"\n== fine grid around the cliff (depth >= {kmin}) ==")
        t = anchor
        while t <= close - dt.timedelta(minutes=30):
            budget = (close - t).total_seconds() / 60.0
            p = 1 - s_at(steps, budget)
            print(f"  fire {t.strftime('%H:%MZ')}  budget {budget:>4.0f}m  "
                  f"P(adjudicated) {100*p:>5.1f}%")
            t += dt.timedelta(minutes=5)
        print(f"\n== cost of dawdling, anchored at the expected flip "
              f"{anchor.strftime('%H:%MZ')} (depth >= {kmin}) ==")
        b0 = (close - anchor).total_seconds() / 60.0
        p0 = 1 - s_at(steps, b0)
        for delay in (5, 10, 20, 30, 45):
            p1 = 1 - s_at(steps, b0 - delay)
            print(f"  waiting {delay:>2} min past the flip: P(adjudicated) "
                  f"{100*p0:.1f}% -> {100*p1:.1f}%, i.e. -{100*(p0-p1):.1f} pts "
                  f"= -{100*P_WIN_HI*(p0-p1):.3f} pts of crown probability")
        for thresh in (0.9, 0.8, 0.5):
            latest = None
            t = anchor
            while t <= close:
                if 1 - s_at(steps, (close - t).total_seconds() / 60.0) >= thresh:
                    latest = t
                t += dt.timedelta(minutes=1)
            print(f"  latest fire with P(adjudicated) >= {thresh:.0%}: "
                  f"{latest.strftime('%H:%MZ') if latest else 'already past'}")
    print("\nCAVEAT: depth is measured at CREATION; a row fired now also meets "
          "whatever arrives later, and depth has been climbing ~0.12 rows/min, "
          "so even the KM column is mildly optimistic for a fire made today.")


if __name__ == "__main__":
    sys.exit(main())
