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


def full_arm(blocks, stat="med"):
    """Primary arm: affine tau(N) intercept on the real full-attention kernel.

    The kernel's main loop is 2-deep over BN=32, so one iteration retires 64
    positions and u := 32c is the cost of one BN slice. A 512-position call
    carries tau0 = 16u of variable work on top of f. Splitting it S ways puts
    K*S threadgroups on C cores and gives every shard 512/S positions, so
    makespan(S) = ceil(K*S/C) * (f + (16/S)*u). The S=8 / C=40 gate the
    assignment names is exactly makespan(8) < makespan(1), i.e. f < 1.5u.
    """
    gates = [("C=40 (ranked M5), S=8", 40, 8), ("C=20 (this host), S=4", 20, 4)]
    out = {}
    for tag, rows in blocks:
        print()
        used = sorted({r["N"] for r in rows if r["N"] >= 64}, reverse=True)
        print("### %s -- affine intercept fit, N in {%s}" % (
            tag, ",".join(str(n) for n in used)))
        print()
        print("| K | f us | +-95% | c us/pos | u=32c us | tau0=16u us | f/tau0 | "
              "95% CI | R^2 | rmse us | max resid us |")
        print("|--:|-----:|------:|---------:|---------:|------------:|-------:|"
              "-------:|----:|--------:|-------------:|")
        for k in ks(rows):
            acc = {}
            for r in rows:
                if r["K"] == k and r["N"] >= 64:
                    acc.setdefault(r["N"], []).append(r[stat])
            pts = sorted(acc)
            xs = [float(n) for n in pts]
            ys = [statistics.fmean(acc[n]) for n in pts]
            fit = linfit(xs, ys)
            tq = T95.get(fit["df"], 2.0)
            u = 32.0 * fit["slope"]
            tau0 = 16.0 * u
            stau = 512.0 * fit["se_slope"]
            ratio = fit["icpt"] / tau0
            lo, hi = ratio_ci(fit["icpt"], fit["se_icpt"], tau0, stau, tq)
            print("| %d | %.3f | %.3f | %.5f | %.3f | %.3f | %.1f%% | "
                  "[%.1f%%, %.1f%%] | %.5f | %.4f | %.3f |" % (
                      k, fit["icpt"], tq * fit["se_icpt"], fit["slope"], u,
                      tau0, 100 * ratio, 100 * lo, 100 * hi, fit["r2"],
                      fit["rmse"], max(abs(r) for r in fit["resid"])))
            out[(tag, k)] = (fit, u, tau0, ratio, (lo, hi), pts, ys)
        print()
        print("Residuals (us, measured - fit):")
        print()
        print("| K | " + " | ".join("N=%d" % n for n in
                                    sorted({r["N"] for r in rows if r["N"] >= 64})) + " |")
        print("|--:|" + "--:|" * len({r["N"] for r in rows if r["N"] >= 64}))
        for k in ks(rows):
            fit, _, _, _, _, pts, _ = out[(tag, k)]
            print("| %d | " % k + " | ".join("%+.3f" % r for r in fit["resid"]) + " |")

    print()
    print("### Primary gate: split-K makespan on the full-attention dispatch")
    print()
    print("makespan(S) = ceil(K*S/C) * (f + (16/S)*u); K=24 is the production")
    print("dispatch (48 full-attention heads, 2 heads per threadgroup).")
    for gate_label, c, s_star in gates:
        for (tag, k), (fit, u, tau0, ratio, ci, _, _) in sorted(out.items()):
            if k != 24:
                continue
            base = waves_c(24, c) * (fit["icpt"] + 16.0 * u)
            split = waves_c(24 * s_star, c) * (fit["icpt"] + (16.0 / s_star) * u)
            # f/tau0 bar that makes makespan(S*) == makespan(1)
            wb, wsp = waves_c(24, c), waves_c(24 * s_star, c)
            num = (wb * 16.0 - wsp * 16.0 / s_star)
            bar = num / ((wsp - wb) * 16.0) if wsp != wb else float("inf")
            need = bar
            print()
            print("- %s, %s: W(base)=%d W(S=%d)=%d; base %.3f us, split %.3f us "
                  "(%.3fx); bar f/tau0 < %.1f%%, measured %.1f%% [%.1f%%, %.1f%%] "
                  "-> %s" % (
                      gate_label, tag, wb, s_star, wsp, base, split, split / base,
                      100 * bar, 100 * ratio, 100 * ci[0], 100 * ci[1],
                      "GO" if ci[1] < bar else ("PARTIAL" if ratio < bar else "NO-GO")))

    print()
    print("Full S scan (K=24; merge dispatch cost `a` from the wave law is")
    print("added separately in the split-cost scan above):")
    print()
    for c in (40, 20):
        print()
        print("C = %d cores" % c)
        print()
        hdr = "| block | " + " | ".join("S=%d" % s for s in range(1, 9)) + " |"
        print(hdr)
        print("|:------|" + "--:|" * 8)
        for (tag, k), (fit, u, tau0, _, _, _, _) in sorted(out.items()):
            if k != 24:
                continue
            cells = []
            for s in range(1, 9):
                m = waves_c(24 * s, c) * (fit["icpt"] + (16.0 / s) * u)
                cells.append("%.2f" % m)
            print("| %s | " % tag + " | ".join(cells) + " |")
    return out


def waves_c(k, c):
    return -(-k // c)


def dense_arm(blocks, fits, stat="med"):
    """Below-the-loop anchors and a curvature check on the dense N grid.

    N=0 runs zero main iterations and no tail slice, so it times the prologue
    and epilogue alone: a direct f that reads no KV bytes and must therefore
    agree between the two cache modes. N=32 adds exactly one 32-position tail
    pass, so (T(32) - T(0)) / 32 is a slope estimate that never enters the
    intercept fit.
    """
    print()
    print("### Direct fixed cost below the loop (N=0) versus the fitted intercept")
    print()
    print("| block | K | T(0) us | T(32) us | (T32-T0)/32 us/pos | fitted f us "
          "| +-95% | T(0) - f us | agree within CI |")
    print("|:------|--:|--------:|---------:|-------------------:|------------:"
          "|------:|------------:|:----------------|")
    direct = {}
    for tag, rows in blocks:
        for k in ks(rows):
            t0 = [r[stat] for r in rows if r["K"] == k and r["N"] == 0]
            t32 = [r[stat] for r in rows if r["K"] == k and r["N"] == 32]
            if not t0:
                continue
            t0m = statistics.fmean(t0)
            t32m = statistics.fmean(t32) if t32 else float("nan")
            key = (tag, k)
            direct[key] = (t0m, t32m)
            if key not in fits:
                continue
            fit, _, _, _, _, _, _ = fits[key]
            tq = T95.get(fit["df"], 2.0)
            half = tq * fit["se_icpt"]
            d = t0m - fit["icpt"]
            print("| %s | %d | %.3f | %.3f | %.5f | %.3f | %.3f | %+.3f | %s |"
                  % (tag, k, t0m, t32m, (t32m - t0m) / 32.0, fit["icpt"], half,
                     d, "yes" if abs(d) <= half else "no"))

    print()
    print("Cache-mode invariance of the N=0 anchor (it reads no KV bytes, so a "
          "difference here is probe overhead, not memory):")
    print()
    print("| K | resident T(0) us | defeat T(0) us | delta % |")
    print("|--:|-----------------:|---------------:|--------:|")
    res_tag = blocks[0][0]
    def_tag = blocks[1][0] if len(blocks) > 1 else None
    for k in sorted({k for (t, k) in direct if t == res_tag}):
        a = direct[(res_tag, k)][0]
        b = direct.get((def_tag, k), (float("nan"),))[0]
        print("| %d | %.3f | %.3f | %+.2f%% |" % (k, a, b, 100 * (b - a) / a))

    print()
    print("### Gate arithmetic from measured points only (no fit)")
    print()
    print("tau0 := T(512) - T(0). Both terms are medians of the same shared "
          "pipeline, so this ratio uses no extrapolation at all.")
    print()
    print("| block | K | T(512) us | T(0) us | tau0 us | f/tau0 | bar | verdict |")
    print("|:------|--:|----------:|--------:|--------:|-------:|----:|:--------|")
    meas = {}
    for tag, rows in blocks:
        for k in ks(rows):
            t512 = [r[stat] for r in rows if r["K"] == k and r["N"] == 512]
            t0 = [r[stat] for r in rows if r["K"] == k and r["N"] == 0]
            if not t512 or not t0:
                continue
            a, b = statistics.fmean(t512), statistics.fmean(t0)
            tau0 = a - b
            meas[(tag, k)] = (a, b, tau0)
            print("| %s | %d | %.3f | %.3f | %.3f | %.1f%% | 9.4%% | %s |"
                  % (tag, k, a, b, tau0, 100 * b / tau0,
                     "GO" if 100 * b / tau0 < 9.4 else "NO-GO"))

    print()
    print("### Wave decomposition of the measured fixed cost")
    print()
    print("T(K, 0) = a + W(K)*f_TG with W = ceil(K/%d): the K=24 (W=2) and "
          "K=48 (W=3) anchors separate the once-per-dispatch constant from the "
          "per-threadgroup fixed work, which is what lets a %d-core host answer "
          "a 40-core question." % (CORES, CORES))
    print()
    print("| block | a us | f_TG us | f(C=40, W=1) us | tau0(C=40) us | "
          "f/tau0 at C=40 | verdict |")
    print("|:------|-----:|--------:|----------------:|--------------:|"
          "---------------:|:--------|")
    proj = {}
    for tag, _ in blocks:
        if (tag, 24) not in meas or (tag, 48) not in meas:
            continue
        t24, t48 = meas[(tag, 24)][1], meas[(tag, 48)][1]
        f_tg = (t48 - t24) / (waves_c(48, CORES) - waves_c(24, CORES))
        a = t24 - waves_c(24, CORES) * f_tg
        f40 = a + f_tg
        tau40 = meas[(tag, 24)][2] / waves_c(24, CORES)
        proj[tag] = (a, f_tg, f40, tau40)
        print("| %s | %.3f | %.3f | %.3f | %.3f | %.1f%% | %s |"
              % (tag, a, f_tg, f40, tau40, 100 * f40 / tau40,
                 "GO" if 100 * f40 / tau40 < 9.4 else "NO-GO"))

    print()
    print("### Split makespan on the ranked grid, from measured anchors only")
    print()
    print("makespan(S) = a + ceil(24S/C)*(f_TG + (16/S)*u_TG), merge dispatch "
          "excluded so the scan is an upper bound on the achievable win. The "
          "merge is a second dispatch, so it cannot cost less than the measured "
          "once-per-dispatch constant `a`; the last two columns compare the best "
          "gross win against that floor.")
    for c in (40, CORES):
        print()
        print("C = %d cores" % c)
        print()
        print("| block | " + " | ".join("S=%d" % s for s in range(1, 9))
              + " | best S | gross gain us | merge floor a us | net |")
        print("|:------|" + "--:|" * 8 + "--:|--:|--:|:--|")
        for tag, (a, f_tg, _, tau40) in proj.items():
            u_tg = tau40 / 16.0
            vals = [a + waves_c(24 * s, c) * (f_tg + (16.0 / s) * u_tg)
                    for s in range(1, 9)]
            best = 1 + min(range(8), key=lambda i: vals[i])
            gain = vals[0] - vals[best - 1]
            print("| %s | " % tag + " | ".join("%.2f" % v for v in vals)
                  + " | %d | %+.2f | %.2f | %s |"
                  % (best, gain, a, "WIN" if gain > a else "LOSS"))

    print()
    print("### Independent low-N estimate of f (never uses the large-N points)")
    print()
    print("N in {64,128,192} keeps the KV working set under 800 kB, where the "
          "relative sd is below 0.5%% and no cache level is being exceeded. "
          "Extrapolating that clean segment to N=0 is an estimate of f that "
          "shares no data with the large-N points that dominate the full-grid "
          "intercept, and none with the N=0 anchor itself.")
    print()
    print("| block | K | slope us/pos | low-N intercept us | direct T(0) us | "
          "delta us | delta % | full-grid f us | delta vs full-grid us |")
    print("|:------|--:|--:|--:|--:|--:|--:|--:|--:|")
    for tag, rows in blocks:
        for k in ks(rows):
            acc = {}
            for r in rows:
                if r["K"] == k and 64 <= r["N"] <= 192:
                    acc.setdefault(r["N"], []).append(r[stat])
            if len(acc) < 3 or (tag, k) not in meas:
                continue
            pts = sorted(acc)
            fit = linfit([float(n) for n in pts],
                         [statistics.fmean(acc[n]) for n in pts])
            t0 = meas[(tag, k)][1]
            d = fit["icpt"] - t0
            gf = fits[(tag, k)][0]["icpt"] if (tag, k) in fits else float("nan")
            print("| %s | %d | %.5f | %.3f | %.3f | %+.3f | %+.1f%% | %.3f | %+.3f |"
                  % (tag, k, fit["slope"], fit["icpt"], t0, d, 100 * d / t0,
                     gf, fit["icpt"] - gf))

    print()
    print("### Model validation: the one split point this host can execute directly")
    print()
    print("A two-way split at C=%d is literally K=48 threadgroups each covering "
          "N=256, which the dense grid already measures. Comparing that measured "
          "point with the model's makespan(S=2, C=%d) says whether the scan is "
          "optimistic or pessimistic about splitting."
          % (CORES, CORES))
    print()
    print("Two merge costs are quoted. `a` is the strict floor: any second "
          "dispatch pays the once-per-dispatch constant. T(0) is the realistic "
          "estimate: the merge launches the same 24 threadgroups and so pays "
          "their prologue and epilogue as well.")
    print()
    print("| block | measured T(K=48,N=256) us | model makespan(S=2,C=%d) us | "
          "model error | measured vs S=1 | merge floor a us | merge est T(0) us "
          "| net vs floor | net vs est |" % CORES)
    print("|:------|--:|--:|--:|--:|--:|--:|:--|:--|")
    for tag, rows in blocks:
        if tag not in proj:
            continue
        a, f_tg, _, tau40 = proj[tag]
        u_tg = tau40 / 16.0
        model = a + waves_c(48, CORES) * (f_tg + 8.0 * u_tg)
        obs = [r[stat] for r in rows if r["K"] == 48 and r["N"] == 256]
        if not obs:
            continue
        om = statistics.fmean(obs)
        base, t0 = meas[(tag, 24)][0], meas[(tag, 24)][1]
        gain = base - om
        print("| %s | %.3f | %.3f | %+.1f%% | %+.3f us (%.3fx) | %.2f | %.2f | "
              "%s | %s |"
              % (tag, om, model, 100 * (model - om) / om, gain, om / base, a,
                 t0, "WIN" if gain > a else "LOSS",
                 "WIN" if gain > t0 else "LOSS"))

    print()
    print("### Curvature of tau(N) on the dense grid")
    print()
    print("Second differences of the eight N in {64..512 step 64}. An affine "
          "tau(N) has them at zero within the duplicate-N null; a positive run "
          "means the working set is outgrowing a cache level as N grows.")
    for tag, rows in blocks:
        print()
        print("| K | " + " | ".join("d2(%d)" % n for n in range(128, 449, 64))
              + " | max |d2| us |")
        print("|--:|" + "--:|" * 6 + "--:|")
        for k in ks(rows):
            acc = {}
            for r in rows:
                if r["K"] == k and 64 <= r["N"] <= 512:
                    acc.setdefault(r["N"], []).append(r[stat])
            y = {n: statistics.fmean(v) for n, v in acc.items()}
            if not all(n in y for n in range(64, 513, 64)):
                continue
            d2 = [y[n - 64] - 2 * y[n] + y[n + 64] for n in range(128, 449, 64)]
            print("| %s K=%d | " % (tag, k) + " | ".join("%+.3f" % v for v in d2)
                  + " | %.3f |" % max(abs(v) for v in d2))
    return direct


def write_csv(blocks):
    path = os.path.join(ART, "sweep.csv")
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
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
    full_tags = ("FULL", "FULLD")
    dense_tags = ("FZ", "FZD")
    calib = [(t, load(t)) for t in calib_tags]
    f2 = [(t, load(t)) for t in f2_tags]
    full = [(t, load(t)) for t in full_tags]
    dense = [(t, load(t)) for t in dense_tags]
    blocks = calib + f2 + full + dense
    labels = {
        "R_sweep": "resident KV (1 slot, r98 binding)",
        "D_sweep": "SLC-defeat, byte-matched across N (slots scale as 512/N)",
        "M3D": "SLC-defeat, fixed 48 slots, split-emulation diagonal",
        "F2": "resident KV, full-attention split diagonal (out of sample)",
        "F2D": "SLC-defeat, full-attention split diagonal (out of sample)",
        "FULL": "PRIMARY ARM: real laguna_full_fused_attn_grow_v1, resident KV",
        "FULLD": "PRIMARY ARM: real laguna_full_fused_attn_grow_v1, SLC-defeat",
        "FZ": "PRIMARY ARM: dense N grid + below-the-loop anchors, resident KV",
        "FZD": "PRIMARY ARM: dense N grid + below-the-loop anchors, SLC-defeat",
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
        if tag in full_tags + dense_tags:
            print()
            print("Intercept fit for this block is in the primary-arm section "
                  "below; the sliding-kernel tau0 = 4g convention does not "
                  "apply to a 2-deep loop.")
            continue
        print()
        print("Least-squares fit over M in {1,2,3,4}; M=0 is an independent "
              "check, never a fit input.")
        fit_table(rows)
        print()
        print("Gate arithmetic from measured points only:")
        direct_ratio_table(rows)

    print()
    print("# Primary arm -- full attention")
    print()
    print("FULL/FULLD are the five-point grid the assignment names. FZ/FZD "
          "resample the same code path at every N divisible by 64 and add the "
          "two below-the-loop anchors, so they are the confirmatory fit.")
    full_arm(full)
    dense_fits = full_arm(dense)
    dense_arm(dense, dense_fits)

    print()
    print("# Secondary arm -- sliding attention")
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
          "the calibration set). FULL/FULLD are excluded: they are a different "
          "kernel with its own fixed cost.")
    wave_model(calib + f2)
    write_csv(blocks)


if __name__ == "__main__":
    main()
