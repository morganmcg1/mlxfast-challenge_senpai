# r97-c result — two-stage simdgroup-axis split of the two fused decode attention kernels

**Assignment** `maple-r97-c-attn-two-stage-split` / `r97-c-rev1` · PR #528 ·
branch `maple-nezuko/r97-attn-two-stage-split` · base `b78e7cd` (R93-A / #496).
Host: Apple **M4 Pro**, `applegpu_g16s`, 20 GPU cores, 48 GiB. Ranked host is
**M5 Max, 40 cores, gen 17** — no official receipts were taken for this arm.

Pre-registration: [`nezuko-r97-attn-split-preregistration.md`](nezuko-r97-attn-split-preregistration.md),
committed in `ed4d4c7` before any timing data existed.

## Verdict

| state | pre-registered bar | outcome |
| --- | --- | --- |
| **Gate 0** — bit-exact `simd_sum` replacement | byte-identical golden + identical token hash | **PASS** (stronger: exact reduction order identified) |
| **sliding split** 32 → 512 TGs | ≥ **120 µs/step** | **NO-GO** — measured ceiling **45–56 µs/step**, before paying 70.2 µs/step of cost |
| **full split** 24 → 96 TGs | ≥ **40 µs/step** further | **NO-GO** — measured ceiling **30–36 µs/step**, before paying 23.4 µs/step of cost |

Neither split state was implemented in the runtime. Both were falsified by a
pre-registered ceiling ladder that measures the mechanism's **strict upper
bound** and finds it below the bar. No editable-path file was touched, so
submitted growth is **0 B** and the static-review surface is unchanged.

## 1. Gate 0 — PASS, and stronger than asked

The assignment made everything conditional on replacing `simd_sum` with an
explicit `simd_shuffle_xor` ladder without changing a single output bit.
`research/nezuko_r97_simdsum_order_probe.swift` answers this directly: 200,000
independent 32-lane vectors, adversarial data (random mantissa × 2^e,
e ∈ [−12, 12]) chosen so fp32 addition is maximally non-associative.

```
xor_ascending     vs simd_sum: bitexact 6400000/6400000 (100.000%)  max_ulp 0
xor_descending    vs simd_sum: bitexact 2434848/6400000 ( 38.044%)  max_ulp 98304
shuffle_down_tree vs simd_sum: bitexact 2434848/6400000 ( 38.044%)  max_ulp 98304
prefix_sequential vs simd_sum: bitexact 1734912/6400000 ( 27.108%)  max_ulp 66638
two_level         vs simd_sum: bitexact 6400000/6400000 (100.000%)  max_ulp 0
```

**`simd_sum` over 32 lanes *is* the ascending XOR butterfly** (deltas
1, 2, 4, 8, 16). It is not a shuffle-down tree, not a descending butterfly, not
a sequential prefix — those three disagree with it on 62–73 % of vectors and by
up to 98,304 ULP. A two-level grouped decomposition is also bit-exact.

Gate 0 therefore passes: a hand-written bit-exact replacement exists and is
known exactly. *Caveat*: measured on gen 16. `simd_sum` lowering is a compiler
decision and the ranked M5 is gen 17, so the identity must be re-confirmed
there before anyone ships code that depends on it.

## 2. Why Gate 0 passing does not buy the split (structural proof)

Gate 0's premise was that a threadgroup-axis split needs a *generic* reduction
regrouping. That premise is wrong in both directions, and the reason kills the
cheap version of the mechanism.

**Online softmax does not combine like a sum.** Partition *p* produces
`(m_p, s_p, o_p)`. The exact merge is max-then-rescale-then-sum. Grouping
partitions hierarchically computes

```
Σ_g ( Σ_{p∈g} o_p · exp(m_p − M_g) ) · exp(M_g − M)
```

and in fp32 `exp(m_p − M_g) · exp(M_g − M) ≠ exp(m_p − M)`. So *no* regrouping
of the cross-partition combine is bit-exact.

**Consequence.** Bit-exactness forces every partition's full `(m_p, s_p, o_p)`
across the threadgroup boundary, in the original partition order. That is a
partition-preserving split, which:

- needs **no** reduction-order change at all — stage 2 re-invokes the identical
  `simd_sum` over the identical 32 values with lane = partition index, so
  Gate 0's ladder is not even required on the critical path; and
- **cannot** merge in stage 1, so it forces a **second dispatch per attention
  layer**: 30 sliding + 10 full = **40 extra dispatches per decode step**.

That second dispatch is the whole cost of the mechanism, and it is not
avoidable while correctness is a hard gate.

## 3. Ceiling ladder — the pre-registered falsifier

`research/nezuko_r97_split_ceiling_ladder.swift` measures how much a
threadgroup-count split can *possibly* recover, ignoring every cost.

Design (#497 blocked-randomised, rule 56): 40 blocks, all rungs visited in a
fresh random order inside each block, 200 in-kernel iterations per measurement,
GPU-timestamp timing, medians across blocks, 4000-resample paired bootstrap on
the ratio against the shipped rung.

What makes it a **ceiling**: every rung runs the same per-simdgroup body over
the same K positions, holds total work and total requested K+V traffic exactly
constant (8 MB/call sliding, 6 MB/call full at *every* rung), and the split
rungs are handed their cross-threadgroup combine **for free** — no partial
buffer is written, no second dispatch is issued, and launch overhead is
amortised over 200 iterations so the measured fraction is the pure
wave-dependent recovery. Nothing a real implementation could do would beat it.

Rung `N = headPairs · t`, with `t` threadgroups per head pair and `32/t`
simdgroups each.

### 3.1 Sliding, 32 head pairs (64 heads), 30 calls/step

| N | t | sg/TG | thr/TG | median µs/call | recovery | 95 % CI | **predicted** |
| ---: | ---: | ---: | ---: | ---: | ---: | --- | ---: |
| **32** | 1 | 32 | 1024 | 10.092 | +0.00 % | — | 0.00 % |
| 64 | 2 | 16 | 512 | 9.998 | +0.94 % | [−2.59, +1.77] | **0.00 %** |
| 128 | 4 | 8 | 256 | 8.790 | +12.90 % | [+10.23, +13.72] | **12.50 %** |
| 256 | 8 | 4 | 128 | 8.241 | +18.34 % | [+15.55, +19.10] | **18.75 %** |
| 512 | 16 | 2 | 64 | 8.239 | +18.36 % | [+18.66, +19.35] | **18.75 %** |

### 3.2 Full, 24 head pairs (48 heads), 10 calls/step

| N | t | sg/TG | thr/TG | median µs/call | recovery | 95 % CI | **predicted** |
| ---: | ---: | ---: | ---: | ---: | ---: | --- | ---: |
| **24** | 1 | 32 | 1024 | 10.059 | +0.00 % | — | 0.00 % |
| 48 | 2 | 16 | 512 | 7.699 | +23.46 % | [+23.07, +23.63] | **25.00 %** |
| 96 | 4 | 8 | 256 | 6.498 | +35.40 % | [+35.19, +35.65] | **37.50 %** |
| 192 | 8 | 4 | 128 | 6.493 | +35.45 % | [+35.27, +35.64] | **37.50 %** |
| 384 | 16 | 2 | 64 | 6.434 | +36.04 % | [+35.93, +36.34] | **37.50 %** |

The predicted column is the pre-registered wave model
`makespan(N, t) = ceil(N/cores)/t`, evaluated at 20 cores. **The pre-registered
plateau-then-step shape is reproduced on both ladders to within 1.5 percentage
points**, including the non-obvious details: the sliding ladder's *flat* rung at
N=64 (predicted exactly 0 % recovery — 64 TGs on 20 cores is still ceil = 4
waves of half-length, identical makespan) and both ladders' saturation once `t`
is large enough that quantisation waste is exhausted. The mechanism is real and
the model of it is right. It is simply too small.

Bootstrap CIs are on the **mean** ratio while the point estimate is the
**median** ratio, which is why the sliding N=512 interval sits slightly above
its point estimate; the per-block distribution is right-tailed. Every
conclusion below uses the most generous end of the interval.

An independent confirmation run of the same binary reproduced both ladders:
sliding saturation +18.99 % (tabled +18.34 %), full saturation +36.23 %
(tabled +36.04 %), sliding N=64 still flat at +1.81 %. The shipped-geometry
anchor was 10.160 / 10.077 µs versus the tabled 10.092 / 10.059 µs, i.e. run-to-
run drift of ≤0.7 pp on the recovery fractions and ≤0.7 % on the anchor. The
tables above are the earlier, **less** favourable run; using the confirmation
run instead moves the M5 net from −18.0 to −16.3 µs/step, which does not
approach either bar. The verdict is not sensitive to which run is quoted.

### 3.3 Why an M4 fraction is admissible evidence for M5 here

Rule: threadgroup geometry can change sign across core counts, so an M4 result
is normally not evidence for M5. **These two rung sets are the exception, by
construction.** The recovery fraction is `1 − ceil(N·t/cores)/(t·ceil(N/cores))`
and for both ladders it is numerically identical at 20 and 40 cores:

| | shipped | t=16 split | 20 cores | 40 cores |
| --- | --- | --- | --- | --- |
| sliding | 32 TGs | 512 TGs | 2 → 1.625 = **0.8125** | 1 → 0.8125 = **0.8125** |
| full | 24 TGs | 384 TGs | 2 → 1.250 = **0.625** | 1 → 0.625 = **0.625** |

Different reasons (M4 pays 2 whole waves, M5 pays 1 wave at 80 %/60 %
occupancy), same ratio. Occupancy is not a confound either: total resident
simdgroups is 1024 at every rung, the per-thread register footprint is
unchanged by threadgroup size, and the epilogue's threadgroup memory *shrinks*
with smaller TGs. The split redistributes a fixed simdgroup population more
evenly across cores — that is the entire mechanism, and it has no hidden upside.

## 4. Projection onto the ranked M5, and the kill

Programme constants, all verified in-repo:

| quantity | value | source |
| --- | --- | --- |
| M5 sliding attention | ≈ 290 µs/step | `CURRENT_RESEARCH_STATE.md:551` |
| M5 full attention | ≈ 100 µs/step | `CURRENT_RESEARCH_STATE.md:551` |
| M5 dispatch glue | 2.3403 µs [2.2766, 2.4040] | `r93-runs/RESULTS.md:328` |
| M4 dispatch glue | 1.2382 µs [1.2237, 1.2518] | rule 57, `CURRENT_RESEARCH_STATE.md:417` |
| wave-dependent share | 84.7 % | `t(K) = 1.413 + 7.849·ceil(K/cores)` (r96-a) |
| score noise σ | 0.6172 % | #496 |

Gain = `cost × fraction × wave-dep`. Cost = `dispatches × µs/dispatch`.

| scenario | sliding gain | sliding cost | full gain | full cost | **net** |
| --- | ---: | ---: | ---: | ---: | ---: |
| wave-dep 0.847, median fraction | +45.1 | −70.2 | +30.5 | −23.4 | **−18.0** |
| wave-dep 1.000, median fraction | +53.3 | −70.2 | +36.0 | −23.4 | **−4.3** |
| wave-dep 1.000, CI-upper fraction | +56.1 | −70.2 | +36.3 | −23.4 | **−1.2** |
| wave-dep 1.000, *optimal* geometry (t=5) | +58.0 | −70.2 | +40.0 | −23.4 | **+4.4** |

All units µs/step. The last row is physically unreachable: it assumes the
kernel has *zero* fixed cost, uses the theoretically optimal rung
(sliding 160 TGs → 0.80, full 120 TGs → 0.60) rather than a measured one, and
still charges nothing for partial-buffer traffic.

**Both pre-registered bars fail, and they fail on the gross gain alone.** The
sliding bar is ≥ 120 µs/step; the most generous measured ceiling is
**56.1 µs/step**, 2.1× short *before* subtracting 70.2 µs/step of dispatch cost.
The full bar is ≥ 40 µs/step; the most generous measured ceiling is
**36.3 µs/step**, short before subtracting 23.4 µs/step. No implementation can
clear a bar that exceeds its own ceiling, so implementing was not merely
unpromising — it was pre-registered as pointless.

**Score-level statement.** Taking M5 decode at ≈ 3.9 ms/step (from sliding
holding its M4 decode share of 7.46 %), the plausible outcome is
−18.0 µs/step ≈ −0.46 % decode ≈ **−0.35 % score**, and the absolute
best conceivable outcome is +4.4 µs/step ≈ **+0.09 % score**. σ(score) is
0.6172 %. **The entire two-sided range of this mechanism on the ranked host is
inside the noise floor** — the best case is 7× below σ and could not be
distinguished from zero even if it were free.

**Uncounted cost, in the same direction.** A partition-preserving split spills
`(m, s, o[128])` fp32 per head per stage-1 threadgroup:
`30·32·16·2·130·4 + 10·24·16·2·130·4 = 19.97 MB` written and read back
= **39.9 MB/step**, +2.2 % of the 1794 MB/step budget. At the programme's
0.015224 %/MB that is a further **−0.61 % score**, which on its own exceeds the
best case in the table. It is left out of the arithmetic above only because
freshly-written partials may be SLC-resident; nothing depends on it.

*(Correction to the pre-registration: §5 there quoted ≈79.9 MB/step for this
traffic. The correct figure at these rungs is 39.9 MB/step. The smaller figure
is used here; it does not change any verdict.)*

## 5. The transferable finding: M4 flatters split mechanisms by ~4×

The same sliding-split mechanism, at the same measured 18.36 % fraction and the
same 84.7 % wave-dependent share, priced on each host with *that host's own*
constants:

| | attention cost | gain | dispatch cost | net | gain/cost |
| --- | ---: | ---: | ---: | ---: | ---: |
| **M4 Pro**, 1.2382 µs/dispatch | 636.0 µs/step | +98.9 | −37.1 | **+61.8** | **2.66** |
| **M5 Max**, 2.3403 µs/dispatch | 290 µs/step | +45.1 | −70.2 | **−25.1** | **0.64** |

M4 is **4.1×** more favourable, and the factor decomposes exactly:
`(636.0 / 290) × (2.3403 / 1.2382) = 2.19 × 1.89 = 4.14`. Two independent
effects compound — the kernel M4 is shrinking is 2.19× larger in absolute terms,
so there is simply more waste to recover, while the dispatch M4 must buy is
1.89× cheaper. Neither is visible in a shape comparison, and the *fractions*
agree perfectly across hosts (§3.3), so a correct, well-powered,
shape-matching M4 ladder would have said "implement" while the ranked host
says "regression".

**This is exactly the trap the ceiling ladder was built to catch, and it caught
it on my own bar.** My pre-registered M4-unit ceiling bar (recovery must exceed
the M4 second-dispatch cost) **PASSED**, +98.9 vs −37.1 µs/step. I registered
it in advance as a *one-way* test — a fail kills the arm, a pass is not a
licence — precisely because M4 is the friendlier host. Had I registered it
two-way, this arm would have shipped an M4-validated regression.

**Proposed programme rule.** Any mechanism that trades kernel time for
dispatch count must be priced with M5 constants before implementation. The
M4→M5 penalty for that trade is ≈ **4.1×** on the sliding kernel and
≈ 1.89× × (M4 kernel µs / M5 kernel µs) in general; an M4 net win smaller than
~4× its M4 dispatch cost is not evidence of an M5 win.

## 6. What would revive part of this

Only the **full-attention** half is close. Its measured ceiling
(+36.0 µs/step at wave-dep 1.0) exceeds its own dispatch cost (−23.4), so
full-attention splitting is *net positive* on M5 at +7 to +13 µs/step — it just
fails a 40 µs/step bar and lands 2.5–4.5× below σ, so it cannot be validated by
measurement. It becomes worth revisiting only if the second dispatch stops
costing 2.34 µs, i.e. if some *other* accepted change already introduces a
stage boundary in the full-attention path that this could ride for free.

The sliding half is dead regardless of geometry: its optimal rung recovers
20.0 % of 290 µs/step = 58.0 µs/step against an unavoidable 70.2 µs/step of
dispatch, so it is a net loss even with zero fixed cost and zero spill traffic.

## 7. Follow-ups I did not implement

1. **Re-confirm the `simd_sum` = ascending-XOR-butterfly identity on gen 17.**
   Cheap (one standalone probe, no runtime edit), and it unblocks any future
   arm that needs a hand-written bit-exact simdgroup reduction. This is the
   durable asset from Gate 0.
2. **Attack the redundant phase-1 work instead.** `CURRENT_RESEARCH_STATE.md:553`
   records 28 of 32 simdgroups idle with no loads in flight before a barrier,
   and every threadgroup sharing a KV head redundantly recomputing that head's
   K RMSNorm+RoPE (4× sliding, 3× full). That is real duplicated work inside the
   existing dispatch — no second dispatch, no partial spill, no wave-quantisation
   ceiling.
3. **Price the 40 % full-attention rung** if a stage boundary ever appears there
   for another reason.

## Reproduction

```bash
xcrun swiftc -O research/nezuko_r97_simdsum_order_probe.swift \
  -o /tmp/nezuko_simdsum_probe -framework Metal -framework Foundation
/tmp/nezuko_simdsum_probe

xcrun swiftc -O research/nezuko_r97_split_ceiling_ladder.swift \
  -o /tmp/nezuko_r97_ladder -framework Metal -framework Foundation
/tmp/nezuko_r97_ladder
```

Both are standalone Metal probes; neither touches the model, the harness, or
any editable path. Runtime ≈ 4 minutes combined on the M4 Pro.
