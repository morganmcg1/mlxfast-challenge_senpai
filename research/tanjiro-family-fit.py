#!/usr/bin/env python3
"""Fit dT(n) = max(0, n*c - slack) on one same-family empty-dispatch series.

Every point must share the same non-empty injection config (sweeps, passes,
matmuls, threadgroups) so that the n = 0 member of the family is the only
reference needed and no cross-family correction is required.

Usage: tanjiro-family-fit.py n0:T0 n1:T1 ...   (n in dispatches, T in ms)
The two largest n are used for the two-parameter fit; every other point is
reported as an out-of-sample residual.
"""
import sys


def main():
    pts = []
    for arg in sys.argv[1:]:
        n, t = arg.split(":")
        pts.append((int(n), float(t)))
    pts.sort()
    if len(pts) < 3 or pts[0][0] != 0:
        raise SystemExit("need an n=0 member and at least two loaded points")

    t0 = pts[0][1]
    print(f"family n=0 reference T = {t0:.5f} ms")
    print(f"{'n':>7} {'T (ms)':>9} {'dT (ms)':>9} {'dT/n (us)':>10}")
    for n, t in pts:
        d = t - t0
        print(f"{n:7d} {t:9.5f} {d:9.4f} {d/n*1000 if n else 0:10.3f}")

    (na, ta), (nb, tb) = pts[-2], pts[-1]
    c = (tb - ta) / (nb - na) * 1000.0  # us per dispatch
    slack = nb * c / 1000.0 - (tb - t0)
    knee = slack / c * 1000.0
    print(f"\nfit from n={na} and n={nb}:")
    print(f"  c     = {c:.3f} us/dispatch")
    print(f"  slack = {slack:.3f} ms")
    print(f"  knee  = {knee:.0f} dispatches")

    print("\nout-of-sample residuals:")
    for n, t in pts[1:-2]:
        pred = max(0.0, n * c / 1000.0 - slack)
        obs = t - t0
        print(f"  n={n:5d}  predicted dT {pred:7.3f}  observed {obs:7.3f}  residual {obs-pred:+7.3f} ms")


if __name__ == "__main__":
    main()
