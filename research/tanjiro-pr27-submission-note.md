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

   That is necessary but **not sufficient**, and this cost me two design
   iterations worth writing down. When the injection magnitude is varied by
   *repeating passes* over the pool, the quantity that has to exceed cache is
   not the pool. The pass loop lives **inside the thread**

   ```
   for (p = 0; p < passes; ++p)
       for (i = 0; i < perThread; ++i) { acc ^= quads[idx]; idx += kThreads; }
   ```

   so after `perThread` strides `idx` has wrapped back to its start and each
   thread immediately re-reads *its own* addresses. A threadgroup of 256
   threads touches 4 KiB per stride, so its per-pass window is
   `perThread × 4 KiB`, and cross-pass hits are possible whenever
   `resident_threadgroups × window` fits in cache. Total pool size never enters
   that inequality.

   Measured **marginal** (pass-to-pass) rates, which is the quantity the fit
   actually uses, in situ through the harness on the development host whose
   independently measured sequential control is 262.5 GB/s and whose nominal
   hardware peak is 273 GB/s:

   | threads | threadgroups | uint4/thread | window/TG | marginal GB/s |
   | ---: | ---: | ---: | ---: | ---: |
   | **65,536** | **256** | **256** | **1 MiB** | **242** |
   | 131,072 | 512 | 128 | 512 KiB | 245 |
   | 262,144 | 1024 | 64 | 256 KiB | **339** |

   339 GB/s is **24% above the host's hardware peak**: the second and third
   passes are cache-served and the accounted bytes never reach DRAM. It is not
   lossless compression — scrambling the pool with a hash instead of a uniform
   fill changes nothing.

   A standalone replica of the same kernel, timed as an *average* over passes
   rather than a marginal, hides this: it reports 241.7 / 247.3 / 262.1 GB/s
   for the same three rows because the cold first pass dilutes the cached ones.
   **Only the marginal rate is diagnostic, and only the in-situ measurement
   produces it.** Choosing the grid from the standalone average is how I picked
   1024 threadgroups and lost a run.

   The shipped configuration is 2^16 threads = **256 threadgroups**. At that
   count every threadgroup is resident simultaneously, so the resident working
   set is the entire 256 MiB pool and cross-pass reuse is arithmetically
   impossible on any cache size. This also makes the choice *safe in the right
   direction* for an unseen larger machine: more GPU cores means more resident
   threadgroups, so a bigger machine pushes the reuse threshold up, and the
   configuration with the fewest threadgroups is the one that stays honest.
   Bandwidth is still saturated at that width — 242 GB/s is 92% of the
   sequential control, and the 512-threadgroup row agrees to 1%.
4. **Never express the injection magnitude through a Metal function constant.**
   In this repo there is a recorded precedent where a mid-process function
   constant flip forced a second pipeline compile *inside* timed prefill for a
   reproducible 15–24% regression. All magnitudes here are host-side loop counts
   and buffer sizes, fixed before the first forward; the Metal sources are
   byte-identical across all configurations.
5. **Command-buffer count must not vary between the runs being differenced.**
   MLX's residency-set encoder commits a command buffer when it exceeds either
   an operation count or a buffer-megabyte budget, and both budgets are selected
   from the GPU family string. Probing `MTL::Device::architecture()->name()`
   directly is worth doing rather than inferring it: the development host
   reports `applegpu_g16s`, and the trailing `s` class selects **50 operations /
   50 MB**, not the 40/40 that a `g`-class name would have selected. The 256 MiB
   pool is 1.34× the megabyte budget and the GEMM operands are 0.42× it, so both
   sit in a regime where the *count* budget dominates; the injection is kept
   below 25 operations per layer boundary so no configuration crosses the
   threshold that a neighbouring one does not.
6. **Empty dispatches must be serialized to measure anything.** MLX creates its
   compute encoder with `MTL::DispatchTypeConcurrent` and inserts a memory
   barrier only when a dispatch binds a buffer that a previous dispatch wrote
   (`mlx/backend/metal/device.cpp`). Independent empty dispatches therefore run
   *concurrently* and cost nearly nothing. This is not hypothetical — 40
   unchained empty dispatches per step moved the decode step by 0.006 ms, i.e.
   0.154 µs each against a 2.53 µs isolated cost, a 16× under-read that would
   have been reported as a real constant. The injected empty dispatches are
   therefore chained through a single global tail: each binds the previous one's
   sink as an unread input, and the tail is carried **across layer boundaries**
   so the chain is unbroken for the whole forward. They then serialize exactly
   like the model's real dependent dispatch stream.
7. **Placement.** The empty dispatches are spread across all 40 layer
   boundaries rather than batched, so their threadgroup-launch ramp overlaps
   real memory traffic and the measured cost is the *in-situ* cost rather than
   the isolated one. The two differ by roughly 10–30% and the in-situ figure is
   the one a dispatch-count-reduction estimate must use.
8. **The official runner sets no environment variables**, so the injection is ON
   by default in the submitted tree. Locally the same binary serves every
   configuration through `DARKBLOOM_INJECT_*` overrides, which is why the local
   validation is cheap.
9. **RAM.** Total scratch is 296 MB (256 MiB pool + 40 MB of GEMM operands),
   allocated on first touch during the untimed warm forward, so it is counted
   before the resident-weight wiring walk and never inside a timed window.

### Injection magnitudes

| unit | size per dispatch | shape | where |
| --- | --- | --- | --- |
| DRAM sweep | 268,435,456 B read per pass | 256 TGs × 256 threads, 256 `uint4`/thread | one dispatch per single-token decode step |
| bf16 GEMM | 17,179,869,184 FLOP | `512×8192 @ 8192×2048` | multi-token forwards only |
| empty dispatch | 0 B, 0 FLOP | 160 TGs × 256 threads | both paths, spread over the 40 layer boundaries |

The GEMM shape is deliberately the real prefill shape class (`M = 512`,
`N = 2048`, deep `K = 8192`) so the rate that comes out is the rate a prefill
roofline needs, not a synthetic MMA peak. Depth was preferred over dispatch
count so the residual per-dispatch confound stays under 0.1 ms. One shared
`matA`/`matB` pair is reused by every injected GEMM, so MLX's own deduplication
absorbs the operand-read charge and the measured slope is arithmetic, not
traffic.

## Configurations

| run | sweep passes / step | bytes / decode step | GEMMs / forward | FLOP / forward | empty dispatches (decode / forward) |
| --- | ---: | ---: | ---: | ---: | ---: |
| A | 1 | 268.44 MB | 20 | 343.60 GFLOP | 0 / 0 |
| B | 3 | 805.31 MB | 40 | 687.19 GFLOP | 0 / 0 |
| C | 1 | 268.44 MB | 20 | 343.60 GFLOP | 600 / 1000 |

Fits:

```
DRAM GB/s     = 536.87 MB   / (T_B - T_A)
matrix FLOP/s = 343.60 GFLOP/ (S_B - S_A - 20 * c_prefill)
c_decode      = (T_C - T_A) / 600      <- in-situ, the number that matters
c_prefill     = (S_C - S_A) / 1000
```

`A` appears in both differences, so a disagreement between the two fits is a
built-in anomaly detector. `A` and `B` issue the **identical number of
dispatches and bind the identical buffer set** — only host-side loop counts
differ — so every per-dispatch and per-command-buffer term cancels exactly in
`B - A` and the two rate fits need no dispatch-cost correction beyond the 20
extra GEMM dispatches.

The empty-dispatch counts in `C` are 15 per layer on the decode path and 25 per
layer on the prefill path. That is deliberately below the point where the
injected operations could push a command buffer past MLX's per-buffer operation
threshold and add a commit, which would contaminate the constant it is trying
to measure (see design note 5).

## Reproduction

The submitted tree *is* configuration A: the official runner sets no environment
variables, so the defaults apply. Locally the same binary serves every
configuration:

```bash
./benchmark.sh --local-iterate                                       # A
DARKBLOOM_INJECT_SWEEP_PASSES=3 DARKBLOOM_INJECT_PREFILL_MATMULS=40 \
  ./benchmark.sh --local-iterate                                     # B
DARKBLOOM_INJECT_DECODE_EMPTY=600 DARKBLOOM_INJECT_PREFILL_EMPTY=1000 \
  ./benchmark.sh --local-iterate                                     # C
DARKBLOOM_INJECT_DECODE_SWEEPS=0 DARKBLOOM_INJECT_PREFILL_MATMULS=0 \
  ./benchmark.sh --local-iterate                                     # zero point

# official
mlxfast submit --note-file <this note> --model "Claude Opus 5"
```

Full knob list, with the shipped default in parentheses:
`DARKBLOOM_INJECT_DECODE_SWEEPS` (1), `DARKBLOOM_INJECT_SWEEP_PASSES` (1),
`DARKBLOOM_INJECT_PREFILL_MATMULS` (20), `DARKBLOOM_INJECT_DECODE_EMPTY` (0),
`DARKBLOOM_INJECT_PREFILL_EMPTY` (0), `DARKBLOOM_INJECT_EMPTY_SPREAD` (1),
`DARKBLOOM_INJECT_EMPTY_TG` (160).

## Results

### Development-host calibration (M4 Pro, `applegpu_g16s`, 20 GPU cores, 48 GB)

The instrument was gated on the development host first: it has to recover
constants that were measured there by other means, to within 10%, before a
receipt is spent. Paired `--local-iterate` receipts, `S` and `T` as defined
above:

| run | sweep grid | passes | GEMMs | empties d/p | S (ms) | T (ms) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| zero | — | 0 | 0 | 0/0 | 583.311 | 9.0068 |
| unchained | 2^17 | 1 | 100 | 40/40 | 808.203 | 10.1526 |
| LA | 2^17 | 1 | 100 | 0/0 | 799.522 | 10.1464 |
| LB | 2^17 | 3 | 300 | 0/0 | 1260.390 | 12.3377 |
| LA2 | 2^18 | 1 | 100 | 0/0 | 802.075 | 10.0595 |
| LB2 | 2^18 | 3 | 300 | 0/0 | 1266.633 | 11.6421 |

Every run returned `passed_correctness: true`, `max_abs_diff: 0`,
`peak_ram_gb: 21`. The injection is output-neutral in practice as well as by
construction.

| quantity | instrument (in situ) | independent control | error |
| --- | ---: | ---: | ---: |
| achievable DRAM read | **245.0 GB/s** | 262.5 GB/s sequential probe | −6.7% |
| MLX steel bf16 GEMM, `512×8192×2048` | **7.40–7.46 TFLOP/s** | 6.77 TFLOP/s profiled on the model's own `attn_proj` | +9–10% |
| chained empty dispatch, 160 TGs | measured in configuration C | 2.5 ± 0.4 µs standalone | — |

Three things fall out of the calibration that are worth more than the numbers:

- The DRAM figure lands at 93% of the standalone sequential control, which is
  the *expected* efficiency of a grid-stride `uint4` read versus an optimal
  sequential one — not a suspicious exact match. Both the shipped
  256-threadgroup grid and the 512-threadgroup grid produce it, agreeing to 1%.
- The FLOP figure is **3.9× below** the host's 28.76 TFLOP/s MMA ceiling, and
  the profiled rate of the model's own GEMM family on the same host is 4.2×
  below it. Any roofline built on a *ceiling* rather than an *achieved* rate is
  wrong by that factor. This is the single most consequential number here: it
  turns "is this GEMM compute bound?" from an assumption into an arithmetic
  question.
- Changing the sweep grid moved the DRAM axis by 38% and the FLOP axis by 0.8%.
  That is a clean control on the differencing method: the axis that should have
  moved did, and the axis that should not have did not.

### Ranked-host results

_Appended per submission as each receipt lands._

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
  reads the host rate. A standalone sweep of the same chained empty dispatch on
  the development host gives 1.56 µs at 1 threadgroup, 1.11 at 8, 1.19 at 40,
  2.53 at 160 and 6.74 at 512, i.e. roughly **1.15 µs fixed + 11.9 ns per
  threadgroup**. The fixed part is the one a dispatch-count reduction recovers;
  the per-threadgroup part is work that has to happen somewhere anyway.
- The constants are *achievable rates for the shapes probed*, and shape matters
  enormously in the cache-resident regime. On the development host the same
  read kernel, given a working set small enough to stay resident, delivers
  1780 GB/s at 8 threadgroups over a 256 KiB–1 MiB window but only ~1000–1200
  GB/s at the 32-threadgroup × 1024-thread shape the model's fused attention
  actually uses, and *less* again at 128 threadgroups. Cache-resident bandwidth
  on this architecture is aggregate-limited, not per-lane, and it is not a
  single number. Do not reuse the DRAM constant for an L2-resident kernel or
  vice versa.

## Learning

The general point is more useful than the numbers: **on a sealed benchmark with
a fixed harness, a deliberately slowed output-neutral candidate is a
measurement instrument.** Any quantity that enters the timing linearly can be
extracted by injecting a known amount of it and differencing two receipts, and
correctness gates are preserved by construction rather than by luck. Three
submissions that score nothing bought four hardware constants that every future
optimization decision on this benchmark divides by.

Two failures are worth more than the successes. Both would have produced a
plausible-looking constant that was wrong in the direction that makes an
optimization arm look attractive:

1. An injected dispatch that binds no buffer a previous dispatch wrote **runs
   concurrently** under MLX's `DispatchTypeConcurrent` encoder and reads 16×
   cheaper than it is. If you inject dispatches to price dispatches, chain them.
2. Repeating passes over a large pool does not defeat cache. The relevant
   quantity is `resident_threadgroups × per-threadgroup-per-pass window`, and
   a *standalone* timing that averages a cold pass with cached ones hides the
   problem completely. Only the marginal rate is diagnostic, and the harness is
   the thing that produces a marginal rate.

Generalised: when an instrument is built out of injected work, every design
choice must be checked against the possibility that the machine found a way to
not do the work. The two tests that catch it are (a) does the measured rate
exceed a known hardware ceiling, and (b) does an axis that should be invariant
under a design change stay invariant.

## Next step

The constants feed directly into three decisions this programme has been making
on estimates: whether the decode step is bandwidth-closed (compare `T` against
the model's per-token byte count divided by the DRAM constant), whether the
512-token seed forward is compute- or bandwidth-bound (the same test on `S` with
the achieved-GEMM constant, *not* an MMA ceiling), and whether reducing the
~406 dispatches per decode step is worth a student (the in-situ per-dispatch
constant times the reduction). With the constants measured rather than assumed,
those become arithmetic. The instrument itself should then be deleted — it is a
measuring tool, not a candidate, and it is one delimited block plus one call
site precisely so that deletion is a two-line diff.

_This work was performed by an AI agent (OpenHands) on behalf of the submitting
researcher._
