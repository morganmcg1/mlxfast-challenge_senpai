# R110-A — prefill `_nax` arm queue

**For: maple-fern (sole submission driver).**
From: maple-tanjiro, PR #692, branch
`maple-tanjiro/r110-prefill-nax-arm-factory`, revision `r110-a-rev4`.
Assignment base_sha: `30904ecbf180aa05d7ddf5cc957e83155fbfc6f4`.
Campaign submission BASE_SHA: `1bc1c8954147c9e322aad1f3b80bd9fa3c0888d7`.

This deliverable is a **queue of arms**, not a timing result. No local number in
this directory is evidence for or against any arm — see §2.

---

## 0. Bottom line (rev3)

**The firing order is reversed from rev2, and the queue is now two arms.**

| Arm | Disposition | Why |
|---|---|---|
| **A2** — fused-NAX `bn` 128 → 64 **+ `wn` 4 → 2**, prefill `N ≤ 1024` | **FIRE FIRST. Live on this branch head — nothing to apply.** | Bit-exact by construction, AOT-instantiated, one env var for a one-binary paired A/B, and the only arm with a *directly measured* mechanism receipt (fern's 1.4613× packing probe). |
| **A1** — expert down `bn` 64 → 32 | **FIRE SECOND. Patch file `A1-expert-down-bn32.patch`.** | Genuinely never measured, priced 0.195–0.30 %, but not bit-exact-by-construction in the same trivial way and has no mechanism receipt behind it. |
| **A3** — expert gather groups 256 → 128 | **REMOVED from the queue.** | An M5 receipt and a queue simulation both put 256 ahead of 128. Kept in this directory only as a compose-trap warning (§7). |
| **A4** — split-K `partition_size` halving | **DEAD END, documented so nobody re-derives it.** | Not bit-exact; 0.42 ms analytic floor; already ranked last as H5; §99.6 forbids assigning it. |

If fern has exactly one slot for this queue: **fire A2.** It is already the
branch head, so the slot costs one build and zero patch handling.

> **Read §14 before acting on §3.** Advisor R112 (00:22Z) and R113 (00:42Z)
> landed after §3 was written. They **retract** the "~1.4 % deficit to the crown"
> §3 prices against (§14.1) and **invert** §3's landing rule — the binding rule
> is now *"ship on a verified positive or do not ship"*, so a **neutral draw is
> a do-not-land** (§14.2). §14.3 records why A2 cannot satisfy the R113 #5
> two-instrument law even in principle, and §14.4 gives the structural
> one-sidedness argument that stands in for the missing M4 arm.

**Why the order flipped.** rev2 said "fire A1, A2 is a ride-along". Three things
changed that:

1. A2's shipped geometry was corrected (`wn` 4 → 2), which turned it from a
   speculative retile into a **provably bit-exact repacking** of an
   already-AOT-instantiated kernel tuple (§5).
2. Under a leaderboard framing rather than a landing-bar framing, the arm with a
   measured mechanism and a zero-correctness-risk profile is worth more per slot
   than the arm with a larger paper number and no mechanism receipt.
3. A2 costs fern nothing to stage — it is the head — whereas A1 needs a patch
   applied to a fresh branch.

## 1. Base provenance — why the gate evidence still binds

The assignment base is `30904ecb`. The advisor branch has since moved to
`8268f593`, but the **submitted surface did not move**:

```
$ git diff --numstat 30904ecb 8268f593 -- Sources Vendor benchmark.json Package.swift
(empty)
```

So no re-baseline is required, and every gate transcript in `GATES.md` that was
taken against `30904ecb` (or against the earlier surface-identical bases
`adfca1e5`, `9fe37190`, `32665a6b`) measures the same submitted surface. The
older base SHAs are left in the historical transcripts deliberately.

## 2. Read this first — why there is no local number

Every arm here targets **M5-only `_nax` kernels**. This host is `Mac16,11`
(M4 Pro, 48 GB, Apple GPU generation 16) and `is_nax_available()` returns
`false`, so none of the retiled kernels is ever dispatched locally.

Every local gate therefore proves exactly three things — **build soundness,
harness health, and that the non-NAX path is unperturbed** — and nothing else.

The sharpest demonstration of this limit: the **wrong** version of A2 (§5) gated
green here, bit-exact, `max_abs_diff: 0`, indistinguishable from the corrected
version. The local gate had no way to see the defect.

**The local noise floor, stated numerically so nobody mines these logs.** Four
gated trees on this host, all of which dispatch *identical* kernels because
`_nax` is unreachable here, produced:

| tree | prefill s/token | decode s/token |
|---|---|---|
| A1 | 0.001111 | 0.012955 |
| A2 (first gate) | 0.001139 | 0.013032 |
| A1+A2 | 0.001112 | 0.013095 |
| A3 | 0.001117 | 0.013021 |
| A2 (head re-gate, job `d7984b40`) | 0.001121 | 0.012974 |

That is a **2.52 % prefill spread and a 1.08 % decode spread across four trees
whose underlying computation is provably the same**. Any local delta smaller
than that is noise, and the arms' whole predicted effect is an order of
magnitude below it.

The cleanest single line in the table is the pair of **A2 rows: the same arm,
measured twice, 0.001139 then 0.001121 — 1.6 % apart with a byte-identical
submitted surface.** That one comparison bounds this host's repeatability
without needing any cross-tree assumption at all. Note also that A2 showed the
*slowest* prefill of the first four; that was noise, not a signal, and must not
be read as evidence against A2.

To correct an assumption made when this work was assigned: the local gates are
**not** more meaningful for A2 than for A1. A2's
`steel_matmul_regular_axpby_nax` sits behind the same `use_nax` gate
(`matmul.cpp:894-898`).

`MLX_METAL_GPU_ARCH` was **not** set at any point. Forcing `_nax` on M4 is
forbidden by the assignment and was not attempted.

## 3. Landing bar and the reference block — corrected

- prefill elasticity **0.362**; S ≈ **97.9 ms**, so **1 ms ≈ 0.37 % of score**;
- ~~maple's deficit to the crown is **~1.4 % of real speed ≈ 3.8 ms of prefill**~~
  **← RETRACTED, see §14.1. This deficit does not exist.**
- both speedup floors must stay **≥ 0.95**.

Archive reference for candidate `prefill_seconds_per_token`:
**1.87812e-4 ± 2.607e-7 s/token, n = 14.**

Three corrections to how rev2 stated this:

1. **σ is 0.1388 %, not 0.103 %.** `2.607e-7 / 1.87812e-4 = 1.388e-3`. The
   0.103 % label was arithmetically wrong and made the reference look ~35 %
   tighter than it is.
2. **3σ = 0.400 ms of S**, i.e. `3 × 2.607e-7 s/token × 512 tokens = 4.004e-4 s`.
   (Equivalently: below **1.87030e-4 s/token**.) 0.4076 ms is a rounding of the
   same quantity; 0.400 ms is what the stored numbers give.
3. **The absolute level is stale.** All 14 archived receipts predate the current
   executable. Use the archive for the **dispersion** (σ), never for the
   **level**. Anchor the level with a fresh HEAD-of-base draw in the same
   session as the candidate.

**The dead zone, and how to resolve it.** The landing bar is 0.30 ms; 3σ is
0.400 ms. A draw in `[0.30, 0.400)` ms clears the bar but is not a measured win,
which reads like a contradiction. It is not — they are two different decisions
and should be recorded separately:

- ~~**Landing decision.** Land if the paired candidate is **non-negative and
  bit-exact**.~~ **← SUPERSEDED by R113 #4, see §14.2. The advisor will not
  integrate on "no worse" or "looks neutral". Ship on a verified positive or do
  not ship.** Do not act on the struck text.
- **Claim decision.** Only call it a **measured** win at **≥ 3σ (≥ 0.400 ms)**.

A single draw in `[0, 0.400)` ms is therefore "**kept, not proven**". Say it that
way in the note rather than picking one of the two thresholds and discarding the
other. Under R113 that phrase is now a **hold**, not a land: see §14.2 for what
"kept, not proven" is allowed to authorise and what it is not.

For A2, `decode_seconds_per_token` must be **unchanged**; §4 fact 2 shows why
that is now a tautology rather than a check.

## 4. Prefill dense-GEMM census — the map both surviving arms are read against

Traced dispatch counts, per forward pass, `M = 512` throughout. M5 has 40 cores,
so "TG/core" is the occupancy-quantization column that matters.

| count | shape | entry point | TGs | TG/core |
|---|---|---|---|---|
| 78 | wk/wv `N=1024 K=2048` | regular nax | 64 | **1.60** |
| 31 | wq `N=8192 K=2048` | regular nax | 512 | 12.8 |
| 10 | wq `N=6144 K=2048` | regular nax | 384 | 9.6 |
| 1 | layer-39 `[K;V] N=2048 K=2048` | regular nax | 128 | 3.2 |
| 38 | router `N=256 K=2048` | **splitk** nax | 64 | 1.60 |
| 29 | g_proj `N=64 K=2048` | **splitk** nax | 16 | **0.40** |
| 10 | g_proj `N=48 K=2048` | **splitk** nax | 16 | **0.40** |
| 30 | wo `N=2048 K=8192` | **splitk** nax | 512 | 12.8 |
| 10 | wo `N=2048 K=6144` | **splitk** nax | 512 | 12.8 |

**Σ 237 steel dispatches + 117 split-K accumulations, 48,368 threadgroups.**

Three structural facts that repeatedly mislead people, including me:

1. **`N ≤ 1024` in `steel_matmul_regular_axpby_nax` reaches only the 78 wk/wv
   dispatches.** Router and g_proj are also narrow but leave through
   `steel_gemm_splitk_axpby_nax`, whose tile block is separate code at
   `matmul.cpp:665-684`. A2's coverage is **78, not 155**.
2. **Decode reaches zero dense steel GEMMs.** `Matmul::eval_gpu` short-circuits
   at `matmul.cpp:1269-1270` with `if (std::min(M, N) == 1) return gemv(...)`,
   and teacher-forced decode is 128 one-token steps, so `M = 1` always. Any arm
   in `matmul.cpp`'s steel tile selection is **structurally prefill-only**.
   This kills the "A2 decode twin" follow-up that an earlier version of this
   file proposed — there is no decode steel dispatch to retile.
3. **The `steel_gemm_bf16` family already runs at 1502.8 GFLOP / 28.6 ms ≈
   52.5 TFLOP/s, i.e. 87.5 % of a 60 TFLOP/s reference**
   (`research/maple-tanjiro-r104c-prefill-steel-census.md:217`; restated at
   `research/advisor-r104-the-receipt-is-the-instrument.md:1375` and
   `research/fern-r104b-wkwv-tile-regroup.md:1026`). There is roughly 0.2 ms of
   total slack in that budget at realistic efficiencies. Any brief whose premise
   is "prefill matmul is inefficient" is refuted before it starts.

The corollary is the most useful thing in this document: **~27.88 ms (28.5 %) of
prefill is unattributed to dense GEMM at all**
(`research/CURRENT_RESEARCH_STATE.md:123` and `:5163`, sourced from
`research/maple-tanjiro-pr91-prefill-budget-census.md:648,658`). That block —
norms, RoPE, SDPA, routing top-k/sort, gather/scatter, casts, copies,
transposes, sync points — is the only target on the map large enough to cover a
3.8 ms deficit. Every arm in this queue is fishing in the 87.5 %-efficient pond.

> **Do not conflate these two numbers.** 87.5 % is an *efficiency of the dense
> steel family against a hardware reference*. 28.5 % is a *share of the whole
> prefill wall-clock that is not dense GEMM*. They are different scopes from
> different censuses at different granularity, and they are not two views of one
> quantity. The pair is only meaningful as: the dense part is nearly maxed out,
> and the non-dense part is where the unclaimed time lives.

## 5. Arm A2 — FIRE FIRST. Live on this branch head.

**Nothing to apply.** The branch head contains A2 and only A2:

```
$ git --no-pager diff --numstat 30904ecbf180aa05d7ddf5cc957e83155fbfc6f4 HEAD \
    -- Sources Vendor benchmark.json Package.swift
17  0  Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/matmul.cpp
```

`DARKBLOOM_FUSED_NAX_NARROW_BN=0` restores the incumbent, so this is a
**one-binary paired A/B**. JIT-only; no metallib rebuild; no kernel body edited,
so no `mlx-generated/*.cpp` twin needs resyncing.

### 5.1 Geometry, and the direct answer to the `TN == 1` question

The rev3 brief and the 00:22Z comment both flag a risk that A2 lands on the
untested `TN == 1` branch of `tile_matmad_nax`. **It does not.** Verified against
source, not inferred:

| | incumbent | shipped A2 |
|---|---|---|
| tile `(bm, bn, bk, wm, wn)` | `(64, 128, 256, 2, 4)` (`matmul.cpp:213-221`) | `(64, 64, 256, 2, 2)` |
| `SM × SN` = `(bm/wm) × (bn/wn)` | 32 × 32 | **32 × 32** |
| `TN` | **2** | **2** |
| total simdgroups | 512 | 512 |
| threadgroups | 64 | 128 |
| simdgroups / TG | 8 | 4 |
| AOT-instantiated | yes | **yes** (`steel_gemm_fused_nax.metal:23-29`) |

Because `bn` and `wn` are halved **together**, `SN` is invariant, so `TN` is
invariant at 2 and the `TN % 2 == 0` arm of `tile_matmad_nax`
(`kernels/steel/gemm/nax.h:972`ff) is taken in both. The `TN == 1` arm is never
entered.

The advisor's rev3 text describes A2 as `bn = 64` with `wn` left at `4`. That
was the **first, discarded** version, and it is exactly the version that would
have hit `SN = 16`, `TN = 1`, a non-AOT `(64,64,256,2,4)` tuple, and +50 %
per-simdgroup operand traffic. The shipped patch is not that. The correction is
the whole reason A2 was re-gated.

Consequence: A2 is a **pure repacking** — same template, same instruction
sequence per simdgroup, same reduction order, 64 TG × 8 sg → 128 TG × 4 sg. It is
**bit-exact by construction**, and the local gate agrees (`max_abs_diff: 0`).

### 5.2 Rule-83 disclosure — third visit to this site

PR #293 (`DARKBLOOM_STEEL_REGULAR_SKINNY_TILE`, same `bn=64, wn=2`) was
introduced by `c2812d1c`, merged inert via `31f64154`, and removed by `6ada66c9`
("Adopt organizer promoted frontier c5b0a13c as research base", 2026-08-08) with
**zero M5 receipts**; PR #585 / fern R104-B (`DARKBLOOM_NAX_SKINNY_TILE`)
self-retracted a priori, also unmeasured. The campaign replacement rule
(`research/CURRENT_RESEARCH_STATE.md:4120-4130`) rejects narrow-`_nax`-tile
briefs on the measured **+0.639 ms M5 regression from PR #527 (Rule 68)** and on
magnitude. A2 is inside the class that rule names.

Both prior visits died **unmeasured**. That is the argument for firing this one:
the site has consumed two review cycles and produced no M5 datum, and A2 is the
cheapest possible instrument for finally getting one.

### 5.3 Valuation — the advisor's price for A2 is arithmetically impossible

The 00:22Z comment prices A2 at **0.94 %–2.52 % of score**. That cannot be right,
and the ceiling argument is short enough to check by hand:

- 1 ms of prefill ≈ **0.37 % of score** (elasticity 0.362, S ≈ 97.9 ms).
- So 0.94 % ⇒ **2.54 ms**, and 2.52 % ⇒ **6.81 ms**, would have to come out of
  the wk/wv family.
- The **entire** wk/wv family on M5 is **3.922 ms**
  (`research/artifacts/tanjiro-r104c/steel_ms_attribution_m4.json`, bucket
  `K=2048, N=1024`, `n=78`, `m5_proj_b_ms = 3.922`, `gflop = 167.505`,
  `m5_tg_per_core = 1.6`, `deficit_ms = 6.98` on the M4-side column).

So if the wk/wv GEMMs vanished entirely, the score would move **1.45 %**. The
2.52 % figure exceeds the family's total cost by 74 %; the 0.94 % figure requires
capturing **65 %** of the whole family from a packing change.

**Honest ceiling — two independent derivations, both under 0.5 %.**

- *Packing-probe bound.* Fern's probe measures 8 sg/TG at 1.4613× the cost of
  4 sg/TG at fixed total simdgroups, i.e. a **31.6 %** reduction
  (`1 − 1/1.4613`) if the mechanism transferred perfectly to M5:
  `0.316 × 3.922 = 1.24 ms` ≈ **0.46 % of score**.
- *Family-efficiency bound.* Driving the wk/wv slice from its share of the
  87.5 %-efficient family to a 60 TFLOP/s reference is worth **≈ 0.93 ms**
  ≈ **0.35 % of score** (`A2-fused-nax-bn64-n1024.md` §5).

The two disagree because they bound different inefficiencies — 87.5 % is a
family *average* over buckets, and this bucket's 1.6 TG/core occupancy waste is
not visible in that average. Take the ceiling as **0.9–1.24 ms ≈ 0.35–0.46 %**
and note that both bounds are *ceilings*, not estimates.

**Realistic estimate: 0.3–0.8 ms ≈ 0.11–0.30 % of score.** Fern explicitly
refuses to transfer the band location from M4 to M5, and M5's 40 cores move the
occupancy quantum relative to this host, so partial capture is the expectation.

**This does not change the firing decision.** A2 still goes first, because the
argument for it was never its magnitude — it is zero correctness risk, a measured
mechanism, an already-staged head, and a site that has twice been abandoned
unmeasured. But the crown-probability table in the 00:22Z comment should be
re-read at the **+0.4 %** row, not the **+0.94 %** row, and the expected value of
this slot is roughly a third of what was quoted. Everything downstream of that
table that treats A2 as a near-crown-closing move should be discounted
accordingly.

### 5.4 Firing commands

A2 is the head, so there is nothing to stage:

```bash
git fetch origin maple-tanjiro/r110-prefill-nax-arm-factory
git checkout -b maple-fern/r110-a2 origin/maple-tanjiro/r110-prefill-nax-arm-factory
git --no-pager diff --numstat 30904ecbf180aa05d7ddf5cc957e83155fbfc6f4 HEAD \
    -- Sources Vendor benchmark.json Package.swift
#   expect exactly: 17  0  Vendor/mlx-swift/.../metal/matmul.cpp
```

Paired A/B inside one binary: candidate is the default,
`DARKBLOOM_FUSED_NAX_NARROW_BN=0` is the control.

## 6. Arm A1 — FIRE SECOND. Patch file.

`darkbloom_expert_down_bn()` default `64` → `32` at `quantized.cpp:1242`.
Prefill-only via the existing `M >= 64` accept gate at `quantized.cpp:1404-1407`.
JIT-only; no metallib rebuild. `DARKBLOOM_EXPERT_DOWN_BN=64` restores the
incumbent for a one-binary paired A/B.

```bash
git checkout -b maple-fern/r110-a1 30904ecbf180aa05d7ddf5cc957e83155fbfc6f4
git show maple-tanjiro/r110-prefill-nax-arm-factory:research/maple-tanjiro-r110/A1-expert-down-bn32.patch > /tmp/A1.patch
git apply --check /tmp/A1.patch && git apply /tmp/A1.patch
git commit -am "R110-A1: expert down bn 64->32 for prefill"
git --no-pager diff --numstat 30904ecbf180aa05d7ddf5cc957e83155fbfc6f4 HEAD \
    -- Sources Vendor benchmark.json Package.swift
#   expect exactly: 1  1  Vendor/mlx-swift/.../metal/quantized.cpp

# REQUIRED second check — numstat alone cannot tell A1 from A3 (see §7):
git --no-pager diff -U0 30904ecbf180aa05d7ddf5cc957e83155fbfc6f4 HEAD \
    -- Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/quantized.cpp \
  | grep '^[-+][^-+]'
#   expect exactly:  -      return 64;
#                    +      return 32;
```

`git apply --check` and `git apply --numstat` were both run against the current
head before hand-off; the patch applies cleanly and touches exactly one file
with `1  1`. **Do not treat that `1  1` as sufficient on its own** — the A3
patch produces the identical numstat on this head, so the content check above is
what actually identifies A1.

**Why it is genuinely unmeasured.** `research/CURRENT_RESEARCH_STATE.md:6784`
records that this knob has no receipt. Priced **0.195–0.30 %** by
`research/maple-alphonse-r107c-expert-gather-gemm-floor.md:604-647`.

**Why it is second, not first.** Its price band overlaps A2's realistic band, but
it lacks A2's two advantages: there is no measured mechanism receipt for the
expert-down tile the way fern's probe backs the packing mechanism, and it is not
bit-exact-by-construction in the trivially checkable way A2 is (it changes the
expert-path tiling, and the bit-exactness rests on the gate transcript rather
than on an invariance argument). Fire it if A2's slot returns and there is a
second slot.

## 7. Arm A3 — REMOVED from the queue

**Do not fire it. Do not stage it.** `A3-expert-gather-groups-128.patch` remains
in this directory for provenance and for the trap below, not as a candidate.

`darkbloom_expert_gather_groups()` 256 → 128 at `quantized.cpp:1225`. The tree
default is already 256 (`quantized.cpp:1226`); A3 moves to the setting that two
independent receipts call worse:

1. **An M5 measurement.** The comment stripped in
   `research/nezuko-r99b/rung1-comment-strip.patch:7390-7393` reads: "Measured
   on M5 Max against the promoted 64 schedule, 128 captures roughly two-thirds
   of the 256 schedule's prefill gain ... 256 measures closer to the acceptance
   ceiling."
2. **A queue simulation.** `research/pr142-lpt-expert-queue-refutation.md:274`
   through `:293` concludes the "**current default `egroups = 256` is
   optimal**"; `:296` calls the knob "**ambiguous, not dominant**, worth at most
   ~0.5 ms, and sign-uncertain in `C`", and gives **−0.061 ms** for the move.

`research/maple-alphonse-r107c-expert-gather-gemm-floor.md:92` records the
resulting "⇒ Stage A arm 3 dropped".

`research/PREFILL_NAX_ANALYSIS.md:56-60` was cited for this in an earlier draft
and has been removed: that document is **retracted as unsourced**
(`research/CURRENT_RESEARCH_STATE.md:123-125`). The drop was re-earned on the two
receipts above without it.

I built and gated A3 before finding this prior art. That is my error, and the
correction is worth more to fern than the arm was.

> **Trap that survives the removal — and it got worse in rev3.** A3's hunk is at
> `quantized.cpp:1223` and A1's is at `:1239`, far enough apart that `git apply`
> of either **succeeds** wherever the other has already landed. There are now two
> distinct failure modes, and they are not caught by the same check:
>
> 1. **Stacking** (A1 *and* A3 applied): shows `2  2 quantized.cpp`. `--numstat`
>    catches this.
> 2. **Substitution** (A3 applied *instead of* A1): shows `1  1 quantized.cpp` —
>    **identical to a correct A1 build.** `--numstat` does **not** catch this.
>    Before rev3 the head carried A1, so any stray `quantized.cpp` edit had to
>    stack and was visible. Now the head carries A2 and `quantized.cpp` is clean,
>    so a wrong-patch build is numerically indistinguishable from the right one.
>
> Both patches are a single one-line `return N;` change in the same file, so the
> **only** sound discriminator is the changed content. After applying A1, this
> must print exactly two lines:
>
> ```bash
> git diff -U0 -- Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/quantized.cpp \
>   | grep '^[-+][^-+]'
> # -      return 64;
> # +      return 32;
> ```
>
> `return 256;` → `return 128;` means you applied **A3**. Stop and reset.
> Patch digests (`shasum -a 256`, first 16): A1 `6c55ca15f0081d34`,
> A3 `7a9d4892e3b1e1bf`.
>
> A2 needs no such check: it is live on the head, and its patch file
> **deliberately no longer applies** there (`patch failed ... matmul.cpp:219`).
> If `A2-fused-nax-bn64-n1024.patch` ever applies cleanly, you are not on the
> intended head.

## 8. Arm A4 — designed, then refuted. Recorded as a dead end.

`DARKBLOOM_SPLITK_NARROW_N`: halve `split_k_partition_size` for `M >= 64 &&
N <= 512` split-K nax shapes, targeting the router (`N=256`, 38×) and g_proj
(`N=64/48`, 39×) dispatches that sit at **0.40–1.60 TG/core** — by far the worst
occupancy on the map, and the obvious next move once §4 shows A2 cannot reach
them.

**It is dead for four independent reasons, any one sufficient:**

1. **Not bit-exact.** Changing the partition size changes the grouping of the
   fp32 split-K reduction. Correctness is a hard gate; this is disqualifying on
   its own.
2. **Magnitude.** The analytic floor for router + g_proj combined is **0.42 ms**
   (`research/RESEARCH_IDEAS_steel-gemm-prefill.md:45-46`) — at or below the
   landing bar even at 100 % capture.
3. **Already enumerated.** It exists as hypothesis **H5** at
   `research/RESEARCH_IDEAS_steel-gemm-prefill.md:200`, and `:209` reads
   "Rank last."
4. **Explicitly forbidden as an experiment.** §99.6
   (heading at `research/CURRENT_RESEARCH_STATE.md:6210`) says "do not assign as
   a timed experiment" at `:6229`.

I am recording it in full because the reasoning chain that produces it —
"g_proj is at 0.40 TG/core, that is terrible, split-K partition size is the
knob" — is short, correct-looking, and will be re-derived by the next person who
reads the census in §4. It ends here.

One genuinely open observation from the same investigation, offered without a
brief attached: the split-K path has **no M5 swizzle override** (grid setup
`matmul.cpp:740-766`) where the regular path has `swizzle_log = 2`
(`matmul.cpp:280-308`). That asymmetry is unexplained and is bit-exact to change.
It is not an arm in this queue.

## 9. Build notes that apply to A1 and A2

- Both are **JIT-only**. No `tools/build-mlx-metallib.sh` rebuild is needed, and
  **no kernel body is edited**, so no `mlx-generated/*.cpp` twin needs resyncing.
- Use `./benchmark.sh --local-iterate` for the scored worker build; a bare
  `swift build -c release` writes a different build directory.
- Any direct `swift build` / `swift test` needs `--force-resolved-versions`,
  followed by `git checkout -- Package.resolved`.
- One knob per official run. Never compose A1 with A2, and never bundle either
  with maple-edward's R110-B work.

## 10. Scope and budget

Each arm submits exactly one path; both checks pass.

- A2 (`matmul.cpp`, current head): `assignment scope OK: 1 submitted path(s)`;
  `editable budget OK: current=2681871/3000000 headroom=318129
  growth=-301978/262144 files=142`.
- A1 (`quantized.cpp`): `assignment scope OK: 1 submitted path(s)`;
  `editable budget OK: current=2681206/3000000 headroom=318794
  growth=-302643/262144 files=142`.

Growth is **negative** for both, so there is no submission-review byte risk.

Both checks were re-run against the campaign `BASE_SHA`
`1bc1c8954147c9e322aad1f3b80bd9fa3c0888d7` on the **final** branch head and
returned the A2 figures above unchanged. `research/` files are not on the
submitted surface, so this queue's documentation cannot move the byte budget.

## 11. Gate evidence

See `GATES.md` for full transcripts. Read §2 before giving any of it weight.

Both arms have a green `./benchmark.sh --local-iterate` with
`max_abs_diff: 0` and an upstream-equivalence run with a **confirmed non-zero
test count** (Rule 105.15). Both also have an env-var control that restores the
base value of the one thing the arm changes without touching the tree —
`DARKBLOOM_EXPERT_DOWN_BN=64` for A1, `DARKBLOOM_FUSED_NAX_NARROW_BN=0` for A2.

All four equivalence reports are **byte-identical**: prefill
`0.125 / 0.011933609 / 5991 == 5991`, decode-0..7 exactly `0` with matching
tokens. That pair is the documented pre-existing non-M5 near-tie, so neither
arm causes it, and the arm-vs-control identity is the direct proof.

A2's gate evidence is on the **branch head as it will be fired** — job
`55fb8d61` for the equivalence run, job `d7984b40` for the local-iterate green.
A1's is on the tree it occupied before the rev3 promotion; its patch has since
been re-verified with `git apply --check` and `--numstat` on the current head.

**Residual risk, stated plainly:** all of that exercises the **non-NAX
fallback**. Neither arm's actual kernel has ever executed anywhere. The
correctness argument for A2 is the invariance argument in §5.1, not the gate; the
gate only proves the invariance argument was not undone by a build error.

## 12. A live trap in the kernel, for anyone sweeping tiles after us

`tile_matmad_nax` (`kernels/steel/gemm/nax.h:972-1029`) has a
`TN == 1 && TM % 2 == 0` arm and a `TN % 2 == 0` arm and **no else branch**.
With `TM = 1`, any odd `TN` emits **no MMA at all and writes zeros** — a silent
wrong-answer, not a compile error or a crash.

Any future `BN` sweep must be validated **jointly with `WN`**, with the standing
requirement `(BN / WN) % 32 == 0`. This is why A2 moves `wn` with `bn`, and why
the discarded first version of A2 was dangerous.

Related, and unexplored: the expert-path `BK` is hardcoded to `64` at
`quantized.cpp:1378` and, unlike `bm`/`wm`/`wn`, is **never re-checked by the
accept gate** at `quantized.cpp:1404-1407`. Its constraints are `BK >= 56` and
`BK % 32 == 0`. Nobody in the campaign appears to have touched it.

## 13. Citation and arithmetic audit — what re-checking changed

Every prior-art and numeric claim in this directory was re-verified against the
cited file, line, or artifact before hand-off. Seven things were wrong and are now
fixed.

1. **PR #293's removal commit.** I had written "deleted by resync `99b974c`".
   `99b974c1` is dated **2026-08-03, four days before the variable existed**. The
   real chain is `c2812d1c` (introduced, 08-07 14:29) → `31f64154` (merged as
   #293, 08-07 18:34) → `6ada66c9` (removed, 08-08 20:37). The substance —
   merged inert, zero M5 receipts — survives; only the commit id was wrong.
2. **A retracted source was propping up the A3 drop.**
   `research/PREFILL_NAX_ANALYSIS.md` is retracted as unsourced
   (`CURRENT_RESEARCH_STATE.md:123-125`). Removed, and the drop re-earned on two
   receipts I had not previously read closely (§7). It is now better evidenced
   than when I made it.
3. **Two efficiency numbers were being conflated.** 87.5 % (dense steel family vs
   a 60 TFLOP/s reference) and 28.5 % (share of whole prefill not attributed to
   dense GEMM) come from different censuses. §4 now carries an explicit warning.
4. **Line-number drift.** fern's sg/TG probe is §7.1 (`:566`, `:575`), not §7;
   r107c's "Stage A arm 3 dropped" is `:92`; H5's "Rank last." is `:209`; the
   split-K prohibition is `§99.6` (heading `:6210`, prohibition `:6229`).
5. **σ was mislabelled** as 0.103 % when the stored numbers give **0.1388 %**
   (§3). Every "how many σ is this" judgement made against the old label was
   ~35 % too generous.
6. **A2's price was overstated by 3–8×** (§5.3). The quoted 0.94–2.52 % of score
   exceeds what the entire wk/wv family costs on M5 (3.922 ms ≈ 1.45 %). The
   honest ceiling is 0.35–0.46 % and the realistic estimate is 0.11–0.30 %.
7. **The A3 compose-trap check was silently invalidated by rev3 itself** (§7).
   The documented discriminator was "`2  2` means stacked, `1  1` means clean".
   That held only while A1 was live on the head. Now that the head carries A2
   and `quantized.cpp` is untouched, applying A3 *instead of* A1 also yields
   `1  1` — the wrong build and the right build are indistinguishable by the
   check I had written. §6 and §7 now require a content check on the changed
   line. Found by re-running the trap against the new head rather than trusting
   the note I had already written about it.

Items 5 and 6 do not change any arm's disposition, but they do change what a slot
spent here is worth, which is the number the leaderboard framing actually turns
on. Item 7 is the one that could have cost a slot outright.

---

## 14. Reconciliation with advisor R112 and R113

**Why this section exists.** §3 was written and frozen before two advisor
comments landed on PR #692: **R112 at 00:22Z** (comment 5) and **R113 at 00:42Z**
(comment 6). My rev3 terminal result went out at **00:48Z**, six minutes after
R113. §3 therefore prices the arm against a number R112 retracts and states a
landing rule R113 inverts. This section is the correction. **Where §3 and §14
disagree, §14 wins.**

### 14.1 The "~1.4 % deficit to the crown" does not exist — retracted

§3 priced this queue against "maple's deficit to the crown is ~1.4 % of real
speed ≈ 3.8 ms of prefill". That framing is void.

- The crown submission `cc6ddc1` (score **2.61650**) belongs to **another
  solver**, and its tree is byte-identical to our common base:
  `git diff 1bc1c895 c5b0a13c -- Sources Vendor benchmark.json Package.swift`
  reports **2 files, +116 lines**, and both are harness-only
  (`LagunaRuntimeLocalIterate.swift`). There is no code in the crown we do not
  already have.
- Class means, not single draws, are the comparable quantity. **Crown-holder
  class mean 2.581271** (n = 16, rel sd 0.911 %) versus **maple HEAD class mean
  2.586439**. We are **already ~0.20 % ahead** of the crown holder's typical
  draw. The 2.61650 crown is a high draw from a distribution whose centre is
  below ours.
- R113 quantifies the noise the crown sits inside: pooled field σ
  **0.6590 %** (56 df, 60 draws). Our HEAD class (n = 3) sits **+0.334 %** above
  the field tree.

**Consequence for this queue.** A2 is not chasing a 3.8 ms hole. It is trying to
move a distribution whose centre is already in front, by enough that a draw
from it beats the field more often. That is a *smaller* target than §3 claimed,
and it is the reason §14.2's bar matters more than §3's did.

### 14.2 The landing rule is inverted — R113 #4 supersedes §3

§3 said: *"Land if the paired candidate is non-negative and bit-exact."*

R113 #4 says the opposite, in the advisor's words: he will **not** integrate on
"no worse" or "looks neutral" — **"Ship on a verified positive or do not ship."**

This is the single most dangerous line in the pre-R113 handoff, because it reads
as authorisation for exactly the action the advisor has now forbidden, and it
sits in the section fern is most likely to read when deciding whether to burn a
slot. It is struck in §3 and restated here:

| Draw | pre-R113 §3 | **binding rule (R113 #4)** |
|---|---|---|
| paired negative | do not land | do not land |
| paired ≈ 0 / "neutral" | **land** | **do not land** |
| paired positive, < 3σ | land, "kept not proven" | **hold** — not shippable, but worth a second paired draw |
| paired positive, ≥ 3σ (≥ 0.400 ms) | land and claim | land and claim |

"**Kept, not proven**" (§3) now authorises **keeping the arm on the branch and
paying for one more paired draw**. It does **not** authorise a submission.

**The bar moved, and A2 clears it.** R113 sets the campaign-winning threshold at
a **verified +0.25 %**, with the marginal value of accuracy stated explicitly —
P(win) over ~20 remaining draws goes +0.00 % → **54.3 %**, +0.25 % → **72.8 %**,
+0.50 % → **86.8 %**, +1.00 % → **98.4 %**; i.e. **+18.5 pp per +0.25 %**.
§5.3's honest A2 numbers are a **0.35–0.46 % ceiling** with a **0.11–0.30 %**
realistic band. So A2's realistic band **straddles the new bar and its ceiling
clears it**. Under §3's old 0.30 ms landing bar A2 looked marginal; under R113's
+0.25 % bar it is on-target. The arm got more valuable when the bar was restated,
not less — but only if the draw is **verified positive**, never if it is neutral.

R113 also states the trade the advisor is willing to make: *"a verified +0.9 %
with an airtight TN=1 proof is worth far more than a verified +2.5 % I cannot
safely integrate."* A2 is built for that trade — its correctness argument is
structural (§5), not statistical.

### 14.3 The two-instrument law (R113 #5) cannot be satisfied by A2 — and the advisor already exempted it

R113 #5 makes a two-instrument rule doctrine: an arm should carry an M4 paired
(ABBA) interval **and** the M5 verdict. A2 cannot satisfy this, and the reason is
not "underpowered", it is stronger than that:

**A2 is provably inert on this host.** The knob only fires inside the
`devc ∈ {s,c,d}` branch of `matmul.cpp`, i.e. only when `_nax` is selected.
`is_nax_available()` is **false** on Mac16,11 (M4 Pro, Apple GPU generation 16).
Gate job `3179bf11` measured the env control and found the two executables
**byte-identical in behaviour**. So an M4 ABBA rig on A2 does not compare a
candidate to a baseline — it compares **one executable to itself**.

That makes the M4 instrument a **null instrument**, not a weak one. The
distinction matters:

- A weak instrument produces a wide interval that contains zero. Reporting it is
  honest and uninformative.
- A **null** instrument produces an interval that is **pure measurement noise
  with a known-zero true effect**. If such an interval ever excludes zero, that
  is by construction a **Type-I error** — and with the local noise floor at
  **2.52 % prefill spread across 4 gated trees** (§2), it will happen at some
  rate. Publishing it would be manufacturing evidence.

I will not run that rig, and I am recording the refusal rather than quietly
omitting it.

**This is already covered.** The advisor's own **§0P.8(c)** admits an arm that
"probes an axis with zero local observability", and A2 is the example that
clause describes. §0P.8 and R113 #5 are consistent: the two-instrument law
governs arms that *have* two instruments. A2 has one, by construction, and the
missing one is the M5 verdict — which only fern can obtain.

**What replaces the missing instrument.** Not a measurement; a structural
argument, in §14.4. That is the honest substitute, and it is weaker than a
number. Fern should treat A2 as a one-instrument arm and price the slot
accordingly.

### 14.4 Why A2 is a structurally one-sided bet — the answer to R113's asymmetry premise

R113's integration asymmetry rests on the premise that a neutral-looking arm may
secretly be, say, −0.25 %, which is why "no worse" is not good enough. **For A2
that premise does not hold**, and the reason is measured — by fern, on the
mechanism, not by me on a null instrument. Source:
`research/fern-r104b-wkwv-tile-regroup.md`.

**Fact 1 — the change conserves every quantity that normally trades off.**
Verified against `matmul.cpp` and `steel_gemm_fused_nax.metal:23-29`:

| | incumbent | A2 |
|---|---|---|
| `(bm,bn,bk,wm,wn)` | `(64,128,256,2,4)` | `(64,64,256,2,2)` |
| per-simdgroup tile `SM×SN` | 32×32 | **32×32 — invariant** |
| `TN` | 2 | **2 — invariant** (never enters the `TN==1` path) |
| threadgroups (wk/wv, M=512 N=1024 K=2048) | 64 | 128 |
| simdgroups per threadgroup (`wm*wn`) | 8 | 4 |
| **total simdgroups** | 512 | **512 — invariant** |

The *same 512 simdgroups* do the *same 32×32 tile* over the *same K-loop*. Only
their grouping into threadgroups changes.

**Fact 2 — there is no shared-memory cost to pay for the regroup.** fern §4.1
compiled all four geometries offline and every pipeline reports
**`staticThreadgroupMemoryLength = 0`** (`threadExecutionWidth = 32`,
`maxTotalThreadsPerThreadgroup = wm*wn*32`; incumbent metallib sha `349cf1e1…`,
A2 `d044f6c9…`, both `SM/SN/SK = 32/32/32`, `TM/TN = 2/2`). fern's own note: this
is *"load-bearing. Threadgroup residency is limited by threads/registers only,
never by threadgroup memory, so a narrower threadgroup can always pack at least
as many simdgroups per core as a wider one. This is what makes the regroup a
one-sided bet on occupancy."*

**Fact 3 — the grouping penalty is measured, and it is one-directional.**
fern §7.1, job `0c4e2817-f311-4933-ba80-b6487d6eb9dd` (exit 0, 21.3 s, probe
`research/fern_r104b_grouping_probe.swift`, 201 lines, `xcrun swiftc -O`,
best-of-25, rule 77), at **total 512 simdgroups**:

| simdgroups/TG | µs | ratio |
|---|---|---|
| 1 | 521.7 | 1.0002 |
| 2 | 521.7 | 1.0002 |
| **4 (= A2)** | **521.6** | **1.0000** |
| **8 (= incumbent)** | **762.2** | **1.4613** |

Reproduced twice. §7.2's causal control identifies the mechanism as **wave
quantization** (~255 µs passes): across **13 measured totals**, at 168/336/672/
704/1008/1024 the g=8 column matches g=4 to within **0.1 %**, and the penalty
appears **only** at 504/512/528 and 840/848. **512 is the worst band observed.**

**The one-sidedness, stated as a bet.** Over those 13 totals, g=4 is *never
materially worse* than g=8: worst case **+0.14 % at total 1024** (inside noise),
best case **46 % better**. So A2's payoff is: **large upside if M5's 512-simdgroup
total lands in a penalty band, approximately neutral otherwise.** There is no
measured configuration in which the regroup costs meaningfully.

**Where this argument stops (fern's limits, §7.3, which I am not softening).**
The `ceil(total/C)` model does not fit all 13 points. The Part-1 concurrency
ladder was unreliable (C = 44, then 20). **M4 Pro has 20 cores; M5 Max is assumed
to have 40** — so the band *locations* are host-specific and fern **explicitly
refuses to extrapolate them to M5**. I inherit that refusal: the claim here is
**"the sign of the bet is one-sided"**, not **"M5 is in a penalty band"**.

**Residual risks, named honestly.** Neither is locally measurable and both are
second-order: (a) **2× threadgroup launch/prologue overhead**, 64 → 128 TGs;
(b) `swizzle_log = 2` traversal over `tn` 8 → 16 changes tile order and therefore
cache locality. If A2 draws negative on M5, these are the two places to look.

### 14.5 Two derivations I made and then retracted — recorded so nobody repeats them

Both looked like solid arguments *against* A2 and both are wrong. They are
written down because they are the natural first two objections anyone will raise.

1. **"The load imbalance cancels exactly."** A naive `ceil(T/W)` wave model gives
   2 waves × 8 sg = 16 sg-units for the incumbent and 4 × 4 = 16 for A2, implying
   a perfect wash. **Refuted** by fern §7.2's measured wall-step counts: at total
   512, g ≤ 4 takes **2 steps** and g = 8 takes **3**. The model is wrong because
   multiple small threadgroups **co-reside per core**, which the one-TG-per-core
   assumption forbids.
2. **"A2 costs +33 % operand traffic."** From classical shared-memory GEMM
   staging: per K-step the incumbent stages `64×(64+128) = 12288·bk` and A2
   stages `128×(64+64) = 16384·bk`, i.e. A tiles fetched twice, B unchanged.
   **Refuted** by Fact 2: `staticThreadgroupMemoryLength = 0` means there is no
   staged A/B tile to double. Per-simdgroup tile, K-loop and load pattern are
   invariant and the total simdgroup count is invariant at 512, so **operand
   traffic is invariant**.

**A standing caution for the next person.** Both retractions came from the same
error: reasoning about this kernel using textbook tiled-GEMM intuitions that
assume threadgroup-memory staging and one-threadgroup-per-core scheduling.
`steel_gemm_fused_nax` does neither. Check
`staticThreadgroupMemoryLength` and fern's §7.2 table before trusting any
occupancy or traffic argument about it.

**Related follow-up, downgraded.** I had planned to extend fern's probe to carry
realistic operand traffic, on the theory that its zero-traffic simplification was
a blind spot. Fact 2 says it is not — the real kernel also moves zero bytes
through threadgroup memory, so the probe is **faithful** on that axis. The
extension is now low value; I did not run it.


---

## 15. Revision rev4 — Stage 0 of the norm+QKV fusion, and what it settles

**The arm queue in §0–§8 is unchanged by rev4.** The submitted surface still
carries A2 and nothing else: `git diff --numstat e400de7d -- Sources Vendor
benchmark.json Package.swift` is exactly `17  0  .../metal/matmul.cpp`. Scope and
budget re-verified at this head (`assignment scope OK: 1 submitted path(s)`;
`current=2681871/3000000 headroom=318129 growth=-301978/262144`). Everything
below is research-only under `research/maple-tanjiro-r110/`.

### 15.1 Outcome: `N-NORM-QKV-FUSION-BELOW-BAR`

Full write-up: `research/maple-tanjiro-r110/N-NORM-QKV-FUSION-BELOW-BAR.md`.

The fused RMSNorm+QKV path is reachable, exact (0 divergences in 35 independent
200-step teacher-forced runs), and **slower** than the unfused path on the only
bank where it runs. Stage 1 was gated on fusion being **+35.7 us/step faster**;
the 32-run paired ABBA measures it **+17.2 us/step slower, 95 % [+9.0, +25.3]**,
with a blocking-free Mann-Whitney check at z = +3.05. **Stage 1 not entered.**
The direction's entire ceiling is ~77 us/step (~0.54 % of score) and this
implementation is 1.3x underwater against it, so the miss is structural rather
than a tuning gap.

### 15.2 The one result here that generalises: the M4 rig is now calibrated

R113 laid down a two-instrument law — *"bring me a paired M4 interval that
excludes zero"* — but the rig's actual resolution had never been established on
this branch. It now is, on a live contrast:

| design | half-width | as % of score |
|---|---|---|
| 32 runs, blocked k=4 x 8 (~26 min) | +-8.1 us/step | **+-0.07 %** |
| same data, widest blocking k=8 x 4 | +-20 us/step | +-0.17 % |

So a ~26-minute paired ABBA does resolve the 0.25 % effect R113 calls
campaign-winning, with a factor of 1.5–3.5 to spare. **The advisor's instrument
claim is confirmed** — for arms that execute on this host.

Two honest limits on that number. It was measured on the **int8 bank**, whose
step is 11.6 ms against the shipped NVFP4 9.8 ms; absolute microsecond
resolution should carry across, but the percentage figures above are computed at
the campaign constant and would tighten slightly on the faster shipped step.
And it is a **decode** contrast — prefill has its own noise, which §2 measured at
a far worse 1.6–2.5 % run-to-run on this host. Nothing here says the rig resolves
0.25 % of *prefill*.

### 15.3 What it does not do: A2 is still unmeasurable here

This calibration sharpens §2 rather than softening it. The rig works; it still
cannot see A2, and the reason is structural, not statistical:

- This host is `Mac16,11` M4 Pro, Apple GPU **generation 16**, so
  `is_nax_available()` is **false** and **no `_nax` kernel is ever dispatched**.
  A2 changes `_nax` tile selection only.
- That is measured, not assumed: the A2 arm run and its
  `DARKBLOOM_FUSED_NAX_NARROW_BN=0` control produce **byte-identical**
  equivalence reports (§11). The knob is inert on this machine.

An ABBA toggling that env var would therefore return a **structural zero** —
tight, clean, and meaningless. Under R113's asymmetric rule that zero would
refuse A2 for a reason that has nothing to do with its behaviour on M5. **A
0.07 %-resolution instrument pointed at a kernel the host never runs is still
blind.** The right move is an M5 paired rig, or an M5 submission decided on A2's
bit-exactness-by-construction; it is not a local interval.

**A1 is inert here too, and this is now proven rather than assumed.** A1's knob
`darkbloom_expert_down_bn()` is read at `quantized.cpp:1396`, inside
`gather_qmm_rhs_nax`, whose body spans **1339–1652** (the next top-level function
is `gather_qmm_rhs` at 1653). That function has exactly **one** caller,
`quantized.cpp:1671`, and it is guarded by
`if (metal::is_nax_available() && transpose && ...)`. With
`is_nax_available() == false` the whole 1339–1652 region — knob, `expert_aligned`
gate and all — is unreachable on this host.

Note this is *not* visible from A1's own gate text: the `expert_aligned`
condition at `:1404-1407` mentions `group_size`, `bits`, shape and `M >= 64` but
never mentions nax, so reading only the gate suggests A1 might be locally
measurable. It is not; the nax check sits one frame up. **Nothing in this queue
is measurable on this host**, and neither arm's own gate says so on its face.

### 15.4 Follow-up worth more than Stage 1 was

Section 10.2 of the write-up: the ~77 us/step prize does not require fusing into
the QKV matvec at all. Folding each layer's input norm into the **previous**
layer's residual-add epilogue — the shape
`residual_rms_router_bf16_2048_rpg8_keys_v1_pf1` already uses — harvests the same
40 dispatches with **no redundant-reduction exposure**, which is precisely the
term that sank this attempt. That is the version of this idea worth assigning.


---

## 16. Revision rev5 — the R116-A answer (advisor comment 5248135695, 01:54Z)

**The submitted surface is still A2 and only A2, byte for byte.** Re-verified at
this head:

```
$ git --no-pager diff --numstat e400de7d095ffcfcde0462b174c7d22d737496fd HEAD \
    -- Sources Vendor benchmark.json Package.swift
17  0  Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/matmul.cpp
```

rev5 adds one research-only file and changes no code. The head is frozen for
A2's M5 receipt: **I do not rebase it and I do not spend a submission slot.**

### 16.1 The kill on norm->QKV fusion is confirmed, in full

`research/maple-tanjiro-r110/N-NORM-QKV-FUSION-ALREADY-SHIPPED-AND-DEAD.md`
carries the three grep-level confirmations the advisor asked for:

| claim | verdict | evidence |
|---|---|---|
| `lagunaNormAffineQKV` ships and is default-ON | **confirmed** | `LagunaRuntimeModel.swift:5482-5483` |
| its guard wants `bits == 8`, the shipped bank is NVFP4 `bits = 4` | **confirmed** | guard `:5926-5932` vs bank `:3048-3054` = `(.nvfp4, 16, 4)`; all three conditions fail, every layer, every step |
| zero dispatches in profiling | **confirmed** | `grep -ci "norm_affine_qkv" stage0-evidence/N.log` -> **0**; the census shows `decode_nvfp4_qkv_h64` 30/step and `rmsbfloat16` 41/step instead |

**I accept the `N-SOLE-PRODUCER-WIDTH-RATIO` family placement and decline the
escape hatch.** My mechanism is not outside nezuko's family; it is the same
rung-1a object. I am not building the NVFP4 port.

### 16.2 The two numbers are not in conflict — and the gap is explained

My **+17.2 us/step** (measured, shipped int8 fusion) and nezuko's **+560 us/step**
(priced, hypothetical NVFP4 port) are different objects with one differing
structural parameter:

| | shipped int8 fusion | NVFP4 port |
|---|---|---|
| grid | `((rows/8)*64,1,1)` (`:5538`) | `((rows/2)*64,1,1)` (`lagunaDecodeNVFP4QKVR1`) |
| rows per threadgroup | **8** | **2** |
| threadgroups for the same rows | 1x | **4x** |
| redundant-reduction exposure | 1x | **4x** |

Same verdict, and the 4x structural penalty is the direction my write-up's §7
predicted before nezuko's number was visible. Nothing here rehabilitates the
direction.

### 16.3 Stage 0 was not void, and this is the only part worth keeping

The guard is **satisfiable legally**: `DARKBLOOM_NATIVE_AFFINE_NVFP4=0` selects
group-32 affine INT8 for Q/K/V/O, which is inside the accepted envelope
(`TASK.md:78-94`). So Stage 0 converted "shipped but dead" into a **measured
price** on the one bank where the code runs, rather than a paper estimate.

Repriced under the advisor's corrected law (`%score = 0.75 x tau x d_us / 8972`,
tau ~ 1.06 for real DRAM removal):

| quantity | rev4 statement | corrected |
|---|---|---|
| ceiling of the whole direction (77.4 us/step) | 0.54 % | **+0.69 %** |
| measured outcome (-17.2 us/step) | -0.12 % | **-0.15 %** |
| Stage-1 entry bar | +35.7 us/step | **+28.1 us/step** |

The bar tightened and the arm still misses it by **more than 10x**. Verdict
unchanged; the miss is structural.

### 16.4 A2's read rule, recorded so it is not misapplied

The advisor fires A2, not me. When the receipt lands, read it **only** on raw
`prefill_seconds_per_token` (sd **0.2033 %/draw**) — never `officialScore`
(sd 0.4938 %) and never the paired ratio (**9.28x worse**). Preregistered against
the n=4 HEAD-class mean **187.8728 us**:

```
d = 100 * (187.8728 - p_A2) / 187.8728
d >= +0.46 %  -> confirm
|d| < 0.46 %  -> inconclusive
d <= -0.46 %  -> revert
```

Prefill elasticity is **0.250**, not the 0.362 used in §3/§5.3. Every prefill
price in §3–§5 is therefore **~31 % too generous** and should be scaled by
`0.250/0.362 = 0.690` when read. A2's honest ceiling becomes **0.24–0.32 %**
(from 0.35–0.46 %) and its realistic band **0.08–0.21 %** (from 0.11–0.30 %) —
i.e. under the corrected elasticity A2 now sits *below* R113's +0.25 % bar in
the realistic case and only its ceiling reaches it. That is a material downgrade
of §14.2's "straddles the bar" claim and I am recording it against my own arm.

### 16.5 One honest tension I could not resolve

The tau ~ 0 constant for threadgroup geometry was measured in the **saturated**
regime. A2's entire rationale (§14.4) is the **under-filled** regime — 64
threadgroups on 40 cores, where wave quantization is exactly what geometry
controls. Those are not obviously the same tau. I cannot settle it locally,
because A2 is `_nax`-gated and this host is Apple GPU generation 16. Flagged
rather than resolved.

