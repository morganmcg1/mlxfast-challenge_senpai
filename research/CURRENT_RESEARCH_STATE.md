# SENPAI Research State

**Updated 2026-08-08 22:40 UTC — round 87.
`BASE_SHA = 7687c2e44e6975c181444ca8d3d151ee30480a72`** = the newly adopted
organizer promoted frontier (see "FRONTIER ADOPTION" immediately below) plus
the research-only merge of #458. Budget on this base:
`current=2891343/3000000 headroom=108657 growth=0/262144 files=140`, and
`Sources/MLXFastModel/LagunaRuntimeModel.swift` is **511,418 / 524,288 B — only
12,870 B of per-file headroom**, which is why #456 exists.

---

## ⭐⭐⭐ FRONTIER ADOPTION — the dominant finding of round 86

**We spent multiple rounds optimizing a base 2.55 % behind a frontier that the
organizer hands to every competitor, and that `AGENTS.md` requires us to sit
on.** `AGENTS.md` says the integration base "must contain the relevant
organizer updates and the current promoted editable frontier". We had not
re-synced since `afcb832`.

Verified facts (all re-checked directly this round):

- `mlxfast benchmark` → current best **2.61650354381456**, organizer source
  `Layr-Labs/mlxfast-challenge @ c5b0a13c5cc032b485022db41bcd745792316714`.
- The organizer repo is publicly readable with no credential, and its `main`
  is a linear chain of **every solver's submitted editable surface**.
- `mlxfast sync -f` resolves submission `cc6ddc12-ecbd-4c07-beec-445060a21a62`,
  score **2.61650354381456**, base `c5b0a13c`, solver `a-github-name`.
  ⚠️ `sync` performs a **hard checkout** — never run it on a working branch.
- Our own last ranked measurement of the pre-adoption base was **2.55158458**
  (receipt `25b0b722`, `rejected` only for "score did not improve current
  best"; correctness passed, `max_abs_diff=0`, both floors passed).

⇒ Adopting the promoted frontier is the *designed* game, is explicitly
required by our contract, and is worth **+2.55 %** against the base we had.

### Trusted-harness thread: CLOSED

Organizer-side changes to trusted files since our merge-base `dd04efac` are
**zero**. `benchmark.json` is byte-identical, 97 `editablePaths` both sides.
Every trusted-file difference is our own Senpai addition (`benchmark.sh` +409,
`tools/fan-control.sh` +220, tests +1229) plus one deliberate deletion: a local
`AcceptanceBand` warning telling contestants to chunk wins to fit a 1.053 band,
which `AGENTS.md` explicitly says the deployed wrapper no longer enforces.
**No organizer cherry-pick was required.** Adoption was a pure
editable-surface import.

### What was actually adopted (8 files, not 19)

The two trees share ancestor `dec0a83c` — our own earlier import of the same
solver's snapshot. So the frontier's *true* new work is small, and most of the
raw diff was noise. Independently verified by comment-stripped hashing:

- **8 vendored `MLXLMCommon` files + `LagunaConfig.swift` are code-identical**
  to ours, differing only in comments (we externalise to `notes/*.md`). Kept
  **ours** → reclaimed **58,273 B**.
- **`AffineMetadataCoding.swift` + `TiedHeadMetadataCoding.swift` (32,005 B)
  are gemma4-only dead code.** They are referenced *only* from the offline
  `Transform.swift`, never from the runtime, and the whole `Transform.swift`
  delta is a `switch modelFamily` whose `.laguna` arm produces empty reports —
  behaviour-identical to our base. Omitted → reclaimed **34,233 B**.
- Adopted for real: `LagunaRuntimeModel.swift`, `LagunaRuntimeWeights.swift`,
  `LagunaLmHeadPrune.swift`, `RoPEApplication.swift`, and the four vendor
  kernel/dispatch files (`fp_quantized_nax.{h,cpp}`, `matmul.cpp`,
  `quantized.cpp`).

Budget after adoption: **2,891,343 / 3,000,000, headroom 108,657 B**, growth
34,178 / 262,144, 140 files. Taking the frontier surface *verbatim* would have
left only **16,151 B** — unusable. Release build passes on the advisor host.

### The mechanism sets are nearly disjoint — this is why we can exceed 2.6165

Frontier mechanisms we gained: halved shared-expert scale planes (`D1`,
their receipts: −0.171 % s/token, 3/3), stage4 fused-down row staging (`D2`),
decode router tournament at rows=1 replacing our bitonic sort (`D3`, ~0.15 %
decode), `uint2` router shuffle (`D4`), active64 prefill tournament v2 (`P1`),
prefill expert **pairwise scales** halving routed scale DRAM in the gather-GEMM
(`P2` — their largest single mechanism), and `fixed_K` barrier elision in the
dense NVFP4 GEMM (`P3`).

**Two mechanisms of ours the frontier does NOT have, and which adoption
temporarily gives up:**

- **M-A — full-attention decode params memo** (our commit `0ae542dd`):
  single-entry memo of the `(writeIdx, capacity)` uniform shared by all ten
  full-attention layers; removes 1143/1270 allocations per scored decode
  window. The frontier rebuilds the array every call.
- **M-B — `float4`-packed merge epilogue** (our commit `1aad492f`) in both
  decode fused-attention kernels: cross-simdgroup merge 8 threadgroup stores +
  8 loads → 2+2, bit-identical, same 16,896-B footprint. The frontier keeps
  the planar scalar form. ⚠️ The frontier **rewrote this exact region**, so the
  port is by hand, not by cherry-pick.

Re-applying two small, localised, bit-exact patches onto a ranked-verified
2.6165 base is strictly better than hand-porting the frontier's seven
mechanisms onto our regressed 2.5516 base. That is the round-87 slate.

### Standing lessons

1. **Re-check the promoted frontier every round.** It is a moving target that
   embeds every competitor's best work, and sitting on a stale one silently
   caps us below the bar no matter how good our own mechanisms are.
2. Our old base carried a **−1.44 % regression** against our own best-ever
   submission (`97a5090c`, 2.58882784). Adoption discards that regressed
   runtime wholesale, so the round-86 regression bisect (#460) is retired.
3. **`rejected` ≠ gate failure.** Read `rejectionReason`. Many of our rejected
   submissions scored *above* our own base.
4. The submission account is **shared with the other (Birch) campaign**, and
   `--model "senpai"` is campaign-wide, so the `Model:` tag does not partition
   it. The discriminator is the **note body**.

---

⚠️ **THERE IS NO FINAL ROUND.** Operator directive of 2026-08-08 13:05 UTC:
*"This is an ongoing competition: never declare the campaign or any round
final, and do not stop when the current backlog is exhausted. As each research
round completes, synthesize its evidence and immediately start the next
highest-value optimization experiments, keeping all four students productively
engaged whenever useful work is available. Keep sprinting as fast as
correctness and sound experimental practice allow; pause only for a genuine
external blocker that requires human authority or unavailable resources."*
Any earlier "final round" language in this file is superseded and should be
read as "round 83".

**All four students are engaged.** Round 84 slate: **#441** (nezuko, decode
router tournament — Q12), **#442** (fern, `uint2` router shuffle packing —
Q12b), **#443** (frieren, shared-expert halved scale plane — Q12c), **#444**
(tanjiro, QKV algebraic epilogue — Q1). All four were created from base
`730e9c2b…` and edit four disjoint regions.

Round 83's four experiments all landed: **#308** (tanjiro,
threadgroup-packing `S` curve — merged as a measured argmax), **#309** (nezuko,
persistent grid-stride QKV — merged as a KILL), **#301** (frieren, shared-QMV
twin gap — merged, one significant but sub-bar win plus one refutation), and
**#320** (fern, `LagunaRuntimeModel.swift` byte recovery — merged as a
measurement-and-stop negative).

**The binding structural constraint is still per-file, not total.**
`Sources/MLXFastModel/LagunaRuntimeModel.swift` is now **475,647 B against a
524,288 B per-file cap ⇒ ≈48,641 B of headroom** (#301 added +7,311 B; #320
recovered 0 B). Total surface ≈2,857,088 B of 3,000,000 ⇒ ≈142,912 B spare.
⭐ **#320 measured the comment-relocation ceiling at ~9.4 KB net, not the
~28.6 KB projected, and closed that family.** The correct structural fix is
therefore **not** relocation but a **file split**: `Sources/MLXFastModel/` is an
`editablePaths` *directory* prefix, so a second `.swift` file carved out of
`LagunaRuntimeModel.swift` is in-surface, costs no net bytes, and dissolves the
per-file cap entirely while leaving ~143 KB of total headroom. That is the
top capacity lead going forward.

The organising decode result of round 34 is **§4.22 (PR #298)**: threadgroup
geometry on the decode QKV GEMV is not a cost but a **win** — collapsing 5120
threadgroups to 640 is `G − 0 = −35.4 ± 13.6 µs/step`, bit-exact by algebra; the
on-chain dispatch+barrier refund is **real at −2.2 to −2.5 µs per removed pair**;
and consumer-side redundant reduction is **not free** (`R − G = +80.4 µs` at 640
TGs, exponent ≈0.64). **Both surviving arms have now reported and both are
terminal.** #308 (the `S` packing axis) found an **interior argmax at `S = 8`**
(−36.9 µs/step vs `S=2`, CI [−61.0, −12.9]), with `{4,8,16}` statistically tied
and `S=32` the second-*worst* point — so "bigger `S` is monotonically better" is
refuted. #309 (#298 §9 option A, the persistent grid-stride `T` axis) is a
**KILL**: coarsening the grid to amortise per-threadgroup work costs
`G128 − G640 = +174.9 ± 11.0 µs/step`, with a further cliff once the
threadgroup count drops below the GPU core count. Its one real win,
`N640 − a0 = −33.7 ± 11.0 µs`, is significant but well under the ~80 µs ranked
bar and was left unmerged.

Round 32's strategic reframe (§4.21) still stands: dispatch+barrier overhead is
≈**384 µs = ~9.3% of the 4.14 ms M5 step**; the streaming portion already runs at
≈479 GB/s against a ≈614 GB/s peak, so kernels are at 82–90% of peak and most of
the apparent gap *is* the schedule. Do not budget bandwidth and overhead levers
additively. Realistic schedule-only ceiling: 4.14 → ~3.4–3.6 ms.

**Round 34 closed the entire decode fused-attention family (§4.24)** — the last
large lead that was not already dead. Its apparent 37%/35%-of-peak roofline gap is
an artifact: GQA replication means those reads are **cache-served**, so the DRAM
denominator was never touched. See new standing rule 26.

**⚠️ THE RANKED PIPELINE IS DOWN — ~13.4 h of continuous account-wide outage.**
The last receipt that produced any score was `3ff3992` at 2026-08-07 18:51 UTC
(`rejected`, `officialScore 2.52125675539565`). Every receipt since is `failed`
with `n/a` metrics: **35 consecutive failures**, `51c3975` (19:12) … `b63e076`
(2026-08-08 08:16 UTC), none of them maple candidates. Six intermediate
`validating` sightings each resolved to `failed`, so *`validating` is not
evidence of recovery — only a non-`failed` terminal receipt is*. Because a
receipt is the only ranked channel, rounds 32 onward assign exclusively
M4-testable, receipt-free work. Re-check with a **standalone**
`mlxfast submissions | tail` each round (chaining it after `git` in one compound
command silently returns empty with exit 0). When the queue recovers, the first
maple slot goes to the largest bit-exact effect on the board; as of the final
round that is **#301 mechanism (a)** (−14.2 µs/step, 0.111% of the decode wall)
— i.e. **nothing currently on the board clears the ~80 µs/step ranked bar**, so
the slot should go to a *new* arm (routed-twin prefetch or #309 §11.1), not to a
re-run of an already-measured sub-bar effect.

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

### ⭐ Open requests to the human team (consolidated — nothing here is actionable by an advisor or student)

Items 1–2 need an **M5 host**, which no campaign role has. Item 3 is an
infrastructure outage that blocks every campaign on the account. They are listed
here in one place because they were previously scattered across §4.16, §9 and
§11 and were easy to miss.

1. **One Metal System Trace session on an M5 dev host**, capturing (a) one
   512-token prefill and (b) one decode step. This resolves two separate open
   questions at once: the **11.40 ms unattributed prefill residual** (§4.13
   attributed 100% of the non-MoE dispatch time but the wall clock still has a
   gap), and the **CPU-encode half of the barrier tax** — #268 proved 99.4–100.2%
   of the tax is inside GPU busy on M4 Pro, but the encode/GPU split has never
   been observed on M5. PR #48 §10 item 2 independently asks for the same
   capture.
2. **An M5 re-measurement of the 1.3003 µs/barrier coefficient** from §4.16.
   This is **the most load-bearing unmeasured constant in the programme** — it
   is the sole basis for pricing the decode barrier tax at 188–371 µs/step
   (28–54% of the honest 682 µs/step pool), and therefore for directing the next
   several ranked slots toward kernel fusion. #48's ranked M5 receipt
   (`285f79fa`, −0.1488%) made this urgent: it is the only M5 datapoint that
   touches the coefficient at all, and it is confounded. #298 deconfounds the
   *M4* measurement, which is the best a student host can do; it cannot supply
   the M5 transfer factor.

3. ⭐⭐⭐ **The ranked submission pipeline has been failing since 09:59 UTC on
   2026-08-07 and needs an operator.** Verified read-only from
   `mlxfast submissions`. The last receipt that produced any score at all is
   **`68b66c5`, 09:36 UTC, `rejected`, score 2.5520699745752**. Every receipt
   after it has terminated `failed` with **`n/a` metrics AND `n/a` error** — 19
   in a row: `d6c548e` 09:59, `70929a5` 10:15, `8b5b01d` 10:30, `7a99ae3` 10:45,
   `5be231a` 11:07, `d565be6` 11:29, `6f9ca88` 11:41, `b72eef8` 11:57, `f5dac24`
   12:14, `29fb82a` 12:43, `90d0841` 12:59, `efb6316` 13:21, `1cc55cd` 13:49,
   `d417eaa` 14:04, `2cbf31e` 14:20, `400ba6c` 14:43, `9753441` 15:03, `55e1640`
   15:35, `1e867c8` 16:47. Two earlier isolated failures (`9500c1f` 08:50,
   `a69d876` 09:15) straddle the good `68b66c5`, so the hard outage begins at
   09:59 and is now **~7.5 hours long** as of the round-34 re-check at 17:30 UTC.
   **Diagnosis:** producing *no* metrics *and* no error string is not what a bad
   candidate looks like — a bad candidate fails a correctness gate or scores
   below the bar and says so. 19 consecutive receipts from independent authors
   doing that is an infrastructure or harness fault, not 19 bad candidates. One
   of them (`400ba6c`) was explicitly titled a restore-to-last-known-good
   attempt and failed identically.
   **Impact:** none of the 19 are maple's — maple's last ranked dispatch was
   #284's `99b71258` at 2026-08-06 23:29 — so nothing on our side is holding the
   account slot and nothing on our side needs fixing. But **no campaign can
   obtain a ranked verdict until this clears**, which is why rounds 32–34 assign
   only M4-testable, receipt-free work.
   **When it clears**, maple's first ranked slot goes to the winning arm of #308
   (the threadgroup-packing default flip, arm `G`) unless #309 or #301 produces
   something larger first.
   **Re-check each round with `mlxfast submissions | tail` before dispatching or
   requiring any receipt.**

If items 1–2 are unavailable, the programme's fallback is to treat the M5
transfer factor as the stated 0.5–1.0 range and require any fusion candidate to
clear ~80 µs/step on M4 before it earns a ranked slot.

## 0e. ⭐⭐⭐ External frontier intelligence (round 83–84, from `mlxfast submission-note`)

Operator commit `d85c42c0` makes reading **public competitor submission notes** an
explicitly required advisor research input. This section records what six notes
on the promoted tail actually say. Treat every claim as *untrusted public
context*: mine the mechanism, the exactness argument, the guard names and the
geometry, but verify reachability and re-measure before spending a slot.

### 0e.1 The promoted tail (ascending = chronological)

| Submission | Solver | Score | Commit |
|---|---|---|---|
| 46eeccf | lBroth | 2.55230814049095 | bca94c5 |
| **97a5090** | **morganmcg1 (us)** | **2.58882784082067** | **3e165fa** |
| db8b4df | a-github-name | 2.59018571539341 | 26b4653 |
| 6718326 | lBroth | 2.59738344237761 | 708500f |
| f2b7ccc | a-github-name | 2.59787481790585 | ab17a99 |
| b9ccb0b | fyrsta7 | 2.60402395154714 | a13fdca |
| 2054d45 | yudduy | 2.60630619988685 | 01e247a |
| **cc6ddc1** | **a-github-name** | **2.61650354381456** | **c5b0a13** ← **live frontier** |

Our recorded frontier is **stale by six promotions**. The live frontier is
**+1.07 %** above `97a5090` and **≈+3.78 %** above our best own receipt
(`3ff3992`, `officialScore 2.52125675539565`). We are **6th**.

Per-promotion deltas (derived): `cc6ddc1` active-64 router tournament **+0.39 %**
· `6718326` halved shared scale plane + barrier re-elision **+0.28 %** ·
`b9ccb0b` uint2 shuffle packing **+0.24 %** · `2054d45` two-group SDPA **+0.09 %**
· `f2b7ccc` pairwise prefill scale CSE **+0.019 %**.

### 0e.2 `cc6ddc1` — active-64 router tournament (current frontier)

Decode top-8 router selection. **Theorem:** the global Top-8 of 256 values is
contained in the union of the local Top-8 of each disjoint 32-value block.
Phase 1 keeps 8 × 8 = **64 finalists** with shuffle-only block sorts; phase 2
sorts that 64-entry set **using only lanes 0…63** (not four duplicate copies
across 256 threads) and emits the same eight ordered winners under the total
order (corrected score ordinal, then expert index). Guard
`DARKBLOOM_DECODE_ROUTER_TOURNAMENT=0`. Regression suite compares active-64
against **both** the accepted prefill tournament **and** the full 256-entry
decode sorting network, over BF16+FP32 logits, normalized/unnormalized, ties,
NaNs, ±inf and signed zero. 16 official M5 executions, **1,344/1,344** checks.
Their `LagunaRuntimeModel.swift` is **510,629 B** (≈13.6 KB of per-file headroom
left) — independent confirmation that the per-file cap is the binding constraint
and that our Q3 file-split is a real capacity lead.

⭐⭐ The same note records an **external M5 negative**: a one-dispatch merged
routed+shared gate/up kernel (`lagunaRoutedSharedSwiGLUQMVPackedTop8R1Kernel`,
guard `DARKBLOOM_MERGED_ROUTED_SHARED_GATEUP`, grid `9*256` TGs of 64 threads)
that **deletes 39 dispatch boundaries and no arithmetic** was measured and
removed: *"Its isolated M5 price was not positive, so the merge was removed."*
This is direct M5 corroboration of our own `LagunaRuntimeModel.swift:7832-7848`
finding, and it is the strongest available evidence that the **M5 dispatch
refund is materially smaller than our M4 barrier-tax model predicts**.

### 0e.3 `b9ccb0b` — carry the router Top-8 comparator pair through one `uint2` shuffle

Site: `Sources/MLXFastModel/LagunaRuntimeModel.swift`, function
`laguna_router_top8_extract_round`, comparator `laguna_router_ordinal_before`,
butterfly offsets `16,8,4,2,1`. Mechanism: pack `(best_ordinal, best_index)`
into a `uint2` and issue **one vector `simd_shuffle_xor`** instead of two scalar
shuffles per butterfly step (AIR `air.simd_shuffle_xor.u.i32` ×2 →
`…u.v2i32` ×1). Consumes `lagunaRouterTop8PrecomputedPrelude`
(guard `DARKBLOOM_ROUTED_GATEUP_R1`). Numbers: 1,344/1,344, `max_abs_diff=0`,
candidate decode `0.00509116015625` vs parent `0.0051070631484375` (**~0.31 %
decode**); `ROUTER_TOP8_EQUIVALENCE cases=4096 experts=1048576 mismatch_words=0`.
Their deferred list names: pairwise NAX scale-hoist specialization, shared
gate/up QMV next-block staging, packing that QMV's two reductions, and relaxing
an affine INT8 prefill guard.

### 0e.4 `6718326` — shared-expert scale halving + barrier re-elision

Two separable mechanisms, both bit-exact:
1. **Shared-expert group-32 halved scale plane** (one byte per 32 weights
   instead of one per 16), built in `LagunaRuntimeWeights.swift`, guard
   `DARKBLOOM_SHARED_SCALE_HALVED` (default on): **+0.171 % decode**, 3/3
   paired, at a cost of **9,855 B**.
2. **Barrier re-elision in the `fp_quantized_nax` fixed_K specialization**
   (JIT/AOT twin pair): **−0.16 % decode** plus a small prefill gain, 3/3 paired.

⚠️⚠️ **Direct conflict with our own #301.** Our PR #301 measured a
pairwise/halved scale plane on the shared gate/up QMV as a **+1.93 %
REGRESSION**. lBroth reports a halved plane as a **+0.171 % gain**. The
construction site differs (weights-side plane construction vs in-kernel
pairwise indexing), so this is a genuine discriminating question, not a
contradiction to dismiss — re-opened as **Q12c → PR #443**.

### 0e.5 `f2b7ccc` — pairwise prefill scale conversion CSE in the M5 NAX expert loader

Files `mlx-generated/fp_quantized_nax.cpp` (JIT, runtime-effective) and
`kernels/fp_quantized_nax.h` (AOT twin). Adds a thread-local `pair_scales`
cache to `QuantizedBlockLoader` so the E4M3→float scale conversion happens
**once per distinct physical scale byte-pair**. Guards
`DARKBLOOM_PREFILL_EXPERT_PAIRWISE_SCALES=0`,
`DARKBLOOM_PREFILL_EXPERT_DOWN_PAIRWISE_SCALES=0`. Exactness is CSE over a
*certified physical alias*, not reassociation. Prefill ≈`188.746`–`188.982`
µs/tok across 5 M5 runs; 1344/1344, `max_abs_diff 0`. Delta only **+0.019 %**
⇒ our **Q12e** is real but low-value.

⭐⭐ The same note **retires four mechanisms with M5 evidence**: "wide-shared
staging" rejected; **"decode scale-lane broadcast" decode-NEGATIVE**; "lm-head
row-major" neutral; **"old X-major fold" officially prefill-NEGATIVE** (register
pressure / occupancy). The last one independently corroborates our own
`XMAJOR pinned off (LagunaRuntimeModel.swift:1586-1596)`, and the lm-head
row-major result corroborates our default-OFF
`lagunaLmHeadRowMajorRefineEnabled`.

### 0e.6 `db8b4df` — zero-copy expert prefill scales + fused-down row staging

⭐ **This submission starts from OUR promoted frontier `3e165fa5` (= `97a5090`).**
Composes (A) a repaired zero-copy expert-scale plane
`[256 experts, 1024 fused output rows, 128 group-16 scale bytes]` exposed as a
"bounded zero-stride marker view" recognized at the **outer `GatherQMM`
normalization site** (v1 failed because generic contiguous normalization
expanded it first), and (B) a **decode-only** staged schedule for the fused
routed+shared down kernel (4-output-tile TG, 9 simdgroups ⇒ 512 tiles × 9 sg ×
39 layers = 179,712 simdgroup tiles/token). Guards
`DARKBLOOM_PREFILL_EXPERT_PAIRWISE_SCALES=0`,
`DARKBLOOM_FUSED_DOWN_ROW_STAGING=0`. Mechanism A: candidate prefill
`0.000189820150390625` vs frontier `0.00019120068359375` ⇒ **+0.72 % raw
prefill**; decode ~0.29 % slower. Retired there: qdot reassociation, dot4
rewrite, alternate quantization, speculative decode, dynamic prompt cache, full
duplicate scale allocation, and an older fused-down implementation.

### 0e.7 `2054d45` — KV-native two-group SDPA schedule ⚠️ reachability unverified

File `Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/kernels/sdpa_vector.h`.
Collapses the adjacent-pair query-head schedule in vector SDPA decode into
**two active query groups per KV head** (was 3 at GQA6, 4 at GQA8) to cut
redundant K/V row reads. Eligibility `D==128`, `V==128`, GQA ∈ {6,8},
`tpg.y==1`, aligned packed loads, no mask, noncausal, no sinks; two-pass
threshold KV ≥ 1024 is **not engaged** in the ranked 512+128 window. Its numbers
are **predicted, not measured** (0.965 ratio ⇒ decode `0.004778813281992187`,
score `2.6492170705818157`); their local `--local-iterate` was no-signal on a
36 GiB host.
⚠️ **Our scored decode attention runs our own custom
`laguna_sliding_fused_attn_ring_v1` / `laguna_full_fused_attn_grow_v1`, not
MLX's `sdpa_vector.h`.** Verify reachability before spending anything on
**Q12f**; it is likely not applicable to our tree.
⚠️ Provenance caveat: `2054d45`'s note describes a genuine kernel change while
`cc6ddc1`'s note claims a byte-identical executable lineage through it. One of
the two is imprecise.

### 0e.8 ⭐⭐ Strategic read

The last six promotions are: (1) our frontier → (2) zero-copy prefill scale
marker view + fused-down row staging → (3) shared-expert halved scale plane +
barrier re-elision → (4) pairwise prefill scale CSE → (5) uint2 router top-8
shuffle packing → (6) active-64 router tournament.

**Four of six are small, bit-exact, algorithmic or representational changes
inside small "glue" kernels** — router top-8 selection algorithm, router shuffle
packing, scale-plane representation, scale-conversion CSE. They are not
bandwidth work, not fusion work, not occupancy work. Our own decode glue pool
(`residual_rms_router_rpg8_keys_v1` 305.1 µs/step +
`decode_router_top8_ordinal_table_norm` 185.7 + `rmsbfloat16` 124.6 + 25.5 ≈
**641 µs/step** on M4) is precisely the region the frontier is mining. Round 84
aims three of four students at it.


## Where we stand

Frontier: promoted candidate `97a5090`, commit `3e165fa`, **rank 1**,
`officialScore = 2.58882784082067`, `ns = 2.5982163`, `S = 97.89475 ms`,
`T = 4.143569335937499 ms`. Round 29 briefs were cut at
`627c4973aa02930808a0a96bfbfdbc3ee486a4c3` (merge of #241); the current advisor base is
**`63ab67c888e1892086b7b5b623de4dd0ebe68c90`**.

**Which base hops actually carry code** — verified with
`git diff --stat <a> <b> -- Sources/ Vendor/ benchmark.json`, not assumed:

| hop | submitted-surface diff |
|---|---|
| `627c4973` → `13f9b6f7` | **empty** (research notes only, incl. the #270 r2 merge) |
| `13f9b6f7` → `e7439c1c` | **empty** (research notes only) |
| **`e7439c1c` → `36b28fa5`** | **`Sources/MLXFastModel/LagunaLmHeadPrune.swift`, 1 file, +10 / −189** (#284 byte recovery) |
| `36b28fa5` → `d9905fc7` | **empty** (research notes only) |
| `d9905fc7` → `b9c2f7c0` | **empty** (research notes only) |
| `b9c2f7c0` → `3f1c58a1` | **empty** (#268 r2 is research-only) |
| **`3f1c58a1` → `69178729`** | **7 files, +36 / −1,719** (#288 comment relocation; `LagunaRuntimeModel.swift` byte-identical) |
| **`69178729` → `31f64154`** | **`Vendor/mlx-swift/…/backend/metal/matmul.cpp` only, +33 / −0** (#293 skinny-tile guard, default OFF) |
| `31f64154` → `7cfea9d6` | **empty** (#298 is research-only) |
| `7cfea9d6` → `63ab67c8` | **empty** (#300 is research-only) |

So exactly **three** hops in the whole round-29→34 chain touch a submitted file. Three
consequences for review:

- A `research_base_changed` event whose compare range contains **only** note-only hops
  needs no rebase and no re-timing: answer it with `accept_result_on_current_base`.
- A range spanning `e7439c1c → 36b28fa5` is only material if the arm itself touches
  `LagunaLmHeadPrune.swift`; a range spanning `3f1c58a1 → 69178729` is only material if
  the arm touches one of #288's seven files (it never touches
  `LagunaRuntimeModel.swift`).
- ⭐ **`69178729 → 31f64154` has a build consequence for every branch, not just
  matmul-touching ones.** `Sources/MLXFastTrustedHarness/VendoredMetalFingerprint.swift:18-21`
  hashes each file under `Vendor/mlx-swift/Source/Cmlx/{mlx,mlx-generated}`, and #293
  edited `matmul.cpp`. **The first build on base `31f64154` or later MUST run
  `./setup.sh`** (or at minimum `tools/build-mlx-metallib.sh`), or the trusted harness
  refuses the tree. Branches cut before that hop (e.g. #301, from `69178729`) are
  unaffected until they rebase.

Use the newest full SHA as the argument
to `validate-assignment-scope.sh` and `check-editable-budget.sh` (both reject short SHAs).

⭐ **The binding budget constraint is per-file, not total.** Total headroom is a
comfortable 131,949 B, but `Sources/MLXFastModel/LagunaRuntimeModel.swift` is
**468,336 B against the 524,288 B per-file cap ⇒ 55,952 B of headroom**, and it is the
file essentially every decode experiment edits. Sizes at base `63ab67c8` for the other
frequently-edited files: `MLXLMCommon/BatchKVCache.swift` 43,383 ·
`CompilableRotatingKVCache.swift` 11,445 · `CompiledDecode.swift` 16,147 ·
`CompilableKVCache.swift` 12,043 · `BaseConfiguration.swift` 8,535 ·
`LagunaLmHeadPrune.swift` 46,797 · `LagunaUpstreamEquivalence.swift` 6,501.
Cap every brief's byte growth at 12,000 B until #311 Part B lands.

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

## ⭐ The finding that now organises decode work: a per-BARRIER tax

**⚠ SUPERSEDED FRAMING — read §4.16 first.** This section originally described the tax
as *flat per dispatch*. **#268 r1 decomposed it and that framing is wrong.** The tax is
**per barrier**, i.e. per unit of serial depth, not per dispatch. The corrected joint fit
(n = 288, 36 blocks, df = 250) is:

- **barrier +1.3003 ± 0.0597 µs**, CI [1.1833, 1.4174], **t = 21.8**
- **dispatch +0.1231 ± 0.0481 µs**, CI [0.0288, 0.2173], **t = 2.6** (an 8.6% residue)
- **one dependent pair = +1.4234 ± 0.0256 µs**, CI [1.3732, 1.4736]

A **barrier-free** dispatch removal refunds only ≈0.123 µs; a **barrier-removing** fusion
refunds ≈1.42 µs. The two differ by 11.6×, so the selection criterion below is rewritten.

Injecting a real barrier-forcing dispatch into the live decode chain costs
**1.30–1.73 µs (pooled ≈1.4 µs, t = 15.6–56.0)**, and #268 shows why the injection
estimate looked flat across sites: every injected site was a *dependent pair*, so every
site paid the same barrier + dispatch sum. Costs are **additive** across injected pairs
(observed/predicted 0.9608 ± 0.0500).

**#269 corroborates the constant by real removal, not injection.** Collapsing four
elementwise ops into one compiled kernel on the off-default stock router tail removed
117 dispatches/step (exactly 3×39) and refunded **+1.233 µs per removed dispatch, 95%
CI [+0.920, +1.545]** (block-paired ABBA, 18 workers, t = +12.54). The two independent
estimates — injection 1.30–1.73 µs, removal 0.920–1.545 µs — overlap. **Injection ≠
removal is now largely retired as a risk: the refund is real and roughly symmetric.**

**Both counts are now measured, not estimated: the default decode path issues exactly
406 dispatches/step** (#269 census) **and exactly 247 barriers/step over 40 layers**
(#268 census) — **6.2 barriers/layer**, against ~7 structural dependency waves.
The prize is therefore `247 × 1.3003 + 406 × 0.1231 =` **371 µs/step (4.5%) on M4 Pro**,
transferring to **188–371 µs/step on M5**.

Consequences already banked:
- ⭐ **The selection criterion is BARRIERS (serial depth) REMOVED, not dispatches
  removed.** Work-elasticity was retired by #241; raw dispatch count is now retired
  by #268.
- ⭐ **RETRACTED: "one removed per-layer dispatch ≈ 27.6 µs/step ≈ 0.42%."** That figure
  is wrong for a barrier-free removal. The corrected refund ladder, per layer removed
  across 39–40 layers:
  - **dependent pair (barrier + dispatch): 56.8 µs/step**
  - **barrier-only: 52.0 µs/step**
  - **barrier-free dispatch only: 4.8 µs/step**
- **A ranked decode arm must bundle ≥3 barrier-removing per-layer fusions** to clear the
  ~80 µs/step 3σ floor. Additivity across fusions is *not* guaranteed — #268's property
  (2) below implies a barrier only costs what it drains.
- **The tax is 28–54% of the entire honest decode pool.** §4.10a reprices the recoverable
  decode budget at **682 µs/step (+10.4%)**, not the fictional 1.20 ms. 188–371 of those
  682 µs are barrier tax.
- **RETRACTED: "kernel time is 13× the dispatch budget."** Against the honest pool the
  ratio is comparable, not an order of magnitude apart.

**⚠ Mechanism: RESOLVED. E1–E5 are ALL REFUTED; only E6 survives.** #268 r1 ran six site
arms and settled this:
- **E1 (CPU graph-eval/encode starvation) — REFUTED twice.** 99.4–100.2% of the tax sits
  inside GPU busy time, and injected CPU spin moves wall by only
  **+0.0497 ± 0.0293 µs per µs of spin (32 SE below 1.0)**. #269 independently measured
  **Δ(inter-kernel gap) = 1 µs against Δ(GPU-busy union) = 139 µs**, the latter agreeing
  with the ABBA step-time effect to **0.4σ**.
- **E2 (per-dispatch fixed launch cost) — REFUTED as the main term**, surviving only as
  the 0.123 µs residue. 160 injected *barrier-free* dispatches cost **−5.6 µs** against
  +224 µs predicted (~40σ).
- **E3 (dirty-footprint cache flush) — REFUTED.** 256 B .. 4 MiB is exactly linear:
  `1.3489 ± 0.0181 µs + 4.172e-6 ± 9.6e-9 µs/byte`. The slope is **239.7 GB/s = 88% of
  the host's 273 GB/s peak**, i.e. ordinary DRAM traffic, not a flush penalty. The
  intercept is our tightest estimate of the fixed part.
- **E4 (buffer-pool/residency bookkeeping) — REFUTED.** 1/4/16/64/256 distinct buffers →
  1.3469/1.5201/1.5507/1.5472/1.4871 µs, non-monotone.
- **E5 (anchor artifact) — RE-CLOSED.** Two anchor-free arms reproduce the split, and
  command buffers stayed at exactly 45 across all of #269's arms.
- ⭐ **E6 — SURVIVES: loss of intra-encoder overlap when `maybeInsertBarrier` emits
  `[encoder memoryBarrier]`** (`device.cpp:363-375`, `set_input_array` `:315-328`).

**Four observed properties of the barrier tax:** (1) charged **per barrier**, not per
dispatch; (2) charged **off the critical path** — the `chain` arm's 157 extra barriers
cost **−42.8 µs**, i.e. *a barrier costs what it drains*; (3) charged **per unit of
serial depth, not per raw RAW edge**; (4) the `diamond1` arm's 80 *parallel* RAW edges
raise the barrier count by only **4** and cost **−0.0070 ± 0.0212 µs/dispatch**, while
the same 80 edges in series cost 78 barriers and 110 µs. MLX's breadth-first eval tape
plus `maybeInsertBarrier` moving `next_*` into `prev_*` collapses forty parallel edges
into one barrier, which is why 247 barriers ≈ true serial depth.

**⇒ The correct lever is KERNEL FUSION that removes serial depth.** Explicitly NOT
ICB/encode overlap, NOT `start_concurrent()`, and NOT graph reordering — MLX already does
the reordering, and it is not on our editable surface anyway. These are now **closed**.

**Cross-validation with #269:** its 117 removed dispatches were a dependent chain, so the
barrier model predicts `117 × 1.4234 =` **166.5 ± 3.0 µs** against a measured
**144.23 ± 23.00 µs — 0.96σ**. A barrier-free-only model predicts 14.4 ± 5.6 µs, which is
**5.5σ low**. The barrier model wins decisively.

Caveats: measured on **M4 Pro** (48 GiB, 20 GPU cores, gen 16) — directional only;
the **1.3003 µs barrier coefficient has never been measured on M5**, and re-measuring it
there is an open escalation to the human team. Reducer caveat:
`fern_gap_stats.py` centres on the K=1 arm, `fern_gap_wandb.py` on the block mean, so
W&B `pooled/*` and `prize/*` read ~6% high — **never compare a W&B t-stat with a doc
t-stat**.

## ⭐⭐ R85-D (#458, merged round 87): the tax decomposed into BYTES vs COUNT — and why the 371 µs "prize" above is a GROSS number

#458 built a synthetic ladder in the live decode glue pool and fitted the three
components of a boundary separately. On M4 Pro:

| component | symbol | measured | note |
|---|---|---|---|
| fixed issue/launch of one extra dispatch | `c_issue` | **≈ 0.17 µs** | agrees with #268's 0.1231 ± 0.0481 residue |
| draining/refilling one 4 KiB dependent round trip | `c_drain` | **≈ 1.24 µs per 4 KiB** | the dominant term |
| command-buffer boundary, packed | `c_CB` | **≤ 0.14 µs** | negligible when MLX packs |
| command-buffer boundary, SPLIT mode | `c_CB` | **≈ 1.7 µs** | only reachable by forcing a split |

**⭐ The byte axis beats the count axis 7.7 : 1.** A boundary costs what it
*drains*, not what it *launches* — this is the quantitative form of #268's
property (2). Decode is **GPU-busy-bound**, not launch-bound.

Three doctrine changes follow, and they are binding on every future assignment:

1. **RETIRED: the "3.00 µs / 4.70 µs per-call floor" doctrine.** Those spans
   were measured in SPLIT command-buffer mode and are an artefact of forcing a
   command-buffer boundary per call. In packed mode the boundary is ≤0.14 µs.
   Relabel any surviving use as "SPLIT-mode spans". This doctrine previously
   motivated ≥2 arms; do not let it motivate another.
2. **⚠ CB-count mirage.** The decode step issues 45 command buffers. `45 × 1.7
   µs ≈ 76 µs/step` looks like a free 1.2 % — **it is not recoverable.** The
   1.7 µs only exists in SPLIT mode; the real packed cost of those 45
   boundaries is ≤6.3 µs/step total.
3. **⭐⭐⭐ GROSS ≠ NET. The 371 µs/step barrier prize computed above is a gross
   upper bound and the campaign has now paid twice for treating it as net.**
   Two independent pieces of evidence:
   - **Serial-depth floor.** #268's census found **247 barriers/step over 40
     layers = 6.2 barriers/layer against ~7 structural dependency waves** in a
     decoder layer. The chain is already close to its structural floor. Most of
     the 247 are not removable by any fusion that preserves the dataflow.
   - **Redundancy eats the refund (§4.18).** The RMSNorm→QKV fusion actually
     removed 40 dispatches and 39 barriers per step, was predicted at
     **+0.85–0.9 %**, and **ranked −0.1488 % on M5.** A fusion that folds a
     producer into a consumer re-executes the producer once per consumer
     threadgroup; the redundancy multiplier `R` is set by the consumer's grid
     decomposition, and `producer_cost × (R − 1)` is charged against the
     refund.

**⇒ New selection rule (supersedes "barriers removed"): rank fusion candidates
by NET = (barriers removed × measured in-situ boundary price) − (producer cost
× (R − 1)), and require the redundancy multiplier `R` to be derived from the
consumer kernel's actual grid/threadgroup decomposition with a line number.**
A candidate with `R = 1` (redundancy-free — e.g. producer and consumer share
the identical decomposition) is worth an order of magnitude more than a
same-gross candidate with `R = 20`. This is the axis #462 is measuring.

## In flight — round 87

All four students are busy. Base for every arm is
`7687c2e44e6975c181444ca8d3d151ee30480a72`.

| PR | Student | Branch / head | Hypothesis | Why now |
|----|---------|---------------|-----------|---------|
| [#460](https://github.com/morganmcg1/mlxfast-challenge_senpai/pull/460) | maple-tanjiro | `maple-tanjiro/r86-base-decode-regression` @ `30eecc6d` (`r86-a-rev2`) | **GATING ARM — verify the frontier adoption.** Build via `./benchmark.sh --local-iterate`, discharge the 64-step tripwire, run `research/run_upstream_equivalence.sh` and prove a non-zero test count, re-audit bytes and per-file caps, independently re-verify the two risky audit decisions the advisor made during adoption, and produce matched timing `f64456dd` vs `7687c2e4`. | Everything else on the board assumes the adopted base is correct and is not silently ~38 µs/step behind our own best promoted content. Nothing should be submitted until this clears. |
| [#457](https://github.com/morganmcg1/mlxfast-challenge_senpai/pull/457) | maple-frieren | `maple-frieren/r85-placement-lever` @ `9d629b77` (`r85-c-rev2`) | **Re-port mechanism M-B: the float4 / AoS merge epilogue** into both decode fused-attention kernels. The frontier author rewrote both epilogues to plane-major SoA and silently reverted our merged PR #205. | This is a **replication of a measured winner**, not a new idea: #205 measured **+18.58 ± 2.92 µs/step, t = 6.37, 12/12 paired blocks positive, `max_abs_diff = 0` over 1344 steps ⇒ ≈ +0.284 % score**. Pre-registered prediction ≈ +18.6 µs/step. Footprint-neutral is **required** (§8: 8 float4 planes need 33,792 B against the 32,768 B threadgroup limit). |
| [#456](https://github.com/morganmcg1/mlxfast-challenge_senpai/pull/456) | maple-fern | `maple-fern/r85-surface-reconstruction` @ `a5a35280` (`r85-b-rev2`) | **Per-file cap relief.** Split `LagunaRuntimeModel.swift`; recommended carve is lines **8693–11283** (`LagunaRuntimeMLP` at `:8693` + `LagunaRuntimeSparseMoEBlock` at `:10476`) = 112,508 B, dropping the scored file to 398,910 B. Plus a local surface-reconstruction harness and an editable-surface integrity audit. | 12,870 B of per-file headroom is not enough to land any kernel change. The key risk is the `private` → `internal` widening required by the split; neutrality must be **measured**, not asserted. |
| [#462](https://github.com/morganmcg1/mlxfast-challenge_senpai/pull/462) | maple-nezuko | `maple-nezuko/r86-insitu-boundary-price` @ `abefac77` (`r86-b-rev1`) | **In-situ boundary price + redundancy-priced barrier census + a post-mortem of #48.** An env-gated un-fusion ladder inserts `k ∈ {0,64,128,256,512}` genuine dependent DRAM round trips into the *real* decode step at two widths (WIDE 4 KiB, TINY ≤64 B); `d = slope(WIDE) − slope(TINY)` is the in-situ drain price. | The price is already measured three times in situ (#268 joint fit, #269 real removal +1.233 µs [+0.920, +1.545], R85-D ladder 1.4140 ± 0.0093) so the GO threshold will almost certainly be met — **the value is in the census**, which must carry a redundancy multiplier `R` and a NET column per the rule above. Expected to close unmerged (instrument-only deoptimizer). |

**Feedback IDs already spent:** `r85-b-fb1-channel-open` (#456);
`r85-c-fb1-channel-open`, `r85-c-fb2-provenance-and-target` (#457);
`r86-b-fb1-redundancy-axis` (#462).

**⚠ Branch names are not guessable from assignment titles.** Recover the exact
head branch, `assignment_id` and `revision_id` from the
`<!-- senpai-assignment:v1 ... -->` marker in a `get_prs` artifact, or from a
*targeted* `git ls-remote origin refs/heads/<branch>` — a bulk
`git ls-remote origin 'refs/heads/maple-*'` has returned a stale SHA.

### Queued behind the current round (not yet assigned)

1. **M-A: full-attention decode params memo** (our commit `0ae542dd`).
   `LagunaRuntimeModel.swift:2301–2303` rebuilds
   `MLXArray([UInt32(writeIdx), UInt32(writeIdx + 1), UInt32(capacity), …])`
   on every decode step of the full-attention "grow" helper (`:2265–2302`,
   called from `:6054`). A single-entry memo keyed on `(writeIdx, capacity)`
   gives 128 builds instead of 1280 and removes ~1152 MLXArray
   allocations/graph leaves. The sliding path at `:1801` already does this via
   `lagunaRingIdxAtlas[writeIdx]`. Position-keyed, so serial-track compliant.
   ⚠ The GPU-busy-bound finding above is a prior *against* it.
2. **Re-port PR #48's fused norm→QKV as an in-situ discriminator.** Modes
   0/1/2 on real kernels separate `c_issue` from `c_drain`; mode 2 is reached
   by a one-character default flip. Blocked pending #462's redundancy verdict
   and #456's byte headroom.
3. **Re-validate previously-open families against the frontier's code**:
   decode intra-CB concurrency (the #174 discriminator), prefill glue (old
   C5), shared-expert overlap (old 5b). All were closed or parked against code
   the frontier has since rewritten.

### Byte-recovery census — corrections applied 2026-08-07 (supersedes §9 of the census doc)

The census doc's §9 recommended a three-file Lever-1 scope
(`LagunaLmHeadPrune.swift` + `LagunaRuntimeWeights.swift` + `LagunaConfig.swift`,
51,634 B). **That recommendation is superseded.** `LagunaLmHeadPrune.swift` is now
owned by **#284**, whose Step 0.5 already deletes 7,985 B of dead row-major refine
from it. The two `Vendor/mlx-swift-lm/Libraries/MLXLMCommon/` files were substituted
in, raising the ceiling from 51,634 B to **79,691 B**.

**⚠ Measured hazard: this codebase embeds Metal kernel source inside Swift `"""`
multi-line string literals.** A `//` line inside such a literal is *Metal source*, not
a Swift comment; stripping it silently changes the compiled kernel. Any comment-byte
recovery must therefore be split by literal membership. Measured at `e1d070f2`:

| file | size | comment B **outside** `"""` (safe) | comment B **inside** a literal | `"""` delims |
|---|---|---|---|---|
| `Sources/MLXFastModel/LagunaRuntimeWeights.swift` | 53,980 | **23,200** | 0 | 0 |
| `Sources/MLXFastModel/LagunaConfig.swift` | 44,726 | **4,753** | 0 | 0 |
| `Vendor/mlx-swift-lm/…/MLXLMCommon/KVCache.swift` | 81,231 | **24,252** | 0 | 0 |
| `Vendor/mlx-swift-lm/…/MLXLMCommon/Evaluate.swift` | 75,312 | **27,486** | 0 | 4 |
| *(excluded)* `Sources/MLXFastModel/LagunaLmHeadPrune.swift` | 54,963 | 21,290 | **2,397** | 16 |
| *(excluded)* `Sources/MLXFastModel/LagunaRuntimeModel.swift` | 468,336 | 120,409 | **742** | 212 |

All four in-scope files carry **zero** comment bytes inside a literal, so a
strip-and-compare equivalence proof is sound for #288's scope and **would not be**
for the two excluded files.

**`Vendor/mlx-swift-lm/` is NOT fingerprinted.**
`VendoredMetalFingerprint.fingerprintedSubtrees = ["mlx", "mlx-generated"]` is rooted
at `defaultCmlxRelativePath = "Vendor/mlx-swift/Source/Cmlx"`, so binding constraint 7
(mandatory metallib rebuild) applies only to that tree. Comment edits under
`Vendor/mlx-swift-lm/` need **no** rebuild.

**Deferred, not dropped:** `LagunaRuntimeModel.swift` holds **~120,409 B** of
recoverable comment bytes — by far the largest single prize, and the file where the
**per-file** 524,288 B cap actually binds (55,952 B left). It is deferred purely on
sequencing grounds: three concurrent students hold line-range fences on it. Schedule a
dedicated whole-file round once #268, #284, and the F1 arm have all landed.

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
6. **⚠ There is a second, per-file cap of 524,288 B.**
   `Sources/MLXFastModel/LagunaRuntimeModel.swift` is **468,336 B** ⇒ only **55,952 B**
   of per-file headroom. Every concurrent decode assignment edits that one file, so a
   large addition hits the *file* cap long before the 49,145 B *total* cap.
7. **⚠ Any edit under `Vendor/mlx-swift/Source/Cmlx/{mlx,mlx-generated}` — including a
   comment-only edit — requires a metallib rebuild.**
   `Sources/MLXFastTrustedHarness/VendoredMetalFingerprint.swift:19-21` per-file
   SHA-256s that whole tree, and the trusted CLI recomputes the fingerprint immediately
   before spawning the worker so a stale metallib cannot mask edits. Re-run
   `tools/build-mlx-metallib.sh` / `./setup.sh` after any such touch.
8. **⭐ Never commit an advisor-owned research document into a student branch** —
   `research/CURRENT_RESEARCH_STATE.md`, `research/RESEARCH_STATE_ARCHIVE_*.md`, and
   `research/maple-byte-recovery-census-*.md`. Read them at your base commit and leave
   them untouched. Carrying a copy forward creates an unmergeable stale-content
   conflict the moment the advisor branch moves; this is exactly what blocked #270 and
   cost it a whole revision cycle. **Standing rule 15**, now embedded in every brief.
   The robust repair is to revert the student's copy to its **merge-base** blob (not to
   the current advisor version), which makes the student's side a no-op and immunises
   the branch against every future advisor commit.
9. **⭐ Standing rule 16 — the equivalence oracle is structurally blind to the
   fused-weight family.** `LagunaUpstreamEquivalence.swift:74-90` builds the model and
   calls `update(parameters:)` + `eval` directly, **bypassing the weight cache**.
   `prepareFusedRuntimeWeights()` (`LagunaRuntimeModel.swift:11016`) has exactly one
   caller, `LagunaRuntimeWeights.swift:637`, which the oracle never reaches. A green
   `run_upstream_equivalence.sh` therefore says **nothing** about any change that only
   takes effect when a fused bank is materialised. Any arm touching a fused bank must
   additionally prove itself with the 64-step drift tripwire *and* a matched
   `--local-iterate` decode pair. Discovered by #270 r2; re-confirmed independently by
   #284 and by #48 §9.4/§9.5/§9.7 (§4.18.8); applies team-wide.
   **CORRECTION 2026-08-07:** an earlier note claimed the oracle file is outside the
   submitted surface. That was **wrong**. `benchmark.json`'s `editablePaths` contains
   only two `Sources` entries — `Sources/MLXFastModel` and `Sources/MLXFastTransform` —
   and both are **directories**, so `Sources/MLXFastModel/LagunaUpstreamEquivalence.swift`
   (6,501 B) **is inside `editablePaths` and CAN be de-blinded**, at a byte cost, by
   routing it through `loadLibraryModel`/`prepareFusedRuntimeWeights()`. This is now a
   normal (low-priority, zero-score, risk-reducing) assignable item, not an escalation.
   Two further blindness facts from #48: under an injected `+1.0f` fault
   `max_abs_diff` stayed **0** while `passed_correctness` went false, so
   **`max_abs_diff` is not an independent residual signal on the fused path**; and the
   argmax gate is **blind below 1e-3**, so it cannot see permutation- or
   statistics-preserving errors, races, missing barriers, occupancy/compiler effects, or
   uninitialised threadgroup memory.
10. **⭐ Standing rule 17 — `DARKBLOOM_*` flags are not axis-local.** #270 r2 flipped
    `DARKBLOOM_FUSED_QKV` expecting a prefill-only effect and paid **+39.99% decode**
    (`decode_speedup` 0.7705, hard-floor FAIL) because the same materialised bank
    silences the fused decode norm+INT8-QKV block at `LagunaRuntimeModel.swift:5709`.
    **Always measure BOTH prefill and decode when flipping any one flag**, and report
    both speedups against the same-session paired baseline. Combined with constraint 3,
    a one-axis local win is not evidence that a candidate is rankable.
11. **⭐ Standing rule 18 — search the remote branches for prior art before briefing any
    "fresh" fusion or kernel idea.** Run `git branch -r` and inspect prior PR branches
    and tags for the exact mechanism. §4.16 named three fusion targets as new work;
    **two of them (C1 = RMSNorm→QKV, C3 = router→top-8) had already been built**, on
    `maple-fern/fused-norm-qkv-gate` (`pr/48`) and `maple-fern/router-top8-fusion`
    (`pr/204`), and C1 had **already consumed a ranked M5 slot**. Neither result had been
    carried into this document. See §4.18. Cost: one wasted ranked slot and a near-miss
    re-assignment.
12. **⭐ Standing rule 19 — barrier counts REBALANCE under fusion; ΔB must be MEASURED,
    not predicted.** #48 §4.3: *"Deleting a producer does not delete its consumer's
    barrier; it rotates it onto whatever the consumer now aliases. ΔB is therefore not
    additive attribution."* The evidence is #48's measured **39:1 split** — folding the
    input RMSNorm into QKV removed 40 dispatches and 39 barriers, while folding the gate
    in removed another 40 dispatches but only **1** barrier (§4.18.3). Any refund
    estimate that counts removed dispatches and assumes proportional barrier savings is
    wrong. Every fusion brief must instrument `maybeInsertBarrier` and report the
    measured before/after barrier count per decode step.

## No W&B channel for this target

The mlxfast harness publishes **no W&B runs**. **mlxfast receipt IDs are the canonical
experiment reference** for this campaign, and PR result comments carry the raw
`officialMetrics`. This is recorded, not a reporting failure; do not ask students for
W&B links they cannot produce.

## Next directions, ranked

### ⭐⭐⭐ FINAL-ROUND RANKING (2026-08-08 ~08:50 UTC) — supersedes the numbered list below

Round 34 closed decode fused attention and H7's rescale skip. Round 36 closed
the router glue family outright (§4.26) and corrected the prefill-MoE
accounting (§4.27). **Round 37 then discovered that the lever this table used
to rank first — `_nax` gather-GEMM scale-load amortization — had already been
assigned as PR #244, run on the ranked M5, and closed as a clean negative (see
standing rule 31).** Round 39 pre-answered two more `_nax` micro-levers offline.
Rounds 40–41 landed #308, #309, #301 and #320, all four of which are terminal.
What remains, in expected-value order:

| # | lead | size | status |
|---|---|---|---|
| 1 | ~~**#308 — threadgroup-packing `S` curve**~~ (tanjiro) | argmax is **`S = 8`, −36.9 µs/step vs `S=2`, CI [−61.0, −12.9]** | ✅ **MERGED, terminal.** `{4,8,16}` are statistically tied and `S=32` is *second-worst*, so "bigger `S` is monotonically better" is **refuted**. Stage 2 was replaced by a static 4-site audit; Stage 3 remains an unapplied **+29 B** `tanjiro_packing_default_flip.patch`. Surviving work is fresh, not a revision: (a) land the default flip with `run_upstream_equivalence.sh` + a `--local-iterate` pair, (b) Stage 2 site 1 = routed MoE gate/up `:7546` at `S ∈ {2,4,8,16}`, which **must** add an `_sgN` kernel-name suffix (rule 33) |
| 2 | ~~**#309 — persistent grid-stride QKV, `T` axis**~~ (nezuko) | `G128 − G640 = **+174.9 ± 11.0 µs/step**` | ⛔ **KILLED and merged as a terminal negative.** The projected −106 µs never existed: coarsening the grid to amortise per-threadgroup work *costs* ~+175 µs/step on this kernel, with a hard cliff once threadgroup count drops below the core count. One real but sub-bar win fell out and is **unmerged**: `N640 − a0 = −33.7 ± 11.0 µs/step` (algebraic epilogue normalization at *full* coverage). Its full-coverage successor is lead 3 |
| 3 | ⭐⭐⭐ **Algebraic epilogue normalization at full coverage** (#309 §11.1) — keep the 640-threadgroup grid, take only the epilogue-normalization algebra that produced `N640 − a0 = −33.7 ± 11.0 µs`, and extend it from partial to full coverage | **priced ceiling ≈ −140 µs/step**, which clears the ~80 µs/step ranked bar | ⭐ **TOP UNASSIGNED LEAD.** Measurable on M4 Pro, so it does *not* need a healthy submission pipeline to make progress. Natural owner **maple-nezuko**. Mandatory: the #309 fault-injection pattern (offset the **store** index only — a bijection over rows is bit-exact by construction), full gate set, and the rule-35 reminder that the equivalence oracle never reaches `prepareFusedRuntimeWeights` |
| 3b | ⛔ ~~**Prefill `_nax` gather-GEMM scale-load amortization** (§4.27 lever 1)~~ | ~~−1.2 to −1.8 ms prefill~~ | ⛔ **CLOSED — already run and refuted as PR #244.** Evidence: `research/CURRENT_RESEARCH_STATE.md:184-186` and `:4505-4510` (closure), `research/tanjiro-nax-kloop-pipeline.md:1064-1078` §6.10 candidate 1 (the proposal), `research/RESEARCH_STATE_ARCHIVE_rounds-22-28.md:610-611` (the assignment). The arm **did** cut device-load issues 3 → 1.25 and still nulled, which is why the PR #215 operative pre-filter is necessary but not sufficient. **Do not re-propose.** No `#244` report file exists under `research/` — this table is the record |
| 4 | ~~**`residual_rms_router_rpg8_keys_v1`**~~ | — | ⛔ **CLOSED by round-36 recon (§4.26).** The ~154 µs "excess" is a **unique-vs-issued-byte artifact**: the 1 MB router weight is partitioned across the 32 threadgroups, not broadcast, and on *issued* bytes the kernel already runs at ≈81% of the M4 ceiling. In situ it is **two-thirds shadowed** (E = 0.349, 2.73 µs/call marginal vs 7.72 census). Every lever is dead: rpg retiling measured null, threads-per-TG null, `n_reads` and accumulator reassociation not bit-exact, prologue split net-negative (+3.6 µs/dispatch × 39), top-8 fusion structurally blocked *and* fully shadowed. **Do not re-propose.** |
| 4b | ⭐⭐ **Prefill `_nax` lever 2 — A-fragment N-tile reuse** (2 N-tiles per A load halves ~16 A re-reads at N=1024, BN=64) — `research/tanjiro-nax-kloop-pipeline.md:1080-1086` | up to several ms, **high variance** — collapses to null if the SLC already absorbs the re-reads | ⭐ **NOW THE TOP SURVIVING `_nax` LEVER**, promoted because lever 1 is closed by PR #244 (row 3b). It is the only remaining prefill-MoE candidate that reduces *requested bytes* rather than load *issues*, so it sits outside the family #244 refuted. Still structurally M5-receipt-gated: `_nax` never executes on a student M4 Pro (gen 16), so until the pipeline is healthy it can only be assigned as a build + bit-exactness + MSL-issue-count experiment with a deferred ranking verdict. Twin edit to `Vendor/mlx-swift/Source/Cmlx/mlx-generated/fp_quantized_nax.cpp` and a `./setup.sh` metallib rebuild are mandatory (rule 9) |
| 5 | **The split-K tie flip** (`matmul.cpp:986-989`, relax `K > 2·max(M,N)` to `>=`) | unlocks the 78 wk/wv dispatches now stuck at **1.6 TG/core**; part of the 6.5–10.3 ms prefill tail | needs its own correctness plan — FP32 partial accumulation is **not bit-exact**. **Publicly promised to tanjiro twice.** |
| 6 | ~~**`LagunaRuntimeModel.swift` comment relocation**~~ (120,254 B pool, 96,027 B of `///`) | ~~≥18,000 B~~ → **measured ceiling ≈9.4 KB** | ⛔ **CLOSED by #320 as a measured dead end.** The submitted-surface diff was **empty** and the file was byte-identical at 468,336 B, so the delivered net shrink was **0 B against an 18,000 B bar**. The corrected planner prices the *whole* mechanism at 12,910 B gross / **9,362 B wave-1 net / 10,251 B full-plan net**, not the 28,643 B originally projected; the error was **char-vs-byte counting**. Two structural reasons it cannot be rescued: the hard-kept (rule-bearing) pool is **82,899 B = 69 %** of the comment pool, and **50 of 62 abstracts truncate mid-sentence**, costing 3,560–8,531 B of the 9,362 B win to restore. **Do not re-propose comment relocation on this file.** |
| 6b | ⭐⭐⭐ **Split `LagunaRuntimeModel.swift` into a second file under `Sources/MLXFastModel/`** — the strategic reframe that replaces row 6 | dissolves the **524,288 B per-file cap** outright instead of clawing back ~9 KB | ⭐ **TOP CAPACITY LEAD, unassigned.** `Sources/MLXFastModel/` is a *directory prefix* in `editablePaths`, so a newly created file inside it is already in-surface: moving declarations out of `LagunaRuntimeModel.swift` (475,647 B after #301, ≈48,641 B of per-file headroom left) converts a hard per-file ceiling into ordinary total-surface budget. Pure capacity, no score, and it should be **paired with a timing arm** rather than assigned as a standalone byte chore. Gates: scope + budget, a scored-worker build, the 64-step drift tripwire, and `run_upstream_equivalence.sh` — a file split must be a *textual* no-op at the compiler level, so any diagnostic change is a bug |
| 7 | **#48 §10 item 4 — widen the `gate_sp` kernel itself** | unquantified | ⚠️ #174 §2.6 lists `gate_sp_h64/h48` among only three kernels that **hide** (E = 0.10) |
| 8 | **H7 specialisation sub-lever only** — constant-fold `N`/`capacity` in the FULL attention kernel (10 calls/step) | 20–40 µs | weak; the sliding kernel already has `constexpr int N = 512` |
| 9 | **CPU-side per-step cost** — cb commit/completion, Swift allocator churn, argmax readback → next-token embedding sync | unmeasured | no instrument yet |
| 10 | **Device-atomics "last threadgroup finalizes"** cross-TG reduction | ~1–3 µs | deterministic only if partials are re-read in fixed index order |

**Gating constraint on all of it (rewritten 2026-08-08 09:45 UTC; supersedes
the round-32 text that used to sit here):** the ranked submission pipeline is
still down and the outage is now the single largest constraint on this
programme. The last receipt that produced any number at all is `3ff3992`,
2026-08-07 18:51 UTC — `rejected`, `officialScore 2.52125675539565`. Since then
there have been **thirty-five consecutive `failed` terminal receipts** with
`n/a` metrics *and* `n/a` error, `51c3975` (19:12 UTC) through `b63e076`
(2026-08-08 08:16 UTC), i.e. **≈13.4 h of continuous account-wide failure, with
no recovery observed as of 09:45 UTC (≈14.9 h)**. None of the thirty-five is a
maple candidate; the account-scoped slot is shared with the parallel campaigns,
so this is telemetry about the shared infrastructure and not about any maple
patch. Six of the receipts were caught mid-flight in `validating` and every one
of them subsequently resolved to `failed`, so **`validating` is not evidence of
recovery — only a non-`failed` terminal receipt is.**

⚠️ Operational hazard: `mlxfast submissions` returns *empty output with exit 0*
when it is chained after `git` in one compound shell command. **Always run it
as the sole command in its own invocation**, e.g. `mlxfast submissions | tail`.

Three consequences for assignment policy:

- **Assign only M4-testable, receipt-free work** until a non-`failed` terminal
  receipt appears. Everything in the round-40/41 queue (algebraic epilogue
  normalization, routed-twin K-block prefetch, the reversed-`ORDER` separator,
  #308 Stage 2/Stage 3, the file split) is deliberately chosen to be decidable
  on a student M4 Pro.
- The old sentence here — "when the pipeline recovers, the first slot goes to
  #308's arm `G`" — is **obsolete**. #308 is merged and terminal, and its
  argmax (`S = 8`, −36.9 µs/step) is roughly half the ~80 µs/step ranked bar.
  Nothing currently on the board clears that bar: the largest surviving decode
  effect is #301 mechanism (a) at −14.2 µs/step = 0.111 % of the decode wall.
  **The first recovered slot therefore belongs to a *new* arm** — the routed-twin
  K-block prefetch (#301 §7.3, priced ceiling ≈ −72 µs/step) or the algebraic
  epilogue normalization at full coverage (#309 §11.1, priced ceiling ≈ −140
  µs/step) — whichever produces a real M4 effect first.
- The old note about lead 3 being "structurally receipt-gated" referred to the
  `_nax` scale-load amortization, which is now **⛔ CLOSED by PR #244**. The
  deferred-verdict framing still applies, but it now belongs to **row 4b, the
  A-fragment N-tile reuse lever**: `_nax` cannot execute on any student M4 Pro
  (gen 16), so that arm can only be assigned today as a build +
  bit-exactness + MSL-issue-count experiment whose ranking verdict waits for a
  healthy pipeline.

> **Re-ranked 2026-08-07 by §4.10a (decode re-priced against an 85% ceiling, not
> 100%) and §4.10b (decode GEMV geometry census).** Two items below changed
> position and one long-standing claim was retracted; read those two sections
> before using this list.
>
> **Updated again 2026-08-07 13:20 UTC by §4.13 (#270 prefill census) and §4.14
> (#269 decode census).** Item 0 is now **assigned as #284**. Item 3's CPU-paced
> branch is **effectively dead** — #269 refuted E1. Item 4 is rewritten: prefill now
> has a complete ledger, a closed glue class, and two named targets (**F1** and
> **`steel_gemm_bf16`**) that between them are the largest unassigned headroom on the
> board.
>
> **⭐⭐ Updated again 2026-08-07 ~14:40 UTC by §4.13b (#270 r2) and §4.16 (#268 r1) —
> two terminal results that between them close item 1, kill item 4's F1, and promote
> H2.** Item 1 is **resolved: the tax is charged per BARRIER (E6), and E1–E5 are all
> refuted.** Item 2's "27.6 µs/step per removed dispatch" is **RETRACTED** and replaced
> by the §4.16 refund ladder (dependent pair 56.8 / barrier-only 52.0 / barrier-free
> dispatch 4.8 µs/step per layer) — selection is now on **barriers removed**, not
> dispatches removed. Item 3 is **closed outright**, together with graph reordering and
> `start_concurrent()`. Item 4's **F1 is dead** and **H2 is promoted to the primary cheap
> prefill lead, assigned as #293**.

0. **⭐ H5 — make lm-head screening prune payload bytes (§11.5). ASSIGNED as #284
   (maple-nezuko), 2026-08-07.** §4.10b **answered H5's "free first experiment" and
   the answer
   is that the pruner does NOT prune payload bytes today.** Decode dispatch 5a
   (`laguna_lmhead_int5_base_coarse_delta_bf16_v1`) streams the *entire* 100,352-row
   coarse plane every step — 100,352 × 1024 B codes + 100,352 × 64 B e8m0 scales =
   **109,182,976 B = 104.1 MiB**, the single largest weight read in the step. All
   pruning happens downstream (5b argmax, 5c one exact 4 KB row, 5d "single digits"
   of survivor blocks). This is the **one place in decode where the byte total is not
   pinned**: greedy argmax permits provably sound row pruning, so it **moves B, not θ,
   and is therefore not capped by the 0.85 ceiling** that bounds every other decode
   idea. At 1–5 % survivors ≈ −71 MB ≈ **163 µs/step ≈ +2.5 % score**, comfortably
   over the ~80 µs single-arm bar.
1. **✅ CLOSED — the tax mechanism is resolved (#268 r1, §4.16).** **E6 wins: the charge
   is per `[encoder memoryBarrier]`, i.e. per unit of serial depth.** Barrier
   **+1.3003 ± 0.0597 µs** (t = 21.8), barrier-free dispatch **+0.1231 ± 0.0481 µs**
   (t = 2.6), dependent pair **+1.4234 ± 0.0256 µs**. E1 (CPU encode starvation), E2
   (per-dispatch fixed cost, survives only as an 8.6 % residue), E3 (cache/residency —
   the size sweep is linear at 88 % of peak DRAM bandwidth), E4 (PSO switching,
   non-monotone) and E5 (anchor artefact) are **all refuted**. Total prize
   **371 µs/step on M4 = 188–371 µs/step on M5 = 28–54 % of the honest 682 µs decode
   pool**. Cross-validated against #269 at 0.96σ. **The one thing still owed is an M5
   re-measurement of the 1.3003 µs coefficient — an open escalation to the human team.**
   #268 **r2** is now censusing the 247 barrier *sites* so we can pick fusions by refund
   rather than by intuition.
2. **⭐⭐ Structural fusion — now the presumed-correct branch, and re-scoped from
   dispatches to BARRIERS.** ⚠️ **RETRACTED: "each per-layer dispatch removed ≈ 27.6 µs/
   step ≈ 0.42 % ≈ 1.80σ."** §4.16 replaces it with a ladder that differs by **11.6×**
   depending on whether the removal eliminates a barrier: **dependent pair 56.8 µs/step
   per layer, barrier-only 52.0, barrier-free dispatch only 4.8.** A fusion that removes
   a dispatch but not a barrier is worth essentially nothing. The three verified targets
   must therefore be re-graded by #268 r2's site census before any of them gets code
   time:
   - **C (input RMSNorm + QKV GEMV)** — the student's own top pick and #268 r2's **C1**.
     A serial chain, so almost certainly barrier-removing. `:5738-5745` currently
     *declines an already-written fused kernel* (`lagunaNormAffineQKV` `:5301-5357`) on
     the NVFP4 path because the guard is INT8-only.
     ⚠️⚠️ **PRIOR ART — see §4.18. PR #48 already built this, already ranked it on M5,
     and got −0.1488%.** That receipt is **CONFOUNDED, not a refutation**: the submitted
     arm bundled −80 dispatches, −40 barriers **and** an unpriced 8× threadgroup-count
     collapse (5120 → 640) plus ~24,320 redundant 2048-element reductions per step,
     because a bit-exact RMSNorm fold must reproduce MLX's 512-thread reduction tree.
     §4.18.7 states the new structural law: **bit-exact RMSNorm fusion is intrinsically a
     geometry change as #48 built it.** The live question is the barrier refund *at fixed
     geometry* — `(mode 1 @ SIMDGROUPS=16) − (mode 0 @ SIMDGROUPS=16)` against a §4.16
     prediction of 55.6 µs/step — which has never been run. Deconfounding that is the
     next assignment; the escape hatch if it confirms is a 64-thread threadgroup that
     *serialises* the same 512-lane tree, preserving stock 2-simdgroup geometry.
   - **B (top-8 selection folded into the router kernel)** — #268 r2's **C3**. Serial
     chain; lines 861–872 already compute the sigmoid score, bias-corrected key and
     ordinal *in registers*. ⚠️ **PRIOR ART: PR #204 already implemented and reverted
     this** (ΔD = −0.9 ± 12.1 µs, ~46 % power ⇒ underpowered, not refuted). Branch
     `maple-fern/router-top8-fusion` tip `e92d09eb`, tag `pr/204`. Any re-attempt starts
     from that branch, not from scratch.
   - **A (shared-expert gate/up merged into the routed packed top-8 QMV)** — #268 r2's
     **C4, and the discriminator.** Precedent already shipped
     (`laguna_routed_shared_nvfp4_down_residual_bf16_r1_v5` at `:7847`, `shared_slot ==
     8`). **But if the census shows these two QMVs are barrier-free siblings, A refunds
     only ~4.8 µs/step/layer and must be DROPPED** despite being the easiest to write.
   Full code geography is in §4. **A shippable decode arm must bundle ≥3
   barrier-removing fusions to clear the ~80 µs/step 3σ floor, and additivity is not
   guaranteed** (a barrier costs what it drains, so each removal shrinks the next one's
   refund).
3. **✅ CLOSED — ICB pre-encoded step replay, `start_concurrent()`, encode overlap AND
   graph reordering are all dead.** #269 localised the refund to the GPU side
   (Δgap 1 µs vs ΔGPU-busy 139 µs) and #268 finished the job: 99.4–100.2 % of the tax is
   inside GPU busy time and injected CPU spin moves wall by only 0.0497 ± 0.0293 µs/µs
   (32 SE below 1.0). Separately, §4.16 shows MLX's breadth-first eval tape **already**
   collapses forty parallel RAW edges into one barrier — 247 barriers ≈ 6.2/layer against
   ~7 structural waves — so reordering is done inside MLX, off our editable surface, with
   nothing left to win. Also reconcile with the standing note that decode pre-encoding is
   structurally unreachable before anyone re-proposes any of this.
4. **⭐ Prefill (25 % weight) — fully censused; F1 is dead, H2 is the live arm (#293).**
   §4.13 attributes **100 %** of the 54.633 ms non-MoE residual and closes the glue
   class at ~99 % of its bandwidth floor. What remains:
   - **☠️ F1 / H1, fuse the attention input projections — KILLED by #270 r2, see
     §4.13b.** Do not re-propose it as a flag flip, and do not re-propose the
     ~1-line `:5709` fix on its own. Three independent reasons: (a) the flag is
     **not prefill-only** — materialising the fused bank makes *decode* fall back to
     stock BF16 QKV, `decode_speedup` 1.0786 → 0.7705, **below the 0.95 floor**;
     (b) the whole M4 win came from 156 fewer `steel_gemm_bf16` dispatches on wk/wv
     **split-K**, and on M5 wk/wv route *regular*, so the projected M5 dispatch delta
     is **~0** and the prefill central estimate 0.66–1.58 ms **straddles the 1.35 ms
     3σ bar**; (c) the fusion silently adds **78 `g2_copy` slice materialisations**
     (+1.516 ms/request) because the prefill `qk_norm_rope`/`qk_norm_yarn` kernels
     cannot read Q/K/V out of a fused bank. A *real* F1 must first teach those two
     kernels a row offset + stride; only then is it worth ~+0.8–1.2 %.
   - **`steel_gemm_bf16` — frontier consult delivered, see §4.15.** ⚠️ **The 12.30 ms
     projection headroom and the 11.40 ms M5 residual OVERLAP (≈9.33 ms shared inside
     steel) and must NOT be budgeted additively.** Realistic recoverable ceiling
     **≈9–10 ms**, central expectation **3–6 ms**; ~2.5–3.0 ms of the 12.30 is
     peak-margin against a 100 %-of-60-TFLOP/s floor and is definitionally
     unrecoverable. Root cause is **M5-specific tail occupancy starvation**, not tile
     quality in the head classes: wq/wo/dense carry 87 % of the 1502.7 GFLOP at
     AI ≈ 390 and 384–512 TGs/dispatch and are healthy, while wk/wv `(512,1024,2048)`
     miss the NAX split-K tie `K > 2*max` **exactly** (2048 vs 2·1024,
     `matmul.cpp:986-989`) and fall to regular-NAX at a **64-TG grid = 1.6 TGs/core on
     40 cores**. On M4 those same shapes take non-NAX split-K at 1024/256/128 TGs —
     **which is precisely why the M4 census measured the tail as healthy and why this
     deficit is invisible off-M5.** Second-order: wo/dense-down (K ≥ 3·max) migrate
     *into* NAX split-K on M5, paying a ~654 MB FP32-partial round trip ≈ 1.2 ms.
   - **⭐⭐ H2, skinny-N regular-NAX tile downsize (`matmul.cpp:227-238`) — now the
     PRIMARY cheap prefill lead, assigned as PR #293 (tanjiro).** With F1 dead the
     substitution argument is void: H2 owns the whole 78-dispatch wk/wv tail alone,
     **−1.5..−5 ms**. The change is host-side only — force `bn=64, wn=2` (so
     bm64/bn64/bk256/wm2/wn2, 128 TGs = 3.2/core) when
     `ceil(M/bm)*ceil(N/bn) <= 96 && N % 64 == 0`, behind
     `DARKBLOOM_STEEL_REGULAR_SKINNY_TILE`. **Bit-exact by the same argument the
     already-ranked `darkbloom_steel_prefill_tile()` (`matmul.cpp:82-93`, applied in
     split-K at `:709-717`) uses**: each output stays owned by one thread and is
     accumulated over the full K range in ascending order; only threadgroup ownership
     regroups. Legality checked against `steel_gemm_fused_nax.h:150-155` (BM/WM and
     BN/WN must be positive multiples of 16). **⭐ It needs no new AOT
     instantiation**: the regular-NAX path is JIT (`matmul.cpp:282` →
     `jit_kernels.cpp:979-1010` → `get_template_definition`, `kernels.h:404-416`), and
     64/64/256/2/2 is in the AOT list anyway (`steel_gemm_fused_nax.metal:23-29`).
     Cost: ~0.2–0.4 KB, plus a mandatory `./setup.sh` because
     `VendoredMetalFingerprint.swift:18-21` per-file hashes the whole
     `Vendor/mlx-swift/Source/Cmlx` tree. **Unfalsifiable on M4 (gen 16 never selects
     `_nax`) ⇒ Stages 0–2 are offline compile + bit-exactness proof, Stage 3 is a
     ranked M5 receipt.** Trade-off it must survive: bn 128→64 raises wk/wv DRAM
     re-reads from 3.92 GB to 5.23 GB (+33 %) across the 78 dispatches.
   - Banked #170 constraint on the MoE half: staging ≈49 % load-issue / ≈51 % DRAM
     bytes, pure-issue term 6.887 ms = 15.9 % of W = 43.2619 ms, streaming floor
     24.15 ms ⇒ **19.11 ms headroom = 7.16 % of score**. Frontier re-derivation puts
     17.7 GB against a 32.4 ms floor vs 43.3 ms measured = 75 % utilisation ⇒ 75→85 %
     is −5.1 ms = **+1.9 %**.
5. **⚠️ RETRACTED: "kernel time is the ~13× larger budget than the dispatch tax."**
   That ratio compared *total* kernel time against *recoverable* dispatch time. The
   decision-relevant comparison is recoverable against recoverable, and §4.16 has now
   re-priced the second term upward: **~311 µs of kernel time vs 188–371 µs of
   barrier+dispatch tax on M5**, i.e. **0.8–1.7×** out of the ~682 µs/step honest pool
   (§4.10a). These are comparably sized bets,
   so kernel work does not automatically outrank dispatch work — and a kernel-time arm
   no longer gets to claim an order-of-magnitude head start in a prioritisation
   argument. Keep a parallel track, but rank it on measured evidence.
5a. **⭐ Per-kernel decode θ calibration (the enabler).** Every remaining kernel-time
   idea is currently unassignable because **no per-kernel θ exists**. §4.10b records
   why the §4.12 marginal-cost ledger cannot supply one: those costs are deflated by
   E ∈ 0.62–0.75, and naive division attributes 84 % of step time to 56 % of bytes,
   forcing the residual above peak bandwidth. Real per-kernel θ needs isolation with
   `MTLCommandBuffer.kernelStartTime`/`kernelEndTime` (per-dispatch
   `MTLCounterSampleBuffer` is closed), plus one pure streaming-read kernel to fix the
   machine's sustainable GB/s — which §4.10a identifies as **the single largest
   unknown in the whole decode budget** (it swings the pool between ~280 and ~940 µs).
   The same command-buffer split censuses the 54.6 ms non-MoE prefill. No direct
   score; converts every later estimate from a guess into a budget. **Binding rule:
   until this is measured, no arm may claim a per-kernel θ number.**
5b. **Two cheap structural asymmetries in the shared expert** (§4.10b), worth one
   combined arm: the shared gate/up kernel (`:6844`) has **no software pipelining**
   while its routed twin (`:7620-7630`) prefetches one K-block ahead; and shared still
   pays non-pairwise **128 B/row** scales (`:6825-6828`) where the QKV lane-major path
   already banked a 4× reduction to 32 B/row.
6. **tanjiro's surviving `win_ok` ctor-hoist** — an `sdiv` plus two modulo tests per
   k-iteration on loop-invariant inputs, unhoistable across the non-inlined call. This
   is an **ALU-issue** hypothesis and is untouched by #244's closure of the load-bound
   family. Reprice it if #270 finds an issue-bound prefill family.
7. **Byte recovery** (frieren, queued) — see
   [`research/maple-byte-recovery-census-2026-08-07.md`](maple-byte-recovery-census-2026-08-07.md).
   **≈70,131 B at LOW risk** (headroom 49,145 → ≈119,276), ceiling ≈173,725 B. The
   dominant lever is *relocating* 172,594 B of campaign measurement narrative out of
   four `Sources/MLXFastModel/*.swift` files into non-editable `notes/` — comments are
   not compiled, so it is byte-for-byte behaviour-neutral. It also relieves the per-file
   cap on `LagunaRuntimeModel.swift`. **There is no score in this work**: the census
   corrected the backlog's claim that `LMHEAD_ROWMAJOR_REFINE` still needed a default
   flip — it has been default OFF since receipt `99b71258` measured +24.6 µs/token on
   M5. Cleanup buys *capacity for future arms*, nothing else.
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

### ⭐⭐⭐ The 36 standing rules — embed VERBATIM in every assignment brief

This is the canonical list. Until round 34 it lived only in PR bodies, which
made it invisible to anyone reading this file. Rules 1–19 predate round 32;
**20–30 are new since**, **31–36 were added in the final round** from #301,
#308, #309 and the round-39 offline recon, and 1 was amended by #300.

1. **Reachability before null.** ⭐ *Amended by #300:* quote the **dispatch**
   guard chain down to a default value, not the construction site. A kernel can
   be built by default and never dispatched (`lagunaNormAffineQKV`).
2. **Matched controls.** Candidate and control in the same session, same
   thermal gate, palindromic ordering.
3. **Content-hash dedupe (#244).** A byte-identical control is silently deduped
   to a stale cross-session receipt; a control must carry an inert,
   behaviour-neutral perturbation.
4. **Never dispatch a ranked arm from an unpushed tree.**
5. **>70% power before a ranked slot.** Compute the MDE first.
6. **Step 0 residency.** Discard the first step; it pays weight residency.
7. **Ledger rows come from raw `officialMetrics` seconds/token**, never from a
   derived percentage.
8. **Byte budget.** Growth ≤ 12,000 B per assignment unless stated; check
   `senpai/check-editable-budget.sh` before and after.
9. **`_nax` twins.** Any kernel with an `mlx-generated/*.cpp` twin must be
   updated in lockstep and checked with `python3 research/nax_twin_check.py`.
10. **Student hosts are M4 Pro (Apple GPU generation 16).** They do **not**
    select `_nax` kernels. An M4 prefill result is not evidence for an `_nax`
    change.
11. **Instruments stay out of `Sources/`.** Ship probes as unapplied
    `research/*.patch`.
12. **Not editable**: `Vendor/mlx-swift/.../metal/device.cpp`, `device.h`,
    `Transforms+Compile.swift`, `MLXFastKernel.swift`,
    `Sources/MLXFastTrustedHarness/*`.
13. **Correctness is a hard gate.** Every checked greedy token must match.
14. **Interaction contrasts run back-to-back in one session.**
15. **Never commit advisor docs into a student branch.**
16. **The equivalence oracle is structurally blind to the fused-weight family**
    (`LagunaUpstreamEquivalence.swift:74-90` bypasses the weight cache and never
    reaches `prepareFusedRuntimeWeights()`). **Always ship a fault-injection
    arm** and hard-fail the harness if the fault arm cannot be detected.
17. **`DARKBLOOM_*` flags are not axis-local.** Enumerate every flag your file
    touches and state its default.
18. **Search `git branch -r` before briefing a "fresh" idea.** Cross-campaign
    branches (`birch-*`, `cedar-*`) have burned many of them.
19. **Barrier/dispatch refunds must be MEASURED with the real kernel removed**,
    never estimated from a census row.
20. **State WHICH memory profile a barrier count came from** — low-memory
    student profile **247**, full/ranked M5 profile **258**.
21. **New `DARKBLOOM_*` guards that cannot be timed locally ship default-OFF.**
22. **Verify threadgroup-geometry compatibility before any fusion.** Two
    kernels with incompatible grid/threadgroup shapes cannot be merged, and
    this kills more fusion candidates than numerics does.
23. **Consumer-side redundant reduction is NOT free** (#298): +308.3 µs/step at
    5120 TGs, +80.4 at 640 TGs, scaling exponent ≈ 0.64.
24. **Separate every confounded change into orthogonal knobs** and run each as
    its own arm. #48 bundled three mechanisms and produced an uninterpretable
    ranked negative.
25. **A stripped-down "in-situ proxy" kernel is not in situ** (#300): ~49% of
    the isolated cost is hidden when the real kernel runs in the real chain.
26. ⭐ **A cache-served read has no roofline headroom.** Before pricing a kernel
    against DRAM bandwidth, check that the bytes it *requests* are not being
    served from cache — GQA replication alone puts the two fused attention
    kernels above 100% of M4 peak.
27. ⭐ **#298's −2.2/−2.5 µs applies only to an ON-CHAIN (dispatch + barrier)
    pair.** Off-chain dispatch removal is worth ≈0.12–0.22 µs each.
28. ⭐ **`x*1.0f` skips are not free.** FADD and FFMA occupy the same issue slot
    on Apple GPU, and dropping a multiply changes FMA contraction — so the
    cheap form is not bit-exact and the bit-exact form is not cheap.
29. ⭐ **A comment keep-policy regex must include rule idioms, not just
    `must match`.** Byte-recovery relocation is only safe if the classifier
    recognises how we actually write load-bearing constraints. The minimum
    alternation is
    `\bMUST\b|must be|must not|load-bearing|NOT knobs|bit-identical|keep .* in sync|pin(s|ned) those|Exactness`,
    and **every** relocated rule-bearing block leaves an in-source pointer
    regardless of any byte floor. Born in the #320 pre-brief audit: six wave-1
    blocks carrying bit-exactness pins were classified `RELOCATE` by a regex
    that only looked for `must match`. Recovering fewer bytes is always
    cheaper than losing a pin.
30. ⭐ **Denominator hygiene.** Always state whether a *time* denominator is a
    **window** (wall-clock occupancy of a phase) or a **marginal delta** (an
    ablation `dS`), and whether a *byte* numerator is **unique** or **issued**.
    A percentage without both labels is meaningless. Two round-36 corrections
    came from exactly this: `43.2619 ms` is `dS_1`, the marginal cost of the
    routed-MoE block, **not** the prefill window (`S = 97.895 ms`); and the
    router kernel's ~154 µs/step "excess" is an artifact of dividing *unique*
    bytes by a rate that the *issued* bytes already saturate.
31. ⭐⭐⭐ **Grep for prior closure before ranking a "new" lever.** Before a
    recon agent's freshly-surfaced lever is written into a ranking table, grep
    this document's closure sections **and** every
    `research/RESEARCH_STATE_ARCHIVE_*.md` for a PR number attached to the same
    *mechanism*, not the same wording. Round 36 ranked `_nax` scale-load
    amortization first; round 37 found it had already been assigned, run on the
    ranked M5 and closed as **PR #244**
    (`research/tanjiro-nax-kloop-pipeline.md:1064-1078`;
    `RESEARCH_STATE_ARCHIVE_rounds-22-28.md:812-818`). A lever that no longer
    has a report file under `research/` is not thereby unexplored — #244 has no
    report file at all.
32. ⭐⭐ **Coarser grids do not amortise per-threadgroup work; they cost.**
    (#309 §11.4.) Collapsing the decode QKV kernel from 5120 to 640
    threadgroups to amortise the per-TG prologue costs **+174.9 ± 11.0 µs/step**
    (`G128 − G640`), and the T-ladder shows a **cliff once the TG count falls
    below the GPU core count** (16 TGs = +917 µs). Any "persistent" or
    grid-stride megakernel plan must price this term *first*; it is roughly
    twice the size of the entire barrier tax it hopes to refund.
33. ⭐⭐ **A kernel selected by a static name literal needs an arm-specific name
    suffix.** (#308; corroborated at `quantized.cpp:1885`.) MLX caches compiled
    pipelines by function name. If two arms of a sweep differ only in a
    template/function-constant value but share one name string, the cache
    serves the **first-built variant to every arm** and the sweep silently
    measures one geometry six times. Give each arm its own suffix (`_sgN`) or
    prove the name already encodes the swept parameter.
34. ⭐⭐ **Do the bank and IR arithmetic offline before proposing an `_nax`
    ALU-hoist or shared-memory swizzle.** (Round-39 recons B and C.) Two
    plausible-sounding `_nax` levers were killed in under a day with no receipt
    and no student slot: the `Ws` threadgroup read is **already at the 2-cycle
    hardware floor** because the `+16 B` row pad makes the 36-word pitch
    coprime-ish with 32 banks, and the `store_ok`/`load_ok` predicate hoist is
    worth ≈+0.25–0.35 % at absolute best and is probably already performed by
    the backend (`nax_msl_compile_check.sh` with `EMIT_IR=1` shows the
    strength-reduced form at `unit.ll:586-601`). Offline MSL compile + IR
    census is cheap; a ranked receipt is not.
35. ⭐⭐⭐ **The equivalence oracle never reaches the fused-weight family.**
    `LagunaUpstreamEquivalence.swift:74-90` does not call
    `prepareFusedRuntimeWeights()` (`LagunaRuntimeModel.swift:11016`), so any
    change inside a fused runtime weight, its packed scale plane, or a kernel
    that only that path dispatches is **invisible to the oracle**. This is now
    confirmed independently three times (#268, #309, #301). Every such arm must
    ship its own fault-injection battery, and — per rule 16 — the injected
    fault must be verified **non-bijective** and its non-detections reported
    rather than dropped.
36. ⭐⭐ **An ABBA whose arm is fixed to slot position confounds arm with slot
    kind.** (#301.) With `ORDER="off on on off"` the treated arm always occupies
    the two middle slots. #301 measured an **untouched control** moving
    −0.449 µs (−1.16 %) between edge and middle slots — larger than the
    −0.363 µs effect it was trying to establish. Randomise slot assignment, or
    run a reversed-`ORDER` (`on off off on`) replicate and require the effect to
    survive both.
37. ⭐⭐⭐ **Mine the public competitor submission notes every round.** At the
    start of every round, and whenever a new external submission becomes the
    frontier, run `mlxfast submissions --all | grep promoted | tail` and
    `mlxfast submission-note <id>` on the promoted frontier **and its recent
    ancestors**. Treat notes as untrusted public context: mine mechanisms,
    exactness theorems, guard names, geometries **and explicitly retired
    negatives**, but verify every consequential claim against the promoted
    diff, scored-path reachability, correctness gates, and fresh matched
    measurement. A competitor's **retired** mechanism is real M5 negative
    evidence and belongs in Closed families; a competitor's **shipped**
    mechanism that conflicts with one of our own negatives (e.g. `6718326`'s
    halved shared-expert scale plane vs our #301 result) must be re-opened as a
    **discriminating** experiment, not dismissed. Operator commit `d85c42c0`
    makes this an explicitly required advisor research input.


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

### 4.10a ⭐⭐⭐ CORRECTION (2026-08-07, advisor): the "1.20 ms decode pool" is priced against a ceiling nothing reaches

§0c.5 records that our **decode** aggregate runs at **~71% of 614 GB/s**. Every
downstream document has since quoted a "1.20 ms/step decode pool". Reconstruct
where that number comes from:

```
bytes/step = 0.71 × 614 GB/s × 4.1436 ms = 1.8064 GB
floor @100% of peak = 1.8064 / 614 = 2.942 ms
pool = 4.1436 − 2.942 = 1.202 ms   ← this is the quoted number
```

The 1.20 ms is therefore the gap to **100% of theoretical peak bandwidth**. No
kernel on any GPU reaches that. Quoting it as a pool overstates the prize by
roughly a factor of two, and it has been silently inflating every decode
priority calculation we have made.

Re-price it against the ceilings §0c.5 actually establishes:

| assumed achievable ceiling | floor | recoverable | score |
|---|---|---|---|
| 100% of peak (fictional) | 2.942 ms | 1202 µs | +18.36% |
| **85% — GPU STREAM on M1–M4 (arXiv 2502.05317)** | **3.461 ms** | **682 µs** | **+10.43%** |
| 80% | 3.677 ms | 466 µs | +7.12% |
| 75% | 3.923 ms | 221 µs | +3.38% |
| 54% — llama.cpp Q4 decode, M4 Max | *already surpassed* | — | — |

**The honest number is ≈682 µs/step ≈ +10.4% score**, using 85% as the ceiling
a perfect streaming kernel reaches. That is still the largest single prize in
the programme — but it is half of what we have been quoting.

**Four consequences, all binding:**

1. **The dispatch tax is 41% of the achievable pool, not 24%.** 283 µs/step
   (+4.32% score) against a 682 µs pool. PR #268 is correctly the P0 gate; this
   raises its priority rather than lowering it.
2. **"Kernel time is 13× the dispatch budget" is the wrong comparison and I
   should not have used it.** Total kernel time is indeed ~13× the dispatch
   tax, but almost all of it is irreducible bandwidth-bound streaming that no
   optimization can remove. The decision-relevant comparison is *recoverable*
   kernel time versus *recoverable* dispatch time: **399 µs versus 283 µs, i.e.
   1.4×**. Kernel-time work and dispatch-tax work are comparably sized bets,
   not a 13:1 mismatch. Any framing that says otherwise is retracted.
3. **§4.10's discipline now applies to decode verbatim.** The byte total is
   pinned by the model and the NVFP4 format; the FLOP total at batch 1 is
   trivial. **Only θ moves.** Every decode kernel proposal must be stated as
   "this raises achieved bandwidth utilisation θ from 0.71 to X, by mechanism
   Y", with X ≤ 0.85, or it is not a proposal. A proposal that cannot name its
   θ mechanism is asking for time it cannot spend.
4. **The whole decode programme lives inside a 14-point band of θ**, from our
   0.71 to the 0.85 ceiling. Each point of θ is worth ≈49 µs/step ≈ **+0.75%
   score** — about 3× the 3σ detection floor, so a one-point θ gain is
   measurable but only just. Arms should target ≥2 points.

**Why would a batch-1 GEMV miss the streaming ceiling at all?** At batch 1 the
arithmetic intensity is `2 × 1 / 0.5625 = 3.56 FLOP/B`, which is far to the
*left* of the 56.9 FLOP/B ridge point — decode is deeply bandwidth-bound in
theory and the FLOP pipe is nearly idle. So the 14-point deficit is **not**
FLOPs. Three candidate mechanisms, in cost order to falsify:

- **(a) Threadgroup occupancy.** All three dominant decode GEMVs dispatch with
  **threadgroup = 64 threads = 2 simdgroups** (QKV `((rows/2)*64,1,1)`/tg 64;
  routed packed top-8 `8*256*64`/tg 64; shared `256*64`/tg 64). Two simdgroups
  per threadgroup is a thin latency-hiding budget for a pure streaming load.
  **This is potentially bit-exact by construction**: if each output element's
  reduction lives entirely inside its own simdgroup, enlarging the threadgroup
  changes only scheduling, never accumulation order. That combination — cheap,
  bit-exact, and aimed straight at θ — makes it the first thing to test.
  ⚠️ AGENTS.md warns threadgroup geometry can change sign across core counts,
  so an M4 Pro result here is **not** M5 evidence.
- **(b) NVFP4 unpack issue pressure.** §4.10's "third resource" applies
  unchanged: dynamic `BITEXTRACT`/`BITINSERT` costs 8–12 cycles and 64-bit
  address arithmetic is emulated in 4 ops. None of this appears on *either*
  roofline axis, so it is exactly the kind of work that caps θ below the
  streaming ceiling while leaving both roofs unsaturated.
- **(c) Scale-plane locality.** The quantization scale plane is a second
  concurrent stream with its own row stride; if its access granularity is
  below a cache line, real DRAM traffic exceeds the 1.8064 GB accounting and
  the true θ is *better* than 0.71 while the recoverable pool is *smaller*.
  This one can invalidate the table above rather than exploit it, so it is a
  measurement prerequisite, not an optimization.

**Falsifier for the whole section:** the 1.8064 GB/step figure is derived from
§0c.5's 71%, not measured. An independent bottom-up byte census (sum the actual
per-step read set: all non-expert weights, 8/256 of routed expert bytes, shared
expert, lm-head, KV at 512 positions) that disagrees materially with 1.8064 GB
invalidates this pricing. **Commission that census before spending a ranked
slot on any θ arm.**

---

### 4.10b ⭐⭐⭐ Decode GEMV geometry census (2026-08-07) — occupancy is NOT the problem, and lm-head is the one place bytes are not pinned

Full census with line numbers: read directly from the live decode path. Two
framing errors of mine are corrected, and one large target is de-risked.

**Reading correction that invalidates the occupancy hypothesis.** MLX
`metalKernel` `grid:` is a **total-thread** count (`dispatch_threads`), not a
threadgroup count — `Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/custom_kernel.cpp:116-117`.
So `tg = 64` does **not** mean 2 simdgroups in flight; it means 2 simdgroups
*per threadgroup* across thousands of threadgroups:

| kernel | threads | TGs | simdgroups/TG | rows/simdgroup | weight B/step | B/thread |
|---|---|---|---|---|---|---|
| QKV lane-major `..._lm1_pw1_se1_sd1` (:4799) | 327,680 sl / 262,144 full | 5120 / 4096 | 2 | 1 | 10.0 / 8.0 MiB | 32 |
| routed packed top-8 (:7546) | 131,072 | 2048 | 2 | 1 (gate+up) | 8.0 MiB | 64 |
| shared gate/up (:6802) | 16,384 | 256 | 2 | 1 (gate+up) | 1.0 MiB | 64 |
| fused down+residual `..._r1_v5` (:7847) | 147,456 | 512 | **9** | 4 | 4.5 MiB | 32 |
| lm-head coarse (:266, `LagunaLmHeadPrune.swift`) | 3,211,264 | 6272 | **16** | 1 | **104.1 MiB** | 32 |
| o_proj (:4237) — *the outlier* | 16,384 | 256 | 2 | **4** | 8.0 / 6.0 MiB | **512 / 384** |

5120 threadgroups over ~40 cores is 128 TGs per core. **There is no occupancy
starvation.** §4.10a mechanism (a) is withdrawn as stated; do not assign it.

**Load width is already near-optimal, and widening it is NOT bit-exact.** Every
NVFP4 kernel loads one **8-byte `uint2`** per 16-value group, and 32 adjacent
lanes cover a contiguous 256 B burst — perfectly coalesced. Widening to
`uint4` would require each lane to own 32 values instead of 16, which
repartitions the per-lane serial float accumulation before `simd_sum` and
therefore **changes the summation tree**. Not bit-exact; the hard greedy-token
gate kills it. Record this so nobody re-proposes it.

**What the census did find in the kernels themselves** (all small, all real):
- The shared gate/up kernel (:6844) has **no software pipelining**, while its
  routed twin (:7620-7630) prefetches one K-block ahead. Same NVFP4 format,
  same reduction. Porting the prefetch is a like-for-like change on 39 MiB/step
  of traffic. Small, but it is the cheapest structural asymmetry on the board.
- Scale-plane traffic is already heavily optimised and **wildly non-uniform**:
  QKV lane-major uses a pairwise 2-byte nibble read (32 B/row) where the stock
  plane would cost 128 B/row — a 4× reduction already banked; the shared kernel
  still pays the full non-pairwise 128 B/row (:6825-6828). Extending pairwise
  scales to the shared expert is the same class of change as the prefetch.
- o_proj is the geometric outlier at 4 rows/simdgroup and 512 B/thread, 8–16×
  every other kernel. Whether that is good or bad is untested; it is the
  natural control for any rows-per-simdgroup arm.

**~~⭐ THE STRATEGIC FINDING: lm-head is the one place where the byte total is
not pinned, which makes it categorically different from every other decode
idea.~~ ⚠️ RETRACTED 2026-08-07 by PR #284 — see §4.17.** The greedy-argmax
identity *does* legally permit sound pruning, but #284's certificate-slack
histogram shows the live 4-bit tier-0 screen is already at the boundary
(`R ≡ (thr − c₁)/delta` never exceeds 5 in 129 real steps, and a 3-bit plane
needs `R > 5`). **No sound cheaper first screen removes a single byte of the
109.19 MB tier-0 read.** The lm-head is now retired as a decode target. The
paragraph below is preserved as the reasoning that motivated #284; its
conclusion is dead.

§4.10a states that the per-step byte total is fixed by the model and the NVFP4
format, so **only θ moves** — capped at 0.85. That is true for attention and
MoE. It is **false for the lm-head**, because the greedy-argmax identity
permits any *provably sound* pruning. Moving B has no 0.85 cap.

The census settles H5's "free first experiment" (§11.5), which asked whether
the existing screening already prunes payload bytes. **It does not.** The live
decode path takes the fused-refinement arm and dispatch 5a
(`laguna_lmhead_int5_base_coarse_delta_bf16_v1`, :266) streams the **entire**
100,352-row coarse plane every single step: 100,352 × 1024 B codes + 100,352 ×
64 B e8m0 scales = **109,182,976 B = 104.1 MiB**. Pruning happens only
*downstream* of that read — 5b argmaxes the coarse scores, 5c exactly verifies
one winner row (4 KB), 5d refines "single digits" of survivor blocks. So today
the pruner avoids the 411 MB full-BF16 pass but pays the full coarse plane.

**H5 is alive and is now the best-characterised large decode target we have.**
At H5's own 1–5% survivor estimate the coarse read drops ~71 MB, worth
**≈163 µs/step ≈ +2.5% score** at current θ — and unlike a θ arm it is not
competing for the same 14-point band.

**Honest caveat on per-kernel pricing — do not skip this.** It is tempting to
divide 104.1 MiB by the ledger's 474 µs lm-head figure and conclude θ = 37.5%,
i.e. half the 71% aggregate. **That arithmetic is invalid.** The §4.12 decode
ledger reports *marginal* costs, deflated by the exposure factor E ∈ 0.62–0.75;
the same division applied to all four big families yields 84% of the step from
56% of the bytes, and the residual families then exceed peak bandwidth — which
is impossible. Marginal costs cannot produce per-kernel θ. Establishing a real
per-kernel θ needs isolated timing via `MTLCommandBuffer.kernelStartTime` /
`kernelEndTime` (the per-dispatch `MTLCounterSampleBuffer` route is closed,
§8). **Until someone measures that, no arm may claim a per-kernel θ number.**

**Ranking consequence.** For the next decode round the order is: (1) H5
lm-head sound pruning — moves B, uncapped, 104.1 MiB confirmed unpruned;
(2) #268's dispatch-tax attribution — 283 µs, 41% of the θ pool, already in
flight; (3) the two shared-expert asymmetries (prefetch, pairwise scales) as a
cheap combined arm; (4) any θ mechanism, but only after per-kernel θ is
actually measured.

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

### 4.13 ⭐⭐⭐ PR #270 — the non-MoE prefill census, 100% attributed

Deliverable: [`research/maple-tanjiro-nonmoe-prefill-census.md`](maple-tanjiro-nonmoe-prefill-census.md)
(628 lines) plus `research/pr270-logs/*` (~14,500 lines),
`research/tanjiro_prefill_census.sh`, `research/tanjiro_steel_trace.sh`,
`research/pr91-gpuprof-hook.patch`. All research-only; submitted-surface growth 0.

**Result: 100% of the residual R = S − W = 97.895 − 43.262 = 54.633 ms is now
attributed**, across all 1222 M4 prefill dispatches and 12 families. The stopping
condition was ≥85%.

**Method.** A byte-emitting MLX dispatch hook (`device.cpp`/`device.h`) plus a
steel-GEMM shape trace (`matmul.cpp`), both **LOCAL-ONLY and reverted** — neither file
is editable. Instrument tax was measured, not assumed: SPLIT=0 wall 545.718 ms with
per-CB busy sum == union 540.396 ms over 81 CBs, 1222 dispatches, 24.717 GiB; SPLIT=1
576.734 vs 546.019 ⇒ **5.7 µs/CB**. `arangeuint32` (26.586 ms) is *provably fully
hidden* ⇒ 0 marginal cost. Deflation factor 0.982275.

**Structure — the biggest structural finding.** Three independent reconciliations agree
on **38 sorted-path MoE layers plus a layer-39 terminal fusion**. This settles the open
question recorded at `CURRENT_RESEARCH_STATE.md:346`: W prices 38 routed blocks, so **R
is genuinely non-MoE** and the two ledgers do not double-count. The steel route table is
**155 split-K + 82 regular**, predicate at `matmul.cpp:971-983` / `:1008-1010`.
Pipeline state captured for all 137 PSOs; the tightest is `steel_attention
bd128_wm4_wn1` at 14848 B ⇒ 2 threadgroups/core. `maxThreads` values of 128/256 are
**declared attributes, not register ceilings** ⇒ there is no register-driven occupancy
cliff to chase.

**⭐ Derived M5 `_nax` routing (the actionable part).** Applying the NAX split-K
predicate to the traced shapes: **wk/wv (78 dispatches) FAIL it on the exact tie
`2048 > 2048` and run regular at only 64 threadgroups**, while **wo (39) and the dense
down projection (1) migrate INTO NAX split-K.** This is a shape-derived prediction about
the ranked host, not an M4 measurement.

**Ledger, Projection A onto R** (ms, and % of S at 0.374750 %/ms):

| family | ms | % of S |
|---|---|---|
| `steel_gemm_bf16` | **37.93** | **38.7%** |
| `attention_core` | 4.88 | 5.0% |
| `nvfp4_dense_qmm` | 3.47 | 3.5% |
| `elementwise` | 2.21 | 2.3% |
| `qk_norm_rope` | 1.97 | 2.0% |
| `sort_scatter` | 1.24 | 1.3% |
| `moe_tail` | 1.21 | 1.2% |
| `rms_norm` | 0.81 | 0.8% |
| `router` | 0.45 | 0.5% |
| `lm_head` | 0.31 | 0.3% |
| `other` | 0.15 | 0.2% |

Projection B sums to 86.50 ms against S = 97.895 ⇒ **11.40 ms (11.6% of S) of
M5-specific loss is localised to the tiny-N GEMM tail.**

**Headroom against analytic floors:** steel **12.30 ms = 4.61% of score** (the largest
named prefill target on the board, currently unassigned); `attention_core` 2.19 ms
(0.82%); `nvfp4_dense_qmm` 1.38 ms (0.52%); glue ≈0.10 ms; `lm_head` **−0.44 ms**
(already below its floor estimate). Total ≈15.9 ms ≈ 5.95%.

**⭐ DECISIVE NEGATIVE — the prefill "glue" class is closed.** elementwise + moe_tail +
qk_norm_rope + rms_norm + router together bind **4.34 GB ⇒ a 7.94 ms DRAM floor against
8.04 ms projected = ~99% of its bandwidth floor.** No scheduling, fusion, or geometry
change can help; **only byte elimination can.** This **retires
`PREFILL_NAX_ANALYSIS.md` H4 as a time target.**

**Correction banked:** the HOST-DIVERGENT share is **91.5% of S (89.54 ms)**, not 94.2%
— the old figure was an M4 numerator over an M4 denominator.

**⭐ F1 — the headline follow-up.** Fuse the attention input projections.
`DARKBLOOM_FUSED_QKV` is default-OFF at `LagunaRuntimeModel.swift:108-114` because of an
M4 ablation in which fusion destroyed wk/wv split-K — **but on M5 wk/wv are already
regular at 64 threadgroups, so that cost term does not exist there.** Step 0 is *zero
code* (flag = 1) and removes 78 dispatches: −0.5 to −4.0 ms, **central −1.6 ms =
+0.60%, ≈3.6σ**. Step 1 is a 4-way `[Wq;Wk;Wv;Wg]` bank (precedent:
`prepareLastPrefillProjectionWeights()` at `:5612+` already concatenates wq + g_proj):
−0.3 to −1.5 ms more, ≈60 lines. **F1 total central −2.2 ms = +0.82%.** It is
**unfalsifiable on M4 by construction** ⇒ it needs an M5 receipt.

F3 (`lagunaPrefillQKHeadsPerGroup=4`) cuts 1.39M → 0.35M threadgroup launches but sits
only 0.20 ms above its floor ⇒ **free rider only**. F4 (wo + dense-down into NAX
split-K) costs a ~654 MB FP32 round-trip ≈ 1.20 ms = 0.45% with **uncertain sign**.

Caveats: M4 Pro, 20 GPU cores, gen 16, no `_nax` available; M5 core count assumed 40 and
the arch suffix `s` is inferred.

### 4.13b ⭐⭐⭐ PR #270 r2 — F1 / `DARKBLOOM_FUSED_QKV` is KILLED, and the oracle is blind

Note [`research/maple-tanjiro-pr270-r2-f1-preclearance.md`](maple-tanjiro-pr270-r2-f1-preclearance.md)
(421 lines) plus `research/pr270-logs/*` and `research/tanjiro_f1_iterate.sh`. Status
`succeeded`. **Verdict: `DARKBLOOM_FUSED_QKV` / F1 / §4.15-H1 must NOT get a ranked
slot — neither as specified nor after the ~1-line fix.**

**Correctness both arms.** 64-step tripwire identical (`max_abs_diff=0`,
`checked_steps=130`, `golden_hash=b9509697…`). `LagunaUpstreamEquivalence` byte-identical
(`EXACT_STEPS=8`, `EXIT=1` in both) ⇒ the non-zero exit is a **pre-existing gen-16 M4
condition**, not a regression.

**The dispatch delta is exactly −78, and it is a mirage.** Command buffers 1066→988,
dispatches 1222→1144. But `steel_gemm_bf16` 392→236 (**−156**) while `qk_norm_rope`
41→119 (**+78**): those 78 additions are `g2_copy` general-strided copies, 2/layer × 39,
materialising the Q/K/V slices at `LagunaRuntimeModel.swift:5892-5894`, costing
**+1.516 ms/request**. Route delta 155 split-K / 82 regular → **77 / 82**;
splitK+accum 35.758 → 7.488 ms; regular steel 182.918 → 203.974 ms; steel total
−7.213 ms; probe wall −0.67%.

**The matched M4 pair fails the floor.** prefill −1.61% **but decode
0.0128459 → 0.0179835 s/tok = +39.99%**; `decode_speedup` 1.0786 → **0.7705** (hard-floor
FAIL); score proxy −21.98%.

Four findings, in order of durability:

**(A) The flag is not prefill-only.** `LagunaRuntimeModel.swift:5709` guards the entire
fused decode norm + INT8-QKV block on `_fusedQKVWeight == nil`, so materialising the bank
at `:11027` makes decode fall back to stock BF16 at `:5905-5908`, losing
`lagunaNormAffineQKV`, the g32 INT8 native-affine QKV bank, the gate rows and the
deferred-gate path: **+5.138 ms/step, 3.7× the in-code `:5877-5880` prediction**. The use
site `:5881` is already gated on `L>1`, so the repair is ~1 line. This is now
**standing rule 17**.

**(B) ⭐⭐ Team-wide correctness-gate gap** — see **standing rule 16**. The oracle never
calls `prepareFusedRuntimeWeights()`, so it is structurally blind to the whole
fused-weight family. This is the single most transferable output of the revision.

**(C)** An env flip can never ship F1 anyway; it needs the `lagunaFusedQKVEnabled`
default flip at `:108-114`.

**(D) DECISIVE — the M4 win does not exist on M5.** All −156 steel dispatches come from
wk/wv split-K GEMMs plus their accumulators, but **on M5 wk/wv route *regular*** (§4.15
route table: they miss the split-K tie at `matmul.cpp:986-989` by exactly one strict
inequality). The M5 projection is −117 regular, +39 fused, **0 accumulators saved**,
+78 `g2_copy` ⇒ **net ≈ 0 dispatches**, and prefill central **0.66–1.58 ms straddles the
1.35 ms 3σ bar**. A no-evidence arm at best.

**What a real F1 would require:** teach the sliding `qk_norm_rope` and full
`qk_norm_yarn` *prefill* kernels to read Q/K/V from the fused bank via a **row offset +
stride**, eliminating all 78 copies, and relax the `:5709` decode guard. Central estimate
then ≈ 2.2–3.1 ms ≈ **+0.8–1.2%** — real, but a multi-kernel project, not a flag flip.
The student additionally recommends **F4 be re-triaged on its own merits** rather than
inheriting F1's fate.

### 4.14 ⭐⭐ PR #269 — the decode dispatch census and the removal price

Note [`research/maple-nezuko-compiled-elementwise-fusion.md`](maple-nezuko-compiled-elementwise-fusion.md)
(403 lines) plus `research/nezuko_compile_{abba.sh,census.sh,probe.py,stats.py}` remain
durable on the closed PR. The hypothesis died; the instruments and three measurements
are the return.

**Census — the default decode path issues exactly 406 dispatches/step.** Only three
families are not Laguna-custom: `rmsbfloat16` (41/step), `argmax` (1), `gather_front`
(1). There are **zero** `binary*`/`unary*`/`ternary*`/`copy*` dispatches.
`compiled{}` fuses only `is_fusable = is_unary || is_binary || is_ternary ||
is_broadcast` (`compile.cpp:77-79`), with Reduce/ArgReduce explicitly excluded
(`:72-74`); Custom, Gather and `fast::RMSNorm` match none of those. **N = 0 is
structural, not a tuning failure.**

**Price — +1.233 µs per removed dispatch, 95% CI [+0.920, +1.545]**, obtained by *real
removal* rather than injection. ABBA design `B,(C U U C)×4,B`, 18 workers, 255 steps,
warmup 8, n = 247/run, measured on the off-default stock router tail
(`DARKBLOOM_FUSED_ROUTER=0`, 39 gates/step). B 8181.1 µs/step (n=2); C 8870.0 (sd 16.8,
n=8); U 9014.3 (sd 32.6, n=8). Block-paired U−C = **+144.23 µs/step, sd 23.00, t =
+12.54, CI [+107.6, +180.8]**; session drift is 8.5% of the effect. An independent
census route gives +1.18 µs.

**Dispatch accounting:** B 406, U 679, C 562 per step, with **45 command buffers in all
three arms**. U−C = 117 = exactly 3×39; `v_copy | v_Sigmoid | vv_Add | v_Negative`
collapse into one kernel. Negative control: the Divide-compiled kernel still sits beside
an unchanged `row_reduce_small_1_reduce_sum` ⇒ 0 removed, exactly as `is_fusable`
predicts. A per-CB decomposition over 8 signatures gives 1.01–1.40 µs/removed dispatch
⇒ **true elimination, not relocation.**

**⭐ Mechanism — E1 refuted** (see the headline section above): Δ(gap) = 1 µs vs Δ(GPU-busy
union) = 139 µs, agreeing with ABBA to 0.4σ; total gap *anti-correlates* with dispatch
count (406 → 355 µs, 679 → 233 µs).

**Rules-legality, verified in source:** `CompilerCache::find` (`compile.cpp:318-368`)
keys only on closure id, stream/device, shapeless flag, and per-input ndim/shape/dtype;
`has_same_shape_and_dtype` (`:327-345`) never reads contents; the constants escape hatch
is unreachable because `Transforms+Compile.swift:91` passes an empty array (count 0).

**Correctness discipline worth copying:** the default arm still showed 406
dispatches/step; 0 golden divergences on all census arms and all 18 ABBA runs; C and U
token streams bit-identical; equivalence `maxAbsLogitError = 0` on all 8 decode steps.
The single prefill divergence (0.125, meanAbs 0.011933609) was **proven pre-existing** by
a byte-identical control on the *unmodified base file* agreeing to 9 significant figures
— that is the template for handling an M4 near-tie.

**Do not resurrect the rejected diff:** `lagunaCompiledRouterTailEnabled` (env
`DARKBLOOM_COMPILED_ROUTER_TAIL`, gated on `MLXHardwareInfo.isCompiledDecodeSupported`),
`lagunaCompiledRouterScores`, `lagunaCompiledRouterNormalize` near
`LagunaRuntimeModel.swift:9459`, rewiring the stock fallback `else` at ~9588-9612;
+40/−5 lines, growth 1,766 B, per-file 470,102 B. It was dead by default and carried an
untested `projectedLogits` vs `logits` asymmetry.

### 4.15 ⭐⭐⭐ Frontier steel_gemm consult (2026-08-07) — the prefill GEMM tail is occupancy-starved on M5, and the two headroom numbers overlap

Full report: [`research/RESEARCH_IDEAS_steel-gemm-prefill.md`](RESEARCH_IDEAS_steel-gemm-prefill.md)
(268 lines). Top-down from the §4.13 route table; no new measurement. Section index
inside that file: `:32` GEMM inventory, `:71` root causes, `:98` hypotheses (H1 `:100`,
H2 `:139`, H3 `:170`, H4 `:187`, H5 `:200`), `:217` the 11.40 ms residual, `:238` what
could not be determined.

**Inventory.** The 512-token prefill issues 237 steel dispatches for 1502.7 GFLOP. At
60 TFLOP/s that is a 25.05–25.63 ms floor against 37.93 ms actual. The head classes
(wq / wo / dense) carry 87 % of the FLOP at arithmetic intensity ≈ 390 with 384–512
threadgroups per dispatch — **they are healthy**. Fitting the 37.93 ms total with the
M4-measured head efficiencies held fixed forces the tail to ≈ **24 % of peak**
(13.2 ms against a 3.2 ms floor). The deficit is concentrated, not diffuse.

**Root causes, ranked.**

1. **Tail occupancy starvation on 40 cores — 6.5–10.3 ms (≈55–85 % of the excess).**
   wk/wv at `(512, 1024, 2048)` fails the NAX split-K predicate `K > 2*max(M,N)` on the
   *exact tie* (2048 vs 2·1024) at `matmul.cpp:988-991`, so it takes regular-NAX, whose
   devc-`s` tile choice (`matmul.cpp:227-238`: bm=64, wm=2, bk=256) yields an 8×8 =
   **64-threadgroup grid = 1.6 TGs/core**. The router adds 64 TGs, g_proj 16 TGs (worse
   per dispatch, small in GFLOP). ⭐ **On M4's 10 cores the same shapes route to
   *non*-NAX split-K at 1024/256/128 TGs — which is exactly why §4.13's M4 census
   measured the tail as healthy, and why this deficit is M5-specific and invisible
   locally.**
2. **wo-class NAX split-K migration — 1.5–5.1 ms (≈12–40 %).** wo and dense-down
   (K ≥ 3·max) migrate *into* split-K on M5 while staying regular on M4. Cost: an extra
   FP32-partial write+read ≈ 654 MB ≈ 1.2 ms, plus split-K's efficiency loss (M4
   measured split-K at 67.7 % vs regular 89.5 %). The already-merged
   `darkbloom_steel_prefill_tile` regroup (`matmul.cpp:87-94`, applied at `:718`) raised
   that grid 128 → 512 TGs; **whether §4.13's projection A already includes its benefit
   is undetermined.**
3. **Peak margin ≈ 2.5–3.0 ms (≈20–25 %) — definitionally UNRECOVERABLE.** The floor
   assumes 100 % of 60 TFLOP/s; the best kernels anywhere in this family reach
   87.5–89.5 %.
4. **Dispatch/launch boundaries — 1.5–4.6 ms — an ALTERNATIVE attribution of cause 1,
   not an additive one.** 155 tail dispatches at O(10–30 µs) each. The measured M5
   command-buffer marginal (27.2 µs/CB × 81 CBs ≈ 2.2 ms) is already booked separately
   under glue. H1 collapses both attributions at once, which is part of why it is the
   top pick.

⚠️ **KEY RECONCILIATION — do not budget additively.** §4.13's 12.30 ms steel projection
headroom and its 11.40 ms M5-specific residual **overlap by ≈9.33 ms inside steel**.
The realistic recoverable ceiling is **≈9–10 ms**, with a central expectation of
**3–6 ms**. Every earlier note that added those two numbers is wrong.

**H1 = census F1, and it is the top pick.** Ship `DARKBLOOM_FUSED_QKV` Step 0 (flag
default flip at `LagunaRuntimeModel.swift:112-114`), then extend to a 4-way
`[Wq;Wk;Wv;Wg]` bank (`:5590-5610`, `:5881-5896`). Folding the 78 wk/wv dispatches into
the wq GEMM takes that grid to **640 TGs**. Central **−3 ms (range −1..−7)** for Step 0
plus ≈ −1 ms for Step 1 — roughly double §4.13's bottom-up −1.6 ms, and it supplies the
mechanism §4.13 could only infer. **Bit-exact on M5**: same regular-NAX kernel, bk stays
256, only threadgroup ownership regroups, with `matmul.cpp:87-94` as precedent. M4 may
show LSB drift because the *route* changes there, so use the near-tie control template
from §4.14. Bytes ≈ 0–3 KB. Falsifier chain: static predicate replay (done) → M4
equivalence + dispatch census with the flag on, predicting exactly **−78** dispatches
(in flight as #270 r2) → one ranked Step-0 run that doubles as the tail-share
measurement. **Kill at Δprefill < +0.3 %.**

**H2 = skinny-N regular-NAX tile downsize — the pre-cleared fallback.** When the grid
would fall below ≈2 TGs/core (N ≤ 1024 at M = 512), pick a smaller tile at
`matmul.cpp:227-238`. Legal per `gemm_nax.h:35-37` (SM = BM/WM ≥ 16; TN = SN/16 even
or 1): bm64/bn64/wm2/wn2 → 128 TGs, bm32/bn128/wm2/wn4 → 128 TGs, bm32/bn64 → 256 TGs.
**Host-side parameters only — no kernel source or JIT-twin change**, though it does
require a metallib rebuild. Bit-exact (bk stays 256; no FP32-partial pass is
introduced). ⭐ **H1 and H2 are SUBSTITUTES, not complements** — same wk/wv target set.
H2 is worth −1.5..−5 ms *if H1 is absent* but only −0.5..−1 ms incremental once H1
ships, which is below MDE. Run H1 first; hold H2. **H2's falsifier is FULLY OFFLINE**
(`research/nax_msl_compile_check.sh`: MSL compile + pipeline stats proving non-empty
MMA; the known NAX failure modes — odd TN>1 and SM<16 — are statically excluded), so it
costs no ranked slot and can be handed to any free student at any time. There is no
local dynamic test: M4 never selects `_nax` and `MLX_METAL_NO_NAX` is unreachable
through SwiftPM.

**H3/H4/H5 are dominated and none is bit-exact.** H3 flips the split-K tie to
`K >= 2*max` (one byte, −3..+1 ms); H4 forces wo-class regular for K ≥ 3·max (−2..+2 ms,
mainly a *diagnostic* for the 11.40 ms residual); H5 raises the router split-K partition
count (≈1 ms). Run them only if H1 and H2 both die.

**The 11.40 ms residual.** The primary discriminator is the H1 Step-0 receipt itself;
the H4 A/B gives a ±2 ms wo-class attribution. **No on-box M5 profiling channel exists**
— `device.cpp` is not editable and every route above is predicate-derived. The frontier
recommends requesting **one Metal System Trace session on any M5 dev host** before
spending multiple ranked slots on this residual.

**Explicitly undetermined:** there is no M5 timing ground truth anywhere in this
analysis (60 TFLOP/s and 40 cores are assumed, and the devc arch branch on M5 is
inferred); whether projection A already includes the merged wo regroup; the JIT
pipeline-cache cost of introducing new tiles; and near-tie argmax stability for the
non-bit-exact options, which is provable only on M5.

### 4.16 ⭐⭐⭐ PR #268 r1 — the tax is charged per BARRIER, and the lever is kernel fusion

Note [`research/maple-fern-dispatch-tax-attribution.md`](maple-fern-dispatch-tax-attribution.md)
(874 lines) plus `research/fern_tax_{campaign.sh,probe.py,stats.py,wandb.py,inject.patch,device_counters.patch}`.
W&B run [`rcj6tohw`](https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/rcj6tohw)
(the campaign's first local-timing W&B run). Primary metric
`fusion_refund_us_per_dependent_pair = 1.4234`. **This section supersedes the
"per-dispatch tax" framing everywhere else in this document.**

**The joint fit.** Six site arms, n = 288, 36 blocks, df = 250, M4 Pro teacher-forced
golden decode at 8.18 ms/step = **406 dispatches / 247 barriers / 40 layers**:

| term | coefficient | 95% CI | t |
|---|---|---|---|
| **barrier** | **+1.3003 ± 0.0597 µs** | [1.1833, 1.4174] | **21.8** |
| **dispatch** | **+0.1231 ± 0.0481 µs** | [0.0288, 0.2173] | 2.6 |
| **sum = one dependent pair** | **+1.4234 ± 0.0256 µs** | [1.3732, 1.4736] | — |

A 4-arm in-chain replicate gives +1.4134 ± 0.0287. The barrier term is **11.6×** the
barrier-free dispatch term.

**Every rival mechanism is refuted.** **E1 (CPU encode starvation)** — 99.4–100.2% of the
tax sits inside GPU busy time; injected CPU spin moves wall by only
**+0.0497 ± 0.0293 µs/µs, 32 SE below 1.0**. **E2 (per-dispatch fixed cost)** survives
only as the 0.123 µs residue (8.6% of a pair); 160 *barrier-free* dispatches cost
**−5.6 µs** against +224 µs predicted (≈40σ). **E3 (cache/residency)** — 256 B..4 MiB is
exactly linear at **1.3489 ± 0.0181 µs + 4.172e-6 ± 9.6e-9 µs/byte**; the slope is
239.7 GB/s = 88% of the host's 273 GB/s peak, i.e. ordinary DRAM traffic, not a barrier
effect. **E4 (encoder/PSO switching)** — 1/4/16/64/256 distinct kernels give
1.3469/1.5201/1.5507/1.5472/1.4871, non-monotone. **E5 (anchor artefact)** — two
anchor-free arms reproduce the split. **E6 survives:** loss of intra-encoder overlap when
`maybeInsertBarrier` emits `[encoder memoryBarrier]` (`device.cpp:363-375`,
`set_input_array` `:315-328`).

**⭐ Four observed properties of the barrier charge.**
1. It is charged **per barrier**, not per dispatch.
2. It is charged **off the critical path**: the `chain` arm's 157 *extra* barriers cost
   **−42.8 µs**. *A barrier costs what it drains* — if there is nothing in flight, it is
   free.
3. It is charged **per unit of serial depth**, not per raw RAW edge.
4. `diamond1`: 80 *parallel* RAW edges raise the barrier count by only **4** and cost
   **−0.0070 ± 0.0212 µs/dispatch**, while the same 80 edges in *series* create 78
   barriers and cost 110 µs.

**Mechanism.** MLX's breadth-first eval tape plus `maybeInsertBarrier` moving `next_*`
into `prev_*` collapses forty parallel edges into a single barrier. The measured 247
barriers ≈ the model's true **serial depth** — 6.2 per layer against ~7 structural waves.
**Graph reordering is therefore already done inside MLX, and is not on our editable
surface.**

**Cross-validation against #269.** Its 117 removed dispatches formed a dependent chain ⇒
prediction 117 × 1.4234 = **166.5 ± 3.0 µs** vs measured **144.23 ± 23.00 µs** = **0.96σ**.
A barrier-free-only model predicts 14.4 ± 5.6 µs = **5.5σ low**. The two independent
campaigns agree.

**The prize, and the ladder.** 247 × 1.3003 + 406 × 0.1231 = **371 µs/step = 4.5% of the
M4 step**; transferred to M5 that is **188–371 µs/step = 28–54% of the ~682 µs/step honest
decode pool** (§4.10a). Refund per *layer* eliminated:

| what a fusion removes | refund |
|---|---|
| a **dependent pair** (barrier + dispatch) | **56.8 µs/step** |
| a **barrier only** | **52.0 µs/step** |
| a **barrier-free dispatch** only | **4.8 µs/step** |

⇒ the selection criterion for every future fusion is **barriers removed, not dispatches
removed**. A candidate must bundle **≥3 barrier-removing fusions** to clear the ~80 µs/step
3σ decode floor, and additivity is **not** guaranteed (property 2 means each removal
shrinks what the next barrier can drain).

**⭐ Recommendation: kernel fusion.** Explicitly **not** ICB, **not** encode overlap,
**not** `start_concurrent()`, **not** graph reordering — all four are closed by this
result. Named first targets: **input RMSNorm → QKV GEMV** (`:5738-5745` currently declines
an *existing* fused kernel on the NVFP4 path) and **attention → o_proj**.

**Open caveat.** The 1.3003 µs barrier coefficient has **never been measured on M5**. It
is the single most load-bearing unmeasured constant in the programme and is an open
escalation to the human team.

### 4.17 ⭐⭐⭐ PR #284 — H5 is KILLED: the lm-head tier-0 read is irreducible, and the lm-head is retired as a decode target

Merged as `36b28fa5`. Deliverable `research/nezuko-pr284-result.md` (280 lines), head
`5a45215a`, host M4 Pro gen 16. Artifacts: `research/nezuko-pr284-byte-price.sh`,
`research/artifacts/nezuko-pr284-byte-price.tsv`,
`research/nezuko-pr284-slack-probe.patch`, `research/nezuko-pr284-slack-histogram.sh`,
`research/artifacts/nezuko-pr284-slack-hist.txt`,
`research/nezuko-pr284-slack-analyze.py`.

**VERDICT: no cheaper first screen in the certificate family can eliminate ANY of the
109,187,072 B tier-0 lm-head read. The best *sound* design saves 0.00 MB and 0.0 µs
against a 164 µs target and an 80 µs kill threshold.**

**Step 0 — the byte table** (decode, `useFusedRefinement: true`, V = 100,352, hidden 2,048).
Stage 5a reads `x` 4,096 + `codes_lo` 102,760,448 + `scales` 6,422,528 =
**109,187,072 B**, writes coarse f32 401,408 + delta bf16 200,704. 5b reads 401,408,
writes 896. 5c reads 4,096. 5d reads 602,112 unconditional + survivors×320 + refined×4,096,
writes 200,704. Arm-A lm-head total ≈ **110.99 MB/step**. (The advisor's brief said
109,182,976 B; it omitted the 4,096 B activation.)

**Measured marginal byte price** (3 reps × 3 arms interleaved, 9/9 `passed: True`):
A default 12,899.4 µs/tok (sd 57.0); B `DARKBLOOM_LMHEAD_FUSED_REFINEMENT=0` 13,042.8
(sd 39.2); C `DARKBLOOM_LM_HEAD_PRUNE=0` 14,112.0 (sd 24.0). **C−A paired = 1,212.6 µs
(sd 80.9) for +300.2 MB ⇒ 4.039 µs/MB ⇒ 247.6 GB/s effective on M4 Pro** — a new
programme anchor. B−A = 143.4 (sd 82.1) is **unusable** because it swaps kernel family.

**Step 0's own kill gate already fired.** 5a is 441.0 µs = **3.42%** of the M4 step and
252.2 µs = **6.09%** of the 4,143.6 µs M5 step @433 GB/s — under the brief's 8% bar. The
student continued anyway, correctly noting that **my brief's 8% kill threshold and its
+2.50% pricing were mutually inconsistent.** That is a real defect in the brief, not in
the work.

**⭐ Step 1 — the decisive measurement.** 5a emits a coarse `c_i` from the top 4 bits plus
a certified one-sided `delta_i`. On the refine path the nibble midpoint gives
`|q − q0| = 0.5` exactly, so `d_i = sd·Σ|x|` and `delta_i = d_i(1 + 32γ)` with γ = 2⁻¹⁵,
rounded **up** into bf16. Stage 5d keeps row *i* iff `c_i + delta_i >= thr`
(`LagunaLmHeadPrune.swift:670` pre-merge) ⇒ **the pruner is already a sound
branch-and-bound and `delta` IS the certificate radius.**

With `Q = ½·sd·Σ|x|`, today's `delta = B₁ = 2Q`; dropping *j* LSBs gives `B_j = Q·2ʲ`; a
sound *j*-bit tier-0 therefore requires **`R ≡ (thr − c₁)/delta > 1 + 2ʲ`**:

| tier-0 width | plane B/row | MB/step | requires |
|---|---|---|---|
| 5-bit | 1,344 | 134.87 | — |
| **4-bit (today)** | **1,088** | **109.19** | **R > 1** |
| 3-bit | 832 | 83.49 | R > 5 |
| 2-bit | 576 | 57.80 | R > 9 |
| 1-bit | 320 | 32.11 | R > 17 |

Bit-plane re-slicing keeps 1,280 + 64 = 1,344 B/row resident ⇒ no extra RAM cost. **R is
the entire experiment.**

**The R histogram over 129 real decode steps** (`DARKBLOOM_LMHEAD_SLACK_PROBE=1`, a
2,609 B instrument kept out of `Sources/`, dispatched between the `thr` dispatch and
`let assembled =`; run `c99c9a2b-f660-4c4c-a87d-35831f910122`, 72 s, exit 0,
**0 divergences**):

`R ≤ 1` mean 777.2 / median 288 / max 31,914 = 0.775% of vocab; `R ≤ 2` mean 86,057.6 =
85.756%; `R ≤ 3` 100,209.0 = 99.858%; **`R ≤ 5` = 100,352 = 100.000%**, identical through
`R ≤ 33`. **Not one row in 129 steps has R > 5.** The 31,914 outlier is the first step
after the seed.

**Pricing (M5 @ 433 GB/s; baseline 109.38 MB = 252.6 µs = 6.10% of the step):**
3-bit → +1 bit @ R≤5 → +1 bit @ R≤1 = **0.00 MB / +0.00%**; the 2-bit chain = 0.00; the
1-bit chain = 0.00; "2-bit side plane, re-read 4-bit @ R≤9" = **−51.38 MB but −118.7 µs
= −1.81% (WORSE, because the re-read costs more than the plane saves).** Even the
*unsound* optimistic bracket `R > 2^(j−1)` fails: 3-bit → 14,294 rows → 8.5 µs; 2-bit →
143 rows → 0.2 µs; 1-bit → 0 rows → 0.0 µs — all ≥10× under the 80 µs 3σ floor.

**⭐ This generalises: M1 (Cauchy–Schwarz), M2 (blocked Hölder) and M3 (two-tier plane)
ALL die too.** To drop 90% of rows, *any* cheaper tier-0 needs a bound below the 10th
percentile of `thr − c₁`, which the histogram places between **1× and 2× today's
delta**; halving the code width multiplies the bound by 4×. **The whole "coarser first
screen" family is off by roughly 10×.** The converse is equally important: today's screen
already leaves only **777 rows (0.78%)** on average, so hypothetical tiers 2–3 would cost
~0.6 µs ⇒ **beyond tier-0 the pruner is essentially optimal.** Any future attack must
**tighten `delta`, not coarsen the codes.**

**Byte recovery shipped (commit `61b064b1`).** Deleted `lagunaLmHeadRowMajorRefineEnabled`,
`lagunaLmHeadRowMajorRefinedExactKernel`
(`laguna_lmhead_exact_fused_int5_sparse_refine_rowmajor_v1`), its 33-line rationale and
the inner ternary arm: `LagunaLmHeadPrune.swift` **54,963 → 46,797 B (−8,166 B)**, budget
`current=2942689 headroom=57311 growth=−8166`. The flag was already default OFF and is a
twice-measured M5 negative (receipt `99b71258`: **+24.6 µs/token on M5** despite −63.7 µs
on M4). No default flipped; the only added lines collapse the call to the surviving
`lagunaLmHeadRefinedExactKernel` with identical args, grid, threadgroup, output shape and
dtype. `git grep` for the removed symbols in `Sources/`/`Vendor/` returns nothing.

**Correctness.** 9/9 `--local-iterate` arms `passed: True` on the post-deletion tree;
the probe run reported `0 divergences` over 128 steps. `run_upstream_equivalence.sh` was
**not** run — justified, because the change is pure dead-code deletion *and* the oracle
provably does not reach this file (below).

**⭐⭐ Independently re-confirms standing rule 16 (second confirmation, after #270 r2).**
`LagunaUpstreamEquivalence.compare` constructs `LagunaRuntimeModel(runtimeConfig)`
directly and **never** calls `prepareFusedRuntimeWeights()`, whose only caller is
`LagunaRuntimeWeights.swift:637` = `loadLibraryModel`, where the `lmHeadPruner` is built
(`LagunaRuntimeModel.swift:11016`, pruner `:11055`). ⇒ the oracle covers **neither the
lm-head pruner, nor fused-QKV, nor the shared-expert layouts**, and this statically
explains the ambiguous `research/frieren_pr35_lm_fault_oracle.sh` result. The real gates
are the 64-step drift tripwire, hidden teacher-forced / anchor / free-run token identity,
`correctnessLogitDiagnostics` top-8, and a pruner-on vs `DARKBLOOM_LM_HEAD_PRUNE=0`
argmax A/B.

**Consequences for the programme:**
1. **The lm-head is retired as a decode target.** §4.10b's line "the lm-head is the ONE
   place the byte total is not pinned" is **RETRACTED**.
2. **§11 H6's `lm_head int5→int4` (−26 MB, −47 µs, +0.72%) is now suspect**: the tier-0
   plane is *already* 4-bit at 1,088 B/row, and a genuine 3-bit plane needs `R > 5`, which
   never occurs. H6 must be re-derived against the byte table above before it is ever
   assigned.
3. Student's own follow-ups: (a) fix the equivalence-oracle gap by routing it through
   `loadLibraryModel`/`prepareFusedRuntimeWeights()`; (b) retire the lm-head; (c) if ever
   revisited, attack `delta`, not code width.

### 4.18 ⭐⭐⭐ PR #48 / PR #204 prior art — the RMSNorm→QKV fusion was already built and already ranked; its M5 negative is CONFOUNDED, not a refutation

Recovered 2026-08-07 by a full read of two abandoned `maple-fern` branches that predate the
current research state. **Two of §4.16's three named fusion targets had already been
implemented, and one had already consumed a ranked M5 slot.** Neither result had been
carried forward. This is why standing rule 18 now exists.

#### 4.18.1 The branches (fetch; do not delete)

| branch | tip | tag | mechanism | outcome |
|---|---|---|---|---|
| `maple-fern/fused-norm-qkv-gate` | `f4c86e44d40c305d850fb30092a0d62d0bbff606` | `pr/48` | input RMSNorm → QKV GEMV (+ per-head `g_proj`) = **§4.16 target C1 / TARGET C** | **ranked M5 NEGATIVE −0.1488%, stripped in r2** |
| `maple-fern/router-top8-fusion` | `e92d09ebb96084efce2b4bdb473e072b2043968f` | `pr/204` | router → top-8 emit-sink = **§4.16 target C3 / TARGET B** | reverted; ΔD = −0.9 ± 12.1 µs, **underpowered** |

The #48 fused kernel is preserved at commit `9c73e16f`; retrieve it with
`git checkout 9c73e16f -- Sources/MLXFastModel/LagunaRuntimeModel.swift`.
Deliverables on the #48 branch: `research/maple-fern-pr48-fused-norm-qkv-gate.md`
(1,214 lines), `research/maple-fern-pr48-submission-note.md` (228 lines),
`research/maple-fern-pr48-receipt.py`, `research/maple_fern_pr48_paired.py`,
`research/sweep_qkv_gate_fuse.sh`.

#### 4.18.2 What #48 actually shipped

Two env controls, both identity by default:

| control | env | values | default |
|---|---|---|---|
| `lagunaDecodeNVFP4QKVR1SIMDGroups` (`:4615`) | `DARKBLOOM_DECODE_NVFP4_QKV_R1_SIMDGROUPS` | 1, 2, 4, 8, 16 | **2** = stock |
| `lagunaDecodeNVFP4NormQKVFuseMode` (`:4727`) | `DARKBLOOM_DECODE_NVFP4_NORM_QKV_FUSE` | 0, 1, 2 | **0** |

- **mode 0** = stock per-layer chain `rmsbfloat16 → qkv (R1 NVFP4) → gate_sp` = **3
  dispatches per attention layer**.
- **mode 1** folds the input RMSNorm into the QKV kernel but still exports the
  device-visible `normalized` row.
- **mode 2** additionally folds per-head `g_proj` + softplus in as a **ride-along on
  `simd_group < 2`** (zero extra threadgroups); `normalized` is never materialised.
  **Mode 2 was the submitted arm** — reached by a one-character default flip at `:4727`
  (candidate commit `fa8618e`).

Fused-kernel structure: **one 512-thread threadgroup**; per-thread sum of squares over
`residual` (`values_per_thread = 16`) → `simd_sum` → cross-simdgroup tail via
`lagunaNormReductionTail2048` → `precise::rsqrt(acc/2048 + 1e-6)`; the normalized row is
staged into `threadgroup bfloat norm_row[2048]` (4 KB); `threadgroup_barrier`; then the
unchanged QKV body with `orow = tile*num_simdgroups + simd_group` and `input = norm_row`.
No scale-plane layout change anywhere — the deferred `× 4194304` row scale is untouched
and the QKV body MSL is emitted from the same string with only `orow`/`input` substituted.

An **earlier** mode-2 variant that gave the gate its own extra threadgroup measured
**+1.6% SLOWER** on M4: one threadgroup streams the whole 128 KB INT8 gate bank on a
single core while the other 640 retire, so the gate becomes the kernel tail.

Threadgroup counts collapse: h64 layers 5120 → **640**; h48 layers 4096 → **512**.

#### 4.18.3 ⭐ The MEASURED barrier census — independent confirmation of §4.16's counters

Instrumented with a throwaway `fprintf` in `maybeInsertBarrier()`
(`Vendor/mlx-swift/.../metal/device.cpp:362-375`); per-step figures are
`(count@120 − count@20)/100`. `device.cpp` is **not** editable; the instrument was
reverted before final verification.

| mode | barriers/step | no-barrier calls/step | dispatches/step |
|---|---:|---:|---:|
| 0 stock | **243** | 163 | **406.00** |
| 1 norm folded | **204** | 162 | **366.00** |
| 2 norm + gate folded | **203** | 123 | **326.00** |

**Decomposition: the norm fold removes 40 dispatches and 39 barriers; the gate fold
removes 40 dispatches and only 1 barrier — a 39:1 asymmetric split.** This independently
confirms §4.16's 406 dispatches/step to the integer. (#268 counted 247 barriers where #48
counts 243; #48 flags its census as a **lower bound** — `CommandEncoder::barrier()`
`:393-395` emits an uncounted barrier and `end_encoding()` serialises across encoder
boundaries with fences.)

**⭐ This is the origin of standing rule 19.** #48 §4.3: *"Deleting a producer does not
delete its consumer's barrier; it rotates it onto whatever the consumer now aliases. ΔB is
therefore not additive attribution."* Any §4.16 refund estimate built by counting removed
dispatches and assuming proportional barrier savings is wrong. **ΔB must be measured, not
predicted.**

#### 4.18.4 The local M4 numbers (all underpowered)

- *Geometry only* (`SIMDGROUPS=16`, fuse 0), N=16 vs stock, 12 × 512-step interleaved
  paired: mean Δ **−0.0193 ms = −0.225%**, sd(d) 0.0383, paired **t = −1.746 (n.s.**,
  t_crit 2.201); median Δ −0.122%, t = −2.900; min **+0.083%**. #48's conclusion:
  *"Widening the geometry 8× is timing-neutral on M4."*
- `decode_probe` 120 steps, single pass, medians: m0 8.555 / m1 8.452 / m2 8.484 ms ⇒ norm
  fold **−103 µs**, gate fold **+32 µs**. #48: *"n=1 per arm, unpaired; not evidence."*
- `--local-iterate` n=3, prefill-netted decode T: m0 **8.8453** (sd 0.1128), m1 **8.7167**
  (sd 0.0540), m2 **8.6897** (sd 0.0767) ⇒ m1−m0 = **−128.7 µs (−1.45%)**, Welch t ≈ 1.78;
  m2−m0 = **−155.6 µs (−1.76%)**, Welch t ≈ 1.98. **Neither is significant.**

#### 4.18.5 The ranked M5 receipt

Ticket **`285f79fa-089f-4184-b1ec-0647cb51e61b`**, created 2026-08-05T19:00:49Z, measured
19:12:03Z, `status rejected`, `officialScore 2.50450520378964`, commit
`3234ece1e2f2c43cf25bfa981f9c75a702564917`.

**Correctness fully green:** `passed_correctness True`, `max_abs_diff 0`,
`checked_steps 1344`, `case_count 11`, GPQA TTFT 9/9 (p50 0.07 s, max 2.3 s), semantic
GPQA 9/9, `peak_ram_gb 21`.

Timing: `decode_seconds_per_token 0.00505923275`,
`prefill_seconds_per_token 0.000190994708984375`; `nd` 2.745476 vs control 2.754322; `npf`
2.013145 (equal); **`ns` 2.540575 vs control `c3ce66ec` `ns` 2.544360 ⇒ Δ = −0.1488%.**
Both floors held but both components moved the wrong way (decode 2.7347 vs 2.7543;
prefill 1.9238 vs 1.9401).

Pre-registered readings: Reading A **+2.595%** (at `c = 2.1828 µs/dispatch`, tanjiro's
measured M5 per-dispatch cost), Reading B **+0.446%**, ~10.2σ apart. The receipt came in
*below* Reading B ⇒ **Reading A refuted outright.** #48's own stance: *"Consistent with a
wash plus session noise; I claim no real regression from a single paired receipt."*
Single-receipt resolution floor is **0.278%**, so −0.1488% is inside noise.

#### 4.18.6 ⚠️⚠️ WHY THIS DOES NOT FALSIFY §4.16 — the candidate bundled THREE changes

The submitted mode-2 arm simultaneously made:

- **(a)** −80 dispatches/step,
- **(b)** −40 barriers/step (with the 39:1 split above),
- **(c)** an **8× threadgroup-count collapse** (5120 → 640) because the fused kernel
  hard-codes 512 threads / 16 simdgroups, **plus ~24,320 redundant 2048-element
  sum-of-squares reductions per decode step** (640 per h64 layer, versus stock's single
  `rmsbfloat16` reduction), each with its own cross-simdgroup tail and threadgroup barrier.

**#48 never prices (c) and never lists it as a loss mechanism.** The decomposition is
ours, not the report's.

| quantity | value |
|---|---|
| §4.16 prediction, mode 2 on M4 | 40 × 1.3003 + 80 × 0.1231 = **61.8 µs/step** |
| §4.16 prediction, mode 1 on M4 | 39 × 1.3003 + 40 × 0.1231 = **55.6 µs/step** |
| §4.16 prediction, gate fold alone | 1 × 1.3003 + 40 × 0.1231 = **6.2 µs/step** |
| #48 measured M4 (`--local-iterate`, n=3) | m2 − m0 = **−155.6 µs/step** (~1.6σ, underpowered) |
| #48 measured M5 (ranked) | −0.1488% ÷ 14.862 %/ms ⇒ **+10.0 µs/step SLOWER** ⇒ effective **−0.125 µs per removed dispatch**, **−0.25 µs per removed pair** |
| **implied M4 → M5 swing** | **≈ 165 µs/step** |

If §4.16's ~62 µs refund transfers to M5 at even half strength (~31 µs), then (c) must
cost about **+41 µs/step on M5** and *both* results are consistent. #48 predicted exactly
this sign-flip risk and never separated it: *"640 threadgroups retire in ~16 waves on 40
cores versus ~32 on 20. A trailing 2-threadgroup dispatch has less shadow to hide in on
the larger part… the sign of the gate fold can differ between M4 and M5."*

#### 4.18.7 ⭐ NEW STRUCTURAL LAW — bit-exact RMSNorm fusion is INTRINSICALLY a geometry change

A bit-exact fold must reproduce MLX's `rmsbfloat16` reduction **tree shape** (512 threads
× `n_reads = 4`). #48 satisfied that by hard-coding 512 threads / 16 simdgroups — which is
*precisely why* the threadgroup count collapses 8×. **§4.16 target C1 cannot be built as a
pure barrier-removal in the way #48 built it.**

**Escape hatch (never built):** tree *shape*, not thread *count*, determines the
floating-point result. A 64-thread threadgroup can **serialise** the same 512-lane
reduction tree at higher ALU cost while preserving the stock 2-simdgroup geometry. This is
the geometry-neutral fusion that the deconfound assignment should design if the barrier
refund is confirmed.

#### 4.18.8 Bit-exactness — CLAIM WITHDRAWN by #48 itself (third confirmation of standing rule 16)

*"The equivalence oracle never executed this kernel and never passed on this host (§9.4),
and the defensible correctness claim is 'no gross always-on corruption', not
'bit-exact'."*

- §9.4: the fused path is structurally unreachable in `LagunaUpstreamEquivalence`
  (`_nativeAffineQKV == nil` there); **82 × `EQUIVALENCE_EXIT=1`, zero passes**; the 0.125
  prefill max-abs-logit error is pre-existing on the unchanged base ⇒ the oracle is
  **doubly uninformative**.
- §9.5(c): under an injected `+1.0f` fault, `max_abs_diff` stayed **0** while
  `passed_correctness` went false ⇒ **`max_abs_diff` is not an independent residual signal
  on this path.**
- §9.7: the argmax gate is **blind below 1e-3**. It cannot see permutation- or
  statistics-preserving errors, races, missing barriers, occupancy or compiler effects,
  uninitialised threadgroup memory, *"or any QKV-phase bug — the QKV side was never
  injected at all."*

#### 4.18.9 Other mechanisms #48 named

- *"Concurrent dispatches still consume scheduler slots. Counts ≠ time."*
- Permission-to-overlap ≠ overlap (a claim #48 withdrew).
- Surviving benefit attribution is *"reduced CPU encode work and per-dispatch launch
  overhead"*, **not** recovered GPU-timeline time.
- Knee model `dT(n) = max(0, n·c − slack)` ⇒ 406 dispatches may sit below saturation, in
  which case removing 80 pays nothing.
- Cost constants: `c = 2.1828 µs/dispatch` (M5, tanjiro); bracket `[0.36, 2.09] µs` (2.09
  chained injected empties, 0.36 concurrent floor); **1 ms decode T = 14.862% of score**;
  price ladder — concurrent floor 28.8 µs (+0.428%), advisor floor 31.8 µs (+0.473%),
  barrier-weighted 98.0 µs (+1.456%), chained 167.2 µs (+2.485%), advisor central
  201.1 µs (+2.988%); promotion bar +1.461% at P = 50%.
- Local-vs-model gap: the norm fold beat its 34.8 µs prediction by 3×, while the gate fold
  moved the wrong way against a −212.8 µs prediction = a **~245 µs discrepancy**.

#### 4.18.10 §10 surviving follow-ups — the family is NOT declared dead

1. Per-dispatch barrier tagging in `maybeInsertBarrier` — #48 calls this *"the
   highest-value item here"*. (Now #268 r2 task 2.1.)
2. A Metal System Trace on one decode step — *"the only way to see the CPU-encode half"*.
   (Escalate to the human team; needs an M5 dev host.)
3. Barrier-class triage for `oproj_act_h64` (0.601) and `residual_rms_router` (0.605).
4. **"The `gate_sp` kernel itself, rather than its dispatch… It is latency-bound, and
   widening *it* may be a different and larger prize than deleting it."** — unexplored.
5. **Mode 1 as its own ranked arm** — one character, never ranked.
6. Reconcile the ×0.812 residual-class factor against M5.

The submission note adds: if the arm is not returned, *"effort should move to memory
traffic and to the routed expert gather-GEMM instead."*

#### 4.18.11 ✅ VERIFIED: the §10.4 instrument hazard is NOT on our line

#48 §10.4 warns of a hardware-constant instrument (`INJECT_DECODE_EMPTY` /
`INJECT_EMPTY_TG`) left inside `Sources/`, worth −3.24% of score if shipped. Checked on
the current advisor HEAD:

- `git grep -n 'INJECT_DECODE_EMPTY|INJECT_EMPTY_TG|injectDecodeEmpty|injectEmptyTG'` over
  `Sources/` and `Vendor/mlx-swift-lm/` = **zero hits**.
- `5a72af3` and `5178d452` are **NOT ancestors of HEAD** (`git merge-base --is-ancestor`
  returns not-ancestor for both).
- The instrument existed at `5a72af3:Sources/MLXFastModel/LagunaRuntimeModel.swift:11046`
  and was removed by commit `a41d8064` ("Remove M5 hardware-constant instrument … to
  recover 12KB file budget").

**The current frontier is clean.** This is nonetheless the concrete near-miss that
justifies standing rule 11 (instruments stay out of `Sources/`).

#### 4.18.12 r2 strip

Per #48 §10.1 the file was restored to the advisor-base blob: `growth=0`,
`current=2941155`, editable diff versus base empty.

#### 4.18.13 Consequences for the programme

1. **§4.16 target C1 is CONFOUNDED, not refuted.** The open question is the barrier refund
   *at fixed geometry* — `(mode 1 @ SIMDGROUPS=16) − (mode 0 @ SIMDGROUPS=16)`, against a
   §4.16 prediction of 55.6 µs/step. That contrast has never been run.
2. **§4.16 target C3 is PR #204's underpowered arm**, not a fresh idea.
3. **The gate fold is the sharpest barrier-vs-dispatch discriminator in the programme** —
   40 dispatches for 1 barrier ⇒ §4.16 predicts only 6.2 µs/step. It is below M4
   resolution, so it can bound but not measure the dispatch coefficient.
4. **Standing rules 18 and 19 are added** as a direct result of this recovery.

### 4.19 ⭐⭐⭐ PR #268 r2 (merged) — the authoritative per-site barrier census

`research/maple-fern-decode-barrier-site-census.md` (518 lines) plus the 922-line r1 report,
`research/fern_tax_*`, and `research/artifacts/fern_sites*`. This supersedes every earlier
guess about *where* the tax in §4.16 is charged.

**Headline: `barrier ∧ cb = 0` in both memory profiles.** A charged barrier is never also a
command-buffer switch, so the two costs are additive and separately attributable.

| per decode step | low-memory (student M4) | **ranked / full (M5)** |
|---|---|---|
| dispatches | 406 | 406 |
| command-buffer switches | 44 | 29 |
| **charged barriers** | **247** | **258** |
| total fences | 291 | 287 |
| sparse fences per layer | 7.103 | **7.000** |
| command buffers | 45 | 30 |

Region split — 39 sparse layers: 390 dispatches, 238 barriers (low) / 248 (ranked). Dense
layer 0: 8 dispatches / 5 barriers (low) / 6 (ranked). lm-head tail: 7 / 4 / 4.
PR #48's contemporaneous count of 243 is **never reconciled** with either profile; that gap
is still open and is a reason to distrust any barrier arithmetic quoted from #48 alone.

**The sparse-layer chain is exactly 7 edges over 10 dispatches, with 3 off-chain free
riders.** Per-edge charges across the 39 sparse layers (low / ranked):
E1 31/33 · **E2 39/39** · E3 24/39 · E4 39/39 · **E5 27/39** · E6 39/39 · E7 39/20 —
totals 238/248.

Dense layer 0 site trace:
`inputNorm[.] gate_softplus[BAR] qkv(h48)[.] attn(full)[.] o_proj[BAR] postNorm[BAR]
dense_gate_up[BAR] dense_down[BAR]`.
lm-head tail: `inputNorm[.] 5a-coarse[BAR] 5b-argmax1[BAR] 5c-winner[BAR] 5d-refine[.]
gather[.] argmax[BAR]`.

⭐ **Naïve 39 × 12 = 468 barriers; measured 238–248 ⇒ MLX already refunds ~48%.** Price every
fusion candidate against 238–248, never against 468. This single correction has killed more
optimistic estimates in this programme than any other number.

⭐ **`MLX_MAX_OPS_PER_BUFFER` and `MLX_MAX_MB_PER_BUFFER` are INERT** —
`RuntimeStartupMemoryPolicy.swift:170-183` force-sets them with `setenv(..., 1)`.

**C1–C6 refund table** (ranked rates; ⚠️ superseded by §4.22 for ON-CHAIN edges only):

| # | candidate | edge | Δbar | Δdisp | µs/step | score | risk |
|---|---|---|---|---|---|---|---|
| **C1a** | `inputNorm` → QKV fused, still writes `normalized` | E2 | −39 | −39 | 55.5 | 0.85–0.9% | low |
| **C1b** | + `gate_softplus` | E2 | −39 | −78 | 60.3 | 0.92% | low-med |
| C2 | `attn` into `o_proj` | E4 | −39 | −39 | 55.5 | 0.85% | high |
| C2′ | `o_proj` into `postNorm+router` | E5 | −39 | −39 | 55.5 | 0.85% | ⛔ BLOCKED |
| C3 | `router_top8` into `postNorm+router` | off-chain | 0 | −39 | 4.8 | 0.07% | low |
| C4 | `shared_swiglu` merged into `routed_swiglu` | off-chain | 0 | −39 | 4.8 | 0.07% | med |
| C5 | `shared_swiglu` into `postNorm+router` | off-chain | 0 | −39 | 4.8 | 0.07% | med |
| C6 | collapse the whole lm-head cascade | tail | −4 | −6 | 5.9 | 0.09% | med |

Ceilings: removing *all* barriers = 321 (low) – 336 (ranked) µs/step; the realistic 7→4-edge
collapse = −152 µs/step.

**Caveats that travel with this census.** Every constant is M4-only. The census reads the
last complete 406-dispatch window of a 3-step run. The `device.cpp` trace patch changes the
vendored-Metal fingerprint, so a patched build **cannot run the trusted harness**. And
`LagunaUpstreamEquivalence.swift:74-90` bypasses the weight cache and never reaches
`prepareFusedRuntimeWeights()` (`:11016`) — the origin of standing rule 16.

### 4.20 ⭐⭐ PR #288 (merged) — the editable byte budget is a managed resource

Comment relocation into non-submitted `notes/*.md` recovered **−76,269 B** across seven files:
`LagunaRuntimeWeights.swift` −2,037 · `LagunaConfig.swift` −308 ·
`MLXLMCommon/KVCache.swift` −12,698 · `MLXLMCommon/Evaluate.swift` −26,993 ·
`Transform.swift` −2,228 · `AffineMetadataCoding.swift` −16,378 (deleted) ·
`TiedHeadMetadataCoding.swift` −15,627 (deleted). `LagunaRuntimeModel.swift` was left
byte-identical.

Gates: scope OK; `research/frieren_comment_strip_check.sh` PASS; code residue `cmp`-identical
on all four edited-in-place files; Transform tests 36/36; `run_upstream_equivalence.sh`
non-vacuous.

⚠️ **Two accepted deviations, both now discharged onto #311:** the build used a bare
`swift build -c release` rather than `--local-iterate`, and **the 64-step drift tripwire was
not run**.

**Method worth reusing.** Relocate under a `## \`symbol\`` heading with
`_relocated from lines A-B at base <sha>_`. **Keep** any line stating a rule the code must
obey, a flag contract, a byte layout, or a numeric derivation; preserve `///` abstracts,
invariants, ordering/aliasing/lifetime constraints, wire-format pins, "must match the Metal
kernel" pins, upstream-deviation markers, `MARK:` separators, and copyright. Gotcha: a bare
`//` pointer inside a `///` run detaches the abstract. Tooling:
`research/frieren_relocate_comments.py`; checker `research/frieren_comment_strip_check.sh`
(phase 1 asserts zero comment-looking lines inside `"""` on base *and* head; phase 2
normalises both sides identically then `cmp`s). The checker self-documents as "necessary but
NOT sufficient" — believe it.

### 4.21 ⭐⭐ Frontier strategic reframe — overhead is ~2× heavier on the ranked box

The same absolute microsecond of schedule overhead is worth twice as much on M5 as on the
student M4, because the M5 step is 4.14 ms against the student's ~8.18–8.20 ms.
258 × 1.30 + 406 × 0.12 ≈ **384 µs ≈ 9.3% of the ranked step.**

Excluding bubbles, the streaming portion of decode already runs at ≈**479 GB/s**, and the
per-kernel plateau is ~500–535 GB/s against a ~614 GB/s peak — so the kernels are already at
**82–90% of achievable peak**. The realistic *schedule-only* ceiling is therefore
4.14 → ~3.4–3.6 ms; there is no large arithmetic win hiding inside the kernels.

**Forbidden because they are not bit-exact:** quantizing lm_head or the router; FP16/BF16
accumulation; fast-math `exp`/`rsqrt`/SiLU; vocab pruning or early-exit argmax; reduced-precision KV.

MoE gather is **not** a DRAM problem; the real pathologies are launch-structural. Metal
cross-threadgroup options, in order of safety: threadgroup-count collapse (only viable for
streams under ~100 KB); device atomics with a "last threadgroup finalizes" pattern
(deterministic if partials are re-read in fixed index order); **no grid sync and no
forward-progress guarantee, so spin barriers are unsafe**; a persistent-threadgroup
megakernel remains "Plan C".

### 4.22 ⭐⭐⭐ PR #298 (merged) — the deconfound, and the major result of the campaign

`research/maple-nezuko-pr48-deconfound.md` (387 lines) plus `nezuko_pr48_abba.sh`,
`nezuko_pr48_deconfound.patch`, `nezuko_pr48_stats.py`, and 48 runs under
`research/pr48-deconfound-logs/`.

PR #48 changed **two** things at once. #298 separated them into orthogonal knobs:
`DARKBLOOM_DECODE_NVFP4_QKV_R1_SIMDGROUPS ∈ {2, 16}` (default 2) and
`DARKBLOOM_DECODE_NVFP4_NORM_QKV_FUSE ∈ {0, 1, 3}` (default 0). Arms:
`0` (2 sg, fuse 0, 5120 TG) · `RV` (2,3) · `V` (2,1) · `G` (16,0, 640 TG) · `R` (16,3) ·
`N` (16,1 — PR #48 reproduced).

48 runs, 4 palindromic blocks, 8 runs/arm, 192 steps/run; **se = 13.6 µs**, 39 df.
Means µs/step: `0` 8179.9 · `RV` 8488.2 · `V` 8399.5 · `G` 8144.5 · `R` 8224.8 · `N` 8124.9.

| contrast | µs/step | t | 95% CI |
|---|---|---|---|
| `G − 0` | **−35.4** | −2.61 | [−62.8, −8.0] |
| `R − G` | +80.4 | 5.93 | [+53.0, +107.7] |
| `RV − 0` | +308.3 | 22.75 | [+280.9, +335.7] |
| `V − RV` | −88.6 | −6.54 | [−116.0, −61.2] |
| `N − R` | −100.0 | −7.38 | [−127.3, −72.6] |
| `N − G` | −19.6 | −1.45 | NULL |
| `V − 0` | +219.6 | 16.21 | [+192.3, +247.0] |
| `N − 0` | **−55.0** | −4.06 | [−82.4, −27.6] |

**Four findings.**
1. The dispatch/barrier refund is **real**, at −2.2 to −2.5 µs per removed **on-chain**
   dispatch. `N − 0 = −55.0` reproduces §4.16's prediction of −55.6 almost exactly.
2. **The "threadgroup-geometry cost" is FALSIFIED — it is a WIN.** Collapsing 5120 TGs to
   640 (`G − 0`) buys −35.4 µs/step and is bit-exact by algebra. This is the origin of #308.
3. **Consumer-side redundant reduction is not free** and scales sub-linearly with
   threadgroup count (exponent ≈ 0.64): +308.3 µs/step at 5120 TG, +80.4 at 640.
4. **The norm fold itself is worth nothing at fixed geometry** (`N − G` is null). Everything
   PR #48 gained came from the geometry change it happened to carry.

**§9 design sketch, as adjudicated.** **A** — a persistent grid-stride lane-major QKV kernel
at a fixed small threadgroup count `T` with fuse mode 1: bit-exact, best of the set, and now
assigned as #309. At T=128 × 16 sg = 2048 simdgroups ⇒ 5 rows/sg for h64, 4 for h48, exact
with no tail. Precedent already in tree at `lagunaResidualRMSNormRouter` (`:853`, `:1055`,
`:10542`). **B** spin barrier — rejected (no forward-progress guarantee). **C1** not
bit-exact. **C2** dominated. **D** cross-threadgroup FP atomics — not bit-exact.

**Accepted deviations.** The static kill-gate argument rests on `device.cpp:315-375`. Prefill
is unreachable from these knobs (`:4960`, `:4970-4971`, `:5922`). **The headline caveat is
M4→M5 sign-flip risk:** the ranked M5 measured PR #48's arm `N` at **−0.1488% = +10.0 µs/step
SLOWER**, the opposite sign from M4. Neither `G` nor `N` clears the ~80 µs 3σ ranked floor on
its own. Correctness: 49/49 runs, 0 divergences over 192 teacher-forced steps.

**Reproduction.** `git apply research/nezuko_pr48_deconfound.patch`;
`CLANG_MODULE_CACHE_PATH="${PWD}/.build-worker/clang-module-cache" swift build -c release
--force-resolved-versions --scratch-path .build-worker --product mlxfast-runtime-worker`;
`git checkout -- Package.resolved`; `./research/nezuko_pr48_abba.sh /tmp/nez298/abba 4 200`;
`python3 research/nezuko_pr48_stats.py /tmp/nez298/abba [--trim 0.05]`. ≈41.5 s/run. The
patch takes `LagunaRuntimeModel.swift` from 468,336 → 475,865 B (growth 7,529).

### 4.23 ⭐⭐⭐ PR #300 (merged) — the redundant-RMSNorm tree, and two corrections that outlive it

`research/maple-fern-redundant-rmsnorm.md` (465 lines) plus
`fern_redundant_rmsnorm_bitwise.swift`, `fern_redundant_rmsnorm_cost.swift`,
`fern_rmsnorm_cost_wandb.py`, `fern_hidden_dump.patch`, `research/redundant-rmsnorm-logs/*`.
Submitted-surface diff EMPTY. W&B `s97y6fdp` (earlier, noisier: `tjo00rhf`).

**Stage 1 — H1 SUPPORTED.** A 64-thread virtualized reduction tree and the 512-thread tree
agree bitwise: 1600 rows, **0 mismatches, 0 ULP**. The fault-injection arm produced
1002/1600 mismatches, and the harness hard-fails if the fault arm *cannot* mismatch
(`:427-433`) — this is the template every future bit-exactness claim should copy.

Reference tree: `laguna_residual_rms_bf16_2048_v1` at `:1015-1057`; shared tail
`lagunaNormReductionTail` `:763-792`. The real fused `[Q;K;V;G]` bank is **10,304 rows
sliding / 8,240 rows full**, so the collapse is **4×, not 8×**.

⭐⭐ **CORRECTION 1 — the 64-thread virtualized tree is BUILT by default but NEVER
DISPATCHED.** `lagunaNativeAffineNVFP4From` (`:2861-2867`) returns 0;
`lagunaNativeAffineWeight` (`:2914-2925`) quantizes every layer with
`groupSize:16, bits:4, mode:.nvfp4`; the fused-dispatch guard `:5739-5741` requires
`.affine / 8 / 32` and is therefore **never satisfiable**. The kernel that actually runs is
`lagunaDecodeNVFP4QKVR1` (`:4815-4881`). **Standing rule 1 is amended because of this:
quoting a build-time guard is not reachability — quote the DISPATCH guard chain down to a
default value.**

**Stage 2 cost — the isolated arm is kept, the in-situ proxy is rejected.** Isolated:
sliding 1288 TG 4.320 ± 0.022 µs · sliding 5152 TG 15.163 ± 0.258 · full 1030 TG
3.593 ± 0.025 · full 4120 TG 12.197 ± 0.272. Per step, the tree already costs
**165.522 ± 0.704 µs**; at 2 rows/TG it would cost **+411.335 ± 8.244 µs** more. The in-situ
proxy measured **−0.182 ± 0.845 µs/dispatch** and the harness returned verdict `KILL`; I
declined to override it.

⭐⭐ **CORRECTION 2 — reconciliation with §4.22.** At ~5120 TGs fern's *isolated* cost is
15.163 µs/dispatch while #298's *real-kernel in-situ* cost is **7.71** ⇒ **49% of the
isolated cost is hidden when the kernel runs in place.** This is the origin of standing
rule 25: a stripped-down "in-situ proxy" kernel is not in situ.

**Product:** the whole `lagunaNormAffineQKV` INT8 family (`:4880-5400`) is confirmed
dead-by-default and **CLOSED**.

### 4.24 ⭐⭐⭐ Round-34 recon — the decode fused-attention family is CLOSED, and the roofline percentages for it were wrong

Two `explore` recon passes (`attn-audit`, `byte-pool`) plus advisor arithmetic. Net effect:
one large apparent pool is deleted, and one measurement convention is corrected.

**Geometry (all in `LagunaRuntimeModel.swift`).** Sliding
`laguna_sliding_fused_attn_ring_v1`: gate `lagunaFusedSlidingAttentionEnabled`
(`DARKBLOOM_FUSED_SLIDING_ATTN`) `:1365-1367`; kernel `:1369-1370`; body ≈`:1378-1662`;
macros `LAGUNA_RESCALE` / `T_LOAD_K` / `T_LOAD_V` `:1647-1691`; wrapper `:1719-1765`;
dispatch `:1744-1746` = `grid ((heads/2)*1024,1,1)`, `threadGroup (1024,1,1)` ⇒ 64 heads ⇒
**32 TGs × 32 simdgroups**. Full `laguna_full_fused_attn_grow_v1`: declared `:1801-1802`,
body ≈`:1827-2163`, params `[writeIdx, writeIdx+1, capacity]` `:2201-2220`, wrapper
`:2226-2271`, identical dispatch shape `:2268-2269` ⇒ 48 heads ⇒ **24 TGs**.
Sliding constants `:1379-1388`: `head_dim=128, window=512, gqa=8, BN=32, BD=32, BDP=33,
qk_per_thread=4, v_per_thread=4, rotary_pairs=64, constexpr int N=512`. Full `:1810-1831`:
`gqa=6, rotary_pairs=32, yarn_mscale=1.3465735912322998f`, **`N = int(params[1])` runtime**,
`capacity = params[2]` runtime.
Two query heads per TG share one staged K/V row. In the prologue `sg<3` does Q0/Q1/K
RMSNorm+RoPE and `sg==3` stages V, leaving **simdgroups 4–31 idle** until a single
`threadgroup_barrier` (sliding ≈`:1449`, full ≈`:1978`). The KV loop
`int i = sg; for (; i+BN < N; i += 2*BN)` is a 32-way intra-TG flash-decoding split with a
2-deep software pipeline and **no barrier inside the loop**.
`staticThreadgroupMemoryLength = 18432 B`; `maxTotalThreadsPerThreadgroup = 1024`. The
epilogue does an `outputs4[BN*BDP]` float4 transpose merge with 3 barriers, 2 `simd_max`, and
12 `simd_sum`.

⭐⭐⭐ **The roofline percentages for these two kernels are INVALID.** Sliding KV bytes are
8 × 512 × 128 × 2 × 2 = **2,097,152 B** ✓ (plus 2,118,656 B including raw_queries 16,384,
raw_keys 2,048, raw_values 2,048, query_weight 256, key_weight 256, angles 512; **no mask
tensor is read**). Full KV is 2.359 MB ⇔ **N = 576** ✓. But **GQA replication means each KV
row is issued 4× (sliding) / 3× (full)**: 8.389 MB/call = 406 GB/s = **149% of M4 peak**;
full 7.078 MB = 284 GB/s = 104%. Those reads are therefore **cache-served**, so the
"37.1% / 34.7% of DRAM peak" rows in the a2 census are ratios against a denominator these
kernels never touch. ⇒ **standing rule 26: a cache-served read has no roofline headroom.**

**What actually limits them.** They are issue/latency-bound. Lone-TG vs co-resident ratio
7.408 / 8.891 = 83.3%. The k-loop runs at **≈90% of its issue-rate floor** (0.749 µs/iter
≈ 1054 cycles against a ~880–960 floor), with **~84 of ~104 FP slot-equivalents pinned by
bit-exactness**. Fixed per-call cost is ~27%: launch ≤1.7 µs (8.2%), **cross-simdgroup
epilogue 3.91 µs (18.8%, constant in N)**, main loop 15.2 µs (73%); the loop fits
1.915 µs/iter + 5.77 µs intercept, R² = 0.9925. The idle simdgroups 4–31 are an intercept
term, not a slope term. These kernels are **not** threadgroup-memory-limited (60 co-resident
TGs at 1024 threads for tgmem 16 B and 18,432 B alike). Widening the epilogue is
**hardware-blocked**: 8 float4 planes would need 33,792 B > the 32,768 B limit.

**Prior art — every variant is already closed.** PR #196 / T1
(`research/nezuko-decode-attention-occupancy.md`, base `3b75a115`, runs
`dc05d40d-16a4-4210-a1d5-9b8abda83518`, `935bcdcb-…`) fitted the staircase
`T(K) = a + b·⌈K/C⌉` with a = 1.661, b = 7.408, **C = 40** ⇒ both 32 and 24 TGs are a
**single wave on the ranked M5, so the idle slots cost literally zero**. PR #103 was NO-GO on
every variant: 1-head/TG is bitwise identical but **+20.1% slower**; pipeline depth 4 =
−1.039%, depth 8 = +0.485%; and end-to-end noise on a byte-identical `Sources/` is +0.73%.
PR #56 (byte floor fictional) and PR #68 (merged `d08ddd7b`, **−0.35%, i.e. slower**) close
the rest. ⚠️ **PR #205 already cashed the #196 §7.1 successor**:
`research/nezuko-attention-merge-epilogue.md`, merged at `3ffc371d`, commit `1aad492f` —
bit-exact (max_abs_diff 0 over 1344 steps), M4 ABBA sliding +0.400 µs/call (+2.51%), full
+0.202 (+1.11%), in-situ **+18.58 ± 2.92 µs/step, t = 6.37, 12/12 pairs positive**; receipts
`c03dc117`, `df9613a8`. **Nothing has touched either kernel body since.** Burned branches:
`birch-thorfinn/attn-epilogue-1pass`, `…-v2`, `attn-pair-o-float4`, `attn-tg-shrink`,
`birch-askeladd/attn-output-float4-v1`, `birch-alphonse/fused-pairab-softmax-v1`,
`maple-fern/attn-reduction-packing` (`4e8b1da8`),
`maple-fern/gqa-kv-group-cooperative-attention`.

**Reconciliation with the PR73 census.** The "−0.084 ms attention excess"
(`maple-tanjiro-pr73-decode-kernel-census.md:35-42`, `:496-503`) covers only the
**projection** block, which is at **107% of its own floor** ⇒ no headroom. The two fused
kernels live in the **remainder** block (`:523-541`): sliding excess 341.9 µs (5.08%), full
145.6 µs (2.16%), sum **487.5 µs M5-equivalent (7.24%)** — the *same quantity* as the M4
"564 µs / 8.26%" (host factor 0.7565). The census disclaims it at `:594-606` and §8.1
`:616-637` already marks it **CLOSED**.

⭐⭐ **H7 is arithmetically dead.** §11.7 proposed skipping the softmax rescale when the max
is unchanged, priced at 60–95 µs. At `LagunaRuntimeModel.swift:1517-1553` the
rescale-consuming code per head per KV slot is
`pair_sum0 = pair_sum0 * pair_factor0 + pair_exp0;` and
`pair_o0[p] = pair_o0[p] * pair_factor0 + pair_exp0 * pipe_va{p};` for p = 0..3 ⇒ **9 ops**.
Skipping when `pair_factor0 == 1.0f` gives a **contracted** `fma(e, v, o)` = 5 ops but rounds
**once instead of twice** ⇒ not bit-exact; the **bit-exact** form is mul + add per lane =
**9 ops, zero saving**, because FADD and FFMA occupy the same slot on Apple GPUs. ⇒
**standing rule 28**, and H7 is recorded as CLOSED-except-specialisation. Only the "20–40 µs
from specialisation" sub-lever survives, and only for the FULL kernel (10 calls/step) where
`N` and `capacity` are runtime values; the sliding kernel already has `constexpr int N = 512`.
The `exp` half of H7 already shipped in `LAGUNA_RESCALE` (`:1647-1658`).

**On-chain fusion space is exhausted.** The sparse chain has 7 edges over 10 dispatches:
`down+residual(prev) —E1→ inputNorm —E2→ qkv —E3→ attn —E4→ o_proj —E5→ postNorm+router
—E6→ shared_swiglu —E7→ down+residual`. **E2** is #309's target. **E1** is #298 §9 option D
(cross-TG FP atomics, not bit-exact). **E3** is 5120×64 vs 32×1024 — incompatible.
**E4/E5** are C2′ — BLOCKED. **E6** is router 32 TGs × 512 threads vs shared 256 TGs × 64 —
blocked. ⇒ only E2 survives.

⭐ **Corrected off-chain dispatch pricing.** #298's "−2.2 to −2.5 µs per removed dispatch" is
really "per removed **(dispatch + barrier) pair on the SERIAL CHAIN**". Off-chain removals
(C3/C4/C5, Δbar = 0) stay at ~0.12 µs × 1.8 ≈ **8.6 µs per 39 dispatches, NOT 86–98 µs**;
PR #204's null (ΔD = −0.9 ± 12.1 µs) is entirely consistent with that. **There is no
C3/C4/C5 re-pricing bonanza.** ⇒ standing rule 27.

**Vendor byte pool (recon B).** `editablePaths` has 97 entries but **4 are directories**
(`Sources/MLXFastModel`, `Sources/MLXFastTransform`, `.../kernels/steel/gemm`,
`.../kernels/steel/attn`), expanding to **140 files = exactly 2,868,051 B**. Fifteen
`Vendor/mlx-swift-lm/` entries total **297,394 B**; only 14 are in `MLXLMCommon/`
(`Laguna.swift` is under `MLXLLM/Models/`). Sizes: KVCache 68,533 · Evaluate 48,319 ·
BatchKVCache 43,383 · SwitchLayers 25,688 · Laguna 23,040 · CompiledDecode 16,147 ·
RoPEUtils 13,352 · CompilableKVCache 12,043 · CompilableRotatingKVCache 11,445 ·
LanguageModel 9,909 · BaseConfiguration 8,535 · AttentionUtils 6,691 · JSONDecodingTypes
4,657 · DynamicSlice 2,860 · RoPEApplication 2,792. There are **zero `/* */` block comments
anywhere**. Estimated recoverable bytes (class A = unreachable and flag-free, keep 5%;
B = unreachable with live flag contracts, keep 25%; C = scored path, keep 55%; Cf = scored
plus flags, keep 62%; X = exhausted): BatchKVCache **9,644** (B) ·
CompilableRotatingKVCache **5,838** (A) · CompiledDecode **4,753** (B) · CompilableKVCache
**4,599** (A) · BaseConfiguration **3,131** (A) · SwitchLayers 2,367 (Cf, hazard) ·
LanguageModel 2,285 (C) · Laguna 1,857 (A) · AttentionUtils 1,655 (C) · DynamicSlice 1,179
(A) · RoPEUtils 832 (C) · RoPEApplication 829 (C) · KVCache 500 (X) · JSONDecodingTypes 414
(C) · Evaluate 0 (X) — **total ≈ 39,883 B**. Scored-runtime reachability: scored =
SwitchLayers (39 refs), KVCache (23), RoPEApplication (8), RoPEUtils (3), LanguageModel (3),
AttentionUtils (2), JSONDecodingTypes (2); not scored = Evaluate, Laguna.swift,
CompiledDecode, BatchKVCache, CompilableKVCache, CompilableRotatingKVCache,
BaseConfiguration, DynamicSlice. All 15 are compiled; none is deletable.
⚠️ **`SwitchLayers.swift` is a trap**: five `MLXFast.metalKernel` `"""` sources (L108/111,
134/149, 157/179, 187/203, 255/315, ≈5,303 B) contain ≈1,115 B of `//` lines that are Metal
**compile input**, so `frieren_comment_strip_check.sh` would report a **false PASS**. It is
excluded from #311.

### 4.25 ⭐⭐ PR #311 (merged) — vendor byte recovery, and the campaign's reference equivalence procedure

maple-fern, merged 2026-08-07 18:18 UTC onto `63ab67c8` → base `5c491cf0`.
Submitted-surface diff is **5 files, +13 / −336 lines, −18,274 B**, all in
`Vendor/mlx-swift-lm/Libraries/MLXLMCommon/`:

| file | base B | head B | delta |
|---|---:|---:|---:|
| `BatchKVCache.swift` | 43,383 | 37,146 | **−6,237** |
| `CompiledDecode.swift` | 16,147 | 11,686 | **−4,461** |
| `CompilableRotatingKVCache.swift` | 11,445 | 8,418 | **−3,027** |
| `CompilableKVCache.swift` | 12,043 | 9,170 | **−2,873** |
| `BaseConfiguration.swift` | 8,535 | 6,859 | **−1,676** |
| **total** | 91,553 | 73,279 | **−18,274** |

22,571 B of prose moved into `notes/*.md`, which is **not** in `editablePaths`.
Recovery was 65.3% of the 27,965 B estimate; the shortfall is the abstract-keep
layer (≈14.3 KB = 39.5% of the 36,164 B pool) plus 922 B of returning pointers.

**Two student corrections to the advisor brief, both accepted.** (i) The three
`CompiledDecode` hits inside `LagunaRuntimeModel.swift` (`:5366`, `:5388`,
`:6272`) are all `MLXHardwareInfo.isCompiledDecodeSupported` — a *substring*,
not a reference; `grep -cw` over all nine file-scope symbols returns 0. (ii)
`SwitchLayers.swift` was correctly excluded (§4.24's Metal-`"""` trap).

**Gates:** comment-strip check PASS (the checker was extended by +5 lines with
zero deletions and its default `BASE_SHA` untouched — *not* relaxed); scope
PASS; budget PASS with `growth=-18274/262144`; docc-detach PASS; Part B dry run
PASS; scored worker build PASS; ⭐ **64-step drift tripwire PASS** — the item
deferred from #288 is now discharged.

⭐ **The equivalence-oracle handling here is the campaign reference
procedure.** `run_upstream_equivalence.sh` exits 1 on this host for a reason
unrelated to the change: prefill `maximumAbsoluteLogitError = 0.125`, all 8
decode steps exact, 0 token mismatches, `EQUIVALENCE_EXACT_STEPS=8`,
`Test run with 1 test in 0 suites`. The student then **restored the five files
to BASE_SHA, re-ran, and obtained an identical result to every digit**, then
restored HEAD. `MLXFAST_LOCAL_ALLOW_GOLDEN_DRIFT` was **not** set. That is how
a pre-existing oracle divergence is to be discharged: prove byte-identity of
the failure on the unchanged base, never relax the gate.

⚠️ **Deficiencies recorded in the public review** (`issuecomment-5220580380`):
`./setup.sh` unreported; `./benchmark.sh --local-iterate` replaced by a bare
`swift build --scratch-path .build-worker` for the **second consecutive time**
from this student; no raw transcripts; only 13 pointers for 54 relocated
blocks; Part A campaign-marker per-file counts never printed.

**Part B manifest** (research-only, unapplied) sizes the remaining prize in the
scored file: pool **254 blocks / 120,254 B** outside literals; **RELOCATE 94
blocks / 28,643 B moved + 980 B pointers ⇒ 27,663 B net**; HARD-KEEP 58,837 B
(48.9%). Wave 1 (86 blocks, 26,216 B net) became **#320**.

### 4.26 ⛔⛔ Round-36 recon A — the `residual_rms_router` family is CLOSED

Subject: `laguna_residual_rms_router_rpg8_keys_v1`, previously our ranked lead
#3 on the strength of a ~154 µs/step "excess" in the decode roofline census.
**That excess is largely an artifact (rule 30).**

**Geometry.** Builder `LagunaRuntimeModel.swift:853-985` (MSL body `919-984`),
variant cache `991-1011`, Swift wrapper `lagunaResidualRMSNormRouter`
`1055-1096`, encode `:1088-1089` → `grid: (tiles*512,1,1)`,
`threadGroup: (512,1,1)` with `tiles = experts / rowsPerGroup` (`:1081`). At
the default `rowsPerGroup = 8` that is **32 TGs × 512 threads = 16,384
threads**, 16 simdgroups per TG of which **only 8 are active** — a compile-time
whole-simdgroup guard, so the useful-lane fraction is exactly **50% with zero
intra-warp divergence**. Phase 1 runs on all 512 lanes of all 32 TGs: fused
`summed = residual + branch`, RMS over `axis_size = 2048`, `base = lid *
n_reads` (`:934`) with **no tile offset — every TG reads the same row**. Phase
2 runs on the 8 active simdgroups: 16 blocks of width 128, `vec<bfloat,4>`
loads, strict `(block,i)`-ordered FP32 accumulation, `simd_sum` plus a 5-step
shuffle ladder. Four barriers; 4,228 B static threadgroup memory. Called from
decode `:10364` (39 of 40 layers) and terminal prefill `:10461`.

**Byte accounting — the artifact.** Unique ≈**1,061,888 B/call**; issued
≈**1,441,792 B/call** (1.36×). The `[256,2048]` bf16 router weight is
**partitioned, not broadcast** (32 TGs × 8 rows), so it is read exactly once.
The 32× re-read is only the norm prologue's 12,288 B → 393,216 B issued. At
6.8 µs/call the *unique*-byte rate is 156 GB/s (60% of the M4 Pro 260.2 GB/s
ceiling) but the *issued*-byte rate is **≈212 GB/s ≈ 81% of ceiling**, and the
re-read 384 KB is L2-served. **A DRAM roofline does not bind this kernel.**
Independently, `maple-fern-decode-marginal-cost-ledger.md:311-341` gives a
chained marginal cost of **106 µs/step (2.73 µs/call)** against a 305.1 µs/step
census figure ⇒ **E = 0.349, two-thirds shadowed** (rule 25).

**Every lever is dead.** rpg retiling is bit-exact but measured null and the
source itself says "SUB-8 IS MEASURED NULL … do not re-sweep" (`:604-628`);
the invariant `tiles × rows_per_group == 256` means retiling **cannot change
in-flight bytes**. Threads-per-TG ≠ 512 via the 64-thread virtualised tree is
legal (#300) but worth −0.182 ± 0.845 µs. Changing `n_reads`, reassociating the
accumulator, or transposing the weight are **not bit-exact**. Splitting out the
redundant norm prologue has a ≈44 µs/step ceiling but costs +1 dispatch ×
39 layers ≈ 140 µs ⇒ **net negative**. Fusing router-top-8 in is both
structurally blocked and fully shadowed (marginal 0.00 ± 0.12 µs/call; reverted
three times). Weight-hoist depth 1→16 moves the step 13 µs = 0.15%.

**Prior art was already negative and we did not act on it:**
`maple-tanjiro-pr73-decode-kernel-census.md:718` says **"Recommend closing"**;
`nezuko-pr158-decode-dead-time.md:511-560` says **"Kill rule fires. Stop."**
`maple-fern-decode-marginal-cost-ledger.md:53` pre-registered the chain-link
prediction and recorded it **refuted**. ⚠️ One unresolved inconsistency:
`nezuko-pr158` reports 8.20 µs/call *and* "~217 GB/s", which are mutually
incompatible on 1.062 MB. ⚠️ Two caveats: `LagunaRuntimeModel.swift:837-1099`
is currently fenced by #309; and the referenced provenance notes (`notes/47`,
`notes/50`, `notes/exp-rpgrouter.md`) are **absent from the tree**, so whether
rpg16/rpg32 were ever measured is not locally verifiable.

### 4.27 ⭐⭐⭐ Round-36 recon B — prefill MoE corrected, and the top unassigned lever

**Headline correction (rule 30).** `43.2619 ms` is **not** the prefill window.
It is `dS_1`, the *marginal* wall-clock cost of the routed-MoE block (39 layers
PREFILL_ROUTED vs 0) — `research/tanjiro-pr34-r2-result.md:660`. The official
M5 prefill wall is **`S ≈ 97.895 ms`**
(`research/artifacts/tanjiro-pr170-receipt-b2.json`, promoted control
`97a5090`), and routed MoE is ≈**44% of prefill**
(`research/artifacts/tanjiro-pr170-note-m2.md:31`). Consequently the
`6.887 ms` "pure issue" term is **15.9% of the MoE window `W`**, i.e.
≈**7.0% of `S`** — not 15.9% of prefill. `dS_1` is an *upper* bound on the MoE
denominator, so every GB/s derived from it is a *lower* bound, and the correct
39→38-layer rescale is **downward to 42.1526 ms**; the `×40/39 = 44.371 ms` at
`tanjiro-pr34-r2-result.md:701-705` is **wrong**.

| claim | verdict |
|---|---|
| `43.2619 ms` is the prefill window | **REFUTED** — it is `dS_1` |
| prefill window | **`S = 97.895 ms`**, MoE `W ≈ 44%` of it |
| `6.887 ms` pure issue | **CONFIRMED** = 7.853 − 0.420 − 0.546; 15.9% of `W` |
| `24.15 ms` streaming floor | **CONFIRMED** (14.8264 GB / 614 GB/s); supersedes 28.77 ms |
| `19.11 ms` headroom | **CONFIRMED**; up to **7.16% of score** at 0.374750 %/ms |

**Dispatch shape.** 1,222 GPU dispatches in 81 command buffers per 512-token
prefill forward, strictly serial
(`maple-tanjiro-pr91-prefill-budget-census.md:28-40`). MoE families: 76
`routed_gather_gemm` (38 layers × 2), 154 `sort_scatter`, 38 `moe_tail`, 40
`router`, 116 `nvfp4_dense_qmm` — so **the shared expert is a plain dense NVFP4
QMM**. The prefill/decode fork is `LagunaRuntimeModel.swift:10180-10190`
(`x.dim(1)>1 && inds.size>=64`) → `lagunaFusedSortedRoutedGateUp:9773`, versus
decode's `:10012-10015`. Because `x` is expanded to `[4096,1,2048]` the
predicate at `quantized.cpp:2351` sends prefill to **`gather_qmm_rhs_nax`**
(`:1653`) while decode falls to `gather_qmv` (`:1046`). Ranked tile
`BM=64,BN=64,BK=64,WM=4,WN=1` = 128 threads/TG.

⭐ **Prefill MoE is row-sparse but ~86% dense in weights.** Zero-row experts
stage nothing (the chunk loop never executes), and `sg_active` elides whole
SM=16 MMA bands — yet **79.74% of the 256 × 38 expert slots receive ≥1 token**
at T=512, so actual weight traffic is **8,379 chunks = 14.8264 GB** against an
all-dense equivalent of 17.2134 GB, i.e. **86.1%**. The 1.456× MMA row padding
moves **zero bytes**. ⇒ prefill MoE is **weight-streaming-bound**, and
"skip the empty experts" has **no byte prize**.

⚠️ Two admissible denominators, never to be mixed:
`14.8264/43.2619 = 342.7 GB/s` (55.8% of 614) versus
`14.8264/(43.2619 − 6.887) = 407.6 GB/s` (66.4%). The old 408.4 GB/s headline
matches the second **by coincidence**. Provenance: ΔM2/ΔB2/ΔS2/ΔS3, `S` and
correctness are official **M5 receipts**; the only per-kernel census is **M4
Pro**, with 94.3% of its trace inside NAX-divergent kernels ⇒ directional only.
The `34.7 TFLOP/s` ceiling is **circular**; the non-circular compute ceiling is
56 TFLOP/s.

**Bit-exact levers, priced.** The operative filter, inherited from closed
PR #215: *count device-load and threadgroup-store issues per thread per
k-iteration; if the count does not fall, expect a null.* Today the loader
issues 3 device loads moving 18 B (one 128-bit packed-weight load plus **two
1-byte scale loads**) and accounts for ≈68% of LSU traffic; the loop is
**issue-bound**.

| lever | saving | bit-exact | `_nax` |
|---|---|---|---|
| ⛔ ~~**1. Widen/amortise the scale loads**~~ — one aligned 16 B load covering 4 k-iterations; loads/thread/iter **3 → 1.25** | **CLOSED — already run and refuted as PR #244** | yes | yes |
| ⭐⭐⭐ **2. Larger tiles / A-fragment N-tile reuse** — reduces *requested bytes*, so it is **outside** the refuted issue-count family | up to several ms, high variance | yes, if per-output accumulation order is preserved | yes |
| 3. `BK=128` (down-proj only) | +0.4–0.8 ms, but `Ws` 17.4 KB drops residency 7→3 TG/core ⇒ likely null | yes | yes |
| 4. Fuse SwiGLU into the gate/up epilogue | **ALREADY DONE** | — | — |
| 5. Fuse down-proj with combine/scatter-add | **ALREADY DONE** (`lagunaPrefillSortedMoETail:9709`); ≤~0.4 ms left | — | no |
| 6. Skip zero-token experts | **no byte prize**; 0.07–0.46 ms, below the 1.0 ms gate; indirect dispatch unreachable | ~0 | — |
| 7. LPT expert→threadgroup scheduling | **REFUTED ≈0.000 ms at R=1** | — | — |
| 8. `DARKBLOOM_EXPERT_GATHER_GROUPS` 256→128 | ≤0.5 ms, sign-uncertain in core count; 256 is optimal | | yes |
| 9. depth-2 pipelining, double-buffered `Ws`, any pure reordering | **dead by closure** (#215; arm 1 measured **+0.684 ms / +1.52σ** while bit-exact) | — | — |

**Ranking (corrected round 39): lever 2 > lever 3 > lever 8.** Lever 1 is
**dead** — it was assigned, run on the ranked M5 and closed as PR #244, and the
round-36 table that ranked it first was written without that closure in view
(see standing rule 31). Levers 4–7 and 9 are spent. Levers 2, 3 and 8 all live
in `_nax` code that **cannot execute on M4 Pro (gen 16)**, so each needs an
official M5 receipt — and the ranked pipeline is the binding constraint, not
the idea supply. Lever 2 is the only survivor that attacks *requested bytes*
rather than *issue count*, which is precisely the axis #244 refuted, so it is
the one prefill `_nax` arm worth a receipt when the pipeline recovers. Read
**raw candidate prefill s/token**, never
`prefill_speedup` (σ_Δ = 0.449 ms). ⚠️ Probe selection is a **compiled-in
constant** `kNaxGatherProbeDefault` (`quantized.cpp:1631-1646`, committed `""`):
**never express arm magnitude through a runtime function constant** — doing so
previously cost 15–24%.

### 4.27b ⭐⭐ Corrections to §4.27's code geography (round-37 recon A)

- **Kernel name.** The ranked 512-token prefill MoE kernel is
  **`fp_gather_qmm_rhs_expert_nax`**, *not* `fp_gather_qmm_rhs_nax`. Dispatch
  chain: `GatherQMM::eval_gpu` (`quantized.cpp:2323`) → the `gather_qmm_rhs`
  gate at `:2351-2352` (`M==1 && B>=16 && right_sorted_ && B/E>=4`) → `:2098-2100`
  → `gather_qmm_rhs_nax` `:1653` → the bm128 switch `:1692-1705` →
  `expert_aligned` `:1731-1735` → template build `:2013-2033`.
- **Function constants 200–207 do NOT reach the ranked kernel.** They are
  declared in `fp_quantized_nax.h:9-24` (200 `align_M`, 201 `align_N`,
  202 `align_K`, 203 `gather_run_skip`, 204 `stage_widest`, 205 `stage_wideld`,
  206 `stage_runbar`, 207 `stage_novol`), but `quantized.cpp:1974-1985` binds
  `func_consts` **only `if (!expert_aligned)`**. ⇒ the compiled-in default *is*
  the ranked arm; an `_nax` A/B must be a compiled-in template argument or a
  JIT `#define` resolved once per process.
- ⚠️ **Never flip a function constant mid-process.** `quantized.cpp:1213-1216`
  and `:1298-1301` record that the removed "1:N" dispatch-prefix form forced a
  second pipeline compile *inside* the timed prefill and cost a reproducible
  **15–24 % regression**.
- **Twin path (rule 9).**
  `Vendor/mlx-swift/Source/Cmlx/mlx-generated/fp_quantized_nax.cpp` (2145
  lines). Header `:196-513` is byte-identical to twin `:345-662`; the read site
  is header `:1865` ↔ twin `:1997`; the probe parameter is header `:1576` ↔
  twin `:1719`. Verify with `python3 research/nax_twin_check.py`.
- ⚠️ **Uncertified `scales` base alignment.** `darkbloom_stage_wide_load_ok`
  (`quantized.cpp:1541-1571`) certifies **only the weight array**; the `scales`
  array's own base `offset()` is never certified. Any wide-load widening on the
  scale plane must certify it first.
- ⭐ **Decode-axis reachability.** All block-loader kernels gate on `M ≥ 64`, so
  they are prefill-only for a steady decode step — **but the decode axis begins
  with a 512-token seed prefill**, so this loader *does* execute inside the
  decode measurement. Seed-forward score elasticity on M5 = **0.362**.

### 4.28 ⛔ Round-39 offline recon — two `_nax` levers closed without a receipt

**A. The `Ws` threadgroup-read swizzle / bank-conflict axis is PRE-ANSWERED.
The `+8`-element pad IS the swizzle.**

Ranked geometry is `quantized.cpp:1694-1706` (`bm=64,bn=64,bk=64,wm=2,wn=2`)
then shipped case 5 (`darkbloom_stage_bm128_variant()` returns 5 on an empty
env, `:1491+`) → `bm=64; wm=4; wn=1;` ⇒ **128 threads/TG**. `Ws` is
`NAXWsChunk16` (`fp_quantized_nax.h:196-199`) with
`BK_padded = BK + 16/sizeof(Wtype)` (`:1608-1609`) ⇒ bfloat **72**,
`kWsElems = 64*72 = 4608`, `Ws_storage[576] × 16 B = 9216 B` (PR #170 receipts
report `staticThreadgroupMemoryLength = 9232 B`). Read site `:1865-1866`:
`Btile.load_contig_tg<Wtype, BK_padded>(Ws + tn*BK_padded + kk1)`.

⭐ **Bank arithmetic kill.** Pitch `72*2 = 144 B = 36 words`, and
`36 ≡ 4 (mod 32)` ⇒ `bank = (4*fm + fn/2 + K) mod 32`, giving exactly 2 lanes
on each of 16 even residues; each lane's 8 B spans 2 words ⇒ **64 distinct
words, exactly 2 per bank across all 32 banks = the hard 2-cycle floor**. An
unpadded 64-element pitch would cost 8 cycles (**4× worse**). There is no
headroom left on this axis.

Only a cheap paired *rider* arm could justify probing it. A fifth probe arm
costs one `if (s == "tgr") return 5;` in `quantized.cpp:1633-1651` plus
flipping `kNaxGatherProbeDefault` at `:1631`. The technique is proven in-repo
twice: `research/nezuko-attention-merge-epilogue.md:173-186` probe P3
(`BDP 33→32`, bit-identical, **+1.966 µs sliding / +1.820 µs full**) and merged
**PR #30** (`RESEARCH_STATE_ARCHIVE_through-round-21.md:4969-4984`, stride
32→33, isolated **−6.30 %**, end-to-end decode **−0.94 %**). ⚠️ Those are
per-threadgroup effects, so the **M5 absolute saving is roughly half** (~40–45 µs
of 4322 ≈ 1.0 % of `T` ⇒ ~0.6 % of score). Do not conflate this with the MLX
grid/tile `swizzle_log = 2` (`tanjiro_nax_skinny_occupancy.py:45-49`), which is
a different mechanism.

**B. The `store_ok`/`load_ok` ALU hoist is near-dead — kill it offline.**

The identifiers are `store_ok`/`load_ok` (not `win_ok`); `load_unsafe_wide`
recomputes both on every call (`fp_quantized_nax.h:399-403`, with
`dst_byte_off()` `:377-379` and `src_byte_off()` `:383-385`). Measured locally:
`EMIT_IR=1 OUT_DIR=/tmp/nax_winok bash research/nax_msl_compile_check.sh`
produces 4185 lines of IR; the ranked instantiation is **outlined** at
`unit.ll:582`; the predicate prologue `unit.ll:586-601` is ≈10 integer ops; the
compiler has already strength-reduced the dst test to `(bj & 3) == 0`; the
surviving `sdiv` exists only because `src_ld` is reloaded from the struct
(`unit.ll:593`) — an outlining artefact. Totals are ≈320 integer ops per thread
for gate/up (K=2048 ⇒ 32 iterations) and ≈80 for routed-down (K=512 ⇒ 8).

⭐ **Ceiling ≈1.0–1.4 ms off 97.9 ms ≈ +0.25–0.35 % of score**, i.e. 3–4σ at
absolute best against `σ_Δ = 0.449 ms`. Bit-exactness is proved twice (`next()`
`:505-512` never touches `bi`/`bj`/`src_ld`; the ctor `:236-256` runs at `:1750`
outside the k-loop; PR #215 §B.2 Constraint 3 gives
`dst_byte_off() = 144*(tid/2) + 64*(tid%2)`, always 16-B aligned ⇒ `store_ok`
is unconditionally true). ⚠️ `research/tanjiro-nax-kloop-pipeline.md`
(~`:420-433`, ~`:544`) already reports the PF=0 IR census and records that
"hoisting the predicates to kernel scope" was **considered and rejected**.

⇒ **Cheapest kill (~10 min, zero receipts):** rebuild the two instantiations
with `__attribute__((always_inline))` (or `EMIT_LIB=1` plus `metal-objdump`)
and check whether the `sdiv` and both `and`/`icmp` pairs vanish. If they do,
the backend has already done the hoist and the lever is dead.

### 4.29 ⭐⭐ Final-round experiment outcomes (#308, #309, #301, #320)

- **#308 — maple-tanjiro, threadgroup packing curve (merged 07:27Z).** Stage 1
  ABBA `0 RV V G R N N R G V RV 0`, 4 scored blocks, 48 scored runs, 8/arm, 192
  steps kept. Means: S=1 8196.2 · S=2 8196.8 (ref) · S=4 8180.1 ·
  **S=8 8159.9 (argmax, −36.9, CI [−61.0, −12.9])** · S=16 8163.5 (−33.4) ·
  S=32 8184.4 (−12.4). `{4,8,16}` are tied and **S=32 is second-worst** ⇒
  monotonicity refuted, the optimum is interior. `R−G = +3.6` CI
  [−20.5, +27.6] is a dead null. Fault attempt 1 was a semantic no-op (a
  bijection over rows) and passed; attempt 2 (store-index-only rotation) failed
  at S=2/S=16 with S=1 identity passing as a control. ⚠️ The archived
  `research/packing-curve-logs/fault2-driver.log:7-9` still literally says
  "Stage 1 is INVALID" — that is a rigid global `EXPECT=fail` artefact, not a
  verdict. Four-site audit: site 1 routed MoE gate/up `:7546` **PURSUE** at
  S=4–8; sites 2/3 LOW PRIOR; site 4 fused down+residual **KILL** (slot ≡
  simdgroup ≡ expert identity). Stage 3 was left as an unapplied +29 B patch;
  no equivalence run; no `--local-iterate`. W&B `8st0k26f`.
- **#309 — maple-nezuko, persistent grid-stride QKV (merged 07:59Z) — KILL.**
  Stage 2a, 7 arms, se 11.0 µs, 46 df. Means: `a0` 8166.9 · `G640` 8160.0 ·
  `R640` 8216.5 · `N640` 8133.2 · `G128` 8334.8 · `R128` 8356.7 · `N128` 8230.1.
  The killer term is **`G128 − G640 = +174.9 ± 11.0 µs/step`**, with a T-ladder
  cliff below core count (full(640) 8.159/8.163 · 128 +182 · 64 +195 · 32 +153 ·
  **16 +917**). `N128 − a0 = +63.2 ± 11.0` (t 5.76); **`N640 − a0 = −33.7 ± 11.0`
  is significant but sub-bar — an unmerged win.** ⇒ **standing rule 32**. W&B
  `b624rd0b`.
- **#301 — maple-frieren, shared-QMV twin gap (merged 08:10Z).** Mechanism (a)
  K-block prefetch: OFF 7.573 (sd 0.120, n=6) vs ON 7.210 (sd 0.070, n=6) ⇒
  **Δ = −0.363 µs/call, 95 % CI [−0.495, −0.232], −4.80 %**, perfect 6-v-6
  separation; the invariant control is null ⇒ −14.2 µs/step = **0.111 %** of the
  12.78 ms decode wall, ~5.6× below the 80 µs bar. Mechanism (b), the
  pairwise/halved scale plane, is **REFUTED at +1.93 %** despite halving the
  plane 131,072 → 65,664 B/call ⇒ closed, and now ~3 KB of deletable dead code
  in the binding file. ⚠️ Both ABBAs used `ORDER="off on on off"`, so arm is
  confounded with slot kind; the untouched control moved **−0.449 µs / −1.16 %**
  ⇒ **standing rule 36**, and (a) stays default OFF until the reversed-`ORDER`
  separator runs. Reachability correction: the scored shared gate/up QMV is
  issued from `LagunaRuntimeMLP.fusedSharedDownInputs`, **not**
  `callAsFunction`. The patch is inert in a ranked run (strict `== "1"` opt-ins
  at `:6806-6813`; the official runner strips env). Surface grew
  468,336 → **475,647 B**. W&B `ag6xhecn`.
- **#320 — maple-fern, `LagunaRuntimeModel.swift` byte recovery (merged
  ~08:15Z) — terminal negative.** The submitted-surface diff is **empty**, the
  file blob is identical at both ends, and the **net shrink is 0 B against an
  ≥18,000 B bar**. Measured ceiling **12,910 B gross / 9,362 B wave-1 net /
  10,251 B full-plan net** against a 28,643 B projection; root cause was
  char-vs-byte counting. Durable findings: **50 of 62 abstracts truncate
  mid-sentence**, costing 3,560–8,531 B of a 9,362 B win; the hard-kept pool is
  **82,899 B = 69 %** of the 120,254 B comment pool; 0 of 54 relocated blocks
  are rule-bearing; all six named pins were kept. 🔴 **Known regression left
  unfixed:** adding the scored file to
  `research/frieren_comment_strip_check.sh:44` makes that script exit 1
  **unconditionally for every future user**, destroying the "PASS — 9/9" signal
  that #311 Part A relies on
  (`research/maple-fern-vendor-byte-recovery.md:251`). ⇒ comment relocation is
  closed; the real fix is to **split `LagunaRuntimeModel.swift`** into a second
  file under `Sources/MLXFastModel/` (already an `editablePaths` directory
  prefix ⇒ in-surface), after which the per-file cap stops binding.

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

### 7.0 ⭐⭐⭐ THE LIVE ASSIGNABLE QUEUE (final round, 2026-08-08 10:30 UTC)

This subsection supersedes the round-25 queue that follows it; that older queue
is retained below for provenance only. Base for every row:
`b1b8dca2ffc5349d153c839f1eb9a790f2b9bfab`. Editable budget at that base,
verified this round: `current=2857088/3000000 headroom=142912 growth=0/262144
files=140`. `LagunaRuntimeModel.swift` is **475,647 B against the 524,288 B
per-file cap**, so per-file headroom is ≈48,641 B and it, not the total, is the
binding constraint.

| # | student fit | experiment | expected size | why now |
|---|---|---|---|---|
| **Q1** ⭐⭐⭐ | nezuko | **Algebraic epilogue normalization at full coverage** (#309 §11.1). Keep the 5120-TG grid; remove the redundant cross-simdgroup reduction algebraically instead of by coarsening the grid. | priced ceiling ≈ **140 µs/step**, clears the ~80 µs bar | #309 killed *grid coarsening* (+174.9 ± 11.0 µs/step) but the epilogue term itself was never attacked at full coverage. Its own `N640 − a0 = −33.7 ± 11.0 µs` is a real, unmerged win this arm should subsume. |
| **Q2** ⭐⭐⭐ | frieren | **Routed-twin K-block prefetch** (#301 §7.3): port #301 mechanism (a) from `lagunaSharedSwiGLUQMVRows1Kernel` to `laguna_routed_nvfp4_swiglu_qmv_packed_top8keys_r1_bf16_v2` (`LagunaRuntimeModel.swift:7546`). | ≈ **−72 µs/step ≈ −0.56 %** | The shared twin measured −0.363 ± 0.13 µs/call over 39 dispatches; the routed twin runs the same 39 dispatches at 38.00 µs/call with 8× the weight traffic. Same mechanism, ~5× the surface. |
| **Q2a** ⭐⭐ | frieren | **Reversed-`ORDER` Stage 1 separator for #301 mechanism (a)** — re-run the Stage 1 ABBA with `ORDER="on off off on"`. Cheap; can be stage 1 of Q2. | decides a one-line default flip at `:6810-6812` | Rule 36: #301's `ORDER="off on on off"` confounds arm with slot kind, and the untouched control moved −0.449 µs (−1.16 %), larger than the −0.363 µs claimed effect. Until this runs, mechanism (a) must stay default OFF. |
| **Q3** ⭐⭐⭐ | fern (paired with a timing arm) | **Split `LagunaRuntimeModel.swift`** into a second file under `Sources/MLXFastModel/`. That directory is already an `editablePaths` prefix, so a new file is in-surface and the per-file cap stops binding. | ≈48,641 B → ≈142,912 B of usable headroom | #320 measured the comment-relocation ceiling at ~9.4 KB net against an ≥18,000 B bar. Relocation is a dead end; the split is the real fix. ⚠️ fern is owed a *timing* experiment — pair the split with a timing arm, or give the split to another student. |
| **Q4** ⭐⭐ | tanjiro | **#308 Stage 2 as fresh work**: threadgroup packing at site 1, routed MoE gate/up (`:7546`), sweeping `S ∈ {2,4,8,16}`. | site 1 carries 1501.7 µs/step, the largest single decode kernel | #308 found an interior argmax at S=8 on the QKV kernel (−36.9 µs/step, CI [−61.0, −12.9]) and refuted monotonicity. Site 1 is the audit's only PURSUE. ⚠️ **Rule 33: the arm MUST carry an `_sgN` kernel-name suffix**, or the pipeline cache serves one variant to both arms. |
| **Q5** ⭐⭐ | tanjiro or nezuko | **Land #308 Stage 3**: apply the +29 B `research/tanjiro_packing_default_flip.patch` (S=2 → S=8 on the QKV kernel), then run `research/run_upstream_equivalence.sh` **and** a `./benchmark.sh --local-iterate` pair, plus an S=8 fault-injection arm and the rule-17 prefill arm. | −36.9 µs/step ≈ 0.46 × the bar | #308 left the win as an unapplied patch with no equivalence run and no `--local-iterate` pair. Sub-bar alone, but it composes with Q1/Q2 and costs almost nothing. |
| **Q6** ⭐ | any | **#301 §7.3 decode-neighbour effect**: a −1.40 % whole-step movement roughly 10× larger than the removed traffic can explain. | unexplained and large | If it is real and steerable it dwarfs every kernel-local lever here. If it is a session artefact, it invalidates a class of our single-session Stage-3 numbers. Either answer is worth a slot. |
| **Q7** ⭐ | fern (cheap) | **Fix `research/frieren_comment_strip_check.sh:44`** — implement the third `not covered` verdict (~10 lines). | restores a shared gate | 🔴 #320 added the scored file to the checked set, so the script now exits 1 **unconditionally for every future user**. #311 Part A cites it as "PASS — 9/9"; that signal is destroyed from base `4b81aa7d` onward. |
| **Q8** ⭐ | any (cheap) | **Delete #301 mechanism (b)**, the refuted pairwise/halved scale plane, from `LagunaRuntimeModel.swift`. | ≈ **3 KB** of the binding per-file budget | Measured +1.93 % regression; closed. Dead code sitting in the one file whose per-file cap binds. |
| **Q9** ⭐ | any (cheap, offline) | **10-minute always-inline IR diff** to formally kill the `store_ok`/`load_ok` ctor hoist. | zero receipts; closes a lever | See §4.28 B. Ceiling is only ≈+0.25–0.35 % and the backend has probably already done it. |
| **Q10** ⭐ | any | **Prefill `_nax` lever 2 — A-fragment N-tile reuse** (`research/tanjiro-nax-kloop-pipeline.md:1080-1086`). | "up to several ms" of a 97.9 ms prefill; must exceed **≈1.35 ms** to clear 3σ | The only surviving `_nax` prefill lever. It reduces *requested bytes*, so it sits outside the issue-count family PR #244 refuted. |

⛔ **Do not assign** (all closed with evidence): the `Ws` threadgroup-read
swizzle / bank-conflict axis (§4.28 A); the `store_ok`/`load_ok` ctor hoist as
a *receipt* experiment (§4.28 B — do Q9 offline instead); `_nax` scale-load
amortization (PR #244); comment-relocation byte recovery (#320); any
coarser-grid amortisation on the QKV kernel (#309); #301 mechanism (b); the
whole `residual_rms_router_rpg8_keys_v1` family (§4.26).

⚠️ **Pipeline precondition for every row above.** As of 2026-08-08 10:17 UTC the
account-scoped ranked pipeline has produced **thirty-five consecutive `failed`
terminal receipts** since `3ff3992` (2026-08-07 18:51 UTC, `rejected`,
`officialScore 2.52125675539565`) — about 15.4 h of continuous outage, with no
new receipt of any kind since `b63e076` at 08:16 UTC. This is an operational
failure, not a candidate problem. Only a **non-`failed` terminal receipt**
counts as recovery. Until then these experiments run locally and stop at a
durable local verdict; none of them may consume a ranked slot.

---

**The round-25 queue below is retained for provenance only.**

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

  > **SUPERSEDED (2026-08-07).** Items 2 and 3 above are wrong. The audited
  > census — [`maple-byte-recovery-census-2026-08-07.md`](maple-byte-recovery-census-2026-08-07.md)
  > — found the `.metal` "duplicates" are all `kernels/X.h` ↔ `mlx-generated/X.cpp`
  > AOT/JIT twins that AGENTS.md requires to both exist (**0 B recoverable**), and
  > BK128 is 2,693 B not 5,164 B. Use the census, not this list.

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

**Closed in round 87 (2026-08-08) — see the R85-D block near the top for the
evidence:**

- **⭐ Dispatch-count reduction that does not eliminate a DRAM round trip —
  CLOSED.** #458 fitted `c_issue ≈ 0.17 µs` against `c_drain ≈ 1.24 µs per
  4 KiB`: the byte axis beats the count axis **7.7 : 1**. Removing `N`
  dispatches whose intermediate stays resident refunds ≈`0.17N` µs, which for
  any realistic `N` is far below the ~80 µs/step ranked detection bar.
  Reopening requires showing that the proposed change deletes a *materialised
  intermediate*, with its byte count, not merely a dispatch.
- **⚠ Not a family, but a standing trap: the CB-count mirage.** `45 command
  buffers/step × 1.7 µs ≈ 76 µs/step` is **not** on the table. The 1.7 µs
  figure is SPLIT-mode only; packed boundaries cost ≤0.14 µs each.
- **⚠ Superseded, not closed: "the barrier prize is 371 µs/step."** That is a
  gross figure. See the NET selection rule; 6.2 barriers/layer against ~7
  structural waves plus §4.18's ranked −0.1488 % say the net is much smaller.

**Closed in round 34 (2026-08-07) — see §4.23 and §4.24 for the evidence:**

- **⭐⭐⭐ The ENTIRE decode fused-attention family — CLOSED.** Both
  `laguna_sliding_fused_attn_ring_v1` and `laguna_full_fused_attn_grow_v1` are
  now off the board for occupancy/wave splitting, KV-splitting across
  threadgroups at *every* S, head-axis repartition, threadgroup-memory
  shrinking, 1-head-per-threadgroup, load-pipeline depth, and the float4
  merge-epilogue.
  **⚠ Clarification added round 87: "the float4 merge-epilogue" is closed for
  FURTHER WIDENING, not closed as a mechanism.** Reason 4 below says
  explicitly that "the epilogue lever was already cashed" — cashed by #205,
  which measured **+18.58 ± 2.92 µs/step, t = 6.37**, bit-exact. The frontier
  adoption silently reverted #205 by rewriting both epilogues to plane-major
  SoA, so re-porting the AoS form is a *replication of a measured winner* and
  is explicitly in scope (#457). Widening past 4 planes remains
  hardware-blocked: 8 float4 planes need 33,792 B against the 32,768 B
  threadgroup limit.
  Four independent reasons, any one of which is sufficient:
  1. **The apparent headroom was an artefact.** The census rows priced these
     two kernels at 37.1% and 34.7% of DRAM peak. That denominator is wrong:
     GQA replication means each KV row is issued 4× (sliding) / 3× (full), so
     the kernels request 8.389 MB and 7.078 MB per call — **406 GB/s and
     284 GB/s, i.e. 149% and 104% of the M4 Pro peak.** Those reads are
     **cache-served**; there is no DRAM roofline gap to close (standing rule 26).
  2. **Occupancy is already a single wave.** PR #196's staircase fit
     `T(K) = 1.661 + 7.408·⌈K/C⌉` with **C = 40** means 32 (sliding) and 24
     (full) threadgroups are one wave on the ranked M5 — the idle simdgroups
     4–31 in the prologue cost **literally zero**, they are an intercept term,
     not a slope term. §8's existing "KV-split-across-threadgroups family, at
     EVERY S — CLOSED" row already covers the split direction.
  3. **The k-loop is at ≈90% of its own issue-rate floor** (0.749 µs/iter
     ≈ 1054 cycles against a ~880–960 cycle floor), with roughly **84 of ~104
     FP slot-equivalents pinned by bit-exactness**. There is no arithmetic to
     remove without changing the numerics.
  4. **The epilogue lever was already cashed.** PR #205
     (`research/nezuko-attention-merge-epilogue.md`, merged `3ffc371d`, commit
     `1aad492f`) took the float4 merge epilogue: bit-exact, max_abs_diff 0 over
     1344 steps, in-situ **+18.58 ± 2.92 µs/step, t = 6.37, 12/12 pairs
     positive**. **Nothing has touched either kernel body since.** Widening it
     further is hardware-blocked: 8 float4 planes need 33,792 B of threadgroup
     memory against a 32,768 B limit.

  Burned branches, all already on `origin`, all null or negative:
  `birch-thorfinn/attn-epilogue-1pass`, `…-v2`, `attn-pair-o-float4`,
  `attn-tg-shrink`, `birch-askeladd/attn-output-float4-v1`,
  `birch-alphonse/fused-pairab-softmax-v1`,
  `maple-fern/attn-reduction-packing` (`4e8b1da8`),
  `maple-fern/gqa-kv-group-cooperative-attention`. PR #103 additionally
  measured 1-head/TG as **bitwise identical but +20.1% slower**, pipeline depth
  4 at −1.039% and depth 8 at +0.485%, against a byte-identical-`Sources/`
  noise floor of **+0.73%**.

  The PR73 census's "−0.084 ms attention excess" does **not** reopen this: that
  row covers only the *projection* block, which is at **107% of its own floor**.
  The two fused kernels live in the census *remainder* block (sliding 341.9 µs
  = 5.08%, full 145.6 µs = 2.16%, sum **487.5 µs M5-equivalent = 7.24%**), which
  the census itself disclaims at `:594-606` and marks CLOSED in its §8.1.

- **⭐⭐ H7's "skip the softmax rescale when the max is unchanged" — the
  multiply-skip half is ARITHMETICALLY DEAD.** At
  `LagunaRuntimeModel.swift:1517-1553` the rescale-consuming code is
  `pair_sum0 = pair_sum0*pair_factor0 + pair_exp0` plus four
  `pair_o0[p] = pair_o0[p]*pair_factor0 + pair_exp0*pipe_va{p}` = **9 ops**.
  Skipping when `pair_factor0 == 1.0f` gives either the *contracted*
  `fma(e,v,o)` at 5 ops — which rounds **once** instead of twice and is
  therefore **not bit-exact** — or the bit-exact mul+add form at **9 ops, zero
  saving**, because FADD and FFMA occupy the same issue slot on Apple GPU. The
  `exp` half of H7 already shipped inside `LAGUNA_RESCALE` (`:1647-1658`).
  **Only the "specialise the FULL kernel on `N`/`capacity`" sub-lever survives**
  (20–40 µs, weak); the sliding kernel already has `constexpr int N = 512`.
  ⇒ standing rule 28.

- **⭐⭐ The whole `lagunaNormAffineQKV` INT8 family (`:4880-5400`) — CLOSED as
  dead-by-default (#300).** `lagunaNativeAffineNVFP4From` (`:2861-2867`) returns
  0 and `lagunaNativeAffineWeight` (`:2914-2925`) quantizes every layer at
  `groupSize:16, bits:4, mode:.nvfp4`, so the fused-dispatch guard `:5739-5741`
  (which demands `.affine/8/32`) is **never satisfiable**. The 64-thread
  virtualized RMSNorm tree is *built* by default but **never dispatched**; the
  live kernel is `lagunaDecodeNVFP4QKVR1` (`:4815-4881`). Standing rule 1 is
  amended accordingly: quote the **dispatch** guard chain down to a default
  value, not merely the construction site.

- **⭐⭐ On-chain fusion edges E1, E3, E4, E5, E6 — all blocked; only E2
  survives.** The sparse decode layer is a 7-edge / 10-dispatch chain
  `down+residual(prev) —E1→ inputNorm —E2→ qkv —E3→ attn —E4→ o_proj —E5→
  postNorm+router —E6→ shared_swiglu —E7→ down+residual`. **E1** requires
  cross-threadgroup FP atomics (not bit-exact). **E3** is geometrically
  incompatible (5120×64 against 32×1024). **E4/E5** is C2′, already recorded as
  BLOCKED. **E6** pits a 32-TG × 512-thread router against a 256-TG × 64-thread
  shared gate/up. **E2 is the last live on-chain edge and it is assigned as
  #309.**

- **⭐⭐ There is no C3/C4/C5 re-pricing bonanza.** #298's headline
  "−2.2 to −2.5 µs per removed dispatch" is really **per removed
  (dispatch + barrier) pair on the SERIAL chain**. Off-chain removals — C3, C4,
  C5, all with Δbarriers = 0 — stay at the §4.16 dispatch-only rate of
  ≈0.12 µs × 1.8 ≈ **8.6 µs/step across 39 layers, not 86–98 µs**. PR #204's
  null (ΔD = −0.9 ± 12.1 µs) is fully consistent with that. ⇒ standing rule 27.

**Closed in round 29 (2026-08-07):**

- **`compiled{}` elementwise decode fusion — CLOSED (#269), N = 0 is structural.**
  The default decode path issues 406 dispatches/step with **zero**
  `binary*`/`unary*`/`ternary*`/`copy*` families, and MLX's `is_fusable`
  (`compile.cpp:77-79`) covers only unary/binary/ternary/broadcast. Custom, Gather,
  Reduce/ArgReduce and `fast::RMSNorm` are all ineligible. There is nothing for
  `compiled{}` to fuse — this is a property of the graph, not of the attempt.
  Reopening requires first *creating* eligible elementwise segments, which is the
  opposite of the dispatch-count objective. Details in §4.14.
- **The prefill "glue" class as a *time* target — CLOSED (#270).** elementwise +
  moe_tail + qk_norm_rope + rms_norm + router run at **~99% of their 7.94 ms DRAM
  bandwidth floor**. Scheduling, fusion, and geometry changes have ~0.10 ms of total
  headroom between them. **Only byte elimination can move this class.** This also
  **retires `PREFILL_NAX_ANALYSIS.md` H4 as a time target.** Details in §4.13.
- **E1 — "the per-dispatch tax is CPU graph-eval/encode starvation" — REFUTED (#269).**
  Δ(inter-kernel gap) = 1 µs against Δ(GPU-busy union) = 139 µs, the latter matching
  the ABBA step-time effect to 0.4σ; the gap is *anti-correlated* with dispatch count.
  The refund is GPU-side. Consequence: **the ICB / encode-overlap pivot is unlikely and
  hand-fusing kernels is the likely-correct lever.** E2/E3/E4 remain open (#268).
- **E5 (command-buffer commit cost) — re-closed independently (#269).** Command-buffer
  count stayed at exactly **45** across arms with 406, 562, and 679 dispatches/step,
  reproducing the #241 MAX_OPS null by a different route.
- **Decode-GEMV threadgroup-occupancy starvation — CLOSED (§4.10b).** 5120
  threadgroups against ~40 cores. §4.10a mechanism (a) is withdrawn; do not assign it.
- **`uint2` → `uint4` load widening in the decode GEMVs — CLOSED (§4.10b), not
  bit-exact.** It repartitions per-lane serial float accumulation before `simd_sum`,
  and 32 lanes already cover a contiguous 256 B burst, so there is no bandwidth case
  either.

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

   > **SUPERSEDED (2026-08-07)** by
   > [`maple-byte-recovery-census-2026-08-07.md`](maple-byte-recovery-census-2026-08-07.md).
   > The candidate list here is partly wrong (`.metal` "duplicates" recover 0 B;
   > BK128 is 2,693 B). The per-file-cap instinct in the last three sentences is
   > **right and is now the census's headline**: relocating 172,594 B of
   > measurement narrative out of four `Sources/MLXFastModel/*.swift` files into
   > non-editable `notes/` is both the largest global lever and the only one that
   > relieves `LagunaRuntimeModel.swift` (now 468,336 B, 55,952 B of file headroom).
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

**✅ ANSWERED 2026-08-07 (§4.10b census) — H5 IS ALIVE.** The free experiment is
done and the pruner does **not** prune payload bytes. Decode takes the `refine`
arm (`useFusedRefinement: inputs.dims(1,1)`, `LagunaRuntimeModel.swift:10977`;
`lagunaLmHeadFusedRefinementEnabled` default ON,
`LagunaLmHeadPrune.swift:95-98`), which issues four dispatches in
`LagunaLmHeadPruner.logits` (`:1090-1168`):

| # | kernel | grid / tg | weight bytes read |
|---|---|---|---|
| 5a | `laguna_lmhead_int5_base_coarse_delta_bf16_v1` (`:266`, src `:269-323`, dispatch `:1107-1113`) | 3,211,264 / 512 → 6272 TGs × 16 simdgroups, 1 row/simdgroup | **109,182,976 B = 104.1 MiB** — the entire coarse plane, unconditionally |
| 5b | `laguna_lmhead_coarse_argmax_stage1_v5` (`:350`, dispatch `:1123-1129`) | (224,128,1) / 224 → 28,672 threads | none (reads 401,408 B of `coarse`) |
| 5c | `laguna_lmhead_exact_winner_bf16_midpoint_threshold_v1` (`:436`, dispatch `:1130-1136`) | (32,1,1) / 32 | exactly one BF16 row = 4096 B (`:479`) |
| 5d | `laguna_lmhead_exact_fused_int5_sparse_refine_v1` (`:662`, src `:667-818`, dispatch `:1153-1159`) | 802,816 / 256 → 3136 TGs × 8 simdgroups, fixed 4-row block | data-dependent; file comment `:63-67` says live blocks are "single digits per step" ⇒ O(10 KB) |

So **all** pruning is downstream of the payload read: 5a streams every row's
1024 B of codes and 64 B of e8m0 scales *before* anything is screened. The
100,352-row coarse plane is the single largest weight read in the decode step,
larger than attention QKV (10.0 MiB) or the routed top-8 gate/up (8.0 MiB) by
an order of magnitude.

**Why this now outranks everything else in the decode queue.** §4.10a showed
that decode is bandwidth-bound at θ ≈ 0.71 with a hard practical ceiling near
0.85, so every other decode idea competes for a 14-point θ band and is capped
by it. H5 does not touch θ at all — it **reduces B**, and B has no ceiling.
It is the one place in the decode step where the byte total is not pinned,
because greedy argmax makes provably sound row pruning legal. Re-priced against
the measured 104.1 MiB rather than the old 134.9 MB estimate: at 1–5 %
survivors ≈ **−71 MB ≈ 163 µs/step ≈ +2.5 % score**, roughly 2× the ~80 µs
single-arm bar and ~3.3× the 3σ floor.

Risk: the soundness proof must be against the kernel's *float* arithmetic; flat
logit tails gut the prune rate; the two-phase structure adds ~3 µs.
Additional risk now visible from the census: 5a's screen is what makes 5d cheap,
so any scheme that prunes 5a's own reads must keep 5d's survivor set provably
correct — the two are coupled, and a naive "skip rows in 5a" breaks the
certificate that lets 5c/5d touch only a handful of exact rows. The correct
shape is a *cheaper first screen* (coarser plane, hierarchical block norms)
that still certifies the same survivor set, not a truncation of 5a.

**Scope note:** `LagunaLmHeadPrune.swift` is one of the three files no
in-flight assignment touches (§9 of the byte-recovery census), so an H5 arm and
frieren's queued Lever-1 cleanup would collide. Sequence them, or fold the
23,687 B of that file's cleanup into the H5 arm.

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

---

## 12. Arithmetic-killed hypotheses from the 2026-08-07 frontier consult

These were priced and rejected on arithmetic alone, before any code was written.
**Do not assign them.** Recorded so the same ideas are not re-derived.

- **Quantize the dense layer-0 MLP (101 MB/step, ~184 µs floor) or the routers
  (41 MB/step).** Both are outside the permitted precision envelope, and router
  quantization perturbs top-8 selection catastrophically. Dead despite being the
  largest BF16 streams remaining in the step.
- **KV-cache compression (87 MB/step, ~160 µs floor).** Outside the envelope;
  changes numerics.
- **INT8 g32 attention.** 9 bits/weight against the shipped NVFP4 g16's 4.5
  ⇒ **+805 MB/step ≈ +1.5 ms**. Independently re-derives the already-closed
  "2× worse than shipped" result.
- **`uint2` → `uint4` load widening in the decode GEMVs.** Two independent
  reasons: it is **not bit-exact** (it repartitions the per-lane serial float
  accumulation that feeds `simd_sum` — §4.10b), and it saves zero bytes. The
  32 lanes already cover a contiguous 256 B burst, so coalescing is already
  optimal. Superseded by order-preserving multi-row scheduling if that is ever
  wanted.
- **Cross-layer megakernel.** The decode chain is serial; fusing beyond the
  per-layer targets buys the same barrier count at severe register-pressure and
  occupancy risk.
- **Skipping unrouted experts in prefill.** With 512 tokens × top-8 over 256
  experts, `E[unique] = 256·(1 − e^−16) ≈ 256`. **Zero skippable bytes.**
- **Shared-expert conditional skip on a small router weight.** Not bit-exact.
- **Embedding / norm / glue micro-ops.** Under 10 MB and under 20 µs/step
  combined — below the noise floor.
- **Sliding-attention occupancy.** 32 threadgroups looks starved (~4 µs
  floor/layer), but splitting is closed by a prior experiment; and §4.10b shows
  the main GEMVs are not occupancy-starved either (5120 TGs over ~40 cores).

## 13. Advisor operating lessons (process, not physics)

- **⚠️ Every advisor note commit fires one `research_base_changed` event per
  in-flight PR.** With three arms open, one `publish_advisor_branch` generates
  three events. **Batch research-state edits into a single commit** rather than
  publishing incrementally. When the moved base is byte-identical on the scored
  surface — verify with
  `git diff <old> <new> -- Sources/ Vendor/ benchmark.json` returning empty —
  the correct response is **not to re-notify students**: the SHA in their brief
  is still reachable and the scope/budget scripts return identical answers, so a
  fresh SHA costs student attention and buys nothing.
  `accept_result_on_current_base` does **not** apply to these, because `wip`
  assignments have no terminal result to accept. Only re-notify when the scored
  surface actually moved.
- **Give frontier subagents an explicit internal time budget.** The first
  kernel-time consult (`b1dda824`, batch
  `maple-2026-08-07-kerneltime-frontier-consult`) died with
  `TimeoutError: inherited subagent deadline expired` and returned **nothing** —
  a full frontier budget spent for zero output. The retry
  (`bcf59bf9`, batch `maple-2026-08-07-kerneltime-consult-retry`) succeeded only
  because the brief told it to reserve time for writing the report. State the
  deadline in the task text and require an interim conclusion before deep dives.
- **Prefer a corroborating second estimate to a blocking one.** The §4.10a
  1.8064 GB/step figure was derived top-down from θ; the frontier consult
  independently produced ≈1.80 GB bottom-up from the layer inventory. Two
  independent derivations agreeing to three significant figures is stronger
  evidence than one measurement, and it arrived without waiting on a slower
  child.

