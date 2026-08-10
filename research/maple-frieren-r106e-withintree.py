#!/usr/bin/env python3
"""R106-E: within-tree session-lottery statistics from the R93 Arm-A null replicates.

The R93 Arm-A nulls (`research/r93-runs/receipts/null-*.json`) are five official
M5 receipts of one machine-code-identical tree; `null-1` is submission commit
`4b0e051b`, the tree R105-B rev4 asks to replicate. They therefore already carry
the five numbers per draw that rev4 requires, and they estimate sd(f) *inside a
fixed tree* at n = 5.

Usage: python3 research/maple-frieren-r106e-withintree.py [--out-json PATH]
"""
import argparse
import glob
import json
import math
import os

MB_D = 0.013855009542
MB_P = 0.000372473193
CORPUS_SD_F = 0.5352      # advisor rev4 §2, n = 84
TANJIRO_SD_F = 0.5393     # #555 Part 1, n = 1185
FRIEREN_SD_F = 0.5369     # this PR §13, n = 1220
RECORD = 2.61650354381456
RECORD_HOLDER_CS = 2.574594   # cc6ddc12, master-baseline candidate score
CORPUS_N = 1220               # scored feed rows behind the corpus sd(f)


def chi2_quantile(p, df):
    """Chi-square quantile via Wilson-Hilferty, refined by bisection on the CDF."""
    def cdf(x):
        # regularised lower incomplete gamma P(df/2, x/2) by series/CF
        a, xx = df / 2.0, x / 2.0
        if xx <= 0:
            return 0.0
        if xx < a + 1:
            term = 1.0 / a
            total = term
            n = 1
            while n < 10000:
                term *= xx / (a + n)
                total += term
                if abs(term) < abs(total) * 1e-15:
                    break
                n += 1
            return total * math.exp(-xx + a * math.log(xx) - math.lgamma(a))
        b = xx + 1.0 - a
        c = 1e300
        d = 1.0 / b
        h = d
        for i in range(1, 10000):
            an = -i * (i - a)
            b += 2.0
            d = an * d + b
            if abs(d) < 1e-300:
                d = 1e-300
            c = b + an / c
            if abs(c) < 1e-300:
                c = 1e-300
            d = 1.0 / d
            delta = d * c
            h *= delta
            if abs(delta - 1.0) < 1e-15:
                break
        return 1.0 - math.exp(-xx + a * math.log(xx) - math.lgamma(a)) * h

    lo, hi = 1e-9, max(1000.0, df * 50.0)
    for _ in range(300):
        mid = (lo + hi) / 2.0
        if cdf(mid) < p:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def sd_ci(sd, n, conf=0.95):
    df = n - 1
    alpha = 1 - conf
    lo = sd * math.sqrt(df / chi2_quantile(1 - alpha / 2, df))
    hi = sd * math.sqrt(df / chi2_quantile(alpha / 2, df))
    return lo, hi


def mean(v):
    return sum(v) / len(v)


def sd(v):
    m = mean(v)
    return math.sqrt(sum((x - m) ** 2 for x in v) / (len(v) - 1))


def corr(a, b):
    ma, mb = mean(a), mean(b)
    num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    da = math.sqrt(sum((x - ma) ** 2 for x in a))
    db = math.sqrt(sum((y - mb) ** 2 for y in b))
    return num / (da * db) if da and db else float("nan")


def fisher_ci(r, n, conf=0.95):
    if n < 4:
        return float("nan"), float("nan")
    z = 0.5 * math.log((1 + r) / (1 - r))
    se = 1.0 / math.sqrt(n - 3)
    crit = 1.959963985
    return math.tanh(z - crit * se), math.tanh(z + crit * se)


def norm_sf(z):
    return 0.5 * math.erfc(z / math.sqrt(2))


def norm_isf(p):
    """Upper-tail inverse: returns z with norm_sf(z) == p."""
    lo, hi = -40.0, 40.0
    for _ in range(200):
        mid = (lo + hi) / 2.0
        if norm_sf(mid) > p:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def expected_max_normal(n):
    """Blom's approximation to E[max] of n iid standard normals."""
    return norm_isf(1.0 - (n - 0.375) / (n + 0.25))


def load(repo):
    rows = []
    for path in sorted(glob.glob(os.path.join(repo, "research", "r93-runs",
                                              "receipts", "null-*.json"))):
        sub = json.load(open(path))["submission"]
        m = sub["officialMetrics"]
        dec, pre = m["decode_seconds_per_token"], m["prefill_seconds_per_token"]
        bd, bp = (m["baseline_decode_seconds_per_token"],
                  m["baseline_prefill_seconds_per_token"])
        cs = (MB_D / dec) ** 0.75 * (MB_P / pre) ** 0.25
        f = 0.75 * math.log(bd / MB_D) + 0.25 * math.log(bp / MB_P)
        rows.append({
            "marker": os.path.basename(path)[:-5],
            "submission_id": sub["id"],
            "commit": m["commit"],
            "created_at": sub["createdAt"],
            "decode_s": dec, "prefill_s": pre,
            "baseline_decode_s": bd, "baseline_prefill_s": bp,
            "cs": cs,
            "official_score": sub["officialScore"],
            "f_pct": f * 100.0,
            "recon_official": cs * math.exp(f),
        })
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-json")
    args = ap.parse_args()
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    rows = load(repo)
    n = len(rows)

    recon_err = max(abs(r["recon_official"] / r["official_score"] - 1) for r in rows)

    ln_cs = [math.log(r["cs"]) * 100 for r in rows]
    f = [r["f_pct"] for r in rows]
    ln_dec = [math.log(r["decode_s"]) for r in rows]
    ln_bd = [math.log(r["baseline_decode_s"]) for r in rows]
    ln_pre = [math.log(r["prefill_s"]) for r in rows]
    ln_bp = [math.log(r["baseline_prefill_s"]) for r in rows]
    ln_os = [math.log(r["official_score"]) * 100 for r in rows]

    sd_lncs, sd_f, sd_lnos = sd(ln_cs), sd(f), sd(ln_os)
    out = {
        "n": n,
        "reconstruction_max_rel_err": recon_err,
        "draws": rows,
        "mean_cs": mean([r["cs"] for r in rows]),
        "max_cs": max(r["cs"] for r in rows),
        "sd_ln_cs_pct": sd_lncs,
        "sd_ln_cs_ci": sd_ci(sd_lncs, n),
        "sd_f_pct": sd_f,
        "sd_f_ci": sd_ci(sd_f, n),
        "mean_f_pct": mean(f),
        "sd_ln_official_pct": sd_lnos,
        "sd_ln_official_ci": sd_ci(sd_lnos, n),
        "sd_ln_bl_decode_pct": sd(ln_bd) * 100,
        "sd_ln_bl_prefill_pct": sd(ln_bp) * 100,
        "H0a_corr_dec": corr(ln_dec, ln_bd),
        "H0a_corr_dec_ci": fisher_ci(corr(ln_dec, ln_bd), n),
        "corr_pre": corr(ln_pre, ln_bp),
        "corr_pre_ci": fisher_ci(corr(ln_pre, ln_bp), n),
        "corr_lncs_f": corr(ln_cs, f),
        "corr_lncs_f_ci": fisher_ci(corr(ln_cs, f), n),
        "corr_bl_legs": corr(ln_bd, ln_bp),
    }

    # Mechanism: a slow session inflates f but also inflates the candidate's own
    # timings, which depresses cs. The regression of ln cs on f measures how much
    # of a session excursion the paired baseline gives back; 1 + slope is the
    # fraction of f that survives into officialScore.
    slope = corr(ln_cs, f) * sd_lncs / sd_f
    out["cs_on_f_slope"] = slope
    out["session_pass_through"] = 1.0 + slope
    out["sd_lnos_implied_by_slope_pct"] = abs(1.0 + slope) * sd_f

    # H0b: is within-tree sd(f) below the corpus figure? chi-square one-sided.
    df = n - 1
    stat = df * (sd_f / CORPUS_SD_F) ** 2
    out["H0b_chi2_stat"] = stat
    out["H0b_reject_below_at_5pct"] = stat < chi2_quantile(0.05, df)

    # winner's curse: 4b0e051b (null-1) is the max of the replicate set.
    csvals = [r["cs"] for r in rows]
    out["winners_curse_bias"] = max(csvals) - mean(csvals)
    out["winners_curse_bias_pct"] = (math.log(max(csvals)) -
                                     mean([math.log(c) for c in csvals])) * 100

    # P(record) per draw. Two independent modelling choices dominate the answer,
    # so report the full 2x3 matrix instead of one number.
    #
    #   anchor  - which cs stands for "this tree": null-1 is the max of the five
    #             replicates and therefore carries the winner's curse.
    #   sigma   - `corpus` is the advisor's sd(f) alone; `naive` adds candidate
    #             noise as if independent; `paired` is the directly measured
    #             sd(ln officialScore), which absorbs the strong negative cs/f
    #             coupling that same-session pairing induces. Only `paired`
    #             describes what a real resubmission of this tree does.
    #
    # E[f] is fixed at 0: baselines are re-measured every session from
    # code the candidate cannot touch, so a tree cannot own a session factor.
    # This tree's mean f (-0.25 %) is 1.07 SE from 0 and is shrunk away.
    sigma_naive = math.sqrt(sd_lncs ** 2 + sd_f ** 2)
    out["sigma_naive_pct"] = sigma_naive
    out["se_mean_f_pct"] = sd_f / math.sqrt(n)
    ln_cs_mean = mean([math.log(c) for c in csvals])
    sd_lo, sd_hi = out["sd_ln_official_ci"]
    for label, ln_cs0 in (("null1", math.log(rows[0]["cs"]) * 100),
                          ("replicate_mean", ln_cs_mean * 100)):
        gap = math.log(RECORD) * 100 - ln_cs0
        for sname, sigma in (("corpus", FRIEREN_SD_F), ("naive", sigma_naive),
                             ("paired", sd_lnos)):
            z = gap / sigma
            out[f"p_record_{label}_{sname}"] = {
                "cs": math.exp(ln_cs0 / 100), "gap_pct": gap, "sigma_pct": sigma,
                "z": z, "p": norm_sf(z), "e_draws": 1.0 / norm_sf(z),
            }
    headline = out["p_record_replicate_mean_paired"]
    out["headline"] = dict(headline)
    out["headline"]["p_at_sd_ci_hi"] = norm_sf(headline["gap_pct"] / sd_hi)
    out["headline"]["p_at_sd_ci_lo"] = norm_sf(headline["gap_pct"] / sd_lo)
    out["geo_mean_official"] = math.exp(mean(ln_os) / 100)

    # The record itself decomposed: cc6ddc12 ranks above us on officialScore
    # while sitting *below* us on the session-free candidate score.
    rec_f = (math.log(RECORD) - math.log(RECORD_HOLDER_CS)) * 100
    out["record_holder"] = {
        "official": RECORD, "cs": RECORD_HOLDER_CS, "f_pct": rec_f,
        "z_vs_corpus_sd_f": rec_f / FRIEREN_SD_F,
        "our_cs_lead_pct": (math.log(max(csvals)) - math.log(RECORD_HOLDER_CS)) * 100,
        "our_mean_cs_lead_pct": (mean([math.log(c) for c in csvals]) -
                                 math.log(RECORD_HOLDER_CS)) * 100,
        "expected_max_z_at_n": expected_max_normal(CORPUS_N),
        "expected_max_f_pct": expected_max_normal(CORPUS_N) * FRIEREN_SD_F,
    }

    print(f"n = {n}   reconstruction max rel err = {recon_err:.3e}")
    print(f"{'marker':<8} {'cs':>10} {'official':>10} {'bl_dec_us':>11} "
          f"{'bl_pre_us':>10} {'f %':>8}")
    for r in rows:
        print(f"{r['marker']:<8} {r['cs']:>10.6f} {r['official_score']:>10.6f} "
              f"{r['baseline_decode_s']*1e6:>11.3f} "
              f"{r['baseline_prefill_s']*1e6:>10.3f} {r['f_pct']:>8.4f}")
    print()
    print(f"sd(ln cs)        = {sd_lncs:.4f} %  CI {out['sd_ln_cs_ci'][0]:.4f}"
          f"..{out['sd_ln_cs_ci'][1]:.4f}")
    print(f"sd(f)            = {sd_f:.4f} %  CI {out['sd_f_ci'][0]:.4f}"
          f"..{out['sd_f_ci'][1]:.4f}   mean f = {out['mean_f_pct']:+.4f} %")
    print(f"sd(ln official)  = {sd_lnos:.4f} %  CI {out['sd_ln_official_ci'][0]:.4f}"
          f"..{out['sd_ln_official_ci'][1]:.4f}")
    print(f"sd(ln bl_decode) = {out['sd_ln_bl_decode_pct']:.4f} %   "
          f"sd(ln bl_prefill) = {out['sd_ln_bl_prefill_pct']:.4f} %")
    print(f"H0a corr(ln dec, ln bl_dec) = {out['H0a_corr_dec']:+.4f} "
          f"CI [{out['H0a_corr_dec_ci'][0]:+.3f}, {out['H0a_corr_dec_ci'][1]:+.3f}]")
    print(f"    corr(ln pre, ln bl_pre) = {out['corr_pre']:+.4f} "
          f"CI [{out['corr_pre_ci'][0]:+.3f}, {out['corr_pre_ci'][1]:+.3f}]")
    print(f"    corr(ln cs, f)          = {out['corr_lncs_f']:+.4f} "
          f"CI [{out['corr_lncs_f_ci'][0]:+.3f}, {out['corr_lncs_f_ci'][1]:+.3f}]")
    print(f"session pass-through: d(ln cs)/df = {out['cs_on_f_slope']:+.4f}, "
          f"so {out['session_pass_through']*100:.1f} % of f survives into "
          f"officialScore -> sd {out['sd_lnos_implied_by_slope_pct']:.4f} % "
          f"(measured {sd_lnos:.4f} %)")
    print(f"H0b vs corpus {CORPUS_SD_F} %: chi2 = {stat:.3f}, "
          f"reject-below-at-5% = {out['H0b_reject_below_at_5pct']}")
    print(f"winner's curse (max - mean cs) = {out['winners_curse_bias']:+.6f} "
          f"({out['winners_curse_bias_pct']:+.4f} % log)")
    print()
    print(f"P(record) per draw  (E[f] = 0; SE of this tree's mean f = "
          f"{out['se_mean_f_pct']:.4f} %)")
    print(f"  {'anchor':<15} {'sigma':<8} {'cs':>9} {'gap %':>8} "
          f"{'sd %':>7} {'z':>6} {'P %':>9} {'E[draws]':>9}")
    for label in ("null1", "replicate_mean"):
        for sname in ("corpus", "naive", "paired"):
            v = out[f"p_record_{label}_{sname}"]
            print(f"  {label:<15} {sname:<8} {v['cs']:>9.6f} {v['gap_pct']:>8.4f} "
                  f"{v['sigma_pct']:>7.4f} {v['z']:>6.3f} {v['p']*100:>9.4f} "
                  f"{v['e_draws']:>9.0f}")
    h = out["headline"]
    print(f"  headline P range over the paired-sd 95 % CI: "
          f"{h['p_at_sd_ci_lo']*100:.5f} % .. {h['p_at_sd_ci_hi']*100:.4f} %")
    print(f"  geometric mean officialScore of the five draws = "
          f"{out['geo_mean_official']:.6f}")
    print()
    rh = out["record_holder"]
    print(f"record holder cc6ddc12: official {rh['official']:.6f}  "
          f"cs {rh['cs']:.6f}  f = {rh['f_pct']:+.4f} % "
          f"(z = {rh['z_vs_corpus_sd_f']:+.3f} vs corpus sd f)")
    print(f"  our cs lead over the record holder: "
          f"{rh['our_cs_lead_pct']:+.4f} % (null-1) / "
          f"{rh['our_mean_cs_lead_pct']:+.4f} % (replicate mean)")
    print(f"  E[max f] over n = {CORPUS_N} draws = "
          f"{rh['expected_max_f_pct']:+.4f} % (z = {rh['expected_max_z_at_n']:.3f})")

    if args.out_json:
        json.dump(out, open(args.out_json, "w"), indent=2)
        print(f"\nwrote {args.out_json}")


if __name__ == "__main__":
    main()
