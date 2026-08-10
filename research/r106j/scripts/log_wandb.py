#!/usr/bin/env python3
"""R106-J: log the integration-tree round to W&B.

Publishes one run carrying the Stage 0 gates, every completed paired ABBA
sweep under research/artifacts/maple-fern-r106j/abba*/runs.tsv, the Rule 75
artefact table, and the nax-wall conservative restatement of each contrast.
"""
import glob
import json
import math
import os
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
ART = os.path.join(ROOT, "research", "artifacts", "maple-fern-r106j")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analyze_abba import analyse, read_rows  # noqa: E402

RUN_COLUMNS = [
    "sweep", "idx", "arm", "started_utc", "wall_s", "rc",
    "decode_s_per_token", "prefill_s_per_token",
    "passed", "max_abs_diff", "golden_hash", "worker_sha256",
]


def status_map(label):
    path = os.path.join(ART, f"{label}.status")
    out = {}
    if not os.path.exists(path):
        return out
    for line in open(path):
        if "=" in line:
            k, _, v = line.strip().partition("=")
            out[f"{label}.{k}"] = v
    return out


def score_json(label):
    path = os.path.join(ART, f"{label}.score.json")
    if not os.path.exists(path):
        return {}
    flat = {}

    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if isinstance(v, (dict, list)):
                    walk(v)
                else:
                    flat.setdefault(k, v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(json.load(open(path)))
    return {f"{label}.{k}": v for k, v in flat.items()}


def sweeps():
    found = []
    for tsv in sorted(glob.glob(os.path.join(ART, "abba*", "runs.tsv"))):
        tag = os.path.basename(os.path.dirname(tsv))
        rows = read_rows(tsv)
        if len(rows) < 4:
            continue
        found.append((tag, rows, analyse(rows)))
    return found


def summarise(tag, res, summary):
    p = f"{tag}.{res['control']}_vs_{res['candidate']}"
    summary[f"{p}.usable_runs"] = res["n_runs"]
    summary[f"{p}.blocks"] = res["n_blocks"]
    summary[f"{p}.correctness_failures"] = res["failures"]
    summary[f"{p}.distinct_golden_hashes"] = len(res["golden"])
    for k in ("d_ln_decode", "d_ln_prefill", "d_ln_score",
              "d_ln_score_decode_only"):
        est = res.get(k)
        if not est:
            continue
        summary[f"{p}.{k}_pct"] = est["mean"]
        if est.get("sem") is not None:
            summary[f"{p}.{k}_sem_pct"] = est["sem"]
            summary[f"{p}.{k}_ci_lo_pct"] = est["lo"]
            summary[f"{p}.{k}_ci_hi_pct"] = est["hi"]
    for (arm, metric), st in res["within"].items():
        summary[f"{p}.within.{arm}.{metric}.mean"] = st["mean"]
        summary[f"{p}.within.{arm}.{metric}.cv_pct"] = st["cv"]
        summary[f"{p}.within.{arm}.{metric}.n"] = st["n"]


def main():
    import wandb

    found = sweeps()
    if not found:
        raise SystemExit("no completed ABBA sweep found under " + ART)

    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True
    ).stdout.strip()

    config = {
        "assignment_id": "maple-r106-i-prefill-traversal-byte-census",
        "revision_id": "r106-i-rev2",
        "round": "R106-J",
        "pr_number": 625,
        "student": "maple-fern",
        "host": "Apple M4 Pro / 48 GiB / applegpu_g16s (GPU gen 16, no _nax)",
        "head_sha": head,
        "T0_sha": "446fe9875d1f95b1216628b5809a99da844e5c79",
        "T1_sha": "4b0e051bf3cd9777bd6d2be64e172c490705f9a5",
        "packing_patch": "research/tanjiro_packing_default_flip.patch",
        "sweeps": [tag for tag, _, _ in found],
        "design": "ABBA paired, block = 4 runs (A B B A / B A A B), arm = "
        "partial checkout of Sources/MLXFastModel + Sources/MLXFastTransform "
        "on one fixed Vendor tree and one fixed mlx.metallib",
        "estimator": "d(ln score) = -0.75*d(ln decode) - 0.25*d(ln prefill), "
        "block-contrast mean, dof = nblocks - 1",
        "conservative_estimator": "d(ln score | prefill neutral) = "
        "-0.75*d(ln decode); prefill is nax-divergent and unreachable on M4",
        "decision_margin_pct_of_cs": 0.40,
        "decode_pct_cs_per_us_step": 0.015228,
        "prefill_pct_score_per_ms": 0.3781,
    }

    summary = {
        "stage0.T0_equivalence_exit": 1,
        "stage0.T1_equivalence_exit": 1,
        "stage0.equivalence_reports_identical": True,
        "stage1.N_BUILD_refuted": True,
    }
    for tag, _, res in found:
        summarise(tag, res, summary)
    for label in ("T0", "T1", "T0P", "T1P"):
        summary.update(status_map(label))
        summary.update(score_json(label))

    run = wandb.init(
        project="mlxfast-maple",
        entity="wandb-applied-ai-team",
        name="r106j-integration-tree",
        job_type="integration",
        config=config,
        tags=["R106-J", "integration-tree", "ABBA", "m4pro", "nax-wall"],
    )
    tbl = wandb.Table(columns=RUN_COLUMNS)
    for tag, rows, _ in found:
        for r in rows:
            tbl.add_data(
                tag, int(r["idx"]), r["arm"], r["started_utc"],
                int(r["wall_s"]), int(r["rc"]),
                float(r["decode_s_per_token"]), float(r["prefill_s_per_token"]),
                r["passed"], r["max_abs_diff"], r["golden_hash"],
                r["worker_sha256"],
            )
    run.log({"abba/runs": tbl})
    for k, v in summary.items():
        if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
            continue
        run.summary[k] = v
    print(f"WANDB_RUN_ID={run.id}")
    print(f"WANDB_RUN_URL={run.url}")
    run.finish()


if __name__ == "__main__":
    main()
