# Laguna XS 2.1 optimization campaign brief

This is a decision document for starting optimization work from the public
frontier without becoming trapped by it. It synthesizes the live MLX Fast
leaderboard, the complete public notes attached to every promoted submission,
and the corresponding promoted source snapshots in Git.

> **Snapshot.** 2026-08-02 at 09:07:21 UTC. The public feed contained 1,068
> attempts and 126 leaderboard successes from 30 solvers. The latest
> promoted source was submission
> [`05e7894f`](https://mlx.fast/api/submissions/05e7894f-0eaf-4f6d-8622-499d1e44185d),
> commit
> [`7702fab`](https://github.com/Layr-Labs/mlxfast-challenge/commit/7702fab8a41fe2f4ff2ae281beeb1548b31e3406),
> with score **2.4549506**. The board is live; refresh the public feed before
> acting on this snapshot.
>
> **Final recheck.** At 09:21:49 UTC the feed had grown to 1,070 attempts, but
> the success set was unchanged at 126 and `upstream/main` still resolved to
> `7702fab`. The two new records were not leaderboard promotions.

Companion material:

- [Exhaustive 126-submission promotion ledger](leaderboard_promotions_2026-08-02.md)
- [Live leaderboard](https://mlx.fast/)
- [Public submission feed](https://mlx.fast/api/benchmarks/1854efdf-feba-4773-bae9-b80520881a74/submissions)

## Executive take

The public score rose from **1.004 to 2.455** in 126 promotions. Comparing the
first and latest promoted candidate measurements, decode fell from 13.568 to
5.249 ms/token (**61.3% lower**) and prefill from 0.3822 to 0.1957 ms/token
(**48.8% lower**). Those endpoint measurements came from different sessions,
so they are historical scale indicators rather than a controlled A/B. The
latest same-session paired result reports **2.6466x decode** and **1.9593x
prefill** speedup.

There was no single winning trick. The frontier is the compound result of five
repeated patterns:

1. **Read fewer bytes.** Attention weights moved from BF16 to affine INT8 and
   finally back to the checkpoint's still-smaller native NVFP4 representation;
   the vocabulary head gained a certified coarse screen; repeated affine
   metadata was indexed rather than reread.
2. **Remove work that provably cannot affect an output.** Prefill expert runs
   and causal attention blocks were skipped only where their stores were
   already discarded; exact LM-head bounds avoid most full vocabulary dot
   products.
3. **Collapse dependency stages, not merely dispatch counts.** Successful
   fusion eliminated materialization or a serialized barrier window. Fusion
   that duplicated a producer or increased live state often lost.
4. **Expose enough independent work to the M5.** One-row-per-SIMD retile,
   expert-group schedules, four-SIMD regrouping, command-buffer sizing, and
   early `asyncEval` rungs improved latency hiding and CPU/GPU overlap.
5. **Move one-time work out of scored windows.** Weights, side layouts, kernel
   pipelines, wired residency, and even the greedy `argmax` pipeline are
   prepared during untimed initialization.

The most important campaign implication is simple: **start from the current
promoted tree**. Reimplementing any isolated July mechanism would usually be a
regression because later submissions already composed, superseded, or
deliberately disabled it.

## How to interpret the evidence

A promotion proves that one complete source snapshot passed the hard gates and
beat its promotion comparator. It does **not** prove every item in a bundled
submission was independently beneficial. Public notes are detailed and useful,
but they are author claims. This brief uses four evidence levels:

| level | meaning | how to use it |
|---|---|---|
| **A — current and isolated** | Active in the latest source and supported by a narrow promotion, same-binary selector, or independent official absolute timing | Treat as established until the frontier changes its multiplicity or dependencies |
| **B — current bundle** | Active in the latest source and included in a promoted compound tree, but marginal value is not fully isolated | Preserve by default; ablate before attributing a new result |
| **C — historical promotion** | Promoted at one point but later superseded, restored, or switched off | Keep the lesson, not necessarily the old implementation |
| **D — hypothesis/negative** | Local evidence, an author interpretation, or an accepted/rejected absolute result without promotion | Use to choose experiments, never as a starting invariant |

The Git branch is a sequence of candidate snapshots. Adjacent commits can be
full-tree overlays and can include restorations or reversions. An immediate
`git diff HEAD^` is therefore not a reliable causal account. Compare promoted
snapshots, read the attached note, and inspect the active defaults together.

## Where successful work landed

The successful history is much more concentrated than the 97-path editable
surface suggests. Counting files touched by each promoted public commit gives
this source-level map:

| surface | promotions touching it | campaign implication |
|---|---:|---|
| `LagunaRuntimeModel.swift` | 98 / 126 | The main optimization battlefield: dispatch, scheduling, fusion, attention, MoE, and runtime shape decisions |
| Any vendored `mlx-swift` kernel source | 44 / 126 | Kernel work mattered, but 82 promotions won without entering the low-level kernel surface |
| `LagunaLmHeadPrune.swift` | 20 / 126 | A focused, exact pruning subcampaign produced a durable family of wins |
| Metal `quantized.cpp` dispatch | 18 / 126 | Host-side geometry and kernel selection were nearly as important as inner-loop edits |
| NAX `fp_quantized` JIT/AOT pair | 14 each | M5-specific QMV/gather work required editing both runtime-effective and source twins |
| Plain `fp_quantized` JIT/AOT pair | 12 each | Non-NAX twins still had to remain coherent and buildable |
| Runtime weight preparation | 10 / 126 | Side layouts, packing, residency, and eager materialization were meaningful enablers |
| `sdpa_vector.h` | 8 / 126 | A small number of attention-kernel changes produced several high-quality wins |
| NAX Steel-attention JIT/AOT pair | 8 each | Prefill attention had a narrower but real optimization line |
| `Sources/MLXFastTransform/` | **0 / 126** | No promotion needed an offline-transform innovation; treat this as open space, not proof that it cannot help |

These are touch counts, not causal contribution estimates: overlay commits may
restore or replace neighboring work. Still, they are a useful search prior.
Start in the scored runtime and its quantized dispatch path unless a fresh
trace gives a concrete reason to invest elsewhere.

## What the current frontier actually does

The following is the point-in-time active stack at commit `7702fab`. Some
older arms remain compiled behind environment selectors; presence in the file
does not mean they are selected.

| phase/surface | active frontier behavior | provenance and interpretation |
|---|---|---|
| Attention weight representation | All 40 decode Q/K/V and output-projection side banks use the checkpoint's group-16 NVFP4 representation (`DARKBLOOM_NATIVE_AFFINE_NVFP4_FROM=0`). The per-head gate remains accepted group-32 affine INT8. | The suffix widened 32→24→17→0 in [`8449082c`](https://mlx.fast/api/submissions/8449082c-4dc2-4526-b3bd-69712c3b8a8e), [`df2a7483`](https://mlx.fast/api/submissions/df2a7483-9c5b-4f4c-8a2f-9fee780515d7), and [`db173215`](https://mlx.fast/api/submissions/db173215-a7d7-4863-a333-8132c33be279). This is now the largest landed byte cut. |
| Attention projection schedule | The large fused RMSNorm+NVFP4-QKV+INT8-gate kernel is retained but **default off**. Stock RMSNorm computes one normalized row, followed by separate QKV and gate projections. | [`a0da915f`](https://mlx.fast/api/submissions/a0da915f-450a-4063-bf8e-ec1661f4a661) showed that the fused kernel repeated a 2,048-wide RMS reduction in every output tile after it became active in all 40 layers. Un-fusing was faster. |
| Attention and KV | Sliding- and full-attention fused decode paths are default on. They combine Q/K normalization and RoPE, exact cache writes, cache advancement, and GQA-paired attention while retaining accepted arithmetic order. | Sliding isolation promoted in [`44076af3`](https://mlx.fast/api/submissions/44076af3-97de-4fed-bc86-acaf914eab6d); later compound snapshots restored the full twin. Treat each path separately in future A/Bs. |
| Decode scheduling | `asyncEval` fires after layers 1, 7, 15, 23, 31, and 39, with an additional layer-0 projection-ready enqueue. | The ladder was established by [`6dd236c2`](https://mlx.fast/api/submissions/6dd236c2-9d28-4f19-b51d-d88bdccafcf2); the layer-0 rung was composed with aligned affine code loads in [`4173c401`](https://mlx.fast/api/submissions/4173c401-0f25-41fd-bec7-cdea22a1aac3). |
| Sparse MoE decode | Router keys/ordinals are exact and precomputed where possible; routed and shared gate/up QMVs are separately schedulable; packed scale banks reduce metadata traffic; the down/reduce/shared/residual path is fused and uses the M5-positive one-row-per-SIMD ownership. | The fundamental down fusion came from [`5bb15364`](https://mlx.fast/api/submissions/5bb15364-25c8-4d16-8d67-d2fb3b211404); the latest R1 retile is [`05e7894f`](https://mlx.fast/api/submissions/05e7894f-0eaf-4f6d-8622-499d1e44185d). |
| Router | Exact ordinal payloads and a score table avoid repeated comparison work. Top-8 selection is also computed inside the routed QMV prologue so that the large routed QMV can share the top-8 barrier window. | [`3223e19d`](https://mlx.fast/api/submissions/3223e19d-8e7a-4001-a2c8-0176900a7005) is the clearest dependency-window explanation. The standalone selector still supplies later consumers. |
| Vocabulary head | Certified pruning is default on for decode and prefill. The current screen is a planar int5 coarse copy with ratio/error bounds, BF16 delta and midpoint thresholds, inline candidate masks, and an exact BF16 tail. | The byte cut landed in [`f03984b6`](https://mlx.fast/api/submissions/f03984b6-98bb-4a79-99d1-8248c214faa1); exact bound tightening continued in [`197572a3`](https://mlx.fast/api/submissions/197572a3-616c-43f3-a99e-cfafd653ea0c) and later promotions. It prunes work, not vocabulary behavior. |
| Prefill MoE | Run/fragment skipping, expert-aligned gathering, fused sorted gate/up, WN1 gather tiling, widened staging, fused split-K, router tournament, and residual/RMS fusions are active. | The pivotal work-elision promotion is [`404b2f50`](https://mlx.fast/api/submissions/404b2f50-1b56-4c59-afed-31ecd7180448). Later promotions changed tiling and staging rather than the mathematical result. |
| Prefill attention/epilogue | One-head-per-threadgroup QK norm/RoPE, final-layer concatenated projection banks, terminal-row-only query work, and an `asyncEval` stride-1 ladder reduce work and overlap graph construction. | The projection-bank composition is [`493f1ee1`](https://mlx.fast/api/submissions/493f1ee1-38d8-4152-86a4-d8489d082727); later terminal-row work is recorded in the ledger. |
| Initialization/runtime | Weights and derived banks are eagerly materialized and wired; command buffers default to 200 MiB/200 ops; hot pipelines are warmed; greedy argmax is explicitly run during warmup. | Full residency and command-buffer tuning were staged earlier. [`e885776f`](https://mlx.fast/api/submissions/e885776f-6af6-4f77-9c48-90fc7ca7fb49) moved an observed ~17 ms per-worker argmax compilation out of both scored windows. |

This active-stack table should become a checked manifest before our first
optimization. A new promotion can overwrite an orthogonal mechanism while
still scoring much higher; [`9847ff8f`](https://mlx.fast/api/submissions/9847ff8f-918e-4988-ba2f-a1137d23784b)
explicitly demonstrated that frontier state is replaceable, not cumulative by
guarantee.

## The major wins and why they worked

### 1. Attention bytes were the largest decode lever

The competition first replaced BF16 attention projections with group-32
affine INT8 side layouts. QKV batching was rolled out in chunks beginning with
[`724f8e52`](https://mlx.fast/api/submissions/724f8e52-38ff-44b8-a3e9-40b4de5c6805),
and output projection INT8 began with
[`8afa9316`](https://mlx.fast/api/submissions/8afa9316-a9db-40aa-bf99-508801c31faf).
This worked because one-token decode repeatedly streams projection weights and
is predominantly bandwidth-bound; retaining BF16 for prefill avoided moving a
different regime onto a slower kernel.

The deeper insight came later: affine INT8 was smaller than BF16, but the
checkpoint's native NVFP4 was smaller again. The accepted INT8 side layout is
about 1.125 bytes/parameter; native NVFP4 group-16 is about 0.5625. Moving all
attention layers back to the original representation roughly halved that
traffic. The three widening promotions took the score from 2.124 to 2.370.

Lessons:

- Compare every new representation to the **best legal existing
  representation**, not only to the original BF16 baseline.
- Representation boundaries can flip near-tie argmaxes non-monotonically.
  Boundary 17 passed while 18 and 19 failed locally. Test each boundary; do not
  assume more approximation means monotonic correctness loss.
- The all-NVFP4 endpoint is numerically closer to the checkpoint oracle than
  the mixed re-quantized regime, which helped both bandwidth and the exactness
  argument.
- This byte lever is now at its legal representation floor. Further attention
  work must attack scheduling, metadata, or duplicated computation unless the
  benchmark contract changes.

### 2. Certified LM-head pruning converted a huge exact GEMV into a small screen

The vocabulary head has 100,352 output rows. The successful family computes a
coarse score plus a conservative error certificate, then performs the exact
BF16 dot product only for rows that can still beat the winner. Refinements
reduced coarse bytes (MXFP8 → planar int6 → planar int5), tightened the bound,
compressed or broadcast candidate masks, and fused threshold reductions.

Why it worked:

- The optimization is exact by construction: a row is omitted only when a
  proved upper bound cannot win.
- The coarse pass is bandwidth-bound, so planar byte reductions translate
  directly to step latency.
- The exact tail often contains only a handful of candidates, so the expensive
  full-precision work scales with ambiguity rather than vocabulary size.

What not to infer: a coarser screen is not automatically better. One int4
experiment produced a prompt-dependent candidate tail and lost ranked time.
Future LM-head work should improve a certificate or reduce bytes while
measuring the full candidate-density distribution, not only average kernel
throughput.

### 3. MoE wins came from eliminating materialization and fixing ownership geometry

The routed/shared down fusion performs eight expert NVFP4 QMVs, router weighting
in slot order, shared-expert combination, scaling, and residual addition in one
kernel. It removes the 8×2,048 intermediate expert-output surface and several
separate operations while preserving every BF16 rounding boundary. That narrow
mechanism promoted at roughly +3.6% in
[`5bb15364`](https://mlx.fast/api/submissions/5bb15364-25c8-4d16-8d67-d2fb3b211404).

Later gains were about GPU ownership rather than FLOPs. R1 layouts assign one
output row to each SIMDgroup, increasing independent streams and reducing live
accumulators. The sign is hardware- and frontier-specific: the latest R1 down
retile is about 12% slower on its author's local Apple GPU yet approximately
0.4% better on isolated official M5 absolutes and promoted in
[`05e7894f`](https://mlx.fast/api/submissions/05e7894f-0eaf-4f6d-8622-499d1e44185d).

The router/top-8 work reinforces a second rule: deleting a dispatch is less
important than deleting a dependency window. Earlier inline top-8 attempts
still left the routed QMV waiting and lost. The successful prologue lets the
routed QMV start in parallel with the standalone selector, so one serialized
window disappears per sparse layer.

### 4. Exact prefill work elision was more valuable than speculative tiling

The NAX gather-GEMM originally computed complete tiles for expert runs even
when its store discarded every row outside the relevant band. RUNSKIP and
later fragment/band refinements avoid exactly that dead arithmetic. The first
narrow implementation promoted at roughly +5% score in
[`404b2f50`](https://mlx.fast/api/submissions/404b2f50-1b56-4c59-afed-31ecd7180448).

Later prefill work improved expert grouping, WN1 tiling, staging widths,
split-K replay, and terminal-row epilogues. The common property is that the
successful changes preserve row-level arithmetic and target a measured
dispatch, staging, or occupancy floor.

One important correction came from this family: an inherited estimate said
gather-GEMM was ~70% of prefill, but direct measurement put it near 15% at that
frontier. A percentage derived by subtraction had absorbed every unknown cost.
Budget shares must come from traces or discriminating experiments, not from a
remainder in a spreadsheet.

### 5. Attention/kernel shape mattered more than the number of launches

Several durable examples:

- SDPA paired adjacent GQA query heads so they share K/V reads while retaining
  independent accumulators
  ([`adf12cb1`](https://mlx.fast/api/submissions/adf12cb1-7176-4bea-a9c6-bd44ea031255)).
- A wider output-transpose exchange plane reduced eight 1,024-thread barriers
  to one without changing producer/consumer pairing
  ([`09d52bc1`](https://mlx.fast/api/submissions/09d52bc1-35b2-4ba2-be9e-bbc3b526a394)).
- QK norm/RoPE fusion first lost because it added a redundant synchronization;
  removing that barrier turned the same broad idea positive.
- NAX QK `unroll_count(4)` improved load/MMA scheduling without changing the
  serial accumulation chain
  ([`1077625a`](https://mlx.fast/api/submissions/1077625a-6ae4-4640-9b93-122029972df3)).
- The all-layer norm/QKV/gate fusion eventually lost because every consumer
  tile recomputed the same RMSNorm. Turning the fusion off in
  [`a0da915f`](https://mlx.fast/api/submissions/a0da915f-450a-4063-bf8e-ec1661f4a661)
  produced one of the largest late-stage jumps.

The general rule is: **fusion pays when it removes a materialized boundary or
a dependency stage without multiplying producer work or resource pressure.**
Count launches only after accounting for duplicated reductions, threadgroup
barriers, register allocation, occupancy, and input rereads.

### 6. CPU/GPU overlap, residency, and warmup compounded the kernel work

The decode graph is built in Swift while Metal executes. `asyncEval` rungs
enqueue completed graph segments early so construction and GPU execution
overlap. A stride sweep showed a U-shaped optimum: too few rungs leave CPU
work exposed; too many pay scheduler overhead. This family moved from one
tail rung to a streaming ladder and later added a layer-0 projection-ready
enqueue.

Wired residency removed repeated driver residency work for the ~21.6 GB model.
Command-buffer limits were retuned **after** the cost structure changed and now
default to 200 MiB/200 ops. The useful lesson is temporal: an old command-buffer
experiment that lost can become positive after residency or fusion changes the
layer boundary.

Finally, [`e885776f`](https://mlx.fast/api/submissions/e885776f-6af6-4f77-9c48-90fc7ca7fb49)
used Metal System Trace plus pipeline-cache instrumentation to find a greedy
`argmax_bfloat16` compilation inside each fresh scored worker. Running the same
request-end operation on warmup logits moved about 17 ms of compilation out of
both windows without touching inference arithmetic.

## Negative results and traps worth carrying forward

These are as valuable as the wins because they rule out attractive dead ends:

- **Decode E2M1 constant-LUT dequant:** bit-exact but about 0.65% slower. The
  register-pipelined unpack wins inside the QMV inner loop. A similar LUT can
  still help a threadgroup-staging GEMM; kernel context matters.
- **Fusion with a redundant RMS barrier:** dispatch count fell, performance
  regressed. Removing the barrier rescued the mechanism.
- **Fused norm/QKV/gate across every NVFP4 layer:** duplicated producer work
  and live state outweighed one launch. The current default is separate.
- **Runtime-parametrized hot-kernel geometry:** a dormant-looking bounds path
  changed register allocation for the whole pipeline and regressed on the
  ranked M5 while winning locally on another M5 Max.
- **Aggressive LM-head coarse formats:** fewer screen bytes can create enough
  exact-tail candidates to lose overall. Preserve a full certificate and
  measure tail percentiles.
- **Router groups below eight:** measured null at a mature frontier; repeated
  norm/reduction work, not group count, was the floor.
- **Double-buffered gather staging:** negative by 5–7% in kernel tests; a
  zero-weight probe suggested the kernel was already execution/staging-bound,
  so more latency-hiding machinery could not buy much.
- **RoPE angle atlas:** retired after a marginal-value audit. Retain the audit,
  not the dormant idea.
- **Local KV/fusion and occupancy verdicts can invert on the ranked box.** One
  historical KV-write path reportedly won 17/17 local pairs and regressed
  ~19% ranked. The latest R1 down retile has the opposite local/ranked sign.
- **Prefill idle and compile artifacts can masquerade as model regressions.**
  The first request after a long thermal wait can pay an idle/compiler penalty.
  Compare absolute phase timings and instrument pipeline builds before blaming
  a decode-only change for prefill movement.
- **Metal debug labels can misattribute raw-encoder kernels.** A 1.7 ms
  “Squeeze” was actually a fused gate/up gather GEMM. Sanity-check attributed
  time against required bandwidth and command-buffer boundaries.

## Correctness patterns that survived the hard gates

The successful implementations repeatedly use the same proof techniques:

1. Preserve the exact K-loop and accumulation order; change tiling or ownership
   around it.
2. Preserve explicit BF16 materialization and rounding boundaries even inside
   a fused kernel.
3. Share loads, not accumulators, across GQA heads.
4. Elide only arithmetic whose result is already discarded, or work excluded
   by a conservative mathematical certificate.
5. Keep the original path in the same binary behind an environment selector
   for causal A/B and emergency fallback.
6. Give changed JIT shapes fresh pipeline names so MLX's name-keyed cache cannot
   reuse an incompatible kernel.
7. Guard decode-only work with exact one-token shapes. Do not create future
   logits, KV rows, rollback state, or request-keyed memoization.
8. Treat near-tie token flips separately from layer-difference checks; a
   `max_abs_diff=0` trace can still end in a changed final argmax.

## Measurement discipline for our campaign

Use three numbers for every official result:

- candidate decode seconds/token;
- candidate prefill seconds/token;
- the same-session baseline for each phase.

The headline score can reject a genuinely faster candidate when the paired
baseline happens to be fast, or promote a marginal candidate on a favorable
draw. Several late submissions recovered real mechanisms by comparing
absolute candidate phases across sessions. That is useful evidence, but it
does not turn a rejected result into a leaderboard win.

Recommended experiment record:

| field | requirement |
|---|---|
| base | promoted submission ID, promoted commit, and active-default manifest |
| hypothesis | named bottleneck, predicted phase, and physical mechanism |
| isolation | one selector or one small source delta; list inherited changes explicitly |
| correctness | exact arithmetic/rounding argument, public trace, serial-track audit |
| local timing | cool-gated same-binary ABBA, distributions rather than one pair |
| official result | candidate and baseline absolutes, paired speedups, gates, thermal status |
| verdict | mechanism belief separated from promotion verdict |
| preservation | whether a later snapshot retained, superseded, or lost the mechanism |

The documented acceptance band is applied against a pinned calibration
reference, while the published speedups use a same-session paired baseline.
Consequently a leaderboard delta can appear larger than the nominal per-run
window. Continue to chunk large mechanisms using absolute candidate timing and
the pinned-band policy; do not infer that the band disappeared from a large
headline jump.

## Where the frontier leaves room

### Highest-ceiling direction: graph-visible cache state and compiled segments

The all-NVFP4 submission reports a working whole-step compiled-decode prototype
that reduced Swift/FFI graph construction to roughly 230 µs but lost to the
current eager+async path because fused attention declined inside the trace: its
ring write index was a host `Int`. The next design would make cache/ring
position a graph value and compile multi-layer segments while leaving external
async scheduling legal and explicit.

This is the clearest route to a qualitatively new gain rather than another
sub-percent kernel tweak. It is also high risk: cache mutation, compilation,
and the serial position contract must remain exact.

### Attention after the byte floor

Attention representation bytes are at the accepted floor, but attention is
still a large absolute traffic pool. Useful questions are now:

- Can full-attention cache/epilogue work lose another dependency stage without
  duplicating QK normalization?
- Can cache indices and small parameter carriers become graph-visible and
  reusable across compiled segments?
- Are there remaining vector-load or metadata layouts that preserve every
  operand and accumulation order?
- Does the full-attention fusion still carry a different prefill/warmup cost
  than the sliding path on the current all-NVFP4 tree?

### Prefill gather-QMM structural tiling

RUNSKIP, WN1, expert grouping, and staging-width changes have mined the obvious
work and load waste. The remaining question from the public notes is structural:
match BK/BM/BN geometry to the observed short expert runs rather than adding
more buffering to the current shape. Reprofile the current kernel first; its
share changed substantially as other work disappeared.

### Exact LM-head certificates

The mature int5 screen is still worth auditing because it is a bandwidth-bound
pass plus a sparse exact tail. Potential wins must jointly improve:

- bytes per vocabulary row;
- bound tightness;
- live candidate p50/p90/p99;
- number of producer/threshold dispatches; and
- exact-tail memory access.

Any proposal that improves only coarse-kernel throughput can lose end to end.

### Kernel/source-budget pressure

Several late notes report the editable-source launch budget within kilobytes or
even bytes of its cap. A new custom family may require deleting dormant losing
arms or consolidating source builders. Treat cleanup as budget recovery with
tests, not as an optimization by itself; do not accidentally remove same-binary
controls needed for causal measurement.

## A balanced starting plan

### Phase 0 — inherit correctly

1. Refresh `mlxfast submissions --all` and `upstream/main`.
2. Preserve the current worktree; create a clean branch from the actual latest
   promoted source rather than running a destructive reset over local work.
3. Build a machine-checked active-default manifest for the features in “What
   the current frontier actually does.”
4. Run setup, the full Swift tests, a cool local baseline, and one detailed
   trace before changing code.
5. Record local hardware, startup-memory profile, toolchain, thermal behavior,
   and the known public-token drift status.

### Phase 1 — reproduce budgets independently

Do not accept the public bottleneck map unchanged. Re-measure:

- decode bytes by attention, MoE, router, and LM head;
- GPU busy time and command-buffer gaps;
- Swift/FFI graph-construction time;
- prefill kernel family shares and expert-run distributions;
- LM-head candidate-density percentiles; and
- first-use pipeline compilations inside scored-equivalent windows.

This is how we keep the leaderboard from becoming a set of blinders. The
public work supplies hypotheses and controls; our trace decides the next target.

### Phase 2 — run a portfolio, not a monoculture

A sensible initial allocation is:

- **60% frontier exploitation:** graph-visible cache state/compiled segments,
  full-attention dependency structure, and current prefill gather tiling;
- **25% independent profiling and falsification:** verify that the inherited
  cost map still holds after the all-NVFP4 and un-fusion jumps;
- **15% fresh ideas:** one mechanism derived from our own trace that does not
  appear in the public notes.

Each experiment should be narrow, reversible, and accompanied by a causal
selector. Bundle only after official absolute timings establish compatible
positive components or when a sub-percent mechanism is otherwise below the
ranked noise floor.

### First candidate queue

| priority | candidate | reason | kill criterion |
|---|---|---|---|
| P0 | Graph-valued ring index + compiled multi-layer segment prototype | Highest published ceiling; attacks CPU/FFI work now exposed by lower weight traffic | Any position/KV semantic ambiguity, inability to dispatch active fused attention, or eager+async remains faster |
| P1 | Current-tree full-attention dependency/epilogue audit | Sliding fusion is proven; full path has had warmup and composition ambiguity | Duplicated producer work, extra cache traffic, or no isolated phase win |
| P2 | Current expert-run distribution and gather-QMM structural retile | Public notes point beyond buffering toward geometry matched to short runs | Kernel gain does not survive end-to-end prefill or changes accumulation order |
| P3 | LM-head certificate/candidate-density audit | Still a distinct bandwidth pass with measurable sparse tail | Coarse byte win expands p90/p99 exact tail enough to erase it |
| P4 | Source-budget reclamation of dormant negative arms | May unblock P0–P3 safely | Any active default, fallback, or causal selector changes |

## Reproduction and refresh commands

The public API is sufficient; clicking 126 rows is unnecessary:

```bash
mlxfast submissions --all
mlxfast submission-note <submission-id-or-prefix>
git fetch upstream main
git show <promoted-commit>
```

Programmatic sources:

```text
https://mlx.fast/api/benchmarks/1854efdf-feba-4773-bae9-b80520881a74/submissions
https://mlx.fast/api/submissions/<full-submission-uuid>
```

The leaderboard-success predicate used by the current site is:

```text
status == "accepted"
&& promotionStatus == "promoted"
&& promotedSourceRef != null
```

One additional record, submission
[`f05541bc`](https://mlx.fast/api/submissions/f05541bc-3bff-43cf-9358-46b1eee5eb66),
was accepted but failed promotion because the benchmark branch moved outside
the editable surface during validation. Its note is useful evidence, but it is
correctly excluded from the 126 leaderboard successes.

## Bottom line

We should inherit the current frontier as infrastructure, not as doctrine. The
competition has already proved that bandwidth accounting, certified work
elision, dependency-stage removal, occupancy, and warmup can compound to more
than halve both phases. It has also proved that local M5 results, dispatch
counts, and seemingly harmless dormant branches can lie.

Our strongest start is therefore:

1. preserve every active frontier invariant;
2. reproduce the current cost map ourselves;
3. attack graph-visible cache/compiled scheduling as the highest-ceiling open
   problem;
4. keep prefill gather and exact LM-head work as disciplined secondary lines;
5. reserve real effort for a trace-derived idea that the leaderboard has not
   already framed.

That gets us the benefit of 126 public experiments without outsourcing our
search strategy to them.
