#!/usr/bin/env python3
"""R106-H Stage A: variance decomposition of the official channel.

The ranked score is  score = (bl_dec/dec)^0.75 * (bl_pre/pre)^0.25, verified
exactly against `decode_speedup`/`prefill_speedup` on all 1218 metric-bearing
receipts.  Writing cs for the common-baseline score with pinned constants,

    ln score = ln cs + ln L
    ln L     = 0.75*ln(bl_dec/MB_D) + 0.25*ln(bl_pre/MB_P)

The candidate program differs on nearly every receipt, but the BASELINE program
is identical on all 1218.  So `ln L` is an n=1218 exact replication of a fixed
program on the ranked host: session structure, drift and tail shape are all
directly estimable there, at dof 1217 instead of dof 10.

Read-only.  No network, no benchmark, no submission.
"""
import json
import math
import statistics as st
import sys
from collections import defaultdict

MB_D = 0.013855009542
MB_P = 0.000372473193
RECORD = 2.61650354381456
US_PER_PCT_CS = 65.67  # 1 % of cs == 65.67 us/step of decode

CORPUS = "/tmp/r106b/receipt-corpus-frozen.json"
VERIFIED = "research/artifacts/maple-nezuko-r106b/replicate-identity-verified.json"
OUT = "research/artifacts/maple-nezuko-r106h/stage-a.json"

# ---------------------------------------------------------------- statistics
CHI2 = {  # exact two-sided 2.5 % / 97.5 % points, for the small-dof pools
    1: (0.000982, 5.02389), 2: (0.0506356, 7.37776), 3: (0.215795, 9.34840),
    4: (0.484419, 11.1433), 5: (0.831212, 12.8325), 6: (1.237344, 14.4494),
    7: (1.689869, 16.0128), 8: (2.179731, 17.5345), 9: (2.700390, 19.0228),
    10: (3.246973, 20.4832), 11: (3.815748, 21.9200), 12: (4.403789, 23.3367),
    14: (5.628726, 26.1189), 17: (7.564186, 30.1910), 19: (8.906516, 32.8523),
    22: (10.98232, 36.7807),
}
T95 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365,
       8: 2.306, 9: 2.262, 10: 2.228, 11: 2.201, 12: 2.179, 13: 2.160,
       14: 2.145, 15: 2.131, 16: 2.120, 17: 2.110, 18: 2.101, 19: 2.093,
       20: 2.086, 25: 2.060, 30: 2.042, 40: 2.021, 60: 2.000, 120: 1.980}


def t975(df):
    if df in T95:
        return T95[df]
    if df <= 0:
        return float("nan")
    ks = sorted(T95)
    if df > ks[-1]:
        return 1.960 + 2.0 / df
    lo = max(k for k in ks if k < df)
    hi = min(k for k in ks if k > df)
    w = (df - lo) / (hi - lo)
    return T95[lo] * (1 - w) + T95[hi] * w


def chi2_ci(df):
    """(lower, upper) chi-square points; Wilson-Hilferty above the table."""
    if df in CHI2:
        return CHI2[df]
    for z, side in ((-1.959964, 0), (1.959964, 1)):
        pass
    out = []
    for z in (-1.959964, 1.959964):
        out.append(df * (1 - 2.0 / (9 * df) + z * math.sqrt(2.0 / (9 * df))) ** 3)
    return (out[0], out[1])


def sd_ci(sd, df):
    """95 % CI for a population sd from a chi-square sd estimate."""
    lo, hi = chi2_ci(df)
    return (sd * math.sqrt(df / hi), sd * math.sqrt(df / lo))


def rel_se_of_sd(n):
    return 1.0 / math.sqrt(2.0 * (n - 1)) if n > 1 else float("nan")


def norm_sf(z):
    return 0.5 * math.erfc(z / math.sqrt(2.0))


def mad_sd(xs):
    m = st.median(xs)
    return 1.4826 * st.median([abs(x - m) for x in xs])


def ols(xs, ys):
    n = len(xs)
    mx, my = st.mean(xs), st.mean(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    b = sxy / sxx
    a = my - b * mx
    resid = [y - (a + b * x) for x, y in zip(xs, ys)]
    return a, b, resid, sxx, n


def ols_ci(xs, ys, extra_params=0):
    a, b, resid, sxx, n = ols(xs, ys)
    df = n - 2 - extra_params
    s2 = sum(r * r for r in resid) / df
    se = math.sqrt(s2 / sxx)
    h = t975(df) * se
    return b, (b - h, b + h), se, df, math.sqrt(s2)


def moments(xs):
    n = len(xs)
    m = st.mean(xs)
    s = st.stdev(xs)
    m3 = sum((x - m) ** 3 for x in xs) / n
    m4 = sum((x - m) ** 4 for x in xs) / n
    sp = math.sqrt(sum((x - m) ** 2 for x in xs) / n)
    return m, s, m3 / sp ** 3, m4 / sp ** 4 - 3.0


def ts(s):
    """ISO8601 -> seconds since epoch, without dateutil."""
    d, t = s.split("T")
    y, mo, da = (int(v) for v in d.split("-"))
    t = t.rstrip("Z")
    hh, mm, rest = t.split(":")
    sec = float(rest)
    days = 0
    for yy in range(1970, y):
        days += 366 if (yy % 4 == 0 and (yy % 100 != 0 or yy % 400 == 0)) else 365
    ml = [31, 29 if (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)) else 28,
          31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    days += sum(ml[:mo - 1]) + da - 1
    return days * 86400 + int(hh) * 3600 + int(mm) * 60 + sec


# ------------------------------------------------------------------- load
def load():
    corpus = json.load(open(CORPUS))
    rows = []
    for s in corpus["submissions"]:
        m = s.get("officialMetrics")
        if not m:
            continue
        bd = m.get("baseline_decode_seconds_per_token")
        bp = m.get("baseline_prefill_seconds_per_token")
        dc = m.get("decode_seconds_per_token")
        pf = m.get("prefill_seconds_per_token")
        if not (bd and bp and dc and pf):
            continue
        cs = (MB_D / dc) ** 0.75 * (MB_P / pf) ** 0.25
        lnL = 0.75 * math.log(bd / MB_D) + 0.25 * math.log(bp / MB_P)
        rows.append({
            "id": s["id"], "sha": s.get("submissionCommitSha"),
            "createdAt": s["createdAt"], "t": ts(s["createdAt"]),
            "status": s.get("status"), "user": s.get("solverUsername"),
            "bl_dec": bd, "bl_pre": bp, "dec": dc, "pre": pf,
            "cs": cs, "lnL": lnL, "score": cs * math.exp(lnL),
            "ln_bl_dec": math.log(bd), "ln_bl_pre": math.log(bp),
            "ln_dec": math.log(dc), "ln_pre": math.log(pf),
            "reported": m.get("decode_speedup") ** 0.75 * m.get("prefill_speedup") ** 0.25,
            "peak_ram": m.get("peak_ram_gb"),
        })
    rows.sort(key=lambda r: r["t"])
    return rows


def main():
    rows = load()
    n = len(rows)
    res = {"n_receipts_with_metrics": n,
           "corpus_sha256": "d450b5b5dc895f0d2d4de52d790035e88ea2e55255fed1ae04c80a9a7c70c12b"}

    # sanity: cs*L must equal the reported score
    err = max(abs(r["score"] - r["reported"]) / r["reported"] for r in rows)
    res["max_rel_err_cs_times_L_vs_reported_score"] = err
    print(f"receipts with usable metrics: {n}")
    print(f"identity check  max |cs*L - reported score| / score = {err:.3e}")

    # ---------------------------------------------------------------- A1
    print("\n=== A1  the baseline lottery: sd of a FIXED program, n=%d ===" % n)
    a1 = {}
    for key, label, pin in (("ln_bl_dec", "ln bl_dec", MB_D),
                            ("ln_bl_pre", "ln bl_pre", MB_P),
                            ("lnL", "ln L (score-weighted)", None)):
        xs = [r[key] for r in rows]
        if pin is not None:
            xs = [x - math.log(pin) for x in xs]
        m, s, skew, kurt = moments(xs)
        lo, hi = sd_ci(s, n - 1)
        rs = mad_sd(xs)
        a1[key] = {"mean_pct": 100 * m, "sd_pct": 100 * s,
                   "sd_ci_pct": [100 * lo, 100 * hi], "mad_sd_pct": 100 * rs,
                   "skew": skew, "excess_kurtosis": kurt, "n": len(xs),
                   "median_pct": 100 * st.median(xs),
                   "min_pct": 100 * min(xs), "max_pct": 100 * max(xs)}
        print(f"  {label:24s} mean {100*m:+.4f} %  median {100*st.median(xs):+.4f} %  "
              f"sd {100*s:.4f} % CI [{100*lo:.4f}, {100*hi:.4f}]  "
              f"madSD {100*rs:.4f} %  skew {skew:+.3f}  exkurt {kurt:+.3f}")
    print(f"  relative SE of these sd estimates: {100*rel_se_of_sd(n):.2f} %  (dof {n-1})")
    r_dp = st.correlation([r["ln_bl_dec"] for r in rows],
                          [r["ln_bl_pre"] for r in rows])
    a1["corr_ln_bl_dec_ln_bl_pre"] = r_dp
    print(f"  corr(ln bl_dec, ln bl_pre) = {r_dp:+.4f}")
    res["A1"] = a1

    # ---------------------------------------------------------------- A5 drift
    print("\n=== A5  drift of the fixed baseline over the campaign ===")
    t0 = rows[0]["t"]
    day = [(r["t"] - t0) / 86400.0 for r in rows]
    a5 = {}
    for key, pin, unit in (("ln_bl_dec", MB_D, "us/step"),
                           ("ln_bl_pre", MB_P, "us/token"),
                           ("lnL", None, "score")):
        ys = [r[key] for r in rows]
        b, ci, se, df, sresid = ols_ci(day, ys)
        scale = 1e6 * (pin if pin else 1.0)
        a5[key] = {"slope_pct_per_day": 100 * b,
                   "slope_ci_pct_per_day": [100 * ci[0], 100 * ci[1]],
                   "dof": df, "resid_sd_pct": 100 * sresid,
                   "span_days": day[-1]}
        extra = ""
        if pin:
            extra = f"  = {b*scale:+.3f} {unit}/day"
        print(f"  {key:12s} slope {100*b:+.5f} %/day  CI [{100*ci[0]:+.5f}, "
              f"{100*ci[1]:+.5f}]  dof {df}{extra}")
        print(f"               residual sd after detrending: {100*sresid:.4f} %")
    a5["span_days"] = day[-1]
    a5["first"] = rows[0]["createdAt"]
    a5["last"] = rows[-1]["createdAt"]
    print(f"  campaign span {day[-1]:.2f} days  {rows[0]['createdAt']} .. {rows[-1]['createdAt']}")
    res["A5"] = a5

    # per-day medians, to see regimes rather than assume a line
    bydayv = defaultdict(list)
    for r in rows:
        bydayv[r["createdAt"][:10]].append(100 * (r["ln_bl_dec"] - math.log(MB_D)))
    res["A5_day_medians_pct"] = {k: {"n": len(v), "median": st.median(v),
                                     "sd": (st.stdev(v) if len(v) > 1 else None)}
                                 for k, v in sorted(bydayv.items())}
    print("  per-UTC-day ln(bl_dec/MB_D):")
    for k, v in sorted(bydayv.items()):
        s = st.stdev(v) if len(v) > 1 else float('nan')
        print(f"    {k}  n={len(v):4d}  median {st.median(v):+.4f} %  sd {s:.4f} %")

    # ---------------------------------------------------------------- A2
    print("\n=== A2  session structure: semivariogram of the FIXED baseline ===")
    # residual after removing the fitted linear drift, so the variogram measures
    # session clustering and not the trend already priced in A5.
    _, bdrift, resid_bd, _, _ = ols(day, [r["ln_bl_dec"] for r in rows])
    xs = [100 * v for v in resid_bd]
    var_tot = st.variance(xs)
    edges = [(0, 1 / 6), (1 / 6, 0.5), (0.5, 1), (1, 2), (2, 4), (4, 8),
             (8, 24), (24, 48), (48, 96), (96, 192), (192, 1e9)]
    bins = []
    acc = {e: [0, 0.0] for e in edges}
    for i in range(len(rows)):
        for j in range(i + 1, len(rows)):
            lag = abs(rows[j]["t"] - rows[i]["t"]) / 3600.0
            d2 = (xs[j] - xs[i]) ** 2
            for e in edges:
                if e[0] <= lag < e[1]:
                    acc[e][0] += 1
                    acc[e][1] += d2
                    break
    print(f"  total detrended variance of ln bl_dec: {var_tot:.6f} (%^2), "
          f"sd {math.sqrt(var_tot):.4f} %")
    print(f"  {'lag (h)':>16s} {'pairs':>8s} {'semivar':>10s} {'/total':>8s} "
          f"{'rho(h)':>8s} {'95% CI on rho':>20s}")
    for e in edges:
        cnt, s2 = acc[e]
        if cnt == 0:
            continue
        gam = s2 / (2 * cnt)
        rho = 1 - gam / var_tot
        # CI on gamma from chi-square with an effective dof; pairs are not
        # independent, so use the conservative count of distinct receipts
        # involved rather than the pair count.
        eff = max(2, int(math.sqrt(2 * cnt)))
        glo, ghi = sd_ci(math.sqrt(gam), eff - 1)
        rlo, rhi = 1 - ghi ** 2 / var_tot, 1 - glo ** 2 / var_tot
        lbl = f"{e[0]:g}-{e[1]:g}" if e[1] < 1e8 else f">{e[0]:g}"
        print(f"  {lbl:>16s} {cnt:>8d} {gam:>10.5f} {gam/var_tot:>8.3f} "
              f"{rho:>+8.3f}   [{rlo:+.3f}, {rhi:+.3f}]")
        bins.append({"lag_lo_h": e[0], "lag_hi_h": e[1], "pairs": cnt,
                     "semivariance_pct2": gam, "ratio_to_total": gam / var_tot,
                     "rho": rho, "rho_ci": [rlo, rhi], "eff_dof": eff - 1})
    res["A2"] = {"detrended_total_variance_pct2": var_tot,
                 "detrended_sd_pct": math.sqrt(var_tot), "bins": bins}

    # A2b: gap-clustered sessions and UTC-day ANOVA
    print("\n  --- A2b variance components of the FIXED baseline ---")
    a2b = {}
    for gap_min, name in ((60, "gap>60min"), (180, "gap>180min"), (None, "UTC day")):
        groups = defaultdict(list)
        if gap_min is None:
            for r, x in zip(rows, xs):
                groups[r["createdAt"][:10]].append(x)
        else:
            gid = 0
            prev = None
            for r, x in zip(rows, xs):
                if prev is not None and (r["t"] - prev) > gap_min * 60:
                    gid += 1
                groups[gid].append(x)
                prev = r["t"]
        gs = [v for v in groups.values() if len(v) >= 2]
        k = len(gs)
        nn = sum(len(v) for v in gs)
        if k < 2 or nn - k < 2:
            continue
        within = math.sqrt(sum((len(v) - 1) * st.variance(v) for v in gs) / (nn - k))
        gm = [st.mean(v) for v in gs]
        # unbiased between-group variance component, unequal group sizes
        grand = sum(len(v) * st.mean(v) for v in gs) / nn
        ssb = sum(len(v) * (st.mean(v) - grand) ** 2 for v in gs)
        msb = ssb / (k - 1)
        n0 = (nn - sum(len(v) ** 2 for v in gs) / nn) / (k - 1)
        varb = max(0.0, (msb - within ** 2) / n0)
        icc = varb / (varb + within ** 2)
        f = msb / within ** 2
        a2b[name] = {"groups": k, "n": nn, "within_sd_pct": within,
                     "between_sd_pct": math.sqrt(varb), "icc": icc,
                     "F": f, "df1": k - 1, "df2": nn - k,
                     "within_sd_ci_pct": list(sd_ci(within, nn - k)),
                     "sd_of_group_means_pct": st.stdev(gm)}
        print(f"  {name:12s} k={k:4d} n={nn:5d}  within sd {within:.4f} % "
              f"CI [{sd_ci(within, nn-k)[0]:.4f}, {sd_ci(within, nn-k)[1]:.4f}]  "
              f"between sd {math.sqrt(varb):.4f} %  ICC {icc:+.4f}  "
              f"F({k-1},{nn-k}) = {f:.3f}")
    res["A2b"] = a2b

    # ---------------------------------------------------------------- A3
    print("\n=== A3  common-mode test: is session noise shared by baseline "
          "and candidate? ===")
    a3 = {}
    ver = json.load(open(VERIFIED))
    by_sha = {}
    for r in rows:
        if r["sha"]:
            by_sha[r["sha"]] = r
            by_sha[r["sha"][:12]] = r
    gsets = []
    for g in ver.get("groups", []):
        if not g.get("verified_inert_only"):
            continue
        mem = []
        for rc in g.get("receipts", []):
            r = by_sha.get(rc.get("sha12"))
            if r:
                mem.append(r)
        if len(mem) >= 2:
            gsets.append((g.get("group"), mem))
    print(f"  verified replicate groups usable: {len(gsets)}  "
          f"receipts {sum(len(m) for m in (g[1] for g in gsets))}")
    dx, dy, dl = [], [], []
    for key, mem in gsets:
        mb = st.mean([r["ln_bl_dec"] for r in mem])
        md = st.mean([r["ln_dec"] for r in mem])
        for r in mem:
            dx.append(r["ln_bl_dec"] - mb)
            dy.append(r["ln_dec"] - md)
        print(f"    {key}  n={len(mem)}")
    if len(dx) >= 4:
        kfe = len(gsets)
        b, ci, se, df, sr = ols_ci(dx, dy, extra_params=kfe - 1)
        a3["within_group"] = {"beta": b, "ci": list(ci), "se": se, "dof": df,
                              "n": len(dx), "groups": kfe,
                              "resid_sd_ln_dec_pct": 100 * sr}
        print(f"  WITHIN verified replicate groups (fixed candidate code):")
        print(f"    beta = {b:+.4f}  95% CI [{ci[0]:+.4f}, {ci[1]:+.4f}]  "
              f"dof {df}   (beta=+1 => pure common-mode, beta=0 => independent)")
        print(f"    residual sd of ln dec after the bl_dec regressor: {100*sr:.4f} %")
        # variance of ln dec within groups with and without the regressor
        s_raw = st.stdev(dy) * math.sqrt((len(dy) - 1) / max(1, len(dy) - kfe))
        a3["within_group"]["raw_sd_ln_dec_pct"] = 100 * s_raw
        print(f"    raw within-group sd of ln dec (no regressor):        "
              f"{100*s_raw:.4f} %")

    # higher-powered variant: all receipts, UTC-day fixed effects
    byday = defaultdict(list)
    for r in rows:
        byday[r["createdAt"][:10]].append(r)
    ax, ay = [], []
    for k, v in byday.items():
        if len(v) < 3:
            continue
        mb = st.mean([r["ln_bl_dec"] for r in v])
        md = st.mean([r["ln_dec"] for r in v])
        for r in v:
            ax.append(r["ln_bl_dec"] - mb)
            ay.append(r["ln_dec"] - md)
    b, ci, se, df, sr = ols_ci(ax, ay, extra_params=len(byday) - 1)
    a3["all_receipts_day_fe"] = {"beta": b, "ci": list(ci), "se": se,
                                  "dof": df, "n": len(ax),
                                  "note": "candidate merit varies within day; "
                                          "unbiased only if merit is "
                                          "uncorrelated with bl_dec"}
    print(f"  ALL receipts, UTC-day fixed effects (merit varies -> noisy y):")
    print(f"    beta = {b:+.4f}  95% CI [{ci[0]:+.4f}, {ci[1]:+.4f}]  "
          f"dof {df}  n {len(ax)}")
    res["A3"] = a3

    # ---------------------------------------------------------------- A4 tail
    print("\n=== A4  tail shape of the baseline lottery (n=%d) ===" % n)
    # standardize the detrended, day-demeaned residual of ln L
    _, _, rl, _, _ = ols(day, [r["lnL"] for r in rows])
    bydayL = defaultdict(list)
    for r, v in zip(rows, rl):
        bydayL[r["createdAt"][:10]].append(v)
    dm = {k: st.mean(v) for k, v in bydayL.items()}
    zsd = st.stdev(rl)
    z_raw = [v / zsd for v in rl]
    zd = [(v - dm[r["createdAt"][:10]]) for r, v in zip(rows, rl)]
    zd = [v / st.stdev(zd) for v in zd]
    a4 = {}
    for label, zs in (("detrended", z_raw), ("detrended+day-demeaned", zd)):
        m, s, skew, kurt = moments(zs)
        rowsx = []
        print(f"  {label}: skew {skew:+.3f}  excess kurtosis {kurt:+.3f}  "
              f"max z {max(zs):+.3f}  min z {min(zs):+.3f}")
        print(f"    {'thr':>5s} {'obs>+t':>7s} {'exp>+t':>8s} {'obs<-t':>7s} "
              f"{'exp<-t':>8s}")
        for thr in (1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.43):
            up = sum(1 for v in zs if v > thr)
            dn = sum(1 for v in zs if v < -thr)
            exp = n * norm_sf(thr)
            print(f"    {thr:>5.2f} {up:>7d} {exp:>8.2f} {dn:>7d} {exp:>8.2f}")
            rowsx.append({"thr": thr, "obs_upper": up, "obs_lower": dn,
                          "expected_gaussian": exp})
        # exponential upper-tail fit above u
        for u in (1.25, 1.5, 2.0):
            ex = [v - u for v in zs if v > u]
            if len(ex) >= 8:
                beta = st.mean(ex)
                pu = len(ex) / n
                p303 = pu * math.exp(-(3.03 - u) / beta) if 3.03 > u else None
                p400 = pu * math.exp(-(4.00 - u) / beta) if 4.00 > u else None
                a4.setdefault("exp_tail_fits", []).append(
                    {"label": label, "u": u, "n_exceed": len(ex),
                     "beta": beta, "p_u": pu, "p_z_gt_3.03": p303,
                     "p_z_gt_4.00": p400,
                     "gauss_p_3.03": norm_sf(3.03),
                     "gauss_p_4.00": norm_sf(4.00)})
                print(f"    exponential tail above u={u}: n={len(ex)} "
                      f"beta={beta:.3f}  P(z>3.03)={p303:.3e} "
                      f"(Gaussian {norm_sf(3.03):.3e})  "
                      f"P(z>4.00)={p400:.3e} (Gaussian {norm_sf(4.00):.3e})")
        a4[label] = {"skew": skew, "excess_kurtosis": kurt, "max_z": max(zs),
                     "min_z": min(zs), "exceedances": rowsx}
    a4["empirical_resolution_floor_p"] = 1.0 / n
    a4["lnL_empirical_quantiles_pct"] = {
        str(q): 100 * sorted(r["lnL"] for r in rows)[
            min(n - 1, max(0, int(round(q * (n - 1)))))]
        for q in (0.001, 0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99, 0.999, 1.0)}
    res["A4"] = a4

    # ---------------------------------------------------------------- gap fix
    print("\n=== gap to the record, with and without the L correction ===")
    best_cs = 2.590559
    gap_L1 = math.log(RECORD / best_cs)
    medL = st.median([r["lnL"] for r in rows])
    meanL = st.mean([r["lnL"] for r in rows])
    res["gap"] = {"record_score": RECORD, "best_cs": best_cs,
                  "gap_pct_L_eq_1": 100 * gap_L1,
                  "median_lnL_pct": 100 * medL, "mean_lnL_pct": 100 * meanL,
                  "gap_pct_at_median_L": 100 * (gap_L1 - medL),
                  "gap_us_per_step_at_median_L": 100 * (gap_L1 - medL) * US_PER_PCT_CS}
    print(f"  advisor's stated gap (implicitly L=1): {100*gap_L1:+.4f} % of cs")
    print(f"  median ln L = {100*medL:+.4f} %   mean ln L = {100*meanL:+.4f} %")
    print(f"  honest gap at the median draw of L: {100*(gap_L1-medL):+.4f} % "
          f"= {100*(gap_L1-medL)*US_PER_PCT_CS:+.2f} us/step of decode")

    # our own receipts, attributed by sha only
    print("\n=== our merit anchors (attribution by submissionCommitSha only) ===")
    anchors = ["4b0e051b", "ef055b9b", "5a43d329", "e1b6e2be", "bd33883e",
               "e33efe4e", "cc6ddc12"]
    res["anchors"] = {}
    for a in anchors:
        hit = [r for r in rows if r["sha"] and r["sha"].startswith(a)]
        if not hit:
            res["anchors"][a] = {"attribution": "uncertain: sha not in corpus"}
            print(f"  {a}  ATTRIBUTION UNCERTAIN (sha absent from corpus)")
            continue
        if len(hit) > 1:
            res["anchors"][a] = {"attribution": f"uncertain: {len(hit)} receipts"}
            print(f"  {a}  ATTRIBUTION UNCERTAIN ({len(hit)} receipts share prefix)")
            continue
        r = hit[0]
        res["anchors"][a] = {"cs": r["cs"], "lnL_pct": 100 * r["lnL"],
                             "score": r["score"], "createdAt": r["createdAt"],
                             "dec_us": 1e6 * r["dec"], "status": r["status"]}
        print(f"  {a}  cs {r['cs']:.6f}  lnL {100*r['lnL']:+.4f} %  "
              f"score {r['score']:.6f}  {r['createdAt']}  {r['status']}")

    extended(rows, gsets, res, day, xs)

    import os
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(res, open(OUT, "w"), indent=1, sort_keys=True)
    print(f"\nwrote {OUT}")


def variogram(rows, vals, label):
    """Semivariogram of `vals` against time lag; flat == i.i.d. draws."""
    var_tot = st.variance(vals)
    edges = [(0, 1 / 6), (1 / 6, 0.5), (0.5, 1), (1, 2), (2, 4), (4, 8),
             (8, 24), (24, 48), (48, 96), (96, 192), (192, 1e9)]
    acc = {e: [0, 0.0] for e in edges}
    for i in range(len(rows)):
        ti, vi = rows[i]["t"], vals[i]
        for j in range(i + 1, len(rows)):
            lag = abs(rows[j]["t"] - ti) / 3600.0
            d2 = (vals[j] - vi) ** 2
            for e in edges:
                if e[0] <= lag < e[1]:
                    acc[e][0] += 1
                    acc[e][1] += d2
                    break
    out = []
    print(f"  {label}: total variance {var_tot:.6f} (%^2)  sd {math.sqrt(var_tot):.4f} %")
    print(f"  {'lag (h)':>16s} {'pairs':>8s} {'/total':>8s} {'rho(h)':>8s}")
    for e in edges:
        cnt, s2 = acc[e]
        if not cnt:
            continue
        gam = s2 / (2 * cnt)
        lbl = f"{e[0]:g}-{e[1]:g}" if e[1] < 1e8 else f">{e[0]:g}"
        print(f"  {lbl:>16s} {cnt:>8d} {gam/var_tot:>8.3f} {1-gam/var_tot:>+8.3f}")
        out.append({"lag_lo_h": e[0], "lag_hi_h": e[1], "pairs": cnt,
                    "ratio_to_total": gam / var_tot, "rho": 1 - gam / var_tot})
    return {"total_variance_pct2": var_tot, "sd_pct": math.sqrt(var_tot),
            "bins": out}


def components(rows, vals, gap_min):
    """(within sd, between sd, icc, F, k, n) for gap-clustered sessions."""
    groups = defaultdict(list)
    gid, prev = 0, None
    for r, x in zip(rows, vals):
        if prev is not None and (r["t"] - prev) > gap_min * 60:
            gid += 1
        groups[gid].append(x)
        prev = r["t"]
    gs = [v for v in groups.values() if len(v) >= 2]
    k = len(gs)
    nn = sum(len(v) for v in gs)
    if k < 2 or nn - k < 2:
        return None
    within = math.sqrt(sum((len(v) - 1) * st.variance(v) for v in gs) / (nn - k))
    grand = sum(len(v) * st.mean(v) for v in gs) / nn
    msb = sum(len(v) * (st.mean(v) - grand) ** 2 for v in gs) / (k - 1)
    n0 = (nn - sum(len(v) ** 2 for v in gs) / nn) / (k - 1)
    varb = max(0.0, (msb - within ** 2) / n0)
    return {"k": k, "n": nn, "within_sd_pct": within,
            "within_sd_ci_pct": list(sd_ci(within, nn - k)),
            "between_sd_pct": math.sqrt(varb),
            "icc": varb / (varb + within ** 2), "F": msb / within ** 2,
            "df1": k - 1, "df2": nn - k}


def extended(rows, gsets, res, day, bd_resid):
    n = len(rows)

    # ------------------------------------------------------------ A1c
    print("\n=== A1c  candidate-axis sigma from the verified replicate groups "
          "(dof 10) ===")
    a1c = {}
    for key, label in (("ln_dec", "ln dec"), ("ln_pre", "ln pre"),
                       ("lnL", "ln L (baseline, same receipts)")):
        pooled, df = 0.0, 0
        for _, mem in gsets:
            v = [100 * r[key] for r in mem]
            pooled += (len(v) - 1) * st.variance(v)
            df += len(v) - 1
        s = math.sqrt(pooled / df)
        lo, hi = sd_ci(s, df)
        a1c[key] = {"sd_pct": s, "sd_ci_pct": [lo, hi], "dof": df,
                    "rel_se_pct": 100 / math.sqrt(2 * df)}
        print(f"  {label:32s} sd {s:.4f} % CI [{lo:.4f}, {hi:.4f}] dof {df} "
              f"(rel SE {100/math.sqrt(2*df):.1f} %)")
    sc = math.sqrt((0.75 * a1c["ln_dec"]["sd_pct"]) ** 2
                   + (0.25 * a1c["ln_pre"]["sd_pct"]) ** 2)
    a1c["sigma_cs_pct"] = sc
    a1c["sigma_cs_ci_pct"] = list(sd_ci(sc, 10))
    lo, hi = sd_ci(sc, 10)
    print(f"  => sigma_cs (candidate axis, 0.75/0.25 weighted) = {sc:.4f} % "
          f"CI [{lo:.4f}, {hi:.4f}] dof 10")
    print(f"     for comparison, Rule 89.2 robust within-group sd(cs) = 0.1763 %, "
          f"pooled = 1.2244 %")
    res["A1c"] = a1c

    # ------------------------------------------------------------ A2c
    print("\n=== A2c  session structure on the prefill and score axes ===")
    _, _, rp, _, _ = ols(day, [r["ln_bl_pre"] for r in rows])
    _, _, rl, _, _ = ols(day, [r["lnL"] for r in rows])
    res["A2c"] = {
        "ln_bl_pre_variogram": variogram(rows, [100 * v for v in rp],
                                         "ln bl_pre (detrended)"),
        "lnL_variogram": variogram(rows, [100 * v for v in rl],
                                   "ln L (detrended)"),
    }
    print("\n  variance components (sessions = gaps > 60 min):")
    for label, vals in (("ln bl_dec", bd_resid),
                        ("ln bl_pre", [100 * v for v in rp]),
                        ("ln L", [100 * v for v in rl])):
        c = components(rows, vals, 60)
        res["A2c"][f"components_{label.replace(' ', '_')}"] = c
        print(f"    {label:10s} k={c['k']:3d} within {c['within_sd_pct']:.4f} % "
              f"CI [{c['within_sd_ci_pct'][0]:.4f}, {c['within_sd_ci_pct'][1]:.4f}]  "
              f"between {c['between_sd_pct']:.4f} %  ICC {c['icc']:+.4f}  "
              f"F({c['df1']},{c['df2']}) = {c['F']:.3f}")

    # ------------------------------------------------------------ A6
    print("\n=== A6  is the huge prefill-baseline spread a harness regime? ===")
    a6 = {}
    for field in ("harness_hash", "golden_hash", "weights_hash"):
        groups = defaultdict(list)
        for r in rows:
            groups[r.get(field)].append(r)
        a6[field] = {"n_distinct": len(groups)}
        print(f"  {field}: {len(groups)} distinct value(s)")
    # regime detection on bl_pre without assuming a cause: sorted structure
    bp = sorted(100 * (r["ln_bl_pre"] - math.log(MB_P)) for r in rows)
    a6["ln_bl_pre_deciles_pct"] = [bp[min(n - 1, int(q * n / 10))]
                                   for q in range(11)]
    print("  ln(bl_pre/MB_P) deciles (%): "
          + " ".join(f"{v:+.3f}" for v in a6["ln_bl_pre_deciles_pct"]))
    # is bl_pre quantized?  the harness reports seconds/token at 512 tokens
    raw = sorted({r["bl_pre"] for r in rows})
    steps = sorted({round((raw[i + 1] - raw[i]) * 1e12) for i in range(len(raw) - 1)})
    a6["n_distinct_bl_pre_values"] = len(raw)
    a6["n_distinct_bl_dec_values"] = len({r["bl_dec"] for r in rows})
    a6["min_positive_bl_pre_step_ps"] = steps[0] if steps else None
    print(f"  distinct bl_pre values {len(raw)} of {n} receipts; "
          f"distinct bl_dec values {a6['n_distinct_bl_dec_values']}")
    print(f"  smallest positive gap between adjacent distinct bl_pre values: "
          f"{steps[0] if steps else None} ps")
    # timer granularity: bl_pre * 512 tokens, bl_dec * 128 steps
    g = sorted({round(r["bl_pre"] * 512 * 1e9) for r in rows})
    a6["prefill_total_ns_distinct"] = len(g)
    res["A6"] = a6

    # ------------------------------------------------------------ A7
    print("\n=== A7  resolving the 4.9x spread: pooled vs robust sd(cs) ===")
    ver = json.load(open(VERIFIED))
    by12 = {}
    for r in rows:
        if r["sha"]:
            by12[r["sha"][:12]] = r
    a7 = {"groups": []}
    tot = {"verified": [0.0, 0], "contaminated": [0.0, 0], "all": [0.0, 0]}
    for g in ver["groups"]:
        mem = [by12[rc["sha12"]] for rc in g["receipts"] if rc["sha12"] in by12]
        if len(mem) < 2:
            continue
        cs = [100 * math.log(r["cs"]) for r in mem]
        v = st.variance(cs)
        lab = "verified" if g.get("verified_inert_only") else "contaminated"
        tot[lab][0] += (len(mem) - 1) * v
        tot[lab][1] += len(mem) - 1
        tot["all"][0] += (len(mem) - 1) * v
        tot["all"][1] += len(mem) - 1
        a7["groups"].append({"group": g["group"], "n": len(mem), "class": lab,
                             "sd_ln_cs_pct": math.sqrt(v),
                             "ss_contribution": (len(mem) - 1) * v,
                             "problems": g.get("problems", [])})
        print(f"  {lab:13s} n={len(mem)}  sd(ln cs) {math.sqrt(v):.4f} %  "
              f"SS {(len(mem)-1)*v:9.4f}  {g['group']}")
    for lab in ("verified", "contaminated", "all"):
        ss, df = tot[lab]
        if df:
            s = math.sqrt(ss / df)
            lo, hi = sd_ci(s, df)
            a7[lab] = {"pooled_sd_ln_cs_pct": s, "dof": df,
                       "ci_pct": [lo, hi], "ss": ss}
            print(f"  POOLED {lab:13s} sd(ln cs) = {s:.4f} % "
                  f"CI [{lo:.4f}, {hi:.4f}]  dof {df}")
    if tot["verified"][1] and tot["contaminated"][1]:
        f = ((tot["contaminated"][0] / tot["contaminated"][1])
             / (tot["verified"][0] / tot["verified"][1]))
        a7["F_contaminated_over_verified"] = f
        a7["F_df"] = [tot["contaminated"][1], tot["verified"][1]]
        print(f"  variance ratio contaminated/verified = {f:.3f} "
              f"on ({tot['contaminated'][1]}, {tot['verified'][1]}) dof")
    a7["reference_n1218_sd_ln_cs_equivalent_pct"] = math.sqrt(
        (0.75 * res["A1"]["ln_bl_dec"]["sd_pct"]) ** 2
        + (0.25 * res["A1c"]["ln_pre"]["sd_pct"]) ** 2)
    print(f"  n=1218 fixed-program reference for sd(ln cs): "
          f"{a7['reference_n1218_sd_ln_cs_equivalent_pct']:.4f} % "
          f"(0.75*sd(ln bl_dec) with the measured candidate prefill sd)")
    res["A7"] = a7

    # ------------------------------------------------------------ A8
    lnL = sorted(r["lnL"] for r in rows)
    res["A8_empirical_lnL"] = {"n": len(lnL),
                               "values_pct": [100 * v for v in lnL]}
    print(f"\n=== A8  exported empirical ln L distribution, n={len(lnL)} ===")
    print(f"  min {100*lnL[0]:+.4f} %  p05 {100*lnL[int(0.05*n)]:+.4f} %  "
          f"p50 {100*lnL[n//2]:+.4f} %  p95 {100*lnL[int(0.95*n)]:+.4f} %  "
          f"max {100*lnL[-1]:+.4f} %")
    need = math.log(RECORD / 2.590559)
    exceed = sum(1 for v in lnL if v > need)
    res["A8_lnL_exceeding_record_gap"] = {
        "required_lnL_pct": 100 * need, "count": exceed, "n": len(lnL),
        "empirical_p": exceed / len(lnL)}
    print(f"  ln L needed for cs=2.590559 to beat the record: "
          f"{100*need:+.4f} %  -> observed in {exceed} of {len(lnL)} receipts "
          f"({100*exceed/len(lnL):.2f} %)")

    # ------------------------------------------------------------ A9
    print("\n=== A9  why is the BASELINE prefill 12x noisier than the "
          "CANDIDATE prefill in the same receipt? ===")
    a9 = {}

    # (a) within verified replicate groups the candidate code is frozen, so
    #     any co-movement of ln pre with ln bl_pre is common-mode machine state.
    xs, ys, ss, dfw = [], [], 0.0, 0
    for _, mem in gsets:
        mx = st.mean([r["ln_bl_pre"] for r in mem])
        my = st.mean([r["ln_pre"] for r in mem])
        ss += sum((100 * (r["ln_bl_pre"] - mx)) ** 2 for r in mem)
        dfw += len(mem) - 1
        for r in mem:
            xs.append(r["ln_bl_pre"] - mx)
            ys.append(r["ln_pre"] - my)
    b, (blo, bhi), se, df, rsd = ols_ci(xs, ys, extra_params=len(gsets) - 1)
    a9["beta_pre_within_groups"] = {"beta": b, "ci": [blo, bhi], "se": se,
                                    "dof": df, "resid_sd_pct": 100 * rsd}
    swb = math.sqrt(ss / dfw)
    a9["within_group_sd_ln_bl_pre_pct"] = swb
    print(f"  within-group leverage: sd(ln bl_pre) = {swb:.4f} % "
          f"(vs candidate sd(ln pre) = {res['A1c']['ln_pre']['sd_pct']:.4f} %)")
    print(f"  beta(ln pre on ln bl_pre, group FE) = {b:+.4f} "
          f"95% CI [{blo:+.4f}, {bhi:+.4f}]  dof {df}")
    print("     beta=+1 => the two legs share machine state and the ratio "
          "cancels; beta=0 => the baseline prefill lottery is pure score noise")

    # (b) shape: locate the antimode of ln(bl_pre/MB_P) as the widest gap
    #     inside the central 60 % of the sorted sample.
    v = sorted(100 * math.log(r["bl_pre"] / MB_P) for r in rows)
    lo_i, hi_i = int(0.20 * n), int(0.80 * n)
    gap, cut = -1.0, None
    for i in range(lo_i, hi_i):
        g = v[i + 1] - v[i]
        if g > gap:
            gap, cut = g, 0.5 * (v[i] + v[i + 1])
    low = [x for x in v if x < cut]
    high = [x for x in v if x >= cut]
    a9["bimodality"] = {
        "antimode_pct": cut, "widest_central_gap_pct": gap,
        "low": {"n": len(low), "mean_pct": st.mean(low), "sd_pct": st.stdev(low)},
        "high": {"n": len(high), "mean_pct": st.mean(high), "sd_pct": st.stdev(high)},
        "separation_pct": st.mean(high) - st.mean(low)}
    print(f"  antimode at {cut:+.3f} % (widest central gap {gap:.3f} %): "
          f"low mode n={len(low)} mean {st.mean(low):+.3f} % sd {st.stdev(low):.3f} % | "
          f"high mode n={len(high)} mean {st.mean(high):+.3f} % sd {st.stdev(high):.3f} % "
          f"| separation {st.mean(high)-st.mean(low):.3f} %")
    wl, wh = len(low) / n, len(high) / n
    mix = math.sqrt(wl * st.stdev(low) ** 2 + wh * st.stdev(high) ** 2
                    + wl * wh * (st.mean(high) - st.mean(low)) ** 2)
    a9["bimodality"]["mixture_sd_pct"] = mix
    a9["bimodality"]["between_mode_share"] = (
        wl * wh * (st.mean(high) - st.mean(low)) ** 2) / mix ** 2
    print(f"  two-component reconstruction: sd {mix:.4f} % of which "
          f"{100*a9['bimodality']['between_mode_share']:.1f} % of the variance is "
          f"between the two modes")

    # (c) is the high mode a persistent regime, or interleaved draw by draw?
    per_day = {}
    for r in rows:
        d = r["createdAt"][:10]
        per_day.setdefault(d, []).append(
            1 if 100 * math.log(r["bl_pre"] / MB_P) >= cut else 0)
    a9["high_mode_fraction_by_day"] = {d: {"n": len(f), "frac": sum(f) / len(f)}
                                       for d, f in sorted(per_day.items())}
    print("  high-mode fraction by UTC day:")
    for d, f in sorted(per_day.items()):
        print(f"    {d}  n={len(f):4d}  frac {sum(f)/len(f):.3f}")
    runs = 1
    seq = [1 if 100 * math.log(r["bl_pre"] / MB_P) >= cut else 0 for r in rows]
    for i in range(1, len(seq)):
        if seq[i] != seq[i - 1]:
            runs += 1
    n1, n0 = sum(seq), len(seq) - sum(seq)
    er = 1 + 2 * n1 * n0 / (n1 + n0)
    vr = 2 * n1 * n0 * (2 * n1 * n0 - n1 - n0) / ((n1 + n0) ** 2 * (n1 + n0 - 1))
    a9["runs_test"] = {"runs": runs, "expected": er, "sd": math.sqrt(vr),
                       "z": (runs - er) / math.sqrt(vr)}
    print(f"  runs test on the mode sequence in submission order: {runs} runs, "
          f"expected {er:.1f} +- {math.sqrt(vr):.1f}, z = "
          f"{(runs-er)/math.sqrt(vr):+.2f} "
          f"(z<0 => clustered regimes, z~0 => interleaved draws)")

    # (d) does the candidate prefill know which mode the baseline drew?
    pl = [100 * r["ln_pre"] for r in rows
          if 100 * math.log(r["bl_pre"] / MB_P) < cut]
    ph = [100 * r["ln_pre"] for r in rows
          if 100 * math.log(r["bl_pre"] / MB_P) >= cut]
    a9["candidate_ln_pre_by_mode"] = {
        "low_mode_mean_pct": st.mean(pl), "high_mode_mean_pct": st.mean(ph),
        "diff_pct": st.mean(ph) - st.mean(pl),
        "low_sd_pct": st.stdev(pl), "high_sd_pct": st.stdev(ph)}
    print(f"  candidate ln pre by baseline mode: low {st.mean(pl):+.3f} % vs "
          f"high {st.mean(ph):+.3f} %  diff {st.mean(ph)-st.mean(pl):+.3f} % "
          f"(merit differs across receipts, so read this only as a co-movement hint)")

    ram = [(r["peak_ram"], 100 * math.log(r["bl_pre"] / MB_P)) for r in rows
           if r.get("peak_ram")]
    if len(ram) > 10:
        rr = ols_ci([a for a, _ in ram], [b_ for _, b_ in ram])
        a9["peak_ram_slope"] = {"beta_pct_per_gb": rr[0], "ci": list(rr[1]),
                                "dof": rr[3], "n": len(ram)}
        print(f"  slope of ln(bl_pre) on peak_ram_gb: {rr[0]:+.4f} %/GB "
              f"CI [{rr[1][0]:+.4f}, {rr[1][1]:+.4f}] dof {rr[3]} n {len(ram)}")
    res["A9"] = a9


if __name__ == "__main__":
    sys.exit(main())
