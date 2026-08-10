#!/usr/bin/env python3
"""R107: how much of the ranked session noise cancels between baseline and candidate?

WHY THIS MATTERS
----------------
The endgame arithmetic (Rule 95.1) prices a draw with sigma_tot ~ 0.55 %, taken
from the dispersion of the *session factor*

    1 + f = (bd/MB_D)^0.75 * (bp/MB_P)^0.25

which depends only on the ranked runner's freshly measured baseline legs.  But
the quantity that actually decides whether a draw takes the record is

    officialScore = (bd/cd)^0.75 * (bp/cp)^0.25

and `bd`/`cd` are measured **in the same session on the same machine**.  If a
slow session slows the baseline and the candidate together, that noise cancels
in the ratio, and the true per-draw sigma of officialScore is far below
sigma(f).  Pricing draws with sigma(f) would then be badly optimistic.

Two independent estimators, both read-only on the public feed:

  A. COMMON-MODE REGRESSION.  Regress ln(candidate leg) on ln(baseline leg)
     across the whole corpus.  Tree heterogeneity lives in the *response*, so
     the slope beta is a consistent estimate of the common-mode coupling even
     though the corpus mixes hundreds of different trees.  The residual
     session noise that survives the ratio is then (1 - beta) * sd(ln baseline).

  B. REPEAT GROUPS.  Pool the within-group variance of ln(officialScore) over
     groups of receipts that share a candidate leg to within a tight tolerance
     (i.e. repeated submissions of the same program).  This is assumption-free
     but has few degrees of freedom.

Usage:
    python3 research/maple-frieren-r107-common-mode.py \
            [--out-json research/maple-frieren-r107-common-mode.json]
"""
import argparse
import json
import math
import os
import urllib.request

FEED = ("https://api.mlx.fast/api/benchmarks/"
        "1854efdf-feba-4773-bae9-b80520881a74/submissions")
MB_D = 0.013855009542
MB_P = 0.000372473193
RECORD = 2.61650354381456
OUR_CS = 2.590559          # best-ever merit in the 4b0e051b family


def fetch():
    req = urllib.request.Request(FEED, headers={
        "Authorization": f"Bearer {os.environ['MLXFAST_API_TOKEN']}",
        "Accept": "application/json",
    })
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.load(r)


def dig(obj, *names):
    stack = [obj]
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            for k, v in cur.items():
                if k in names and isinstance(v, (int, float)) and not isinstance(v, bool):
                    return float(v)
            stack.extend(cur.values())
        elif isinstance(cur, list):
            stack.extend(cur)
    return None


def mean(xs):
    return sum(xs) / len(xs)


def var(xs):
    m = mean(xs)
    return sum((x - m) ** 2 for x in xs) / (len(xs) - 1)


def sd(xs):
    return math.sqrt(var(xs))


def slope(x, y):
    mx, my = mean(x), mean(y)
    sxy = sum((a - mx) * (b - my) for a, b in zip(x, y))
    sxx = sum((a - mx) ** 2 for a in x)
    return sxy / sxx


def norm_sf(z):
    return 0.5 * math.erfc(z / math.sqrt(2))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-json", default=None)
    args = ap.parse_args()

    feed = fetch()
    subs = feed["submissions"] if isinstance(feed, dict) and "submissions" in feed else feed

    rows = []
    for s in subs:
        official = dig(s, "officialScore", "official_score")
        bd = dig(s, "baselineDecodeSecondsPerToken", "baseline_decode_seconds_per_token")
        bp = dig(s, "baselinePrefillSecondsPerToken", "baseline_prefill_seconds_per_token")
        cd = dig(s, "decodeSecondsPerToken", "decode_seconds_per_token")
        cp = dig(s, "prefillSecondsPerToken", "prefill_seconds_per_token")
        if None in (official, bd, bp, cd, cp) or min(bd, bp, cd, cp) <= 0:
            continue
        cs = (MB_D / cd) ** 0.75 * (MB_P / cp) ** 0.25
        rows.append({"id": s.get("id"), "O": official, "cs": cs,
                     "bd": bd, "bp": bp, "cd": cd, "cp": cp,
                     "f": official / cs - 1.0})
    print(f"usable receipts: {len(rows)}")

    lbd = [math.log(r["bd"]) for r in rows]
    lbp = [math.log(r["bp"]) for r in rows]
    lcd = [math.log(r["cd"]) for r in rows]
    lcp = [math.log(r["cp"]) for r in rows]
    lO = [math.log(r["O"]) for r in rows]
    lf = [math.log1p(r["f"]) for r in rows]

    sd_bd, sd_bp = sd(lbd), sd(lbp)
    print(f"\nbaseline dispersion   decode {sd_bd*100:.4f} %   prefill {sd_bp*100:.4f} %")
    print(f"candidate dispersion  decode {sd(lcd)*100:.4f} %   prefill {sd(lcp)*100:.4f} %"
          "   (includes tree heterogeneity)")
    print(f"sd(ln(1+f))           {sd(lf)*100:.4f} %")
    print(f"sd(ln officialScore)  {sd(lO)*100:.4f} %   (includes tree heterogeneity)")

    # --- A. common-mode regression ------------------------------------------
    bdec = slope(lbd, lcd)
    bpre = slope(lbp, lcp)
    print("\nA. COMMON-MODE COUPLING  (ln candidate leg  ~  ln baseline leg)")
    print(f"   decode  beta = {bdec:+.4f}   -> surviving session noise "
          f"{abs(1-bdec)*sd_bd*100:.4f} %")
    print(f"   prefill beta = {bpre:+.4f}   -> surviving session noise "
          f"{abs(1-bpre)*sd_bp*100:.4f} %")
    resid_d = abs(1 - bdec) * sd_bd
    resid_p = abs(1 - bpre) * sd_bp
    sigma_A = math.sqrt((0.75 * resid_d) ** 2 + (0.25 * resid_p) ** 2)
    sigma_f = math.sqrt((0.75 * sd_bd) ** 2 + (0.25 * sd_bp) ** 2)
    print(f"   sigma(ln O | tree) from common-mode model = {sigma_A*100:.4f} %")
    print(f"   sigma(ln(1+f)) reconstructed from legs    = {sigma_f*100:.4f} %")
    print(f"   prefill share of Var(f) = {(0.25*sd_bp)**2/sigma_f**2*100:.2f} %")

    # --- B. repeat groups ----------------------------------------------------
    print("\nB. REPEAT GROUPS  (receipts sharing a candidate leg within tolerance)")
    best = None
    for tol in (2e-4, 5e-4, 1e-3, 2e-3):
        rows.sort(key=lambda r: (r["cd"], r["cp"]))
        groups, cur = [], [rows[0]]
        for prev, r in zip(rows, rows[1:]):
            same = (abs(math.log(r["cd"] / prev["cd"])) < tol
                    and abs(math.log(r["cp"] / prev["cp"])) < tol)
            if same:
                cur.append(r)
            else:
                groups.append(cur)
                cur = [r]
        groups.append(cur)
        multi = [g for g in groups if len(g) >= 2]
        ss, df = 0.0, 0
        for g in multi:
            v = [math.log(x["O"]) for x in g]
            m = mean(v)
            ss += sum((x - m) ** 2 for x in v)
            df += len(g) - 1
        if df >= 5:
            s_within = math.sqrt(ss / df)
            print(f"   tol {tol:.0e}: {len(multi)} groups, df={df:3d}, "
                  f"sd(ln O | tree) = {s_within*100:.4f} %")
            if best is None:
                best = (tol, df, s_within)
        else:
            print(f"   tol {tol:.0e}: {len(multi)} groups, df={df:3d}  (too few)")

    # --- what it costs to take the record -----------------------------------
    need = math.log(RECORD / OUR_CS)
    print(f"\nRECORD ARITHMETIC   need ln(O/cs) >= {need*100:.4f} % on a draw")
    for label, sig in (("sigma(f) pricing (Rule 95.1)", sigma_f),
                       ("common-mode pricing (A)", sigma_A)) + (
                      (("repeat-group pricing (B)", best[2]),) if best else ()):
        p = norm_sf(need / sig)
        n20 = 1 - (1 - p) ** 20
        print(f"   {label:32s} sigma {sig*100:6.4f} %  "
              f"P(draw) {p*100:6.3f} %   P(20 draws) {n20*100:5.1f} %")

    out = {
        "n": len(rows),
        "sd_ln_baseline_decode": sd_bd, "sd_ln_baseline_prefill": sd_bp,
        "beta_decode": bdec, "beta_prefill": bpre,
        "sigma_lnO_common_mode": sigma_A, "sigma_lnf": sigma_f,
        "repeat_group": ({"tol": best[0], "df": best[1], "sd": best[2]} if best else None),
        "need_ln_ratio": need,
    }
    if args.out_json:
        with open(args.out_json, "w", encoding="utf-8") as fh:
            json.dump(out, fh, indent=2)
        print(f"\nwrote {args.out_json}")


if __name__ == "__main__":
    main()
