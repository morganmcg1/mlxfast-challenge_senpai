# R116-A premise correction: the assignment's headroom figure is M4 data and
# is further overstated by the un-applied SPLIT correction

This is a correction to the *framing* of assignment `maple-r116-a-shipped-
defaults-audit`, not to its executable instruction. The audit itself (screen +
confirmation over the shipped compiled defaults) proceeds unchanged. The
correction matters because the assignment justifies the round with a prize
estimate that is roughly an order of magnitude too large, and because the
mechanism it points at is already staffed on another PR.

## What the assignment claims

> `shared_nvfp4_swiglu_qmv_rows1_halved_bf16_v1` runs at 284.9 us/step and
> 153.1 GB/s = 58 % of the bandwidth ceiling, leaving ~119 us/step of slack,
> worth about +1.0 % of score.

## What the ranked-M5 evidence actually says

`research/maple-alphonse-r109e-qk-ceiling.md:~1451` and the digest at
`research/CURRENT_RESEARCH_STATE.md:590-593`:

> `shared_nvfp4_swiglu_qmv_rows1_halved` **230.0 us/step at 70.2 % of peak** —
> the only unfused half of the shared expert; fusion worth **20-40 us/step**.

Full M5 row: 230.0 us/step corrected, 2.8 % of decode, 39.4 calls/step,
5.84 us/call, 1.119 MB/call, **191.7 GB/s = 70.2 % of peak**, raw headroom
**68.5 us/step**.

So the 284.9 us / 153.1 GB/s / 58 % / 119 us figures are this M4 Pro
development host, not the machine that decides the score. Correction 1:
119 -> 68.5 us/step of raw headroom.

## Correction 2: the SPLIT=1 deflation has not been applied

`research/CURRENT_RESEARCH_STATE.md:594-596` and `:601-606`:

> **The atlas is uncorrected for SPLIT inflation.** Deflate every row by
> `1.554 us x calls/step` before ranking.
> **SPLIT inflation = +1.554 busy us per command buffer.** Under SPLIT=1 every
> dispatch is its own command buffer, so this is a *pool correction that scales
> with calls/step*.

For this kernel: `1.554 us x 39.4 calls/step = 61.2 us/step` of pure
instrumentation artifact. The 68.5 us of raw headroom therefore deflates to
roughly **7 us/step of real in-kernel headroom**.

The remaining recoverable quantity is dispatch removal, not bandwidth. Fusing
the gate/up half into the already-fused down half removes ~39.4 dispatches per
step. The measured removal price is **0.108 us/dispatch**
(`research/CURRENT_RESEARCH_STATE.md:1775-1782`, PR #483: +80 dispatches/step
cost +8.61 us/step, CI [-17.71, +35.02], family declared "terminal - the family
is dead"), i.e. ~4.3 us/step. That price is also why the *dispatch-count* story
alone cannot fund this round.

## Reconciled prize

| source | prize |
| ------ | ----- |
| assignment framing (M4, uncorrected) | ~119 us/step ~= 1.0 % of score |
| research state's own estimate | 20-40 us/step ~= 0.17-0.34 % |
| SPLIT-corrected in-kernel + dispatch | ~7 + ~4.3 = **~11 us/step ~= 0.09 %** |

The honest range is **10-40 us/step, i.e. 0.09-0.34 % of score** — about
3-11x smaller than the assignment states.

## The mechanism is already staffed

`research/CURRENT_RESEARCH_STATE.md:597-600`:

> **Assigned:** lever A (+C as fallback) -> maple-alphonse, PR **#700**
> (`maple-r114-e-gate-sp-latency-excavation`). **Shared-expert QMV fusion and
> the routed gate/up QMV family -> maple-edward, #693 `r110-b-rev4`.**

Shared-expert SwiGLU-QMV fusion is edward's assignment, not this one. R116-A
should not be justified by that kernel's headroom.

## Do NOT redirect this round to attention

An earlier internal suggestion (from a support agent, now retracted) proposed
redirecting to `laguna_sliding_fused_attn_ring_v1` (373.4 us/step, nominally
38.8 % of peak) or `full_fused_attn_grow_v1`. That is closed:
`research/CURRENT_RESEARCH_STATE.md:4624` — round 107, PR #642,
**`N-ISSUE-BOUND`**: both `laguna_sliding_fused_attn_ring_v1` and
`full_fused_attn_grow_v1` are at **97.7 % of peak instruction issue**
(`:3217`, `:3656`), so the apparent bandwidth headroom is not purchasable and
the whole above-floor pool including geometry changes is closed. Sliding QK-MMA
is doubly closed at `:1191` (`N-ISSUE-BOUND` + `N-QK-MMA-PADDING-BOUND`).
The `full_fused_attn_grow_v1` number is also 233.9 us/step at 135.6 GB/s =
**49.7 % of peak**, not the ~38 % that circulates from uncorrected SPLIT=1
timing (`:593`).

## What this means for R116-A

R116-A's executable content — auditing whether the shipped compiled defaults of
the NVFP4 SwiGLU-QMV header family and the o_proj QMV family are the fastest
settings — is independent of the kernel-headroom framing and is still worth
running: the header family is spliced into three decode kernels totalling
**2,647 us/step = 31 % of decode busy**, and a default flip is a one-line,
zero-build, bit-exact change. That is the round this student ran. The framing
paragraph should simply not be reused to size a future round.
