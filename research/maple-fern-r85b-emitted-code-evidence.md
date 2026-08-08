# R85-B split: emitted-code neutrality evidence

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

## Conclusion

Every function that executes inside the timed prefill or decode loop is
instruction-identical between base and candidate. The split is a pure
source-layout change with no measurable machine-code consequence on the scored
path. Paired wall-clock timing is reported as a sanity check, but this
comparison, not the wall clock, is the load-bearing neutrality evidence.

## Reproduction

```bash
python3 research/fern_emit_compare.py dump  --out ../mlxfast-r85b-emit
python3 research/fern_emit_compare.py sizes --out ../mlxfast-r85b-emit
python3 research/fern_emit_compare.py diff  --out ../mlxfast-r85b-emit
bash research/fern_asm_diff.sh
```
