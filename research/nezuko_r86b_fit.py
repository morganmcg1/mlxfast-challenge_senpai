#!/usr/bin/env python3
"""Fit the R86-B in-situ boundary-price ladder and size sweep.

usage: nezuko_r86b_fit.py [--csv OUT.csv] DIR [DIR ...]

Reads the per-step decode dumps written by `research/nezuko_r86b_ladder.sh`
(`bNN_sNNN_<w|t><inserts>.steps`) and `research/nezuko_r86b_size.sh`
(`bNN_sNNN_z<width>_<inserts>.steps`). Each file holds per-step decode times in
milliseconds; the unit of replication is the run median with the first WARMUP
steps dropped.

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
LAYERS = 40  # LagunaConstants.numHiddenLayers on this base
PCT_PER_US = 0.015280  # % of score per us/step of decode

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
    return T95[min(sorted(T95), key=lambda k: abs(k - df))]


def run_median_us(path):
    with open(path) as fh:
        ms = [float(x) for x in fh.read().split() if x.strip()]
    tail = ms[WARMUP:]
    if not tail:
        raise SystemExit(f"{path}: no steps after warmup")
    return statistics.median(1e3 * v for v in tail)


def load_ladder(dirs):
    """Return [(block, slot, mode, inserts, median_us)] for non-primer runs.

    Mode `o` is the env-unset arm: the instrument call is present in the binary
    but returns its argument before touching MLX.
    """
    rows = []
    for d in dirs:
        for p in sorted(glob.glob(os.path.join(d, "b*_s*_*.steps"))):
            m = re.search(r"b(\d+)_s(\d+)_(off|[wt]\d+)\.steps$",
                          os.path.basename(p))
            if not m or int(m.group(1)) == 0:
                continue
            arm = m.group(3)
            mode, inserts = ("o", 0) if arm == "off" else (arm[0], int(arm[1:]))
            rows.append((f"{d}#{m.group(1)}", int(m.group(2)), mode, inserts,
                         run_median_us(p)))
    return rows


def load_size(dirs):
    """Return [(block, slot, width_elems, inserts, median_us)]."""
    rows = []
    for d in dirs:
        for p in sorted(glob.glob(os.path.join(d, "b*_s*_z*.steps"))):
            m = re.search(r"b(\d+)_s(\d+)_z(\d+)_(\d+)\.steps$", os.path.basename(p))
            if not m or int(m.group(1)) == 0:
                continue
            rows.append((f"{d}#{m.group(1)}", int(m.group(2)), int(m.group(3)),
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
    return a, b, math.sqrt(s2 * (1.0 / n + mx * mx / sxx)), math.sqrt(s2 / sxx), df


def report_mode(rows, mode, label, csv):
    sub = [r for r in rows if r[2] == mode]
    if not sub:
        return None
    ins = sorted({r[3] for r in sub})
    print(f"\n=== {label} (mode={mode}) ===")
    print(f"{'inserts':>8} {'k':>6} {'n':>3} {'median us/step':>15} {'IQR':>8} "
          f"{'sd':>8} {'vs k=0':>10}")
    base, cell = None, {}
    for a in ins:
        vals = sorted(r[4] for r in sub if r[3] == a)
        cell[a] = vals
        med = statistics.median(vals)
        q = (vals[int(0.75 * (len(vals) - 1))] - vals[int(0.25 * (len(vals) - 1))]
             if len(vals) > 3 else float("nan"))
        sd = statistics.stdev(vals) if len(vals) > 1 else float("nan")
        if a == 0:
            base = med
        print(f"{a:>8} {LAYERS*a:>6} {len(vals):>3} {med:>15.1f} {q:>8.1f} "
              f"{sd:>8.1f} {med - base:>10.1f}")
        if csv is not None:
            csv.append(["ladder", mode, a, LAYERS * a, len(vals), f"{med:.2f}",
                        f"{sd:.2f}", f"{med - base:.2f}"])

    blocks = {}
    for b, _s, _m, a, v in sub:
        blocks.setdefault(b, []).append((a, v))
    xs, ys = [], []
    for pts in blocks.values():
        bm = statistics.mean(v for _, v in pts)
        bx = statistics.mean(LAYERS * a for a, _ in pts)
        for a, v in pts:
            xs.append(LAYERS * a - bx)
            ys.append(v - bm)
    _a, sl, _sea, seb, df = ols(xs, ys)
    t = t95(df)
    print(f"within-block slope = {sl:.4f} +- {t*seb:.4f} us/boundary "
          f"(95% CI [{sl - t*seb:.4f}, {sl + t*seb:.4f}], df={df}, n={len(xs)})")

    a2, sl2, sea2, seb2, df2 = ols([LAYERS * r[3] for r in sub],
                                   [r[4] for r in sub])
    print(f"raw slope = {sl2:.4f} +- {t95(df2)*seb2:.4f} us/boundary, "
          f"intercept = {a2:.1f} +- {t95(df2)*sea2:.1f} us/step")

    print("secants (local slope between adjacent rungs):")
    for a0, a1 in zip(ins, ins[1:]):
        dn = LAYERS * (a1 - a0)
        dv = statistics.median(cell[a1]) - statistics.median(cell[a0])
        print(f"  inserts {a0:>3} -> {a1:>3} (+{dn:>5} bnd) {dv:>9.1f} us "
              f"=> {dv/dn:>7.4f} us/boundary")

    nz = [r for r in sub if r[3] > 0]
    if len({r[3] for r in nz}) >= 3:
        a3, sl3, sea3, seb3, df3 = ols([LAYERS * r[3] for r in nz],
                                       [r[4] for r in nz])
        print(f"inserts>0 only: slope = {sl3:.4f} +- {t95(df3)*seb3:.4f} "
              f"us/boundary, intercept = {a3:.1f} +- {t95(df3)*sea3:.1f} us/step "
              f"(offset vs k=0 cell: {a3 - statistics.median(cell[0]):+.1f} us)")
    return sl, t * seb, cell


def report_size(rows, csv):
    if not rows:
        return
    print("\n=== SIZE SWEEP: price of one dependent round trip vs width ===")
    print(f"{'bytes':>9} {'n0':>3} {'n2':>3} {'T(k=0)':>10} {'T(k=80)':>10} "
          f"{'delta us':>10} {'us/boundary':>12} {'sd(price)':>10}")
    pts = []
    for w in sorted({r[2] for r in rows}):
        # Pair each inserts=2 run with the inserts=0 run of the same width in
        # the same block, so a block-level shift cancels inside the pair.
        by_block = {}
        for b, _s, ww, ins, v in rows:
            if ww == w:
                by_block.setdefault(b, {}).setdefault(ins, []).append(v)
        prices = []
        for d in by_block.values():
            if 0 in d and 2 in d:
                prices.append((statistics.median(d[2]) - statistics.median(d[0]))
                              / (2 * LAYERS))
        v0 = [v for _b, _s, ww, ins, v in rows if ww == w and ins == 0]
        v2 = [v for _b, _s, ww, ins, v in rows if ww == w and ins == 2]
        if not prices:
            continue
        price = statistics.median(prices)
        sd = statistics.stdev(prices) if len(prices) > 1 else float("nan")
        by = 2 * w
        print(f"{by:>9} {len(v0):>3} {len(v2):>3} {statistics.median(v0):>10.1f} "
              f"{statistics.median(v2):>10.1f} "
              f"{statistics.median(v2)-statistics.median(v0):>10.1f} "
              f"{price:>12.4f} {sd:>10.4f}")
        pts.append((by, price))
        if csv is not None:
            csv.append(["size", by, "", 2 * LAYERS, len(prices), f"{price:.4f}",
                        f"{sd:.4f}", ""])
    big = [(b, p) for b, p in pts if b >= 65536]
    if len(big) >= 2:
        _a, sl, _sea, seb, df = ols([b for b, _ in big], [p for _, p in big])
        # price = c_fixed + 2W/BW  =>  slope is us per byte of W; the round trip
        # moves 2W bytes, so BW_eff = 2 bytes / (slope us) = 2/slope MB/s*1e-6.
        bw = (2.0 / sl) / 1e3 if sl > 0 else float("nan")  # GB/s
        print(f"large-W limb: price = {_a:.3f} + {sl:.3e}*bytes us "
              f"=> c_fixed = {_a:.3f} us, BW_eff = {bw:.1f} GB/s (df={df})")
        pct_per_mb = sl * 1048576 * PCT_PER_US
        print(f"large-W limb in PR#110 units: {pct_per_mb:.6f} %/MB of moved "
              f"activation bytes (PR#110 realised: 0.015224 %/MB)")
    small = [(b, p) for b, p in pts if b <= 65536]
    if len(small) >= 2:
        lo, hi = min(p for _, p in small), max(p for _, p in small)
        print(f"small-W limb (<=64 KiB): price spans {lo:.4f}..{hi:.4f} "
              f"us/boundary (range {hi-lo:.4f})")


def main():
    args = sys.argv[1:]
    csv_path = None
    if args and args[0] == "--csv":
        csv_path = args[1]
        args = args[2:]
    if not args:
        raise SystemExit(__doc__)
    csv = [] if csv_path else None
    lad = load_ladder(args)
    if lad:
        print(f"loaded {len(lad)} ladder runs from {len(args)} session dir(s)")
        wide = report_mode(lad, "w", "WIDE-insitu: 4 KiB dependent round trip", csv)
        tiny = report_mode(lad, "t", "TINY-insitu: 2 B dependent op", csv)
        report_mode(lad, "o", "OFF: instrument present but env-disarmed", csv)
        if wide and tiny:
            sw, ew, _ = wide
            st, et, _ = tiny
            d = sw - st
            se = math.hypot(ew / 1.96, et / 1.96)
            print(f"\nd = slope(WIDE) - slope(TINY) = {d:.4f} +- {1.96*se:.4f} "
                  f"us/boundary (95% CI [{d-1.96*se:.4f}, {d+1.96*se:.4f}]); "
                  f"ratio = {sw/st if st else float('nan'):.2f}x")
            print(f"d in score units: {d*PCT_PER_US:.6f} % of score per boundary")
            for n in (40, 120, 240):
                print(f"  eliminating {n:>3} boundaries/step => "
                      f"{n*d:>8.1f} us/step => {n*d*PCT_PER_US:>6.3f} % of score")
            if csv is not None:
                csv.append(["summary", "d_us_per_boundary", "", "", "",
                            f"{d:.4f}", f"{1.96*se:.4f}", ""])
    report_size(load_size(args), csv)
    if csv_path:
        with open(csv_path, "w") as fh:
            fh.write("kind,arm,x,k,n,value,dispersion,delta_vs_k0\n")
            for row in csv:
                fh.write(",".join(str(c) for c in row) + "\n")
        print(f"\nwrote {csv_path}")


if __name__ == "__main__":
    main()
