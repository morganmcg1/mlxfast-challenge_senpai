# Sliding fused decode attention probe

A standalone Metal harness that times and bit-diffs variants of the scored
sliding fused decode attention kernel in about two seconds, instead of the eight
minutes a `./benchmark.sh --local-iterate` pair costs.

It is not part of the submitted surface. Nothing here runs on the scored path.

## Why trust it, and for what

Calibrated end to end on an M4 Pro against `BASE_SHA`
`768bb9d4adfc2baac7d74c0008afc92d010329da`. Heads-per-threadgroup 8 was measured
in isolation at +95.42 us per sliding layer versus the shipped width 2. Over the
30 sliding layers that predicts +2.863 ms/token; the harness measured decode
going from 0.0146222 to 0.0174630 s/token, i.e. **+2.841 ms, so the probe's
differential was 0.77% high**.

**Trust the differential, not the absolute.** The two numbers have different
error structure, and only the differential was ever calibrated.

### Instrument reconciliation (PR #37, M4 Pro)

This probe's headline 30.03 us/layer and the in-situ SPLIT dispatch profiler's
22.34 us/layer for `sliding_fused_attn_ring_v1` disagreed by 34%. Running both
command-buffer layouts and both clocks on the same kernel, in the same process,
resolves it entirely as instrument, not kernel:

| layout | clock | us/layer | cross-process spread |
|---|---|---:|---:|
| batched, 30 dispatches per buffer | host wall | 26.37 - 28.21 | 7% |
| batched, 30 dispatches per buffer | GPU device | 21.96 - 23.99 | 9% |
| split, 1 dispatch per buffer | GPU device | **22.66 - 22.78** | **0.5%** |

Split GPU-clock lands at 22.73 us mean against the profiler's 22.34 (which is
its split `us/call` minus 1.33 us/command-buffer). That is 1.7% apart, below
this probe's ~2% resolution floor, so **the two harnesses agree and 22.34 is the
right kernel cost**. The 34% was:

- **+4.1 us/dispatch** of host encode/commit/wait that `DispatchTime` counts and
  `gpuStartTime`/`gpuEndTime` do not (+18%);
- **+1.2 us/dispatch** of window granularity, because one buffer spanning 30
  dispatches has its `gpuStart -> gpuEnd` span include the inter-dispatch gaps
  that a one-dispatch buffer excludes (+5%);
- the rest, cross-process variance of the host clock.

The host tax is a *constant additive* term: measured at 4.11 us/dispatch for the
shipped 32-threadgroup config and 4.13 us/dispatch for the same kernel at 8
threadgroups, whose GPU time differs by 1.5x. That is why the differential
survives (0.77% end-to-end) while the absolute does not, and it is the reason to
keep using this probe for A/B work.

### Corrected denominator

The 30 sliding-attention dispatches are 30 x 22.73 us = **0.682 ms of a 14.622
ms decode token, so sliding decode attention is 4.66% of decode** on that host,
not the 6.16% previously stated here. A kernel that cost literally nothing would
be decode_speedup 1.0489, i.e. **score 1.0365**. Every published headroom figure
derived from the old 30.03 us is about 1.2 score points too generous.

## Fidelity

- Same geometry as the runtime: 8 KV heads, 512-slot ring, 30 layer buffers,
  1024-thread threadgroups, `head_dim` 128, bf16 cache.
- `fastMathEnabled = false`, matching MLX's `Device::build_library_`
  (`Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/device.cpp`).
- Every variant's output is compared bytewise against the first variant, so a
  claimed bit-exact restructure is verified before its timing is believed.
- Timing is round-robin: 9 blocks x 20 steps x 30 dispatches, warmed up, min and
  median reported. Round-robin matters -- the same variant varies ~10% between
  separate processes, so only within-process ordering is comparable, and effects
  under about 2% are not resolvable.
- Every variant is timed under all four cells of the reconciliation table above.
  Read the **split GPU** column when you need a per-layer cost to compare with
  the dispatch profiler or to price against a bandwidth ceiling; read the
  batched columns when you want an A/B difference.

## Use

```bash
cd senpai/tools/sliding-attn-probe
python3 render.py 768bb9d4 lagunaSlidingFusedAttentionKernel probe_orig.metal
xcrun swiftc -O main.swift -o probe -framework Metal -framework Foundation
./probe shipped:probe_orig.metal:2 mine:probe_mine.metal:4
```

Each argument is `label:file.metal:headsPerThreadgroup`; the first is the
reference for the bitwise diff, so pass the unmodified kernel first. The heads
field sets the dispatched threadgroup count (`64 / heads`).

It sets *only* that. It is not a kernel parameter, so passing a different heads
value with the same `.metal` file under-dispatches that kernel rather than
retiming it at a new width -- and the bitwise diff will still report 0, because
the heads the shorter grid never touches keep the reference's bytes. A width
comparison needs a `.metal` file actually written at that width.

Write `probe_mine.metal` by hand or generate it, keeping the `[[kernel]] void
probe(...)` signature `render.py` emits, since `main.swift` binds those buffers
by index.
