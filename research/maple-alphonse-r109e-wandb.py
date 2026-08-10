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

# Baselines for the assignment's normalized-score formula.
NS_DECODE_REF = 0.013890  # s/token
NS_PREFILL_REF = 0.0003845  # s/token

# Closed pricing bracket, PR #685 comment 5246312084.
#   %score = elasticity_T * tau * delta_M4_steady_step_wall_us / T_M4
#          = 0.63 * tau * delta / 8972
ADVISOR_PCS_PER_WALL_US = 0.0070  # at tau = 1
ADVISOR_PCS_PER_BUSY_US = 0.0056  # at tau = 1
BAR_PCS = 0.378
BAR_US_STEP_M4_WALL = 54.0
BAR_US_STEP_M4_BUSY = 68.0
CORRECTION = 1.28  # applied as instructed; derivation not independently checked
SIGMA = 0.1498
ELASTICITY_T = 0.638
ELASTICITY_S = 0.362
POOL_US_STEP = 249.5  # advisor slate: my share of the M4 decode step
POOL_HARVEST_REQUIRED = 0.272

# tau is per mechanism class, not per experiment.
UNIT = os.environ.get("UNIT", "slot")
PROFILE = {
    "slot": {
        "arms": {"C": "(unset)", "P": "bcast", "D": "dose1", "X": "dose10"},
        "env_switch": "DARKBLOOM_FULL_ATTN_QK_PROBE",
        "mechanism_class": "in-kernel ALU at fixed geometry",
        "tau": 1.0,
        "unit_name": "issue slot",
        "name": "maple-alphonse-r109e-full-attn-qk-ceiling",
        "job_type": "stage0-ceiling-probe",
    },
    "alloc": {
        "arms": {"O": "MEMO=0", "M": "(unset)", "A": "MEMO=0 DOSE=10",
                 "B": "MEMO=0 DOSE=100"},
        "env_switch": "DARKBLOOM_FULL_PARAMS_MEMO/DARKBLOOM_FULL_PARAMS_DOSE",
        "mechanism_class": "host encode / dispatch",
        "tau": 0.01,
        "unit_name": "host MLXArray construction",
        "name": "maple-alphonse-r109e-full-attn-params-memo",
        "job_type": "stage0-params-memo",
    },
}[UNIT]
ARM_ENV = PROFILE["arms"]


def _ceiling(prefix, saving_us, se_us, prices):
    """Price one M4 wall saving every way the campaign currently prices things.

    `saving_us` is positive when the arm is faster than the control. The
    corrected and busy figures are two independent re-expressions of the same
    wall saving, not a chain: `corrected` applies the advisor's M4->M5 factor,
    `busy` restates M4 wall microseconds as GPU-busy microseconds at the
    measured 0.8 duty. The two advisor prices already agree across that duty,
    so pricing wall-with-wall and busy-with-busy gives the same %score.
    """
    hi = saving_us + 1.96 * se_us
    out = {
        f"{prefix}/saving_us_per_step_m4_wall": saving_us,
        f"{prefix}/saving_us_per_step_m4_wall_95hi": hi,
        f"{prefix}/saving_us_per_step_corrected": saving_us * CORRECTION,
        f"{prefix}/saving_us_per_step_corrected_95hi": hi * CORRECTION,
        f"{prefix}/saving_us_per_step_busy": saving_us / A.BUSY_TO_WALL,
        f"{prefix}/saving_us_per_step_busy_95hi": hi / A.BUSY_TO_WALL,
        f"{prefix}/fraction_of_bar": saving_us / BAR_US_STEP_M4_WALL,
        f"{prefix}/fraction_of_bar_95hi": hi / BAR_US_STEP_M4_WALL,
        # The advisor's pool is a profiler (busy) figure: 68/249.5 = 27.2%, the
        # quoted required harvest. So the pool share must use busy, not wall.
        f"{prefix}/pool_share": saving_us / A.BUSY_TO_WALL / POOL_US_STEP,
        f"{prefix}/pool_share_95hi": hi / A.BUSY_TO_WALL / POOL_US_STEP,
        f"{prefix}/clears_bar_95hi": 1.0 if hi >= BAR_US_STEP_M4_WALL else 0.0,
    }
    for key, pr in prices.items():
        # The busy price is quoted per GPU-busy microsecond, so it must be
        # applied to the busy restatement; it then agrees with the wall price.
        lo_us, hi_us = (
            (saving_us / A.BUSY_TO_WALL, hi / A.BUSY_TO_WALL)
            if key.endswith("_busy") else (saving_us, hi)
        )
        out[f"{prefix}/pcs_{key}"] = lo_us * pr
        out[f"{prefix}/pcs_{key}_95hi"] = hi_us * pr
    # `fraction_of_bar` compares raw microseconds and is only meaningful for a
    # tau = 1 mechanism. This one divides through the class's own tau, so a
    # host-encode saving is not read as if it were in-kernel work.
    out[f"{prefix}/fraction_of_bar_priced"] = out[f"{prefix}/pcs_advisor_wall"] / BAR_PCS
    out[f"{prefix}/fraction_of_bar_priced_95hi"] = (
        out[f"{prefix}/pcs_advisor_wall_95hi"] / BAR_PCS
    )
    return out


def main():
    paths = sys.argv[1:]
    rows = A.load(paths)
    head = subprocess.run(
        ["git", "-C", REPO, "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()

    ctrl_arm = A.CONTROL
    arms = sorted({a for a, _, _, _ in rows})
    probes = [a for a in arms if a != ctrl_arm]
    ctrl = [d for a, d, _, _ in rows if a == ctrl_arm]
    cm, csd, cn = A.stats(ctrl)
    reg = A.regression(rows, probes) if len(rows) > len(probes) + 3 else {}
    lead_arms = {a for a, _, _, _ in rows[:: A.BLOCK]}
    reg_lead = (
        A.regression(rows, probes, lead=True)
        if len(lead_arms) > 1 and len(rows) > len(probes) + 4
        else {}
    )
    tau = PROFILE["tau"]
    prices = {
        # The advisor's closed bracket is the headline; the rest are kept so an
        # older memo number can still be reproduced from this run.
        "advisor_wall": ADVISOR_PCS_PER_WALL_US * tau,
        "advisor_busy": ADVISOR_PCS_PER_BUSY_US * tau,
        "rule105_2_beta": A.K_BETA * A.M5_PRICE,
        "k_issue_upper": A.K_ISSUE_UPPER * A.M5_PRICE,
        "brief_m5_step": A.BRIEF_PRICE,
    }

    run = wandb.init(
        entity="wandb-applied-ai-team",
        project="mlxfast-maple",
        name=PROFILE["name"],
        job_type=PROFILE["job_type"],
        tags=["maple-alphonse", "r109-E", "full_attention", "decode",
              "laguna_full_fused_attn_grow_v1", "ceiling-probe", "abba",
              "dose-response", "m4-directional", f"unit-{UNIT}",
              PROFILE["job_type"]],
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
            if UNIT == "slot" else
            "Stage 0 bolt-on of R109-E: memoize the 5-element params MLXArray "
            "rebuilt on every full-attention call. 10 full-attention calls per "
            "decode step share one (writeIdx, capacity), so the memo removes 9 "
            "of 10 host constructions per step, bit-exact. O is the shipped "
            "rebuild-always path, M the memo, and A/B add 10x/100x extra "
            "constructions per call as a dose ruler. This is the host-encode "
            "mechanism class (tau ~ 1%), so its wall microseconds must NOT be "
            "priced with the in-kernel ALU coefficient."
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
            "grid": "((heads/2)*1024,1,1)",
            "threadgroup": "(1024,1,1)",
            "geometry_changed": False,
            "env_switch": PROFILE["env_switch"],
            "mechanism_class": PROFILE["mechanism_class"],
            "tau": tau,
            "unit_name": PROFILE["unit_name"],
            "arms": ARM_ENV,
            "arm_slots": A.SLOTS,
            "ladder_slots": A.LADDER_SLOTS,
            "control_arm": ctrl_arm,
            "order": "".join(a for a, _, _, _ in rows),
            "n_runs": len(rows),
            "block_len": A.BLOCK,
            "block_lead_arms": sorted(lead_arms),
            "harness": "./benchmark.sh --local-iterate",
            "fan_prompt": 0,
            "host": "Apple M4 Pro, 20 GPU cores, 48 GiB, macOS 26.5.2",
            "apple_gpu_generation": 16,
            "nax_reachable": False,
            "price_pcs_per_us_step": prices,
            # Closed pricing bracket (PR #685 comment 5246312084).
            "advisor_pcs_per_wall_us_tau1": ADVISOR_PCS_PER_WALL_US,
            "advisor_pcs_per_busy_us_tau1": ADVISOR_PCS_PER_BUSY_US,
            "bar_pcs": BAR_PCS,
            "bar_us_step_m4_wall": BAR_US_STEP_M4_WALL,
            "bar_us_step_m4_busy": BAR_US_STEP_M4_BUSY,
            "m4_to_m5_correction": CORRECTION,
            "sigma_prefill_share": SIGMA,
            "elasticity_T": ELASTICITY_T,
            "elasticity_S": ELASTICITY_S,
            "pool_us_per_step_m4": POOL_US_STEP,
            "pool_harvest_required": POOL_HARVEST_REQUIRED,
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
    if "__lead__" in reg_lead:
        spike, sspike = reg_lead["__lead__"]
        summary["lead/spike_us_per_step"] = spike
        summary["lead/spike_se"] = sspike
        summary["lead/spike_ci_lo"] = spike - 1.96 * sspike
        summary["lead/spike_ci_hi"] = spike + 1.96 * sspike
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
        if arm in reg_lead:
            b, bse = reg_lead[arm]
            summary[f"arm_{arm}/delta_lead_adj_us"] = b
            summary[f"arm_{arm}/delta_lead_adj_se"] = bse
            summary[f"arm_{arm}/delta_lead_adj_ci_lo"] = b - 1.96 * bse
            summary[f"arm_{arm}/delta_lead_adj_ci_hi"] = b + 1.96 * bse
        bd = A.block_delta(rows, arm)
        if len(bd) > 1:
            bm, bsd, bn = A.stats(bd)
            summary[f"arm_{arm}/delta_block_us"] = bm
            summary[f"arm_{arm}/delta_block_se"] = bsd / math.sqrt(bn)
        # Prefer the lead-adjusted estimate: block position is confounded with
        # arm whenever the driver pins one arm to slot 1.
        best, bse = reg_lead.get(arm, reg.get(arm, (pm - cm, se)))
        summary.update(_ceiling(f"arm_{arm}", -best, bse, prices))

    lo_arm, hi_arm = A.DOSE_ARMS
    dose_reg = reg_lead or reg
    if lo_arm in dose_reg and hi_arm in dose_reg:
        span = A.SLOTS[hi_arm] - A.SLOTS[lo_arm]
        slope = (dose_reg[hi_arm][0] - dose_reg[lo_arm][0]) / span
        sse = math.sqrt(dose_reg[hi_arm][1] ** 2 + dose_reg[lo_arm][1] ** 2) / span
        ladder = slope * A.LADDER_SLOTS
        hi = (slope + 1.96 * sse) * A.LADDER_SLOTS
        summary[f"dose/ns_per_{UNIT}"] = slope * 1000.0
        summary[f"dose/ns_per_{UNIT}_se"] = sse * 1000.0
        summary["dose/ladder_ceiling_us_per_step"] = ladder
        summary["dose/ladder_ceiling_us_per_step_95hi"] = hi
        summary.update(_ceiling("dose", ladder, sse * A.LADDER_SLOTS, prices))

    run.summary.update(summary)
    print(run.url)
    for k in sorted(summary):
        print(f"{k}\t{summary[k]}")
    run.finish()


if __name__ == "__main__":
    main()
