# R85-D → R86-A cross-prediction: is the base decode regression dispatch-count-related?

## Epistemic status (read this first)

- Written **2026-08-08T20:17Z**, in response to the advisor comment on PR #458
  (`5227928870`, 20:14:43Z) which asks me to "state in your prior whether you
  expect the base regression to be dispatch-count-related."
- This is **NOT** part of my R85-D pre-registration. My R85-D prior was sealed
  in `research/nezuko-r85-prereg.md` at commit `2a69afa` (19:33:27Z) before any
  ladder measurement, and I have **not** edited it and will not. By the time the
  advisor's message arrived the ladder was 28/41 runs in, so anything written
  now is post-hoc **with respect to my own arm**.
- It **is** genuinely out-of-sample with respect to **R86-A**: PR #460 was
  created 20:11:34Z and at the time of writing has **zero comments, zero
  reviews and no posted measurement**. Nothing about Tanjiro's dataset has been
  observed. That is what makes this prediction falsifiable rather than
  decorative.
- I am **not** bisecting anything. One mechanism per arm (Rule 24). This file
  hands R86-A a calibration constant and a cheap discriminator; the bisection
  is his.

## The question

R86-A's target is **≈38 µs/step of decode** lost between our integration base
and `97a5090c`'s content, spread over 11 differing editable files. The advisor
notes that 38 µs/step "is squarely inside the range your naive dispatch-cost
reading predicts (~80–115 µs/step)" and asks whether the two arms converge on
one mechanism.

## What my ladder already fixes

Measured in-situ on this host (M4 Pro, 48 GiB, Apple GPU gen 16), decode step,
40 decoder layers, `N_extra = 40·K` injected null dispatches:

| quantity | value |
| --- | --- |
| base decode step, unprofiled median | 8234 µs |
| base dispatches / step (profiled census) | **406.0** |
| base command buffers / step | **45.0** |
| on-chain slope (dispatch **+** dependency barrier, 4 KiB) | **1.4134 ± 0.0127 µs/dispatch** |
| work-independent slope (dispatch + barrier, 4 B) | **0.1843 ± 0.0969 µs/dispatch** |
| per-command-buffer cost (programme component model) | ≈ 1.7 µs/CB |

Both ladder arms carry the **same** dispatch count *and* the same barrier count
— MLX's `maybeInsertBarrier()` fires ahead of every `dispatch_threadgroups`
whose input was written since the last barrier, and both chains are
data-dependent. The only thing that differs is bytes moved. So the 0.18 µs arm
is the work-independent price of issuing a dispatch, and the remaining ~1.23 µs
of the wide slope is exposed memory latency belonging to the op's own work.

## The arithmetic

For the 38 µs/step regression to be *dispatch-count*-related, the base would
have to carry, relative to `97a5090c`'s content:

| mechanism | slope | extra units/step needed | as % of measured base |
| --- | --- | --- | --- |
| dependent dispatch boundaries | 1.4134 µs | **+26.9 boundaries** | +6.6 % of 406 |
| barrier-free dispatches | 0.1843 µs | **+206 dispatches** | +51 % of 406 |
| command buffers | ≈1.7 µs | **+22.4 CBs** | +50 % of 45 |

Every one of those is a **large, directly countable structural change**, not a
subtle one. That is the useful part: this hypothesis does not need a bisection
to test, it needs one census.

## Prediction

> **I expect the base decode regression is NOT dispatch-count-related.**
> Confidence ≈ **80 %**. Concretely I predict the profiled dispatch count per
> decode step differs between the two trees by **less than ±10 dispatches/step**
> (and CB count by less than ±3/step), which at my measured slopes accounts for
> **under 15 µs/step** of the 38 µs/step — i.e. under 40 % of it, and most
> likely under 10 %.

**Most likely mechanism instead: bytes moved, specifically KV-cache traffic.**
Reasoning:

1. My ladder says the byte axis outweighs the count axis **7.7:1** on-chain
   (1.229 ± 0.098 µs of the 1.413 µs slope is traffic, not issue). A regression
   mechanism drawn at random from decode is therefore far more likely to be a
   bytes mechanism than a count mechanism.
2. Five of the seven decode-relevant candidate files R86-A names —
   `CompilableKVCache`, `CompilableRotatingKVCache`, `KVCache`, `BatchKVCache`,
   and to a lesser extent `CompiledDecode` — are cache **movement and layout**
   code. Their natural failure mode is an extra copy, a lost in-place update,
   a rotating-window slice materialising the full window instead of the latest
   512 positions, or a dtype/contiguity change forcing a re-pack. All of those
   move bytes at constant dispatch count.
3. 38 µs/step at 8234 µs/step is 0.46 % of the step. A single extra full-window
   KV read on the sliding-window layers is comfortably that size; +27 dispatch
   boundaries is not something that hides in an 11-file research delta.
4. `Evaluate` and `BaseConfiguration` are the two that *could* move counts (an
   eval boundary changes CB packing). If the census does show a CB delta, my
   prediction fails and those two become the prime suspects — that is the
   condition under which I am wrong, stated in advance.

## The cheap discriminator I recommend (≈90 s, no bisection)

This tests the whole dispatch-count family in **one paired run** instead of
three rounds of halving, and it is immune to the ±13.5 µs/step placement
lottery because it counts structure rather than timing it:

```bash
DARKBLOOM_GPU_PROFILE=1 python3 research/decode_probe.py --steps 40 --profile
```

on each tree, and compare the `per steady step: ... cbs=... dispatches=...`
line. On the base that line reads `cbs=45.0 dispatches=406.0`.

- Counts match within a few → dispatch count is **exonerated**; skip it and
  hunt bytes. My slopes convert whatever residual count delta exists into an
  exact µs/step budget, so it can be *subtracted* rather than argued about.
- Counts differ by ~25+ boundaries or ~20+ CBs → my prediction is wrong, the
  arms converge, and the count delta localises the file immediately.

The same profiled line also reports `gpu_busy_sum`, `gpu_busy_union` and `gap`.
On the base, `gap` is 0.207 ms (2.6 % of the step) and busy is 7.848 ms — so if
the 38 µs is *inside* busy it is work, and if it shows up in `gap` it is
issue/CB overhead. That is a second free bit from the same run.

## What I am not claiming

- This is M4 evidence. The regression is measured on M5. If the mechanism is
  `_nax`-gated or core-count-gated it will not appear on this host at all, which
  is R86-A's own Null A.
- My 80 % is a subjective prior calibrated on one host and one instrument, not
  a frequentist statement.
- I have not looked at the 11-file diff, and I am not going to.
