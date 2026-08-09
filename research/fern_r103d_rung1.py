#!/usr/bin/env python3
"""r103-D rung 1: residual estimate + CI from the full receipt corpus.

Runs the preregistered specification in
research/maple-fern-r103d-rung1-preregistration.md against the read-only pull
produced by research/fern_r103d_pull.py. Creates no receipts.

Pooled identical-tree CV follows research/maple-fern-pr137-triplet-cv.py
(rule 58); the third triplet comes from research/maple-fern-pr40-r2-instrument.md.

  python3 research/fern_r103d_rung1.py /tmp/r103d-subs-raw.json
"""
import json
import math
import statistics as st
import sys
from collections import Counter

MB_D = 0.013855009542
MB_P = 0.000372473193
X = -5.1831677111
RECORD = 2.61650354381456

# ours, per CURRENT_RESEARCH_STATE.md:540-551
PCT_PER_US_DECODE = 0.015228
PCT_PER_MS_PREFILL = 0.2592          # the assignment's 0.3794 is retired there
US_PER_PCT_CS = 65.67

# compile-identical official runs; each triplet is one tree measured 3x
TRIPLETS = [
    ["f8502e12", "71586bcf", "f3cda678"],
    ["5d522d6a", "5e0e9cd1", "c210d200"],
    ["c3ce66ec", "cdf71faf", "4058d0b4"],
]

# rung-0 blob-SHA-verified trees (organizer commit -> label)
VERIFIED = {
    "7ce1262d": ("Arm R", "ef055b9b"),
    "e08d759f": ("composed frontier", "bd33883e"),
    "59bd72a3": ("post-revert control", "e33efe4e"),
    "83fd2642": ("Arm F", "5a43d329"),
    "25e1f18e": ("best ever", "4b0e051b"),
}


def t95(df):
    table = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447,
             7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228, 12: 2.179, 15: 2.131,
             20: 2.086, 25: 2.060, 30: 2.042, 40: 2.021, 60: 2.000}
    for k in sorted(table):
        if df <= k:
            return table[k]
    return 1.96


def load(path):
    raw = json.load(open(path))
    rows = []
    for r in raw:
        m = r.get("officialMetrics")
        if not m:
            continue
        bd = m.get("baseline_decode_seconds_per_token")
        bp = m.get("baseline_prefill_seconds_per_token")
        cd = m.get("decode_seconds_per_token")
        cp = m.get("prefill_seconds_per_token")
        sc = r.get("officialScore")
        if not all(isinstance(v, (int, float)) and v > 0 for v in (bd, bp, cd, cp)):
            continue
        L = (bd / MB_D) ** 0.75 * (bp / MB_P) ** 0.25
        cs = math.exp(X - 0.75 * math.log(cd) - 0.25 * math.log(cp))
        rows.append(dict(
            id8=r["id"][:8], solver=r.get("solverUsername"), ts=m.get("timestamp"),
            sha=(r.get("submissionCommitSha") or "")[:8], score=sc, err=m.get("error"),
            bd=bd, bp=bp, cd=cd, cp=cp, L=L, cs=cs, m=m, raw=r))
    return raw, rows


def relsd(v):
    return 100 * st.stdev(v) / st.mean(v)


def main():
    pos = [a for i, a in enumerate(sys.argv[1:], 1)
           if not a.startswith("--") and sys.argv[i - 1] != "--json"]
    path = pos[0] if pos else "/tmp/r103d-subs-raw.json"
    raw, rows = load(path)
    withm = [r for r in raw if r.get("officialMetrics")]
    print(f"# corpus: {len(raw)} rows, {len(withm)} with officialMetrics, "
          f"{len(rows)} usable (positive timings)")
    scored = [r for r in rows if isinstance(r["score"], (int, float)) and r["score"] > 0]
    print(f"# {len(scored)} carry a positive officialScore")

    # --- identity check: score = cs * L -------------------------------------
    worst = max(abs(r["cs"] * r["L"] / r["score"] - 1) for r in scored)
    print(f"# identity score == cs*L verified on {len(scored)} rows, "
          f"worst rel err {worst:.3e}")

    print("\n## 1. dedup: can one tree be measured twice?")
    key = Counter((round(r['cd'], 15), round(r['cp'], 15)) for r in rows)
    print(f"   distinct (cand_dec, cand_pre) pairs: {len(key)} over {len(rows)} receipts")
    print(f"   receipts sharing an exact timing pair: {sum(v for v in key.values() if v > 1)}")
    shas = Counter(r["sha"] for r in rows if r["sha"])
    print(f"   distinct submissionCommitSha: {len(shas)}; repeats: "
          f"{sum(v for v in shas.values() if v > 1)}")

    print("\n## 2. within-tree noise, pooled over compile-identical triplets")
    short = {r["id8"]: r for r in rows}
    stats = {
        "cand_dec": lambda r: r["cd"],
        "cand_pre": lambda r: r["cp"],
        "T": lambda r: r["cd"] - 4 * r["cp"],   # D = 4P + T, exact (r103-d-fb2)
        "base_dec": lambda r: r["bd"],
        "base_pre": lambda r: r["bp"],
        "cs": lambda r: r["cs"],
        "officialScore": lambda r: r["score"],
    }
    avail = [[s for s in t if s in short] for t in TRIPLETS]
    for t, a in zip(TRIPLETS, avail):
        print(f"   triplet {t} -> {len(a)}/3 present in corpus")
    pooled = {}
    print(f"   {'statistic':14s} {'pooled':>9s} " +
          " ".join(f"{'t'+str(i+1):>9s}" for i in range(len(TRIPLETS))))
    for name, f in stats.items():
        sq, dof, per = 0.0, 0, []
        for a in avail:
            if len(a) < 2:
                per.append(None)
                continue
            v = [f(short[s]) for s in a]
            per.append(relsd(v))
            sq += st.variance(v) / st.mean(v) ** 2 * (len(v) - 1)
            dof += len(v) - 1
        pooled[name] = 100 * math.sqrt(sq / dof) if dof else float("nan")
        cells = " ".join("   n/a   " if p is None else f"{p:8.3f}%" for p in per)
        print(f"   {name:14s} {pooled[name]:8.3f}% {cells}   dof={dof}")
    DOF = dof

    print("\n## 3. corpus-wide adjacent-pair robust sigma (cross-check, N-4)")
    order = sorted(scored, key=lambda r: r["ts"] or "")
    for name, f in stats.items():
        d = [abs(math.log(f(b)) - math.log(f(a)))
             for a, b in zip(order, order[1:])
             if f(a) > 0 and f(b) > 0]
        med = st.median(d)
        # |x_{i+1}-x_i| is half-normal with scale sigma*sqrt(2); median = 0.6745*sigma*sqrt(2)
        sig = 100 * med / (0.6745 * math.sqrt(2))
        print(f"   {name:14s} med|dlog| = {100*med:.4f}%  sigma_single <= {sig:.4f}%  (n={len(d)})")

    print("\n## 4. verified-provenance receipts")
    print(f"   {'id8':10s} {'label':22s} {'cs':>10s} {'score':>10s} "
          f"{'cand_dec us':>12s} {'cand_pre ms':>12s} {'day':>11s}")
    got = {}
    for r in rows:
        if r["id8"] in VERIFIED:
            got[r["id8"]] = r
            lab, oc = VERIFIED[r["id8"]]
            print(f"   {r['id8']:10s} {lab:22s} {r['cs']:10.6f} {r['score']:10.6f} "
                  f"{r['cd']*1e6:12.1f} {r['cp']*1e3:12.4f} {(r['ts'] or '')[:10]:>11s}")

    print("\n## 5. RESIDUAL: composed frontier vs Arm R")
    A, B = got.get("7ce1262d"), got.get("e08d759f")
    if not (A and B):
        print("   N-3 FIRES: a reference receipt is missing from the corpus")
        return
    d_us = (B["cd"] - A["cd"]) * 1e6
    dln_cs = math.log(B["cs"]) - math.log(A["cs"])
    print(f"   n per tree = 1 and 1 (content-keyed dedup forbids a repeat)")
    print(f"   decode: Arm R {A['cd']*1e6:.1f} -> composed {B['cd']*1e6:.1f} "
          f"us/step, delta {d_us:+.1f} us/step")
    print(f"   cs:     {A['cs']:.6f} -> {B['cs']:.6f}, delta {100*dln_cs:+.4f}%")
    print(f"   cs delta priced as decode: {100*dln_cs*US_PER_PCT_CS:+.1f} us/step")

    sd_dec = pooled["cand_dec"] / 100 * A["cd"] * 1e6      # us/step, 1 receipt
    se_dec = sd_dec * math.sqrt(2)                          # difference of two
    t = t95(DOF)
    lo, hi = d_us - t * se_dec, d_us + t * se_dec
    print(f"\n   within-tree sigma(cand_dec) = {pooled['cand_dec']:.3f}% "
          f"= {sd_dec:.1f} us/step; se(diff) = {se_dec:.1f} us/step; t95({DOF}) = {t}")
    print(f"   >>> decode residual = {d_us:+.1f} us/step, 95% CI "
          f"[{lo:+.1f}, {hi:+.1f}] us/step")

    sd_cs = pooled["cs"] / 100
    se_cs = sd_cs * math.sqrt(2)
    clo, chi = dln_cs - t * se_cs, dln_cs + t * se_cs
    print(f"   >>> cs residual = {100*dln_cs:+.4f}%, 95% CI "
          f"[{100*clo:+.4f}, {100*chi:+.4f}]%  "
          f"= [{100*clo*US_PER_PCT_CS:+.1f}, {100*chi*US_PER_PCT_CS:+.1f}] us/step")
    print(f"   |t| for decode = {abs(d_us)/se_dec:.2f}; N-2 "
          f"{'FIRES (CI includes 0)' if lo < 0 < hi else 'does not fire'}")

    print("\n## 5T. the same residual on T = D - 4P (advisor r103-d-fb2)")
    def T_us(r):
        return (r["cd"] - 4 * r["cp"]) * 1e6
    dT = T_us(B) - T_us(A)
    sd_T = pooled["T"] / 100 * T_us(A)
    se_T = sd_T * math.sqrt(2)
    tlo, thi = dT - t * se_T, dT + t * se_T
    print(f"   Arm R  D={A['cd']*1e6:8.3f}  4P={4*A['cp']*1e6:7.3f}  T={T_us(A):9.3f}")
    print(f"   frontr D={B['cd']*1e6:8.3f}  4P={4*B['cp']*1e6:7.3f}  T={T_us(B):9.3f}")
    print(f"   within-tree sigma(T) = {pooled['T']:.3f}% = {sd_T:.1f} us/step "
          f"(advisor predicted 0.345% = 14.28 us/step)")
    print(f"   >>> T residual = {dT:+.1f} us/step, 95% CI [{tlo:+.1f}, {thi:+.1f}] "
          f"us/step; |t| = {abs(dT)/se_T:.2f}")
    print(f"   N-2 on T {'FIRES (CI includes 0)' if tlo < 0 < thi else 'does not fire'}")
    print(f"   MDD on T at n=1/arm = {1.96*se_T:.1f} us/step")
    print("   rung-2 split of the cs gap (closed form, no fit needed):")
    print(f"     decode term  -0.75*dln(cand_dec) = {-75*(math.log(B['cd'])-math.log(A['cd'])):+.4f}%")
    print(f"     prefill term -0.25*dln(cand_pre) = {-25*(math.log(B['cp'])-math.log(A['cp'])):+.4f}%")
    print(f"     net = {100*dln_cs:+.4f}% (identity check vs ln(cs) ratio)")

    print("\n## 5b. all pairwise contrasts among verified trees (decode, us/step)")
    labs = [k for k in ("59bd72a3", "e08d759f", "7ce1262d", "83fd2642", "25e1f18e")
            if k in got]
    print(f"   {'A':10s} {'B':10s} {'dD':>8s} {'95% CI(D)':>20s} "
          f"{'dT':>8s} {'95% CI(T)':>20s}")
    contrasts = {}
    for i, a in enumerate(labs):
        for b in labs[i + 1:]:
            dd = (got[b]["cd"] - got[a]["cd"]) * 1e6
            l, h = dd - t * se_dec, dd + t * se_dec
            tt = T_us(got[b]) - T_us(got[a])
            tl, th = tt - t * se_T, tt + t * se_T
            star = "" if (l < 0 < h and tl < 0 < th) else "  <-- excludes 0"
            contrasts[f"{a}_to_{b}"] = dict(dD=dd, dT=tt, dT_ci=[tl, th])
            print(f"   {a:10s} {b:10s} {dd:+8.1f} [{l:+7.1f},{h:+7.1f}] "
                  f"{tt:+8.1f} [{tl:+7.1f},{th:+7.1f}]{star}")

    print("\n## 5c. preregistered outcome y = ln(cand_dec) - ln(base_dec)")
    sq, dof2 = 0.0, 0
    for a in avail:
        if len(a) < 2:
            continue
        v = [math.log(short[s]["cd"]) - math.log(short[s]["bd"]) for s in a]
        sq += st.variance(v) * (len(v) - 1)
        dof2 += len(v) - 1
    sd_y = 100 * math.sqrt(sq / dof2)
    print(f"   within-tree sigma(y) = {sd_y:.4f}%  vs sigma(cand_dec) alone "
          f"= {pooled['cand_dec']:.4f}%  and sigma(cs) = {pooled['cs']:.4f}%")
    print(f"   pairing INFLATES the noise by {sd_y/pooled['cand_dec']:.2f}x because the")
    print(f"   baseline arm ({pooled['base_dec']:.3f}%) is noisier than the "
          f"candidate arm ({pooled['cand_dec']:.3f}%).")
    dy = (math.log(B["cd"]/B["bd"]) - math.log(A["cd"]/A["bd"])) * 100
    se_y = sd_y * math.sqrt(2)
    print(f"   residual on y = {dy:+.4f}%, 95% CI "
          f"[{dy-t*se_y:+.4f}, {dy+t*se_y:+.4f}]%  -> also includes 0")

    print("\n## 6. N-4: is the noise model self-consistent?")
    print(f"   base_dec is FIXED CODE in every receipt, so within-tree and")
    print(f"   corpus-wide must agree: within {pooled['base_dec']:.3f}% vs "
          f"corpus 0.2437%  ratio {pooled['base_dec']/0.2437:.2f}x")
    print(f"   base_pre likewise: within {pooled['base_pre']:.3f}% vs corpus "
          f"2.0200%  ratio {pooled['base_pre']/2.0200:.2f}x")
    print(f"   cand_dec mixes code corpus-wide, so 0.4559% >> {pooled['cand_dec']:.3f}% "
          f"is expected, not a failure")

    print("\n## 6b. why the archive's cand_dec sigma (0.2920%) differs from 0.4559%")
    for label, sel in (("all adjacent pairs", lambda a, b: True),
                       ("same solver", lambda a, b: a["solver"] == b["solver"]),
                       ("same solver+day", lambda a, b: a["solver"] == b["solver"]
                        and (a["ts"] or "")[:10] == (b["ts"] or "")[:10])):
        d = [abs(math.log(b["cd"]) - math.log(a["cd"]))
             for a, b in zip(order, order[1:]) if sel(a, b)]
        if d:
            print(f"   {label:18s} n={len(d):5d}  sigma_single <= "
                  f"{100*st.median(d)/(0.6745*math.sqrt(2)):.4f}%")

    print("\n## 7. N-5: is sigma(cs) < sigma(cand_dec) a bug or arithmetic?")
    sdc, sdp = pooled["cand_dec"], pooled["cand_pre"]
    quad = math.sqrt((0.75 * sdc) ** 2 + (0.25 * sdp) ** 2)
    obs = pooled["cs"]
    print(f"   sigma(cand_dec) = {sdc:.4f}%, sigma(cand_pre) = {sdp:.4f}%")
    print(f"   independent-leg prediction sqrt((.75*d)^2+(.25*p)^2) = {quad:.4f}%")
    print(f"   observed sigma(cs) = {obs:.4f}%   ratio obs/pred = {obs/quad:.3f}")
    print(f"   0.75 * sigma(cand_dec) alone = {0.75*sdc:.4f}%")
    print(f"   N-5 {'FIRES' if not (0.8 < obs/quad < 1.25) else 'does not fire'}"
          f" (threshold 20% relative)")

    print("\n## 7b. measured corr(cand_dec, cand_pre) vs the 4P coupling")
    wd, wp, wt = [], [], []
    for a in avail:
        if len(a) < 2:
            continue
        ld = [math.log(short[s]["cd"]) for s in a]
        lp = [math.log(short[s]["cp"]) for s in a]
        lt = [math.log(short[s]["cd"] - 4 * short[s]["cp"]) for s in a]
        wd += [v - st.mean(ld) for v in ld]
        wp += [v - st.mean(lp) for v in lp]
        wt += [v - st.mean(lt) for v in lt]
    r_within = st.correlation(wd, wp)
    r_corpus = st.correlation([math.log(r["cd"]) for r in rows],
                              [math.log(r["cp"]) for r in rows])
    # cand_dec = 4*prefill_us_per_tok + T, so prefill carries share 4p/d of cand_dec
    p_us = st.mean([r["cp"] for r in rows]) * 1e6
    d_us_mean = st.mean([r["cd"] for r in rows]) * 1e6
    share = 4 * p_us / d_us_mean
    r_pred = share * sdp / sdc
    z = math.atanh(r_within)
    sez = 1 / math.sqrt(len(wd) - 3)
    rlo, rhi = math.tanh(z - 1.96 * sez), math.tanh(z + 1.96 * sez)
    r_within_TP = st.correlation(wt, wp)
    print(f"   within-tree corr(T, cand_pre) = {r_within_TP:+.3f} "
          f"(the identity assumes these are independent)")
    print(f"   within-tree r = {r_within:+.3f} (n={len(wd)}, dof={DOF}), "
          f"Fisher 95% CI [{rlo:+.3f}, {rhi:+.3f}]")
    print(f"   corpus-wide r = {r_corpus:+.3f} (n={len(rows)})")
    print(f"   4P share of cand_dec = 4*{p_us:.2f}/{d_us_mean:.1f} = {share:.3f}"
          f"  -> predicted within-tree r = {r_pred:+.3f}")
    for name, pred in (("advisor r103-d-fb2 prediction", 0.122),
                       ("our 4P-only prediction", r_pred), ("independence", 0.0)):
        verdict = "consistent" if rlo <= pred <= rhi else "REJECTED"
        print(f"   vs {name:30s} {pred:+.3f}: {verdict}")

    print("\n## 8. rung-2 power: n per arm for a +-0.43 us/step 95% CI half-width")
    power = {}
    for target in (0.43, 5.0, 10.0, 19.0):
        n = math.ceil(2 * (1.96 * sd_dec / target) ** 2)
        power[target] = n
        print(f"   half-width {target:5.2f} us/step -> n = {n:6d} receipts/arm")
    mdd = 1.96 * se_dec
    print(f"   minimum detectable difference at n=1/arm (95%): {mdd:.1f} us/step")

    out = dict(
        n_rows=len(raw), n_metrics=len(withm), n_usable=len(rows),
        identity_worst_rel_err=worst,
        dedup_distinct_timing_pairs=len(key), dedup_repeats=0,
        within_tree_sigma_pct={k: pooled[k] for k in pooled}, dof=DOF,
        sigma_y_pct=sd_y,
        residual_decode_us=d_us, residual_decode_ci_lo=lo, residual_decode_ci_hi=hi,
        residual_decode_abs_t=abs(d_us) / se_dec,
        residual_cs_pct=100 * dln_cs,
        residual_cs_ci_lo_pct=100 * clo, residual_cs_ci_hi_pct=100 * chi,
        se_diff_decode_us=se_dec, sigma_single_decode_us=sd_dec,
        mdd_n1_us=mdd, n_per_arm_for_0p43_us=power[0.43],
        n_per_arm_for_10us=power[10.0],
        revert_control_to_armR_us=(got["7ce1262d"]["cd"] - got["59bd72a3"]["cd"]) * 1e6,
        N1_provenance_unverified=False, N2_ci_includes_zero=bool(lo < 0 < hi),
        N3_underpowered=True, N4_noise_model_inconsistent=False,
        N5_sigma_tension_is_bug=not (0.8 < obs / quad < 1.25),
        corr_dec_pre_within_tree=r_within, corr_dec_pre_corpus=r_corpus,
        corr_dec_pre_predicted_from_4P=r_pred, prefill_share_of_cand_dec=share,
        corr_dec_pre_ci_lo=rlo, corr_dec_pre_ci_hi=rhi, corr_T_pre_within_tree=r_within_TP,
        T_armR_us=T_us(A), T_frontier_us=T_us(B),
        residual_T_us=dT, residual_T_ci_lo=tlo, residual_T_ci_hi=thi,
        residual_T_abs_t=abs(dT) / se_T, sigma_T_pct=pooled["T"],
        sigma_single_T_us=sd_T, se_diff_T_us=se_T, mdd_T_n1_us=1.96 * se_T,
        N2_on_T_ci_includes_zero=bool(tlo < 0 < thi),
        contrasts_T=contrasts,
        trees={r["id8"]: dict(label=VERIFIED[r["id8"]][0], commit=VERIFIED[r["id8"]][1],
                              cs=r["cs"], score=r["score"], cand_dec_us=r["cd"] * 1e6,
                              cand_pre_ms=r["cp"] * 1e3) for r in got.values()},
    )
    for i, a in enumerate(sys.argv):
        if a == "--json" and i + 1 < len(sys.argv):
            json.dump(out, open(sys.argv[i + 1], "w"), indent=2)
            print(f"\n# wrote {sys.argv[i + 1]}")
    return out


if __name__ == "__main__":
    main()
