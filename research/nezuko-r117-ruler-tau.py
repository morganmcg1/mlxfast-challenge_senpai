#!/usr/bin/env python3
"""nezuko-r117-ruler-tau.py -- estimate tau for the attention scale-plane byte class.

Reads the TSV emitted by research/maple-nezuko-r107j-certify.sh for the R117-C
byte-dose ruler and reports, per the pre-registration
(research/nezuko-r117-byte-dose-ruler-preregistration.md) and its 03:07Z amendment:

  PRIMARY    tau = slope of paired d(us/step) on predicted-us-at-tau-1, fitted
             WITH A FREE INTERCEPT, summarised across blocks.
  REPORTED   the intercept itself -- the direct estimate of the R114 "offset
             class" (an arm sitting ~40 us/step off a no-gate reference for
             reasons unrelated to what it changes).
  DIAGNOSTIC per-rung tau (raw ratio), which is offset-biased by c/dbytes and is
             therefore NOT the headline; plus residuals about the fitted line,
             which is the honest linearity test.
  CHECK      additivity AN vs ON+QN, both raw and intercept-adjusted.

Estimation note. Each block contributes a complete set of 4 paired differences,
so a per-block OLS gives one independent (tau_b, c_b) pair per block, and the
across-block t interval on those is a summary-measure estimator: it respects the
blocking and cannot pseudo-replicate. That is why the dof here is (blocks - 1)
and not (blocks*rungs - 2).

Auditability additions (requested by the advisor 2026-08-11 03:08Z for the
isolated-harness ruler; they are estimator-level asks and so port directly onto
this full-model ruler even though the instrument differs):

  ORDER SPLIT  certify.sh rotates the within-block arm order by (b-1) mod NARM,
               so every rung is measured BEFORE its block's control in some
               blocks and AFTER it in others. That is the rotation-design
               analogue of reporting ABBA and BAAB separately. Both halves are
               fitted independently and printed; if their slopes disagree in
               SIGN the ruler is reporting an order artefact, not a byte cost,
               and the pre-registered decision rule is suspended.
  BOOTSTRAP    percentile CI on the MEDIAN of the per-block tau (and on the
               median paired difference per rung), resampling blocks with
               replacement. Distribution-free; reported alongside the t
               interval on the mean rather than instead of it.
  HISTOGRAM    ASCII histogram of the raw paired differences and of the
               residuals about the fit, so bimodality is visible rather than
               averaged away.
  --csv PATH   writes the tidy per-observation array (one row per measured
               arm-in-block, with its control, its dose and its residual) so a
               reader can re-derive every number here without this script.
               Each row also carries the golden hash of BOTH members of the
               pair, a golden_match flag and both passed flags, so a reader can
               confirm from the published array alone that no rung bought its
               bytes by changing the answer. Without those columns that claim
               would rest on my prose.

Usage:  python3 research/nezuko-r117-ruler-tau.py ROWS.tsv [--csv OUT.csv]
Env:    BW=256.7   assumed peak GB/s used to convert bytes to us at tau=1.
                   (The family's own achieved rate is 235.6 GB/s; tau scales
                   inversely, so tau_at_235.6 = tau_at_256.7 * 256.7/235.6.)
        BOOT=20000 bootstrap resamples.
"""
import csv
import math
import os
import random
import sys
from collections import defaultdict

# ---------------------------------------------------------------- doses
# Bytes ADDED to the decode step by turning each gate off, computed from source
# before any measurement (see pre-registration Sec. "The doses").
# Units: 1e6 bytes per decode step.
DOSE_MB = {
    "OP": 9.830,
    "ON": 29.409,
    "QN": 36.966,
    "AN": 66.375,
}
BW = float(os.environ.get("BW", "256.7"))  # GB/s = 1e9 B/s


def t_crit(dof):
    table = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447,
             7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228, 11: 2.201, 12: 2.179,
             13: 2.160, 14: 2.145, 15: 2.131, 16: 2.120, 17: 2.110, 18: 2.101,
             19: 2.093, 20: 2.086, 24: 2.064, 30: 2.042}
    if dof in table:
        return table[dof]
    if dof < 1:
        return float("nan")
    keys = sorted(table)
    return table[min(keys, key=lambda k: abs(k - dof))]


def summarise(vals, label="", unit=""):
    n = len(vals)
    if n == 0:
        return None
    m = sum(vals) / n
    if n == 1:
        return (m, float("nan"), float("nan"), float("nan"), n)
    sd = math.sqrt(sum((v - m) ** 2 for v in vals) / (n - 1))
    se = sd / math.sqrt(n)
    hw = t_crit(n - 1) * se
    return (m, sd, hw, se, n)


def fmt_ci(s, unit="", nd=3):
    m, sd, hw, se, n = s
    if math.isnan(hw):
        return f"{m:.{nd}f}{unit} (n=1, no interval)"
    return f"{m:+.{nd}f}{unit}  CI95 [{m-hw:+.{nd}f}, {m+hw:+.{nd}f}]  sd={sd:.3f} n={n}"


def median(vals):
    v = sorted(vals)
    n = len(v)
    if n == 0:
        return float("nan")
    return v[n // 2] if n % 2 else 0.5 * (v[n // 2 - 1] + v[n // 2])


def boot_median(vals, iters=None, seed=117):
    """Percentile bootstrap CI95 on the median. Distribution-free; reported
    because the advisor asked for a bootstrap median rather than a t interval
    on the mean. With n<=7 blocks the bootstrap is coarse (the resampled median
    can only take a few distinct values) and is read as a robustness check on
    the t interval, not as a replacement for it."""
    n = len(vals)
    if n < 2:
        return (median(vals), float("nan"), float("nan"), n)
    iters = iters or int(os.environ.get("BOOT", "20000"))
    rng = random.Random(seed)
    reps = []
    for _ in range(iters):
        reps.append(median([vals[rng.randrange(n)] for _ in range(n)]))
    reps.sort()
    lo = reps[int(0.025 * iters)]
    hi = reps[min(iters - 1, int(0.975 * iters))]
    return (median(vals), lo, hi, n)


def fmt_boot(b, unit="", nd=3):
    m, lo, hi, n = b
    if math.isnan(lo):
        return f"{m:+.{nd}f}{unit} (n={n}, no interval)"
    return f"{m:+.{nd}f}{unit}  boot-CI95 [{lo:+.{nd}f}, {hi:+.{nd}f}]  n={n}"


def ols(xs, ys):
    """Free-intercept least squares. Returns (slope, intercept)."""
    n = len(xs)
    xbar = sum(xs) / n
    ybar = sum(ys) / n
    sxx = sum((x - xbar) ** 2 for x in xs)
    if sxx == 0:
        return (float("nan"), ybar)
    sxy = sum((x - xbar) * (y - ybar) for x, y in zip(xs, ys))
    slope = sxy / sxx
    return (slope, ybar - slope * xbar)


def gap_stat(vals):
    """Largest spacing between consecutive order statistics in the interior
    (>=n/4 of the mass on each side), expressed in sd units."""
    n = len(vals)
    v = sorted(vals)
    m = sum(v) / n
    sd = math.sqrt(sum((x - m) ** 2 for x in v) / (n - 1)) if n > 1 else 0.0
    edge = max(2, n // 4)
    if sd <= 0 or n < 2 * edge + 1:
        return (0.0, None, sd)
    best, at = 0.0, None
    for i in range(edge, n - edge + 1):
        g = (v[i] - v[i - 1]) / sd
        if g > best:
            best, at = g, 0.5 * (v[i] + v[i - 1])
    return (best, at, sd)


def gap_pvalue(vals, iters=4000, seed=1117):
    """Monte-Carlo p-value for the gap statistic against a Gaussian null of the
    SAME n, plus the power against a two-component null separated by 3 sd.

    The null distribution of this statistic is strongly n-dependent -- measured
    here, Gaussian data gives median 0.78 / p95 1.29 at n=7 but median 0.31 /
    p95 0.51 at n=28 -- so a single fixed threshold is not a test at all: 1.5 sd
    is a 1% false positive at n=7 and has essentially ZERO power at n=28. The
    threshold is therefore calibrated per call instead of asserted."""
    n = len(vals)
    obs = gap_stat(vals)[0]
    if n < 5:
        return (obs, float("nan"), float("nan"))
    rng = random.Random(seed)
    null = sorted(gap_stat([rng.gauss(0, 1) for _ in range(n)])[0]
                  for _ in range(iters))
    p = sum(1 for x in null if x >= obs) / iters
    crit = null[int(0.95 * iters)]
    alt = sum(1 for _ in range(iters)
              if gap_stat([rng.gauss(0, 1) + (3 if rng.random() < 0.5 else -3)
                           for _ in range(n)])[0] > crit) / iters
    return (obs, p, alt)


def histogram(vals, width=44, unit=""):
    """ASCII histogram plus a scale-aware, self-calibrated bimodality statistic.

    Binning note. An 'empty bin between two occupied bins' is NOT a bimodality
    test at these sample sizes: with n=7 and 7 bins, unimodal Gaussian data
    produces an interior hole almost every time (verified on this script's own
    synthetic selftest, which is Gaussian by construction and tripped that
    naive flag on all four rungs). So the bin count is tied to sqrt(n), the
    sorted values are printed verbatim for small n, and the reported flag is
    the largest interior spacing in sd units scored against a Monte-Carlo
    Gaussian null at the same n, with the test's own power printed beside it.
    """
    out = []
    n = len(vals)
    if n < 2:
        return ["    (too few points to bin)"]
    lo, hi = min(vals), max(vals)
    if hi == lo:
        return [f"    all {n} values identical at {lo:+.2f}{unit}"]
    span = hi - lo
    nbins = max(3, min(12, int(round(math.sqrt(n) * 1.2))))
    counts = [0] * nbins
    for v in vals:
        k = min(nbins - 1, int((v - lo) / span * nbins))
        counts[k] += 1
    mx = max(counts)
    for k, c in enumerate(counts):
        a = lo + span * k / nbins
        b = lo + span * (k + 1) / nbins
        bar = "#" * int(round(width * c / mx)) if mx else ""
        out.append(f"    [{a:+8.2f},{b:+8.2f}) {c:>3} {bar}")
    v = sorted(vals)
    ratio, at, sd = gap_stat(vals)
    _, p, power = gap_pvalue(vals)
    out.append(f"    n={n} min={lo:+.2f} med={median(vals):+.2f} max={hi:+.2f} sd={sd:.2f}")
    if math.isnan(p):
        out.append(f"    max interior spacing = {ratio:.2f} sd  (n too small to score)")
    else:
        flag = "YES <-- inspect for two regimes" if p < 0.05 else "no"
        out.append(f"    max interior spacing = {ratio:.2f} sd"
                   + (f" (near {at:+.2f})" if at is not None else "")
                   + f"   p_vs_gaussian={p:.3f}   bimodal? {flag}")
        out.append(f"    [this test's own power against a 3-sd two-component"
                   f" split at n={n} is {power:.2f}]")
    if n <= 12:
        out.append("    sorted: " + " ".join(f"{x:+.2f}" for x in v))
    return out


def selftest(tau_true=0.75, c_true=-40.0, run_sd=7.0, blocks=7, seed=7,
             pos_drift=0.0):
    """Emit a synthetic TSV with a KNOWN tau and a KNOWN R114-style offset.

    This exists because the estimator choice is load-bearing: on this synthetic
    data the pre-registered free-intercept slope recovers tau to ~0.01, while
    the no-intercept slope reads ~0.53 for a true 0.75 and the raw per-rung
    ratios read -0.29 / 0.43 / 0.46 / 0.59, i.e. they manufacture a textbook
    'saturating, cache-absorbed' curve out of data that is exactly linear.
    A 0.2 error in tau straddles the 0.6 decision boundary, so this is not a
    stylistic preference about estimators.
    """
    rng = random.Random(seed)
    pred = {a: DOSE_MB[a] * 1e6 / (BW * 1e9) * 1e6 for a in DOSE_MB}
    hdr = ("session\tidx\tblock\tpos\tarm\tgates\tkernels\tdecode_s_per_token\t"
           "prefill_s_per_token\tpassed\tgolden\twall_s\thead\terror")
    arms = ["C"] + list(DOSE_MB)
    narm = len(arms)
    lines, idx = [hdr], 0
    for b in range(1, blocks + 1):
        base = 8972.0 + rng.gauss(0, 8)             # block-level drift
        rot = (b - 1) % narm                        # certify.sh rotation
        for k, a in enumerate(arms):
            idx += 1
            pos = ((k - rot) % narm) + 1            # position this arm ran at
            d = 0.0 if a == "C" else c_true + tau_true * pred[a]
            d += pos_drift * (pos - 1)              # pure ORDER artefact
            us = base + d + rng.gauss(0, run_sd)
            lines.append(f"SELFTEST\t{idx}\t{b}\t{pos}\t{a}\tg\tnone\t{us/1e6!r}\t"
                         f"0.00111\ttrue\tSELFTESTGOLDEN\t150\tselftest\t")
    path = "/tmp/nezuko-r117-ruler-selftest.tsv"
    with open(path, "w") as fh:
        fh.write("\n".join(lines) + "\n")
    print(f"[selftest] wrote {path}  tau_true={tau_true} c_true={c_true} "
          f"run_sd={run_sd} blocks={blocks}")
    print(f"[selftest] the PRIMARY tau below should land near {tau_true} and the")
    print(f"[selftest] intercept near {c_true}; the no-intercept contrast should NOT.\n")
    return path


def main():
    argv = sys.argv[1:]
    csv_out = None
    if "--csv" in argv:
        i = argv.index("--csv")
        csv_out = argv[i + 1]
        del argv[i:i + 2]
    if not argv:
        print(__doc__)
        sys.exit(2)
    if argv[0] == "--selftest":
        path = selftest()
    elif argv[0] == "--selftest-order":
        # Negative control for the ORDER SPLIT guard: tau_true = 0 and NO byte
        # effect at all; the entire apparent signal is a 15 us-per-position
        # drift. A ruler that cannot notice this is not auditable.
        print("[selftest-order] tau_true=0, c_true=0, pure +15 us/position drift.")
        print("[selftest-order] The PRIMARY tau will be non-zero and WRONG; the")
        print("[selftest-order] order split is what is supposed to expose it.\n")
        path = selftest(tau_true=0.0, c_true=0.0, pos_drift=15.0)
    else:
        path = argv[0]

    # block -> arm -> decode us/token ; also collect integrity fields
    lvl = defaultdict(dict)
    posn = defaultdict(dict)          # block -> arm -> within-block position
    gold = defaultdict(dict)          # block -> arm -> golden hash (truncated)
    pas = defaultdict(dict)           # block -> arm -> passed flag
    goldens, passes, heads = set(), set(), set()
    with open(path) as fh:
        for row in csv.DictReader(fh, delimiter="\t"):
            if not row.get("arm") or not row.get("decode_s_per_token"):
                continue
            try:
                us = float(row["decode_s_per_token"]) * 1e6
            except ValueError:
                continue
            lvl[int(row["block"])][row["arm"]] = us
            try:
                posn[int(row["block"])][row["arm"]] = int(row.get("pos", "0"))
            except ValueError:
                pass
            gold[int(row["block"])][row["arm"]] = row.get("golden", "")[:16]
            pas[int(row["block"])][row["arm"]] = row.get("passed", "")
            goldens.add(row.get("golden", "")[:18])
            passes.add(row.get("passed", ""))
            heads.add(row.get("head", ""))

    rungs = [a for a in ("OP", "ON", "QN", "AN") if any(a in v for v in lvl.values())]
    # keep only blocks that are COMPLETE (control + every rung present)
    blocks = sorted(b for b, v in lvl.items() if "C" in v and all(r in v for r in rungs))
    dropped = sorted(set(lvl) - set(blocks))

    print("=" * 78)
    print("R117-C byte-dose ruler -- tau for the attention scale-plane byte class")
    print(f"file      : {path}")
    print(f"assumed BW: {BW} GB/s  (tau=1 means 'these bytes stream at peak')")
    print(f"blocks    : {len(blocks)} complete {blocks}"
          + (f"   DROPPED incomplete: {dropped}" if dropped else ""))
    print(f"integrity : golden={sorted(goldens)} passed={sorted(passes)} head={sorted(heads)}")
    print("=" * 78)
    if not blocks:
        print("\nNo complete block yet -- nothing to fit.")
        return

    # predicted us/step at tau = 1
    pred = {a: DOSE_MB[a] * 1e6 / (BW * 1e9) * 1e6 for a in rungs}
    print("\n--- rungs and their doses ---")
    print(f"{'arm':<5}{'dMB/step':>10}{'pred us @tau=1':>16}")
    for a in rungs:
        print(f"{a:<5}{DOSE_MB[a]:>10.3f}{pred[a]:>16.2f}")

    # per-block paired differences
    D = {a: [lvl[b][a] - lvl[b]["C"] for b in blocks] for a in rungs}

    print("\n--- paired differences vs the block's own control (us/step) ---")
    hdr = "block " + "".join(f"{a:>12}" for a in rungs) + f"{'C level':>12}"
    print(hdr)
    for i, b in enumerate(blocks):
        print(f"{b:<6}" + "".join(f"{D[a][i]:>12.2f}" for a in rungs)
              + f"{lvl[b]['C']:>12.2f}")

    # ---------------- PRIMARY: per-block free-intercept OLS, tau = slope
    xs = [pred[a] for a in rungs]
    xbar = sum(xs) / len(xs)
    sxx = sum((x - xbar) ** 2 for x in xs)
    taus, cs = [], []
    for i, b in enumerate(blocks):
        ys = [D[a][i] for a in rungs]
        ybar = sum(ys) / len(ys)
        sxy = sum((x - xbar) * (y - ybar) for x, y in zip(xs, ys))
        tau_b = sxy / sxx
        taus.append(tau_b)
        cs.append(ybar - tau_b * xbar)

    st = summarise(taus, "tau")
    sc = summarise(cs, "c")
    print("\n" + "=" * 78)
    print("PRIMARY ENDPOINT -- tau from the free-intercept OLS slope")
    print("=" * 78)
    print(f"  per-block tau : {[f'{t:+.3f}' for t in taus]}")
    print(f"  tau           = {fmt_ci(st)}")
    print(f"  intercept c   = {fmt_ci(sc, ' us/step', 2)}")
    print(f"                  (R114 offset class predicted c ~ -40 us/step)")
    if not math.isnan(st[2]):
        lo, hi = st[0] - st[2], st[0] + st[2]
        print(f"\n  DECISION RULE (pre-registered):")
        if lo > 0.6:
            print(f"    tau CI95 lower {lo:+.3f} > 0.6  ==> BYTE CLASS CONFIRMED at ~unity.")
        elif hi < 0.6:
            print(f"    tau CI95 upper {hi:+.3f} < 0.6  ==> N-ATTN-SCALE-BYTES-SUBUNITY.")
        else:
            print(f"    CI95 [{lo:+.3f}, {hi:+.3f}] STRADDLES 0.6 ==> report, refuse to pick.")
        print(f"    (excludes 0.3? {'YES' if lo > 0.3 or hi < 0.3 else 'NO'};"
              f"  excludes 1.0? {'YES' if lo > 1.0 or hi < 1.0 else 'NO'};"
              f"  excludes 0? {'YES' if lo > 0 or hi < 0 else 'NO'})")
        print(f"\n  tau restated against the family's achieved 235.6 GB/s:"
              f" {st[0]*BW/235.6:+.3f}")

    # naive no-intercept slope, for contrast only
    num = sum(sum(x * D[a][i] for x, a in zip(xs, rungs)) for i in range(len(blocks)))
    den = len(blocks) * sum(x * x for x in xs)
    print(f"\n  [contrast] no-intercept slope = {num/den:+.3f}"
          "  <- the estimator the amendment REJECTS (absorbs the offset into tau)")

    # ---------------- BOOTSTRAP on the median (advisor 03:08Z ask)
    bt = boot_median(taus)
    bc = boot_median(cs)
    print("\n  [bootstrap, blocks resampled with replacement, "
          f"{int(os.environ.get('BOOT','20000'))} reps]")
    print(f"    median tau       = {fmt_boot(bt)}")
    print(f"    median intercept = {fmt_boot(bc, ' us/step', 2)}")
    print("    With n<=7 blocks the resampled median takes few distinct values, so")
    print("    this is a robustness check on the t interval above, not a substitute.")

    # ---------------- ORDER SPLIT (the rotation-design ABBA/BAAB analogue)
    print("\n" + "-" * 78)
    print("ORDER SPLIT -- rung measured BEFORE vs AFTER its block's control")
    print("-" * 78)
    have_pos = all(posn.get(b, {}).get(a) for b in blocks for a in ["C"] + rungs)
    if not have_pos:
        print("  positions unavailable in this file; split not computed.")
    else:
        halves = {"rung-BEFORE-control": [], "rung-AFTER-control": []}
        for i, b in enumerate(blocks):
            pc = posn[b]["C"]
            for a in rungs:
                key = ("rung-BEFORE-control" if posn[b][a] < pc
                       else "rung-AFTER-control")
                halves[key].append((pred[a], D[a][i], a, b))
        keys = list(halves)
        fits = {}
        for key in keys:
            pts = halves[key]
            armset = sorted({p[2] for p in pts})
            if len(armset) < 2:
                print(f"  {key:<22} n={len(pts):<3} only arms {armset} -- "
                      "no dose spread, slope not identified")
                continue
            s, c0 = ols([p[0] for p in pts], [p[1] for p in pts])
            fits[key] = (s, c0)
            print(f"  {key:<22} n={len(pts):<3} arms={','.join(armset):<14} "
                  f"tau={s:+.3f}  c={c0:+.2f} us/step")
        print("  (pooled OLS within each half: the half does not contain a complete")
        print("   dose set in every block, so a per-block fit is not available here.)")
        if len(fits) == 2:
            (s0, c0), (s1, c1) = fits[keys[0]], fits[keys[1]]
            # block bootstrap on BOTH contrasts
            byblock = defaultdict(list)
            for key in keys:
                for x, y, a, b in halves[key]:
                    byblock[b].append((x, y, key))
            bl = sorted(byblock)
            rng = random.Random(1177)
            iters = int(os.environ.get("BOOT", "20000")) // 4 or 1
            dts, dcs = [], []
            for _ in range(iters):
                pool = defaultdict(list)
                for _ in range(len(bl)):
                    for x, y, key in byblock[bl[rng.randrange(len(bl))]]:
                        pool[key].append((x, y))
                if len(pool) < 2 or any(len({p[0] for p in pool[k]}) < 2
                                        for k in keys):
                    continue
                f = {k: ols([p[0] for p in pool[k]], [p[1] for p in pool[k]])
                     for k in keys}
                dts.append(f[keys[1]][0] - f[keys[0]][0])
                dcs.append(f[keys[1]][1] - f[keys[0]][1])
            def pct(v):
                v = sorted(v)
                return (v[int(0.025 * len(v))], v[min(len(v) - 1, int(0.975 * len(v)))])
            agree = (s0 > 0) == (s1 > 0)
            print(f"  SLOPE  sign agreement: {'YES' if agree else 'NO'}"
                  f"   dtau = {s1-s0:+.3f}"
                  + (f"  boot-CI95 [{pct(dts)[0]:+.3f}, {pct(dts)[1]:+.3f}]" if dts else ""))
            print(f"  OFFSET split:            dc  = {c1-c0:+.2f} us/step"
                  + (f"  boot-CI95 [{pct(dcs)[0]:+.2f}, {pct(dcs)[1]:+.2f}]" if dcs else ""))
            print("  Read the OFFSET line first. On this rotation design a pure order")
            print("  artefact does NOT flip the slope sign -- verified with")
            print("  --selftest-order, where a 15 us/position drift with tau_true=0")
            print("  left both half-slopes positive and agreeing (+0.175 / +0.226)")
            print("  while the intercepts split by 67 us/step (-60.6 vs +6.9). The")
            print("  ABBA/BAAB sign rule is therefore NOT the sensitive statistic")
            print("  here; the intercept contrast is. Both are printed so a reader")
            print("  can apply either.")
            if not agree:
                print("  ==> the two orders disagree in sign: this ruler is reporting an")
                print("      ORDER ARTEFACT, not a byte cost. Decision rule SUSPENDED.")
            if dcs and (pct(dcs)[0] > 0 or pct(dcs)[1] < 0):
                print("  ==> the offset contrast EXCLUDES ZERO: position is doing work in")
                print("      this ruler. tau itself is protected by the rotation (see the")
                print("      negative control), but the intercept c must not be read as")
                print("      the R114 offset class alone.")

    # ---------------- HISTOGRAMS (bimodality check)
    print("\n" + "-" * 78)
    print("HISTOGRAMS -- raw paired differences, then residuals about the fit")
    print("-" * 78)
    for a in rungs:
        print(f"  {a}  (dose {DOSE_MB[a]:.3f} MB/step, pred {pred[a]:.1f} us at tau=1)")
        for ln in histogram(D[a]):
            print(ln)
    resid = [D[a][i] - (sc[0] + st[0] * pred[a])
             for a in rungs for i in range(len(blocks))]
    print("  ALL RESIDUALS about the primary fit (pooled over rungs and blocks)")
    for ln in histogram(resid):
        print(ln)
    print("  A clean unimodal residual cloud is what licenses the single-slope")
    print("  reading; an interior gap would mean two regimes are being averaged.")

    # ---------------- DIAGNOSTIC: per-rung raw ratios + residuals
    print("\n" + "-" * 78)
    print("DIAGNOSTIC -- per-rung means, raw ratios (offset-biased), and residuals")
    print("-" * 78)
    print(f"{'arm':<5}{'mean dus':>22}{'raw tau':>10}{'resid vs fit':>14}"
          f"{'median dus (boot CI95)':>34}")
    for a in rungs:
        s = summarise(D[a], a)
        raw = s[0] / pred[a]
        fit = sc[0] + st[0] * pred[a]
        bm = boot_median(D[a])
        bs = (f"{bm[0]:+8.2f} [{bm[1]:+8.2f},{bm[2]:+8.2f}]"
              if not math.isnan(bm[1]) else f"{bm[0]:+8.2f}")
        print(f"{a:<5}{s[0]:>10.2f} +/-{s[2]:>7.2f}{raw:>10.3f}{s[0]-fit:>14.2f}"
              f"{bs:>34}")
    print("  raw tau is biased by c/dbytes -- large on small rungs. Read RESIDUALS")
    print("  for linearity, not the raw column.")

    # ---------------- SECONDARY (POST-HOC, NOT PRE-REGISTERED)
    # Per-rung tau after removing that block's own fitted intercept:
    #     tau_a^b = (D[a][b] - c_b) / pred_a
    # This is the only fair way to compare rungs, because the raw ratio carries
    # the +c/pred_a bias that is 8x larger on the smallest rung than the
    # largest. It is a POST-HOC decomposition: it was NOT in the
    # pre-registration, it re-uses the same data as the primary endpoint, and
    # its per-rung intervals are NOT multiplicity-corrected. It is reported to
    # expose structure for the NEXT experiment, never to license a decision.
    print("\n" + "-" * 78)
    print("SECONDARY (POST-HOC) -- per-rung tau after removing the block's own c")
    print("-" * 78)
    print(f"{'arm':<5}{'owner of the added bytes':>28}{'tau_a (CI95)':>30}")
    owner = {"OP": "o_proj plane (pairwise)",
             "ON": "o_proj plane (lane-major)",
             "QN": "qkv plane (lane-major)",
             "AN": "both planes"}
    for a in rungs:
        per = [(D[a][i] - cs[i]) / pred[a] for i in range(len(blocks))]
        sa = summarise(per)
        print(f"{a:<5}{owner.get(a, ''):>28}{fmt_ci(sa):>30}")
    print("  If these rungs do not share one tau, then 'the byte class' is not a")
    print("  scalar: the marginal cost of a byte depends on WHICH kernel owns it")
    print("  and on how far that kernel already sits from the DRAM asymptote.")
    print("  Treat any ordering here as a hypothesis to be tested on new data.")
    print("  CONFOUND, found after launch and not pre-registered: no rung is a")
    print("  PURE byte dose. Every kill switch that resizes the plane also")
    print("  changes how the plane is addressed -- PAIRWISE=0 makes 32 lanes")
    print("  read 32 distinct scale bytes where the shipped kernel has lane 2j")
    print("  and 2j+1 share one byte, and NARROW=0 swaps a nibble walk for a")
    print("  strided byte read. That is why OP can exceed 1. It is also exactly")
    print("  the bundle an encoder change would buy, so the ruler stays")
    print("  ecologically valid for pricing an encoder -- it is just not a")
    print("  clean byte-count instrument, and must not be quoted as one.")

    # sensitivity: drop the rung whose addressing change is largest
    if all(a in D for a in ("ON", "QN", "AN")) and "OP" in D:
        sub = ["ON", "QN", "AN"]
        xs2 = [pred[a] for a in sub]
        xb2 = sum(xs2) / len(xs2)
        sxx2 = sum((x - xb2) ** 2 for x in xs2)
        t2 = []
        for i in range(len(blocks)):
            ys = [D[a][i] for a in sub]
            yb = sum(ys) / len(ys)
            t2.append(sum((x - xb2) * (y - yb)
                          for x, y in zip(xs2, ys)) / sxx2)
        print(f"\n  SENSITIVITY, OP dropped (3 rungs, 1 dof/block):"
              f" tau = {fmt_ci(summarise(t2))}")

    # ---------------- CHECK: additivity
    if all(a in D for a in ("AN", "ON", "QN")):
        raw_add = [D["AN"][i] - D["ON"][i] - D["QN"][i] for i in range(len(blocks))]
        adj_add = [v + sc[0] for v in raw_add]
        print("\n" + "-" * 78)
        print("CHECK -- additivity  AN vs ON + QN   (doses add to the byte: "
              f"{DOSE_MB['ON']}+{DOSE_MB['QN']}={DOSE_MB['ON']+DOSE_MB['QN']:.3f}"
              f" vs AN {DOSE_MB['AN']})")
        print("-" * 78)
        print(f"  raw AN-(ON+QN)      = {fmt_ci(summarise(raw_add), ' us/step', 2)}")
        print(f"    under a pure-offset model with perfect additivity this should")
        print(f"    sit at +c = {-sc[0]:+.2f}... i.e. the raw number is NOT zero-centred.")
        print(f"  intercept-adjusted  = {fmt_ci(summarise(adj_add), ' us/step', 2)}")
        print(f"    THIS is the one that should cover zero if the doses add.")

    # ---------------- raw array export
    if csv_out:
        with open(csv_out, "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["block", "arm", "pos", "control_pos", "order",
                        "control_us_per_step", "arm_us_per_step", "delta_us",
                        "dose_MB_per_step", "pred_us_at_tau1",
                        "fitted_us", "residual_us",
                        "control_golden", "arm_golden", "golden_match",
                        "control_passed", "arm_passed"])
            for i, b in enumerate(blocks):
                pc = posn.get(b, {}).get("C", "")
                gc = gold.get(b, {}).get("C", "")
                for a in rungs:
                    pa = posn.get(b, {}).get(a, "")
                    ga = gold.get(b, {}).get(a, "")
                    order = ("" if pc == "" or pa == ""
                             else ("before" if pa < pc else "after"))
                    fit = sc[0] + st[0] * pred[a]
                    w.writerow([b, a, pa, pc, order,
                                f"{lvl[b]['C']:.3f}", f"{lvl[b][a]:.3f}",
                                f"{D[a][i]:.3f}", f"{DOSE_MB[a]:.3f}",
                                f"{pred[a]:.3f}", f"{fit:.3f}",
                                f"{D[a][i]-fit:.3f}",
                                gc, ga, "yes" if (gc and ga and gc == ga) else "NO",
                                pas.get(b, {}).get("C", ""),
                                pas.get(b, {}).get(a, "")])
        print(f"\n  raw per-observation array written to {csv_out} "
              f"({len(blocks)*len(rungs)} rows)")

    print("\n" + "=" * 78)


if __name__ == "__main__":
    main()
