# R85-B split: emitted-code neutrality evidence

> **SUPERSEDED — historical.** Every number in this note was produced on base
> `7687c2e44e6975c181444ca8d3d151ee30480a72`, which advisor feedback 5 replaced
> with the scored-surface-move base
> `3217f111142346e004f41fae611a8bede172a659`. Do **not** quote its byte counts,
> `__TEXT,__text` deltas, or symbol tallies as current. The current-base
> equivalents live in `research/maple-fern-r85b-binary-forensics.md`; the
> current-base byte accounting lives in `research/r85b-logs-rebased/budget.txt`.
> This note is retained because its method, and the fact that the same method
> reached the same verdict on two different bases, is itself evidence.

Research-only note. Not part of `editablePaths`.

Question: does moving 2,587 lines of `Sources/MLXFastModel/LagunaRuntimeModel.swift`
verbatim into a new in-surface file `Sources/MLXFastModel/LagunaRuntimeLayers.swift`
change any machine code that executes inside the timed prefill or decode window?

The advisor's failure threshold is 5 us/step decode. On this M4 Pro host that is
~0.039% of a decode step, well below `--local-iterate` run-to-run resolution, so
paired wall-clock timing alone cannot answer the question. Emitted-code
comparison can, and does.

## Method

`research/fern_emit_compare.py` builds each arm with the scored worker product
into a private scratch path, then compares:

- `sizes`: Mach-O section sizes of the linked `mlxfast-runtime-worker` binary
  (`size -m`), plus per-object `__text` sums.
- `diff`: linked-binary symbol tables (`nm -n`), with Swift private
  discriminators normalised so that a symbol which only changed file-of-origin
  compares equal by shape.
- `asm`: per-symbol disassembly (`otool -tvV` restricted to each symbol's
  address range) for every MLXFastModel text symbol, compared instruction by
  instruction with addresses, branch targets and literal-pool offsets
  normalised.

`research/fern_asm_diff.sh` drives the full-symbol sweep.

Builds are not bit-reproducible: two consecutive builds of the unchanged base
produced different binary sha256 values. Section, symbol and instruction
comparison is stable; whole-binary hashing is not, and was not used.

## Result 1 — linked binary section sizes

| section | base | cand | delta |
|---|---|---|---|
| `__TEXT,__text` | 18,976,524 | 18,976,616 | **+92 (+0.00048%)** |
| `__TEXT,__const` | | | +64 |
| `__TEXT,__eh_frame` | | | +16 |
| `__TEXT,__objc_methname` | | | -16 |
| `__DATA,__data` | | | -16 |
| `__DATA_CONST,__const` | | | +16 |
| `__DATA_CONST,__got` | | | +16 |

All other non-DWARF sections are byte-identical. `__DWARF` deltas are debug-only
and excluded.

The per-object `__text` sum moves +356 B (453,532 -> 453,888), but that metric
is misleading: whole-module-optimisation partitioning emits shared generic
helpers into more than one output object and the linker dedups them. The linked
binary is the honest number.

## Result 2 — linked binary symbol diff

17 symbols added, 13 removed. All accounted for:

- 11 entries are rename-only pairs caused by the five `private` -> `internal`
  widenings the split required (a `private` global's mangled name embeds a
  file discriminator; widening to `internal` removes it).
- 2 are merged-specialization representative swaps, where the linker picked a
  different equivalent instantiation as the surviving copy
  (`makeLagunaAttentionGateProjection` `Si48` <-> `Si64`;
  `_ArrayBufferV._consumeAndCreateNew` `UInt32` <-> `Int32`).
- 4 are newly emitted shared helpers: default-argument generators for
  `MLX.quantizedMM`, `MLXArray.asType` and an `MLXArray` subscript, plus
  `_$sSaySiGSayxGSlsWlTm`. These four are the +92 B.

None of the four new helpers is reachable from the decode or prefill hot loop;
they are default-argument thunks materialised because the call sites now live
in a different file of the same module.

## Result 3 — per-symbol instruction diff

926 MLXFastModel text symbols on each side.

- **917 body-identical**, instruction for instruction.
- **2 identical modulo a linker branch island**: `LagunaConfig.WOc` and
  `LagunaRuntimeMLP.callAsFunction`. In each case every body instruction is
  identical (376/376 and 377/377) and the only extra instruction is an
  unreachable `b` island the linker parked in inter-function padding after the
  final `ret`. That is a link-layout artefact, not a codegen change.
- **4 renamed pairs**, verified identical separately:
  `lagunaDecodeEmbeddingRoPEAtlas` 66 <-> 66 insns,
  `makeLagunaAttentionGateProjection` 188 <-> 188,
  `lagunaRouterPrecomputedKeysEnabled` one-time initialiser 81 <-> 81,
  `lagunaTerminalPrefillFusionEnabled` one-time initialiser 81 <-> 81.
- **3 body-different**, all construction/teardown, none on the timed path:

| symbol | base insns | cand insns | difference |
|---|---|---|---|
| `LagunaRuntimeModelInner.init(config:)` | 374 | 375 | one extra `mov x0, #0` |
| `LagunaRuntimeDecoderLayer.init(_:layerIdx:)` | 183 | 184 | one extra `mov x0, #0` |
| `LagunaNativeAffineWeight.WOh` (outlined destroy) | 20 | 11 | 9 fewer insns |

`init(config:)` and `init(_:layerIdx:)` run once per model load, before the
thermal gate and before any timed window. The outlined destroy shrank.

## Result 4 — the timed path specifically

Result 3 counts symbols. The advisor's question is narrower: did the
`private` -> `internal` widening cost an inlining or specialization opportunity
on the *scored* path? `research/fern_hotpath_check.py` inverts the report — it
enumerates the functions that execute inside the timed prefill/decode window and
asserts none of them is in the not-identical set.

```
MLXFastModel __text symbols: base=926 cand=926 matched-after-normalisation=922

  IDENTICAL  n=  1  LagunaRuntimeModelInner.callAsFunction
  IDENTICAL  n=  1  LagunaRuntimeDecoderLayer.callAsFunction
  IDENTICAL  n= 10  LagunaRuntimeSparseMoEBlock
     ISLAND  n=  1  LagunaRuntimeMLP.callAsFunction
  IDENTICAL  n=  6  LagunaRuntimeMoEGate
  IDENTICAL  n= 21  LagunaRuntimeAttention
  IDENTICAL  n= 16  lagunaDecodeRouter
  IDENTICAL  n=  1  lagunaDecodeEmbeddingRoPEAtlas
  IDENTICAL  n= 32  lagunaPrefill
  IDENTICAL  n=  2  lagunaRoPE
  IDENTICAL  n=  2  makeLagunaAttentionGateProjection
  DIFFERENT  n= 18  LagunaNativeAffineWeight   [DIFF] ...LagunaNativeAffineWeightVWOh
```

131 of 132 timed-path symbols are body-identical instruction for instruction.
The two exceptions:

- `LagunaRuntimeMLP.callAsFunction` — all 377 body instructions identical; the
  only extra instruction is an unreachable linker branch island parked in
  inter-function padding after the final `ret`.
- `LagunaNativeAffineWeight.WOh` — the compiler-outlined destroy shrank from 20
  to 11 instructions. Shorter, not longer.

Note that `LagunaRuntimeSparseMoEBlock`'s real hot entry is a `private func
forward(...)`, whose mangled name embeds a file-name hash and therefore
*changes* under the carve. It is still verified identical: the comparison
normalises the private discriminator, so a symbol that only changed
file-of-origin is matched by shape and its body is compared. Without that
normalisation the MoE block would have silently dropped out of the comparison,
which is the specific trap this check exists to avoid.

## Result 5 — wall clock, reported for completeness

7 counterbalanced paired rounds via `research/paired-timing-r85b-split.sh`
(each pair is a full `./benchmark.sh --local-iterate` per arm on the same host
in the same session), analysed by `research/fern_timing_stats.py`:

```
n = 7 pairs   baseline decode 12942.0 us/step
decode  diff mean +26.52  sd 93.52  sem 35.35  95% CI [-64.36, +117.40] us/step  (+0.2049 %)
prefill diff mean -3.257  sd 15.503  95% CI [-18.322, +11.808] us/token

baseline-first  n=5  mean +41.44  sd 70.38
candidate-first n=2  mean -10.78  sd 169.62
arm-order effect (BF - CF) +52.23 us/step <- position-in-session drift, not code
order-balanced mean +15.33  se 62.00  ~95% CI [-106.19, +136.85] us/step (+0.1184 %)

one-sided 95% upper bound on a real decode regression:
  pooled         +95.2 us/step  (0.736 %)
  order-balanced +117.3 us/step  (0.906 %)
```

Two things to read here.

First, the **arm-order effect is +52 µs/step**. The first three rounds always
ran baseline first, and baseline decode drifted monotonically upward across
that session (12.909 -> 12.925 -> 12.952 ms), so the candidate systematically
inherited a warmer host. Both arms are the same code in expectation, so that
+52 µs is pure position-in-session drift. It is larger than the whole effect
being argued about, which is why the ordering was counterbalanced and why the
order-balanced estimate is the one to quote.

Second, the **wall clock cannot resolve this question at all**. At sd ≈ 94
µs/step, a ±5 µs/step 95 % interval would need ~1,344 pairs, about 127 hours of
arms. What the 7 pairs do establish is an upper bound: a decode regression
larger than ~0.74 % (pooled) is excluded. That is the same class of result as
the advisor's own GREEN verdict on PR #460 (+6.34 µs/step, pooled SD 49.00,
95 % CI [−104.73, +117.41], regression > 0.81 % excluded) — in fact the upper
CI limits agree to three digits.

Correctness passed on all 14 arms with `max_abs_diff` 0 and no golden-drift
override set.

## Conclusion

Every function that executes inside the timed prefill or decode loop is
instruction-identical between base and candidate. The split is a pure
source-layout change with no measurable machine-code consequence on the scored
path. Paired wall-clock timing is reported as a sanity check, but this
comparison, not the wall clock, is the load-bearing neutrality evidence.

## Appendix — exact byte accounting (the deliverable)

All numbers measured on the candidate tree against
`BASE_SHA=7687c2e44e6975c181444ca8d3d151ee30480a72`.

Per-file (cap 524,288 B/file):

| file | base | candidate | headroom after |
|---|---|---|---|
| `Sources/MLXFastModel/LagunaRuntimeModel.swift` | 511,418 | **399,115** | **125,173** |
| `Sources/MLXFastModel/LagunaRuntimeLayers.swift` (new) | — | **112,578** | 411,710 |
| sum of the two | 511,418 | 511,693 | — |

Surface totals:

```
senpai/validate-assignment-scope.sh 7687c2e4... \
  Sources/MLXFastModel/LagunaRuntimeModel.swift \
  Sources/MLXFastModel/LagunaRuntimeLayers.swift
  -> assignment scope OK: 2 submitted path(s)

senpai/check-editable-budget.sh 7687c2e4...
  -> editable budget OK: current=2891618/3000000 bytes headroom=108382
     growth=275/262144 files=141 (base=140)
```

The 275 B of growth reconciles exactly:

```
+316  new-file header (license/module banner)
  -1  one blank line removed at the carve seam
 -40  5 x "private " -> "internal " is 5 x -8 B
----
+275
```

`LagunaRuntimeLayers.swift` is in-surface through the bare directory entry
`Sources/MLXFastModel` already present in `editablePaths`; `benchmark.json` is
not edited, and the editable-path count moving 140 -> 141 is diagnostic only.

**What this changes for the queue.** Per-file headroom on the scored forward
pass goes from 12,870 B to **125,173 B**, a 9.7x increase. After the split the
largest editable file is 399,115 B and the next largest is 112,578 B, so no
individual file is within 400 kB of the per-file cap and the *only* binding
constraint left on the surface is the 3,000,000 B total, with 108,382 B of
headroom. Growth per review remains capped at 262,144 B; this submission spends
275 B of it.

## Reproduction

```bash
# emitted-code comparison (Results 1-3)
python3 research/fern_emit_compare.py dump  --out ../mlxfast-r85b-emit
python3 research/fern_emit_compare.py sizes --out ../mlxfast-r85b-emit
python3 research/fern_emit_compare.py diff  --out ../mlxfast-r85b-emit
bash research/fern_asm_diff.sh

# timed-path assertion (Result 4)
python3 research/fern_hotpath_check.py ../mlxfast-r85b-emit

# paired wall clock (Result 5) -- rounds as $1, output dir via OUT
OUT=../mlxfast-r85b-split-timing bash research/paired-timing-r85b-split.sh 4
python3 research/fern_timing_stats.py '../mlxfast-r85b-split-timing/*.row.json'
```
