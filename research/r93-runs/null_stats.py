#!/usr/bin/env python3
"""Arm A summary and the section-3 minimum-resolvable-difference table.

Reads the null receipts directly so the report can never drift from the
receipts. chi2_ci comes from channel_noise (scipy is not available on this
host), so importing it also prints that module's own analysis; run this with
stdout filtered if that is noisy.
"""
import glob
import json
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))

# t(0.975, df) for the df values used below.
T975 = {2: 4.303, 4: 2.776, 6: 2.447, 8: 2.306, 10: 2.228,
        14: 2.145, 3: 3.182, 5: 2.571, 7: 2.365}


# chi2 0.025/0.975 quantiles, same table as critique_checks.py. Wilson-Hilferty
# is 4 % optimistic on the upper tail at df=4, which is the df this report uses.
CHI2 = {1: (0.000982, 5.024), 2: (0.0506, 7.378), 3: (0.2158, 9.348),
        4: (0.4844, 11.143), 5: (0.8312, 12.833), 6: (1.2373, 14.449),
        7: (1.6899, 16.013), 8: (2.1797, 17.535)}


def chi2_ci_mult(n):
    """95% CI on sigma as a multiple of its point estimate."""
    df = n - 1
    if df in CHI2:
        lo, hi = CHI2[df]
    else:
        def q(z):
            return df * (1 - 2 / (9 * df) + z * math.sqrt(2 / (9 * df))) ** 3
        lo, hi = q(-1.959964), q(1.959964)
    return math.sqrt(df / hi), math.sqrt(df / lo)


def mean_sd(xs):
    m = sum(xs) / len(xs)
    v = sum((x - m) ** 2 for x in xs) / (len(xs) - 1)
    return m, math.sqrt(v)


def main():
    rows = []
    for path in sorted(glob.glob(os.path.join(HERE, "receipts", "null-*.json"))):
        d = json.load(open(path))["submission"]
        m = d["officialMetrics"]
        rows.append((os.path.basename(path)[:-5],
                     m["decode_seconds_per_token"] * 1e6,
                     m["prefill_seconds_per_token"] * 1e6,
                     m["baseline_decode_seconds_per_token"] * 1e6,
                     m["baseline_prefill_seconds_per_token"] * 1e6))
    n = len(rows)
    print("ARM A  n=%d" % n)
    print("| marker | cand decode us | cand prefill us | bl decode us | bl prefill us |")
    print("|---|---|---|---|---|")
    for r in rows:
        print("| `%s` | %.3f | %.4f | %.3f | %.3f |" % r)

    lo, hi = chi2_ci_mult(n)
    out = {}
    for i, name in enumerate(["cand decode", "cand prefill", "bl decode", "bl prefill"], start=1):
        xs = [r[i] for r in rows]
        m, s = mean_sd(xs)
        cv = 100.0 * s / m
        out[name] = (m, s, cv)
        print("%-13s mean %10.4f  sd %8.4f  CV %.4f%%  95%% CI [%.4f%%, %.4f%%]"
              % (name, m, s, cv, cv * lo, cv * hi))
    print("chi2 multipliers at n=%d: [%.3f, %.3f]" % (n, lo, hi))

    BOUND = {"cand decode": 0.2924, "cand prefill": 0.2573}
    for k, b in BOUND.items():
        m, s, cv = out[k]
        print("%-13s point/bound = %.3f   upper/bound = %.3f   %s"
              % (k, cv / b, cv * hi / b,
                 "CONFIRMED below bound" if cv * hi < b else "consistent, not confirmed"))

    print()
    print("SECTION 3: minimum resolvable |delta decode|, two arms of n receipts")
    dm = out["cand decode"][0]
    sig = out["cand decode"][2]
    sig_plan = 0.4261          # corpus near-replicate sigma, section 9.5
    slope = 2.3403             # us per dispatch, section 4
    print("| n per arm | df | t(.975) | min |d| (raw us) | | in us/step | in dispatches | min |d| planning sigma |")
    print("|---|---|---|---|---|---|---|")
    for nn in (2, 3, 4, 6, 8):
        df = 2 * nn - 2
        t = T975[df]
        mrd = t * sig * math.sqrt(2.0 / nn)
        mrd_us = mrd / 100.0 * dm
        mrd_plan = t * sig_plan * math.sqrt(2.0 / nn)
        print("| %d | %d | %.3f | %.4f%% | %.2f us | %.2f | %.4f%% (%.2f us) |"
              % (nn, df, t, mrd, mrd_us, mrd_us / slope,
                 mrd_plan, mrd_plan / 100.0 * dm))


if __name__ == "__main__":
    main()
