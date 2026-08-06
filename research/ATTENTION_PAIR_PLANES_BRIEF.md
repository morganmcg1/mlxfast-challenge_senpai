# JIT Attention pair_planes 2→4 Assignment Brief

## Ready-to-Assign Experiment

This is the assignment body for the JIT fused attention pair_planes 2→4 experiment.
When a student becomes available, use this brief with the assign-experiment skill.

## Assignment Body

## Experiment: JIT Fused Attention Epilogue pair_planes 2→4 (collapse 3 barriers to 1)

### Causal Question
The JIT fused attention kernels (sliding and full) use `pair_planes = 2` in their epilogue, requiring 3 barriers per kernel call. The stock SDPA vector kernel already uses PLANES=4 (1 barrier). Can collapsing the JIT epilogue to a single round with pair_planes=4 reduce barrier overhead and improve decode throughput?

### Target Evidence
Two JIT fused attention kernels on the scored decode path:
- Sliding fused attention (`lagunaSlidingFusedAttentionKernel`): threadgroup alloc L1495, epilogue L1607-1667
- Full fused attention (`lagunaFullFusedAttentionKernel`): threadgroup alloc L1957, epilogue L2104-2164

Both use `pair_planes = 2` (L1610/2106). The epilogue does two rounds of threadgroup exchange:
- Round 1: write elements 0,1 → barrier → read → barrier (L1617-1654)
- Round 2: write elements 2,3 → barrier → read (L1646-1667)
- Total: 3 barriers (L1623, L1646, L1654)

The stock SDPA vector kernel (sdpa_vector.h L723-732) already uses PLANES=4 with a single barrier round, measured +0.60% (12/12 pairs, shipped).

### Expected Signal
~0.4% decode improvement. 2 fewer barriers per kernel call × 40 attention layers = 80 fewer barriers per decode step. Barriers are pipeline stalls on the instruction-bound M5.

### Numerical Risk
**Bit-exact.** Each element writes to its own dedicated plane — no RAW or WAR hazard within a round. The producer/consumer lane pairing and simd_sum reduction tree are identical per element. The plane base offset is an additive constant for both writer and reader. This is the same argument as the stock PLANES=4 optimization.

Threadgroup memory: increases from `4 * BN * BDP` to `8 * BN * BDP`:
- 8 × 32 × 33 = 8448 bytes + 512 bytes (max/sum) = 8960 bytes
- Well within 32 KiB threadgroup limit
- Kernel uses 128 threads (4 simdgroups), so occupancy is unaffected

### Implementation Details

**Submitted paths:** `Sources/MLXFastModel/LagunaRuntimeModel.swift`

**Sliding kernel (L1495, L1607-1667):**
1. Change threadgroup `outputs` allocation from `4 * BN * BDP` to `8 * BN * BDP` (L1495)
2. Change `pair_planes` from 2 to 4 (L1610)
3. Collapse the two-round exchange into one round: write all 4 elements, single barrier, read all 4
4. Remove the 2nd and 3rd barriers

**Full kernel (L1957, L2104-2164):**
Same changes as sliding kernel.

### Stop Rule
- **Green:** bit-exact, same-host seconds/token gain → proceed to --local-submit
- **Dead:** no gain (barrier overhead may be hidden by other latency)
- **Invalid:** correctness failure (threadgroup memory overflow or race condition)

### Budget
File: LagunaRuntimeModel.swift at ~510K / 524,288 bytes. The change adds ~100-200 bytes (larger allocation + restructured loop). Total surface: ~2,967K / 3,000,000 bytes. Headroom: ~33K bytes.
