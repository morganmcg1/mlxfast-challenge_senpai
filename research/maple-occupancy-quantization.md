# Occupancy quantization closes the fused-attention width family

Host: AWS-hosted Apple M4 Pro, 20 GPU cores, 48 GB. Ranking host: M5 Max,
**40 GPU cores** (Apple ships M5 Max in 32- and 40-core GPU configurations;
neither is >= 48). BASE_SHA `0d980bb03040182b4595cab070fd249944ea3621`.

Instrument: `senpai/tools/full-attn-probe`, adapted from fern's
`senpai/tools/sliding-attn-probe` to the growing-KV family (48 query heads,
8 KV heads, GQA 6, `head_dim` 128, 10 layers/step, contiguous bf16 cache,
`capacity` 640, live prefix N=576). Bytewise output diff against the shipped
kernel; `min` of 9 round-robin blocks of 20 steps.

## 1. The GPU runs exactly one 1024-thread threadgroup per core

The new `--occupancy` mode times a fixed kernel at `g = 1..48` dispatched
threadgroups, alternating scan direction per round so host drift cannot fake a
step. Both kernels give the same staircase:

| dispatched threadgroups | width-1 us/dispatch | width-2 us/dispatch |
| --- | ---: | ---: |
| 1 | 22.81 | 29.46 |
| 20 | 21.72 | 30.90 |
| **21** | **30.12** | **39.78** |
| 24 | 30.10 | 40.86 |
| 40 | 33.73 | 40.75 |
| **41** | **38.57** | **49.07** |
| 48 | 39.78 | 50.57 |

Flat 1..20, riser at 21, flat 21..40, riser at 41. Twenty concurrent 1024-thread
threadgroups on a 20-core GPU is **one threadgroup per core**.

The riser positions are identical for `staticThreadgroupMemoryLength` 9216 B
(width-1) and 17920 B (width-2). **Threadgroup memory is not the occupancy
limiter in this family; the 1024-thread threadgroup size is.** That
independently explains fern's null result for reducing threadgroup memory
17920 -> 9728 B: it cannot buy occupancy that the thread count already caps.

## 2. Per-threadgroup cost is sublinear in heads-per-threadgroup

Single-threadgroup measurements isolate the cost of one threadgroup with no
occupancy effects: 22.81 us at 1 head, 29.46 us at 2 heads. Doubling the heads
costs **1.29x, not 2x**, because the threadgroup's K/V stream is shared across
its heads. Fitting `T_tg(w) = a + b*w`:

```
a = 16.16 us  (KV stream, amortized over the heads in the threadgroup)
b =  6.65 us  (per-head work)
```

A linear `w/2` work model is therefore wrong, and any prediction built on one
(including my own pre-measurement estimate) overstates the cost of wide
threadgroups and understates the cost of narrow ones.

## 3. Width 2 is the argmax on the ranking host, and it is already shipped

Valid widths divide GQA 6. Combining the two measurements above:

| width | threadgroups | per-tg cost | waves @ 20 cores | waves @ 40 cores | 40-core cost |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 48 | 22.81 us | 3 | **2** | 30.10 us |
| **2** | **24** | **29.46 us** | **2** | **1** | **29.60 us** |
| 3 | 16 | 36.11 us | 1 | 1 | 36.11 us |
| 6 | 8 | 56.06 us | 1 | 1 | 56.06 us |

On 40 cores, width 2's 24 threadgroups fit in a single wave while width 1's 48
do not, and every width above 2 pays more per threadgroup than it saves in
waves. **Width 2 is optimal for any host with 24..47 GPU cores**, which covers
both shipped M5 Max configurations.

On 20 cores the ordering inverts, because width 2 also needs 2 waves there:
width 1 measures **-1.11 us/layer (-2.75%)** across 6 independent within-process
orderings, all 6 with the same sign and all 6 with 0 bytewise output mismatches.
That is a genuine M4 Pro win that **does not transfer**, and the crossover is
purely the inequality `24 <= cores < 48`. A host with >= 48 GPU cores would flip
it to -24.5%, so this width is worth revisiting only for an Ultra-class part; no
M5 Max configuration reaches 48.

Directionally this also explains fern's sliding-attention width-8 regression:
64/8 = 8 threadgroups leaves 12 of 20 cores idle while each threadgroup pays
`a + 8b`. The measured +95.42 us/layer is larger than these coefficients
predict (~+29 us), which is consistent with width 8 needing `8*BN*BD*4` =
32768 B of threadgroup memory — exactly the device limit.

## 4. Why the "raise in-flight bytes" remap cannot generalize here

nezuko's rows-per-simdgroup win took a kernel from 42% to 89% of the measured
260.2 GB/s DRAM ceiling by raising memory in flight per barrier-bounded
threadgroup. The three kernels in this assignment are not short of in-flight
bytes:

- **`full_fused_attn_grow_v1`** reports 43% of ceiling only because the
  denominator counts *unique live* K/V bytes (23.6 MB/step). What the kernel
  actually requests is 70.8 MB/step at width 2 — **172 GB/s of requested
  bandwidth against a 260 GB/s DRAM ceiling**, with the 3x redundancy across
  the threadgroups sharing a KV head served from cache (the live K+V working
  set is 2.4 MB/layer). Width 1 doubles requested bandwidth to 355 GB/s,
  i.e. *above* the DRAM ceiling, and still gets faster — proof that this kernel
  streams from cache and is bound by occupancy, not DRAM.
- **`residual_rms_router_bf16_2048_rpg8_keys_v1`** cannot change its in-flight
  bytes by retiling at all: `tiles * rows_per_group == 256` at every setting, so
  total requested bytes are invariant. The rows-per-group sweep the brief asked
  for is already recorded as null in the shipped docstring
  (`LagunaRuntimeModel.swift:604-628`: rpg1 vs rpg8 paired A/B mean -5 us/step,
  rpg4/rpg2 +25/+35 us, with an explicit "do not re-sweep"), and for the same
  occupancy reason found here — rpg8 puts 32 threadgroups on the machine, which
  is 1 wave at 40 cores, while rpg64 puts only 4. The one lever retiling leaves
  open is weight-hoist depth, swept below and also null.
- **`oproj_act_h48_v1`** is already at the rows-per-simdgroup argmax
  (`results_per_simdgroup = 4`, `num_simdgroups = 2`, 256 threadgroups of 64
  threads) and has only 37 us/step of headroom = 0.2% of decode even at the
  ceiling.

## 5. Router weight-hoist depth is null

Hoist depth is the number of bf16 `vec<bfloat,4>` row chunks loaded into
registers before the MAC block; it must divide `router_blocks == 16`. Depth 4
ships. All depths are bit-exact (loads move, `router_result[0]` keeps its strict
`(block, i)` order); all arms ran 120 teacher-forced steps with 0 divergences.

| depth | in-flight bytes/dispatch | n | mean whole-step |
| ---: | ---: | ---: | ---: |
| 1 | 64 KB | 1 | 8.785 ms |
| **4 (shipped)** | **256 KB** | **4** | **8.783 ms** |
| 8 | 512 KB | 1 | 8.772 ms |
| 16 | 1 MB | 4 | 8.770 ms |

A **16x change in memory-level parallelism moves the whole step by 13 us
(0.15%)**, and the depth-1 arm that should have been clearly slower is not
slower at all. With 39 dispatches/step at 6.8 us/call, the router's distance
from the DRAM roofline is fixed per-dispatch cost, not exposed load latency.
Not promotable: 13 us is inside the base spread (8.775..8.794 ms, n=4).

## 6. Instrument note: the whole-step probe produced a false positive

`research/decode_probe.py` medians over 120 teacher-forced steps have a
run-to-run spread of roughly +-15 us, which is the same size as every effect
measured here. In the first interleaved batch, 4 width-1 runs
(8.646/8.672/8.761/8.766 ms) fell entirely below 4 base runs
(8.775..8.794 ms) — complete separation, nominally p = 1/70. **It did not
replicate.** A second batch put width-1 at 8.774/8.761 ms against base
8.774/8.769/8.784 ms, and the two sub-8.68 ms runs never recurred in any arm.

Final pooled whole-step tally across three batches:

| arm | n | mean | sd | vs base |
| --- | ---: | ---: | ---: | ---: |
| base | 8 | 8780.1 us | 7.7 us | — |
| width 1, all runs | 7 | 8734.1 us | 52.1 us | -46.0 us |
| width 1, excluding the two outliers | 5 | 8764.2 us | 6.1 us | **-15.9 us** |

The base arm's own standard deviation is 7.7 us over 8 runs, so the instrument
is well behaved; the width-1 arm's 52.1 us is entirely the two outliers. The
robust estimate **-15.9 us/step (-0.18% step, -0.09% M4 decode)** agrees with
the isolated probe's -11.1 us/step, and the mechanism cannot produce -46 us.

The lesson is that complete separation across n=4 is not evidence when the arms
are measured in one alternating sequence on a host with slow state drift; only
the isolated within-process probe resolves a 2.75% per-kernel effect. Had I
stopped at the first batch I would have reported a 4x overstated win.

## 7. Disposition

Nothing from this arm is promoted, and the scored surface on this branch is
byte-identical to `BASE_SHA` (142 files, 2,999,655 B, 345 B headroom intact).
The width-1 kernel and the router hoist-depth knob were reverted out of
`Sources/MLXFastModel/LagunaRuntimeModel.swift`; they remain reachable in commit
`9f88d94` and renderable into the probe from there.

If the advisor ever wants to spend an M5 dispatch testing the extrapolation in
§3, the recipe is to *replace* the `lagunaFullFusedAttentionKernel` literal with
the width-1 body from `9f88d94` and set `grid: (heads * 1024, 1, 1)` — that is
byte-negative (the width-1 body renders 5,144 B smaller) and bit-exact. The
prediction being tested is **+1.7% on the 10 full-attention dispatches, i.e.
about +0.04% decode**, so it is a check on the occupancy model rather than a
candidate win.

What would actually be worth an arm, and is not this mechanism: on a 40-core
host the full-attention dispatch occupies only 24 of 40 cores, and the sliding
dispatch 32 of 40. No head-axis width can fix that, because `48/w` never lands
in `(24, 40]`. Splitting the K/V prefix across two threadgroups per head
(flash-decoding split-K, then a combine pass) would put 48 threadgroups of half
the sequence work on the machine and is the only way I can see to fill it. That
changes the reduction order, so it is not bit-exact and needs its own
correctness argument.
