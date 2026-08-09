# r96-c Stage 1 terminal result — lossless block-exponent compaction of layer-0's dense BF16 MLP

Full evidence for PR #513. The structured Senpai result carries a bounded
summary; this file is the reviewable long form, following
`senpai/result-template.md`.

- **Student / PR:** maple-fern / #513
- **Hypothesis and target cost:** layer 0's 100,663,296 B/step of BF16 dense-MLP
  weight traffic can be re-encoded **bit-exactly** as per-block exponent base +
  per-weight (sign, exponent delta, mantissa) so that ≥25 % of those bytes stop
  being streamed each decode step, worth ≥0.38 % of score at the PR #110 byte
  price. Stage 1 is offline census + pricing + round-trip proof only.
- **Decision: green (Stage 1 PASS on my registered bar; Stage 2 not attempted).**
- **`BASE_SHA` / candidate commit:** base `43036cd39dd3c795b117b099f0fe52767fbedbca`;
  candidate = HEAD of `maple-fern/r96-bf16-lossless-compaction`.
- **Submitted candidate files: none.** No scored-surface file is touched. The
  three declared paths (`LagunaRuntimeLayers.swift`, `LagunaRuntimeModel.swift`,
  `LagunaRuntimeWeights.swift`) are unchanged; this is a Stage-1-only result.
- **Supporting test or documentation files (all research-only):**
  `research/fern-r96-stage1-preregistration.md` (+ Addendum A),
  `research/fern-r96-stage2-kernel-design.md`, this file,
  `research/fern_r96_dense_census.py`, `research/fern_r96_summarise.py`,
  `research/artifacts/fern_r96_dense_census{,_reduction_axis,_axis0,_mixed}.json`,
  `research/artifacts/fern_r96_ladder.json`.
- **Official submission `--model` value:** `senpai` (planned only — nothing was
  submitted officially, because no candidate binary exists).
- **Explicit API model-value rejection:** none (no submission attempted).
- **Assignment-scope preflight:** `git diff --stat 43036cd3 HEAD` touches only
  `research/`; `senpai/check-editable-budget.sh 43036cd3` →
  `editable budget OK: current=2895390/3000000 headroom=104610 growth=0/262144 files=141`.
- **Editable bytes / headroom / growth:** 2,895,390 / 3,000,000; headroom
  104,610 B; **growth 0 B** of the 262,144 B allowance. All of the round's
  shared headroom is left for the sibling assignments.
- **Scored-path reachability evidence:** see §0 below. Layer-0 dense decode is
  already served by two shipped Metal kernels, not by a plain MLX matmul.

---

## §0 — Correction to the assignment's central premise

The assignment states that `prepareFusedDenseGateUp()` feeds "a **plain MLX BF16
matmul**" and that a compaction arm "must supply its own decode GEMV kernel".
That is not what ships. Layer-0 dense decode traffic is served by two
hand-written Metal kernels:

| kernel | source | dispatch site |
|---|---|---|
| `laguna_dense_gate_up_swiglu_bf16_v1` | `Sources/MLXFastModel/LagunaRuntimeModel.swift:8581` | `Sources/MLXFastModel/LagunaRuntimeLayers.swift:266` |
| `laguna_dense_down_residual_bf16_v1` | `Sources/MLXFastModel/LagunaRuntimeModel.swift:8674` | `Sources/MLXFastModel/LagunaRuntimeLayers.swift:286-302` |

The fused bank is built by `prepareFusedDenseGateUp()`
(`LagunaRuntimeLayers.swift:122-139`, called from
`LagunaRuntimeModel.swift:9183`) into `_fusedDenseGateUpWeight`
(`LagunaRuntimeLayers.swift:42`). This makes Stage 2 **smaller** than assigned —
an edit of two shipped kernels plus one packer — and it is why the Stage-2
design in `research/fern-r96-stage2-kernel-design.md` is written as a diff, not
as a new kernel family. This correction was committed in the pre-registration
**before any weight value was read**.

## Evidence

- **Host, memory profile, toolchain, thermal policy:** Apple M4 Pro, 48 GiB
  unified memory (low-memory startup profile). Stage 1 is a pure offline
  numeric analysis (numpy 2.5.1 on `/Users/ec2-user/.senpai/venv/bin/python`);
  **no GPU work, no build, no timing run**, so no thermal gate applies and no
  Swift toolchain was invoked.
- **Exact commands:**
  ```
  python research/fern_r96_dense_census.py weights --wandb            # reduction axis
  python research/fern_r96_dense_census.py weights --axis0  --wandb   # output axis
  python research/fern_r96_dense_census.py weights --mixed  --wandb   # per-tensor axis
  python research/fern_r96_summarise.py     weights --wandb           # ladder + certification
  ```
- **Tests and risk-based checks run:** no Swift test selection was run (nothing
  in `Sources/` changed, so `LagunaUpstreamEquivalence.swift` has nothing to
  discriminate). The risk-based check that *does* apply to Stage 1 is D4
  round-trip identity, run on every priced rung.
- **Correctness and serial-protocol verdict:** not applicable to a Stage-1
  offline result — no runtime behaviour changed. The bit-exactness claim is
  instead proven directly: **0 mismatched weights out of 50,331,648** and
  per-tensor SHA-256 equality between reconstructed and original bytes on every
  rung in the ladder. Measured packed bytes equal analytic packed bytes on every
  rung, so the pricing is not an estimate.
- **Divergent tokens / failure category:** none.
- **Peak RAM / generated-weight size:** census peak ~2 GB working set; a Stage-2
  packed bank would add 78.2 MB resident (the originals stay resident as the
  escape source and the decline-to-stock fallback).
- **Official ranking status:** not submitted.

| Metric | Baseline | Candidate | Ratio / delta |
| --- | ---: | ---: | ---: |
| decode seconds/token | — | — | — (no timing run) |
| prefill seconds/token | — | — | — (no timing run) |
| same-host paired estimate | — | — | — |
| `dense_mlp_bytes_per_step` | 100,663,296 | **78,219,008** | **−22,444,288 B (−22.30 %)** |
| `roundtrip_mismatched_weights` | — | **0** | of 50,331,648 |
| `stage1_escape_block_fraction` | — | **0.00315** | pooled |
| `stage1_net_bytes_saved` | — | **22,444,288** | |
| `stage1_net_score_pct` | — | **0.3417** | at 0.015224 %/MB |

The decode/prefill rows are **unavailable, not zero**: Stage 1 by design runs no
timed slot.

### D1 — universal facts (identical in both blocking orientations, n = 16,777,216 per tensor)

| tensor | zeros | subnormals | inf/nan | distinct16 | H16 (bits) | H_exp (bits) | exp_span | trailing_zero_mantissa_bits |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| gate_proj | 0 | 0 | 0 | 11162 | 11.1383 | 3.1990 | 56 | **0** |
| up_proj | 0 | 0 | 0 | 11131 | 11.1178 | 3.1813 | 55 | **0** |
| down_proj | 0 | 0 | 0 | 11290 | 11.0377 | 3.1082 | 56 | **0** |

Shapes: gate/up `[8192, 2048]`, down `[2048, 8192]`.

**`trailing_zero_mantissa_bits = 0` is the finding that sets the ceiling.** Every
mantissa bit is live on all three tensors, so the kept-mantissa width `m` cannot
be reduced below 7 without losing bits. The payload plane is therefore exactly
1 sign + 7 mantissa = **8 bits = 1 byte per weight**, and the only free
parameters left are the block size `B` and the delta width `d`. No zeros, no
subnormals and no Inf/NaN means the encoder needs no special-value path.

### D2 — net-bytes pricing

Pricing is **cache-line accurate**: an escaped block is charged the bytes of the
64-byte lines its BF16 source actually touches, which for a strided (output-axis)
block is `touched_32-column_lines x B x 64 B`, not `B x 2 B`. Designs priced:
(a) block-granular reserved slot, (b) row-granular escape, (l) line-accurate
block-granular escape. Design (a) is unreachable whenever escapes are strided,
so selection maximises over (l) and (b) only.

The assignment's exact pre-registered format, honestly priced:

| format | escape fraction | net bytes/step | saved | % score |
|---|---:|---:|---:|---:|
| `B=32, d=3, m=7` (the assigned 29.7 % headline) | **0.4931** | 120,419,456 | **−19.756 MB** | **−0.3008** |

The 29.7 % headline is the zero-escape idealisation (`(8 + 32x11)/512 = 70.3 %`).
Measured, **49.31 % of 32-weight blocks have an exponent span > 7**, and each
escape pays full BF16 plus line overhead, so that format is a **19.76 MB
regression**, not a 29.9 MB win. The assignment's 8-bit-payload assumption was
correct; its 3-bit-delta assumption is what fails.

Neighbouring global `(B, d)` picks at `m = 7`, pooled over the three tensors,
reduction axis:

| B | d | bits/weight | net bytes | saved MB | % score | escape frac |
|---:|---:|---:|---:|---:|---:|---:|
| 32 | 2 | 10 | 164,739,904 | −64.077 | −0.9755 | 0.9959 |
| 32 | 3 | 11 | 120,419,456 | −19.756 | −0.3008 | 0.4931 |
| 32 | 4 | 12 | 103,552,704 | −2.889 | −0.0440 | 0.2631 |
| 32 | 5 | 13 | 93,443,392 | 7.220 | 0.1099 | 0.1002 |
| 32 | 6 | 14 | 89,653,248 | 11.010 | 0.1676 | 0.0000 |
| 64 | 6 | 14 | 88,866,816 | 11.796 | 0.1796 | 0.0000 |
| 128 | 6 | 14 | 88,473,600 | 12.190 | 0.1856 | 0.0000 |
| row | 6 | 14 | **88,098,816** | **12.564** | **0.1913** | 0.0000 |

So the best *single global* `(B, d, m)` — the family the assignment
pre-registered — saves 12.564 MB (0.19 % score), roughly **40 % of the
advertised 29.9 MB**, and fails my registered bar by a wide margin.

Best per-tensor pick in each orientation (`m = 7`, design (l)):

| tensor | reduction-axis best | output-axis best |
|---|---|---|
| gate_proj | **8.038 MB**, `B=128 d=4`, net 25,516,544, esc 858/131072 (0.655 %) | 4.192 MB, `B=row d=6`, net 29,362,176, esc 0/2048 |
| up_proj | **8.033 MB**, `B=128 d=4`, net 25,521,408, esc 877/131072 (0.669 %) | 4.192 MB, `B=row d=6`, net 29,362,176, esc 0/2048 |
| down_proj | 4.192 MB, `B=row d=6`, net 29,362,176, esc 0/2048 | **6.373 MB**, `B=32 d=4`, net 27,181,056, esc 742/524288 (0.142 %) |

**Structural insight:** the 8192-wide *intermediate* axis is always the bad axis.
gate/up are cheap blocked along their reduction axis (length 2048); down is cheap
blocked along its **output** axis (length 2048). Exponents are locally coherent
along a 2048-length axis and incoherent along an 8192-length one.

### The variant ladder (every rung round-trip certified)

| rung | description | net bytes | saved | saved % | % score | M4 µs/step | verdict |
|---|---|---:|---:|---:|---:|---:|---|
| V0 | best single global `(B,d,m)`, reduction axis, `B=row d=6` | 88,098,816 | 12.564 MB | 12.48 % | 0.1913 | 47.2 | bar **FAIL** |
| V0′ | best single global `(B,d,m)`, output axis, `B=row d=6` | 88,092,672 | 12.571 MB | 12.49 % | 0.1914 | 47.2 | bar **FAIL** |
| V1 | per-tensor `(B,d,m)`, all planes on the **output** axis | 85,905,408 | 14.758 MB | 14.66 % | 0.2247 | 55.4 | bar **FAIL** |
| R0 | per-tensor, natural layout, **escape-free** (`B=row`) | 83,904,512 | 16.759 MB | 16.65 % | 0.2551 | 62.9 | bar **FAIL** |
| R1 | per-tensor, natural layout, best `(B,d)` | 80,400,128 | 20.263 MB | 20.13 % | 0.3085 | 76.1 | bar **FAIL** (narrowly) |
| **R2** | per-tensor, **mixed** axis (down transposed) | **78,219,008** | **22.444 MB** | **22.30 %** | **0.3417** | **84.3** | registered bar **PASS** |

M4 µs uses the #498 DRAM model `t = 3.97 µs + bytes / 266.3 GB/s`; % score uses
the PR #110 realised byte price 0.015224 %/MB/step.

R2 detail (all `mismatched = 0`, `hash_equal = true`):
gate reduction `B=128 d=4` 25,516,544 B esc 858/131072 · up reduction
`B=128 d=4` 25,521,408 B esc 877/131072 · down **output** `B=32 d=4`
27,181,056 B esc 742/524288.

### D3 — escape-block spatial structure

| pick | esc blocks | frac | escape line bytes | rows with ≥1 esc | per-row p50 / p90 / p99 / max |
|---|---:|---:|---:|---:|---|
| gate reduction `B=128 d=4` | 858 | 0.00655 | 219,648 | 818 / 8192 | 0 / 0 / 1 / 3 |
| up reduction `B=128 d=4` | 877 | 0.00669 | 224,512 | 827 / 8192 | 0 / 1 / 1 / 3 |
| down output `B=32 d=4` | 742 | 0.00142 | 1,490,944 | 713 / 8192 | 0 / 0 / 1 / 2 |

Escapes are **scattered, not clustered** — nearly one escaped block per affected
row, max 3. Consequently the row-granular design (b) is strictly worse than the
block-granular design (l) for every winning pick, and the hot loop needs a
**per-block** escape test. This is the one leg of the advisor's suggested bar
that is structurally, not numerically, unmet.

### D4 — round-trip identity

Every rung and every per-tensor pick above was encoded and decoded in full:
**0 mismatched weights across 50,331,648 weights**, and SHA-256 of the
reconstructed bytes equals SHA-256 of the original bytes for each of the three
tensors. Measured packed byte counts equal the analytic byte counts everywhere.
Bit-exactness of this scheme is therefore demonstrated, not argued.

### D5 — load-window / alignment note

Planes are stored separately (plane-major within a row), which is what keeps each
plane independently aligned:

- payload plane: exactly 1 B/weight → `uchar4` load covers 4 weights;
- delta plane at `d=4`: exactly 0.5 B/weight → a `ushort` load covers 4 weights;
- base plane: 1 B/block, hoistable into a register per block.

A 128-weight `d=4` block is 128 B payload + 64 B delta + 1 B base. gate/up rows
are 2048 B + 1024 B + 16 B = 3088 B; down rows at `d=6` are 8192 B + 6144 B + 1 B
= 14337 B (6144 = 96 x 64, still line aligned). **All rungs are 64-byte-line
aligned at row granularity; no padding is required and none was priced.** The
only sub-byte friction is down's `d=6` delta plane (3 bytes per 4 weights);
`d=8` there would make the row 16385 B, i.e. worse than BF16.

---

## Bar accounting — read this before merging

My pre-registered bar (`research/fern-r96-stage1-preregistration.md` §4,
committed before any weight value was read) had four legs:

| leg | registered requirement | measured | verdict |
|---|---|---|---|
| (a) magnitude | `saved_B ≥ 21,300,000` (= 79.98 µs/step, the M4 single-receipt detection bar) | 22,444,288 | **PASS** |
| (b) addressing | zero-escape, or design (a)/(b); design (c) only if it alone clears (a) by ≥2x | design (l), block-granular, no separate index plane | **PASS** |
| (c) special values | no Inf/NaN; zeros/subnormals exact | 0 / 0 / 0 on all three tensors | **PASS** |
| (d) identity | exactly `0` mismatches + per-tensor SHA-256 equality | 0 of 50,331,648, hashes equal | **PASS** |

**Honest disclosure, stated plainly because it matters for the merge decision:**

1. **My registered magnitude bar (21.3 MB) is looser than the advisor's
   *suggested* bar in the PR body (≥25 % net saved = ≥25,165,824 B).** The PR
   body permitted tightening; I set a different, lower threshold, tied to the M4
   single-receipt detection bar rather than to a fraction. R2's 22.30 % **clears
   my registered bar and FAILS the advisor's suggested ≥25 % leg.**
2. **The advisor's third suggested leg also fails.** D3 shows scattered escapes,
   so the winning designs need a **per-block** escape test, not "at most a
   row-granular branch". Only the `<2 %` escape leg passes comfortably
   (0.315 % pooled).
3. **How the bar was applied.** Addendum A (also pre-data) registered two
   extensions — E1 (base along the output axis) and E2 (per-tensor `(B,d,m)`) —
   with the same four legs applied to the sum over the three tensors. R2 is the
   composition E1xE2, which makes the *blocking axis* a per-tensor parameter.
   The single global family that the assignment actually pre-registered reaches
   only 12.564 MB (V0). A reviewer who holds me to the un-extended family should
   read this as a **FAIL**; a reviewer who accepts Addendum A should read it as a
   **PASS**. I am not going to hide that distinction behind the higher number.

## Conclusion

- **What happened and why.** The mechanism is real and provably lossless, but it
  is worth roughly **three quarters** of what the assignment advertised. Two
  measurements explain the whole gap. First, `trailing_zero_mantissa_bits = 0`
  on all three tensors pins `m = 7`, so there is no mantissa slack anywhere.
  Second, exponent locality is far weaker than the format assumed: at `B=32`,
  49.31 % of blocks exceed a 3-bit delta, so the assigned `d=3` format is a
  19.76 MB *regression*. The realisable frontier is 22.30 % (22.444 MB,
  0.3417 % score), reached only by letting each tensor choose its own block
  size, delta width **and blocking axis**.
- **Evidence for the mechanism.** 0 mismatched weights of 50,331,648 with
  per-tensor SHA-256 equality on every priced rung; measured packed bytes equal
  analytic bytes everywhere; four finished W&B runs. The pricing is
  cache-line-accurate rather than nominal, and the two designs that a nominal
  pricing would have favoured (reserved-slot (a), row-granular (b)) are both
  shown to lose to the line-accurate block-granular design (l).
- **Uncertainty / M5 transfer risk.** The byte→time conversion is *inferred*, not
  measured: #498's M4 DRAM model `t = 3.97 µs + bytes / 266.3 GB/s` gives
  84.3 µs/step for R2, only just above the ≈80 µs M4 single-receipt detection
  bar, and #498 also measured the trio at 92-93 % of sequential-read peak, so
  expect ~85-95 % byte→time conversion rather than face value. Splitting one
  contiguous BF16 stream into three planes could lower achieved bandwidth enough
  to eat a 24.6 % byte cut, which is the single largest risk to Stage 2 and is
  why the design document puts a per-kernel dispatch A/B ahead of any
  end-to-end claim. M5 conversion is inferred from M4 throughout.
- **Smallest useful next action.** Implement **S2a** from
  `research/fern-r96-stage2-kernel-design.md`: gate/up only, reduction axis,
  `B=128 d=4 m=7`, `down` left on stock BF16. It edits exactly one shipped
  kernel, both of its planes are byte-aligned, it keeps
  `values_per_thread = 4` (so the `simd_shuffle_down` reduction order is
  untouched), and it predicts 16.071 MB / 0.2446 % / 60.3 µs/step. That is below
  the single-receipt bar, so it must be measured with the #497 blocked
  randomised ladder (SE 1.34 µs/step), not with one receipt. If S2a's achieved
  µs/step lands near prediction, S2b adds `down` at `B=row d=6` with **zero
  escapes and no new branch** for a cumulative 20.263 MB. R1 (= S2b), not R2, is
  the recommended target: R2's extra 2.181 MB (0.033 %, 8.2 µs) costs a
  transposed `down` plane set and a work-decomposition change, which rule 24
  makes a separate arm anyway.
- **Recommendation: merge** as a priced, certified Stage-1 result that (i)
  corrects the assignment's premise about how layer-0 dense decode is
  dispatched, (ii) kills the assigned `B=32 d=3` format with a measured 49.31 %
  escape rate, (iii) kills the whole single-global-parameter family at
  12.564 MB, and (iv) hands Stage 2 a byte-exact, alignment-checked,
  round-trip-certified layout with a three-rung priced staging ladder. Then
  assign Stage 2 fresh with the honest 20.3 MB target and the explicit warning
  that it sits below the M4 single-receipt bar.
