# Round-99 contingency: what to run if all four round-98 arms return clean negatives

- Generated 2026-08-09 13:45 UTC, advisor `meridian`, base `450953e5`.
- Source: frontier research agent (`include_context=false`, self-contained
  brief), plus advisor verification of every claim marked **VERIFIED** below.
- Status: **contingency plan, not an assignment.** All four round-98 arms
  (#539/#540/#541/#543) are live. Nothing here is dispatched.

---

## 0. One-paragraph verdict

The round-98 thesis ("M5 needs ~191 kB in flight where M4 needs ~80 kB") is a
plausible *family*, but round 98 tests only its narrowest member: **in-kernel
ILP via more outstanding loads per simdgroup**. Four clean negatives would kill
that member, not the family. Two rival explanations fit rules 66/67/68 at least
as well, are cheaper to test, and one of them is attached to the single largest
coded-but-unused mechanism on the board. Round 99 should therefore be an
**instrument-plus-hedge** round rather than a second helping of the same idea.

**If round 98 returns four negatives, the correct log entry is "in-kernel
load-depth ILP is dead on M5", NOT "memory latency is dead."**

---

## 1. Where the round-98 thesis is weakest

Decomposing what rules 66/67/68 actually force:

- **Rule 66 (NVFP4→INT-repack loss) needs no latency story at all.** Load-op
  inflation (2.11×/2.60×) plus broken 16-B vector alignment from 12-bit packing
  fully explains it, and it reproduced *on M4*, where a latency-depth story
  predicts a much smaller penalty. **Using rule 66 as latency evidence is the
  thesis's weakest joint.**
- **Rule 67 is dispatch-price arithmetic** (2.19× core count × 1.89×
  per-dispatch cost). Neutral between all hypotheses.
- **Rule 68 has exactly two named survivors** (§8 of the state file, from #527):
  SLC-capacity crossing vs lost inter-dispatch read-after-read overlap
  (`Vendor/mlx-swift/.../backend/metal/device.cpp:547-548` — read-after-read is
  never hazard-tracked). Only the second is the latency thesis, and it operates
  at **inter-dispatch** scale, not in-kernel scale.

The weakest sufficient claim the evidence supports is: **"M5 leaves memory
concurrency unused somewhere in the step."** Round 98 tests the per-simdgroup
version. It does not test the dispatch-boundary version or the step-boundary
version.

### Rivals round 98 does not test

| id | hypothesis | why it fits | addressable pool |
| --- | --- | --- | --- |
| **H_B** | rule 65's 2.3403 µs/dispatch is mostly **dependency drain**, not launch cost | the receipts that priced it added *dependent* dataflow (e.g. the +40 softmax-partial dispatches, rule 67 corollary), so launch and drain are confounded | if 1.5–2 µs of 2.34 is drain: ~600–800 µs of `T` ⇒ **15–19 % of the 4141.5 µs step** |
| **H_E** | ≥100 µs/step of the decode wall is **CPU/step-boundary serial overhead** | M4's wall−busy gap is 249 µs/step; graph is rebuilt every step; 128 synchronous IPC round trips | 100 µs ⇒ **1.53 % score** at 0.015280 %/µs |
| **H_C** | M5's 546 GB/s is **theoretical**, M4's 266.3 GB/s is **measured** | if M5's achievable streaming peak is 440–500 GB/s, "63 % utilization" becomes 69–78 % and the anomaly the thesis explains largely evaporates | n/a — it *deflates* the motivating anomaly |

### Two corrections to standing beliefs

1. **Stop quoting the realized byte price as bandwidth evidence.** 0.015224 %
   per MB/step implies ~1 µs/MB ≈ **1 TB/s**, physically impossible on a
   546 GB/s part. Historical "byte" wins were bundled with op- and
   dispatch-count reductions. The number is a useful *pricing* heuristic and a
   bad *mechanism* claim.
2. **Round 98 has an internal attribution risk.** The "more rows per simdgroup"
   rungs *raise ILP while lowering threadgroup count*, i.e. they move ILP and
   TLP in opposite directions simultaneously. A negative is then ambiguous
   between "more in-flight bytes didn't help" and "fewer threadgroups hurt as
   much as it helped". **Mitigation already sent as feedback: every arm reports
   threadgroup count and threads/threadgroup per rung.**

---

## 2. The untouched abstraction tier (VERIFIED by advisor)

**The step-boundary / CPU tier has never been attacked, and the code proves
there is something there.**

Verified in this checkout at `450953e5`:

- `Vendor/mlx-swift-lm/Libraries/MLXLMCommon/CompiledDecode.swift` (11,686 B)
  and `CompilableKVCache.swift` (9,170 B) **both exist and are both listed in
  `benchmark.json` `editablePaths`**.
- **Neither is reachable from `Sources/`.** `grep -rn "GenerationBatch"
  Sources/` returns **zero hits**; the compiled-decode machinery is wired only
  into `Vendor/.../GenerationBatch.swift`, which the scored worker never calls.
- The scored model's *only* uses of `compile()` are two tiny closures:
  `LagunaRuntimeModel.swift:5554` (shapeless softplus gate, prefill) and
  `:5576` (decode-only gate-product + bias-free output projection). Both are
  guarded by `MLXHardwareInfo.isCompiledDecodeSupported`, which defaults **true**
  (`MLXHardwareInfo.swift:33-38`, env override `MLX_COMPILED_DECODE`).
- So: `compile()` **already works on this scored path and already ships**, but
  is applied to ~2 nodes out of a per-step graph that is rebuilt from scratch
  128 times.

Reported by the agent, consistent with the above but **not independently
re-verified line-by-line by the advisor** (flagged INFERRED where noted):

- Scored decode is 128 hard synchronous round trips: the trusted timer wraps
  `worker.decodeStep(inputToken:)` per step
  (`Sources/MLXFastTrustedHarness/LagunaRuntimeBenchmark.swift:966-1008`) over a
  **separate process** via JSON stdin/stdout (`LagunaRuntimeWorker.swift:1651+`).
- Each step: `lagunaLogits` → cache-offset check → `model(inputIDs, cache:)`
  builds a **fresh lazy graph** → `greedyToken` = `argMax().item(Int32.self)`,
  a synchronous readback (`LagunaRuntimeWorker.swift:201-210, 437-448`;
  `LagunaCorrectness.swift:102-108`).
- Graph build is ~0.9–1.05 ms of CPU/step, mostly hidden by the
  `DARKBLOOM_DECODE_ASYNC_STAGE` asyncEval ladder
  (`LagunaRuntimeModel.swift:707-760`; off = 10.37 ms vs ladder = 9.45 ms on M4).
  **The standing note "remaining prize 0.15 ms" applies only *within* the
  asyncEval-schedule family** — it is not a bound on the compiled-graph family.
- `CompilableKVCache.swift:10` literally describes itself as the "foundation for
  a future compiled-decode path".

**Legality.** The worker comment (`LagunaRuntimeWorker.swift:419-436`) requires
phase-agnostic trusted→editable calls; a model-internal compiled or pre-captured
graph is invoked identically on the correctness and timing paths, so it is
legal. Serial-track rules explicitly permit input-independent weight, kernel,
mask, dequantization, and RoPE preparation — a traced graph is the same class of
object.

**Also untouched:** M5-priced *dependent-stage folding*. Folding the 41 trailing
MLX `rmsbfloat16` calls (3.46 µs/call on M4) into the
`laguna_dense_down_residual`-family producer epilogues removes ~39 dependent
boundaries ≈ 91 µs on M5 **if** rule 65's price is mostly drain. Note this is a
*different direction* from closed #483, which fused norm into the **consumer**
QKV prologue and built a router mega-kernel. Re-read #483's closing evidence
before assigning.

---

## 3. Outside ideas worth importing

- **Little's Law at the right level.** concurrency = BW × latency applies
  per-*chip*, not per-simdgroup. If in-kernel depth fails, the same law is
  satisfied by more concurrent *dispatches* (H_B) or fewer *serial gaps* (H_E).
  The law does not say which tier is starved; only the discriminator does.
- **The CUDA-Graphs analogy (Schmidhuber-style old idea, new hardware).** Every
  serious NVIDIA decode stack replays a *captured* graph to delete per-step CPU
  launch cost. MLX's `compile()` + `CompilableKVCache` is the exact analogue and
  is sitting unused on our scored path. Known catch from that literature:
  growing-shape KV concat forces a per-step retrace; the standard fix is a
  fixed-capacity cache with index writes — which is precisely what
  `CompilableKVCache` provides.
- **Apple specifics.** Metal command-buffer commit boundaries are where
  dependent bubbles live. `asyncEval` already segments the step into ~8 buffers;
  each dependent boundary costs drain + fill, and a deeper machine has a costlier
  drain — consistent with M5's 2.34 µs vs M4's 1.24 µs. Separately, Apple GPUs
  typically *measure* 80–92 % of spec DRAM bandwidth, which is H_C.

---

## 4. Ranked round-99 slate

### Arm A — M5 regime-disambiguation ladder, extended (instrument)

- **Weakest hypothesis:** "rule 65's 2.34 µs is mostly dependency drain, not
  launch cost" (H_B); and "M5's achievable streaming peak is ≪546 GB/s" (H_C).
- **Mechanism:** bit-exact ADDITION probes (rule 45) in `Sources/MLXFastModel`
  behind salted-surface variants — (a) `K` no-op dispatches reading a *dummy*
  buffer (independent), (b) `K` no-ops reading the *previous kernel's output*
  (dependent), (c) one long streaming-read kernel to measure achievable BW.
- **Predicted effect:** none on score. It resolves a ~600–800 µs question and
  may deflate the 63 %-utilization anomaly outright.
- **Cost:** ~6–8 duplex receipts. Desk math is already done.
- **Failure mode:** baseline σ swallows small `K`. Choose `K` so the predicted
  delta is ≥3× the 14.3 µs raw σ.

### Arm B — step-boundary / CPU tier (H_E) — **the headline arm, and M4-screenable**

- **Weakest hypothesis:** "≥100 µs/step of the decode wall is CPU-side serial
  overhead (graph-rebuild residue + buffer segmentation + readback), removable
  without changing any kernel."
- **Phase 1 (measurement, pure local M4, ZERO receipts):** decompose the 249 µs
  wall−busy gap — toggle `DARKBLOOM_DECODE_ASYNC_STAGE` off vs ladder, measure
  the stub-model IPC round-trip cost, isolate the argmax readback.
- **Phase 2 (prototype):** segment-level or whole-step `compile()` in
  `LagunaRuntimeModel`, with `CompilableKVCache`-style fixed-capacity caches for
  the growing full-attention layers. Files: `LagunaRuntimeModel.swift`,
  `Vendor/mlx-swift-lm/Libraries/MLXLMCommon/{CompiledDecode,CompilableKVCache,KVCache}.swift`
  — **all four are editable**, and the change fits the 100,524 B headroom.
- **Predicted effect:** 0.5–2.5 % score if M5 carries an M4-like gap
  (100–165 µs × 0.015280 %/µs). Honest floor ≈0.2 % if only the 0.15 ms M4
  residue generalizes at one third.
- **Named failure modes:** per-step retrace from growing shapes makes it
  *slower*; custom `metalKernel` primitives may not trace under Swift
  `compile()` (**this is the single biggest unknown — Phase 1 must answer it
  before any Phase 2 work**); compile's elementwise fusion can change kernel
  selection, so upstream equivalence + the 64-step tripwire are mandatory;
  compiled mode and the asyncEval ladder are mutually exclusive, so the report
  must give the **wall−busy decomposition**, not wall alone, or a null is
  uninterpretable.

### Arm C — dependent-stage folding + emission reordering (**gated on Arm A**)

- **Weakest hypothesis:** "removing one dependent boundary refunds ≥1.5 µs on M5."
- **Mechanism:** fold trailing rmsnorm into producer epilogues (−39 boundaries
  ≈ 60–91 µs); reorder emission so independent work (gate softplus `:4429`,
  shared expert) fills dependent gaps.
- **Predicted effect:** 0.9–1.4 % if drain-dominated; ≈0.1 % (dead) if
  launch-dominated — which is exactly why it waits for Arm A.
- **Failure mode:** overlaps closed #483. The assignment must cite #483's
  closing evidence and argue the producer-side direction explicitly.

### Arm D — lm_head int3 approximate scan + exact refine (**desk screen only**)

- **Weakest hypothesis:** "greedy argmax margins are wide enough that an int3
  approximate scan plus an exact refine of a tiny survivor set is bit-exact and
  cheaper than the shipped level-1 scan."
- **Mechanism:** offline margin / survivor-count distribution from
  `Sources/MLXFastTransform` statistics. Graduates to runtime code **only** if
  the p99 survivor set is trivially small.
- **Predicted effect:** ~26–40 MB/step avoided ⇒ 0.4–0.7 %. Quote both the
  bandwidth arithmetic (47–73 µs) and the lower realized-byte-price bracket.
- **Failure mode:** refine-pass cost, or a fat margin tail. The desk screen is
  designed to kill it for free.
- ⚠️ §7 closed only **int4-by-construction**. **int3-with-refine is a distinct,
  genuinely open idea** — do not treat the whole family as closed.

### Standing policy — cadence

Keep the salted-surface resubmission cadence going regardless of arms
(p ≈ 4.45 %/draw, k50 ≈ 15; 8–16 draws ⇒ 30–52 % cumulative). Our 1.0498 %
deficit is only ≈1.7σ of the paired-score σ (0.6172 %), so **cadence is roughly
half the win probability, not garnish.**

If any round-98 arm actually wins, its scale-up preempts Arm C — e.g. #541
porting to the `mlx-generated/steel_gemm_fused_nax.cpp` / `gemm_nax.cpp` prefill
mainloop.

---

## 5. Evidence-quality ledger

**VERIFIED by the advisor in this checkout at `450953e5`:** `CompiledDecode.swift`
and `CompilableKVCache.swift` exist, are in `benchmark.json` `editablePaths`, and
are unreachable from `Sources/`; `GenerationBatch` has zero hits under
`Sources/`; the only scored `compile()` sites are `LagunaRuntimeModel.swift:5554`
and `:5576`; `MLXHardwareInfo.isCompiledDecodeSupported` defaults true.

**VERIFIED by the agent (code read, not re-checked by the advisor):** decode
round-trip and timer placement; the worker decode handler and its
phase-agnosticity rule; `lagunaLogits` / `greedyToken`; the asyncEval ladder and
its M4 numbers; the `device.cpp:547-548` read-after-read line.

**INFERRED (flagged, not measured):** ~406 dispatches/step; the composition of
the 249 µs gap; that M5 carries an M4-like gap at all; the drain share of the
2.34 µs price; the lm_head byte pool available to an int3 scan.
