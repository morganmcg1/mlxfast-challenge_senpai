# SENPAI Research State

- **2026-08-06 18:50 UTC** — round 22 issued (4 assignments), advisor branch at
  `2443984f8de7544170a256ad854a22fcf18c8460`.
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

Advisor branch HEAD: **`2443984f8de7544170a256ad854a22fcf18c8460`**
(`ORGANIZER_FRONTIER_SHA=afcb8320912aa1162f841f282442d7c093e6b2e5`).

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

**BASE_SHA `2443984f8de7544170a256ad854a22fcf18c8460` for all four.**

**Governing rule this round: every arm has a free offline falsifier that runs
FIRST.** This is the direct remedy for rounds 19, 20 and 21, which shipped
**zero scored bytes** between them. The only scored-byte movement in four
rounds is nezuko's 259-line deletion in #110.

| PR | student | arm | falsifier (runs first) | expected |
| --- | --- | --- | --- | --- |
| **#137** | maple-fern | lm-head cascade **fusion** across RAW-dependent stages | calibrated-injection slope test `dStep/dX`, spin X ∈ {0,5,10,20,40} µs at each boundary → per-site critical-path map. GO ≥40 µs, STOP <25 µs | 80 µs = **+1.17%**, bit-exact, M4-measurable |
| **#138** | maple-tanjiro | prefill `_nax` **BK 64→128** (gate_up 32→16 trips, down 8→4); secondary BN arm **down-only** | offline MSL compile + occupancy audit; Ws 9.2→17.4 kB; kill if TG/core 3→1, re-scope down-only if 3→2 | **+0.7…+1.8%** |
| **#142** | maple-frieren | device-compacted **LPT expert queue** via `dispatchThreadgroups(indirectBuffer:)` (`quantized.cpp:1900-1930` + prep kernel) | rows-per-expert histogram (he **owns and publishes** it) + pure-arithmetic LPT makespan simulation on 40 cores; demote if <1 ms | **+0.4…+1.1%**, bit-exact |
| **#143** | maple-nezuko | checkpoint **expert-slab dedup** + scale-plane census (`MLXFastTransform` + sort-time merge) | **pure CPU scan of the 21.6 GB checkpoint — zero GPU, zero receipts**; kill at <5% byte-duplicate rate | 10% hit ≈ −2…−4 ms S = **+0.7…+1.4%**, bit-exact |

Nezuko's declared fallback if the census kills H4: **H6 `residual_rms_router`
transpose** — offline-transposed layout for float4-coalesced loads, 2 rows per
simdgroup; 40.9 MB/step at 61.8%→95% = **−42 µs T = +0.62%**, bit-exact and
M4-measurable — plus closing the **24.9 MB / 5.7% unallocated** remainder in
his own #110 census.

### Region fence (four students in adjacent code)

| student | owns |
| --- | --- |
| fern | lm-head cascade region of `LagunaRuntimeModel.swift` (~:10920-11053) + tier-1/tier-2 kernels |
| tanjiro | `_nax` kernel inner loop / tile geometry + accept gate ~`quantized.cpp:1634-1671` |
| frieren | grid/dispatch construction ~`quantized.cpp:1900-1930` + new prep kernel |
| nezuko | `Sources/MLXFastTransform` |

frieren and tanjiro are both in `quantized.cpp`. Advisor arbitrates any
overlap; students must not edit each other's region.

---

## 7. Held for round 23

- **H1 row-adaptive dual-path gather kernel.** Biggest single arm on the board
  at **+1.4…+2.9%** — but it is **not bit-exact** and it is **M4-blind**. Needs
  a correctness story and the `_nax` safety rig before it can be assigned.
- **H5 per-expert fused FFN.** +0.2…+3.6%, but **kill on paper first** via the
  SLC-absorption bound: it collapses to **+0.22%** if the 16.8 MB/layer
  `gate_up` working set already fits a ~48 MB-class SLC. Do not assign until
  someone has done that arithmetic.

---

## 8. Closed families — do not re-litigate

The full evidence table lives in the archive
([`RESEARCH_STATE_ARCHIVE_through-round-21.md`](RESEARCH_STATE_ARCHIVE_through-round-21.md),
"Closed families"). Consult it before proposing anything below. Summary index:

**Closed this session:**

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

1. **Prefill, prefill, prefill.** §2 says the decode inventory is worth at most
   +2.85% even at 100% removal, while prefill's unattributed remainder is
   31.28 ms ≈ +15.17%. Every strong future hypothesis should be asked "does
   this move `S`?" first. The blocker is that per-kernel prefill attribution is
   **94.2% NAX-divergent**, so M4 cannot see it — which makes the `_nax` safety
   rig (§5) the enabling infrastructure for the whole direction, not a side
   quest. **Tanjiro #138 is the pathfinder for this.**
2. **Fusion selected by RAW-dependence (§4).** We now have a *rule* for which
   fusions pay. Enumerate every RAW-dependent chain on the scored path and rank
   by exposed serial time. Fern #137 is the first instance; there should be
   more.
3. **Close the 24.9 MB / 5.7% unallocated census remainder.** An unexplained
   5.7% of the byte inventory is the most likely place a missed arm is hiding.
   Assigned as a secondary to nezuko.
4. **Occupancy / tile geometry on the two unsaturated kernels only.**
   `residual_rms_router` (61.8%) and `gate_sp` (30.4 GB/s, latency-bound).
   Everything else is at 94.6–100.2% and is not worth an arm.
5. **Scheduling rather than arithmetic.** Frieren #142's indirect dispatch is
   the first of a class: the launch/queue/ordering layer has had far less
   attention than the kernel inner loops, and it is generation-independent so
   M4 evidence is admissible.
6. **Deletion as an optimization.** Nezuko's 259-line deletion is the only
   scored-byte movement in four rounds, and headroom is down to 78,253 B.
   Reclaiming dead scaffolding is cheap, safe, and buys room for real arms.
   Candidate: tanjiro's 9 near-duplicate `.metal` variants.
7. **Bit-exactness relaxation, carefully.** H1 is the largest arm we have and
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
  mutation goes through typed transitions.
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
