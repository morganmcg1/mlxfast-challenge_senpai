#!/usr/bin/env python3
"""fern R109-F: per-shot crown probability straight off the published scores.

Earlier in this round I estimated crown EV as P(draw >= CROWN/normalized),
treating `normalized` as a fixed property of an executable class and `draw` as
the only random variable.  `fern_r109f_leg_noise.py` shows that is wrong:
`normalized` itself has a 0.37 % per-receipt sd, which is the same order as the
draw spread, because the *candidate* legs jitter almost as much as the baseline
legs (candidate decode cv 0.278 % vs baseline decode cv 0.224 %).

So the honest estimator is non-parametric and needs no decomposition at all:
what fraction of recent full-leg receipts published a score above the crown?
Every receipt in the modern cluster is a draw from essentially the same code
(between-package code spread <= 0.16 %), so the empirical exceedance rate over
that cluster *is* our per-shot probability.

Usage:
    python3 research/fern_r109f_crown_ev_empirical.py [receipts.json]
"""

from __future__ import annotations

import json
import math
import statistics
import sys

PATH = sys.argv[1] if len(sys.argv) > 1 else "/tmp/subs_p4.json"

CROWN = 2.61650354381456
REF_D = 0.01385621216015625
REF_P = 0.00036751938916015626
WINDOWS = ["2026-08-06T00", "2026-08-08T00", "2026-08-09T00", "2026-08-10T00"]
DECODE_CLUSTER_MAX_US = 4960.0


def norm(dec: float, pf: float) -> float:
    return (REF_D / dec) ** 0.75 * (REF_P / pf) ** 0.25


def main() -> None:
    rows = json.load(open(PATH))["submissions"]
    recs = []
    for r in rows:
        m = r.get("officialMetrics") or {}
        d = m.get("decode_seconds_per_token")
        p = m.get("prefill_seconds_per_token")
        s = r.get("officialScore")
        if not (d and p and s and m.get("passed_correctness")):
            continue
        recs.append({
            "id": r["id"][:8], "solver": r["solverUsername"],
            "created": (r.get("createdAt") or "")[:19],
            "d": d * 1e6, "p": p * 1e6, "pub": s, "n": norm(d, p),
        })
    recs.sort(key=lambda x: x["created"])

    print("=" * 96)
    print("fern R109-F: empirical per-shot crown probability")
    print("  source=%s  full-leg correct=%d  crown=%.14f" % (PATH, len(recs), CROWN))
    print("=" * 96)

    print("\n[A] instrument comparison: published vs normalized (modern cluster)")
    print("-" * 96)
    for since in WINDOWS:
        sel = [x for x in recs
               if x["created"] >= since and x["d"] <= DECODE_CLUSTER_MAX_US]
        if len(sel) < 4:
            continue
        pub = [x["pub"] for x in sel]
        nz = [x["n"] for x in sel]
        cv_pub = 100.0 * statistics.stdev(pub) / statistics.fmean(pub)
        cv_nz = 100.0 * statistics.stdev(nz) / statistics.fmean(nz)
        print("  since %s  n=%3d  cv_published %6.3f %%  cv_normalized %6.3f %%"
              "  variance ratio %5.2fx  => receipts needed ratio %5.2fx"
              % (since, len(sel), cv_pub, cv_nz,
                 (cv_pub / cv_nz) ** 2, (cv_pub / cv_nz) ** 2))

    print("\n[B] non-parametric exceedance: fraction of receipts above the crown")
    print("-" * 96)
    for since in WINDOWS:
        sel = [x for x in recs
               if x["created"] >= since and x["d"] <= DECODE_CLUSTER_MAX_US]
        if not sel:
            continue
        hits = [x for x in sel if x["pub"] > CROWN]
        n = len(sel)
        k = len(hits)
        p = k / n
        # Wilson 95 % upper bound so that k=0 still yields a usable bound
        z = 1.96
        denom = 1 + z * z / n
        centre = (p + z * z / (2 * n)) / denom
        half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
        lo, hi = max(0.0, centre - half), min(1.0, centre + half)
        best = max(x["pub"] for x in sel)
        print("  since %s  n=%3d  above crown %2d  p=%.4f  95%%CI [%.4f, %.4f]"
              "  best published %.6f (%.4f %% short)"
              % (since, n, k, p, lo, hi, best, 100.0 * (CROWN - best) / CROWN))
        for h in hits:
            print("        HIT %s %s %-14s published %.6f"
                  % (h["id"], h["created"], h["solver"][:14], h["pub"]))

    print("\n[C] shots needed for a 50 %% / 80 %% chance at the crown")
    print("-" * 96)
    for since in WINDOWS:
        sel = [x for x in recs
               if x["created"] >= since and x["d"] <= DECODE_CLUSTER_MAX_US]
        if len(sel) < 10:
            continue
        n = len(sel)
        k = sum(1 for x in sel if x["pub"] > CROWN)
        z = 1.96
        p = k / n
        denom = 1 + z * z / n
        centre = (p + z * z / (2 * n)) / denom
        half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
        hi = min(1.0, centre + half)
        for label, pp in (("point", p), ("optimistic(95%%UB)", hi)):
            if pp <= 0:
                print("  since %s  %-20s p=0 -> unbounded" % (since, label))
                continue
            n50 = math.log(0.5) / math.log(1 - pp)
            n80 = math.log(0.2) / math.log(1 - pp)
            print("  since %s  %-20s p=%.4f  n(50%%)=%6.1f  n(80%%)=%6.1f"
                  "  -> at 22 min/shot: %5.1f h / %5.1f h"
                  % (since, label, pp, n50, n80, n50 * 22 / 60, n80 * 22 / 60))

    print("\n[D] what published score would a mean-code shot need to beat?")
    print("-" * 96)
    sel = [x for x in recs if x["created"] >= "2026-08-09T00"
           and x["d"] <= DECODE_CLUSTER_MAX_US]
    pub = [x["pub"] for x in sel]
    mu, sd = statistics.fmean(pub), statistics.stdev(pub)
    print("  modern cluster published mean %.6f sd %.6f (cv %.3f %%)  n=%d"
          % (mu, sd, 100 * sd / mu, len(sel)))
    print("  crown is %+.2f sd above that mean" % ((CROWN - mu) / sd))
    need = (CROWN - mu) / mu * 100.0
    print("  a *code* improvement of %+.3f %% would put the mean shot on the crown"
          % need)
    print("  ... but between-package code spread in this cluster is <= 0.16 %%,")
    print("      so no reachable code change closes it; only the tail does.")


if __name__ == "__main__":
    main()
