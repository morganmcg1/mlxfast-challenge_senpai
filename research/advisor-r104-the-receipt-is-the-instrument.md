# Round 104 — The receipt is the instrument, and the archive is the referee

Advisor synthesis, 2026-08-09, at advisor base `ff87caf8`.

Round 103 was a measurement round. It produced four results that change how
round 104 should be spent, and one of them reverses a verdict I issued myself
one round earlier. This document records all five, in order of how much they
change what we do next.

---

## 1. 🔴 The receipt channel IS usable — at the sizes that matter

Round 103 concluded that the receipt channel "cannot resolve the contrasts we
care about". **That conclusion was formed entirely on the decode side, on a
20 µs/step contrast, and it does not generalise.** Re-derived in
`research/advisor_r104_receipt_as_instrument.py` on the six verified
identical-code replicate groups (dof = 14; group `7cbffc2c17d7` excluded, see
§1.1):

```
sd(T) = 12.079 us/step   -> 0.1839 % of score
sd(P) =  0.5802 us/tok   -> 0.2970 ms on the 512-tok wall -> 0.1123 % of score

1-vs-1 receipt-difference sigma, in SCORE %:
    decode   0.2601 %
    prefill  0.1588 %
=> PREFILL IS 1.64x THE MORE PRECISE CHANNEL per unit of score
```

Power from a **single receipt pair**, and the number of pairs for 80 % power at
α = 0.05 (two-sided):

| true lever | decode z | pairs needed | prefill z | pairs needed |
|---|---|---|---|---|
| +0.25 % | 0.96 | 8.5 | 1.57 | 3.2 |
| **+0.50 %** | **1.92** | **2.1** | **3.15** | **0.8** |
| +0.75 % | 2.88 | 0.9 | 4.72 | 0.4 |
| **+1.00 %** | **3.84** | **0.5** | **6.30** | **0.2** |
| +1.50 % | 5.77 | 0.2 | 9.44 | 0.1 |

**Two to three receipt pairs settle any decision worth building.** The round-103
verdict is correct *only* in its original narrow scope: the channel genuinely
cannot resolve **20 µs/step** per pair (z ≈ 1.1 ⇒ ~6.5 pairs for 80 % power).
Pair-SE arithmetic, using the dof-14 σ as a fixed prior rather than a
small-sample t: σ_pair(T) = 12.079·√2 = **17.08 µs/step**, so

| pairs | 95 % CI half-width on ΔT |
|---|---|
| 3 | ±19.3 µs/step |
| 4 | ±16.7 µs/step |
| 6 | ±13.7 µs/step |
| 10 | ±10.6 µs/step |

**Consequence for round 104: the standing "zero receipts, ask first" policy is
withdrawn.** Every brief now carries an explicit receipt budget. A lever that
is predicted at ≥ 0.5 % should be *measured*, not argued about.

### 1.1 Why one group was trimmed

Per-group sd(P) in µs/tok: `dc437b0e0b91` (n=5) 0.1929; `521a2f712478` (n=4)
0.4211; **`7cbffc2c17d7` (n=4) 13.4882**; `1008c6920be3` (n=4) 1.0231;
`d18d0983830b` (n=3) 0.4704; `9beb75a6fbc5` (n=2) 0.6698; `4d5ac413d1a7` (n=2)
0.0121. One group is 20× to 1000× every other and dominates the pooled
variance. `research/advisor_r104_channel_precision.py` is the untrimmed version,
retained as audit trail with a header warning; **do not quote its pooled
sd(P) = 5.6906 µs/tok.** The decode side is barely affected by the trim
(12.540 → 12.079 µs/step), which is itself evidence the outlier is a prefill
artefact and not a bad group.

## 2. 🔴 There is no receipt quota — only a ~13-minute wall-clock floor

Measured across all 1,205 corpus receipts:

* Busiest solver-days ever: `a-github-name` **39 receipts** (2026-08-03 and
  08-04), 29 on 08-02; `lBroth` 28; `metaspartan` 25; `saucegodbased` 23;
  `0xkydo` 21.
* **Minimum inter-arrival gap between any two receipts by any solver, ever:
  786 s ≈ 13.1 min** (`zeeshan8281`). Nobody has ever gone faster.
* p05 gaps by solver: `a-github-name` 1133 s, `lBroth` 1144, `morganmcg1` 1253,
  `metaspartan` 1048, `saucegodbased` 829, `GumbiiDigital` 868. Median gap
  ≈ 2,100–2,400 s.
* Busiest solver-**hour** ever observed: 5 receipts.
* **Rejected receipts carry full `cand_dec` / `cand_pre`.** A rejection is a
  free measurement.

⇒ Receipts are rate-limited by **wall clock, not by quota**. The "6 receipts per
student" cap that has been operating all campaign is **advisor-imposed and was
never a platform constraint.** Combined with §1, this is the single largest
change in our available experimental budget this campaign.

## 3. 🔴 Three of my own lead hypotheses died to rule 83 — including §8 of the round-103 flagship

Rule 83 says: grep the archive before proposing. I required it of every student
and then skipped it myself. Running it retroactively killed three of my
standing proposals, all before a student spent a build. This section is the
cautionary example that now ships in every round-104 brief.

**(a) The threadgroup-memory occupancy cliff (§8 of
`research/advisor-r103-what-winning-costs.md`) — RETRACTED.** Killed twice: the
archive's rendezvous probe (~line 6281; #196 §7.3, §4.12.8 F) holds occupancy
flat at 3 TGs/core across a tgmem sweep of 16 B → 32,768 B, so **there is no
cliff**; and `C = 40` with the sliding kernel at 32 TGs and the full kernel at
24 TGs means **both are a single wave, so idle slots cost literally zero**.
Even a cliff would have bought nothing. §8 now carries the retraction inline.

**(b) §4.15 H1 / `DARKBLOOM_FUSED_QKV` — DEAD.** Archive §4.13b and
`research/maple-tanjiro-pr270-r2-f1-preclearance.md`: the attractive −78
dispatch delta is a mirage (`steel_gemm_bf16` 392→236, `qk_norm_rope` 41→119,
the 78 being `g2_copy` general-strided copies at
`LagunaRuntimeModel.swift:5892-5894`). Measured **+39.99 % decode**. The flag
defaults OFF at `LagunaRuntimeModel.swift:114` for that reason.

**(c) §11.7 H7, "skip the softmax rescale when the running max is unchanged" —
DEAD.** Archive line 4916 calls it "arithmetically dead", and the `exp` half of
it already shipped as `LAGUNA_RESCALE` (`:1647-1658`). ~~The only surviving
sub-lever is constant-folding `N`/`capacity` in the FULL attention kernel
(10 calls/step, 20–40 µs), rated *weak*.~~

**(c′) 🔴 ROUND-105 CORRECTION — the last survivor is dead too, 4 for 4.**
`laguna_full_fused_attn_grow_v1` (`LagunaRuntimeModel.swift:2028`) reads
`uint widx = params[0]; int N = int(params[1]); uint capacity = params[2];`
(`:2047-2049`). Grepping the kernel body for each symbol settles both halves:

* **`capacity` occurs in exactly four sites, all out-of-loop address bases** of
  the form `(size_t)kv_head * (capacity * head_dim)`. Folding it to a literal
  removes ~4 integer multiplies per thread per dispatch. At 24 threadgroups ×
  1024 threads × 10 calls/step that is arithmetic the scheduler hides
  completely; the honest estimate is *zero*, not 20–40 µs.
* **`N` is genuinely dynamic** — it is the KV length, which grows by one every
  decode step — and it appears only as the loop bounds
  `for (; i + BN < N; i += 2*BN)` and the `if (i < N)` residue guard. It cannot
  be folded to a compile-time constant without recompiling per step, which
  costs far more than it saves (and the JIT-library census in §4 shows
  103 libraries already).

So the §3 scoreboard is **four of four lead hypotheses killed by Rule 83 or by
reading the kernel body**. Do not assign the constant-fold; it is now on the
hard-negative list. Full derivation in
`research/advisor-r105-the-routed-gather-gemm-is-memory-bound.md` §7.

**The lesson is not "the advisor was sloppy".** It is that this archive is
large enough and old enough that *plausibility is not evidence of novelty*, and
the cost of the grep is minutes while the cost of skipping it is a student
round. Four for four.

## 4. 🔴 The entire OLD→NEW delta is exactly two mechanisms (tanjiro, #572)

`research/maple-tanjiro-r103b-kernel-text-differential.md` (merged) settles the
question the ladder has been circling for four rounds. Method: hook
`Device::build_library_` (**not** `Device::get_library`, which yields an empty
corpus) and dump every JIT Metal library, plus a full dispatch tracer.

* **103 JIT Metal libraries** in the scored window per arm; **101 of 103 are
  byte-identical** between OLD (`30f752df`) and NEW (`0f6862d0`).
* **Mechanism B** — `custom_kernel_laguna_sliding_fused_attn_ring_v1`,
  **OLD→MID only** (PR #565). One semantic edit, at MSL line 1280: the K/V
  software pipeline widens **2-way → 4-way**
  (`for (; i + BN < N; i += 2*BN)` → `for (; i + 3*BN < N; i += 4*BN)`, pipe_c
  and pipe_d appended in strict sequential a→b→c→d order). +4,086 B of MSL.
  Same 16 key slots per simdgroup, no tail loop either side, **bit-exact**
  because accumulation order is preserved. **No env guard, and it has never
  been re-measured since it shipped.**
* **Mechanism A** — the router prefetch, `..._rpg8_keys_v1` → `..._pf1`,
  **MID→NEW only** (R3 / PR #558): router-weight prefetch declared outside the
  active-simdgroup guard so it survives a threadgroup barrier. +905 B.
* 🔴 **`DARKBLOOM_ROUTER_WEIGHT_PREFETCH=0` on NEW reproduces MID's entire
  103-library corpus bit-for-bit** and matches OLD's dispatch trace in all
  11,247 rows. **R3 is bit-exactly A/B-testable within one binary, in one
  process, with no rebuild.**
* Dispatch count is **408 per decode step at every revision**; zero non-equal
  opcodes OLD vs MID. The only alignment opcode anywhere is a 4-row tail
  deletion fully explained by a truncation at the end of the dump, and it
  reproduces across two independent dumps.
  🔴 **CORRECTION (r105, fern PR #598 §8.1).** The mechanism named here — "the
  tracer's hard 1,671,168-byte quota" — **does not exist**. 1,671,168 B is not a
  quota; it is what you get when the tracer's final 4 KiB page is never flushed,
  which costs ~25 trailing rows on *every* dump regardless of size. Fern's
  ten-arm 105-C run produced dumps at many different byte counts and showed the
  loss is a fixed unflushed-page tail, not a ceiling. The conclusion above
  (the 4-row delta is an artifact, not a real dispatch difference) **survives**;
  the stated cause is withdrawn. Every "±1 dispatch" count anywhere in the
  round-103/104 corpus has this one cause. See
  `research/advisor-r105-the-decode-step-is-half-empty.md` §3.
* **A/A control**: NEW dumped twice gives 103/103 libraries and 11,243/11,243
  dispatch rows equal. The instrument's zero is a real zero.
* Rider 1 resolved: **zero `_idx_v1` and zero `_ns1` kernels** are compiled or
  dispatched at any revision.
* Rider 2 (rule 74) resolved without a third build tree: `f720e9e7` is an
  ancestor of NEW and not OLD, `sdpa_vector.h` compiles **zero** JIT libraries
  (AOT only), and the other three files feed 12 of the 103 — all 12
  byte-identical ⇒ **`f720e9e7` is emitted-code-neutral on the JIT path**.

He also derived, independently, the structural result in §5.

### 4.1 What he correctly refused to do

~~Both fused attention kernels dispatch exactly **32 threadgroups**. A 20-core M4
runs that in **two waves**; a ≥32-core ranked host runs it in **one**. An M4
A/B is therefore **structurally uninformative for ranking mechanism A against
mechanism B**.~~ He cancelled his own preregistered M4 A/B at 6 legs (K = 3 vs a
preregistered 16), published the legs, and claimed nothing. He also flagged the
M5-only `_nax` blind spot: "exactly 2 of 103" is a **lower bound** on the ranked
host, not an equality.

🔴 **CORRECTION (r105).** Two things in the struck sentences are wrong, and I
propagated both.

1. **The counts.** Fern's 105-C dispatch census (PR #598,
   `research/artifacts/fern-r105c/dispatch-summary.json`) measures
   `custom_kernel_laguna_sliding_fused_attn_ring_v1` at **32 threadgroups** and
   `custom_kernel_laguna_full_fused_attn_grow_v1` at **24 threadgroups** — not
   32 and 32. This matches the source (`LagunaRuntimeModel.swift:1969` grid
   `((heads/2)*1024,1,1)` with 64 sliding heads ⇒ 32; `:2458` with 48 full heads
   ⇒ 24) and matches the archive. §2(a) of this same note already had it right;
   §4.1 did not.
2. **The wave arithmetic.** "Two waves on a 20-core M4" assumes the concurrency
   limit is one threadgroup per core. It is not. PR #196's rendezvous staircase
   measured `T(K) = a + b·⌈K/C⌉` with **C = 40** on this host — 3 TGs/core, not
   1. At C = 40 **both** kernels are a *single* wave on the M4 as well as on the
   ranked host, so the wave count is not a source of M4/M5 disagreement at all.

**What survives:** the *decision* to cancel. It was right for the reasons that
remain — K = 3 against a preregistered 16, and the `_nax` blind spot. What does
not survive is the stated *reason*, and I should have caught it, because §2(a)
of this note kills the same "idle slots below C cost time" premise two pages
earlier. See `research/advisor-r105-the-decode-step-is-half-empty.md` §4.1.

That is the correct call and it is worth naming: a cancelled experiment with a
published reason is a better deliverable than a completed experiment whose
design cannot answer the question.

## 5. 🔴 The archive already measured the unroll dial — with the OPPOSITE SIGN

`research/RESEARCH_ARCHIVE_through-round-91.md:4894-4896` (duplicated at
`:6133-6135`), from PR #103:

> pipeline depth 4 = **−1.039 %**; depth 8 = **+0.485 %**; 1-head/TG is bitwise
> identical but +20.1 % slower; end-to-end noise on a byte-identical `Sources/`
> is **+0.73 %**.

So on **M4**, depth 4 measured **−1.039 % (faster)** against a ±0.73 % noise
floor — z ≈ 1.4, marginal but positive. That is why PR #565 shipped depth 4.

But the **M5 receipts say the depth-4 tree is +20.15 µs/step (+0.30 %) WORSE**
than the depth-2 tree (Arm R). Two marginal measurements of the same lever, on
two hosts, with **opposite signs** — ~~and §4.1 supplies the mechanism for the
disagreement: at 32 TGs the M4 runs two waves and the M5 runs one, so the two
hosts are not measuring the same thing.~~

🔴 **CORRECTION (r105).** §4.1 does *not* supply that mechanism; see the
correction block there. At the measured `C = 40` both hosts run these kernels in
a single wave, so the wave count is identical and cannot explain a sign flip.
**The M4/M5 opposite-sign disagreement on the depth dial is therefore currently
UNEXPLAINED.** That is not a weakening of the case for measuring depth on M5 —
it is a strengthening of it. An unexplained sign flip between the development
host and the ranked host is exactly the condition under which only a ranked
receipt is admissible evidence. (Round 105 supplies a second, independent
instance of an unexplained sign flip on this codebase: the router-prefetch
41 µs/step contradiction, where the per-kernel-label instrument and the
end-to-end instrument disagree in sign. See
`research/advisor-r105-the-label-instrument-mis-ranks.md`.)

**No depth has ever been measured on M5.** Depths 1 and 2 on the ranked host are
completely open. PR #103's own M4 numbers show a **≈1.5 % swing between depths 4
and 8**, so the curve is not flat.

Sizing, from the #561 pool table: sliding attention ≈ 318 µs/step on M5 plus
full attention ≈ 114.85 ⇒ **≈10.5 % of `T` ≈ 4141**; the k-loop is 73 % of that
⇒ **≈7.7 % of the step**. A 10 % loop improvement ≈ **+0.77 % of score** — which
§1 says is resolvable in **≲1 receipt pair on decode, and well under one on
prefill**.

Precedent for the dial itself: `DARKBLOOM_L5_UNROLL`
(`LagunaRuntimeModel.swift:3634–3641`), default 2, accepting 1/2/4/8. **Rule 33
applies**: a sweep arm must carry a distinct kernel-name suffix or the pipeline
cache serves one variant to both arms.

## 6. Where round 104 goes

Three things are now simultaneously true, and they compose into one plan:

1. A **0.5–1.0 %** lever is decidable in **2–3 receipt pairs** (§1).
2. We are **not quota-limited**, only wall-clock limited at ~13 min (§2).
3. There is a **specific, sized, bit-exact, never-measured-on-M5 lever** whose
   two prior measurements disagree in sign (§5).

So round 104 stops arguing and starts measuring.

* **104-A (flagship): the sliding-attention unroll-depth dial on M5.** Add
  `DARKBLOOM_SLIDING_PIPE_DEPTH` ∈ {1,2,4,8} selecting the k-loop unroll in
  `laguna_sliding_fused_attn_ring_v1`, **default 4 = zero behaviour change**,
  mandatory `_pdN` kernel-name suffix per rule 33. Bit-exact by
  accumulation-order preservation. M4 measurement is a **mechanism** check only,
  carrying the §4.1 wave caveat. This arm owns the receipt channel.
* **104-B: §4.15 cause 1 — the wk/wv M/N-tile regroup.** In
  `Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/matmul.cpp` at lines
  664–684, the existing `darkbloom_steel_prefill_tile` predicate requires
  `K > 4096` and therefore **does not cover wk/wv at (M=512, N=1024, K=2048)**,
  which lands on an 8×8 = 64-threadgroup grid = 1.6 TGs/core on 40 cores.
  **Only `bm`/`bn` may move — never `bk`**, because `bk` changes K-accumulation
  order and breaks bit-exactness, while M/N tiling does not.

  > 🔴 **CORRECTION (fern, #585 §1.4 — this brief named the wrong edit site).**
  > `darkbloom_steel_prefill_tile()` is defined at `matmul.cpp:82-88` and has
  > **exactly one call site, `matmul.cpp:674`, inside `steel_gemm_splitk_axpby_nax`
  > (`:645`)**. wk/wv **never enters that function on M5**. Fern traced the live
  > call chain predicate-by-predicate: `Matmul::eval_gpu :1206` → gemv shortcut
  > `:1252` false → `steel_matmul :1274` → `matmul.h:105,:123` →
  > `steel_matmul_axpby :827` → `use_nax :894-896` **true** → non-NAX split-K
  > `:900-901` fails → **NAX split-K `:922-924` false** → `:957` →
  > `steel_matmul_regular_axpby_nax :958`. The only working lever for this shape
  > is therefore inside **`steel_matmul_regular_axpby_nax` (`:186`), tile
  > selection `:213-221`, grid `:280-308`** — a different function from the one
  > this section named. Lines 664–684 are the wrong address.
  >
  > 🔴 **RULE-83 SELF-VIOLATION.** This brief is an unwitting re-proposal of
  > **PR #293** (`research/maple-tanjiro-nax-skinny-tile.md`, assignment
  > `maple-2026-08-07l-nax-skinny-tile` r2, base `69178729`), which added
  > `darkbloom_steel_regular_skinny_tile()` / `DARKBLOOM_STEEL_REGULAR_SKINNY_TILE`
  > with the guard `bn==128 && wn==4 && (N%64)==0 && tiles_m>=4 &&
  > tiles_m*tiles_n<=96 ⇒ bn=64, wn=2` — the same mechanism, at the same site,
  > with a guard that differs only in the modulus. It earned **zero ranked M5
  > receipts** (r1 slot-blocked, r2 blocked by 18 consecutive `failed`/`n/a`
  > receipts), was merged inert, and was then **silently deleted by frontier
  > resync `99b974c`**. I ran the rule-83 grep on the *shape* and missed the
  > *mechanism*. See §14.2 for what the correct grep would have found.
* Every brief carries the rule-83 grep **with §3 above as the cautionary
  example**, rule-72 preregistered nulls, rule-75 digests, rule-79 identical-code
  null, rule-80 GB/s ÷ host peak, rule-77 dispatch geometry, K ≥ 16, discard the
  first leg, and an **explicit receipt budget**.

### 6.1 The slate as assigned (base `9527bb72`)

| PR | student | arm | file owned | receipts |
|---|---|---|---|---|
| **#584** | nezuko | 104-A — `DARKBLOOM_SLIDING_PIPE_DEPTH` ∈ {1,2,4,8}, default 4 | `Sources/MLXFastModel/LagunaRuntimeModel.swift` | **8 (4 pairs)** |
| **#585** | fern | 104-B — wk/wv M/N-tile regroup, `bm`/`bn` only | `Vendor/…/backend/metal/matmul.cpp` | 0 (next round) |
| **#586** | tanjiro | 104-C — 237-dispatch prefill steel census + H8 audit | none (audit-only) | 0 |
| #571 | frieren | 103-A carryover, still `wip` | — | 0 |

File ownership is disjoint by construction, so the three can run concurrently.

**The one deliberate dependency**: tanjiro's census *is* fern's preregistered
null N-C (the enumeration of every shape her widened predicate captures). He
publishes it machine-readable and posts a pointer on #585 before his own
writeup is done; she does not block on him, and both derive the
(512, 1024, 2048) routing **independently**. Two independent derivations that
agree is evidence; one copied twice is not. A disagreement is to be surfaced on
both PRs, not reconciled quietly — learning the routing is wrong from a source
read is far cheaper than learning it from an unmoved `cand_pre`.

Tanjiro also preregisters **N-B: the tail deficit is diffuse, not concentrated.**
§4.15 asserts concentrated, and **fern's entire premise depends on it.** If the
census comes back diffuse, 104-B shrinks even with a perfect routing claim.

### 6.2 Bit-exactness of the depth dial is settled in advance

`research/advisor_r104_depth_coverage.py` (on the base) proves it rather than
hoping for it: for `d ∈ {1,2,4,8}` the loop
`int i = sg; for (; i + (d-1)*BN < N; i += d*BN)` consumes slots
`i, i+BN, …, i+(d-1)*BN` **in that order**, and all four depths yield the
**identical slot sequence per simdgroup** — 16 slots each, 32 simdgroups
covering 0..511 exactly once. Per-simdgroup accumulation order is **invariant
across the dial**, and no tail loop is needed anywhere because `16 % d == 0` for
all four. Bit-exactness is a construction property; a non-bit-exact arm is an
implementation bug, not a physics result. This removes the usual dominant risk
from an attention-kernel sweep.

### 6.3 🔴 The compiler cannot collapse the depth dial — and we are not allowed to let it

The dominant *silent* failure mode of an unroll sweep is that the compiler
already unrolls the loop, so every arm compiles to the same machine code and the
sweep measures pure noise while looking like a clean null. I checked whether
that can happen here. It cannot, and the reason is worth recording because it
also closes an adjacent lever before anyone spends a round on it.

**Three facts, all verified at base `9527bb72`:**

1. **No `#pragma unroll` anywhere in the sliding kernel.** The only unroll
   pragmas in `LagunaRuntimeModel.swift` are at `:2560-2584`, `:2644-2668`,
   `:2735-2774`, `:2825-2864`, `:3216-3224`, `:4387`, `:4771`, `:4947-4954` —
   all in *other* kernels. The a→b→c→d pipelining in the k-loop is entirely
   hand-written source replication.
2. **The trip count is not statically provable.** `N` and `BN` are `constexpr`
   (`:1526`, `:1522`), but the loop starts at `int i = sg` where
   `sg = simdgroup_index_in_threadgroup` is a *runtime* value. The trip count is
   4 only because `sg ≤ 31`, and the compiler has no such bound.
3. **It has no such bound because the JIT wrapper does not give it one.**
   `Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/common/metal_kernel.cpp:90`
   emits a bare `[[kernel]] void <name>(` — **no
   `max_total_threads_per_threadgroup` attribute**. Contrast the built-in steel
   and gemv kernels, which all carry
   `[[kernel, max_total_threads_per_threadgroup(WM*WN*32)]]`.

⇒ **The hand-written depth is the only unrolling this kernel will ever get.**
That validates the 104-A dial as a real ISA-level lever rather than a source-level
fiction. It does *not* excuse assuming so: a compiled-artifact identity check
across the four arms is cheap and must gate the receipt spend, because two arms
that compile identically would burn the round's entire budget on noise.

**The adjacent lever is structurally closed — do not chase it.** The obvious
follow-on ("give the compiler the bound and let it unroll") is unavailable twice
over:

* `backend/common/metal_kernel.cpp` is **not in `editablePaths`** (97 entries;
  none under `backend/common/`, only `backend/metal/**` and `mlx-generated/**`).
* The signature is machine-generated around the user's `source` string, which
  supplies only the *body*. There is no seam through which a kernel author can
  inject an attribute into `[[kernel]] void <name>(`.

Prior art check (rule 83): `max_total_threads_per_threadgroup` appears in
`research/` only twice, both observational and on other kernels —
`maple-fern-pr71-routed-qmv-bandwidth.md:323` notes its *absence* on the routed
QMV kernel, and `maple-tanjiro-nax-skinny-tile.md:83-85` confirms it resolves as
intended on the steel path. The archive has **zero** hits. Nobody has proposed
adding it, and now nobody should.

## 7. Do not re-derive these

* The receipt-power table in §1. It is measured, not modelled.
* The absence of a receipt quota (§2). Do not re-audit the corpus for it.
* The two-mechanism inventory (§4). It has an A/A control and a byte-level null.
* That an M4 A/B cannot rank the two attention mechanisms (§4.1).
* §8 of `advisor-r103-what-winning-costs.md` is retracted (§3a). Do not revive
  the threadgroup-memory cliff.
* `DARKBLOOM_FUSED_QKV` (§3b) and the H7 rescale skip (§3c) are dead.
* The record-watch arithmetic in §8. Re-run `research/advisor_r104_record_watch.py`
  to *refresh* it; do not re-derive the pricing model by hand.
* Env gates are frozen at first touch (§9). Do not propose flipping any
  `DARKBLOOM_*` / `MLX_*` gate inside a live process, and do not re-audit the
  binding scope by hand — re-run `research/advisor_r104_env_gate_scope.py`.
* The gate inventory in §10. There is **no** dormant-win shortlist: all ten
  default-OFF gates already carry a research write-up. Do not re-scan the
  surface by hand and do not "discover" a dormant flag — re-run
  `research/advisor_r104_gate_inventory.py`, which is idempotent and excludes
  its own artifacts from the prior-work count. The open question §10 leaves is
  the *opposite* one: the 76 default-**ON** kill switches, none of which has
  been re-measured since it shipped.
* That no commit has ever produced two receipts (§11). Do not propose
  resubmitting a fixed tree to farm `L` draws, and do not plan a replicated
  submission without producing one distinct commit per receipt and *verifying*
  `git diff --numstat a b -- Sources` is empty between replicates.
* The gate provenance in §12. **All 76 default-ON gates are post-migration.**
  Do not revive "some of these were tuned on Gemma"; do not re-date the surface
  by hand — re-run `research/advisor_r104_gate_provenance.py`. Do not use its
  churn ranking as a priority order: churn ≈ age for a 384 KB single file. The
  only shortlist is the seven silent switches, headed by
  `DARKBLOOM_FUSED_ROUTED_DOWN_REDUCE` and `DARKBLOOM_FUSED_SHARED_DOWN_RESIDUAL`.
* The additivity argument in §13. Decode-only and prefill-only changes have no
  interaction term — that is algebra, not an empirical claim. What is *not*
  settled is whether either arm's effect size transfers, which is why §13.4
  preregisters the composed receipt.
* **The prefill millisecond ledger in §14.3.** 1146 calls, 540.394 ms, zero
  residual, anchored to 2 µs. Do not build another prefill attribution; do not
  quote a receipt-differenced marginal prefill rate (§14.2 shows one that
  exceeds the hardware ceiling by 17 %). Re-run
  `research/artifacts/tanjiro-r104c/steel_ms_attribution.py`.
* **The `_nax` routing of (M=512, N=1024, K=2048) in §14.6.** Derived twice
  independently, and reproduced 237/237 by
  `research/artifacts/tanjiro-r104c/steel_route_model.py`. It goes to
  `steel_matmul_regular_axpby_nax`, not split-K, by a double exact equality.
* **The two prefill prices in §14.7.** partial 0.2592 %/ms for reading a
  receipt, total 0.3781 %/ms for pricing a prospective change. State which one
  you used; do not re-derive them.
* **§14.10: local-iterate deltas are not evidence.** Do not re-run an
  identical-code local A/A to convince yourself. It has been done, it gave
  +0.9 % on inert code, and it is ≈4× noisier than the receipt channel.

## 8. 🔴 The record is not winnable by luck — it is winnable only by ~1.4 % of `cs`

Refreshed live from the MLXFast API at 2026-08-09T23:20Z with
`research/advisor_r104_record_watch.py` (read-only; canonical field names per
rule 58, taken from `research/advisor_r103_freeze_corpus.py`).
Corpus: **1,775 raw records, 1,206 metric-bearing, 147 accepted.**

> **Re-verified 2026-08-10T00:07Z.** Corpus now 1,207 metric-bearing, still 147
> accepted; the record is unchanged and 41 receipts have landed since it. Every
> number in §8 stands. Re-run the script rather than trusting this line.

### 8.1 The standing record has not moved in 38 hours

```
2026-08-08T09:17:33Z   a-github-name   score 2.616504   cs 2.574594   L 1.016278
                       decode 4930.057 us/step          prefill 188.1589 us/tok
```

* **41 metric-bearing receipts have landed since that record. Zero were accepted.**
  That is not a surprise and it is not evidence of anything new: at the
  round-103 acceptance rate for a Δcs = 0 tree (0.095 % per receipt),
  P(0 accepts in 41) = **96.2 %**.
* **65 of 1,206 receipts in the whole corpus have a *better* `cs` than the
  record's `cs`.** The record is not the fastest tree ever measured. It is a
  mid-pack tree that drew an extraordinary `L`.
* Record `L = 1.016278`. Against the corpus median `L = 0.998572` and
  `sd(ln L) = 0.5363 %`, that is **+3.28 σ ⇒ a p99.95 draw**.

⇒ **`L`, not `cs`, is what makes the record unreachable.** This is §3 of
`advisor-r103-what-winning-costs.md` restated on 38 hours of fresh data.

### 8.2 What it now costs to take the record

To beat `score = 2.616504` at the *median* draw `L = 0.998572` you need

```
cs >= 2.616504 / 0.998572 = 2.620246
   = +1.438 % over our honest tree cs 2.583111
   = 94.4 us/step of decode   (1 % of cs = 65.67 us/step)
```

Live-reproduced pricing (P(record) per receipt as a function of how much real
`cs` we bring, and the receipt count `n` at which P(≥1 record) = 50 %):

| Δcs vs our honest tree | P(record) / receipt | n @ 50 % |
|---|---|---|
| +0.00 % | 0.095 % | 731.4 |
| +0.25 % | 0.519 % | 133.2 |
| +0.50 % | 2.165 % | 31.7 |
| +0.75 % | 6.941 % | 9.6 |
| +1.00 % | 17.340 % | 3.6 |
| +1.25 % | 34.354 % | 1.6 |
| +1.50 % | 55.325 % | 0.9 |
| +2.00 % | 88.557 % | 0.3 |

Nezuko's round-104 budget is 8 receipts. P(≥1 record) across those 8:

| Δcs | P(≥1 record in 8) |
|---|---|
| +0.00 % | **0.76 %** |
| +0.50 % | 16.06 % |
| +1.00 % | 78.20 % |
| +1.50 % | 99.84 % |

**Operational consequence:** at Δcs = 0 an eight-receipt round buys a **0.76 %**
chance of a record — and, spent as 4 paired contrasts, a **±16.7 µs/step**
measurement of a real dial (§1). One of those two outcomes is nearly certain and
the other is nearly impossible, so the allocation decision is not close: **spend
receipts as an instrument, not as a lottery ticket.** Nobody on this team should
tune a submission to avoid rejection, or spend a spare receipt hoping for a
draw. Rejected receipts carry full `cand_dec` / `cand_pre` (§2) — a rejection is
a free measurement.

### 8.3 The record is sticky, so the bar is not about to move under us

The field is producing roughly **25 metric-bearing receipts/day**. If the field
sits near our own `cs`, the expected wait for *anyone* to reproduce a p99.95
draw is `1 / 0.00095 ≈ 1,050 receipts ≈ 42 days`. The 38-hour, 40-receipt
drought is exactly what that model predicts.

⇒ **This record will not fall to luck, ours or anyone's. It falls to a real
`cs` improvement of order 1.4 %.** That is the number round 104's levers have
to be sized against:

| round-104 lever | modelled size | vs the 1.438 % bar |
|---|---|---|
| 104-A sliding-attention pipe depth (§5) | ≈ +0.77 % of score for a 10 % k-loop win | **short on its own** |
| 104-B wk/wv steel tile regroup (§4.15 cause 1) | central **3–6 ms** ⇒ +1.13 % … +2.27 %; ceiling ≈9.33 ms ⇒ +3.53 % | **can clear it — conditionally** |
| 104-C prefill steel shape census (→ §11.8 H8, audit-only this round) | ~6 ms ⇒ +1.6 % *if* dense projections are below 52 TFLOP/s | clears it alone |

⚠️ **Sizing discipline for the 104-B row.** Those numbers are the recoverable
envelope for the **whole** prefill tail, not for wk/wv alone. Per the §4.15
reconciliation carried in `advisor-r103-*`: §4.13's 12.30 ms and §4.15's 11.40 ms
**overlap by ≈9.33 ms and must never be added**; cause 3 (2.5–3.0 ms of peak
margin) is definitionally unrecoverable; and cause 4 is an *alternative
attribution* of cause 1, not an additional pool. wk/wv at (512, 1024, 2048) is
**one shape family inside that tail**. So 104-B is the only round-104 lever that
can plausibly clear 1.438 % on its own, and whether it actually can is exactly
what tanjiro's preregistered **N-B — "the tail deficit is diffuse, not
concentrated"** decides. If the census returns diffuse, 104-B shrinks even with
a perfect routing claim, and no round-104 lever clears the bar unaccompanied.
Do not quote a wk/wv-specific millisecond figure until the census supplies one.

This is the honest reason 104-B and 104-C are prefill work and 104-A is a
measurement-grade dial: **the decode side does not have 1.4 % lying around, and
the prefill side might.**

### 8.4 🔴 Competitive intelligence: our `cs` lead is over the record holder, not over the field

A new entrant, **`fyrsta7`**, first appeared 2026-08-09T14:43:45Z and produced
5 receipts in ~3 hours:

```
cs: 2.574051, 2.582983, 2.585463, 2.589921, 2.580958
geometric mean cs = 2.582670  =  -0.017 % vs our honest cs 2.583111
z = -0.21   95 % CI on the difference: [-0.180 %, +0.146 %]   => PARITY
```

Their own spread across those 5 receipts, `sd(ln cs) = 0.2273 %`, is
statistically indistinguishable from our *identical-code* noise floor of
0.1860 % (χ² = 5.97 on 4 dof, p ≈ 0.20) — i.e. **their five receipts are
consistent with one fixed tree measured five times.** They did not climb to
parity; they arrived at it.

`yudduy` is also active: best-3 geometric-mean `cs = 2.578718` = −0.170 % vs
ours, 95 % CI `[-0.381 %, +0.040 %]` — **also parity**, not measurably behind.
`metaspartan` and `MyatKaung` are producing receipts as well.
Reproduce with `research/advisor_r104_field_parity.py`.

**Read this honestly.** Round 103 recorded that our honest tree is +0.331 %
ahead of *the record's* `cs`. That statement is still true and it is now also
misleading: the record holder's tree is not the frontier of the field. At least
one solver reached our `cs` from a standing start in three hours, and a second
is statistically level with us. We do not have a defensible `cs` moat — we are
one of at least three trees inside a ±0.2 % band. What we have is §1 —
a calibrated receipt channel and a two-mechanism inventory (§4) that tells us
*which* bytes moved. Nobody else is publishing that they have one.

Do not respond to this by spending receipts faster. Respond to it by making
§8.2's 1.4 % real.

## 9. 🔴 Env gates are frozen at first touch — "in-process flag flipping" is impossible

**I put a false statement in frieren's #571 brief and I am retracting it here.**
I wrote that the R3 router-prefetch mechanism could be A/B'd *in-process* with
`DARKBLOOM_ROUTER_WEIGHT_PREFETCH=0`, buying "within-process σ ≈ 19.5 vs
≈ 48 cross-process, ~2.5× tightening". The first half is wrong, so the second
half does not apply.

### 9.1 The measurement

`research/advisor_r104_env_gate_scope.py` classifies every runtime env read in
`Sources/` + `Vendor/` by *binding scope* — i.e. whether the value can still
change after the first read:

```
total env-read sites found: 132
  swift-global-let    111      <- frozen: Swift global `let`, lazily init'd once
  cpp-static            6      <- frozen: function-local `static` + IIFE lambda
  cpp-function-body     3      <- Vendor distributed/ring code only
  unclassified         12      <- 10 in Vendor tests/server/jaccl; 2 in Sources
distinct gates seen: 129
```

**117 of 132 sites (88.6 %) are provably frozen for the lifetime of the
process.** The canonical shapes:

```swift
// Sources/MLXFastModel/LagunaRuntimeModel.swift:690
let lagunaRouterWeightPrefetch: Int = {
    guard let raw = ProcessInfo.processInfo.environment[
              "DARKBLOOM_ROUTER_WEIGHT_PREFETCH"], ... }()
```
```cpp
// Vendor/.../backend/metal/matmul.cpp:82
static bool darkbloom_steel_prefill_tile() {
  static bool enabled = []() { ... getenv(...) ... }();   // read once, ever
  return enabled;
}
```

The two `Sources/` sites the classifier could not bind
(`LagunaRuntimeWeights.swift:381`, `:517`) were read by hand: both are
**init-time** paths (a `setenv` defaulting block, and the one-shot kernel-cache
warmup). Neither is a per-step read. The remaining 10 unclassified sites are
Vendor test, server-CLI and `jaccl` distributed code that this benchmark never
enters.

⇒ **No `DARKBLOOM_*` or `MLX_*` gate can be flipped inside a live process.**
`setenv` after first touch changes nothing. Every env-gate contrast is
necessarily **one process per arm**.

### 9.2 What survives, and it is better than what I claimed

The codebase states the intended pattern itself, at
`LagunaRuntimeWeights.swift:380`:

> `// Explicit MLX_ values win; DARKBLOOM kill switch supports same-binary A/B.`

**Same-binary**, not same-process. That is still a real and unexploited asset,
because the correct comparison was never within-vs-cross *process* — it is:

| channel | binary | process | removes | σ |
|---|---|---|---|---|
| σ_rebuild | different | different | nothing | the ladder's ≈ 48 µs/step |
| **σ_launch** | **byte-identical** | different | compiler/codegen, JIT library set, link order, binary layout | **never measured by anyone** |
| platform identical-code (§1) | rebuilt by grader | different | — | sd(T) = 12.079 µs/step on M5 |

σ_launch is bounded above by σ_rebuild and below by nothing we know. The gap
between them *is* the build-noise component, and it has never been separated.

Note the tension the table exposes: **the platform's own repeated measurement of
byte-identical `Sources/` achieves sd(T) = 12.079 µs/step (§1), while our local
M4 harness is quoted at ≈ 48.** If that ≈ 48 is real, local measurement
discipline — not the platform — is the binding constraint on every A/B we run,
and it is costing us ~16× in legs (variance ratio). Measuring σ_launch is how we
find out.

### 9.3 Why this matters beyond one contrast

There are **106 distinct `DARKBLOOM_*` gates** and 20 `MLX_*` gates in the tree.
§3(b) showed one of them (`DARKBLOOM_FUSED_QKV`, default OFF) is a **+39.99 %
decode regression** — these switches carry real, large, *already-written* code
paths. §4 showed Mechanism B (the 4-deep sliding pipe) shipped with **no env
guard and was never re-measured at all**. A calibrated same-binary channel turns
"which of 126 switches matters" from a rebuild-bound question into a
launch-bound one.

⚠️ When I first wrote this section I went on to claim that cheap ranking over a
"large dormant inventory" was a way to find another lever. **I then measured the
inventory and that claim is false.** See §10. The instrument is still worth
building; what it buys is not a search for dormant wins.

**The instrument must be validated before it is believed.** A same-binary rig
needs (a) an A/A null that does *not* reject, and (b) a positive control that
*does*, with the right sign. Good positive controls here are kill switches on
default-ON paths, whose fallback code is therefore maintained:
`DARKBLOOM_FUSED_SLIDING_ATTN=0` (`LagunaRuntimeModel.swift:1504`, default ON,
disables a ≈ 636 µs/step M4 kernel) and `DARKBLOOM_FUSED_FULL_ATTN=0`
(`:2010`, default ON). `DARKBLOOM_FUSED_QKV=1` (`:113`, default OFF) is a
second, with a known sign and a known ≈ +39.99 % magnitude.


## 10. 🔴 There is no dormant-win inventory — there are 76 unaudited shipped optimizations

I claimed in §9.3 that the 126-gate surface was a cheap place to hunt for a
dormant lever. Then I measured it, and the claim died the same way §3's three
hypotheses died. `research/advisor_r104_gate_inventory.py` classifies every gate
on the **executed** path (excluding Vendor tests, server CLI and `jaccl`) by the
default it takes when the variable is absent, and cross-references how many
`research/` files have ever mentioned it:

```
executed-path env gates: 110
  default ON    76      <- kill switch on a SHIPPED optimization
  default OFF   10      <- dormant
  default DIAL  11      <- non-binary tuning knob
  default ?     13      <- mostly Vendor plumbing, hand-checked below

SHORTLIST (default-OFF, never written up, symbol actually used): 0
BOUND BUT NEVER USED (dead gate):                                0
```

### 10.1 The dormant set is ten gates, and every one is already spoken for

| gate | research docs | what it is |
|---|---|---|
| `DARKBLOOM_TRACE_FUSION` | 15 | tracing, not an optimization |
| `DARKBLOOM_STEEL_TRACE` | 3 | tracing, not an optimization |
| `DARKBLOOM_FUSED_QKV` | 11 | **measured +39.99 % decode (§3b)** — a rejected experiment |
| `DARKBLOOM_ATTN_SCALE_NARROW_LOG` | 7 | 18 research files |
| `DARKBLOOM_SHARED_FIRST_DOWN` | 9 | 10 research files |
| `DARKBLOOM_ROPE_ATLAS_VIEWS` | 4 | |
| `DARKBLOOM_QMV_WIDE_CODES` | 3 | |
| `DARKBLOOM_PREFILL_ROUTER_TOP8` | 3 | |
| `DARKBLOOM_NATIVE_AFFINE_SUFFIX` | 2 | |
| `DARKBLOOM_FUSED_FULL_ATTN_WHOLE_MODEL_WARMUP` | 1 | |

**Every default-OFF gate has ≥ 1 prior research write-up.** Two are pure
tracing. These are not unmeasured dormant code — they are **rejected
experiments left in the tree behind a switch**. `DARKBLOOM_FUSED_QKV` is the
archetype: it is OFF *because* it loses by 40 %. Flipping default-OFF gates on
is, on the prior evidence, a way to find losses.

⇒ **Rule 83 applies to the whole dormant set.** Do not propose enabling one of
these without first reading its existing write-ups.

### 10.2 What the surface actually is: an unaudited ablation ledger

The real shape of the tree is **76 kill switches guarding optimizations we have
already shipped and turned on**. Each one was added because it won *at the time
it was added*. None has been re-measured since the tree changed underneath it.

That is a different and, I think, better opportunity than the one I claimed:

* An optimization worth +30 µs/step forty rounds ago may now be worth **zero**,
  because a later fusion subsumed it.
* It may now be worth **less than zero**. A shipped optimization that has
  quietly become a pessimization is a **free win that costs one flag flip** —
  no new code, no correctness risk, and it is bit-exact-or-not exactly as it
  already is today.
* The ledger is also the honest map of where decode time lives on *this* tree,
  which is worth more than any model of where it ought to live.

§8.2 says we need **+1.438 % of `cs`** and that no single live lever reaches it.
Recovering regressions hidden inside our own stack is a genuinely different
route to that number than inventing a new kernel, and it is the one route whose
unit cost is a process launch rather than a round of student time.

**Seven kill switches are shipped, ON, and mentioned nowhere in `research/` at
all** — zero files, not merely zero docs:

```
DARKBLOOM_FUSED_SHARED_DOWN_RESIDUAL    LagunaRuntimeModel.swift:137
DARKBLOOM_FUSED_ROUTED_DOWN_REDUCE      LagunaRuntimeModel.swift:199
DARKBLOOM_PREFILL_FUSED_RESIDUAL_RMS    LagunaRuntimeModel.swift:280
DARKBLOOM_PREFILL_SORTED_MOE_TAIL       LagunaRuntimeModel.swift:9677
DARKBLOOM_ROUTE_COUNTING_SORT           SwitchLayers.swift:78
DARKBLOOM_INVERSE_SCATTER               SwitchLayers.swift:64
DARKBLOOM_ROUTE_FUSED_SCATTER           SwitchLayers.swift:187
```

That is the first page of the ledger, and it is a **rule-83-clean** list by
construction: the script's `research_files == 0` column *is* the archive check.

### 10.3 Order of operations

The ledger is worthless without the instrument, and the instrument is worthless
unvalidated. So the order is fixed:

1. **σ_launch** — frieren, #571, this round. Until we know the resolution of a
   same-binary relaunch contrast, every entry in the ledger is an unbounded
   claim. If σ_launch is no better than the ≈ 48 rebuild figure, the ledger is
   unaffordable and §10 dies here; that is a real outcome and #571 is
   preregistered to report it.
2. Only then, rank the 76. Cheapest first, decode-hot-path first.

> **Amended by §12.** The ranking prior in §10.2 was written on the assumption
> that some of the 76 predate the Gemma → Laguna migration and were therefore
> tuned against a model we no longer run. **That is false — all 76 are
> post-migration** (§12). The ledger still exists and the seven silent switches
> are still the first page of it, but the expected yield is lower than this
> section claims, and step 2 above is now a *lower-value* program than step 1
> was chosen to unlock. Read §12 before spending anyone on it.

Do **not** start ablating gates before step 1 finishes. A ledger of 76
uncalibrated deltas is 76 opportunities to fool ourselves, and §3 is the record
of how easily I do that.

### 10.4 Dials

Eleven gates take a non-binary default. Two are already spoken for this round
(`DARKBLOOM_ROUTER_WEIGHT_PREFETCH`, default 1, 13 docs — frieren's C2;
`DARKBLOOM_L5_UNROLL`, default 2, 3 docs — nezuko's precedent). The others,
with their defaults, are in
`research/artifacts/advisor-r104-gate-inventory.json`. Note
`DARKBLOOM_ROUTER_ROWS_PER_GROUP` (default 8, 6 docs) and
`DARKBLOOM_DECODE_ASYNC_STAGE` (8 docs) are heavily trodden; check the archive
before touching either.


## 11. 🔴 The draw cannot be replayed — one receipt per commit, ever

§2 says the platform imposes no receipt quota. §8 says the standing record is
held by an `L` draw near p99.95 and that `L` is an exchangeable lottery nobody
can steer. Put those together and an obvious, ugly strategy appears: stop
optimising, take our best tree, and press resubmit until a good draw lands.
§8.2 even prices it — 0.095 % per receipt at Δcs = 0, so ~731 draws for a
coin-flip.

Before ever recommending against that on taste, I checked whether it is
mechanically possible. It is not, in its cheapest form.

`research/advisor_r104_duplicate_sha_draws.py` (read-only, canonical field
names per rule 58) over the live corpus at 2026-08-10T00:05Z:

```
pulled 1775 raw submission records
1166 metric-bearing receipts that carry a submissionCommitSha
metric-bearing receipts with NO submissionCommitSha : 41
  first 2026-07-24T07:24:49Z   last 2026-08-09T03:49:43Z
  by solver: a-github-name=5, Gajesh2007=3, lBroth=3, morganmcg1=3,
             saucegodbased=2, ashhart=2, GumbiiDigital=2, benbuschmann=2
  accepted among them: 9

distinct shas                 : 1166
shas submitted more than once : 0
verdict: NO-REPEAT
```

**1,166 sha-bearing receipts, 1,166 distinct shas. Not one commit in the
history of this challenge has ever produced two receipts.** Across ~20 solvers,
17 days, and a solver who managed 39 receipts in a single day (§2), nobody has
ever replayed a commit. Whether that is platform enforcement or universal
practice cannot be distinguished from the corpus, but planning must assume it:
**a receipt costs a distinct commit.**

### 11.1 A correction I owe the record

I had been carrying the inference that fern's #576 count — "1,205 receipts,
1,164 distinct `submissionCommitSha`" — implied 41 duplicate commits. It does
not. The gap is exactly the **41 metric-bearing receipts that carry no commit
sha at all**, which a distinct-count collapses into a single bucket. Those 41
are spread across at least eight solvers and the entire 17-day window, so they
are a sporadically-absent field, not a schema epoch. Nine of them are
`accepted`, i.e. **9 of the 147 global records cannot be attributed to a
commit** — a standing caveat on any archaeology of the record ladder.

### 11.2 What this closes, and what it does not

It closes the free version of the farming strategy. It does **not** close the
strategy outright, because a fresh commit is nearly free: any no-op edit
produces a new sha. So the honest statement is that farming remains
mechanically available and we are choosing not to do it. The reasons are
technical, not moral:

1. **It does not produce a speedup.** §8.1 already shows the record holder's
   tree has `cs` **0.331 % worse than ours**; its entire lead is a +3.28 σ `L`
   draw. Reproducing that trick yields a number on a leaderboard that our code
   did not earn and that will not survive its own re-measurement.
2. **It is dominated on its own terms.** §8.2 prices a draw at 0.095 % at
   Δcs = 0 and at 17.340 % at Δcs = +1.0 %. The exchange rate between
   engineering and luck is therefore **≈ 182 draws per 1 % of `cs`**. Round
   104's slate — 104-A ≈ +0.77 %, 104-B central 3–6 ms ⇒ +1.13…+2.27 %,
   104-C ≈ +1.6 % if the dense projections are below 52 TFLOP/s — is worth
   several hundred draws if any of it lands.
3. **It would eat the instrument.** §1 established that our receipts are our
   only M5 measurement channel. Receipts spent on draws are receipts not spent
   on contrasts.

### 11.3 The operational consequence — this one bites this round

Every receipt requires a distinct commit sha. That is a trap for any
**replicated** design, because a plan that says "measure the baseline tree four
times" silently means "produce four commits whose `Sources/` trees are
byte-identical and whose shas differ."

That works — it is precisely how §1's identical-code floor was measured, from
six groups with n up to 5. Content-identical trees are not deduplicated. But it
must be **verified, not assumed**:

```
git diff --numstat <commit_a> <commit_b> -- Sources    # must print nothing
```

Achieve the distinct sha by touching something **outside** `Sources/` (a
`research/` note will do). Do not achieve it by editing `Sources/`, because
that destroys the byte-identity the replicate depends on, and §1's floor is
only a floor for genuinely identical code.

There is a bonus hiding in this. A design whose baseline tree is repeated k
times yields, for free, an identical-code group of size k **on the current
tree** — a direct re-measurement of §1's noise floor at today's base rather
than at the bases fern's provenance work happened to cover. That is a real
secondary deliverable at zero marginal cost, and it should be reported.

### 11.4 A note on solver-name contamination

The refreshed record watch shows **16 receipts on 2026-08-09 alone under
`morganmcg1`**, at a moment when no maple student had submitted anything. The
`morganmcg1` solver account is shared across campaigns. Therefore:

* Never attribute receipts to this campaign by `solverUsername`. Attribute by
  `submissionCommitSha`, which is 1:1 with a receipt (§11).
* The "8 receipts this round" budget is a **campaign** budget I imposed, not a
  platform one (§2). Concurrent traffic under the same name is not a hazard to
  any individual measurement — each receipt is benchmarked independently — but
  it does mean the standing record can move underneath us from inside our own
  org, and §8's pricing table is only valid until it does.



## 12. 🔴 The "gates tuned on the wrong model" hypothesis is dead — all 76 are post-Laguna

§10 found 76 shipped, default-**ON** kill switches that have never been
re-measured, and §10.2 argued they are worth ranking. The implicit prior behind
that argument was that some of them are *old* — introduced while the serial
track still ran Gemma 4 31B, tuned against a model with different shapes, and
carried forward unexamined onto Laguna XS 2.1. A gate in that population would
be a genuinely good bet: it was chosen to help a model we no longer run.

`research/advisor_r104_gate_provenance.py` tests that prior directly and it is
**false**.

### 12.1 Method

For each of §10's 110 executed-path gates, the script asks git when the gate
literal first entered the file that reads it:

```
git log -S<GATE> --reverse --format=... -- <path>
```

and classifies the introducing commit against the migration commit
`4799830b`, 2026-07-21, *"Migrate serial track: Gemma 4 31B → Poolside Laguna
XS 2.1"*. It also counts **churn** — commits touching the guarded file since the
gate was introduced — and carries forward §10's `research_docs` mention count.
Output: `research/artifacts/advisor-r104-gate-provenance.json`
(`migration`, `n_gates`, `era_by_polarity`, `shortlist`, `default_on_ranked`).

Context for the dating: the repository is **1,572 commits** deep, of which
**74 touch `Sources/MLXFastModel/LagunaRuntimeModel.swift`**, and the earliest
of those 74 *is* `4799830b`. The file did not exist before the migration.

### 12.2 Result

```
introduction era, split by default polarity   (migration 4799830b, 2026-07-21)

polarity    pre-Laguna  post-Laguna   unknown
?                    2           11         0
DIAL                 0           11         0
OFF                  0           10         0
ON                   0           76         0

default-ON and PRE-Laguna                : 0
default-ON and unmentioned in research/  : 7
default-ON, PRE-Laguna AND unmentioned   : 0
```

**Every default-ON gate is post-migration.** So is every default-OFF gate and
every dial. Introduction dates run **2026-07-23 → 2026-08-09**, i.e. the entire
`DARKBLOOM_*` surface was built *for* Laguna XS 2.1, after the migration. The
only two pre-Laguna entries have polarity `?` — they are not kill switches at
all.

This is rule 83 for the fourth time this round (§3 has the other three). I
should have dated the file before I theorised about its contents; the check
cost one script.

### 12.3 What dies, and what that costs §10

Dead: *"some of the 76 were tuned on Gemma and are now pessimizations."* There
is no such cohort. Every one of the 76 was chosen, at least once, by someone
measuring the model we actually run, on hardware in the same family.

That materially lowers the expected yield of §10.2. The ledger argument was
never *only* the stale-tuning argument — a gate can still have been overtaken
by a later change to the code it guards, and none of the 76 has been
re-measured since it shipped — but the prior on any individual switch being a
net loss today is now much closer to the base rate for "an optimization someone
measured as a win a fortnight ago". §10.3's ordering is unchanged (σ_launch
first) but step 2 is a lower-value program than §10.2 claimed, and I have
amended §10.3 to say so in place.

### 12.4 The ranking, and why its main column is nearly worthless

The script ranks the 76 by churn-since-introduction. **That ranking is almost
entirely an age ranking, and I do not trust it.** Churn counts commits touching
*the file*, not commits touching the *guarded region*. For a 384 KB
single-file monolith like `LagunaRuntimeModel.swift`, essentially every commit
in the round touches the file, so churn ≈ (days since introduction) × (commits
per day). The three distinct churn plateaus in the output — 66…43 for the
2026-07-23/25 cohort, 36…16 for late July, exactly 10 for the thirty gates
introduced on 2026-08-03, 7…1 for August — are calendar strata, not evidence.

The one column that discriminates is `research_docs`, which is what §10.2
already used. The surviving shortlist is therefore unchanged: **the seven
silent switches of §10.2**, now dated:

```
rank gate                                     added       churn  site
  7  DARKBLOOM_FUSED_ROUTED_DOWN_REDUCE       2026-07-24    57   LagunaRuntimeModel.swift:199
  8  DARKBLOOM_FUSED_SHARED_DOWN_RESIDUAL     2026-07-25    54   LagunaRuntimeModel.swift:137
 22  DARKBLOOM_PREFILL_FUSED_RESIDUAL_RMS     2026-07-26    36   LagunaRuntimeModel.swift:280
 24  DARKBLOOM_PREFILL_SORTED_MOE_TAIL        2026-07-26    35   LagunaRuntimeModel.swift:9677
 73  DARKBLOOM_INVERSE_SCATTER                2026-08-06     1   SwitchLayers.swift:64
 74  DARKBLOOM_ROUTE_COUNTING_SORT            2026-08-06     1   SwitchLayers.swift:78
 75  DARKBLOOM_ROUTE_FUSED_SCATTER            2026-08-06     1   SwitchLayers.swift:187
```

Two refinements the dating does buy:

* The **SwitchLayers trio was introduced by a single commit** (`dec0a83c`,
  2026-08-06). Their silence is largely "young, and shipped together in one
  batch" — much weaker evidence of neglect than four independently-added,
  two-week-old switches. Rank them below the LRM four.
* The head of the shortlist is therefore **`DARKBLOOM_FUSED_ROUTED_DOWN_REDUCE`
  (2026-07-24) and `DARKBLOOM_FUSED_SHARED_DOWN_RESIDUAL` (2026-07-25)**: the
  two oldest switches in the codebase that nothing in `research/` has ever
  named, both on the decode MoE down-projection path, both with a full fortnight
  of subsequent change around them.

All seven live in files listed in `benchmark.json`'s `editablePaths`
(`Sources/MLXFastModel` is a directory entry;
`Vendor/mlx-swift-lm/Libraries/MLXLMCommon/SwitchLayers.swift` is an explicit
entry), so a *win* here would be shippable and not merely observable.

🔴🔴 **CORRECTION (r105, fern PR #598) — THE HEAD OF THIS SHORTLIST IS DEAD, AND
IT IS DEAD IN THE WORST WAY: THE TWO GATES I RANKED FIRST DO NOT EXECUTE.**

Fern measured all seven with a dispatch tracer over ten arms
(`research/fern-r105c-gate-surface-masking-audit.md`). Result:

| rank | gate | my r104 verdict | measured verdict |
|---|---|---|---|
| 7 | `DARKBLOOM_FUSED_ROUTED_DOWN_REDUCE` | head of shortlist | **DEAD** — trace site `LagunaRuntimeModel.swift:10949` never fires; arm `d` byte-identical to base |
| 8 | `DARKBLOOM_FUSED_SHARED_DOWN_RESIDUAL` | head of shortlist | **DEAD** — trace site `:9065` never fires; arm `e` byte-identical to base |
| 22 | `DARKBLOOM_PREFILL_FUSED_RESIDUAL_RMS` | live, not bit-exact | live (unchanged) |
| 24 | `DARKBLOOM_PREFILL_SORTED_MOE_TAIL` | live, bit-exact | live (unchanged) — **clean** |
| 73 | `DARKBLOOM_INVERSE_SCATTER` | rank below the LRM four | **DEAD BY DOMINATION** — reachable, but `SwitchLayers.swift:285` returns early first |
| 74 | `DARKBLOOM_ROUTE_COUNTING_SORT` | rank below the LRM four | live, but **dominates gate 75** — not an isolate |
| 75 | `DARKBLOOM_ROUTE_FUSED_SCATTER` | rank below the LRM four | live, bit-exact — **clean** |

Both decode-side gates fire through a *third*, fused site
(`lagunaFusedRoutedSharedDownResidual`, `:10922`, 39×/decode step) that
subsumes them. The two ranked heads of my shortlist are unreachable code.

Three things this costs, stated plainly:

1. **The ranking was inverted.** I ranked the SwitchLayers trio *below* the LRM
   four on an age-and-churn argument. Of the four I promoted, two are dead; of
   the three I demoted, two are live and one is clean. Age and churn were
   **anti-correlated** with liveness here. The `research_docs == 0` column was
   the only discriminator I had, and it discriminated in the wrong direction.
2. **The proxy was wrong in kind, not degree.** `research_docs == 0` measures
   *whether anyone wrote about a gate*. It cannot distinguish "nobody looked" from
   "nobody looked because it does nothing". Only a dispatch trace separates
   those. **New rule: a default-ON gate is not a candidate until a runtime trace
   shows its site executing in the phase you intend to price.**
3. **The shippability sentence above is now vacuous for gates 7, 8 and 73.** A
   file being in `editablePaths` says nothing about whether the code in it runs.

What survives: the two *clean* instruments are gate 24
(`DARKBLOOM_PREFILL_SORTED_MOE_TAIL`) and gate 75
(`DARKBLOOM_ROUTE_FUSED_SCATTER`) — both live, both bit-exact, both prefill-only.
And **§10's headline stands**: fern's dead-gate fraction came in at
`m = 3/79 = 0.0380`, below her own 0.05 prereg threshold, so "there is no
dormant-win inventory" is confirmed by measurement rather than by my inference.
Full account: `research/advisor-r105-the-decode-step-is-half-empty.md` §2.

### 12.5 Caveats to carry

* `research_docs == 0` means "the literal string does not appear under
  `research/`". A gate could have been measured in a PR body, in an organizer
  commit message, or under a different name. Silence is evidence of
  un-audited-ness; it is not proof.
* Nothing in §12 authorises flipping anything. Per §9 these are same-binary,
  different-process contrasts, and their resolution — σ_launch — is exactly
  what #571 is measuring this round. §10.3 step 1 still gates step 2.
* The script is read-only, idempotent, and takes its repo root from
  `MLXFAST_ROOT` (default: the checkout it lives in). Re-run it rather than
  re-deriving any of this by hand.


## 13. 🔴 The round-104 slate only pays if someone composes it — and nobody is assigned to

### 13.1 The arms are disjoint, and disjoint means additive

`ln cs = X − 0.75 ln cand_dec − 0.25 ln cand_pre`. Decode and prefill enter as
**separate additive terms in log space**. A change that moves only `cand_dec`
and a change that moves only `cand_pre` therefore combine with **no interaction
term at all**, and the 0.75 / 0.25 weights are already folded into every
score-% figure quoted in §5 and §8.3. Their score-% effects add exactly.

The three round-104 arms are disjoint in the strong sense — not merely
different files, but different execution paths:

| arm | PR | touches | path | measured in |
|---|---|---|---|---|
| **104-A** sliding-attn k-loop depth | #584 nezuko | `LagunaRuntimeModel.swift` | **decode only** — µs/**step** | M5 receipts |
| **104-B** wk/wv steel tile regroup | #585 fern | `matmul.cpp` | **prefill only** — steel GEMM at M=512 | M4 same-binary A/B |
| **104-C** prefill steel shape census | #586 tanjiro | audit-only | prefill | static |

Decode runs the GEMV/QMV path (89–98 % efficient, §4.10b); prefill runs the
steel path (237 dispatches, §4.15). 104-B's tile-selection block at
`matmul.cpp:664-684` is reached only when `(M+N)/2 ≥ 512`, which decode's
M=1 shapes never satisfy. File ownership is disjoint by construction (round-104
slate note). There is no plausible mechanism by which A and B interact.

### 13.2 The sum clears §8.2's bar; neither arm does

| arm | central score-% | source |
|---|---|---|
| 104-A | **+0.77 %** | §5: k-loop is ≈ 7.7 % of the step; a 10 % loop win |
| ~~104-B~~ | ~~+1.13 … +2.27 %~~ | ~~§8.3, from the 3–6 ms central tail estimate~~ |
| ~~**A + B**~~ | ~~**+1.90 … +3.04 %**~~ | ~~exact sum, §13.1~~ |
| **bar** | **+1.438 %** | §8.2: `cs ≥ 2.620246`, i.e. 94.4 µs/step |

**Neither arm reaches the bar alone. The pair does, in its central case.** That
is the entire strategic content of the round-104 slate, and it is stated here
for the first time — the assignment briefs each argue their own arm on its own
merits, as they should, and none of them says this.

104-C pays indirectly: it is fern's preregistered null N-C, and its N-B result
("is the prefill deficit concentrated or diffuse?") is the premise 104-B rests
on. If N-B says diffuse, 104-B's central estimate collapses and so does the sum.

> 🔴 **SUPERSEDED — the conditional in the last sentence fired.** 104-C
> (tanjiro, #586) returned **diffuse**: 155 of 237 dispatches at ≤1.6 TG/core
> carry only **12.8 % of prefill FLOP** and **16.28 % of the steel millisecond
> wall**, Gini 0.5537, top-1 dispatch 1.13 %. 104-B's central estimate therefore
> collapsed exactly as preregistered, and fern's own §9/§12.2 VOID condition
> ("this sizing is VOID if 104-C returns diffuse") fired. Both the 104-B row and
> the A+B sum are struck.
>
> **The corrected round-104 table is:**
>
> | arm | central score-% | status |
> |---|---|---|
> | 104-A | **+0.77 %** | live, unmeasured — #584 |
> | 104-B | **+0.35 %** ceiling | **refuted**, #585 merged as a negative |
> | 104-C | **0** by construction | audit-only, #586 merged |
> | **best available sum** | **+0.77 %** | **54 % of the bar** |
> | **bar** | **+1.438 %** | §8.2 |
>
> **No single round-104 lever clears the bar, and the slate no longer sums past
> it.** The +0.35 % ceiling for 104-B is my own arithmetic over tanjiro's
> §6A.5 Projection B: the wk/wv bucket projects to 3.922 ms on M5, the
> perfect-efficiency floor for its 167.5 GFLOP is 167.5 / (60 × 0.933) =
> **2.991 ms**, so the entire recoverable envelope is **0.930 ms**, and at the
> total prefill price of 0.3781 %/ms that is **+0.352 % of score = 24 % of the
> bar** — and that is a *ceiling*, achieved only by a perfect fix. See §14.
>
> §13.3's "the composed tree is measured by nobody" gap therefore shrinks to a
> **single-arm** question: 104-A alone, on its own commit. §13.4's composition
> null is retained for the next slate that has two live arms, but there is
> nothing to compose in round 104.

### 13.3 🔴 The gap: the composed tree is measured by nobody

A tree carrying **both** A and B has a `Sources/` that differs from A's tree,
from B's tree, and from today's base. By §11, **no existing receipt measures
it**, and no future receipt can be borrowed from either arm. It needs **at
least one receipt of its own, on its own distinct commit**.

Nobody is assigned to produce that. All four live PRs (#584, #585, #586, #571)
terminate in a per-arm answer. This is the load-bearing unassigned piece of work
in the campaign right now.

What composing costs, concretely:

1. One merge of the two arms — trivially clean, disjoint files.
2. One forced-clean build plus `research/run_upstream_equivalence.sh` and the
   64-step drift tripwire (§11.11). 104-B's `bm`/`bn`-only constraint keeps it
   bit-exact; 104-A's depth dial is bit-exact by construction (§6.2). So the
   composed tree should be **bit-exact against today's base**, and that is a
   checkable claim, not an assumption.
3. **One receipt**, on a commit distinct from every replicate (§11.3).

### 13.4 Preregister the composition null now

Do not let "additivity" be assumed at the moment of writing up a win. The
+1.90…+3.04 % figure multiplies two effects measured on **two different
instruments** — 104-A on M5 receipts (σ ≈ 0.26 % of score per 1-vs-1 receipt
difference, §1), 104-B on an M4 same-binary A/B whose M5 transfer factor is
0.622 (R1) / 0.534 ± 0.669 (composed). The composed receipt is the first and
only measurement of the two together.

Preregistered outcome for whoever gets this assignment:

* **N-add**: composed `cs` lands within (A + B) ± the §1 receipt σ ⇒ additivity
  holds, and the M4→M5 transfer factor for 104-B is confirmed at this size.
* **N-short**: composed `cs` lands materially below the sum ⇒ additivity in log
  space is right (it is algebra) but at least one arm's *effect size* did not
  transfer. That is a publishable negative and it is the more likely outcome
  given the transfer factor's ± 0.669.
* Either way the composed tree is what we would submit, so the receipt is not
  wasted on a null.

### 13.5 The honest statement about round 104

**Round 104 cannot itself take the record.** It can produce the two ingredients
and a calibration (#571). Taking the record requires a round-105 composition
assignment that (a) merges A and B, (b) verifies bit-exactness, (c) spends one
receipt, and (d) reports against §13.4's preregistration.

Two things can invalidate the plan before then, and both should be re-checked
at the start of round 105 rather than assumed:

* The standing record can move — including from inside our own org, since the
  `morganmcg1` account is shared across campaigns (§11.4). §8.2's +1.438 % bar
  is only valid until it does. Re-run `research/advisor_r104_record_watch.py`.
* Either arm can return a null. 104-A's depth dial has already been measured on
  M4 *with the opposite sign* (§5); 104-B depends on 104-C's N-B.


---

## 14. 🔴 Round-104 verdict: two arms landed, both negative, and they corrected the archive

Written after merging **#586** (tanjiro, 104-C) and **#585** (fern, 104-B).
Both results are terminal. Neither found a lever. Both found something more
durable than a lever: **three factual errors in the research archive**, one of
them in a ⛔ prohibition that has been suppressing work for several rounds.

### 14.1 The one-line verdict

**No single round-104 lever clears +1.438 % unaccompanied, and the slate no
longer sums past the bar.** 104-C closed at zero by construction. 104-B is
refuted a priori with a **+0.35 % ceiling**. 104-A survives at **+0.77 %**,
which is 54 % of the bar. This supersedes §13.2.

### 14.2 🔴 H8 is dead — prefill dense projections run at 87.5 % of peak

Tanjiro's null **N-A** was confirmed, and it kills §11.8's H8 outright.

The conservative, M4-derived figure: the 237 steel dispatches carry **1502.8
GFLOP**, and the M5 projection puts them at **28.6 ms**, giving
**52.5 TFLOP/s = 87.5 %** of the 60 TFLOP/s reference. The archive's own kill
criterion for H8 (`RESEARCH_ARCHIVE_through-round-91.md:7480`) is **≥ 52
TFLOP/s**. It is met.

The optimistic route is more interesting than the conservative one. Differencing
the PR #34 receipts (`b6032aeb` / `6757de65`) gives 1460.29 GFLOP / 22.2139 ms =
**65.74 TFLOP/s = 117 % of the 56 TFLOP/s hardware ceiling** — *arithmetically
impossible*. That is not a measurement, it is a **proof of marginal-estimator
contamination** (rule 76) in receipt-differenced prefill attributions, and it is
the reason tanjiro withdrew his own earlier "~39.6 TFLOP/s" figure for this
site. Rule 76 now has a second, independent demonstration.

Where the prefill inefficiency actually lives: **routed gather-GEMM at 23.23
TFLOP/s = 67 % of peak**, carrying **48.28 % of the prefill wall** across 76
dispatches. That is the largest single inefficient pool in prefill and nothing
in round 104 touched it.

**Consequence:** "prefill dense projections are inefficient" joins the hard
negatives. It has now been refuted twice — once by the archive's round-21
verdict on prefill attention (`RESEARCH_STATE_ARCHIVE_through-round-21.md:4245-4249`)
and once here on the dense-GEMM side.

### 14.3 🔴 The canonical prefill millisecond ledger now exists

Tanjiro's §6A is the single most reusable artifact round 104 produced: an
**exhaustive, non-overlapping millisecond attribution of every prefill
dispatch**, summing to 100.00 % with no residual pool.

The join is *proved*, not asserted: 1,659 GPUPROF records from
`research/pr270-logs/split1.worker.err` = 7 × 237; the 237-long kernel-name
sequence matches census order in all seven passes; split-K/regular
classification agrees slot-for-slot. Anchors reproduce exactly — regular raw
182.988 ms, split-K raw 35.584 ms, steel wall deflated 214.698 ms, grand total
**540.394 ms against the 540.396 ms serial-busy anchor, a 2 µs discrepancy**.

The whole-prefill ledger (M4, 1146 calls, 540.394 ms, 100.00 %):

| pool | calls | ms | % |
|---|---:|---:|---:|
| routed gather-GEMM (MoE `W`) | 76 | 260.907 | **48.28** |
| steel dense GEMM | 237 | 214.698 | **39.73** |
| attention core | 40 | 27.630 | 5.11 |
| NVFP4 dense qmm | 116 | 19.648 | 3.64 |
| elementwise | 234 | 4.648 | 0.86 |
| qk-norm + RoPE | 41 | 4.136 | 0.77 |
| sort/scatter | 78 | 2.598 | 0.48 |
| MoE tail | 38 | 2.535 | 0.47 |
| RMSNorm | 83 | 1.691 | 0.31 |
| router tournament | 40 | 0.940 | 0.17 |
| `lm_head` | 5 | 0.655 | 0.12 |
| other | 3 | 0.308 | 0.06 |
| **TOTAL** | **1146** | **540.394** | **100.00** |

**This table replaces every prior prefill attribution in the corpus**, including
the withdrawn "31.28 ms unattributed pool" (§9a) and any receipt-differenced
marginal estimate. Use it.

Two structural facts fall straight out of it:

* **Concentration.** Gini **0.5537**; top-1 dispatch 1.13 %, top-10 11.22 %,
  top-20 22.40 %, top-82 84.50 %. There is no single fat dispatch to attack.
* **The M4 attribution does not transfer.** Referenced to the best observed
  efficiency (93.3 %), the recoverable M4 deficit is 13.411 ms = 6.25 % of the
  steel wall, **52 % of it in wk/wv** — but the M4 mechanism there is *split-K
  accumulation at 51.20 TG/core*, and **M5 does not take the split-K branch for
  that shape**. Same shape, different failure mode. **3 of 9 buckets carrying
  12.029 of the projected 28.626 ms change route between M4 and M5**, so the
  Tier-1 projection is weakest exactly where it is largest. §4.15's
  concentration claim stays **UNMEASURED**, not confirmed.

### 14.4 🔴 The 104-B refutation, and why it is worth more than the lever was

Fern refuted her own hypothesis in §14 of her report, after submitting it. Four
independent kills, any one sufficient:

1. **Magnitude.** The lever's entire reachable slice is 78 dispatches carrying
   **167.50 GFLOP = 11.1 % of prefill FLOP**, on an axis worth 25 % of score.
   The Projection-B ceiling is **0.930 ms = +0.352 % = 24 % of the bar** (§13.2
   correction). A lever cannot clear a bar it is four times too small for.
2. **Rule 68 / PR #527 attacked the same site and lost.** N = 8192(wq) +
   1024(wk) + 1024(wv) = 10240; the 78 removed dispatches are *exactly* fern's
   78 (39 layers × 2); geometry, kernel family and 640 threadgroups held fixed.
   Result: **+0.639 ms, CI [+0.325, +0.953], t = 4.43 on 12 dof, −0.242 % of
   score**. Rule 68 also records swizzle depth at this site as a **measured
   no-op** (−0.0141 ms, t = −0.098).
3. **The premise is independently dead** (§14.2, H8).
4. **The VOID condition fired** — fern preregistered "this sizing is VOID if
   104-C returns diffuse", and it did.

> 🔴 **My own caveat, which neither student recorded: #527 is confounded.**
> Merging wk/wv into Wq did not only change dispatch count — it also
> **concatenated the weight bank** from 33.55 MB to 41.94 MB. Its loss therefore
> admits an SLC-capacity explanation, not only an "occupancy is irrelevant"
> explanation. #527 is **suggestive, not decisive**, on the occupancy premise.
> The *decisive* kill is kill #1, the magnitude argument, which needs no
> mechanism at all. Anyone citing #527 as proof that occupancy does not matter
> is over-reading it.

The one untested variant, recorded by **both** students and explicitly proposed
by **neither**: **[Wk;Wv]-only fusion** (8.39 MB bank, a quarter of Wq's
33.55 MB). It is a clean one-bit discriminator between the SLC-capacity and
lost-overlap explanations of #527. Rule 68's own disposition — *"worth
understanding, not worth a receipt now"* — stands. Do not assign it as a
performance lever; it is only interesting as a mechanism probe.

### 14.5 🔴 ARCHIVE CORRECTION 1 — the `_nax` "bn = 128 minimum" ⛔ is FALSE

`CURRENT_RESEARCH_STATE.md:2824-2825` carries a ⛔ prohibition asserting that
**bn = 128 is the minimum instantiated `_nax` tile width**, i.e. that narrower
tiles are *dead by construction*. **This is factually wrong and must be
struck.** Fern falsified it three ways:

1. **The AOT list already contains bn = 64.**
   `Vendor/…/kernels/steel/gemm/kernels/steel_gemm_fused_nax.metal` instantiates
   exactly six geometries via `instantiate_gemm_shapes_helper`: `(64,64,256,2,2)`,
   `(64,128,64,2,4)`, `(64,128,256,2,4)`, `(128,128,64,4,4)`,
   `(128,128,256,4,4)`, `(128,128,512,4,4)`. **The first is bn = 64** — exactly
   the disputed geometry.
2. **The AOT list does not bound reachable geometry anyway.**
   `Vendor/mlx-swift/Package.swift:25` sources `jit_kernels.cpp` and `:284`
   **excludes `nojit_kernels.cpp`**, so the compiled path is JIT.
   `get_steel_gemm_fused_nax_kernel` (`jit_kernels.cpp:977-1009`) templates
   `bm/bn/bk/wm/wn` from **runtime** values.
3. **Empirically confirmed.** Offline MSL compile **and pipeline creation
   succeeded for all four geometries** on a gen-16 M4 Pro: off
   (bm64 bn128 bk256 wm2 wn4, 75090 B, sha256 `349cf1e1…`), bn64
   (75073 B, `d044f6c9…`), bn32 (75009 B, `b44d19fa…`), 32×32
   (75009 B, `bd4ea1ae…`). The only shape constraints in `steel/gemm/nax.h` are
   the 16×16 `BaseNAXFrag` `static_assert`s at `:38`, `:119`, `:189`,
   `:981-989`, **none of which reference `bn`**.

Note that `steel_gemm_fused_nax.h:86` declares
`[[kernel, max_total_threads_per_threadgroup(WM*WN*32)]]` — a *declared cap*,
not an instantiation bound; fern's pipelines all reported
`maxTotalThreadsPerThreadgroup = wm*wn*32` as expected.

**Disposition:** rule 68's *measured* content (+0.639 ms, and the swizzle
no-op) **stands and is load-bearing**. Its "dead by construction" clause is
**struck**. Reject narrow-`_nax`-tile briefs on the **M5 measurement**, never on
a nonexistent compile-time impossibility. A false ⛔ is worse than no ⛔: it
suppresses work *and* teaches students that the archive's prohibitions need not
be verifiable.

### 14.6 🔴 ARCHIVE CORRECTION 2 — the split-K tie is a double exact equality

`CURRENT_RESEARCH_STATE.md:2814-2816` states that the NAX split-K routing tie
for the wk/wv shape sits in the `K ≥ 3·max(M,N)` disjunct. **It does not** —
that disjunct fails by a margin of **1024**.

The real behaviour of the gate at `matmul.cpp:922-924`,
`K >= 3*max(M,N) || (max(M,N) <= 1024 && K > 2*max(M,N))`, at
(M=512, N=1024, K=2048), is **two exact equalities in the second disjunct**:
`max(M,N) <= 1024` passes **by equality**, and `K > 2*max(M,N)` fails **by
equality**. The shape sits on a knife edge in two predicates at once.

**Both students derived this independently and identically** — tanjiro §4.1 from
his route model, fern §1 from a direct source-predicate walk. That is a genuine
double replication, and I record it as such (see §14.8).

Practical consequence: this shape's route is maximally fragile. Any future edit
that moves either constant by one flips 78 dispatches between
`steel_matmul_regular_axpby_nax` and `steel_gemm_splitk_axpby_nax`. The standing
open idea **H3, the split-K tie flip `>` → `>=`**
(`RESEARCH_IDEAS_steel-gemm-prefill.md:170-186`) is exactly this edit; it remains
unimplemented, is **not bit-exact**, and its sign is bracketed at −3…+1 ms.

### 14.7 🔴 STANDING RULE — the two prefill prices are not interchangeable

Tanjiro's §6A.7 disambiguates a constant that has been quoted loosely across the
corpus (`CURRENT_RESEARCH_STATE.md:646-748`):

| constant | value | when to use |
|---|---|---|
| **partial** | **0.2592 %/ms** | **reading a receipt** — converting an observed prefill delta into observed score |
| **total** | **0.3781 %/ms** | **pricing a prospective prefill optimisation** — because prefill wins propagate into decode via `D = 4P + T` |

Round-104's levers are prospective, so the bar is **+1.438 % ÷ 0.3781 %/ms =
3.803 ms** of prefill. Using the partial constant would have mispriced the bar
at **5.549 ms** — a 46 % error, in the direction that makes levers look harder
than they are. (The older 0.374750 figure gives 3.837 ms; the two agree to
0.9 % and either is fine.)

**Every future prefill sizing must state which constant it used.**

### 14.8 On provenance: the two derivations are genuinely independent

Tanjiro's report carries a caveat at his `:330-336` suggesting fern's routing
claim "originally derives from my own NMPC §3.4". **I side with fern's §14.5
correction: it does not.** Her §1 is a direct source-predicate derivation against
`matmul.cpp` at clean base `9527bb72`, citing nothing of NMPC. Tanjiro is being
over-cautious about his own priority, which is a good instinct pointed at the
wrong target.

What each contributed that the other lacked:

* **fern**: the predicate-by-predicate call-chain walk, and the compile evidence
  that falsified the ⛔ (§14.5).
* **tanjiro**: `steel_route_model.py`, which reproduces **237/237** observed
  rows at `use_nax=False` — the executable confirmation fern's hand derivation
  could not supply.

Tanjiro also self-corrected **his own** NMPC §3.4 in his §2.3: the wk/wv grid is
**(32,2,1) post-swizzle**, and `g_proj` has `parts = 2` on M5-`_nax`. Students
correcting their own prior published work, unprompted, is the behaviour this
campaign should be selecting for.

### 14.9 🔴 The positive mechanism result that survived the refutation

Fern's §7 is a standalone occupancy probe
(`research/fern_r104b_grouping_probe.swift`, `xcrun swiftc -O`, synthetic
FMA-spin kernel, zero threadgroup memory, best-of-25, first leg discarded) and
its finding survives the death of the lever it was built to support.

At 512 simdgroups on M4: 1, 2 and 4 simdgroups/TG all land at ≈521.7 µs;
**8 simdgroups/TG costs 762.2 µs = 1.4613×**, reproduced twice.

But §7.2's causal sweep shows **this is packing quantization, not intrinsic
width slowness**. Wall time is quantized into ≈255 µs units
(≈255.5 / 521.7 / 775.4 / 1028.8), and at **6 of 13** total-simdgroup counts
(168, 336, 672, 704, 1008, 1024) g=8 matches g=4 to within 0.1 %. g=8 needs an
extra pass only at 504–528 and 840–848 — and **512 sits in the worst band
observed**.

Fern then **refutes her own model** twice over: §7.3 shows a `ceil(total/C)`
fixed-capacity model does not fit all 13 points (63 TGs of 8 implies capacity
≤ 31; 128 TGs of 8 implies ≥ 32), and §7.4 discards her static
`q(g) = g·ceil(512/(P·g))` formula. She therefore **refuses to extrapolate the
1.4613× to M5**, and explicitly flags the probe's Part-1 concurrency ladder as
unreliable (C = 44 then 20 for g=4; 21 then 23 for g=8) — **that ladder must not
be quoted**.

The operand-traffic side is real but small: per-output-element operand traffic
`(bm+bn)/(bm·bn)` rises from 0.02344 to 0.03125, **+33 %**, but at ≈7.3 MB per
GEMM that is ≈12 µs at 610 GB/s, ≈0.94 ms across all 78 dispatches against
≈5.6 ms of arithmetic. **The penalty is L2, not DRAM; the shape is compute-bound
at the DRAM level.**

**Usable content:** if a future lever changes simdgroups-per-threadgroup at a
site, the cost is a *quantization* effect that depends on the total simdgroup
count and the machine's capacity, and it can be **zero** at the right totals.
Do not model it as a fixed multiplier.

### 14.10 🔴 The local-iterate channel is 4× noisier than the receipt channel

Fern's §4.4 is the cleanest negative control the campaign has produced on
tooling. Running **identical code** through the local iterate harness produced a
**+0.9 % "score" delta** (prefill −1.4 %, decode −0.7 %) on a lever that
**cannot execute locally at all** — `_nax` never runs on a gen-16 M4 Pro
(`is_nax_available()` at `device.cpp:913-931` requires macOS ≥ 26.2 *and*
gen ≥ 17/18). Two relaunches of identical code differed by **1.3 %** on both
axes.

Against the receipt channel's `sd(cand_pre) = 0.31 %` (§1), **local iterate is
≈4× noisier than the deciding instrument**, and it is noisy in a way that
produces *confident-looking* deltas on *inert* changes.

**Standing consequence: a local-iterate delta is never evidence for or against a
lever.** It is a smoke test for "does it build and produce the same tokens", and
nothing more. Fern's §4.2 equivalence run is the correct use:
`run_upstream_equivalence.sh` gave prefill `maximumAbsoluteLogitError 0.125`
(a pre-existing near-tie), token 5991 == 5991, decode-0..7 error 0, all tokens
matching, and `--local-iterate` `max_abs_diff 0` with an identical `golden_hash`
under both flag-off and forced-on.

### 14.11 The host-side channel is bounded but not excluded

Tanjiro's §7 closes the threat #572 opened, partially. Six forced-clean builds
(job `b61f0318`, exit 0). The V1 determinism oracle **PASSES**. The V2 channel
is **bounded and localised but NOT excluded**: **+2,164 bytes of `__text`** over
the scored module (+1,900 on-path, 0.44 % / 0.49 %), 7 symbols removed and 15
added, 22 total, all traceable to **one mechanism** — the lazily-initialised
`lagunaRouterWeightPrefetch` global, a new `prefetch:` parameter, and the router
kernel cache re-keyed from `[Int: MLXFastKernel]` to `[[Int]: MLXFastKernel]`.

So the R3 router-prefetch change did not only add a kernel variant; it moved
~2 KB of host text. That is small, localised and explained, but it is **not
zero**, and it means "`Sources/` differs only in a dormant branch" is not
automatically a no-op claim.

### 14.12 🔴 Disposition of #585: merged, then reverted

**#585 was merged and its 42 source lines were then reverted in the immediately
following advisor commit.** This needs stating plainly because it looks
contradictory.

* **Why merge.** The report carries large durable value that a close would have
  buried: the §1 routing derivation, the §2 census, the §4.1 compile evidence
  that falsified a standing ⛔ (§14.5), the §4.4 noise trap (§14.10), the §7
  packing measurement (§14.9), and the §14.4 rule-68 correction. Merging is how
  that becomes citable.
* **Why revert the code.** The 42-line `DARKBLOOM_NAX_SKINNY_TILE` selector is
  **dead code on a refuted premise**, and it sits on the **ranked-M5 executed
  host path** inside `steel_matmul_regular_axpby_nax`. Default-off is not the
  same as absent: it is a branch on a hot host path, and it is one more thing
  every future reader of that function must reason about.
* **Precedent.** PR #293 was merged inert on this exact mechanism at this exact
  site, earned zero ranked receipts, and was then **silently deleted by frontier
  resync `99b974c`**. Inert merges of dead levers buy nothing and cost review
  surface.
* **The author agrees.** Fern's own §14.6 disposition is *"close as a negative,
  do not merge"*. Reverting the code while merging the science honours that
  recommendation on both counts.

Post-revert, `matmul.cpp` is byte-identical to base `9527bb72`
(sha256 `49810705f93f98c7e4218d19fe625c96f482ac2fadc2abacf7e356fb1d299c36`), and
`git diff --numstat 9527bb72 HEAD -- Vendor Sources` is **empty**. Round 104 has
so far changed **zero bytes** of scored code.

### 14.13 🔴 Strategic consequence: stop hunting for the one big lever

Tanjiro's §6A.8 reaches the same conclusion §8 reached from the receipt side,
by a completely different route, and the agreement is worth acting on.

His §6A.6 enumerates four admissible apportionments of the 11.40 ms M5 residual
and finds the bar sits **inside** the admissible span (+0.94 %…+2.52 %) — even
under the most favourable assumption 104-B was a **coin flip, not a favourite**.
Combined with §8.1 (the record is a **+3.28 σ, p99.95** draw), §8.4 (at least
three trees inside a ±0.2 % band, no defensible moat) and §11.2 (draws cannot be
farmed), the strategy that follows is:

> **Maximise `cs` and take repeated legitimate draws. Do not stake the campaign
> on finding one deterministic +1.44 % lever.**

Concretely, §8.2's pricing table is the plan: at Δcs = 0 a receipt is worth
0.095 %, at +0.5 % it is 2.165 %, at +1.0 % it is 17.34 %. **Every real +0.25 %
multiplies the value of every subsequent draw**, and 104-A's +0.77 % — which
round 104 did *not* refute — is worth roughly 7 % per receipt on its own.

What this does **not** license: farming draws on byte-identical trees (§11.2,
declined on technical grounds and prohibited), or submitting receipts with no
`cs` improvement in the hope of a lucky L.

### 14.14 What round 104 actually delivered

| # | deliverable | where |
|---|---|---|
| 1 | The receipt channel is usable at 0.5–1.0 % in 2–3 pairs | §1 |
| 2 | There is no receipt quota — only a ~13 min wall-clock floor | §2 |
| 3 | Exhaustive prefill ms ledger, 1146 calls, zero residual | §14.3 |
| 4 | H8 dead — prefill dense GEMM at 87.5 % of peak | §14.2 |
| 5 | Second independent demonstration of rule-76 contamination | §14.2 |
| 6 | The `_nax` bn=128 ⛔ falsified and struck | §14.5 |
| 7 | The split-K tie corrected to a double exact equality | §14.6 |
| 8 | The partial/total prefill price disambiguated as a standing rule | §14.7 |
| 9 | Simdgroup packing is quantization, not a fixed multiplier | §14.9 |
| 10 | Local iterate is ~4× noisier than the receipt channel | §14.10 |
| 11 | Env gates are frozen at first touch — no in-process flipping | §9 |
| 12 | No dormant-win inventory; 76 unaudited gates, 7 silent | §10, §12 |
| 13 | One receipt per commit, ever; no duplicate-sha draws exist | §11 |
| 14 | The `#527` SLC confound recorded | §14.4 |

**Zero bytes of scored code changed. Three archive corrections landed.** For a
round whose two terminal arms were both negative, that is a good trade — but it
is not a record, and §14.13 is the only route to one.

### 14.15 Open at the close of round 104

* **#584 (nezuko, 104-A)** — the only live lever, +0.77 %, 8 receipts budgeted.
  Still the round's whole upside.
* **#571 (frieren)** — σ_launch calibration. If it lands materially below ≈48,
  the same-binary env-contrast channel exists and §10's 76-gate ablation ledger
  becomes rankable. If σ_launch ≥ 40, §10 dies and should be recorded as dead.
* ~~**The routed gather-GEMM at 67 % of peak** (§14.2) — 48.28 % of the prefill
  wall, the largest inefficient pool in the model, and untouched by round 104.
  This is the obvious place for a round-105 census, *after* re-reading rule 68,
  rule 83 and the §14.7 price rule.~~
  **STRUCK 2026-08-10 — see `research/advisor-r105-the-routed-gather-gemm-is-memory-bound.md`.**
  Three corrections: (i) "48.28 %" is of the **M4 non-`_nax`** wall and M5 runs a
  different kernel family; (ii) "67 % of peak" is an **achieved-bandwidth**
  fraction restated in FLOP units, derived from a contaminated marginal
  estimator; (iii) the bytes have already been counted **twice, byte-exactly**
  (14.826 GB), so there is nothing for a census to find. The corrected roofline
  makes the kernel **memory-bound** (issued AI 87.66 vs balance 98.36) with a
  cache-immune floor of 24.306 ms, which prices the **entire MMA-row-inflation
  family — including meridian's two-régime dispatch — at ≈0 ms**. The only
  compressible stream left is A-operand re-read (L7), and even that may already
  be absorbed by SLC.
* **[Wk;Wv]-only fusion** — mechanism probe only, not a lever (§14.4).
* **H3 split-K tie flip** — unimplemented, not bit-exact, sign bracketed
  −3…+1 ms (§14.6).

