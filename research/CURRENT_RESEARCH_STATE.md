# SENPAI Research State

**Updated 2026-08-07 11:55 UTC — round 28 closed, round 29 launched.**

**This is a living document, not a log.** The round 22–28 chronology now lives in
[`RESEARCH_STATE_ARCHIVE_rounds-22-28.md`](RESEARCH_STATE_ARCHIVE_rounds-22-28.md);
everything before round 22 is in
[`RESEARCH_STATE_ARCHIVE_through-round-21.md`](RESEARCH_STATE_ARCHIVE_through-round-21.md).
Read those only for the derivation behind a number quoted here. **Keep this file
short. Prune it every round.**

## Most recent human/operator direction

`operator_nudge`, 2026-08-07 11:47 UTC — post-upgrade utilization check: assign
Fern, Tanjiro and Nezuko; **preserve Frieren's current work and do not duplicate or
reset it** merely because conversations were rotated. Acted on: three assignments
created (#268, #269, #270), Frieren deliberately not assigned.

Standing operator guidance still binding (§0a, `eae07f01`): the +0.61% advisor
acceptance bar is **deleted**; 0.243% is noise context, not a threshold; **one
receipt can justify a clear win**; student-host prefill work is endorsed for
implementation/correctness/reachability, just not for M5 *timing*.

## Where we stand

Frontier: promoted candidate `97a5090`, commit `3e165fa`, **rank 1**,
`officialScore = 2.58882784082067`, `ns = 2.5982163`, `S = 97.89475 ms`,
`T = 4.143569335937499 ms`. Base for round 29 is **`627c4973`** (merge of #241;
**zero submitted-surface bytes changed**).

Round 28 closed with two clean negatives and one structural finding:

- **#241 (fern) — merged.** Produced the round's headline result (below) plus three
  refutations: the `MLX_MAX_OPS_PER_BUFFER` / `MLX_MAX_MB_PER_BUFFER` axis is a clean
  null (0.00 ± 0.02 ms); the command-buffer *size-clause* hypothesis is dead (the
  size accumulator counts only unique inputs, `device.cpp:320`); and **work-elasticity
  E is not a fusion-selection criterion**.
- **#244 (tanjiro) — closed, clean negative.** Second independent refutation that the
  `_nax` inner loop is device-load-bound. The `_nax` load-amortization family is now
  closed.
- **#148 (frieren) — closed, unstarted and superseded.** Branch carried only the
  empty assignment commit.

## ⭐ The finding that now organises decode work: a flat per-dispatch tax

Injecting a real barrier-forcing dispatch into the live decode chain costs
**1.30–1.73 µs (pooled ≈1.4 µs, t = 15.6–56.0)**. The cost is **flat across sites
regardless of work-elasticity** — a site with E = −0.045 still pays 1.416 µs,
statistically identical to the most exposed site at 1.295 µs — and costs are
**additive** (observed/predicted 0.9608 ± 0.0500).

At ~400 dispatches/step this is **≈560 µs/step ≈ 6.8%** of the 8.20 ms M4 Pro step,
projecting to **≈283 µs/step on M5 ≈ a quarter of the ~1.20 ms unexplained decode
gap**. Perfect elimination of the whole tax ≈ **+5% score**.

Consequences already banked:
- **The selection criterion flips from work-elasticity to raw dispatch count.**
- One removed **per-layer** dispatch ≈ 27.6 µs/step M5 ≈ **0.42% score ≈ 1.80σ**
  (marginal alone). Bundling 3 ≈ 83 µs ≈ **1.3% ≈ 5.4σ**. Three is the practical
  minimum for a ranked arm.

**⚠ The mechanism is NOT established, and this is the campaign's biggest open risk.**
Flatness kills *site-local serial idle*, but a fixed per-dispatch cost is equally
predicted by: **E1** CPU-side graph-eval/encode starving the GPU; **E2** GPU
command-processor launch cost (barrier-independent); **E3** cache flush/invalidate
scaling with dirty footprint; **E4** residency/bookkeeping scaling with distinct
resources. (**E5** command-buffer commit is already refuted by the MAX_OPS null.)
**If the tax is CPU-encode starvation, hand-fusing Metal kernels is the wrong lever**
and indirect command buffers / encode overlap is the right one. Do not commission
bit-exact fused kernels until #268 reports.

Second unresolved unknown: **injection ≠ removal.** Named asymmetries — the barrier
may be re-triggered by another consumer; MLX resource tracking may just move the
serialization point; a fused kernel may repay saved launch time as recompute.

Caveats: measured on **M4 Pro** (48 GiB, 20 GPU cores, gen 16) — directional only;
the 1.4 µs constant has **never been measured on M5**. The 400 dispatches/step figure
is an estimate, replaceable by a counter in `maybeInsertBarrier`
(`device.cpp:363-366`). Reducer caveat: `fern_gap_stats.py` centres on the K=1 arm,
`fern_gap_wandb.py` on the block mean, so W&B `pooled/*` and `prize/*` read ~6% high —
**never compare a W&B t-stat with a doc t-stat**.

## Round 29 — in flight

| PR | Student | Hypothesis | Ranked slot |
|----|---------|-----------|-------------|
| #268 | maple-fern | **P0 gating**: attribute the 1.4 µs tax to E1–E4 (barrier counter, dependent-vs-independent injection, CPU busy-spin, `GPUStartTime`/`GPUEndTime`, footprint and resource sweeps) and price the refund (R1 self-fusion + diamond control). Decision rule: refund ≥1 µs ⇒ count reduction is the campaign; ≤0.3 µs ⇒ pivot to ICB/encode overlap. | none |
| #269 | maple-nezuko | **R2 hedge**: `compiled{}` fusion of real elementwise decode segments (router `normTopkProb` 9573, SwiGLU epilogue, residual chains). Robust to either E1 or E2 because it removes CPU ops *and* GPU dispatches. Rules-legal: MLX compile cache keys on shape/dtype, not tokens. | local-first |
| #270 | maple-tanjiro | **Non-MoE prefill census**: the ≈54.6 ms with no census at all, worth ≈20% of score at 0.374750 %/ms. Structural census + relative timing, every row flagged for M5 host divergence. | none |
| — | maple-frieren | Preserved per operator nudge. **Queued next**: byte-recovery cleanup carrying the `DARKBLOOM_LMHEAD_ROWMAJOR_REFINE` default flip (a twice-measured M5 negative; defaulting OFF recovers **+0.2237% `ns`**). | none |

**Region fences in `Sources/MLXFastModel/LagunaRuntimeModel.swift`** (11,073 lines,
three concurrent editors): 853–1097, 4623–5372, 5700–5800, 6700–6910, 7500–7700,
8329–8382, 8525–8910, 9466–9578, 10031–10120.

## ⚠ New binding constraints from round 28

1. **Content-hash dedupe (#244).** `mlxfast submit` deduplicates on the **content hash
   of the submitted editable surface**, not the commit SHA. A byte-exact control is
   silently resolved to a **stale cross-session receipt** and costs zero receipts —
   producing exactly the invalid cross-session comparison the matched-control rule
   (§3, #215) outlaws. **The matched-control doctrine is re-specified:** a control arm
   needs an inert, behaviour-neutral perturbation that changes the surface hash
   without changing emitted code, or must be replaced by a same-session A/B in which
   both arms are non-trivial. Never cite a receipt you did not watch being created.
2. **Never dispatch a ranked arm from an unpushed tree (#148).** Receipt `9631b9d`
   (commit `1201db1`, officialScore 1.64018613) is unverifiable and **must not be
   cited** anywhere.
3. **A deliberately-degraded ranked arm is structurally expensive** (#148): it
   consumes the scarce account-scoped slot and returns no candidate score. Justify it
   against the opportunity cost of a real candidate arm or do not assign it.
4. **`device.cpp` and `device.h` are NOT in `editablePaths`.** This kills the
   per-resource `memoryBarrier(resources:count:)` one-liner as a *shippable* change; a
   barrier counter there is a research-only instrument. `Transforms+Compile.swift` and
   `MLXFastKernel.swift` are likewise not editable — callable, not modifiable.
5. **Byte headroom is now a first-class constraint.** 2,950,855 / 3,000,000 bytes used
   ⇒ **49,145 B headroom**, 142 files. Per-PR growth target ≤ 12,000 B.
   `check-editable-budget.sh` requires the **full 40-char SHA**.

## No W&B channel for this target

The mlxfast harness publishes **no W&B runs**. **mlxfast receipt IDs are the canonical
experiment reference** for this campaign, and PR result comments carry the raw
`officialMetrics`. This is recorded, not a reporting failure; do not ask students for
W&B links they cannot produce.

## Next directions, ranked

1. **Resolve the tax mechanism (#268).** Everything below reorders on its answer.
2. **If GPU-paced**: structural dispatch-count reduction — the three verified fusion
   targets A (shared-expert gate/up QMV merged into the routed packed top-8 QMV),
   B (top-8 selection folded into the router kernel, which already computes the
   sigmoid score, bias-corrected key and ordinal *in registers* at lines 861–872), and
   C (input RMSNorm + QKV GEMV). Full code geography is in §4.
3. **If CPU-paced**: ICB pre-encoded step replay — highest ceiling of any decode idea.
   MoE routing does **not** block pre-encoding (expert choice is data, not dispatch
   structure); only KV length and RoPE position offset are dynamic, and both have
   known indirect-argument workarounds. Also: `start_concurrent()` batching
   (`device.h:88`, audit 1–2 spots) and CPU-side encode overlap. Skip MTLEvent /
   multi-queue.
4. **Prefill (25% weight, largely unexplored).** #270's census, plus the banked #170
   constraint: staging ≈49% load-issue / ≈51% DRAM bytes, pure-issue term 6.887 ms =
   15.9% of W = 43.2619 ms, streaming floor 24.15 ms ⇒ **19.11 ms headroom = 7.16% of
   score**.
5. **Kernel time remains the ~13× larger budget than the dispatch tax.** Keep a
   parallel track on it regardless of #268's verdict.
6. **tanjiro's surviving `win_ok` ctor-hoist** — an `sdiv` plus two modulo tests per
   k-iteration on loop-invariant inputs, unhoistable across the non-inlined call. This
   is an **ALU-issue** hypothesis and is untouched by #244's closure of the load-bound
   family. Reprice it if #270 finds an issue-bound prefill family.
7. **Byte recovery** (frieren, queued) — the `LMHEAD_ROWMAJOR_REFINE` default flip
   carries a real measured **+0.2237% `ns`**, so cleanup is not overhead here.
8. Lower priority: LPT expert→threadgroup permutation (simulate first, free);
   multi-chunk `Ws` accumulator blocking (only +8.0% redundancy); dense-GEMM prefill
   replication census; bf16 prefill-only attention scratch; RoPE-table precompute;
   offline scale-plane repack in `Sources/MLXFastTransform`.

## Re-classified: underpowered, not refuted

- **#204** — 39-dispatch side-branch deletion, −0.9 ± 29.7 µs at ~46% power.
- **#158** — observational −0.12 ± 0.22 µs/dispatch fit.

Both are *consistent with* the 1.4 µs tax; neither had the power to see it. Do not
cite them as evidence against dispatch-count reduction.

---
---

## 0a. Operator `eae07f01` — the heuristics that were softened

`eae07f01` ("Soften Maple research heuristics", mmcguire, 2026-08-06 21:55:23
UTC) edits `senpai/program.md` only (+66 / −55) and is now the remote head of
the advisor branch. Read it as a critique of *this* advisor: we have been
**too quick to close families and too rigid about numeric gates**. Each row
below is binding; the "was" column exists so nobody re-derives the old rule
from an older document.

| # | was | is now |
| --- | --- | --- |
| 1 | thread re-tiling "does **not** transfer; an M4 measurement is not evidence" | "is core-count sensitive; interpret M4 timing with **wave analysis** rather than presenting it as sufficient M5 evidence" |
| 2 | "**Never** run a prefill kernel experiment on a student host" | "**Use** student-host prefill experiments to validate implementation, correctness, reachability, or a hypothesis"; only their *timing* is not `_nax` ranking evidence |
| 3 | S/T decomposition mandatory "for every official run" | decompose "**when identifying where its gain came from**" |
| 4 | every submission needs "a family of at least three" | "**one receipt can justify a clear win or follow-up**"; repeat only for a marginal effect near observed variance |
| 5 | "**Never** rank by `officialScore`" | `officialScore` **is authoritative for leaderboard ranking**; it and the raw `*_speedup` fields are only *noisy for attributing a small mechanism across sessions* |
| 6 | 0.243% noise floor, "the advisor's acceptance bar is 2× that, **0.61%**" | that clause is **deleted**. 0.243% is "noise context, **not a universal submission or promotion threshold**" |
| 7 | a closed decode arm is "worth approximately nothing… do not reopen" | "**starts with low expected value**… revisit one when a proposal **identifies a new mechanism or new evidence**" |
| 8 | precision "not a lever in either direction" | "within the permitted envelope and current frontier, precision is not an *evidenced* lever; a new proposal must first show a compliant byte or math advantage" |
| 9 | attention precision "a **dead lever** … do not treat as headroom in either direction" (`3fbbd2d3`) | "a **low-priority direction** … **revisit** only when a mechanism stays inside the accepted envelope and shows a **net byte or math advantage**" |

`3fbbd2d3` ("Soften Maple attention precision guidance", 2026-08-06 22:04:20
UTC) is a second operator commit in the same direction, also touching
`senpai/program.md` only. The arithmetic is unchanged and still fatal to the
naive move: Q/K/V/O already run **NVFP4 group-16 at 0.5625 B/param** where the
envelope permits **group-32 affine INT8 at 1.125 B/param**, so *adopting* the
envelope adds ~802 MB/token — ~28% of the decode axis. What changed is the
verdict on the *family*: it is now open to a proposal that finds a **net** byte
or math advantage inside the envelope, rather than forbidden outright. The
unchanged prohibition: **do not propose taking any other class below its
current representation.**


**What this changes operationally.**

1. **The +0.61% advisor acceptance bar is retired as a universal gate.** Three
   leads were killed by it alone and are legitimate to revive on their own
   merits: the prefill `PREFILL_ASYNC_LADDER` stride sweep (**+0.34%**, one
   literal, bit-exact, byte-neutral, §9), the shared-expert SwiGLU epilogue
   (**+0.040%**, plus a **+0.028%** zero-byte sub-lead, §7), and the lm-head
   cascade fusion remainder (**+0.060%**). None of these is large; each is
   cheap, and the field has moved less than that per round.
2. **Receipt families are sized to the decision, not to a constant.** A
   designed effect that is large and unmissable needs one or two receipts. An
   effect within ±0.243% on `ns` still needs repetition, because that is what
   the noise says — but that is now a *statement about the effect*, not a
   standing tax on every submission.
3. **`officialScore` for ranking, `ns` for attribution.** Both statements are
   true simultaneously. Quote `officialScore` when the question is "did we
   move on the board"; quote `ns` when the question is "did mechanism X pay".
4. **An M4-only student may be assigned a prefill kernel change** whose
   deliverable is implementation, correctness, bit-exactness, reachability and
   *wave analysis* — with the ranking verdict deferred to an M5 receipt. This
   supersedes the stricter phrasing this document carried at §3a item 4.
5. **Closure is provisional.** §8 remains the record of what has been
   falsified, but a genuinely new mechanism or new evidence reopens any row in
   it. Repeating a closed arm unchanged still does not.

Also recorded by the same commit, and consistent with our own findings: on the
M5 the 512-token forward runs at ~28.8 TFLOP/s and ~272 GB/s — roughly **half
of each M5 roofline** — and the public field has been stuck on that axis for
**102 consecutive submissions**.

---

## 0c. M5 / NAX hardware facts and published ceilings

Source: plateau-escalation research batch
`maple-r25-plateau-escalation-2026-08-06`, tasks `ab3a87f3` (hardware,
general web) and `1986eb13` (research publications), 2026-08-06. **Read this
before writing any kernel-level assignment.** Facts are tagged
**[documented]** (Apple or MLX source), **[reverse-engineered]**
(philipturner/metal-benchmarks and equivalents), or **[measured]** (a named
third-party benchmark). Do not promote a reverse-engineered figure to a
prediction without a matching in-tree measurement.

### 0c.1 M5 Max machine constants

| quantity | value | status |
|---|---|---|
| DRAM bandwidth, M5 Max 40-core | **614 GB/s** | [documented] LPDDR5X-8533 |
| DRAM bandwidth, M5 Max 32-core | 460 GB/s | [documented] |
| DRAM bandwidth, M5 Pro / M5 | 307 / 153 GB/s | [documented] |
| unified memory | 128 GB | [documented] |
| peak GPU compute vs M4 | ">4×" (Apple's claim) | [documented] |
| max threads/threadgroup | 1024 | [documented] apple7+ |
| max threadgroup memory (API) | 32 KB | [documented] |
| SIMD width | 32 | [documented] |
| bf16 | a documented Metal 4 tensor type | [documented] |
| **SLC size** | **unknown** | rumour only — see below |
| GPU clock, registers/thread, resident simdgroups/core | **not published** | — |

⚠️ **No Apple document gives the M5 Max SLC size, GPU clock, register count
per thread, or resident simdgroups per core.** Every figure circulating for
M5 Max SLC is rumour-grade. Our working assumption remains "≥48 MB, unknown"
(§ Apple SLC facts). Do not build a staging argument on an assumed SLC size.

**Per-core structure [reverse-engineered], Apple7/8 baseline:**
- 1 core = 4 partitions × 32 lanes = **128 FP32 FMA/clk**; each partition
  issues 1 instruction/clk from 1 simdgroup ⇒ **4 instructions/clk/core**.
- Register file ≈ **208 KB/core**. Physical threadgroup memory ≈ 60 KB/core
  versus the 32 KB API limit.
- I-cache 12 KB; L1 data 8 KB; **global cache line 128 B**; on-core data
  bandwidth **64 B/clk/core**.
- Occupancy ladder: 1024 threads/core = **32 simdgroups** at ≤104 half-
  registers, falling to 832 / 640 / 512 / **384 (12 simdgroups)** at
  128 / 160 / 208 / 256 half-registers.
- **ALU utilisation saturates at ~24 simdgroups/core**; below that the core is
  issue/latency-limited, not throughput-limited.
- ALU latency 3–6 cycles. FP32 dependent-FMA chains take 6.6 cycles at minimum
  occupancy versus 3.9 for FP16. M3+ **dual-issues FP32 with FP16/INT**.
- **Address arithmetic is real work.** 64-bit integer add (`IADD64`) is
  emulated in **4 operations**. Dynamic (non-constant) `BITEXTRACT` /
  `BITINSERT` degrade to **8–12 cycles** versus ~1 for the constant form.
  ⇒ NVFP4 unpack and gather pointer math compete for the same issue slots as
  the FMAs. **This is the main support for §4.10's third-resource
  hypothesis.**

✅ **RESOLVED (PR #196, M4 Pro / 20 cores) — 32 vs 96 simdgroups/core: both
are correct and measure different things.**

- **96 simdgroups/core is the *residency* ceiling.** Proved by a cooperative
  rendezvous kernel that cannot complete unless all launched threadgroups make
  simultaneous forward progress (run `935bcdcb`). It holds at 1024 / 512 / 256 /
  128 threads per threadgroup (3 / 6 / 12 / 24 TG per core = 96 simdgroups every
  time) and is flat in threadgroup memory from 16 B to 32768 B. That invariance
  is what a hardware slot limit looks like, and it reconciles #57, #138 and
  #157 — the last of which reported the same 96 as 24 TG/core × 4 simdgroups
  for a 128-thread threadgroup.
- **32 simdgroups/core is the *throughput* width** — one 1024-thread
  threadgroup per core per wave. This is what the duration staircase measures
  and it is the number that governs performance. Both scored attention kernels
  show a flat duration from K=1 to K=C and a **+6.5 µs riser at exactly
  K = C+1 and K = 2C+1** (run `dc05d40d`, unit resolution, K = 1…3C).

**For all performance modelling use 32.** Fitting `T(K) = a + b·⌈K/C⌉` to the
wave plateaus gives a marginal wave cost `b = 7.408 µs` against a lone-threadgroup
latency of 8.891 µs, i.e. **co-residency recovers only ~17% of a wave**: these
kernels are issue/ALU-bound, not latency-bound, so the extra residency has
almost nothing to hide. This is consistent with the "ALU saturates at ~24
simdgroups/core" line above — with 3 co-resident 32-simdgroup threadgroups the
core is far past saturation, which is *why* the extra residency buys so little.

Caveat: measured on M4 Pro (gen 16). The 96-slot ceiling is not verified on the
ranked M5. See `research/nezuko-decode-attention-occupancy.md` §3 and §6.

### 0c.2 The Neural Accelerator (NAX)

- **One NAX per shader core**, alongside the ALU pipelines. Reachable only
  through Metal 4 `MTLTensor` + `mpp::tensor_ops` (MPP), gated on
  **`MTLGPUFamily.apple10` and later**. [documented]
- **Apple's own tile recommendation** (MPP Programming Guide §2.3.2): on M5,
  a simdgroup tile of **SM = SN = 32** is a good starting point for 16-bit
  operands; smaller data types may need *larger* tiles; too-large tiles
  regress. [documented]
- Apple and the MLX team both state **threadgroup staging is not required for
  peak GEMM** — device-memory streaming through the cache is fastest.
  [documented]
- **[measured, A19, 5 cores ~1.46 GHz]** FP16 matmul **7.5 TFLOP/s**
  (~1024 FLOP/core/clk); **FP32 accumulate is free**; INT8→INT32
  **13.4 TOPS** (~2× FP16). SIMD-path FP32 1.88 / FP16 3.2 TFLOP/s ⇒ the
  matrix path is ≈**4× the FP16 SIMD path**.
- Extrapolated 40-core M5 Max at ~1.75 GHz: **~70 TFLOP/s FP16, ~130 TOPS
  INT8, ~18 TFLOP/s FP32 SIMD**.
- **[measured] MLX PR #3211: 52–60 TFLOP/s fp16 on a real M5 Max** — 75–85%
  of the extrapolation. **Use 52–60 TFLOP/s, not 70, as the practical dense
  ceiling.**
- **Optimal tile ≈32×32; larger regresses. Transposes are free.**
- **~256 cycles to produce a 32×32×32 product** ⇒ NAX latency is long; deep
  pipelining with multiple independent accumulators is required to cover it.
  ⚠️ Consequence: **adding a second accumulator can make a latency-bound NAX
  kernel *faster*, not slower.** An arm that adds MMA work and comes back flat
  or faster is evidence of latency-boundness, not of spare MMA throughput.
- Keeping one core's NAX fed needs ~64 B/clk ≈ **93 GB/s per core** ⇒ NAX
  kernels are **cache/reuse-bound by construction**.
- **Cooperative tensor fragments live in per-thread registers** ⇒ they share
  the 208 KB register file with vector ALU state, so extra accumulators carry
  a second-order occupancy cost. Issue-slot sharing between NAX and the vector
  ALU is **undocumented**.
- Apple tech talk 111432: NAX utilisation is a **separate counter**, and the
  practical limiter in Apple's own worked example was **data supply** —
  utilisation went 50% → 100% purely by changing threadgroup traversal order.

### 0c.3 MLX `_nax` gating and geometry (read from our own checkout)

- `is_nax_available()`, `Vendor/mlx-swift/.../metal/device.cpp:913`:
  `MLX_METAL_NO_NAX` off, **runtime macOS ≥ 26.2**, `architecture_gen >= 17`
  (**18** if the arch string ends in `'p'`).
- Per-op gates: `env::enable_tf32() || dtype != float32`. Quantized
  additionally needs **`transpose && K % 64 == 0`**
  (`quantized.cpp:733, 972, 2005`). SDPA excludes `head_dim == 80`
  (`scaled_dot_product_attention.cpp:177`). Device-class routing switches on
  `architecture().back()` (`'s'`/`'c'`/`'d'`).
- **Hardware fragment shape:** `steel/gemm/nax.h:503` builds
  `mpp::tensor_ops::matmul2d_descriptor(16, 32, 16, …)` at
  `execution_simdgroup` scope ⇒ **M16 × N32 × K16 per simdgroup**, two
  N-halves per call.
- Fused NAX GEMM defaults (`matmul.cpp:227`): `bm128 bn128 bk512 wm4 wn4`;
  for `'s'/'c'/'d'` devices `bm64 wm2`, with `bk=64` when
  `K ≥ 8192 && K > M+N` else 256. Split-K NAX fires when `K ≥ 3·max(M,N)` or
  (`max(M,N) ≤ 1024 && K > 2·max(M,N)`).
- ⚠️ **`gather_mm_rhs_nax` (`matmul.cpp:2091`) disagrees with our shipped
  geometry at our shape.** It fixes `bn128 bk128 wn4` and picks `bm/wm` by
  `M/E`: 64/2 when `M/E > 48`, 32/1 when `> 24`, else **16/1**. Our prefill is
  M = 4096 rows/layer over E = 256 experts ⇒ **M/E = 16 ⇒ upstream MLX would
  choose `bm16/wm1`**. We ship `bm64/wm4` (arm 5 of the
  `DARKBLOOM_STAGE_BM128` sweep) and measured it better. This is not a bug,
  but it is a second independent signal that **our kernel's binding constraint
  is not the one MLX's heuristic models** — the first being §4.10.
- ⚠️ Our shipped `BM=64, WM=4, WN=1` gives **SM=16, SN=64**. Apple's
  recommended starting point (SM=SN=32) is exactly our sweep **arm 0**
  (`BM64 WM2 WN2`), which measured **2.13% slower** than what we ship.
  Empirical optimum disagrees with the vendor recommendation. Weak evidence
  **against** MMA-throughput-boundness: an MMA-limited kernel should prefer
  the vendor-optimal fragment packing.

### 0c.4 Known MLX limitations in exactly our regime

- **MLX discussion #3691:** the MoE weight-reuse GEMM **tops out around
  80 GB/s at small M on an M5 Pro**, and the NAX path is *on* that curve, not
  above it. Explicitly names the (16,32,16) descriptor at M = 16–64 — our
  primitive, our regime. (We measure 408.4 GB/s on M5 Max, so we are not on
  the pathological curve, but the family is known-fragile at small M/E and
  upstream has not solved it.)
- **MLX issue #3584:** `quantized_matmul` runs **1.5–1.8× slower than fp16**
  at M = 96/128 because a split-K path fires when the single-kernel
  `qmm_t_nax` would win. ⇒ **Any stray split-K instantiation in a scored run
  is a red flag.** A scored run must generate exactly two NVFP4 gather-rhs
  pipelines (`..._k_2048_n_1024_eg_256_ws_1_wl_{1|0}` and
  `..._k_512_n_2048_eg_256_ws_1_wl_{1|0}`).
- Crashes from missing instantiations: issue #3362, PR #3632.
- Large-K NAX slow tail: issue #3017 (split-K up to 1.6×); segmented NAX
  matmul PR #3419 (1.1–2.75×).
- Third-party datum: bypassing NAX regressed 828 → 400 tok/s (jundot/omlx)
  ⇒ **NAX helps prefill more than decode**, consistent with our own split.

### 0c.5 Bandwidth-versus-peak calibration

- GPU STREAM on M1–M4 reaches **~85% of theoretical peak** (arXiv 2502.05317).
- llama.cpp Q4 decode on a 40-core M4 Max: 296/546 GB/s = **~54%**.
- Apple's MLX post: the M5-vs-M4 *decode* gain of 19–27% tracks the 28%
  bandwidth gain — **decode is bandwidth-bound, prefill is compute-bound.**
- Practical reading for us: 85% is the ceiling a perfect streaming kernel
  reaches; 54% is what a real quantized decode loop reaches. Our decode
  aggregate at ~71% of the 614 GB/s floor is therefore **between** those two,
  which is why §7's 1.20 ms pool is plausible but not free.

⚠️ **Do not cite arXiv 2607.19438 ("BaseRT" page).** It asserts M5 reports
`apple9`, contradicting Apple's documented `apple10`. Treat the whole page as
unreliable. (The *separate* BaseRT paper 2607.00501 is fine — see §0c.7.)

### 0c.6 Exact-compression ceilings — the headline negative

**No published technique reduces bytes-read below "all top-k expert weights"
at batch 1 while preserving exact numerics.** This is the strongest negative
result from the literature pass and it closes a family we kept half-open.

- **Lossless entropy coding of already-4-bit tensors has a measured ceiling of
  ~1.04×** (Q4_K 1.041–1.045×; ~1.01× over a whole GGUF). The bf16 ceiling is
  ≈**1.495×**. ⇒ **Entropy-coding the NVFP4 payload nibbles is not worth
  doing.** Formally closed.
- ✅ **The one exact opportunity nobody measured: the scale plane.** Every
  cited study coded the *payload*. The NVFP4 scale plane is 1 byte per 16
  values ≈ **12.5% of payload bytes**, and E4M3/E8M0 scale distributions are
  low-entropy. **Nobody has measured its entropy.** This is a cheap offline
  histogram — see §7 idea 8's method, applied to scales rather than bf16.
- **TritonMoE** (2605.23911): fused gate+up reaches 43% of peak bandwidth, but
  its own limitations section states that **for 256-expert / top-8 models the
  bottleneck is loading expert weights, not dispatch efficiency**. The reuse
  argument dies at batch 1. Matches our 552.1 MB finding exactly.
- Layout precedents that are free and exact: **M2XFP** (2601.19213) stores
  three separate contiguous fixed-length streams (4-bit elements / 8-bit
  shared scale / 8-bit metadata) for alignment and independent parallel
  access; **MOSS** (2511.05811) stores scales contiguously aligned to the MMA
  inner-loop access pattern; **MicroMix** (2508.02343) uses offline channel
  permutation. ⚠️ We refuted H-a (alignment) and H-d (two disjoint streams)
  in-tree — cite these only as design vocabulary, not as revival evidence.
- **Fixed-length beats variable-length on SIMD:** **ZipServ** (2603.17435)
  uses a TCA-TBE fixed-length bitmap giving **branch-divergence-free
  constant-time decode** straight into registers feeding the MMA. **dtANS**
  (2603.01915) is engineered so decode is not the bottleneck in a
  memory-bound GEMV. Shannon-bound tile-level ANS (2606.15789) aligns to GEMM
  tiling. **DFloat11** (2504.11651) achieves 30% bit-identical but is
  bf16-only. ⇒ if we ever code the scale plane, **fixed-length, not ANS**.
- **FASQ** (2605.04084), batch-1 GEMV: eliminating the shared-memory LUT gave
  **zero SMEM, zero barriers ⇒ 12 resident blocks/SM versus 1**; split-K
  across grid-z tuned to ~8 blocks/SM. The codebook part is lossy and
  therefore out of bounds, but **the occupancy structure transfers**.
- ⚠️ **Split-K warning** (2402.00025): W4A16 at M = 1–16 gave 1.24× on H100,
  1.14× on A100-40, and **0.64× — a regression — on A100-80**. The optimal
  split factor **flips sign across GPUs**. Any split-K proposal needs its own
  M5 measurement; M4 evidence is worthless for it.

### 0c.7 Fusion and dispatch-count literature — supports §7 ideas 1–4

- ⭐ **Fusion gains are non-additive. Do not screen components individually.**
  **ClusterFusion++** (2604.23553) on Pythia-2.8B: TPOT 6.80 → 5.32 ms
  (attention-only fusion) → **4.90 ms fully fused (1.39×)**. The MLP-down
  fusion measured **0.75× — slower — in isolation**, yet contributed
  positively inside the full fusion. **This is a direct warning against our
  own habit of pricing each fusion separately** (§4.1a's price table), and it
  is the main literature support for §7 idea 1.
- **ClusterFusion** (2508.18850) fuses QKV-projection + attention +
  O-projection into one kernel, exactly. This is the published form of §7
  idea 3's endpoint.
- **Open-TQ-Metal** (2604.16957): a fused Metal SDPA with dequant in
  registers, online softmax and zero intermediates ran **48× faster than
  dequantize-then-attend at 128K context**; separately,
  **`mx::set_wired_limit()` recovered 10× throughput (0.6 → 6.0 tok/s)**.
  ⚠️ Check whether our harness already sets a wired limit before treating
  this as a lead — at 21.6 GB resident on a 128 GB box it is probably moot,
  but it is a one-line check.
- **BaseRT** (2607.00501, the real one): separate GEMV(M=1) and GEMM kernels
  per format, dequant fused in the inner loop, **zero allocation in the decode
  loop**, per-chip threadgroup config selected from core count.
- ⭐ **Radix-8 FFT on Apple GPUs** (2603.27569): **the 208 KiB register file is
  the primary resident tier; the 32 KiB threadgroup memory is an exchange
  buffer only. Barriers cost ~2 cycles, while scattered threadgroup access is
  expensive. `simdgroup_matrix` did not help.** ⇒ supports tanjiro's B2 arm
  being a *weak* perturbation and S2 being a strong one.
- **Rigel** (2606.12765) on M4 Max: `matmul2d` runs on the shader cores with
  no dedicated matrix datapath; fp8 is emulated at 0.94× fp16;
  **hand-fused GEMM+bias+GELU gained +12.9% while bare-GEMM rewrites did not
  help — epilogue fusion is the lever.** Consistent with our own §7 R2
  shared-expert SwiGLU epilogue lead.
- **SAR fusion** (2604.03585): 22× from single-dispatch fusion on M1; the MMA
  FFT reached only 93% of scalar.
- **Multi-node MoE on Apple Silicon** (10.1145/3649601.3698722):
  **pre-stacking expert weights as one 4D tensor keeps execution time stable**
  versus separate 2D matrices. We already do this; recorded as confirmation.
- **vllm-mlx** (2601.19139): M4 Max worked example, 56 ms theoretical versus
  ~67 ms observed = **~11 ms of CPU-side overhead**. Independent corroboration
  that host-side cost is real on Apple Silicon at this scale.
- Metal-Sci (2605.09708) puts SLC at ≈24 MB on M1 Pro — consistent with our
  M4 Pro figure, still no M5 Max number.

### 0c.8 Dispatch-count evidence — the quantitative case for §7 idea 2

- ⭐ **TaxBreak** (2603.12465): **OLMoE runs at 260.5 ms/token at BS=1, 11.7×
  slower than dense Llama-3 at equal activated parameters. 93,053 kernels per
  inference versus 8,475. GPU utilisation 15.5% versus 58.9%. Persistently
  host-bound through BS=16.** This is the single strongest published
  statement that **sparse MoE decode at batch 1 is a dispatch-count problem,
  not a bandwidth problem** — exactly §7 claim 1.
- **Fleet** (2604.15379): a persistent megakernel gives **1.3–1.5× lower
  decode latency at bs=1–16 on MI350X**, and explains why graph capture is
  strictly weaker than a persistent kernel — L2 is flushed at kernel
  boundaries, forcing intermediates through HBM.
- **Event Tensor** (2604.13327) handles data-dependent megakernel dynamism —
  i.e. the MoE routing case, which is the hard part for us.
- **Batch-1 instrument** (2605.30571): CUDA-Graph A/B isolates launch
  overhead — 1.259× on H100 versus 1.028× on L4. Also: int4 realization
  varies **45.24 ms (Marlin) versus 17.36 ms (ExLlamaV2)** — implementation,
  not bit width.
- **Ada-MK** (2605.11581): launch overhead is 14.6% of end-to-end and +23.6%
  single-batch.
- **RaMP** (2604.26039): a 4-term cost model cuts geometry-selection regret
  from 8.1% to 0.93%. Relevant if we ever re-open geometry selection.

### 0c.9 Roofline methodology we should be using

- Williams 2009 in-core ceilings; Williams 2010 **Little's Law: required
  in-flight bytes = latency × peak bandwidth**. We have never computed our
  in-flight byte requirement. For decode at 614 GB/s and ~1 µs of dispatch
  latency that is ~614 KB in flight — a number worth checking against our
  actual outstanding-load depth.
- **Instruction Roofline** (10.1002/cpe.6591; 2110.08221): count *instructions*
  to expose fetch–decode–issue limits. **This is the missing axis in §4.10.**
- **Time-based roofline** (2009.04598): runtime = launch latency × kernel
  count. Kernels **<5 µs are launch-dominated** — several of our decode
  kernels are in that range.
- **SAAKE** (10.1145/3192366.3192397): perturb one resource by ±10% and
  re-emulate; the highest-sensitivity resource is the binding one. **This is
  precisely tanjiro's #170 design**, arrived at independently. Good sign.


## 2. The score model (memorise this; do not re-derive it)

From the promoted receipt's **candidate** arm:

| quantity | value |
| --- | --- |
| prefill wall `S` | **97.89475 ms** |
| decode per-step `T` | **4.143569335937499 ms** |
| `sigma` (prefill share of log-score) | 0.15582 |
| normalized score `ns` | 2.5982163 |

Paired baseline arm: prefill 382.682697265625 µs, decode 13.84496646875 ms
(these are the harness's per-token units; `S` and `T` above are the wall
figures).

**Elasticities:**

| lever | elasticity | practical rate |
| --- | --- | --- |
| prefill `S` | **−0.3669** | **−1 ms of S = +0.362%** |
| decode `T` | **+0.6331** | **−1 µs of T = +0.01464%** |

Ratio 1.726 — decode is worth more *per proportional unit*, prefill is 23.6×
larger *in absolute time*.

Worked prefill points: −3.13 ms = **+1.20%**; −7.82 ms = **+3.10%**;
−15 ms = **+6.4%**.

> An earlier advisor note put the 3.13 ms figure at "+2.08%". **That was
> wrong.** Use the table above.
>
> ⚠️ **A previous version of this line quoted "−31.28 ms = +15.17%". That
> number is withdrawn — see §9a.** 31.28 ms was never measured; it is a
> subtraction residual against a derived roofline floor, and
> `research/maple-tanjiro-pr91-prefill-budget-census.md:845` already adjudicates
> that exact value as **mis-sourced / CLOSED**. The elasticity arithmetic is
> fine; the 31.28 ms input was not.

### The single most important strategic fact

**The entire remaining decode byte inventory, removed at a physically
impossible 100%, is worth +2.85%** — 4.50% of `T`. Decode byte-shaving as a
*family* is near exhaustion. That is why round 22 is a **prefill pivot**.

> ⚠️ **Scope this correctly.** +2.85% is a **byte-removal ceiling at the
> current schedule and layout**. It is *not* a time floor on `T`, and it must
> stop being quoted as a reason decode gets no work — decode still carries
> **75% of the score weight**. Three of our own numbers say schedule and layout
> have more authority over `T` than the byte inventory does: forcing decode
> serialization costs **+5.49%**; the marginal byte price spans **463.5 → 968.4
> GB/s across planes on the same DRAM** (so "% of achievable bandwidth" is
> partly circular, since layout sets the denominator); and a barrier-serialized
> dispatch is priced at **1.980 ± 0.044 µs** on the M5. **`Σ(marginal per-family
> cost)` versus `T` has never been measured on the M5.** #148's decode axis is
> now co-primary precisely to read it (§9.7).

### The byte-price law (replaces two retired constants)

**RETIRED — do not use, do not quote, delete on sight:** `0.0272 %/MB` and
`14.862 %/ms`. Both appeared throughout the archive (old §0.9.36, §R20.2) and
both are wrong because they assume a single global bandwidth.

**In force:**

```
Δscore% = 15.2800 × MB_removed / R_marg[GB/s]
```

Unpriced plane ⇒ use the interval **[463, 969] GB/s** and report both ends.

Measured `R_marg`:

| plane | R_marg (GB/s) | n |
| --- | --- | --- |
| lm-head base | **968.4** (σ 0.269) | 6 |
| routed MoE g32 | 700.3 | 1 |
| attention scale | 524.1 | 1 |
| attention pairwise | 463.5 | 1 |

Corrections adopted: `gate_sp` unique DRAM is **5.5296 MB/step** (nezuko #110),
superseding PR #73's 7.86. PR #72's **+0.834%** anchor is **retired as
circular**.

Only two decode kernels remain unsaturated: `residual_rms_router` at **61.8%**
of achievable bandwidth, and `gate_sp` at 30.4 GB/s = **11.7%** (latency-bound,
not bandwidth-bound). Everything else sits at 94.6–100.2%.

---

## 3. Measurement doctrine (binding on every assignment)

> **⚠ Read the round-28 constraints at the top of this file first.** Rules 1–5 there
> (content-hash submit dedupe, no ranked arm from an unpushed tree, the cost of a
> deliberately-degraded arm, `device.cpp` non-editability, and the 49,145 B headroom)
> amend this section and take precedence where they conflict. In particular the
> **matched-control rule below is re-specified**: a byte-exact control arm is silently
> deduped to a stale cross-session receipt, so a control must carry an inert,
> behaviour-neutral perturbation that changes the submitted surface hash.

1. **Local M4 `--local-iterate` MDE is ±0.73%.** Established empirically by
   tanjiro in PR #103 §11.2 using byte-identical Sources. No win *or* loss may
   be claimed inside that band.
2. **`officialScore` for ranking, `ns` for attribution** (revised by `eae07f01`,
   §0a row 5). `officialScore` *is* the authoritative leaderboard number; what
   it and the raw `*_speedup` fields are bad at is attributing a small
   mechanism across sessions. Use `ns` for that.
   Pooled cv: `ns` **0.149%**, `officialScore` **0.553%**. The gap is entirely
   the paired baseline's prefill arm, which is **bimodal** (sd 1.933%,
   p50 368.5 µs / p90 382.9 µs). The **candidate** arm's prefill redraw sd is
   only **0.260%**, i.e. **0.065% of `ns`** — so `ns` is a *precise prefill
   instrument*: a genuine +1.2% prefill arm lands at roughly **8σ**.
3. **Receipt channel.** Round budget ≤10 receipts total. **Size the family to
   the decision, not to a constant** (`eae07f01`, §0a row 4): one receipt can
   justify a clear win or a follow-up; an effect inside ±0.243% on `ns` needs
   repetition because that is what the noise says. 0.243% is noise context —
   **not** a submission or promotion threshold, and the old "advisor acceptance
   bar = 0.61%" is deleted. The old "~35 min per receipt,
   single queue-owner" model is **RETIRED** — see §10 for the rule now in force.
   The per-receipt price is currently **un-remeasured**; every dispatch must
   record dispatch time, first "capacity occupied" response, admission time and
   receipt time so we can rebuild it.
4. **M4 vs M5.** Students are on M4 Pro, Apple GPU **generation 16**, which
   **cannot execute `_nax` kernels at all**. The official M5 selects `_nax`.
   Any `_nax` arm is therefore M4-blind and needs the safety rig in §5.
   Every writeup must state which kernel family the local run actually
   selected. **Exception:** hand-written decode MSL is executed identically by
   both hosts, so M4 timing *is* admissible there. See §3a for the strengthened
   form of both halves of this rule.
5. **The greedy-token gate is structurally blind to sub-token logit drift.**
   Measured, not assumed: fern's 1-ULP fault-injection control in #137 made
   **64 of 65** per-step logit digests differ and still reported
   `token_mismatches: 0`. A passing token gate is therefore **not** evidence of
   bit-exactness. Any arm claiming bit-exactness must carry a **bitwise logit
   digest** (`top_k = 100352`, all 64 steps) **and** a deliberately perturbed
   control that is *shown to fire* on that digest. A digest test with no firing
   control is vacuous. This raises the evidentiary bar for every future
   precision-relaxation arm, H1 included.

### 3a. ⚠️ CORRECTION (round 24): our M4 prefill census measures kernels the M5 never runs

This is the most consequential correction of the campaign so far. It invalidates
a claim we have been restating for several rounds, and it simultaneously
*strengthens* the decode half of our transfer doctrine.

**The evidence.** `research/maple-fern-prefill-roofline.md:15-40` records the
capability probe taken on the student host:

```text
arch=applegpu_g16s  gen=16  last=s  nax_gen_required=17  nax_available=false
```

The OS gate passes; the **GPU generation gate fails**. Every `_nax` kernel is
unreachable on an M4 Pro. Fern's own words: this is "a strictly stronger failure
mode than the advisor's 'threadgroup re-tiling does not transfer': it is not the
same kernel at a different occupancy, it is a *different kernel*."

**The inverted claim.** We have repeatedly written "94.2% of prefill is `_nax`".
The truth is the exact opposite: **94.2% of the M4 prefill census is *not*
`_nax`, and every one of those kernels is NAX-divergent** — the M5 runs a
different Metal function for it.

| observed pipeline on M4 | ms/fwd | share | what the M5 runs instead |
|---|---:|---:|---|
| `nvfp4_gather_qmm_rhs_nt` (bm16/bn32/bk32/wm1/wn2) | 266.65 | 48.5% | `nvfp4_gather_qmm_rhs_expert_static_nax_nt_…bm_64_bn_64_bk_64_wm_4_wn_1` |
| `steel_gemm_fused_nt_bfloat16_bm64_bn64_bk16_wm2_wn2` | 183.37 | 33.4% | `steel_gemm_fused_nax_nt_…` (bm128/bn128/bk512 family) |
| `steel_gemm_splitk_nt` + `_accum` | 33.04 | 6.0% | NAX split-K branch (`matmul.cpp:988`) |
| `steel_attention_bfloat16_bq32_bk16_bd128_wm4_wn1` | 28.23 | 5.1% | `steel_attention_nax` at bq64/bk32 |
| `nvfp4_qmm_t` | 6.64 | 1.2% | `nvfp4_qmm_t_nax_static_…` |
| **NAX-divergent subtotal** | **517.92** | **94.2%** | |
| `nvfp4_qmm_t_splitk_fused` | 13.56 | 2.5% | same kernel (split-K precedes the NAX gate) |
| `laguna_*` custom + elementwise + rms + router + moe_tail + sort/scatter + lm_head | ~18.09 | 3.3% | same kernels |

Note in particular that the routed gather GEMM on M4 runs at
**bm16/bn32/bk32/wm1/wn2** — a 16-row tile — while the M5 runs a **64-row**
tile. Any tiling, occupancy or row-padding arithmetic derived from the M4
census is arithmetic about the wrong kernel.

**Four programme consequences.**

1. Correct the drifted restatements wherever they are cited:
   `RESEARCH_IDEAS_2026-08-06_09:00.md:189`,
   `PREFILL_LEDGER_INSTRUMENT.md:10`, `RESEARCH_STATE_ARCHIVE:5823`.
2. **Absolute M4 prefill per-kernel times, and every tiling/occupancy
   conclusion drawn from them, do not transfer to M5.** Only the ~3.3% tail of
   hand-written `laguna_*`/elementwise/rms/router/sort work is common to both
   hosts. This does *not* invalidate M4 *wall-clock* prefill A/B when the arm
   changes host-side dispatch structure rather than kernel internals — but it
   does mean an M4 kernel-internals result is not evidence.
3. **The steady decode step is 100% host-independent.** Every decode dispatch is
   a hand-written `laguna_*` kernel (or `rms`/`gather_front`); none sits behind
   a NAX or `#available` gate. The only capability gate anywhere in `Sources/`
   is `lagunaExpertAlignedGatherEnabled`
   (`LagunaRuntimeModel.swift:235-249`), which decode never reaches. Our
   existing "hand-written decode MSL transfers M4→M5" exception is therefore
   not an exception at all — it is the general rule for decode.
4. **Assignment policy** (softened by `eae07f01`, §0a rows 1–2). An M4-only
   student **may** be assigned a prefill kernel change. What the student host
   delivers is implementation, correctness, bit-exactness, kernel-reachability
   and **wave analysis**; what it cannot deliver is a ranking verdict for the
   M5 `_nax` surface. Every such writeup must state which kernel family the
   local run actually selected, and must defer the ranking claim to one of
   (a) an M5 receipt, or (b) an argument with a ≥100× margin that survives the
   kernel substitution. Decode still carries 75% of the score weight and is
   host-independent, so it remains the cheaper place to *close* a question —
   but that is an expected-value statement, not a prohibition.

### Resubmission variance-harvesting: formally REFUTED

Tested directly this session. Our 2.588828 sits at the **85.7th percentile of
its own null** (+0.632% above the expected 2.5726). Therefore:

- E[one resubmission] = **−0.63%**
- P(beat) = **12.7% per ticket**; ~8 tickets needed for even odds
- the service **dedupes byte-identical archives**
  (`senpai/experiment-runbook.md:195-198`), so every ticket needs a
  byte-distinct tree
- there is **no rate limit** anywhere, and the leaderboard keeps the **best**
  (`TASK.md:44`)

It is a losing lottery against a channel we need for real arms.
**Decision: we do not do it.** Do not re-propose.

---

## 4. The mechanism that now organises our thinking

MLX opens encoders `MTL::DispatchTypeConcurrent` (`device.cpp:548`) and inserts
barriers **only on a real RAW/WAR hazard** (`device.cpp:318-375`). Forcing
serialization costs **+5.49%** [+4.70, +6.28], p = 0.029.

Consequences:

- **A hazard-free kernel is shadowed.** Its cost can be entirely hidden behind
  a concurrent neighbour. This is why the `gate_sp` occupancy arm (#101)
  measured null despite a correct local mechanism.
- **A RAW-dependent cascade cannot be shadowed.** MLX *must* barrier, so the
  stages are genuinely serial, so **fusing them pays**.

So #101, which reads as a null result, is actually **the theory that predicts
fern's lm-head cascade fusion (#137) works.** Negative results that identify a
selection rule are worth more than marginal positives.

**Corollary now owed to the programme:** every banked "µs/step saved" claim
measured *in isolation* rather than *in situ* is suspect for shadow-execution
over-attribution. Re-audit as they come up.

### 4.1 ✅ RESOLVED (round 23, #157 + #158): the residency-ceiling law

The shadow-model contradiction is closed. Two independent PRs agree, so per the
rule below no single receipt was needed and none was spent.

> **THE RESIDENCY-CEILING LAW (#157 D2).** Two independent kernels overlap when
> their **combined** threadgroup count is at or below the machine's concurrent-TG
> residency ceiling (**~480 on a 20-core M4 Pro = 24 TG/core; ~960 on a 40-core
> M5 Max**), and essentially not at all above it.

Measured `concurrent_1cb` GEMM ladder with duration held ≈20 ms: 16 TGs →
`overlap_eff` **1.0112**; 80 → 0.1192; 2048 → 0.0426; 9792 → 0.0128.
Complementary `alu/mem`: 2 TGs → 0.4954 … 9792 → 0.0259. So overlap is a
**spare-capacity** property, not a scheduler property.

Resolution of the three candidate readings:

- **(a) the instrument is blind — CONFIRMED.** `gpu_busy_union` is computed
  **per command buffer** (`research/decode_probe.py:147-192`, merge `:177-186`;
  prefill twin `research/prefill_probe.py:148-165`) from a CB completion
  handler. MLX packs 20–50 ops per CB on one queue, so `union == sum` is
  *guaranteed by construction* and carries zero information. Control:
  `concurrent_1cb` reports union-overlap 0.000000 while wall 13.954 ms against
  an isolated sum of 27.939 ms — **perfect hiding, invisible to the metric.**
  Worse, PR #73's run A used `DARKBLOOM_GPU_PROFILE_SPLIT` (`cbs=406
  dispatches=406`), which makes that evidence self-refuting.
- **(b) no shadowing at real width — SEPARATELY TRUE**, but for a different
  reason than we assumed. #157 D5 measured prefill-512 geometry: MoE per layer
  compacts to **9,798 TGs** (490× the M4 ceiling, 245× the M5 ceiling);
  attention is 384–512 TGs. Nothing in the scored graph runs under the ceiling.
  #158 confirms this independently at **decode** width: capping dispatches per
  CB leaves `gpu_busy_sum` flat at 7.99 ± 0.06 ms while CBs go 45 → 204, so
  hidden decode work is **≤ 0.06 ms/step (< 1%)**. ⚠️ **The decode half of this
  bullet is under direct challenge by PR #174** — it contradicts PR #101's
  +0.456 ms/step serialization cost by 7.6×. See §4.9. The *prefill* half (the
  245× residency margin) is untouched by that challenge.
- **(c) M4 ≠ M5 — not needed.** The 245× margin transfers safely.

**Programme consequences (binding):**

1. **`gpu_busy_union` is RETIRED programme-wide.** Every "nothing overlaps
   because sum == union" claim is withdrawn
   (`nezuko-decode-roofline.md:193-202`, `nezuko-terminal-report.md:221-225`,
   `maple-tanjiro-pr73-decode-kernel-census.md:721`). **`gpu_busy_sum` and the
   per-CB intervals remain valid.** Delete the union column from new reports.
2. **Attack B (graph-level overlap / co-residency) is CLOSED for prefill**, and
   *provisionally* closed for decode by #158's flat-`sum` control. Any future
   "hide X behind Y" proposal must **first** show that X or Y leaves the machine
   under-occupied (< ~480 combined TGs on M4 Pro, < ~960 on M5 Max). Prefill
   tail-fill upside is bounded at O(0.5%) ≈ 0.5 ms ≈ **+0.18%** — below bar.
   ⚠️ **The decode half of this closure is under challenge by PR #174** (§4.9).
   Until #174 reports, do not cite "decode has no exploitable intra-CB
   concurrency" as settled, and do not cite it *against* a decode proposal
   without also citing #101's +0.456 ms/step. The prefill closure stands
   unconditionally.
3. **The decode host gap is PROPORTIONAL, not absolute** (#158 §1.1: slope
   +0.0594 ± 0.0191 on injected work, 3.10σ nominal — treat as ~1.5–2σ, see the
   caveat below). Either way the whole dispute is bounded at **gap/wall =
   3.01%** and the two models differ by only 0.33% of wall. The qualitative
   conclusion is the one that matters: **there is no host-side pool to harvest;
   wall time must be bought by removing GPU work.** The hoped +4.7% host-gap
   pool does not exist.
4. **#158 §2 headline — RESOLVED in r2 and RETIRED (merged as `268fb087`).**
   "406 dispatches × 1.9 µs = 771 µs of dead time" is **withdrawn by its own
   author** and replaced by **no band at all**. r2 conceded every audit point:
   slope-not-level (§4.1.b), the two routes are not independent, the ~5σ
   internal inconsistency, the `rsdr` busy≫wall anomaly (which on re-measure
   inverted to wall **exceeding** busy: +171 µs = 4.40 µs/disp), and the
   percentage-denominator error. The "exactly 1.9 µs" corollary is struck.
   **Never price anything at 1.9 µs/dispatch again.**

   What replaces it, and what is now programme doctrine:

   > **Per-dispatch cost is real but SITE-SPECIFIC, not a floor.** Envelope
   > **≈1.5–8 µs/dispatch** across 6 arms / 3 sweeps / 2 currencies / 28 runs.
   > The best-conditioned traffic-free point estimate comes from §4.7's
   > `nonorm` arm (unfuses an RMS-norm out of the router GEMV: **+78 dispatches
   > for ~4 KB**): **3.59 ± 1.44 µs/dispatch** hook-off wall, 4.08 ± 2.18
   > hook-on, 4.13 ± 1.63 busy. CBs/step stayed fixed at 45 across every arm,
   > so this cost lives **inside GPU busy**, distinct from §4.5's 2.66 µs/CB
   > idle gap and §1.1's ~265 µs host gap. **The three must not be summed.**
   > **Refutation of any floor model:** `rrr` gives 7.43 µs and `rsdr` 1.83 µs
   > at *identical* +39 dispatches, same sweep, adjacent runs.

   > **PRICING RULE (supersedes every earlier version).** Price a prospective
   > fusion by its **traffic delta first**, then add a **3–4 µs/dispatch
   > bonus sized at that site** — a *prior*, not a coefficient. Always check
   > the **wall** marginal, not just busy.

   Two instrument results from the same round are worth more than the retired
   headline. **(a) A command buffer costs 1.59 ± 0.21 µs busy, 4.25 µs wall,
   2.66 µs of pure gap** — one event, three currencies (§4.5.c). ⚠️ PR #101
   independently derives ≈**0.42 µs/CB [0.24, 0.60]** by a non-circular route;
   these are 3.8× apart and **unreconciled** (see §4.9). **(b) The `SPLIT=1`
   census is stable**: replicated n=4, busy median 8572.8 µs at half-range
   0.12%, and **0 of 24 kernels** exceeded a 10% half-range (worst
   `gather_front`, 5.3%). That stability is what licenses §2.c's adjudications
   — and it is also why the §2.b *ranking* can only be wrong through
   **attribution**, not through noise (§4.9).

   Arithmetic footnote, now settled: `576/(406−45) = 1.596` per **CB** and
   `1.596 × (1 − 45/406) = 1.419` as the **census de-inflation constant** are
   both correct — they answer different questions, with an algebraic
   consistency proof at `nezuko-pr158-decode-dead-time.md:1069-1075`. The real
   r1 defect was that the constant was *missing*, not that it was wrong.

#### 4.1a The real, transferable finding from #158: the fusion price table

Read backwards, #158's unfuse sweep is a **retrospective measurement of four
already-shipped fusions worth ≈1.17 ms/step ≈ 14% of decode busy**. That prices
fusion directly, and far better than any flat floor:

| fusion (measured by reversing it) | dispatches removed | µs saved (busy) | **µs per dispatch removed** |
|---|---:|---:|---:|
| `DARKBLOOM_FUSED_RESIDUAL_RMS_ROUTER` | 39 | 259.5 | **6.65** |
| `DARKBLOOM_FUSED_ROUTED_SWIGLU_QMV` | 195 | 471.5 | **2.42** |
| `DARKBLOOM_FUSED_SHARED_SWIGLU_QMV` | 195 | 371.5 | **1.91** |
| `DARKBLOOM_FUSED_ROUTED_SHARED_DOWN_RESIDUAL` | 39 | 71.5 (wall only +20.5) | **1.83** (wall 0.53) |
| all four jointly | 429 | 673.0 | **1.57** |

Each arm n=1 (±0.36 µs/disp on the 39-dispatch arms, ±0.07 on the 195-dispatch
arms); all arms showed 0 token divergences.

> **RULE: price a prospective fusion by its traffic delta, not by a flat
> per-dispatch floor.** Fusions that eliminate a *materialised intermediate*
> have measured **1.6–6.7 µs per dispatch removed**; a fusion that only removes
> a launch is worth much less, and `rsdr` shows a busy saving of 71.5 µs
> converting to only 20.5 µs of **wall** — always check the wall marginal.

**All three "cheapest reads" were run in r2.** (1) `SPLIT=1` replicated n=4 —
**census is stable**, 0/24 kernels above a 10% half-range. (2) Hook-off unfuse
sweep, palindromic ×2, 12 runs, 0 divergences — hook cost is +0.11% of wall, so
the instrument is exonerated; but only **4 of 5 arms** were re-run (the
all-four-jointly Δ=429 arm, her best-conditioned point, is still missing in wall
currency — now Step 0 of #174). (3) The true traffic-neutral arm (`nonorm`) is
the report's **best result** and supplies the 3.59 µs/dispatch figure above.

---

#### 4.1b Two measurement laws from #158 that bind every future arm

**LAW 1 — the GPUPROF clock defect (§4.1.d).** `analyze_profile` correlated GPU
records against `time.perf_counter()` step spans. On macOS CPython **3.9.6**
(`/usr/bin/python3`, which `run_training` resolves) `perf_counter` has a
**process-relative epoch** — measured offset −137,996.9 s vs mach — so the
correlation window went **silently empty**. Every committed r2 profiled log
reads `0 inside 199 steady steps`. The failure mode is **fail-to-zero**, not
bias: a ~138,000 s offset is all-or-nothing.

> **Corollary — no retraction is needed anywhere else.** Any surviving
> *non-zero* GPUPROF number in this programme is safe by construction. PR #91's
> prefill census, PR #157, and the byte-price ledger all stand. r1 of #158 ran
> under the 3.13 venv, so no r1 number is invalidated either.

> **RULE: GPU↔host correlation must use `CLOCK_UPTIME_RAW`, never
> `time.perf_counter()`. A probe reporting "0 records inside N steps" is a
> FAILED RUN, not a zero-work result.** Fixed in `research/decode_probe.py:26-35`
> (`mach_now()`) with a loud `WINDOW CORRELATION FAILED` path at `:204-210`,
> shared by `nezuko_pr158_gap_probe.py:32`. ⚠️ **Not yet verified end to end** —
> no committed log yet shows a post-fix *non-empty* window; every r2 busy number
> was reconstructed offline from uncommitted `/tmp/*.err` files, so only the
> **wall** numbers are repo-reproducible today. That gap is Step 0 item 2 of
> #174.

**LAW 2 — cross-sweep reproducibility (§4.6.e).** Same protocol, two sessions:
`rsdr` moved **4.40 → 1.33 µs/disp (3.3×)** and `rrr` **4.90 → 8.06**, while
`ssq` (1.62→2.14) and `rsq` (2.26→2.18) reproduced. Pooled baselines differed by
only 23 µs, so this is not drift in the baseline — it is **arm-level
between-session scatter of ≈±70 µs**, which is ±1.8 µs/disp at Δ=39 but only
±0.36 at Δ=195. That exactly predicts which arms reproduced.

> **RULE: palindromic ordering kills within-session drift only. Within-session
> half-ranges understate true uncertainty 2–5×. Design local decode arms with
> Δ ≥ 150 dispatches, and read marginals as the cross-sweep envelope.**
> Note the asymmetry that follows: the ranked M5 receipt channel resolves
> ~10 µs/step on decode (cv 0.235% on T = 4.1436 ms) — **more sensitive than
> the local probe** — and the steady decode step is 100% host-independent. For
> small decode effects, a receipt is the better instrument, not the fallback.

### 4.9 ✅ RESOLVED (was: THE OPEN CONTRADICTION) — is there 0.456 ms/step of decode concurrency?

> **RESOLVED 2026-08-07 by PR #174 as reading R-B (sibling shadowing). See
> §4.12.** #158's "hidden concurrency ≤ 0.06 ms/step" bound is **RETRACTED** as
> an arithmetic artifact: its concurrent-arm de-inflation subtracted the
> destroyed concurrency `D` along with the per-CB cost `c`. The corrected
> per-CB cost is **0.540 µs/CB**, not 1.588. Decode intra-CB concurrency is
> **real, 382–448 µs/step, and already fully realized** by MLX's concurrent
> encoder. The rest of this section is retained as the record of the
> contradiction and of how it was posed.

**This was the single most important unresolved number in the programme, and it
sits directly under the decode axis that carries 75% of the score weight.**

Two measurements on the same host family answer the same question 7.6× apart:

| source | measurement | claim |
|---|---|---|
| **#158 §4.5** | `gpu_busy_sum` **flat at 7.99 ± 0.06 ms** while CBs go **45 → 204** | hidden concurrent work **≤ 0.06 ms/step** |
| **#101 §3.2** | forcing `MTL::DispatchTypeSerial` in the encoder costs **+0.456 ms/step** | **0.456 ms/step = 5.5% of the decode step** is real dispatch-level concurrency |

#101's arm is not weak. Eight runs, ABBA-verified live by a plumbing banner
(`s01=0,s02=1,s03=1,s04=0,s05=0,s06=1,s07=1,s08=0`), 392 samples each, **complete
separation** (every concurrent median below every serial median), pooled 95% CI
**[+4.70%, +6.28%]**, permutation p = 2/70 = 0.029 — the exact minimum attainable
for 4-vs-4. CB count and kernel code were unchanged; **only the encoder dispatch
type varied**. The probe was an env-gated `device.cpp` patch, since reverted —
`device.cpp` is not in `editablePaths`, so it could never ship, but it is a
perfectly good *instrument*.

**Three candidate resolutions, pre-registered on #174. All three are live.**

- **R-A — seam pipelining.** The 0.456 ms is per-*dispatch* tail/head overlap,
  not co-residency: 456/406 ≈ **1.12 µs/dispatch**. Note the arithmetic that
  makes this attractive: `SPLIT=1` inflates busy by 8572.8 − 7999.4 = **573.4 µs**,
  and 573.4/406 = **1.41 µs/dispatch** — suspiciously close. Nezuko's
  de-inflation constant `1.412` was derived on a **per-CB** model. If these are
  the same effect, the correct de-inflation unit is the **call**, which
  redistributes cost away from many-call short kernels and **changes the §2.b
  ranking**. Under R-A both results stand and are additive; the effect should
  scale with **call count**.
- **R-B — sibling shadowing.** The 0.456 ms is genuine co-residency, and
  nezuko's bound is **vacuous** for exactly the structural reason tanjiro's #157
  D1 found `gpu_busy_union` vacuous. #157 measured `two_cb` `overlap_eff`
  **0.4998 = full overlap**: *splitting a command buffer does not serialize its
  work*. So sweeping 45 → 204 CBs may simply not have removed the concurrency it
  was supposed to remove. Under R-B the effect is concentrated at a **few sibling
  sites**, not spread over dispatches. Known live example: `gate_sp` shares its
  input tensor `normalized` with the QKV qmv
  (`LagunaRuntimeModel.swift:5758`, `:5761-5762`, `:5802-5803`), creates no
  RAW/WAR hazard, so MLX inserts no barrier and its **8 threadgroups** run
  entirely in the shadow of a ~43 µs/call matvec.
- **R-C — currency mismatch.** Busy stayed flat while wall moved, so the effect
  is outside GPU busy altogether.

**Why it matters more than its size.** If R-B holds, the §2.b census
systematically **over-attributes** cost to kernels that are already free, and
the top of our decode target list is partly fictional. Every decode arm we
assign is priced off that census.

> **INTERIM RULE until #174 reports.** Do not treat a §2.b census row as an
> *exposed* cost without an independent exposure check. The known calibrator is
> `DARKBLOOM_AFFINE_GATE_SOFTPLUS`: the census charges `gate_sp` 199.2 + 63.1 =
> 262 µs/step, yet PR #101 removed a real inefficiency from it and measured
> **−0.04%, CI [−0.55%, +0.48%]** end to end. Its exposure factor is ≈0.1.

⚠️ **A second, smaller inconsistency inside #158 itself, still unexplained.**
§2.b's census prices `gate_sp_h64` at **199.2 µs/step** and `gate_sp_h48` at
**63.1**, while §1.2.b's own table (`:466`) quotes **241.7 / 77.3** for the same
kernels — matching the appendix census (`:1220`, `:1224`: 243.1, 77.3). Two
measurement sets ~20% apart in one document. Resolve before quoting either.

> **DO NOT RE-PROPOSE `gate_sp` OCCUPANCY RE-GEOMETRIZATION.** PR #101 built
> exactly that (parameterized `R`/`NS`, grid divisor `heads/(NS*R)`, 9
> geometries, bit-exactness *proved* with 128 payload comparisons and a live
> perturbation control) and measured **−0.04%**. The hypothesised "unexploited
> parallel axis" does not exist: the 2048-wide reduction is **already split
> 32-way across the simdgroup** (32 lanes × 8 values × 8 k-blocks) and closed by
> `simd_sum` (`:4304`). The only remaining bit-exact axis is one simdgroup per
> row = 2048 threads = **4×, not 32–64×**; anything beyond needs split-K plus a
> two-stage reduce, which changes float accumulation order. The 186 µs figure
> quoted in #158 §1.2 is an **estimated and explicitly unreachable ceiling**
> (`nezuko-pr158-decode-dead-time.md:692`, `:704-705`, `:743`), not a cost.
> `gate_sp` unique DRAM traffic is 2304 B/row × 2400 rows = **5.5296 MB/step**;
> achieved bandwidth is 22.2 GB/s (h64) and 17.5 GB/s (h48).


### 4.10 ⚠️ The roofline-ridge identity — the 67%/67% signature is *one* number

**This retires the most-quoted interpretation in the whole document.**

For nine rounds we have quoted the in-situ M5 gather-GEMM measurement as
"408.4 GB/s = 67% of 610, *and* 23.23 TFLOP/s = 67% of 34.7 — neither a
bandwidth problem nor a FLOP problem, therefore jointly saturated." That
reading is wrong, and the coincidence is algebraically forced.

Compute the kernel's arithmetic intensity from first principles:

```
AI = 2 × (tokens per expert) / (bytes per parameter)
   = 2 × 16 / 0.5625
   = 56.9 FLOP/B
```

Now compute the machine balance of the M5 Max:

```
machine balance = 34.7 TFLOP/s / 610 GB/s = 56.9 FLOP/B
```

**These are identical.** The prefill routed gather-GEMM sits *exactly on the
roofline ridge point*. When a kernel sits on the ridge, its bandwidth
utilisation and its FLOP utilisation are the **same number by construction** —
they are `θ` and `θ`, one efficiency scalar, not two independent roofs both
happening to bind at 0.67.

**Consequences, all binding:**

1. **"Jointly saturated" is not an observation.** Any kernel at this shape
   would show matching percentages at any θ. The 67%/67% coincidence conveys
   essentially zero information about *which* resource limits us.
2. **The byte total and the FLOP total are both pinned** by the model and the
   quantization format. We cannot move either. **Only θ moves.** Every prefill
   MoE idea must therefore be stated as "this raises θ from 0.67 to X, by
   mechanism Y" or it is not a proposal.
3. **There is a third resource.** If neither DRAM nor the FMA pipe is the sole
   limiter at θ=0.67, something else is stealing issue slots. The leading
   candidate is **three-way issue contention** — buffer loads, dequant integer
   ops, and FMAs each consuming roughly a third of issue bandwidth yields
   exactly ⅔ on both axes. See §0c on AGX address arithmetic: 64-bit integer
   add is emulated in 4 operations and dynamic `BITEXTRACT`/`BITINSERT` cost
   8–12 cycles. NVFP4 unpack is dynamic bit extraction plus 64-bit pointer
   math on the same ports as the FMAs.
4. **This is the sub-hypothesis tanjiro's #170 does not currently test.** His
   arms M2/S2/B2 perturb MMA count, threadgroup staging, and barriers — not
   address/bitfield issue pressure. Advisor feedback on #170
   (`pr170-r1-apple-nax-facts-and-optional-fourth-arm-2026-08-06`) offers an
   optional 4th arm and, more importantly, tells him that **a null on M2/S2/B2
   must not be reported as "H0 confirmed"** — it must be reported as "jointly
   saturated on the axes we tested".
5. **§7 idea 6 (dequant instruction diet) is the constructive follow-on** if
   #170's H3 wins.

**Calibration for how much θ is on the table:** MLX PR #3211 measures
**52–60 TFLOP/s fp16 on a real M5 Max** dense GEMM. Our gather-GEMM achieves
23.23 TFLOP/s — about **40%** of what the same silicon does on a dense fp16
matmul. That gap, not the 67%, is the prize.

**What this does *not* change:** the withdrawn "15.4 ms recoverable overlap
pool" stays withdrawn; the row-tile axis stays closed (§8); the excess
+14.30 ms over the derived floor is still a residual, not a measured pool.

---

### 4.11 ⭐⭐⭐ The M4/M5 regime difference — and the first measured transfer factor

**Source: PR #137 (maple-fern), ranked receipt `99b71258-abdd-4cce-bbe8-3e75161032e0`
(see `research/maple-fern-pr137-lmhead-cascade.md` §14), plus the competitor
snapshot `4b06e931` note.**

This is the most consequential doctrine change of round 25. It supersedes the
optimistic reading of "the steady decode step is host-independent".

#### 4.11.1 The regime statement

- **The M5 Max is instruction-bound during decode**, sitting at roughly **89%
  GPU utilisation**. Competitor snapshot `4b06e931`'s own note records this.
- **M4 Pro student hosts are bandwidth-bound during decode.** Our whole decode
  byte inventory (§2) and every byte-price argument was built on that regime.

These are *different limiting resources*. An optimisation that removes bytes
relieves the M4's binding constraint and does nothing for the M5's — and if it
buys those bytes with extra instructions, serialisation, or lower occupancy, it
is a straight loss on the ranked host.

#### 4.11.2 The two independent confirmations

1. **PR #137, our own ranked receipt.** A bit-exact lm-head sparse-refine
   rewrite measured **−63.7 µs/token** on M4 (kernel S4: 77.4 → 13.7 µs) and
   **+24.6 µs/token** on M5 (candidate decode `0.0049330185546875` s/tok against
   the promoted `97a5090c` arm's `0.0049083720703125`). **Transfer factor
   = −0.40 ± 0.24.** The whole pre-registered honest band (0.50–0.75) is
   excluded at ≥ 3.8σ. The arm's mechanism was pure bandwidth arithmetic: a
   traffic model (control ~9–13 MB vs ~3 MB at ~273 GB/s ⇒ ~50–70 µs vs
   ~11–13 µs) reproduces the M4 result exactly — which is precisely why it did
   not survive a host where bandwidth is not binding. The cost side is
   occupancy: the control launches **25,088 concurrent simdgroups**; the
   row-major arm launches **3,136**, and its serial `while(live_mask)` walk has
   latency = max over 3,136 Poisson(0.64) draws.
2. **Competitor snapshot `4b06e931`.** It landed **15 individually-validated
   bit-exact decode optimisations** and measured **+233.8 µs/token slower** on
   M5. Fifteen wins, all validated, all in the wrong direction on the ranked
   host. That is not bad luck; it is a systematic regime error.

#### 4.11.3 ⭐ THE BINDING RULE (applies to every decode assignment from now on)

> **An M4 decode result must state its mechanism — bandwidth reduction versus
> instruction/latency reduction — before any transfer to M5 is claimed. An M4
> decode win whose mechanism is bandwidth reduction is presumptively
> NON-TRANSFERABLE and must not be promoted on M4 evidence alone.**

Corollaries:

- **Instruction-count and latency mechanisms are now the privileged class.**
  A change that removes *work* (address arithmetic, redundant dequantisation
  ops, issue-slot contention, serialisation) targets the M5's actual binding
  resource. §7 idea 6 (the dequant instruction diet, raising θ) moves to the
  head of the decode queue on exactly this basis.
- **Byte-removal ideas need a second justification.** §7 idea 5 (lm-head
  two-level screening) and idea 8 (entropy recode of the bf16 planes) are both
  byte-based and are now in doubt on transfer grounds, independent of their
  arithmetic being correct.
- **This does not retract §3a.** The steady decode step remains
  host-independent for *kernel selection* — the only capability gate in
  `Sources/` is `lagunaExpertAlignedGatherEnabled`, which decode never reaches.
  M4 remains fully valid for implementation, correctness, bit-exactness,
  reachability, and wave analysis. What it is no longer valid for is
  **predicting the sign of a decode timing change**.
- **It also does not retract the byte-price law** (§2). That law converts
  removed bytes into score *on the assumption that bandwidth is binding*. On
  the ranked M5 that assumption is now known to be false for decode, so the law
  is an upper bound on decode and should be quoted as such.

#### 4.11.4 The `officialScore` decomposition — the canonical worked example

PR #137 also produced the cleanest possible demonstration of the
**`ns` for attribution, `officialScore` for ranking** doctrine (§3).

The receipt's `officialScore` fell **1.283%**. Decomposed:

| term | contribution |
|---|---:|
| `0.75 · log(decode_speedup)` | −0.340% |
| `0.25 · log(prefill_speedup)` | −0.951% |

The prefill term is **entirely the paired baseline draw**: the session's
baseline prefill drew **−3.755%** against the reference draw and **−4.210%**
against the pinned normaliser, while the *candidate* prefill was flat at
−0.022%. Baseline decode was quiet at +0.048% (0.20σ).

So a **−0.37% decode regression** presented as a **−1.28% catastrophe** on
`officialScore`. Judging the mechanism on `officialScore` would have been a
3.5× overstatement caused by a coin the candidate never touched. `ns` reported
the true −0.369%.

This is consistent with §0a row 5: `officialScore` **is** authoritative for
ranking (it is what the leaderboard uses), and it is **still** the wrong
instrument for attributing a small mechanism across sessions.

#### 4.11.5 ✅ RESOLVED — the frontier was unanchored for six merges; receipt `08ddee45` anchored it

> **Outcome (2026-08-07, PR #137 r3).** Receipt
> `08ddee45-3403-4a6f-aa75-bb9967d62763`, commit `456a92e5`, landed
> **`ns = 2.59440830`** against the promoted `2.5982163`: **−0.147% = −0.66σ**,
> clearing the pre-registered HEALTHY edge 2.5924 at −1.01σ. **ROW A.**
> **The six promoted maple merges after `97a5090c` did not regress the M5
> frontier.** One receipt anchored six previously unvalidated merges, and the
> +24.6 µs/token seen in r2 is convicted as the row-major arm, not the merges.
> Correctness unanimous (`max_abs_diff 0`, 1344 steps, GPQA 9/9 both, both
> floors True). The pre-registered table below is retained as the record of how
> the decision was made *before* the number arrived. Three consequences are
> carried forward in §4.11.6.

The free-feed audit prompted by this PR found that **every `Model: senpai` row
after our promoted receipt `97a5090c` belongs to another campaign or failed.**

**No maple merge landed after `97a5090c` has ever been measured on the ranked
M5.** Our rank-1 standing (`officialScore 2.58882784082067`, commit `3e165fa`)
rests on a commit roughly six merges behind the current advisor branch. Every
merge since has been accepted on M4 evidence, research value, or zero-scored-byte
grounds — which was defensible under the old doctrine and is *not* defensible
under §4.11.3.

This also means the +24.6 µs/token in PR #137 is **not yet cleanly attributed**:
it could be the arm, or it could be the six unvalidated merges, or both.

**Action taken:** PR #137 r3 is assigned the **anchoring receipt** — the
identical tree with `DARKBLOOM_LMHEAD_ROWMAJOR_REFINE` defaulted to the shipped
arm, dispatched to the ranked M5. Pre-registered decision table (against
promoted `ns = 2.5982163`; paired cross-session sd on `ns` = 0.222%):

| flipped-default `ns` | reading | action |
|---|---|---|
| `≥ 2.5924` | frontier healthy; the +24.6 µs is the arm | merge #137 for the anchor, arm default-OFF |
| `2.5867 – 2.5924` | ambiguous; cost shared | merge for the anchor, open a bisect assignment |
| `< 2.5867` | the merged frontier itself regressed | **programme emergency**: bisect the six merges before any further promotion |

**Standing rule from this:** the advisor may not let more than ~2 merges
accumulate without a ranked anchor. An anchoring receipt is cheap (one default
flip, no new code) and is now a scheduled programme cost, not an optional one.
The anchor is a *scheduling* obligation, not a hypothesis — it buys attribution
for every merge behind it at the price of one receipt.

#### 4.11.6 ⭐ Three constants the anchoring receipt bought

**(a) M5 host drift is measurable, monotone, and now correctable.** The two
instruments reconcile exactly, and their difference *is* the drift. `ns` uses
fixed normalisers and does not cancel host drift; `decode_speedup` uses the
same-session paired baseline and does. Across the three receipts the paired
baseline decode ran

| receipt | paired baseline decode (s/tok) | vs promoted |
|---|---|---|
| `97a5090c` (promoted) | 0.01384496646875 | — |
| #137 r2 | 0.013851607421875 | +0.048% |
| #137 r3 (`08ddee45`) | 0.01385760709375 | **+0.091%** |

i.e. **monotone +0.091% over roughly three hours of M5 wall time**. The r3
candidate reads −0.147% on `ns` and −0.073% on `decode_speedup`; −0.147% +
0.091% = −0.056%, matching the paired figure inside noise. This is the first
*direct* measurement of M5 baseline drift rather than an inference from it.
**Practical rule:** when comparing an `ns` value to a promoted `ns` taken hours
earlier, the baseline may legitimately have drifted ~0.03%/hour in the
pessimistic direction; prefer the same-session paired `decode_speedup` for
attribution and reserve `ns` for cross-session bookkeeping where the paired
figure is unavailable.

**(b) A second live confirmation that `officialScore` cannot attribute a small
mechanism.** r3's `officialScore` 2.57481890 sits −0.593% below the 2.59018572
bar against a 0.587% σ — 3.7× looser than `ns`. Almost all of it is the prefill
baseline draw (prefill_speedup 1.9628 vs 2.0015, −1.93%, on a σ that is
*entirely* baseline) while candidate prefill barely moved (0.00019138 vs
0.00019120; S = 97.99 vs 97.89 ms). **Reading this receipt on `officialScore`
would have manufactured a −0.59% regression out of a tree provably
byte-identical in behaviour to base.** Consistent with §0a row 5:
`officialScore` is authoritative for *ranking* and wrong for *attribution*.

**(c) The receipt price is 43 min 55 s, not ~35 min.** Measured end to end on
r3: dispatch 01:57:14Z → slot blocked by another campaign 02:00:09–02:20:10
(**19.6 min queue**) → accepted 02:20:19 → terminal 02:41:08 (**20.8 min
validating**). Plan receipt-bearing assignments against ~45 min per receipt,
with the queue half of that outside our control.

---

### 4.12 ⭐⭐⭐ PR #174 — decode concurrency resolved, and the decode step re-priced against the roofline

PR #174 (maple-nezuko, `maple-2026-08-06p-decode-exposure-audit`, head
`87b1f240`) is the most consequential research round of the campaign so far. It
carries zero submitted bytes and changes no kernel; what it changes is what we
believe about where decode time lives.

#### 4.12.1 The arithmetic bug, and the retraction

#158 measured the concurrent arm and the serial arm and de-inflated the
concurrent one by an estimated per-CB cost `c`. But the concurrent arm's busy
time is `busy_c(k) = busy_s(k) − D(k)`, where `D(k)` is the concurrency
destroyed at split `k`. Fitting `c` on the concurrent arm therefore recovers
not `c` but `c_true + [D(0) − D(1)]/361.2`. Verified directly:
`(8598.5 − 8022.0)/361.2 = 1.596 = 0.540 + 381.5/361.2`.

**#158 conflated the per-command-buffer cost `c` with destroyed concurrency
`D`.** Two constants change:

| constant | #158 value | corrected |
|---|---|---|
| per-CB cost | 1.588 µs/CB | **0.540 µs/CB** (3.0× smaller) |
| census de-inflation | 1.412 µs/call | **+0.939 µs/call** (opposite sign) |
| hidden concurrency | ≤ 60 µs/step | **382–448 µs/step** |

#158's headline bound is retracted. The merge of #158 stands — its
instrument, its two measurement laws, and its clock-defect fix are all sound —
but its central number is not.

#### 4.12.2 The verdict: R-B (sibling shadowing)

Three readings were on the table. R-A: the cost is per-*seam* (barrier
boundaries between dispatch groups). R-B: independent sibling kernels genuinely
overlap inside one concurrent encoder. R-C: the effect is an artifact of
wall-vs-busy accounting.

- **R-C dies** on arm A0 (16 runs, ABBA-ABBA, 0 token divergences): forcing
  serial dispatch at the shipped 45-CB split costs wall **+420.9 µs**
  (p=.057) and `gpu_busy_sum` **+448.0 µs** (p=.086), while the wall-minus-busy
  gap moves −21 µs (p=.63) and `gpu_busy_union == gpu_busy_sum`. CBs/step and
  dispatches/step are exactly unchanged. The destroyed overlap is **intra-CB**.
- **R-A dies** on the per-group census: the per-seam price varies 4× and
  **falls** as groups grow (3 dispatches → 3.33 µs/seam; 5 → 1.70; 10 →
  1.40–1.52; 12 → 0.83–0.93). R-A predicts the opposite ordering.
- The discriminating number: SPLIT=2 removes 159 seams and gives
  `D(2)/D(0) = 387.0/448.0 = 0.864`. R-A predicts 0.560; R-B predicts ≈0.95.
  The mixture weight is `w = 0.78 ± 0.24` (1σ), ±0.47 once doctrine-inflated —
  **directional only**, but the sign is unambiguous.

PR #101's +456 µs now replicates across three sessions and five arms:
**421 / 448 / 456 / 490 / 580 µs/step**.

#### 4.12.3 Which kernels are actually hiding — and the exposure factor E

Nested-group composition isolates exactly **three** shadowed kernels:
`gate_sp_h64` (6.64 µs/call × 30), `gate_sp_h48` (6.31 × 10), and
`shared_nvfp4_swiglu_qmv_rows1` (6.09 × 39). Budget 499.9 µs/step vs 451.5
measured ⇒ **E = 0.10, CI [0.00, 0.25]**. All three hide inside 35–43 µs/call
matvecs. This mechanistically confirms PR #101's `gate_sp` NO-GO: you cannot
speed up a kernel that is already free.

Everything large is **exposed**. Estimator C's well-powered arm (A1b,
`FUSED_QKV_PROJECTION`, ΔI = +4955.2 µs/step = 33× the design floor) gives
**E = 0.999, CI [0.87, 1.14]** across 140 calls / 3379.3 µs/step. Estimator A
gives `sliding_fused_attn_ring_v1` **E ≥ 0.90** and `oproj_act_h64`
**E ≥ 0.94**. The remaining 11 census rows (4113.5 µs/step) carry a pooled
`E_rest = 1.013`.

> **NEW DOCTRINE RULE.** *A §2.b census row is not exposed cost until it has an
> exposure factor. Small hazard-free kernels sitting beside 35–43 µs/call
> matvecs have E ≈ 0.10 and are worth approximately nothing.* The re-priced
> census moves **574 µs/step of nominal cost down to 57 µs/step of real cost**;
> the top-15 rows barely move (max |Δrank| = 2).

#### 4.12.4 Honesty, and what is carried

The pre-registered k=1 tripwire **fired** (+66.5 µs against a 50 µs limit).
Nezuko withdrew A0 as a pre-registered quantitative result and carries `D(0)`
as the **range 382–448 µs/step**. Two results are `D(0)`-independent and stand
on their own: the §0 algebraic identity, and the §3.5 bundle reading. An
independent frontier review raised seven findings; all seven were fixed in the
same revision. `gpu_busy_sum` **survives** as a within-arm work accountant and
**fails** as a concurrency detector.

#### 4.12.5 ⭐ The re-pricing that matters: census rank is not headroom rank

Pricing the whole decode step against the M4 Pro DRAM roofline (273 GB/s, 20
cores) splits the 8.45 ms step into three pools:

| pool | effective µs/step | % of step | byte floor µs/step | headroom µs/step | headroom % score |
|---|---:|---:|---:|---:|---:|
| NVFP4 / bf16 weight streaming | 5920 | 70.1 | 5582 | **338** | 4.94 |
| attention (2 kernels) | 881 | 10.4 | 317 | **564** | **8.26** |
| glue (kilobyte operands) | 641 | 7.6 | 152 | **489** | 7.16 |

Achieved bandwidth in the weight pool: `decode_nvfp4_qkv_h64` **268.2 GB/s
(98.2% of peak)** · `qkv_h48` 262.7 (96.2) · `oproj_act_h64` 256.9 (94.1) ·
`dense_down_residual` bf16 249.5 (91.4) · `dense_gate_up_swiglu` bf16 249.0
(91.2) · `routed_..._top8keys_r1_v2` 248.3 (91.0) ·
`routed_shared_..._down_res` 243.7 (89.3) · `oproj_act_h48` 237.3 (86.9).

> **The top four census entries are 4816 µs/step = 57% of the decode step, and
> their combined remaining headroom is 377 µs/step — and capturing even that
> requires literally 100% of DRAM peak. The weight pool is FINISHED. Rank 2 in
> time is near-last in opportunity.**

The two attention kernels run at **101.4 GB/s (37.1% of peak)** and **95 GB/s
(34.7%)** on unique bytes. That is the anomaly, and it is not a byte problem.

#### 4.12.6 The priced target list

- **T1 — decode attention occupancy. ⛔ MECHANISM REFUTED by #196 (merged);
  the 564 µs/step / +8.26% survives ONLY as a bytes-based ceiling with no
  known route to it.** Both decode attention kernels dispatch **one threadgroup
  per PAIR of query heads** (`LagunaRuntimeModel.swift:1370` sliding, `:1819`
  full; both compute `head0 = pair_tg * 2`). 64 sliding heads ⇒ **32 TGs**;
  48 full heads ⇒ **24 TGs**. Bytes are not the constraint: GQA replication
  puts replicated traffic at 149%/104% of DRAM peak, i.e. cache-served, while
  unique bytes are 37.1%/34.7%. The pool ceiling (881 µs/step at 101/95 GB/s
  vs the 98.2% the same host demonstrates on `decode_nvfp4_qkv_h64`) is still
  the *arithmetic* target, but **#196 shows the kernels are issue/ALU-bound,
  not bandwidth-bound** — the marginal wave costs 7.408 µs against an 8.891 µs
  lone-TG latency, so co-residency recovers only ~17%. A future attack must
  reduce **instructions**, not bytes or threadgroups. The only measured
  instruction-side lever left is **the merge epilogue (§4.12.8 G)**, worth
  +0.685% at ceiling. Both the 227 µs/step tail estimate and every KV-split
  geometry are dead (§8).
- **T2 — routed-MoE matvec bandwidth. 188 µs/step, +2.75%. Fenced to #148.**
  `routed_..._top8keys_r1_bf16_v2` at 91.0% (gap 7.2 pts, 110 µs) and
  `routed_shared_..._down_residual_bf16_r1_v5` at 89.3% (8.9 pts, 78 µs). Soft
  ceiling: some of the gap is structural (gather indirection, per-expert scale
  reload).
- **T3 — the glue pool. 489 µs/step ceiling, 100–300 µs/step realistic.**
  `residual_rms_router_rpg8_keys_v1` 305.1 µs/step (floor 151.0) ·
  `decode_router_top8_ordinal_table_norm` 185.7 (floor 0.1 — it sorts 1.03 kB
  at an implied **0.2 GB/s**) · `rmsbfloat16` 124.6 (floor 0.6) · six kernels
  below 8 µs/step totalling 25.5. Fusion candidates in order of mechanicalness:
  (1) `rmsbfloat16` into its consumer matvec prologue; (2) **the router-top8
  sort into `residual_rms_router_rpg8_keys_v1` — ~186 µs/step ≈ 2.72% score,
  reading no new bytes**; (3) residual epilogues into producing matvecs. These
  are **three separate small experiments**, not one, and each consumes TG
  memory in kernels already at 91–98% of roofline.

The glue pool is **explicitly disjoint** from per-dispatch host encode cost
(24 µs/step total). Conflating the two is the error that sent #158 chasing
per-dispatch overhead.

#### 4.12.7 What this closes

- **Decode intra-CB concurrency: CLOSED — already harvested.** Further overlap,
  dispatch-granularity, dispatch-type, and CB-re-splitting work is on the STOP
  list. The shipped 45-CB split is already at the gap minimum.
- **Per-CB overhead: CLOSED.** 45 CBs × 0.540 µs = **24 µs/step total**.
- **The three shadowed kernels (`gate_sp_h64`, `gate_sp_h48`,
  `shared_nvfp4_swiglu_qmv_rows1`): CLOSED at E ≈ 0.10.**
- **Constant per-dispatch census corrections: CLOSED.** The correction is not a
  constant; it is an exposure factor that must be measured per family.
- **The dense bf16 MLP → NVFP4 idea: RULED OUT BY THE PRECISION ENVELOPE.**
  `dense_gate_up_swiglu` and `dense_down_residual` (`laguna_dense_*_bf16_v1`,
  `LagunaRuntimeModel.swift:8040`, `:8133`, `vec<bfloat,4>` loads) move 101 MB
  and 409 µs per step = 4.8% of the step. NVFP4 would be 28 MB / ~104 µs — a
  306 µs/step, **4.48% score** prize. The accepted envelope permits only
  group-32 affine INT8 for Q/K/V/O and per-head `g_proj`. **Recorded so nobody
  re-derives it.**
- `lmhead_int5_base_coarse_delta` (427.0 µs/step, 6.25%, census rank 6) is not
  byte-modellable (pruned/sparse) and is fenced to #137.

#### 4.12.8 ⭐⭐⭐ CORRECTION to §5.1 — the decode attention kernels, read directly

Advisor read both kernels in `Sources/MLXFastModel/LagunaRuntimeModel.swift` at
base `3b75a115`. Four premises change; two of them invert the arm ranking #174
§5.1 proposed. Handed to #196 as its §1.

**(A) The threadgroup is 1024 threads = 32 simdgroups, not 32 threads.**
`lagunaSlidingFusedAttention` wrapper **:1719-1765**, kernel
`laguna_sliding_fused_attn_ring_v1` declared **:1369-1370**:
`grid ((heads/2)*1024, 1, 1)`, `threadGroup (1024,1,1)`,
`outputShapes [[1, heads, 1, headDim]]`, `.bfloat16`; `heads = 64` ⇒ **32 TGs ×
1024 threads**. `params` comes from `lagunaRingIdxAtlas[writeIdx]` when
`lagunaParamsAtlasEnabled` (env `DARKBLOOM_PARAMS_ATLAS != "0"`, default ON);
512-entry atlas built during warmup at **:1774-1790**.
`lagunaFullFusedAttention` wrapper **:2220-2266**, kernel
`laguna_full_fused_attn_grow_v1` declared **:1818-1819**: same grid/TG shape,
`heads = 48` ⇒ **24 TGs**; `params = MLXArray([writeIdx, writeIdx+1,
capacity])` (no atlas); `angles` is `headDim/2` wide vs full `headDim` for
sliding. Call sites: sliding **:5972**, full **:5998**; full-attention pipeline
prewarm **:2270-2293**.

**(B) The kernel ALREADY implements a 32-way flash-decoding split with a
working merge.** §5.1's "16 sequential KV iterations, no split, no
flash-decoding merge" is **RETRACTED**. Offsets relative to the sliding body at
:1369 — constants `head_dim=128, window=512, gqa=8, BN=32, BD=32, BDP=BD+1,
qk_per_thread=4, v_per_thread=4, rotary_pairs=64, N=512, typedef float U`.
Prologue `if (sg < 3)` stages q(head0)/q(head1)/k(kv_head) with RMSNorm+RoPE
into `tg_q0/tg_q1/tg_k`, `else if (sg == 3)` stages v; **one**
`threadgroup_barrier` after the prologue (rel :83); then
`if ((head0 % gqa) == 0 && sg == 0)` writes the new K/V ring row (rel :85-:96).
Threadgroup arrays `outputs[4*BN*BDP]`, `max_scores[2*BN]`,
`sum_exp_scores[2*BN]` (rel :98-:100) plus four `bfloat[head_dim]` planes. The
KV loop `for (; i + BN < N; i += 2*BN)` (rel :133) strides by **64**, is 2-deep
software pipelined (`pair_score0/1`, `pipeb_score0/1`, each `simd_sum`'d), and
runs **8 iterations covering 16 KV positions per simdgroup**. **There is NO
`threadgroup_barrier` inside the KV loop**; barriers occur only in the
post-loop merge at rel :239, :262, :270. That merge (rel :225-:290) carries
per-simdgroup running `pair_max0/1`, `pair_sum0/1`, publishes them to
`max_scores`/`sum_exp_scores`, `simd_max`es the global max, rescales by
`pair_global_factor`, `simd_sum`s the partials, and accumulates `outputs[]`
over two planes (`pair_planes = 2`, `pair_plane_size = BN*BDP`). The
full-attention kernel mirrors it exactly (`gqa=6`, `rotary_pairs=32`,
`yarn_mscale=1.3465735912322998f`, loop rel :142, merge rel :277-:314).
⇒ **A KV split across threadgroups is a LIFT of existing, already-bit-exact
code, not a new algorithm.**

**(C) ⛔ RETRACTED IN FULL by PR #196 (merged). The occupancy tail does not
exist and T1 is CLOSED.** My original table computed *relative makespan*
`ceil(N/C)/S` and concluded that S = 5 was uniquely optimal on both hosts.
Nezuko measured the kernels directly (M4 Pro, unit-resolution K = 1…3C
staircase on **both** kernels) and refuted it on two independent grounds:

1. **There is no tail to recover.** Sliding dispatches **N = 32** TGs and full
   dispatches **N = 24** (`LagunaRuntimeModel.swift:1761` / `:2263` with
   `slidingAttentionHeads = 64`, `fullAttentionHeads = 48`). Both are ≤ C = 40,
   so **on the ranked M5 both attention dispatches already run in exactly one
   wave.** The "80% / 60% efficiency" figures are *idle slots*, and **idle slots
   cost zero time.** The claimed 20%/40% recoverable tail, the ~227 µs/step M4
   estimate, and the ~110 µs/step M5 / +1.6% score prize are all **dead**.
2. **The relative-makespan model was wrong because per-TG duration is not
   `d/S`.** The measured law is `T(K) = a + b·ceil(K/C)` with **a = 1.661 µs**
   (once per call), **b = 7.408 µs** (per wave), fit error +0.0/+1.5/+0.0% at
   W = 1/2/3. Decomposing a single wave at K = 20 gives fixed **f = 3.130 µs**
   and marginal **g = 0.7483 µs/KV-iter**, i.e. per-wave fixed **φ = 1.469 µs**
   on top of `a`. Because φ is paid per wave and is *not* divided by S, **S = 2
   is algebraically exactly one extra φ worse than S = 1 for any f > 0**
   (`a + 2φ + 8g` vs `a + φ + 8g`). Every S ≥ 2 strictly adds waves while
   conserving work ⇒ **every split loses, unconditionally.**

Measured, wave-matched at C = 40 (P4b emulation): S=1 **9.078 µs**, S=2
**10.384** (1.144×), S=5 **15.468** (1.704×), S=10 **19.832** (2.185×). At the
real M4 C = 20, where quantization *is* real, break-even needs a fixed cost
below 0.533 g = 0.399 µs; the measured f = 3.130 is **7.8× short** and even the
most generous φ = 1.469 is **3.7× short**. Direct P4 at C = 20 is monotone
worse: 18.333 / 20.309 / 27.296 / 34.875 µs for S = 1/2/5/10. Note the
S-efficiency table *does* reproduce my arithmetic (S = 5 is uniquely 100% on
both kernels at both core counts) — **and those 100% points are among the worst
absolute timings.** That is the whole lesson.

**M5 transfer is not in doubt.** The refutation rests on `32 ≤ 40` and
`24 ≤ 40`, arithmetic over runtime constants, not on any M4-only number. The M4
timings only confirm the mechanism and rule out the two-wave fallback, where the
split also loses.

**Doctrine that replaces the retracted table:** model a decode kernel as
`T = a + W·φ + work`, where `W = ceil(N/C)`. **Threadgroups up to C are free**
(#196 §7.2). **Idle slots below C cost zero.** Never price a decode geometry
change with a relative-makespan ratio.

**(D) The head-axis repartition idea (1 head per TG, grid 32→64 / 24→48) is
DEAD by the same arithmetic** — 64/80 = 80%, identical to today on both hosts —
**and it additionally doubles K/V read traffic**, because the two heads in a
pair currently share the staged K/V (`tg_k`, `tg_v`, `kv_head = head0/gqa`).
Closed; do not re-derive.

**(E) The merge is the hazard.** An inter-TG merge must be added. (a) a second
dispatch is **RAW-dependent hence fully exposed** — ~3–5 µs × 40 calls/step =
120–200 µs/step, plausibly eating the whole 227 µs prize; (b) float atomics
break reduction order; (c) **atomic-counter "last TG merges" with a fixed
index-order reduction over the S partials is deterministic and bit-exact —
recommended**; (d) folding into `oproj_act` is misaligned (contraction
6144/8192). Merge cost must be pre-registered as a separately measured row.

**(F) ✅ THE GATING UNKNOWN IS RESOLVED by #196 — 32 and 96 are both correct and
measure different things.**

- **96 simdgroups/core is the RESIDENCY CEILING** — a hardware slot limit.
  Nezuko's rendezvous probe measured **3 TGs/core at 1024 threads = 96
  simdgroups/core**, and the number is *invariant in threadgroup size*
  (1024/512/256/128 threads ⇒ 3/6/12/24 TGs per core = 96 simdgroups every
  time) and **flat in threadgroup memory from 16 B all the way to 32768 B**.
  This reconciles #57, #138 and #157.
- **32 simdgroups/core is the THROUGHPUT WIDTH** — one 1024-thread TG per core
  per wave. This is what the staircase measures and what governs performance.
  **Use 32 for all performance modelling; use 96 only for co-residency
  questions.**

The staircase is unambiguous. Sliding: flat 8.891–9.104 µs to K = 20, **+6.482
riser at K = 21**, flat to K = 40, **+6.444 at K = 41**. Full: flat 9.128–9.327,
**+6.250 at K = 21**, **+6.902 at K = 41**. In-wave mean |Δ| ≈ 0.06 µs, so the
risers are a **100× discontinuity**. The pre-registered kill (≥2 co-resident TGs
*and* no step at N = cores) therefore did **not** fire: co-residency is 3, but
the step at K = C is present and huge.

Two corollaries worth carrying:

- `b / lone-TG latency = 7.408 / 8.891 = 83.3%` ⇒ **co-residency recovers only
  ~17% of a wave.** These kernels are **issue/ALU-bound, not latency-bound**,
  consistent with the published "ALU saturates at ~24 simdgroups/core".
- **Shrinking attention threadgroup memory buys ZERO residency** (#196 §7.3):
  both the real 18448 B body and a 10000 B halved-plane variant cap at 3 TG/core.
  That family is closed.

Caveat as stated by the author: measured on M4 Pro (Apple GPU gen 16); the
96-slot ceiling is **not verified on the ranked M5**. The parts of the
conclusion we rely on (§4.12.8 C) do not depend on it.

**(G) ⭐ THE SUCCESSOR TARGET #196 LEFT BEHIND — the intra-kernel merge
epilogue.** While pricing the split, nezuko measured the *existing* post-KV-loop
merge (3 `threadgroup_barrier`s + 4 threadgroup passes over `outputs[]`,
sliding-kernel offsets rel :225–:290) at **1.068 / 1.072 / 1.170 µs for
N = 64 / 256 / 512 rows — CONSTANT in N.** That is ~80% of the very per-wave
fixed cost φ that killed the split, and **12.9% of a 512-row call**. It is
therefore the largest *measured, structural* fixed cost inside the two decode
attention kernels.

Ceiling if the merge were free: 40 calls × 1.17 µs = **46.8 µs/step = +0.685%
score**. A realistic 30% shave ≈ **+0.21%**. Small, but it is a *fixed* cost on
the critical path of a kernel with **E ≥ 0.90** (fully exposed, #174 §3.6), it
needs no new bytes, and the instrumentation already exists. This is the natural
next assignment on the attention surface — note it is an *intra*-TG cost, so
none of the inter-TG merge hazards in (E) apply.

## 5. `_nax` safety rig (mandatory for any `_nax` arm)

Because M4 cannot execute these kernels, a broken `_nax` change measures as a
clean flat local result and then fails or silently falls back on M5. Required:

1. Environment kill-switch for in-binary A/B.
2. Offline MSL compile + pipeline-statistics check **proving a non-empty MMA**
   (`research/nax_msl_compile_check.sh`).
3. A **positive kernel-selection assert** — prove the `_nax` path was taken.

Known silent-failure modes:

- odd `TN>1` ⇒ empty `tile_matmad_nax`
- `SM<16` ⇒ `TM=0`
- the accept gate at `quantized.cpp:1660-1671` requires `bm==64 && wm==4` and
  **silently falls back** otherwise

Keep `mlx-generated/*.cpp` twins consistent with their `.metal`/header source;
that embedded source is what gets compiled at runtime.

---

## 7. Held for round 25 — the assignable queue

Ranked by expected value **now that the +0.61% acceptance bar is retired**
(§0a row 6). The first three were killed *only* by that bar and are revived
verbatim; all three are small, bit-exact and cheap to specify.

| # | arm | prize | why it is assignable today | first blocker |
| --- | --- | --- | --- | --- |
| **R1** | **prefill `PREFILL_ASYNC_LADDER` stride sweep** | **≈+0.34%** | one-literal, byte-neutral, bit-exact edit at `LagunaRuntimeModel.swift:733`; stride has **never** been swept | M4 cannot resolve 0.037% by wall clock — needs the M5 receipt channel (≈2.3σ ⇒ ~3 receipts) |
| **R2** | **shared-expert SwiGLU epilogue in prefill** | **+0.040%** (plus a **+0.028%** zero-byte sub-lead) | the concatenated NVFP4 `[gate; up]` bank already exists and is default-on; **no `MLXFastTransform` work** | the epilogue must be added to `fp_qmm_t_nax_static` (ships `wm=2,wn=2` ⇒ `kSwigluRegLocal` false); bf16-sigmoid bit-exactness is the top risk |
| **R3** | **lm-head cascade fusion remainder** | **+0.060%** | fern's #137 Step 0 already priced it exactly (5.2 µs M4) and the code is in her region | must wait for #137 to merge, then folds into the same cleanup PR |

**R1 provenance warning — read before assigning it.** The doc comment at
`LagunaRuntimeModel.swift:719` quotes ranked numbers (1.87782 → 1.88526,
+0.40%) for this knob. Those are **uncorroborated**: the line arrived in
`6aaba9d` ("Validate submission 0c1ab7f8-…", `yukon-autoresearch[bot]`,
2026-07-26), an **imported external competitor snapshot**, and
`leaderboard_promotions_2026-08-02.md:93` records that same submission at
**1.3271399980 (rank 34)**. Treat the +0.40% as folklore; our own derivation
(below) is what justifies the slot.

> **The decode ladder IS swept, and it contradicts the prefill gloss.**
> `lagunaDecodeAsyncStage` (`:677`, env `DARKBLOOM_DECODE_ASYNC_STAGE`
> `:679-680`, default `"at:0,1,7,15,23,31,39"`, mask built `:10656-10668`).
> Sweep (notes/52, two Latin squares, 66/66 correct), normalised to the
> shipped 7-rung ladder:
>
> | arm | fires/step | relative |
> | --- | ---: | ---: |
> | `off` | 0 | 10.3735 ms absolute |
> | `ladder8` | 5 | 1.0000 |
> | `ladder6` | 6 | 1.0064 |
> | `at:1,7,15,23,31,39` | 6 | **1.0170** |
> | `ladder2` | 20 | 1.0169 |
> | `ladder1` | 40 | 1.0178 |
> | lone fire at layer 1 | 1 | **0.9476** |
>
> Six fires cost either +0.64% or +1.70% **depending only on where they are**,
> and one well-placed fire beats every ladder by 5%. ⇒ **placement, not
> density.** The decode ladder is do-not-retry; the *prefill* ladder has never
> been touched, and R1 must sweep placement as well as stride.

**R1's own derivation.** Prefill forces the graph ≈41×/forward: the ladder
only fires in the `else` branch of `if i == layers.count − 1, h.dim(1) > 1`
(`:10863`), so layer 39 never fires ⇒ ~39 fires at stride 1, plus the terminal
`eval(logits)` and the `greedyToken` argMax host readback. Stride 8 removes
~34 fires; at the **M5-measured** +27.177 µs/cb that is ≈0.93 ms off
S ≈ 97.95 ms ⇒ **≈+0.34%**. M4 *can* validate fire count, CB count,
bit-exactness and correctness — it just cannot rank the result.

> ⚠️ **`Evaluate.swift` and `CompiledDecode.swift` are DEAD SURFACE.** They are
> editable and they look like the decode loop; they are not it. The scored
> serial loop is `Sources/MLXFastTrustedHarness/LagunaRuntimeWorker.swift`:
> `case "prefill":` `:361-381`, `lagunaLogits(...)` `:206-214`, `eval(logits)`
> `:374`, `case "decode_begin"` `:383+`, `func prefill` `:1800`, `func
> decodeStep` `:1814`. Timing bracket `LagunaRuntimeBenchmark.swift:809-811`,
> worker selection `:480-495`, decode phase `:864-896`.
> (`Sources/MLXFastHarness/LagunaRuntimeWorker.swift:201` is an **untrusted
> duplicate** — editing it changes nothing.)

### Also held

- **H1 row-adaptive dual-path gather kernel.** Biggest single arm on the board
  at **+1.4…+2.9%** — but it is **not bit-exact** and it is **M4-blind**. Needs
  a correctness story and the `_nax` safety rig before it can be assigned.
  **Its bar just rose:** §3.5 means a passing greedy-token gate proves nothing
  about logit drift, so H1 needs an argument about *how far* the logits move,
  not a token-equality demonstration.
- **Shared-expert SwiGLU epilogue in prefill.** *Re-scoped after a pricing pass
  refuted the first version of this lead; the earlier "58.5 + 24 = 82.5 MiB by
  flipping two guards" framing is **wrong** and is retained nowhere.* Corrected
  position:
  - The shipped `fuse_swiglu` predicate lives inside the **routed-expert gather
    kernel** (`fp_quantized_nax.h:1797`) and needs `lhs_indices`/`rhs_indices`
    plus `M>=64 && bm==64 && wm==4`. **Neither candidate site can dispatch to
    it.** There is no guard to flip.
  - **Dense layer 0 is closed.** `N=16384` fails the predicate *and* the weights
    are plain bf16 `Linear` (`LagunaRuntimeModel.swift:8438-8446`) — no
    quantized kernel exists to extend. The `x.dim(1)==1` guard at `:8423` is
    **load-bearing correctness**: it protects single-row GEMVs with hard
    `precondition`s that crash at `M=512`.
  - **Shared expert is still worth a slot.** The concatenated NVFP4 `[gate; up]`
    bank already exists (`prepareFusedSharedGateUp()` `:8248-8276`, default on),
    so **no `MLXFastTransform` work is needed**. The prefill guard is at
    **`:8463`** (not `:8503`) and is conservative scoping, not correctness.
  - **But the real work is adding a new epilogue to `fp_qmm_t_nax_static`**,
    which ships `wm=2, wn=2` ⇒ `SN=32` ⇒ `kSwigluRegLocal` false. Threadgroup
    and register budget are **free** (9,224 B of 32,768; the stage is a cast
    alias). Value **78.0 MiB written+read** (2.000 MiB × 39 layers) + 78 fewer
    dispatches. Lifting the guard *alone* saves **zero bytes**, only 39
    dispatches ≈ **+0.028%** — below MDE, stepping stone only.
  - **Prefill-only.** Both sites are already fused in decode, so this cannot
    touch the 75%-weight axis.
  - Top bit-exactness risk: the fused epilogue's bf16 sigmoid under
    `fp contract(off)` vs `MLXNN.silu(gate)*up` under `compile(shapeless:)`.
    Greedy-token gates prove token equality, **not** bit-exactness.
  Full corrected evidence:
  [`h5-per-expert-fused-ffn-closure.md`](h5-per-expert-fused-ffn-closure.md) §6.
- **Incidental occupancy datum from the same investigation:** average rows per
  expert is 16 (route-histogram mean = 16.00) against `SM=16`, so on the average
  expert **only 1 of 4 simdgroups is active** in the gather GEMM. Independent of
  the above; consistent with tanjiro's #138 line of attack.
- **Post-merge cleanup PR**, now genuinely owed — #138 shipped **+5,164 scored
  bytes** and headroom is down to 73,089 B. Three concrete targets, deletion as
  the explicit default:
  1. the **dead BK128 machinery** in `_nax` (#138, default off, unreachable on
     M4) if no `_nax` arm adopts it within ~2 rounds;
  2. tanjiro's **9 near-duplicate `.metal` variants**;
  3. fern's **`DARKBLOOM_LMHEAD_ROWMAJOR_REFINE` dual-arm flag** and the
     superseded S4 kernel, the moment #137 merges.

### ⭐ Round-25 frontier programme: own the *inter-kernel timeline*

Source: plateau-escalation frontier readout, 2026-08-06 (batch
`maple-r25-plateau-escalation-2026-08-06`, task `208828fb`). This is the
**strategy-tier change** demanded by the plateau protocol. Every family in §8
was closed by attacking *intra-kernel* efficiency. The two structural claims
below say the remaining money is somewhere else.

**Structural claim 1 — decode's remaining 1.20 ms is *between* kernels.**
Decode reads ≈1794 MB/step. At the M5 Max's 614 GB/s that is a **2.94 ms**
floor; we measure **4.144 ms**. The pool is **1.20 ms = +17.6% of score**. But
every big decode kernel we have profiled runs at **94.6–100.2% of its
achievable rate in isolation**, while the aggregate sits at ~71% of the floor.
Those two facts can only be reconciled if ~0.8–1.0 ms/step lives in dispatch
gaps, CPU encode, pass-boundary drains, and serial latency chains
(SDPA→O-proj, norm→router→top-k→gather). We have never systematically attacked
that. **The tier change is: own the timeline, not the kernels.**

⚠️ This 1.20 ms pool and §4.9's contradiction are the *same question asked
twice*. Do not spend two students on it. #174 (nezuko) is already measuring
the exposure side; ideas 2 and 4 below are the instrumentation that would
close it. Sequence them after #174 reports.

**Structural claim 2 — the prefill gather-GEMM sits at the roofline ridge by
algebraic necessity.** See the new §4.10. The 67%/67% signature is *one*
number, not two roofs. Read §4.10 before assigning any prefill gather work.

**Red herrings, named and killed:**
- 552.1 MB routed-expert decode traffic = 8/256 × 16.45 GiB **exactly** ⇒
  decode already reads only live experts. There is no dead-expert traffic to
  remove. Do not re-propose expert-traffic pruning.
- The 45% attention read (807.7 MB) has **no byte lever** inside our precision
  rules (§0a row 9 arithmetic). Its only levers are dispatch count and stream
  structure.
- Sliding-window incremental softmax is **not bit-exact** — window membership
  changes every step. And KV is only 4.7% of the read anyway.

#### The eight ranked ideas

Each carries: mechanism / why §8 does not already close it / magnitude /
**cheapest falsifier** / risk. Magnitudes use the §2 elasticities
(decode −1 µs = +0.01464%; prefill −1 ms = +0.362%).

**1. Fuse the per-layer serial epilogue chain — ≈290 µs ⇒ +4.3%.**
Residual-add + RMSNorm + router matvec (2048×256) + top-8 selection in one
kernel (≈5 KB threadgroup, well under the 32 KB limit — this is *not* the
74 KB H5 case that closed). Gate-softplus becomes an epilogue of the
O-projection GEMV. Not closed by §8: the closed fusion work priced *traffic*
deltas; this prices a **serial latency chain** where each stage's output is
the next stage's address input.
*Falsifier:* GPU-timestamp the norm→router→top-k→softplus chain per layer.
Kill if the chain costs <3 µs/layer.
*Risk:* **top-8 tie-breaking must preserve exact accumulation and comparison
order or expert selection flips.** This is a correctness cliff, not a drift
risk — one flipped expert changes tokens.

**2. Pre-encode the whole decode step — ≈550 µs ⇒ +8.1%.**
Indirect command buffer, or a single concurrent encoder with hand-placed
narrow fences. Expert-GEMV base addresses come from a **GPU-written argument
buffer** filled by the top-k kernel, so the CPU never touches the hot loop.
Recovers ~⅔ of the 0.75–0.95 ms host/gap pool.
*Falsifier:* one Metal System Trace of one decode step, summing GPU-idle plus
encode time between kernels. Kill if <200 µs.
*Risk:* **high.** Replacing MLX's hazard tracking with manual fences can
produce intermittently wrong logits that still pass local goldens. Byte budget
is 73 KB ⇒ prototype the concurrent-encoder variant (cheap) before ICB
(expensive). Requires idea 3 as an on-ramp.

**3. Slab-merge the static GEMVs + consumption-ordered weight arena —
≈150–200 µs ⇒ +2.5%.**
Offline-concatenate Q|K|V|g_proj per layer into one slab; one GEMV with split
epilogues. Order all static-address planes in step-consumption order.
*Falsifier:* microbench fused QKVg against four dispatches, then in-situ. Kill
if in-situ Δ <30 µs.
*Risk:* **low** — per-row accumulation order is unchanged, so bit-exactness is
structural, not empirical. **This is the low-risk on-ramp to idea 2** and the
best round-25 opener for a student who has not worked the decode path.

**4. Prefill attribution audit of the unattributed ~28 ms — ≈8 ms ⇒ +2.9%.**
QKV/O projections at 512 tokens are ≈1.3 TFLOP ≈15–20 ms at θ≈0.7. If our
"attention ≈22 ms" figure is SDPA *only*, the projections are most of the
so-called unattributed pool. Note §9a already says that pool is a subtraction
residual, not a measurement — this idea is how we replace it with a real one.
*Falsifier:* one GPU trace; attribute every kernel >0.3 ms.
*Risk:* **none — information only.** Highest information per GPU-hour on the
board. ⚠️ Must run on M5 (§3a: 94.2% of M4 prefill time is kernels the M5
never runs), and **no M5 GPUPROF artifact exists yet** — see §10.

**5. Two-level lm-head screening cascade — ≈148 µs ⇒ +2.2%.**
Add an ~8–16 MB weight-derived *bound* plane read before the 134.9 MB int5
plane. At an 80% kill rate: ~45 MB versus 134.9 MB.
*Falsifier:* offline survivor fraction on fixture activations. Kill if
survivors >60%.
*Risk:* a loose bound explodes survivors on hidden prompts; argmax must remain
**provably** exact, not empirically exact. Overlaps fern's #137 surface —
sequence after #137 lands.

**6. Dequant instruction diet in the gather-GEMM family (raise θ) — ~+3%.**
Offline-recode NVFP4 so in-kernel dequant is one table lookup per byte-aligned
code pair; per-group 16-entry scale×code LUT built once per tile. θ 0.67→0.78
takes MoE 44→37.8 ms = +2.2%, plus ~+1–1.5% if the same family serves prefill
projections.
*Falsifier:* Metal GPU counters on the gather-GEMM. Kill if the buffer-load
pipe is >85% busy with ALU <50% (then pivot to wider vectorized loads).
*Risk:* the LUT must reproduce **bit-identical** products; threadgroup-memory
bank conflicts can eat the win. **This is the constructive follow-on to
tanjiro's #170 if H3 wins**, and the AGX ISA facts in §0c row "address
arithmetic" are its main support.

**7. SLC-timed weight staging under SDPA/router latency windows —
≈100 µs ⇒ +1.5%.**
Cross-kernel, per-step, *timed* staging. Distinct from the closed first-touch
prewarm (§8) and the closed in-kernel prefetch (§8) because the unit is a
scheduled window, not a kernel.
*Falsifier:* DRAM-busy counter during SDPA windows. Kill if >85% busy.
*Risk:* requires idea 2's encoder structure to exist first. **Do not assign
standalone.**

**8. Lossless entropy recode of the bf16 planes — ≈35 MB ⇒ +0.85%.**
Layer-0 MLP (100.7 MB) plus routers (40.9 MB). Per-group exponent base plus
3–4-bit offsets, branchless decode to identical bf16 bits.
*Falsifier:* offline exponent-entropy histogram. Kill if <15% reduction.
*Risk:* low, but see §0c: the measured lossless ceiling on **already-4-bit**
data is only ~1.04×, so this must stay confined to the **bf16** planes where
the ceiling is ≈1.495×.

**Frontier's closing judgement, recorded verbatim in substance:** *everyone
sweeps kernels; almost nobody owns the timeline. The decisive artifacts are
two traces — one decode step, one prefill — with a limiter/counter readout,
not another geometry sweep.* Ideas 1–3 form one coherent decode programme
worth a defensible **~+10–14%**; ideas 4 and 6 are the only theory-consistent
prefill movers.

**Advisor's sequencing for round 25:** idea 4 first (zero risk, pure
information, and it repairs §9a), then idea 3 (low risk, real gain, on-ramps
idea 2), then ideas 1 and 6 in parallel, holding 2 and 7 until 3 and 4 have
reported. Idea 5 waits on #137; idea 8 is a filler.


#### ⭐ De-risking pass (2026-08-07): three of the eight ideas are now materially different

Two source-reading agents were sent into the shipped decode path before any
round-25 assignment was written. They changed the ranking. **Read this
subsection before assigning from the list above.**

##### (a) Idea 3 is re-specified: Q/K/V are *already* one slab. The live residue is **QKV + `g_proj` in one dispatch**.

- Q, K and V are already **one fused dispatch over one concatenated bank**.
  `prepareNativeAffineQKVWeight()` (`LagunaRuntimeModel.swift:5494`)
  concatenates the q/k/v code planes and scale planes (`:5536-5537`) into
  `_nativeAffineQKV` (`:5573`, declared `:5444`); rows =
  `(heads + 2*numKeyValueHeads)*headDim` (`:4816`) = **10240 (h64) / 8192
  (h48)**, contraction K = 2048. The bank is built **once outside the timed
  loop** by `prepareFusedRuntimeWeights()` (`:11011`, `eval(fusedArrays)`
  `:11042`), called from `LagunaRuntimeWeights.swift:637`. Decode call
  `lagunaDecodeNVFP4QKVR1` `:5759-5762`; kernels
  `laguna_decode_nvfp4_qkv_h{48,64}_r1_v1` `:4692` / `_ns1` `:4708` / `_lm1`
  `:4793`; three mutually-exclusive dispatch sites `:4838`, `:4856`, `:4865`.
- **`o_proj` cannot join — REFUTED on two independent grounds.** Its bank
  `_nativeAffineOProj` (`:5450`, built `:5467` from `wo.weight`
  `[hiddenSize, nHeads*headDim]` `:5471`) has contraction dim **6144 (h48) /
  8192 (h64)**, not 2048; and its input is the post-SDPA `output`, a strict
  serial RAW on the *same layer's* QKV. Kernels `laguna_oproj_act_h{48,64}_v1`
  `:4359` / `_v1_lm1` `:4377`; gated block `:6138-6145`; NVFP4 arm `:6181-6194`.
  **Recorded as closed (§8).**
- **`g_proj` is the only remaining merge candidate, and its contraction dim
  matches.** `_nativeAffineGProj` (declared `:5459`, assigned `:5534`) is built
  by `lagunaNativeAffineGProjWeight` (`:435-448`), which **always** uses
  group-32 affine INT8 (`:441-442`) because the accepted envelope caps `g_proj`
  there (`:433-434`, `TASK.md:80-88`). Shapes (`:4342-4344`): `packedCodes
  [heads,512]`, `scales [heads,64]`, `biases [heads,64]`; original
  `[heads,2048]` (`LagunaCheckpointValidation.swift:359`). **K = 2048 — the
  same as Q/K/V.** Output width = `heads`, known at build time; kernels are
  pre-specialised per `heads ∈ {64,48}` (`:4320-4327`), output `[1,1,heads]`
  (`:4351`), grid `(heads/8)*64` (`:4349`). Call `lagunaGateSoftplus` `:5802`;
  kernel `laguna_gate_sp_h{48,64}_v1` built `:4324`, dispatched `:4347-4353`;
  flag `DARKBLOOM_AFFINE_GATE_SOFTPLUS` `:4272-4273`.
- ⇒ A single *bank* merge is barred (NVFP4 vs INT8 are different
  representations, and moving either one is an envelope violation). **A single
  *dispatch* binding both an NVFP4 plane and an INT8 plane, selected by a
  simdgroup-uniform `out_row` branch, is barred by nothing in the source.**
- ⭐ **The consumer side is already written and already validated.**
  `prepareNativeAffineQKVWeight` contains a `foldGateIntoBank` path at
  `:5510-5533` (`totalRows += nHeads`, `_nativeAffineQKVGateRows = nHeads`) and
  the consumer already slices gate rows out of the QKV output at `:5787-5790`.
  It requires `groupSize==32 && bits==8 && mode==.affine` (`:5521-5522`).
  Because the shipped default is `DARKBLOOM_NATIVE_AFFINE_NVFP4_FROM = "0"`
  (`:2856-2861`), `lagunaNativeAffineWeight` takes the NVFP4 branch on **all 40
  layers** (`:2909-2922`), so `foldGateIntoBank` is **false everywhere** and the
  gate always pays its own dispatch. **Do not delete this dead path — it is the
  reusable half of this idea.**
- ⭐ **A fourth dispatch is stranded by the same gate.** The input RMSNorm is a
  separate dispatch every layer because `lagunaFusedNormAffineQKV` requires an
  INT8 bank **and** folded gate rows (`:5733-5738`), so it never fires on the
  shipped config. **Folding the gate in is a precondition for recovering
  norm+QKV fusion too.**
- **Dispatch arithmetic.** Per layer today: (1) `decode_nvfp4_qkv_h{48,64}`
  K=2048 N=8192/10240; (2) `gate_sp_h{48,64}` K=2048 N=48/64; (3)
  `oproj_act_h{48,64}` K=6144/8192 N=2048 ⇒ **120 projection dispatches/token**.
  Merging (2) into (1) ⇒ **−40/token (−33%)**; recovering the norm fusion ⇒
  another −40. The gate's ~110 KB/layer of INT8 is **already** being read, so
  **the prize is launch/latency, not bandwidth.**
- **Price.** 40 dispatches at #158's measured 3.13–3.59 µs/dispatch ≈ **132
  µs/step ≈ 3.2% of T = 4.1436 ms ⇒ ≈ +2.0% score**; ≈ +4.0% if the norm fusion
  also lands. Precision is unchanged for both classes ⇒ envelope-compliant,
  **zero submitted bytes**.
- **Instrument.** Δ = 40 dispatches is *below* the §4.1b LAW 2 threshold of
  Δ ≥ 150 for a local M4 decode arm. The ranked M5 receipt channel resolves
  ~10 µs/step (cv 0.235%) ≫ 132 µs ⇒ **measure on M5, not on the local probe.**
- **Pre-registered caveat.** `gate_sp` is the known-shadowed calibrator
  (§4.9, E ≈ 0.1; PR #101 measured its occupancy re-geometrization at −0.04%).
  So the *kernel body* may already be free — **the prize is the seam, not the
  work.** If #174 returns E ≈ 0.1 for a 1-threadgroup sibling, this idea's
  expected value falls with it.
- **Rejected sub-option:** reverting layers to INT8 g32 so the existing
  `foldGateIntoBank` fires. It doubles Q/K/V weight traffic (0.5625 → 1.125
  B/param) and the in-repo sweep records it as monotone worse (~−0.5%/layer,
  `:2849-2854`).
- **Build pattern to copy** — `prepareFusedSharedGateUp()` (`:8248-8275`):
  idempotence guard `:8249`; exact-stock-config guard `:8250-8258`;
  dtype/shape guards `:8259-8266`; **`return []` on any decline so the caller
  silently keeps the stock path** `:8267-8268`; `concatenated(axis: 0)`
  separately for codes and scales `:8269-8270`; retain side copies + a split
  offset `:8272-8274` with the consumer slicing at `:8500-8501`; return arrays
  so the caller batches **one** `eval` `:11042`, run once from
  `prepareFusedRuntimeWeights()` `:11029` after checkpoint `update`+`eval` and
  before warmup (`LagunaRuntimeWeights.swift:631-637`). **The module tree is
  never restructured — every fused layout is a derived side copy**
  (`:11005-11010`).

**Verdict: this is the strongest round-25 opener and replaces idea 3 at the top
of the queue.**

##### (b) Idea 1 is DOWNGRADED: the epilogue chain is already fused; only a 1-threadgroup sibling remains

- `DARKBLOOM_FUSED_RESIDUAL_RMS_ROUTER` (flag `:531-533`, default ON) already
  computes **all four** of: the residual+branch BF16 add (`:940-949`), the
  2048-wide FP32 RMS reduction and weight scale (`:953-963`), the full
  `[256,2048]` BF16 router mat-vec with one FP32 accumulator per expert row
  (`:966-978`, body `:875-900`), and — because `DARKBLOOM_ROUTER_PRECOMPUTED_KEYS`
  also defaults ON (`:171-172`) — the per-expert sigmoid score plus
  `correction_bias` plus a monotone sortable `uint` ordinal, emitted as a 4th
  output `router_keys[256]` (`:861-869`, helper `laguna_router_key_ordinal`
  `:8749`). Kernel `laguna_residual_rms_router_bf16_2048_rpg8_keys_v1` built
  `:993-1010`, **one** dispatch, grid `tiles*512 = 32*512` (`:1086-1094`),
  call-site guard `:10351-10369`. It does **not** do top-8 selection.
- Top-8 happens in two places, both real. (i) A **separate selector dispatch**
  per sparse layer: `gate(x, logits:)` `:10004` → `lagunaDecodeRouterTop8`
  (`:9527-9538`, impl `:8881-8899`), kernel
  `laguna_decode_router_top8_ordinal_table_(norm_)v1` (`:8792-8807`), grid/TG
  **(256,256) = 1 threadgroup, 256 threads** (`:8872-8877`); the cast sink
  `:8911` and the top-k renorm sink `:8918` are already folded in (both default
  ON, `normTopkProb` default true, `LagunaConfig.swift:446`) ⇒ **no extra cast,
  sum or divide dispatch exists.** (ii) Top-8 is *also* folded into the routed
  gate/up GEMV: `laguna_routed_nvfp4_swiglu_qmv_packed_top8keys_r1_bf16_v2`
  (`:7541`) runs the shuffle-only comparator prelude
  `lagunaRouterTop8PrecomputedPrelude` (`:7504-7516`, helper `:7475-7502`), so
  each threadgroup re-extracts only its own `expert_slot` winner from
  `router_keys` and **never waits on the selector** (`:7566`). Dispatch
  `:10046-10062`, wrapper `:7655-7690`.
- ⇒ **Only two distinct dispatches exist between the end of `o_proj` and the
  start of the routed gate/up GEMV.** Nothing else: `eScoreCorrectionBias` is
  already F32 (`LagunaCheckpointValidation.swift:462`) so the `asType(.float32)`
  at `:9537` is a no-op; the shared-expert gate/up is issued **after** routed
  inside `fusedSharedDownInputs` (`:10105`); and `mergedSharedActivated` is
  declared but **never assigned** (`:10030`, `:10105`) ⇒ no merged
  routed+shared gate/up dispatch exists today.
- ⭐ **The selector is a sibling branch, not on the critical path.** Dispatch 1
  → routed gate/up GEMV is a true RAW (the GEMV reads both `normalized` and
  `router_keys`, `:10056-10061`, preconditions `:7661-7667`), and dispatch 1 →
  dispatch 2 is a true RAW. But **dispatch 2 → routed gate/up GEMV is not a
  dependency** — the GEMV takes `routerKeys`, not `inds`; every use of `inds`
  before it is shape/dtype metadata only (`:10009`, `:10052-10057`). The
  selector is on the critical path only to `lagunaRoutedSharedDownResidual` /
  `lagunaRoutedDownReduce` (`:10112-10113`, `:10125-10130`). The shared-expert
  branch is likewise documented as independent of the router top-8 (`:274-276`).
- At **1 threadgroup**, far below the ~480-TG residency ceiling (§4.1), that
  sibling should overlap essentially perfectly. **The residue of idea 1 is 39
  dispatch seams ≈ 129 µs ≈ +1.9%, and only if a 1-TG sibling actually costs
  its seam — which is exactly what PR #174 arm A1 is measuring. Sequence idea 1
  strictly after #174 reports.** Folding top-8 *into* `residual_rms_router`
  would need a cross-threadgroup reduction over its 32 threadgroups (a global
  sync), so it is not a one-kernel change.
- For the record, the already-shipped decode fusion flags (all default ON,
  `!= "0"`): `DARKBLOOM_FUSED_ROUTED_SWIGLU_QMV` `:149-150`,
  `DARKBLOOM_FUSED_SHARED_SWIGLU_QMV` `:127-129`,
  `DARKBLOOM_FUSED_ROUTED_SHARED_DOWN_RESIDUAL` `:141-145` (8 routed downs +
  shared down + router-weight reduction + routed scale + both BF16 residual
  adds in one **288-thread** dispatch), plus the two retiles
  `DARKBLOOM_ROUTED_GATEUP_R1` `:7529-7538` and `DARKBLOOM_QMV_R1` `:269-271`,
  and `DARKBLOOM_PACKED_SCALES` `:152-166`.
  **Idea 1 was priced against a chain that no longer exists. Its +4.3% estimate
  is withdrawn.**

##### (c) `mx::set_wired_limit()` is CLOSED — we already call it, but only on the M5

`LagunaRuntimeWeights.swift:546-598` `wireResidentWeightsIfEnabled()` computes
`target = 1.0 × Memory.activeMemory + 64 MiB` (≈31.4 GiB, constants
`:541-542`), clamps to `GPU.maxRecommendedWorkingSetBytes() − 256 MiB`
(`:571-573`) and applies it through `WiredMemoryTicket(...).start()`
(`:575-590`) → `mlx_set_wired_limit` (`Vendor/mlx-swift/Source/MLX/WiredMemory.swift:28`).
It is invoked once from construction (`:460-462`) under `DARKBLOOM_WIRED_ZH !=
"0"` (default ON) **and `physicalMemory >= 96 GiB` (`:547-548`)**, logging
`mlxfast: wired-zh ...` to stderr (`:592-598`). `MLX_WIRED_LIMIT` is not
present; `setShouldMaximizeConcurrentCompilation` is not called anywhere
(headers only). **The Open-TQ-Metal `set_wired_limit` lead from §0c.7 is
therefore already harvested — recorded in §8.**

⚠️ **Doctrine caveat this creates.** "The steady decode step is host-independent
for kernel selection" now needs an asterisk: **the ranked M5 runs with its
weights wired-resident and the 48 GiB M4 student hosts never trip that gate.**
Kernel *selection* is still identical, and the organizer states the <64 GiB
profile "changes allocator management, not ranked code paths", so this is a
caveat rather than a crisis — but any M4 decode result whose mechanism is
residency, page faulting, or first-touch behaviour is **not** transferable.

##### (d) Idea 4 is INFEASIBLE as written; its only available form is already PR #148

The prefill attribution audit was specified as a Metal System Trace of one
prefill on the ranked machine. **Students have no M5 shell; the M5 is reachable
only through `mlxfast submit`, which returns `officialMetrics` and no GPU
trace.** No M5 GPUPROF artifact exists anywhere in the repo, and none can be
produced. The only executable form of idea 4 is **calibrated work injection
read back through the ranked receipt channel** — which is precisely the
experiment maple-frieren is already running in PR #148. **Do not assign a
second student to idea 4.** The advisor sequencing note above ("idea 4 first")
is superseded.

#### ⭐⭐ Second de-risking pass (2026-08-07): idea 2 and idea 3 are both DEAD

Two more source-reading agents were sent in before any round-25 assignment was
written — one auditing idea 2's reachability, one auditing the re-specified
idea 3's design. **Both ideas died.** More importantly, the second audit
falsified the *pricing model* that generated ideas 1, 2 and 3 alike. Read (e),
(f) and especially (g) before proposing anything priced in dispatches.

##### (e) Idea 2 is DEAD as written — decode pre-encoding is structurally unreachable

The editable surface has been enumerated exactly. `benchmark.json`'s 97
entries expand to: `Sources/MLXFastModel` (whole dir), `Sources/MLXFastTransform`
(whole dir), 15 × `Vendor/mlx-swift-lm/`, 80 × `Vendor/mlx-swift/`. Of those
80, **76 are kernel sources and only 4 are dispatch/host machinery**:

| bytes | path | role |
|---|---|---|
| 88,309 | `Vendor/…/backend/metal/matmul.cpp` | encode site (GEMM/GEMV) |
| 83,954 | `Vendor/…/backend/metal/quantized.cpp` | encode site (NVFP4 QMM, MoE gather-GEMM) |
| 50,368 | `Vendor/…/backend/metal/jit_kernels.cpp` | pipeline/JIT build |
| 9,697 | `Vendor/…/backend/metal/kernels.h` | kernel decls |

**Not editable:** `metal/device.cpp`, `metal/device.h`, `metal/eval.cpp`,
`mlx/transforms.cpp`, `mlx/utils.h`, and ⭐ **all of
`Vendor/mlx-swift/Source/MLX/*.swift`**.

- **The hard blocker is `device.h:104-105`.** `MTL::ComputeCommandEncoder*
  get_command_encoder()` is **private**, and `device.h`/`device.cpp` are not
  editable. So `memoryBarrier(scope:)`, `useResource`, ICB encoding and custom
  fences are all **structurally out of reach**. There is no
  `MTLIndirectCommandBuffer` use anywhere reachable (only unused non-editable
  metal-cpp bindings), and `Sources/MLXFastModel/` contains no `import Metal`.
- **Command-buffer lifetime is decided entirely in non-editable code.**
  `needs_commit()` = `buffer_ops_ > max_ops || (buffer_sizes_>>20) > max_mb`
  (`device.cpp:484-487`); family defaults 40/50 (`:576-593`); env override
  (`:596-597` → `mlx/utils.h:178-188`); the actual end/commit is
  `eval.cpp:59-63` and `:73-77` (`gpu::finalize`), called from
  `transforms.cpp:276` and `:315`. One encoder per CB, opened
  `MTL::DispatchTypeConcurrent` (`device.cpp:548`).
- ⭐ **"Fewer CBs" is already measured and has the WRONG SIGN.** The 66-run
  two-Latin-square decode-ladder sweep (`LagunaRuntimeModel.swift:660-676`,
  §7's placement table): `off` (one flush/step) **10.3735 ms**; `ladder8`
  **9.4533 ms**; `at:1,7,15,23,31,39` ≈ **9.29 ms**. Collapsing toward one
  command buffer is **~10–11% slower** — MLX's graph build runs on the CPU and
  the GPU idles until a flush. **The prize is *more, earlier* flushes, not
  fewer.** Idea 2's whole framing was backwards.
- ⭐ **Multi-stream is completely unexploited and IS reachable.** MLX creates
  one `MTLCommandQueue` per stream (`device.cpp:284`), keys encoders per stream
  index (`eval.cpp:22-27`) and holds per-stream fences
  (`transforms.cpp:285-292`). We cannot edit that machinery, but the `stream:`
  *argument* is fully ours — and `Sources/MLXFastModel/*.swift` currently
  passes **no explicit `stream:` anywhere**.

**Replacement leads (these inherit idea 2's slot, at much lower stated
magnitude and much higher confidence):**

- **(L1) Multi-stream decode.** #157 §4c at production width (`alu/mem`,
  tg=9792) measured `two_queue` **0.1268** vs `two_cb` **0.0546** vs
  `concurrent_1cb` **0.0120** — multi-queue overlaps ~2.3× better than two CBs
  and ~10× better than one concurrent CB. Now confirmed reachable. Natural
  first movers off the main stream: the **1-threadgroup top-8 selector**
  (§(b)), `gate_sp`, or lm-head screening.
- **(L2) Encode-site `start_concurrent()` / `barrier()` and barrier pruning.**
  `CommandEncoder::start_concurrent()`/`barrier()` are public
  (`device.h:88-90, :93, :97`) and callable from the editable `quantized.cpp`
  (`get_command_encoder(s)` at `:221, :284, :316`) and `matmul.cpp`, overriding
  the auto-barrier logic at `device.cpp:324-325, 347-348, 363-371`. In-tree
  precedent: `DARKBLOOM_STAGE_RUNBAR` at `quantized.cpp:1290` already dropped
  two provably dead per-run barriers.
- **(L3) "More, earlier flushes."** A finer search around earlier first-flush
  placement in the decode async ladder (`LagunaRuntimeModel.swift:678-708`, env
  `DARKBLOOM_DECODE_ASYNC_STAGE`, default `at:0,1,7,15,23,31,39`; prefill twin
  `:730-740`). Note the lone-fire-at-layer-1 row scores **0.9476** (worse), so
  this is a placement-and-density surface, not a monotone dial.

##### (f) Idea 3 is DEAD — the QKV + `g_proj` merge was already built and measured on the ranked M5

**PR #48 (`research/maple-fern-pr48-fused-norm-qkv-gate.md`, 65,364 B,
`assignment_id maple-2026-08-05d-fused-norm-qkv-gate`) built exactly this
kernel and measured it on the ranked M5 at −0.1488% on `ns`.**

- Its **mode 2** = RMSNorm fold + **gate ride-along**, −80 decode dispatches
  (406 → 326, exactly as the merge predicts). Its **mode 1** = norm fold only,
  −40. Dispatch census confirms the per-layer NVFP4 tail anatomy: **1 norm +
  1 QKV + 1 gate = 3, collapsing to 1**.
- The ride-along map already exists **in the "gate tiles first" form** —
  `if (tile < gate_tiles && simd_group < 2) { … }`, `gate_tiles = heads/8`,
  Swift-side guard `heads/8 <= rows/16`; zero extra threadgroups, zero extra
  norm recomputation. The *trailing*-tile form was measured **+1.6% slower on
  M4** (one threadgroup streams the whole 128 KB INT8 gate bank on a single
  core while the other 640 retire ⇒ the gate becomes the kernel's tail).
- ⭐ **The receipt.** Ticket **`285f79fa-089f-4184-b1ec-0647cb51e61b`**, created
  2026-08-05T19:00:49Z, commit `3234ece1e2f2c43cf25bfa981f9c75a702564917`,
  submitted `--model senpai`, `status rejected`, `officialScore
  2.50450520378964`.
  **Correctness fully green**: `passed_correctness True`, `max_abs_diff 0`,
  `checked_steps 1344`, `case_count 11`, all `first_failing_*` null,
  `gpqa_ttft_passed True` 9/9, `semantic_gpqa_passed True` 9/9,
  `peak_ram_gb 21`.
  **Timing**: `nd` 2.745476 vs control 2.754322; `npf` 2.013145 (shared);
  **`ns` 2.540575 vs control `c3ce66ec` 2.544360 ⇒ Δ = −0.1488%.**
- ⭐ **The pre-registration is what matters.** PR #48 registered *Reading A*
  (dispatch-count × µs/dispatch: 80 × 2.1828 µs ⇒ **+2.595%**) against
  *Reading B* (**+0.44%**) with a **10.2 σ** separation. The M5 came in at
  **−0.15%**, below even Reading B. **Reading A was refuted outright.**
- The mechanical merge is *trivial* and that is precisely the point: both
  kernels are TG `(64,1,1)` = 2 simdgroups × 32 lanes, all-register, `simd_sum`
  reduction, reading the same `normalized` buffer; merged buffer count is
  8 in + 2 out = 10, far under the 31 limit; TG memory stays 0 B. There is
  in-file precedent (`laguna_fused_norm_qkv_projection_bf16_h{48,64}_v3`,
  `LagunaRuntimeModel.swift:3239-3308`, dispatch `:3372-3387`). **Ease of
  implementation was never the constraint; the mechanism simply is not worth
  anything.**
- **The one genuinely untested cell** is a *dispatch-only* gate merge (no norm
  fold) at the shipped `num_simdgroups=2` geometry with gate tiles scheduled
  first — PR #48's mode 2 bundled the norm fold and its
  `QKV_R1_SIMDGROUPS=16` re-tiling, so the gate fold was never isolated on M5.
  Expect **sub-0.5%**, and the barrier census says the deleted dispatches are
  the cheap ones (the norm fold removes 39 barriers; **the gate fold deletes
  exactly 1 of 40**). Frame it only as a narrow pre-registered discriminator,
  never as an unexplored win.
- If it is ever revisited, the three bit-exactness risks are: (1) `R`/`NS` are
  free work-assignment but **`V=8` and `BK=256` are NOT** — they fix which 8
  products enter each lane and the `simd_sum` tree; (2) FP re-association /
  FMA contraction ⇒ the gate body must be emitted as **byte-identical MSL**
  (PR #48's `lagunaGateSoftplusBody(orow:input:)` extraction is the safe
  pattern); (3) keep the device-side bf16 `normalized` input boundary and the
  softplus `float(bfloat(r))` round-trip and NaN branch verbatim.
- ⚠️ **Oracle caveat, recorded from PR #48 §9.4/§9.7:** forcing `FUSE=0` gave a
  **byte-identical** fusion-site list and per-step errors to `FUSE=2`, i.e. the
  upstream-equivalence oracle **cannot distinguish the modes at all**. The
  defensible claim from it is "no gross always-on corruption", never
  "bit-exact". Demand a **positive reachability trace** for any custom kernel.

##### (g) ⭐⭐ The synthesis: dispatch COUNT is not the currency; dispatch OVERLAP is

Three independent results are jointly consistent under exactly one reading:

| result | observation |
|---|---|
| **PR #48, ranked M5** | −80 decode dispatches ⇒ **−0.15%** (nothing) |
| **PR #101, M4** | forcing `DispatchTypeSerial` ⇒ **+0.456 ms/step, +5.49%** |
| **PR #158, M4** | `gpu_busy_sum` **flat at 7.99 ± 0.06 ms** across 45 → 204 CBs |

**The machine already overlaps well.** *Removing* a dispatch removes something
that was already hidden; *breaking* the overlap is expensive. This also
retroactively explains the §4.1a busy-vs-wall divergence (`rsdr`: busy −71.5 µs
but wall **+20.5 µs**).

**Consequences, and they are programme-wide:**

1. **Headroom lies in increasing overlap beyond MLX's conservative
   auto-barriers ((L2)) or adding a second queue ((L1)) — not in fusing or
   merging kernels.** Every remaining "fuse N dispatches" proposal is now
   presumed worthless until it clears the PR #48 refutation.
2. **Idea 1's residue (≈ +1.9%) is priced by the same refuted model** and is
   now suspect on the same evidence. **#174 arm A1's exposure factors are the
   decisive test, and its importance rises sharply.**
3. **The surviving ideas are the non-dispatch-count ones:** idea 5 (lm-head
   cascade — *byte*-based), idea 6 (dequant instruction diet / raise θ —
   *work*-based, prefill), idea 8 (entropy recode of the bf16 planes —
   *byte*-based), plus (L1)/(L2)/(L3) above.
4. **Doctrine change (added to §3):** *do not price a decode fusion by removed
   dispatch count at all.* Price it by traffic delta, by exposure factor
   E = ΔS/ΔI measured on the actual kernel, or not at all.

##### Revised round-25 sequencing (v3, supersedes v2 — rewritten after #174)

#174 landed and moved almost every entry. The dispatch-count question it was
sequenced to adjudicate is now **answered and closed** (§4.12): decode
concurrency is real, already harvested, and worth ~448 µs/step that we are
already collecting. That kills the whole "buy more overlap" branch and
promotes a target nobody was working on.

1. ⛔ **T1 — decode attention occupancy — LANDED AND REFUTED.** PR #196
   (nezuko, `maple-2026-08-07a-decode-attention-occupancy`) merged with a
   complete negative and **zero submitted bytes**. The 564 µs/step / +8.26%
   figure survives only as a *bytes-based ceiling*; #196 proves the
   occupancy-tail mechanism that was supposed to reach it **does not exist**
   (32 and 24 TGs both fit inside one M5 wave) and that splitting costs
   1.144×/1.704×/2.185× at S=2/5/10 even when wave-matched. See §4.12.8 (C),
   (F) and the three new §8 closures. **The best possible outcome from a
   negative: it killed a family, a pricing model, and a gating unknown in one
   pass, and left a measured successor target behind (§4.12.8 G).**
2. ⭐⭐ **T3 candidate 2 — fuse or DELETE `decode_router_top8_ordinal_table_norm`**
   (#174 §5.3). **Now the single largest priced decode target left**:
   185.7 µs/step ≈ **+2.72%**, reads no new bytes, and the selector sorts
   1.03 kB at an implied 0.2 GB/s. Two facts sharpen it since #174:
   (a) the kernel is a **full 256-element bitonic sort in ONE threadgroup of
   256 threads** — 36 compare-exchange rounds, 12 `threadgroup_barrier`s,
   ~2.5% of one core, and by #196's staircase a 1-TG dispatch costs the same
   wall time as a 40-TG one, so essentially all 4.70 µs/call is fixed cost on
   the serial critical path; and (b) on the shipped decode path its
   `router_indices` output is **dead** — the routed GEMV consumes `router_keys`
   and recomputes its own top-8 — so the dispatch survives solely to produce
   **8 normalized fp32 scores**. That admits a *deletion* arm, not just a
   fusion arm. Price it with #196's `T = a + W·φ + work`, **not** with
   removed-dispatch-count × µs/dispatch (§4.12.3).
   The other two glue fusions (`rmsbfloat16` into its consumer prologue;
   residual epilogues into producing matvecs) are **separate small
   experiments**, not one bundle.
2b. ⭐ **The attention merge epilogue** (§4.12.8 G, #196 §7.1) — the successor
   #196 measured but did not attack. 1.068/1.072/1.170 µs for N=64/256/512,
   **constant in N**, = 12.9% of a 512-row call, ceiling **+0.685%** score,
   realistic ~+0.21%. It is *intra*-threadgroup, so §4.12.8 (E)'s inter-TG
   merge hazards do not apply. Natural next assignment for nezuko, who already
   instrumented it.
3. **#170 reports** → if H3 (schedule+latency-limited) wins, idea 6 (dequant
   instruction diet, θ 0.67 → 0.78, ~+3%) becomes the constructive follow-on.
4. ✅ **#137 r3 (the anchoring receipt) — LANDED.** Receipt `08ddee45` read
   ROW A at −0.66σ: the frontier survived the six unvalidated merges, so
   §4.11.5 is resolved and the standing "no more than ~2 merges without an
   anchor" rule is now a *scheduling* obligation rather than an open risk. It
   also convicted the row-major refine arm, which removes idea 5's second arm.
   **PR #137 merged at r4 as `ee914666`** (r4 was a mechanical conflict fix
   only; the scored tree is identical to r3).
5. **#148 reports** → is idea 4, in its only available form. T2 (routed-MoE
   matvec bandwidth, 188 µs/step, +2.75%, a *soft* ceiling) is fenced to it.
6. **(L2) Encode-site barrier pruning / `start_concurrent()`** in the editable
   `quantized.cpp` / `matmul.cpp` — demoted to filler. #174 shows the encoder
   already delivers the overlap and only three small hazard-free kernels hide.

**Demoted or dead after #174:**

- **(L1) multi-stream decode** — demoted from first place. The concurrent
  encoder already delivers ~448 µs/step of real intra-CB overlap; only
  small kernels (`gate_sp_h64`, `gate_sp_h48`,
  `shared_nvfp4_swiglu_qmv_rows1`, E ≈ 0.10) have anything left to hide. A
  second queue would be buying a good we already own.
- **(L3) "more, earlier flushes"** — **dead**. #174 §6 measures the shipped
  45-CB split as already sitting at the host-gap minimum.
- **Ideas 2 and 3** remain closed (§8); idea 7 has lost its prerequisite;
  idea 8 is byte-based and therefore under §4.11.3 transfer doubt.


---

## 8. Closed families — do not repeat, but reopening is allowed

**Closure here is provisional** (`eae07f01`, §0a row 7). A closed family
"starts with low expected value"; it is reopened by a proposal that
**identifies a new mechanism or new evidence**, and is *not* reopened by
re-running the same arm or by hoping for a different draw. Read each row for
*what was falsified*, then ask whether your proposal actually attacks that.

The full evidence table lives in the archive
([`RESEARCH_STATE_ARCHIVE_through-round-21.md`](RESEARCH_STATE_ARCHIVE_through-round-21.md),
"Closed families"). Consult it before proposing anything below. Summary index:

**Closed in round 28 (2026-08-07):**

- **`_nax` load-amortization — CLOSED (#244).** Hoisting/amortizing scale loads in
  the `_nax` inner loop produced a clean negative. Together with #215 this is the
  **second independent refutation that the `_nax` inner loop is device-load-bound**.
  The whole "feed the `_nax` loop faster" family is closed. Note the surviving
  *sibling* hypothesis is **ALU-issue**, not load: tanjiro's `win_ok` ctor-hoist is
  untouched by this closure.
- **`MLX_MAX_OPS_PER_BUFFER` / `MLX_MAX_MB_PER_BUFFER` tuning — CLOSED (#241).**
  Clean null, 0.00 ± 0.02 ms across the swept range.
- **The command-buffer *size-clause* hypothesis — REFUTED (#241).** The size
  accumulator counts only **unique inputs** (`device.cpp:320`), so the clause cannot
  fire the way the hypothesis required.
- **Work-elasticity `E` as a fusion-selection criterion — REFUTED (#241).** Injected
  dispatch cost is **flat** across sites: a site with E = −0.045 pays 1.416 µs versus
  1.295 µs at the most exposed site. Select on **raw dispatch count** instead.
- **H13/H2, "serial idle at low-slack consumers" — REFUTED (#241)** by the same
  flatness result.
- **Per-dispatch GPU timestamps via `MTLCounterSampleBuffer` — UNSUPPORTED.**
  `atDispatchBoundary: false` on this stack. Use `MTLCommandBuffer.GPUStartTime` /
  `GPUEndTime` and `kernelStartTime` / `kernelEndTime`, which are supported on all
  devices. (`atStageBoundary` is still unprobed.)
- **Per-resource `memoryBarrier(resources:count:)` — BLOCKED, not refuted.**
  `Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/device.cpp` and `device.h` are
  **not in `editablePaths`**, so this cannot ship. Research-instrument only.

**Closed in earlier sessions:**

- **⭐⭐ The lm-head row-major sparse-refine arm
  (`DARKBLOOM_LMHEAD_ROWMAJOR_REFINE`) — CLOSED as a twice-measured M5
  negative (§4.11.5, §4.11.6).** r2 shipped it ON and cost −0.369%; r3 is the
  *identical tree* with the default flipped OFF and recovers **+0.2237% of
  `ns` (+1.01σ) and −16.59 µs/token**. Two independent ranked receipts, one
  controlled comparison, same sign. The flag and its kernel move to the
  cleanup list; do not propose a third geometry of it without a new
  mechanism (§0a row 7).
- **⭐ The "~35 minutes per ranked receipt" planning constant — RETIRED.**
  #137 r3's fully instrumented dispatch→verdict cycle was **43 min 55 s**
  (19.6 min blocked behind another campaign, 20.8 min validating). Budget
  ~45 min per receipt, and treat queue contention as a first-class cost when
  sequencing anchors (§4.11.6c).
- **⭐⭐ Attention head-axis repartition (one query head per threadgroup) —
  CLOSED by integer-wave arithmetic *and* by a byte argument (§4.12.8 D).**
  Splitting the head pair doubles the grid (32 → 64 sliding, 24 → 48 full) but
  64/80 = 80% and 48/60 = 80% are **exactly the shipped efficiencies** on both
  20 and 40 cores, so the quantization gain is zero; and the two heads in a
  pair share the staged `tg_k`/`tg_v` planes (`kv_head = head0 / gqa`), so the
  split **doubles K/V read traffic**. It is null-to-negative on both axes.
- **⭐⭐⭐ The decode-attention KV-split-across-threadgroups family, at EVERY
  S — CLOSED by PR #196 (§4.12.8 C).** #174 §5.1 proposed S=2; I then proposed
  S=5 on a relative-makespan model. **Both are refuted, and so is the model.**
  Two independent grounds, either one sufficient:
  (i) **There is no tail to recover.** The shipped grids are 32 TGs (sliding)
  and 24 TGs (full) against C = 40 M5 cores at 3 threadgroups/core residency.
  `N ≤ C` at S = 1 ⇒ one wave ⇒ the "occupancy tail" the whole family was
  built to reclaim **does not exist on the ranked host**. This is arithmetic
  over runtime constants, so it transfers to M5 from an M4 measurement.
  (ii) **Splitting costs strictly more even when it is wave-free.** Direct
  wave-matched measurement at C = 40 (#196 §5): S=1 9.078 µs, S=2 10.384
  (1.144×), S=5 15.468 (**1.704×**), S=10 19.832 (2.185×). The fixed cost per
  threadgroup is `f = 3.130 µs` — **34.3% of a full 512-row call** — so every
  extra shard re-pays a third of the kernel for a fraction of the work.
  The replacement pricing model is `T = a + W·φ + work` with
  `a = 1.661 µs`, `φ = 1.469 µs/wave`, `W = ceil(N / (3C))`. **Never price a
  decode geometry with a relative-makespan ratio again**; idle slots below the
  residency ceiling cost exactly zero.
- **⭐⭐ Shrinking attention threadgroup memory to buy residency — CLOSED
  (#196 §7.3, §4.12.8 F).** The rendezvous probe holds occupancy flat at
  3 threadgroups/core across tgmem 16 B → 32768 B. Both attention kernels
  already declare 18432 B of a 32768 B budget and are nowhere near the
  limiter. Any proposal that spends effort compressing `outputs[]`,
  `max_scores[]`, `sum_exp_scores[]`, or the staging planes **in order to
  raise occupancy** buys zero and should be rejected on sight. (Compressing
  them to reduce *work* is a different, still-open argument.)
- **⭐⭐ "Idle slots below C cost time" as a pricing model — CLOSED.** The
  unit-resolution staircase (#196 §2, both kernels, K = 1…3C) is **flat to
  within ±0.06 µs from K = 1 to K = 20**, then steps +6.48 µs at K = 21 and
  +6.44 µs at K = 41 — a 100× discontinuity at the wave boundary and nothing
  in between. A dispatch of 1 threadgroup and a dispatch of C threadgroups
  take the *same wall time*. Every argument of the form "only 32 of 40 cores
  are busy, so we are leaving 20% on the table" is therefore **invalid**; the
  only quantity that costs time is the integer wave count `W`. Note also that
  the marginal wave costs `b = 7.408 µs` against a lone-TG latency of
  8.891 µs — co-residency recovers only ~17% of a wave, so these kernels are
  **issue/ALU-bound, not latency-hiding-bound**.
- **⭐⭐⭐ Decode intra-CB concurrency, per-CB overhead, and the three shadowed
  kernels — CLOSED by PR #174 (§4.12).** The overlap is real (382–448 µs/step)
  and MLX's concurrent encoder **already harvests all of it**; there is nothing
  left to win by changing dispatch type, dispatch granularity, CB count, or the
  CB split, and the shipped 45-CB split is already at the wall-minus-busy gap
  minimum. Per-CB overhead is 45 × 0.540 µs = **24 µs/step in total**.
  `gate_sp_h64`, `gate_sp_h48`, and `shared_nvfp4_swiglu_qmv_rows1` sit at
  exposure **E = 0.10 [0.00, 0.25]** — they hide inside 35–43 µs/call matvecs
  and are worth approximately nothing. This also closes **constant
  per-dispatch census corrections**: the correction is not a constant, it is a
  per-family exposure factor that must be measured.
- **⭐⭐⭐ The weight-streaming pool as a target — CLOSED (§4.12.5).** The top
  four census entries are 57% of the decode step and run at 89–98% of the M4
  Pro DRAM roofline; their combined remaining headroom is 338 µs/step and
  capturing it would require literally 100% of peak. **Census rank is not
  headroom rank.** Attention (10.4% of the step, 564 µs/step of headroom) and
  the glue pool (7.6%, 489 µs/step) are where the decode headroom actually is.
- **⭐⭐ The dense bf16 MLP → NVFP4 conversion — CLOSED by the precision
  envelope, not by measurement (§4.12.7).** `dense_gate_up_swiglu` and
  `dense_down_residual` move 101 MB / 409 µs per step; NVFP4 would be
  28 MB / ~104 µs, a **306 µs/step ≈ 4.48% score** prize. The accepted
  envelope permits only group-32 affine INT8 for Q/K/V/O and per-head
  `g_proj`. Recorded explicitly so nobody re-derives the prize and proposes it
  again.
- **⭐ The lm-head row-major sparse-refine arm — CLOSED on a ranked receipt.**
  PR #137's `laguna_lmhead_exact_fused_int5_sparse_refine_rowmajor_v1` cut the
  S4 stage from 77.4 to 13.7 µs on M4 and moved the local decode probe −112.5
  µs/step with a bit-identical logit digest, then measured **`ns` 2.58861777 =
  −0.369%** on the ranked M5 (receipt `99b71258-abdd-4cce-bbe8-3e75161032e0`).
  It will not ship default-ON.
- **⭐⭐ M4 decode wins whose mechanism is *bandwidth reduction* — CLOSED as a
  transferable class (§4.11.3).** PR #137 is the measured instance: a −63.7
  µs/step M4 prediction landed at **+24.6 µs/step on M5**, transfer factor
  **−0.40 ± 0.24**, with the honest 0.50–0.75 band excluded at ≥3.8σ. M5
  decode is instruction-bound at ~89% utilization; M4 Pro is bandwidth-bound.
  A byte-removal decode result is now presumptively non-transferable and may
  not be promoted on M4 evidence alone. Instruction- and latency-mechanism
  results remain the privileged class.
- **⭐⭐ The QKV + `g_proj` single-dispatch merge — CLOSED, because it was
  already built and measured on the ranked M5.** PR #48
  (`research/maple-fern-pr48-fused-norm-qkv-gate.md`) shipped a three-mode
  kernel whose mode 2 folds the input RMSNorm *and* the per-head `g_proj` +
  softplus into the fused QKV dispatch, removing **exactly 80 decode
  dispatches** (406 → 326). Receipt
  **`285f79fa-089f-4184-b1ec-0647cb51e61b`** (commit `3234ece1`, measured
  2026-08-05T19:12:03Z) came back **fully correct** — `max_abs_diff 0`,
  `checked_steps 1344`, `case_count 11`, GPQA TTFT 9/9, semantic GPQA 9/9,
  both floors clear — and **`ns` 2.540575 against a same-session control
  `c3ce66ec` at 2.544360 ⇒ Δ = −0.1488%**. Both component speedups were
  marginally *worse*. The PR pre-registered Reading A (80 × 2.1828 µs ⇒
  **+2.595%**) against Reading B (+0.44%) with a **10.2 σ** separation; the
  measurement landed below both. **Reading A is refuted outright.** The one
  cell never tested is a *dispatch-only* gate merge (no norm fold) at
  `num_simdgroups=2`; expect sub-0.5%, because the barrier census shows the
  gate fold deletes only **1 of 40** barriers — the 40 dispatches it buys are
  the cheap ones. Reopen only as a narrow pre-registered discriminator, never
  as a headline win.
- **⭐⭐ Pricing a decode fusion by (dispatches removed) × (µs/dispatch) —
  CLOSED as a predictive model.** The same receipt is a direct falsification:
  −80 dispatches bought −0.15%. The µs/dispatch constants in §4.1a were
  measured in **`gpu_busy_sum` currency on M4** and do **not** convert to M5
  wall time. Do not price a decode fusion by removed dispatch count at all
  without new evidence. See §7's second de-risking subsection (g) for the
  replacement doctrine: **dispatch COUNT is not the currency; dispatch OVERLAP
  is.**
- **Decode-step pre-encoding (ICB, or one hand-fenced encoder for the whole
  step) — CLOSED, structurally unreachable.** Command-buffer lifetime is
  decided entirely in non-editable code (`metal/device.cpp:484-487`,
  `:576-593`; `metal/eval.cpp:59-63`, `:73-77`), and
  **`metal/device.h:104-105` makes `get_command_encoder()` private** inside a
  non-editable header, so `memoryBarrier(scope:)`, `useResource`, ICB
  encoding and custom fences are all out of reach. Only 4 of the 80 editable
  `Vendor/mlx-swift/` entries are dispatch/host files (`matmul.cpp`,
  `quantized.cpp`, `jit_kernels.cpp`, `kernels.h`); every
  `Vendor/mlx-swift/Source/MLX/*.swift` is **not** editable. See §7
  subsection (e) for the three replacement leads (multi-stream decode,
  encode-site `start_concurrent()`/barrier pruning, more-and-earlier flushes).
- **Reducing the decode command-buffer count — CLOSED, measured ~10% WORSE.**
  The 66-run two-Latin-square asyncEval-ladder sweep in
  `LagunaRuntimeModel.swift:660-676` puts `off` (fewest flushes) at **10.3735
  ms**, `ladder8` at **9.4533 ms**, and `at:1,7,15,23,31,39` at ≈**9.29 ms**.
  Collapsing toward one command buffer is **~10–11% slower**. The prize, if
  any, is in *more, earlier* flushes — and even that is a
  placement-and-density surface, not a monotone dial (a lone fire at layer 1
  scores 0.9476, i.e. worse).
- **`mx::set_wired_limit()` — CLOSED, already shipped.** The Open-TQ-Metal
  lead (§0c.7, 10× throughput recovery) is already in the runtime:
  `LagunaRuntimeWeights.swift:546-598`, invoked at `:460-462`, gated on
  `DARKBLOOM_WIRED_ZH != "0"` **and `physicalMemory >= 96 GiB` (`:547-548`)**.
  Reopening requires a *different* residency mechanism, not this call. See
  §7's de-risking subsection (c) for the M4-vs-M5 doctrine caveat it creates.
- **`o_proj` joining the fused QKV slab — CLOSED (refuted twice over).** Its
  contraction dim is 6144/8192 rather than 2048, and its input is post-SDPA
  `output`, a strict serial RAW on the same layer's QKV. `g_proj` (K = 2048,
  independent of SDPA) is the only remaining merge candidate; see §7
  subsection (a).
- **The row-tile / row-lane-occupancy axis of the prefill gather GEMM —
  CLOSED, and its banked prize RETRACTED.** I had queued a round-24 assignment
  on "25% row-lane utilisation in the (16,256) grid". Direct source reading
  killed it on three independent grounds:
  - *The premise was arithmetically wrong.* `grid.y` is **one threadgroup per
    expert**, not per (expert, row-chunk) (`quantized.cpp:1960`,
    `fp_quantized_nax.h:1691-1697`); row chunks are an **inner serial loop**
    (`:1713-1716`). An inactive simdgroup does no MMA (`sg_active`,
    `:1717-1719`) though it still runs the K-loop, both barriers and the
    cooperative weight stage. So the real waste is **≈1.29× MMA padding** and
    **≈1.08× weight re-staging**, not 4×.
  - *The axis was already swept and shipped at its optimum.* A measured 6-arm
    `DARKBLOOM_STAGE_BM128` variant sweep lives in editable source
    (`quantized.cpp:1413-1487` doc, `:1491-1510` selector, `:1659-1667` table):
    BM64/WM2/WN2 (control) · BM128/WM4 · BM128/WM2 (regression) · BM128/WM8 ·
    BM64/WM4/WN2 (+15.40%) · **BM64/WM4/WN1 = shipped default**. A separate
    BM ∈ {16,32,64,128} sweep gives chunks/layer 372.6 / 263.2 / **220.5** /
    207.9 with idle TGs pinned at 51.9 for *every* BM; 64→128 buys only −5.7%.
    "The lever is smaller SM, not bigger BM." **SM<16 is impossible**
    (`TM = SM/16` integer-divides to 0 ⇒ zero MMA; `kFragRows=16`), and
    **WM=8 is expressible but useless** (only form is bm128/wm8 ⇒ SM=16,
    identical to shipped).
  - *Row-lane masking is structurally barred.* A 16-row predicate is
    thread-varying while `tile_matmad_nax` is a simdgroup-collective op that
    cannot be lane-masked (`quantized.cpp:1439-1443`; this is why FRAGSKIP was
    rejected).

  **Formal retraction:** the banked **"+1.9–2.6% row-padding prize" is
  withdrawn.** `453,120 = Σ ceil(n_e/16)·16` *is* the floor, not a target.
  Also retired with it: "1 of 4 simdgroups active" (traced to commit `fbc1371`,
  **reasoned, never measured**), and the idea of cashing it in — variant 5
  deliberately moved padding *out of MMA into staging*, so the prize would have
  to be won on the **staging** axis, which is exactly what fern's #40 measured
  null (`Ws` double-buffer dS = **+0.1150 ms**, register prefetch **+0.4626
  ms**, both the wrong sign, inside σ = 0.2536, on 3 same-session M5 receipts
  with `max_abs_diff = 0`).

  Empty threadgroups are priced at **0.355 ms — below the ±0.73% MDE** — and
  `DARKBLOOM_EXPERT_GATHER_GROUPS` self-refutes coarsening (256/128/64/32 give
  empty-TG 20.26/4.77/0.33/0.00% but makespan 40.777/40.838/41.386/42.344 ms),
  so 256 is optimal. Production never operates in the swept occupancy region:
  gate/up is 4,096 TGs (102/core on a 40-core M5), down 8,192 (205/core), and
  the binding occupancy term is **96 simdgroups/core, not threadgroup bytes**
  (#57 + #138; at ≥128 thr/TG, 1 KB / 9,232 / 17,424 / 32,768 B all yield 480
  TGs). **Only two descendants survive**, both listed in §9: routing-aware
  two-régime dispatch (needs a *mechanism proposal, not a knob*), and register
  pressure per simdgroup (never run).
- **The entire checkpoint-compression family — CLOSED by exhaustive offline
  evidence** (nezuko, #143, merged; zero scored bytes, zero receipts). A
  full-byte hash of **all 60,582 slabs / 21,561,408,512 B**:
  - **H4 slab dedup is refuted at 0.0000%.** Routed removable **0 / 59,904**.
    Whole-checkpoint removable 38 slabs = 38 KiB = **0.0002%**. The only
    multi-member class is `router.e_score_correction_bias`, byte-identical
    across 39 layers (and all-zero — a bit-exact micro-win, not queued).
  - **NVFP4 mantissa compression is closed permanently.** All 16 nibble codes
    occur in every routed role ⇒ **0%** fixed-width headroom; pooled nibble
    entropy 3.9417–3.9527 of 4 bits ⇒ **≤ +0.144%** for *any* global memoryless
    code. Best case for whole-checkpoint lossless compression is +9.09%, and
    that is unreachable.
  - **Routed scale-plane recode is closed by a repricing, not by entropy.**
    Scale entropies are 2.4723/2.6002/2.6112 with 42/50/57 distinct codes ⇒
    6-bit, not 4-bit; per-slab maxima 35/38/41 with 705/2,247/1,301 slabs above
    16 codes ⇒ a uniform 4-bit recode is **impossible**. Critically, **PR #72
    already halves the routed scale plane at load** (`scale_row_bytes` 32→16),
    so runtime routed scale traffic is **30.67 MB/step, not 61.34**. Uniform
    6-bit is therefore worth **+0.167%** (below the 0.243% 2σ noise line) and
    mixed 4/6-bit **+0.310%**. Note that this family is *not* closed by a
    numeric bar — the 0.61% bar is deleted (§0a) — it is closed by the entropy
    census showing a uniform 4-bit recode is arithmetically impossible.
  - Routed experts are 39 × 256 × 3 = 29,952 mantissa + 29,952 scale slabs =
    **16.45 GiB = 81.94%** of the checkpoint, so this closure covers the
    overwhelming majority of the bytes.
  - **H6 `residual_rms_router` transpose was pre-mortem refuted from source:**
    the router gemv is *already* float4-coalesced (32 lanes × 8 B = 256
    contiguous B per load). Do not spend a dose or a slot on it.
  - Also delivered and reusable: the **wall-time census** (n = 1,082; last-20
    medians wall 52 s / correctness 39 s / timed 45.5 s ⇒ #148 R1 wall risk LOW,
    but the +70 ms design ceiling *does* leave the envelope, so R2/R3 must not
    be bundled), and the **shadow-execution over-attribution audit** — 10
    HIGH-RISK rows whose "savings" were derived from isolated kernel durations,
    largest `D-FUSE-GATESP` at 213 µs/step. Treat those numbers as upper bounds
    on an unshadowed machine, never as predicted slopes.
- **lm-head cascade dispatch fusion — CLOSED** (fern, #137 Step 0). The
  calibrated injection slope priced the assigned fusion at **5.2 µs = +0.060%**
  on M4, **5× below** the pre-registered 25 µs STOP. Command-buffer batching
  across the four cascade stages is already optimal. The cascade census that
  produced this also produced the round's best arm (see §6): S1 419.8 µs,
  S2 2.3 µs, S3 2.9 µs, **S4 77.4 µs**.
- **`_nax` BK 64→128 — merged as infrastructure, perf arm DEFAULT OFF**
  (tanjiro, #138; `inconclusive`, no receipt spent). Two durable results:
  - **Finding D — a latent correctness-adjacent bug, now fixed.** BK=128
    silently disabled the widened device load: `kSrcBytes` went 16→32 while
    `kWideLoadShapeOk` hard-required `== 16`, so `load_ok` was false and
    `store_ok` true ⇒ **32 scalar byte loads per thread per k-iteration**
    instead of two 16 B vector loads. It compiled, linked and produced correct
    numbers. Fixed by admitting `kSrcBytes == 32` plus two `static_assert`s;
    provably inert at BK=64 (**BK=64 AIR is byte-identical to base**).
  - **⚠️ Doctrine correction — PR #57's occupancy claim was measured on a
    broken probe.** The old probe bound a *dynamic* threadgroup pointer, so
    `setThreadgroupMemoryLength` never bound anything. Repaired: at the real
    geometry (128 threads/TG) 1 KB / 9,232 / 17,424 / 32,768 B **all** give 480
    TGs (24.0/core) ⇒ BK=128 costs zero occupancy on M4; but the 32-threads/TG
    falsification control **does** bind (95.0 → 63.0 TG/core). So "threadgroup
    memory is not the occupancy currency; 96 simdgroups/core is the ceiling" is
    **true at ≥128 threads/TG and FALSE at 32 threads/TG**. Cite it scoped.
  - Why default off: unreachable locally (gen 16 vs `is_nax_available()`,
    `quantized.cpp:1994`); estimated 0.03–0.08% against a ±0.73% MDE; and
    BK=128 needs 34,816 B of threadgroup memory, which **forecloses** the
    BK=64 double-buffered tile (18,432 B). The successor "BK=64 +
    double-buffered weight tile on both shapes" was **formally declined** as a
    re-proposal of the closed `_nax` staging/prefetch/double-buffer/overlap
    axis (#24/#37/#40, arms C1/C2).
  - Reusable: `research/nax_safety_rig.sh` (6 checks, all PASS vs
    `BASE_REV=a36a29c`) + `research/nax_twin_check.py`, plus a **positive**
    kernel-selection assert at `quantized.cpp:1698` verified live as a string
    in `quantized.cpp.o`.
- **Expert-scheduling reordering — CLOSED AS A FAMILY** (frieren, #142, merged).
  Graham's additive bound `makespan ≤ Σp/m + p_max·(1 − 1/m)` with `p_max ≈ 32`
  units against ~353 per core, 9728 tasks over 40–160 slots, caps **any**
  reordering — LPT, SJF, work-stealing, priority queues, static schedules — at
  ~9% of the tail term. The argument is **distribution-free**, not
  trace-specific. Best plausible total 0.458 ms = **+0.166%**, below our ±0.73%
  MDE.
  Two premises of my own assignment were **wrong** and are corrected here:
  (i) there is no worst-case-rows grid — `quantized.cpp:1917-1923` sets
  `grid.y` to a **constant 256** on the expert path and compact otherwise, so
  the recoverable quantity was the 20.26% empty-threadgroup fraction, not a
  15.19× imbalance; (ii) indirect dispatch is **out of surface** —
  `device.h:56` exposes only `dispatch_threadgroups(MTL::Size, MTL::Size)`,
  `get_command_encoder()` is private at `device.h:105`, and `device.h` is not
  among the 97 `editablePaths`. A persistent worker-pool kernel (fixed grid +
  atomic counter) *would* emulate it in-surface, so the rejection is
  cost-benefit rather than impossibility.
  Also self-refuted: `DARKBLOOM_EXPERT_GATHER_GROUPS` coarsening. 256/128/64/32
  groups give 20.26/4.77/0.33/0.00% empty threadgroups, but imbalance grows
  faster than the empty-TG saving (C=80: 40.777/40.838/41.386/42.344 ms).
  **Default 256 is optimal.**
  Merged campaign infrastructure:
  `research/artifacts/route-histogram-prefill512.csv` (9728 rows = 38 sparse
  layers × 256 experts; sum 155648, zero 1971 = 20.26%, median 7, mean 16.00,
  p99 142, max 505, `chunks_bm64` = 8379 ⇒ 1.0802 re-read),
  `-stats.json`, `README-route-histogram.md`,
  `research/lpt_expert_queue_sim.py`,
  `research/pr142-lpt-expert-queue-refutation.md`. Already used twice.
- **H5 per-expert fused FFN — CLOSED, and it was never worth +3.6%.**
  `gate_up → SwiGLU` is **already fused register-locally** and on by default
  (`fp_quantized_nax.h:1797-1798, 1800-1836, 1656-1657`; `quantized.cpp:1581-1584`;
  `jit_kernels.cpp:1205`), decode twins included. The only remaining boundary is
  `SwiGLU → down` (prefill `LagunaRuntimeModel.swift:9829`, decode `:7796-7806`),
  and fusing it needs `64×512×2 + 64×72×2 = 74,752 B` of threadgroup memory =
  **2.28× the 32 KB limit** (current usage 9,224 B); the register alternative is
  512 f32/thread against a ~128 ceiling. Only `BM=16` fits, which forces `WM=1`
  and 32 threads/TG — a **different kernel family**, not a fusion, and it would
  have to re-win the `bm==64 && wm==4` accept gate at `quantized.cpp:1660-1671`.
  Separately the **SLC-absorption bound partly holds**: the governing figure is
  **8 MiB per layer** (the 312 MiB aggregate is never simultaneously resident),
  which is comfortably served by a ~24 MiB M4-Pro or ≥48 MB M5-Max-class SLC, so
  the promised DRAM saving is largely illusory. Decode traffic is only
  ~0.6 MiB/step, so H5 was **only ever a prefill arm**. Full write-up and the
  replacement lead: [`h5-per-expert-fused-ffn-closure.md`](h5-per-expert-fused-ffn-closure.md).
- **lm-head 3+2 re-split — DEAD.** Measured **−0.377%**, CI [−0.644, −0.230].
  It adds **+23.64 MB/step** and needs 44.74% survivors against an observed
  **85.65%**. Nezuko's "#105 GO +0.405%" was the *pricing constant* applied to
  a stale pre-result assumption. **There is no shippable lm-head byte arm.**
- **BN 64→32 (promoted arm C2) is WRONG, not slow.** Default variant 5 is
  BM64/WM4/**WN1** (`quantized.cpp:1468-1478`); `kSwigluRegLocal` requires
  `BN==64` (`fp_quantized_nax.h:1656-1657`); fused gate_up pairs gate column
  `c` with up column `c+32` inside one 64-wide tile, so BN=32 makes in-kernel
  swiglu **impossible** for N=1024/K=2048. Admissible **down-only**.
- **Resubmission variance-harvesting** — see §3.

**Previously closed (top re-proposal risks — a fresh idea generator will
suggest these):**

per-kernel decode residual recovery ("find the big one") · the routed-QMV
byte/bandwidth framing · baseline-draw timing exploitation · the entire `_nax`
staging / prefetch / double-buffer / overlap axis · the in-kernel
`threadgroup_barrier` family · batched reduction and chain-shortening as a
general tactic (three independent arms died at their own analytic ceiling) ·
`sliding_fused_attn_ring_v1` as a byte target (443 GB/s = 170% of the M4 DRAM
ceiling, ~90% of its issue floor) · offline codes/scales interleave (closed
twice) · attention byte de-amplification / head packing · `MLX_MAX_OPS_PER_BUFFER`
(inert ≥40) · `MLX_METAL_FAST_SYNCH` (inert) · decode graph repartitioning ·
in-loop host CPU · decode head latency · first-touch prewarm (now closed for the
prefill/seed path too — see the 06:30 bullet) · **the cold-seed-prefill lever**
(`benchmarkPrefillWarmupRuns = 0`; the scored prefill and the in-window seed
forward are the same single cold operation, so there is no asymmetry to
harvest) · ⛔ **holding warmup buffers live across `Memory.clearCache()` —
OUT OF BOUNDS, protocol bypass, not merely closed** · *naive* attention
INT8 envelope adoption (backwards — adds ~802 MB/step; the **family** is only
low-priority now, reopenable by a net byte/math advantage inside the envelope,
§0a row 9) · certified lm-head screening ·
NVFP4 scale-plane amplification (A = 1.000) · quantized attention weights in
prefill · prefill overlap C1/C2 · `DARKBLOOM_STAGE_BM128` · **attributing** a
small mechanism from `officialScore` (it remains authoritative for *ranking*,
§0a row 5) · `./probe` on the M5 (impossible — no shell on the ranked
host; the only M5 channel is a submitted candidate plus its receipt `metrics`).

**`MLX_MAX_MB_PER_BUFFER` — CLOSED, and it is our canonical M4→M5 inversion.**
Earlier notes said "no M5 datum exists"; that is **false**. 200 → 50 was
submitted (receipt `3e6fdcb`, commit `1ce8373`, `research/nezuko-mb50-receipt.md`)
and returned **`ns` −1.608%** on the M5 — `S` +2.193%, `T` +1.316% — against
**two independent balanced M4 confirmations of −1.76% and −1.99% wall/step,
monotone in the cap.** Opposite sign. Do not re-propose it, and cite it whenever
a student wants to treat M4 agreement as M5 evidence.

**⚠️ REOPENED THIS ROUND — "decode has no exploitable intra-CB concurrency"
(≤ 0.06 ms/step).** This row entered the closed list on #158 §4.5 alone
(`gpu_busy_sum` flat at 7.99 ± 0.06 ms across 45 → 204 CBs). PR #101 §3.2
independently measures **+0.456 ms/step** for forcing `MTL::DispatchTypeSerial`
— 7.6× larger, with complete separation and p = 0.029. Both cannot be right as
stated. **PR #174 (nezuko, round 24) is the discriminator**; §4.9 holds the
three candidate resolutions and the pre-committed decision table. Until it
reports:

- do **not** cite the ≤ 0.06 ms/step bound to reject a decode proposal without
  also citing the +0.456 ms/step counter-measurement;
- do **not** cite the +0.456 ms/step figure as a harvestable pool either — it
  is the cost of *removing* concurrency, which is not the same as the gain from
  *adding* it;
- do **not** treat a §2.b census row as *exposed* serial cost without an
  independent exposure check (§4.9 interim rule).

The **prefill** co-residency closure (#157 D5, 245× residency margin) is
untouched by this reopening and remains unconditional.

**Still open in the archive but reopened / unresolved:** prefill glue (old C5),
shared-expert overlap (old 5b), decode intra-CB concurrency (above).

---

## 9a. ⚠️ CORRECTION: what we actually know about prefill time

Two numbers this programme has been quoting as measurements are not
measurements. Both were audited to primary sources on 2026-08-06; correct them
wherever you see them.

**1. The "31.28 ms unattributed prefill pool" does not exist as a measured
quantity.** It is a *subtraction residual* — measured M5 wall minus a **derived
roofline floor**, with no per-kernel attribution behind it.
`research/maple-tanjiro-pr91-prefill-budget-census.md:845` already adjudicates
the exact 31.28 value as **mis-sourced / CLOSED**: it is reproducible only under
an unstated 500 GB/s assumption plus a 20.26% zero-row discount (`:106-112`).
The census's own honest statement is **UNATTRIBUTED = 22.9–37.9 ms, central
27.88 ms at 546.2 GB/s** (`:657-658`), explicitly labelled "an **upper bound on
recoverable time, not recoverable time**" (`:666-667`).
`RESEARCH_STATE_ARCHIVE_through-round-21.md:1172-1181, :6365` had already
refuted the related CLAIM C and withdrawn a 15.4 ms overlap pool.

The only *direct* prefill wall-vs-busy measurement we own says the opposite of a
large pool. `research/pr91-logs/step1-split0.log:15-19` (M4, shipped cap): wall
**545.242 ms**, `gpu_busy_sum` **540.455 ms = 99.1% of wall**, gap ≈ **4.79 ms
(0.9%)**, **81 command buffers, 1222 dispatches**, 24.717 GiB bound. Archive
closure `:6374` says the same at 99.4%. And the M5-measured marginal command
buffer cost is **+27.177 µs/cb** for prefill (2147 µs / 79 cb,
`research/nezuko-mbcap-up-prereg.md:80-82`, ranked receipt `3e6fdcba`) — so the
*entire* 81-CB prefill boundary cost on M5 is **O(2.1 ms)**. CB overhead cannot
be 31 ms. (Caveat from `RESEARCH_STATE_ARCHIVE:3277`: do not quote the
+27.2 µs/cb rate *above* the shipped cap.)

**2. "94.2% of M5 prefill is `_nax`" is an M4 measurement, and its denominator
is the M4 per-kernel census total (~550 ms), not M5 wall.** Origin
`research/maple-fern-prefill-roofline.md:20-35`: `nvfp4_gather_qmm_rhs_nt`
266.65 ms (48.5%) + `steel_gemm_fused_nt` 183.37 (33.4%) + `steel_gemm_splitk_nt`
+ accum 33.04 (6.0%) + `steel_attention` 28.23 (5.1%) + `nvfp4_qmm_t` 6.64 (1.2%)
= 517.92 ms = 94.2%. The correct reading is *"these are the M4 kernels that M5
replaces with `_nax` variants"*. It drifted into a direct M5 claim at
`RESEARCH_IDEAS_2026-08-06_09:00.md:189`, `PREFILL_LEDGER_INSTRUMENT.md:10` and
`RESEARCH_STATE_ARCHIVE_through-round-21.md:5823`. The related "~66 ms M5 busy"
is doubly inferred (`census:998` = 97.95 − 31.28).

**What is actually solid about prefill:**

| fact | value | source |
|---|---|---|
| M5 prefill wall (ranked, promoted arm) | **97.895 ms** | receipt `97a5090` |
| M4 prefill wall / busy / gap | 545.24 / 540.46 / 4.79 ms (**99.1% busy**) | `pr91-logs/step1-split0.log:15-19` |
| command buffers @ shipped 200 MB cap | **81** prefill; decode **45/step** (#158, n=28) vs **34/step** (mbcap ladder) ⚠️ see note | `nezuko-mbcap-up-prereg.md:31-37`, **reproduces measured M5 counts exactly** (`-receipt.md:34,:186`); #158 §4.5, §4.7 |
| dispatches | **1222** prefill, **406** decode/step | same; #158 confirms 406 with the census (`:1548`) |
| M5 marginal CB cost | prefill **+27.177 µs/cb**, decode **+1.1045 µs/cb** | ranked receipt `3e6fdcba` |
| M4 marginal CB cost | prefill 5.88 µs/cb, decode 1.681 µs/cb | same source, M4 arm |
| honest unattributed band | **22.9–37.9 ms, upper bound only** | `pr91-...-census.md:657-667` |

**CB counts are cap-dependent; dispatch counts are not.** Across the
`MLX_MAX_MB_PER_BUFFER` ladder, prefill CBs go **234 (cap 12) → 81 (200 MB,
shipped) → 42 (400) → 41 (512+)** and decode CBs go **34 → 19 → 18 → 13 → 9**;
dispatch counts (1222 prefill, 406 decode) are invariant throughout. ⚠️ The
decode CB count therefore has two live readings — **45/step** measured directly
by #158 under the profiling hook (stable at 45–46 across 28 runs while
dispatches moved 406 → 601) and **34/step** from the mbcap ladder's cap-12 row.
They are not the same configuration and should not be reconciled by picking one:
quote 45 for anything derived from #158's decode census, and the ladder value
only when reasoning about the cap. Anyone who needs the shipped-cap decode CB
count for a *new* derivation should re-measure it rather than inherit either
number. **`−1.37 µs/boundary` is retired** — it was a fit to the old ladder and
has been superseded by the two directly measured marginal costs above.

**The instrument blind spot, and the cheapest fix.** The PR91 hook captures only
`GPUStartTime()` / `GPUEndTime()` (`research/pr91-gpuprof-hook.patch:137-141`).
There is **no host-side timestamp and no `addScheduledHandler` anywhere in the
repo**, so "host is slow building the graph" cannot be separated from "GPU is
waiting on the driver". `kernelStartTime()` / `kernelEndTime()` are already
declared in
`Vendor/mlx-swift/Source/Cmlx/metal-cpp/Metal/MTLCommandBuffer.hpp:165,167` and
used **nowhere**. Adding those two plus a host clock read at the `commit()` site
(`device.cpp:489`) is the smallest instrument upgrade that would answer the
causal question, and it costs zero receipts. **That host clock read must be
`CLOCK_UPTIME_RAW`** — see §4.1b LAW 1 for why `time.perf_counter()` silently
destroyed every profiled run in #158 r2. `device.cpp` is not editable, so this
lives as a `.patch` under `research/`, like `pr91-gpuprof-hook.patch`.

**~~Parser bug~~ — CLAIM WITHDRAWN, and already hardened.** I asserted that
`research/decode_probe.py` and `nezuko_cb_idle.py` corrupted kernel names by
using `split(" ", 4)` against a six-field record. #158 r2 **rebutted this with
the raw line** (`:892`): the hook emits **five** fields, so `split(" ", 4)` was
correct all along. Nezuko nonetheless replaced both call sites with an
auto-detecting `parse_gpuprof_line()` (`research/decode_probe.py:38-51`),
imported by `nezuko_cb_idle.py:37` and `nezuko_pr158_split_kernels.py:20`, so
the parser now tolerates either format. `research/prefill_probe.py:48` uses
`split(" ", 5)` and is also correct for its own hook. **Nothing to fix; do not
re-open this.**

**The one measurement that would settle prefill:** a single M5 session with the
PR91 hook attached. It either kills the pool outright or converts it into a real
target. Until then, treat every prefill kernel-level number as M4 evidence about
a code path M4 does not execute the same way.

---

## 9. Potential next research directions

Ordered by expected value, not by ease.

> **Structural criticism to keep in view (round-23 frontier review).** Every one
> of the 20+ families in §8 is either a kernel-micro-optimisation or a
> byte-currency argument. We have never tested a *graph-level execution
> structure* change — how the forward pass is decomposed into dispatches,
> chunks and command buffers — and we have never spent a round on decode
> **dead time** as opposed to decode **bytes**. Directions 1, 3 and 4 below
> exist to break that monoculture. Two of them (1, 3) are falsifiable on M4
> for free, which is rare on this programme.

1. **Decode dead-time programme (frontier "Attack A") — ⚠️ SEVERELY DOWNGRADED
   by its own experiment (#158, merged `268fb087`), and now split in two.**
   The original pitch was that decode carried a large pool of time not spent
   moving bytes, priced from three numbers. **All three have since been
   retired or reduced:**
   - the **1.980 µs/dispatch** M5 price (PR #34 r2) generalised into a
     "1.9 µs floor ⇒ 771 µs ⇒ 9.6%" headline that #158 r2 **withdrew outright**
     (§4.1 item 4). Per-dispatch cost is real but **site-specific**, envelope
     ≈1.5–8 µs, best traffic-free estimate **3.59 ± 1.44 µs/dispatch**, and it
     lives **inside GPU busy** at a fixed 45 CBs/step. There is no floor and no
     band. Never price a decode fusion at 1.9 µs/dispatch again.
   - the **0.322 ms host/queue gap** is proportional, not absolute, and is
     bounded at 3.01% of wall with no harvestable pool (§4.1 item 3).
   - forced serialization's **+5.49%** is the *one survivor*, and it is now the
     open contradiction of §4.9 rather than a pool: it is the cost of
     *removing* concurrency, which does not entail a symmetric gain from adding
     it, and it is contradicted 7.6× by #158's own flat-`gpu_busy_sum` control.

   What is left is two much narrower questions, and only the first is live:

   **1a. Is the §2.b decode census telling the truth about *exposed* cost?
   → IN FLIGHT as #174 (nezuko).** The census attributes 8006.6 µs/step across
   24 kernels, but a census row is *occupancy*, not *exposure*. We already own
   one calibrator showing the two can differ by 10×
   (`DARKBLOOM_AFFINE_GATE_SOFTPLUS`: 262 µs/step of census, −0.04% measured ⇒
   E ≈ 0.1, PR #101). #174 measures exposure factors directly and re-prices the
   top 10 rows. **Until it reports, every decode target selected off the census
   is provisional**, including the four shipped fusions' apparent 1.17 ms/step.
   A clean null there (E ≈ 1 everywhere) would *restore* this direction at
   roughly its original strength; a low-E result kills most of it.

   **1b. Fusion selected by RAW-dependence — still valid, but re-priced.**
   The mechanism is sound and has shipped four times (r1 table, §4.1a). It is
   now priced **traffic-delta first, then a 3–4 µs/dispatch bonus sized at that
   site**, and the wall marginal must be checked, not just busy. This is
   ordinary incremental work, not a +2–5% programme. It is still **M4-valid end
   to end** (decode kernels are hand-written MSL/QMV, not `_nax`, and the steady
   decode step is host-independent), but any local arm must now clear the
   **Δ ≥ 150 dispatches** design rule from §4.1b LAW 2 — most single-fusion arms
   move 39–78 dispatches and therefore sit inside the ±70 µs between-session
   scatter. For those, **the ranked M5 receipt channel is the more sensitive
   instrument** (cv 0.235% on `T`), which inverts the old "measure locally
   first" default for small decode fusions.
2. **Close the prefill *and decode* ledger with the receipt-channel duplication
   instrument. → IN FLIGHT as #148 (frieren).** Full spec:
   [`PREFILL_LEDGER_INSTRUMENT.md`](PREFILL_LEDGER_INSTRUMENT.md).
   §2 says the decode inventory is worth at most +2.85% even at 100% removal,
   while prefill's unattributed remainder is a **subtraction residual, not a
   pool** — honest range **22.9–37.9 ms, central 27.88 ms** (§9a), and the
   ledger is worth running precisely *because* that residual is unmeasured. We
   are blind to it because 94.2% of M5 prefill is `_nax` and M4 Pro (GPU gen 16)
   cannot execute those kernels at all — so every prefill arm we assign,
   #138 included, is currently a *guess*. The instrument fixes that: duplicate
   one kernel family's pure work, submit a deliberately-slow candidate, and read
   the shift off the candidate arm's raw `prefill_seconds_per_token`.
   > **The instrument already exists and has already returned three M5
   > readings**: `research/tanjiro-pr34/instrument.patch` (317 lines against
   > `LagunaRuntimeModel.swift`), four knobs
   > `DARKBLOOM_INJECT_{PREFILL_ROUTED,PREFILL_ATTN,DECODE_ATTN,DECODE_ROUTED}`.
   > **Disposal is `asyncEval(pending)`, NOT a `0.5*(y1+y2)` fold** — results are
   > never consumed into `y`, so the output store path is untouched and
   > bit-exactness is *structural*; the bf16-overflow hazard of a fold does not
   > exist. It is ~round-10 vintage and will **not** apply cleanly: port the four
   > `lagunaInject*Work` builders and the disposal, not the hunks.
   **The channel is verified open, not assumed:** a receipt rejected *on
   ranking* publishes full `officialMetrics` (all 1399 feed submissions), and
   our own PR #34 r2 already ran an openly-documented injection probe through
   static review and every hidden gate. Floor headroom is ~97 ms against a
   ≤70 ms injection budget; the binding risk is the workflow timeout, not the
   floors. A floor/correctness/gate failure, by contrast, publishes **nothing**.
   Three receipts resolve a strategic fork we cannot otherwise resolve: if the
   residual `R = S₀ − Σx̂ᵢ ≈ 0`, the unattributed prefill time is *inside* the
   measured kernels (work programme: inner loops, tile geometry); if
   `R ≈ 20–30 ms` it is *between* them (work programme: dispatch structure).
   ⚠️ Every `x̂ᵢ` from #34 is a **marginal** cost carrying two unseparated
   biases (warm-cache amortisation ⇒ undercount, overlap exposure ⇒ overcount),
   so `R` is a difference of biased quantities. **First named next step, already
   assigned to frieren:** run `PREFILL_ROUTED` at **13 and 26** to give four
   dose points (0, 13, 26, 39) — slope 43.2619/39 = **1.109 ms/copy**, so m=26 ⇒
   S ≈ 126.7 ms, far below the ~200.6 ms floor trip. **Pre-register 26 first;
   do not re-measure 39.** Linear ⇒ the residual stands; concave ⇒ it shrinks;
   convex ⇒ it grows. The named gap this closes: *"there is no dose-response
   within a single kernel."*
   **Owner: frieren, PR #148** — he wrote "`T_gather ≈ 25 ms` is asserted, never
   measured" in #142, so he fills the hole he found. Nezuko was told on #143 that
   he no longer owns this. **Do not let two students probe concurrently** — one
   shared in-flight slot.
   Refinements added since the spec was written:
   **(a) The decode axis is now co-primary, not a bonus row.**
   `prefill_seconds_per_token` and `decode_seconds_per_token` publish
   independently, so **every** receipt must carry a decode row, not only
   both-phase families such as `routed_gather_gemm`. The decode row probably
   matters more (75% weight): the "decode is exhausted at +2.85%" claim is a
   **bandwidth** argument from per-kernel roofline utilisation (94.6–100.2%),
   and roofline utilisation says nothing about **gap time between kernels**.
   The decode slope gives Σ(kernel time) directly; the residual
   `T − Σ(slopes)` against `T = 4.1436 ms/step` is the number that arbitrates
   §4.1 and gates direction 1. "Host gap is absolute" predicts ≈322 µs (7.8% of
   the M5 step); "host gap is proportional" predicts ≈137 µs — 185 µs apart,
   comfortably resolvable.
   **(a′) Multi-dose linearity is mandatory.** Each family must be injected at
   ≥2 levels and reported as a **slope in absolute µs/step per duplicated copy**,
   plus the linearity residual. A slope that does not scale with dose is not a
   measurement of that kernel; it is a measurement of the schedule, and that
   disagreement is itself a publishable shadow-execution finding. Predict the
   M4 slope ≈ 1.0× the kernel's isolated GPU duration before running; a slope
   materially below that means the duplicate was elided and the probe is invalid.
   Prefer large-isolated-duration families for dose 1, and include at least one
   #48-style *hazard-free* family, because hazard-free vs hazard-bearing is
   exactly what discriminates §4.1 resolution (a) from (b).
   **(b) Wall-time trap.** Injection also multiplies work in the hidden
   correctness suite, anchors, free runs and GPQA checks — far more forward
   passes than the timed window. Project
   `wall ≈ wall_median + (injected fraction)×correctness_seconds + prefill Δ +
   128×decode Δ` and size the multiplier to ≤70% of the timeout. **Escape hatch:**
   gate the injection on `seq_len > 1` (prefill only). A shape gate is legal under
   the serial non-speculative rule — it branches on the supplied input's length,
   not on token values, and is the same legal class as the existing
   prefill-vs-decode kernel selection.
   **Elision is the probe's existence risk:** MLX is lazy and may CSE the
   duplicate away, which looks identical to `T_gather = 0`. The M4 must show a
   measurable slowdown first; CSE is a graph-layer property, so the non-`_nax` M4
   path is a valid test despite M4 being unable to execute `_nax`.
   Fold bit-exactly as `0.5*(y1+y2)` — exact in IEEE-754 including subnormals;
   the **only** hazard is bf16 overflow to inf. Never `y1 + (y2 − y2)`. Never
   double-append KV. **Rejected design:** Hadamard/compressed-sensing
   multiplexing of several families into one receipt — dominated, since the
   signals are already ~60σ.
3. **Graph-level two-chunk wavefront prefill (frontier "Attack B") — the
   monoculture-breaker, and it has a free falsifier. → ASSIGNED as #157
   (tanjiro), gated on the falsifier.** Today prefill runs one
   512-token chunk through layer *i* completely before starting layer *i+1*, so
   the bf16 attention block and the NVFP4 routed GEMMs never co-reside on the
   GPU. Split the prompt into two 256-token chunks and software-pipeline them
   (chunk A at layer *i+1* while chunk B is at layer *i*) so the two very
   different kernel families overlap. **This is legal**: every row still
   corresponds to a token supplied in the same invocation, which the serial
   non-speculative rule explicitly permits for multi-row kernels.
   Arithmetic: the tax is re-reading the ~17.7 GB of routed expert banks at
   roughly 1.7–1.9× (two chunks of 256 rows touch nearly the same expert set as
   one chunk of 512), ≈ **+24 ms** on `S`; the prize is hiding 25–35 ms of bf16
   attention behind GEMM time. Net **−1 to +11 ms**, i.e. **0 to +4%** — a
   fat-tailed bet, not a favourite. What makes it worth a slot anyway is a
   **zero-receipt M4 falsifier** — but the *old* falsifier is retired and must
   not be reused.
   > ⚠️ **RETIRED FALSIFIER — do not check `gpu_busy_union < gpu_busy_sum`.**
   > PR #157 D1 proved that instrument is computed **per command buffer** and is
   > therefore structurally blind: MLX packs 20–50 ops into one CB on one queue,
   > so `union == sum` is guaranteed by construction, not by the hardware. Its
   > control run `concurrent_1cb` reported `overlap_eff` **1.0024** — full,
   > ideal overlap — while the union metric read exactly **0.000000**. Any
   > "nothing overlaps" reading from §4.1 that rested on this metric is void.
   >
   > **Replacement falsifier — the residency ceiling (§4.1, #157 D2).** Two
   > independent kernels overlap when their **combined threadgroup count is
   > ≲480 on a 20-core M4 Pro** (24 TG/core) and essentially not at all above
   > it. Measured ladder: 16 TGs → `overlap_eff` 1.0112; 80 → 0.0542; 2048 →
   > 0.0213; 9792 → 0.0064. Scale to the M5 Max's 40 cores and the ceiling is
   > ~960. **The prefill MoE dispatch alone is 9,798 TGs per layer** (#157 D5),
   > i.e. **245× the M5 ceiling**, and the attention kernels it would hide
   > behind are 384–512 TGs. So the interleave has no under-occupied machine to
   > exploit and this direction is **already falsified on paper** at
   > prefill-512 width. It survives only for a variant that first shows one of
   > the two families leaving the machine under-occupied. Do not spend a
   > student-day re-measuring the ceiling; spend it finding an under-occupied
   > pair, or drop the direction.
4. **Offline cross-tensor expert-slab re-pack in consumption order (frontier
   "Attack C").** The byte-price law (§2) shows the same DRAM delivering
   968.4 GB/s to the lm-head plane but only 700.3 GB/s to the routed MoE g32
   plane. That 27.7% gap is a *layout* property, not a bandwidth property.
   Re-pack the routed expert banks offline so that bytes are laid out in the
   order the gather kernel consumes them across tensors. If the routed plane
   cleared at the lm-head rate, 553 MB/step × (1/700.3 − 1/968.4) ≈ **219 µs**,
   a **+3.2%** cap; realistically **+1–2%**. Values are untouched, so this is
   bit-exact by construction and is pure `MLXFastTransform` + metadata work.
   **Distinct from two closed families:** the twice-closed offline interleave
   was *within-tensor* (codes and scales of one tensor), and #71 was *in-kernel*
   staging. This is *cross-tensor ordering*.
   > **⚠️ DOWNGRADED — do not assign without a premise test first.** Reading the
   > actual layout after #143: routed `gate` and `up` are **already fused into
   > one per-expert-contiguous bank**, and `down[e]` is consumed by a
   > *different dispatch*. There is therefore very little cross-tensor locality
   > left to exploit *within* a dispatch, and none is exploitable *across*
   > dispatches. The 700.3 vs 968.4 GB/s deficit is real but this is not yet a
   > demonstrated explanation of it. Step 0 for any future assignment is to
   > **explain the deficit** — gather-index scatter, per-expert row counts below
   > a full tile, scale-plane stride, or SLC behaviour — before proposing a
   > re-pack. Also gate on #148 publishing a gather-plane row.
   >
   > **⚠️ SECOND DOWNGRADE — the 27.7% deficit is not statistically
   > established.** Both endpoints are **n=1** planes with enormous intervals:
   > the 968.4 GB/s lm-head plane
   > (`maple-nezuko-pr110-byte-price-ledger.md:267`, 25.69 MB) has CI
   > **[773.6, 1294.6]**, and the 700.3 GB/s routed g32 plane (`:269`,
   > 30.67 MB) has CI **[493.1, 1207.9]**. Those bands overlap on 83.4% /
   > 60.8% of their mass. The ledger itself flags the divergence between its
   > `PLANE` ratio 1.3828 (`:493`) and its `ESTIMATOR` ratio 1.2821 (`:494`).
   > Independent routed-block averages land at **546.2 ± 23.3 GB/s**
   > (`tanjiro-pr34-result.md:602`) and attention QMV at **651.8 GB/s** with no
   > gather at all. Mechanism hypotheses tested since: H-a address alignment
   > **REFUTED** (A = 1.000, `maple-fern-pr22-result.md:84-105`); H-d two
   > disjoint streams **REFUTED** (walk-order packed bank already ships,
   > default ON); H-c wave quantisation at M=1 **SUPPORTED**; H-b gather
   > indirection refuted as a *per-byte* cost, undetermined as *serial
   > latency*. Read together, the effect is **dispatch/latency, not per-byte
   > layout efficiency** — which is exactly what an offline re-pack cannot
   > touch. **No offline re-layout is justified by this number.** If the
   > direction is revived, its Step 0 must first re-measure both planes with
   > n ≥ 5 and show non-overlapping intervals.
5. **Prefill arms generally.** Prefill still carries 25% of the score weight
   and a hard 0.95 floor, and the public field has been stuck on this axis for
   102 consecutive submissions — so the axis is not exhausted. But **do not
   size a prefill arm off the retired "+15.17%" figure**: that came from the
   withdrawn 31.28 ms pool (§9a). Size prefill arms off the measured
   elasticity instead — **−1 ms on `S` = +0.362%** — and off an honest,
   *measured* target, not a subtraction residual. Until direction 2 lands its
   ledger these are unguided. Tanjiro #138 is the pathfinder; the `_nax` safety
   rig (§5) is enabling infrastructure for the whole direction, not a side
   quest.
6. **Close the 24.9 MB / 5.7% unallocated census remainder.** An unexplained
   5.7% of the byte inventory is the most likely place a missed arm is hiding.
   Assigned as a secondary to nezuko.
7. **Occupancy / tile geometry on the two unsaturated kernels — BOTH NOW
   CLOSED. Do not re-propose either.**
   > **`gate_sp` — measured null, not an open lead.** PR #101 arm A built
   > exactly the proposed re-geometrization: parameterized `R`/`NS`, grid
   > divisor `heads/(NS*R)`, **9 geometries** swept, bit-exactness *proved*
   > (128 payload comparisons bitwise equal at bf16 and fp32, plus a live
   > perturbation control shown to fire, `pr101-frieren-result.md:78-90`).
   > Result: **−0.04%, CI [−0.55%, +0.48%]** — a clean null with a tight
   > interval. The hypothesised "unexploited parallel axis" **does not exist**:
   > the 2048-wide reduction is *already* split 32-way across the simdgroup
   > (32 lanes × 8 values × 8 k-blocks) and closed by `simd_sum`
   > (`LagunaRuntimeModel.swift:4304`). The only remaining bit-exact axis is one
   > simdgroup per row = 2048 threads = **4×, not 32–64×**; anything beyond
   > needs split-K plus a two-stage reduce, which changes float accumulation
   > order and is therefore not bit-exact. Dropping R 4→1 also multiplies
   > redundant input re-reads 4× (2.46 → 9.83 MB/step, `:191-196`), and
   > isolated duration spread across the 9 geometries was only 80–117%
   > (`:404-406`). The 186 µs "prize" is an **estimated, explicitly
   > unreachable ceiling** (`nezuko-pr158-decode-dead-time.md:692`,
   > `:704-705`, `:743` — it is exposed 262.3 µs minus 40 dispatches × the now
   > *retired* 1.9 µs floor), not a cost. Corrected facts: `gate_sp` is the
   > per-head `g_proj` + softplus, **not** the shared expert; unique DRAM
   > 2304 B/row × 2400 rows = **5.5296 MB/step**; achieved bandwidth **22.2
   > GB/s (h64) / 17.5 GB/s (h48)** — the "30.4 GB/s" figure quoted above was
   > wrong and is withdrawn.
   >
   > **`residual_rms_router` (61.8% useful lanes) — structurally closed.** The
   > 50% idle lanes carry **zero intra-warp divergence**: the guard is a
   > compile-time whole-simdgroup predicate, so ballot compaction has nothing
   > to compact. §8 records this closure.
   >
   > Everything else is at 94.6–100.2% and was never worth an arm. **This whole
   > direction is now empty.** More importantly, `gate_sp` is the programme's
   > best **exposure calibrator**: the §2.b census charges it 199.2 + 63.1 =
   > **262 µs/step**, yet removing a real inefficiency inside it moved the
   > decode step by **−0.04%**, implying an exposure factor of **≈0.1**. That
   > is the seed of §4.9 and of PR #174.
8. **Scheduling rather than arithmetic — narrowed, not closed.** #142 closed
   *reordering* (§8: Graham's bound caps it distribution-free). What survives is
   the rest of the launch layer: encoder construction, command-buffer
   partitioning, barrier placement, and the number of dispatches. That layer is
   generation-independent, so M4 evidence is admissible — its main advantage over
   every prefill arm. On the decode side this is direction 1; on the prefill
   side direction 2's `R` verdict decides its worth: `R ≈ 20–30 ms` makes it the
   round-23 headline, `R ≈ 0` demotes it.
9. **Deletion as an optimization.** Nezuko's 259-line deletion is the only
   scored-byte movement in four rounds, and global headroom is now down to
   **73,089 B** at `268fb087` (`current=2926911/3000000`, 142 files).
   Reclaiming dead scaffolding is cheap, safe, and buys room for real arms.
   Candidates: tanjiro's 9 near-duplicate `.metal` variants; the dead BK128
   machinery (5,164 B); fern's dual-arm flag; the ~32 KB of Laguna-dead
   transform sidecar coders (item 12). **But note the binding constraint is
   not global.** `Sources/MLXFastModel/LagunaRuntimeModel.swift` is at
   **467,167 / 524,288 B**, leaving only **57,121 B** in the one file every
   runtime arm has to edit. Deleting transform-side bytes lifts the global
   ceiling and does nothing for that. A cleanup PR should therefore target
   `LagunaRuntimeModel.swift` itself first.
10. **Shared-expert prefill SwiGLU epilogue.** Held detail in §7. Prefill-only,
    78.0 MiB/step of written+read traffic across 39 sparse layers plus 78 fewer
    dispatches; the concatenated NVFP4 `[gate;up]` bank already exists so there
    is no `MLXFastTransform` work. The real task is adding a SwiGLU epilogue to
    `fp_qmm_t_nax_static`, and the dominant risk is bf16 bit-exactness of the
    fused sigmoid against `compiledSiluProduct`. Dense layer 0 is **closed** —
    bf16 `Linear`, `N=16384`, and its `x.dim(1)==1` guard is load-bearing
    correctness.
11. **Bit-exactness relaxation, carefully.** H1 (row-adaptive dual-path gather
    kernel, +1.4…+2.9%) is the largest single arm we have and it is blocked on
    correctness, not on mechanism. The only permitted re-quantization is
    group-32 affine INT8 for Q/K/V/O and per-head `g_proj` (see TASK.md's
    accepted envelope) — and adopting that envelope for attention is already
    closed as *backwards*. So H1 needs a different correctness argument,
    specifically a bit-exactness proof rather than an envelope appeal. It is
    also M4-blind, so it needs a receipt slot to evaluate at all.

12. **The offline transform surface — an untouched 87% of the submittable
    board (advisor audit, 2026-08-06).** Verified facts, each checked against
    source rather than inferred:
    - `editablePaths`' 97 entries expand to **142 files**, and **123 of them
      (87%) have never been modified by this team** on any branch. All five
      files of `Sources/MLXFastTransform/` are among them, as is every file
      under `steel/attn` and all of `steel/gemm` except `nax.h`.
    - **On Laguna the transform is a pass-through.** `Transform.swift:219-226`
      APFS CoW-clones each reference shard byte-identically; `:250-269`
      explicitly returns *empty* metadata reports for Laguna, so
      `AffineMetadataCoding.swift` and `TiedHeadMetadataCoding.swift`
      (~32 KB combined) are dead on our path and reachable only from the
      `.gemma4` branch.
    - **The transform output is not pinned by a golden digest.** Every pinned
      SHA-256 in `fixtures/poolside_laguna_xs_2_1_nvfp4_tensor_inventory.json`
      and `Tests/MLXFastTests/LagunaArtifactContractTests.swift:275-300` hashes
      the **input** reference checkpoint. The only trusted output check is
      `Sources/MLXFastTrustedHarness/TransformVerification.swift:78-91`, which
      re-runs *our own submitted* transform and byte-compares — a determinism
      check, not a fixed digest — and it is opt-in
      (`MLXFAST_VERIFY_TRANSFORM`, `benchmark.sh:2150`, workflow default
      false). The only hard output constraint is the 25 GiB cap in
      `Sources/MLXFastCore/Constants.swift:176`.
    - AGENTS.md sanctions this explicitly: "Use transform metadata or layout
      changes that let the runtime skip real work without changing behavior."

    **Two findings that cut the other way, and they are why this is item 12
    and not item 1:**
    - **Editing `Sources/MLXFastTransform/` forces a full 21.6 GB
      regeneration on the official host.** `source_hash()`
      (`benchmark.sh:1579-1586`) hashes `Package.swift`, `Package.resolved`,
      `Sources/MLXFastCore` and `Sources/MLXFastTransform`; a mismatch against
      `SOURCE_HASH_PATH` triggers the regenerate branch at `:2125-2135`. Today
      that branch is nearly free because it is a CoW clone. A real re-layout
      must *read and rewrite* the whole checkpoint. Worse, the paired session
      runs a pristine-transform baseline and our candidate, so the hash flips
      **twice** and the cost may be paid twice. Against a base rate of
      **49/1399 submissions dead on timeout**, that is a first-order risk, not
      a footnote.
    - **`docs/laguna-weight-contract.md:131` says the `switch_mlp` tensors
      "must not be split into per-expert tensors."** Read in context that
      paragraph describes the *input* schema, and the trusted tests
      (`LagunaArtifactContractTests.swift:344,368`) only pin
      `LagunaCheckpointValidation.expectedTensorInventory()` to the public 912
      and require it to reject input mutations. But the prose is ambiguous and
      a static review could read it as governing the output. **Nobody spends a
      receipt on a re-layout until this is resolved.**

    **Therefore: Step 0 is a null-layout legality-and-cost probe, not a
    re-layout.** Change the transform so the output is semantically identical
    (same 912 tensor names, dtypes, shapes and bytes) but the *source hash
    changes* and the write path is a real copy rather than a CoW clone. Measure
    the added session wall-clock on the M5 and confirm the receipt still
    publishes. Kill rule: **if the paired session grows by more than ~40 s, or
    any run times out, the entire offline-layout direction is dead** and we
    have bought that knowledge for one receipt instead of a round.

    **⚠️ DOWNGRADED — this direction is legally clear but scientifically
    unmotivated. Do not assign it.** The audit found an opportunity surface,
    not a lever, and since the audit its one candidate lever has been taken
    away. That lever was the **700.3 vs 968.4 GB/s marginal-rate deficit**
    (§9.4) — closing it on 552.1 MB/step of routed traffic would have been
    `552.1/700.3 = 788 µs` falling to `552.1/968.4 = 570 µs`, i.e. **218 µs =
    +3.19%**, larger than the entire remaining byte-removal ceiling. Three
    things killed it as a transform target:
    - The deficit is **not statistically established** (both planes n=1, CIs
      [773.6, 1294.6] and [493.1, 1207.9], overlapping on 83.4% / 60.8% of
      their mass — see the second downgrade under §9 direction 4).
    - The two *layout* explanations were tested and **refuted**: H-a address
      alignment (A = 1.000) and H-d two disjoint streams (the walk-order packed
      bank already ships, default ON). What survives — H-c wave quantisation
      at M=1 and H-b gather indirection as *serial latency* — are **online,
      runtime-side** mechanisms. An offline re-layout cannot reach either.
    - Within-tensor code/scale interleave was already closed (§8).

    So the surface is real and the legality argument above stands, but there is
    currently **no transform-side mechanism that would use it**. Revive only if
    someone brings an actual lever; the null-layout probe above remains the
    correct Step 0 *if* that ever happens, and is not worth a receipt before
    then.

    **Cheap side-benefit, worth taking whenever someone is in that module:**
    deleting the ~32 KB of Laguna-dead sidecar coders would lift global surface
    headroom from 73,089 B to ~105,000 B (+44%). It does **not** relieve the
    binding constraint, which is the 57,121 B remaining inside
    `LagunaRuntimeModel.swift`, and it requires also removing the `.gemma4`
    branch that calls them — check `Tests/MLXFastTests/TransformTests.swift`
    first.

---

## 10. Open programme issues

- **Submission lifecycle — CURRENT RULE (supersedes `bdb77bb0`).** Commit
  **`55ab1b2`** on `main`, "Let submitters manage validation retries" (mmcguire,
  2026-08-06 21:28:52 UTC), rewrites `senpai/program.md` §5. It is propagated to
  every branch (advisor `ad57f32`, fern `f13d659`, frieren `c5c8c6d`,
  nezuko `1a014f5`). The previous "queue owner / once-per-ten-minutes" model in
  `bdb77bb0` is **retired**; do not apply it. What is in force:
  - **There is no queue owner and no queue manager.** Any authorised advisor,
    student, or human operator holding a committed, preflighted candidate may
    dispatch, and **owns that candidate's submission lifecycle end to end,
    including retries**. Never wait for another agent's permission and never
    hand a candidate off.
  - If validation capacity is occupied: preserve the exact commit and note, keep
    doing useful work, recheck periodically **without a tight polling loop** and
    never sooner than the server's own retry guidance, then retry the
    *identical* `mlxfast submit --model "senpai"`.
  - **Before retrying after a timeout or ambiguous response, first check whether
    the first request already created a submission.**
  - "Capacity occupied" is **not** a rejection and carries **zero** information
    about the candidate. Never fall back to another `--model` value for a
    capacity, timeout, network, or validation condition — the campaign fallback
    is authorised **only** on an explicit rejection of `senpai` as a model
    value, and must then be recorded in the public note.
  - The **~35 min per-receipt price is retired and un-remeasured.** Every
    dispatch must record dispatch time, first "occupied" response, admission
    time and receipt time so the programme can rebuild that constant.
  - Operator broadcast `<!-- senpai-submission-lifecycle-correction:v1 -->` was
    posted to PR #137 and PR #148 at 2026-08-06T21:32Z. That notification item
    is **discharged**; round-24 assignments carry the rule in their body.
- The prior blocker text is retained for provenance: there is still **no typed
  transition to open a new GitHub issue**, so cross-campaign coordination
  continues to require a human operator. `bdb77bb0` is the precedent for how
  that arrives — as a commit to `senpai/program.md` on the advisor branch,
  surfaced to me as a `baseline_advanced` event. **Always diff an unexplained
  `baseline_advanced` SHA before assuming it is machine noise.**
- **`gh` CLI has no token** in the advisor shell, by design. All GitHub
  mutation goes through typed transitions. Field notes on their required fields:
  `create_assignment` needs `revision_id` **and** `expected_base_sha`, and uses
  `head_branch` (not `branch`); `send_assignment_feedback` needs
  `expected_head_sha`, must **omit** `student`, and is **refused unless the PR is
  `status:wip`** — so post review feedback *before* a student flips to
  `status:review`, or carry it into the next assignment body (as was done for
  #142 → #148 §9); `push_branch` needs both `expected_head_sha` and
  `expected_remote_sha`; `request_revision` takes
  `pr_number, assignment_id, expected_head_sha, revision_id, comment` and flips
  the PR back to `status:wip` — which is also how to re-open the feedback
  channel on a PR that has already gone to review; `merge_experiment` takes
  `pr_number, assignment_id, expected_head_sha, accepted_base_sha, merge_method`
  and has **no `reason`/`body` field** (`close_experiment` does take `reason`).
  Multiple distinct `feedback_id`s per revision are accepted.
  `git ls-remote origin 'refs/heads/...'` works without a token and is the
  cheapest way to see whether a student has pushed.
- **Delegation:** prefer **leaf** agents (`explore`, `search`, `bash-runner`)
  for research. `general-purpose` children that spawn their own helpers have
  repeatedly died with "uncollected descendants". Two leaf agents closed H5 this
  session at zero cost. A `frontier` / `general-purpose` child with
  `include_context=false` **does** complete cleanly when it is explicitly told
  not to spawn sub-agents — that is how to buy a fresh structural critique.
- `rg` is **not installed** on the advisor host; use `grep -rn`.
- Merges may return "mergeability unknown"; this is transient and resolves
  after a few minutes. Retry rather than working around it.
- Cascading `baseline_advanced` events are normal when merging several PRs in
  a session; supply `accepted_base_sha` explicitly.
- A **post-merge cleanup PR** is owed as soon as an arm actually ships bytes
  (prune stale experiment flags and dead paths; make the winning behaviour the
  single clear main path).
- Owed to students from #101/#103: the 7.86 → 5.5296 MB/step correction is
  recorded above; the shadow-execution re-audit (§4) is open; the D5
  golden/harness-hash receipt is satisfiable by a no-op because `harnessHash()`
  excludes `research/`; the MDE floor is now explicitly ±0.73%.

---

## 11. Round-26 frontier hypothesis slate (H1–H9)

Produced 2026-08-07 by a context-free frontier agent given only the budget
framing (decode/prefill split, byte inventory, score elasticities) and the
public repository. It had **no** campaign history, so read §11.10 before
assigning any item: four of its premises are wrong or already cashed.

### 11.0 The organising claim

Decode measures 4.144 ms/step against a 2.94 ms byte floor (1794 MB / 614 GB/s
on M5). That leaves **1.204 ms of non-byte time**. The three in-flight PRs
(#204, #205, #148) between them claim only ~230 µs of it. The remaining ~1.0 ms
spread over 406 decode dispatches is ≈2.5 µs/dispatch — which is almost exactly
the attention per-call fixed cost measured in #196 (`a = 1.661 µs`) plus one
wave (`φ = 1.469 µs`).

⛔ **REFUTED 2026-08-07 by PR #204.** The theory this section originally
advanced — *"the residual is per-dispatch fixed cost, and the unpulled lever is
fewer/fatter dispatches"* — is dead. Fern deleted 39 decode dispatches per step
in a controlled ABCCBA design and measured `−0.9 ± 12.1 µs`, 95% CI ≈
[−32, +30], against a census prediction of −105…−185 µs. `T = a + W·φ` is a
**throughput-slot upper bound**, not a marginal cost.

**Replacement organising claim: the residual is *exposed critical-path
duration*, and the only decode dispatches worth deleting are chain-links.** A
chain-link is the sole occupant of its barrier-bounded interval; a side-branch
is issued inside a much larger sibling's concurrency interval and is therefore
free. Use the **static side-branch predicate** — *X is a side-branch iff every
consumer of X also transitively depends on a sibling Y with duration ≫ X, where
Y is issued no later than X* — to pre-register a per-target verdict off the
Swift dataflow before any GPU work, and confirm it with the #204 §7
duplicate-injection sweep. The consequence for this slate is that
work-*reduction* inside a chain-link kernel (H7, #205) and genuine
critical-path or gap recovery (H1, H9) survive, while dispatch-*count*
reduction (H2, H4) is demoted until a chain-link verdict is shown.

Conversion constants (**corrected 2026-08-07** — the 512-token seed prefill is
inside the scored decode window, `D = (S + 128·T)/128`): **1 µs removed from
per-step `T` = +0.015280% score**, so 1% of decode (41.4 µs) = **+0.633%**; **1
ms removed from the 512-token prefill wall `S` = +0.374750% score**, so 1% of
prefill (0.979 ms) = **+0.367%**. The older `0.2554 %/ms` and `0.0181 %/µs`
constants used elsewhere in this section are retired; every figure below has
been restated.

### 11.1 H1 — decode-step gap taxonomy ⭐ DECISION NODE

Three distinct sinks are currently conflated: (a) inter-dispatch gaps inside a
command buffer, (b) the step-boundary bubble, (c) exposed small-kernel
duration. Everything we have closed only killed remedies for (a).

If (b) is large — 89% GPU utilisation implies ≈456 µs idle per step, and
teacher-forced stepping forces a CPU round trip per token while MLX rebuilds
and re-encodes a ~406-node lazy graph in Swift — then the fix is host-side, in
editable Swift: GPU-side argmax with a 4-byte copy (first check it is not
already a 200–400 KB logits copy plus a dtype convert), precomputed masks and
position tensors instead of per-step `MLXArray` slicing churn, and node-count
reduction.

Magnitude: a boundary bubble of 150–400 µs; recovering two thirds is
**+1.8–4.8% score**.

First experiment: one timeline capture over 3–5 consecutive decode steps
reporting (1) last-kernel-end → first-kernel-start gap per step, (2) the sum of
inter-dispatch gaps, (3) per-kernel exposed durations sorted descending.
Kill criterion: boundary gap < 30 µs **and** gap sum < 300 µs.

This prices H2, H3, H4, H7 and H9 exactly, and is the cheapest thing on the
slate.

### 11.2 H2 — merge the shared expert into the routed gather as a 257th expert

The shared expert is 2048→512→2048: identical geometry to a routed expert. Yet
it is read every layer as ~1.77 MB through 2 small GEMV dispatches (~69 MB per
step). At load time — input-independent, therefore allowed — append its
up/gate/down slabs to the expert bank and extend the routing key array with a
forced 9th entry of weight 1.0. The MoE block then goes from 4 to 2
weight-streaming dispatches per layer.

Magnitude: ~6.9 → ~2.9 µs/layer ⇒ ~4 µs × 39 = ~155 µs; census-priced at
120–200 µs = +1.83–3.06% at the corrected decode elasticity.

⛔ **BADLY DEMOTED 2026-08-07 (#204 + #174).** The kernel this hypothesis
deletes, `shared_nvfp4_swiglu_qmv_rows1`, is one of the exactly three decode
kernels #174 measured at exposure **`E = 0.10 [0.00, 0.25]`** — it is a
textbook side-branch, hidden behind the routed weight-streaming GEMV. Applying
that exposure, the honest value is **≈+0.18–0.31%**, not +1.8–3.1%. Do not
assign this as a fusion until the #204 §7 duplicate-injection sweep returns a
non-zero marginal slope for that specific kernel.

First experiment (if revived): runtime-only prototype (repack at load, force
the 9th key) plus tripwire plus upstream equivalence plus timing; 1–2 days.

Risk: summation order. The reference computes the shared and routed sums
separately and then adds them; a fused epilogue must accumulate the routed
experts in reference order and add the shared row exactly where the reference
adds it. Confirm the shared expert uses the same SwiGLU epilogue, else carry a
per-row flag.

This is **not** expert reordering, **not** up/down fusion, and a different and
larger idea than §7 R2 (the prefill-only shared-expert SwiGLU epilogue worth
+0.040%).

### 11.3 H3 — fold `g_proj` + sigmoid gate into the O-projection prologue

`g_proj` is a 2048×64 GEMV, ~74–170 KB, so ~95% of its cost is fixed, and it
runs 40× per step. The closed experiment merged it into **QKV** and lost (it
serialised two concurrent big streams). This folds it into the **other** side.

O-proj already consumes `sigmoid(g) ⊙ attn_out`. In the O-proj prologue one
simdgroup computes the 48–64 gates from the normed hidden (64×2048 MACs, noise
inside a 9–17 MB stream), barriers once, and gates the input vector in
threadgroup memory.

Magnitude: (2.3 + 1.8 − 1.0) × 40 ≈ **90–120 µs = +1.6–2.2% score**, halved if
the gate-apply is already fused.

Risk: sigmoid bit-match (copy the reference exp/divide verbatim); the prologue
dot product must replicate the standalone quantized-GEMV accumulation order.

### 11.4 H4 — systematic absorption of the remaining elementwise dispatches

There are 3–5 pure-elementwise launches per layer (norm1, norm2, RoPE if it is
not already an epilogue, residual adds), each ~1.8–2.5 µs and fully exposed.
Epilogue fusions — RoPE on Q/K, residual add on O and on the down output — are
bitwise-trivial. Norm-*prologue* fusion is bitwise-achievable only by
dedicating one simdgroup to reproduce the reference reduction tree exactly and
then broadcasting, so **do the norms last**.

Magnitude: 3 × 2 µs × 39 ≈ 230 µs gross; census-priced at 120–200 µs =
+1.83–3.06% at the corrected decode elasticity.

⚠️ **SERIOUSLY DAMAGED 2026-08-07 (#204).** This hypothesis prices every
absorbed dispatch at its census duration, which is exactly the model #204
refuted: 39 deleted dispatches bought `−0.9 ± 12.1 µs`. Worse, the census row
for `rmsbfloat16` (1.82 µs/call) sits *below* the fitted single-TG floor
`a + φ = 3.13 µs`, which is impossible under additive per-kernel costs — the
census is internally inconsistent for exactly this class of small elementwise
kernel. **Re-scope: H4 may only target dispatches that pass the static
side-branch predicate as chain-links**, and each target must first show a
non-zero slope in the #204 §7 duplicate-injection sweep. The "shrinks host
encode time" argument is also weakened: host encode is only on the critical
path when the front-end saturates.

First experiment: the marginal-cost ledger, not a fusion. Only after a target
shows a real slope should a fusion kernel be authored; stop when the measured
marginal gain falls below 20 µs.

### 11.5 H5 — make lm-head screening prune payload bytes

The lm-head costs 134.9 MB per step (full NVFP4 is 115.6 MB plus ~19 MB of
structure), so on its face every row still streams. The argmax identity permits
any *provably sound* pruning.

Offline transform emits per-row column-block norms (for Cauchy–Schwarz tail
bounds) plus a contiguous hot list of ~4K high-prior tokens. Online: (1) score
the hot list exactly (4.7 MB) to seed a high running max; (2) take partial dots
over the first k = 512 columns (28.9 MB) with the tail bound
‖w_i[k:]‖·‖h[k:]‖ inflated by a rigorous float-error term; (3) fully rescore
the survivors.

Magnitude: at 1–5% survivors ≈ 38 MB, so ~97 MB saved ≈ 158 µs =
**+2.9% score**, all of it on the serial step tail.

First experiment (free): read the existing screening code and log the achieved
prune rate and the bytes actually read over real decode steps. If it already
prunes payload reads, H5 is dead. Then run a CPU-side bound-tightness
simulation on recorded hidden states before touching Metal.

Risk: the soundness proof must be against the kernel's *float* arithmetic; flat
logit tails gut the prune rate; the two-phase structure adds ~3 µs.

### 11.6 H6 — prefill gather-GEMM instruction diet via offline plane separation

If the gather GEMM is issue/schedule-limited (θ = 0.67 with both rooflines at
67% hints at exactly this), attack instruction count where Apple GPUs pay:
64-bit adds (4 ops) and dynamic bitfield extracts (8–12 cycles).

De-interleave NVFP4 offline into a payload plane and a scale plane so that
payload rows are exactly 1024 B and expert payload slabs exactly 512 KiB —
power-of-two everything — collapsing inner-loop addressing to one 64-bit
per-threadgroup base plus 32-bit shifted offsets. De-interleave the nibbles
into low/high planes so per-element dynamic extracts become two static
mask/shift ops per 8 weights. Decode the fp8-e4m3 scales with the 3-op
bit-shift-to-fp16 identity (the offline transform validates that no denormal or
NaN scales occur and records it in metadata) instead of a memory LUT. Bake trip
counts and strides as compile-time constants in editable `jit_kernels.cpp` and
unroll 4 groups.

Magnitude: the routed gather is ≈1.0 TFLOP / 23.2 TFLOP/s ≈ 43.3 ms; θ from
0.67 → 0.75–0.78 gives 37–39 ms, so prefill 91.8–93.5 ms = **+1.1–1.6% score**
(up to +3% at the top of the range).

**Do NOT adopt fp16 scale planes**: +11% expert bytes ≈ +100 µs decode, and a
dual plane is 3.92 GB against 3.65 GB of inventory headroom.

First experiment: await #170's instruments; in parallel pull the compiled inner
loop's instruction mix from an Xcode GPU capture. If unpack + address ops are
under 25% of issue slots, or issue utilisation is already above 85%, it dies.

Risk: the layout change also touches decode's 89–98%-efficient GEMVs.

This is the same idea as surviving round-25 frontier item 6 (raise θ), now with
a concrete mechanism.

### 11.7 H7 — attention-kernel issue diet: skip the softmax rescale when the max is unchanged

The decode attention kernels are issue-bound (~350–450 µs/step from 40 calls ×
[1.661 + waves×1.469 + N×0.748 µs] against only ~138 µs of KV bytes). In online
softmax the accumulator rescale factor is exactly 1.0 whenever the running max
does not update — which is almost always after the first few KV blocks.
`x·1.0` is bitwise `x` for all finite values, so a **simdgroup-uniform** branch
that skips the rescale multiplies (and the exp of 0) is bit-exact and
divergence-free. Add compile-time specialisation of KV strides and window
sizes.

Magnitude: ~0.10–0.15 µs × ~9 iterations × 40 calls ≈ 40–55 µs plus 20–40 µs
from specialisation ⇒ **60–95 µs = +1.1–1.7% score**, compounding with #205.

First experiment: instrument one kernel with a counter of max-update frequency
per simdgroup; half a day. Kill: updates in more than 30% of iterations, or the
rescale is under 10% of loop instructions.

### 11.8 H8 — prefill dense-projection NAX efficiency audit

Dense attention projections are ≈1.46 TFLOP of prefill — *more FLOPs than the
routed gather* — yet only the **gather** tile geometry has ever been swept. If
the `_nax` dense path runs at 40–45 TFLOP/s on tall-skinny shapes (M = 512,
N up to 10240) rather than 52–60, several ms sit in tile/stage tuning of
editable `matmul.cpp` plus the kernel sources.

Magnitude: 1.46 TFLOP at 45 → 55 TFLOP/s is 32.4 → 26.5 ms ⇒ ~6 ms of prefill ≈
**+1.6% score**. Dead if it is already ≥52 TFLOP/s.

First experiment: compute achieved TFLOP/s per dense matmul family from the
existing prefill timeline instruments.

Risk: M5-only, so all tuning must happen on the M5 box.

### 11.9 H9 — commit-granularity sweep in the *increasing* direction

"Fewer CBs is 10% worse" is a one-sided result: CB boundaries currently *help*
pipelining. The untested direction is *more* and *earlier* commits at strategic
points (for example after each layer's attention) from editable Swift eval
boundaries.

Magnitude: 30–80 µs = +0.5–1.4%.

First experiment: sweep 3–4 split placements in an afternoon on M5 against a
fresh paired baseline. High chance of flat or negative; worth it only because
it is nearly free and probes the same pool H1 maps.

### 11.10 ⚠️ Advisor caveats — apply these before assigning any of the above

1. **`mx::set_wired_limit()` is already shipped** (`LagunaRuntimeWeights.swift`
   `:546-598`, M5-only, gated at ≥96 GiB). Any proposal that assumes it is an
   available lever is already cashed.
2. **H5's "lm-head still streams every row" is in doubt.** §5.4 records
   `lmhead_int5_base_coarse_delta` at 427.0 µs/step and a certified screening
   cascade already exists ("certified lm-head screening" is on the closed
   list). H5 must **first** re-verify the achieved prune rate and the bytes
   actually read.
3. **H3 carries a real hazard the agent could not know.** PR #48 measured the
   QKV-side variant at −0.1488% on the ranked M5 (receipt `285f79fa`), and #174
   §2.6 shows `gate_sp_h64` / `gate_sp_h48` are among the **only three kernels
   that hide** (E = 0.10). Folding them may *expose* work that is presently
   free. H3 must open with an exposure measurement, not a fusion.
4. **H7's per-call constants come from #196 and are M4 Pro measurements at 1024
   threads/TG.** The model form (`T = a + W·φ + work`) is right; the numbers are
   host- and geometry-specific.

### 11.11 Sequencing

1. Run **H1 first**. It is the decision node, costs about a day, and prices H2,
   H3, H4, H7 and H9. Students have no M5 shell, so the realistic form is an
   M4-side timeline capture — the `kernelStartTime()` / `kernelEndTime()` plus
   `CLOCK_UPTIME_RAW` instrument upgrade sketched in §9a, living as a `.patch`
   under `research/` — together with a receipt-side check.
2. H2 + H3 + H4 together plausibly claim 300–450 µs of the ~1.0 ms gap. Expect
   sub-additivity: measure each alone, one mechanism per submission.
3. The offline transform is the quiet enabler in three places (H2's bank
   append, H5's sketches and hot list, H6's plane split), all
   additive-inventory-compatible and inside the 3.4 GiB headroom **except the
   rejected fp16 scale plane**. §9 item 12 (output re-layout) was downgraded for
   lack of a mechanism; H2 and H6 supply new mechanisms, which is a legitimate
   revival under §0a row 7.
4. Everything here preserves bitwise activations by construction
   (order-preserving fusion, ×1.0 skips, layout-only changes, provable bounds).
   Route every candidate through `research/run_upstream_equivalence.sh` and the
   64-step drift tripwire before any timing.
