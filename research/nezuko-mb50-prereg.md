# Pre-registration — `MLX_MAX_MB_PER_BUFFER` 200 -> 50, one ranked M5 receipt

Assignment `maple-2026-08-05b-mb-per-buffer-50`, PR #44, base
`d18ebbbaf724cfc8cc631d9d50de7104f0c879b8`.
Written and committed **before** the submission was dispatched.

## Arm under test

One-token diff in `Sources/MLXFastModel/LagunaRuntimeWeights.swift:386`:
`setenv("MLX_MAX_MB_PER_BUFFER", "200", 0)` -> `"50"`. `MLX_MAX_OPS_PER_BUFFER`
stays 200 and `MLX_BFS_MAX_WIDTH` stays 50. The branch is gated on
`policy.isLowMemory == false` (>= 64 GiB), so it fires unconditionally on the
128 GB ranked M5 and never on this 48 GiB M4 Pro unless
`DARKBLOOM_STARTUP_MEMORY_PROFILE=full` is forced.

The cap only moves where `needs_commit()` closes a command buffer
(`Vendor/mlx-swift/.../metal/device.cpp:484-487`). It changes no kernel, layout,
precision, mask, RoPE, cache, or dispatch order, so the greedy token stream is
bit-exact by construction. That is a prediction to be checked, not an excuse to
skip the check.

## Prior (local M4 wall-clock only; there is no M5 datum on this axis)

| source | design | effect of 50 MB vs 200 MB |
| --- | --- | --- |
| frieren PR #23 r2 | balanced `ABBA\|BAAB\|ABBA`, 12 arms, 2000 steps/arm, fresh process per arm | decode step **-1.76%** |
| my own forced-full sweep (run `4db9908a`) | full200 n=3 8.5707 +/- 0.0460 ms wall | **-1.99%** wall, t = -3.2; 400 MB +2.50%, t = +4.0; monotone |
| frieren cb/step traces | 48 cb/step -> 140 cb/step | step 8834.4 -> 8678.6 us (**-1.76%**) |

Transfer arithmetic: M4 decode 13.344 ms/token vs M5 5.087, and M4
under-reports decode wins by ~1.28x. A -1.8 to -2.0% M4 decode wall maps to
roughly **-1.4 to -2.0% of M5 decode s/tok**, and decode carries 0.75 of the
score exponent, so the **pre-registered prediction is `Delta ns = +1.05% to
+1.50%`**, point estimate **+1.25%**.

## Metric and why

The verdict is taken on **`ns`**, the renormalised score computed from
candidate-side timings only:

```
norm_decode_su  = 0.013890  / decode_seconds_per_token
norm_prefill_su = 0.0003845 / prefill_seconds_per_token
ns              = norm_decode_su**0.75 * norm_prefill_su**0.25
Delta           = 100 * (ns_candidate / ns_control - 1)   [%]
```

Control: `c3ce66e` (n=1), `cand_pre` 191.308 us, `cand_dec` 5.04644 ms,
**`ns_control` = 2.544360**, `S` = 97.950 ms, `T` = 4.2812 ms.

**Noise term used: the candidate-side per-receipt sigma, not fern's
`sigma_ln(officialScore) ~= 0.73%`.** `ns` is a function of the candidate arm
alone, so the paired-baseline draw — which is the entire reason `officialScore`
carries 0.73% and prefill_speedup carries a 4.9% floor — cancels out of it
exactly. The programme's pooled figure over 7 byte-identical families (27 dof)
is `cv(ns) = 0.149%`; the advisor's candidate-side `sigma_S ~= 0.183%` is the
looser of the two and is the one adopted here, deliberately, so the
confirmation bar cannot be accused of being tuned to the answer.

Both this receipt and the control are n=1, so the relevant dispersion is the
difference of two single draws:

```
sigma_diff = 0.183% * sqrt(2) = 0.259%      2 * sigma_diff = 0.52%
```

`sigma_ln(officialScore) = 0.73%` is used for nothing except stating in advance
that the officialScore delta is **not** evidence: at 0.73% per arm, a paired
officialScore contrast has a 2-sigma floor of 2.07%, i.e. it cannot see the
predicted +1.25% at all. Reporting officialScore as an outcome would be a
category error under the rule now in force.

## Decision rule (fixed before submission)

Let `Delta` be as defined above, from the single ranked receipt.

1. **Confirmation** — `Delta >= +0.52%`. The M4 cap effect transfers to the M5
   with the same sign. Recommend the one-token change for the frontier. If
   `Delta` lands in `[+0.52%, +1.05%)` the sign is confirmed but the magnitude
   is **attenuated relative to the M4 prediction**, and I will say so rather
   than quietly banking the M4 number.
2. **Refutation** — `Delta <= 0.00%`. The cap effect does not transfer. This
   retires the cap axis as an M5 lever and, more valuably, is the first
   calibration of what a well-designed M4 wall-clock result is worth on the
   ranked host. It is a full-value result and I will report it as one.
3. **Indeterminate** — `0.00% < Delta < +0.52%`. Attenuated or unresolved. I
   will **not** claim a win, will **not** ask for promotion, and will state that
   a second receipt is required to separate a real ~+0.3% from noise.
4. **Invalid, not a null** — any of `max_abs_diff != 0`, a failed correctness or
   hidden gate, `passed_decode_speedup_floor == false`, or
   `passed_prefill_speedup_floor == false`. Then the arm produced no reading on
   the hypothesis and I will say the diff was wrong, not that the cap is
   neutral.

Sub-hypothesis recorded now, reported either way: the M4 evidence is a
**decode-step** effect, so the expected decomposition is `T` down and `S`
roughly flat. If instead `S` moves and `T` does not, the mechanism I have been
assuming is wrong even if `Delta` is positive.

Secondary, for the ledger only, explicitly not part of any verdict:
`officialScore`, `draw = officialScore / ns`, the paired baseline's prefill us
and its percentile in fern's feed, TTFT, peak RAM, semantic GPQA, and the UTC
submit/release times.

## Stop rule

One receipt. Terminal whatever the sign. No second ranked slot without the
advisor granting it.
