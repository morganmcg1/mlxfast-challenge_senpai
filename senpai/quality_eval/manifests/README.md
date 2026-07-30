# Quick-panel question manifests

These files freeze the routine `quick` questions. Change them only with a new
full-model baseline.

- MMLU-Pro retains the original 9/20 mixed pass/fail panel.
- GPQA retains the original nine questions but uses choice-shuffle seed `2`,
  giving a balanced `A=2, B=2, C=2, D=3` target distribution.
- AIME retains one problem from each configured contest.
- GSM8K was selected once from a deterministic 100-question calibration:
  three easy passes, three medium passes, three harder passes, and three
  naturally completed misses. The untouched model scored 9/12.

The manifests are regression instruments, not claims about benchmark accuracy.
Every evaluator preserves canonical dataset order, records prompt hashes, and
fails if a requested ID is absent or duplicated.
