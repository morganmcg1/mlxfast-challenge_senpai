#!/usr/bin/env python3
"""R125-D: publish the routed-down BN ladder evidence to W&B.

Logs the static AIR/byte census, the measured threadgroup-memory occupancy
ladder, the paired local A/B (decode-neutrality and correctness guard), and the
derived score prediction that uses the campaign's single transfer constant
(1.022 ms -> +0.378 %, i.e. 0.3699 %/ms at S = 97.863 ms) exactly once.

Research-only; not on editablePaths.
  python3 research/maple-tanjiro-r125d-wandb.py
"""
from __future__ import annotations

import csv
import json
import os
import statistics

import wandb

D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "artifacts", "tanjiro-r125d")

PCT_PER_MS = 0.378 / 1.022  # single campaign transfer constant
DOWN_MS = 14.42             # down-shape share of the routed gather-GEMM family
DRAM_FLOOR_MS = 10.51       # same bytes at 546.2 GB/s
BEST_RECEIPT = 2.60664970
CROWN = 2.61650354
SIGMA_PCT = 0.489


def occupancy_rows():
    rows = []
    with open(os.path.join(D, "occupancy-census.csv")) as fh:
        for r in csv.reader(fh):
            if len(r) == 5 and r[0].isdigit():
                rows.append(dict(threads_per_tg=int(r[0]), tg_bytes=int(r[1]),
                                 rep=int(r[2]), peak_resident_tgs=int(r[3]),
                                 elapsed_s=float(r[4])))
    return rows


def main():
    census = json.load(open(os.path.join(D, "air-census.json")))
    occ = occupancy_rows()
    ab_path = os.path.join(D, "paired-ab.json")
    ab = json.load(open(ab_path)) if os.path.exists(ab_path) else None

    run = wandb.init(
        entity="wandb-applied-ai-team",
        project="mlxfast-maple",
        name="r125d-routed-down-bn128",
        job_type="prefill-routed-down-bn",
        group="r125-d",
        config=dict(
            assignment_id="maple-r125-d-prefill-routed-down-bn",
            revision_id="r125-d-rev1",
            pr_number=732,
            branch="maple-tanjiro/r125-d-prefill-routed-down-bn",
            base_sha="a9de9e8f21188715f6d80ada4b581bcd50d4ec81",
            code_commit="965f2f4b",
            lever="darkbloom_expert_down_bn",
            candidate_bn=128,
            baseline_bn=64,
            shape="down K=512 N=2048 eg=256 bm=64 bk=64 wm=4 wn=1",
            host="Apple M4 Pro (Apple GPU gen 16, is_nax_available()==false)",
            kernel_reachable_locally=False,
            max_threadgroup_memory_bytes=32768,
            transfer_pct_per_ms=PCT_PER_MS,
            operating_point_S_ms=97.863,
            receipt_sigma_pct=SIGMA_PCT,
            best_receipt=BEST_RECEIPT,
            crown=CROWN,
        ),
    )

    ct = wandb.Table(columns=sorted({k for r in census.values() for k in r}))
    for key in ("down-bn32", "down-bn64", "down-bn128"):
        ct.add_data(*[census[key].get(c) for c in ct.columns])
    run.log({"air_census": ct})

    # Two SK stages are in flight per threadgroup, so in-flight staged weight
    # bytes per core = resident TGs/core * staged_bytes_per_sk_step * 2.
    ot = wandb.Table(columns=["bn", "tg_bytes", "n", "mean_resident_tgs", "sd",
                              "per_core", "staged_w_bytes_in_flight_per_core"])
    inflight = {}
    for tg, bn in ((4624, 32), (9232, 64), (18448, 128)):
        vals = [r["peak_resident_tgs"] for r in occ if r["tg_bytes"] == tg]
        mean = statistics.fmean(vals)
        per_core = mean / 20.0
        staged = per_core * census[f"down-bn{bn}"]["staged_bytes_per_sk_step"] * 2
        inflight[bn] = staged
        ot.add_data(bn, tg, len(vals), round(mean, 2),
                    round(statistics.stdev(vals), 2), round(per_core, 3),
                    int(round(staged)))
    run.log({"occupancy_ladder": ot})

    pool_ms = DOWN_MS - DRAM_FLOOR_MS
    gain = inflight[128] / inflight[64] - 1.0  # +0.44 bytes in flight
    pred = wandb.Table(columns=["eta", "delta_S_ms", "delta_score_pct",
                                "predicted_receipt"])
    for eta in (0.0, 0.25, 0.5, 0.75, 1.0):
        d_ms = -min(pool_ms, DOWN_MS - DOWN_MS / (1.0 + gain * eta))
        pct = -d_ms * PCT_PER_MS
        pred.add_data(eta, round(d_ms, 3), round(pct, 4),
                      round(BEST_RECEIPT * (1 + pct / 100.0), 6))
    run.log({"score_prediction": pred})

    summary = dict(
        down_shape_ms=DOWN_MS,
        dram_floor_ms=DRAM_FLOOR_MS,
        addressable_pool_ms=round(pool_ms, 3),
        central_delta_S_ms=-1.44,
        central_delta_score_pct=round(1.44 * PCT_PER_MS, 4),
        interval_delta_S_ms_low=-3.91,
        interval_delta_S_ms_high=2.00,
        interval_delta_score_pct_low=round(-2.00 * PCT_PER_MS, 4),
        interval_delta_score_pct_high=round(3.91 * PCT_PER_MS, 4),
        central_in_sigma=round(1.44 * PCT_PER_MS / SIGMA_PCT, 3),
        needed_pct_for_crown=round(100.0 * (CROWN / BEST_RECEIPT - 1.0), 4),
        w_bytes_per_layer_mb=census["down-bn128"]["w_bytes_per_layer_mb"],
        x_reread_saved_gb=round(census["down-bn64"]["x_reread_family_gb"]
                                - census["down-bn128"]["x_reread_family_gb"], 3),
        tgs_per_layer_candidate=census["down-bn128"]["tgs_per_layer"],
        tgs_per_layer_baseline=census["down-bn64"]["tgs_per_layer"],
        equivalence_exact_steps=8,
        equivalence_prefill_max_abs_logit_error=0.125,
        equivalence_tokens_matched="9/9",
    )

    if ab:
        for arm, bn in (("candidate", "128"), ("baseline", "64")):
            rows = ab[bn]
            for k in ("decode_seconds_per_token", "prefill_seconds_per_token",
                      "decode_speedup", "prefill_speedup"):
                summary[f"{arm}_{k}"] = statistics.fmean([r[k] for r in rows])
            summary[f"{arm}_passed_correctness"] = all(r["passed_correctness"] for r in rows)
            summary[f"{arm}_checked_steps"] = rows[0]["checked_steps"]
            summary[f"{arm}_max_abs_diff"] = max(r["max_abs_diff"] for r in rows)
            summary[f"{arm}_reps"] = len(rows)
        summary["decode_ratio_candidate_over_baseline"] = (
            summary["candidate_decode_seconds_per_token"]
            / summary["baseline_decode_seconds_per_token"])

    run.summary.update(summary)
    print(json.dumps(summary, indent=1, default=str))
    print(f"run_id={run.id} url={run.url}")
    run.finish()


if __name__ == "__main__":
    main()
