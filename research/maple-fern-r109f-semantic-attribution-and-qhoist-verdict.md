# r109-F — semantic attribution, the QHOIST verdict, and the fork-main A/B

Campaign r109-F (`maple-r109-f-integration-and-submission`, revision
`r109-f-rev2`), student **maple-fern**.

This document supersedes three claims made earlier tonight. Each superseded
claim is named explicitly below so the record is auditable.

---

## 1. Headline: `DARKBLOOM_ATTN_QHOIST=1` is a −1.36 % regression, and one receipt proved it

Ticket 3 (`e4078827-c7fd-4173-a2bf-2f6af7cc6e73`, created
2026-08-11T00:00:00.289Z) flipped the `DARKBLOOM_ATTN_QHOIST` compile-time
default from 0 to 1 in three files. It is now terminal: **rejected**, reason
`score did not improve current best`, published **2.52713571388054**.

The receipt ledger for our executable classes, with `normalized =
(REF_D/decode)^0.75 × (REF_P/prefill)^0.25`, `REF_D = 0.01385621216015625`,
`REF_P = 0.00036751938916015626`:

| ticket | id | decode µs | prefill µs | normalized | draw | published |
|---|---|---:|---:|---:|---:|---:|
| 1 | `c1c0ba2c-ec1c-43f4-92bb-3c5b8b0a76e9` | 4932.4 | 187.69 | 2.566844 | 1.001130 | 2.569744 |
| 2 | `88584270-140e-4f28-a924-b00c77b1becd` | 4932.6 | 187.65 | 2.566903 | 1.011244 | 2.595765 |
| 3 | `e4078827-c7fd-4173-a2bf-2f6af7cc6e73` | 4948.5 | 196.30 | **2.532027** | 0.998068 | 2.527136 |

Ticket 3 versus ticket 1, per leg:

- decode **+16.1 µs/token (+0.327 %)**
- prefill **+8.61 µs/token (+4.586 %)**
- normalized **−1.3564 %**

QHOIST hurt *both* legs. The prefill damage is the larger share, which is
consistent with the knob living in the NAX attention kernel where prefill does
its bulk work.

### Attribution is airtight, not inferred

`research/fern_r109f_semantic_diff.py pkg-t2 pkg-t3` — comment- and
whitespace-invariant diff over the two official package trees:

```
file                                                         +sem   -sem |    +raw    -raw
...swift/Source/Cmlx/mlx/mlx/backend/metal/jit_kernels.cpp       2      2 |      10       2
.../metal/kernels/steel/attn/kernels/steel_attention_nax.h       1      1 |       6       4
...swift/Source/Cmlx/mlx-generated/steel_attention_nax.cpp       1      1 |       7       5
TOTAL                                                            4      4 |      23      11
```

**Four semantic lines, three files, and they are exactly the QHOIST flip.**
Nothing else changed between the two measured executables. There is no
confound to argue about: the −1.3564 % normalized delta is caused by those
four lines.

### This is the resolution claim, demonstrated

Earlier tonight I argued from a same-executable control pair (`pkg-t1` /
`pkg-t2`, which differ only by a 4-line comment) that the *normalized*
statistic has a spread of **0.0020 %** where the *published* score has
**1.0126 %**, so one receipt suffices to resolve an arm that published score
would need ~470 receipts to see.

Ticket 3 is that claim used in anger. The signal is **−1.3564 %**, i.e.
**678× the same-executable normalized noise band**. Meanwhile the *published*
scores were 2.569744 → 2.527136, a −1.66 % move that is only 1.6× the
control pair's published spread of 1.0126 % — by published score alone this
would have been a one-sigma shrug. The draw for ticket 3 was 0.998068,
below the mean, so published score *overstated* the damage and would have
mixed the code effect with luck. The normalized statistic separated them.

**Action taken: the QHOIST flip is reverted on the integration branch.** It is
not a candidate for any stacked submission.

### Note on the compile gate

The pre-flight evidence in `research/maple-fern-r109f-qhoist-compile-gate.md`
was correct and remains correct: the flipped default provably reached the
compiler (`-D…=0` → 285,968 B of `.air`, `=1` → 288,288 B, and the ordinary
build produced 288,288 B). A green compile gate proved the change was *live*.
It said nothing about whether the change was *good*, and the change was not
good. The gate did its job; I over-read it as encouragement.

---

## 2. Superseded claim: "we dropped 5,213 lines of fork main"

`git diff --stat 1bc1c895..HEAD -- Sources Vendor` reports **+2382 / −5213**,
which I first read as our branch having deleted a large amount of upstream
work.

That reading is an artifact. `git log 1bc1c895..HEAD` contains commit
`f720e9e7`, *"r99-B rung 1: reclaim 176,468 editable bytes from vendored
comment content"* — a deliberate comment-stripping pass run to buy editable-byte
budget.

Two tools were built to measure the real churn:

- `research/fern_r109f_comment_fraction.py` classifies lines. Verdict:
  **+342 / −206 code, +2040 / −5007 comment or blank; 96.0 % of deletions are
  comment or blank.**
- `research/fern_r109f_semantic_diff.py` lexes `//` and `/* */` out (string-
  and char-literal aware), normalises whitespace, then diffs. This is needed
  because the same pass stripped *inline* comments from otherwise-unchanged
  lines, e.g. `int64_t C_batch_stride /* = 0*/,` → `int64_t C_batch_stride ,`
  and `} // namespace` → `}`. A line-level classifier still over-counts those.

**True semantic delta `1bc1c895 → 66e6bbce` over `Sources` + `Vendor`:
+63 / −16 lines across 5 of 30 touched files — 1.0 % of the raw churn.**

| file | +sem | −sem |
|---|---:|---:|
| `Sources/MLXFastModel/LagunaRuntimeModel.swift` | 43 | 12 |
| `Vendor/…/backend/metal/quantized.cpp` | 16 | 0 |
| `Vendor/…/backend/metal/jit_kernels.cpp` | 2 | 2 |
| `…/steel/attn/kernels/steel_attention_nax.h` | 1 | 1 |
| `…/mlx-generated/steel_attention_nax.cpp` | 1 | 1 |

The last three are the QHOIST flip now being reverted. The `quantized.cpp`
addition is a `darkbloom_expert_down_bn()` env reader **defaulting to 64**,
i.e. a no-op at default, gated behind a predicate that requires `M >= 64` and
therefore cannot touch decode at all. `matmul.cpp`, `sdpa_vector.h`,
`rms_norm.metal`, `arg_reduce.metal`, `Evaluate.swift`, `KVCache.swift`,
`CompiledDecode.swift`, `BatchKVCache.swift` and all 25 other touched files are
**comment-only, zero semantic change**.

---

## 3. Superseded claim: "our 59-line delta is the regression"

Having found the real delta was ~59 semantic lines — chiefly a router weight
prefetch in `LagunaRuntimeModel.swift` — the natural next hypothesis was that
those lines caused the 41.9 µs/token decode deficit we carry against
same-day official receipts. I tested it directly instead of arguing about it.

`research/fern_r109f_ab_rebuild.sh` builds the metallib, builds the runtime
worker, runs `benchmark.sh --local-iterate`, and archives the score, holding
every harness file at the branch revision so `harness_hash` inputs outside
the model are constant.

Arm: scratch branch `fern-r109f-ab-forkmain`, `Sources` and `Vendor` reverted
wholesale to fork main `1bc1c895`.

| arm | decode s/tok | vs HEAD |
|---|---:|---:|
| HEAD `17868864` | 0.012953359 | — |
| fork main `1bc1c895` | 0.012990220 | **+0.28 % (slower)** |

Both arms: `passed_correctness: true`, identical `golden_hash`
`b9509697c08a2cf3…`. Local decode repeatability on this host is 0.05–0.1 %
(measured: two runs of the same executable moved decode by +0.1 %), so
+0.28 % is a real ordering.

**Our branch delta is a small net gain over fork main, not a regression.**
The hypothesis is dead. Whatever the fast packages have, fork main never had
it either — so the deficit is work we are *missing*, not damage we *did*.

### Harness-hash caveat, resolved

The two arms report different `harness_hash`. This is not a protocol
difference. `harnessHash()` at
`Sources/MLXFastHarness/LagunaRuntimePreflight.swift:44` hashes the entire
`Sources` tree, model code included, so reverting the model necessarily moves
it. The measurement code itself is byte-identical across the arms:

```
git diff --stat 1bc1c895 66e6bbce -- Sources/MLXFastHarness \
    Sources/MLXFastTrustedHarness Sources/MLXFastCore \
    benchmark.json benchmark.sh tools Package.swift
```

is empty.

---

## 4. Where the deficit actually is

`research/fern_r109f_decode_regime.py` buckets all 1230 full-leg receipts by
UTC day and reads the runner's *own* baseline decode leg, which is the only
host thermometer available in the receipt stream.

- **The host is stable.** Baseline decode median per day spans
  13834.3–13883.0 µs and the per-day minimum spans 13780.7–13821.4 µs across
  all 18 days — a **0.35 % total range**. There is no host regime step.
- **The candidate frontier moved and then stopped.** Per-day `cand_min` fell
  monotonically 12149.5 µs (07-24) → 4886.0 µs (08-08) and has been flat for
  four days: 4886.6 (08-07), 4886.0 (08-08), 4893.7 (08-09), 4890.7 (08-10).
  Nobody has moved the true frontier since 08-07.
- Host-normalised, `cand_min / base_med` went 0.87822 → 0.35306. All of the
  field's improvement is candidate-side.
- **On 2026-08-10** (n=23, 4 solvers) `cand_min` was 4890.7, p10 4904.4,
  **median 4916.6**. Our two receipts that day were **4932.4 and 4932.6 —
  worse than the day's median.**

So the ~0.86 % / 41.9 µs decode gap is code, measured against contemporaneous
packages on a demonstrably stable host.

### The feature contingency table, and why the obvious answer is wrong

Signatures: atlas-v3 = `hidden_vectors_out[lane + 128]`; prefetch =
`lagunaRouterWeightPrefetch`.

| ref | cand decode µs | normalized | atlasV3 | prefetch |
|---|---:|---:|:-:|:-:|
| `1bc1c895` fork main | — | — | 0 | 0 |
| `pkg-t1` | 4932.4 | 2.566844 | 0 | 1 |
| `pkg-t2` | 4932.6 | 2.566903 | 0 | 1 |
| `pkg-e27f1ce` | 4890.7 | 2.582263 | **1** | 0 |
| `pkg-25e1f18` | 4894.1 | 2.582070 | 0 | 1 |
| `66e6bbce` ours | — | — | 0 | 1 |

**Neither single feature separates the fast pair from the slow pair.**
`pkg-25e1f18` is fast while carrying prefetch and *not* carrying atlas v3, so
prefetch is not the culprit and atlas v3 is not the sole cause. A specific
sub-hypothesis was also refuted directly: `lagunaRouterWeightPrefetch`
defaults to **1** in `pkg-t1` *and* in the fast `pkg-25e1f18` (25e1f18 merely
widens the accepted set from `[0,1,5]` to `[0,1,2,3,4,5]`), and
`lagunaRouterRowsPerGroup` defaults to 8 in all three. Prefetch is active in a
fast package.

Per the r111 attribution rule I make no authorship claim on `5c542169`
(`pkg-e27f1ce`) or `4b0e051b` (`pkg-25e1f18`). They are used here purely as
*measured public executables* with fetchable trees, which is all the argument
needs.

### The one decode-path difference that is testable

The whole comment-invariant delta `pkg-t1 → pkg-e27f1ce` is **+26 / −67 lines
over two files**: `LagunaRuntimeModel.swift` (+26/−51) and `quantized.cpp`
(+0/−16). The `quantized.cpp` part is the prefill-only `M >= 64` gather-GEMM
guard. On the decode path exactly two things differ, and one of them is an
8-line kernel change — the embedding+RoPE atlas kernel:

- ours: `laguna_decode_embedding_rope_atlas_bf16_2048_v2`, `constexpr uint
  hidden_vectors = hidden_size / 4`, one guarded store
  `if (lane < hidden_vectors) hidden_vectors_out[lane] = …`, dispatch
  `grid:(512,1,1) threadGroup:(512,1,1)`
- theirs: `…_v3_tg128`, no `hidden_vectors`, four unguarded stores at `lane`,
  `lane+128`, `lane+256`, `lane+384`, dispatch
  `grid:(128,1,1) threadGroup:(128,1,1)`

Both cover the same 512 vec4 stores (`hidden_size` 2048 / 4 = 512); v2's guard
is dead code at its own geometry. The suspected mechanism is threadgroup
sizing — 512 threads is 16 co-resident SIMD groups where 128 is 4. The guard
removal is only sound at exactly 128 lanes, so geometry and guard must move
together, and `passed_correctness` / `golden_hash` are the gate.

That arm (`fern-r109f-ab-atlasv3`, commit `4e5aaf6b`) is measured in §5.

---

## 5. Arm ledger

Reproduce with `python3 research/fern_r109f_ab_table.py`. All four arms return
`passed_correctness: true` and the *same* `golden_hash b9509697c08a2cf3…`, so
every row below is a bit-exact variant of the same model.

| arm | branch / job | atlas | prefetch | decode s/tok | Δ vs HEAD | Δ µs |
|---|---|:-:|:-:|---:|---:|---:|
| HEAD baseline | integration @ `17868864` | v2 | 1 | 0.0129533590 | — | — |
| atlas `v3_tg128` | `fern-r109f-ab-atlasv3` @ `4e5aaf6b` | **v3** | 1 | **0.0129499915** | **−0.0260 %** | **−3.37** |
| atlas v3 + prefetch=0 | job `f621d5c1` (env knob) | v3 | **0** | 0.0129673988 | +0.1084 % | +14.04 |
| fork main `1bc1c895` | `fern-r109f-ab-forkmain` @ `8fdfb2a1` | v2 | 0 | 0.0129902204 | +0.2846 % | +36.86 |

Baseline artifact:
`research/artifacts/fern-r109f/score.head-17868864.local-iterate.json`.
Arm artifacts: `research/artifacts/fern-r109f/ab/score.<label>.json`.

Local host is much slower than the ranked host (decode 12953 vs 4932 µs =
2.63×; prefill 1122 vs 187.6 µs = 6.0×) while using the same official
`REF_D`/`REF_P` constants, so local absolute scores are meaningless and only
*within-host arm ordering* is used above.

### 5.1 atlas v3_tg128 result — exact, and the best of the four arms

`v3_tg128` is **−3.37 µs (−0.0260 %)** against HEAD. Local decode
repeatability is 0.05–0.10 %, so this is *inside* the noise band: v3 is not a
measurable win locally, but it is also demonstrably not a loss, and it is
byte-identical in kernel body to `pkg-e27f1ce`, the fastest non-maple package
in the receipt stream (4890.7 µs). The patch is four edits in
`Sources/MLXFastModel/LagunaRuntimeModel.swift`: kernel name `…_v2` →
`…_v3_tg128`; delete `constexpr uint hidden_vectors = hidden_size / 4;`;
replace the guarded single store with four unguarded stores at
`lane`/`+128`/`+256`/`+384`; and shrink the dispatch from `(512,1,1)/(512,1,1)`
to `(128,1,1)/(128,1,1)`. It is promoted because it is free locally, exact, and
the only structural difference to the fast package that we can actually test.

### 5.2 The 2×2 closes the router-weight-prefetch question: keep the default at 1

The two candidate discriminators against `pkg-e27f1ce` were the atlas kernel
version and `lagunaRouterWeightPrefetch`
(`Sources/MLXFastModel/LagunaRuntimeModel.swift:696`, accepted set `[0,1,5]`,
our default `1`; `pkg-e27f1ce` has no prefetch at all). Holding atlas at v3 and
flipping only the env knob costs **+17.41 µs (+0.134 %)**, i.e. turning
prefetch *off* is roughly 2× the repeatability band **slower**. The fork-main
corner (v2, prefetch 0) is +36.86 µs, so the two effects are not additive —
fork main carries the other 59 semantic lines of §2 as well — but the sign is
unambiguous in both rows that vary prefetch.

**Consequence:** matching `pkg-e27f1ce` by *deleting* our prefetch would make
us slower, not faster. The 41.9 µs ranked-host decode deficit of §4 is
therefore **not** explained by either axis of this 2×2. Since `_nax` is
permanently off on this M4 host, the remaining live hypothesis is that
`pkg-e27f1ce`'s advantage lives in a NAX-only path that local A/B is blind to
— which is exactly what the arm factories (#692 A2 fused-NAX `bn` 128→64,
#693 `_nax` register-prefetch port) are built to reach.

---

## 6. Method notes worth keeping

1. **A green compile gate is not a green result.** Ticket 3 had airtight
   evidence that the flag reached the compiler and still lost 1.36 %.
2. **Normalize before you interpret.** Ticket 3's published score fell 1.66 %,
   which is inside the range a same-executable pair can produce by luck alone.
   The normalized statistic showed −1.36 % against a 0.0020 % noise band.
3. **Diff semantically before you theorise.** A +2382/−5213 raw diff was
   +63/−16 real lines. Two nights of "we deleted upstream work" reasoning
   rested on a comment-stripping commit.
4. **Test the host hypothesis with the runner's own baseline leg.** It is a
   free thermometer embedded in every receipt and it said the host never moved.
5. **Refute with a build, not an argument.** The fork-main A/B took one
   scratch branch and 147 s and killed the leading hypothesis.
