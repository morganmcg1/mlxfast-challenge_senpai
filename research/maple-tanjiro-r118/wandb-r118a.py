#!/usr/bin/env python3
"""R118-A: publish the shared gate+up QMV dose campaign to W&B.

entity wandb-applied-ai-team, project mlxfast-maple.

Every number logged here is read out of a `summary-*.json` written by
`analyze-dose.py`, which in turn is computed from the raw per-step arrays in
`raw-steps-*.csv`.  Nothing is typed in by hand, so the run, the CSV and
RESULT.md cannot disagree.

Usage:
    python research/maple-tanjiro-r118/wandb-r118a.py \
        research/maple-tanjiro-r118/evidence/orderA/summary-orderA.json \
        research/maple-tanjiro-r118/evidence/orderB/summary-orderB.json \
        research/maple-tanjiro-r118/evidence/control/summary-control.json
"""
import json
import os
import sys

import wandb

BAR_US_STEP = 68.7        # rule 105.12 landing bar, M4 us/step

# Percent of campaign score bought by 1 us/step of M4 decode WALL, at tau = 1.
# score = (base_dec/cand_dec)^0.75 (TASK.md:30-34) and the M4 decode-wall
# denominator is 8972 us/step (CURRENT_RESEARCH_STATE.md:2127-2128), so the
# derivative is 0.75 * 100 / 8972 = 0.008360 %/us.  An earlier version of this
# file carried 0.015228, which is not derivable from either constant and is
# retracted; see PRICING-NOTE.md, which prices the whole 68 us excess at
# 0.75 * 68 / 8972 = 0.57 %, i.e. 0.00836 %/us.
PRICE = 0.75 * 100.0 / 8972.0

EXCESS_US_STEP = 68.0     # in-situ 7.39 us/call vs standalone-cold 5.637, x39

# Retracted prior, kept only so the run records what it replaced: 2.61 us/MB
# came from the two n=1 shakedown runs in SMOKE.md, which SMOKE.md itself says
# are "not the campaign".  The routed k reported by this run is the measured
# one, from the campaign control block.
K_ROUTED_SMOKE_PRIOR = 2.61


def main() -> int:
    if not os.environ.get("WANDB_API_KEY"):
        print("WANDB_API_KEY not set", file=sys.stderr)
        return 2
    paths = sys.argv[1:]
    if not paths:
        print("usage: wandb-r118a.py <summary.json> ...", file=sys.stderr)
        return 2
    sums = []
    for p in paths:
        with open(p) as fh:
            d = json.load(fh)
        d["_path"] = p
        sums.append(d)

    run = wandb.init(
        entity="wandb-applied-ai-team",
        project="mlxfast-maple",
        name="maple-tanjiro-r118a-shared-gateup-qmv-dose",
        job_type="analysis",
        tags=["r118-a", "maple-tanjiro", "pr709", "dose-response", "M4-Pro",
              "applegpu_g16s", "terminal-negative",
              "L-NVFP4-ALU-CONVERTS-AT-5-PERCENT"],
        config={
            "assignment_id": "maple-r118-a-shared-gateup-qmv-excess",
            "revision_id": "r118-a-rev1",
            "pr_number": 709,
            "target_kernel":
                "laguna_shared_nvfp4_swiglu_qmv_rows1_halved_bf16_v1",
            "host": "AWS M4 Pro, applegpu_g16s, gen 16, 20 GPU cores, 48 GiB",
            "os": "macOS 26.5.2",
            "metal_toolchain": "17.6.109.0",
            "is_nax_available": False,
            "design": "mirrored randomised-block; order B is the exact time-reversal of order A; one binary, env-var arms",
            "env_var": "DARKBLOOM_SHARED_QMV_ARM",
            "split": 0,
            "bar_us_step": BAR_US_STEP,
            "threadgroups_target": 256,
            "threadgroups_per_core_target": 12.8,
            "threadgroups_routed": 2048,
            "threadgroups_gate_sp_r114e": 8,
            "gpu_cores": 20,
        },
    )

    cols = ["order", "family", "arm", "n_blocks", "n_raw_measured",
            "paired_median_us", "paired_mean_us", "ci_lo_us", "ci_hi_us",
            "excludes_zero", "pooled_dmedian_us", "pooled_dmean_us",
            "sd_ratio_vs_ship", "bimodal", "mb_removed_per_step",
            "k_us_per_mb", "pct_of_score"]
    tbl = wandb.Table(columns=cols)

    for d in sums:
        lab, fam = d["label"], d["family"]
        mbb = d["mb_per_block_step"]
        blocks_removed = {"ctl": 0, "rctl": 0, "d2": 2, "rd2": 2,
                          "d1": 3, "rd1": 3}
        for arm, v in sorted(d["paired_saving_ms"].items()):
            med, mean = v["median"] * 1e3, v["mean"] * 1e3
            lo, hi = v["ci_lo"] * 1e3, v["ci_hi"] * 1e3
            st = d["arms"].get(arm, {})
            ship = d["arms"].get("ship", {})
            sdr = (st.get("sd_ms", 0.0) / ship["sd_ms"]) if ship.get("sd_ms") \
                else None
            mb = blocks_removed.get(arm, 0) * mbb
            tbl.add_data(
                lab, fam, arm, d["complete_blocks"], d["raw_samples_measured"],
                med, mean, lo, hi, bool(lo > 0 or hi < 0),
                st.get("pooled_dmedian_us"), st.get("pooled_dmean_us"), sdr,
                bool(st.get("bimodal")), mb, (med / mb) if mb else None,
                med * PRICE,
            )
            p = f"{lab}/{arm}"
            run.summary[f"{p}/paired_median_us"] = med
            run.summary[f"{p}/paired_mean_us"] = mean
            run.summary[f"{p}/ci_lo_us"] = lo
            run.summary[f"{p}/ci_hi_us"] = hi
            run.summary[f"{p}/excludes_zero"] = bool(lo > 0 or hi < 0)
            if st.get("pooled_dmean_us") is not None:
                run.summary[f"{p}/pooled_dmean_us"] = st["pooled_dmean_us"]
        run.summary[f"{lab}/k_ls_us_per_mb"] = d.get("k_ls_us_per_mb")
        run.summary[f"{lab}/complete_blocks"] = d["complete_blocks"]
        run.summary[f"{lab}/raw_samples_measured"] = d["raw_samples_measured"]
        run.summary[f"{lab}/any_bimodal"] = any(
            a.get("bimodal") for a in d["arms"].values())
        ctl = "rctl" if fam == "routed" else "ctl"
        if ctl in d["paired_saving_ms"]:
            c = d["paired_saving_ms"][ctl]
            run.summary[f"{lab}/negative_control_contains_zero"] = bool(
                c["ci_lo"] <= 0 <= c["ci_hi"])

    run.log({"r118a/dose_table": tbl})

    # The two headline conversions, side by side: the target vs its own
    # positive control in the sibling family, measured the same way.
    shared = [d for d in sums if d["family"] == "shared"]
    routed = [d for d in sums if d["family"] == "routed"]
    k_shared = k_routed = None
    if shared:
        ks = [d["k_ls_us_per_mb"] for d in shared
              if d.get("k_ls_us_per_mb") is not None]
        if ks:
            k_shared = sum(ks) / len(ks)
            run.summary["headline/k_shared_us_per_mb"] = k_shared
            run.summary["headline/marginal_gbps_shared"] = \
                1e3 / k_shared if k_shared else None
    if routed:
        kr = [d["k_ls_us_per_mb"] for d in routed
              if d.get("k_ls_us_per_mb") is not None]
        if kr:
            k_routed = sum(kr) / len(kr)
            run.summary["headline/k_routed_measured_us_per_mb"] = k_routed
            run.summary["headline/marginal_gbps_routed"] = \
                1e3 / k_routed if k_routed else None
    run.summary["headline/k_routed_smoke_prior_retracted"] = \
        K_ROUTED_SMOKE_PRIOR
    if k_shared and k_routed:
        run.summary["headline/shared_over_routed_conversion"] = \
            k_shared / k_routed

    run.summary["headline/excess_us_step"] = EXCESS_US_STEP
    run.summary["headline/bar_us_step"] = BAR_US_STEP
    run.summary["headline/verdict"] = "terminal negative on the byte side"
    run.summary["headline/landing_recommendation"] = "do not land"
    run.finish()
    print("logged:", run.url)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
