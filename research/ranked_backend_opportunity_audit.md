# Ranked backend opportunity audit

## Verdict

**NO-GO.** At audit input `8966ca398ca32801c3c032382e264e885eba36f8`, no unowned, non-exhausted mechanism on the ranked path has both exact M5 ownership and a conservative static floor of at least **18 us/token decode** or **2.33 ms per 512-token prefill** within the **8 KiB candidate-growth** envelope. No successor experiment is proposed.

The machine-readable census is [`ranked_backend_opportunity_atlas.json`](ranked_backend_opportunity_atlas.json) (17 families; SHA-256 `204879be05a5bce3edb12293a99af3847f7bf5284fc539d6d43c6e02e3ba08a7`). This PR changes no production or submission-surface file.

## Scope and method

- Assignment base: `1237c647f7229ccd997d43f7005d485ea9f3ac90`.
- Audited tree: `8966ca398ca32801c3c032382e264e885eba36f8`.
- The advisor confirmed production source remained unchanged through research-state commit `41d686f15eafda68d9f77905997dab6d78dfdcda`; the audit therefore continued without rebasing.
- History was limited to commits and research records reachable from the isolated assignment checkout and base. Launch isolation prohibited consulting unrelated refs, so this report does not claim a `git log --all` census.
- Active optimization work was excluded rather than duplicated: #645, #646, and #650. PR #640 is incorporated as a terminal below-Amdahl result; #653 is a research-only M4-to-M5 transfer-calibration sibling, not an optimization mechanism.
- Assignment facts were applied directly: #647 showed that the M4 CLI lacks discriminative resource counters; #649 closed exact routed-down epilogue ownership.
- Static source analysis counted logical calls and exact parameter-bank bytes where ownership is explicit. It does **not** invent physical unique-DRAM bytes, command-buffer counts, encoder counts, or fence durations that MLX realizes dynamically.
- No benchmark, inference, correctness run, official submission, or W&B run was launched; this was intentionally research-only.

## Frozen scored census

The model has hidden size 2048 and 40 layers: one dense MLP layer, 39 sparse layers, ten full-attention layers, and thirty sliding-attention layers. Full attention has 48 Q heads, sliding attention 64 Q heads, both have eight KV heads of dimension 128, and the sliding window is 512. Sparse layers route top-8 of 256 experts, each with intermediate size 512 (`LagunaConfig.swift:14-34,490-505`).

The frozen window is one 512-token prefill plus a decode measurement charged for one 512-token seed and 128 one-token calls (`Constants.swift:94-130`). Therefore:

| Logical work | Prefill | Decode seed | 128 decode calls | Charged decode total |
|---|---:|---:|---:|---:|
| model forwards | 1 | 1 | 128 | 129 |
| layer calls | 40 | 40 | 5,120 | 5,160 |
| full-attention calls | 10 | 10 | 1,280 | 1,290 |
| sliding-attention calls | 30 | 30 | 3,840 | 3,870 |
| sparse-layer calls | 39 | 39 | 4,992 | 5,031 |
| dense-layer calls | 1 | 1 | 128 | 129 |

The runtime builds one retained mask/RoPE family per attention type, specializes the final prefill layer to keep all KV rows but only the last row of downstream work, and slices to the final row before final norm/head (`LagunaRuntimeModel.swift:11438-11665`).

## Platform and ownership matrix

M4 Pro reports Apple GPU generation 16. Quantized/SDPA selectors choose NAX only on later generations (runtime `LagunaRuntimeModel.swift:242-265`; backend `device.cpp:913-932`; NAX QMM/gather selectors `quantized.cpp:718-750,955-995,1990-2024`; SDPA selector `scaled_dot_product_attention.cpp:166-200`). Thus an M4 timing can support a common-source mechanism, but cannot validate an `_nax`-only M5 change.

| Family | Ranked reach and scale | Platform class | History / owner | Screen |
|---|---|---|---|---|
| host graph, enqueue, sync | 129 forwards; lazy 40-layer graph | common host | descriptor hoists exhausted; #650 measures remainder | reject: no exact 18 us/token floor |
| embedding, RoPE, masks | 129 embedding calls; two retained families | common | atlases and decode-mask elision promoted | exhausted |
| input RMS + QKV + gate | 5,160 layer calls; QKV banks 32-40 MiB/layer | common native-affine/custom | retention, width, staging, binding families tested | exhausted |
| QK norm + RoPE | 1,290 full + 3,870 sliding calls | common JIT | retained-producer and packet variants tested | exhausted |
| KV cache | 5,160 updates; 160 KiB written per supplied token over all layers | common | rotating/full cache/materializer work tested | exhausted |
| sliding attention | 3,870 charged calls; at least 8.05 GB logical KV reads over decode steps | common JIT | vector/packet/cap/geometry families tested | exhausted |
| full attention | 1,290 charged calls; at least 3.02 GB logical KV reads | regular M4 / NAX M5 counterpart | regular path tested; NAX-only work lacks M4 reach | defer M5-only |
| gated O projection | 5,160 calls; O banks 24-32 MiB/layer | common native-affine/custom | source width, staging, load sharing tested | exhausted |
| residual + RMS + router | 5,031 sparse calls; 39 MiB router banks/step | common JIT | fusion, packed bank, bias-cache work tested | exhausted |
| router top-8 | 5,031 calls; grid/TG 256 for decode | common JIT | active64/tournament promoted; score variants tested | exhausted |
| routed gate/up + SwiGLU | 5,031 calls; 9 MiB selected expert parameters/layer | regular M4 / NAX M5 counterpart | scale, split-K, width, sharing tested; #646 excluded | exhausted/active |
| shared gate/up + SwiGLU | 5,031 calls; 1.125 MiB bank/layer | common plus backend QMM | retained fusion promoted; #640 exact dual-backend epilogue saved 356.8-368.1 us vs 569.3 us gate | closed below whole-prefill Amdahl |
| routed down/reduce/tail | 5,031 calls; 4.5 MiB selected parameters/layer | regular M4 / NAX M5 counterpart | #649 owns exact seam; tail/split-K/scale tested | below floor and owned |
| shared down + residual | 5,031 calls; 576 KiB bank/layer | common | routed/shared co-dispatch already present | exhausted |
| dense layer-0 MLP | 129 calls; 96 MiB BF16 parameters | common | fused gate/up and down residual; dense-R8 tested | exhausted |
| terminal prefill row | one terminal layer per 512-row forward | common | all-KV/last-row specialization promoted | exhausted |
| final norm/head/argmax | 129 calls; 392 MiB BF16 head bank | common | final-row slicing/pruner promoted; repartition regressed | exhausted |

The atlas records wrapper names, shapes, call counts, guarded launch behavior, available threadgroup geometry, logical bytes, unique-byte unknowns, ABI/generated-source ownership, citations, and classifications for each row. Where a custom dispatch is one-per-layer, its call count is the corresponding table count. Generic MLX matmul/SDPA launch and synchronization counts remain `null` or qualified because static Swift/C++ source cannot recover the dynamically realized command graph, and #647 established that the available M4 counters cannot discriminate it.

## Amdahl and novelty gates

The reference frontier is 13.49788 ms/token decode and 579.29728 ms per 512-token prefill. The assignment floors therefore require removing at least 0.133354% of decode or 0.402212% of prefill, with exact ownership rather than an aggregate kernel guess.

1. **Shared-prefill SwiGLU:** PR #640 tested the exact regular-M4 and ranked-NAX producer epilogue, removing 38 activation launches and 79,691,776 logical bytes in 8,077 bytes of growth. The bit-exact ABBA/BAAB savings were 368.125/356.8225 us against a fresh 569.285 us whole-prefill gate, projecting only 1.000636216x/1.000581458x. It is closed below the 1.001x whole-prefill Amdahl floor and should not be retried standalone.
2. **Routed-down prefill epilogue:** #649's traffic-only upper bound is 2.218 ms/pass, already below the 2.33 ms admission floor before accounting for incomplete physical removal. It is also explicitly owned/closed.
3. **Host bridge/enqueue/synchronization:** source exposes configurable `asyncEval` sites but no attributable removable duration. #647 removes counter attribution and #650 owns measurement. There is no honest static 18 us/token claim.
4. **Regular quantized QMM/gather:** the remaining regular-path seams overlap prior scale packing, source-width, cross-lane sharing, split-K, tail fusion, and binding work, or active #646.
5. **M5 NAX QMM/gather/SDPA:** M4 generation 16 does not execute these variants. Without an M5-attributed removable cost, assigning a ranked candidate would be speculation rather than a feasibility result.
6. **Attention, router, dense MLP, terminal row, and LM head:** current source already contains the promoted fusion/specialization, while reachable history records neutral, regressed, below-floor, or saturated follow-ups.

A production candidate would also face only 15,879 bytes global submission headroom (12,598 bytes in the runtime Swift file at audit time). This research-only result consumes zero submission bytes, but the required candidate budget of at most 8 KiB does not rescue any mechanism rejected above.

## Reproduction and verification

```bash
# Static census inputs
git rev-parse HEAD
grep -nE 'numHiddenLayers|numAttentionHeads|numKeyValueHeads|slidingWindow|numExperts|numExpertsPerToken' Sources/MLXFastModel/LagunaConfig.swift
grep -nE 'prefillLength|decodeSteps|decodeSeedLength' Sources/MLXFastCore/Constants.swift
grep -nER 'supportsNAX|generation|_nax' Sources/MLXFastModel/LagunaRuntimeModel.swift Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal

# Deliverable and scope checks
python3 -m json.tool research/ranked_backend_opportunity_atlas.json >/dev/null
shasum -a 256 research/ranked_backend_opportunity_atlas.json
wc -c research/ranked_backend_opportunity_audit.md research/ranked_backend_opportunity_atlas.json
git diff --exit-code 1237c647f7229ccd997d43f7005d485ea9f3ac90 -- Sources Vendor
senpai/check-editable-budget.sh 1237c647f7229ccd997d43f7005d485ea9f3ac90
```

Expected scope result: only this report and its JSON atlas differ; `Sources/` and `Vendor/` are byte-identical to the assignment base. Runtime, peak memory, W&B URLs/run IDs, correctness metrics, and paired timing metrics are N/A because no executable candidate or run was permitted.

## Conclusion

There is no threshold-clearing, correctly owned successor to hand to another student from this audit. Resume backend assignment only after one of these facts changes: a currently active owner releases a distinct seam with at least 18 us/token decode or 2.33 ms/prefill attributable work, an M5 run provides kernel-attributed evidence for an NAX-only mechanism, or a new common-source mechanism demonstrates a conservative static floor above the assignment threshold.

SENPAI-RESULT: {"terminal":true,"status":"complete","pending_arms":false,"wandb_run_ids":[],"primary_metric":{"name":"same_host_paired_estimate","available":false,"value":null},"test_metric":{"name":"passed_correctness","available":false,"value":null}}
