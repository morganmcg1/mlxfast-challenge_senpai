# SENPAI Research State

- **Updated:** 2026-08-08 20:59 UTC
- **Most recent human research direction:** Keep all Cedar students on distinct M4-reachable arms; do not wait for deeper synthesis before acting. Continue synthesis in the background, let any fully preflighted genuine win submit independently under programme policy, and do not treat this as a final round.
- **Current scored baseline:** The active assignment base is `7f3193b6fc433f3a400b5c3dbfdcb6402d4f2b33`. The promoted frontier remains official submission `cc6ddc1`, weighted score `2.61650354381456`, commit `c5b0a13c5cc032b485022db41bcd745792316714`. The editable surface is `2,971,013 / 3,000,000` bytes, leaving `28,987` bytes. Ranked paired M5 evidence remains authoritative; decode and prefill speedups must each remain at least `0.95`. W&B: N/A.
- **Current research focus and themes:**
  - [PR #461](https://github.com/morganmcg1/mlxfast-challenge_senpai/pull/461) assigns Cedar-Tanjiro an exact 65,536-entry BF16-output SiLU lookup table in the active shared-expert Rows1 QMV. It isolates shared-expert special-function cost. W&B: N/A.
  - [PR #463](https://github.com/morganmcg1/mlxfast-challenge_senpai/pull/463) assigns Cedar-Fern an exact 65,536-entry FP32 sigmoid lookup table in the active decode router. It isolates router special-function cost. W&B: N/A.
  - [PR #464](https://github.com/morganmcg1/mlxfast-challenge_senpai/pull/464) assigns Cedar-Frieren an arithmetic-only current-frontier test of replacing the scalar four-lane NVFP4 qdot chain with an equivalent `dot(float4, float4)` form. All current scale, seed, sign-domain, and low-scale fast paths must remain intact. W&B: N/A.
  - [PR #465](https://github.com/morganmcg1/mlxfast-challenge_senpai/pull/465) assigns Cedar-Nezuko a representation-only conversion of the seven remaining active scalar qdot input-staging arrays to register-resident `float4` chunks while preserving scalar qdot arithmetic order. W&B: N/A.
- **Current interpretation:**
  - The four live arms form two clean causal pairs: exact special-function elimination in separate runtime kernels, and NVFP4 qdot arithmetic form versus input-staging representation. No student may combine paired mechanisms before each is measured independently.
  - Recent Cedar results reject count-heavy producer fusion, source-only unrolling, tiny host-object reuse, and deeper QMV load scheduling as current priorities because they regressed or reversed under cooled order reversal.
  - Maple's measured dispatch ladder shows that count-only fusion is too small: command-buffer issue cost is roughly `0.1–0.17 µs`, while a serialized 4 KiB round trip costs roughly `1.24 µs`. The next fusion hypothesis must retain a real dependent intermediate in registers rather than merely remove dispatch count. Evidence: W&B run `7ep17pqq` — https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/7ep17pqq.
  - M4 evidence is directional only after proving the scored runtime reaches the same kernel family. `_nax` and generation-17 selectors still require direct M5 evidence.
  - Preserve exact greedy outputs, serial non-speculative semantics, one-mechanism attribution, and the `28,987`-byte frontier headroom. The qdot assignments are capped at 2 KiB growth and should be net non-growing; the LUT assignments remain capped at 8 KiB and may not embed source-literal tables.
  - Any isolated kernel win must survive cooled matched AB/BA end-to-end timing. Screening thresholds are isolated kernel at least `1.005x` where applicable, full decode at least `1.002x`, prefill at least `0.998x`, and weighted at least `1.0015x` in both orders.
- **Potential next research directions and themes:**
  - Review PRs #464 and #465 strongest-first. If one qdot mechanism wins, merge it, rebase the other, and rerun only if the winning edit changes its causal comparison point.
  - Let PRs #461 and #463 establish whether exact special-function elimination has measurable end-to-end value; do not combine the tables before independent evidence is terminal.
  - Pursue true register-resident producer/consumer fusion only where a dependent intermediate and its real round trip disappear; do not reopen count-only fusion.
  - Await Maple's editable-cap split and float4 attention-merge evidence before consuming additional headroom in those owned areas. W&B: N/A for those deterministic systems PRs.
  - Restore archived LM-head and NAX hypotheses only when their named memory or hardware conditions are available; do not leave students idle behind unavailable hardware.
  - Fully preflighted candidates may submit independently, first with `mlxfast submit --model "senpai"`; only an explicit unsupported-model rejection permits one fallback, and ambiguous responses must not trigger duplicate submissions.

_Except for the linked Maple measurement run, these deterministic inference experiments have no direct W&B run IDs. Trusted local benchmark artifacts, supervised harness records, and official measurements remain the primary inference evidence._

_This research-state update was generated by OpenHands on behalf of the research team._
