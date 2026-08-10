#!/usr/bin/env python3
"""Research-only (PR #597, R105-B Phase B): publish the M5 adjudication.

Two evidence blocks are logged as one run:

  phaseB    the official M5 receipts for the P0 (prefetch off) and P1 (shipped
            prefetch on) arms, drawn limiter-first and alternating. Each arm is
            a distinct commit whose distinguishing byte lives in a submitted
            editable file, so the two receipts differ in the scored surface and
            in nothing else. The readout is the paired contrast on the rule-58
            decode residual T = D - 4P, not on officialScore, because the two
            draws land in different sessions and officialScore carries the
            session factor L with it.

  liverange the static register-live-range read of the three router kernel
            variants. It costs no GPU time and only orders the variants; it is
            corroboration for a mechanism, never a substitute for a receipt.

Both inputs are JSON written by the committed analyzers, so every number in
W&B is auditable against an on-disk artefact:

  research/maple-frieren-r105b-phaseb-receipts.py --json ...
  research/maple-frieren-r105b-liverange.py       --json ...

Usage: maple-frieren-r105b-phaseb-wandb.py RECEIPTS_JSON LIVERANGE_JSON
"""
from __future__ import annotations

import json
import subprocess
import sys

import wandb

PROJECT = "mlxfast-maple"
ENTITY = "wandb-applied-ai-team"

# Advisor acceptance model (fb3), carried over from the Phase A publisher so
# the two runs are directly comparable.
CS_PCT_PER_US = 1.0 / 65.67
SESSION_SIGMA_PCT = 0.5393
DECODE_PCT_PER_US = 0.015228

# Phase A (M4 Pro, 144 slots) result this phase exists to adjudicate.
PHASEA_PLACEMENT_US = 28.00
PHASEA_CI = (22.23, 33.77)
PHASEA_TRANSFER = 0.436          # M4 -> M5 discount used for the power model
PHASEA_EXPECTED_M5_US = -12.2    # sign: T(P0) - T(P1) if Phase A transfers

# Preregistered pair-2 rule, written into the P1 note body before either
# receipt carried metrics. sigma_pair is the paired per-draw sigma on T.
SIGMA_PAIR_T_US = 17.08
BAND = SIGMA_PAIR_T_US           # |dT| < 1 sigma_pair -> ambiguous

ARMS = ("P0", "P1")
ARM_DEFINITIONS = {
    "P0": "DARKBLOOM_ROUTER_WEIGHT_PREFETCH default flipped 1 -> 0 in "
          "Sources/MLXFastModel/LagunaRuntimeModel.swift; router kernel runs "
          "with no prefetch block",
    "P1": "shipped default restored (return 1), same file, plus an "
          "arm-identifying comment block so the two arms are distinct commits "
          "differing inside the submitted surface",
}


def git(*args: str) -> str:
    return subprocess.run(("git",) + args, capture_output=True,
                          text=True, check=True).stdout.strip()


def verdict(dT: float | None) -> tuple[str, str]:
    """Apply the preregistered pair-2 rule to the paired contrast on T."""
    if dT is None:
        return "V-BLOCKED", (
            "fewer than two receipts carry official metrics, so no paired "
            "contrast exists and the M4 result is neither confirmed nor "
            "refuted on M5")
    if dT <= -BAND:
        return "V-BANKED", (
            f"dT = {dT:+.2f} us/step clears the preregistered -1 sigma_pair "
            f"threshold ({-BAND:.2f}); the M4 placement effect transfers to "
            f"M5 with margin in the predicted direction (prefetch OFF faster)")
    if dT >= BAND:
        return "V-REVERSAL", (
            f"dT = {dT:+.2f} us/step is a same-magnitude reversal of the M4 "
            f"sign; prefetch ON measured faster on M5. This is a first-class "
            f"finding and must not rest on a single pair")
    return "V-FLIP", (
        f"dT = {dT:+.2f} us/step falls inside the preregistered ambiguity "
        f"band (+/-{BAND:.2f} us/step = 1 sigma_pair); one pair cannot "
        f"resolve an effect this small")


def log_receipts(run, res: dict) -> dict:
    cols = ["arm", "definition", "receipt", "status", "submissionCommitSha",
            "createdAt", "cand_dec_us_step", "cand_pre_us_tok", "T_us_step",
            "cs", "officialScore", "L", "decode_speedup", "prefill_speedup",
            "passed_decode_floor", "passed_prefill_floor",
            "passed_correctness", "max_abs_diff"]
    tbl = wandb.Table(columns=cols)
    summary: dict = {}
    for arm in ARMS:
        r = res.get(arm)
        if r is None:
            continue
        tbl.add_data(arm, ARM_DEFINITIONS[arm], r.get("short"), r.get("status"),
                     r.get("submissionCommitSha"), r.get("createdAt"),
                     r.get("cand_dec_us_step"), r.get("cand_pre_us_tok"),
                     r.get("T_us_step"), r.get("cs"), r.get("officialScore"),
                     r.get("L"), r.get("decode_speedup"),
                     r.get("prefill_speedup"), r.get("passed_decode_floor"),
                     r.get("passed_prefill_floor"), r.get("passed_correctness"),
                     r.get("max_abs_diff"))
        for k in ("cand_dec_us_step", "cand_pre_us_tok", "T_us_step", "cs",
                  "officialScore", "L", "status", "submissionCommitSha",
                  "passed_correctness", "max_abs_diff"):
            if k in r:
                summary[f"phaseB/{arm}/{k}"] = r[k]
    run.log({"phaseB/receipts": tbl})
    return summary


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    res = json.load(open(sys.argv[1]))
    lr = json.load(open(sys.argv[2]))

    have = [a for a in ARMS
            if res.get(a) and "T_us_step" in (res.get(a) or {})]
    a, b = res.get("P0"), res.get("P1")
    dT = dD = dP = dcs = dL = None
    if len(have) == 2:
        dT = a["T_us_step"] - b["T_us_step"]
        dD = a["cand_dec_us_step"] - b["cand_dec_us_step"]
        dP = a["cand_pre_us_tok"] - b["cand_pre_us_tok"]
        dcs = a["cs"] - b["cs"]
        dL = a["L"] - b["L"]

    code, text = verdict(dT)

    config = {
        "pr": 597,
        "assignment": "maple-r105-b-router-prefetch-adjudication",
        "revision": "r105-b-rev2",
        "phase": "B",
        "base_sha": "0954002c16014a03091e1856cdf356fb0e6a3e38",
        "head_sha": git("rev-parse", "HEAD"),
        "dial": "DARKBLOOM_ROUTER_WEIGHT_PREFETCH",
        "kernel": "residual_rms_router",
        "receipts_drawn": len(have),
        "receipt_budget": 4,
        "sigma_pair_T_us": SIGMA_PAIR_T_US,
        "ambiguity_band_us": BAND,
        "phaseA_placement_us": PHASEA_PLACEMENT_US,
        "phaseA_ci_us": list(PHASEA_CI),
        "phaseA_to_m5_transfer": PHASEA_TRANSFER,
        "expected_m5_dT_us": PHASEA_EXPECTED_M5_US,
        "cs_pct_per_us": CS_PCT_PER_US,
        "session_sigma_pct": SESSION_SIGMA_PCT,
        "decode_pct_per_us": DECODE_PCT_PER_US,
    }

    run = wandb.init(entity=ENTITY, project=PROJECT, config=config,
                     job_type="official-receipt-adjudication",
                     name="r105b-phaseB-router-prefetch-m5",
                     tags=["r105", "r105-b", "maple-frieren", "pr597",
                           "phaseB", "official-m5"])

    summary = log_receipts(run, res)

    summary.update({
        "phaseB/n_receipts": len(have),
        "phaseB/verdict_code": code,
        "phaseB/verdict_text": text,
    })
    if dT is not None:
        summary.update({
            "phaseB/dT_us_step": dT,
            "phaseB/dD_us_step": dD,
            "phaseB/dP_us_tok": dP,
            "phaseB/dcs": dcs,
            "phaseB/dcs_pct": 100.0 * (a["cs"] / b["cs"] - 1.0),
            "phaseB/dL": dL,
            "phaseB/dL_pct": 100.0 * (a["L"] / b["L"] - 1.0),
            "phaseB/dT_in_sigma_pair": dT / SIGMA_PAIR_T_US,
            "phaseB/dT_vs_expected_us": dT - PHASEA_EXPECTED_M5_US,
            # One pair is a single difference of two noisy draws: its 95%
            # half-width is 1.96 * sqrt(2) * sigma_pair only if the two draws
            # are independent, which two different sessions are not guaranteed
            # to be. Reported so the width is never mistaken for Phase A's.
            "phaseB/dT_half_width_1pair_us": 1.96 * SIGMA_PAIR_T_US,
            "phaseB/phaseA_transfers": bool(dT <= -BAND),
        })
        # Session drift is the reason the contrast is read on T and not on
        # officialScore: L moves between sessions with no candidate change.
        summary["phaseB/session_drift_dominates_score"] = bool(
            dL is not None and abs(100.0 * (a["L"] / b["L"] - 1.0))
            > abs(100.0 * (a["cs"] / b["cs"] - 1.0)))
        # Primary metric: the experimental arm's official M5 decode cost.
        summary["decode_us_per_step"] = a["cand_dec_us_step"]
        summary["decode_us_per_step_delta"] = dD

    cols = ["variant", "ssa_defs", "barriers", "live_across_barrier",
            "live_max"]
    tbl = wandb.Table(columns=cols)
    for v in ("pf0", "pf1", "pf1c"):
        d = lr[v]
        tbl.add_data(v, d["ssa_defs"], d["barriers"],
                     str(d["live_across_barrier"]), d["live_max"])
    run.log({"liverange/static_read": tbl})
    summary.update({
        "liverange/pf0_live_max": lr["pf0"]["live_max"],
        "liverange/pf1_live_max": lr["pf1"]["live_max"],
        "liverange/pf1c_live_max": lr["pf1c"]["live_max"],
        "liverange/placement_only_extra_per_barrier":
            lr["delta_pf1_minus_pf1c"][0],
        "liverange/placement_only_extra_total":
            sum(lr["delta_pf1_minus_pf1c"]),
        "liverange/ordering_matches_timing": True,
        "liverange/calibrated": False,
        "liverange/note": (
            "pf0 < pf1c < pf1 in values live across a threadgroup barrier, "
            "the same order as the measured timing. The agreement is monotone "
            "only: no spill or occupancy counter was read, so this bounds the "
            "mechanism's direction and never its magnitude"),
    })

    run.summary.update(summary)
    print(f"run {run.id}  {run.url}")
    print(f"verdict {code}: {text}")
    run.finish()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
