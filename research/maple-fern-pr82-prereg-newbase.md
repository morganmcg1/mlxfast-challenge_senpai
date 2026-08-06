# Pre-registered new-base (f2fedd58) screen — PR82

Written before any new-base timing number was read.

## Arms
- **B** = unchanged base, detached at `f2fedd584e6514569758d79e581402210306e77b`
- **C** = candidate, `maple-fern/routed-qmv-router-dedup` @ `352e5f26`

Arms are labelled *post hoc by `harness_hash`*, never by intent (old-base
seq2 position 4 was mis-armed because `benchmark.sh` builds inside the
supervised process and a post-launch `git checkout` raced the build).

## Sequence
| run | role | arm |
| --- | --- | --- |
| 0 | correctness certificate + thermal warm-up, **excluded from timing** | C |
| nb1.1 | timed | B |
| nb1.2 | timed | C |
| nb1.3 | timed | C |
| nb1.4 | timed | B |
| nb2.1 | timed | C |
| nb2.2 | timed | B |
| nb2.3 | timed | B |
| nb2.4 | timed | C |

Position-balanced within each sequence and mirrored across the two, so
every arm occupies each of positions 1-4 exactly once across the screen.

## Decision rule (per programme law §0.9.32)
Both arms are certified bit-identical (`max_abs_diff == 0`, identical
`golden_hash`). Timing is therefore **context, not the claim**. The screen
answers one question only — the advisor's register-pressure question:

> did #72's extra patch-select registers create a spill boundary that the
> prelude deletion now falls off?

- **Null (predicted):** `|pooled decode_gain - 1|` is not larger than the
  measured within-arm A/A spread from the same session. Conclusion: no
  spill interaction; the old-base verdict (weight-bandwidth-bound, ALU
  reductions do not pay) carries over to the new base.
- **Positive:** pooled `decode_gain` exceeds the measured A/A spread and the
  same sign appears in both sequences independently. Conclusion: #72 moved
  the kernel to a register cliff and the deletion now pays — a real finding
  to escalate.
- **Negative:** symmetric, and would be equally reportable.

No fixed no-harm band is used. §0.9.32 withdrew the constant band in the
brief as a stop condition; the comparator is the measured spread.
