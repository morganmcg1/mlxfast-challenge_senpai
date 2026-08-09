#!/usr/bin/env python3
"""R102-A rung 1: fit the split-invariant fixed cost of the decode attention
kernel from the interleaved row sweep produced by
research/run_frieren_r102_fixed_cost.sh.

Reads the `SWEEP k=.. idx=.. N=.. M=..` machine lines from each artifact log
and emits Markdown tables on stdout plus a tidy CSV.

Cost model under test (per *call*, C = GPU cores, W = ceil(K/C) waves):

    T(K, M) = a + W*phi + W*g*M          f_direct(K) := T(K, 0) = a + W*phi

`a`   is paid once per dispatch and is NOT re-paid by a KV split.
`phi` is paid once per wave of threadgroups and IS re-paid whenever the split
      pushes the threadgroup count into another wave.
`g*M` is the ring-loop work, which a split divides by S.
"""

import csv
import math
import os
import re
import statistics
import sys

ART = os.path.join("research", "artifacts", "frieren-r102")
CORES = 20  # measured C for this host (staircase steps at K=21 and K=41)

SWEEP_RE = re.compile(
    r"SWEEP k=(\d+) idx=(\d+) N=(\d+) M=(\d+) slots=(\d+) n=(\d+) "
    r"min=([\d.]+) med=([\d.]+) mean=([\d.]+) sd=([\d.]+)"
)

# two-sided 95% t quantiles by degrees of freedom
T95 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447,
       7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228}


def waves(k):
    return -(-k // CORES)


def load(tag):
    path = os.path.join(ART, tag + ".log")
    rows = []
    with open(path) as fh:
        for line in fh:
            m = SWEEP_RE.search(line)
            if m:
                rows.append({
                    "block": tag,
                    "K": int(m.group(1)), "idx": int(m.group(2)),
                    "N": int(m.group(3)), "M": int(m.group(4)),
                    "slots": int(m.group(5)), "rounds": int(m.group(6)),
                    "min": float(m.group(7)), "med": float(m.group(8)),
                    "mean": float(m.group(9)), "sd": float(m.group(10)),
                })
    if not rows:
        sys.exit("no SWEEP lines in " + path)
    return rows


def ks(rows):
    return sorted({r["K"] for r in rows})


def by_m(rows, k, stat="med"):
    """Average duplicate row-count columns for one K -> {M: value}."""
    acc = {}
    for r in rows:
        if r["K"] == k:
            acc.setdefault(r["M"], []).append(r[stat])
    return {m: statistics.fmean(v) for m, v in acc.items()}


def linfit(xs, ys):
    n = len(xs)
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    slope = sxy / sxx
    icpt = my - slope * mx
    pred = [icpt + slope * x for x in xs]
    resid = [y - p for y, p in zip(ys, pred)]
    sse = sum(r * r for r in resid)
    sst = sum((y - my) ** 2 for y in ys)
    df = n - 2
    s2 = sse / df if df > 0 else 0.0
    se_slope = math.sqrt(s2 / sxx) if sxx else 0.0
    se_icpt = math.sqrt(s2 * (1.0 / n + mx * mx / sxx)) if sxx else 0.0
    r2 = 1.0 - sse / sst if sst else 1.0
    return {"slope": slope, "icpt": icpt, "r2": r2, "df": df,
            "se_slope": se_slope, "se_icpt": se_icpt,
            "rmse": math.sqrt(sse / n), "resid": resid, "pred": pred}


def ratio_ci(f, sf, tau, stau, tq):
    """Delta-method 95% CI for f/tau treating f and tau as independent."""
    r = f / tau
    if r == 0:
        return (0.0, 0.0)
    var = (sf / tau) ** 2 + (f * stau / tau ** 2) ** 2
    h = tq * math.sqrt(var)
    return (r - h, r + h)


def verdict(x):
    if x < 0.0667:
        return "GO"
    if x < 0.20:
        return "PARTIAL"
    return "NO-GO"


def dup_null(rows, stat="med"):
    """Within-round null: same N visited twice in the same interleaved round."""
    out = []
    for k in ks(rows):
        cols = {}
        for r in rows:
            if r["K"] == k:
                cols.setdefault(r["N"], []).append(r)
        for n, group in sorted(cols.items()):
            if len(group) < 2:
                continue
            vals = [g[stat] for g in group]
            lo, hi = min(vals), max(vals)
            out.append((k, n, len(group), lo, hi, 100.0 * (hi - lo) / lo))
    return out


def point_table(rows):
    print("| K | W | idx | N | M | slots | min us | med us | sd us | rel sd % |")
    print("|--:|--:|----:|--:|--:|------:|-------:|-------:|------:|---------:|")
    for r in rows:
        print("| %d | %d | %d | %d | %d | %d | %.3f | %.3f | %.4f | %.3f |" % (
            r["K"], waves(r["K"]), r["idx"], r["N"], r["M"], r["slots"],
            r["min"], r["med"], r["sd"], 100.0 * r["sd"] / r["med"]))


def fit_table(rows, stat="med"):
    print()
    print("| K | W | f_fit us | +-95% | g us/iter | tau0=4g us | f/tau0 | "
          "95% CI | R^2 | rmse us | f_direct(M=0) us | fit-direct % | verdict |")
    print("|--:|--:|---------:|------:|----------:|-----------:|-------:|"
          "-------:|----:|--------:|-----------------:|-------------:|:--------|")
    res = {}
    for k in ks(rows):
        d = by_m(rows, k, stat)
        pts = sorted(m for m in d if m >= 1)
        fit = linfit([float(m) for m in pts], [d[m] for m in pts])
        tq = T95.get(fit["df"], 2.0)
        tau0 = 4.0 * fit["slope"]
        stau = 4.0 * fit["se_slope"]
        ratio = fit["icpt"] / tau0
        lo, hi = ratio_ci(fit["icpt"], fit["se_icpt"], tau0, stau, tq)
        direct = d.get(0)
        dd = 100.0 * (fit["icpt"] - direct) / direct if direct else float("nan")
        print("| %d | %d | %.3f | %.3f | %.4f | %.3f | %.1f%% | "
              "[%.1f%%, %.1f%%] | %.5f | %.4f | %.3f | %+.1f%% | %s |" % (
                  k, waves(k), fit["icpt"], tq * fit["se_icpt"], fit["slope"],
                  tau0, 100 * ratio, 100 * lo, 100 * hi, fit["r2"],
                  fit["rmse"], direct if direct else float("nan"), dd,
                  verdict(ratio)))
        res[k] = (fit, tau0, direct, d)
    return res


def direct_ratio_table(rows, stat="med"):
    """Gate arithmetic that uses only measured points (no extrapolation)."""
    print()
    print("| K | W | T(N=512) us | f_direct(M=0) us | tau0=T-f us | f/tau0 | "
          "verdict |")
    print("|--:|--:|------------:|-----------------:|------------:|-------:|"
          ":--------|")
    for k in ks(rows):
        d = by_m(rows, k, stat)
        if 4 not in d or 0 not in d:
            continue
        tau0 = d[4] - d[0]
        r = d[0] / tau0
        print("| %d | %d | %.3f | %.3f | %.3f | %.1f%% | %s |" % (
            k, waves(k), d[4], d[0], tau0, 100 * r, verdict(r)))


def wave_model(blocks, stat="med"):
    """Split f_direct(K) into a (per call) and phi (per wave of C TGs)."""
    print()
    print("### Wave decomposition of the direct fixed cost "
          "(`f_direct(K) = a + W*phi`, W = ceil(K/%d))" % CORES)
    print()
    print("| block | K | W | f_direct us |")
    print("|:------|--:|--:|------------:|")
    xs, ys = [], []
    for tag, rows in blocks:
        for k in ks(rows):
            d = by_m(rows, k, stat)
            if 0 not in d:
                continue
            print("| %s | %d | %d | %.3f |" % (tag, k, waves(k), d[0]))
            xs.append(float(waves(k)))
            ys.append(d[0])
    fit = linfit(xs, ys)
    tq = T95.get(fit["df"], 2.0)
    print()
    print("a   = %.3f +- %.3f us  (per call, NOT re-paid by a split)"
          % (fit["icpt"], tq * fit["se_icpt"]))
    print("phi = %.3f +- %.3f us  (per wave of %d threadgroups, re-paid)"
          % (fit["slope"], tq * fit["se_slope"], CORES))
    print("R^2 = %.5f, rmse = %.4f us, n = %d" % (fit["r2"], fit["rmse"],
                                                  len(xs)))
    return fit


def m3_table(rows, stat="med"):
    print()
    print("### M3 direct split emulation (byte-matched diagonal, "
          "merge pass omitted -> generous to the split)")
    print()
    print("| S | K=32*S | W | N=512/S | M | T us | vs S=1 |")
    print("|--:|-------:|--:|--------:|--:|-----:|-------:|")
    base = None
    for k, n, s in ((32, 512, 1), (64, 256, 2), (128, 128, 4)):
        hits = [r for r in rows if r["K"] == k and r["N"] == n]
        if not hits:
            continue
        v = statistics.fmean(h[stat] for h in hits)
        if base is None:
            base = v
        print("| %d | %d | %d | %d | %d | %.3f | %.3fx |" % (
            s, k, waves(k), n, hits[0]["M"], v, v / base))


def f2_table(blocks, a, phi, t_ring512, stat="med"):
    """Out-of-sample test of the wave law on the one split the law says wins.

    Full attention ships K=24 threadgroups, so on a 20-core host a 2-way KV
    split goes W=2 -> W=3: one extra wave bought in exchange for halving the
    ring.  The law predicts a real 12% win there.  F2 measures the same
    byte-matched diagonal used for M3D, (24,512) vs (48,256), and none of its
    points were used to fit a or phi.
    """
    print()
    print("### F2 out-of-sample test: the split the wave law says SHOULD win")
    print()
    print("| block | S | K | W | N | M | measured us | predicted us | err % | "
          "measured vs S=1 | predicted vs S=1 |")
    print("|:------|--:|--:|--:|--:|--:|------------:|-------------:|------:|"
          "----------------:|-----------------:|")
    for tag, rows in blocks:
        base_m = base_p = None
        for s, k, n in ((1, 24, 512), (2, 48, 256)):
            d = by_m(rows, k, stat)
            hits = [r for r in rows if r["K"] == k and r["N"] == n]
            if not hits or 0 not in d:
                continue
            m = statistics.fmean(h[stat] for h in hits)
            w = waves(k)
            pred = a + w * (phi + t_ring512 * hits[0]["M"] / 4.0)
            if base_m is None:
                base_m, base_p = m, pred
            print("| %s | %d | %d | %d | %d | %d | %.3f | %.3f | %+.1f%% | "
                  "%.3fx | %.3fx |"
                  % (tag, s, k, w, n, hits[0]["M"], m, pred,
                     100 * (pred - m) / m, m / base_m, pred / base_p))


def split_scan(a, phi, t_ring512):
    """Price an S-way KV split of the shipped decode grids with the measured
    wave law.  Shipped grids are heads/2 threadgroups of 1024 threads:
    32 for sliding (64 query heads), 24 for full attention (48 query heads).

        T(S) = a + ceil(K*S/C) * (phi + t_ring/S)

    The ring work per shard is t_ring/S; the cross-shard merge that a real
    split needs is NOT priced here, so every number below is optimistic.
    """
    for cores, label in ((40, "ranked M5 (C=40)"), (CORES, "this host (C=20)")):
        for k, kind, keys in ((32, "sliding", 512), (24, "full", 576)):
            t_ring = t_ring512 * keys / 512.0
            print()
            print("**%s, %s decode attention (K=%d threadgroups, "
                  "%d keys, t_ring=%.3f us)**" % (label, kind, k, keys, t_ring))
            print()
            print("| S | K*S | W | phi cost us | ring us | T us | vs S=1 |")
            print("|--:|----:|--:|------------:|--------:|-----:|-------:|")
            base = None
            for s in (1, 2, 3, 4, 5, 6, 8, 10):
                w = -(-k * s // cores)
                tphi, tring = w * phi, w * t_ring / s
                t = a + tphi + tring
                if base is None:
                    base = t
                print("| %d | %d | %d | %.3f | %.3f | %.3f | %+.3f us (%.3fx) |"
                      % (s, k * s, w, tphi, tring, t, t - base, t / base))


def write_csv(blocks):
    path = os.path.join(ART, "sweep.csv")
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["block", "K", "waves", "idx", "N", "M", "slots", "rounds",
                    "min_us", "med_us", "mean_us", "sd_us"])
        for _, rows in blocks:
            for r in rows:
                w.writerow([r["block"], r["K"], waves(r["K"]), r["idx"],
                            r["N"], r["M"], r["slots"], r["rounds"],
                            "%.4f" % r["min"], "%.4f" % r["med"],
                            "%.4f" % r["mean"], "%.4f" % r["sd"]])
    print()
    print("wrote " + path)


def main():
    calib_tags = ("R_sweep", "D_sweep", "M3D")
    f2_tags = ("F2", "F2D")
    calib = [(t, load(t)) for t in calib_tags]
    f2 = [(t, load(t)) for t in f2_tags]
    blocks = calib + f2
    labels = {
        "R_sweep": "resident KV (1 slot, r98 binding)",
        "D_sweep": "SLC-defeat, byte-matched across N (slots scale as 512/N)",
        "M3D": "SLC-defeat, fixed 48 slots, split-emulation diagonal",
        "F2": "resident KV, full-attention split diagonal (out of sample)",
        "F2D": "SLC-defeat, full-attention split diagonal (out of sample)",
    }
    for tag, rows in blocks:
        print()
        print("## %s -- %s" % (tag, labels[tag]))
        print()
        point_table(rows)
        print()
        print("Within-round duplicate-N null (same N twice per round):")
        print()
        print("| K | N | copies | lo us | hi us | spread % |")
        print("|--:|--:|-------:|------:|------:|---------:|")
        for k, n, c, lo, hi, pct in dup_null(rows):
            print("| %d | %d | %d | %.3f | %.3f | %.2f%% |"
                  % (k, n, c, lo, hi, pct))
        print()
        print("Least-squares fit over M in {1,2,3,4}; M=0 is an independent "
              "check, never a fit input.")
        fit_table(rows)
        print()
        print("Gate arithmetic from measured points only:")
        direct_ratio_table(rows)

    print()
    print("Wave law fitted on the calibration blocks only; F2/F2D are held "
          "out so their comparison is a genuine prediction.")
    wm = wave_model(calib)
    m3_table([r for t, rows in blocks if t == "M3D" for r in rows])
    rows20 = [r for t, rows in blocks if t == "R_sweep" for r in rows]
    d20 = by_m(rows20, 20)
    t_ring512 = d20[4] - d20[0]
    print()
    print("### Projected split cost from the measured wave law")
    print()
    print("t_ring(512 keys) = T(K=20, M=4) - f_direct(K=20) = %.3f us "
          "(wave-matched, W=1)" % t_ring512)
    split_scan(wm["icpt"], wm["slope"], t_ring512)
    f2_table(f2, wm["icpt"], wm["slope"], t_ring512)
    print()
    print("Refit including the held-out F2/F2D points (adds W=3, absent from "
          "the calibration set):")
    wave_model(blocks)
    write_csv(blocks)


if __name__ == "__main__":
    main()
