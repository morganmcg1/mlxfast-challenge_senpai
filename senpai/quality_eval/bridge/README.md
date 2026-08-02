# Laguna quality bridge

This nested Swift package loads the repository's modified Laguna runtime once
and serves synchronous JSONL requests:

```bash
swift build -c release --force-resolved-versions \
  --product laguna-quality-bridge

.build/release/laguna-quality-bridge \
  --weights /path/to/transformed/weights \
  --metallib /path/to/mlx.metallib \
  --full-logits
```

The process writes one ready record before accepting requests:

```json
{"kind":"ready","ok":true,"model":"laguna","vocab_size":100352,"max_position_embeddings":262144}
```

Generation request:

```json
{"id":"g1","kind":"generate","prompt_token_ids":[1,2],"max_tokens":128,"temperature":0,"top_p":1,"top_k":0,"seed":0,"min_tokens":0,"stop_token_ids":[2,24]}
```

Generation response:

```json
{"id":"g1","ok":true,"token_ids":[42],"finish_reason":"stop"}
```

Teacher-forced logprob request (`score_end` is exclusive and defaults to the
prompt length):

```json
{"id":"p1","kind":"logprobs","prompt_token_ids":[1,2,3],"score_start":1,"score_end":3}
```

The response has one `token_logprobs` value for each token in
`score_start..<score_end`. Each value is `log P(token[i] | token[..<i])`.

```json
{"id":"p1","ok":true,"token_logprobs":[-1.25,-0.5]}
```

Malformed or invalid requests remain in-band:

```json
{"id":"bad","ok":false,"error":"prompt_token_ids must not be empty"}
```

stdout is reserved for JSONL. Load progress and diagnostics go to stderr.
`--full-logits` forces `DARKBLOOM_LM_HEAD_PRUNE=0` before model
initialization. That retains the candidate's batch-one model/KV path while
using the full BF16 vocabulary head required for probability-correct sampling,
stop masking, and prompt log probabilities. Without the flag, the submitted
ranked head is used and the bridge accepts only unmasked greedy generation;
sampling, positive `min_tokens`, and logprob requests fail explicitly.
