#!/usr/bin/env python3
"""Publish the R129-Q ratchet/bar analysis to W&B.

Recomputes by IMPORTING research/r129q_ratchet_and_bar.py and calling the same
metrics() the CLI prints from, so the run and the console cannot drift.  No
number in this file is pasted.

usage (from repo root):
  python research/r129q_publish_ratchet_wandb.py <snapshot.json> [tree_score] [suffix]
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import datetime as dt                     # noqa: E402
import wandb                              # noqa: E402
import r129q_ratchet_and_bar as R         # noqa: E402

snap = sys.argv[1]
tree = float(sys.argv[2]) if len(sys.argv) > 2 else None
suffix = sys.argv[3] if len(sys.argv) > 3 else ""

rows = R.load(snap)
asof = max(R.ts(x["updatedAt"]) for x in rows)
close = asof.replace(hour=17, minute=0, second=0, microsecond=0)
ERA = "2026-08-08"
m = R.metrics(rows, asof, close, ERA, tree)
sem = R.semantics(rows)

run = wandb.init(
    entity="wandb-applied-ai-team", project="mlxfast-maple",
    name="fern-r129q-ratchet-and-bar" + (("-" + suffix) if suffix else ""),
    job_type="analysis",
    tags=["r129-q", "read-only", "ratchet", "bar", "value-of-a-draw",
          "era-split", "self-correction"],
    notes=("What does a fire have to BEAT? `accepted` == took the GLOBAL record, "
           "compared at ADJUDICATION time. Era-split model-free crown probability "
           "supersedes my published 1.5-2% per-draw prior, which sits above its "
           "95% ceiling. Read-only: on-disk snapshot, nothing fired."))

flat = {k: v for k, v in m.items() if isinstance(v, (int, float, str, bool))}
flat["snapshot"] = os.path.basename(snap)
flat["asof_utc"] = asof.isoformat()
flat["published_at_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
flat["era_start"] = ERA
flat["verdict_accepted_means"] = "new_global_record_at_adjudication_time"
flat["fired_anything"] = False
wandb.log(flat)
wandb.summary.update(flat)

# --- table 1: what `accepted` means -------------------------------------------
t = wandb.Table(columns=["model_of_improved", "agreements", "n", "pct"])
n = m["improved_means_global_best_n"]
for lab, k in (("score > GLOBAL prior max @ adjudication time",
                m["improved_means_global_best_agree"]),
               ("score > GLOBAL prior max @ fire time",
                m["agree_if_compared_at_fire_time"]),
               ("score > the ACCOUNT's own prior best",
                m["agree_if_compared_to_account_best"])):
    t.add_data(lab, k, n, round(100.0 * k / n, 2))
wandb.log({"what_accepted_means": t})

# --- table 2: the ratchet, per day --------------------------------------------
pd_ = R.per_day_advances(rows)
t2 = wandb.Table(columns=["day", "record_advances"])
for d in sorted(pd_):
    t2.add_data(d, pd_[d])
wandb.log({"record_advances_per_day": t2})

# --- table 3: bar-rise hazard, both routes ------------------------------------
t3 = wandb.Table(columns=["era_days", "advances", "per_day", "p_rise_calendar",
                          "scored_fires", "per_fire_rate", "per_fire_upper95",
                          "p_rise_from_inflight"])
for D in (1, 3, 5):
    c, f = m["hazard"]["cal_%dd" % D], m["hazard"]["fire_%dd" % D]
    t3.add_data(D, c["advances"], round(c["per_day"], 3), round(c["p_rise"], 4),
                f["scored_fires"], round(f["p_per_fire"], 5),
                round(f["p_per_fire_upper95"], 5),
                round(f["p_rise_from_inflight"], 4))
wandb.log({"bar_rise_hazard": t3})

# --- table 4: model-free jump rates, era-split --------------------------------
t4 = wandb.Table(columns=["margin", "population", "k", "n", "rate_pct",
                          "upper95_pct", "any_positive"])
for margin_lab, key in (("our_best +%.4f%%" % m["need_from_our_best_pct"], "jump_best"),
                        ("our_tree +%.4f%%" % m.get("need_from_our_tree_pct", 0.0),
                         "jump_tree")):
    if key not in m:
        continue
    j = m[key]
    for pop in ("all", "era", "ours", "ours_era"):
        if pop in j:
            c = j[pop]
            t4.add_data(margin_lab, pop, c["k"], c["n"],
                        round(100 * c["rate"], 4),
                        round(100 * c["rate_upper95"], 4), c["any_positive"])
wandb.log({"model_free_jump_rates": t4})

# --- table 5: the two ratchet anomalies --------------------------------------
t5 = wandb.Table(columns=["id", "at", "score", "prior_max", "improved"])
for a in sem["anomalies"]:
    t5.add_data(a["id"], a["at"], a["score"], a["prior_max"], a["improved"])
wandb.log({"ratchet_anomalies": t5})

print("=== PUBLISHED SCALARS (recomputed via metrics(), not pasted) ===")
for k in ("improved_means_global_best_pct", "epoch_verdict", "bar",
          "need_from_our_best_pct", "era_jump_k", "era_jump_n",
          "p_jump_era_upper95", "p_jump_alltime_optimistic",
          "p_crown_published_prior", "p_crown_chain_era_upper95",
          "published_prior_exceeds_era_ceiling",
          "p_bar_rises_before_close_worst_route"):
    print("  %-38s %s" % (k, m[k]))
print("run:", run.url)
run.finish()
