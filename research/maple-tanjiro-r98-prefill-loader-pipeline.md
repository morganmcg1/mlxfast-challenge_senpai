# R98-C — routed gather-GEMM loader/MMA pipelining (`_nax` expert kernel)

PR #541 · branch `maple-tanjiro/r98-prefill-loader-pipeline` ·
assignment `maple-r98-c-prefill-loader-pipeline` rev `r98-c-rev1` ·
BASE_SHA `450953e5c8287bfa1f409addf568d7851458cf94`.

**Status of this document.** Sections 1–8 are the *preregistration*. They were
written and committed before the first receipt was spent. Section 9 is filled in
per receipt afterwards and never rewrites a preregistered prediction.

> **⛔ SUSPENDED 2026-08-09.** The research base was replaced by the promoted
> organizer frontier `4f3108c4` (PR #541 comment `5231841896`). **Zero receipts
> were ever spent and no GPU work was ever launched on this arm.** Every number
> below is bound to base `450953e5` / `e510bb3d`. Section 12 records, with git
> evidence, exactly which of those numbers survive the base move and which do
> not. No rebase has been performed; the arm waits for a revised brief or a
> close.

---

## 1. Hypothesis under test (H-C)

The routed gather-GEMM mainloop is loader-latency-bound: the k-loop alternates
`barrier → stage tile k → barrier → MMA on tile k`, so every simdgroup in the
threadgroup stalls at the second rendezvous until the slowest lane has finished
writing the weight tile, and the MMA pipe drains while that happens. Giving the
loop a real double buffer — stage tile *k+1* while tile *k* feeds the MMA —
should remove that exposed latency and reduce prefill seconds/token.

The intervention is only meaningful if it *also* removes a barrier. With one
staging buffer the two barriers are irreducible (one WAR, one RAW). With two
buffers the WAR and RAW hazards target disjoint memory and a single rendezvous
per iteration discharges both. So this arm is simultaneously:

- a latency-overlap test (stage k+1 issues before the MMA of k), and
- a synchronization-count test (2 barriers/iteration → 1).

Both directions are the round-98 thesis; §7 explains why the arm is *not*
redundant with PR #215.

## 2. Coordinate correction to the assignment

The assignment cites `Ws` at `fp_quantized_nax.h:1363-1367` and the mainloop at
`:1496-1568`. Those lines belong to **`fp_gather_qmm_rhs_nax`** (header
1326–1644), which is *not* the kernel the ranked M5 runs for the Laguna MoE.

The scored kernel is **`fp_gather_qmm_rhs_expert_nax`**, header 1690–2036
(twin: `mlx-generated/fp_quantized_nax.cpp` from line 1832). `quantized.cpp`
routes to it whenever `expert_aligned` holds, which it does for both Laguna MoE
shapes at the shipped tiling. All edits in this arm are inside the expert
kernel; the non-expert kernel is deliberately left byte-identical and serves as
an in-file control.

Instantiation actually built (from `get_template_definition`):

```
T=bfloat16_t, gs=16, bits=4, BM=64, BN=64, BK=64, WM=4, WN=1, transpose=true,
{K,N} ∈ {(2048,1024),(512,2048)}, Wtype=bfloat, tg_expert_groups=256,
wide_store=true, wide_load=true, pairwise_scale_layout ∈ {1,2}
```

`BK_padded = 72`; `kWsElems = BN*BK_padded = 4608` bfloat = **9216 B**;
`kWsPerChunk = 8`, `kWsChunks = 576` exactly. `SM=16 SN=64 SK=32 TM=1 TN=4
TK=2`; **128 threads = 4 simdgroups** per threadgroup. `K_it = 32` (gate/up,
K=2048) or `8` (down, K=512).

## 3. Rung 1 (free flag screen) — **null by construction, no receipt spent**

The assignment's rung 1 was to screen the existing `DARKBLOOM_EXPERT_STAGE_*`
function constants (fc204–207: `WIDEST`, `WIDELD`, `RUNBAR`, `NOVOL`) for a free
win before writing code. That screen cannot produce a signal, for a reason that
is visible in the source and does not need a machine:

`quantized.cpp` populates `func_consts` only on the `!expert_aligned` branch.
The expert kernel is compiled **without function constants** — its staging
widths arrive as *template* arguments `wide_store` / `wide_load`, and both are
already `true` in the shipped instantiation. The in-source comment in the
mainloop states the same thing independently:

> This kernel is built WITHOUT function constants (static expert shape path),
> so the `stage_novol` lever never reaches it -- the volatile must go here.

So fc204–207 are dead on the scored path: they can only ever reach
`fp_gather_qmm_rhs_nax`, which the ranked M5 does not run for this shape.
Rung 1 is recorded as a **structural null at zero receipts**, and the whole
receipt budget is available to rung 2. This is also a live corpus correction:
any future note proposing an `EXPERT_STAGE_*` flag screen should stop here.

## 4. Implementation (rung 2)

Four edits, all inside `fp_gather_qmm_rhs_expert_nax`, mirrored byte-for-byte
into the JIT twin (`mlx-generated/fp_quantized_nax.cpp`) by a three-way merge
that refuses on any conflict; the twin differs from the header only by an
eight-line comment block the generator had already dropped.

1. **Storage.** `Ws_storage[kWsChunks]` → `Ws_storage[kWsChunks * kWsStages]`
   with `kWsStages = 2`, `kWsStride = kWsChunks * kWsPerChunk` elements. `Ws`
   and `gate_up_stage` still alias buffer 0, so the staged-epilogue arm is
   unaffected.
2. **Prologue** (per chunk, immediately before the k-loop): one
   `threadgroup_barrier`, capture `stage_dst0 = loader_w.dst`, stage tile 0 into
   buffer 0, `loader_w.next()`. `loader_w` is constructed *inside* the
   `chunk_start` loop, so `stage_dst0` is always the buffer-0-relative,
   per-thread destination — there is no cross-chunk carry.
3. **Mainloop.** One `threadgroup_barrier` per iteration instead of two. The
   staging call becomes `if (k + 1 < K_it) { loader_w.dst = stage_dst0 +
   ((k+1)&1)*kWsStride; …stage…; loader_w.next(); }`; the trailing barrier is
   deleted.
4. **MMA.** `const threadgroup Wtype* Wk = Ws + (k & 1) * kWsStride;` and
   `Btile.load_contig_tg<Wtype, BK_padded>(Wk + tn*BK_padded + kk1)`. The
   loop-tail `loader_w.next()` moves into the guarded stage, so the tail is
   `xn += BK;` only.

### 4.1 Hazard proof

At iteration `k` the single barrier discharges both hazards because they target
disjoint buffers:

- **RAW.** Tile `k` lives in buffer `k&1`. It was staged during iteration `k-1`
  (or by the prologue for `k=0`), i.e. strictly before this barrier. The barrier
  publishes it to every simdgroup before the MMA reads it.
- **WAR.** The stage below writes buffer `(k+1)&1`. The last reads of that
  buffer were the MMA of iteration `k-1` (buffer `(k-1)&1 = (k+1)&1`), which
  happened after the previous barrier and before this one. This barrier retires
  them.
- **Within the iteration**, the stage writes `(k+1)&1` while the MMA reads
  `k&1`. Disjoint, so no rendezvous is needed between them — that is exactly the
  overlap being bought.
- **Across chunks**, the prologue barrier reproduces the guard the shipped
  loop's first barrier provided (the shipped source says so in the
  `#ifndef DARKBLOOM_SWIGLU_REGLOCAL` comment: "the next chunk's k-loop opens
  with its own WAR barrier"). In the shipped `DARKBLOOM_SWIGLU_REGLOCAL` build
  the epilogue touches no threadgroup memory at all.

### 4.2 Bit-exactness

`Dtile` is accumulated in the same order — `k` ascending, `kk1` ascending within
`k`, same fragments, same `tile_matmad_nax` calls, same operand values. Only the
*address* the B fragment is read from changes, and it is read after the barrier
that published exactly the bytes the shipped code would have published. No
arithmetic, rounding, contraction or ordering change. Bit-exact by construction,
not by measurement.

### 4.3 Barrier census

Per `(chunk, column tile)`: shipped `2 * K_it`, arm `K_it + 1`.

| GEMM | shape | col tiles | `K_it` | shipped barriers | arm barriers |
|---|---|---:|---:|---:|---:|
| gate/up | K=2048 N=1024 | 16 | 32 | 1024 | 528 |
| down | K=512 N=2048 | 32 | 8 | 512 | 288 |
| **total per chunk** | | | | **1536** | **816** |

`research/tanjiro-nax-kloop-pipeline.md` §A.2 counts **8379** chunk-iterations
over the 512-token prefill, so the arm removes **≈ 6.03 M** threadgroup
rendezvous. `research/tanjiro-pr66-barrier-scope-narrowing.md` prices
`threadgroup_barrier` at **≈ 22.1 ns at 4 simdgroups** (0.32 ns at 1 SG, +21.2
ns 1→2, +0.6 ns 2→4) — this kernel's exact geometry. That is **≈ 133 ms of
summed threadgroup-time**, to be divided by realized threadgroup concurrency.
PR #66's own caveat applies: an added-work slope is an *upper bound* on the
saving from removal.

## 5. Step 0 — zero-receipt occupancy discriminator (**this is the headline**)

Method and reading copied from `tanjiro-nax-kloop-pipeline.md` §6.6. Artifact:
`research/artifacts/tanjiro-pr541-step0-pipeline-stats.txt`. Both ranked shapes,
offline-compiled control vs arm, `DARKBLOOM_SWIGLU_REGLOCAL` and
`DARKBLOOM_BSEARCH_HOIST` on as shipped.

| function | tgMem_B | maxThreads | width | TGs/core |
|---|---:|---:|---:|---:|
| `…_2048x1024_bk64` control | 9232 | 1024 | 32 | **7** |
| `…_2048x1024_bk64` arm | **18448** | 1024 | 32 | **3** |
| `…_512x2048_bk64` control | 9232 | 1024 | 32 | **7** |
| `…_512x2048_bk64` arm | **18448** | 1024 | 32 | **3** |

At 4 simdgroups per threadgroup and the 64 KiB per-core threadgroup pool used
throughout this corpus: `floor(65536/9232) = 7` → `floor(65536/18448) = 3`.
The simdgroup-slot bound (32 SG/core ÷ 4 = 8 TGs) is not binding in either case,
so **threadgroup memory is the binding residency constraint on both sides** and
the arm costs `28 → 12` resident simdgroups per core, a **57 % reduction**.
`maxTotalThreadsPerThreadgroup` is unchanged at the 1024 API ceiling and the
execution width is unchanged at 32, so launch geometry and register-driven
residency are not implicated — the entire residency change is the second
staging buffer.

**This is the advisor's named failure mode, and it is now known before any
receipt.** It is *not* a reason to skip the measurement, for three reasons:

1. The 64 KiB per-core pool is a corpus convention measured on nothing; the M5's
   pool is not observable from this host. If it is 128 KiB the arm sits at 7
   TGs/core and the confound vanishes.
2. `PR #215` §6.9 concluded this loop is **issue-limited, not
   exposed-latency-limited**, at 28 resident simdgroups. If that is right,
   residency above the issue-saturation point is free to spend, and the barrier
   removal is a pure win. If it is wrong, the arm loses. Either way the receipt
   discriminates.
3. No footprint-neutral variant removes a barrier. Two live `BN×BK_padded` tiles
   cannot fit in the 9362 B that 7 TGs/core allows; `BN=32` would fit but breaks
   the fused swiglu (`kSwigluRegLocal` requires `BN==64`, and the staged
   epilogue pairs gate column `c` with `c + BN/2`, which is only the correct
   gate/up pairing at `BN=64`). Barrier removal *requires* the second buffer.

### 5.1 Preregistered fallback if the arm is null

If rung 2 is non-positive, the correct follow-up is the advisor's **half-tile
(split-K) staging** variant, and its budget is already computed:

- buffers of `BN × (SK + 8) = 64 × 40` bfloat = **5120 B** each, two stages =
  **10240 B** (+16 B `bounds`) = 10256 B → `floor(65536/10256)` = **6 TGs/core**,
  a 14 % residency cost instead of 57 %;
- barrier count is *unchanged* (1 per 32-deep iteration × 64 = the shipped 2 per
  64-deep iteration × 32), so it isolates **overlap** from **synchronization
  count**, which is exactly what a null here would leave ambiguous;
- it is bit-exact for the same reason as §4.2: the `Dtile` accumulation visits
  `k*64 + kk1` in the identical ascending sequence whether the tile depth is 64
  with two `SK` steps or 32 with one.

## 6. Preregistered go/no-go

Primary readout: candidate prefill wall against the contemporaneous paired
control in the same official session. `f = 4 · prefill_sec_per_tok ÷
decode_sec_per_tok` is recomputed per receipt from the candidate's own score
JSON and reported, never carried over.

- **Rung 3** iff prefill improves **≥ 0.8 ms** vs the contemporaneous control,
  the revert leg lands within **1 prediction-se** of zero, and decode is flat
  within **0.5 σ** (σ(cand_dec) = 0.2939 %).
- **Falsification of H-C** requires a non-positive rung 2 **with a clean revert
  leg and no occupancy regression**. §5 shows the occupancy precondition already
  fails, so a null here **cannot** falsify H-C; it will be recorded as a
  *resource constraint* and routed to §5.1.
- A prefill regression larger than the §4.3 upper-bound saving (≈ 1.1 ms at
  120-way concurrency) is affirmative evidence that this kernel is
  **residency-limited**, which is itself a first-class finding: it would explain
  PR #215 §6.9's null mechanistically and would retire the whole in-kernel
  staging family for good rather than leaving it "closed by measurement".

Magnitude bracket for the upside, stated before the draw: 133 ms of summed
threadgroup-time ÷ realized concurrency gives **≈ 0.48 ms** at 280-way (40 cores
× 7 TGs) and **≈ 1.11 ms** at 120-way (40 × 3). At the round-98 cost model
(prefill **0.3794 %score/ms**) that is **+0.18 % to +0.42 % score**, against
σ(score) = 0.6172 % — so a single receipt cannot resolve the low end, and the
0.8 ms gate is deliberately set above it.

## 7. Why this is not PR #215 re-run

`research/tanjiro-nax-kloop-pipeline.md` §6.9 declared the `_nax` in-kernel
staging / prefetch / "double-buffering" family closed: measured on the ranked M5
at **+0.684 ms (+1.52 σ)** against a −7.6 σ … −27.2 σ prediction, with occupancy
and geometry *provably* constant, and concluded the loop is limited by memory-op
**issue**, not exposed latency. That is a serious prior and it is the reason
this arm needed the §5 discriminator before spending anything.

It is nevertheless a different intervention in kind:

| | PR #215 arm 1 | PR #541 rung 2 |
|---|---|---|
| prefetch target | **registers** | **threadgroup memory** |
| threadgroup bytes added | **0** | **+9216** |
| barriers per iteration | **2 (both kept)** | **1** |
| instruction count | **+7.5 %** | **−1 barrier**, staging unchanged |
| residency | 7 → 7 TGs/core | **7 → 3 TGs/core** |

PR #215 tested whether *device-read* latency was exposed and found it was not.
It could not test the barrier itself, because a single buffer makes both
barriers mandatory. Round 98's `CURRENT_RESEARCH_STATE.md` §4 explicitly
reopens "real double buffering, and prefetch across barriers" on the M5
in-flight-bytes argument (M5 needs ≈ 191 kB in flight vs M4's ≈ 80 kB), so the
frontier's own thesis and §6.9's verdict disagree. **This arm is the
discriminator between them**, and §5 has already converted it from a two-way to
a three-way discriminator by pricing the residency leg in advance.

## 8. Ideas dead by construction (not to be re-proposed)

Carried forward from the assignment §7 and re-verified against this base:
prefill dispatch-count reduction of any kind (rule 68), `_nax` N-tile narrowing
below `bn=128`, `_nax` prefill swizzle depth, and M-tile underfill. Added by
§3 of this note: `DARKBLOOM_EXPERT_STAGE_{WIDEST,WIDELD,RUNBAR,NOVOL}` flag
screens on the scored path.

**M4 is inadmissible for this arm.** Apple GPU generation 16 never selects the
`_nax` prefill kernels, so no local timing on this host is evidence about it.
The offline Metal compile plus the metallib pipeline reflection in §5 are the
only local gates that say anything, and the corresponding artifacts are
committed.

## 9. Receipts

| # | arm | candidate prefill | control prefill | Δ ms | `f` | pred-se | decode Δ | verdict |
|---|---|---|---|---|---|---|---|---|
| — | *(preregistration committed; no receipt spent yet)* | | | | | | | |

## 10. Local gates

| gate | result |
|---|---|
| offline MSL compile, `2048x1024` + `512x2048`, `std=metal4.0` | *(§9 update)* |
| metallib link + pipeline reflection | *(§9 update)* |
| `senpai/validate-assignment-scope.sh` | *(§9 update)* |
| `senpai/check-editable-budget.sh` | *(§9 update)* |
| `research/run_upstream_equivalence.sh` | *(§9 update)* |
| 64-step drift tripwire | *(§9 update)* |

## 11. Rule 68 re-scoring (advisor's explicit ask)

*To be written against the receipt, per the advisor's instruction: whichever way
rung 2 lands, re-score rule 68's two surviving explanations — (a) SLC capacity
crossing, (b) lost inter-dispatch read-after-read overlap — and state whether
the `[Wk;Wv]`-only discriminator becomes more or less urgent.*

## 12. Base move to `4f3108c4` — what survives, what does not

The HOLD (comment `5231841896`) states the base was *replaced*, not advanced,
and that every line anchor and every prefill attribution number in the brief is
stale. That is correct for the attribution numbers. It is **not** correct for
the kernel coordinates, and the distinction decides how much of §2–§5 has to be
redone. Evidence below, all read-only; nothing was rebased.

### 12.1 The edited Metal surface is byte-identical across the base move

`4f3108c4` is a merge; `e510bb3d` is one of its ancestors
(`git merge-base --is-ancestor e510bb3d 4f3108c4` → yes). The sync commit
`71818038` does rewrite `fp_quantized_nax.h`/`.cpp`, `steel/gemm/nax.h`,
`gemm_nax.cpp` and `quantized.cpp` **relative to its own parent `e630f1f`**,
which sits on the `main` lineage — but the Maple branch already carried the
`cc6ddc1` kernel content, so the merge resolves to the same blobs. Blob
identity, old base `83da91e` (≡ `e510bb3d` for these files) vs new `4f3108c4`:

| file | blob @83da91e | blob @4f3108c4 |
|---|---|---|
| `kernels/fp_quantized_nax.h` | `8b173827` | `8b173827` |
| `mlx-generated/fp_quantized_nax.cpp` | `bf6c5339` | `bf6c5339` |
| `metal/quantized.cpp` | `8b2d47ec` | `8b2d47ec` |
| `kernels/steel/gemm/nax.h` | `95dbffee` | `95dbffee` |
| `mlx-generated/gemm_nax.cpp` | `144a1bae` | `144a1bae` |

`git diff --stat 83da91e 4f3108c4 -- Sources/ Vendor/` lists **no**
`Vendor/mlx-swift/Source/Cmlx/**` path at all. Independently,
`git show 83da91e:…fp_quantized_nax.h | sed -n '1690,2036p'` and the same range
at `4f3108c4` are identical, so `fp_gather_qmm_rhs_expert_nax` still occupies
header lines **1690–2036** on the new base, `kWsElems` at `:1733`,
`kWsPerChunk` at `:1734`, `Ws_storage` at `:1736`.

Consequently these survive unchanged and do **not** need redoing:

- §2 coordinate correction (shipped kernel is `fp_gather_qmm_rhs_expert_nax`,
  not `fp_gather_qmm_rhs_nax`), including all line anchors.
- §3 rung-1 structural null — `quantized.cpp` is byte-identical, so
  `func_consts` is still populated only on the `!expert_aligned` branch and
  `DARKBLOOM_EXPERT_STAGE_{WIDEST,WIDELD,RUNBAR,NOVOL}` still cannot reach the
  shipped expert kernel. Rung 1 remains null at zero cost.
- §4 implementation, RAW/WAR hazard proof, bit-exactness argument, and the
  per-chunk barrier arithmetic (1536 → 816).
- §5 Step-0 occupancy result (`tgMem 9232 → 18448 B`, 7 → 3 threadgroups per
  core at a 64 KiB pool, `maxThreads 1024`, `width 32`), because it is an
  offline compile + metallib-reflection property of these exact byte-identical
  sources. The §5.1 half-tile fallback arithmetic (10256 B, 6 TGs/core) is
  likewise unaffected.
- The working-tree patch itself: it applies to `4f3108c4` verbatim.

### 12.2 What the base move genuinely invalidates

Everything that converts a kernel-level change into a *score* change, because
`Sources/MLXFastModel/LagunaRuntimeModel.swift` gained ~2928 lines,
`Sources/MLXFastModel/LagunaRuntimeLayers.swift` (2597 lines) was deleted, and
the `MLXLMCommon` cache/decode stack (`KVCache`, `BatchKVCache`,
`CompilableKVCache`, `CompilableRotatingKVCache`, `CompiledDecode`, `Evaluate`)
was rewritten. Treat as **stale and unverified**:

- the loader-vs-compute LSU split (50 vs ~40) and the "loader ≈68 % of LSU
  traffic" figure;
- the `steel_gemm_bf16` pool time (12.30 ms), the candidate prefill wall
  (96.278 ms), and the ≈54 % routed-GEMM share of prefill;
- the prefill window `W = 43.2619 ms` and the cost model constants in §6
  (0.3794 %score/ms prefill, 0.015280 %/µs/step decode, σ values), all of which
  were fitted to the old runtime;
- the record and best-common-baseline numbers.

The 280-way / 120-way concurrent-threadgroup assumption behind the 0.48–1.11 ms
wall estimate is **not** in this list: see §12.5, finding 5. Launch geometry is
set entirely C++-side in the byte-identical `quantized.cpp`, so it survives.

### 12.3 Byte budget on the new base

`senpai/check-editable-budget.sh 4f3108c4…` against this working tree reports
`current=2902014 headroom=97986 growth=-81835`, i.e. the *base* editable surface
at `4f3108c4` is `2902014 + 81835 = 2983849` bytes — matching the HOLD's
`2983849/3000000`, **headroom 16 151 bytes**. This arm's own editable-surface
delta is small:

| file | 83da91e | 57735c6 | Δ |
|---|---|---|---|
| `fp_quantized_nax.h` | 71 504 | 72 776 | +1 272 |
| `mlx-generated/fp_quantized_nax.cpp` | 74 454 | 75 726 | +1 272 |
| `metal/quantized.cpp` | 84 383 | 84 377 | −6 |
| **total** | | | **+2 538** |

So a rebase onto `4f3108c4` would leave ≈ **13 613 bytes** of headroom. The
budget is tight but is not the binding constraint on this arm. (`research/*`
is not on the editable surface and costs nothing.)

### 12.4 Rule 68

Rule 68 was derived on `_nax` geometry that §12.1 shows is byte-identical on the
new base, so the *kernel-side* premise of the `[Wk;Wv]`-only discriminator is
intact. What changed underneath it is the Swift attention/cache stack, which is
exactly where the `[Wk;Wv]` fusion lives. §11 therefore stays unwritten and the
spare receipt stays suspended until the advisor's audit says whether the fusion
call site still exists in the same form.

### 12.5 The Swift-side "rewrite" is mostly a file re-merge

The HOLD reads the `LagunaRuntimeModel.swift ±9716` / `LagunaRuntimeLayers.swift
−2597` diffstat as a rewrite of the runtime. It is dominated by an
**un-split**: `LagunaRuntimeLayers.swift` carries the header *"split verbatim
out of `LagunaRuntimeModel.swift` so neither file approaches the per-file
submission cap"*, and the frontier move puts it back. Old
`LagunaRuntimeLayers.swift:11-2597` reappears as
`LagunaRuntimeModel.swift:8693-11279` at a constant `+8682` offset with **2
changed lines**, both `let`→`private let` / `func`→`private func` on non-MoE
decode helpers. A multiset comparison of non-blank lines gives old
(`Model`+`Layers`) 11 363 vs new (`Model`) 11 220, with only 240 old-only and 97
new-only lines — and those are dominated by the split-file header comment, the
duplicated `import` block, the added `private` qualifiers, and brace
bookkeeping.

Audited findings on the new base (`Sources/MLXFastModel/LagunaRuntimeModel.swift`
unless noted):

1. **Prefill routed-MoE call site preserved verbatim.**
   `LagunaRuntimeSparseMoEBlock.forward` calls `lagunaFusedSortedRoutedGateUp`
   at `:10859` (definition `:10382`), gated by `x.dim(1) > 1, inds.size >= 64`
   at `:10826-10830`, with the stock `switchMLP(x, inds)` fallback at `:10877`.
   Bank prep `prepareFusedRoutedGateUp()` at `:10523`, invoked once from
   `:11704`. No `MLXLMCommon` file touches MoE.
2. **Still reaches `gather_qmm_rhs`.** `:10420` (gate/up) and `:10450` (down)
   both call `MLX.gatherQuantizedMM(…, transpose: true, groupSize: 16, bits: 4,
   mode: .nvfp4, sortedIndices: doSort)`. All five `gatherQuantizedMM` sites in
   the file are byte-identical to the old base over a ±8/14-line window. No
   custom kernel, segmented GEMM, or `quantized_matmul` substitution.
3. **Shapes and grouping unchanged.** `:10589-10592` builds
   `[experts, 2*split, weightDepth]` with `split = 512`, i.e. gate/up
   `K=2048, N=1024` and down `K=512, N=2048`, matching
   `quantized.cpp:1687-1688`. `gatherSort`/`scatterUnsort` are stock at
   `:10406`/`:10467`; `darkbloom_expert_gather_groups()` is still 256;
   `M = 512 × 8 = 4096`. The `expert_aligned` gate
   (`lagunaExpertAlignedStageEnabled` `:249`, `DARKBLOOM_EXPERT_ALIGNED_GATHER`
   `:255-256`) sits at identical line numbers on both bases, so the shipped
   kernel is still `fp_gather_qmm_rhs_expert_nax` and §3's rung-1 null still
   holds.
4. **GEMM count unchanged** — two dispatches per MoE layer.
   `LagunaRuntimeWeights.swift` (blob `159d896a`), `LagunaLmHeadPrune.swift` and
   `RuntimeWeightLoading.swift` are byte-identical across the move;
   `LagunaConfig.swift` differs only in a doc comment. The two genuinely new
   files, `Sources/MLXFastTransform/AffineMetadataCoding.swift` (+438) and
   `TiedHeadMetadataCoding.swift` (+401), are offline-transform metadata and do
   not add or remove a routed GEMM.
5. **Launch geometry is C++-owned and unchanged.** `quantized.cpp:1966-1970`
   sets `grid_dims(N/bn, egroups, 1)` and `group_dims(32, wn, wm)`;
   `darkbloom_gather_xmajor_ct()` is pinned 0 and the bm128 default 5 gives
   `wm=4, wn=1`, 128 threads/TG. Grid is `16 × 256` (gate/up) and `32 × 256`
   (down). The Swift caller influences only `N`/`K`, which finding 3 shows are
   unchanged, so §4's occupancy-times-geometry arithmetic survives intact.

**What is genuinely new on the Swift side** is decode-only: the
`DARKBLOOM_ROUTER_WEIGHT_PREFETCH` arm (`lagunaRouterWeightPrefetch`) was
removed, a fused residual+RMSNorm+router kernel was added
(`lagunaResidualRMSNormRouterSource`, `rowsPerGroup ∈ {1,2,4,8,16,32,64}`), a
4096-entry RoPE angle atlas was added, and the decode SDPA-vector pair kernel
was rewritten from `float4 outputs4` to a planar `U outputs[4*BN*BDP]` with
2-deep instead of 4-deep pipelining. Together with the `MLXLMCommon` cache and
`Evaluate` rewrite these are exactly the changes that invalidate §12.2's
attribution and cost-model constants — and none of them touch the routed
gather-GEMM this arm edits.

### 12.6 Net position

Of the four things a rebase would have to redo, three are already done: the
kernel patch applies verbatim, the coordinates and the rung-1 null are verified
on `4f3108c4`, and the Step-0 occupancy discriminator is a property of
byte-identical sources. What is missing is a fresh profile on the new runtime to
re-derive the prefill window, the routed-GEMM share of prefill, and the σ/cost
constants — i.e. exactly one contemporaneous baseline receipt, not a redesign.
This is offered as input to the advisor's audit; **no rebase, benchmark, push,
or submission has been attempted, and the arm stays suspended until instructed.**

## Reply

*(The student role receives HTTP 403 from `respond_to_human_issue` and
`get_prs`; this committed section is the reply of record.)*

**On the HOLD (comment `5231841896`).** Acknowledged and complied with. No
receipt was ever spent on this arm, no GPU job was ever launched, no benchmark
was in flight to footnote, and nothing has been pushed. I have not rebased.

**One correction, offered for your audit rather than as a reason to resume.**
"Replaced, not merely advanced" is right for the decode stack and for every
attribution number, but not for the surface this arm edits. All five files it
touches — `fp_quantized_nax.h`/`.cpp`, `steel/gemm/nax.h`, `gemm_nax.cpp`,
`quantized.cpp` — are **byte-identical** between `83da91e` and `4f3108c4`
(§12.1); `git diff --stat 83da91e 4f3108c4 -- Vendor/mlx-swift/` is empty.
`71818038` rewrites them only relative to its own `main`-lineage parent
`e630f1f`; the Maple branch already carried the `cc6ddc1` kernel content, so the
merge is a no-op there. The `LagunaRuntimeModel.swift ±9716` /
`LagunaRuntimeLayers.swift −2597` pair is likewise dominated by an un-split of a
file that had been divided *verbatim* to stay under the per-file cap: the moved
region differs by 2 `private` qualifiers (§12.5), and all five
`gatherQuantizedMM` call sites are byte-identical. So §2's line anchors, §3's
rung-1 structural null, §4's hazard proof and barrier census, and §5's Step-0
occupancy result (`tgMem 9232 → 18448 B`, 7 → 3 TGs/core) all hold on
`4f3108c4` as written.

**What really did go stale** is everything downstream of a profile: the
loader/compute LSU split, the 68 % loader share, the 12.30 ms
`steel_gemm_bf16` pool, the 96.278 ms prefill wall, the ≈54 % routed-GEMM share,
`W = 43.2619 ms`, and the §6 σ/%-per-ms constants (§12.2). Recovering them costs
one contemporaneous baseline receipt, not a redesign.

**Byte budget.** Verified: base surface at `4f3108c4` is 2 983 849 / 3 000 000,
headroom 16 151 B. This arm adds **+2 538 B** (§12.3), leaving ≈13 613 B. Tight
but not binding here.

**Rule 68.** The `_nax` geometry it was derived on is byte-identical (§12.4), so
the kernel-side premise survives; what moved is the Swift attention/cache stack
where the `[Wk;Wv]` fusion lives. §11 stays unwritten and the spare receipt
stays suspended pending your audit.

**Housekeeping.** Commit `b11fe74` tracks eight round-97 A/B evidence logs that
had been sitting untracked in `research/r97-logs/`; two ~1.2 MB profiler stderr
dumps are excluded local-only via `.git/info/exclude`. These are research files
outside `editablePaths` and cost no submission budget. They are unrelated to
this arm and can be dropped from the branch if you would rather keep its diff
clean.

**Waiting on you** for either a revised brief bound to `4f3108c4` or a close. If
you resume the arm, §12.6 is the shortest path; if you would rather spend the
budget on §5.1's half-tile split-K variant directly and skip the full-width arm,
say so and I will switch.

---

*Earlier reply, written before the HOLD, to the `e510bb3d` → `450953e5` move.
Retained for the record; superseded above where the two disagree.*

**On the base move.** Confirmed. `git diff e510bb3d 450953e5` is
`research/CURRENT_RESEARCH_STATE.md | 49 +++--` and nothing else, so the move is
inert for this arm. No rebase was needed and nothing already collected against
`e510bb3d` is discarded.

**On the assignment's line numbers.** They point at `fp_gather_qmm_rhs_nax`,
not the kernel the M5 runs. Corrected in §2; the arm is implemented in
`fp_gather_qmm_rhs_expert_nax` only.

**On rung 1.** It is structurally null and cost zero receipts — see §3. The
`EXPERT_STAGE_*` function constants cannot reach the shipped expert kernel
because `quantized.cpp` only populates `func_consts` on the `!expert_aligned`
branch.

**On your named failure mode.** It has already fired, before any receipt: §5
measures `tgMem 9232 → 18448 B`, i.e. `7 → 3` threadgroups per core and a 57 %
loss of resident simdgroups, with launch geometry and `maxThreads` unchanged.
I did *not* treat that as a reason to cancel the arm — no footprint-neutral
formulation can remove a barrier (§5, point 3) — but I have preregistered that
a null result here is a **resource constraint, not a falsification of H-C**, and
§5.1 already carries the costed half-tile split-K design (10256 B, 6 TGs/core,
bit-exact for the same reason) as the follow-up. If you would rather spend the
budget directly on the half-tile variant and skip the full-width arm, say so and
I will switch; the argument for measuring the full-width arm first is that it is
the only version that tests the barrier count, and §5 point 2 makes its outcome
informative in both directions.
