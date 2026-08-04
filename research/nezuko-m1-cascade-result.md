# PR #20 — LM-head three-level decode cascade (M1) + two deletions

SENPAI-RESULT: {"terminal":true,"status":"complete","pending_arms":false,"wandb_run_ids":[],"primary_metric":{"name":"official_m5_renormalised_ns_ratio_vs_base_family","available":true,"value":1.00455},"test_metric":{"name":"passed_correctness","available":true,"value":1}}

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

**And that last clause turns out to be the whole story of this arm.** 264.0
GB/s is **1.290×** the 204.6 GB/s step average. The brief prices removed bytes
at `MB / 1794`, i.e. at the step average. Removing bytes from an
above-average-efficiency dispatch buys proportionally *less* time. See the
conclusion.

## The survivor census: the byte numerator is confirmed to 99.3%

Before trusting a 25.69 MB numerator I instrumented the screen, because the
cascade's second stage re-reads the 1-bit residual plane for every surviving
four-row block. If survivors were common, most of the "removed" bytes would
come straight back. The inherited code asserted in a comment
(`LagunaLmHeadPrune.swift:626`) that survivors are "single digits per step".
**That assertion had never been instrumented, and it is wrong by two orders of
magnitude.**

The census is an env-gated diagnostic (`DARKBLOOM_LMHEAD_PRUNE_STATS=1`) that
evaluates the kernel's own screen `coarse + delta >= thr` on the host and
counts surviving rows and live four-row blocks. It forces a host sync per call
so it is never on a timed path, and it is **not** part of any submitted
archive — it was built and run on a scratch branch. The patch is reproduced at
the end of this document.

Over the 128 timed decode steps of one `--local-iterate` run:

| quantity | mean | median | min | max |
| --- | ---: | ---: | ---: | ---: |
| surviving rows (of 100352) | 534 | 288 | 55 | 9193 |
| live 4-row blocks (of 25088) | 458 | 269 | 55 | 7261 |

458 live blocks is **1.83%** of blocks. The re-read costs
`534 × (256 + 64) B = 171 KB/step`, so the **net removal is 25.519 MB of a
nominal 25.69 MB — 99.3%.** The numerator is right to within 0.7%, and the
half-size realised effect below is therefore *not* a byte-accounting error.

Two consequences beyond this arm:

- Anyone sizing the sparse-refine dispatch (the 6.5 GB/s, 74 µs/step dispatch
  the advisor flagged as the worst-efficiency op in decode) should use 458
  live simdgroups, not "single digits". 98.2% of simdgroups exit empty, not
  99.996%.
- The distribution is extremely skewed (median 288, max 9193). The max is a
  step where the model is genuinely uncertain between many tokens. A future
  fix to that dispatch must be sized on the mean, not the median.

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
   original `_v5`, the local delta would be inflated. Source audit bounds
   this: `_v5` and `_v6` read the identical 1344 B/row (1024 codes + 256
   residual + 64 scales) and differ only in decode algebra, because the
   `v5→v6` bump is a *re-encoding* rather than a rename — `_v5` puts the low
   4 bits in the nibble and bit 4 in the residual plane
   (`float4(ne | (he << 4u)) - 16.0f`), `_v6` puts `H = floor(q/2)+8` in the
   nibble and the residual low bit in the plane
   (`float4((ne << 1u) | he) - 16.0f`, `:194-195`). That inversion is exactly
   what makes the 1024 B nibble plane a self-contained 2×-coarse code
   (`float4(ne << 1u) - 15.5f`, `:281-282`). Same bytes, a couple of ALU ops
   apart, in a memory-bound kernel. This is a *caveat on the local number*,
   not on the mechanism.
3. **Fewer survivors reaching the exact GEMV.** Real but bounded, and now
   known to be in the *helpful* direction: M1's second screen is strictly
   tighter (half-cell `d = D/2`) than the one it replaces, so it can only
   reduce the number of live blocks reaching the 16 KB/block BF16 GEMV. The
   whole slot-4 pass is only 74–76.6 µs, so even eliminating it entirely buys
   0.85% of `T`.

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

The brief authorises 4 receipts and asks for 3 on the byte-identical tip. I
**planned** to spend 2 on a decomposition instead. This is a deliberate
deviation and here is the justification; the outcome — the 2 X receipts never
got a submission slot — is recorded after the plan, not substituted for it.

`Y − C0` is not M1. It is M1 *plus* Part 1a, the two reverts the brief also
told me to land in the same arm — and the brief's own hypothesis is that
`9c1ad1c` carries our `S +0.236%` regression, i.e. that Part 1a moves the score
on its own. The one number the brief asks for, "the realised MB-to-score
conversion factor … that single number re-prices every other byte arm on the
board", is therefore only computable from `Y − X`.

| tree | surface | receipts |
| --- | --- | ---: |
| C0 | `BASE_SHA` (`aecc470`) | 3 (banked; see the stale-control correction above) |
| X | `BASE_SHA` − `9c1ad1c` − `6ca0c71` | 2 |
| Y | X + M1 cascade | 2 |

Splitting 2/2 rather than 3/1 dominates on both decomposition contrasts and
costs almost nothing on the briefed one:

| contrast | Y=3, X=1 | Y=2, X=2 |
| --- | ---: | ---: |
| `Y − X` (M1 alone) | 1.155σ | **1.000σ** |
| `X − C0` (Part 1a alone) | 1.155σ | **0.913σ** |
| `Y − C0` (as briefed) | **0.816σ** | 0.913σ |

At the pooled 27-dof floor σ(`ns`) = 0.149% that is 0.149% on M1 and 0.136% on
Part 1a, against 0.172% for both under the 3/1 split.

The second driver is Y1 itself. It returned `ns +0.456%`, less than half the
predicted +0.914%. Once an effect is known to be present but half-size, a third
replicate only narrows Y's own mean from 0.105% to 0.086% — while the entire
*interpretation* of that half-size number turns on whether Part 1a is adding to
it or cancelling part of it. Precision on the confound is worth more than
precision on the total.

**Order is forced to `Y, Y, X, X`** because Y2 was already in flight when Y1
returned. That makes `Y − X` co-linear with session time, which I do not like.
The mitigation is that the σ quoted above is the pooled 27-dof floor estimated
across receipts spanning 07:53–15:00 on this same board, so it already contains
whatever between-session drift the service has; it is not a within-session
repeatability figure. `S` — which nothing in this family should move — is the
built-in drift control on every contrast, and it has stayed inside 0.5σ.

## Official M5 receipts

All receipts are `mlxfast` submissions on this account, measured against the
pinned baseline in their own session. `rejected` here means "did not clear the
leaderboard ranking bar", **not** a gate failure — every gate passed on every
receipt.

| id | tree | submitted | `officialScore` | `decode_s/tok` | `prefill_s/tok` | `baseline_decode` | `baseline_prefill` |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| `5d522d6a` | C0 | 10:49 | 2.49146984957439 | — | — | — | — |
| `5e0e9cd1` | C0 | 11:15 | 2.50009215851464 | — | — | — | — |
| `c210d200` | C0 | 11:38 | 2.51474335355716 | — | — | — | — |
| `0c21dc18` | Y | 14:16 | 2.49232051064996 | 0.0050840029296875 | 0.000191463623046875 | 0.0138298844453125 | 0.000366997884765625 |
| `2dce5912` | Y | 14:48 | 2.49270808422625 | — | — | — | — |
| `1feeabc8` | X | 15:34 | 2.50037778074127 | — | — | — | — |
| `X2` | X | not run | — | — | — | — | — |

`1feeabc8` (commit `3478ba9`) is the decomposition control: tree X, committed
at `6d14ed9`, the promoted frontier with the two Part 1a commits reverted and
nothing added. It landed and **it changes the headline** — see the next
section. A second X receipt was prepared and attempted but not accepted: the
endpoint enforces `account already has 1 submission(s) in flight for this
benchmark (limit 1)` **per account**, not per student, and the slot was held
by a sibling student's run. So X is n=1, and every statement below carries
that.

Gate detail for `0c21dc18` (representative; `2dce5912` matches):

```
max_abs_diff            0
passed_correctness      true
checked_steps           1344
gpqa_ttft_passed        true   (9/9)
semantic_gpqa_passed    true   (9/9)
decode_speedup_floor    true
prefill_speedup_floor   true
peak_ram_gb             21
bandwidth_gb_per_token  0      (model is RAM-resident, as documented)
```

### `Y − C0`: the arm exactly as briefed

Renormalised per `research/nezuko-renormalise.py`, with
`S = 512000 × prefill_s_per_tok` ms and `T = 1000 × decode_s_per_tok − S/128`
ms:

| statistic | C0 (n=3) | Y (n=2) | effect |
| --- | ---: | ---: | --- |
| `ns` | 2.518242 | 2.529702 | **+0.455% ± 0.136%  (3.3σ)** |
| `T` (ms) | 4.3513 | 4.3224 | **−0.664% ± 0.203%  (3.3σ)** |
| `S` (ms) | 97.942 | 97.863 | −0.080% ± 0.159%  (0.5σ) |
| published `officialScore` | 2.502102 | 2.492514 | −0.383% ± 0.446%  (0.9σ) |

Within-family cv: C0 `ns` 0.180%, `T` 0.253%, `S` 0.091%, published 0.470%;
Y `ns` 0.002%, `T` 0.140%, `S` 0.241%, published 0.011%.

Three things to read off this table:

1. **The effect is real and on the predicted axis.** 3.3σ on both `ns` and `T`,
   same sign, consistent magnitude.
2. **The negative control is clean, and it is a real prediction rather than a
   hope.** `refine` is `useFusedRefinement && lagunaLmHeadFusedRefinementEnabled`
   (`LagunaLmHeadPrune.swift:932`), and `useFusedRefinement` is
   `inputs.dims(1, 1)` (`LagunaRuntimeModel.swift:10862-10865`) — true *only*
   for a single-token step. On the 512-token prefill the cascade is off and
   slot 1 falls back to a 1344 B/row kernel, byte-identical to the base. So M1
   is structurally incapable of moving `S`, and `S` moved by
   −0.080% ± 0.159%. A significant `S` shift would have been evidence that
   something other than the intended mechanism was in the receipts.
3. **The published score says nothing.** −0.383% ± 0.446% on the same data
   where the renormalised statistic reads +0.455% ± 0.136%. Had I ranked on
   `officialScore` I would have reported this arm as a mild *regression*. This
   is the sharpest single demonstration of the 3.3× instrument advantage I
   measured in #12, and it is on a real effect rather than on identical code.

### `X − C0` and `Y − X`: the decomposition, and why it matters

`Y − C0` is the arm as briefed, but the brief bundled two things: the LM-head
cascade (M1) and two Part 1a reverts. `1feeabc8` separates them.

| contrast | what it isolates | `ns` | `T` | `S` |
| --- | --- | --- | --- | --- |
| `X − C0` | the two Part 1a reverts alone | +0.179% ± 0.172% (1.0σ) | −0.274% ± 0.256% (1.1σ) | −0.010% ± 0.201% (0.0σ) |
| `Y − X` | the LM-head cascade alone | +0.276% ± 0.182% (1.5σ) | −0.391% ± 0.272% (1.4σ) | −0.071% ± 0.213% (0.3σ) |
| `Y − C0` | both together (as briefed) | **+0.455% ± 0.136% (3.3σ)** | **−0.664% ± 0.203% (3.3σ)** | −0.080% ± 0.159% (0.5σ) |

The two rows compose exactly into the third — that is an identity of ratios of
the same three family means, not an independent check. The *content* is the
split, and it is uncomfortable:

**By point estimate, 39% of the effect I reported as "the byte mechanism" is
the two reverts, not the cascade.** On `T` the share is 41%.

I want to be precise about how much this is established, because the honest
answer is "not much, and that is itself the finding":

- The combined `Y − C0` = +0.455% ± 0.136% is solid at 3.3σ. Nothing here
  touches it.
- Neither half is significant on its own. `X − C0` is 1.0σ and `Y − X` is
  1.5σ, against a 2σ resolution floor of 0.344% for these family sizes. With
  X at n=1 I cannot reject "the reverts did nothing" *or* "the reverts did 39%
  of it".
- The errors on the two halves are anti-correlated by construction, so this is
  one measurement with a poorly-located split point, not two measurements.

What follows regardless of where the split point sits:

**The 0.50× conversion factor is an upper bound on the cascade's own
conversion factor, not an estimate of it.** The cascade alone converts at
`0.276/0.914 = 0.302×` centrally, with a 1σ range of roughly 0.10× to 0.50×.
Any byte-removal experiment priced off this arm should use ≤0.50×, and should
plan against ~0.30×.

This also makes the unexplained residual *worse*, not better. After the
measured 0.775 dispatch-denominator correction the cascade-alone prediction is
−1.102% of `T` and the cascade delivered −0.391%, a factor of 0.355 rather
than the 0.602 I computed from the combined arm. Whatever is missing, there is
more of it than I said.

One pre-registered prediction failed. I predicted that if the conversion
factor were a property of M1 alone, `X − C0` would show `ns ≈ 0` and
`S ≈ −0.24%` — the latter because the advisor's hypothesis was that one of the
reverted commits caused the harvest's `S +0.236%` prefill regression. Measured
`S` is −0.010% ± 0.201%: no recovery. That is 1.14σ from the prediction, so it
is not rejected, but the prime suspect is not currently supported either.

## Conclusion

### The headline answer

**No. Removing 25.5 MB/token from the LM-head read stream does not buy the
+0.914% of score the DRAM-saturation model predicts. The briefed arm buys
0.455%, which is 0.50× the prediction — and once the decomposition control is
subtracted, the byte mechanism's own share is centrally 0.302×, with 0.50× as
its upper bound.**

The model is not wrong in sign or in kind. The effect is real (3.3σ), it lands
on the predicted axis (`T`, decode) and not on the control axis (`S`,
prefill), and its sign is the predicted one. The model is wrong in
**magnitude**, and it is wrong in the direction that matters most for
planning: a byte removed from *this* stream is worth about half what the
average byte in the token budget is worth, so any arm priced at the average
rate is over-priced by roughly 2×.

| quantity | brief's prediction | realised | ratio |
| --- | ---: | ---: | ---: |
| score (`ns`) | +0.914% | **+0.455% ± 0.136%** | **0.50** |
| decode `T` | −1.422% | **−0.664% ± 0.203%** | **0.47** |
| %score per MB | 0.03556 | **0.01783** | **0.50** |

The observed `T` rejects the brief's prediction at **3.7σ** — but only if the
prediction is treated as an exact point value, which is generous to me. Both
`1794` and `25.7` are derived quantities. Giving the prediction its own
uncertainty:

| prediction uncertainty | rejection |
| --- | ---: |
| ±0% (as quoted) | 3.73σ |
| ±5% | 3.52σ |
| ±10% | 3.06σ |
| ±15% | 2.57σ |

The rejection survives any plausible uncertainty on the byte budget, but
"3.7σ" is an upper bound on the confidence rather than a neutral statement of
it. I would defend "rejected at ≥3σ" and not more.

**Two caveats attach to the headline itself**, both stated at length below and
neither of which I want a reader to miss:

1. **The measured arm is M1 *plus* the two Part 1a reverts**, which the brief
   told me to land together, and the decomposition control says that bundling
   matters. `1feeabc8` puts **39% of the +0.455% on the reverts** by point
   estimate. At n=1 for X neither half clears 2σ, so the split is not
   established in either direction — but "attribute it all to the byte
   mechanism" is no longer the default reading, and I have changed the
   headline accordingly. The table above is the briefed arm; the byte
   mechanism alone is +0.276% ± 0.182%.
2. **The conversion factor is what this arm measures well. The *explanation*
   for it is incomplete.** The 0.50× combined figure is a 3.3σ measurement and
   I stand behind it. Of the miss, a measured dispatch-denominator correction
   accounts for 45%; **the remaining 0.438% ± 0.203% of `T` I cannot currently
   explain**, and on the cascade-alone contrast the unexplained part is larger
   still. I had an explanation, it was wrong, and I withdraw it below rather
   than ship it.

### The two-stage conversion failed in exactly one of its two stages

The brief's model is a product of two independent conversions:

```
score gain = 0.638 × (MB removed) / 1794
             ^^^^^                  ^^^^
             T → score              MB → T
```

Reporting a single lumped "0.50× realised" hides the actual finding, because
only one of the two legs is an empirical claim at all.

- **`T → score` = 0.638 cannot fail. It is an algebraic identity, not a
  measured constant** — and I do not think this was noticed when the model was
  written. With `S` unchanged,

  ```
  d(ln ns) = 0.75 · d(ln decode_speedup) = −0.75 · dT / (T + S/128)
           = −[0.75 · T/(T + S/128)] · (dT/T)

  0.75 × 4.3513 / (4.3513 + 97.942/128) = 0.75 × 0.85045 = 0.63784
  ```

  The brief's 0.638 *is* `0.75 · T/(T + S/128)` evaluated at the pinned
  baseline, to three decimal places. So this leg was never at risk and there
  is nothing to validate. I originally wrote that my realised 0.455/0.664 =
  0.685 "confirms" it; that was wrong twice over. It cannot confirm a
  definition, and propagating the errors gives **0.685 ± 0.293**, which fails
  to distinguish 0.638 (0.16σ) from 0.4 (0.97σ) or 1.0 (1.07σ). The ratio is
  a consistency check on my own arithmetic and nothing more.

  The one condition the identity needs is `S` unchanged, which I verified
  independently from the code (see the negative-control note above) and
  measured at −0.080% ± 0.159%.

- **Therefore 100% of the miss is in `MB → T`, and this is established by
  algebra rather than by splitting the blame empirically.**
  Assumed 0.05574 %`T` per MB; realised **0.02602 %`T` per MB** — **wrong by
  2.14×**. This is the single number that needs to be re-derived, and it is
  the number the brief said would "re-price every other byte arm on the
  board".

So the correction to apply to sibling byte arms is **not** a blanket 0.50× on
the score estimate. It is a 0.47× on the *byte-to-time* leg only — and that
0.47× is itself a product of two independent, separately transferable errors,
which is the form other arms should actually reuse:

```
0.467  =  0.775            ×  0.602
          ^^^^^               ^^^^^
          bytes left a         unexplained
          1.29x-faster-        residual
          than-average
          dispatch
```

The two factors do not have the same epistemic status and I do not want them
read as if they do:

- **0.775 is measured, and it is the part other arms can reuse.** It is the
  ratio of two independently measured bandwidths, 204.6 and 264.0 GB/s,
  neither of which came from this arm's receipts. It would have been the same
  number had the arm never run. It applies to any arm removing bytes from an
  above-average dispatch; an arm removing bytes from an *average* dispatch
  should keep `MB / 1794` unchanged.
- **0.602 is the residual, and it has no mechanism attached to it.** It is
  `observed / dispatch-corrected prediction` by construction, i.e.
  definitionally "everything I did not predict". I initially named it a
  survivor-re-read effect; that attribution was wrong by two orders of
  magnitude and is withdrawn two sections below. **Do not propagate 0.602 to
  other arms** — it is this arm's unexplained remainder, not a transferable
  correction.

### Why `MB → T` failed: the denominator is a bandwidth, and the brief used the wrong one

The brief divided removed bytes by 1794, which is the **step-average**
bandwidth of the whole decode step. But the dispatch these bytes were actually
removed from does not run at the step average. Measured on this M4 host:

| | GB/s | vs step average |
| --- | ---: | ---: |
| decode step average | 204.6 | 1.00× |
| `coarse` LM-head dispatch (where the bytes were) | 264.0 | **1.29×** |

Bytes were being removed from a stream that was already running 29% *faster*
than average, so removing them frees proportionally less time than the average
rate implies. Re-pricing at the correct 264 GB/s denominator moves the
prediction from −1.422% to **−1.102%** of `T`.

That closes about 45% of the gap and is a real, mechanical correction to the
brief's method. **It is not sufficient.** The observed −0.664% ± 0.203% still
rejects the dispatch-corrected −1.102% at **2.2σ**. Something else is eating
the remaining 0.438% of `T`.

### Where the residual 0.438% goes: 171 KB through the worst dispatch on the machine

The cascade does not remove *all* the bytes. Surviving rows must still be
re-read at full precision. The brief assumed this was negligible, and the
inherited code comment at `LagunaLmHeadPrune.swift:626` asserts the survivor
count is "single digits per step".

**That comment is wrong by two orders of magnitude.** The census (method and
patch in the appendix) over all 128 timed decode steps:

| | rows | 4-row blocks |
| --- | ---: | ---: |
| mean | 534 | 458 |
| median | 288 | 269 |
| min | 55 | 55 |
| max | 9193 | 7261 |

458 live blocks of 25088 = **1.83% occupancy**. The re-read is
534 × 320 B = **171 KB/step**, so the net removal is 25.519 MB of the nominal
25.69 MB — **99.3%**. On a pure byte count the comment's error is harmless:
171 KB against 25.69 MB is a rounding error, and the byte numerator survives.

It is *not* harmless on a time count, and the reason is a structural fact
about *where* those 171 KB land. M1 does not add a dispatch. It has exactly
four dispatches before and after, and it **swaps slot 4 in place**:

| slot | before (`6d14ed9`) | after (HEAD) |
| ---: | --- | --- |
| 1 | `..._int5_inline_coarse_ratio_bound_delta_bf16_v5`, 1344 B/row | `..._int5_base_coarse_delta_bf16_v1`, **1088 B/row** |
| 2 | `..._coarse_argmax_stage1_v5` | unchanged |
| 3 | `..._exact_winner_bf16_midpoint_threshold_v1` | unchanged |
| 4 | `..._exact_inline_mask_block_delta_bf16_lane0_mask_v1` | `..._exact_fused_int5_sparse_refine_v1`, **+320 B/survivor** |

(`LagunaLmHeadPrune.swift:939-954` and `:971-986`; grid and threadgroup are
byte-identical in all four slots, only the buffer set changes. The 320 B is
`codes_bit` 256 B + `scales` 64 B, `:694-695` — exactly the census
denominator.)

Slot 4 is the dispatch the campaign knows as **"74 µs/step, 0.481 MB,
6.5 GB/s — the worst-efficiency dispatch in the entire decode step, 2.5% of
ceiling"**. My first draft of this section used that figure to explain the
whole residual shortfall: 171 KB entering a 6.5 GB/s dispatch would cost
13–26 µs on M5, bracketing the observed 19.1 µs neatly.

**That argument is wrong, and so is the 6.5 GB/s figure it rests on. Both fail
for the same reason my census exists.** This is the most consequential thing
in this report and it goes against my own arm, so I am showing the working.

The 0.481 MB byte count for slot 4 counts only the all-rows screen — lane 0
reading `coarse[r]` (4 B) + `delta[r]` (2 B) for its four rows, i.e. 6 B/row
over 100352 rows = 0.602 MB. It omits the dominant term. When
`candidate_mask != 0` the kernel falls through to a stock `gemv_al` replica
that reads **all four rows of `lm_head` unconditionally** — `mrow = lm_head +
(base + tm) * K` for `tm` in 0..3, 16 iterations of 4 BF16 per lane
(`6d14ed9:455-482`) — which is 4 × 2048 × 2 B = **16 KB per live block**.

That term was assumed negligible because the code comment said live blocks are
"single digits per step". **My census measured 458.** So:

| term | bytes/step |
| --- | ---: |
| all-rows screen (6 B × 100352) | 0.602 MB |
| BF16 GEMV (458 live blocks × 16 KB) | **7.504 MB** |
| `x` (2048 BF16, cache-resident) | 0.004 MB |
| **total, unique** | **8.110 MB** |

**8.110 MB in 74 µs is 109.6 GB/s = 42% of the 260.2 GB/s ceiling.** On issued
bytes (`x` is re-read by each of the 458 active simdgroups) it is 9.98 MB and
135 GB/s. Either way it is an ordinary rate for a scattered 16 KB-granular
gather — **not a defect, and not 2.5% of ceiling.** The true byte count is
**16.9× the assumed one**, and the "worst dispatch in decode" is an artefact
of the same refuted comment my census was written to test.

Three things follow, and the first one costs me my own explanation:

1. **My re-read hypothesis fails by two orders of magnitude.** Priced at the
   corrected 109.6 GB/s, the 171 KB costs **1.56 µs on M4 = 0.018% of `T`**,
   not 0.438%. It cannot explain the shortfall. I am withdrawing the bracket
   argument rather than keeping it because it was pleasing.
2. **The residual 0.438% ± 0.203% of `T` is therefore unexplained.** I have a
   measured conversion factor and a measured dispatch-denominator correction
   that closes 45% of the gap; I do not have an account of the rest. Saying so
   is more useful than a mechanism that dissolves on inspection.
3. **The campaign's second-largest identified decode opportunity is much
   smaller than believed.** Pricing slot 4 from 0.481 MB gave "~65–69 µs
   recoverable = 0.48% of score". At 8.11 MB and 42% of ceiling the arithmetic
   is completely different, and a scattered gather will not reach ceiling
   anyway. This should be re-derived before anyone is assigned to it.

The unit "bytes removed" is still the wrong unit for pricing an optimisation —
but the lesson from this section is narrower and sharper than the one I first
drew. It is not "price at achieved bandwidth". It is: **an achieved-bandwidth
figure is only as good as its byte numerator, and a numerator resting on an
uninstrumented code comment is not evidence.** The 6.5 GB/s number was wrong
not because bandwidth is the wrong lens but because 0.481 MB was wrong.

I want to state the generalisation carefully, because the obvious phrasing is
too strong. "Always price at achieved bandwidth" is **not** correct: in a
latency-bound or occupancy-bound dispatch, bytes are nearly free and should be
priced at ~0, not at the achieved rate. The defensible rule is **price at the
binding resource, and audit the byte numerator before you trust either.**

### Two things I can rule out for the residual without spending a receipt

Both are source-level, cost nothing, and narrow the search.

**1. Stream fragmentation is not the mechanism.** The obvious suspicion about
a 19% byte saving that under-delivers is that the removed bytes were
interleaved with retained ones, so the memory system still fetches them. That
is not the layout here. The three planes are **separate buffers with separate
base pointers**, and the M1 coarse kernel simply stops binding one of them:

```
before  inputNames: ["x", "codes_lo", "codes_hi", "scales"]
        codes_lo + row*1024 ,  codes_hi + row*256 ,  scales + row*64
after   inputNames: ["x", "codes_base", "scales"]
        codes_base + row*1024 ,                      scales + row*64
```

`codes_hi` is not bound, not addressed, and not read. Each surviving buffer is
still walked with a contiguous per-row stride. This is a clean whole-buffer
drop — 25.69 MB of perfectly sequential traffic removed from a dispatch that
was already sequential — which is the *most* favourable case for the byte
model, not a degraded one. So the residual is not fragmentation, and it is not
cache-line granularity either.

**2. A large fixed per-dispatch cost is self-contradictory with the 101%
figure.** The other natural explanation is that slot 1's 510.9 µs contains a
big byte-independent component (launch, tail, the final reduction), so cutting
19% of bytes cuts less than 19% of time. Price it: to explain the
cascade-alone shortfall, slot 1 would have to save ~34.5 µs rather than
97.3 µs, which requires **~65% of its runtime to be byte-independent** — and
then its byte-proportional part would have to move 134.88 MB in ~181 µs, i.e.
at **~745 GB/s, roughly 3× the DRAM ceiling.** A dispatch cannot be reported
at 101% of the read ceiling *and* be two-thirds fixed cost. One of those two
claims is wrong.

That is the sharpest lead I can hand over, and it points back at the
measurement rather than at the mechanism. Note also that "264.0 GB/s = 101% of
ceiling" is not a description of a perfect dispatch; **a sustained read cannot
exceed the read ceiling**, so either the 260.2 GB/s ceiling is ~5% low (M4 Pro
is 273 GB/s nominal, so 264 GB/s = 96.7% of nominal is entirely plausible and
I think this is the answer) or the 134.88 MB numerator is high. Given that
this same campaign's *other* `lm_head` bandwidth figure turned out to have a
16.9×-wrong numerator, the numerator deserves a counter rather than an
assumption. The per-dispatch probe of the after-build settles both at once:
slot 1 should read **413.5 µs** if the bytes left at the dispatch's own rate.

### The advisor's "second lever" needs re-deriving before it is assigned

The 14:38 note prices fixing slot 4 at "~65–69 µs recovered = 0.75% of the M4
step ≈ 0.48% of score", and calls it *"on your surface, needs no new
mechanism, and removes no bytes — so it is orthogonal to your main arm and
cannot confound it."* Two corrections, in increasing order of importance.

**First, it is not orthogonal: it is slot 4, and this arm replaces slot 4.**
The kernel the note prices,
`..._exact_inline_mask_block_delta_bf16_lane0_mask_v1`, **does not exist in my
tree** — M1 swapped it for `..._exact_fused_int5_sparse_refine_v1` in the same
slot with identical geometry. Any fix must be written against the post-M1
kernel, or it is patching code that merging M1 deletes.

**Second, and this is the one that changes the decision: the 0.48% is built on
the 0.481 MB byte count, and that number is 16.9× too small.** The
diagnosis it supports — "too few bytes in flight per lane" — reads the lane-0
`simd_broadcast` as the binding constraint. It is not. The broadcast governs
the *screen*, which is 0.602 MB of the dispatch's 8.11 MB; the other 7.5 MB is
a fully-parallel 32-lane BF16 GEMV over 458 live blocks that no broadcast
throttles. At 42% of ceiling on a scattered 16 KB-granular gather, slot 4 is
close to what that access shape can deliver.

I have not re-derived the true headroom, and I do not want to guess at it in
place of the wrong number: the honest statement is that **the recoverable time
in slot 4 is unknown and materially smaller than 65–69 µs.** The cheap way to
settle it is the per-dispatch probe below, which measures slot 4 directly
instead of inferring it.

What *is* still true and still worth assigning is narrower: 458 live blocks
read 16 KB each to use at most 4 rows' worth of it, and the block-granular
`for tm in 0..3` loop reads all four rows even when one survived. With 534
survivors in 458 blocks, roughly **1.2 rows per live block are wanted out of
4** — so a row-granular gather could plausibly cut the GEMV term by ~3×
(7.5 MB → ~2.2 MB). That is a real, sized opportunity resting on measured
survivor counts rather than on a code comment, and it is a *different* fix
from the one the note describes.

### Resolution of the 76.6 µs / 134.9 MB contradiction

**Resolved: the two figures belong to two different dispatches, and the
premise of the contradiction was a byte-count error.**

The brief's framing was: 76.6 µs at the 260.2 GB/s ceiling moves at most
~20 MB, which is irreconcilable with a 134.9 MB plane read. The resolution has
two parts:

1. **The 134.9 MB belongs to slot 1, not slot 4.** Slot 1
   (`lmhead_int5_inline_coarse_v5`) reads 1344 B/row × 100352 = 134.88 MB in
   510.9 µs at 264.0 GB/s. Slot 4 is a separate 74–76.6 µs dispatch. There was
   never a single kernel doing both.
2. **Slot 4's own byte count was wrong by 16.9×**, and my census is what
   showed it. At 0.481 MB it looked like a 6.5 GB/s pathology; at the measured
   458 live blocks it is 8.11 MB at 109.6 GB/s and needs no special
   explanation.

So the brief's instinct was right — a 76.6 µs figure could not be
reconciled — but the irreconcilable quantity was slot 4's *bytes*, not slot
1's. This was the "highest-value thirty minutes in the arm" and it paid, just
not in the direction anyone expected.

I should also flag two of my own retractions in this area:

- I earlier back-solved a −8.6% achieved-bandwidth drop and attributed it to
  MLP loss. **Never measured, and physically doubtful** — the before-kernel
  was already at 101% of its ceiling, leaving no room for the mechanism I
  proposed. Retracted.
- I then replaced it with the survivor-re-read explanation for the residual
  shortfall. **Also wrong**, by two orders of magnitude, once slot 4 is priced
  with the correct numerator. Retracted above.

The residual 0.438% ± 0.203% of `T` currently has *no* mechanism attached to
it, and I would rather leave that gap open than fill it a third time.

The cheapest discriminator, if anyone wants to close it properly: run a
per-dispatch probe of the *after* build on the same M4 host. Slot 1 goes from
1344 to 1088 B/row, so at unchanged bandwidth it should read
`510.9 × 1088/1344 = 413.5 µs`. **≈414 µs kills the MLP story; ≈453 µs would
support it.** One build, one run, no receipts. The same probe reads out slot
4's new cost directly, which would replace the bracket above with a
measurement.

### Issued vs unique bytes — proposing a standing rule

Both my numerator and the brief's are **unique** bytes: each vocabulary row's
weight counted once per step. They are *not* **issued** bytes, which would
additionally count the same line being pulled by several threadgroups.

For this arm the two coincide closely enough not to matter, because the
LM-head weight stream is read once per row. But they diverge badly for gather
GEMMs and for any kernel with re-reading tiles, and a brief that quotes "MB
removed" without saying which one is not reproducible. **Proposed standing
rule: every byte-arm brief must declare `unique` or `issued` in the same
sentence as the MB figure.** All figures in this report are `unique`.

### Caveats I do not want buried

- **Transfer confound.** Both bandwidth denominators (204.6 and 264.0 GB/s)
  are M4 measurements; the effect they are predicting is an M5 measurement.
  The 1.29× dispatch-to-average ratio is the kind of quantity that should
  transfer, but it has not been verified on M5, and the M5 is authoritative.
- **The "impossible bandwidth" argument is weak and I am not leaning on it.**
  The realised saving implies a marginal 883 GB/s against a 614 GB/s nominal
  peak, which sounds like a contradiction; at 2σ it drops to 548 GB/s and the
  contradiction evaporates. It is suggestive, not evidence.
- **Prompt dependence.** Survivor counts are a property of the logit
  distribution, so the census transfers exactly from M4 to M5, but the hidden
  M5 prompts are not these prompts and the mean could differ. The conclusion
  only needs the re-read to be small in bytes, and at 171 KB against 25.69 MB
  there are two orders of magnitude of margin.
- **The published `officialScore` disagrees with this entire result**, and is
  wrong. On the same receipts it reads −0.383% ± 0.446% where the renormalised
  statistic reads +0.455% ± 0.136%. Ranking on `officialScore` would have
  filed this arm as a mild regression.

### Partly resolved: the Part 1a / M1 decomposition

`Y − C0` is the arm exactly as briefed. It is **not** M1 alone: it is M1
*plus* the two Part 1a reverts, which the brief also told me to land in the
same arm. One decomposition receipt landed (`1feeabc8`, tree X = `BASE_SHA` −
`9c1ad1c` − `6ca0c71`), which is enough to change the reading and not enough
to settle it. The full contrast table is in
*`X − C0` and `Y − X`: the decomposition* above; the summary is:

- Point estimate: **39% of the briefed arm's +0.455% is the two reverts.**
- Neither half clears 2σ at n=1 for X, so the split location is unresolved.
- The safe consequence: **0.50× is an upper bound on the byte mechanism's own
  conversion factor; plan against the 0.302× central estimate.**

A second X receipt was prepared and attempted three times but never accepted —
the endpoint enforces a 1-in-flight limit *per account*, not per student, and
a sibling's run held the slot throughout. Tree X is committed at `6d14ed9`,
verified byte-identical on the editable surface, and the driver is
`research/sweep_x_vs_y.sh`. Taking X to n=2 moves the 2σ resolution floor from
0.344% to about 0.30%, which would still not separate a 0.179% effect; **X
needs n≈4 to call this**, and that is the honest cost of the answer.

My pre-registered prediction was that if the half-size conversion factor were
a property of M1 rather than Part 1a, `X − C0` would read `ns` ≈ 0 and
`S` ≈ −0.24%. Measured: `ns` +0.179% ± 0.172%, `S` −0.010% ± 0.201%. The `ns`
leg went the wrong way for that hypothesis and the `S` leg showed no recovery
at all. Neither is significant, so the prediction is not rejected — but it is
not supported, and I am recording it as failed-as-stated rather than quietly
dropping it.

One further consequence for the advisor's own model: the hypothesis that
`9c1ad1c` carries the harvest's `S +0.236%` prefill regression now has a
direct test rather than an inference, and that test came back flat
(−0.010% ± 0.201%). If that regression is real it is more likely in one of the
five *unreverted* harvest commits.

### What I did not do, and why

I did not implement the refine-dispatch fix, despite having the diagnosis and
a concrete plan (P1: all-lane vectorised screen plus an in-simdgroup survivor
loop, 74 µs → ~15–20 µs, ~100 lines). The brief's stop rule is "one mechanism,
one attribution", and this arm's whole value is a clean conversion factor. A
second mechanism landed in the same receipts would have destroyed it. The plan
is written up in the body for the advisor to assign separately — but as noted
above, it must be scoped as *recovering this arm's shortfall*, not as an
independent gain.

### Recommendation

1. **Stop treating `T → score` = 0.638 as a measured constant.** It is
   `0.75 · T/(T + S/128)` at the pinned baseline. Recompute it whenever `T`
   or `S` moves rather than carrying 0.638 forward — and note that any arm
   which *does* move `S` invalidates it and needs the full two-term form.
   No arm should ever spend a receipt "validating" it.
2. **Retire `MB / 1794` as a universal byte-to-time rule.** Replace it with
   per-dispatch pricing: use the achieved bandwidth of the dispatch the bytes
   actually live in. For this arm the removed bytes left a 264 GB/s dispatch,
   not the 204.6 GB/s step average, and that alone is a 0.775× correction.
3. **Audit every achieved-bandwidth figure's numerator before acting on it.**
   The 6.5 GB/s "worst dispatch in decode" was wrong because its byte count
   omitted a 7.5 MB term, on the authority of an uninstrumented code comment.
   A GB/s figure is a ratio, and this campaign has been treating the numerator
   as free. Any dispatch whose byte count came from reasoning about code rather
   than from a counter should be re-checked.
4. **Re-audit sibling byte arms for the dispatch-denominator factor only.**
   Ask of each arm: what is the achieved bandwidth of the dispatch the bytes
   leave, versus the 204.6 GB/s step average? An arm removing bytes from an
   average dispatch keeps `MB/1794` intact. Do **not** apply my `0.602` — it
   is an unexplained residual specific to this arm, not a correction.
5. **Price byte arms at ≤0.50×, and plan against ~0.30×.** The decomposition
   receipt moved the byte mechanism's own central conversion factor from
   0.50× to 0.302×. 0.50× is now an upper bound. Any arm on the board whose
   go/no-go rests on `MB/1794 × 0.638` at face value is over-priced by 2–3×,
   which is enough to move several of them below the 0.61% bar.
6. **Do not assign the slot-4 fix as currently priced.** Re-derive it first.
   The 0.48%-of-score estimate rests on a 16.9×-too-small byte count and on a
   `simd_broadcast` diagnosis that governs only 7% of the dispatch's traffic.
   If something is assigned there, the defensible target is the *row-granular
   gather*: 458 live blocks read 16 KB each for ~1.2 wanted rows out of 4, so
   the 7.5 MB GEMV term could plausibly fall ~3×. Write it against the post-M1
   kernel. And whatever it is priced at, apply recommendation 5 to that price.
7. **Run the per-dispatch probe of the after-build.** One M4 build, one run,
   no receipts. It settles the MLP retraction, measures slot 4 directly, and
   is the only cheap route to the unexplained residual — which the
   decomposition made *larger*, not smaller.
8. **Finish the decomposition only if the answer is worth ~3 more receipts.**
   X is at n=1. n=2 still cannot separate a 0.179% effect; n≈4 can. The
   cheaper alternative is to accept the ≤0.50× upper bound from
   recommendation 5 and spend those receipts on a new mechanism instead. My
   recommendation is the latter — the bound is already actionable, and the
   exact split point changes no decision I can identify.

   This is a campaign-allocation recommendation, not an argument against a
   second X receipt. X2 would not make the split significant; it would halve
   the sampling error on X's *own* mean, which currently rests on a single
   draw. I had no competing use for my fourth authorised slot — no new
   mechanism is built, and recommendation 6 says the obvious next one should
   be re-priced before it is written — so X2 was strictly better than nothing.
   **It did not land.** I attempted it three times over the closing hour and
   every attempt returned `account already has 1 submission(s) in flight`; the
   limit is per *account*, not per student, and a sibling held the slot
   throughout. The tree is committed at `6d14ed9` and the note is
   `research/nezuko-part1a-note.md`, so it is one command for whoever has the
   slot next. If it lands, recompute the `X − C0` and `Y − X` rows before
   anyone quotes the 39% figure.
9. **Adopt the `unique`/`issued` declaration rule** for byte-arm briefs.

## Appendix — the survivor-census patch

Not in any submitted archive. Applied to `Sources/MLXFastModel/
LagunaLmHeadPrune.swift` on a scratch branch, built with `swift build -c
release --force-resolved-versions`, and run as

```bash
DARKBLOOM_LMHEAD_PRUNE_STATS=1 research/run_local_benchmark.sh --local-iterate
```

`--local-iterate` is required rather than the cheaper `correctness` command:
the runtime worker is launched under a seatbelt profile containing
`(deny file-write*)` with only `/dev/null` allowed, so a diagnostic cannot
write a file, and only `benchmark --local-iterate|--local-submit` passes
`forwardsWorkerStderr: true`. Every other CLI path installs
`emit: { _ in }` and discards worker stderr. Worth knowing before anyone else
spends thirty minutes on it.

```swift
// near the other DARKBLOOM_ flags
private let lagunaLmHeadPruneStatsEnabled =
    ProcessInfo.processInfo.environment["DARKBLOOM_LMHEAD_PRUNE_STATS"] == "1"
private nonisolated(unsafe) var lagunaLmHeadPruneStatsCalls = 0

// in logits(), after `thr` is built and before the `assembled` dispatch
if lagunaLmHeadPruneStatsEnabled {
    let live = (coarse + delta.asType(.float32)) .>= thr
    let survivors = live.asType(.int32).sum()
    let liveBlocks = live.reshaped([vocab / 4, 4]).any(axis: 1)
        .asType(.int32).sum()
    eval(survivors, liveBlocks)
    lagunaLmHeadPruneStatsCalls += 1
    let line =
        "mlxfast: lmhead prune stats call=\(lagunaLmHeadPruneStatsCalls)"
        + " survivors=\(survivors.item(Int32.self))"
        + " live4blocks=\(liveBlocks.item(Int32.self))"
        + " of \(vocab / 4) refine=\(refine)\n"
    FileHandle.standardError.write(Data(line.utf8))
}
```

The expression is the kernel's own screen (`LagunaLmHeadPrune.swift:675`,
`coarse[r] + float(delta[r]) >= thr[0]`) lifted to the host, so it counts
exactly the rows the kernel's `base_mask` sets. It forces a host sync per
call, so the timings from a run with it enabled are meaningless and were
discarded; only the counts were used.

Survivor counts are a numerical property of the logit distribution, not a
timing property, so this M4 measurement transfers to M5 exactly. It is
prompt-dependent, and the hidden M5 prompts are not these prompts, so the
mean could differ; the conclusion only needs it to be small enough that the
re-read is a rounding error, and at 171 KB against 25.69 MB there are two
orders of magnitude of margin.
