SENPAI-RESULT: {"terminal":true,"status":"complete","pending_arms":false,"wandb_run_ids":[],"primary_metric":{"name":"same_host_paired_estimate","available":false,"value":null},"test_metric":{"name":"passed_correctness","available":false,"value":null}}

# PR #649: routed-down prefill epilogue feasibility

## Decision

**Gate 0: NO-GO. No production source was changed and no model run or official submission was made.**

The stock regular and ranked NAX routed-down producers are expert-major. Their
threadgroups do not own all eight routed rows for one token, so they cannot
perform the required slot-ordered token reduction without a second grid-wide
phase or a different, token-major decomposition. The token-major decomposition
is exact in principle, but rereads the packed expert matrices once per route
occurrence rather than once per expert and raises the ideal routed-down weight
traffic by 16x. Three independent assignment gates also fail: the optimistic
bank write/read traffic ceiling is only 2.217510 ms, below the required
2.33 ms measured lower bound; the clean fused epilogue needs operands that the
editable GatherQMM ABI cannot carry; and a credible dual-family patch exceeds
the assignment's 8 KiB cap.

## Scored-path census and current tail

`Sources/MLXFastModel/LagunaRuntimeModel.swift` runs the ordinary sparse
prefill path for layers **1 through 38**, for an exact census of **38 layers**.
Layer 0 is dense and layer 39 uses the terminal one-row path, so neither is in
the proposed 512-row routed-down fusion census.

For each ordinary layer, routed down currently materializes a sorted BF16 bank
with shape `[4096, 2048]`:

- 512 tokens x top-8 routes = 4096 sorted rows;
- 2048 BF16 output channels;
- 16,777,216 bytes written per layer;
- the standalone tail reads the same 16,777,216 bytes per layer.

The tail in `LagunaRuntimeModel.swift` is dispatched over grid `(512, 512, 1)`
with threadgroup `(256, 1, 1)`, or 1,024 threadgroups per ordinary layer. It
uses the inverse permutation to recover each token's eight flattened route
occurrences, multiplies each routed row by its BF16 router weight, accumulates
slots in logical order 0 through 7 at BF16 boundaries, then combines the
routed scale, shared expert, and residual using the existing BF16 conversion
boundaries. Duplicate expert IDs remain distinct flattened route occurrences;
they are not algebraically mergeable.

The required replacement therefore must preserve all of these properties:

1. down projection accumulates in FP32 and stores a BF16 route row;
2. router weighting creates the same BF16 weighted slot value;
3. slots reduce in order 0, 1, ..., 7 with the same BF16 rounding points;
4. routed scale, shared output, and residual retain their current boundaries;
5. each duplicate route occurrence participates independently.

Reassociation, unordered atomics, an FP32 eight-slot accumulator, or merging
duplicate experts is not an exact implementation of the current graph.

## Regular producer ownership

The executable regular NVFP4 GatherQMM source is
`Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/kernels/fp_quantized.h` (with the
runtime-embedded twin
`Vendor/mlx-swift/Source/Cmlx/mlx-generated/fp_quantized.cpp`), not the affine
fallback in `quantized.h`.

Its selected routed-down geometry is:

- `BM=16`, `BN=32`, `BK=32`, `WM=1`, `WN=2`;
- grid `(64, 256, 1)` = **16,384 threadgroups** per layer;
- 64 threads per threadgroup;
- one group owns 16 sorted rows by 32 output columns;
- dynamic threadgroup scratch is 3,840 bytes: 1,280 bytes for X and 2,560
  bytes for W.

The row dimension is sorted by expert. A group scans the expert run(s) that
intersect its 16-row tile and writes those route rows for only one 32-column
band. One token's eight route occurrences generally belong to unrelated expert
runs, row tiles, and threadgroups. Even when duplicate experts make two rows
adjacent, that group still cannot own the token's other expert slots. The
producer has no grid synchronization and its local first/last run boundaries
cannot establish whole-token ownership.

```text
regular group (row tile r..r+15, cols c..c+31)
    owns expert-sorted route rows in this tile only
    may see 0..k occurrences for token t
    does not own t's remaining slots in other expert runs
    cannot emit exact token[t, c..c+31]
```

Adding router weights or inverse indices as reads does not repair ownership.
Writing the same BF16 route rows preserves the 16 MiB bank; launching a later
reduction preserves the standalone second dispatch. Cross-group atomics would
change reduction order and rounding and are not a valid exact alternative.

## Ranked NAX producer ownership

On ranked M5 hardware the routed-down producer selects
`fp_quantized_nax.h` and its embedded twin `fp_quantized_nax.cpp`. The selected
variant uses:

- `BM=64`, `BN=64`, `BK=64`, variant 5, `WM=4`, `WN=1`;
- executable default of 256 expert groups despite a stale nearby comment;
- grid `(32, 256, 1)` = **8,192 threadgroups** per layer;
- 128 threads per threadgroup;
- one group owns one expert and one 64-column output band;
- source-declared scratch of 9,224 bytes: a 9,216-byte BF16 W tile plus two
  32-bit bounds.

This is an even clearer expert-major partition. Each group can see every
sorted occurrence for its one expert in its column band, but a token's eight
slots span up to eight expert groups. Duplicate experts can share a group yet
still remain separate slots, and other slots remain in other groups.

```text
NAX group (expert e, cols c..c+63)
    owns all sorted rows routed to e for that column band
    can produce route contributions for token t at expert e
    does not own t's slots routed to experts != e
    cannot complete exact slot-order reduction for token t
```

The current NAX GatherQMM ABI does not receive router weights, inverse
permutation, shared output, residual, or routed scale, so it also lacks the
inputs needed to replace the tail even if ownership were changed.

## Exact token-major alternative and why it is rejected

A separate producer can own a token and output-channel tile, then visit slots
in exact order. This is the only simple ownership map found that eliminates the
bank and tail while preserving the current BF16 sequence:

```text
for token t assigned to this group:
  routed = bf16(0)
  for slot s in 0..<8:
    e = expert[t, s]
    row = down_nvfp4_fp32_accumulate_bf16_store_boundary(x[t, s], W[e])
    weighted = bf16(row * bf16(router[t, s]))
    routed = bf16(routed + weighted)
  out[t] = existing_bf16_epilogue(routed, scale, shared[t], residual[t])
```

It is computationally unacceptable for this shape. One logical packed down
matrix for one expert contains 524,288 bytes of NVFP4 weights plus 65,536 bytes
of scales, or **589,824 bytes**. The optimistic expert-major ideal reads 256
matrices per layer:

```text
256 * 589,824 = 150,994,944 bytes/layer
```

Token-major ownership has 512 x 8 = 4096 route occurrences:

```text
4096 * 589,824 = 2,415,919,104 bytes/layer
```

That is **16x** the ideal packed weight traffic before cache effects. It also
at least doubles dispatched groups while retaining the same useful MMA work:
32,768 versus 16,384 regular groups, and 16,384 versus 8,192 NAX groups. A
persistent global scheduler could theoretically regroup work, but it would
need cross-threadgroup coordination and a second reduction phase; no bounded,
exact, <=8 KiB design was identified.

## Amdahl and traffic accounting

The maximum bank traffic directly removed by perfect fusion is:

```text
38 layers * (16,777,216-byte write + 16,777,216-byte read)
= 1,275,068,416 bytes
```

At the assignment's optimistic 575 GB/s conversion:

```text
1,275,068,416 / 575,000,000,000 * 1000
= 2.217510 ms
```

This is already below the mandatory **2.33 ms measured lower bound** and does
not include uncertainty. `research/CURRENT_RESEARCH_STATE.md` records the
related #646 requirement, but the branch contains no terminal qualifying M5
measurement proving >=2.33 ms with <=0.10 ms uncertainty. Thus the independent
Amdahl gate fails even before implementation risk.

The 1,024 tail groups x 38 = 38,912 dispatch groups are real overhead, but no
measured evidence in the assigned base establishes enough additional cost to
convert the 2.217510 ms optimistic traffic ceiling into the required lower
bound. It would be invalid to treat a theoretical dispatch cost as the
required measurement.

## Editable scope, ABI, byte budget, and compiler feasibility

The hypothetical backend source set is editable under `benchmark.json`:

1. `Sources/MLXFastModel/LagunaRuntimeModel.swift`
2. `Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/quantized.cpp`
3. `Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/jit_kernels.cpp`
4. `Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/kernels/fp_quantized.h`
5. `Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/kernels/fp_quantized_nax.h`
6. `Vendor/mlx-swift/Source/Cmlx/mlx-generated/fp_quantized.cpp`
7. `Vendor/mlx-swift/Source/Cmlx/mlx-generated/fp_quantized_nax.cpp`

`senpai/validate-assignment-scope.sh` passed for those paths against base
`84d8c61b3ab732426a6c28f9cccbb8821177eaab`. The repository budget check also
passed at 2,984,121 / 3,000,000 bytes, leaving 15,879 bytes globally;
`LagunaRuntimeModel.swift` is 511,690 bytes, leaving 12,598 bytes in that file.

However, a clean fused call must transport router weights, inverse indices,
routed scale, shared output, and residual through the public operation. The
relevant public bridge files, `Vendor/mlx-swift/Source/MLX/Ops.swift` and
`Vendor/mlx-swift/Source/Cmlx/mlx/mlx/ops.cpp`, are not editable. Reusing an
unrelated tensor slot or smuggling pointers through metadata would not be a
maintainable or contract-safe implementation.

A conservative regular + NAX + generated-twin + dispatch patch is estimated at
12--30 KiB, above the assignment's 8 KiB experiment cap. No compiler skeleton
was built: producer ownership, Amdahl evidence, editable ABI, and byte gates
all fail first. Consequently there is no honest threadgroup-memory or
occupancy result to report, and no claim is made from source-declared scratch
alone.

## Verification and reproducibility

Static checks used:

```bash
senpai/validate-assignment-scope.sh 84d8c61b3ab732426a6c28f9cccbb8821177eaab \
  Sources/MLXFastModel/LagunaRuntimeModel.swift \
  Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/quantized.cpp \
  Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/jit_kernels.cpp \
  Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/kernels/fp_quantized.h \
  Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/kernels/fp_quantized_nax.h \
  Vendor/mlx-swift/Source/Cmlx/mlx-generated/fp_quantized.cpp \
  Vendor/mlx-swift/Source/Cmlx/mlx-generated/fp_quantized_nax.cpp
senpai/check-editable-budget.sh 84d8c61b3ab732426a6c28f9cccbb8821177eaab
git diff --check
git diff --exit-code 84d8c61b3ab732426a6c28f9cccbb8821177eaab -- \
  Sources/MLXFastModel Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal \
  Vendor/mlx-swift/Source/Cmlx/mlx-generated
```

Expected result: scope PASS, editable budget PASS, report formatting PASS, and
production-source identity PASS. No build, correctness test, local benchmark,
GPU/model job, W&B run, or official M5 submission was performed because Gate 0
requires stopping before production implementation when any mandatory gate
fails. W&B run IDs and URLs are therefore not applicable. Runtime and peak
memory are also not applicable.

## Conclusion

The hypothesis is rejected on the assigned base. The existing expert-major
regular and NAX producers cannot own the exact token reduction; the only simple
exact ownership reversal has a 16x ideal expert-weight traffic penalty; the
optimistic removable bank traffic misses the Amdahl threshold; and the clean
ABI and <=8 KiB constraints are unsatisfied. The correct action is to retain
the current production path and preserve the negative result for future design
work.

_This research report was generated by an AI agent (OpenHands) on behalf of the
assigned student._
