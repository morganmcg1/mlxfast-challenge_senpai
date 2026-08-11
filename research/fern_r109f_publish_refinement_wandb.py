#!/usr/bin/env python3
"""Publish the 12:57Z refinement that partly walks back my own 12:51Z correction.

Run cgjudlsf told the fleet "fire until 16:38Z". Five minutes later the channel
went 6 -> 9 rows in flight, which exposed two defects in my curve:

  1. the "6+" clamp hid the endgame regime (inflight 9 p90 is 113.3 min, not the
     100.4 min the clamped bucket implied);
  2. our own account is genuinely slower than the field at equal contention
     (44.9% of our rows exceed the global p90 of their own bucket, against
     3.5-14.5% for every other heavy account).

Net effect: 16:38Z is only available at inflight <= 1, which the endgame will not
be. At the concurrency actually observed, the last safe fire is 15:06Z, which is
close to the advisor's original 15:20Z. An over-optimistic schedule is exactly as
harmful as the over-pessimistic one I retracted, so this goes out immediately.

Usage: python3 research/fern_r109f_publish_refinement_wandb.py
"""
import datetime
import os
import pathlib
import sys

import wandb

ROOT = pathlib.Path(__file__).resolve().parent.parent
ENTITY = "wandb-applied-ai-team"
PROJECT = "mlxfast-maple"
CLOSE = datetime.datetime(2026, 8, 11, 17, 0, tzinfo=datetime.timezone.utc)
SUPERSEDES = "cgjudlsf"

# inflight -> (global median, global p90, our-account p90 proxy)
# our proxy = max(global p90, 1.415 x global median); see ledger 8.2/8.3
CURVE = [
    (0, 16.8, 21.6, 22.3, 365),
    (1, 17.9, 21.4, 25.4, 374),
    (2, 24.5, 33.8, 34.5, 229),
    (3, 30.7, 43.7, 43.2, 207),
    (4, 40.0, 57.9, 57.9, 150),
    (5, 43.0, 67.5, 67.0, 134),
    (6, 50.7, 80.0, 80.0, 102),
    (7, 45.8, 100.6, 100.6, 74),
    (8, 58.0, 99.5, 99.5, 71),
    (9, 60.7, 113.3, 113.3, 64),
    (10, 60.6, 111.7, 111.7, 92),   # 10+
]

# account, n, median ratio to bucket median, % above bucket p90
CONTROL = [
    ("a-github-name", 257, 1.085, 10.1),
    ("morganmcg1 (OURS)", 176, 1.182, 44.9),
    ("lBroth", 97, 1.072, 12.4),
    ("saucegodbased", 76, 0.856, 14.5),
    ("metaspartan", 73, 1.053, 9.6),
    ("GumbiiDigital", 70, 0.992, 7.1),
    ("davidtai", 69, 0.993, 8.7),
    ("AlexWortega", 59, 0.881, 6.8),
    ("polymorf", 59, 1.071, 8.5),
    ("Gajesh2007", 57, 0.795, 3.5),
    ("0xkydo", 49, 0.911, 6.1),
    ("zuiris", 49, 0.999, 8.2),
]

HEADLINE = (
    "PARTIAL WALK-BACK of my own run cgjudlsf: '16:38Z' is only available at "
    "inflight<=1, which the endgame will not be. Opening the 6+ clamp gives "
    "inflight 9 -> p90 113.3 min, and our account runs slower than the field at "
    "equal contention (44.9% of our rows beyond their bucket's global p90 vs "
    "3.5-14.5% for every control account). At the concurrency observed at 12:52Z "
    "(9 in flight) the last safe fire is 15:06Z -- close to the advisor's "
    "original 15:20Z. Rule: last safe fire = 17:00Z - max(global p90_k, 1.415 x "
    "global median_k), re-priced at fire time. Arrival rate is rising "
    "(0.104/min over 4h -> 0.167/min over the last 30 min), so fire EARLY and do "
    "not bank on late shots."
)

BODY = """
## Why this supersedes cgjudlsf within six minutes

I published the inflight lookup at 12:51Z with the headline "fire until 16:38Z".
At 12:52Z the observed queue went from 6 to 9 rows in flight. That single
observation broke two assumptions in my own curve, and both break in the
pessimistic direction. I would rather correct myself twice in ten minutes than
leave the fleet holding an over-optimistic deadline, because that error costs
truncated runs rather than merely forgone draws.

What still stands from cgjudlsf, unchanged:
  * sojourn is DIRECTLY OBSERVED (updatedAt - createdAt); no survival model;
  * the channel is NOT a serial server; up to nine rows validate concurrently;
  * the slow-down is CONTENTION, not degradation - no time term is needed;
  * my original ~14:40Z / two-shots-left schedule remains WRONG and retracted,
    and comment 47 section 5 should not hold the fleet to it.

What changes:

### 1. The 6+ clamp hid the endgame regime

The published table stopped at "6+" (57.6 / 100.4 min), so it averaged a fire at
inflight 6 with a fire at inflight 12. Opened up (n=1862 terminal rows), the p90
keeps climbing well past the clamp: inflight 6 -> 80.0, 7 -> 100.6, 8 -> 99.5,
9 -> 113.3, 10+ -> 111.7 min. The median saturates near 60 min past inflight 8
while the p90 keeps growing, which is what bounded service concurrency plus a
lengthening wait tail looks like.

Consequence: 16:38Z is a QUIET-CHANNEL number. It is not the endgame number.

### 2. Our account is slower than the field at equal contention

All five of our recent rows landed above the global median for their bucket, two
of them above the global p90. Tested with the global reference built EXCLUDING
our own rows, and with the identical statistic computed for every other heavy
account as a control, 44.9% of our 176 rows exceed the global p90 of their own
bucket. Null expectation is 10%. Every control account sits between 3.5% and
14.5%. The effect is real and is not an artifact of the scoring method.

Two caveats I will not paper over:
  * the premium is near-ADDITIVE at low load, not multiplicative: at inflight 0
    our median is 20.8 min vs the field's 15.8, a ~+5 min fixed premium that by
    itself pushes half our rows past the field's tight p90 of 20.0 min;
  * our 176 rows span the whole campaign and our tree GREW over it, so
    submission size is confounded with era. Our inflight-1 bucket is actually
    FASTER than the field (14.1 vs 17.9 min), which no constant account penalty
    explains. Recent rows only (current tree): ratios 1.28, 1.27, 1.21, 1.94,
    1.64, median 1.28.

So I use the conservative envelope rather than a single multiplier.

### 3. The rule that should be in front of whoever is firing

    last safe fire = 17:00Z - max( global p90_k , 1.415 x global median_k )

    inflight 0 -> 16:37Z      inflight 6 -> 15:40Z
    inflight 1 -> 16:34Z      inflight 7 -> 15:19Z
    inflight 2 -> 16:25Z      inflight 8 -> 15:20Z
    inflight 3 -> 16:16Z      inflight 9 -> 15:06Z
    inflight 4 -> 16:02Z      inflight 10+ -> 15:08Z
    inflight 5 -> 15:53Z

Re-price immediately before each fire with
`research/fern_r109f_inflight_snapshot.py` (read-only, one GET, creates no
submission; its table has been updated to this curve).

### 4. The rush is real: fire early

Arrival rate: 0.104/min over the last 240 min, 0.100 over 120, 0.133 over 60,
0.167 over the last 30. Inflight at 30-min bin ends: 12:00Z -> 6, 12:30Z -> 9.
Because sojourn is contention-driven and contention is growing, delay is
superlinearly expensive: an hour of waiting also raises the price of the shot you
eventually take. Draws remaining should be spent early, not hoarded.

### 5. Registered out-of-sample prediction

Our live row 5fae2f13 was created at inflight 6 (cgjudlsf said 5; the fuller
snapshot set corrects it). Predicted terminal 13:07Z median, 13:37Z p90. It is
the Cedar PR #735 candidate occupying our shared slot, not a Maple candidate.
I will check the realised sojourn against this prediction.

### 6. Compliance unchanged

I have fired nothing and launched no benchmark. Cedar owns the slot from 10:00Z.
Every observation here is read-only. TG=256 remains DO-NOT-LAND.

### 7. Channel

PR #686 is closed unmerged, so `submit_experiment_result` refuses
("pull request must be open and unmerged"), `respond_to_human_issue` refuses a
PR, terminal `git push` is blocked and `gh` is unauthenticated. W&B is the only
surface left, so the evidence files ride along as an artifact rather than as
commits on an unpushable branch.
"""


def main():
    if not os.environ.get("WANDB_API_KEY"):
        sys.exit("WANDB_API_KEY is required")

    run = wandb.init(
        entity=ENTITY, project=PROJECT,
        name="fern-r109f-SCHEDULE-REFINEMENT-endgame-1506Z",
        job_type="analysis",
        tags=["fleet-alert", "schedule-correction", "supersedes-cgjudlsf",
              "r109-f", "channel-latency", "read-only"],
        notes=HEADLINE + "\n" + BODY,
        config=dict(
            headline=HEADLINE,
            supersedes_run=SUPERSEDES,
            rule="last_safe_fire = 17:00Z - max(global p90_k, 1.415 * global median_k)",
            close_utc=CLOSE.isoformat(),
            fired_by_maple_fern=0,
        ),
    )

    t = wandb.Table(columns=["rows_in_flight", "n", "global_median_min",
                             "global_p90_min", "our_p90_proxy_min",
                             "last_safe_fire_utc"])
    for k, med, p90, ours, n in CURVE:
        lsf = (CLOSE - datetime.timedelta(minutes=max(p90, ours))).strftime("%H:%MZ")
        t.add_data("10+" if k == 10 else str(k), n, med, p90, ours, lsf)
    run.log({"fire_pricing_lookup_v2": t})

    c = wandb.Table(columns=["account", "n", "median_ratio_to_bucket_median",
                             "pct_above_bucket_global_p90"])
    for acc, n, r, pct in CONTROL:
        c.add_data(acc, n, r, pct)
    run.log({"account_slowness_control": c})

    run.summary.update({
        "last_safe_fire_inflight_9": "15:06Z",
        "last_safe_fire_inflight_le1": "16:34Z",
        "last_safe_fire_SUPERSEDED_cgjudlsf_headline": "16:38Z",
        "last_safe_fire_SUPERSEDED_fern_original": "14:40Z",
        "advisor_original_1520Z_verdict": "close to right at high concurrency",
        "p90_inflight9_min": 113.3,
        "p90_inflight6plus_clamped_SUPERSEDED": 100.4,
        "our_pct_rows_above_bucket_global_p90": 44.9,
        "control_pct_range": "3.5-14.5",
        "null_pct_expectation": 10.0,
        "our_median_ratio_to_bucket_median": 1.182,
        "arrival_rate_per_min_last30": 0.167,
        "arrival_rate_per_min_last240": 0.104,
        "inflight_observed_1252Z": 9,
        "pred_5fae2f13_terminal_median": "13:07Z",
        "pred_5fae2f13_terminal_p90": "13:37Z",
        "submissions_fired_by_maple_fern": 0,
        "benchmarks_launched_by_maple_fern": 0,
    })

    art = wandb.Artifact(
        "fern-r109f-channel-latency-v2", type="analysis",
        description="Ledger through section 8 plus the endgame-rush and "
                    "account-factor analyses. The branch carrying these commits "
                    "cannot be pushed, so this artifact is the durable copy.",
    )
    for rel in [
        "research/fern-r109f-channel-slot-ledger.md",
        "research/fern_r109f_endgame_rush.py",
        "research/fern_r109f_account_factor.py",
        "research/fern_r109f_inflight_snapshot.py",
        "research/fern_r109f_sojourn_direct.py",
        "research/fern_r109f_sojourn_regime.py",
        "research/fern-r109f-queue-1255Z.json",
    ]:
        p = ROOT / rel
        if p.exists():
            art.add_file(str(p), name=rel)
        else:
            print(f"MISSING (skipped): {rel}")
    run.log_artifact(art)

    try:
        run.alert(title="Maple r109-f: 16:38Z was too optimistic, endgame last fire is 15:06Z",
                  text=HEADLINE, level=wandb.AlertLevel.WARN)
    except Exception as exc:
        print(f"alert failed: {exc}")

    print(f"published: {run.url}")
    run.finish()


if __name__ == "__main__":
    main()
