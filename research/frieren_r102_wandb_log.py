#!/usr/bin/env python3
"""Publish the R102-A rung-1 fixed-cost study to W&B.

    python3 research/frieren_r102_wandb_log.py

One run per measurement block carries its whole interleaved row sweep as a step
series keyed on the sweep index, so both the (K, N) grid and the within-round
duplicate-N null are plottable. One summary run carries both arms' gate
arithmetic, the wave law, the projected split scan for both shipped decode
grids, the held-out F2 test, and the rung-1 verdict.

The measurements themselves come from research/run_frieren_r102_fixed_cost.sh;
this script only reads its artifact logs and must never re-time anything.
"""
import json
import os
import statistics
import sys

import wandb

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from frieren_r102_fit import (CORES, T95, by_m, ks, linfit, load, ratio_ci,
                              waves, waves_c)

PROJECT = os.environ.get("WANDB_PROJECT", "mlxfast-maple")
ENTITY = os.environ.get("WANDB_ENTITY", "wandb-applied-ai-team")
TAGS = ["maple", "student:maple-frieren", "pr566", "r102-a", "split-k",
        "decode-attention"]

CALIB = ("R_sweep", "D_sweep", "M3D")
HELDOUT = ("F2", "F2D")
PRIMARY = ("FULL", "FULLD", "FZ", "FZD")
DENSE = ("FZ", "FZD")

SLIDING = "laguna_sliding_fused_attn_ring_v1"
FULLK = "laguna_full_fused_attn_grow_v1"

BLOCK_CFG = {
    "R_sweep": {"memory_mode": "resident", "slots": 1, "cache_copies": 1,
                "role": "calibration", "arm": "secondary_sliding",
                "kernel": SLIDING, "row_bound": "source_substitution"},
    "D_sweep": {"memory_mode": "slc_defeat", "slots": 48, "cache_copies": 64,
                "stride_kv": 32, "byte_matched": True, "role": "calibration",
                "arm": "secondary_sliding", "kernel": SLIDING,
                "row_bound": "source_substitution"},
    "M3D": {"memory_mode": "slc_defeat", "slots": 48, "cache_copies": 12,
            "stride_kv": 32, "byte_matched": False, "role": "calibration",
            "arm": "secondary_sliding", "kernel": SLIDING,
            "row_bound": "source_substitution",
            "diagonal": "sliding split emulation (32,512)(64,256)(128,128)"},
    "F2": {"memory_mode": "resident", "slots": 1, "cache_copies": 1,
           "role": "held_out", "arm": "secondary_sliding", "kernel": SLIDING,
           "row_bound": "source_substitution",
           "diagonal": "full-attention TG-count emulation (24,512)(48,256)"},
    "F2D": {"memory_mode": "slc_defeat", "slots": 48, "cache_copies": 12,
            "stride_kv": 32, "byte_matched": False, "role": "held_out",
            "arm": "secondary_sliding", "kernel": SLIDING,
            "row_bound": "source_substitution",
            "diagonal": "full-attention TG-count emulation (24,512)(48,256)"},
    "FULL": {"memory_mode": "resident", "slots": 1, "cache_copies": 1,
             "role": "primary", "arm": "primary_full", "kernel": FULLK,
             "row_bound": "params[1] (no source edit)",
             "grid": "N in {512,384,256,128,64}"},
    "FULLD": {"memory_mode": "slc_defeat", "slots": "48*512/N",
              "cache_copies": 96, "stride_kv": 32, "byte_matched": True,
              "role": "primary", "arm": "primary_full", "kernel": FULLK,
              "row_bound": "params[1] (no source edit)",
              "grid": "N in {512,384,256,128,64}"},
    "FZ": {"memory_mode": "resident", "slots": 1, "cache_copies": 1,
           "role": "primary_confirmatory", "arm": "primary_full",
           "kernel": FULLK, "row_bound": "params[1] (no source edit)",
           "grid": "N in {512..64 step 64} + 32 + 0"},
    "FZD": {"memory_mode": "slc_defeat", "slots": "48*512/N",
            "cache_copies": 96, "stride_kv": 32, "byte_matched": True,
            "role": "primary_confirmatory", "arm": "primary_full",
            "kernel": FULLK, "row_bound": "params[1] (no source edit)",
            "grid": "N in {512..64 step 64} + 32 + 0"},
}

# Shipped decode grids: heads/2 threadgroups of 1024 threads.
GRIDS = {"sliding": (32, 512), "full": (24, 576)}

# Gates the assignment sets, after the advisor's arm swap.
GATE_PRIMARY_PCT = 9.4       # full kernel, S=8 on C=40
GATE_PRIMARY_C20_PCT = 25.0  # full kernel, S=4 on C=20 (this host's optimum)
GATE_SECONDARY_PCT = 1.6     # sliding kernel, S=8 on C=40

COMMON = {
    "host": "m4pro-20core-48gb",
    "gpu_family": "applegpu_g16s",
    "gpu_cores": CORES,
    "resident_tgs_per_core": 1,
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


def sliding_gate_rows(blocks):
    """Secondary arm: f/tau0 per (block, K) from measured points only.

    The sliding kernel is 4-deep over BN=32, so M := N/128 and the M=0 point at
    N=96 is a direct measurement of the fixed cost.
    """
    out = []
    for tag, rows in blocks:
        for k in ks(rows):
            d = by_m(rows, k)
            if 4 not in d or 0 not in d:
                continue
            tau0 = d[4] - d[0]
            out.append({"block": tag, "K": k, "W": waves(k),
                        "T_N512_us": d[4], "f_direct_us": d[0],
                        "tau0_us": tau0, "f_over_tau0_pct": 100 * d[0] / tau0,
                        "gate_pct": GATE_SECONDARY_PCT,
                        "pass": 100 * d[0] / tau0 < GATE_SECONDARY_PCT})
    return out


def full_gate_rows(blocks, stat="med"):
    """Primary arm: affine tau(N) = f + c*N on the real full-attention kernel.

    Its main loop is 2-deep over BN=32, so one iteration retires 64 positions,
    u := 32c is one BN slice and a 512-position call carries tau0 = 16u of
    variable work. There is no reachable M=0 point on the five-point grid, so f
    is the fitted intercept; the dense grid adds a direct N=0 anchor.
    """
    out = []
    for tag, rows in blocks:
        for k in ks(rows):
            acc = {}
            for r in rows:
                if r["K"] == k and r["N"] >= 64:
                    acc.setdefault(r["N"], []).append(r[stat])
            pts = sorted(acc)
            if len(pts) < 3:
                continue
            ys = [statistics.fmean(acc[n]) for n in pts]
            fit = linfit([float(n) for n in pts], ys)
            tq = T95.get(fit["df"], 2.0)
            u = 32.0 * fit["slope"]
            tau0 = 16.0 * u
            lo, hi = ratio_ci(fit["icpt"], fit["se_icpt"], tau0,
                              512.0 * fit["se_slope"], tq)
            ratio = 100 * fit["icpt"] / tau0
            row = {"block": tag, "K": k, "n_points": len(pts),
                   "f_us": fit["icpt"], "f_ci95_us": tq * fit["se_icpt"],
                   "c_us_per_pos": fit["slope"], "u_us": u, "tau0_us": tau0,
                   "f_over_tau0_pct": ratio,
                   "f_over_tau0_lo_pct": 100 * lo,
                   "f_over_tau0_hi_pct": 100 * hi,
                   "r2": fit["r2"], "rmse_us": fit["rmse"],
                   "max_resid_us": max(abs(r) for r in fit["resid"]),
                   "gate_pct": GATE_PRIMARY_PCT,
                   "pass": ratio < GATE_PRIMARY_PCT}
            t0 = [r[stat] for r in rows if r["K"] == k and r["N"] == 0]
            t32 = [r[stat] for r in rows if r["K"] == k and r["N"] == 32]
            if t0:
                row["T_N0_direct_f_us"] = statistics.fmean(t0)
                row["direct_minus_fitted_f_us"] = \
                    statistics.fmean(t0) - fit["icpt"]
            if t32:
                row["T_N32_us"] = statistics.fmean(t32)
            out.append(row)
    return out


def direct_f_map(rows, tag, stat="med"):
    """Fixed cost per K with no fit, keyed by the block's reachable anchor.

    The dense blocks reach N=0 exactly; on the coarse blocks the lowest M=0
    point is the best available direct anchor. by_m() cannot be used on the
    dense blocks because N=32 and N=0 both land in M=0.
    """
    if tag in DENSE:
        out = {}
        for k in ks(rows):
            v = [r[stat] for r in rows if r["K"] == k and r["N"] == 0]
            out[str(k)] = statistics.fmean(v) if v else None
        return out
    return {str(k): by_m(rows, k).get(0) for k in ks(rows)}


def measured_gate_rows(blocks, stat="med"):
    """Primary gate with zero extrapolation: tau0 := T(512) - T(0)."""
    out = []
    for tag, rows in blocks:
        for k in ks(rows):
            def med(n):
                v = [r[stat] for r in rows if r["K"] == k and r["N"] == n]
                return statistics.fmean(v) if v else None
            t512, t0, t32 = med(512), med(0), med(32)
            if t512 is None or t0 is None:
                continue
            tau0 = t512 - t0
            ratio = 100 * t0 / tau0
            out.append({"block": tag, "K": k, "W": waves(k),
                        "T_N512_us": t512, "T_N0_us": t0, "T_N32_us": t32,
                        "tail_slope_us_per_pos":
                            None if t32 is None else (t32 - t0) / 32.0,
                        "tau0_us": tau0, "f_over_tau0_pct": ratio,
                        "gate_pct": GATE_PRIMARY_PCT,
                        "pass": ratio < GATE_PRIMARY_PCT})
    return out


def wave_projection(gate_rows, cores=40):
    """Split the measured N=0 anchor into a per-call and a per-threadgroup part.

    T(K,0) = a + W(K)*f_TG. With two K on a C=20 host this identifies both
    terms, so the C=40 fixed cost (W=1 for K=24) follows without re-measuring.
    """
    out = []
    by = {}
    for g in gate_rows:
        by.setdefault(g["block"], {})[g["K"]] = g
    for tag, d in by.items():
        if 24 not in d or 48 not in d:
            continue
        w24, w48 = waves(24), waves(48)
        f_tg = (d[48]["T_N0_us"] - d[24]["T_N0_us"]) / (w48 - w24)
        a = d[24]["T_N0_us"] - w24 * f_tg
        f40 = a + f_tg
        tau40 = d[24]["tau0_us"] / w24
        out.append({"block": tag, "a_us": a, "f_TG_us": f_tg,
                    "cores": cores, "f_at_C40_us": f40, "tau0_at_C40_us": tau40,
                    "f_over_tau0_pct_at_C40": 100 * f40 / tau40,
                    "gate_pct": GATE_PRIMARY_PCT,
                    "pass": 100 * f40 / tau40 < GATE_PRIMARY_PCT})
    return out


def full_makespan_scan(f, u, k, cores):
    """makespan(S) = ceil(K*S/C) * (f + (16/S)*u), merge dispatch excluded."""
    out, base = [], None
    for s in range(1, 9):
        w = waves_c(k * s, cores)
        t = w * (f + (16.0 / s) * u)
        if base is None:
            base = t
        out.append({"S": s, "K_total": k * s, "W": w, "makespan_us": t,
                    "delta_us": t - base, "ratio": t / base})
    return out


def dup_null_pct(rows):
    """Worst within-round duplicate-N spread in the block, in percent."""
    worst = 0.0
    acc = {}
    for r in rows:
        acc.setdefault((r["K"], r["N"]), []).append(r["med"])
    for v in acc.values():
        if len(v) > 1 and min(v) > 0:
            worst = max(worst, 100 * (max(v) - min(v)) / min(v))
    return worst


def sliding_split_scan(a, phi, t_ring512, cores, k, keys):
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
    prim = [(t, load(t)) for t in PRIMARY]
    blocks = calib + held + prim

    ids = []
    for tag, rows in blocks:
        cfg = dict(COMMON, block=tag, **BLOCK_CFG[tag])
        run = init("r102a-%s" % tag.lower(), "kernel_probe", cfg,
                   "R102-A rung 1, block %s" % tag)
        for i, r in enumerate(sorted(rows, key=lambda x: (x["K"], x["idx"]))):
            run.log({"K": r["K"], "W": waves(r["K"]), "N": r["N"], "M": r["M"],
                     "slots": r["slots"], "med_us": r["med"],
                     "min_us": r["min"], "mean_us": r["mean"],
                     "sd_us": r["sd"], "sweep_idx": r["idx"]}, step=i)
        gate = (full_gate_rows([(tag, rows)]) if tag in PRIMARY
                else sliding_gate_rows([(tag, rows)]))
        put(run, {"worst_dup_null_pct": dup_null_pct(rows),
                  "points": len(rows), "gate": gate,
                  "f_direct_us": direct_f_map(rows, tag)})
        ids.append(run.id)
        run.finish()

    # ---- secondary arm: sliding kernel ------------------------------------
    wm = wave_fit(calib)
    wm_all = wave_fit(calib + held)
    r20 = by_m([r for t, rows in calib if t == "R_sweep" for r in rows], 20)
    t_ring512 = r20[4] - r20[0]
    sgates = sliding_gate_rows(calib + held)
    sworst = max(g["f_over_tau0_pct"] for g in sgates)
    sbest = min(g["f_over_tau0_pct"] for g in sgates)

    scans = {}
    for cores in (40, CORES):
        for kind, (k, keys) in GRIDS.items():
            scans["C%d_%s" % (cores, kind)] = sliding_split_scan(
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

    # ---- primary arm: real full-attention kernel --------------------------
    pgates = full_gate_rows(prim)
    prod = [g for g in pgates if g["K"] == 24]
    # The measured-only gate is the headline: both terms are medians of the
    # same shared pipeline, so it survives the convexity that biases the fit.
    mgates = measured_gate_rows([b for b in prim if b[0] in DENSE])
    mprod = [g for g in mgates if g["K"] == 24]
    pworst = max(g["f_over_tau0_pct"] for g in mprod)
    pbest = min(g["f_over_tau0_pct"] for g in mprod)
    fworst = max(g["f_over_tau0_pct"] for g in prod)
    proj = wave_projection(mgates)
    projworst = max(p["f_over_tau0_pct_at_C40"] for p in proj)
    makespan = {}
    for g in prod:
        for cores in (40, CORES):
            makespan["%s_C%d" % (g["block"], cores)] = full_makespan_scan(
                g["f_us"], g["u_us"], 24, cores)

    # Direct S=2 threadgroup-count emulation on the real kernel: the gross
    # ratio before any merge dispatch is charged.
    direct_s2 = []
    for tag, rows in prim:
        def med(k, n):
            v = [r["med"] for r in rows if r["K"] == k and r["N"] == n]
            return statistics.fmean(v) if v else None
        b, s, t0 = med(24, 512), med(48, 256), med(24, 0)
        if b and s:
            direct_s2.append({"block": tag, "base_us": b, "split_us": s,
                              "gross_ratio": s / b,
                              "merge_floor_us": wm["a_us"],
                              "with_merge_us": s + wm["a_us"],
                              "net_ratio": (s + wm["a_us"]) / b,
                              "merge_est_us": t0,
                              "net_ratio_merge_est":
                                  None if t0 is None else (s + t0) / b})

    run = init("r102a-summary", "analysis",
               dict(COMMON, rungs_run="1", rungs_declined="2,3",
                    blocks=json.dumps(list(BLOCK_CFG)), receipts_spent=0),
               "R102-A rung 1 summary: split-invariant fixed cost of the "
               "decode attention kernel, both arms")
    put(run, {
        "primary_metric": pworst,
        "primary_metric_name": "f_over_tau0_pct_primary_arm_worst",
        "primary_arm_kernel": FULLK,
        "primary_f_over_tau0_pct_worst": pworst,
        "primary_f_over_tau0_pct_best": pbest,
        "primary_f_over_tau0_pct_worst_fitted": fworst,
        "primary_f_over_tau0_pct_worst_at_C40": projworst,
        "primary_gate_pct": GATE_PRIMARY_PCT,
        "primary_gate_c20_pct": GATE_PRIMARY_C20_PCT,
        "primary_verdict": "NO_GO" if pworst >= GATE_PRIMARY_PCT else "GO",
        "primary_gate_source": "measured T(512)-T(0), no extrapolation",
        "primary_measured_gate_table": mgates,
        "primary_wave_projection_c40": proj,
        "primary_gate_table": pgates,
        "primary_makespan_scan": makespan,
        "primary_direct_s2_emulation": direct_s2,
        "secondary_arm_kernel": SLIDING,
        "secondary_f_over_tau0_pct_worst": sworst,
        "secondary_f_over_tau0_pct_best": sbest,
        "secondary_gate_pct": GATE_SECONDARY_PCT,
        "secondary_verdict": "NO_GO" if sworst >= GATE_SECONDARY_PCT else "GO",
        "secondary_gate_table": sgates,
        "verdict": "NO_GO",
        "wave_a_us": wm["a_us"], "wave_a_ci95_us": wm["a_ci95_us"],
        "wave_phi_us": wm["phi_us"], "wave_phi_ci95_us": wm["phi_ci95_us"],
        "wave_r2": wm["r2"], "wave_rmse_us": wm["rmse_us"], "wave_n": wm["n"],
        "wave_refit_all": {k: v for k, v in wm_all.items() if k != "points"},
        "t_ring_512keys_us": t_ring512,
        "phi_over_t_ring_pct": 100 * wm["phi_us"] / t_ring512,
        "sliding_split_scan": scans,
        "heldout_f2": f2,
        "replicates_pr196": True,
        "pr196_f_over_tau0_pct": 52.6,
        "pr196_a_us": 1.661, "pr196_phi_us": 1.469, "pr196_f_us": 3.130,
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
