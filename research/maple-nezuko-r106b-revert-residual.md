# R106-B — revert-residual forensics and Stage B decode mechanism test

Student `maple-nezuko`. PR #616, assignment `maple-r106-b-revert-residual-forensics`,
revision `r106-b-rev3`, research base `446fe987`, campaign
`BASE_SHA = 1bc1c8954147c9e322aad1f3b80bd9fa3c0888d7`.
Host: Apple M4 Pro, 20 GPU cores, 1 GPU.

**Governance up front.** No official submission was made by this assignment;
`senpai/submit-official.sh` was never invoked. **Zero receipts** were consumed.
The #584 receipt ladder stayed cancelled and unrun, and R106-H remains closed
under Rule 79 (W&B run `xuncd3kc`). Every timing number below comes from the
local host.

Sections follow the mandated order §A-§G.

---

# §A — ledger and elimination pass

## A.1 What the assignment asked

R106-B asked whether the revert of the R106 patch left a *residual* on the
frontier — i.e. whether the frontier tree is slower than the pre-patch tree by
more than measurement noise — and, if so, to attribute and recover it.

## A.2 Stage 0 outcome: N-RESIDUAL (already published)

Paired frontier-vs-ArmR contrast, W&B run `d942xnno`, 0 receipts consumed
(full working in `research/maple-nezuko-r106b-revert-residual-forensics.md`):

| quantity | value |
|---|---|
| residual `D` (frontier - Arm R), decode | **+19.405 us/step** |
| pooled sd | 11.920 us/step |
| dof | 10 |
| 95 % CI | **[-18.156, +56.966] us/step** |
| z | +1.151 |
| `T = D - 4P` | +20.149 us/step, CI [-17.877, +58.175] |

Arms: frontier `bd33883eb89209c9714c8c570e399613ecbaa848`
(decode 4913.117 us/step, prefill 187.857 us, T 4161.690, `cs` 2.582286) versus
Arm R `ef055b9b1956e8056267972308fd7deddd89649d`
(decode 4893.712, prefill 188.043, T 4141.541, `cs` 2.589321), 17.47 h apart,
n = 1 per arm. **Both CIs cover zero, so the residual is not resolvable and the
preregistered N-RESIDUAL label fires.**

Two deviations from the assignment's prescribed estimator are on the record:
`submissionCommitSha` grouping yields 1,693 distinct shas and **zero** replicate
groups, so the prescribed sigma is inestimable and content-level `DP-*` pools
were substituted; and `advisor_r103_replicate_sigma.py` digests only `Sources/`
(54 of ~2,300 files), which is why content-level pooling is the tighter
grouping. A NaN-comparison bug in the pooling script was fixed before the
numbers above were produced.

## A.3 Why Stage A is a written elimination pass, not a measurement campaign

The advisor's instruction was explicit: *do not hold the patch for a tidier
ledger*. With the residual demonstrably below the resolvability floor, further
attribution spending cannot change a decision:

* sd(ln `cs` | fixed tree) on this host is **0.2276 %**, i.e. **~15 us/step**,
  so the 3-sigma receipt-resolvability floor is **42.6 us/step**. The measured
  residual (+19.4) is less than half that floor. No affordable number of
  repetitions on the official ladder can separate it from zero, and the ladder is
  not available to this branch in any case (no official submissions).
* sd(ln officialScore) = 0.3728 %, so the lottery channel is dead (Rule 96.2).
* Even if the residual were real and fully recovered, +19.4 us/step is
  **0.295 % of `cs`** — below the gap to the record (record 2.61650354381456 vs
  our best `cs` 2.590559 on tree `4b0e051b`, a gap of ~1.0 %).

Stage A therefore closes as a written pass and the remaining budget goes to
Stage B: find a *mechanism-level* decode win larger than the residual that
survives a preregistered paired test.

## A.4 Elimination pass over the decode dispatch ledger

Families already closed and **not** reopened:

| family | closed by | why it stays closed |
|---|---|---|
| split-K / flash-decoding / KV-split of either decode attention kernel | #196, #566 | measured null-to-negative; both raise the dispatch count, and Rule 65 prices every added dispatch at +2.3403 us |
| threadgroup-boundary splitting for TG-count starvation | #528, rule 67 | raises TG count; measured negative |
| barrier / encoder / command-buffer scheduling | Rule 92 | whole family capped at 1.3003 us/step |
| decode byte reduction by fusion or redundant-read elimination | #619 | ceiling 0.231 % of `cs`, already largely banked |
| quantisation-metadata byte reduction | #615 | closed |
| router weight prefetch | Rule 89.4 | closed |
| cross-TG dedup of phase-1 K RMSNorm+RoPE | prior round | closed |
| second float4 epilogue plane | prior round | closed |
| stream-fragmenting byte reductions | #525, rule 66 | closed |

One family is **narrowly and deliberately reopened**, and I flag it rather than
bury it: "ALU-side levers on M4 — decode is not ALU-bound on this host". That
closure was reached on the projection/matmul kernels, where the question was
arithmetic op count and precision. The *sliding decode-attention* kernel is a
different kernel with a different cost: §C.2 shows it runs at ~10 % of ALU peak
with a 4x-redundant, cache-served request stream, which leaves cross-lane
instruction issue as the live candidate. Whether that candidate is real is the
question §C tests, not a premise it assumes. The reopening is therefore scoped to
"cross-lane reduction instruction count in `laguna_sliding_fused_attn_ring_v1`"
and to nothing else.

Deconfliction against live channels: frieren #597 owns bit-exactness and the
margin-certificate instrument; fern #625 owns the integration tree; tanjiro #620
owns prefill; edward #629's L3 patch touches `lagunaDecodeNVFP4QKVLaneMajorSource`
(the QKV projection kernel) and therefore does **not** overlap the attention
kernel this branch edits; alphonse #630 owns the routed K-loop (a wash).

What survived the pass was the sliding decode-attention kernel: 22.34 us/call x
30 calls = **670 us/step**, 8 MiB requested per call against 2 MiB unique, and
0.75 TFLOP/s = ~10 % of this host's ~7.2 TFLOP/s peak. Stage B attacked it
twice: first on the request side (H4), then, after H4 refuted the request-side
premise, on the instruction side (PACKRED).

---

# §B — the patch

Single file: `Sources/MLXFastModel/LagunaRuntimeModel.swift`.

## B.1 Structural change: reductions factored behind header macros

The shipped kernel `laguna_sliding_fused_attn_ring_v1` performs 44 cross-lane
reductions per lane per call (32 `simd_sum` in the row loop, 2 `simd_max` +
2 `simd_sum` + 8 `simd_sum` in the online-softmax epilogue). Those call sites
are replaced by four macros — `LAGUNA_QK_REDUCE2`, `LAGUNA_MAX_REDUCE2`,
`LAGUNA_SUM_REDUCE2`, `LAGUNA_ACC_REDUCE4` — and the Metal source string and the
common header are hoisted into `lagunaSlidingFusedAttnRingSource` and
`lagunaSlidingFusedAttnRingHeaderCommon`. Each kernel spelling then supplies its
own macro definitions through the `header:` argument, so **every arm compiles
from one source string** and the arms cannot drift apart.

The control spelling's macros expand to exactly the `simd_sum`/`simd_max` code
that shipped, so the refactor is behaviour-preserving by construction; §F
records the zero-tolerance oracle run that confirms it.

## B.2 Arms registered

| Swift binding | Metal name | gate | default |
|---|---|---|---|
| `lagunaSlidingFusedAttentionKernel` | `laguna_sliding_fused_attn_ring_v1` | none (control) | active |
| `lagunaSlidingFusedAttentionPackredKernel` | `laguna_sliding_fused_attn_ring_packred_v1` | `DARKBLOOM_FUSED_SLIDING_ATTN_PACKRED=1` | off |
| `lagunaSlidingFusedAttentionH4Kernel` | `laguna_sliding_fused_attn_ring_h4_v1` | `DARKBLOOM_FUSED_SLIDING_ATTN_H4=1` | off |

All gates default to off/control, so one binary serves every arm of a paired
campaign and no arm can be confounded by a rebuild.

## B.3 PACKRED, the Stage B candidate

Each reduction site in the kernel reduces two or four scalars at the same
program point, so the 5-step butterfly can be shared:

| site | reductions | shuffles (control) | shuffles (PACKRED) |
|---|---|---|---|
| row loop, 16 rows x 2 heads, 4 unrolled slots x 4 iterations | 32 x `simd_sum` | 160 | 80 (`float2`) |
| epilogue output planes | 8 x `simd_sum` | 40 | 10 (`float4` per head) |
| epilogue max and softmax sums | 2 x `simd_max`, 2 x `simd_sum` | 20 | 10 (`float2` each) |
| prologue RMSNorm + RoPE (untouched) | 1 `simd_sum` + 4 `simd_shuffle` | 9 | 9 |
| **total** | | **229** | **109** |

The adds are unchanged in count; only the shuffle traffic is shared.
`simd_max` packing is exact because `max` does no rounding; `simd_sum` packing
uses an ascending-mask (1, 2, 4, 8, 16) xor butterfly, which is the standard
lowering, but the vendor's `simd_sum` association is unspecified, so exactness
was declared in advance to be an empirical question (§F).

Device memory traffic, grid, threadgroup size, threadgroup memory and the
dispatch count are all **unchanged** (§D), so Rule 65's +2.3403 us/dispatch does
not apply.

## B.4 The H4 arm (measured, retained only as evidence)

`laguna_sliding_fused_attn_ring_h4_v1` packs 4 query heads that share one KV
head into a single threadgroup instead of 2, halving threadgroups from 32 to 16
and requested KV bytes per call from 8 MiB to 4 MiB against 2 MiB unique. Its
per-head arithmetic and row-to-simdgroup mapping are unchanged.

## B.5 Diagnostic probe (attribution instrument, not a candidate)

`laguna_sliding_fused_attn_ring_noreduce_v1`, gate
`DARKBLOOM_FUSED_SLIDING_ATTN_NOREDUCE=1`, deletes the row-loop cross-lane
reduction and uses each lane's 4-dimension partial dot product as if it were the
whole one, leaving every load, FMA, barrier and the whole epilogue in place. It
therefore produces **numerically wrong attention output by design**, was
declared as such in Amendment 1 section 5 before it was run, is used only under
`--local-iterate`, and is never a submission candidate.

## B.6 A self-inflicted build break, recorded because it is a reusable trap

The refactor in B.1 initially **broke the JIT build of every arm, the control
included**, and the triage that ran against it was worthless. It is recorded
here rather than quietly fixed, because the failure mode is invisible by
inspection and any future header split will hit it.

Swift multi-line string literals do **not** end with a newline. Splitting
`header:` into `…HeaderCommon + …ReduceBaseline` therefore produced a header
whose final characters were `} while (false)`, and MLX appends the generated
`[[kernel]] void …(…)` signature directly after it — onto that same line. The
diagnostics were:

```
mlx/backend/metal/kernels/utils.h:525: error: 'buffer' attribute only applies to parameters
mlx/backend/metal/kernels/utils.h:525: error: program scope variable must reside in constant address space
Fatal error: [metal::Device] Unable to build metal library from source
```

Both messages point at a *vendored* header, which is misleading: the tell is
that `Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/kernels/utils.h` is
**445 lines long**, so "line 525" is 80 lines past its end — the reported file is
the concatenated translation unit, not the file on disk, and 525 − 445 = 80
lands exactly on the last line of the spliced header. The two errors are then
precisely what a kernel signature parsed at program scope looks like:
`[[buffer(n)]]` attached to something that is not a parameter, and
`device`-qualified declarations outside a function.

Fix: follow the convention already present in this file at
`LagunaRuntimeModel.swift:8473`, which concatenates with an explicit separator
(`lagunaSharedSwiGLUQMVHeader + "\n" + lagunaDecodeRouterOrdinalHeader`), and
additionally leave each macro block newline-terminated in its own right so the
splice is safe from either side. Commit `82db365e`.

Two hygiene consequences that are load-bearing for the rest of this report:

1. **Every number below post-dates `82db365e`.** No measurement taken against
   the broken tree is quoted anywhere, not even as a bound.
2. The break was caught only because the control arm was interleaved and *also*
   failed (`decode=0`, `passed=false` for both C and K). A candidate-only triage
   would have reported "candidate does not build", moved on, and left the
   control silently broken for the paired campaign. That is an argument for
   Rule 68's contemporaneous control as a **build** check and not only as a
   timing control.

---

# §C — the paired A/B

## C.1 Design of record (Amendment 2), fixed before the first evidence run

Full text in `research/maple-nezuko-r106b-stageb-amendment2.md`. Summary:

| item | value |
|---|---|
| design | control-anchored, position-balanced block design |
| block | 4 runs: `C` first, then a permutation of `K`, `H`, `P` |
| blocks | 6, order `C K P H \| C P H K \| C H K P \| C K H P \| C P K H \| C H P K` |
| pairing | every candidate run differences against the `C` run of **its own block** |
| declared dof | **5** per contrast; `t(0.975, 5) = 2.5706` |
| evidence path | `./benchmark.sh --local-submit`, 1023 decode steps |
| primary metric | `decode_us_per_step`, converted at 0.015228 % of `cs` per us/step |
| stopping | none: all 24 runs execute; no arm dropped mid-campaign |
| runner | `research/maple-nezuko-r106b-packred-paired.sh` |

Three properties of this design are load-bearing and each answers a specific
way the round-103 measurements went wrong.

1. **The control is interleaved, not borrowed.** Every difference is against a
   control run measured minutes away on the same binary, same weights, same
   thermal state. Stage 0's residual was a contrast between two runs 17.47 hours
   apart with n = 1 per arm, which is exactly why its CI was 75 us/step wide.
2. **Position inside the block is balanced.** Each of `K`, `H`, `P` occupies
   block positions 2, 3 and 4 exactly twice across the six blocks, so a monotone
   within-block drift (thermal soak, page-cache warming) cannot be mistaken for
   an arm effect. The block-difference estimator removes any per-block additive
   offset exactly; the position balance removes the first-order within-block
   trend.
3. **One binary, gate-selected.** All four arms are separate Metal kernel names
   in one build (§D.2), so alternating arms costs no rebuild and no arm can be
   confounded by a differing compile.

**Why the design was upgraded.** Amendment 1 allowed me to close on a cheap
`--local-iterate` gate. I retired that gate unexercised because its threshold
(2 x 15 us/step) is smaller than the realised control-vs-control spread of the
instrument in this session (118 us/step between two runs of the *same* binary
with all gates unset). Under Rule 86 no `--local-iterate` number appears in any
conclusion here; the two control runs are quoted in Amendment 2 as evidence
about the instrument, which is the only role triage may play. The deviation costs
~100 minutes of otherwise idle host time and buys an evidence-grade answer for
all three contrasts, including the H4 arm that had previously been refuted on
triage alone.

## C.2 What the candidate is supposed to move, stated before the numbers

The sliding decode-attention kernel costs 22.34 us/call x 30 calls =
**670 us/step**, i.e. 10.2 % of `cs` — 35x the residual under investigation, so
it is the right place to look even though the residual itself is unresolvable.
Two independent counts say it is not limited by the thing a kernel of this shape
is usually limited by:

* **Arithmetic:** ~0.75 TFLOP/s against this host's ~7.2 TFLOP/s peak, i.e.
  ~10 % of peak. Not ALU-throughput-bound.
* **Bandwidth:** 8 MiB requested per call against 2 MiB unique, a request rate of
  ~375 GB/s against ~273 GB/s of DRAM. The 4x redundancy is therefore
  cache-served, and under Rule 98.9 that cache-resident figure is **not** quoted
  as a saving anywhere in this report.

What is left is instruction issue, and the kernel issues **229 cross-lane
shuffle/lane-read operations per lane per call** (§B.3). PACKRED halves that to
109 without changing a single load, store, FMA, barrier, or the dispatch
geometry (§D.1). So the campaign is a clean single-variable test of one
proposition:

> **Is the sliding decode-attention kernel's cost sensitive to cross-lane
> reduction instruction count on this host?**

`K` answers it for a *correct* halving. `P` answers the stronger question by
deleting the row-loop reduction outright and accepting wrong output: `-D_P`
bounds what **any** lever targeting that reduction could ever recover, PACKRED
and the Stage C `P-ROWLANE` proposal included. The forward reference in §A.4 to
"direct evidence that the kernel is instruction-issue-bound" is therefore a
question this section answers, not an assumption it relies on; §C.3 records
which way it went.

---

# §D — dispatch geometry and the Rule 33 kernel-suffix proof

## D.1 Geometry (Rule 77)

All fields read directly off the dispatch site `lagunaSlidingFusedAttention`,
`LagunaRuntimeModel.swift:2479-2548`, with `heads = 64`, `kvHeads = 8`,
`headDim = 128`, `window = 512`.

| quantity | C (control) | K (PACKRED) | H4 (refuted) |
|---|---|---|---|
| Metal kernel name | `laguna_sliding_fused_attn_ring_v1` | `laguna_sliding_fused_attn_ring_packred_v1` | `laguna_sliding_fused_attn_ring_h4_v1` |
| `grid` | `((heads / 2) * 1024, 1, 1)` = **(32768, 1, 1)** | **(32768, 1, 1)** | `((heads / 4) * 1024, 1, 1)` = (16384, 1, 1) |
| `threadGroup` | **(1024, 1, 1)** | **(1024, 1, 1)** | (1024, 1, 1) |
| threadgroups per dispatch | **32** | **32** | 16 |
| simdgroups per threadgroup | 32 | 32 | 32 |
| query heads per threadgroup | 2 | 2 | 4 |
| `outputShapes` | `[[1, 64, 1, 128]]` | `[[1, 64, 1, 128]]` | `[[1, 64, 1, 128]]` |
| `outputDTypes` | `.bfloat16` | `.bfloat16` | `.bfloat16` |
| threadgroup memory | unchanged | **unchanged** | unchanged |
| dispatches per decode step | 30 | **30** | 30 |
| KV bytes requested per call | 8 MiB (2 MiB unique) | **8 MiB (2 MiB unique)** | 4 MiB (2 MiB unique) |

**C and K are geometrically identical in every field.** The PACKRED change is
confined to the *instruction stream* at the reduction sites. Two consequences,
stated because they are the usual confounders for a small decode effect:

- Rule 65's **+2.3403 µs per added dispatch** cannot be any part of a C-vs-K
  difference: the dispatch count is identical at 30 per step.
- Rule 92's schedulable-slack family (408 dispatches / 247 charged barriers /
  47 command buffers, 1.3003 µs/step of total headroom) is untouched, since no
  barrier or command-buffer boundary moves.

The H4 arm is tabulated only because it was measured and refuted (§C.1). It
*does* change geometry, which is why its null is reported against its own
interleaved control rather than against K's.

## D.2 Rule 33 kernel-suffix proof

Each arm is a **distinct Metal kernel name**, not a recompilation of one name,
so the binary that ran is identifiable from the artifact instead of inferred
from the environment:

| Swift binding | Metal name | selection gate | decl line |
|---|---|---|---|
| `lagunaSlidingFusedAttentionKernel` | `laguna_sliding_fused_attn_ring_v1` | none — default | 2037 |
| `lagunaSlidingFusedAttentionPackredKernel` | `laguna_sliding_fused_attn_ring_packred_v1` | `DARKBLOOM_FUSED_SLIDING_ATTN_PACKRED=1` | 2051 |
| `lagunaSlidingFusedAttentionNoReduceKernel` | `laguna_sliding_fused_attn_ring_noreduce_v1` | `DARKBLOOM_FUSED_SLIDING_ATTN_NOREDUCE=1` | 2065 |
| `lagunaSlidingFusedAttentionH4Kernel` | `laguna_sliding_fused_attn_ring_h4_v1` | `DARKBLOOM_FUSED_SLIDING_ATTN_H4=1` | 2079 |

Gates are read once each at lines 1505 / 1515 / 1527 / 1535; the selection ladder
is at 2515-2537. Because all four arms are compiled into **one binary** and
chosen at run time, a paired campaign alternates arms *without rebuilding*, so
no arm can be confounded by a differing compile — which is the property that
makes the interleaving in §C meaningful. `DARKBLOOM_TRACE_FUSION=1` additionally
emits `sliding fused attention` (all arms) and `sliding fused attention h4`
(H4 only), so the taken path is visible in the run log.

