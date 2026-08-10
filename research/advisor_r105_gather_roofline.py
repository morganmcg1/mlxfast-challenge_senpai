#!/usr/bin/env python3
"""advisor r105: roofline audit of the prefill routed gather-GEMM.

Reads research/artifacts/route-histogram-prefill512.csv
  header: layer_index,expert_id,rows,chunks_bm64

Establishes, from first principles and the measured routing histogram:
  * exact useful FLOP of the 76 prefill routed gather-GEMM dispatches
  * exact MMA row inflation at the kFragRows=16 floor
  * exact DRAM weight traffic (nvfp4 payload + uint8 scales), accounting for
    per-chunk weight re-reads
  * the resulting bandwidth floor in ms on M5 Max (610 GB/s measured, rule 80)
  * arithmetic intensity vs the M5 machine balance

The point: decide whether this kernel is compute-bound or memory-bound BEFORE
anyone proposes a tiling arm.
"""
import csv, os, sys, math
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV = os.path.join(ROOT, "research", "artifacts", "route-histogram-prefill512.csv")

# ---- model constants (Sources/MLXFastModel/LagunaConfig.swift) -------------
HIDDEN = 2048          # K of gate/up ; N of down
MOE_INT = 512          # moeIntermediateSize
N_GATEUP = 2 * MOE_INT # 1024   (gate and up fused)
K_GATEUP = HIDDEN      # 2048
N_DOWN = HIDDEN        # 2048  <- host cert: (K==2048 && N==1024) || (K==512 && N==2048)
K_DOWN = MOE_INT       # 512
EXPERTS = 256
TOPK = 8
TOKENS = 512
SPARSE_LAYERS = 38     # 40 layers - layer0 dense - last layer (last-token only)

BITS = 4
GROUP = 16             # nvfp4 group size -> 1 uint8 scale per 16 elements
BYTES_PER_ELEM = BITS / 8.0                 # 0.5
SCALE_BYTES_PER_ELEM = 1.0 / GROUP          # 0.0625
W_BYTES_PER_ELEM = BYTES_PER_ELEM + SCALE_BYTES_PER_ELEM   # 0.5625

# ---- kernel geometry (quantized.cpp:1362-1372 variant 5 ; fp_quantized_nax.h)
BM, BN, BK, WM, WN = 64, 64, 64, 4, 1
SM = BM // WM          # 16
K_FRAG_ROWS = 16       # steel/gemm/nax.h:27-28

# ---- machine (rule 80) -----------------------------------------------------
M5_BW = 610.0e9        # bytes/s measured
M5_PEAK = 60.0e12      # FLOP/s reference used throughout this campaign
PRICE_PCT_PER_MS = 0.3781   # rule 84, total-prefill price


def load():
    rows = []
    with open(CSV) as f:
        r = csv.DictReader(f)
        for rec in r:
            rows.append((int(rec["layer_index"]), int(rec["expert_id"]),
                         int(rec["rows"]), int(rec["chunks_bm64"])))
    return rows


def main():
    recs = load()
    layers = sorted({l for l, _, _, _ in recs})
    per_layer = defaultdict(list)
    for l, e, r, c in recs:
        per_layer[l].append((e, r, c))

    tot_rows = sum(r for _, _, r, _ in recs)
    tot_entries = len(recs)
    print(f"CSV rows                : {tot_entries}")
    print(f"distinct layers         : {len(layers)}  ({min(layers)}..{max(layers)})")
    print(f"sum(rows)               : {tot_rows}")
    print(f"expected per-layer rows : {TOKENS*TOPK} ; layers*that = {len(layers)*TOKENS*TOPK}")

    # ---- empties -----------------------------------------------------------
    # entries with rows==0 may be absent; reconstruct against the full 256 grid
    present = defaultdict(set)
    for l, e, r, c in recs:
        if r > 0:
            present[l].add(e)
    nonempty_counts = [len(present[l]) for l in layers]
    tot_nonempty = sum(nonempty_counts)
    tot_slots = len(layers) * EXPERTS
    print(f"\nnon-empty (layer,expert): {tot_nonempty} / {tot_slots} "
          f"= {100.0*tot_nonempty/tot_slots:.2f}%  "
          f"(empty {100.0*(tot_slots-tot_nonempty)/tot_slots:.2f}%)")
    print(f"  per-layer non-empty   : min {min(nonempty_counts)} "
          f"max {max(nonempty_counts)} mean {sum(nonempty_counts)/len(layers):.1f}")

    # ---- MMA row inflation at the kFragRows=16 floor -----------------------
    issued = sum(math.ceil(r / K_FRAG_ROWS) * K_FRAG_ROWS for _, _, r, _ in recs if r > 0)
    print(f"\nMMA rows useful (1 GEMM): {tot_rows}")
    print(f"MMA rows issued (1 GEMM): {issued}   inflation {issued/tot_rows:.4f}x")
    print(f"  both GEMMs            : useful {2*tot_rows} issued {2*issued}")

    # ---- chunk re-reads of the weight tile ---------------------------------
    # a threadgroup owns (expert, BN-column-block) and re-loads its Ws slab once
    # per BM=64 row chunk of that expert's run
    chunks_csv = sum(c for _, _, r, c in recs if r > 0)
    chunks_calc = sum(math.ceil(r / BM) for _, _, r, _ in recs if r > 0)
    print(f"\nchunks_bm64 (from CSV)  : {chunks_csv}")
    print(f"ceil(rows/64) recomputed: {chunks_calc}   {'MATCH' if chunks_csv==chunks_calc else 'MISMATCH'}")
    print(f"weight re-read factor   : {chunks_csv/tot_nonempty:.4f}x "
          f"(chunks per non-empty expert)")

    # ---- DRAM weight traffic ----------------------------------------------
    # per (layer, expert) the kernel streams the expert's full weight matrix,
    # once per row chunk.
    gu_elems = N_GATEUP * K_GATEUP          # 1024*2048 per expert
    dn_elems = N_DOWN * K_DOWN              # 2048*512  per expert
    per_expert_bytes = (gu_elems + dn_elems) * W_BYTES_PER_ELEM
    print(f"\nper-expert weight bytes : gate/up {gu_elems*W_BYTES_PER_ELEM/1e6:.3f} MB"
          f"  down {dn_elems*W_BYTES_PER_ELEM/1e6:.3f} MB"
          f"  total {per_expert_bytes/1e6:.3f} MB")
    full_bank = EXPERTS * per_expert_bytes * len(layers)
    print(f"full 38-layer bank      : {full_bank/1e9:.3f} GB (all 256 experts)")

    touched_once = tot_nonempty * per_expert_bytes
    touched_chunks = chunks_csv * per_expert_bytes
    print(f"touched once per expert : {touched_once/1e9:.3f} GB")
    print(f"touched per row-chunk   : {touched_chunks/1e9:.3f} GB  <-- what the kernel issues")

    # ---- activation traffic -------------------------------------------------
    # grid_dims.x = N/BN threadgroups, EACH of which reads the SAME x rows for
    # its expert.  So the x side is replicated gx times unless L2/SLC absorbs it.
    gx_gu = N_GATEUP // BN     # 16
    gx_dn = N_DOWN // BN       # 32
    per_row_ideal = (K_GATEUP * 2) + (MOE_INT * 2) + (N_DOWN * 2)
    per_row_replic = (gx_gu * K_GATEUP * 2) + (gx_dn * MOE_INT * 2) + (N_DOWN * 2)
    act_ideal = tot_rows * per_row_ideal
    act_replic = tot_rows * per_row_replic
    print(f"\ngrid.x (gate/up, down)  : {gx_gu}, {gx_dn}  -> x rows re-read that many times")
    print(f"activations, ideal reuse: {act_ideal/1e9:.3f} GB  ({per_row_ideal} B/row)")
    print(f"activations, no reuse   : {act_replic/1e9:.3f} GB  ({per_row_replic} B/row)")

    models = [
        ("weights only (cache-immune floor)", touched_chunks),
        ("weights + ideal-reuse activations", touched_chunks + act_ideal),
        ("weights + zero-reuse activations", touched_chunks + act_replic),
    ]
    total_bytes = touched_chunks + act_ideal
    print(f"TOTAL DRAM (central est.): {total_bytes/1e9:.3f} GB")

    # ---- FLOP --------------------------------------------------------------
    gflop_useful = 0.0
    for l, e, r, c in recs:
        if r == 0:
            continue
        gflop_useful += 2.0 * r * N_GATEUP * K_GATEUP
        gflop_useful += 2.0 * r * N_DOWN * K_DOWN
    gflop_issued = 0.0
    for l, e, r, c in recs:
        if r == 0:
            continue
        rr = math.ceil(r / K_FRAG_ROWS) * K_FRAG_ROWS
        gflop_issued += 2.0 * rr * N_GATEUP * K_GATEUP
        gflop_issued += 2.0 * rr * N_DOWN * K_DOWN
    print(f"\nuseful FLOP             : {gflop_useful/1e9:.2f} GFLOP")
    print(f"issued FLOP (16-row flr): {gflop_issued/1e9:.2f} GFLOP  "
          f"({gflop_issued/gflop_useful:.4f}x)")

    # ---- roofline ----------------------------------------------------------
    ai_useful = gflop_useful / total_bytes
    ai_issued = gflop_issued / total_bytes
    balance = M5_PEAK / M5_BW
    print(f"\narithmetic intensity    : useful {ai_useful:.2f} FLOP/byte"
          f"  issued {ai_issued:.2f} FLOP/byte")
    print(f"M5 machine balance      : {balance:.2f} FLOP/byte "
          f"({M5_PEAK/1e12:.0f} TFLOP/s / {M5_BW/1e9:.0f} GB/s)")
    verdict = "MEMORY-BOUND" if ai_issued < balance else "COMPUTE-BOUND"
    print(f"VERDICT                 : {verdict} "
          f"(issued AI is {balance/ai_issued:.2f}x below balance)")

    dram_floor_ms = total_bytes / M5_BW * 1e3
    mma_floor_ms = gflop_issued / M5_PEAK * 1e3
    mma_useful_ms = gflop_useful / M5_PEAK * 1e3
    print(f"\nDRAM floor, by traffic model:")
    for label, b in models:
        print(f"  {label:38s} {b/1e9:7.3f} GB -> {b/M5_BW*1e3:7.3f} ms")
    print(f"MMA-issue floor         : {mma_floor_ms:.3f} ms "
          f"(useful-only {mma_useful_ms:.3f} ms)")

    # ---- against the measured (contaminated) M5 number ---------------------
    for label, meas in (("tanjiro dS_1 (contaminated)", 43.262),):
        print(f"\n--- vs {label} = {meas:.3f} ms ---")
        print(f"  achieved bandwidth    : {total_bytes/(meas/1e3)/1e9:.1f} GB/s "
              f"= {100.0*total_bytes/(meas/1e3)/M5_BW:.1f}% of {M5_BW/1e9:.0f}")
        print(f"  achieved TFLOP/s      : useful {gflop_useful/(meas/1e3)/1e12:.2f} "
              f"= {100.0*gflop_useful/(meas/1e3)/M5_PEAK:.1f}% of peak ; "
              f"issued {gflop_issued/(meas/1e3)/1e12:.2f} "
              f"= {100.0*gflop_issued/(meas/1e3)/M5_PEAK:.1f}%")
        gap = meas - dram_floor_ms
        print(f"  gap to DRAM floor     : {gap:.3f} ms = {gap*PRICE_PCT_PER_MS:+.3f}% of cs")
        # what a perfect fix of MMA row inflation would buy, IF compute-bound
        infl_saving = meas * (1.0 - gflop_useful/gflop_issued)
        print(f"  if row inflation were the binding term, perfect fix buys "
              f"{infl_saving:.3f} ms = {infl_saving*PRICE_PCT_PER_MS:+.3f}% of cs")
        print(f"  but DRAM floor forbids going below {dram_floor_ms:.3f} ms, so the")
        print(f"  MAXIMUM any in-kernel arm can buy is "
              f"{gap:.3f} ms = {gap*PRICE_PCT_PER_MS:+.3f}% of cs")

    print(f"\nbar to the record       : +1.438% of cs = "
          f"{1.438/PRICE_PCT_PER_MS:.3f} ms of prefill")


if __name__ == "__main__":
    main()
