#!/usr/bin/env python3
"""r100-B Part 1: session_factor = officialScore / cs over the r93 receipt corpus.

cs is the pinned-baseline candidate score model
    cs = (MB_D/cand_dec)^0.75 * (MB_P/cand_pre)^0.25
with MB_D/MB_P the pinned median baseline, so session_factor collapses to a
pure function of the session's own measured baseline. This script checks that
identity, characterises the distribution and its serial structure, and turns
it into a per-draw probability of beating the standing record.
"""
import json
import math
import statistics as st
from collections import Counter, defaultdict
from datetime import datetime

CORPUS = "research/r93-runs/receipts-latest.json"
MB_D = 0.013855009542
MB_P = 0.000372473193
RECORD = 2.61650354381456

MERIT = [
    ("current promoted frontier (2aa2f79)", 2.575633),
    ("frontier + r85-C epilogue (+0.236%)", 2.575633 * 1.002358),
    ("frontier + all three reverted wins (+0.40%)", 2.575633 * 1.0040),
    ("our best measured cs (25e1f18e)", 2.590559),
    ("best + 0.5% new merit", 2.590559 * 1.005),
]


def norm_sf(x):
    return 0.5 * math.erfc(-x / math.sqrt(2.0))


def main():
    rows = json.load(open(CORPUS))
    rows = [r for r in rows if r.get("cs") and r.get("score")]
    for r in rows:
        r["sf"] = r["score"] / r["cs"]
        r["dt"] = datetime.strptime(r["ts"], "%Y-%m-%dT%H:%M:%SZ")
    rows.sort(key=lambda r: r["dt"])
    n = len(rows)

    print(f"corpus            {CORPUS}")
    print(f"n receipts        {n}")
    print(f"window            {rows[0]['ts']} .. {rows[-1]['ts']}")

    # --- identity check: sf should equal the baseline deviation exactly ------
    worst = 0.0
    for r in rows:
        pred = (r["bl_dec"] / MB_D) ** 0.75 * (r["bl_pre"] / MB_P) ** 0.25
        worst = max(worst, abs(pred / r["sf"] - 1.0))
    print(f"\n[identity] sf == (bl_dec/MB_D)^.75*(bl_pre/MB_P)^.25 "
          f"worst rel err {worst:.3e}")

    sf = [r["sf"] for r in rows]
    pct = [100.0 * (x - 1.0) for x in sf]

    mean = st.mean(pct)
    sd = st.stdev(pct)
    med = st.median(pct)
    mad = st.median([abs(x - med) for x in pct])
    print("\n[distribution]  session_factor - 1, in percent")
    print(f"  mean {mean:+.4f}%   sd {sd:.4f}%   n {n}")
    print(f"  median {med:+.4f}%  MAD {mad:.4f}%  robust sd (1.4826*MAD) "
          f"{1.4826*mad:.4f}%")
    print(f"  min {min(pct):+.4f}%   max {max(pct):+.4f}%   "
          f"range {max(pct)-min(pct):.4f}%")
    q = sorted(pct)
    for p in (0.1, 1, 5, 25, 50, 75, 95, 99, 99.9):
        idx = min(n - 1, int(round(p / 100.0 * (n - 1))))
        print(f"  p{p:<5} {q[idx]:+.4f}%")
    m3 = sum((x - mean) ** 3 for x in pct) / n
    m4 = sum((x - mean) ** 4 for x in pct) / n
    sd_pop = math.sqrt(sum((x - mean) ** 2 for x in pct) / n)
    print(f"  skew {m3/sd_pop**3:+.3f}   excess kurtosis "
          f"{m4/sd_pop**4 - 3.0:+.3f}")

    # --- how well does the normal model describe the upper tail? ------------
    print("\n[upper tail] empirical vs normal, thresholds in sd units")
    for k in (1.0, 1.5, 2.0, 2.5, 3.0):
        thr = mean + k * sd
        emp = sum(1 for x in pct if x > thr)
        print(f"  > mean+{k:.1f}sd ({thr:+.4f}%)  empirical {emp:4d}/{n} "
              f"= {100.0*emp/n:6.3f}%   normal {100.0*(1-norm_sf(k)):6.3f}%")

    # --- serial structure ----------------------------------------------------
    def acf1(series):
        k = len(series)
        if k < 3:
            return float("nan")
        mu = st.mean(series)
        num = sum((series[i] - mu) * (series[i + 1] - mu) for i in range(k - 1))
        den = sum((x - mu) ** 2 for x in series)
        return num / den if den else float("nan")

    r1 = acf1(pct)
    print("\n[serial structure]")
    print(f"  lag-1 autocorrelation, global ts order   r1 = {r1:+.4f} "
          f"(n={n}, 2/sqrt(n) = {2/math.sqrt(n):.4f})")
    for lag in (2, 5, 10, 25, 50):
        mu = st.mean(pct)
        num = sum((pct[i] - mu) * (pct[i + lag] - mu) for i in range(n - lag))
        den = sum((x - mu) ** 2 for x in pct)
        print(f"  lag-{lag:<3} autocorrelation                    "
              f"r{lag} = {num/den:+.4f}")

    # a "session" proxy: receipts closer together than a gap threshold
    for gap_min in (10, 30, 60):
        blocks, cur = [], [rows[0]]
        for a, b in zip(rows, rows[1:]):
            if (b["dt"] - a["dt"]).total_seconds() > gap_min * 60:
                blocks.append(cur)
                cur = []
            cur.append(b)
        blocks.append(cur)
        big = [b for b in blocks if len(b) >= 3]
        within, between = [], []
        for b in big:
            v = [100.0 * (x["sf"] - 1.0) for x in b]
            within.append(st.stdev(v))
            between.append(st.mean(v))
        if len(big) >= 3:
            print(f"  gap<{gap_min:>2}min blocks: {len(blocks)} total, "
                  f"{len(big)} with n>=3; mean within-block sd "
                  f"{st.mean(within):.4f}%, between-block sd "
                  f"{st.stdev(between):.4f}%")

    # per-solver consecutive pairs (a solver's own back-to-back submissions)
    bysolver = defaultdict(list)
    for r in rows:
        bysolver[r["solver"]].append(r)
    nums, dens, pairs = 0.0, 0.0, 0
    mu = st.mean(pct)
    for s, rs in bysolver.items():
        if len(rs) < 3:
            continue
        v = [100.0 * (x["sf"] - 1.0) for x in rs]
        for a, b in zip(v, v[1:]):
            nums += (a - mu) * (b - mu)
            pairs += 1
        dens += sum((x - mu) ** 2 for x in v)
    print(f"  within-solver consecutive-pair r1 = {nums/dens:+.4f} "
          f"({pairs} pairs)")

    # --- time-of-day / day breakdown ----------------------------------------
    print("\n[time of day, UTC hour]")
    byhour = defaultdict(list)
    for r, p in zip(rows, pct):
        byhour[r["dt"].hour].append(p)
    for h in sorted(byhour):
        v = byhour[h]
        s = st.stdev(v) if len(v) > 1 else float("nan")
        print(f"  {h:02d}h  n={len(v):4d}  mean {st.mean(v):+.4f}%  "
              f"sd {s:.4f}%  max {max(v):+.4f}%")
    print("\n[by date, UTC]")
    byday = defaultdict(list)
    for r, p in zip(rows, pct):
        byday[r["dt"].date().isoformat()].append(p)
    for d in sorted(byday):
        v = byday[d]
        s = st.stdev(v) if len(v) > 1 else float("nan")
        print(f"  {d}  n={len(v):4d}  mean {st.mean(v):+.4f}%  "
              f"sd {s:.4f}%  min {min(v):+.4f}%  max {max(v):+.4f}%")

    # --- probability of beating the record ----------------------------------
    print(f"\n[per-draw P(officialScore > record={RECORD:.8f})]")
    print("  merit cs                                     needed sf   "
          "z      normal      empirical(n/N)")
    sf_sorted = sorted(sf)
    for label, cs in MERIT:
        need = RECORD / cs
        need_pct = 100.0 * (need - 1.0)
        z = (need_pct - mean) / sd
        pn = 1.0 - norm_sf(z)
        emp = sum(1 for x in sf if x > need)
        print(f"  {label:<44} {need:.6f}  {z:+6.3f}  {100*pn:9.5f}%  "
              f"{100.0*emp/n:8.4f}% ({emp}/{n})")
    print(f"\n  observed max sf in corpus = {max(sf):.6f}; the cs needed to "
          f"beat the record at that draw = {RECORD/max(sf):.6f}")

    # --- what does the record itself imply? ---------------------------------
    rec = [r for r in rows if abs(r["score"] - RECORD) < 1e-9]
    if rec:
        r = rec[0]
        print(f"\n[record receipt] id={r['id']} solver={r['solver']} "
              f"ts={r['ts']} cs={r['cs']:.6f} sf={100*(r['sf']-1):+.4f}% "
              f"(z = {(100*(r['sf']-1)-mean)/sd:+.3f})")

    # --- is session_factor independent of candidate merit? ------------------
    cs_v = [r["cs"] for r in rows]
    mcs, msf = st.mean(cs_v), st.mean(pct)
    cov = sum((a - mcs) * (b - msf) for a, b in zip(cs_v, pct))
    den = math.sqrt(sum((a - mcs) ** 2 for a in cs_v)
                    * sum((b - msf) ** 2 for b in pct))
    print(f"\n[independence] corr(cs, session_factor) = {cov/den:+.4f}")
    top = sorted(rows, key=lambda r: -r["cs"])[:100]
    tv = [100.0 * (r["sf"] - 1.0) for r in top]
    print(f"  top-100 cs receipts: mean sf {st.mean(tv):+.4f}% "
          f"sd {st.stdev(tv):.4f}% (full corpus {mean:+.4f}% / {sd:.4f}%)")

    # --- cumulative probability over a receipt budget ------------------------
    print("\n[cumulative P(at least one record-beating receipt) - empirical]")
    print("  merit cs                                       k=1     k=2     "
          "k=3     k=5     k=10    k=20    E[draws]")
    for label, cs in MERIT:
        need = RECORD / cs
        p = sum(1 for x in sf if x > need) / n
        cells = "  ".join(f"{100*(1-(1-p)**k):6.2f}%" for k in (1, 2, 3, 5, 10, 20))
        exp = f"{1/p:8.1f}" if p > 0 else "     inf"
        print(f"  {label:<44} {cells} {exp}")

    # --- inverse: merit required for a target per-draw probability ----------
    print("\n[inverse] empirical merit cs required for a target per-draw P")
    for target in (0.01, 0.02, 0.05, 0.10, 0.25, 0.50):
        idx = int(math.floor((1.0 - target) * n))
        idx = min(max(idx, 0), n - 1)
        need_sf = sf_sorted[idx]
        cs_req = RECORD / need_sf
        gain = 100.0 * (cs_req / 2.575633 - 1.0)
        print(f"  P={100*target:5.1f}%  needs sf >= {need_sf:.6f}  "
              f"=> cs >= {cs_req:.6f}  ({gain:+.3f}% over the 2aa2f79 "
              f"frontier)")

    # --- accepted-vs-rejected sanity ----------------------------------------
    print("\n[status] session_factor does not differ by acceptance "
          "(it is a baseline property)")
    for stat in ("accepted", "rejected"):
        v = [100.0 * (r["sf"] - 1.0) for r in rows if r["status"] == stat]
        print(f"  {stat:<9} n={len(v):4d} mean {st.mean(v):+.4f}% "
              f"sd {st.stdev(v):.4f}%")

    # --- decode vs prefill share of the session factor ----------------------
    d = [100.0 * ((r["bl_dec"] / MB_D) ** 0.75 - 1.0) for r in rows]
    p_ = [100.0 * ((r["bl_pre"] / MB_P) ** 0.25 - 1.0) for r in rows]
    print("\n[decomposition] which baseline axis drives the session factor?")
    print(f"  0.75-weighted decode term  mean {st.mean(d):+.4f}% "
          f"sd {st.stdev(d):.4f}%")
    print(f"  0.25-weighted prefill term mean {st.mean(p_):+.4f}% "
          f"sd {st.stdev(p_):.4f}%")
    md, mp = st.mean(d), st.mean(p_)
    cov2 = sum((a - md) * (b - mp) for a, b in zip(d, p_))
    den2 = math.sqrt(sum((a - md) ** 2 for a in d)
                     * sum((b - mp) ** 2 for b in p_))
    print(f"  corr(decode term, prefill term) = {cov2/den2:+.4f}")


if __name__ == "__main__":
    main()
