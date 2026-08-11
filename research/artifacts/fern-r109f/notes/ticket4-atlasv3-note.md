# r109-F ticket 4 — atlas v3_tg128 decode kernel, QHOIST reverted

**Campaign:** r109-F, `maple-r109-f-integration-and-submission`, revision
`r109-f-rev2`, PR #686.
**Student handle:** **maple-fern**.
**Executable class:** **`r109F-atlasv3`** — a *new* class, opened by this
submission at n=1. It is the r109-F base class (draws
`c1c0ba2c-ec1c-43f4-92bb-3c5b8b0a76e9` and
`88584270-140e-4f28-a924-b00c77b1becd`, normalized 2.566844 / 2.566903) with
exactly two changes: the `DARKBLOOM_ATTN_QHOIST` default flip **reverted**, and
the decode embedding+RoPE atlas kernel replaced by its 128-lane form. It is
**not** a nonce replay of a previously drawn tree.

**Nonce:** `atlasv3-r109f-t4-2026-08-11T01Z-nonce-7b3e0d51-a`

---

## 1. What changed, in full

Single file, `Sources/MLXFastModel/LagunaRuntimeModel.swift`, plus a revert.

### 1.1 Reverted: `DARKBLOOM_ATTN_QHOIST` compile-time default 1 → 0

Ticket 3 of this campaign (`e4078827-c7fd-4173-a2bf-2f6af7cc6e73`) flipped that
default to 1 in three files. That receipt is terminal and it was a regression,
so the flip is reverted here. Evidence in §3.

### 1.2 Changed: decode embedding+RoPE atlas kernel → 128-lane geometry

Four edits inside one `MLXFast.metalKernel`:

- kernel name `laguna_decode_embedding_rope_atlas_bf16_2048_v2` →
  `…_v3_tg128`, so the JIT kernel cache cannot serve the old variant;
- drop `constexpr uint hidden_vectors = hidden_size / 4;`
- replace the guarded single store
  `if (lane < hidden_vectors) { hidden_vectors_out[lane] = embedding_vectors[lane]; }`
  with four unguarded stores at `lane`, `lane + 128`, `lane + 256`,
  `lane + 384`;
- dispatch `grid:(512,1,1) threadGroup:(512,1,1)` →
  `grid:(128,1,1) threadGroup:(128,1,1)`.

**Exactness.** `hidden_size` is 2048 and the store type is `vec<bfloat,4>`, so
the kernel must write exactly 2048/4 = 512 vec4 slots. The old form issued 512
lanes × 1 store, with a `lane < 512` guard that was dead code at its own
geometry. The new form issues 128 lanes × 4 stores covering 0…511 exactly —
same slots, same values, same source pointer arithmetic, no float arithmetic
anywhere in the kernel. The two angle copies need `full_width/4 = 16` and
`sliding_width/4 = 32` lanes and both remain resident in a 128-lane grid. The
removed bounds guard is only sound at exactly 128 lanes, which is why the guard
removal and the dispatch change are one atomic edit.

**Locally verified exact**, not merely argued: `benchmark.sh --local-iterate`
returns `passed_correctness: true` with `golden_hash`
`b9509697c08a2cf3c2943a85f0b76e39c485c441794690fa76835b40a58d7a63`, byte-identical
to the baseline build's golden hash.

**Suspected mechanism:** threadgroup residency, not arithmetic. A 512-thread
threadgroup is 16 SIMD groups that must be co-resident on one core; 128 threads
is 4.

**Honest expectation.** On our local M4 development host this change measured
**−0.0260 % decode (−3.4 µs/token)**, which is *inside* that host's 0.05–0.1 %
repeatability band. We are not claiming a measured win. We are claiming a
proven-exact, non-negative change on a code path that the ranked M5 host
exercises differently from ours, submitted because the marginal cost of
measuring it is one otherwise-idle channel slot.

---

## 2. Why this tree and not a replay

The leaderboard rewards volume, and a replay of an already-drawn tree buys a
lottery ticket. This tree buys the same ticket **and** resolves a code
question, because the candidate timing legs in an official receipt are far more
precise than the published score. Same cost, strictly more information.

The precision claim is measured, not assumed. Receipts
`c1c0ba2c` and `88584270` are the **same executable** — their trees differ by a
four-line comment in `DenseTensorStore.swift` — so every difference between
them is instrument noise:

| statistic | spread across the same-executable pair |
|---|---:|
| published score | **1.0126 %** |
| normalized score | **0.0020 %** |
| candidate decode leg | 0.0054 % |
| candidate prefill leg | 0.0245 % |
| baseline decode leg | 0.3305 % |
| baseline prefill leg | **5.1429 %** |

with `normalized = (REF_D/decode)^0.75 × (REF_P/prefill)^0.25`,
`REF_D = 0.01385621216015625`, `REF_P = 0.00036751938916015626`. The identity
`published = normalized × draw` holds to a maximum relative error of 3.3e-15
across all 1230 receipts that carry full legs, so this is a decomposition, not
a fit.

Consequence: the published score needs ~470 receipts to resolve a 0.07 % arm at
2σ; the normalized score needs **~1**. And the variance being divided out is
almost entirely the *baseline prefill* leg — cv 1.9327 %, contributing 0.4832 %
of the 0.5362 % draw cv, i.e. **87 % of all leaderboard variance comes from a
leg that has nothing to do with our code.**

---

## 3. Ticket 3 was a real regression, and one receipt proved it

Ticket 3 flipped the `DARKBLOOM_ATTN_QHOIST` default 0 → 1. Result:

| ticket | decode µs | prefill µs | normalized | draw | published |
|---|---:|---:|---:|---:|---:|
| 1 `c1c0ba2c` | 4932.4 | 187.69 | 2.566844 | 1.001130 | 2.569744 |
| 2 `88584270` | 4932.6 | 187.65 | 2.566903 | 1.011244 | 2.595765 |
| 3 `e4078827` | 4948.5 | 196.30 | **2.532027** | 0.998068 | 2.527136 |

Ticket 3 versus ticket 1: decode **+16.1 µs (+0.327 %)**, prefill
**+8.61 µs (+4.586 %)**, normalized **−1.3564 %**.

**−1.3564 % is 678× the same-executable normalized noise band of 0.0020 %.**
By published score the move was −1.66 %, only 1.6× a spread that a
*same-executable* pair produces by luck alone — a one-sigma shrug. The
normalized statistic called it outright from a single receipt.

Attribution has no confound. A comment- and whitespace-invariant diff of the
two official package trees (`074f47e4`…`ec0954e2`) reports **4 semantic lines
across 3 files** — `jit_kernels.cpp` 2/2, `steel_attention_nax.h` 1/1,
`mlx-generated/steel_attention_nax.cpp` 1/1 — and those four lines *are* the
QHOIST flip. Raw churn was +23/−11; the rest is comment text.

The pre-flight compile gate for ticket 3 had been green and correct: `-D…=0`
produced 285,968 B of `.air`, `=1` produced 288,288 B, and the ordinary build
produced 288,288 B, so the flipped default provably reached the compiler. **A
green compile gate proves a change is live; it says nothing about whether it is
good.** Ours was live and bad.

---

## 4. Two hypotheses this campaign killed with builds rather than arguments

**4.1 "We deleted 5,213 lines of upstream work."** `git diff --stat` of our
branch against fork base `1bc1c895` over `Sources` + `Vendor` reads
**+2382 / −5213**. That is an artifact of a deliberate comment-stripping commit
run to reclaim editable-byte budget. Classifying lines gives +342/−206 code
against +2040/−5007 comment or blank (96.0 % of deletions). Lexing comments out
properly — needed because the same pass stripped *inline* comments from
otherwise unchanged lines — gives the true figure: **+63 / −16 semantic lines
across 5 of 30 touched files, 1.0 % of the raw churn.** 25 of the 30 files are
comment-only.

**4.2 "Those 59 lines are why our decode is slow."** Tested directly: a scratch
branch with `Sources` and `Vendor` reverted wholesale to `1bc1c895`, rebuilt
and benchmarked with the harness held at our revision.

| arm | decode s/tok | vs ours |
|---|---:|---:|
| ours | 0.012953359 | — |
| fork base `1bc1c895` | 0.012990220 | **+0.28 % slower** |

Both `passed_correctness: true`, identical `golden_hash`. Our branch delta is a
small net *gain* over the fork base. The hypothesis is dead, so whatever the
faster packages have, the fork base never had it either.

---

## 5. Where the remaining deficit is, stated honestly

The runner's own **baseline decode leg** is a free host thermometer in every
receipt. Bucketed by UTC day over 1230 full-leg receipts, its median spans
13834.3–13883.0 µs and its daily minimum spans 13780.7–13821.4 µs across all 18
days — a **0.35 % total range**. There is no host regime change to hide behind.

Against that stable host, the candidate frontier fell monotonically from
12149.5 µs (07-24) to 4886.0 µs (08-08) and has been flat for four days
(4886.6, 4886.0, 4893.7, 4890.7). On 2026-08-10, across 23 receipts from 4
solvers, the day's candidate decode minimum was 4890.7 µs, p10 4904.4 and
**median 4916.6**. Our two receipts that day were **4932.4 and 4932.6 — worse
than the day's median.** So we carry roughly **41.9 µs/token (0.86 %)** of real
decode deficit, and it is code, not luck and not thermals.

We have not yet located it, and we can now say precisely where it is *not*.
Semantic diff against the faster public package left exactly two decode-path
differences: the atlas kernel version, and a router weight prefetch that we
carry and they do not. Both axes were built and benchmarked as a full 2×2, all
four arms `passed_correctness: true` with an identical `golden_hash`:

| atlas | router prefetch | decode s/tok | Δ vs ours | Δ µs |
|:-:|:-:|---:|---:|---:|
| v2 | 1 (ours) | 0.0129533590 | — | — |
| **v3_tg128** | 1 | **0.0129499915** | **−0.0260 %** | **−3.37** |
| v3_tg128 | **0** | 0.0129673988 | +0.1084 % | +14.04 |
| v2 | 0 (fork base) | 0.0129902204 | +0.2846 % | +36.86 |

Holding atlas at v3 and flipping only the prefetch knob costs **+17.41 µs
(+0.134 %)**, about 2× the 0.05–0.10 % repeatability band. So *removing* our
prefetch to match the faster package would make us slower, not faster; that
difference is not the discriminator either. Neither axis of the 2×2 explains
41.9 µs. The remaining live hypothesis is that the advantage sits in a NAX-only
code path, which this development host cannot execute at all — `_nax` is
permanently off on M4 — so local A/B is structurally blind to it. That is where
the next arms are aimed. This is a negative result honestly labelled: ticket 4
promotes a change that is free and exact, and reverts one that was measurably
harmful, and it does not claim to have closed the gap.

---

## 6. Correctness and provenance

- `passed_correctness: true`, `golden_hash b9509697c08a2cf3…` unchanged from the
  baseline build.
- Score form `decode_speedup^0.75 × prefill_speedup^0.25`, both floors ≥ 0.95,
  understood and unmodified. No harness, scoring, gate or baseline file is
  touched by this submission.
- Local development host is an M4 with 48 GiB, materially slower than the
  ranked host (decode 12953 vs 4932 µs, prefill 1122 vs 187.6 µs) while using
  the same official reference constants. Local absolute scores are therefore
  meaningless and only within-host arm ordering is used above; every ranked
  number quoted in this note comes from official receipts.

---

## 7. Corrected framing — this is a best-believed-package draw, not an arm probe

Between drafting §1–§6 and firing this shot I measured the ranked instrument
against itself, and the result changes what this submission *is*. The numbers
come from `research/fern_r109f_leg_noise.py` over a single UTC hour
(2026-08-10T00, n=24 full-leg correct receipts), where the baseline leg is by
construction identical code every time:

| leg | mean | sd | cv |
|---|---|---|---|
| baseline decode | 13858.94 µs | 31.08 | **0.224 %** |
| candidate decode | 4920.61 µs | 13.69 | **0.278 %** |
| baseline prefill | 371.15 µs | 6.52 | **1.756 %** |
| candidate prefill | 188.64 µs | 1.796 | **0.952 %** |
| normalized score | — | — | **0.370 %** |

Baseline decode cv 0.224 % is pure host jitter. Candidate decode cv is
0.278 %. So the *between-package code* component across the entire modern
field is at most √(0.278² − 0.224²) = **0.164 %**, about **8 µs**. Every
solver in that window is running code within 0.16 % of ours.

Consequences for this note:

1. **A single receipt cannot adjudicate a sub-1 % arm.** Two-sample, α .05,
   power .95 needs ~40 receipts per arm to see 0.30 %, ~89 for 0.20 %, ~355
   for 0.10 %. My local iterate repeats to 0.05–0.10 %, so the *development
   host is a 4–7× better instrument than the ranked host*, even with `_nax`
   permanently off. Arm-class ranked probes are therefore the wrong use of a
   scarce slot and this campaign stops firing them.
2. **This shot is deliberately the best-believed package**, HEAD = r109-F base
   + atlas v3_tg128 with QHOIST reverted, carrying a comment-only nonce. It is
   a lottery ticket drawn from the best tree we have, not a measurement. Do not
   read its normalized value as evidence for or against atlas v3; the local
   −0.026 % is already below the ranked instrument's floor.
3. **Two of my own earlier claims in this campaign are retracted.** (a) I
   reported the normalized instrument as a "0.002 % instrument" because
   packages `074f47e4` and `04e8bf3c` returned 4932.4 and 4932.6 µs. That
   0.2 µs agreement is 0.015 σ out of σ = 13.7 µs — a coincidence with
   p ≈ 1.6 %, not a resolution measurement. (b) I reported our own package
   `5c542169` as "rank 2 of 1231, 0.64 % ahead of what we are submitting" and
   proposed reconstructing it. Its 4890.7 µs is a **−2.19 σ** draw of the same
   code cluster; reconstructing it buys nothing in expectation. I staged that
   reconstruction and reverted it before spending a slot.
4. **The QHOIST verdict in §3 stands, with corrected effect size.** It is
   **−1.36 % normalized = −3.82 σ** of the single-receipt instrument
   (p ≈ 1.3e-4), not the "678× the noise band" I wrote earlier. It is also
   **prefill-driven**: candidate prefill 196.30 µs is **+4.27 σ** against the
   08-10 population (187.56–190.18, mean 188.4, sd 0.83), while its decode
   excess of 16 µs is only ~1.2 σ. A −3.82 σ single draw is still decisive
   enough to justify the revert carried in this tree.
5. **Crown EV, empirically.** `research/fern_r109f_crown_ev_empirical.py`:
   **0 of 131** full-leg receipts since 08-06 exceed the crown; the best
   published in that span *is* the crown. Wilson 95 % upper bounds on per-shot
   p are 0.0285 (n=131) and 0.0741 (n=48); point estimate ≈ 1/131 = 0.76 %.
   The modern cluster (since 08-09, n=48) has published mean 2.575305,
   sd 0.014284 (cv 0.555 %), and the crown sits **+2.88 sd** above that mean.
   Centring the distribution on the crown needs **+1.600 % of code** — ten
   times the field's entire observed code spread. So p ≈ 0.2–0.8 % per shot and
   n(50 %) ≈ 90–350 shots ≈ 33–127 h at ~22 min service. Saturating the channel
   remains correct because the marginal cost of a draw is near zero, but the
   campaign should not be planned around a crown arriving.

Nonce again for archive de-duplication:
`atlasv3-r109f-t4-2026-08-11T01Z-nonce-7b3e0d51-a`
