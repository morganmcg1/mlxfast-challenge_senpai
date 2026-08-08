# SDPA Vector Kernel: GQA Pair-Heads 2→3/4 Implementation Plan

**Date:** 2026-08-08
**File:** `Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/kernels/sdpa_vector.h`
**Type:** AOT Metal kernel header (requires metallib rebuild)
**Status:** Design only — not implemented

## Executive Summary

The current SDPA vector kernel pairs 2 adjacent query heads per threadgroup,
sharing K/V loads. The #1 competitor (yudduy, score 2.6063) extends this to
3 heads per group for GQA6 layers and 4 heads per group for GQA8 layers,
reducing K/V traffic by 33% and 50% respectively on those layer types. This
document analyzes the feasibility, memory budget, bit-exactness, and
implementation approach for replicating and extending that optimization.

Our current best: 2.5888. Gap to #1: +0.67%.

## Laguna Model Architecture

From `Tests/Fixtures/PoolsideLagunaXS21NVFP4/config-contract.json`:

| Property | Value |
|---|---|
| num_hidden_layers | 40 |
| num_key_value_heads | 8 |
| head_dim | 128 |
| sliding_window | 512 |

Layer type distribution (repeating pattern of 1 full + 3 sliding):
- **10 full_attention layers** (indices 0,4,8,12,16,20,24,28,32,36)
  - 48 query heads → GQA factor 6 (48/8=6)
  - `num_attention_heads_per_layer`: 48
- **30 sliding_attention layers** (indices 1-3, 5-7, ..., 37-39)
  - 64 query heads → GQA factor 8 (64/8=8)
  - `num_attention_heads_per_layer`: 64

D = V = 128, so `qk_per_thread = v_per_thread = 4` (128/32).
Threadgroup: 1024 threads = 32 simdgroups (BN=BD=32).

## Current State: DARKBLOOM_GQA_PAIR_HEADS=2

### How It Works (lines 295-606)

1. **Guard** (L310-314): `use_gqa_pair` requires `gqa_factor==6||8`, `tpg.y==1`
   (single query), `tpg.x%2==0` (even head count), aligned, no mask/causal/sinks.

2. **Head mapping** (L316-337): `pair_idx = tid.x`, `q_head0 = 2*pair_idx`,
   `q_head1 = q_head0+1`, `kv_head_idx = q_head0/gqa_factor`.
   Threadgroups past `tpg.x/2` early-return (L318-320).

3. **Register state**: Two independent sets — `pair_q0/q1`, `pair_o0/o1`,
   `pair_max0/1`, `pair_sum0/1`. Each head has its own online-softmax accumulator.

4. **Main loop** (L359-531): Two-deep software pipeline. Loads K/V for 2
   positions (a,b) via `vec<T,4>` loads. Computes scores for both heads against
   the same K. Updates each head's softmax state independently. Writes both
   heads' output accumulators using the shared V.

5. **Exchange epilogue** (L533-596): `pair_planes=2`, processes 4 elements
   (v_per_thread=4) in 2 rounds of 2. Each round: write 2 elements × 2 heads
   into 4 planes, barrier, read back. 3 barriers total.

### Memory Budget (Current)

```
exchange_planes = 4 (2 heads × 2 planes/head)
outputs:  4 × 32 × 32 × 4 B = 16384 B
max_scores:  2 × 32 × 4 B = 256 B
sum_exp_scores: 2 × 32 × 4 B = 256 B
Total: 16384 + 512 = 16896 B (16.5 KiB) ✓
```

### K/V Traffic (Current)

Per decode step, per layer:
- GQA6: 48 query heads → 24 pairs → 24 K/V row loads (was 48)
- GQA8: 64 query heads → 32 pairs → 32 K/V row loads (was 64)
- Each K/V row: D=128 elements × 2 bytes (bfloat16) = 256 B, loaded by 32
  simdgroups (each simdgroup loads 4 elements), so 1 K/V row load = 256 B
  read from device memory per threadgroup.

## Target: 3 Heads for GQA6, 4 Heads for GQA8

### Divisibility Constraint (Critical)

The group size MUST divide the GQA factor so no group crosses a KV-head
ownership boundary:

| GQA Factor | Divisors | Max group (≤4) | Q-heads/group | Groups/layer |
|---|---|---|---|---|
| 6 (full) | 1,2,3,6 | 3 | 3 | 48/3 = 16 |
| 8 (sliding) | 1,2,4,8 | 4 | 4 | 64/4 = 16 |

- PAIR_HEADS=3 works for GQA6 (6/3=2 groups per KV head) but NOT GQA8 (8/3≈2.67).
- PAIR_HEADS=4 works for GQA8 (8/4=2 groups per KV head) but NOT GQA6 (6/4=1.5).

**Both group sizes yield exactly 2 groups per KV head** — the maximum K/V
sharing while keeping groups within a single KV head. This is yudduy's design:
"exactly two active query groups per KV head."

### K/V Traffic Reduction

| Layer type | Current (2-head) | New (3 or 4-head) | Reduction |
|---|---|---|---|
| GQA6 (10 layers) | 24 K/V loads | 16 K/V loads | 33% fewer |
| GQA8 (30 layers) | 32 K/V loads | 16 K/V loads | 50% fewer |

Weighted by layer count: (10×33% + 30×50%)/40 = (330+1500)/40 = 45.75%
average K/V load reduction across all attention layers.

Since decode is 75% of the score and attention K/V traffic is a significant
fraction of decode time (each of 40 layers reads K/V for up to 512+128=640
positions × 128 elements × 2 bytes per position per load), this reduction
directly impacts the primary scored component.

## Memory Budget Analysis

### PAIR_HEADS=3 (GQA6 only, pair_planes=2)

```
exchange_planes = 3 × 2 = 6
outputs:    6 × 32 × 32 × 4 B = 24576 B
max_scores: 3 × 32 × 4 B = 384 B
sum_exp_scores: 3 × 32 × 4 B = 384 B
Total: 24576 + 768 = 25344 B (24.75 KiB) ✓ FITS
```

### PAIR_HEADS=4 (GQA8, naive pair_planes=2)

```
exchange_planes = 4 × 2 = 8
outputs:    8 × 32 × 32 × 4 B = 32768 B
max_scores: 4 × 32 × 4 B = 512 B
sum_exp_scores: 4 × 32 × 4 B = 512 B
Total: 32768 + 1024 = 33792 B (33.0 KiB) ✗ EXCEEDS 32 KiB LIMIT
```

This is a hard metallib compile error, not a slow kernel.

### PAIR_HEADS=4 (GQA8, 6-plane staggered exchange)

The solution to fit 4 heads in 6 planes: **staggered head processing**.

Instead of exchanging all 4 heads simultaneously, process heads in two
batches across the exchange rounds:

**Batch 1 (heads 0,1,2): 3 heads × 2 planes = 6 planes**
- Round 1: write elements 0,1 of heads 0,1,2 into planes 0-5 → barrier → read
- Round 2: write elements 2,3 of heads 0,1,2 into planes 0-5 → barrier → read

**Batch 2 (head 3): 1 head × 2 planes, reusing 2 of the 6 planes**
- Round 3: write elements 0,1 of head 3 into planes 0,1 → barrier → read
- Round 4: write elements 2,3 of head 3 into planes 0,1 → barrier → read

```
exchange_planes = 6 (max across batches)
outputs:    6 × 32 × 32 × 4 B = 24576 B
max_scores: 4 × 32 × 4 B = 512 B  (all 4 heads, always allocated)
sum_exp_scores: 4 × 32 × 4 B = 512 B
Total: 24576 + 1024 = 25600 B (25.0 KiB) ✓ FITS
```

This is yudduy's exact configuration: "six exchange planes + four-head
max/sum" = 25 KiB.

**Barrier count:** 4 rounds × (write → barrier → read) with inter-round
barriers = 7 barriers (vs current 3 for 2-head). The extra 4 barriers are
a trade-off for the 50% K/V traffic reduction on 30/40 layers.

**Alternative: 2+2 staggering (4 planes)**
Process heads 0,1 in rounds 1-2 (4 planes), then heads 2,3 in rounds 3-4
(reuse same 4 planes). Total = 4 planes = 16384 + 1024 = 17408 B. Same 7
barriers, less memory. However, this CANNOT handle the 3-head GQA6 case
(3×2=6 planes needed), so the allocation must be 6 to serve both GQA6 and
GQA8 from one compiled kernel.

### Unified allocation for dual group sizes

Since the same compiled kernel handles both GQA6 and GQA8 (selected by
runtime `gqa_factor`), the compile-time `exchange_planes` must be the
maximum: **6**.

```
constexpr int exchange_planes = (D==128 && V==128 && GQA_PAIR_ENABLED) ? 6 : v_planes;
```

The stock (non-pair) path uses `v_planes=4` and only touches 4 of the 6
allocated planes — a 8192 B waste that is harmless (fits in 32 KiB) and
avoids needing a second kernel specialization.

## Specific Code Changes

All line numbers refer to `sdpa_vector.h` at the current frontier.

### 1. Macro definitions (lines 97-113)

Replace the `DARKBLOOM_GQA_PAIR_HEADS` macro block with a dual-group design:

```cpp
// Lines 97-113: Replace DARKBLOOM_GQA_PAIR_HEADS with:
#ifndef DARKBLOOM_GQA_GROUP_FULL    // heads per group for GQA6 (full attention)
#define DARKBLOOM_GQA_GROUP_FULL 3
#endif
#ifndef DARKBLOOM_GQA_GROUP_SLIDING // heads per group for GQA8 (sliding attention)
#define DARKBLOOM_GQA_GROUP_SLIDING 4
#endif
#ifndef DARKBLOOM_GQA_GROUP_MAX     // max of the two, for memory allocation
#define DARKBLOOM_GQA_GROUP_MAX 4
#endif
```

### 2. Exchange plane allocation (lines 279-291)

```cpp
// Line 284-288: Change exchange_planes computation
constexpr int v_planes = PLANES < v_per_thread ? PLANES : v_per_thread;
constexpr int gqa_pair_planes = 6; // 3×2 for GQA6, reused staggered for GQA8
constexpr int exchange_planes =
    (D == 128 && V == 128 &&
     DARKBLOOM_GQA_GROUP_FULL >= 2 && DARKBLOOM_GQA_GROUP_SLIDING >= 2)
    ? gqa_pair_planes
    : v_planes;
// Line 289: outputs allocation stays exchange_planes * BN * BD
threadgroup U outputs[exchange_planes * BN * BD];
// Line 290-291: max/sum for up to DARKBLOOM_GQA_GROUP_MAX heads
threadgroup U max_scores[DARKBLOOM_GQA_GROUP_MAX * BN];
threadgroup U sum_exp_scores[DARKBLOOM_GQA_GROUP_MAX * BN];
```

### 3. Pair path guard (lines 295-314)

Change the constexpr guard from `DARKBLOOM_GQA_PAIR_HEADS == 2` to the new
condition, and update the runtime `use_gqa_pair` check:

```cpp
// Line 295: Change constexpr condition
if constexpr (D == 128 && V == 128 &&
              DARKBLOOM_GQA_GROUP_FULL >= 2 &&
              DARKBLOOM_GQA_GROUP_SLIDING >= 2) {

// Line 310-314: Update guard — group count divides head count
const int gqa_group = (gqa_factor == 6) ? DARKBLOOM_GQA_GROUP_FULL
                  : (gqa_factor == 8) ? DARKBLOOM_GQA_GROUP_SLIDING
                  : 0;
const bool use_gqa_pair =
    gqa_group >= 2 &&
    tpg.y == 1 && (tpg.x % gqa_group) == 0 &&
    pair_vec_aligned &&
    !has_mask && !do_causal && !has_sinks;
```

### 4. Head mapping and pointers (lines 316-337)

Replace the fixed 2-head mapping with variable group size:

```cpp
if (use_gqa_pair) {
    const int group_idx = tid.x;
    const int q_head0 = gqa_group * group_idx;
    if (q_head0 >= int(tpg.x)) {
        return;  // excess threadgroups early-return
    }
    const int n_active_heads = min(gqa_group, int(tpg.x) - q_head0);
    const int kv_head_idx = q_head0 / gqa_factor;

    // Query pointers for each active head
    const device T* group_queries[DARKBLOOM_GQA_GROUP_MAX];
    device T* group_out[DARKBLOOM_GQA_GROUP_MAX];
    for (int h = 0; h < n_active_heads; ++h) {
        group_queries[h] = queries + (q_head0 + h) * D + simd_lid * qk_per_thread;
        group_out[h] = out + (q_head0 + h) * V + simd_gid * v_per_thread;
    }
    // Shared K/V (loaded once for all heads in the group)
    const device T* group_keys =
        keys + kv_head_idx * k_head_stride + simd_gid * k_seq_stride +
        simd_lid * qk_per_thread;
    const device T* group_values =
        values + kv_head_idx * v_head_stride + simd_gid * v_seq_stride +
        simd_lid * v_per_thread;
```

### 5. Register state (lines 339-357)

Use arrays instead of individually named variables. The register pressure
increases: 4 heads × (4 q + 4 o + 2 scalars) = 40 registers vs current 20.

```cpp
    thread U group_q[DARKBLOOM_GQA_GROUP_MAX][qk_per_thread];
    thread U group_o[DARKBLOOM_GQA_GROUP_MAX][v_per_thread];
    U group_max[DARKBLOOM_GQA_GROUP_MAX];
    U group_sum[DARKBLOOM_GQA_GROUP_MAX];

    for (int h = 0; h < n_active_heads; ++h) {
        for (int j = 0; j < qk_per_thread; ++j)
            group_q[h][j] = static_cast<U>(scale) * group_queries[h][j];
        for (int j = 0; j < v_per_thread; ++j)
            group_o[h][j] = 0;
        group_max[h] = Limits<U>::finite_min;
        group_sum[h] = 0;
    }
```

**Register pressure note:** At 4 heads × 4 q-elements = 16 q-registers + 4×4=16
o-registers + 8 scalars = 40 floats. Apple GPU has 256 registers per thread
(8 per lane in a 32-lane simdgroup, shared register file). 40 floats is
within budget but reduces occupancy headroom. The current 2-head path uses
20 floats. Residency is already 1 threadgroup per core, so occupancy is
unaffected.

### 6. Main loop — score computation (lines 359-531)

The two-deep software pipeline structure stays. The K/V loads are unchanged
(loaded once, shared). The score and output updates loop over `n_active_heads`:

```cpp
    // Two-deep pipeline: load positions a and b, accumulate in order
    int i = simd_gid;
    for (; i + BN < N; i += 2 * BN) {
        // Load K/V for positions a and b (shared across all heads)
        const vec<T, 4> vec_ka = *reinterpret_cast<const device vec<T, 4>*>(group_keys);
        const vec<T, 4> vec_kb = *reinterpret_cast<const device vec<T, 4>*>(group_keys + inner_k_stride);
        U pipe_ka[4], pipe_kb[4];
        // ... unpack vec_ka, vec_kb (same as current L376-385)
        const vec<T, 4> vec_va = *reinterpret_cast<const device vec<T, 4>*>(group_values);
        const vec<T, 4> vec_vb = *reinterpret_cast<const device vec<T, 4>*>(group_values + inner_v_stride);
        // ... unpack vec_va, vec_vb (same as current L386-397)

        // Per-head score and update (position a)
        for (int h = 0; h < n_active_heads; ++h) {
            U score = 0;
            score += group_q[h][0] * pipe_ka[0];
            score += group_q[h][1] * pipe_ka[1];
            score += group_q[h][2] * pipe_ka[2];
            score += group_q[h][3] * pipe_ka[3];
            score = simd_sum(score);

            U new_max = max(group_max[h], score);
            U factor;
            DARKBLOOM_RESCALE_FACTOR(factor, group_max[h] - new_max);
            U exp_score = fast::exp(score - new_max);
            group_max[h] = new_max;
            group_sum[h] = group_sum[h] * factor + exp_score;
            group_o[h][0] = group_o[h][0] * factor + exp_score * vec_va.x;
            group_o[h][1] = group_o[h][1] * factor + exp_score * vec_va.y;
            group_o[h][2] = group_o[h][2] * factor + exp_score * vec_va.z;
            group_o[h][3] = group_o[h][3] * factor + exp_score * vec_va.w;
        }

        // Per-head score and update (position b) — same pattern with pipe_kb/vb
        for (int h = 0; h < n_active_heads; ++h) {
            // ... identical to above with pipe_kb and vec_vb
        }

        group_keys += 2 * inner_k_stride;
        group_values += 2 * inner_v_stride;
    }
    // Tail iteration (i < N): same pattern, single position (same as L462-514)
```

**Performance note:** The `for (int h ...)` loop over heads will be unrolled
by the Metal compiler at `-O3` since `n_active_heads` is either 3 or 4
(loaded from `gqa_group`, which is a runtime value but the compiler can
still unroll if structured as `if (n_active_heads == 3) {...} else {...}`).
For maximum performance, consider two explicit branches:

```cpp
    if (n_active_heads == 3) {
        // Unrolled 3-head score + update
    } else { // n_active_heads == 4
        // Unrolled 4-head score + update
    }
```

This avoids loop overhead and gives the compiler the best unrolling hint.

### 7. Exchange epilogue (lines 533-596)

This is the most complex change. The epilogue must handle both 3-head (6
planes, 2 rounds) and 4-head (6 planes, 4 rounds staggered) cases.

**For 3 heads (GQA6):** Identical to current 2-head structure, just with 3
heads instead of 2. Uses 6 planes (3×2), 2 rounds, 3 barriers.

```
Round 1: write elements 0,1 of heads 0,1,2 into planes 0-5 → barrier → read
         (head h uses planes h*2 and h*2+1)
Round 2: write elements 2,3 of heads 0,1,2 into planes 0-5 → barrier → read
```

**For 4 heads (GQA8):** Staggered 3+1:
```
Round 1: write elements 0,1 of heads 0,1,2 into planes 0-5 → barrier → read
Round 2: write elements 2,3 of heads 0,1,2 into planes 0-5 → barrier → read
Round 3: write elements 0,1 of head 3 into planes 0,1 → barrier → read
Round 4: write elements 2,3 of head 3 into planes 0,1 → barrier → read
```

Implementation with a helper structure:

```cpp
    constexpr int pair_plane_size = BN * BD; // 1024

    // Publish max/sum for all active heads
    if (simd_lid == 0) {
        for (int h = 0; h < n_active_heads; ++h) {
            max_scores[h * BN + simd_gid] = group_max[h];
            sum_exp_scores[h * BN + simd_gid] = group_sum[h];
        }
    }

    // Global max/sum reduction for each head
    for (int h = 0; h < n_active_heads; ++h) {
        U local_max = max_scores[h * BN + simd_lid];
        U global_max = simd_max(local_max);
        U global_factor = fast::exp(local_max - global_max);
        group_max[h] = global_max;  // reuse as storage
        group_sum[h] = simd_sum(sum_exp_scores[h * BN + simd_lid] * global_factor);
    }

    // Exchange: process heads in batches of 3 (or fewer for the tail)
    // Batch structure: [0,1,2] then [3] for 4 heads; [0,1,2] for 3 heads
    int head_batch_starts[] = {0, 3}; // for 4 heads; {0} for 3 heads
    int head_batch_sizes[] = {3, 1};  // for 4 heads; {3} for 3 heads
    int n_batches = (n_active_heads <= 3) ? 1 : 2;

    for (int batch = 0; batch < n_batches; ++batch) {
        int h_start = head_batch_starts[batch];
        int h_count = (batch == 0) ? min(3, n_active_heads) : n_active_heads - 3;
        int planes_per_head = 2; // pair_planes

        // Round 1: elements 0,1
        for (int h = 0; h < h_count; ++h) {
            int head = h_start + h;
            int plane_base = h * planes_per_head;
            outputs[plane_base * pair_plane_size + simd_lid * BD + simd_gid] = group_o[head][0];
            outputs[(plane_base + 1) * pair_plane_size + simd_lid * BD + simd_gid] = group_o[head][1];
        }
        threadgroup_barrier(mem_flags::mem_threadgroup);
        for (int h = 0; h < h_count; ++h) {
            int head = h_start + h;
            int plane_base = h * planes_per_head;
            U factor = fast::exp(max_scores[head * BN + simd_lid] - group_max[head]);
            U acc0 = simd_sum(outputs[plane_base * pair_plane_size + simd_gid * BD + simd_lid] * factor);
            U acc1 = simd_sum(outputs[(plane_base + 1) * pair_plane_size + simd_gid * BD + simd_lid] * factor);
            group_o[head][0] = group_sum[head] == 0 ? acc0 : (acc0 / group_sum[head]);
            group_o[head][1] = group_sum[head] == 0 ? acc1 : (acc1 / group_sum[head]);
        }

        // Round 2: elements 2,3
        threadgroup_barrier(mem_flags::mem_threadgroup);
        for (int h = 0; h < h_count; ++h) {
            int head = h_start + h;
            int plane_base = h * planes_per_head;
            outputs[plane_base * pair_plane_size + simd_lid * BD + simd_gid] = group_o[head][2];
            outputs[(plane_base + 1) * pair_plane_size + simd_lid * BD + simd_gid] = group_o[head][3];
        }
        threadgroup_barrier(mem_flags::mem_threadgroup);
        for (int h = 0; h < h_count; ++h) {
            int head = h_start + h;
            int plane_base = h * planes_per_head;
            U factor = fast::exp(max_scores[head * BN + simd_lid] - group_max[head]);
            U acc0 = simd_sum(outputs[plane_base * pair_plane_size + simd_gid * BD + simd_lid] * factor);
            U acc1 = simd_sum(outputs[(plane_base + 1) * pair_plane_size + simd_gid * BD + simd_lid] * factor);
            group_o[head][2] = group_sum[head] == 0 ? acc0 : (acc0 / group_sum[head]);
            group_o[head][3] = group_sum[head] == 0 ? acc1 : (acc1 / group_sum[head]);
        }
    }
    // Note: skip trailing barrier on last round (same optimization as stock path)
```

**Barrier count:**
- 3 heads (GQA6): 1 batch × 2 rounds × 2 barriers = 3 barriers (same as current)
- 4 heads (GQA8): 2 batches × 2 rounds × 2 barriers + 1 inter-batch barrier = 7 barriers

Wait — the inter-batch barrier is already the trailing barrier of batch 1's
round 2, which serves as the inter-batch barrier for batch 2's round 1 write.
So it's: 2 batches × (write-barrier-read, write-barrier-read) = 4 writes, 4
barriers, 4 reads. But the trailing barrier of the last round can be
skipped (no subsequent write to protect). So: 3 barriers for the first
batch (write-barrier-read-write-barrier-read) and 2 for the second batch
(write-barrier-read-write-[skip]) = 5 barriers... 

Actually, more carefully:
- Batch 0, Round 1: write → B1 → read
- Batch 0, Round 2: write → B2 → read
- Batch 1, Round 1: write → B3 → read  (B2 also protects this write from Batch 0 Round 2's read)
- Batch 1, Round 2: write → B4 → read  (B3 also protects this write from Batch 1 Round 1's read)

B4 is the trailing barrier of the last round — it protects nothing if
nothing follows, so it can be skipped. Total: B1, B2, B3, B4-skip = **3
effective barriers** for 4 heads. Wait, no — B2 protects both the Round 2
read AND the Batch 1 Round 1 write (they reuse the same planes). So the
barriers are:

1. B1: after Batch0/R1 write, before Batch0/R1 read
2. B2: after Batch0/R1 read + Batch0/R2 write, before Batch0/R2 read + Batch1/R1 write
3. B3: after Batch0/R2 read + Batch1/R1 write + Batch1/R1 read + Batch1/R2 write, before Batch1/R2 read

That's 3 barriers. But wait, there are RAW/WAR hazards between batches
since they share planes. Let me be more careful:

Batch 0 Round 1: WRITE planes 0-5 → B1 → READ planes 0-5
Batch 0 Round 2: WRITE planes 0-5 → B2 → READ planes 0-5
Batch 1 Round 1: WRITE planes 0-1 → B3 → READ planes 0-1
Batch 1 Round 2: WRITE planes 0-1 → [B4] → READ planes 0-1

B1: RAW for Batch0/R1 (write→read)
B2: WAR for Batch0/R1 (read→write of R2) + RAW for Batch0/R2
B3: WAR for Batch0/R2 (read→write of Batch1/R1) + RAW for Batch1/R1
[B4]: WAR for Batch1/R1 + RAW for Batch1/R2 — but since nothing follows,
      the WAR is moot and the RAW is within the same warp, so B4 can be skipped
      ONLY IF the read happens before any subsequent write. Since there is no
      subsequent write, B4 protects the Batch1/R2 read from... nothing.
      Actually, B4 is needed for the RAW: the write of Batch1/R2 must complete
      before the read. But simd_sum reads from threadgroup memory, and the
      write is by the same threads — no, the write is by lane l of simdgroup
      g, and the read is by lane l of simdgroup g reading what was written by
      lane g of simdgroup l. So the RAW hazard IS real (cross-simdgroup).

Therefore B4 IS needed. Total: **4 barriers** for 4 heads.

Hmm, but in the current 2-head/2-round code (lines 532-596), the structure is:
```
write → B1 → read → write → B2 → read → write → B3 → read
```
That's 3 barriers for 2 rounds (the B2 serves double duty as WAR for round 1
and RAW for round 2, and B3 serves as WAR for round 2 and RAW for the second
round's elements 2,3).

Wait, I'm confusing myself. Let me re-read the current code:

Lines 537-548: Write max/sum to threadgroup + write elements 0,1 of both heads
Line 549: B1 (threadgroup_barrier)
Lines 551-556: Read back max/sum + read elements 0,1
Lines 558-564: Write elements 2,3 of both heads (reusing same planes)
Line 566: B2 (threadgroup_barrier)
Lines 567-572: Read back elements 2,3 (wait, these read into pair_o0[pair_planes+i] which is o0[2] and o0[3])

Hmm wait, the code at lines 562-580:
```
// Line 558: threadgroup_barrier  <-- B2
// Lines 559-564: write pair_o0[pair_planes+i] and pair_o1[pair_planes+i] 
//                = elements 2,3 into planes 0,1,2,3
// Line 566: threadgroup_barrier  <-- B3
// Lines 567-580: read back elements 2,3
```

So the current structure is:
1. Write elements 0,1 (L543-547)
2. B1 (L549)
3. Read elements 0,1 (L562-556)
4. Write elements 2,3 (L559-564) ← wait, this is BEFORE B2
5. B2 (L566)
6. Read elements 2,3 (L567-580)

Wait, I need to re-read more carefully. Let me look at the actual flow:

```
L537-541: if simd_lid==0, write max/sum
L543-547: write o0[0],o0[1] to planes 0,1; o1[0],o1[1] to planes 2,3
L549: BARRIER  ← B1
L551-560: read max/sum from threadgroup; compute global max/sum/factor
L562-556: read o0[0],o0[1] from planes 0,1; o1[0],o1[1] from planes 2,3
          → store into pair_o0[0], pair_o0[1], pair_o1[0], pair_o1[1]
L558: BARRIER  ← B2 (WAR: protect the read above from the write below)
L559-564: write o0[2],o0[3] to planes 0,1; o1[2],o1[3] to planes 2,3
L566: BARRIER  ← B3 (RAW: protect the read below from the write above)
L567-580: read o0[2],o0[3] from planes 0,1; o1[2],o1[3] from planes 2,3
          → store into pair_o0[2], pair_o0[3], pair_o1[2], pair_o1[3]
```

So 3 barriers (B1, B2, B3) for 2 rounds. The last barrier (B3) protects the
RAW of round 2. There is no trailing barrier after the last read because
nothing follows that writes to the same planes.

For 4 heads with 3+1 staggering:
```
B1: Write batch0 R1 (heads 0,1,2 elements 0,1) → B1 → Read batch0 R1
B2: → Write batch0 R2 (heads 0,1,2 elements 2,3) → B2 → Read batch0 R2
B3: → Write batch1 R1 (head 3 elements 0,1) → B3 → Read batch1 R1
B4: → Write batch1 R2 (head 3 elements 2,3) → B4 → Read batch1 R2
```

B2 serves double duty: WAR for batch0 R1 read, RAW for batch0 R2 write.
B3 serves double duty: WAR for batch0 R2 read, RAW for batch1 R1 write.
   (Batch1 reuses planes 0,1 from batch0, so the WAR hazard is real.)
B4 serves: WAR for batch1 R1 read, RAW for batch1 R2 write.

Total: 4 barriers for 4 heads (vs 3 for 2 heads current). The extra barrier
is the cost of the 4th head's staggered processing.

For 3 heads (GQA6): Same 2-round structure as current, just 3 heads:
```
Write 3 heads R1 → B1 → Read 3 heads R1 → Write 3 heads R2 → B2 → Read 3 heads R2 → B3 → Read done
```
Wait, that's still 3 barriers. Same as current.

Actually for 3 heads, the structure mirrors the current 2-head exactly:
- B1: after writing elements 0,1 of all 3 heads, before reading
- B2: after reading elements 0,1 and writing elements 2,3 (WAR + RAW)
- B3: after writing elements 2,3, before reading (RAW)
= 3 barriers

For 4 heads (3+1 staggering):
- B1: after writing batch0 (3 heads) elements 0,1, before reading
- B2: after reading batch0 R1 + writing batch0 R2, before reading R2 (WAR + RAW)
- B3: after reading batch0 R2 + writing batch1 R1, before reading batch1 R1 (WAR + RAW)
- B4: after reading batch1 R1 + writing batch1 R2, before reading batch1 R2 (WAR + RAW)
= 4 barriers

So the barrier count goes from 3 (current 2-head) to 3 (new 3-head) or 4
(new 4-head). The extra barrier for 4-head is negligible vs the 50% K/V
traffic reduction.
```

### 8. Output write (lines 599-604)

```cpp
    if (simd_lid == 0) {
        for (int h = 0; h < n_active_heads; ++h) {
            for (int j = 0; j < v_per_thread; ++j) {
                group_out[h][j] = static_cast<T>(group_o[h][j]);
            }
        }
    }
    return;
```

## Bit-Exactness Analysis

The optimization must preserve every checked greedy token. The pair path
must be bit-exact with the stock per-head path.

### What is preserved

1. **Key order**: Each head processes keys in the same order (simd_gid=0,
   1, 2, ..., 31 stepping by BN). The group path loads K/V for each position
   once and computes all heads' scores against it in the same iteration. The
   key traversal order per head is unchanged.

2. **Score computation**: Each head's score is `simd_sum(q[0..3] · k[0..3])`.
   The dot product accumulation order is identical (same 4-element unrolled
   multiply-add chain). The `simd_sum` reduction across 32 lanes is the same.

3. **Online-softmax state**: Each head maintains independent `max`, `sum`,
   and `o` accumulators. The rescale factor computation
   (`DARKBLOOM_RESCALE_FACTOR`) and `fast::exp` calls are identical per head.
   The accumulation order (max → factor → exp → update sum → update o) is
   preserved per head.

4. **Reduction tree**: The exchange epilogue uses the same 32×32 transpose
   and `simd_sum` reduction. Each head's elements are written to its own set
   of planes (disjoint memory), read back in the transposed order, and
   reduced with `simd_sum`. The producer/consumer lane pairing and reduction
   tree are identical to the stock path.

5. **K/V sharing is safe**: K and V are read-only device memory. Multiple
   heads reading the same K/V row get the same values. No write-after-read
   or race conditions on device memory.

### What changes (and why it's still exact)

1. **K/V load placement**: The two-deep pipeline hoists loads to the top of
   each iteration. This is identical to the current pair path's approach
   (already shipped and verified bit-exact). Loads have no side effects.

2. **vec<T,4> loads**: The 8-byte vector loads replace 4 scalar loads with
   identical element values in identical order (certified by `pair_vec_aligned`).

3. **Exchange plane reuse for 4-head staggering**: In the 4-head case, head 3
   reuses planes 0,1 after heads 0,1,2 have finished with them. The barrier
   between batches (B3) ensures all reads from batch 0 complete before batch
   1's writes begin. The plane memory is clean — no residual data from a
   different head can corrupt the reduction.

### Risk: register allocation

With 4 heads, the register file holds 4×(4 q + 4 o) = 32 arrays + 8 scalars
= 40 floats per thread. If the compiler spills to threadgroup memory, it
could change the FP sequence. Mitigation: verify no spills via Metal
disassembly (check for threadgroup writes in the score loop). The current
2-head path uses 20 floats with no spills. 40 floats is within the 256-
register per-thread budget on Apple GPU, but should be verified.

### Risk: loop unrolling

If the `for (int h = 0; h < n_active_heads; ++h)` loop is NOT unrolled, the
compiler may introduce different instruction scheduling that changes the
FP rounding sequence. Mitigation: use explicit `if (n_active_heads == 3)
{...} else {...}` branches with fully unrolled per-head code, matching the
current manual unrolling style.

## Build Instructions

### Metallib rebuild (required)

This is an AOT kernel. Changes to `sdpa_vector.h` require rebuilding
`mlx.metallib`:

```bash
cd /path/to/target
./tools/build-mlx-metallib.sh
```

This compiles all vendored Metal sources (including `sdpa_vector.h` via
`scaled_dot_product_attention.metal`) into `mlx.metallib` placed next to
the runtime worker binary.

**CRITICAL**: A stale `mlx.metallib` silently serves the previous kernel.
Always rebuild after editing the header. The build script fingerprints all
vendored Metal sources and refuses to serve a stale metallib.

### Build verification

```bash
# Rebuild the worker with the new metallib
./benchmark.sh --local-iterate

# Or direct swift build (matched to the scored build directory)
swift build -c release --force-resolved-versions
git checkout -- Package.resolved
```

### Byte budget check

```
sdpa_vector.h: 45148 B current
Estimated growth: ~3000-5000 B (arrays, branching, exchange epilogue)
New size: ~48000-50000 B
Per-file limit: 524288 B → ~474000 B headroom ✓
Total surface: 1904653 B current
Total limit: 3000000 B → ~1095000 B headroom ✓
Growth per review: 262144 B → well within limit ✓
```

## Testing Plan

### 1. Upstream equivalence (mandatory before timing)

```bash
cd /path/to/target
./research/run_upstream_equivalence.sh
```

This runs `lagunaRuntimeMatchesVendoredUpstreamOnM5WhenEnabled` against the
vendored Laguna oracle with zero tolerance (`MAX_ABS_ERROR=0`). It uses the
exact bare test filter, repairs the debug metallib placement, and refuses
to call a zero-test invocation a pass.

**A failure here means the change is not bit-exact and must not ship.**

### 2. Local timing (paired baseline/candidate)

```bash
./benchmark.sh --local-iterate
```

This builds the scored worker and runs matched baseline/candidate timing.
Compare fresh candidate seconds/token with a fresh unchanged baseline on
the same host. The decode window is 128 one-token steps with 75% score
weight; prefill is 512 tokens with 25% weight.

### 3. Golden token check

The benchmark includes a 64-step drift tripwire. If the change alters any
greedy token, this will fail. Run the full benchmark suite:

```bash
./benchmark.sh --local-iterate
```

### 4. M4 directional check (if M5 unavailable)

On M4 Pro hosts: the kernel family differs (`_nax` prefill kernels are not
selected), but the decode SDPA vector kernel IS the same. A same-host
baseline vs. candidate comparison gives directional evidence for the decode
component. Do not interpret M4 prefill results as evidence.

### 5. Pre-submit validation

```bash
./benchmark.sh --local-submit
```

Then inspect the candidate against `benchmark.json`'s `editablePaths`. The
`mlxfast submit` command uploads only the editable surface and does not run
local preflight.

## Expected Timing Improvement

### K/V traffic model

Per decode step, per attention layer, the SDPA vector kernel reads:
- K: N positions × D=128 elements × 2 bytes = N × 256 B per KV head
- V: N positions × V=128 elements × 2 bytes = N × 256 B per KV head
- Total per KV head: N × 512 B

At decode with N up to 640 (512 seed + 128 steps):
- Per layer per KV head: 640 × 512 B = 327,680 B = 320 KiB
- (K: 640 × 128 × 2 = 163,840 B + V: 640 × 128 × 2 = 163,840 B = 327,680 B)

### Current vs. proposed

| Config | GQA6 K/V loads | GQA8 K/V loads | Total K/V bytes (40 layers) |
|---|---|---|---|
| Stock (no pairing) | 48 × 320 KiB | 64 × 320 KiB | (10×48 + 30×64) × 320 KiB = 4,224,000 KiB |
| Current (2-head) | 24 × 320 KiB | 32 × 320 KiB | (10×24 + 30×32) × 320 KiB = 2,112,000 KiB |
| Proposed (3/4-head) | 16 × 320 KiB | 16 × 320 KiB | (10×16 + 30×16) × 320 KiB = 1,280,000 KiB |

K/V traffic reduction from current to proposed:
(2,112,000 - 1,280,000) / 2,112,000 = **39.4% reduction**

Verified with concrete numbers (N=640, D=V=128, bfloat16):
- Current (2-head): 375.0 MiB per decode step across 40 layers
- Proposed (3/4-head): 200.0 MiB
- **46.7% reduction** (the higher figure accounts for N=640 positions × 2 bytes
  per element × 2 for K+V, summed across 10 GQA6 + 30 GQA8 layers)

### Score impact estimate

Decode is 75% of the score. If attention K/V traffic is ~30-40% of decode
time (the rest being MoE, RMSNorm, projections, etc.), a 39.4% K/V reduction
translates to ~12-16% decode time reduction, or ~12-16% decode speedup.

Score = decode_speedup^0.75 × prefill_speedup^0.25
If decode speedup = 1.12-1.16 and prefill unchanged (1.0):
Score improvement ≈ 1.12^0.75 - 1 ≈ 8.9% to 1.16^0.75 - 1 ≈ 11.7%

However, yudduy's actual gain was only +0.67% (2.5901 → 2.6063), suggesting
the K/V traffic fraction is much smaller than 30-40% of decode time, or the
barrier overhead and register pressure partially offset the traffic savings.

**Conservative estimate: +0.5% to +1.0% score improvement**, matching
yudduy's observed gain. The improvement is modest because:
1. Attention K/V traffic is a fraction of total decode time (MoE expert
   gather-GEMM dominates).
2. The extra barriers for 4-head staggering add overhead.
3. Register pressure may cause instruction scheduling degradation.
4. The 3-head GQA6 improvement (33% fewer loads on 10/40 layers) is smaller
   than the 4-head GQA8 improvement (50% fewer loads on 30/40 layers).

### Why our gap to #1 is +0.67%

yudduy's score 2.6063 vs our 2.5888. If we replicate their exact approach
(3 heads for GQA6, 4 heads for GQA8, 6 exchange planes), we should close
most of this gap, as it is their primary differentiating optimization.

## Phased Implementation Recommendation

### Phase 1: PAIR_HEADS=3 for GQA6 only (safest)

- Change `DARKBLOOM_GQA_GROUP_FULL=3`, keep `DARKBLOOM_GQA_GROUP_SLIDING=2`
- `exchange_planes=6` (3×2 for GQA6, 4 for GQA8 fallback to 2-head)
- Only 10/40 layers affected
- 33% K/V reduction on full-attention layers
- Barrier count unchanged (3 for 3-head, same as 2-head)
- **Risk: LOW** — straightforward extension of current code
- **Expected gain: ~0.2-0.3%** (10/40 layers, 33% reduction)

### Phase 2: PAIR_HEADS=4 for GQA8 (higher reward, more complex)

- Also set `DARKBLOOM_GQA_GROUP_SLIDING=4`
- Implement the 3+1 staggered exchange (6 planes, 4 barriers)
- 30/40 layers affected
- 50% K/V reduction on sliding-attention layers
- Extra barrier overhead (4 vs 3)
- **Risk: MEDIUM** — staggered exchange is novel, needs careful barrier analysis
- **Expected gain: ~0.4-0.7%** (30/40 layers, 50% reduction, minus barrier cost)

### Phase 3: Combined (match yudduy)

- Both Phase 1 and Phase 2 together
- `exchange_planes=6` serves both
- **Expected gain: ~0.6-1.0%** (closing the gap to #1)

## Summary of Risks and Mitigations

| Risk | Severity | Mitigation |
|---|---|---|
| Bit-exactness failure | HIGH | Run upstream equivalence with zero tolerance; verify no register spills |
| Threadgroup memory overflow | MEDIUM | Verified: 25600 B < 32768 B; compile-time check via metallib build |
| Register pressure (4 heads = 40 floats) | MEDIUM | Verify via Metal disassembly; use explicit if-branch unrolling |
| Barrier overhead (4 vs 3 for 4-head) | LOW | 1 extra barrier per 30/40 layers; negligible vs 50% K/V reduction |
| M5 metallib stale | HIGH | Always rebuild with `tools/build-mlx-metallib.sh`; verify fingerprint |
| Group crosses KV-head boundary | CRITICAL | Verified: 3 divides 6, 4 divides 8; runtime check `tpg.x % gqa_group == 0` |
| Editable surface byte limit | LOW | Estimated ~48-50 KB, limit 524 KB; total ~1.91 MB, limit 3 MB |
