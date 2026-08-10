#!/usr/bin/env python3
"""R107-G: publish the decode-family regime census to W&B.

entity wandb-applied-ai-team, project mlxfast-maple.

Logs, for every family in the census:
  - the H-REGIME decomposition (dispatch / byte / issue / residual, both nominal
    and exposed issue terms),
  - the regime verdict and the implied two-pool constant k,
  - the exchange rates and the two 0.4 %-bar figures,
  - the non-byte slack bound in bars,
plus the two host constants this census measured (DRAM ceiling and sustained fma
issue rate) and the machine balance point derived from them, and the alpha/beta
adjudication table.

Nothing here is a receipt: every number is either a local M4 measurement made in
this assignment or an audited figure quoted from the charge, and each row carries
a `provenance` field saying which.
"""
import os
import sys

import wandb

PEAK = 266.3e9            # measured achievable DRAM, this M4 Pro
BEST_STREAM = 262.96e9    # best measured streaming rate (160 TG x 64 thr, ilp 4)
FMA_CEIL_2048 = 3.4453e12  # measured sustained fma/s at 2048 TG x 64 thr
FMA_CEIL_256 = 3.6364e12   # measured sustained fma/s at 256 TG x 64 thr
SLOT_2048 = 0.038043721   # us per fma-per-thread, 2048 TG x 64 thr
SLOT_256 = 0.004505613    # us per fma-per-thread, 256 TG x 64 thr
INTERCEPT = 3.97          # us, rule 55 per-dispatch intercept, M4
PRICE = 0.015228          # % of cs per M4 us/step
BAR = 0.4
EXPOSURE = 0.087          # measured on family D at its operating point
BALANCE = PEAK / FMA_CEIL_2048

# name, calls, M4 us/step, bytes/dispatch, k, slot, base fma/thr, geom GB/s, regime, provenance
FAM = [
    ("D_T2c_routed_gate_up", 39, 1497.7, 8_912_821, 0.4369, SLOT_2048, 128, 256.4e9,
     "BYTES", "directly_probed"),
    ("A_T3b_oproj_h64", 30, 1117.7, 8_652_667, 0.4369, SLOT_256, 1024, 254.4e9,
     "BYTES", "inferred"),
    ("C_T0b_a_qkv_h64", 30, 1340.1, 10_823_667, 0.4369, SLOT_2048, 256, 254.4e9,
     "BYTES", "inferred"),
    ("B_T2d_down_residual", 39, 858.9, 5_013_590, 0.4369, SLOT_2048, 64, 252.3e9,
     "BYTES", "inferred"),
    ("E_T2b_gate_sp_h64", 30, 248.0, 262_000, 0.5000, SLOT_2048, 68, 219.0e9,
     "LATENCY", "inferred"),
]


def main() -> int:
    if not os.environ.get("WANDB_API_KEY"):
        print("WANDB_API_KEY not set", file=sys.stderr)
        return 2
    run = wandb.init(
        entity="wandb-applied-ai-team",
        project="mlxfast-maple",
        name="maple-tanjiro-r107g-decode-family-regime-census",
        job_type="analysis",
        tags=["r107-g", "maple-tanjiro", "pr648", "regime-census", "M4-Pro",
              "applegpu_g16s", "N-BYTES-EVERYWHERE"],
        config={
            "assignment_id": "maple-r107-g-decode-family-regime-census",
            "revision_id": "r107-g-rev1",
            "pr_number": 648,
            "host": "AWS M4 Pro, applegpu_g16s, gen 16, 20 GPU cores, 48 GiB unified",
            "os": "macOS 26.5.2",
            "metal_toolchain": "17.6.109.0",
            "epoch_advisor_tip": "acb56108",
            "runtime_model_sha256": "a736b50f66b08b9004a807ff38226aaeb95ba836e6e833b51a8e862466d850c4",
            "receipts_consumed": 0,
            "measured_dram_peak_gbps": PEAK / 1e9,
            "measured_best_stream_gbps": BEST_STREAM / 1e9,
            "measured_fma_ceiling_2048tg": FMA_CEIL_2048,
            "measured_fma_ceiling_256tg": FMA_CEIL_256,
            "quoted_fma_ceiling": 4.04e12,
            "machine_balance_point_bytes_per_fma": BALANCE,
            "rule55_intercept_us": INTERCEPT,
            "campaign_price_pct_cs_per_m4_us_step": PRICE,
            "bar_pct_cs": BAR,
            "measured_exposure_fraction_family_D": EXPOSURE,
            "effective_slc_mib": "12-16",
            "outcome": "N-BYTES-EVERYWHERE + LATENCY(E) + N-DEGENERATE(alpha)",
        },
    )

    # ---- host constants -------------------------------------------------
    run.summary["host/dram_peak_gbps"] = PEAK / 1e9
    run.summary["host/best_stream_gbps"] = BEST_STREAM / 1e9
    run.summary["host/stream_pct_of_peak"] = 100.0 * BEST_STREAM / PEAK
    run.summary["host/fma_per_s_sustained"] = FMA_CEIL_2048
    run.summary["host/fma_pct_of_quoted_4p04e12"] = 100.0 * FMA_CEIL_2048 / 4.04e12
    run.summary["host/balance_point_bytes_per_fma"] = BALANCE

    # ---- per-family census table ---------------------------------------
    cols = ["family", "provenance", "regime", "k", "calls", "m4_us_step",
            "dispatch_us", "bytes_per_dispatch", "achieved_gbps", "pct_dram_peak",
            "pct_geometry_achievable", "bytes_per_fma", "x_balance_point",
            "byte_term_us", "issue_term_nominal_us", "issue_term_exposed_us",
            "residual_latency_us", "dram_floor_us", "nonbyte_slack_us",
            "nonbyte_slack_pct_cs", "nonbyte_slack_bars",
            "bar_instr_per_thread_exposed", "bar_instr_per_thread_nominal",
            "base_fma_per_thread", "bar_mib_per_step", "bar_pct_of_family_bytes",
            "bar_m4_us_step", "bar_pct_of_family_m4_cost"]
    table = wandb.Table(columns=cols)

    fam_bytes_total = 0.0
    for (name, calls, m4, byt, k, slot, base_fma, geom, regime, prov) in FAM:
        disp = m4 / calls
        byte_us = byt / PEAK * 1e6
        achieved = byt / (disp * 1e-6)
        nom_us = base_fma * slot
        exp_us = nom_us * EXPOSURE if prov == "inferred" else base_fma * 0.003313
        resid = disp - byte_us - exp_us
        floor = byte_us + INTERCEPT
        slack = disp - floor
        slack_step = slack * calls
        slack_pct = slack_step * k * PRICE
        # exchange rates
        nom_pct_per_instr = slot * calls * k * PRICE
        exp_pct_per_instr = nom_pct_per_instr * EXPOSURE
        bar_instr_nom = BAR / nom_pct_per_instr
        bar_instr_exp = BAR / exp_pct_per_instr
        # byte axis: 1 % of B = 16,714,024 B ~ 27.73 M4 us/step ~ 0.4223 % of cs
        mib_step = byt * calls / (1024.0 * 1024.0)
        bar_mib = BAR / 0.4223 * (16_714_024 / (1024.0 * 1024.0))
        bar_m4 = BAR / (k * PRICE)
        fam_bytes_total += byt * calls
        bpf = byt / _fma_total(name, base_fma, calls)
        table.add_data(
            name, prov, regime, k, calls, m4, disp, byt, achieved / 1e9,
            100.0 * achieved / PEAK, 100.0 * achieved / geom,
            bpf, bpf / BALANCE,
            byte_us, nom_us, exp_us, resid, floor, slack, slack_pct,
            slack_pct / BAR, bar_instr_exp, bar_instr_nom, base_fma, bar_mib,
            100.0 * bar_mib / mib_step, bar_m4, 100.0 * bar_m4 / m4)
        prefix = f"family/{name}"
        run.summary[f"{prefix}/regime"] = regime
        run.summary[f"{prefix}/k"] = k
        run.summary[f"{prefix}/dispatch_us"] = disp
        run.summary[f"{prefix}/byte_term_us"] = byte_us
        run.summary[f"{prefix}/issue_term_nominal_us"] = nom_us
        run.summary[f"{prefix}/issue_term_exposed_us"] = exp_us
        run.summary[f"{prefix}/residual_latency_us"] = resid
        run.summary[f"{prefix}/achieved_gbps"] = achieved / 1e9
        run.summary[f"{prefix}/pct_dram_peak"] = 100.0 * achieved / PEAK
        run.summary[f"{prefix}/nonbyte_slack_bars"] = slack_pct / BAR
        run.summary[f"{prefix}/bar_instr_per_thread_exposed"] = bar_instr_exp
        run.summary[f"{prefix}/bar_m4_us_step"] = bar_m4
    run.log({"census/families": table})

    # ---- family D dose ladder (the direct probe) ------------------------
    dose_cols = ["session", "arm", "extra_fma_per_thread", "delta_us", "sd",
                 "delta_pct", "t_stat", "residency"]
    dose = wandb.Table(columns=dose_cols)
    for row in [
        ("s1", "dose4", 128, 0.424, 0.179, 1.095, 15.20, "defeated"),
        ("s1", "dose8", 256, 1.860, 0.237, 4.799, 50.27, "defeated"),
        ("s1", "dose16", 512, 5.865, 0.209, 15.120, 179.59, "defeated"),
        ("s2", "dose4", 128, 0.369, 0.177, 0.952, 13.38, "defeated"),
        ("s2", "dose8", 256, 1.848, 0.223, 4.769, 53.00, "defeated"),
        ("s2", "dose16", 512, 5.808, 0.216, 14.973, 172.58, "defeated"),
        ("s3", "dose4", 128, 2.061, float("nan"), 5.682, float("nan"),
         "RESIDENT - NOT A HEADLINE"),
        ("s3", "dose8", 256, 3.571, float("nan"), 9.756, float("nan"),
         "RESIDENT - NOT A HEADLINE"),
        ("s3", "dose16", 512, 7.617, float("nan"), 21.100, float("nan"),
         "RESIDENT - NOT A HEADLINE"),
    ]:
        dose.add_data(*row)
    run.log({"family_D/dose_ladder": dose})
    run.summary["family_D/marginal_us_per_fma_base"] = 0.003313
    run.summary["family_D/marginal_us_per_fma_high_dose"] = 0.015645
    run.summary["family_D/pure_alu_slot_us"] = SLOT_2048
    run.summary["family_D/exposure_fraction_base"] = 0.087
    run.summary["family_D/linearity_ratio_d16_over_d4"] = 13.83
    run.summary["family_D/residency_inflation_of_base_sensitivity"] = 4.86
    run.summary["family_D/reach_pct_vs_charge"] = 1.03

    # ---- family D bytes ladder -----------------------------------------
    byte_cols = ["session", "threadgroups", "ref_us", "gbps", "pct_peak",
                 "slc_fit", "regime_label"]
    bt = wandb.Table(columns=byte_cols)
    for row in [
        ("s1", 128, 4.89, 115.1, 43.2, True, "PARTIAL"),
        ("s1", 256, 7.18, 155.9, 58.6, True, "PARTIAL"),
        ("s1", 512, 12.92, 173.0, 65.0, True, "PARTIAL"),
        ("s1", 1024, 22.12, 201.9, 75.8, True, "PARTIAL"),
        ("s1", 2048, 38.75, 230.4, 86.5, False, "SATURATED"),
        ("s2", 128, 5.12, 109.8, 41.2, True, "PARTIAL"),
        ("s2", 256, 7.21, 155.4, 58.4, True, "PARTIAL"),
        ("s2", 512, 12.76, 175.2, 65.8, True, "PARTIAL"),
        ("s2", 1024, 22.04, 202.6, 76.1, True, "PARTIAL"),
        ("s2", 2048, 38.85, 229.7, 86.3, False, "SATURATED"),
    ]:
        bt.add_data(*row)
    run.log({"family_D/bytes_ladder": bt})
    run.summary["family_D/marginal_bandwidth_gbps_top2"] = 254.4
    run.summary["family_D/marginal_bandwidth_pct_of_peak"] = 95.5

    # ---- bandwidth vs geometry -----------------------------------------
    g = wandb.Table(columns=["threadgroups", "threads_per_tg", "gbps"])
    for tg, tpt, v in [(80, 64, 222.0), (160, 64, 262.96), (260, 64, 254.4),
                       (520, 64, 256.4), (80, 288, 257.0), (160, 288, 255.4),
                       (260, 288, 254.6), (520, 288, 252.5)]:
        g.add_data(tg, tpt, v)
    run.log({"host/bandwidth_vs_geometry": g})

    slc = wandb.Table(columns=["working_set_mib", "gbps"])
    for mib, v in [(2, 1820), (4, 1521), (8, 585), (12, 506), (16, 300),
                   (20, 267), (24, 265), (32, 263)]:
        slc.add_data(mib, v)
    run.log({"host/slc_ladder": slc})

    # ---- alpha / beta adjudication -------------------------------------
    ab = wandb.Table(columns=["pool", "m4_us_step", "m5_measured_us_step",
                              "m5_achieved_gbps", "m4_efficiency_pct",
                              "ceiling_demanded_gbps", "implied_alpha"])
    ab.add_data("routed", 2261.2, 1010.67, 515.9, 86.4, 597.1, 0.4460)
    ab.add_data("qkvo", 3122.4, 1230.70, 597.9, 88.3, 677.1, 0.3933)
    run.log({"adjudication/alpha_beta": ab})
    run.summary["adjudication/verdict"] = "N-DEGENERATE"
    run.summary["adjudication/alpha_upper_bound_alpha_free"] = 0.4454
    run.summary["adjudication/sse_alpha_0p4369"] = 96.2
    run.summary["adjudication/sse_alpha_0p389"] = 126.7
    run.summary["adjudication/ceiling_disagreement_pct"] = 13.4

    # ---- headline scalars ----------------------------------------------
    run.summary["census/outcome"] = "N-BYTES-EVERYWHERE"
    run.summary["census/families_bytes_bound"] = 4
    run.summary["census/families_issue_bound"] = 0
    run.summary["census/families_latency_bound"] = 1
    run.summary["census/max_nonbyte_slack_bars_gemv"] = 0.62
    run.summary["census/family_E_full_fusion_prize_pct_cs"] = 1.664
    run.summary["census/pool_bytes_per_step_mib"] = fam_bytes_total / (1024.0 * 1024.0)
    run.summary["census/rule55"] = "CONFIRMS CLOSURE for all five families"
    run.summary["census/receipts_consumed"] = 0

    print("wandb run:", run.url)
    run.finish()
    return 0


def _fma_total(name, base_fma, calls):
    """Threads per dispatch, so bytes/fma can be derived from base fma/thread."""
    threads = {
        "D_T2c_routed_gate_up": 131_072,
        "A_T3b_oproj_h64": 16_384,
        "C_T0b_a_qkv_h64": 81_920,
        "B_T2d_down_residual": 147_456,
        "E_T2b_gate_sp_h64": 1_920,
    }[name]
    return base_fma * threads


if __name__ == "__main__":
    raise SystemExit(main())
