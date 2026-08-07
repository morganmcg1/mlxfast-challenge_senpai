#!/usr/bin/env python3
"""Stage 2 driver for PR #300: build, run and publish the redundant-RMSNorm cost probe.

Usage (from repo root):
    python3 research/fern_rmsnorm_cost_wandb.py [reps]
"""
import json
import os
import platform
import subprocess
import sys
from pathlib import Path

import wandb

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "research" / "fern_redundant_rmsnorm_cost.swift"
BIN = Path("/tmp/fern_rmsnorm_cost")
LOGDIR = ROOT / "research" / "redundant-rmsnorm-logs"
LOG = LOGDIR / "stage2-cost.log"
JSONOUT = LOGDIR / "stage2-cost.json"

reps = sys.argv[1] if len(sys.argv) > 1 else "400"
LOGDIR.mkdir(parents=True, exist_ok=True)

subprocess.run(
    ["swiftc", "-O", str(SRC), "-o", str(BIN), "-framework", "Metal", "-framework", "Foundation"],
    check=True,
    cwd=ROOT,
)

proc = subprocess.run(
    [str(BIN), reps, str(JSONOUT)], capture_output=True, text=True, cwd=ROOT
)
output = proc.stdout + proc.stderr
LOG.write_text(output)
print(output)
proc.check_returncode()

data = json.loads(JSONOUT.read_text())

chip = subprocess.run(
    ["sysctl", "-n", "machdep.cpu.brand_string"], capture_output=True, text=True
).stdout.strip()

run = wandb.init(
    project="mlxfast-maple",
    entity="wandb-applied-ai-team",
    name="fern-pr300-stage2-redundant-rmsnorm-cost",
    job_type="microbenchmark",
    tags=["pr300", "maple-fern", "redundant-rmsnorm", "stage2"],
    config={
        "assignment_id": "maple-2026-08-07n-redundant-rmsnorm-tree",
        "revision_id": "r1",
        "pr": 300,
        "host_chip": chip,
        "host_os": platform.mac_ver()[0],
        "reps_per_buffer": data["reps_per_buffer"],
        "rounds": data["rounds"],
        "fast_math": False,
        "threadgroup_threads": 64,
        "axis_size": 2048,
        "decision_threshold_us_per_step": data["decision_threshold_us"],
    },
)

scalar = {k: v for k, v in data.items() if isinstance(v, (int, float))}
scalar["decision_pursue"] = 1.0 if data["decision"] == "PURSUE" else 0.0
run.log(scalar)
run.summary.update(scalar)
run.summary["decision"] = data["decision"]

art = wandb.Artifact("pr300-stage2-redundant-rmsnorm-cost", type="benchmark")
art.add_file(str(JSONOUT))
art.add_file(str(LOG))
run.log_artifact(art)

print(f"WANDB_RUN_ID={run.id}")
print(f"WANDB_RUN_URL={run.url}")
run.finish()
