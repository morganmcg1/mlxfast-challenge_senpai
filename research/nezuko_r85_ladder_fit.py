#!/usr/bin/env python3
"""Fit the R85-D injected-dispatch cost ladder.

usage: nezuko_r85_ladder_fit.py DIR [DIR ...]

Reads `bNN_sNNN_<arm>.steps` dumps written by `research/nezuko_r85_ladder.sh`,
where each file holds per-step decode times in milliseconds. The unit of
replication is the run median with the first WARMUP steps dropped.

Blocks are palindromes, so every arm appears twice per block at mirrored slots.
Block means are removed before fitting (a within-block fixed-effect model) so a
between-block level shift cannot bias the slope; it only enters as variance.
"""
import glob
import math
import os
import re
import statistics
import sys

WARMUP = 16
LAYERS = 40  # LagunaConstants.numHiddenLayers

T95 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365,
       8: 2.306, 9: 2.262, 10: 2.228, 11: 2.201, 12: 2.179, 13: 2.160,
       14: 2.145, 15: 2.131, 16: 2.120, 17: 2.110, 18: 2.101, 19: 2.093,
       20: 2.086, 22: 2.074, 24: 2.064, 26: 2.056, 29: 2.045, 34: 2.032,
       39: 2.023, 49: 2.010, 59: 2.001, 99: 1.984}


def t95(df):
    if df <= 0:
        return float("nan")
    if df in T95:
        return T95[df]
    keys = sorted(T95)
    return T95[min(keys, key=lambda k: abs(k - df))]


def run_median_us(path):
    with open(path) as fh:
        ms = [float(x) for x in fh.read().split() if x.strip()]
    tail = ms[WARMUP:]
    if not tail:
        raise SystemExit(f"{path}: no steps after warmup")
    return statistics.median(1e3 * v for v in tail)


def load(dirs):
    """Return [(block, slot, mode, k, median_us)] for every non-primer run."""
    rows = []
    for d in dirs:
        for p in sorted(glob.glob(os.path.join(d, "b*_s*_*.steps"))):
            m = re.search(r"b(\d+)_s(\d+)_([wt])(\d+)\.steps$", os.path.basename(p))
            if not m:
                continue
            blk = int(m.group(1))
            if blk == 0:  # primer
                continue
            rows.append((f"{d}#{blk}", int(m.group(2)), m.group(3),
                         int(m.group(4)), run_median_us(p)))
    return rows


def ols(xs, ys):
    n = len(xs)
    mx, my = statistics.mean(xs), statistics.mean(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    b = sxy / sxx
    a = my - b * mx
    resid = [y - (a + b * x) for x, y in zip(xs, ys)]
    df = n - 2
    s2 = sum(r * r for r in resid) / df
    se_b = math.sqrt(s2 / sxx)
    se_a = math.sqrt(s2 * (1.0 / n + mx * mx / sxx))
    return a, b, se_a, se_b, df, resid


def report_mode(rows, mode, label):
    sub = [r for r in rows if r[2] == mode]
    if not sub:
        return None
    ks = sorted({r[3] for r in sub})
    print(f"\n=== {label} (mode={mode}) ===")
    print(f"{'K':>4} {'N_extra':>8} {'n':>3} {'median us/step':>15} "
          f"{'sd':>8} {'vs K=0':>10}")
    base = None
    cell = {}
    for k in ks:
        vals = [r[4] for r in sub if r[3] == k]
        m = statistics.median(vals)
        cell[k] = vals
        sd = statistics.stdev(vals) if len(vals) > 1 else float("nan")
        if k == 0:
            base = m
        delta = m - base if base is not None else float("nan")
        print(f"{k:>4} {LAYERS*k:>8} {len(vals):>3} {m:>15.1f} {sd:>8.1f} "
              f"{delta:>10.1f}")

    # Within-block centering: remove each block's mean so a between-block level
    # shift cannot bias the slope.
    blocks = {}
    for b, s, md, k, v in sub:
        blocks.setdefault(b, []).append((k, v))
    xs, ys = [], []
    for b, pts in blocks.items():
        bm = statistics.mean(v for _, v in pts)
        bx = statistics.mean(LAYERS * k for k, _ in pts)
        for k, v in pts:
            xs.append(LAYERS * k - bx)
            ys.append(v - bm)
    a, sl, se_a, se_b, df, _ = ols(xs, ys)
    t = t95(df)
    print(f"within-block slope = {sl:.4f} +- {t*se_b:.4f} us/dispatch "
          f"(95% CI [{sl - t*se_b:.4f}, {sl + t*se_b:.4f}], df={df})")

    # Uncentred fit for the intercept and the linearity check.
    xs2 = [LAYERS * r[3] for r in sub]
    ys2 = [r[4] for r in sub]
    a2, sl2, se_a2, se_b2, df2, _ = ols(xs2, ys2)
    print(f"raw slope = {sl2:.4f} +- {t95(df2)*se_b2:.4f} us/dispatch, "
          f"intercept = {a2:.1f} +- {t95(df2)*se_a2:.1f} us/step")

    # Secants: local slope between consecutive ladder points.
    print("secants (local slope between adjacent ladder points):")
    for k0, k1 in zip(ks, ks[1:]):
        dn = LAYERS * (k1 - k0)
        dv = statistics.median(cell[k1]) - statistics.median(cell[k0])
        print(f"  K {k0:>3} -> {k1:>3}  (+{dn:>5} disp)  "
              f"{dv:>9.1f} us  => {dv/dn:>7.4f} us/dispatch")
    top = ks[len(ks) // 2:]
    if len(top) >= 2:
        dn = LAYERS * (top[-1] - top[0])
        dv = statistics.median(cell[top[-1]]) - statistics.median(cell[top[0]])
        print(f"top-half secant K {top[0]}->{top[-1]}: {dv/dn:.4f} us/dispatch")
    return sl, t * se_b, cell


def main():
    dirs = sys.argv[1:]
    if not dirs:
        raise SystemExit(__doc__)
    rows = load(dirs)
    if not rows:
        raise SystemExit("no ladder runs found")
    print(f"loaded {len(rows)} runs from {len(dirs)} session dir(s)")
    wide = report_mode(rows, "w", "WIDE: 4 KiB per injected dispatch")
    tiny = report_mode(rows, "t", "TINY: 4 B per injected dispatch")
    if wide and tiny:
        sw, ew, _ = wide
        st, et, _ = tiny
        d = sw - st
        se = math.hypot(ew / 1.96, et / 1.96)
        print(f"\nwide - tiny = {d:.4f} +- {1.96*se:.4f} us/dispatch "
              f"(95%); ratio = {sw/st if st else float('nan'):.2f}")


if __name__ == "__main__":
    main()
