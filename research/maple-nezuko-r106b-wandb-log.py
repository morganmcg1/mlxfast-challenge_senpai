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
T975 = {
    1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447,
    7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228, 11: 2.201, 12: 2.179,
    13: 2.160, 14: 2.145, 15: 2.131, 16: 2.120, 17: 2.110, 18: 2.101,
    19: 2.093, 20: 2.086,
}

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


def _num(row):
    """Decode seconds/token as float, or None for a row the harness did not score."""
    v = row.get("decode_s_per_token", "NA")
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def paired_stats(rows, cand_arm):
    """Amendment 2 block design -> pair each candidate run with the C run of its
    own block. Falls back to positional pairing for the older strictly
    alternating TSVs, which carry no `block` column."""
    if rows and "block" in rows[0]:
        ctrl_by_block, cand_by_block = {}, {}
        for r in rows:
            val = _num(r)
            if val is None:
                continue
            if r["arm"] == "C":
                ctrl_by_block[r["block"]] = val
            elif r["arm"] == cand_arm:
                cand_by_block[r["block"]] = val
        blocks = sorted(set(ctrl_by_block) & set(cand_by_block), key=int)
        ctrl = [ctrl_by_block[b] for b in blocks]
        cand = [cand_by_block[b] for b in blocks]
    else:
        ctrl = [v for v in (_num(r) for r in rows if r["arm"] == "C") if v is not None]
        cand = [v for v in (_num(r) for r in rows if r["arm"] == cand_arm)
                if v is not None]
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
        try:
            pre = float(r.get("prefill_s_per_token", "NA"))
        except (TypeError, ValueError):
            pre = None
        tbl.add_data(int(r["idx"]), r["arm"], ARM_NAMES.get(r["arm"], "?"),
                     _num(r), pre, r["passed"])
    return {("stageb/triage_" + name): tbl}


def main():
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    paired_path = pathlib.Path(sys.argv[1])
    rows = read_rows(paired_path)
    # Candidate arms carry outcome labels; arm P is the deliberately incorrect
    # attribution instrument of Amendment 2 section 5 and carries a *bound*.
    cands = [a for a in ("K", "H", "D") if any(r["arm"] == a for r in rows)]
    if not cands:
        raise SystemExit("paired TSV has no candidate arm among K/H/D")
    stats = {a: paired_stats(rows, a) for a in cands}
    if any(r["arm"] == "P" for r in rows):
        try:
            stats["P"] = paired_stats(rows, "P")
        except SystemExit:
            pass

    def label_for(arm, st):
        lo, hi = st["ci95_low_us"], st["ci95_high_us"]
        excludes_zero = not (lo <= 0.0 <= hi)
        # Arm P's incorrectness is preregistered and expected, so it must not be
        # allowed to stamp N-CORRECT on a candidate; correctness is judged on the
        # control runs and this arm's own runs only.
        correct = all(r["passed"] == "true" for r in rows
                      if r["arm"] in ("C", arm))
        if arm == "P":
            return "BOUND-ONLY (incorrect by design)", excludes_zero, correct
        if not correct:
            return "N-CORRECT", excludes_zero, correct
        if st["delta_us_per_step"] < 0.0 and excludes_zero:
            # V-ATTRIB vs V-RECOVER is decided by the zero-tolerance oracle, which
            # this script does not run; the report records which one applies.
            return "V-RECOVER-or-V-ATTRIB", excludes_zero, correct
        return "N-RECOVER", excludes_zero, correct

    labels = {a: label_for(a, st) for a, st in stats.items()}
    # The headline arm is the preregistered Stage B candidate PACKRED when present.
    cand = "K" if "K" in stats else cands[0]
    st = stats[cand]
    label, excludes_zero, all_correct = labels[cand]
    lo, hi = st["ci95_low_us"], st["ci95_high_us"]

    run = wandb.init(
        entity=ENTITY,
        project=PROJECT,
        job_type="r106b-stageb-paired",
        name=os.environ.get("WANDB_NAME", "maple-nezuko-r106b-stageb-paired"),
        notes=os.environ.get("WANDB_NOTES", (
            "R106-B Stage B. Candidate arm %s vs the shipped sliding "
            "decode-attention kernel, paired on ./benchmark.sh --local-submit. "
            "Preregistered in research/maple-nezuko-r106b-stageb-preregistration.md, "
            "research/maple-nezuko-r106b-stageb-amendment1.md and "
            "research/maple-nezuko-r106b-stageb-amendment2.md (design of record: "
            "control-anchored position-balanced blocks of 4). Stage 0's "
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
    # Every contrast in the campaign, so the null arms are on the record too
    # (Rule 79) and the P-arm bound is retrievable without re-reading the TSV.
    for arm, ast in stats.items():
        alab, aexc, acor = labels[arm]
        pref = "stageb/arm_%s/" % arm
        summary.update({(pref + k): v for k, v in ast.items()
                        if k != "paired_diffs_us"})
        summary[pref + "label"] = alab
        summary[pref + "ci95_excludes_zero"] = aexc
        summary[pref + "runs_correct"] = acor
        summary[pref + "meaning"] = ARM_NAMES.get(arm, "?")
    if "P" in stats:
        # -D_P is the upper bound on what any main-loop-reduction lever can win.
        summary["stageb/reduction_recoverable_bound_us_per_step"] = \
            -stats["P"]["delta_us_per_step"]
    run.summary.update(summary)

    tbl = wandb.Table(columns=["session", "idx", "block", "arm", "arm_meaning",
                               "decode_s_per_token", "prefill_s_per_token",
                               "passed", "wall_s"])
    for r in rows:
        dec = _num(r)
        try:
            pre = float(r.get("prefill_s_per_token", "NA"))
        except (TypeError, ValueError):
            pre = None
        tbl.add_data(r.get("session", ""), int(r["idx"]), r.get("block", ""),
                     r["arm"], ARM_NAMES.get(r["arm"], "?"),
                     dec, pre, r["passed"], r.get("wall_s", ""))
    payload = {"stageb/paired_runs": tbl}
    for p in sys.argv[2:]:
        payload.update(triage_table(read_rows(p), pathlib.Path(p).stem))
    run.log(payload)

    for arm in sorted(stats):
        ast = stats[arm]
        print("arm=%s label=%-28s n=%d dof=%d delta=%+8.3f us/step "
              "ci=[%+8.3f, %+8.3f] pct_cs=%+.4f"
              % (arm, labels[arm][0], ast["n_pairs"], ast["dof"],
                 ast["delta_us_per_step"], ast["ci95_low_us"],
                 ast["ci95_high_us"], ast["delta_pct_cs"]))
    print("headline arm=%s label=%s delta=%.3f us/step ci=[%.3f, %.3f] "
          "pct_cs=%+.4f run=%s"
          % (cand, label, st["delta_us_per_step"], lo, hi,
             st["delta_pct_cs"], run.id))
    print("W&B run url:", run.url)
    run.finish()


if __name__ == "__main__":
    main()
