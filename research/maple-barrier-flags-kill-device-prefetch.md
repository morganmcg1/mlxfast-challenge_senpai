# Manual device-read prefetching cannot pay in these k-loops: the barriers never fenced device memory

**Status: measured negative with a leading mechanism explanation.** The
implementation was bit-exact and passed every hidden gate on the ranked host; it
made prefill **0.651% slower**. This file records why, because the reason retires
a family of arms rather than just the one that was assigned.

Receipt `7a5a1e08-aebb-4123-aed6-ce83ee3936bc` (M5 Max, ranked host, commit
`183f8f0`):

```
S  98.347 ms   vs 3-receipt byte-identical control 97.711 +- 0.254   +0.651%  (+2.501 sigma)
T  4.3612 ms   vs control 4.3718 +- 0.0104                          -0.242%  (-1.014 sigma)
ns 2.51083     vs control 2.51286                                   -0.081%
max_abs_diff 0   checked_steps 1344   GPQA 9/9   peak_ram_gb 21   error ''
```

## What was built

The routed-expert NVFP4 gather-GEMM stages weights through threadgroup memory
once per k-tile. The arm split that fused `load -> decode -> store` into a
register **prefetch** (device loads for tile `k+1`) and a **commit** (decode +
threadgroup store for tile `k`), issuing the prefetch *after* the RAW barrier so
the device read for the next tile would be in flight across the current tile's
MMA. Zero extra threadgroup memory, so no occupancy trade.

The intent was to convert `cmp + dram` into `max(cmp, dram)` on the one
DRAM-bound block of the prefill forward, worth a modelled 16.75-22.69 ms.

## Why it cannot work

Every barrier in the routed-expert k-loop -- all 21 in `fp_quantized_nax.h` --
is `threadgroup_barrier(mem_flags::mem_threadgroup)`. **Not one is
`mem_device`.** The shipped stage sits between two of them (`:1851`, `:1872`):

```
threadgroup_barrier(mem_flags::mem_threadgroup);      // WAR: last MMA done with Ws
loader_w.load_unsafe_wide<wide_store, wide_load>();   // <-- device load + decode + tg store
threadgroup_barrier(mem_flags::mem_threadgroup);      // RAW: publish Ws
    ... MMA over Ws ...
loader_w.next();
```

`mem_flags::mem_threadgroup` fences **threadgroup** memory only. It places no
ordering constraint on device-address-space loads. So the device read inside
`load_unsafe_wide` was already free to be hoisted *above the WAR barrier*, into
the previous iteration's MMA region -- one iteration earlier than the manual
version even placed it.

The transformation was already legal for the compiler to perform, and the
measurement says it was performing it.

## Why the measurement supports this rather than merely being consistent with it

The discriminating evidence is the **magnitude**, not the sign:

- If the overlap had been genuinely absent, the arm implemented it correctly and
  bit-exactly, and the modelled prize was 16.75-22.69 ms on a 98.153 ms prefill:
  a **17-23% win**. Measured: **-0.65%**.
- If instead register pressure had collapsed occupancy, the cost would be a large
  fraction of the block, not 0.65%.

A 0.651% change is the signature of "a little extra bookkeeping in a loop whose
structure did not otherwise move". Neither alternative produces that. What the
split actually added was:

1. a named `StageRegs` (`kSrcBytes = 16` + `sc[2]` + `bool staged`, ~19 B/lane,
   ~5 registers) whose **live range now spans the RAW barrier and the whole MMA
   region**, where the MMA accumulators are already live. The byte count is
   unchanged from the fused version; the *live range* is not.
2. a `staged` flag and a `k + 1 < K_it` guard branch per iteration.

Both **constrain** the scheduler rather than freeing it.

## The general rule

> Manual software pipelining of device reads across a Metal barrier is a no-op at
> best whenever that barrier is `mem_flags::mem_threadgroup`-only, because the
> barrier never fenced the thing being prefetched. It can only pay where the
> barrier actually orders the prefetched access -- `mem_device`, or a value
> consumed *through* threadgroup memory that the barrier does order.

**Screening test, cost ~1 second:** `grep -n 'threadgroup_barrier' <kernel>` on
any k-loop proposed for pipelining. If the flags are `mem_threadgroup` only, the
device-read overlap is already legal for the compiler and the arm is dead before
a line is written.

## What this retires

- Expert-GEMM weight-stage double buffering in threadgroup memory.
- Prefetch depth (`tiles_ahead` 1 -> 2): same mechanism, deeper, so it inherits
  the same fatal premise at ~9 more registers. Strictly worse than the measured
  result.
- The framing that the 98.153 ms prefill's gap to its ~28.17 ms DRAM floor is
  recoverable *by overlap*. The floor still stands -- 14.09 GB must cross the bus
  -- but the gap has to be closed by **removing work**, not by rescheduling it.

## Relation to the field-wide null

See `research/maple-field-axis-asymmetry.md`: across 926 public receipts that
cleared every gate and were timed, **zero beat our prefill by 2 sigma** while 74
beat our decode by 2 sigma and the best cleared 6 sigma. If overlap on the prefill
path is already harvested by the compiler, then the most obvious class of prefill
optimisation returns nothing -- which is one coherent reason that axis has not
moved for anybody.

## How to falsify this cheaply

`metal-objdump` exists locally but disassembles pre-register-allocation AIR, so it
cannot report physical register counts; the real number comes from the driver at
pipeline creation. Two routes, in order of cost:

1. Read `MTLComputePipelineState.maxTotalThreadsPerThreadgroup` for the stock and
   stage-2 pipelines. 1024 in both means register pressure is not the story and
   lost scheduling freedom is the whole explanation.
2. In a **throwaway local build**, change one bracketing barrier to
   `mem_flags::mem_threadgroup | mem_flags::mem_device` and re-measure the
   **stock** path. If the hoisting story is right, adding the device fence should
   slow stock prefill by roughly what this arm lost. **Diagnostic only -- never
   submit it**, since it can only remove performance.

## Confidence

The barrier flags are certain. The Metal semantics of
`mem_flags::mem_threadgroup` are, to my understanding, certain but were not
verified against a disassembly. The step from "the compiler *may* hoist" to "the
compiler *did* hoist" is inference from the magnitude of the regression, and it is
the part a reader should push on. Both falsification routes above are cheap.
