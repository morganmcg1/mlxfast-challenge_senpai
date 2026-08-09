"""Robustness checks on the corr(candidate, same-session baseline) ~ 0 claim.

The solver-day de-meaning estimator can be attenuated toward zero if a solver's
candidate timing trends within a day while the baseline does not. These variants
guard against that.
"""
import json
import math
import statistics as st
import sys
from collections import defaultdict
from datetime import datetime

r = json.load(open(sys.argv[1] if len(sys.argv) > 1
                   else "research/r93-runs/receipts-latest.json"))
for x in r:
    x["t"] = datetime.strptime(x["ts"], "%Y-%m-%dT%H:%M:%SZ")
r.sort(key=lambda x: x["t"])
g = defaultdict(list)
for x in r:
    g[(x["solver"], x["ts"][:10])].append(x)


def corr(A, B):
    n = len(A)
    sa = (sum(z * z for z in A) / (n - 1)) ** 0.5
    sb = (sum(z * z for z in B) / (n - 1)) ** 0.5
    rho = (sum(a * b for a, b in zip(A, B)) / (n - 1)) / (sa * sb)
    se = 1 / math.sqrt(n - 3)
    return n, rho, math.tanh(math.atanh(rho) - 1.96 * se), math.tanh(math.atanh(rho) + 1.96 * se)


def report(lab, A, B):
    n, rho, lo, hi = corr(A, B)
    print("    %-42s n=%4d  corr=%+.4f  95%% CI [%+.4f, %+.4f]" % (lab, n, rho, lo, hi))


for axis, ka, kb in [("DECODE", "cand_dec", "bl_dec"), ("PREFILL", "cand_pre", "bl_pre")]:
    print("=" * 78)
    print(axis)
    print("=" * 78)

    # (a) baseline estimator: de-mean within solver-day, n>=5
    A, B = [], []
    for v in g.values():
        if len(v) < 5:
            continue
        a = [x[ka] for x in v]
        b = [x[kb] for x in v]
        ma, mb = st.mean(a), st.mean(b)
        A += [z - ma for z in a]
        B += [z - mb for z in b]
    report("(a) solver-day de-meaned, n>=5", A, B)

    # (b) first differences within solver-day: removes any linear drift in code perf
    A, B = [], []
    for v in g.values():
        if len(v) < 3:
            continue
        for i in range(len(v) - 1):
            A.append(v[i + 1][ka] - v[i][ka])
            B.append(v[i + 1][kb] - v[i][kb])
    report("(b) first differences within solver-day", A, B)

    # (c) near-replicate groups only: solver-day where candidate CV < 0.5%
    A, B = [], []
    ngrp = 0
    for v in g.values():
        if len(v) < 4:
            continue
        a = [x[ka] for x in v]
        if 100 * st.stdev(a) / st.mean(a) >= 0.5:
            continue
        ngrp += 1
        b = [x[kb] for x in v]
        ma, mb = st.mean(a), st.mean(b)
        A += [z - ma for z in a]
        B += [z - mb for z in b]
    if len(A) > 4:
        report("(c) near-replicate groups (cand CV<0.5%%), %d grps" % ngrp, A, B)
    else:
        print("    (c) near-replicate groups: too few (%d)" % len(A))

    # (d) consecutive same-solver pairs <=60 min apart
    A, B = [], []
    for v in g.values():
        for i in range(len(v) - 1):
            if (v[i + 1]["t"] - v[i]["t"]).total_seconds() <= 3600:
                A.append(v[i + 1][ka] - v[i][ka])
                B.append(v[i + 1][kb] - v[i][kb])
    report("(d) consecutive same-solver pairs <=60min", A, B)

    # power: what correlation could we have missed?
    n = len(A)
    print("    -> with n=%d, 95%% CI half-width on rho is ~%.3f; a true rho above"
          % (n, 1.96 / math.sqrt(n - 3)))
    print("       that would have been detected. Variance reduction from pairing is")
    print("       1-rho^2 at best, so |rho|<0.1 means <1%% variance saved.")
    print()
