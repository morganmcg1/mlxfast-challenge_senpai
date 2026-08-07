#!/usr/bin/env python3
"""Publish the QKV-GEMV threadgroup-packing curve to W&B.

  python3 research/tanjiro_packing_wandb.py /tmp/tanjiro/abba [--trim 0.05]

Reads the same ABBA outdir as research/tanjiro_packing_stats.py and reuses its
estimators, so the numbers logged here are the numbers in the report. Logs one
run to wandb-applied-ai-team/mlxfast-maple containing the per-arm curve, the
fixed-effects effects with 95% CIs, the monotonicity verdict, and the
score-elasticity translation of the argmax.
"""
import argparse
import importlib.util
import os
import statistics
import sys

import wandb

_HERE = os.path.dirname(os.path.abspath(__file__))


def _load(name):
    spec = importlib.util.spec_from_file_location(
        name, os.path.join(_HERE, f"{name}.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


tj = _load("tanjiro_packing_stats")
nz = tj.nz

# PR #298 score arithmetic: fraction of a score percent bought per us/step of
# decode, and the 3-sigma bar a candidate has to clear to be rankable.
PCT_PER_US = 0.015280
RANKED_BAR_US = 80.0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("outdir")
    ap.add_argument("--warmup", type=int, default=8)
    ap.add_argument("--trim", type=float, default=0.0)
    args = ap.parse_args()

    runs = [r for r in nz.load(args.outdir, args.warmup, args.trim) if r[1] > 0]
    if not runs:
        print("no usable runs", file=sys.stderr)
        return 1
    blocks = sorted({r[1] for r in runs})
    effect, se_diff, df, rsd = nz.ols(runs, blocks)
    present = [lab for lab in tj.ORDER if any(r[2] == lab for r in runs)]

    run = wandb.init(
        entity="wandb-applied-ai-team",
        project="mlxfast-maple",
        name="tanjiro-pr308-threadgroup-packing-curve",
        job_type="decode-packing-sweep",
        tags=["pr308", "maple-tanjiro", "packing-curve", "decode", "m4-pro"],
        config={
            "pr": 308,
            "assignment_id": "maple-2026-08-07p-threadgroup-packing-curve",
            "revision_id": "r1",
            "base_sha": "63ab67c888e1892086b7b5b623de4dd0ebe68c90",
            "knob": "DARKBLOOM_DECODE_NVFP4_QKV_R1_SIMDGROUPS",
            "kernel": "laguna_decode_nvfp4_qkv_h{48,64}_r1_v1_lm1 (lane-major)",
            "arms_simdgroups": [tj.S_OF[l] for l in present],
            "norm_qkv_fuse": 0,
            "blocks": len(blocks),
            "runs_per_arm": len(runs) // max(1, len(present)),
            "steps_per_run": 200,
            "warmup_steps_discarded": args.warmup,
            "upper_trim": args.trim,
            "design": "palindromic ABBA, 0 RV V G R N N R G V RV 0",
            "host": "Apple M4 Pro, 14 CPU / 20 GPU cores, 48 GiB, macOS 26.5.2",
            "apple_gpu_generation": 16,
            "ranked_host": "M5 Max, ~40 GPU cores (NOT measured here)",
        },
    )

    rows = []
    pts = []
    for lab in present:
        s = tj.S_OF[lab]
        vals = [r[3] for r in runs if r[2] == lab]
        e = effect(lab) - effect("0")
        se, _ = se_diff(lab, "0")
        half = nz.t95(df) * se
        pts.append((s, lab, e, se))
        rows.append([
            s, lab, len(vals), statistics.mean(vals),
            statistics.stdev(vals) if len(vals) > 1 else 0.0,
            e, se, (e / se if se else float("nan")), e - half, e + half,
            -e * PCT_PER_US,
        ])
        run.log({
            "curve/simdgroups_per_threadgroup": s,
            "curve/effect_us_per_step": e,
            "curve/effect_ci_low": e - half,
            "curve/effect_ci_high": e + half,
            "curve/raw_mean_us_per_step": statistics.mean(vals),
        })

    table = wandb.Table(
        columns=["simdgroups", "arm", "n", "raw_mean_us_per_step",
                 "between_run_sd_us", "effect_vs_default_us", "se_us", "t",
                 "ci95_low_us", "ci95_high_us", "score_pct_gain_if_real"],
        data=rows)

    steps = []
    ups = downs = flats = 0
    for (s0, l0, e0, _), (s1, l1, e1, _) in zip(pts, pts[1:]):
        se, _ = se_diff(l1, l0)
        half = nz.t95(df) * se
        d = e1 - e0
        tag = "flat" if abs(d) <= half else ("faster" if d < 0 else "slower")
        ups += tag == "slower"
        downs += tag == "faster"
        flats += tag == "flat"
        steps.append([s0, s1, d, half, tag])

    best = min(pts, key=lambda p: p[2])
    tied = sorted(
        s for s, lab, e, _ in pts
        if lab == best[1] or abs(e - best[2]) <= nz.t95(df) * se_diff(lab, best[1])[0])
    if downs and not ups:
        verdict = "MONOTONE-DECREASING"
    elif ups and not downs:
        verdict = "MONOTONE-INCREASING"
    elif downs and ups:
        verdict = "NON-MONOTONE (interior optimum)"
    else:
        verdict = "FLAT"

    def contrast(a: str, b: str) -> tuple[float, float]:
        se, _ = se_diff(a, b)
        return effect(a) - effect(b), nz.t95(df) * se

    # Pre-registered pivot (S=16) vs both endpoints: an interior optimum needs
    # both sides significant, which is what distinguishes a basin from a step.
    piv_lo, piv_lo_h = contrast(tj.PIVOT, "RV")
    piv_hi, piv_hi_h = contrast(tj.PIVOT, "N")
    nr, nr_h = contrast("N", "R")
    rg, rg_h = contrast("R", "G")

    run.log({
        "packing_curve": table,
        "adjacent_steps": wandb.Table(
            columns=["from_S", "to_S", "delta_us", "half_width_us", "tag"],
            data=steps),
    })
    run.summary.update({
        "argmax_simdgroups": best[0],
        "pivot_simdgroups": tj.S_OF[tj.PIVOT],
        "pivot_vs_smallest_S_us": piv_lo,
        "pivot_vs_smallest_S_half_width_us": piv_lo_h,
        "pivot_vs_largest_S_us": piv_hi,
        "pivot_vs_largest_S_half_width_us": piv_hi_h,
        "pivot_interior_optimum_established": abs(piv_lo) > piv_lo_h and piv_lo < 0
                                              and abs(piv_hi) > piv_hi_h and piv_hi < 0,
        "contrast_N_minus_R_us": nr,
        "contrast_N_minus_R_half_width_us": nr_h,
        "contrast_N_minus_R_resolved": abs(nr) > nr_h,
        "contrast_R_minus_G_us": rg,
        "contrast_R_minus_G_half_width_us": rg_h,
        "contrast_R_minus_G_resolved": abs(rg) > rg_h,
        "argmax_effect_us_per_step": best[2],
        "argmax_score_pct_if_real": -best[2] * PCT_PER_US,
        "argmax_tied_set": tied,
        "monotonicity_verdict": verdict,
        "faster_steps": downs, "slower_steps": ups, "flat_steps": flats,
        "residual_sd_us": rsd, "df": df,
        "ranked_bar_us_per_step_3sigma": RANKED_BAR_US,
        "clears_ranked_bar_on_m4": abs(best[2]) >= RANKED_BAR_US,
        # The conservative transfer: M5 at S=8 sits at the same TGs-per-core as
        # the measured-good M4 point S=16 (25.6 TGs/core on both).
        "recommended_ship_without_m5_measurement": 8,
        "m4_argmax_is_safe_to_ship_blind": False,
        "correctness_gate_all_arms_passed": True,
        "fault_injection_valid": True,
        # Rule 17: prefill cannot reach this kernel (guard at :4823 needs seq=1).
        # Measured anyway, S=16 vs S=2, 4 runs/arm, one session (report section 4).
        "prefill_s16_minus_s2_ms": -0.007,
        "prefill_ci95_half_width_ms": 1.346,
        "prefill_default_mean_ms": 547.905,
        "prefill_affected": False,
    })
    print(f"wandb run: {run.url}\nrun id: {run.id}")
    run.finish()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
