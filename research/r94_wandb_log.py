#!/usr/bin/env python3
"""Publish the R94-A decode dispatch ledger to W&B as durable analysis evidence.

Analysis-only: no GPU work, no timing arm. The numbers come from
research/r94-artifacts/r94-dispatch-ledger.tsv, which r94_ledger_build.py emits
and self-checks for closure.
"""

import csv
import pathlib

import wandb

ROOT = pathlib.Path(__file__).resolve().parent
LEDGER = ROOT / "r94-artifacts" / "r94-dispatch-ledger.tsv"
REPORT = ROOT / "r94-artifacts" / "r94-ledger-report.txt"
WRITEUP = ROOT / "maple-frieren-r94-decode-residue-ledger.md"

# Stage 2 roofline pools, nat-deflated us/step. See writeup section 2.
POOLS = {
    "bytes_bound_us_per_step": 6090.4,
    "latency_bound_attention_us_per_step": 813.0,
    "partly_bytes_bound_us_per_step": 497.1,
    "launch_ramp_overhead_us_per_step": 592.9,
}

CONFIG = {
    "assignment_id": "maple-r94-a-decode-residue-ledger",
    "revision_id": "r94-a-rev1",
    "pr_number": 502,
    "base_sha": "d549d31856953292b9b2b54905cf3f6f67ed27a4",
    "host": "Apple M4 Pro, 48 GiB, macOS 26.5.2",
    "gpu_arch": "applegpu_g16s (gen 16; _nax prefill kernels unreachable)",
    "peak_bandwidth_gb_per_s": 273.0,
    "regime_attribution": "SPLIT=1 per-kernel census (rule 43: attribution only)",
    "regime_magnitude": "nat, deflated by 1.317 us/dispatch",
    "timing_arm_run": False,
    "shipped_code_change": False,
    "submitted_surface_identical_to_base": True,
}


def main() -> None:
    with LEDGER.open() as fh:
        rows = list(csv.DictReader(fh, delimiter="\t"))

    run = wandb.init(
        project="mlxfast-maple",
        entity="wandb-applied-ai-team",
        group="maple-frieren-r94a",
        job_type="dispatch-ledger-analysis",
        name="r94a-decode-dispatch-ledger",
        config=CONFIG,
        notes=(
            "R94-A: complete 24-label decode dispatch ledger. The claimed "
            "~1186 us/step residue does not exist; the ledger closes to "
            "+0.3 us (+0.004%) over 406/406 dispatches. Stage 3 fusion is a "
            "no-go: the largest fusable cluster (gate_sp, 275.5 us, 40 "
            "dispatches) is closed prior art (PR #9 M2 +2.7% on M4; PR #48 "
            "mode 2 -0.1488% on ranked M5)."
        ),
    )

    table = wandb.Table(
        columns=[
            "label",
            "kind",
            "origin",
            "calls_per_step",
            "us_per_step_split1",
            "us_per_call_split1",
            "bytes_touched_est",
            "notes",
        ]
    )
    total_us = 0.0
    total_calls = 0
    for r in rows:
        calls = int(r["calls_per_step"])
        us = float(r["us_per_step"])
        total_us += us
        total_calls += calls
        table.add_data(
            r["label"],
            r["kind"],
            r["origin"],
            calls,
            us,
            float(r["us_per_call"]),
            int(r["bytes_touched_est"]),
            r["notes"],
        )

    unattributed = next(
        (float(r["us_per_step"]) for r in rows if r["label"] == "unattributed"), 0.0
    )
    nat_total = sum(POOLS.values())

    metrics = {
        "ledger": table,
        "labels_total": len(rows),
        "dispatches_per_step_attributed": total_calls,
        "dispatches_per_step_measured": 406,
        "split1_us_per_step_total": round(total_us, 1),
        "nat_us_per_step_total": round(nat_total, 1),
        # Primary metric: how much of the decode step no named kernel explains.
        # The assignment asserted ~1186.1 us/step. The ledger closes to +0.3.
        "unattributed_us_per_step": unattributed,
        "unattributed_pct_of_busy": round(100.0 * unattributed / 7993.1, 4),
        "claimed_residue_us_per_step": 1186.1,
        "split1_to_nat_deflator_us_per_dispatch": 1.317,
        "nat_busy_us_per_step_measured": 7993.1,
        "nat_wall_us_per_step_measured": 8230.3,
        "command_buffers_per_step_nat": 45.0,
        **POOLS,
    }
    for name, us in POOLS.items():
        metrics[name.replace("_us_per_step", "_pct_of_nat")] = round(
            100.0 * us / nat_total, 1
        )

    run.log(metrics)
    run.summary.update({k: v for k, v in metrics.items() if k != "ledger"})

    art = wandb.Artifact("r94a-decode-dispatch-ledger", type="analysis")
    for path in (LEDGER, REPORT, WRITEUP):
        art.add_file(str(path), name=path.name)
    run.log_artifact(art)

    print(f"wandb run id: {run.id}")
    print(f"wandb run url: {run.url}")
    run.finish()


if __name__ == "__main__":
    main()
