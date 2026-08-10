#!/usr/bin/env python3
"""R106-F: prefill non-GEMM census arithmetic.

Consumes the adjudicated family table produced by
research/prefill_census_adjudicate.py (M4 Pro, 512-token prefill) and emits
the headline GEMM/non-GEMM partition, per-family roofline placement, and the
desk price of the ranked candidates in M5 ms and % of score.

Roofline constants are host constants, not measurements of this run:
  M4_TFLOPS  BF16 SIMD MMA peak, 20 cores x 256 FLOP/clk x ~1.56 GHz.
  M4_DRAM    LPDDR5X peak, Rule-80 bandwidth probe.
"""

M4_TFLOPS = 8.0
M4_DRAM = 260.2
M5_DRAM_ACHIEVED = 546.2
M5_PREFILL_MS = 97.895

# %-of-score per ms of M5 prefill removed. Low = receipt-derived, high = prospective.
SCORE_PCT_PER_MS = (0.2592, 0.3781)
SCORE_BAR_PCT = 0.2

WALL = 548.386

# family -> (fair_ms, bytes_bound_GB)
FAM = {
    "routed_gather_gemm": (265.440, 18.968),
    "steel_gemm_bf16": (214.513, 4.552),
    "attention_core": (28.133, 0.696),
    "nvfp4_dense_qmm": (19.998, 0.652),
    "elementwise": (4.710, 1.632),
    "qk_norm_rope": (4.194, 0.768),
    "sort_scatter": (2.633, 1.134),
    "moe_tail": (2.539, 0.878),
    "rms_norm": (1.714, 0.497),
    "router": (0.673, 0.012),
    "lm_head": (0.667, 0.959),
    "other": (0.311, 0.211),
    "MIXED": (0.022, 0.000),
}
IDLE = 2.839

# FLOPs derived from the model dims and the trace's own call counts, so that
# every count is pinned by an observed dispatch multiplicity rather than by an
# assumed layer count. L=512 tokens, hidden=2048, head_dim=128, top-k=8,
# MoE inter=512, shared inter=512. 2 FLOP per MAC throughout.
L, HID, MOE_INTER = 512, 2048, 512
# Layer 39 is diverted to callLastPrefillRow (1-row), so only 38 MoE layers and
# 39 attention layers run at full length. Both counts are confirmed by the
# trace: 76 = 38 x 2 gather dispatches, 39 steel_attention + 1 sdpa_vector.
MOE_LAYERS, ATTN_LAYERS = 38, 39
_gate_up = 2 * (HID * MOE_INTER * 2)
_down = MOE_INTER * HID * 2
_routed_per_layer = L * 8 * (_gate_up + _down)
_shared_per_layer = L * (_gate_up + _down)
# 40 layers, 10 full (48 q-heads) + 30 sliding (64 q-heads); the diverted layer
# 39 is sliding. Causal halving is already applied: 2 * L^2/2 * D per head, x2
# for the QK and AV products.
_attn = sum(
    heads * n * (2 * L * L * 128)
    for heads, n in ((48, 10), (64, ATTN_LAYERS - 10))
)

GFLOP = {
    "routed_gather_gemm": MOE_LAYERS * _routed_per_layer / 1e9,
    "steel_gemm_bf16": 1502.8,  # prior art; see inconsistency E (1465.3 alt.)
    "attention_core": _attn / 1e9,
    "nvfp4_dense_qmm": MOE_LAYERS * _shared_per_layer / 1e9,
}
GFLOP_ALT = {"steel_gemm_bf16": 1465.3}

MMA = ["routed_gather_gemm", "steel_gemm_bf16", "nvfp4_dense_qmm"]
GLUE = [f for f in FAM if f not in MMA and f != "attention_core"]


def pct(x):
    return 100.0 * x / WALL


def rule(c="-", n=104):
    print(c * n)


def main():
    fam_sum = sum(v[0] for v in FAM.values())
    assert abs(fam_sum + IDLE - WALL) < 1e-3, (fam_sum, IDLE, WALL)

    steel = FAM["steel_gemm_bf16"][0]
    non_steel = WALL - steel

    print("== HEADLINE ==")
    print(f"  steel_gemm*      {steel:8.3f} ms  {pct(steel):6.2f}%")
    print(f"  NOT steel_gemm*  {non_steel:8.3f} ms  {pct(non_steel):6.2f}%   <-- headline")
    rule()

    print("== DECOMPOSITION OF THE NON-steel_gemm SHARE ==")
    other_mm = FAM["routed_gather_gemm"][0] + FAM["nvfp4_dense_qmm"][0]
    attn = FAM["attention_core"][0]
    glue = sum(FAM[f][0] for f in GLUE)
    glue_gb = sum(FAM[f][1] for f in GLUE)
    for label, ms in (
        ("other matmul (gather-GEMM + nvfp4 dense)", other_mm),
        ("attention core (also MMA)", attn),
        ("true non-matmul glue", glue),
        ("GPU-idle (unattributed)", IDLE),
    ):
        print(f"  {label:42s} {ms:8.3f} ms  {pct(ms):6.2f}%")
    print(f"  {'sum':42s} {other_mm + attn + glue + IDLE:8.3f} ms  "
          f"{pct(other_mm + attn + glue + IDLE):6.2f}%")
    mm_total = sum(FAM[f][0] for f in MMA)
    print(f"\n  matmul (3 families)        {mm_total:8.3f} ms  {pct(mm_total):6.2f}%")
    print(f"  matmul + attention         {mm_total + attn:8.3f} ms  {pct(mm_total + attn):6.2f}%")
    print(f"  non-MMA glue + idle        {glue + IDLE:8.3f} ms  {pct(glue + IDLE):6.2f}%")
    print(f"  glue bytes bound           {glue_gb:8.3f} GB")
    rule()

    print(f"== MMA ROOFLINE (M4 peak {M4_TFLOPS} TFLOP/s, DRAM {M4_DRAM} GB/s, "
          f"balance {M4_TFLOPS*1e3/M4_DRAM:.1f} FLOP/B) ==")
    print(f"  {'family':22s} {'GFLOP':>8s} {'TFLOP/s':>8s} {'%peak':>7s} "
          f"{'AI':>7s} {'floor':>8s} {'headroom':>9s}")
    for f in MMA + ["attention_core"]:
        ms, gb = FAM[f]
        gf = GFLOP[f]
        tflops = gf / ms  # GFLOP/ms == TFLOP/s
        ai = gf / gb  # GFLOP/GB == FLOP/B
        floor = gf / M4_TFLOPS
        print(f"  {f:22s} {gf:8.1f} {tflops:8.2f} {100*tflops/M4_TFLOPS:6.1f}% "
              f"{ai:7.1f} {floor:7.2f}ms {ms-floor:8.2f}ms")
    for f, gf in GFLOP_ALT.items():
        ms = FAM[f][0]
        print(f"  {f+' (alt GFLOP)':22s} {gf:8.1f} {gf/ms:8.2f} "
              f"{100*gf/ms/M4_TFLOPS:6.1f}% {gf/FAM[f][1]:7.1f} "
              f"{gf/M4_TFLOPS:7.2f}ms {ms-gf/M4_TFLOPS:8.2f}ms")
    rule()

    print(f"== GLUE ROOFLINE (DRAM-bound; floor = bytes / {M4_DRAM} GB/s) ==")
    print(f"  {'family':22s} {'GB':>7s} {'ms':>8s} {'GB/s':>8s} {'%roof':>7s} "
          f"{'floor':>8s} {'headroom':>9s}")
    glue_headroom = 0.0
    for f in sorted(GLUE, key=lambda k: -FAM[k][0]):
        ms, gb = FAM[f]
        if ms <= 0 or gb <= 0:
            print(f"  {f:22s} {gb:7.3f} {ms:8.3f} {'-':>8s} {'-':>7s} {'-':>8s} {'0.00':>7s}ms")
            continue
        rate = gb * 1e3 / ms
        floor = gb * 1e3 / M4_DRAM
        head = max(0.0, ms - floor)
        glue_headroom += head
        print(f"  {f:22s} {gb:7.3f} {ms:8.3f} {rate:8.1f} {100*rate/M4_DRAM:6.0f}% "
              f"{floor:7.2f}ms {head:8.2f}ms")
    lo, hi = SCORE_PCT_PER_MS
    bar_lo, bar_hi = SCORE_BAR_PCT / hi, SCORE_BAR_PCT / lo

    # The DRAM roofline only bounds a family whose bytes dominate its runtime.
    # router binds 12 MB across 39 selection kernels; its roof is occupancy and
    # tournament latency, so charging it DRAM headroom is a category error.
    router_head = max(0.0, FAM["router"][0] - FAM["router"][1] * 1e3 / M4_DRAM)
    addressable = glue_headroom - router_head
    print(f"\n  nominal headroom (every family to 100% of DRAM roof)  {glue_headroom:6.2f} ms M4")
    print(f"    less router (bytes negligible -> not DRAM-bounded)   {router_head:6.2f} ms M4")
    print(f"    DRAM-addressable headroom, all in qk_norm_rope       {addressable:6.2f} ms M4")
    for label, ms4 in (("nominal", glue_headroom), ("DRAM-addressable", addressable)):
        ms5 = ms4 * M4_DRAM / M5_DRAM_ACHIEVED
        print(f"    {label:18s} -> M5 {ms5:.2f} ms = {100*ms5/M5_PREFILL_MS:.2f}% of M5 prefill "
              f"= {ms5*lo:.3f}-{ms5*hi:.3f}% of score")
    print(f"    bar for +{SCORE_BAR_PCT}% of score: {bar_lo:.2f}-{bar_hi:.2f} ms of M5 prefill")
    rule()

    print("== M4-ONLY ARTEFACT CORRECTION (lagunaExpertAlignedGatherEnabled == false) ==")
    g2_copy = 1.689
    sigmoid_total, sigmoid_n, sigmoid_routed = 1.532, 77, 38
    sigmoid_m4_only = sigmoid_total * sigmoid_routed / sigmoid_n
    artefact = g2_copy + sigmoid_m4_only
    print(f"  g2_copybfloat16bfloat16 (76 calls)          {g2_copy:6.3f} ms  M4-only")
    print(f"  routed silu-product ({sigmoid_routed}/{sigmoid_n} of chain)        "
          f"{sigmoid_m4_only:6.3f} ms  M4-only")
    print(f"  total glue that does not exist on M5        {artefact:6.3f} ms "
          f"= {100*artefact/glue:.1f}% of measured glue")
    print(f"  M5-relevant glue (M4 clock)                 {glue - artefact:6.3f} ms")
    m5_glue = (glue - artefact) * M4_DRAM / M5_DRAM_ACHIEVED
    print(f"  M5-relevant glue, bandwidth-scaled          {m5_glue:6.3f} ms "
          f"= {100*m5_glue/M5_PREFILL_MS:.2f}% of M5 prefill")
    rule()

    print("== DESK PRICE: top candidate ==")
    shared_silu = sigmoid_total * (sigmoid_n - sigmoid_routed) / sigmoid_n
    cands = [
        ("TOP: g2_Multiplybfloat16 gate-fold into o_proj prologue", 1.328, True),
        ("runner-up: shared-expert silu-product fold", shared_silu, True),
        ("ceiling: every M5-live byte-deletion lever at once", 1.328 + shared_silu, True),
        ("g2_copybfloat16bfloat16 strided-view removal", g2_copy, False),
    ]
    for name, ms_m4, live in cands:
        ms_m5 = ms_m4 * M4_DRAM / M5_DRAM_ACHIEVED
        print(f"  {name}")
        print(f"    M4 {ms_m4:.3f} ms -> M5 {ms_m5:.3f} ms "
              f"({100*ms_m5/M5_PREFILL_MS:.2f}% of M5 prefill)")
        print(f"    score value {ms_m5*lo:.3f}% (conservative) .. {ms_m5*hi:.3f}% (prospective)")
        print(f"    vs bar {SCORE_BAR_PCT}%: "
              f"{'CLEARS only under the prospective rate' if ms_m5*hi >= SCORE_BAR_PCT > ms_m5*lo else ('CLEARS' if ms_m5*lo >= SCORE_BAR_PCT else 'BELOW BAR')}")
        print(f"    live on ranked M5: {live}")
    rule()

    print("== VERDICT INPUTS ==")
    print(f"  matmul+attention share of prefill      {pct(mm_total + attn):.2f}%")
    print(f"  DRAM-addressable glue headroom (M5)    "
          f"{addressable * M4_DRAM / M5_DRAM_ACHIEVED:.2f} ms vs bar {bar_lo:.2f}-{bar_hi:.2f} ms")
    print(f"  attention core % of MMA peak           "
          f"{100*GFLOP['attention_core']/FAM['attention_core'][0]/M4_TFLOPS:.1f}%")
    print(f"  steel_gemm % of MMA peak               "
          f"{100*GFLOP['steel_gemm_bf16']/steel/M4_TFLOPS:.1f}%")
    print(f"  gather-GEMM % of MMA peak              "
          f"{100*GFLOP['routed_gather_gemm']/FAM['routed_gather_gemm'][0]/M4_TFLOPS:.1f}%")


if __name__ == "__main__":
    main()
