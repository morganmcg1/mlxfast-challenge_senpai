#!/usr/bin/env python3
"""r105-D decode byte census, keyed to the 25 traced dispatch families.

Extends `research/fern_r101_byte_audit.py` (whose 15-family table this reuses
verbatim, HEAD epoch) with the ten small families the r101/r94 tables omitted,
so that every one of the 408 traced decode dispatches carries a byte number.
The point of closing the tail is not that the tail is large -- it is that the
84 single-threadgroup dispatches can only be argued about honestly once their
bytes are on the page next to their occupancy.

Emits research/artifacts/fern-r105d/decode-byte-census.json with the arithmetic
for every row written out as a string.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fern_r101_byte_audit import (  # noqa: E402
    EXPERTS, HIDDEN, VOCAB, SPARSE_LAYERS, SLIDING_LAYERS, FULL_LAYERS,
    HEAD_EPOCH, families,
)

# Rule 80 host ceilings.
M5_GBS = 610.0          # measured, ranked M5 Max (tanjiro PR #27)
M4_GBS = 262.98         # measured sequential, this M4 Pro host (r101)
M5_STEP_US = 4141.5     # ranked decode step, seed-prefill amortisation removed
US_PER_PCT_SCORE = 65.67

# trace family -> (r101 family name | None, calls, arithmetic note)
MAP_R101 = {
    "nvfp4_qkv_h64": "T0b(a) qkv h64",
    "routed_nvfp4_swiglu_qmv_packed_top8keys": "T2c routed gate+up qmv",
    "nvfp4_qkv_h48": "T0b(b) qkv h48",
    "routed_shared_nvfp4_down_residual": "T2d routed+shared down+residual",
    "shared_nvfp4_swiglu_qmv_rows1_halved": "T2a shared gate+up qmv",
    "oproj_act_h64": "T3b oproj h64",
    "lmhead_int5_base_coarse_delta": "T1c lmhead int5 base coarse delta",
    "oproj_act_h48": "T3c oproj h48",
    "residual_rms_router": "T1a residual rms router",
    "sliding_fused_attn_ring": "T3a sliding fused attn",
    "full_fused_attn_grow": "T3a' full fused attn",
    "gate_sp_h64": "T2b gate_sp h64",
    "dense_gate_up_swiglu": "dense gate_up (layer 0)",
    "dense_down_residual": "dense_down (layer 0)",
    "gate_sp_h48": "T2b' gate_sp h48",
}


def tail_families():
    """The ten families r101/r94 never priced. All operand traffic, no weights
    except the lm-head refine plane and the embedding row."""
    bf = 2
    rows = []

    # rmsbfloat16: 41 calls. Reads 2048 BF16 activations + 2048 BF16 gamma,
    # writes 2048 BF16. One threadgroup, 512 threads.
    b = 41 * (HIDDEN * bf * 3)
    rows.append(("rmsbfloat16", 41, b,
                 f"41 calls x 3 x {HIDDEN} x {bf} B (x, gamma, y) = {b} B"))

    # prefill_router_tournament: 39 calls. Reads 256 BF16 logits + 256 F32
    # correction bias, writes 8 uint32 ordinals + 8 float weights.
    b = 39 * (EXPERTS * bf + EXPERTS * 4 + 8 * 4 + 8 * 4)
    rows.append(("prefill_router_tournament", 39, b,
                 f"39 x ({EXPERTS}x2 logits + {EXPERTS}x4 bias + 8x4 idx + 8x4 w) = {b} B"))

    # embedding_rope_atlas: 1 call. One BF16 vocab row + RoPE tables + write.
    b = 1 * (HIDDEN * bf * 2 + 128 * 4 * 2)
    rows.append(("embedding_rope_atlas", 1, b,
                 f"1 x (2x{HIDDEN}x{bf} embed row + out, + 128x4x2 rope) = {b} B"))

    # residual_rms_bf16_2048_v1: 1 call (layer-0 post-attention fused norm).
    b = 1 * (HIDDEN * bf * 4)
    rows.append(("residual_rms_bf16_2048_v1", 1, b,
                 f"1 x 4 x {HIDDEN} x {bf} (x, residual, gamma, y) = {b} B"))

    # lm-head chain tail. Stage-1 coarse argmax reads the stage-0 partial
    # scores; refine reads a sparse int5 slice; winner/argmax/gather/copy are
    # O(candidates).
    b = 1 * (128 * 224 * 4 * 2)
    rows.append(("lmhead_coarse_argmax_stage1", 1, b,
                 f"1 x 128 TG x 224 thr x 4 B x 2 (in+out) = {b} B"))
    # refine: 3136 TG x 256 thr, int5 rows for the surviving candidate set.
    # Priced at the same 1344 B/row planar int5 cost for 3136x256/2048 rows.
    refine_rows = 3136 * 256 // 2048
    b = refine_rows * 1344
    rows.append(("lmhead_exact_fused_int5_sparse_refine", 1, b,
                 f"{refine_rows} candidate rows x 1344 B/row planar int5 = {b} B"))
    b = 1 * (32 * 4 * 4)
    rows.append(("lmhead_exact_winner", 1, b, f"1 x 32 lanes x 4 fields x 4 B = {b} B"))
    b = 2 * (49 * 1024 * 4)
    rows.append(("gather_front", 2, b, f"2 calls x 49 TG x 1024 thr x 4 B = {b} B"))
    b = 1 * (49 * 1024 * 4)
    rows.append(("vn_copy", 1, b, f"1 x 49 TG x 1024 thr x 4 B = {b} B"))
    b = 1 * (1024 * 4 * 2)
    rows.append(("argmax", 1, b, f"1 x 1024 thr x 4 B x 2 = {b} B"))
    return rows


def main():
    head = {n: (b, c) for n, b, c in families(**HEAD_EPOCH)}
    out_rows = []
    for tf, r101 in MAP_R101.items():
        b, c = head[r101]
        out_rows.append(dict(family=tf, calls=c, bytes_per_step=b,
                             source=f"fern_r101_byte_audit.families() HEAD epoch, row '{r101}'",
                             arithmetic=f"{b} B/step over {c} calls "
                                        f"= {b / c:.0f} B/call"))
    for tf, c, b, note in tail_families():
        out_rows.append(dict(family=tf, calls=c, bytes_per_step=b,
                             source="r105-D, newly priced (absent from r94/r101 tables)",
                             arithmetic=note))

    out_rows.sort(key=lambda r: -r["bytes_per_step"])
    total = sum(r["bytes_per_step"] for r in out_rows)
    calls = sum(r["calls"] for r in out_rows)
    r101_total = sum(r["bytes_per_step"] for r in out_rows
                     if r["family"] in MAP_R101)
    tail_total = total - r101_total

    for r in out_rows:
        r["pct_of_step_bytes"] = round(100.0 * r["bytes_per_step"] / total, 4)
        r["m5_floor_us"] = round(r["bytes_per_step"] / M5_GBS * 1e-3, 3)
        r["m5_floor_pct_score"] = round(
            (r["bytes_per_step"] / M5_GBS * 1e-3) / US_PER_PCT_SCORE, 4)

    single_tg = {"rmsbfloat16", "prefill_router_tournament", "embedding_rope_atlas",
                 "residual_rms_bf16_2048_v1", "lmhead_exact_winner", "argmax"}
    # the rest of the 203 dispatches that run fewer than C=40 threadgroups
    sub_c_only = {"residual_rms_router", "sliding_fused_attn_ring",
                  "full_fused_attn_grow", "gate_sp_h64", "gate_sp_h48"}
    stg_bytes = sum(r["bytes_per_step"] for r in out_rows if r["family"] in single_tg)
    stg_calls = sum(r["calls"] for r in out_rows if r["family"] in single_tg)
    subc_bytes = stg_bytes + sum(r["bytes_per_step"] for r in out_rows
                                 if r["family"] in sub_c_only)
    subc_calls = stg_calls + sum(r["calls"] for r in out_rows
                                 if r["family"] in sub_c_only)

    # SPLIT=1 per-kernel-label seconds, M4 Pro. RULE 82b: these are an upper
    # bound with an unguaranteed sign and are used here ONLY for shape.
    LABEL_US_M4 = {
        "routed_nvfp4_swiglu_qmv_packed_top8keys": 1497.7,
        "nvfp4_qkv_h64": 1340.1, "oproj_act_h64": 1117.7,
        "routed_shared_nvfp4_down_residual": 858.9,
        "sliding_fused_attn_ring": 636.0, "lmhead_int5_base_coarse_delta": 420.3,
        "nvfp4_qkv_h48": 362.8, "residual_rms_router": 312.8,
        "shared_nvfp4_swiglu_qmv_rows1_halved": 287.1, "oproj_act_h48": 301.8,
        "gate_sp_h64": 248.0, "dense_gate_up_swiglu": 269.4,
        "full_fused_attn_grow": 229.7, "dense_down_residual": 133.8,
        "gate_sp_h48": 80.2,
        "rmsbfloat16": 141.9,               # PR #483
        "prefill_router_tournament": 185.5,  # fern-r105c
    }
    label_total = sum(LABEL_US_M4.values())
    rollup = {}
    for tag, members in (("SINGLE_TG", single_tg),
                         ("SUB_C40_all", single_tg | sub_c_only),
                         ("AT_OR_ABOVE_C40", {r["family"] for r in out_rows}
                          - single_tg - sub_c_only)):
        b = sum(r["bytes_per_step"] for r in out_rows if r["family"] in members)
        c = sum(r["calls"] for r in out_rows if r["family"] in members)
        lab = sum(v for k, v in LABEL_US_M4.items() if k in members)
        rollup[tag] = dict(
            dispatches=c,
            pct_of_408_dispatches=round(100.0 * c / calls, 2),
            bytes_per_step=b,
            pct_of_step_bytes=round(100.0 * b / total, 4),
            m5_dram_floor_us=round(b / M5_GBS * 1e-3, 3),
            label_us_m4_split1=round(lab, 1),
            pct_of_label_total=round(100.0 * lab / label_total, 2),
            rule82b=("SPLIT=1 label seconds: upper bound, unguaranteed sign, "
                     "shape only, never magnitude"),
        )

    roofline = dict(
        m5_dram_gbs_measured=M5_GBS,
        m4_dram_gbs_measured_this_host=M4_GBS,
        step_bytes=total,
        step_bytes_MB=round(total / 1e6, 2),
        dispatches_priced=calls,
        m5_dram_floor_us=round(total / M5_GBS * 1e-3, 2),
        m5_ranked_step_us=M5_STEP_US,
        m5_dram_floor_pct_of_step=round(100.0 * (total / M5_GBS * 1e-3) / M5_STEP_US, 2),
        m5_headroom_above_dram_floor_us=round(M5_STEP_US - total / M5_GBS * 1e-3, 2),
        m5_headroom_pct_score=round(
            (M5_STEP_US - total / M5_GBS * 1e-3) / US_PER_PCT_SCORE, 3),
        m5_achieved_gbs_at_ranked_step=round(total / (M5_STEP_US * 1e-6) / 1e9, 1),
        m5_pct_of_measured_peak=round(
            100.0 * (total / (M5_STEP_US * 1e-6) / 1e9) / M5_GBS, 1),
        note=("The headroom row is a SUBTRACTION RESIDUAL. It is an upper bound "
              "on recoverable time, not recoverable time, and it has no "
              "per-kernel attribution behind it. An unattributed pool is not a "
              "lever."),
    )

    summary = dict(
        schema="fern-r105d-decode-byte-census-v1",
        host_note=("byte counts are representation facts and are host-independent; "
                   "the roofline divides them by the Rule 80 measured M5 ceiling"),
        step_bytes=total,
        r101_15_family_bytes=r101_total,
        r105d_tail_bytes=tail_total,
        r105d_tail_pct_of_step=round(100.0 * tail_total / total, 4),
        single_tg_family_bytes=stg_bytes,
        single_tg_family_calls=stg_calls,
        single_tg_pct_of_step_bytes=round(100.0 * stg_bytes / total, 4),
        single_tg_m5_dram_floor_us=round(stg_bytes / M5_GBS * 1e-3, 3),
        sub_C40_family_bytes=subc_bytes,
        sub_C40_family_calls=subc_calls,
        occupancy_rollup=rollup,
        roofline=roofline,
        families=out_rows,
    )

    outdir = "research/artifacts/fern-r105d"
    os.makedirs(outdir, exist_ok=True)
    with open(os.path.join(outdir, "decode-byte-census.json"), "w") as fh:
        json.dump(summary, fh, indent=2)

    print(f"step bytes            {total:>14,} B  ({total/1e6:.2f} MB)")
    print(f"  r101 15 families    {r101_total:>14,} B  ({100*r101_total/total:.3f} %)")
    print(f"  r105-D tail (10)    {tail_total:>14,} B  ({100*tail_total/total:.4f} %)")
    print(f"  84 single-TG calls  {stg_bytes:>14,} B  ({100*stg_bytes/total:.4f} %)")
    print(f"M5 DRAM floor         {roofline['m5_dram_floor_us']:.2f} us "
          f"= {roofline['m5_dram_floor_pct_of_step']:.2f} % of the {M5_STEP_US} us step")
    print(f"M5 achieved           {roofline['m5_achieved_gbs_at_ranked_step']} GB/s "
          f"= {roofline['m5_pct_of_measured_peak']} % of measured peak")
    print(f"unattributed residual {roofline['m5_headroom_above_dram_floor_us']:.2f} us "
          f"= {roofline['m5_headroom_pct_score']:.3f} % of score  <-- NOT a lever")
    print()
    for tag, v in rollup.items():
        print(f"{tag:16s} {v['dispatches']:3d} disp ({v['pct_of_408_dispatches']:5.2f}%)  "
              f"{v['bytes_per_step']:>13,} B ({v['pct_of_step_bytes']:7.4f}%)  "
              f"label {v['label_us_m4_split1']:7.1f} us ({v['pct_of_label_total']:5.2f}%)")
    print()
    for r in out_rows:
        print(f"{r['family'][:42]:42s} {r['calls']:3d} {r['bytes_per_step']:>13,} "
              f"{r['pct_of_step_bytes']:7.3f}%  floor {r['m5_floor_us']:8.3f} us")


if __name__ == "__main__":
    main()
