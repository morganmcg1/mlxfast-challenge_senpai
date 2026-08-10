#!/usr/bin/env python3
"""Research-only (PR #597, R106-E): publish the fixed-tree noise measurement.

The chartered design -- resubmit one fixed compiled tree n>=4 times under
distinct commit SHAs -- is impossible: the official channel content-addresses
submissions on the uploaded editablePaths payload, so draw 2 replayed draw 1's
receipt (section 12 of the write-up). The substitute estimator uses the pinned
baseline, which *is* a fixed tree re-measured in every ranked session, and
reaches n = 1220 at zero channel cost (section 13).

Consumes the JSON written by `maple-frieren-r106e-legnoise.py`. Nothing is
recomputed here beyond the record re-pricing, so W&B and the on-disk artefact
cannot disagree.

Usage: maple-frieren-r106e-wandb.py LEGNOISE_JSON [WRITEUP_MD]
"""
from __future__ import annotations

import json
import math
import subprocess
import sys
from pathlib import Path

import wandb

PROJECT = "mlxfast-maple"
ENTITY = "wandb-applied-ai-team"
RUN_ID = "x5nontxm"

HYPOTHESES = {
    "H1_near_replicate_pair": 0.2494,
    "H2_session_factor_555": 0.5393,
    "H3_pooled_cross_code_residual": 1.2244,
}
RECORD = 2.61650354381456
BEST_DRAW = 2.590559
# Mean of ln(officialScore / cs) over the 1220 scored sessions; the X constant
# was calibrated to make this ~0, and it is reported rather than assumed.
MEAN_LN_SESSION_FACTOR_PCT = -0.0104

# Draw 1 official metrics, read back from the submissions feed with
# `maple-frieren-r106e-draws.py`. cs/f are recomputed there from the raw legs.
DRAW1 = {
    "cs": 2.574073,
    "official_score": 2.5938073513119,
    "baseline_decode_us_step": 13869.2998,
    "baseline_prefill_us_tok": 382.8416,
    "session_factor_f": 1.0076665,
    "cand_decode_us_step": 4931.3688,
    "cand_prefill_us_tok": 188.1609,
    "decode_speedup": 2.8124645124005556,
    "prefill_speedup": 2.0346500031788994,
    "passed_correctness": True,
    "max_abs_diff": 0,
    "rejection_reason": "score did not improve current best",
    "submission_commit_sha_reported": "dbd0b684c9abb9052720269250ff504ca2e421e9",
}

DRAWS = [
    {"draw": 1, "tag": "R106E-DRAW-01-8db6ffaf",
     "commit": "8db6ffaf1c67f6044711c2aa198ec3b3922553fd",
     "submission": "2771067f-54b4-4e73-aa4f-f2b01d322c02",
     "fired": "2026-08-10T08:54:49Z", "status": "rejected",
     "outcome": "scored", "note_stored": True, "metrics": DRAW1},
    {"draw": 2, "tag": "R106E-DRAW-02-ae12fdb3",
     "commit": "ae12fdb397270061cc07e79b7f4b432d4af75c84",
     "submission": "2771067f-54b4-4e73-aa4f-f2b01d322c02",
     "fired": "2026-08-10T09:18:21Z", "status": "rejected",
     "outcome": "dedup no-op (draw 1 receipt replayed)", "note_stored": False,
     "metrics": None},
]

# P(a fresh draw of a tree takes the record), with the estimation penalty for
# knowing that tree's cs from only m prior draws.
TICKETS = [
    ("A: redraw the live base", DRAW1["cs"], 1),
    ("B: redraw best-ever 4b0e051b", BEST_DRAW, 1),
    ("C: A and B pooled as one tree",
     math.exp(0.5 * (math.log(DRAW1["cs"]) + math.log(BEST_DRAW))), 2),
]


def norm_sf(z: float) -> float:
    return 0.5 * math.erfc(z / math.sqrt(2.0))


def main() -> None:
    legnoise = json.loads(Path(sys.argv[1]).read_text())
    writeup = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(
        "research/maple-frieren-r106e-replication.md")

    groups = legnoise["groups"]
    by_label = {g["label"]: g for g in groups}
    head = by_label["headline_fixed_tree"]
    rho_rows = head["rows"]
    at0 = next(r for r in rho_rows if r["rho"] == 0.0)
    at1 = next(r for r in rho_rows if r["rho"] == 1.0)
    sf = by_label["session_factor_reconstruction"]
    allsess = by_label["All scored sessions"]

    commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True,
                            text=True).stdout.strip()
    gap_pct = 100 * math.log(RECORD / BEST_DRAW)

    config = {
        "experiment": "R106-E fixed-tree noise measurement",
        "assignment": "maple-r105-b-router-prefetch-adjudication",
        "revision": "r105-b-rev4",
        "pr": 597,
        "student": "maple-frieren",
        "chartered_design": "one fixed compiled tree, byte-identical in "
                            "Sources/ and Vendor/, submitted n>=4 times under "
                            "distinct commit SHAs",
        "chartered_design_status": "IMPOSSIBLE - channel deduplicates on the "
                                   "uploaded editablePaths payload, not on "
                                   "submissionCommitSha",
        "substitute_estimator": "pinned baseline legs, which are a fixed tree "
                                "re-measured every ranked session",
        "research_base": "7491001264832c2566de65c5cab9f363c6426e09",
        "wrapper_base_sha": "1bc1c8954147c9e322aad1f3b80bd9fa3c0888d7",
        "head_at_publish": commit,
        "submitted_surface_sha256":
            "fcd5063faa5f4b142c0b6157e3b3e32f3d628a52aa5171b9dd8212757a8948e8",
        "submitted_surface_files": 142,
        "submitted_surface_bytes": 2680208,
        "draws_fired": len(DRAWS),
        "draws_scored": 1,
        "n_sessions": legnoise["n_usable"],
        "record_score": RECORD,
        "best_draw_score": BEST_DRAW,
        "record_gap_log_pct": gap_pct,
        "hypotheses_under_adjudication_pct": HYPOTHESES,
        "protocol": "Rule 88 watch-until-idle, single shot, never retry",
    }

    run = wandb.init(entity=ENTITY, project=PROJECT, config=config,
                     id=RUN_ID, resume="allow",
                     job_type="channel-noise-measurement",
                     name="r106e-fixed-tree-noise",
                     tags=["r106", "r106-e", "maple-frieren", "pr597",
                           "measurement-only", "m5-official", "channel-sigma",
                           "noise-model"],
                     notes="Adjudicates sigma(ln cs | fixed tree). The three "
                           "campaign figures (0.2494 / 0.5393 / 1.2244 %) are "
                           "not estimates of one parameter. Answer: "
                           "sigma(ln cs) ~ 0.74 %, sigma(ln officialScore) ~ "
                           "1.20 %.")

    dtbl = wandb.Table(columns=["draw", "tag", "commit", "submission", "fired",
                                "status", "outcome", "note_stored", "cs",
                                "official_score", "session_factor_f",
                                "baseline_decode_us_step",
                                "baseline_prefill_us_tok",
                                "cand_decode_us_step", "cand_prefill_us_tok",
                                "decode_speedup", "prefill_speedup",
                                "passed_correctness", "max_abs_diff"])
    for d in DRAWS:
        m = d["metrics"] or {}
        dtbl.add_data(d["draw"], d["tag"], d["commit"][:12], d["submission"],
                      d["fired"], d["status"], d["outcome"], d["note_stored"],
                      m.get("cs"), m.get("official_score"),
                      m.get("session_factor_f"),
                      m.get("baseline_decode_us_step"),
                      m.get("baseline_prefill_us_tok"),
                      m.get("cand_decode_us_step"),
                      m.get("cand_prefill_us_tok"),
                      m.get("decode_speedup"), m.get("prefill_speedup"),
                      m.get("passed_correctness"), m.get("max_abs_diff"))
    run.log({"draws": dtbl})

    sd_cs, sd_f = at0["sd_ln_cs_pct"], sf["sd_ln_sf_pct"]
    mu_f = MEAN_LN_SESSION_FACTOR_PCT
    ttbl = wandb.Table(columns=["ticket", "cs_estimate", "m_prior_draws",
                                "sd_ln_score_pct", "z_vs_record",
                                "p_takes_record"])
    for label, cs_hat, m in TICKETS:
        sd = math.sqrt(sd_cs ** 2 * (1 + 1.0 / m) + sd_f ** 2)
        z = (100 * math.log(RECORD / cs_hat) - mu_f) / sd
        ttbl.add_data(label, cs_hat, m, sd, z, norm_sf(z))
    run.log({"ticket_pricing": ttbl})

    ltbl = wandb.Table(columns=["quantity", "n", "sd_pct", "robust_sd_pct",
                                "lag1"])
    win = {g["label"]: g for g in groups if g["label"].startswith("window ")}
    wall = win["window all"]
    ltbl.add_data("ln baseline decode leg", allsess["n"],
                  allsess["sd_ln_bd_pct"], wall["robust_sd_ln_bd_pct"],
                  allsess["lag1_ln_bd"])
    ltbl.add_data("ln baseline prefill leg", allsess["n"],
                  allsess["sd_ln_bp_pct"], wall["robust_sd_ln_bp_pct"],
                  allsess["lag1_ln_bp"])
    run.log({"baseline_legs": ltbl})

    wtbl = wandb.Table(columns=["window", "n", "sd_ln_bd_pct", "sd_ln_bp_pct",
                                "robust_sd_ln_bd_pct", "robust_sd_ln_bp_pct"])
    for g in groups:
        if g["label"].startswith("window "):
            wtbl.add_data(g["label"][7:], g["n"], g["sd_ln_bd_pct"],
                          g["sd_ln_bp_pct"], g["robust_sd_ln_bd_pct"],
                          g["robust_sd_ln_bp_pct"])
    run.log({"stationarity": wtbl})

    rtbl = wandb.Table(columns=["rho", "sd_ln_cs_pct", "sd_ln_score_pct",
                                "z_vs_record", "p_one_draw_beats_record"])
    for r in rho_rows:
        s = r["sd_ln_S_pct"]
        z = gap_pct / s if s > 0 else float("inf")
        rtbl.add_data(r["rho"], r["sd_ln_cs_pct"], s, z, norm_sf(z))
    run.log({"sigma_vs_rho": rtbl})

    ptbl = wandb.Table(columns=["assumption", "sd_ln_score_pct", "z",
                                "p_one_draw_beats_record"])
    for label, s in (("campaign current (rho = 1)", at1["sd_ln_S_pct"]),
                     ("section 10 first correction", 0.5942),
                     ("this work (rho = 0)", at0["sd_ln_S_pct"])):
        z = gap_pct / s
        ptbl.add_data(label, s, z, norm_sf(z))
    run.log({"record_repricing": ptbl})

    htbl = wandb.Table(columns=["hypothesis", "value_pct", "what_it_is",
                                "verdict"])
    htbl.add_data("H1 near-replicate pair", HYPOTHESES["H1_near_replicate_pair"],
                  "one near-replicate pair, dof 1",
                  "too small by ~3x; within noise of the decode leg alone")
    htbl.add_data("H2 session_factor (#555)", HYPOTHESES["H2_session_factor_555"],
                  "sd(ln session_factor), baseline-only",
                  "correct for what it measures, but it is the rho = 1 corner")
    htbl.add_data("H3 pooled cross-code residual",
                  HYPOTHESES["H3_pooled_cross_code_residual"],
                  "pooled residual across differing code",
                  "approximately right for sigma(ln S | fixed tree); not "
                  "meaningfully inflated by code differences")
    run.log({"adjudication": htbl})

    prefill_share = sf["prefill_share"]
    summary = {
        "n_sessions": legnoise["n_usable"],
        "sd/baseline_decode_leg_pct": allsess["sd_ln_bd_pct"],
        "sd/baseline_prefill_leg_pct": allsess["sd_ln_bp_pct"],
        "corr/baseline_legs_within_session": allsess["corr_legs"],
        "lag1/baseline_decode_leg": allsess["lag1_ln_bd"],
        "lag1/baseline_prefill_leg": allsess["lag1_ln_bp"],
        "sd/session_factor_reconstructed_pct": sf["sd_ln_sf_pct"],
        "sd/session_factor_published_pct": HYPOTHESES["H2_session_factor_555"],
        "validation/session_factor_rel_error":
            abs(sf["sd_ln_sf_pct"] / HYPOTHESES["H2_session_factor_555"] - 1),
        "share/session_factor_variance_from_prefill_leg": prefill_share,
        "sigma/ln_cs_fixed_tree_pct": at0["sd_ln_cs_pct"],
        "sigma/ln_score_fixed_tree_pct": at0["sd_ln_S_pct"],
        "sigma/ln_score_rho1_pct": at1["sd_ln_S_pct"],
        "record_gap_log_pct": gap_pct,
        "p_record/campaign_rho1": norm_sf(gap_pct / at1["sd_ln_S_pct"]),
        "p_record/this_work_rho0": norm_sf(gap_pct / at0["sd_ln_S_pct"]),
        "p_record/underestimate_factor":
            norm_sf(gap_pct / at0["sd_ln_S_pct"])
            / norm_sf(gap_pct / at1["sd_ln_S_pct"]),
        "h3_prediction_rel_error":
            abs(at0["sd_ln_S_pct"] / HYPOTHESES["H3_pooled_cross_code_residual"]
                - 1),
        "draw1/cs": DRAW1["cs"],
        "draw1/official_score": DRAW1["official_score"],
        "draw1/baseline_decode_us_step": DRAW1["baseline_decode_us_step"],
        "draw1/baseline_prefill_us_tok": DRAW1["baseline_prefill_us_tok"],
        "draw1/session_factor_f": DRAW1["session_factor_f"],
        "draw1/session_factor_z":
            (100 * math.log(DRAW1["session_factor_f"])
             - MEAN_LN_SESSION_FACTOR_PCT) / sf["sd_ln_sf_pct"],
        "draw1/passed_correctness": DRAW1["passed_correctness"],
        "draw1/gap_to_best_ever_cs_pct": 100 * math.log(BEST_DRAW / DRAW1["cs"]),
        "draw1/gap_to_best_ever_in_sigma":
            100 * math.log(BEST_DRAW / DRAW1["cs"]) / at0["sd_ln_cs_pct"],
        "channel/dedup_confirmed": True,
        "channel/ladder_feasible": False,
        "verdict": "sigma(ln cs | fixed tree) ~ 0.74 %; sigma(ln officialScore "
                   "| fixed tree) ~ 1.20 %; H3 is approximately correct and "
                   "the campaign has implicitly been assuming rho = 1",
    }
    for k, v in HYPOTHESES.items():
        summary[f"ratio_vs/{k}"] = at0["sd_ln_cs_pct"] / v

    wt_path = Path("research/maple-frieren-r106e-withintree.json")
    rc_path = Path("research/maple-frieren-r106e-record-check.json")
    if wt_path.exists():
        wt = json.loads(wt_path.read_text())
        wtbl = wandb.Table(columns=["marker", "commit", "created", "cs",
                                    "official_score", "session_factor_f_pct",
                                    "baseline_decode_us_step",
                                    "baseline_prefill_us_tok",
                                    "cand_decode_us_step",
                                    "cand_prefill_us_tok", "recon_official"])
        for d in wt["draws"]:
            wtbl.add_data(d["marker"], d["commit"][:12], d["created_at"],
                          d["cs"], d["official_score"], d["f_pct"],
                          1e6 * d["baseline_decode_s"],
                          1e6 * d["baseline_prefill_s"],
                          1e6 * d["decode_s"], 1e6 * d["prefill_s"],
                          d["recon_official"])
        run.log({"within_tree_draws": wtbl})

        ptbl = wandb.Table(columns=["anchor", "sigma_model", "cs", "gap_pct",
                                    "sigma_pct", "z", "p_record_per_draw",
                                    "expected_draws"])
        for anchor in ("null1", "replicate_mean"):
            for model in ("corpus", "naive", "paired"):
                r = wt[f"p_record_{anchor}_{model}"]
                ptbl.add_data(anchor, model, r["cs"], r["gap_pct"],
                              r["sigma_pct"], r["z"], r["p"], r["e_draws"])
        run.log({"p_record_matrix": ptbl})

        stbl = wandb.Table(columns=["statistic", "value_pct", "ci_lo", "ci_hi",
                                    "interpretation"])
        stbl.add_data("sd(ln cs) within fixed tree", wt["sd_ln_cs_pct"],
                      *wt["sd_ln_cs_ci"],
                      "candidate-only noise after same-session pairing")
        stbl.add_data("sd(session factor f)", wt["sd_f_pct"], *wt["sd_f_ci"],
                      "session noise carried by the pinned baseline legs")
        stbl.add_data("sd(ln officialScore) within fixed tree",
                      wt["sd_ln_official_pct"], *wt["sd_ln_official_ci"],
                      "what actually governs the record lottery")
        stbl.add_data("sd(ln baseline decode leg)",
                      wt["sd_ln_bl_decode_pct"], float("nan"), float("nan"),
                      "n=5 within-tree")
        stbl.add_data("sd(ln baseline prefill leg)",
                      wt["sd_ln_bl_prefill_pct"], float("nan"), float("nan"),
                      "n=5 within-tree; prefill leg dominates f")
        run.log({"within_tree_sigma": stbl})

    if rc_path.exists():
        rc = json.loads(rc_path.read_text())
        ctbl = wandb.Table(columns=["rank_by_cs", "commit", "submission",
                                    "created", "cs", "official_score",
                                    "session_factor_f_pct", "attribution"])
        for i, r in enumerate(rc["by_cs"], 1):
            ctbl.add_data(i, r["commit"], r["id"], r["created"], r["cs"],
                          r["official"], r["f_pct"],
                          (r.get("note") or "")[:300])
        run.log({"top_by_cs": ctbl})

        cen = rc["census"]
        ltbl = wandb.Table(columns=["quantity", "value"])
        for k, v in cen.items():
            ltbl.add_data(k, v)
        ltbl.add_data("record_cs_rank", rc["record_cs_rank"])
        ltbl.add_data("scored_sessions", rc["scored"])
        run.log({"lottery_census": ltbl})

    if wt_path.exists():
        def sd_ln_pct(key):
            v = [math.log(d[key]) for d in wt["draws"]]
            m = sum(v) / len(v)
            return 100 * math.sqrt(sum((x - m) ** 2 for x in v) / (len(v) - 1))

        summary.update({
            "within_tree/sd_ln_cand_decode_leg_pct": sd_ln_pct("decode_s"),
            "within_tree/sd_ln_cand_prefill_leg_pct": sd_ln_pct("prefill_s"),
            "within_tree/sd_ln_baseline_decode_leg_pct":
                wt["sd_ln_bl_decode_pct"],
            "within_tree/sd_ln_baseline_prefill_leg_pct":
                wt["sd_ln_bl_prefill_pct"],
            "within_tree/baseline_over_cand_prefill_noise_ratio":
                wt["sd_ln_bl_prefill_pct"] / sd_ln_pct("prefill_s"),
            "within_tree/n": wt["n"],
            "within_tree/reconstruction_max_rel_err":
                wt["reconstruction_max_rel_err"],
            "within_tree/sd_ln_cs_pct": wt["sd_ln_cs_pct"],
            "within_tree/sd_session_factor_pct": wt["sd_f_pct"],
            "within_tree/sd_ln_official_pct": wt["sd_ln_official_pct"],
            "within_tree/mean_session_factor_pct": wt["mean_f_pct"],
            "within_tree/corr_ln_decode_vs_baseline_decode": wt["H0a_corr_dec"],
            "within_tree/corr_ln_cs_vs_session_factor": wt["corr_lncs_f"],
            "within_tree/session_pass_through": wt["session_pass_through"],
            "within_tree/sd_ln_official_implied_by_slope_pct":
                wt["sd_lnos_implied_by_slope_pct"],
            "within_tree/H0b_chi2": wt["H0b_chi2_stat"],
            "within_tree/H0b_reject_below_at_5pct":
                wt["H0b_reject_below_at_5pct"],
            "within_tree/winners_curse_bias_pct": wt["winners_curse_bias_pct"],
            "within_tree/sigma_naive_unpaired_pct": wt["sigma_naive_pct"],
            "p_record/headline_per_draw": wt["headline"]["p"],
            "p_record/headline_expected_draws": wt["headline"]["e_draws"],
            "p_record/headline_ci_lo": wt["headline"]["p_at_sd_ci_lo"],
            "p_record/headline_ci_hi": wt["headline"]["p_at_sd_ci_hi"],
            "p_record/advisor_prior_per_draw":
                wt["p_record_null1_corpus"]["p"],
            "record_holder/session_factor_pct":
                wt["record_holder"]["f_pct"],
            "record_holder/session_factor_z":
                wt["record_holder"]["z_vs_corpus_sd_f"],
            "record_holder/our_cs_lead_pct":
                wt["record_holder"]["our_cs_lead_pct"],
            "record_holder/expected_max_f_over_corpus_pct":
                wt["record_holder"]["expected_max_f_pct"],
        })
    if rc_path.exists():
        summary.update({
            "corpus/n_scored": rc["scored"],
            "corpus/sd_session_factor_pct": cen["corpus_sd_f_pct"],
            "corpus/mean_session_factor_pct": cen["corpus_mean_f_pct"],
            "corpus/corr_ln_cs_vs_session_factor": cen["corpus_corr_lncs_f"],
            "corpus/record_cs_rank": rc["record_cs_rank"],
            "lottery/n_top_cs_receipts": cen["n_band"],
            "lottery/n_record_beating": cen["n_record_beating"],
            "lottery/band_sd_session_factor_pct": cen["band_f_sd_pct"],
            "lottery/required_f_median_pct": cen["required_f_median_pct"],
            "lottery/p_max_le_observed_given_corpus_sd":
                cen["p_max_le_observed_given_corpus_sd"],
        })
        summary["verdict"] = (
            "RETRACTED by the direct n=5 within-tree measurement: the "
            "corpus + rho=0 route overstated both sigmas by ~3x. Use "
            f"sd(ln cs | fixed tree) = {wt['sd_ln_cs_pct']:.4f} % and "
            f"sd(ln officialScore | fixed tree) = "
            f"{wt['sd_ln_official_pct']:.4f} %.")
        summary["verdict_r106e_final"] = (
            "Same-session pairing cancels ~34 % of session noise: within a "
            "fixed tree sd(ln officialScore) = "
            f"{wt['sd_ln_official_pct']:.4f} %, not the corpus sd(f) = "
            f"{cen['corpus_sd_f_pct']:.4f} %. Independent confirmation: the "
            f"top-cs cohort shows sd(f) = {cen['band_f_sd_pct']:.4f} %. "
            f"P(record)/draw for our best tree is {wt['headline']['p']:.6%} "
            f"(E ~ {wt['headline']['e_draws']:.0f} draws), and "
            f"{cen['n_band']} top-cs receipts have produced "
            f"{cen['n_record_beating']} record-beating draws. Buying draws is "
            "not a route to the record; raising cs by ~1.28 % is.")

    art = wandb.Artifact("r106e-fixed-tree-noise", type="measurement")
    art.add_file(sys.argv[1], name="legnoise.json")
    if writeup.exists():
        art.add_file(str(writeup), name="replication-writeup.md")
    for extra in ("research/maple-frieren-r106e-legnoise.py",
                  "research/maple-frieren-r106e-stats.py",
                  "research/maple-frieren-r106e-ladder.py",
                  "research/maple-frieren-r106e-note.py",
                  "research/maple-frieren-r106e-payload-digest.py",
                  "research/maple-frieren-r106e-draws.py",
                  "research/maple-frieren-r106e-draw.sh",
                  "research/maple-frieren-r106e-withintree.py",
                  "research/maple-frieren-r106e-withintree.json",
                  "research/maple-frieren-r106e-record-check.py",
                  "research/maple-frieren-r106e-record-check.json",
                  "research/maple-frieren-r106e-surface-compare.py"):
        if Path(extra).exists():
            art.add_file(extra, name=Path(extra).name)
    run.log_artifact(art)

    run.summary.update(summary)
    print(f"W&B run: {run.url}  id={run.id}")
    run.finish()


if __name__ == "__main__":
    main()
