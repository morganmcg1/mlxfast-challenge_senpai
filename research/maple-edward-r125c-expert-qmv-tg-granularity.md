# R125-C — threads-per-threadgroup granularity for the routed expert QMV

Assignment `maple-r125-c-expert-qmv-tg-granularity`, revision `r125-c-rev1`, PR #731.
Base `codex/mlxfast-maple-20260804-advisor` @ `a9de9e8f21188715f6d80ada4b581bcd50d4ec81`.
Branch `maple-edward/r125-c-expert-qmv-tg-granularity`.
Host: Apple M4 Pro, 20 GPU cores, Apple GPU generation 16 (not the ranked M5).

## 0. Verdict

_(filled in after the ladder campaign; see §3)_

## 1. Bandwidth census and candidate admissibility

The advisor gate asks for achieved bandwidth divided by the measured streaming
peak, per candidate kernel, *before* choosing a target. All numbers below come
from an earlier same-host census, not from new measurements.

Source: `research/maple-edward-r110/STAGE0-QMV-BANDWIDTH.md`, captured on base
`ad3773a0a188cad3e4ac97479dd7da31341d41ab` on this same M4 Pro. The streaming
peak table at `:139-144` gives a median of **256.7 / 256.9 GB/s** over the two
sweep directions (best 259.2 / 260.0).

| kernel | bytes/dispatch | real µs/call | achieved GB/s | % of 256.7 GB/s peak | % of own short-dispatch ceiling |
|---|---|---|---|---|---|
| K1 routed gate/up `..._top8keys_r1_bf16_v2` | 8,912,896 | 38.44 | 232.0 | **90.4 %** | 93.5 % |
| K4 routed+shared down/residual `..._sh_stage4_v6` | 5,013,504 | 22.09 | 227.6 | 88.7 % | **96.7 %** |
| K2 decode qkv h64 | 10,823,680 | 44.73 | 242.1 | 94.3 % | 95.4 % |
| K3 oproj qmv h64 | 8,652,800 | 37.15 | 233.4 | 90.9 % | 93.9 % |

Byte derivations at `STAGE0-QMV-BANDWIDTH.md:118-123`, per-call timings at
`:94-97`, achieved GB/s at `:173`, short-dispatch ceilings at `:146-173`.

A second, independent capture agrees: `research/maple-alphonse-r109e-bwatlas.txt`
rows 7/8/20/29 (that script assumes a 273.0 GB/s peak,
`research/maple-alphonse-r109e-bwatlas.py:38`, so its percentages are lower by
construction but the *ordering* is the same).

**Reading of the gate.** The two reference points on this host are K2 decode qkv
(94.3 % of peak, 95.4 % of its own ceiling), where nezuko's threadgroup ladder
returned a null, and K3 oproj (90.9 % / 93.9 %), where the equivalent ladder
won. K1 routed gate/up sits at 90.4 % / 93.5 % — on the *winning* side of both
reference points, and it is the least bandwidth-saturated of the four. It is
therefore admissible under the advisor's ">~93 % of measured peak ⇒ expect a
null" rule, and it is the best available candidate in this family.

The fused routed+shared down/residual kernel (K4) looks attractive on raw
%-of-peak (88.7 %, the lowest of the four) but it is at **96.7 % of its own
short-dispatch ceiling** — the least headroom in the table. That kernel is a
worse candidate than the raw column suggests, which is why the ladder below
targets K1 only and the K4 tiles-per-threadgroup arm was deprioritised.

### Verified kernel arithmetic

The model has **39 MoE layers** out of 40: `mlp_only_layers=[0]` and
`decoder_sparse_step=1` (`Sources/MLXFastModel/LagunaConfig.swift:544-548`,
`:855-865`). hiddenSize 2048, numExperts 256, numExpertsPerTok 8,
moeIntermediateSize 512.

Routed gate/up QMV per decode token, per layer:

- grid **131,072 threads** = 4,096 simdgroups = 8 expert slots × 512 rows;
- per row: 1,024 B gate + 1,024 B up + 128 B scales = 2,176 B;
- × 4,096 rows = **8,912,896 B/dispatch**, matching the census;
- × 39 layers = **347.6 MB/token** of routed gate/up weight traffic alone.

The activation row is 2,048 bf16 = **4,096 B** and is bit-identical for every
simdgroup in the dispatch. It is read once per *threadgroup* out of L2 into L1:

| threads/TG | simdgroups/TG | TGs/dispatch | L2→L1 activation fills/dispatch | per token (×39) |
|---|---|---|---|---|
| 64 (shipped) | 2 | 2,048 | 8.39 MB | 327 MB |
| 128 | 4 | 1,024 | 4.19 MB | 164 MB |
| 256 | 8 | 512 | 2.10 MB | 82 MB |

DRAM traffic for that row is 4,096 B once — it lives in L2 — so the saving is
**L2→L1**, exactly the mechanism frieren reported for `lagunaSharedSwiGLUQMV`
in R119-C. Weight traffic (the 347.6 MB/token) is untouched by the ladder.

### Wave arithmetic

| threads/TG | TGs | TGs/core @ C=20 (this host) | tail | TGs/core @ C=40 (M5 Max) | tail |
|---|---|---|---|---|---|
| 64 | 2,048 | 102.4 → 103 | 0.6 % | 51.2 → 52 | 1.6 % |
| 128 | 1,024 | 51.2 → 52 | 1.6 % | 25.6 → 26 | 1.5 % |
| 256 | 512 | 25.6 → 26 | 1.5 % | 12.8 → 13 | 1.5 % |
| 512 | 256 | 12.8 → 13 | 1.5 % | 6.4 → 7 | 8.6 % |

512 threads/TG is excluded from the ladder: on a 40-core M5 it would leave an
8.6 % tail-imbalance, which is why 256 tops the ladder on both core counts and
why the ladder stops there.

## 2. Code change

All edits are in `Sources/MLXFastModel/LagunaRuntimeModel.swift`, an
`editablePaths` entry.

1. **`lagunaRoutedQMVThreadsPerThreadgroup` (`:8059`)** reads
   `DARKBLOOM_ROUTED_QMV_TG` and accepts only `128` or `256`; anything else
   (including unset) yields **64**, the shipped value. The default build is
   therefore byte-identical to base.

2. **`lagunaRoutedSwiGLUQMVPackedTop8R1Source(simdgroupsPerThreadgroup:)`
   (`:8067`)** emits the original source text unchanged when `S == 2`. For
   `S > 2` it recovers the shipped *global* simdgroup ordinal:

   ```metal
   uint laguna_simd_ordinal = groupExpr * S + simdgroup_index_in_threadgroup;
   uint group      = laguna_simd_ordinal / 2;
   uint simd_group = laguna_simd_ordinal % 2;
   ```

   Every simdgroup therefore computes exactly the same `(group, simd_group)`
   pair, and hence the same output row, as it did at 64 threads/TG. The grid is
   unchanged at 131,072 threads, so the set of ordinals is unchanged. This is
   the bit-identity argument; it is confirmed empirically in §3.

3. **Name-suffixed pipelines.** The factory
   `lagunaRoutedSwiGLUQMVPackedTop8R1Kernel(threadsPerThreadgroup:)` (`:8207`)
   builds `..._r1_bf16_v2_tg128` / `_tg256`, and
   `lagunaRoutedSwiGLUQMVPackedTop8R1WideKernel` (`:8224-8228`) is `nil` at 64.
   Distinct names matter: MLX keys its per-process library and PSO cache on the
   generated kernel name (`Vendor/mlx-swift/.../metal_kernel.cpp:289-316`), and
   a same-name-different-source pair triggers `clear_library` and a recompile on
   *every* alternation (`custom_kernel.cpp:56-69`). Threadgroup size itself is
   **not** part of any cache key (`fast_primitives.h:418`; it is used only at
   encode time, `custom_kernel.cpp:102-115`).

4. **Dispatch (`:8330-8340`)** selects `(Wide ?? base)`, sets
   `threadGroup: (threads, 1, 1)`, leaves the grid at 131,072, and emits
   `lagunaTrace("routed gate/up QMV r1 tg\(threads)")` for reachability proof.

5. **`lagunaSharedRoutedSwiGLUQMV` grid-append is guarded** by
   `lagunaRoutedQMVThreadsPerThreadgroup == 64` (`:8274`) so the wide arms never
   silently fall into a different fusion. That fused path is itself opt-in
   (`DARKBLOOM_SHARED_ROUTED_QMV_FUSED == "1"`, `:8231`) and is **off by
   default**, so all arms share the same append state without any extra
   environment variable. Verified in the trace, §3.

### Reachability correction to the assignment

The assignment's priorities #2 `lagunaSharedDownResidual` and #3
`lagunaRoutedDownReduce` are **fallback paths only** on this base.
`DARKBLOOM_FUSED_ROUTED_SHARED_DOWN_RESIDUAL != "0"` (LRM ~`:144`) makes the
288-thread fused routed+shared down kernel
(`lagunaRoutedSharedDownResidualSource` `:8506`, dispatch `:8875-8880`) the live
default: it is tried at `:11144-11177` and the unfused pair is only reached at
`:11179`. A threadgroup knob on #2/#3 would not have been on the scored path.

## 3. Measurements

_(filled in after the ladder campaign)_

## 4. Mechanism

_(filled in after the ladder campaign)_

## 5. Deviations from the assignment

_(filled in after the ladder campaign)_

## 6. Next steps

_(filled in after the ladder campaign)_
