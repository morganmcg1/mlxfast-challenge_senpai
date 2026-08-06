#!/usr/bin/env python3
"""Drift-adjusted arm estimate for the PR #72 counterbalanced timing series.

Fits  y = a + b*slot + d*arm   (arm = 0 base, 1 cand)  by OLS and reports the
arm coefficient as a percentage of the base mean, alongside the unadjusted
difference. Also reports the adjacent-pair (local) estimator, which uses only
neighbouring C/B slots and so is insensitive to any smooth session trend.

Usage: drift.py [newbase|oldbase]     (default newbase = campaign B)

All percentages use the *reduction* convention  (base - cand) / base, matching
analyze.py.
"""
import json
import os
import statistics as st
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CAMPAIGNS = {
    # campaign B, advisor base ab1f9a1, executed C B B C B C
    "newbase": [
        ("cand", "newbase_cand_r1.json"),
        ("base", "newbase_base_r1.json"),
        ("base", "newbase_base_r2.json"),
        ("cand", "newbase_cand_r2.json"),
        ("base", "newbase_base_r3.json"),
        ("cand", "newbase_cand_r3.json"),
    ],
    # campaign A, old base 00374ba, executed B C B C B C B
    "oldbase": [
        ("base", "base_r1.json"),
        ("cand", "cand_r1.json"),
        ("base", "base_r2.json"),
        ("cand", "cand_r2.json"),
        ("base", "base_r3.json"),
        ("cand", "cand_r3.json"),
        ("base", "base_r4.json"),
    ],
}
ORDER = CAMPAIGNS[sys.argv[1] if len(sys.argv) > 1 else "newbase"]
KEYS = {"decode": "decode_seconds_per_token", "prefill": "prefill_seconds_per_token"}


def load():
    rows = []
    for slot, (arm, fn) in enumerate(ORDER, start=1):
        try:
            m = json.load(open(os.path.join(HERE, fn)))["metrics"]
        except FileNotFoundError:
            print(f"  (missing {fn} -- slot {slot} skipped)")
            continue
        assert m["passed_correctness"] and m["max_abs_diff"] == 0, fn
        rows.append((slot, arm, fn, m))
    return rows


def ols3(rows, key):
    """Least squares for y = a + b*slot + d*isCand, solved via normal equations."""
    X = [[1.0, float(s), 1.0 if a == "cand" else 0.0] for s, a, _, _ in rows]
    y = [m[key] for _, _, _, m in rows]
    n, p = len(X), 3
    A = [[sum(X[i][r] * X[i][c] for i in range(n)) for c in range(p)] for r in range(p)]
    b = [sum(X[i][r] * y[i] for i in range(n)) for r in range(p)]
    # Gauss-Jordan
    M = [A[r][:] + [b[r]] for r in range(p)]
    for col in range(p):
        piv = max(range(col, p), key=lambda r: abs(M[r][col]))
        M[col], M[piv] = M[piv], M[col]
        d = M[col][col]
        M[col] = [v / d for v in M[col]]
        for r in range(p):
            if r != col and M[r][col]:
                f = M[r][col]
                M[r] = [M[r][k] - f * M[col][k] for k in range(p + 1)]
    return [M[r][p] for r in range(p)]


def adjacent(rows, key):
    """Mean of every C/B difference between immediately neighbouring slots."""
    diffs = []
    for i in range(len(rows) - 1):
        a1, a2 = rows[i][1], rows[i + 1][1]
        if a1 == a2:
            continue
        y1, y2 = rows[i][3][key], rows[i + 1][3][key]
        base_v, cand_v = (y1, y2) if a1 == "base" else (y2, y1)
        diffs.append((base_v - cand_v) / base_v * 100.0)
    return diffs


rows = load()
print("slot arm  file                              decode        prefill")
for s, a, fn, m in rows:
    print(f"{s:>4} {a:5s} {fn:32s} {m[KEYS['decode']]:.9f} {m[KEYS['prefill']]:.9f}")

for name, key in KEYS.items():
    ys = [m[key] for _, _, _, m in rows]
    bm = st.mean([m[key] for _, a, _, m in rows if a == "base"])
    cm = st.mean([m[key] for _, a, _, m in rows if a == "cand"])
    a0, slope, arm = ols3(rows, key)
    d = adjacent(rows, key)
    print(f"\n== {name} ==")
    print(f"  unadjusted arm difference : {(bm - cm) / bm * 100:+.4f}%")
    print(f"  session slope             : {slope * 1e6:+.3f} us per slot "
          f"({slope / bm * 100:+.4f}% per slot)")
    print(f"  drift-adjusted arm effect : {-arm / bm * 100:+.4f}%")
    print(f"  adjacent-pair diffs       : "
          + ", ".join(f"{v:+.4f}%" for v in d))
    print(f"  adjacent-pair mean        : {st.mean(d):+.4f}%"
          + (f"  sd {st.stdev(d):.4f}%" if len(d) > 1 else ""))
