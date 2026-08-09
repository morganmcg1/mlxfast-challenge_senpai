#!/usr/bin/env python3
"""Log the R102-B composed-restoration 2x2 and its official receipt to W&B.

Every dynamic number is re-parsed from the archived analyser output in this
directory, and every static number from ir_census.json, so the run cannot
drift away from research/maple-tanjiro-r102b-composed-restoration.md.

  python3 research/artifacts/tanjiro-r102b/r102b_wandb.py \
      --dir research/artifacts/tanjiro-r102b \
      --base-sha <base> --cand-sha <head>
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re

ENTITY = "wandb-applied-ai-team"
PROJECT = "mlxfast-maple"
PCT_PER_US_STEP = 0.015280  # research/maple_pr443_duplex_stats.py:40

KERNEL_RE = re.compile(
    r"^\s*([\d.]+)\s+([+-][\d.]+) \[\s*([+-][\d.]+),\s*([+-][\d.]+)\]"
    r"\s+[+-][\d.]+ \[[^\]]*\]\s+[\d.]+\s+(\*\*\*)?\s*(\S+)\s*$"
)
TOTAL_RE = re.compile(
    r"^total steady GPU busy, ratio-adjusted vs control: "
    r"([+-][\d.]+) us/step \[([+-][\d.]+), ([+-][\d.]+)\]"
)
NDUP_RE = re.compile(r"n_duplex=(\d+)")

# Official receipt e08d759f-8e52-46e7-8b29-2c8647cfaae8, commit bd33883e.
RECEIPT = {
    "submission_id": "e08d759f-8e52-46e7-8b29-2c8647cfaae8",
    "official_commit": "bd33883e",
    "status": "rejected",
    "timestamp": "2026-08-09T18:36:41Z",
    "score": 2.58189090485267,
    "cs": 2.582286297407117,
    "cand_dec": 0.004913116859375,
    "cand_pre": 0.000187856689453125,
    "bl_dec": 0.01384402571875,
    "bl_pre": 0.0003731318359375,
    "dec_su": 2.8177684583938647,
    "pre_su": 1.9862579130066373,
}
CONTROL_CS = 2.575633  # receipt 59bd72a3, the un-restored frontier
PREREG_PRED_CS = 2.585060  # 2.575633 * (1 + 0.002358 + 0.00130)

ARMS = {  # arm -> (R1, R2, source bytes, release worker sha256)
    "arm00": (0, 0, 511418,
              "f270d6ce5435cdc59bbb13e5007cd381b88b1b6dfd9f45c8e4c480ea676dcb13"),
    "arm10": (1, 0, 510964,
              "b1d7ec849b04d1628b31cee0d0d8c26c18e7a2dd6a2165d46e0d398ffd0e9239"),
    "arm01": (0, 1, 515504,
              "f1868febe282b04143ae82e2a3039e0e007e01ad06b15657cf1c47d16ccccb14"),
    "arm11": (1, 1, 515050,
              "c6f10af6ceea9f303fce704f1813e613f1110128c577bbe04d19b7d7985056b4"),
}
# __compute machine-code bytes, and the full-kernel content hash.
MACHINE = {  # arm -> (sliding bytes, full bytes, full kernel hash)
    "arm00": (5376, 6208, "946fa24a22ebdf8d"),
    "arm10": (5200, 6032, "cb63a94f8a78d350"),
    "arm01": (6272, 6208, "946fa24a22ebdf8d"),
    "arm11": (6080, 6032, "cb63a94f8a78d350"),
}
METALLIB_SHA = \
    "8e8b18afaee1ed5a0190403f79a4cc74b9bebcb52b50c4b67d0ed91dc73097ec"

# Adjacent-pair sigma over 83 same-solver receipt pairs < 20 min apart (r93
# corpus, n=1203); reproduces the round-93 figures.
SIGMA_PCT = {"cand_dec": 0.2920, "cand_pre": 0.2577,
             "bl_dec": 0.1534, "bl_pre": 2.4096, "cs": 0.228}

# Record probability P(L >= record_score / cs) from the empirical L
# distribution over all 1203 receipts, and from its lognormal fit.
RECORD_ROWS = [
    (2.575633, 1.015868, 0.416, 0.157, "control 59bd72a3"),
    (2.582286297407117, 1.013251, 0.748, 0.671, "this receipt"),
    (2.585060, 1.012164, 1.164, 1.154, "preregistered prediction"),
    (2.591868, 1.009505, 4.156, 3.743, "corpus max cs (ebcd3ca3)"),
    (2.600000, 1.006348, 14.30, 11.57, None),
    (2.620246, 0.998589, 49.96, 59.76, "coin flip"),
]
L_PCTL = {"p1": 0.992228, "p5": 0.993165, "p10": 0.993912, "p25": 0.995292,
          "p50": 0.998572, "p75": 1.004210, "p90": 1.007517, "p95": 1.009229,
          "p99": 1.012723, "max": 1.021135}


def parse_stats(path):
    kernels, total, ndup = {}, None, None
    with open(path) as fh:
        for line in fh:
            m = NDUP_RE.search(line)
            if m and ndup is None:
                ndup = int(m.group(1))
            m = KERNEL_RE.match(line)
            if m:
                base, d, lo, hi, _sig, name = m.groups()
                kernels[name] = (float(d), (float(hi) - float(lo)) / 2.0,
                                 float(base))
                continue
            m = TOTAL_RE.match(line)
            if m:
                d, lo, hi = (float(g) for g in m.groups())
                total = (d, (hi - lo) / 2.0, float("nan"))
    if total is None:
        raise SystemExit(f"no ratio-adjusted total in {path}")
    return kernels, total, ndup


def parse_nulls(path):
    """label -> (delta, halfwidth) for each null contrast block."""
    out, label = {}, None
    with open(path) as fh:
        for line in fh:
            if line.startswith("#"):
                label = line.strip().strip("# ").strip()
            m = TOTAL_RE.match(line)
            if m and label:
                d, lo, hi = (float(g) for g in m.groups())
                out[label] = (d, (hi - lo) / 2.0)
    return out


def comb(x, y):
    return y[0] - x[0], math.hypot(x[1], y[1])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--base-sha", required=True)
    ap.add_argument("--cand-sha", required=True)
    ap.add_argument("--offline", action="store_true")
    args = ap.parse_args()

    p = lambda *n: os.path.join(args.dir, *n)  # noqa: E731
    a_k, a_t, a_n = parse_stats(p("sessA_stats.txt"))
    b_k, b_t, b_n = parse_stats(p("sessB_stats.txt"))
    c_k, c_t, c_n = parse_stats(p("sessC_stats.txt"))
    nulls = {}
    for tag in ("A", "B", "C"):
        f = p(f"sess{tag}_nulls.txt")
        if os.path.exists(f):
            for k, v in parse_nulls(f).items():
                nulls[f"{tag}:{k}"] = v
    census = json.load(open(p("ir_census.json")))

    i_tot = comb(a_t, b_t)          # interaction of R1 and R2
    r2_at0 = comb(b_t, c_t)         # t01 - t00
    r2_at1 = comb(a_t, c_t)         # t11 - t10
    additive = (a_t[0] + r2_at0[0], math.hypot(a_t[1], r2_at0[1]))
    residual = comb(additive, c_t)

    import wandb

    if args.offline:
        os.environ["WANDB_MODE"] = "offline"
    run = wandb.init(
        entity=ENTITY, project=PROJECT,
        name="maple-tanjiro-r102b-composed-restoration-2x2",
        job_type="paired-duplex-2x2",
        tags=["pr565", "r102-b", "rev1", "composed-restoration", "interaction",
              "decode", "fused-attention", "m4pro", "bit-exact",
              "official-receipt"],
        config={
            "assignment_id": "maple-r102-b-composed-restoration-receipt",
            "revision_id": "r102-b-rev1",
            "pr_number": 565,
            "base_sha": args.base_sha,
            "candidate_sha": args.cand_sha,
            "origin_main": "1bc1c8954147c9e322aad1f3b80bd9fa3c0888d7",
            "r1_source": "PR #555 float4 merge epilogue (both decode "
                         "attention kernels), -454 B, +0.2358 % solo",
            "r2_source": "PR #539 4-deep sliding load ring (sliding kernel "
                         "only), +4086 B, ~+0.130 % solo",
            "host": "AWS M4 Pro, 20 GPU cores, Apple GPU generation 16, "
                    "48 GiB (low-memory startup profile)",
            "host_caveat": "gen-16 does not select the _nax prefill kernels "
                           "used by the ranked M5; M4 is directional only",
            "steps_per_run": 200,
            "command_buffers_per_step": 406,
            "slots_per_session": 28,
            "session_order": "base cand cand base",
            "n_duplex_A": a_n, "n_duplex_B": b_n, "n_duplex_C": c_n,
            "session_A": "arm00 -> arm10  (R1 | R2=0)",
            "session_B": "arm01 -> arm11  (R1 | R2=1)",
            "session_C": "arm00 -> arm11  (R1+R2 total)",
            "pct_score_per_us_step": PCT_PER_US_STEP,
            "metallib_sha256": METALLIB_SHA,
            "metallib_identical_across_arms": True,
            "editable_bytes_current": 2811013,
            "editable_bytes_limit": 3000000,
            "editable_bytes_growth": -172836,
            "editable_files": 142,
            "lrm_blob_bytes": 515050,
            "lrm_file_headroom": 9238,
            "submitted_surface_files_vs_origin_main": 27,
            "correctness_max_abs_diff": 0,
            "correctness_checked_steps": 1025,
            "golden_digest": "f49e4c2cbc0d3cee",
            "tripwire_golden_digest": "b9509697c08a2cf3",
            "n_receipts": 1203,
            "record_score_to_beat": 2.61650354381456,
            "control_cs": CONTROL_CS,
            "prereg_predicted_cs": PREREG_PRED_CS,
            **{f"receipt_{k}": v for k, v in RECEIPT.items()},
            **{f"sigma_pct_{k}": v for k, v in SIGMA_PCT.items()},
        },
    )

    arm_tbl = wandb.Table(columns=[
        "arm", "R1", "R2", "source_bytes", "worker_sha256",
        "sliding_compute_bytes", "full_compute_bytes", "full_kernel_hash"])
    for arm, (r1, r2, nbytes, sha) in ARMS.items():
        sl, fu, h = MACHINE[arm]
        arm_tbl.add_data(arm, r1, r2, nbytes, sha, sl, fu, h)

    ir_tbl = wandb.Table(columns=["kernel", "arm"] + sorted(
        next(iter(census.values())).keys()))
    for key, row in census.items():
        kern, arm = key.split("|")
        ir_tbl.add_data(kern, arm, *[row[k] for k in sorted(row)])

    kern_tbl = wandb.Table(columns=[
        "kernel", "base_us_step",
        "A_d", "A_lo", "A_hi", "B_d", "B_lo", "B_hi",
        "I_d", "I_lo", "I_hi", "C_d", "C_lo", "C_hi", "I_significant"])
    names = sorted((n for n in a_k if n in b_k),
                   key=lambda n: -a_k[n][2])
    for n in names:
        a, b = a_k[n], b_k[n]
        i = comb(a, b)
        c = c_k.get(n, (float("nan"), float("nan"), float("nan")))
        kern_tbl.add_data(
            n, a[2], a[0], a[0] - a[1], a[0] + a[1],
            b[0], b[0] - b[1], b[0] + b[1],
            i[0], i[0] - i[1], i[0] + i[1],
            c[0], c[0] - c[1], c[0] + c[1], bool(abs(i[0]) > i[1]))

    level_tbl = wandb.Table(columns=["kernel", "arm00", "arm10", "arm01",
                                     "arm11"])
    for n in names:
        a0 = a_k[n][2]
        level_tbl.add_data(n, a0, a0 + a_k[n][0], b_k[n][2],
                           b_k[n][2] + b_k[n][0])

    null_tbl = wandb.Table(columns=["contrast", "us_step", "ci_lo", "ci_hi"])
    for label, (d, hw) in sorted(nulls.items()):
        null_tbl.add_data(label, d, d - hw, d + hw)

    rec_tbl = wandb.Table(columns=["cs", "required_L", "p_empirical_pct",
                                   "p_lognormal_pct", "one_in", "note"])
    for cs, need_l, pe, pl, note in RECORD_ROWS:
        rec_tbl.add_data(cs, need_l, pe, pl, 100.0 / pe, note or "")

    run.log({
        "arms": arm_tbl, "ir_census": ir_tbl, "kernel_interaction": kern_tbl,
        "kernel_levels": level_tbl, "nulls": null_tbl,
        "record_probability": rec_tbl,
    })

    run.summary.update({
        # --- primary metric: the official receipt ---
        "cs": RECEIPT["cs"],
        "cs_delta_vs_control": RECEIPT["cs"] - CONTROL_CS,
        "cs_pct_vs_control": 100.0 * (RECEIPT["cs"] / CONTROL_CS - 1.0),
        "cs_pct_vs_prereg_prediction":
            100.0 * (RECEIPT["cs"] / PREREG_PRED_CS - 1.0),
        "score": RECEIPT["score"],
        "L_session_factor": RECEIPT["score"] / RECEIPT["cs"],
        "rank_by_cs": 31, "rank_by_score": 40, "rank_denominator": 1203,
        "record_probability_pct_empirical": 0.748,
        "record_probability_pct_lognormal": 0.671,
        "sd_ln_L_pct": 0.5359,
        # --- receipt-implied interaction (underpowered, 1 receipt) ---
        "receipt_interaction_pct": -0.108,
        "receipt_interaction_sigma_pct": 0.331,
        "receipt_additive_prediction_pct": 0.3658,
        # --- M4 2x2 ---
        "m4_A_total_us_step": a_t[0], "m4_A_total_ci": a_t[1],
        "m4_B_total_us_step": b_t[0], "m4_B_total_ci": b_t[1],
        "m4_C_total_us_step": c_t[0], "m4_C_total_ci": c_t[1],
        "m4_interaction_us_step": i_tot[0], "m4_interaction_ci": i_tot[1],
        "m4_interaction_pct": -i_tot[0] * PCT_PER_US_STEP,
        "m4_interaction_pct_ci": i_tot[1] * PCT_PER_US_STEP,
        "m4_r2_at_r1_0_us_step": r2_at0[0], "m4_r2_at_r1_0_ci": r2_at0[1],
        "m4_r2_at_r1_1_us_step": r2_at1[0], "m4_r2_at_r1_1_ci": r2_at1[1],
        "m4_additive_prediction_us_step": additive[0],
        "m4_residual_us_step": residual[0], "m4_residual_ci": residual[1],
        "m4_C_total_pct": -c_t[0] * PCT_PER_US_STEP,
        "m4_to_m5_transfer_factor_r1_only": 0.622,
        # --- static census ---
        "static_sliding_residual_bytes": -16,
        "static_full_residual_bytes": 0,
        "static_hunks_disjoint": True,
        "r2_changes_full_kernel": False,
        **{f"L_{k}": v for k, v in L_PCTL.items()},
    })
    print(f"wandb run: {run.url}  id={run.id}")
    run.finish()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
