#!/usr/bin/env python3
"""Direct (not Kaplan-Meier) sojourn measurement for the official validation queue.

WHY THIS SUPERSEDES research/fern_r109f_sojourn_km.py
-----------------------------------------------------
My KM estimator treated terminal times as unobservable and reconstructed the
sojourn distribution from creation times plus right-censoring.  That was
unnecessary: every row in the queue listing carries BOTH `createdAt` and
`updatedAt`, and for a terminal row `updatedAt` IS the terminal timestamp.
So the sojourn is *directly observed*, per row, with no censoring model,
no inspection paradox and no length bias.

It also fixes a second, larger error: POPULATION.  The listing is global
(many solver accounts).  Rows from different accounts validate CONCURRENTLY
-- six were `validating` simultaneously at 12:22Z -- so the queue is NOT a
single global serial server.  The constraint that binds us is per-account:
at most one non-terminal submission per account.  Therefore the quantity
that prices our fire/no-fire decision is the sojourn of OUR OWN rows,
not the global pool.  Pooling other accounts' rows inflates it.

Usage:  python3 research/fern_r109f_sojourn_direct.py <queue.json> [asof_iso]
"""
import datetime
import json
import sys

TERMINAL = {"rejected", "failed", "accepted", "promoted", "completed", "error"}
OURS = "morganmcg1"


def parse(ts):
    return datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))


def sojourn_min(row):
    """Observed sojourn in minutes for a terminal row, else None."""
    if str(row.get("status", "")).lower() not in TERMINAL:
        return None
    c, u = row.get("createdAt"), row.get("updatedAt")
    if not c or not u:
        return None
    v = (parse(u) - parse(c)).total_seconds() / 60.0
    return v if v > 0 else None


def quantiles(vals):
    v = sorted(vals)
    if not v:
        return None

    def q(p):
        return v[min(len(v) - 1, int(p * len(v)))]

    return dict(
        n=len(v), median=q(0.50), p75=q(0.75), p90=q(0.90),
        mean=sum(v) / len(v), mx=v[-1], mn=v[0],
    )


def report(label, vals):
    s = quantiles(vals)
    if not s:
        print(f"{label:<26} n=0")
        return
    print(
        f"{label:<26} n={s['n']:4d}  min={s['mn']:6.1f}  median={s['median']:6.1f}  "
        f"p75={s['p75']:6.1f}  p90={s['p90']:6.1f}  mean={s['mean']:6.1f}  max={s['mx']:7.1f}"
    )


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "research/fern-r109f-queue-1222Z.json"
    asof = parse(sys.argv[2]) if len(sys.argv) > 2 else None
    doc = json.load(open(path))
    rows = doc["submissions"] if isinstance(doc, dict) else doc
    if asof is None:
        asof = max(parse(r["updatedAt"]) for r in rows if r.get("updatedAt"))
    print(f"rows={len(rows)}  asof={asof.isoformat()}")

    all_s, our_s = [], []
    for r in rows:
        s = sojourn_min(r)
        if s is None:
            continue
        all_s.append(s)
        if r.get("solverUsername") == OURS:
            our_s.append(s)

    print("\n== observed sojourn, whole history ==")
    report("ALL accounts", all_s)
    report("ours (morganmcg1)", our_s)

    for hours in (24, 12, 6):
        cut = asof - datetime.timedelta(hours=hours)
        a = [sojourn_min(r) for r in rows
             if r.get("createdAt") and parse(r["createdAt"]) >= cut]
        o = [sojourn_min(r) for r in rows
             if r.get("solverUsername") == OURS and r.get("createdAt")
             and parse(r["createdAt"]) >= cut]
        print(f"\n== created within last {hours}h ==")
        report("ALL accounts", [x for x in a if x])
        report("ours (morganmcg1)", [x for x in o if x])

    # our recent rows, explicit, so the reader can audit every number
    cut = asof - datetime.timedelta(hours=12)
    mine = sorted(
        (r for r in rows if r.get("solverUsername") == OURS
         and r.get("createdAt") and parse(r["createdAt"]) >= cut),
        key=lambda r: r["createdAt"],
    )
    print("\n== our rows, last 12h (created -> updated = sojourn) ==")
    prev_created = None
    for r in mine:
        s = sojourn_min(r)
        gap = ""
        if prev_created is not None:
            gap = f"  gap_since_prev_create={(parse(r['createdAt']) - prev_created).total_seconds()/60:6.1f}m"
        prev_created = parse(r["createdAt"])
        print(
            f"  {r['id'][:8]}  {str(r['status']):<10}  created={r['createdAt']}  "
            f"updated={r.get('updatedAt')}  sojourn={('%6.1fm' % s) if s else '   LIVE'}{gap}"
        )

    # P(land before close) for our own service-time distribution
    print("\n== P(a shot fired at t reaches terminal before 17:00Z) : OUR sojourn ==")
    close = parse("2026-08-11T17:00:00Z")
    ref = [x for x in our_s if x]
    for hh, mm in [(13, 30), (14, 0), (14, 30), (15, 0), (15, 30), (16, 0), (16, 30), (16, 45)]:
        t = parse(f"2026-08-11T{hh:02d}:{mm:02d}:00Z")
        budget = (close - t).total_seconds() / 60.0
        if budget <= 0:
            continue
        p = sum(1 for x in ref if x <= budget) / len(ref)
        print(f"  fire {hh:02d}:{mm:02d}Z  budget={budget:5.1f}m  P(land)={p:5.3f}")


if __name__ == "__main__":
    main()
