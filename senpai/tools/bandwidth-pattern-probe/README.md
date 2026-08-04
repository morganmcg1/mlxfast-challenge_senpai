# Bandwidth probe parameterised by access pattern

Achieved DRAM read bandwidth as a function of **access pattern** and of **bytes
per dispatch**, on the host it runs on. It is not part of the submitted surface
and nothing here runs on the scored path.

The point is to replace the single global ceiling in the decode roofline with a
per-stream achievable ceiling. A clean streaming probe reports ~262 GB/s on this
M4 Pro (96% of the 273 GB/s pin), but the decode step never streams: it reads
NVFP4 codes 8 B per lane from one buffer with their fp8 scales 1 B per lane from
a second, gathers 8 scattered expert blocks out of 256, walks a ring KV buffer,
and does all of it in a few hundred small serialized dispatches. Pricing all of
that at 262 GB/s books every one of those deviations as "unexplained residual".

## Build and run

```bash
xcrun swiftc -O main.swift -o probe -framework Metal -framework Foundation
./probe                      # the per-pattern report
./probe --mode sizes         # bandwidth vs bytes per dispatch
./probe --mode runs          # bandwidth vs contiguous run length, random order
./probe --mode downshape     # the routed-down dispatch shape, one knob at a time
./probe --mode downsize      # that shape swept at its real 5.06 MB byte count
./probe --mode empty         # serialized empty-dispatch floor
./probe --mode tune          # threads x groups per core for the control
```

Flags: `--tg-size`, `--tg-per-core`, `--cores`, `--repeats`, `--pool-mb`,
`--sizes`, `--runs`.

## What makes the numbers trustworthy

- Every timed dispatch reads a region no earlier dispatch in the same command
  buffer read, from pools far larger than any cache, so nothing is served out of
  the SLC.
- Both pools get a first-touch pass **and** a 0.5 s sustained load before
  anything is timed. Without the sustained part the first timed configuration
  reads 35% low and the whole table is silently ordered by warm-up. This was a
  real error in the first run of this probe: the shipped routed-down shape read
  145.7 GB/s cold and 222.5 GB/s warm.
- Loads are consumed by XOR into registers and stored only on a value that
  cannot occur, so nothing is dead-code eliminated and the write stream is ~0 B.
- Time is the GPU timestamp span of one command buffer holding N serialized
  dispatches, so per-dispatch ramp-up and drain are charged the way MLX charges
  them.
- `min` over repeats. Only within-process comparisons are meaningful.

## The `qmv` kernel is the real inner loop

`qmvSource` is the shipped NVFP4 group-16 weight read with the arithmetic
removed: a simdgroup owns `rowsPerSimd` output rows, and per k-block a lane
reads 8 B of codes and 1 B of scale per row, so 32 lanes cover 256 contiguous
bytes of each code row and 32 contiguous bytes of each scale row. That is the
inner loop of `laguna_decode_nvfp4_*`, `laguna_routed_nvfp4_*` and MLX
`fp_qmv_fast_impl` alike (`Sources/MLXFastModel/LagunaRuntimeModel.swift:4547`,
`:7405`, `Vendor/.../kernels/fp_quantized.h:101`).

`rowsPerSimd` matters because it sets **device-load bytes in flight per lane**,
which is `kBlocks * rowsPerSimd * 8 B`. A 2048-value row is 4 k-blocks, so it
has 32 B in flight at one row per simdgroup; a 512-value row (the routed down
projection) is a single k-block, so it only reaches 32 B by taking 4 rows.

## Results on this M4 Pro, 2026-08-04

Sequential control 262.5 GB/s at 64 MB/dispatch. Every real pattern, measured
at equal bytes per dispatch and the shipped in-flight depth:

| pattern | GB/s | of control |
| --- | ---: | ---: |
| NVFP4 attention rows, 2048 B, split scales | 236.6 | 90% |
| NVFP4 routed gate/up rows, 1024 B, split scales | 243.0 | 93% |
| NVFP4 routed down rows, 256 B, 4 rows/simd | 241.4 | 92% |
| 8 scattered 1.77 MB expert blocks | 246.8 | 94% |
| 576 scattered 16 KB blocks | 242.4 | 92% |
| 256 B KV runs, any stride, at 8 MB/dispatch | 227.8–234.2 | 87–89% |

So **no access pattern in the decode step costs meaningful bandwidth.** Fusing
the scale plane into the code rows is worth −0.3% to +2.5%, i.e. nothing, which
confirms from measurement what fern established from the addressing.

The two things that do cost bandwidth are bytes per dispatch and in-flight
depth:

| MB/dispatch | 0.125 | 0.5 | 1 | 2 | 8 | 16 | 64 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| GB/s | 28 | 113 | 173 | 212 | 235 | 250 | 262 |

| in-flight B/lane | 8 | 16 | 32 | 64 | 128 |
| --- | ---: | ---: | ---: | ---: | ---: |
| GB/s at 5.06 MB | 92–103 | 171–190 | 225 | 217–225 | 207–211 |

Serialized empty dispatch: 2.46 us at a 160x256 grid, 0.87 us at 1x32.

`research/tanjiro-pr21-roofline.py` crosses these curves with the measured
per-dispatch profile to rebuild the roofline.
