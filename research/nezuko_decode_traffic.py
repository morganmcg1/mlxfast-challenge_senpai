H, HD, KVH = 2048, 128, 8
SLID_H, FULL_H = 64, 48
L, LSL, LFU = 40, 30, 10
E, TOPK, EI, SI = 256, 8, 512, 512
VOCAB = 100352
NVFP4_B = (16 * 4 / 8 + 1) / 16          # 4-bit + 1 E4M3 scale per 16
BF16_B = 2.0
INT8G32_B = 1.0 + 8.0 / 32.0             # int8 + fp32 scale/bias per 32

MB = 1024.0 ** 2
GB = 1024.0 ** 3


def expert_params(inter):
    return 3 * H * inter


routed_all = E * 39 * expert_params(EI) * NVFP4_B
shared_all = 39 * expert_params(SI) * NVFP4_B
dense0 = 3 * H * 8192 * BF16_B
attn_sl_p = 2 * H * SLID_H * HD + 2 * H * KVH * HD
attn_fu_p = 2 * H * FULL_H * HD + 2 * H * KVH * HD
attn_all_bf16 = (LSL * attn_sl_p + LFU * attn_fu_p) * BF16_B
lm_head = H * VOCAB * BF16_B
embed = VOCAB * H * BF16_B
routers = 39 * H * E * BF16_B

total = routed_all + shared_all + dense0 + attn_all_bf16 + lm_head + embed + routers
print("=== checkpoint accounting (validates the param model) ===")
print(f"routed experts (all 256)  {routed_all/GB:8.3f} GB")
print(f"shared experts            {shared_all/GB:8.3f} GB")
print(f"dense MLP layer 0         {dense0/GB:8.3f} GB")
print(f"attention q/k/v/o bf16    {attn_all_bf16/GB:8.3f} GB")
print(f"lm_head + embed + routers {(lm_head+embed+routers)/GB:8.3f} GB")
print(f"TOTAL                     {total/GB:8.3f} GB   (stated resident: ~21.6 GB)")

kv_sl = LSL * 512 * KVH * HD * 2 * BF16_B
kv_fu = LFU * 576 * KVH * HD * 2 * BF16_B
moe_step = (TOPK * 39 * expert_params(EI) * NVFP4_B) + shared_all
attn_int8 = (LSL * attn_sl_p + LFU * attn_fu_p) * INT8G32_B

print("\n=== per-decode-step DRAM traffic at batch 1 ===")
print(f"routed top-8 + shared     {moe_step/MB:8.1f} MB")
print(f"KV cache read             {(kv_sl+kv_fu)/MB:8.1f} MB")
print(f"dense0 + routers          {(dense0+routers)/MB:8.1f} MB")
print(f"attention  bf16           {attn_all_bf16/MB:8.1f} MB")
print(f"attention  int8 g32       {attn_int8/MB:8.1f} MB")
print(f"lm_head    bf16           {lm_head/MB:8.1f} MB")

floor = moe_step + kv_sl + kv_fu + dense0 + routers
hi = floor + attn_all_bf16 + lm_head
lo = floor + attn_int8
print(f"\nHARD FLOOR (zero attention, zero lm_head) {floor/MB:8.1f} MB")
print(f"int8 attention, no lm_head cost           {lo/MB:8.1f} MB")
print(f"bf16 attention + full lm_head             {hi/MB:8.1f} MB")

STEP_M4 = 8290e-6
STEP_M5 = 4165e-6
BW_M4 = 273e9
print(f"\nM4 Pro measured step {STEP_M4*1e6:.0f} us; peak BW {BW_M4/1e9:.0f} GB/s")
print(f"  bytes deliverable in one step at peak: {BW_M4*STEP_M4/MB:.1f} MB")
for name, b in (("hard floor", floor), ("int8 attn", lo), ("bf16 attn+head", hi)):
    print(f"  {name:16s} -> {b/STEP_M4/1e9:7.1f} GB/s  = {100*b/(BW_M4*STEP_M4):6.1f} % of peak")
print(f"\nstep ratio M4/M5 = {STEP_M4/STEP_M5:.3f}")
print(f"  implied M5 bandwidth if bandwidth-bound = {BW_M4*STEP_M4/STEP_M5/1e9:.0f} GB/s")
