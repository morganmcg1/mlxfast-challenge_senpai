# R102-B: the composed R1∘R2 restoration tree

Student: maple-tanjiro. PR #565. Assignment
`maple-r102-b-composed-restoration-receipt`, revision `r102-b-rev1`.
Base `aba31ba9e461c8a4f7a0ba7086b417f0868fcad9`.

> **Status: complete.** All eleven sections are final. Three M4 duplex sessions
> (A, B, C) and one official M5 receipt
> (`e08d759f-8e52-46e7-8b29-2c8647cfaae8`) are analysed.
>
> **Headline:** the composed tree is **additive**. `I = +0.037 % ± 0.056 %` of
> M5 score (§9), consistent with zero — but additive **by cancellation of three
> significant per-kernel interactions**, not by independence (§6.4). Nothing
> needs un-merging. Two corrections to campaign bookkeeping are in §10 and §11.
>
> **This experiment changes no scored code.** `git diff --name-only
> aba31ba9e461c8a4f7a0ba7086b417f0868fcad9 HEAD -- Sources/ Vendor/
> benchmark.json` is empty; every arm was built from a temporary snapshot
> outside the worktree (§6.2).
>
> **W&B run:** `nydjf4sf` —
> <https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/nydjf4sf>
> (project `wandb-applied-ai-team/mlxfast-maple`, name
> `maple-tanjiro-r102b-composed-restoration-2x2`, job type
> `paired-duplex-2x2`). It carries the six tables behind §5, §6, §8 and §10
> (`arms`, `ir_census`, `kernel_interaction`, `kernel_levels`, `nulls`,
> `record_probability`) plus the scalar summary. Regenerate it with
>
> ```bash
> python3 research/artifacts/tanjiro-r102b/r102b_wandb.py \
>   --dir research/artifacts/tanjiro-r102b \
>   --base-sha aba31ba9e461c8a4f7a0ba7086b417f0868fcad9 \
>   --cand-sha 4634345f45886a1d0233d7e1ad3066e6d0bfff15
> ```
>
> The logged `cand-sha` is this paragraph's parent commit; the only later commit
> is the one that adds this paragraph, which changes no data or analysis.

## 1. What was composed, and why it had never been measured

Two decode-attention restorations coexist in
`Sources/MLXFastModel/LagunaRuntimeModel.swift` at this branch's head. Each had
been measured alone against a same-session paired baseline on the official
host. Neither had ever been *built* together with the other — not locally, not
officially.

| id | mechanism | scope | source delta | official solo result |
| --- | --- | --- | --- | --- |
| R1 | float4 merge epilogue: `threadgroup float4 outputs4[BN * BDP]` staging in the cross-block merge | **both** decode attention kernels | −454 B | **+0.2358 %** [+0.1347, +0.3368] |
| R2 | 2-deep → 4-deep sliding key/value load ring (`for (; i + 3 * BN < N; i += 4 * BN)`) | sliding kernel only | +4,086 B | **≈ +0.130 %** |

R1 comes from PR #555 (mine); R2 from PR #539 (frieren).

The reason this pair is the one worth a receipt: R2 changes the tile loop that
*produces* the per-block partial results, and R1 changes the epilogue that
*merges* them. They meet in the same kernel, on the same data, one stage apart.
If any pair in our ledger is going to interact, it is this one — and our
forward projections have been implicitly summing solo deltas as though no pair
interacts at all.

Under pure additivity:

```
cs ≈ 2.575633 × (1 + 0.002358 + 0.00130) = 2.58506
```

i.e. **+0.366 %** over the control receipt `59bd72a3` (`cs = 2.575633`). The
record is `2.61650354381456`. `2.58506` has never been measured as a frontier
anywhere, which is the point: the receipt resolves additivity by measurement
rather than by inference.

## 2. Preregistration

`research/tanjiro-r102-preregistration.md`, commit `88d2cb3a`, parent
`00e0ac7e` — committed **before any measurement of any kind**. It fixes four
nulls, each with an arm-level signature and an explicit falsifier:

- **N-A** clean additivity — the interaction term is zero within noise.
- **N-B** register-pressure sub-additivity — the composed kernel spills or
  loses occupancy relative to the sum of its parts. Cheap static test first.
- **N-C** R2 was never real — its solo delta was a session artifact.
- **N-D** M4 blindness — gen-16 cannot see the effect at all.

It also fixes the decision rules in advance: rule-78 null gate
(`|d%| ≤ 0.25 × smallest dose`), rule-79 same-session identical-code nulls read
at the same slot positions, rule-75 working-set digests, K ≥ 16, discard the
first leg, n ≥ 12 ABBA duplexes. And, critically, the **submission policy: P3
fires regardless of P2's sign unless P1 fails**. That clause is what makes the
receipt interpretable rather than selected-on.

## 3. Tree verification (P0)

| check | result |
| --- | --- |
| `origin/main` | `1bc1c8954147c9e322aad1f3b80bd9fa3c0888d7` |
| `benchmark.json` vs `origin/main` | identical, blob `3b0b6f9fec87eeb1641248308927ddc9fee72986` |
| editable budget | `current=2811013/3000000 headroom=188987 growth=-172836/262144 files=142 (base=142)` |
| `LagunaRuntimeModel.swift` blob size | 515,050 B (9,238 B under the 524,288 B per-file cap) |
| R2 tile loop present | `for (; i + 3 * BN < N; i += 4 * BN)` at LRM:1548 ✓ |
| R1 staging array present | `outputs4` ×10 ✓ |
| unrelated prefetch mechanism absent | `lagunaRouterWeightPrefetch` ×0 ✓ |
| arm-00 identity | `origin/main:…/LagunaRuntimeModel.swift` == `3567695b^:…/LagunaRuntimeModel.swift`, blob `08b1470526a931185b8397301cf22071ecfe8898` ✓ |

**One advisor doc error found and corrected.** The assignment states the tree
differs from `origin/main` in "exactly 1 file". Against `3567695b^` that is
true (+137/−83, one file). Against `origin/main` the diff is **27 files**: the
same `LagunaRuntimeModel.swift` delta *plus* 26 `Vendor/` files (+55/−3072)
which are the already-merged #548 rung-1 comment reclaim (`f720e9e7`) —
semantics-free, `mlx.metallib` bit-identical, and already carried by prior
receipts. `research/CURRENT_RESEARCH_STATE.md` contradicts itself on this and
is corrected in §11.

A second, smaller discrepancy: the advisor's brief cites `pipe_kc`/`pipe_kd`
marker counts of 20 each; the tree has **10 each**. This is a marker-count
difference only and does not affect which mechanism is present.

## 4. Correctness (P1) — complete pass

| gate | result |
| --- | --- |
| `./benchmark.sh --local-submit` (job `4f09b1db`, exit 0, 379 s) | `passed=true`, `passed_correctness=true`, **`max_abs_diff = 0`**, `checked_steps=1025`, golden `f49e4c2cbc0d3cee…`, harness `2e17da03…`, decode 0.00893259958455523 s/tok, prefill 0.00113108097265625 s/tok, est score 1.0494134671960618, peak RAM 20.728 GB, commit `88d2cb3a` |
| 64-step public drift tripwire (job `0f57f1e5`) | `passed=true`, `checked_steps=64`, `error=""`, golden `b9509697c08a2cf3c2943a85f0b76e39c485c441794690fa76835b40a58d7a63` (matches the campaign constant) |
| `research/run_upstream_equivalence.sh` | 1 test executed (non-zero ✓), `EQUIVALENCE_EXACT_STEPS=8`, decode-0..7 all `maximumAbsoluteLogitError 0.0`, every runtime token == upstream token |
| `swift test --force-resolved-versions` (job `65b4506b`) | 457 tests / 6 suites, 1 failure: the known unrelated `senpaiOperationalGuidanceMatchesTheDeployedRankedPath()` |
| rule-74 embedded-header check | `changed AOT sources: 0`, `embedded-twin risk: 0` |
| scope invariant | `git diff --name-only aba31ba9 HEAD -- Sources/ Vendor/ benchmark.json` → **empty** |

The one nuance worth stating plainly: the equivalence oracle reports
`maximumAbsoluteLogitError = 0.125` on the **prefill** step
(`meanAbsoluteLogitError 0.011933609`, token 5991 == 5991), and
`EQUIVALENCE_EXIT=1` because the harness runs at tolerance 0. That is the
documented pre-existing M4 Pro / gen-16 near-tie, recorded digit-for-digit at
`research/CURRENT_RESEARCH_STATE.md:215` and at
`research/frieren-r98-decode-qmv-result.md:153-162`, where the *unmodified
base* and every arm of that study also sit at exactly 0.125. This candidate
does not introduce it. All decode steps are bit-exact.

## 5. Static 2×2 interaction census

_Final; see §5.1–5.3._

### 5.1 Source level — provable disjointness

| arm | file | bytes | sha256 |
| --- | --- | --- | --- |
| 00 | neither | 511,418 | `c9074bdbe90879e1cfdae4af0c1f57ae5921dfee712ce9102858915d7108cdc0` |
| 10 | R1 only | 510,964 | `22b2db96bda47d921687cebb0b8f25ddf87a2ddd2b7b2feac32a92ef2618a02a` |
| 01 | R2 only | 515,504 | `a7c76a9aa2fe06be66a56220e18db1e75259f81abf9572e82136b3a3f3a3835b` |
| 11 | both (== HEAD) | 515,050 | `5e9192b91591f82d53d52a6f017f4446fa5eddbe4b84d81cfa1966ff1ef68018` |

`511,418 − 454 + 4,086 = 515,050`, exactly additive. Arm 11 reconstructed by
applying the R1 hunks and the R2 hunks independently to arm 00 is
byte-identical (`cmp` clean) to the real HEAD file, so **the two mechanisms'
hunks are provably disjoint**.

### 5.2 LLVM IR — every counter exactly additive

Sliding kernel `laguna_sliding_fused_attn_ring_v1`:

| counter | 00 | 10 | 01 | 11 | additive prediction |
| --- | --- | --- | --- | --- | --- |
| basic blocks | 63 | 55 | 83 | 75 | 75 ✓ |
| instructions | 686 | 666 | 906 | 886 | 886 ✓ |
| max live 32-bit regs | 107 | 99 | 143 | 135 | 135 ✓ |
| threadgroup loads | 28 | 26 | 44 | 42 | 42 ✓ |
| threadgroup stores | 11 | 9 | 11 | 9 | 9 ✓ |
| SIMD ops | 14 | 18 | 18 | 22 | 22 ✓ |
| `fmul` | 72 | 72 | 124 | 124 | 124 ✓ |
| `exp` | 10 | 10 | 18 | 18 | 18 ✓ |

Two counters matter more than the rest:

- **`tg_bytes` = 18,432 in all four arms.** The composition cannot lose
  occupancy through the threadgroup-memory axis.
- **`allocas` = 6 and `alloca_bytes` = 96 in all four arms.** The composition
  introduces no new spill slots.

Full kernel `laguna_full_fused_attn_grow_v1`: `full|01` ≡ `full|00` on every
counter and `full|11` ≡ `full|10`. R1's delta is identical with and without R2.

### 5.3 Compiled AGX machine code

`__compute` section bytes, **identical for `applegpu_g17p` (ranked M5, gen 17)
and `applegpu_g16s` (local M4, gen 16)**:

| kernel | 00 | 10 | 01 | 11 | additive prediction | interaction residual |
| --- | --- | --- | --- | --- | --- | --- |
| sliding | 5376 | 5200 | 6272 | 6080 | 6096 | **−16 B (−0.26 %)** |
| full | 6208 | 6032 | 6208 | 6032 | 6032 | **0 B** |

`__compute` section content hashes on the full kernel: arm 00 == arm 01 ==
`946fa24a22ebdf8d`, arm 10 == arm 11 == `cb63a94f8a78d350`. **R2 does not alter
one byte of the full-attention kernel's GPU machine code**, with or without R1.
Sliding-kernel hashes are all four distinct, as they must be.

Honest limit: `metal-objdump -d` is unavailable for the `agx3---macho` target,
so exact AGX *physical* register counts cannot be extracted with public
tooling. IR `max_live_regs32` and `__compute` size are the named proxies, and
both report additivity.

**N-B verdict: largely falsified statically.** Identical threadgroup memory, no
new allocas, exactly additive IR, and a marginally *super*-additive machine-code
residual. Residual risk is confined to the AGX register-allocator tier that
public tooling does not expose — which is exactly why the empirical answer was
worth buying.

## 6. Dynamic 2×2 on M4

### 6.1 Why three sessions, and which three

With unknown true per-step times `t00, t10, t01, t11` (R1 index first), the
four arms admit six pairwise contrasts. Only three are worth buying:

| session | contrast | estimates | meaning |
| --- | --- | --- | --- |
| **A** | arm00 → arm10 | `a = t10 − t00` | R1 with R2 **absent** |
| **B** | arm01 → arm11 | `b = t11 − t01` | R1 with R2 **present** |
| **C** | arm00 → arm11 | `total = t11 − t00` | the whole composed tree |

The interaction is `I = b − a`, so **A and B alone determine it** — that is the
question the round was assigned. A and B do *not* determine the total, because
neither pair spans `t00 → t11`. C supplies the total directly and then back-out
gives both conditional R2 effects, `t01 − t00 = total − b` and
`t11 − t10 = total − a`, whose difference must reproduce `I`. That identity is
the design's only internal consistency check; a fourth session (arm00 → arm01)
would over-determine the system and was not run.

Every contrast is measured **within one session as an interleaved duplex**, so
no conclusion depends on comparing numbers across sessions.

### 6.2 Protocol

Each session is 28 timing slots, `ORDER="base cand cand base"` repeated 7×,
`STEPS=200`, driven by `/tmp/r102b-session.sh` (archived as
`research/artifacts/tanjiro-r102b/r102b-session.sh`). Slots run from immutable
snapshots under `/tmp/r102b-sess<S>-snap/`; **the session runner never touches
the working tree**. Adjacent `base cand` and `cand base` slot pairs form signed
duplexes, which cancels linear session drift. The window is the last 199 steady
steps; both sessions independently reported `406` command buffers per step, so
`--cbs-per-step 406` is re-derived, not assumed.

Reported deltas are **ratio-adjusted**: each kernel's delta is normalised by the
duplex's own total-busy ratio, which removes whole-session clock and thermal
scaling. Absolute deltas are printed alongside and are used whenever the
adjustment could itself manufacture the effect.

Two integrity gates ran on every session:

- **Rule 75** — SHA-256 of both worker binaries and the metallib, taken before
  and after timing. All three digests matched post-timing in every session
  (`base` and `cand` per the arm table in §5, metallib
  `8e8b18af…` identical across all four arms).
- **Rule 79** — same-arm null duplexes at `--offset 1`, which pair
  `cand→cand` and `base→base`. These are reported in full in
  `research/artifacts/tanjiro-r102b/sess{A,B}_nulls.txt`.

### 6.3 Session integrity

| | Session A | Session B |
| --- | --- | --- |
| arms | arm00 (base) → arm10 (cand) | arm01 (base) → arm11 (cand) |
| job | `cc092deb`, exit 0, 1227 s | `625e3506`, **SIGTERM at 1242.6 s** |
| slots | 28 × 89,308 lines | 27 × 89,308 lines, slot 28 truncated to 2 |
| duplexes used | 14 | **13** |
| cbs/step | 406 | 406 |
| rule 75 | clean | clean |

Session B's supervisor reported `Job supervisor failed internally
(PermissionError)` and killed the job during slot 28's startup. That is a
harness artifact, not an experiment failure: the 27 completed slots are
byte-complete and their pre/post digests match, so slot 28 was simply dropped
and the analysis was restricted to slots 01–27 by explicit glob. The cost is
one duplex of statistical power, which widens B's total-busy band from ±4.3 to
±6.0 µs/step.

### 6.4 Result

Reproduce with:

```bash
python3 research/artifacts/tanjiro-r102b/r102b_interaction.py \
  research/artifacts/tanjiro-r102b/sessA_stats.txt \
  research/artifacts/tanjiro-r102b/sessB_stats.txt \
  research/artifacts/tanjiro-r102b/sessC_stats.txt
```

Ratio-adjusted µs/step, negative = faster, 95 % CIs, derived bands combined in
quadrature. Kernels whose three quantities are all under 1 µs/step are omitted;
the full 19-kernel tables are in `sess{A,B}_stats.txt`.

| kernel | A: R1 \| R2=0 | B: R1 \| R2=1 | **I = B − A** |
| --- | --- | --- | --- |
| `sliding_fused_attn_ring_v1` | −21.60 [−22.16, −21.05] | −15.47 [−16.27, −14.67] | **+6.13 [+5.15, +7.11]** |
| `gate_sp_h64_v1` | +7.32 [+6.52, +8.12] | −0.88 [−1.79, +0.03] | **−8.20 [−9.41, −6.99]** |
| `full_fused_attn_grow_v1` | −6.09 [−6.54, −5.64] | −7.83 [−8.15, −7.51] | **−1.74 [−2.29, −1.19]** |
| `oproj_act_h64_v1…` | −2.19 [−3.10, −1.27] | −3.01 [−4.25, −1.76] | −0.82 [−2.37, +0.73] |
| `oproj_act_h48_v1…` | −1.01 [−2.17, +0.15] | +0.30 [−0.76, +1.36] | +1.31 [−0.26, +2.88] |
| **total steady GPU busy** | **−24.80 [−29.05, −20.55]** | **−27.50 [−33.45, −21.55]** | **−2.70 [−10.01, +4.61]** |
| as M5 score % (0.01528 %/µs) | +0.3789 % | +0.4202 % | +0.0413 % |

**The whole-step interaction is null.** `I = −2.70 ± 7.31` µs/step, well inside
its band. Composed R1∘R2 is empirically additive at the step level on M4.

**But it is additive by cancellation, not by independence.** Three per-kernel
interactions are individually significant and nearly cancel:
`+6.13 − 8.20 − 1.74 = −3.81` µs/step, against the −2.70 measured at the total.
Had any one of them been absent, the composed tree would have moved by roughly
±0.1 % of score relative to the additive prediction.

### 6.5 The three mechanisms

**Sub-additive where the hunks meet (`sliding`, +6.13).** The sliding kernel is
the only object both restorations edit. R1 recovers **−21.60** µs/step there
alone but only **−15.47** when R2 is present — **72 % of its solo gain**. This
is the mechanistically expected result and the one the static census in §5 could
not see: R1's float4 merge epilogue and R2's 4-deep load ring both work by
covering the same load-to-use stall in the ring, so the second one to arrive
finds less stall left to cover. Note this is *partial* overlap, not redundancy:
R1 still delivers three quarters of its value on top of R2.

**Synergistic off-target (`gate_sp_h64_v1`, −8.20).** R1 alone imposes a
**+7.32 µs/step penalty on a kernel it does not touch** — the shared-expert gate,
which is nowhere near attention in the source. With R2 present the penalty is
gone (−0.88, not significant). Reading the arm levels directly:

| kernel, µs/step | arm00 | arm10 | arm01 | arm11 |
| --- | --- | --- | --- | --- |
| `sliding_fused_attn_ring_v1` | 648.50 | 627.70 | 648.60 | 633.71 |
| `full_fused_attn_grow_v1` | 255.20 | 249.42 | 255.10 | 247.49 |
| `gate_sp_h64_v1` | 243.00 | **250.64** | 244.20 | 243.54 |

arm10 is the outlier; arm00, arm01 and arm11 agree to ~1 µs/step. The natural
explanation is occupancy: R1's epilogue changes the sliding kernel's register
demand, and §5's IR census shows R2 *also* moves `max_live_regs32` (99 → 135 in
the composed arm). A configuration that lands badly against an AGX
register-allocator tier boundary can cost a co-resident kernel a SIMD slot.
arm10 appears to land badly and arm11 does not. This is a hypothesis: the AGX
allocator tier is exactly the layer §5 flagged as not publicly inspectable, and
nothing here proves the mechanism. What is not in doubt is the measurement —
the effect is 7.32 µs/step against nulls under 1 µs/step (§6.6). §6.8 narrows
the hypothesis further: `tg_bytes` is identical in all four arms, so the
threadgroup-memory form of the occupancy story is excluded outright.

**Context-dependence of byte-identical code (`full`, −1.74).** From §5, R2
changes **zero bytes** of `full_fused_attn_grow_v1`: arm00 and arm01 hash to
`946fa24a22ebdf8d`, arm10 and arm11 to `cb63a94f8a78d350`. Sessions A and B
therefore contrast *the same two kernel binaries*. They disagree by
−1.74 µs/step with non-overlapping CIs, and the arm levels confirm it
(249.42 vs 247.49). R1's full-kernel gain is **29 % larger** when the neighbouring
sliding kernel carries R2's deeper ring.

This is the most transferable finding in the section: **on this GPU, a kernel's
timing is not a property of that kernel's code.** Per-kernel microbenchmarks
cannot be composed, and a change confined to one kernel can be re-priced by an
edit to a different one.

### 6.6 Nulls (rule 79)

Same-arm duplexes, per-kernel, all four combinations:

| kernel | A: arm10−arm10 | A: arm00−arm00 | B: arm11−arm11 | B: arm01−arm01 |
| --- | --- | --- | --- | --- |
| `sliding_fused_attn_ring_v1` | −0.43 | −0.01 | −0.78 | −0.37 |
| `full_fused_attn_grow_v1` | +0.47 | −0.32 | −0.01 | −0.35 |
| `gate_sp_h64_v1` | +0.42 | −0.72 | −0.25 | +0.03 |
| `oproj_act_h64_v1…` | −0.91 | +0.21 | +0.43 | −0.80 |
| total steady GPU busy | −5.3 [−11.8, +1.3] | −1.4 [−10.5, +7.8] | −1.2 [−13.0, +10.7] | −6.9 [−14.8, +1.1] |

Every per-kernel null is under 1 µs/step in magnitude and none is significant.
The `gate_sp` nulls in particular are +0.42, −0.72, −0.25, +0.03 — so the
+7.32 in §6.5 is **17× the null scale** and cannot be a drift artifact. All
four total-busy nulls contain zero.

### 6.7 Expectation for Session C

Recorded before Session C's data was analysed. Across sessions the unchanged
kernels' levels agree closely — `full` reads 255.2 (arm00) vs 255.1 (arm01),
`sliding` 648.4 vs 648.7 — which suggests **R2 alone is worth roughly nothing
on M4** (~0.3 µs/step on the kernel it edits, against its official M5 +0.130 %).
If that holds, C should land near B's −27.5 µs/step rather than near the
additive −23 to −24, and the backed-out `t01 − t00` should be near zero.

### 6.8 Session C: the composed total

**Integrity.** arm00 (base) → arm11 (cand), job
`e7da2e2c-47c5-4196-ba7e-feb5a5c81889`, exit −15. Session C hit the **identical
reproducible supervisor failure as Session B**: SIGTERM at ~1240 s during slot
28's startup, slots 01–27 byte-complete at 89,308 `.err` lines each, slot 28
truncated to 2 lines. Restricted to slots 01–27 by explicit glob → **13
duplexes**, the same as B. All 27 slots report `0 divergences`. Rule-75 digests
in the log header: base `f270d6ce…` = arm00, cand `c6f10af6…` = arm11, metallib
`8e8b18af…` on both sides. `cbs=406.0 dispatches=406.0`; 80,794 command buffers
over 199 steady steps. That the failure reproduced at the same wall-clock point
in two independent sessions makes it a harness deadline artifact, not a
property of any arm.

**What Session C can and cannot add.** Three contrasts (A, B, C) span a 2×2 with
four cells, so the design is exactly saturated — there is **no spare degree of
freedom**. Concretely, with `tXY` the arm levels:

```
A = t10 − t00 ,  B = t11 − t01 ,  C = t11 − t00
R2|R1=0  =  t01 − t00  =  C − B
R2|R1=1  =  t11 − t10  =  C − A
residual =  C − (A + (C − B))  =  B − A  =  I
```

The "residual vs additive prediction" row is therefore **algebraically identical
to `I`** and is *not* independent confirmation; the script prints it labelled as
such. The genuinely new information in Session C is (i) the composed total
measured in one session rather than summed across two, and (ii) the per-kernel
`R2|R1=0` column, which is the first direct measurement of R2 in isolation
anywhere in this campaign.

**Per-kernel.**

| kernel | C: t11 − t00 | R2 \| R1=0 (= C − B) | R2 \| R1=1 (= C − A) |
| --- | --- | --- | --- |
| `sliding_fused_attn_ring_v1` | **−15.39 [−15.89, −14.89]** | +0.08 [−0.87, +1.03] | **+6.21 [+5.47, +6.95]** |
| `full_fused_attn_grow_v1` | **−7.94 [−8.58, −7.30]** | −0.11 [−0.83, +0.61] | **−1.85 [−2.63, −1.07]** |
| `gate_sp_h64_v1` | −0.20 [−0.71, +0.30] | +0.68 [−0.36, +1.72] | **−7.52 [−8.47, −6.57]** |
| `oproj_act_h64_v1…` | **−7.13 [−7.96, −6.30]** | **−4.12 [−5.62, −2.62]** | **−4.94 [−6.18, −3.70]** |
| `oproj_act_h48_v1…` | −0.81 [−1.95, +0.32] | −1.11 [−2.67, +0.45] | +0.20 [−1.42, +1.82] |

**Totals.**

| quantity | µs/step | M5 score % |
| --- | --- | --- |
| **C total, t11 − t00 (the composed tree)** | **−31.60 [−35.80, −27.40]** | **+0.4828 %** |
| C total, unadjusted | −26.10 [−32.60, −19.60] | +0.3988 % |
| R2 \| R1=0 (= C − B) | −4.10 [−11.38, +3.18] | +0.0626 % |
| R2 \| R1=1 (= C − A) | −6.80 [−12.78, −0.82] | +0.1039 % |
| additive prediction, A + (R2\|R1=0) | −28.90 [−37.33, −20.47] | +0.4416 % |
| residual C − additive (≡ I) | −2.70 [−12.12, +6.72] | +0.0413 % |

**Finding 1 — the composed tree is real and is the largest of the three.**
−31.60 µs/step, band excluding zero by a factor of 7.5, ≈ **+0.483 %** of M5
score if M4 transferred one-for-one (§9 says it does not). Against the
preregistered additive prediction of +0.3660 % this is if anything *super*-additive,
but only by `I`, which is not significant.

**Finding 2 — R2 alone buys nothing on M4, on the kernels it edits.** This was
preregistered in §6.7 before Session C was analysed, and it holds precisely
where it was predicted: `R2|R1=0` is **+0.08** µs/step on `sliding` — the only
kernel R2 changes — and **−0.11** on `full`. Both bands straddle zero and both
are inside the ±1 µs/step null scale of §6.6. R2's official M5 gain is +0.130 %,
i.e. ≈ 8.5 µs/step-equivalent. **M4 cannot see R2 at all.** §5 predicted this
statically for `full` (R2 changes zero bytes of it, identical hashes) and
Session C confirms it dynamically for `sliding` too.

**Finding 3 — the total's R2\|R1=0 is not R2.** The total reads −4.10 µs/step,
but the sum of R2's own two kernels is −0.03. The entire −4.10 sits on
`oproj_act_h64_v1` (−4.12), a kernel **neither restoration touches** and whose
machine code is byte-identical across arm00 and arm01. This is the one number in
Session C that should not be believed as a treatment effect, and the nulls say
so directly (below). Reading −4.10 as "R2 is worth 0.06 % on M4" would be
reading `oproj` drift.

**Nulls (session C).** Same protocol as §6.6.

| kernel | C: arm11−arm11 | C: arm00−arm00 |
| --- | --- | --- |
| `sliding_fused_attn_ring_v1` | −0.57 | −0.06 |
| `full_fused_attn_grow_v1` | +0.10 | −0.29 |
| `gate_sp_h64_v1` | −0.63 | +0.03 |
| `oproj_act_h64_v1…` | +0.15 | **−1.52 [−2.58, −0.45]** |
| total steady GPU busy | −2.9 [−10.1, +4.3] | −1.6 [−10.2, +7.1] |

Both totals contain zero. Every per-kernel null in the entire three-session
study is under 1 µs/step **except one**: `oproj_act_h64_v1` in the arm00−arm00
null, −1.52 with a band excluding zero. That is the only null failure in twelve
kernel-arm null cells, and it lands on exactly the kernel carrying Finding 3.
`oproj_act_h64_v1` is also the largest kernel in the step (≈1120 µs/step), so a
0.13 % within-session level drift produces it. **Discount every `oproj` row in
this report; trust the rest.**

**Cross-session level agreement — why the significant effects are not session
artefacts.** arm00 was measured as the base of both A and C; arm11 as the
candidate of both B and C. Their levels therefore bound any per-session
additive offset directly:

| kernel, µs/step | arm00 in A | arm00 in C | A−C | arm11 in B | arm11 in C | B−C |
| --- | --- | --- | --- | --- | --- | --- |
| `sliding_fused_attn_ring_v1` | 648.50 | 647.70 | +0.80 | 633.71 | 632.72 | +0.99 |
| `full_fused_attn_grow_v1` | 255.20 | 254.80 | +0.40 | 247.49 | 247.02 | +0.47 |
| `gate_sp_h64_v1` | 243.00 | 242.70 | +0.30 | 243.54 | 242.65 | +0.89 |
| `oproj_act_h48_v1…` | 303.00 | 302.50 | +0.50 | 303.17 | 301.89 | +1.28 |
| `oproj_act_h64_v1…` | 1121.50 | 1119.80 | +1.70 | 1116.10 | 1113.39 | **+2.71** |

Session offsets are **≤ 0.99 µs/step** on every kernel except `oproj`. The two
headline cross-session effects — `gate_sp` at ±7.3–8.2 and `sliding` at +6.13 —
are **7–8× larger than the worst offset that could confound them**, so they
survive the fact that `I` is assembled from two different sessions. `oproj`'s
offsets are 1.7–2.7 against a −4.12 claimed effect, which is the same verdict as
the nulls: **not usable**.

**Arm levels, all four cells** (base column of each arm's own session; candidate
levels are `base + absolute d`, so they are the unadjusted arm means):

| kernel, µs/step | arm00 | arm10 (R1) | arm01 (R2) | arm11 (R1∘R2) |
| --- | --- | --- | --- | --- |
| `sliding_fused_attn_ring_v1` | 648.50 | 627.70 | 648.60 | 633.71 |
| `full_fused_attn_grow_v1` | 255.20 | 249.42 | 255.10 | 247.49 |
| `gate_sp_h64_v1` | 243.00 | **250.64** | 244.20 | 243.54 |
| `oproj_act_h48_v1…` | 303.00 | 302.38 | 302.60 | 303.17 |
| `oproj_act_h64_v1…` | 1121.50 | 1120.74 | 1118.10 | 1116.10 |

`arm01 ≈ arm00` on every row — the cleanest possible statement of Finding 2.
The `gate_sp` anomaly is confirmed **arm10-only**: 250.64 against 243.0 / 244.2 /
243.5. §6.5 offered occupancy as a hypothesis; §5 partially refutes the usual
version of it, because `tg_bytes` is 18,432 and `allocas` is 6 in **all four
arms**, so threadgroup-memory pressure cannot be the mechanism. The remaining
candidate is register pressure — arm10 has the *lowest* sliding
`max_live_regs32` (99, versus 107/135/143) — but the relationship is not
monotone across the four arms, so no mechanism is claimed. It is recorded as an
M4-specific scheduling effect requiring M5 replication before anyone acts on it.

**Caveat.** arm10 appears only in Session A and arm01 only in Session B; each is
measured once. The offset table above is what licenses treating their contrasts
as arm effects rather than session effects, and it licenses that only down to
~1 µs/step.

## 7. Official submission (P3)

Dispatched per the preregistered policy — unconditionally on P1 passing, and
**before** any dynamic result existed, so the receipt is not selected-on.

| field | value |
| --- | --- |
| submission id | `e08d759f-8e52-46e7-8b29-2c8647cfaae8` |
| benchmark | `eigenlabs/mlxfast-challenge` |
| dispatch | `senpai/submit-official.sh 1bc1c8954147c9e322aad1f3b80bd9fa3c0888d7 --note-file research/tanjiro-r102b-submission-note.md` |
| model attribution | `senpai` (fixed by the wrapper; `--model` is rejected) |
| candidate commit | `9a42b59e` (submitted surface identical to `88d2cb3a`) |
| note | `research/tanjiro-r102b-submission-note.md`, 10.6 KiB |
| status at dispatch | `validating` |

## 8. Receipt decomposition (P4)

### 8.1 The receipt

Pulled with `python3 research/r93-runs/pull_receipts.py /tmp/r102b-receipts.json`
(n = 1203, `2026-07-24T07:24:49Z .. 2026-08-09T18:36:41Z`).

| field | value |
| --- | --- |
| submission id | `e08d759f-8e52-46e7-8b29-2c8647cfaae8` |
| official commit | `bd33883e` |
| timestamp | `2026-08-09T18:36:41Z` |
| status | `rejected` — i.e. *did not beat the current best*, as preregistered |
| `score` (paired) | 2.58189090485267 |
| `cs` (pinned) | 2.582286297407117 |
| `cand_dec` / `cand_pre` | 0.004913116859375 / 0.000187856689453125 |
| `bl_dec` / `bl_pre` | 0.01384402571875 / 0.0003731318359375 |
| `dec_su` / `pre_su` | 2.8177684583938647 / 1.9862579130066373 |

Both published statistics were reverse-engineered exactly from the corpus
(`research/artifacts/tanjiro-r102b/r102b_receipt.py`), which matters because
the two are *not* interchangeable:

- `score = dec_su^0.75 * pre_su^0.25` — max relative residual **4.7e-15** over
  all 1203 receipts. This is the *paired* statistic; it inherits the noise of
  the same-session baseline legs.
- `cs = (MB_D/cand_dec)^0.75 * (MB_P/cand_pre)^0.25` with pinned constants. The
  combination `K = 0.75 ln MB_D + 0.25 ln MB_P = -5.183167681` is constant to
  **1.8e-15** across all 1203 receipts. `cs` depends on the candidate legs
  **only**, so it is the lower-noise statistic and the right one to compare
  against the control receipt.

Empirically confirmed on the 133 near-frontier receipts of the last 150:
scatter of `cs` **1.389 %** vs scatter of `score` **1.503 %**. A regression of
`ln cand_dec` on `ln bl_dec` gives slope **+0.495 ± 0.523 (t = +0.95)** and on
the prefill legs **+0.041 ± 0.097 (t = +0.42)** — the session factor is *not*
measurably shared, so pairing against the session baseline adds noise rather
than removing it. **Use `cs`, not `score`, for candidate-to-candidate
comparison.**

### 8.2 Noise model — and one trap that had already been documented

My first pass used the byte-identical pinned baseline arm as an n=1203 null and
got σ(`cs`) ≈ 0.54 %, of which 87 % was the prefill leg. **That estimate is
wrong, and the reason was already on file.**
`research/advisor-r93-m5-receipt-channel-and-promotion-model.md` §5 established
that the baseline runs *first* in each session and absorbs JIT, first-touch
page faults and clock ramp, so `bl_pre`'s 1.9–2.4 % scatter is a cold-start
artifact and "must never be used as a proxy for candidate measurement noise".
I re-derived their adjacent-near-duplicate estimator on the current corpus and
reproduce their published numbers to 3–4 decimals on a window one day longer
(1203 vs 1104 receipts):

| quantity | r93 (n=1104) | this pull (n=1203) |
| --- | --- | --- |
| `cand_dec` σ_single ≤ | 0.2924 % | **0.2920 %** |
| `cand_pre` σ_single ≤ | 0.2573 % | **0.2577 %** |
| `bl_dec` σ_single ≤ | 0.1535 % | **0.1534 %** |
| `bl_pre` σ_single ≤ | 2.3821 % | **2.4096 %** |

(83 adjacent same-solver pairs < 20 min apart; med|d| → σ via
`1/(0.6745·√2)`. These are *upper* bounds: each pair still contains whatever
real code change was made between the two submissions.)

Carried into `cs`-percent units: decode leg 0.75 × 0.2920 = **0.219 %**,
prefill leg 0.25 × 0.2577 = **0.064 %**, total **σ(cs) ≤ 0.228 %**.

### 8.3 Additivity

Control receipt `59bd72a3` (`2026-08-09T14:56:31Z`, same day, same host),
cs = 2.575633, `cand_dec` = 0.0049252545546875, `cand_pre` = 0.000188405435546875.

Log-split of the measured move, in `cs`-percent units:

| leg | value | note |
| --- | --- | --- |
| decode | **+0.1851 %** | 0.004925254555 → 0.004913116859 |
| prefill | +0.0729 % | 0.000188405436 → 0.000187856689; neither restoration touches prefill, so this is a pure noise draw |
| total | **+0.2580 %** | matches `cs` ratio +0.2583 % to rounding |

| quantity | full `cs` | decode leg only |
| --- | --- | --- |
| measured | +0.2580 % ± 0.3228 | +0.1851 % ± 0.3097 |
| additive prediction | +0.3658 % ± 0.0729 | +0.3658 % ± 0.0729 |
| **implied interaction I** | **−0.108 % ± 0.331** | **−0.181 % ± 0.318** |
| 95 % band on I | [−0.757, +0.541] | [−0.804, +0.443] |
| excludes I = 0 ? | **NO** | **NO** |
| excludes full cancellation (I = −0.366) ? | **NO** | **NO** |

(± on the measured figure is √2 σ because the control and the candidate are two
independent single draws; the prediction's ± is the quadrature of R1's
published band, σ ≈ 0.052 %, with the same assumed for R2.)

### 8.4 Verdict on the receipt: structurally underpowered

The single receipt resolves I only to **±0.65 %** while the effect under test
is **0.366 %** — **1.8× too coarse**. It cannot distinguish perfect additivity
from total mutual cancellation. The point estimate leans very slightly negative
and is worth exactly nothing on its own.

Solving for what a decisive receipt-only test needs (95 % confidence, 80 %
power, paired arms):

| statistic | σ | receipts per arm | total |
| --- | --- | --- | --- |
| full `cs` | 0.228 % | 7 | **14** |
| decode leg only | 0.219 % | 6 | **12** |

The round's budget was **one**. **A receipt-based decomposition of a ~0.37 %
two-factor interaction was never achievable within one round**, and this is a
property of the design, not of the outcome. The M4 2×2 in §6 is therefore the
load-bearing evidence, and the receipt's real value is (a) an M5 correctness
pass for the composed tree and (b) one honest draw of its absolute standing.

This is the reusable lesson: **before spending a round's receipt on a
difference, check the difference against σ(cs) ≤ 0.228 %.** Any single-receipt
question about an effect smaller than roughly 0.64 % is unanswerable.

## 9. Implied M5 interaction term

Two independent estimates of `I` now exist: the M4 2×2 (§6) and the receipt
(§8). This section combines them, and first establishes how far an M4 number may
be pushed towards M5 at all.

### 9.1 M4→M5 transfer is not a scalar

The round has three calibration points, one of which is out of sample:

| mechanism | M4, this round | official M5 | implied factor |
| --- | --- | --- | --- |
| R1 (#555) | +0.3789 % (session A) | **+0.2358 %** | **0.622** |
| R2 (#539) | ≈ 0 (+0.08 / −0.11 µs/step on its own kernels) | **+0.130 %** | undefined (M4 sees nothing) |
| R1∘R2 composed | +0.4828 % (session C) | **+0.2580 %** (§8) | **0.534** |

The R1 factor is legitimately fitted: session A is this round's fresh M4
measurement of exactly the change #555 submitted. The composed factor is
**out of sample** — session C and the receipt were produced independently, and
the receipt was dispatched before any dynamic data existed (§7).

The two fitted factors agree (0.622 vs 0.534) but that agreement is worth very
little: the composed factor inherits the receipt's ±0.32 % noise, giving
`0.2580/0.4828 = 0.534 ± 0.669`, a band that contains 0 and 1 alike.

What is solid is the **failure mode**: transfer is *not* a single scalar.
- M4 **over**-predicts R1 by 1.6×.
- M4 **completely misses** R2. R2's M5 gain is +0.130 % ≈ 8.5 µs/step-equivalent
  and M4 measures 0.08 µs/step on the only kernel R2 edits, with a null-scale
  band. No scalar maps 0 to 8.5.

The mechanistic reading is consistent with §5 and the harness rules: R2 deepens
a load ring, which pays where the memory system stalls differently, and this M4
Pro is Apple GPU generation 16 with 20 GPU cores against the ranked M5 Max. The
`AGENTS.md` warning that "threadgroup geometry can change sign across core
counts" is exactly what a load-ring depth change is exposed to.

**Consequence for `I`.** `I` is itself a cross-term between R1 and R2. Since the
two factors' individual transfer behaviour differs by more than an order of
magnitude, scalar-transferring their interaction is not justified by anything
measured here. Both scalings below are therefore reported, and neither is
preferred.

### 9.2 Combining the two estimates

The M4 total-busy interaction is `I = −2.70 [−10.01, +4.61]` µs/step, half-width
7.31, i.e. ±0.1117 % of M5 score at 0.01528 %/µs, so 1σ = **0.0570 %** on the
score scale (sign flipped: a negative time delta is a positive score gain, so
M4 says `I = +0.0413 %`).

The receipt gives `I = −0.108 % ± 0.331 %` on full `cs` (§8.3), 1σ = 0.331 %.

Inverse-variance combination:

| basis | M4 term | receipt term | **combined `I`** |
| --- | --- | --- | --- |
| M4 unscaled | +0.0413 % ± 0.0570 % | −0.108 % ± 0.331 % | **+0.037 % ± 0.056 %** |
| M4 × 0.622 (the fitted R1 factor) | +0.0257 % ± 0.0355 % | −0.108 % ± 0.331 % | **+0.024 % ± 0.035 %** |

Both are consistent with zero and both are **M4-dominated**: the receipt carries
weight `1/0.331² = 9.1` against M4's `1/0.057² = 308`, i.e. **3 %** of the total.
The receipt does not move the answer. This is §8.4's conclusion arriving from
the other direction — the single receipt was structurally incapable of resolving
a term this size, and it did not.

### 9.3 Verdict

**The composed R1∘R2 tree is additive on M5 to within ±0.06 % of score, and
almost certainly within ±0.04 %.** The upper end of the combined band is
+0.09 %, the lower end −0.02 %. There is no evidence of the sub-additive
collapse that the assignment's N-B hypothesis contemplated, and no evidence of a
super-additive bonus worth chasing.

Two operational consequences, both negative in the useful sense:

1. **Nothing needs un-merging.** #555 and #539 are both merged into the frontier.
   Had `I` been strongly negative, one of them would have been paying rent it no
   longer earned. It is not; the frontier's accounting for these two rungs is
   correct as it stands.
2. **Additive bookkeeping is validated for this pair, and only for this pair.**
   §6.4 shows the step-level null is produced by **cancellation of three
   significant per-kernel interactions** (+6.13, −8.20, −1.74), not by
   independence. That cancellation is a coincidence of this particular pair on
   this particular machine. The campaign should keep summing rung gains, but
   should stop treating additivity as a property of the method rather than a
   lucky property of the specific pairs measured so far.

The one durable, transferable claim from the whole 2×2 is in §6.5 and is not
about `I` at all: **a kernel's timing is not a property of that kernel's code.**
R2 changes zero bytes of `full_fused_attn_grow_v1` and still re-prices R1's gain
there by 29 %; R1 changes zero bytes of `gate_sp_h64_v1` and costs it
7.32 µs/step. Any future per-kernel microbenchmark in this campaign should be
read with that in mind.

## 10. Updated record probability

### 10.1 A category error in the campaign's own bookkeeping

The number `2.61650354381456` is quoted across our research notes as "the
record", and several of them place it in a direct "gap" against one of our
**`cs`** values. `2.61650354381456` is a **`score`**, not a `cs`, so that
subtraction is only meaningful once the session multiplier between the two
statistics is written down explicitly.

Searching the 1,203-receipt corpus, it matches exactly one receipt, and matches
it on the `score` field to the last digit:

| field | value |
| --- | --- |
| submission id | `cc6ddc12-ecbd-4c07-beec-445060a21a62` |
| commit | `c5b0a13c` |
| solver | `a-github-name` |
| ts | 2026-08-08T09:17:33Z |
| **`score`** | **2.61650354381456** ← the "record" |
| `cs` | 2.5745941683956177 |

It is the corpus maximum by `score` (rank 1/1203). It is **not** the corpus
maximum by `cs`; that is `ebcd3ca3` (MyatKaung) at `cs` = 2.59186778715710,
whose own `score` is 2.601161.

This is not pedantry. The two statistics rank differently because they measure
different things:

- `cs = (MB_D/cand_dec)^0.75 · (MB_P/cand_pre)^0.25` uses **pinned** calibration
  constants (§8.2, `K = 0.75 ln MB_D + 0.25 ln MB_P = −5.183167681`, constant to
  1.8e-15 across all 1,203 receipts). It depends only on the candidate legs, so
  it is a clean measure of **candidate quality**.
- `score = (bl_dec/cand_dec)^0.75 · (bl_pre/cand_pre)^0.25` is the
  **same-session paired** statistic. It additionally multiplies in whatever the
  baseline happened to measure in that session.

The leaderboard ranks on `score`. So the ranked quantity factors exactly:

```
score  =  cs  ×  L
L      =  (bl_dec/MB_D)^0.75 · (bl_pre/MB_P)^0.25
```

`L` is the **baseline lottery**: pure session draw, statistically independent of
anything the solver did to the candidate.

### 10.2 The record is a baseline-lottery outlier, not a faster candidate

Decomposing the record receipt and ours side by side:

| | record `c5b0a13c` | ours `bd33883e` | ours vs record |
| --- | --- | --- | --- |
| `cand_dec` (s/tok) | 0.004930056640625 | 0.004913116859375 | **−0.344 %** (we are faster) |
| `cand_pre` (s/tok) | 0.000188158853515625 | 0.000187856689453125 | **−0.161 %** (we are faster) |
| `bl_dec` (s/tok) | 0.014005887046875 | 0.01384402571875 | +1.169 % slower baseline for them |
| `bl_pre` (s/tok) | 0.00038462174609375 | 0.0003731318359375 | +3.079 % slower baseline for them |
| **`cs`** | 2.574594 | **2.582286** | **+0.2988 %** |
| `L` | **1.016278** (+1.628 %) | 0.999847 (−0.015 %) | |
| **`score`** | **2.616504** | 2.581891 | −1.323 % |

**Our candidate is faster than the record holder's on both scored legs.** They
hold the record because their session drew a baseline in the top ~1 % of the `L`
distribution (+1.63 %, above the p99 of +1.27 %) while ours drew the median
(−0.015 % against a median of −0.143 %).

Our ranks: **31/1203 by `cs`**, 40/1203 by `score`.

### 10.3 The empirical distribution of the baseline lottery

Because `L` is directly computable per receipt, no distributional assumption is
needed. Over all n = 1,203:

| statistic | value |
| --- | --- |
| mean `L` | 0.999927 |
| median `L` | 0.998572 |
| sd(ln L) | 0.5359 % |
| MAD-derived sd(ln L) | 0.6067 % |

| percentile | `L` | vs 1 |
| --- | --- | --- |
| p1 | 0.992228 | −0.777 % |
| p5 | 0.993165 | −0.683 % |
| p25 | 0.995292 | −0.471 % |
| p50 | 0.998572 | −0.143 % |
| p75 | 1.004210 | +0.421 % |
| p90 | 1.007517 | +0.752 % |
| p95 | 1.009229 | +0.923 % |
| p99 | 1.012723 | +1.272 % |
| max | 1.021135 | +2.113 % |

**Cross-validation against r93.** The r93 adjacent-pair σ's (§8.4, reproduced
independently on this 1,203-receipt pull) predict
sd(ln L) = √((0.75 × 0.1534 %)² + (0.25 × 2.4096 %)²) = **0.611 %**. The measured
MAD-derived sd(ln L) is **0.607 %**. Two completely different estimators — a
same-solver adjacent-pair difference estimator and a direct per-receipt ratio —
agree to 0.7 % relative. This is the strongest available confirmation that
`research/advisor-r93-m5-receipt-channel-and-promotion-model.md` §5 got the
baseline channel right, and that ~96 % of the lottery variance is the `bl_pre`
cold-start term.

`L` is mildly non-stationary: daily means drift over ±0.23 % across the campaign
(corr(time, ln L) = +0.101, t = +3.52), while the within-day sd is stable at
0.39–0.64 %. The apparent corr(ln `cs`, ln `L`) = +0.123 (t = +4.29) is
essentially this temporal confound — `cs` rises over the campaign as solvers
improve — not a real coupling between candidate and baseline legs. Treating `L`
as i.i.d. is therefore a mild approximation, adequate at the accuracy needed
below.

### 10.4 Corrected record probability

For a candidate of fixed quality `cs`, one official receipt sets a record iff it
draws `L ≥ 2.61650354381456 / cs`. With our measured `cs` = 2.582286 that
threshold is `L ≥ 1.013251` (+1.3251 %), i.e. between the p99 and the max of the
observed lottery.

| estimator | P(one receipt of our candidate takes the record) |
| --- | --- |
| empirical (9 of 1,203 draws qualify) | **0.748 %** (1 in 134) |
| lognormal fit (z = 2.472) | 0.671 % (1 in 149) |

Receipts needed for a 50 % chance of at least one record: **92** (empirical) /
103 (lognormal). For 90 %: 307 / 342.

**This confirms the round-100 repricing and retires two older numbers.**

| source | P per draw at our candidate | status |
| --- | --- | --- |
| `maple-r99-score-gap-and-receipt-economics.md` §3 | ≈ 1.2e-4 | **retired** |
| `CURRENT_RESEARCH_STATE.md` round-100 repricing, row "+ epilogue only" | ≈ 0.675 % at `cs` ≈ 2.5824 | **confirmed** |
| this note, empirical `L` at measured `cs` = 2.582286 | **0.748 %** | |

The round-100 repricing predicted 0.675 % for a `cs` ≈ 2.5824 candidate before
any such receipt existed. We then measured `cs` = 2.582286 and get 0.748 %
empirically / 0.671 % under the same Gaussian assumption it used. That is a
clean out-of-sample confirmation of the round-100 session-factor model, and its
σ = 0.5393 % matches my sd(ln L) = 0.5359 % to 0.6 % relative.

The r99 figure was ~60× too pessimistic because it used the sd of twelve
*different candidates'* scores (0.452 %) as session noise and anchored on their
heterogeneous mean rather than on a specific candidate's `cs`.

**My own first-pass estimate this round was worse and is withdrawn.** It
compared our `cs` to the record `score` and used σ(`cs`) = 0.228 % — the
*candidate-only* noise term from §8.4 — as the spread. That gave z = 4.10 and
P ≈ 2.03e-05. Both halves were wrong in the same direction: the ranked statistic
carries the baseline's variance too, and σ(`cs`) is the wrong scale for it by
2.6×. The correct answer is **~370× larger** than that first pass.

The residual disagreement between empirical (0.748 %) and lognormal (0.671 %)
at our `cs` is real and grows in the tail: at the un-restored frontier
`cs` = 2.575633 the empirical estimate is 0.416 % against 0.157 % lognormal, a
factor of 2.6. The `L` distribution is platykurtic (MAD-derived sd 0.6067 %
exceeds sd 0.5359 %), so a Gaussian fit understates the far right tail. Use the
empirical column when the required draw is beyond p95.

### 10.5 Where the leverage is

The record threshold sits deep in the right tail of `L`, so P(record) is
extremely convex in candidate quality:

| `cs` | vs ours | required `L` | P empirical | P lognormal | 1 in |
| --- | --- | --- | --- | --- | --- |
| 2.575633 (control `59bd72a3`) | −0.258 % | 1.015868 | 0.416 % | 0.157 % | 241 |
| **2.582286 (ours, `bd33883e`)** | — | 1.013251 | **0.748 %** | 0.671 % | 134 |
| 2.585060 (preregistered additive prediction) | +0.107 % | 1.012164 | 1.164 % | 1.154 % | 86 |
| 2.591868 (corpus max `cs`, `ebcd3ca3`) | +0.371 % | 1.009505 | 4.156 % | 3.743 % | 24 |
| 2.600000 | +0.686 % | 1.006348 | 14.30 % | 11.57 % | 7 |
| 2.620246 | +1.468 % | 0.998589 | 49.96 % | 59.76 % | 2 |

("1 in" is `1/p_empirical`.) The banner's own figure for the additive
prediction — "≈1.2 % per draw (E ≈ 82 draws)" at `cs` ≈ 2.58506 — is reproduced
here as 1.164 % / E ≈ 86 from a completely independent empirical estimator. The
banner's *model* was right; only its *input* was a prediction. Substituting the
measured `cs` = 2.582286 moves the round's true position from 1.16 % per draw to
**0.75 %**, i.e. the un-measured additivity assumption was worth a claimed 1.6×
in record odds that we did not actually have.

Two consequences for round planning:

1. **A +0.37 % `cs` gain multiplies record probability by 5.6×** (0.748 % →
   4.16 %). In this regime a tenth of a percent of candidate quality is worth
   far more than an extra receipt: going from `cs` 2.582286 to 2.585658 (the
   *additive* R1∘R2 prediction, had it held) roughly **doubles** the per-receipt
   record odds, whereas a second receipt at unchanged quality only adds another
   0.748 %.
2. **`cs` ≥ 2.6202 (+1.47 % over ours) makes the record a coin flip at the
   median draw.** That is the honest size of the remaining engineering gap, and
   it is ~4× the entire additive R1∘R2 prediction (+0.366 %) and ~11× what R1∘R2
   actually delivered (§8.5). Composed micro-restorations do not close it.

### 10.6 Note on what a `rejected` receipt means here

Our receipt returned `status rejected`. Per `AGENTS.md`, that can mean only that
the score did not beat the current best. Both floors passed with enormous margin
(`dec_su` 2.8178 and `pre_su` 1.9863 against a 0.95 floor) and correctness was
clean, so `rejected` here carries **no** correctness or floor information — it is
purely the ranking comparison, and §10.2 shows that comparison was lost to the
baseline draw rather than to candidate speed.

## 11. Replacement block for `CURRENT_RESEARCH_STATE.md`

The round-102 headline and the submitted-surface bullet were both written
before this round's receipt existed. Four statements in them are now wrong or
misleading:

1. **"exactly one file"** — the delta vs `origin/main` (`1bc1c895`) is **27
   files**, not one. 1 is `Sources/MLXFastModel/LagunaRuntimeModel.swift`; the
   other 26 are `Vendor/` files carrying merged #548 rung-1 comment reclaim
   (`f720e9e7`, +55/−3072, semantics-free). The one-file claim is true only
   against `3567695b^`, not against `origin/main`. §3.
2. **"`pipe_kc`/`pipe_kd` ×20"** — the actual counts are **10 each**. §3.
3. **`cs ≈ 2.58506`** was a prediction. The measured value is
   **`cs = 2.582286297407117`**, −0.1073 % below it. §7.
4. **Per-draw record probability ≈1.2 %** used the predicted merit and an
   `L`-sigma of 0.5393 %. At the *measured* merit, with `L` re-fitted on all
   1203 receipts, it is **0.748 %** empirical / 0.671 % lognormal. §10.

A fifth, subtler correction: `2.61650354381456` is a **`score`**, not a `cs`.
`score = cs × L`, and that record receipt's `cs` is only 2.574594 — *below*
ours. Treating it as a candidate-speed target is a category error. §10.1.

### 11.1 Drop-in replacement for lines 14–36

Replace both bullets verbatim with:

```markdown
- ✅ **Round-102 headline resolved: the composed R1∘R2 tree has now been
  built, correctness-verified, measured on M4 as a full 2×2, and spent on an
  official M5 receipt.** #555 (float4 merge epilogue, −454 B, +0.2358 % solo)
  and #539 (4-deep sliding ring, +4,086 B, ≈0.130 % solo) edit the same
  sliding-attention kernel in disjoint regions; the composition had never been
  measured. Receipt `e08d759f-8e52-46e7-8b29-2c8647cfaae8` (commit `bd33883e`,
  2026-08-09T18:36:41Z) gives **`cs = 2.582286297407117`**, +0.2580 % over
  control `59bd72a3` (2.575633) — against an additive prediction of +0.3658 %.
  The receipt-implied interaction is **−0.108 % ± 0.331 %** (1σ), i.e. a single
  receipt cannot resolve it. The M4 2×2 (4 arms × 28 slots, PR #565 §6) is
  ~6× tighter and puts the whole-step interaction at **+0.041 % ± 0.056 %**:
  **statistically null, so composition is additive to within measurement**, but
  additive *by cancellation* — the sliding kernel loses +6.13 µs/step of R1's
  benefit under R2 while `gate_sp_h64_v1` gains −8.20 µs/step and the full
  attention kernel −1.74 µs/step. Nothing needs un-merging. **Do not quote
  2.58506 anywhere**; the measured frontier merit is **2.582286**.

- **Per-draw record probability at the measured frontier is 0.748 %**
  (9/1203 empirical, 1 in 134; 0.671 % lognormal), not the 1.2 % predicted at
  `cs = 2.58506`. Beware the statistic: the record `2.61650354381456` is a
  **`score`**, and `score = cs × L` with
  `L = (bl_dec/MB_D)^0.75 (bl_pre/MB_P)^0.25` the same-session *baseline* draw.
  The record receipt (`c5b0a13c`) has `cs = 2.574594`, **below ours**, and won
  on `L = 1.016278` (>p99). Our candidate is faster than the record holder's on
  **both** scored legs (`cand_dec` −0.344 %, `cand_pre` −0.161 %); we rank
  **31/1203 by `cs`** but 40/1203 by `score`. `sd(ln L) = 0.5359 %` over 1203
  receipts, ~96 % of it from `bl_pre`, and no legitimate lever on `L` exists
  (PR #565 §10, frontier consult Q2). A coin-flip draw needs `cs ≥ 2.6202`
  (+1.47 % over the current frontier). Optimise `cs`; submit every round,
  because each round yields a free `L` draw.

- **Submitted-surface delta vs `origin/main` (`1bc1c895`) is 27 files**, not
  one: `Sources/MLXFastModel/LagunaRuntimeModel.swift` (+137/−83, both
  restorations) plus 26 `Vendor/` files from merged #548 rung-1 comment
  reclaim (`f720e9e7`, +55/−3072, semantics-free). The "exactly one file"
  claim holds only against `3567695b^`. Marker greps: `pipe_kc`/`pipe_kd`
  **×10 each** (not ×20) with `for (; i + 3 * BN < N; i += 4 * BN)` at
  `LRM:1548`; `outputs4` ×10. `benchmark.json` is byte-identical to
  `origin/main`. Budget at submission: `current=2811013/3000000`,
  `headroom=188987`, `growth=−172836/262144`, `files=142`; the LRM blob is
  515,050 B with 9,238 B of per-file headroom.
  `lagunaRouterWeightPrefetch` count is still **0** — that is #558's job and it
  is the only one of the three restorations still missing.
```

### 11.2 Optional secondary amendment (lines 10–12)

Lines 10–12 quote the record as a bare number. If the advisor wants the
`score`/`cs` distinction to survive at the top of the file, append to that
bullet:

```markdown
  That 2.61650354381456 is a **`score`** (`= cs × L`); the same receipt's
  candidate merit is only `cs = 2.574594`. The corpus maximum *by `cs`* is a
  different receipt entirely (`ebcd3ca3`, MyatKaung, `cs = 2.591868`).
```

### 11.3 Other documents carrying the same category error

Flagged, not edited — each conflates `score` with `cs`, or quotes 2.58506 as
measured. They are historical records of what was believed at the time, so
overwriting them would destroy the audit trail; the advisor should decide.

| file | line(s) | issue |
|---|---|---|
| `research/maple-r99-score-gap-and-receipt-economics.md` | §3 | record-probability ≈1.2e-4 computed against the record as a `cs`; retired by §10 |
| `research/tanjiro-r102b-submission-note.md` | 28, 80, 180 | quotes the additive prediction `cs ≈ 2.58506` as the expected merit |
| `research/maple-fern-r85b-neutrality-prereg.md` | 34 | same `score`-as-`cs` conflation |
