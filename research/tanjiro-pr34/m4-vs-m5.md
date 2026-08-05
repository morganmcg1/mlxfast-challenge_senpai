# Why the M4 and the ranked M5 disagree, and what an M4 reading is worth

The advisor asked for this in the PR body rather than buried in a submission
note, because it governs how much weight any local number in this programme can
carry. All figures below are from artefacts on this branch, not from memory.

## The two axes, same tree, two hosts

Decompose each receipt into a prefill axis and a steady decode step:

```
S = 512000 * prefill_seconds_per_token          # ms for the 512-token forward
T = 1000 * decode_seconds_per_token - S / 128    # ms for the steady one-token step
```

| quantity | M4 Pro (`m4-L0.json`, inert) | ranked M5 (`b6032aeb`) | M4 / M5 |
| --- | --- | --- | --- |
| `S`, prefill forward | 577.20 ms | 97.86 ms | **5.90x** |
| `T`, steady decode step | 8.8161 ms | 4.2747 ms | **2.06x** |
| full `decode_seconds_per_token` | 13.326 ms | 5.039 ms | 2.64x |

So the headline "5.9x on prefill, 2.0x on decode" is a candidate-to-candidate
ratio of the *same* promoted tree on two hosts. It is not a hardware
specification ratio, and the two axes disagree for different reasons.

## The prefill 5.9x is mostly a NAX gate, not raw hardware

The M4 prefill number is not "the same work, slower". The promoted frontier's
routed gather-GEMM takes `gather_qmm_rhs_nax` only when `is_nax_available()`
holds, and `Vendor/mlx-swift/.../device.cpp:913` requires GPU architecture
generation >= 17. This host reports generation 16 (`applegpu_g16s`), so the M4
silently takes the non-NAX fallback.

The size of that gate is visible without any extra measurement. The M4 local
`prefill_speedup` for the promoted frontier is `188.17 / 577.20 = 0.326`: on M4
the frontier is **three times slower than the pinned baseline** on the prefill
axis, while on M5 the same tree scores `1.913`. A tree cannot be both 3x slower
and 1.9x faster for hardware-clock reasons. The frontier's prefill path is
tuned for a kernel the M4 cannot dispatch.

Consequence: **the M4 cannot screen any prefill change that touches a NAX-gated
kernel.** It is not conservative there, it is anti-correlated.

## The decode 2.06x is closer to an honest hardware ratio

The steady decode step has no NAX gate on the routed QMV path, and 2.06x is in
the range a bandwidth and clock difference explains. That is why this programme
uses M4 for decode-side method validation - is the instrument linear, is the
injected work negligible, is the response shape stable - and never for absolute
decode rates.

## The pinned local baseline is a stored constant, so local speedups are not measurements

Across all eleven r1 local runs, `baseline_decode_seconds_per_token` is
`0.01385621216015625` and `baseline_prefill_seconds_per_token` is
`0.00036751938916015626`, identical to every digit. A freshly measured baseline
cannot repeat to seventeen digits eleven times. The local paired baseline is a
pinned value, not a same-session measurement of this host.

Two things follow, and both are load-bearing for r2:

1. Every local `*_speedup` field is a candidate measured against a constant from
   another machine. It is arithmetic, not a comparison. Only same-host
   candidate-versus-candidate ratios mean anything locally.
2. For the local M4 ladder, `dT(n)` must be formed as `T(n) - T(0)` with both
   points measured on this host in the same session, **not** as
   `T(n) - T_pinned`. The pre-registered paired-baseline estimator in
   `prereg-r2.md` applies to the official receipts, where the baseline really is
   measured alongside the candidate; `senpai/tools/pr34_fit_ladder.py --json` is
   for those, and the local ladder is differenced against its own anchor
   instead. The anchor is run first and last in `pr34_m4_ladder.sh` so drift
   between the two is visible rather than assumed.

## What this means for the r2 conclusion

The M4 ladder in this revision validates the *instrument*: that the injected
dispatch carries negligible GPU work at 8 threadgroups, that the response is
linear in the injected count, and that the law has a knee at all. The *value* of
`c_M5` and `slack_M5` comes only from the five official receipts. Where the two
hosts disagree, the M5 receipt wins, and I will not use an M4 number to argue
for or against a fusion on M5.
