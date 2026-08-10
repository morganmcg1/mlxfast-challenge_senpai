#!/usr/bin/env python3
"""Log the R106-C decode serialisation ledger to W&B."""
import json
import os
import sys

import wandb

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
LEDGER = os.path.join(REPO, "research", "artifacts", "fern-r106c", "dag_ledger.json")

BARRIER_US = 1.3003
BARRIER_SE = 0.0597
DECODE_PCT_PER_US = 0.015228

with open(LEDGER) as f:
    led = json.load(f)

run = wandb.init(
    project="mlxfast-maple",
    entity="wandb-applied-ai-team",
    name="r106c-decode-serialisation-ledger",
    job_type="analysis",
    tags=["r106-c", "maple-fern", "pr617", "dag", "barriers", "N-CRITICAL"],
    config={
        "assignment_id": "maple-r106-c-decode-serialisation-ledger",
        "revision_id": "r106-c-rev1",
        "pr": 617,
        "base_sha": "0954002c16014a03091e1856cdf356fb0e6a3e38",
        "host": "Apple M4 Pro 48GiB (applegpu_g16s gen=16)",
        "instrument": "research/r106c/scripts/trace_dag.patch",
        "barrier_us_m4": BARRIER_US,
        "barrier_us_se": BARRIER_SE,
        "decode_pct_per_us": DECODE_PCT_PER_US,
        "stage3_gate_us_per_step": 33.0,
        "trace_correctness": "expected_token==actual_token==902, logit_delta=0",
    },
)

summary = dict(led)
summary.pop("kernels", None)
summary.pop("level_size_histogram", None)
summary.update(
    {
        "serial_chain_fraction": led["min_groups_ptr_with_anti"]
        / led["dispatches_per_step"],
        "headroom_us_plus_2sigma": led["headroom_groups"]
        * (BARRIER_US + 2 * BARRIER_SE),
        "gate_shortfall_factor": 33.0 / led["headroom_us_per_step"],
        "levels_width1": 207,
        "levels_width2": 42,
        "levels_width3": 39,
        "verdict": "N-CRITICAL (H1 dead: encoder already MTL::DispatchTypeConcurrent)",
        "stage3_built": False,
        "device_cpp_in_editable_paths": False,
    }
)
run.summary.update(summary)

art = wandb.Artifact("r106c-decode-serialisation-ledger", type="analysis")
art.add_file(LEDGER)
art.add_file(
    os.path.join(REPO, "research", "artifacts", "fern-r106c", "decode_step_dispatches.tsv")
)
art.add_file(
    os.path.join(REPO, "research", "maple-fern-r106c-decode-serialisation-ledger.md")
)
art.add_file(os.path.join(HERE, "dag_ledger.py"))
art.add_file(os.path.join(HERE, "trace_dag.patch"))
run.log_artifact(art)

print(run.url)
run.finish()
