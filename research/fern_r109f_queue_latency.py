#!/usr/bin/env python3
"""fern_r109f_queue_latency.py -- how long does the ranked queue actually take?

The single-slot-per-account rule means a submission's *wall* cost is not the
validation time, it is the validation time of whatever is already in flight.
On a saturated channel that number is the whole planning constraint: it sets how
many shots a campaign can physically fire before a deadline, and it sets how
long a "submit when the slot frees" poller has to be allowed to live.

This script measures it from the public receipt list, three ways:

1. **Concurrency** -- how many rows are non-terminal right now, and how long the
   oldest of them has been waiting. If this is climbing, the queue is backing up
   and every planned shot just got more expensive.
2. **Per-account gap** -- for the account that owns this campaign's slot, the
   observed gap between consecutive `createdAt` values. Because the account is
   limited to one in flight, that gap *is* the realised end-to-end latency, and
   it is the number to plan with.
3. **Trend** -- the same gap bucketed by hour, so a backing-up queue is visible
   as a rising series rather than as one alarming instant.

Usage:
    python3 research/fern_r109f_queue_latency.py [--cache /tmp/subs_p11.json]
                                                 [--solver morganmcg1]
                                                 [--hours 12]
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import statistics as st
import sys

CACHES = [
    "/tmp/subs_p11.json",
    "/tmp/subs_p10.json",
    "/tmp/subs_p9.json",
    "/tmp/subs_p8.json",
    "research/artifacts/fern-r109f/receipts/submissions.json",
]

TERMINAL = {"rejected", "failed", "accepted", "cancelled"}


def parse(ts: str) -> dt.datetime:
    return dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))


def load(cache: str | None) -> tuple[list[dict], str]:
    for path in [cache] if cache else CACHES:
        if path and os.path.exists(path):
            with open(path) as fh:
                blob = json.load(fh)
            rows = blob["submissions"] if isinstance(blob, dict) else blob
            return rows, path
    sys.exit("no receipt cache found")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache")
    ap.add_argument("--solver", default="morganmcg1")
    ap.add_argument("--hours", type=int, default=12)
    ap.add_argument("--deadline", default="2026-08-11T20:00:00Z")
    ap.add_argument("--p-shot", type=float, default=0.004847,
                    help="empirical p(crown) per shot for the shipped class")
    args = ap.parse_args()

    rows, src = load(args.cache)
    rows = [r for r in rows if r.get("createdAt")]
    rows.sort(key=lambda r: r["createdAt"])
    now = parse(rows[-1]["createdAt"])
    print(f"source: {src}  rows={len(rows)}  newest createdAt={rows[-1]['createdAt']}")

    # ---- 1. concurrency ------------------------------------------------
    live = [r for r in rows if (r.get("status") or "").lower() not in TERMINAL]
    print()
    print(f"=== in-flight right now: {len(live)} ===")
    print(f"{'id':10s} {'solver':16s} {'status':11s} {'createdAt':26s} {'age min':>8s}")
    for r in live:
        age = (now - parse(r["createdAt"])).total_seconds() / 60
        print(
            f"{r['id'][:8]:10s} {str(r.get('solverUsername'))[:16]:16s} "
            f"{str(r.get('status')):11s} {r['createdAt']:26s} {age:8.1f}"
        )
    if live:
        oldest = min(parse(r["createdAt"]) for r in live)
        print(f"oldest in flight has been waiting {(now - oldest).total_seconds() / 60:.1f} min")
        print("(ages are measured against the newest createdAt in the cache, so they")
        print(" are lower bounds on true wall age.)")

    # ---- 2. per-account realised latency -------------------------------
    mine = [r for r in rows if r.get("solverUsername") == args.solver]
    print()
    print(f"=== realised end-to-end latency for account {args.solver!r} ===")
    print(f"receipts: {len(mine)}")
    gaps = []
    for a, b in zip(mine, mine[1:]):
        g = (parse(b["createdAt"]) - parse(a["createdAt"])).total_seconds() / 60
        if 0 < g < 24 * 60:
            gaps.append((g, a["createdAt"], b["id"][:8]))
    if gaps:
        vals = [g for g, _, _ in gaps]
        vals_s = sorted(vals)
        print(f"  consecutive createdAt gaps, n={len(vals)}")
        print(f"    median {st.median(vals):7.2f} min")
        print(f"    mean   {st.fmean(vals):7.2f} min")
        print(f"    p10    {vals_s[len(vals_s) // 10]:7.2f} min")
        print(f"    p90    {vals_s[9 * len(vals_s) // 10]:7.2f} min")
        print(f"    min    {vals_s[0]:7.2f} min")
        print(f"    max    {vals_s[-1]:7.2f} min")
        print("  because this account is capped at 1 in flight, the gap is the")
        print("  realised cost of one shot including queue wait.")
        recent = [g for g, ts, _ in gaps if (now - parse(ts)).total_seconds() <= args.hours * 3600]
        if recent:
            print(f"  last {args.hours} h only: n={len(recent)} median {st.median(recent):.2f} min "
                  f"max {max(recent):.2f} min")

    # ---- 3. trend ------------------------------------------------------
    print()
    print(f"=== queue trend, last {args.hours} h (all solvers) ===")
    print(f"{'hour (UTC)':14s} {'created':>8s} {'terminal by cache':>18s} {'still live':>11s}")
    cutoff = now - dt.timedelta(hours=args.hours)
    buckets: dict[str, list[dict]] = {}
    for r in rows:
        t = parse(r["createdAt"])
        if t >= cutoff:
            buckets.setdefault(t.strftime("%Y-%m-%d %H"), []).append(r)
    for hour in sorted(buckets):
        b = buckets[hour]
        nlive = sum(1 for r in b if (r.get("status") or "").lower() not in TERMINAL)
        print(f"{hour:14s} {len(b):8d} {len(b) - nlive:18d} {nlive:11d}")
    print()
    print("A rising 'still live' column at the bottom of this table is the queue")
    print("backing up.  When it does, a submit-when-free poller needs a longer")
    print("--max-wait than the historical per-account gap suggests, and the number")
    print("of shots left before a deadline has to be recomputed downward.")

    # ---- 4. shot budget to the deadline --------------------------------
    if not gaps:
        return
    vals = sorted(g for g, _, _ in gaps)
    med = st.median(vals)
    p90 = vals[9 * len(vals) // 10]
    deadline = parse(args.deadline)
    minutes_left = (deadline - now).total_seconds() / 60
    print()
    print(f"=== shot budget to {args.deadline} ===")
    print(f"  wall minutes remaining (from newest createdAt) {minutes_left:.0f}")
    print(f"{'per-shot latency':28s} {'shots':>7s} {'P(crown) at':>13s} {'P(crown) at':>13s}")
    print(f"{'':28s} {'':>7s} {args.p_shot:>12.4f} {args.p_shot / 3:>12.4f}")
    for label, lat in (
        ("median observed", med),
        ("last-window median", st.median([g for g, ts, _ in gaps
                                          if (now - parse(ts)).total_seconds() <= args.hours * 3600]
                                         or vals)),
        ("p90 observed (congested)", p90),
        ("oldest-in-flight age now", (now - min((parse(r["createdAt"]) for r in live), default=now)
                                      ).total_seconds() / 60 or med),
    ):
        n = int(minutes_left // lat) if lat > 0 else 0
        pc = 1.0 - (1.0 - args.p_shot) ** n
        pc3 = 1.0 - (1.0 - args.p_shot / 3) ** n
        print(f"{label:28s} {n:7d} {pc * 100:12.1f}% {pc3 * 100:12.1f}%")
    print()
    print(f"  p/shot {args.p_shot:.4f} is this campaign's atlas-v3 class figure: the")
    print("  empirical fraction of full-leg receipts whose draw factor is large")
    print("  enough to lift the class mean over the crown.  The right-hand column")
    print("  divides it by 3 for the honest reason that the single account slot is")
    print("  SHARED with the advisor and the other maple students, so this campaign")
    print("  does not get every shot in the window.")
    print("  Read together with the elasticity table: no achievable code delta")
    print("  changes these numbers as much as simply having more shots does, which")
    print("  is why a congested queue is a strategic event and not an annoyance.")


if __name__ == "__main__":
    main()
