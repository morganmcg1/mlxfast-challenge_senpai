#!/usr/bin/env python3
"""Publish the R102-A rung-1 fixed-cost study to W&B.

    python3 research/frieren_r102_wandb_log.py

One run per measurement block carries its whole interleaved row sweep as a
step series keyed on the sweep index, so both the (K, N) grid and the
within-round duplicate-N null are plottable. One summary run carries the wave
law, the gate arithmetic, the projected split scan for both shipped decode
grids, the held-out F2 test, and the rung-1 verdict.

The measurements themselves come from research/run_frieren_r102_fixed_cost.sh;
this script only reads its artifact logs and must never re-time anything.
"""
import json
import os
import sys

import wandb

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from frieren_r102_fit import (CORES, T95, by_m, ks, linfit, load, waves)

PROJECT = os.environ.get("WANDB_PROJECT", "mlxfast-maple")
ENTITY = os.environ.get("WANDB_ENTITY", "wandb-applied-ai-team")
TAGS = ["maple", "student:maple-frieren", "pr566", "r102-a", "split-k",
        "decode-attention"]

CALIB = ("R_sweep", "D_sweep", "M3D")
HELDOUT = ("F2", "F2D")

BLOCK_CFG = {
    "R_sweep": {"memory_mode": "resident", "slots": 1, "cache_copies": 1,
                "role": "calibration"},
    "D_sweep": {"memory_mode": "slc_defeat", "slots": 48, "cache_copies": 64,
                "stride_kv": 32, "byte_matched": True, "role": "calibration"},
    "M3D": {"memory_mode": "slc_defeat", "slots": 48, "cache_copies": 12,
            "stride_kv": 32, "byte_matched": False, "role": "calibration",
            "diagonal": "sliding split emulation (32,512)(64,256)(128,128)"},
    "F2": {"memory_mode": "resident", "slots": 1, "cache_copies": 1,
           "role": "held_out",
           "diagonal": "full-attention split emulation (24,512)(48,256)"},
    "F2D": {"memory_mode": "slc_defeat", "slots": 48, "cache_copies": 12,
            "stride_kv": 32, "byte_matched": False, "role": "held_out",
            "diagonal": "full-attention split emulation (24,512)(48,256)"},
}

# Shipped decode grids: heads/2 threadgroups of 1024 threads.
GRIDS = {"sliding": (32, 512), "full": (24, 576)}

COMMON = {
    "host": "m4pro-20core-48gb",
    "gpu_family": "applegpu_g16s",
    "gpu_cores": CORES,
    "ranked_host": "m5max-40core-128gb",
    "ranked_gpu_cores": 40,
    "instrument": "fern_r100_attn_probe",
    "rounds_per_point": 21,
    "reps_per_round": 2000,
    "base_sha": "51e36805030a982daecda80535281f4540a1cde1",
    "pr": 566,
    "assignment_id": "maple-r102-a-splitk-decode-attention",
    "revision_id": "r102-a-rev1",
    "rung": 1,
    "submitted_surface_delta_bytes": 0,
}


def init(name, job_type, config, notes=""):
    wandb_dir = os.environ.get("WANDB_DIR", "/tmp/r102/wandb")
    os.makedirs(wandb_dir, exist_ok=True)
    return wandb.init(dir=wandb_dir, entity=ENTITY, project=PROJECT, name=name,
                      notes=notes, job_type=job_type, tags=TAGS, config=config,
                      reinit=True)


def put(run, mapping):
    for k, v in mapping.items():
        run.summary[k] = v if isinstance(v, (int, float, bool)) or v is None \
            else json.dumps(v)


def wave_fit(blocks):
    """f_direct(K) = a + W*phi over every M=0 point in the given blocks."""
    xs, ys, pts = [], [], []
    for tag, rows in blocks:
        for k in ks(rows):
            d = by_m(rows, k)
            if 0 not in d:
                continue
            xs.append(float(waves(k)))
            ys.append(d[0])
            pts.append({"block": tag, "K": k, "W": waves(k),
                        "f_direct_us": d[0]})
    fit = linfit(xs, ys)
    tq = T95.get(fit["df"], 2.0)
    return {"a_us": fit["icpt"], "a_ci95_us": tq * fit["se_icpt"],
            "phi_us": fit["slope"], "phi_ci95_us": tq * fit["se_slope"],
            "r2": fit["r2"], "rmse_us": fit["rmse"], "n": len(xs),
            "points": pts}


def gate_rows(blocks):
    """f/tau0 per (block, K) from measured points only."""
    out = []
    for tag, rows in blocks:
        for k in ks(rows):
            d = by_m(rows, k)
            if 4 not in d or 0 not in d:
                continue
            tau0 = d[4] - d[0]
            out.append({"block": tag, "K": k, "W": waves(k),
                        "T_N512_us": d[4], "f_direct_us": d[0],
                        "tau0_us": tau0, "f_over_tau0_pct": 100 * d[0] / tau0})
    return out


def dup_null_pct(rows):
    """Worst within-round duplicate-N spread in the block, in percent."""
    worst = 0.0
    acc = {}
    for r in rows:
        acc.setdefault((r["K"], r["N"]), []).append(r["med"])
    for v in acc.values():
        if len(v) > 1:
            worst = max(worst, 100 * (max(v) - min(v)) / min(v))
    return worst


def split_scan(a, phi, t_ring512, cores, k, keys):
    t_ring = t_ring512 * keys / 512.0
    out, base = [], None
    for s in (1, 2, 3, 4, 5, 6, 8, 10):
        w = -(-k * s // cores)
        t = a + w * phi + w * t_ring / s
        if base is None:
            base = t
        out.append({"S": s, "K_total": k * s, "W": w, "T_us": t,
                    "delta_us": t - base, "ratio": t / base})
    return out


def main() -> int:
    calib = [(t, load(t)) for t in CALIB]
    held = [(t, load(t)) for t in HELDOUT]
    blocks = calib + held

    ids = []
    for tag, rows in blocks:
        run = init("r102a-%s" % tag.lower(), "kernel_probe",
                   dict(COMMON, block=tag, **BLOCK_CFG[tag]),
                   "R102-A rung 1, block %s" % tag)
        for i, r in enumerate(sorted(rows, key=lambda x: (x["K"], x["idx"]))):
            run.log({"K": r["K"], "W": waves(r["K"]), "N": r["N"], "M": r["M"],
                     "slots": r["slots"], "med_us": r["med"],
                     "min_us": r["min"], "mean_us": r["mean"],
                     "sd_us": r["sd"], "sweep_idx": r["idx"]}, step=i)
        put(run, {"worst_dup_null_pct": dup_null_pct(rows),
                  "points": len(rows),
                  "f_direct_us": {str(k): by_m(rows, k).get(0)
                                  for k in ks(rows)},
                  "gate": gate_rows([(tag, rows)])})
        ids.append(run.id)
        run.finish()

    wm = wave_fit(calib)
    wm_all = wave_fit(blocks)
    r20 = by_m([r for t, rows in calib if t == "R_sweep" for r in rows], 20)
    t_ring512 = r20[4] - r20[0]
    gates = gate_rows(blocks)
    worst = max(g["f_over_tau0_pct"] for g in gates)
    best = min(g["f_over_tau0_pct"] for g in gates)

    scans = {}
    for cores in (40, CORES):
        for kind, (k, keys) in GRIDS.items():
            scans["C%d_%s" % (cores, kind)] = split_scan(
                wm["a_us"], wm["phi_us"], t_ring512, cores, k, keys)

    # Held-out prediction vs measurement on the one split the law says wins.
    f2 = []
    for tag, rows in held:
        bm = bp = None
        for s, k, n in ((1, 24, 512), (2, 48, 256)):
            hits = [r for r in rows if r["K"] == k and r["N"] == n]
            if not hits:
                continue
            m = sum(h["med"] for h in hits) / len(hits)
            pred = wm["a_us"] + waves(k) * (
                wm["phi_us"] + t_ring512 * hits[0]["M"] / 4.0)
            if bm is None:
                bm, bp = m, pred
            f2.append({"block": tag, "S": s, "K": k, "W": waves(k), "N": n,
                       "measured_us": m, "predicted_us": pred,
                       "pred_err_pct": 100 * (pred - m) / m,
                       "measured_ratio": m / bm, "predicted_ratio": pred / bp})

    s5 = next(x for x in scans["C40_sliding"] if x["S"] == 5)
    run = init("r102a-summary", "analysis",
               dict(COMMON, rungs_run="1", rungs_declined="2,3",
                    blocks=json.dumps(list(BLOCK_CFG)),
                    receipts_spent=0),
               "R102-A rung 1 summary: split-invariant fixed cost of the "
               "decode attention kernel")
    put(run, {
        "primary_metric": worst,
        "primary_metric_name": "f_over_tau0_pct_worst_arm",
        "f_over_tau0_pct_worst": worst,
        "f_over_tau0_pct_best": best,
        "gate_go_threshold_pct": 6.67,
        "gate_nogo_threshold_pct": 20.0,
        "verdict": "NO_GO",
        "gate_table": gates,
        "wave_a_us": wm["a_us"], "wave_a_ci95_us": wm["a_ci95_us"],
        "wave_phi_us": wm["phi_us"], "wave_phi_ci95_us": wm["phi_ci95_us"],
        "wave_r2": wm["r2"], "wave_rmse_us": wm["rmse_us"], "wave_n": wm["n"],
        "wave_refit_all": {k: v for k, v in wm_all.items() if k != "points"},
        "t_ring_512keys_us": t_ring512,
        "phi_over_t_ring_pct": 100 * wm["phi_us"] / t_ring512,
        "split_scan": scans,
        "s5_sliding_c40_ratio": s5["ratio"],
        "s5_sliding_c40_delta_us": s5["delta_us"],
        "heldout_f2": f2,
        "replicates_pr196": True,
        "pr196_f_over_tau0_pct": 52.6,
        "pr196_a_us": 1.661, "pr196_phi_us": 1.469,
        "probe_only_no_e2e": True,
        "submitted_surface_delta_bytes": 0,
        "block_run_ids": ids,
    })
    ids.append(run.id)
    run.finish()
    for i in ids:
        print("https://wandb.ai/%s/%s/runs/%s" % (ENTITY, PROJECT, i))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
