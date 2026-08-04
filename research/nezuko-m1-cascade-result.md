# PR #20 — LM-head three-level decode cascade (M1) + two deletions

<!-- SENPAI-RESULT marker is inserted at submission time, once the official
     M5 family has returned. Do not infer an unmeasured score. -->

- **Student / PR:** `maple-nezuko` / [#20](https://github.com/morganmcg1/mlxfast-challenge_senpai/pull/20)
- **`BASE_SHA`:** `aecc470edecf01cbf9cb708bdc5ad69b90c73754`
- **Candidate commits:** `6d14ed9` (deletions), `86615c5` (M1 cascade)
- **Submitted candidate files (5, all inside `editablePaths`):**
  `Sources/MLXFastModel/LagunaLmHeadPrune.swift`,
  `Sources/MLXFastModel/LagunaRuntimeModel.swift`,
  `Sources/MLXFastModel/LagunaRuntimeWeights.swift`,
  `Vendor/mlx-swift/Source/Cmlx/mlx-generated/fp_quantized_nax.cpp`,
  `Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/kernels/fp_quantized_nax.h`
- **Supporting documentation:** `research/nezuko-m1-cascade-note.md` (submission
  note), this file.

## Hypothesis and target cost

The decode LM-head screen's level-one pass reads 1344 B/row over all 100352
rows = **134.88 MB/step**, measured at **510.9 µs/call and 264.0 GB/s** — 101%
of this host's 260.2 GB/s read ceiling. It is the largest single byte stream in
the decode step and is already bandwidth-saturated, so the only lever is to read
fewer bytes.

M1 re-splits the INT5 planes so the nibble plane alone is a self-contained
2×-coarse code, letting level one read **1088 B/row** and deferring the 256 B
bit plane to a sparse refinement over survivors only. That removes
**25.69 MB/step** (134.88 → 109.18 MB).

Priced at the level-one kernel's own 264.0 GB/s, that is **97.3 µs**, or
**−1.11% of `T`**. Priced at the step-average ~204.6 GB/s it would be −1.43%.
The local A/B is designed to discriminate between those two.

## Resolving the 76.6 µs / 134.9 MB contradiction

**The two figures belong to two different kernels.** From the measured
per-dispatch table (`research/nezuko-decode-roofline.md`, Interim 8):

| dispatch | n/step | µs/call | MB/call | GB/s | %ceil |
|---|---|---|---|---|---|
| `lmhead_int5_inline_coarse_v5` | 1 | **510.9** | **134.88** | 264.0 | 101% |
| `lmhead_exact_inline_mask_block_v1` | 1 | **76.6** | ~0.5 | — | latency |

The 134.88 MB belongs to the *coarse screen*, which takes 510.9 µs. The 76.6 µs
belongs to the *exact BF16 GEMV over survivors*, which reads ~0.5 MB and is
latency-bound, not bandwidth-bound. The lm_head block totals 528.3 µs over four
ops. There is no contradiction, and nothing about the byte table needs revising:
level one reads 1344 B/row unconditionally over all rows, with no early exit,
which was confirmed by source inspection as well as by the counter.

Consequently the cascade's ceiling prices cleanly: it removes 25.69 MB from a
510.9 µs / 264.0 GB/s stream.

## Evidence

- **Host:** Mac16,11 (M4 Pro), 48 GiB unified memory, low-memory startup
  profile, 20-core GPU. Thermal gate via `research/run_local_benchmark.sh`,
  which reads `.temp.cpu_temp_avg` because `macmon` reports a frozen 2.37 °C
  GPU temperature on this host.
- **Commands:**
  - Correctness + timing: `research/run_local_benchmark.sh --local-iterate`,
    8 runs in one session, ABBA-blocked (`ctrl, cand, cand, ctrl` × 2).
  - Same-binary arm switch: `DARKBLOOM_LMHEAD_FUSED_REFINEMENT=0` selects the
    single-pass control; unset selects the cascade. Both arms are the *same
    binary*, so the only difference is the screen.
  - Oracle: `research/run_upstream_equivalence.sh`.
- **Why a same-binary A/B rather than the harness baseline:** the
  `score.local-iterate.baseline.json` present on this host was three hours
  stale and from a different commit (`25e1d2c`). `--local-iterate`'s printed
  delta compared against it, which is exactly the unmatched-timing trap the
  runbook warns about. That stale artifact was moved aside and every number
  below comes from arms measured back-to-back in one session.

### Local A/B — all 8 arms, ABBA-blocked in one session

Arm and elapsed time came out very nearly orthogonal (mean elapsed 8.40 min for
`ctrl`, 8.45 min for `cand`), so the block did its job and the drift-corrected
regression `metric = a + b·t + c·arm` is well conditioned:

| Metric | Control | Cascade | Arm effect (drift-corrected) | Host drift |
| --- | ---: | ---: | ---: | ---: |
| `T` (pure decode step, ms) | 9.1185 | 8.9688 | **−1.643% ± 0.430%** (3.8σ) | +0.0027 ms/min |
| `S` (512-token prefill, ms) | 591.23 | 583.67 | −1.273% ± 0.639% (2.0σ) | −0.622 ms/min |
| `decode_seconds_per_token` (ms) | 13.7375 | 13.5287 | **−1.519% ± 0.314%** (4.8σ) | −0.0022 ms/min |

Host drift on `T` is negligible, so the `T` effect is not a drift artifact.

**`S` is a negative control and it is the dominant source of uncertainty.**
Refinement is applied only when the input is a single decode token, and the
`DARKBLOOM_LMHEAD_FUSED_REFINEMENT` switch does not alter the plane packing, so
both arms run a byte-identical prefill. The true `ΔS` is therefore **zero by
construction**, and the observed −1.257% (1.6σ) is prefill measurement noise —
prefill is a *single* 512-token forward, so it is far noisier per run than the
128-step decode average.

That matters because `T = dec − S/128` subtracts that noisy term. Propagating
it, σ(S)/128 ≈ 0.037 ms on a 9.0 ms `T` ≈ 0.41% — which is essentially all of
the 0.44% uncertainty on `T`. Two estimators therefore bracket the answer:

| Estimator | `ΔT` | as % of `T` | ns (×0.638) |
| --- | ---: | ---: | ---: |
| Per-run `T` (unconstrained) | −0.1498 ms | **−1.64% ± 0.43%** | +1.05% |
| Constrained `ΔS ≡ 0`, so `ΔT = Δdec` | −0.2087 ms | **−2.29% ± 0.34%** | +1.46% |

The constrained estimator is the statistically better one given that `ΔS = 0`
is known a priori, but it is also the more flattering one, so both are
reported.

**Both exceed the byte-removal prediction (−1.11% kernel-rate, −1.43%
step-average), and that deserves scepticism rather than celebration.** Three
candidate explanations, and what each would imply:

1. **Contiguity.** Level one now reads one contiguous 1024 B run per row
   instead of two disjoint streams (1024 B + 256 B), so it should also win on
   prefetch and TLB pressure, not only on bytes. This would make the excess
   real and would transfer to M5.
2. **The control is not the pre-M1 baseline.** The `=0` arm still carries the
   *new* plane packing and the renamed `_v6` single-pass kernel — it is
   "refinement off", not "pre-M1". If `_v6` were more expensive than the
   original `_v5`, the local delta would be inflated. Against this: both
   kernels read the same 1344 B/row and differ only by a couple of ALU ops in
   a memory-bound kernel, so they should be cost-equivalent. This is a
   *caveat on the local number*, not on the mechanism.
3. **Fewer survivors reaching the exact GEMV.** Bounded: the exact pass is
   only 76.6 µs total, so even eliminating it entirely buys 0.85% of `T`.

Explanation 2 is the one the local A/B cannot rule out on its own, and it is
precisely what the official **tree Y vs banked control C0** comparison
settles, because that pair *is* measured against the true unmodified base.
I am therefore treating the local result as "the mechanism works and is worth
official receipts", not as the final magnitude.

### Correctness

- Every one of the 8 `--local-iterate` runs: `max_abs_diff = 0`,
  `passed_correctness = true`, `checked_steps = 130`, identical `golden_hash`
  and `weights_hash`.
- Plane round-trip and decode algebra verified symbolically against all three
  consumer kernels; producer and consumers agree on both plane conventions.
- Refinement certificate re-derived (see note §3); the constant shipped here is
  **strictly more conservative** than the source submission's.

### Scope of the upstream-equivalence oracle: it does *not* reach this change

The brief asks for the equivalence oracle on the final tip. I ran it and it
reports what the brief asks for — but the honest reading is narrower than it
looks, and the difference matters.

`Sources/MLXFastModel/LagunaUpstreamEquivalence.swift:74` constructs the
runtime model directly and **never calls `prepareFusedRuntimeWeights()`**,
which is the only caller of the pruner constructor
(`LagunaRuntimeModel.swift:10943`, reached in production from
`LagunaRuntimeWeights.swift:637`). The oracle therefore exercises the *stock,
unfused, unpruned* head. Empirically confirmed: the oracle's full stderr
contains **zero** `mlxfast:` runtime markers, and in particular no
`mlxfast: lm_head prune active`, whereas every benchmark run emits it twice.

So the oracle result on the tip —

```
prefill  maxAbsLogitErr 0.125       meanAbs 0.011933609   token 5991 == 5991
decode-0..7  maxAbsLogitErr 0       meanAbs 0             all 8 tokens match
EQUIVALENCE_EXACT_STEPS=8
```

— is a valid zero-error statement about **Part 1a** (the two reverts *are* on
the oracle's path: `6ca0c71` is the NAX `fp_qmm_t` k-loop used by every routed
expert GEMM, `9c1ad1c` is dispatch-level), and it confirms the reverts changed
nothing numerically. Its prefill triple is byte-identical to the pre-M1 record
in `nezuko-decode-roofline.md:558`. **It says nothing at all about M1.**

This is a pre-existing property of the oracle, not something this arm
introduced — the same gap means the oracle has never covered the fused-QKV or
fused shared-gate/up mechanisms already on the frontier either. I did not
"fix" it by adding a `prepareFusedRuntimeWeights()` call, for two reasons:
`LagunaUpstreamEquivalence.swift` is inside `editablePaths`, so touching it
would have broken the byte-identity of the receipt family mid-flight; and
widening the oracle is a separate change that deserves its own measurement.
**Flagged as a follow-up — it is a real hole in the campaign's safety net.**

M1's correctness therefore rests on the gate that *does* run the pruner:
`--local-submit` on `04dd953`, `passed = true`, `checked_steps = 1025`,
`max_abs_diff = 0`, `passed_correctness = true`, golden hash `f49e4c2c…`, with
`mlxfast: lm_head prune active (coarse copy resident)` present in the log —
plus the 8 `--local-iterate` runs above. That is 1025 argmax-identical checked
steps through the live cascade, which is a stronger statement than the
oracle's 8, but it is a *token*-identity statement, not a logit-identity one.

### Correction to the brief: the named control family is stale

The brief says to compare against "the existing 3-receipt control on our base
(`f8502e12`, `71586bcf`, `f3cda678`)". Those three replicate **tanjiro's**
`BASE_SHA` from PR #13, which is *pre-harvest*. PR #20's
`BASE_SHA = aecc470` contains the #12 harvest merge, so it is seven commits
downstream of them:

```
git diff --stat 25e1d2c 9c1ad1c -- <97 editablePaths>
 8 files changed, 418 insertions(+), 844 deletions(-)
```

The family that *does* replicate this arm's base is my own harvest-tip trio
`5d522d6a`, `5e0e9cd1`, `c210d200`, submitted from commit `9c1ad1c`:

```
git diff --stat 9c1ad1c aecc470 -- <97 editablePaths>
 (empty)
```

**`9c1ad1c`'s editable surface is byte-identical to `BASE_SHA`.** Differencing
against `f8502e12`-family would silently credit this arm with the whole
7-commit harvest (`T −0.468%`), i.e. roughly half the predicted M1 effect.
C0 below therefore means `5d522d6a`/`5e0e9cd1`/`c210d200`; the pre-harvest
trio is reported alongside only as a cross-check.

### Receipt allocation

The brief authorises 4 receipts and asks for 3 on the byte-identical tip. I am
spending the 4th on a **decomposition** rather than a 4th replicate, because
with C0 already at n=3 and the pooled 27-dof floors (`ns` 0.149%, `T` 0.222%)
a 3-receipt Y resolves the predicted +0.91% at ~7.5σ, so a 4th Y buys almost
nothing, whereas without X the arm cannot separate Part 1a from M1 at all:

| tree | surface | receipts |
| --- | --- | ---: |
| C0 | `BASE_SHA` | 3 (banked) |
| X | `BASE_SHA` − `9c1ad1c` − `6ca0c71` | 1 |
| Y | X + M1 cascade | 3 |

`Y − C0` = the arm as briefed, `X − C0` = Part 1a alone, `Y − X` = **M1
alone**, which is the quantity the DRAM-saturation model actually predicts and
the only one that prices the remaining byte arms. Submission order
`Y, Y, X, Y` puts X mid-span so linear session drift cancels, and keeps the
briefed 3-receipt Y family intact if the last receipt is lost.

## Conclusion

_(completed once the official M5 family returns)_
