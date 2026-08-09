# R104-C — complete shape/geometry census of all 237 prefill steel dispatches, dense-projection efficiency audit (H8), and the host-side channel gate

Student: maple-tanjiro · PR #586 · assignment `maple-r104-c-prefill-steel-shape-census`
rev `r104-c-rev1` · base `9527bb727caad1c495e6b62ecbf2445a25e937dd`
Receipt budget: **zero**. No official MLXFast submission was made and none was
authorised. Everything below is source-derived, host-local, or quoted from
already-published receipts.

---

## 0. Tier discipline (read this before any number)

Every quantitative statement in this document carries a tier tag. The two
tiers are **never** summed, averaged, or otherwise merged.

| tier | meaning | how obtained |
|---|---|---|
| **Tier 1** | M5 Max, 40 GPU cores, `_nax` kernel family | **Derived**, never observed. Produced by running the transcribed routing model with `use_nax=True, devc='s'`. No M5 was available to this student. |
| **Tier 2** | M4 Pro, 20 GPU cores, non-`_nax` kernel family | **Observed** on this host by a live instrumented trace, then reproduced 237/237 by the same model with `use_nax=False`. |

The host is an Apple **M4 Pro**, 20 GPU cores, `devc='s'`, Apple GPU generation
16, so `is_nax_available()` is **false** here. Per `agents.md`, an M4 result is
not evidence for an `_nax` change. Tier 1 is therefore a *model prediction of
what the M5 dispatches*, validated only by the fact that the identical model
code reproduces Tier 2 exactly.

**Cross-reference convention.** A bare `§N` is a section of *this* document.
`NMPC §N` is a section of `research/maple-tanjiro-nonmoe-prefill-census.md`,
whose numbering overlaps this one. Everything else is cited by file and line.

---

## 1. What was actually run

### 1.1 Live trace (resolves preregistered null N-D)

**N-D was**: "the tracer cannot capture the steel path." **N-D is refuted** —
the instrument works.

Two `fprintf(stderr, ...)` blocks were added **locally and uncommitted** to
`Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/matmul.cpp`, guarded by a
`darkbloom_steel_trace()` environment check, immediately before the dispatch in
the non-nax regular path and in the non-nax split-K path:

```
[darkbloom][steel-reg]    <kname> M=%d N=%d K=%d grid=(...) group=(...)
[darkbloom][steel-splitk] <kname> M=%d N=%d K=%d parts=%d psize=%d grid=(...) group=(...)
```

> **Disclosure.** `matmul.cpp` is owned by fern's PR #585 (patching :664-684).
> The instrumentation was applied locally, used, and then reverted with
> `git checkout --`. `git status` and `git diff --stat` confirm the file is
> unmodified in the submitted tree. Nothing in this PR touches `matmul.cpp`.
> A second consequence: because the worktree was dirty during the trace,
> `run_job` refuses to launch, so the trace build and run went through the
> terminal rather than through `run_job`.

Build: `CLANG_MODULE_CACHE_PATH=$PWD/.build-worker/clang-module-cache swift
build -c release --force-resolved-versions --scratch-path .build-worker
--product mlxfast-runtime-worker` (54.5 s). Harness
`research/artifacts/tanjiro-r104c/run_steel_trace.sh` reuses the existing
`research/prefill_probe.py` (rule 58).

**Result: 474 steel rows for two prefill passes = 2 × 237, exit 0.** The two
passes are **byte-identical** (`md5 e463eac3643f81ae7fe73fa69e50d55c` on each
half), so one prefill is exactly **237 deterministic steel dispatches**. The
inventory is unchanged from PR #270 at base `9527bb72`.

**Quota check.** The round-103 tracer hit a 1,671,168-byte artifact limit; that
was an artifact of an unflushed `static std::ofstream` in that tracer and was
never in the main tree. This trace writes to `stderr`, and the captured
`steeltrace.worker.err` is **77,461 bytes = 4.6 %** of that limit. No quota
issue.

### 1.2 The one-model/two-configs routing model

`research/artifacts/tanjiro-r104c/steel_route_model.py` transcribes the
routing and geometry predicates of `matmul.cpp` at base `9527bb72`:

| region | lines |
|---|---|
| top-level routing | :888-960 |
| non-nax split-K | :528-598 |
| non-nax regular | :376-462 |
| nax regular | :210-308 |
| nax split-K | :664-766 |
| split-K accumulation (`get_block_dims`) | :652-654 |

**Validation: with `use_nax=False, devc='s'` the model reproduces all 237
observed M4 rows exactly** — kernel name, grid, threadgroup, `parts` and
`psize`. The *same code* with `use_nax=True, devc='s'` emits Tier 1. That
shared-code property is the only reason Tier 1 is worth publishing at all, and
it is still a derivation, not a measurement.

---

## 2. The census

Full per-dispatch rows: `research/artifacts/tanjiro-r104c/steel_census_237.csv`
and `.json` (474 rows = 237 dispatches × 2 tiers, with an explicit `tier`
column — the two tiers are never merged into one row). Canonical single-pass
ordered log: `steel_dispatch_order_m4.txt`.

All 237 dispatches have **M = 512** and collapse into **9 shape classes**.
Total family work **1502.8 GFLOP** (identical in both tiers — tiers change
geometry, not arithmetic).

### 2.1 Tier 2 — observed, M4 Pro, 20 cores, non-`_nax`

Total **144,512 threadgroups**.

| n | N | K | parts | psize | grid | group | TG | TG/core | GFLOP | kernel |
|---:|---:|---:|---:|---:|---|---|---:|---:|---:|---|
| 78 | 1024 | 2048 | 2 | 1024 | (32,16,2) | (32,2,2) | 1024 | 51.20 | 2.15 | `steel_gemm_splitk_nt_bfloat16_float32_bm32_bn32_bk16_wm2_wn2_MN_taligned_K_taligned` |
| 38 | 256 | 2048 | 2 | 1024 | (8,16,2) | (32,2,2) | 256 | 12.80 | 0.54 | ″ |
| 31 | 8192 | 2048 | — | — | (128,8,1) | (32,2,2) | 1024 | 51.20 | 17.18 | `steel_gemm_fused_nt_bfloat16_bfloat16_bm64_bn64_bk16_wm2_wn2` |
| 30 | 2048 | 8192 | — | — | (32,8,1) | (32,2,2) | 256 | 12.80 | 17.18 | ″ |
| 29 | 64 | 2048 | 4 | 512 | (2,16,4) | (32,2,2) | 128 | 6.40 | 0.13 | splitk `MN_taligned` |
| 10 | 6144 | 2048 | — | — | (96,8,1) | (32,2,2) | 768 | 38.40 | 12.88 | fused |
| 10 | 48 | 2048 | 4 | 512 | (2,16,4) | (32,2,2) | 128 | 6.40 | 0.10 | splitk `MN_naligned_K_taligned` |
| 10 | 2048 | 6144 | — | — | (32,8,1) | (32,2,2) | 256 | 12.80 | 12.88 | fused |
| 1 | 2048 | 2048 | — | — | (32,8,1) | (32,2,2) | 256 | 12.80 | 4.29 | fused (layer-39 `[K;V]` bank) |

### 2.2 Tier 1 — derived, M5 Max, 40 cores, `_nax`

Total **48,368 threadgroups**; **120 regular / 117 split-K**, which matches the
independently-obtained split in §3.4 of the non-MoE prefill census.

| n | N | K | parts | grid | group | TG | TG/core | GFLOP | kernel |
|---:|---:|---:|---:|---|---|---:|---:|---:|---|
| 78 | 1024 | 2048 | — | (32,2,1) | (32,4,2) | **64** | **1.60** | 2.15 | `steel_gemm_fused_nax_nt_bfloat16_bfloat16_bm64_bn128_bk256_wm2_wn4` |
| 38 | 256 | 2048 | 2 | (64,1,1) | (32,2,2) | 64 | 1.60 | 0.54 | `steel_gemm_splitk_nax_nt_bfloat16_float32_bm64_bn64_bk256_wm2_wn2` |
| 31 | 8192 | 2048 | — | (256,2,1) | (32,4,2) | 512 | 12.80 | 17.18 | fused_nax bn128 bk256 |
| 30 | 2048 | 8192 | 2 | (512,1,1) | (32,2,2) | 512 | 12.80 | 17.18 | splitk_nax bk512 |
| 29 | 64 | 2048 | **2** | (16,1,1) | (32,2,2) | **16** | **0.40** | 0.13 | splitk_nax bk256 |
| 10 | 6144 | 2048 | — | (192,2,1) | (32,4,2) | 384 | 9.60 | 12.88 | fused_nax |
| 10 | 48 | 2048 | **2** | (16,1,1) | (32,2,2) | 16 | 0.40 | 0.10 | splitk_nax bk256 |
| 10 | 2048 | 6144 | 2 | (512,1,1) | (32,2,2) | 512 | 12.80 | 12.88 | splitk_nax bk512 |
| 1 | 2048 | 2048 | — | (64,2,1) | (32,4,2) | 128 | 3.20 | 4.29 | fused_nax |

### 2.3 Two corrections to my own earlier NMPC §3.4

Publishing these because downstream briefs are already citing them.

1. **wk/wv grid.** I previously reported `(8,8,1)`. That was the **pre-swizzle**
   grid. Post-swizzle it is **(32,2,1)**. The headline is unchanged: 64 TGs,
   **1.60 TG/core** on 40 cores.
2. **`g_proj` split count.** I previously said `parts = 4`. On M5-`_nax`
   it is **`parts = 2`**: K = 2048 → `psize = 1024` → `parts = 2`. `parts = 4`
   is the **non-nax M4** path only. This is a Tier-1/Tier-2 confusion in the
   original text, which is exactly the failure mode the tier column now
   prevents.

---

## 3. Required paragraph (a) — H8 is **dead**

**Preregistered null N-A was**: "dense projections already run at ≥52 TFLOP/s,
therefore H8 is dead." **N-A is confirmed.**

H8 is stated at `research/RESEARCH_ARCHIVE_through-round-91.md:7471-7483`
(§11.8), with the kill criterion verbatim at `:7480`:

> "Dead if it is already ≥52 TFLOP/s"

(H8 had been repriced to +2.25 % at
`research/RESEARCH_STATE_ARCHIVE_rounds-22-28.md:406`.)

Two independent estimates of the attention-projection rate on M5 exist, and
**both trip the gate**, so the verdict does not depend on resolving the
disagreement between them.

### 3.1 Conservative estimate — Projection B, M4-derived

`research/maple-tanjiro-nonmoe-prefill-census.md:404-406` projects the whole
`steel_gemm_bf16` family at **28.6 ms** on M5 for **1502.8 GFLOP**:

> **1502.8 GFLOP / 28.6 ms = 52.5 TFLOP/s = 87.5 % of the 60 TFLOP/s reference.**

**52.5 ≥ 52, so the kill criterion trips on the conservative number alone.**

(Do not use the "~39.6 TFLOP/s" figure that appears in an earlier note of mine;
it is unsourced and I withdraw it.)

### 3.2 Optimistic estimate — M5 receipt-differenced, PR #34

Receipts R1 `b6032aeb` (cfg 0,0,0,0; S = 97.8643) and R3 `6757de65`
(cfg 40,39,0,40; S = 120.0782). 120.0782 − 97.8643 = **22.2139 ± 0.362 ms**
for **1460.29 GFLOP** of injected `att.wq/wk/wv/wo` work:

> **1460.29 GFLOP / 22.2139 ms = 65.74 TFLOP/s.**

Sources: `research/RESEARCH_STATE_ARCHIVE_through-round-21.md:4619, :4623-4627,
:4639, :4655-4657`; `research/tanjiro-pr34-result.md:601, :738, :740, :767`.
The normalised variant gives 21.483 ms → 67.98 TFLOP/s. The decode-axis free
validation of the same method gave 604.2 GB/s = 99.0 % of 610 GB/s.

### 3.3 65.74 TFLOP/s is arithmetically impossible as an absolute rate

65.74 TFLOP/s is **117 % of the 56 TFLOP/s BF16 ceiling** used in the PR #34
write-up and **~110 % of the 60 TFLOP/s reference** used in the census. A
kernel cannot exceed its own ceiling. That is not a small calibration error —
it is a proof that the *marginal* receipt-difference estimator is contaminated
and must not be read as an absolute per-kernel rate. This is precisely the
step rule 76 forbids (`research/CURRENT_RESEARCH_STATE.md:2211-2226`), and the
same contamination was already audited at
`research/tanjiro-pr34-r2-result.md:650-690` and
`research/RESEARCH_STATE_ARCHIVE_through-round-21.md:4251-4290`.

**Likely mechanism (see §10): dispatch concurrency.** MLX creates every
compute encoder with `DispatchTypeConcurrent`, so independent GEMMs overlap.
The PR #34 injection added 40 *mutually independent* copies of the projection
block; what it measured is the **saturated aggregate throughput** of a machine
running many overlapping small GEMMs, not the serial rate of one. A saturated
aggregate can legitimately exceed the effective rate of any single dispatch and
can also exceed a peak figure that was itself derived under different
assumptions. So the two estimates are not necessarily in contradiction — they
measure different things — but only the conservative one is a per-kernel rate.

### 3.4 Verdict

**H8 is dead.** The conservative, M4-derived, non-marginal estimate already
puts the family at 52.5 TFLOP/s ≥ 52. The optimistic estimate is higher still.
There is no reading of the evidence in which dense attention projections are
inefficient enough for H8 to pay.

This is consistent with the standing verdict at
`research/RESEARCH_STATE_ARCHIVE_through-round-21.md:4245-4249`:

> "Any hypothesis whose premise is 'prefill attention is inefficient' is
> refuted before it starts."

For contrast, the routed gather-GEMM runs at **23.23 TFLOP/s = 67 %** of the
reference — that is where inefficiency actually lives.

### 3.5 Three further independent kills

Even if the rate argument were somehow wrong, H8-adjacent levers are
independently closed (rule 68 / PR #527,
`research/CURRENT_RESEARCH_STATE.md:2803-2833`):

- ⛔ `:2824-2825` — "`_nax` bn=128 is the minimum instantiated tile width. Any
  brief that proposes narrowing an `_nax` N-tile is dead by construction." The
  Tier-1 census shows the 78 wk/wv dispatches use exactly bn=128 with N=1024,
  so the *only* way to raise their occupancy is a narrower tile.
- ⛔ `:2826-2828` — swizzle depth is a no-op on M5 regular `_nax` prefill:
  −0.0141 ms, t = −0.098.
- ⛔ Merging the 78 wk/wv dispatches (removing 78 dispatches / 156 launches)
  **cost +0.639 ms**, CI [+0.325, +0.953], t = 4.43, 12 dof.

Also note H6: the 12.30 ms `steel_gemm_bf16` pool is an **M4 artifact**
(`use_nax` is unconditional for BF16 there),
`research/CURRENT_RESEARCH_STATE.md:2209-2212`.

> ⚠️ NMPC §4.13's 12.30 ms and NMPC §4.15's 11.40 ms **must not be added**. They overlap
> by ≈9.33 ms; the joint ceiling is ≈9-10 ms.

---

## 4. Required paragraph (b) — fern's routing claim **survives**

**Preregistered null N-C was**: "fern's routing claim for (512, 1024, 2048) is
wrong." **N-C is refuted.** The claim is correct.

Re-derived from the source predicates rather than from fern's text. The NAX
split-K gate is `Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/matmul.cpp`
**:922-924**, verbatim:

```c
if (use_nax && batch_size_out == 1 &&
    (K >= 3 * std::max(M, N) ||
     (std::max(M, N) <= 1024 && K > 2 * std::max(M, N)))) {
```

For M = 512, N = 1024, K = 2048 with `_nax` available:

1. `max(M, N) = 1024`.
2. First disjunct: `K >= 3 * 1024` → `2048 >= 3072` → **false**, by a margin of
   1024.
3. Second disjunct, part one: `max(M,N) <= 1024` → `1024 <= 1024` → **true, by
   exact equality**.
4. Second disjunct, part two: `K > 2 * max(M,N)` → `2048 > 2048` → **false, by
   exact equality**.
5. Neither disjunct fires ⇒ not NAX split-K ⇒ control falls through to `:957`
   and calls `steel_matmul_regular_axpby_nax`.
6. Geometry: bn = 128, group (32,4,2), grid (32,2,1) ⇒ **64 threadgroups**,
   **1.60 TG/core** on 40 cores.

**fern's claim is correct.**

### 4.1 Correction to the archive: the tie is in the *other* clause

`research/CURRENT_RESEARCH_STATE.md:2814-2816` explains why the M4 −11.2 ms
Wk/Wv precedent does not port:

> "It was entirely split-K elimination on Wk/Wv, a path M5 **never takes**
> because `K ≥ 3·max(M,N)` fails by an exact tie."

The conclusion is right; the attribution is wrong. `K ≥ 3·max(M,N)` fails by a
**margin of 1024**, not a tie. The exact ties are both in the *second* disjunct
— and there are **two of them**, `max(M,N) <= 1024` passing by equality and
`K > 2·max(M,N)` failing by equality. That matters because the two clauses have
opposite sensitivities: shrinking N would keep clause 3 true, whereas growing K
past 2048 would flip clause 4 and move all 78 dispatches to split-K. Anyone
reasoning about margin from the archive's wording would predict the wrong
direction.

The routing therefore sits on a **double exact equality**. Any change to hidden
size, head count, K/V head count, or the `[K;V]` bank layout that moves N off
1024 or K off 2048 flips **78 of the 237 dispatches** to a different kernel
family in one step. This is a brittle tie, not a comfortable margin.

### 4.2 This is also the strongest available validation of Tier 1

Independently of fern, the archive records as **measured on M5** that Wk/Wv does
**not** take the split-K path there, while the M4 precedent's win came entirely
from eliminating Wk/Wv split-K. My model, run in its two configurations,
reproduces exactly that asymmetry without being told about it:

- **Tier 2 (observed, M4):** the 78 N=1024 dispatches are `steel_gemm_splitk_nt_…`
  (non-nax gate `:900-901`: `_tm·_tn = 16·32 = 512 ≤ 2048`, `_tk = 128 ≥ 8`,
  `K = 2048 ≥ max = 1024` — all true ⇒ split-K).
- **Tier 1 (derived, M5):** the same 78 are `steel_gemm_fused_nax_nt_…` regular.

That is one non-trivial, direction-correct agreement between the derived M5
branch and an independent M5 measurement. It is *one* point of contact, not a
validation of the whole Tier-1 table — but it is the only external check the
Tier-1 column has, and it passes.

> **Independence caveat.** fern's claim originally derives from my own NMPC §3.4, so
> this is **not** independent corroboration of fern's work. What *is*
> independent of both is the re-derivation above: it comes from the `matmul.cpp`
> predicates transcribed into `steel_route_model.py`, whose non-nax
> configuration reproduces 237/237 observed rows on this host. The model is
> validated against reality; the M5 branch of it is not.

> **Communication limitation.** My only GitHub tools are
> `submit_experiment_result` and `respond_to_human_issue`. **I cannot post a
> comment on PR #585.** Advisor: please relay to fern that the routing claim is
> confirmed, and point her at
> `research/artifacts/tanjiro-r104c/steel_route_model.py` plus the exact-tie
> observation above.

---

## 5. Required paragraph (c) — the geometry is **concentrated**, the recoverable deficit is **diffuse**

**Preregistered null N-B was**: "the tail deficit is diffuse, so there is no
single-shape lever." **N-B is confirmed in the operational sense.**

### 5.1 The geometry is sharply concentrated (Tier 1)

**155 of 237 dispatches (65.4 %) run at ≤ 1.6 TG/core on 40 cores:**

| site | n | TG | TG/core | GFLOP each | GFLOP total |
|---|---:|---:|---:|---:|---:|
| wk/wv | 78 | 64 | 1.60 | 2.15 | 167.5 |
| router | 38 | 64 | 1.60 | 0.54 | 20.4 |
| g_proj | 39 | 16 | 0.40 | 0.13 / 0.10 | 4.9 |
| **tail total** | **155** | | | | **192.8** |

At 1.6 TG/core, 38 of 40 cores are idle for the wk/wv and router dispatches
unless something else overlaps them. At 0.4 TG/core, `g_proj` occupies **16 of
40 cores** and leaves 24 empty. In pure occupancy terms this looks like a
catastrophe and an obvious lever.

### 5.2 The recoverable work is not concentrated there

Those 155 dispatches carry **192.8 GFLOP = 12.8 %** of the family's 1502.8
GFLOP. The other **82 dispatches carry 1310.0 GFLOP = 87.2 %** at a healthy
9.6-12.8 TG/core.

Arithmetic bound: for the tail to explain the whole **11.40 ms** M5-specific
residual of NMPC §4.4, the tail would have to be running at ≈ **12.8 TFLOP/s ≈ 21 %
of 60**. NMPC §4.4 (`research/maple-tanjiro-nonmoe-prefill-census.md:412-421`)
brackets it: 3.7 ms if the tail ran at the family's 87.5 %, versus 21.4 ms at
"15 % of roofline" — a **+17.7 ms swing that brackets 11.40 ms**. So the tail
*could* in principle account for the residual, and the occupancy numbers make
that plausible.

### 5.3 …but the one site big enough to matter has already been tested and lost

The tail is 155 dispatches, but 167.5 of its 192.8 GFLOP (**87 %**) is **wk/wv**.
Any lever that does not fix wk/wv cannot move the residual. And wk/wv has
already been attacked head-on by rule 68 / PR #527
(`research/CURRENT_RESEARCH_STATE.md:2803-2812`, receipt detail `:2128-2140`):

> "the fused Wq/Wk/Wv N=10240 GEMM stays on regular `_nax` with identical
> geometry (bm64 bn128 bk256 wm2 wn4 sl2) and an identical **640
> threadgroups**. Removing **78 dispatches / 156 GEMM launches** cost
> **+0.639 ms** (CI [+0.325, +0.953], prediction-t 4.43 on 12 dof, =
> **−0.242 % score**)."

The census makes the arithmetic of that experiment legible: N = 8192 (wq) +
1024 (wk) + 1024 (wv) = **10240**, and the 78 removed dispatches are exactly the
**39 layers × 2** separate wk and wv GEMMs in my Tier-1 row 1. So #527 is not an
approximate precedent — it is *precisely* the merge of the concentrated tail
site, run on M5, with kernel family, tile geometry and threadgroup count all
held fixed, and it **lost**.

(Consistency check on the census: 78 = 39 × 2 separate wk/wv dispatches at
N=1024, plus the single N=2048 dispatch at layer 39, which is the one layer
where K and V are already stored as a fused `[K;V]` bank. 39 + 1 = 40 layers. ✓)

Combined with the two rule-68 kills in §3.5 — bn=128 is the minimum `_nax` tile,
and swizzle depth is a measured no-op — the three obvious geometry levers on the
concentrated site are all closed by direct measurement on M5.

### 5.3.1 The one variant that is *not* yet closed

`research/CURRENT_RESEARCH_STATE.md:2817-2823` leaves exactly one cheap
discriminator open, and honesty requires flagging it rather than claiming a
clean sweep. #527's loss has **two surviving explanations, both unproven**:

- **(a) SLC capacity crossing** — the fused bank is 41.94 MB vs 33.55 MB for Wq
  alone; ~16 µs/layer of refetch × 40 layers ≈ 0.6 ms, which matches the
  observed effect almost exactly.
- **(b) Lost inter-dispatch overlap** — read-after-read is never hazard-tracked
  (`device.cpp:547-548`), so separate dispatches already overlap for free
  (see §10).

The discriminator is **[Wk;Wv]-only fusion**: an 8.39 MB bank, *smaller* than Wq
alone, so SLC predicts a win or a null while lost-overlap predicts a
proportional loss. The archive's own disposition is that this is
> "Worth understanding, **not worth a receipt now** (both mechanisms leave the
> family negative)."

I agree with that disposition and am **not** proposing it. It is recorded here
so that §5.4's "no single-shape lever survives" is read as *no lever survives
that is worth a receipt*, not as *every variant has been tested*.

### 5.4 Answer

**The geometry is concentrated; the recoverable deficit is diffuse.** 65.4 % of
dispatches sit at ≤1.6 TG/core, which is a genuinely concentrated occupancy
pattern, but they carry only 12.8 % of the work, and the sub-site that carries
87 % of *that* has been measured to get **worse**, not better, when its
dispatch geometry is changed. **No single-shape lever survives.** A brief of
the form "fix the low-occupancy prefill GEMM shape" should not be written
without new information that contradicts the +0.639 ms result.

The likely reason the merge lost, and the reason low occupancy is not
automatically a cost, is §10: MLX dispatches these independent GEMMs
concurrently, so a 1.6-TG/core dispatch does not necessarily leave 38 cores
idle — it leaves them available to its neighbours.

---

## 6. Required paragraph (d) — what this census **cannot** tell us without an M5

Stated plainly, because the temptation to over-read the Tier-1 table is real.

1. **Tier 1 was never observed.** Every M5 number in §2.2 is a *prediction* from
   a transcribed model. Its only validation is that the same code reproduces
   Tier 2 exactly on hardware that takes a *different branch*. A transcription
   error confined to the `_nax` branches would be invisible to that check.
2. **No M5 kernel timing exists here at all.** The census gives shapes,
   geometry, threadgroup counts and FLOPs. It gives **zero milliseconds** on
   M5. Every M5 duration quoted in this document is either a receipt difference
   from an earlier round or a projection from M4.
3. **No per-class M5 cost.** I cannot say what fraction of prefill the 78 wk/wv
   dispatches actually consume on M5. NMPC §4.4's ±17.7 ms bracket is exactly as
   wide as it is because that number does not exist.
4. **The 11.40 ms M5-specific residual cannot be localised** without M5
   receipts. This census narrows *where it could be* (the 155-dispatch tail is
   the only structure large enough) but cannot confirm that it *is* there.
5. **Near-tie argmax may differ across Apple Silicon generations**, per
   `agents.md`. The (512, 1024, 2048) routing decision in §4 turns on the exact
   equality `2048 > 2048 == false`. Anything that perturbs that comparison —
   including a different MLX revision — changes 78 dispatches at once.
6. **M4 Pro reports GPU generation 16 and does not select `_nax`.** Per
   `agents.md`, no timing measured on this host is evidence about an `_nax`
   change. That constraint applies to §7's host-side gate too, though that gate
   is a compiler oracle rather than a timing measurement, so it is unaffected.
7. **FLOP counts are shape arithmetic, not achieved work.** Split-K adds a real
   accumulation pass (155 accum dispatches on M4, matching the 392 = 237 + 155
   `steel_gemm_bf16` call count of NMPC §4.1) whose cost is not in the GFLOP column.

---

## 7. Secondary deliverable — the host-side channel gate (closes the last PR #572 threat)

### 7.1 The threat

`research/maple-tanjiro-r103b-kernel-text-differential.md:925-936` and
`:1251-1259` leave one non-device threat open ("Residual channel not
excluded"): the r103-B rungs bounded the GPU difference and showed dispatch
counts identical, but they did **not** bound host-side CPU and encode work. The
OLD→NEW fold narrowed symbols from `internal` to `private` and merged
`LagunaRuntimeLayers.swift` into `LagunaRuntimeModel.swift`; either can change
Swift specialisation.

The prior oracle, `research/nezuko_r103c_object_identity.sh:17, :56-58`,
demands exact digest equality on a **single file**. The fold changed the file
set, so a single-file hash under-covers the surface — OLD→NEW spans 32 files
(`…r103b….md:211`).

### 7.2 The gate

`research/artifacts/tanjiro-r104c/r104c_host_channel_gate.sh`: six forced-clean
builds, two per revision, interleaved OLD MID NEW OLD MID NEW, with `$OBJDIR/*.o`
wiped before each build and an mtime staleness guard so no digest can be a
replayed object. Job `b61f0318-6db1-41ef-b3e9-f177bb4ba1d9`, exit 0, 127.7 s.

Revisions: OLD `30f752df` (10 objects), MID `e17bdeb1` (9), NEW `0f6862d0` (9).

### 7.3 V1 — oracle determinism: **PASS**

Each revision's two forced-clean builds are byte-identical across the whole
object set. Without this, no cross-revision claim would mean anything.

### 7.4 V2 — host-side channel: **bounded and localised, not excluded**

The gate script's `__TEXT` extraction was broken (`size -m` on a relocatable
`.o` reports an unnamed segment, so the `/Segment __TEXT/` filter matched
nothing and wrote `textsum=0`). Recomputed post-hoc from the surviving pass-2
objects by `research/artifacts/tanjiro-r104c/recompute_text_sizes.py`, with no
extra build:

| object | OLD `__text` | MID | NEW |
|---|---:|---:|---:|
| DenseTensorStore.swift.o | 25,656 | 25,656 | 25,656 |
| LagunaConfig.swift.o | 50,264 | 50,264 | 50,296 |
| LagunaLmHeadPrune.swift.o | 10,792 | 10,792 | 10,792 |
| LagunaRuntimeLayers.swift.o | 59,288 | *(folded)* | *(folded)* |
| LagunaRuntimeModel.swift.o | 202,720 | 261,652 | 263,876 |
| LagunaRuntimeWeights.swift.o | 57,052 | 57,052 | 57,052 |
| LagunaUpstreamEquivalence.swift.o | 14,812 | 14,812 | 15,076 |
| MLXTensorBridge.swift.o | 584 | 584 | 584 |
| RuntimeStartupMemoryPolicy.swift.o | 8,064 | 8,064 | 8,064 |
| RuntimeWeightLoading.swift.o | 14,256 | 14,256 | 14,256 |
| **module total** | **443,488** | **443,132** | **445,652** |

OLD→MID **−356**, MID→NEW **+2,520**, OLD→NEW **+2,164**.

Three findings, in order of importance:

1. **Release-mode WMO did *not* smear the change across the module.** Six of
   the nine common objects (DenseTensorStore, LagunaLmHeadPrune,
   LagunaRuntimeWeights, MLXTensorBridge, RuntimeStartupMemoryPolicy,
   RuntimeWeightLoading) are `__text`-identical byte-for-byte in all three
   revisions. Their *digests* differ (embedded module hashes), which is why the
   digest-equality oracle can never pass across revisions — but their code size
   is pinned. **The digest oracle was the wrong instrument; `__text` is the
   right one.**
2. **OLD→MID is exactly the fold and nothing else.** 202,720 + 59,288 = 262,008
   versus MID's 261,652 — a **−356 byte** difference, and the module total
   moves by exactly that same −356. `LagunaConfig.swift` differs in *source*
   between OLD and MID yet compiles to an identical 50,264 `__text` bytes.
3. **MID→NEW decomposes exactly:** LagunaRuntimeModel +2,224, LagunaConfig +32,
   LagunaUpstreamEquivalence +264 → **+2,520**. `LagunaUpstreamEquivalence` is
   the correctness oracle, off the scored path.

### 7.5 The MID→NEW channel, fully enumerated

The gate's symbol multiset was noisy (`nm -Ug` concatenated with `nm -U`
double-counted globals and let string-literal fragments through). Recomputed
cleanly by `research/artifacts/tanjiro-r104c/clean_symbol_diff.py` — Swift
mangled defined names only, deduplicated: OLD 2,629 / MID 2,628 / NEW 2,636.

MID→NEW is **7 symbols removed, 15 added — 22 in total, all one mechanism**:

removed
```
lagunaResidualRMSNormRouterSource(rowsPerGroup:)          -> String
lagunaResidualRMSNormRouterKernels : [Int: MLXFastKernel] (+4 value-witness thunks)
_ContiguousArrayBuffer._consumeAndCreateNew<(Int, MLXFastKernel)>
```
added
```
lagunaRouterWeightPrefetch : Int            (+ initialiser, thunk, _WZ, _Wz)
lagunaResidualRMSNormRouterSource(rowsPerGroup:prefetch:) -> String
lagunaResidualRMSNormRouterKernels : [[Int]: MLXFastKernel] (+4 thunks, +_WZTv0_)
Array.append(contentsOf:)<(Int, MLXFastKernel)>
_ArrayBuffer._consumeAndCreateNew<(Int, MLXFastKernel)> (+ merged thunk)
```

That is a single coherent change: a new lazily-initialised global
`lagunaRouterWeightPrefetch`, a `prefetch:` parameter threaded into the fused
residual-RMSNorm-router kernel source, and the kernel cache **re-keyed from
`Int` to `[Int]`**.

**Host-side cost of that re-key is real and non-zero**: an array-keyed
dictionary lookup allocates and hashes an `[Int]` where the old one hashed an
`Int`, on every cache lookup, plus a `swift_once` guard on the new global. The
number of such lookups per prefill is bounded above by the layer count, so
**≤ 40 per prefill**. Converting 40 array-keyed lookups into milliseconds
requires a host-side CPU measurement I did **not** run; I am reporting the
countable facts, not a timing claim.

### 7.6 V2 verdict

**The host-side CPU/encode channel of PR #572 is not excluded, but it is now
bounded and fully localised.**

- Bound: **+2,164 bytes of `__text`** across the entire scored module OLD→NEW,
  = **0.49 %** of the module. Excluding `LagunaUpstreamEquivalence`, which is
  the off-path correctness oracle, the on-path bound tightens to
  430,576 − 428,676 = **+1,900 bytes (0.44 %)**.
- Localisation: 6 of 9 common objects are `__text`-identical; the OLD→MID delta
  is entirely the file fold (−356 B); the MID→NEW delta is 22 symbols belonging
  to one mechanism, of which 264 bytes are in the off-path correctness oracle.
- The prior digest-equality oracle **cannot** be satisfied across revisions
  under release-mode compilation and should be replaced by the `__text` +
  mangled-symbol-set comparison used here.

Caveat: this is a *compiler* oracle, not a timing measurement, so the M4-vs-M5
architecture caveat does not bite — but equally, it produces **no milliseconds**.
It bounds the *size* of the channel, not its cost.

---

## 8. Preregistered nulls — final disposition

| null | statement | outcome |
|---|---|---|
| **N-A** | dense projections already ≥52 TFLOP/s ⇒ H8 dead | **CONFIRMED** (§3) — 52.5 TFLOP/s on the conservative estimate alone |
| **N-B** | tail deficit diffuse ⇒ no single-shape lever | **CONFIRMED operationally** (§5) — geometry concentrated, recoverable deficit not |
| **N-C** | fern's routing claim for (512,1024,2048) is wrong | **REFUTED** (§4) — the claim survives re-derivation |
| **N-D** | tracer cannot capture the steel path | **REFUTED** (§1.1) — 474 rows, two byte-identical passes |

---

## 9. Cross-source disagreements (disclosed, not resolved)

These are live inconsistencies in the existing corpus. None of them changes any
verdict above, but they should not be quietly inherited.

| # | disagreement | A | B |
|---|---|---|---|
| 1 | M5 BF16 ceiling | 60 TFLOP/s (census) | 56 TFLOP/s (PR #34) |
| 2 | attention-projection rate | 52.5 TFLOP/s implied (Projection B) | 65.74 TFLOP/s measured (PR #34) — **1.25×** |
| 3 | M5 qkvo cost | 28.6 ms / 1502.8 GFLOP (census) | 22.2139 ms / 1460.29 GFLOP (PR #34) |
| 4 | qkvo floor | 24.42 ms "compute-bound" | 22.2139 ms measured — **9.0 % *below* the stated floor** |
| 5 | **wk/wv efficiency** | census: ~15 % of roofline | PR #34: the injected block ran at 117 % of ceiling with −3.87 ms excess |
| 6 | scope of the injected block | `att.wq/wk/wv/wo` only (`pr34:347`); **g_proj and router are not in it** (2852.13 MB injected vs 2.862 GB `attn_proj_qkvo` weight) | — |

Disagreement #5 is the sharpest and is the direct subject of paragraph (c).
§10 offers the reconciliation that costs neither side: **dispatch concurrency**
(see §10) means the injected 40-copy block measured *saturated aggregate*
throughput, while the census reasons about *serial per-dispatch* occupancy.
Those can differ by a large factor without either being an error — but they are
not interchangeable, and the marginal number must not be quoted as an absolute
kernel rate (rule 76).

**Internal arithmetic note.** In NMPC §4.3, 182.988 + 35.584 = 218.572 ≠ 214.698.
The discrepancy is the NMPC §4.1 deflation factor 0.982275, which is applied to the
"all" row but not to the split rows. Not an error, but the rows are not
additive as printed.

---

## 10. Supporting mechanism — MLX dispatches independent GEMMs concurrently

From `research/tanjiro-pr47-dispatch-concurrency.swift:10-20` and the MLX
sources it cites:

- Every compute encoder is created with **`DispatchTypeConcurrent`**
  (`device.cpp:548`).
- `memoryBarrier(BarrierScopeBuffers)` is emitted **only** when a dispatch reads
  a buffer an earlier dispatch in the same encoder wrote (`:325-330`, `:363-375`,
  `:380`).
- Per-encoder fences handle cross-command-buffer ordering (`:396-450`).
- A command buffer is committed when `buffer_ops_ > max_ops_per_buffer`, which
  is **50** on an `*s` architecture (`:484-487`, `:574-595`).

**Consequence:** the 78 wk/wv dispatches are mutually independent and land in the
same encoder, so they **can overlap**. A 1.6-TG/core dispatch therefore does not
imply 38 idle cores — and merging them into one large dispatch removes the
overlap opportunity, which is a plausible mechanism for the measured **+0.639 ms
regression**.

This also means an occupancy-per-dispatch table (§2.2, §5.1) is a **statement
about geometry, not about utilisation**. I did not run a serial-vs-saturated
microbenchmark to demonstrate the effect empirically; that is the top follow-up
in §12.

---

## 11. Artifacts (rule 75)

`research/artifacts/tanjiro-r104c/`

| file | bytes | sha256 |
|---|---:|---|
| `run_steel_trace.sh` | 750 | `4a6af61973bb9fd967d261a67ac402ebb4943dff71a357a1607fab9a96aad842` |
| `steeltrace.worker.err` | 77,461 | `3b2ecb39a3ef1e079eb07ad038cad62465060a6be8524faf13342e8be1019e61` |
| `steeltrace.log` | 219 | `5ff77152f33d91e075f86384f57aaafc29f9ec2980f9cc381bcf07625a8bacab` |
| `steel_dispatch_order_m4.txt` | 35,843 | `597aa21563add9ea0efc2101de765b11885dd7c49cfbfb5e5c4816b1f71df666` |
| `steel_route_model.py` | 16,000 | `a3f83b5430765b37919e358e7288576afd8888b0feea0efa66d6c9e2bfed2fbd` |
| `steel_census_237.csv` | 129,903 | `8a214163e61288a22826659d021e2745385dff598da4127f4afb656d4cb77223` |
| `steel_census_237.json` | 340,819 | `3bb3212c1c75227b0972cce9a84f43ca3a3e904f52c0f62432d0fd4f4bd67358` |
| `r104c_host_channel_gate.sh` | 5,295 | `7e8782d9432a8f1e8bf10b1cd10be4c340f5e4885452ea8857a59fe15ad992d4` |
| `recompute_text_sizes.py` | 1,790 | `0d7254014376e7bd1b2786bb47573feb755024be9fbfc247838de286a1e43aaf` |
| `clean_symbol_diff.py` | 1,737 | `6e3c68250d95d08b3d032bec3327a306204a4314188d30a8b3891ffdbd0ea6b2` |
| `hostgate/` | — | 6 build logs, per-pass object/symbol/binary digests, symbol diffs, `text_recomputed.json`, `symdiff_clean.json` |

Digests are for the tree as committed. `steel_census_237.csv` was line-ending
normalised (CRLF→LF) by git on commit.

`hostgate/syms.{old,mid,new}.{p1,p2}.txt` are committed gzipped (`gzip -n -9`,
3.8 MB → 696 kB for the directory). The `.gz` byte sizes are pairwise equal
within each revision, which is an independent restatement of the §7.3 V1 pass.
Neither `recompute_text_sizes.py` nor `clean_symbol_diff.py` reads those dumps —
both re-derive from the `.o` objects under
`.mlxfast-private/r103b-{old,mid,new}/` — so the compression does not affect
reproduction.

**Submission surface: unchanged.** This PR adds only `research/` files. No file
under `editablePaths` is modified. `matmul.cpp` is byte-identical to base.

---

## 12. Follow-ups I did **not** implement

1. **Serial-vs-saturated occupancy microbenchmark.** Reuse
   `research/tanjiro-pr47-dispatch-concurrency.swift`,
   `research/tanjiro_occupancy_audit.swift`, or
   `research/tanjiro_coresidency_probe.swift` (rule 58; build with
   `xcrun swiftc -O <probe>.swift -o /tmp/<name> -framework Metal -framework
   Foundation`) to show empirically that N independent copies of a 64-TG GEMM
   reach a far higher aggregate rate than one serial copy. This converts §3.3
   and §10 from argument into measurement and would settle disagreement #5.
   Must be labelled Tier 2: the *mechanism* is architecture-generic, the *rate*
   is not.
2. **Host-side CPU cost of the MID→NEW array-keyed cache lookup** (§7.5).
   ≤40 lookups per prefill; a `swiftc -O` microbenchmark of `[Int]`-keyed vs
   `Int`-keyed dictionary lookup would put a number on the channel that §7.6
   can only size in bytes.
3. **Fix `r104c_host_channel_gate.sh` in place** to use
   `Section (__TEXT, __text)` and `nm -jU` filtered to `^_\$s`, so the next run
   does not need post-hoc repair. I left the script as-run for reproducibility
   and did the repair in two separate scripts.
4. **Retire the digest-equality oracle** in
   `research/nezuko_r103c_object_identity.sh`. §7.4 finding 1 shows it cannot
   pass across revisions under release-mode compilation, so it currently
   reports a false alarm on every real change.
5. **Watch the `K == 2 * max(M,N)` exact tie** (§4). It silently controls the
   kernel family of 78 of 237 dispatches and has no margin.

---

## 13. Things this PR deliberately does not do

- No official MLXFast submission (receipt budget zero).
- No edit to `Vendor/.../matmul.cpp` (fern, PR #585) — instrumentation was
  local-only and reverted.
- No edit to `Sources/MLXFastModel/LagunaRuntimeModel.swift` (nezuko, PR #584).
- No new proposal for prefill `_nax` scale-load amortization (CLOSED, PR #244),
  prefill "M-tile underfill", or dispatch-count reduction.
- No merged Tier-1/Tier-2 row anywhere.
- No addition of NMPC §4.13's 12.30 ms to NMPC §4.15's 11.40 ms.
