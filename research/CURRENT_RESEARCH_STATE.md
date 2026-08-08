# SENPAI Research State

- **Updated:** 2026-08-08 11:20:19 UTC
- **Most recent human research direction:** Authorized campaign roles own the exact lifecycle of any committed, fully preflighted official candidate. Continue useful research while admission is busy, avoid tight polling or duplicate submissions after ambiguous responses, and submit with `mlxfast submit --model "senpai"` first; only an explicit invalid-or-unsupported model rejection permits one fallback.
- **Current scored baseline:** The live advisor base before this state-only update is `75f6ec9bf2cfb2573b5d4a7fd432cd9ef59e3e3c`. The official best weighted score remains `2.59787481790585`. [PR #399](https://github.com/morganmcg1/mlxfast-challenge_senpai/pull/399) remains the latest matched local frontier evidence: decode `1.007475065x`, prefill `0.999582837x`, weighted `1.005496185x`. The editable surface is `2,971,013 / 3,000,000` bytes, leaving `28,987` bytes. Ranked paired M5 evidence remains authoritative; decode and prefill speedups must each remain at least `0.95`. W&B: N/A.
- **Current research focus and themes:**
  - [PR #362](https://github.com/morganmcg1/mlxfast-challenge_senpai/pull/362) remains Cedar-Fern's deletion-first LM-head cleanup, blocked pending capable-host equivalence, fallback checks, matched timing, and local-submit evidence. W&B: N/A.
  - [PR #421](https://github.com/morganmcg1/mlxfast-challenge_senpai/pull/421) remains blocked pending direct M5 validation of paired-query-head `_nax` GQA K/V-fragment reuse; M4 generation 16 cannot reach the ranked kernel family. W&B: N/A.
  - [PR #429](https://github.com/morganmcg1/mlxfast-challenge_senpai/pull/429) remains blocked pending direct M5 validation of the generic underoccupied regular-NAX occupancy selector; local M4 correctness does not establish its M5 performance sign. W&B: N/A.
  - Assign Cedar-Nezuko one M4-reachable, architecture-generic prefill experiment: extend the existing fused sliding-prefill Q/K normalization-plus-RoPE kernels to emit raw V directly in `[1, KVH, L, 128]` head-major layout. The candidate must replace only the separate sliding-prefill V reshape/transpose, preserve Q/K arithmetic and all cache/attention semantics, and cover both ordinary 512-token sliding prefill and the terminal last-row sliding path. W&B: N/A.
- **Recent decisions and lessons:**
  - [PR #432](https://github.com/morganmcg1/mlxfast-challenge_senpai/pull/432) closed as a useful negative after full 16 KiB dense-down activation staging passed exactness but missed the isolated reproducibility gate: AB measured `1.019017x`, while BA measured `1.000491x`, below the required `1.003x`. The candidate was reverted. W&B: N/A.
  - [PR #430](https://github.com/morganmcg1/mlxfast-challenge_senpai/pull/430) closed as a measured negative after routed R1 activation staging produced a small decode gain but regressed prefill enough to miss its contract. W&B: N/A.
  - [PR #428](https://github.com/morganmcg1/mlxfast-challenge_senpai/pull/428) closed after exact fused prefill transpose/gate materialization changed sign between AB and BA. Together with PR #432, this reinforces paired-order gates before full-model escalation. W&B: N/A.
  - [PR #423](https://github.com/morganmcg1/mlxfast-challenge_senpai/pull/423) established that exact frozen benchmark-shape predicates fail static integrity; scheduling policy must use generic occupancy invariants. W&B: N/A.
- **Potential next research directions and themes:**
  - Evaluate four non-overlapping mechanisms: capable-host LM-head deletion validation, M5-only NAX GQA fragment reuse, M5-only regular-NAX tile subdivision, and M4-reachable sliding-prefill V-layout emission.
  - Treat V-layout emission as a producer-layout experiment, not another post-attention transpose fusion: piggyback the V load/store on the existing K-head threadgroups and require bitwise equality against the stock V reshape/transpose before timing.
  - Require a focused real-Metal old-chain versus fused-output AB/BA screen before full-model timing. Advance only when both orders exceed `1.002x` and the lower confidence bound exceeds `1.0`.
  - Preserve one-mechanism attribution: do not alter full-attention kernels, Q/K arithmetic, projection weights, SDPA, masks, cache behavior, decode, threadgroup geometry, NAX selectors, or any second optimization.
  - Treat M4 evidence as directional only, but useful here because this generic embedded sliding-prefill kernel family is locally reachable; continue requiring direct M5 reachability for `_nax` experiments.
  - Full activation staging, routed activation staging, post-SDPA transpose/gate fusion, exact-shape scheduling, historical multi-token softplus recovery, and previously catalogued broadcast/staging variants remain exhausted.
  - Candidate submitters must record the exact commit and receipt, own terminal status, follow server retry guidance, and never duplicate a submission after an ambiguous response.

_These deterministic inference experiments have no direct W&B run IDs. Trusted local benchmark artifacts, supervised harness records, and official measurements remain the primary inference evidence._

_This research-state update was generated by OpenHands on behalf of the research team._
