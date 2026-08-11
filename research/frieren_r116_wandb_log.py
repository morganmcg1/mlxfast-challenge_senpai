#!/usr/bin/env python3
"""Publish the R116-A shipped-defaults audit to W&B.

    python3 research/frieren_r116_wandb_log.py screen research/r116-defaults/screen
    python3 research/frieren_r116_wandb_log.py confirm <confirm-dir>

One run per arm carries that arm's per-block steady decode step series and the
paired contrast against the control arm. One summary run carries the contrast
table, the contamination sensitivity re-analysis, the shipped-default census,
and the stage verdict.

This script only reads artifacts produced by research/frieren_r116_screen_run.sh
and research/frieren_r116_confirm_run.sh; it never re-times anything.
"""
import argparse
import glob
import json
import os
import statistics
import sys

import wandb

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from frieren_steady_step import EMAX, NAME, SAMPLE, contrasts, samples

PROJECT = os.environ.get("WANDB_PROJECT", "mlxfast-maple")
ENTITY = os.environ.get("WANDB_ENTITY", "wandb-applied-ai-team")
BASE_TAGS = ["maple", "student:maple-frieren", "pr705", "r116-a",
             "shipped-defaults", "decode"]

# Flag census over Sources/ and Vendor/ at base 93688bf (see
# research/frieren_r116_tau_status_inventory.md section 2).
CENSUS = {
    "census_distinct_darkbloom_env_reads_sources": 91,
    "census_default_on_not_equal_zero": 68,
    "census_default_off_equal_one": 9,
    "census_non_boolean_valued": 14,
    "census_vendor_getenv_sites": 3,
    "census_comment_lines_for_flag_family": 16,
}

# Arm -> the single compiled default it flips off (or on).
ARM_FLAG = {
    "ctl": "(control; no flag flipped)",
    "ns0": "DARKBLOOM_NVFP4_NIBBLE_SPLIT=0",
    "ns2": "DARKBLOOM_NVFP4_NIBBLE_SPLIT=2",
    "qse0": "DARKBLOOM_QKV_SEED_ELIDE=0",
    "qmvse0": "DARKBLOOM_QMV_SEED_ELIDE=0",
    "qmvsc0": "DARKBLOOM_QMV_SIGN_CARRY=0",
    "sc0": "DARKBLOOM_NVFP4_SCALE_CARRY=0",
    "sd0": "DARKBLOOM_SHARED_DUAL=0",
    "sfd1": "DARKBLOOM_SHARED_FUSED_DOWN=1",
}

# us of paired steady decode step -> fraction of score, from the campaign
# conversion recorded in research/frieren_r116_flag_inventory_and_prereg.md.
SCORE_PER_US = 0.000084


def block_rows(logdir, min_token=16):
    rows = []
    for path in sorted(glob.glob(os.path.join(logdir, "log-*-b*.txt"))):
        hit = NAME.search(os.path.basename(path))
        if not hit:
            continue
        vals = samples(path, min_token)
        if len(vals) < 3:
            continue
        rows.append({
            "arm": hit.group(1),
            "block": int(hit.group(2)),
            "path": path,
            "n": len(vals),
            "series_us": [1e6 * v for v in vals],
            "steady_mean_us": 1e6 * statistics.mean(vals),
            "steady_median_us": 1e6 * statistics.median(vals),
            "within_sd_us": 1e6 * statistics.stdev(vals),
        })
    return rows


def score_records(logdir):
    """arm -> block -> harness score json, only for runs that passed."""
    out = {}
    for path in sorted(glob.glob(os.path.join(logdir, "score-*-b*.json"))):
        name = os.path.basename(path)[len("score-"):-len(".json")]
        arm, _, block = name.rpartition("-b")
        try:
            doc = json.load(open(path))
        except (OSError, ValueError):
            continue
        flat = {k: v for k, v in doc.items() if k != "metrics"}
        flat.update(doc.get("metrics") or {})
        out.setdefault(arm, {})[int(block)] = flat
    return out


def arm_runs(stage, rows, scores, control, group):
    """One W&B run per arm; returns arm -> run url/id."""
    cons = {c["arm"]: c for c in contrasts(rows, control)}
    by_arm = {}
    for r in rows:
        by_arm.setdefault(r["arm"], []).append(r)
    handles = {}
    for arm in sorted(by_arm):
        blocks = sorted(by_arm[arm], key=lambda r: r["block"])
        run = wandb.init(
            project=PROJECT, entity=ENTITY, group=group,
            name=f"r116a-{stage}-{arm}", job_type=f"r116a-{stage}",
            tags=BASE_TAGS + [f"stage:{stage}", f"arm:{arm}"],
            reinit=True,
            config={
                "stage": stage,
                "arm": arm,
                "flag": ARM_FLAG.get(arm, "unknown"),
                "control_arm": control,
                "is_control": arm == control,
                "n_blocks": len(blocks),
                "min_token": 16,
                "harness": "./benchmark.sh --local-iterate",
                "startup_memory_profile": "full",
                "host_class": "M4 (directional; ranked host is M5)",
                "under_report_factor_local_iterate": 1.28,
                "score_fraction_per_us": SCORE_PER_US,
            })
        step = 0
        for b in blocks:
            for i, us in enumerate(b["series_us"]):
                wandb.log({"decode/last_step_us": us,
                           "decode/block": b["block"],
                           "decode/sample_index": i}, step=step)
                step += 1
            wandb.log({"block/steady_mean_us": b["steady_mean_us"],
                       "block/steady_median_us": b["steady_median_us"],
                       "block/within_sd_us": b["within_sd_us"],
                       "block/n_samples": b["n"],
                       "block/id": b["block"]}, step=step)
            step += 1

        means = [b["steady_mean_us"] for b in blocks]
        run.summary["steady_mean_us"] = statistics.mean(means)
        run.summary["steady_between_block_sd_us"] = (
            statistics.stdev(means) if len(means) > 1 else float("nan"))
        run.summary["n_blocks_measured"] = len(blocks)
        c = cons.get(arm)
        if c:
            run.summary["delta_vs_control_us"] = c["delta_us"]
            run.summary["delta_sem_us"] = c["sem_us"]
            run.summary["delta_t"] = c["t"]
            run.summary["n_pairs"] = c["n_pairs"]
            run.summary["projected_score_delta"] = (
                -c["delta_us"] * SCORE_PER_US)

        srec = scores.get(arm, {})
        passed = [d for d in srec.values() if d.get("passed")]
        run.summary["n_score_json"] = len(srec)
        run.summary["n_score_json_passed"] = len(passed)
        if passed:
            for key in ("score", "decode_speedup", "prefill_speedup"):
                vals = [d[key] for d in passed if isinstance(d.get(key),
                                                             (int, float))]
                if vals:
                    run.summary[f"harness/{key}_mean"] = statistics.mean(vals)
        hashes = {d.get("golden_hash") for d in passed if d.get("golden_hash")}
        run.summary["golden_hash_count"] = len(hashes)
        run.summary["golden_hash"] = sorted(hashes)[0] if hashes else ""
        handles[arm] = {"id": run.id, "url": run.url}
        run.finish()
    return handles


def summary_run(stage, rows, scores, control, group, handles, sensitivity):
    cons = sorted(contrasts(rows, control), key=lambda c: c["delta_us"])
    run = wandb.init(
        project=PROJECT, entity=ENTITY, group=group,
        name=f"r116a-{stage}-summary", job_type=f"r116a-{stage}-summary",
        tags=BASE_TAGS + [f"stage:{stage}", "summary"], reinit=True,
        config={
            "stage": stage,
            "control_arm": control,
            "n_arms": len(cons) + 1,
            "n_blocks": len({r["block"] for r in rows}),
            "decision_rule": ("negative contrast with |t| >= 3 over 18 blocks "
                              "AND screen sign agreement"),
            "ship_rule": "ship on a verified positive or do not ship",
            **CENSUS,
        })

    table = wandb.Table(columns=["arm", "flag", "n_pairs", "delta_us",
                                 "sem_us", "t", "projected_score_delta",
                                 "wandb_run_id"])
    for c in cons:
        table.add_data(c["arm"], ARM_FLAG.get(c["arm"], "unknown"),
                       c["n_pairs"], round(c["delta_us"], 2),
                       round(c["sem_us"], 2), round(c["t"], 3),
                       round(-c["delta_us"] * SCORE_PER_US, 6),
                       handles.get(c["arm"], {}).get("id", ""))
    run.log({"contrasts": table})

    if sensitivity:
        stable = wandb.Table(columns=["arm", "n_pairs", "delta_us", "sem_us",
                                      "t"])
        for c in sorted(sensitivity, key=lambda c: c["delta_us"]):
            stable.add_data(c["arm"], c["n_pairs"], round(c["delta_us"], 2),
                            round(c["sem_us"], 2), round(c["t"], 3))
        run.log({"contrasts_block2_excluded": stable})
        best_s = min(sensitivity, key=lambda c: c["delta_us"])
        run.summary["sensitivity/argmax_arm"] = best_s["arm"]
        run.summary["sensitivity/argmax_delta_us"] = best_s["delta_us"]

    if cons:
        best = min(cons, key=lambda c: c["delta_us"])
        bias = EMAX.get(len(cons), 1.4236) * best["sem_us"]
        run.summary["argmax_arm"] = best["arm"]
        run.summary["argmax_delta_us"] = best["delta_us"]
        run.summary["argmax_delta_debiased_us"] = best["delta_us"] + bias
        run.summary["argmax_selection_bias_us"] = bias
        run.summary["argmax_t"] = best["t"]
        run.summary["any_significant_win"] = bool(
            best["delta_us"] + bias < 0 and best["t"] <= -3)

    all_scores = [d for arm in scores.values() for d in arm.values()]
    hashes = {d.get("golden_hash") for d in all_scores
              if d.get("passed") and d.get("golden_hash")}
    run.summary["distinct_golden_hashes"] = len(hashes)
    run.summary["n_runs_total"] = len(all_scores)
    run.summary["n_runs_failed"] = sum(1 for d in all_scores
                                       if not d.get("passed"))
    for arm, h in handles.items():
        run.summary[f"arm_run_url/{arm}"] = h["url"]
    url = run.url
    run.finish()
    return url


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=["screen", "confirm"])
    ap.add_argument("logdir")
    ap.add_argument("--control", default="ctl")
    ap.add_argument("--group", default="")
    ap.add_argument("--exclude-block", type=int, action="append", default=[])
    args = ap.parse_args()

    rows = block_rows(args.logdir)
    if not rows:
        raise SystemExit(f"no usable logs under {args.logdir}")
    scores = score_records(args.logdir)
    group = args.group or f"r116a-{args.stage}"

    sensitivity = None
    if args.exclude_block:
        kept = [r for r in rows if r["block"] not in args.exclude_block]
        sensitivity = contrasts(kept, args.control)

    handles = arm_runs(args.stage, rows, scores, args.control, group)
    url = summary_run(args.stage, rows, scores, args.control, group, handles,
                      sensitivity)
    print(f"summary run: {url}")
    for arm in sorted(handles):
        print(f"  {arm:<8} {handles[arm]['url']}")


if __name__ == "__main__":
    main()
