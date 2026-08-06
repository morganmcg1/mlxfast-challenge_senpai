# PR #157 — pre-registration, committed before any probe output was observed

Assignment `maple-2026-08-06n-graph-coresidency-falsifier`, revision `r1`,
student `maple-tanjiro`. `BASE_SHA = 9dd2eec38a11d0e0bc7bcdbc5aec46e3436f284f`.

**Zero submitted bytes so far.** Everything in Step 0 lives in `research/`.

This document and `research/tanjiro_coresidency_probe.swift` are committed in
the same commit, before the probe has ever been executed. The audit trail is
the commit, not this sentence.

---

## 1. Host

| fact | value | source |
| --- | --- | --- |
| chip | Apple M4 Pro | `sysctl machdep.cpu.brand_string` |
| unified memory | 48 GiB (`hw.memsize = 51539607552`) | `sysctl` |
| macOS | 26.5.2 (25F84) | `sw_vers` |
| GPU cores | 20 (to be reconfirmed by the probe) | prior PR #57 host record |
| Apple GPU family | generation 16, `applegpu_g16s` | `device.cpp:913-931` gate |

---

## 2. The finding that already exists, from code reading alone

Assignment §1.1 requires: *"Establish explicitly whether `union` is computed
from per-dispatch GPU timestamps or from per-command-buffer start/end — read
the code path, do not infer it."*

**It is per command buffer.** Chain:

1. `research/decode_probe.py:147-192` (`analyze_profile`) and
   `research/prefill_probe.py:148-165` (`analyze`) both compute
   `gpu_busy_sum` as the plain sum of interval durations and `gpu_busy_union`
   as a sweep-merge of those same intervals.
2. The intervals they consume are `GPUPROF <gpu_start_s> <gpu_end_s> ...`
   lines, one **per command buffer**, emitted from the command-buffer
   completion handler by `research/pr91-gpuprof-hook.patch`, which patches
   `CommandEncoder::commit()` in
   `Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/device.cpp` to record
   `cbuf->GPUStartTime()` and `cbuf->GPUEndTime()`.
3. There is no counter-sample-buffer, `xctrace`, Instruments, or
   `MTLCaptureManager` path anywhere in `research/`, `Sources/`, or
   `Vendor/.../backend/metal`. Per-dispatch attribution is obtained only
   indirectly, by `DARKBLOOM_GPU_PROFILE_SPLIT` forcing **one dispatch per
   command buffer** in `needs_commit()`.

Two consequences follow immediately and are stated here *before* any timing:

- **The instrument is structurally incapable of observing intra-command-buffer
  concurrency.** MLX's only concurrency mechanism is
  `MTL::DispatchTypeConcurrent` *within one encoder inside one command buffer*
  (`device.cpp:548`). A metric built from command-buffer start/end timestamps
  cannot resolve anything below the command buffer. Whatever two hazard-free
  dispatches inside one CB do, `sum` and `union` are identical by construction
  for that CB.
- **The PR #73 run A datum is worse than blind: it is self-refuting.** It ran
  with `SPLIT=1`, i.e. exactly one dispatch per command buffer
  (`cbs=406 dispatches=406`). Under `SPLIT=1` there is no intra-CB pair left to
  overlap, so `union == sum` is guaranteed by the experimental setup and
  carries zero bits about concurrency.

So `gpu_busy_sum == gpu_busy_union` to 6 ns measures one real thing —
**command buffers on a single `MTLCommandQueue` do not overlap each other** —
and says nothing whatsoever about the mechanism the shadow model actually
claims. That is a fact about Metal queue semantics, not about MLX.

The probe below exists to *demonstrate* this empirically rather than assert it
from source, and to answer the question the blind instrument could never
reach.

---

## 3. What the probe measures, and why wall clock is the primary instrument

Because the incumbent instrument is suspected blind, the probe must not rely on
it for the verdict. The primary instrument is **CPU wall clock across
`commit()` + `waitUntilCompleted()`**, which cannot be blind to overlap: if two
kernels each take 20 ms in isolation and the pair completes in 21 ms, they
overlapped, and no timestamp plumbing is required to know it.

The incumbent CB-union instrument is computed *alongside* wall, on the very
same command buffers, so that the two can be compared directly. That
side-by-side is the instrument-validation deliverable.

`overlap = 1 - wall_AB / (wall_A + wall_B)`. 0 = perfectly serial, 0.5 = perfect
two-way overlap of equal-cost kernels.

### 3.1 Arms

All arms encode the same two dispatches with identical grids and identical
buffer bindings except where noted, replicating MLX's encoder semantics from
`device.cpp` (concurrent encoder at `:548`; `memoryBarrier(BarrierScopeBuffers)`
inserted only on a real hazard at `:325-330`, `:363-375`).

| arm | encoder | barrier | dependency | expectation |
| --- | --- | --- | --- | --- |
| `A_only` / `B_only` | concurrent | – | – | isolation baselines |
| `concurrent_1cb` | concurrent | none | none | the question |
| `barrier_1cb` | concurrent | yes | none | prices the barrier alone |
| `raw_1cb` | concurrent | yes | B reads A's output | **negative control**, must be serial |
| `serialenc_1cb` | **serial** | – | none | second serialisation mechanism |
| `two_cb` | 2 command buffers | – | none | what the incumbent instrument *can* see |

### 3.2 Kernel pairs

| pair | A | B | why |
| --- | --- | --- | --- |
| `alu/alu` | compute-bound ALU burn | same | cleanest positive control |
| `mem/mem` | bandwidth-bound stream | same | two kernels contending for the same resource |
| `alu/mem` | compute-bound | bandwidth-bound | **the wavefront's actual premise**: hiding a bandwidth-bound MoE behind a compute-bound attention |
| `gemm/gemm` | bf16 GEMM | bf16 GEMM | assignment §1.2 realism check |

The `alu/mem` pair is an addition to the assignment. §3's two-chunk wavefront
does not need "two kernels overlap"; it needs *a bandwidth-bound kernel and a
compute-bound kernel* to overlap. Those are different claims and the second is
the one that has to be true.

### 3.3 Occupancy sweep (assignment §1.3)

Threadgroup counts per kernel: **2, 5, 10, 20, 40, 240, 1000**, at 256
threads/TG. On a 20-core M4 Pro, 20 TGs is one TG per core and (at the
96-simdgroup/core ceiling, scoped per PR #138 to `>=128` threads/TG) 240 TGs is
nominal full occupancy. Anything at or below 10 leaves the majority of the
device idle; 1000 oversubscribes it.

Duration is auto-calibrated per size to ≈20 ms per kernel so that fixed
per-command-buffer overhead (≈0.1 ms) is <1% of every measurement.

### 3.4 Statistics

Every (arm, size, pair) cell is sampled once per round, in an order reshuffled
each round, preceded by a sustained ALU burn to pin GPU clocks (without it,
sub-millisecond DVFS transitions corrupt short measurements — established in
PR #47 D1). Point estimate = median over rounds; interval = 95% percentile
bootstrap over rounds. Rounds default 7.

---

## 4. Pre-registered decision rule

Assignment §2's table, plus the thresholds I will apply to my own additions.
These are fixed now.

| observed | verdict |
| --- | --- |
| positive control (`alu/alu`, 2 TGs, `concurrent_1cb`) has wall-overlap `< 0.05` | **No concurrency on this stack at all.** Attack B and the entire graph-overlap family close permanently. Reading (b) of §4.1 is correct. |
| positive control overlap `>= 0.15`, and CB-union on that same arm reports `union == sum` | **The incumbent instrument is blind.** Every zero-overlap datum in the programme is retracted. Reading (a). |
| `raw_1cb` shows overlap `>= 0.05` | Probe is fabricating concurrency. Discard the run, do not report a verdict. |
| real case (`gemm/gemm`) overlap `< 0.05` at all sizes | Graph-level overlap dead for realistic kernels; close Attack B. |
| real case overlap `>= 0.15` at any size | **GO** to §3 wavefront, subject to the §5 tax gate. |
| overlap present only at low TG counts | Report the boundary; it reconciles (a) with (b). Wavefront GO **only** if the boundary admits prefill-sized grids. |

`alu/mem` specific: if `alu/alu` overlaps but `alu/mem` does not, the wavefront
is dead regardless of the headline number, because its entire mechanism is
mixed-resource hiding. I will report this as a separate, dispositive line.

## 5. The tax gate, also fixed now

Even on GO, the wavefront is only implemented if

```
predicted extra routed-expert bytes at 2 x 256 tokens vs 1 x 512 tokens
  priced at the routed-plane marginal rate 700.3 GB/s
      <  measured overlap headroom from Step 0
```

computed from the merged artifact `research/artifacts/route-histogram-prefill512.csv`.
If the tax exceeds the headroom, I stop and report the arithmetic instead of
writing code. No submitted byte is spent on a mechanism whose own tax estimate
eats it.

## 6. Legality note for §3, recorded in advance

`TASK.md`'s serial non-speculative rule permits multi-row kernels *"only when
every row corresponds to a token supplied in that invocation"*. Both 256-token
chunks are tokens of the same 512-token prefill invocation; total logical and
physical KV advance is exactly 512; no logits or KV rows are produced for any
unsupplied token; no state is deferred across invocations. Chunked evaluation
of supplied tokens is therefore legal, and is not speculation.

## 7. What is *not* claimed

Nothing here is an M5 claim. Concurrency is a scheduler property and M4 Pro
executes bf16 GEMMs natively, so the mechanism question transfers; the
*magnitude* of any wavefront win does not, and would need official receipts.
