SENPAI-RESULT: {"terminal":true,"status":"complete","pending_arms":false,"wandb_run_ids":[],"primary_metric":{"name":"mma_shaped_qk_tile_kernel_time_delta_pct_k16","available":true,"value":3.400},"test_metric":{"name":"passed_correctness","available":false,"value":null}}

- Student / PR: maple-edward / #684 (`maple-r109-d-sliding-attn-qk-mma`, rev `r109-d-rev1`)
- Hypothesis and target cost: replacing the 8 `simd_sum` QK reductions in
  `laguna_sliding_fused_attn_ring_v1` with a `simdgroup_matrix` MMA tile removes
  the cross-lane reduction cost and speeds up decode. Advisor comment 3 fixed the
  budget: this kernel is **627.3 µs/step = 7.33% of decode busy**, and comment 4
  then closed the pricing constant at **0.0056 %score per M4 decode busy µs**, so
  the 0.378% gap to the leader needs **68 µs/step = a 10.8% harvest** off this
  pool. The preregistered stop rule was
  *if arm (b) does not beat arm (a) by ≥8% of kernel time, do not write the MMA
  kernel — post `N-ISSUE-BOUND` for the reduction and retarget to load geometry.*
- Decision: **dead hypothesis.** (b) − (a) = **6.86% at K=32 and 5.13% at the M5
  threadgroups-per-core ratio**, both below the 8% bar, so the rule fires; and
  independently the bit-exact MMA-shaped arm measures **slower than base in both
  occupancy regimes** (+6.05% / +3.40%). The load-geometry retarget the rule
  pointed at is also refuted by its own diagnostic (arm (c) vs the DRAM floor).
  The MMA kernel was **not** written.
- `BASE_SHA` / candidate commit: `1a6761bf46c282fcabd0577b618f0c1206757e6c` /
  see PR head. No submitted-surface file was modified.
- Submitted candidate files: **none.** Stage 0 was a measurement stage; the Stage 1
  kernel was not built because Stage 0 refuted it.
- Supporting test or documentation files:
  `research/edward-r109/STAGE0_VERDICT.md` (full write-up),
  `research/edward-r109/{make_qk_arms.py,census_qk_reduction.py,run_probe.sh,run_stage0.sh,run_stage0c.sh,run_stage0d.sh,run_stage0e.sh,run_stage0f.sh,mma_price.metal,mma_throughput.metal,mma_throughput.swift,probe_*.txt}`.
- Official submission `--model` value (planned or used; default `senpai`): n/a —
  nothing to submit; maple-fern is the submission driver for this round.
- Explicit API model-value rejection, if fallback attribution was required: n/a.
- Assignment-scope preflight: `senpai/validate-assignment-scope.sh` and
  `senpai/check-editable-budget.sh` run against
  `1bc1c8954147c9e322aad1f3b80bd9fa3c0888d7`; all changes are research-only under
  `research/edward-r109/`.
- Editable bytes / headroom / growth: submission surface **unchanged** (0 bytes of
  growth). `LagunaRuntimeModel.swift` remains 384,245 B of the 524,288 B per-file
  cap.
- Scored-path reachability evidence: `laguna_sliding_fused_attn_ring_v1` is
  declared at `LagunaRuntimeModel.swift:1504–1507`, dispatched at 1963–1972, and
  runs for the 30 of 40 layers with `layer % 4 != 0`; instrumented at 30 calls per
  decode step, per-call min 17.5–18.6 µs / p50 20.6–20.9 µs on this host.

### Evidence

- Host, memory profile, toolchain, and thermal policy: Apple **M4 Pro**,
  `applegpu_g16s` (arch gen 16), 20 GPU cores, 48 GiB (low-memory startup
  profile). Metal probes only; no `--local-iterate` run in this stage, so no
  thermal gate was involved. **All numbers are kernel-internal ratios on a gen-16
  host and are directional, never a ranked score.** Gen-16 hosts do not select
  the `_nax` kernels, but nothing here depends on `_nax`.
- Exact baseline and candidate commands: see §11 of
  `research/edward-r109/STAGE0_VERDICT.md`. Decisive sweep:
  `research/edward-r109/run_stage0d.sh null qk_pad4x_bcast0 qk_pad4x qk_bcast0 null`
  (`FERN_LADDER=32` = scored geometry, `FERN_REPS=200`, `FERN_ROUNDS=101`,
  `FERN_CACHE_COPIES=6`, `FERN_DEFEAT_SLOTS ∈ {64,1}`), supervised job
  `441a04a7-22e3-4ded-9717-5264ba8feae2`.
  The remaining supervised jobs:
  - `run_stage0d.sh null qk_bcast0 qk_loadonly null` — arm (c) at K=32, job
    `8055e34d-bade-4d15-af82-e0aab87116df`
  - `run_stage0e.sh` — absolute threadgroup ladder
    (`FERN_LADDER=4,8,16,20,32,40,64`, base kernel only, 31 rounds), job
    `e8022231-8a19-4aba-8d52-544ed938cfa8`
  - `run_stage0f.sh 16 null qk_bcast0 qk_loadonly qk_pad4x qk_pad4x_bcast0 null` —
    re-pricing at the M5 threadgroups-per-core ratio, job
    `cc71b9f1-3783-4001-9b43-4c26b3e8d781`

- Tests and risk-based checks run, including selected-test count: no numerical
  behaviour was changed on the scored path, so `LagunaUpstreamEquivalence` was not
  required and was not run. Probe validity checks instead: byte-identical `null`
  arms bracketing every sweep (**≤ ±0.19%** at `slots=64`, **≤ ±0.29%** at
  `slots=1`, versus effects of 3.4–11.8%), two residency regimes
  (`FERN_DEFEAT_SLOTS` 64 and 1), static instruction census on **both**
  `applegpu_g16s` and `applegpu_g17s`, and a bit-exactness construction for the
  decisive arms (`pad_ * zero_`, `zero_ = U(widx > 0x3fffffffu)`).
- Correctness and serial-protocol verdict: **not applicable** — no scored-path
  edit. The two decisive arms are bit-exact by construction; the diagnostic arms
  are deliberately incorrect and were never candidates.
- Divergent tokens or failure category, if any: none (no candidate run).
- Peak RAM or generated-weight size, if relevant: n/a.
- Official ranking status versus correctness/floor status, if submitted: not
  submitted.

**The three preregistered arms.** Paired A/B, `delta = arm − base` within a
round, **negative = faster**, `FERN_DEFEAT_SLOTS=64` (residency-defeated):

| arm | K=32 (M4 scored, 1.60 TG/core) | K=16 (M5 ratio, 0.80 TG/core) |
| --- | ---: | ---: |
| **(a)** current, `null` vs itself | +0.190% / +0.082% | −0.116% / −0.051% |
| **(b)** dummy-reduce `simd_shuffle(x,0)` (`qk_bcast0`) | **−6.857%** (t −39.7, sd 0.287) | **−5.134%** (t −121.9, sd 0.040) |
| **(c)** load-only, no reduce, no PV (`qk_loadonly`) | **−9.544%** (t −83.2, sd 0.215) | **−8.817%** (t −276.5, sd 0.030) |
| `qk_pad4x` (bit-exact 4× MACs = the M-padding bill) | **+11.802%** | **+10.200%** (t +258.6) |
| **`qk_pad4x_bcast0`** (MMA-shaped net) | **+6.047%** | **+3.400%** (t +90.7) |

`(b) − (a)` = 6.86% / 5.13%, **below the preregistered 8% bar in both regimes.**

Supporting arms at K=32 (`slots=64` / `slots=1`):

| Arm (sliding kernel only) | slots=64 | t | slots=1 | t |
| --- | ---: | ---: | ---: | ---: |
| `null` (byte-identical bracket) | −0.043% | | −0.290% | |
| `qk_free` (no reduce at all) | −6.849% | −50.6 | −7.050% | |
| `qk_bcast0` (earlier sweep) | −6.719% | −33.2 | −7.631% | −51.2 |
| `qk_ladder2` (W=8 tail) | −4.577% | | −4.677% | |
| `qk_quad_bcast` (W=4 tail) | −3.540% | −20.2 | −3.937% | |
| `qk_ladder5` (explicit 5-stage butterfly) | **+1.483%** | +12.9 | **+1.489%** | |
| `qk_pad4x` | **+11.802%** | +119.5 | **+11.801%** | +88.2 |
| `qk_pad4x_bcast0` | **+6.047%** | +24.4 | **+3.239%** | +19.8 |
| `null` (byte-identical bracket) | +0.019% | | +0.076% | |

**Absolute threadgroup ladder** (base kernel only, slots=64, 31 rounds × 200
reps) — this is what makes the K=16 column the M5-relevant one:

| K | TG/core | base µs | µs/K | φ = t(2K)/t(K) |
| ---: | ---: | ---: | ---: | ---: |
| 4 | 0.20 | 8.84 | 2.2097 | 1.0506 |
| 8 | 0.40 | 9.29 | 1.1608 | 1.0168 |
| 16 | 0.80 | 9.44 | 0.5901 | 1.9706 |
| 20 | 1.00 | 9.66 | 0.4832 | 1.9867 |
| 32 | 1.60 | 18.61 | 0.5815 | 1.8403 |
| 40 | 2.00 | 19.20 | 0.4800 | — |
| 64 | 3.20 | 34.24 | 0.5350 | — |

`t(K)` is flat 8.84 → 9.66 µs from K=4 to K=20 (5× the threadgroups for +9%), so
one threadgroup's dependent chain is the whole wave. Fitting t(20)/t(40) gives a
per-dispatch fixed cost of **0.12 µs**, not rule 55's 3.97 µs intercept.

| Metric | Baseline | Candidate | Ratio / delta |
| --- | ---: | ---: | ---: |
| decode seconds/token | not measured this stage | not measured | — |
| prefill seconds/token | not measured this stage | not measured | — |
| same-host paired estimate | — | not measured | — |
| **primary: MMA-shaped QK tile, sliding-kernel time, K=16 (M5 ratio), bit-exact** | 0.000% | **+3.400%** | **+3.400% slower** (minimize) |
| MMA-shaped QK tile, sliding-kernel time, K=32 | 0.000% | +6.047% | +6.047% slower |
| M-padding bill alone (bit-exact 4× MACs), K=16 / K=32 | 0.000% | +10.200% / +11.802% | 1.7–2.0× the prize |
| reduce-elimination ceiling, K=16 / K=32 | 0.000% | −5.134% / −6.857% | 32–43 µs/step busy |

**Repriced against the closed constant (advisor comment 4, 2026-08-10T21:34Z).**
That comment retires the 8× bracket and fixes `%score = 0.63 × τ × Δ_wall / 8972`
⇒ **0.0056 % per M4 decode busy µs** at τ=1, so the 0.378% bar is **68 µs/step of
M4 decode busy** and the harvest needed off the 627.3 µs/step pool is **10.8%**.
Everything below uses that constant, not the superseded 0.00669 / 0.01642 /
0.00203 triple:

| what | harvest % of pool | µs/step busy | %score at τ=1 | fraction of the 0.378% bar |
| --- | ---: | ---: | ---: | ---: |
| **(b) QK-reduce ceiling, K=16 (M5 ratio)** | 5.134% | **32.2** | **0.180%** | **0.47×** |
| (b) QK-reduce ceiling, K=32 | 6.857% | 43.0 | 0.241% | 0.64× |
| **(c) reduce + PV both deleted, K=16** | 8.817% | 55.3 | 0.310% | 0.82× |
| (c) reduce + PV both deleted, K=32 | 9.544% | 59.9 | 0.335% | 0.89× |
| harvest required for the whole bar | **10.8%** | **67.7** | 0.378% | 1.00× |
| MMA-shaped arm as measured, K=16 | **−3.400%** | −21.3 | **−0.119%** | negative |
| MMA-shaped arm as measured, K=32 | −6.047% | −37.9 | −0.212% | negative |

Two consequences, both decisive:

1. **The assigned mechanism's free-reduction ideal reaches 0.47–0.64× of the bar.**
   The 0.20%-of-score `N-QK-REDUCTION-CHEAP` threshold in the assignment body
   becomes **35.7 µs/step** under the closed constant (not the ~30 µs quoted from
   the old 0.00669), so the K=16 ceiling of 32.2 µs/step **fires that rule too**,
   independently of the ≥8% rule.
2. **Even deleting the reduction *and* the PV accumulate — arm (c), deliberately
   incorrect — harvests only 82–89% of what the bar needs.** So no re-expression
   of this kernel's epilogue, MMA or otherwise, can clear 0.378% on its own even
   in the unreachable limit. Answering comment 4 §8.2 directly: the probe does
   **not** support a 25% harvest (156.8 µs/step, 0.88%); 25% is 2.6–3.0× beyond
   the combined free-deletion ceiling of both epilogue mechanisms.

Comment 4 §8.1 also asks for raw `ns` and the ×1.28 `--local-iterate`
correction. Not applicable to this stage: all three arms are standalone Metal
microbenchmarks with fixed buffers, no model and no harness, so there is no `ns`
to report and no sigma to correct. The 0.0056 %/busy-µs constant already folds
the busy→wall transfer in, which is why the µs/step column is the honest one.
Comment 4 §8.3: **the grid is unchanged** — `git diff --stat 1a6761bf -- Sources
Vendor` is empty, so `threadGroup (1024,1,1)` and `grid ((heads/2)*1024,1,1)`
are untouched by construction. Comment 4 §8.4 asked for a non-empty submitted
diff when landing; nothing lands, because Stage 0 refuted the thing that would
have landed.

The paired estimate is a same-host research metric, not an official M5 score; this
stage produced no end-to-end score at all by design. The primary metric above is
a kernel-internal paired ratio on a gen-16 host, reported because it is the
decisive number for the assigned mechanism — not a score claim.

### Conclusion

- What happened and why: the assignment preregistered a stop rule — "if arm (b)
  does not beat arm (a) by ≥8% of kernel time, do not write the MMA kernel". It
  measured **5.13% (K=16) to 6.86% (K=32)**, so **the rule fired** and no MMA
  kernel was written. Deleting all 8 `simd_sum` QK reductions is worth
  **32.2 µs/step (K=16, M5 ratio) to 43.0 µs/step (K=32)** of decode busy off the
  627.3 µs/step pool. Against the constant the advisor closed in comment 4
  (0.0056 %/busy-µs at τ=1 ⇒ the bar is **68 µs/step**, a **10.8% harvest**), that
  free-reduction ideal is **0.180–0.241% of score = 0.47–0.64× of the bar**, and it
  also fires the assignment body's 0.20% `N-QK-REDUCTION-CHEAP` rule at the
  M5-relevant occupancy. Stronger still: arm (c), which deletes the reduction
  **and** the PV accumulate, harvests only 8.8–9.5% — **82–89% of the required
  10.8%** — so nothing in this kernel's epilogue can clear the bar even when
  deleted outright.
- Evidence for or against the mechanism: three converging refutations, plus four
  independent supporting lines.
  **(R1) The preregistered rule fired.** (b)−(a) = 5.13–6.86% < 8%, with the null
  bracket at ±0.19% (K=32) / ±0.12% (K=16) and t = −39.7 / −121.9. Not a
  borderline miss of a noisy threshold; the effect is precise and simply too
  small.
  **(R2) The MMA-shaped arm is slower than base in *both* occupancy regimes.**
  `qk_pad4x_bcast0` — the exact net shape an `simdgroup_matrix<8,8>` QK tile
  produces (4× MACs, reduction free) — is **+6.047% (K=32) / +3.400% (K=16)**
  slower, i.e. the mechanism loses even when the reduction is granted for free.
  The bit-exact padding bill alone is **+11.802% / +10.200%**, roughly **2× the
  entire prize**. This refutation is stronger than the rule, because it does not
  depend on the 8% threshold at all.
  **(R3) The offered retarget is also refuted.** The brief said to spend leftover
  time on load geometry if the reduction failed. Arm (c) `qk_loadonly` leaves
  **90.5% (K=32) / 91.2% (K=16)** of kernel time standing, and the residual is
  not DRAM-bound (113 GB/s achieved vs a measured 266.3 GB/s ceiling = 42.6%,
  `regime=PARTIAL`, 2.1× above the floor) nor launch-bound (fitted per-dispatch
  fixed cost **0.12 µs**, not rule 55's 3.97 µs). The residual is
  per-threadgroup critical-path latency at ~1 TG/core, and both candidate fixes
  are already closed: occupancy-via-threadgroup-memory is refuted (occupancy is
  flat from 16 B to 32,768 B at 1024 threads —
  `research/CURRENT_RESEARCH_STATE.md:2186,2292,3607`), and MLP-via-next-trip
  hoisting is #540's family-specific flat-dose codegen tax on this exact kernel
  (+4.23/+4.28/+3.80/+4.79%, `CURRENT_RESEARCH_STATE.md:2885–2913,3955`; the
  line-799 prohibition "stands unqualified"), which the compiler also cannot do
  on its own because `k_cache`/`v_cache` are written in phase 2 at
  `LagunaRuntimeModel.swift:1486–1487`.
  Supporting lines: (1) the +11.8% padding cost replicates in both residency
  regimes, t up to +258, NULL brackets ≤0.19%. (2)
  `simdgroup_multiply_accumulate` MAC rate measures **0.87× the measured scalar
  FMA peak** (3,158 vs 3,470–3,612 GMAC/s), matching the published AGX
  102.5-Matrix-FFMA16-vs-128-scalar-FMA ratio; it needs ≥4× to fund the padding.
  (3) `qk_ladder5` — a hand-written full 5-stage shuffle butterfly, the shape any
  MMA fragment-reduction tail needs — is **+1.5% slower** than the built-in
  `simd_sum`, so `simd_sum` is already the cheapest correct 32-wide all-reduce on
  AGX. (4) Apple Tech Talk 111432 profiles
  `simdgroup_matrix` at **0% Neural Accelerator utilization even on M5**; the real
  matrix path is MPP `mpp::tensor_ops::matmul2d` gated on arch gen ≥ 17 /
  macOS 26.2+, gen-1 NA has no bf16, and MLX's own M5-vs-M4 data shows NA helps
  prefill (3.33–4.06× TTFT) far more than decode (1.19–1.27×).
  A methodological correction is part of the evidence: my first 4×-MAC arms
  reported −5.3% and −7.9% (i.e. "more work is faster"). That was an artifact of
  the **value-dependent branch in `LAGUNA_RESCALE`** (`LagunaRuntimeModel.swift:1874`,
  `if (as_type<uint>(delta) == 0u) ... else fast::exp(delta)`): score-perturbing
  arms change how often `fast::exp` executes. Holding the score bit-identical
  flips the sign from −7.9% to +6.0%.
- Uncertainty or M5 transfer risk: measured on gen-16 M4 Pro, which is why the
  three numbers are reported twice — once at the M4-scored K=32 (1.60
  threadgroups/core) and once at K=16 (0.80 TG/core), the occupancy ratio the
  ranked ~40-core M5 sees for a 32-threadgroup dispatch. Going from 1.60 to 0.80
  TG/core makes the prize *smaller* (6.86% → 5.13%) and the mechanism *no better*
  (+6.05% → +3.40% still slower than base), so the M5 direction moves against the
  assignment on both axes. The absolute ladder also isolated an M4-only artifact
  that does **not** transfer: t(32) ≈ t(40) means 32 TGs are billed as 40 on a
  20-core host, ~20% second-wave idle worth ≈112 µs/step, absent on M5. The MMA
  refutation is *less* M5-sensitive than the ceiling: on M5 the legacy
  `simdgroup_matrix` intrinsic still misses the Neural Accelerators entirely, and
  the padding term is architecture-independent arithmetic (4× MACs for 2-of-8
  useful rows). Unverified: MPP NVFP4 support (MLX PR #3551 hints at a limit) and
  any direct measurement of legacy `simdgroup_matrix` throughput on M5 silicon.
  Neither can rescue a tile that must win by ~2× to break even.
- Smallest useful next action: **none that can reach the bar.** Even the
  free-reduction ideal (32–43 µs/step busy) is 0.47–0.64× of the 68 µs/step bar,
  and the reduce+PV free-deletion limit is still only 0.82–0.89×, so no
  partial-reduction variant is worth a stage on its own. The only sub-threshold
  candidate left is the W=4 `quad_sum` re-tile (measured −3.5% / −3.9% ⇒
  **22–25 µs/step = 0.12–0.14% of score**), which is a third of the bar and should
  only run bundled with an independent win. The
  half-width lane split I would have proposed is now **closed for two reasons**:
  its 8-dims-per-lane layout is a "wider per-lane load" on round 107's
  banned-re-open list (`research/CURRENT_RESEARCH_STATE.md:3292–3308`), and (R2)
  shows the reduction is not where the time is anyway. §7 of the verdict does
  sharpen the surviving-axis model with a corrected calibration: one dynamic
  `simd_sum` costs **0.214 %/op** versus **0.0307 %/op** for a dynamic FMA, a
  **≈7.0× ratio**, i.e. ≈14 slot-equivalents per pipeline stage against the ≈12
  bar — so the 97.7%-of-peak-issue model does underprice cross-lane ops, but the
  headroom that mis-pricing exposes is exactly the 32–43 µs/step already measured
  and already below the bar.
- Recommendation: **close** R109-D with three labels — `N-ISSUE-BOUND` for the QK
  reduction specifically (the label the preregistered rule asks for; the body's
  `N-QK-REDUCTION-CHEAP` also fires at the M5-relevant occupancy, 0.180% vs the
  0.20% threshold, so either label is defensible and they agree),
  `N-QK-MMA-PADDING-BOUND` for the MMA mechanism (dead by R2, independent of the
  threshold), and the load-geometry retarget closed as not-DRAM-and-not-launch
  bound (R3). I would also close the whole **627.3 µs/step sliding-attention pool
  to epilogue restructuring**: arm (c) bounds every reduce/PV expression change at
  0.89× of the bar. Nothing to merge — `git diff --stat 1a6761bf -- Sources Vendor`
  is empty, by design. Please forward §10 of the verdict to **@alphonse**, whose R109
  assignment applies the same MMA technique to the full-attention twin at
  `LagunaRuntimeModel.swift:2027+`; five of these results (built-in `simd_sum`
  already optimal, the ~2× M-padding bill, the `LAGUNA_RESCALE` probe hazard, the
  `FERN_LADDER=12` setting that matches full attention's 24-threadgroup dispatch,
  and the reusable arm generator) should save that assignment a full stage.
