# maple-fern R109-F ticket 3 — `DARKBLOOM_ATTN_QHOIST` promoted to the default in the NAX prefill attention kernel

Submitter: maple-fern (morganmcg1 channel), round 109, integration-and-submission role.
Local result commit at submission time: see `commit_sha` in the accompanying typed result.
Replay nonce for archive de-duplication: `qhoist-r109f-t3-2026-08-10T23:47Z-nonce-4f1c9a2e`.

## One-paragraph summary

This candidate changes exactly one thing: the compile-time default of
`DARKBLOOM_ATTN_QHOIST` in the NAX (M5 matrix-coprocessor) Steel attention
kernel flips from `0` to `1`, so the loop-invariant Q fragments are staged once
into registers ahead of the K/V streaming loop instead of being re-materialised
from device memory on every K tile. No kernel arithmetic is touched, no tile
shape changes, and no Swift-level solver code changes. The intent is to remove
redundant Q loads from the *prefill* attention kernel on the ranked host. The
honest caveat, stated up front: this code path is unreachable on my development
machine, so this receipt is the *first* execution of the hoisted body anywhere,
and the readout I care about is the candidate prefill leg.

## What changed, precisely

Three files, all inside the vendored MLX tree, all of them default-value or
comment edits:

1. `Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/kernels/steel/attn/kernels/steel_attention_nax.h`
   — the `#ifndef DARKBLOOM_ATTN_QHOIST` fallback becomes `1` (was `0`).
   This is the definition the ahead-of-time `mlx.metallib` build compiles.
2. `Vendor/mlx-swift/Source/Cmlx/mlx-generated/steel_attention_nax.cpp`
   — the same `#ifndef` fallback in the generated JIT twin becomes `1`.
   This is the string the runtime hands to the Metal JIT, so it is the
   runtime-effective copy; leaving it at `0` would have silently no-op'd the
   whole arm. `nojit_kernels.cpp` is excluded from the SwiftPM target
   (`Vendor/mlx-swift/Package.swift:284`) while `jit_kernels.cpp` is included
   (`:25`), which is how I established which twin actually matters.
3. `Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/jit_kernels.cpp:1305`
   — `darkbloom_attn_qhoist_define()` now reads
   `env::get_var("DARKBLOOM_ATTN_QHOIST", "1") != "0"` and, when the operator
   opts *out*, emits an explicit `#define DARKBLOOM_ATTN_QHOIST 0` ahead of the
   kernel source. This mirrors the existing `darkbloom_attn_qblock_major_define()`
   helper line-for-line, so the opt-out story is symmetric with the arm that
   was already shipped: setting `DARKBLOOM_ATTN_QHOIST=0` in the environment
   restores the stock upstream kernel byte-for-byte.

Nothing else in the diff for this ticket. The remainder of the branch is
research prose, ledger rows and analysis tooling under `research/`, which
cannot affect the ranked binary.

## Why I believe this kernel is on the ranked prefill path

This was the part I got wrong in an earlier round — the arm had been retired on
the grounds that the hoisted block was dead code. That retirement was based on a
misreading, and here is the corrected chain, each link checked in source:

* At prefill the solver's own fused attention entry points
  (`lagunaSlidingFusedAttention` / `lagunaFullFusedAttention`,
  `Sources/MLXFastModel/LagunaRuntimeModel.swift:6164` and `:6190`) require
  `values.dims(1, 1, nKVHeads * headDim)`, i.e. sequence length exactly 1.
  A 512-token prefill therefore returns `nil` from the fused path and cannot
  consume it.
* The `callLastPrefillRow` shortcut (`LagunaRuntimeModel.swift:11681`) is
  guarded by `i == layers.count - 1` and by a `.causal` mask, and it builds a
  query of length 1. So it applies to one layer only; every other layer runs
  full `qL == L` attention through `attentionWithCacheUpdate`
  (`LagunaRuntimeModel.swift:6276`), which for a non-quantised KV cache calls
  `MLXFast.scaledDotProductAttention`
  (`Vendor/mlx-swift-lm/Libraries/MLXLMCommon/AttentionUtils.swift:48`).
* Inside MLX, `ScaledDotProductAttention::use_fallback` returns false for this
  shape: `qL = 512 > 8` and `headDim = 128` is in the supported
  `{64, 80, 128}` set, so `supports_sdpa_full` holds.
* `eval_gpu` then takes the full-attention branch into
  `sdpa_full_self_attention_metal`
  (`mlx/backend/metal/scaled_dot_product_attention.cpp:166`), and at `:177`
  that function dispatches to `sdpa_full_self_attention_nax` whenever
  `is_nax_available() && q.shape(3) != 80 && (tf32_enabled || dtype != float32)`.
* `LagunaConstants.headDim` is 128 and the model runs in bfloat16, so both
  side conditions hold. On a host where `is_nax_available()` is true, the NAX
  kernel *is* the prefill attention kernel for this benchmark.

The corollary is the caveat: on my development host `is_nax_available()` is
false, the kernel is never dispatched, and a local A/B is structurally
incapable of showing anything. I am not going to dress a local no-op up as a
validation.

## Why I expect the outputs to be numerically identical

The hoist is a pure staging change:

* The staging block (`steel_attention_nax.h:292-337`) fills `Qhoist[TQ * TD]`
  from the *same* base pointer with the *same* `Q_load_off` offset and the
  *same* row stride the in-loop path uses, under the *same*
  `!align_Q && is_last_q` bounds predicate. The out-of-bounds lanes take the
  identical zero-fill.
* The consumption site (`:387`) is
  `Qtile.frag_at(0, 0) = Qhoist[iq * TD + id];` — a register-to-register move
  replacing a load of the identical element.
* No floating-point operation is added, removed, reordered or re-associated.
  The mma chain, the online-softmax rescaling and the accumulator layout are
  untouched.

So this should be bit-identical output, not merely numerically close. If the
correctness gate fails, my exactness reasoning is wrong and I want to know that
more than I want the receipt.

## What it costs, and why this is genuinely two-sided

`TQ = 1`, `TD = 8`, so the hoist holds 8 bfloat16 fragments — 128 bytes per
thread, about **+28 registers per thread**, and roughly +16 KB across a
128-thread threadgroup. The kernel allocates no threadgroup memory, so this is
purely a register-file cost, and register pressure is exactly the currency the
NAX attention kernel is short of.

There is a specific reason to think the sign is not guaranteed. Immediately
adjacent to the hoist, upstream carries a
`#pragma clang loop unroll_count(4)` on the head-dimension loop with a comment
recording that a *partial* unroll was chosen deliberately: fully unrolling
hoists all `TD` loads up front and stops the compiler from interleaving the
next K-tile loads with the running mma chain, which was worth +12% kernel
throughput at head_dim 128 on M5 Max. My hoist does to the Q side precisely
what that comment warns against doing to the K side. Two plausible outcomes:
the Q loads were redundant and their removal is a small win, or the extra live
registers spill / cut occupancy and claw back more than the loads cost. I do
not have a strong prior between them, and I am submitting because the ranked
channel is the only instrument that can settle it.

## The verification I *could* do locally, and did

Since a runtime A/B is impossible on this host, I ran the strongest static gate
available — a real Metal-compiler build of the hoisted body, which had never
been compiled by anyone before, because the default was off:

* `tools/build-mlx-metallib.sh` completed with exit 0. `steel_attention_nax.air`
  built clean, and the only warning in the whole metallib build is a
  pre-existing unused-variable warning in `fp_quantized_nax.h:1712`.
* To prove the flag was actually live in that build rather than silently
  defaulting off, I re-ran the exact `xcrun -sdk macosx metal` recipe CMake
  uses, twice, with `-DDARKBLOOM_ATTN_QHOIST=0` and `=1`:
  `285968` bytes off, `288288` bytes on, both exit 0, both warning-free. The
  `.air` produced by the ordinary metallib build is `288288` bytes — a
  byte-exact match with the `=1` compile, which is direct evidence that the
  flipped default reached the compiler.
* I diffed the hoist body in the header against the generated JIT twin: the
  only differences are comment wording, i.e. the JIT will compile the same code
  the AOT compiler just accepted.

So the claim I am making is bounded and, I hope, precisely bounded: the hoisted
kernel *compiles* and is *reachable on the ranked host*; whether it is *faster*
is the open question this receipt answers.

## What I will read off the receipt

The signal lives in the candidate prefill leg. Across my 16 receipts from this
date the candidate prefill leg has mean 188.40 µs with a coefficient of
variation of 0.4710% (≈0.89 µs), so a change larger than about ±0.5% is
resolvable from a single receipt against that paired history; anything smaller
needs replays. The candidate decode leg should be unchanged within noise, since
decode attention goes through the solver's fused L==1 kernels and never reaches
this code. If decode moves, that is a red flag about my reachability analysis
rather than a result.

I am deliberately *not* forecasting a crown from this. On my own receipt
population the published score decomposes as `normalized × draw`, and the draw
term accounts for 84.2% of published variance; break-even against the current
crown needs a normalized level of about 2.6104, which is +1.088% over my best
normalized receipt of 2.582263383. A prefill-only improvement of a fraction of a
percent, weighted by the 0.25 exponent, cannot bridge that. This submission is
priced as information about the M5 prefill attention kernel, which the whole
programme has been reasoning about analytically and nobody has yet measured.

## Reproduction and rollback

* Reproduce the hoisted build: `bash tools/build-mlx-metallib.sh`, then
  `swift build -c release --force-resolved-versions --scratch-path .build-worker
  --product mlxfast-runtime-worker`.
* Recover stock upstream behaviour with no source edit:
  `DARKBLOOM_ATTN_QHOIST=0` in the environment, which makes
  `darkbloom_attn_qhoist_define()` emit an explicit `#define
  DARKBLOOM_ATTN_QHOIST 0`.
* Recover it at compile time: pass `-DDARKBLOOM_ATTN_QHOIST=0` to the metal
  compiler, or restore the two `#ifndef` fallbacks to `0`.

## Scope and hygiene

Editable-surface budget after this ticket: `current=2682367/3000000`,
`headroom=317633`, `files=142`, and every touched file is far below the
per-file 524288-byte cap. `senpai/validate-assignment-scope.sh` passes for all
three touched paths. The paths are disjoint from the two sibling arms running in
this round (an expert-down block-size arm in `quantized.cpp:1222-1250`,
`:1380-1520` and all of `matmul.cpp`; and a weight-tile staging arm in
`quantized.cpp:1690-1790` plus `quantized_utils.*` / `fp_quantized*`), so this
candidate can be stacked with either without a textual conflict.
