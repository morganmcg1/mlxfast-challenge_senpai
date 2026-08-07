# MLXFast Laguna XS 2.1 Research Ideas — 2026-08-07 12:41 UTC

Status: advisor proposal only. No runtime code, benchmark, submission, commit, or GitHub mutation was performed.

## Evidence and live-state reconciliation

- The score contract is `decode_speedup^0.75 * prefill_speedup^0.25`, with both paired speedups at least `0.95` (`senpai/program.md:12-20`, `benchmark.json:115-119`). The ranked M5 Max result is authoritative; M4 data is only directional, and M4 does not exercise M5 `_nax` prefill kernels (`senpai/program.md:43-50`).
- The scored forward path is `Sources/MLXFastModel/LagunaRuntimeModel.swift`; the exact submission surface and size limits come from `benchmark.json` (`senpai/program.md:111-151`, `benchmark.json:8-105`). Attention re-quantization is limited to group-32 affine INT8 Q/K/V/O and per-head `g_proj`; none of the proposals below introduces another numeric representation (`TASK.md:78-97`).
- The user's 12:41 snapshot named advisor/base `fcc65b88d5285f0ad74050d444d11e05a82bdc5c`. The newer checked-in live state at 12:58 supersedes it: assignment base `cbe09a9b4f2cb70df3d78a906fd66fb516bde3c6`, scored frontier `6d32b6c7581b5e1dadaa0df3b391809bcf17ac76`, official score `2.59787481790585`, and 24,168 bytes of global editable headroom (`research/CURRENT_RESEARCH_STATE.md:3-9`). The docs-only base move does not change the scored mechanism.
- The requested `list-experiments` skill was invoked but is unavailable in this agent's loaded skill catalog. To avoid inventing history, I reviewed the durable full PR exports available in advisor state (`pull-requests-65d85ceb2cef4008d8b0.md`, `pull-requests-8fca0e2daba8f299cc1d.md`, and `pull-requests-e856a886fc72da114fd8.md`) and reconciled them against the newer live state. This is strong local evidence but not a claim of a fresh GitHub fetch.
- Current work is no longer the 12:41 set: PR #282 tests output-major routed-down prefill, #252 measures cold/warm duplicate slope, #275 tests sliding K/V lookahead, and cedar-frieren is already occupied by PR #279's sliding write-slot-owner specialization (`research/CURRENT_RESEARCH_STATE.md:11-18`). PR #246 has closed unmerged as a size dead end; PR #266 remains a negative result (`research/CURRENT_RESEARCH_STATE.md:19-24`). Therefore the selected assignment below is **queued for cedar-frieren only after PR #279 terminates**, not dispatched now.
- W&B is normally not used for this systems-inference programme. The selected assignment's required evidence is matched timing, reachability, compiler-resource, and correctness artifacts, so no W&B run is expected.

## What the history says

The useful positive pattern is exact-shape work removal with a short, provable data path: KV slack removal, terminal-prefill Q/K normalization plus RoPE, direct-index routed gate/up, fused routed/shared down, BF16 qdot compaction, and router-key suppression. The repeated negative pattern is geometry or scheduling churn whose local effect is smaller than order/thermal noise. In particular:

- Do not revisit PR #39's one-SIMDgroup OProj geometry; it regressed decode.
- Do not repeat PR #42's producer-side gate activation movement; it was exact but weighted-negative.
- Do not repeat PR #246's padding/size mechanism or PR #266's threadgroup geometry; do not duplicate active PR #282's output-major routed-down layout, PR #252's measurement study, or PR #279's sliding-attention ownership work; and do not revive closed PR #275's prefetch mechanism.
- The best next bet should keep output rows, weight order, reduction order, precision boundaries, and dispatch count fixed while eliminating duplicated work inside an already-hot decode kernel.

## Ranked fresh single-mechanism ideas

Ratings are relative: impact estimates are hypotheses, not measured claims. “M5 relevance” distinguishes architecture-generic JIT kernels from M5-only `_nax` paths.

| Rank | Single mechanism | Weighted-impact potential | Attribution | Correctness risk | M5 relevance | Complexity |
|---:|---|---|---|---|---|---|
| **1** | **Cooperatively stage each already-preactivated 512-element BF16 OProj input tile once per threadgroup, then let both existing SIMDgroups consume it.** | Medium decode; plausibly ~0.1–0.4% weighted if duplicate activation traffic is material | Very high: same grid, rows, weights, reductions, and dispatches | Low–medium: added barriers/TG memory, but identical BF16 multiply boundary | High and architecture-generic; must still confirm on M5 | Low–medium; one submitted file |
| **2** | Fuse the prefill SDPA output transpose and already-activated per-head BF16 gate product into one exact-shape materializer. | Low–medium prefill; ~0.03–0.12% weighted | High if tracing proves two current materializations/dispatches | Medium: preserve transpose indexing and BF16 rounding exactly | High; generic path, M5 authoritative | Medium; stop if MLX already fuses them |
| **3** | In M5 `_nax` prefill SDPA, packet adjacent query heads sharing one KV head so a threadgroup reuses the same K/V tile while retaining each query head's original softmax order. | Medium–high prefill; ~0.05–0.25% weighted | High in isolated H48/H64 kernel timing | High: occupancy, masking, and near-tie logits | **M5-only**; M4 cannot validate reachability or sign | High; `.metal` plus generated twin |
| **4** | Add a gate-aware, head-major prefill OProj consumer that reads SDPA's native `[H,L,D]` result directly, avoiding a transposed intermediate. | Medium prefill | Medium: replaces a layout boundary, so inspect dispatch trace carefully | Medium–high: larger exact-shape kernel and arithmetic-order proof | High; M5 full benchmark required | High; alternative to rank 2, never combine initially |
| **5** | Specialize M5 `_nax` prefill SDPA all-valid causal tiles so only diagonal/partial tiles execute per-element mask predicates. | Low–medium prefill | High after tile-class counters and isolated timing | Low–medium if arithmetic and visitation order are unchanged | **M5-only** | Medium; stop if compiler/source already performs this elision |
| **6** | Fuse full-prefill Q/K normalization and partial-rotary YaRN RoPE into the retained fused-QKV projection epilogue, extending the terminal-prefill win without changing the projection. | Medium prefill | Medium–high with per-stage counters | High: exact normalization/RoPE rounding and near-tie tokens | High; M5 correctness authoritative | High; likely multiple editable kernel sources |
| **7** | Reindex only the exact-shape M5 `_nax` fused-QKV prefill threadgroup grid to improve output-tile locality while leaving tile dimensions and arithmetic untouched. | Low–medium prefill | High, but effect may be below MDE | Low numerically; medium performance portability | **M5-only** | Medium; test one predeclared swizzle, not a broad sweep |

Ranks 2 and 4 are mutually exclusive explanations for the same layout boundary: first test whether a small exact materializer fusion wins; only consider a layout-native OProj consumer if that result proves the boundary is material but the intermediate remains costly. Ranks 3, 5, and 7 require actual M5 execution evidence because an M4 Pro does not select `_nax`.

## Selected queued assignment for cedar-frieren

### Title

Decode-only preactivated NVFP4 OProj cooperative 512-BF16 input-tile staging

### Dispatch condition

Do **not** create or route this assignment while cedar-frieren owns PR #279. After #279 terminates, refresh live PR state, use the then-current exact maintained-base SHA as `BASE_SHA`, and recheck that no newly active PR owns preactivated NVFP4 OProj input staging. If #279 merges, rebase first; its sliding-attention kernel changes are logically separate but the exact comparison base must be current.

### Hypothesis

For the serial `B=1, L=1` activated NVFP4 OProj path, each 64-thread threadgroup contains two SIMDgroups. In every 512-column K block, both SIMDgroups currently load the same attention values and per-head activated gate values and independently compute the same exact `bfloat(float(x) * g)` values (`Sources/MLXFastModel/LagunaRuntimeModel.swift:4102-4112,4114-4147`). Staging those 512 BF16 products once in 1,024 bytes of threadgroup memory should halve this duplicated activation/gate read-and-product work while preserving output-row ownership, weight/code/scale reads, accumulation, reductions, output BF16 rounding, and dispatch geometry.

The benefit is plausible because the operation repeats across all reached NVFP4 OProj layers and 128 scored decode steps, which receive 75% score weight. The risk is that two synchronization points per 512-column block, threadgroup-memory occupancy, or compiler register changes outweigh the saved traffic. This is exactly what the proposed resource and isolated-kernel gates distinguish.

### Submitted paths

Only:

```text
Sources/MLXFastModel/LagunaRuntimeModel.swift
```

No transform, metadata, checkpoint, vendor, package, test-harness, or generated-weight change. A temporary uncommitted local oracle/probe may be used and then deleted; it is not a submitted path.

Before implementation, run against the then-current `BASE_SHA`:

```bash
senpai/validate-assignment-scope.sh "$BASE_SHA" Sources/MLXFastModel/LagunaRuntimeModel.swift
senpai/check-editable-budget.sh "$BASE_SHA"
```

Cap net growth in the submitted file at **12,288 bytes**. With the currently reported 24,168-byte global headroom, this preserves at least 11,880 bytes for integration variance. Re-run both checks after the implementation; do not rely on the present headroom if the base changes.

### Scored-path reachability proof

1. The decode gate projection can produce already-softplus-activated BF16 gate values through `lagunaGateSoftplus` (`LagunaRuntimeModel.swift:4212-4290`; caller around `5504-5515`).
2. The activated kernel registry instantiates both sliding H48 and full-attention H64 variants with `preActivatedGate: true` (`LagunaRuntimeModel.swift:4292-4305`).
3. `lagunaGatedAffineOProjNVFP4` selects that registry only when `gateIsActivated` is true (`LagunaRuntimeModel.swift:4310-4320`) and guards exact serial shapes `[1,1,heads*128]` (`LagunaRuntimeModel.swift:4322-4343`).
4. The scored forward caller reaches this branch for native NVFP4 OProj weights and activated gates (`LagunaRuntimeModel.swift:5883-5897`), inside the `B=1, L=1` serial-only OProj guard (`LagunaRuntimeModel.swift:5840-5846`).
5. Inside the generated source, `block_size = 16 * 32 = 512` and `num_simdgroups = 2`; both SIMDgroups independently execute the same input/gate product for each K block (`LagunaRuntimeModel.swift:4114-4147`).

Required trace evidence before timing: both H48 and H64 activated variants must fire during scored one-token decode; the candidate must have zero hits in prefill, raw-gate NVFP4, group-32 INT8 OProj, BF16 OProj, and generic fallback paths.

### One allowed mechanism

Change only the `preActivatedGate == true` generated Metal source so one producer SIMDgroup/thread subset writes the exact existing BF16 products for the current 512-column block to a 512-element threadgroup array; after a threadgroup barrier, both existing SIMDgroups load their 16-value lane slice and execute the unchanged weight loop. Add the necessary reuse/overwrite barrier between K blocks. Version the activated kernel name if required to avoid stale JIT cache reuse.

### Hard boundaries

- No change to output-row ownership, grid, 64-thread threadgroup, two-SIMDgroup geometry, four results per SIMDgroup, K-block order, weight/code/scale layout, scale decode, accumulation, `simd_sum`, or final BF16 store.
- Preserve the exact numerical boundary `bfloat(float(attention) * float(activatedGate))` before conversion back to float for qdot. Do not move softplus, fuse the gate projection, alter activation precision, reassociate the contraction, or use fast math.
- Do not modify `preActivatedGate == false`, group-32 affine INT8 OProj, BF16 OProj, prefill, last-row, or fallback branches.
- No new weight format, quantization, layer-coverage expansion, metadata, cache, memoization, future-token work, deferred KV/logit state, or benchmark specialization.
- No double buffering, async copy, alternate threadgroup geometry, scale-layout change, or second optimization in this PR. If simple staging is negative, report and close rather than adding another mechanism.
- Remove trace-only code and temporary local oracle files before the terminal result.

### Evidence sequence and stopping rules

1. **Base, scope, budget, and overlap.** Record exact `BASE_SHA`, scored frontier SHA, file sizes, active PR set, scope-check output, and budget output. Stop on overlap or projected growth above 12,288 bytes.
2. **Static resource preflight.** For both H48 and H64, compare baseline/candidate Metal compiler or capture evidence: threadgroup memory should rise by exactly 1,024 bytes, with no spill and no occupancy-class loss. Stop if either variant fails compilation, spills, loses occupancy, or uses an unexplained amount of threadgroup memory.
3. **Direct deterministic kernel oracle.** Compare old and staged activated kernels for both H48 and H64 over seeded random BF16 attention/gate inputs plus signed zero, BF16 subnormal, small/large finite, and mixed-sign attention cases. Use the same resident codes/scales. Require bit-for-bit BF16 output equality. Any bit mismatch stops the experiment.
4. **Reachability trace.** Under the exact scored worker, prove both activated variants are reached only for one-token decode and that excluded branches have zero candidate hits. Stop if the changed kernel is unreachable or contaminates prefill/fallback paths.
5. **Isolated kernel timing.** On the same quiet host and architecture, use fixed warm-up and interleaved samples in **A/B then B/A** order for H48 and H64 separately. Report medians, dispersion, and resource counters. Proceed only if the candidate is faster in both orderings for both variants and each variant clears the larger of 1.5% or twice the paired-noise/MDE estimate. One predeclared repeat is allowed for an order conflict; a second conflict or sign reversal stops the experiment.
6. **Matched full-model screen.** Run the official local-iterate path, not a bare release build, as two matched pairs: baseline/candidate followed by candidate/baseline, respecting the thermal gate and one-model-process rule:

   ```bash
   ./benchmark.sh --local-iterate
   ```

   Retain only if correctness passes, both orderings favor candidate decode, the paired decode point estimate is at least `1.002`, the paired weighted point estimate is at least `1.0015` with a lower confidence bound above `1.0`, and prefill is at least `0.998`. The official contractual floor remains `0.95`; the tighter prefill gate is causal because this mechanism is decode-only. Stop after one controlled repeat if results remain within noise or disagree by order.
7. **Correctness escalation.** Only after a timing-positive screen, run the exact upstream-equivalence wrapper and the public drift/golden gates:

   ```bash
   research/run_upstream_equivalence.sh
   ```

   Require every checked greedy token and equivalence case to pass. On non-M5 near-tie drift, compare the unchanged base under the documented policy; never treat a local override as an official pass.
8. **Promotion preflight.** Only a reproducible retained winner proceeds to:

   ```bash
   ./benchmark.sh --local-submit
   ```

   Re-run scope/budget checks and inspect the final submitted diff. Official M5 correctness and paired timing decide promotion. No W&B run is expected; preserve commands, architecture, kernel reachability, compiler resources, raw paired timing, and correctness artifacts in the terminal structured result/PR evidence.

### Success interpretation

- A clean isolated and end-to-end win supports the hypothesis that duplicated gated-input preparation, not OProj output geometry, is a remaining decode bottleneck. Promote only this staging mechanism.
- An isolated win with no end-to-end effect bounds the OProj share below the programme's practical MDE; close without expanding scope.
- A barrier/occupancy regression falsifies this staging design but does not justify reviving one-SIMDgroup geometry or producer-side gate movement.
- Bit drift means the implementation moved the BF16 boundary or changed source indexing; do not time or salvage it with tolerances.

## Recommended next action

Keep PR #279 running. When cedar-frieren becomes idle, refresh live state and, if no OProj-staging overlap has appeared, route the single-mechanism assignment above from the then-current maintained base. The next research fallback should be rank 2's prefill transpose-plus-gate materializer, not another sliding-attention decode variant.

_This research proposal was generated by OpenHands on behalf of the research team._
