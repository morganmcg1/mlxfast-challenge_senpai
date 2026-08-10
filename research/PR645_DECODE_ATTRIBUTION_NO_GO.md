# PR #645 decode critical-path attribution: NO-GO

## Decision

**Terminal result: inconclusive attribution, conservative NO-GO for a successor experiment.**

The unchanged production route passes the local 130-step correctness gate and has a source/config-derived architectural census matching the assignment's expected counts. However, the first Metal System Trace capture ended before the MLXFast worker entered scored decode and contained no MLXFast process, command buffer, or encoder. The assignment required an immediate stop for stale route selection. Consequently, no valid GPU inclusive/exclusive duration, host enqueue time, p50/p95 distribution, family share, ABBA/BAAB perturbation calibration, or ±5 us/token bound exists. Without bounded family timing, no conservative successor with at least 18 us/token recoverable decode time is eligible.

No production or vendor source was changed, no candidate optimization was timed, and no official submission was made.

## Scope and environment

- Required base: `d50e6e4d900c92b06803c936064a4f47c79401d0`
- Measurement commit: `524df488785332ddcf02c2fd44ef16f085ad4b40`
- Branch: `cedar-thorfinn/decode-critical-path-attribution`
- Host: Mac mini `Mac16,11`, Apple M4 Pro, 14-core CPU, 20-core GPU, 48 GB unified memory
- Xcode: 26.6 (`17F113`); Instruments/xctrace: 16.0
- Apple GPU generation: 16; this host does not establish M5 `_nax` behavior
- W&B: N/A. This assignment is local systems measurement and generated no W&B run.

Before this report was added:

```text
full diff versus required base: 0 files
Sources/ + Vendor/ diff versus required base: 0 files
LagunaRuntimeModel.swift SHA-256:
  ed084a8aa840f651449b8c9f344c2cd40786de9eccee2c291bde419716022ccb
editable surface: 2,984,121 / 3,000,000 bytes
editable headroom: 15,879 bytes
editable growth: 0 bytes
```

## Clean baseline

Supervised job `90921b79-a2a7-4c08-a28f-5bdd81d95e38` ran:

```bash
./benchmark.sh --local-iterate
```

The unchanged route passed correctness (`checked_steps=130`, `max_abs_diff=0`) in 184.138 s with 21 GB peak RAM.

| Metric | Result |
|---|---:|
| Decode | 0.0129538343046875 s/token = **12,953.834 us/token** |
| M4 prefill diagnostic | 0.001111484375 s/token |
| Pinned calibration decode | 0.01385621216015625 s/token |
| Score JSON | `/tmp/pr645-baseline-a1.json` |
| Score SHA-256 | `be435a861e3d0bddc4c55592a229a61afa22231f21ba722036a3bb33b44ed936` |

The M4 prefill value is diagnostic only and is not evidence for the ranked M5 prefill route.

## Source/config-derived architectural census

This is an architectural census, **not an observed Metal route census**. `weights/config.json` and the fixed runtime invariants describe 40 layers: 10 full-attention layers, 30 sliding-attention layers, and sparse MoE on layers 1-39. Across 128 one-token decode requests:

| Structural event | Formula | Count |
|---|---:|---:|
| Sliding fused-attention opportunity | 30 × 128 | **3,840** |
| Full fused-attention after first-step growth fallback | 10 × 127 | **1,270** |
| Gated OProj | 40 × 128 | **5,120** |
| Sparse MoE chain | 39 × 128 | **4,992** |
| Terminal LM head | 1 × 128 | **128** |

Relevant fixed model checks begin at `Sources/MLXFastModel/LagunaConfig.swift:20` and validate the 40-layer schedules around lines 491-504. The scored decode path is in `Sources/MLXFastModel/LagunaRuntimeModel.swift`, including native affine OProj preparation/use around lines 5497-5537 and 5846-5883, routed gate/up preparation/use around lines 10491-10865, and decode scheduling around lines 11297-11677.

The local census control produced:

```json
{"counts":{"full_fused_attention":1270,"gated_oproj":5120,"sliding_fused_attention":3840,"sparse_moe_chain":4992,"terminal_lm_head":128},"layer_count":40,"matched":true,"source":"weights/config.json","steps":128}
```

Positive corruption control deliberately changed `sliding_fused_attention` to 3,839; the parser reported `matched=false` and exited 3. The uncorrupted control exited 0.

```text
/tmp/pr645-census-control.py       7a15bbcb4c8eabc4e7afe9ea6e8a4601e8da35fbd2829d59abf9f602a2bddb09
/tmp/pr645-census-good.json        633577310387e778ccbdddec406abb6705dcbf13254c2d0e552360728687155b
/tmp/pr645-census-corrupt.json     c9df6fd117294f9717f147614fe8f93b23fc52b8d18cfedc076963e834834a7c
/tmp/pr645-census-status.txt       68e7241881fff5b99b46f434f212572f9a316fba655ffbac91ae87330af1a941
```

Source inspection also identified source-selected kernel candidates such as `laguna_sliding_fused_attn_ring_v1`, `laguna_full_fused_attn_grow_v1`, native affine gated OProj variants, packed routed gate/up, shared rows-1, and fused routed/shared down-residual. Because the trace was stale, these names must not be represented as observed production dispatches.

## Metal trace Gate 0 failure

Supervised job `d202ee28-fc19-428b-a29c-3bea75ef8cdd` ran the unchanged benchmark through Instruments:

```bash
xcrun xctrace record \
  --template "Metal System Trace" \
  --output /tmp/pr645-metal-a1.trace \
  --window 15s --no-prompt --target-stdout - \
  --launch -- /bin/bash ./benchmark.sh --local-iterate
```

The benchmark itself completed successfully in 413.392 s and passed the same 130-step correctness gate. Its decode timing was 0.0130631461640625 s/token. Relative to the clean run, that is +109.312 us/token (+0.844%), but this is **not** a valid instrumentation perturbation estimate: the trace did not overlap scored decode.

The exported TOC proves the stale capture:

- Trace interval: `2026-08-10T13:14:42.145Z` to `2026-08-10T13:15:12.145Z`
- Scored decode occurred roughly 183 s after launch, outside the trace interval
- Launched target: wrapper shell PID 16113
- Processes in the trace: bash, WindowServer, DTServiceHub, kernel, loginwindow, iconservicesagent, and SecurityAgent; no MLXFast worker
- Application command buffers: **0**
- Application encoders: **0**
- `metal-gpu-intervals`: 12,599 rows, all attributable to WindowServer or SecurityAgent

Therefore Gate 0 failed: the trace observed compositor/UI work rather than the benchmark worker. Launching the worker directly would not preserve the trusted JSON-line protocol, token validation, cooling/memory gates, or exact scored route. The assignment's stale-path stop condition prohibited redesigning and rerunning the profiler.

### Trace artifact checksums

```text
/tmp/pr645-metal-a1.trace (tar stream)  ada5813e79a5b87078c4db3f35830c0acee3c10839b9ce3bdabc7b4a63bc3453
/tmp/pr645-metal-a1-score.json          84207f153386785abf65c17be30239b8952678ceb6e67ec671f6291ee6cac05a
/tmp/pr645-metal-a1-toc.xml             fcc0e5ede2a449917d7cf0ddac2d2fdcf2e3b67347eb566c5503f0c315c3e223
/tmp/pr645-metal-a1-gpu.xml             87d3d25f04ca73204a3f0d4b16753831ee31572ff938e4da9f5d530c7fd1ec08
/tmp/pr645-metal-a1-cb.xml              95bb15457bcf7220e135c233f6099dadf010cd4c353ab2a8af3522272a647894
/tmp/pr645-metal-a1-encoders.xml        3e10040cfc10b36fe3581ef906a9c930d5a51837acccf3f0091d59c776cb68f1
```

## Requested family attribution

`N/A` means the trace contained no production worker samples. The baseline total is not assigned to any family.

| Family | Structural count | GPU inclusive/exclusive | Host enqueue / dispatch | p50 / p95 | us/token | Share | Bound |
|---|---:|---:|---:|---:|---:|---:|---:|
| Normalized input + QKV/gate projection enqueue | N/A | N/A | N/A | N/A | N/A | N/A | Unresolved |
| Sliding fused attention | 3,840 source-derived | N/A | N/A | N/A | N/A | N/A | Unresolved |
| Full fused attention | 1,270 source-derived | N/A | N/A | N/A | N/A | N/A | Unresolved |
| Gated OProj | 5,120 source-derived | N/A | N/A | N/A | N/A | N/A | Unresolved |
| Residual/RMS/router | N/A | N/A | N/A | N/A | N/A | N/A | Unresolved |
| Routed gate/up | 4,992 chain opportunities | N/A | N/A | N/A | N/A | N/A | Unresolved |
| Shared gate/up | 4,992 chain opportunities | N/A | N/A | N/A | N/A | N/A | Unresolved |
| Fused routed/shared down + sparse residual | 4,992 chain opportunities | N/A | N/A | N/A | N/A | N/A | Unresolved |
| Terminal norm + LM head/argmax | 128 LM-head opportunities | N/A | N/A | N/A | N/A | N/A | Unresolved |
| Unclassified host/enqueue/sync remainder | N/A | N/A | N/A | N/A | N/A | N/A | Unresolved |

The only valid end-to-end measurement is the unchanged total of 12,953.834 us/token. Treating that total as an unclassified remainder would be misleading; its decomposition uncertainty is much greater than the required ±5 us/token.

No ABBA or reverse BAAB series was run because the mandatory stale-route stop fired on the first capture. The +0.844% whole-run delta cannot certify profiler perturbation despite being numerically below 1%, because profiling had already stopped before decode.

## Correctness and restoration

Setup job `4f51aff5-f7af-4e41-bcdd-ac787452ac00` passed. The clean local benchmark passed all 130 checked steps with exact tokens.

Unchanged-tree upstream equivalence was run both before and after measurement:

- Before: job `2dbe87b6-868e-404b-b7a3-9b2c1fd83be8`
- After: job `5984162e-c4e4-4a48-a05f-88eea29f11f4`
- Command: `research/run_upstream_equivalence.sh`
- Both runs: exit 1 from the unchanged M4 prefill tolerance mismatch
- Prefill: maximum absolute logit error 0.125, mean absolute logit error 0.011933609; runtime/upstream token both 5991
- Decode steps 0-7: maximum and mean absolute error 0; exact token sequence `509, 902, 5991, 509, 902, 5991, 509, 902`
- Wrapper evidence: `EQUIVALENCE_EXACT_STEPS=8`, `EQUIVALENCE_EXIT=1`

This is the same unchanged-base M4 prefill drift on both sides of measurement, not a regression from this assignment. No instrumentation or production change remained to restore.

## Novelty audit and Amdahl gate

The audit excluded active sibling work on codeword loads, down scales, shared prefill epilogues, prefill Q/K vectors, and OProj uint2. Prior work also covers sparse cast/guard hoists, routed/shared co-dispatch, fixed attention scale, launch descriptor hoists, dense-R8, correction-bias caching, router-table recomputation, diagnostic-only hooks, head repartition/four-head packets, retained post-projection Q/K producers, and binding-only changes.

Because no family has a latency estimate bounded to ±5 us/token, an Amdahl upper bound cannot be stated honestly. In particular, no family can be shown to have at least 18 us/token conservatively recoverable after uncertainty. **No successor experiment is proposed.** A future profiling assignment would first need an assignment-approved way to attach Instruments to the trusted child worker while preserving the exact benchmark route, then repeat Gate 0 and calibrated ABBA/BAAB before selecting a mechanism.

## Conclusion

The expected structural census is internally consistent and its corruption control works, but the actual production route was not captured. Under the explicit stop rules, the defensible result is NO-GO rather than speculative family ranking. The measurement establishes no optimization win and leaves the production submission surface identical to the required base.

_This report was prepared by an AI agent (OpenHands) on behalf of the student._
