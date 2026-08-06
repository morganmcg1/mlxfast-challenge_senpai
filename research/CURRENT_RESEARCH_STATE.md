# SENPAI Research State

- **2026-08-06 20:10 UTC** — round 22 mid-flight, all four students occupied.
  #142 resolved and merged as a successful negative; frieren reassigned to the
  prefill ledger as **#148**. This revision absorbs the round-23 frontier
  review: the +2.85% decode ceiling is re-scoped as a *byte-removal* ceiling
  (§2, §4.1), the ledger's decode axis is promoted to co-primary with a
  mandatory multi-dose linearity control (§9.2), a decode dead-time programme
  becomes the top next direction (§9.1), and `MLX_MAX_MB_PER_BUFFER` is closed
  as our canonical M4→M5 sign inversion (§8).
- **Most recent human research direction:** none new this session. Standing
  campaign rules remain: every official submission goes out as
  `mlxfast submit --model "senpai"`; advisor and all four students are
  authorized to dispatch; **launch isolation from the parallel `birch` campaign
  is absolute** — do not inspect, cite, or borrow from it.
- **This is a living document.** It was 6,874 lines and had become an archive.
  Everything prior to round 22 now lives in
  [`RESEARCH_STATE_ARCHIVE_through-round-21.md`](RESEARCH_STATE_ARCHIVE_through-round-21.md).
  Read that only when you need the derivation behind a number quoted here.
  Keep *this* file short. Prune it every round.

---

## 1. Where we stand

**We are rank 1.**

| field | value |
| --- | --- |
| receipt | `97a5090` |
| commit | `3e165fa` |
| officialScore | **2.58882784082067** |
| status | promoted |
| origin | PR #80 (frieren, attention pairwise scale halving) |

Later leaderboard receipts `26dc269`, `c95b4e4`, `00de2d3` and the in-flight
`57d8f082` are **birch**, not ours. Do not read them as competition from a
third party and do not chase them.

Advisor branch HEAD: **`3d745e438d47c6a32d4391c7da161ad1004fbde1`**
(`ORGANIZER_FRONTIER_SHA=afcb8320912aa1162f841f282442d7c093e6b2e5`). The two
commits since round 22 opened are **research-only**; the byte budget below is
unchanged, and the `baseline_advanced` events they fire on #137/#138/#143 do not
require a rebase. Students must not rebase; the advisor supplies
`accepted_base_sha` at merge.

### Byte budget at BASE_SHA

```
current=2921747/3000000   headroom=78253   growth=0/262144   files=142
Sources/MLXFastModel/LagunaRuntimeModel.swift = 467167/524288  (headroom 57121 B)
```

Headroom is now a real constraint. Prefer `quantized.cpp` for new kernel source.

---

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
−31.28 ms = **+15.17%**.

> An earlier advisor note put the 3.13 ms figure at "+2.08%". **That was
> wrong.** The frontier agent's ~11.6% for the full remainder was roughly
> right. Use the table above.

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

1. **Local M4 `--local-iterate` MDE is ±0.73%.** Established empirically by
   tanjiro in PR #103 §11.2 using byte-identical Sources. No win *or* loss may
   be claimed inside that band.
2. **Judge official receipts by `ns`, never by `officialScore`.**
   Pooled cv: `ns` **0.149%**, `officialScore` **0.553%**. The gap is entirely
   the paired baseline's prefill arm, which is **bimodal** (sd 1.933%,
   p50 368.5 µs / p90 382.9 µs). The **candidate** arm's prefill redraw sd is
   only **0.260%**, i.e. **0.065% of `ns`** — so `ns` is a *precise prefill
   instrument*: a genuine +1.2% prefill arm lands at roughly **8σ**.
3. **Receipt channel.** Single shared in-flight slot across all four students,
   ~35 min per receipt. Round budget ≤10 receipts total. Kill a family if its
   first receipt is below `best − 0.243%` (2σ).
4. **M4 vs M5.** Students are on M4 Pro, Apple GPU **generation 16**, which
   **cannot execute `_nax` kernels at all**. The official M5 selects `_nax`.
   Any `_nax` arm is therefore M4-blind and needs the safety rig in §5.
   Every writeup must state which kernel family the local run actually
   selected.

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

### 4.1 ⚠️ Open contradiction: the shadow model vs. the M4 profile

This is now the highest-value unresolved question in the campaign, because it
decides whether the 75%-weight axis has a lane at all. Three facts, at least
one of which must be misread:

1. **M4 decode overlap is exactly zero.** `gpu_busy_sum == gpu_busy_union` to
   **6 ns** (`research/nezuko-decode-roofline.md:193-202`, restated
   `research/nezuko-terminal-report.md:221-225`; reconfirmed
   `research/maple-tanjiro-pr73-decode-kernel-census.md:721`). Steady step:
   wall 9.816 ms, busy 9.492/9.498 ms, **host gap 0.322 ms = 3.3%**, 45 command
   buffers (1.33 µs each ⇒ only 60 µs/step), 406 dispatches. Stable at 3.0–3.5%
   across the whole `MLX_MAX_MB_PER_BUFFER` sweep.
2. **PR #48 removed 80 decode dispatches (406 → 326) for `ns` −0.1488%** —
   ≈ 0.12 µs per removed dispatch. We explained this as *those dispatches were
   hazard-free and therefore already shadowed, hence free.*
3. **PR #34 r2 priced a barrier-serialized dispatch at 1.980 ± 0.044 µs on the
   M5** — 16× the #48 marginal rate.

(1) and (2) are hard to hold together: if nothing overlaps, nothing can be
shadowed. Candidate resolutions:

- **(a)** the M4 `union` is computed per command buffer or from timestamps
  blind to intra-buffer overlap ⇒ "zero concurrency" is an artifact and
  shadowing is real;
- **(b)** shadowing is not real, the #48 dispatches were genuinely ~0.12 µs of
  GPU work, and 1.980 µs prices *the added barrier* rather than the dispatch;
- **(c)** M4 and M5 differ structurally — for which we now have hard precedent
  (§8, `MLX_MAX_MB_PER_BUFFER`).

**Adjudicated by #148's mandatory dose-linearity control.** Per-family slope
`d(decode_seconds_per_token)/dm` compared against the family's isolated GPU
duration: slope ≈ isolated ⇒ serial, and `Σ(slopes) ≈ T` ⇒ (b), decode is
execution-saturated and only layout remains. Slope ≪ isolated ⇒ (a), and every
in-isolation µs/step claim in the campaign is over-attributed. The residual
`T − Σ(slopes)` also separates "host gap is absolute" (≈ 322 µs ⇒ 7.8% of the
M5 step) from "host gap is proportional" (≈ 137 µs) — 185 µs apart.

**No equivalent prefill profile exists.** `research/nezuko_mbpb_prefill.sh:8-14`
states its `--profile` window covers only steady decode steps, so the busy/wall
lines in `nezuko-mbpb-prefill.log` are decode. Only prefill total wall is
recorded (`:2`, 544.93 ms on M4). #148's prefill rows are the first per-family
prefill attribution this programme will have.

---

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

## 6. Round 22 — in flight

**BASE_SHA `2443984f8de7544170a256ad854a22fcf18c8460` for #137/#138/#143;
`3d745e438d47c6a32d4391c7da161ad1004fbde1` for #148.**

**Governing rule this round: every arm has a free offline falsifier that runs
FIRST.** This is the direct remedy for rounds 19, 20 and 21, which shipped
**zero scored bytes** between them. The only scored-byte movement in four
rounds is nezuko's 259-line deletion in #110. **The rule is already paying:**
#142 reached a defensible terminal verdict in under an hour for **zero GPU cost
and zero receipts**.

| PR | student | arm | falsifier (runs first) | expected | state |
| --- | --- | --- | --- | --- | --- |
| **#137** | maple-fern | lm-head cascade **fusion** across RAW-dependent stages | calibrated-injection slope test `dStep/dX`, spin X ∈ {0,5,10,20,40} µs at each boundary → per-site critical-path map. GO ≥40 µs, STOP <25 µs | 80 µs = **+1.17%**, bit-exact, M4-measurable | wip |
| **#138** | maple-tanjiro | prefill `_nax` **BK 64→128** (gate_up 32→16 trips, down 8→4); secondary BN arm **down-only** | offline MSL compile + occupancy audit; Ws 9.2→17.4 kB; kill if TG/core 3→1, re-scope down-only if 3→2 | **+0.7…+1.8%** | wip |
| **#142** | maple-frieren | device-compacted **LPT expert queue** via `dispatchThreadgroups(indirectBuffer:)` | rows-per-expert histogram + pure-arithmetic LPT makespan simulation | — | **MERGED as a successful negative** (§8) |
| **#143** | maple-nezuko | checkpoint **expert-slab dedup** + scale-plane census (`MLXFastTransform` + sort-time merge) | **pure CPU scan of the 21.6 GB checkpoint — zero GPU, zero receipts**; kill at <5% byte-duplicate rate | 10% hit ≈ −2…−4 ms S = **+0.7…+1.4%**, bit-exact | wip |
| **#148** | maple-frieren | **prefill ledger R1** — measure `T_gather` on the real M5 by calibrated bit-exact work injection, read off the receipt's `officialMetrics` | three free offline falsifiers: (a) M4 elision check, (b) bit-exactness + bf16 overflow margin, (c) wall-time projection ≤70% of timeout | resolves the §9.1 strategic fork | wip |

Nezuko's declared fallback if the census kills H4: **H6 `residual_rms_router`
transpose** — offline-transposed layout for float4-coalesced loads, 2 rows per
simdgroup; 40.9 MB/step at 61.8%→95% = **−42 µs T = +0.62%**, bit-exact and
M4-measurable — plus closing the **24.9 MB / 5.7% unallocated** remainder in
his own #110 census. He is **no longer** the ledger owner (told on #143).

### Region fence (four students in adjacent code)

| student | owns |
| --- | --- |
| fern | lm-head cascade region of `LagunaRuntimeModel.swift` (~:10920-11053) + tier-1/tier-2 kernels |
| tanjiro | `_nax` kernel inner loop / tile geometry + accept gate ~`quantized.cpp:1634-1671`, `tg_expert_groups`, `.metal` variants |
| frieren | routed-MoE **gather call site** in `LagunaRuntimeModel.swift` (#148 injection point) |
| nezuko | `Sources/MLXFastTransform` + CPU-side slab construction |

Advisor arbitrates any overlap; students must not edit each other's region.
**Only one submission receipt may be in flight campaign-wide** (~35 min each) —
this binds #148 hardest, because its whole method is spending receipts.

---

## 7. Held for round 23

- **H1 row-adaptive dual-path gather kernel.** Biggest single arm on the board
  at **+1.4…+2.9%** — but it is **not bit-exact** and it is **M4-blind**. Needs
  a correctness story and the `_nax` safety rig before it can be assigned.
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
- **Post-merge cleanup PR**, owed the moment any arm ships scored bytes.
  Candidate: tanjiro's 9 near-duplicate `.metal` variants. Headroom is 78,253 B.

---

## 8. Closed families — do not re-litigate

The full evidence table lives in the archive
([`RESEARCH_STATE_ARCHIVE_through-round-21.md`](RESEARCH_STATE_ARCHIVE_through-round-21.md),
"Closed families"). Consult it before proposing anything below. Summary index:

**Closed this session:**

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
in-loop host CPU · decode head latency · first-touch prewarm · attention INT8
envelope adoption (backwards — adds ~802 MB/step) · certified lm-head screening ·
NVFP4 scale-plane amplification (A = 1.000) · quantized attention weights in
prefill · prefill overlap C1/C2 · `DARKBLOOM_STAGE_BM128` · ranking a candidate
by `officialScore` · `./probe` on the M5 (impossible — no shell on the ranked
host; the only M5 channel is a submitted candidate plus its receipt `metrics`).

**`MLX_MAX_MB_PER_BUFFER` — CLOSED, and it is our canonical M4→M5 inversion.**
Earlier notes said "no M5 datum exists"; that is **false**. 200 → 50 was
submitted (receipt `3e6fdcb`, commit `1ce8373`, `research/nezuko-mb50-receipt.md`)
and returned **`ns` −1.608%** on the M5 — `S` +2.193%, `T` +1.316% — against
**two independent balanced M4 confirmations of −1.76% and −1.99% wall/step,
monotone in the cap.** Opposite sign. Do not re-propose it, and cite it whenever
a student wants to treat M4 agreement as M5 evidence.

**Still open in the archive but reopened / unresolved:** prefill glue (old C5),
shared-expert overlap (old 5b).

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

1. **Decode dead-time programme (frontier "Attack A") — the top pick on the
   75%-weight axis.** §2's "+2.85% even at 100% removal" is a *byte-removal
   ceiling at fixed schedule and layout*; it is silent about time that is not
   spent moving bytes (§4.1). Three independent numbers say that time is not
   small: forced serialization costs **+5.49%** [+4.70,+6.28]; a
   barrier-serialized dispatch was priced at **1.980 ± 0.044 µs** on M5 (PR #34
   r2) and the decode step has ~150–250 RAW boundaries, i.e. **300–500 µs =
   7–12% of `T = 4.1436 ms`**; and the M4 profile shows a **0.322 ms host/queue
   gap (3.3%)** plus 45 command buffers at 1.33 µs each (60 µs/step).
   The programme is: enumerate every RAW-dependent chain on the scored decode
   path, rank by exposed serial time, and attack the top ones with the #137
   fusion pattern plus encode-order changes that let hazard-free work be
   enqueued between the two halves of a hazard. This *subsumes and replaces the
   old standalone "fusion selected by RAW-dependence" direction* — that was the
   rule, this is the systematic sweep.
   Expected +2–5%. Decisive advantages: it is **incremental** (each fused chain
   is a separate small commit, so a partial result still ships), it is
   **M4-falsifiable end to end** (decode kernels are hand-written MSL/QMV, not
   `_nax`, so M4 executes the whole path — the one axis where local timing is
   real evidence), and it sits on the 75% weight. Sequencing: gated on #148's
   decode-axis verdict (§4.1 decision rule). If the ledger's residual
   `T − Σ(slopes)` is ≈ 0, decode really is execution-saturated and this
   direction dies cheaply; if it is ≥ 300 µs, this direction owns the next two
   student rounds.
2. **Close the prefill *and decode* ledger with the receipt-channel duplication
   instrument.** Full spec: [`PREFILL_LEDGER_INSTRUMENT.md`](PREFILL_LEDGER_INSTRUMENT.md).
   §2 says the decode inventory is worth at most +2.85% even at 100% removal,
   while prefill's unattributed remainder is 31.28 ms ≈ **+15.17%**. We are
   blind to it because 94.2% of M5 prefill is `_nax` and M4 Pro (GPU gen 16)
   cannot execute those kernels at all — so every prefill arm we assign,
   #138 included, is currently a *guess*. The instrument fixes that: duplicate
   one kernel family's pure work bit-exactly (`0.5*(y1+y2)`), submit a
   deliberately-slow candidate, and read the shift off the candidate arm's raw
   `prefill_seconds_per_token`.
   **The channel is verified open, not assumed:** a receipt rejected *on
   ranking* publishes full `officialMetrics` (all 1399 feed submissions), and
   our own PR #34 r2 already ran an openly-documented injection probe through
   static review and every hidden gate. Floor headroom is ~97 ms against a
   ≤70 ms injection budget; the binding risk is the workflow timeout, not the
   floors. A floor/correctness/gate failure, by contrast, publishes **nothing**.
   Three receipts resolve a strategic fork we cannot otherwise resolve: if the
   residual `R = S₀ − Σx̂ᵢ ≈ 0`, the 31.28 ms is *inside* the measured kernels
   (work programme: inner loops, tile geometry); if `R ≈ 20–30 ms` it is
   *between* them (work programme: dispatch structure).
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
   monoculture-breaker, and it has a free falsifier.** Today prefill runs one
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
   fat-tailed bet, not a favourite. What makes it worth a slot anyway is the
   **zero-receipt M4 falsifier**: tape-interleave two independent large GEMMs
   and check whether `gpu_busy_union < gpu_busy_sum`. §4.1 records that in the
   *measured* decode profile these are equal to 6 ns — nothing overlaps — so if
   an explicitly interleaved pair also fails to overlap, Apple's scheduler does
   not co-resident-execute distinct kernel families at all and **the entire
   family dies for one student-day and no receipts**. Run that falsifier first,
   always.
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
   staging. This is *cross-tensor ordering*. Gate on #143's slab machinery
   landing and on #148 publishing a gather-plane row.
5. **Prefill arms generally.** Same +15.17% logic, but until direction 2 lands
   these are unguided. Tanjiro #138 is the pathfinder; the `_nax` safety rig
   (§5) is enabling infrastructure for the whole direction, not a side quest.
6. **Close the 24.9 MB / 5.7% unallocated census remainder.** An unexplained
   5.7% of the byte inventory is the most likely place a missed arm is hiding.
   Assigned as a secondary to nezuko.
7. **Occupancy / tile geometry on the two unsaturated kernels only.**
   `residual_rms_router` (61.8%) and `gate_sp` (30.4 GB/s, latency-bound).
   Everything else is at 94.6–100.2% and is not worth an arm.
8. **Scheduling rather than arithmetic — narrowed, not closed.** #142 closed
   *reordering* (§8: Graham's bound caps it distribution-free). What survives is
   the rest of the launch layer: encoder construction, command-buffer
   partitioning, barrier placement, and the number of dispatches. That layer is
   generation-independent, so M4 evidence is admissible — its main advantage over
   every prefill arm. On the decode side this is direction 1; on the prefill
   side direction 2's `R` verdict decides its worth: `R ≈ 20–30 ms` makes it the
   round-23 headline, `R ≈ 0` demotes it.
9. **Deletion as an optimization.** Nezuko's 259-line deletion is the only
   scored-byte movement in four rounds, and headroom is down to 78,253 B.
   Reclaiming dead scaffolding is cheap, safe, and buys room for real arms.
   Candidate: tanjiro's 9 near-duplicate `.metal` variants.
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

---

## 10. Open programme issues

- **§R21.7 remains open:** there is **no typed transition to open a new GitHub
  issue**, so the birch/maple shared-submission-channel coordination issue
  cannot be filed by an agent. This needs a human operator.
- **`gh` CLI has no token** in the advisor shell, by design. All GitHub
  mutation goes through typed transitions. Field notes on their required fields:
  `create_assignment` needs `revision_id` **and** `expected_base_sha`, and uses
  `head_branch` (not `branch`); `send_assignment_feedback` needs
  `expected_head_sha`, must **omit** `student`, and is **refused unless the PR is
  `status:wip`** — so post review feedback *before* a student flips to
  `status:review`, or carry it into the next assignment body (as was done for
  #142 → #148 §9); `push_branch` needs both `expected_head_sha` and
  `expected_remote_sha`.
- **Delegation:** prefer **leaf** agents (`explore`, `search`, `bash-runner`)
  for research. `general-purpose` children that spawn their own helpers have
  repeatedly died with "uncollected descendants". Two leaf agents closed H5 this
  session at zero cost.
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
