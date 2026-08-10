#!/usr/bin/env python3
"""R106-H Stage C: discharge Rule 93.1 (launch mixing), then re-price the
channel at the corrected receipt rate.

Stage A established the decomposition `ln score = ln cs + ln L` exactly
(max rel err 5.4e-16 over n = 1218) and Stage B priced the record as a lottery.
Rule 93.1 then warned that the `morganmcg1` account is shared by three
launches, so any pooled sigma is a mixture.

Stage C answers that objection with the corpus itself rather than with note
text. The frozen corpus is not our account: it is the whole benchmark, 70
distinct `solverUsername` values over 1218 metric-bearing receipts. Because
`ln L` is a function of the *pinned baseline* run in that session and carries
zero candidate information, every one of those 1218 receipts is a replicate of
the same program. Solver identity is therefore a *stronger* proxy for "launch"
than note text: 70 groups instead of 3, with n = 1218 instead of 84.

Outputs are written as JSON; nothing here touches Sources/ or Vendor/ and no
receipt is spent.
"""
import json
import math
import os
import statistics as st
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from nezuko_r106h_stage_a import (MB_D, MB_P, RECORD, VERIFIED, chi2_ci, load,
                                  norm_sf, sd_ci, t975, ts)

OUT = "research/artifacts/maple-nezuko-r106h/stage-c.json"
CORPUS = "/tmp/r106b/receipt-corpus-frozen.json"

# Rule 93.2: 2.7 receipts/hour is the *account* rate shared by three launches;
# our own share is about 0.9/hour. Rule 88 fixes the serial service time.
OUR_RATE = 0.9
ACCOUNT_RATE = 60.0 / 22.0
DECODE_PCT_PER_US = 0.015228   # % of cs per us/step of decode (state doc)
OUR_ACCOUNT = "morganmcg1"


def wilson(k, n, z=1.959963985):
    if n == 0:
        return [float("nan"), float("nan")]
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return [(c - h) / d, (c + h) / d]


def f_sf(f, d1, d2):
    """Upper tail of the F distribution via the regularised incomplete beta."""
    if f <= 0:
        return 1.0
    x = d2 / (d2 + d1 * f)
    return betainc(d2 / 2.0, d1 / 2.0, x)


def betainc(a, b, x):
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    lbeta = math.lgamma(a) + math.lgamma(b) - math.lgamma(a + b)
    front = math.exp(math.log(x) * a + math.log(1 - x) * b - lbeta) / a
    if x > (a + 1) / (a + b + 2):
        return 1.0 - betainc(b, a, 1 - x)
    f, c, d = 1.0, 1.0, 0.0
    for i in range(0, 300):
        m = i // 2
        if i == 0:
            num = 1.0
        elif i % 2 == 0:
            num = (m * (b - m) * x) / ((a + 2 * m - 1) * (a + 2 * m))
        else:
            num = -((a + m) * (a + b + m) * x) / ((a + 2 * m) * (a + 2 * m + 1))
        d = 1.0 + num * d
        if abs(d) < 1e-30:
            d = 1e-30
        d = 1.0 / d
        c = 1.0 + num / c
        if abs(c) < 1e-30:
            c = 1e-30
        f *= c * d
        if abs(1.0 - c * d) < 1e-12:
            break
    return front * (f - 1.0)


def anova(groups, min_n=2):
    """One-way random-effects ANOVA on {label: [values]}; returns pct units."""
    gs = {k: v for k, v in groups.items() if len(v) >= min_n}
    k = len(gs)
    n = sum(len(v) for v in gs.values())
    if k < 2 or n - k < 1:
        return None
    grand = sum(sum(v) for v in gs.values()) / n
    ssb = sum(len(v) * (st.fmean(v) - grand) ** 2 for v in gs.values())
    ssw = sum(sum((x - st.fmean(v)) ** 2 for x in v) for v in gs.values())
    msb, msw = ssb / (k - 1), ssw / (n - k)
    n0 = (n - sum(len(v) ** 2 for v in gs.values()) / n) / (k - 1)
    var_b = max(0.0, (msb - msw) / n0)
    sw = math.sqrt(msw)
    lo, hi = sd_ci(sw, n - k)
    return {
        "groups": k, "n": n, "F": msb / msw, "df1": k - 1, "df2": n - k,
        "p_F": f_sf(msb / msw, k - 1, n - k),
        "within_sd_pct": sw * 100.0,
        "within_sd_ci_pct": [lo * 100.0, hi * 100.0],
        "between_sd_pct": math.sqrt(var_b) * 100.0,
        "icc": var_b / (var_b + msw) if var_b + msw > 0 else 0.0,
    }


def sd_block(vals, label):
    if len(vals) < 2:
        return {"label": label, "n": len(vals)}
    s = st.stdev(vals)
    lo, hi = sd_ci(s, len(vals) - 1)
    return {"label": label, "n": len(vals), "sd_pct": s * 100.0,
            "sd_ci_pct": [lo * 100.0, hi * 100.0],
            "mean_pct": st.fmean(vals) * 100.0,
            "median_pct": st.median(vals) * 100.0}


def p_semi(lnL, need, sc):
    if sc <= 0:
        return sum(1 for v in lnL if v > need) / len(lnL)
    return sum(norm_sf((need - v) / sc) for v in lnL) / len(lnL)


def main():
    rows = load()
    notes = {}
    for s in json.load(open(CORPUS))["submissions"]:
        notes[s["id"]] = s.get("note") or ""
    for r in rows:
        r["note"] = notes.get(r["id"], "")
    lnL = [r["lnL"] for r in rows]
    res = {"schema": "maple-nezuko-r106h-stage-c/1", "n_receipts": len(rows)}

    # ---- C0: the corpus is the whole benchmark, not our account -------------
    by_user = {}
    for r in rows:
        by_user.setdefault(r["user"], []).append(r)
    res["C0_corpus_scope"] = {
        "n_distinct_solvers": len(by_user),
        "our_account_receipts": len(by_user.get(OUR_ACCOUNT, [])),
        "top_solvers": sorted(((u, len(v)) for u, v in by_user.items()),
                              key=lambda x: -x[1])[:8],
        "note": ("ln L is a function of the pinned baseline run only "
                 "(zero candidate information, verified to 5.4e-16), so all "
                 "1218 receipts replicate the same program"),
    }

    # ---- C1: is the L lottery solver/launch dependent? ----------------------
    c1 = {}
    for key, lab in (("lnL", "ln_L"), ("ln_bl_pre", "ln_bl_pre"),
                     ("ln_bl_dec", "ln_bl_dec")):
        g = {u: [r[key] for r in v] for u, v in by_user.items()}
        c1["anova_by_solver_" + lab] = anova(g, min_n=3)
    c1["sd_lnL_by_cohort"] = [
        sd_block(lnL, "all receipts (n=1218)"),
        sd_block([r["lnL"] for r in by_user.get(OUR_ACCOUNT, [])],
                 "our shared account only"),
        sd_block([r["lnL"] for r in by_user.get("a-github-name", [])],
                 "largest single-solver account a-github-name"),
    ]
    # note-text launch attribution inside our own account (Rule 93.1)
    ours = by_user.get(OUR_ACCOUNT, [])
    launch = {}
    for r in ours:
        nt = r["note"].lower()
        hits = tuple(sorted(k for k in ("maple", "cedar", "birch") if k in nt))
        launch.setdefault("+".join(hits) if hits else "unattributed", []).append(r)
    c1["our_account_note_attribution"] = {k: len(v) for k, v in sorted(launch.items())}
    c1["sd_lnL_by_note_launch"] = [
        sd_block([r["lnL"] for r in v], k) for k, v in sorted(launch.items())
    ]
    c1["anova_lnL_by_note_launch"] = anova(
        {k: [r["lnL"] for r in v] for k, v in launch.items()}, min_n=3)
    # the prefill coin, by cohort
    anti = -0.0003507169434067623
    c1["high_prefill_mode_fraction"] = []
    for lab, sub in (("all", rows), ("our account", ours),
                     ("a-github-name", by_user.get("a-github-name", []))):
        k = sum(1 for r in sub if r["ln_bl_pre"] - math.log(MB_P) > anti)
        c1["high_prefill_mode_fraction"].append(
            {"cohort": lab, "n": len(sub), "k": k,
             "frac": k / len(sub) if sub else float("nan"),
             "ci": wilson(k, len(sub))})
    res["C1_launch_mixing_L_axis"] = c1

    # ---- C2: the cs axis - which receipts back sigma_cs --------------------
    ver = json.load(open(VERIFIED))
    by12 = {}
    for r in rows:
        if r["sha"]:
            by12.setdefault(r["sha"][:12], r)
    c2 = {"verified_groups": [], "n_groups_in_file": len(ver["groups"])}
    for g in ver["groups"]:
        gr = [by12[s] for s in g.get("shas", []) if s in by12]
        if not gr:
            continue
        c2["verified_groups"].append({
            "group": g["group"],
            "verified_inert_only": bool(g.get("verified_inert_only")),
            "n_in_group": g.get("n"),
            "n_matched_in_corpus": len(gr),
            "solvers": sorted(set(r["user"] for r in gr)),
            "all_ours": all(r["user"] == OUR_ACCOUNT for r in gr),
        })
    ver_ours = [g for g in c2["verified_groups"]
                if g["verified_inert_only"] and g["all_ours"]]
    c2["n_verified_groups_all_ours"] = len(ver_ours)
    c2["n_verified_groups"] = sum(
        1 for g in c2["verified_groups"] if g["verified_inert_only"])
    c2["conclusion"] = (
        "sigma_cs is estimated only from tree-identical receipts, and every "
        "verified group is entirely our own account, so that estimate is "
        "launch-clean by construction; Rule 93.1's mixture worry does not "
        "reach the cs axis"
        if c2["n_verified_groups_all_ours"] == c2["n_verified_groups"] else
        "WARNING: at least one verified group mixes solver accounts; "
        "sigma_cs may itself be a mixture")
    res["C2_cs_axis_provenance"] = c2

    # ---- C3: sigma-parameterised P(record) / E[draws] / wall clock ---------
    lnR = math.log(RECORD)
    sc_pt, sc_lo, sc_hi = 0.001833592904341719, 0.0012811619060010068, 0.0032178335912329004
    ladder = [
        ("observed max cs of our best tree (order statistic, n=5)", 2.590559143419936, 1),
        ("unbiased merit of that same tree (n=5 mean)", 2.583111139942713, 5),
        ("merged frontier bd33883e", 2.582286, 1),
        ("unbiased best + 0.10 % of cs", 2.583111139942713 * math.exp(0.0010), 5),
        ("unbiased best + 0.25 % of cs", 2.583111139942713 * math.exp(0.0025), 5),
        ("unbiased best + 0.50 % of cs", 2.583111139942713 * math.exp(0.0050), 5),
        ("unbiased best + 1.00 % of cs", 2.583111139942713 * math.exp(0.0100), 5),
    ]
    c3 = []
    for lab, cs, nobs in ladder:
        need = lnR - math.log(cs)
        k = sum(1 for v in lnL if v > need)
        row = {"label": lab, "cs": cs, "need_lnL_pct": need * 100.0,
               "empirical": {"k": k, "n": len(lnL), "p": k / len(lnL),
                             "ci": wilson(k, len(lnL))},
               "sigma_variants": {}}
        for tag, sc in (("point", sc_pt), ("lo", sc_lo), ("hi", sc_hi)):
            # predictive sd for a fresh draw of a tree whose merit is known
            # from nobs receipts; the known-merit variant drops that estimation
            # term so the ladder stays monotone in merit
            spred = sc * math.sqrt(1.0 + 1.0 / nobs)
            p = p_semi(lnL, need, spred)
            pk = p_semi(lnL, need, sc)
            row["sigma_variants"][tag] = {
                "sigma_cs_pct": sc * 100.0,
                "sigma_predictive_pct": spred * 100.0,
                "p_draw": p,
                "p_draw_known_merit": pk,
                "expected_draws": (1.0 / p) if p > 0 else float("inf"),
                "expected_draws_known_merit": (1.0 / pk) if pk > 0 else float("inf"),
                "hours_our_rate": (1.0 / p / OUR_RATE) if p > 0 else float("inf"),
                "hours_account_rate": (1.0 / p / ACCOUNT_RATE) if p > 0 else float("inf"),
                "cum_p_10_draws": 1 - (1 - p) ** 10,
                "cum_p_30_draws": 1 - (1 - p) ** 30,
            }
        c3.append(row)
    res["C3_record_ladder"] = c3

    # ---- C4: exchange rate Y ----------------------------------------------
    def cum(p, k):
        return 1 - (1 - p) ** k

    def merit_worth_one_draw(cs0, nobs, kbudget, sc):
        spred = sc * math.sqrt(1.0 + 1.0 / nobs)
        base = cum(p_semi(lnL, lnR - math.log(cs0), spred), kbudget)
        target = cum(p_semi(lnL, lnR - math.log(cs0), spred), kbudget + 1)
        lo, hi = 0.0, 0.06
        for _ in range(70):
            mid = 0.5 * (lo + hi)
            cur = cum(p_semi(lnL, lnR - math.log(cs0) - mid, spred), kbudget)
            if cur < target:
                lo = mid
            else:
                hi = mid
        return 0.5 * (lo + hi), base, target

    c4 = {"basis": "unbiased merit of the best tree, cs 2.583111, n=5",
          "per_budget": {}}
    for kb in (4, 10, 20, 40, 80):
        d, b, t = merit_worth_one_draw(2.583111139942713, 5, kb, sc_pt)
        c4["per_budget"][str(kb)] = {
            "pct_of_cs": d * 100.0,
            "us_per_step": d * 100.0 / DECODE_PCT_PER_US,
            "cum_p_at_k": b, "cum_p_at_k_plus_1": t}
    c4["inverse_mechanism_to_draws"] = {}
    for lab, pct in (("+0.10 % of cs (6.6 us/step)", 0.10),
                     ("+0.25 % of cs (16.4 us/step)", 0.25),
                     ("+0.50 % of cs (32.8 us/step)", 0.50),
                     ("Rule 91 whole 19.0 us/step revert residual", 0.3204),
                     ("Rule 92 dispatch-reorder ceiling 1.30 us/step", 0.0198),
                     ("#619 redundant-read + fusion ceiling 0.231 %", 0.231),
                     ("#617 + #619 closed-decode ceilings combined", 0.2508),
                     ("Rule 94.1 prefill gap, 9.3 % of score", 9.3)):
        m = pct / 100.0
        spred = sc_pt * math.sqrt(1.2)
        p0 = p_semi(lnL, lnR - math.log(2.583111139942713), spred)
        p1 = p_semi(lnL, lnR - math.log(2.583111139942713) - m, spred)
        # draws k such that cum(p0,k) == cum(p1,1); a gain that puts every
        # empirical draw over the bar makes one draw certain and r unbounded
        kd = (math.log(1 - p1) / math.log(1 - p0)) if p1 < 1.0 - 1e-12 else None
        c4["inverse_mechanism_to_draws"][lab] = {
            "pct_of_cs": pct, "p_without": p0, "p_with": p1,
            "draws_multiplier": kd,
            "extra_draws_at_budget_10": None if kd is None else (kd - 1.0) * 10.0,
            "extra_draws_at_budget_20": None if kd is None else (kd - 1.0) * 20.0,
            "extra_hours_at_budget_20_our_rate":
                None if kd is None else (kd - 1.0) * 20.0 / OUR_RATE}
    c4["multiplier_note"] = (
        "cum(p1,k) = cum(p0, k*r) exactly, with r = ln(1-p1)/ln(1-p0), so a "
        "permanent merit gain multiplies the effective draw count by r at any "
        "budget; r is the budget-free statement and (r-1)*k is the extra-draw "
        "statement at budget k")
    res["C4_exchange_rate"] = c4

    # ---- C7: the tree-selection rule ---------------------------------------
    spred1 = sc_pt * math.sqrt(2.0)      # a fresh tree with one receipt
    best_cs = 2.583111139942713
    c7 = {"basis": ("ticket value of drawing from a tree whose merit is delta "
                    "below the best known tree; r < 1 means the draw is worth "
                    "less than a repeat of the best tree"),
          "sigma_cs_pct": sc_pt * 100.0,
          "rows": []}
    p_best = p_semi(lnL, lnR - math.log(best_cs), spred1)
    for dpct in (0.0, 0.02, 0.05, 0.10, 0.20, 0.50, 1.00):
        d = dpct / 100.0
        p2 = p_semi(lnL, lnR - math.log(best_cs) + d, spred1)
        r = (math.log(1 - p2) / math.log(1 - p_best)) if 0 < p2 < 1 else 0.0
        c7["rows"].append({
            "merit_deficit_pct_of_cs": dpct,
            "merit_deficit_us_per_step": dpct / DECODE_PCT_PER_US,
            "p_draw": p2, "ticket_value_ratio": r,
            "n_receipts_to_resolve_this_deficit_per_arm":
                (2.0 * (1.959963985 * sc_pt / d) ** 2) if d > 0 else float("inf")})
    c7["rule"] = (
        "Draw from the single highest-merit buildable tree. A second tree is "
        "only worth a draw when its merit deficit is inside the resolution "
        "floor of sigma_cs, and sigma_cs is 0.183 % of cs, so any deficit we "
        "can actually measure with a handful of receipts already costs more "
        "ticket value than diversification buys.")
    res["C7_tree_selection"] = c7

    # ---- C5: the prefill coin ---------------------------------------------
    hi_mode = [r for r in rows if r["ln_bl_pre"] - math.log(MB_P) > anti]
    lo_mode = [r for r in rows if r["ln_bl_pre"] - math.log(MB_P) <= anti]
    need_best = lnR - math.log(2.590559143419936)
    need_unb = lnR - math.log(2.583111139942713)
    c5 = {"antimode_pct_vs_MB_P": anti * 100.0}
    for lab, sub in (("high", hi_mode), ("low", lo_mode)):
        kb = sum(1 for r in sub if r["lnL"] > need_best)
        ku = sum(1 for r in sub if r["lnL"] > need_unb)
        c5[lab + "_mode"] = {
            "n": len(sub),
            "mean_ln_bl_pre_pct": st.fmean(r["ln_bl_pre"] - math.log(MB_P) for r in sub) * 100.0,
            "mean_lnL_pct": st.fmean(r["lnL"] for r in sub) * 100.0,
            "sd_lnL_pct": st.stdev([r["lnL"] for r in sub]) * 100.0,
            "winners_vs_observed_max": {"k": kb, "p": kb / len(sub),
                                        "ci": wilson(kb, len(sub))},
            "winners_vs_unbiased": {"k": ku, "p": ku / len(sub),
                                    "ci": wilson(ku, len(sub))},
        }
    c5["coin_value_pct_of_score"] = (
        c5["high_mode"]["mean_lnL_pct"] - c5["low_mode"]["mean_lnL_pct"])
    c5["coin_value_us_per_step_decode_equiv"] = (
        c5["coin_value_pct_of_score"] / DECODE_PCT_PER_US)
    res["C5_prefill_coin"] = c5

    # ---- C6: what actually holds the record, and is it in the corpus? ------
    best = max(rows, key=lambda r: r["score"])
    c6 = {"record_score_from_state_doc": RECORD,
          "record_sha_cc6ddc12_in_corpus": any(
              (r["sha"] or "").startswith("cc6ddc12") for r in rows),
          "max_score_receipt_in_corpus": {
              "sha12": (best["sha"] or "")[:12], "user": best["user"],
              "createdAt": best["createdAt"], "score": best["score"],
              "cs": best["cs"], "lnL_pct": best["lnL"] * 100.0},
          "n_corpus_receipts_at_or_above_record": sum(
              1 for r in rows if r["score"] >= RECORD)}
    top = sorted(rows, key=lambda r: -r["score"])[:5]
    c6["top5"] = [{"sha12": (r["sha"] or "")[:12], "user": r["user"],
                   "score": r["score"], "cs": r["cs"],
                   "lnL_pct": r["lnL"] * 100.0} for r in top]
    res["C6_record_provenance"] = c6

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    if os.path.exists(OUT):
        os.remove(OUT)
    with open(OUT, "w") as fh:
        json.dump(res, fh, indent=1, sort_keys=True)
    print("wrote", OUT)
    print(json.dumps(res["C1_launch_mixing_L_axis"]["anova_by_solver_ln_L"], indent=1))
    print(json.dumps(res["C1_launch_mixing_L_axis"]["sd_lnL_by_cohort"], indent=1))
    print(json.dumps(res["C6_record_provenance"], indent=1))


if __name__ == "__main__":
    main()
