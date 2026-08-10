# External ranked-mechanism survey — NO-GO

Assignment: `cedar-tanjiro-external-ranked-mechanism-survey-20260810`
Assignment base: `21011663a0ecf8c5288a5092388dc0bc78ef2051`
Machine table: [`external_ranked_mechanism_candidates.json`](external_ranked_mechanism_candidates.json), SHA-256 `0f76d1180c7606a34dff0af498bc0bafc2f951b7ccf0ec77567cccf2c9885cbd`

## Verdict

**NO-GO: nominate no implementation experiment.** Four independent public lineages produced seven plausible Metal/quantized-inference mechanisms. Six are already present, exhausted, not on Cedar's scored hot path, or incompatible with exact checked reductions. The sole novel, exact, scored-reachable mechanism—branch-free lane-major LM-head scale metadata—owns only **8.875 us/token**, 49.3% of the required **18 us/token** decode floor, and its public end-to-end result regressed 0.256%. No candidate clears all novelty, reachability, exactness, M4/M5 relevance, static-ownership, and <=8 KiB scope gates.

This was research only: no production edits, build, benchmark, W&B run, candidate composition, or official submission.

## Decision basis

PR [#652](https://github.com/morganmcg1/mlxfast-challenge_senpai/pull/652) at `1fae5317e0ba348b004d69fb94f1b6c3c7f710c0` is the duplicate baseline. Its 17-family atlas (SHA-256 `204879be05a5bce3edb12293a99af3847f7bf5284fc539d6d43c6e02e3ba08a7`) spans host/enqueue, embedding/RoPE/mask, QKV/gate, QK norm/RoPE, KV update, both attentions, attention output, router, routed/shared gate-up-SwiGLU, routed/shared down tails, dense layer 0, final-row extraction, and final norm/LM head/argmax.

Reference windows were 13.49788 ms/token decode and 579.29728 ms/pass prefill. The assignment floors are 18 us/token (0.1334%) and 2.33 ms/pass (0.4022%). Submitted surface is 2,984,121/3,000,000 bytes, leaving 15,879 bytes globally; this assignment further limits any candidate to 8,192 bytes. Active lanes #645/#646/#650/#651/#654 were treated as excluded, not candidate evidence.

## Public source provenance

| Lineage | Immutable evidence | Date | License / local evidence hash |
|---|---|---:|---|
| Organizer challenge | [PR #1814](https://github.com/Layr-Labs/mlxfast-challenge/pull/1814), candidate `1b21f5f9b394aca727f52510e8fed97da2e62016`, receipt `7df02ad4-a616-484f-ba87-240a5719f074` | 2026-08-10 | MIT; receipt-note SHA-256 `ef2d9a13ed4b3c06db638d4b494766f671dfd64f1d121fb238b97bef01d30dc1` |
| MLX | [#3961](https://github.com/ml-explore/mlx/pull/3961) `5a1e44c3bb991dab753cee394b0b1d889e2eb9a7`; [#2078](https://github.com/ml-explore/mlx/pull/2078) `5de6d94a903c9bf315e5548b03ec5294e5169c1a`; [#3120](https://github.com/ml-explore/mlx/pull/3120) `38ad257088fb2193ad47e527cf6534a689f30943` | 2025-04-17–2026-08-09 | MIT; license SHA-256 `ccfab7ccb2ea306f71531c8ca77bb55507606cd90768b1e32b8b52ab5b48cf01` |
| llama.cpp | [#13388](https://github.com/ggml-org/llama.cpp/pull/13388) `611aa914ef4231fab5d1ad04773c42e119ae2d2e`; [#22711](https://github.com/ggml-org/llama.cpp/pull/22711) `da44953329daec5f16b7b19d7ebfdc6552415362` | 2025-05-09–2026-05-12 | MIT; license SHA-256 `94f29bbed6a22c35b992c5c6ebf0e7c92f13b836b90f36f461c9cf2f0f1d010d` |
| BaseRT | [paper](https://arxiv.org/html/2607.00501v1), [repo commit](https://github.com/basecompute/baseRT/commit/bbded2c2fdb5e8fc1893fbbc5853a9e131250034) | 2026-08-09 | Apache-2.0; license SHA-256 `cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30` |

The survey extracted claims and mechanisms only; no external code was copied. An independent reimplementation would remain required under the target's editable-path contract.

## Candidate audit

| Mechanism and public claim | Cedar seam / M4→M5 mapping | Classification |
|---|---|---|
| **Lane-major LM-head scales**: exact 33-byte rows remove 3,110,912 logical bytes/token. M4 isolated kernel 436.628→427.778 us; recurring control saved 8.875 us, while total decode regressed 0.256%. | `LagunaLmHeadPrune.swift`, atlas family 17; same custom decode seam on M4/M5. Reported growth 7,020 bytes fits scope. | **Below Amdahl floor.** Novel and exact, but 8.875 us is only 49.3% of 18 us. Earlier 17-byte escape/sentinel encoding was 1.8–2.1% slower from branch/if-conversion cost. |
| **Narrow NVFP4 QMV tile**: MLX #3961 changes M5 g17s from four to two results/SIMD for N>=4096; Qwen generation +2.7%. | Generic MLX QMV is not Cedar's hot projection seam. Cedar already promotes a one-output-row/SIMD packed routed R1 kernel in families 11/13. Public evidence is M5-only. | **Already present/exhausted.** Output-row geometries are saturated; related routed load-sharing was exact but materially slower in #638. |
| **Sorted gather QMM**: MLX #2078 sorts MoE rows by expert and uses dedicated gathered quantized GEMM, yielding large public prompt gains. | Cedar prefill already calls `gatherSort` + `MLX.gatherQuantizedMM` and has a fused sorted routed path; ranked M5 selects NAX where available. | **Already present** in families 11/13. |
| **Split-K small-M QMM**: MLX #3120 reports ~25–30% on M3 Max at M=12–16. | Superficially matches per-expert prefill row counts, but generic M3 evidence does not establish M5 NAX benefit. | **Incompatible/exhausted.** Split-K re-associates checked reductions and is recorded as exhausted. |
| **Expert-major dense-GEMM remap**: llama.cpp #13388 compacts routed rows, runs ordinary dense GEMMs, then unmaps; pp512 gains were ~1.8–4.1x on tested Q4/F16 models. | Cedar already sorts expert runs and uses tuned GatherQMM. A dense remap changes format, materialization, and reduction ownership. | **No exact static bound.** No conservative residual >=2.33 ms/pass after current grouping and remap costs; unlikely <=8 KiB. |
| **Metal function constants for divmod**: llama.cpp #22711 reports M4 Pro decode +1.21–5.37%, prefill unchanged. | Relevant hardware generation, but Cedar's hot generated kernels already emit fixed dimensions as `constexpr`; remaining generic fallback is not the scored seam. | **Already present/not reachable.** Literal/descriptor hoists are exhausted. |
| **Separate decode GEMV with inline dequant**: BaseRT reports up to 1.56x vs llama.cpp and 1.35x vs MLX; large-MoE decode often only 1.04–1.07x. | BaseRT uses M3/M4 Q4/Q8. Cedar already uses custom M=1 NVFP4 QMV, `laguna_nvfp4_qdot_16`, and fused routed/shared decode kernels on M4/M5. | **Already present/format mismatch** across families 3, 8, 11, 13, 15. |

## Duplicate and negative audit

The ideas duplicate #652/`CURRENT_RESEARCH_STATE.md`: row tilings, split-K, packed scales, sorted MoE, routed-load sharing, descriptor hoists, epilogues, cache/attention, and LM-head repartitioning. Organizer frontier `c5b0a13c5cc032b485022db41bcd745792316714` (score 2.61650354381456) already contains paired scale metadata, zero-copy prefill scale views, barrier elision, packed router state, and active-64 Top8 routing.

Internal bounds reinforce the floor: #640 removed 38 launches and 79,691,776 logical bytes but saved only 356.8–368.1 us/pass; #649 bounded routed-down at 2.218 ms/pass. #647 found no discriminative M4 counters; #653 found no unbiased M4/M5 pairs. Cross-model/format percentages cannot replace Cedar seam ownership.

## Reproduction and closure

Searches used `Metal`, `NVFP4`, `quantized`, `QMV`, `QMM`, `MoE`, `gather`, `function constants`, and `Apple Silicon inference`, followed by immutable diffs, claims, and licenses. Closure checks:

```bash
python3 -m json.tool research/external_ranked_mechanism_candidates.json >/dev/null
shasum -a 256 research/external_ranked_mechanism_{candidates.json,survey.md}
wc -c research/external_ranked_mechanism_{candidates.json,survey.md}
git diff --check
git diff --exit-code 21011663a0ecf8c5288a5092388dc0bc78ef2051 -- Sources Vendor
senpai/check-editable-budget.sh 21011663a0ecf8c5288a5092388dc0bc78ef2051
```

The correct next action is to preserve the production frontier and wait for genuinely new public evidence with exact Cedar ownership above a static floor, rather than spend M4 or official M5 allocation on these mechanisms.
