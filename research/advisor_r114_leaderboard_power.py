#!/usr/bin/env python3
"""R114 -- what can ONE official submission actually resolve, per leg?

Why this exists
---------------
I was about to spend a submission slot firing maple-tanjiro's A2 arm (a prefill
`_nax` GEMM tile change that CANNOT be measured on M4, because `_nax` is off on
gen-16 silicon).  My justification was: "sigma on the candidate prefill leg is
0.1388%, and A2 should move prefill by 0.30-0.83%, so one draw is a 2-6 sigma
observation."

That sentence silently mixes three different noise scales:
  (a) the replication sd of the TOTAL SCORE across replay draws (0.659%, R113),
  (b) the replication sd of the RAW candidate prefill time,
  (c) the replication sd of the BASELINE-NORMALISED prefill ratio.
Only (c) is the paired statistic, and only (c) justifies calling one draw a
2-6 sigma observation.  Before spending an irreplaceable slot I should measure
which one is real instead of asserting it.

Every receipt carries a same-session paired baseline arm running identical
pinned code, so the ratio candidate/baseline cancels session-level host drift.
This script measures all three scales on OUR OWN four byte-equivalent HEAD-class
receipts, and cross-checks against the field's large replicate populations.

Outputs the only number that matters for the decision:
    the minimum detectable prefill effect for a 1-vs-k paired comparison.
"""

from __future__ import annotations

import json
import math
import os
import statistics as st
import sys
import urllib.parse
import urllib.request
from collections import defaultdict

API = os.environ.get("MLXFAST_API_URL", "https://api.mlx.fast")
BENCH = os.environ.get("MLXFAST_BENCHMARK_REF", "eigenlabs/mlxfast-challenge")
CACHE = "/tmp/mlxfast_subs_r114.json"

# Our HEAD executable class: byte-equivalent editable surfaces, differing only
# by inert nonces / dead knobs.  Any spread among these is pure instrument.
OURS = ["c1c0ba2", "2771067", "8858427", "2aedeb8"]
CROWN_ID = "cc6ddc1"


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
        if not m.get("baseline_decode_seconds_per_token"):
            continue
        if not m.get("prefill_seconds_per_token"):
            continue
        out.append({
            "id": s.get("id") or s.get("submissionId") or "",
            "at": s.get("createdAt", ""),
            "who": s.get("solverUsername", ""),
            "score": s.get("officialScore"),
            "ok": bool(m.get("passed_correctness")),
            "cd": m["decode_seconds_per_token"],
            "bd": m["baseline_decode_seconds_per_token"],
            "cp": m["prefill_seconds_per_token"],
            "bp": m["baseline_prefill_seconds_per_token"],
        })
    out.sort(key=lambda r: r["at"])
    return out


def relsd(v):
    return 100.0 * st.stdev(v) / st.mean(v)


def show(tag, rows):
    n = len(rows)
    if n < 2:
        print("  %-28s n=%d (too few)" % (tag, n))
        return None
    cd = [r["cd"] for r in rows]
    bd = [r["bd"] for r in rows]
    cp = [r["cp"] for r in rows]
    bp = [r["bp"] for r in rows]
    rd = [a / b for a, b in zip(cd, bd)]
    rp = [a / b for a, b in zip(cp, bp)]
    print("  %-28s n=%2d | raw cand dec %6.3f%%  pre %6.3f%% | "
          "baseline dec %6.3f%%  pre %6.3f%% | RATIO dec %6.3f%%  pre %6.3f%%"
          % (tag, n, relsd(cd), relsd(cp), relsd(bd), relsd(bp),
             relsd(rd), relsd(rp)))
    return {"rd": rd, "rp": rp, "cd": cd, "cp": cp, "bd": bd, "bp": bp}


def fit_exponents(rows):
    """Recover the score's leg exponents by OLS on logs.

    log score ~ c - a*log(cand_dec) - b*log(cand_pre)
    """
    sel = [r for r in rows if r["score"] and r["score"] > 0 and r["ok"]]
    if len(sel) < 20:
        return None
    y = [math.log(r["score"]) for r in sel]
    x1 = [math.log(r["cd"]) for r in sel]
    x2 = [math.log(r["cp"]) for r in sel]
    n = len(sel)
    my, m1, m2 = st.mean(y), st.mean(x1), st.mean(x2)
    y0 = [v - my for v in y]
    a1 = [v - m1 for v in x1]
    a2 = [v - m2 for v in x2]
    s11 = sum(v * v for v in a1)
    s22 = sum(v * v for v in a2)
    s12 = sum(p * q for p, q in zip(a1, a2))
    s1y = sum(p * q for p, q in zip(a1, y0))
    s2y = sum(p * q for p, q in zip(a2, y0))
    det = s11 * s22 - s12 * s12
    if abs(det) < 1e-18:
        return None
    b1 = (s22 * s1y - s12 * s2y) / det
    b2 = (s11 * s2y - s12 * s1y) / det
    pred = [b1 * p + b2 * q for p, q in zip(a1, a2)]
    ss_res = sum((p - q) ** 2 for p, q in zip(y0, pred))
    ss_tot = sum(v * v for v in y0)
    return b1, b2, 1 - ss_res / ss_tot, n


def main():
    rows = load()
    print("=" * 96)
    print("R114 -- per-leg instrument resolution from the official receipt feed")
    print("=" * 96)
    print("receipts with paired baselines: %d   (%s .. %s)"
          % (len(rows), rows[0]["at"][:10], rows[-1]["at"][:10]))
    print()

    print("-" * 96)
    print("(1) SCORE STRUCTURE -- what weight does the prefill leg actually carry?")
    print("-" * 96)
    fit = fit_exponents(rows)
    if fit:
        b1, b2, r2, n = fit
        print("  OLS  log(score) ~ %+.4f*log(cand_decode) %+.4f*log(cand_prefill)"
              "   R^2=%.5f  n=%d" % (b1, b2, r2, n))
        print("  => decode elasticity %.3f, prefill elasticity %.3f"
              % (-b1, -b2))
        print("  => a 1.00%% prefill-time improvement is worth %.3f%% of score"
              % (-b2))
        w_pre = -b2
    else:
        w_pre = 0.25
        print("  fit unavailable; assuming prefill weight 0.25")
    print()

    print("-" * 96)
    print("(2) REPLICATION NOISE, three scales, on populations of identical code")
    print("-" * 96)
    ours = [r for r in rows if any(r["id"].startswith(p) for p in OURS)]
    print("  our HEAD executable class receipts found: %d of %d"
          % (len(ours), len(OURS)))
    st_ours = show("maple HEAD class", ours)

    byw = defaultdict(list)
    for r in rows:
        if r["ok"]:
            byw[r["who"]].append(r)
    for who in ("a-github-name", "MyatKaung", "fyrsta7", "newjordan"):
        sel = byw.get(who, [])
        if len(sel) >= 4:
            show("field replay: " + who, sel)
    print()
    print("  READ THIS: if the RATIO columns are not much smaller than the raw")
    print("  candidate columns, the paired baseline does NOT cancel the noise,")
    print("  and there is no cheap paired statistic hiding in the receipt.")
    print()

    print("-" * 96)
    print("(3) THE DECISION -- minimum detectable prefill effect, 1 arm vs k controls")
    print("-" * 96)
    if st_ours:
        sd_rp = st.stdev(st_ours["rp"]) / st.mean(st_ours["rp"]) * 100
        sd_cp = st.stdev(st_ours["cp"]) / st.mean(st_ours["cp"]) * 100
    else:
        sd_rp = sd_cp = float("nan")
    pool_rp = []
    pool_cp = []
    for who, sel in byw.items():
        if len(sel) < 5:
            continue
        rp = [r["cp"] / r["bp"] for r in sel]
        cp = [r["cp"] for r in sel]
        # only replay-like populations (tight) contribute
        if relsd(cp) < 2.0:
            pool_rp.append((len(sel) - 1, st.stdev(rp) / st.mean(rp) * 100))
            pool_cp.append((len(sel) - 1, st.stdev(cp) / st.mean(cp) * 100))

    def pool(ps):
        num = sum(df * s * s for df, s in ps)
        den = sum(df for df, s in ps)
        return math.sqrt(num / den) if den else float("nan")

    p_rp, p_cp = pool(pool_rp), pool(pool_cp)
    print("  prefill RATIO   sd: ours(3 df) %.4f%%   pooled field(%d df) %.4f%%"
          % (sd_rp, sum(df for df, _ in pool_rp), p_rp))
    print("  prefill RAW     sd: ours(3 df) %.4f%%   pooled field(%d df) %.4f%%"
          % (sd_cp, sum(df for df, _ in pool_cp), p_cp))
    print()
    sigma = p_rp if p_rp == p_rp else sd_rp
    print("  Using the pooled field ratio sd sigma = %.4f%% as the per-draw scale." % sigma)
    print()
    print("  One A2 draw vs k HEAD-class controls: se(diff) = sigma*sqrt(1 + 1/k)")
    print("  %-6s %-14s %-16s %-16s" % ("k", "se(diff) %", "MDE @80% power %", "MDE in score %"))
    for k in (4, 8, 16, 32):
        se = sigma * math.sqrt(1.0 + 1.0 / k)
        mde = 2.80 * se           # two-sided 5%, 80% power
        print("  %-6d %-14.4f %-16.4f %-16.4f" % (k, se, mde, mde * w_pre))
    print()
    print("  A2's honest prefill-time effect (from tanjiro's corrected ceiling,")
    print("  0.11-0.30%% of SCORE) is %.3f-%.3f%% of prefill time."
          % (0.11 / w_pre, 0.30 / w_pre))
    print()
    print("  VERDICT: compare that range against the MDE column above.")


if __name__ == "__main__":
    main()
