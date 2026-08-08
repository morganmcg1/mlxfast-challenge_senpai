# R86-A rev2 — base-adoption gate result

Assignment `maple-r86-a-base-decode-regression`, revision `r86-a-rev2`, PR #460.

**Hypothesis H.** The adopted base at `7687c2e4` is correct, buildable, and
materially faster in decode than `f64456dd`.
**Null.** An advisor audit decision changed behaviour, or the byte reclaim broke
something the compiler did not catch.

Host: Apple M4 Pro, 20 cores, Apple GPU generation 16. This host **never selects
the `_nax` kernels**, so two of the eight adopted files are unreachable here.
Predictions were committed in `research/tanjiro-r86-base-gate-prereg.md` before
any measurement.

**Evidence index.** Harness `research/tanjiro-r86-base-gate.sh`; raw artifacts
`research/r86-gate-results/{new,old}-r{1,2,3}.{json,log}` and
`research/r86-gate-results/equivalence.log`; W&B run
[`k1t3wevm`](https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/k1t3wevm)
(`base-adoption-gate`, logged by `research/tanjiro_r86_base_gate_wandb.py`, so
the run summary and this note cannot drift apart).

---

## 1. What the adoption actually changed

`f64456dd..7687c2e4` touches exactly **8 editable paths** (plus research-only
files):

| path | changed lines | reachable on M4? |
| --- | ---: | --- |
| `Sources/MLXFastModel/LagunaRuntimeModel.swift` | 1435 | yes |
| `Sources/MLXFastModel/LagunaRuntimeWeights.swift` | 117 | yes |
| `Sources/MLXFastModel/LagunaLmHeadPrune.swift` | 5 | yes |
| `Vendor/.../MLXLMCommon/RoPEApplication.swift` | 1 | yes |
| `Vendor/.../metal/quantized.cpp` | 210 | yes |
| `Vendor/.../metal/matmul.cpp` | 33 | yes |
| `Vendor/.../mlx-generated/fp_quantized_nax.cpp` | 304 | **no** (gen 16) |
| `Vendor/.../metal/kernels/fp_quantized_nax.h` | 314 | **no** (gen 16) |

The gate harness flips exactly these 8 paths between arms. The per-arm
`surface=` hash differs between arms (`74ce56efdd2d` for `new`,
`343d60625c49` for `old`), which is the control proving the flip took effect
rather than silently re-timing one tree.

## 2. Byte budget and per-file cap

`senpai/check-editable-budget.sh 7687c2e4`:

```
current=2891343/3000000  headroom=108657  growth=0/262144  files=140
```

This matches the advisor's claim exactly. All 97 `editablePaths` exist and none
exceeds the 524,288 B per-file cap; the largest five are `matmul.cpp` 88,309,
`metal/quantized.cpp` 84,383, `mlx-generated/quantized.cpp` 81,561,
`quantized.h` 80,989, `gemv.cpp` 79,603.

## 3. Audit (a) — omitting the two transform metadata files

The advisor kept **our** `Sources/MLXFastTransform/Transform.swift` while not
adopting `AffineMetadataCoding.swift` and `TiedHeadMetadataCoding.swift`.

First correction to the framing: those two files **never existed in our tree at
all**. They are frontier-only additions (`c5b0a13`), absent at `HEAD`,
`f64456dd` and `7687c2e4`. So the risk was never a dangling symbol — that would
not compile. The real risk was a *producer/consumer* split: the adopted
frontier runtime expecting sidecars our older transform never writes.

**Static resolution.** In our whole tree there are **zero** references to
`AffineMetadataCoding`, `TiedHeadMetadataCoding`,
`mlxfast-projection-metadata`, or `mlxfast-tied-head-metadata` anywhere under
`Sources/` or `Vendor/`. At the frontier the only references are the two
defining files plus exactly two call sites, both inside `case .gemma4:` of a
`switch modelFamily`. The frontier's own header comment says the generator is
"Invoked only on the `.gemma4` transform family path".

The entire `Transform.swift` difference is two hunks confined to that sidecar
region. On the `.laguna` branch the frontier constructs empty reports
(`weightMap: [:]`, `tensorByteCount: 0`), and since
`tensorCount == weightMap.count == 0` and
`shardCount == (weightMap.isEmpty ? 0 : 1) == 0`, the frontier reduces term by
term to our code:

| frontier expression on `.laguna` | reduces to | our code |
| --- | --- | --- |
| `totalTensorByteCount + 0 + 0` | `totalTensorByteCount` | `outputTensorByteCount = totalTensorByteCount` |
| `[:].merging([:])` | `[:]` | `additionalWeightMap: [:]` |
| `copiedTensors + 0 + 0` | `copiedTensors` | `denseTensorCount: copiedTensors` |
| `textKeysByShard.count + 0 + 0` | `textKeysByShard.count` | `denseShardCount: textKeysByShard.count` |

**Empirical resolution.** The advisor asked for the arm to be exercised, not
merely compiled. `benchmark.sh` regenerates `weights/` behind a hash that
includes `Sources/MLXFastTransform`, so the transform is part of every scored
run. The produced checkpoint is a 20 GB pass-through: 912 tensors across 5
shards, `total_size = 21,561,408,512`, untied `lm_head.weight`, and **zero**
sidecar files or sidecar tensor names in `model.safetensors.index.json`. The
benchmark then loaded exactly that output and reproduced the expected golden
hash. Our `Transform.swift` is byte-identical (26,559 B) at `f64456dd`,
`7687c2e4` and `HEAD`, so this holds for both arms.

**Verdict (a): SAFE.** The omitted files are reachable only from the archived
`.gemma4` path. The ranked Laguna path is provably unchanged and is exercised
end to end. The only real loss is that our tree's archived Gemma arm cannot
emit sidecars — not a scored path.

## 4. Audit (b) — are the 8 kept files code-identical to the frontier's?

The advisor's method was a comment-stripped MD5. I re-verified independently
with three methods that *name* differences rather than merely detecting them
(`research/tanjiro_r86_code_identity_audit.py`,
`research/r86-code-identity-audit.log`):

- **A** Swift-aware lexer (line/block/nested comments, ordinary, multiline and
  `#`-raw strings) → normalised code-line diff. The lexer passes a 7-case
  self-test battery including `//` inside strings, nested `/* /* */ */`, `#if`,
  and division.
- **B** token-stream comparison, insensitive to line breaking and indentation.
- **C** per-line classification of the raw diff hunks, independent of the
  whole-file state machine.

| file | raw diff lines | code lines | tokens | verdict |
| --- | ---: | ---: | ---: | --- |
| `LagunaConfig.swift` | 7 | 954/954 | 6336/6336 | identical |
| `BaseConfiguration.swift` | 37 | 114/114 | 683/683 | identical |
| `BatchKVCache.swift` | 109 | 779/779 | 6036/6036 | identical |
| `CompilableKVCache.swift` | 57 | 170/170 | 1359/1359 | identical |
| `CompilableRotatingKVCache.swift` | 61 | 113/113 | 984/984 | identical |
| `CompiledDecode.swift` | 85 | 217/217 | 1528/1528 | identical |
| `Evaluate.swift` | 536 | 1299/1299 | 7979/7979 | identical |
| `KVCache.swift` | 258 | 1497/1497 | 11614/11614 | identical |

`raw_line_diffs_total=1150`, `CODE_IDENTITY=PASS`. Method C left 4 unproven
lines, all bare `}` in `KVCache.swift`; these are diff-alignment artefacts from
comment insertions shifting hunk boundaries, and methods A and B — which see
identical token sequences of length 11,614 — prove they cancel.

**Verdict (b): CONFIRMED.** All 1,150 raw line differences are comments,
blanks and whitespace. Zero code differences.

Bookkeeping correction: the advisor described the kept set as "8 MLXLMCommon
files + LagunaConfig". The true kept set is **7 MLXLMCommon files +
LagunaConfig = 8**; `RoPEApplication.swift` was the eighth MLXLMCommon file but
it was *adopted*, not kept.

## 5. Correctness gates

**Every one of the 6 arms passed**, and both trees produce the *same* output:

| | new (adopted, `7687c2e4`) | old (`f64456dd`) |
| --- | --- | --- |
| `passed` | True ×3 | True ×3 |
| `passed_correctness` | True ×3 | True ×3 |
| `checked_steps` | 130 ×3 | 130 ×3 |
| `golden_hash` | `b9509697c08a…` | `b9509697c08a…` |
| `harness_hash` | `38f6fd160c…` | `242af6faff…` |
| `peak_ram_gb` | 21 | 21 |
| surface SHA-256 (8 flipped paths) | `74ce56efdd2d` | `343d60625c49` |

`MLXFAST_LOCAL_ALLOW_GOLDEN_DRIFT` was left **unset** for the whole block, so
no override was in play. The two independent controls — differing `surface=`
hash *and* differing `harness_hash` — prove the flip really took effect and the
harness was not silently re-timing one tree; the identical `golden_hash` then
proves the two trees emit identical checked tokens.

### Upstream-equivalence oracle (adopted content)

`research/run_upstream_equivalence.sh` → `EQUIVALENCE_EXACT_STEPS=8`,
`EQUIVALENCE_EXIT=1`, 1 test executed in 42.849 s. **Non-zero test count
confirmed**, so this is a real oracle result and not the zero-selected-test
failure mode the wrapper exists to catch.

```
prefill    maximumAbsoluteLogitError 0.125  meanAbsoluteLogitError 0.011933609  5991 == 5991
decode-0..7  maximumAbsoluteLogitError 0    meanAbsoluteLogitError 0            all tokens equal
```

`EQUIVALENCE_EXIT=1` is **not** a regression from the adoption. The oracle
applies a zero tolerance to prefill, and the reported figures are a *digit-for-
digit* match to the pre-existing base signature this host has produced for many
rounds — `0.125` / `0.011933609` / token `5991 == 5991` / 8 exact decode steps
(`research/CURRENT_RESEARCH_STATE.md:3074`, `research/frieren-host-cpu-budget.md:471`,
`research/frieren-pr23-r2-cap.md:311`, `research/maple-fern-pr40-result.md:110`).
Because the adopted content reproduces that signature exactly rather than
merely "also failing", a separate old-base oracle control would add no
information and was not spent.

Scope limit, stated honestly: the oracle exercises shared paths only. It says
nothing about `fp_quantized_nax.cpp` / `fp_quantized_nax.h`, which this gen-16
host never selects.

## 6. Matched timing

ABBA order, one `--local-iterate` per arm, thermal gate honoured, single
model-holding process throughout. Time-ordered:

| time (UTC) | arm | decode µs/step | prefill µs/token |
| --- | --- | ---: | ---: |
| 21:16:17 | new | 12997.54 | 1125.03 |
| 21:21:28 | old | 12914.93 | 1115.54 |
| 21:24:55 | old | 12953.02 | 1112.87 |
| 21:29:45 | new | 12926.95 | 1137.26 |
| 21:33:13 | new | 12956.10 | 1122.39 |
| 21:37:59 | old | 13031.67 | 1139.03 |

Convention: **Δ = old − new**, so positive means the adopted base is faster.

| axis | old mean | new mean | Δ | pooled SD | 95 % CI | significant? |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| decode µs/step | 12966.54 | 12960.20 | **+6.34** | 49.00 | [−104.73, +117.41] | no |
| prefill µs/token | 1122.48 | 1128.23 | **−5.75** | 11.62 | [−32.09, +20.60] | no |

Both axes are a **null result**: the point estimates are 0.05 % and 0.51 % of
their means, both an order of magnitude inside the instrument.

Against the pre-registered 90 % intervals (committed before any rev2
measurement, `research/tanjiro-r86-base-gate-prereg.md`):

- decode: predicted **+200 µs/step [+30, +450]**, measured **+6.34** →
  **prereg MISS**. My prediction that the adoption is a visible decode win on
  M4 is falsified.
- prefill: predicted **+5 µs/token [−55, +65]**, measured **−5.75** →
  **prereg HIT** (I predicted the M4 prefill axis would be near-silent because
  the frontier's prefill work is concentrated in the two `_nax` files this host
  cannot execute).

**Instrument resolution and what it does *not* settle.** Pooled SD 49.0 µs at
n=3/arm resolves ±111 µs at 95 %. The ~38 µs/step figure in the rev1 assignment
premise is **below this instrument's floor** and this block neither confirms nor
refutes it. Resolving 38 µs at 95 % needs **12.8 reps/arm** (≈26 runs, ≈2 h of
exclusive host time); resolving 100 µs needs 1.8. A second 3+3 block would only
tighten ±111 → ±78 µs and would not change any decision, so I did not spend it.

## 7. Verdict

**The adopted base `7687c2e4` is GREEN as an integration base. Do not revert
it.** All four gate questions are discharged:

1. **Correctness** — 6/6 arms pass, 130 checked steps, and the adopted tree
   emits a `golden_hash` byte-identical to `f64456dd`'s. No drift override used.
2. **Numerics** — oracle exact on all 8 decode steps; the single prefill
   divergence is a digit-for-digit match to the long-documented pre-existing M4
   artefact, so the adoption introduced zero numerical change on any path this
   host can reach.
3. **Surface legality** — `current=2891343/3000000`, `headroom=108657`,
   `growth=0/262144`, all 97 `editablePaths` present, no file near the 524,288 B
   cap.
4. **Timing** — decode-neutral, Δ = +6.34 µs/step [−104.73, +117.41]. **A
   decode regression larger than ~105 µs/step (0.81 %) is excluded at 95 %.**

Both advisor audit decisions are independently confirmed rather than merely
re-asserted: **(a)** the two omitted transform-metadata files are reachable only
from the archived `.gemma4` branch, the ranked `.laguna` branch reduces term by
term to our code, and the transform was *exercised* end to end producing a
21,561,408,512 B checkpoint with zero sidecars; **(b)** all 1,150 raw line
differences in the 8 kept files are comments/whitespace, proven by three
independent methods including a token-stream comparison
(`CODE_IDENTITY=PASS`).

**The honest caveat the advisor should carry forward.** This is a *no-regression*
verdict, not a confirmation that the adoption's ranked gain landed. Two of the
eight adopted files — and 618 of the changed kernel lines, the largest deltas —
are `_nax` prefill sources that a gen-16 host **cannot execute**. The M5 gain
implied by the leaderboard (2.6165035 / 2.5515846 = **+2.544 %** of score) is
therefore mostly invisible to this instrument by construction, and my measured
M4 null is fully consistent with the frontier being a large M5 win. The M5
predictions in the prereg (decode −80 µs/step, prefill −12 µs/token) stand
unscored and can only be settled by an official receipt.

**Follow-up I did not run** (advisor's call, ≈2 h exclusive host time): a
13-rep/arm block would resolve the 38 µs/step scale and could adjudicate the
retired rev1 premise. I judge it low value — the decision to keep `7687c2e4`
does not depend on it, and 38 µs/step is 0.29 % of decode, i.e. 0.19 % of score.

## 8. Unresolvable by design

nezuko's cross-prediction (`632e2c4`, ~80% confidence that the R85 regression
was not dispatch-count-related, guessing KV-cache bytes,
`research/nezuko-r85-460-crossprediction.md`) is now **unresolvable by
design**: rev2 retired the 11-file bisect that would have adjudicated it, and
the tree it referred to has been replaced. It should be scored as neither
confirmed nor refuted.
