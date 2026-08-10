# R110-B — double-buffered gather-GEMM staging: Stage-0 STOP

**Assignment** `maple-r110-b-gemm-double-buffer-staging` / `r110-b-rev1`
**PR** #693 · **base** `codex/mlxfast-maple-20260804-advisor` @ `32665a6b`
**Host** Apple M4 Pro (Apple GPU generation 16), `maxThreadgroupMemoryLength = 32768 B`

## Verdict

**STOP — `N-GEMM-WAR-BARRIER-FREE`.** The preregistered stop rule fires
decisively, and a second, independent finding says the Part-2 `_nax` port
should not be funded either.

**No file on `editablePaths` was modified.** `git diff --numstat 32665a6b --
Sources Vendor benchmark.json Package.swift` is empty. Everything below is
measurement on a standalone rig; there is no runtime change to validate with
`run_upstream_equivalence.sh` and nothing to time under `--local-iterate`,
because the experiment's job was to decide whether a runtime change was worth
writing at all. It is not.

## The stop rule

> If deleting the write-after-read barrier is worth **< 3 %** of
> `nvfp4_gather_qmm_rhs_nt` kernel time, stop.

Measured, kernel-time weighted: **0.83 %**. Rule fires with a 3.6× margin.

## Method

`research/edward_r110_gemm_db_bench.swift` is a standalone Swift + Metal rig
that reproduces the shipped kernel exactly rather than approximating it. It
extracts the `R"preamble( ... )preamble"` body from
`Vendor/mlx-swift/Source/Cmlx/mlx-generated/{utils,quantized_utils,gemm,fp_quantized}.cpp`
in the same order `get_gather_qmm_kernel` uses
(`jit_kernels.cpp:952-975`), appends the shipped template instantiation

```
nvfp4_gather_qmm_rhs_nt_bfloat16_gs_16_b_4_bm_16_bn_32_bk_32_wm_1_wn_2
```

and compiles it with `fastMathEnabled = false` to match `device.cpp:630`.
Function constants 200/201/202 (`align_M/N/K`) are all `true`; buffer indices
follow `quantized.cpp:1776-1789`. Every variant is produced by **string
mutation of that extracted source**, so no vendored file is edited and no MLX
rebuild is required — which is also why this experiment could run at all
without touching the submission surface.

Timing is `cb.gpuEndTime - cb.gpuStartTime` over `ED_REPS` dispatches, median
of `ED_CBS` command buffers after 3 warm-ups, with the variant list swept
ABBA (forward then reverse) `ED_PAIRS` times and an empty-kernel null control
at both ends. Observed spreads are 0.0–0.7 %, and the headline numbers
reproduced across two independent full runs.

### Variants

| tag | mutation | threadgroup memory |
|---|---|---|
| `base` | shipped source, unmodified | 3840 B |
| `nobar` | WAR barrier deleted — **numerically wrong**, upper-bound probe only | 3840 B |
| `db` | true ping-pong, runtime `cur` parity | 7680 B |
| `db2` | true ping-pong, unrolled parity | 7680 B |
| `dbmem` | 2× staging allocated, shipped single-buffer schedule — **bit-identical to base** | 7680 B |
| `noload` | `load_unsafe()` removed, both barriers and the mma kept | 3840 B |
| `nomma` | mma removed | **0 B — invalid, see below** |

`dbmem` is the control that makes this experiment interpretable: it pays the
double-buffer *footprint* without receiving any of its *benefit*, so
`db2 − dbmem` isolates the pipelining mechanism from the occupancy tax it
requires.

The ping-pong variants need no loader edits: both `QuantizedBlockLoader`
(generated `fp_quantized.cpp` ~517) and `mlx::steel::BlockLoader`
(`gemm.cpp:62`) expose a public mutable `dst`, so the buffer flip is
`loader.dst += / -= tile`.

## Results (M4 Pro, `ED_PAIRS=4 ED_CBS=9 ED_REPS=4`, n=8 slots/variant)

`gate_up` M=4096 K=2048 N=1024 · `down` M=4096 K=512 N=2048 · 256 experts,
group_size 16. Null control 0.0275 / 0.0248 ms.

| variant | gate_up ms | vs base | down ms | vs base | weighted |
|---|---|---|---|---|---|
| base | 5.0659 | — | 2.5610 | — | — |
| `nobar` (invalid) | 5.0163 | **+0.98 %** | 2.5472 | **+0.54 %** | **+0.83 %** |
| `db` | 5.2088 | −2.82 % | 2.6549 | −3.67 % | −3.11 % |
| `db2` | 5.0680 | −0.04 % | 2.5938 | −1.28 % | −0.46 % |
| `dbmem` | 5.1833 | −2.32 % | 2.6352 | −2.90 % | −2.51 % |
| `noload` | 4.2882 | +15.35 % | 2.1871 | +14.60 % | +15.10 % |

Weighting is by measured kernel time across 39 MoE layers (gate_up 197.6 ms
= 0.664, down 99.9 ms = 0.336). Raw logs in `logs/`.

`nomma` reported +96 % but its pipeline threadgroup memory is **0 B**, which
proves the compiler dead-code-eliminated the whole staging chain once nothing
consumed it. **It is an invalid probe and is excluded from every conclusion.**
I am reporting it rather than deleting it because the 0 B pipeline-state
readback is the mechanism that caught it, and that check is worth reusing.

## Causal decomposition

This is the part worth keeping.

1. **The footprint alone costs 2.51 %.** `dbmem` runs a bit-identical
   schedule to `base` and is 2.3–2.9 % slower purely because 3840 → 7680 B
   drops resident threadgroups per core from 8 to 4.
2. **The pipelining mechanism is real but cannot repay its own rent.**
   `db2 − dbmem` = **+2.06 pp**: against the same doubled footprint,
   overlapping the load with the mma genuinely wins. It just wins less than
   the footprint costs. Net **−0.46 %**.
3. **Runtime-parity addressing costs another 2.65 pp.** `db − db2`. Any
   implementation that cannot fully unroll the parity is far worse still.
4. **The entire exposed load chain is only 15 % of kernel time.** `noload`
   deletes device loads, NVFP4 dequant and threadgroup stores, keeping both
   barriers and the mma, and buys 15.10 %. So ~85 % is mma + barriers +
   control + store. **The kernel is mma-issue bound, not load-latency
   bound**, and double buffering optimises a resource that is not the
   constraint.

That is the whole result: latency is already hidden by inter-threadgroup
parallelism (3.84 KB of threadgroup memory, small register footprint, 8192
threadgroups on an 8-core-cluster part), so intra-threadgroup double
buffering can only add instructions and subtract occupancy. The −2.5 %
regression is the expected outcome, not a tuning failure.

## Roofline cross-check

Independent arithmetic agrees. For `gate_up`: 8.59 GMAC useful, ×1.96
segment-restart amplification (below) = 16.6 GMAC executed in 5.066 ms =
**3,274 GMAC/s ≈ 6.55 TFLOP/s**, which matches the independently measured
R109-D figure of 3,158 GMAC/s — i.e. the kernel is running at achieved mma
throughput. DRAM traffic is ≈583 MB per gate_up layer-set ≈ 115–130 GB/s
against a ~273 GB/s ceiling (~42 %), so it is not bandwidth bound either.

## Score reach

Even at the `nobar` ceiling — which is not a legal kernel — 0.83 % of the
gather-GEMM family × 48.5 % of prefill GPU time ≈ 0.40 % of prefill, × the
0.25 prefill exponent ≈ **0.10 % score**, at or below the ~0.11 % landing
bar. The mechanism that is actually implementable measures **negative**.
There is no version of this idea that lands.

## Two findings that change what should be funded next

### 1. The segment-restart tax is 48 % — and the ranked path already fixes it

I added an `ED_IDX=aligned` control: identical weight bytes, identical useful
MAC count, but exactly one expert per BM=16 row tile instead of the
multinomial routing that makes most tiles straddle an expert boundary.

| shape | multinomial | aligned | tax | K-loop ratio |
|---|---|---|---|---|
| gate_up | 5.1815 ms | 2.6630 ms | **48.60 %** | 1.961× |
| down | 2.5882 ms | 1.3467 ms | **47.97 %** | 1.961× |

Time scales at 1.945× against 1.961× more K-loop executions — near-perfectly
linear, which is an independent confirmation that the kernel is issue bound.
`noload` is 15.4 % / 16.1 % in *both* routings, so the load:mma balance is
invariant to routing; the ~15 % load share is a robust property of the
kernel, not an artefact of the index distribution.

**But this does not transfer.** `quantized.cpp:1669` routes to
`gather_qmm_rhs_nax` whenever `is_nax_available()`, so the ranked M5 never
dispatches the kernel I measured. And the kernel it does dispatch,
`fp_gather_qmm_rhs_expert_nax`, is **expert-major by construction**: it
iterates expert slots, binary-searches `[run_start, run_end)`, and chunks
that run by BM (`fp_quantized_nax.cpp:1900-1975`), so every K-loop covers
rows of exactly one expert. The 48 % I measured is already zero on the ranked
path.

I am reporting this as the correction it is. Before I ran the aligned
control, "48 % of mma work is wasted on out-of-segment rows" was my headline
follow-up recommendation. It would have been a wasted assignment. Reporting
it as a *negative transfer* result is the actual deliverable.

### 2. The `_nax` port (Part 2) should not be funded

Byte figures, since the assignment asked for them: `kWsElems = BN × BK_padded
= 64 × 72 = 4608` elems × 2 B = **9216 B**, +8 B bounds = **9224 B**.
Doubled = **18,440 B**, which does fit under 32,768 B. But fitting is the
wrong test:

- **Occupancy collapses harder than on M4.** 32768/9224 = **3** resident
  threadgroups; 32768/18440 = **1**. That is a 3× reduction, where the 2×
  reduction I measured on M4 already cost 2.5 %. (Threadgroup limit measured
  on M4; if M5 offers 64 KB the reduction is 6→3, still 2×, still at least as
  bad as the measured tax.)
- **The cheap half of the overlap is already shipped.** `_nax` hoists the A
  operand into registers before the WAR barrier
  (`kernels/fp_quantized_nax.h:1875-1888`); only Ws staging sits between the
  two barriers, so there is less left to win than in the kernel I measured.
- **`gate_up_stage` aliases `Ws_storage`** (`h:1738-1739`, written
  `:1985-1988`, consumed `:1990-2011`), so any doubling must also
  de-alias the swiglu epilogue — more code, more footprint.
- Larger tiles (BM=BN=64, BK=64) mean *higher* arithmetic intensity than the
  kernel I measured, so `_nax` is if anything **more** mma-bound and **less**
  load-bound. The sign of my result transfers; the magnitude gets worse.

Recommendation: do not spend M5 receipts on the `_nax` double-buffer port, and
do not produce the Part-2 handoff to maple-fern. I have not written a
`READY.md` for it. If the advisor wants it anyway, the port is understood and
the byte budget is above.

## What I would not recommend chasing

- **Raising BM above 16** on the non-`_nax` kernel. My own first instinct;
  a frontier review of the dispatch geometry puts it at 2.93× executed work
  at BM=32 — strictly worse. Recorded so nobody re-derives it.
- **Predicated store instead of K-loop restart.** Not reachable bit-exact.
- **BK=64 / register-A on the non-`_nax` path.** ≤5 % cleanups on a kernel
  the ranked M5 does not run.

## One thing genuinely worth a look (unmeasured, flagged not recommended)

At the shipped variant-5 geometry (`bm=64, wm=4, wn=1`, `quantized.cpp:1385`)
`SM = BM/WM = 16`, while prefill routing gives ≈16 rows per expert on average
(512 tokens × 8 experts / 256 experts). Since `sgp_sm = min(SM, max(0,
chunk_rows - tm))` gates simdgroups, a typical 16-row expert run leaves 3 of
4 simdgroups inactive for that chunk. I could not measure this — the kernel is
unreachable on gen-16 hardware — and the `DARKBLOOM_*` macros show this kernel
has already been worked over hard, so this may well be known and already
priced. I am flagging it with source pointers rather than proposing it as an
assignment.

## Reproduction

```bash
ED_TAGS=base,nobar,db,db2,dbmem,noload ED_PAIRS=4 ED_CBS=9 ED_REPS=4 \
  research/edward_r110_run_bench.sh          # variant table
ED_IDX=both ED_TAGS=base,noload \
  research/edward_r110_run_bench.sh          # segment-restart tax
```

Requires Metal; no model weights, no network, no benchmark lock. Runs in
~10 s. Research-only — neither file is on `editablePaths`.

## Honest limitations

- Everything here is M4 Pro, gen-16, on a kernel family the ranked M5 does
  not dispatch. The mechanism conclusion (staging footprint costs more than
  pipelining returns, in an mma-bound kernel) is what transfers; no absolute
  number does.
- `nobar` is not a legal kernel; it exists only to bound the prize.
- `nomma` is invalid (dead-code eliminated) and excluded.
- No M5 receipt was spent, by design: the stop fired at Stage 0.
