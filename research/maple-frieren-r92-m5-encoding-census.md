# r92-b — differential g16s-vs-g17s encoding census of the scored decode path

**Student:** maple-frieren · **PR:** #490 · **assignment:** `maple-r92-b-m5-encoding-census`
(rev `r92-b-rev1`) · **base:** `8486638578a283de40369172f68c3a4d2d6a5365`
· **host:** Apple M4 Pro, 48 GiB (low-memory startup profile) · **date:** 2026-08-09

## Verdict

**H0.** There is a real, reproducible static g17s excess on the scored decode
path, but it is not the uint-MAD phenomenon that H1 requires, and no concrete
rewrite survived census.

Specifically:

1. The excess exists and is narrow. Only two of the twelve reachable scored
   decode kernels are larger on g17s: `laguna_sliding_fused_attn_ring_v1`
   (+128 B, +1.8 %) and `laguna_full_fused_attn_grow_v1` (+144 B, +1.8 %).
   Weighted by dispatch count that is **+5280 static `__compute` bytes per
   steady decode step**.
2. Six of the twelve kernels are *smaller* on g17s, by up to 416 B
   (`laguna_fused_norm_qkv_projection_bf16_h64_v3`, −5.2 %). So g17s codegen
   differs from g16s in several opposing ways and any single Δ is a **net**,
   never an instruction count. This independently re-confirms rule 42's
   retirement of `(bytes − floor)/8`.
3. Stage-3 ablation localises ~40–55 % of the two positive Δs to the
   `simd_sum` family, and within that family to the **epilogue**, which runs
   once per launch. `simd_sum` is a shuffle reduction, not the uint-MAD opcode
   class that rule 42 identifies as H1's entire physical basis.
4. The uint-MAD encoding penalty itself was reproduced exactly (12.0 B/op g16s
   → 14.0 B/op g17s, +16.7 %, on an operation touching no memory). But the hot
   loops of both positive kernels are float-FMA / `simd_sum` / `simd_max` /
   `fast::exp` dominated, and float FMA encodes at **6.0 B/op on both
   arches**. The physical mechanism H1 needs is absent from the code that
   actually spins.
5. Both concrete rewrites suggested by the localisation were **falsified by
   census**: fusing the four componentwise epilogue `simd_sum` calls into one
   `float4` `simd_sum` censuses **byte-identical on both arches** (compiler
   canonicalisation — rule 42's first hypothesis), and a hand-written
   `simd_shuffle_xor` butterfly is **+944 B g16s / +912 B g17s** (the builtin
   lowers far more compactly).

The honest caveat, and the recommended next arm, is item (6) below: the
integer-ALU-heavy fused NVFP4 routed-expert kernels — the single most plausible
home for H1 — were initially outside the reach of the dump vehicle. See
"Stage 1′".

## Method and admissibility

Per advisor rule 42 the census measures **static `__compute` section code bytes**
of a compiled Metal function, and is admissible **only** as a matched-null
difference within one opcode class and one loop structure. Bytes are never
converted to instruction counts.

- Compiler: `xcrun metal` from Metal toolchain v17.6.109.0.92Vqge.
- Flags matched to the runtime: `-std=metal4.0 -fno-fast-math`, verified
  against `Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/device.cpp:631`
  (`setFastMathEnabled(false)`) and `:632` (`MTL::LanguageVersion4_0`).
- Arches: `applegpu_g16s` (this host) and `applegpu_g17s`. `g17s = M5 Max` is
  an **inference**, not documented. The arch discriminator is `CpuSubtype`:
  g16s `0x1D3`, g17s `0x163`, g17p `0x143`, g18p `0x173`; all report
  `Arch: agx3`. No AGX disassembler exists (`metal-objdump -d` fails on agx3),
  so byte counts are the only available signal.
- Sizes read with `xcrun metal-size` / `applegpu-nt` via
  `senpai/tools/agx-census-probe/census.sh`.

### Control 1 — encoding table reproduced (PASS)

Marginal bytes per operation, from `senpai/tools/agx-census-probe/encoding.metal`
arms at three loop lengths each:

| op class | g16s B/op | g17s B/op | Δ |
|---|---|---|---|
| float add | 4.0 | 4.0 | 0 % |
| float FMA | 6.0 | 6.0 | 0 % |
| float FMA, loop-varying immediate | 11.0 | 11.0 | 0 % |
| **uint MAD** | **12.0** | **14.0** | **+16.7 %** |

Raw `__compute` bytes — g16s: `e_null` 1600; `ffma` 1840/2032/2416;
`fadd` 1760/1888/2144; `fimm` 1888/2240/2944; `imad` 2032/2416/3184.
g17s: `e_null` 1584; `ffma` 1824/2016/2400; `fadd` 1744/1872/2128;
`fimm` 1872/2224/2928; `imad` 2080/2528/3424.

This is the entire physical basis available to H1, and it applies to integer
multiply-add, an operation touching no memory. It is stated explicitly here
because it is the yardstick against which every kernel ranking below must be
read.

### Control 2 — arch floor is *not* a constant −16 B (refines rule 42)

Rule 42 records the g16s→g17s floor as a constant −16 B (1520/1504 and
1600/1584). That holds only for kernels with no simdgroup attributes:

| floor arm | g16s | g17s | Δ |
|---|---|---|---|
| `floor_buf1` | 1520 | 1504 | −16 |
| `floor_buf2` | 1520 | 1504 | −16 |
| `floor_buf4` | 1600 | 1584 | −16 |
| `floor_buf4_bf16` | 1616 | 1600 | −16 |
| **`floor_buf4_bf16_simd`** | **1664** | **1664** | **0** |

The delta collapses to exactly 0 B once simdgroup/lane attributes are declared
— which **every** scored Laguna decode kernel does. So a per-kernel Δ must be
reported **bracketed over a correction of −16..0 B**, not corrected by an
inherited constant. All Stage-2 verdicts below use that bracket together with
rule 42's |Δ| ≤ 16 B noise band (16-byte alignment quantum).

## Stage 1 — what the scored decode path actually dispatches

MLX will print the generated MSL for a custom kernel when the Swift
`metalKernel(..., verbose: true)` flag is set
(`Vendor/mlx-swift/.../backend/common/metal_kernel.cpp:343`, a `std::cout`
write). The obstacle is that the runtime worker replaces `STDOUT_FILENO` with
`/dev/null` before any dispatch
(`Sources/MLXFastHarness/LagunaRuntimeWorker.swift:1187-1200`, helper
`redirectDescriptorToDevNull` at `:1255`), so nothing survives under
`./benchmark.sh`.

Stage 1 therefore used the upstream-equivalence oracle under `swift test`
(`Tests/MLXFastTests/LagunaCorrectnessTests.swift:216-249` →
`LagunaUpstreamEquivalence.compare`,
`Sources/MLXFastModel/LagunaUpstreamEquivalence.swift:41-120`), which runs in
the test process and keeps stdout.

`verbose: true` was added at **48 invocation sites** — 33 in
`LagunaRuntimeModel.swift`, 9 in `LagunaRuntimeLayers.swift`, 6 in
`LagunaLmHeadPrune.swift` (`metalKernel(` *constructions* number 45/15/6, but
only 33/9/6 carry an `outputDTypes:` invocation). The exact edit is preserved
as `research/maple-frieren-r92-verbose-dump.patch` (517 lines, 48
`+verbose: true`).

Run: 18.8 s wall, `research/r92-runs/verbose-dump-all48.log` (12,033,105 B),
1717 kernel emissions. The oracle itself reported prefill
`maximumAbsoluteLogitError = 0.125` (mean 0.0119, argmax token 5991 matching
upstream) and **all 8 decode steps exactly 0.0**; the test "fails" only because
its tolerance is 0. The prefill residual is a non-M5 host artefact and is
recorded as a limit, not attributed to the instrumentation (see Limits).

**Reconstruction fidelity was validated, not assumed.** Extracting one dumped
translation unit (`laguna_dense_down_residual_bf16_v1.metal`) and compiling it
with `census.sh` exported exactly the symbol MLX's `kernel_name()` produces,
with matched flags — so the TU in the log is the TU the driver compiles.

### Dispatch decomposition

`prefill = 115`, `decode step 0 = 202`, `steps 1–7 = 200` each;
115 + 202 + 7×200 = 1717 ✓. A steady decode step, counting instrumented custom
kernel dispatches only:

| kernel | dispatches / step |
|---|---|
| `laguna_residual_rms_router_bf16_2048_rpg8_keys_v1_pf1` | 39 |
| `laguna_prefill_router_tournament_ordinal_norm_active64_v2` | 39 |
| `laguna_fused_norm_qkv_projection_bf16_h64_v3` | 30 |
| `laguna_sliding_fused_attn_ring_v1` | 30 |
| `laguna_gated_output_projection_bf16_h64_u2_v3` | 30 |
| `laguna_fused_norm_qkv_projection_bf16_h48_v3` | 10 |
| `laguna_full_fused_attn_grow_v1` | 10 |
| `laguna_gated_output_projection_bf16_h48_u2_v3` | 10 |
| `laguna_residual_rms_bf16_2048_v1` | 1 |
| `laguna_dense_down_residual_bf16_v1` | 1 |

Artifacts: `research/r92-artifacts/r92-kernel-dispatch-trace.txt`,
`research/r92-artifacts/r92-dispatch-segmentation.txt`,
`research/r92-artifacts/r92-kernel-manifest.tsv`.

## Stage 1′ — the oracle vehicle never reaches the NVFP4 experts

The Stage-1 dump contains **zero** occurrences of `nvfp4`. The fused NVFP4
routed-expert kernels are decode-dominant and are the only genuinely
integer-ALU-heavy kernels in the model (nibble unpack,
`bank_tile = logical_row/4`, `sub = logical_row%4`, packed-scale address
arithmetic). They were never dispatched.

Root cause: `LagunaUpstreamEquivalence` loads the raw **dense safetensors**
store (`LagunaUpstreamEquivalence.swift:52,66-84` → `loadRuntimeWeightArrays`,
`Sources/MLXFastModel/RuntimeWeightLoading.swift:12-37`), not the
MLXFastTransform NVFP4 packed bank. The guard chain at
`Sources/MLXFastModel/LagunaRuntimeLayers.swift:2014-2060` therefore fails
(`fusedWeight.dtype == .uint32`, `fusedScales.dtype == .uint8`,
`_packedRoutedGateUpBank`, …) and the stock gather-GEMM path runs instead.

This is a **rule 39 reachability failure of the measurement vehicle**, and it
was found late. It is reported prominently because it means H1 was, at the end
of Stage 3, untested exactly where it is most plausible.

<!-- STAGE1PRIME_RESULT -->

## Stage 2 — census of every reachable scored decode kernel

`research/r92-artifacts/r92-census.tsv` (60 rows, studies `r92_floor`,
`r92_encoding`, `r92_decode`). "corrected" applies the Control-2 bracket;
"noise" is |Δ| ≤ 16 B after correction.

| kernel | /step | sig | g16s | g17s | raw Δ | corrected | % | verdict |
|---|---|---|---|---|---|---|---|---|
| `laguna_sliding_fused_attn_ring_v1` | 30 | simd | 7168 | 7296 | **+128** | +128..+144 | +1.8 | **g17s excess** |
| `laguna_full_fused_attn_grow_v1` | 10 | simd | 8000 | 8144 | **+144** | +144..+160 | +1.8 | **g17s excess** |
| `laguna_full_qk_norm_yarn_bf16_128_v4` | 0 | simd | 2912 | 2912 | +0 | — | 0 | noise |
| `laguna_prefill_moe_tail_bf16_v1` | 0 | plain | 2624 | 2624 | +0 | — | 0 | noise |
| `laguna_residual_rms_bf16_2048_v1` | 1 | simd | 2288 | 2272 | −16 | −16..0 | −0.7 | noise |
| `laguna_prefill_router_tournament_ordinal_norm_active64_v2` | 39 | plain | 4720 | 4688 | −32 | −32..−16 | −0.7 | noise |
| `laguna_residual_rms_router_bf16_2048_rpg8_keys_v1_pf1` | 39 | simd | 4128 | 4016 | −112 | −112..−96 | −2.7 | g17s cheaper |
| `laguna_dense_down_residual_bf16_v1` | 1 | simd | 2944 | 2752 | −192 | −192..−176 | −6.5 | g17s cheaper |
| `laguna_gated_output_projection_bf16_h48_u2_v3` | 10 | simd | 2976 | 2784 | −192 | −192..−176 | −6.5 | g17s cheaper |
| `laguna_gated_output_projection_bf16_h64_u2_v3` | 30 | simd | 2976 | 2784 | −192 | −192..−176 | −6.5 | g17s cheaper |
| `laguna_fused_norm_qkv_projection_bf16_h48_v3` | 10 | simd | 8048 | 7632 | −416 | −416..−400 | −5.2 | g17s cheaper |
| `laguna_fused_norm_qkv_projection_bf16_h64_v3` | 30 | simd | 8064 | 7648 | −416 | −416..−400 | −5.2 | g17s cheaper |

Weighted positive static g17s excess per steady decode step:
30 × 128 + 10 × 144 = **+5280 B**.

Note the sign spread. The scored router
`..._ordinal_active64_v2_...` censuses 4720 / 4688 here, in the same direction
as the advisor's counter-evidence datapoint (4304 / 4272 in #481; the numeric
difference is a different reconstruction of the same family, see Limits). g17s
is not uniformly "worse at integers"; it is *differently* compiled.

## Stage 3 — ablation bisection of the two positive kernels

`research/r92-artifacts/r92-bisect.tsv`. Each row substitutes or deletes one
mechanism in the dumped TU and re-censuses both arches. `ΔvsBase` is the change
in the g17s−g16s gap; a positive `ΔvsBase` means the ablation made the gap
*worse*, i.e. the ablated mechanism was not the cause.

| ablation | sliding g16s/g17s/Δ | ΔvsBase | grow g16s/g17s/Δ | ΔvsBase |
|---|---|---|---|---|
| base | 7168 / 7296 / +128 | — | 8000 / 8144 / +144 | — |
| `ring_pred_const` | 7040 / 7200 / +160 | +32 | 7872 / 8048 / +176 | +32 |
| `ring_branch_dead` | 7040 / 7200 / +160 | +32 | 7808 / 8000 / +192 | +48 |
| `ring_both` | 7040 / 7200 / +160 | +32 | 7808 / 8000 / +192 | +48 |
| `rope_prologue_dead` | 5424 / 5536 / +112 | −16 | 5952 / 6080 / +128 | −16 |
| `addr_uint32` | 7184 / 7280 / +96 | −32 | 7904 / 8080 / +176 | +32 |
| `rescale_bitcast_dead` | 7136 / 7248 / +112 | −16 | 7952 / 8080 / +128 | −16 |
| **`no_simd_sum`** | 7072 / 7152 / +80 | **−48** | 7904 / 7968 / +64 | **−80** |
| `no_simd_sum_loop` | 7136 / 7248 / +112 | −16 | 7952 / 8080 / +128 | −16 |
| **`no_simd_sum_epilogue`** | 7120 / 7200 / +80 | **−48** | 7952 / 8048 / +96 | **−48** |
| `no_simd_sum_prologue` | 7168 / 7280 / +112 | −16 | 8000 / 8128 / +128 | −16 |
| `no_simd_max` | 7152 / 7264 / +112 | −16 | 7984 / 8096 / +112 | −32 |
| `no_fast_exp` | 7008 / 7120 / +112 | −16 | 7776 / 7904 / +128 | −16 |
| `simd_sum_ladder` | 8112 / 8208 / +96 | −32 | 9072 / 9168 / +96 | −48 |
| `epilogue_vec_simd_sum` | 7168 / 7296 / +128 | **+0** | 8000 / 8144 / +144 | **+0** |
| `N_128` | 7152 / 7280 / +128 | +0 | n/a | — |
| `N_256` | 7152 / 7280 / +128 | +0 | n/a | — |
| `N_1024` | 7168 / 7296 / +128 | +0 | n/a | — |

### What Stage 3 establishes

- **The main loop is rolled.** Δ is invariant across N ∈ {128, 256, 1024}
  while absolute bytes barely move. Rule 42's "`unroll(full)` is ignored for
  large loops" holds here.
- **Exonerated** (ablation is noise-band or wrong-signed): the ring-buffer
  index substitution, the RoPE prologue (deleting 1744 B of it moves Δ by only
  −16 B), the rescale bitcast, `fast::exp`, `simd_max`, the prologue RMS
  `simd_sum`, and the hot-loop `simd_sum`.
- **`simd_sum` carries the excess, in the epilogue.** Removing all `simd_sum`
  recovers 48 B (sliding) / 80 B (grow) of gap; removing only the epilogue
  ones recovers 48 B in both. Per site the epilogue's 10 `simd_sum` calls cost
  48 B on g16s and 96 B on g17s (**+100 %**), while hot-loop and prologue sites
  cost the same on both arches. The epilogue executes **once per launch**, so
  this static excess carries very little dynamic weight.
- **No surviving rewrite.** `epilogue_vec_simd_sum` censuses byte-identical to
  base on both arches — the compiler already canonicalises four componentwise
  `simd_sum` calls into whatever it wants, exactly rule 42's canonicalisation
  prediction. `simd_sum_ladder` (5-stage `simd_shuffle_xor` butterfly, BD=32)
  is +944 B / +912 B, so the builtin is already the compact lowering; it is
  also not guaranteed bit-exact.
- **`addr_uint32` is not a matched null and not robust.** It flips Δ sign
  (−32 sliding, +32 grow). Its absolute g17s bytes do fall in both kernels
  (−16, −64) while g16s *rises* in sliding (+16) — superficially the
  "invisible on M4" signature the assignment asked for — but it changes opcode
  class, so rule 42 forbids reading it as a matched-null difference.
  Decisively, **all four `(size_t)` casts live in the once-per-launch
  prologue** (sliding `:139,140,142,143,155,156,158,159`; grow
  `:147,148,150,151,163,164,166,167`). The hot loop advances
  `pair_keys` / `pair_values` by `int` strides
  (`inner_k_stride` / `inner_v_stride`), so loop addressing is 64-bit pointer
  arithmetic either way. (For the record the ranges do fit uint32:
  `window * head_dim` = 65536 with `kv_head` < 8 → 524288 max; full-attention
  `seq` ≤ 640 → 655360.)

## Limits

1. **Static bytes are not time.** Nothing in this report is a timing
   measurement. Rule 42 admits the census only as a matched-null difference
   within one opcode class and one loop structure, and the biggest signal here
   (`simd_sum` epilogue) sits in code that runs once per launch.
2. **`g17s = M5 Max` is an inference.** It is not documented anywhere in the
   toolchain. Everything reported for g17s is a cross-compilation result, not
   an M5 measurement. No AGX disassembler exists, so the mapping from bytes to
   opcodes is unavailable in principle.
3. **This host is M4 Pro = g16s.** It reports Apple GPU generation 16 and does
   not select the `_nax` prefill kernels the ranked M5 uses, so no result here
   is evidence about `_nax` code.
4. **The oracle prefill logit error is 0.125.** Decode steps are exact
   (0.0). An unchanged-base equivalence control run to attribute this residual
   to the host rather than to the 48 `verbose:` flags was **not** run — the
   flags only set a debug-print bit in the MLX kernel constructor and cannot
   change numerics, but that argument is not a measurement, so the residual is
   recorded as an open item.
5. **Mechanical reconstruction of interpolated-template kernels is
   intractable at this budget**, which is why Stage 1 used the runtime's own
   dump instead. The routed NVFP4 kernels compose `header:` from three
   concatenated header strings and three runtime interpolations
   (`lagunaScalePatchHeaderBytes` = 128,
   `Sources/MLXFastModel/LagunaRuntimeWeights.swift:985`;
   `lagunaNvfp4RowScaleSuffix`, `LagunaRuntimeModel.swift:6685,6695`;
   `lagunaRouterTop8PrecomputedPrelude`, `:7816-7827`), and faithfully
   replicating MLX's TU generator by hand was judged too error-prone. The
   corollary is that #481's `router_real` figures (4304 / 4272) are a
   hand-reconstruction and should be superseded by the Stage-2 dump-derived
   4720 / 4688 for the same family.
6. **Dispatch counts are instrumented-site counts.** The 200/step figure
   counts custom `metalKernel` dispatches carrying `verbose:`; stock MLX
   primitives are not counted.

## Recommended next arm

Census the fused NVFP4 routed-expert kernels
(`laguna_routed_nvfp4_swiglu_qmv_packed_top8keys_r1_bf16_v2`,
`laguna_routed_nvfp4_down_reduce_bf16_v2`) on g16s vs g17s, using the real
transformed-weight path. Those kernels' hot loops contain the nibble unpack and
integer address arithmetic that the uint-MAD encoding penalty actually taxes;
they are also ~30 % of decode dispatch weight. If a matched-null g17s excess
exists anywhere on this model, it is there. If it does not, H1 should be closed.

## Reproduction

```bash
# Stage 1: MSL dump via the equivalence oracle (research-only instrumentation)
python3 senpai/tools/agx-census-probe/add_verbose_dump.py     # adds 48 verbose: true
bash senpai/tools/agx-census-probe/run_verbose_dump.sh research/r92-runs/verbose-dump-all48.log
python3 senpai/tools/agx-census-probe/split_verbose_dump.py \
    research/r92-runs/verbose-dump-all48.log research/r92-runs/kernels \
    research/r92-runs/router-recon/preamble.metal
python3 senpai/tools/agx-census-probe/segment_dispatches.py research/r92-runs/verbose-dump-all48.log

# Stage 2: census
bash senpai/tools/agx-census-probe/run_r92_census.sh research/r92-runs/kernels research/r92-runs/r92-census.tsv
python3 senpai/tools/agx-census-probe/analyze_r92_census.py \
    research/r92-runs/r92-census.tsv research/r92-runs/kernels research/r92-runs/order.txt

# Stage 3: ablation bisection
python3 senpai/tools/agx-census-probe/bisect_attn.py \
    research/r92-runs/kernels research/r92-runs/bisect research/r92-runs/r92-bisect.tsv
```

All instrumentation is reverted in the final commit; the submitted editable
surface for this experiment is **zero bytes changed**.
