#!/usr/bin/env python3
"""Is the official M5 measurement noise time-correlated?

Answers one programme-level question: would dispatching a candidate and its
baseline as two back-to-back official receipts resolve more than two receipts
taken at arbitrary times?  If the host drifts slowly, yes, and a lot.  If the
noise is white, pairing buys nothing and the resolution table in section 11.6
of `nezuko-attention-merge-epilogue.md` stands as written.

The test uses the one series in the receipt corpus that contains no candidate
signal at all.  Every official receipt times an *unmodified baseline binary*
in the same session and publishes `baseline_decode_seconds_per_token` and
`baseline_prefill_seconds_per_token`.  That binary is constant across the whole
corpus, so all of the variation in those two columns is measurement noise.

No arguments, no GPU, no network.  Reads `nezuko_receipt_corpus.csv` next to
this file, which is a projection of
`GET /api/benchmarks/<id>/submissions` keeping only the columns used here.
"""
import csv
import datetime as dt
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
CORPUS = os.path.join(HERE, "nezuko_receipt_corpus.csv")

GAP_BINS = [
    (0.0, 0.25, "<15 min"),
    (0.25, 1.0, "15-60 min"),
    (1.0, 4.0, "1-4 h"),
    (4.0, 24.0, "4-24 h"),
    (24.0, 24 * 7, "1-7 d"),
    (24 * 7, float("inf"), ">7 d"),
]


def sd(xs):
    mu = sum(xs) / len(xs)
    return mu, math.sqrt(sum((x - mu) ** 2 for x in xs) / (len(xs) - 1))


def load():
    recs = []
    with open(CORPUS, newline="") as fh:
        for row in csv.DictReader(fh):
            recs.append(
                dict(
                    t=dt.datetime.fromisoformat(
                        row["createdAt"].replace("Z", "+00:00")
                    ),
                    id=row["id8"],
                    sha=row["sha8"],
                    score=float(row["officialScore"]),
                    bd=float(row["baseline_decode_s"]),
                    bp=float(row["baseline_prefill_s"]),
                )
            )
    recs.sort(key=lambda r: r["t"])
    return recs


def variogram(recs, key, label):
    """Mean squared difference vs elapsed time between the two receipts.

    For an i.i.d. series every bin sits at 2*sigma^2, so the implied sd equals
    the marginal sd in every bin.  A rising limb would be drift.
    """
    xs = [r[key] for r in recs]
    mu, s = sd(xs)
    print(f"\n=== {label} ===")
    print(f"  marginal: mean {mu:.9g}  sd {s:.6g}  cv {100 * s / mu:.4f}%")

    acc = {name: [0, 0.0] for _, _, name in GAP_BINS}
    n = len(recs)
    for i in range(n):
        ti, xi = recs[i]["t"], recs[i][key]
        for j in range(i + 1, n):
            gap = (recs[j]["t"] - ti).total_seconds() / 3600.0
            d2 = (recs[j][key] - xi) ** 2
            for lo, hi, name in GAP_BINS:
                if lo <= gap < hi:
                    acc[name][0] += 1
                    acc[name][1] += d2
                    break
    print(f"  {'gap bin':<12} {'pairs':>8} {'implied sd':>13} {'vs marginal':>12}")
    for _, _, name in GAP_BINS:
        cnt, tot = acc[name]
        if cnt < 8:
            continue
        isd = math.sqrt(tot / (2 * cnt))
        print(f"  {name:<12} {cnt:>8} {isd:>13.6g} {100 * isd / s:>11.1f}%")

    adj = [xs[i + 1] - xs[i] for i in range(n - 1)]
    amu, asd = sd(adj)
    iid = math.sqrt(2) * s
    print(f"  adjacent-pair delta: n {len(adj)}  mean {amu:.6g}  sd {asd:.6g}")
    print(f"    i.i.d. prediction sqrt(2)*sd = {iid:.6g}   "
          f"ratio {asd / iid:.4f}  (1.00 = no drift)")
    c = [x - mu for x in xs]
    r1 = sum(c[i] * c[i + 1] for i in range(n - 1)) / sum(x * x for x in c)
    print(f"    lag-1 autocorrelation r1 = {r1:+.4f}  "
          f"(se ~ {1 / math.sqrt(n):.4f})")
    return s


def main():
    recs = load()
    n = len(recs)
    print(f"receipts with a baseline arm: {n}")
    print(f"span: {recs[0]['t']} .. {recs[-1]['t']}")

    sd_bd = variogram(recs, "bd", "baseline_decode")
    variogram(recs, "bp", "baseline_prefill")

    gaps = [(recs[i + 1]["t"] - recs[i]["t"]).total_seconds() / 60.0
            for i in range(n - 1)]
    g = sorted(gaps)
    print(f"\nadjacent submission gaps (min): p25 {g[len(g) // 4]:.1f}  "
          f"median {g[len(g) // 2]:.1f}  p75 {g[3 * len(g) // 4]:.1f}")
    print("  restricting the pairing test to genuinely back-to-back receipts:")
    for lim in (15, 30, 60):
        sel = [recs[i + 1]["bd"] - recs[i]["bd"]
               for i in range(n - 1) if gaps[i] <= lim]
        _, s2 = sd(sel)
        print(f"    <= {lim:>3} min: n {len(sel):>4}  delta sd {s2:.6g}  "
              f"= {100 * s2 / (math.sqrt(2) * sd_bd):.1f}% of i.i.d.")

    rel = [abs(recs[i + 1]["score"] - recs[i]["score"])
           / (0.5 * (recs[i + 1]["score"] + recs[i]["score"])) * 100.0
           for i in range(n - 1)]
    r = sorted(rel)
    tight = sum(1 for x in rel if x < 0.02)
    print(f"\nadjacent officialScore |delta%|: p10 {r[len(r) // 10]:.4f}  "
          f"median {r[len(r) // 2]:.4f}  p90 {r[9 * len(r) // 10]:.4f}")
    print(f"  pairs closer than 0.020%: {tight} of {len(rel)} "
          f"({100 * tight / len(rel):.2f}%) -- a tight adjacent pair is "
          f"ordinary, not evidence of drift")

    best = max(recs, key=lambda x: x["score"])
    print(f"\ncorpus best officialScore: {best['score']:.6f}  {best['id']}  "
          f"{best['t']}")


if __name__ == "__main__":
    main()
