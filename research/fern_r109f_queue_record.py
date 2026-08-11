#!/usr/bin/env python3
"""fern r109-f: whole-record queue facts from the submissions listing.

Answers, from timestamps alone (no polling, no new submissions):

1. one-in-flight-per-solver: does any solver ever hold two overlapping
   non-terminal intervals?  An interval is [createdAt, updatedAt] for a row
   that reached a terminal status, which brackets the time it occupied a slot.
2. service time: updatedAt - createdAt for terminal rows, by hour, so the
   current backlog can be priced.
3. current backlog and the implied wait for a submission fired now.

Usage: research/fern_r109f_queue_record.py <submissions.json>
"""
from __future__ import annotations

import json
import statistics as st
import sys
from datetime import datetime, timezone

TERMINAL = {"completed", "failed", "accepted", "rejected", "cancelled", "error"}


def ts(s):
    if not s:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def main() -> int:
    rows = json.load(open(sys.argv[1]))["submissions"]
    now = datetime.now(timezone.utc)
    print(f"rows={len(rows)}  now={now.isoformat()}")

    # ---- 1. one-in-flight-per-solver -------------------------------------
    by_solver: dict[str, list] = {}
    for r in rows:
        c, u = ts(r.get("createdAt")), ts(r.get("updatedAt"))
        if c is None:
            continue
        end = u if (u and r.get("status") in TERMINAL) else now
        by_solver.setdefault(r.get("solverUsername") or "?", []).append(
            (c, end, r["id"][:8], r.get("status")))
    violations = []
    for solver, ivs in by_solver.items():
        ivs.sort()
        for a, b in zip(ivs, ivs[1:]):
            # strict overlap: next created before previous finished
            if b[0] < a[1]:
                violations.append((solver, a, b, (a[1] - b[0]).total_seconds()))
    print(f"\n=== one-in-flight-per-solver test ===")
    print(f"solvers={len(by_solver)} overlapping_pairs={len(violations)}")
    for v in sorted(violations, key=lambda x: -x[3])[:12]:
        print(f"  {v[0]}: {v[1][2]}({v[1][3]}) [{v[1][0]:%H:%M:%S}-{v[1][1]:%H:%M:%S}] "
              f"vs {v[2][2]}({v[2][3]}) created {v[2][0]:%H:%M:%S} "
              f"overlap={v[3]:.0f}s")
    if violations:
        worst = max(v[3] for v in violations)
        big = [v for v in violations if v[3] > 60]
        print(f"  worst overlap {worst:.0f}s; pairs overlapping >60s: {len(big)}")

    # ---- 2. service time -------------------------------------------------
    svc = []
    for r in rows:
        c, u = ts(r.get("createdAt")), ts(r.get("updatedAt"))
        if c and u and r.get("status") in TERMINAL:
            d = (u - c).total_seconds()
            if d >= 0:
                svc.append((c, d, r.get("status"), r.get("solverUsername")))
    svc.sort()
    d_all = [x[1] for x in svc]
    print(f"\n=== service time (updatedAt-createdAt), terminal rows n={len(d_all)} ===")
    qs = st.quantiles(d_all, n=20)
    print(f"  median={st.median(d_all):.0f}s  mean={st.mean(d_all):.0f}s "
          f"p5={qs[0]:.0f}s p25={qs[4]:.0f}s p75={qs[14]:.0f}s p95={qs[18]:.0f}s "
          f"max={max(d_all):.0f}s")
    print("  by hour (UTC) on the final day:")
    last = [x for x in svc if x[0] >= svc[-1][0].replace(hour=0, minute=0,
                                                         second=0, microsecond=0)]
    buckets: dict[int, list] = {}
    for c, d, _s, _u in last:
        buckets.setdefault(c.hour, []).append(d)
    for h in sorted(buckets):
        v = buckets[h]
        print(f"    {h:02d}Z n={len(v):>3} median={st.median(v):>7.0f}s "
              f"mean={st.mean(v):>7.0f}s max={max(v):>7.0f}s")

    # ---- 3. current backlog ---------------------------------------------
    live = [r for r in rows if r.get("status") not in TERMINAL]
    live.sort(key=lambda r: ts(r["createdAt"]))
    print(f"\n=== current backlog: {len(live)} non-terminal ===")
    for r in live:
        age = (now - ts(r["createdAt"])).total_seconds()
        print(f"  {r['id'][:8]} {str(r.get('solverUsername')):>14} "
              f"{r.get('status'):>10} created {ts(r['createdAt']):%H:%M:%S}Z "
              f"age={age/60:.1f}min")
    if live:
        oldest = (now - ts(live[0]["createdAt"])).total_seconds()
        print(f"  oldest in-flight age = {oldest/60:.1f} min "
              f"({oldest:.0f}s), i.e. already past the "
              f"p{sum(1 for d in d_all if d < oldest) * 100 // len(d_all)} "
              f"of the whole-record service distribution")

    # throughput: terminal completions per hour over the last 6h
    cutoff = now.timestamp() - 6 * 3600
    done_recent = [x for x in svc if ts_epoch(x[0]) + x[1] >= cutoff]
    if done_recent:
        comp = sorted(ts_epoch(x[0]) + x[1] for x in done_recent)
        span = (comp[-1] - comp[0]) / 3600 or 1e-9
        print(f"\n=== recent throughput ===")
        print(f"  completions in last ~6h window: {len(comp)} over "
              f"{span:.2f}h = {len(comp)/span:.1f}/h")
        if len(live) and len(comp) / span > 0:
            wait = len(live) / (len(comp) / span)
            print(f"  a submission fired NOW sits behind {len(live)} rows => "
                  f"queue-only wait ~{wait:.2f}h, plus its own service "
                  f"(median {st.median(d_all)/3600:.2f}h)")
    return 0


def ts_epoch(d):
    return d.timestamp()


if __name__ == "__main__":
    sys.exit(main())
