#!/usr/bin/env python3
"""fern R109-F: hour-resolution timeline of ranked candidate decode.

Why this exists
---------------
Package `5c542169b5` (receipt e27f1ce4, 2026-08-10T08:18Z) measured 4890.7 us
candidate decode; our three 2026-08-10T23Z/2026-08-11T00Z receipts measured
4932-4949 us.  Two readings compete:

  (A) code regression - our branch carries an arm that costs ~42 us.
  (B) harness/base change - `benchmark.sh` and `tools/fan-control.sh` differ by
      230 and 137 *semantic* lines between the `5c542169b5` tree and our base
      `1bc1c895`, and neither file is in `editablePaths`, so the difference is
      the service's, not ours.  A driver change would move every solver.

(B) is falsifiable: if the whole population steps up at the same wall-clock
moment, it is the driver.  If other solvers keep landing sub-4900 receipts
after the step, it is our code.

Usage:
    python3 research/fern_r109f_decode_timeline.py [receipts.json] [since_iso]
"""

from __future__ import annotations

import json
import statistics
import sys
from collections import defaultdict

PATH = sys.argv[1] if len(sys.argv) > 1 else "/tmp/subs_p4.json"
SINCE = sys.argv[2] if len(sys.argv) > 2 else "2026-08-09T00"


def main() -> None:
    with open(PATH) as fh:
        rows = json.load(fh)["submissions"]

    recs = []
    for r in rows:
        m = r.get("officialMetrics") or {}
        d = m.get("decode_seconds_per_token")
        bd = m.get("baseline_decode_seconds_per_token")
        if not d or not bd or not m.get("passed_correctness"):
            continue
        created = r.get("createdAt") or ""
        if created < SINCE:
            continue
        recs.append((created, r["solverUsername"], r["id"][:8],
                     d * 1e6, bd * 1e6,
                     (m.get("prefill_seconds_per_token") or 0) * 1e6))
    recs.sort()

    print("=" * 96)
    print("fern R109-F: ranked candidate decode timeline (full-leg, correct)")
    print("  source = %s   since = %s   n = %d" % (PATH, SINCE, len(recs)))
    print("=" * 96)
    print("%-19s %-15s %-9s %10s %10s %9s" % (
        "createdAt(UTC)", "solver", "receipt", "cand_dec_us", "base_dec_us",
        "cand_pf_us"))
    print("-" * 96)
    for created, solver, rid, d, bd, pf in recs:
        print("%-19s %-15s %-9s %10.1f %10.1f %9.2f" % (
            created[:19], solver[:15], rid, d, bd, pf))

    print()
    print("per-UTC-hour summary of candidate decode (us)")
    print("-" * 96)
    print("%-13s %4s %10s %10s %10s  %s" % (
        "hour", "n", "min", "median", "max", "solvers"))
    buckets: dict[str, list] = defaultdict(list)
    for created, solver, _rid, d, _bd, _pf in recs:
        buckets[created[:13]].append((d, solver))
    for hour in sorted(buckets):
        vals = [d for d, _ in buckets[hour]]
        solvers = sorted({s for _, s in buckets[hour]})
        print("%-13s %4d %10.1f %10.1f %10.1f  %s" % (
            hour, len(vals), min(vals), statistics.median(vals), max(vals),
            ",".join(s[:9] for s in solvers)))


if __name__ == "__main__":
    main()
