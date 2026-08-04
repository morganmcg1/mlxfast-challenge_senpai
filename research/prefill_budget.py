#!/usr/bin/env python3
"""Research-only analytic byte/FLOP budget for one 512-token Laguna forward.

Reads weights/config.json so the geometry cannot drift from the checkpoint.
Prints, per stage: weight bytes read once, MACs, GFLOP, the DRAM-floor time at a
measured read-bandwidth ceiling, and the compute-floor time at a measured MMA
ceiling. The point is the regime question: at 512 tokens each weight is read once
and reused 512 times, so the forward should be compute-bound, not
bandwidth-bound, and the two floors below say by how much.

Usage:
  python3 research/prefill_budget.py [--tokens 512] [--bw-gbs 260.2]
                                     [--tflops 8.0] [--measured-ms 585.0]
"""

import argparse
import json
import pathlib

REPO = pathlib.Path(__file__).resolve().parents[1]

BF16 = 2.0
# NVFP4: 4-bit value + one 8-bit scale per group of 16.
NVFP4 = 0.5 + 1.0 / 16.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tokens", type=int, default=512)
    ap.add_argument("--bw-gbs", type=float, default=260.2,
                    help="measured host read ceiling (research/host_bandwidth_ceiling.swift)")
    ap.add_argument("--tflops", type=float, default=8.0,
                    help="measured MMA ceiling (research/host_flop_ceiling.swift)")
    ap.add_argument("--measured-ms", type=float, default=None,
                    help="measured wall ms for one forward, for %-of-floor columns")
    args = ap.parse_args()

    cfg = json.loads((REPO / "weights/config.json").read_text())
    T = args.tokens
    H = cfg["hidden_size"]
    D = cfg["head_dim"]
    KV = cfg["num_key_value_heads"]
    heads = cfg["num_attention_heads_per_layer"]
    layer_types = cfg["layer_types"]
    n_layers = cfg["num_hidden_layers"]
    dense_layers = set(cfg["mlp_only_layers"])
    ffn = cfg["intermediate_size"]
    moe_ffn = cfg["moe_intermediate_size"]
    shared_ffn = cfg["shared_expert_intermediate_size"]
    n_exp = cfg["num_experts"]
    top_k = cfg["num_experts_per_tok"]
    vocab = cfg["vocab_size"]
    window = cfg["sliding_window"]

    rows = {}

    def add(stage, weight_bytes=0.0, act_bytes=0.0, macs=0.0):
        slot = rows.setdefault(stage, [0.0, 0.0, 0.0])
        slot[0] += weight_bytes
        slot[1] += act_bytes
        slot[2] += macs

    for i in range(n_layers):
        nh = heads[i]
        qdim = nh * D
        kvdim = KV * D
        # --- attention projections (BF16) ---
        wq = H * qdim
        wk = H * kvdim
        wv = H * kvdim
        wo = qdim * H
        wg = H * nh  # per-head gate
        add("attn_proj_qkvo", weight_bytes=(wq + wk + wv + wo + wg) * BF16,
            act_bytes=(T * H + T * (qdim + 2 * kvdim) + T * qdim + T * H) * BF16,
            macs=T * (wq + wk + wv + wo + wg))
        # --- attention core (causal; sliding window >= T so both are full causal) ---
        span = T if layer_types[i] == "full_attention" else min(T, window)
        # causal pair count, capped by the window
        pairs = sum(min(q + 1, span) for q in range(T))
        add("attn_core", act_bytes=(T * (qdim + 2 * kvdim) + T * qdim) * BF16,
            macs=pairs * nh * D * 2)
        # --- norms / rope ---
        add("norm_rope", act_bytes=(4 * T * H + 2 * T * qdim) * BF16)
        if i in dense_layers:
            add("dense_mlp_layer0",
                weight_bytes=3 * H * ffn * BF16,
                act_bytes=(T * H + 3 * T * ffn + T * H) * BF16,
                macs=T * 3 * H * ffn)
            continue
        # --- router (BF16) ---
        add("router", weight_bytes=H * n_exp * BF16,
            act_bytes=(T * H + T * n_exp) * BF16, macs=T * H * n_exp)
        # --- routed experts (NVFP4) ---
        rows_sorted = T * top_k
        add("routed_experts",
            weight_bytes=n_exp * (2 * H * moe_ffn + moe_ffn * H) * NVFP4,
            act_bytes=(rows_sorted * H + rows_sorted * 2 * moe_ffn
                       + rows_sorted * moe_ffn + rows_sorted * H) * BF16,
            macs=rows_sorted * (2 * H * moe_ffn + moe_ffn * H))
        # --- shared expert (NVFP4) ---
        add("shared_expert",
            weight_bytes=(2 * H * shared_ffn + shared_ffn * H) * NVFP4,
            act_bytes=(T * H + T * 2 * shared_ffn + T * shared_ffn + T * H) * BF16,
            macs=T * (2 * H * shared_ffn + shared_ffn * H))
        # --- moe tail (combine + residual) ---
        add("moe_tail", act_bytes=(rows_sorted * H + 2 * T * H) * BF16)

    add("embedding", weight_bytes=T * H * BF16, act_bytes=T * H * BF16)
    # LM head runs on the single terminal row only.
    add("lm_head", weight_bytes=vocab * H * BF16,
        act_bytes=(H + vocab) * BF16, macs=H * vocab)

    total_w = sum(v[0] for v in rows.values())
    total_a = sum(v[1] for v in rows.values())
    total_m = sum(v[2] for v in rows.values())

    print(f"one {T}-token forward, {n_layers} layers "
          f"(bw ceiling {args.bw_gbs} GB/s, mma ceiling {args.tflops} TFLOP/s)\n")
    hdr = (f"{'stage':<20}{'weightGB':>10}{'actGB':>8}{'GFLOP':>9}"
           f"{'%FLOP':>7}{'dramMs':>8}{'mmaMs':>8}{'FLOP/B':>8}")
    print(hdr)
    print("-" * len(hdr))
    order = sorted(rows.items(), key=lambda kv: -kv[1][2])
    for stage, (wb, ab, macs) in order:
        gflop = 2 * macs / 1e9
        byt = wb + ab
        print(f"{stage:<20}{wb / 1e9:10.3f}{ab / 1e9:8.3f}{gflop:9.1f}"
              f"{2 * macs / (2 * total_m) * 100:7.1f}"
              f"{byt / args.bw_gbs / 1e9 * 1e3:8.1f}"
              f"{gflop / args.tflops / 1e3 * 1e3:8.1f}"
              f"{(2 * macs / byt) if byt else 0:8.1f}")
    print("-" * len(hdr))
    total_bytes = total_w + total_a
    total_gflop = 2 * total_m / 1e9
    dram_ms = total_bytes / args.bw_gbs / 1e9 * 1e3
    mma_ms = total_gflop / args.tflops / 1e3 * 1e3
    print(f"{'TOTAL':<20}{total_w / 1e9:10.3f}{total_a / 1e9:8.3f}"
          f"{total_gflop:9.1f}{100.0:7.1f}{dram_ms:8.1f}{mma_ms:8.1f}"
          f"{total_gflop * 1e9 / total_bytes:8.1f}")
    print(f"\nmachine balance      {args.tflops * 1e12 / (args.bw_gbs * 1e9):.1f} FLOP/byte")
    print(f"forward intensity    {total_gflop * 1e9 / total_bytes:.1f} FLOP/byte"
          f"  -> {'COMPUTE' if total_gflop * 1e9 / total_bytes > args.tflops * 1e12 / (args.bw_gbs * 1e9) else 'BANDWIDTH'}-bound regime")
    print(f"dram floor           {dram_ms:.1f} ms")
    print(f"mma floor            {mma_ms:.1f} ms")
    if args.measured_ms:
        print(f"measured             {args.measured_ms:.1f} ms")
        print(f"achieved bandwidth   {total_bytes / (args.measured_ms / 1e3) / 1e9:.1f} GB/s"
              f"  ({total_bytes / (args.measured_ms / 1e3) / 1e9 / args.bw_gbs * 100:.1f}% of ceiling)")
        print(f"achieved compute     {total_gflop / (args.measured_ms / 1e3) / 1e3:.2f} TFLOP/s"
              f"  ({total_gflop / (args.measured_ms / 1e3) / 1e3 / args.tflops * 100:.1f}% of ceiling)")


if __name__ == "__main__":
    main()
