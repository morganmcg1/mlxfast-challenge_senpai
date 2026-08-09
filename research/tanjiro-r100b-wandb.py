#!/usr/bin/env python3
"""Log the r100-B epilogue re-port census and the Part 1 lottery result to W&B.

Every timing number is re-derived here from the census artifacts (the two
analyser JSONs plus the raw per-slot .log/.steps/.tokens files), so the W&B
run cannot drift away from research/maple-tanjiro-r100-epilogue-report.md.

  python3 research/tanjiro-r100b-wandb.py \
      --wall /tmp/tanjiro-r100b-wall.json \
      --wall-null /tmp/tanjiro-r100b-wall-null.json \
      --kernel /tmp/tanjiro-r100b-abba.json \
      --kernel-null /tmp/tanjiro-r100b-abba-null.json \
      --logdir /tmp/tanjiro-r100b-census \
      --base-sha <base> --cand-sha <head>
"""
import argparse
import glob
import json
import os
import re
import statistics

ENTITY = "wandb-applied-ai-team"
PROJECT = "mlxfast-maple"
PCT_PER_US_STEP = 0.015280
TOUCHED = ("sliding_fused_attn_ring", "full_fused_attn_grow")
DIVERGE_RE = re.compile(r"teacher-forced greedy tokens: (\d+) divergences")
LOG_RE = re.compile(r"^(\d+)-rep(\d+)-([a-z_0-9]+)\.log$")
STEPS_RE = re.compile(r"^(\d+)-rep(\d+)-([a-z_0-9]+)\.steps$")
PROF_RE = re.compile(
    r"per steady step: wall=([\d.]+) ms gpu_busy_sum=([\d.]+) ms "
    r"gpu_busy_union=([\d.]+) ms gap=([\d.]+) ms")
T95 = {2: 12.706, 3: 4.303, 4: 3.182, 5: 2.776, 6: 2.571, 7: 2.447, 8: 2.365}
CHANNELS = ("wall", "busy_sum", "busy_union", "gap")


def load(path):
    with open(path) as fh:
        return json.load(fh)


def ci(deltas):
    n = len(deltas)
    mean, sd = statistics.mean(deltas), statistics.stdev(deltas)
    half = T95.get(n, 1.96) * sd / (n ** 0.5)
    return {"mean": mean, "lo": mean - half, "hi": mean + half, "sd": sd, "n": n}


def token_identity(logdir):
    digests = {}
    for path in sorted(glob.glob(os.path.join(logdir, "[0-9]*.tokens"))):
        with open(path) as fh:
            digests.setdefault(fh.read(), []).append(os.path.basename(path))
    divergences = []
    for path in sorted(glob.glob(os.path.join(logdir, "[0-9]*.log"))):
        with open(path, errors="replace") as fh:
            m = DIVERGE_RE.search(fh.read())
        divergences.append(int(m.group(1)) if m else -1)
    return len(digests), [len(g) for g in digests.values()], divergences


def decompose(logdir):
    """ABBA-paired wall / gpu_busy / gap deltas, in us/step."""
    slots = {}
    for path in sorted(glob.glob(os.path.join(logdir, "[0-9][0-9]-rep*.log"))):
        m = LOG_RE.match(os.path.basename(path))
        if not m:
            continue
        with open(path, errors="replace") as fh:
            pm = PROF_RE.search(fh.read())
        if not pm:
            continue
        slots[int(m.group(1))] = (
            m.group(3), [float(pm.group(i)) * 1000.0 for i in (1, 2, 3, 4)])

    keys = sorted(slots)
    out = {"per_arm": {}, "abba": {}}
    for j, name in enumerate(CHANNELS):
        for arm in ("base", "cand"):
            vs = [v[j] for a, v in slots.values() if a == arm]
            out["per_arm"][f"{name}_{arm}"] = statistics.mean(vs)
        deltas = []
        for i in range(0, len(keys) - 1, 2):
            a, b = slots[keys[i]], slots[keys[i + 1]]
            sign = 1.0 if a[0] == "base" else -1.0
            deltas.append(sign * (b[1][j] - a[1][j]))
        out["abba"][name] = ci(deltas)
    return out, slots


def wall_null_combined(logdir):
    """Identical-code adjacent-duplex spread (offset 1), all same-arm pairs."""
    slots = {}
    for path in sorted(glob.glob(os.path.join(logdir, "[0-9][0-9]-rep*.steps"))):
        m = STEPS_RE.match(os.path.basename(path))
        if not m:
            continue
        with open(path) as fh:
            ms = [float(x) for x in fh if x.strip()]
        slots[int(m.group(1))] = (m.group(3), [v * 1000.0 for v in ms[1:]])

    keys = sorted(slots)
    deltas = []
    for i in range(1, len(keys) - 1, 2):
        (aarm, av), (barm, bv) = slots[keys[i]], slots[keys[i + 1]]
        if aarm != barm:
            continue
        deltas.append(statistics.median(bv) - statistics.median(av))
    return ci(deltas)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--wall", required=True)
    ap.add_argument("--wall-null", required=True)
    ap.add_argument("--kernel", required=True)
    ap.add_argument("--kernel-null", required=True)
    ap.add_argument("--logdir", required=True)
    ap.add_argument("--base-sha", required=True)
    ap.add_argument("--cand-sha", required=True)
    ap.add_argument("--offline", action="store_true")
    args = ap.parse_args()

    wall, wall_null = load(args.wall), load(args.wall_null)
    kern, kern_null = load(args.kernel), load(args.kernel_null)
    n_streams, group_sizes, divergences = token_identity(args.logdir)
    dec, dec_slots = decompose(args.logdir)
    wnull = wall_null_combined(args.logdir)

    import wandb

    if args.offline:
        os.environ["WANDB_MODE"] = "offline"
    run = wandb.init(
        entity=ENTITY, project=PROJECT,
        name="maple-tanjiro-r100b-epilogue-report-and-session-factor",
        job_type="paired-abba-timing",
        tags=["pr555", "r100-b", "rev1", "epilogue-report", "session-factor",
              "decode", "fused-attention", "m4pro", "bit-exact"],
        config={
            "assignment_id": "maple-r100-b-epilogue-report-and-session-factor",
            "revision_id": "r100-b-rev1",
            "pr_number": 555,
            "base_sha": args.base_sha,
            "candidate_sha": args.cand_sha,
            "mechanism_reported_from": "PR #457 r85-C float4 merge epilogue",
            "host": "AWS M4 Pro, 20 GPU cores, Apple GPU generation 16, 48 GiB",
            "kernels_touched": list(TOUCHED),
            "threadgroup_bytes_before": 16896,
            "threadgroup_bytes_after": 16896,
            "stores_per_lane_before": 8,
            "stores_per_lane_after": 2,
            "loads_per_lane_before": 8,
            "loads_per_lane_after": 2,
            "barriers_before": 3,
            "barriers_after": 3,
            "simd_sum_before": 10,
            "simd_sum_after": 10,
            "editable_bytes_delta": -454,
            "editable_bytes_headroom_global": 16605,
            "editable_bytes_headroom_file": 13324,
            "command_buffers_per_step": 406.0,
            "dispatches_per_step": 406.0,
            "steps_per_run": wall["steady_steps"] + 1,
            "steady_steps": wall["steady_steps"],
            "abba_order": "base cand cand base",
            "reps": 4,
            "n_duplex_contrast": kern["n_duplex"],
            "n_duplex_null_cand": kern_null["n_duplex"],
            "pct_score_per_us_step": PCT_PER_US_STEP,
            "unit_convention": "un-ratioed (M4 us/step taken at face value)",
            "cross_machine_bracket": [1.00, 1.56],
            # Part 1 lottery corpus
            "receipt_corpus": "research/r93-runs/receipts-latest.json",
            "n_receipts": 1185,
            "record_to_beat": 2.61650354381456,
            "frontier_candidate_score": 2.575633,
        },
    )

    slot_tbl = wandb.Table(columns=["slot", "rep", "arm", "median_us_step",
                                    "trim10_us_step", "mean_us_step"])
    for s in wall["slots"]:
        slot_tbl.add_data(s["slot"], s["rep"], s["arm"], s["median"],
                          s["trimmed"], s["mean"])

    kern_tbl = wandb.Table(columns=["kernel", "base_us_step", "adj_us_step",
                                    "adj_ci_lo", "adj_ci_hi", "abs_us_step",
                                    "abs_ci_lo", "abs_ci_hi", "abs_sd",
                                    "null_adj_us_step", "touched"])
    null_labels = kern_null["labels"]
    for key, row in sorted(kern["labels"].items(),
                           key=lambda kv: -kv[1]["base_us_step"]):
        nrow = null_labels.get(key)
        kern_tbl.add_data(key, row["base_us_step"], row["adj_us_step"],
                          row["adj_ci"][0], row["adj_ci"][1],
                          row["abs_us_step"], row["abs_ci"][0],
                          row["abs_ci"][1], row["abs_sd_us_step"],
                          nrow["adj_us_step"] if nrow else float("nan"),
                          any(t in key for t in TOUCHED))

    dec_tbl = wandb.Table(columns=["channel", "base_mean_us_step",
                                   "cand_mean_us_step", "abba_delta_us_step",
                                   "ci_lo", "ci_hi", "sd", "n"])
    for name in CHANNELS:
        d = dec["abba"][name]
        dec_tbl.add_data(name, dec["per_arm"][f"{name}_base"],
                         dec["per_arm"][f"{name}_cand"],
                         d["mean"], d["lo"], d["hi"], d["sd"], d["n"])

    # Analyser sign convention: negative = candidate faster. Publish the win as
    # positive us/step saved so it reads with the same sign as the score delta.
    touched_saved = -sum(row["adj_us_step"] for key, row in kern["labels"].items()
                         if any(t in key for t in TOUCHED))
    med = wall["stats"]["median"]
    trim = wall["stats"]["trim10"]
    busy = dec["abba"]["busy_sum"]

    summary = {
        # primary: per-kernel GPU-busy census, the instrument that resolves the effect
        "gpu_busy_adj_saved_us_step": -kern["busy_adj"]["us_step"],
        "gpu_busy_adj_ci95_lo": -kern["busy_adj"]["ci"][1],
        "gpu_busy_adj_ci95_hi": -kern["busy_adj"]["ci"][0],
        "gpu_busy_adj_sd": kern["busy_adj"]["sd_us_step"],
        "gpu_busy_abs_saved_us_step": -kern["busy_abs"]["us_step"],
        "gpu_busy_abs_ci95_lo": -kern["busy_abs"]["ci"][1],
        "gpu_busy_abs_ci95_hi": -kern["busy_abs"]["ci"][0],
        "gpu_busy_null_adj_saved_us_step": -kern_null["busy_adj"]["us_step"],
        "gpu_busy_null_abs_saved_us_step": -kern_null["busy_abs"]["us_step"],
        "base_gpu_busy_us_step": kern["base_busy_us_step"],
        # touched kernels and the score conversion
        "touched_kernels_saved_us_step": touched_saved,
        "touched_kernels_score_pct": touched_saved * PCT_PER_US_STEP,
        "score_pct_from_busy_adj": -kern["busy_adj"]["us_step"] * PCT_PER_US_STEP,
        "r85c_published_score_pct": 0.2358,
        # wall/busy/gap decomposition
        "decomp_wall_delta_us_step": dec["abba"]["wall"]["mean"],
        "decomp_busy_sum_delta_us_step": busy["mean"],
        "decomp_busy_sum_ci_lo": busy["lo"],
        "decomp_busy_sum_ci_hi": busy["hi"],
        "decomp_busy_union_delta_us_step": dec["abba"]["busy_union"]["mean"],
        "decomp_gap_delta_us_step": dec["abba"]["gap"]["mean"],
        "decomp_gap_ci_lo": dec["abba"]["gap"]["lo"],
        "decomp_gap_ci_hi": dec["abba"]["gap"]["hi"],
        "decomp_base_wall_us_step": dec["per_arm"]["wall_base"],
        "decomp_cand_wall_us_step": dec["per_arm"]["wall_cand"],
        # wall estimator: reported, but underpowered by design
        "wall_median_saved_us_step": med["delta_us_step"],
        "wall_median_ci95_lo": med["ci95_lo"],
        "wall_median_ci95_hi": med["ci95_hi"],
        "wall_median_score_pct": med["score_pct"],
        "wall_trim10_saved_us_step": trim["delta_us_step"],
        "wall_null_saved_us_step": wnull["mean"],
        "wall_null_sd": wnull["sd"],
        "wall_null_n": wnull["n"],
        # correctness
        "distinct_token_streams": n_streams,
        "max_teacher_forced_divergences": max(divergences),
        "bit_exact_argmax": n_streams == 1 and max(divergences) == 0,
        "equivalence_exact_decode_steps": 8,
        "equivalence_prefill_max_abs_diff": 0.125,
        "equivalence_prefill_matches_unchanged_base": True,
        # Part 1 lottery
        "session_factor_identity_max_rel_err": 4.885e-15,
        "session_factor_sd_pct": 0.5393,
        "session_factor_mean_pct": -0.0041,
        "session_factor_lag1_autocorr": -0.0173,
        "record_session_factor_pct": 1.6278,
        "record_candidate_score": 2.574594,
        "p_beat_record_per_draw_frontier_pct": 0.422,
        "p_beat_record_per_draw_with_epilogue_pct": 0.675,
        "p_beat_record_per_draw_all_three_pct": 1.350,
        "receipts_spent": 0,
    }
    run.summary.update(summary)
    run.log({"slots": slot_tbl, "per_kernel": kern_tbl,
             "decomposition": dec_tbl, **summary})
    print(json.dumps(summary, indent=2))
    print(f"token stream groups: {group_sizes}")
    print(f"decomposition slots: {len(dec_slots)}")
    print(f"run id: {run.id}")
    print(f"run url: {run.url}")
    run.finish()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
