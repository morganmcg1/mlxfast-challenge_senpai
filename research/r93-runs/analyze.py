#!/usr/bin/env python3
"""R93 receipt-channel calibration.

Arm A: sigma of the official candidate-side timings from machine-code-identical
replicates, with a chi-square CI, and the minimum resolvable decode delta at
n paired submissions.

Arm B: marginal microseconds per injected decode dispatch on the ranked M5,
regressed on the source-constant ladder, with a linearity check.

usage: analyze.py <receipts.json> <manifest.json>

manifest.json: {"nulls": ["<id>", ...], "ladder": {"<id>": K, ...},
                "tg": 8, "corpus_bound_dec_pct": 0.2924,
                "corpus_bound_pre_pct": 0.2573}
"""
import json
import math
import sys

# two-sided 95% t quantiles by degrees of freedom
T95 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365,
       8: 2.306, 9: 2.262, 10: 2.228, 11: 2.201, 12: 2.179, 14: 2.145,
       16: 2.120, 18: 2.101, 20: 2.086}
# chi-square 0.025 / 0.975 quantiles by degrees of freedom
CHI2_LO = {1: 0.00098, 2: 0.0506, 3: 0.216, 4: 0.484, 5: 0.831, 6: 1.237,
           7: 1.690, 8: 2.180, 9: 2.700, 10: 3.247}
CHI2_HI = {1: 5.024, 2: 7.378, 3: 9.348, 4: 11.143, 5: 12.833, 6: 14.449,
           7: 16.013, 8: 17.535, 9: 19.023, 10: 20.483}


def t95(df):
    return T95.get(df, 1.96 if df > 20 else T95[max(k for k in T95 if k <= df)])


def stats(xs):
    n = len(xs)
    m = sum(xs) / n
    if n < 2:
        return m, 0.0, n
    sd = math.sqrt(sum((x - m) ** 2 for x in xs) / (n - 1))
    return m, sd, n


def sigma_ci(sd, n):
    df = n - 1
    if df not in CHI2_LO:
        return None, None
    return (sd * math.sqrt(df / CHI2_HI[df]), sd * math.sqrt(df / CHI2_LO[df]))


def main():
    receipts = json.load(open(sys.argv[1]))
    man = json.load(open(sys.argv[2]))
    by = {r["id"]: r for r in receipts}

    print("=" * 78)
    print("ARM A - candidate-side channel sigma from machine-code-identical nulls")
    print("=" * 78)
    nulls = [by[i] for i in man["nulls"] if i in by]
    missing = [i for i in man["nulls"] if i not in by]
    if missing:
        print(f"MISSING from corpus: {missing}")
    for r in sorted(nulls, key=lambda r: r["ts"]):
        print(f"  {r['id']} {r['ts']} cand_dec={r['cand_dec']*1e6:9.3f}us "
              f"cand_pre={r['cand_pre']*1e6:8.4f}us "
              f"bl_dec={r['bl_dec']*1e6:9.2f} bl_pre={r['bl_pre']*1e6:8.3f} "
              f"score={r.get('score')}")
    if len(nulls) < 2:
        print("  not enough null replicates yet")
        return

    out = {}
    for axis, bound_key in (("dec", "corpus_bound_dec_pct"),
                            ("pre", "corpus_bound_pre_pct")):
        cand = [r[f"cand_{axis}"] * 1e6 for r in nulls]
        base = [r[f"bl_{axis}"] * 1e6 for r in nulls]
        m, sd, n = stats(cand)
        lo, hi = sigma_ci(sd, n)
        pct = 100 * sd / m
        bm, bsd, _ = stats(base)
        print(f"\n  {axis}: mean={m:.4f}us sd={sd:.4f}us  sigma={pct:.4f} %"
              f"   (corpus upper bound {man[bound_key]:.4f} %)")
        if lo is not None:
            print(f"       chi-square 95% CI on sigma: "
                  f"[{100*lo/m:.4f} %, {100*hi/m:.4f} %]  n={n}")
        print(f"       same-session baseline cv = {100*bsd/bm:.4f} % "
              f"(ratio baseline/candidate = {(bsd/bm)/(sd/m):.2f}x)")
        out[axis] = (m, sd, pct, hi if hi else sd)

    print("\n  Minimum resolvable |delta| (two-sided 95% t, paired arms of n each,")
    print("  so se = sigma*sqrt(2/n)); 'operative' uses the sigma CI upper end:")
    for axis in ("dec", "pre"):
        m, sd, pct, sd_hi = out[axis]
        print(f"    {axis}: (point sigma / operative sigma)")
        for n in (4, 6, 8):
            for tag, s in (("point", sd), ("oper.", sd_hi)):
                d = t95(2 * n - 2) * s * math.sqrt(2.0 / n)
                print(f"      n={n} {tag}: {100*d/m:6.4f} %  = {d:8.3f} us"
                      + (f"  (per decode step)" if axis == "dec" else
                         f"  (per prefill token)"))

    print()
    print("=" * 78)
    print("ARM B - marginal microseconds per injected decode dispatch (M5)")
    print("=" * 78)
    ladder = {i: k for i, k in man.get("ladder", {}).items() if i in by}
    lmiss = [i for i in man.get("ladder", {}) if i not in by]
    if lmiss:
        print(f"MISSING from corpus: {lmiss}")
    pts = [(0, r["cand_dec"] * 1e6, r["id"]) for r in nulls]
    for i, k in ladder.items():
        pts.append((k, by[i]["cand_dec"] * 1e6, i))
    pts.sort()
    for k, y, i in pts:
        print(f"  K={k:5d} {i} cand_dec={y:9.3f}us "
              f"cand_pre={by[i]['cand_pre']*1e6:8.4f}us")
    if not ladder:
        print("  no ladder rungs yet")
        return

    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    n = len(xs)
    mx = sum(xs) / n
    my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    icept = my - slope * mx
    resid = [y - (icept + slope * x) for x, y in zip(xs, ys)]
    df = n - 2
    s_err = math.sqrt(sum(r * r for r in resid) / df)
    se_slope = s_err / math.sqrt(sxx)
    print(f"\n  OLS over {n} points: slope = {slope:.4f} us/dispatch")
    print(f"  residual s = {s_err:.3f} us, se(slope) = {se_slope:.4f}")
    print(f"  95% CI: [{slope - t95(df)*se_slope:.4f}, "
          f"{slope + t95(df)*se_slope:.4f}] us/dispatch")
    print(f"  intercept = {icept:.3f} us (K=0 decode step)")
    print("\n  linearity - per-segment marginal cost between adjacent rungs:")
    agg = {}
    for k, y, _ in pts:
        agg.setdefault(k, []).append(y)
    ks = sorted(agg)
    for a, b in zip(ks, ks[1:]):
        ya = sum(agg[a]) / len(agg[a])
        yb = sum(agg[b]) / len(agg[b])
        print(f"    K {a:5d} -> {b:5d}: {(yb-ya)/(b-a):.4f} us/dispatch")
    print("\n  residuals vs fit (us): "
          + ", ".join(f"K={k}:{r:+.2f}" for (k, _, _), r in zip(pts, resid)))
    pre = [by[i]["cand_pre"] * 1e6 for i in ladder]
    prenull = [r["cand_pre"] * 1e6 for r in nulls]
    if pre and prenull:
        mn, sdn, _ = stats(prenull)
        ml, sdl, _ = stats(pre) if len(pre) > 1 else (sum(pre) / len(pre), 0.0, 1)
        print(f"\n  prefill internal control: null mean {mn:.4f}us, "
              f"ladder mean {ml:.4f}us, shift {100*(ml-mn)/mn:+.4f} % "
              f"(expected ~0: the arm is decode-gated)")


if __name__ == "__main__":
    main()
