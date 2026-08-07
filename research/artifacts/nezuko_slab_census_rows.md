# checkpoint slab census
dir: weights
tensors: 912   slabs: 60582
slab bytes: 20.08 GiB  (21561408512)
mode: rows

## enumerator self-check

- distinct (shard, offset) sites: 60582 of 60582 slabs
- repeated sites: 0   overlapping slabs: 0   out-of-range slabs: 0
- verdict: PASS

## inventory by role

| role | slabs | bytes each | total bytes | share |
|---|---|---|---|---|
| `routed.gate_proj.weight` | 9984 | 524288 | 5234491392 | 24.2771% |
| `routed.up_proj.weight` | 9984 | 524288 | 5234491392 | 24.2771% |
| `routed.down_proj.weight` | 9984 | 524288 | 5234491392 | 24.2771% |
| `attn.o_proj.weight` | 40 | mixed | 1258291200 | 5.8358% |
| `attn.q_proj.weight` | 40 | mixed | 1258291200 | 5.8358% |
| `routed.down_proj.scales` | 9984 | 65536 | 654311424 | 3.0346% |
| `routed.up_proj.scales` | 9984 | 65536 | 654311424 | 3.0346% |
| `routed.gate_proj.scales` | 9984 | 65536 | 654311424 | 3.0346% |
| `lm_head.weight` | 1 | 411041792 | 411041792 | 1.9064% |
| `model.embed_tokens.weight` | 1 | 411041792 | 411041792 | 1.9064% |
| `attn.k_proj.weight` | 40 | 4194304 | 167772160 | 0.7781% |
| `attn.v_proj.weight` | 40 | 4194304 | 167772160 | 0.7781% |
| `router.weight` | 39 | 1048576 | 40894464 | 0.1897% |
| `dense.down_proj.weight` | 1 | 33554432 | 33554432 | 0.1556% |
| `dense.gate_proj.weight` | 1 | 33554432 | 33554432 | 0.1556% |
| `dense.up_proj.weight` | 1 | 33554432 | 33554432 | 0.1556% |
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
| `attn.k_norm.weight` | 40 | 256 | 10240 | 0.0000% |
| `attn.q_norm.weight` | 40 | 256 | 10240 | 0.0000% |
| `model.norm.weight` | 1 | 4096 | 4096 | 0.0000% |

## sub-slab row census

Row-level duplicate structure inside each role. A row is the innermost
contiguous dimension of a slab. This is NOT part of the Step 0 gate: a
row-level dedup needs a per-row indirection whose own bytes must be paid.

| role | rows | row bytes | distinct rows | removable rows | removable bytes | index cost @ 4B/row | net bytes |
|---|---|---|---|---|---|---|---|
| `attn.g_proj.weight` | 2400 | 4096 | 2400 | 0 (0.0000%) | 0 | 0 | 0 |
| `attn.k_proj.weight` | 40960 | 4096 | 40960 | 0 (0.0000%) | 0 | 0 | 0 |
| `attn.o_proj.weight` | 81920 | 16384 | 81920 | 0 (0.0000%) | 0 | 0 | 0 |
| `attn.q_proj.weight` | 307200 | 4096 | 307200 | 0 (0.0000%) | 0 | 0 | 0 |
| `attn.v_proj.weight` | 40960 | 4096 | 40960 | 0 (0.0000%) | 0 | 0 | 0 |
| `dense.down_proj.weight` | 2048 | 16384 | 2048 | 0 (0.0000%) | 0 | 0 | 0 |
| `dense.gate_proj.weight` | 8192 | 4096 | 8192 | 0 (0.0000%) | 0 | 0 | 0 |
| `dense.up_proj.weight` | 8192 | 4096 | 8192 | 0 (0.0000%) | 0 | 0 | 0 |
| `lm_head.weight` | 100352 | 4096 | 100288 | 64 (0.0638%) | 262144 | 401408 | -139264 |
| `model.embed_tokens.weight` | 100352 | 4096 | 100352 | 0 (0.0000%) | 0 | 0 | 0 |
| `routed.down_proj.scales` (1/8 sample) | 2555904 | 32 | 2555686 | 218 (0.0085%) | 6976 | 10223616 | -10216640 |
| `routed.down_proj.weight` (1/8 sample) | 2555904 | 256 | 2555904 | 0 (0.0000%) | 0 | 0 | 0 |
| `routed.gate_proj.scales` (1/8 sample) | 638976 | 128 | 638976 | 0 (0.0000%) | 0 | 0 | 0 |
| `routed.gate_proj.weight` (1/8 sample) | 638976 | 1024 | 638976 | 0 (0.0000%) | 0 | 0 | 0 |
| `routed.up_proj.scales` (1/8 sample) | 638976 | 128 | 638976 | 0 (0.0000%) | 0 | 0 | 0 |
| `routed.up_proj.weight` (1/8 sample) | 638976 | 1024 | 638976 | 0 (0.0000%) | 0 | 0 | 0 |
| `router.weight` | 9984 | 4096 | 9984 | 0 (0.0000%) | 0 | 0 | 0 |
| `shared.down_proj.scales` | 79872 | 32 | 79871 | 1 (0.0013%) | 32 | 319488 | -319456 |
| `shared.down_proj.weight` | 79872 | 256 | 79872 | 0 (0.0000%) | 0 | 0 | 0 |
| `shared.gate_proj.scales` | 19968 | 128 | 19968 | 0 (0.0000%) | 0 | 0 | 0 |
| `shared.gate_proj.weight` | 19968 | 1024 | 19968 | 0 (0.0000%) | 0 | 0 | 0 |
| `shared.up_proj.scales` | 19968 | 128 | 19968 | 0 (0.0000%) | 0 | 0 | 0 |
| `shared.up_proj.weight` | 19968 | 1024 | 19968 | 0 (0.0000%) | 0 | 0 | 0 |

wall total: 4.70 s
