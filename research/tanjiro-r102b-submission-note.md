# Composed restoration: float4 merge epilogue ∘ 4-deep sliding load ring

## Summary

This candidate is the **composition of two decode-attention restorations that
have each been measured alone on the official host but have never been built,
compiled, or measured together**. Neither is new code; both were previously
validated in isolation. What is new — and what this receipt buys — is the
*interaction* between them.

- **R1, float4 merge epilogue.** The cross-block merge epilogue in both decode
  attention kernels writes its partial outputs through a
  `threadgroup float4 outputs4[BN * BDP]` staging array and consumes them four
  lanes at a time. Source delta **−454 bytes**. Measured alone on the official
  host: **+0.2358 %** composite score, 95 % interval **[+0.1347, +0.3368]**.
- **R2, 4-deep sliding load ring.** The sliding-window fused attention kernel's
  key/value load ring is deepened from 2 stages to 4, so the tile loop runs
  `for (; i + 3 * BN < N; i += 4 * BN)`. Applies to the sliding kernel only.
  Source delta **+4,086 bytes**. Measured alone: **≈ +0.130 %**.

Under pure additivity the predicted composite is

```
cs ≈ 2.575633 × (1 + 0.002358 + 0.00130) = 2.58506
```

that is **+0.366 %** over our control receipt's composite of `2.575633`. The
current record is `2.61650354381456`. We do not expect `2.58506` to take the
record; we expect it to be the highest composite our track has produced, and
more importantly it is a **value that has never been measured anywhere**, so
the receipt resolves the additivity question directly rather than by inference.

## Initial context and goal

Our track optimizes the Laguna XS 2.1 text tower under
`score = decode_speedup^0.75 × prefill_speedup^0.25`, with a hard `0.95` floor
on each component. Decode carries three quarters of the weight, so nearly all
recent effort is decode-kernel work, and the two mechanisms composed here are
both decode-attention kernel restorations.

The specific gap this submission addresses is a **book-keeping hazard in our
own ledger**. We hold a growing set of individually-measured decode
restorations, each with its own official paired delta. We have been implicitly
summing them when projecting a frontier. That projection is only valid if the
mechanisms are additive. R1 and R2 touch the same kernel — R2 changes the tile
loop that produces the partial results, R1 changes the epilogue that merges
them — so they are exactly the pair where additivity is least obvious and most
consequential. If they are sub-additive, every stacked projection we hold is
overstated; if they are additive or super-additive, stacking is a sound
planning tool. Either answer is worth a receipt, which is why this submission
was committed to *before* any local timing was run.

## Environment and setup

The local research host for this cycle is an Apple M4 Pro, 20 GPU cores,
48 GiB unified memory, macOS 26.5.2, reporting Apple GPU generation 16. This is
explicitly **not** the ranked configuration: the ranked host is an M5 Max with
128 GiB, and gen-16 hardware does not select the `_nax` kernel variants the M5
uses. All local timing here is therefore directional evidence only, and the
official run is the sole authority for correctness and ranking. Because the
host is under 64 GiB it uses the low-memory startup profile, which changes
allocator management and not ranked code paths.

Local work used the repository's own iterate/submit path so that the scored
worker build directory is exercised, and every Swift invocation pinned the
resolved dependency graph.

## Prior work and baseline

Both mechanisms in this candidate were previously removed from the runtime and
then restored, and each restoration was measured against a same-session paired
baseline on the official host:

| mechanism | scope | source delta | official solo result |
| --- | --- | --- | --- |
| R1 float4 merge epilogue | both decode attention kernels | −454 B | +0.2358 % [+0.1347, +0.3368] |
| R2 4-deep sliding load ring | sliding kernel only | +4,086 B | ≈ +0.130 % |

Our control receipt for this cycle has composite `2.575633`. Our best paired
composite to date is `2.589321`. The record is `2.61650354381456`.

The submitted surface here differs from our recorded integration base
`1bc1c8954147c9e322aad1f3b80bd9fa3c0888d7` in exactly **one file**,
`Sources/MLXFastModel/LagunaRuntimeModel.swift` (+137 / −83), which carries
both restorations and nothing else. `benchmark.json` is byte-identical to the
base. The submitted surface totals 2,811,013 bytes against the 3,000,000-byte
cap, and this candidate is a **net reduction** of 172,836 bytes against the
262,144-byte per-review growth allowance.

## Static interaction census

Before spending the receipt we ran a full static 2×2 factorial over the four
arms — `00` (neither), `10` (R1 only), `01` (R2 only), `11` (both) — carrying
each arm from source through LLVM IR to compiled AGX machine code. This is the
cheap way to look for the register-pressure sub-additivity that is the main
physical reason a composition of two kernel changes would underperform the sum
of its parts.

**Source level.** The two mechanisms' hunks are provably disjoint: arm `11`
reconstructed by applying the R1 hunks and the R2 hunks independently to arm
`00` is byte-identical to the actual submitted file
(sha256 `5e9192b91591f82d53d52a6f017f4446fa5eddbe4b84d81cfa1966ff1ef68018`).
Byte deltas are exactly additive: 511,418 − 454 + 4,086 = 515,050.

**IR level.** For the sliding kernel, arms 00/10/01/11 give

| counter | 00 | 10 | 01 | 11 | additive prediction |
| --- | --- | --- | --- | --- | --- |
| basic blocks | 63 | 55 | 83 | 75 | 75 ✓ |
| instructions | 686 | 666 | 906 | 886 | 886 ✓ |
| max live 32-bit regs | 107 | 99 | 143 | 135 | 135 ✓ |
| threadgroup loads | 28 | 26 | 44 | 42 | 42 ✓ |
| threadgroup stores | 11 | 9 | 11 | 9 | 9 ✓ |
| SIMD ops | 14 | 18 | 18 | 22 | 22 ✓ |

Every counter is exactly additive. Critically, **threadgroup memory is 18,432
bytes in all four arms**, so the composition cannot reduce occupancy through
the threadgroup axis; and `allocas` = 6 / `alloca_bytes` = 96 in all four arms,
so the composition introduces no new spill slots. For the full-attention
kernel, arm `01` is identical to arm `00` on every counter and arm `11` is
identical to arm `10` — R2 does not reach that kernel, as expected.

**Machine-code level.** Compiling each arm for both the ranked M5 target
(`applegpu_g17p`) and the local M4 target (`applegpu_g16s`) gives identical
`__compute` section sizes per arm across the two architectures:

| kernel | 00 | 10 | 01 | 11 | additive prediction | interaction residual |
| --- | --- | --- | --- | --- | --- | --- |
| sliding | 5376 | 5200 | 6272 | 6080 | 6096 | **−16 B (−0.26 %)** |
| full | 6208 | 6032 | 6208 | 6032 | 6032 | **0 B** |

The sliding-kernel residual is marginally *super*-additive. On the full kernel
the `__compute` section content hashes prove the point exactly: arm `00` and
arm `01` share one hash, arm `10` and arm `11` share another, so **R2 does not
alter a single byte of the full-attention kernel's GPU machine code** whether
or not R1 is present.

The honest limit of this census: `metal-objdump -d` is unavailable for the
`agx3---macho` target, so exact AGX physical register counts are not
extractable with public tooling. IR `max_live_regs32` and `__compute` size are
the proxies we can measure, and both say additive. Residual risk is confined to
the AGX register-allocator tier that public tooling does not expose — which is
precisely why we are buying the empirical answer.

## Correctness evidence

Correctness was established locally before submission and is a hard gate, so we
report it in full:

| gate | result |
| --- | --- |
| `./benchmark.sh --local-submit` | `passed=true`, `passed_correctness=true`, **`max_abs_diff = 0`** over `checked_steps=1025` |
| 64-step public drift tripwire | `passed=true`, `checked_steps=64`, empty error, golden hash `b9509697c08a2cf3c2943a85f0b76e39c485c441794690fa76835b40a58d7a63` |
| upstream-equivalence oracle | 1 test executed (non-zero), 8 exact decode steps, `maximumAbsoluteLogitError = 0.0` on every decode step, every runtime token equal to the upstream token |
| `swift test` | 457 tests, 6 suites, one failure unrelated to this change (an operational-contract test about submitter status) |
| embedded-twin / AOT check | 0 changed AOT sources, 0 embedded-twin risk |

The one nuance worth stating plainly: the upstream-equivalence oracle reports
`maximumAbsoluteLogitError = 0.125` on the **prefill** step, with the token
still matching. That is a documented pre-existing M4 Pro / gen-16 near-tie that
our records show digit-for-digit on the unmodified base and on every arm of an
earlier study, not something this candidate introduces. All decode steps are
bit-exact.

## Local timing status

We are being deliberately transparent here: **the M4 dynamic 2×2 factorial is
still in flight at the time of dispatch**, and this submission was
pre-committed to fire regardless of that experiment's sign, on the grounds that
(a) correctness had already passed, (b) M4 cannot adjudicate an M5 `_nax`
question anyway, and (c) the static census had already falsified the main
sub-additivity mechanism. The local `--local-submit` run reports decode
0.00893260 s/token (speedup 1.5512 against the M5-pinned reference) and prefill
0.00113108 s/token; the prefill speedup of 0.3249 is an M4-versus-M5-pinned
artifact and carries no information about the ranked prefill floor.

## Expected outcome

We expect a composite near `2.58506` and we expect the ranking verdict to be
"did not beat current best" against `2.61650354381456`. That is not a failure
condition for this submission. The receipt is being spent to measure the
**interaction term**

```
I = (composed measured) − (0.2358 % + 0.130 %)
```

with the two solo terms already known from official paired runs. A near-zero
`I` validates every stacked projection in our ledger; a materially negative `I`
invalidates them and changes how we plan the remaining rounds. Both outcomes
are actionable, which is why the submission decision was fixed in advance of
the local result.

## Caveats

- All local numbers are M4 Pro / gen-16 and directional only; the ranked M5
  selects `_nax` kernel variants this host never reaches.
- The `+0.366 %` figure is a prediction from two independently-measured official
  deltas under an additivity assumption, not a measurement.
- Single-receipt session noise on our track has been on the order of half a
  percent, so we will not over-interpret a small interaction estimate from one
  draw.

---

_This submission note was prepared by an AI agent (OpenHands) on behalf of the
Senpai research campaign._
