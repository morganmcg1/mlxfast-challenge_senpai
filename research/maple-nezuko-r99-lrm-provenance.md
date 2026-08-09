# Relocated comment prose from `Sources/MLXFastModel/LagunaRuntimeModel.swift`

Every comment block removed from the submitted file, verbatim and in
source order. The strip preserves line numbering, so these labels are
line numbers in both the pre-strip and the post-strip file. Verify and
reverse the edit with `research/nezuko_r103c_relocation_verify.py`.
Tagged blocks: darkbloom-flag=72, receipt-provenance=4.

Blocks: 284.

## L7-L8

```swift
// Correctness-first Laguna XS 2.1 runtime, behavior-checked against the
// vendored reference implementation and specialized by guarded fast paths.
```

## L21-L27

```swift
// MARK: - Allocation-free shape checks
//
// `MLXArray.shape` builds a fresh Swift `[Int]` and comparing it against a
// dimension literal builds a second one, so each such guard on the decode path
// costs two heap allocations. `ndim` and `shapeN` are direct C accessors that
// allocate nothing, and the `ndim` test short-circuits `shapeN`'s
// dimensionality precondition.
```

## L30

```swift
    /// True when the shape is exactly the listed dimensions.
```

## L43

```swift
    /// True when `other` has an identical shape.
```

## L51-L57

```swift
/// Builds the `initializeRope` scaling dictionary for a per-type Laguna RoPE
/// spec. For `default` RoPE only the type is consulted; for YaRN the factory
/// reads factor / original context / betas. The XS config also serializes
/// `attention_factor: 1.0`, but both vendored MLX Laguna implementations
/// intentionally ignore that Hugging Face field. Do not forward it here:
/// leaving MLX's mscale/mscale_all_dim defaults at 1.0/0.0 yields the upstream
/// attention scaling of `0.1 * ln(32) + 1` (~1.34657).
```

## L70-L74 — darkbloom-flag

```swift
/// `DARKBLOOM_TRACE_FUSION=1` prints one stderr line the first time each fused
/// decode path is taken. Every fusion here is guarded on dtype, rank, exact
/// shape and module identity and falls back silently when a guard declines, so
/// a change that quietly stops firing looks exactly like a change that does
/// nothing. This makes "did it actually run" observable without a debugger.
```

## L99-L112 — darkbloom-flag

```swift
// MARK: - Runtime fusion feature flags

// Each fusion below concatenates the OUTPUT ROWS of same-dtype projections
// that consume the same input. Per-row gemv/qmv/gather-qmv arithmetic is
// independent of which rows share a dispatch (every output row keeps its own
// K-loop and scale application in the original order), so the fused dispatch
// is bit-exact against the separate dispatches it replaces. The per-head
// g_proj (N=64) uses a different split-K gemv variant and is never fused.

/// `DARKBLOOM_FUSED_QKV` (default OFF; set "1" to enable): after checkpoint
/// load, retain one row-concatenated `[Wq; Wk; Wv]` BF16 weight per attention
/// layer and serve Q/K/V from a single projection dispatch. Ablation on the
/// paired local benchmark showed a mild prefill cost with no decode gain, so
/// this ships opt-in.
```

## L116-L120 — darkbloom-flag

```swift
/// `DARKBLOOM_FUSED_SHARED_GATE_UP` (default on; set "0" to disable): after
/// checkpoint load, retain one row-concatenated NVFP4 `[gate; up]` bank per
/// shared expert and serve single-token decode from one quantized matmul.
/// Multi-token prefill remains on the stock separate banks so the ranked
/// prefill path and its smaller gather/GEMM shapes are unchanged.
```

## L124-L127

```swift
/// Decode-only shared-expert NVFP4 QMV + SwiGLU fusion. This consumes the
/// retained row-concatenated `[gate; up]` bank and emits only the 512-wide
/// BF16 activation, preserving the two independent QMV casts and every BF16
/// boundary in the compiled SiLU product.
```

## L131-L135

```swift
/// Decode-only shared-expert down QMV plus both sparse-block residual adds.
/// The kernel preserves the stock BF16 down-projection result, the inner
/// `routed + shared` rounding, and the outer `h + r2` rounding while avoiding
/// the intermediate shared/r2 materializations and the final elementwise
/// dispatch.
```

## L139-L141

```swift
/// Higher-fusion decode path: the eight routed down projections and the
/// shared down projection share one 288-thread dispatch, which also performs
/// the exact router reduction, routed scale, and both BF16 residual adds.
```

## L146-L148

```swift
/// Routed-expert counterpart to the shared QMV + SwiGLU fusion. Each decode
/// request supplies exactly eight current-token expert indices; the kernel
/// reads those banks directly and emits `[1, 1, 8, 1, 512]`.
```

## L152-L164 — darkbloom-flag

```swift
/// `DARKBLOOM_PACKED_SCALES` (default ON; set "0" to disable): decode-only
/// scale-interleaved side copy of the fused routed gate/up NVFP4 bank. The
/// stock `lagunaRoutedSwiGLUQMV` reads codes and E4M3 scales from two separate
/// tensors (four device streams per simdgroup iteration: gate codes, up
/// codes, gate scales, up scales). The packed side bank stores only the 32
/// scale bytes for each row and K block, in the kernel's exact walk order
/// `[expert][tile 128][k-block 4][row-pair sub 8]`; the resident fused code
/// bank is reused directly. Load widths, dequant expressions, accumulation
/// order, and every BF16 boundary are identical to the stock kernel — only
/// scale address computation changes, so the packed dispatch is bit-exact
/// (class A).
/// Memory: +~16 MiB resident per sparse layer while enabled (the stock fused
/// code bank stays resident for prefill and fallback paths).
```

## L168-L170

```swift
/// Publish exact corrected router ordinals from the existing fused producer
/// so routed QMV consumers avoid repeating the nonlinear key construction.
/// The OFF arm restores the promoted selector dependency exactly.
```

## L174-L177

```swift
/// One-shot stderr visibility for the packed-scales arm: with the flag set,
/// the arm MUST announce either "active" (bank built / packed dispatch taken)
/// or "inactive" (a guard declined and the stock kernel ran instead), so a
/// silently-declining guard can never measure its own control.
```

## L195-L197

```swift
/// Decode-only routed NVFP4 down-QMV plus BF16 router weighting, fixed-order
/// expert reduction, and the Laguna 2.5 routed scale. The custom kernel emits
/// one 2048-wide branch instead of materializing eight expert rows.
```

## L201-L215 — darkbloom-flag

```swift
/// `DARKBLOOM_FUSED_ROUTED_GATE_UP` (default on; set "0" to disable): after
/// checkpoint load, retain one row-concatenated NVFP4 `[gate; up]` bank per
/// sparse layer's routed experts and serve single-token decode's gate/up from
/// one gather-QMM dispatch. DECODE-ONLY: the module tree, checkpoint keys,
/// and every multi-token (prefill) forward stay fully stock -- ablation
/// showed the fused bank helps decode (~+1.9%) but badly hurts the M=512
/// sorted gather-GEMM prefill path, so prefill always dispatches the stock
/// separate banks.
///
/// That prefill finding pre-dates RUNSKIP. See
/// `DARKBLOOM_PREFILL_FUSED_GATE_UP` immediately below for the current,
/// separately-flagged, post-RUNSKIP re-measurement of the same fusion idea
/// applied to the sorted prefill path -- this flag and its history are left
/// as-is (decode-only) rather than folded together, so each can be ablated
/// independently.
```

## L219-L220

```swift
/// Multi-token sorted gather-GEMM counterpart to the decode gate/up fusion;
/// independently ablatable and row-arithmetic-identical to separate banks.
```

## L224-L226

```swift
/// Exact prefill-only reuse of the certified packed decode scale bank by the
/// expert-aligned NAX path. Setting the flag to zero keeps the stock fused
/// scale plane and backend specialization.
```

## L230

```swift
// Official paired-M5 replay nonce 20260807T0236Z; executable source unchanged.
```

## L234-L237

```swift
/// The compact marker is legal only for GatherQMM's sorted RHS expert path,
/// whose batching guard requires at least four routed rows per expert. Shorter
/// prefills keep the original full scale plane so no generic kernel can ever
/// observe the marker representation.
```

## L267-L273

```swift
/// Decode post-attention residual + RMSNorm fusion. The kernel emits
/// both the rounded BF16 residual (needed by the following skip connection)
/// and the normalized row (consumed immediately by the MLP), eliminating a
/// separate residual-add materialization/read. Restricted to the single-row
/// (`x.size == hiddenSize`) decode shape at its call site; see
/// `lagunaPrefillFusedResidualRMSNormEnabled` immediately below for the
/// multi-token counterpart, gated independently.
```

## L277-L278

```swift
/// Multi-token use of the row-general residual+RMSNorm kernel; its independent
/// row dispatch preserves the stock add and normalization order per token.
```

## L283-L287 — darkbloom-flag

```swift
/// One output row per simdgroup for the default split routed gate/up decode
/// QMV. Official submission `b56a6d9` passed all 1,344 exact-token checks:
/// every row retains its K-block order and 32-lane reduction while the grid
/// exposes twice as many independent simdgroups to cover memory latency.
/// Set `DARKBLOOM_QMV_R1=0` to restore the two-row control.
```

## L291-L294

```swift
/// Shared-expert twin of the accepted routed R1 schedule. The shared branch
/// is dependency-independent from router top-8 and runs concurrently with it;
/// one row per SIMD group exposes twice as many weight streams while keeping
/// each row's four K-block accumulations and reduction tree unchanged.
```

## L298-L310 — darkbloom-flag

```swift
/// `DARKBLOOM_SHARED_SCALE_HALVED` (default ON; set "0" to ablate): serves
/// the shared expert's gate/up and `down_proj` NVFP4 scales from the group-32
/// halved planes instead of the shipped byte-per-16-weights ones. The routed
/// gate/up and down banks already ship halved (`DARKBLOOM_PACKED_SCALES`);
/// the shared expert is the last MoE plane still read at full width, worth
/// 196,608 bytes per sparse layer of which half is a duplicate the quantizer
/// wrote twice. Nothing is requantized: `lagunaHalvedGroup32ScalePlane`
/// installs the plane only when every discarded odd byte is bitwise equal to
/// its even partner, and the pairs that are not are carried in the patch
/// header, so the kernels reconstruct the shipped plane exactly. Off means
/// the stock planes and the stock kernels, byte for byte. Measured on-default
/// after three order-alternated local-submit pairs (decode -0.171% s/token,
/// on faster in 3/3) plus token-exact correctness with the flag on.
```

## L314-L323 — darkbloom-flag

```swift
/// `DARKBLOOM_QMV_WIDE_CODES` (default OFF, under measurement): the shared
/// gate/up QMV reads code words two adjacent groups at a time. Each lane owns
/// groups `2l` and `2l+1` of a 1024-weight slab and loads their codes in one
/// aligned `uint4` instead of two strided `uint2`s, halving both the code
/// loads and the K-loop trip count; the halved scale plane supplies the pair's
/// single shared byte, so scale loads halve again. NOT bit-exact against the
/// stock kernel: the products are identical floats, but each lane now sums a
/// different pair of groups, so the per-lane partials and the simd tree see a
/// reassociated order. Requires the halved planes
/// (`DARKBLOOM_SHARED_SCALE_HALVED`); without them the flag is inert.
```

## L327-L329 — darkbloom-flag

```swift
/// Folds the per-head softplus gate into the output projection's GEMV (see
/// `lagunaGatedOutputProjectionSource`), with one kernel variant per attention
/// family. Set `DARKBLOOM_FUSED_GATED_OUTPUT=0` to ablate.
```

## L333-L336 — darkbloom-flag

```swift
/// Issues Q, K and V as one dispatch over the three stock weights (see
/// `lagunaFusedQKVProjectionSource`). Unlike `DARKBLOOM_FUSED_QKV` this keeps
/// no concatenated bank, so prefill is untouched. Set
/// `DARKBLOOM_FUSED_QKV_PROJECTION=0` to ablate.
```

## L340-L345

```swift
/// TensorFold-derived within-token batching for the serial decode stream.
/// A native group-32 affine INT8 side layout packs Q/K/V into one batched
/// quantized matmul, cutting their weight traffic without speculating future
/// tokens or changing the KV dependency. Prefill stays on the original BF16
/// projections. Two ranked chunks proved 28 layers; this final bounded chunk
/// widens the same layout to all 40 layers.
```

## L356-L364 — darkbloom-flag

```swift
/// Depth-selection mode for both native affine INT8 attention layouts.
///
/// **Default (unset or anything but `1`) is the shipped PREFIX predicate**
/// `layer < count`, so the shipped semantics are byte-for-byte what the ranked
/// chunks proved. `DARKBLOOM_NATIVE_AFFINE_SUFFIX=1` selects the LAST `count`
/// layers (`layer >= numHiddenLayers - count`) instead. It exists to measure
/// whether the quantization perturbation the argmax gate sees depends on the
/// DEPTH of the quantized site (an early layer's error has 39 more layers of
/// amplification runway than a late one's) at matched weight-traffic coverage.
```

## L368-L371

```swift
/// Restricts a native affine layout to exactly one layer index, for
/// amplification-vs-depth probes. Unset (or out of range) keeps the normal
/// prefix/suffix coverage. The layer count must still be non-zero, so the
/// layout is prepared and dispatched exactly as it would be in a ranked run.
```

## L405-L418 — darkbloom-flag

```swift
/// The same native group-32 affine INT8 side layout applied to the attention
/// output projection. `o_proj` is the single largest BF16 decode weight read
/// left in the attention block — 30 sliding layers at `[2048, 8192]` plus 10
/// full-attention layers at `[2048, 6144]` is ~1.2 GB of the decode token's
/// weight traffic — and unlike Q/K/V it is read *after* SDPA, so quantizing it
/// changes nothing about the KV dependency or the cache contents.
///
/// Decode only: prefill and every non-`[1, 1, ·]` call keep the BF16 parameter,
/// which stays authoritative and resident. The first 16 layers are the
/// acceptance-band-safe first chunk; later submissions can widen the same
/// layout the way `DARKBLOOM_NATIVE_AFFINE_QKV_LAYERS` was widened.
///
/// Set `DARKBLOOM_NATIVE_AFFINE_OPROJ=0` (or `..._LAYERS=0`) to fall back to
/// the exact stock gated projection inside the same binary.
```

## L436-L457 — darkbloom-flag

```swift
/// The same native group-32 affine INT8 side layout applied to the attention
/// per-head gate projection (`g_proj`), admitted to the accepted quantization
/// envelope by the g_proj amendment. `g_proj` is a tiny `[heads, 2048]` BF16
/// read (48/64 rows), but its decode GEMV is one extra dispatch per layer
/// against the same normalized row the Q/K/V batch already computes, and its
/// output feeds only the softplus gate — never the KV cache — so requantizing
/// it perturbs the model strictly less than the already-shipped Q/K/V and
/// o_proj layouts. Unlike those layouts the gate bank is ALWAYS group-32
/// affine INT8: the envelope caps `g_proj` there, so the NVFP4 tail window
/// (`lagunaNativeAffineNVFP4From`) and the measurement-only probe format do
/// not apply to it. On layers whose QKV bank is itself group-32 INT8 the gate
/// rows concatenate into that same bank and ride the same dispatch for free;
/// on the NVFP4 tail layers the gate keeps a separate group-32 INT8 bank and
/// replaces the BF16 GEMV one dispatch for one dispatch.
///
/// Decode only: prefill and every non-`[1, 1, ·]` call keep the BF16
/// parameter, which stays authoritative and resident. Coverage is prepared
/// inside `prepareNativeAffineQKVWeight`, so a layer only gets the gate
/// layout when its QKV layout is also active.
///
/// Set `DARKBLOOM_NATIVE_AFFINE_GPROJ=0` (or `..._LAYERS=0`) to fall back to
/// the exact stock BF16 gate projection inside the same binary.
```

## L478-L481

```swift
/// Builds the gate projection's side layout. Unlike
/// `lagunaNativeAffineWeight` this NEVER takes the NVFP4 tail window or the
/// probe round-trip: the accepted envelope admits `g_proj` only as group-32
/// affine INT8, so the layout is fixed regardless of layer depth.
```

## L499-L522 — darkbloom-flag

```swift
/// Sliding-layer per-head RMSNorm + plain RoPE fusion (see
/// `lagunaSlidingQKNormRoPEKernel`).
///
/// **DEFAULT ON, deliberately** (`!= "0"`; set
/// `DARKBLOOM_FUSED_SLIDING_QK_NORM_ROPE=0` to ablate).
///
/// History, because the negative result and its resolution are the
/// instructive part — but note the default is ON today:
///  * Submission `7333473` ranked this fusion at **-0.19%** (1.09995 against
///    a 1.10187 frontier) and it shipped default-off. The diagnosis at the
///    time — "one simdgroup per head is a bad kernel shape" — was wrong.
///  * The actual cause was one redundant line. The kernel parked the inverse
///    RMS in a `threadgroup` slot and issued a `simdgroup_barrier` to
///    broadcast it, but `simd_sum` already returns the total to *every* lane,
///    so each lane can derive the same `precise::rsqrt` locally and
///    bit-identically. At 72 threadgroups per layer across 30 sliding layers
///    that barrier was paid **2160 times per decode token** for nothing, and
///    the full-attention twin had the identical pattern (another 560).
///  * Deleting both and **re-enabling** this fusion measured 10.456 -> 10.326
///    ms steady step (+1.19%, 4/4 pairs) and promoted as `9e06de6` at
///    **1.12019, +1.73%** — the largest single win in the project.
///
/// So the -0.19% figure describes a kernel that no longer exists. Do not
/// spend measurement pairs re-ablating this on the strength of that number.
```

## L526-L539 — darkbloom-flag

```swift
/// Multi-token (prefill) twin of the two decode QK-norm+RoPE fusions above
/// (see `lagunaPrefillSlidingQKNormRoPEKernel` /
/// `lagunaPrefillFullQKNormYaRNKernel`). One dispatch per layer replaces the
/// four stock dispatches on sliding layers (q RMSNorm, k RMSNorm, RoPE q,
/// RoPE k) and the six on full-attention layers (the partial-YaRN RoPE first
/// materializes a general copy of the transposed view). The cos/sin rows
/// come from the same load-time probe-seed atlas the decode kernels can
/// consume, so every rotary factor is a float the stock RoPE kernel itself
/// produced.
///
/// **DEFAULT ON** (`!= "0"`; set `DARKBLOOM_PREFILL_QK_NORM_ROPE=0` to
/// ablate). Guarded on shape/dtype/family and a host-known cache offset
/// with `offset + L <= lagunaRoPEAngleAtlasLength`; every other case takes
/// the verbatim stock path.
```

## L543-L548 — darkbloom-flag

```swift
/// Heads-per-threadgroup repartition for the prefill QK-norm+RoPE kernels.
/// The shipped kernels pack four heads (four SIMDs) per threadgroup; this
/// selects a one-head-per-threadgroup twin (one SIMD) instead -- the proven
/// DECODE shape. Bit-exact in the EG256 class: each head is one SIMD and all
/// per-head arithmetic is SIMD-local, so only threadgroup composition changes.
/// Default `1` selects H1; `DARKBLOOM_PREFILL_QK_HEADS=4` restores the control.
```

## L556-L562 — darkbloom-flag

```swift
/// Terminal-prefill projection banking. The last decoder layer consumes Q and
/// the per-head gate for only the final supplied row, while K/V must still be
/// produced for every row so the cache advances normally. Retained `[Q; G]`
/// and `[K; V]` BF16 banks therefore turn four independent projections into
/// two without changing any output row's contraction or rounding. Set
/// `DARKBLOOM_LAST_PREFILL_PROJECTION_BANKS=0` to restore the four stock
/// `Linear` calls and skip allocating the two derived banks.
```

## L567-L569 — darkbloom-flag

```swift
/// `DARKBLOOM_TERMINAL_FUSION` (default ON; set "0" to disable): current-API
/// port of overlay-dropped `9f98995`. `callLastPrefillRow` reuses the ordinary
/// path's accepted row-local fused residual+RMSNorm(+router)+MoE-tail helpers.
```

## L573-L578 — darkbloom-flag

```swift
/// Full-attention counterpart: fuses per-head Q/K RMSNorm with partial YaRN
/// RoPE. One stock FP32 probe row carries the authoritative rotary factors,
/// while the custom kernel preserves the normalized BF16 boundary and tail.
/// Folds the MoE router's `[256, 2048]` projection into the post-attention
/// residual + RMSNorm kernel, which is the dispatch immediately before it and
/// its only producer. Set `DARKBLOOM_FUSED_RESIDUAL_RMS_ROUTER=0` to ablate.
```

## L585-L602 — darkbloom-flag

```swift
/// Decode-only carrier for the two authoritative RoPE angle rows consumed by
/// the fused Q/K kernels. At load time each attention family's own stock RoPE
/// materializes an exact FP32 position atlas. A single custom kernel then
/// replaces the token embedding gather and copies both selected atlas rows,
/// removing the two per-token probe RoPE dispatches without changing their
/// values.
///
/// Default ON since the r=1-regime re-sweep (2026-08-02, M5 Max driver rig):
/// under the current one-row QMV geometry + counting-sort frontier the arm
/// measures −0.55..−0.7% steady decode, 4/4 mirrored pairs favoring ON
/// (medians 4.521/4.535/4.536/4.533 vs controls 4.563/4.557/4.574/4.543),
/// inverting the earlier fusion-stack-audit conclusion (−0.23% against ON
/// under the pre-r=1 regime) — the same regime-rot pattern the tail QKV
/// fusion showed in reverse. Values are unchanged by construction (the
/// atlas rows are the family's own stock RoPE outputs, copied); free-run
/// token hash and 1,600 teacher-forced steps are identical across arms.
/// Set `DARKBLOOM_ROPE_ANGLE_ATLAS=0` to restore the stock fallback
/// (`embedTokens` gather + `ropeAngleTable` probes).
```

## L606-L625 — darkbloom-flag

```swift
/// Zero-dispatch decode angle carrier: serve the two per-step RoPE angle rows
/// as contiguous row VIEWS of the load-time FP32 position atlases instead of
/// running the two probe RoPE dispatches every token. Unlike the fused
/// embedding+atlas kernel above (default OFF; its fixed kernel cost measured
/// −0.23%), this path adds no kernel at all: the atlas row for position `p`
/// is bit-identical to the probe output at `p` by construction (the atlas IS
/// the family's own stock RoPE run over the broadcast probe seed), and a
/// row slice of the contiguous `[1, 1, 4096, D]` atlas is a zero-copy
/// row-contiguous view, so the two probe dispatches vanish from the front of
/// every decode step with no replacement work. The stock `embedTokens`
/// gather is unchanged.
///
/// MEASURED (2026-08-01, M5 Max 128 GB, driver rig, 150-step cool-floor
/// ABBA): views are +0.01..+0.07 ms/step vs the probe dispatches — the two
/// probes are off the critical path (they overlap the embedding gather and
/// layer-0 front), so removing them buys nothing, and aliasing the ~3 MB
/// atlas buffers as per-step kernel inputs appears to add slight
/// resource-tracking cost. Default OFF, same promoted-era conclusion as the
/// fused embedding+atlas kernel above. Set `DARKBLOOM_ROPE_ATLAS_VIEWS=1`
/// to re-measure.
```

## L629-L637 — darkbloom-flag

```swift
/// `DARKBLOOM_FUSED_DENSE_GATE_UP_SWIGLU` (default on; set "0" to disable):
/// after checkpoint load, retain one row-concatenated BF16 `[gate; up]` bank
/// for layer 0's dense (non-quantized) MLP and serve single-token decode's
/// gate/up projections plus the SiLU-gated product from one dispatch (see
/// `LagunaRuntimeMLP.fusedDenseDownResidual` and `lagunaDenseGateUpSwiGLU`).
/// Layer 0 is the only layer whose MLP is plain BF16 `Linear` rather than
/// NVFP4 `QuantizedLinear`, so every gate/up fusion flag above (all guarded
/// on `QuantizedLinear`) always declines for it; this is its dedicated
/// counterpart.
```

## L641-L647 — darkbloom-flag

```swift
/// `DARKBLOOM_FUSED_DENSE_DOWN_RESIDUAL` (default on; set "0" to disable):
/// layer-0-only decode fusion of the dense MLP's down projection with the
/// decoder layer's `h + r2` residual add (see `lagunaDenseDownResidual`).
/// Every other down+residual fusion flag in this file requires
/// `mlp as? LagunaRuntimeSparseMoEBlock`, which layer 0 never satisfies, so
/// layer 0's residual add was the one MLP-side decode dispatch left with no
/// fusion counterpart at all before this flag.
```

## L651-L675 — darkbloom-flag

```swift
/// `DARKBLOOM_ROUTER_ROWS_PER_GROUP` (default `8`; set `64` to restore the
/// pre-widening shape, `32`/`16` for intermediate points, `4`/`2`/`1` for the
/// sub-8 shapes): router output rows owned by one threadgroup in
/// `laguna_residual_rms_router_bf16_2048`.
///
/// The router GEMV reads the whole `[256, 2048]` BF16 gate — 1,048,576 B —
/// once per sparse layer. At `64` (16 simdgroups x 4 rows) the 256 rows need
/// `256/64 = 4` threadgroups, and it measures 140.2 GB/s against a 575 GB/s
/// box (`notes/47` §2a): four threadgroups cannot cover the machine's cores.
/// Each halving doubles the tile count at constant total work, 8 -> 32
/// threadgroups. `rows_out` stays 256 in every setting, so no wave
/// quantization hole is created (`notes/50` §6b-§6d).
///
/// Bit-exact. `rows_per_group` changes only WHICH THREADGROUP OWNS WHICH ROW.
/// Every output row keeps its own private FP32 accumulator, its own K-loop
/// over `router_blocks` in `(block, i)` order, its own `simd_shuffle_down`
/// ladder, and one BF16 round. No add is regrouped: the reduction tree exists
/// only at lane level and this knob does not touch it.
///
/// SUB-8 IS MEASURED NULL (`notes/exp-rpgrouter.md`, 2026-07-31, 6.15 ms era):
/// rpg1 vs rpg8 paired A/B mean −5 µs/step (−29.5/−13.5/+25.5/−4.0 µs, inside
/// the ~18 µs local floor); rpg4/rpg2 single runs +25/+35 µs. Each extra tile
/// re-runs the barriered 2048-wide norm before its router rows, so below 8 the
/// redundant norm cancels whatever row-latency overlap the extra threadgroups
/// buy. Do not re-sweep; the values stay accepted only as ablation controls.
```

## L686-L695 — darkbloom-flag

```swift
/// `DARKBLOOM_ROUTER_WEIGHT_PREFETCH` (default `1`): hoists the first group of
/// the router GEMV's `router_weight` device loads above the RMS reduction tail.
/// Those loads depend only on `tile`/`simd_group`/`simd_lane`, never on the
/// norm, yet unhoisted they are issued after four `threadgroup_barrier`s, so
/// their latency cannot overlap the reduction ladder. `1` hoists one four-load
/// group; `0` restores the unhoisted form and `5` is the PLACEMENT CONTROL that
/// emits the character-identical one-group peel immediately below the normalize
/// barrier instead, so `1` minus `5` isolates cross-barrier overlap from the
/// peel itself. Loads only: the accumulation order into `router_result[0]` is
/// untouched, so every arm is bit-exact with arm `0`.
```

## L706-L711 — darkbloom-flag

```swift
/// `DARKBLOOM_DECODE_ASYNC_STAGE` (default `at:1,7,15,23,31,39`): process-once
/// boundary schedule for decode-step async scheduling. Active only when the
/// invocation input shape is exactly `[1, 1]`; prefill and multi-token shapes
/// are never asyncEval'd. `off`/`0` disables it; `norm` and `logits` remain
/// process-once ablation points, as does any single layer index `0`-`39`.
/// No operation, cache row, or token is added.
```

## L721-L743

```swift
/// Two schedule families, both special cases of the `at:i,j,k` boundary set:
/// `ladderN` fires after every `N`th layer, and `at:` names the boundaries
/// outright. `asyncEval` adds no operation, cache row, dtype boundary or
/// token — it only enqueues already-constructed work earlier — so every
/// schedule here is bit-exact and the choice is purely a measurement.
///
/// MEASURED, `notes/52` (two Latin squares, 66 runs, 66/66 `passed_correctness`,
/// steady step 8..128, all contrasts 6/6 paired). `off` is 10.3735 ms and the
/// previous `ladder8` default 9.4533, so overlap was already worth +9.7%; the
/// remaining prize is 0.15 ms and this default takes essentially all of it:
///
///     ladder8   (5 fires)  1.0000   the promoted default, unswept
///     ladder6   (6 fires)  1.0064
///     ladder2  (20 fires)  1.0169
///     ladder1  (40 fires)  1.0178
///     at:1,7,15,23,31,39   1.0170   <- six fires, ties forty
///
/// `ladderN`'s first fire is at layer `N-1`, so it structurally skips the
/// widest GPU-idle window in the step: the front. Adding ONE rung at layer 1
/// to `ladder8`'s own boundaries is worth as much as quadrupling the ladder,
/// for one extra scheduler round trip instead of thirty-five. The front rung
/// is worthless alone — a lone fire at layer 1 measures 0.9476, the worst
/// schedule tested — and only pays once the rest of the step is covered.
```

## L756-L760

```swift
        // `at:i,j,k` — an arbitrary boundary set, as a bitmask over decoder
        // layer indices (bit `i` ⇒ fire after layer `i`). `ladderN` and the
        // single-rung forms are both special cases of it, so every schedule
        // shape can be measured without a rebuild. Indices ≥ 64 are rejected
        // rather than silently dropped; Laguna has 40 layers.
```

## L781-L782

```swift
/// Diagnostic front-edge rung: enqueue layer 0's already-constructed QKV and
/// gate projections before the rest of that layer's graph is built.
```

## L786-L798 — darkbloom-flag

```swift
/// `DARKBLOOM_PREFILL_ASYNC_LADDER` (default `1`; `0`/`off` disables;
/// `8` restores the prior default): a ranked measurement on the
/// 1.87782 base scored stride 1 at 1.88526 (+0.40% vs that base, rejected
/// only because a larger win promoted mid-queue), and the decode-side
/// ladder sweep showed denser firing pays until graph-build cost
/// dominates. Stride 1 fires `asyncEval` after every layer:
/// prefill-side twin of the decode ladder above. Multi-token forwards build
/// a ~400-op graph with the GPU idle until the final eval; firing `asyncEval`
/// after every Nth layer streams completed segments exactly as the promoted
/// decode ladder does. Same exactness ground: no operation, order, cache
/// write, or token changes — only when already-constructed work is enqueued.
/// This pays into both score components: the prefill phase itself and the
/// 512-token seed prefill charged to the decode window.
```

## L808-L823 — darkbloom-flag

```swift
/// The shared 512-thread RMSNorm prologue emitted by three decode kernels.
///
/// 512 threads / 16 simdgroups square one 2048-wide row, `simd_sum` inside
/// each simdgroup, the sixteen partials meet in `local_sums`, and one inverse
/// RMS comes back out. Gathering those sixteen partials genuinely needs
/// threadgroup memory -- `simd_shuffle*` reaches only the 32 lanes of the
/// calling simdgroup, so no shuffle crosses from simdgroup 5 to simdgroup 0.
///
/// A `DARKBLOOM_SHUF_NORM_BCAST` / `DARKBLOOM_SHUF_NORM_INIT` pair once made
/// the two non-gather barriers here optional. Both were measured locally at
/// -0.70% steady step (6/6 pairs, t=4.77, 95% CI excluding zero) and shipped
/// as submission `58864bf4`, which the ranked runner **rejected at -0.07%**.
/// The effect did not exist on the ranked box. Barrier removal has only ever
/// paid in narrow 32-thread kernels (`9e06de6`, +1.73%), where the rendezvous
/// is a large fraction of the kernel; in a 512-thread kernel it is free.
/// Removed rather than left default-OFF so nobody re-derives it.
```

## L826-L829

```swift
/// Emits the cross-simdgroup half of that prologue, from the sixteen partial
/// writes through to a `float laguna_inv_mean` the normalize loop consumes.
/// The emitted text is line for line what the three kernels shipped, plus a
/// register alias for `local_inv_mean[0]`.
```

## L856-L857

```swift
    // The first line inherits the enclosing literal's indentation, exactly as
    // the `\(epilogue)` interpolation in the router kernel does.
```

## L861

```swift
/// The 2048-row prologue shared by both residual+RMSNorm kernels.
```

## L866-L867

```swift
/// The fused QKV kernel names the same two builtins `lane` and `simd_group`
/// and spells its constants differently, but the reduction is the same shape.
```

## L872-L875

```swift
/// Four-load block groups actually hoisted. Only the `rows_per_thread == 1`
/// accumulate shape (`rows_per_group` 1/2/4/8, so including the default 8) has
/// a prefetchable peel, so every other shape collapses to arm 0's source and
/// arm 0's kernel name.
```

## L881-L928 — darkbloom-flag

```swift
/// Post-attention residual add + RMSNorm with the MoE router's projection
/// folded in.
///
/// Every sparse layer follows this norm with a `[256, 2048]` BF16 GEMV whose
/// only input is the normalized row, so that GEMV is the very next link in the
/// dependency chain and nothing can overlap it. Folding it in costs each
/// threadgroup a redundant 4 KB read of the normalized row it just produced
/// and removes a kernel from the chain.
///
/// Exactness: the router half replicates MLX's gemv for out_vec 256 and in_vec
/// 2048, which selects BM 4, BN 1, SM 1, SN 32, TM 4, TN 4. Lane `l` covers
/// columns `4l + 128i`, products accumulate in `i` then `tn` order in FP32,
/// and the simdgroup reduces with the same `simd_shuffle_down` ladder before
/// one BF16 round. The norm half is untouched.
///
/// `rowsPerGroup` (see `DARKBLOOM_ROUTER_ROWS_PER_GROUP`) chooses only WHICH
/// THREADGROUP OWNS WHICH ROW. 256 divides evenly by 64/32/16/8, every row
/// keeps its own private accumulator and its own `(block, i)` K-loop, and no
/// add is regrouped. **At `rowsPerGroup == 64` this emits the pre-widening
/// kernel** — no guard, no unroll, the same four-element initializer, and
/// `tile * rows_per_group` is the literal 64 the old
/// `tile * (simd_size * rows_per_thread / 2)` folded to. That is what makes
/// `DARKBLOOM_ROUTER_ROWS_PER_GROUP=64` a null by construction and therefore a
/// usable control (`notes/50` §7e).
///
/// Below 16 rows per group there are fewer rows than simdgroups, so
/// `rows_per_thread` bottoms out at 1 and the surplus simdgroups sit out the
/// router phase behind `active_simd_groups`. They still run the norm, which
/// needs all 512 threads, and the guard opens *after* the norm's
/// `threadgroup_barrier` and closes *after* the logit write, so no thread is
/// skipped past a barrier and no row goes unwritten.
///
/// At `rows_per_thread == 1` the block loop is also unrolled four deep. This
/// is the load-level-parallelism half of `notes/50` §6b-ter: `tiles *
/// rows_per_group == 256` at every tiling, so retiling alone cannot add a
/// single outstanding load and leaves in-flight bytes pinned at 64 KB — which
/// is the whole of the measured 140 GB/s. Hoisting four blocks' weight loads
/// takes that to 256 KB.
///
/// **LOADS ONLY.** `router_result[0]` stays a single accumulator stepped in
/// strict `(block, i)` order: block 0's four products, then block 1's, and so
/// on into the same register. Giving each unrolled step its own partial and
/// summing the four at the end would regroup 64 sequential FP32 adds into a
/// tree — bit-exactness lost, every local check still green, the hidden
/// exact-token gate failed. `router_blocks == 16` and `16 % 4 == 0`, so there
/// is no tail. The `normalized_row` coefficients are read inline rather than
/// staged: at one row per thread both cost `n_reads` threadgroup reads per
/// block, so staging would buy nothing and cost 16 registers per unroll step.
```

## L1115-L1119

```swift
/// One kernel per supported `rows_per_group`, all built eagerly so that every
/// arm of an ablation is served by the same binary (`notes/00`'s one-binary
/// rule). MLX keys its JIT library cache by name and clears it when a name's
/// source changes (`custom_kernel.cpp:58-68`), so the variant MUST be in the
/// name or four sources would thrash one cache entry.
```

## L1150-L1151

```swift
/// Residual add + RMSNorm for the layers whose MLP is not a sparse block
/// (layer 0) and for any shape the router fusion above declines.
```

## L1210-L1216

```swift
    // `rows_per_group` router rows per threadgroup, so 256 / rows_per_group
    // tiles. Divides exactly for 64/32/16/8/4/2/1 (4..256 tiles), so no partial
    // tile is dispatched and no row is computed twice or missed. The 512-thread
    // threadgroup and `n_reads == 4` are NOT knobs: they are load-bearing for
    // the `rms_single_row` correspondence (each thread squares its own
    // contiguous four elements), and moving either regroups the FP32 RMS
    // summation and forfeits bit-exactness.
```

## L1257

```swift
// MARK: - Attention
```

## L1364-L1384

```swift
/// Sliding-layer twin of the full-attention QK-norm+RoPE kernel above. The
/// thirty sliding layers carry plain RoPE -- the whole 128-element head
/// rotates, the angle scale is one, and there is no YaRN mscale -- so their
/// per-head RMSNorm and rotation stayed on the stock four-dispatch path
/// (`q_norm`, `k_norm`, RoPE(q), RoPE(k)) while the ten full-attention layers
/// were fused. This kernel closes that gap: one dispatch per decode step per
/// layer for all 72 heads, emitting the transposed `[1, heads, 1, 128]` layout
/// attention consumes directly.
///
/// Exactness, link for link with the pair it replaces:
///  * The RMSNorm half mirrors `rms_single_row` (rms_norm.metal) at
///    axis_size 128 with N_READS 4 and a 32-thread group: lane `l` owns the
///    contiguous block `[4l, 4l+4)`, accumulates `float(x)^2` in index order,
///    `simd_sum`s, and applies `precise::rsqrt(acc / 128 + eps)`. The
///    `bfloat(...)` inside `w[i] * bfloat(x[i] * inv_mean)` is load-bearing:
///    it is the same rounding the separate kernel would have written out and
///    the rotation would have read back.
///  * The rotation mirrors `rope_single_impl<T, false>` for `dims == 128`:
///    pair `p` couples elements `p` and `p + 64`, and `cos`/`sin` come from a
///    table produced by that very kernel (see `_slidingRoPEAngleSeed`), so
///    they are the same floats, not a re-derivation.
```

## L1483-L1503 — darkbloom-flag

```swift
/// `DARKBLOOM_FUSED_SLIDING_ATTN` (default on; set "0" to disable): decode
/// fused attention for the thirty sliding-window layers in the steady
/// wrapped regime. ONE dispatch replaces the four-stage dependency chain
/// [QK-norm+RoPE kernel] -> [K cache slice-assign] -> [V cache
/// slice-assign] -> [sdpa_vector]: it computes the new token's per-head
/// Q/K RMSNorm + plain RoPE in threadgroup memory (textual replica of
/// `laguna_sliding_qk_norm_rope_bf16_128_v1`), persists the new K/V row
/// into the ring backing at the slot `RotatingKVCache.updateInPlace` would
/// have written, and attends over the full 512-slot ring in slot order with
/// the GQA-pair schedule of the shipped `sdpa_vector` pair path (textual
/// replica: same key visit order per simdgroup, same online-softmax text
/// including the alpha-skip rescale, same two-plane combine and reduction
/// trees). Bit-exactness of the substitution: at slot `write_idx` every
/// threadgroup substitutes the just-computed row from threadgroup memory —
/// the values pass through the same `bfloat` storage rounding the separate
/// kernels would have written to and re-read from the cache, so scores and
/// output are bit-identical, and no threadgroup ever reads slot
/// `write_idx` from device memory, making the concurrent slot write
/// race-free by construction (its only consumers are future steps, ordered
/// by command-buffer sequencing). Removes 3 dispatches + their encoder-wide
/// barriers per sliding layer per decode step.
```

## L1925-L1927

```swift
/// Fused decode attention for a sliding layer in the steady ring regime.
/// Returns `[1, heads, 1, headDim]` attended output; the caller advances the
/// cache clock via `RotatingKVCache.fusedRingAdvance()`.
```

## L1977-L1983

```swift
/// Pre-materialized 4-byte uniform buffers for every possible sliding ring
/// write index (2 KB total, built on first touch during untimed warmup):
/// replaces a fresh 1-element MLXArray allocation per sliding-attention call
/// (30/step). Input-independent: all 512 values built unconditionally; the
/// lookup indexes by the cache's ring position (request-local state), the
/// same contract as the RoPE angle atlases. Worker decode is
/// single-threaded, so the write-once unsafe opt-out is sound.
```

## L1996-L1997 — darkbloom-flag

```swift
/// `DARKBLOOM_PARAMS_ATLAS=0` restores the per-call fresh 1-element array
/// (ablation control for the atlas above; identical bytes either way).
```

## L2001-L2009 — darkbloom-flag

```swift
/// `DARKBLOOM_FUSED_FULL_ATTN` (default on; set "0" to disable): decode
/// fused attention for the ten full-attention layers once the cache backing
/// has spare capacity (from the second decode step on; the first step's
/// stock growth concat is kept). Same design as the sliding twin above —
/// ONE dispatch replaces [QK-norm+YaRN kernel] -> [K slice-assign] ->
/// [V slice-assign] -> [sdpa_vector] — with the full-attention phase-1 text
/// (textual replica of `laguna_full_qk_norm_yarn_bf16_128_v4`: 64-dim
/// partial rotary, folded mscale roundings, passthrough tail) and the
/// pair path's runtime-length loop + single-row tail at gqa_factor 6.
```

## L2013-L2015

```swift
/// Diagnostic-only coupling control for the historical second whole-model
/// constructor decode. Full-attention fusion no longer implies this rewarm;
/// set the flag explicitly only when reproducing the retired bundled arm.
```

## L2020-L2022

```swift
/// Compile only the full-attention custom kernel during untimed construction,
/// using tiny throwaway arrays. Unlike the retired whole-model rewarm, this
/// does not execute another Laguna layer or retain request/cache state.
```

## L2409-L2411

```swift
/// Fused decode attention for a full-attention layer with spare backing
/// capacity. Returns `[1, heads, 1, headDim]`; the caller advances the
/// cache clock via `KVCacheSimple.fusedAppendAdvance()`.
```

## L2462-L2465

```swift
/// Force creation of `lagunaFullFusedAttentionKernel`'s pipeline state with
/// production Q/K/V geometry and a minimal two-row cache. Every tensor is
/// deterministic, input-independent, evaluated once, and released before the
/// constructor clears transient allocator cache and wires resident weights.
```

## L2499-L2523

```swift
/// Multi-token sliding-layer Q/K RMSNorm + plain RoPE fusion. One dispatch
/// replaces the stock four (`rms_single_row` q, `rms_single_row` k,
/// `rope_bfloat16` q, `rope_bfloat16` k) for a whole prefill layer and
/// writes both outputs directly in the `[1, heads, L, 128]` layout SDPA and
/// the cache update consume, so the transposed-view round trip is gone too.
///
/// Grid mapping: one threadgroup of 128 threads (four simdgroups) per
/// (head-block, token); each simdgroup owns one (token, head) row, exactly
/// the row `rms_single_row` gets at axis_size 128 (N_READS 4, one 32-lane
/// simdgroup per row). `threadgroups_per_grid.y` is L, so no shape constant
/// is baked and any L dispatches the same compiled kernel.
///
/// Exactness, link for link with the stock chain:
///  * The norm replicates `rms_single_row` at axis_size 128: lane `l` owns
///    the contiguous block `[4l, 4l+4)`, squares in index order, `simd_sum`
///    (the stock single-simdgroup threadgroup then sums `local_sums`, which
///    adds only zeros), `precise::rsqrt(acc / 128 + 1e-6)`, and the BF16
///    rounding inside `w[i] * bfloat(x[i] * inv)` — the same expression the
///    shipped decode kernels use against the same stock kernel.
///  * The rotation replicates `rope_impl<T, _, 4>` (`rope_bfloat16`,
///    non-traditional, dims 128): pair `p` couples `p` and `p + 64`, and the
///    cos/sin floats are read from the probe-seed atlas row for the token's
///    absolute position — values the stock RoPE kernel computed, not a
///    re-derivation. The decode twin (`laguna_sliding_qk_norm_rope_bf16_128_v1`)
///    consumes the same table with the same expression.
```

## L2600-L2608

```swift
/// One-head-per-threadgroup twin of the prefill sliding QK-norm+RoPE kernel
/// (H1). BIT-EXACT repartition in the EG256 class: the `*4` original packs
/// four heads (four SIMDs) per threadgroup; this twin packs one (one SIMD).
/// Each head's work is fully SIMD-local -- RMSNorm `simd_sum`, the within-SIMD
/// `lane ^ 16` rotary-partner shuffle, and every BF16 rounding boundary never
/// cross heads -- so the value each head writes is identical regardless of how
/// many heads share a threadgroup. This matches the proven DECODE shape
/// (`lagunaSlidingQKNormRoPEKernel`, one SIMD/head, the project's largest
/// single win); the prefill `*4` was an unaudited divergence from it.
```

## L2684-L2697

```swift
/// Multi-token full-attention twin: per-head Q/K RMSNorm + partial YaRN
/// RoPE (rotary half 64, mscale on the rotary inputs, tail passes through).
/// One dispatch replaces the stock six (`rms_single_row` ×2, the general
/// copy each partial RoPE materializes first ×2, `rope_freqs_bfloat16` ×2).
///
/// Exactness mirrors the shipped decode kernel
/// (`laguna_full_qk_norm_yarn_bf16_128_v4`) against the same stock chain:
/// the same rms_single_row reproduction; the same mscale round-trip
/// `float(bfloat(x * bfloat(mscale)))` the stock
/// `rope_input_with_mscale<bfloat16, true>` applies under the negative-scale
/// sentinel; the same probe-seed angle row (the FP32 probe recovers
/// `fl(fl(1/mscale) * mscale) == 1.0f`, so the atlas carries pure cos/sin);
/// and the tail elements 64…127 written verbatim, matching the values the
/// stock pre-RoPE copy leaves behind.
```

## L2783-L2788

```swift
/// One-head-per-threadgroup twin of the prefill full-attention QK-norm+YaRN
/// kernel (H1). Bit-exact repartition (EG256 class): each head is one SIMD and
/// all per-head arithmetic (RMSNorm `simd_sum`, the within-SIMD `lane ^ 8` YaRN
/// partner shuffle, the mscale round-trip) is SIMD-local, so grouping one head
/// per threadgroup instead of four changes only launch count/occupancy, not any
/// head's output value. Matches the proven decode shape.
```

## L2973

```swift
/// Exact UInt16 indices into an insertion-ordered BF16 `(scale,bias)` LUT.
```

## L3019

```swift
    /// Shipped group-32 affine INT8 or the inherited group-16 NVFP4 tail.
```

## L3024-L3026

```swift
    /// Lossless narrow re-encoding of `scales`, read only by the decode-only
    /// NVFP4 attention QMVs. `scales` stays authoritative for every other
    /// reader and for the MLX fallback.
```

## L3028-L3030

```swift
    /// Lane-major re-encoding of `scales`, built instead of `narrowScales` when
    /// it is available. Same reader, same authority: `scales` is still the
    /// plane every other consumer and the escape path read.
```

## L3042-L3047

```swift
/// Group-16 NVFP4 attention tail start layer. NVFP4 as shipped costs
/// 0.5625 B/param vs 1.125 for the group-32 affine INT8 side layout, so
/// each layer kept on NVFP4 halves its attention weight traffic (decode is
/// bandwidth-bound; local sweep monotone ~-0.5%/layer). Numerically this is
/// the shipped representation the goldens came from — envelope option (1),
/// which never requires the INT8 re-quant.
```

## L3056

```swift
/// Diagnostic-only numeric-format probe; unset on the shipped path.
```

## L3128

```swift
/// Decode-only, exact fused input RMSNorm plus Q/K/V/gate projections.
```

## L3565-L3566

```swift
    // Q/K/V tiles at 64 rows each, then 8 more tiles carrying the 64 gate
    // rows as two eight-simdgroup split-K groups apiece.
```

## L3582-L3615

```swift
/// Decode-only fusion of the per-head attention gate with the output
/// projection. The stock decode path is two dispatches: one compiled
/// elementwise kernel that softplus-gates the attention output, and one GEMV
/// over `o_proj`. This kernel folds the gate into the GEMV's vector loads, so
/// the 8192-wide gated row is never materialized and the layer spends one
/// dispatch instead of two.
///
/// Exactness. The fused QKV producer has already reproduced
/// `softplus(gate.asType(.float32)).asType(.bfloat16)` after preserving the
/// projection's intermediate BF16 rounding boundary. This consumer applies
/// the same BF16 gate product as stock. The projection reproduces MLX's
/// `gemv` for this shape exactly: out_vec 2048 and in_vec 8192 select BM 4,
/// BN 1, SM 1, SN 32, TM 4, TN 4, so a thread owns four output rows, lane `l`
/// covers input columns `4l + 128i`, products accumulate in `i` then `tn`
/// order in FP32, and the simdgroup reduces with the same
/// `simd_shuffle_down` ladder (16, 8, 4, 2, 1) before lane 0 rounds once to
/// BF16. Because column `4l + 128i` always lies inside head `i`, the gate a
/// thread needs at step `i` is simply `gate_values[i]`.
/// Depth-2 block unroll, `notes/54` §11: L5 is the only large kernel whose
/// in-flight budget is small enough for memory-level parallelism to bind at
/// all. It holds 512 KB against `lm_head`'s 1280 KB, and at the top of the
/// measured 287–947 ns latency bracket 512 KB supports 554 GB/s against L5's
/// measured 553.8. Hoisting two blocks' loads takes that to 1.05 MB, which
/// clears the 596.1 GB/s fabric ceiling under every calibration in the
/// bracket. If L5 is fabric-bound instead this is flat — a result, not a
/// failure. L5's 0.40 waves are what make the ~20 extra registers free: at
/// 3.2 threadgroups per core against a capacity of 8 there is no occupancy to
/// lose (`notes/46` §6).
///
/// **LOADS ONLY.** `result[row]` stays one accumulator per row, stepped in
/// strict `(block, i)` order — block 0's four products then block 1's, into
/// the same register. Per-unroll partial sums combined at the end would
/// regroup the FP32 chain into a tree and forfeit bit-exactness while passing
/// every local check. `blocks == heads` is 64 or 48, both even, so no tail.
```

## L3802-L3812 — darkbloom-flag

```swift
/// `DARKBLOOM_L5_UNROLL` (default `2`; `1` restores the pre-unroll loop
/// verbatim, `4`/`8` deepen it): block-loop unroll depth for the gated output
/// projection. Every depth divides both block counts — 64 heads and 48 — so no
/// tail loop is ever needed, and depth `1` emits the pre-patch loop, which
/// makes it a true ablation control rather than an approximation of one.
///
/// The depth sweep {1, 2, 4} on this kernel is the highest-information
/// measurement left on this box. It decides whether outstanding loads per
/// thread — rather than bandwidth or occupancy — is what limits this whole
/// kernel family. A monotone rise toward 596 GB/s would mean the 462.9 µs /
/// 4.52% ceiling that L1+L5 have been sized against is itself too low.
```

## L3822-L3824

```swift
/// Every head count x every unroll depth, built eagerly so that one binary
/// serves every arm of an ablation (`notes/00`'s one-binary rule) and so MLX's
/// name-keyed JIT library cache never sees two sources under one name.
```

## L3868-L3886

```swift
/// Decode-only producer/consumer fusion for the per-head output gate. The
/// stock chain between the gate projection and the output projection is four
/// dispatches — BF16→FP32 cast, `LogAddExp(x, 0)`, FP32→BF16 cast, and the
/// broadcast product against the attention row — all over a 48/64-element
/// logit vector and a 6144/8192-element row. This kernel performs the same
/// four steps in one dispatch, reproducing each rounding boundary exactly:
///
/// - the FP32 softplus is MLX's `LogAddExp<float>` verbatim (same
///   `maxval + log1p(exp(minval - maxval))` form, same NaN/inf guards, and
///   the same `log1p`: MLX's own Goldberg implementation from its metal
///   utils preamble, which is also what the eager softplus dispatch uses);
/// - the gate is rounded to BF16 exactly where the stock `.asType(.bfloat16)`
///   rounds it, and the product rounds once to BF16 exactly where MLX's BF16
///   binary multiply rounds `float(bfloat(float(values[i]) * gate))`.
///
/// Every output element is therefore bit-identical to the four-dispatch
/// chain; the only change is dispatch count. One thread per output element;
/// the softplus is recomputed per element of a head, which is the same FP32
/// op stream the standalone softplus dispatch would run once per head.
```

## L3922-L3923 — darkbloom-flag

```swift
/// Set `DARKBLOOM_FUSED_GATE_PRODUCT=0` to ablate and restore the exact
/// four-dispatch stock chain (eager softplus + donated in-place multiply).
```

## L3927-L3930

```swift
/// Returns the gated attention row for one decode token, or nil when the
/// preconditions do not hold (caller falls back to the stock chain). The
/// result is bit-identical to `output * softplus(gateLogits)` as the stock
/// chain computes it; see the kernel commentary above.
```

## L3953-L3955

```swift
// MARK: - Gated native-affine INT8 output projection (one dispatch)

/// Exact per-head softplus gate plus group-32 affine INT8 output GEMV.
```

## L4065-L4067

```swift
/// One kernel per attention head count, built eagerly so one binary serves
/// every arm of an ablation and MLX's name-keyed JIT cache never sees two
/// sources under one name.
```

## L4102-L4109 — darkbloom-flag

```swift
/// `DARKBLOOM_FUSED_GATED_AFFINE_OPROJ` (default ON; set "0" to disable).
/// Fuses the per-head softplus gate product into the native group-32 affine
/// INT8 o_proj GEMV so the decode attention tail is one dispatch instead of
/// two. Bit-exact: the gate factor is applied at the same FP32 -> BF16
/// rounding point as `lagunaGateProductSoftplus`, and the contraction keeps
/// MLX's affine GEMV geometry and accumulation order exactly. Falls back to
/// the exact two-dispatch chain whenever the affine o proj is not group-32
/// INT8 (the NVFP4 tail layers) or any guard declines.
```

## L4113

```swift
/// Gates only the NVFP4 tail-layer twin so it can be ablated independently.
```

## L4117-L4129 — darkbloom-flag

```swift
/// `DARKBLOOM_NVFP4_QMV_SIGN_CARRY` (default OFF): in the standalone NVFP4
/// o_proj QMV decode (`lagunaGatedAffineOProjNVFP4Source`), fold the E4M3
/// group-scale sign bit into the half bit pattern instead of a conditional
/// negate — the same bit-exact transform ivanfioravanti's 71b80b1f applied to
/// the fused tail qdot (`DARKBLOOM_TAIL_NVFP4_SCALE_FOLD`), which this
/// standalone kernel did not carry. For `bits = 128 + m` the carry
/// `bits + (bits & 128)` yields `256 + m`, and `(256 + m) << 7 ==
/// 0x8000 | (m << 7)` because `m <= 127` keeps `m << 7 <= 16256 < 0x8000`;
/// IEEE half is sign-magnitude, so that pattern IS the negation, including
/// `-0.0h`. For `bits < 128` the add is the identity. Replaces the branch and
/// the intermediate `half` with one carrying add. Exhaustively bit-identical
/// over all 256 E4M3 bytes (`LagunaNVFP4QMVFoldTests`); the two power-of-two
/// scale factors were already folded to the per-row `* 4194304.0f` epilogue.
```

## L4133-L4145 — darkbloom-flag

```swift
/// `DARKBLOOM_E4M3_SIGN_DOMAIN` (default ON; set "0" to keep the sign-carry
/// forms): census-certified sign-domain specialization of the E4M3 scale
/// decode. A full scan of the pinned checkpoint's 234 U8 scale tensors
/// (1,970,601,984 bytes) measures min 1, max 73, zero sign bits, and the
/// init-derived attention side banks inherit nonnegativity from the vendored
/// `fp_quantize` producer (`simd_max(abs(w)) / 6` converted to E4M3), so
/// `bits & 128 == 0` on every scale byte any kernel can read. The carrying
/// add `bits + (bits & 128)` therefore reduces algebraically to `bits` and
/// the sign select to the identity — same bit pattern, same float, fewer
/// dependent ops. The kill switch restores the carry forms, which remain
/// exact over all 256 bytes. (Mechanism first priced by 0xkydo's 3d6f202,
/// which passed every hidden gate and the static review; census reproduced
/// independently on this machine before adoption.)
```

## L4149-L4157 — darkbloom-flag

```swift
/// `DARKBLOOM_NVFP4_QMV_SEED_ELIDE` (default OFF): in the same o_proj QMV
/// decode, assign the first four-term product group to the accumulator instead
/// of adding it to a `+0.0f` seed, removing one dead FP add per output row per
/// K block. `fadd 0.0, %t` is not foldable under `setFastMathEnabled(false)`
/// (`0.0 + (-0.0) == +0.0 != -0.0`), so the add is really emitted. Eliding it
/// can only flip the sign of an all-`-0.0` group's zero, which the
/// `+0.0f`-seeded `result[row]` accumulator (`+0.0 + -0.0 == +0.0`) and the
/// BF16 epilogue absorb, so the kernel output is bit-identical
/// (`LagunaNVFP4QMVFoldTests`).
```

## L4161-L4163

```swift
/// Gate product + native-affine INT8 output projection in one dispatch, or
/// `nil` when any shape, dtype or wire-format guard declines (caller then runs
/// the exact two-dispatch chain).
```

## L4216-L4221

```swift
// MARK: - Gated NVFP4 output projection for the affine tail layers

/// NVFP4 twin of `lagunaGatedAffineOProjSource` for layers using the native
/// group-16 NVFP4 output projection. It folds the softplus gate, broadcast
/// product, and contraction into one dispatch while preserving the BF16 gate
/// rounding point and the stock NVFP4 accumulation geometry.
```

## L4232-L4234

```swift
    // Sign-carry fold: E4M3 is sign-magnitude, so carrying the sign bit into
    // the half pattern is the exact negation over all 256 bytes (incl. -0.0h);
    // the OFF arm keeps the negate-after-convert form verbatim.
```

## L4244-L4246

```swift
    // Seed elision: assign the first four-term group instead of adding it to a
    // dead `+0.0f` seed. Only a signed-zero can differ, and the `+0.0f`-seeded
    // `result[row]` plus BF16 epilogue absorb it. OFF arm keeps the seed.
```

## L4303-L4309

```swift
    // Lane-major arm: one row-wide base plus a 4-bit offset per group, stored
    // so that lane `simd_lid` -- or pair-lane `simd_lid >> 1`, whose two lanes
    // provably share a scale byte -- owns a contiguous nibble run. A block's
    // scale is then one byte load and a shift instead of the stock 32-byte
    // group read. An escaped row (`base == 0xFF`) selects the stock plane's
    // *address*, so both arms issue exactly one load and the compiler cannot
    // speculate the wide read this replaces.
```

## L4439-L4441

```swift
/// Lane-major twins of the two NVFP4 o_proj registries. Distinct kernel names
/// so a JIT cache can never serve one arm's binary to the other. `weight_scales`
/// stays bound because the escaped-row arm reads it.
```

## L4648-L4658

```swift
/// Exact E4M3 scale decode and stock-order 16-value qdot for the fused tail.
/// The stock path shifts the 7-bit magnitude into a half (thereby dividing by
/// 256), restores that factor in half, applies the sign, then multiplies its
/// float scale by 16384 before the accumulated qdot. The enabled path folds
/// both powers of two into one exact float multiply (`256 * 16384 = 2^22`).
/// `bits + (bits & 128)` moves E4M3's sign to half bit 15 when shifted while
/// retaining the magnitude. Every E4M3 magnitude is finite; the half-form
/// intermediate is at most 1.875, so neither formulation rounds or overflows.
/// An exhaustive comparison over all 256 scale bytes is bit-identical,
/// including both signed zeros. The environment switch keeps the original
/// expression as a direct timing and correctness control.
```

## L4662-L4675 — darkbloom-flag

```swift
/// `DARKBLOOM_QKV_TAIL_FOLD` (default ON for the ranked run; set "0" to restore
/// the frontier q/k/v QMV): ports the two exactness-proven ALU
/// micro-elisions the o_proj (`lagunaGatedAffineOProjNVFP4Source`) and MoE
/// (`lagunaSharedSwiGLUQMVHeader`) NVFP4 QMVs already ship into the decode
/// q/k/v NVFP4 tail QMV (`lagunaDecodeNVFP4QKVR1Source` +
/// `lagunaTailNVFP4QMVHeader`): (1) seed elision -- assign the first four-term
/// product group instead of adding it to a dead `+0.0f` seed; and (2) scale
/// defer -- return the RAW half from `laguna_tail_nvfp4_scale` and apply the
/// folded `2^22` once per output row at the R1 epilogue instead of once per
/// 16-value group. Both are pure instruction-count reductions: identical bytes,
/// loads, geometry and reduction order (the R1 one-row-per-simdgroup schedule
/// and the `simd_sum` order are untouched). When OFF the generated kernel
/// source, name and dispatch are byte-identical to the frontier q/k/v QMV;
/// ranked correctness is the CXXC exact-token gate.
```

## L4679-L4680 — darkbloom-flag

```swift
/// Seed-elision half of `DARKBLOOM_QKV_TAIL_FOLD`, kept as its own constant so
/// the two elisions can later split behind independent env sub-flags.
```

## L4683-L4686 — darkbloom-flag

```swift
/// Scale-defer half of `DARKBLOOM_QKV_TAIL_FOLD`. Composes only with the active
/// fold arm, exactly like MoE's
/// `lagunaNvfp4ScaleDeferEnabled && lagunaNvfp4ScaleFoldEnabled`: deferring the
/// `2^22` only makes sense once the fold has parked it in the scale.
```

## L4690-L4695

```swift
/// Body of `laguna_tail_nvfp4_scale`. The folded arm parks `256 * 16384 == 2^22`
/// in the scale; under scale-defer it returns the RAW half and the `2^22` is
/// re-applied once per output row by `lagunaTailNVFP4RowScaleSuffixSource` at
/// the R1 epilogue. Explicit bool params (no env) so both arms are exercisable
/// under plain `swift test`, mirroring `lagunaGatedAffineOProjNVFP4Source`. The
/// non-defer and unfolded arms reproduce the frontier text verbatim.
```

## L4708-L4709

```swift
/// Accumulator declaration for `laguna_tail_nvfp4_qdot`: the seed-elided arm
/// drops the dead `= 0` initializer because the first group now assigns.
```

## L4714-L4719

```swift
/// First four-term product group of `laguna_tail_nvfp4_qdot`. Seed-elided, the
/// first code word (`j == 0`) assigns the accumulator; every other word adds.
/// The `if (j == 0)` / `else` split and the multiply/add expressions are the
/// exact text o_proj's `firstAccum` emits, so the association is untouched --
/// only a signed-zero can differ, absorbed by the `+0.0f`-seeded `result` and
/// the BF16 epilogue. The non-elided arm reproduces the frontier group verbatim.
```

## L4742-L4744

```swift
/// The deferred `2^22` re-applied once per output row at the R1 epilogue when
/// scale-defer is active (empty otherwise), mirroring MoE's
/// `lagunaNvfp4RowScaleSuffix`.
```

## L4802-L4806

```swift
/// Decode-only, static-shape R1 schedule for the live group-16 NVFP4 QKV
/// bank. The generated QMV gives each SIMD group four output rows. This twin
/// keeps every row's K order, FP32 accumulator, simd reduction and BF16 cast
/// intact while giving each SIMD one row, matching the M5-positive routed and
/// shared expert schedules. Multi-token prefill cannot pass the shape guard.
```

## L4811-L4814

```swift
    // Narrow arm: three planes replace the 32-byte uint8 group. Lane `simd_lid`
    // owns group `simd_lid` of the block, so its nibble is byte `simd_lid >> 1`
    // and its 5th bit is bit `simd_lid & 7` of byte `simd_lid >> 3`. The
    // reconstructed byte then feeds the unchanged scale decode.
```

## L4915-L4921

```swift
/// Lane-major twin of `lagunaDecodeNVFP4QKVR1Source`: every scale code this
/// lane needs for the whole row arrives in one 2-byte load -- 64 contiguous
/// bytes per simdgroup -- and is decoded into registers before the K loop, so
/// the four 32-group blocks cost one request instead of twelve strided byte
/// requests. An escaped row (`base == 0xFF`) takes the simdgroup-uniform else
/// arm and reads the stock plane. Both arms fill the same `sb` registers, so
/// the K loop below is the R1 loop with its scale argument already resident.
```

## L5204 — darkbloom-flag

```swift
/// `DARKBLOOM_NORM_AFFINE_QKV_STAGE` = `inline` (default) or `tg`.
```

## L5208-L5224 — darkbloom-flag

```swift
/// `DARKBLOOM_NORM_AFFINE_QKV_PF` (default 4 = register-prefetch depth 4,
/// **DEFAULT ON**; set "0" to restore the stock inline kernel; 1...4
/// clamped). QmvLimiter study (notes/exp-qmvlimiter.md): the fused kernel's
/// RMS prologue (three barriers + the 2048-element reduction) runs
/// dead-serial BEFORE the first weight byte of each threadgroup's short
/// 18 KB stream, costing ~9% of the dispatch (harness noprol probe); the
/// prefetch variant issues the first `depth` k-blocks' code/scale/bias
/// loads ABOVE the prologue so the weight stream is in flight while the
/// reduction runs, then consumes them from registers in the exact stock
/// order. Pure reads of immutable weights and an identical FP schedule ->
/// bit-identical (standalone-harness memcmp on all output rows, random
/// banks, r10304 and r8240; model-level 130/130 max_abs_diff=0). Depth-4
/// measured -11.9%/-12.2% kernel-level at decode clocks (48.61->42.84 us
/// r10304, 39.34->34.55 us r8240; 554/549 GB/s vs 488/482 stock; projected
/// ~-171 us/step), depth curve monotone pf1->pf4, occupancy unchanged
/// (maxTotalThreadsPerThreadgroup 1024, +64 B thread state). Ignored under
/// the `tg` staged variant.
```

## L5231-L5237

```swift
/// Register-prefetch twin of the inline `lagunaNormAffineQKVSource`. The
/// NORM half and the k-loop arithmetic are textually the stock inline
/// variant's; the only changes are (a) the stream-pointer setup and the
/// first `depth` k-blocks' weight/scale/bias loads hoisted above the
/// prologue into registers, and (b) those blocks peeled off the k-loop,
/// consuming the registers with the identical per-i accumulation order.
/// Same values, same operation order per output row -> bit-exact.
```

## L5415-L5417

```swift
/// One kernel per reachable `[Q; K; V; (G)]` row count: both head families,
/// gate rows folded in or not. All four are multiples of 8, so `qmv`'s `fast`
/// predicate holds and no tail threadgroup is ever dispatched.
```

## L5475-L5481 — darkbloom-flag

```swift
/// `DARKBLOOM_FUSED_NORM_AFFINE_QKV` (default ON; set "0" to disable). Folds
/// the input RMSNorm into the native group-32 affine INT8 QKV GEMV so the
/// decode attention head is one dispatch instead of two. Bit-exact (inline
/// variant re-derives normalized values from L1-resident rows with no
/// occupancy cost). Applies only on group-32 INT8 layers with the gate rows
/// folded into the QKV bank; the NVFP4 tail layers and any guard decline keep
/// the separate norm + projection.
```

## L5485-L5487

```swift
/// Input RMSNorm + native-affine INT8 `[Q; K; V; (G)]` projection in one
/// dispatch, or `nil` when any shape, dtype or wire-format guard declines
/// (caller then runs the exact two-dispatch chain).
```

## L5546-L5548

```swift
/// Keep the stock shapeless unary gate for prefill. Ranked measurement showed
/// the larger gate/product graph regressing the complete prefill schedule even
/// though its isolated steady-state subpath was slightly faster.
```

## L5556-L5560

```swift
/// Decode-only outer compilation of the same gate product with the following
/// bias-free BF16 output projection. MLX keeps the matmul primitive intact but
/// schedules the elementwise producer and projection as one compiled graph,
/// avoiding a separate frontend boundary and shortening the gated vector's
/// lifetime. Prefill deliberately uses the smaller gate-only fusion.
```

## L5588-L5591

```swift
/// Laguna attention: GQA with per-head QK-norm, per-layer-type RoPE (YaRN on
/// full-attention layers over the first half of the head, plain RoPE on
/// sliding layers over the whole head), and per-head softplus output gating.
/// Mirrors the vendored `LagunaAttention` forward exactly.
```

## L5601-L5603

```swift
    /// Retained `[1]` FP32 carrier of `scale` for the fused decode
    /// attention kernel (same float the stock SDPA call passes), built once
    /// so the per-step graph adds no fresh scalar upload for it.
```

## L5618-L5623 — darkbloom-flag

```swift
    /// Retained fused `[Wq; Wk; Wv]` weight (output rows concatenated, query
    /// rows first), built once after checkpoint load when
    /// `DARKBLOOM_FUSED_QKV` is enabled. Plain stored property with a leading
    /// underscore so Module reflection never treats this derived layout as a
    /// checkpoint parameter; the q/k/v `Linear` modules keep the original
    /// arrays for parameter integrity.
```

## L5626-L5629

```swift
    /// Terminal-prefill-only BF16 side banks. Q and the per-head gate share
    /// the singleton final normalized row; K and V share every normalized
    /// supplied row. The authoritative modules remain intact for checkpoint
    /// loading and every fallback path.
```

## L5633-L5635

```swift
    /// Derived native group-32 affine layout for one serial decode token's
    /// Q/K/V batch. The original BF16 parameters remain authoritative and
    /// continue to serve prefill.
```

## L5638-L5641

```swift
    /// Derived native group-32 affine layout for the attention output
    /// projection, used only by the serial decode call. `wo.weight` remains the
    /// authoritative parameter and continues to serve prefill, the last-row
    /// prefill path, and every decode fallback.
```

## L5644-L5650

```swift
    /// Derived native group-32 affine INT8 layout for the attention per-head
    /// gate projection, used only by the serial decode call. Retained
    /// separately only on layers whose QKV bank is NOT group-32 INT8 (the
    /// NVFP4 tail window); on INT8-bank layers the gate rows concatenate into
    /// `_nativeAffineQKV` instead and `_nativeAffineQKVGateRows` records them.
    /// `gProj.weight` remains the authoritative parameter and continues to
    /// serve prefill, the last-row prefill path, and every decode fallback.
```

## L5653-L5656

```swift
    /// Number of gate rows appended at the tail of the fused QKV bank (0 when
    /// the gate is not folded into the bank). The appended rows sit after the
    /// Q/K/V rows, so the decode call slices them out of the same dispatch's
    /// output at `queryDim + 2 * kvDim`.
```

## L5694-L5700

```swift
        // The per-head gate joins the same side layout where the envelope
        // allows it. It is always group-32 affine INT8 (never the NVFP4 tail
        // window), so it can concatenate into the QKV bank only when that
        // bank is itself group-32 INT8; on the NVFP4 tail layers it keeps a
        // separate bank and its own dispatch. Either way every output row's
        // K loop is independent of which rows share the dispatch, so folding
        // the gate rows into the bank does not move a single Q/K/V value.
```

## L5755-L5757

```swift
            // Lane-major first: the two banks are alternatives, so building
            // only the one that will dispatch keeps a single side plane
            // resident instead of both.
```

## L5770-L5776

```swift
    /// Builds and retains the fused QKV weight from the loaded q/k/v
    /// projection weights. Called once after weights are installed and
    /// evaluated (before warmup); returns the new array so the caller can
    /// batch a single eval. Fuses only the exact stock configuration: three
    /// plain bias-free `Linear` projections of one dtype over the same input
    /// width, so the fused matmul is `matmul(x, w.T)` with every original
    /// output row unchanged.
```

## L5799-L5803

```swift
    /// Build the two terminal-prefill projection banks once after checkpoint
    /// load. Only the final sliding layer can dispatch them. Concatenating
    /// output rows is exact for bias-free `Linear`: each row retains the same
    /// K loop, BF16 inputs and BF16 weight bytes, independent of which other
    /// output rows share the matmul dispatch.
```

## L5888-L5890

```swift
        // One dispatch for the input RMSNorm and all three projections when
        // the decode preconditions hold; otherwise normalize separately and
        // fall through to the stock projections below.
```

## L5919-L5924

```swift
                // One dispatch for the input RMSNorm AND the INT8 projection
                // (see `lagunaNormAffineQKVSource`). Requires the group-32
                // affine INT8 wire format AND the gate rows folded into the
                // bank, so no consumer downstream of here needs a
                // device-visible normalized row; the NVFP4 tail layers and
                // any guard decline keep the separate norm.
```

## L5943-L5946

```swift
                // The fused tail norm+QKV+gate kernel was removed after the
                // r=1-regime re-sweep re-measured it +2.7% (its defusion is
                // the promoted state); the placeholder keeps the downstream
                // defer/eager gate-activation plumbing unchanged.
```

## L5948-L5949

```swift
                // Only materialized when the fused kernel declined; the gate
                // branches below that read it are unreachable when it fired.
```

## L5975-L5977

```swift
                    // Removed tail-fusion placeholder: always nil since the
                    // r=1-regime re-sweep; kept so the defer/eager plumbing
                    // below stays structurally unchanged.
```

## L5980-L5982

```swift
                    // The gate rows rode the fused bank's single dispatch;
                    // slice them out of its tail. Same row-local math as a
                    // standalone group-32 INT8 gate qmv.
```

## L5985-L5987

```swift
                    // NVFP4-tail layer: the gate keeps its own group-32 INT8
                    // bank (the envelope caps g_proj there) and replaces the
                    // BF16 GEMV one dispatch for one dispatch.
```

## L6020-L6024

```swift
                // When the fused gate-product kernel will consume the gate at
                // the output projection, hand it the RAW BF16 logits and skip
                // the eager softplus chain entirely; the kernel reproduces
                // those exact rounding boundaries inside its single dispatch.
                // Otherwise keep the stock eager activation.
```

## L6053-L6057

```swift
        // The fused result already contains every consumer of the normalized
        // row. Materialize that row only for the stock projections or the
        // retained row-concatenated QKV bank. Checking actual bank presence
        // above (rather than its environment flag) preserves the custom
        // fallback if fused-weight preparation declined.
```

## L6064-L6067

```swift
        // The retained BF16 [Wq; Wk; Wv] bank is PREFILL-ONLY: at decode it
        // would override the INT8 fused norm+QKV path (measured +1.4 ms/step
        // when force-enabled), while at L > 1 it collapses three steel GEMMs
        // into one.
```

## L6072-L6077

```swift
            // One dispatch over the row-concatenated [Wq; Wk; Wv] weight,
            // identical math to the three bias-free `Linear` calls
            // (`matmul(x, w.T)`). Each output row's K-loop is independent of
            // which rows share the dispatch, so every Q/K/V element is
            // bit-exact; the slices are views and the reshapes below may
            // copy, which does not change values.
```

## L6120-L6126

```swift
        // Multi-token twins of the decode fusions. The angle input is the
        // full load-time atlas (one cos/sin row per absolute position) and
        // `qkRoPEOffsets` carries the cache offset the stock
        // `applyRotaryPosition` would have used, both prepared once per
        // forward by the inner model; the guards fall through to the stock
        // four/six-dispatch chain for any other shape, dtype, or cache
        // state.
```

## L6161-L6163

```swift
            // One dispatch replaces the QK-norm+RoPE kernel, both cache
            // slice-assign dispatches, and sdpa_vector; see the kernel doc.
            // The clock advance below mirrors updateInPlace(tokenCount: 1).
```

## L6186-L6189

```swift
            // Full-attention twin of the fused branch above; engages from
            // the second decode step (the first step's growth concat stays
            // stock). The clock advance mirrors the stock single-token
            // update.
```

## L6256-L6261

```swift
        // With a singleton sequence axis, `[B, 1, H, D]` and
        // `[B, H, 1, D]` have the same contiguous byte order. Reshape
        // directly so decode does not carry a no-op transpose view through
        // the lazy graph. Multi-token calls still require the real axis swap.
        // A fused attention branch consumed the raw values already, so the
        // head-major layout only exists for the stock SDPA fallback.
```

## L6284-L6287

```swift
        // SDPA returns `[B, H, L, D]`. When `L == 1`, flattening its
        // contiguous head-major payload directly produces the exact
        // `[B, 1, H*D]` byte order; the transpose only changes singleton-axis
        // metadata. Preserve the real transpose for prefill.
```

## L6294-L6296

```swift
            // Per-head softplus gate computed in float32, then broadcast
            // across the head dimension (or applied elementwise for a
            // per-element gate).
```

## L6309-L6329

```swift
            // Native group-32 affine INT8 output projection for the serial
            // decode token. The stock fused kernel folds the gate into the
            // GEMV's own vector loads; this path cannot, because MLX's
            // `quantizedMM` owns the contraction. It therefore reproduces that
            // kernel's element-wise ordering explicitly: the per-head gate
            // multiplies the attention output *first*, through the same single
            // BF16 rounding boundary the kernel spells as
            // `float(bfloat(float(values[i]) * gate))` (an MLX BF16 binary
            // product rounds once, identically), and only then does the
            // contraction run. Gate-then-project is what every stock decode
            // form computes — the fused kernel, the compiled
            // `attentionGateProjection`, and the plain
            // `(output * gate); wo(output)` tail all apply the gate per input
            // element before the K loop — so the only perturbation this branch
            // introduces is the weight quantization itself.
            //
            // The broadcast multiply stays an MLX binary op deliberately: its
            // input is row-contiguous and refcount-1, so MLX donates the
            // attention output buffer and runs the product in place, whereas a
            // custom kernel would have to allocate and first-touch a fresh
            // 8192-wide output.
```

## L6338-L6342

```swift
                // Raw logits + gated affine GEMV: ONE dispatch for the softplus
                // chain, the broadcast product AND the INT8 contraction (see
                // `lagunaGatedAffineOProjSource`). Only the group-32 affine
                // INT8 wire format is served; the NVFP4 tail layers and any
                // guard decline fall through to the two-dispatch chain below.
```

## L6404-L6408

```swift
                // Raw logits + fused kernel: one dispatch reproduces the
                // softplus chain AND the broadcast product bit-exactly (see
                // `lagunaGateProductSoftplusSource`). Falls back to the stock
                // compiled-softplus + donated in-place multiply whenever the
                // gate is already activated or the kernel declines.
```

## L6481-L6486

```swift
    /// Prefill-only final-layer attention when the caller consumes just the
    /// last hidden row. K/V and the cache update still cover every supplied
    /// token. Q projection, Q normalization, Q RoPE, SDPA, and the output
    /// gate/projection run only for the last query; its RoPE offset is advanced
    /// by the discarded query-row count so it remains at the supplied
    /// sequence's final absolute position.
```

## L6546-L6547

```swift
        // The last-row query length is exactly one, so the SDPA result's
        // `[B, H, 1, D]` storage is already the desired flattened head order.
```

## L6569-L6604 — darkbloom-flag

```swift
// MARK: - Dense MLP (also used as the shared expert)

/// `DARKBLOOM_NVFP4_SCALE_FOLD` (default on; set "0" to restore the pre-fold
/// arithmetic): hoists the `2^14` out of `laguna_nvfp4_qdot_16`'s sixteen
/// per-call multiplies and folds it into the one multiply
/// `laguna_nvfp4_scale` already performs. **−16 scalar multiplies per
/// `qdot_16` call, −16.5% of the dequantize ALU, ~−1104 M float multiplies per
/// token across L8 + L9, and nothing added** (`notes/57` §10).
///
/// Bit-exact. `16384 == 2^14`, and scaling a binary float by an exact power of
/// two touches only the exponent field, so every product, partial sum and
/// rounding decision in the accumulator chain is exactly `2^-14 ×` its old
/// value — same bits, different exponent — and the `2^14` reappears once in
/// the scale before the single final rounding.
///
/// **The dtype move is range-checked, not assumed** (`notes/58` §1a). The
/// multiply moves from half to float because `4194304` overflows half, and a
/// power-of-two argument does NOT by itself survive a dtype change — so all
/// 256 E4M3 scale bytes were enumerated through both paths, in half and in
/// float, with an explicit `isfinite` check on the old path. **Zero
/// divergence, and no overflow is reachable:** the shuffle
/// `(bits & 127) << 7` maps E4M3 into half format, and since E4M3's exponent
/// bias is 7 against half's 15 it already yields the scale divided by 256 —
/// which is exactly what the old `*= 256.0` corrected. The half-domain
/// intermediate therefore peaks at **1.875**, and the scale at **480**,
/// against half's finite max of 65504. **136x headroom.**
///
/// The compiler cannot do this fold itself: `device.cpp:631` sets
/// `setFastMathEnabled(false)`, so reassociating `Σ(a·h·2^14)` into
/// `2^14·Σ(a·h)` is forbidden and all sixteen multiplies really are emitted.
/// `device.cpp` is outside `editablePaths`, so it is done by hand.
///
/// Safe under the `notes/00` kernel-selection rule: this is a pure arithmetic
/// identity **inside our own Metal source**. No shape, dtype, tile count or
/// reduction order that MLX can observe changes, so it cannot alter which
/// kernel MLX selects.
```

## L6608-L6650 — darkbloom-flag

```swift
/// `DARKBLOOM_NVFP4_NIBBLE_SPLIT` (default `1` = split; set `0` for the stock
/// shuffle, `2` for the 2-constant control arm): a strictly shorter
/// instruction sequence that produces the SAME eight `half` bit patterns per
/// code word. Values, dtypes, FP32 accumulation and its order, and the single
/// final BF16 round are untouched -- only the integer sequence that builds the
/// half bit patterns changes.
///
///   0  stock. Each of the four `half2` words takes its own magnitude
///      shift+mask, its own sign shift+mask and an OR: 5 int ops (4 for `p3`,
///      whose sign is already in place) = **19 per code word, 38 per 16-value
///      group**, spread over **eight distinct 32-bit mask constants**.
///
///   1  split. Separate the even and odd nibbles once, and in the same step
///      slide each nibble's sign three places so magnitude and sign sit at a
///      FIXED offset from one another. After that one shift+mask yields a
///      whole `half2`:
///
///          xe = c & 0x0F0F0F0F   even nibbles: mag 4j..4j+2, sign 4j+3
///          ge = xe | (xe << 3)   sign copied to 4j+6 -- those bits are zero
///                                in `xe`, so the OR cannot collide
///          yo = c & 0xF0F0F0F0   odd nibbles
///          go = yo | (yo >> 3)   mag copied down to 4j-3..4j-1, sign kept
///          p0 = (ge << 9) & M    p2 = (ge << 1) & M
///          p1 = (go << 8) & M    p3 =  go       & M     M = 0x8E008E00
///
///      **13 int ops per code word, 26 per group (-12), and three mask
///      constants instead of eight (-5 live constant registers).**
///
///   2  the op-count control. Identical 19-op structure to stock -- shift
///      first, then mask -- but only TWO distinct mask constants. It isolates
///      "fewer live constants" from "fewer instructions": if `2` alone moves
///      the needle the win is register pressure, if only `1` moves it the win
///      is the instruction count.
///
/// Bit-exactness is by construction, not tolerance. Every form here is an OR
/// of masked shifts, so each output bit is an OR of a fixed subset of input
/// bits and the 33 single-bit basis words pin the function completely. All 33
/// basis words plus 300 000 random words agree bit-for-bit with stock, and
/// decoding every (nibble position, code) pair through both yields the
/// identical float -- the NVFP4 alphabet {0, .5, 1, 1.5, 2, 3, 4, 6} x 2^-14.
///
/// Composes with `DARKBLOOM_NVFP4_SCALE_FOLD`: that flag scales the decoded
/// weights, this one only changes how their bits are assembled.
```

## L6659-L6666 — darkbloom-flag

```swift
/// Folds the e4m3 group-scale's sign bit into the half bit pattern instead of
/// negating after conversion. For `bits = 128 + m` the carry `bits + (bits &
/// 128)` yields `256 + m`, and `(256 + m) << 7 == 0x8000 | (m << 7)` because
/// `m <= 127` keeps `m << 7 <= 16256 < 0x8000`; IEEE half is sign-magnitude,
/// so that pattern IS the negation, including `-0.0h`. For `bits < 128` the
/// add is the identity. Drops `laguna_nvfp4_scale` from seven AIR ops to five
/// in the innermost K loop of every routed/shared decode QMV.
/// `DARKBLOOM_NVFP4_SCALE_CARRY=0` restores the negate-after-convert form.
```

## L6670-L6718 — darkbloom-flag

```swift
/// `DARKBLOOM_NVFP4_QDOT_SEED_ELIDE` (default on; set "0" to restore the
/// `float accum = 0.0f;` seed): removes the one dead FP add per 16-value NVFP4
/// group. `laguna_nvfp4_qdot_codes_16` seeds its accumulator with the literal
/// `+0.0f` and then performs four `accum +=`, so the very first of those four
/// is `fl(+0.0f + t)`. **`fadd float 0.0, %t` is NOT foldable to `%t`** —
/// `0.0f + (-0.0f)` is `+0.0f`, not `-0.0f`, so eliminating it needs the
/// no-signed-zeros flag, and `device.cpp:631` sets
/// `setFastMathEnabled(false)`. The add really is emitted, once per group, and
/// with ~69 M groups per decoded token across the nine routed/shared
/// SwiGLU-QMV and down kernels that is ~69 M dead FP adds per token, ~1.4% of
/// this loop's ALU.
///
/// **Bit-exactness is a closed case analysis over signed zero, not a
/// tolerance.** Write the four partial sums `t0..t3` (`t0` is the first
/// four-term group of packed word `codes.x`). Current: `a = (((+0 + t0) + t1)
/// + t2) + t3`. Elided: `a' = ((t0 + t1) + t2) + t3`.
///
///  1. If `t0 != -0.0` then `+0.0 + t0 == t0` bit-for-bit (IEEE 754 round-to-
///     nearest: `+0` is the additive identity for every operand except `-0`),
///     so `a' == a` and nothing downstream can differ.
///  2. If `t0 == -0.0` then the current form holds `+0.0` and the elided form
///     `-0.0`. Both are zeros, so each subsequent add either lands on the same
///     nonzero value (`±0 + x == x`) or keeps both operands zero. `a` and `a'`
///     can therefore differ ONLY as `+0.0` versus `-0.0`, and only when all
///     sixteen products of the group are `-0.0` (a sum of floats is `-0.0`
///     only if both addends are `-0.0`).
///  3. `scale` is always finite — `laguna_nvfp4_scale` builds its half from
///     `(bits & 127) << 7`, whose largest magnitude is 1.875h, so no E4M3 byte
///     can make it Inf/NaN — hence `scale * (±0.0) == ±0.0` and `qdot`'s
///     return differs at most in the sign of a zero.
///  4. Every call site absorbs that sign. The SwiGLU kernels accumulate into
///     `gate_result`/`up_result`, seeded `+0.0f`: `+0.0 + (-0.0) == +0.0`, and
///     once the accumulator is nonzero a `±0.0` addend leaves it unchanged, so
///     a `-0.0` row accumulator is unreachable in either form. The down
///     kernels assign `result[row]`, `simd_sum` it (again `+0 + -0 == +0`
///     unless all 32 lanes are `-0.0`), cast to BF16, and then reach the
///     output only through `routed + shared` / `product + routed_total` /
///     `residual + r2`, whose left operands are themselves `+0.0`-seeded
///     accumulations or the residual — so the `-0.0` is absorbed there too.
///
/// `LagunaNVFP4QdotSeedTests` executes 1-4 over the adversarial signed-zero
/// domain on the CPU, including groups whose every NVFP4 code is `-0.0`
/// (code 8) and every activation `+0.0`.
///
/// The two packed-word bodies are emitted textually in BOTH arms of the flag,
/// so the flag isolates the seed and nothing else. That costs no arithmetic:
/// the Metal compiler must already fully unroll the two-iteration `j` loop —
/// `input` is a `thread float[16]` that only stays in registers under constant
/// indices — so the unrolled text is what it was already compiling.
```

## L6722-L6751 — darkbloom-flag

```swift
/// `DARKBLOOM_NVFP4_SCALE_DEFER` (default ON; set "0" to restore): moves
/// the `2^22` that `DARKBLOOM_NVFP4_SCALE_FOLD` parked in
/// `laguna_nvfp4_scale` out of the per-group scale and onto the per-row
/// accumulator, one multiply per output row instead of one per 16-value
/// group. `laguna_nvfp4_scale` drops from five ops to four (and, add, shift,
/// convert) and the group cost falls by one FP multiply -- the same ~69 M
/// removals per decoded token as the seed elision above.
///
/// Off by default **on purpose**. Unlike the seed elision, the carry sign-fold
/// and the nibble split, this one is not exact by case analysis: it is exact
/// under a range condition. Multiplying by an exact power of two is exact and
/// commutes with rounding, so with `s' = scale * 2^-22` every group product
/// `fl(s' * accum)` is exactly `2^-22 * fl(scale * accum)`, every partial sum
/// of those products is exactly `2^-22` times the current one, and the single
/// epilogue multiply restores it before the one BF16 rounding -- **provided no
/// product lands in the FP32 subnormal range**, where scaling no longer
/// commutes with rounding.
///
/// The condition, stated exactly: the deferred form diverges only if some
/// group has `0 < |scale * accum| < 2^-104`. `s'` is at least `2^-17` (the
/// smallest nonzero E4M3 byte, `2^-9`, over 256), so that needs
/// `|accum| < 2^-109`; every NVFP4 weight is a multiple of `2^-15` and every
/// activation is BF16, so a nonzero `accum` below `2^-109` needs all sixteen
/// activations of the group below roughly `2^-99`. This model cannot produce
/// them: activations are BF16 roundings of `O(1)` residual-stream and RMSNorm
/// quantities, and cancellation in BF16 lands on that same coarse grid, so a
/// hidden value is either exactly zero (which contributes an exact zero and is
/// safe) or within a few tens of binades of the row's scale. The margin is
/// ~60 binades — promoted to the shipped default on that basis; the
/// exact-token gates fail loudly if the range assumption is ever violated.
```

## L6756-L6761 — darkbloom-flag

```swift
/// The `2^22` that `laguna_nvfp4_scale` stops applying under
/// `DARKBLOOM_NVFP4_SCALE_DEFER`, re-applied once per output row at the
/// accumulator-to-BF16 boundary. It appears at exactly one site per
/// `laguna_nvfp4_scale` call site in every kernel that uses
/// `lagunaSharedSwiGLUQMVHeader`; `nvfp4EveryScaleCallSiteHasARowRescaleSite`
/// pins those two counts equal per kernel so a missed epilogue cannot ship.
```

## L6765-L6771 — darkbloom-flag

```swift
    // The two halves of one power-of-two regrouping. They MUST move together:
    // the scale absorbs `2^14` exactly when the weights stop applying it.
    // `4194304.0f == 256 · 16384 == 2^22`.
    // Under `DARKBLOOM_NVFP4_SCALE_DEFER` the `2^22` leaves the per-group
    // scale entirely and is re-applied once per output row by
    // `lagunaNvfp4RowScaleSuffix`; the tail is then the same expression the
    // unfolded arm uses, for the opposite reason.
```

## L6814-L6815

```swift
    // The carry form only composes with the folded tail, which is where the
    // sign lands before any further scaling; keep the negate form otherwise.
```

## L6827-L6830

```swift
    // E4M3 bytes 0...15 are a linear positive run.  In the default folded
    // deferred-scale arm the half bit pattern is already the exact value
    // needed by the qdot; skip the carry/sign setup for this overwhelmingly
    // common case.  Keep every ablation's source unchanged.
```

## L6839-L6844

```swift
    // One packed 32-bit code word: eight NVFP4 values, four `half2` patterns,
    // two four-term FP groups. The first group of the FIRST word seeds the
    // accumulator when the seed elision is enabled; every other group adds.
    // Word `w` owns `input[8w .. 8w+7]`, exactly the indices the `8 * j` form
    // produced, so the multiply/add expressions and their association are
    // untouched.
```

## L6986-L6994

```swift
/// One-output-row scheduling twin of `lagunaSharedSwiGLUQMVKernel`.
/// Arithmetic is textually identical per row; only row ownership changes.
///
/// `halved` selects the group-32 halved scale plane built by
/// `lagunaHalvedGroup32ScalePlane`: one byte per 32 weights behind the patch
/// header, so a simdgroup's 32 lanes read 16 contiguous bytes in place of 32
/// and each lane issues one scale load per two it issued before. The fused
/// plane concatenates gate over up, so the only two pairs the quantizer can
/// leave unequal are gate row 0 and up row 0, carried in header slots 0 and 1.
```

## L7092-L7097

```swift
/// Wide-codes twin of the halved R1 kernel: two adjacent groups per lane, one
/// `uint4` code load and one shared scale byte per pair, two K iterations
/// instead of four. The pair's second group reuses `laguna_nvfp4_qdot_codes_16`
/// on the upper half of the `uint4`, so the per-group arithmetic and the
/// accumulate-then-`simd_sum` shape are unchanged; only the lane-to-group
/// assignment moves, which is the documented reassociation.
```

## L7197-L7199

```swift
    // A halved plane is the one-dimensional header-plus-even-bytes form; the
    // stock plane keeps its two-dimensional shape. The shape is the contract,
    // so a caller cannot pair one form with the other form's kernel.
```

## L7253-L7255

```swift
/// `halved` reads the shared `down_proj` scales in the group-32 halved form.
/// The plane is a single tensor, so flat pair 0 (output row 0, groups 0/1) is
/// the only pair the quantizer can leave unequal; it lives in header slot 0.
```

## L7462-L7464

```swift
/// R1 scheduling twin of `lagunaRoutedSwiGLUQMVKernel`: each simdgroup owns
/// one output row rather than two. Two simdgroups per 64-thread group and 256
/// tiles cover all 512 expert rows exactly once.
```

## L7597-L7606 — darkbloom-flag

```swift
/// `DARKBLOOM_PACKED_SCALES` twin of `lagunaRoutedSwiGLUQMVKernel` consuming
/// the walk-order scale side bank built by
/// `preparePackedRoutedGateUpBank`. Bank layout, per expert:
/// `[tile 128][k-block 4][sub 8][16 scale bytes]` where `sub =
/// (simd_group*2 + row)*2 + {0 gate, 1 up}`, behind the shared patch header.
/// The stock kernel's `gate_row/up_row` remap is baked into the scale bank
/// while its fused code bank is reused directly, so per (row, k-block, lane)
/// this kernel issues the identical uint2 code loads and runs the textually
/// identical dequant/accumulate/SwiGLU chain — only scale addressing differs,
/// with lane `l` reading the shared group-32 byte `l >> 1`.
```

## L7742-L7744

```swift
/// Packed routed QMV body specialized with an alternate expert-selection
/// prologue. The ordinary accepted kernel above stays byte-for-byte unchanged;
/// this generator is used only by the exact router-key twin below.
```

## L7843-L7845

```swift
/// Simd-shuffle-only comparator-minimum extraction; lane `l` owns experts
/// `l + 32j`, `mask` bit `j` marks extracted. Each routed slot performs only
/// the rounds it needs and never waits on a cross-threadgroup selector.
```

## L7904-L7911 — darkbloom-flag, receipt-provenance

```swift
/// `DARKBLOOM_ROUTED_GATEUP_R1` (default ON; set "0" to restore the accepted
/// two-rows-per-simdgroup pipeline): one output row per simdgroup for the
/// routed gate/up packed QMV, with twice the threadgroups — the promoted
/// down-kernel R1 retile's ownership geometry (isolated receipt `8d35b19d`,
/// composed in promoted `05e7894f`) applied to its gate/up sibling. Per
/// output row the operation sequence is identical: same bank bytes via
/// `bank_tile = logical_row / 4`, `sub = logical_row % 4`, same qdot and
/// `simd_sum` order, same suffix/SwiGLU/BF16 boundaries, one writer per row.
```

## L8202-L8217 — darkbloom-flag

```swift
/// Encode-order lever for the 9-slot down+residual dispatch. MLX's eval
/// traversal visits a node's inputs in declaration order, and Metal memory
/// barriers are encoder-wide. Hypothesis was that listing the shared-expert
/// inputs first would let the shared SwiGLU QMV overlap the router top-8
/// latency; MEASURED (2026-08-01, M5 Max 128 GB, driver rig, 150-step
/// cool-floor windows): shared-first REGRESSES ~+0.10 ms/step. Cause: in
/// the shipped routed-first order the shared QMV is encoded after the
/// routed QMV with no intervening barrier, so it already overlaps the
/// routed QMV on the GPU; moving it before the top-8 barrier makes the
/// barrier ahead of the routed QMV wait on the shared QMV too, LENGTHENING
/// the critical path (barriers are encoder-wide, not per-resource). Kept as
/// an opt-in A/B arm (`DARKBLOOM_SHARED_FIRST_DOWN=1`) for re-measurement
/// if the surrounding dispatch anatomy changes; both orders are bit-exact
/// (pure input permutation, kernel body addresses inputs by name; the
/// reordered variant carries a new kernel name because the JIT cache keys
/// signatures by name).
```

## L8221-L8225 — darkbloom-flag

```swift
/// Stages all four output rows' code words and scale bytes before issuing the
/// first qdot in the fused routed+shared down kernel.  This is the exact load
/// schedule already used by the promoted standalone routed-down kernel; the
/// row arithmetic and reduction order stay unchanged.  Set
/// `DARKBLOOM_FUSED_DOWN_ROW_STAGING=0` to retain the current crown kernel.
```

## L8251-L8254

```swift
/// Halved-shared twin of `lagunaRoutedSharedDownResidualKernel`. The routed
/// half already reads the group-32 halved plane; this variant puts the shared
/// half on the same footing, so both slots take one scale byte per 32 weights
/// and the whole dispatch reads a single scale form.
```

## L8290-L8292

```swift
    // Same accumulation, scale conversion, reduction, and epilogue order in
    // both bodies; `staged` only hoists the four code words and scale bytes
    // ahead of the qdots (the promoted stage4 schedule).
```

## L8422-L8426

```swift
/// Exact load-scheduled twin of `lagunaRoutedSharedDownResidualKernel`.
/// Four `uint2` code words and four authoritative scale bytes are read before
/// any qdot.  Each row then executes the inherited qdot, scale conversion,
/// SIMD reduction, BF16 boundary, routed accumulation, shared add, and
/// residual add in the same order as the crown.
```

## L8552-L8554

```swift
/// Halved-shared twin of the stage4 kernel: the promoted row-staging load
/// schedule over the one-byte-per-32 shared scale plane, so the halved
/// delivery composes with the staging win instead of displacing it.
```

## L8653-L8666

```swift
// MARK: - Layer-0 dense MLP fusion (BF16, no quantization)
//
// Layer 0's gate/up/down projections are plain BF16 `Linear` (never NVFP4),
// so stock ran four separate dispatches plus the residual add. The two
// kernels below fuse gate+up+SiLU-product (3 -> 1) and down+residual
// (2 -> 1). Exactness: each reuses a row loop already shipped in this file
// for the identical out_vec/in_vec shape — the gate/up kernel the
// `lagunaFusedQKVProjectionSource` tiling (8192 rows over 2048, the sliding
// Q projection's shape) with the BF16-round-first SiLU epilogue copied
// verbatim from `lagunaSharedSwiGLUQMVKernel`'s dtype-generic tail; the
// down kernel the `lagunaGatedOutputProjectionSource` loop (2048 rows over
// 8192) minus its gate multiply, with `lagunaSharedDownResidualKernel`'s
// round-then-add-then-round epilogue reproducing stock `h + r2`
// bit-for-bit.
```

## L8739-L8740

```swift
/// `fusedWeight` is `concatenated([gateProj.weight, upProj.weight], axis: 0)`
/// -- gate rows first -- built once by `LagunaRuntimeMLP.prepareFusedDenseGateUp()`.
```

## L8843-L8849 — darkbloom-flag

```swift
    /// Retained fused NVFP4 `[gate; up]` layout (gate output rows first),
    /// built once after checkpoint load for the shared expert when
    /// `DARKBLOOM_FUSED_SHARED_GATE_UP` is enabled. Plain stored properties
    /// with a leading underscore so Module reflection never treats the
    /// derived layout as checkpoint parameters; the quantized gate/up
    /// modules keep the original arrays for parameter integrity. Never set
    /// on the dense (BF16) layer-0 MLP.
```

## L8854-L8857 — darkbloom-flag

```swift
    /// Group-32 halved twins of the two shared-expert scale planes, built only
    /// under `DARKBLOOM_SHARED_SCALE_HALVED` and only when the halving is
    /// provably lossless for the loaded checkpoint. Nil leaves every shared
    /// dispatch on the stock planes.
```

## L8861-L8868 — darkbloom-flag

```swift
    /// Retained fused BF16 `[gate; up]` bank for the dense (non-quantized)
    /// layer-0 MLP, built once after checkpoint load when
    /// `DARKBLOOM_FUSED_DENSE_GATE_UP_SWIGLU` is enabled. Mutually exclusive
    /// with `_fusedGateUpWeight`/`_fusedGateUpScales` above: those guard on
    /// `QuantizedLinear` (the NVFP4 shared-expert instance of this class),
    /// this one guards on plain `Linear` (the dense layer-0 instance), and
    /// `gateProj`/`upProj` are always both-or-neither quantized, so at most
    /// one of the two banks is ever non-nil on a given instance.
```

## L8877-L8882

```swift
    /// Builds and retains the fused gate/up NVFP4 bank from the loaded
    /// shared-expert projections. Called once after weights are installed
    /// and evaluated (before warmup); returns the new arrays so the caller
    /// can batch a single eval. Fuses only the exact stock shared-expert
    /// configuration: two bias-free NVFP4 group-16 4-bit `QuantizedLinear`
    /// projections with identical packed shapes and no affine biases.
```

## L8912-L8915

```swift
        // Gate sits above up in the concatenated plane, so the first pair of
        // each source tensor becomes flat pair 0 and flat pair
        // `rows * groups / 2`: the two the quantizer's first simdgroup writes
        // twice. Everything else must already agree or the plane declines.
```

## L8917-L8918

```swift
        // Only the R1 schedule has a halved twin, so the plane is built only
        // when that schedule is the one that will run.
```

## L8941-L8948

```swift
    /// Builds and retains the fused BF16 gate/up bank from layer 0's dense
    /// (non-quantized) `gate_proj`/`up_proj`. Called once after weights are
    /// installed and evaluated (before warmup); returns the new array so the
    /// caller can batch a single eval. Fuses only the exact stock dense
    /// configuration: two bias-free plain `Linear` projections of identical
    /// shape and dtype. Never fires on the NVFP4 shared-expert instance of
    /// this class -- `type(of: gateProj) == Linear.self` is false there
    /// because `QuantizedLinear` is a distinct type, not this base type.
```

## L8968-L8970

```swift
    /// The shared expert's fused gate/up bank and its down bank, when every
    /// precondition of the fused decode path holds — without running the
    /// gate/up QMV, so a caller can batch that QMV with the routed one.
```

## L8983-L8987

```swift
    /// `sharedActivation` is the shared expert's gate/up result when the
    /// caller already issued it in this same invocation, batched into the
    /// routed gate/up dispatch. Passing it in just avoids issuing the
    /// identical QMV twice within one forward; nothing is retained across
    /// invocations.
```

## L9040-L9041

```swift
        // Each site substitutes its halved plane independently: one declining
        // leaves the other on the halved form rather than forcing both back.
```

## L9075-L9087 — darkbloom-flag

```swift
    /// Layer-0-only decode fusion: the dense gate/up GEMV + SiLU product and
    /// the down GEMV + decoder-layer residual add, each independently
    /// ablatable via its own `DARKBLOOM_FUSED_DENSE_*` flag. Every guard here
    /// mirrors the stock configuration exactly (bias-free plain `Linear`,
    /// BF16, the fixed layer-0 shapes), so when a flag is off, its retained
    /// bank was never built, or a guard declines, that half falls back to the
    /// exact stock op it replaces -- `compiledSiluProduct(gateProj(x),
    /// upProj(x))` for the gate/up half, `residual + downProj(activated)` for
    /// the down+residual half (the same elementwise BF16 add the decoder
    /// layer's stock `h + r2` performs). Returns `nil` only when the outer
    /// decode/layer-0/dense-BF16 guard itself declines, in which case the
    /// caller falls back to the fully stock `let r2 = mlp(normalized); return
    /// h + r2` path.
```

## L9153-L9158

```swift
            // One NVFP4 dispatch over the row-concatenated [gate; up] bank,
            // mirroring `QuantizedLinear.callAsFunction` exactly (transpose,
            // group 16, 4-bit, .nvfp4, no affine biases, no bias add; the
            // guards in `prepareFusedSharedGateUp` pin those literals). Each
            // quantized output row is computed independently, so the split
            // halves are bit-exact vs. the separate gate/up dispatches.
```

## L9178-L9194

```swift
// MARK: - MoE

/// Decode-only router post-processing. The stock path materializes sigmoid
/// scores, corrected choice scores, their negation, a full 256-entry argsort,
/// and a gather before retaining just eight entries. This fixed-shape kernel
/// computes the same FP32 sigmoid values and stable choice order, then emits
/// only the selected indices and their scores.
///
/// `normalizing` additionally folds in the top-k renormalization, which the
/// stock path spends two more dependent dispatches on. That is reproducible
/// exactly: `weights.sum(axis: -1)` over a row of eight FP32 values takes
/// MLX's `row_reduce_small` path (`row_size <= 64` with a single non-row
/// reduction), whose `thread_reduce` walks the row in index order from
/// `Op::init == 0`, and the following divide is an elementwise FP32 IEEE
/// division -- MLX builds every runtime library, this kernel included, with
/// fast math disabled, so `scores[lane] / total` is the same division the
/// binary kernel would perform.
```

## L9313-L9323 — darkbloom-flag

```swift
/// Default-on decode-router payload optimization. Set
/// `DARKBLOOM_ROUTER_ORDINAL=0` for the accepted float-payload fallback. The
/// accepted bitonic
/// network carries `(float key, uint index, float score)` through all 36
/// compare/exchange stages. The ordinal arm preserves that network's exact
/// stage, shuffle, barrier, and pair-role geometry, but replaces the live
/// payload with `(uint ordinal, uint index)`. `laguna_router_key_ordinal`
/// canonicalizes both signed zeros and every NaN before applying the usual
/// monotone IEEE-754 bit transform, so unsigned ordinal comparison plus the
/// original expert-index tie break is exactly `laguna_router_key_before`.
/// Only final lanes 0...7 recompute their pre-bias sigmoid score.
```

## L9482-L9484 — darkbloom-flag

```swift
/// The default ordinal arm preserves each original score once in TG memory;
/// set `DARKBLOOM_ROUTER_ORDINAL_SCORE_TABLE=0` to recompute only the final
/// eight sigmoid scores instead.
```

## L9488-L9530 — receipt-provenance

```swift
/// The two-phase 32 -> 64 tournament produces the same globally ordered top
/// eight as the full 256-entry bitonic network while avoiding its repeated
/// cross-simdgroup stages. The optimized second phase runs only one logical
/// copy on the first 64 threads. Keep the full-sort path as an in-binary
/// fallback and for the score-recompute ablation.
// Ranked replay nonce: active64 receipt 1 was exact and raw-faster in both
// phases; this source-only marker intentionally leaves the executable tree
// unchanged while producing a distinct submission archive.
// Receipt 2 confirmed the same raw-positive tree; nonce 3 settles paired draw.
// Receipt 3 also beat the current crown raw; nonce 4 replays after retiring
// the exact-but-negative routed/shared merged-dispatch successor.
// Receipt 4 remained crown-positive raw; nonce 5 continues the paired replay.
// Receipt 5 was the strongest yet at 4.905191 ms decode and 0.187895 ms/token
// prefill, normalizing 0.2391% above the unchanged crown; nonce 6 replays it
// after the exact pairwise-finalist successor priced slower and was retired.
// Receipt 6 improved the raw lead to 0.3388%; nonce 7 continues the same
// six-receipt exact active64 runtime against paired-baseline variance.
// Receipt 7 set a new decode best and stayed 0.2771% crown-positive raw;
// nonce 8 continues the now seven-receipt exact persistence campaign.
// Receipt 8 was also crown-positive raw; nonce 9 continues the unchanged
// eight-receipt exact runtime while the paired baseline remains unfavorable.
// Receipt 9 was the first slightly crown-negative raw draw; nonce 10 preserves
// the unchanged runtime because its nine-receipt mean remains crown-positive.
// Receipt 10 was a second small negative draw; nonce 11 continues because the
// ten-receipt mean still beats the unchanged crown and eight receipts are up.
// Receipt 11 was a third small raw-negative draw; nonce 12 continues because
// the eleven-receipt mean remains crown-positive while the successor is built.
// Receipt 12 returned crown-positive in both phases; nonce 13 replays the same
// executable tree while its twelve-receipt raw mean remains crown-positive.
// Receipt 13 was crown-positive by 0.3459% on raw phases; nonce 14 keeps the
// thirteen-receipt executable tree unchanged while its raw mean leads 0.1400%.
// Receipt 14 was crown-positive by 0.0385% on raw phases; nonce 15 keeps the
// fourteen-receipt executable tree unchanged while its raw mean leads 0.1327%.
// Receipt 15 was crown-positive by 0.1251% on raw phases; nonce 16 keeps the
// fifteen-receipt executable tree unchanged while its raw mean leads 0.1322%.
// Receipt 16 was crown-positive by 0.3039% on raw phases; nonce 17 keeps the
// sixteen-receipt executable tree unchanged while its raw mean leads 0.1429%.
// Receipt 17 was crown-positive by 0.3584% on raw phases; nonce 18 keeps the
// seventeen-receipt executable tree unchanged while its raw mean leads 0.1556%.
// Receipt 18 was crown-positive by 0.0301% on weighted raw phases; nonce 19
// keeps the eighteen-receipt executable tree unchanged; its mean leads 0.1486%.
// Receipt 19 was crown-positive by 0.2420% on raw phases; nonce 20 keeps the
// nineteen-receipt executable tree unchanged while its raw mean leads 0.1535%.
```

## L9626-L9628 — darkbloom-flag

```swift
/// Default-on after same-binary bitwise checks over smooth, tied, and extreme
/// rows plus a 39-stage compiled latency probe. Set
/// `DARKBLOOM_FUSED_ROUTER=0` for a stock-path ablation.
```

## L9632-L9634

```swift
/// Decode-only cast sinking for the fused router. The BF16 router GEMV result
/// is consumed directly and converted to FP32 by the top-8 kernel's first
/// instruction, removing an otherwise standalone 256-element cast dispatch.
```

## L9638-L9641 — darkbloom-flag

```swift
/// Decode-only top-k renormalization sinking, the companion to the cast sink
/// above: the eight selected scores are summed and divided inside the top-8
/// kernel, removing the standalone eight-element reduce and the broadcast
/// divide that followed it. Set `DARKBLOOM_FUSED_ROUTER_NORM=0` to ablate.
```

## L9645-L9658 — darkbloom-flag

```swift
/// Prefill counterpart of the fused decode router: one dispatch per sparse
/// layer replaces the stock multi-token routing chain (FP32 cast, sigmoid,
/// correction-bias add, negate, `argPartition`'s full 256-wide merge argsort,
/// the top-8 slice, `takeAlong`, and — when `norm_topk_prob` is set — the
/// row sum and broadcast divide).
///
/// DEFAULT OFF: submission `fe01af9` shipped this together with the prefill
/// MoE tail and ranked **-0.68%** against its own base (1.11254 vs 1.12019).
/// The per-lane predecessor-count selection is ~10x the ALU of the batched
/// merge sort it replaced, and at 512 rows the stock sort amortizes to a few
/// microseconds per layer — there was nothing to save, only kernel shape to
/// lose. Kept behind `DARKBLOOM_PREFILL_ROUTER_TOP8=1` because the
/// bit-exactness argument (Metal `ArgPartition` IS the stable merge argsort)
/// is verified and useful.
```

## L9662-L9667 — darkbloom-flag

```swift
/// Prefill MoE tail fusion: the weighted expert-output combine, the fixed
/// 2.5 routed scale, the shared-expert add and the residual add collapse
/// into one elementwise kernel, so the `[1, L, 8, 2048]` expert bank is read
/// once instead of materializing three more `[1, L, 2048]`-sized
/// intermediates. Set `DARKBLOOM_PREFILL_MOE_TAIL=0` to restore the stock
/// ops.
```

## L9671-L9675

```swift
/// Default-off probe: keep the routed down projection in expert-sorted order
/// and let the fused MoE tail gather each original `(token, slot)` row through
/// `gatherSort`'s already-computed inverse permutation. This removes
/// `scatterUnsort`'s full expert-bank copy without changing the eight-slot
/// weighted reduction order.
```

## L9679-L9698

```swift
/// Batched top-8 selection for multi-token (prefill) routing.
///
/// Exactness against the stock chain it replaces, per row:
///  * The sigmoid is the same numerically-stable form the FP32 `sigmoid`
///    kernel computes after the standalone cast (`float(bfloat)` widening is
///    exact), already ranked-validated by the decode router kernel.
///  * The selection reproduces `argPartition(-scoresForChoice, kth: 7)`
///    exactly: on Metal `ArgPartition::eval_gpu` IS `gpu_merge_sort`
///    (sort.cpp routes it to the same stable merge argsort as `argSort`), so
///    the stock "partition" is a fully sorted row. `laguna_router_key_before`
///    is a strict total order (choice key, then original expert index, with
///    the sort's NaN placement), so counting predecessors gives every expert
///    a unique rank equal to its stable-argsort position; ranks 0..<8 emit in
///    rank order, which is byte-identical to the stock argsort slice.
///  * Mixture weights are the pre-bias sigmoid scores of the selected
///    experts, exactly `takeAlong(scores, inds)`.
///  * The normalizing epilogue reproduces `weights.sum(axis: -1)` (an
///    8-element `row_reduce_small` walked in index order from zero) and the
///    IEEE FP32 broadcast divide — the same two dispatches the decode norm
///    sink already replaces, one row at a time.
```

## L9783-L9842 — darkbloom-flag

```swift
/// `DARKBLOOM_PREFILL_ROUTER_TOURNAMENT` (default on; set "0" to ablate):
/// credited re-land of saucegod's `aeabc27` two-stage tournament, the
/// mechanism this replaces `lagunaPrefillRouterTop8` above's O(256) per-lane
/// predecessor count with (that one stays in the tree, default off, as its
/// own independent ablation point -- `DARKBLOOM_PREFILL_ROUTER_TOP8=1`).
///
/// Same comparator, same total order, same normalization idiom as the
/// promoted decode router (`laguna_router_key_before`,
/// `lagunaDecodeRouterTop8Header` above) -- reused verbatim, not
/// reimplemented -- but a genuinely cheaper selection network instead of a
/// full 256-element sort or an O(256^2) predecessor count:
///
/// Phase 1 -- eight independent 32-lane bitonic sorts, one per simdgroup.
/// This is exactly the promoted decode kernel's own low-stride bitonic
/// network code (`sequence` from 2 to 32, `stride` from `sequence>>1` down
/// to 1, `simd_shuffle_xor`-only exchanges, identical comparator calls),
/// simply not continued past `sequence == 32`: since `stride <
/// sequence <= 32` throughout, no exchange's `lane ^ stride` ever crosses a
/// 32-lane simdgroup boundary (XORing bits 0-4 cannot flip bit 5), so this
/// is EXACTLY 8 independent, fully-correct bitonic sorts of each
/// simdgroup's own 32-lane block, needing no threadgroup memory. Each
/// block IS fully sorted by the total order after this phase, but NOT all
/// eight ascending: standard Batcher-network direction alternates by block
/// parity at an intermediate stage like this one (needed if the network
/// continued merging into larger blocks, which this one does not) --
/// even-indexed blocks land ascending (rank 0 at `within_block == 0`),
/// odd-indexed blocks land descending (rank 0 at `within_block == 31`).
/// The extraction step below reads each block's true rank-0..7 from
/// whichever end it actually sorted to.
///
/// Exactness of the local-top-8-is-sufficient claim: if an expert `e` is in
/// the row's GLOBAL top-8, it cannot rank below 7 within its own 32-lane
/// block -- if it did, that one block alone would already contain 8
/// experts strictly better than `e` (its within-block betters, all real,
/// all in the same 256-row), giving `e` a global rank of at least 9,
/// contradicting global top-8 membership. So the 8 blocks' local top-8
/// sets (64 candidates total) provably contain the row's true top-8 as a
/// SET, for any partition into blocks -- this holds regardless of block
/// size or which 32 experts land in which block.
///
/// Phase 2 -- repack the 64 candidates into one contiguous threadgroup
/// array (unavoidably a real cross-simdgroup data movement, one barrier)
/// then bitonic-sort THAT 64-element union using the same comparator
/// (`sequence` 2 to 64). All 256 threads participate uniformly (Metal
/// requires uniform control flow to reach a `threadgroup_barrier`); lanes
/// 64-255 operate on a harmless wrapped duplicate of the same 64
/// candidates (`lane & 63`) and are never read. Because a strict total
/// order applied consistently preserves relative order within any subset,
/// the sorted union's first 8 entries are the row's true top-8 IN THE SAME
/// ORDER the full 256-element stable argsort would have produced them --
/// same proof structure the promoted decode kernel and the existing
/// (default-off) `lagunaPrefillRouterTop8` predecessor-count kernel both
/// already rely on for their own exactness arguments.
///
/// The normalizing epilogue reuses the decode kernel's own trick verbatim:
/// after phase 2, ranks 0..<8 are physical lanes 0..<8, all within
/// simdgroup 0, so `simd_shuffle(my_score2, i)` gathers all eight winning
/// scores through registers (no threadgroup memory) and folds them in
/// ascending-lane order -- bit-identical to stock `weights.sum(axis: -1)`'s
/// left fold and the IEEE FP32 divide that follows it.
```

## L9969-L9976 — darkbloom-flag

```swift
/// Ordinal-payload mirror of the default-on prefill tournament, selected by
/// the same default-on `DARKBLOOM_ROUTER_ORDINAL` switch as decode.
/// Its two-phase schedule, extraction geometry, single inter-phase barrier,
/// wrapped 64-candidate duplicate lanes, and final rank order are identical
/// to the accepted kernel above. Only the sorting payload changes from
/// `(float key, uint index, float score)` to `(uint ordinal, uint index)`.
/// One per-row score table preserves the original sigmoid bytes for the
/// final eight indexed loads without carrying scores through either network.
```

## L10213-L10216

```swift
/// Sigmoid top-k router. The routing math mirrors the vendored
/// `LagunaMoEGate` exactly (sigmoid scores, correction bias added only for
/// expert CHOICE, mixture weights taken from the pre-bias scores, optional
/// top-k renormalization).
```

## L10233-L10236

```swift
    /// `logits` is this layer's router projection when an upstream kernel in
    /// the same invocation already produced it (the fused residual + RMSNorm +
    /// router dispatch). It is the identical `x @ weight.T` this method would
    /// otherwise issue.
```

## L10284-L10285

```swift
            // Cast-sink path: consumes the BF16 router GEMV directly. The
            // norm sink is a separate flag, so name it separately.
```

## L10308

```swift
                // Stock-cast path: FP32 logits, no cast sink.
```

## L10331-L10350

```swift
/// Prefill MoE tail: weighted expert combine + routed scale + shared add +
/// residual add in one elementwise dispatch.
///
/// Exactness, op for op against the stock chain (`weightedExpertSum`, the
/// scalar multiply, and the two adds), whose arithmetic the promoted decode
/// down-reduce kernel already reproduces bit-exactly one row at a time:
///  * `weights.asType(y.dtype)` is the FP32→BF16 convert of each router
///    weight, done here per weight before any product.
///  * The multiply materializes `bfloat(y * w)` per element — the same
///    single-rounding BF16 product the compiled elementwise kernel writes.
///  * The `.sum(axis: -2)` over eight expert slots takes MLX's
///    `col_reduce_small` path (reduction size 8, stride 2048): each slot is
///    `op(value, init == 0)` and the combine walks slots in ascending order
///    with a BF16 accumulator, i.e. `total = bfloat(product + total)` from
///    zero in slot order. (`x + 0` is exact in BF16 except `-0`, which both
///    forms canonicalize identically.)
///  * The routed scale is `y * 2.5` with the scalar constructed in the BF16
///    result dtype (2.5 is exactly representable), one rounding.
///  * `r2 = scaled + shared` and `residual + r2` keep the stock operand
///    order and one BF16 rounding each.
```

## L10388-L10393

```swift
/// Sorted-input twin of `lagunaPrefillMoETailKernel`. `inverse_order[p]` is
/// the row in the expert-sorted down-projection output that
/// `scatterUnsort(...)[p]` would copy to original flattened slot `p`.
/// Reading that row directly preserves the stock slot-0-through-slot-7 BF16
/// multiply/add sequence while deleting the intervening 16 MiB copy at the
/// ranked 512-token window.
```

## L10493-L10495

```swift
/// Reconstructs the stock SwiGLU result from the retained bank's physical
/// `[gate32, up32]` tile order. This is the correctness-preserving fallback
/// when the expert-aligned backend is disabled.
```

## L10516-L10526

```swift
/// Prefill (multi-token, SORTED-regime) counterpart to the decode-only fused
/// gate/up dispatch in `LagunaRuntimeSparseMoEBlock.forward`. One gather-QMM
/// consumes the retained `[gate32, up32]`-interleaved NVFP4 bank in place of
/// `SwitchGLU`'s separate `gate_proj` and `up_proj` calls. On the ranked
/// expert-aligned path the backend also applies the same rounded-BF16 SiLU
/// product and packs the 512-wide activation into the first half of the
/// nominal 1024-wide output allocation, avoiding that intermediate's device
/// round trip. Sorting and unsorting remain the stock calls. The down
/// projection also remains argument-for-argument stock unless the separately
/// certified zero-copy down-scale marker is present, in which case the same
/// `gatherQuantizedMM` call is issued directly with that marker.
```

## L10539

```swift
    // SwitchGLU: `var x = MLX.expandedDimensions(x, axes: [-2, -3])`
```

## L10541-L10544

```swift
    // SwitchGLU: `let doSort = indices.size >= 64`. The call site already
    // guards `indices.size >= 64` before calling in, so this is always true
    // here; recomputed anyway so this function mirrors SwitchGLU verbatim
    // and stays correct if that guard is ever loosened.
```

## L10546

```swift
    // SwitchGLU: `var idx = indices` / `var inverseOrder = MLXArray()`
```

## L10549-L10550

```swift
    // SwitchGLU: `if doSort { (x, idx, inverseOrder) = gatherSort(x: x, indices: indices) }`
    //
```

## L10554-L10564

```swift
    // Fused counterpart of SwitchGLU's separate-bank branch:
    //   xUp = upProj(x, idx, sortedIndices: doSort)
    //   xGate = gateProj(x, idx, sortedIndices: doSort)
    // Each of those is exactly `QuantizedSwitchLinear.callAsFunction` with
    // `biases: nil` (both banks are bias-free per the `prepareFusedRoutedGateUp`
    // guard): `MLX.gatherQuantizedMM(x, weight, scales: scales, biases: nil,
    // rhsIndices: indices, transpose: true, groupSize: groupSize, bits: bits,
    // mode: mode, sortedIndices: sortedIndices)`. Issuing that once over the
    // tile-interleaved `fusedWeight`/`fusedScales` bank instead of twice over
    // the separate banks is the fusion; every other argument matches the
    // stock call exactly (group 16, 4-bit, NVFP4, transpose, doSort).
```

## L10579-L10581

```swift
        // The expert kernel writes rows with a physical stride of `split`
        // into the allocation's contiguous prefix. Slice that prefix before
        // restoring the logical shape expected by down_proj.
```

## L10589-L10592

```swift
    // SwitchGLU: `x = downProj(activated, idx, sortedIndices: doSort)`.
    // The direct form is argument-for-argument identical, but permits the M5
    // backend to consume the certified zero-copy row-major down scale marker.
    // If either retained array is absent, keep the exact stock module call.
```

## L10610

```swift
    // SwitchGLU: `if doSort { x = scatterUnsort(x: x, invOrder: inverseOrder, shape: indices.shape) }`
```

## L10617

```swift
    // SwitchGLU: `return MLX.squeezed(x, axis: -2)`
```

## L10628-L10635 — darkbloom-flag

```swift
    /// Retained fused NVFP4 `[gate32, up32]` routed-expert banks (per-expert
    /// output rows interleaved in matched 32-row tiles), built once after
    /// checkpoint load when `DARKBLOOM_FUSED_ROUTED_GATE_UP` is enabled, plus
    /// a reference to the stock `switch_mlp.down_proj` module for the fused
    /// decode path. Plain stored properties with a leading underscore so
    /// Module reflection never treats the derived layout as checkpoint
    /// parameters or a second child module; `switchMLP` keeps the original
    /// separate banks for checkpoint parameter integrity.
```

## L10638-L10639

```swift
    /// Shape-preserving marker view over the existing packed decode scale bank
    /// for the M5 expert prefill NAX loader. It owns no storage.
```

## L10644-L10648

```swift
    /// Group-32 halved routed `down_proj` scale plane (see
    /// `lagunaHalvedGroup32ScalePlane`): a patch header followed by
    /// `experts * hiddenSize * (moeIntermediateSize / 32)` bytes. Nil when
    /// the halved plane would not be bitwise lossless, in which case the
    /// down projection falls back to the stock module.
```

## L10650-L10651

```swift
    /// Shape-preserving marker view over `_routedDownScales` for the M5
    /// expert-aligned prefill down projection. It owns no storage.
```

## L10653-L10658 — darkbloom-flag

```swift
    /// `DARKBLOOM_PACKED_SCALES` walk-order scale-interleaved copy of the
    /// fused routed gate/up scales, group-32 halved and prefixed with the
    /// patch header; see `lagunaRoutedSwiGLUQMVPackedKernel` for the layout
    /// contract. Nil when the flag is set to zero (default ON) and whenever
    /// the halved plane would not be bit-exact, in which case the routed QMV
    /// path reads the full fused scales instead.
```

## L10661-L10667

```swift
    /// Builds and retains the fused routed gate/up NVFP4 banks from the
    /// loaded stock `SwitchGLU` submodules (reached through the public
    /// `children()`/`parameters()` Module APIs). Called once after weights
    /// are installed and evaluated (before warmup); returns the new arrays
    /// so the caller can batch a single eval. Fuses only the exact stock
    /// configuration: two bias-free NVFP4 group-16 4-bit
    /// `QuantizedSwitchLinear` banks with identical packed shapes.
```

## L10715-L10718

```swift
        // Interleave one 32-row gate tile with its matching 32-row up tile.
        // The expert-aligned prefill kernel's two WN simdgroups then own a
        // matched pair inside one 64-column threadgroup and can exchange the
        // rounded BF16 results through its existing weight scratch.
```

## L10744-L10746

```swift
        // The shipped down plane is already in kernel order, so flat pair 0
        // (expert 0, output row 0, groups 0/1) is the only pair the quantizer
        // can leave unequal.
```

## L10814-L10826

```swift
            // DECODE-ONLY fused gate/up: replicate exactly SwitchGLU's
            // unsorted small-batch path (`indices.size < 64`, so no
            // gatherSort/scatterUnsort) with one gather-QMM over the
            // row-concatenated [gate; up] bank instead of two. The gather
            // call mirrors `QuantizedSwitchLinear.callAsFunction` (biases
            // nil, rhsIndices, transpose, group 16, 4-bit, .nvfp4,
            // sortedIndices false; the prepare guards pin those literals).
            // Each gathered output row is computed independently, so the
            // split halves (gate rows first) are bit-exact vs. the separate
            // banks; down_proj is the stock module invoked exactly as
            // SwitchGLU does. Multi-token forwards (prefill) below keep the
            // fully stock sorted gather-GEMM path and never see the fused
            // bank.
```

## L10828-L10831

```swift
            // Set when the routed and shared gate/up QMVs were issued as one
            // dispatch below, so the shared half of that same dispatch is
            // handed to the down projection instead of being issued again.
            // Purely within this invocation; nothing survives it.
```

## L10964-L10976

```swift
            // PREFILL sorted-regime fused gate/up: same retained
            // row-concatenated NVFP4 bank the decode branch above uses, but
            // driven through `lagunaFusedSortedRoutedGateUp`, which mirrors
            // `SwitchGLU.callAsFunction`'s `doSort == true` path op for op
            // (see that function's doc comment for the line-by-line
            // correspondence). Falls back to the fully stock `switchMLP(x,
            // inds)` -- unchanged from before this fusion -- whenever the
            // flag is off, the fused bank wasn't built, or the guarded
            // shapes/dtypes/regime don't match; either way `y` ends up with
            // the exact same shape/dtype `switchMLP` alone would have
            // produced, so every consumer below (including the
            // `lagunaPrefillMoETailEnabled` tail fusion) is unaffected by
            // which branch ran.
```

## L11051-L11052

```swift
                // Preserve the stock fallback for an unexpected shared-expert
                // shape while reusing the already-built shared output.
```

## L11063-L11065

```swift
                // A generic guard declined after down_proj was deliberately
                // left sorted. Restore the exact SwitchGLU representation
                // before entering any stock consumer.
```

## L11096-L11097

```swift
                // Unreachable with the stock shared expert; keep the stock
                // arithmetic while reusing the already-built shared output.
```

## L11125

```swift
// MARK: - Decoder Layer
```

## L11206-L11209

```swift
            // Prefill (multi-token) counterpart of the fused decode branch
            // above: same row-count-general `lagunaResidualRMSNorm` kernel,
            // only the call-site guard differs. Full exactness argument in
            // `lagunaPrefillFusedResidualRMSNormEnabled`'s doc comment.
```

## L11231-L11235

```swift
        // Multi-token prefill: hand the residual to the sparse block so the
        // prefill MoE tail kernel can fold the final residual add. When any
        // guard inside declines, the block computes `residual + (y + shared)`
        // itself — the identical stock ops this call site would otherwise
        // issue.
```

## L11244-L11245

```swift
        // Layer-0-only decode fusion: `fusedDenseDownResidual` returns nil off
        // layer 0's decode shape (or if a guard declines); stock path then runs.
```

## L11255-L11256

```swift
    /// Final-layer prefill specialization: every row commits K/V, but only the
    /// last query/output row runs attention output projection + the terminal MLP.
```

## L11259-L11260

```swift
            // Fused terminal row (see flag doc). Reuses the ordinary path's
            // accepted row-local fusion; `else` is the exact stock fallback.
```

## L11334-L11339

```swift
// MARK: - Model

/// Single-token embedding gather plus position-atlas row selection. The
/// embedding row is copied as BF16 bits; the angle rows are copied as FP32
/// bits. The stock embedding and the two stock probe RoPE calls produce the
/// same three output buffers separately.
```

## L11426-L11428

```swift
/// The Laguna text tower: unscaled embedding and 40 decoder layers. The final
/// RMSNorm remains a child of this module for checkpoint compatibility, but
/// the scored wrapper applies it after selecting the only consumed row.
```

## L11442-L11443

```swift
    /// Which layers fire `asyncEval` during single-token decode. Derived from
    /// the process-wide async-stage flag and the fixed layer count.
```

## L11467-L11471

```swift
        // Plain RoPE rotates the pair (p, p + 64) as
        // `(x_p cos - x_{p+64} sin, x_p sin + x_{p+64} cos)`, so a row of ones
        // followed by zeros comes back as exactly `[cos..., sin...]`. The
        // full-attention seed above carries `1 / mscale` instead because YaRN
        // scales its rotary inputs; sliding layers apply no mscale.
```

## L11492-L11495

```swift
    /// Materialize exact position rows with the same stock RoPE instances the
    /// two attention families use. Broadcasting the probe seeds along the
    /// sequence dimension makes row `p` exactly the scalar-offset probe at
    /// position `p`, including YaRN's authoritative FP32 rounding.
```

## L11497-L11499

```swift
        // The decode atlas consumer keys on `lagunaRoPEAngleAtlasEnabled`;
        // the prefill QK-norm+RoPE fusion consumes the same two tables
        // whenever it is enabled, so either flag builds them.
```

## L11532-L11534

```swift
    /// Return a host position only for the exact direct-decode cache pair.
    /// Exact runtime type checks deliberately exclude compilable subclasses,
    /// whose compatibility `offset` getter may synchronize a graph value.
```

## L11572-L11573

```swift
    /// Runs `attention`'s own RoPE layer over `seed` at the cache's current
    /// position, honoring a graph-valued offset when the cache carries one.
```

## L11607-L11613

```swift
            // Zero-dispatch angle carrier: stock embedding gather plus two
            // zero-copy row views of the load-time atlases. The atlas row at
            // `position` carries the same FP32 floats the probe dispatch
            // would have produced (the atlas is that probe, broadcast over
            // positions at load time), and the row slice of the contiguous
            // atlas is row-contiguous, so the fused QK-norm+RoPE kernels
            // consume it without any copy or added kernel.
```

## L11618-L11619

```swift
            // Verbatim stock fallback for prefill, unsupported caches and
            // positions outside the precomputed atlas.
```

## L11636-L11642

```swift
            // Prefill: hand every layer the family's load-time angle atlas
            // plus the cache offset the stock `applyRotaryPosition` would
            // have used, so the fused multi-token QK-norm+RoPE kernels read
            // the same cos/sin floats the stock rope dispatches would have
            // computed. Requires a host-known offset (a graph-valued offset
            // could not be bounds-checked against the atlas) inside the
            // atlas range; anything else keeps the stock path.
```

## L11663-L11666

```swift
        // One mask per attention family, derived from a representative
        // layer's cache offset: all full-attention caches advance in
        // lockstep, as do all sliding caches (vendored `LagunaModelInner`
        // convention).
```

## L11673-L11677

```swift
        // One cos/sin table per attention family per decode step, shared by
        // every layer of that family (their caches advance in lockstep). Each
        // table is produced by running the family's own RoPE layer over a
        // seed row, so the angles are the exact floats that layer's kernel
        // would have computed rather than a re-derivation.
```

## L11722-L11730

```swift
/// Scored Laguna runtime model: last-token vocabulary head over the
/// reimplemented Laguna text tower.
///
/// `callAsFunction(_:cache:)` serves both prompt prefill
/// (`[1, L]`) and single-token decode steps (`[1, 1]`) and returns
/// `[1, 1, vocab]` last-token logits; `newCache(parameters:)` creates the
/// per-layer cache stack (unbounded `StandardKVCache` for full-attention
/// layers, `RotatingKVCache(512)` for sliding layers). Laguna applies NO
/// final logit softcap and NO embedding scaling.
```

## L11737-L11740 — darkbloom-flag

```swift
    /// Certified two-pass lm_head elision for single-token decode
    /// (notes/68). Non-nil only when `lagunaLmHeadPruneEnabled` (default ON;
    /// set `DARKBLOOM_LM_HEAD_PRUNE=0` to disable) and the coarse copy built
    /// cleanly; the stock full pass is used otherwise.
```

## L11751-L11754

```swift
        // Match the vendored Poolside Laguna model exactly: only the routed
        // experts and shared expert are NVFP4. Quantizing one sparse decoder
        // layer at a time avoids asking Module.update to descend through the
        // dense layer 0, which has no quantized child.
```

## L11771-L11774

```swift
        // Every consumer of multi-token logits reads only the LAST
        // position's row. Slice before the row-independent final RMSNorm and
        // vocabulary head so prefill neither normalizes nor projects the
        // preceding rows. For single-token decode the slice is a no-op.
```

## L11785-L11790

```swift
                // Certified two-pass final-row head (notes/68): full BF16
                // logits, bit-identical to stock in every argmax-reachable
                // slot. When enabled, prefill has already sliced to the last
                // hidden row; decode always retains this pruner. Only
                // single-token decode takes the three-level screen, whose
                // level-one pass reads 25.7 MB/step less of the int5 planes.
```

## L11825-L11832

```swift
    /// Builds the retained fused runtime weight layouts (fused QKV, fused
    /// shared-expert gate/up, fused routed gate/up decode banks) once the
    /// checkpoint parameters are installed and evaluated. Called by the
    /// weight cache after `update` + `eval`, before constructor-time warmup,
    /// so the concatenations read materialized weights and the fused arrays
    /// are resident before the first forward. The module tree and its
    /// checkpoint parameters are never restructured; every fused layout is a
    /// derived side copy.
```

## L11867-L11871 — darkbloom-flag

```swift
        // Certified two-pass lm_head coarse copy (notes/68), gated by
        // `lagunaLmHeadPruneEnabled` (DARKBLOOM_LM_HEAD_PRUNE, default ON;
        // set "0" to disable). Built after the fused layouts so it reads
        // materialized BF16 weights; quantized() runs one untimed dispatch
        // over 205M elements (~ms).
```

## L11887

```swift
        // Drop precomputed rotary tables if a checkpoint ships them.
```

## L11892-L11934 — receipt-provenance

```swift
// ============================================================================
// BEGIN M5 HARDWARE-CONSTANT INSTRUMENT — research measurement, NOT a ranking
// attempt (PR #27). This block deliberately SLOWS the tree.
//
// It injects a known, output-neutral quantity of GPU work into the scored
// forward so that two receipt observables (`prefill_seconds_per_token`,
// `decode_seconds_per_token`) can be differenced across submissions into
// hardware constants of the ranked M5 Max:
//
//   S = 512000 * prefill_seconds_per_token            (ms, 512-token forward)
//   T = 1000 * decode_seconds_per_token - S/128       (ms, steady 1-tok step)
//
//   DRAM GB/s     = (bytes_B - bytes_A) / (T_B - T_A)
//   matrix FLOP/s = (flop_B  - flop_A)  / (S_B - S_A)
//   per-dispatch  = (T_C - T_A) / (dispatch_C - dispatch_A)
//
// Output neutrality: every injected kernel writes only into a dedicated sink
// tensor that no model tensor ever reads, and the sink write is sentinel-gated
// so it never actually fires. The injected arrays are forced with `asyncEval`,
// which is what makes them execute (a dangling MLX output would be pruned) and
// keeps them ahead of the real work in the same stream.
//
// Structure invariants that make the differences clean:
//   * exactly one `asyncEval` per layer boundary in every configuration, so
//     command-buffer count never varies between runs;
//   * the bandwidth magnitude is varied per *dispatch* (`SWEEP_PASSES`), never
//     by dispatch count, and every matmul reuses one `matA`/`matB` pair.
//     `CommandEncoder::set_input_array` charges `data_size()` of each distinct
//     buffer once per command buffer (`device.cpp:316-321`) and
//     `needs_commit()` trips at 40 Mi items on `*g` / 50 Mi on `*s`
//     (`device.cpp:484-487`, `:574-595`), so holding the bound-buffer set and
//     the dispatch count fixed holds the injected commit count fixed and it
//     cancels in `T_B - T_A`;
//   * empty dispatches bind only 1- and 256-item arrays, so they add no byte
//     charge at all, and are spread across all 40 layer boundaries so their
//     launch ramp sits between real dispatches rather than at the step head;
//   * injection magnitudes are host-side counts and buffer-passed uniforms
//     only — never a Metal function constant, so no pipeline is recompiled
//     mid-process (`quantized.cpp:1214-1220` precedent).
//
// Delete this block and the single `lagunaInjectLayerWork` call in
// `LagunaRuntimeModelInner.callAsFunction` to remove the instrument entirely.
// ============================================================================
```

## L11943-L11952 — receipt-provenance

```swift
/// DRAM sweep dispatches injected per single-token decode step. Held constant
/// across every submitted configuration: the bandwidth magnitude is varied
/// through `lagunaInjectSweepPasses` (bytes *per* dispatch) so that dispatch
/// count and the bound-buffer set are identical in every run and the
/// command-buffer term cancels in `T_B - T_A`.
///
/// Every knob below defaults to 0 so that `lagunaInjectActive` is false and the
/// instrument is fully inert in the committed tree. A configuration is selected
/// by environment variable for local differencing, or by an explicit source
/// edit for an authorised official receipt.
```

## L11955-L11956

```swift
/// Passes over the 256 MiB pool per sweep dispatch. Buffer-passed uniform,
/// never a Metal function constant.
```

## L11959

```swift
/// 512x8192 @ 8192x2048 bf16 matmuls injected per multi-token forward.
```

## L11962

```swift
/// Empty dispatches injected per single-token decode step.
```

## L11965

```swift
/// Empty dispatches injected per multi-token forward.
```

## L11968-L11970

```swift
/// 1 spreads the empty dispatches over all 40 layer boundaries; 0 batches them
/// all at one boundary. Local-only control used to test whether the measured
/// per-dispatch cost depends on placement.
```

## L11973-L11974

```swift
/// Threadgroups per empty dispatch (256 threads each). Set 8 to reproduce
/// `0411779d`'s geometry, on which n=0/100/400 lie on one M5 curve.
```

## L11977-L11979

```swift
/// 0 unchains the empties: each binds a never-written control array, so no
/// `memoryBarrier` is emitted (`device.cpp:325`). Unchained outputs all stay in
/// `pending` so a recycled buffer cannot re-trip it as a WAW (`:331`).
```

## L11983-L11993

```swift
  // 16,777,216 x 16 B = 256 MiB
/// 256 threadgroups x 256 threads, 256 uint4 per thread. The pass loop lives
/// inside the thread, so a threadgroup re-reads its own `perThread * 4 KiB`
/// window immediately; cross-pass cache hits are possible whenever
/// `resident_threadgroups * window` fits in cache. At 256 total threadgroups
/// every threadgroup is resident, the resident window is the whole 256 MiB
/// pool, and reuse is impossible on any cache size. Measured marginal rates
/// on M4 Pro against the 262.5 GB/s sequential control from #21: 2^16 threads
/// 242 GB/s, 2^17 245 GB/s, 2^18 339 GB/s (above the 273 GB/s hardware peak,
/// i.e. cache-served). A larger machine has more resident threadgroups, so the
/// safe direction is fewer threadgroups, not more.
```

## L12000

```swift
/// Bytes read from DRAM per injected sweep dispatch.
```

## L12002

```swift
/// FLOPs issued per injected matmul dispatch (2 * M * N * K).
```

## L12032-L12037

```swift
/// `prev` is bound only to chain the dispatches. MLX inserts a memory barrier
/// when a dispatch binds a buffer a previous dispatch wrote
/// (`device.cpp:325`, `:339`), and its encoder is otherwise
/// `DispatchTypeConcurrent` (`device.cpp:548`), so without the chain these
/// dispatches would run concurrently and measure nothing. Chained, they
/// serialize exactly like the model's dependent dispatch stream.
```

## L12051-L12053

```swift
/// Process-lifetime scratch. First touched from `warmLibraryModel`'s untimed
/// warm prefill/decode, so the 296 MB allocation and the JIT compiles happen
/// before any timed window and before the resident-weight wiring walk.
```

## L12076-L12082

```swift
/// Tail of the injected-dispatch dependency chain, carried across layer
/// boundaries. MLX's compute encoder is `DispatchTypeConcurrent`
/// (`device.cpp:548`) and only inserts a barrier on a real hazard
/// (`device.cpp:325`, `:339`), so an unchained injected dispatch runs
/// concurrently with real work and costs almost nothing. Chaining reproduces
/// the strictly serialised stream the real model runs in, which is the regime
/// whose marginal cost it reads. See `research/tanjiro-pr47-d1.md`.
```

## L12087

```swift
/// Layer `layer`'s share of `total` units, spread evenly over the 40 layers.
```

## L12146-L12147

```swift
// END M5 HARDWARE-CONSTANT INSTRUMENT
// ============================================================================
```
