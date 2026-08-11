#!/usr/bin/env python3
"""R114e -- did maple's own submitted surface get ~0.5% SLOWER, or is that drift?

R114d ranked every receipt by the score its TREE would earn on a fixed reference
baseline, which removes the 96%-of-variance baseline lottery.  Five receipts from
our own maple campaign then came out 0.35-0.62% AHEAD of our current HEAD:

    25e1f18  08-09 02:56  +0.610%   "R93 Arm A, null replicate 1/5"
    7ce1262  08-09 00:58  +0.562%   "Arm R: zero-edit ranked receipt of our base"
    83fd264  08-09 01:32  +0.540%   "Arm F: zero-edit fidelity control"
    05dd8bb  08-09 04:06  +0.479%   "R93 Arm A, null replicate 3/5"
    59d2418  08-10 10:42  +0.376%   "replay of the 4b0e051b editable surface"

(e27f1ce, +0.618%, is the CEDAR launch's receipt on this shared account.  Launch
isolation forbids borrowing it and it is excluded from every conclusion here.)

Before anyone touches a submission surface over this, the obvious confound must
be killed: those receipts are from 08-09/08-10 and ours are from 08-10/08-11.
If the ranked host drifted slower, every later tree looks worse.

The baseline arm is the control for exactly this: identical pinned code on every
receipt, every day.  This script
  (1) measures host drift per day from the baseline arm,
  (2) re-ranks trees after dividing by the SAME-DAY baseline mean,
  (3) restricts to strictly within-day comparisons, which need no correction,
  (4) reports within-tree replicate noise so the effect has an error bar.
"""

from __future__ import annotations

import json
import math
import os
import statistics as st
import urllib.parse
import urllib.request
from collections import defaultdict

API = os.environ.get("MLXFAST_API_URL", "https://api.mlx.fast")
BENCH = os.environ.get("MLXFAST_BENCHMARK_REF", "eigenlabs/mlxfast-challenge")
CACHE = "/tmp/mlxfast_subs_r114.json"
OURS = ["c1c0ba2", "2771067", "8858427", "2aedeb8"]
MAPLE_FAST = ["25e1f18", "7ce1262", "83fd264", "05dd8bb", "59d2418", "69fb349"]
CEDAR = ["e27f1ce"]
WD, WP = 0.75, 0.25


def fetch(path=CACHE):
    if path and os.path.exists(path):
        return json.load(open(path))
    token = os.environ["MLXFAST_API_TOKEN"]
    ref = urllib.parse.quote(BENCH, safe="")
    url = "%s/api/benchmarks/%s/submissions" % (API, ref)
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + token})
    with urllib.request.urlopen(req) as r:
        data = json.load(r)
    json.dump(data, open(path, "w"))
    return data


def load():
    out = []
    for s in fetch()["submissions"]:
        m = s.get("officialMetrics")
        if not m:
            continue
        if isinstance(m, str):
            m = json.loads(m)
        if not (m.get("baseline_decode_seconds_per_token") and m.get("prefill_seconds_per_token")
                and m.get("baseline_prefill_seconds_per_token") and m.get("decode_seconds_per_token")):
            continue
        if not m.get("passed_correctness"):
            continue
        out.append({
            "id": s.get("id", ""), "at": s.get("createdAt", ""),
            "who": s.get("solverUsername", ""), "score": s.get("officialScore"),
            "cd": m["decode_seconds_per_token"], "bd": m["baseline_decode_seconds_per_token"],
            "cp": m["prefill_seconds_per_token"], "bp": m["baseline_prefill_seconds_per_token"],
        })
    out.sort(key=lambda r: r["at"])
    return out


def main():
    rows = load()
    byday = defaultdict(list)
    for r in rows:
        byday[r["at"][:10]].append(r)

    print("=" * 98)
    print("(1) HOST DRIFT measured on the baseline arm (identical pinned code, every receipt)")
    print("=" * 98)
    print("  %-12s %-5s %-15s %-15s %-13s" %
          ("day", "n", "base_dec ms", "base_pre us", "sem dec"))
    ref = None
    for d in sorted(byday):
        v = byday[d]
        md = st.mean([r["bd"] for r in v])
        mp = st.mean([r["bp"] for r in v])
        sem = st.stdev([r["bd"] for r in v]) / math.sqrt(len(v)) if len(v) > 2 else float("nan")
        if ref is None:
            ref = md
        print("  %-12s %-5d %-15.6f %-15.4f %-13.6f" % (d, len(v), md * 1e3, mp * 1e6, sem * 1e3))
    print()
    d9 = st.mean([r["bd"] for r in byday["2026-08-09"]])
    d10 = st.mean([r["bd"] for r in byday["2026-08-10"]])
    p9 = st.mean([r["bp"] for r in byday["2026-08-09"]])
    p10 = st.mean([r["bp"] for r in byday["2026-08-10"]])
    drift = WD * 100 * (d10 / d9 - 1) + WP * 100 * (p10 / p9 - 1)
    print("  08-09 -> 08-10 host drift: decode %+.4f%%, prefill %+.4f%%"
          % (100 * (d10 / d9 - 1), 100 * (p10 / p9 - 1)))
    print("  => a tree measured on 08-10 looks %+.4f%% of score different from the"
          % -drift)
    print("     same tree measured on 08-09, purely from the host.")
    print()

    print("=" * 98)
    print("(2) SAME-DAY-BASELINE-NORMALISED tree scores: drift divided out")
    print("=" * 98)

    dayb = {d: (st.mean([r["bd"] for r in v]), st.mean([r["bp"] for r in v]))
            for d, v in byday.items()}

    def tnorm(r):
        bd, bp = dayb[r["at"][:10]]
        return (bd / r["cd"]) ** WD * (bp / r["cp"]) ** WP

    ours = [r for r in rows if any(r["id"].startswith(p) for p in OURS)]
    ohead = st.mean([tnorm(r) for r in ours])
    print("  our HEAD class, day-normalised tree score: %.6f  (n=%d)" % (ohead, len(ours)))
    for r in sorted(ours, key=lambda r: r["at"]):
        print("     %-9s %-17s %.6f" % (r["id"][:7], r["at"][:16], tnorm(r)))
    print()
    print("  maple's own earlier trees, day-normalised:")
    print("  %-9s %-17s %-11s %-13s" % ("id", "created", "tree", "vs our HEAD"))
    for pid in MAPLE_FAST:
        m = [r for r in rows if r["id"].startswith(pid)]
        if not m:
            continue
        r = m[0]
        print("  %-9s %-17s %-11.6f %+-13.4f" %
              (r["id"][:7], r["at"][:16], tnorm(r), 100 * (tnorm(r) / ohead - 1)))
    print()
    for pid in CEDAR:
        m = [r for r in rows if r["id"].startswith(pid)]
        if m:
            r = m[0]
            print("  [cedar, EXCLUDED from all conclusions] %-9s %.6f  %+.4f%%"
                  % (r["id"][:7], tnorm(r), 100 * (tnorm(r) / ohead - 1)))
    print()

    print("=" * 98)
    print("(3) STRICTLY WITHIN-DAY comparison (08-10 only): no correction needed at all")
    print("=" * 98)
    d10rows = byday["2026-08-10"]
    ours10 = [r for r in d10rows if any(r["id"].startswith(p) for p in OURS)]
    print("  our HEAD-class receipts on 08-10:")
    for r in ours10:
        print("     %-9s %-17s cd %.6f ms  cp %.4f us" %
              (r["id"][:7], r["at"][:16], r["cd"] * 1e3, r["cp"] * 1e6))
    print("  maple's other 08-10 receipts that beat them on decode:")
    if ours10:
        ocd = st.mean([r["cd"] for r in ours10])
        ocp = st.mean([r["cp"] for r in ours10])
        for r in sorted(d10rows, key=lambda r: r["cd"]):
            if r["who"] != "morganmcg1" or r["cd"] >= ocd:
                continue
            if any(r["id"].startswith(p) for p in CEDAR):
                tag = "  [CEDAR - excluded]"
            elif any(r["id"].startswith(p) for p in OURS):
                continue
            else:
                tag = ""
            eq = -(WD * 100 * (ocd / r["cd"] - 1) + WP * 100 * (ocp / r["cp"] - 1))
            print("     %-9s %-17s cd %.6f ms  cp %.4f us   %+.4f%% of score%s"
                  % (r["id"][:7], r["at"][:16], r["cd"] * 1e3, r["cp"] * 1e6, eq, tag))
    print()

    print("=" * 98)
    print("(4) ERROR BAR: within-tree replicate noise on the candidate legs")
    print("=" * 98)
    reps = [r for r in rows if r["id"].startswith("25e1f18") or r["id"].startswith("05dd8bb")]
    if len(reps) == 2:
        a, b = reps
        print("  R93 Arm A null replicates 1/5 and 3/5 (same declared tree, same day):")
        print("     %s cd %.6f ms   %s cd %.6f ms   diff %+.4f%%"
              % (a["id"][:7], a["cd"] * 1e3, b["id"][:7], b["cd"] * 1e3,
                 100 * (b["cd"] / a["cd"] - 1)))
    print("  our HEAD class candidate decode sd: %.4f%% (n=%d)"
          % (100 * st.stdev([r["cd"] for r in ours]) / st.mean([r["cd"] for r in ours]),
             len(ours)))
    print()
    print("  VERDICT RULE: if (2) and (3) still show maple trees >=0.3% ahead after")
    print("  day-normalisation, and (1) shows drift of only ~0.1%, then our current")
    print("  submitted surface is genuinely slower than one we already owned, and the")
    print("  editable paths of that receipt are recoverable with `mlxfast reset`.")


if __name__ == "__main__":
    main()
