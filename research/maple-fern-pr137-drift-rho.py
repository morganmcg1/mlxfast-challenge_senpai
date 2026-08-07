#!/usr/bin/env python3
"""Is the day-scale prefill shift common to both arms, or baseline-only?

If common mode, the paired ratio cancels it and the fixed-normaliser ns is the
exposed statistic.  If baseline-only, ns is clean and officialScore is exposed.
Either way the decode-only nsd is immune, because baseline decode shows an
excess between-day sigma of only 0.047 %.
"""
import json, math, statistics as st
from collections import defaultdict

rows = [r for r in json.load(open("/tmp/pr137_submit/feed.json"))
        if (r.get("officialMetrics") or {}).get("baseline_prefill_seconds_per_token")]

by_day = defaultdict(list)
for r in rows:
    m = r["officialMetrics"]
    ts = m.get("timestamp") or r["createdAt"]
    if m.get("prefill_seconds_per_token"):
        by_day[ts[:10]].append((m["baseline_prefill_seconds_per_token"],
                                m["prefill_seconds_per_token"],
                                m["baseline_decode_seconds_per_token"],
                                m["decode_seconds_per_token"]))

days = sorted(d for d in by_day if len(by_day[d]) >= 30)
print("%-12s %5s  %-22s %-22s" % ("day", "n", "baseline prefill", "candidate prefill"))
bp, cp, bd, cd = [], [], [], []
for d in days:
    v = by_day[d]
    bp.append(st.median([x[0] for x in v]))
    cp.append(st.median([x[1] for x in v]))
    bd.append(st.median([x[2] for x in v]))
    cd.append(st.median([x[3] for x in v]))
    print("%-12s %5d  %.9f        %.9f" % (d, len(v), bp[-1], cp[-1]))


def devs(xs):
    m = st.mean(xs)
    return [x / m - 1 for x in xs]


def detrend(xs):
    """remove a linear trend in day index (candidates genuinely improve)"""
    n = len(xs)
    t = list(range(n))
    mt, mx = st.mean(t), st.mean(xs)
    b = sum((a - mt) * (y - mx) for a, y in zip(t, xs)) / sum((a - mt) ** 2 for a in t)
    return [y - (mx + b * (a - mt)) for a, y in zip(t, xs)]


def rho(xs, ys):
    mx, my = st.mean(xs), st.mean(ys)
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    sy = math.sqrt(sum((y - my) ** 2 for y in ys))
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (sx * sy)


print()
for lbl, b, c in (("prefill", bp, cp), ("decode", bd, cd)):
    db, dc = devs(b), detrend(devs(c))
    print("%s: sd of daily baseline medians %.3f%%, of detrended candidate medians %.3f%%"
          % (lbl, 100 * st.stdev(db), 100 * st.stdev(dc)))
    print("   rho(daily baseline dev, detrended daily candidate dev) = %+.3f  (n=%d days)"
          % (rho(db, dc), len(db)))

print()
print("consequence for a cross-session paired difference, in ns-percent:")
W_NS, W_NSD = 0.138, 0.148          # within-session sd, identical-tree triplets
DRIFT_P, DRIFT_D = 0.395, 0.047     # excess between-day sigma of the baseline arms
for lbl, extra_ns, extra_nsd in (
        ("if the prefill shift is common mode (ns exposed)", 0.25 * DRIFT_P, 0.0),
        ("if it is baseline-only (officialScore exposed)", 0.0, 0.0)):
    a = math.sqrt((W_NS * 2 ** 0.5) ** 2 + (extra_ns * 2 ** 0.5) ** 2)
    print("  %-52s ns paired sd %.3f%%  -> sd on t %.3f" % (lbl, a, a / 0.933))
nsd_pair = math.sqrt((W_NSD * 2 ** 0.5) ** 2 + (0.75 * DRIFT_D * 2 ** 0.5) ** 2)
print("  %-52s nsd paired sd %.3f%% -> sd on t %.3f"
      % ("nsd is immune under both", nsd_pair, nsd_pair / 0.933))
