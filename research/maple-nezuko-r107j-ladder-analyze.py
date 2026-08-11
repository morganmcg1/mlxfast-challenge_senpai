#!/usr/bin/env python3
"""R107-J' 7.6 commit-cadence ladder: blocked paired analysis + kill switches.

Reads the TSV emitted by research/maple-nezuko-r107j-certify.sh for the four-arm
ladder (CTL, S1, S0, N400) and prints, for every ordered pair of arms, the
blocked paired-difference CI95 in M4 us/token, then the two DERIVED structural
quantities the ladder was preregistered to measure:

    primary   S1 - S0  = 39 * c      c = per-commit-boundary cost (us/step/commit)
    liveness  N400 - S1 = 360 * s    s = per-dispatch cost        (us/step/dispatch)

Everything printed here is host=M4-Pro . epoch=R107 . MARGINAL except the
per-arm LEVELS block, which is CENSUS (whole-model 1023-step decode rate).

Kill switches (all four preregistered in 7.6, before any row was read):
  K1 liveness   N400 - S1 CI95 must exclude zero and be positive
  K2 identity   one golden hash across every row of every arm
  K3 prefill    every prefill paired CI95 must cover zero
  K4 symmetry   every contrast is reported whether or not it helps

Scoring of 9.6's preregistered three-way discrimination on s is printed last.

Usage: python3 /tmp/r107j-ladder-analyze.py ROWS.tsv
"""
import math
import sys
from collections import OrderedDict, defaultdict

T975 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365,
        8: 2.306, 9: 2.262, 10: 2.228, 11: 2.201, 12: 2.179, 13: 2.160,
        14: 2.145, 15: 2.131, 16: 2.120, 17: 2.110, 18: 2.101, 19: 2.093,
        20: 2.086, 21: 2.080, 22: 2.074, 23: 2.069, 24: 2.064, 25: 2.060}

PCS_PER_M5_US = 0.015228   # % of cs per M5 us/step
K_GRID = OrderedDict([("k=1.0 floor", 1.0), ("k=1.890 105.24-4", 1.890),
                      ("alpha 0.4369", 0.4369), ("beta 0.5000", 0.5000)])

# 9.6 preregistered predictions for the liveness contrast N400-S1 = 360*s
PREREG = OrderedDict([
    ("#483 s=0.108", 38.9),
    ("frieren arm-F s=0.4478", 161.2),
    ("rule 57 s=1.2382", 445.8),
])

ARMS = ["CTL", "S1", "S0", "N400"]


def tstar(dof):
    if dof in T975:
        return T975[dof]
    return 1.96 if dof > 30 else T975[max(k for k in T975 if k <= dof)]


def ci(xs):
    """mean, half-width, sd of a list of paired differences."""
    n = len(xs)
    m = sum(xs) / n
    if n < 2:
        return m, float("nan"), float("nan"), n
    sd = math.sqrt(sum((x - m) ** 2 for x in xs) / (n - 1))
    return m, tstar(n - 1) * sd / math.sqrt(n), sd, n


def verdict(m, hw, want_positive=False):
    """Three-valued: not enough data / covers zero / excludes zero."""
    if hw != hw:                      # nan
        return "n/a (need >=2 blocks)"
    if abs(m) <= hw:
        return "covers 0"
    if want_positive and m < 0:
        return "excludes 0 but WRONG SIGN"
    return "excludes 0"


def ols_contrasts(dec, blocks, arms, pos):
    """Additive block+position+arm least squares, as a position-imbalance fallback.

    With the certify script's rotation the design is a replicated 4x4 Latin square, so
    when every block is complete this reproduces the paired estimate exactly. It only
    does work when blocks had to be dropped and position balance is therefore broken.
    """
    try:
        import numpy as np
    except Exception:
        return None
    y, rows = [], []
    bidx = {b: i for i, b in enumerate(blocks)}
    aidx = {a: i for i, a in enumerate(arms)}
    npos = len(arms)
    for b in blocks:
        for a in arms:
            r = [1.0]
            r += [1.0 if bidx[b] == i else 0.0 for i in range(1, len(blocks))]
            p = pos[b][a]
            r += [1.0 if p == i else 0.0 for i in range(2, npos + 1)]
            r += [1.0 if aidx[a] == i else 0.0 for i in range(1, len(arms))]
            rows.append(r)
            y.append(dec[b][a])
    X = np.array(rows)
    yv = np.array(y)
    dof = X.shape[0] - np.linalg.matrix_rank(X)
    beta, *_ = np.linalg.lstsq(X, yv, rcond=None)
    resid = yv - X @ beta
    sigma2 = float(resid @ resid) / dof
    XtXi = np.linalg.pinv(X.T @ X)
    na = len(arms)
    base = X.shape[1] - (na - 1)

    def contrast(a, b_):
        v = np.zeros(X.shape[1])
        if aidx[a] > 0:
            v[base + aidx[a] - 1] += 1.0
        if aidx[b_] > 0:
            v[base + aidx[b_] - 1] -= 1.0
        est = float(v @ beta)
        se = math.sqrt(sigma2 * float(v @ XtXi @ v))
        return est, tstar(dof) * se
    return contrast, dof


def load(path):
    rows = []
    with open(path) as fh:
        header = fh.readline().rstrip("\n").split("\t")
        for line in fh:
            f = line.rstrip("\n").split("\t")
            if len(f) < len(header):
                continue
            rows.append(dict(zip(header, f)))
    return rows


def main():
    rows = load(sys.argv[1])
    dec = defaultdict(dict)    # block -> arm -> us/token
    pre = defaultdict(dict)
    pos = defaultdict(dict)
    goldens, passed, arms_seen = set(), set(), []
    for r in rows:
        b, a = int(r["block"]), r["arm"]
        dec[b][a] = float(r["decode_s_per_token"]) * 1e6
        pre[b][a] = float(r["prefill_s_per_token"]) * 1e6
        pos[b][a] = int(r["pos"])
        goldens.add(r["golden"])
        passed.add(r["passed"])
        if a not in arms_seen:
            arms_seen.append(a)
    order = [a for a in ARMS if a in arms_seen] + [a for a in arms_seen if a not in ARMS]
    full = sorted(b for b in dec if len(dec[b]) == len(order))
    print("rows=%d  blocks_complete=%d  arms=%s" % (len(rows), len(full), ",".join(order)))
    print("K2 identity: %d distinct golden hash(es) %s | passed values %s"
          % (len(goldens), sorted(x[:12] for x in goldens), sorted(passed)))
    print()

    balanced = True
    print("POSITION BALANCE over the %d complete blocks used (rotation design: each arm"
          " should hit each of the %d positions equally often)" % (len(full), len(order)))
    for a in order:
        counts = [sum(1 for b in full if pos[b][a] == p) for p in range(1, len(order) + 1)]
        ok = len(set(counts)) == 1
        balanced = balanced and ok
        print("  %-5s positions %s  %s" % (a, counts, "balanced" if ok else "*** IMBALANCED ***"))
    if not balanced:
        print("  -> position is confounded with arm in the raw paired contrasts; the additive"
              " block+pos+arm fit below is the estimate to read.")
    print()

    print("LEVELS  host=M4-Pro . epoch=R107 . CENSUS   (mean over complete blocks)")
    for a in order:
        xs = [dec[b][a] for b in full]
        m, hw, sd, n = ci(xs)
        print("  %-5s n=%2d  decode %9.3f us/token  sd %6.3f (cv %.3f %%)  mean pos %.2f"
              % (a, n, m, sd, 100.0 * sd / m, sum(pos[b][a] for b in full) / max(1, len(full))))
    print()

    print("PAIRED DIFFERENCES  host=M4-Pro . epoch=R107 . MARGINAL  (M4 us/token)")
    diffs = {}
    for i, a in enumerate(order):
        for bb in order[i + 1:]:
            xs = [dec[b][bb] - dec[b][a] for b in full]
            m, hw, sd, n = ci(xs)
            diffs[(bb, a)] = (m, hw, sd, n, xs)
            neg = sum(1 for x in xs if x < 0)
            print("  %-5s - %-5s  D %+9.3f  CI95 [%+9.3f, %+9.3f]  hw %7.3f  sd %6.3f  n=%d  neg %d/%d  %s"
                  % (bb, a, m, m - hw, m + hw, hw, sd, n, neg, n, verdict(m, hw)))
    print()

    if len(full) >= 2:
        fit = ols_contrasts(dec, full, order, pos)
        if fit is not None:
            contrast, dof = fit
            print("ADDITIVE block+position+arm FIT (robustness; identical to the paired estimate"
                  " when position balance holds)  dof=%d" % dof)
            for i, a in enumerate(order):
                for bb in order[i + 1:]:
                    est, hw = contrast(bb, a)
                    print("  %-5s - %-5s  D %+9.3f  CI95 [%+9.3f, %+9.3f]  %s"
                          % (bb, a, est, est - hw, est + hw, verdict(est, hw)))
            print()

    print("PREFILL (K3: every CI95 must cover zero)  MARGINAL  M4 us/token")
    for i, a in enumerate(order):
        for bb in order[i + 1:]:
            xs = [pre[b][bb] - pre[b][a] for b in full]
            m, hw, sd, n = ci(xs)
            v = verdict(m, hw)
            print("  %-5s - %-5s  D %+8.3f  CI95 [%+8.3f, %+8.3f]  %s"
                  % (bb, a, m, m - hw, m + hw,
                     v if v != "excludes 0" else "*** EXCLUDES 0 -> K3 FAIL ***"))
    print()

    def show(label, key, divisor, unit):
        sign = 1.0
        if key not in diffs:
            if (key[1], key[0]) in diffs:      # stored in the other orientation
                key_, sign = (key[1], key[0]), -1.0
            else:
                print("  %s: arms missing" % label)
                return None
        else:
            key_ = key
        m, hw, sd, n, xs = diffs[key_]
        m = sign * m
        print("  %s = %s - %s = %d * %s" % (label, key[0], key[1], divisor, unit))
        print("    contrast %+9.3f  CI95 [%+9.3f, %+9.3f]  hw %7.3f  n=%d" % (m, m - hw, m + hw, hw, n))
        print("    %-4s     %+9.4f  CI95 [%+9.4f, %+9.4f]  hw %7.4f"
              % (unit, m / divisor, (m - hw) / divisor, (m + hw) / divisor, hw / divisor))
        return m, hw, n

    print("DERIVED STRUCTURAL QUANTITIES  MARGINAL")
    c = show("primary  ", ("S1", "S0"), 39, "c")
    print()
    s = show("liveness ", ("N400", "S1"), 360, "s")
    print()

    if s is not None and s[1] == s[1]:
        m, hw, n = s
        live_ok = abs(m) > hw and m > 0
        print("K1 liveness: %s (D %+.3f, hw %.3f)"
              % ("PASS - injected dispatches reach the GPU and cost time" if live_ok
                 else "*** FAIL -> ladder VOID, 3A positive control re-arms (7.6 + 3B) ***", m, hw))
        print()
        print("9.6 preregistered three-way discrimination on s (written before any row read)")
        for name, pred in PREREG.items():
            print("    %-24s predicts %+8.1f  ->  measured is %+6.2f half-widths away  %s"
                  % (name, pred, (m - pred) / hw,
                     "CONSISTENT" if abs(m - pred) <= hw else "rejected at CI95"))
        print()
        print("    s promoted to % of cs for ONE merge (n=40 dispatches/step removed, 105.24"
              " family E). Sign convention: positive = a merge that removes them SAVES time.")
        for kn, kv in K_GRID.items():
            eff = 40.0 * (m / 360.0)
            lo, hi = 40.0 * (m - hw) / 360.0, 40.0 * (m + hw) / 360.0
            print("      %-18s %+7.4f %% of cs  CI95 [%+7.4f, %+7.4f]  (draw bar 0.4 %%)"
                  % (kn, eff * kv * PCS_PER_M5_US, lo * kv * PCS_PER_M5_US, hi * kv * PCS_PER_M5_US))
        print("    Upper-bound caveat (9.5): this prices a REMOVAL with an ADDITION slope measured")
        print("    on injected no-ops, and it holds the intercept fixed; #48 removed dispatches and")
        print("    scored -0.1488 %. Enough to justify building, not a certificate.")
    print()
    if c is not None and c[1] == c[1]:
        m, hw, n = c
        print("primary c: %s zero (D %+.3f, hw %.3f) -- CONFOUNDED, see 7.6: S0's 40 empties are"
              % ("EXCLUDES" if abs(m) > hw else "covers", m, hw))
        print("           concurrent roots on layer 0, so S1-S0 mixes cadence with dispatch parallelism")
        print("           (105.24 fact 2: MTL::DispatchTypeConcurrent, device.cpp:545-548).")


if __name__ == "__main__":
    main()
