#!/usr/bin/env python3
"""R114c -- the TRUE code gap to the crown, measured with the lottery removed.

Established in R114b, with R^2 = 1.0000000 over 1232 receipts:

    score = (baseline_decode/cand_decode)^0.75 * (baseline_prefill/cand_prefill)^0.25

and the baseline arm -- identical pinned code on every receipt -- carries 2.61%
replication noise on its prefill leg versus 0.13% on the candidate prefill leg
and 0.015% on the candidate decode leg.  96% of all leaderboard score variance
is the baseline arm.  The candidate arm is clean.

Therefore every "how far are we from the crown" number this campaign has ever
produced was read through 0.53-0.66% of noise that has nothing to do with our
code.  This script removes it: it compares candidate legs directly.

It answers three questions that decide how the remaining hours are spent:

  Q1  How much faster is the crown's TREE than ours, on each leg, in code terms?
  Q2  What score would our tree have scored on the crown's baseline draw, and
      what would the crown's tree have scored on ours?  (the counterfactual
      that separates code from luck)
  Q3  Given the gap, is it reachable by the decode work in flight?
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
CROWN = "cc6ddc1"
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
        out.append({
            "id": s.get("id", ""), "at": s.get("createdAt", ""),
            "who": s.get("solverUsername", ""), "score": s.get("officialScore"),
            "ok": bool(m.get("passed_correctness")),
            "cd": m["decode_seconds_per_token"], "bd": m["baseline_decode_seconds_per_token"],
            "cp": m["prefill_seconds_per_token"], "bp": m["baseline_prefill_seconds_per_token"],
        })
    out.sort(key=lambda r: r["at"])
    return out


def score_of(cd, cp, bd, bp):
    return (bd / cd) ** WD * (bp / cp) ** WP


def main():
    rows = load()
    ours = [r for r in rows if any(r["id"].startswith(p) for p in OURS)]
    crown = [r for r in rows if r["id"].startswith(CROWN)]
    if not crown:
        print("crown receipt %s not found in feed" % CROWN)
        return
    cr = crown[0]

    ocd = st.mean([r["cd"] for r in ours])
    ocp = st.mean([r["cp"] for r in ours])

    print("=" * 92)
    print("Q1 -- THE TRUE CODE GAP, candidate legs only (no baseline, no lottery)")
    print("=" * 92)
    print("  %-22s %-16s %-16s" % ("", "decode ms/tok", "prefill us/tok"))
    print("  %-22s %-16.6f %-16.4f" % ("maple HEAD class (n=4)", ocd * 1e3, ocp * 1e6))
    print("  %-22s %-16.6f %-16.4f" % ("crown " + CROWN, cr["cd"] * 1e3, cr["cp"] * 1e6))
    gd = 100 * (ocd / cr["cd"] - 1)
    gp = 100 * (ocp / cr["cp"] - 1)
    print()
    print("  our decode  is %+.4f%% slower than the crown's  -> %+.4f%% of score"
          % (gd, -WD * gd))
    print("  our prefill is %+.4f%% slower than the crown's  -> %+.4f%% of score"
          % (gp, -WP * gp))
    print("  TOTAL TRUE CODE GAP: %+.4f%% of score" % (-(WD * gd + WP * gp)))
    print()
    print("  measurement precision on this comparison:")
    print("    our decode  leg sd 0.0145%% (n=4) -> se of our mean %.4f%%"
          % (0.0145 / 2))
    print("    crown is a single receipt, so its own leg noise (~0.015-0.29%%) applies once")
    print()

    print("=" * 92)
    print("Q2 -- COUNTERFACTUAL: separate code from baseline luck")
    print("=" * 92)
    obd = st.mean([r["bd"] for r in ours])
    obp = st.mean([r["bp"] for r in ours])
    print("  crown receipt's own baseline draw: dec %.6f ms  pre %.4f us"
          % (cr["bd"] * 1e3, cr["bp"] * 1e6))
    print("  our four receipts' mean baseline : dec %.6f ms  pre %.4f us"
          % (obd * 1e3, obp * 1e6))
    print("  crown's baseline prefill is %+.3f%% vs our mean -> worth %+.4f%% of score"
          % (100 * (cr["bp"] / obp - 1), WP * 100 * (cr["bp"] / obp - 1)))
    print()
    s_ours_on_crown_base = score_of(ocd, ocp, cr["bd"], cr["bp"])
    s_crown_on_our_base = score_of(cr["cd"], cr["cp"], obd, obp)
    print("  our tree scored on the CROWN's baseline draw : %.8f" % s_ours_on_crown_base)
    print("  crown's published score                      : %.8f" % cr["score"])
    print("  crown's tree scored on OUR mean baseline     : %.8f" % s_crown_on_our_base)
    print("  our published class mean                     : %.8f"
          % st.mean([r["score"] for r in ours]))
    print()
    lucky = 100 * (cr["score"] / s_crown_on_our_base - 1)
    print("  => the crown receipt drew a baseline worth %+.4f%% of score versus our"
          % lucky)
    print("     typical baseline. That fraction of its %.5f is LUCK, not code."
          % cr["score"])
    print()

    print("=" * 92)
    print("Q3 -- WHERE THE GAP LIVES, and can the work in flight close it?")
    print("=" * 92)
    need_dec = -(WD * gd + WP * gp) / WD
    print("  To close the whole %+.4f%% gap on the DECODE leg alone we must cut"
          % (-(WD * gd + WP * gp)))
    print("  candidate decode by %.4f%% = %.2f us/token (of %.2f us)."
          % (-need_dec, -need_dec / 100 * ocd * 1e6, ocd * 1e6))
    print()
    print("  For calibration, decode work currently in flight:")
    for lbl, us in (("edward QMV family, 0.85%% of 5489 us/step", 47.0),
                    ("alphonse gate_sp latency, whole 240.6 us/step", 240.6),
                    ("free env flips", 10.0)):
        print("    %-44s %6.1f us/step -> %+.4f%% of score"
              % (lbl, us, WD * 100 * us / (ocd * 1e6) * 1.0))
    print()
    print("  NOTE the unit conversion: candidate decode is %.2f us/token on the"
          % (ocd * 1e6))
    print("  ranked M5 host, while the M4 rig reports ~8972 us/step of busy time.")
    print("  The us/step numbers above are M4-measured; converting them requires")
    print("  the M4->M5 transfer, which is exactly the ratio this campaign has")
    print("  repeatedly got wrong. Treat the last column as an ORDER OF MAGNITUDE.")
    print()

    print("=" * 92)
    print("Q4 -- how many solvers' TREES are actually ahead of ours?")
    print("=" * 92)
    best = {}
    for r in rows:
        if not r["ok"]:
            continue
        key = r["who"]
        cur = best.get(key)
        v = (r["cd"], r["cp"])
        if cur is None or v[0] < cur[0]:
            best[key] = v
    ahead = [(w, v) for w, v in best.items() if v[0] < ocd]
    ahead.sort(key=lambda t: t[1][0])
    print("  solvers whose best candidate DECODE beats our class mean (%.4f ms):"
          % (ocd * 1e3))
    for w, v in ahead[:15]:
        eq = -(WD * 100 * (ocd / v[0] - 1) + WP * 100 * (ocp / v[1] - 1))
        print("    %-20s dec %.6f ms  pre %8.4f us   code gap %+.4f%% of score"
              % (w, v[0] * 1e3, v[1] * 1e6, eq))
    print()
    print("  total solvers ahead of us on decode: %d of %d" % (len(ahead), len(best)))


if __name__ == "__main__":
    main()
