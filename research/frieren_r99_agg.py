"""Research-only aggregator (not part of the submission surface).

Parses a `research/frieren_r99_run_probe.sh` log and treats the sweep, not the
within-run dispatch, as the unit of replication. The probe's own paired t is
computed across 15 rounds inside one process and is far more confident than the
between-sweep spread, so it is ignored here.

Each contrast is measured in both arm orders. Any bias common to the two orders
(the base-vs-base null is about -1 %, so the CAND slot is not neutral) cancels
in `(FWD - REV) / 2`, which is the reported estimate.

Usage: python3 research/frieren_r99_agg.py LOG [K ...]
"""

import math
import re
import sys

# PROVISIONAL, inherited from the advisor's price list and r98 pool estimate.
# CURRENT_RESEARCH_STATE.md:996 gives the sliding-attention pool on both hosts:
# 636.0 us/step measured on this M4 Pro, ~290 us/step projected on the ranked
# M5. The 0.015280 %/us decode price is defined against M5 us/step (4893.7
# us/step decode, 1 % = 48.94 us/step), so the score column must use the M5
# pool; using the M4 pool overstates every conversion by 636/290.
POOL_US_M4 = 636.0
POOL_US_M5 = 290.0
SCORE_PER_US = 0.015280

ROW = re.compile(
    r"^\s*(\d+)\s+[\d.]+\s+([\d.]+)\s+([\d.]+)\s+"
    r"([-+][\d.]+)\s+([-+][\d.]+)\s+([\d.]+)\s+([-+][\d.]+)\s+([-+][\d.]+)\s*$")


def parse(path):
    """-> {(leg, order, K): [pct per sweep]}"""
    out = {}
    leg = order = None
    for line in open(path):
        if line.startswith("@@LEG"):
            _, leg, order = line.split()
        elif line.startswith("@@END"):
            leg = order = None
        elif leg:
            m = ROW.match(line)
            if m:
                out.setdefault((leg, order, int(m.group(1))), []).append(
                    float(m.group(8)))
    return out


def stats(xs):
    n = len(xs)
    mean = sum(xs) / n
    if n < 2:
        return mean, 0.0, 0.0, n
    sd = math.sqrt(sum((x - mean) ** 2 for x in xs) / (n - 1))
    return mean, sd, sd / math.sqrt(n), n


def main():
    data = parse(sys.argv[1])
    ks = [int(k) for k in sys.argv[2:]] or sorted({k for _, _, k in data})
    legs = []
    for leg, _, _ in data:
        if leg not in legs:
            legs.append(leg)

    print("estimate = (FWD - REV) / 2, percent of base kernel time, "
          "negative = candidate faster")
    print("us_m4 uses the measured %.1f us/step M4 sliding pool; us_m5 and "
          "score use the" % POOL_US_M4)
    print("projected %.1f us/step M5 pool with the %.6f %%/us M5 decode price."
          % (POOL_US_M5, SCORE_PER_US))
    print()
    hdr = ("  leg      K   fwd_mean  fwd_sd   rev_mean  rev_sd    est%"
           "    sem      t     us_m4   us_m5   score%")
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))
    for leg in legs:
        for k in ks:
            f = data.get((leg, "FWD", k))
            r = data.get((leg, "REV", k))
            if not f or not r:
                continue
            fm, fsd, fse, _ = stats(f)
            rm, rsd, rse, _ = stats(r)
            est = (fm - rm) / 2
            sem = math.sqrt(fse ** 2 + rse ** 2) / 2
            t = est / sem if sem else float("nan")
            us4 = est / 100 * POOL_US_M4
            us5 = est / 100 * POOL_US_M5
            print("  %-7s %3d  %+8.2f %7.2f  %+8.2f %7.2f  %+7.3f %6.3f "
                  "%+7.2f %+7.2f %+7.2f  %+7.3f"
                  % (leg, k, fm, fsd, rm, rsd, est, sem, t, us4, us5,
                     -us5 * SCORE_PER_US))
        print()
    print("sweeps = %d" % max(len(v) for v in data.values()))


if __name__ == "__main__":
    main()
