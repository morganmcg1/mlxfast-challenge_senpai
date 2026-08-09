#!/usr/bin/env python3
"""Segment-matched M4 Pro convexity read-out for Arm C section 10.10.

Reads the replicate-indexed per-step dumps written by armc_local_sweep.sh and
asks the question the M5 receipts answered in section 10.9: is the routed
gather-GEMM ALU ladder convex on M4 Pro too, or is M4's single steep slope flat
across the same 0 -> 24 -> 64 segments?

Directional only. The ranked M5 decides; this closes section 10.8's
segment-mismatch caveat, which is a comparability caveat, not a ranking claim.
"""
import glob
import math
import os
import re
import statistics as st
import sys

OUT = sys.argv[1] if len(sys.argv) > 1 else "/tmp/r93/armc"
WARMUP = 10
LEVELS = [0, 24, 64]

# Student t two-sided 0.05 critical values by df.
TCRIT = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447,
         7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228, 12: 2.179, 15: 2.131}


def tcrit(df):
    if df in TCRIT:
        return TCRIT[df]
    keys = sorted(TCRIT)
    return TCRIT[min(keys, key=lambda k: abs(k - df))]


def load(path):
    with open(path) as fh:
        v = [float(x) for x in fh.read().split() if x.strip()]
    return v[WARMUP:]


def collect():
    """spec level -> list of (replicate tag, median ms, trimmed mean ms)."""
    by_level = {n: [] for n in LEVELS}
    for path in sorted(glob.glob(os.path.join(OUT, "steps-[0-9][0-9]-*.txt"))):
        base = os.path.basename(path)
        m = re.match(r"steps-(\d\d)-routed-fma-(\d+)\.txt$", base)
        if not m:
            continue
        idx, n = m.group(1), int(m.group(2))
        if n not in by_level:
            continue
        v = load(path)
        if len(v) < 50:
            continue
        v_sorted = sorted(v)
        k = max(1, len(v_sorted) // 20)          # 5 % trim each tail
        trimmed = v_sorted[k:len(v_sorted) - k]
        by_level[n].append((idx, st.median(v), sum(trimmed) / len(trimmed),
                            len(v)))
    return by_level


def main():
    by_level = collect()
    missing = [n for n in LEVELS if len(by_level[n]) < 2]
    if missing:
        print(f"insufficient replicates at levels {missing}; "
              f"counts={[(n, len(by_level[n])) for n in LEVELS]}")
        return 1

    print("=" * 74)
    print("SECTION 10.10  M4 Pro segment-matched convexity (local, directional)")
    print("=" * 74)
    print(f"source={OUT}  warmup dropped={WARMUP} steps")
    print()
    print(f"{'n':>4} {'rep':>4} {'steps':>6} {'median ms':>11} {'trim5% ms':>11}")
    for n in LEVELS:
        for idx, med, trim, cnt in by_level[n]:
            print(f"{n:>4} {idx:>4} {cnt:>6} {med:>11.4f} {trim:>11.4f}")
    print()

    # Per-level replicate summary on the robust (median) statistic.
    mean, sd, nrep = {}, {}, {}
    print(f"{'n':>4} {'reps':>5} {'mean of medians':>16} {'sd':>9} {'cv %':>8}")
    for n in LEVELS:
        vals = [r[1] for r in by_level[n]]
        mean[n] = sum(vals) / len(vals)
        sd[n] = st.stdev(vals) if len(vals) > 1 else float("nan")
        nrep[n] = len(vals)
        print(f"{n:>4} {nrep[n]:>5} {mean[n]:>16.4f} {sd[n]:>9.4f} "
              f"{100 * sd[n] / mean[n]:>8.4f}")
    print()

    # Pooled within-level sd.
    ss, dfp = 0.0, 0
    for n in LEVELS:
        vals = [r[1] for r in by_level[n]]
        mu = mean[n]
        ss += sum((v - mu) ** 2 for v in vals)
        dfp += len(vals) - 1
    sp = math.sqrt(ss / dfp)
    r = min(nrep[n] for n in LEVELS)
    print(f"pooled within-level sd = {sp:.4f} ms on {dfp} df "
          f"({100 * sp / mean[0]:.4f} % of the n=0 step)")
    print()

    # Segment slopes, us per unit of n. One unit of n = 4 fma per K iteration
    # per thread, matching the M5 read-out in section 10.9.
    def seg(a, b):
        width = b - a
        d_ms = mean[b] - mean[a]
        slope_us = 1000.0 * d_ms / width
        se_us = 1000.0 * sp * math.sqrt(1.0 / nrep[a] + 1.0 / nrep[b]) / width
        tc = tcrit(dfp)
        return (d_ms, slope_us, se_us, slope_us - tc * se_us,
                slope_us + tc * se_us, slope_us / se_us)

    print(f"{'segment':>10} {'d step ms':>11} {'d step %':>9} "
          f"{'us/unit':>9} {'se':>8} {'95% CI':>22} {'t':>8}")
    segs = {}
    for a, b in [(0, 24), (24, 64), (0, 64)]:
        d_ms, slope, se, lo, hi, t = seg(a, b)
        segs[(a, b)] = (slope, se)
        pct = 100.0 * d_ms / mean[a]
        print(f"{a:>4}->{b:<5} {d_ms:>11.4f} {pct:>9.4f} {slope:>9.4f} "
              f"{se:>8.4f} [{lo:>9.4f},{hi:>9.4f}] {t:>8.3f}")
    print()

    # Convexity: slope(24->64) - slope(0->24). The n=24 mean enters both, so
    # propagate the shared term explicitly rather than adding variances.
    w1, w2 = 24.0, 40.0
    d_slope = segs[(24, 64)][0] - segs[(0, 24)][0]
    var = (1000.0 ** 2) * (sp ** 2) * (
        (1.0 / nrep[64]) / w2 ** 2
        + (1.0 / nrep[24]) * (1.0 / w2 + 1.0 / w1) ** 2
        + (1.0 / nrep[0]) / w1 ** 2)
    se_d = math.sqrt(var)
    tc = tcrit(dfp)
    t_d = d_slope / se_d
    print("CONVEXITY TEST (M4 Pro)")
    print(f"  slope(0->24)   = {segs[(0, 24)][0]:.4f} us/unit")
    print(f"  slope(24->64)  = {segs[(24, 64)][0]:.4f} us/unit")
    print(f"  delta slope    = {d_slope:+.4f} us/unit  se {se_d:.4f}")
    print(f"  t({dfp} df)      = {t_d:+.3f}   crit {tc:.3f}   "
          f"{'CONVEX' if abs(t_d) > tc and d_slope > 0 else 'not resolved'}")
    print(f"  95% CI         = [{d_slope - tc * se_d:+.4f}, "
          f"{d_slope + tc * se_d:+.4f}]")
    if segs[(0, 24)][0] != 0:
        print(f"  slope ratio    = {segs[(24, 64)][0] / segs[(0, 24)][0]:.2f}x")
    print()

    # Direct comparison with the M5 receipts (section 10.9).
    m5 = {"lo": (1.1657, 4910.9253), "hi": (8.0696, 4910.9253)}
    print("M4 Pro vs M5, same segments, as a fraction of that machine's step")
    print(f"{'segment':>10} {'M4 us/unit':>11} {'M4 %/unit':>10} "
          f"{'M5 us/unit':>11} {'M5 %/unit':>10} {'M4/M5':>7}")
    for (a, b), key in [((0, 24), "lo"), ((24, 64), "hi")]:
        m4_slope = segs[(a, b)][0]
        m4_pct = 100.0 * m4_slope / (1000.0 * mean[0])
        m5_slope, m5_step = m5[key]
        m5_pct = 100.0 * m5_slope / m5_step
        print(f"{a:>4}->{b:<5} {m4_slope:>11.4f} {m4_pct:>10.4f} "
              f"{m5_slope:>11.4f} {m5_pct:>10.4f} "
              f"{m4_slope / m5_slope:>7.2f}")
    print()

    # Bit-exactness across every replicate and level.
    hashes = {}
    for path in sorted(glob.glob(os.path.join(OUT, "tokens-[0-9][0-9]-*.txt"))):
        with open(path) as fh:
            body = fh.read()
        hashes.setdefault(hash(body), []).append(os.path.basename(path))
    print(f"token-stream identity across {sum(len(v) for v in hashes.values())} "
          f"runs: {len(hashes)} distinct stream(s) "
          f"{'(bit-exact)' if len(hashes) == 1 else '(MISMATCH)'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
