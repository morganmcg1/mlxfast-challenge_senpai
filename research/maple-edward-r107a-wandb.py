#!/usr/bin/env python3
"""Research-only (PR #629, R107-A): publish the routed gate/up packing curve.

Reads the artefacts the stage-0 and stage-1 drivers already wrote and logs them
as one run in wandb-applied-ai-team/mlxfast-maple. Nothing is recomputed: every
timing number comes from the preregistered analyzer
(research/maple-frieren-r103a-analyze-multi.py), so the run can be audited
against the on-disk files.

Usage:
  python3 research/maple-edward-r107a-wandb.py STAGE1_DIR [STAGE0_DIR]
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import wandb

ENTITY = "wandb-applied-ai-team"
PROJECT = "mlxfast-maple"

# Graduation gate from the assignment: a non-default S must show a
# consistent-sign full-decode gain of at least 0.2% and a kernel-local gain of
# at least 0.5%.
GATE_DECODE_PCT = 0.20
GATE_KERNEL_PCT = 0.50
# Percent of candidate score bought per us/step of M4-equivalent decode time,
# and the M5<-M4 transfer factor for a structural change (doc R1).
CS_PCT_PER_US = 1.0 / 65.67
M5_FROM_M4 = 0.622

ARM_MECHANISM = {
    "base": "shipped default: R1 packed kernel, 2 simdgroups/threadgroup",
    "null1": "rule-79 identical-execution null (SG=1 parses to 0 -> default)",
    "sg2": "mechanism null: same body and geometry, distinct _sg2 pipeline",
    "sg4": "4 simdgroups/threadgroup (1024 threadgroups)",
    "sg8": "8 simdgroups/threadgroup (512 threadgroups)",
    "sg16": "16 simdgroups/threadgroup (256 threadgroups)",
}


def sh(cmd: list[str]) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True,
                              check=True).stdout.strip()
    except Exception:
        return ""


def kv_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if path.exists():
        for line in path.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, _, v = line.partition("=")
                if k.strip().isidentifier():
                    out[k.strip()] = v.strip()
    return out


def geometry_rows(stage0: Path) -> list[dict]:
    """One R107GEOM receipt per arm, as emitted by the geom-instrumented build."""
    rows = []
    for err in sorted(stage0.glob("geom-*.err")):
        line = next((ln for ln in err.read_text(errors="replace").splitlines()
                     if ln.startswith("R107GEOM ")), None)
        if line is None:
            continue
        row = {"arm": err.stem.replace("geom-", "")}
        row.update(dict(kv.split("=", 1) for kv in line.split()[1:] if "=" in kv))
        metal = err.with_suffix(".metal")
        if metal.exists():
            row["metal_src_sha"] = sh(["shasum", "-a", "256", str(metal)]).split()[0]
            stride = [ln for ln in metal.read_text().splitlines()
                      if "logical_row = tile" in ln]
            row["row_stride_line"] = stride[0].strip() if stride else ""
        rows.append(row)
    return rows


def parity_rows(stage0: Path) -> list[dict]:
    rows = []
    for log in sorted(stage0.glob("*.log")):
        if log.stem.startswith("geom-"):
            continue
        m = re.search(r"teacher-forced greedy tokens: (\d+) divergences",
                      log.read_text(errors="replace"))
        if m is None:
            continue
        tok = log.with_suffix(".tokens")
        rows.append({
            "probe": log.stem,
            "divergences": int(m.group(1)),
            "token_cksum": sh(["cksum", str(tok)]).split()[0] if tok.exists() else "",
            "expectation": "must FAIL" if log.stem.startswith("fault-") else "must pass",
        })
    return rows


def main() -> None:
    s1 = Path(sys.argv[1])
    s0 = Path(sys.argv[2]) if len(sys.argv) > 2 else None
    rep = json.loads((s1 / "analysis-multi.json").read_text())
    prov = kv_file(s1 / "provenance.txt")

    med = rep["stats"]["median"]
    step_us = med["levels"]["base"]

    config = {
        "assignment_pr": 629,
        "assignment_id": "maple-r107-a-routed-gateup-packing",
        "branch": "maple-edward/r107-routed-gateup-packing",
        "assigned_head_sha": "526881c4f6e2b879c1dfef67212b852cf5c9b7ed",
        "code_sha": sh(["git", "rev-parse", "HEAD"]),
        "host": sh(["sysctl", "-n", "machdep.cpu.brand_string"]),
        "host_mem_bytes": sh(["sysctl", "-n", "hw.memsize"]),
        "site": "routed MoE gate/up packed top-8 R1 NVFP4 QMV "
                "(laguna_routed_nvfp4_swiglu_qmv_packed_top8keys_r1_bf16_v2)",
        "control": "DARKBLOOM_ROUTED_GATEUP_SG in {2,4,8,16,32}",
        "design": "rotated palindrome, 6 arms x 12 slots per repetition",
        "reps": prov.get("reps"),
        "warmup_reps_discarded": rep.get("warmup_reps"),
        "steps_per_slot": prov.get("steps"),
        "decision_statistic": "median of steps 1..N-1 (cycle-blocked contrast)",
        "official_analog_statistic": "mean_first128",
        "gate_decode_pct": GATE_DECODE_PCT,
        "gate_kernel_pct": GATE_KERNEL_PCT,
        "digest_before": prov.get("digest_before"),
        "digest_after": prov.get("digest_after"),
        "grid_threads": 131072,
        "total_simdgroups": 4096,
        "logical_rows": 512,
    }

    run = wandb.init(entity=ENTITY, project=PROJECT,
                     name="maple-edward-r107a-routed-gateup-packing",
                     job_type="kernel-geometry-sweep", config=config,
                     tags=["r107a", "moe", "routed-gate-up", "threadgroup-packing",
                           "m4-directional"])

    summary: dict = {
        "precision/worst_half_width_us": rep["precision"]["worst_half_width_m4"],
        "precision/pass": rep["precision"]["pass"],
        "n2_fires_drift": rep["n2_fires"],
        "n5_fires_all_indistinguishable": rep["n5_fires"],
        "base_step_us": step_us,
    }
    for arm, lvl in med["levels"].items():
        summary[f"level/{arm}_us_per_step"] = lvl

    contrasts = wandb.Table(columns=[
        "leg", "estimator", "k", "mean_us", "half_width", "lo", "hi",
        "pos", "neg", "pct_of_step", "excl_bound_us", "clears_0.2pct_gate"])
    for est, block in (("cycle-blocked", med.get("cycle_contrasts") or {}),
                       ("per-repetition", med.get("contrasts") or {})):
        for leg, c in block.items():
            pct = 100.0 * c["mean"] / step_us
            contrasts.add_data(leg, est, c["k"], c["mean"], c["half_width"],
                               c["lo"], c["hi"], c["pos"], c["neg"], pct,
                               c.get("excludes_above_m4"),
                               bool(pct <= -GATE_DECODE_PCT and c["hi"] < 0))
    run.log({"contrasts": contrasts})

    for leg, c in (med.get("cycle_contrasts") or {}).items():
        key = leg.replace("->", "_to_")
        summary[f"cycle/{key}/mean_us"] = c["mean"]
        summary[f"cycle/{key}/lo"] = c["lo"]
        summary[f"cycle/{key}/hi"] = c["hi"]
        summary[f"cycle/{key}/pct_of_step"] = 100.0 * c["mean"] / step_us
        summary[f"cycle/{key}/cs_pct_m4"] = c["mean"] * CS_PCT_PER_US
        summary[f"cycle/{key}/m5_projected_us"] = c["mean"] * M5_FROM_M4

    robust = wandb.Table(columns=["statistic", "leg", "mean_us", "lo", "hi"])
    for stat, block in rep["stats"].items():
        for leg, c in (block.get("cycle_contrasts") or {}).items():
            robust.add_data(stat, leg, c["mean"], c["lo"], c["hi"])
    run.log({"robustness_across_statistics": robust})

    nulls = wandb.Table(columns=["cell", "arm", "separation", "k", "mean_us",
                                 "lo", "hi", "excludes_zero"])
    for key, n in (med.get("nulls") or {}).items():
        nulls.add_data(key, n["arm"], n["separation"], n["k"], n["mean"],
                       n["lo"], n["hi"], n["lo"] * n["hi"] > 0)
    run.log({"rule79_nulls": nulls})

    arms = wandb.Table(columns=["arm", "mechanism", "us_per_step"])
    for arm, lvl in med["levels"].items():
        arms.add_data(arm, ARM_MECHANISM.get(arm, ""), lvl)
    run.log({"arms": arms})

    if s0 is not None:
        geo = geometry_rows(s0)
        if geo:
            cols = sorted({k for r in geo for k in r})
            t = wandb.Table(columns=cols)
            for r in geo:
                t.add_data(*[r.get(c, "") for c in cols])
            run.log({"stage0/geometry_receipts": t})
        par = parity_rows(s0)
        if par:
            t = wandb.Table(columns=["probe", "divergences", "token_cksum",
                                     "expectation"])
            for r in par:
                t.add_data(r["probe"], r["divergences"], r["token_cksum"],
                           r["expectation"])
            run.log({"stage0/parity_and_fault_control": t})
            summary["stage0/fault_control_failed_as_required"] = all(
                r["divergences"] > 0 for r in par if r["probe"].startswith("fault-"))
            summary["stage0/parity_divergences_total"] = sum(
                r["divergences"] for r in par if not r["probe"].startswith("fault-"))

    cks = s1 / "tokens.cksum"
    if cks.exists():
        summary["stage1/distinct_token_checksums"] = len(
            {ln.split()[0] for ln in cks.read_text().split("\n") if ln.strip()})

    run.summary.update(summary)
    print(run.url)
    run.finish()


if __name__ == "__main__":
    main()
