# RESEARCH IDEAS — steel_gemm_bf16 prefill excess (12.30 ms projection / 11.40 ms M5 residual)

Frontier-consultant analysis, 2026-08-08. Sources: census
`research/maple-tanjiro-nonmoe-prefill-census.md` (PR #270 head; not on this
branch — fetch via `refs/pull/270/head`), `research/CURRENT_RESEARCH_STATE.md`
§4.13/§5, and direct source verification of
`Vendor/mlx-swift/Source/Cmlx/mlx/backend/metal/matmul.cpp`,
`.../steel/gemm/kernels/steel_gemm_fused_nax.h`, `.../gemm_nax.h`, and
`Sources/MLXFastModel/LagunaRuntimeModel.swift`. All M5 routing and occupancy
claims below are **predicate-derived from source, not measured on an M5**;
60 TFLOP/s BF16 peak and 40 GPU cores are working assumptions.

Budget frame (census): official M5 prefill S = 97.895 ms; MoE gather-GEMM
W = 43.262 ms; non-MoE R = 54.633 ms. steel_gemm_bf16 projection A =
**37.93 ms** vs a 100%-of-peak analytic floor of **25.63 ms** → headroom
**12.30 ms**. Projection B (hold M4-measured kernel-family efficiencies,
scaled to M5 peak) totals 86.50 ms vs actual 97.895 → **11.40 ms M5-specific
residual**. Score sensitivity ≈ 0.375 %/ms of prefill; statistical floor for
one paired run ≈ 1.35 ms (3σ, σ_Δ ≈ 0.45 ms).

**Headline reconciliation (do not double-count):** the 12.30 and 11.40 are
mostly the *same* milliseconds. 37.93 − 28.6 (steel at M4-held efficiency)
≈ 9.33 ms of the 11.40 residual sits inside steel; the remaining ~2.97 ms of
the 12.30 is the 100%→87.5-89.5% peak margin, which is largely unrecoverable.
The other ~2.1 ms of the 11.40 lives in attention_core (~1.2) and
nvfp4_dense_qmm (~0.85), out of scope here. **Realistic recoverable ceiling in
steel ≈ 9–10 ms, concentrated in the tiny-N tail; central expectation for the
hypotheses below ≈ 3–6 ms.**

---

## 1. What steel_gemm_bf16 does in the 512-token prefill

Per-prefill GEMM inventory (census §3.2 M4 dispatch log, routes re-derived for
M5 from `matmul.cpp` predicates; BF16 = 2 B/elem; AI = FLOP/byte;
floor = GFLOP_total / 60 TFLOP/s):

| class | (M,N,K) | count | GFLOP total | AI | floor ms | M5 route (derived) | TGs/disp (TGs/core) |
|---|---|---|---|---|---|---|---|
| wq slide + dense gate/up | 512,8192,2048 | 31 | 532.6 | 390 | 8.88 | regular NAX bm64 bn128 bk256 | 512 (12.8) |
| wo slide + dense down | 512,2048,8192 | 30 | 515.4 | 390 | 8.59 | **NAX split-K** (K≥3·max), darkbloom tile 64/64 BK512 parts2 | 512 (12.8) |
| wk+wv | 512,1024,2048 | 78 | 167.5 | 293 | 2.79 | **regular NAX** (fails split-K tie: K=2048 not > 2·1024) bm64 bn128 bk256 | **64 (1.6)** |
| wq full | 512,6144,2048 | 10 | 128.8 | 385 | 2.15 | regular NAX | 384 (9.6) |
| wo full | 512,2048,6144 | 10 | 128.8 | 385 | 2.15 | NAX split-K | ~384–512 |
| router | 512,256,2048 | 38 | 20.4 | 157 | 0.34 | NAX split-K (bm/bn 64, parts2) | **64 (1.6)** |
| g_proj slide/full | 512,{64,48},2048 | 39 | 4.9 | ~55 | 0.08 | NAX split-K | **16 (0.4)** |
| [K;V] bank L39 | 512,2048,2048 | 1 | 4.3 | 341 | 0.07 | regular NAX | 128 |
| **total** | | 237 | **1502.7** | | **25.05** | | |

(Census's own floor partition sums to 25.63 ms; the ~0.6 ms delta vs this
table is classification rounding, immaterial.)

Structure of the problem:

- **Head classes** (wq/wo/dense, 81 dispatches, 1309.9 GFLOP, 87% of work)
  have AI ≈ 390 and 380–512 TGs per dispatch — they are compute-bound and
  well-shaped for 40 cores. At M4-held efficiency (regular 89.5%, split-K
  67.7–87.5%) they cost ≈ 24.4–28.3 ms.
- **Tail classes** (wk/wv + router + g_proj, 155 dispatches, 192.8 GFLOP, 13%
  of work) land at **64/64/16 threadgroups per dispatch = 0.4–1.6 TGs/core**.
  Census §4.4 brackets: tail at 87.5% eff = 3.7 ms; at 15% = 21.4 ms.
- Fitting A = 37.93: with heads at optimistic efficiency (24.7 ms), the tail
  implicitly runs at ≈ **24% of peak ≈ 13.2 ms actual vs 3.2 ms floor**; with
  wo pessimistic (67.7% split-K → 28.3 ms heads), tail ≈ 9.7 ms (33% eff).
  Either way, **6.5–10.3 ms of the 12.30 sits in the tail**, dominated by the
  78 wk/wv dispatches; the wo split-K class holds another 1.5–5.1 ms.

Prefill is strictly serial on-GPU (census: SPLIT=0 sum ≡ union on M4), so any
dispatch removed or sped up converts ~1:1 into prefill ms.

## 2. Root-cause candidates, ranked by explanatory share of the 12.30 ms

1. **Tail occupancy starvation on 40 cores (~55–85%, 6.5–10.3 ms).**
   wk/wv (512,1024,2048) fails the NAX split-K tie `K > 2*max(M,N)` exactly
   (2048 vs 2·1024) at `matmul.cpp:988-991` and takes the regular-NAX path,
   whose tile choice for devc 's' (`matmul.cpp:227-238`: bm=64, wm=2,
   bk=256) yields an 8×8 = 64-TG grid — 1.6 TGs/core cannot fill 40 cores'
   SIMD pipelines. Router (64 TGs) and g_proj (16 TGs) are worse per-dispatch
   but small in GFLOP. On M4 (10 cores) the same shapes route to *non-NAX
   split-K with 1024/256/128 TGs* — this is why the M4 census measured the
   tail as healthy and why the deficit is M5-specific.
2. **wo-class NAX split-K route (~12–40%, 1.5–5.1 ms).** wo/dense-down
   (K≥3·max) migrates *into* split-K on M5 (it is regular on M4). Cost: an
   extra FP32-partial write+read round trip (~654 MB ≈ 1.2 ms at DRAM bw)
   plus whatever efficiency split-K loses vs regular (M4 measured split-K at
   67.7% vs regular 89.5%). The already-merged `darkbloom_steel_prefill_tile`
   regroup (`matmul.cpp:87-94`, applied at :718) raised the grid from 128 to
   512 TGs; whether census projection A includes its benefit is uncertain.
3. **Peak-margin (~20–25%, ~2.5–3.0 ms) — unrecoverable.** The floor assumes
   100% of 60 TFLOP/s; the best kernels measured anywhere in this family
   reach 87.5–89.5%. This slice of the 12.30 is definitional, not a defect.
4. **Dispatch/launch boundaries (alternative attribution of #1, not
   additive).** 155 tail dispatches at O(10–30 µs) apiece ≈ 1.5–4.6 ms;
   the measured M5 command-buffer marginal is 27.2 µs/CB × 81 CBs ≈ 2.2 ms,
   accounted separately under glue. Removing tail dispatches (H1) collapses
   both attributions at once.

## 3. Prioritized hypotheses

### H1 — Ship the fused QKV bank for prefill, then extend to [Wq;Wk;Wv;Wg] (census F1 Steps 0+1) — TOP PICK

- **Mechanism.** `DARKBLOOM_FUSED_QKV` already exists
  (`LagunaRuntimeModel.swift:112-114`, default OFF;
  `prepareFusedQKVWeight()` :5590-5610; prefill-only use :5881-5896). It
  folds all 78 wk/wv dispatches into the wq GEMM: (512, 10240, 2048) regular
  NAX → tn=80, tm=8 = **640 TGs (16/core)**. The 167.5 GFLOP tail rides at
  head-class occupancy; 78 dispatch launches disappear. Step 1 adds g_proj
  rows ([Wq;Wk;Wv;Wg], N=10304/10288) at the same use site, deleting 39
  16-TG split-K dispatches + their FP32-partial accum passes (precedent:
  `prepareLastPrefillProjectionWeights()` :5612+, the [K;V] bank).
- **Anchors.** `LagunaRuntimeModel.swift:108-114, 5590-5610, 5881-5896,
  5612+`; route predicate `matmul.cpp:957-991`; tile select :227-238.
- **Predicted saving.** Step 0: −1..−7 ms, central **−3 ms** (wk/wv actual
  ~9–13 ms → rides along at ≈ +2.8 ms marginal inside the enlarged wq
  dispatch). Step 1: −0.3..−1.5, central −1. Family central ≈ **−4 ms ≈
  +1.5% score**. Well above the 1.35 ms noise floor.
- **Bit-exactness.** On M5: **yes** — wk/wv and wq already run the *same*
  regular-NAX kernel with the same bm64/bk256 tiling; row-concatenation only
  changes which TG owns which output columns while each output element keeps
  its k-ascending MMA chain (exactly the accepted darkbloom-regroup argument,
  `matmul.cpp:87-94`; also documented at the use site :5884-5890). On M4 the
  route for wk/wv changes (split-K → regular) → LSB drift possible *locally
  only*; use the documented golden-drift policy for local equivalence.
- **Byte cost.** Step 0 ≈ 0–0.2 KB (default flip, keep env kill-switch);
  Step 1 ≈ 2–3 KB. Headroom 49,145 B — fits easily.
- **Cheapest falsifiers.** (a) Static predicate replay of the fused shape —
  done here: regular on both hosts (M5: NAX 640 TGs; M4: non-NAX regular).
  (b) Local M4 run with `DARKBLOOM_FUSED_QKV=1`: upstream-equivalence +
  greedy goldens (drift policy) + dispatch census showing −78 steel
  dispatches. M4 *timing* is expected neutral-to-slightly-negative and is
  NOT evidence against the M5 gain (on M4 the flag removes an *efficient*
  1024-TG split-K; on M5 it removes a *starved* 64-TG regular — the census's
  key argument for why the shipped-OFF ablation doesn't transfer).
  (c) One ranked M5 submission of Step 0 alone — doubles as the tail-share
  measurement of §4.
- **Kill criterion.** M5 paired receipt Δprefill < +0.3% (< ~0.8 ms) →
  tail-occupancy explanation is wrong; close the family and pivot to H4.

### H2 — Skinny-N tile downsize for regular NAX (fallback / complement to H1)

- **Mechanism.** In the devc-'s' regular-NAX tile selection
  (`matmul.cpp:227-238`), when the resulting grid would be < ~2 TGs/core
  (e.g. N ≤ 1024 at M=512), choose a smaller tile to multiply TG count:
  verified-legal options per `gemm_nax.h:35-37` constraints (SM=BM/WM ≥ 16;
  TN=SN/16 even or 1): bm64/bn64/wm2/wn2 → SM32/SN32/TM2/TN2, 128 TGs;
  bm32/bn128/wm2/wn4 → SM16/SN32/TM1/TN2, 128 TGs; combined bm32/bn64 →
  256 TGs. Applies to wk/wv (if H1 cannot ship) and any future skinny-N
  shape; does not touch head classes.
- **Anchors.** `matmul.cpp:200-345` (esp. 227-238);
  `steel/gemm/kernels/steel_gemm_fused_nax.h:80-200`; `gemm_nax.h:35-37`;
  JIT twin `mlx-generated/steel_gemm_fused_nax.cpp` (no source change needed
  for new template instantiations — host-side params only).
- **Predicted saving.** −1.5..−5 ms if H1 absent (same target set); ≈ −0.5..−1
  incremental if H1 ships (residual skinny shapes only). 
- **Bit-exactness.** **Yes** — bk stays 256, per-element k-order unchanged,
  only TG ownership regroups (darkbloom precedent). No FP32-partial pass is
  introduced.
- **Byte cost.** ~0.2–0.4 KB in `matmul.cpp`. Editing anything under
  `Cmlx/mlx` fires `VendoredMetalFingerprint.swift:19-21` → run
  `tools/build-mlx-metallib.sh` once (setup cost, not scored bytes).
- **Cheapest falsifiers.** (a) `research/nax_msl_compile_check.sh` offline
  MSL compile + pipeline-stats for each candidate tile proving non-empty MMA
  (the known NAX failure modes are odd TN>1 and SM<16 — both excluded
  statically above, but prove it). (b) There is NO local dynamic test: M4
  never selects `_nax` (gen 16) and `MLX_METAL_NO_NAX` is unreachable via
  SwiftPM — first dynamic evidence is a ranked M5 run.
- **Kill criterion.** MSL check shows empty-MMA/fallback for the chosen tile,
  or ranked Δprefill < +0.3% when H1 is absent.

### H3 — Flip the split-K tie for wk/wv (`K > 2*max` → `K >= 2*max`)

- **Mechanism.** One-token edit at `matmul.cpp:989-991` routes wk/wv to NAX
  split-K: parts2 → 16·8·2 = 256 TGs (6.4/core). Higher occupancy than
  today's 64, but adds an FP32-partial write+read ≈ 2×4.2 MB×78 ≈ 655 MB ≈
  +1.2 ms DRAM traffic, and split-K's measured family efficiency (67.7% on
  M4) is worse than regular's.
- **Bit-exactness.** **No** — route change inserts a separate FP32
  accumulation pass (different summation grouping). Greedy tokens *probably*
  survive but near-tie argmax flips are exactly the documented M5 risk.
- **Predicted saving.** −3..+1 ms (sign uncertain). Byte cost ~1–10 B. Must
  audit which *other* shapes sit exactly on K = 2·max before shipping.
- **Falsifier / kill.** Static shape audit first; then only a ranked run can
  price it. Kill on any golden/equivalence mismatch or Δprefill < +0.3%.
  **Dominated by H1/H2 (bit-exact, larger expected effect) — run only if both
  die.**

### H4 — wo-class route A/B: force regular for K≥3·max shapes (diagnostic)

- **Mechanism.** wo/dense-down (512,2048,{6144,8192}) currently takes NAX
  split-K (Case 2 first clause, `matmul.cpp:988-989`). Forced-regular would
  select bm64/bn128/**bk64** (the K≥8192 && K>M+N branch) → 128 TGs — lower
  occupancy but no FP32 round trip (−654 MB). Census F4 prices the traffic
  at ~1.2 ms; the efficiency sign is genuinely unknown post-darkbloom.
- **Bit-exactness.** **No** (route change, same caveats as H3).
- **Predicted saving.** −2..+2 ms; primarily worth running as the *second
  discriminator* for §4 attribution, not as a merge candidate on its own.
- **Falsifier.** Env-gated predicate override (~0.2 KB) + one ranked A/B.
  Kill on Δprefill ≤ 0 or any token mismatch.

### H5 — Raise split-K partition count for router (and g_proj if H1-Step-1 absent)

- **Mechanism.** `matmul.cpp:711-732`: K=2048 → partition_size 1024 → 2
  parts. Halving partition_size for tiny-grid cases → parts4: router
  4·8·4 = 128 TGs, g_proj 32 TGs. More partials but 2× occupancy.
- **Bit-exactness.** **No** — partial-sum boundaries move (accumulation
  regrouping across K). Small prize: router excess ≈ ~1 ms at 25% eff;
  g_proj mostly subsumed by H1 Step 1. Byte ~0.1 KB.
- **Falsifier / kill.** Same as H3: static audit + ranked run; kill below
  +0.3%. Rank last.

**Recommended sequence.** H1-Step-0 (bit-exact, existing code, one flag flip,
doubles as the key measurement) → H1-Step-1 → H2 for residual skinny shapes →
H4 as diagnostic if the receipts say the tail was not the story → H3/H5 only
on a plateau. H1+H2 combined central expectation ≈ −3.5..−5 ms ≈ +1.3–1.9%
score; hard ceiling for the whole family ≈ 9–10 ms.

## 4. The 11.40 ms M5-specific residual — what to measure

Decomposition (this analysis): ≈ 9.33 ms inside steel (the tail + wo-route
losses above) + ≈ 1.2 ms attention_core + ≈ 0.85 ms nvfp4_dense_qmm. It
overlaps the 12.30 almost entirely; do not budget them additively.

Measurement plan, cheapest first:

1. **H1-Step-0 ranked receipt** is the single most informative number: Δ ≈
   −3 ms confirms tail-starvation as the dominant term; Δ ≈ 0 falsifies it
   and re-points at wo/peak-margin.
2. **H4 ranked A/B** (env-gated) prices the wo-class split-K choice ±2 ms.
3. **No on-box M5 profiling channel exists in ranked runs** (`device.cpp` /
   `device.h` are not editable; no instrumentation may ship). If any M5 dev
   host is ever available, one Metal System Trace / MTLCounterSampleBuffer
   session over the 512-token window would settle the entire per-dispatch
   decomposition in an afternoon — worth requesting before spending multiple
   ranked slots.
4. Track the ~2.2 ms CB-boundary share (81 CBs × 27.2 µs) separately under
   glue; H1 removes dispatches, not CBs, so its receipt is not confounded.

## 5. What I could not determine, and what would settle it

- **No M5 timing ground truth.** Every route, TG count, and efficiency above
  is derived from `matmul.cpp` predicates + M4 measurements + assumed
  60 TFLOP/s / 40 cores. If real BF16 MMA peak is materially below 60
  TFLOP/s, part of the "excess" is definitional. Settled by: any M5
  microbenchmark of one (512,8192,2048) regular-NAX GEMM, or item 3 above.
- **Whether projection A (37.93) already includes the merged darkbloom
  regroup's benefit** on the wo class (changes H4's prior by ±2 ms). Settled
  by: comparing census run date vs merge date of the regroup, or one H4 A/B.
- **The devc arch branch on M5** ('s' inferred). Wrong branch changes tile
  numbers but not the starvation story (64 vs 128 TGs both starve 40 cores).
- **Metal JIT pipeline-cache behavior for new tile instantiations** (H2):
  first-use compile should land in unscored warmup; a cold-cache ranked
  penalty is possible but bounded. Settled by the MSL compile check + one
  ranked run.
- **Near-tie greedy-argmax stability** for the non-bit-exact options
  (H3/H4/H5) can only be proven on the M5 gate itself; local goldens are
  necessary but not sufficient. This is priced into their rank.
- The M4 ablation note "mild prefill cost" for `DARKBLOOM_FUSED_QKV`
  (`LagunaRuntimeModel.swift:110-114`) was never decomposed; the census
  attributes it to M4's efficient split-K being replaced. If that attribution
  is wrong, H1's central −3 shrinks. Settled by H1-Step-0's receipt (the
  kill criterion covers it).

**Honest bottom line.** Of the headline 12.30 ms, ~2.5–3 ms is peak-margin
and not recoverable by any routing/tiling change; the recoverable core is the
~6.5–10 ms tail-starvation + wo-route slice, and the two cheapest, bit-exact,
already-precedented levers (H1, H2) plausibly capture 3–6 ms of it. Anything
beyond that requires non-bit-exact route changes with genuine argmax risk and
should wait for the H1/H4 receipts.
