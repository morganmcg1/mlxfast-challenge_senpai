#!/usr/bin/env python3
"""Analyse a position-balanced ABBA arm screen from a probe log.

Reads `[pNN-X] steps=... wall_ms_per_step=...` lines (research/frieren_cap_abba.sh
or any script using research/frieren_host_cpu_probe.py with `pNN-ARM` labels),
drops the discard arm, and reports three estimators of the A->B contrast:

  1. pooled means (ignores drift; what the unbalanced sweep reported)
  2. within-block paired differences (cancels any drift smooth over 4 arms)
  3. OLS with a linear position term (cancels a global linear trend)

Research-only.
"""

import re
import statistics
import sys

LINE = re.compile(r"\[p(\d+)-([AB])\] steps=\d+ wall_ms_per_step=([0-9.]+)")


def ols_two_predictor(y, x1, x2):
    """OLS y = b0 + b1*x1 + b2*x2 via normal equations; returns (b, se)."""
    n = len(y)
    cols = [[1.0] * n, x1, x2]
    k = 3
    xtx = [[sum(cols[i][t] * cols[j][t] for t in range(n)) for j in range(k)]
           for i in range(k)]
    xty = [sum(cols[i][t] * y[t] for t in range(n)) for i in range(k)]
    # Gauss-Jordan inverse of a 3x3 symmetric matrix.
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
    return beta, se


def main():
    text = open(sys.argv[1], errors="replace").read()
    arms = [(int(p), a, float(v)) for p, a, v in LINE.findall(text)]
    arms = [(p, a, v) for p, a, v in arms if p > 0]
    if not arms:
        sys.exit("no arm lines found")
    print(f"{'pos':>4} {'arm':>3} {'ms/step':>9}")
    for p, a, v in arms:
        print(f"{p:>4} {a:>3} {v:>9.4f}")

    va = [v for _, a, v in arms if a == "A"]
    vb = [v for _, a, v in arms if a == "B"]
    ma, mb = statistics.mean(va), statistics.mean(vb)
    sea = statistics.stdev(va) / len(va) ** 0.5 if len(va) > 1 else 0.0
    seb = statistics.stdev(vb) / len(vb) ** 0.5 if len(vb) > 1 else 0.0
    sed = (sea * sea + seb * seb) ** 0.5
    print(f"\npooled  A n={len(va)} {ma:.4f} se {sea:.4f}"
          f" | B n={len(vb)} {mb:.4f} se {seb:.4f}")
    print(f"pooled  delta {mb - ma:+.4f} ms = {(mb - ma) / ma * 100:+.3f}%"
          f" +/- {sed / ma * 100:.3f}%  t={(mb - ma) / sed if sed else 0:+.2f}")

    blocks, diffs = [], []
    for start in range(0, len(arms) - 3, 4):
        blk = arms[start:start + 4]
        ba = [v for _, a, v in blk if a == "A"]
        bb = [v for _, a, v in blk if a == "B"]
        if len(ba) == 2 and len(bb) == 2:
            d = statistics.mean(bb) - statistics.mean(ba)
            blocks.append((blk[0][0], statistics.mean(ba),
                           statistics.mean(bb), d))
            diffs.append(d)
    print(f"\n{'block@pos':>10} {'A mean':>9} {'B mean':>9} {'B-A':>9}")
    for p, a, b, d in blocks:
        print(f"{p:>10} {a:>9.4f} {b:>9.4f} {d:>+9.4f}")
    if len(diffs) > 1:
        md = statistics.mean(diffs)
        sd = statistics.stdev(diffs) / len(diffs) ** 0.5
        print(f"paired  delta {md:+.4f} ms = {md / ma * 100:+.3f}%"
              f" +/- {sd / ma * 100:.3f}%  t({len(diffs) - 1})="
              f"{md / sd if sd else 0:+.2f}")

    y = [v for _, _, v in arms]
    pos = [float(p) for p, _, _ in arms]
    isb = [1.0 if a == "B" else 0.0 for _, a, _ in arms]
    beta, se = ols_two_predictor(y, pos, isb)
    print(f"\nOLS     drift {beta[1]:+.4f} ms/position (se {se[1]:.4f})")
    print(f"OLS     delta {beta[2]:+.4f} ms = {beta[2] / ma * 100:+.3f}%"
          f" +/- {se[2] / ma * 100:.3f}%  t={beta[2] / se[2] if se[2] else 0:+.2f}")


if __name__ == "__main__":
    main()
