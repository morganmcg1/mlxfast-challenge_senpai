#!/usr/bin/env python3
"""R106-H Stage D: adjudicate the two competing within-tree sigma estimates and
reconstruct sigma_cs from the two measurement axes.

PR #616 comments 7 and 8 asked four specific things that Stages A-C did not do:

  D1  exclude every `R106E-DRAW-*` receipt from the sigma fit, explicitly.
  D2  verify -- not adopt -- Rule 93.4(a)'s pooled within-identical-tree
      sigma(cs) = 0.1453 % at dof 7, whose key is the note-declared tree
      identity.
  D3  adjudicate that key against Stage 0's key, which is byte identity of the
      submitted surface at `submissionCommitSha` (git blob shas over all 97
      editable paths).  The two keys disagree, and the disagreement is the
      finding.
  D4  test the homogeneity that pooling assumes, across eras and score levels.
  D5  compare robust and classical within-group sigma.
  D6  carry sigma_decode and sigma_prefill separately and *reconstruct*
      sigma_cs from them instead of fitting sigma_cs directly, then report the
      residual of the reconstruction.
  D7  test whether the note-attributed launch partition of our own account has
      significantly different dispersion.

Read-only.  No network, no benchmark, no submission.
"""
import json
import math
import os
import statistics as st
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from nezuko_r106h_stage_a import (CORPUS, VERIFIED, chi2_ci, load, mad_sd,
                                  rel_se_of_sd, sd_ci)
from nezuko_r106h_stage_c import OUR_ACCOUNT, f_sf

OUT = "research/artifacts/maple-nezuko-r106h/stage-d.json"

# Rule 93.4(a): the four note-declared identical-tree families, verbatim.
ADVISOR_FAMILIES = {
    "nezuko calibration A/B/C (2026-08-04)":
        [2.489564, 2.486075, 2.489138],
    "nezuko corpus-harvest 5d522d6a A/B/C (2026-08-04)":
        [2.495927, 2.488426, 2.496426],
    "tanjiro r105-A arm A0 (2026-08-10)":
        [2.583779, 2.580890, 2.574592],
    "tanjiro r105-A arm A1 (2026-08-10)":
        [2.575716, 2.573106],
}
DRAW01_CS = 2.574073          # the R106E-DRAW-01 receipt, Rule 93.4(f)
MATCH_TOL = 3e-6              # advisor values are quoted to 6 decimals


def chi2_sf(x, k):
    """Upper tail of chi-square: Q(k/2, x/2) by series or Lentz CF."""
    if x <= 0:
        return 1.0
    a, z = 0.5 * k, 0.5 * x
    lg = math.lgamma(a)
    if z < a + 1.0:                                    # lower series
        term = 1.0 / a
        s = term
        n = 0
        while abs(term) > abs(s) * 1e-16 and n < 10000:
            n += 1
            term *= z / (a + n)
            s += term
        return 1.0 - s * math.exp(-z + a * math.log(z) - lg)
    tiny = 1e-300                                      # upper continued fraction
    b, c, d = z - a + 1.0, 1.0 / tiny, 1.0 / (z - a + 1.0)
    h = d
    for i in range(1, 10000):
        an = -i * (i - a)
        b += 2.0
        d = an * d + b
        if abs(d) < tiny:
            d = tiny
        c = b + an / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 1e-16:
            break
    return h * math.exp(-z + a * math.log(z) - lg)


def pool(groups):
    """Pooled within-group sd of log values, in percent, with its dof."""
    ss, dof, per = 0.0, 0, []
    for lab, vals in groups:
        if len(vals) < 2:
            continue
        m = st.mean(vals)
        s = sum((v - m) ** 2 for v in vals)
        ss += s
        dof += len(vals) - 1
        per.append({
            "group": lab, "n": len(vals),
            "sd_pct": st.stdev(vals) * 100.0,
            "mad_sd_pct": mad_sd(vals) * 100.0,
            "mean": m, "ss": s,
        })
    if dof == 0:
        return None
    sd = math.sqrt(ss / dof) * 100.0
    lo, hi = sd_ci(sd, dof)
    return {"pooled_sd_pct": sd, "ci_pct": [lo, hi], "dof": dof, "ss": ss,
            "n_groups": len(per), "groups": per}


def bartlett(groups):
    """Bartlett's K^2 for equal variances across groups with n_i >= 2."""
    gs = [(lab, v) for lab, v in groups if len(v) >= 2]
    k = len(gs)
    if k < 2:
        return None
    ns = [len(v) for _, v in gs]
    vs = [st.variance(v) for _, v in gs]
    if min(vs) <= 0:
        return None
    N = sum(ns)
    dof_tot = N - k
    sp2 = sum((n - 1) * v for n, v in zip(ns, vs)) / dof_tot
    num = dof_tot * math.log(sp2) - sum((n - 1) * math.log(v)
                                        for n, v in zip(ns, vs))
    den = 1.0 + (sum(1.0 / (n - 1) for n in ns) - 1.0 / dof_tot) / (3.0 * (k - 1))
    K2 = num / den
    return {"K2": K2, "df": k - 1, "p": chi2_sf(K2, k - 1), "k_groups": k,
            "group_sd_pct": [math.sqrt(v) * 100.0 for v in vs],
            "group_n": ns}


def f_two_sided(v1, d1, v2, d2):
    """Two-sided variance-ratio test, larger variance on top."""
    if v1 >= v2:
        f, a, b = v1 / v2, d1, d2
    else:
        f, a, b = v2 / v1, d2, d1
    return {"F": f, "df": [a, b], "p_two_sided": min(1.0, 2.0 * f_sf(f, a, b))}


def axis_reconstruction(dec, pre, direct, label, dof=None):
    """var(ln cs) = 0.5625 var(ln dec) + 0.0625 var(ln pre) + 0.375 cov.

    ln cs = const - 0.75 ln dec - 0.25 ln pre, so both coefficients are
    negative and the covariance term enters with a plus sign.  `dof` overrides
    the n-1 divisor so a group-centred sample can be scored at the same n-k
    the pooled estimator uses; otherwise the identity is exact but the two
    routes appear to disagree purely through that divisor.
    """
    n = len(dec)
    k = dof if dof else n - 1
    md, mp = st.mean(dec), st.mean(pre)
    vd = sum((a - md) ** 2 for a in dec) / k
    vp = sum((b - mp) ** 2 for b in pre) / k
    cov = sum((a - md) * (b - mp) for a, b in zip(dec, pre)) / k
    rho = cov / math.sqrt(vd * vp) if vd > 0 and vp > 0 else float("nan")
    recon = math.sqrt(0.5625 * vd + 0.0625 * vp + 0.375 * cov) * 100.0
    return {
        "label": label, "n": n, "dof_used": k,
        "sigma_decode_axis_pct": 0.75 * math.sqrt(vd) * 100.0,
        "sigma_prefill_axis_pct": 0.25 * math.sqrt(vp) * 100.0,
        "sd_ln_dec_pct": math.sqrt(vd) * 100.0,
        "sd_ln_pre_pct": math.sqrt(vp) * 100.0,
        "corr_dec_pre": rho,
        "covariance_term_pct2": 0.375 * cov * 1e4,
        "reconstructed_sd_pct": recon,
        "directly_fitted_sd_pct": direct,
        "residual_pct": recon - direct,
        "rel_residual": (recon - direct) / direct if direct else float("nan"),
    }


def flagged_shas(group):
    """sha prefixes named on the left of a `problems` entry."""
    return {p.split(":", 1)[0] for p in group.get("problems") or []}


def member_level_inert(groups, ln_by_sha12):
    """Replicate sets after dropping only the members that carry a
    non-comment difference, instead of discarding the whole group.

    Stage 0 marked a group `verified_inert_only` only when *every* member
    passed the line check, so one dirty member cost the group's whole
    contribution.  Group membership is already a shared comment-insensitive
    digest, so the survivors of a mixed group are still mutual replicates.
    """
    out, detail = [], []
    for g in groups:
        bad = flagged_shas(g)
        keep = [r["sha12"] for r in g["receipts"]
                if not any(r["sha12"].startswith(b) for b in bad)]
        vals = [ln_by_sha12[s] for s in keep if s in ln_by_sha12]
        detail.append({"group": g["group"], "n": g["n"],
                       "verified_inert_only": bool(g.get("verified_inert_only")),
                       "n_flagged_members": len(bad),
                       "flagged_prefixes": sorted(bad),
                       "n_kept": len(vals), "kept_sha12": keep})
        if len(vals) > 1:
            out.append((g["group"], vals))
    return out, detail


def independent_axis_route(sd_dec_pct, sd_pre_pct, rho, source):
    """sigma_cs rebuilt from per-axis dispersions measured somewhere else."""
    vd, vp = (sd_dec_pct / 100.0) ** 2, (sd_pre_pct / 100.0) ** 2
    cov = rho * math.sqrt(vd * vp)
    return {"source": source, "sd_ln_dec_pct": sd_dec_pct,
            "sd_ln_pre_pct": sd_pre_pct, "assumed_corr": rho,
            "reconstructed_sigma_cs_pct":
                math.sqrt(0.5625 * vd + 0.0625 * vp + 0.375 * cov) * 100.0}


def main():
    rows = load()
    raw = json.load(open(CORPUS))["submissions"]
    notes = {s["id"]: (s.get("note") or "") for s in raw}
    for r in rows:
        r["note"] = notes.get(r["id"], "")
    res = {"schema": "maple-nezuko-r106h-stage-d/1", "n_receipts": len(rows)}

    # ---- D1: the R106E-DRAW contamination guard ----------------------------
    hits = [s["id"] for s in raw if "R106E-DRAW" in (s.get("note") or "")]
    near = [r for r in rows if abs(r["cs"] - DRAW01_CS) < 1e-5]
    res["D1_draw01_guard"] = {
        "n_receipts_scanned": len(raw),
        "n_notes_matching_R106E_DRAW": len(hits),
        "matching_ids": hits,
        "n_receipts_within_1e-5_of_draw01_cs": len(near),
        "corpus_frozen_at": "2026-08-10T08:37Z",
        "verdict": ("excluded by construction: the frozen corpus predates the "
                    "R106E-DRAW-01 receipt and contains zero notes matching "
                    "R106E-DRAW, so no sigma in this report can be inflated "
                    "by it" if not hits else "PRESENT -- must be dropped"),
    }

    # ---- D2: locate Rule 93.4(a)'s families in the frozen corpus ----------
    by_cs = sorted(rows, key=lambda r: r["cs"])
    fam_located, fam_groups = {}, []
    for fam, vals in ADVISOR_FAMILIES.items():
        members = []
        for v in vals:
            best = min(by_cs, key=lambda r: abs(r["cs"] - v))
            ok = abs(best["cs"] - v) <= MATCH_TOL
            members.append({
                "advisor_cs": v, "matched": ok,
                "corpus_cs": best["cs"] if ok else None,
                "abs_err": abs(best["cs"] - v),
                "sha12": (best["sha"] or "")[:12] if ok else None,
                "ts": best["createdAt"] if ok else None,
                "user": best["user"] if ok else None,
                "ln_cs": math.log(best["cs"]) if ok else None,
            })
        got = [m for m in members if m["matched"]]
        fam_located[fam] = {
            "n_quoted": len(vals), "n_matched": len(got),
            "advisor_sd_pct": st.stdev([math.log(v) for v in vals]) * 100.0,
            "corpus_sd_pct": (st.stdev([m["ln_cs"] for m in got]) * 100.0
                              if len(got) > 1 else None),
            "members": members,
        }
        if len(got) > 1:
            fam_groups.append((fam, [m["ln_cs"] for m in got]))
    res["D2_advisor_families"] = {
        "families": fam_located,
        "pool_from_advisor_quoted_values":
            pool([(f, [math.log(v) for v in vs])
                  for f, vs in ADVISOR_FAMILIES.items()]),
        "pool_from_corpus_matched_values": pool(fam_groups),
    }

    # ---- D3: note-declared identity vs byte identity of the surface -------
    ident = json.load(open(VERIFIED))
    mine, sha_to_group, sha_to_any = [], {}, {}
    for g in ident["groups"]:
        shas = {r["sha12"] for r in g["receipts"]}
        for s in shas:
            sha_to_any[s] = g["group"]
        if not g.get("verified_inert_only"):
            continue
        vals = [math.log(r["cs"]) for r in rows
                if (r["sha"] or "")[:12] in shas]
        if len(vals) > 1:
            mine.append((g["group"], vals))
        for s in shas:
            sha_to_group[s] = g["group"]
    adjudication = []
    for fam, info in fam_located.items():
        rowsx = []
        for m in info["members"]:
            rowsx.append({
                "advisor_cs": m["advisor_cs"], "sha12": m["sha12"],
                "in_byte_verified_group": sha_to_group.get(m["sha12"]),
                "in_any_digest_group": sha_to_any.get(m["sha12"]),
            })
        labs = {r["in_byte_verified_group"] for r in rowsx}
        adjudication.append({
            "family": fam, "members": rowsx,
            "distinct_byte_groups": sorted(x for x in labs if x),
            "n_members_outside_any_byte_verified_group":
                sum(1 for r in rowsx if not r["in_byte_verified_group"]),
        })
    ln_by_sha12 = {(r["sha"] or "")[:12]: math.log(r["cs"]) for r in rows
                   if r["sha"]}
    member_groups, member_detail = member_level_inert(ident["groups"],
                                                      ln_by_sha12)
    member_pool = pool(member_groups)
    note_pool = res["D2_advisor_families"]["pool_from_corpus_matched_values"]
    group_pool = pool(mine)
    fam_member_keep = {s for d in member_detail for s in d["kept_sha12"]}
    fam_member_groups = []
    for fam, info in fam_located.items():
        vals = [m["ln_cs"] for m in info["members"]
                if m["matched"] and m["sha12"] in fam_member_keep
                and sha_to_any.get(m["sha12"])]
        if len(vals) > 1:
            fam_member_groups.append((fam, vals))
    res["D3_key_adjudication"] = {
        "byte_verified_pool": group_pool,
        "families_vs_byte_key": adjudication,
        "member_level_pool": member_pool,
        "member_level_detail": member_detail,
        "advisor_families_member_level_pool": pool(fam_member_groups),
        "note_key_vs_group_key_F": f_two_sided(
            (group_pool["pooled_sd_pct"] / 100.0) ** 2, group_pool["dof"],
            (note_pool["pooled_sd_pct"] / 100.0) ** 2, note_pool["dof"]),
        "note_key_vs_member_key_F": f_two_sided(
            (member_pool["pooled_sd_pct"] / 100.0) ** 2, member_pool["dof"],
            (note_pool["pooled_sd_pct"] / 100.0) ** 2, note_pool["dof"]),
        "identity_definition": ident["identity"],
        "note": ("Stage 0's key is a comment-insensitive sha256 over every "
                 "file under Sources/ and Vendor/, with every surviving strict "
                 "difference line-checked to be a full-line // comment; the "
                 "note-declared key instead trusts the free-text arm label"),
    }

    # ---- D4: is pooling across eras and score levels defensible? ----------
    era = {}
    for lab, vals in mine:
        shas = {r["sha12"] for g in ident["groups"] if g["group"] == lab
                for r in g["receipts"]}
        day = min(r["createdAt"][:10] for r in rows
                  if (r["sha"] or "")[:12] in shas)
        era.setdefault("2026-08-04..05" if day <= "2026-08-05" else
                       "2026-08-09..10", []).append((lab, vals))
    era_pools = {k: pool(v) for k, v in sorted(era.items())}
    era_ratio = None
    if len(era_pools) == 2:
        a, b = sorted(era_pools)
        era_ratio = f_two_sided((era_pools[a]["pooled_sd_pct"] / 100.0) ** 2,
                                era_pools[a]["dof"],
                                (era_pools[b]["pooled_sd_pct"] / 100.0) ** 2,
                                era_pools[b]["dof"])
        era_ratio["eras"] = [a, b]
    res["D4_homogeneity"] = {
        "bartlett_byte_verified_groups": bartlett(mine),
        "bartlett_advisor_families": bartlett(fam_groups),
        "era_pools_byte_verified": era_pools,
        "era_variance_ratio": era_ratio,
        "mean_cs_by_era": {
            k: st.mean([math.exp(v) for _, vals in members for v in vals])
            for k, members in sorted(era.items())
        },
    }

    # ---- D5: robust vs classical -----------------------------------------
    bv = res["D3_key_adjudication"]["byte_verified_pool"]
    dev = [v - g["mean"] for (lab, vals), g in zip(mine, bv["groups"])
           for v in vals]
    jack = []
    for i, (lab, vals) in enumerate(mine):
        for j, v in enumerate(vals):
            trimmed = [(l2, [x for k2, x in enumerate(v2) if
                             not (i == i2 and j == k2)])
                       for i2, (l2, v2) in enumerate(mine)]
            p = pool(trimmed)
            jack.append({"dropped_group": lab, "dropped_ln_cs": v,
                         "dropped_cs": math.exp(v),
                         "pooled_sd_pct": p["pooled_sd_pct"], "dof": p["dof"]})
    worst = max(dev, key=abs)
    res["D5_robust_vs_classical"] = {
        "classical_pooled_sd_pct": bv["pooled_sd_pct"],
        "robust_pooled_sd_pct_from_centred_deviations": mad_sd(dev) * 100.0,
        "n_centred_deviations": len(dev),
        "per_group": [{"group": g["group"], "n": g["n"],
                       "classical_sd_pct": g["sd_pct"],
                       "mad_sd_pct": g["mad_sd_pct"]} for g in bv["groups"]],
        "largest_group_share_of_pooled_ss":
            max(g["ss"] for g in bv["groups"]) / bv["ss"],
        "max_abs_studentised_deviation":
            abs(worst) * 100.0 / bv["pooled_sd_pct"],
        "leave_one_receipt_out": sorted(jack, key=lambda x: x["pooled_sd_pct"]),
        "leave_one_out_range_pct": [min(x["pooled_sd_pct"] for x in jack),
                                    max(x["pooled_sd_pct"] for x in jack)],
    }

    # ---- D6: reconstruct sigma from the two axes --------------------------
    sha_sets = {g["group"]: {r["sha12"] for r in g["receipts"]}
                for g in ident["groups"]}
    dec_dev, pre_dev, cs_dev = [], [], []
    for lab, _ in mine:
        grp = [r for r in rows if (r["sha"] or "")[:12] in sha_sets[lab]]
        for key, sink in (("ln_dec", dec_dev), ("ln_pre", pre_dev)):
            m = st.mean([r[key] for r in grp])
            sink.extend(r[key] - m for r in grp)
        m = st.mean([math.log(r["cs"]) for r in grp])
        cs_dev.extend(math.log(r["cs"]) - m for r in grp)
    k = len(mine)
    dof_g = len(cs_dev) - k
    direct_cs = math.sqrt(sum(d * d for d in cs_dev) / dof_g) * 100.0
    rho_within = axis_reconstruction(dec_dev, pre_dev, direct_cs, "x",
                                     dof=dof_g)["corr_dec_pre"]
    res["D6_two_axis_reconstruction"] = {
        "candidate_axes_matched_dof":
            axis_reconstruction(dec_dev, pre_dev, direct_cs,
                                "candidate dec/pre, group-centred, dof %d"
                                % dof_g, dof=dof_g),
        "candidate_axes_naive_n_minus_1":
            axis_reconstruction(dec_dev, pre_dev, direct_cs,
                                "same sample scored at n-1=%d instead of n-k"
                                % (len(cs_dev) - 1)),
        "baseline_axes_all_receipts":
            axis_reconstruction(
                [r["ln_bl_dec"] for r in rows], [r["ln_bl_pre"] for r in rows],
                st.stdev([r["lnL"] for r in rows]) * 100.0,
                "baseline bl_dec/bl_pre, n=%d" % len(rows)),
        "independent_axis_routes": [
            independent_axis_route(0.1839, 0.1123, 0.0,
                                   "#597 R106-E per-receipt sd(T), sd(P), "
                                   "independent axes"),
            independent_axis_route(0.1839, 0.1123, rho_within,
                                   "#597 R106-E per-receipt sd(T), sd(P), at "
                                   "this report's within-group corr"),
        ],
        "directly_fitted_sigma_cs_pct": direct_cs,
        "note": ("the identity is algebraic, so the same sample can never "
                 "disagree with itself once both routes use the same divisor: "
                 "the matched-dof residual is exactly zero and the n-1 variant "
                 "shows what the divisor alone is worth.  The informative "
                 "cross-check therefore uses per-axis dispersions measured on "
                 "a different sample (#597) and compares the result with this "
                 "report's direct fit"),
    }

    # ---- D7: does the note-attributed launch partition differ? -----------
    ours = [r for r in rows if r["user"] == OUR_ACCOUNT]
    parts = {}
    for r in ours:
        nt = r["note"].lower()
        h = tuple(sorted(x for x in ("maple", "cedar", "birch") if x in nt))
        parts.setdefault("+".join(h) if h else "unattributed", []).append(r)
    blocks = {}
    for lab, v in sorted(parts.items()):
        if len(v) < 2:
            continue
        s = st.stdev([r["lnL"] for r in v]) * 100.0
        lo, hi = sd_ci(s, len(v) - 1)
        blocks[lab] = {"n": len(v), "sd_lnL_pct": s, "ci_pct": [lo, hi],
                       "dof": len(v) - 1,
                       "rel_se_of_sd": rel_se_of_sd(len(v))}
    res["D7_launch_partition"] = {
        "blocks": blocks,
        "maple_vs_unattributed": (
            f_two_sided((blocks["maple"]["sd_lnL_pct"] / 100.0) ** 2,
                        blocks["maple"]["dof"],
                        (blocks["unattributed"]["sd_lnL_pct"] / 100.0) ** 2,
                        blocks["unattributed"]["dof"])
            if "maple" in blocks and "unattributed" in blocks else None),
        "note": ("Rule 93.4(3) measured sd(f) 0.4778 % maple (n=44) against "
                 "0.5868 % residual (n=41) on the account's 85 scored "
                 "receipts and expected no significance; this is the same "
                 "test on the frozen corpus's own attribution"),
    }

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as fh:
        json.dump(res, fh, indent=1, sort_keys=True)
    print(json.dumps(res, indent=1, sort_keys=True))
    print("\nwrote " + OUT)


if __name__ == "__main__":
    main()
