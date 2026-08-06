# RESEARCH IDEAS — 2026-08-06 18:30 UTC (external advisor review)

Written by a fresh senior systems advisor asked to stress-test the prefill
reframe and break the 3-round plateau (rounds 19-21: 4 merged PRs, zero scored
bytes, frontier `1d12077a`, officialScore 2.58882784082067).

Score calculus used throughout (from program.md + receipt feed):
`score = decode_su^0.75 · prefill_su^0.25`; S = seed-512 forward, T = steady
decode step; on M5 S ≈ 100 ms, T ≈ 4.36 ms, D = S/128 + T ≈ 5.14 ms.
Elasticities: **S 0.362, T 0.638**. Rules of thumb: **−1 ms of S = +0.362%
score; −1 µs of T = +0.01464% score.**

---

## 1. Critique of the reframe ("noise floor kills local decidability, receipts are the instrument, prefill is the open axis")

**Mostly correct, with three breaks that must be engineered around, not
ignored.**

Correct parts:
- The M4 ±0.73% decode noise floor really does exceed nearly every surviving
  decode arm (realistic remaining decode inventory ≈ 1.4% score at ~50%
  removal). Local timing can no longer *decide*; it can only *screen*.
- Official receipts return full metrics even on `rejected` (~35 min round
  trip), and the renormalised statistic `ns = nd^0.75·np^0.25` pools to cv
  0.149%. Three receipts per family gives 2σ ≈ 0.243% — an instrument ~6×
  sharper than local M4.
- Prefill inventory is real: gather-GEMM runs at roughly half of both M5
  rooflines (≈28.8 TFLOP/s of ~57, ≈272 GB/s of ~546), the MMA row-padding
  ratio is a *measured* 1.456× issue inflation, and 51.9/256 expert columns
  launch zero rows. My own decomposition of S ≈ 100 ms: weight-slab DRAM
  ≈ 22 ms, ideal MMA ≈ 18-20 ms, padded MMA ≈ 26-29 ms — leaving **~20+ ms of
  slack** (staging serialisation, issue inefficiency, empty/imbalanced
  threadgroups). Prefill has been touched by ~zero of the field's 100+
  submissions.

Break #1 — **the binding constraint becomes receipt throughput, not ideas.**
One in-flight submission at a time (CRS §0.9.28), a shared ranked account
(§0.9.34), ~35 min/receipt, ~3 receipts/family: the round budget is ~10-15
receipts. The reframe is only operational if the round is *planned as a
receipt schedule* (families, riders, kill rules) the way beam time is
scheduled at an accelerator. Ideas that cannot pre-commit a receipt count
should not start.

Break #2 — **M4-blindness for `_nax` is correctness-blindness, not just
timing-blindness.** M4 (Apple GPU gen 16) fails `is_nax_available()`
(device.cpp:913-931) and *never executes* the edited kernel: a silently-broken
`_nax` change passes every local gate and burns a receipt (or worse, a
correctness gate) on the M5. Known silent-failure modes: odd TN>1 → empty MMA;
SM<16 → TM=0; falling off the accept gate (quantized.cpp:1660-1663,
`bm==64 && wm==4 && (wn==2||wn==1)`) silently dispatches the non-expert
kernel. Every `_nax` arm must ship with (a) a process-constant env
kill-switch (research/PREFILL_NAX_ANALYSIS.md:165-176 precedent), (b) an
offline compile + pipeline-stat check (research/nax_msl_compile_check.sh and
the tanjiro probe compile NAX MSL fine on M4 — execution is what's gated, not
compilation), and (c) a positive "expert kernel actually selected" assert.

Break #3 — **the 7-9 significant figures are clock precision, not process
precision, and S is bimodal.** `baseline_prefill` shows a 3.61% gap between
session modes (rel sd 1.932% vs decode's 0.248%). `ns` does *not* cancel a
session-level prefill mode (it renormalises by pinned calibration, not by the
same-session baseline), while the paired `prefill_speedup` partially does.
The dispatch-table comment at quantized.cpp:1471-1475 shows the team already
once had to un-reject a real mechanism ("earlier rejections were
session-baseline draw fog") using API absolutes across four sessions. So the
reframe's "receipts make prefill as measurable as decode" is *not yet true*:
first fit a two-mode model of S from the existing receipt corpus (zero GPU),
decide the estimator (within-mode `ns`, or mode-classified paired speedup),
and only then spend prefill receipts. Also note elasticity honesty: 0.362
decays as S shrinks (∂ is on *current* S); a −15 ms programme delivers ~+5.2%,
not 15×0.362.

Concrete example of the receipt-burn risk the reframe must manage: **the
promoted C2 arm (BN 64→32) as specified collides with the shipped swiglu
epilogue.** The default variant is 5 = BM64/WM4/**WN1** (quantized.cpp:1468-
1478), so `kSwigluRegLocal = (WN==1 && BN==64 && SM==16)` is *active*
(fp_quantized_nax.h:1656-1657). BN=32 breaks it — and worse, the fused
gate_up layout pairs gate column c with up column c+32 *inside one 64-wide
tile* (fp_quantized_nax.h:1645-1655): with BN=32 a tile holds only gate or
only up columns, so in-kernel swiglu is impossible for the N=1024/K=2048
shape, not merely slower. C2 must be re-scoped to the down projection
(N=2048/K=512, no epilogue) or carry an epilogue redesign, or it will burn
its receipts on a regression/mismatch.

---

## 2. Why three rounds shipped zero scored bytes (ranked)

1. **The programme optimised its instrument instead of the model.** Rounds
   19-21 produced laws §0.9.37-40, a "price-of-a-byte" crisis declared
   higher-value than any arm (§R21.1), and merged PRs (#71, #73, #104, #110
   class) that are research-only *by design*. Meanwhile the admissibility
   bars derived from that instrument (0.278% single-receipt MDE, 0.61%
   advisor bar, ~27.8 MB decode-byte floor) exclude nearly every remaining
   decode arm — the bars were sharpened until nothing passes, on an axis
   whose whole realistic inventory is ~1.4%. Measurement rigor rose;
   scored-byte throughput fell to zero.

2. **Receipt starvation by channel discipline + bundling ambition.** One
   in-flight submission (§0.9.28), a shared account (§0.9.34), a blocked
   human channel (§R21.7), and a ~1%-of-ns bundling bar (§R18.9) mean the
   cheap measurement the team *knows* it has (rejected receipts return full
   metrics) is treated as precious. Evidence: C2 was promoted "strongest
   prefill arm" two rounds ago and still has zero receipts.

3. **The decode-first frame outlived its evidence.** Decode kernels are at
   94.6-100.2% of the M4 bandwidth ceiling (only residual_rms_router 61.8%
   and gate_sp are not saturated), yet assignments kept mining decode bytes.
   Prefill was "unowned by choice" after three nulls (#24, #37, #40) —
   availability bias: those tested *one* axis (staging overlap) of a
   ~40-50 ms kernel family with ~20 ms of non-byte slack, and the axis
   closure was generalised to the whole seed forward.

---

## 3. Six new falsifiable hypotheses

Format: mechanism → files → first-principles arithmetic → cheapest decisive
falsifier → bit-exactness. None is in the closed list; adjacency is argued
where it exists. All live inside `benchmark.json` editablePaths; all
falsifiers are offline/local-first; every `_nax` arm carries the env
kill-switch + accept-gate assert from §1.

### H1 — Row-count-adaptive dual-path gather kernel (small experts leave MMA)

**Mechanism.** In `fp_gather_qmm_rhs_expert_nax` (fp_quantized_nax.h:1568-
1900) every expert pays the full tile machinery regardless of run length: Ws
staging of a 64×64 weight tile per k-iteration (32 iterations for gate_up, 8
for down), two barriers per iteration, and MMA issue padded to 16-row
fragments (measured 1.456× rows-issued/useful). Mean rows/expert is
512·8/256 = **16**, and routing is skewed (51.9 experts get 0 rows), so a
large fraction of experts carry 1-15 rows — for them the tile path is mostly
overhead. Add a per-expert-slot branch: if `n_e < 16`, compute the run with a
QMV-style per-row dot-product loop (all 128 lanes on real rows, weights
streamed through registers, no Ws staging, no barriers, no padding); else take
the existing MMA path unchanged. This is **not** the closed "sub-16 SM" arm
(it does not shrink the MMA fragment; it removes MMA for runs where MMA
cannot win) and not the closed staging/prefetch family (no change to the MMA
path's staging).

**Files.** fp_quantized_nax.h (new branch inside the expert loop) + its
generated twin `mlx-generated/fp_quantized_nax.cpp` (JIT source of truth) +
`jit_kernels.cpp` if a new template arg is added; dispatch untouched
(quantized.cpp:1660-1663 gate unchanged).

**Arithmetic.** Padding removal alone: issue ratio 1.456→~1.10 on the
small-expert mass ≈ −25% of MMA issue. With gather ≈ 40-50 ms of S and
MMA-issue+staging ≈ 60% of it, saving 30-40% of the small-expert share ≈
**−4…−8 ms of S → +1.4…+2.9% score.**

**Falsifier (zero receipts first).** Instrument routing locally (research
harness, M4 is fine — routing is model math, not NAX) to get the exact
rows-per-expert histogram for the 512-token fixture; compute exactly which
fraction of (expert × col-tile) work items fall under the threshold and the
padded-fragment + barrier count removed. If < 20% of gather work is
small-expert, kill before writing kernel code. Then 2-3 receipts.

**Bit-exact: NO** (per-output FMA order changes for small experts). Defensible:
decode already computes the *same* experts with QMV-order accumulation — the
phase-dependent-numerics precedent ships today; the gate is greedy tokens +
the 64-step tripwire, and `run_upstream_equivalence.sh` is the pre-receipt
screen. This is the main risk; the kill-switch env restores single-path.

### H2 — Device-compacted, LPT-ordered expert work queue via indirect dispatch

**Mechanism.** grid.y is unconditionally `egroups = 256`
(quantized.cpp:1920-1923): 51.9 empty experts × 16 col-tiles × 39 layers ≈
32k no-op threadgroup launches per prefill, and the 40-core M5 tail is set by
the largest expert because scheduling order is expert-index, not size. Add a
tiny device kernel after routing that writes (a) a compacted list of
non-empty (expert, row-start, row-count) tuples sorted largest-first (LPT)
and (b) a threadgroups-per-grid triple into a small buffer; dispatch the
gather kernel with `dispatchThreadgroups(indirectBuffer:)` — we own the
encoder call in quantized.cpp. This *answers* E3's recorded objection (host
would stall syncing the device row count) instead of re-proposing E3: the
count never reaches the host. Not the closed "dispatch-count reduction"
family (that closure was encoder/command-buffer overhead; this removes
*scheduled no-op work* and reorders real work).

**Files.** quantized.cpp (encoder + new prep kernel dispatch),
fp_quantized_nax.h + generated twin (read slot from queue via tid.y),
possibly steel/gemm headers untouched.

**Arithmetic.** Empty-launch cost was priced O(0.3-1.5 ms); LPT tail
flattening on 40 cores with a skewed size distribution is typically another
1-2% of the kernel: **−1…−3 ms of S → +0.4…+1.1%.** Pairs multiplicatively
with H1 (same queue can carry the small/large classification).

**Falsifier.** Same offline histogram as H1 → exact empty-launch count and a
simulated LPT vs index-order makespan on 40 cores (pure arithmetic). If
simulated makespan gain < 1 ms, demote to rider on H1. Then 2 receipts.

**Bit-exact: YES** (identical per-expert work and accumulation order;
execution order across threadgroups is already unordered).

### H3 — BK 64→128: halve the k-loop trip count of the staged MMA path

**Mechanism.** The inner loop runs K/BK iterations, each = full-TG Ws stage +
2 barriers + 2 unrolled SK=32 MMA steps (fp_quantized_nax.h:1717-1839).
gate_up: 32 iterations; down: 8. Doubling BK to 128 halves iterations and
barrier count and doubles MMA work per stage (4 unrolled steps), improving
issue density between synchronisation points. This is *not* the closed
staging/prefetch/double-buffer family (no new buffering or overlap; the
schedule stays load→barrier→MMA) and not the closed "in-kernel barrier"
family (barriers per stage unchanged; stages per output halve). It is
adjacent to closed geometry re-tiling — the difference is that it is
receipt-decided (per §1) and screened by *offline occupancy math*, not M4
timing.

**Files.** quantized.cpp:1634-1645 (BK constant + gate `align_K` already
holds: 2048%128=0, 512%128=0), fp_quantized_nax.h template + generated twin,
jit_kernels.cpp instantiation.

**Arithmetic.** Ws grows 64×(64+pad)×2B ≈ 9.2 KB → 64×(128+8)×2B ≈ 17.4 KB.
Occupancy: at a 32 KB threadgroup pool this drops resident TGs 3→1 — the
falsifier below decides; if the pool is 64 KB (family-9 M5), 3→3 with no
loss. Barrier/stage overhead is plausibly 10-20% of gather time:
**−2…−5 ms of S → +0.7…+1.8%**, contingent on occupancy.

**Falsifier (offline, zero GPU-receipts).** Compile the modified MSL with
research/nax_msl_compile_check.sh + the tanjiro probe
(research/tanjiro_gathergemm_occupancy_probe.swift measured
staticThreadgroupMemoryLength=9232 B, maxTotalThreadsPerThreadgroup=1024 on
the shipped kernel) and read the new static TG memory +
`maxTotalThreadsPerThreadgroup`; if resident-TG arithmetic says occupancy
halves, kill or scope to down-only (K_it 8→4, same Ws growth). Then 2
receipts as one family with the C2-fix (below).

**Bit-exact: YES** (same k-ascending accumulation per output; BK partitions
the same ordered sum — verify with the upstream-equivalence oracle).

### H4 — Checkpoint structure: expert-slab dedup + NVFP4 scale-plane census

**Mechanism.** Laguna XS is an upcycled/routed checkpoint; upcycling and
distillation commonly leave (a) bit-identical expert row-slabs across experts
in some layers, (b) constant or low-entropy NVFP4 scale planes (the stride-4
scale-constancy census R6a was queued but never run), (c) zero cachelines
(R6b). Exploits, in increasing ambition: merge row runs of bit-identical
experts at sort time (host side, `LagunaRuntimeModel`/transform metadata) so
one staging serves two experts' rows — fewer stagings, less padding,
bit-exact; skip scale loads where a tile's scale plane is constant (encode a
per-tile flag in transform metadata, branch in the loader).

**Files.** Sources/MLXFastTransform (offline census + metadata),
Sources/MLXFastModel/LagunaRuntimeModel.swift (sort-time merge),
fp_quantized_nax.h + twin only for the scale-flag variant.

**Arithmetic.** Fully determined by hit rate, which is *free to measure*: a
10% dedup/merge rate ≈ 10% of staging+padding ≈ −2-4 ms S (+0.7-1.4%); a
null result costs one CPU-hour and zero receipts. This is the only hypothesis
class whose falsifier is literally a file scan of the 21.6 GB checkpoint.

**Falsifier.** Offline scan (research tooling, not runtime): hash 16-row×BK
slabs per expert per layer; histogram collisions; report merge-able row mass.
Kill at < 5%.

**Bit-exact: YES** for dedup-merge (identical bytes ⇒ identical products);
scale-flag variant also bit-exact (same values, fewer loads).

### H5 — Per-expert fused FFN: gate_up → swiglu → down in one kernel

**Mechanism.** Today each MoE layer runs two gather-GEMMs with a DRAM round
trip between them: the swiglu output (4096 rows × 512 cols BF16 ≈ 4.2 MB) is
written and re-read, and the down pass re-stages x and re-searches bounds.
Fuse per expert: a threadgroup that owns an expert's 64-row chunk computes
its gate_up columns, applies swiglu, keeps the 64×512 BF16 activation
(64 KB — too big; stage per 16-row fragment: 16×512×2B = 16 KB) in
threadgroup memory, then runs the down GEMM from it. Removes the intermediate
write+read (≈ 2×4.2 MB×39 ≈ 327 MB), the second kernel's x-loads and bounds
searches, and halves dispatch waves. Adjacent to nothing closed (kernel
*fusion* across the swiglu boundary was never tested; R5 refuted only
*glue-op* cost).

**Files.** fp_quantized_nax.h + twin (new fused kernel), quantized.cpp
(dispatch), LagunaRuntimeModel.swift (call the fused op).

**Arithmetic.** DRAM saved ≈ 327 MB + down-pass x re-reads ≈ 134 MB/layer ×
39 ≈ 5.2 GB *if* those re-reads miss SLC — the honest range is 0.6 ms (SLC
absorbs everything but the 327 MB) to ~10 ms: **+0.2…+3.6%**, widest error
bars of the six.

**Falsifier first (paper, then local).** Bound SLC absorption: gate_up x is
16.8 MB/layer, down x 4.2 MB/layer vs M5 SLC (unknown, M1-Max-class chips
shipped 48 MB) — if the census says the re-read working set fits SLC, the
gain collapses to the 327 MB term (−0.6 ms, +0.22%) → kill. This one-page
arithmetic *precedes* any code. Only if it survives: 3 receipts.

**Bit-exact: YES if** the staged activation is stored as BF16 (same rounding
as the DRAM round trip) and k-order is preserved — both are design choices we
control.

### H6 — Decode rider: fix the one unsaturated kernel (`residual_rms_router`, 61.8%)

**Mechanism.** Every decode kernel is at 94.6-100.2% of the M4 bandwidth
ceiling except `residual_rms_router` (61.8%) and the latency-bound `gate_sp`
(30.4 GB/s; already owned by #101). The router plane reads 40.9 MB/step
(2048×256 BF16 × 39 layers). At M=1 the GEMV is latency-bound: too few rows
in flight per simdgroup and 2-byte-granular loads. Offline-transpose the
router weights to a layout enabling `float4`/8-wide coalesced loads and
process 2 output rows per simdgroup (row-pair interleave in the transform,
consumed by a small loader change) — a *data-layout* change, not the closed
occupancy re-tiling family (no threadgroup geometry claim, and decode
transfers M4→M5 in kernel family).

**Files.** Sources/MLXFastTransform (layout), the router GEMV kernel source
in Sources/MLXFastModel (or the MLXLMCommon MoE gate helper on the scored
path), no `_nax` involvement.

**Arithmetic.** 40.9 MB at 61.8%→95% of 546 GB/s: 121 µs → 79 µs =
**−42 µs of T → +0.62% score.**

**Falsifier.** M4 per-kernel microbench (the per-kernel table that produced
61.8% already exists — rerun with the new layout; decode kernel families
transfer M4→M5 directionally). Local, zero receipts; then 1-2 receipts.

**Bit-exact: YES** (same dot products; layout permutation only), verify with
the oracle since router near-ties choose experts.

---

## 4. Bet-the-round (4 students, 24 h): "Own the seed forward"

Rationale: decode inventory is ~1.4% and saturated; the seed forward holds
~20 ms of measured slack and elasticity 0.362. Target: **−8…−15 ms of S ≈
+3…+5.4% score**, decided by receipts, screened offline.

- **Student A (zero-GPU, day 1): S-mode receipt model + receipt schedule.**
  Fit the bimodal baseline_prefill structure from the existing receipt corpus
  + the 3-receipt control (`f8502e12`,`71586bcf`,`f3cda678`); publish the
  estimator (within-mode ns vs paired speedup) and the round's receipt
  schedule. Unblocks every other student's measurement. Also: re-scope C2 to
  down-only (the BN=32 × `kSwigluRegLocal`/gate-up-pairing collision in §1).
- **Student B: H1 dual-path kernel** behind `DARKBLOOM_SMALL_EXPERT_QMV`,
  after the day-1 histogram falsifier; upstream-equivalence + tripwire before
  any receipt; 3 receipts.
- **Student C: H2 indirect-dispatch queue + H4 censuses.** Day 1: histogram,
  empty-launch count, LPT makespan simulation, slab-dedup scan (all offline).
  Day 2: implement the queue if ≥1 ms simulated, else promote H4 merge if
  dedup ≥5%; 2 receipts.
- **Student D: H3 BK=128 (+ C2-down) geometry family.** Offline pipeline-stat
  occupancy check first; ship as one 2-receipt family with kill-switch.

Stop rule: any family whose first receipt shows `ns` below the current best
minus 0.243% (2σ) is killed, not iterated. Receipt budget: ≤ 10.

— end —
