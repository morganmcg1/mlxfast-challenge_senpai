# Round 9 research ideas — 2026-08-05 15:35Z

Author: meridian (advisor). Base `d267ebda88c50a6e1b539d9265050dbaae00c268`.

**Evidence contract:** this programme has **no W&B runs**. Every claim below is
cited to a ranked `mlxfast` receipt ID or a `research/*.md` path with line
numbers.

---

## 0. Headline: we have been buying measurement with ranked receipts and shipping nothing

Two facts established today change what round 9 should be.

### 0.1 The shipped editable tree has been byte-frozen for ~18 hours

Fingerprint = sha1 over the ordered list of `git rev-parse <rev>:<path>` blob IDs
for all 97 `editablePaths` in `benchmark.json`.

| rev | date | editable-tree fingerprint |
|---|---|---|
| `768bb9d4` (BASE_SHA) | — | `ed340e9939ab` |
| `9a407ed6` | 08-04 19:20 | `36039062e545` |
| `a3c096ee` | 08-04 21:02 | `5fe63db21fa1` |
| `6f1289a9` | 08-04 21:03 | **`97c022d6bf31`** |
| `d18ebbba` (#32 merge) | 08-05 | `97c022d6bf31` |
| `904173a0` (#40 merge) | 08-05 | `97c022d6bf31` |
| `1849b376` (#34 merge) | 08-05 | `97c022d6bf31` |
| `d267ebda` (HEAD) | 08-05 | `97c022d6bf31` |

**Three merged PRs (#32 r2, #40 r2, #34 r2) and ~18.2 hours shipped zero net
editable bytes.** A first-parent walk confirms only `9a407ed6`, `a3c096ee` and
`6f1289a9` ever moved the shipped tree. Four editable files churned *inside*
merged branches; every change was reverted before merge. Independent
corroboration: the `baseline_advanced` intersection for PR #35 spans 93 changed
files and **0** editable paths.

### 0.2 Renormalised `ns` says the control is our best arm

`ns = nd^0.75 · npf^0.25` with `nd = 0.013890/decode_s_per_tok`,
`npf = 0.0003845/prefill_s_per_tok`; `draw = officialScore/ns`. Computed from
`officialMetrics` for all 23 `solverUsername=='morganmcg1'` submissions.

| created (Z) | feed sha | officialScore | ns | draw |
|---|---|---:|---:|---:|
| 08-04T21:20:30 | `1c4fb41` | 1.788158 | 1.804692 | 0.990838 |
| 08-05T09:33:21 | `e82d6cf` **(control)** | 2.523276 | **2.544360** | 0.991714 |
| 08-05T10:01:44 | `2808e93` | 2.290697 | 2.283549 | 1.003130 |
| 08-05T10:25:19 | `504104e` | 2.505056 | 2.539719 | 0.986352 |
| 08-05T10:53:31 | `d4235c9` | **2.545892** | 2.538013 | 1.003104 |
| 08-05T12:25:15 | `021fa4a` | 2.493877 | 2.503448 | 0.996177 |
| 08-05T14:12:43 | `cc4b1dc` | 2.516657 | 2.514737 | 1.000764 |

- Best `ns` in our history = **the control** (frozen frontier, cap 200) at
  **2.544360**.
- Our board-leading receipt (`officialScore` 2.545892, gap to crown 0.2517%) has
  `ns` **2.538013** — **0.25% worse than doing nothing** — with a baseline draw
  of 1.003104.
- **Every arm submitted since 08-04 21:03Z is `ns`-inferior to the frozen
  frontier.**

Our leaderboard position is a favourable baseline lottery ticket on code that is
measurably worse than the code it replaced. The instruments that let us say this
to ±0.03% are genuinely valuable — but the programme has now **staffed
measurement of both big residuals and mechanism ownership of neither, while
treating "GPU busy" as "GPU useful."**

### 0.3 Round-9 directive

**Stop buying measurement with ranked receipts. Start shipping mechanism.**
Every round-9 assignment must either (a) change bytes on the scored path, or
(b) be a *free, local, M4-legal* audit that decides a mechanism arm without
consuming a receipt. No more ranked receipts spent on knob sweeps.

⚠ **Submission-feed SHA mapping.** The API's `submissionCommitSha` differs from
the local commit SHA students report. Map by timestamp. Ledger names
`c3ce66e`, `0411779`, `cdf71fa`, `4058d0b`, `3e6fdcb`, `c747336` correspond to
feed SHAs `e82d6cf`, `2808e93`, `504104e`, `d4235c9`, `021fa4a`, `cc4b1dc`.

---

## 1. Retirements — clear these off the board before assigning anything

| item | verdict | authority |
|---|---|---|
| Round-8 idea 3 (R-MBBUF, command-buffer byte cap) | **RETIRED** | §0.9.12 three-point M5 curve; log-quadratic fit peaks at ~176 MB for **+0.018%**, 16× below the 0.278% resolution floor |
| Whole command-buffer knob family | **CLOSED AXIS** | same; plus the ops axis is structurally unreachable (max 28 ops/cb at the shipped byte cap, rule needs 201, `cbs at ops limit` = 0 across six arms / 131,954 cbs) |
| Round-8 idea 1 (P-GLUE) | **CANCELLED** | prior round |
| Round-8 idea 2 magnitude | **VOID** | conversion-step error |
| P-SHARED | **OUT** | +0.08–0.10%, below the 0.278% floor. Rider only — never spend a slot |
| Gather-GEMM mechanism #1 (`Ws` double-buffer) + register-prefetch sibling | **MEASURED NULL** | fern #40 |
| Gather-GEMM mechanism #2 (SM=16 banding) | **CLOSED AND STRUCK** | `SM = BM/WM` (`:1634`), `TM = SM/16` integer division (`:1637`) ⇒ any `SM<16` gives `TM=0`; host guard `quantized.cpp:1662` pins `bm==64 && wm==4` |
| **N1 — static specialisation on the 512 decode window** | **RETIRED ON ARRIVAL** | see §1.1 |
| **N2 — h48 padding audit** | **RETIRED ON ARRIVAL** | see §1.2 |

### 1.1 N1 retired: the sliding kernel is already statically specialised

I proposed exploiting the fact that at decode the sliding ring is exactly 512
positions — a statically known trip count admitting full unroll and
compile-time loads-in-flight. **The frontier source read shows this already
exists.** `sliding_fused_attn_ring_v1` uses a compile-time `N=512`, `BN=32`, and
16 slots per simdgroup executed as 8 trips of a hand-written 2-deep pipeline
(`LagunaRuntimeModel.swift:1529-1530`). There is no dynamic bound to remove.
The residual value in this direction is *deeper* pipelining, which is already
captured as R2 in `research/BRIEF_QUEUED_SLIDING_ATTN_REWRITE.md` §3 Step 2.

### 1.2 N2 retired: the h48 path does not pad, and the ledger already proved it

I proposed auditing whether the 10 h48 layers pad to 64 lanes (48 = 3×16), which
would move ~33% more bytes than needed. **Arithmetic on data already in
`research/nezuko-pr9-dispatch-fusion.md:120-144` refutes it:**

- `oproj_h48` 7.09 MB/call vs `oproj_act_h64` 9.45 MB/call ⇒ ratio
  **0.750 = 48/64 exactly.** No padding.
- `decode_nvfp4_qkv_h48_r1` 9.44 MB/call vs `..._h64_r1` 11.80 MB/call ⇒ ratio
  **0.800**. Not 0.75 — but that is *correct*, because QKV output width is
  `heads·128 + 2·kv_heads·128`, and `gqa=6` gives 48/6 = 8 KV heads, same as
  64/8 = 8. So h64 = 8192+1024+1024 = 10240 and h48 = 6144+1024+1024 = 8192,
  ratio **8192/10240 = 0.800 exactly.** No padding.

Both retirements are worked examples of the standing ledger-hygiene rule: **a
banked price is not evidence, and an idea that can be killed by arithmetic on
data already on disk must never consume a student slot.** Five of eight checked
queue prices were wrong; two of two new ideas died to a source read and a
division. Re-derive before assigning.

---

## 2. The round-9 strategic theme: the low-efficiency-kernel class

Nezuko's round-8 conclusion was **"This is an occupancy problem, not a
dispatch-count problem"** (`research/nezuko-pr9-dispatch-fusion.md:180-193`).
The programme has never operationalised it. It should be the whole of round 9.

Four decode kernels sit far below the M4 260.2 GB/s ceiling and together carry
**83.6% of the M4 decode residual (1.650 ms)**:

| kernel | n | % of ceiling | M4 recoverable | **central (×0.812)** | % score |
|---|---:|---:|---:|---:|---:|
| `sliding_fused_attn_ring_v1` | 30 | **36%** | 428 µs | **347 µs** | **+5.16%** |
| `full_fused_attn_grow_v1` | 10 | **43%** | 130 µs | 106 µs | +1.57% |
| `residual_rms_router_..._rpg8` | 39 | **60%** | 106 µs | 86 µs | +1.28% |
| `shared_nvfp4_swiglu_qmv_rows1` | 39 | **73%** | 65 µs | 53 µs | +0.78% |
| **total** | | | **1380 µs** | **1121 µs** | **+16.65%** |

Zeroing the *entire* M5 residual is `(4.281/2.941)^0.75 − 1 = **+32.7%**`, so
this class is roughly half the theoretical decode headroom.

The frontier design review of the two attention kernels (task
`8dd61eee-216d-55d7-906d-10411e8e0398`) found the mechanism, and it is
**structural, not numerical**:

1. **Too few threadgroups, one per core.** 32 TGs (sliding) / 24 (full), each
   pinned to one GPU core by ~18.4 kB of threadgroup memory against a 32 kB
   budget. On a ~40-core M5 Max, **32 threadgroups cannot fill the GPU even
   once.**
2. **Burst-then-stall issue pattern.** 4 vec4 loads (32 B/lane in flight), then
   16 FMAs + 4 serialised `simd_sum` shuffle trees + 4 `exp`s + 32 accumulate
   FMAs (`:1537-1616`). Apple issues in order and **the compiler cannot hoist
   next-trip loads because `k_cache`/`v_cache` are also written in phase 2
   (`:1486-1487`)** — provable non-aliasing fails.
3. 28 of 32 simdgroups idle through phase 1 with no loads in flight
   (`:1425-1471`).

Those three findings generalise into three new, cheap, receipt-free audits —
ideas N5, N4, N3 below — that would rank the *entire* decode step by structural
waste for the first time.

---

## 3. Ranked round-9 ideas

### Rank 1 — ★★ Sliding-attention occupancy rewrite (`+5.2%` central)

**Brief is written and queued:** `research/BRIEF_QUEUED_SLIDING_ATTN_REWRITE.md`.
Presumptive owner @maple-nezuko (her #44 r3 preview). Ladder is
Step 0 static occupancy audit → R2 deepen pipeline 2→4 slots → R1 one query head
per threadgroup (32→64 TGs) → R1+R2 → ranked receipt. Companion
`full_fused_attn_grow_v1` is a **separate** PR (+1.57%). Combined pool
453 µs ⇒ **+6.7%, the largest priced item in the programme.**

Bit-exactness key: **R1 is safe because head0 and head1 never interact
numerically**; cross-threadgroup position splits are *not* safe. dup/ser
first-touch ratio 0.971 ⇒ fusion cannot help here; only a better kernel can.
**M4-screenable** (JIT `MLXFast.metalKernel`, not `_nax`-gated).

### Rank 2 — ★★ fern #48 fused norm + QKV + gate (`+0.47%` floor / `+2.99%` central)

**IN FLIGHT.** Repriced today; the gate is **85.9% of the prize**:

| side | disp | M4 µs/call | M4 µs/step | M5 µs | % score |
|---|---:|---:|---:|---:|---:|
| norm `rmsbfloat16` (40 of 41) | 40 | 0.87 | 34.8 | 28.3 | +0.420% |
| gate `gate_sp_h64/h48` | 40 | 5.32 | 212.8 | 172.8 | **+2.568%** |
| combined | 80 | — | 247.6 | 201.1 | **+2.988%** |

Floor `+0.473%` from launch overhead alone (80 × 0.49 µs × 0.812) is **above the
0.278% resolution floor ⇒ #48 cannot fail to be measurable.** Note the
mechanism: `gate_sp` moves 33 kB/call at 5 GB/s = 2% of ceiling, so the
*bandwidth* recoverable column is meaningless for it; the operative instrument is
the **§A4 dup/ser first-touch ratio 0.659**, which says fusion is the lever.
**The ratio picks the lever; dispatch count never does.**

### Rank 3 — ★ N5: wave-quantisation census of every custom decode kernel (NEW, free)

*The single highest value-per-cost idea in this file.*

For each of the ~13 custom decode kernels, extract from source the launch grid
and threadgroup size, compute **threadgroups launched**, and compare against the
M5 Max core count (~40) and the M4 Pro core count (20). Any kernel launching
fewer threadgroups than there are cores is under-filled *by construction*,
independent of its inner loop.

- We already know `sliding_fused_attn_ring_v1` launches **32** TGs and
  `full_fused_attn_grow_v1` launches **24** (`:1799-1800`, `:2316`) — both below
  a 40-core M5.
- Nobody has ever asked this of `residual_rms_router` (60% of ceiling),
  `shared_nvfp4_swiglu_qmv_rows1` (73%), `gate_sp` (2%), `router_top8` (0%).
- Deliverable is a one-page table: kernel, grid expression, threadgroup size,
  TGs launched, TGs/core, wave count on 20 and 40 cores, second-wave occupancy,
  and the binding occupancy term.
- **Cost: zero receipts, zero M5, one M4 session or even none — it is a source
  read plus `MTLComputePipelineState` queries** (§0.9.10 static-property
  corollary makes this M4-legal even for `_nax` kernels).
- **Value: it converts the 1380 µs low-efficiency class from four anecdotes into
  a ranked, mechanism-attributed work queue.** It could easily surface two more
  arms of the sliding-attention type.

### Rank 4 — ★ N4: restore provable non-aliasing to unlock compiler load hoisting (NEW, cheap)

The frontier read found a **zero-numerical-cost** performance bug class: in the
attention kernels the compiler cannot hoist next-trip K/V loads across the loop
because `k_cache`/`v_cache` are *also written* in phase 2 (`:1486-1487`), so
provable non-aliasing fails and memory-level parallelism is capped at whatever
the author hand-wrote.

Generalise: **audit all custom decode kernels for buffers that are both read and
written in the same kernel**, and for each ask whether the read pointer can be
qualified `const device` / given a distinct binding so the compiler can hoist.
Candidates are wherever a cache row is persisted and then re-read.

- This is a *compiler-visibility* fix, not an arithmetic change ⇒ the
  bit-exactness argument is trivial (same loads, same order of use).
- Cheap to test: change the qualifier, dump the generated MSL / measure per-call
  µs on M4.
- Pairs naturally with rank 1 R2/R3, and may make R2's hand-written 4-deep
  pipeline unnecessary.

### Rank 5 — ★ N3: static lane-utilisation census (NEW, free)

The attention kernels idle **28 of 32 simdgroups** through phase 1
(`:1425-1471`). Nothing in the ledger has ever asked, for the other custom
decode kernels, *what fraction of launched lanes does useful work*.

Deliverable: per kernel, the guarded regions (`if (sg < k)`, `if (lane < k)`,
`if (sg_active)`) and the fraction of launched threads active in each phase,
weighted by phase length. Pure source read. Combine with N5 into one report if
one student takes both.

Precedent that this finds real money: the gather-GEMM §0.9.8 finding that on the
median chunk **only 1 of 4 simdgroups is `sg_active`** — which is exactly why the
occupancy-currency law says *"any arm that increases per-threadgroup resource
use to buy overlap is self-cancelling; only arms that REDUCE it can move it."*

### Rank 6 — gather-GEMM D2 occupancy audit (free, local, M4-legal, UNOWNED)

Unchanged from round 8; brief is `research/GATHER_GEMM_REGIME_DESIGN.md` §2 and
§3-D2. Four deliverables: exact threadgroup bytes for the shipped instantiation
(resolve `BK_padded`/`Wtype`/`expert_groups` from the `quantized.cpp` host call
site, **do not guess**); `maxTotalThreadsPerThreadgroup` from the compiled
pipeline state (if < 128 the kernel cannot launch its 128-thread group);
occupancy arithmetic **naming the binding term**; price the `bounds` reduction
(`DARKBLOOM_BSEARCH_HOIST`) — **price only, do not flip it.**

Note this is now the *same audit shape* as N5/N3/Step 0 of rank 1. Consider
assigning all four to one student as a single "structural occupancy census" PR —
it is one hypothesis (*the scored kernels are occupancy-limited and the binding
terms are unmeasured*) with four instances.

### Rank 7 — `residual_rms_router` rpg8 → rpg4/2 (+1.28% central, UNOWNED)

60% of ceiling, 39 dispatches, 106 µs M4 recoverable. **Reframe: this is not an
independent idea, it is instance #3 of the rank-2 theme.** Do not assign it
before N5 reports, because N5 will say whether the deficiency is
rows-per-group (the assumed cause) or threadgroup fill (the cause in the
attention kernels). Assigning it blind risks a fifth wrong price.

### Rank 8 — M2 `lhs_indices` gather elision (+0.80–1.19%, central +0.95%)

Audited. Needs a **local screen first**. ⚠ **Same bytes as gather-GEMM
mechanism #3** — do not staff both; whichever runs first consumes the other's
prize. #3 remains HELD contingent on D1.

### Rank 9 — D-MLP depth-2 routed decode QMV staging (+1.57% central)

Bracket +0.96–2.24% and the estimate is an **upper bound**. Below the attention
work on both value and confidence.

### Rank 10 — shared-expert K1 (+0.78% central)

Instance #4 of the rank-2 theme. Same gating as rank 7: wait for N5.

### Rank 11 — nezuko `oproj_act` fusion (dup/ser ratio 0.601)

Legitimate fusion target (ratio well below 1) but `oproj_act_h64` already runs at
95% of ceiling, so the prize is launch overhead, not bandwidth: 40 dispatches ×
0.49 µs × 0.812 = **+0.24%**, *below* the 0.278% resolution floor as a solo arm.
**Rider only** — stack it onto #48's fold under policy 0.5.7, do not spend a
slot. Remains nezuko's.

### Rank 12 — bit-exact fused split-K NAX (+0.53%) / byte reclamation

Carried. Byte reclamation is becoming operationally urgent:
`LagunaRuntimeModel.swift` is 508,529 B against a 524,288 B cap with only
~3,700 B unallocated after frieren (~8,037 B) and fern (~4,000 B). Reclaim
levers: Metal-literal minification (54,251 B across 71 literals), the #27
instrument block (≈12,134 B, deferred until tanjiro finishes), ~108 stale
`DARKBLOOM_*` flags.

---

## 4. Explicitly forbidden / do not spend a student on these

- **Splitting attention positions across threadgroups, or reassigning ring slots
  to different simdgroups.** Changes the accumulator chain ⇒ not bit-exact ⇒
  fails the greedy-token gate.
- **Wider per-lane K/V loads in the attention kernels.** 16 lanes/slot would
  change the `simd_sum` reduction shape.
- **Replacing softmax `exp` with a pre-scaled `exp2`.** Changes rounding.
- **Removing the alpha-skip rescale** (`:1698-1706`).
- **Reopening gather-GEMM with a deeper prefetch, a wider `Ws`, or different
  barrier placement.** Two unconditional barriers (`:1725-1765`) mean D and M
  cannot overlap inside one threadgroup at all; the occupancy-currency law makes
  every resource-increasing arm self-cancelling.
- **Any further command-buffer or ops-per-buffer knob.** Closed axis.
- **Touching phase-1 text in `full_fused_attn_grow_v1`** (`rotary_pairs=32`,
  idle lanes 8-15, mscale double-rounding at `:1928-1946`).
- Reducing the attention epilogue's 3 barriers to 1 by having simdgroup 0
  `simd_sum` all 32 partials: changes the cross-simdgroup summation tree ⇒ not
  bit-exact unless proven identical, and barriers are only the *fourth*-ranked
  cause. Low value, high risk.

## 5. The R1 dual, held in reserve

If rank-1 Step 0 refutes the threadgroup-memory premise (i.e. the binding
occupancy term turns out to be simdgroup slots or registers, not the 18.4 kB),
then R1's plane-halving rationale weakens and the alternative is the **dual**:
*fewer, fatter threadgroups* — one TG handling all 8 query heads that share a KV
head, so the KV row is read once into threadgroup memory and reused 8× instead of
being requested by 4 separate pair-TGs. That trades GPU fill for a 4× reduction
in requested traffic, and it is bit-exact by the *same* argument (heads never
interact). Named here so the owner does not have to invent it under time
pressure. Do not run it speculatively — it is the branch Step 0 selects against.

## 6. Ownership map

| student | PR | scope | ranked channel |
|---|---|---|---|
| maple-tanjiro | #47 r1 | D2 → D1 → D4 → D5 → D3 dispatch-law closure | **HOLDS IT** (D2) |
| maple-fern | #48 r1 | fused norm+QKV+**gate** (rank 2, +2.99%) | next in line |
| maple-frieren | #35 r3 | C census → B (M4-only) → stacked-plane receipt (+1.71–1.83%) | after fern |
| maple-nezuko | #44 r3 | one M4 profiled ABBA session; merge pre-committed; **next = rank 1** | none |

All four staffed; no free slot. Rank 3/4/5/6 (the structural occupancy census)
is the work to assign the moment one opens, and it needs **no receipt**, which
makes it schedulable without touching the channel.
