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

Usage:  python3 research/nezuko-r117-ruler-tau.py ROWS.tsv
Env:    BW=256.7   assumed peak GB/s used to convert bytes to us at tau=1.
                   (The family's own achieved rate is 235.6 GB/s; tau scales
                   inversely, so tau_at_235.6 = tau_at_256.7 * 256.7/235.6.)
"""
import csv
import math
import os
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


def selftest(tau_true=0.75, c_true=-40.0, run_sd=7.0, blocks=7, seed=7):
    """Emit a synthetic TSV with a KNOWN tau and a KNOWN R114-style offset.

    This exists because the estimator choice is load-bearing: on this synthetic
    data the pre-registered free-intercept slope recovers tau to ~0.01, while
    the no-intercept slope reads ~0.53 for a true 0.75 and the raw per-rung
    ratios read -0.29 / 0.43 / 0.46 / 0.59, i.e. they manufacture a textbook
    'saturating, cache-absorbed' curve out of data that is exactly linear.
    A 0.2 error in tau straddles the 0.6 decision boundary, so this is not a
    stylistic preference about estimators.
    """
    import random
    random.seed(seed)
    pred = {a: DOSE_MB[a] * 1e6 / (BW * 1e9) * 1e6 for a in DOSE_MB}
    hdr = ("session\tidx\tblock\tpos\tarm\tgates\tkernels\tdecode_s_per_token\t"
           "prefill_s_per_token\tpassed\tgolden\twall_s\thead\terror")
    lines, idx = [hdr], 0
    for b in range(1, blocks + 1):
        base = 8972.0 + random.gauss(0, 8)          # block-level drift
        for a in ["C"] + list(DOSE_MB):
            idx += 1
            d = 0.0 if a == "C" else c_true + tau_true * pred[a]
            us = base + d + random.gauss(0, run_sd)
            lines.append(f"SELFTEST\t{idx}\t{b}\t1\t{a}\tg\tnone\t{us/1e6!r}\t"
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
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    path = selftest() if sys.argv[1] == "--selftest" else sys.argv[1]

    # block -> arm -> decode us/token ; also collect integrity fields
    lvl = defaultdict(dict)
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

    # ---------------- DIAGNOSTIC: per-rung raw ratios + residuals
    print("\n" + "-" * 78)
    print("DIAGNOSTIC -- per-rung means, raw ratios (offset-biased), and residuals")
    print("-" * 78)
    print(f"{'arm':<5}{'mean dus':>22}{'raw tau':>10}{'resid vs fit':>14}")
    for a in rungs:
        s = summarise(D[a], a)
        raw = s[0] / pred[a]
        fit = sc[0] + st[0] * pred[a]
        print(f"{a:<5}{s[0]:>10.2f} +/-{s[2]:>7.2f}{raw:>10.3f}{s[0]-fit:>14.2f}")
    print("  raw tau is biased by c/dbytes -- large on small rungs. Read RESIDUALS")
    print("  for linearity, not the raw column.")

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

    print("\n" + "=" * 78)


if __name__ == "__main__":
    main()
