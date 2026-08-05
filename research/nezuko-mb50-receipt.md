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
| UTC receipt released | _pending_ |
| UTC slot released to advisor | _pending_ |

## Receipt fields

_pending — filled from `mlxfast submissions` once the run is terminal._

| field | value |
| --- | --- |
| `commit` (receipt) | |
| `cand_pre` (µs) | |
| `cand_dec` (ms) | |
| computed `ns` | |
| Δ `ns` vs control 2.544360 | |
| `S` (ms) | |
| `T` (ms) | |
| officialScore | |
| `draw` = officialScore / `ns` | |
| paired-baseline prefill µs (percentile) | |
| `max_abs_diff` | |
| decode floor verdict | |
| prefill floor verdict | |
| semantic GPQA | |
| TTFT | |
| peak RAM | |

## Verdict against the pre-registered bands

_pending._

- Confirm: Δ`ns` >= +0.52%
- Refute: Δ`ns` <= 0.00%
- Indeterminate: 0.00% < Δ`ns` < +0.52% (no win claim, no promotion ask,
  a second receipt would be required)
- Invalid: `max_abs_diff != 0`, any hidden-gate failure, or either floor
  verdict failing
