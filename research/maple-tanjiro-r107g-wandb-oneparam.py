#!/usr/bin/env python3
"""R107-G addendum: log the §3.7 one-parameter dispatch model to the existing run.

Resumes the census run (entity wandb-applied-ai-team, project mlxfast-maple,
run id jhuxsg3h) and

  1. CORRECTS one stale metric.  `census/family_E_full_fusion_prize_pct_cs` was
     first logged as 1.664, which priced the whole family-E fusion prize at
     beta = 0.5.  Rule 105.13 supplies a third regime constant k_dispatch = 1.89
     for the dispatch-elimination component, which lifts the prize to 2.451 % of
     `cs`.  The old value is kept under a `_superseded_beta_only` key so the
     correction is auditable rather than silent.

  2. Adds the §3.7 one-parameter model: the 13-family measured-vs-predicted
     efficiency table, its residual statistics, the free two-parameter fit that
     recovers both host constants without being told them, the full 13-family
     non-byte slack table, and the falsification leg on the two attention
     families the model deliberately does not fit.

Every number here is either a local M4 measurement from this assignment or an
audited B.0.3 / rule figure quoted from the charge.  Zero receipts consumed.
"""
import os
import sys

import wandb

PEAK = 266.3e9
INTERCEPT = 3.97
PRICE = 0.015228   # % of cs per M5 us/step
BETA = 0.5
BAR = 0.4

# name, bytes/dispatch, census M4 dispatch_us, calls/step, provenance
# byte counts and M4 us/step are byte-identical to research/maple-tanjiro-r107g-oneparam.py
# so this run and stage1-oneparam-model.txt cannot drift.
FAM = [
    ("T2b_prime_gate_sp_h48", 197_000, 80.2 / 10, 10, "derived_from_B033_M4"),
    ("E_T2b_gate_sp_h64", 262_000, 248.0 / 30, 30, "derived_from_B033_M4"),
    ("T1a_residual_rms_router", 1_048_600, 312.8 / 39, 39, "derived_from_B033_M4"),
    ("T2a_shared_gate_up", 1_114_100, 287.1 / 39, 39, "derived_from_B033_M4"),
    ("B_T2d_down_residual", 5_013_500, 858.9 / 39, 39, "derived_from_B033_M4"),
    ("T3c_oproj_h48", 6_490_000, 301.8 / 10, 10, "derived_from_B033_M4"),
    ("T0b_b_qkv_h48", 8_659_000, 362.8 / 10, 10, "derived_from_B033_M4"),
    ("A_T3b_oproj_h64", 8_652_667, 1117.7 / 30, 30, "derived_from_B033_M4"),
    ("D_T2c_routed_gate_up", 8_912_900, 1497.7 / 39, 39, "measured_locally"),
    ("C_T0b_a_qkv_h64", 10_823_667, 1340.1 / 30, 30, "derived_from_B033_M4"),
    ("dense_down_L0", 33_550_000, 133.8 / 1, 1, "derived_from_B033_M4"),
    ("dense_gate_up_L0", 67_110_000, 269.4 / 1, 1, "derived_from_B033_M4"),
    ("T1c_lmhead", 109_180_000, 420.3 / 1, 1, "derived_from_B033_M4"),
]

# the two attention families the model refuses to fit (falsification leg)
ATTN = [
    ("T3a_sliding_fused_attn", 2_097_000, 636.0 / 30, 30),
    ("T3a_prime_full_fused_attn", 2_359_000, 229.7 / 10, 10),
]


def main() -> int:
    if not os.environ.get("WANDB_API_KEY"):
        print("WANDB_API_KEY not set", file=sys.stderr)
        return 2
    run = wandb.init(
        entity="wandb-applied-ai-team",
        project="mlxfast-maple",
        id="jhuxsg3h",
        resume="must",
    )

    # ---------------- 1. the stale family-E prize metric ----------------
    old = run.summary.get("census/family_E_full_fusion_prize_pct_cs")
    run.summary["census/family_E_full_fusion_prize_pct_cs_superseded_beta_only"] = (
        old if old is not None else 1.664
    )
    run.summary["census/family_E_full_fusion_prize_pct_cs"] = 2.451
    run.summary["census/family_E_full_fusion_prize_bars"] = 2.451 / BAR
    run.summary["census/family_E_dispatch_component_m5_us_step"] = 70.21
    run.summary["census/family_E_dispatch_component_pct_cs"] = 1.069
    run.summary["census/family_E_prize_correction_note"] = (
        "beta-only 1.664 superseded: rule 105.13 prices the dispatch-elimination "
        "component of the prize at k_dispatch=1.89, not beta=0.5"
    )

    # ---------------- 2. the one-parameter model ----------------
    rows = []
    slack_rows = []
    meas_pct, pred_pct = [], []
    xs, ys = [], []
    total_pos_slack = 0.0
    for name, nbytes, disp, calls, prov in FAM:
        bus = nbytes / PEAK * 1e6
        pred = bus + INTERCEPT
        m_pct = 100.0 * bus / disp
        p_pct = 100.0 * bus / pred
        slack = disp - pred
        per_step = slack * calls
        pct_cs = per_step * BETA * PRICE
        meas_pct.append(m_pct)
        pred_pct.append(p_pct)
        xs.append(float(nbytes))
        ys.append(disp)
        if per_step > 0:
            total_pos_slack += per_step
        rows.append([name, nbytes / 1e6, disp, bus, pred, m_pct, p_pct,
                     m_pct - p_pct, prov])
        slack_rows.append([name, slack, per_step, pct_cs, pct_cs / BAR,
                           "OPEN" if pct_cs / BAR >= 1.0
                           else ("AT_OR_BELOW_FLOOR" if slack <= 0 else "CLOSED")])
        pre = f"oneparam/{name}"
        run.summary[f"{pre}/bytes_per_dispatch"] = nbytes
        run.summary[f"{pre}/dispatch_us_m4"] = disp
        run.summary[f"{pre}/pred_us_m4"] = pred
        run.summary[f"{pre}/measured_pct_of_peak"] = m_pct
        run.summary[f"{pre}/predicted_pct_of_peak"] = p_pct
        run.summary[f"{pre}/residual_pp"] = m_pct - p_pct
        run.summary[f"{pre}/nonbyte_slack_us"] = slack
        run.summary[f"{pre}/nonbyte_slack_m4_us_step"] = per_step
        run.summary[f"{pre}/nonbyte_slack_bars_at_beta"] = pct_cs / BAR
        run.summary[f"{pre}/provenance"] = prov

    n = len(FAM)
    resid = [m - p for m, p in zip(meas_pct, pred_pct)]
    mean_resid = sum(resid) / n
    mean_abs = sum(abs(r) for r in resid) / n
    rms = (sum(r * r for r in resid) / n) ** 0.5
    mbar = sum(meas_pct) / n
    sst = sum((m - mbar) ** 2 for m in meas_pct)
    sse = sum(r * r for r in resid)
    r2 = 1.0 - sse / sst

    run.summary["oneparam/n_families"] = n
    run.summary["oneparam/free_parameters"] = 0
    run.summary["oneparam/byte_range_ratio"] = max(xs) / min(xs)
    run.summary["oneparam/measured_efficiency_min_pct"] = min(meas_pct)
    run.summary["oneparam/measured_efficiency_max_pct"] = max(meas_pct)
    run.summary["oneparam/residual_mean_pp"] = mean_resid
    run.summary["oneparam/residual_mean_abs_pp"] = mean_abs
    run.summary["oneparam/residual_rms_pp"] = rms
    run.summary["oneparam/r2_on_efficiency_column"] = r2
    run.summary["oneparam/total_positive_slack_m4_us_step"] = total_pos_slack
    run.summary["oneparam/total_positive_slack_pct_cs_at_beta"] = (
        total_pos_slack * BETA * PRICE)
    run.summary["oneparam/total_positive_slack_bars_at_beta"] = (
        total_pos_slack * BETA * PRICE / BAR)
    run.summary["oneparam/families_clearing_one_bar_alone"] = sum(
        1 for r in slack_rows if r[4] >= 1.0)

    # free two-parameter OLS, to show the census recovers both host constants
    xbar = sum(xs) / n
    ybar = sum(ys) / n
    sxy = sum((x - xbar) * (y - ybar) for x, y in zip(xs, ys))
    sxx = sum((x - xbar) ** 2 for x in xs)
    slope = sxy / sxx
    icept = ybar - slope * xbar
    fsse = sum((y - (slope * x + icept)) ** 2 for x, y in zip(xs, ys))
    fsst = sum((y - ybar) ** 2 for y in ys)
    run.summary["oneparam_freefit/slope_us_per_byte"] = slope
    run.summary["oneparam_freefit/implied_bandwidth_gbps"] = (1e6 / slope) / 1e9
    run.summary["oneparam_freefit/intercept_us"] = icept
    run.summary["oneparam_freefit/r2_on_dispatch_us"] = 1.0 - fsse / fsst
    run.summary["oneparam_freefit/bw_pct_of_campaign_ceiling"] = (
        100.0 * (1e6 / slope) / PEAK)
    run.summary["oneparam_freefit/intercept_ratio_to_rule55"] = icept / INTERCEPT

    # falsification: the model must MISS the two fused-attention families
    worst_ratio = 0.0
    for name, nbytes, disp, calls in ATTN:
        pred = nbytes / PEAK * 1e6 + INTERCEPT
        ratio = disp / pred
        worst_ratio = max(worst_ratio, ratio)
        run.summary[f"oneparam_falsify/{name}/dispatch_us_m4"] = disp
        run.summary[f"oneparam_falsify/{name}/pred_us_m4"] = pred
        run.summary[f"oneparam_falsify/{name}/meas_over_pred"] = ratio
    ratios = [d / (nb / PEAK * 1e6 + INTERCEPT) for (nm, nb, d, c, p) in FAM
              if nb >= 1_000_000]
    run.summary["oneparam_falsify/bytes_dominated_ratio_min"] = min(ratios)
    run.summary["oneparam_falsify/bytes_dominated_ratio_max"] = max(ratios)
    run.summary["oneparam_falsify/attention_worst_ratio"] = worst_ratio
    run.summary["oneparam_falsify/n_bytes_dominated"] = len(ratios)

    # the gate_sp coincidence: same kernel, two head counts, same latency pool
    run.summary["oneparam/gate_sp_h64_slack_us"] = 3.313
    run.summary["oneparam/gate_sp_h48_slack_us"] = 3.310
    run.summary["oneparam/gate_sp_slack_difference_us"] = 0.003

    run.log({
        "oneparam/model_table": wandb.Table(
            columns=["family", "MB_per_dispatch", "dispatch_us_m4", "bus_us",
                     "pred_us", "measured_pct_peak", "predicted_pct_peak",
                     "residual_pp", "provenance"],
            data=rows),
        "oneparam/slack_table": wandb.Table(
            columns=["family", "slack_us", "slack_m4_us_step",
                     "pct_cs_at_beta", "bars_at_beta", "verdict"],
            data=slack_rows),
    })

    print("updated wandb run:", run.url)
    print(f"  n={n}  R2={r2:.4f}  rms={rms:.2f}pp  "
          f"freefit={(1e6/slope)/1e9:.1f}GB/s @ {icept:.2f}us")
    print(f"  total positive slack = {total_pos_slack:.1f} M4 us/step "
          f"= {total_pos_slack*BETA*PRICE:.3f} pct cs")
    run.finish()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
