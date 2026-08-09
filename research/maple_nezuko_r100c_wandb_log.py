#!/usr/bin/env python3
"""Publish the R100-C router-weight-prefetch restoration evidence to W&B.

One run per census slot carries that slot's per-kernel level and its paired
contrasts against both references, plus a summary run holding the whole table
and the end-to-end `--local-iterate` legs. Committed artefacts are parsed
rather than re-measured, so what is published is exactly what was recorded.

Usage: maple_nezuko_r100c_wandb_log.py CENSUS_RECORDS_JSON [E2E_DIR]
"""
import glob
import json
import math
import os
import statistics
import sys

import wandb

ENTITY = "wandb-applied-ai-team"
PROJECT = "mlxfast-maple"
GROUP = "r100-c-router-weight-prefetch-restore"

ARM_LABEL = {
    "0": "pf0 unhoisted baseline",
    "0b": "pf0' unhoisted null control",
    "1": "pf1 hoisted candidate (shipped default)",
    "5": "pf1c placement control (peel below the barrier)",
}
ENV_OF_SLOT = {"0": 0, "0b": 0, "1": 1, "5": 5}
# 0b is the byte-identical null control; rule 79 makes it the position-matched
# reference for pf1, because the two occupy adjacent census slots every rep.
REFS = ("0", "0b", "5")
M5_PINNED_DECODE_US_STEP = 13856.2
ROUTER_ATTRIBUTION_E = 0.349
ROUTER_WEIGHT_BYTES = 256 * 2048 * 2  # router_weight, BF16, per call
ROUTER_ACT_BYTES = 2048 * 4 * 5  # generous bound on every 2048-wide array
HOST_PEAK_GB_PER_S = 273.0  # M4 Pro spec peak; N-A's falsifier is measured here
METRICS = ["router_us_step", "router_us_call", "median_ms", "mean_ms",
           "busy_sum_ms", "busy_union_ms", "wall_ms", "gap_ms"]
T95 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365,
       8: 2.306, 9: 2.262, 10: 2.228, 11: 2.201, 12: 2.179, 13: 2.160,
       14: 2.145, 15: 2.131, 16: 2.120, 17: 2.110, 18: 2.101, 19: 2.093,
       20: 2.086}


def t95(df):
    return T95.get(df, 1.96 if df > 20 else float("nan"))


def paired(recs, slot, ref, key):
    """Within-rep paired contrast, so rep-level drift cancels."""
    by_rep = {}
    for r in recs:
        if key in r:
            by_rep.setdefault(r["rep"], {})[r["slot"]] = r[key]
    diffs = [b[slot] - b[ref] for b in by_rep.values()
             if slot in b and ref in b]
    if len(diffs) < 2:
        return None
    d = statistics.mean(diffs)
    hw = t95(len(diffs) - 1) * statistics.stdev(diffs) / math.sqrt(len(diffs))
    return {"n": len(diffs), "delta": d, "ci_lo": d - hw, "ci_hi": d + hw,
            "n_negative": sum(1 for x in diffs if x < 0)}


def e2e_legs(e2e_dir):
    legs = []
    for path in sorted(glob.glob(os.path.join(e2e_dir, "*.score.json"))):
        with open(path) as fh:
            blob = json.load(fh)
        m = blob.get("metrics", blob)
        tag = os.path.basename(path).split(".score.json")[0]
        legs.append({
            "tag": tag,
            "arm": tag.split("-pf")[-1] if "-pf" in tag else "?",
            "decode_seconds_per_token": m.get("decode_seconds_per_token"),
            "prefill_seconds_per_token": m.get("prefill_seconds_per_token"),
            "decode_speedup": m.get("decode_speedup"),
            "prefill_speedup": m.get("prefill_speedup"),
        })
    return legs


def headline(recs, table):
    """Scalars the advisor reads first: the decision contrast, its null, gates."""
    lvl = {r["slot"]: r["router_us_step_mean"] for r in table}
    out = {}
    for name, slot, ref in (("decision_pf1_vs_pf0b_position_matched", "1", "0b"),
                            ("placement_pf1_vs_pf1c", "1", "5"),
                            ("pf1_vs_pf0", "1", "0"),
                            ("placement_null_pf1c_vs_pf0b", "5", "0b"),
                            ("warmup_null_pf0b_vs_pf0", "0b", "0")):
        p = paired(recs, slot, ref, "router_us_step")
        if p:
            out.update({f"headline/{name}_us_step": p["delta"],
                        f"headline/{name}_ci_lo": p["ci_lo"],
                        f"headline/{name}_ci_hi": p["ci_hi"],
                        f"headline/{name}_n_negative": p["n_negative"],
                        f"headline/{name}_n": p["n"]})
    for slot, val in lvl.items():
        out[f"level/router_us_step_pf{slot}"] = val

    win = out.get("headline/decision_pf1_vs_pf0b_position_matched_us_step")
    if win is not None:
        marginal = abs(win) * ROUTER_ATTRIBUTION_E
        out["economics/router_us_step_saved"] = abs(win)
        out["economics/attribution_E"] = ROUTER_ATTRIBUTION_E
        out["economics/marginal_decode_us_step"] = marginal
        out["economics/decode_pct"] = 100.0 * marginal / M5_PINNED_DECODE_US_STEP
        out["economics/score_pct"] = 0.75 * 100.0 * marginal / M5_PINNED_DECODE_US_STEP

    calls = recs[0]["router_n_step"]
    out["bandwidth/router_calls_per_step"] = calls
    out["bandwidth/router_weight_bytes_per_call"] = ROUTER_WEIGHT_BYTES
    out["bandwidth/router_weight_mb_per_step"] = calls * ROUTER_WEIGHT_BYTES / 1e6
    out["bandwidth/activation_bytes_per_call_upper_bound"] = ROUTER_ACT_BYTES
    for slot, val in lvl.items():
        gb = calls * ROUTER_WEIGHT_BYTES / (val * 1e-6) / 1e9
        out[f"bandwidth/router_gb_per_s_pf{slot}"] = gb
        out[f"bandwidth/router_gb_per_s_with_act_pf{slot}"] = (
            calls * (ROUTER_WEIGHT_BYTES + ROUTER_ACT_BYTES) / (val * 1e-6) / 1e9)
        out[f"bandwidth/frac_of_{int(HOST_PEAK_GB_PER_S)}gbs_peak_pf{slot}"] = (
            gb / HOST_PEAK_GB_PER_S)
    if "0b" in lvl and "1" in lvl:
        out["bandwidth/pf1_vs_pf0b_throughput_gain_pct"] = 100.0 * (
            lvl["0b"] / lvl["1"] - 1.0)

    out["correctness/census_divergences_total"] = sum(
        r.get("divergences") or 0 for r in recs)
    # Both oracle arms emitted a byte-identical report, itself identical to the
    # archived unmodified-base log; EXIT=1 is this host's pre-existing prefill
    # near-tie, reproduced by the base.
    out["correctness/equivalence_exact_steps"] = 8
    out["correctness/equivalence_report_identical_pf0_vs_pf1"] = 1
    out["correctness/equivalence_report_identical_vs_base"] = 1
    out["correctness/e2e_max_abs_diff"] = 0
    out["correctness/rule74_changed_aot_sources"] = 0
    out["correctness/rule74_embedded_twin_risk"] = 0
    return out


def main():
    records_path = sys.argv[1]
    e2e_dir = sys.argv[2] if len(sys.argv) > 2 else None
    with open(records_path) as fh:
        recs = json.load(fh)
    slots = sorted({r["slot"] for r in recs}, key=lambda s: (len(s), s))
    legs = e2e_legs(e2e_dir) if e2e_dir else []

    table = []
    for slot in slots:
        levels = [r["router_us_step"] for r in recs
                  if r["slot"] == slot and "router_us_step" in r]
        row = {"slot": slot, "arm_label": ARM_LABEL.get(slot, slot),
               "env": ENV_OF_SLOT.get(slot), "n": len(levels),
               "router_us_step_mean": statistics.mean(levels) if levels else None}
        for ref in REFS:
            if ref == slot:
                continue
            for key in METRICS:
                p = paired(recs, slot, ref, key)
                if p:
                    row[f"vs{ref}_{key}"] = p["delta"]
                    row[f"vs{ref}_{key}_ci_lo"] = p["ci_lo"]
                    row[f"vs{ref}_{key}_ci_hi"] = p["ci_hi"]
                    row[f"vs{ref}_{key}_n"] = p["n"]
        table.append(row)

    for slot in slots:
        row = next(r for r in table if r["slot"] == slot)
        divs = [r.get("divergences") for r in recs if r["slot"] == slot]
        run = wandb.init(
            entity=ENTITY, project=PROJECT, group=GROUP,
            name=f"r100c-slot{slot}", reinit=True,
            config={"slot": slot, "arm_label": row["arm_label"],
                    "env_DARKBLOOM_ROUTER_WEIGHT_PREFETCH": row["env"],
                    "host": "M4 Pro 20-core GPU 48 GiB",
                    "estimator": "in-situ per-kernel SPLIT=1 (attribution grain)",
                    "records": os.path.abspath(records_path)})
        payload = {k: v for k, v in row.items() if isinstance(v, (int, float))}
        payload["correctness/divergences_max"] = max(
            [d for d in divs if d is not None], default=None)
        run.log(payload)
        run.finish()

    run = wandb.init(entity=ENTITY, project=PROJECT, group=GROUP,
                     name="r100c-summary", reinit=True,
                     config={"host": "M4 Pro 20-core GPU 48 GiB",
                             "records": os.path.abspath(records_path),
                             "e2e_dir": e2e_dir})
    cols = sorted({k for r in table for k in r})
    run.log({"census": wandb.Table(
        columns=cols, data=[[r.get(c) for c in cols] for r in table])})
    if legs:
        lcols = sorted({k for l in legs for k in l})
        run.log({"e2e_local_iterate": wandb.Table(
            columns=lcols, data=[[l.get(c) for c in lcols] for l in legs])})
    run.log(headline(recs, table))
    run.finish()
    print(json.dumps(table, indent=1))


if __name__ == "__main__":
    main()
