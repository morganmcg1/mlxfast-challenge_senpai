#!/usr/bin/env python3
"""Research-only (PR #571, R103-A): publish the rung-1/rung-2 record to W&B.

Reads the artefacts the drivers already wrote -- analysis.json, optionally
census.json, the provenance files and the token-parity checksum list -- and
logs them as one run in wandb-applied-ai-team/mlxfast-maple. Nothing is
recomputed here; if a number is in W&B it came from the preregistered analyzer,
so the run can be audited against the on-disk artefacts.

Usage:
  python3 research/maple-frieren-r103a-wandb.py RUNG1_DIR [RUNG2_DIR]
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import wandb

PROJECT = "mlxfast-maple"
ENTITY = "wandb-applied-ai-team"

# The M5 quantity this experiment exists to reproduce, derived in doc 1.1 from
# the two official receipts: reported decode = seed_prefill/128 + steady_step,
# so the steady-step delta is larger than the +19.405 us/step headline.
M5_TARGET_US = 20.149
M5_TARGET_PCT = 0.4865
M5_HEADLINE_US = 19.405


def sh(cmd: list[str]) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True,
                              check=True).stdout.strip()
    except Exception:
        return ""


def kv_file(path: Path) -> dict[str, str]:
    out = {}
    if path.exists():
        for line in path.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, _, v = line.partition("=")
                if k.strip().isidentifier():
                    out[k.strip()] = v.strip()
    return out


def flat_paired(prefix: str, p: dict) -> dict:
    keep = ("k", "mean", "sd", "half_width", "lo", "hi", "pos", "neg")
    return {f"{prefix}/{k}": p[k] for k in keep if k in p}


def main() -> None:
    r1 = Path(sys.argv[1])
    r2 = Path(sys.argv[2]) if len(sys.argv) > 2 else None
    a = json.loads((r1 / "analysis.json").read_text())

    prov = kv_file(r1 / "provenance.txt")
    prov0 = kv_file(Path("/tmp/maple-r103a/rung0-provenance.txt"))

    cks = r1 / "tokens.cksum"
    n_distinct = len({ln.split()[0] for ln in cks.read_text().split("\n") if ln.strip()}) \
        if cks.exists() else -1

    config = {
        "assignment_id": "maple-r103-a-missing-microseconds-localize",
        "revision_id": "r103-a-rev1",
        "pr": 571,
        "branch": "maple-frieren/r103-missing-microseconds-localize",
        "base_sha": "0f6862d099252d40a807df30abfbbd7c9cd596ae",
        "old_sha": "30f752df890de58d9d98382505c95f2008591101",
        "code_sha": sh(["git", "rev-parse", "HEAD"]),
        "host": sh(["sysctl", "-n", "machdep.cpu.brand_string"]),
        "host_mem_bytes": sh(["sysctl", "-n", "hw.memsize"]),
        "design": "4-slot position-matched ABBA (oldA old new oldB), "
                  "order reversed on odd reps",
        "warmup_reps_discarded": a["warmup_reps"],
        "pairs_analysed": len(a["analysed_reps"]),
        "position_multiset": a["position_multiset"],
        "decision_statistic": "median of steps 1..N-1",
        "m5_target_us_per_step": M5_TARGET_US,
        "m5_target_pct": M5_TARGET_PCT,
        "m5_headline_us_per_step": M5_HEADLINE_US,
        "digest_head": prov0.get("digest_head"),
        "digest_at_old": prov0.get("digest_at_old"),
        "digest_after_restore": prov0.get("digest_after_restore"),
        "token_checksums_distinct": n_distinct,
        "rung2_run": r2 is not None,
    }

    run = wandb.init(entity=ENTITY, project=PROJECT, config=config,
                     job_type="timing-census",
                     name="r103a-abba-m4-rung1",
                     tags=["r103", "r103-a", "maple-frieren", "pr571",
                           "measurement-only", "m4-pro"],
                     notes="R103-A rung 1: paired ABBA reproduction attempt of "
                           "the OLD->NEW decode regression on M4 Pro, with a "
                           "byte-identical-code null arm.")

    summary: dict = {
        "verdict_code": a["verdict_code"],
        "verdict_text": a["verdict_text"],
    }
    for stat in ("median", "trimmed", "mean", "mean_first128"):
        if stat not in a:
            continue
        b = a[stat]
        summary.update(flat_paired(f"{stat}/real", b["real"]))
        summary.update(flat_paired(f"{stat}/null", b["null"]))
        summary[f"{stat}/old_level_us"] = b["old_level_us"]
        summary[f"{stat}/real_relative_pct"] = b["real_relative_pct"]
        summary[f"{stat}/real_over_m5_target"] = \
            b["real"]["mean"] / M5_TARGET_US
    for key, p in a.get("diagnostics", {}).items():
        summary.update(flat_paired(f"diag/{key}", p))

    # Per-repetition paired differences, so the run carries the raw evidence
    # for the interval rather than only its endpoints.
    for row in a["median"]["real"]["pairs"]:
        rep = row["rep"]
        null_rows = {q["rep"]: q for q in a["median"]["null"]["pairs"]}
        wandb.log({
            "rep": rep,
            "pair/real_new_minus_old_us": row["diff_us"],
            "pair/new_us": row["new"],
            "pair/old_us": row["old"],
            "pair/null_oldB_minus_oldA_us":
                null_rows.get(rep, {}).get("diff_us"),
        }, step=rep)

    if r2 is not None and (r2 / "census.json").exists():
        c = json.loads((r2 / "census.json").read_text())
        summary["census/n_kernels"] = c["n_kernels"]
        for k, v in c["reconciliation"].items():
            summary[f"census/{k}"] = v
        for key, blk in c["totals"].items():
            summary.update(flat_paired(f"census/total/{key}/real", blk["real"]))
            summary.update(flat_paired(f"census/total/{key}/null", blk["null"]))
        tbl = wandb.Table(columns=["kernel", "old_us_step", "real_mean_us",
                                   "real_lo", "real_hi", "null_mean_us",
                                   "null_half_width", "clears_null"])
        for d in c["per_kernel"]:
            tbl.add_data(d["kernel"], d["old_us_step"], d["real"]["mean"],
                         d["real"]["lo"], d["real"]["hi"], d["null"]["mean"],
                         d["null"].get("half_width"), d["clears_null"])
        run.log({"census/per_kernel": tbl})

    run.summary.update(summary)

    art = wandb.Artifact("r103a-evidence", type="measurement")
    for p in [r1 / "analysis.json", r1 / "provenance.txt", r1 / "index.tsv",
              r1 / "tokens.cksum", Path("/tmp/maple-r103a/rung0-provenance.txt")]:
        if p.exists():
            art.add_file(str(p))
    if r2 is not None:
        for p in [r2 / "census.json", r2 / "rung2-build.txt",
                  r2 / "provenance.txt"]:
            if p.exists():
                art.add_file(str(p))
    run.log_artifact(art)

    print(f"W&B run: {run.url}  id={run.id}")
    run.finish()


if __name__ == "__main__":
    main()
