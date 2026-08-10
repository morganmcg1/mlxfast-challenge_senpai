#!/usr/bin/env python3
"""R106-E: measure the official channel's replication spread.

Selects the draws of one replication ladder out of the official feed by their
note marker, then reports the three numbers the campaign actually consumes:

  1. sd(ln x) for cs, decode, prefill and the ranked officialScore, each with a
     chi-square confidence interval, plus the 1-vs-1 difference sigma sd*sqrt2.
  2. whether the spread is session-correlated -- candidate leg regressed on
     baseline leg. `cs` is supposed to strip the session draw; if the legs move
     together it is not doing its job.
  3. the preregistered discrimination verdict.

Every draw in a ladder ships a byte-identical compiled tree, so all observed
spread is channel noise with no code effect mixed in. That is the property no
prior campaign receipt has had.

Usage: maple-frieren-r106e-ladder.py [--marker R106E-DRAW-] [--since ISO]
                                     [--json OUT]
"""
import argparse
import json
import math
import os
import subprocess
import statistics

BENCH = "1854efdf-feba-4773-bae9-b80520881a74"
API = "https://api.mlx.fast/api"
X = -5.1831677111  # cs = exp(X - .75 ln(D/1e6) - .25 ln(P/1e6))

# Preregistered discrimination thresholds on the 1-vs-1 sd of ln cs, in %.
TIGHT, LOOSE = 0.35, 0.80
# The three incumbent estimators this round is meant to separate, in %.
INCUMBENTS = {"89.2 near-replicate 1-vs-1": 0.2494,
              "#555 session lottery": 0.5393,
              "89.2 pooled": 1.2244}
RECORD, BEST_DRAW = 2.61650354381456, 2.590559
RULE91_RESIDUAL_PCT = 0.3204  # round-103 "unexplained" 19.0 us/step, as % of cs


def get(url, token):
    r = subprocess.run(["curl", "-s", "-H", "Authorization: Bearer " + token, url],
                       capture_output=True, text=True)
    return json.loads(r.stdout)


def cs_of(dec, pre):
    if not dec or not pre:
        return None
    return math.exp(X - 0.75 * math.log(dec / 1e6) - 0.25 * math.log(pre / 1e6))


def norm_q(p):
    """Acklam's inverse normal CDF, good to ~1e-9."""
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00]
    pl, ph = 0.02425, 1 - 0.02425
    if p < pl:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    if p > ph:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    q, r = p - 0.5, (p - 0.5) ** 2
    return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)


def chi2_q(p, k):
    """Wilson-Hilferty quantile of chi-square with k dof."""
    z = norm_q(p)
    return k * (1 - 2.0 / (9 * k) + z * math.sqrt(2.0 / (9 * k))) ** 3


def sd_ci(sd, n, conf=0.95):
    """Chi-square CI for a normal sd from n observations."""
    k = n - 1
    if k < 1:
        return (None, None)
    lo = math.sqrt(k * sd * sd / chi2_q(1 - (1 - conf) / 2, k))
    hi = math.sqrt(k * sd * sd / chi2_q((1 - conf) / 2, k))
    return lo, hi


def betacf(a, b, x):
    tiny, eps = 1e-30, 3e-16
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    if abs(d) < tiny:
        d = tiny
    d, h = 1.0 / d, 1.0 / d
    for m in range(1, 300):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        c = 1.0 + aa / c
        if abs(d) < tiny:
            d = tiny
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        c = 1.0 + aa / c
        if abs(d) < tiny:
            d = tiny
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        de = d * c
        h *= de
        if abs(de - 1.0) < eps:
            break
    return h


def betai(a, b, x):
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    lb = (math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
          + a * math.log(x) + b * math.log(1 - x))
    bt = math.exp(lb)
    if x < (a + 1) / (a + b + 2):
        return bt * betacf(a, b, x) / a
    return 1.0 - bt * betacf(b, a, 1 - x) / b


def t_sf2(t, dof):
    """Two-sided Student-t tail probability."""
    if dof <= 0:
        return float("nan")
    return betai(dof / 2.0, 0.5, dof / (dof + t * t))


def regress(xs, ys):
    """Least squares y ~ x. Returns r, slope, t, dof, two-sided p."""
    n = len(xs)
    if n < 3:
        return None
    mx, my = statistics.mean(xs), statistics.mean(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    if sxx <= 0 or syy <= 0:
        return None
    r = sxy / math.sqrt(sxx * syy)
    slope = sxy / sxx
    dof = n - 2
    r = max(-0.999999999, min(0.999999999, r))
    t = r * math.sqrt(dof / (1 - r * r))
    return dict(n=n, r=r, slope=slope, t=t, dof=dof, p=t_sf2(t, dof))


def spread(name, xs, conf=0.95):
    """sd of ln x reported in %, with CI and the 1-vs-1 difference sigma."""
    n = len(xs)
    if n < 2:
        return None
    ln = [math.log(v) for v in xs]
    sd = statistics.stdev(ln)
    lo, hi = sd_ci(sd, n, conf)
    pct = lambda v: (None if v is None else 100 * v)
    return dict(name=name, n=n, mean=statistics.mean(xs),
                sd_pct=pct(sd), lo_pct=pct(lo), hi_pct=pct(hi),
                pair_sd_pct=pct(sd * math.sqrt(2)),
                pair_lo_pct=pct(lo * math.sqrt(2)) if lo else None,
                pair_hi_pct=pct(hi * math.sqrt(2)) if hi else None,
                rel_se_pct=100 / math.sqrt(2 * (n - 1)))


def verdict(pair_sd_pct):
    if pair_sd_pct is None:
        return "INSUFFICIENT"
    if pair_sd_pct <= TIGHT:
        return "V-TIGHT"
    if pair_sd_pct >= LOOSE:
        return "V-LOOSE"
    return "V-MID"


def p_record(gap_pct, pair_sd_pct):
    """P(a single draw beats the record) given the gap and the 1-vs-1 sigma."""
    if not pair_sd_pct:
        return None
    z = gap_pct / pair_sd_pct
    # survival of the standard normal via erfc
    return 0.5 * math.erfc(z / math.sqrt(2))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--marker", default="R106E-DRAW-")
    ap.add_argument("--since", default="2026-08-10T08:00")
    ap.add_argument("--json", dest="out")
    a = ap.parse_args()
    token = os.environ["MLXFAST_API_TOKEN"]

    feed = get(f"{API}/benchmarks/{BENCH}/submissions", token)
    if isinstance(feed, dict):
        feed = feed.get("submissions") or feed.get("data") or []
    rows = sorted((r for r in feed if (r.get("createdAt") or "") >= a.since),
                  key=lambda r: r["createdAt"])

    draws = []
    for r in rows:
        d = get(f"{API}/submissions/{r['id']}", token)
        d = d.get("submission", d)
        note = d.get("note") or ""
        if a.marker not in note:
            continue
        tag = next((w for w in note.replace("`", " ").split()
                    if w.startswith(a.marker)), a.marker + "??")
        m = d.get("officialMetrics") or {}
        us = lambda k: (m[k] * 1e6 if m.get(k) else None)
        cd, cp = us("decode_seconds_per_token"), us("prefill_seconds_per_token")
        draws.append(dict(
            tag=tag, t=r["createdAt"], id=r["id"], status=d.get("status"),
            cand_dec=cd, cand_pre=cp,
            base_dec=us("baseline_decode_seconds_per_token"),
            base_pre=us("baseline_prefill_seconds_per_token"),
            cs=cs_of(cd, cp), score=d.get("officialScore"),
            dec_su=m.get("decode_speedup"), pre_su=m.get("prefill_speedup"),
            commit=m.get("commit") or d.get("submissionCommitSha"),
            correct=m.get("passed_correctness"), max_abs_diff=m.get("max_abs_diff"),
            golden=m.get("golden_hash"), reason=d.get("rejectionReason"),
            improved=d.get("improved"), completed=d.get("completedAt"),
        ))
    for d in draws:
        d["L"] = (d["score"] / d["cs"]) if (d["score"] and d["cs"]) else None

    print(f"=== R106-E ladder: {len(draws)} draw(s) matching '{a.marker}' ===\n")
    fmt = lambda v, w, p=3: (f"{v:{w}.{p}f}" if isinstance(v, (int, float)) else " " * (w - 1) + "-")
    print(f"{'tag':22}{'time':9}{'status':11}{'cand_dec':>10}{'cand_pre':>9}"
          f"{'base_dec':>10}{'base_pre':>9}{'cs':>10}{'score':>10}{'L':>8}")
    for d in draws:
        print(f"{d['tag'][:21]:22}{d['t'][11:19]} {str(d['status'])[:10]:10}"
              f"{fmt(d['cand_dec'],10)}{fmt(d['cand_pre'],9)}{fmt(d['base_dec'],10)}"
              f"{fmt(d['base_pre'],9)}{fmt(d['cs'],10,6)}{fmt(d['score'],10,6)}"
              f"{fmt(d['L'],8,5)}")

    ok = [d for d in draws if d["cs"] and d["score"]]
    print(f"\ncorrectness: "
          f"{sum(1 for d in ok if d['correct'])}/{len(ok)} passed, "
          f"max_abs_diff set: {sorted({d['max_abs_diff'] for d in ok})}, "
          f"golden hashes: {len({d['golden'] for d in ok})} distinct")
    print(f"distinct submissionCommitSha: {len({d['commit'] for d in ok})} of {len(ok)}")

    out = dict(draws=draws, spreads={}, regressions={}, verdicts={})
    if len(ok) < 2:
        print("\nn < 2 -- no spread computable yet.")
        if a.out:
            json.dump(out, open(a.out, "w"), indent=1)
        return

    print("\n=== SPREAD (sd of ln x, %; CI is chi-square) ===")
    print(f"{'quantity':26}{'n':>3}{'sd%':>9}{'95% CI':>20}{'1-vs-1 sd%':>12}{'relSE%':>9}")
    series = [("cs (candidate-only)", [d["cs"] for d in ok]),
              ("officialScore (RANKED)", [d["score"] for d in ok]),
              ("cand decode", [d["cand_dec"] for d in ok]),
              ("cand prefill", [d["cand_pre"] for d in ok]),
              ("base decode", [d["base_dec"] for d in ok if d["base_dec"]]),
              ("base prefill", [d["base_pre"] for d in ok if d["base_pre"]])]
    for name, xs in series:
        if len(xs) < 2:
            continue
        s = spread(name, xs)
        out["spreads"][name] = s
        ci = f"[{s['lo_pct']:.4f},{s['hi_pct']:.4f}]"
        print(f"{name:26}{s['n']:>3}{s['sd_pct']:>9.4f}{ci:>20}"
              f"{s['pair_sd_pct']:>12.4f}{s['rel_se_pct']:>9.1f}")

    cs_pair = out["spreads"]["cs (candidate-only)"]["pair_sd_pct"]
    sc_pair = out["spreads"]["officialScore (RANKED)"]["pair_sd_pct"]

    print("\n=== SESSION CORRELATION (candidate leg ~ baseline leg) ===")
    for lab, ck, bk in (("decode", "cand_dec", "base_dec"),
                        ("prefill", "cand_pre", "base_pre")):
        pts = [(d[bk], d[ck]) for d in ok if d[bk] and d[ck]]
        g = regress([math.log(x) for x, _ in pts], [math.log(y) for _, y in pts])
        out["regressions"][lab] = g
        if g:
            print(f"{lab:9} n={g['n']} r={g['r']:+.4f} slope={g['slope']:+.4f} "
                  f"t({g['dof']})={g['t']:+.3f} p={g['p']:.4f}")
        else:
            print(f"{lab:9} n<3 -- not estimable")

    corr = any(g and g["p"] < 0.05 and abs(g["r"]) > 0.5
               for g in out["regressions"].values())
    print(f"N-CORRELATED: {'FIRES' if corr else 'does not fire'} "
          f"(criterion |r|>0.5 and p<0.05 on either leg)")

    print("\n=== PREREGISTERED DISCRIMINATION (on 1-vs-1 sd of ln cs) ===")
    v = verdict(cs_pair)
    out["verdicts"] = dict(cs=v, cs_pair_sd_pct=cs_pair,
                           score_pair_sd_pct=sc_pair,
                           n_correlated=corr,
                           ranked_penalty=(sc_pair / cs_pair) if cs_pair else None)
    print(f"measured 1-vs-1 sd(ln cs) = {cs_pair:.4f}%  ->  {v}"
          f"   (thresholds: TIGHT<={TIGHT}, LOOSE>={LOOSE})")
    for k, val in INCUMBENTS.items():
        print(f"  vs {k:32} {val:6.4f}%  ratio {cs_pair/val:5.2f}x")

    print("\n=== S-RANKED: the quantity that is actually ranked ===")
    print(f"1-vs-1 sd(ln officialScore) = {sc_pair:.4f}%, "
          f"{sc_pair/cs_pair:.2f}x the cs figure")
    gap = 100 * math.log(RECORD / BEST_DRAW)
    for lab, s in (("cs", cs_pair), ("officialScore", sc_pair)):
        p = p_record(gap, s)
        n = (1 / p) if p and p > 0 else float("inf")
        print(f"  gap {gap:.4f}% priced on {lab:14} z={gap/s:5.2f} "
              f"P(record)/draw={100*p:8.4f}%  expected draws={n:12.1f}")

    print("\n=== RULE 91 RE-PRICING ===")
    for lab, s in (("cs", cs_pair), ("officialScore", sc_pair)):
        print(f"  round-103 residual {RULE91_RESIDUAL_PCT}% of cs on {lab:14}"
              f" -> z = {RULE91_RESIDUAL_PCT/s:.2f}")

    if a.out:
        json.dump(out, open(a.out, "w"), indent=1)
        print(f"\nwrote {a.out}")


if __name__ == "__main__":
    main()
