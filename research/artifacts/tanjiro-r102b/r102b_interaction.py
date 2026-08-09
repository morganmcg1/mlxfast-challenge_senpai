#!/usr/bin/env python3
"""Combine the R102-B 2x2 duplex sessions into per-kernel interaction terms.

Session A contrasts arm00 -> arm10 (R1 with R2 absent);
Session B contrasts arm01 -> arm11 (R1 with R2 present);
Session C contrasts arm00 -> arm11 (the whole composed tree).

The interaction of R1 and R2 is I = B - A. Session C supplies the total and,
with A and B, the two conditional R2 effects.

Usage: r102b_interaction.py sessA_stats.txt sessB_stats.txt [sessC_stats.txt]
"""
from __future__ import annotations

import math
import re
import sys

PCT_PER_US_STEP = 0.015280  # research/maple_pr443_duplex_stats.py

KERNEL_RE = re.compile(
    r"^\s*[\d.]+\s+([+-][\d.]+) \[\s*([+-][\d.]+),\s*([+-][\d.]+)\]"
    r"\s+[+-][\d.]+ \[[^\]]*\]\s+[\d.]+\s+(\*\*\*)?\s*(\S+)\s*$"
)
TOTAL_RE = re.compile(
    r"^total steady GPU busy, ratio-adjusted vs control: "
    r"([+-][\d.]+) us/step \[([+-][\d.]+), ([+-][\d.]+)\]"
)
NDUP_RE = re.compile(r"n_duplex=(\d+)")


def parse(path):
    kernels, total, ndup = {}, None, None
    with open(path) as fh:
        for line in fh:
            m = NDUP_RE.search(line)
            if m and ndup is None:
                ndup = int(m.group(1))
            m = KERNEL_RE.match(line)
            if m:
                d, lo, hi, _sig, name = m.groups()
                kernels[name] = (float(d), (float(hi) - float(lo)) / 2.0)
                continue
            m = TOTAL_RE.match(line)
            if m:
                d, lo, hi = (float(g) for g in m.groups())
                total = (d, (hi - lo) / 2.0)
    if total is None:
        raise SystemExit(f"no ratio-adjusted total found in {path}")
    return kernels, total, ndup


def comb(x, y):
    """Difference y - x with quadrature-combined 95% half-widths."""
    return y[0] - x[0], math.hypot(x[1], y[1])


def fmt(v):
    d, hw = v
    star = "  *" if abs(d) > hw else "   "
    return f"{d:+7.2f} [{d - hw:+7.2f}, {d + hw:+7.2f}]{star}"


def main(argv):
    if len(argv) < 3:
        raise SystemExit(__doc__)
    a_k, a_t, a_n = parse(argv[1])
    b_k, b_t, b_n = parse(argv[2])
    c_k = c_t = c_n = None
    if len(argv) > 3:
        c_k, c_t, c_n = parse(argv[3])

    print("R102-B composed-restoration 2x2, ratio-adjusted us/step "
          "(negative = candidate faster)")
    print(f"  A: arm00 -> arm10   R1 | R2=0   n_duplex={a_n}")
    print(f"  B: arm01 -> arm11   R1 | R2=1   n_duplex={b_n}")
    if c_t:
        print(f"  C: arm00 -> arm11   R1+R2 total  n_duplex={c_n}")
    print("  bands are 95% CIs; quadrature-combined for derived quantities; "
          "* marks exclusion of zero")

    names = [n for n in a_k if n in b_k]
    names.sort(key=lambda n: -abs(comb(a_k[n], b_k[n])[0]))

    print("\n== R1 conditional effect and interaction I = B - A ==")
    print(f"{'kernel':<52} {'A: R1|R2=0':>26} {'B: R1|R2=1':>26} "
          f"{'I = B - A':>26}")
    for n in names:
        i = comb(a_k[n], b_k[n])
        if abs(a_k[n][0]) < 1.0 and abs(b_k[n][0]) < 1.0 and abs(i[0]) < 1.0:
            continue
        print(f"{n:<52} {fmt(a_k[n]):>26} {fmt(b_k[n]):>26} {fmt(i):>26}")
    i_tot = comb(a_t, b_t)
    print(f"{'TOTAL steady GPU busy':<52} {fmt(a_t):>26} {fmt(b_t):>26} "
          f"{fmt(i_tot):>26}")
    print(f"{'  as M5 score %':<52} "
          f"{-a_t[0] * PCT_PER_US_STEP:+25.4f} "
          f"{-b_t[0] * PCT_PER_US_STEP:+25.4f} "
          f"{-i_tot[0] * PCT_PER_US_STEP:+25.4f}")

    if c_t is None:
        return
    print("\n== total and the two conditional R2 effects ==")
    r2_at0 = comb(b_t, c_t)   # (t11-t00) - (t11-t01) = t01-t00
    r2_at1 = comb(a_t, c_t)   # (t11-t00) - (t10-t00) = t11-t10
    add = (r2_at0[0] + a_t[0], math.hypot(r2_at0[1], a_t[1]))
    rows = [
        ("C total  t11 - t00 (R1+R2 vs control)", c_t),
        ("R2 | R1=0  t01 - t00  = C - B", r2_at0),
        ("R2 | R1=1  t11 - t10  = C - A", r2_at1),
        ("additive prediction  A + (R2|R1=0)", add),
        ("identity check  (R2|R1=1) - (R2|R1=0) == I", comb(r2_at0, r2_at1)),
        ("residual  C - additive", comb(add, c_t)),
    ]
    for label, v in rows:
        print(f"{label:<52} {fmt(v):>26}   "
              f"score {-v[0] * PCT_PER_US_STEP:+.4f}%")


if __name__ == "__main__":
    main(sys.argv)
