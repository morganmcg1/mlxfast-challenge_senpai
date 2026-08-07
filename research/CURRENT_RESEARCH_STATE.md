# SENPAI Research State

- **Updated:** 2026-08-07 00:06:50 UTC
- **Most recent human research direction:** Authorized campaign roles own the exact lifecycle of any committed, fully preflighted official candidate. Do not wait for a central queue owner; follow server retry guidance, avoid tight polling and duplicate submissions after ambiguous responses, and continue useful research while admission is busy. Submit with `mlxfast submit --model "senpai"` first; only an explicit invalid-or-unsupported model rejection permits one fallback.
- **Current integrated baseline:** `7e1ca41041ba305af36e374fb64949151d8ba121` on `codex/mlxfast-cedar-20260804-advisor`; its scored runtime frontier is `0e04cf64e35f969635d0bad6c977d0e7de77850a`, with only advisor documentation above it. The same-session normalized baseline is decode `1.0`, prefill `1.0`, and weighted score `1.0`; both official component floors are `0.95`. The editable surface is `2,998,093 / 3,000,000` bytes, leaving `1,907` bytes. Ranked paired M5 evidence is authoritative.
- **Current research focus and themes:**
  - [PR #150](https://github.com/morganmcg1/mlxfast-challenge_senpai/pull/150) is the merged current winner, making router-key suppression canonical.
  - [PR #171](https://github.com/morganmcg1/mlxfast-challenge_senpai/pull/171), Fern revision `r2`, tests sliding-attention exact-block boundary trim elision. It must add a rotating-trim invalidation test, pass `--local-submit`, and may spend exactly one authoritative M5 submission with `--model senpai`.
  - [PR #176](https://github.com/morganmcg1/mlxfast-challenge_senpai/pull/176), Nezuko, tests the reverse ablation of standalone NVFP4 QMV seed elision, with alternating local timing, strict correctness, and at most one M5 submission only after clearing the prescribed thresholds.
  - [PR #178](https://github.com/morganmcg1/mlxfast-challenge_senpai/pull/178), Tanjiro, tests recomputing the final eight router ordinal scores instead of retaining all 256 sigmoid scores in threadgroup memory. It must clear decode `>= 1.0015x` in both paired comparisons, prefill `>= 0.995x`, weighted score `> 1`, and full correctness before hard-selecting the recompute arm.
  - [PR #33](https://github.com/morganmcg1/mlxfast-challenge_senpai/pull/33), Frieren revision `r6`, must cleanly recompose only its deletion cleanup from `a068310f7ffd4bd2e6e3444db772ce21bb796038`, preserve all winners, leave only `LagunaRuntimeModel.swift` in the submitted delta, and pass a fresh `--local-submit`; no matched timing or M5 run is required.
  - [PR #177](https://github.com/morganmcg1/mlxfast-challenge_senpai/pull/177) is administratively closed because its assignment marker used the display name rather than the registered student identity; no experiment ran and no scientific conclusion was drawn.
  - [PR #151](https://github.com/morganmcg1/mlxfast-challenge_senpai/pull/151) is closed as a correct official non-winner: receipt `0e430857-0d9b-45c8-a7d6-b60ad5f6c563` passed correctness and both floors, but weighted score `2.460600` was `12.91%` below the comparison best.
  - [PR #168](https://github.com/morganmcg1/mlxfast-challenge_senpai/pull/168) is closed as a clean local negative after stable indirect-slot ordering missed the decode continuation threshold.
  - Recent closed negatives remain useful guardrails: [PR #164](https://github.com/morganmcg1/mlxfast-challenge_senpai/pull/164) tested fused-attention release checks, [PR #163](https://github.com/morganmcg1/mlxfast-challenge_senpai/pull/163) tested release preallocation, and [PR #152](https://github.com/morganmcg1/mlxfast-challenge_senpai/pull/152) tested fused QKV projection order.
- **Potential next research directions and themes:**
  - Prefer deletion-first or byte-neutral reached-path work because only `1,907` editable bytes remain.
  - After the active assignments, test the shared-expert fused-bank invariant guard hoist and routed-down static divisibility guard hoist as separate hypotheses.
  - Precomputing the per-layer decode asynchronous-fire mask and introducing a dedicated one-token decode loop remain distinct structural candidates; avoid combining them before either mechanism is measured independently.
  - Avoid overlap with PRs #176/#178, and do not repeat broad tile or threadgroup tuning already falsified by prior experiments.
  - Treat M4 timing as directional only, never as evidence for M5-only `_nax` prefill geometry. Preserve matched local controls and the `0.95` component floors.
  - Require exact scope and budget validation, an intact 40C gate, same-host matched evidence, checked outputs, and official M5 evidence for promotion.
  - Candidate submitters must record the exact commit and receipt, own the terminal status, follow server retry guidance, and never duplicate a submission after an ambiguous response.

_These inference experiments emit no W&B run IDs, so no direct W&B run URLs exist; trusted local benchmark artifacts, supervised harness records, and official measurements are the evidence record._

_This research-state update was generated by OpenHands on behalf of the research team._
