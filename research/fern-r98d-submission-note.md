> **NEVER SUBMITTED.** Drafting artifact only. The advisor HOLD of
> 2026-08-09T13:46:53Z replaced the research base before this note was used.
> The single `mlxfast submit` invocation that referenced it failed local
> note-length validation in 0.6 s, before any network call, so no submission
> exists and no receipt was spent. Kept for the record; do not reuse without
> re-deriving every number against the new base.

## r98-D: deepen weight staging in the routed SwiGLU decode QMV kernel

Single-file change to `Sources/MLXFastModel/LagunaRuntimeModel.swift`
(32 insertions, 36 deletions; the submitted surface **shrinks** by 80 bytes).

### What changed

`laguna_routed_nvfp4_swiglu_qmv_packed_top8keys_r1_bf16_v2` — the shipped default
routed gate/up decode kernel — used a depth-1 software pipeline: it prefetched the
next K-block's packed codes and scales while consuming the current block. The
kernel's K loop is exactly 4 blocks (`input_width / block_width`), so depth-1
leaves only ~16 B of quantized weight per lane outstanding at any moment.

This change replaces the pipeline with **full 4-block staging**: a fully unrolled
prologue loads `gate_codes[4]`, `up_codes[4]`, `gate_sb[4]`, `up_sb[4]`, then a
second fully unrolled loop does the input load and the two `qdot` calls. Per lane
that raises codes in flight 16 B → 64 B and scale bytes 2 → 8.

### Why

The routed gate/up decode QMV is memory bound, and the question this submission
tests is *which* kind of memory bound. On the measured host it already reaches
~91 % of the achievable roofline for this site, which is consistent with a
bandwidth limit. But the ranked M5 needs roughly 191 kB in flight to saturate,
against roughly 80 kB on the smaller part, so the same kernel can be
latency-limited there while looking bandwidth-limited elsewhere. Deepening the
staging adds outstanding loads without changing bytes moved, arithmetic, or
dispatch count, which isolates latency from bandwidth as the binding constraint.

Nothing else moves: identical addresses, identical `qdot` arithmetic, identical
accumulation order and `simd_sum` tail, identical dispatch count (no kernel added
or removed), no change to precision or layout, no new allocation.

### Correctness

- `./benchmark.sh --local-submit`: `passed_correctness = true`, `max_abs_diff = 0`
  over 1025 checked steps, empty `error`, no failing case/step/layer.
- `LagunaUpstreamEquivalence`: candidate and unchanged base produce
  **byte-identical** results — same prefill logits (max abs err 0.125, mean
  0.0119), same argmax, and all 8 teacher-forced decode steps differ by exactly
  0.0 (`EQUIVALENCE_EXACT_STEPS=8`). The residual prefill delta is a pre-existing
  property of the non-M5 development host, which reports Apple GPU generation 16
  and therefore never selects the `_nax` prefill kernels; the candidate
  contributes zero to it.

### Timing honesty

The development host is not the ranked part, and I am **not** claiming a local
speedup. A preregistered revert control (base → candidate → base, identical code
in both base legs) showed a −49.9 µs/token drift between the two identical base
runs, three times the candidate's nominal −15.7 µs/token, plus a −2.2 % prefill
drift that must be exactly zero by construction. The local screen therefore has
no resolving power for this effect and is used only as a bit-exactness and
no-regression gate. The paired same-session M5 measurement is the decision
instrument, which is exactly what this submission is for.

_Submitted by an AI agent (OpenHands) on behalf of the Senpai research campaign._
