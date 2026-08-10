#!/usr/bin/env python3
"""The baseline lottery: corrected record-gap VOI, parametric and nonparametric.

WHY THIS EXISTS
---------------
`advisor_r106_baseline_pairing_test.py` established that each official receipt
carries an independent multiplicative session term

    f := 0.75 ln(bdec/MB_D) + 0.25 ln(bpre/MB_P),     officialScore = cs * e^f

with corr(f, candidate timings) statistically indistinguishable from zero, and
sd(f) measured over the whole scored corpus.  Because the leaderboard ranks on
officialScore and the campaign ranks trees on cs, the record gap has been
priced with the WRONG sigma: the VOI table in the research state uses cs-only
spreads, but a draw against the record is a draw on cs * e^f.

This script recomputes the table with sigma_total = sqrt(sigma_cs^2 + sd(f)^2)
and, because a normal tail assumption is doing real work at z ~ 1.7, also
reports the NONPARAMETRIC probability using the 84 empirical f draws directly.

READ-ONLY.  Usage:
    python3 research/advisor_r106_baseline_lottery_voi.py
"""
import json
import math
import os
import pathlib
import statistics
import urllib.parse
import urllib.request

BENCHMARK = "eigenlabs/mlxfast-challenge"
BASE = os.environ.get("MLXFAST_API_BASE", "https://api.mlx.fast").rstrip("/")
MB_D = 0.013855009542
MB_P = 0.000372473193
RECORD = 2.61650354381456

# merit table from the research state, cs units
TREES = [
    ("4b0e051b", 2.590559, "best-ever cs"),
    ("5a43d329", 2.588750, "round-100 restoration"),
    ("ef055b9b", 2.589321, "Arm R"),
    ("e1b6e2be", 2.587191, ""),
    ("bd33883e", 2.582286, "merged frontier"),
    ("e33efe4e", 2.575633, "== origin/main"),
]

SIGMA_CS = [
    (0.1763, "identical-code per-receipt floor (Rule 89.2 robust within-group)"),
    (0.2494, "1-vs-1 difference sd (Rule 89.2)"),
    (0.5393, "mid estimate"),
    (1.2244, "pooled corpus sd (Rule 89.2)"),
]


def token():
    t = os.environ.get("MLXFAST_API_TOKEN")
    if t:
        return t
    p = pathlib.Path.home() / ".config" / "mlxfast" / "config.json"
    if p.exists():
        return json.loads(p.read_text()).get("token")
    return None


def get(url, tok):
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {tok}"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode())


def phi_sf(z):
    return 0.5 * math.erfc(z / math.sqrt(2))


def main():
    tok = token()
    b = get(f"{BASE}/api/benchmarks/{urllib.parse.quote(BENCHMARK, safe='')}", tok)
    bid = (b.get("benchmark") or b)["id"]
    subs = get(f"{BASE}/api/benchmarks/{bid}/submissions", tok)
    if isinstance(subs, dict):
        subs = subs.get("submissions", subs.get("data", []))

    F = []
    for s in subs:
        if s.get("solverUsername") != "morganmcg1":
            continue
        m = s.get("officialMetrics") or {}
        bd, bp = (m.get("baseline_decode_seconds_per_token"),
                  m.get("baseline_prefill_seconds_per_token"))
        if not (bd and bp):
            continue
        F.append(100 * (0.75 * math.log(bd / MB_D) + 0.25 * math.log(bp / MB_P)))
    F.sort()
    n = len(F)
    sdf = statistics.pstdev(F)
    print(f"empirical session term f over n={n} official receipts (percent):")
    print(f"    mean {statistics.mean(F):+.4f}   sd {sdf:.4f}   "
          f"min {F[0]:+.4f}   max {F[-1]:+.4f}")
    qs = [0.05, 0.25, 0.5, 0.75, 0.90, 0.95, 0.99]
    print("    quantiles: " + "  ".join(
        f"p{int(q*100)}={F[min(n-1, int(q*n))]:+.4f}" for q in qs))
    print(f"    relative SE of this sd = {100/math.sqrt(2*(n-1)):.1f} %")
    # normality check on the term that carries the tail
    sk = sum(((x - statistics.mean(F)) / sdf) ** 3 for x in F) / n
    ku = sum(((x - statistics.mean(F)) / sdf) ** 4 for x in F) / n - 3
    print(f"    skew {sk:+.3f}   excess kurtosis {ku:+.3f}")
    print(f"    record-holder cc6ddc12 needed f = "
          f"{100*math.log(RECORD/2.574594):+.4f} %  "
          f"(z = {100*math.log(RECORD/2.574594)/sdf:.2f}); "
          f"observed count that high in n={n}: "
          f"{sum(1 for x in F if x >= 100*math.log(RECORD/2.574594))}\n")

    for sha, cs, tag in TREES:
        gap = 100 * math.log(RECORD / cs)
        print(f"=== {sha}  cs {cs:.6f}  gap to record {gap:+.4f} %  {tag}")
        emp = sum(1 for x in F if x >= gap) / n
        print(f"    nonparametric (f draws alone, ignores cs noise): "
              f"P={100*emp:.3f} %  "
              f"[{sum(1 for x in F if x >= gap)}/{n}]"
              + (f"  E[draws]={1/emp:.1f}" if emp else "  E[draws]=inf"))
        print(f"    {'sigma_cs':>10} {'sigma_tot':>10} {'z':>7} "
              f"{'P/draw':>9} {'E[draws]':>10} {'h@2.7/h':>9} {'h@0.9/h':>9}")
        for scs, _ in SIGMA_CS:
            st = math.sqrt(scs * scs + sdf * sdf)
            z = gap / st
            p = phi_sf(z)
            ed = 1 / p if p > 0 else float("inf")
            print(f"    {scs:>10.4f} {st:>10.4f} {z:>7.3f} {100*p:>8.3f}% "
                  f"{ed:>10.1f} {ed/2.7:>9.1f} {ed/0.9:>9.1f}")
        # cs-only pricing, i.e. what the research state currently says
        st = SIGMA_CS[1][0]
        z = gap / st
        print(f"    [old cs-only pricing at sigma={st}: z={z:.2f}, "
              f"P={100*phi_sf(z):.5f} %, E[draws]={1/phi_sf(z):,.0f}]")
        print()


if __name__ == "__main__":
    main()
