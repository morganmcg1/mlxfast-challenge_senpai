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

## Conclusion

_(completed once the official M5 family returns)_
