#!/usr/bin/env python3
"""R106-J (PR #597): publish the bit-exactness-shelf adjudication.

Three deliverables, one run:

  A. A reusable **margin certificate**.  Three students were blocked on the
     question "how far from a token flip is a not-bit-exact candidate?".  The
     instrument (research/maple-frieren-r106j-margin-certificate.py) answers it
     with full-vocab logits: perturbation stats, baseline top-1/top-2 margins,
     a safety factor, and an argmax-flip count that must be zero.  It also
     carries the two sections the assignment did not ask for and that turn out
     to matter: a RANK-and-DELTA exposure (TASK.md:131-134 permits a hidden
     anchor to constrain rank, not only argmax) and a hidden-anchor flip-rate
     curve.  Plus a null cell (Rule 79): the same build against itself.

  B. DARKBLOOM_QMV_WIDE_CODES, end to end.  B0 reachability is settled by
     kernel NAME from a GPU-side dispatch trace, not by "the flag was read".
     B1 correctness is zero token flips everywhere.  B2 is a paired ABBA over
     12 independent worker processes, and it says the lever is a REGRESSION of
     -0.5363 % of score.  The invariant control moves by a null, so the
     instrument is not just measuring drift.

  C. The shelf, re-adjudicated by PERTURBATION CLASS instead of by the one-bit
     label "bit-exact / not bit-exact", and ranked by % of score.

The headline is a negative result and it is logged as one.  The lever is left
OFF, no tree is handed to fern, and the two rows that come out on top of the
re-adjudication are rows somebody else closed on an unmeasured label.

Usage: maple-frieren-r106j-wandb.py
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

import wandb

PROJECT = "mlxfast-maple"
ENTITY = "wandb-applied-ai-team"
RUN_ID = "r106jfrieren"

ART = Path("research/artifacts/maple-frieren-r106j")

# Assignment conversion constants (rev5).
PCT_PER_US_STEP = 0.015228   # % of score per us/step of decode
PCT_PER_MS_PREFILL = 0.3781  # % of score per ms of prefill
SHIP_BAR_PCT = 0.4           # endgame sec2 bar


def git(*args: str) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True,
                          check=False).stdout.strip()


def load(name: str) -> dict:
    return json.loads((ART / name).read_text())


def finite(x):
    """The null cell's safety factors are legitimately +inf (zero perturbation
    over a positive margin). W&B tables do not round-trip inf, and writing a
    huge sentinel would be a lie about a quantity whose whole point is that it
    is unbounded, so log None and let the verdict column carry the meaning."""
    return None if x is None or x != x or x in (float("inf"), float("-inf")) else x


def main() -> None:
    os.environ.setdefault("WANDB_DIR", tempfile.mkdtemp(prefix="mf-r106j-wandb-"))

    teacher = load("cert_teacher.json")
    free = load("cert_free.json")
    null = load("cert_null.json")
    abba = load("abba_report.json")

    pb = abba["target_paired_by_block"]
    cpb = abba["control_paired_by_block"]

    config = {
        "round": "R106-J",
        "pr": 597,
        "assignment_id": "maple-r105-b-router-prefetch-adjudication",
        "revision_id": "r105-b-rev5",
        "student": "maple-frieren",
        "branch": git("rev-parse", "--abbrev-ref", "HEAD"),
        "head_commit": git("rev-parse", "HEAD"),
        "lever": "DARKBLOOM_QMV_WIDE_CODES (LagunaRuntimeModel.swift:323-324)",
        "flag_default": "OFF, and it stays OFF",
        "pct_of_score_per_us_step_decode": PCT_PER_US_STEP,
        "pct_of_score_per_ms_prefill": PCT_PER_MS_PREFILL,
        "ship_bar_pct_of_score": SHIP_BAR_PCT,
        "abba_design": "off on on off x 3 blocks, 12 independent processes, "
                       "1 arm per process, 33 teacher-forced steps each",
        "abba_prereg_sigma_us_per_call": 0.10,
        "abba_prereg_mde_pct_of_score": 0.078,
        "golden_case": "longcopy-gate-english-512 (the only public local case)",
        "vocab": 100352,
    }

    run = wandb.init(project=PROJECT, entity=ENTITY, id=RUN_ID,
                     name="r106j-bitexactness-shelf-adjudication",
                     job_type="analysis", config=config, resume="allow")

    # ---- Deliverable A: the certificate ----------------------------------
    # One row per arm of the instrument, including the null cell.  The null
    # cell is the row that makes the other two readable: it establishes that
    # the pipeline is bitwise deterministic, so every differing element in the
    # candidate rows is caused by the lever and by nothing else.
    cert = wandb.Table(columns=[
        "arm", "mode", "positions", "verdict",
        "elements_differing", "elements_compared", "frac_differing",
        "abs_max", "abs_p99", "abs_p50",
        "margin_min", "margin_p1", "margin_p50", "exact_ties",
        "global_safety_factor",
        "decision_relevant_sf_min", "decision_relevant_sf_p1",
        "argmax_flips", "narrow_top8_gaps",
    ])
    for label, c in (("null control (same build twice)", null),
                     ("wide-codes, teacher-forced", teacher),
                     ("wide-codes, free-run 128 steps", free)):
        p, m, s = c["1_perturbation"], c["2_baseline_margin"], c["3_safety_factor"]
        dr = s["decision_relevant"]
        cert.add_data(
            label, c["mode"], c["positions_certified"], c["verdict"],
            p["elements_differing"], p["elements_compared"],
            p["elements_differing"] / p["elements_compared"],
            p["abs_max"], p["abs_p99"], p["abs_p50"],
            m["min"], m["p1"], m["p50"], m["exact_ties"],
            finite(s["global_safety_factor"]),
            finite(dr["min"]), finite(dr["p1"]),
            c["4_argmax_flips"]["flip_count"],
            c["5_rank_delta_exposure"]["gaps_narrower_than_2x_max_perturbation"],
        )
    run.log({"A_certificate": cert})

    # The flip-rate curve is the part of the certificate that answers the
    # question the three blocked students were actually asking.  Zero observed
    # flips on one public prompt is not a bound; this is the extrapolation, and
    # it is labelled as an extrapolation.
    flip = wandb.Table(columns=["anchor_margin", "teacher_flip_rate", "free_run_flip_rate"])
    tf = teacher["3_safety_factor"]["hidden_anchor_exposure"][
        "fraction_of_positions_that_would_flip_at_margin"]
    ff = free["3_safety_factor"]["hidden_anchor_exposure"][
        "fraction_of_positions_that_would_flip_at_margin"]
    for k in sorted(tf, key=float):
        flip.add_data(float(k), tf[k], ff.get(k))
    run.log({"A_hidden_anchor_flip_rate": flip})

    # ---- Deliverable B ----------------------------------------------------
    # B0: reachability, settled by which program the GPU ran.
    b0 = wandb.Table(columns=["arm", "kernel_executed", "dispatch_records"])
    b0.add_data("DARKBLOOM_QMV_WIDE_CODES unset",
                "custom_kernel_laguna_shared_nvfp4_swiglu_qmv_rows1_halved_bf16_v1_", 1328)
    b0.add_data("DARKBLOOM_QMV_WIDE_CODES=1",
                "custom_kernel_laguna_shared_nvfp4_swiglu_qmv_rows1_halved_WIDE_bf16_v1_", 1329)
    run.log({"B0_reachability": b0})

    # B2: the paired result, plus its own control.  Both are reported the same
    # way so the reader can check that the control is null by the same test
    # that calls the target significant.
    b2 = wandb.Table(columns=[
        "kernel", "role", "off_mean_us_per_call", "on_mean_us_per_call",
        "paired_delta_us_per_call", "sd_across_blocks", "se", "t", "df",
        "ci95_lo_us_per_call", "ci95_hi_us_per_call",
        "delta_us_per_step", "pct_of_score", "pct_ci_lo", "pct_ci_hi", "verdict",
    ])
    b2.add_data("laguna_shared_nvfp4_swiglu_qmv_rows1", "TARGET",
                abba["target"]["off_mean"], abba["target"]["on_mean"],
                pb["mean_delta_us_per_call"], pb["sd_across_blocks"], pb["se"],
                pb["t"], pb["df"], pb["ci95_us_per_call"][0], pb["ci95_us_per_call"][1],
                pb["mean_delta_us_per_step"], pb["pct_of_score"],
                pb["pct_of_score_ci95"][0], pb["pct_of_score_ci95"][1],
                "SLOWER, CI excludes zero")
    b2.add_data("routed_shared_nvfp4_down_residual (v6)", "INVARIANT CONTROL",
                abba["control"]["off_mean"], abba["control"]["on_mean"],
                cpb["mean_delta_us_per_call"], cpb["sd_across_blocks"], cpb["se"],
                cpb["t"], cpb["df"], cpb["ci95_us_per_call"][0], cpb["ci95_us_per_call"][1],
                cpb["mean_delta_us_per_step"], cpb["pct_of_score"],
                cpb["pct_of_score_ci95"][0], cpb["pct_of_score_ci95"][1],
                "NULL, CI spans zero")
    run.log({"B2_paired_abba": b2})

    blocks = wandb.Table(columns=["block", "off_us_per_call", "on_us_per_call", "delta"])
    for name, b in pb["blocks"].items():
        blocks.add_data(name, b["off_mean"], b["on_mean"], b["delta"])
    run.log({"B2_blocks": blocks})

    # ---- Deliverable C: the ranked shelf ---------------------------------
    # Value is in % of score for every row so they are commensurable.  The
    # class column is the point of the exercise: "not bit-exact" was doing all
    # the adjudication work before, and it does not distinguish a 1-ULP
    # reassociation from a 5.4-logit rewrite.
    shelf = wandb.Table(columns=[
        "rank", "row", "value_pct_of_score", "perturbation_class",
        "certificate_obtainable", "verdict", "owner"])
    shelf.add_data(1, "split-K tie flip (matmul.cpp:986-989)",
                   "fraction of +2.46..+3.89", "2", "plausibly yes",
                   "RE-OPEN - biggest unpriced number, perturbation class is right",
                   "tanjiro #620")
    shelf.add_data(2, "wider per-lane loads, sliding attention",
                   "+0.51..+1.02", "1-2", "likely yes",
                   "RE-OPEN - blocked five rounds on an unmeasured label", "unassigned")
    shelf.add_data(3, "H3 attention-projection defrag", "+0.9..+2.3", "0/1 and 2",
                   "yes for the class-0/1 half",
                   "SPLIT THE LEVER - ship the bit-exact half with no certificate at all",
                   "tanjiro #620")
    shelf.add_data(None, "#615 lane-major nibble-delta byte coding (NOT on my list)",
                   "~+0.48", "0", "not needed",
                   "RE-OPEN - bit-exact, above the 0.4 % bar, dropped on a byte threshold",
                   "unassigned")
    shelf.add_data(4, "DARKBLOOM_QMV_WIDE_CODES",
                   f"{pb['pct_of_score']:.4f} (measured)", "3 (measured)",
                   "NO - measured and refused",
                   "CLOSE ON EVIDENCE - it is slower AND class-3", "maple-frieren #597")
    shelf.add_data(5, "group-64 scale-plane re-merge (#615)", "+0.37..+0.48", "4", "no",
                   "CLOSE", "unassigned")
    shelf.add_data(6, "router accumulator reassociation", "+0.11, CI spans 0", "1-2",
                   "probably yes", "LEAVE CLOSED - null effect, not a correctness problem",
                   "closed")
    run.log({"C_shelf_ranked": shelf})

    classes = wandb.Table(columns=["class", "what_it_is", "expected_perturbation",
                                   "certificate_likely"])
    classes.add_data(0, "bit-exact: identical FMA sequence and order", "exactly 0", "not needed")
    classes.add_data(1, "reassociation of a short reduction, <=8 terms, one site",
                     "sub-ULP to ~1 ULP", "very likely")
    classes.add_data(2, "reassociation of a long reduction or a whole K-loop",
                     "~1-10 ULP", "plausible, must be measured")
    classes.add_data(3, "reassociation changing WHICH VALUES each lane sums over a long chain",
                     "O(1 logit unit) - comparable to decision margins",
                     "measured NO for wide codes")
    classes.add_data(4, "changes the numerical values (coarser scales, lower precision)",
                     "unbounded by any order argument", "very unlikely")
    run.log({"C_perturbation_classes": classes})

    # ---- the retraction I owe from R107 ----------------------------------
    # A third replicate of the same tree arrived this session.  It makes my own
    # published resubmission-noise estimate too small, which makes my own
    # published overtake probability too large.  Logging it here rather than
    # quietly editing the old run.
    sigma = wandb.Table(columns=["estimator", "n", "sd_ln_O_pct", "z", "p_per_draw_pct",
                                 "p_20_draws_pct", "status"])
    sigma.add_data("r107 sec8 as published", 2, 0.4219, 3.939, 0.004, 0.08,
                   "SUPERSEDED - n=2 is not an estimate")
    sigma.add_data("three replicates of tree 4b0e051b", 3, 0.3016, 5.42, None, None,
                   "ACCEPTED point estimate, df=2, still weak")
    sigma.add_data("under sigma = 0.5396 % (r107 headline)", None, 0.5396, 3.03, 0.12, 2.4,
                   "for comparison")
    sigma.add_data("under sigma = 0.58 %", None, 0.58, 2.82, 0.24, 4.7,
                   "vs sec8's claimed 2.7 %/draw and 42 % over 20 - ~9x overstated")
    run.log({"R107_sigma_retraction": sigma})

    run.summary.update({
        # Deliverable A
        "cert_verdict_teacher": teacher["verdict"],
        "cert_verdict_free_run": free["verdict"],
        "cert_verdict_null_cell": null["verdict"],
        "null_cell_elements_differing": null["1_perturbation"]["elements_differing"],
        "pipeline_bitwise_deterministic": null["1_perturbation"]["bitwise_identical"],
        "max_abs_delta_logit": teacher["1_perturbation"]["abs_max"],
        "min_baseline_margin": teacher["2_baseline_margin"]["min"],
        "global_safety_factor": finite(teacher["3_safety_factor"]["global_safety_factor"]),
        "decision_relevant_safety_factor_min":
            finite(teacher["3_safety_factor"]["decision_relevant"]["min"]),
        "argmax_flips_teacher": teacher["4_argmax_flips"]["flip_count"],
        "argmax_flips_free_run": free["4_argmax_flips"]["flip_count"],
        "free_run_common_prefix": free["7_free_run"].get("common_prefix_length"),
        # Deliverable B
        "b0_reachable": True,
        "b1_token_flips": 0,
        "b2_delta_us_per_call": pb["mean_delta_us_per_call"],
        "b2_delta_us_per_step": pb["mean_delta_us_per_step"],
        "b2_pct_of_score": pb["pct_of_score"],
        "b2_pct_of_score_ci95": pb["pct_of_score_ci95"],
        "b2_t": pb["t"],
        "b2_control_pct_of_score": cpb["pct_of_score"],
        "b2_control_ci_spans_zero":
            cpb["ci95_us_per_call"][0] < 0 < cpb["ci95_us_per_call"][1],
        "b2_wallclock_cross_check_us_per_step": 37.2,
        "outcome_primary": "N-NULL (negative sign)",
        "outcome_secondary": "N-CORRECT (independent of B2)",
        "b3_executed": False,
        "tree_handed_to_fern": False,
        "rule75_digest_owed": False,
        "distance_below_ship_bar_pct": SHIP_BAR_PCT - pb["pct_of_score"],
        # Deliverable C
        "shelf_top_row": "split-K tie flip (tanjiro #620)",
        "shelf_rows_reopened": 3,
        "shelf_rows_closed": 3,
        "shelf_row_not_on_my_list_flagged": "#615 lane-major nibble-delta, class 0, ~+0.48 %",
        # R107 retraction
        "sigma_resubmit_3rep_pct": 0.3016,
        "r107_sec8_retracted": True,
    })

    for name in ("research/maple-frieren-r106j-bitexactness-shelf.md",
                 "research/maple-frieren-r106j-margin-certificate.py",
                 "research/maple_frieren_r106j_wide_codes_abba.sh",
                 "research/maple_frieren_r106j_abba_analyse.py",
                 "research/maple_frieren_r106j_b1_rerun.sh",
                 "research/maple-frieren-r107-session-noise.md"):
        p = Path(name)
        if p.exists():
            art = wandb.Artifact(p.stem.replace(".", "-"), type="report")
            art.add_file(str(p))
            run.log_artifact(art)

    ev = wandb.Artifact("r106j-evidence", type="dataset")
    for p in sorted(ART.glob("*")):
        if p.is_file():
            ev.add_file(str(p))
    run.log_artifact(ev)

    print("run:", run.url)
    run.finish()


if __name__ == "__main__":
    main()
