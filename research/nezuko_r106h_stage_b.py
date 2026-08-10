#!/usr/bin/env python3
"""R106-H Stage B: the record as a lottery, and the merit/draw exchange rate.

Reads the frozen receipt corpus through the Stage A loader so that the score
identity, the L decomposition and the verified replicate groups are shared.
Every probability is reported with an interval and a stated estimator; the
empirical estimator is the primary one because it needs no tail assumption.
"""
import json
import math
import os
import statistics as st
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from nezuko_r106h_stage_a import (MB_D, MB_P, RECORD, VERIFIED, load, norm_sf,
                                  sd_ci, t975)

OUT = "research/artifacts/maple-nezuko-r106h/stage-b.json"
RECEIPTS_PER_HOUR = 60.0 / 22.0          # Rule 88: serial queue, ~22 min service
DECODE_PCT_PER_US = 0.015228             # % of cs per us/step of decode


def wilson(k, n, z=1.959963985):
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((c - h) / d, (c + h) / d)


def p_empirical(lnL, need):
    k = sum(1 for v in lnL if v > need)
    lo, hi = wilson(k, len(lnL))
    return {"k": k, "n": len(lnL), "p": k / len(lnL), "ci": [lo, hi]}


def p_semi(lnL, need, sc):
    """Empirical L convolved with a Gaussian candidate axis of sd sc (log units)."""
    if sc <= 0:
        return p_empirical(lnL, need)["p"]
    return sum(norm_sf((need - v) / sc) for v in lnL) / len(lnL)


def p_gauss(need, sc, sl):
    return norm_sf(need / math.sqrt(sc * sc + sl * sl))


def invert_draws(lnL, sc, m, k_list):
    """Merit increment worth exactly one extra draw at each budget k."""
    out = {}
    lnR = math.log(RECORD)
    for k in k_list:
        target = 1 - (1 - p_semi(lnL, lnR - m, sc)) ** (k + 1)
        lo, hi = 0.0, 0.05
        for _ in range(60):
            mid = 0.5 * (lo + hi)
            cur = 1 - (1 - p_semi(lnL, lnR - m - mid, sc)) ** k
            if cur < target:
                lo = mid
            else:
                hi = mid
        out[k] = 0.5 * (lo + hi)
    return out


def main():
    rows = load()
    lnL = [r["lnL"] for r in rows]
    lnR = math.log(RECORD)
    res = {"schema": "maple-nezuko-r106h-stage-b/1",
           "record_score": RECORD, "n_receipts": len(rows)}

    # ---------------------------------------------------------------- B0
    # candidate-axis sigma and its interval (A1c, dof 10)
    pooled, df = 0.0, 0
    ver = json.load(open(VERIFIED))
    by_sha = {}
    for r in rows:
        if r["sha"]:
            by_sha[r["sha"][:12]] = r
    gsets = []
    for g in ver.get("groups", []):
        if not g.get("verified_inert_only"):
            continue
        mem = [by_sha[rc["sha12"]] for rc in g.get("receipts", [])
               if rc.get("sha12") in by_sha]
        if len(mem) >= 2:
            gsets.append((g.get("group"), mem))
    for _, mem in gsets:
        lc = [math.log(r["cs"]) for r in mem]
        pooled += (len(lc) - 1) * st.variance(lc)
        df += len(lc) - 1
    sc = math.sqrt(pooled / df)
    sc_lo, sc_hi = sd_ci(sc, df)
    sl = st.stdev(lnL)
    res["sigma_cs"] = {"sd_pct": 100 * sc, "ci_pct": [100 * sc_lo, 100 * sc_hi],
                       "dof": df}
    res["sigma_L_pct"] = 100 * sl
    print("=== B0  the two axes ===")
    print(f"  sigma_cs (candidate axis, dof {df}) = {100*sc:.4f} % "
          f"CI [{100*sc_lo:.4f}, {100*sc_hi:.4f}]  (rel SE of the sd "
          f"{100/math.sqrt(2*df):.1f} %)")
    print(f"  sigma_L  (baseline lottery, dof {len(lnL)-1}) = {100*sl:.4f} % "
          f"(rel SE {100/math.sqrt(2*(len(lnL)-1)):.2f} %)")
    print(f"  per-draw sigma of the ranked score = "
          f"{100*math.sqrt(sc*sc+sl*sl):.4f} % (axes independent; the prefill "
          f"common-mode test rejects cancellation)")

    # ---------------------------------------------------------------- B1
    # winner's curse, measured rather than assumed: our best receipt is the max
    # of a verified n=5 replicate group, so the group mean is unbiased merit.
    print("\n=== B1  merit of our best tree, before and after the winner's "
          "curse ===")
    b1 = {}
    for key, mem in gsets:
        cs = [r["cs"] for r in mem]
        mx = max(cs)
        b1[key] = {"n": len(cs), "max_cs": mx, "mean_cs": st.mean(cs),
                   "se_mean_pct": 100 * sc / math.sqrt(len(cs)),
                   "selection_bias_pct": 100 * math.log(mx / st.mean(cs))}
        print(f"  {key:26s} n={len(cs)}  max cs {mx:.6f}  mean cs "
              f"{st.mean(cs):.6f}  max is {100*math.log(mx/st.mean(cs)):+.4f} % "
              f"above the group mean (SE of the mean "
              f"{100*sc/math.sqrt(len(cs)):.4f} %)")
    res["B1_groups"] = b1
    top = max(b1.items(), key=lambda kv: kv[1]["max_cs"])
    m_obs = math.log(top[1]["max_cs"])
    m_unb = math.log(top[1]["mean_cs"])
    res["B1_top_group"] = top[0]
    print(f"  best-observed receipt sits in {top[0]}: observed cs "
          f"{top[1]['max_cs']:.6f}, unbiased tree merit "
          f"{top[1]['mean_cs']:.6f} ({100*(m_unb-m_obs):+.4f} % of cs)")

    # ---------------------------------------------------------------- B2
    print("\n=== B2  P(beat the record) for one draw, by assumed true merit ===")
    ladder = []
    for label, m in (("observed max cs (winner's curse, optimistic)", m_obs),
                     ("unbiased merit of that tree (n=5 mean)", m_unb),
                     ("frontier tree bd33883e cs 2.582286", math.log(2.582286)),
                     ("unbiased merit +0.10 % of cs", m_unb + 0.0010),
                     ("unbiased merit +0.25 % of cs", m_unb + 0.0025),
                     ("unbiased merit +0.50 % of cs", m_unb + 0.0050)):
        need = lnR - m
        emp = p_empirical(lnL, need)
        row = {"label": label, "cs": math.exp(m), "need_lnL_pct": 100 * need,
               "empirical": emp,
               "semi_empirical": {"point": p_semi(lnL, need, sc),
                                  "sigma_lo": p_semi(lnL, need, sc_lo),
                                  "sigma_hi": p_semi(lnL, need, sc_hi)},
               "gaussian": p_gauss(need, sc, sl)}
        ladder.append(row)
        print(f"  {label}")
        print(f"     cs {math.exp(m):.6f}  needs ln L > {100*need:+.4f} %")
        print(f"     empirical {emp['k']}/{emp['n']} = {100*emp['p']:.2f} % "
              f"CI [{100*emp['ci'][0]:.2f}, {100*emp['ci'][1]:.2f}] %")
        print(f"     semi-empirical (L empirical (x) N(0,sigma_cs)) "
              f"{100*row['semi_empirical']['point']:.2f} % "
              f"[{100*row['semi_empirical']['sigma_lo']:.2f}, "
              f"{100*row['semi_empirical']['sigma_hi']:.2f}] % across the "
              f"sigma_cs CI")
        print(f"     both-Gaussian {100*row['gaussian']:.2f} %")
    res["B2_ladder"] = ladder

    # ---------------------------------------------------------------- B3
    print("\n=== B3  does a record beat require winning the prefill coin? ===")
    v = sorted(100 * math.log(r["bl_pre"] / MB_P) for r in rows)
    n = len(v)
    gap, cut = -1.0, None
    for i in range(int(0.20 * n), int(0.80 * n)):
        if v[i + 1] - v[i] > gap:
            gap, cut = v[i + 1] - v[i], 0.5 * (v[i] + v[i + 1])
    hi_mode = [r for r in rows if 100 * math.log(r["bl_pre"] / MB_P) >= cut]
    need = lnR - m_obs
    winners = [r for r in rows if r["lnL"] > need]
    in_hi = sum(1 for r in winners if 100 * math.log(r["bl_pre"] / MB_P) >= cut)
    fh, fh_ci = len(hi_mode) / n, wilson(len(hi_mode), n)
    res["B3"] = {"antimode_pct": cut, "high_mode_frac": fh,
                 "high_mode_ci": list(fh_ci),
                 "winners": len(winners), "winners_in_high_mode": in_hi,
                 "prefill_coin_score_value_pct":
                     0.25 * (st.mean([x for x in v if x >= cut])
                             - st.mean([x for x in v if x < cut]))}
    print(f"  high prefill mode: {len(hi_mode)}/{n} = {100*fh:.1f} % "
          f"CI [{100*fh_ci[0]:.1f}, {100*fh_ci[1]:.1f}] %")
    print(f"  the mode flip is worth "
          f"{res['B3']['prefill_coin_score_value_pct']:.4f} % of score "
          f"(0.25 x the {res['B3']['prefill_coin_score_value_pct']/0.25:.3f} % "
          f"mode separation) = "
          f"{res['B3']['prefill_coin_score_value_pct']/DECODE_PCT_PER_US:.1f} "
          f"us/step of decode")
    print(f"  of the {len(winners)} receipts whose L alone would have carried "
          f"cs {math.exp(m_obs):.6f} past the record, {in_hi} were in the high "
          f"prefill mode")
    # regime sensitivity: has the high-mode rate changed recently?
    for days, lab in ((3, "last 3 UTC days"), (7, "last 7 UTC days")):
        cutoff = rows[-1]["t"] - days * 86400
        sub = [r for r in rows if r["t"] >= cutoff]
        k = sum(1 for r in sub if 100 * math.log(r["bl_pre"] / MB_P) >= cut)
        lo, hi = wilson(k, len(sub))
        kk = sum(1 for r in sub if r["lnL"] > need)
        res["B3"][f"last_{days}d"] = {"n": len(sub), "high_mode": k,
                                      "high_mode_ci": [lo, hi],
                                      "winners": kk,
                                      "winner_ci": list(wilson(kk, len(sub)))}
        print(f"  {lab}: n={len(sub)}  high mode {k} = {100*k/len(sub):.1f} % "
              f"CI [{100*lo:.1f}, {100*hi:.1f}] %   record-carrying L "
              f"{kk} = {100*kk/len(sub):.1f} % CI "
              f"[{100*wilson(kk,len(sub))[0]:.1f}, "
              f"{100*wilson(kk,len(sub))[1]:.1f}] %")

    # ---------------------------------------------------------------- B4
    print("\n=== B4  draws, wall clock and cumulative probability ===")
    b4 = []
    for row in ladder[:3]:
        p = row["semi_empirical"]["point"]
        pe = row["empirical"]["p"]
        e = {"label": row["label"], "p_draw": p,
             "expected_draws": (1 / p) if p > 0 else None,
             "hours": (1 / p) / RECEIPTS_PER_HOUR if p > 0 else None,
             "p_empirical": pe}
        for k in (4, 10, 20, 40, 82):
            e[f"cum_{k}"] = 1 - (1 - p) ** k
        b4.append(e)
        print(f"  {row['label']}")
        print(f"     p/draw {100*p:.2f} %  E[draws] {1/p:.1f}  exclusive "
              f"channel time {(1/p)/RECEIPTS_PER_HOUR:.1f} h at "
              f"{RECEIPTS_PER_HOUR:.2f} receipts/h")
        print("     cumulative P: " + "  ".join(
            f"k={k}: {100*e[f'cum_{k}']:.1f} %" for k in (4, 10, 20, 40, 82)))
    res["B4"] = b4

    # ---------------------------------------------------------------- B5
    print("\n=== B5  exchange rate Y: merit worth exactly one extra draw ===")
    y = {}
    for lab, m in (("unbiased merit of the best tree", m_unb),
                   ("observed max cs", m_obs)):
        inv = invert_draws(lnL, sc, m, [4, 10, 20, 40])
        y[lab] = {str(k): {"pct_of_cs": 100 * dm,
                           "us_per_step": 100 * dm / DECODE_PCT_PER_US}
                  for k, dm in inv.items()}
        print(f"  {lab} (cs {math.exp(m):.6f}):")
        for k, dm in inv.items():
            print(f"     at a budget of k={k:2d} draws, one extra draw is worth "
                  f"{100*dm:.4f} % of cs = {100*dm/DECODE_PCT_PER_US:.2f} "
                  f"us/step of decode")
    res["B5_exchange_rate"] = y
    # inverse: how many draws is a known mechanism size worth?
    print("  inverse reading, at a budget of k=20 draws:")
    base = 1 - (1 - p_semi(lnL, lnR - m_unb, sc)) ** 20
    inv2 = {}
    for dm, lab in ((0.000198, "Rule 92 dispatch-reordering ceiling 1.30 us/step"),
                    (0.0010, "+0.10 % of cs = 6.6 us/step"),
                    (0.003204, "Rule 91 whole 19.0 us/step revert residual"),
                    (0.0050, "+0.50 % of cs = 32.8 us/step")):
        pnew = p_semi(lnL, lnR - m_unb - dm, sc)
        k_eq = math.log(1 - base) / math.log(1 - pnew) if pnew > 0 else None
        inv2[lab] = {"pct_of_cs": 100 * dm, "draws_equivalent": 20 - k_eq}
        print(f"     {lab}: worth {20-k_eq:+.1f} draws "
              f"({(20-k_eq)/RECEIPTS_PER_HOUR:+.1f} h of channel)")
    res["B5_inverse"] = inv2

    # ---------------------------------------------------------------- B6
    print("\n=== B6  tree selection: repeat the best tree, or diversify? ===")
    b6 = {}
    p_best = p_semi(lnL, lnR - m_unb, sc)
    for dm in (0.0005, 0.0010, 0.0020, 0.0050):
        p2 = p_semi(lnL, lnR - m_unb + dm, sc)
        b6[f"-{100*dm:.2f}%"] = {"p": p2, "ratio": p2 / p_best}
        print(f"  a tree {100*dm:.2f} % of cs behind the best has p/draw "
              f"{100*p2:.3f} % = {100*p2/p_best:.0f} % of the best tree's rate")
    # power to tell two trees apart on merit
    print("  receipts needed per arm to resolve a merit gap at 80 % power, "
          "alpha=0.05 (two-sided):")
    for d in (0.0005, 0.0010, 0.0020, 0.0050):
        nn = 2 * (sc / d) ** 2 * (1.959963985 + 0.8416212) ** 2
        b6[f"n_per_arm_{100*d:.2f}%"] = nn
        print(f"     gap {100*d:.2f} % of cs -> n = {nn:.0f} per arm "
              f"({2*nn/RECEIPTS_PER_HOUR:.0f} h of channel for the pair)")
    res["B6"] = b6

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(res, open(OUT, "w"), indent=1, sort_keys=True)
    print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
