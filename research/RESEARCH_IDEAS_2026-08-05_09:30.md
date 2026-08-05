# RESEARCH IDEAS — 2026-08-05 09:30 UTC

Advisor-side idea slate for the next assignment round. Ideas only; nothing
here is implemented. All magnitudes use the official M5 anchors
(S = 97.863 ms prefill, T = 4.3224 ms/decode-step) and the measured score
elasticities from `research/CURRENT_RESEARCH_STATE.md`
(1% T reduction → +0.638% score; 1% S reduction → +0.362% score; the decode
window includes the 512-token seed, which is why these differ from the raw
0.75/0.25 exponents). Detection floor for one paired receipt pair (two n=3
families) is 0.243% score at 2σ. Receipts are ~35 min, concurrent-safe, and
publish full metrics even on `rejected`.

This slate deliberately does not restate the four live experiments
(fern #40 gather-GEMM double-buffering; frieren #35 r2 scale-code narrowing +
transfer calibration; tanjiro #34 r2 dispatch-saturation law; nezuko #32 r2
byte/latency census + K1) and does not re-litigate closed families except
where explicitly argued.

---

## 1. Where the headroom is, and the assumption the programme leans on

**What the record says.** The visible field gap is 0.64%; the campaign needs
+1.0–2.0% content. Two internal prizes dwarf that gap:

- **Prefill:** tanjiro #27 measured overlap+glue at 46 ms (43–49), i.e.
  44–51% of S₀. Fern #40 owns only the routed gather-GEMM staging↔MMA overlap
  slice of it (~15.4 ms recoverable). The remaining **~20 ms of prefill
  residual is unattributed and unowned** — spread across attn_core
  (161.1 GFLOP, never measured on M5), shared_expert (125.6 GFLOP / 69 MB,
  never measured), the MoE sort/gather/scatter chain, and elementwise glue.
  Full recovery would be worth ~+7.4% score; half is +3.7%.
- **Decode:** roofline says 1794 MB/token / 610 GB/s = 2.941 ms; measured T is
  4.3224 ms. The two big QMV families explain 75.5% of bytes with only
  +0.106 ms excess, leaving **~1.27 ms/step (29% of T) unattributed**.
  #32/#34 own the *measurement*; **no experiment owns a mechanism**.
  Recovering a third is ~+6% score.

**The untested assumption.** The programme treats "GPU busy" as "GPU useful."
Prefill was recorded as 99.4% GPU-busy with host/cb closed, and the residual
was mentally filed under the (assigned) gather-GEMM overlap prize — but #27's
own numbers say the glue pool is ~3× what #40 chases. Symmetrically on
decode, all live arms are measurement arms, while the one *causal* decode
mechanism the programme has ever proven on M5 — encoder-wide barrier
scheduling, via `DARKBLOOM_SHARED_FIRST_DOWN`, which moved decode by
0.10 ms/step on pure reordering — sits unowned as an opt-in flag rather than
being extended. The slate below is built to convert those two unowned
residuals into named, owned mechanisms, plus a small number of cheap
one-receipt flips.

> **ADVISOR CORRECTION (meridian, 2026-08-05).** The `SHARED_FIRST_DOWN`
> measurement is a **+0.10 ms/step REGRESSION**, not a win
> (`LagunaRuntimeModel.swift:7630-7645`; corroborated
> `research/frieren-pr23-result.md:212`, `CURRENT_RESEARCH_STATE.md:687`). The
> flag is correctly shipped OFF and flipping it ON would **cost** ~1.5% of
> score. The shipped routed-first order already overlaps the shared QMV with
> the routed QMV; shared-first puts the top-8 barrier ahead of both and
> lengthens the critical path. What survives is the *lever*, not a free win:
> encode order is a bit-exact, M5-measurable control with ~2.3%-of-T of
> demonstrated authority over decode time, and we have only ever measured it
> in the losing direction at one site. Idea 2 remains live on that basis. Its
> "already-proven single reorder = +1.5%" line is void.

**Standing constraint that gates several ideas:** submission byte headroom is
59,027 B total and `LagunaRuntimeModel.swift` has only 15,759 B under its
per-file cap. Authorised reclamation (#27 instrument block
`LagunaRuntimeModel.swift:10975–11223` ≈ 12,134 B; Metal-literal minification
≈ 54,251 B; 108 stale `DARKBLOOM_*` flags) should be sequenced *before* any
Swift-heavy idea below.

---

## 2. Ranked ideas

### Idea 1 — P-GLUE: name the ~20 ms of unowned prefill glue (census → targeted kill)

- **Hypothesis.** The ~20 ms of prefill wall not covered by roofline blocks
  or #40's overlap slice is concentrated in ≤3 nameable op families (MoE
  routing/sort/scatter chain, attention core, shared expert, materialised
  elementwise), not smeared uniformly.
- **Mechanism.** Prefill busy ≠ useful. The roofline table prices only the
  large GEMM blocks; attn_core and shared_expert were never measured on M5;
  the routing chain (`argPartition`/`takeAlong` at
  `LagunaRuntimeModel.swift:9429–9431`, sort-based gather/scatter in
  SwitchGLU `:9659–9694`) is a cascade of small ops with materialisation
  between large GEMMs. tanjiro's receipt-differencing method (#27) already
  works at block level; extend it to these blocks.
- **Magnitude.** Prefill: attribution itself is 0, but the downstream kills
  are the largest unowned prize on the board — half-recovery = −10 ms S =
  +3.7% score; full = +7.4%. Decode: 0 (separate path).
- **Legality.** Pure measurement, then behaviour-preserving fusion/removal.
  No serial-rule or precision interaction.
- **Bytes.** Census: 0 permanent (instrument blocks are temporary; reclaim as
  in #27). Fixes land in roomy Metal files (`quantized.cpp` 442,957 spare;
  `jit_kernels.cpp` 473,920 spare).
- **Cheapest screen.** M4 *can* enumerate the op sequence and dispatch counts
  (graph is identical; only GEMM kernel selection differs — the M4 blindness
  is to `_nax` GEMM *time*, not to op inventory). Then 2–3 M5 receipt
  families with block-level timer differencing.
- **Good null.** Census shows no family ≥ 2 ms (glue smeared < 1 ms/family
  across dozens of ops). That is itself decisive: it kills per-op fusion for
  prefill and redirects the whole prefill effort to encoder/command-buffer
  restructuring or to accepting #40 as the last prefill prize.
- **Confidence.** High that the census resolves (method proven in #27);
  medium (~50%) that a single family holds ≥ 8 ms.

### Idea 2 — D-STRAND: decode independent-strand overlap via barrier/encoder scheduling

- **Hypothesis.** Part of the 1.27 ms decode residual is serialisation of
  data-independent strands (shared-expert K1 QMV and router → top-8 → routed
  chain; gate_sp vs o_proj input prep) caused by encoder-wide Metal barriers,
  and ordering/encoder-split changes alone recover 0.1–0.3 ms/step.
- **Mechanism.** Measured decode concurrency is exactly zero (gpu_busy_sum ==
  union to 6 ns) across ~406 dispatches and 45 command buffers/step. Metal
  memory barriers are encoder-wide, not per-resource — proven on M5 by
  `DARKBLOOM_SHARED_FIRST_DOWN`, where *pure reordering* of shared-expert
  work moved +0.10 ms/step. The small-kernel pool that could hide inside big
  QMVs is ~0.59 ms/step (gate_sp 213 µs + K1 ~243 µs + router ~96 µs + rms
  ~36 µs), all at 0–73% of ceiling.
- **Magnitude.** Decode: hiding half the pool = −0.3 ms T = +4.4% score.
  Prefill: ~0 (prefill is 99.4% busy; strands there are GEMM-bound).
  **VOID (advisor):** the former second clause claimed the proven reorder was
  worth −0.10 ms/+1.5%. It is a +0.10 ms regression; see the correction box
  above. The demonstrated quantity is the *authority* of encode order over
  decode time (0.10 ms/step = 2.3% of T at one site), not a banked win.
- **Legality.** Pure scheduling; same kernels, operands, FMA order →
  bit-exact. Serial rule untouched (all work belongs to the supplied token).
- **Bytes.** 2–6 KB Swift in `LagunaRuntimeModel.swift` — gated on
  reclamation (only 15,759 B spare). No Metal edits for the ordering arm.
- **Cheapest screen.** Decode steady-step is 100% host-independent
  (hand-written `laguna_*` kernels on both hosts), so M4 gives a directional
  wall-clock sign for GPU-side serialisation; M5 receipt decides (M4
  concurrency structure may differ by GPU generation). First arm: apply the
  SHARED_FIRST_DOWN *method* (bit-exact input permutation, renamed kernel) to
  the router strand — one receipt. Note the sign lesson from that site: the
  win comes from removing a barrier that stands between two already-adjacent
  independent strands, not from moving small work earlier. Audit where each
  encoder-wide barrier actually falls before choosing a permutation.
- **Good null.** Reorders and encoder splits move M4 by <0.05 ms and the M5
  receipt by <0.243%: strand serialisation is not the residual, which
  *strengthens* the per-dispatch-overhead explanation and re-weights Idea 4.
- **Confidence.** Medium. This is the only decode mechanism with a ranked M5
  causal receipt already in hand; it is the cheapest path from measurement to
  mechanism ownership.

### Idea 3 — R-MBBUF: one-receipt `MLX_MAX_MB_PER_BUFFER` 200→400 flip (+ BFS width arm)

- **Hypothesis.** The wired-host command-buffer cap (set via `setenv
  MLX_MAX_MB_PER_BUFFER 200` behind `DARKBLOOM_POST_WIRE_COMMAND_BUFFER`,
  `LagunaRuntimeWeights.swift:381–389`, live only on ≥96 GiB hosts — i.e. on
  the ranked M5 but on no local M4) sits on the wrong side of the §E sign
  contradiction; flipping to 400 (arm 2: `MLX_BFS_MAX_WIDTH` 50→20) moves T
  by ±1–2%.
- **Mechanism.** The cap sets command-buffer split points → commit
  granularity → host/GPU pipelining. 45 cbs/step at ~1.33 µs measured
  overhead each; too-small caps starve pipelining, too-large delay first
  commit. The historical local measurements contradict each other in sign —
  and none of them ran with the ranked host's wiring active.
- **Magnitude.** Decode: ±0.05–0.10 ms/step = ±0.7–1.5% score. Prefill:
  unknown sign, ±1–2 ms = ±0.4–0.7%. Symmetric risk is exactly why this is
  a probe, not a ship-first change.
- **Legality.** Allocator/scheduling env only; bit-exact; serial rule
  untouched.
- **Bytes.** ~50 B (constant change).
- **Cheapest screen.** None exists locally (<96 GiB hosts never wire the
  flag; M4 pipelining differs regardless). One ranked receipt *is* the
  screen — the cheapest information purchase on the board (~35 min,
  concurrent with other receipts, `rejected` still publishes metrics).
- **Good null.** |Δ| < 0.243% on both axes ⇒ the cap is inert in the
  200–400 range; close held item 9 permanently and stop citing §E.
- **Confidence.** Low on sign, high on value-of-information per receipt-hour
  (top of the board on that metric).

### Idea 4 — D-FUSE-GATESP: fuse the unassigned `gate_sp` family into its neighbour

- **Hypothesis.** The `gate_sp_h64/h48` family
  (`laguna_gate_sp_h\(heads)_v1`, `LagunaRuntimeModel.swift:4356`; 40
  dispatches/step, 213 µs GPU, 0.033 MB, 2% of memory ceiling — marked
  UNASSIGNED in the nezuko #9 table) is pure launch latency and can be folded
  into the adjacent o_proj (which already reads the whole attention output,
  `:4409–4416`) for a near-pure dispatch-count win.
- **Mechanism.** A 5.32 µs kernel moving 0.033 MB has no memory or compute
  justification; its cost is launch + encode. Each dispatch also carries
  ~4.1 µs host encode/commit (rule 15). Fusing removes 40 GPU launches and 40
  host encodes per step.
- **Magnitude.** Decode: GPU-time-only bound = −0.21 ms = +3.1% score; with
  host encode exposure = up to −0.38 ms = +5.6%; realistic conditional
  estimate +1.5–3%, **conditional on #34's M5 saturation law showing tail
  dispatches are serially exposed**. Prefill: ~0 (amortised across 512 rows).
- **Legality.** Same math, fused. Bit-exact achievable: apply the per-head
  sigmoid gate elementwise with identical rounding before the unchanged QMV
  accumulation order. Inside the accepted attention envelope (no
  re-quantization involved).
- **Bytes.** Fused Metal kernel 3–8 KB in `jit_kernels.cpp` (473,920 spare) +
  ~2 KB Swift plumbing (needs reclamation headroom).
- **Cheapest screen.** M4 cannot see it (dispatch-count class sits under the
  M4 saturation knee: 1209 extra dispatches free vs ~406 issued). Sequence
  strictly after #34 reports; then one receipt family. M4 is still useful as
  a non-regression gate (regressions transfer in full).
- **Good null.** Receipt < 0.243% when the #34 law predicted ≥ 0.5% ⇒ the
  rule-15 host-overhead model is wrong for tail dispatches — feeds back into
  #34's interpretation, which is valuable either way.
- **Confidence.** Medium-high on mechanism, medium on magnitude (law-
  dependent). This is deliberately the *smallest clean* member of the fusion
  family — one kernel, one neighbour — not a speculative per-layer megafusion.

### Idea 5 — D-MLP: depth-2 weight staging in the routed decode QMV (memory-level parallelism)

- **Hypothesis.** The routed QMV's 546.2 GB/s (vs 610 stream and vs
  651.8 GB/s achieved by the qkv QMV) is in-flight-load-limited, not
  gather-fundamental; depth-2 staging per the R1-twin precedent
  (`LagunaRuntimeModel.swift:7325`) closes ≥ half the gap.
- **Mechanism.** Random 8-expert row gathers need more outstanding loads to
  cover DRAM latency; qkv proves the M5 memory system pays >100% of stream
  for well-pipelined gathered reads. The routed kernel already has a depth-1
  staging precedent in-tree to extend.
- **Magnitude.** Decode: routed bytes 552.08 MB/step; 546.2→610 GB/s saves
  552.08×(1/546.2 − 1/610) s ≈ 0.106 ms = +1.56% score at full closure;
  half-closure +0.78%. Prefill: 0 (prefill routed path is the `_nax` MMA
  gather-GEMM — fern #40's territory, different kernel).
- **Legality.** Load-schedule-only; FMA order preserved → bit-exact. No
  precision change.
- **Cheapest screen.** Same hand-written kernel family runs on M4 decode and
  the DRAM-byte/latency class transfers ~106%; but the kernel is already at
  93% of the *M4* ceiling, so M4 may mask wins — screen for sign +
  non-regression on M4, then 1–2 receipt families.
- **Bytes.** Metal in `fp_quantized_nax.h` twin (458,773 spare) /
  `quantized.cpp`; small Swift toggle.
- **Good null.** No M4 movement and receipt < 0.243% ⇒ 546.2 GB/s is the true
  ceiling for 8-expert random gathers (consistent with the closed
  access-pattern family's 87–94% band) — close permanently, and the decode
  residual story shifts fully to dispatch overhead + strands.
- **Confidence.** Medium-low on full closure, high on cheap falsifiability.

### Idea 6 — D-SPLITK: promote held item 8 — bit-exact fused split-K for NAX steel o_proj/g_proj/router

- **Hypothesis.** The three small NAX-steel GEMMs on the decode path leave
  ~0.53% score in launch + reduction overhead, recoverable by a fused
  split-K with a fixed, bit-exact reduction tree.
- **Mechanism.** Small-N GEMMs underfill the GPU; split-K raises occupancy;
  a *fixed* combine order keeps bit-exactness. Already priced by the board
  as held item 8; promoting it now is justified because it is one of the few
  NAX-adjacent ideas with a *local* falsification path.
- **Magnitude.** Decode: ~−0.036 ms = +0.53% score (board pricing). Prefill:
  ~0.
- **Legality.** Bit-exact by constructed reduction order; no precision
  change; serial rule untouched.
- **Bytes.** Metal header (`fp_quantized_nax.h`, 458,773 spare) + small
  Swift.
- **Cheapest screen.** Locally falsifiable on the non-NAX twin (rare for
  this class), then one receipt.
- **Good null.** Twin shows no win ⇒ launch overhead is already hidden
  behind neighbouring work; close held item 8 with evidence instead of
  leaving it in limbo.
- **Confidence.** Medium; modest but cheap, and it retires a held item
  either way.

### Idea 7 — D-PIPE-ATTN: software-pipeline next K-tile loads across the sliding-attention reduction

- **Hypothesis.** The fused sliding-window attention kernel (30 × 22.34 µs,
  issue-bound) stalls during the ascending-xor `simd_sum` butterfly;
  prefetching the next iteration's K/V tile during the reduction hides DRAM
  latency and recovers 8–15% of kernel time.
- **Mechanism.** #36 closed reduction *shortening* (the butterfly is
  depth/ILP-bound, not instruction-count-bound) — but the state file itself
  names cross-reduction load pipelining as the one remaining lever, and no
  experiment owns it. This is latency *hiding*, orthogonal to #36's closure.
- **Magnitude.** Decode: pool = 30 × 22.34 µs = 670 µs/step; 15% = −0.10 ms
  = +1.5% score; 8% = +0.8%. Prefill: 0 (different attention kernel family).
- **Legality.** Load scheduling only; FMA and reduction order unchanged →
  bit-exact.
- **Bytes.** 1–2 KB in the `laguna_*` attention Metal source + its
  `mlx-generated/*.cpp` twin (both roomy).
- **Cheapest screen.** Fully local: decode steady-step kernels are
  host-independent and geometry is fixed, so an M4 kernel-time A/B is valid
  evidence for this class. Then one receipt.
- **Good null.** M4 kernel time unchanged ⇒ occupancy already covers the
  latency and 22.34 µs is genuinely issue-slot-bound, confirming #36's
  boundary from a second direction; close the last sliding-attention lever.
- **Confidence.** Medium-low (occupancy may already hide the loads), but the
  screen is fully local and cheap — good student-scale work.

### Idea 8 — X-MARGIN: argmax-margin census — price the bit-exactness tax (offline, doctrine review)

- **Hypothesis.** Checked greedy tokens carry logit margins that are many
  orders above reassociation-level FP noise, meaning the programme's
  self-imposed bit-exactness doctrine (as opposed to the official
  token-match gate + oracle tolerance, prefill max_abs 0.125) is blocking a
  legal class of faster kernels (reassociated reductions, free-order
  split-K, fused epilogues with different rounding) worth a cumulative
  +1–3%.
- **Mechanism.** Gates check tokens, not bits; the M5 is authoritative for
  near-ties. Today the programme cannot even *state* the minimum margin on
  any checked position — the doctrine is assumption, not measurement. An
  offline census (min/percentile logit gap on public fixtures across all
  512 + 128 checked positions, compared against measured kernel-noise
  envelopes ~1e-3 in bf16 accumulation) converts doctrine into a priced
  risk.
- **Magnitude.** Direct: 0. Enabling: unlocks or permanently closes the
  reassociation class across decode (attention reductions, split-K) and
  prefill (GEMM epilogues). Decode candidates alone plausibly +1–2%.
- **Legality.** Fully legal to measure. Any subsequent non-bit-exact kernel
  must still respect: token match on hidden 512-token teacher-forced cases,
  the oracle tolerance, and near-tie risk on M5 — which is exactly what the
  census prices. No quantization change (§F do-not-extend untouched; the
  precision *envelope* constrains stored-weight quantization, not FP
  execution order).
- **Bytes.** 0 scored bytes (offline analysis; instrument locally, do not
  submit instrumentation).
- **Cheapest screen.** Entirely local and offline; no receipt needed for the
  census itself.
- **Good null.** Min margin on *any* checked position < 10× the
  reassociation noise envelope ⇒ doctrine is correct; write the number down
  and never spend on this question again.
- **Confidence.** High the census is cheap and decisive; medium that it
  unlocks anything shippable. Worth doing precisely because it is the only
  idea that can *permanently* settle a standing programme-wide constraint.

### Idea 9 — D-TINY-LAT: geometry/latency retune batch for the decode tiny-kernel tail

- **Hypothesis.** After #34's law lands, a single batch retuning threadgroup
  geometry/occupancy for the latency-bound tail — `residual_rms_router`
  (39 × 6.81 µs, 60% ceiling), `decode_router` (39 × 2.47 µs, 0–1%), rms
  (41 × 0.87 µs), plus held item 6's lm_head exact-pass (76.6 µs/step,
  latency-bound) — recovers 0.10–0.20 ms/step in aggregate.
- **Mechanism.** Kernels at 0–60% of ceiling on ~0.5 ms/step of GPU time are
  latency- or occupancy-bound; geometry retunes are the standard lever. The
  lm_head exact-pass member is already board-priced as M5-only.
- **Magnitude.** Decode: −0.13 to −0.20 ms = +1.9% to +3.0% (aggregate,
  optimistic); realistic +0.8–1.5%. Prefill: 0.
- **Legality.** Geometry-only for kernels whose reduction order is
  per-thread-serial or already order-fixed; any member where geometry alters
  reduction order is excluded (or moved to the Idea-8-gated class).
  Bit-exact for the included members.
- **Bytes.** Small Metal + Swift constants; fits current headroom.
- **Cheapest screen.** M5-only for the latency-bound members (M4 latency
  structure differs; explicitly so for lm_head exact-pass). Batch the whole
  tail into 1–2 receipt families with per-member flags so one receipt pair
  attributes sign per member.
- **Good null.** Aggregate < 0.243% ⇒ the tail is launch-bound, not
  geometry-bound — which re-weights Idea 4 (fusion) as the only remaining
  lever for the tail.
- **Confidence.** Medium-low per member, medium as a batch; strictly
  sequenced after #34.

### Idea 10 — P-ROUTE-FUSE: fuse the prefill MoE routing chain (conditional on Idea 1)

- **Hypothesis.** The prefill routing chain — `argPartition(-scores, kth:
  topK-1)` + `takeAlong` (`LagunaRuntimeModel.swift:9429–9431`) plus the
  sort-based gather/scatter in SwitchGLU (`:9659–9694`) — spends more time
  in sort/permute glue and materialisation than the router GEMM itself
  (20.9 GFLOP / 40.9 MB), and a fused top-8 + counting-sort kernel recovers
  2–4 ms of prefill.
- **Mechanism.** 512 tokens × 256 experts × top-8 through a cascade of
  generic sort ops materialises multiple intermediates between large GEMMs.
  The decode path already proves bit-exact fusion of this exact selection is
  achievable: the hand-written decode router kernel
  (`LagunaRuntimeModel.swift:8311–9101`) documents bit-exact top-8
  reproducing the stable merge-argsort order — reuse that technique at
  batch=512.
- **Magnitude.** Prefill: if the Idea-1 census attributes ≥ 4 ms to the
  chain, fusion recovers 2–4 ms = +0.7–1.5% score. Decode: 0 (already
  fused).
- **Legality.** Must reproduce stable argsort merge order bit-exactly
  (technique in-tree); serial rule untouched; no precision change.
- **Bytes.** 4–8 KB Metal (`jit_kernels.cpp`) + ~2 KB Swift.
- **Cheapest screen.** M4-valid (the chain is standard MLX ops, not `_nax`
  GEMM; graph identical across hosts), so a local prefill wall-clock A/B
  screens it before any receipt. Caution flag: `DARKBLOOM_PREFILL_ROUTER_TOP8`
  ranked −0.68% — this neighbourhood has traps; that failure replaced the
  selection math wholesale, whereas this idea keeps selection bit-identical
  and removes only materialisation, but it still mandates census-first
  sizing.
- **Good null.** Census attributes < 2 ms to the chain ⇒ drop without
  building anything (that is the point of sequencing behind Idea 1).
- **Confidence.** Conditional; medium-low standalone, medium if the census
  flags the chain.

### Idea 11 — B-BYTES: byte reclamation as scheduled enabling work (sequencing, not novelty)

- **Hypothesis.** Ideas 2, 4, 9, 10 (Swift-side plumbing) are gated by the
  15,759 B `LagunaRuntimeModel.swift` per-file headroom; executing the
  already-authorised reclamations first (instrument block `:10975–11223`
  ≈ 12,134 B; Metal-literal minification ≈ 54,251 B across 71 literals; 108
  stale `DARKBLOOM_*` flags) unblocks the slate at zero timing risk.
- **Mechanism/Magnitude.** No direct score effect; pure headroom. Listed as a
  ranked item only so the round explicitly schedules it before Swift-heavy
  work rather than discovering the cap mid-experiment (local timing can pass
  a candidate the official static review refuses).
- **Legality/Bytes.** Negative bytes by construction; behaviour-preserving
  deletions; verify with the committed-contract check
  (`senpai/check-editable-budget.sh`) before assignment.
- **Cheapest screen.** `wc -c` + one local `--local-iterate` non-regression
  run; one receipt only if a flag deletion touches a live default.
- **Good null.** N/A (bookkeeping).
- **Confidence.** High; this is the cheapest way to stop byte pressure from
  silently shaping which mechanisms get tried.

---

## 3. Considered and rejected

- **lm_head 3-bit coarse plane / deeper cascade levels.** #37's certificate
  arithmetic closed level-0 screens: survivor blow-up makes total bytes
  worse. Nothing new to add; stays closed.
- **KV-cache byte reduction inside fused attention.** The kernels are not
  byte-bound (#21/#30/#36: issue/ILP-bound at 22–23 µs); sliding layers
  already cap at 512 positions. No mechanism.
- **Router/routing-score re-quantization.** Outside the accepted envelope
  (only Q/K/V/O + per-head g_proj INT8 g32 is permitted), and §F already
  rules the inherited NVFP4 attention bank "disclosed, do-not-extend."
  Rejected on legality.
- **Expert co-routing / physical expert re-layout on disk.** Decode gather
  measured at 87–94% of sequential across access patterns (closed family):
  DRAM random-access is layout-indifferent at this granularity; routing
  histogram (20.26% zero pairs, CV 1.80) doesn't change bytes moved per
  step. Prefill layout is #40's staging problem, already owned.
- **Decode-only duplicate routed weight bank (padded/transposed).**
  +14 GB-class peak-RAM risk against the 21.6 GB resident budget on a
  128 GB host shared with the harness, for a rate already inside the gather
  band. Poor risk/return.
- **Indirect command buffers / CUDA-Graphs-style step replay.** The encode
  loop lives in `device.cpp`/`eval.cpp`-class MLX internals that are not on
  the editable-paths surface; the editable dispatch files can't hold the
  replay machinery. Falls outside the submission surface.
- **Persistent megakernel for the whole decode step.** Argument-buffer
  plumbing + Swift-side rewrite blows the per-file byte cap and collapses
  attribution; Idea 4 (single smallest fusion) plus #34's law is the
  disciplined version of the same intuition.
- **Speculative/lookahead anything** (prompt-lookup, multi-row future
  tokens, deferred KV): excluded by the serial non-speculative track rules
  even when bit-exact. Not proposed.
- **Token-keyed caching of prompt results or KV.** Explicitly prohibited
  (benchmark repetition is not a real workload). Not proposed.
- **Re-litigating closed families** (offline codes/scales interleave;
  MLX_METAL_FAST_SYNCH; MLX_MAX_OPS_PER_BUFFER ≥40; h×s=64 rebalance; BM
  widening / sub-16 SM / zero-row skip; vector-width reduction changes in
  fused attention; dense-attn-GEMM-misses-NAX). Reviewed each closure's
  evidence; none rests on an assumption this slate contradicts — with the
  single argued exception that Idea 7 targets a lever #36 *named but did not
  test* (load pipelining), not the lever it closed (reduction shortening).
- **M4-first screening of `_nax` prefill kernels.** 94.2% of M5 prefill time
  runs kernels an M4 never selects; #35 owns the transfer-calibration
  question. Any prefill idea above that touches `_nax` paths defers to
  receipts, not local timing.

---

*Advisor slate only — no code changed. Byte figures, timings, elasticities,
and line references are from `research/CURRENT_RESEARCH_STATE.md` (read
2026-08-05) and direct greps of the working tree at the same time.*
