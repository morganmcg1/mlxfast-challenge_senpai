"""Prefill roofline decomposition and the attention-representation byte ledger.

Answers three questions the campaign had been guessing at:
  1. Is the 512-token forward compute-bound, bandwidth-bound, or at the ridge?
  2. Per block, which of the two floors binds, and what does perfect
     intra-kernel overlap buy?
  3. What does the shipped NVFP4-g16 attention representation save against the
     TASK.md envelope (group-32 affine INT8), i.e. how much of our position
     depends on the round-trip being exact?

All byte counts decimal (MB = 1e6 B), matching the campaign's GB/s arithmetic.
"""

H = 2048
LAYERS = 40
HEAD_DIM = 128
KV_HEADS = 8
FULL_ATTN_LAYERS = [l for l in range(LAYERS) if l % 4 == 0]  # 48 query heads
MOE_LAYERS = list(range(1, LAYERS))                          # layer 0 is dense
EXPERTS, TOPK, MOE_INTER = 256, 8, 512
DENSE_INTER = 8192
VOCAB = 100352
SEQ = 512

# Achievable ceilings on the ranked M5 Max (see CURRENT_RESEARCH_STATE.md).
DRAM_LO, DRAM_MID, DRAM_HI = 485e9, 500e9, 530e9
MMA_PEAK = 60e12

BF16, NVFP4_G16, INT8_G32 = 2.0, 0.5625, 1.125

S_MEASURED_MS = 98.153
ELASTICITY_S = 0.362
ELASTICITY_T = 0.638
DECODE_BYTES_MB = 1794.0


def heads(layer):
    return 48 if layer % 4 == 0 else 64


def qkvo_params():
    q = k = v = o = 0
    for l in range(LAYERS):
        w = heads(l) * HEAD_DIM
        q += w * H
        k += KV_HEADS * HEAD_DIM * H
        v += KV_HEADS * HEAD_DIM * H
        o += H * w
    return q, k, v, o


def gproj_params():
    return sum(heads(l) * H for l in range(LAYERS))


q, k, v, o = qkvo_params()
QKVO = q + k + v + o
GPROJ = gproj_params()

# One expert bank = gate+up+down at the MoE intermediate width.
EXPERT_PARAMS_PER_LAYER = EXPERTS * 3 * MOE_INTER * H
SHARED_PARAMS_PER_LAYER = 3 * MOE_INTER * H
ROUTER_PARAMS_PER_LAYER = EXPERTS * H
DENSE_MLP_PARAMS = 3 * DENSE_INTER * H

print("=" * 74)
print("PARAMETER INVENTORY")
print("=" * 74)
print(f"q_proj {q/1e6:10.2f} M   k_proj {k/1e6:8.2f} M   "
      f"v_proj {v/1e6:8.2f} M   o_proj {o/1e6:9.2f} M")
print(f"qkvo total            {QKVO/1e6:10.2f} M params")
print(f"g_proj total          {GPROJ/1e6:10.2f} M params")
print(f"routed experts        {EXPERT_PARAMS_PER_LAYER*len(MOE_LAYERS)/1e6:10.2f} M params"
      f"  ({len(MOE_LAYERS)} MoE layers)")
print(f"layer-0 dense MLP     {DENSE_MLP_PARAMS/1e6:10.2f} M params")
print(f"routers               {ROUTER_PARAMS_PER_LAYER*len(MOE_LAYERS)/1e6:10.2f} M params")

print()
print("=" * 74)
print("ATTENTION REPRESENTATION LEDGER  (what the NVFP4 claim is worth)")
print("=" * 74)
qkvo_bf16 = QKVO * BF16 / 1e6
qkvo_int8 = QKVO * INT8_G32 / 1e6
qkvo_nvfp4 = QKVO * NVFP4_G16 / 1e6
g_bf16, g_int8 = GPROJ * BF16 / 1e6, GPROJ * INT8_G32 / 1e6
print(f"qkvo as BF16        {qkvo_bf16:9.1f} MB   (what PREFILL reads today)")
print(f"qkvo as INT8 g32    {qkvo_int8:9.1f} MB   (the TASK.md envelope)")
print(f"qkvo as NVFP4 g16   {qkvo_nvfp4:9.1f} MB   (what DECODE reads today)")
print(f"g_proj BF16/INT8    {g_bf16:9.1f} /{g_int8:6.2f} MB")
print()
decode_attn_shipped = qkvo_nvfp4 + g_int8
decode_attn_envelope = qkvo_int8 + g_int8
print(f"decode attention stream, shipped   = {decode_attn_shipped:8.1f} MB"
      f"   (byte table row: 807.7)")
print(f"decode attention stream, envelope  = {decode_attn_envelope:8.1f} MB")
exposure = decode_attn_envelope - decode_attn_shipped
print(f"BYTES THE NVFP4 CLAIM IS WORTH     = {exposure:8.1f} MB/token"
      f"  = {100*exposure/DECODE_BYTES_MB:.1f}% of the decode budget")
print(f"  -> score at stake if the round-trip is NOT exact: "
      f"{100*ELASTICITY_T*exposure/DECODE_BYTES_MB:.1f}%")
print()
prefill_attn_saving = (qkvo_bf16 + g_bf16) - decode_attn_shipped
print(f"if PREFILL also used the decode banks: -{prefill_attn_saving:.1f} MB")

print()
print("=" * 74)
print("PREFILL ROOFLINE, PER BLOCK  (512-token forward)")
print("=" * 74)
# FLOP = 2 * params * tokens for every projection; attn_core scored separately.
blocks = []
blocks.append(("attn_proj_qkvo", 2 * QKVO * SEQ, qkvo_bf16))
blocks.append(("g_proj", 2 * GPROJ * SEQ, g_bf16))
# Experts: every token uses TOPK banks, but across 512 tokens the whole bank is
# resident-read once, minus the 20.26% of (layer,expert) pairs with zero rows.
expert_flop = 2 * (3 * MOE_INTER * H) * TOPK * len(MOE_LAYERS) * SEQ
expert_bytes = (EXPERT_PARAMS_PER_LAYER * len(MOE_LAYERS)
                * NVFP4_G16 * (1 - 0.2026) / 1e6)
blocks.append(("routed_experts", expert_flop, expert_bytes))
blocks.append(("shared_expert",
               2 * SHARED_PARAMS_PER_LAYER * len(MOE_LAYERS) * SEQ,
               SHARED_PARAMS_PER_LAYER * len(MOE_LAYERS) * NVFP4_G16 / 1e6))
blocks.append(("dense_mlp_layer0", 2 * DENSE_MLP_PARAMS * SEQ,
               DENSE_MLP_PARAMS * BF16 / 1e6))
blocks.append(("router", 2 * ROUTER_PARAMS_PER_LAYER * len(MOE_LAYERS) * SEQ,
               ROUTER_PARAMS_PER_LAYER * len(MOE_LAYERS) * BF16 / 1e6))
# Attention core: QK^T and PV over the causal/sliding masks.
attn_core = 0
for l in range(LAYERS):
    n = heads(l)
    span = SEQ if l % 4 == 0 else min(SEQ, 512)
    attn_core += 2 * 2 * n * HEAD_DIM * SEQ * span / 2  # causal halves it
blocks.append(("attn_core", attn_core, 0.0))

print(f"{'block':<18}{'GFLOP':>9}{'MB':>10}{'FLOP/B':>9}"
      f"{'cmp ms':>8}{'dram ms':>9}{'binds':>7}{'ovl ms':>8}")
tot_flop = tot_bytes = 0.0
serial_ms = overlap_ms = 0.0
for name, flop, mb in blocks:
    cmp_ms = flop / MMA_PEAK * 1e3
    dram_ms = mb * 1e6 / DRAM_MID * 1e3
    inten = flop / (mb * 1e6) if mb else float("inf")
    binds = "cmp" if cmp_ms > dram_ms else "dram"
    ovl = max(cmp_ms, dram_ms)
    print(f"{name:<18}{flop/1e9:9.1f}{mb:10.1f}"
          f"{inten:9.1f}{cmp_ms:8.2f}{dram_ms:9.2f}{binds:>7}{ovl:8.2f}")
    tot_flop += flop
    tot_bytes += mb
    serial_ms += cmp_ms + dram_ms
    overlap_ms += ovl

print("-" * 74)
print(f"{'TOTAL':<18}{tot_flop/1e9:9.1f}{tot_bytes:10.1f}"
      f"{tot_flop/(tot_bytes*1e6):9.1f}"
      f"{tot_flop/MMA_PEAK*1e3:8.2f}{tot_bytes*1e6/DRAM_MID*1e3:9.2f}")

print()
print("=" * 74)
print("THE RIDGE")
print("=" * 74)
ridge = MMA_PEAK / DRAM_MID
inten = tot_flop / (tot_bytes * 1e6)
print(f"machine balance point   = {ridge:6.1f} FLOP/byte  "
      f"({MMA_PEAK/1e12:.0f} TFLOP/s / {DRAM_MID/1e9:.0f} GB/s)")
print(f"forward arithmetic int. = {inten:6.1f} FLOP/byte")
print(f"ratio                   = {inten/ridge:6.3f}   "
      f"-> the 512-token forward sits ON the roofline ridge")
print()
print(f"global compute floor      {tot_flop/MMA_PEAK*1e3:7.2f} ms")
print(f"global DRAM floor         {tot_bytes*1e6/DRAM_MID*1e3:7.2f} ms  "
      f"({tot_bytes*1e6/DRAM_HI*1e3:.1f}-{tot_bytes*1e6/DRAM_LO*1e3:.1f} at "
      f"{DRAM_HI/1e9:.0f}-{DRAM_LO/1e9:.0f} GB/s)")
print(f"perfectly SERIAL sum      {serial_ms:7.2f} ms   <- what we appear to run")
print(f"per-kernel OVERLAP sum    {overlap_ms:7.2f} ms   <- realistic ceiling")
print(f"measured S                {S_MEASURED_MS:7.2f} ms")
print()
glue_lo, glue_hi = 9.0, 12.0
for label, floor in (("per-kernel overlap + glue", overlap_ms),):
    for g in (glue_lo, glue_hi):
        tgt = floor + g
        win = (S_MEASURED_MS - tgt) / S_MEASURED_MS
        print(f"{label} {g:.0f} ms -> S {tgt:6.2f} ms = "
              f"{100*win:5.1f}% of S = {100*ELASTICITY_S*win:4.1f}% of score")

print()
print("=" * 74)
print("FERN'S ARM (#24): the expert kernel is the BANDWIDTH-BOUND block")
print("=" * 74)
ef, eb = expert_flop, expert_bytes
e_cmp, e_dram = ef / MMA_PEAK * 1e3, eb * 1e6 / DRAM_MID * 1e3
print(f"routed_experts: compute {e_cmp:.2f} ms, DRAM {e_dram:.2f} ms "
      f"({eb*1e6/DRAM_HI*1e3:.1f}-{eb*1e6/DRAM_LO*1e3:.1f} ms at "
      f"{DRAM_HI/1e9:.0f}-{DRAM_LO/1e9:.0f} GB/s)")
print(f"serial  {e_cmp+e_dram:.2f} ms   perfect overlap {max(e_cmp,e_dram):.2f} ms")
for share in (0.45, 0.50):
    cur = share * S_MEASURED_MS
    win_ms = cur - max(e_cmp, e_dram)
    print(f"  at {100*share:.0f}% of S = {cur:.1f} ms today -> floor "
          f"{max(e_cmp,e_dram):.1f} ms: win {win_ms:.1f} ms = "
          f"{100*win_ms/S_MEASURED_MS:.1f}% of S = "
          f"{100*ELASTICITY_S*win_ms/S_MEASURED_MS:.1f}% of score")
print()
print("Perfect overlap CANNOT beat the DRAM floor for this block: staging IS")
print("the DRAM read. Double buffering converts serial(cmp+dram) -> max(), so")
print("the prize is the compute time it hides, not the staging time it removes.")

print()
print("=" * 74)
print("SHARED EXPERT / ROUTED EXPERT CONCURRENCY (independent sub-graphs)")
print("=" * 74)
sh_flop = 2 * SHARED_PARAMS_PER_LAYER * len(MOE_LAYERS) * SEQ
sh_cmp = sh_flop / MMA_PEAK * 1e3
print(f"shared_expert is compute-bound ({sh_cmp:.2f} ms) and consumes the same")
print(f"post-attention hidden state as the routed experts; outputs are summed.")
print(f"Hiding it entirely inside the routed DRAM stall: {sh_cmp:.2f} ms = "
      f"{100*sh_cmp/S_MEASURED_MS:.1f}% of S = "
      f"{100*ELASTICITY_S*sh_cmp/S_MEASURED_MS:.2f}% of score")
