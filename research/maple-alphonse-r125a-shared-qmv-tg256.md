# R125-A — shared-expert SwiGLU QMV threadgroup width (TG=256) on the maple base

Student: maple-alphonse · PR #729 · assignment `maple-r125-a-shared-qmv-tg256-landing`
revision `r125-a-rev1` · branch `maple-alphonse/r125-a-shared-qmv-tg256-landing`
base `codex/mlxfast-maple-20260804-advisor` @ `a9de9e8f21188715f6d80ada4b581bcd50d4ec81`

## 0. Verdict

**Do not land TG=256. The assignment's premise is inverted.**

The assignment asks me to port frieren's R119-C TG=256 shared-SwiGLU-QMV geometry
onto the maple base and ship it as the default, on the stated grounds that the
geometry is worth about `+0.38 %` decode. Both halves of that premise fail on the
evidence that already exists in this repository, and my own replication on this
base agrees with the existing evidence:

1. **frieren's `+4.67` is a cost, not a gain.** The column in
   `research/frieren_r119c_FINAL_RESULT.md` is `qmv us/step` — per-step GPU-busy
   microseconds of the shared-QMV kernel — so arm C (TG=256) being `+4.67 us/step`
   above arm A (TG=64) means TG=256 is **1.61 % slower**, not faster. frieren's own
   title is "TG count is inert for the shared-expert SwiGLU QMV" and his law
   `L-LOAD-BALANCE-GRANULARITY` is recorded as **refuted**.
2. **The `+0.38 %` figure belongs to a different, already-rejected change.** It
   comes from PR #714 §0(b) and prices the R119-A router-tournament *grid-append
   fusion*, for which TG=256 is an enabling debit. That fusion was measured
   end-to-end as a **loss** (`+27.024 us/token`, `+0.210 %` decode), terminal
   verdict `N-GRIDAPPEND-SECOND-INSTANCE-BELOW-BAR`.

Landing TG=256 alone therefore pays the debit and collects nothing.

**Landing branch: none.** The branch carries the mechanism as an opt-in selector
(`DARKBLOOM_SHARED_QMV_TG`, default `64`), so the submitted surface is
behaviourally and dispatch-identical to the base unless the variable is set.

**My replication (§1), 12 mirrored slots on this base:** TG=64 `289.88 ± 0.48`
µs/step vs TG=256 `294.62 ± 0.46` µs/step, paired
**Δ = +4.73 ± 0.52 µs/step, CI95 [+2.50, +6.96], +1.63 %, 3/3 blocks positive**.
frieren measured `+4.67 ± 0.68` on a different base. Two independent instruments
agree that TG=256 is the *slower* geometry.

**End-to-end confirmation (§7), 16 mirrored slots, `SPLIT=0` fused schedule:**
wall decode is `8210.67` vs `8209.94` µs/step, paired
**Δ = −0.73 ± 11.41 µs/step, CI95 [−19.33, +17.86]**, 2/4 blocks and 4/8 mirror
pairs positive; the mean-centre estimator flips the sign to `+0.99`. A flat null
at `|Δ| < 0.015 %` of wall. This instrument is too coarse to *see* §1's
`+4.73 µs/step` (that is `+0.058 %` of wall, four times below its SEM), so §7
does not confirm the regression — but the `+0.38 %` gain the landing was
premised on requires **`Δ = −41.4 µs/step`**, which sits 3.6 σ outside the
interval. The benefit is excluded; only the sign of the (small) harm is beyond
this instrument's reach.

**What should be submitted:** nothing from this branch. The current best
(`2.6195531094824` at organizer commit `4ea72c3`) should stand; landing TG=256
would ship a measured regression on the strength of a misread column. I fired no
official submission, per the assignment.

## 0b. The portable hunk

The advisor's top-priority deliverable is "the smallest hunk that sets shared-QMV
threadgroup granularity to 256, applicable by someone else to a tree that does not
contain edward's #712 fused-kernel merge". Three patch files are committed; all
touch only `Sources/MLXFastModel/LagunaRuntimeModel.swift`.

| file | applies to | verified against | lines |
| --- | --- | --- | --- |
| `research/r125a-tg256-core.patch` | trees **with** #712 (current frontier) | `18ac6015` — 5/5 hunks, offset `+8` | 103 |
| `research/r125a-tg256-core-pre712.patch` | trees **without** #712 | `29a79361^` — 5/5 hunks, offset `0` | 109 |
| `research/r125a-tg256-fused-guard.patch` | **only** trees with #712 | `18ac6015` — 1/1 hunk, offset `-35` | 12 |
| `research/r125a-tg256-default-flip.patch` | on top of either core patch | `18ac6015` + core — 1/1 hunk | 10 |
| `research/r125a-tg256-landing.patch` | **the advisor's landing artifact**, trees with #712 | `18ac6015` — applied for real, fuzz `0`, file 396 910 → 398 851 B | 103 |

The fourth file is the advisor's requested compiled-default flip, kept **separate
and unapplied** on this branch. It is a one-line change of `else { return 64 }`
to `else { return 256 }` inside `lagunaSharedSwiGLUQMVThreadgroupWidth`, so the
advisor can land TG=256 in seconds if they overrule my recommendation, and the
`DARKBLOOM_SHARED_QMV_TG=64` escape hatch still restores the shipped geometry.
**I recommend against applying the flip**; the evidence is in §1, §2 and §7.

`research/r125a-tg256-landing.patch` is the fifth file: `core + flip`
pre-composed into a single `patch -p1` / `git apply` against `18ac6015`, so the
advisor needs one command rather than two. It is the exact artifact the plumbing
check in §8 exercises.

`git apply --check` was run for each row above; the two core patches, the flip
and the composed landing patch were also applied for real and the resulting file
inspected. Every hunk lands with fuzz `0`.

### The fused guard must NOT ship with the flip

The advisor's acceptance condition (2) is that with
`DARKBLOOM_SHARED_ROUTED_QMV_FUSED=1` the generated source and dispatch stay
byte-identical to today's tree. That condition is already satisfied
*structurally* by the core patch, and the guard patch would **break** it:

- The fused site calls the generator without the new parameter —
  `lagunaSharedSwiGLUQMVRows1Source(halved:weightName:scalesName:outputName:)`
  inside `lagunaSharedRoutedSwiGLUQMVKernel` (LRM:8238 on the branch tree) — so
  it picks up the defaulted `simdgroupsPerThreadgroup: Int = 2` and emits
  `uint row = tile * 2 + simd_group;` no matter what the selector returns. Its
  dispatch is hardcoded (`constexpr uint laguna_shared_tiles = 256;`,
  `threadGroup: (64,1,1)`). Byte-identity under FUSED=1 is therefore automatic.
- `research/r125a-tg256-fused-guard.patch` adds
  `lagunaSharedSwiGLUQMVThreadgroupWidth == 64` to the fused eligibility list in
  `lagunaSharedRoutedSwiGLUQMV(...)`. It exists because the branch ships the
  selector with default `64`, where it is a free safety belt. Once the default
  is 256 it stops being a belt and becomes a **kill switch**: FUSED=1 would
  silently fall back to the unfused path, which is exactly the behaviour change
  condition (2) forbids.

So the landing artifact is `core + flip` with the guard **removed**, which is
what `research/r125a-tg256-landing.patch` contains
(`grep -c 'ThreadgroupWidth == 64'` → `0`). Keep the guard only on trees that
keep the default at `64`.

### Anchors (symbol + line on the delivery base `18ac6015`, file unpatched)

| # | anchor symbol | line | what the hunk does |
| --- | --- | --- | --- |
| 1 | `let lagunaSharedQMVWideCodesEnabled` | 332 | insert `lagunaSharedSwiGLUQMVThreadgroupWidth` immediately after this declaration; reads `DARKBLOOM_SHARED_QMV_TG` ∈ {64,128,256}, default **64** |
| 2 | `private func lagunaSharedSwiGLUQMVRows1Source(` | 7139 | add defaulted parameter `simdgroupsPerThreadgroup: Int = 2` |
| 3 | `uint row = tile * 2 + simd_group;` (the **first** of two occurrences; the one inside anchor 2's body — the second, 7263, belongs to the routed kernel and must not be touched) | 7169 | emit `tile * \(simdgroupsPerThreadgroup)` instead of the literal `2` |
| 4 | `private let lagunaSharedSwiGLUQMVRows1HalvedKernel` | 7232 | add two sibling kernel constants `…HalvedTG128Kernel` / `…HalvedTG256Kernel` with **distinct Metal names** (`…_tg128_bf16_v1`, `…_tg256_bf16_v1`) at 4 and 8 simdgroups |
| 5 | `func lagunaSharedSwiGLUQMV(` | 7334 | derive `threads`, pick the kernel by `threads`, set `tiles = sharedExpertIntermediateSize / (threads / 32)`, dispatch `grid: (tiles * threads, 1, 1)` / `threadGroup: (threads, 1, 1)` |
| G | `func lagunaSharedRoutedSwiGLUQMV(` | 8218 | *(guard patch only)* add `lagunaSharedSwiGLUQMVThreadgroupWidth == 64,` to the eligibility list so #712's fused path declines when TG ≠ 64 |

Anchor 4 is the non-obvious one: MLX caches compiled libraries **by kernel name**,
so reusing `laguna_shared_nvfp4_swiglu_qmv_rows1_halved_bf16_v1` for a second
threadgroup width silently returns the first-compiled body and the experiment
measures nothing. Each width needs its own name.

Byte budget on the delivery base: `LagunaRuntimeModel.swift` goes 396 910 →
398 903 B (**+1 993**), under both the 524 288 B per-file cap and the 262 144 B
per-review growth cap.

### Why the split exists — the #712 collision

Anchors 2 and 3 are the only ones that differ across the #712 boundary. #712
(`29a79361`, R119-B grid-append) rewrote `lagunaSharedSwiGLUQMVRows1Source`
from `(halved: Bool) -> String` into a four-parameter generator with
`weightName` / `scalesName` / `outputName` defaults, and correspondingly
parameterised the weight-pointer lines that sit in anchor 3's trailing context.
Hunk-by-hunk `git apply --check` on `29a79361^` confirms this precisely:
hunks 1, 4 and 5 apply unchanged, hunks 2 and 3 do not. `…-core-pre712.patch`
is the same change re-expressed against the one-parameter signature. Both core
patches are otherwise identical in effect, and neither depends on the fused
kernel existing.

The guard patch is the only piece with a real #712 dependency, and it is not
part of the mechanism — it exists so a tree that has *both* changes cannot
dispatch #712's 64-thread-only fused kernel while `DARKBLOOM_SHARED_QMV_TG`
asks for a wider threadgroup. On a tree without #712 it must be skipped, and
`git apply --check` refuses it there, which is the desired failure mode.

### Could #712's fused kernel be re-tiled for 256-thread threadgroups?

Not by changing a constant, and not worth doing. The fused kernel hardcodes
`constexpr uint laguna_shared_tiles = 256;` (LRM:8201 on `18ac6015`) and is
dispatched at 64 threads/threadgroup because a grid-append shares **one**
threadgroup size across both halves of the dispatch: the routed top-8 QMV half
and the appended shared half. Widening to 256 threads therefore requires
(a) re-parameterising the *routed* generator's row mapping and per-simdgroup
reduction the same way I parameterised the shared one — the routed half is what
pins 64 threads, not the shared half; (b) recomputing `laguna_shared_tiles` as
`sharedExpertIntermediateSize / (threads / 32)`, i.e. 64 rather than 256, and
re-deriving the tile-offset arithmetic that separates routed tiles from shared
tiles in the appended grid, in the new tile units; and (c) absorbing a 4×
larger threadgroup-scratch footprint for the cross-simdgroup reduction (8
partial sets instead of 2), which fits but moves occupancy. That is a
simultaneous rewrite of two kernels whose correctness is currently protected by
the fact that neither is reachable by default. And the payoff is negative
twice over: §1 shows the 256-thread shared geometry is itself ~1.6 % slower per
shared-QMV step on this base (§5 ranked-equivalent ≈ +2.9 µs/step), and the
grid-append fusion the re-tiling would enable was already measured end-to-end as
a loss (`+27.024 us/token`, verdict `N-GRIDAPPEND-SECOND-INSTANCE-BELOW-BAR`,
§2b). I did not build it, per the assignment.

### Recommendation

Do not apply any of these patches as a default change. If a future student
wants the arms on a different base, apply the core patch matching the tree
shape, add the guard patch iff the tree has #712 **and** the default stays
`64`, and drive it with `DARKBLOOM_SHARED_QMV_TG`; the shipped dispatch is then
unchanged.

If the advisor overrules me and lands TG=256 anyway, the one command is

```bash
git apply research/r125a-tg256-landing.patch   # core + flip, no guard
```

and nothing else — not the guard patch, for the reason above.

## 1. Replication on the maple base

`research/maple_r125a_atlas.sh` → `/tmp/maple-r125a-atlas`, analysed by
`research/maple_r125a_analyze.py`. Host: M4 Pro, 20 GPU cores, 48 GiB, Apple GPU
generation 16 (never selects `_nax`), low-memory startup profile. 13 slots =
1 warm-up + 3 blocks of mirrored `64 256 256 64`, 200 decode steps each,
`DARKBLOOM_GPU_PROFILE=1 DARKBLOOM_GPU_PROFILE_SPLIT=1`,
`DARKBLOOM_SHARED_ROUTED_QMV_FUSED=0` throughout, 40 °C thermal gate re-armed
before every slot (`gpu_at_start` 37.1–39.3 °C, so no slot started hot). All 13
slots exit 0.

### Per-slot shared-QMV cost (`laguna_shared_nvfp4_swiglu_qmv_rows1_halved`)

| block | slot | TG | µs/step | calls/step | step busy ms |
| --- | --- | --- | --- | --- | --- |
| 1 | 1 | 64 | 291.50 | 39.00 | 8.282 |
| 1 | 2 | 256 | 294.10 | 39.00 | 8.204 |
| 1 | 3 | 256 | 294.50 | 39.00 | 8.225 |
| 1 | 4 | 64 | 289.00 | 39.00 | 8.200 |
| 2 | 1 | 64 | 290.10 | 39.00 | 8.202 |
| 2 | 2 | 256 | 294.00 | 39.00 | 8.219 |
| 2 | 3 | 256 | 293.70 | 39.00 | 8.209 |
| 2 | 4 | 64 | 288.80 | 39.00 | 8.203 |
| 3 | 1 | 64 | 291.00 | 39.00 | 8.242 |
| 3 | 2 | 256 | 296.80 | 39.00 | 8.263 |
| 3 | 3 | 256 | 294.60 | 39.00 | 8.204 |
| 3 | 4 | 64 | 288.90 | 39.00 | 8.205 |

### Result

| arm | n | mean µs/step | sem |
| --- | --- | --- | --- |
| TG=64 (default) | 6 | **289.88** | 0.48 |
| TG=256 | 6 | **294.62** | 0.46 |

Within-block paired deltas: `+4.05`, `+4.40`, `+5.75` µs/step.

> **Δ(TG256 − TG64) = +4.73 ± 0.52 µs/step, CI95 [+2.50, +6.96], = +1.63 % of the
> TG=64 kernel cost. 3/3 blocks positive, 6/6 slot-pairs positive.**

TG=256 is **slower**, decisively, on this base. The sign is not ambiguous: the
CI95 excludes zero by a factor of ~5 in sem units, and the mirrored `64 256 256 64`
ordering means slot position cannot produce it.

### Agreement with frieren R119-C

| quantity | frieren R119-C | this replication |
| --- | --- | --- |
| arm A / TG=64 | 289.83 ± 1.42 | 289.88 ± 0.48 |
| arm C / TG=256 | 294.50 ± 0.85 | 294.62 ± 0.46 |
| Δ | +4.67 ± 0.68 | +4.73 ± 0.52 |

Both arm means agree to better than 0.05 % and the deltas agree to 1.3 % of
themselves. This is an independent instrument on a different base reproducing
frieren's numbers essentially exactly, which retires the question: frieren's
`+4.67` is a **cost**, and TG=256 pays it.

### Controls

- **Mechanism reaches the scored path.** The TG=256 slots dispatch
  `custom_kernel_laguna_shared_nvfp4_swiglu_qmv_rows1_halved_tg256_bf16_v1`
  (`maxThreads=1024 execWidth=32`), the TG=64 slots dispatch
  `…_rows1_halved_bf16_v1`. Distinct PSO names in `*.pso` confirm the new kernel
  is compiled and executed rather than silently aliased to the cached one.
- **Token identity.** 9/9 comparison slots are byte-identical to their block's
  `s1_tg64` token stream (`TOKENS_IDENTICAL`), and the warm-up teacher-forced
  golden reports **0 divergences**.
- **Negative control.** Of 21 untouched kernels, 6 exceed the ±0.655 µs/step atlas
  resolution, all small and mostly *negative* (largest `-1.85` µs/step = −0.14 %
  of a 1357 µs kernel; largest positive `+0.72` = +0.25 %). Nothing untouched
  moves anywhere near +1.63 % of its own cost, so the shared-QMV delta is not a
  session-wide drift artefact.
- **Whole-step diagnostic.** GPU-busy sum is 8.222 ± 0.014 ms/step (TG=64) vs
  8.221 ± 0.009 ms/step (TG=256). The +4.73 µs is ~0.058 % of a decode step, i.e.
  well below whole-step resolution on this instrument. That is the honest
  magnitude statement: the regression is real and cleanly measured *at the kernel
  level*, and it is small in absolute end-to-end terms — but it is a debit with no
  credit attached, which is enough to decline it.

SPLIT=1 serialises dispatches, so the measured +4.73 µs/step is an **upper bound**
on the un-overlapped cost — the same caveat frieren recorded. Since the sign is
what the decision turns on, and SPLIT=1 can only exaggerate a cost rather than
invent one, no SPLIT=0 paired-wall A/B was needed to reject the landing.

## 2. Conflict resolution: where the `+0.38 %` premise came from

The assignment body states that frieren measured TG=256 at "+4.67 us/step ...
about +0.38 % decode". Those are two different experiments and the sign of the
first is inverted.

### 2a. Anchor: frieren R119-C is a *cost* measurement

`git show 039800fe5ed5f2523aeb4c9f4e225d15fd219191:research/frieren_r119c_FINAL_RESULT.md`

* Title: **"TG count is inert for the shared-expert SwiGLU QMV"**;
  `L-LOAD-BALANCE-GRANULARITY` recorded as **refuted**.
* Instrument: `decode_probe.py --profile` with `DARKBLOOM_GPU_PROFILE=1`,
  `DARKBLOOM_GPU_PROFILE_SPLIT=1`, 200 steps, `n=6` per arm, mirrored
  `64 128 256 256 128 64` × 3, 40 °C gate per slot, 19/19 slots `rc=0`.
* The reported column is `qmv us/step`: per-step GPU-busy time **of the
  shared-QMV kernel**, i.e. a cost. Lower is better.

| arm | geometry | qmv us/step | Δ vs A |
|---|---|---|---|
| A | TG=64, 2 simdgroups/TG, 256 TGs | 289.83 ± 1.42 (sem 0.58) | — |
| B | TG=128, 4 simdgroups/TG, 128 TGs | 290.38 ± 1.07 | +0.55 ± 0.73 (NS) |
| C | TG=256, 8 simdgroups/TG, 64 TGs | 294.50 ± 0.85 | **+4.67 ± 0.68 = +1.61 % slower** |

Through-origin slope φ = **+0.065 [+0.052, +0.079]** µs per simdgroup-per-TG —
a positive **cost** coefficient. All three arms hold the work byte-identical:
512 output rows, one row per simdgroup, 16 384 threads total; only the
partition into threadgroups changes.

frieren's own caveats, which I inherit: raw kernel numbers only, no end-to-end
anchor; `SPLIT=1` serialises one dispatch per command buffer, so it removes the
overlap that would otherwise hide part of the cost — the measured φ is an
**upper bound** on the deployed cost. The optional `SPLIT=0` paired-wall leg was
never run.

### 2b. Anchor: the `+0.38 %` is R119-A grid-append, and it lost

PR #714 §0(b) prices the router-tournament **grid-append fusion** at
`64.8–65.5 us/step` ≈ `+0.38 %`. TG=256 appears there as the *enabler*: the
fused kernel needs the wide threadgroup so the appended router-tournament grid
fits alongside the shared-expert tiles. The fusion itself was then measured:

* joint arm G: **+13.6 us/step [+9.5, +17.7]** (and +11.2 [+4.4, +18.0] under the
  ranked `DARKBLOOM_STARTUP_MEMORY_PROFILE=full` startup profile);
* end-to-end decode: **+27.024 us/token (+0.210 %)**, CI [−70.8, +124.9],
  4/4 arm-halves positive;
* terminal verdict `N-GRIDAPPEND-SECOND-INSTANCE-BELOW-BAR`, governing law
  `L-SIBLING-DISPATCH-IS-ALREADY-FREE` — MLX already encodes
  `MTL::DispatchTypeConcurrent` (`Vendor/mlx-swift/.../metal/device.cpp:548`), so
  sibling dispatches already overlap and fusing them buys nothing;
* the dispatch-removal arm R bounded a dispatch at `D ≤ 0.374 us/dispatch`
  against Rule 57's assumed `1.2382`.

So the `+0.38 %` was never a TG=256 gain, and the change it enabled is closed as
a loss.

### 2c. Independent corroboration from my own R119-A branch

On `maple-alphonse/r119-a-gridappend-family` (HEAD `c860c492`), arm **W**
(`DARKBLOOM_SHARED_QMV_WIDE8=1`) is exactly this geometry: `threads=256`,
`tiles=64`, 8 simdgroups per threadgroup. Measured at kernel level:

* low-memory startup profile: **−1.5 us/step, CI95 [−15.4, +12.5]** (10/12 blocks
  negative, sign test p = 0.039);
* ranked `DARKBLOOM_STARTUP_MEMORY_PROFILE=full`: **+2.7 [−11.2, +16.5]**;
* 48 runs, 48/48 cells proven 200/200/50.

Arm W was never taken end-to-end. frieren's `+4.67` sits comfortably inside W's
confidence interval, so the two instruments are consistent: the effect is small,
its sign is not favourable, and nothing supports a decode gain.

## 3. Correctness certificate

`research/maple_r125a_correctness.sh`, hook-free release worker built from this
branch's `LagunaRuntimeModel.swift`, job `12d3186e-027a-4b92-98c6-00844f3a8f22`,
exit 0 in 305 s. Every leg was run at **both** widths from the *same* binary,
so the only difference is the `DARKBLOOM_SHARED_QMV_TG` environment value.

| leg | TG=64 | TG=256 |
|---|---|---|
| teacher-forced 512-seed golden, 200 steps | **0 divergences** | **0 divergences** |
| free run, 64 self-fed steps | hash `005195dea7a52563`, distinct=3, cycle=3 | hash `005195dea7a52563`, distinct=3, cycle=3 |
| upstream-equivalence oracle | 8 steps `maxAbsLogitError = 0`, 1 step `0.125` | 8 steps `maxAbsLogitError = 0`, 1 step `0.125` |

Direct token-stream comparison of the dumped token files:

```
tf: TG64 == TG256 TOKENS_IDENTICAL
fr: TG64 == TG256 TOKENS_IDENTICAL
```

The free run is the stronger of the two token checks: it feeds the model its own
argmax, so a single divergent step at any position would fork the sequence and
change the hash. The hashes are equal, so every one of the 64 argmaxes agreed.

The single `maximumAbsoluteLogitError = 0.125` step is the **pre-existing
Apple-GPU-generation-16 prefill divergence of this host**, not a regression from
this branch. It is identical at both widths, it is present with the selector
compiled in but inactive, and frieren confirmed the same 0.125 on the unmodified
base in #714. `MLXFAST_LOCAL_ALLOW_GOLDEN_DRIFT` was never set, and
`research/run_upstream_equivalence.sh` was used so a zero-test invocation could
not be mistaken for a pass (the wrapper's non-zero exit is that one prefill step,
with `EQUIVALENCE_EXACT_STEPS=8` recorded at both widths).

Bit-identity is expected rather than lucky: the arms partition the same 512
output rows into threadgroups differently but assign one row per simdgroup in
both cases, and no reduction crosses a simdgroup boundary (`tgMem = 0`, §4). No
accumulation order changes, so no output value can change.

## 4. Mechanism and cross-kernel prediction

### Why a wider threadgroup is pure debit here

The shared expert's fused gate/up projection produces
`LagunaConstants.sharedExpertIntermediateSize` = 512 output rows, and the rows1
kernel assigns **exactly one row per simdgroup** (`uint row = tile *
simdgroupsPerThreadgroup + simd_group;`). Both arms therefore launch the same
512 simdgroups and issue the same arithmetic and the same weight traffic; the
only thing the selector changes is how those simdgroups are *packaged*:

| arm | threads/TG | simdgroups/TG | threadgroups | simdgroups |
| --- | --- | --- | --- | --- |
| TG=64 | 64 | 2 | 256 | 512 |
| TG=256 | 256 | 8 | 64 | 512 |

So the +4.73 µs/step is entirely a scheduling effect, not extra work. Two
mechanisms account for its sign, and the profile evidence discriminates between
them:

1. **The dispatchable-unit count collapses 4×.** The GPU schedules
   *threadgroups* onto cores, so the arm with 64 units has far less freedom to
   keep 20 (locally) or 40 (ranked) cores busy as they drain, and its tail
   quantises worse. §5 tabulates this exactly.
2. **A 256-thread threadgroup is pinned to one core.** Its 8 simdgroups
   contend for that single core's issue slots while each streams a *different*
   packed NVFP4 weight row; at 2 simdgroups/TG the same 8 rows can be spread
   across up to 4 cores. This kernel is weight-streaming bound, so the
   contention is directly on the critical resource.

The decisive structural fact is in the PSO line itself: **`tgMem=0`**. The
kernel allocates no threadgroup memory, because there is no cross-simdgroup
reduction and no shared tile — every simdgroup reads a disjoint weight row and
writes a disjoint output element. The *only* things a wider threadgroup can buy
in a Metal kernel are threadgroup-memory reuse and cheaper cross-simdgroup
reduction, and this kernel needs neither. There is therefore no credit side to
the ledger at all: widening the threadgroup here can only cost. That is the
general reason `L-LOAD-BALANCE-GRANULARITY` was refuted rather than merely
unconfirmed, and it is why I would not expect a different answer on the ranked
host.

### Cost coefficient

Per additional simdgroup-per-threadgroup (2 → 8, i.e. 6 increments):

- this replication: `+4.73 / 6 = +0.79 µs/step` per increment
  (`+0.020 µs/call` at 39.00 calls/step);
- frieren's three-arm through-origin fit over 2/4/8 simdgroups
  (`0`, `+0.55`, `+4.67`): `+0.73 µs/step` per increment.

Two independent instruments on different bases agree on the coefficient to
within 8 %. The relationship is convex, not linear — TG=128 is statistically
indistinguishable from TG=64 (frieren: `+0.55 ± 0.73`, NS) while TG=256 is
clearly positive — which is what mechanism 1 predicts, since quantisation loss
only bites once the threadgroup count drops near the core count.

### Falsifiable predictions

1. **Any QMV-family kernel with `tgMem=0` and one output row per simdgroup will
   show the same sign under TG widening.** The shared rows1 kernel and the
   routed top-8 QMV (same `row = tile * 2 + simd_group` idiom, LRM:7263 on
   `18ac6015`) are both in this class. Predicted magnitude ≈ `+0.02 µs` per call
   per additional simdgroup-per-TG.
2. **A kernel with a genuine cross-simdgroup reduction (`tgMem > 0`) is the only
   place TG widening could pay.** None of the shared or routed QMV kernels are
   in that class, so this family is closed as an optimisation target — which is
   the transferable result here.
3. **The ranked M5 does not flip the sign.** §5's quantisation model says the
   40-core host shrinks the *relative* penalty by ~1.6× versus this 20-core
   host, giving a ranked-equivalent ≈ `+2.9 µs/step`, still strictly positive.
   The debit shrinks; it does not invert. This prediction is host-portable
   because it depends only on threadgroup-count quantisation against core
   count, not on any `_nax` kernel selection, so gen-16 unreachability of
   `_nax` does not weaken it.

## 5. Ranked-host quantisation

The local host has **20 GPU cores**; the ranked M5 Max has **40**. The shared
SwiGLU QMV launches one threadgroup per tile, and each threadgroup occupies one
core, so the worst-core row count is
`ceil(TGs / C) * rows_per_TG`:

| arm | TGs | rows/TG | worst core, C=40 | vs A | worst core, C=20 | vs A |
|---|---|---|---|---|---|---|
| A (TG=64) | 256 | 2 | 7 × 2 = 14 | 0 % | 13 × 2 = 26 | 0 % |
| B (TG=128) | 128 | 4 | 4 × 4 = 16 | +14.3 % | 7 × 4 = 28 | +7.7 % |
| C (TG=256) | 64 | 8 | 2 × 8 = 16 | +14.3 % | 4 × 8 = 32 | +23.1 % |

The local C=20 geometry therefore **overstates** arm C's imbalance penalty by a
factor `23.1 / 14.3 = 1.61`. Deflating frieren's local `+4.67 us/step` by that
factor gives a ranked-equivalent cost of about **+2.9 us/step** — still a cost,
still the wrong sign, and still with nothing to pay for it. The quantisation
argument softens the penalty; it never turns it into a gain.

Two further ranked caveats: the M4 Pro reports Apple GPU generation 16 and does
not select the `_nax` kernels the ranked M5 uses, and threadgroup geometry is
exactly the class of change whose sign can move with core count. Both cut
against landing an unpaid geometry change on M4 evidence alone.

## 6. Deviations from the assignment

1. **No landing branch.** The assignment's success criterion was a branch with
   TG=256 as the shipped default. The evidence says that ships a regression, and
   the advisor explicitly authorised "land nothing" if TG=256 is not
   distinguishable. It is distinguishable — in the wrong direction.
2. **Arms reduced to TG=64 vs TG=256.** frieren already showed TG=128 ≈ TG=64
   (NS). I spent the whole slot budget on the decisive contrast to maximise
   power on the arm the assignment wanted to land.
3. **Mechanism kept, default unchanged.** `DARKBLOOM_SHARED_QMV_TG` is committed
   so the advisor or the next student can re-run the arms on any base without
   re-deriving the kernels, but the default is `64`.
4. **No official submission.** Per the assignment, the advisor owns submission; I
   ran none. On this evidence I recommend not firing one on this premise.

## 7. End-to-end wall A/B (`SPLIT=0`), 16 slots

§1's `+4.73 us/step` is a *kernel-isolated* number: it is measured with
`DARKBLOOM_SHARED_QMV_SPLIT=1`, which forces a separate command encoding for the
shared-expert SwiGLU QMV so the kernel's own cost is readable. That is the right
instrument for attributing the geometry effect, but it is not the scored
quantity. This section measures the same two arms with `SPLIT=0` — the ordinary
fused-schedule decode path — and asks the only question that matters for
landing: does the shipped wall time move?

Design: 4 blocks x 4 slots, mirrored `64, 256, 256, 64` inside each block so a
monotone thermal or clock drift cancels within a block *and* within each mirror
pair. 400 decode steps per slot, first 16 discarded, per-step centre taken twice
(median and mean) so the conclusion cannot rest on one estimator. 40 C cool gate
before every slot. Harness `research/maple_r125a_wall.sh`, analyser
`research/maple_r125a_wall_analyze.py`, raw slot logs under
`/tmp/maple-r125a-wall`.

| centre | arm mean TG=64 | arm mean TG=256 | block-paired delta | CI95 | blocks + | mirror-pair delta | CI95 | pairs + |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| median | 8210.67 us/step | 8209.94 us/step | **-0.73 +/- 11.41** | [-19.33, +17.86] | 2/4 | **-0.73 +/- 9.57** | [-18.21, +17.00] | 4/8 |
| mean | 8215.22 us/step | 8216.21 us/step | **+0.99 +/- 13.58** | [-21.24, +23.23] | 2/4 | **+0.99 +/- 11.69** | [-20.01, +22.87] | 4/8 |

This is a textbook null: the point estimate flips sign between the two centres,
its magnitude is under 1 us/step on an 8210 us/step wall (**|delta| < 0.015 %**),
and exactly half of the blocks and half of the mirror pairs fall on each side.

**What this does and does not settle.** The wall instrument's paired SEM is
about +/- 11 us/step, i.e. +/- 0.14 % of wall. The §1 kernel effect,
`+4.73 us/step`, is `+0.058 %` of wall — *four times below this instrument's
resolution*. So §7 honestly cannot confirm §1's regression end to end; a real
`+4.73 us/step` debit is invisible here and I will not claim otherwise. What §7
does do is close the other direction with authority. The advisor's landing
premise was a `+0.38 %` score gain; on the 75/25 decode/prefill weighting a
decode-only `+0.38 %` score movement needs
**`delta = -41.4 us/step`** of wall. That value sits 3.6 sigma outside the
median-centre CI and 3.1 sigma outside the mean-centre CI, and no individual
block of the four comes anywhere near it (worst block for TG=64 is
`-24.41 us/step`, and its mirror block is `+25.85 us/step`). The claimed benefit
is excluded by this measurement even though the measured harm is too small for
it to see.

**Correctness inside the timed arms.** All 12 non-reference slots emitted
`TOKENS_IDENTICAL` against their block's slot-1 reference — 400 greedy decode
tokens each, at both widths, under the fused schedule. That is on top of the
independent 200-step teacher-forced certificate in §3.

Reading §1 and §7 together: TG=256 is a small real debit on the kernel and a
statistical no-op on the wall. Neither reading supports landing it, and §7 is
the one that rules out the gain that was supposed to justify it.
