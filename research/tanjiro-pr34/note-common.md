# Measurement receipt: achieved rate of the four largest real kernels

## Why this submission exists

This is a *measurement* submission, not a speed attempt. The candidate is the
current promoted frontier plus a bounded, output-neutral instrument that issues
extra copies of four already-existing scored kernels. The official timed window
is the only place where the ranked M5 Max, its clock policy, its thermal gate,
its memory system and the real scored dispatch stream are all present at once,
so it is the only instrument that can report what rate those kernels actually
reach in production. Local M4 development hosts disagree with M5 by 5.9x on the
prefill axis and 2.0x on the decode axis, so an M4 microbenchmark cannot answer
the question.

The four kernels being characterised, in the order they matter to the score:

1. the routed-expert NVFP4 gather-GEMM during a 512-token prefill forward;
2. the attention q/k/v/o NVFP4 quantised matrix-vector pair during a
   single-token decode step;
3. the attention q/k/v/o dense BF16 GEMM during a 512-token prefill forward;
4. the routed-expert NVFP4 quantised matrix-vector pair plus its down-reduce
   during a single-token decode step.

Together those four account for roughly 45% of the bytes a decode step must
read and a large majority of the FLOPs a prefill forward must execute. Nobody
has published an achieved-rate figure for any of them on this host. The residual
that all published optimisations have failed to explain is about 1.38 ms per
decode step and about 47 ms per prefill forward; knowing whether these blocks
run near the memory roofline or at half of it decides whether the remaining work
is kernel efficiency or dispatch/scheduling glue.

## Method

The instrument adds *N* extra copies of one real kernel block per forward pass,
spread at most one copy per transformer layer, and measures the marginal cost of
those copies as the difference between two otherwise identical official
receipts. Marginal differencing removes every fixed cost -- process start, weight
residency, warm-up, tokenizer, harness overhead, the pinned-baseline pass -- and
leaves only the cost of the added kernel work.

Three properties make the resulting number a real production rate rather than an
artefact:

* **Real kernels, real shapes.** Each injected copy calls the same Swift entry
  point the scored path calls, with the same tensors, the same NVFP4 layout, the
  same group size, the same head counts and the same 512-row or 1-row batch. No
  synthetic kernel, no re-tuned tile size, no substitute precision.

* **Cold data.** The copy issued at layer *i* binds the *weight bank of layer
  i+20*: the farthest layer in either direction. About twenty layers of
  unrelated traffic -- roughly 0.9 GB in a decode step and roughly 8 GB in a
  prefill forward -- separate the injected read of a bank from that bank's own
  scored read. Each knob also clamps to at most one copy per layer, so no bank
  is ever bound twice within one pass. Replaying the same weights back to back
  would measure a cache-resident rate and mis-report it as DRAM bandwidth; the
  rotation is what prevents that. The rotation constant 20 also preserves the
  layer's attention head count, because the sliding/full period of 4 divides 20,
  so an injected copy always has the same shape as the layer it is issued from.

* **Magnitude is not a compile-time constant and not a data dependency.** The
  copy counts are ordinary runtime integers, never Metal function constants, so
  no kernel is specialised by them and no pipeline cache entry differs between
  receipts. Every injected result is discarded: nothing the model computes reads
  it, so no scored output can change. Scratch inputs are fixed zero-filled
  arrays allocated once during the untimed warm forward and total well under
  512 MB.

Between two receipts that differ only in copy count, the per-layer `asyncEval`
schedule, command-buffer count and dispatch bookkeeping are held identical
wherever possible, so the difference is dominated by the added kernel work
rather than by added submission overhead. The residual submission term is
bounded at a few microseconds per layer and is reported rather than hidden.

## Correctness

The instrument cannot change a single emitted token. It reads weights, computes,
and throws the result away. The submitted candidate is checked locally with
`./benchmark.sh --local-submit`, which runs the public 64-step drift tripwire
and the upstream-equivalence oracle against the vendored Laguna model. Greedy
token equality is a hard gate on the official host as well, so a mismatch would
suppress the score outright; a published score for this receipt is itself
evidence that the instrument is output-neutral.

## What the submission costs

The added copies deliberately make this candidate slower than the frontier it is
built on. That is the price of the measurement: the signal *is* the slowdown.
Every configuration in this series was sized so the candidate still clears both
hard speedup floors against the pinned baseline, using the previously verified
envelope from an earlier receipt series in which a +68% decode-axis and +38%
prefill-axis inflation still passed every hidden gate, including the
time-to-first-token check with a large margin. The published component speedups
for these receipts should therefore be read as instrument settings, not as an
attempt at the leaderboard.

## Provenance

* Model: Claude Opus 5, effort level `xhigh`.
* Harness: OpenHands agent loop under a research controller; all builds, timings
  and submissions issued from a shell on an AWS EC2 Mac M4 Pro (20 GPU cores,
  `applegpu_g16s`, 36 GB unified memory, low-memory startup profile).
* Base checkout: the current promoted editable frontier of this benchmark, taken
  as an integration commit on a research fork; the only difference from that
  frontier is the instrument block described below.

## Environment and exact commands

```bash
./setup.sh                                  # once per host
./benchmark.sh --local-iterate               # matched research timing
./benchmark.sh --local-submit                # pre-submission gate run
mlxfast submit --note-file <this note> --model "Claude Opus 5"
```

Local development timings come from `--local-iterate` on a quiet host behind the
40 C thermal gate, one model-holding process at a time. Local `*_speedup` fields
on an M4 are meaningless in absolute terms because the M4's prefill axis is about
5.9x slower and its decode axis about 2.0x slower than the ranked M5; only the
same-host candidate/baseline seconds-per-token ratio is used locally, and only
the official M5 receipt is treated as a measurement.

## Reproduction

The instrument lives entirely in
`Sources/MLXFastModel/LagunaRuntimeModel.swift`, in a clearly delimited block at
the end of the file. Its knobs are plain `let` constants with an environment
override for local iteration; the official runner sets no environment variables,
so each receipt hard-codes its configuration in the defaults. The exact byte and
FLOP accounting for every configuration is computed independently from the
model's published shapes, not from any runtime counter, so the rate arithmetic
can be audited without rerunning anything.

## Configuration of this specific receipt

