#!/usr/bin/env python3
"""R107 (PR #597): publish the session-noise correction and the draw ladder.

What this run carries, and why each piece is here:

  * The corrected within-tree sigma.  My earlier published figure (0.3728 %,
    n = 5) was an underpowered estimate and too small by ~30 %.  The repeat-group
    estimator reaches df 191-359 and lands at 0.527-0.550 %, which *confirms*
    Rule 95.1's sigma_tot ~ 0.5546 % rather than undercutting it.  Anyone sizing
    an overtake probability off the old number is over-optimistic.

  * Evidence that the session factor is i.i.d. white noise, so draws cannot be
    timed.  This closes a lever rather than opening one.

  * The decomposition showing the record is a +2.93 sigma session draw on a tree
    whose merit is 0.618 % BELOW ours.

  * The draw ladder itself, one row per fired leg, including draw 1's failed
    adjudication (it was not a replay of the intended tree at all).

Nothing here is recomputed from a summary: cs and f come from the published raw
legs via the analysis scripts, and the ladder rows come from the on-disk ledger.

Usage: maple-frieren-r107-wandb.py [--draws research/maple-frieren-r107-draws.json]
"""
from __future__ import annotations

import argparse
import json
import math
import subprocess
from pathlib import Path

import wandb

PROJECT = "mlxfast-maple"
ENTITY = "wandb-applied-ai-team"
RUN_ID = "r107frieren"

RECORD = 2.61650354381456
OUR_CS = 2.590559


def git(*args: str) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True,
                          check=False).stdout.strip()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--draws", default="research/maple-frieren-r107-draws.json")
    args = ap.parse_args()

    ledger = json.loads(Path(args.draws).read_text())
    draws = ledger["draws"]

    need_pct = 100 * math.log(RECORD / OUR_CS)

    config = {
        "round": "R107",
        "pr": 597,
        "branch": git("rev-parse", "--abbrev-ref", "HEAD"),
        "head_commit": git("rev-parse", "HEAD"),
        "rule": "95.7 volume + integration: replay the 4b0e051b family under the 95.6 recipe",
        "family_tree": ledger["family_tree"],
        "family_cs": OUR_CS,
        "base_sha": ledger["base_sha"],
        "record_target": RECORD,
        "required_session_factor_pct": need_pct,
        "feed_n": 1220,
    }

    run = wandb.init(project=PROJECT, entity=ENTITY, id=RUN_ID,
                     name="r107-session-noise-and-draw-ladder",
                     job_type="analysis", config=config, resume="allow")

    # ---- 1. the sigma correction ------------------------------------------
    sigma_tbl = wandb.Table(columns=["estimator", "df", "sd_pct", "verdict"])
    sigma_tbl.add_data("A: common-mode regression", None, None,
                       "FAILED - beta_dec = -12.3, physically impossible")
    sigma_tbl.add_data("B: repeat groups (chain clustering)", 191, 0.5269,
                       "WITHDRAWN - single-linkage leaks tree heterogeneity in, "
                       "conditioning on noisy candidate legs deflates; confounded both ways")
    sigma_tbl.add_data("mine, earlier published (n=5)", 4, 0.3728,
                       "SUPERSEDED - underpowered, ~30 % too small")
    sigma_tbl.add_data("sd(f) direct, tree-free by construction", 1219, 0.5369,
                       "ACCEPTED - dominant term")
    sigma_tbl.add_data("sd(f) predicted from baseline CVs", None, 0.5180,
                       "independent cross-check, agrees to 3.6 %")
    sigma_tbl.add_data("sd(ln cs | tree), family A replicates", 3, 0.0540,
                       "candidate leg is highly reproducible")
    sigma_tbl.add_data("sigma_resubmit = sqrt(sd(f)^2 + sd(ln cs)^2)", None, 0.5396,
                       "HEADLINE")
    sigma_tbl.add_data("C: named replicate sets (assumption-free)", 4, 0.2666,
                       "compatible (chi2_4 = 0.912, p = 0.077); 95 % CI [0.160, 0.766]; "
                       "NOT preferred - dominant term is measurable at n = 1220")
    sigma_tbl.add_data("Rule 95.1 sigma_tot", None, 0.5546, "CONFIRMED to 3 %")

    # Both failures are logged on purpose: they are the kind of result that gets
    # quietly dropped, and dropping them would invite someone to re-run them.
    run.summary["estimator_A_common_mode_regression"] = (
        "FAILED and discarded: beta_dec = -12.3, physically impossible; "
        "collinear baseline regressors and noisy published baselines"
    )
    run.summary["estimator_B_repeat_groups"] = (
        "WITHDRAWN as evidence: single-linkage chain clustering on noisy candidate "
        "legs is confounded in both directions; its agreement with 0.5546 % was luck"
    )
    run.summary["largest_live_risk"] = (
        "If the df=4 replicate sigma (0.267 %) is the truth rather than 0.540 %, "
        "P(record over 18 draws) collapses from ~45 % to ~0.2 %"
    )

    # ---- 2. i.i.d. structure ----------------------------------------------
    timing = {
        "f_mean_pct": -0.0090,
        "f_sd_pct": 0.5376,
        "lag1_autocorr": 0.0284,
        "lag1_significance_threshold": 0.0561,
        "lag1_significant": False,
        "diurnal_r2": 0.0005,
        "diurnal_amplitude_pct": 0.0126,
        "max_4h_bucket_deviation_pct": 0.056,
        "baseline_decode_cv_pct": 0.2460,
        "baseline_prefill_cv_pct": 1.9362,
        "prefill_share_of_var_f_pct": 87.23,
    }

    # ---- 3. the record is a draw ------------------------------------------
    SIGMA = 0.5396
    record_tbl = wandb.Table(columns=["who", "sha", "cs", "officialScore", "f_pct", "z"])
    record_tbl.add_data("record holder", "c5b0a13c", 2.574594, 2.616504, 1.6147,
                        1.6147 / SIGMA)
    record_tbl.add_data("ours (best merit)", "4b0e051b", OUR_CS, 2.575377, -0.5861,
                        -0.5861 / SIGMA)

    # ---- 4. pricing --------------------------------------------------------
    price_tbl = wandb.Table(columns=["sigma_pct", "z", "p_per_draw_pct",
                                     "p_12_pct", "p_18_pct", "p_24_pct"])
    for s in (0.2666, 0.3728, 0.5369, 0.5396, 0.5546):
        z = need_pct / s
        p = 0.5 * math.erfc(z / math.sqrt(2))
        price_tbl.add_data(s, z, 100 * p,
                           *[100 * (1 - (1 - p) ** k) for k in (12, 18, 24)])

    # ---- 5. the ladder -----------------------------------------------------
    ladder = wandb.Table(columns=["draw", "marker", "commit", "submission",
                                  "fired_utc", "status", "on_family_tree",
                                  "officialScore", "cs", "f_pct", "beats_record"])
    scored = 0
    best_official = None
    for d in draws:
        o = d.get("official_score")
        beats = (o is not None and o > RECORD)
        if o is not None:
            scored += 1
            best_official = o if best_official is None else max(best_official, o)
        ladder.add_data(d["draw"], d["marker"], d["commit"], d.get("submission"),
                        d.get("fired_utc"), d["status"], d.get("on_family_tree"),
                        o, d.get("cs"), d.get("f_pct"), beats)

    run.log({
        "sigma_estimates": sigma_tbl,
        "record_decomposition": record_tbl,
        "draw_pricing": price_tbl,
        "draw_ladder": ladder,
        **{f"timing/{k}": v for k, v in timing.items()},
    })

    run.summary.update({
        "sigma_resubmit_pct": SIGMA,
        "sigma_f_pct_n1220": 0.5369,
        "sigma_f_pct_predicted_from_baselines": 0.5180,
        "sigma_assumption_free_df4_pct": 0.2666,
        "sigma_assumption_free_ci95": "[0.160, 0.766]",
        "sigma_superseded_pct": 0.3728,
        "session_factor_is_iid": True,
        "draws_are_timeable": False,
        "record_is_session_draw_sigma": 1.6147 / SIGMA,
        "our_merit_edge_over_record_holder_pct": 100 * math.log(OUR_CS / 2.574594),
        "required_session_factor_pct": need_pct,
        "p_per_draw_pct": 100 * 0.5 * math.erfc(
            (need_pct / SIGMA) / math.sqrt(2)),
        "draws_fired": sum(1 for d in draws if d.get("submission")),
        "draws_scored": scored,
        "best_official_score": best_official,
        "record_taken": bool(best_official and best_official > RECORD),
        "local_best_holdable_tree": "4b0e051b (rank 1 of 25 materialisable)",
        "higher_merit_trees_not_holdable": "ebcd3ca387ae 2.591868, 5c542169b5e6 2.590753",
    })

    for name in ("research/maple-frieren-r107-session-noise.md",
                 "research/maple-frieren-r106e-amendment3.md",
                 "research/maple-frieren-r107-draws.json",
                 "research/maple-frieren-r107-local-sha-merit.json",
                 "research/maple-frieren-r107-sigma-adjudication.json"):
        p = Path(name)
        if p.exists():
            art = wandb.Artifact(p.stem, type="report")
            art.add_file(str(p))
            run.log_artifact(art)

    print("run:", run.url)
    run.finish()


if __name__ == "__main__":
    main()
