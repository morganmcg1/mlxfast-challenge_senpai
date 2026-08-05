#!/usr/bin/env python3
"""Characterise the ranked-benchmark measurement instrument from the public receipt feed.

Every receipt returned by the benchmark API carries the candidate timings *and*
the same-session paired baseline timings. The baseline arm runs identical pinned
code on every submission by every solver, so pooling it across the feed yields a
large-sample probe of the ranked host and of the harness's own measurement noise.

Research-only: this file is not part of `editablePaths` and is never submitted.

Usage:
    MLXFAST_API_TOKEN=... python3 research/receipt_instrument_analysis.py [cache.json]

Without a cache path the feed is fetched and cached to /tmp/mlxfast_subs.json.
"""

import json
import os
import statistics as st
import sys
import urllib.request
from collections import defaultdict

API = os.environ.get("MLXFAST_API_URL", "https://api.mlx.fast")
BENCH = os.environ.get("MLXFAST_BENCHMARK_REF", "eigenlabs/mlxfast-challenge")
CACHE = "/tmp/mlxfast_subs.json"

# Fixed normalisers used to rank candidates without dividing by the noisy
# paired baseline. Their absolute values are arbitrary; only ratios matter.
NORM_DECODE = 0.013890
NORM_PREFILL = 0.0003845

# A candidate within this factor of the best ever recorded on *both* axes is
# treated as frontier-tight, i.e. close enough to a replicate population that
# its spread bounds measurement noise from above.
TIGHT = 1.03


def fetch(path):
    if path and os.path.exists(path):
        return json.load(open(path))
    token = os.environ["MLXFAST_API_TOKEN"]
    ref = urllib.parse.quote(BENCH, safe="")
    url = "%s/api/benchmarks/%s/submissions" % (API, ref)
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + token})
    with urllib.request.urlopen(req) as r:
        data = json.load(r)
    json.dump(data, open(CACHE, "w"))
    return data


def load(path):
    out = []
    for s in fetch(path)["submissions"]:
        m = s["officialMetrics"]
        if not m:
            continue
        if isinstance(m, str):
            m = json.loads(m)
        if not m.get("baseline_decode_seconds_per_token"):
            continue
        if not m.get("passed_correctness"):
            continue
        out.append((s["createdAt"], s["solverUsername"], m))
    out.sort()
    return out


def relsd(v):
    return 100 * st.stdev(v) / st.mean(v)


def pearson(x, y):
    mx, my = st.mean(x), st.mean(y)
    sx = sum((a - mx) ** 2 for a in x) ** 0.5
    sy = sum((b - my) ** 2 for b in y) ** 0.5
    return sum((a - mx) * (b - my) for a, b in zip(x, y)) / (sx * sy)


def ns(m):
    """Fixed-normaliser composite: the low-variance ranking statistic."""
    d = NORM_DECODE / m["decode_seconds_per_token"]
    p = NORM_PREFILL / m["prefill_seconds_per_token"]
    return d ** 0.75 * p ** 0.25


def arms(sel):
    return {
        "cand_pre": [m["prefill_seconds_per_token"] * 1e6 for _, _, m in sel],
        "base_pre": [m["baseline_prefill_seconds_per_token"] * 1e6 for _, _, m in sel],
        "cand_dec": [m["decode_seconds_per_token"] * 1000 for _, _, m in sel],
        "base_dec": [m["baseline_decode_seconds_per_token"] * 1000 for _, _, m in sel],
    }


def main():
    recs = load(sys.argv[1] if len(sys.argv) > 1 else CACHE)
    print("correctness-passing receipts with paired baselines: %d  (%s .. %s)"
          % (len(recs), recs[0][0][:10], recs[-1][0][:10]))

    a = arms(recs)
    print("\n== baseline arm: identical pinned code on every receipt")
    print("   prefill rel sd %.3f%%   decode rel sd %.3f%%"
          % (relsd(a["base_pre"]), relsd(a["base_dec"])))

    byday = defaultdict(list)
    for r in recs:
        byday[r[0][:10]].append(r)
    dm_dec = [st.mean([x[2]["baseline_decode_seconds_per_token"] for x in v])
              for _, v in sorted(byday.items())]
    print("   day-mean baseline decode spans %.3f%% across %d days -> host drift is negligible"
          % (100 * (max(dm_dec) / min(dm_dec) - 1), len(dm_dec)))

    bp = min(m["prefill_seconds_per_token"] for _, _, m in recs)
    bd = min(m["decode_seconds_per_token"] for _, _, m in recs)
    tight = [r for r in recs
             if r[2]["prefill_seconds_per_token"] < bp * TIGHT
             and r[2]["decode_seconds_per_token"] < bd * TIGHT]
    t = arms(tight)
    print("\n== frontier-tight population (within %.0f%% of best on both axes), n=%d"
          % (100 * (TIGHT - 1), len(tight)))
    for axis, cand, base in (("prefill", "cand_pre", "base_pre"),
                             ("decode", "cand_dec", "base_dec")):
        ratio = [b / c for b, c in zip(t[base], t[cand])]
        pred = (relsd(t[cand]) ** 2 + relsd(t[base]) ** 2) ** 0.5
        print("   %-7s candidate %.3f%%  baseline %.3f%%  r=%+.3f"
              % (axis, relsd(t[cand]), relsd(t[base]), pearson(t[base], t[cand])))
        print("           paired speedup %.3f%% observed vs %.3f%% predicted "
              "by independent noise -> pairing costs %.1fx"
              % (relsd(ratio), pred, relsd(ratio) / relsd(t[cand])))

    off = [m["decode_speedup"] ** 0.75 * m["prefill_speedup"] ** 0.25
           for _, _, m in tight]
    fixed = [ns(m) for _, _, m in tight]
    print("\n== ranking statistics on the same population")
    print("   officialScore        rel sd %.3f%%" % relsd(off))
    print("   fixed-normaliser ns  rel sd %.3f%%  -> %.2fx tighter"
          % (relsd(fixed), relsd(off) / relsd(fixed)))

    print("\n== frontier-tight candidate arm by day (is there session drift to correct?)")
    tbd = defaultdict(list)
    for r in tight:
        tbd[r[0][:10]].append(r)
    print("   %-12s %5s %12s %8s %12s %8s"
          % ("day", "n", "cand_pre_us", "sd", "cand_dec_ms", "sd"))
    for day, v in sorted(tbd.items()):
        d = arms(v)
        f = lambda x: st.stdev(x) if len(x) > 1 else 0.0
        print("   %-12s %5d %12.3f %8.3f %12.5f %8.5f"
              % (day, len(v), st.mean(d["cand_pre"]), f(d["cand_pre"]),
                 st.mean(d["cand_dec"]), f(d["cand_dec"])))


if __name__ == "__main__":
    main()
