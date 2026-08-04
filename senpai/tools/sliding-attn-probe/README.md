# Sliding fused decode attention probe

A standalone Metal harness that times and bit-diffs variants of the scored
sliding fused decode attention kernel in about two seconds, instead of the eight
minutes a `./benchmark.sh --local-iterate` pair costs.

It is not part of the submitted surface. Nothing here runs on the scored path.

## Why trust it

Calibrated end to end on an M4 Pro against `BASE_SHA`
`768bb9d4adfc2baac7d74c0008afc92d010329da`. Heads-per-threadgroup 8 was measured
in isolation at +95.42 us per sliding layer versus the shipped width 2. Over the
30 sliding layers that predicts +2.863 ms/token; the harness measured decode
going from 0.0146222 to 0.0174630 s/token, i.e. **+2.841 ms, so the probe's
differential was 0.77% high**.

The same calibration fixes the denominator every attention arm needs: the 30
sliding-attention dispatches are 30 x 30.03 us = 0.901 ms of a 14.622 ms decode
token, so **sliding decode attention is 6.16% of decode on that host**. A kernel
that cost literally nothing would be decode_speedup 1.066, i.e. score 1.049 --
the whole mechanism family barely spans the acceptance band.

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

Write `probe_mine.metal` by hand or generate it, keeping the `[[kernel]] void
probe(...)` signature `render.py` emits, since `main.swift` binds those buffers
by index.
