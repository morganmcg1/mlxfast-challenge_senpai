#!/usr/bin/env python3
"""READ-ONLY: score my registered out-of-sample prediction for one submission row.

Ledger 8.5 registered, before the fact, that row 5fae2f13 (created 12:16:59Z at
rows-in-flight 6) would reach a terminal state at median 13:07Z / p90 13:37Z.
This script reads the row's terminal timestamp from the public collection and
reports the signed error, plus a Wilson interval on our recent shot-yield rate
(ledger 10) so the P(crown)-per-shot term is not asserted without a bound.

Usage: python3 research/fern_r109f_check_prediction.py <queue.json> [id-prefix]
"""
import datetime
import json
import math
import sys

PRED_MEDIAN_MIN = 50.7   # global median sojourn at inflight 6
PRED_P90_MIN = 80.0      # global p90 sojourn at inflight 6


def ts(s):
    return datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))


def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((c - h) / d, (c + h) / d)


def main(argv):
    path = argv[0] if argv else "research/fern-r109f-queue-1310Z.json"
    pref = argv[1] if len(argv) > 1 else "5fae2f13"
    doc = json.load(open(path))
    rows = doc.get("submissions", doc)
    hit = [r for r in rows if str(r.get("id", "")).startswith(pref)]
    if not hit:
        print(f"row {pref} not found in {path}")
        return 2
    r = hit[0]
    c, u = ts(r["createdAt"]), ts(r["updatedAt"])
    soj = (u - c).total_seconds() / 60.0
    print(f"row        {pref}  user={r.get('solverUsername')}")
    print(f"created    {c.isoformat()}")
    print(f"terminal   {u.isoformat()}   status={r.get('status')}")
    print(f"sojourn    {soj:.1f} min")
    print(f"predicted  median {PRED_MEDIAN_MIN:.1f} min ({(c+datetime.timedelta(minutes=PRED_MEDIAN_MIN)).strftime('%H:%MZ')})"
          f"  p90 {PRED_P90_MIN:.1f} min ({(c+datetime.timedelta(minutes=PRED_P90_MIN)).strftime('%H:%MZ')})")
    print(f"error vs median {soj-PRED_MEDIAN_MIN:+.1f} min ({(soj-PRED_MEDIAN_MIN)/PRED_MEDIAN_MIN:+.1%})"
          f"   inside p90: {'YES' if soj <= PRED_P90_MIN else 'NO'}")
    print(f"officialScore {r.get('officialScore')}  claimed {r.get('claimedScore')}"
          f"  improved {r.get('improved')}  reason {r.get('rejectionReason')!r}")

    mine = [x for x in rows if x.get("solverUsername") == r.get("solverUsername")
            and str(x.get("status", "")).lower() in ("failed", "rejected", "accepted")
            and ts(x["createdAt"]) >= ts("2026-08-09T13:00:00Z")]
    s = sum(1 for x in mine if str(x.get("status", "")).lower() != "failed")
    lo, hi = wilson(s, len(mine))
    print(f"\nour shot yield, last 48h: {s}/{len(mine)} scored"
          f"   Wilson95 = [{lo:.1%}, {hi:.1%}]")
    print(f"=> P(crown) per fired shot in [{0.0148*lo:.2%}, {0.0148*hi:.2%}]"
          f", point {0.0148*s/max(len(mine),1):.2%}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
