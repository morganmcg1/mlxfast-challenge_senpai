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

### Local A/B — pending final arms

_(table filled from `/tmp/ab-m1/score.*.json`)_

| Metric | Control (single-pass) | Cascade (M1) | Delta |
| --- | ---: | ---: | ---: |
| `T` (pure decode step, ms) | | | |
| `S` (512-token prefill, ms) | | | |
| `decode_seconds_per_token` (ms) | | | |

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
