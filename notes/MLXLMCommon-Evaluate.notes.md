# Relocated commentary — `Evaluate.swift`

Measurement narrative and design history moved verbatim out of `Vendor/mlx-swift-lm/Libraries/MLXLMCommon/Evaluate.swift`
to free bytes on the capped editable submission surface. Line numbers refer to
the file as it stood at base `e1d070f2`. Nothing here is compiled or
submitted, and the code is unchanged (see
`research/frieren_comment_strip_check.sh`).

## `line1`

_relocated from lines 1-1 at base e1d070f2_

Copyright © 2024 Apple Inc.

## `LogitSampler`

_relocated from lines 7-10 at base e1d070f2_

A `LogitSampler` is responsible for sampling `logits` produced by
a ``LanguageModel`` to produce a token.

See also: ``LogitProcessor``

## `sample`

_relocated from lines 13-13 at base e1d070f2_

Given `logits` produce a new `MLXArray` with the token.

## `LogitProcessor`

_relocated from lines 17-33 at base e1d070f2_

A `LogitProcessor` is an optional visitor of `logits`.

The ``LogitProcessor`` is called with the input (prompt) before generating tokens:

```swift
processor?.prompt(input.text.tokens)
```

Then for each token generated it has a chance to adjust the logits:

```swift
logits = processor?.process(logits: logits) ?? logits
let y = sampler.sample(logits: logits)
processor?.didSample(token: y)
```

See also: ``LogitSampler``

## `prompt`

_relocated from lines 36-36 at base e1d070f2_

Called before token generation starts with the text tokens of the prompt

## `process`

_relocated from lines 39-39 at base e1d070f2_

Called to visit and possibly modify the logits

## `didSample`

_relocated from lines 42-42 at base e1d070f2_

Called to provide the sampled token

## `GenerateParameters`

_relocated from lines 46-53 at base e1d070f2_

Parameters for text generation, see ``TokenIterator``.

This produces:

- ``LogitSampler``
- ``LogitProcessor``

for the `TokenIterator`.

## `prefillStepSize`

_relocated from lines 56-56 at base e1d070f2_

Step size for processing the prompt

## `maxTokens`

_relocated from lines 59-59 at base e1d070f2_

Maximum tokens to generate

## `maxKVSize`

_relocated from lines 62-63 at base e1d070f2_

Maximum size of the key-value cache. Old entries (except the first 4 tokens) will be overwritten.
When set, uses ``RotatingKVCache`` instead of ``KVCacheSimple``

## `kvBits`

_relocated from lines 66-66 at base e1d070f2_

Number of bits to use for KV cache quantization. nil implies no cache quantization.

## `kvGroupSize`

_relocated from lines 69-69 at base e1d070f2_

Group size for KV cache quantization (default: 64)

## `quantizedKVStart`

_relocated from lines 72-72 at base e1d070f2_

Step to begin using a quantized KV cache when kvBits is non-nil (default: 0)

## `temperature`

_relocated from lines 75-75 at base e1d070f2_

Sampling temperature

## `topP`

_relocated from lines 78-78 at base e1d070f2_

Top-p sampling

## `topK`

_relocated from lines 81-81 at base e1d070f2_

Top-k sampling (0 disables)

## `minP`

_relocated from lines 84-84 at base e1d070f2_

Min-p sampling threshold relative to the highest probability token (0 disables)

## `repetitionPenalty`

_relocated from lines 87-87 at base e1d070f2_

Penalty factor for repeating tokens

## `repetitionContextSize`

_relocated from lines 90-90 at base e1d070f2_

Number of tokens to consider for repetition penalty

## `presencePenalty`

_relocated from lines 93-93 at base e1d070f2_

additive penalty for tokens that appear in recent context

## `presenceContextSize`

_relocated from lines 96-96 at base e1d070f2_

number of tokens to consider for presence penalty

## `frequencyPenalty`

_relocated from lines 99-99 at base e1d070f2_

additive penalty that scales with token frequency in recent context

## `frequencyContextSize`

_relocated from lines 102-102 at base e1d070f2_

number of tokens to consider for frequency penalty

## `repetitionPenalty`

_relocated from lines 157-158 at base e1d070f2_

1 is the identity (logits are ×/÷ by it), so skip it like "unset" —
clients commonly send repetition_penalty: 1 by default.

## `ArgMaxSampler`

_relocated from lines 202-202 at base e1d070f2_

Sampler that uses `argMax` (most likely) to sample the logits.

## `TopPSampler`

_relocated from lines 211-217 at base e1d070f2_

Sampler that uses probability filters (`topP`, `topK`, `minP`) and `temperature`
to sample the logits.

Filters are applied in the same order as Python mlx-lm: top_p → min_p → top_k.
Each filter operates on the full vocabulary in original token order, masking
rejected tokens with `-inf`. This matches the composable filter chain in
`mlx_lm.sample_utils.make_sampler`.

## `topP`

_relocated from lines 248-248 at base e1d070f2_

Apply filters in Python mlx-lm order: top_p → min_p → top_k.

## `applyTopP`

_relocated from lines 263-264 at base e1d070f2_

Keep tokens whose cumulative probability exceeds `1 - topP` (nucleus sampling).
Matches `apply_top_p` from `mlx_lm/sample_utils.py`.

## `filtered`

_relocated from lines 271-271 at base e1d070f2_

Mask low-probability tail in sorted order, scatter back to original vocab order.

## `applyMinP`

_relocated from lines 276-277 at base e1d070f2_

Keep tokens with probability >= maxProb * minP.
Matches `apply_min_p` from `mlx_lm/sample_utils.py`.

## `maxLogprob`

_relocated from lines 279-279 at base e1d070f2_

threshold in log-space: log(maxProb * minP) = maxLogprob + log(minP)

## `applyTopK`

_relocated from lines 285-286 at base e1d070f2_

Keep only the top-k highest-probability tokens.
Mirrors `apply_top_k` from `mlx_lm/sample_utils.py`.

## `maskIndices`

_relocated from lines 290-291 at base e1d070f2_

O(V) partition on negated logprobs so top-k land at [0, topK).
Indices at [topK, V) are the tokens to mask out.

## `CategoricalSampler`

_relocated from lines 297-297 at base e1d070f2_

Sampler that uses `temperature` to sample the logits.

## `TokenRing`

_relocated from lines 314-318 at base e1d070f2_

GPU-resident ring buffer of recent token IDs.

Shared by penalty processors to avoid duplicating ring buffer logic.
Uses `MLX.where` mask operations for GPU-only updates (no CPU←GPU sync),
preserving `asyncEval()` pipelining in `TokenIterator`.

## `validTokens`

_relocated from lines 333-333 at base e1d070f2_

The valid portion of the ring (all of it once full), or `nil` if empty.

## `loadPrompt`

_relocated from lines 339-344 at base e1d070f2_

Bulk-load from a prompt, keeping the last `capacity` tokens.

Flatten to 1-D first: the VLM path passes a 2-D `[1, seq]` token array, so
`prompt.dim(0)` would read the batch size (1), not `seq` — mis-sizing the
buffer and crashing a later `append` with an MLX broadcast error on any
image request carrying a penalty. 1-D prompts are unaffected (no-op reshape).

## `append`

_relocated from lines 364-364 at base e1d070f2_

Append a single token using GPU-only mask write (no CPU←GPU sync).

## `RepetitionContext`

_relocated from lines 373-373 at base e1d070f2_

Processor that implements a `repetitionPenalty`.

## `PresencePenaltyContext`

_relocated from lines 404-407 at base e1d070f2_

Processor that applies an additive presence penalty to tokens in a recent context window.

The penalty is applied once per unique token via scatter-write (writing the
same value to the same index multiple times is idempotent).

## `FrequencyPenaltyContext`

_relocated from lines 432-435 at base e1d070f2_

Processor that applies an additive frequency penalty to tokens in a recent context window.

Frequency counting is performed on GPU via `scatter_add` to build a histogram
of token occurrences, avoiding CPU←GPU synchronization.

## `PenaltyProcessor`

_relocated from lines 465-465 at base e1d070f2_

Processor that composes penalty processors in Python mlx-lm order.

## `TokenIteratorProtocol`

_relocated from lines 502-505 at base e1d070f2_

Common properties shared by token-generating iterators.

Public so model-specific iterators outside `MLXLMCommon` can plug into
the shared generation loop.

## `TokenIterator`

_relocated from lines 512-534 at base e1d070f2_

Generator of tokens.

This is typically used via a call to ``generate(input:cache:parameters:context:wiredMemoryTicket:)`` returning `AsyncStream<Generation>`.

To use it directly:

```swift
let generateParameters: GenerateParameters
let input: LMInput
let model: LanguageModel

let iterator = try TokenIterator(input: input, model: model, parameters: generateParameters)

for token in iterator {
    ...
}
```

Tokens are integers that can be passed through a `Tokenizer` or ``StreamingDetokenizer`` to produce Strings.

Port of `generate_step()` from https://github.com/ml-explore/mlx-examples/blob/main/llms/mlx_lm/utils.py

Note: this uses `asyncEval()` and there may be an async evaluation running after a call to `next()`.

## `kvBits`

_relocated from lines 547-547 at base e1d070f2_

Cache quantization parameters

## `promptPrefillTime`

_relocated from lines 552-552 at base e1d070f2_

Internal metrics

## `line562`

_relocated from lines 555-562 at base e1d070f2_

Initialize a `TokenIterator` with the given tokens. Note: this has been
replaced with ``init(input:model:cache:parameters:)``.

- Parameters:
  - prompt: the prompt tokens
  - model: the ``LanguageModel``
  - cache: optional ``KVCache``
  - parameters: the generation parameters

## `line596`

_relocated from lines 585-596 at base e1d070f2_

Initialize a `TokenIterator` with the given input.

If more control is needed over the generation,
``init(input:model:cache:processor:sampler:prefillStepSize:maxTokens:)``
allows a caller to specify ``LogitProcessor`` and ``LogitSampler``
directly.

- Parameters:
  - input: language model input
  - model: the ``LanguageModel``
  - cache: optional ``KVCache``
  - parameters: the generation parameters

## `line627`

_relocated from lines 618-627 at base e1d070f2_

Initialize a `TokenIterator` with the given input and logit handling.

- Parameters:
  - input: language model input
  - model: the ``LanguageModel``
  - cache: optional ``KVCache``
  - processor: the logit processor
  - sampler: the logit sampler
  - prefillStepSize: optional prefill step size
  - maxTokens: maximum number of tokens to generate

## `line641`

_relocated from lines 641-641 at base e1d070f2_

No cache quantization for this direct initialization

## `token`

_relocated from lines 658-658 at base e1d070f2_

evaluate the remainder of the prompt -- this primes the pump

## `logits`

_relocated from lines 672-672 at base e1d070f2_

process the logits (one hot array of possible tokens)

## `y`

_relocated from lines 676-676 at base e1d070f2_

transform logits back to a token

## `step`

_relocated from lines 684-684 at base e1d070f2_

Evaluate the next token and return the new token (y), updating cache state

## `line690`

_relocated from lines 690-690 at base e1d070f2_

Apply dynamic cache quantization after each step

## `previousY`

_relocated from lines 706-706 at base e1d070f2_

save current value -- this will be returned

## `token`

_relocated from lines 709-709 at base e1d070f2_

compute the next state and async eval the next token

## `SpeculativeTokenIterator`

_relocated from lines 720-744 at base e1d070f2_

Generator of tokens using speculative decoding.

This is typically used via a call to ``generate(input:cache:parameters:context:draftModel:draftCache:numDraftTokens:wiredMemoryTicket:)``
returning `AsyncStream<Generation>`.

To use it directly:

```swift
let generateParameters: GenerateParameters
let input: LMInput
let mainModel: LanguageModel
let draftModel: LanguageModel

let iterator = try SpeculativeTokenIterator(
    input: input, mainModel: mainModel, draftModel: draftModel,
    parameters: generateParameters, numDraftTokens: 2)

for token in iterator {
    ...
}
```

Tokens are integers that can be passed through a `Tokenizer` or ``StreamingDetokenizer`` to produce Strings.

Port of `speculative_generate_step()` from https://github.com/ml-explore/mlx-lm/blob/main/mlx_lm/generate.py

## `pendingTokens`

_relocated from lines 765-765 at base e1d070f2_

Buffer of accepted tokens from the current speculation round

## `promptPrefillTime`

_relocated from lines 769-769 at base e1d070f2_

Internal metrics

## `line781`

_relocated from lines 772-781 at base e1d070f2_

Initialize a `SpeculativeTokenIterator` with the given input.

- Parameters:
  - input: language model input
  - mainModel: the main (verifier) ``LanguageModel``
  - draftModel: the draft ``LanguageModel`` (must share the same tokenizer)
  - mainCache: optional ``KVCache`` for the main model
  - draftCache: optional ``KVCache`` for the draft model
  - parameters: the generation parameters
  - numDraftTokens: number of tokens the draft model proposes per round

## `prepare`

_relocated from lines 822-822 at base e1d070f2_

Prefill both main and draft models with the prompt, priming caches for generation

## `tokens`

_relocated from lines 826-826 at base e1d070f2_

Prefill main model

## `tokens`

_relocated from lines 839-839 at base e1d070f2_

Prefill draft model, don't call didSample here -- processor tracks main model's accepted sequence only

## `speculateRound`

_relocated from lines 852-852 at base e1d070f2_

Run one round of speculative decoding: draft, verify, accept/reject

## `draftProcessor`

_relocated from lines 860-860 at base e1d070f2_

Draft generation: autoregressive loop with draft model

## `verifyTokens`

_relocated from lines 874-874 at base e1d070f2_

Verification: main model processes proposals in one pass

## `sampled`

_relocated from lines 884-884 at base e1d070f2_

Process each position sequentially so that the processor sees tokens sampled at earlier positions

## `verifyLogits`

_relocated from lines 895-895 at base e1d070f2_

Batch-sample all verify tokens from main model in one operation

## `mainTokensList`

_relocated from lines 900-900 at base e1d070f2_

Compare and accept proposed tokens

## `finalToken`

_relocated from lines 915-916 at base e1d070f2_

Always emit the main model's token at position `accepted`
(either the correction token or the bonus token if all drafts matched)

## `line921`

_relocated from lines 921-921 at base e1d070f2_

Rewind caches for rejected tokens

## `line925`

_relocated from lines 925-925 at base e1d070f2_

Apply dynamic cache quantization after rewind

## `line929`

_relocated from lines 929-929 at base e1d070f2_

Set y/draftY for the next round

## `line934`

_relocated from lines 933-934 at base e1d070f2_

If all draft tokens were accepted, the draft model hasn't processed
the last accepted draft token yet. Feed it through to keep caches in sync.

## `token`

_relocated from lines 950-950 at base e1d070f2_

Drain the pending buffer first

## `line958`

_relocated from lines 958-958 at base e1d070f2_

Run a new speculation round

## `GenerateResult`

_relocated from lines 974-974 at base e1d070f2_

Result of a call to a deprecated callback-based generate function.

## `line984`

_relocated from lines 977-984 at base e1d070f2_

Initializes a new `GenerateResult` instance.

- Parameters:
  - inputText: The input text used for generation.
  - tokenIds: The array of generated token IDs.
  - output: The generated output string.
  - promptTime: The time taken to prompt the input.
  - generateTime: The time taken to generate the output.

## `inputText`

_relocated from lines 1006-1006 at base e1d070f2_

input (prompt, images, etc.)

## `promptTokenIds`

_relocated from lines 1009-1009 at base e1d070f2_

The token IDs of the input prompt.

## `tokenIds`

_relocated from lines 1017-1017 at base e1d070f2_

Generated token IDs

## `output`

_relocated from lines 1023-1023 at base e1d070f2_

Output text

## `promptTokenCount`

_relocated from lines 1026-1026 at base e1d070f2_

The number of tokens included in the input prompt.

## `generationTokenCount`

_relocated from lines 1029-1029 at base e1d070f2_

The number of tokens generated by the language model.

## `promptTime`

_relocated from lines 1032-1032 at base e1d070f2_

Time to process the prompt (generate the first token)

## `generateTime`

_relocated from lines 1035-1035 at base e1d070f2_

Time to generate the remaining tokens

## `promptTokensPerSecond`

_relocated from lines 1038-1038 at base e1d070f2_

The number of tokens processed per second during the prompt phase.

## `tokensPerSecond`

_relocated from lines 1043-1043 at base e1d070f2_

The number of tokens generated per second during the generation phase.

## `GenerateDisposition`

_relocated from lines 1056-1056 at base e1d070f2_

Action from token visitor callback in deprecated callback-based generate functions.

## `line1058`

_relocated from lines 1058-1058 at base e1d070f2_

Keep producing tokens until an EOS token is produced

## `SynchronousGenerationLoopResult`

_relocated from lines 1061-1061 at base e1d070f2_

Stop producing tokens, e.g. a token limit has been hit

## `stopTokenIds`

_relocated from lines 1077-1077 at base e1d070f2_

Build complete EOS token set from all sources.

## `now`

_relocated from lines 1109-1109 at base e1d070f2_

Compute the timing for the prompt.

## `line1116`

_relocated from lines 1116-1116 at base e1d070f2_

Check for end-of-sequence tokens.

## `maxTokens`

_relocated from lines 1130-1130 at base e1d070f2_

If the iterator ends naturally, the max-token limit was reached.

## `line1145`

_relocated from lines 1142-1145 at base e1d070f2_

TokenIterator uses `asyncEval()` to keep the pipeline full. If the caller
exits the program right away, those tasks will still be executing and will
hit assertions as the mlx scheduler is torn down. Synchronize with the stream
to make sure it is complete.

## `generate`

_relocated from lines 1157-1167 at base e1d070f2_

Given prompt tokens generate text using the given model and parameters.

``generate(input:cache:parameters:context:wiredMemoryTicket:)`` returning `AsyncStream<Generation>` is the preferred call.

- Parameters:
  - promptTokens: tokenized prompt
  - parameters: generation parameters
  - model: model to evaluate
  - tokenizer: tokenizer to convert tokens back into strings and recognize special tokens
  - extraEOSTokens: any additional stop tokens
  - didGenerate: visitor for the tokens as they are generated

## `input`

_relocated from lines 1183-1184 at base e1d070f2_

this is a compatibility cover -- create the required values
for the iteration

## `generate`

_relocated from lines 1196-1205 at base e1d070f2_

Generate tokens from an ``LMInput`` and a ``ModelContext``.

Prefer using ``generate(input:cache:parameters:context:wiredMemoryTicket:)`` returning `AsyncStream<Generation>` instead.

- Parameters:
  - input: prepared language model input
  - parameters: parameters controlling the token generation
  - context: model context (model and tokenizer)
  - didGenerate: token visitor that can output tokens as they are generated and indicate early stop
- Returns: the generated output

## `generate`

_relocated from lines 1222-1231 at base e1d070f2_

Low-level token generation using a ``TokenIterator``.

``generate(input:cache:parameters:context:wiredMemoryTicket:)`` returning `AsyncStream<Generation>` is the preferred call.

- Parameters:
  - input: prepared language model input
  - context: model context (model and tokenizer)
  - iterator: token iterator
  - didGenerate: token visitor that can output tokens as they are generated and indicate early stop
- Returns: the generated output

## `generate`

_relocated from lines 1258-1267 at base e1d070f2_

Generate tokens from an ``LMInput`` and a ``ModelContext``.

Prefer using ``generate(input:cache:parameters:context:wiredMemoryTicket:)`` returning `AsyncStream<Generation>` instead.

- Parameters:
  - input: prepared language model input
  - parameters: parameters controlling the token generation
  - context: model context (model and tokenizer)
  - didGenerate: token visitor that can output tokens as they are generated and indicate early stop
- Returns: Information about the generation

## `generate`

_relocated from lines 1284-1293 at base e1d070f2_

Low-level token generation using a ``TokenIterator``.

``generate(input:cache:parameters:context:wiredMemoryTicket:)`` returning `AsyncStream<Generation>` is the preferred call.

- Parameters:
  - input: prepared language model input
  - context: model context (model and tokenizer)
  - iterator: token iterator
  - didGenerate: token visitor that can output tokens as they are generated and indicate early stop
- Returns: Information about the generation

## `generate`

_relocated from lines 1321-1369 at base e1d070f2_

Generates tokens asynchronously using the provided language model input, parameters, and context.

This function initializes a `TokenIterator` with the given input, model, and generation parameters,
and then streams the token generation process via an `AsyncStream`. The resulting stream yields
instances of the `Generation` enum, which can represent text chunks, tool calls, or summary
completion information.

* Important: if the stream is terminated early (e.g. break from the loop) computation will continue
using the model, parameters, KVCache, etc. for some time (typically a few ms).  This is typically OK for
one-shot calls, but for "chat session" type calls consider using
``generateTask(promptTokenCount:modelConfiguration:tokenizer:iterator:wiredMemoryTicket:)``
so that the end of the generation task can be observed.

- Parameters:
  - input: The input for the language model.
  - cache: optional ``KVCache``
  - parameters: The configuration options for token generation.
  - context: The model context, including the model itself and associated tokenizer.
  - wiredMemoryTicket: Optional wired memory ticket for policy-based coordination across
    concurrent tasks. This is opt-in and only applied on GPU devices that support wired
    memory control (macOS 15 / iOS 18 / tvOS 18 or newer).
- Returns: An `AsyncStream` that emits `Generation` values, including generated text chunks (`.chunk`),
  tool calls (`.toolCall`), and completion information (`.info`).
- Throws: An error if the `TokenIterator` initialization fails due to invalid input or model configuration.

### Example Usage:
```swift
// Define the input, parameters, and context for token generation.
let generateParameters: GenerateParameters
let input: UserInput
let context: ModelContext

let lmInput = try context.processor.prepare(input: input)

// Call the generate function to get an AsyncStream.
let stream = try generate(input: lmInput, parameters: generateParameters, context: context)

// Process the stream asynchronously to handle text chunks and completion info.
for await generation in stream {
    switch generation {
    case .chunk(let text):
        print("Generated text: \(text)")
    case .info(let info):
        print("Finished: \(info.tokensPerSecond) tokens/s.")
    case .toolCall(let call):
        print("Tool call: \(call.function.name)")
    }
}
```

## `generate`

_relocated from lines 1385-1429 at base e1d070f2_

Generates text and tool calls asynchronously using speculative decoding with a draft model.

This function uses a smaller draft model to propose tokens that are verified in batch
by the main model, potentially accelerating generation. The resulting stream yields
decoded text chunks, tool calls, and completion information. It has the same output as the
non-speculative ``generate(input:cache:parameters:context:wiredMemoryTicket:)``.

Both models must share the same tokenizer.

### Example Usage:
```swift
let generateParameters: GenerateParameters
let input: UserInput
let mainContext: ModelContext
let draftModel: LanguageModel

let lmInput = try mainContext.processor.prepare(input: input)

let stream = try generate(
    input: lmInput, parameters: generateParameters,
    context: mainContext, draftModel: draftModel)

for await generation in stream {
    switch generation {
    case .chunk(let text):
        print("Generated text: \(text)")
    case .info(let info):
        print("Finished: \(info.tokensPerSecond) tokens/s.")
    case .toolCall(let call):
        print("Tool call: \(call.function.name)")
    }
}
```

- Parameters:
  - input: The input for the language model.
  - cache: optional ``KVCache`` for the main model.
  - parameters: The configuration options for token generation.
  - context: The model context for the main (verifier) model.
  - draftModel: The draft ``LanguageModel`` for speculative token proposals.
  - draftCache: optional ``KVCache`` for the draft model.
  - numDraftTokens: Number of tokens the draft model proposes per round (default: 2).
  - wiredMemoryTicket: Optional wired memory ticket for policy-based coordination.
- Returns: An `AsyncStream` that emits `Generation` values.
- Throws: An error if the iterator initialization fails.

## `generateTask`

_relocated from lines 1481-1494 at base e1d070f2_

Low-level token generation using a ``TokenIterator``, returning an
`AsyncStream<Generation>` and a `Task`.

* Important: if the stream is terminated early (e.g. break from the loop) computation will continue
using the model, parameters, KVCache, etc. for some time (typically a few ms).  Callers can await
the `task` to observe when the use of the parameters is complete.

- Parameters:
  - promptTokenCount: number of tokens in the prompt
  - modelConfiguration: model configuration (for EOS/extra EOS tokens and tool-call format)
  - tokenizer: tokenizer (for EOS id, unknown token id, and detokenization)
  - iterator: token iterator
  - wiredMemoryTicket: Optional wired memory ticket for policy-based coordination.
- Returns: An `AsyncStream` that emits `Generation` values and a `Task`

## `generateTask`

_relocated from lines 1515-1519 at base e1d070f2_

Low-level token generation accepting any ``TokenIteratorProtocol``
conformer.

This mirrors the `TokenIterator` overload while allowing model-specific
iterators to share the standard `AsyncStream<Generation>` output path.

## `generateTokens`

_relocated from lines 1540-1554 at base e1d070f2_

Generates raw token IDs asynchronously using the provided language model input, parameters, and context.

This is similar to `generate(input:cache:parameters:context:)`, but yields raw token IDs instead of decoded text/tool calls.
This is useful for downstream parsers that need access to token IDs directly (e.g. Harmony parsing).

- Parameters:
  - input: The input for the language model.
  - cache: optional ``KVCache``
  - parameters: The configuration options for token generation.
  - context: The model context, including the model itself and associated tokenizer.
  - includeStopToken: when true, the terminating EOS/unknown token is yielded before finishing
  - wiredMemoryTicket: Optional wired memory ticket for policy-based coordination across
    concurrent tasks. This is opt-in and only applied on GPU devices that support wired
    memory control (macOS 15 / iOS 18 / tvOS 18 or newer).
- Returns: An `AsyncStream` that emits `TokenGeneration` values.

## `generateTokens`

_relocated from lines 1576-1593 at base e1d070f2_

Generates raw token IDs asynchronously using speculative decoding with a draft model.

This is similar to `generate(input:cache:parameters:context:draftModel:draftCache:numDraftTokens:wiredMemoryTicket:)`,
but yields raw token IDs instead of decoded text/tool calls.

Both models must share the same tokenizer.

- Parameters:
  - input: The input for the language model.
  - cache: optional ``KVCache`` for the main model.
  - parameters: The configuration options for token generation.
  - context: The model context for the main (verifier) model.
  - draftModel: The draft ``LanguageModel`` for speculative token proposals.
  - draftCache: optional ``KVCache`` for the draft model.
  - numDraftTokens: Number of tokens the draft model proposes per round (default: 2).
  - wiredMemoryTicket: Optional wired memory ticket for policy-based coordination.
- Returns: An `AsyncStream` that emits `TokenGeneration` values.
- Throws: An error if the iterator initialization fails.

## `generateTokensTask`

_relocated from lines 1624-1639 at base e1d070f2_

Generates raw token IDs asynchronously and returns the stream plus a `Task`.

Prefer this overload if you want to be able to observe when the underlying generation work is finished
(especially if the consumer terminates the stream early).

- Returns: An `AsyncStream` that emits `TokenGeneration` values and a `Task`.

- Parameters:
  - input: The input for the language model.
  - cache: optional ``KVCache``
  - parameters: The configuration options for token generation.
  - context: The model context, including the model itself and associated tokenizer.
  - includeStopToken: when true, the terminating EOS/unknown token is yielded before finishing
  - wiredMemoryTicket: Optional wired memory ticket for policy-based coordination across
    concurrent tasks. This is opt-in and only applied on GPU devices that support wired
    memory control (macOS 15 / iOS 18 / tvOS 18 or newer).

## `generateTokenTask`

_relocated from lines 1660-1675 at base e1d070f2_

Low-level raw token generation using a `TokenIterator`, returning an
`AsyncStream<TokenGeneration>` and a `Task`.

This is useful for parsers that need access to the token IDs directly (e.g. Harmony parsing)
without detokenization or tool-call parsing.

- Parameters:
  - promptTokenCount: number of tokens in the prompt
  - modelConfiguration: model configuration (for EOS/extra EOS tokens)
  - tokenizer: tokenizer (for EOS id and unknown token id)
  - iterator: token iterator
  - includeStopToken: when true, the terminating EOS/unknown token is yielded before finishing
  - wiredMemoryTicket: Optional wired memory ticket for policy-based coordination across
    concurrent tasks. This is opt-in and only applied on GPU devices that support wired
    memory control (macOS 15 / iOS 18 / tvOS 18 or newer).
- Returns: An `AsyncStream` that emits token IDs and a final `.info`, plus a `Task`.

## `task`

_relocated from lines 1710-1710 at base e1d070f2_

Launch a Task to perform iteration asynchronously.

## `line1727`

_relocated from lines 1727-1727 at base e1d070f2_

Check for cancellation on every loop iteration.

## `line1739`

_relocated from lines 1739-1739 at base e1d070f2_

Check for end-of-sequence tokens

## `line1783`

_relocated from lines 1783-1783 at base e1d070f2_

Synchronize with the stream to ensure tasks are completed

## `ticket`

_relocated from lines 1786-1786 at base e1d070f2_

Finalize the stream

## `line1799`

_relocated from lines 1799-1799 at base e1d070f2_

When the consumer cancels (or ends) the stream, cancel our underlying task.

## `measure`

_relocated from lines 1809-1809 at base e1d070f2_

Measures the execution time of a closure.

## `GenerateStopReason`

_relocated from lines 1816-1816 at base e1d070f2_

MARK: - Generation structs

## `GenerateStopReason`

_relocated from lines 1818-1818 at base e1d070f2_

Reason why token generation stopped.

## `line1820`

_relocated from lines 1820-1820 at base e1d070f2_

Generation stopped because an EOS/unknown stop token was encountered.

## `line1823`

_relocated from lines 1823-1823 at base e1d070f2_

Generation stopped because the configured max token limit was reached.

## `line1826`

_relocated from lines 1826-1826 at base e1d070f2_

Generation stopped due to explicit task cancellation or early stream termination.

## `GenerateCompletionInfo`

_relocated from lines 1830-1832 at base e1d070f2_

Represents metadata and statistics related to token generation.

Provides information about the number of tokens processed during both the prompt and generation phases, as well as the time taken for each phase.

## `promptTokenCount`

_relocated from lines 1834-1834 at base e1d070f2_

The number of tokens included in the input prompt.

## `generationTokenCount`

_relocated from lines 1837-1837 at base e1d070f2_

The number of tokens generated by the language model.

## `promptTime`

_relocated from lines 1840-1840 at base e1d070f2_

The time interval (in seconds) taken to process the input prompt.

## `generateTime`

_relocated from lines 1843-1843 at base e1d070f2_

The time interval (in seconds) taken to generate the output tokens.

## `stopReason`

_relocated from lines 1846-1846 at base e1d070f2_

Reason generation stopped.

## `promptTokensPerSecond`

_relocated from lines 1849-1849 at base e1d070f2_

The number of tokens processed per second during the prompt phase.

## `tokensPerSecond`

_relocated from lines 1854-1854 at base e1d070f2_

The number of tokens generated per second during the generation phase.

## `Generation`

_relocated from lines 1881-1886 at base e1d070f2_

Represents the different stages or outputs of the token generation process.

This enum distinguishes between the following:
- `.chunk`: A decoded string from one or more tokens generated by the language model.
- `.toolCall`: A tool call parsed from the generated output.
- `.info`: Metadata and performance statistics about the generation process.

## `line1888`

_relocated from lines 1888-1888 at base e1d070f2_

A generated text chunk as a String.

## `line1891`

_relocated from lines 1891-1891 at base e1d070f2_

Completion information summarizing token counts and performance metrics.

## `chunk`

_relocated from lines 1894-1894 at base e1d070f2_

A tool call from the language model.

## `chunk`

_relocated from lines 1897-1897 at base e1d070f2_

Generated text or nil

## `info`

_relocated from lines 1906-1906 at base e1d070f2_

Completion info or nil

## `toolCall`

_relocated from lines 1915-1915 at base e1d070f2_

Tool call or nil

## `collect`

_relocated from lines 1924-1924 at base e1d070f2_

Reducer that can be used with `throttle()` to gather elements into a batch

## `TokenGeneration`

_relocated from lines 1931-1933 at base e1d070f2_

Represents the different stages or outputs of raw-token generation.

This mirrors `Generation`, but yields raw token IDs instead of decoded text/tool calls.

## `line1935`

_relocated from lines 1935-1935 at base e1d070f2_

A generated token ID.

## `token`

_relocated from lines 1938-1938 at base e1d070f2_

Completion information summarizing token counts and performance metrics.

## `token`

_relocated from lines 1941-1941 at base e1d070f2_

Token ID or nil

## `info`

_relocated from lines 1949-1949 at base e1d070f2_

Completion info or nil

## `collect`

_relocated from lines 1957-1957 at base e1d070f2_

Reducer that can be used with `throttle()` to gather elements into a batch

## `TokenLoopHandler`

_relocated from lines 1966-1966 at base e1d070f2_

MARK: - TokenLoopHandlers

## `onToken`

_relocated from lines 1971-1971 at base e1d070f2_

Return false to stop the loop early.

## `onStopToken`

_relocated from lines 1977-1977 at base e1d070f2_

Called only when includeStopToken == true and a stop token was hit.

## `onGenerationEnd`

_relocated from lines 1983-1983 at base e1d070f2_

Called after the token loop finishes, before the info event.

## `textToYield`

_relocated from lines 2008-2008 at base e1d070f2_

Process chunk through the tool call processor.

## `line2015`

_relocated from lines 2015-2015 at base e1d070f2_

Emit all complete tool calls in parse order.
