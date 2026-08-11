#!/usr/bin/env python3
"""Is OUR account slower than the global field at equal contention?

Motivation: with the 6+ clamp opened, all five of our recent rows came in slower
than the global median for their inflight bucket, and two of the five beat the
global p90 for their bucket. If that is systematic, then the global lookup I
just published to the fleet is over-optimistic FOR US, and an over-optimistic
fire schedule is exactly as harmful as the over-pessimistic one I retracted.

Method: for every terminal row, compute exact rows-in-flight at creation and the
observed sojourn. Build the global median/p90 per bucket from rows that are NOT
ours, then score each of our rows as a ratio to its bucket's global median.
Ratios are compared against the same statistic computed for other heavy accounts,
so that "our account is slow" is tested against "every account looks slow when
scored this way".

Read-only: consumes cached snapshots only.

Usage: python3 research/fern_r109f_account_factor.py <queue.json> [more.json ...]
"""
import bisect
import collections
import datetime
import json
import statistics
import sys

TERMINAL = {"rejected", "failed", "accepted", "promoted", "completed", "error"}
OURS = "morganmcg1"
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


def bucket(k):
    return 10 if k >= 10 else k


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
        n = 0
        for x in recs[:bisect.bisect_right(starts, t)]:
            if x is exclude:
                continue
            if x["u"] is None or x["u"] > t:
                n += 1
        return n

    done = []
    for x in recs:
        if not x["term"] or x["u"] is None:
            continue
        soj = (x["u"] - x["c"]).total_seconds() / 60.0
        if soj >= 0:
            done.append(dict(k=inflight_at(x["c"], exclude=x), soj=soj,
                            user=x["user"], id=x["id"], c=x["c"]))

    # global reference built from rows that are NOT ours (no self-contamination)
    ref = collections.defaultdict(list)
    for d in done:
        if d["user"] != OURS:
            ref[bucket(d["k"])].append(d["soj"])
    gmed = {k: statistics.median(v) for k, v in ref.items() if len(v) >= 5}
    gp90 = {k: q(v, 0.90) for k, v in ref.items() if len(v) >= 5}

    print(f"terminal rows {len(done)}  ours {sum(1 for d in done if d['user']==OURS)}")
    print("\n=== global reference (rows NOT ours) ===")
    print(f"{'inflight':>9} {'n':>5} {'median':>8} {'p90':>8}")
    for k in sorted(gmed):
        print(f"{('10+' if k==10 else k)!s:>9} {len(ref[k]):>5} {gmed[k]:8.1f} {gp90[k]:8.1f}")

    def ratios(user):
        out = []
        for d in done:
            if d["user"] != user:
                continue
            b = bucket(d["k"])
            if b in gmed and gmed[b] > 0:
                out.append(d["soj"] / gmed[b])
        return out

    # how many of our rows exceed the global p90 of their own bucket?
    over90 = tot = 0
    for d in done:
        if d["user"] != OURS:
            continue
        b = bucket(d["k"])
        if b in gp90:
            tot += 1
            over90 += d["soj"] > gp90[b]

    r_ours = ratios(OURS)
    print(f"\n=== our account, ratio of sojourn to global median of same bucket ===")
    print(f"n={len(r_ours)}  median={statistics.median(r_ours):.3f}  "
          f"mean={statistics.fmean(r_ours):.3f}  p75={q(r_ours,0.75):.3f}  "
          f"p90={q(r_ours,0.90):.3f}")
    print(f"rows above the global p90 of their own bucket: {over90}/{tot} "
          f"({100.0*over90/max(tot,1):.1f}%)   [null expectation 10%]")

    # control: the same statistic for every other heavy account
    print("\n=== control: same ratio statistic for the busiest accounts ===")
    cnt = collections.Counter(d["user"] for d in done)
    print(f"{'account':<14} {'n':>5} {'median_ratio':>13} {'%>global p90':>13}")
    for user, n in cnt.most_common(12):
        rr = ratios(user)
        if len(rr) < 20:
            continue
        o = t = 0
        for d in done:
            if d["user"] != user:
                continue
            b = bucket(d["k"])
            if b in gp90:
                t += 1
                o += d["soj"] > gp90[b]
        tag = "  <== OURS" if user == OURS else ""
        print(f"{str(user):<14} {n:>5} {statistics.median(rr):>13.3f} "
              f"{100.0*o/max(t,1):>12.1f}%{tag}")

    # our own per-bucket numbers where we have samples
    print("\n=== our account per bucket (small n, shown for completeness) ===")
    ours_by_k = collections.defaultdict(list)
    for d in done:
        if d["user"] == OURS:
            ours_by_k[bucket(d["k"])].append(d["soj"])
    print(f"{'inflight':>9} {'n':>5} {'our med':>9} {'glob med':>9} {'our p90':>9}")
    for k in sorted(ours_by_k):
        v = ours_by_k[k]
        print(f"{('10+' if k==10 else k)!s:>9} {len(v):>5} {statistics.median(v):9.1f} "
              f"{gmed.get(k, float('nan')):9.1f} {q(v,0.90):9.1f}")

    # ---- what this does to OUR last safe fire ----
    print("\n=== our-account last safe fire (global p90 x our ratio tail) ===")
    tail = q(r_ours, 0.90)
    print(f"using our ratio p90 = {tail:.3f} applied to the global median per bucket")
    print(f"{'inflight':>9} {'our p90 est':>12} {'last safe fire':>15} {'(global-only)':>15}")
    for k in sorted(gmed):
        est = gmed[k] * tail
        lsf = (CLOSE - datetime.timedelta(minutes=est)).strftime("%H:%MZ")
        gonly = (CLOSE - datetime.timedelta(minutes=gp90[k])).strftime("%H:%MZ")
        print(f"{('10+' if k==10 else k)!s:>9} {est:12.1f} {lsf:>15} {gonly:>15}")


if __name__ == "__main__":
    main()
