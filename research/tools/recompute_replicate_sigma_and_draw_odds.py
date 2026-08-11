#!/usr/bin/env python3
"""Independently recompute sigma(one official draw at fixed program) from the r103
replicate artifact, and price a re-draw of an unchanged tree against the bar.

Why this exists: the manifest's earlier claim "sigma(one official draw) has never been
measured by replication" was false, and the sigma it quoted (0.49 %) was a cross-code
modelled figure. This script recomputes the within-group dispersion FROM THE PER-RECEIPT
SCORES (not from the artifact's own pooled fields), so the manifest number is reproducible
and independent of the artifact's summary arithmetic.

Usage:
    python3 research/tools/recompute_replicate_sigma_and_draw_odds.py
"""

from __future__ import annotations

import json
import math
import os
import statistics as st

ART = os.path.join("research", "artifacts", "advisor-r103", "replicate-sigma.json")
BAR = 2.6195531094824  # organizer bar, receipt cdcd091
BEST = 2.60664970  # e27f1ce, best-ever draw on the shared account


def phi(z: float) -> float:
    """Standard normal CDF."""
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def pull_scores(receipts: list) -> list:
    out = []
    for r in receipts:
        for key in ("candidateScore", "candidate_score", "score", "cs"):
            v = r.get(key) if isinstance(r, dict) else None
            if isinstance(v, (int, float)) and v > 0:
                out.append(float(v))
                break
    return out


def main() -> None:
    d = json.load(open(ART))
    groups = d["groups"]
    print(f"artifact: {ART}")
    print(f"receipts fetched: {d.get('n_receipts')}  commits: {d.get('n_commits')}")
    print(f"artifact-reported trimmed pooled sd(ln cs) %: {d.get('trimmed_pooled_sd_ln_cs_pct')}")
    print(f"artifact-reported pooled  sd(ln cs) %: {d.get('pooled_sd_ln_cs_pct')} "
          f"(dof {d.get('pooled_sd_ln_cs_pct_dof')})")
    print()

    rows = []
    for g in groups:
        cs = pull_scores(g.get("receipts") or [])
        if len(cs) < 2:
            continue
        lns = [math.log(x) for x in cs]
        sd = st.stdev(lns) * 100.0
        rows.append((g["digest"][:8], len(cs), sd, g.get("sd_ln_cs_pct"),
                     g.get("mean_D"), g.get("mean_P"), sorted(cs)))

    rows.sort(key=lambda r: -r[2])
    print(f"{'digest':10s} {'n':>2s} {'recomputed sd(ln cs)%':>22s} {'artifact%':>10s} "
          f"{'mean_D':>10s} {'mean_P':>8s}")
    for dig, n, sd, sd_art, mD, mP, cs in rows:
        mDs = f"{mD:.3f}" if isinstance(mD, (int, float)) else "-"
        mPs = f"{mP:.3f}" if isinstance(mP, (int, float)) else "-"
        sda = f"{sd_art:.4f}" if isinstance(sd_art, (int, float)) else "-"
        print(f"{dig:10s} {n:2d} {sd:22.4f} {sda:>10s} {mDs:>10s} {mPs:>8s}")
        print(f"{'':10s}    scores: {['%.4f' % x for x in cs]}")

    def pooled(rs):
        num = sum((n - 1) * sd * sd for _, n, sd, *_ in rs)
        dof = sum(n - 1 for _, n, _, *_ in rs)
        return math.sqrt(num / dof), dof

    all_sd, all_dof = pooled(rows)
    # trim the single pathological group (contention/thermal excursion regime)
    worst = rows[0][0]
    trim = [r for r in rows if r[0] != worst]
    tr_sd, tr_dof = pooled(trim)
    print()
    print(f"pooled (all {len(rows)} groups)      sd(ln cs) = {all_sd:.4f} %  dof {all_dof}")
    print(f"pooled (trim {worst})       sd(ln cs) = {tr_sd:.4f} %  dof {tr_dof}")
    worst_ok = max(r[2] for r in trim)
    print(f"worst well-behaved single group sd  = {worst_ok:.4f} %")

    gap = (BAR - BEST) / BEST * 100.0
    print()
    print(f"gap to bar: ({BAR} - {BEST}) / {BEST} = {gap:.4f} %")
    print()
    print(f"{'sigma%':>8s} {'gain%':>7s} {'z':>7s} {'P(1 draw)':>10s} {'P(3 draws)':>11s}")
    for sigma in (worst_ok, tr_sd):
        for gain in (0.0, 0.26, 0.50):
            z = (gap - gain) / sigma
            p1 = 1.0 - phi(z)
            print(f"{sigma:8.4f} {gain:7.2f} {z:7.3f} {p1*100:9.2f}% "
                  f"{(1-(1-p1)**3)*100:10.2f}%")

    # score-model consistency check on the reference group
    for dig, n, sd, sd_art, mD, mP, cs in rows:
        if dig.startswith("dc437b0e"):
            g = next(x for x in groups if x["digest"].startswith("dc437b0e"))
            sdD = g["sd_D_us"] / g["mean_D"] * 100.0
            sdP = g["sd_P_us"] / g["mean_P"] * 100.0
            comb = math.sqrt((0.75 * sdD) ** 2 + (0.25 * sdP) ** 2)
            print()
            print(f"consistency check on dc437b0e: 0.75*sd(lnD)={0.75*sdD:.4f} % + "
                  f"0.25*sd(lnP)={0.25*sdP:.4f} % -> {comb:.4f} % vs observed {sd:.4f} %")
            print(f"  1 us/step on the ranked host = {1.0/g['mean_D']*0.75*100:.5f} % of score "
                  f"(mean_D = {g['mean_D']:.3f} us/step)")


if __name__ == "__main__":
    main()
