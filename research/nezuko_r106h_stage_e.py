#!/usr/bin/env python3
"""R106-H Stage E — verify Rule 96 ("the lottery is dead") against the corpus.

Rule 96 was published at 2026-08-10T10:40Z on the advisor branch, after Stages
A-D of this report were computed.  It reaches the opposite policy conclusion to
Stage B from a within-tree n=5 replicate set.  Its three load-bearing numbers
are the shrunk anchor (cs 2.583106), the paired decision denominator
(sd(ln officialScore | fixed tree) = 0.3728 %, from rho(ln cs, f) = -0.7920),
and a model-free cohort test (27 receipts at cs >= the shrunk anchor, zero
records, sd(f) = 0.3687 %).

Stage E re-derives each of them from the frozen 1218-receipt corpus and from
the five byte-verified identical-tree groups (dof 10) established in R106-B,
and tests the one structural fact Rule 96 does not use: baseline prefill is
bimodal (Stage A, A9), so a within-tree sd of the baseline prefill leg is a
mixture statistic, not a Gaussian sigma.

Usage: nezuko_r106h_stage_e.py [OUT_JSON]
"""
import json
import math
import statistics as st
import sys

from nezuko_r106h_stage_a import (VERIFIED, chi2_ci, load, mad_sd,
                                  rel_se_of_sd, norm_sf, sd_ci, ts)

RECORD_SCORE = 2.61650354381456
FRIEREN_ANCHOR = 2.583106
OUR_RATE_PER_HOUR = 0.9
US_STEP_PER_PERCENT_CS = 65.67

# Rule 96's own figures, quoted so the report can diff against them.
R96 = {
    "anchor_cs": 2.583106,
    "selection_bias_pct": 0.2881,
    "sd_ln_cs_within_tree_pct": 0.2276,
    "sd_f_within_tree_pct": 0.5263,
    "rho_ln_cs_f": -0.7920,
    "sd_ln_score_within_tree_pct": 0.3728,
    "leg_sd_cand_dec_pct": 0.2938,
    "leg_sd_cand_pre_pct": 0.1027,
    "leg_sd_bl_dec_pct": 0.1471,
    "leg_sd_bl_pre_pct": 2.1725,
    "leg_F_4_4": 447.5,
    "gap_pct": 1.2846,
    "p_record_per_draw_pct": 0.0285,
    "expected_draws": 3510,
    "cohort_n": 27,
    "cohort_records": 0,
    "cohort_max_f_pct": 0.612,
    "cohort_mean_f_pct": -0.179,
    "cohort_sd_f_pct": 0.369,
    "cohort_p_max_le_observed": 0.0253,
    "paired_resolvable_cs_pct": 0.228,
}


def pearson(xs, ys):
    n = len(xs)
    mx, my = st.mean(xs), st.mean(ys)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx <= 0 or syy <= 0:
        return None
    return sxy / math.sqrt(sxx * syy)


def fisher_ci(r, n):
    """Fisher-z 95 % interval for a correlation."""
    if n < 4 or r is None or abs(r) >= 1:
        return None
    z = 0.5 * math.log((1 + r) / (1 - r))
    se = 1.0 / math.sqrt(n - 3)
    lo, hi = z - 1.96 * se, z + 1.96 * se
    return [math.tanh(lo), math.tanh(hi)]


def pooled_within(groups):
    """Pool centred sums of squares across groups. groups: list of lists."""
    ss = 0.0
    dof = 0
    for g in groups:
        if len(g) < 2:
            continue
        m = st.mean(g)
        ss += sum((v - m) ** 2 for v in g)
        dof += len(g) - 1
    if dof == 0:
        return None, 0
    return math.sqrt(ss / dof), dof


def pooled_within_cov(pairs):
    """Pooled within-group covariance and correlation. pairs: list of (xs, ys)."""
    sxy = sxx = syy = 0.0
    dof = 0
    for xs, ys in pairs:
        if len(xs) < 2:
            continue
        mx, my = st.mean(xs), st.mean(ys)
        sxy += sum((x - mx) * (y - my) for x, y in zip(xs, ys))
        sxx += sum((x - mx) ** 2 for x in xs)
        syy += sum((y - my) ** 2 for y in ys)
        dof += len(xs) - 1
    if dof == 0 or sxx <= 0 or syy <= 0:
        return None
    return {
        "dof": dof,
        "sd_x_pct": math.sqrt(sxx / dof),
        "sd_y_pct": math.sqrt(syy / dof),
        "cov_pct2": sxy / dof,
        "rho": sxy / math.sqrt(sxx * syy),
    }


def f_sf(f, d1, d2):
    """Upper tail of the F distribution, by continued-fraction incomplete beta."""
    if f <= 0:
        return 1.0
    x = d2 / (d2 + d1 * f)
    return betainc(d2 / 2.0, d1 / 2.0, x)


def betainc(a, b, x):
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    lbeta = (math.lgamma(a) + math.lgamma(b) - math.lgamma(a + b))
    front = math.exp(a * math.log(x) + b * math.log(1 - x) - lbeta)
    if x < (a + 1) / (a + b + 2):
        return front * _cf(a, b, x) / a
    return 1.0 - math.exp(b * math.log(1 - x) + a * math.log(x) - lbeta) * \
        _cf(b, a, 1 - x) / b


def _cf(a, b, x):
    tiny = 1e-30
    c, d = 1.0, 1.0 - (a + b) * x / (a + 1.0)
    if abs(d) < tiny:
        d = tiny
    d = 1.0 / d
    h = d
    for m in range(1, 300):
        m2 = 2 * m
        num = m * (b - m) * x / ((a + m2 - 1.0) * (a + m2))
        d = 1.0 + num * d
        if abs(d) < tiny:
            d = tiny
        c = 1.0 + num / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        h *= d * c
        num = -(a + m) * (a + b + m) * x / ((a + m2) * (a + m2 + 1.0))
        d = 1.0 + num * d
        if abs(d) < tiny:
            d = tiny
        c = 1.0 + num / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 1e-12:
            break
    return h


def wilson(k, n):
    if n == 0:
        return [0.0, 1.0]
    p = k / n
    z = 1.959964
    den = 1 + z * z / n
    ctr = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return [max(0.0, ctr - half), min(1.0, ctr + half)]


def load_groups(rows):
    """The five byte-verified identical-tree groups from R106-B (dof 10)."""
    ver = json.load(open(VERIFIED))
    by_sha = {}
    for r in rows:
        if r["sha"]:
            by_sha[r["sha"][:12]] = r
    out = {}
    for g in ver["groups"]:
        if not g.get("verified_inert_only"):
            continue
        key = g["group"]
        members = []
        for sha12 in g["shas"]:
            r = by_sha.get(sha12[:12])
            if r:
                members.append(r)
        if len(members) >= 2:
            members.sort(key=lambda r: r["t"])
            out[key] = members
    return out


def main(out_path):
    rows = load()
    groups = load_groups(rows)
    res = {"schema": "maple-nezuko-r106h-stage-e/1", "n_receipts": len(rows),
           "rule_96_quoted": R96}

    ln_record = math.log(RECORD_SCORE)

    # ---------------------------------------------------------------- E1
    # Winner's curse on the one five-member family, independently of frieren's
    # note key: our key is a byte digest of the submitted surface.
    print("== E1 winner's curse on the five-member family ==")
    e1 = {}
    for key, members in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        css = [r["cs"] for r in members]
        mx = max(css)
        gmean = math.exp(st.mean([math.log(c) for c in css]))
        e1[key] = {
            "n": len(members),
            "max_cs": mx,
            "geo_mean_cs": gmean,
            "selection_bias_pct": 100.0 * math.log(mx / gmean),
            "se_of_mean_pct": (100.0 * st.stdev([math.log(c) for c in css])
                               / math.sqrt(len(css)) if len(css) > 2 else None),
            "members": [{"sha12": r["sha"][:12], "cs": r["cs"],
                         "ts": r["createdAt"], "user": r["user"]}
                        for r in members],
        }
        print(f"  {key:34s} n={len(members)}  max {mx:.6f}  "
              f"gmean {gmean:.6f}  bias {e1[key]['selection_bias_pct']:+.4f} %")
    five = [k for k, v in e1.items() if v["n"] == 5]
    res["E1_winners_curse"] = {
        "groups": e1,
        "five_member_group": five[0] if five else None,
        "rule_96_anchor_cs": R96["anchor_cs"],
        "our_anchor_cs": e1[five[0]]["geo_mean_cs"] if five else None,
        "anchor_agreement_pct": (100.0 * math.log(e1[five[0]]["geo_mean_cs"]
                                                  / R96["anchor_cs"])
                                 if five else None),
    }
    if five:
        print(f"  Rule 96 anchor {R96['anchor_cs']:.6f} vs ours "
              f"{e1[five[0]]['geo_mean_cs']:.6f}  "
              f"({res['E1_winners_curse']['anchor_agreement_pct']:+.5f} %)")

    # ---------------------------------------------------------------- E2
    # The paired decision denominator: sd(ln score | fixed tree).
    print("\n== E2 within-tree decision denominator ==")
    e2 = {"per_group": {}}
    pairs = []
    for key, members in sorted(groups.items()):
        lncs = [100.0 * math.log(r["cs"]) for r in members]
        lnL = [100.0 * r["lnL"] for r in members]
        lnS = [100.0 * math.log(r["score"]) for r in members]
        pairs.append((lncs, lnL))
        row = {
            "n": len(members),
            "sd_ln_cs_pct": st.stdev(lncs) if len(members) > 1 else None,
            "sd_f_pct": st.stdev(lnL) if len(members) > 1 else None,
            "sd_ln_score_pct": st.stdev(lnS) if len(members) > 1 else None,
            "rho_ln_cs_f": pearson(lncs, lnL) if len(members) > 2 else None,
        }
        if len(members) > 3:
            row["rho_ci"] = fisher_ci(row["rho_ln_cs_f"], len(members))
        e2["per_group"][key] = row
        print(f"  {key:34s} n={len(members)}  sd(ln cs) {row['sd_ln_cs_pct'] or 0:.4f} "
              f" sd(f) {row['sd_f_pct'] or 0:.4f}  sd(ln S) "
              f"{row['sd_ln_score_pct'] or 0:.4f}  rho "
              f"{row['rho_ln_cs_f'] if row['rho_ln_cs_f'] is not None else float('nan'):+.4f}")

    pw = pooled_within_cov(pairs)
    sd_S, dof_S = pooled_within([[100.0 * math.log(r["score"]) for r in m]
                                 for m in groups.values()])
    recon = math.sqrt(pw["sd_x_pct"] ** 2 + pw["sd_y_pct"] ** 2
                      + 2 * pw["cov_pct2"])
    e2["pooled"] = {
        "dof": pw["dof"],
        "sd_ln_cs_pct": pw["sd_x_pct"],
        "sd_ln_cs_ci_pct": sd_ci(pw["sd_x_pct"], pw["dof"]),
        "sd_f_pct": pw["sd_y_pct"],
        "sd_f_ci_pct": sd_ci(pw["sd_y_pct"], pw["dof"]),
        "cov_pct2": pw["cov_pct2"],
        "rho_ln_cs_f": pw["rho"],
        "rho_ci": fisher_ci(pw["rho"], pw["dof"] + 1),
        "sd_ln_score_direct_pct": sd_S,
        "sd_ln_score_dof": dof_S,
        "sd_ln_score_reconstructed_pct": recon,
        "rel_residual": recon / sd_S - 1.0 if sd_S else None,
        "rel_se_of_sd_pct": 100.0 * rel_se_of_sd(pw["dof"] + 1),
    }
    print(f"  pooled dof {pw['dof']}: sd(ln cs) {pw['sd_x_pct']:.4f} %  "
          f"sd(f) {pw['sd_y_pct']:.4f} %  rho {pw['rho']:+.4f} "
          f"{e2['pooled']['rho_ci']}")
    print(f"  sd(ln score | tree) = {sd_S:.4f} % [{sd_ci(sd_S, dof_S)[0]:.4f}, "
          f"{sd_ci(sd_S, dof_S)[1]:.4f}]  vs Rule 96's "
          f"{R96['sd_ln_score_within_tree_pct']:.4f} %")

    # Frieren's own group in isolation, so the comparison is like-for-like.
    if five:
        m5 = groups[five[0]]
        lncs = [100.0 * math.log(r["cs"]) for r in m5]
        lnL = [100.0 * r["lnL"] for r in m5]
        lnS = [100.0 * math.log(r["score"]) for r in m5]
        e2["five_member_group_only"] = {
            "n": 5, "dof": 4,
            "sd_ln_cs_pct": st.stdev(lncs),
            "sd_f_pct": st.stdev(lnL),
            "sd_ln_score_pct": st.stdev(lnS),
            "sd_ln_score_ci_pct": sd_ci(st.stdev(lnS), 4),
            "rho_ln_cs_f": pearson(lncs, lnL),
            "rho_ci": fisher_ci(pearson(lncs, lnL), 5),
            "rho_t_stat": None,
        }
        r = e2["five_member_group_only"]["rho_ln_cs_f"]
        e2["five_member_group_only"]["rho_t_stat"] = (
            r * math.sqrt(3) / math.sqrt(1 - r * r))
        print(f"  five-member group alone: sd(ln cs) {st.stdev(lncs):.4f}  "
              f"sd(f) {st.stdev(lnL):.4f}  sd(ln S) {st.stdev(lnS):.4f}  "
              f"rho {r:+.4f} (t={e2['five_member_group_only']['rho_t_stat']:+.3f}, dof 3)")
    res["E2_paired_denominator"] = e2

    # ---------------------------------------------------------------- E3
    # Per-leg dispersion inside a fixed tree.
    print("\n== E3 per-leg dispersion inside a fixed tree ==")
    legs = {"cand_dec": "ln_dec", "cand_pre": "ln_pre",
            "bl_dec": "ln_bl_dec", "bl_pre": "ln_bl_pre"}
    e3 = {"pooled": {}, "five_member_group_only": {}}
    for name, fld in legs.items():
        sd, dof = pooled_within([[100.0 * r[fld] for r in m]
                                 for m in groups.values()])
        e3["pooled"][name] = {"sd_pct": sd, "dof": dof,
                              "ci_pct": sd_ci(sd, dof)}
        print(f"  pooled {name:9s} sd {sd:.4f} % (dof {dof}) "
              f"{[round(v, 4) for v in sd_ci(sd, dof)]}")
    if five:
        for name, fld in legs.items():
            vals = [100.0 * r[fld] for r in groups[five[0]]]
            e3["five_member_group_only"][name] = {
                "sd_pct": st.stdev(vals), "dof": 4,
                "ci_pct": sd_ci(st.stdev(vals), 4),
                "rule_96_pct": R96[f"leg_sd_{name}_pct"],
            }
            print(f"  n=5    {name:9s} sd {st.stdev(vals):.4f} %  "
                  f"(Rule 96: {R96[f'leg_sd_{name}_pct']:.4f} %)")
        a = e3["five_member_group_only"]["bl_pre"]["sd_pct"]
        b = e3["five_member_group_only"]["cand_pre"]["sd_pct"]
        F = (a / b) ** 2
        e3["bl_pre_vs_cand_pre_F"] = {
            "F": F, "df": [4, 4], "p_one_sided": f_sf(F, 4, 4),
            "rule_96_F": R96["leg_F_4_4"],
        }
        print(f"  F(bl_pre/cand_pre) = {F:.1f} (dof 4,4) p={f_sf(F, 4, 4):.2e} "
              f"vs Rule 96's {R96['leg_F_4_4']}")
    res["E3_per_leg"] = e3

    # ---------------------------------------------------------------- E4
    # Is that 2.17 % baseline-prefill sd a Gaussian sigma, or the A9 coin?
    print("\n== E4 the within-tree baseline-prefill sd is the A9 coin ==")
    MB_P = 0.000372473193
    pre_pct = sorted(100.0 * math.log(r["bl_pre"] / MB_P) for r in rows)
    # Re-locate the antimode exactly as Stage A A9 did: widest central gap.
    lo_i = int(0.15 * len(pre_pct))
    hi_i = int(0.85 * len(pre_pct))
    best = (0.0, None)
    for i in range(lo_i, hi_i):
        gap = pre_pct[i + 1] - pre_pct[i]
        if gap > best[0]:
            best = (gap, 0.5 * (pre_pct[i] + pre_pct[i + 1]))
    cut = best[1]
    for r in rows:
        r["bl_pre_pct"] = 100.0 * math.log(r["bl_pre"] / MB_P)
        r["mode"] = "high" if r["bl_pre_pct"] > cut else "low"
    e4 = {"antimode_pct": cut, "widest_central_gap_pct": best[0],
          "corpus_high_fraction": sum(1 for r in rows if r["mode"] == "high")
          / len(rows), "per_group": {}}
    straddle = 0
    within_mode = []
    for key, members in sorted(groups.items()):
        modes = [r["mode"] for r in members]
        nh = modes.count("high")
        e4["per_group"][key] = {
            "n": len(members), "n_high": nh, "n_low": len(members) - nh,
            "straddles": 0 < nh < len(members),
            "sd_bl_pre_pct": st.stdev([r["bl_pre_pct"] for r in members]),
            "members": [{"sha12": r["sha"][:12], "mode": r["mode"],
                         "bl_pre_pct": r["bl_pre_pct"],
                         "lnL_pct": 100.0 * r["lnL"]} for r in members],
        }
        if 0 < nh < len(members):
            straddle += 1
        for m in ("high", "low"):
            sub = [r["bl_pre_pct"] for r in members if r["mode"] == m]
            if len(sub) > 1:
                within_mode.append(sub)
        print(f"  {key:34s} n={len(members)} high={nh} low={len(members)-nh}"
              f"  sd(bl_pre) {e4['per_group'][key]['sd_bl_pre_pct']:.4f} %"
              f"{'  <-- STRADDLES' if 0 < nh < len(members) else ''}")
    sd_wm, dof_wm = pooled_within(within_mode)
    sd_all, dof_all = pooled_within([[r["bl_pre_pct"] for r in m]
                                     for m in groups.values()])
    e4["n_groups_straddling"] = straddle
    e4["n_groups"] = len(groups)
    e4["pooled_sd_bl_pre_all_pct"] = sd_all
    e4["pooled_sd_bl_pre_all_dof"] = dof_all
    e4["pooled_sd_bl_pre_within_mode_pct"] = sd_wm
    e4["pooled_sd_bl_pre_within_mode_dof"] = dof_wm
    e4["variance_share_from_mode_coin"] = (
        1.0 - (sd_wm ** 2 / sd_all ** 2) if sd_wm and sd_all else None)
    print(f"  pooled sd(bl_pre | tree)          = {sd_all:.4f} % (dof {dof_all})")
    if sd_wm:
        print(f"  pooled sd(bl_pre | tree AND mode) = {sd_wm:.4f} % (dof {dof_wm})"
              f"  => the coin carries "
              f"{100 * e4['variance_share_from_mode_coin']:.1f} % of it")
    # And the same for f itself, which is what the lottery pays out in.
    sd_f_all, dof_f_all = pooled_within([[100.0 * r["lnL"] for r in m]
                                         for m in groups.values()])
    f_wm = []
    for members in groups.values():
        for m in ("high", "low"):
            sub = [100.0 * r["lnL"] for r in members if r["mode"] == m]
            if len(sub) > 1:
                f_wm.append(sub)
    sd_f_wm, dof_f_wm = pooled_within(f_wm)
    e4["pooled_sd_f_all_pct"] = sd_f_all
    e4["pooled_sd_f_within_mode_pct"] = sd_f_wm
    e4["pooled_sd_f_within_mode_dof"] = dof_f_wm
    print(f"  pooled sd(f | tree) {sd_f_all:.4f} %  ->  "
          f"sd(f | tree AND mode) {sd_f_wm:.4f} % (dof {dof_f_wm})")
    res["E4_mode_coin"] = e4

    # ---------------------------------------------------------------- E5
    # The model-free cohort test, re-run on our corpus.
    print("\n== E5 the top-cs cohort ==")
    e5 = {}
    for label, thresh in (("rule_96_anchor", FRIEREN_ANCHOR),
                          ("our_anchor", res["E1_winners_curse"]["our_anchor_cs"]
                           or FRIEREN_ANCHOR),
                          ("selected_max", 2.590559)):
        coh = [r for r in rows if r["cs"] >= thresh]
        if len(coh) < 2:
            e5[label] = {"threshold_cs": thresh, "n": len(coh)}
            continue
        fs = [100.0 * r["lnL"] for r in coh]
        need = [100.0 * (ln_record - math.log(r["cs"])) for r in coh]
        recs = [r for r in coh if r["score"] >= RECORD_SCORE]
        sd = st.stdev(fs)
        e5[label] = {
            "threshold_cs": thresh, "n": len(coh),
            "n_records": len(recs),
            "records": [r["sha"][:12] for r in recs],
            "max_f_pct": max(fs), "mean_f_pct": st.mean(fs),
            "sd_f_pct": sd, "sd_f_ci_pct": sd_ci(sd, len(coh) - 1),
            "mad_sd_f_pct": mad_sd(fs),
            "need_f_min_pct": min(need), "need_f_median_pct": st.median(need),
            "need_f_max_pct": max(need),
            "high_mode_fraction": sum(1 for r in coh if r["mode"] == "high")
            / len(coh),
            "n_distinct_users": len({r["user"] for r in coh}),
            "ours_n": sum(1 for r in coh if r["user"] == "morganmcg1"),
        }
        print(f"  cs >= {thresh:.6f}: n={len(coh)}  records={len(recs)}  "
              f"max f {max(fs):+.4f} %  mean {st.mean(fs):+.4f} %  "
              f"sd {sd:.4f} % {[round(v, 4) for v in sd_ci(sd, len(coh)-1)]}")
        print(f"      need f in [{min(need):+.4f}, {max(need):+.4f}] "
              f"median {st.median(need):+.4f} %  high-mode frac "
              f"{e5[label]['high_mode_fraction']:.3f}")
    # Is the cohort's lower sd(f) a truncation artefact of rho < 0?
    lncs_all = [100.0 * math.log(r["cs"]) for r in rows]
    f_all = [100.0 * r["lnL"] for r in rows]
    rho_corpus = pearson(lncs_all, f_all)
    sd_f_corpus = st.stdev(f_all)
    e5["corpus_rho_ln_cs_f"] = rho_corpus
    e5["corpus_rho_ci"] = fisher_ci(rho_corpus, len(rows))
    e5["corpus_sd_f_pct"] = sd_f_corpus
    e5["conditional_sd_f_if_rho_pct"] = sd_f_corpus * math.sqrt(
        1 - rho_corpus ** 2)
    e5["conditional_sd_f_if_rho_96_pct"] = sd_f_corpus * math.sqrt(
        1 - R96["rho_ln_cs_f"] ** 2)
    print(f"  corpus rho(ln cs, f) = {rho_corpus:+.4f} "
          f"{[round(v, 4) for v in e5['corpus_rho_ci']]}; a rho of "
          f"{R96['rho_ln_cs_f']} would shrink sd(f) to "
          f"{e5['conditional_sd_f_if_rho_96_pct']:.4f} %")
    res["E5_cohort"] = e5

    # ---------------------------------------------------------------- E6
    # Is a large f actually available to a good tree?
    print("\n== E6 is a large payout available to a good tree ==")
    anchor = res["E1_winners_curse"]["our_anchor_cs"] or FRIEREN_ANCHOR
    need_anchor = 100.0 * (ln_record - math.log(anchor))
    big = [r for r in rows if 100.0 * r["lnL"] >= need_anchor]
    e6 = {
        "anchor_cs": anchor, "need_f_pct": need_anchor,
        "n_receipts_with_f_at_least_need": len(big),
        "empirical_p": len(big) / len(rows),
        "empirical_ci": wilson(len(big), len(rows)),
        "big_f_receipts": [{"sha12": (r["sha"] or "")[:12], "cs": r["cs"],
                            "f_pct": 100.0 * r["lnL"], "score": r["score"],
                            "user": r["user"], "mode": r["mode"],
                            "ts": r["createdAt"]}
                           for r in sorted(big, key=lambda r: -r["lnL"])],
        "max_cs_among_big_f": max((r["cs"] for r in big), default=None),
        "n_big_f_above_anchor": sum(1 for r in big if r["cs"] >= anchor),
    }
    print(f"  need f >= {need_anchor:+.4f} % from cs {anchor:.6f}: "
          f"{len(big)}/{len(rows)} receipts cleared it "
          f"({100 * len(big) / len(rows):.2f} %)")
    print(f"  of those, {e6['n_big_f_above_anchor']} were on a tree at or above "
          f"the anchor; best tree among them cs "
          f"{e6['max_cs_among_big_f']:.6f}")
    # 2x2 independence table on the two events the record needs jointly.
    good = [r for r in rows if r["cs"] >= anchor]
    lucky = [r for r in rows if 100.0 * r["lnL"] >= need_anchor]
    both = [r for r in rows if r["cs"] >= anchor
            and 100.0 * r["lnL"] >= need_anchor]
    e6["two_by_two"] = {
        "n": len(rows), "n_good_tree": len(good), "n_lucky_session": len(lucky),
        "n_both": len(both),
        "expected_both_if_independent": len(good) * len(lucky) / len(rows),
        "n_record": sum(1 for r in rows if r["score"] >= RECORD_SCORE),
    }
    print(f"  2x2: good {len(good)}  lucky {len(lucky)}  both {len(both)}  "
          f"(expected under independence "
          f"{e6['two_by_two']['expected_both_if_independent']:.3f})")
    res["E6_joint"] = e6

    # ---------------------------------------------------------------- E7
    # P(record)/draw at the shrunk anchor, five ways.
    print("\n== E7 P(record)/draw at the shrunk anchor, five ways ==")
    f_pct = sorted(100.0 * r["lnL"] for r in rows)
    f_high = sorted(100.0 * r["lnL"] for r in rows if r["mode"] == "high")
    f_low = sorted(100.0 * r["lnL"] for r in rows if r["mode"] == "low")
    p_high = len(f_high) / len(rows)
    sd_cs_tree = res["E2_paired_denominator"]["pooled"]["sd_ln_cs_pct"]
    sd_f_tree = res["E2_paired_denominator"]["pooled"]["sd_f_pct"]
    sd_S_tree = res["E2_paired_denominator"]["pooled"]["sd_ln_score_direct_pct"]

    def emp(need, sample):
        k = sum(1 for v in sample if v >= need)
        return {"k": k, "n": len(sample), "p": k / len(sample),
                "ci": wilson(k, len(sample))}

    def gauss(need, sd):
        return {"sd_pct": sd, "z": need / sd, "p": norm_sf(need / sd)}

    e7 = {"anchor_cs": anchor, "need_f_pct": need_anchor, "models": {}}
    e7["models"]["empirical_all_receipts"] = emp(need_anchor, f_pct)
    e7["models"]["empirical_high_mode_only"] = emp(need_anchor, f_high)
    e7["models"]["mixture_coin_times_high_mode"] = {
        "p_high_mode": p_high,
        "p_given_high": emp(need_anchor, f_high)["p"],
        "p": p_high * emp(need_anchor, f_high)["p"],
    }
    e7["models"]["gauss_corpus_sd_f"] = gauss(need_anchor, sd_f_corpus)
    e7["models"]["gauss_within_tree_sd_f"] = gauss(need_anchor, sd_f_tree)
    e7["models"]["gauss_within_tree_sd_ln_score"] = gauss(need_anchor, sd_S_tree)
    e7["models"]["gauss_rule_96"] = gauss(need_anchor,
                                          R96["sd_ln_score_within_tree_pct"])
    e7["models"]["gauss_within_mode_sd_f"] = gauss(
        need_anchor, res["E4_mode_coin"]["pooled_sd_f_within_mode_pct"])
    for name, m in e7["models"].items():
        p = m["p"]
        m["expected_draws"] = (1.0 / p) if p > 0 else None
        m["hours_at_our_rate"] = ((1.0 / p) / OUR_RATE_PER_HOUR
                                 if p > 0 else None)
        print(f"  {name:34s} p={100 * p:8.4f} %  E[draws]="
              f"{m['expected_draws'] if m['expected_draws'] is None else round(m['expected_draws'], 1)}"
              f"  h={m['hours_at_our_rate'] if m['hours_at_our_rate'] is None else round(m['hours_at_our_rate'], 1)}")
    e7["n_high_mode"] = len(f_high)
    e7["n_low_mode"] = len(f_low)
    e7["max_f_low_mode_pct"] = max(f_low)
    e7["max_f_high_mode_pct"] = max(f_high)
    res["E7_p_record"] = e7

    # ---------------------------------------------------------------- E8
    # What the channel can resolve, and what a record actually cost.
    print("\n== E8 channel resolution and the record itself ==")
    e8 = {
        "sd_ln_cs_within_tree_pct": sd_cs_tree,
        "paired_resolvable_1v1_cs_pct": sd_cs_tree * math.sqrt(2),
        "paired_resolvable_us_step": sd_cs_tree * math.sqrt(2)
        * US_STEP_PER_PERCENT_CS,
        "rule_96_paired_resolvable_cs_pct": R96["paired_resolvable_cs_pct"],
        "mde_3sigma_cs_pct": 3 * sd_cs_tree * math.sqrt(2),
        "n_receipts_at_or_above_record": sum(1 for r in rows
                                            if r["score"] >= RECORD_SCORE),
        "max_score_in_corpus": max(r["score"] for r in rows),
        "max_score_sha12": max(rows, key=lambda r: r["score"])["sha"][:12],
        "max_score_cs": max(rows, key=lambda r: r["score"])["cs"],
        "max_score_f_pct": 100.0 * max(rows, key=lambda r: r["score"])["lnL"],
        "max_score_user": max(rows, key=lambda r: r["score"])["user"],
    }
    print(f"  within-tree sd(ln cs) {sd_cs_tree:.4f} % => a 1-vs-1 paired A/B "
          f"resolves {e8['paired_resolvable_1v1_cs_pct']:.4f} % of cs "
          f"({e8['paired_resolvable_us_step']:.1f} us/step) at 1 sigma; "
          f"3 sigma needs {e8['mde_3sigma_cs_pct']:.4f} %")
    print(f"  receipts at or above the record: "
          f"{e8['n_receipts_at_or_above_record']}; corpus max score "
          f"{e8['max_score_in_corpus']:.6f} ({e8['max_score_sha12']}, "
          f"cs {e8['max_score_cs']:.6f}, f {e8['max_score_f_pct']:+.4f} %)")
    res["E8_channel"] = e8

    json.dump(res, open(out_path, "w"), indent=1, sort_keys=True)
    print(f"\nwrote {out_path}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1
         else "research/artifacts/maple-nezuko-r106h/stage-e.json")
