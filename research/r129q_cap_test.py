#!/usr/bin/env python3
"""R129-Q part 2: give the "no overlap" negative real statistical power.

Offline; reads a snapshot already on disk. No network, no submission.

If per-account admission were UNCONSTRAINED, the gap between one fire and the
next would be set by the driver's own cadence and would sometimes be SHORTER
than the previous row's sojourn (i.e. fire while the previous row is still in
flight) -> negative reaction time. If a hard cap of one in flight is enforced,
reaction = gap - sojourn is strictly >= 0 with a spike just above 0 (drivers
that re-fire as soon as they are allowed).

Usage: research/r129q_cap_test.py <snapshot.json>
"""
from __future__ import annotations

import datetime as dt
import json
import statistics
import sys

US = "morganmcg1"
TERMINAL = {"rejected", "failed", "accepted", "promoted"}
CLOSE = dt.datetime(2026, 8, 11, 17, 0, 0, tzinfo=dt.timezone.utc)


def ts(s: str) -> dt.datetime:
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


def main(argv: list[str]) -> int:
    blob = json.load(open(argv[0]))
    rows = blob["submissions"]
    polled = blob.get("polled_at", "unknown")
    print(f"snapshot {argv[0]}  n={len(rows)}  polled_at={polled}")

    per: dict[str, list[dict]] = {}
    for r in rows:
        per.setdefault(r.get("solverUsername") or "<none>", []).append(r)

    print("\n=== REACTION TIME  r_i = gap(fire_i -> fire_i+1) - sojourn_i  [min] ===")
    allr: list[float] = []
    ourr: list[float] = []
    neg = 0
    for who, rs in per.items():
        rs = sorted([x for x in rs if x.get("status") in TERMINAL],
                    key=lambda x: x["createdAt"])
        for i in range(len(rs) - 1):
            soj = (ts(rs[i]["updatedAt"]) - ts(rs[i]["createdAt"])).total_seconds() / 60.0
            gap = (ts(rs[i + 1]["createdAt"]) - ts(rs[i]["createdAt"])).total_seconds() / 60.0
            r = gap - soj
            allr.append(r)
            if who == US:
                ourr.append(r)
            if r < 0:
                neg += 1
    allr.sort()
    n = len(allr)
    print(f"  consecutive fire pairs across all 89 accounts: n={n}")
    print(f"  NEGATIVE reaction times (fired before own previous row went "
          f"terminal): {neg}  = {100.0*neg/n:.3f}%")
    for lo, hi in ((0, 1), (0, 2), (0, 5), (0, 10)):
        k = sum(1 for x in allr if lo <= x < hi)
        print(f"  reaction in [{lo},{hi}) min: {k:5d}  {100.0*k/n:5.1f}%")
    print(f"  reaction percentiles: p1 {allr[int(0.01*(n-1))]:.2f}  "
          f"p5 {allr[int(0.05*(n-1))]:.2f}  p25 {allr[int(0.25*(n-1))]:.2f}  "
          f"median {statistics.median(allr):.2f}  p75 {allr[int(0.75*(n-1))]:.2f}")
    print(f"  min reaction observed: {allr[0]:.3f} min")
    ourr.sort()
    if ourr:
        print(f"  OUR account n={len(ourr)}: min {ourr[0]:.2f}  p5 "
              f"{ourr[int(0.05*(len(ourr)-1))]:.2f}  median "
              f"{statistics.median(ourr):.2f}  frac in [0,2) "
              f"{100.0*sum(1 for x in ourr if 0 <= x < 2)/len(ourr):.1f}%")
    print("  => a hard floor at 0 with a mass immediately above it is the "
          "signature of an enforced one-in-flight cap; an unconstrained channel "
          "would show negatives.")

    print("\n=== OUR SOJOURN BY CREATION HOUR, 2026-08-11 (congestion trend) ===")
    ours = sorted([r for r in per.get(US, []) if r["createdAt"].startswith("2026-08-11")],
                  key=lambda r: r["createdAt"])
    for r in ours:
        a = ts(r["createdAt"])
        term = r.get("status") in TERMINAL
        b = ts(r["updatedAt"]) if term else None
        soj = (b - a).total_seconds() / 60.0 if term else None
        print(f"  {r['id'][:8]}  created {a.strftime('%H:%M:%SZ')}  "
              f"{'terminal ' + b.strftime('%H:%M:%SZ') if term else 'IN FLIGHT':22s}  "
              f"sojourn {soj:6.1f} min" if term else
              f"  {r['id'][:8]}  created {a.strftime('%H:%M:%SZ')}  IN FLIGHT"
              f"              sojourn      ? min   status={r.get('status')}")
    done = [((ts(r['updatedAt']) - ts(r['createdAt'])).total_seconds() / 60.0,
             ts(r['createdAt'])) for r in ours if r.get("status") in TERMINAL]
    for lo, hi, label in ((0, 8, "00:00-08:00Z"), (8, 12, "08:00-12:00Z"),
                          (12, 24, "12:00Z+")):
        w = [s for s, c in done if lo <= c.hour < hi]
        if w:
            print(f"  window {label}: n={len(w)} median {statistics.median(w):.1f} "
                  f"max {max(w):.1f} min")

    print("\n=== DRAWS REMAINING under SERIAL + cap=1 ===")
    live = [r for r in rows if r.get("status") not in TERMINAL]
    mine_live = [r for r in live if r.get("solverUsername") == US]
    poll = ts(polled) if polled != "unknown" else ts(rows[0]["createdAt"])
    for r in mine_live:
        a = ts(r["createdAt"])
        print(f"  our in-flight row {r['id'][:8]} created {a.strftime('%H:%M:%SZ')} "
              f"age {(poll-a).total_seconds()/60.0:.1f} min at poll")
        for label, budget in (("morning median 20.8", 20.8),
                              ("5fae2f13 live 46.3", 46.3),
                              ("last-6h median 82.8", 82.8),
                              ("last-6h max 99.4", 99.4)):
            free = a + dt.timedelta(minutes=budget)
            lastfire = CLOSE - dt.timedelta(minutes=budget)
            extra = 1 + int((lastfire - free).total_seconds() // (budget * 60)) \
                if free <= lastfire else 0
            print(f"    budget {label:22s} -> channel free "
                  f"{free.strftime('%H:%M:%SZ')}, last safe fire "
                  f"{lastfire.strftime('%H:%M:%SZ')}, further draws after this "
                  f"one: {extra}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
