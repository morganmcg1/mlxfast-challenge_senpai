# checkpoint slab census
dir: weights
tensors: 912   slabs: 60582
slab bytes: 20.08 GiB  (21561408512)
mode: entropy

## enumerator self-check

- distinct (shard, offset) sites: 60582 of 60582 slabs
- repeated sites: 0   overlapping slabs: 0   out-of-range slabs: 0
- verdict: PASS

## inventory by role

| role | slabs | bytes each | total bytes | share |
|---|---|---|---|---|
| `routed.up_proj.weight` | 9984 | 524288 | 5234491392 | 24.2771% |
| `routed.gate_proj.weight` | 9984 | 524288 | 5234491392 | 24.2771% |
| `routed.down_proj.weight` | 9984 | 524288 | 5234491392 | 24.2771% |
| `attn.q_proj.weight` | 40 | mixed | 1258291200 | 5.8358% |
| `attn.o_proj.weight` | 40 | mixed | 1258291200 | 5.8358% |
| `routed.up_proj.scales` | 9984 | 65536 | 654311424 | 3.0346% |
| `routed.down_proj.scales` | 9984 | 65536 | 654311424 | 3.0346% |
| `routed.gate_proj.scales` | 9984 | 65536 | 654311424 | 3.0346% |
| `lm_head.weight` | 1 | 411041792 | 411041792 | 1.9064% |
| `model.embed_tokens.weight` | 1 | 411041792 | 411041792 | 1.9064% |
| `attn.k_proj.weight` | 40 | 4194304 | 167772160 | 0.7781% |
| `attn.v_proj.weight` | 40 | 4194304 | 167772160 | 0.7781% |
| `router.weight` | 39 | 1048576 | 40894464 | 0.1897% |
| `dense.down_proj.weight` | 1 | 33554432 | 33554432 | 0.1556% |
| `dense.up_proj.weight` | 1 | 33554432 | 33554432 | 0.1556% |
| `dense.gate_proj.weight` | 1 | 33554432 | 33554432 | 0.1556% |
| `shared.gate_proj.weight` | 39 | 524288 | 20447232 | 0.0948% |
| `shared.down_proj.weight` | 39 | 524288 | 20447232 | 0.0948% |
| `shared.up_proj.weight` | 39 | 524288 | 20447232 | 0.0948% |
| `attn.g_proj.weight` | 40 | mixed | 9830400 | 0.0456% |
| `shared.gate_proj.scales` | 39 | 65536 | 2555904 | 0.0119% |
| `shared.down_proj.scales` | 39 | 65536 | 2555904 | 0.0119% |
| `shared.up_proj.scales` | 39 | 65536 | 2555904 | 0.0119% |
| `post_attention_layernorm.weight` | 40 | 4096 | 163840 | 0.0008% |
| `input_layernorm.weight` | 40 | 4096 | 163840 | 0.0008% |
| `router.e_score_correction_bias` | 39 | 1024 | 39936 | 0.0002% |
| `attn.q_norm.weight` | 40 | 256 | 10240 | 0.0000% |
| `attn.k_norm.weight` | 40 | 256 | 10240 | 0.0000% |
| `model.norm.weight` | 1 | 4096 | 4096 | 0.0000% |

## information-theoretic floor per role

A memoryless lossless recode cannot beat zeroth-order entropy.
`nibble H` is the relevant column for NVFP4 mantissa planes (4-bit
symbols); `byte H` is the relevant one for U8 scale planes.

| role | bytes measured | byte H (bits/8b) | nibble H (bits/4b) | distinct byte codes | fixed-width LUT bits | LUT saving | best lossless size | max saving |
|---|---|---|---|---|---|---|---|---|
| `attn.g_proj.weight` | 9.38 MiB | 6.2582 | 3.5989 | 256 | 8 | +0.00% | 8.43 MiB | +10.03% |
| `attn.k_norm.weight` | 10.00 KiB | 4.9325 | 3.3049 | 255 | 8 | +0.00% | 8.26 KiB | +17.38% |
| `attn.k_proj.weight` | 160.00 MiB | 6.2547 | 3.5523 | 256 | 8 | +0.00% | 142.09 MiB | +11.19% |
| `attn.o_proj.weight` | 1.17 GiB | 6.2353 | 3.5691 | 256 | 8 | +0.00% | 1.05 GiB | +10.77% |
| `attn.q_norm.weight` | 10.00 KiB | 4.8153 | 3.2626 | 253 | 8 | +0.00% | 8.16 KiB | +18.43% |
| `attn.q_proj.weight` | 1.17 GiB | 6.2759 | 3.5621 | 256 | 8 | +0.00% | 1.04 GiB | +10.95% |
| `attn.v_proj.weight` | 160.00 MiB | 6.2322 | 3.5682 | 256 | 8 | +0.00% | 142.73 MiB | +10.80% |
| `dense.down_proj.weight` | 32.00 MiB | 6.4138 | 3.6165 | 256 | 8 | +0.00% | 28.93 MiB | +9.59% |
| `dense.gate_proj.weight` | 32.00 MiB | 6.4396 | 3.6139 | 256 | 8 | +0.00% | 28.91 MiB | +9.65% |
| `dense.up_proj.weight` | 32.00 MiB | 6.4309 | 3.6179 | 256 | 8 | +0.00% | 28.94 MiB | +9.55% |
| `input_layernorm.weight` | 160.00 KiB | 5.1395 | 3.3109 | 256 | 8 | +0.00% | 132.44 KiB | +17.23% |
| `lm_head.weight` | 392.00 MiB | 6.2364 | 3.5643 | 256 | 8 | +0.00% | 349.30 MiB | +10.89% |
| `model.embed_tokens.weight` | 392.00 MiB | 6.2078 | 3.6189 | 256 | 8 | +0.00% | 354.65 MiB | +9.53% |
| `model.norm.weight` | 4.00 KiB | 4.5121 | 3.1262 | 156 | 8 | +0.00% | 3.13 KiB | +21.85% |
| `post_attention_layernorm.weight` | 160.00 KiB | 5.4336 | 3.3768 | 256 | 8 | +0.00% | 135.07 KiB | +15.58% |
| `routed.down_proj.scales` | 624.00 MiB | 2.4723 | 2.2364 | 42 | 6 | +25.00% | 192.84 MiB | +69.10% |
| `routed.down_proj.weight` (1/19 sample) | 263.00 MiB | 7.8810 | 3.9417 | 256 | 8 | +0.00% | 4.80 GiB | +1.46% |
| `routed.gate_proj.scales` | 624.00 MiB | 2.6002 | 2.3009 | 50 | 6 | +25.00% | 202.82 MiB | +67.50% |
| `routed.gate_proj.weight` (1/19 sample) | 263.00 MiB | 7.8860 | 3.9444 | 256 | 8 | +0.00% | 4.81 GiB | +1.39% |
| `routed.up_proj.scales` | 624.00 MiB | 2.6112 | 2.3061 | 57 | 6 | +25.00% | 203.68 MiB | +67.36% |
| `routed.up_proj.weight` (1/19 sample) | 263.00 MiB | 7.9003 | 3.9527 | 256 | 8 | +0.00% | 4.82 GiB | +1.18% |
| `router.e_score_correction_bias` | 39.00 KiB | 0.0000 | 0.0000 | 1 | 0 | +100.00% | 0 B | +100.00% |
| `router.weight` | 39.00 MiB | 6.2452 | 3.5823 | 256 | 8 | +0.00% | 34.93 MiB | +10.44% |
| `shared.down_proj.scales` | 2.44 MiB | 2.5080 | 2.2548 | 40 | 6 | +25.00% | 782.50 KiB | +68.65% |
| `shared.down_proj.weight` | 19.50 MiB | 7.8678 | 3.9356 | 256 | 8 | +0.00% | 19.19 MiB | +1.61% |
| `shared.gate_proj.scales` | 2.44 MiB | 2.7070 | 2.3515 | 35 | 6 | +25.00% | 844.57 KiB | +66.16% |
| `shared.gate_proj.weight` | 19.50 MiB | 7.8957 | 3.9508 | 256 | 8 | +0.00% | 19.26 MiB | +1.23% |
| `shared.up_proj.scales` | 2.44 MiB | 2.5835 | 2.2936 | 37 | 6 | +25.00% | 806.06 KiB | +67.71% |
| `shared.up_proj.weight` | 19.50 MiB | 7.9065 | 3.9575 | 256 | 8 | +0.00% | 19.29 MiB | +1.06% |

- bytes actually measured: 6.23 GiB
- checkpoint size: 20.08 GiB
- best-case memoryless lossless size: 18.25 GiB
- **maximum achievable saving from ANY memoryless lossless scheme: +9.09%**

- routed plane bytes: 16.45 GiB (81.9353% of checkpoint)

## per-slab scale alphabet (exhaustive)

| role | slabs | max codes in any slab | p50 | p99 | slabs >16 codes | LUT bits | scale-plane saving |
|---|---|---|---|---|---|---|---|
| `routed.down_proj.scales` | 9984 | 35 | 13 | 22 | 705 | 6 | +25.00% |
| `routed.gate_proj.scales` | 9984 | 38 | 13 | 26 | 2247 | 6 | +25.00% |
| `routed.up_proj.scales` | 9984 | 41 | 13 | 22 | 1301 | 6 | +25.00% |
| `shared.down_proj.scales` | 39 | 31 | 25 | 31 | 39 | 5 | +37.50% |
| `shared.gate_proj.scales` | 39 | 30 | 27 | 30 | 36 | 5 | +37.50% |
| `shared.up_proj.scales` | 39 | 31 | 24 | 31 | 36 | 5 | +37.50% |

wall total: 2.04 s
