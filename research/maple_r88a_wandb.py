#!/usr/bin/env python3
"""Log the PR #473 R88-A two-regime give-back session to W&B.

One run per dispatch regime (`s1` = DARKBLOOM_GPU_PROFILE_SPLIT=1, 406 CBs/step;
`nat` = shipped grain, ~45 CBs/step), grouped so they can be diffed, plus the
pre-registered conversion factors in both summaries. Every number is read back
out of the analyser JSON so the W&B run and the research report cannot drift.

Each `--*-null` flag takes the base/base and cand/cand same-arm JSONs in that
order; those offset-1 duplexes are the estimator's own zero check.

  python3 research/maple_r88a_wandb.py \
      --s1-kern  /tmp/maple-r88a/s1-kern.json  \
      --s1-kern-null /tmp/maple-r88a/s1-kern-null-{base,cand}.json \
      --s1-add   /tmp/maple-r88a/s1-add.json   \
      --s1-add-null  /tmp/maple-r88a/s1-add-null-{base,cand}.json \
      --nat-kern /tmp/maple-r88a/nat-kern.json \
      --nat-kern-null /tmp/maple-r88a/nat-kern-null-{base,cand}.json \
      --nat-add  /tmp/maple-r88a/nat-add.json  \
      --nat-add-null /tmp/maple-r88a/nat-add-null-{base,cand}.json \
      --nat-model-adj /tmp/maple-r88a/nat-model-adj_us_step.json \
      --base-sha 417f42c4 --cand-sha <head>
"""
import argparse
import glob
import json
import math
import os
import re

ENTITY = "wandb-applied-ai-team"
PROJECT = "mlxfast-maple"
PCT_PER_US_STEP = 0.015280
TOUCHED = ("sliding_fused_attn_ring", "full_fused_attn_grow")
DIVERGE_RE = re.compile(r"teacher-forced greedy tokens: (\d+) divergences")
CBS_RE = re.compile(r"cbs=([\d.]+) dispatches=([\d.]+)")


def load(path):
    with open(path) as fh:
        return json.load(fh)


def slot_facts(logdir):
    """Token-stream identity, divergences and regime constants from raw logs."""
    digests, divergences, cbs, disp = {}, [], set(), set()
    for path in sorted(glob.glob(os.path.join(logdir, "[0-9]*.tokens"))):
        with open(path) as fh:
            digests.setdefault(fh.read(), []).append(os.path.basename(path))
    for path in sorted(glob.glob(os.path.join(logdir, "[0-9]*.log"))):
        with open(path, errors="replace") as fh:
            text = fh.read()
        m = DIVERGE_RE.search(text)
        divergences.append(int(m.group(1)) if m else -1)
        c = CBS_RE.search(text)
        if c:
            cbs.add(float(c.group(1)))
            disp.add(float(c.group(2)))
    return {"distinct_token_streams": len(digests),
            "token_groups": [len(g) for g in digests.values()],
            "max_divergences": max(divergences) if divergences else -1,
            "cbs_per_step": sorted(cbs), "dispatches_per_step": sorted(disp)}


def touched_sum(kern):
    """Signed sum of ratio-adjusted deltas on the #457-touched kernels.

    The half-width combines the per-label half-widths in quadrature, which is
    indicative rather than exact because the labels share duplexes.
    """
    tot, var = 0.0, 0.0
    labels = []
    for key, row in kern["labels"].items():
        if not any(t in key for t in TOUCHED):
            continue
        labels.append(key)
        tot += row["adj_us_step"]
        var += ((row["adj_ci"][1] - row["adj_ci"][0]) / 2) ** 2
    return tot, math.sqrt(var), sorted(labels)


def ratio(num, num_hw, den, den_hw):
    if den == 0:
        return None, None
    c = num / den
    rel = math.hypot(num_hw / num if num else 0.0, den_hw / den)
    return c, abs(c) * rel


def main() -> int:
    ap = argparse.ArgumentParser()
    for regime in ("s1", "nat"):
        for part in ("kern", "add"):
            ap.add_argument(f"--{regime}-{part}", required=True)
            # same-arm nulls come as a pair: base/base and cand/cand duplexes
            ap.add_argument(f"--{regime}-{part}-null", nargs=2, required=True,
                            metavar=("BASE_BASE", "CAND_CAND"))
        ap.add_argument(f"--{regime}-model-adj", default=None)
        ap.add_argument(f"--{regime}-logdir", default=None)
    ap.add_argument("--logroot", default="/tmp/maple-r88a")
    ap.add_argument("--base-sha", required=True)
    ap.add_argument("--cand-sha", required=True)
    ap.add_argument("--predicted-c", type=float, default=0.85)
    ap.add_argument("--predicted-c-lo", type=float, default=0.55)
    ap.add_argument("--predicted-c-hi", type=float, default=1.10)
    ap.add_argument("--offline", action="store_true")
    args = ap.parse_args()
    cfg = vars(args)

    data = {}
    for regime in ("s1", "nat"):
        logdir = cfg[f"{regime}_logdir"] or os.path.join(args.logroot, regime)
        d = {"kern": load(cfg[f"{regime}_kern"]),
             "add": load(cfg[f"{regime}_add"]),
             "facts": slot_facts(logdir), "logdir": logdir}
        for arm, path in zip(("base", "cand"), cfg[f"{regime}_kern_null"]):
            d[f"kern_null_{arm}"] = load(path)
        for arm, path in zip(("base", "cand"), cfg[f"{regime}_add_null"]):
            d[f"add_null_{arm}"] = load(path)
        if cfg[f"{regime}_model_adj"]:
            d["model"] = load(cfg[f"{regime}_model_adj"])
        d["touched"] = touched_sum(d["kern"])
        data[regime] = d

    s1, nat = data["s1"], data["nat"]
    s1_touched, s1_touched_hw, touched_labels = s1["touched"]
    s1_total = s1["kern"]["busy_adj"]["us_step"]
    s1_total_hw = (s1["kern"]["busy_adj"]["ci"][1]
                   - s1["kern"]["busy_adj"]["ci"][0]) / 2
    nat_total = nat["kern"]["busy_adj"]["us_step"]
    nat_total_hw = (nat["kern"]["busy_adj"]["ci"][1]
                    - nat["kern"]["busy_adj"]["ci"][0]) / 2

    # absolute-busy view: wall == busy_abs + gap holds exactly, so the abs
    # census is the clock-consistent estimator and the adjusted one is only
    # the control-matched quantity. Report c under every pairing.
    s1_touched_abs = sum(row["abs_us_step"]
                         for key, row in s1["kern"]["labels"].items()
                         if any(t in key for t in TOUCHED))
    nat_abs = nat["kern"]["busy_abs"]["us_step"]
    nat_wall = nat["add"]["metrics"]["wall"]["us_step"]
    nat_wall_hw = (nat["add"]["metrics"]["wall"]["ci"][1]
                   - nat["add"]["metrics"]["wall"]["ci"][0]) / 2

    c_touched, c_touched_hw = ratio(nat_total, nat_total_hw,
                                    s1_touched, s1_touched_hw)
    c_total, c_total_hw = ratio(nat_total, nat_total_hw, s1_total, s1_total_hw)
    c_wall, c_wall_hw = ratio(nat_wall, nat_wall_hw, s1_touched, s1_touched_hw)
    shared = {
        "s1_touched_abs_us_step": s1_touched_abs,
        "nat_total_abs_us_step": nat_abs,
        "nat_wall_us_step": nat_wall,
        "nat_wall_ci95_halfwidth": nat_wall_hw,
        "conversion_c_touched_wall_over_adj": c_wall,
        "conversion_c_touched_wall_over_adj_halfwidth": c_wall_hw,
        "conversion_c_touched_abs_over_abs":
            (nat_abs / s1_touched_abs) if s1_touched_abs else None,
        "s1_touched_us_step": s1_touched,
        "s1_touched_ci95_halfwidth": s1_touched_hw,
        "s1_total_us_step": s1_total,
        "s1_total_ci95_halfwidth": s1_total_hw,
        "nat_total_us_step": nat_total,
        "nat_total_ci95_halfwidth": nat_total_hw,
        "conversion_c_touched": c_touched,
        "conversion_c_touched_halfwidth": c_touched_hw,
        "conversion_c_total": c_total,
        "conversion_c_total_halfwidth": c_total_hw,
        "predicted_c_touched": args.predicted_c,
        "predicted_c_ci80": [args.predicted_c_lo, args.predicted_c_hi],
        "giveback_us_step_s1": s1_total - s1_touched,
        "giveback_frac_s1": (1 - s1_total / s1_touched) if s1_touched else None,
        "giveback_frac_nat": (1 - nat_total / s1_touched) if s1_touched else None,
    }

    import wandb

    if args.offline:
        os.environ["WANDB_MODE"] = "offline"
    urls = {}
    for regime in ("s1", "nat"):
        d = data[regime]
        run = wandb.init(
            entity=ENTITY, project=PROJECT,
            name=f"maple-r88a-giveback-{regime}",
            group="maple-r88a-two-regime-giveback",
            job_type="paired-abba-timing",
            tags=["pr473", "r88-a", "giveback", "two-regime", regime,
                  "decode", "fused-attention", "m4pro", "methodology"],
            config={
                "assignment_id": "maple-r88-a-kernel-giveback",
                "revision_id": "r88-a-rev1",
                "pr_number": 473,
                "regime": regime,
                "split_dispatch_per_cb": regime == "s1",
                "base_sha": args.base_sha,
                "candidate_sha": args.cand_sha,
                "epilogue_pr_under_test": 457,
                "host": "AWS M4 Pro 48 GiB, Apple GPU generation 16",
                "kernels_touched": list(TOUCHED),
                "touched_labels_seen": touched_labels,
                "steps_per_run": 200,
                "reps": 4,
                "slots_per_regime": 16,
                "n_duplex": d["kern"]["n_duplex"],
                "pct_score_per_us_step": PCT_PER_US_STEP,
                "cross_process_sigma_us_step": 48.0,
                **{f"regime_{k}": v for k, v in d["facts"].items()},
            },
        )
        kern_tbl = wandb.Table(columns=[
            "label", "base_us_step", "adj_us_step", "adj_ci_lo", "adj_ci_hi",
            "abs_us_step", "abs_sd", "touched"])
        for key, row in sorted(d["kern"]["labels"].items(),
                               key=lambda kv: -kv[1]["base_us_step"]):
            kern_tbl.add_data(key, row["base_us_step"], row["adj_us_step"],
                              row["adj_ci"][0], row["adj_ci"][1],
                              row["abs_us_step"], row["abs_sd_us_step"],
                              any(t in key for t in TOUCHED))
        step_tbl = wandb.Table(columns=[
            "metric", "base_us_step", "delta_us_step", "ci_lo", "ci_hi", "sd",
            "null_base_delta", "null_base_sd", "null_cand_delta",
            "null_cand_sd"])
        for metric, row in d["add"]["metrics"].items():
            nb = d["add_null_base"]["metrics"].get(metric, {})
            nc = d["add_null_cand"]["metrics"].get(metric, {})
            step_tbl.add_data(metric, row["base_us_step"], row["us_step"],
                              row["ci"][0], row["ci"][1], row["sd_us_step"],
                              nb.get("us_step"), nb.get("sd_us_step"),
                              nc.get("us_step"), nc.get("sd_us_step"))

        add = d["add"]["metrics"]
        summary = {
            "busy_adj_us_step": d["kern"]["busy_adj"]["us_step"],
            "busy_adj_ci95_lo": d["kern"]["busy_adj"]["ci"][0],
            "busy_adj_ci95_hi": d["kern"]["busy_adj"]["ci"][1],
            "busy_adj_sd_us_step": d["kern"]["busy_adj"]["sd_us_step"],
            "busy_adj_score_pct": (d["kern"]["busy_adj"]["us_step"]
                                   * PCT_PER_US_STEP),
            "busy_abs_us_step": d["kern"]["busy_abs"]["us_step"],
            "busy_null_base_adj_us_step":
                d["kern_null_base"]["busy_adj"]["us_step"],
            "busy_null_cand_adj_us_step":
                d["kern_null_cand"]["busy_adj"]["us_step"],
            "wall_null_base_us_step":
                d["add_null_base"]["metrics"]["wall"]["us_step"],
            "wall_null_cand_us_step":
                d["add_null_cand"]["metrics"]["wall"]["us_step"],
            "touched_sum_us_step": d["touched"][0],
            "base_busy_us_step": d["kern"]["base_busy_us_step"],
            "wall_delta_us_step": add["wall"]["us_step"],
            "wall_sd_us_step": add["wall"]["sd_us_step"],
            "busy_sum_delta_us_step": add["busy_sum"]["us_step"],
            "busy_union_delta_us_step": add["busy_union"]["us_step"],
            "overlap_delta_us_step": add["overlap"]["us_step"],
            "gap_delta_us_step": add["gap"]["us_step"],
            "gap_base_us_step": add["gap"]["base_us_step"],
            "gap_pct_of_wall": (100 * add["gap"]["base_us_step"]
                                / add["wall"]["base_us_step"]),
            "overlap_base_us_step": add["overlap"]["base_us_step"],
            "bit_exact_argmax": (d["facts"]["distinct_token_streams"] == 1
                                 and d["facts"]["max_divergences"] == 0),
            **shared,
        }
        if "model" in d:
            summary.update({f"model_{k}": v for k, v in d["model"].items()
                            if not isinstance(v, list)})
        run.summary.update(summary)
        payload = {"per_label": kern_tbl, "per_step_metrics": step_tbl,
                   **summary}
        if "model" in d:
            model_tbl = wandb.Table(columns=[
                "cb_signature", "cbs_per_step", "base_us_step", "obs_delta",
                "obs_ci_halfwidth", "pred_giveback_real",
                "pred_giveback_is_s1_artefact"])
            for row in d["model"]["signatures"]:
                model_tbl.add_data(row["sig"], row["cbs"], row["base_us"],
                                   row["obs"], row["obs_hw"], row["pred_a"],
                                   row["pred_b"])
            payload["nat_model_comparison"] = model_tbl
        run.log(payload)
        urls[regime] = run.url
        run.finish()

    print(json.dumps(shared, indent=2))
    for regime, url in urls.items():
        print(f"{regime} run url: {url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
