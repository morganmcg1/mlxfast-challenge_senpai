# Arm G — folding the attention pre-norm out of its own dispatch

Host: Apple M4 Pro, 48 GiB, `applegpu_g16s`, 20 GPU cores, macOS 26.5.2. No
`_nax` kernels on this generation, so every number below is directional for the
ranked M5 and is reported as a per-kernel ratio rather than a score.

## Why the pre-norm is a target at all

Decode per-step kernel census (`research/r87a-runs/ceiling.json`,
`deltas.E0.per_kernel`, arm E0 reference microseconds per step):

| kernel | us/step | share |
| --- | --- | --- |
| routed_nvfp4_swiglu_qmv_packed_top8keys_r1_bf16_v2 | 1501.4 | 17.54% |
| decode_nvfp4_qkv_h64_r1_v1_lm1_pw1_se1_sd1 | 1340.7 | 15.66% |
| oproj_act_h64_v1_lm1_pw1_sc1_se1 | 1119.2 | 13.08% |
| routed_shared_nvfp4_down_residual_bf16_sh_stage4_v6 | 861.2 | 10.06% |
| sliding_fused_attn_ring_v1 | 627.3 | 7.33% |
| lmhead_int5_base_coarse_delta_bf16_v1 | 422.3 | 4.93% |
| decode_nvfp4_qkv_h48_r1_v1_lm1_pw1_se1_sd1 | 363.5 | 4.25% |
| residual_rms_router_bf16_2048_rpg8_keys_v1 | 320.1 | 3.74% |
| oproj_act_h48_v1_lm1_pw1_sc1_se1 | 302.9 | 3.54% |
| shared_nvfp4_swiglu_qmv_rows1_halved_bf16_v1 | 284.9 | 3.33% |
| dense_gate_up_swiglu_bf16_v1 | 269.4 | 3.15% |
| gate_sp_h64_v1 | 250.7 | 2.93% |
| full_fused_attn_grow_v1 | 249.5 | 2.92% |
| prefill_router_tournament_ordinal_norm_active64_v2 | 186.2 | 2.18% |
| rmsbfloat16 | 142.3 | 1.66% |
| dense_down_residual_bf16_v1 | 134.5 | 1.57% |

`rmsbfloat16` is 41 dispatches per decode step (40 attention pre-norms plus the
final norm) at 3.47 us each, for 8 KB of traffic per dispatch — about 0.6 GB/s,
i.e. essentially all launch overhead. The MLP-side pre-norm is already fused
(`residual_rms_router_bf16_2048_rpg8_keys_v1`); the attention side is not.

Two separate arm A0/E0 measurements also established that this decode step has
**zero kernel overlap**: `busy_sum == busy_union` (8558/8558 and 8472/8471 us)
with `cbs == dispatches == 406` and wall 9797/9716 us, so the 1229 us of
non-busy wall is 3.03 us of gap per command buffer. Deleting a dispatch
therefore removes ~3.5 us of busy *and* ~3.0 us of gap, and adding a RAW edge
between two kernels costs no lost overlap.

## Rung 1: fold the norm into the NVFP4 QKV matvec — decisive negative

`research/nezuko_armg_qkv_norm_probe.swift` slices the shipped
`lagunaTailNVFP4QMVHeader` and `lagunaDecodeNVFP4QKVLaneMajorSource` text out of
`LagunaRuntimeModel.swift`, resolves the interpolations to the live
`_lm1_pw1_se1_sd1` configuration, asserts six AOT `rms_norm.metal` expressions
are unchanged, and compiles six raw-Metal pipelines. Fixtures: rows 10240
(the h64 site), hidden 2048, 8 independent weight sets, one command buffer per
dispatch, busy from `gpuEndTime - gpuStartTime`, 3 warmups then 12 ABBA pairs
per set.

Reproduce:

```bash
xcrun swiftc -Onone research/nezuko_armg_qkv_norm_probe.swift -o /tmp/nezarmg_d
/tmp/nezarmg_d
```

Bit-exactness: the 64-thread / 2-simdgroup restatement of the AOT
`rms_single_row` laguna fast path reproduces **all 2048 `normalized` words and
all 10240 `projected` words exactly** — 0 mismatches across five residual
distributions (standard, wide, tiny, near-zero, heavy-tail) for the no-emit,
hoisted-emit and in-loop-emit arms. Simdgroup `sg` owns AOT chunks
`8*sg ..< 8*sg+8`, each lane accumulates the same four contiguous squares in the
same order into the same `local_sums` slot, and the final 32-lane `simd_sum`
sees an identical operand vector.

Cost (192 samples per arm, median us per dispatch):

| arm | median | p10 | ratio | QKV growth us/step | net busy us/step | net score % |
| --- | --- | --- | --- | --- | --- | --- |
| A stock | 34.25 | 33.54 | 1.000 | — | — | — |
| P prologue only (timing-only) | 35.04 | 33.75 | 1.023 | +39.4 | −102.9 | +0.688 |
| N no-emit | 55.31 | 54.75 | 1.615 | +1048.0 | +905.7 | −6.057 |
| H hoisted-emit (correct) | 55.50 | 55.08 | 1.620 | +1057.4 | +915.1 | −6.119 |
| L in-loop-emit | 163.46 | 162.79 | 4.773 | +6429.1 | +6286.8 | −42.04 |

Break-even for deleting the 41 `rmsbfloat16` dispatches is +142.3 us/step across
the QKV pool (1340.7 h64 + 363.5 h48 = 1704.2 us/step), i.e. ratio 1.0835.
Fidelity check: arm A's effective code bandwidth is 306.2 GB/s against 235 GB/s
for the live scored h64 dispatch (44.7 us), so the probe is not
launch-overhead-dominated.

Attribution is unambiguous:

- the RMS **reduction** is nearly free (P: +2.3%), and
- **emitting** `normalized` is free when hoisted out of the main loop
  (H − N = +0.005 ratio), but
- **recomputing the normalize per element inside the main loop** costs +59%.

Generalizable lesson: fusing a small elementwise producer into a many-
threadgroup matvec multiplies the producer's cost by the threadgroup count. The
2048-element RMS costs 2048 ops standalone but 5120 × 2048 = 10.5M ops when
recomputed per threadgroup. The in-loop store form is additionally catastrophic
(4.77x), consistent with store/load aliasing in the hot loop.

Alternatives rejected before measuring: threadgroup staging of `normalized`
(4 KB/TG caps residency at ~8 TG/core versus 48, and only halves the ALU);
folding the norm weight into the NVFP4 weights offline (not bit-exact); a
per-lane 64-float register cache (spills).

## Rung 1b: host the reduction in `gate_sp` instead

`normalized` has exactly two live consumers on the scored decode path:
`lagunaDecodeNVFP4QKVR1` (5120 threadgroups) and
`lagunaGateSoftplus` (`heads / 8` = **8** threadgroups of 64 threads). Rung 1's
attribution says the fusion is only lost to the per-threadgroup multiplier, so
the same bit-exact prologue pays 8 × 2048 elementwise ops instead of
5120 × 2048 — a 640x smaller redundancy — and can publish `normalized` as a
second output for the QKV dispatch.

`Sources/MLXFastModel/LagunaNormFusedGateSoftplus.swift` implements
`laguna_gate_sp_rms_h{48,64}_v1`: the validated 64-thread reduction, then
`normalized` written once by threadgroup 0 simdgroup 0, then the unchanged
`gate_sp` body with `float(input[col+i])` replaced by the same normalize
expression. Eligibility mirrors the existing gate-softplus branch exactly, so a
layer that does not dispatch `gate_sp` keeps the two-kernel form, and prefill
(L = 512) is untouched.
