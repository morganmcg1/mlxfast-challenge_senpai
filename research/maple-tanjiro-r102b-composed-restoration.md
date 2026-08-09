# R102-B: the composed R1∘R2 restoration tree

Student: maple-tanjiro. PR #565. Assignment
`maple-r102-b-composed-restoration-receipt`, revision `r102-b-rev1`.
Base `aba31ba9e461c8a4f7a0ba7086b417f0868fcad9`.

> **Status: in progress.** Sections 1–4 and 7 are final. Sections 5, 6, and
> 8–11 are placeholders pending the M4 dynamic 2×2 and the official receipt.

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

_Pending._

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

_Pending the receipt._

## 9. Implied M5 interaction term

_Pending._

## 10. Updated record probability

_Pending._

## 11. Replacement block for `CURRENT_RESEARCH_STATE.md`

_Pending._
