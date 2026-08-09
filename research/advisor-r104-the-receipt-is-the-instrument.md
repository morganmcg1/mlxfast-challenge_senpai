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
it already shipped as `LAGUNA_RESCALE` (`:1647-1658`). The only surviving
sub-lever is constant-folding `N`/`capacity` in the FULL attention kernel
(10 calls/step, 20–40 µs), rated *weak*.

**The lesson is not "the advisor was sloppy".** It is that this archive is
large enough and old enough that *plausibility is not evidence of novelty*, and
the cost of the grep is minutes while the cost of skipping it is a student
round. Three for three.

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
  deletion fully explained by the tracer's hard 1,671,168-byte quota, and it
  reproduces across two independent dumps.
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

Both fused attention kernels dispatch exactly **32 threadgroups**. A 20-core M4
runs that in **two waves**; a ≥32-core ranked host runs it in **one**. An M4
A/B is therefore **structurally uninformative for ranking mechanism A against
mechanism B**. He cancelled his own preregistered M4 A/B at 6 legs (K = 3 vs a
preregistered 16), published the legs, and claimed nothing. He also flagged the
M5-only `_nax` blind spot: "exactly 2 of 103" is a **lower bound** on the ranked
host, not an equality.

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
two hosts, with **opposite signs** — and §4.1 supplies the mechanism for the
disagreement: at 32 TGs the M4 runs two waves and the M5 runs one, so the two
hosts are not measuring the same thing.

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
* Every brief carries the rule-83 grep **with §3 above as the cautionary
  example**, rule-72 preregistered nulls, rule-75 digests, rule-79 identical-code
  null, rule-80 GB/s ÷ host peak, rule-77 dispatch geometry, K ≥ 16, discard the
  first leg, and an **explicit receipt budget**.

## 7. Do not re-derive these

* The receipt-power table in §1. It is measured, not modelled.
* The absence of a receipt quota (§2). Do not re-audit the corpus for it.
* The two-mechanism inventory (§4). It has an A/A control and a byte-level null.
* That an M4 A/B cannot rank the two attention mechanisms (§4.1).
* §8 of `advisor-r103-what-winning-costs.md` is retracted (§3a). Do not revive
  the threadgroup-memory cliff.
* `DARKBLOOM_FUSED_QKV` (§3b) and the H7 rescale skip (§3c) are dead.
