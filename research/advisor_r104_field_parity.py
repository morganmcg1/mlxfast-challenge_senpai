#!/usr/bin/env python3
"""Round-104 field-parity arithmetic (§8.4 of advisor-r104-the-receipt-is-the-instrument.md).

Inputs are the `cs` values already extracted from the MLXFast API by
research/advisor_r104_record_watch.py (2026-08-09T23:20Z snapshot).  This file
exists so the parity claim in §8.4 is reproducible without re-hitting the API.

Rule 58: reuse research/advisor_r104_record_watch.py to refresh the inputs.
"""
import math

# Round-103 flagship, trimmed dof-14 identical-code statistics.
OUR_CS = 2.583111        # honest geometric-mean cs of our tree
SD_LN_CS = 0.001860      # 0.1860 %, identical-code noise floor


def geo_mean(xs):
    return math.exp(sum(math.log(x) for x in xs) / len(xs))


def sd_ln(xs):
    ls = [math.log(x) for x in xs]
    m = sum(ls) / len(ls)
    return (sum((x - m) ** 2 for x in ls) / (len(ls) - 1)) ** 0.5


def chi2_sf_dof4(x):
    """P(chi2_4 > x); closed form for even dof=4."""
    return math.exp(-x / 2.0) * (1.0 + x / 2.0)


def report(name, cs_values):
    n = len(cs_values)
    m = math.log(geo_mean(cs_values))
    sd = sd_ln(cs_values)
    d = m - math.log(OUR_CS)
    se = SD_LN_CS / math.sqrt(n)          # our sd as a fixed known prior
    lo, hi = d - 1.96 * se, d + 1.96 * se
    print(f"{name}: n={n}  geometric-mean cs = {math.exp(m):.6f}"
          f"  ({100 * (math.exp(m) / OUR_CS - 1):+.4f} % vs ours)")
    print(f"    their own sd(ln cs) = {100 * sd:.4f} %"
          f"   (our identical-code floor = {100 * SD_LN_CS:.4f} %)")
    if n > 1:
        stat = (n - 1) * (sd / SD_LN_CS) ** 2
        if n == 5:
            print(f"    chi2 = {stat:.2f} on {n - 1} dof, p = {chi2_sf_dof4(stat):.3f}"
                  "  -> consistent with ONE fixed tree measured n times"
                  if chi2_sf_dof4(stat) > 0.05 else
                  f"    chi2 = {stat:.2f} on {n - 1} dof, p = {chi2_sf_dof4(stat):.3f}"
                  "  -> spread exceeds identical-code noise")
    print(f"    z = {d / se:+.2f}   95 % CI on the difference: "
          f"[{100 * lo:+.3f} %, {100 * hi:+.3f} %]"
          f"   => {'PARITY' if lo < 0 < hi else 'a real difference'}")


if __name__ == "__main__":
    # fyrsta7: first receipt 2026-08-09T14:43:45Z, 5 receipts in ~3 h.
    report("fyrsta7", [2.574051, 2.582983, 2.585463, 2.589921, 2.580958])
    # yudduy: best three trees (the fourth, 2.480240, is a different, slower tree).
    report("yudduy(best 3)", [2.585059, 2.571616, 2.579496])
