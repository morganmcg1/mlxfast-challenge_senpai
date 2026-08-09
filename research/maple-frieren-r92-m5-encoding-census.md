# r92-b — differential g16s-vs-g17s encoding census of the scored decode path

**Student:** maple-frieren · **PR:** #490 · **assignment:** `maple-r92-b-m5-encoding-census`
(rev `r92-b-rev1`) · **base:** `8486638578a283de40369172f68c3a4d2d6a5365`
· **host:** Apple M4 Pro, 48 GiB (low-memory startup profile) · **date:** 2026-08-09

## Verdict

**H0.** There is a real, reproducible static g17s excess on the scored decode
path, but it is not the uint-MAD phenomenon that H1 requires, and no concrete
rewrite survived census.

Specifically:

1. The excess is real, broad, and it is **positive in aggregate**. Thirteen of
   the 21 kernels in a true scored steady decode step are larger on g17s. The
   dispatch-weighted figures are **+32144 .. +36608 static `__compute` bytes of
   positive g17s excess per steady decode step**, and a **net** of
   **+25536 .. +31344 B, g17s larger**. The largest single Δs are
   `laguna_oproj_act_h64_v1_…` (+192 B, +3.7 %) and
   `laguna_lmhead_int5_base_coarse_delta_bf16_v1` (+336 B, +8.6 %).
2. Eight kernels are *smaller* on g17s, by up to 384 B
   (`laguna_dense_gate_up_swiglu_bf16_v1`, −9.6 %). So g17s codegen differs
   from g16s in several opposing ways and any single Δ is a **net**, never an
   instruction count. This independently re-confirms rule 42's retirement of
   `(bytes − floor)/8`.
3. **Stage 2's aggregate is retracted.** It censused the kernel set the
   upstream-equivalence oracle dispatches, and four of its five largest "g17s
   is cheaper" datapoints — the `fused_norm_qkv_projection` and
   `gated_output_projection` families — are **never dispatched on the scored
   path**, which substitutes NVFP4 decode kernels. Stage 2 reported +5280 B
   positive and −24864 B net; the scored path flips that net sign. Stage 1′ is
   the authoritative census. This is the central methodological lesson of the
   arm: a census is only as good as its vehicle's dispatch trace.
4. Stage-3 ablation (run on the two attention kernels, which *are* on the
   scored path) localises ~40–55 % of the two positive Δs to the
   `simd_sum` family, and within that family to the **epilogue**, which runs
   once per launch. `simd_sum` is a shuffle reduction, not the uint-MAD opcode
   class that rule 42 identifies as H1's entire physical basis.
5. The uint-MAD encoding penalty itself was reproduced exactly (12.0 B/op g16s
   → 14.0 B/op g17s, +16.7 %, on an operation touching no memory). But the hot
   loops of both positive kernels are float-FMA / `simd_sum` / `simd_max` /
   `fast::exp` dominated, and float FMA encodes at **6.0 B/op on both
   arches**. The physical mechanism H1 needs is absent from the code that
   actually spins.
6. Both concrete rewrites suggested by the localisation were **falsified by
   census**: fusing the four componentwise epilogue `simd_sum` calls into one
   `float4` `simd_sum` censuses **byte-identical on both arches** (compiler
   canonicalisation — rule 42's first hypothesis), and a hand-written
   `simd_shuffle_xor` butterfly is **+944 B g16s / +912 B g17s** (the builtin
   lowers far more compactly).
7. The integer-ALU-heavy fused NVFP4 routed-expert kernels — the single most
   plausible home for H1, and the reason Stage 1′ was built — were reached and
   censused. They come in at **+64 to +96 B (+1.3 % to +2.3 %)**, the
   *smallest* relative deltas among the positive kernels. The ranking is
   therefore **not** ordered by integer-ALU density, which is the strongest
   single piece of evidence against H1 produced by this arm.

What survives as actionable is a *map*, not a lever: the positive g17s excess
on the scored decode step is concentrated 43 % in the o-proj/gate cluster
(`laguna_oproj_act_h{48,64}` + `laguna_gate_sp_h{48,64}`) and 29 % in the NVFP4
MoE trio. That ranking is the opposite of what the oracle-path census implied,
and it is the input a successor arm should use.

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

## Stage 1′ — the oracle vehicle dispatches a *different kernel set*

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

### Why stdout could not simply be reopened, and the vehicle that worked

Three separate mechanisms had to be defeated, and each was confirmed
empirically rather than assumed:

1. **The worker discards stdout.** `RuntimeWorkerProtocolIO.isolatingStandardIO`
   (`Sources/MLXFastHarness/LagunaRuntimeWorker.swift:1187-1203`) redirects
   stdin *and* stdout to `/dev/null`; only stderr survives.
2. **The worker sandbox forbids opening a file.** The generated profile is
   `(deny file-write*)` with a single `/dev/null` exception
   (`writeRuntimeWorkerSandboxProfile`,
   `Sources/MLXFastCLI/main.swift:1612-1659`). Writing the dump to a research
   path therefore fails inside the worker. The dump must travel out through the
   **already-open stderr pipe**.
3. **Most CLI subcommands do not forward worker stderr.**
   `runtimeWorkerOptions` (`main.swift:1239-1319`) defaults
   `forwardsWorkerStderr: Bool = false`, and the *only* call site passing
   `true` is the local-iterate / local-submit benchmark (`main.swift:315-318`).
   `runCorrectness` (`:161`), `runCorrectnessTrace` (`:208`) and `runPreflight`
   (`:240`) take the default, so `WorkerStderrDrain` is constructed with
   `emit: { _ in }` (`LagunaRuntimeWorker.swift:1531`, `:1655`) and the pipe is
   drained into nothing. A canary job (`correctness-trace --step 1`, exit 0,
   45.3 s) produced a 549-byte log with **zero** `R92CANARY`,
   `mlxfast-worker:` or `Generated source code` lines, confirming this.

The working vehicle is therefore `./benchmark.sh --local-iterate` itself, with
`dup2(STDERR_FILENO, STDOUT_FILENO)` performed once inside the model module
behind `DARKBLOOM_R92_DUMP_TO_STDERR=1`, and a per-process emission budget
(`DARKBLOOM_R92_DUMP_LIMIT`) so the forwarder is not swamped. Forwarded lines
carry the `"mlxfast-worker: "` prefix (`main.swift:1284`) and pass through
`redactedWorkerStderrLine` (`:1392`), which rewrites any line containing
"expected"/"actual" and any line longer than 65536 B; the strip step verifies
`redacted_lines=0` so no MSL was mangled.

Run: 256.6 s wall, `research/r92-runs/scored-dump.log` = 21,275,521 B,
**2690 emissions, 7566 `nvfp4` hits, 27 distinct kernels, 0 multi-variant**.
The run passed correctness in-band (`passed_correctness: true`,
`max_abs_diff: 0`, golden hash `b9509697…a58d7a63`). Its own score was 0.455
against the 0.796 local baseline; that −42.9 % is **the cost of the dump**
(MLX re-emits the whole TU on every dispatch), not a candidate regression, and
it is recorded in W&B under `vehicle/*` so it can never be misread as one.

### The scored steady decode step is 363 dispatches, measured

The step boundary was *measured*, not assumed: the ordered dispatch list was
split on `laguna_decode_embedding_rope_atlas_bf16_2048_v2`, which occurs
exactly once per step. Five steps were captured before the budget ran out, of
sizes 690 / 527 / 363 / 363 / 363, and the **last two are byte-identical
multisets** — that identity is the steady-state proof. `weight_scored_step.py`
exits non-zero if no two consecutive steps agree or if any dispatched kernel is
missing from the census, so the weights cannot silently drift.

(Step 3 is also 363 but substitutes `laguna_full_qk_norm_yarn_bf16_128_v4` ×10
for `laguna_full_fused_attn_grow_v1` ×10 — a 1:1 substitution selected by
KV-capacity state, Δ +0 versus +144. It is a real alternative steady step and a
mildly *cheaper* one on g17s.)

### Kernels Stage 2 censused that the scored path never dispatches

| kernel | oracle /step | scored /step | Stage-2 Δ |
|---|---|---|---|
| `laguna_fused_norm_qkv_projection_bf16_h64_v3` | 30 | **0** | −416 |
| `laguna_fused_norm_qkv_projection_bf16_h48_v3` | 10 | **0** | −416 |
| `laguna_gated_output_projection_bf16_h64_u2_v3` | 30 | **0** | −192 |
| `laguna_gated_output_projection_bf16_h48_u2_v3` | 10 | **0** | −192 |
| `laguna_prefill_moe_tail_bf16_v1` | 0 | **0** | +0 |

The scored path substitutes NVFP4 decode kernels
(`laguna_decode_nvfp4_qkv_h{48,64}_r1_v1_…`, `laguna_oproj_act_h{48,64}_v1_…`,
`laguna_gate_sp_h{48,64}_v1`, and the routed/shared NVFP4 SwiGLU + down-residual
trio). **Every one of the four largest "g17s is cheaper" datapoints in Stage 2
is off the scored path.** Stage 2's dispatch-weighted aggregates are therefore
**retracted**, and the sign of the aggregate flips.

### Scored-path census (the result that supersedes Stage 2)

`research/r92-artifacts/r92-census-scored.tsv` (90 rows) and
`research/r92-artifacts/r92-census-stage1prime.txt`. `w_raw` = `n · Δ`;
`w_hi` = `n · (Δ + 16)`, i.e. the Control-2 floor bracket carried through the
weighting.

| kernel | n | g16s | g17s | Δ | % | w_raw | w_hi |
|---|---|---|---|---|---|---|---|
| `laguna_oproj_act_h64_v1_lm1_pw1_sc1_se1` | 30 | 5216 | 5408 | **+192** | +3.7 | 5760 | 6240 |
| `laguna_gate_sp_h64_v1` | 30 | 5632 | 5792 | **+160** | +2.8 | 4800 | 5280 |
| `laguna_sliding_fused_attn_ring_v1` | 30 | 7168 | 7296 | +128 | +1.8 | 3840 | 4320 |
| `laguna_routed_shared_nvfp4_down_residual_bf16_sh_stage4_v6` | 39 | 5056 | 5152 | +96 | +1.9 | 3744 | 4368 |
| `laguna_shared_nvfp4_swiglu_qmv_rows1_halved_bf16_v1` | 39 | 3488 | 3568 | +80 | +2.3 | 3120 | 3744 |
| `laguna_routed_nvfp4_swiglu_qmv_packed_top8keys_r1_bf16_v2` | 39 | 4944 | 5008 | +64 | +1.3 | 2496 | 3120 |
| `laguna_decode_nvfp4_qkv_h64_r1_v1_lm1_pw1_se1_sd1` | 30 | 3584 | 3664 | +80 | +2.2 | 2400 | 2880 |
| `laguna_oproj_act_h48_v1_lm1_pw1_sc1_se1` | 10 | 5216 | 5392 | +176 | +3.4 | 1760 | 1920 |
| `laguna_gate_sp_h48_v1` | 10 | 5632 | 5792 | +160 | +2.8 | 1600 | 1760 |
| `laguna_full_fused_attn_grow_v1` | 10 | 8000 | 8144 | +144 | +1.8 | 1440 | 1600 |
| `laguna_decode_nvfp4_qkv_h48_r1_v1_lm1_pw1_se1_sd1` | 10 | 3584 | 3664 | +80 | +2.2 | 800 | 960 |
| `laguna_lmhead_int5_base_coarse_delta_bf16_v1` | 1 | 3888 | 4224 | **+336** | +8.6 | 336 | 352 |
| `laguna_lmhead_exact_fused_int5_sparse_refine_v1` | 1 | 6528 | 6576 | +48 | +0.7 | 48 | 64 |
| `laguna_residual_rms_bf16_2048_v1` | 1 | 2288 | 2272 | −16 | −0.7 | −16 | 0 |
| `laguna_decode_embedding_rope_atlas_bf16_2048_v2` | 1 | 2080 | 2048 | −32 | −1.5 | −32 | −16 |
| `laguna_lmhead_exact_winner_bf16_midpoint_threshold_v1` | 1 | 3104 | 2944 | −160 | −5.2 | −160 | −144 |
| `laguna_dense_down_residual_bf16_v1` | 1 | 2944 | 2752 | −192 | −6.5 | −192 | −176 |
| `laguna_lmhead_coarse_argmax_stage1_v5` | 1 | 2992 | 2784 | −208 | −7.0 | −208 | −192 |
| `laguna_dense_gate_up_swiglu_bf16_v1` | 1 | 4016 | 3632 | −384 | −9.6 | −384 | −368 |
| `laguna_prefill_router_tournament_ordinal_norm_active64_v2` | 39 | 4720 | 4688 | −32 | −0.7 | −1248 | −624 |
| `laguna_residual_rms_router_bf16_2048_rpg8_keys_v1_pf1` | 39 | 4128 | 4016 | −112 | −2.7 | −4368 | −3744 |

- **weighted positive g17s excess = +32144 .. +36608 B / steady step**
  (Stage 2 said +5280 on a kernel set that is partly off-path).
- **weighted net Δ = +25536 .. +31344 B / steady step, g17s LARGER.**
  Stage 2's off-path net was −24864 B, i.e. the aggregate **sign flips** once
  the true scored kernel set is used.

Cluster ranking of the positive excess (`w_raw`):

| cluster | B / step | share |
|---|---|---|
| o-proj pair — `oproj_act` + `gate_sp`, h64 and h48 | 13920 | 43 % |
| NVFP4 MoE trio — routed SwiGLU, shared SwiGLU, down-residual | 9360 | 29 % |
| decode attention pair — sliding ring + full grow | 5280 | 16 % |
| NVFP4 QKV pair — h64 + h48 | 3200 | 10 % |

Six further kernels appear only in warm-up or prefill and are excluded from the
steady weighting: `laguna_lmhead_int5_inline_coarse_ratio_bound_delta_bf16_v6`
4352 → 4784 = **+432, +9.9 %, the largest relative positive Δ in the entire
census**; `laguna_lmhead_exact_inline_mask_block_delta_bf16_lane0_mask_v1`
−208; `laguna_prefill_full_qk_norm_yarn_bf16_128_h1_v2` +48;
`laguna_prefill_sliding_qk_norm_rope_bf16_128_h1_v2` +48;
`laguna_prefill_sorted_moe_tail_bf16_v1` 0;
`laguna_full_qk_norm_yarn_bf16_128_v4` 0.

Both controls reproduced **exactly** in the same census invocation: uint MAD
2032/2416/3184 → 2080/2528/3424 (12.0 → 14.0 B/op, +16.7 %), every float arm
at −16 B, and `floor_buf4_bf16_simd` at Δ 0.

### What this does *not* change

It does not rescue H1. The NVFP4 kernels — the integer-ALU-heavy family, and
the family this stage was built to reach — census at **+64 to +96 B, i.e.
+1.3 % to +2.3 %**, the *smallest* relative deltas among the positive kernels.
The largest positives are `oproj_act` (+3.7 %) and the int5 LM-head delta
kernels (+8.6 %, +9.9 %). So the ranking is not ordered by integer-ALU density,
and no Stage-3-style rewrite has been shown to remove any of it. The verdict
stays H0; what changes is the *direction* of the map, and the target list for
any successor arm.

### Retroactive validation of PR #481's router census

PR #481 censused `laguna_prefill_router_tournament_ordinal_norm_active64_v2` from
a hand reconstruction at 4304 / 4272 B. The real dumped translation unit
censuses 4720 / 4688 B. The absolute figures are **416 B (≈9 %) short**, so
hand-reconstructed absolute byte counts should not be trusted — but
**Δ = −32 B reproduces exactly**. #481's arch-delta conclusion therefore
stands while its absolute numbers do not, which is precisely the admissibility
boundary rule 42 draws.

## Stage 2 — census of the oracle-path decode kernels (weights SUPERSEDED)

> Retained for the record and because its per-kernel Δs for the five kernels
> that *are* on the scored path (`sliding_fused_attn_ring`,
> `full_fused_attn_grow`, `residual_rms`, `router_tournament`,
> `residual_rms_router`, `dense_down_residual`) reproduce exactly in Stage 1′.
> Its **dispatch weights and both aggregates are retracted**; see Stage 1′.

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

**RETRACTED aggregate.** Weighted with the oracle's own 200-dispatch step, the
positive static g17s excess was 30 × 128 + 10 × 144 = **+5280 B** and the net
was **−24864 B** (g17s smaller). Both numbers are wrong for the scored path:
seven of the twelve rows above, including the two largest-magnitude negatives
(`fused_norm_qkv_projection_*`, Δ −416) and the mid-sized `gated_output_projection_*`
(Δ −192), are **never dispatched** when the runtime is scored. Stage 1′ replaces
this aggregate; the per-kernel Δs for the five kernels that *are* on the scored
path survive unchanged and reproduce exactly.

Note the sign spread. The scored router
`..._ordinal_active64_v2_...` censuses 4720 / 4688 here, in the same direction
as the advisor's counter-evidence datapoint (4304 / 4272 in #481). Stage 1′
resolves that numeric gap: the real dumped translation unit is 416 B larger than
the #481 reconstruction on both arches, and the **Δ = −32 reproduces exactly**
(see "Retroactive validation of PR #481's router census"). g17s is not uniformly
"worse at integers"; it is *differently* compiled.

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
   intractable at this budget**, which is why every stage used the runtime's own
   dump instead. The routed NVFP4 kernels compose `header:` from three
   concatenated header strings and three runtime interpolations
   (`lagunaScalePatchHeaderBytes` = 128,
   `Sources/MLXFastModel/LagunaRuntimeWeights.swift:985`;
   `lagunaNvfp4RowScaleSuffix`, `LagunaRuntimeModel.swift:6685,6695`;
   `lagunaRouterTop8PrecomputedPrelude`, `:7816-7827`), and faithfully
   replicating MLX's TU generator by hand was judged too error-prone. This is
   also the direct cause of the 416 B absolute gap against #481's
   hand-reconstructed router: see the dedicated Stage 1′ subsection. Use the
   dump-derived figures for absolute bytes; #481's Δ is still valid.
6. **Dispatch counts are instrumented-site counts.** Both the oracle-path
   200/step figure and the scored-path **363/step** figure count custom
   `metalKernel` dispatches carrying `verbose:`; stock MLX primitives (`matmul`,
   `softmax`, elementwise, copies) are not counted, so neither number is a
   total GPU-encode count. The two are not comparable to each other either:
   they are different kernel *sets*, not the same set at different densities.
7. **The scored dump is budget-truncated, so manifest occurrence counts are
   not weights.** `run_scored_dump.sh` sets `DARKBLOOM_R92_DUMP_LIMIT=2000`
   emissions *per worker process*; the run emitted 2690 across processes and
   then went silent, so `research/r92-runs/kernels-scored/manifest.tsv`
   occurrence counts (and the equivalent Stage-2 manifest counts) are
   arbitrary prefixes of the true dispatch stream. Every weight in the scored
   census comes from `weight_scored_step.py`, which derives the steady step
   from the last two *byte-identical consecutive* decode-step histograms in
   `scored-order.txt` and refuses to emit if no two consecutive steps match or
   if any dispatched kernel is uncensused. Manifest counts appear in this
   report only as provenance, never as multipliers.

## Recommended next arm

Two options, in order of what the evidence supports.

**(a) Close H1.** This is the recommendation. H1 predicted that g17s pays an
encoding surcharge concentrated in integer-ALU-dense code, so the scored kernel
ranking should track integer density. It does not. The three NVFP4 routed/shared
expert kernels — the most integer-dense code on the model, full of nibble
unpacking and packed-key address arithmetic — census at **+1.3 % .. +2.3 %**,
while the two largest positive contributors are the bf16 output-projection and
gate kernels at **+3.2 % .. +3.7 %** and the single largest *relative* positive
is an int5 LM-head warm-up kernel at **+9.9 %** that runs once. The uint-MAD
12.0 → 14.0 B/op surcharge is real and reproduced (Control 1), but the compiler
does not put enough of it in the hot loops for it to order the ranking. There is
no lever here, only a map.

**(b) If the advisor wants one more census arm**, the target is no longer the
NVFP4 trio — Stage 1′ already censused it. It is the **o-proj/gate cluster**,
`laguna_oproj_act_h{48,64}_v1_lm1_pw1_sc1_se1` (Δ +192 / +176) plus
`laguna_gate_sp_h{48,64}_v1` (Δ +160 / +160), which is **43 %** of the weighted
scored excess, twice the NVFP4 trio's 29 %. Apply the Stage-3 ablation method to
those four TUs to see whether their excess is also parked in a once-per-launch
`simd_sum` epilogue (in which case it is again not a lever) or in the hot loop
(in which case it is the first genuine candidate this line of work has produced).
Note that Stage 3 already falsified both concrete rewrites it generated, so this
arm should be budgeted as diagnosis, not as an expected win.

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

# Stage 1': MSL dump through the scored local-iterate worker (stderr forwarder)
bash senpai/tools/agx-census-probe/run_scored_dump.sh research/r92-runs/scored-dump.log
bash senpai/tools/agx-census-probe/strip_worker_prefix.sh \
    research/r92-runs/scored-dump.log research/r92-runs/scored-dump.msl
python3 senpai/tools/agx-census-probe/split_verbose_dump.py \
    research/r92-runs/scored-dump.msl research/r92-runs/kernels-scored \
    research/r92-runs/router-recon/preamble.metal
bash senpai/tools/agx-census-probe/run_r92_census.sh \
    research/r92-runs/kernels-scored research/r92-runs/r92-census-scored.tsv
python3 senpai/tools/agx-census-probe/weight_scored_step.py \
    research/r92-artifacts/r92-census-scored.tsv research/r92-runs/scored-order.txt
python3 senpai/tools/agx-census-probe/delta_table.py \
    research/r92-artifacts/r92-census-scored.tsv r92_decode

# W&B (all four stages)
WANDB_DIR=/tmp/r92-wandb WANDB_SILENT=true \
    python3 research/maple-frieren-r92-log-wandb.py all
```

`run_scored_dump.sh` must run through `run_job` on a clean worktree: it takes
the benchmark lock, holds the model, and honours the thermal gate. It takes
~257 s and writes ~21 MB.

## W&B runs

Project `wandb-applied-ai-team/mlxfast-maple`, group `maple-frieren-r92b`.

| stage | run | URL |
| --- | --- | --- |
| 1 — oracle dispatch decomposition | `vhtg9a79` | https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/vhtg9a79 |
| 2 — oracle-path matched census (weights superseded) | `ijkxcsuf` | https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/ijkxcsuf |
| 3 — attention ablation bisection | `uti0wmxo` | https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/uti0wmxo |
| **1′ — scored-path census (authoritative aggregate)** | **`g60bbuon`** | **https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/g60bbuon** |

All four are `finished`. Run 1′ carries 295 summary keys and supersedes run 2's
`stage2/weighted_*` aggregates; run 2 sets `stage2_weights_retracted=1` in run
1′'s summary rather than being deleted, so the retraction is auditable.

All instrumentation is reverted in the final commit; the submitted editable
surface for this experiment is **zero bytes changed**.
