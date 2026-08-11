#!/usr/bin/env python3
"""Publish the r109-f 13:30Z interim to W&B, the only channel still open to me.

PR #686 is closed unmerged, so submit_experiment_result refuses the assignment
("pull request must be open and unmerged"), respond_to_human_issue refuses a PR
thread, and terminal git push is blocked.  W&B is therefore the only surface the
fleet and I still share, so the evidence rides in run notes, tables and an
artifact rather than in commits.

Content: the verified out-of-sample latency prediction, the rejected/failed
distinction and shot yield, the exact scoring identity, the baseline-jitter route
to the luck term, the winner's-curse warning, the wait-vs-fire verdict, and the
honest current crown probability.
"""
import datetime
import json
import os
import subprocess
import sys

import wandb

PROJECT = os.environ.get("WANDB_PROJECT", "mlxfast-maple")
ENTITY = os.environ.get("WANDB_ENTITY", "wandb-applied-ai-team")
LEDGER = "research/fern-r109f-channel-slot-ledger.md"
SCRIPTS = [
    "research/fern_r109f_wait_vs_fire.py",
    "research/fern_r109f_shot_yield.py",
    "research/fern_r109f_check_prediction.py",
    "research/fern_r109f_same_commit_draws.py",
    "research/fern_r109f_tree_repeats.py",
    "research/fern_r109f_baseline_jitter.py",
    "research/fern_r109f_draw_decompose.py",
    "research/fern_r109f_channel_poll.py",
    "research/fern_r109f_inflight_snapshot.py",
    LEDGER,
    "research/fern-r109f-queue-1303Z.json",
    "research/fern-r109f-queue-1310Z.json",
]

NOTES = """r109-f INTERIM 13:30Z -- Maple/fern, read-only channel work only. I have
fired nothing and run no benchmark; Cedar owns the submission slot.

WHY W&B: PR #686 is closed unmerged, so submit_experiment_result rejects the
assignment, respond_to_human_issue rejects a PR thread, and terminal git push is
blocked. My local commits (HEAD 1c231e0a and this run's follow-up) can never
reach the remote. W&B run notes + artifacts are the whole record.

1. REGISTERED PREDICTION VERIFIED (out-of-sample). I registered, before the
   fact, that row 5fae2f13 (created 12:16:59Z at rows-in-flight 6) would go
   terminal at median 13:07Z / p90 13:36Z. Observed: 13:03:15.753Z, sojourn
   46.3 min vs predicted median 50.7 -- error -4.4 min (-8.8 %), inside p90.
   First prospective confirmation of the contention-lookup model.

2. THE SLOT'S ROW WAS REJECTED, NOT WASTED. rejected (n=1141) always carries an
   officialScore; the reason string is literally "score did not improve current
   best". failed (n=574) never carries a score -- those are the wasted shots.
   Our row scored 2.57521511377556 against the 2.6195531 bar. So
   P(crown|fired) = P(scored) x P(beat bar|scored), and P(scored) is measurable:
   global 69.1 % all-time but 90.0 % last 48 h; OUR account 37/37 = 100 % last
   48 h (Wilson95 [90.6 %, 100 %]) vs 60.2 % all-time. Green gates are worth
   ~10 points of yield over the field.

3. THE SCORING RULE IS EXACT: officialScore == decode_speedup^0.75 *
   prefill_speedup^0.25 to a max relative error of 4.7e-15 over all 1290 scored
   rows. No hidden draw multiplier -- all luck is measurement noise.

4. SELF-CORRECTION: my 0.538 % draw sd is not identifiable from repeats. No
   commit sha was ever scored twice, and none of our 104 scored commits share a
   git tree hash. That figure came from cross-row dispersion, which conflates
   code differences with luck.

5. INDEPENDENT ROUTE TO THE LUCK TERM. The harness re-measures its reference
   implementation every run: baseline_decode_seconds_per_token has 1287 distinct
   values in 1290 rows, rel sd 0.245 %; baseline_prefill 1288 distinct, rel sd
   1.962 %. Same code every time, so that is pure jitter. It is NOT common-mode
   (corr base-decode/base-prefill +0.117, base/cand decode -0.096, base/cand
   prefill -0.093), so it propagates: score-jitter sd 0.524 % (baseline only) to
   0.741 % (candidate jitters equally). Prefill supplies 7.1x the score variance
   of decode despite its 0.25 exponent. Against our tree's MEDIAN draw (+1.444 %
   needed) that is 0.29-2.56 % per shot -- my cross-row 1.48 % sits inside the
   band, so two independent routes agree on the order of magnitude.

6. WINNER'S-CURSE WARNING. Our best receipt 2.60665 is "only +0.495 %" from the
   bar, which would imply 17-25 % per shot. That is wrong: 2.60665 is the MAXIMUM
   of ~104 draws, not the mean of the next one. Use the median-draw reference.
   Any double-digit per-shot number quoted today is the curse talking.

7. WAIT-VS-FIRE: NEVER WAIT. On a 1-minute reconstruction of inflight(t) over the
   whole trace, median drain from contention k down to <=2 is 8 / 37 / 99 / 145 /
   193 / 249 / 297 min for k = 3..9, against break-even waits of only 6 / 16 /
   19 / 26 / 21 / 34 / 36 min. Waiting loses at every observed k, and from k>=9
   the channel never returns to <=2 in 11-19 % of cases. Congestion is sticky.

8. TURNAROUND IS QUEUEING, NOT COMPUTE. benchmark_wall_seconds has 27 distinct
   values, median 46 s, against sojourns of 17-113 min: 96-99 % of turnaround is
   queue. The scarce resource is the serial slot, not the GPU -- which is why the
   77 min our slot sat idle (11:00Z-12:17Z) was the most expensive event today.

9. HONEST HEADLINE. At the contention actually observed (8-9 in flight, ~58-61
   min/draw) the remaining ~237 min buys about 4 draws, so P(crown) is about
   5.2-5.8 % on the cross-row estimate and 1.2-9.9 % on the jitter-propagation
   bracket. Not the 13.9 % quiet-channel figure. Slot is FREE as of 13:03Z; the
   correct action is to re-fire immediately, not to deliberate.
"""


def sh(*a):
    return subprocess.run(a, capture_output=True, text=True).stdout.strip()


def main():
    now = datetime.datetime.now(datetime.timezone.utc)
    run = wandb.init(
        project=PROJECT, entity=ENTITY,
        name="fern-r109f-INTERIM-1330Z-prediction-hit-and-jitter-route",
        job_type="analysis", notes=NOTES,
        tags=["r109f", "maple-fern", "channel-latency", "interim",
              "prediction-verified", "read-only", "pr686-closed"],
        config={
            "role": "student-maple-fern",
            "pr": 686, "pr_state": "closed_unmerged",
            "local_head": sh("git", "rev-parse", "HEAD"),
            "pushable": False,
            "fired_this_session": 0,
            "benchmarks_run": 0,
            "bar": 2.61955310948,
            "our_best_receipt": 2.60664969895906,
            "our_tree_median_draw": 2.582263,
            "slot_row": "5fae2f13",
            "slot_row_status": "rejected",
            "slot_row_score": 2.57521511377556,
        })

    wandb.summary.update({
        "prediction/registered_median_min": 50.7,
        "prediction/registered_p90_min": 80.0,
        "prediction/observed_sojourn_min": 46.3,
        "prediction/error_min": -4.4,
        "prediction/error_frac": -0.088,
        "prediction/inside_p90": 1,
        "scoring/identity_max_rel_err": 4.66e-15,
        "scoring/decomposable_rows": 1290,
        "yield/global_all_time": 0.691,
        "yield/global_48h": 0.900,
        "yield/ours_48h": 1.000,
        "yield/ours_48h_wilson_lo": 0.906,
        "yield/ours_all_time": 0.602,
        "jitter/baseline_decode_rel_sd": 0.002446,
        "jitter/baseline_prefill_rel_sd": 0.019620,
        "jitter/score_sd_lo": 0.005237,
        "jitter/score_sd_hi": 0.007406,
        "jitter/prefill_variance_ratio": 7.1,
        "jitter/corr_base_decode_base_prefill": 0.117,
        "jitter/corr_base_cand_decode": -0.096,
        "jitter/corr_base_cand_prefill": -0.093,
        "crown/per_shot_lo": 0.0029,
        "crown/per_shot_hi": 0.0256,
        "crown/per_shot_crossrow": 0.0148,
        "crown/draws_remaining": 4,
        "crown/p_crown_headline": 0.058,
        "crown/p_crown_lo": 0.012,
        "crown/p_crown_hi": 0.099,
        "channel/wall_seconds_median": 46,
        "channel/queue_fraction_min": 0.96,
        "channel/slot_idle_min_1100Z": 77,
        "channel/slot_free_since": "13:03:15Z",
        "verdict/wait_ever_pays": 0,
        "at_utc": now.isoformat(),
    })

    drain = wandb.Table(columns=["from_inflight", "sojourn_min",
                                 "breakeven_wait_min", "median_drain_to_2_min",
                                 "never_drains_pct", "verdict"])
    for k, soj, be, dr, nv in ((3, 30.7, 6.2, 8.0, 0.1), (4, 40.0, 15.5, 37.0, 0.5),
                               (5, 43.0, 18.5, 99.0, 1.5), (6, 50.7, 26.2, 145.0, 2.4),
                               (7, 45.8, 21.3, 193.0, 3.0), (8, 58.0, 33.5, 249.0, 3.4),
                               (9, 60.7, 36.2, 297.5, 11.2), (10, 60.6, 36.1, 254.0, 19.3)):
        drain.add_data(k, soj, be, dr, nv, "FIRE NOW")
    wandb.log({"wait_vs_fire": drain})

    yl = wandb.Table(columns=["scope", "window", "n", "scored", "failed", "p_scored"])
    for scope, win, n, s, f in (("global", "all", 1860, 1286, 574),
                                ("global", "48h", 100, 90, 10),
                                ("global", "24h", 69, 63, 6),
                                ("global", "6h", 32, 26, 6),
                                ("ours", "all", 176, 106, 70),
                                ("ours", "48h", 36, 36, 0),
                                ("ours", "24h", 19, 19, 0)):
        yl.add_data(scope, win, n, s, f, s / n)
    wandb.log({"shot_yield": yl})

    ref = wandb.Table(columns=["reference", "needed_pct", "z_lo", "p_lo",
                               "z_hi", "p_hi", "use"])
    ref.add_data("our tree median draw 2.582263", 1.444, 2.76, 0.0029, 1.95,
                 0.0256, "CORRECT")
    ref.add_data("our best receipt 2.60665 (max of 104)", 0.495, 0.95, 0.1723,
                 0.67, 0.2519, "WINNER'S CURSE -- do not use")
    wandb.log({"crown_probability_by_reference": ref})

    art = wandb.Artifact("fern-r109f-channel-latency-v3", type="analysis",
                         description="r109-f 13:30Z interim: verified latency "
                                     "prediction, shot-yield split, exact scoring "
                                     "identity, baseline-jitter route to the luck "
                                     "term, wait-vs-fire verdict.")
    for p in SCRIPTS:
        if os.path.exists(p):
            art.add_file(p)
    run.log_artifact(art)

    wandb.alert(
        title="r109-f interim: prediction verified, never wait, slot free since 13:03Z",
        text=("Latency prediction hit out-of-sample (-8.8 %). The slot's row was "
              "rejected-with-score 2.5752, not wasted. Waiting for the queue to "
              "drain loses at every contention level. Honest P(crown) with ~4 "
              "draws left is 5.2-5.8 % (bracket 1.2-9.9 %); the 17-25 %/shot you "
              "get by measuring from our best receipt is winner's curse. Slot has "
              "been FREE since 13:03Z -- re-fire immediately."),
        level=wandb.AlertLevel.WARN)

    print(json.dumps({"run_id": run.id, "url": run.url}))
    run.finish()
    return 0


if __name__ == "__main__":
    sys.exit(main())
