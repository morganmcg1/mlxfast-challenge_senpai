#!/usr/bin/env python3
"""READ-ONLY: measure channel draw noise from SAME-COMMIT repeat submissions.

Why re-derive this.  The published score is a deterministic function of the two
reported speedups:

    officialScore = decode_speedup**0.75 * prefill_speedup**0.25

(verified here to ~1e-6 on every decomposable row).  So there is no separate
"draw" multiplier hiding in the scoring formula: all run-to-run luck lives in
the measured speedups themselves.  The right way to size that luck is therefore
to take commits that were submitted more than once and look at the spread of
their official scores -- same tree, different draw.

Outputs
  1. verification of the scoring identity,
  2. within-commit relative spread, pooled across all repeated commits,
  3. the resulting P(a fresh draw of our best tree clears the bar), by the
     pooled empirical distribution and by a normal approximation.

Usage: python3 research/fern_r109f_same_commit_draws.py <queue.json> [...]
"""
import collections
import json
import math
import statistics
import sys

BAR = 2.61955310948          # crown to beat
OUR_BEST_SHA = "5c542169b5e6c295805f50fa65df3150816eb443"  # receipt e27f1ce, 2.60664969895906


def load(paths):
    seen, rows = set(), []
    for p in paths:
        doc = json.load(open(p))
        for r in doc.get("submissions", doc):
            i = r.get("id")
            if i not in seen:
                seen.add(i)
                rows.append(r)
    return rows


def scored(rows):
    out = []
    for r in rows:
        s = r.get("officialScore")
        m = r.get("officialMetrics") or {}
        if not s or not isinstance(m, dict):
            continue
        d, p = m.get("decode_speedup"), m.get("prefill_speedup")
        if not d or not p:
            continue
        out.append((r, float(s), float(d), float(p)))
    return out


def main(argv):
    rows = load(argv or ["research/fern-r109f-queue-1310Z.json"])
    sc = scored(rows)
    print(f"rows={len(rows)}  scored+metrics={len(sc)}")

    err = [abs(s / (d ** 0.75 * p ** 0.25) - 1) for _, s, d, p in sc]
    print(f"\n1. scoring identity officialScore == decode^0.75 * prefill^0.25")
    print(f"   max relative error over {len(err)} rows = {max(err):.2e}"
          f"   (median {statistics.median(err):.2e})")

    by = collections.defaultdict(list)
    for r, s, d, p in sc:
        sha = r.get("submissionCommitSha")
        if sha:
            by[sha].append((r, s, d, p))
    rep = {k: v for k, v in by.items() if len(v) >= 2}
    print(f"\n2. repeated commits: {len(rep)} commits with >=2 scored rows"
          f"  ({sum(len(v) for v in rep.values())} rows)")

    pooled, per_commit = [], []
    for sha, v in rep.items():
        ss = [s for _, s, _, _ in v]
        med = statistics.median(ss)
        for s in ss:
            pooled.append(s / med)
        if len(ss) >= 3:
            per_commit.append((len(ss), statistics.pstdev(ss) / med, sha[:8],
                               min(ss), max(ss), max(ss) / min(ss) - 1))
    per_commit.sort(reverse=True)
    print(f"   {'n':>3}  {'rel sd':>7}  {'commit':>8}  {'min':>10}  {'max':>10}  {'spread':>7}")
    for n, sd, sha, lo, hi, spread in per_commit[:12]:
        print(f"   {n:3d}  {sd:6.3%}  {sha:>8}  {lo:10.6f}  {hi:10.6f}  {spread:6.3%}")

    pooled.sort()
    sd = statistics.pstdev(pooled)
    print(f"\n   pooled within-commit ratio: n={len(pooled)}  sd={sd:.4%}"
          f"  p05={pooled[int(.05*len(pooled))]:.5f}"
          f"  p95={pooled[int(.95*len(pooled))]:.5f}  max={pooled[-1]:.5f}")

    ours = by.get(OUR_BEST_SHA, [])
    if ours:
        ss = sorted(s for _, s, _, _ in ours)
        med = statistics.median(ss)
        need = BAR / med
        k = sum(1 for x in pooled if x >= need)
        p = k / len(pooled)
        se = math.sqrt(max(p * (1 - p), 1e-12) / len(pooled))
        z = (need - 1) / sd
        gauss = 0.5 * math.erfc(z / math.sqrt(2))
        print(f"\n3. our best tree {OUR_BEST_SHA[:8]}: n={len(ss)} official rows,"
              f" median {med:.6f}, max {ss[-1]:.6f}")
        print(f"   needed ratio to clear {BAR}: {need:.6f} ({(need-1)*100:+.3f} %,"
              f" z={z:.2f} on pooled sd)")
        print(f"   empirical P(fresh draw clears bar) = {k}/{len(pooled)} = {p:.2%}"
              f"  (95 % CI {max(p-1.96*se,0):.2%}-{p+1.96*se:.2%})")
        print(f"   normal approximation               = {gauss:.2%}"
              f"   -> tail is {'fatter' if p > gauss else 'thinner'} than normal")
        for shots in (1, 2, 3, 4, 6):
            print(f"     {shots} shot(s): empirical {1-(1-p)**shots:6.2%}"
                  f"   normal {1-(1-gauss)**shots:6.2%}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
