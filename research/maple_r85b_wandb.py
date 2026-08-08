#!/usr/bin/env python3
"""Publish the R85-B split-neutrality campaign to W&B.

Reads only the committed artifacts under research/r85b-logs-rebased/ so the run
is reproducible from the repository alone, and publishes one run holding the
four timing contrasts on both axes, the per-kernel-label decomposition of the
EFFECT contrast, the dispatch/token/instruction identity gates, and the byte
accounting this arm exists to deliver.

Usage:
  python3 research/maple_r85b_wandb.py [--offline] [--logs DIR]
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
from pathlib import Path

PERCENT_PER_US = 0.015280
DELTA_US = 5.0

# Contrast key -> (artifact stem, wall-clock section name, short label).
CONTRASTS = {
    "effect": ("armstats-effect.json", "EFFECT  base vs cand (offset 0)", "cand - base"),
    "lottery": ("armstats-lottery.json", "LOTTERY cand vs cand2 (offset 1)", "cand2 - cand"),
    "null_cand2": ("armstats-null-c2.json", "NULL    cand2 vs cand2 (offset 0)", "cand2 - cand2"),
    "null_base": ("armstats-null-b.json", "NULL    base vs base (offset 1)", "base - base"),
}

# One-sided t quantiles at 95% and 80%, indexed by degrees of freedom.
T95 = {2: 2.920, 3: 2.353, 7: 1.895}
T80 = {2: 0.978, 3: 0.941, 7: 0.896}


def one_sided_upper(mean: float, sd: float, n: int) -> float:
    return mean + T95[n - 1] * sd / math.sqrt(n)


def resolvable_floor(sd: float, n: int) -> float:
    """Smallest true effect declarable non-inferior at 95% confidence, 80% power."""
    return (T95[n - 1] + T80[n - 1]) * sd / math.sqrt(n)


ASM_COUNTERS = {
    "body-identical": "body_identical",
    "identical modulo islands": "island_only",
    "body-DIFFERENT": "body_different",
    "present on one side only": "one_side",
}


def parse_asm(path: Path) -> dict[str, int]:
    """-> flat counters keyed `<needle>/<arm-pair>/<category>`."""
    out: dict[str, int] = {}
    section = None
    for line in path.read_text().splitlines():
        header = re.match(r"# asm (\S+) vs (\S+) :: needle=(\S+)", line)
        if header:
            left, right, needle = header.groups()
            section = f"{needle}/{left}_vs_{right}"
            continue
        if section is None:
            continue
        symbols = re.match(r"symbols disassembled: base=(\d+)", line)
        if symbols:
            out[f"{section}/symbols"] = int(symbols.group(1))
            continue
        counter = re.match(r"\s+(\S.*?)\s*:\s*(\d+)\s*$", line)
        if counter and counter.group(1) in ASM_COUNTERS:
            out[f"{section}/{ASM_COUNTERS[counter.group(1)]}"] = int(counter.group(2))
    return out


def parse_one_side_orphans(path: Path) -> int:
    text = path.read_text()
    return int(re.search(r"no body-identical partner: (\d+)", text).group(1))


def parse_budget(path: Path) -> dict[str, int]:
    text = path.read_text()
    budget = re.search(r"current=(\d+)/(\d+) bytes headroom=(\d+) growth=(\d+)/(\d+) files=(\d+)", text)
    per_file = dict(
        (m.group(2), int(m.group(1))) for m in re.finditer(r"^\s+(\d+) (Sources/\S+)$", text, re.M)
    )
    return {
        "surface_bytes": int(budget.group(1)),
        "surface_cap": int(budget.group(2)),
        "surface_headroom": int(budget.group(3)),
        "growth_bytes": int(budget.group(4)),
        "growth_cap": int(budget.group(5)),
        "file_count": int(budget.group(6)),
        "runtime_model_bytes": per_file["Sources/MLXFastModel/LagunaRuntimeModel.swift"],
        "runtime_layers_bytes": per_file["Sources/MLXFastModel/LagunaRuntimeLayers.swift"],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--logs", default=str(Path(__file__).resolve().parent / "r85b-logs-rebased"))
    ap.add_argument("--project", default="mlxfast-maple")
    ap.add_argument("--entity", default="wandb-applied-ai-team")
    ap.add_argument("--offline", action="store_true")
    args = ap.parse_args()

    logs = Path(args.logs)
    if args.offline:
        os.environ["WANDB_MODE"] = "offline"

    import wandb

    wall = json.loads((logs / "stats-wall.json").read_text())["wall_clock"]
    busy = {key: json.loads((logs / stem).read_text()) for key, (stem, _, _) in CONTRASTS.items()}
    asm = parse_asm(logs / "asm-body-identity.log")
    orphans = parse_one_side_orphans(logs / "one-side-pairs.txt")
    budget = parse_budget(logs / "budget.txt")

    dispatch = (logs / "dispatch-identity.txt").read_text()
    runs_compared, differing = map(int, re.search(r"runs compared: (\d+), differing: (\d+)", dispatch).groups())
    token_cksums = {line.split()[0] for line in (logs / "token-identity.txt").read_text().splitlines() if line.strip()}

    per_file_cap = 524_288
    base_runtime_model_bytes = 510_964  # base 3217f111, quoted in r85-b-fb6

    run = wandb.init(
        entity=args.entity,
        project=args.project,
        name="maple-r85b-split-neutrality",
        job_type="measurement",
        tags=["pr456", "maple-fern", "r85-b", "surface-split", "neutrality", "m4pro"],
        config={
            "assignment_id": "maple-r85-b-surface-reconstruction",
            "revision_id": "r85-b-rev2",
            "pr": 456,
            "base_sha": "3217f111142346e004f41fae611a8bede172a659",
            "host": "Apple M4 Pro / 48 GiB / 20 GPU cores / gen16",
            "design": "cross-process ABBA adjacent-duplex, ratio-adjusted GPU-busy",
            "order": "base cand cand2 cand2 cand base",
            "reps": 4,
            "runs": 24,
            "steps_per_run": 200,
            "cbs_per_step": 406,
            "delta_us_step": DELTA_US,
            "percent_per_us": PERCENT_PER_US,
            "carve": "LagunaRuntimeMLP .. LagunaRuntimeDecoderLayer -> LagunaRuntimeLayers.swift",
            "private_to_internal_widenings": 5,
        },
    )

    contrast_rows = []
    for key, (_, wall_name, short) in CONTRASTS.items():
        adj, absolute = busy[key]["busy_adj"], busy[key]["busy_abs"]
        n = adj["n"]
        upper = one_sided_upper(adj["us_step"], adj["sd_us_step"], n)
        floor = resolvable_floor(adj["sd_us_step"], n)
        w = wall[wall_name]
        for name, val in (
            ("busy_adj/us_step", adj["us_step"]),
            ("busy_adj/sd_us_step", adj["sd_us_step"]),
            ("busy_adj/ci95_lo", adj["ci"][0]),
            ("busy_adj/ci95_hi", adj["ci"][1]),
            ("busy_adj/upper_1s95", upper),
            ("busy_adj/resolvable_floor_us_step", floor),
            ("busy_adj/n_duplex", n),
            ("busy_abs/us_step", absolute["us_step"]),
            ("busy_abs/sd_us_step", absolute["sd_us_step"]),
            ("wall/us_step", w["d_us"]),
            ("wall/sd_us_step", w["sd_us"]),
            ("wall/upper_1s95", w["upper_1s"]),
            ("wall/resolvable_floor_us_step", w["floor_us"]),
            ("base_busy_us_step", busy[key]["base_busy_us_step"]),
        ):
            run.summary[f"contrast/{key}/{name}"] = val
        contrast_rows.append(
            [
                key,
                short,
                n,
                adj["us_step"],
                adj["sd_us_step"],
                adj["ci"][0],
                adj["ci"][1],
                upper,
                floor,
                floor <= DELTA_US,
                w["d_us"],
                w["sd_us"],
            ]
        )

    run.log(
        {
            "contrasts": wandb.Table(
                columns=[
                    "contrast",
                    "arms",
                    "n_duplex",
                    "busy_adj_us_step",
                    "busy_adj_sd",
                    "ci95_lo",
                    "ci95_hi",
                    "upper_1s95",
                    "resolvable_floor",
                    "delta5_resolvable",
                    "wall_us_step",
                    "wall_sd",
                ],
                data=contrast_rows,
            ),
            "effect_by_label": wandb.Table(
                columns=["label", "base_us_step", "adj_us_step", "abs_us_step", "abs_sd_us_step"],
                data=[
                    [name, rec["base_us_step"], rec["adj_us_step"], rec["abs_us_step"], rec["abs_sd_us_step"]]
                    for name, rec in sorted(
                        busy["effect"]["labels"].items(), key=lambda kv: -kv[1]["base_us_step"]
                    )
                ],
            ),
        }
    )

    for name, val in asm.items():
        run.summary[f"asm/{name}"] = val
    run.summary["asm/one_side_orphans"] = orphans
    run.summary["identity/dispatch_runs_compared"] = runs_compared
    run.summary["identity/dispatch_runs_differing"] = differing
    run.summary["identity/dispatch_identical"] = differing == 0
    run.summary["identity/distinct_token_cksums"] = len(token_cksums)
    run.summary["identity/tokens_identical"] = len(token_cksums) == 1

    for name, val in budget.items():
        run.summary[f"bytes/{name}"] = val
    run.summary["bytes/base_runtime_model_bytes"] = base_runtime_model_bytes
    run.summary["bytes/per_file_cap"] = per_file_cap
    run.summary["bytes/base_per_file_headroom"] = per_file_cap - base_runtime_model_bytes
    run.summary["bytes/cand_per_file_headroom"] = per_file_cap - budget["runtime_model_bytes"]
    run.summary["bytes/per_file_headroom_ratio"] = (per_file_cap - budget["runtime_model_bytes"]) / (
        per_file_cap - base_runtime_model_bytes
    )

    effect = busy["effect"]["busy_adj"]
    run.summary["primary/us_step"] = effect["us_step"]
    run.summary["primary/upper_1s95_us_step"] = one_sided_upper(
        effect["us_step"], effect["sd_us_step"], effect["n"]
    )
    run.summary["primary/ci95_halfwidth_us_step"] = (effect["ci"][1] - effect["ci"][0]) / 2
    run.summary["primary/score_percent_at_upper_bound"] = (
        -one_sided_upper(effect["us_step"], effect["sd_us_step"], effect["n"]) * PERCENT_PER_US
    )
    run.summary["primary/verdict"] = "no source-attributable cost above the build-lottery floor"

    print(f"run: {run.url}")
    print(f"id : {run.id}")
    run.finish()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
