#!/usr/bin/env python3
"""R119-B statistics for the grid-append shared+routed gate/up QMV campaign.

Consumes the raw per-step CSVs written by research/edward_r119b_abba.sh
(order_tag,block,run,arm,step,ms) and reports, per order tag:

  * block estimator      -- within-block mean(C) - mean(F), t-CI over blocks
  * adjacent-pair        -- every temporally adjacent C/F pair, t-CI over pairs
  * Welch                -- two-sample Welch t on the per-run medians
  * bimodality           -- Sarle's coefficient on raw samples, pooled and per run

The per-run statistic is the median of that run's steady per-step wall, which is
what the campaign ranks. Delta is reported as (baseline arm - candidate arm), so
a positive delta means the candidate arm is faster.

scipy is not available on this host, so the Student-t tail is evaluated through
the regularized incomplete beta continued fraction and the critical value by
bisection.

Research-only; not on editablePaths.
  python3 research/edward_r119b_stats.py /tmp/r119b-abba/abba_raw.csv ...
"""
from __future__ import annotations

import argparse
import csv
import math
from collections import defaultdict

import numpy as np


def _betacf(a: float, b: float, x: float) -> float:
    tiny = 1e-30
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < tiny:
        d = tiny
    d = 1.0 / d
    h = d
    for m in range(1, 300):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < tiny:
            d = tiny
        c = 1.0 + aa / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < tiny:
            d = tiny
        c = 1.0 + aa / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 3e-16:
            break
    return h


def betainc(a: float, b: float, x: float) -> float:
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    lbeta = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
    front = math.exp(lbeta + a * math.log(x) + b * math.log1p(-x))
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _betacf(a, b, x) / a
    return 1.0 - math.exp(lbeta + b * math.log1p(-x) + a * math.log(x)) * _betacf(b, a, 1.0 - x) / b


def t_sf2(t: float, df: float) -> float:
    """Two-sided Student-t survival probability."""
    if df <= 0:
        return float("nan")
    return betainc(0.5 * df, 0.5, df / (df + t * t))


def t_crit(df: float, conf: float = 0.95) -> float:
    lo, hi = 0.0, 200.0
    target = 1.0 - conf
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if t_sf2(mid, df) > target:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def one_sample_ci(vals: np.ndarray, conf: float = 0.95):
    n = vals.size
    if n < 2:
        return float("nan"), float("nan"), float("nan"), float("nan"), n
    mean = float(vals.mean())
    sd = float(vals.std(ddof=1))
    se = sd / math.sqrt(n)
    df = n - 1
    tc = t_crit(df, conf)
    t = mean / se if se > 0 else float("inf")
    return mean, mean - tc * se, mean + tc * se, t_sf2(abs(t), df), n


def welch(a: np.ndarray, b: np.ndarray, conf: float = 0.95):
    na, nb = a.size, b.size
    va, vb = a.var(ddof=1), b.var(ddof=1)
    diff = float(a.mean() - b.mean())
    se = math.sqrt(va / na + vb / nb)
    if se == 0:
        return diff, float("nan"), float("nan"), float("nan"), float("nan")
    df = (va / na + vb / nb) ** 2 / ((va / na) ** 2 / (na - 1) + (vb / nb) ** 2 / (nb - 1))
    tc = t_crit(df, conf)
    t = diff / se
    return diff, diff - tc * se, diff + tc * se, t_sf2(abs(t), df), df


def sarle(x: np.ndarray) -> float:
    """Sarle's bimodality coefficient; > 0.555 is the usual suspicion threshold."""
    n = x.size
    if n < 4:
        return float("nan")
    m = x.mean()
    s = x.std(ddof=1)
    if s == 0:
        return float("nan")
    z = (x - m) / s
    g1 = (n / ((n - 1) * (n - 2))) * np.sum(z ** 3)
    g2 = ((n * (n + 1)) / ((n - 1) * (n - 2) * (n - 3))) * np.sum(z ** 4) - (
        3 * (n - 1) ** 2 / ((n - 2) * (n - 3))
    )
    return float((g1 ** 2 + 1.0) / (g2 + 3.0))


def mode_count(x: np.ndarray, bin_ms: float = 0.005, rel_height: float = 0.10) -> int:
    """Count separated peaks in a smoothed histogram.

    Sarle's coefficient is inflated by skew alone, so a heavy right tail on a
    single-peaked latency distribution can exceed 0.555 with no second mode.
    This counts peaks directly so the two cases can be told apart.
    """
    if x.size < 64:
        return 0
    edges = np.arange(np.min(x), np.max(x) + bin_ms, bin_ms)
    if edges.size < 5:
        return 1
    h, _ = np.histogram(x, bins=edges)
    k = np.ones(5) / 5.0
    s = np.convolve(h.astype(float), k, mode="same")
    thresh = rel_height * s.max()
    peaks = 0
    i = 1
    while i < s.size - 1:
        if s[i] >= thresh and s[i] > s[i - 1] and s[i] >= s[i + 1]:
            peaks += 1
            i += 3
        else:
            i += 1
    return peaks


def load(paths):
    rows = []
    for p in paths:
        with open(p, newline="") as fh:
            for r in csv.DictReader(fh):
                rows.append(
                    (r["order_tag"], int(r["block"]), int(r["run"]), r["arm"], int(r["step"]), float(r["ms"]))
                )
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("csv", nargs="+")
    ap.add_argument("--baseline", default="C", help="baseline arm label")
    ap.add_argument("--candidate", default="F", help="candidate arm label")
    ap.add_argument("--conf", type=float, default=0.95)
    ap.add_argument("--trim", type=int, default=0, help="drop this many leading steps per run")
    ap.add_argument("--pool", action="store_true",
                    help="analyse all input tags as one set; adjacent pairs never cross a tag")
    args = ap.parse_args()

    rows = load(args.csv)
    base, cand = args.baseline, args.candidate

    src_index = {t: i for i, t in enumerate(sorted({r[0] for r in rows}))}
    per_run_samples: dict = defaultdict(list)
    run_meta: dict = {}
    for tag, block, run, arm, step, ms in rows:
        if step <= args.trim:
            continue
        if args.pool:
            i = src_index[tag]
            key = ("pooled", i * 10000 + run)
            meta = (i * 1000 + block, arm, tag)
        else:
            key = (tag, run)
            meta = (block, arm, tag)
        per_run_samples[key].append(ms)
        run_meta[key] = meta

    tags = sorted({t for t, _ in per_run_samples})
    for tag in tags:
        runs = sorted(r for t, r in per_run_samples if t == tag)
        print(f"\n================ order tag: {tag} ================")
        print(f"{'run':>6} {'blk':>5} {'arm':>4} {'n':>6} {'median':>9} {'mean':>9} {'p10':>9} {'p90':>9} {'bimod':>7}")
        run_med: dict = {}
        for r in runs:
            x = np.asarray(per_run_samples[(tag, r)], dtype=float)
            block, arm, src = run_meta[(tag, r)]
            med = float(np.median(x))
            run_med[r] = (block, arm, med, src)
            print(
                f"{r:>6} {block:>5} {arm:>4} {x.size:>6} {med:>9.4f} {x.mean():>9.4f} "
                f"{np.percentile(x, 10):>9.4f} {np.percentile(x, 90):>9.4f} {sarle(x):>7.3f}"
            )

        base_meds = np.array([v[2] for _, v in sorted(run_med.items()) if v[1] == base])
        cand_meds = np.array([v[2] for _, v in sorted(run_med.items()) if v[1] == cand])
        if base_meds.size == 0 or cand_meds.size == 0:
            print(f"  (missing arm; have {sorted({v[1] for v in run_med.values()})})")
            continue
        ref = float(base_meds.mean())
        print(f"\n  n({base})={base_meds.size} n({cand})={cand_meds.size}  ref mean({base})={ref:.4f} ms")

        # --- block estimator ---------------------------------------------
        per_block: dict = defaultdict(lambda: defaultdict(list))
        for r, (b, a, m, _src) in run_med.items():
            per_block[b][a].append(m)
        deltas, kept = [], []
        for b in sorted(per_block):
            if base in per_block[b] and cand in per_block[b]:
                d = float(np.mean(per_block[b][base]) - np.mean(per_block[b][cand]))
                deltas.append(d)
                kept.append(b)
        if deltas:
            d = np.asarray(deltas)
            mean, lo, hi, p, n = one_sample_ci(d, args.conf)
            print(f"  block estimator      blocks={n} delta={mean:+.4f} ms "
                  f"CI[{lo:+.4f},{hi:+.4f}] p={p:.4g}  rel={100*mean/ref:+.3f}% "
                  f"CI[{100*lo/ref:+.3f}%,{100*hi/ref:+.3f}%] {'EXCLUDES-ZERO' if lo*hi>0 else 'INCLUDES-ZERO'}")

        # --- adjacent-pair estimator -------------------------------------
        pair_d = []
        for i in range(len(runs) - 1):
            r1, r2 = runs[i], runs[i + 1]
            _, a1, m1, s1 = run_med[r1]
            _, a2, m2, s2 = run_med[r2]
            if s1 != s2:
                continue
            if a1 == base and a2 == cand:
                pair_d.append(m1 - m2)
            elif a1 == cand and a2 == base:
                pair_d.append(m2 - m1)
        if pair_d:
            d = np.asarray(pair_d)
            mean, lo, hi, p, n = one_sample_ci(d, args.conf)
            print(f"  adjacent-pair        pairs={n} delta={mean:+.4f} ms "
                  f"CI[{lo:+.4f},{hi:+.4f}] p={p:.4g}  rel={100*mean/ref:+.3f}% "
                  f"CI[{100*lo/ref:+.3f}%,{100*hi/ref:+.3f}%] {'EXCLUDES-ZERO' if lo*hi>0 else 'INCLUDES-ZERO'}")

        # --- Welch on per-run medians ------------------------------------
        if base_meds.size >= 2 and cand_meds.size >= 2:
            diff, lo, hi, p, df = welch(base_meds, cand_meds, args.conf)
            print(f"  Welch (run medians)  df={df:.1f} delta={diff:+.4f} ms "
                  f"CI[{lo:+.4f},{hi:+.4f}] p={p:.4g}  rel={100*diff/ref:+.3f}% "
                  f"CI[{100*lo/ref:+.3f}%,{100*hi/ref:+.3f}%] {'EXCLUDES-ZERO' if lo*hi>0 else 'INCLUDES-ZERO'}")

        # --- pooled bimodality -------------------------------------------
        for arm in (base, cand):
            pooled = np.concatenate(
                [np.asarray(per_run_samples[(tag, r)]) for r in runs if run_meta[(tag, r)][1] == arm]
            )
            bc = sarle(pooled)
            lo98, hi98 = np.percentile(pooled, [1.0, 99.0])
            core = pooled[(pooled >= lo98) & (pooled <= hi98)]
            bc_core = sarle(core)
            modes = mode_count(pooled)
            if bc > 0.555 and modes >= 2:
                flag = "SUSPECT-BIMODAL"
            elif bc > 0.555:
                flag = "unimodal-skewed (Sarle inflated by right tail)"
            else:
                flag = "unimodal"
            print(f"  raw arm {arm}: samples={pooled.size} median={np.median(pooled):.4f} "
                  f"bimodality={bc:.3f} core98={bc_core:.3f} modes={modes} {flag}")


if __name__ == "__main__":
    main()
