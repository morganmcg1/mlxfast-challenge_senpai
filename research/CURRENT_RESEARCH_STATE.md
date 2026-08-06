# SENPAI Research State

- **2026-08-06 19:35 UTC** — round 22 mid-flight. #142 resolved and merged as a
  successful negative; frieren reassigned to the prefill ledger as **#148**.
  Advisor branch at `3d745e438d47c6a32d4391c7da161ad1004fbde1`.
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
- **Extend the *existing* fused SwiGLU to the two cases it currently skips.**
  This is the replacement for H5 and it is the strongest round-23 candidate
  precisely because it invents nothing. Two sites take the unfused path:
  (a) the **shared expert in prefill** (`LagunaRuntimeModel.swift:8503`) —
  gate 0.5 MiB + up 0.5 MiB + activated 0.5 MiB per layer = **58.5 MiB per
  512-token prefill**; (b) **dense layer 0**, where fusion is gated on
  `x.dim(1) == 1` (`:8423`), i.e. decode only — **~24 MiB**. Together ~82.5 MiB
  of prefill round trip that a shipped, production kernel can already remove.
  **Do not assign until the SLC-adjusted price is written down** (§8, H5) —
  apply the byte-price law with a sceptical `R_marg`, because the per-layer
  working sets are small enough to be cache-served. Full evidence:
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

**Still open in the archive but reopened / unresolved:** prefill glue (old C5),
shared-expert overlap (old 5b), `MLX_MAX_MB_PER_BUFFER` magnitude (two M4
measurements favour *smaller* buffers; **no M5 datum exists**).

---

## 9. Potential next research directions

Ordered by expected value, not by ease.

1. **Close the prefill ledger with the receipt-channel duplication
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
   Two refinements added since the spec was written:
   **(a) Dual axis.** `prefill_seconds_per_token` and `decode_seconds_per_token`
   publish independently, so a both-phase family such as `routed_gather_gemm`
   yields **two ledger rows per receipt**. The decode row may matter more (75%
   weight): the "decode is exhausted at +2.85%" claim is a **bandwidth** argument
   from per-kernel roofline utilisation (94.6–100.2%), and roofline utilisation
   says nothing about **gap time between kernels**. The decode slope gives
   Σ(kernel time) directly; compare it to `T = 4.1436 ms/step`.
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
2. **Prefill arms generally.** Same +15.17% logic, but until direction 1 lands
   these are unguided. Tanjiro #138 is the pathfinder; the `_nax` safety rig
   (§5) is enabling infrastructure for the whole direction, not a side quest.
3. **Fusion selected by RAW-dependence (§4).** We now have a *rule* for which
   fusions pay. Enumerate every RAW-dependent chain on the scored path and rank
   by exposed serial time. Fern #137 is the first instance; there should be
   more.
4. **Close the 24.9 MB / 5.7% unallocated census remainder.** An unexplained
   5.7% of the byte inventory is the most likely place a missed arm is hiding.
   Assigned as a secondary to nezuko.
5. **Occupancy / tile geometry on the two unsaturated kernels only.**
   `residual_rms_router` (61.8%) and `gate_sp` (30.4 GB/s, latency-bound).
   Everything else is at 94.6–100.2% and is not worth an arm.
6. **Scheduling rather than arithmetic — narrowed, not closed.** #142 closed
   *reordering* (§8: Graham's bound caps it distribution-free). What survives is
   the rest of the launch layer: encoder construction, command-buffer
   partitioning, barrier placement, and the number of dispatches. That layer is
   generation-independent, so M4 evidence is admissible — its main advantage over
   every prefill arm. Direction 1's `R` verdict tells us whether it is worth
   anything: `R ≈ 20–30 ms` makes this the round-23 headline, `R ≈ 0` demotes it.
7. **Deletion as an optimization.** Nezuko's 259-line deletion is the only
   scored-byte movement in four rounds, and headroom is down to 78,253 B.
   Reclaiming dead scaffolding is cheap, safe, and buys room for real arms.
   Candidate: tanjiro's 9 near-duplicate `.metal` variants.
8. **Bit-exactness relaxation, carefully.** H1 is the largest arm we have and
   it is blocked on correctness, not on mechanism. The only permitted
   re-quantization is group-32 affine INT8 for Q/K/V/O and per-head `g_proj`
   (see TASK.md's accepted envelope) — and adopting that envelope for attention
   is already closed as *backwards*. So H1 needs a different correctness
   argument, probably a bit-exactness proof rather than an envelope appeal.

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
