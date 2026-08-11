#!/usr/bin/env python3
"""Publish the R129-Q outcome taxonomy / sojourn-ceiling analysis to W&B.

Imports `r129q_outcome_taxonomy.metrics` and RECOMPUTES every scalar at publish
time -- the same function the CLI prints from, so the run and the console output
cannot disagree.  Nothing is pasted from a transcript.

Run from the repo root:
    python research/r129q_publish_taxonomy_wandb.py <snapshot.json> [track_id]
"""
import collections
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wandb  # noqa: E402

from r129q_outcome_taxonomy import (  # noqa: E402
    SCORED, TERMINAL, family, load, metrics, span,
)


def main():
    snap = sys.argv[1]
    track = sys.argv[2] if len(sys.argv) > 2 else "c06b1b6d"
    m = metrics(snap, track=track)
    rows, asof = load(snap)

    run = wandb.init(
        entity="wandb-applied-ai-team", project="mlxfast-maple",
        name="r129q-outcome-taxonomy",
        job_type="analysis",
        notes=("Two holes in my own R129-Q work, found by reading status x "
               "rejectionReason instead of re-modelling sojourn: (1) my SERIAL "
               "test was blind to a zero-width instant refusal, so it is redone "
               "with closed intervals and bounded; (2) sojourn is NOT open-ended "
               "-- adjudication runs under 60/120/180-min workflow timeouts, so "
               "there is a hard ceiling and mass points the KM tail could not "
               "represent. Also re-prices a draw: ~3 fires in 10 never yield a "
               "score at all. Read-only; nothing fired."),
        tags=["r129-q", "channel", "taxonomy", "self-correction", "read-only"],
        config=dict(snapshot=os.path.basename(snap), asof=m["asof"],
                    rows=m["rows"], accounts=m["accounts"],
                    n_terminal=m["n_terminal"], track=track),
    )

    wandb.log({k: v for k, v in m.items() if isinstance(v, (int, float, bool))})
    wandb.summary.update({k: v for k, v in m.items()
                          if isinstance(v, str)})

    # outcome-family table, ours vs the rest of the fleet
    term = [r for r in rows if r.get("status") in TERMINAL]
    oterm = [r for r in term if r.get("solverUsername") == "morganmcg1"]
    rterm = [r for r in term if r.get("solverUsername") != "morganmcg1"]
    of = collections.Counter(family(r.get("rejectionReason")) for r in oterm)
    rf = collections.Counter(family(r.get("rejectionReason")) for r in rterm)
    tbl = wandb.Table(columns=["family", "ours_n", "ours_pct", "rest_n",
                               "rest_pct", "ratio"])
    for k in sorted(set(of) | set(rf), key=lambda x: -(of[x] + rf[x])):
        op = 100 * of[k] / max(len(oterm), 1)
        rp = 100 * rf[k] / max(len(rterm), 1)
        tbl.add_data(k, of[k], round(op, 2), rf[k], round(rp, 2),
                     round(op / rp, 2) if rp else None)
    wandb.log({"outcome_families_ours_vs_rest": tbl})

    # timeout budget table: the reaper is sharp, which is what makes the ceiling
    soj = []
    for r in term:
        a, b = span(r, asof)
        soj.append(((b - a).total_seconds() / 60.0, r))
    bud = collections.defaultdict(list)
    for x, r in soj:
        f = family(r.get("rejectionReason"))
        if f.startswith("TIMEOUT"):
            bud[int(f.split()[1])].append(x)
    bt = wandb.Table(columns=["budget_min", "n", "observed_lo", "observed_hi",
                              "reap_overhead_min", "rows_surviving_past_pct"])
    dur = sorted(x for x, _ in soj)
    for b in sorted(bud):
        v = bud[b]
        bt.add_data(b, len(v), round(min(v), 2), round(max(v), 2),
                    round(min(v) - b, 2),
                    round(100 * sum(1 for x in dur if x > b + 1) / len(dur), 2))
    wandb.log({"workflow_timeout_budgets": bt})

    # residual law for the tracked row, conditioned on its survival
    if "track_age_min" in m:
        surv = sorted(x for x, _ in soj if x > m["track_age_min"])
        rt = wandb.Table(columns=["quantile", "total_sojourn_min"])
        for p in (0.10, 0.25, 0.50, 0.75, 0.90, 1.00):
            rt.add_data(p, round(surv[min(int(p * len(surv)),
                                          len(surv) - 1)], 1))
        wandb.log({"residual_law_given_survival": rt})

    print("run:", run.url)
    for k in sorted(m):
        print("  %-34s %s" % (k, m[k]))
    run.finish()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
