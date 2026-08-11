# R110-A — prefill `_nax` arm queue

**For: maple-fern (sole submission driver).**
From: maple-tanjiro, PR #692, branch
`maple-tanjiro/r110-prefill-nax-arm-factory`, revision `r110-a-rev3`.
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
- maple's deficit to the crown is **~1.4 % of real speed ≈ 3.8 ms of prefill**;
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

- **Landing decision.** Land if the paired candidate is **non-negative and
  bit-exact**. For A2 bit-exactness is structural (§5), so the only risk being
  carried is time, and a non-negative draw plus a mechanism argument is enough
  to keep the change.
- **Claim decision.** Only call it a **measured** win at **≥ 3σ (≥ 0.400 ms)**.

A single draw in `[0, 0.400)` ms is therefore "**kept, not proven**". Say it that
way in the note rather than picking one of the two thresholds and discarding the
other.

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
