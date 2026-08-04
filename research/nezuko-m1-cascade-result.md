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

The brief authorises 4 receipts and asks for 3 on the byte-identical tip. I
spent **2 on a decomposition** instead. This is a deliberate deviation and here
is the justification.

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
| `X1` | X | pending | — | — | — | — | — |
| `X2` | X | pending | — | — | — | — | — |

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
2. **The negative control is clean.** `S` did not move. Nothing in this arm
   touches prefill, and nothing in prefill moved.
3. **The published score says nothing.** −0.383% ± 0.446% on the same data
   where the renormalised statistic reads +0.455% ± 0.136%. Had I ranked on
   `officialScore` I would have reported this arm as a mild *regression*. This
   is the sharpest single demonstration of the 3.3× instrument advantage I
   measured in #12, and it is on a real effect rather than on identical code.

## Conclusion

_(completed once `X1`/`X2` return)_

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
