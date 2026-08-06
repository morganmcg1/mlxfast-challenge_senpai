#!/usr/bin/env python3
"""Report one PR #137 receipt on both the score axis and the decode axis.

    python3 /tmp/pr137_submit/analyze_receipt.py <submission_id>

Uses the cheap single-row endpoint, not the 17 MB feed.
"""
import json
import os
import sys
import urllib.request

ROW = "https://api.mlx.fast/api/submissions/"

NORM_DECODE = 0.013890
NORM_PREFILL = 0.0003845

# Ranking bar: db8b4df1 / 26b46535 (2026-08-06T21:47Z), confirmed against the
# benchmark endpoint's currentBestScore.
BEST_NS = 2.59018571539341
BEST_DSPD = 2.818908868713026
GO_NS = 2.6045
KILL_NS = 2.5919

# Promoted maple reference: 97a5090c / 3e165fa5 (2026-08-06T05:14Z receipt).
PROMOTED_NS = 2.58882784082067
PROMOTED_DECODE_MS = 4.9083720703125
PROMOTED_DSPD = 2.82068398043601
PROMOTED_PSPD = 2.0014713863613727
PROMOTED_T_MS = 4.143569335937499
PROMOTED_S_MS = 97.89475

PAIRED_BASELINE_DECODE_MS = 13.84496646875
M4_CENSUS_US = 63.7
ELASTICITY_PCT_PER_US = 0.01464

# Fixed-normaliser scores of the two reference receipts.  These drop the
# paired baseline draw, which section 13 shows is uncorrelated with the
# candidate and therefore pure added noise.
BEST_NS_FIXED = 2.59596813
BEST_NSD = 2.17645653
PROMOTED_NS_FIXED = 2.59821630
PROMOTED_NSD = 2.18184340

# Instrument noise from the two documented identical-tree replicate triplets
# (f8502e12/71586bcf/f3cda678 and 5d522d6a/5e0e9cd1/c210d200; 6 rows, 4 dof).
# Section 13.11: the 27-cluster estimates are contaminated by real code
# differences on the candidate axes and are upper bounds, not noise.
SD_SCORE_PCT = 0.559
SD_NS_PCT = 0.138
SD_NSD_PCT = 0.148
SD_DSPD_PCT = 0.361
SD_DECODE_PCT = 0.197

# Score-axis size of a full-transfer (t = 1) effect, from the section 11.5
# elasticity: 63.7 us * 0.01464 %/us.
EFFECT_SCORE_PCT = M4_CENSUS_US * ELASTICITY_PCT_PER_US
EFFECT_DECODE_PCT = EFFECT_SCORE_PCT / 0.75


def ns_of(prefill, decode):
    return ((NORM_DECODE / decode) ** 0.75) * ((NORM_PREFILL / prefill) ** 0.25)


def fetch(sid):
    tok = os.environ["MLXFAST_API_TOKEN"]
    req = urllib.request.Request(ROW + sid,
                                 headers={"Authorization": f"Bearer {tok}"})
    raw = json.load(urllib.request.urlopen(req))
    return raw.get("submission", raw)


def transfer(obs_pct, effect_pct, sd_ref_pct):
    """Point estimate and 1-sigma for the M4->M5 transfer factor.

    obs_pct is the observed improvement of this receipt over a reference
    receipt.  Both receipts are single draws, so the difference carries
    sqrt(2) times the single-receipt sd.
    """
    sd_diff = sd_ref_pct * (2 ** 0.5)
    return obs_pct / effect_pct, sd_diff / effect_pct


def main():
    sid = sys.argv[1]
    hit = fetch(sid)
    met = hit.get("officialMetrics") or {}

    print(f"submission        {hit.get('id')}")
    print(f"status            {hit.get('status')}")
    print(f"commit            {met.get('commit')}")
    print(f"officialScore     {hit.get('officialScore')}")
    print(f"improved          {hit.get('improved')}")
    print(f"promotionStatus   {hit.get('promotionStatus')}")
    print(f"promotionReason   {hit.get('promotionReason')!r}")
    print(f"rejectionReason   {hit.get('rejectionReason')!r}")
    print(f"createdAt         {hit.get('createdAt')}   updatedAt {hit.get('updatedAt')}")
    print(f"error             {met.get('error')!r}")
    print()
    for k in sorted(met):
        if k not in ("commit", "runtime", "error"):
            print(f"  {k} = {met[k]}")
    print()

    d = met.get("decode_seconds_per_token")
    p = met.get("prefill_seconds_per_token")
    if d is None or p is None:
        print("!! no candidate seconds published -- redacted receipt.")
        print("   A ranking-only rejection publishes full metrics, so a")
        print("   redacted receipt means a correctness or floor failure.")
        return

    score = hit.get("officialScore")
    ns = ns_of(p, d)
    nsd = (NORM_DECODE / d) ** 0.75
    dms = 1000.0 * d
    S = 512000.0 * p
    T = 1000.0 * d - S / 128.0
    dspd = met.get("decode_speedup")
    pspd = met.get("prefill_speedup")

    print("--- PRIMARY: ns, fixed normalisers (advisor's pre-registered band) ---")
    print(f"ns                {ns:.8f}   [1 sigma = {SD_NS_PCT} %]")
    print(f"  vs 97a5090c {PROMOTED_NS_FIXED:.8f}"
          f"   {(ns / PROMOTED_NS_FIXED - 1) * 100:+.3f} %")
    print(f"  GO   >= {GO_NS}   -> {'GO' if ns >= GO_NS else 'no'}")
    print(f"  KILL <  {KILL_NS}   -> {'KILL' if ns < KILL_NS else 'no'}")
    if KILL_NS <= ns < GO_NS:
        print("  -> inside the pre-registered adjudication window;"
              " advisor adjudicates on the transfer factor")
    t, sdt = transfer((ns / PROMOTED_NS_FIXED - 1) * 100, EFFECT_SCORE_PCT, SD_NS_PCT)
    print(f"  implied transfer  {t:+.2f} +- {sdt:.2f}")
    print(f"  vs bar   {BEST_NS_FIXED:.8f}   {(ns / BEST_NS_FIXED - 1) * 100:+.3f} %")
    print()

    print("--- ranking axis: officialScore (decides promotion, not the arm) ---")
    print(f"officialScore     {score:.8f}")
    print(f"  vs bar {BEST_NS:.8f}   {score - BEST_NS:+.8f}"
          f"  ({(score / BEST_NS - 1) * 100:+.3f} %)   [1 sigma = {SD_SCORE_PCT} %]")
    print(f"  -> {'beats' if score > BEST_NS else 'does not beat'} the ranking bar")
    print(f"  vs promoted 97a5090c {PROMOTED_NS:.8f}"
          f"   {(score / PROMOTED_NS - 1) * 100:+.3f} %")
    t, sdt = transfer((score / PROMOTED_NS - 1) * 100, EFFECT_SCORE_PCT, SD_SCORE_PCT)
    print(f"  implied transfer  {t:+.2f} +- {sdt:.2f}   (4x looser: see 13.11)")
    print()

    print("--- corroborating decode axis (section 13.8) ---")
    print(f"nsd = (norm/d)^.75 {nsd:.8f}   [1 sigma = {SD_NSD_PCT} %]")
    print(f"  vs bar   {BEST_NSD:.8f}   {(nsd / BEST_NSD - 1) * 100:+.3f} %")
    print(f"  vs 97a5090c {PROMOTED_NSD:.8f}   {(nsd / PROMOTED_NSD - 1) * 100:+.3f} %")
    t, sdt = transfer((nsd / PROMOTED_NSD - 1) * 100,
                      EFFECT_SCORE_PCT, SD_NSD_PCT)
    print(f"  implied transfer  {t:+.2f} +- {sdt:.2f}")
    print(f"candidate decode  {d}   ({dms:.6f} ms)")
    print(f"  vs 97a5090c     {PROMOTED_DECODE_MS:.6f} ms"
          f"   {(PROMOTED_DECODE_MS - dms) * 1000.0:+.1f} us"
          f"   ({(1.0 - dms / PROMOTED_DECODE_MS) * 100:+.3f} %)"
          f"   [1 sigma = {SD_DECODE_PCT} %]")
    print(f"  T saving implied by that delta: "
          f"{(PROMOTED_DECODE_MS - dms) * 1000.0:+.1f} us of the {M4_CENSUS_US} us M4 census")
    if dspd:
        print(f"decode_speedup    {dspd}")
        print(f"  vs 97a5090c     {PROMOTED_DSPD:.6f}"
              f"   {(dspd / PROMOTED_DSPD - 1) * 100:+.3f} %"
              f"   [1 sigma = {SD_DSPD_PCT} %]")
        t, sdt = transfer((dspd / PROMOTED_DSPD - 1) * 100,
                          EFFECT_DECODE_PCT, SD_DSPD_PCT)
        print(f"  implied transfer  {t:+.2f} +- {sdt:.2f}")
        print(f"  vs bar dspd     {BEST_DSPD:.6f}   {(dspd / BEST_DSPD - 1) * 100:+.3f} %")
    print("  caveat: the reference tree is 6 promoted maple merges behind this")
    print("          candidate, so this transfer estimate is our mechanism plus")
    print("          the unmeasured M5 effect of those merges.")
    print()

    print("--- prefill axis (expected flat) ---")
    print(f"candidate prefill {p}   (S = {S:.5f} ms, promoted {PROMOTED_S_MS})")
    if pspd:
        print(f"prefill_speedup   {pspd}   vs 97a5090c {PROMOTED_PSPD:.6f}"
              f"   {(pspd / PROMOTED_PSPD - 1) * 100:+.3f} %   [1 sigma = 2.45 %, all of it the baseline draw]")
    print(f"T (marginal, ms)  {T:.6f}   (promoted {PROMOTED_T_MS})"
          f"   {(T - PROMOTED_T_MS) * 1000.0:+.1f} us")
    print()

    print("--- gates ---")
    for k in ("passed_correctness", "passed_decode_speedup_floor",
              "passed_prefill_speedup_floor", "max_abs_diff", "checked_steps",
              "semantic_gpqa_passed", "gpqa_ttft_passed", "golden_hash"):
        print(f"  {k} = {met.get(k)}")
    print(f"  paired baseline decode  {met.get('baseline_decode_seconds_per_token')}"
          f"   (97a5090c saw {PAIRED_BASELINE_DECODE_MS / 1000.0})")


if __name__ == "__main__":
    main()
