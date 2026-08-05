# mb-per-buffer 50 — ranked receipt log (PR #44, Deliverable A)

Candidate: `MLX_MAX_MB_PER_BUFFER` 200 -> 50 in
`Sources/MLXFastModel/LagunaRuntimeWeights.swift:386`
(one file, one token, `MLX_MAX_OPS_PER_BUFFER` unchanged at 200).

Pre-registration: `research/nezuko-mb50-prereg.md`, committed in `3cb8ebc`
before the submission was dispatched.

## Submission channel

| field | value |
| --- | --- |
| submission id | `3e6fdcba-29d7-4bd2-bca4-7fc9c565a495` (`3e6fdcb`) |
| local commit submitted | `1ce8373` |
| note | `research/nezuko-mb50-submission-note.md` (16.5 KiB uploaded) |
| model label | `Claude Opus 5` |
| UTC submit | 2026-08-05T12:25:09Z |
| CLI returned | 2026-08-05T12:25:17Z (`status validating`) |
| slot state before submit | free — every prior submission terminal, last `4058d0b` at 10:53 |
| receipt `createdAt` | 2026-08-05T12:25:15.775Z |
| official run `timestamp` | 2026-08-05T12:35:02Z |
| UTC receipt released (`updatedAt`, terminal) | 2026-08-05T12:46:03.999Z |
| UTC slot released to advisor | 2026-08-05T12:46:04Z (receipt terminal; confirmed free by `mlxfast submissions` at 12:53:57Z) |
| wall time submit -> terminal | 20 min 48 s |

The shared `morganmcg1` ranked channel is **released**. One submission was
dispatched for this assignment and nothing was chained behind it; the next slot
is committed to tanjiro.

## Receipt fields

From `mlxfast submissions` / `officialMetrics`, fetched 2026-08-05T12:54:11Z
into `research/nezuko-corpus-1253.json` (untracked, 1,507 records).

| field | value |
| --- | --- |
| `commit` (receipt) | `021fa4a442cac25b2390818abdc3bcb04570fed0` |
| `cand_pre` (µs) | **195.502521** (`prefill_seconds_per_token` 0.000195502521484375) |
| `cand_dec` (ms) | **5.1195537** (`decode_seconds_per_token` 0.0051195537109375) |
| computed `ns` | **2.503448** (`nd` 2.71313, `npf` 1.96673) |
| Δ `ns` vs control 2.544360 | **−1.608%** |
| `S` (ms) | 100.097 (control 97.950, **+2.193%**) |
| `T` (ms) | 4.3375 (control 4.2812, **+1.316%**) |
| officialScore | 2.49387730410401 |
| `draw` = officialScore / `ns` | 0.99618 (control 0.99171) |
| published `decode_speedup` | 2.7037883055 |
| published `prefill_speedup` | 1.9569614726 |
| paired-baseline prefill µs (percentile) | 382.591 µs — **88.7th percentile** of 1,033 scored receipts (corpus median 368.497 µs): an unusually slow-prefill baseline session |
| paired-baseline decode ms (percentile) | 13.8422 ms — 42.5th percentile (median 13.8483 ms): an ordinary decode session |
| `max_abs_diff` | **0** |
| `passed_correctness` | true (1,344 checked steps, 11 cases, `golden_hash` be7738fc…, `weights_hash` aff99430…) |
| decode floor verdict | **pass** (`passed_decode_speedup_floor` true, 2.7038 vs floor 0.95) |
| prefill floor verdict | **pass** (`passed_prefill_speedup_floor` true, 1.9570 vs floor 0.95) |
| semantic GPQA | pass, 9/9 (`claude-opus-4-8`) |
| TTFT | pass, 9/9; p50 0.073 s, max 2.4 s, reported 0.41 s |
| peak RAM | 21 GB (`process_resident_memory_gb` 0.11, `bandwidth_gb_per_token` 0) |
| status / rejectionReason | `rejected` — "score did not improve current best" |
| renormalised rank | 238 of 1,033 scored receipts |

No control arm was included in this receipt; the control is the earlier
independent receipt `c3ce66e` named in the pre-registration.

## Verdict against the pre-registered bands

**REFUTE.** Δ`ns` = **−1.608%**, which is below the pre-registered refutation
threshold of `Δ <= 0.00%`. The pre-registered point prediction was **+1.25%**
(interval +1.05% to +1.50%); the ranked M5 delivered a regression of the same
order in the opposite direction. The receipt is valid, not invalid: correctness
passed with `max_abs_diff = 0`, and both hard floors passed, so the negative
result is a real measurement of the treatment and not a gate failure.

- Confirm: Δ`ns` >= +0.52% — not met.
- Refute: Δ`ns` <= 0.00% — **met (−1.608%)**.
- Indeterminate: 0.00% < Δ`ns` < +0.52% — not applicable.
- Invalid: `max_abs_diff != 0`, any hidden-gate failure, or either floor
  verdict failing — none occurred.

### Sub-hypothesis

The pre-registration also predicted the decomposition `T` down and `S` flat.
Both halves are wrong, and `S` is the larger miss:

| axis | prereg | measured | outcome |
| --- | --- | --- | --- |
| `T` (decode-only ms/step) | down ~1.8% | **+1.316%** | sign inverted |
| `S` (512-token prefill ms) | flat | **+2.193%** | not flat, and the larger regression |

**Corrected score decomposition.** An earlier version of this file weighted the
*percent* changes of `S` and `T` by 0.25/0.75, which is wrong: `S` and `T` have
very different absolute scales, so the split has to be done in milliseconds
using the frontier sensitivities. With `D = 5.046441` ms/token and
`S = 97.9497` ms at the control point,

```text
d ln ns / dT = -0.75 / D                    = -0.75 / 5.046441        = -0.148620 per ms
d ln ns / dS = -0.25 / S - 0.75 / (128 * D) = -0.0025523 - 0.0011611  = -0.0037134 per ms
```

so one millisecond of decode `T` is worth 14.862% of score, one millisecond of
prefill `S` is worth 0.371%, and one decode millisecond equals 40.0 prefill
milliseconds. Applying these to the measured shifts:

| axis | Δ (ms) | sensitivity (per ms) | score cost |
| --- | --- | --- | --- |
| `T` | +0.056335 | −0.148620 | **−0.837%** |
| `S` | +2.1476 | −0.0037134 | **−0.797%** |
| sum | | | **−1.634%** |

The exact log delta is `ln(2.503448 / 2.544360) = −1.621%`, so the linearisation
is accurate to 0.013 points. Decode and prefill each cost about 0.8 points: the
regression is **not** decode-dominated, which is the opposite of what the
weight-only split implied.

### Acceptance-band check (hand-computed)

`emitLocalAcceptanceBandNotice` is gone, but `tolerances`, `Score.swift` and four
test files still enforce decode `[0.980, 1.053]` and prefill `[0.952, 1.053]`, so
the team rule is that any arm whose predicted decode or prefill speedup exceeds
1.04 must carry this arithmetic. Doing it for this arm:

| quantity | value | band | inside? |
| --- | --- | --- | --- |
| predicted decode speedup | `1 / (1 − 0.0197) = 1.0201` | `[0.980, 1.053]` | yes |
| predicted prefill speedup | `≈ 1.000` (M4 prefill wall flat, 0.6% range, n=1) | `[0.952, 1.053]` | yes |
| measured decode ratio | `5.046441 / 5.1195537 = 0.9857` | `[0.980, 1.053]` | yes |
| measured prefill ratio | `191.308 / 195.5025 = 0.9785` | `[0.952, 1.053]` | yes |

The predicted decode speedup of 1.0201 is well under the 1.04 trigger, so no
band risk existed before submission, and the measured ratios also sit inside
both bands. No legacy band verdict could have masked or distorted this result.
The published paired `decode_speedup = 2.7038` and `prefill_speedup = 1.9570`
are candidate-versus-baseline figures, a different quantity from these
band ratios; they matter only for the two `0.95` floors, which both pass.

### Is the regression a slow-session artefact?

The paired baseline prefill for this session sits at the 88.7th percentile, so
the obvious objection is that the host was simply in a slow-prefill state and
`cand_pre` inherited it. Across all 1,033 scored receipts the correlation
between candidate and same-session baseline timings is **negative and near
zero** — `corr(cand_pre, base_pre) = −0.104`, `corr(cand_dec, base_dec) =
−0.111` — so a slow baseline does not predict a slow candidate, which is the
premise the pinned-baseline renormalisation rests on. Combined with the
previously measured pooled dispersion of repeated identical-tree receipts
(`ns` cv 0.149%, `T` 0.222%, `S` 0.174%), the observed shifts are roughly
11 σ on `ns`, 6 σ on `T` and 13 σ on `S`. The regression is a treatment
effect, not session noise.

The one caveat worth stating plainly: both the candidate and the control are
n=1 ranked receipts. The dispersion figures come from earlier repeated
receipts on this benchmark, not from repeats of these two trees.
