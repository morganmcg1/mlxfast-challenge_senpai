#!/usr/bin/env python3
"""Two corrections to my own contention curve, both found at 12:52Z when the
observed queue jumped from 6 to 9 rows in flight in seven minutes.

1. My published curve clamps at "6+", so it mixes inflight 6 with inflight 12.
   In an endgame rush that is exactly the regime everyone will fire into, so the
   clamp has to be opened up: estimate per-k for k = 6,7,8,9,10+.

2. inflight is not a constant of the day -- it is rising as the field rushes the
   close. A single "last safe fire" clock value is therefore still wrong, even
   as a lookup, unless you price the inflight you will MEET, not the inflight you
   see. This script measures the arrival-rate trend and reports a forecast-based
   last safe fire.

Read-only: consumes cached snapshots, issues no requests, creates no submission.

Usage: python3 research/fern_r109f_endgame_rush.py <queue.json> [more.json ...]
"""
import bisect
import datetime
import json
import statistics
import sys

TERMINAL = {"rejected", "failed", "accepted", "promoted", "completed", "error"}
CLOSE = datetime.datetime(2026, 8, 11, 17, 0, tzinfo=datetime.timezone.utc)


def P(ts):
    return datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))


def load(paths):
    best = {}
    for p in paths:
        doc = json.load(open(p))
        rows = doc["submissions"] if isinstance(doc, dict) else doc
        for r in rows:
            prev = best.get(r["id"])
            if prev is None or (str(prev.get("status", "")).lower() not in TERMINAL
                               and str(r.get("status", "")).lower() in TERMINAL):
                best[r["id"]] = r
    return list(best.values())


def q(vals, p):
    v = sorted(vals)
    return v[min(len(v) - 1, int(p * len(v)))] if v else float("nan")


def main():
    paths = sys.argv[1:] or ["research/fern-r109f-queue-1255Z.json"]
    rows = load(paths)

    recs = []
    for r in rows:
        c = r.get("createdAt")
        if not c:
            continue
        term = str(r.get("status", "")).lower() in TERMINAL
        u = r.get("updatedAt")
        recs.append(dict(id=r["id"][:8], user=r.get("solverUsername"),
                        c=P(c), u=P(u) if (term and u) else None, term=term))
    recs.sort(key=lambda x: x["c"])
    starts = [x["c"] for x in recs]

    def inflight_at(t, exclude=None):
        """rows created at/before t that had not terminated by t"""
        n = 0
        for x in recs[:bisect.bisect_right(starts, t)]:
            if x is exclude:
                continue
            if x["u"] is None or x["u"] > t:
                n += 1
        return n

    # ---------- 1. open up the 6+ clamp ----------
    obs = []
    for x in recs:
        if not x["term"] or x["u"] is None:
            continue
        soj = (x["u"] - x["c"]).total_seconds() / 60.0
        if soj < 0:
            continue
        obs.append((inflight_at(x["c"], exclude=x), soj, x))

    print(f"terminal rows with observed sojourn: {len(obs)}")
    print("\n=== sojourn by EXACT rows-in-flight at creation (clamp opened) ===")
    print(f"{'inflight':>9} {'n':>5} {'median':>8} {'p90':>8} {'last_safe_fire':>15}")
    curve = {}
    for k in list(range(0, 10)) + ["10+"]:
        if k == "10+":
            sel = [s for kk, s, _ in obs if kk >= 10]
        else:
            sel = [s for kk, s, _ in obs if kk == k]
        if len(sel) < 5:
            print(f"{str(k):>9} {len(sel):>5} {'(too few)':>8}")
            continue
        med, p90 = statistics.median(sel), q(sel, 0.90)
        curve[k] = (med, p90)
        lsf = (CLOSE - datetime.timedelta(minutes=p90)).strftime("%H:%MZ")
        print(f"{str(k):>9} {len(sel):>5} {med:8.1f} {p90:8.1f} {lsf:>15}")

    # ---------- 2. is inflight rising? (the endgame rush) ----------
    print("\n=== arrivals and concurrency through the day (UTC, 30-min bins) ===")
    day0 = datetime.datetime(2026, 8, 11, 0, 0, tzinfo=datetime.timezone.utc)
    latest = max(x["c"] for x in recs)
    print(f"{'bin':>8} {'arrivals':>9} {'inflight@end':>13}")
    b = day0
    while b < latest:
        nxt = b + datetime.timedelta(minutes=30)
        n = sum(1 for x in recs if b <= x["c"] < nxt)
        if n or b > latest - datetime.timedelta(hours=6):
            print(f"{b.strftime('%H:%M'):>8} {n:>9} {inflight_at(nxt):>13}")
        b = nxt

    # arrival rate over the last 30/60/120 min, and its trend
    print("\n=== arrival rate (rows/min) ===")
    for win in (30, 60, 120, 240):
        lo = latest - datetime.timedelta(minutes=win)
        n = sum(1 for x in recs if x["c"] >= lo)
        print(f"  last {win:>3}m: {n:>4} rows -> {n / win:5.3f}/min")

    # ---------- 3. forecast-based last safe fire ----------
    # If arrivals continue at the recent rate and service keeps up only as well
    # as it has, the inflight a shot MEETS is the current inflight plus whatever
    # the field adds while it waits. Price the pessimistic tail we can observe.
    now_inflight = inflight_at(latest)
    print(f"\ninflight at latest observation ({latest.strftime('%H:%M:%SZ')}): {now_inflight}")
    worst = max(curve, key=lambda k: curve[k][1] if k != "10+" else 1e9)
    k_key = "10+" if now_inflight >= 10 else min(now_inflight, max(
        [k for k in curve if k != "10+"]))
    if k_key in curve:
        med, p90 = curve[k_key]
        budget = (CLOSE - latest).total_seconds() / 60.0
        print(f"a shot fired now meets inflight~{now_inflight} -> median {med:.1f}m, p90 {p90:.1f}m")
        print(f"budget to 17:00Z = {budget:.1f}m -> "
              f"{'SAFE' if budget > p90 else 'UNSAFE'} at p90")
        print(f"last safe fire at THIS concurrency = "
              f"{(CLOSE - datetime.timedelta(minutes=p90)).strftime('%H:%MZ')}")
    print("\nNOTE: because inflight is rising, the honest rule is to re-price at "
          "fire time and prefer the p90 of the NEXT-WORSE bucket as the margin.")

    # ---------- 4. our own account's live rows, out-of-sample check ----------
    print("\n=== our account's rows, latest 6 ===")
    ours = [x for x in recs if x["user"] == "morganmcg1"][-6:]
    for x in ours:
        k = inflight_at(x["c"], exclude=x)
        if x["u"]:
            soj = (x["u"] - x["c"]).total_seconds() / 60.0
            pred = curve.get("10+" if k >= 10 else k)
            ps = f" predicted med {pred[0]:.1f} p90 {pred[1]:.1f}" if pred else ""
            print(f"  {x['id']} created {x['c'].strftime('%H:%M:%SZ')} inflight={k:>2} "
                  f"sojourn={soj:6.1f}m{ps}")
        else:
            age = (latest - x["c"]).total_seconds() / 60.0
            pred = curve.get("10+" if k >= 10 else k)
            ps = (f" predicted med {pred[0]:.1f} p90 {pred[1]:.1f} -> due "
                  f"{(x['c'] + datetime.timedelta(minutes=pred[0])).strftime('%H:%MZ')}"
                  f"/p90 {(x['c'] + datetime.timedelta(minutes=pred[1])).strftime('%H:%MZ')}"
                  if pred else "")
            print(f"  {x['id']} created {x['c'].strftime('%H:%M:%SZ')} inflight={k:>2} "
                  f"LIVE age={age:6.1f}m{ps}")


if __name__ == "__main__":
    main()
