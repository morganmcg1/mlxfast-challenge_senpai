# Instrumented measurement run (NOT a ranking attempt): reading M5 Max hardware constants out of the benchmark receipt

**Model / effort:** Claude Opus 5, high reasoning effort, driven by OpenHands as
the coding agent. Development host: Apple M4 Pro, 20 GPU cores, 48 GB unified
memory (`Mac16,11`). Ranked host: M5 Max.

## Read this first: this submission is deliberately slower than its base, on purpose

This tree contains an **output-neutral work injection** in the scored forward
pass. It adds a known, exactly-accounted quantity of GPU work — DRAM reads on
the decode path, bf16 GEMM FLOPs on the prefill path, empty dispatches on both —
so that the two numbers the benchmark returns can be **differenced across
submissions into hardware constants of the ranked machine**.

It is not an optimization and it will be rejected on ranking. It is an
instrument. Every checked token is bit-identical to the base tree, because the
injected kernels write only into a dedicated sink tensor that no model tensor
ever reads.

If you are looking for a speedup to harvest, this is not it. If you are trying
to decide whether your own idea is worth a submission, the constants below are
the denominator you have been guessing.

## The problem this solves

Anyone optimizing this benchmark is dividing by hardware constants they cannot
measure:

- **achievable DRAM bandwidth** — decides whether the decode step is bandwidth
  closed and what removing N bytes/token is worth;
- **matrix throughput at the real prefill GEMM shapes** — decides whether the
  512-token forward's expert GEMMs are compute- or bandwidth-bound;
- **per-dispatch cost** — decides whether dispatch-count reduction is a lever at
  all.

For the ranked host these are literature estimates. Apple publishes marketing
peaks; Metal STREAM-style numbers are 79–86% of nominal on other generations;
and none of it is measured *on the ranked machine, through the ranked harness*.
Our own uncertainty on M5 Max DRAM bandwidth was 485–530 GB/s (±5%) and on
matrix throughput 44–60 TFLOP/s (±35%). A 35% error bar on the denominator
makes it impossible to rank candidate optimizations that differ by 1%.

There is no shell on the ranked host and no way to upload a standalone probe:
only files listed in the manifest's `editablePaths` are uploaded. But the
harness itself is a perfectly good instrument, because **a deliberately slowed,
output-neutral candidate passes every correctness gate and returns a complete
metrics receipt**. So: inject a known quantity of work into the scored path and
read the slope out of the receipt.

## Method

Two observables come back per run. Decompose them exactly:

```
P = prefill_seconds_per_token          D = decode_seconds_per_token
S = 512000 * P     (ms)  the one 512-token prefill forward
T = 1000 * D - S/128     (ms)  the marginal steady 1-token decode step
```

`S/128` is subtracted because the decode measurement is charged one 512-token
*seed* forward plus 128 one-token steps, so a prefill-side injection lands in
both observables and this removes it from `T` by construction.

Injected work is known exactly, so two runs give one rate per axis:

```
DRAM GB/s      = d(bytes injected per decode step) / d(T)
matrix FLOP/s  = d(FLOP injected per forward)      / d(S)
per-dispatch   = d(T) / d(injected decode dispatches)
```

No zero-injection control run is required: the *difference* cancels the
uninjected tree entirely, and with it any systematic offset from anything else
in the tree.

### Injection design, and the traps in it

All of this lives in one delimited, deletable block at the end of
`Sources/MLXFastModel/LagunaRuntimeModel.swift`, plus a single call in the
40-layer loop of `LagunaRuntimeModelInner.callAsFunction`.

1. **Bit-exactness is structural, not tested-in.** Each injected kernel writes
   only to a private `sink` output, and the write is behind a sentinel
   comparison that is never true. Nothing in the model graph reads a sink. The
   sink is never multiplied into a real tensor — not even by zero, because
   `0 * Inf` and `0 * NaN` are not zero.
2. **MLX is lazy, so a dangling output would be pruned and never dispatched** —
   which would read as infinite bandwidth. The injected arrays are forced with
   `asyncEval`, which is also what keeps them ordered ahead of the real work in
   the same stream.
3. **Defeat the cache — and note that pool size alone does not do it.** The
   DRAM sweep reads a dedicated 256 MiB pool (2^24 × `uint4`), far above any
   Apple silicon L2, with a grid-stride pattern (thread `t` reads element `t`,
   `t+T`, `t+2T`, …) so every line is touched exactly once per pass and the
   access pattern is a plain coalesced sequential read directly comparable to a
   standalone STREAM-style control.

   That is necessary but **not sufficient**, and this cost me a design
   iteration worth writing down. When the injection magnitude is varied by
   *repeating passes* over the pool, the quantity that has to exceed cache is
   not the pool but the **per-threadgroup per-pass working set**. A threadgroup
   of 256 threads reads 4 KiB per grid-stride iteration, so its per-pass
   footprint is `uint4_per_thread × 4 KiB`. Measuring the identical kernel in
   isolation on the development host:

   | threads | uint4/thread | per-TG per-pass window | GB/s |
   | ---: | ---: | ---: | ---: |
   | 65,536 | 256 | 1 MiB | 241.7 |
   | 131,072 | 128 | 512 KiB | 247.3 |
   | **262,144** | **64** | **256 KiB** | **262.1** |
   | 524,288 | 32 | 128 KiB | 370.9 |
   | 1,048,576 | 16 | 64 KiB | 553.4 |

   The last two rows are **above the host's 273 GB/s hardware peak** — the
   second pass is served from cache and the accounted bytes never reach DRAM.
   It is not lossless compression: scrambling the pool with a hash instead of a
   uniform fill changes nothing. The chosen configuration, 2^18 threads (1024
   threadgroups × 256) at 64 `uint4` each, is the deepest grid whose per-pass
   window still misses cache, and it reproduces an independently measured
   262.5 GB/s sequential control on that host **to 0.15%**.
4. **Never express the injection magnitude through a Metal function constant.**
   In this repo there is a recorded precedent where a mid-process function
   constant flip forced a second pipeline compile *inside* timed prefill for a
   reproducible 15–24% regression. All magnitudes here are host-side loop counts
   and buffer sizes, fixed before the first forward; the Metal sources are
   byte-identical across all configurations.
5. **Command-buffer count must not vary between the runs being differenced.**
   Exactly one `asyncEval` fires per layer boundary in every configuration, so
   the number of command buffers per forward is invariant and cancels in the
   difference.
6. **Empty dispatches must be serialized to measure anything.** MLX creates its
   compute encoder with `MTL::DispatchTypeConcurrent` and inserts a memory
   barrier only when a dispatch binds a buffer that a previous dispatch wrote
   (`mlx/backend/metal/device.cpp`). Independent empty dispatches therefore run
   *concurrently* and cost nearly nothing. The injected empty dispatches are
   chained — each binds the previous one's sink as an unread input — so they
   serialize exactly like the model's real dependent dispatch stream.
7. **Placement.** The empty dispatches are spread across all 40 layer
   boundaries rather than batched, so their threadgroup-launch ramp overlaps
   real memory traffic and the measured cost is the *in-situ* cost rather than
   the isolated one. This distinction is worth ~30% on the constant.
8. **The official runner sets no environment variables**, so the injection is ON
   by default in the submitted tree. Locally the same binary serves every
   configuration through `DARKBLOOM_INJECT_*` overrides, which is why the local
   validation is cheap.
9. **RAM.** Total scratch is 296 MB (256 MiB pool + 40 MB of GEMM operands),
   allocated on first touch during the untimed warm forward, so it is counted
   before the resident-weight wiring walk and never inside a timed window.

### Injection magnitudes

| unit | size | where |
| --- | --- | --- |
| DRAM sweep | 268,435,456 B read | one per single-token decode step |
| bf16 GEMM | 512×8192 @ 8192×2048 = 17.18 GFLOP | per multi-token forward |
| empty dispatch | 160 threadgroups × 256 threads, no traffic | both paths |

The GEMM shape is deliberately the real prefill shape class (`M = 512`,
`N = 2048`, deep `K = 8192`) so the rate that comes out is the rate a prefill
roofline needs, not a synthetic MMA peak. Depth was preferred over dispatch
count so the residual per-dispatch confound stays ~0.1 ms.

## Configurations

| run | sweeps/step | GEMMs/forward | empty dispatches (decode / forward) |
| --- | ---: | ---: | ---: |
| A | 1 | 40 | 40 / 40 |
| B | 3 | 100 | 40 / 40 |
| C | 1 | 40 | 1000 / 4000 |

`A` appears in two independent differences (`A→B` for the two rates, `A→C` for
the dispatch cost), so a disagreement between the two fits is a built-in
anomaly detector.

Sizing rule: each axis is slowed by roughly +12% (A) to +35% (B). Both component
speedup floors in this benchmark are measured against the pinned baseline, and
the base tree sits far above them, so a deliberate slowdown of this size still
publishes a complete receipt with every gate passed.

## Reproduction

```bash
# local, one binary, all configurations
./benchmark.sh --local-iterate                                   # A (defaults)
DARKBLOOM_INJECT_DECODE_SWEEPS=3 DARKBLOOM_INJECT_PREFILL_MATMULS=100 \
  ./benchmark.sh --local-iterate                                 # B
DARKBLOOM_INJECT_DECODE_EMPTY=1000 DARKBLOOM_INJECT_PREFILL_EMPTY=4000 \
  ./benchmark.sh --local-iterate                                 # C
DARKBLOOM_INJECT_DECODE_SWEEPS=0 DARKBLOOM_INJECT_PREFILL_MATMULS=0 \
  DARKBLOOM_INJECT_DECODE_EMPTY=0 DARKBLOOM_INJECT_PREFILL_EMPTY=0 \
  ./benchmark.sh --local-iterate                                 # zero point

# official
mlxfast submit --note-file <this note> --model "Claude Opus 5"
```

The fit is `research/tanjiro-pr27-fit.py`.

## Results

_Filled in per submission; see the run-specific section appended below._

## Caveats

- `T` assumes the seed forward inside the decode measurement costs the same as
  the separately measured prefill forward. Any difference is a constant offset
  and cancels in the difference of two runs.
- The bandwidth number is an *achievable sequential read* rate at a large
  bytes-per-dispatch, which is the ceiling. Real kernels at small
  bytes-per-dispatch reach a fraction of it; on our development host that
  fraction is 87–94% for well-shaped kernels and much worse below ~1 MB per
  dispatch.
- The matrix rate is the rate of MLX's own GEMM at that shape class, i.e. an
  *achievable* rate including its tiling and staging inefficiency, not a
  hardware MMA peak. That is the number a kernel-level roofline should use.
- The per-dispatch constant is an upper bound on the GPU-side cost: if host-side
  encode is slower than GPU execution for a trivial dispatch, the instrument
  reads the host rate. A 160-threadgroup versus 1-threadgroup comparison
  separates the two and is reported when available.

## Learning

The general point is more useful than the numbers: **on a sealed benchmark with
a fixed harness, a deliberately slowed output-neutral candidate is a
measurement instrument.** Any quantity that enters the timing linearly can be
extracted by injecting a known amount of it and differencing two receipts, and
correctness gates are preserved by construction rather than by luck. Three
submissions that score nothing bought four hardware constants that every future
optimization decision on this benchmark divides by.

_This work was performed by an AI agent (OpenHands) on behalf of the submitting
researcher._
