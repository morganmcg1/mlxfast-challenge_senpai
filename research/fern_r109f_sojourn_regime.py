#!/usr/bin/env python3
"""Is the queue slow-down a trend or a contention effect? And how many draws remain?

Our own account's sojourn was 22.1-23.2 min for thirteen consecutive rows and then
jumped to 29.6 / 82.8 / 99.4 min.  Two competing explanations with different
operational consequences:

  (A) TIME TREND  - the validator is degrading as the 17:00Z close approaches
                    (everyone piles in).  Then it will keep getting worse and the
                    effective deadline moves EARLIER than the raw quantiles say.
  (B) CONTENTION  - sojourn is a function of how many rows are in flight when a
                    row is created.  Then it is predictable from observable state,
                    and we can price a shot at fire time instead of guessing.

This script regresses observed sojourn on concurrency-at-creation to separate them,
then converts the answer into remaining draws and remaining crown probability.

Usage: python3 research/fern_r109f_sojourn_regime.py <queue.json> [asof_iso]
"""
import datetime
import json
import sys

TERMINAL = {"rejected", "failed", "accepted", "promoted", "completed", "error"}
OURS = "morganmcg1"
CLOSE = "2026-08-11T17:00:00Z"

# per-draw probability of clearing the bar, from the draw-variance model:
# need multiplier 2.6195531/2.582263 = 1.014441, draw sd 0.538% => z=2.344
P_PER_DRAW = 0.0148


def parse(ts):
    return datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "research/fern-r109f-queue-1222Z.json"
    doc = json.load(open(path))
    rows = doc["submissions"] if isinstance(doc, dict) else doc
    asof = parse(sys.argv[2]) if len(sys.argv) > 2 else max(
        parse(r["updatedAt"]) for r in rows if r.get("updatedAt"))

    recs = []
    for r in rows:
        c, u = r.get("createdAt"), r.get("updatedAt")
        if not c or not u:
            continue
        term = str(r.get("status", "")).lower() in TERMINAL
        recs.append(dict(
            id=r["id"][:8], user=r.get("solverUsername"), term=term,
            c=parse(c), u=parse(u) if term else None,
        ))

    def concurrency_at(t):
        """rows created before t and still non-terminal at t"""
        n = 0
        for x in recs:
            if x["c"] <= t and (x["u"] is None or x["u"] > t):
                n += 1
        return n - 1  # exclude the row itself

    done = [x for x in recs if x["term"]]
    for x in done:
        x["soj"] = (x["u"] - x["c"]).total_seconds() / 60.0
        x["conc"] = concurrency_at(x["c"])

    print("== (B) contention: sojourn vs rows in flight at creation (all accounts) ==")
    buckets = {}
    for x in done:
        if x["soj"] <= 0:
            continue
        k = min(x["conc"], 6)
        buckets.setdefault(k, []).append(x["soj"])
    for k in sorted(buckets):
        v = sorted(buckets[k])
        med = v[len(v) // 2]
        p90 = v[min(len(v) - 1, int(0.9 * len(v)))]
        print(f"  inflight={k}{'+' if k==6 else ' '}  n={len(v):4d}  median={med:6.1f}  "
              f"p90={p90:6.1f}  mean={sum(v)/len(v):6.1f}")

    print("\n== (A) time trend: our account's sojourn by hour of 8/11 ==")
    mine = sorted((x for x in done if x["user"] == OURS
                   and x["c"] >= asof - datetime.timedelta(hours=14)),
                  key=lambda x: x["c"])
    for x in mine:
        print(f"  {x['c'].strftime('%H:%M')}Z  inflight={x['conc']:2d}  sojourn={x['soj']:6.1f}m  {x['id']}")

    # regime estimates
    base = [x["soj"] for x in done if x["user"] == OURS and x["conc"] <= 2 and x["soj"] > 0]
    busy = [x["soj"] for x in done if x["conc"] >= 5 and x["soj"] > 0]
    def q(v, p):
        v = sorted(v)
        return v[min(len(v) - 1, int(p * len(v)))] if v else float("nan")
    print(f"\n  QUIET regime (ours, inflight<=2): n={len(base)} median={q(base,.5):.1f} p90={q(base,.9):.1f}")
    print(f"  BUSY  regime (any,  inflight>=5): n={len(busy)} median={q(busy,.5):.1f} p90={q(busy,.9):.1f}")

    print("\n== remaining draws and crown probability, by regime ==")
    close = parse(CLOSE)
    now = asof
    # a draw costs (service + ~1.5 min refire latency); serialized per account
    for label, svc in [("quiet 22.7m", 22.7), ("observed-recent 29.6m", 29.6),
                       ("busy median 62.1m", 62.1), ("busy p90 99.4m", 99.4)]:
        cycle = svc + 1.5
        # first draw already in flight: assume it terminates after svc from 12:17Z
        first_done = parse("2026-08-11T12:16:59Z") + datetime.timedelta(minutes=svc)
        t = max(now, first_done)
        n = 1  # the live row counts as a draw
        while t + datetime.timedelta(minutes=svc) <= close:
            n += 1
            t = t + datetime.timedelta(minutes=cycle)
        p = 1 - (1 - P_PER_DRAW) ** n
        # latest fire time that still lands
        last = close - datetime.timedelta(minutes=svc)
        print(f"  service={label:<22} draws={n:2d}  last_safe_fire={last.strftime('%H:%M')}Z  "
              f"P(crown)={p*100:5.2f}%")


if __name__ == "__main__":
    main()
