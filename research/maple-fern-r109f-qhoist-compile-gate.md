# maple-fern R109-F — compile gate for the `DARKBLOOM_ATTN_QHOIST` default flip (ticket 3)

Recorded 2026-08-10 ~23:46Z on the M4 development host, at local commit `ef6612c7`
(+ ticket-3 changes already committed at `37f16a7a`).

## Why a gate was needed

The hoisted body inside `steel_attention_nax.h` had **never been compiled by
anybody**, because `DARKBLOOM_ATTN_QHOIST` defaulted to `0` and no build in this
repository ever passed `-DDARKBLOOM_ATTN_QHOIST=1`. A syntax or type error in
that block would not have shown up until the ranked host tried to build it,
which would burn a submission slot on a build failure rather than a measurement.
A second, subtler failure mode: flipping only the `#ifndef` in the vendored
header while leaving the generated JIT twin at `0` would produce a *silently
inert* candidate that looks like a clean negative result but tested nothing.

An earlier attempt at a gate was worthless and is recorded here so the mistake
is not repeated: `swift build -c release --force-resolved-versions --product
mlxfast-swift` (job `ce3c484a-422b-45c0-96e4-3fdd5b9853d8`) exited 0 in 9.4 s
with no compile steps, and `.build/release/mlxfast-swift` kept its 12:38 mtime
while `jit_kernels.cpp` was already 23:36 — nothing was rebuilt, so nothing was
validated. Exit code 0 from a build that did no work is not evidence.

## Gate 1 — the AOT Metal compile actually ran, and ran with the flag on

`bash tools/build-mlx-metallib.sh` (job `bb305342-23b0-44c3-8abe-e09882478169`)
exited 0. Log evidence:

* line 29 `[  0%] Building steel_attention_nax.air`
* line 76 `[100%] Building mlx.metallib`
* the only warning in the entire build is pre-existing:
  `fp_quantized_nax.h:1712: warning: unused variable 'BN_padded'`.
  Nothing from the attention TU.

Output: `.build-worker/release/mlx.metallib`, 158504952 bytes, 23:43;
`.build-worker/mlx-metal/mlx/backend/metal/kernels/steel_attention_nax.air`,
**288288 bytes**, 23:42.

## Gate 2 — proof the flipped default reached the compiler (A/B on the exact recipe)

Exit-code-0 does not distinguish "compiled the hoist" from "compiled the stock
kernel because the macro was still 0 somewhere". So I extracted the literal
recipe CMake uses for that target out of
`.build-worker/mlx-metal/mlx/backend/metal/kernels/CMakeFiles/mlx-metallib.dir/build.make`
and re-ran it twice by hand with the macro forced each way:

```
xcrun -sdk macosx metal -x metal -Wall -Wextra -fno-fast-math \
  -Wno-c++17-extensions -Wno-c++20-extensions -mmacosx-version-min=26.5.2 \
  -DDARKBLOOM_ATTN_QHOIST={0,1} \
  -c .../steel/attn/kernels/steel_attention_nax.metal \
  -I.../Source/Cmlx/mlx -o /tmp/qh/nax_{off,on}.air
```

| variant | exit | stderr | `.air` bytes |
|---|---|---|---|
| `-DDARKBLOOM_ATTN_QHOIST=0` | 0 | empty | 285968 |
| `-DDARKBLOOM_ATTN_QHOIST=1` | 0 | empty | 288288 |

Two conclusions, both load-bearing:

1. **The hoisted body compiles cleanly** — exit 0, zero diagnostics, with
   `-Wall -Wextra` on. The arm cannot fail the ranked build for a Metal syntax
   or type reason.
2. **The default flip is live in the ordinary build.** The `.air` produced by
   the plain `tools/build-mlx-metallib.sh` run is 288288 bytes, byte-count
   identical to the forced `=1` compile and 2320 bytes larger than the forced
   `=0` compile. If my header edit had not taken effect, the ordinary build
   would have produced the 285968-byte artifact.

The +2320-byte code-size delta is also a sanity check on the mechanism: the
hoist adds a staging block and turns eight in-loop loads into register moves,
which is the right order of magnitude, not a whole-kernel rewrite.

## Gate 3 — the JIT twin compiles the same code

`Vendor/mlx-swift/Source/Cmlx/mlx-generated/steel_attention_nax.cpp` is the
runtime-effective source string (`jit_kernels.cpp` is in the SwiftPM target at
`Vendor/mlx-swift/Package.swift:25`; `nojit_kernels.cpp` is excluded at `:284`).
It contains 6 occurrences of `Qhoist` and its `#ifndef` fallback is now `1`
(lines 25-26). Diffing the hoist region of the header (lines 288-400) against
the twin (lines 1572-1684) shows differences **only** in comment wording — the
twin carries an abbreviated version of the upstream `unroll_count(4)` note. The
executable text is the same text the Metal compiler just accepted in Gate 2.

## Gate 4 — the C++ translation unit rebuilds and links

`swift build -c release --force-resolved-versions --scratch-path .build-worker
--product mlxfast-runtime-worker` (job `212d911e-db8a-4c43-8b2a-a1808824fb09`)
finished: `Build of product 'mlxfast-runtime-worker' complete! (49.70s)`.
Unlike the earlier no-op, this one did real work on the edited file:
`.build-worker/arm64-apple-macosx/release/Cmlx.build/mlx/mlx/backend/metal/jit_kernels.cpp.o`
has mtime 23:45, i.e. newer than the 23:36 edit to `jit_kernels.cpp`. So the
`env::get_var("DARKBLOOM_ATTN_QHOIST", "1")` default and the opt-out
`#define ... 0` emission are both compiled into the scored binary
`.build-worker/release/mlxfast-runtime-worker`.

## What the gate does *not* establish

It says nothing about speed, and it cannot. `is_nax_available()` is false on this
M4 host, so `sdpa_full_self_attention_metal`
(`mlx/backend/metal/scaled_dot_product_attention.cpp:166`) never takes the
`:177` branch into `sdpa_full_self_attention_nax`, and the kernel is never
dispatched. A local benchmark A/B of this arm is structurally a no-op and any
delta it shows is harness noise. That is precisely why the arm is being spent on
a ranked receipt: the ranked host is the only instrument that executes it.

It also does not establish bit-exactness by measurement — only by reading the
source. The staging block (`steel_attention_nax.h:292-337`) reuses the same base
pointer, `Q_load_off`, row stride and `!align_Q && is_last_q` bounds predicate as
the in-loop load, and the consumption site (`:387`) replaces a load with a
register move; no float op is added, removed or reordered. The ranked
correctness gate is the test of that claim, and if it fails I want the failure
recorded rather than explained away.

## Residual risk carried into the submission

* Register pressure: `TQ=1`, `TD=8` ⇒ 8 bf16 fragments = 128 B/thread ≈ **+28
  registers/thread**, ~+16 KB live across a 128-thread group. The kernel
  allocates no threadgroup memory, so the cost is entirely register file.
* Upstream's adjacent `#pragma clang loop unroll_count(4)` comment records that
  a *partial* unroll was chosen deliberately so K-tile loads interleave with the
  mma chain (+12% at head_dim 128 on M5 Max). The Q hoist does to Q what that
  comment warns against doing to K, so the sign of the effect is genuinely
  two-sided and I am not claiming a prior.
