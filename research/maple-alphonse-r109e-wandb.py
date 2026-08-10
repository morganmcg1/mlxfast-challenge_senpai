#!/usr/bin/env python3
"""Publish the R109-E Stage 0 full-attention QK ceiling probe to W&B.

Usage: python research/maple-alphonse-r109e-wandb.py TSV [TSV...]

Estimators are imported from `maple-alphonse-r109e-analyze.py` so the run's
numbers cannot drift from the memo's numbers. Every per-run decode/prefill
sample is logged as a step so the ABBA sequence and any thermal drift are
inspectable in the UI.
"""

import importlib.util
import math
import os
import subprocess
import sys

import wandb

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEC = importlib.util.spec_from_file_location(
    "r109e_analyze", os.path.join(REPO, "research/maple-alphonse-r109e-analyze.py")
)
A = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(A)

ARM_ENV = {"C": "(unset)", "P": "bcast", "D": "dose1", "X": "dose10"}
# Baselines for the assignment's normalized-score formula.
NS_DECODE_REF = 0.013890  # s/token
NS_PREFILL_REF = 0.0003845  # s/token
STAGE0_GATE_PCS = 0.20
STAGE1_TARGET_PCS = 0.25


def main():
    paths = sys.argv[1:]
    rows = A.load(paths)
    head = subprocess.run(
        ["git", "-C", REPO, "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()

    arms = sorted({a for a, _, _, _ in rows})
    probes = [a for a in arms if a != "C"]
    ctrl = [d for a, d, _, _ in rows if a == "C"]
    cm, csd, cn = A.stats(ctrl)
    reg = A.regression(rows, probes) if len(rows) > len(probes) + 3 else {}
    host_price = 0.75 * 100.0 / cm
    prices = {
        "host_matched": host_price,
        "rule105_2_beta": A.K_BETA * A.M5_PRICE,
        "k_issue_upper": A.K_ISSUE_UPPER * A.M5_PRICE,
        "brief_unsourced": A.BRIEF_PRICE,
    }

    run = wandb.init(
        entity="wandb-applied-ai-team",
        project="mlxfast-maple",
        name="maple-alphonse-r109e-full-attn-qk-ceiling",
        job_type="stage0-ceiling-probe",
        tags=["maple-alphonse", "r109-E", "full_attention", "decode",
              "laguna_full_fused_attn_grow_v1", "simd_sum", "simdgroup_matrix",
              "ceiling-probe", "abba", "dose-response", "m4-directional"],
        notes=(
            "Stage 0 of R109-E. Instead of writing the simdgroup_matrix QK "
            "rewrite first, measure its ceiling: substitute the six QK "
            "`simd_sum` statements of laguna_full_fused_attn_grow_v1 with "
            "(P) simd_broadcast_first, deleting the ladder, and with (D/X) a "
            "bit-exact doubling butterfly repeated 1x/10x, adding a known "
            "number of issue slots. Geometry, inputNames and dispatch are "
            "byte-identical across arms. P upper-bounds any QK-reduction "
            "rewrite; D/X give a dose-response slope that prices an issue slot "
            "without relying on the correctness-failing P arm. Directional M4 "
            "Pro evidence only (Apple GPU gen 16, never selects _nax)."
        ),
        config={
            "assignment_id": "maple-r109-e-full-attn-qk-mma",
            "revision_id": "r109-e-rev1",
            "pr": 685,
            "branch": "maple-alphonse/r109-full-attn-qk-mma",
            "base_sha": "1a6761bf46c282fcabd0577b618f0c1206757e6c",
            "head_sha": head,
            "kernel": "laguna_full_fused_attn_grow_v1",
            "kernel_share_of_decode_pct": 2.69,
            "kernel_us_per_step_m4_ledger": 229.7,
            "grid": "((heads/2)*1024,1,1)",
            "threadgroup": "(1024,1,1)",
            "geometry_changed": False,
            "env_switch": "DARKBLOOM_FULL_ATTN_QK_PROBE",
            "arms": ARM_ENV,
            "arm_slots": A.SLOTS,
            "ladder_slots": A.LADDER_SLOTS,
            "order": "".join(a for a, _, _, _ in rows),
            "n_runs": len(rows),
            "block_len": A.BLOCK,
            "harness": "./benchmark.sh --local-iterate",
            "fan_prompt": 0,
            "host": "Apple M4 Pro, 20 GPU cores, 48 GiB, macOS 26.5.2",
            "apple_gpu_generation": 16,
            "nax_reachable": False,
            "price_pcs_per_us_step": prices,
            "stage0_gate_pcs": STAGE0_GATE_PCS,
            "stage1_target_pcs": STAGE1_TARGET_PCS,
        },
    )

    for i, (arm, dec, pre, passed) in enumerate(rows):
        ns = ((NS_DECODE_REF / (dec / 1e6)) ** 0.75) * (
            (NS_PREFILL_REF / (pre / 1e6)) ** 0.25
        )
        run.log({
            "run/index": i,
            "run/arm": arm,
            "run/arm_slots": A.SLOTS.get(arm, float("nan")),
            "run/decode_us_per_step": dec,
            "run/prefill_us_per_token": pre,
            "run/normalized_score": ns,
            "run/passed_correctness": 1.0 if passed == "true" else 0.0,
        }, step=i)

    summary = {"control/decode_us_per_step_mean": cm,
               "control/decode_us_per_step_sd": csd,
               "control/n": cn}
    for arm in arms:
        vals = [d for a, d, _, _ in rows if a == arm]
        m, sd, n = A.stats(vals)
        passes = sorted({p for a, _, _, p in rows if a == arm})
        summary[f"arm_{arm}/decode_mean_us_per_step"] = m
        summary[f"arm_{arm}/decode_sd"] = sd
        summary[f"arm_{arm}/n"] = n
        summary[f"arm_{arm}/passed_correctness"] = "/".join(passes)

    for arm in probes:
        pv = [d for a, d, _, _ in rows if a == arm]
        pm, psd, pn = A.stats(pv)
        se = math.sqrt(csd * csd / cn + psd * psd / pn)
        summary[f"arm_{arm}/delta_welch_us"] = pm - cm
        summary[f"arm_{arm}/delta_welch_se"] = se
        if arm in reg:
            b, bse = reg[arm]
            summary[f"arm_{arm}/delta_ols_us"] = b
            summary[f"arm_{arm}/delta_ols_se"] = bse
            summary[f"arm_{arm}/delta_ols_ci_lo"] = b - 1.96 * bse
            summary[f"arm_{arm}/delta_ols_ci_hi"] = b + 1.96 * bse
        bd = A.block_delta(rows, arm)
        if len(bd) > 1:
            bm, bsd, bn = A.stats(bd)
            summary[f"arm_{arm}/delta_block_us"] = bm
            summary[f"arm_{arm}/delta_block_se"] = bsd / math.sqrt(bn)
        best, bse = reg.get(arm, (pm - cm, se))
        for key, pr in prices.items():
            summary[f"arm_{arm}/ceiling_pcs_{key}"] = -best * pr
            summary[f"arm_{arm}/ceiling_pcs_{key}_95hi"] = -(best - 1.96 * bse) * pr

    if "D" in reg and "X" in reg:
        slope = (reg["X"][0] - reg["D"][0]) / (A.SLOTS["X"] - A.SLOTS["D"])
        sse = math.sqrt(reg["X"][1] ** 2 + reg["D"][1] ** 2) / (
            A.SLOTS["X"] - A.SLOTS["D"]
        )
        ladder = slope * A.LADDER_SLOTS
        hi = (slope + 1.96 * sse) * A.LADDER_SLOTS
        summary["dose/ns_per_issue_slot"] = slope * 1000.0
        summary["dose/ns_per_issue_slot_se"] = sse * 1000.0
        summary["dose/ladder_ceiling_us_per_step"] = ladder
        summary["dose/ladder_ceiling_us_per_step_95hi"] = hi
        for key, pr in prices.items():
            summary[f"dose/ceiling_pcs_{key}"] = ladder * pr
            summary[f"dose/ceiling_pcs_{key}_95hi"] = hi * pr

    run.summary.update(summary)
    print(run.url)
    for k in sorted(summary):
        print(f"{k}\t{summary[k]}")
    run.finish()


if __name__ == "__main__":
    main()
