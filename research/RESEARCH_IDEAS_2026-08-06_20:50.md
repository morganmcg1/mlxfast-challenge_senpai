# Research Ideas — Round 24 Candidates (2026-08-06 20:50 UTC)

Prepared by advisor-delegate from a fresh source audit at BASE_SHA
`9dd2eec38a11d0e0bc7bcdbc5aec46e3436f284f`. All paths/line numbers verified in
this checkout. Score prices used throughout (from CURRENT_RESEARCH_STATE):
−1 ms prefill wall = **+0.362 %** score; −1 µs decode step = **+0.01464 %**
score; acceptance bar **+0.61 %**; 2σ kill floor 0.243 %.

Framing that drives this list: after this audit, the op-fusion frontier is
essentially harvested (fused QKV `LagunaRuntimeModel.swift:5880-5892`, prefill
router tournament `:9484-9502`, one-dispatch counting sort
`SwitchLayers.swift:320-338`, sorted MoE tail `:9636-9700`, fused sorted routed
gate/up `:10176-10200`, level-2 causal elision already inside
`steel_attention_nax.h:237-282,352,591-628`). What is *not* harvested is the
**time between kernels**: ~31.28 ms of the 97.89 ms prefill wall is GPU-idle /
unattributed, and ~322 µs of each 4,143.6 µs decode step is host gap. Round 23
(#148/#157/#158) is *measuring* those pools; the ideas below are the *fix
mechanisms*, which are currently unassigned.

---

## Idea 1 — Whole-step compiled decode (port `CompiledDecode` onto the scored serial loop)

**Hypothesis (one line).** Rebuilding the ~300-op lazy decode graph in Swift
every step is the dominant part of the 322 µs/step host gap; capturing the step
once with MLX `compile(inputs:outputs:)` and replaying it removes most of that
gap.

**Mechanism (verified paths).**
- The infrastructure already exists in editable files and is *not* on the
  scored path: `Vendor/mlx-swift-lm/Libraries/MLXLMCommon/CompiledDecode.swift`
  (whole-step `compileForward`, doc: "collapsing hundreds of FFI crossings into
  a single compiled call"), `CompilableKVCache.swift`,
  `CompilableRotatingKVCache.swift` (fixed-shape caches with `MLXArray`
  offsets), and the `TieredForward` fast/slow two-graph selector
  (`CompiledDecode.swift:38-83`) that already solves the growing
  full-attention-cache problem (fast graph attends a fixed prefix, slow graph
  the whole buffer, no KV copy on switch).
- Today only micro-fusions are compiled
  (`LagunaRuntimeModel.swift:5361,5383` gate on
  `MLXHardwareInfo.isCompiledDecodeSupported`); the whole-step
  `setupCompiledDecode` is only called from `GenerationBatch.swift` (batch
  engine, not scored, not editable — but the call site we need is the serial
  iterator in `Vendor/mlx-swift-lm/Libraries/MLXLMCommon/Evaluate.swift`,
  which IS editable).
- Port work: (a) promote the two cache families used by the fused decode
  kernels (`KVCacheSimple.fusedAppendPrepare()` /
  `RotatingKVCache.fusedRingPrepare()`, consumed at
  `LagunaRuntimeModel.swift:5960-6010`) to compile-traceable form — the fused
  kernels already take `writeIdx` as an array input, but the *advance*
  (`fusedRingAdvance()`, `fusedAppendAdvance()`) mutates Swift-side state and
  must move in-graph, exactly the `CompilableRotatingKVCache` pattern; (b) trace
  through `MLXFast.metalKernel` primitives (they are ordinary graph primitives;
  no Swift closure may call `.item()` during the step); (c) drop the
  `decodeFireMask` interior `asyncEval`s (`LagunaRuntimeModel.swift:10873-10885`)
  inside the compiled body — their purpose (overlapping graph build with GPU)
  disappears when there is no per-step build.

**Expected value (arithmetic).** #158's measured host gap is 322 µs/step. If
compile removes 60–85 % of it (residual = cached-schedule encode + commit):
190–275 µs × 0.01464 %/µs = **+2.8 % to +4.0 % score**. Even a pessimistic
100 µs recovery = +1.46 %, 2.4× the acceptance bar. (Decode has 75 % score
weight; price already reflects the exponent.)

**Cheapest falsifier + kill rule.** Stage 1 (2–3 days): wire
`CompiledDecode.compileForward` around the *stock* decode forward (fused
attention flags off, stock Compilable caches) in `--local-iterate`; measure
paired steady-state seconds/step. Kill the family if (a) compiled-vs-uncompiled
Δstep < 30 µs (≈ +0.44 % score-equivalent) on both a quiet M4 and the ranked
probe, **and** (b) #158 attributes < 100 µs/step to graph-build+FFI. Stage 2
only if stage 1 passes: trace the fused-kernel path.

**Main correctness/rule risk.** MLX `compile` fuses elementwise chains into
generated kernels — per-element operation order is preserved, but this must be
*proven*, not assumed: run `research/run_upstream_equivalence.sh` plus the
bitwise logit digest (top_k=100352, 64 steps) with a firing control (fern's
1-ULP protocol), since the token gate is blind to sub-token drift. Serial-rule
exposure: none — same per-invocation computation, no cross-request state; the
compiled trace is an input-independent kernel/dispatch cache, explicitly
allowed.

**Why not §8.** Closed family "decode graph repartitioning" covered
`asyncEval` fire-mask partitioning of the *interpreted* graph; whole-step
compile is a different mechanism (eliminates graph construction rather than
re-slicing it). "In-loop host CPU" closure was about moving work onto the host,
not removing host overhead. No prior PR touches `CompiledDecode`.

**Student time.** ~1–2 weeks incl. equivalence rig. **EV/time: highest of the
big swings.**

---

## Idea 2 — Prefill asyncEval ladder cadence re-tune on M5 (stride sweep, then 2-line default change)

**Hypothesis (one line).** With `lagunaPrefillAsyncLadderStride` defaulting to
1 (`LagunaRuntimeModel.swift:732-737`), the prefill window issues ~40 separate
eval boundaries whose scheduling/commit gaps are a material slice of the
31.28 ms GPU-idle pool; a coarser stride (4–16) recovers most of that slice.

**Mechanism.** `:10888-10896` fires `asyncEval` after every
`stride` layers during multi-token forwards. Each boundary costs scheduler
wake-up, command-buffer commit, and a GPU drain-to-refill bubble. If the
per-boundary bubble on M5 is b µs, total cost ≈ b × 40/stride. The knob is
env-read at process start; the *submission* is changing the default literal
(and possibly the decode `decodeFireMask` twin at `:10623,10656` as a sibling
arm).

**Expected value (arithmetic).** Unknown X = inter-boundary idle attributable
to the ladder (bounded above by 31.28 ms; frieren's #148 ledger and tanjiro's
#157 instrument will bound it). Recovery at stride k ≈ X·(1−1/k). At X = 4 ms,
k = 8: 3.5 ms × 0.362 %/ms = **+1.27 %**. At X = 2 ms: +0.63 % (still above
bar). At X = 10 ms: +3.2 %. Note the doc's worked point: −3.13 ms = +1.20 %.

**Cheapest falsifier + kill rule.** Pure measurement, ~half a day: sweep
`DARKBLOOM_PREFILL_ASYNC_LADDER ∈ {1,2,4,8,16,40,off}` with
`./benchmark.sh --local-iterate` paired baselines on a quiet M4, then confirm
the sign on the ranked box (fold into a #148-style calibrated probe if
possible — the M4→M5 buffer-granularity sign inversion precedent
(`MLX_MAX_MB_PER_BUFFER`, M4 −1.76/−1.99 % vs M5 +1.608 %) makes M4-only
evidence inadmissible for promotion). Kill if best-of-sweep saves < 0.3 ms
prefill wall on M4 **and** the #148/#157 attribution shows < 50 µs per
boundary on M5.

**Main correctness/rule risk.** None to numerics (`asyncEval` cadence changes
only when already-constructed work is enqueued — the file's own doc at
`:725-731` states the exactness ground). Risk is purely
measurement-validity: M4/M5 sign inversion.

**Why not §8.** `MLX_MAX_OPS_PER_BUFFER` (inert ≥40) and
`MLX_MAX_MB_PER_BUFFER` (M5 regression) tuned *MLX-internal buffer splitting*;
the ladder is a *model-side eval cadence* the closures never swept. The ladder
itself was promoted at stride 1 without a documented M5 stride sweep.

**Student time.** Days. **EV/time: best of the list; assign as a rider to any
student with local bench access.**

---

## Idea 3 — Stream-parallel shared expert in prefill (reopened old-5b with a new, editable mechanism)

**Hypothesis (one line).** The shared-expert prefill chain (fused gate_up QMM →
SwiGLU → down QMM, ~3.2 GFLOP/layer ≈ 4 ms GPU total across 39 layers) is
data-independent of the routed pipeline until the tail combine, and issuing it
on a second MLX stream overlaps it under the routed gather-GEMMs for near-free.

**Mechanism (verified paths).**
- Independence: in `LagunaRuntimeSparseMoEBlock.forward`
  (`LagunaRuntimeModel.swift:10160-10240`), `sharedExpert(x)` consumes only the
  block input `x` and is consumed only by `lagunaPrefillSortedMoETail(...)`
  alongside the routed output — a two-branch diamond.
- Mechanism: MLX Swift ops accept a `stream:` target; arrays produced on
  stream B and consumed on stream A get automatic event-based dependencies
  from the MLX scheduler. This avoids the closed command-buffer-splitting
  approach (prefill overlap C1/C2) and needs no `device.cpp` edits (which are
  NOT in `editablePaths` — constraint verified against `benchmark.json`).
- Gate on evidence: tanjiro's #157 co-residency instrument is the direct
  admissibility test. If M5 never co-schedules two compute kernels from
  different queues, this idea is dead on arrival — that is exactly what #157
  answers first.

**Expected value (arithmetic).** Shared-expert prefill GPU time ≈ 39 ×
(2×512×2048×1024 + 2×512×512×2048) FLOP ≈ 125 GFLOP ≈ 3.5–4.5 ms at the
observed ~30 TFLOPS MMA rate. Fully hidden: 4 ms × 0.362 %/ms = **+1.4 %**.
Half hidden (event sync + occupancy interference): +0.7 %. Both above bar.

**Cheapest falsifier + kill rule.** (1) Await #157: if co-residency = never,
close with zero further spend. (2) If possible, a 30-line prototype moving only
`sharedExpert(x)` to a second stream for L>1, measured paired on M4 (weak
directional) and via ranked probe. Kill if prefill wall improves < 0.5 ms on
the co-residency-positive host, or if cross-stream sync adds > 0.5 ms.

**Main correctness/rule risk.** Cross-stream dependency bugs would corrupt
activations — caught by upstream equivalence + drift tripwire; no envelope or
serial-rule exposure. Scheduler-level nondeterminism does not change values
(same ops, same operands, disjoint outputs).

**Why not §8.** "Shared-expert overlap (old 5b)" is explicitly *reopened* in
the archive; the closed variants were in-kernel barrier tricks and
command-buffer splitting. The MLX second-stream mechanism has never been
tried here.

**Student time.** ~1 week after #157 reports. **EV/time: high, conditional.**

---

## Idea 4 — Decode-step indirect command buffer (ICB) replay — escalation of Idea 1

**Hypothesis (one line).** Even a compiled trace pays per-step encode+commit;
pre-encoding the entire fixed-shape decode step into a reusable
`MTLIndirectCommandBuffer` (input-independent: only the token id, offsets, and
ring indices change, all read from device buffers) removes nearly all remaining
host time.

**Mechanism.** The decode path is already ~90 % hand-written MSL with fixed
shapes (`lagunaResidualRMSNormRouterKernels` :991, fused QKV :3330, fused
attention :1369/:1818, routed SwiGLU QMV + down-reduce :10022-10160, gate/oproj
:3716-4355), which is exactly the profile ICBs want. Requires compiling the
same MSL through a direct `MTLLibrary` with
`supportIndirectCommandBuffers = true`, persistent self-owned intermediate
`MTLBuffer`s, and stable weight buffers (MLX weight arrays are load-time
constants; their buffers do not move). New code can live in a new file under
`Sources/MLXFastModel/` (directory is on the editable surface; total headroom
73,089 B, `LagunaRuntimeModel.swift` per-file headroom 57,121 B — budget the
runtime in the new file).

**Expected value (arithmetic).** Ceiling = the full 322 µs host gap plus
in-buffer encode: 322 × 0.01464 = **+4.7 %**; incremental over a successful
Idea 1 ≈ +0.5–1.5 %. Standalone value if Idea 1's trace is blocked by the
fused-kernel path.

**Cheapest falsifier + kill rule.** Do not start until (a) Idea 1 lands and
its residual gap is measured, and (b) #158 confirms the gap is absolute (not
proportional). Kill trigger for starting at all: residual host gap after
Idea 1 < 100 µs/step. Prototype falsifier: ICB containing just the 40
`residual_rms_router` + fused-attention dispatches, replayed 128×, vs the same
sequence dispatched normally; kill if per-step saving extrapolates < 60 µs.

**Main correctness/rule risk.** Highest of the list: buffer-lifetime bugs
produce silent garbage (mitigate with the drift tripwire + logit digest);
bypassing MLX's scheduler means manual hazard tracking. Rule-wise clean: the
ICB is an input-independent dispatch cache; no cross-request state (KV ring
indices advance exactly one position per invocation).

**Why not §8.** No prior family touched Metal-level command replay; closures
covered MLX-graph-level partitioning and env knobs only.

**Student time.** 2–3 weeks. **EV/time: good ceiling, run only after Idea 1.**

---

## Idea 5 — (Endorsement, already held for round 24) H1 row-adaptive dual-path gather GEMM

Kept on the board with its existing numbers (+1.4–2.9 %): route histogram
(`research/artifacts/route-histogram-prefill512.csv`) shows median 7 rows per
(layer,expert) vs BM=64 tiles ⇒ 3.44× padded-row FLOP amplification and only
1-of-4 simdgroups active on the mean expert. The blocking work item stays the
bit-exactness proof: the QMV-style small-row path must reproduce the gather
GEMM's per-row K-loop accumulation order bitwise, else it cannot ship
(token gate is blind; use the logit-digest rig). M4-blind (`_nax`), needs the
§5 safety rig (accept gate `quantized.cpp:1660-1671` requires `bm==64 && wm==4`
and falls back silently; `is_nax_available()` at `quantized.cpp:1994`).
Not re-counted in my ranking since it is already held; listed to keep round-24
sequencing honest.

---

## Idea 6 — Bundle-only: prefill KV-cache-write fusion + shared-expert SwiGLU epilogue

Two sub-bar items worth bundling into whichever prefill PR ships first:
(a) write rotated K (and copy V) directly into the cache backing store inside
the prefill QK-norm+RoPE kernels (`:2332-2597`), deleting 2 slice-assign
dispatches + ~2 MB intermediate traffic per layer (~80 dispatches, ~80 MB
total ⇒ ~0.25–0.4 ms ⇒ +0.09–0.14 %); (b) the held §9.10 shared-expert prefill
SwiGLU epilogue (78 MiB + 78 dispatches ⇒ ~+0.1–0.3 %, real work =
new epilogue in `fp_qmm_t_nax_static`, `kSwigluRegLocal` currently false there
because SN=32; prefill guard at `LagunaRuntimeModel.swift:8463` is scoping, not
correctness). Each alone is under the 0.61 % bar; together with Idea 2 or 3
they clear it. Kill rule per item: measured contribution < 0.15 ms.

---

## Ranking by EV per unit student time

| Rank | Idea | EV (score) | Student time | Gate |
|---|---|---|---|---|
| 1 | Idea 2: ladder cadence sweep | +0.6–3.2 % | days | none (measure first) |
| 2 | Idea 1: whole-step compiled decode | +2.8–4.0 % | 1–2 wk | #158 attribution strengthens but not required |
| 3 | Idea 3: stream-parallel shared expert | +0.7–1.4 % | 1 wk | #157 co-residency = yes |
| 4 | Idea 5: H1 dual-path gather (held) | +1.4–2.9 % | 1–2 wk | bit-exactness proof |
| 5 | Idea 4: ICB replay | +0.5–4.7 % | 2–3 wk | after Idea 1 |
| 6 | Idea 6: bundle items | +0.2–0.45 % | days | bundle only |

---

## Investigated and rejected this round (do not re-open without new evidence)

1. **Causal K-block tile skipping in `steel_attention_nax`** — already fully
   implemented, including per-simdgroup level-1 *and* level-2 (P@V skip)
   elision, Q-fragment hoisting, and zigzag qblock scheduling
   (`steel/attn/kernels/steel_attention_nax.h:237-282, 340-352, 591-628`,
   `DARKBLOOM_ATTN_QBLOCK_MAJOR/ZIGZAG` default ON). No headroom left in mask
   elision; any note listing this as open is stale.
2. **Prefill fused QKV projection** — already one matmul over the
   row-concatenated `[Wq; Wk; Wv]` bank (`LagunaRuntimeModel.swift:5880-5892`).
3. **Prefill router/top-k/sort/scatter op fusion ("glue" as ops)** — already
   harvested: router tournament single kernel (`:9484-9502`), one-dispatch
   counting sort + inverse order (`SwitchLayers.swift:320-338`), fused sorted
   routed gate/up with deferred unsort (`:10176-10200`), sorted MoE tail single
   dispatch incl. residual (`:9636-9700`). The *reopened C5* should be
   re-scoped to command-buffer/idle-gap structure (Ideas 2/3), not op count.
4. **Quantizing attention weights for decode bytes** — already shipped: native
   group-32 affine INT8 side layouts for batched QKV, o_proj, and g_proj plus
   an inherited group-16 NVFP4 tail with depth selection
   (`LagunaRuntimeModel.swift:294-442, 2827-2926`). Extending NVFP4 to more
   layers is a precision change outside the accepted envelope (forbidden);
   full-INT8 re-adoption is the §8 "backwards, adds ~802 MB/step" closure.
5. **lm-head / dense-layer-0 / router quantization** — outside the accepted
   attention-only envelope; §8 "no shippable lm-head byte arm" stands.
6. **Chunked prefill to reduce attention FLOPs** — the causal triangle is
   invariant under chunking; sliding window (512) equals full attention at
   L=512, so no mask-family win exists at the scored shape.
7. **KV-cache re-layout / byte reduction in decode** — sliding KV is SLC-served
   (443 GB/s closure `sliding_fused_attn_ring_v1`); KV re-quantization is a
   precision change outside the envelope.
8. **Prefill lm-head waste** — already sliced to the last row before final norm
   (`lagunaLastTokenHidden`), logits `[1,1,vocab]`.
9. **`MLX_MAX_MB_PER_BUFFER` / `MLX_MAX_OPS_PER_BUFFER` retunes** — closed with
   the canonical M4→M5 sign inversion / inert verdicts; superseded by the
   model-side cadence knob (Idea 2), which is a different mechanism.
10. **Any multi-token/speculative/lookahead decode restructure** — excluded by
    the serial non-speculative track rules regardless of bit-exactness.

## Contradictions / doc corrections surfaced by this audit

- `device.cpp`/`device.h` (and `fast.cpp`, `scaled_dot_product_attention.cpp`)
  are **not** in `benchmark.json.editablePaths`; any mechanism requiring MLX
  scheduler/barrier edits must route through editable call sites
  (`matmul.cpp`, `quantized.cpp`, `jit_kernels.cpp`, kernel bodies) or
  Swift-side stream selection.
- "94.2 % of M5 prefill time is `_nax`" and "31.28 ms unattributed" only
  reconcile if the 94.2 % is a share of **GPU-busy** (~66.6 ms), not wall
  (97.89 ms). State this explicitly in the research state doc to prevent
  double-counting headroom.
- The SDPA dispatch geometry (bq=64, bk=32, wm=4, wn=1) is hardcoded in the
  **non-editable** `scaled_dot_product_attention.cpp:31-36,177-179`; only
  kernel-internal restructuring is on the table for attention.
- Decode attention plane is already quantized (see rejected #4): any residual
  note or mental model pricing decode attention as BF16 (≈2.85 GB/step)
  overstates decode byte headroom by ~2×.
