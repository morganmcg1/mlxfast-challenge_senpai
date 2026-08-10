#!/usr/bin/env python3
"""Analyse the R106-J paired ABBA run for DARKBLOOM_QMV_WIDE_CODES.

The driver (`research/maple_frieren_r106j_wide_codes_abba.sh`) writes one
`NN-repK-{off,on}.err` per process containing raw `GPUPROF <start> <end> <nops>
<names>` command-buffer records emitted by `research/nezuko-pr158-gpuprof-hook.patch`.

`research/decode_probe.py` correlates those records against the driver's
per-step wall spans, but the spans live only in the driver process, so this
script re-derives the steady window from the records themselves:

  the shared-QMV kernel fires exactly once per layer per forward, so the last
  `LAYERS * (STEPS - 1)` records of that kernel are the steady decode calls
  (step 0 is dropped: it pays the one-time KV growth concat).

The unit of analysis is the **process mean µs/call** (Rule 40: the process is
the randomisation unit, not the call), and the contrast is Welch on the six
process means per arm.  A kernel that the lever cannot touch is carried through
the identical pipeline as an invariant control.
"""
from __future__ import annotations

import argparse
import glob
import json
import math
import os
import re
import statistics
import sys

# The lever swaps one kernel for another, so match the family, not the leaf.
TARGET = re.compile(r"laguna_shared_nvfp4_swiglu_qmv_rows1")
CONTROL = re.compile(r"routed_shared_nvfp4_down_residual")

LAYERS = 39


def records(path: str, pattern: re.Pattern) -> list[tuple[float, float, str]]:
    out = []
    with open(path, errors="replace") as fh:
        for line in fh:
            if not line.startswith("GPUPROF "):
                continue
            parts = line.rstrip("\n").split(" ", 4)
            if len(parts) < 5:
                continue
            names = parts[4].strip()
            if not pattern.search(names):
                continue
            out.append((float(parts[1]), float(parts[2]), names))
    return out


def steady(path: str, pattern: re.Pattern, steps: int) -> dict:
    recs = records(path, pattern)
    want = LAYERS * (steps - 1)
    if len(recs) < want:
        return {"error": f"{os.path.basename(path)}: only {len(recs)} records, "
                         f"need {want}"}
    tail = recs[-want:]
    durs = [(e - s) * 1e6 for s, e, _ in tail]
    names = sorted({n for _, _, n in tail})
    return {
        "n_records_total": len(recs),
        "n_steady": len(durs),
        "kernel_names": names,
        "mean_us_per_call": statistics.mean(durs),
        "median_us_per_call": statistics.median(durs),
        "sd_us_per_call": statistics.pstdev(durs),
        "us_per_step": statistics.mean(durs) * LAYERS,
    }


def welch(a: list[float], b: list[float]) -> dict:
    """Two-sided Welch on small samples; normal critical value stated honestly."""
    na, nb = len(a), len(b)
    ma, mb = statistics.mean(a), statistics.mean(b)
    va = statistics.variance(a) if na > 1 else 0.0
    vb = statistics.variance(b) if nb > 1 else 0.0
    se = math.sqrt(va / na + vb / nb)
    delta = mb - ma
    if se == 0.0:
        return {"delta": delta, "se": 0.0, "t": float("nan"), "df": float("nan"),
                "ci95": [delta, delta]}
    t = delta / se
    num = (va / na + vb / nb) ** 2
    den = 0.0
    if na > 1:
        den += (va / na) ** 2 / (na - 1)
    if nb > 1:
        den += (vb / nb) ** 2 / (nb - 1)
    df = num / den if den else float("nan")
    # t critical at 95% for small df, table lookup (two-sided).
    table = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447,
             7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228, 11: 2.201, 12: 2.179,
             13: 2.160, 14: 2.145, 15: 2.131, 20: 2.086, 30: 2.042}
    key = min(table, key=lambda k: abs(k - df))
    tc = table[key]
    return {"delta": delta, "se": se, "t": t, "df": df, "t_crit_95": tc,
            "ci95": [delta - tc * se, delta + tc * se]}


def paired_by_block(arms: dict, which: str, pct_per_us_step: float) -> dict:
    """The contrast the ABBA design is actually built for.

    Each `off on on off` block is one pair: the two ON processes and the two OFF
    processes share the same block, and the mean *position* of ON equals the mean
    position of OFF (2.5 in both cases), so any drift that is linear in launch
    order cancels exactly inside a block.  The block delta is therefore the
    drift-free contrast, and the blocks are the independent replicates.
    """
    blocks: dict[str, dict[str, list[float]]] = {}
    for arm in ("off", "on"):
        for row in arms[arm]:
            m = re.match(r"(\d+)-(rep\d+)-", row["file"])
            if not m or "mean_us_per_call" not in row[which]:
                continue
            blocks.setdefault(m.group(2), {"off": [], "on": []})
            blocks[m.group(2)][arm].append(row[which]["mean_us_per_call"])
    deltas, detail = [], {}
    for rep in sorted(blocks):
        b = blocks[rep]
        if not b["off"] or not b["on"]:
            continue
        d = statistics.mean(b["on"]) - statistics.mean(b["off"])
        deltas.append(d)
        detail[rep] = {"off_mean": statistics.mean(b["off"]),
                       "on_mean": statistics.mean(b["on"]), "delta": d}
    n = len(deltas)
    if n < 2:
        return {"blocks": detail, "note": "fewer than two blocks"}
    mean = statistics.mean(deltas)
    sd = statistics.stdev(deltas)
    se = sd / math.sqrt(n)
    tc = {2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571}.get(n - 1, 2.0)
    ci = [mean - tc * se, mean + tc * se]
    return {
        "blocks": detail, "n_blocks": n, "deltas": deltas,
        "mean_delta_us_per_call": mean, "sd_across_blocks": sd, "se": se,
        "t": mean / se if se else float("nan"), "df": n - 1, "t_crit_95": tc,
        "ci95_us_per_call": ci,
        "mean_delta_us_per_step": mean * LAYERS,
        "ci95_us_per_step": [c * LAYERS for c in ci],
        "pct_of_score": -mean * LAYERS * pct_per_us_step,
        "pct_of_score_ci95": sorted(-c * LAYERS * pct_per_us_step for c in ci),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="/tmp/r106j-abba")
    ap.add_argument("--steps", type=int, default=33)
    ap.add_argument("--pct-per-us-step", type=float, default=0.015228,
                    help="%% of score per us/step of decode (assignment constant)")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    arms: dict[str, list[dict]] = {"off": [], "on": []}
    for path in sorted(glob.glob(os.path.join(args.dir, "*.err"))):
        base = os.path.basename(path)
        arm = "on" if base.endswith("-on.err") else "off"
        row = {"file": base,
               "target": steady(path, TARGET, args.steps),
               "control": steady(path, CONTROL, args.steps)}
        arms[arm].append(row)

    report = {"dir": args.dir, "steps": args.steps, "layers": LAYERS,
              "processes": arms}

    for which in ("target", "control"):
        vals = {}
        for arm in ("off", "on"):
            vals[arm] = [r[which]["mean_us_per_call"] for r in arms[arm]
                         if "mean_us_per_call" in r[which]]
        if not vals["off"] or not vals["on"]:
            continue
        w = welch(vals["off"], vals["on"])
        w["off_means"] = vals["off"]
        w["on_means"] = vals["on"]
        w["off_mean"] = statistics.mean(vals["off"])
        w["on_mean"] = statistics.mean(vals["on"])
        w["off_sd_across_processes"] = (statistics.stdev(vals["off"])
                                        if len(vals["off"]) > 1 else 0.0)
        w["on_sd_across_processes"] = (statistics.stdev(vals["on"])
                                       if len(vals["on"]) > 1 else 0.0)
        w["delta_us_per_step"] = w["delta"] * LAYERS
        w["ci95_us_per_step"] = [c * LAYERS for c in w["ci95"]]
        w["pct_of_score"] = -w["delta_us_per_step"] * args.pct_per_us_step
        w["pct_of_score_ci95"] = sorted(
            -c * LAYERS * args.pct_per_us_step for c in w["ci95"])
        report[which] = w
        report[which + "_paired_by_block"] = paired_by_block(
            arms, which, args.pct_per_us_step)

    # Wall-clock ms/step from the driver logs, as a coarse cross-check only.
    wall = {"off": [], "on": []}
    for path in sorted(glob.glob(os.path.join(args.dir, "*.log"))):
        arm = "on" if path.endswith("-on.log") else "off"
        for line in open(path, errors="replace"):
            m = re.search(r"decode steps=\d+ mean=([0-9.]+) ms", line)
            if m:
                wall[arm].append(float(m.group(1)))
    if wall["off"] and wall["on"]:
        report["wall_ms_per_step"] = {
            "off": wall["off"], "on": wall["on"],
            "welch": welch(wall["off"], wall["on"])}

    text = json.dumps(report, indent=2)
    print(text)
    if args.out:
        with open(args.out, "w") as fh:
            fh.write(text + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
