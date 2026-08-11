#!/usr/bin/env python3
"""fern r109-f: per-row sojourn of the ranked validation channel.

The one-in-flight-per-account rule makes the *per-row sojourn* (updatedAt -
createdAt for a terminal row) the number that sets how many draws a campaign can
still fire before a deadline. This computes it from one cached read-only
snapshot of the public submissions collection -- no polling, no submission.

Two things it deliberately does NOT use:

* the head-of-line age. Rows from different accounts are in service
  concurrently (6 live rows, all `validating`, at 12:22Z), so the oldest live
  row is a straggler, not a queue head. Pricing our own wait off it
  over-estimates by ~4x.
* the per-account createdAt gap. That measures our own firing discipline
  (including idle time) rather than the channel's service time.

Usage: research/fern_r109f_sojourn.py <snapshot.json> [--hours 6] [--close 17:00]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import statistics as st

TERMINAL = {"completed", "failed", "accepted", "rejected", "cancelled", "error"}


def ts(s):
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00")) if s else None


def q(sorted_vals, p):
    if not sorted_vals:
        return float("nan")
    return sorted_vals[min(len(sorted_vals) - 1, int(p * len(sorted_vals)))]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("snapshot")
    ap.add_argument("--hours", type=float, default=6.0)
    ap.add_argument("--close", default="17:00")
    args = ap.parse_args()

    rows = json.load(open(args.snapshot))["submissions"]
    now = dt.datetime.now(dt.timezone.utc)
    hh, mm = (int(x) for x in args.close.split(":"))
    close = now.replace(hour=hh, minute=mm, second=0, microsecond=0)

    per_hour = {}
    pooled = []
    for r in rows:
        if r.get("status") not in TERMINAL:
            continue
        c, u = ts(r.get("createdAt")), ts(r.get("updatedAt"))
        if not c or not u:
            continue
        if (now - c).total_seconds() > args.hours * 3600:
            continue
        minutes = (u - c).total_seconds() / 60.0
        per_hour.setdefault(c.strftime("%H"), []).append(minutes)
        pooled.append(minutes)

    print(f"snapshot={args.snapshot}  read_at={now:%Y-%m-%dT%H:%M:%SZ}  rows={len(rows)}")
    print(f"\n=== per-row sojourn, terminal rows created in the last {args.hours:g} h ===")
    for k in sorted(per_hour):
        v = sorted(per_hour[k])
        print(f"  created {k}z: n={len(v):2d}  median {st.median(v):6.1f} min"
              f"  min {v[0]:5.1f}  max {v[-1]:6.1f}")
    pooled.sort()
    if pooled:
        print(f"  pooled: n={len(pooled)} median {st.median(pooled):.1f}"
              f" p75 {q(pooled, .75):.1f} p90 {q(pooled, .90):.1f} max {pooled[-1]:.1f} min")

    live = sorted((r for r in rows if r.get("status") not in TERMINAL),
                  key=lambda r: ts(r["createdAt"]))
    print(f"\n=== live rows now: {len(live)} (concurrent service, not a FIFO head) ===")
    for r in live:
        c = ts(r["createdAt"])
        print(f"  {r['id'][:8]} {str(r.get('solverUsername')):>11}"
              f" created {c:%H:%M:%SZ} age {(now - c).total_seconds()/60:6.1f} min")

    print(f"\n=== draw budget to close {close:%H:%MZ} (one in flight per account) ===")
    for lab, s in (("median", st.median(pooled) if pooled else 0),
                   ("p75", q(pooled, .75)), ("p90", q(pooled, .90))):
        last_fire = close - dt.timedelta(minutes=s)
        # serial chain of fires starting from the currently live row's ETA
        ours = [r for r in live if r.get("solverUsername") == "morganmcg1"]
        start = (ts(ours[0]["createdAt"]) + dt.timedelta(minutes=s)) if ours else now
        n, t = 0, start
        while t + dt.timedelta(minutes=s) <= close:
            n += 1
            t = t + dt.timedelta(minutes=s)
        print(f"  sojourn {lab:>6} {s:6.1f} min -> last fire {last_fire:%H:%MZ},"
              f" further draws after the live row: {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
