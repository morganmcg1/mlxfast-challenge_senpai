# SENPAI Research State

- **Updated:** 2026-08-08 13:38:45 UTC
- **Most recent human research direction:** Authorized campaign roles own the exact lifecycle of any committed, fully preflighted official candidate. Continue useful research while admission is busy, avoid tight polling or duplicate submissions after ambiguous responses, and submit with `mlxfast submit --model "senpai"` first; only an explicit invalid-or-unsupported model rejection permits one fallback.
- **Current scored baseline:** The active experiment base is `56627049c538474747297c8345a3a59260bf5226`. The official best weighted score remains `2.59787481790585`. [PR #399](https://github.com/morganmcg1/mlxfast-challenge_senpai/pull/399) remains the latest matched local frontier evidence: decode `1.007475065x`, prefill `0.999582837x`, weighted `1.005496185x`. The editable surface is `2,971,013 / 3,000,000` bytes, leaving `28,987` bytes. Ranked paired M5 evidence remains authoritative; decode and prefill speedups must each remain at least `0.95`. W&B: N/A.
- **Current research focus and themes:**
  - [PR #434](https://github.com/morganmcg1/mlxfast-challenge_senpai/pull/434) assigns Cedar-Nezuko an M4-reachable decode experiment: fold the exact post-attention residual addition into the active H48/H64 B=L=1 group-16 NVFP4 OProj producer, then feed the presummed BF16 vector directly to the existing fused RMS/router consumer without changing rounding order, router reduction order, dispatch count, or fallbacks. W&B: N/A.
  - [PR #362](https://github.com/morganmcg1/mlxfast-challenge_senpai/pull/362) remains Cedar-Fern's deletion-first LM-head cleanup, blocked pending capable-host equivalence, fallback checks, matched timing, and local-submit evidence. W&B: N/A.
  - [PR #421](https://github.com/morganmcg1/mlxfast-challenge_senpai/pull/421) remains Cedar-Frieren's M5-only paired-query-head `_nax` GQA K/V-fragment reuse experiment, blocked pending ranked-kernel reachability, correctness, occupancy, and cooled paired timing evidence. W&B: N/A.
  - [PR #429](https://github.com/morganmcg1/mlxfast-challenge_senpai/pull/429) remains Cedar-Tanjiro's M5-only generic underoccupied regular-NAX occupancy selector, blocked pending generation-17-or-newer dispatch, correctness, and cooled paired timing evidence. W&B: N/A.
- **Recent decisions and lessons:**
  - [PR #433](https://github.com/morganmcg1/mlxfast-challenge_senpai/pull/433) closed as an exact but timing-negative sliding-prefill V-layout result. The isolated H1 AB speedup was `0.989676077x`, BA was `0.957131486x`, geomean was `0.973588193x`, and the bootstrap 95% CI was `[0.959544194, 0.988311821]`; producer piggybacking added work rather than eliminating enough layout cost. W&B: N/A.
  - [PR #432](https://github.com/morganmcg1/mlxfast-challenge_senpai/pull/432) closed as a useful negative after full 16 KiB dense-down activation staging passed exactness but changed sign across order: AB measured `1.019017x`, while BA measured `1.000491x`, below the required `1.003x`. W&B: N/A.
  - These results reinforce isolated real-Metal AB/BA gates before full-model escalation and favor eliminating a materialized boundary inside an already-active producer over adding producer work solely to change layout.
- **Potential next research directions and themes:**
  - First evaluate whether the active NVFP4 OProj can own the exact BF16 residual boundary and remove one global intermediate without changing numerical order. Require bitwise equality for the summed vector, normalized vector, and router logits before timing.
  - Keep the four active mechanisms non-overlapping: producer-owned decode residual folding, capable-host LM-head deletion validation, M5-only NAX GQA fragment reuse, and M5-only regular-NAX tile subdivision.
  - Advance PR #434 only if isolated H48 and H64 AB/BA geomeans each reach at least `1.003x`, then require end-to-end decode at least `1.002x` in both orders, prefill at least `0.998x`, weighted speedup at least `1.0015x`, and a lower confidence bound above `1.0`.
  - If residual folding is negative, profile other exact producer-consumer boundaries that remove a materialized global vector without adding a dispatch; do not repeat OProj input staging or V-layout piggybacking.
  - Treat M4 evidence as directional and only valid for locally reached kernel families. Continue requiring direct M5 evidence for `_nax` and generation-17-or-newer selectors.
  - Preserve one-mechanism attribution and the serial non-speculative contract. Do not alter projections, SDPA, masks, cache behavior, token advancement, precision envelopes, or unrelated fallback paths.
  - Candidate submitters must record the exact commit and receipt, own terminal status, follow server retry guidance, and never duplicate a submission after an ambiguous response.

_These deterministic inference experiments have no direct W&B run IDs. Trusted local benchmark artifacts, supervised harness records, and official measurements remain the primary inference evidence._

_This research-state update was generated by OpenHands on behalf of the research team._
