#!/usr/bin/env python3
"""R107 sigma adjudication — which within-tree sigma is the honest one?

WHY THIS EXISTS
---------------
The whole ladder is priced off sigma, and the answer is violently
sigma-sensitive.  We need ln(O/cs) >= +0.9965 % to take the record:

    sigma = 0.37 %  ->  z 2.67  ->  ~0.4 %/draw  ->  ~7 % over 18 draws
    sigma = 0.55 %  ->  z 1.81  ->  ~3.5 %/draw  ->  ~47 % over 18 draws

I have published both numbers at different times, and I found a real defect in
the estimator behind the larger one, so this script adjudicates rather than
assumes.

THE DEFECT.  `maple-frieren-r107-common-mode.py` Estimator B groups receipts
that "share a candidate leg to within a tolerance".  Two problems:

  (1) It is SINGLE-LINKAGE chain clustering -- each row is compared only to its
      immediate predecessor in sorted order -- so a dense chain can span a range
      far wider than the tolerance and merge genuinely different trees.  That
      leaks TREE HETEROGENEITY into a "within-tree" variance and inflates it.
  (2) It conditions on the *measured* candidate legs, which are themselves
      noisy.  Conditioning on candidate noise being similar REMOVES candidate
      variance from the within-group spread, which deflates it.

Confounded in both directions, so its agreement with 0.5546 % is not evidence.

THE IDENTITY THAT MATTERS.  With cs computed from fixed reference constants,

    ln O = ln cs + f,      f = 0.75 ln(bd/MB_D) + 0.25 ln(bp/MB_P)

f depends ONLY on the session baseline legs and cs ONLY on the candidate legs.
So a resubmission of one fixed tree has

    Var(ln O | tree) = Var(ln cs | tree) + Var(f) + 2 Cov(ln cs, f | tree)

and the covariance term is exactly the common-mode question: if a slow session
inflates the baseline and the candidate together, Cov < 0 in these coordinates
(f up, cs down) and the resubmission sigma is SMALLER than sd(f).

THREE HONEST ESTIMATES, computed here:
  E1  sd(f) over the feed                  -- clean, tree-free, but is only the
                                              baseline term
  E2  corr(ln cs, f) and the implied
      Var(ln O) decomposition              -- tests cancellation directly
  E3  sd(ln O) over NAMED replicate sets   -- the assumption-free ground truth,
      (Rule 95.3 families)                    small n but no clustering hack

Read-only.  Writes nothing but a JSON summary.
"""
from __future__ import annotations

import json
import math
import os
import urllib.request

FEED = ("https://api.mlx.fast/api/benchmarks/"
        "1854efdf-feba-4773-bae9-b80520881a74/submissions")
MB_D = 0.013855009542
MB_P = 0.000372473193
RECORD = 2.61650354381456

# Rule 95.3: four replicates of one semantic tree, and two of the main-like one.
FAMILY_A = ["4b0e051b", "ef055b9b", "5a43d329", "e1b6e2be"]
FAMILY_B = ["bd33883e", "e33efe4e"]


def fetch(url):
    req = urllib.request.Request(url, headers={
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


def sdig(obj, *names):
    stack = [obj]
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            for k, v in cur.items():
                if k in names and isinstance(v, str) and v:
                    return v
            stack.extend(cur.values())
        elif isinstance(cur, list):
            stack.extend(cur)
    return None


def mean(xs):
    return sum(xs) / len(xs)


def sd(xs):
    if len(xs) < 2:
        return float("nan")
    m = mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def price(need_pct, sigma_pct, draws=18):
    z = need_pct / sigma_pct
    p = 0.5 * math.erfc(z / math.sqrt(2))
    return z, 100 * p, 100 * (1 - (1 - p) ** draws)


def main():
    feed = fetch(FEED)
    subs = feed["submissions"] if isinstance(feed, dict) and "submissions" in feed else feed

    rows = []
    for s in subs:
        O = dig(s, "officialScore", "official_score")
        cd = dig(s, "decodeSecondsPerToken", "decode_seconds_per_token")
        cp = dig(s, "prefillSecondsPerToken", "prefill_seconds_per_token")
        if None in (O, cd, cp) or min(cd, cp) <= 0 or O <= 0:
            continue
        cs = (MB_D / cd) ** 0.75 * (MB_P / cp) ** 0.25
        rows.append({
            "O": O, "cs": cs,
            "lnO": math.log(O), "lncs": math.log(cs), "f": math.log(O / cs),
            "sha": (sdig(s, "submissionCommitSha", "submission_commit_sha",
                         "commitSha") or "")[:8],
            "ts": sdig(s, "createdAt", "created_at", "submittedAt"),
        })
    n = len(rows)
    print(f"receipts: {n}")

    # ---- E1: sd(f) ---------------------------------------------------------
    f = [r["f"] for r in rows]
    lncs = [r["lncs"] for r in rows]
    lnO = [r["lnO"] for r in rows]
    sd_f = sd(f) * 100
    print("\nE1  sd(f)  = %.4f %%   (baseline term only, tree-free)" % sd_f)
    print("    mean f = %+.4f %%" % (mean(f) * 100))

    # ---- E2: cancellation --------------------------------------------------
    mf, mc = mean(f), mean(lncs)
    cov = sum((a - mf) * (b - mc) for a, b in zip(f, lncs)) / (n - 1)
    r_fc = cov / (sd(f) * sd(lncs))
    print("\nE2  ACROSS-FEED correlation of f and ln cs: r = %+.4f" % r_fc)
    print("    (across the feed this is dominated by tree heterogeneity in ln cs,")
    print("     so it BOUNDS rather than measures the within-tree covariance)")
    print("    sd(ln cs) over feed = %.4f %%   sd(ln O) over feed = %.4f %%"
          % (sd(lncs) * 100, sd(lnO) * 100))

    # ---- E3: named replicate sets -----------------------------------------
    print("\nE3  NAMED REPLICATE SETS (Rule 95.3) -- assumption-free ground truth")
    out_sets = {}
    for label, fam in (("family A (4b0e051b et al)", FAMILY_A),
                       ("family B (main-like)", FAMILY_B)):
        got = [r for r in rows if r["sha"] in fam]
        # keep one receipt per sha (a sha can appear once); report all found
        print(f"\n  {label}: matched {len(got)}/{len(fam)}")
        for r in sorted(got, key=lambda r: r["sha"]):
            print("    %s  O %.6f  cs %.6f  f %+.4f %%"
                  % (r["sha"], r["O"], r["cs"], r["f"] * 100))
        if len(got) >= 2:
            s_lnO = sd([r["lnO"] for r in got]) * 100
            s_lncs = sd([r["lncs"] for r in got]) * 100
            s_f = sd([r["f"] for r in got]) * 100
            print("    sd(ln O)  = %.4f %%   <-- within-tree resubmission sigma"
                  % s_lnO)
            print("    sd(ln cs) = %.4f %%   sd(f) = %.4f %%" % (s_lncs, s_f))
            out_sets[label] = {"n": len(got), "sd_lnO_pct": s_lnO,
                               "sd_lncs_pct": s_lncs, "sd_f_pct": s_f}

    # pooled across both families
    pooled_ss, pooled_df = 0.0, 0
    for fam in (FAMILY_A, FAMILY_B):
        got = [r["lnO"] for r in rows if r["sha"] in fam]
        if len(got) >= 2:
            m = mean(got)
            pooled_ss += sum((x - m) ** 2 for x in got)
            pooled_df += len(got) - 1
    pooled = math.sqrt(pooled_ss / pooled_df) * 100 if pooled_df else float("nan")
    print("\n  POOLED within-family sd(ln O) = %.4f %%  (df %d)" % (pooled, pooled_df))

    # ---- pricing under each candidate sigma --------------------------------
    need = 100 * math.log(RECORD / 2.590559)
    print(f"\nPRICING  (need {need:+.4f} %% from cs 2.590559, 18 draws)")
    print("  estimator                       | sigma % |   z   | P/draw % | P(18) %")
    cands = [("E3 pooled within-family", pooled),
             ("E1 sd(f) baseline term", sd_f),
             ("prior published (n=5)", 0.3728),
             ("Rule 95.1 sigma_tot", 0.5546)]
    pricing = {}
    for label, s in cands:
        if s != s:
            continue
        z, p1, p18 = price(need, s)
        print("  %-31s | %7.4f | %5.3f | %8.3f | %7.1f" % (label, s, z, p1, p18))
        pricing[label] = {"sigma_pct": s, "z": z, "p_per_draw_pct": p1,
                          "p_18_pct": p18}

    Path = __import__("pathlib").Path
    Path("research/maple-frieren-r107-sigma-adjudication.json").write_text(
        json.dumps({"n": n, "sd_f_pct": sd_f, "corr_f_lncs": r_fc,
                    "sets": out_sets, "pooled_within_family_sd_lnO_pct": pooled,
                    "pooled_df": pooled_df, "need_pct": need,
                    "pricing": pricing}, indent=2))
    print("\nwrote research/maple-frieren-r107-sigma-adjudication.json")


if __name__ == "__main__":
    main()
