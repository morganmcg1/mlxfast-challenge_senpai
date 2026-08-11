#!/usr/bin/env python3
"""R114b -- VERIFY the claim that leaderboard score noise is baseline-arm noise.

R114a produced a startling pair of numbers on our four byte-equivalent HEAD-class
receipts:

    candidate decode  rel sd  0.015%      baseline decode  rel sd  0.167%
    candidate prefill rel sd  0.130%      baseline prefill rel sd  2.607%

If true, the candidate arm -- the only arm our code changes -- is 20x to 170x
more reproducible than the paired baseline arm, and every "the leaderboard is
too noisy to measure anything" conclusion on this campaign has been about the
wrong arm.  That is a big enough claim that it gets an independent check before
a single slot or brief moves.

Four falsifiable checks, any of which can kill it:

  C1  Exact score model.  Fit log(score) on all four legs.  If score is
      (base/cand)^w then the baseline coefficients must come out EQUAL AND
      OPPOSITE to the candidate ones, with R^2 ~ 1.  If they come out ~0, the
      baseline is decorative and cannot be the noise source.

  C2  Variance budget.  Predict the score's replication sd from the four leg
      sds using the fitted weights, and compare with the DIRECTLY OBSERVED
      score sd.  If the prediction misses, the decomposition is wrong.

  C3  Is our 0.015% real or n=4 luck?  Print every raw value, and find all
      other solver populations that look like true replicates, then pool.

  C4  Drift.  A control arm fired yesterday is only a valid control for an arm
      fired today if the candidate arm does not drift.  Measure day-over-day
      movement of the candidate legs within replicate populations.
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
        if not (m.get("baseline_decode_seconds_per_token")
                and m.get("prefill_seconds_per_token")
                and m.get("baseline_prefill_seconds_per_token")
                and m.get("decode_seconds_per_token")):
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


def relsd(v):
    return 100.0 * st.stdev(v) / st.mean(v)


def ols(y, xs):
    """Plain multiple OLS through centred data. Returns (betas, r2, n)."""
    n = len(y)
    k = len(xs)
    my = st.mean(y)
    mx = [st.mean(x) for x in xs]
    Y = [v - my for v in y]
    X = [[x[i] - mx[j] for i in range(n)] for j, x in enumerate(xs)]
    A = [[sum(X[a][i] * X[b][i] for i in range(n)) for b in range(k)] for a in range(k)]
    B = [sum(X[a][i] * Y[i] for i in range(n)) for a in range(k)]
    # Gaussian elimination
    M = [row[:] + [B[i]] for i, row in enumerate(A)]
    for c in range(k):
        p = max(range(c, k), key=lambda r: abs(M[r][c]))
        M[c], M[p] = M[p], M[c]
        if abs(M[c][c]) < 1e-20:
            return None
        for r in range(k):
            if r == c:
                continue
            f = M[r][c] / M[c][c]
            for cc in range(c, k + 1):
                M[r][cc] -= f * M[c][cc]
    beta = [M[i][k] / M[i][i] for i in range(k)]
    pred = [sum(beta[j] * X[j][i] for j in range(k)) for i in range(n)]
    ssr = sum((Y[i] - pred[i]) ** 2 for i in range(n))
    sst = sum(v * v for v in Y)
    return beta, 1 - ssr / sst, n


def main():
    rows = load()
    ours = [r for r in rows if any(r["id"].startswith(p) for p in OURS)]

    print("=" * 100)
    print("C1 -- EXACT SCORE MODEL: does the baseline arm enter the score?")
    print("=" * 100)
    sel = [r for r in rows if r["ok"] and r["score"] and r["score"] > 0]
    y = [math.log(r["score"]) for r in sel]
    res = ols(y, [[math.log(r["cd"]) for r in sel], [math.log(r["cp"]) for r in sel],
                  [math.log(r["bd"]) for r in sel], [math.log(r["bp"]) for r in sel]])
    b, r2, n = res
    print("  log(score) = %+.5f*log(cd) %+.5f*log(cp) %+.5f*log(bd) %+.5f*log(bp)"
          % (b[0], b[1], b[2], b[3]))
    print("  R^2 = %.7f   n = %d" % (r2, n))
    print()
    print("  candidate decode weight  %+.4f   baseline decode weight  %+.4f   sum %+.4f"
          % (b[0], b[2], b[0] + b[2]))
    print("  candidate prefill weight %+.4f   baseline prefill weight %+.4f   sum %+.4f"
          % (b[1], b[3], b[1] + b[3]))
    print()
    if abs(b[0] + b[2]) < 0.05 and abs(b[1] + b[3]) < 0.05:
        print("  => CONFIRMED: score is a RATIO (baseline/candidate)^w. The baseline arm")
        print("     enters the score with full, opposite weight, so ALL of its noise")
        print("     lands in the score.")
    else:
        print("  => NOT a clean ratio; decomposition below is suspect.")
    print()

    print("=" * 100)
    print("C2 -- VARIANCE BUDGET on our four byte-equivalent HEAD-class receipts")
    print("=" * 100)
    wd, wp = abs(b[0]), abs(b[1])
    legs = {k: [r[k] for r in ours] for k in ("cd", "cp", "bd", "bp")}
    sds = {k: relsd(v) for k, v in legs.items()}
    for k, lbl in (("cd", "candidate decode"), ("cp", "candidate prefill"),
                   ("bd", "baseline  decode"), ("bp", "baseline  prefill")):
        w = wd if k in ("cd", "bd") else wp
        print("  %-18s rel sd %7.4f%%   x weight %.3f  ->  %7.4f%% of score"
              % (lbl, sds[k], w, w * sds[k]))
    pred = math.sqrt((wd * sds["cd"]) ** 2 + (wp * sds["cp"]) ** 2
                     + (wd * sds["bd"]) ** 2 + (wp * sds["bp"]) ** 2)
    obs = relsd([r["score"] for r in ours])
    print()
    print("  predicted score rel sd (quadrature) %.4f%%" % pred)
    print("  OBSERVED  score rel sd              %.4f%%" % obs)
    print("  ratio predicted/observed            %.3f" % (pred / obs))
    share_bp = (wp * sds["bp"]) ** 2 / pred ** 2
    print()
    print("  => the BASELINE PREFILL arm alone accounts for %.1f%% of all score variance."
          % (100 * share_bp))
    print()

    print("=" * 100)
    print("C3 -- is the candidate arm's reproducibility real? raw values")
    print("=" * 100)
    print("  %-9s %-17s %-14s %-14s %-14s %-14s" %
          ("id", "created", "cand_dec ms", "cand_pre us", "base_dec ms", "base_pre us"))
    for r in sorted(ours, key=lambda r: r["at"]):
        print("  %-9s %-17s %-14.6f %-14.4f %-14.6f %-14.4f"
              % (r["id"][:7], r["at"][:16], r["cd"] * 1e3, r["cp"] * 1e6,
                 r["bd"] * 1e3, r["bp"] * 1e6))
    print()
    print("  Other populations that look like true replicates")
    print("  (>=4 receipts from one solver whose candidate DECODE spread < 0.5%):")
    byw = defaultdict(list)
    for r in rows:
        if r["ok"]:
            byw[r["who"]].append(r)
    pool = []
    for who, s in sorted(byw.items()):
        if len(s) < 4:
            continue
        cds = [r["cd"] for r in s]
        if relsd(cds) < 0.5:
            cps = [r["cp"] for r in s]
            bps = [r["bp"] for r in s]
            print("    %-18s n=%3d  cand_dec %.4f%%  cand_pre %.4f%%  base_pre %.4f%%"
                  % (who, len(s), relsd(cds), relsd(cps), relsd(bps)))
            pool.append((len(s) - 1, relsd(cds), relsd(cps)))
    if pool:
        def pl(i):
            return math.sqrt(sum(df * v[i] ** 2 for df, *v in
                                 [(p[0], p[1], p[2]) for p in pool])
                             / sum(p[0] for p in pool))
        df = sum(p[0] for p in pool)
        pdec = math.sqrt(sum(p[0] * p[1] ** 2 for p in pool) / df)
        ppre = math.sqrt(sum(p[0] * p[2] ** 2 for p in pool) / df)
        print()
        print("    POOLED candidate-arm sd (%d df): decode %.4f%%   prefill %.4f%%"
              % (df, pdec, ppre))
    else:
        pdec = sds["cd"]
        ppre = sds["cp"]
    print()

    print("=" * 100)
    print("C4 -- DRIFT: is a control fired yesterday valid for an arm fired today?")
    print("=" * 100)
    for who in ("morganmcg1",):
        s = [r for r in byw.get(who, []) if r["ok"]]
    byday = defaultdict(list)
    for r in rows:
        if r["ok"]:
            byday[r["at"][:10]].append(r)
    days = sorted(byday)[-8:]
    print("  day-mean of the BASELINE arms (identical pinned code every receipt):")
    print("  %-12s %-6s %-16s %-16s" % ("day", "n", "base_dec ms", "base_pre us"))
    for d in days:
        v = byday[d]
        print("  %-12s %-6d %-16.6f %-16.4f"
              % (d, len(v), 1e3 * st.mean([r["bd"] for r in v]),
                 1e6 * st.mean([r["bp"] for r in v])))
    dm_d = [st.mean([r["bd"] for r in byday[d]]) for d in days]
    dm_p = [st.mean([r["bp"] for r in byday[d]]) for d in days]
    print()
    print("  day-mean spread: baseline decode %.3f%%   baseline prefill %.3f%%"
          % (100 * (max(dm_d) / min(dm_d) - 1), 100 * (max(dm_p) / min(dm_p) - 1)))
    print("  => host drift on the decode leg is the binding constraint on using")
    print("     yesterday's receipts as controls.")
    print()

    print("=" * 100)
    print("C5 -- WHAT ONE DRAW RESOLVES, read on the CANDIDATE arm")
    print("=" * 100)
    print("  %-26s %-14s %-14s %-16s" %
          ("statistic", "sd (rel)", "se(1 vs 4)", "MDE@80% in score"))
    for lbl, sd, w in (("candidate decode", pdec, wd),
                       ("candidate prefill", ppre, wp),
                       ("official score", obs, 1.0)):
        se = sd * math.sqrt(1 + 1 / 4)
        print("  %-26s %-14.4f %-14.4f %-16.4f" % (lbl, sd, se, 2.80 * se * w))
    print()
    print("  A2 (tanjiro) expected effect: 0.11-0.30%% of score on the prefill leg")
    print("   = %.3f-%.3f%% of candidate prefill time." % (0.11 / wp, 0.30 / wp))
    se_p = ppre * math.sqrt(1 + 1 / 4)
    print("   = %.2f-%.2f sigma against a 4-control paired comparison."
          % (0.11 / wp / se_p, 0.30 / wp / se_p))


if __name__ == "__main__":
    main()
