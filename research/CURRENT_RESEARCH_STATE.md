# SENPAI Research State

- **Updated:** 2026-08-08 19:19:35 UTC
- **Most recent human research direction:** Keep Cedar-Nezuko's live experiment running and immediately place Cedar-Fern, Cedar-Frieren, and Cedar-Tanjiro on distinct M4-reachable arms; do not wait for deeper synthesis before acting. Continue that synthesis in the background, let any fully preflighted genuine win submit independently under programme policy, and do not treat this as a final round.
- **Current scored baseline:** The active assignment base is `cac292f644f66be956d8422a4da384e9112cbdea`. The promoted frontier remains official submission `cc6ddc1`, weighted score `2.61650354381456`, commit `c5b0a13c5cc032b485022db41bcd745792316714`. The editable surface is `2,971,013 / 3,000,000` bytes, leaving `28,987` bytes. Ranked paired M5 evidence remains authoritative; decode and prefill speedups must each remain at least `0.95`. W&B: N/A.
- **Current research focus and themes:**
  - [PR #451](https://github.com/morganmcg1/mlxfast-challenge_senpai/pull/451) keeps Cedar-Nezuko on the live named-scalar depth-1 prefetch experiment for the NVFP4 OProj decode path. W&B: N/A.
  - [PR #453](https://github.com/morganmcg1/mlxfast-challenge_senpai/pull/453) assigns Cedar-Fern an exact router-top8 epilogue fusion: compute comparison and normalization inside the residual-RMSNorm router-source producer, eliminating the 256-logit materialization and dependent dispatch without changing selected experts or weights. W&B: N/A.
  - [PR #454](https://github.com/morganmcg1/mlxfast-challenge_senpai/pull/454) assigns Cedar-Frieren an explicit depth-1 software pipeline in the M4-reachable packed top-8 routed SwiGLU QMV, preloading the next fixed 512-K gate/up block while preserving qdot and reduction order. W&B: N/A.
  - [PR #455](https://github.com/morganmcg1/mlxfast-challenge_senpai/pull/455) assigns Cedar-Tanjiro a compiler-first four-block unroll and pointer/address specialization in the M4-reachable shared SwiGLU QMV, with an early static-null stop if the baseline compiler already emits equivalent code. W&B: N/A.
- **Archived hardware-dependent evidence:**
  - [PR #362](https://github.com/morganmcg1/mlxfast-challenge_senpai/pull/362) preserves Cedar-Fern's deletion-first LM-head cleanup. It closed without a scientific rejection because the 48 GiB host could not complete full-model validation; renew it on a host with at least 64 GiB. W&B: N/A.
  - [PR #421](https://github.com/morganmcg1/mlxfast-challenge_senpai/pull/421) preserves Cedar-Frieren's paired-query-head `_nax` GQA fragment-reuse packet. It closed because generation-16 M4 cannot reach that kernel; renew it on generation-17-or-newer M5 hardware. W&B: N/A.
  - [PR #429](https://github.com/morganmcg1/mlxfast-challenge_senpai/pull/429) preserves Cedar-Tanjiro's underoccupied regular-NAX occupancy selector. It closed because generation-16 M4 cannot reach that selector; renew it on generation-17-or-newer M5 hardware. W&B: N/A.
- **Current interpretation:**
  - The active batch spans four non-overlapping decode mechanisms: OProj load-latency overlap, router materialization/dispatch removal, routed-QMV fixed-block load overlap, and shared-QMV compiler/address specialization.
  - M4 evidence is directional only after proving the scored runtime reaches the same kernel family. `_nax` and generation-17 selectors still require direct M5 evidence.
  - Preserve exact greedy outputs, reduction order where assigned, serial non-speculative semantics, one-mechanism attribution, and the `28,987`-byte headroom. Each new arm is capped at 8 KiB growth.
  - A producer-local or microbenchmark win must survive cooled matched AB/BA end-to-end timing. Current screening thresholds are kernel at least `1.005x`, full decode at least `1.002x`, prefill at least `0.998x`, and weighted at least `1.0015x`.
- **Potential next research directions and themes:**
  - Use the four live results to distinguish dispatch/materialization overhead from memory-latency and compiler-scheduling limits, then follow the strongest measured cost center rather than combining mechanisms prematurely.
  - If router fusion wins, inspect other exact decode producer-consumer boundaries that remove a serial dispatch without adding arithmetic to a hot producer.
  - If either QMV scheduling arm wins, test only the resource-constrained follow-up suggested by occupancy and generated-code evidence; reject variants that increase spills or merely restate compiler output.
  - Restore the archived LM-head and NAX hypotheses only when their named hardware conditions are available; do not leave students idle behind unavailable hardware.
  - Continue deeper local-history and external-systems synthesis in the background for the next assignment batch.
  - Fully preflighted candidates may submit independently, first with `mlxfast submit --model "senpai"`; only an explicit unsupported-model rejection permits one fallback, and ambiguous responses must not trigger duplicate submissions.

_These deterministic inference experiments have no direct W&B run IDs. Trusted local benchmark artifacts, supervised harness records, and official measurements remain the primary inference evidence._

_This research-state update was generated by OpenHands on behalf of the research team._
