#!/usr/bin/env python3
"""READ-ONLY: decompose one public submission row into tree quality x draw luck.

published = normalized x draw, where
  normalized = (D0/decode)^0.75 x (P0/prefill)^0.25
with the harness constants below.  Applied uniformly to every row of the public
collection (the same decomposition behind the 1280-row draw distribution in
research/fern-r109f-cedar-endgame-memo.md), so it answers the only question
that matters for the remaining shots:

  a rejected shot -- was it an unlucky draw of a good tree, or a slower tree?

If the tree is as good as our best-known tree, keep firing it; if the draw was
merely unlucky, firing the same tree again is the highest-value action.  If the
tree is measurably slower, the fleet should fire whichever tree has the best
measured normalized value instead.

Usage: python3 research/fern_r109f_draw_decompose.py <queue.json> <id-prefix> [...]
"""
import json
import statistics
import sys

D0 = 0.01385621216015625
P0 = 0.00036751938916015626
BAR = 2.61955310948
OUR_BEST_NORMALIZED = 2.582263      # ledger 3 / memo
CROWN_NORMALIZED = 2.576540         # crown holder's own tree
DRAW_MEDIAN = 1.001830              # 1280-row draw distribution
DRAW_SD = 0.005394


def metrics(row):
    m = row.get("officialMetrics") or {}
    if not isinstance(m, dict):
        return None, None
    dec = pre = None
    for k, v in m.items():
        kl = k.lower()
        try:
            v = float(v)
        except (TypeError, ValueError):
            continue
        if "decode" in kl and dec is None:
            dec = v
        elif "prefill" in kl and pre is None:
            pre = v
    return dec, pre


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    path, prefixes = argv[0], argv[1:]
    doc = json.load(open(path))
    rows = doc.get("submissions", doc)

    for pref in prefixes:
        hit = [r for r in rows if str(r.get("id", "")).startswith(pref)]
        if not hit:
            print(f"{pref}: not found")
            continue
        r = hit[0]
        pub = r.get("officialScore")
        dec, pre = metrics(r)
        print(f"\n=== {pref}  user={r.get('solverUsername')}  status={r.get('status')} ===")
        print(f"published officialScore = {pub}")
        if dec is None or pre is None or not pub:
            print(f"officialMetrics keys = {sorted((r.get('officialMetrics') or {}).keys())}")
            print("cannot decompose: decode/prefill not both present")
            continue
        norm = (D0 / dec) ** 0.75 * (P0 / pre) ** 0.25
        draw = float(pub) / norm
        print(f"decode={dec:.8f}  prefill={pre:.10f}")
        print(f"normalized (tree quality) = {norm:.6f}")
        print(f"draw (channel luck)       = {draw:.6f}   "
              f"({(draw-DRAW_MEDIAN)/DRAW_SD:+.2f} sd vs draw median {DRAW_MEDIAN})")
        print(f"tree vs our best {OUR_BEST_NORMALIZED}: "
              f"{(norm/OUR_BEST_NORMALIZED-1)*100:+.3f} %")
        print(f"tree vs crown's tree {CROWN_NORMALIZED}: "
              f"{(norm/CROWN_NORMALIZED-1)*100:+.3f} %")
        need = BAR / norm
        print(f"draw needed from THIS tree to take the crown = {need:.6f} "
              f"({(need-1)*100:+.3f} %, {(need-DRAW_MEDIAN)/DRAW_SD:.2f} sd)")
        need_ours = BAR / OUR_BEST_NORMALIZED
        print(f"draw needed from OUR BEST tree               = {need_ours:.6f} "
              f"({(need_ours-1)*100:+.3f} %, {(need_ours-DRAW_MEDIAN)/DRAW_SD:.2f} sd)")

    # empirical exceedance of both thresholds over the whole decomposable trace
    draws = []
    for r in rows:
        pub = r.get("officialScore")
        dec, pre = metrics(r)
        if pub and dec and pre:
            norm = (D0 / dec) ** 0.75 * (P0 / pre) ** 0.25
            draws.append(float(pub) / norm)
    if draws:
        draws.sort()
        n = len(draws)
        print(f"\n=== empirical draw distribution, n={n} decomposable rows ===")
        print(f"median {statistics.median(draws):.6f}  sd {statistics.pstdev(draws):.6f}  "
              f"max {draws[-1]:.6f}")
        for label, thr in (("our best tree", BAR / OUR_BEST_NORMALIZED),):
            k = sum(1 for d in draws if d >= thr)
            p = k / n
            se = (p * (1 - p) / n) ** 0.5
            print(f"P(draw >= {thr:.6f}) from {label}: {k}/{n} = {p:.2%} "
                  f"(95 % CI {max(p-1.96*se,0):.2%}-{p+1.96*se:.2%})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
