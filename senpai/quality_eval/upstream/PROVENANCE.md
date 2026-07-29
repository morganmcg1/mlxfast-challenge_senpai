# Evaluator provenance

All six Python files were imported from
[`morganmcg1/gemma-challenge-senpai`](https://github.com/morganmcg1/gemma-challenge-senpai).
`PROVENANCE.json` additionally records the pristine SHA-256 for every source.

| Local file | Exact source commit | Source path | Git blob |
| --- | --- | --- | --- |
| `run_eval.py` | `63616f139becd76a8cae191e1845e04920a243ea` | `research/validity/downstream_quality_eval/run_eval.py` | `365d880f326ba95d0b181003140252102783443b` |
| `aime_eval.py` | `1bb8f4747b12300199e57aac2b4cd31f4f74ec49` | `research/downstream_quality_aime/aime_eval.py` | `728af3176fbac47d7ad7a19cfc56c33fcc47d340` |
| `gsm8k_eval.py` | `8c61cd30752ca516a7d2ab0d2373be0cbdbd1bb3` | `research/downstream_quality_gsm8k/gsm8k_eval.py` | `22e68d5165514dc13333ca332728df54ce5e3eff` |
| `ppl_endpoint.py` | `7ce30a52eec3104457959a0106e9d0e933f32d76` | `official/main_bucket/shared_resources/speed_benchmark/scripts/ppl_endpoint.py` | `72a2d4fca8b904a71001cd1e5972e45573dff934` |
| `check_prompt_sets.py` | `7ce30a52eec3104457959a0106e9d0e933f32d76` | `research/readme_quality_refresh_20260621/check_prompt_sets.py` | `3e55781f5f03957f5a6949d42930956ed71cb7e6` |
| `summarize_five_pass.py` | `7ce30a52eec3104457959a0106e9d0e933f32d76` | `research/readme_quality_refresh_20260621/summarize_five_pass.py` | `2eff2eeea35a6fa2ffe26c166effa4d62637097d` |

The three `main` imports above were resolved against local `main` at
`7ce30a52eec3104457959a0106e9d0e933f32d76`. The PPL source itself was last
changed by `bce393cc52cf82585597d7791325ec0856c98faf`.

Local adaptations preserve dataset construction and scoring:

- the default served name is `laguna-xs-2.1`;
- AIME and GSM8K are endpoint-only and retain raw completions by default;
- MMLU-Pro/GPQA output includes each raw completion;
- all downstream outputs include a deterministic aggregate over their evaluated
  `(id, prompt_sha)` set; AIME and GSM8K item hashes cover the exact endpoint
  messages plus the gold answer;
- the prompt-set checker validates whichever of MMLU-Pro, GPQA-Diamond, AIME,
  and GSM8K are present, requiring each present task in every compared directory;
- MMLU-Pro, GPQA, and GSM8K retain request-error diagnostics but exit nonzero
  when any item request fails; MMLU-Pro/GPQA also reject incomplete sample
  sets, so request failures cannot be accepted as quality scores;
- profile-driven runs enforce exact MMLU-Pro, GPQA-Diamond, AIME, and GSM8K
  cardinalities, and GSM8K also enforces its requested few-shot count;
- PPL output retains token IDs, score boundaries, and scored log-probabilities;
- PPL sends its score boundaries to the Laguna adapter as a performance hint,
  without changing the official token-weighted perplexity equation, while
  rejecting non-finite values and unexpected manifest sizes;
- the summarizer reports the additive ranked-head GPQA greedy behavior proxy
  separately from the historical full-logit greedy metric.
