#!/usr/bin/env python3
"""r105-E A1: per-family achieved-bandwidth ledger for the decode step.

Joins three independent sources:
  * byte census      research/artifacts/fern-r105d/decode-byte-census.json
  * M4 SPLIT=1 label PR #488 profile (provenance next to LABEL_US_M4 below)
  * pattern ceiling  research/artifacts/fern-r105e/pattern-bandwidth.json (A3)

Emits research/artifacts/fern-r105e/family-bandwidth-ledger.csv.

Reproduce:  python3 research/fern_r105e_ledger.py
"""
import csv
import json
import math
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CENSUS = os.path.join(ROOT, "research/artifacts/fern-r105d/decode-byte-census.json")
PATTERN = os.path.join(ROOT, "research/artifacts/fern-r105e/pattern-bandwidth.json")
OUT = os.path.join(ROOT, "research/artifacts/fern-r105e/family-bandwidth-ledger.csv")

RULE80_GBS = 266.3        # M4 Pro reference constant used by the assignment
M5_PEAK_GBS = 610.0       # M5 Max reference constant used by the assignment
M4_CORES = 20             # this host
M5_CORES = 40             # ranked host
EXTRACTION = 263.121 / RULE80_GBS   # A3-measured M4 extraction of its constant
US_PER_PCT_CS = 65.67     # 1 % of composite score, in M5 decode us/step

# M4 Pro (applegpu_g16s, 20 GPU cores) per-step label sums, DARKBLOOM_GPU_PROFILE_SPLIT=1.
# Rows 1-17: research/fern_r105d_bytes.py:142-155 (PR #488, decode_probe.py --steps 80).
# Rows 18-24: research/maple-nezuko-r92-barrier-hoist-generalization.md:94-100 (same run).
# vn_copy is absent from that census and is therefore null here.
LABEL_US_M4 = {
    "routed_nvfp4_swiglu_qmv_packed_top8keys": 1497.7,
    "nvfp4_qkv_h64": 1340.1,
    "oproj_act_h64": 1117.7,
    "routed_shared_nvfp4_down_residual": 858.9,
    "sliding_fused_attn_ring": 636.0,
    "lmhead_int5_base_coarse_delta": 420.3,
    "nvfp4_qkv_h48": 362.8,
    "residual_rms_router": 312.8,
    "oproj_act_h48": 301.8,
    "shared_nvfp4_swiglu_qmv_rows1_halved": 287.1,
    "dense_gate_up_swiglu": 269.4,
    "gate_sp_h64": 248.0,
    "full_fused_attn_grow": 229.7,
    "prefill_router_tournament": 185.5,
    "rmsbfloat16": 141.9,
    "dense_down_residual": 133.8,
    "gate_sp_h48": 80.2,
    "lmhead_exact_fused_int5_sparse_refine": 77.0,
    "argmax": 9.0,
    "lmhead_exact_winner": 4.7,
    "lmhead_coarse_argmax_stage1": 4.1,
    "embedding_rope_atlas": 3.5,
    "gather_front": 3.4,
    "residual_rms_bf16_2048_v1": 2.9,
}

# Per-dispatch launch geometry, grid expressed in THREADS.
# Extracted from /tmp/r105c/dump/a_base/dispatch.tsv (columns grid, threadgroup).
GEOMETRY = {
    "routed_nvfp4_swiglu_qmv_packed_top8keys": (131072, 64),
    "nvfp4_qkv_h64": (327680, 64),
    "nvfp4_qkv_h48": (262144, 64),
    "oproj_act_h64": (16384, 64),
    "oproj_act_h48": (16384, 64),
    "routed_shared_nvfp4_down_residual": (147456, 288),
    "shared_nvfp4_swiglu_qmv_rows1_halved": (16384, 64),
    "lmhead_int5_base_coarse_delta": (3211264, 512),
    "lmhead_exact_fused_int5_sparse_refine": (802816, 256),
    "dense_gate_up_swiglu": (65536, 512),
    "dense_down_residual": (16384, 128),
    "sliding_fused_attn_ring": (32768, 1024),
    "full_fused_attn_grow": (24576, 1024),
    "residual_rms_router": (16384, 512),
    "gate_sp_h64": (512, 64),
    "gate_sp_h48": (384, 64),
    "lmhead_coarse_argmax_stage1": (28672, 224),
    "vn_copy": (131072, 1024),
    "rmsbfloat16": (512, 512),
    "gather_front": (1, 1),
    "residual_rms_bf16_2048_v1": (512, 512),
    "embedding_rope_atlas": (512, 512),
    "argmax": (1024, 1024),
    "lmhead_exact_winner": (32, 32),
    "prefill_router_tournament": (256, 256),
}


def occupancy_curve(pattern_json):
    """Best measured streaming GB/s versus total grid threads on this 20-core M4."""
    best = {}
    for m in pattern_json["measurements"]:
        if m["pattern"] not in ("stream", "stream_tg64"):
            continue
        g = m["grid_threads"]
        best[g] = max(best.get(g, 0.0), m["achieved_gbs"])
    return sorted(best.items())


def curve_gbs(grid_threads, curve):
    """Piecewise-linear in log2(threads); linear below the first measured knee."""
    lo_g, lo_b = curve[0]
    if grid_threads <= lo_g:
        return lo_b * grid_threads / lo_g
    for (g0, b0), (g1, b1) in zip(curve, curve[1:]):
        if grid_threads <= g1:
            t = (math.log2(grid_threads) - math.log2(g0)) / (math.log2(g1) - math.log2(g0))
            return b0 + t * (b1 - b0)
    return curve[-1][1]


def main():
    census = json.load(open(CENSUS))
    pattern = json.load(open(PATTERN))
    curve = occupancy_curve(pattern)
    stream_peak = pattern["stream_peak_gbs"]
    pattern_peak = pattern["nvfp4_qmv_faithful_gbs"]   # A3 faithful routed-expert replica
    m5_sat_gbs = M5_PEAK_GBS * EXTRACTION

    rows = []
    for fam in census["families"]:
        name = fam["family"]
        b = fam["bytes_per_step"]
        calls = fam["calls"]
        grid, tptg = GEOMETRY[name]
        label = LABEL_US_M4.get(name)
        bytes_per_dispatch = b / calls

        # The curve is indexed by total threads on 20 cores; a dispatch of `grid`
        # threads on `cores` cores has the same threads/core as grid*20/cores here.
        occ_m4 = min(1.0, curve_gbs(grid, curve) / stream_peak)
        occ_m5 = min(1.0, curve_gbs(grid * M4_CORES / M5_CORES, curve) / stream_peak)

        ceil_m4 = pattern_peak * occ_m4
        floor_ceiling_us = b / (ceil_m4 * 1e3)
        floor_peak_us = b / (pattern_peak * 1e3)

        m5_floor_sat_us = b / (m5_sat_gbs * 1e3)
        m5_floor_occ_us = b / (m5_sat_gbs * occ_m5 * 1e3)
        m5_occ_penalty_us = m5_floor_occ_us - m5_floor_sat_us

        # A bandwidth ceiling only describes a family that moves enough bytes per
        # dispatch to amortise DRAM latency; below that the dispatch is latency
        # and serialisation bound and the roofline is not the binding limit.
        regime = "BANDWIDTH" if (bytes_per_dispatch >= 1 << 20 and grid >= 5120) else "LATENCY"

        rows.append({
            "family": name,
            "n_dispatches": calls,
            "bytes_unique": b,
            "pct_of_step_bytes": round(fam["pct_of_step_bytes"], 4),
            "grid_threads_per_dispatch": grid,
            "threads_per_tg": tptg,
            "regime": regime,
            "label_us_m4": "" if label is None else round(label, 2),
            "achieved_gbs_m4": "" if label is None else round(b / (label * 1e3), 3),
            "pct_of_266_3": "" if label is None else round(100.0 * b / (label * 1e3) / RULE80_GBS, 3),
            "pattern_ceiling_gbs": round(ceil_m4, 3),
            "pct_of_pattern_ceiling": "" if label is None else round(100.0 * b / (label * 1e3) / ceil_m4, 3),
            "floor_us_at_pattern_ceiling": round(floor_ceiling_us, 3),
            "floor_us_at_saturated_peak": round(floor_peak_us, 3),
            "surplus_us_m4": "" if label is None else round(label - floor_ceiling_us, 3),
            "m5_occupancy_frac": round(occ_m5, 4),
            "m5_floor_us_saturated": round(m5_floor_sat_us, 3),
            "m5_occupancy_penalty_us": round(m5_occ_penalty_us, 3),
            "m5_occupancy_penalty_pct_of_cs": round(m5_occ_penalty_us / US_PER_PCT_CS, 4),
        })

    rows.sort(key=lambda r: (r["surplus_us_m4"] if r["surplus_us_m4"] != "" else -1e9), reverse=True)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    lab = [r for r in rows if r["label_us_m4"] != ""]
    tot_label = sum(r["label_us_m4"] for r in lab)
    tot_bytes = sum(r["bytes_unique"] for r in rows)
    pos = [r for r in lab if r["surplus_us_m4"] > 0]
    tot_pos = sum(r["surplus_us_m4"] for r in pos)
    bw_pos = [r for r in pos if r["regime"] == "BANDWIDTH"]
    bw_rows = [r for r in rows if r["regime"] == "BANDWIDTH"]
    tot_m5_pen = sum(r["m5_occupancy_penalty_us"] for r in bw_rows)
    lat_bytes = sum(r["bytes_unique"] for r in rows if r["regime"] == "LATENCY")

    print(f"wrote {OUT}")
    print(f"families={len(rows)}  bytes={tot_bytes}  label_us={tot_label:.1f}")
    print(f"aggregate achieved = {tot_bytes/(tot_label*1e3):.2f} GB/s "
          f"({100*tot_bytes/(tot_label*1e3)/RULE80_GBS:.2f}% of {RULE80_GBS})")
    print(f"pattern peak (A3 faithful nvfp4 replica) = {pattern_peak:.2f} GB/s; "
          f"saturated step floor = {tot_bytes/(pattern_peak*1e3):.1f} us")
    print(f"positive surplus total = {tot_pos:.1f} us over {len(pos)} families "
          f"({sum(r['surplus_us_m4'] for r in bw_pos):.1f} us in {len(bw_pos)} BANDWIDTH-regime)")
    print(f"M5 occupancy penalty, BANDWIDTH regime only = {tot_m5_pen:.1f} us = "
          f"{tot_m5_pen/US_PER_PCT_CS:.3f} % of cs   "
          f"(LATENCY-regime families hold {100*lat_bytes/tot_bytes:.3f}% of bytes "
          f"and are not roofline-modellable)")
    print("\ntop 8 by surplus_us_m4:")
    cum = 0.0
    for r in rows[:8]:
        cum += r["surplus_us_m4"]
        print(f"  {r['family']:<44} {r['regime']:<9} surplus={r['surplus_us_m4']:>8.1f}  "
              f"label={r['label_us_m4']:>7}  m5_occ_pen={r['m5_occupancy_penalty_us']:>7.1f}  "
              f"cum={100*cum/tot_pos:5.1f}%")
    print("\nlargest M5 occupancy penalties:")
    for r in sorted(bw_rows, key=lambda x: -x["m5_occupancy_penalty_us"])[:6]:
        print(f"  {r['family']:<44} grid={r['grid_threads_per_dispatch']:>8}  "
              f"occ={r['m5_occupancy_frac']:.3f}  pen={r['m5_occupancy_penalty_us']:>7.1f} us  "
              f"= {r['m5_occupancy_penalty_pct_of_cs']:.3f}% cs")
    print(f"\ncurve knees (M4, 20 cores): {[(g, round(v, 2)) for g, v in curve]}")


if __name__ == "__main__":
    main()
