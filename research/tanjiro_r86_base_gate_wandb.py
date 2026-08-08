#!/usr/bin/env python3
"""Log the R86-A rev2 base-adoption gate to W&B.

Reads the matched ABBA pair written by `research/tanjiro-r86-base-gate.sh`
(pre-adoption base f64456dd = arm "old" vs adopted base 7687c2e4/HEAD = arm
"new") plus the static audit verdicts, so the W&B run and
`research/tanjiro-r86-base-gate-result.md` cannot drift apart.

  python3 research/tanjiro_r86_base_gate_wandb.py research/r86-gate-results
"""
import argparse
import glob
import json
import os
import statistics as st
import sys

import wandb

ENTITY = "wandb-applied-ai-team"
PROJECT = "mlxfast-maple"

OLD_SHA = "f64456dd2dc503af080dca65bddfb922164c7bc5"
NEW_SHA = "7687c2e44e6975c181444ca8d3d151ee30480a72"
FRONTIER_SHA = "c5b0a13"

# Pre-registered 90% intervals, committed before any measurement
# (research/tanjiro-r86-base-gate-prereg.md).
PREREG = {
    "m4_decode_us_per_step": (200.0, 30.0, 450.0),
    "m4_prefill_us_per_token": (5.0, -55.0, 65.0),
    "m5_decode_us_per_step": (-80.0, -162.0, -20.0),
    "m5_prefill_us_per_token": (-12.0, -25.0, -2.0),
}
T_CRIT = {2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447}


def load(results_dir):
    arms = {"old": [], "new": []}
    for path in sorted(glob.glob(os.path.join(results_dir, "*.json"))):
        arm = os.path.basename(path).split("-")[0]
        if arm not in arms:
            continue
        m = json.load(open(path))["metrics"]
        arms[arm].append(
            {
                "file": os.path.basename(path),
                "arm": arm,
                "decode_us": m["decode_seconds_per_token"] * 1e6,
                "prefill_us": m["prefill_seconds_per_token"] * 1e6,
                "correct": bool(m["passed_correctness"]),
                "steps": int(m["checked_steps"]),
                "golden": m["golden_hash"],
                "harness": m["harness_hash"],
                "peak_ram_gb": m.get("peak_ram_gb"),
            }
        )
    return arms


def interval(old, new):
    na, nb = len(old), len(new)
    delta = st.mean(old) - st.mean(new)
    if na < 2 or nb < 2:
        return delta, None, None
    dof = na + nb - 2
    pooled = (
        ((na - 1) * st.variance(old) + (nb - 1) * st.variance(new)) / dof
    ) ** 0.5
    half = T_CRIT.get(dof, 2.0) * pooled * (1 / na + 1 / nb) ** 0.5
    return delta, pooled, half


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("results_dir")
    ap.add_argument("--code-identity-pass", type=int, default=1)
    ap.add_argument("--equivalence-steps", type=int, default=-1)
    ap.add_argument("--equivalence-exit", type=int, default=-1)
    args = ap.parse_args()

    arms = load(args.results_dir)
    rows = arms["old"] + arms["new"]
    if not rows:
        print("no result JSONs found", file=sys.stderr)
        return 1

    goldens = sorted({r["golden"] for r in rows})
    all_correct = all(r["correct"] for r in rows)

    summary = {
        "assignment_id": "maple-r86-a-base-decode-regression",
        "revision_id": "r86-a-rev2",
        "pr_number": 460,
        "host": "apple-m4-pro-20core",
        "gpu_generation": 16,
        "nax_reachable": False,
        "old_base_sha": OLD_SHA,
        "new_base_sha": NEW_SHA,
        "frontier_sha": FRONTIER_SHA,
        "golden_drift_override": os.environ.get(
            "MLXFAST_LOCAL_ALLOW_GOLDEN_DRIFT", "<unset>"
        ),
        "n_old": len(arms["old"]),
        "n_new": len(arms["new"]),
        "all_arms_passed_correctness": all_correct,
        "distinct_golden_hashes": len(goldens),
        "golden_hash": goldens[0] if len(goldens) == 1 else ",".join(goldens),
        "checked_steps": sorted({r["steps"] for r in rows}),
        "code_identity_audit_pass": bool(args.code_identity_pass),
        "equivalence_exact_steps": args.equivalence_steps,
        "equivalence_exit": args.equivalence_exit,
    }

    for key, label in (("decode_us", "decode_us_per_step"),
                       ("prefill_us", "prefill_us_per_token")):
        old = [r[key] for r in arms["old"]]
        new = [r[key] for r in arms["new"]]
        delta, pooled, half = interval(old, new)
        summary[f"old_{label}_mean"] = st.mean(old)
        summary[f"new_{label}_mean"] = st.mean(new)
        summary[f"delta_{label}"] = delta
        if half is not None:
            summary[f"pooled_sd_{label}"] = pooled
            summary[f"resolution_{label}"] = half
            summary[f"ci_lo_{label}"] = delta - half
            summary[f"ci_hi_{label}"] = delta + half
            summary[f"significant_{label}"] = bool(
                delta - half > 0 or delta + half < 0
            )
        point, lo, hi = PREREG[f"m4_{label}"]
        summary[f"prereg_point_{label}"] = point
        summary[f"prereg_lo_{label}"] = lo
        summary[f"prereg_hi_{label}"] = hi
        summary[f"prereg_hit_{label}"] = bool(lo <= delta <= hi)

    run = wandb.init(
        entity=ENTITY,
        project=PROJECT,
        job_type="base-adoption-gate",
        name="r86-a-rev2-base-gate",
        config={
            "hypothesis": "adopted base 7687c2e4 is correct, buildable and "
            "materially faster in decode than f64456dd",
            "delta_convention": "old_minus_new_positive_means_new_faster",
            "prereg": PREREG,
            "reps_per_arm": len(arms["new"]),
            "design": "ABBA matched pair, 8 adopted editable paths flipped",
        },
    )

    table = wandb.Table(
        columns=["file", "arm", "decode_us_per_step", "prefill_us_per_token",
                 "correct", "steps", "golden12", "peak_ram_gb"]
    )
    for r in sorted(rows, key=lambda r: r["file"]):
        table.add_data(r["file"], r["arm"], r["decode_us"], r["prefill_us"],
                       r["correct"], r["steps"], r["golden"][:12],
                       r["peak_ram_gb"])
    run.log({"arms": table})
    run.summary.update(summary)

    for k in sorted(summary):
        print(f"{k} = {summary[k]}")
    print(f"WANDB_RUN_ID={run.id}")
    print(f"WANDB_URL={run.url}")
    run.finish()
    return 0


if __name__ == "__main__":
    sys.exit(main())
