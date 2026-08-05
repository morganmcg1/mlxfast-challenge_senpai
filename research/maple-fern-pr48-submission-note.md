# Decode NVFP4 QKV: fold the attention input RMSNorm and the per-head gate into the R1 QKV kernel

## 1. Initial context and goal

The scored window is one 512-token prefill plus a teacher-forced decode pass of
128 one-token steps, combined as `decode_speedup^0.75 * prefill_speedup^0.25`.
Decode carries 75 % of the weight, so decode is where the marginal effort
belongs. The text tower is ~21.6 GB of NVFP4 weights, fully RAM-resident, so
there is no I/O, streaming, or expert-cache cost to attack; everything that can
be won has to come out of arithmetic, memory traffic, or dispatch overhead.

At batch 1 the decode step is not arithmetic-bound. Each layer issues a long
chain of small dependent kernels, most of which touch a 2048-element activation
vector. My goal for this work item was narrow and deliberately singular: reduce
the number of dispatches on the decode path **without changing a single output
bit**, so that whatever the timing result turns out to be, it is attributable to
dispatch count and intermediate traffic and to nothing else.

## 2. Environment and setup

Development host: Apple M4 Pro, 20 GPU cores, 48 GiB unified memory,
macOS 26.5.2. Ranked target: M5 Max, 128 GB. This asymmetry matters and is
discussed honestly in section 9 — the M4 Pro reports Apple GPU generation 16
and therefore does not select the `_nax` kernel family the ranked M5 uses.

Build and measurement used the harness's own worker build directory rather than
a bare `swift build`, because the two write different build trees:

```
mkdir -p .build-worker/clang-module-cache
CLANG_MODULE_CACHE_PATH="${PWD}/.build-worker/clang-module-cache" \
  swift build -c release --force-resolved-versions \
  --scratch-path .build-worker --product mlxfast-runtime-worker
git checkout -- Package.resolved
```

`--force-resolved-versions` is mandatory here; without it the frozen dependency
graph can be silently rewritten.

## 3. Prior work and baseline

The decode path in this runtime is already heavily fused. Before this change the
active fusions included `residual+rmsnorm+router`, a fused router top-8, a
packed routed gate/up QMV with SwiGLU, a routed+shared down residual, an
embedding+RoPE atlas, sliding and full fused attention, and a gated affine
output projection QMV. That is a well-tuned baseline, and it shaped the search:
the easy adjacent-elementwise fusions were already gone.

What remained unfused was the immediate neighbourhood of the QKV projection. Per
attention layer the stock decode step issues three dependent dispatches:

```
rmsbfloat16  ->  qkv (R1 NVFP4)  ->  gate_sp (per-head g_proj qmv)
```

Both the RMSNorm and the gate are tiny. The RMSNorm reduces over a 2048 axis;
the gate is a small per-head quantized matrix-vector. Neither has enough work to
cover its own launch, and both sit directly adjacent to the QKV kernel in the
dependency chain. Across 40 attention layers that is 80 launches per decode step
whose only reason to exist is that they were written as separate kernels.

## 4. Hypothesis

If per-dispatch cost on the ranked machine is real and is returned when a
dispatch is deleted, then removing 80 dependent launches per decode step should
produce a measurable decode improvement, with zero numerical risk because the
folds can be made bit-exact.

The falsifiable form: this candidate deletes exactly 80 dispatches per step and
changes nothing else. Whatever decode delta it produces is a direct measurement
of the marginal value of a deleted decode dispatch on this hardware.

## 5. Approach selection and tradeoffs

Three candidate mechanisms were considered:

1. widen the QKV kernel's threadgroup geometry;
2. fold the input RMSNorm into QKV;
3. additionally fold the per-head gate into QKV.

I implemented all three, and — importantly — kept 2 and 3 as *selectable modes*
rather than hardcoding only the final one. Mode 0 is the stock three-dispatch
path, mode 1 folds the norm, mode 2 folds norm and gate. That costs a few
hundred bytes of source but it is what makes per-fold attribution possible at
all, and it keeps the unfused path reachable for differential correctness
testing.

The main tradeoff was in the RMSNorm fold. MLX's standalone `rmsbfloat16` for a
2048 axis uses exactly 512 threads / 16 simdgroups with `n_reads = 4`. Floating
point summation is not associative, so **any** other thread count reorders the
sum of squares and changes the result in the last bits. I could have chosen a
geometry better suited to the fused kernel's register pressure. I deliberately
did not: correctness is a hard gate where every checked greedy token must match,
and a bit-exact fusion is worth strictly more than a slightly faster fusion that
introduces drift I would then have to defend. So the fused kernel is pinned to
MLX's exact reduction geometry and tree shape. The gate fold likewise reuses the
accumulator layout of the standalone `gate_sp` kernel.

## 6. Implementation — what changed

All changes are in `Sources/MLXFastModel/LagunaRuntimeModel.swift`, on the
scored decode path.

- A fused kernel source generator that emits an R1 NVFP4 QKV kernel with the
  RMSNorm prologue and, optionally, the per-head gate epilogue inlined.
- The normalized activation is staged in 4 KB of threadgroup memory rather than
  written to and re-read from unified memory. The gate result stays in
  registers. The fused path therefore *removes* a device-visible `normalized`
  allocation instead of adding one.
- A mode selector, defaulting to the fully folded path, with the stock path and
  the norm-only path still selectable for attribution and testing.
- One-shot stderr tracing for each fused site. This matters more than it looks:
  every fusion here is guarded on dtype, rank, exact shape and module identity
  and falls back *silently* when a guard declines. Without tracing, a change
  that quietly stops firing is indistinguishable from a change that does
  nothing. The trace prints once per site, so it cannot perturb timing.

Untouched: weight layout, quantization, cache policy, attention dispatch, MoE,
RoPE. No new precision. No caching or memoization keyed on input tokens. No
cross-invocation state: each decode step computes logits and KV rows only for
the single token supplied to it and advances position by exactly one, so the
serial non-speculative rules are satisfied by construction.

## 7. Exact commands

```
research/run_local_benchmark.sh --local-iterate      # matched A/B research
DARKBLOOM_TRACE_FUSION=1 research/run_local_benchmark.sh --local-submit
research/run_upstream_equivalence.sh                 # vs vendored Laguna oracle
```

The fuse mode was swept with `DARKBLOOM_DECODE_NVFP4_NORM_QKV_FUSE=0|1|2`.

## 8. Experiments and dispatch census

Instrumenting the decode step and counting dispatches per token:

| configuration | dispatches / decode step |
|---|---:|
| mode 0, stock three-dispatch path | 406 |
| mode 1, RMSNorm folded | 366 |
| mode 2, RMSNorm + gate folded (submitted) | 326 |

Exactly the predicted −40 and −80. The trace confirms the fused sites fire for
both head counts present in the tower (`h48` and `h64`) and that the mode-0 and
mode-1 sites do not fire in the submitted configuration.

## 9. Failures and course corrections

**The barrier census surprised me.** I expected the number of pipeline barriers
to fall roughly in proportion to the deleted dispatches. It did not: barriers
*rebalanced* rather than simply decreasing, and the per-mode barrier counts do
not decompose additively across the two folds. The honest consequence is that a
barrier delta is only a lower bound on the structural change, and per-fold
attribution from barrier counts is invalid. I withdrew that line of reasoning
and attribute only against the fully unfused baseline, for the fusion as a whole.

**The bigger course correction: my development host cannot price this change.**
Modelling dispatch overhead as `dT(n) = max(0, n·c − slack)` — a per-dispatch
cost that only becomes visible once the queue is deep enough to stop hiding it —
the M4 Pro has several milliseconds of slack, placing its knee far above the
dispatch counts in play. Removing 80 dispatches on that host predicts a
*structurally* unmeasurable change. And indeed my mode 0 / 1 / 2 local timings
were separated by less than their own run-to-run spread at n = 3 reps, with the
two folds indistinguishable from each other — exactly what the model predicts,
and therefore not evidence of anything.

I stopped trying to extract a timing verdict locally. That is why this is
submitted as a clean measurement rather than as a change I claim to have already
proven fast.

## 10. Measured results

Local validation of exactly this candidate (`--local-submit`): `max_abs_diff 0`,
`passed_correctness true`, `checked_steps 1025`, `case_count 1`,
`peak_ram_gb 21`, `passed true`, `error ""`. The fused and unfused paths agree
bit-for-bit on the 64-step drift tripwire and the teacher-forced cases, and
every checked greedy token matches. Peak RAM was unchanged at 21 GB across all
modes, consistent with the fused path removing rather than adding an
intermediate allocation.

I am deliberately **not** quoting local wall clock. See section 9: this host is
an M4 Pro on Apple GPU generation 16, it does not reach the `_nax` kernels the
ranked M5 selects, and it is on the wrong side of the dispatch-count knee. Its
seconds-per-token are not evidence for this change in either direction.

## 11. Caveats and a pre-registered prediction

Before submitting, I wrote down and committed the two readings this receipt
discriminates between, so the interpretation could not be chosen after seeing
the number. Both share the same measured per-dispatch constant; they differ only
on whether a *deleted* dispatch returns it.

- **Reading A** — that constant is genuine per-dispatch overhead and is fully
  returned. Predicts roughly +2.7 % on the combined score.
- **Reading B** — it is a correlated marginal reflecting encode, launch ramp and
  queue depth, so only the actual GPU work is returned. Predicts roughly +0.4 %.

The two are separated by about ten standard deviations of cross-session decode
noise, so the receipt should resolve them cleanly. **My prior is B**, because my
own instrumentation pointed at CPU-side encode plus launch ramp rather than GPU
synchronisation, which is Reading B's mechanism. I am stating that in advance
and I will not reinterpret a small positive result as a partial A.

A further pre-registered caveat: Reading A assumes a real dispatch's launch cost
equals that of an empty probe dispatch. If the truth is intermediate, the result
lands between the two predictions, which is a legitimate outcome rather than a
failed experiment.

## 12. Learning

Three things generalise beyond this kernel. First, on a well-fused batch-1
decode path the remaining wins are structural — launch count and intermediate
traffic — not arithmetic. Second, bit-exactness is cheap to preserve if you pin
the fused reduction to the geometry of the kernel you are replacing, and it
removes an entire category of risk. Third, and most practically: a development
machine can be *structurally* incapable of measuring a class of change, and the
correct response is to say so and get a receipt from the real target, not to
average more noisy local reps until something crosses a significance threshold.

## 13. Next steps

If the deleted-dispatch cost is meaningfully returned, the same treatment
applies to the other short dependent chains remaining on the decode path, and
dispatch count becomes a first-class optimization target rather than a side
effect. If it is not, that closes the axis cheaply and definitively, which is
also worth knowing, and effort should move to memory traffic and to the routed
expert gather-GEMM instead.
