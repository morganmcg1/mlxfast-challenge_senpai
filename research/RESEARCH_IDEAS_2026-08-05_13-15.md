# Ranked Causal Research Ideas — 2026-08-05 13:15 UTC

## Decision frame

- Objective: improve the serial text-tower score, weighted 75% decode and 25% prefill, without changing any checked token.
- Evidence basis: the programme, current research state, targeted scored-path inspection, and one compact local history synthesis. No individual PR was refetched. The broad synthesis task terminated after leaving a usable draft, so an independent scored-path inspection was audited and integrated; historical completeness remains a residual risk.
- Budget split: idea 0, ideas 1–2, and seams A–C fit or reduce the current 2,168-byte margin; ideas 3–6 wait for the projected 19,353-byte post-cleanup margin.
- Exclusions: active/held mechanisms and low-value directions listed in the living state are not duplicated, except idea 0, which was assigned as PR #53 after this synthesis identified it.
- Privacy: only technical mechanisms and public repository paths are recorded.


### 0. Elide the unused value reshape on fused attention — assigned as PR #53

**Hypothesis:** the scored fused sliding/full paths populate `fusedAttended`, but the runtime still constructs the fallback `values` reshape/transposition before nil-coalescing skips `attentionWithCacheUpdate`. Moving that reshape into the fallback branch removes one dead lazy-graph/view operation per reached fused layer without changing math or cache state.

- **Submitted path:** `Sources/MLXFastModel/LagunaRuntimeModel.swift` only.
- **Reachability:** fused sliding/full branches set `fusedAttended` around `LagunaRuntimeModel.swift:5701-5749`; the unconditional value reshape occurs before the fallback selection around `:5760-5826`.
- **Byte risk:** negligible and preferably negative.
- **Correctness risk:** very low if the existing one-token and multi-token fallback reshape is preserved exactly.
- **Cheapest decisive test:** one control-first matched `--local-iterate` pair with `130/130` exact tokens; repeat once only if noise could change the decision.
- **Stop rule:** stop on any fallback, cache, token, or budget regression; otherwise confirm only a clear same-host gain with both component floors intact.
- **Why current evidence is non-dispositive:** prior attention and projection experiments changed kernels, geometry, or metadata; none isolated this host graph-construction operation.

## Feasible now under 2,168 bytes

### 1. Share one full-attention parameter carrier across aligned layers

**Hypothesis:** host-side construction of the same three-word full-cache parameter array once per full-attention layer is measurable in serial decode; one position/capacity-keyed carrier reused by all full layers in that invocation removes most of those allocations without changing GPU arithmetic.

- **Mechanism:** replace per-layer `MLXArray([writeIdx, writeIdx + 1, capacity])` creation with a compact one-entry serial cache keyed by `(writeIdx, capacity)`. Its genuine hits are across layers within the same invocation, not repeated prompts.
- **Likely submitted path:** `Sources/MLXFastModel/LagunaRuntimeModel.swift` only.
- **Reachability:** `lagunaFullFusedAttention` creates the carrier at `LagunaRuntimeModel.swift:2245-2247`; the scored full-attention decode branch calls it at `:5737-5749` for every supplied one-token step.
- **Byte risk:** low, approximately +700 to +1,500 bytes if implemented as one small store; reject the implementation before timing if total growth exceeds 1,600 bytes.
- **Correctness risk:** low numerically; medium for accidental stale/concurrent reuse. Key both dynamic values, retain the existing serial-worker invariant, and never cache token-dependent data.
- **Cheapest decisive test:** add a temporary allocation counter proving one construction per decode position, compare cached and uncached helper outputs exactly at capacity boundaries, then run two matched local decode pairs.
- **Stop rule:** stop on any output mismatch, cache-position error, growth above 1,600 bytes, or decode improvement below 0.20% in both matched pairs.
- **Why current evidence is non-dispositive:** the existing sliding-ring atlas covers a fixed one-word index; it does not test a dynamic three-word carrier shared across full layers. GPU geometry and projection-metadata evidence do not isolate this Swift allocation.

### 2. Compile duplicated fused-attention shape checks out of release

**Hypothesis:** repeated Swift `shape == [...]` and dtype preconditions add avoidable CPU dispatch work on every fused sliding/full attention call after the caller has already established the eligible fixed geometry.

- **Mechanism:** keep all checks as debug `assert`s, retain dynamic write-index/capacity guards in release, and remove only duplicated fixed dtype/shape preconditions from optimized builds.
- **Likely submitted path:** `Sources/MLXFastModel/LagunaRuntimeModel.swift` only.
- **Reachability:** the checks execute in the scored sliding helper at `:1712-1731` and full helper at `:2223-2242`; guarded decode dispatch reaches them at `:5701-5749`.
- **Byte risk:** very low and probably net-negative; allow at most +300 bytes.
- **Correctness risk:** no arithmetic change, but medium defensive risk if an eligibility guard is incomplete. Preserve dynamic bounds and make debug builds fail on every former invariant.
- **Cheapest decisive test:** build one release A/B differing only in check compilation, run the public drift path plus two matched decode probes, and inspect host dispatch time if the end-to-end result is noisy.
- **Stop rule:** stop on any debug assertion, token mismatch, crash under an alternate valid cache state, or decode improvement below 0.15% in both pairs.
- **Why current evidence is non-dispositive:** available evidence changes GPU scheduling, math, or data layout; none isolates release-mode Swift validation overhead while holding the kernels byte-for-byte fixed.

## Additional tiny scored-path seams

### A. Encode the exact fixed fused-attention scale bits

The reached fused attention shapes use a fixed scale. Replacing repeated host-side scale derivation/conversion with the identical precomputed bit pattern could remove small dispatch work while preserving kernel arithmetic exactly. First prove bit identity for every reached path; stop on any mismatch or absent end-to-end signal.

### B. Short-circuit one-token mask construction

The one-token decode path may build mask/view objects whose result is structurally known from cache position and attention mode. Prove the mask is identical across full/sliding boundaries, then bypass only the redundant construction. Preserve cache limits and all multi-token behavior; stop on any boundary mismatch.

### C. Skip the known-identity first full-cache contiguization

When the initial full-attention cache storage is already contiguous in the required order, a first-use contiguization may be an identity. Instrument shape/stride identity before changing control flow, preserve later wrapped/grown cases, and stop unless the identity is proven on the scored path.

These three seams are single-file or very small, arithmetic-preserving candidates. Test them separately after PR #53, strongest evidence first. Dynamic full-attention carrier reuse remains plausible but should wait for more byte headroom because its state/invalidation complexity is disproportionate to the current margin.

## Wait for projected 19,353-byte post-cleanup margin

### 3. Native output-major routed-down layout for multi-row prefill

**Hypothesis:** the gathered routed-down projection is limited by strided packed-weight access in multi-row prefill; storing its quantized weights natively in the output-major tile order consumed by the ranked architecture should improve coalescing without changing selected routes or arithmetic.

- **Mechanism:** transform routed-down weights and scale/bias metadata offline into the consumer's output-major tile order, then dispatch a matching gathered quantized kernel. Preserve each output's current accumulation order; do not combine this with new geometry.
- **Likely submitted paths:** `Sources/MLXFastTransform/Transform.swift`; `Sources/MLXFastModel/LagunaRuntimeModel.swift`; `Vendor/mlx-swift-lm/Libraries/MLXLMCommon/SwitchLayers.swift`; `Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/quantized.cpp`; both `kernels/quantized.{h,metal}` and `kernels/quantized_nax.{h,metal}`; and their `mlx-generated/quantized.cpp` and `mlx-generated/quantized_nax.cpp` twins.
- **Reachability:** the scored sorted sparse prefill path is `LagunaRuntimeModel.swift:9591-9668`, with the separate gathered down projection at `:9658-9659`; its generic gathered quantized dispatch is in `SwitchLayers.swift:476-522,615-628`. The 512-token prefill reaches this path; steady one-token fused-down decode is explicitly outside the experiment.
- **Byte risk:** high, estimated +8 to +18 KiB if the old layout path is replaced rather than duplicated. Proceed only after cleanup and require static-budget validation before building.
- **Correctness risk:** high: expert/row mapping, packed nibble order, scale/bias grouping, and architecture-specific kernel twins must agree. Any changed reduction order can move greedy argmax.
- **Cheapest decisive test:** first round-trip a small transformed tensor through reference dequantization, then compare one gathered-down layer exactly over adversarial row/expert assignments; only then run upstream equivalence and a 512-token prefill pair.
- **Stop rule:** stop on any dequantized-value mismatch, token drift, growth above the post-cleanup margin, decode speedup below 0.995, or prefill improvement below 1.0% in two matched pairs.
- **Why current evidence is non-dispositive:** prior consumer experiments changed row geometry or scheduling while holding the packed weight layout fixed. This isolates the producer/layout variable and targets multi-row prefill rather than the rejected decode geometries.

### 4. Split each fused GQA head-pair into independent 512-thread groups

- **Mechanism:** replace each 1,024-thread/two-query-head group with two 512-thread/one-head groups. Keep 16 SIMD groups per head, the same key traversal, and the same per-head reduction tree; only scheduling granularity changes.
- **Likely submitted path:** `Sources/MLXFastModel/LagunaRuntimeModel.swift`, where both JIT Metal sources and launch geometry live.
- **Reachability:** pair ownership is explicit at `:1350-1353` and `:1819-1823`; scored launches use `(heads / 2) * 1024` with 1,024-thread groups at `:1742-1744` and `:2254-2255`.
- **Budget/risk:** retain both variants behind an architecture selector during research, estimated +3 to +7 KiB. Correctness risk is medium and hardware-portability risk is high.
- **Decisive test and stop:** exact helper comparison at ring wrap and several full-cache lengths, followed by matched same-host decode and authoritative hardware confirmation. Stop on any mismatch or less than 0.5% decode gain.
- **Freshness:** negative fused-down geometry says nothing about attention occupancy; the proposed split preserves each head's reduction tree instead of widening an output tile.

### 5. Index-only sorted sparse prefill: eliminate activation reorder and output scatter

- **Mechanism:** keep the existing route sort, but pass source-row and destination-row indices into grouped quantized kernels so they gather original activations and write directly to original token/slot positions. Do not materialize a reordered activation tensor or a later scatter tensor.
- **Likely submitted paths:** `Vendor/mlx-swift-lm/Libraries/MLXLMCommon/SwitchLayers.swift`, quantized Metal dispatch/kernel files and generated twins, plus `Sources/MLXFastModel/LagunaRuntimeModel.swift` only if metadata plumbing is required.
- **Reachability:** sort/reorder/scatter occurs in `SwitchLayers.swift:207-231,315-371`; the scored 512-row sparse path reaches it through `LagunaRuntimeModel.swift:9591-9668`.
- **Budget/risk:** estimated +10 to +18 KiB; high row/gate association risk, but no intended arithmetic-order change.
- **Decisive test and stop:** property-check randomized duplicate routes and empty/imbalanced groups against the current sorted path, then upstream equivalence and paired prefill. Stop on any mapping drift or less than 0.7% prefill gain.
- **Freshness:** exact route selection evidence addresses which routes survive, not the downstream materialized permutation; direct one-row expert-offset arithmetic is a different decode mechanism.

### 6. Empty-cache prefill write-only KV update with direct SDPA operands

- **Mechanism:** when all supplied prefill tokens start from an empty cache and fit the cache contract, write rotated K/V into resident storage without constructing returned concat/slice views, while SDPA consumes the already-available rotated K/V tensors directly. The first decode token must observe identical resident rows and offsets.
- **Likely submitted paths:** `Sources/MLXFastModel/LagunaRuntimeModel.swift`, `Vendor/mlx-swift-lm/Libraries/MLXLMCommon/KVCache.swift`, and `Vendor/mlx-swift-lm/Libraries/MLXLMCommon/AttentionUtils.swift`.
- **Reachability:** prefill cache update and SDPA meet at `LagunaRuntimeModel.swift:5769-5826`; rotating-cache concat/view work is in `KVCache.swift:569-590,654-662`.
- **Budget/risk:** estimated +2 to +5 KiB, so wait for cleanup. Correctness risk is medium around offsets, masks, sliding truncation, and the prefill-to-decode handoff.
- **Decisive test and stop:** compare full and sliding cache contents after a 512-token prefill and require the first continuation token to match exactly before timing. Stop on any cache/token drift or less than 0.3% prefill gain.
- **Freshness:** existing steady-state decode cache work does not test the empty-cache multi-row return-view boundary.

## Recommended order

Run idea 0 first; it is now assigned as PR #53 because it is reachable, deletion-oriented, math-invariant, and lower risk than the other seams. Next prioritize exact fixed-scale bits, the one-token mask short-circuit, first-cache contiguity identity, and release-check compilation as separate arms. Defer dynamic parameter-carrier reuse until cleanup creates safer byte headroom. After cleanup, test native output-major routed-down layout before the broader kernel changes because it has the clearest untested producer/layout contrast and the largest plausible prefill bandwidth signal. Keep every experiment isolated and revalidate both score floors.

These inference experiments emit no W&B run IDs, so no direct W&B run URLs exist.

_This research synthesis was generated by an AI agent (OpenHands) on behalf of the research team._
