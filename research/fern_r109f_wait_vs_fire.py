#!/usr/bin/env python3
"""Fire now, or wait for the queue to drain?

Our account validates one row at a time, so draws are serial for us: the number
of draws left is (budget to close) / (sojourn per draw), and sojourn depends on
the contention we fire into. That creates a real decision: firing into inflight 9
costs ~61 min, but firing into a quiet queue costs ~17 min, so waiting could pay
for itself -- IF the queue actually drains, and waiting burns budget either way.

Break-even is simple: waiting w minutes to fire at contention j instead of firing
now at contention k pays iff

    w + sojourn(j) < sojourn(k)      i.e.   w < sojourn(k) - sojourn(j)

So the question is empirical: starting from contention k, how long does the queue
actually take to drain to j? This reconstructs inflight(t) on a one-minute grid
across the whole multi-day trace and measures the drain time directly.

Read-only: consumes cached snapshots only.

Usage: python3 research/fern_r109f_wait_vs_fire.py <queue.json> [more.json ...]
"""
import bisect
import collections
import datetime
import json
import statistics
import sys

TERMINAL = {"rejected", "failed", "accepted", "promoted", "completed", "error"}
CLOSE = datetime.datetime(2026, 8, 11, 17, 0, tzinfo=datetime.timezone.utc)
P_PER_DRAW = 0.0148

MED = {0: 16.8, 1: 17.9, 2: 24.5, 3: 30.7, 4: 40.0, 5: 43.0,
       6: 50.7, 7: 45.8, 8: 58.0, 9: 60.7, 10: 60.6}


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

    spans = []
    for r in rows:
        c = r.get("createdAt")
        if not c:
            continue
        term = str(r.get("status", "")).lower() in TERMINAL
        u = r.get("updatedAt")
        spans.append((P(c), P(u) if (term and u) else None))

    lo = min(s for s, _ in spans)
    hi = max(max((e for _, e in spans if e), default=lo),
             max(s for s, _ in spans))
    print(f"trace spans {lo.isoformat()} .. {hi.isoformat()} "
          f"({(hi - lo).total_seconds()/3600:.1f} h, {len(spans)} rows)")

    # inflight on a one-minute grid
    minutes = int((hi - lo).total_seconds() // 60) + 1
    delta = [0] * (minutes + 2)
    for s, e in spans:
        i = int((s - lo).total_seconds() // 60)
        delta[max(i, 0)] += 1
        if e is not None:
            j = int((e - lo).total_seconds() // 60)
            if 0 <= j <= minutes:
                delta[j] -= 1
    inflight, run = [], 0
    for d in delta[:minutes]:
        run += d
        inflight.append(run)

    print(f"inflight grid: mean {statistics.fmean(inflight):.2f}, "
          f"median {statistics.median(inflight)}, max {max(inflight)}")

    # occupancy histogram
    hist = collections.Counter(min(v, 10) for v in inflight)
    print("\n=== how much of the trace sits at each contention level ===")
    for k in sorted(hist):
        print(f"  inflight {('10+' if k==10 else k)!s:>3}: "
              f"{100.0*hist[k]/len(inflight):5.1f}% of minutes")

    # ---- drain time: from contention k, how long until <= target? ----
    print("\n=== drain time (minutes) from contention k down to a target ===")
    for target in (1, 2, 3):
        print(f"\n  target inflight <= {target}")
        print(f"  {'from k':>7} {'n':>6} {'median':>8} {'p25':>7} {'p75':>8} "
              f"{'never(%)':>9}")
        for k in range(target + 1, 11):
            waits, never = [], 0
            for i, v in enumerate(inflight):
                if (v if v < 10 else 10) != k:
                    continue
                j = i
                while j < len(inflight) and inflight[j] > target:
                    j += 1
                if j >= len(inflight):
                    never += 1
                else:
                    waits.append(j - i)
            n = len(waits) + never
            if n < 20:
                continue
            print(f"  {k:>7} {n:>6} {statistics.median(waits) if waits else float('inf'):>8.1f} "
                  f"{q(waits,0.25) if waits else float('inf'):>7.1f} "
                  f"{q(waits,0.75) if waits else float('inf'):>8.1f} "
                  f"{100.0*never/n:>8.1f}%")

    # ---- break-even table ----
    print("\n=== fire-now vs wait: break-even wait, and the drain time you'd need ===")
    print(f"{'from k':>7} {'sojourn(k)':>11} {'break-even w to reach<=2':>25} "
          f"{'median drain to<=2':>19} {'verdict':>10}")
    for k in range(3, 11):
        be = MED[k] - MED[2]
        waits, never = [], 0
        for i, v in enumerate(inflight):
            if (v if v < 10 else 10) != k:
                continue
            j = i
            while j < len(inflight) and inflight[j] > 2:
                j += 1
            if j >= len(inflight):
                never += 1
            else:
                waits.append(j - i)
        med_drain = statistics.median(waits) if waits else float("inf")
        verdict = "WAIT" if med_drain < be else "FIRE NOW"
        print(f"{k:>7} {MED[k]:>11.1f} {be:>25.1f} {med_drain:>19.1f} {verdict:>10}")

    # ---- draws remaining under fire-immediately, at the contention we see ----
    print("\n=== draws remaining under 'fire immediately', serial per account ===")
    now = datetime.datetime.now(datetime.timezone.utc)
    budget = (CLOSE - now).total_seconds() / 60.0
    print(f"now {now.strftime('%H:%M:%SZ')}, budget to close {budget:.0f} min")
    print(f"{'contention held':>16} {'min/draw':>9} {'draws':>7} {'P(crown)':>9}")
    for k in (0, 1, 2, 3, 5, 6, 8, 9):
        d = int(budget // MED[k])
        print(f"{('10+' if k==10 else k)!s:>16} {MED[k]:>9.1f} {d:>7} "
              f"{100*(1-(1-P_PER_DRAW)**d):>8.1f}%")
    print("\nThe honest current number is the row for the contention actually "
          "observed, not the quiet-channel row.")


if __name__ == "__main__":
    main()
