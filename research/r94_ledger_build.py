#!/usr/bin/env python3
"""R94-A Stage 0/1: rebuild the complete scored decode-step dispatch ledger.

Sources (all in-tree, no new GPU run required):
  A) research/maple-nezuko-r92-barrier-hoist-generalization.md:70-100
     PR #488 SPLIT=1 live decode census, default arm. 24 labels, 406
     dispatches/step, gpu_busy_sum 8.528 ms/step.
  B) research/r92-artifacts/r92-census-stage1prime.txt
     PR #490 scored-worker emission trace. 21 custom-kernel labels,
     363 dispatches/step (steady state proven by two byte-identical
     consecutive Counter multisets).
  C) research/CURRENT_RESEARCH_STATE.md rule 41 dispatch-boundary brackets.
"""
import pathlib
import sys

# (us_per_step, calls_per_step, label, kind, origin, notes)
LEDGER = [
    (1497.7, 39, "laguna_routed_nvfp4_swiglu_qmv_packed_top8keys_r1_bf16_v2", "swift_kernel", "LagunaRuntimeModel.swift:8309-cluster", "routed top-8 gate/up NVFP4 gather-GEMV"),
    (1340.1, 30, "laguna_decode_nvfp4_qkv_h64_r1_v1_lm1_pw1_se1_sd1", "swift_kernel", "LagunaRuntimeModel.swift qkv emitter", "sliding-window layers, 64 q heads"),
    (1117.7, 30, "laguna_oproj_act_h64_v1_lm1_pw1_sc1_se1", "swift_kernel", "LagunaRuntimeModel.swift oproj emitter", "o_proj + gate application"),
    (858.9, 39, "laguna_routed_shared_nvfp4_down_residual_bf16_sh_stage4_v6", "swift_kernel", "LagunaRuntimeModel.swift:8309", "routed+shared down proj + residual"),
    (636.0, 30, "laguna_sliding_fused_attn_ring_v1", "swift_kernel", "LagunaRuntimeModel.swift sliding attn", "ring KV, 512-window"),
    (420.3, 1, "laguna_lmhead_int5_base_coarse_delta_bf16_v1", "swift_kernel", "LagunaLmHeadPrune.swift", "int5 screening plane, 134.9 MB"),
    (362.8, 10, "laguna_decode_nvfp4_qkv_h48_r1_v1_lm1_pw1_se1_sd1", "swift_kernel", "LagunaRuntimeModel.swift qkv emitter", "full-attn layers, 48 q heads"),
    (312.8, 39, "laguna_residual_rms_router_bf16_2048_rpg8_keys_v1_pf1", "swift_kernel", "LagunaRuntimeModel.swift:1083", "post-attn residual add + RMS + router logits"),
    (301.8, 10, "laguna_oproj_act_h48_v1_lm1_pw1_sc1_se1", "swift_kernel", "LagunaRuntimeModel.swift oproj emitter", ""),
    (287.1, 39, "laguna_shared_nvfp4_swiglu_qmv_rows1_halved_bf16_v1", "swift_kernel", "LagunaRuntimeModel.swift shared-expert", "shared expert gate/up"),
    (269.4, 1, "laguna_dense_gate_up_swiglu_bf16_v1", "swift_kernel", "LagunaRuntimeModel.swift dense MLP", "layer 0 dense MLP"),
    (248.0, 30, "laguna_gate_sp_h64_v1", "swift_kernel", "LagunaRuntimeModel.swift:4429", "per-head g_proj sigmoid gate"),
    (229.7, 10, "laguna_full_fused_attn_grow_v1", "swift_kernel", "LagunaRuntimeModel.swift full attn", "growing KV, full attention"),
    (185.5, 39, "laguna_prefill_router_tournament_ordinal_norm_active64_v2", "swift_kernel", "LagunaRuntimeLayers.swift:776", "rows=1 decode entry, name is misleading"),
    (141.9, 41, "rmsbfloat16", "mlx_stock", "MLX AOT rms kernel", "40 input norms + 1 final norm"),
    (133.8, 1, "laguna_dense_down_residual_bf16_v1", "swift_kernel", "LagunaRuntimeModel.swift dense MLP", "layer 0"),
    (80.2, 10, "laguna_gate_sp_h48_v1", "swift_kernel", "LagunaRuntimeModel.swift:4429", ""),
    (77.0, 1, "laguna_lmhead_exact_fused_int5_sparse_refine_v1", "swift_kernel", "LagunaLmHeadPrune.swift", ""),
    (9.0, 1, "argmax_bfloat16", "mlx_stock", "MLX AOT arg_reduce", ""),
    (4.7, 1, "laguna_lmhead_exact_winner_bf16_midpoint_threshold_v1", "swift_kernel", "LagunaLmHeadPrune.swift", ""),
    (4.1, 1, "laguna_lmhead_coarse_argmax_stage1_v5", "swift_kernel", "LagunaLmHeadPrune.swift", ""),
    (3.5, 1, "laguna_decode_embedding_rope_atlas_bf16_2048_v2", "swift_kernel", "LagunaRuntimeModel.swift embedding", "1/step, r92 step splitter"),
    (3.4, 1, "gather_frontbfloat16_int32_int_2", "mlx_stock", "MLX AOT gather", "embedding row gather"),
    (2.9, 1, "laguna_residual_rms_bf16_2048_v1", "swift_kernel", "LagunaRuntimeModel.swift:1182", "layer-0 dense post-attn norm"),
]

# --- byte model -------------------------------------------------------------
# weights/config.json: hidden 2048, head_dim 128, kv_heads 8, 40 layers,
# num_attention_heads_per_layer = 30x64 (sliding) + 10x48 (full_attention),
# mlp_only_layers [0] (dense, bf16, intermediate 8192), 39 sparse layers,
# 256 experts, top-8, moe_intermediate 512, shared_expert 512, vocab 100352,
# quantization nvfp4 bits 4 group_size 16.
H, HD, KVH, V = 2048, 128, 8, 100352
N_SLIDE, N_FULL, N_SPARSE = 30, 10, 39
MOE_I, DENSE_I, TOP8 = 512, 8192, 8


def nvfp4(w: int) -> int:
    """4-bit element + one fp8 group scale per 16 elements."""
    return int(w * (0.5 + 1.0 / 16.0))


def int8g32(w: int) -> int:
    """INT8 code + bf16 scale and bias per group of 32."""
    return w + (w // 32) * 4


def bf16(w: int) -> int:
    return w * 2


KV_SLIDE = 512 * KVH * HD * 2 * 2          # ring window, K and V, bf16
KV_FULL = 576 * KVH * HD * 2 * 2           # 512 seed + mean 63.5 decode steps

# label -> (bytes_touched_est per step, verdict, roofline note)
BYTES = {
    "laguna_routed_nvfp4_swiglu_qmv_packed_top8keys_r1_bf16_v2":
        (N_SPARSE * TOP8 * nvfp4(2 * MOE_I * H), "bytes-bound", ""),
    "laguna_decode_nvfp4_qkv_h64_r1_v1_lm1_pw1_se1_sd1":
        (N_SLIDE * (nvfp4(64 * HD * H) + 2 * nvfp4(KVH * HD * H)), "bytes-bound", ""),
    "laguna_oproj_act_h64_v1_lm1_pw1_sc1_se1":
        (N_SLIDE * nvfp4(64 * HD * H), "bytes-bound", ""),
    "laguna_routed_shared_nvfp4_down_residual_bf16_sh_stage4_v6":
        (N_SPARSE * (TOP8 + 1) * nvfp4(MOE_I * H), "bytes-bound", ""),
    "laguna_sliding_fused_attn_ring_v1":
        (N_SLIDE * KV_SLIDE, "latency-bound", "KV stream only; softmax serialization dominates"),
    "laguna_lmhead_int5_base_coarse_delta_bf16_v1":
        (int(V * H * 0.625), "bytes-bound",
         "nominal full int5 plane; implied rate exceeds the platform peak, so the "
         "kernel already reads less than the whole plane"),
    "laguna_decode_nvfp4_qkv_h48_r1_v1_lm1_pw1_se1_sd1":
        (N_FULL * (nvfp4(48 * HD * H) + 2 * nvfp4(KVH * HD * H)), "bytes-bound", ""),
    "laguna_residual_rms_router_bf16_2048_rpg8_keys_v1_pf1":
        (N_SPARSE * bf16(256 * H), "partly-bytes-bound", "router matrix 256x2048 bf16"),
    "laguna_oproj_act_h48_v1_lm1_pw1_sc1_se1":
        (N_FULL * nvfp4(48 * HD * H), "bytes-bound", ""),
    "laguna_shared_nvfp4_swiglu_qmv_rows1_halved_bf16_v1":
        (N_SPARSE * nvfp4(2 * MOE_I * H), "partly-bytes-bound", ""),
    "laguna_dense_gate_up_swiglu_bf16_v1":
        (bf16(2 * DENSE_I * H), "bytes-bound", "layer-0 MLP is bf16, not NVFP4"),
    "laguna_gate_sp_h64_v1":
        (N_SLIDE * int8g32(64 * H), "overhead-bound", "147 KB per call; 40 calls/step"),
    "laguna_full_fused_attn_grow_v1":
        (N_FULL * KV_FULL, "latency-bound", "KV length grows 512 -> 640"),
    "laguna_prefill_router_tournament_ordinal_norm_active64_v2":
        (N_SPARSE * 256 * 4, "overhead-bound", "40 KB/step total; pure boundary + ramp"),
    "rmsbfloat16":
        (41 * bf16(H) * 2, "overhead-bound", "MLX AOT; 168 KB/step total"),
    "laguna_dense_down_residual_bf16_v1":
        (bf16(DENSE_I * H), "bytes-bound", ""),
    "laguna_gate_sp_h48_v1":
        (N_FULL * int8g32(48 * H), "overhead-bound", ""),
    "laguna_lmhead_exact_fused_int5_sparse_refine_v1":
        (0, "overhead-bound", "sparse candidate rows only; byte count not derivable in-tree"),
    "argmax_bfloat16": (0, "overhead-bound", "MLX AOT arg_reduce over the pruned candidate set"),
    "laguna_lmhead_exact_winner_bf16_midpoint_threshold_v1": (0, "overhead-bound", ""),
    "laguna_lmhead_coarse_argmax_stage1_v5": (0, "overhead-bound", ""),
    "laguna_decode_embedding_rope_atlas_bf16_2048_v2": (0, "overhead-bound", ""),
    "gather_frontbfloat16_int32_int_2": (bf16(H), "overhead-bound", "one embedding row"),
    "laguna_residual_rms_bf16_2048_v1": (bf16(H) * 2, "overhead-bound", ""),
}

# M4 Pro unified-memory peak. The 260.2 GB/s figure from an earlier local copy
# microbenchmark is a floor on achievable rate, not the roofline: several rows
# below beat it, so the roofline used here is the platform peak.
CEILING_GB_S = 273.0

REPORTED_BUSY_SPLIT1 = 8528.0
REPORTED_DISPATCHES = 406
R92_CUSTOM_DISPATCHES = 363
NAT_BUSY = 7993.1
NAT_WALL = 8230.3
SPLIT1_WALL = 9768.0
ADVISOR_NAMED_SUBTOTAL = [1702.9, 1419.5, 1497.7, 858.9, 636.0, 312.8, 229.7, 141.9, 4.7, 2.9]
TINY_US = 0.7258
WIDE_US = 1.4064
# 1 us/step of decode == this fraction of score (assignment PR #502)
SCORE_PCT_PER_US = 0.015280


def main() -> int:
    tot_us = sum(r[0] for r in LEDGER)
    tot_n = sum(r[1] for r in LEDGER)
    stock = [r for r in LEDGER if r[3] == "mlx_stock"]
    custom = [r for r in LEDGER if r[3] == "swift_kernel"]
    stock_n = sum(r[1] for r in stock)
    custom_n = sum(r[1] for r in custom)

    print(f"labels                     = {len(LEDGER)}  (custom {len(custom)}, stock {len(stock)})")
    print(f"dispatches/step            = {tot_n}   reported {REPORTED_DISPATCHES}   delta {tot_n-REPORTED_DISPATCHES}")
    print(f"ledger us/step             = {tot_us:.1f}   reported busy {REPORTED_BUSY_SPLIT1:.1f}"
          f"   residual {tot_us-REPORTED_BUSY_SPLIT1:+.1f} ({100*(tot_us-REPORTED_BUSY_SPLIT1)/REPORTED_BUSY_SPLIT1:+.3f} %)")
    print()
    print("--- Stage 0 reconciliation: 363 vs 406 ---")
    print(f"custom metalKernel dispatches (carry verbose:) = {custom_n}  [r92 vehicle saw {R92_CUSTOM_DISPATCHES}]")
    print(f"MLX stock/AOT dispatches (no verbose: hook)    = {stock_n}"
          f"   = {' + '.join(f'{r[1]}x {r[2]}' for r in stock)}")
    print(f"{custom_n} + {stock_n} = {custom_n+stock_n}  -> both counts are steady-state; the gap is the")
    print("stock-op blind spot of the r92 verbose-dump vehicle, not warm-up or SPLIT=1 inflation.")
    print()
    print("--- the claimed residue ---")
    named = sum(ADVISOR_NAMED_SUBTOTAL)
    print(f"advisor named subtotal (SPLIT=1 rows)          = {named:.1f} us over 281 dispatches")
    print(f"rows present in the same census but omitted    = {tot_us-named:.1f} us over {tot_n-281} dispatches")
    print(f"claimed residue 1186.1 us = {NAT_BUSY} (nat busy) - {named:.1f} (SPLIT=1 subtotal)")
    print("  -> cross-regime subtraction (rule 43) of an incomplete subtotal.")
    print(f"SPLIT=1 busy - nat busy = {REPORTED_BUSY_SPLIT1-NAT_BUSY:+.1f} us/step over {tot_n} dispatches"
          f" = {(REPORTED_BUSY_SPLIT1-NAT_BUSY)/tot_n:.3f} us/dispatch")
    print(f"SPLIT=1 wall - nat wall = {SPLIT1_WALL-NAT_WALL:+.1f} us/step (the instrument tax)")
    print(f"rule-41 boundary bracket: TINY {TINY_US} .. WIDE {WIDE_US} us/dispatch"
          f" -> per-dispatch busy inflation {(REPORTED_BUSY_SPLIT1-NAT_BUSY)/tot_n:.3f} us sits inside it")
    print()
    print("--- nat-regime deflation of every row (subtract 1 boundary per call) ---")
    infl = (REPORTED_BUSY_SPLIT1 - NAT_BUSY) / tot_n
    print(f"{'us/step_s1':>10} {'calls':>6} {'us/call_s1':>10} {'us/step_nat_est':>15} {'score%_if_zero':>14}  label")
    for us, n, label, kind, origin, notes in LEDGER:
        nat = max(0.0, us - n * infl)
        print(f"{us:10.1f} {n:6d} {us/n:10.2f} {nat:15.1f} {nat*SCORE_PCT_PER_US:13.3f}%  {label}")
    print()
    print("--- clusters (nat-deflated) ---")
    groups = {
        "attention qkv+oproj+attn+gate (h48/h64)": [
            "laguna_decode_nvfp4_qkv_h64_r1_v1_lm1_pw1_se1_sd1",
            "laguna_decode_nvfp4_qkv_h48_r1_v1_lm1_pw1_se1_sd1",
            "laguna_oproj_act_h64_v1_lm1_pw1_sc1_se1",
            "laguna_oproj_act_h48_v1_lm1_pw1_sc1_se1",
            "laguna_sliding_fused_attn_ring_v1",
            "laguna_full_fused_attn_grow_v1",
            "laguna_gate_sp_h64_v1",
            "laguna_gate_sp_h48_v1",
        ],
        "routed MoE trio": [
            "laguna_routed_nvfp4_swiglu_qmv_packed_top8keys_r1_bf16_v2",
            "laguna_routed_shared_nvfp4_down_residual_bf16_sh_stage4_v6",
            "laguna_shared_nvfp4_swiglu_qmv_rows1_halved_bf16_v1",
        ],
        "norm + router": [
            "laguna_residual_rms_router_bf16_2048_rpg8_keys_v1_pf1",
            "laguna_prefill_router_tournament_ordinal_norm_active64_v2",
            "rmsbfloat16",
            "laguna_residual_rms_bf16_2048_v1",
        ],
        "lm head": [
            "laguna_lmhead_int5_base_coarse_delta_bf16_v1",
            "laguna_lmhead_exact_fused_int5_sparse_refine_v1",
            "laguna_lmhead_exact_winner_bf16_midpoint_threshold_v1",
            "laguna_lmhead_coarse_argmax_stage1_v5",
            "argmax_bfloat16",
        ],
        "layer-0 dense MLP": [
            "laguna_dense_gate_up_swiglu_bf16_v1",
            "laguna_dense_down_residual_bf16_v1",
        ],
        "embedding": [
            "laguna_decode_embedding_rope_atlas_bf16_2048_v2",
            "gather_frontbfloat16_int32_int_2",
        ],
    }
    by_label = {r[2]: r for r in LEDGER}
    seen = set()
    for name, labels in groups.items():
        us = sum(max(0.0, by_label[l][0] - by_label[l][1] * infl) for l in labels)
        n = sum(by_label[l][1] for l in labels)
        seen |= set(labels)
        print(f"{us:9.1f} us/step  {n:4d} disp  {100*us/(NAT_BUSY):5.1f}% of nat busy  {name}")
    missing = set(by_label) - seen
    assert not missing, missing

    print()
    print("--- Stage 2 roofline verdicts (nat-deflated us, bytes from weights/config.json) ---")
    print(f"{'us/step_nat':>11} {'MB/step':>9} {'GB/s':>7} {'%ceil':>6}  {'verdict':<19} label")
    pools: dict[str, list[float]] = {}
    for us, n, label, kind, origin, notes in LEDGER:
        nat = max(0.0, us - n * infl)
        nbytes, verdict, _ = BYTES[label]
        gbs = (nbytes / (nat * 1e-6) / 1e9) if nat > 0 and nbytes else 0.0
        pools.setdefault(verdict, []).append(nat)
        print(f"{nat:11.1f} {nbytes/1e6:9.1f} {gbs:7.1f} {100*gbs/CEILING_GB_S:5.0f}%  {verdict:<19} {label}")
    print()
    for verdict in ("bytes-bound", "latency-bound", "partly-bytes-bound", "overhead-bound"):
        pool = pools.get(verdict, [])
        print(f"{sum(pool):9.1f} us/step  {100*sum(pool)/NAT_BUSY:5.1f}% of nat busy  "
              f"{len(pool):2d} labels  {verdict}")
    print(f"{sum(sum(v) for v in pools.values()):9.1f} us/step  total (nat busy {NAT_BUSY})")

    out = pathlib.Path("research/r94-artifacts/r94-dispatch-ledger.tsv")
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w") as fh:
        fh.write("label\tkind\torigin\tcalls_per_step\tus_per_step\tus_per_call"
                 "\tbytes_touched_est\tnotes\n")
        for us, n, label, kind, origin, notes in LEDGER:
            nat = max(0.0, us - n * infl)
            nbytes, verdict, rnote = BYTES[label]
            gbs = (nbytes / (nat * 1e-6) / 1e9) if nat > 0 and nbytes else 0.0
            note = (f"{verdict}; nat_est {nat:.1f} us/step; "
                    f"{gbs:.0f} GB/s = {100*gbs/CEILING_GB_S:.0f}% of M4 Pro peak"
                    if nbytes else f"{verdict}; nat_est {nat:.1f} us/step")
            for extra in (rnote, notes):
                if extra:
                    note += f"; {extra}"
            fh.write(f"{label}\t{kind}\t{origin}\t{n}\t{us:.1f}\t{us/n:.2f}\t{nbytes}\t{note}\n")
        resid = REPORTED_BUSY_SPLIT1 - tot_us
        fh.write(f"unattributed\tresidue\tSPLIT=1 gpu_busy_sum minus the 24 rows above\t"
                 f"{REPORTED_DISPATCHES - tot_n}\t{resid:.1f}\t0.00\t0\t"
                 f"the ledger closes to {100*abs(resid)/REPORTED_BUSY_SPLIT1:.3f} % of busy and "
                 f"{REPORTED_DISPATCHES - tot_n} dispatches; there is no residue to attribute\n")
    print(f"\nwrote {out}")

    if abs(tot_us - REPORTED_BUSY_SPLIT1) / REPORTED_BUSY_SPLIT1 > 0.02:
        print("LEDGER DOES NOT CLOSE WITHIN 2%", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
