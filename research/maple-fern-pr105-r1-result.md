# PR #105 r1 result — the lm-head 4+1 → 3+2 re-split is a regression

**Verdict: decisive negative. The mechanism was not implemented, because the
pre-registered hard gate refuted it before any code was written.**

- Assignment `maple-2026-08-06k-lmhead-base-plane-resplit`, revision `r1`.
- `BASE_SHA` `dec0a83c075d151ef5dec94f4005bd39ff2c2d69`.
- **Submitted surface: byte-identical to base. Zero growth.**
  `git diff dec0a83c HEAD -- Sources/ Vendor/` is empty.
- No W&B run exists. The gate stopped the arm before any timed experiment, so
  there was nothing to train, time, or log. Reporting a timing number here
  would be inventing one.

---

## 0. One-paragraph summary

The hypothesis was that re-splitting the lm-head int5 weight into a 3-bit base
plane plus a 2-bit residual would remove 25.69 MB per decode step from the
saturated tier-1 stream, at the price of a slightly wider level-1 certificate
and therefore a few more tier-2 survivors. The census says the price is not
"a few more". The re-split **exactly doubles** the level-1 cell, and the
survivor curve at that radius is not near-zero — it is **85.7 % of the
vocabulary**. Tier 2 re-reads 576 B per surviving row under 3+2, so the arm
adds 49.51 MB where it removes 25.69 MB. Net **−23.64 MB/step**: a regression
on **all 128** timed decode steps, with the single most favourable step still
1.35× past break-even. Applying §R20.2, 3+2 would cost **−0.377 % of score,
interval [−0.644 %, −0.230 %]**.

---

## 1. Method (Deliverable 0)

An env-gated host-side MLX mirror of the tier-1 screen was inserted in
`LagunaLmHeadPruner.logits(...)` immediately after the threshold `thr` is
formed. For each candidate radius `k` it counted rows satisfying
`(coarse + k*delta) >= thr` and the number of live 4-row blocks:

```
DARKBLOOM_LMHEAD_PRUNE_STATS=1 research/run_local_benchmark.sh --local-iterate
```

The probe forces a host sync per step, so **timings from that build are
meaningless and none were taken**. The probe has since been reverted; the tree
is byte-identical to base.

- Raw data: `research/maple-fern-pr105-census-raw.txt` (131 unique stat lines).
- Analysis: `research/maple_fern_pr105_census.py` (reproduces every number
  below from the raw file; no arguments needed).
- Call structure: calls 1 and 3 are the two one-pass prefill passes
  (`refine=false`); calls 4–131 are the **128 teacher-forced decode steps** of
  the timed window (`refine=true`). All statistics below use those 128 steps.

### Why k = 2.0 is the exact proxy for 3+2

`sd = 2^e`, `q = round(w/sd)`, `|q| <= 15`, `u = q+16 ∈ [1,31]`.

- Today (4+1): `H4 = u>>1`, base point `q0 = 2*H4 - 15.5`, so `|q - q0| <= 0.5`
  and the level-1 cell is `|w - sd*q0| <= sd`. That is `k = 1.0`.
- Proposed (3+2): `H3 = u>>2`, base point `q0 = 4*H3 - 14.5`, so
  `|q - q0| <= 1.5` and the cell is `|w - sd*q0| <= 2*sd`. That is `k = 2.0`,
  **exactly** — the delta doubles by an exact power of two, with no modelling
  slack.

### Independent validation of the k mapping

The prefill one-pass kernel computes the **half**-cell `d_half = (sd/2)*Σ|x|`,
while the base-plane kernel accumulates `d_acc = Σ sd*|x| = 2*d_half`
(`LagunaLmHeadPrune.swift:276-315`). The two kernels must therefore agree
under a factor-of-two shift in `k`, and they do:

```
refine=false k=2.0, call 1 : 31835 survivors
refine=true  k=1.0, call 2 : 31914 survivors   (the adjacent position)
```

Two independently written screens, one shift, 0.25 % apart. The mapping is
sound.

A second, stronger corroboration: this census puts the **k=1.0 decode mean at
534.0 survivors**, reproducing nezuko's independently measured "534 survivors
mean" exactly. (An earlier raw sample of mine quoted 31,914; that is the
warm-up call, and it is the per-step *maximum* of the distribution, not a
typical step. Corrected here.)

---

## 2. The survivor curve

**Decode, base-plane screen, cell radius = k·sd, n = 128 timed steps:**

| k | mean | median | min | max | % vocab | live 4-blocks | % blocks |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1.0 | 534.0 | 288 | 55 | 9 193 | 0.53 | 458.0 | 1.83 |
| 1.5 | 23 780.3 | 16 219 | 5 455 | 87 170 | 23.70 | 13 050.1 | 52.02 |
| **2.0** | **85 947.3** | **89 116** | **60 760** | **99 967** | **85.65** | **24 964.0** | **99.51** |
| 2.5 | 99 340.4 | 99 564 | 97 498 | 100 266 | 98.99 | 25 071.9 | 99.94 |
| 3.0 | 100 207.9 | 100 242 | 99 988 | 100 352 | 99.86 | 25 075.8 | 99.95 |
| 4.0 | 100 342.7 | 100 352 | 100 268 | 100 352 | 99.99 | 25 086.6 | 99.99 |

**Prefill one-pass, cell radius = k·(sd/2), n = 2:**

| k | mean | min | max | % vocab |
|---:|---:|---:|---:|---:|
| 1.0 | 166.5 | 138 | 195 | 0.17 |
| 1.5 | 2 651.5 | 2 174 | 3 129 | 2.64 |
| 2.0 | 22 463.0 | 13 091 | 31 835 | 22.38 |
| 2.5 | 69 100.0 | 51 799 | 86 401 | 68.86 |
| 3.0 | 94 557.5 | 91 199 | 97 916 | 94.23 |
| 4.0 | 100 122.5 | 100 069 | 100 176 | 99.77 |

The curve is a cliff between k = 1.0 and k = 2.5, crossing from 0.5 % to 99 %
of the vocabulary. **The deployed certificate sits at the foot of that cliff.**

---

## 3. Cost model

Hidden size 2048, vocabulary 100 352, e8m0 scales one byte per group of 32
(64 B/row). Per-row bytes **READ** (§0.9.40):

| stream | bytes/row | note |
|---|---:|---|
| tier-1 base plane, 4+1 | 1024 + 64 = **1088** | 4-bit plane |
| tier-1 base plane, 3+2 | 768 + 64 = **832** | 3-bit plane |
| tier-2 refine, 4+1 | 256 + 64 = **320** | 1-bit residual, **per surviving row** |
| tier-2 refine, 3+2 | 512 + 64 = **576** | 2-bit residual, per surviving row |
| pre-#20 one-pass | 1024 + 256 + 64 = **1344** | single fused int5 pass |

The refine kernel charges **per surviving row, not per live block**. Confirmed
by reading `laguna_lmhead_exact_fused_int5_sparse_refine_v1`: the
`#pragma clang loop unroll(disable)` loop over `tm` does
`if ((base_mask & (1u<<tm)) == 0) continue;`, so block granularity only gates
the whole-simdgroup early-out; a live block with one survivor still pays one
row. This is the single fact that decides the experiment, and it was the one
the pre-registration got wrong.

**Per decode step, bytes READ, mean over the 128 timed steps:**

```
pre-#20 one-pass                                        134.87 MB
4+1 (today)     tier1 109.18  +  tier2  0.17   =        109.35 MB
3+2 (proposed)  tier1  83.49  +  tier2 49.51   =        133.00 MB
```

**Bytes REMOVED (§0.9.40; positive = less traffic):**

| change | REMOVED MB/step | n | range | half-range | sd |
|---|---:|---:|---|---:|---:|
| 3+2 vs 4+1 | **−23.64** | 128 | [−30.95, −9.29] | 10.83 | 6.70 |
| 4+1 vs one-pass (PR #20, retro) | **+25.52** | 128 | — | — | — |

**Predicted score, priced with §R20.2** (+0.41 % per 25.7 MB/step REMOVED,
interval [0.25 %, 0.70 %]):

| change | point | interval |
|---|---:|---|
| 3+2 vs 4+1 | **−0.377 %** | **[−0.644 %, −0.230 %]** |

The gate in the pre-registration was "< 10 MB net saving → stop and write it
up as a decisive negative". The result is not a small saving; it is a −23.64 MB
loss. **0 of 128 steps** would have removed a single byte.

### Break-even

3+2 can afford `((1088-832)*V + 320*S_{k=1}) / 576` tier-2 survivors:

```
break-even            : 44 898 rows = 44.74 % of vocab   (k* ~ 1.67 sd)
measured k=2 mean     : 85 947     = 85.65 %
measured k=2 minimum  : 60 760     = 60.55 %
best step overshoot   : 1.353x the affordable survivor count
steps below break-even: 0 / 128
```

3+2 does not miss break-even by a hair. It is off by 0.33 in cell radius, over
an interval where the curve is at its steepest: survival rises 62 percentage
points between k = 1.5 and k = 2.0, and 41 points between k\* = 1.67 and the
k = 2.0 the re-split forces.

---

## 4. Pre-registered predictions — verdicts

### §2.2 **FALSIFIED**

I predicted `survivors_{k=2}` mean **< 6 000** and `live4blocks_{k=2}` mean
**< 5 000**. Actual: **85 947** and **24 964** — wrong by 14× and 5×. The error
was extrapolating the k=1 tail (534 rows, 0.53 %) as if the curve were
exponential in k. It is not; it is a cliff, and k=2 is on the far side of it.
This is exactly the failure mode a pre-registered gate exists to catch cheaply,
and it caught it for the cost of one instrumented `--local-iterate`.

### §2.4 **CONFIRMED**

I predicted that tier-2 survivor traffic would **not** explain PR #20's
sub-band transfer. Confirmed, and more strongly than expected: tier-2 reads
**0.17 MB/step**, which is **0.16 %** of the cascade's 109.35 MB. PR #20's true
removal is 25.52 MB rather than the 25.69 MB zero-survivor idealisation — a
0.7 % correction, far too small to explain anything.

**A note on circularity, stated plainly:** §R20.2's constant is *calibrated
from* PR #20, so applying it to PR #20 is a consistency check, not evidence.
The non-circular content of §2.4 is that R20.2's denominator is accurate to
0.7 %, so the pricing constant does not need revision.

### Where PR #20's missing transfer actually went (§0.9.39 applied)

A roofline route prices #20's 25.52 MB at the M5 610 GB/s byte channel:

```
25.52 MB / 610 GB/s               = 41.84 us/step
0.75 * 41.84 / 4908 us            = +0.639 % of score
observed                          = +0.41 %
transfer                          = 0.64x        (below the 1.0-1.2x band)
```

Under §0.9.39 a ratio outside 1.0–1.2× is presumed a denominator error, so I
solved for the denominator that would make it 1.0×: **951 GB/s**. That is above
the M5 610 GB/s ceiling and above every corpus-sanctioned rate (281.3 / 415 /
546.2 / 651.8 GB/s). **No admissible denominator rescues the roofline route
here**, which means the shortfall is not a mis-priced denominator — it is real
non-byte cost. The bytes come off a stream that is already at 100.2 % of its
channel (`laguna_lmhead_int5_base_coarse_delta_bf16_v1`, 109.18 MB / 418.9 µs =
260.6 GB/s on this M4 Pro; see the erratum), while the cascade simultaneously
pays serial dispatch latency for the extra stages. That is why §R20.2's
empirical constant, not a roofline, is the right instrument for this channel —
and it is why I priced 3+2 with §R20.2 above.

**This makes −0.377 % optimistic, not conservative.** 3+2's added bytes land in
the *refine* kernel, whose cost is latency-heavy rather than purely streaming,
so the real regression is likely larger than R20.2's byte-proportional estimate.

---

## 5. Deliverable 1 — the 3+2 superset proof (sound, but economically dead)

The proof obligation was discharged on paper before the gate result was
analysed. Recording it so nobody re-derives it: **the scheme is correct; it is
simply not profitable.** With `H3 = u>>2`, `r = u&3`, midpoint `r := 1.5`,
`q0 = 4*H3 - 14.5`:

1. `|q - q0| <= 1.5` gives cell `|w - sd*q0| <= 2*sd`, so the delta is exactly
   `2.0f*d_acc` — an exact power of two, no rounding slack.
2. `|q0| <= 14.5` bounds the magnitude ratio at `m <= 7.25*d`, so the emitted
   certificate is `d*(1 + 16.0f*GAMMA)`; `1 + 2^-11` is exact in FP32.
3. The refine correction `4*H3 - 14.5 + (r - 1.5) = q` is exact: every term is
   a multiple of 0.5 with at most 6 significand bits.
4. The refined certificate is `D3 = 4d` with `m <= 32d`, i.e. `d*(1 + 65*GAMMA)`
   — identical to today's, so the tier-2 **exactness** is unchanged by
   construction. (Only the tier-2 **population** changes, which is the whole
   problem.)
5. The refined multiplier becomes `c = (1 + 56*GAMMA)/4 = 0x1.007p-2`
   (margin 7·GAMMA), replacing `0x1.005p-1f` at `LagunaLmHeadPrune.swift:727`;
   the product is exact (8 + 13 = 21 < 24 bits).
6. The `maxCode <= 15.0` init guard, the one-pass prefill bound
   (`m <= 30d`, `1 + 61*GAMMA`) and the decline path are all untouched.
7. Threshold soundness at `:404-422` is unchanged: it depends only on
   `e_r <= e_winner`.

Layout E, fixed but now not implemented: `codes_base` `[V,768]` carrying, per
group of 32, 8 B of 2-bit `hi2 = u>>3` plus 4 B of 1-bit `b1 = (u>>2)&1`;
`codes_resid` `[V,512]` of 2-bit `r = u&3`; reassembly
`hcode = (hi2<<3) | (b1<<2)`, `ve = float4(hcode) - 14.5f`; residual
`ve = float4(r) - 1.5f`.

---

## 6. Proposed durable law — the lm-head certificate knee

I propose the following for the corpus (number to be assigned by the advisor).

> **The lm-head int5 cascade is closed to certificate-geometry work.**
>
> (a) *Tier 2 is exhausted.* At the deployed 4+1 split, tier-2 reads
> **0.17 MB/step out of 109.35 MB/step — 0.16 %** of the cascade. Even a
> perfect tier-2 (zero survivors) is worth **+0.003 % of score**. No proposal
> whose benefit is "fewer survivors" can be worth building.
>
> (b) *Widening the level-1 cell is pre-refuted.* Survival as a function of
> cell radius k, n = 128 timed decode steps: 0.53 % at k = 1.0, 23.70 % at
> k = 1.5, **85.65 % at k = 2.0**, 98.99 % at k = 2.5, 99.99 % at k = 4.0.
> Tier-2 economics break even at 44.74 % survival, i.e. **k\* ≈ 1.67**. Any
> scheme whose cell exceeds ~1.67·sd loses. Concretely pre-refuted:
> **3+2 re-split** (k = 2.00 exactly, this PR); **coarser scale groups**
> (k scales with the group-max/group-mean ratio, ≥ 2×); **scale-only bounds**
> (radius ≈ 15.5·sd ⇒ k ≈ 15.5, 99.99 % survive); **prefix / partial-dimension
> bounds** (unbounded tail ⇒ k ≥ 2.5 for any useful prefix).
>
> (c) *Therefore only tier-1 bytes matter, and they are 1088 B/row of
> irreducible representation.* The one remaining sub-lever is the 64 B/row
> e8m0 scale plane (6.42 MB/step, 5.9 % of tier 1); halving it via a per-row
> base exponent plus 4-bit deltas would remove 3.21 MB/step, worth
> **+0.051 %, interval [+0.031 %, +0.087 %]** under §R20.2 — below the
> programme's decision noise floor.
>
> (d) *The remaining lm-head opportunity is latency, not bytes.* See §7.

Corollary for the erratum: `research/maple-fern-pr105-r1-erratum-lmhead-ceiling.md`
§3.3 claimed 3+2 was "the shape of the only remaining move" and that its
25.69 MB "is the whole of its expected value". That is now superseded — the
25.69 MB is gross, not net. §3.1 and §3.2 of the erratum stand.

---

## 7. Suggested follow-ups (not implemented)

1. **Fuse the five small cascade kernels (highest value).** The erratum's
   per-kernel split shows the cascade aggregate is 508.1 µs M4 / 112.4 MB while
   stage 1 alone is 418.9 µs / 109.18 MB. The other five kernels are therefore
   **3.2 MB but 89.2 µs** — at 260.2 GB/s their bytes account for only ~12 µs,
   leaving **~77 µs of pure dispatch/occupancy latency**. Dispatch latency does
   not shrink with M5's wider channel, so ~82 µs likely survives to the ranked
   host: `0.75 * 82 / 4908 = 1.25 % of score`. That dwarfs everything left in
   the byte channel. Candidate fusions: argmax stage 1 into the coarse kernel,
   and the threshold GEMV into the exact pass. This needs its own per-kernel
   latency census before anyone prices it — I have not measured the five
   kernels individually, only inferred them by subtraction, and §0.9.39 applies
   to that inference too.
2. **Retire the "shrink the tier-2 survivor set" idea class.** §6(a) closes it
   arithmetically. Anyone proposing it should be pointed at
   `research/maple-fern-pr105-census-raw.txt`.
3. **Reuse the census probe.** The `DARKBLOOM_LMHEAD_PRUNE_STATS` pattern
   (host-side MLX mirror of a kernel screen, env-gated, reverted before timing)
   cost one `--local-iterate` and killed a multi-day arm. It generalises to any
   pruning or early-exit kernel in the tree.

---

## 8. Preflight, verbatim

```
$ senpai/check-editable-budget.sh dec0a83c075d151ef5dec94f4005bd39ff2c2d69
editable budget OK: current=2934331/3000000 bytes headroom=65669 growth=0/262144 files=142 (file count is diagnostic only; base=142)

$ senpai/validate-assignment-scope.sh dec0a83c075d151ef5dec94f4005bd39ff2c2d69 \
    Sources/MLXFastModel/LagunaLmHeadPrune.swift \
    Sources/MLXFastModel/LagunaRuntimeModel.swift
assignment scope OK: 2 submitted path(s)
```

Final growth is **0 bytes**: nothing on the submitted surface changed.

The advisor advanced the base twice during this arm (`b60bdd75`, `2f3ed2e2`),
both zero submitted bytes, and instructed no rebase. `expected_base_sha` is
therefore still `dec0a83c…` and the editable surface is byte-identical to it.
