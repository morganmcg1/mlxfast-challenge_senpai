#!/usr/bin/env python3
"""Log the R106-B Stage B verdict to W&B.

Publishes one run in wandb-applied-ai-team/mlxfast-maple carrying

  * Stage 0's N-RESIDUAL numbers (revert-residual forensics),
  * the Stage B *evidence* paired test on ./benchmark.sh --local-submit,
  * the two Stage B *triage* tables (Rule 86: --local-iterate is never
    evidence, so they are logged as tables and never as the primary metric).

No official receipt is spent; every number comes from the local M4 Pro host.

Usage:
  research/maple-nezuko-r106b-wandb-log.py <paired.tsv> [triage.tsv ...]
Env:
  WANDB_NAME / WANDB_NOTES optional overrides.
"""

import csv
import math
import os
import pathlib
import statistics
import sys

import wandb

ENTITY = "wandb-applied-ai-team"
PROJECT = "mlxfast-maple"

# Campaign constants (R106 ledger).
US_PER_PCT_CS = 65.67          # 1 % of cs, in decode microseconds per step
PCT_CS_PER_US = 0.015228       # % of cs bought by 1 us/step of decode
KERNEL_US_PER_STEP = 670.2     # sliding decode attention: 22.34 us/call x 30

# Stage 0 N-RESIDUAL numbers, carried so both labels live in one run.
STAGE0 = {
    "stage0/residual_us_per_step": 19.405,
    "stage0/pooled_sd_us": 11.920,
    "stage0/dof": 10,
    "stage0/ci95_low_us": -18.156,
    "stage0/ci95_high_us": 56.966,
    "stage0/z": 1.151,
    "stage0/T_us_per_step": 20.149,
    "stage0/T_ci95_low_us": -17.877,
    "stage0/T_ci95_high_us": 58.175,
    "stage0/label": "N-RESIDUAL",
}

# Student's t 97.5 % quantiles for small dof.
T975 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447}

ARM_NAMES = {
    "C": "control (shipped laguna_sliding_fused_attn_ring_v1)",
    "K": "PACKRED (packed float2/float4 cross-lane butterfly)",
    "H": "H4 (4 query heads per threadgroup)",
    "D": "H4/d2 (4 heads per threadgroup, pipeline depth 2)",
    "P": "NOREDUCE probe (row-loop reduction deleted; WRONG output by design)",
}


def read_rows(path):
    with open(path) as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def paired_stats(rows, cand_arm):
    """Strictly alternating campaign -> pair the j-th C with the j-th candidate."""
    ctrl = [float(r["decode_s_per_token"]) for r in rows if r["arm"] == "C"]
    cand = [float(r["decode_s_per_token"]) for r in rows if r["arm"] == cand_arm]
    n = min(len(ctrl), len(cand))
    if n == 0:
        raise SystemExit("no paired rows for arm %s" % cand_arm)
    d_us = [(cand[j] - ctrl[j]) * 1e6 for j in range(n)]
    mean_d = statistics.fmean(d_us)
    if n >= 2:
        sd_d = statistics.stdev(d_us)
        half = T975.get(n - 1, 2.0) * sd_d / math.sqrt(n)
    else:
        sd_d = float("nan")
        half = float("nan")
    return {
        "n_pairs": n,
        "dof": n - 1,
        "t975": T975.get(n - 1, float("nan")),
        "control_mean_decode_s": statistics.fmean(ctrl[:n]),
        "candidate_mean_decode_s": statistics.fmean(cand[:n]),
        "delta_us_per_step": mean_d,
        "sd_paired_diff_us": sd_d,
        "ci95_half_width_us": half,
        "ci95_low_us": mean_d - half,
        "ci95_high_us": mean_d + half,
        "delta_pct_cs": mean_d * PCT_CS_PER_US,
        "delta_pct_of_kernel": 100.0 * mean_d / KERNEL_US_PER_STEP,
        "paired_diffs_us": d_us,
    }


def triage_table(rows, name):
    tbl = wandb.Table(columns=["idx", "arm", "arm_meaning", "decode_s_per_token",
                               "prefill_s_per_token", "passed"])
    for r in rows:
        tbl.add_data(int(r["idx"]), r["arm"], ARM_NAMES.get(r["arm"], "?"),
                     float(r["decode_s_per_token"]),
                     float(r["prefill_s_per_token"]), r["passed"])
    return {("stageb/triage_" + name): tbl}


def main():
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    paired_path = pathlib.Path(sys.argv[1])
    rows = read_rows(paired_path)
    cand = next((a for a in ("K", "D", "H") if any(r["arm"] == a for r in rows)), None)
    if cand is None:
        raise SystemExit("paired TSV has no candidate arm among K/D/H")
    st = paired_stats(rows, cand)

    lo, hi = st["ci95_low_us"], st["ci95_high_us"]
    excludes_zero = not (lo <= 0.0 <= hi)
    all_correct = all(r["passed"] == "true" for r in rows)
    if not all_correct:
        label = "N-CORRECT"
    elif st["delta_us_per_step"] < 0.0 and excludes_zero:
        # V-ATTRIB vs V-RECOVER is decided by the zero-tolerance oracle, which
        # this script does not run; the report records which one applies.
        label = "V-RECOVER-or-V-ATTRIB"
    else:
        label = "N-RECOVER"

    run = wandb.init(
        entity=ENTITY,
        project=PROJECT,
        job_type="r106b-stageb-paired",
        name=os.environ.get("WANDB_NAME", "maple-nezuko-r106b-stageb-paired"),
        notes=os.environ.get("WANDB_NOTES", (
            "R106-B Stage B. Candidate arm %s vs the shipped sliding "
            "decode-attention kernel, paired on ./benchmark.sh --local-submit. "
            "Preregistered in research/maple-nezuko-r106b-stageb-preregistration.md "
            "and research/maple-nezuko-r106b-stageb-amendment1.md. Stage 0's "
            "N-RESIDUAL revert-residual result is carried in the summary. No "
            "official submission, no receipt spent." % cand)),
        tags=["r106-b", "stage-b", "paired", "no-receipt", "arm-" + cand],
        config={
            "host": "Apple M4 Pro, 20 GPU cores",
            "evidence_path": "./benchmark.sh --local-submit (1023 decode steps)",
            "candidate_arm": cand,
            "candidate_meaning": ARM_NAMES.get(cand, "?"),
            "us_per_pct_cs": US_PER_PCT_CS,
            "pct_cs_per_us": PCT_CS_PER_US,
            "kernel_us_per_step": KERNEL_US_PER_STEP,
            "threadgroups_per_call": 32,
            "threadgroup_threads": 1024,
            "dispatches_per_step": 30,
            "threadgroup_memory_bytes": 18432,
        },
    )

    summary = dict(STAGE0)
    summary.update({("stageb/" + k): v for k, v in st.items()
                    if k != "paired_diffs_us"})
    summary["stageb/label"] = label
    summary["stageb/ci95_excludes_zero"] = excludes_zero
    summary["stageb/all_runs_correct"] = all_correct
    run.summary.update(summary)

    tbl = wandb.Table(columns=["session", "idx", "arm", "arm_meaning",
                               "decode_s_per_token", "prefill_s_per_token",
                               "passed"])
    for r in rows:
        tbl.add_data(r.get("session", ""), int(r["idx"]), r["arm"],
                     ARM_NAMES.get(r["arm"], "?"),
                     float(r["decode_s_per_token"]),
                     float(r["prefill_s_per_token"]), r["passed"])
    payload = {"stageb/paired_runs": tbl}
    for p in sys.argv[2:]:
        payload.update(triage_table(read_rows(p), pathlib.Path(p).stem))
    run.log(payload)

    print("arm=%s label=%s delta=%.3f us/step ci=[%.3f, %.3f] pct_cs=%+.4f run=%s"
          % (cand, label, st["delta_us_per_step"], lo, hi,
             st["delta_pct_cs"], run.id))
    print("W&B run url:", run.url)
    run.finish()


if __name__ == "__main__":
    main()
