# Autoresearch Result Template

Load this file only when an experiment reaches a terminal result. Report
measured facts and uncertainty; never infer an unmeasured score.

## Machine-readable marker

The result must begin with exactly one single-line marker:

```text
SENPAI-RESULT: {"terminal":true,"status":"complete","pending_arms":false,"wandb_run_ids":[],"primary_metric":{"name":"local_paired_score_estimate","value":1.0123},"test_metric":{"name":"passed_correctness","value":1}}
```

Use `passed_correctness: 1` for a passing local gate and `0` otherwise. If no
valid timing exists, use a truthful sentinel such as `0` for the primary metric
and explain the no-result immediately below. Keep `wandb_run_ids` empty unless
orchestration separately recorded a real external run.

## Result

### Identity

- Student:
- PR:
- Question or hypothesis:
- Target cost and prior evidence:
- Decision: green, ambiguous, invalid candidate, or dead hypothesis

### Reproducibility

- `BASE_SHA`:
- Candidate commit:
- Submitted candidate files:
- Supporting test/documentation files:
- Mac model and chip generation:
- Unified memory and startup memory profile:
- macOS, Xcode, and Swift versions:
- Exact baseline and candidate commands:
- Measurements completed:
- Thermal gate and fan policy:

### Validation

- Tests run:
- `passed`:
- `passed_correctness`:
- Checked steps and divergent tokens, if any:
- Serial-protocol verdict:
- Stronger risk-based quality checks, if required:
- Peak RAM:
- Generated weights byte count, if relevant:

### Performance

| Metric | Baseline | Candidate | Ratio / delta |
| --- | ---: | ---: | ---: |
| decode seconds/token | ... | ... | ...x |
| prefill seconds/token | ... | ... | ...x |
| local estimated score | ... | ... | ... |
| passed correctness | ... | ... | — |
| peak RAM GB | ... | ... | ... |

Report both component metrics. Compute the same-host research estimate as:

```text
decode_gain = baseline.decode_seconds_per_token / candidate.decode_seconds_per_token
prefill_gain = baseline.prefill_seconds_per_token / candidate.prefill_seconds_per_token
paired_estimate = decode_gain^0.75 * prefill_gain^0.25
```

This is not the official M5 score.

### Interpretation

- What happened:
- Most likely mechanism:
- Evidence that supports or contradicts the hypothesis:
- Caveats, including M5 transfer risk:
- Suggested follow-ups:
- Recommendation: merge, repeat, revise, or close

## Decision meanings

- **Green:** valid and repeatably faster end to end, with acceptable component
  and transfer risk.
- **Ambiguous:** the smallest useful follow-up could still change the decision.
- **Invalid candidate:** this implementation cannot be promoted because of a
  correctness, protocol, memory, build, or submitted-surface failure; state
  whether a compliant implementation remains plausible.
- **Dead hypothesis:** its measured or bounded economics no longer justify more
  work, or a valid implementation has no repeatable gain.

Negative and no-result reports are first-class research assets. Name the
failure category—correctness, serial validity, build feasibility, memory,
hardware transfer, infrastructure, measurement noise, or lack of end-to-end
speed—and preserve the evidence needed to avoid repeating it.
