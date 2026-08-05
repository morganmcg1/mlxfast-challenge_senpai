#!/usr/bin/env python3
"""Analyse a mirrored multi-level MLX_MAX_MB_PER_BUFFER screen.

Reads `[pNN-mbLEVEL] steps=... wall_ms_per_step=...` lines produced by
research/nezuko_mbpb_levels.sh, drops the discard arm, and reports for each
level, against the 200 MB reference:

  1. pooled means (ignores drift)
  2. within-block paired differences (cancels drift smooth over one block)
  3. OLS with a linear position term (cancels a global linear trend)

Research-only.
"""

import re
import statistics
import sys

LINE = re.compile(r"\[p(\d+)-mb(\d+)\] steps=\d+ wall_ms_per_step=([0-9.]+)")
REF = 200
BLOCK = 5


def ols(y, cols):
    """OLS via normal equations; returns (beta, se, df)."""
    n = len(y)
    k = len(cols)
    xtx = [[sum(cols[i][t] * cols[j][t] for t in range(n)) for j in range(k)]
           for i in range(k)]
    xty = [sum(cols[i][t] * y[t] for t in range(n)) for i in range(k)]
    aug = [row[:] + [1.0 if i == j else 0.0 for j in range(k)]
           for i, row in enumerate(xtx)]
    for col in range(k):
        piv = max(range(col, k), key=lambda r: abs(aug[r][col]))
        aug[col], aug[piv] = aug[piv], aug[col]
        pval = aug[col][col]
        aug[col] = [v / pval for v in aug[col]]
        for r in range(k):
            if r != col and aug[r][col] != 0.0:
                f = aug[r][col]
                aug[r] = [v - f * w for v, w in zip(aug[r], aug[col])]
    inv = [row[k:] for row in aug]
    beta = [sum(inv[i][j] * xty[j] for j in range(k)) for i in range(k)]
    resid = [y[t] - sum(beta[i] * cols[i][t] for i in range(k))
             for t in range(n)]
    s2 = sum(r * r for r in resid) / (n - k)
    se = [(s2 * inv[i][i]) ** 0.5 for i in range(k)]
    return beta, se, n - k


def tstat(vals):
    n = len(vals)
    if n < 2:
        return float("nan"), 0
    m = statistics.fmean(vals)
    sd = statistics.stdev(vals)
    if sd == 0:
        return float("inf") if m else 0.0, n - 1
    return m / (sd / n ** 0.5), n - 1


def main():
    text = open(sys.argv[1], errors="replace").read()
    arms = [(int(p), int(mb), float(v)) for p, mb, v in LINE.findall(text)]
    arms = [a for a in arms if a[0] > 0]
    if not arms:
        sys.exit("no arm lines found")

    print(f"{'pos':>4} {'blk':>4} {'mb':>5} {'ms/step':>9}")
    for p, mb, v in arms:
        print(f"{p:>4} {(p - 1) // BLOCK:>4} {mb:>5} {v:>9.4f}")

    levels = sorted({mb for _, mb, _ in arms}, reverse=True)
    by_level = {L: [v for _, mb, v in arms if mb == L] for L in levels}
    by_block = {}
    for p, mb, v in arms:
        by_block.setdefault((p - 1) // BLOCK, {})[mb] = v
    ref_mean = statistics.fmean(by_level[REF])

    print(f"\npooled means (reference {REF} MB = {ref_mean:.4f} ms)")
    print(f"{'mb':>5} {'n':>3} {'mean':>9} {'sd':>7} {'delta%':>8}")
    for L in levels:
        vals = by_level[L]
        sd = statistics.stdev(vals) if len(vals) > 1 else float("nan")
        print(f"{L:>5} {len(vals):>3} {statistics.fmean(vals):>9.4f} "
              f"{sd:>7.4f} {(statistics.fmean(vals) / ref_mean - 1) * 100:>+8.2f}")

    print(f"\nwithin-block paired differences vs {REF} MB (verdict estimator)")
    print(f"{'mb':>5} {'n':>3} {'d_ms':>8} {'sd':>7} {'d%':>7} {'t':>7} {'df':>3}")
    for L in levels:
        if L == REF:
            continue
        diffs, rels = [], []
        for b, row in sorted(by_block.items()):
            if L in row and REF in row:
                diffs.append(row[L] - row[REF])
                rels.append((row[L] / row[REF] - 1) * 100)
        if not diffs:
            continue
        t, df = tstat(rels)
        sd = statistics.stdev(diffs) if len(diffs) > 1 else float("nan")
        print(f"{L:>5} {len(diffs):>3} {statistics.fmean(diffs):>+8.4f} "
              f"{sd:>7.4f} {statistics.fmean(rels):>+7.2f} {t:>+7.2f} {df:>3}")

    print("\nOLS with linear position term (level dummies vs "
          f"{REF} MB, in % of {REF} MB)")
    y = [v / ref_mean * 100 for _, _, v in arms]
    pos = [float(p) for p, _, _ in arms]
    pos_c = [p - statistics.fmean(pos) for p in pos]
    dummies = [L for L in levels if L != REF]
    cols = [[1.0] * len(y), pos_c]
    for L in dummies:
        cols.append([1.0 if mb == L else 0.0 for _, mb, _ in arms])
    beta, se, df = ols(y, cols)
    print(f"{'term':>10} {'coef%':>8} {'se':>7} {'t':>7}  df={df}")
    print(f"{'position':>10} {beta[1]:>+8.3f} {se[1]:>7.3f} "
          f"{beta[1] / se[1]:>+7.2f}")
    for i, L in enumerate(dummies):
        j = 2 + i
        print(f"{('mb' + str(L)):>10} {beta[j]:>+8.3f} {se[j]:>7.3f} "
              f"{beta[j] / se[j]:>+7.2f}")


if __name__ == "__main__":
    main()
