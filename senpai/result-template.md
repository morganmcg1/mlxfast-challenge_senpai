# Autoresearch Result Template

Use this only for a terminal result. Never infer an unmeasured score.

## Machine-readable marker

Begin with exactly one single-line marker:

```text
SENPAI-RESULT: {"terminal":true,"status":"complete","pending_arms":false,"wandb_run_ids":[],"primary_metric":{"name":"same_host_paired_estimate","available":true,"value":1.0123},"test_metric":{"name":"passed_correctness","available":true,"value":1}}
```

`terminal` means this arm will not resume. `status` means the report is
complete, not that the candidate won. Set `pending_arms` only when assigned
arms remain. Use only real run IDs. For either metric, use
`"available":false,"value":null` when no valid measurement exists; never use
numeric zero as a missing-value sentinel. A measured correctness failure is
available with value `0`.

- Student / PR:
- Hypothesis and target cost:
- Decision: green, ambiguous, invalid candidate, or dead hypothesis
- `BASE_SHA` / candidate commit:
- Submitted candidate files:
- Supporting test or documentation files:
- Underlying agent provider/model and reasoning effort:
- Official submission `--model` value (planned or used; default `senpai`):
- Explicit API model-value rejection, if fallback attribution was required:
- Assignment-scope preflight:
- Editable bytes / headroom / growth:
- Scored-path reachability evidence:

### Evidence

- Host, memory profile, toolchain, and thermal policy:
- Exact baseline and candidate commands:
- Tests and risk-based checks run, including selected-test count:
- Correctness and serial-protocol verdict:
- Divergent tokens or failure category, if any:
- Peak RAM or generated-weight size, if relevant:
- Official ranking status versus correctness/floor status, if submitted:

| Metric | Baseline | Candidate | Ratio / delta |
| --- | ---: | ---: | ---: |
| decode seconds/token | ... | ... | ...x |
| prefill seconds/token | ... | ... | ...x |
| same-host paired estimate | — | ... | — |

The paired estimate is a same-host research metric, not an official M5 score.

### Conclusion

- What happened and why:
- Evidence for or against the mechanism:
- Uncertainty or M5 transfer risk:
- Smallest useful next action:
- Recommendation: merge, repeat, revise, or close
