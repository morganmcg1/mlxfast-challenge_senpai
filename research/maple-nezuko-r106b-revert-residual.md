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
question this section answers, not an assumption it relies on; §C.5 records
which way it went.

## C.3 Measurement scale: why the triage numbers are 8x noisier than the evidence numbers

This subsection is arithmetic on the harness, fixed before the evidence campaign
was read, and it is the mechanical explanation of the noise wall that forced
Amendment 2. It is written out because it is reusable by anyone on this tree who
triages with `--local-iterate` and then reasons in `--local-submit` units.

**The reported decode figure contains a fixed per-run term.** For a single
control run the harness printed, in the same log,

```
mean_step_seconds            = 0.008448
decode_seconds_per_token     = 0.012953    (N = 128 decode steps, --local-iterate)
```

The reported figure is 53 % larger than the mean step it is computed from, so it
is not a mean step time. Fitting `decode_spt = mean_step + K/N` gives
**K = (0.012953 - 0.008448) x 128 = 0.5766 s** of fixed per-run cost folded into
the per-token figure. Predicting the long path from that one fit:

| | mean_step_seconds | N | predicted decode_spt | observed decode_spt |
|---|---|---|---|---|
| `--local-iterate` | 0.008448 | 128 | (fit) 0.012953 | 0.012953 |
| `--local-submit` | 0.008448 | 1023 | **0.009012** | **0.008966** |

The prediction lands within 0.5 % of an independently measured `--local-submit`
run on the same tree, so the model is the right one: one fixed ~0.58 s term,
amortised over however many decode steps the mode runs.

Three consequences, all of which bear on this round's design:

1. **The two modes are not the same scale.** 0.012953 vs 0.008966 s/token is a
   factor of 1.44. An iterate number and a submit number can never appear in the
   same contrast, and a % - of - `cs` conversion calibrated on the submit path
   (this round's 1 us/step = 0.015228 % of `cs`) is simply wrong applied to an
   iterate number. Rule 86 forbids iterate-as-evidence; this is the mechanism
   behind the rule, not merely a convention.

2. **Triage noise is evidence noise multiplied by 1023/128 = 8.** Whatever
   run-to-run variance the fixed term carries is divided by `N`. The three
   interleaved control replicates in the PACKRED triage table gave
   sd = **60.0 us/step** at N = 128, which implies an sd of only **7.7 ms** on the
   fixed term, i.e. **7.5 us/step** at N = 1023. So the 118 us/step
   control-versus-control spread that made Amendment 1's triage gate inoperable
   is an artefact of the short run, not evidence that this host is unstable; the
   evidence path's own sigma is expected near the ledger's fixed-tree
   sigma(ln `cs`) = 0.2276 % ~ 15 us/step, and that is the scale the dof-5
   intervals in C.5 should be read against.

   This is a **falsifiable prediction about this round's own controls**, made
   from triage data before any evidence run was read: the campaign's six
   control replicates should show a standard deviation near **7.5 us/step** if
   the fixed-term model is right, and in any case well under the 60 us/step the
   same host showed at N = 128. If instead the controls scatter by tens of
   microseconds per step, the model is wrong, the host really is unstable at
   the evidence scale too, and every interval in C.5 has to be read as a
   noise-dominated bound rather than a measurement. C.5 reports the outcome.

3. **Amendment 1's abandonment gate was mis-scaled, which is why it was retired
   unexercised.** Its threshold was 2 x 15 us/step - a number taken from the
   evidence-scale ledger - but it was to be applied to iterate-scale
   measurements whose own control noise is 8x larger. No candidate of the size
   this round is chasing could ever have cleared it, so the gate could only ever
   have returned "abandon", regardless of the truth. Amendment 2 replaced it
   with a contemporaneous-control evidence campaign for exactly this reason.

**A stale-score trap, recorded alongside B.6.** `--local-iterate` writes
`score.local-iterate.json`; `--local-submit` writes `score.json`
(`benchmark.sh:138-141`). A script that runs `--local-iterate` and then reads
`score.json` does not fail - it silently reads whatever `--local-submit` left on
disk earlier, possibly hours before and from a different arm. I hit this while
smoke-testing the provenance line: a fresh iterate run appeared to report
0.008966 s/token, which was in fact a 15-hour-old submit score. The triage
runner sidesteps it by parsing the run log rather than the JSON; the evidence
runner deletes `score.json` before every run and treats a missing file as fatal
(non-fatal only for the deliberately incorrect probe arm), so a stale read
cannot enter the paired table.

**A second trap, found in my own instrument while the campaign ran.** The paired
runner lifts the correctness flag with `jq -r '.metrics.passed_correctness //
"NA"'`. jq's `//` alternative operator fires on `false` as well as on `null`, so
a genuine `passed_correctness: false` is written into the table as `NA`. The
correctness column is therefore ambiguous between "the harness said false" and
"the field was absent" — which matters here precisely because one arm is
*required* to say false. Rather than edit the runner mid-campaign (that would
have split the table across two instrument versions), the ambiguity is resolved
after the fact by `research/maple-nezuko-r106b-verify-evidence-rows.sh`, which
re-derives, from each per-run log independently of the JSON, the announced Metal
kernel name, the harness's own `checked timing complete passed=` flag and its own
`decode_seconds_per_token`, and fails if any of the three disagrees with the
table. A table row is admissible only in the combinations `true`/`true` and
`NA`/`false`; a table `NA` paired with a log `true` would mean a control or
candidate run had silently lost its score, and aborts the audit. The audit output
is quoted in F.3.

## C.4 A weakness in the design of record, and the audit that measures it

This subsection is written **after the first block of four runs had landed and
before any of the remaining twenty were read**, so it is a statement about the
design and not a reaction to a result. It is here because it is the design's most
serious flaw and I would rather name it than have a reviewer find it.

Amendment 2 fixes the control at **position 1 of every block** and permutes
K/H/P over positions 2, 3 and 4. That guarantees each candidate a
contemporaneous control, which was the point. But it also means the control is
**never measured at positions 2-4**, so anything systematic in run order —
the host warming across a block, a page cache filling, any monotone drift the
40 °C cool gate does not fully absorb — lands entirely on the candidates and
pushes **every** paired difference in the same direction. A design that pairs a
first-position control against later-position candidates cannot, by itself,
distinguish "the candidate is slower" from "later runs in a block are slower".

The design does make the confound measurable, and that is the redeeming
property. Within the candidate positions, **arm and position are orthogonal**:
each of K, H and P is run exactly twice at each of positions 2, 3 and 4. So

- a position effect can be estimated from the **18 candidate runs alone**, with
  no help from the control and no contamination by arm; and
- an arm contrast adjusted for block and for a linear position trend can be
  fitted over all 24 runs and compared against the preregistered contrast.

`research/maple-nezuko-r106b-position-audit.py` does both, and also reports the
scatter of the six control replicates (the C.3 prediction test) and the interval
half-width the campaign actually achieved. Two rules of reading, fixed here:

1. **The preregistered dof-5 paired contrast remains the result of record.** The
   block + position + arm fit is secondary, was not preregistered, and is
   reported as a diagnostic on the primary — never as a substitute for it.
2. If the position slope is small relative to the paired deltas, the primary
   stands as measured. If it is comparable to them, then the primary's deltas
   are **upper bounds on candidate slowdown** and lower bounds on any candidate
   speedup, and the correct conclusion is that the design, not the candidate,
   is what the campaign measured. Either way the round's verdict is stated in
   those terms rather than silently taking the more flattering number.

A properly balanced design would have run C at every position too — blocks of
four drawn from a Latin square over {C, K, H, P} rather than C-first blocks.
That costs nothing extra in runs and is the design any successor should use on
this harness; it is written into the Stage C notes in §G for that reason.

## C.5 Results

<!-- FILLED FROM /tmp/r106b-packred-evidence.tsv -->

---

# §D — dispatch geometry and the Rule 33 kernel-suffix proof

## D.1 Geometry (Rule 77)

All fields read directly off the dispatch site `lagunaSlidingFusedAttention`,
`LagunaRuntimeModel.swift:2496-2566` (call site `:6743`), with `heads = 64`, `kvHeads = 8`,
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
| threadgroup memory | **18432 B** | **18432 B (unchanged)** | larger (six `head_dim` staging rows instead of four, `4 * BN` score scratch instead of `2 * BN`) |
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
| `lagunaSlidingFusedAttentionKernel` | `laguna_sliding_fused_attn_ring_v1` | none — default | 2052 |
| `lagunaSlidingFusedAttentionPackredKernel` | `laguna_sliding_fused_attn_ring_packred_v1` | `DARKBLOOM_FUSED_SLIDING_ATTN_PACKRED=1` | 2066 |
| `lagunaSlidingFusedAttentionNoReduceKernel` | `laguna_sliding_fused_attn_ring_noreduce_v1` | `DARKBLOOM_FUSED_SLIDING_ATTN_NOREDUCE=1` | 2081 |
| `lagunaSlidingFusedAttentionH4Kernel` | `laguna_sliding_fused_attn_ring_h4_v1` | `DARKBLOOM_FUSED_SLIDING_ATTN_H4=1` | 2095 |

Gates are read once each at lines 1504 / 1514 / 1526 / 1534; the selection ladder
is at 2532-2554 (the H4 early branch at 2532, the NOREDUCE/PACKRED/control
ternary at 2549-2554). Because all four arms are compiled into **one binary** and
chosen at run time, a paired campaign alternates arms *without rebuilding*, so
no arm can be confounded by a differing compile — which is the property that
makes the interleaving in §C meaningful.

**Provenance, not inference.** One binary chosen by environment variable has a
matching failure mode: if the gate name were mistyped, or a stale binary were
executed, the run would fall through to the control and the campaign would
record a paired difference of ~0 under the candidate's label — a fabricated null
that looks exactly like a real one. Arm K is the dangerous case, because it is
identical to the control in geometry (D.1) *and* in output (§F), so nothing
observable distinguishes it. Each of the four kernels above is a lazily
initialised Swift global referenced from exactly one arm of the ladder, so its
one-shot initialiser runs if and only if that arm was taken. Each therefore
announces its own MLX kernel name once, on stderr, at construction:

```
mlxfast: sliding fused attn kernel: laguna_sliding_fused_attn_ring_packred_v1
```

The write is inside the initialiser, never in the decode loop, so it costs
nothing per dispatch and cannot perturb a timed phase
(`lagunaSlidingArmNoted`, line 2046). The evidence runner greps that line out of
every run log, records it in the table's `kernel` column, and **aborts the whole
campaign** on any disagreement with the arm it believes it exported
(`maple-nezuko-r106b-packred-paired.sh`, `expected_kernel` / `observed_kernel`).
Two smoke runs confirmed the discrimination before the campaign started:
unset gates named `laguna_sliding_fused_attn_ring_v1`, and
`DARKBLOOM_FUSED_SLIDING_ATTN_PACKRED=1` named
`laguna_sliding_fused_attn_ring_packred_v1`.

`DARKBLOOM_TRACE_FUSION=1` additionally emits `sliding fused attention` (all
arms) and `sliding fused attention h4` (H4 only), but that path is deliberately
*not* the campaign's provenance evidence: it is off by default and it never
distinguished PACKRED from the control.

---

# §E — surface accounting (Rule 75)

Every number below is printed by `research/maple-nezuko-r106b-surface.sh`, so
this section is reproducible rather than transcribed. It is quoted at commit
**`86539cf9c2b28013f0b21da9b4d542da4022e99e`**, which is the commit the campaign
binary was built from. Commits after it touch `research/` only, so the edited
source's digest below is the digest of the binary that produced every number in
§C.5.

## E.1 Edited-source identity

Exactly **one** file under `Sources/` is touched.

| | `Sources/MLXFastModel/LagunaRuntimeModel.swift` |
|---|---|
| base `446fe9875d1f95b1216628b5809a99da844e5c79` sha256 | `a736b50f66b08b9004a807ff38226aaeb95ba836e6e833b51a8e862466d850c4` |
| base bytes | 384245 |
| candidate `86539cf9` sha256 | `c11c453b6b9e4f3f0bebb1c11e43ee48595314a7000c4eda10412998d6269aed` |
| candidate bytes | **410245** |
| per-file cap | 524288 |
| headroom under the per-file cap | 114043 B (78.2 % of cap used) |
| diff vs base | 627 insertions, 36 deletions, 1 file |

The 26000-byte growth is dominated by three whole extra kernel spellings (the
packed candidate, the refuted H4 variant and the deliberately incorrect probe)
plus the macro headers they select between, all default-off. §C.5's verdict
decides whether any of it is proposed for anyone else's tree; if the verdict is
that none of it is, the bytes are the price of the measurement, not of a
shipped change.

## E.2 Editable-surface budget

`senpai/check-editable-budget.sh 446fe9875d1f95b1216628b5809a99da844e5c79` at the
same commit:

```
editable budget OK: current=2706208/3000000 bytes headroom=293792
growth=26000/262144 files=142 (file count is diagnostic only; base=142)
```

- **current** 2706208 of 3000000 → 293792 B headroom on the whole editable
  surface.
- **growth** 26000 of 262144 → **9.9 %** of the growth allowance consumed, all
  of it in the one file above.
- **files** 142, unchanged from base: no new source file was added. Everything
  new in `research/` is documentation and instrumentation, which the budget
  tool does not count against the editable surface.

---

# §F — correctness

## F.1 What each arm is required to prove

| arm | requirement | why that bar |
|---|---|---|
| C (control) | golden set passes on every run | if the control ever failed, the whole paired table would be measuring a broken tree |
| K (PACKRED) | golden set passes **and** the zero-tolerance upstream-equivalence oracle reports bit-exactness | PACKRED changes the *order* of a floating-point reduction, so it is not exact by construction; it must be shown exact, or it needs frieren's #597 margin certificate before anyone may ship it |
| H (H4) | golden set passes; equivalence oracle run for completeness | H4 changes the reduction tree width as well, same argument |
| P (NOREDUCE) | **required to fail** | P deletes the row-loop cross-lane reduction, so its output is arithmetically wrong by construction. A `passed_correctness = true` from arm P would mean the gate had not been taken and the whole attribution would be void (§D.2). In the table P's flag appears as `NA` for the jq reason in §C.3; the audit script confirms the underlying log said `false` |

Arm P's failure is therefore not a defect in the campaign, it is the campaign's
positive control: it is the only run in the table whose correctness result proves
that a gate-selected kernel swap actually reached the GPU.

## F.2 The bit-exactness question for PACKRED

`simd_shuffle_xor` butterflies are summed in a fixed tree. Packing two rows into a
`float2` and reducing both in the same butterfly does not change *which* partial
sums are added, nor in what order — each component of the packed vector follows
exactly the tree the scalar version followed. The prediction is therefore
bit-exactness, not merely closeness, and the oracle is run at
`MLXFAST_LAGUNA_EQUIVALENCE_MAX_ABS_ERROR=0` so that any deviation at all is a
failure rather than a tolerance question.

## F.3 Results

<!-- FILLED FROM research/maple-nezuko-r106b-packred-exactness.sh -->

## F.4 Golden-set caveat on this host

The public golden tensors were generated on an M5. This host is an M4 Pro, so a
near-tie in an argmax comparison can in principle differ without any code being
wrong. That caveat does **not** apply to the arm P failure reported above,
because the interleaved C and K runs on the same host and in the same session
passed: the host is producing golden-conformant output for every arm whose
arithmetic is unchanged, and only the arm whose arithmetic was deliberately
broken fails.

---

# §G — handoff

## G.1 What is being handed to whom

<!-- FILLED AFTER §C.5 -->

## G.2 The channel problem, stated because it changes what a reader should expect

This round's charge asks for the Stage C handoff comment id on PR #625. I could
not obtain one. The role has **no GitHub write credential**: `gh` is
unauthenticated, there is no `GH_TOKEN` or PAT in the environment, and the
`respond_to_human_issue` tool refuses a pull request ("human messages must use an
issue, not a pull request"). Two channels remain, and both are used:

1. this file and the rest of `research/`, which are pushed on the assignment
   branch and are therefore readable by fern and by the advisor; and
2. the typed `submit_experiment_result` payload, whose summary carries the
   verdict, the labels and the pointers.

So §G's "handoff comment id" is **unavailable, not omitted**. Anything that was
meant to reach #616 or #625 as a comment is instead written here, including:

- the ladder-kill notice: the runaway r104-A ladder job
  `1ad95928-4caa-491d-8964-f560e5fa88f5` is **dead** (exit -15, killed while
  polling for leg 05 after legs 02/03/04 had landed) and no stray processes of
  it remain on this host; and
- the build-load notice: this round ran 24 x `--local-submit` plus 12 triage runs
  plus an equivalence pass on the shared host, roughly two and a half hours of
  continuous GPU occupancy, which is worth knowing for anyone timing an
  integration build in the same window.

## G.3 Stage C proposal (described and costed, NOT implemented): wave quantisation

Amendment 1 §6 proposed `P-ROWLANE` — pushing the packed-reduction idea further
by keeping the row loop's partial sums in lanes. Arm P kills that whole family:
with the row-loop cross-lane reduction **deleted outright** the kernel is not
measurably faster, so no lever that merely makes the reduction cheaper can win
anything. `P-ROWLANE` is withdrawn. What follows replaces it.

**The observation.** Every sliding-attention dispatch launches **32
threadgroups** of 1024 threads onto a **20-GPU-core** M4 Pro. Each threadgroup
asks for 18432 B of threadgroup memory, which is more than half of a core's
32 KiB budget, so two threadgroups cannot co-reside on one core: the dispatch
occupies **one core-slot per threadgroup**, and the wall time of the dispatch is

```
elapsed  =  ceil(nTG / 20)  x  (work per threadgroup)
```

With nTG = 32 that is `ceil(1.6) = 2` slots to do 1.6 slots of work, so **20 % of
the kernel's own elapsed time is cores standing idle in the tail of the second
wave**, not work.

**The model already has one successful out-of-sample prediction.** Substituting
H4's geometry: nTG = 16 threadgroups, each doing twice the work,
`ceil(16/20) = 1` slot x 2t = **2t** — identical to the control's `2 x t = 2t`.
The model therefore predicted H4's measured null *before* being fitted to it,
and it predicts the same null for every power-of-two head split, because
`ceil(64/(20h)) x h` is 2 for h = 1, 2 and 4 alike. That is why §C's H4 arm is not
evidence against the request-side byte-redundancy hypothesis: the geometry it
chose could not have moved the clock whatever the bytes did. Any future
heads-per-threadgroup experiment on this tree will also return null for the same
reason, and should not be run.

**The only geometry that breaks the tie.** The waste vanishes when nTG is an
exact multiple of 20. Writing nTG = (64/h) x s for h query heads per threadgroup
and s splits of the 512-key window, `nTG ≡ 0 (mod 20)` needs `s ≡ 0 (mod 5)`.
The cheapest solution is

| | control | proposal |
|---|---|---|
| query heads per threadgroup | 2 | **8** |
| window splits per head group | 1 | **5** (chunks of 103/103/102/102/102 keys) |
| threadgroups per dispatch | 32 | **40** |
| core-slots used on 20 cores | 2 (for 1.6 of work) | **2 (for 2.0 of work)** |

**The prize, and why it is not a headline.** Removing the idle tail is worth up
to 20 % of the sliding-attention kernel's own time. That kernel is a
**kernel-local** 670 µs/step figure (22.34 µs/call x 30 calls), so 20 % of it is
≈ **134 µs/step**, or ≈ 2.0 % of `cs` if — and only if — kernel time converts
one-for-one into decode step time. Rule 98.9 forbids headlining that: it is an
upper bound on a kernel-local quantity, and this round's own arm P is the standing
warning that a kernel-local saving can convert to exactly nothing. It is offered
as the reason to *run* the experiment, not as a claim.

**The cost, stated honestly.** Five window chunks per head group must be combined
into one softmax result. Two ways:

- *Second dispatch* (flash-decoding style combine). Simple and correct, but
  Rule 65 charges **+2.3403 µs/step per added dispatch**; one combine per
  sliding-attention dispatch is +30 dispatches = **+70.2 µs/step**, which eats
  more than half the prize before anything is measured. Net ≈ +64 µs/step.
- *Single dispatch with a device-memory scratch* and an atomic arrival counter,
  the last threadgroup of each head group performing the combine. No dispatch
  charge, but it needs a scratch buffer, an atomic, and a correctness argument
  about ordering — and it changes the request pattern, so it must be measured
  against a contemporaneous control like everything else here.

**What a Stage C owner should do first.** Confirm the residency premise before
building anything: the whole model rests on one threadgroup per core, which is
inferred from 18432 B against a 32 KiB budget, not measured. If two threadgroups
do co-reside, `nTG/20` is not the right denominator and the prize evaporates. A
counter-based occupancy probe, or simply timing a variant with the threadgroup
memory dropped below 16 KiB, settles it for far less than the cost of the
combine.

## G.4 Two measurement notes any successor on this harness should take

Neither of these is about the sliding kernel; both cost a round to learn.

1. **Use a Latin square, not a control-first block.** This round's blocks put the
   control at position 1 and permuted the candidates over positions 2-4 (§C.1).
   That leaves run-order drift entirely on the candidates and is exactly the
   confound §C.4 had to audit after the fact. Drawing each block of four as a row
   of a Latin square over {control, cand1, cand2, cand3} costs **no extra runs**
   and makes position orthogonal to arm for the control as well, so the paired
   contrast needs no adjustment at all.
2. **Never mix `--local-iterate` and `--local-submit` numbers.** They differ by
   1.44x on this tree, for the mechanical reason derived in §C.3: the reported
   `decode_seconds_per_token` carries a fixed ~0.5766 s per-run term amortised
   over the mode's decode-step count (128 vs 1023). The same arithmetic says a
   triage screen at N = 128 is **8x noisier** than the evidence path, so a gate
   whose threshold was computed on evidence-scale noise can never be cleared by
   triage-scale data. Compute the screen's threshold in the screen's own units,
   or do not screen.
