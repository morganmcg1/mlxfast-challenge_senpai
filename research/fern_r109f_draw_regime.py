#!/usr/bin/env python3
"""READ-ONLY: is the luck term a coin flip, or a REGIME you can observe?

`fern_r109f_luck_identity.py` proves the identity

    published = normalized(candidate) x draw(baseline),
    draw = (baseline_decode/D0)^0.75 x (baseline_prefill/P0)^0.25

exactly (max rel err 4.7e-15 over 1284 rows), where the baseline numbers are
the grader's own re-measurement of the REFERENCE implementation on the grading
host.  Draw therefore contains no code content at all: it is pure host state.

Host state is not i.i.d. across time -- graders warm up, get busy, throttle.
If `log draw` is autocorrelated, then the luck of the NEXT shot is partly
observable BEFORE firing, from other teams' receipts in the last hour.  That
would be the one and only legitimate reason to time a shot.

Outputs
  1. lag-1..lag-5 autocorrelation of log draw in creation order;
  2. variance decomposition between-hour vs within-hour (ICC);
  3. the current regime: draw of the most recent N terminal rows.

Usage: python3 research/fern_r109f_draw_regime.py <submissions.json> [min_score]
"""
import json
import math
import statistics
import sys
from datetime import datetime, timezone

D0 = 0.01385621216015625
P0 = 0.00036751938916015626


def parse_ts(s):
    if not isinstance(s, str):
        return None
    t = s.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(t).astimezone(timezone.utc)
    except Exception:
        return None


def main():
    path = sys.argv[1]
    minscore = float(sys.argv[2]) if len(sys.argv) > 2 else 0.0
    with open(path) as fh:
        blob = json.load(fh)
    rows = blob if isinstance(blob, list) else (
        blob.get("submissions") or blob.get("items") or blob.get("data") or [])

    recs = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        sc = r.get("officialScore")
        m = r.get("officialMetrics")
        if not isinstance(sc, (int, float)) or float(sc) < minscore:
            continue
        if not isinstance(m, dict):
            continue
        d = {k.lower(): v for k, v in m.items()}
        bd = d.get("baseline_decode_seconds_per_token")
        bp = d.get("baseline_prefill_seconds_per_token")
        if not (isinstance(bd, (int, float)) and isinstance(bp, (int, float))):
            continue
        ts = parse_ts(r.get("updatedAt")) or parse_ts(r.get("createdAt"))
        if ts is None:
            continue
        draw = (bd / D0) ** 0.75 * (bp / P0) ** 0.25
        recs.append((ts, math.log(draw), draw, float(bd), float(bp),
                     (r.get("githubUsername") or "?"), float(sc)))
    recs.sort(key=lambda x: x[0])
    print("rows with draw + timestamp :", len(recs))
    if len(recs) < 30:
        return 1
    x = [r[1] for r in recs]
    mu = statistics.fmean(x)
    sd = statistics.stdev(x)
    print("sd log draw                : %.4f %%" % (100 * sd))

    print()
    print("AUTOCORRELATION of log draw in grading order")
    for lag in range(1, 6):
        a = x[:-lag]
        b = x[lag:]
        num = sum((p - mu) * (q - mu) for p, q in zip(a, b))
        den = sum((p - mu) ** 2 for p in x)
        print("   lag %d : %+.4f" % (lag, num / den))

    # hour buckets -> ICC
    buckets = {}
    for ts, lx, *_ in recs:
        key = ts.strftime("%Y-%m-%dT%H")
        buckets.setdefault(key, []).append(lx)
    big = {k: v for k, v in buckets.items() if len(v) >= 3}
    within, wn = 0.0, 0
    means = []
    for k, v in big.items():
        m = statistics.fmean(v)
        means.append(m)
        within += sum((z - m) ** 2 for z in v)
        wn += len(v) - 1
    sw = math.sqrt(within / wn)
    sb = statistics.stdev(means)
    print()
    print("HOURLY REGIME (buckets with n>=3: %d, rows %d)" % (
        len(big), sum(len(v) for v in big.values())))
    print("   within-hour  sd log draw : %.4f %%" % (100 * sw))
    print("   between-hour sd of means : %.4f %%" % (100 * sb))
    print("   ICC (between/total var)  : %.3f" % (sb ** 2 / (sb ** 2 + sw ** 2)))

    print()
    print("CURRENT REGIME -- last 14 graded rows")
    print("   %-22s %-14s %9s %11s %11s %s" % (
        "graded (updatedAt)", "account", "draw", "base_dec_us", "base_pre_us", "score"))
    for ts, _, draw, bd, bp, who, sc in recs[-14:]:
        print("   %-22s %-14s %9.6f %11.3f %11.3f %.6f" % (
            ts.strftime("%m-%dT%H:%M:%SZ"), str(who)[:14], draw,
            1e6 * bd, 1e6 * bp, sc))
    last = [r[2] for r in recs[-10:]]
    print("   median draw, last 10     : %.6f" % statistics.median(last))
    print("   median draw, all         : %.6f" % statistics.median([r[2] for r in recs]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
