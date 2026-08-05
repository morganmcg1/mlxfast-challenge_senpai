# Pre-registration — PR #44 r2, `MLX_MAX_MB_PER_BUFFER` upward axis

Written and committed **before** the ranked receipt. Supersedes
`research/nezuko-mb50-prereg.md`, which covered the downward half of the same
axis (r1, refuted: 50 MB measured −1.608% on ns).

- Arm: `Sources/MLXFastModel/LagunaRuntimeWeights.swift:386`,
  `MLX_MAX_MB_PER_BUFFER` `"50"` → `"512"`. One file, one token.
- Held fixed: `MLX_MAX_OPS_PER_BUFFER` = `200` (proven inert on this axis),
  `MLX_BFS_MAX_WIDTH` = `50`.
- Control: `c3ce66e`, `cand_pre 191.308 µs`, `cand_dec 5.04644 ms`,
  ns **2.544360**.
- Bit-exact by construction: the cap only moves command-buffer flush
  boundaries. Every arithmetic op, order, and dtype is unchanged.

## Why the upward half is the live half

`200 MB` is not a tuned value. Commit `814652a0` imported it from a
competitor snapshot, replacing `512`, and it was never validated in this
codebase — it was confounded with the ops-per-buffer knob that is now proven
inert. r1 tested only 200 → 50 (downward) and found it worse. The upward
direction had never been measured. `512` is therefore a *restoration* of this
file's pre-import value, not a novel extreme.

## B1 measured counts (M4 Pro, this host, counts-only evidence)

`research/nezuko_mbpb_up.sh`, 100 decode steps per cell,
`DARKBLOOM_STARTUP_MEMORY_PROFILE=full`, ops cap pinned at 200. Prefill cb
recovered by differencing the `--prefill` and decode-only totals.

| cap MB | decode cb/step | prefill cb | dispatches | divergences | mlx_peak_gb | peak_ram_gb |
|-------:|---------------:|-----------:|-----------:|------------:|------------:|------------:|
| 200 | 34.0 | 81 | 406.0 | 0 | 36.39 | 20.72 |
| 400 | 19.0 | 42 | 406.0 | 0 | 36.94 | 20.72 |
| **512** | **18.0** | **41** | 406.0 | 0 | 36.94 | 20.72 |
| 1024 | 13.0 | 41 | 406.0 | 0 | 36.94 | 20.72 |
| 2048 | 9.0 | 41 | 406.0 | 0 | 36.94 | 20.72 |

Dispatch count is invariant at 406 and greedy tokens match at every cap, so
the cap moves boundaries only — it does not change the work graph.
`gpu_busy_sum == gpu_busy_union` in all ten cells, so GPU time is cleanly
serial and the counts are trustworthy.

**Hard stop did not fire.** The assignment's no-arm condition was a cb curve
already flat at 200 in both phases. It is not flat: 200 → 400 removes 44% of
decode boundaries and 48% of prefill boundaries.

### Knee

- Prefill cb reaches its floor of **41** at **512** and stays there through
  2048. The prefill half of this axis is *closed* by this receipt.
- Decode cb has **no floor** at or below 2048 (still 9 and falling).

## Why 512 and not 2048

Predicted ns gain is monotone in the cap (+0.640 / +0.666 / +0.748 / +0.814%
for 400 / 512 / 1024 / 2048), so "largest predicted" would say 2048. I am
spending the single receipt at 512 because:

1. 512 captures **40 of 40** available prefill boundaries — the larger half of
   the predicted win (+0.404% of +0.666%).
2. It is past the decode elbow: 34 → 19 removes 15 cb, 19 → 18 removes one
   more. All 16 cheap decode boundaries are already gone at 512.
3. The extra +0.148% from 512 → 2048 is **~1σ of ns repeat noise**
   (cv 0.149%). One receipt cannot resolve it, so spending the receipt there
   buys no decidable information.
4. Mechanism warning against the deep end: M4 `gpu_busy_sum` — a GPU-side
   quantity, and clean because sum == union — is *minimised at 400* and then
   rises monotonically (8.335 → 8.181 → 8.233 → 8.248 → 8.271 ms at 200 / 400
   / 512 / 1024 / 2048). My own transfer law forbids using that to predict the
   M5 *magnitude*, but it is direct evidence that the linear count model is
   incomplete above ~400–512. 9 cb/step is a 3.8× extrapolation below the
   measured M5 point (34 cb) into exactly that region.
5. Memory is a non-issue and cannot be the reason to stay low: `mlx_peak_gb`
   is 36.94 for every cap ≥ 400 and worker `peak_ram_gb` is 20.72 everywhere.
   The cap is a flush threshold, not an allocation.

## Prediction (from my own counts × r1's own M5 per-boundary costs)

Slopes measured by the r1 ranked receipt `3e6fdcba` on M5, not assumed:
decode **+1.1045 µs/cb** (56.33 µs over 51 added cb), prefill
**+27.177 µs/cb** (2147 µs over 79 added cb). Score conversion from tanjiro's
PR #34 M5 dispatch law: 1 ms of T = 14.862% of score, 1 ms of S = 0.37134%.

Applying `research/nezuko_mbcap_predict.py --dec-cb 18 --pre-cb 41`:

- decode cb 34 → 18 (−16): `dT = −17.67 µs` → **+0.2626%** of score
- prefill cb 81 → 41 (−40): `dS = −1.0871 ms` → **+0.4037%** of score
- **predicted d_ns = +0.6663%**
- implies `cand_pre 189.185 µs`, `cand_dec 5.020275 ms`, ns **2.561436**

Hand-computed acceptance band (decode `[0.980, 1.053]`, prefill
`[0.952, 1.053]`): predicted decode ratio **1.0052**, predicted prefill ratio
**1.0112**. Both comfortably interior, so neither floor nor the legacy band is
at risk under the prediction, and a band failure would itself be information.

## Decision rule, fixed in advance

σ = 0.149% (candidate-side ns repeat cv). Verdict is read off measured d_ns
against control ns 2.544360, and **rank on ns, never on officialScore**.

| measured d_ns | verdict | what it means |
|---|---|---|
| > +0.97% | **OVERSHOOT** | per-cb cost is *larger* than r1's slope; the count law is superlinear. Justifies an immediate 1024/2048 follow-up receipt. |
| +0.37% … +0.97% | **CONFIRM** | prediction ± 2σ. The M5 boundary-count law is linear and symmetric in direction; merge 512. |
| +0.15% … +0.37% | **PARTIAL** | boundary removal helps but less than the r1 slope; the law is concave in count. Merge if it beats best, but do not extrapolate further. |
| −0.15% … +0.15% | **NULL** | boundary count is not causal on M5 in the downward direction. r1's 50 MB regression was a small-buffer pathology, not a linear boundary law. Revert the token to 200 and close the axis. |
| < −0.15% | **REFUTE** | removing boundaries *hurts* M5. The M4 `gpu_busy` turnover transferred and the count law is wrong in this direction. Revert to 200 and amend the transfer law. |

## Which cell of the four-cell B−C model each sign tests

The model from Deliverable C: boundary **counts** transfer M4 → M5 exactly;
boundary **timing** does not, not even in sign.

- **Cells 1–2** (decode-count → M5 decode time; prefill-count → M5 prefill
  time) are tested **out-of-sample in the opposite direction**. r1 measured
  both slopes by *adding* boundaries; this receipt *removes* them. CONFIRM
  puts both cells on a two-point line through the shipped config.
- **Cell 3** (M4 boundary timing → M5 boundary timing, proven
  non-transferring) gets its decisive out-of-sample test. frieren's M4 wall
  datum says 400 MB is **+2.50% worse** (t = +4.0), and my own M4 wall agrees
  (8.599 → 8.734 ms at 512, worse) while M4 *GPU* time improves. Cell 3 says
  that wall datum is inadmissible. A positive d_ns confirms the non-transfer
  and retires frieren's datum. A negative d_ns means M4 wall *did* transfer
  here, and the law needs the qualifier "M4 wall becomes admissible when the
  host-gap fraction moves by more than ~3 points" (it moves 3.1% → 5.7%).
- **Cell 4** (M4 count = M5 count) is not re-tested; it is assumed, and every
  number above depends on it. The 200 MB row reproducing decode 34 / prefill
  81 exactly — the counts r1 measured on M5 — is the consistency check that
  licenses the assumption.

## Budget

Exactly **one** ranked receipt, at 512. No re-measurement, no second arm. If
the verdict is NULL or REFUTE the token goes back to `200` and the axis closes
with the upward half measured rather than assumed.

## Gate A2 outcome: numerical-inertness control (resolved before submitting)

`research/run_upstream_equivalence.sh` returns rc=1 on this M4 Pro host at
**every** cap, including the unmodified base value. Prefill reports
`maximumAbsoluteLogitError 0.125` (mean `0.011933609`); all 8 decode steps are
exactly 0; every argmax token matches (5991/509/902 x 3).
`EQUIVALENCE_EXACT_STEPS=8` of 9.

`research/nezuko_equiv_control.sh` replays the *same built binary* at three
caps via the environment override (env wins over the in-code `setenv(...,0)`,
so no rebuild and no confound). Log: `research/nezuko_equiv_control.log`.

| `MLX_MAX_MB_PER_BUFFER` | role | prefill max abs err | prefill mean abs err | decode steps exact | argmax match |
|---|---|---|---|---|---|
| 200 | base / revert target | 0.125 | 0.011933609 | 8 / 8 | yes |
| 50 | r1 arm | 0.125 | 0.011933609 | 8 / 8 | yes |
| 512 | **r2 arm** | 0.125 | 0.011933609 | 8 / 8 | yes |

The three per-cap step blocks are **byte-identical** (md5
`9e46ee364ceaf57dbbab59b28dca78b3` for all three). The divergence is invariant
to the submitted token, so it is a property of host + base, not of this change.
That is the AGENTS.md-documented M4 Pro case: this host reports Apple GPU
generation 16 and does not select the `_nax` prefill kernels the ranked M5
uses, and the divergence is prefill-only -- exactly the axis whose kernel
family differs. Decode, which carries 75% of the score weight, is bit-exact at
all three caps.

Per the pre-committed rule this is the "all three caps show it" branch:
**proceed to the single ranked receipt at 512**, and report this control table
rather than claiming a clean equivalence pass. `./benchmark.sh --local-iterate`
independently reports `passed_correctness true` with `max_abs_diff 0` and the
golden hash matched, so no locally comparable gate is failing.

## Scope note recorded before submitting: this receipt cannot be promoted

`research/receipt_baseline_lottery.py c3ce66e 3e6fdcb` over 1034
correctness-passing receipts gives the promotion arithmetic:

- The baseline arm runs pinned code on every receipt, so its spread is pure
  noise: prefill sd **1.933%**, decode sd **0.247%**, injecting **0.518%** into
  every `officialScore`.
- Crown to beat is **2.552308**. From the control's candidate code the
  candidate-side edge needed is **+1.61%** of score for 50% promotion odds and
  **+2.31%** for 90%.

My pre-registered prediction is **+0.666%**. That is roughly 2.4x short of a
coin-flip promotion, so **this receipt is expected to come back `rejected` even
if it confirms perfectly.** It is a measurement, not a promotion bid, and
`rejected` here carries no information about correctness or about the
hypothesis. Read `d_ns`, `max_abs_diff`, and the two floor verdicts; ignore
ranking status.

The same tool also shows why `ns` and not `officialScore` is the ranking
statistic for this axis. The prior receipt's `officialScore` gap of -1.165%
decomposes into **candidate (real code) -1.621%** plus **baseline (lottery)
+0.449%** — it drew a baseline at the **88.7th percentile** (`base_z` +1.42)
while the control drew the 54.1st. The candidate-side term -1.621% agrees with
`d_ns` -1.608% to within 0.013 points, confirming that `ns`, computed from
`cand_pre` and `cand_dec` alone, is baseline-independent. Every per-commit slope
in this pre-registration was fitted on `ns`, so none of them inherits the
lottery.

## Realised outcome (written after the ranked receipt released)

Receipt `c747336c-2f0b-4870-8481-faccaeafe99f`, runner commit
`cc4b1dc77d59c4a55cffdabab0fee68e2071e22f`, submitted 2026-08-05T14:12:43Z,
released 2026-08-05T14:34:20Z.

| quantity | pre-registered | observed | miss |
| --- | --- | --- | --- |
| `cand_pre` (us) | 189.1848 | 197.093424 | +4.18% |
| `cand_dec` (ms) | 5.020275 | 5.0752060 | +1.09% |
| `ns` | 2.561436 | 2.514736 | -1.82% |
| `d_ns` vs control 2.544360 | +0.666% | **-1.1643%** | -1.83 pp = **7.9 sigma** |

Decision rule as written: `d_ns < -0.15%` is REFUTE. Observed -1.1643% is far
past that line, so the rule fires unambiguously.

Action taken, exactly as pre-committed: the arm is reverted to
`MLX_MAX_MB_PER_BUFFER = "200"`, leaving the submitted surface byte-identical to
`BASE_SHA`, and the transfer law is amended in
`research/nezuko-mbcap-up-receipt.md`.

Everything else on the receipt was green: `max_abs_diff 0`,
`passed_correctness true`, `error ""`, both speedup floors passed (decode
2.7380, prefill 1.9543), semantic GPQA 9/9, TTFT 9/9. The `rejected` status is
ranking-only and was pre-registered as the expected outcome; the paired baseline
drew the 96.8th percentile (`base_z` +1.777), which is why the `officialScore`
gap (-0.262%) is smaller than the real candidate regression (-1.171%).

What the miss teaches: the pre-registration's error was not in `ns` arithmetic
(the candidate-side lottery decomposition reproduces `d_ns` to 0.007 pp) but in
assuming per-command-buffer cost is a cap-independent constant. It was fitted on
the 200-to-50 direction, which *adds* buffers, and then extrapolated to a
direction that *removes* them. Prefill `S` was predicted to fall 1.087 ms and
instead rose 2.9621 ms -- 2.7x the magnitude with the sign inverted. See the
amended law in the receipt note.

