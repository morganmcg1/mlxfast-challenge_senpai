#!/usr/bin/env python3
"""Log the PR #457 R85-C placement battery to W&B.

Every contrast number is read back from the JSON that
`research/maple_r85_arm_stats.py` wrote, so the W&B run and the report cannot
drift apart. Per-run wall/busy rows are parsed from the probe stdout logs,
which are also the source of the calibrated noise floor.

  python3 research/maple_r85_wandb.py \
      --contrast-dir research/maple-r85-logs \
      --arms-dir /tmp/maple-r85-arms --arms-dir /tmp/maple-r85-pad-arms \
      --inert-dir /tmp/maple-r85-inert --inert-dir /tmp/maple-r85-pad-inert
"""
import argparse
import glob
import hashlib
import json
import math
import os
import re
import statistics

ENTITY = "wandb-applied-ai-team"
PROJECT = "mlxfast-maple"

SLOT_RE = re.compile(r"^(\d+)-rep(\d+)-([a-z_]+)\.log$")
STEP_RE = re.compile(
    r"per steady step: wall=(?P<wall>[\d.]+) ms gpu_busy_sum=(?P<busy>[\d.]+) ms"
    r" gpu_busy_union=(?P<union>[\d.]+) ms gap=(?P<gap>[\d.]+) ms"
    r" \((?P<gappct>[\d.]+)% of wall\) cbs=(?P<cbs>[\d.]+)")
DECODE_RE = re.compile(
    r"decode steps=(?P<steps>\d+) mean=(?P<mean>[\d.]+) ms"
    r" median=(?P<median>[\d.]+) ms")
DIVERGE_RE = re.compile(r"teacher-forced greedy tokens: (\d+) divergences")
# Only the halved/dose arms build the extra scale plane; other "packed-scales
# active" lines are emitted by every arm and must not be matched.
PLANE_MESSAGE = "packed-scales active: shared gate/up halved scale plane"

# Contrast tag -> (arm_a, arm_b, what it isolates).
CONTRASTS = {
    "placement": ("base", "dose_one",
                  "retain 39 unread ~82 KB planes; read set unchanged"),
    "doseresponse": ("base", "dose_two",
                     "retain 78 unread planes; read set unchanged"),
    "dosestep": ("dose_one", "dose_two",
                 "second dose step, counterbalanced pairing phase"),
    "readonly": ("dose_one", "halved",
                 "footprint held, read set halved (PR #443's win)"),
    "null": ("base", "base", "in-session null floor"),
    "padaddr": ("halved", "halved_pad",
                "16 KiB x PAD_PAGES address displacement per plane"),
    "posctl": ("base", "halved",
               "within-session replay of PR #443 end to end"),
    "padnull": ("halved_pad", "halved_pad", "in-session null floor, pad arm"),
    "armnull": ("halved", "halved", "in-session null floor, halved arm"),
}

CONTRAST_COLS = [
    "contrast", "arm_a", "arm_b", "isolates", "n_duplex", "offset",
    "giveback6_us_step", "giveback6_ci95", "total_adj_us_step",
    "total_adj_ci95", "total_adj_sd", "total_abs_us_step", "total_abs_ci95",
    "total_abs_sd", "base_busy_us_step", "resolves_38us",
]
KERNEL_COLS = [
    "contrast", "kernel", "base_us_step", "adj_us_step", "adj_ci95_lo",
    "adj_ci95_hi", "abs_us_step", "abs_ci95_lo", "abs_ci95_hi",
    "adj_significant", "is_giveback6",
]
RUN_COLS = [
    "set", "slot", "rep", "arm", "wall_us_step", "gpu_busy_us_step",
    "gpu_gap_us_step", "gap_percent_of_wall", "cbs_per_step",
    "decode_mean_ms", "decode_median_ms", "divergences",
]
NOISE_COLS = [
    "estimator", "unit", "sd", "n", "ci95_half_width_1v1",
    "half_width_at_n8", "percent_of_score_at_n8", "resolves_38us_step",
]
INERT_COLS = ["set", "arm", "digest", "matches_reference", "plane_message"]

GIVEBACK6 = (
    "routed_shared_nvfp4_down_residual",
    "sliding_fused_attn_ring",
    "full_fused_attn_grow",
    "gate_sp_h48",
    "oproj_act_h64",
    "dense_down_residual",
)
# Score sensitivity measured for this window: 1 us/step of decode is this many
# percent of the published score.
PCT_PER_US_STEP = 0.015280
TARGET_US_STEP = 38.0


def hw(ci):
    """Half-width of a [lo, hi] interval as emitted by maple_r85_arm_stats.py."""
    return 0.5 * (ci[1] - ci[0])


def is_giveback(kernel):
    return any(kernel.startswith(g) for g in GIVEBACK6)


def giveback_rows(labels):
    return [v for k, v in labels.items() if is_giveback(k)]


def load_runs(dirs):
    rows = []
    for d in dirs:
        for path in sorted(glob.glob(os.path.join(d, "[0-9][0-9]-rep*.log"))):
            m = SLOT_RE.match(os.path.basename(path))
            if not m:
                continue
            text = open(path, errors="replace").read()
            step = STEP_RE.search(text)
            if not step:
                continue
            dec = DECODE_RE.search(text)
            div = DIVERGE_RE.search(text)
            rows.append(dict(
                set=os.path.basename(d.rstrip("/")), slot=int(m.group(1)),
                rep=int(m.group(2)), arm=m.group(3),
                wall=1000.0 * float(step.group("wall")),
                busy=1000.0 * float(step.group("busy")),
                gap=1000.0 * float(step.group("gap")),
                gappct=float(step.group("gappct")),
                cbs=float(step.group("cbs")),
                decode_mean=float(dec.group("mean")) if dec else None,
                decode_median=float(dec.group("median")) if dec else None,
                divergences=int(div.group(1)) if div else None))
    return rows


def load_inert(dirs):
    """Digest the emitted free-run token files, exactly as the gate script does.

    A free run compounds any divergence, so two arms share a digest only if
    every generated token agreed.
    """
    rows = []
    for d in dirs:
        for path in sorted(glob.glob(os.path.join(d, "*.tokens"))):
            arm = os.path.basename(path)[:-len(".tokens")]
            digest = hashlib.sha256(open(path, "rb").read()).hexdigest()[:12]
            err = path[:-len(".tokens")] + ".err"
            etext = open(err, errors="replace").read() if os.path.exists(err) \
                else ""
            rows.append(dict(arm=arm, digest=digest, set=os.path.basename(
                d.rstrip("/")), plane=PLANE_MESSAGE in etext))
    ref = next((r["digest"] for r in rows if r["arm"] == "base"), None)
    for r in rows:
        r["matches"] = None if not ref else r["digest"] == ref
    return rows


def sd_stats(values):
    n = len(values)
    if n < 2:
        return None
    sd = statistics.stdev(values)
    # Paired 1-vs-1 comparison of two independent draws.
    hw1 = 1.96 * sd * math.sqrt(2.0)
    hw8 = 1.96 * sd / math.sqrt(8.0)
    return n, sd, hw1, hw8


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--contrast-dir", default="research/maple-r85-logs")
    ap.add_argument("--arms-dir", action="append", default=[])
    ap.add_argument("--inert-dir", action="append", default=[])
    ap.add_argument("--run-name", default="maple-r85c-placement-lever")
    ap.add_argument("--offline", action="store_true")
    args = ap.parse_args()

    contrasts = {}
    for tag in CONTRASTS:
        path = os.path.join(args.contrast_dir, f"r85c-{tag}.json")
        if os.path.exists(path):
            contrasts[tag] = json.load(open(path))
    anchors = {}
    for path in sorted(glob.glob(os.path.join(
            args.contrast_dir, "r85c-*-anchor-*.json"))):
        name = os.path.basename(path)[len("r85c-"):-len(".json")]
        anchors[name] = json.load(open(path))
    if not contrasts:
        raise RuntimeError("no contrast JSON found; refusing to publish")

    runs = load_runs(args.arms_dir)
    inert = load_inert(args.inert_dir)

    import wandb
    if args.offline:
        os.environ["WANDB_MODE"] = "offline"
    run = wandb.init(
        entity=ENTITY, project=PROJECT, name=args.run_name,
        job_type="r85c-placement-lever",
        config={
            "pr": 457,
            "assignment": "maple-r85-c-placement-lever",
            "revision": "r85-c-rev1",
            "branch": "maple-frieren/r85-placement-lever",
            "base_sha": "cc5688d0dfd6347bde0efd624cd6e10fdd4cfd26",
            "base_sha_current": "f64456dd2dc503af080dca65bddfb922164c7bc5",
            "host": "Mac16,11 M4 Pro 14c 48GiB macOS 26.5.2",
            "apple_gpu_generation": 16,
            "nax_reachable": False,
            "m5_directional_only": True,
            "probe": "research/decode_probe.py --steps 33 --profile",
            "steady_steps": 32,
            "cbs_per_step": 406,
            "flags": {
                "DARKBLOOM_SHARED_SCALE_HALVED": "unset (default off)",
                "DARKBLOOM_SHARED_SCALE_PLACEMENT_DOSE": "unset (default 0)",
                "DARKBLOOM_SHARED_SCALE_PAD_PAGES": "unset (default 0)",
            },
            "pct_of_score_per_us_step": PCT_PER_US_STEP,
            "submitted_surface":
                "Sources/MLXFastModel/LagunaRuntimeModel.swift",
            "timed_runs": len(runs),
            "arm_sets": sorted(set(r["set"] for r in runs)),
        })

    summary = {}

    ctab = wandb.Table(columns=CONTRAST_COLS)
    ktab = wandb.Table(columns=KERNEL_COLS)
    for tag, data in contrasts.items():
        arm_a, arm_b, isolates = CONTRASTS[tag]
        labels = data["labels"]
        give = giveback_rows(labels)
        g_sum = sum(x["adj_us_step"] for x in give)
        g_ci = math.sqrt(sum(hw(x["adj_ci"]) ** 2 for x in give))
        adj, abs_ = data["busy_adj"], data["busy_abs"]
        ctab.add_data(
            tag, arm_a, arm_b, isolates, data["n_duplex"], data["offset"],
            g_sum, g_ci, adj["us_step"], hw(adj["ci"]), adj["sd_us_step"],
            abs_["us_step"], hw(abs_["ci"]), abs_["sd_us_step"],
            data["base_busy_us_step"],
            bool(hw(adj["ci"]) < TARGET_US_STEP / 2))
        for kernel, v in sorted(labels.items(),
                                key=lambda kv: -abs(kv[1]["adj_us_step"])):
            ktab.add_data(
                tag, kernel, v["base_us_step"], v["adj_us_step"],
                v["adj_ci"][0], v["adj_ci"][1],
                v["abs_us_step"], v["abs_ci"][0], v["abs_ci"][1],
                bool(v["adj_ci"][0] > 0.0 or v["adj_ci"][1] < 0.0),
                is_giveback(kernel))
        for field, val in (("giveback6_us_step", g_sum),
                           ("giveback6_ci95", g_ci),
                           ("total_adj_us_step", adj["us_step"]),
                           ("total_adj_ci95", hw(adj["ci"])),
                           ("total_abs_us_step", abs_["us_step"]),
                           ("total_abs_ci95", hw(abs_["ci"])),
                           ("n_duplex", data["n_duplex"])):
            summary[f"{tag}/{field}"] = val
        summary[f"{tag}/giveback6_percent_of_score"] = g_sum * PCT_PER_US_STEP

    atab = wandb.Table(columns=["contrast", "anchor", "n_duplex",
                                "giveback6_us_step", "giveback6_ci95",
                                "contains_zero"])
    for name, data in anchors.items():
        tag, anchor = name.split("-anchor-", 1)
        labels = data["labels"]
        give = giveback_rows(labels)
        g_sum = sum(x["adj_us_step"] for x in give)
        g_ci = math.sqrt(sum(hw(x["adj_ci"]) ** 2 for x in give))
        atab.add_data(tag, anchor, data["n_duplex"], g_sum, g_ci,
                      bool(abs(g_sum) < g_ci))

    rtab = wandb.Table(columns=RUN_COLS)
    for r in runs:
        rtab.add_data(r["set"], r["slot"], r["rep"], r["arm"], r["wall"],
                      r["busy"], r["gap"], r["gappct"], r["cbs"],
                      r["decode_mean"], r["decode_median"], r["divergences"])

    ntab = wandb.Table(columns=NOISE_COLS)

    def add_noise(name, unit, values, n_override=None):
        st = sd_stats(values)
        if not st:
            return
        n, sd, hw1, hw8 = st
        ntab.add_data(name, unit, sd, n_override or n, hw1, hw8,
                      hw8 * PCT_PER_US_STEP, bool(hw1 < TARGET_US_STEP))

    for key, label in (("wall", "whole-step wall clock"),
                       ("busy", "whole-step GPU busy sum")):
        for arm in sorted(set(r["arm"] for r in runs)):
            xs = [r[key] for r in runs if r["arm"] == arm and r["slot"] > 1]
            add_noise(f"{label}, arm={arm}, slot>1", "us/step", xs)
        add_noise(f"{label}, pooled slot>1", "us/step",
                  [r[key] for r in runs if r["slot"] > 1])
    for tag, data in contrasts.items():
        sd = data["busy_adj"]["sd_us_step"]
        if sd and not math.isnan(sd):
            ntab.add_data(f"ratio-adjusted whole-step busy, {tag}", "us/step",
                          sd, data["n_duplex"], 1.96 * sd,
                          1.96 * sd / math.sqrt(8.0),
                          1.96 * sd / math.sqrt(8.0) * PCT_PER_US_STEP,
                          bool(1.96 * sd < TARGET_US_STEP))

    first = [r for r in runs if r["slot"] == 1]
    later = [r for r in runs if r["slot"] > 1]
    if first and later:
        pen = statistics.mean(r["wall"] for r in first) - \
            statistics.median([r["wall"] for r in later])
        summary["noise/first_run_penalty_us_step"] = pen
        summary["noise/first_run_penalty_x_target"] = pen / TARGET_US_STEP

    itab = wandb.Table(columns=INERT_COLS)
    for r in inert:
        itab.add_data(r["set"], r["arm"], r["digest"], r["matches"],
                      r["plane"])
    summary["correctness/inertness_arms"] = len(inert)
    summary["correctness/inertness_all_match"] = bool(
        inert and all(r["matches"] for r in inert))
    summary["correctness/teacher_forced_divergences"] = sum(
        r["divergences"] or 0 for r in runs)
    summary["correctness/teacher_forced_comparisons"] = sum(
        33 for r in runs if r["divergences"] is not None)

    run.log({
        "contrasts": ctab, "kernels": ktab, "anchors": atab, "runs": rtab,
        "noise_floor": ntab, "inertness": itab,
    })
    run.summary.update(summary)
    for k in sorted(summary):
        print(f"{k}: {summary[k]}")
    print(f"wandb url: {run.url}")
    run.finish()


if __name__ == "__main__":
    main()
