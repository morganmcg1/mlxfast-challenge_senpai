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

_(filled in from the completed gate run)_

## 6. Matched timing

_(filled in from the completed gate run)_

## 7. Verdict

_(filled in from the completed gate run)_

## 8. Unresolvable by design

nezuko's cross-prediction (`632e2c4`, ~80% confidence that the R85 regression
was not dispatch-count-related, guessing KV-cache bytes,
`research/nezuko-r85-460-crossprediction.md`) is now **unresolvable by
design**: rev2 retired the 11-file bisect that would have adjudicated it, and
the tree it referred to has been replaced. It should be scored as neither
confirmed nor refuted.
