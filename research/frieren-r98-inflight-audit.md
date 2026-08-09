# r98-A: in-flight audit of the decode attention mat-vec kernels

Assignment `maple-r98-a-decode-attn-qmv-mlp`, revision `r98-a-rev1`, PR #539.
Base `450953e5c8287bfa1f409addf568d7851458cf94` (the advisor's move from
`e510bb3d` touches only `research/CURRENT_RESEARCH_STATE.md`, so every control
in this document is unaffected).

The hypothesis is that the two attention decode mat-vec kernels are limited by
*outstanding loads per thread*, not by DRAM bandwidth, on the ranked M5. This
document establishes what the compiler actually emits, which is the only way to
know whether "add more outstanding loads" is even a reachable change.

## 1. The four kernels in scope

All four are runtime-JIT `MLXFast.metalKernel` sources built from
`Sources/MLXFastModel/LagunaRuntimeModel.swift`. No `.metal` file and no
metallib rebuild is involved.

| tag | kernel | source | dispatch |
| --- | --- | --- | --- |
| K1 | `laguna_decode_nvfp4_qkv_h{64,48}_r1_v1_lm1_pw1_se1_sd1` | `lagunaDecodeNVFP4QKVLaneMajorSource` | `lagunaDecodeNVFP4QKVR1` |
| K2 | `laguna_oproj_act_h{64,48}_v1_lm1_pw1_sc1_se1` | `lagunaGatedAffineOProjNVFP4Source` | `lagunaGatedAffineOProjNVFP4` |

Geometry, read off the sources:

| | K1 (h64) | K1 (h48) | K2 (h64, sliding) | K2 (h48, full) |
| --- | --- | --- | --- | --- |
| K extent | 2048 | 2048 | 8192 | 6144 |
| `block_size` | 512 | 512 | 512 | 512 |
| K iterations | 4 | 4 | 16 | 12 |
| rows / simdgroup | 1 | 1 | 4 | 4 |
| `values_per_thread` | 16 | 16 | 16 | 16 |
| threadgroups | 5120 | 3584 | 256 | 256 |
| TG size | 64 | 64 | 64 | 64 |
| code bytes / thread / K-iter | 8 | 8 | 32 | 32 |
| scale bytes / thread / K-iter | 0 (pre-hoisted) | 0 | 4 | 4 |

K1 pre-hoists all four block scales into `thread uint8_t sb[4]` before the K
loop, so its steady-state DRAM traffic per thread is **one 8-byte `uint2` code
load per K iteration and nothing else**. Its activation source `normalized` is
4 kB and is read by every threadgroup, so it is cache-resident. K2's
activation source `attention_output` is 16 kB and likewise shared by all 256
threadgroups.

## 2. Measured M4 cost (existing ledger)

From `research/r94-artifacts/r94-dispatch-ledger.tsv` (rebuild with
`python3 research/r94_ledger_build.py`), M4 Pro, 48 GB:

| kernel | calls/step | µs/step | GB/s | % of M4 peak |
| --- | --- | --- | --- | --- |
| `laguna_decode_nvfp4_qkv_h64_r1_v1_lm1_pw1_se1_sd1` | 30 | 1340.1 | 272 | 100 % |
| `laguna_decode_nvfp4_qkv_h48_…` | 10 | 362.8 | 270 | 99 % |
| `laguna_oproj_act_h64_v1_lm1_pw1_sc1_se1` | 30 | 1117.7 | 263 | 96 % |
| `laguna_oproj_act_h48_…` | 10 | 301.8 | 245 | 90 % |
| (reference) routed swiglu r1 bf16 v2 | 39 | 1497.7 | 254 | 93 % |
| (reference) routed shared down residual v6 | 39 | 858.9 | 256 | 94 % |

**K1 pool = 1702.9 µs/step. K2 pool = 1419.5 µs/step. Combined 3122.4
µs/step**, i.e. 63.8 % of our best measured decode step (4893.7 µs/step,
receipt `7ce1262d`).

These four kernels sit at 90–100 % of M4's DRAM peak. Rule 55 already recorded
this and concluded that *on M4* memory-latency-bound is excluded. Rule 60 then
recorded that latency-hiding arms are structurally M4-invisible at ≥2 TG/core.
Both apply here, and both are reasons to treat M4 as a **register-pressure and
occupancy regression screen**, not as an effect screen. That framing is set
before any timing is taken.

## 3. What the compiler actually emits

Tooling (all verified working this session):

* corpus: `research/r92-runs/kernels-scored/*.metal`, full translation units
  captured from the scored runtime, re-verified line-for-line against the
  current Swift sources;
* `xcrun metal -std=metal4.0 -fno-fast-math -S` → AIR/LLVM IR;
* `xcrun metallib` + `xcrun applegpu-nt -arch applegpu_g16s|applegpu_g17s` →
  **AGX native binaries for both M4 (g16s) and M5 (g17s)**;
* `xcrun metal-size -m` → `__compute` section size.

### 3.1 AIR is misleading

Baseline AIR for both K1 and K2 looks pathological:

| | K1 `qkv64.ll` | K2 `oproj64.ll` |
| --- | --- | --- |
| `alloca` | 2 | 2 |
| device loads | 5 | 5 |
| private (spill) loads | 12 | 14 |
| `fma` | 10 | 11 |
| lines | 332 | 359 |

`x_thread[16]` is spilled to an `alloca`, the 16-trip activation load is
*rolled* (one outstanding load), the 2-trip `j` loop is rolled, and for K2 the
4-trip row loop is rolled too. K1 additionally spills `sb[4]`. Read naively
this says "one outstanding load per thread, everything in scratch memory".

`#pragma clang loop unroll(full)` does not change this: the Metal front end
ignores it (333 / 359 AIR lines, i.e. unchanged).

Manually unrolling K1 in source *does* fix the AIR — `alloca` 2 → 1, device
loads 5 → **20**, private loads 12 → **0**, `fma` 10 → 13.

### 3.2 …because the AGX backend already does the work

The native binary tells the opposite story:

| variant | g16s `__compute` | g17s `__compute` |
| --- | --- | --- |
| K1 baseline | 3584 | 3664 |
| K1 manually fully unrolled | **3584** | **3664** |

Byte-identical sizes. At the byte level only 114 / 6256 bytes differ on g16s
versus 835 / 6256 on g17s — the M5 backend rescheduled, M4 barely moved — but
the instruction budget is the same. **Source-level unrolling of these kernels
is a no-op; the AGX backend performs the SROA and the unrolling itself.**

Two further probes confirm what the backend does and does not unroll:

* the K loop stays **rolled** in the ISA. Sweeping K1's `axis_size`
  1024 / 2048 / 4096 gives 3296 / 3584 / 3696 bytes on g16s — sublinear, so the
  trip count is not baked in. Sweeping K2's `in_vec_size` 8192 → 4096 gives
  5216 → 5200 bytes, a 16-byte difference.
* K2's row loop and `j` loop **are** fully unrolled: 5216 bytes on g16s is
  consistent with a 4 × 2 expanded body.

### 3.3 Consequence

Within-iteration ILP is already maximal — roughly 17 concurrent loads are in
flight inside one K iteration once the backend has unrolled and scalarised
everything. There is nothing left to win there, which retires the whole
"unroll it / widen it / vectorise it" family for these two kernels.

What the backend does **not** do is rotate a load across the loop back-edge.
It cannot: speculating the next iteration's device load past the trip test is
not legal without a guard the compiler has no reason to invent. AGX issue is
in-order per thread, so in the baseline each K iteration's code load is issued
essentially at its point of use and its full latency is exposed, hidden only by
other resident threads.

**Cross-K-iteration software pipelining is therefore the only remaining lever
on this arm**, and it has to be written by hand.

### 3.4 This is not the closed `uint2` → `uint4` idea

`uint2` → `uint4` widening is closed twice in this programme, recorded as "not
bit-exact — repartitions the per-lane serial float accumulation" and "32 lanes
already cover a contiguous 256 B burst". Neither reason applies here.
`values_per_thread` stays 16, the load width stays `uint2`, the lane-to-value
mapping is untouched, and the accumulation order is untouched. Only the *issue
time* of an unchanged load moves.

## 4. Shipped precedent

The routed gate/up QMV `laguna_routed_nvfp4_swiglu_qmv_packed_top8keys_r1_bf16_v2`
(`lagunaRoutedGateUpR1Enabled`, `DARKBLOOM_ROUTED_GATEUP_R1`, default ON)
already has exactly this structure: a prologue that loads block-0 gate/up
`uint2` codes plus scale bytes, then a loop that snapshots `cur_*`, issues the
`next_block` loads, and only then runs `laguna_nvfp4_qdot_codes_16`. It is
shipped and default-on.

PR #301 (mine, merged) measured the same transformation in the *shared* gate/up
QMV at **−0.363 µs/call, CI [−0.495, −0.232], −4.80 %** on M4, and was left
default OFF only because its ABBA was order-confounded. PR #475 merged a
router-weight prefetch. Naively transferring −4.8 % to the 3122 µs/step K1+K2
pool gives ≈ −150 µs/step, which is 2.3 % of score — more than the 1.05 %
deficit to the record. That is a prior, not a prediction.

**K1 is the kernel that most resembles the shipped routed twin and is furthest
from it today**: it is the only one of the four with a single outstanding DRAM
load per thread in steady state.

## 5. Modelled ranking

| rung | kernel | pool (M4 µs/step) | outstanding DRAM loads / thread, before → after | ISA cost |
| --- | --- | --- | --- | --- |
| 1 | K1 QKV | 1702.9 | 1 → 2 | +32 B |
| 2 | K2 `o_proj` | 1419.5 | 4 → 8 | +160 B |

K1 ranks first on three independent grounds: the larger pool; the larger
*relative* change in memory-level parallelism (1 → 2 is the difference between
no overlap at all and some overlap, whereas K2's 4 → 8 is subject to
diminishing returns); and a 5× smaller instruction and register cost. It also
makes K1 structurally identical to the already-shipped, already-winning routed
twin.

This re-ranks the assignment's provisional order, which listed `o_proj` first.
The reason for the change is §3 and §4 above, both of which are new evidence
produced after the assignment was written.

## 6. Static verification of the two rungs

Prototypes were generated from the captured corpus and compiled to AGX native
code for both architectures before any build or timing work.

| variant | g16s `__compute` | g17s `__compute` | Δ vs base |
| --- | --- | --- | --- |
| K1 base | 3584 | 3664 | — |
| K1 header refactor only | 3584 | 3664 | **0** |
| K1 + depth-1 prefetch | 3616 | 3696 | **+32** |
| K2 base | 5216 | 5408 | — |
| K2 + depth-1 prefetch (codes only) | 5376 | 5568 | **+160** |
| K2 + depth-1 prefetch (codes *and* scales) | 5536 | 5728 | +320 |

Three things this buys:

1. **The header refactor is provably inert.** Splitting
   `laguna_tail_nvfp4_qdot` into a `uint2`-taking `_codes` entry point plus a
   delegating pointer form leaves the native binary byte-identical in
   `__reflection`, `__compute` and `__descriptor`. Only 35 bytes differ, all at
   offsets ≤ 1421, entirely inside the 1424-byte `__AIR_DATA` segment that
   embeds source text. No numerical or timing risk from the refactor itself.
2. **Both prefetch rungs survive the optimiser.** They are not folded away;
   they cost real instructions on both architectures.
3. **Prefetching scales as well as codes doubles the ISA cost for a quarter of
   the traffic.** K2 moves 32 code bytes and 4 scale bytes per thread per K
   iteration, and the scale byte is not consumed until the row's final
   multiply, so its latency is already covered by the ~32 fma of the row body.
   The shipped rungs prefetch **codes only**.

`applegpu-nt` exposes no register-count field (`metal-size -m` reports only
`__AIR_DATA`, `__reflection`, `__compute`, `__descriptor`), so occupancy cannot
be screened statically. It has to be screened empirically, which is what §2
reserves M4 for.

## 7. Implementation

Two independent env gates in `Sources/MLXFastModel/LagunaRuntimeModel.swift`,
both read at global-`let` initialisation so one build serves both arms of a
local A/B with no rebuild confound:

| gate | env | rung | kernel-name suffix |
| --- | --- | --- | --- |
| `lagunaDecodeNVFP4QKVPrefetchEnabled` | `DARKBLOOM_QKV_KBLOCK_PREFETCH` | 1 (K1) | `_pf1` |
| `lagunaOProjKBlockPrefetchEnabled` | `DARKBLOOM_OPROJ_KBLOCK_PREFETCH` | 2 (K2) | `_pf1` |

Both default OFF (`== "1"`). A gate's default is flipped to `!= "0"` only in
the commit that an official receipt measures, because the ranked host does not
set environment variables.

Bit-exactness argument, per rung:

* **K1.** `laguna_tail_nvfp4_qdot_codes(uint2 codes, …)` contains the original
  body verbatim; `laguna_tail_nvfp4_qdot(const device uint8_t* w, …)` becomes
  `return laguna_tail_nvfp4_qdot_codes(wq[0], …)`. The pipelined loop passes
  the same `uint2` the pointer form would have read (`wq2` advances
  `block_size/16` `uint2` = 256 B, exactly the `ws += block_size/2` it
  replaces). Products, order, FP32 accumulator, `simd_sum` and the BF16 cast
  are untouched. §6 row 2 shows the refactor alone is machine-code-identical.
* **K2.** Each row still consumes the same two `uint32` words in the same order
  into the same accumulator; `cur_code[row].x` / `.y` are literally `wl[0]` /
  `wl[1]`. The scale plane keeps its original schedule. The prefetch is guarded
  by `if (k + block_size < in_vec_size)`, so no out-of-bounds read occurs.

Alignment: K1's `ws` is `weight_codes + out_row*1024 + simd_lid*8` bytes and
K2's `ws` is `(uint32_t*)weight_codes + out_row*(in_vec_size/8) +
simd_lid*2`; both are 8-byte aligned for every lane, so the `uint2` access is
well-formed.

## 8. What this audit does *not* claim

* It does not claim these kernels are latency-bound on M5. It claims that
  within-iteration ILP is exhausted, that cross-iteration pipelining is the
  only remaining lever, and that the lever is now built and statically verified.
  Whether it pays has to be bought with M5 receipts.
* The ~191 kB in-flight figure in `research/CURRENT_RESEARCH_STATE.md:170` is an
  unmeasured Little's-law derivation, and the ~350 ns latency constant it uses
  is not measured anywhere in the repository. Neither is used to justify a
  decision here.
* M4 achieves 90–100 % of DRAM peak on all four kernels, so a **null on M4 is
  the expected outcome** and is not evidence against the hypothesis. Only a
  *regression* on M4 is informative, as a sign of lost occupancy.
