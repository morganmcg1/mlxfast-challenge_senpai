# QUEUED BRIEF — Fused decode attention: occupancy rewrite of `sliding_fused_attn_ring_v1`

- Author: meridian (advisor)
- Written: 2026-08-05 15:30Z
- Status: **QUEUED, NOT ASSIGNED.** Written ahead of a free slot so dispatch has zero latency.
- Presumptive owner: **@maple-nezuko** (named as her next preview in the #44 r3 request; she authored the per-dispatch table this brief is priced from).
- Queue rank: **1**. Largest priced item in the programme.
- Base at time of writing: `d267ebda88c50a6e1b539d9265050dbaae00c268`
- Design evidence: frontier design review, 2026-08-05 15:20-15:25Z, task `8dd61eee-216d-55d7-906d-10411e8e0398`

---

## 0. Why this is rank 1

`sliding_fused_attn_ring_v1` is the single largest pool of recoverable time in the
decode step, and it is the only large pool where the mechanism is *named and
source-verified* rather than hypothesised.

| quantity | value | source |
|---|---|---|
| dispatches/step | 30 | decode dispatch inventory |
| M4 µs/call | 22.34 | `research/nezuko-pr9-dispatch-fusion.md:120-144` |
| M4 µs/step | 670 | same |
| MB/call (unique) | 2.097 | same |
| MB/step | 62.91 | same |
| achieved GB/s | 94 | same |
| M4 ceiling | 260.2 GB/s | `research/nezuko-decode-roofline.md` |
| **% of ceiling** | **36%** | same |
| **M4 recoverable** | **428 µs/step** | same |
| M5 byte floor @ 651.8 GB/s | 96.5 µs | programme rate table |

Priced through the **residual-class** conversion factor `×0.812` (1.340 ms M5
residual / 1.650 ms M4 residual — *not* the wall-clock ratio 0.501) and the
exchange rate `1 ms decode T = 14.862 % of score`:

| conversion | M5 µs | % of score |
|---|---:|---:|
| pessimistic (×0.501) | 214 | **+3.19%** |
| **central (×0.812)** | **347** | **+5.16%** |
| optimistic (×1.0) | 428 | +6.36% |

**Use +5.2% in all communication.** My earlier +8.5% (573 µs) is retracted; the
only surviving mentions are inside the §0.9.11a retraction text of
`research/CURRENT_RESEARCH_STATE.md` (~lines 686-687).

Companion kernel `full_fused_attn_grow_v1`: n=10, ~23.5 µs/call, 235 µs/step,
2.621 MB/call, 112 GB/s, **43% of ceiling**, ~130 µs recoverable ⇒ **+1.57%**
central. **Combined pool 453 µs ⇒ +6.7%.**

### Why the lever is a kernel rewrite and not fusion

The §A4 dup/ser first-touch ratio for `sliding_fused_attn_ring_v1` is **0.971**
(`research/nezuko-pr32-r2-report.md`). A ratio near 1 means the kernel's cost is
already its own, not a first-touch/launch artefact ⇒ **fusion cannot help; only
a better kernel can.** Compare `oproj_act` at 0.601 and `gate_sp` at 0.659,
where fusion *is* the lever (that is @maple-fern's #48).

### Resolvability

Policy 0.5.8 receipt-resolvability floor is 3σ = **42.6 µs/step**. The central
recovery is **347 µs = 8.1× the floor**. This arm cannot fail to be measurable.
Against the measured promotion bar (+1.461% at P=50%, +1.830% at P=80%,
+2.018% at P=95%) even the pessimistic **+3.19%** clears P=95% comfortably.

### Programme context the owner must be told

The shipped editable tree has been **byte-frozen since 08-04 21:03Z** — three
merged PRs and ~18 hours of zero net editable bytes. And renormalised `ns`
across our 23 ranked receipts says the **control (frozen frontier) is our best
arm at ns 2.544360**; our board-leading `officialScore` 2.545892 has ns
2.538013, i.e. 0.25% *worse* than doing nothing, carried by a baseline draw of
1.003104. **This arm is the programme's best chance to ship real mechanism.**

---

## 1. Source anatomy (verified — do not re-derive, but do re-read before editing)

All line numbers are `Sources/MLXFastModel/LagunaRuntimeModel.swift` at
`d267ebda` unless stated.

- Kernel string literals: sliding at **`:1382`** (opened `:1381`), full at
  **`:1857`** (opened `:1856`). Both are JIT `MLXFast.metalKernel` strings —
  **no `.metal` / `mlx-generated/*.cpp` twin to keep in sync.**
- Invoked at **`:5893-5905`**. Full-fused engages only from decode step 2
  (`:5797-5800`).
- Launch geometry: `grid = ((heads/2)*1024, 1, 1)`, `threadGroup = (1024,1,1)`
  — **`:1799-1800`** (sliding), **`:2316`** (full).
- Head counts from `LagunaConfig.swift:21-26`; kernel constexpr `gqa=8`
  (`:1392`) and `gqa=6` (`:1866`).
  - sliding: 64 query heads ⇒ **32 threadgroups**, 8 KV heads, **4 TGs re-read
    each KV head**
  - full: 48 query heads ⇒ **24 threadgroups**, 8 KV heads, **3 TGs re-read
    each KV head**
- One TG serves a **pair** of query heads: `head0 = pair_tg*2` (`:1408-1410`).
- 1024 threads = **32 simdgroups** (`BN=32`). Simdgroup `sg` owns ring slots
  `i ≡ sg (mod 32)` — 16 slots — visited in **increasing order** as a serial
  online-softmax chain, executed as 8 trips of a hand-written **2-deep**
  pipeline (`for (; i+BN<N; i+=2*BN)`, `:1529-1530`).
- Within a slot each of 32 lanes owns 4 of the 128 head-dim elements
  (`qk_per_thread=4`, pointer setup `:1499-1504`); the QK dot reduces with
  **two `simd_sum`s per slot** (`:1556-1557`, `:1592-1593`).
- K/V loads are 8-byte `vec<bfloat,4>` (`T_LOAD_K/V`, `:1719-1739`) — **already
  vectorised; "use wider loads" is not the fix.**
- Per-slot branch substitutes the just-computed row from threadgroup memory when
  `i == widx` (`:1533-1534`); the device slot `widx` is stale/racing by design
  (`:1478-1489`, documented `:1369-1376`).
- Phase 1 (`:1425-1471`): **only simdgroups 0-3 of 32** do Q/K RMSNorm + RoPE
  and the V copy. **28 of 32 simdgroups idle** until the barrier at `:1471`.
- Phase 2 (`:1478-1489`): one TG per KV head persists the new K/V row.
- Epilogue (`:1626-1682`): cross-simdgroup combine via threadgroup planes +
  `simd_sum`, two rounds, **three barriers**; final store by lane 0 of each
  simdgroup only (`:1684-1693`). Alpha-skip rescale at `:1698-1706`.
- **Threadgroup memory ≈ 18.4 kB/TG**: `outputs[4*BN*BDP]` = 4×32×33 floats =
  16.9 kB (`:1495`) + `max`/`sum` 512 B (`:1496-1497`) + four bfloat rows 1 kB
  (`:1416-1419`).
- Full kernel differs by: runtime `N` (`:2008`), capacity-strided cache
  (`:1958`), a **single-slot tail** (`:2099`), and partial-rotary phase 1
  (`rotary_pairs=32`, mscale double-rounding, `:1876-1946`).
- Steady-ring no-tail assumption in the sliding kernel is valid **only** because
  `fusedRingPrepare` gates on `offset >= maxCacheSize`
  (`Vendor/mlx-swift-lm/.../KVCache.swift:710-715`); benchmark decode always
  enters wrapped (512-token seed).

**Traffic accounting.** 2.097 MB/call is exactly one unique copy of
8 KV heads × 512 positions × 128 dims × bf16 × {K,V}. The counters therefore see
**deduplicated** traffic; *requested* traffic is already 4× that (one request set
per pair-TG sharing a KV head). Remember this when reasoning about R1.

---

## 2. Diagnosis: why 36% of ceiling

Ranked by confidence and size.

1. **Too few threadgroups, and one TG per core (high confidence, dominant).**
   32 TGs (sliding) / 24 (full), each pinned to one GPU core because 18.4 kB of
   threadgroup memory against a 32 kB/core budget admits only one resident
   1024-thread TG. On a ~40-core M5 Max, **32 TGs cannot fill the GPU even
   once** — ≥20% of cores are idle by construction for the sliding kernel and
   ~40% for the full kernel. On a 20-core M4 Pro it is two waves (20 + 12, the
   second 60% full). This is a wave-quantisation *and* an overlap problem: with
   one TG per core there is nothing to hide the softmax ALU stretch behind.
2. **Burst-then-stall issue pattern per simdgroup (high, co-dominant).** Each
   trip issues only 4 vec4 loads (32 B/lane in flight) then runs a long
   dependent ALU stretch: 16 FMAs, **4 serialised `simd_sum` shuffle trees**
   (~5 dependent shuffle+add steps each), 4 `exp`s, 32 accumulate FMAs
   (`:1537-1616`). Apple GPUs issue in order, and the compiler **cannot** hoist
   next-trip loads across the loop because `k_cache`/`v_cache` are also
   *written* in phase 2 (`:1486-1487`) — provable non-aliasing fails, so
   memory-level parallelism is capped at the hand-written 2-deep pipeline.
   Memory idles during softmax; ALUs idle during loads.
3. **Reduction serialisation on the critical path (medium-high).** Roughly 40%
   of loop instructions are shuffle/scalar reduction work. The order is the
   bit-exactness contract and must not change; the fix is to *overlap* it, which
   is impossible at one TG per core.
4. **Phase-1 and epilogue serialisation (medium, smaller).** 28 of 32
   simdgroups idle before the `:1471` barrier with **no ring loads in flight**;
   the epilogue adds three more barriers.

**Explicitly NOT the cause** (do not spend time here): short scalar loads (loads
are already 8-byte vec4, `:1719`); dispatch count (30 is given, and the dup/ser
ratio 0.971 says launch overhead is not the cost); DRAM bandwidth
(94 GB/s ≪ 260 GB/s).

---

## 3. Deliverables

### Step 0 — free static occupancy audit (M4-legal, no edits, do this FIRST)

The dominant diagnosis rests on the premise *"18.4 kB of threadgroup memory is
the binding occupancy term, so one TG per core."* **Verify the premise before
paying for a rewrite.** This is the §0.9.10 static-property corollary: static
kernel properties are M4-legal even for kernels whose ranked behaviour is M5's.
Precedent: @maple-fern's merged `research/nax_msl_compile_check.sh`.

Report, for the shipped instantiation of **both** kernels:

1. **Exact static threadgroup bytes** from the compiled
   `MTLComputePipelineState` (`staticThreadgroupMemoryLength`), not from
   arithmetic on the source. My 18.4 kB is a source-read estimate.
2. **`maxTotalThreadsPerThreadgroup`.** If it is < 1024 the kernel cannot launch
   its declared threadgroup and something in my reading is wrong — say so loudly
   and stop.
3. **The binding occupancy term, named.** Threadgroups per core admitted by
   (a) threadgroup memory, (b) simdgroup slots per core, (c) register file.
   A 1024-thread TG is 32 simdgroups; the programme's working figure for
   simdgroup slots per core is 24 (`research/CURRENT_RESEARCH_STATE.md` §0.9.8).
   **If 24 is right, a 32-simdgroup threadgroup cannot be resident at all and
   the occupancy story is different from mine.** Resolve this from the device
   and the pipeline object, not from a blog post. Name which term binds.
4. Same four numbers for `full_fused_attn_grow_v1`.

**Step 0 is a complete deliverable on its own.** If it refutes the
threadgroup-memory premise, say so and I will merge the refutation — that is a
clean retirement and it redirects the rewrite rather than wasting an M5 receipt.

### Step 1 — R1: one query head per threadgroup (highest ceiling)

Change `head0 = pair_tg*2` (`:1408-1410`) to one head per TG and grid to
`heads*1024`; drop the paired streams; halve `outputs` from 4 planes to 2
(`:1495`) so threadgroup memory falls to ~9.9 kB.

- Sliding: 32 → **64 TGs**. Full: 24 → **48 TGs**.
- **Bit-exactness argument:** head0 and head1 never interact numerically. Every
  accumulator, every `simd_sum`, and every epilogue combine is per-head. The
  slot→simdgroup schedule and the visit order are unchanged. **This is the
  strongest bit-exactness argument available in this kernel and it is why R1 is
  the arm, not a position split.**
- **Named risk:** *requested* K/V traffic doubles (4 → 8 TGs per KV head).
  Unique DRAM traffic is unchanged, but L2/fabric must absorb 2× the requests.
  At 94 GB/s against a 260 GB/s M4 ceiling there is headroom, so M4 should
  screen this honestly. **Report achieved GB/s before and after.**
- Expected recovery: **40-60% of the 428 µs** if the premise in Step 0 holds.

### Step 2 — R2: deepen the load pipeline 2 → 4 slots

Load K/V for `i, i+32, i+64, i+96` at the top of the trip, then run the four
online-softmax updates **in that exact slot order with the same accumulator
sequence**. The loads are order-free reads; the arithmetic is textually the
current two iterations concatenated, so the floating-point order is identical.
Doubles loads in flight to 64 B/lane and halves the number of ALU-only gaps the
in-order front end exposes. Register cost ≈ +12/thread; occupancy is not
register-bound (confirm against Step 0). Expected recovery: **15-30%**.

Note the framing: the threadgroup is already at the 1024-thread hardware
maximum, so the sanctioned "more parallelism within a threadgroup over
positions" can only mean **more memory parallelism per lane**, not more threads.

### Step 3 — R3 (optional): pre-barrier prefetch of the first pipeline stage

Have all 32 simdgroups issue their first K/V loads *before* the phase-1 barrier
(`:1471`), overlapping phase-1 ALU with the first DRAM latency. The `widx` slot
must still take the substitute value after the barrier — **load unconditionally
and select, do not branch**. The discarded device read of `widx` may race
another TG's phase-2 write; that is benign only because the value is never
consumed, so keep the select. Expected recovery: **5-15%**.

### Step 4 — ranked receipt of the best sliding-only arm

Ask me for the channel before submitting. Requirements:

- nezuko-style **pre-registered decision rule** committed *before* the run.
- `research/run_upstream_equivalence.sh` (never a bare `swift test` filter).
- The public 64-step drift tripwire.
- Report **`ns` first, `officialScore` second**, plus hand-computed legacy band
  ratios (decode ∈ [0.980, 1.053], prefill ∈ [0.952, 1.053] — the band is NOT
  retired, only the local notice was deleted).
- Compare against the fixed published control `c3ce66ec` (ns 2.544360), which
  gives a 0.278% resolution floor at one receipt.

### Step 5 — NOT in this PR

Porting the winner to `full_fused_attn_grow_v1` is a **separate PR**. Its
runtime `N`, per-simdgroup trip counts and single-slot tail (`:2099`) make a
4-deep pipeline the likeliest bug site in either kernel. Do the sliding kernel
first: bigger pool, fixed `N=512`, no tail.

---

## 4. Correctness traps (all five are real)

1. **Slot order is reduction order.** Any rewrite must keep slots
   `sg, sg+32, sg+64, …` on the *same* simdgroup in *increasing* order.
   **Splitting positions across threadgroups, or reassigning slots to different
   simdgroups, is not bit-exact** and will fail the greedy-token gate.
2. **`widx` substitution.** Device slot `widx` is stale/racing by design. A
   deeper pipeline needs its **own `sub` flag per in-flight slot**; a prefetch
   variant must *select*, not skip.
3. **Steady-ring no-tail assumption** holds only via the `fusedRingPrepare` gate
   at `KVCache.swift:710-715`. Do not remove the wrap handling on the belief
   that decode is always wrapped — the gate is what makes it true.
4. **Do not touch phase-1 text in the full kernel.** `rotary_pairs` is 32 there
   vs 64 in sliding, phase 1 has idle lanes 8-15, and there is **mscale
   double-rounding** at `:1928-1946`. The variant difference is *query heads*
   (64 vs 48); `head_dim` is 128 in both.
5. **Do not remove the alpha-skip rescale** (`:1698-1706`).

Also forbidden as non-bit-exact: **wider per-lane loads** (16 lanes/slot would
change the `simd_sum` reduction shape).

---

## 5. M4 vs M5 screenability

Both kernels are JIT `MLXFast.metalKernel` strings (`:1381`, `:1856`) and are
**not `_nax`-gated**, so they execute on M4 — the M4 per-dispatch profile proves
it. **This is the rare large arm that is M4-screenable.**

**M4 can decide:** per-call µs deltas for R1/R2/R3, whether R1's doubled L2
traffic backfires, achieved GB/s before/after, and bit-exactness. If a public
golden disagrees on M4, test the unchanged base first and use
`MLXFAST_LOCAL_ALLOW_GOLDEN_DRIFT=1` only when the base shows the same near-tie
divergence.

**M5 decides the final sign and magnitude.** Wave quantisation depends on core
count: 32 TGs is ~2 waves on a 20-core M4 Pro but a single under-filled wave on
a ~40-core M5 Max, so R1's win *should* be larger on M5 — but `AGENTS.md` warns
explicitly that threadgroup geometry can change sign across core counts. Record
core count and architecture in every measurement.

---

## 6. Contract

- **Editable surface:** `Sources/MLXFastModel/LagunaRuntimeModel.swift` only.
- **Byte budget: re-issued at assignment time.** At the time of writing
  `LagunaRuntimeModel.swift` is 508,529 B against a 524,288 B per-file cap
  (15,759 B spare, of which ~8,037 B is allocated to @maple-frieren's #35 and
  ~4,000 B to @maple-fern's #48). Provisional allowance **net ≤ +3,000 B**.
  R1 should be roughly byte-neutral; R2's unrolled pipeline is the growth risk.
  If more room is needed the reclaim levers are Metal-literal minification
  (54,251 B across 71 literals) and the #27 instrument block (≈12,134 B,
  currently deferred until @maple-tanjiro finishes with it) — **ask, do not
  self-serve.** Report the file size in the result.
- **One hypothesis per PR.** The hypothesis is: *the fused decode attention
  kernels are occupancy- and memory-parallelism-limited, and increasing
  threadgroup count and loads-in-flight within the existing bit-exact reduction
  structure recovers a large fraction of the 428 µs residual.* R1/R2/R3 are
  variants of that one mechanism, so they belong in this PR as a ladder.
- **Evidence contract:** this programme has **no W&B runs**. Cite ranked
  `mlxfast` receipt IDs and `research/*.md` paths with line numbers.
- **Ranked channel is scheduled by me.** Exactly one in-flight submission per
  account and all four students share `morganmcg1`.
- **Standing docs-only rule** applies to `baseline_advanced` events: intersect
  `git diff --name-only <assigned>..<current>` with the 97 `editablePaths`;
  empty ⇒ accept the new base, keep evidence, no rebase, no re-run.

## 7. Recommended execution order

**Step 0 → R2 (sliding only) → R1 (sliding only) → R1+R2 → ranked receipt.**

R2 first because it is the lowest-risk edit and its bit-exactness is textual.
R1 second because it has the highest ceiling but the one named traffic risk.
Then the combination, then the channel.
