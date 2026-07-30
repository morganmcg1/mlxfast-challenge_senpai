# Quick-panel question manifests

These files freeze the routine `quick` questions. Change them only with a new
full-model baseline.

- MMLU-Pro retains the original 9/20 mixed pass/fail panel.
- GPQA retains the original nine questions but uses choice-shuffle seed `2`,
  giving a balanced `A=2, B=2, C=2, D=3` target distribution.
- AIME contains nine fixed problems, three from each configured contest.
- GSM8K contains six fixed problems: three baseline passes and three misses.
- `quick_prompt_contract.json` pins the exact prompt-set digest produced for
  each evaluator.

The manifests are regression instruments, not claims about benchmark accuracy.
Every evaluator records prompt hashes and fails if a requested ID is absent or
duplicated. AIME and GSM8K also preserve manifest order; MMLU-Pro and GPQA use
their frozen upstream dataset order.
