#!/usr/bin/env python3
"""Paired statistics for the R114-E gate_sp grid-append fusion ABBA.

Reads one or more TSVs written by
`research/maple-alphonse-r114-gatesp-fusion-abba.sh` and reports the two
interval estimators that the balanced CFFC design admits.  Both estimators
share the SAME point estimate; they differ only in the variance model and
the degrees of freedom, so reporting both is the honest framing rather than
a choice between them.

  block     one delta per CFFC quadruple, mean(F) - mean(C).  Cancels a
            linear host drift exactly inside each block.  Few df.
  adjacent  one delta per disjoint neighbouring C/F pair, always signed
            F - C.  The design supplies equal numbers of C-first and
            F-first pairs, so a linear drift cancels across the pair set
            while giving 2x the residual df of the block estimator.

Usage: research/maple-alphonse-r114-gatesp-abba-stats.py TSV [TSV ...]
"""

import statistics
import sys

# Verified win bar for this assignment: +0.25 % of M4 decode wall.
BAR_US = 36.0

# two-sided 95 % Student-t critical values, indexed by degrees of freedom
T_CRIT = {
    1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365,
    8: 2.306, 9: 2.262, 10: 2.228, 11: 2.201, 12: 2.179, 13: 2.160,
    14: 2.145, 15: 2.131, 16: 2.120, 17: 2.110, 18: 2.101, 19: 2.093,
    20: 2.086, 21: 2.080, 22: 2.074, 23: 2.069, 24: 2.064, 25: 2.060,
    26: 2.056, 27: 2.052, 28: 2.048, 29: 2.045, 30: 2.042,
}


def t_crit(df):
    if df < 1:
        return None
    if df in T_CRIT:
        return T_CRIT[df]
    return 1.960 if df > 30 else None


def load(paths):
    """Return [(arm, decode_s, prefill_s)] in acquisition order."""
    rows = []
    for path in paths:
        with open(path) as handle:
            for line in handle:
                parts = line.rstrip("\n").split("\t")
                if len(parts) < 5 or parts[0] == "idx":
                    continue
                arm, dec, pre, passed = parts[1], parts[2], parts[3], parts[4]
                if passed != "true":
                    sys.exit(f"{path}: run {parts[0]} did not pass: {parts[5:]}")
                rows.append((arm, float(dec), float(pre)))
    return rows


def summarize(rows, index, label, unit_us):
    """Per-arm run-to-run spread on one metric."""
    print(f"  {label}")
    for arm in ("C", "F"):
        vals = [r[index] for r in rows if r[0] == arm]
        mean = statistics.fmean(vals)
        sd = statistics.stdev(vals) if len(vals) > 1 else float("nan")
        print(
            f"    {arm}  n={len(vals):2d}  mean={mean:.10f}  "
            f"sd={sd * unit_us:7.1f} us  ({100 * sd / mean:.2f} %)"
        )
    c = statistics.fmean([r[index] for r in rows if r[0] == "C"])
    f = statistics.fmean([r[index] for r in rows if r[0] == "F"])
    print(
        f"    point estimate  F-C = {(f - c) * unit_us:+8.1f} us "
        f"({100 * (f - c) / c:+.3f} %)"
    )
    return (f - c) * unit_us


def block_deltas(rows):
    """mean(F) - mean(C) inside each complete CFFC-style quadruple."""
    out = []
    for start in range(0, len(rows) - 3, 4):
        quad = rows[start:start + 4]
        c = [r[1] for r in quad if r[0] == "C"]
        f = [r[1] for r in quad if r[0] == "F"]
        if len(c) == 2 and len(f) == 2:
            out.append(statistics.fmean(f) - statistics.fmean(c))
    return out


def adjacent_deltas(rows):
    """F - C over disjoint neighbouring opposite-arm pairs, left to right."""
    out = []
    i = 0
    while i < len(rows) - 1:
        a, b = rows[i], rows[i + 1]
        if a[0] != b[0]:
            f = a[1] if a[0] == "F" else b[1]
            c = a[1] if a[0] == "C" else b[1]
            out.append(f - c)
            i += 2
        else:
            i += 1
    return out


def welch(rows, unit_us):
    """Unpaired Welch interval: throws the pairing away as a robustness check."""
    c = [r[1] for r in rows if r[0] == "C"]
    f = [r[1] for r in rows if r[0] == "F"]
    if len(c) < 2 or len(f) < 2:
        return
    vc, vf = statistics.variance(c) / len(c), statistics.variance(f) / len(f)
    mean = (statistics.fmean(f) - statistics.fmean(c)) * unit_us
    se = (vc + vf) ** 0.5 * unit_us
    df = int((vc + vf) ** 2 / (vc ** 2 / (len(c) - 1) + vf ** 2 / (len(f) - 1)))
    crit = t_crit(df)
    lo, hi = mean - crit * se, mean + crit * se
    verdict = "excludes zero" if hi < 0 or lo > 0 else "INCLUDES ZERO"
    bar = "clears bar" if hi < -BAR_US else "does not clear bar"
    print(
        f"  {'unpaired':9s} df={df:2d}  mean={mean:+8.1f} us  {' ' * 12}"
        f"se={se:5.1f}  95% CI [{lo:+8.1f}, {hi:+8.1f}]  "
        f"({verdict}, {bar})"
    )


def interval(name, deltas, unit_us):
    n = len(deltas)
    if n < 2:
        print(f"  {name:9s} n={n} -- too few for an interval")
        return
    mean = statistics.fmean(deltas) * unit_us
    sd = statistics.stdev(deltas) * unit_us
    se = sd / n ** 0.5
    crit = t_crit(n - 1)
    lo, hi = mean - crit * se, mean + crit * se
    neg = sum(1 for d in deltas if d < 0)
    verdict = "excludes zero" if hi < 0 or lo > 0 else "INCLUDES ZERO"
    bar = "clears bar" if hi < -BAR_US else "does not clear bar"
    print(
        f"  {name:9s} n={n:2d}  mean={mean:+8.1f} us  sd={sd:6.1f}  "
        f"se={se:5.1f}  95% CI [{lo:+8.1f}, {hi:+8.1f}]  "
        f"({neg}/{n} negative, {verdict}, {bar})"
    )


def main():
    paths = sys.argv[1:]
    if not paths:
        sys.exit(__doc__)
    rows = load(paths)
    print(f"runs: {len(rows)}  order: {''.join(r[0] for r in rows)}")
    print(f"bar : {BAR_US:.1f} us/step of decode wall (win must beat this)")

    print("\ndecode seconds/token")
    summarize(rows, 1, "per-arm spread", 1e6)
    print("\nprefill seconds/token")
    summarize(rows, 2, "per-arm spread", 1e6)

    print("\npaired interval estimators on decode us/step")
    interval("block", block_deltas(rows), 1e6)
    interval("adjacent", adjacent_deltas(rows), 1e6)
    welch(rows, 1e6)


if __name__ == "__main__":
    main()
