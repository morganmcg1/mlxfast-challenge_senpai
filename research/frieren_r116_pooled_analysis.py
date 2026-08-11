#!/usr/bin/env python3
"""Pool the R116-A screen and confirmation stages to the advisor's instrument standard.

    python3 research/frieren_r116_pooled_analysis.py SCREEN_DIR CONFIRM_DIR \
        [--control ctl] [--min-token 16] [--csv OUT.csv] [--json OUT.json]

The 03:50Z instrument standard asks for: paired blocks, >= 64 measured decode
cycles per order, ABBA and BAAB reported separately, a bootstrap CI on the
median paired saving, and the raw sample array dumped to CSV.

Blocks alternate order by parity in both runners: odd block = forward arm order
(ABBA), even block = reversed (BAAB). Screen and confirmation blocks are kept as
distinct labels (S1..Sn, C1..Cn) because they contain different arm sets and so
have different block durations and thermal context; every contrast is still
formed strictly within one block.
"""
import argparse
import csv
import glob
import json
import os
import random
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from frieren_steady_step import NAME, samples

EMAX = {1: 0.0, 2: 0.5642, 3: 0.8463, 4: 1.0294, 5: 1.1630, 6: 1.2672,
        7: 1.3522, 8: 1.4236, 9: 1.4850, 10: 1.5388}


def load(logdir, stage, min_token):
    rows = []
    for path in sorted(glob.glob(os.path.join(logdir, "log-*.txt"))):
        m = NAME.search(os.path.basename(path))
        if not m:
            continue
        arm, block = m.group(1), int(m.group(2))
        vals = [v * 1e6 for v in samples(path, min_token)]
        if not vals:
            continue
        rows.append({
            "stage": stage,
            "block": f"{stage[0].upper()}{block}",
            "order": "ABBA" if block % 2 == 1 else "BAAB",
            "arm": arm,
            "n_tokens": len(vals),
            "steady_mean_us": statistics.mean(vals),
            "steady_median_us": statistics.median(vals),
            "within_sd_us": statistics.stdev(vals) if len(vals) > 1 else 0.0,
            "raw_us": vals,
        })
    return rows


def paired(rows, control):
    """One paired delta per (arm, block); the control is always same-block."""
    by_block = {}
    for r in rows:
        by_block.setdefault(r["block"], {})[r["arm"]] = r
    out = []
    for block, arms in by_block.items():
        if control not in arms:
            continue
        base = arms[control]["steady_mean_us"]
        for arm, r in arms.items():
            if arm == control:
                continue
            out.append({"arm": arm, "block": block, "stage": r["stage"],
                        "order": r["order"],
                        "delta_us": r["steady_mean_us"] - base,
                        "n_tokens": r["n_tokens"]})
    return out


def boot_median_ci(diffs, iters=20000, seed=20260811):
    if len(diffs) < 2:
        return float("nan"), float("nan")
    rng = random.Random(seed)
    meds = []
    for _ in range(iters):
        meds.append(statistics.median(
            [diffs[rng.randrange(len(diffs))] for _ in diffs]))
    meds.sort()
    return meds[int(0.025 * iters)], meds[int(0.975 * iters)]


def summarize(diffs):
    mean = statistics.mean(diffs)
    if len(diffs) < 2:
        return {"n": len(diffs), "mean_us": mean, "sem_us": float("nan"),
                "t": float("nan"), "median_us": mean,
                "ci_lo_us": float("nan"), "ci_hi_us": float("nan")}
    sem = statistics.stdev(diffs) / len(diffs) ** 0.5
    lo, hi = boot_median_ci(diffs)
    return {"n": len(diffs), "mean_us": mean, "sem_us": sem,
            "t": mean / sem if sem else float("nan"),
            "median_us": statistics.median(diffs), "ci_lo_us": lo,
            "ci_hi_us": hi}


def permutation_argmax_null(rows, control, iters=20000, seed=20260811):
    """False-positive calibration in place of a duplicate-control arm.

    Shuffles arm labels within each block and records how negative the best
    arm's pooled mean looks under the null. The observed argmax must beat this
    distribution to mean anything.
    """
    by_block = {}
    for r in rows:
        if r["arm"] == control:
            continue
        by_block.setdefault(r["block"], []).append(r["delta_us"])
    if not by_block:
        return None
    # Only blocks carrying the full arm set are comparable; a screen block has
    # 8 arms and a confirmation block has 3, so pooling them would silently
    # shrink the null to the smaller width.
    k = max(len(v) for v in by_block.values())
    blocks = [v for v in by_block.values() if len(v) == k]
    if k < 2 or len(blocks) < 2:
        return None
    rng = random.Random(seed)
    best = []
    for _ in range(iters):
        cols = [[] for _ in range(k)]
        for vals in blocks:
            v = vals[:k]
            rng.shuffle(v)
            for i in range(k):
                cols[i].append(v[i])
        best.append(min(statistics.mean(c) for c in cols))
    best.sort()
    return {"arms": k, "blocks": len(blocks),
            "p05_us": best[int(0.05 * iters)],
            "p50_us": best[int(0.50 * iters)],
            "min_us": best[0]}


# 0.00836 % of score per M4 wall us/step at tau=1 (banked r109 conversion).
PCT_PER_US_TAU1 = 0.00836


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("screen_dir")
    ap.add_argument("confirm_dir")
    ap.add_argument("--control", default="ctl")
    ap.add_argument("--min-token", type=int, default=16)
    ap.add_argument("--csv", default="")
    ap.add_argument("--json", default="")
    a = ap.parse_args()

    rows = (load(a.screen_dir, "screen", a.min_token)
            + load(a.confirm_dir, "confirm", a.min_token))
    if not rows:
        sys.exit("no parsable logs")
    diffs = paired(rows, a.control)
    arms = sorted({d["arm"] for d in diffs})

    cycles = {}
    for r in rows:
        cycles.setdefault((r["arm"], r["order"]), 0)
        cycles[(r["arm"], r["order"])] += r["n_tokens"]

    report = {"arms": {}, "control": a.control, "min_token": a.min_token}
    print(f"pooled paired contrasts vs {a.control} "
          f"(+us = slower; steady tail, tokens >= {a.min_token})\n")
    hdr = ("arm", "n", "mean_us", "sem", "t", "median", "ci95_lo", "ci95_hi",
           "cyc_ABBA", "cyc_BAAB")
    print("{:<8}{:>4}{:>10}{:>8}{:>8}{:>9}{:>9}{:>9}{:>10}{:>10}".format(*hdr))
    for arm in arms:
        d = [x["delta_us"] for x in diffs if x["arm"] == arm]
        s = summarize(d)
        report["arms"][arm] = {"pooled": s, "by_order": {}, "by_stage": {}}
        print("{:<8}{:>4}{:>10.1f}{:>8.1f}{:>8.2f}{:>9.1f}{:>9.1f}{:>9.1f}"
              "{:>10}{:>10}".format(
                  arm, s["n"], s["mean_us"], s["sem_us"], s["t"],
                  s["median_us"], s["ci_lo_us"], s["ci_hi_us"],
                  cycles.get((arm, "ABBA"), 0), cycles.get((arm, "BAAB"), 0)))

    print("\nby order (advisor instrument standard: report ABBA and BAAB "
          "separately)")
    print("{:<8}{:<6}{:>4}{:>10}{:>8}{:>8}".format(
        "arm", "order", "n", "mean_us", "sem", "t"))
    for arm in arms:
        for order in ("ABBA", "BAAB"):
            d = [x["delta_us"] for x in diffs
                 if x["arm"] == arm and x["order"] == order]
            if not d:
                continue
            s = summarize(d)
            report["arms"][arm]["by_order"][order] = s
            print("{:<8}{:<6}{:>4}{:>10.1f}{:>8.1f}{:>8.2f}".format(
                arm, order, s["n"], s["mean_us"], s["sem_us"], s["t"]))

    print("\nby stage (screen blocks are the preregistration's own prior)")
    print("{:<8}{:<9}{:>4}{:>10}{:>8}{:>8}".format(
        "arm", "stage", "n", "mean_us", "sem", "t"))
    for arm in arms:
        for stage in ("screen", "confirm"):
            d = [x["delta_us"] for x in diffs
                 if x["arm"] == arm and x["stage"] == stage]
            if not d:
                continue
            s = summarize(d)
            report["arms"][arm]["by_stage"][stage] = s
            print("{:<8}{:<9}{:>4}{:>10.1f}{:>8.1f}{:>8.2f}".format(
                arm, stage, s["n"], s["mean_us"], s["sem_us"], s["t"]))

    gaps = []
    for arm in arms:
        by = report["arms"][arm]["by_order"]
        if "ABBA" in by and "BAAB" in by:
            gaps.append(by["ABBA"]["mean_us"] - by["BAAB"]["mean_us"])
    if gaps:
        report["order_effect"] = {
            "n_arms": len(gaps), "mean_abba_minus_baab_us": statistics.mean(gaps),
            "sd_us": statistics.stdev(gaps) if len(gaps) > 1 else float("nan"),
            "max_abs_us": max(abs(g) for g in gaps)}
        print(f"\nposition effect: ABBA-minus-BAAB per arm averages "
              f"{statistics.mean(gaps):+.1f}us, sd "
              f"{report['order_effect']['sd_us']:.1f}us, largest single arm "
              f"{report['order_effect']['max_abs_us']:.1f}us")
        print("  -> compare against the flag effects above; where the position "
              "effect is larger, order balance is doing the real work")

    best = min(arms, key=lambda x: report["arms"][x]["pooled"]["mean_us"])
    bs = report["arms"][best]["pooled"]
    bias = bs["sem_us"] * EMAX.get(len(arms), 1.5388)
    report["argmax"] = {"arm": best, "raw_us": bs["mean_us"],
                        "debias_us": bias, "debiased_us": bs["mean_us"] + bias}
    print(f"\nargmax={best} raw={bs['mean_us']:.1f}us "
          f"debias(+{bias:.1f}us for best-of-{len(arms)}) -> "
          f"{bs['mean_us'] + bias:.1f}us")

    report["permutation_null"] = {}
    for stage in ("screen", "confirm"):
        null = permutation_argmax_null(
            [d for d in diffs if d["stage"] == stage], a.control)
        if not null:
            continue
        report["permutation_null"][stage] = null
        per_arm = [statistics.mean(d) for d in
                   ([x["delta_us"] for x in diffs
                     if x["arm"] == arm and x["stage"] == stage]
                    for arm in arms) if d]
        obs = min(per_arm)
        null["observed_argmax_us"] = obs
        print(f"permutation argmax null [{stage}] ({null['arms']} arms x "
              f"{null['blocks']} blocks, labels shuffled within block): "
              f"p50={null['p50_us']:.1f}us p05={null['p05_us']:.1f}us "
              f"min={null['min_us']:.1f}us | observed argmax {obs:.1f}us "
              f"-> {'BEATS' if obs < null['p05_us'] else 'inside'} the null")

    print(f"\nprice of the argmax: {abs(bs['mean_us']) * PCT_PER_US_TAU1:.3f}% "
          f"of score pre-tau, "
          f"{abs(bs['mean_us']) * PCT_PER_US_TAU1 * 0.4:.3f}% at tau=0.4 "
          f"(campaign screening threshold is +0.25% pre-tau = 29.9 us/step)")

    if a.csv:
        with open(a.csv, "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["stage", "block", "order", "arm", "token_index",
                        "step_us"])
            for r in sorted(rows, key=lambda x: (x["stage"], x["block"],
                                                 x["arm"])):
                for i, v in enumerate(r["raw_us"]):
                    w.writerow([r["stage"], r["block"], r["order"], r["arm"],
                                a.min_token + i, f"{v:.1f}"])
        print(f"\nraw sample array -> {a.csv}")
    if a.json:
        report["per_run"] = [{k: v for k, v in r.items() if k != "raw_us"}
                             for r in rows]
        report["paired"] = diffs
        with open(a.json, "w") as fh:
            json.dump(report, fh, indent=2)
        print(f"report -> {a.json}")


if __name__ == "__main__":
    main()
