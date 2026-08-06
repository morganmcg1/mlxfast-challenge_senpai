# checkpoint slab census
dir: weights
tensors: 912   slabs: 60582
slab bytes: 20.08 GiB  (21561408512)
mode: full

## enumerator self-check

- distinct (shard, offset) sites: 60582 of 60582 slabs
- repeated sites: 0   overlapping slabs: 0   out-of-range slabs: 0
- verdict: PASS

## inventory by role

| role | slabs | bytes each | total bytes | share |
|---|---|---|---|---|
| `routed.down_proj.weight` | 9984 | 524288 | 5234491392 | 24.2771% |
| `routed.gate_proj.weight` | 9984 | 524288 | 5234491392 | 24.2771% |
| `routed.up_proj.weight` | 9984 | 524288 | 5234491392 | 24.2771% |
| `attn.o_proj.weight` | 40 | mixed | 1258291200 | 5.8358% |
| `attn.q_proj.weight` | 40 | mixed | 1258291200 | 5.8358% |
| `routed.down_proj.scales` | 9984 | 65536 | 654311424 | 3.0346% |
| `routed.gate_proj.scales` | 9984 | 65536 | 654311424 | 3.0346% |
| `routed.up_proj.scales` | 9984 | 65536 | 654311424 | 3.0346% |
| `lm_head.weight` | 1 | 411041792 | 411041792 | 1.9064% |
| `model.embed_tokens.weight` | 1 | 411041792 | 411041792 | 1.9064% |
| `attn.v_proj.weight` | 40 | 4194304 | 167772160 | 0.7781% |
| `attn.k_proj.weight` | 40 | 4194304 | 167772160 | 0.7781% |
| `router.weight` | 39 | 1048576 | 40894464 | 0.1897% |
| `dense.up_proj.weight` | 1 | 33554432 | 33554432 | 0.1556% |
| `dense.gate_proj.weight` | 1 | 33554432 | 33554432 | 0.1556% |
| `dense.down_proj.weight` | 1 | 33554432 | 33554432 | 0.1556% |
| `shared.up_proj.weight` | 39 | 524288 | 20447232 | 0.0948% |
| `shared.gate_proj.weight` | 39 | 524288 | 20447232 | 0.0948% |
| `shared.down_proj.weight` | 39 | 524288 | 20447232 | 0.0948% |
| `attn.g_proj.weight` | 40 | mixed | 9830400 | 0.0456% |
| `shared.gate_proj.scales` | 39 | 65536 | 2555904 | 0.0119% |
| `shared.down_proj.scales` | 39 | 65536 | 2555904 | 0.0119% |
| `shared.up_proj.scales` | 39 | 65536 | 2555904 | 0.0119% |
| `input_layernorm.weight` | 40 | 4096 | 163840 | 0.0008% |
| `post_attention_layernorm.weight` | 40 | 4096 | 163840 | 0.0008% |
| `router.e_score_correction_bias` | 39 | 1024 | 39936 | 0.0002% |
| `attn.q_norm.weight` | 40 | 256 | 10240 | 0.0000% |
| `attn.k_norm.weight` | 40 | 256 | 10240 | 0.0000% |
| `model.norm.weight` | 1 | 4096 | 4096 | 0.0000% |

## hash pass

- bytes hashed: 20.08 GiB (21561408512)
- wall: 0.92 s
- fraction of checkpoint read: 100.0000%

## duplicate verdict — EXACT

- distinct classes: 60544 of 60582 slabs
- classes with >1 member: 1
- slabs in a duplicate class: 39 / 60582 = 0.0644%
- **removable (redundant) slabs: 38 / 60582 = 0.0627%**
- **removable bytes: 38.00 KiB / 20.08 GiB = 0.0002%**

### routed experts only (the arm's target)

- routed slabs: 59904, bytes 16.45 GiB
- removable slabs: 0 = 0.0000%
- **removable bytes: 0 B = 0.0000%**

### duplicate classes by role

| role | classes | members | removable slabs | removable bytes |
|---|---|---|---|---|
| `router.e_score_correction_bias` | 1 | 39 | 38 | 38912 |

### duplicate class-size histogram

| members per class | classes |
|---|---|
| 39 | 1 |

### duplicate classes (verified by memcmp)

- `router.e_score_correction_bias` len=1024 memcmp=OK distinct-offsets=YES : L9/e-1@s1+185173979 L7/e-1@s1+837201627 L6/e-1@s1+1736692699 L5/e-1@s1+2100680923 L1/e-1@s1+2890674139 L8/e-1@s1+2934458075 L3/e-1@s1+3321457371 L2/e-1@s1+3713831387 L4/e-1@s1+5025618651 L20/e-1@s2+28377 L17/e-1@s2+988251865 L16/e-1@s2+1206042073 L13/e-1@s2+1341309401 L15/e-1@s2+1628165849 L19/e-1@s2+2415459801 L12/e-1@s2+3674105817 L14/e-1@s2+3674307801 L10/e-1@s2+3875643865 L18/e-1@s2+4061906393 L11/e-1@s2+4330343129 L29/e-1@s3+375487538 L28/e-1@s3+882873138 L26/e-1@s3+1258666034 L25/e-1@s3+1871830578 L27/e-1@s3+2006377010 L23/e-1@s3+2746292786 L30/e-1@s3+4225274162 L21/e-1@s3+4565346610 L24/e-1@s3+4566986034 L22/e-1@s3+4945461554 L37/e-1@s4+880646778 L38/e-1@s4+1083621498 L35/e-1@s4+1274729850 L36/e-1@s4+1462114938 L33/e-1@s4+3577985146 L39/e-1@s4+3624451450 L31/e-1@s4+3624452474 L34/e-1@s4+4254713210 L32/e-1@s4+4313958778

- memcmp verified classes: 1, mismatched: 0
- classes whose members alias the same (shard, offset): 0

### degenerate slabs

- all-zero slabs: 39 (39.00 KiB)
- constant-byte non-zero slabs: 0

### near-duplicate line item: identical mantissa, differing scales

- routed mantissa slabs sharing bytes with another mantissa slab: 0
- (a mantissa-only match is NOT bit-exactly exploitable unless the paired scale plane also matches)

wall total: 0.94 s
