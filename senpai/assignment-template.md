# Experiment Assignment Template

Use this before a student branch starts. Keep submitted candidate paths
separate from research-only tests, scripts, and notes.

- Student / PR:
- Full `BASE_SHA`:
- Host and memory profile:
- One causal hypothesis:
- Scored cost and expected direction:
- Scored call-path proof:
- Submitted candidate paths:
- Research-only support paths:
- Runtime-effective JIT/AOT source and `_nax` variant, if relevant:
- Numerical or protocol risk:
- Cheapest decisive test:

## Required preflight

Run these from a clean checkout of the recorded base, replacing the example
paths with every proposed submitted path:

```bash
senpai/validate-assignment-scope.sh "$BASE_SHA" \
  Sources/MLXFastModel/Example.swift
senpai/check-editable-budget.sh "$BASE_SHA"
```

The first command reads `benchmark.json` from `BASE_SHA`, never from the
working tree. The second checks the current editable surface against the hard
3,000,000-byte total, 524,288-byte per-file, and 262,144-byte growth caps.

Before timing a selector, prove that it reaches the scored input shape and
effective kernel. Before reporting an upstream-equivalence result, use:

```bash
research/run_upstream_equivalence.sh
```

The exact bare filter is
`lagunaRuntimeMatchesVendoredUpstreamOnM5WhenEnabled`. A command that selects
zero tests is not a pass.

## Authority boundary

- The student may edit, test, commit, push, and report the assigned branch.
- Only the advisor or human operator may dispatch an official submission.
- An authorized campaign role may dispatch from a provisioned AWS host, but
  must never print or commit its submission credentials.
- Every official Senpai submission must first use
  `mlxfast submit --model "senpai"`. Only if the API explicitly rejects
  `senpai` as an invalid or unsupported model value may the same candidate be
  retried once with the exact underlying provider/model name. Never fall back
  for a timeout, network error, validation failure, or unrelated error because
  the first submission may already exist. Record the actual provider/model and
  reasoning effort in the public note, plus the explicit rejection if a
  fallback was required.
- Documentation-only work does not change the submitted archive or require a
  new baseline. Keep the recorded base fixed until a promoted editable-path
  change actually advances the frontier.
