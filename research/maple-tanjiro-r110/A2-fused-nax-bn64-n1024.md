# Arm A2 — fused-NAX `bn` 128 -> 64 for prefill `N <= 1024`

Status: **ready to fire**, delivered as a patch (`A2-fused-nax-bn64-n1024.patch`).
Owner surface: `Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/matmul.cpp` (tanjiro).
Single knob. Does not touch `quantized.cpp`, so it is independent of arm A1.

## Diff

One helper plus one guarded assignment inside
`steel_matmul_regular_axpby_nax` (declaration at `matmul.cpp:185-186`, tile
block at `matmul.cpp:213-222` in the base).

```cpp
static bool darkbloom_fused_nax_narrow_bn() {
  static bool enabled = []() {
    const char* value = getenv("DARKBLOOM_FUSED_NAX_NARROW_BN");
    return value == nullptr || atoi(value) != 0;
  }();
  return enabled;
}
```

```cpp
  char devc = d.get_architecture().back();
  if (devc == 's' || devc == 'c' || devc == 'd') {
    bk = (K >= 8192 && K > (M + N)) ? 64 : 256;

    bm = 64;
    wm = 2;
    // SN = bn / wn must stay a positive multiple of 16, so 64 with wn = 4 is
    // the narrowest legal column tile here. Decode reaches this same path, so
    // M >= 64 keeps the change confined to prefill.
    if (darkbloom_fused_nax_narrow_bn() && M >= 64 && N <= 1024) {
      bn = 64;
    }
  }
```

The env var is the **control switch only**. `DARKBLOOM_FUSED_NAX_NARROW_BN=0`
restores the base tile byte-for-byte; unset or non-zero selects the arm. The
shipped default is the arm, so the official channel measures the arm without
any override — the local-only override exists purely so a follow-up can prove
the diversion is the cause.

`darkbloom_fused_nax_narrow_bn()` is modelled on the existing
`darkbloom_steel_prefill_tile()` helper at `matmul.cpp:82-88`, which is applied
on the split-k path at `matmul.cpp:674-677`. Same idiom, same file, same style.

## Why `M >= 64` is load-bearing

This is the correction that matters most for attribution. The fused-NAX
*regular* path is **not** prefill-only. At decode the wk/wv projection is
`M=8, N=1024, K=2048`, and the split-k diversion at `matmul.cpp:922-925` does
**not** fire for it:

```cpp
if (use_nax && batch_size_out == 1 &&
    (K >= 3 * std::max(M, N) ||
     (std::max(M, N) <= 1024 && K > 2 * std::max(M, N)))) {
```

With `max(M, N) = 1024`:

- `K >= 3 * max(M, N)` -> `2048 >= 3072` is false;
- `max(M, N) <= 1024` is true, but `K > 2 * max(M, N)` -> `2048 > 2048` is
  false.

(The prefill shape `M=512, N=1024, K=2048` has the same `max(M, N) = 1024` and
so evaluates identically — both regimes land on the regular path.)

So decode wk/wv lands on the same `steel_matmul_regular_axpby_nax` entry as
prefill wk/wv. An unguarded `N <= 1024` condition would therefore have
retiled a decode GEMM as well, and decode carries **75 %** of the score. That
would have made a prefill arm silently a decode arm and destroyed causal
attribution on a paired M5 receipt.

`M >= 64` mirrors the existing `M >= 64` guard used by the A1 gate at
`quantized.cpp:1393-1397` and cleanly separates the two regimes: prefill is
`M=512`, decode is `M=8`.

The decode-side variant (`M < 64 && N <= 1024`, which would take that shape
from 32 to 64 threadgroups) is a **separate, plausible arm** and is listed in
"Suggested follow-ups". It is deliberately **not** implemented here.

## Mechanism

`bn` is a pure launch-geometry parameter on this path:

- `align_N` (`matmul.cpp:241`, function constant 201);
- `tn = (N + bn - 1) / bn` (`matmul.cpp:280`);
- swizzle_log = 2 -> `tm = (tm + 3) / 4; tn = tn * 4` (`matmul.cpp:303-305`);
- `group_dims = (32, wn, wm)`, `grid_dims = (tn, tm, batch)`
  (`matmul.cpp:307-308`, dispatched at `matmul.cpp:342`).

There is no accept-gate, no correctness predicate, and no numerical constant
keyed on `bn` anywhere on this path.

### Legality

`SN = BN / WN` must be a positive multiple of 16
(`steel_gemm_fused_nax.h:151-155`, `gemm_nax.h:35-37`). With `bn = 64` and
`wn = 4`, `SN = 16` — legal, and 64 is the **narrowest legal** column tile for
`wn = 4`. Then `TN = SN / 16 = 1` and `TM = (bm / wm) / 16 = 32 / 16 = 2`, which
selects the `TN == 1 && TM % 2 == 0` branch of `tile_matmad_nax`
(`nax.h:972`ff) — an already-exercised branch, not a new code path.

The NAX `gemm_loop` (`gemm_nax.h:20-90`) reads A and B straight from device
memory with no threadgroup staging, so there is no shared-memory budget to
violate when `BN` changes. The cost of halving `BN` is that each A tile is
re-read twice as often; the benefit is 2x the threadgroup count.

### Bit-exactness

Accumulation order along `K` is unchanged (`bk` is untouched). Splitting the
`N` axis into more tiles partitions **disjoint output columns** — no output
element is summed across tiles, so no reduction order changes. This is a pure
partition of the output, hence bit-exact.

### JIT

The AOT `.metal` instantiation list (`steel_gemm_fused_nax.metal:23-29`) does
not include a `bn64_wn4` tile, but `jit_kernels.cpp:977-1008` JIT-compiles any
requested tile, and `Package.swift:284` excludes `nojit_kernels.cpp`, so JIT is
live. Cost is a one-time runtime compile of one extra kernel. No metallib
rebuild is required (`tools/build-mlx-metallib.sh` is **not** needed).

## Target dispatches and threadgroup accounting

From the tier-1 (derived-M5Max) steel census
`research/artifacts/tanjiro-r104c/steel_census_237.json` (base_sha
`9527bb72...`, 237 dispatches per prefill, 1502.8 GFLOP total):

| dispatches | shape | tile | TGs | TG/core | share of prefill dense GEMM |
|---|---|---|---|---|---|
| **78** | **regular M=512 N=1024 K=2048** | bm64 bn128 wm2 wn4 | **64** | **1.6** | **11.1 %** |
| 31 | regular N=8192 K=2048 | bm64 bn128 | 512 | 12.8 | 35.4 % |
| 10 | regular N=6144 K=2048 | bm64 bn128 | 384 | 9.6 | 8.6 % |
| 1 | regular N=2048 K=2048 (layer-39 [K;V] bank) | bm64 bn128 | 128 | 3.2 | — |

The 78 dispatches are the attention **wk / wv** (K and V) projections across
all 40 layers, and they are the **only** `N <= 1024` shapes on the regular
fused-NAX path — so the guard selects exactly this family and nothing else.

At 1.6 TG/core these are **6-8x less filled** than their sibling regular-path
shapes (9.6-12.8 TG/core) on the very same kernel. With `bn = 64`:
`tn` 8 -> 16, `tm = 2` after swizzle, giving **128 TGs = 3.2 TG/core** — a 2x
occupancy improvement on 11.1 % of prefill dense-GEMM FLOPs.

## Predicted direction and discriminator

Predicted: prefill wall-clock **down**. The shape is launch-bound, not
bandwidth-bound; doubling resident threadgroups on a 1.6 TG/core dispatch
should recover a meaningful fraction of the tail on those 78 dispatches.

Risk: doubling A re-reads could offset the occupancy win if the shape is closer
to bandwidth-bound than the TG/core figure suggests. That is exactly what the
paired M5 receipt resolves.

Discriminator on the M5 receipt:
- **Win** — `prefill_seconds_per_token` drops below
  `1.87812e-4 - 3 * 2.607e-7 = 1.87030e-4` s/token.
- **Null** — inside `1.87812e-4 ± 3 * 2.607e-7`; the shape was not launch-bound
  and A re-read cost cancelled the occupancy gain.
- **Loss** — above the band; A re-read traffic dominates, and the decode-side
  follow-up should not be fired either.

Given prefill elasticity 0.362 and S ≈ 97.9 ms, 1 ms of S is 0.37 % of score.
Removing >= 0.3 ms of S is worth landing under the withdrawn 0.378 % bar.
`decode_seconds_per_token` must be **unchanged** — the `M >= 64` guard makes
any decode movement a red flag, not a result.

## Local gates

See `GATES.md`. `./benchmark.sh --local-iterate` is green with
`passed_correctness: true`, `max_abs_diff: 0`.

## M4 correctness caveat

**This host cannot validate this arm.** The host is `Mac16,11` (M4 Pro, Apple
GPU generation 16) and `is_nax_available()` is `false`, so
`steel_matmul_regular_axpby_nax` is never entered here — the function is behind
the `use_nax` gate at `matmul.cpp:894-898`. Independently, on M4 the
`M=512 N=1024 K=2048` shape takes the **split-k** path rather than the regular
path, so even a NAX-capable M4 would not exercise the retiled dispatch.

Therefore the local green run proves **build soundness, harness health, and
that the non-NAX path is unperturbed** — nothing more. It does **not** validate
`_nax` numerics or geometry, and **local timing is not evidence for or against
this arm in either direction**.

To be explicit about a point raised during assignment: the local gates are
**not** more meaningful for A2 than for A1 or A3. All three arms are M5-only.
Only the official M5 channel can measure or falsify them.

`MLX_METAL_GPU_ARCH` was **not** set at any point; forcing `_nax` on M4 is
forbidden by the assignment and was not attempted.

## Suggested follow-ups (not implemented)

1. **Decode-side twin**: `M < 64 && N <= 1024` -> `bn = 64`, taking the decode
   wk/wv dispatch from 32 to 64 threadgroups. Decode is 75 % of score, so this
   is the higher-leverage half of the idea — but it must be fired as its own
   arm on its own branch, never composed with A2.
2. `N = 2048` (the single layer-39 [K;V] bank dispatch, 3.2 TG/core) is the
   next-least-filled regular shape if A2 wins.
