# R109 Arm G — result: the `rmsbfloat16` attention pre-norm is not recoverable

Student: maple-nezuko. PR #682, assignment `maple-r109-b-router-hybrid-selector`,
revision `r109-b-rev2`, research base
`1a6761bf46c282fcabd0577b618f0c1206757e6c`. Host: Apple M4 Pro, 20 GPU cores,
48 GiB, `applegpu_g16s`.

**Status: Arm G is refuted.** The 142.3 µs/step / 41-dispatch `rmsbfloat16`
attention pre-norm pool cannot be converted into a decode win by folding the
reduction into either of its two consumers. Two reusable rules and one
correction to a banked programme claim come out of it.

## 0. Verdict in one table

| what was tried | result | µs/step | CI95 |
|---|---|---|---|
| Fold RMS into the NVFP4 QKV matvec (5120 TGs) | decisive negative | kernel 34.25 → 55.50 µs/dispatch (1.62×) | — |
| Fold RMS into `gate_sp`, delete the pre-norm dispatch (mode C) | **slower** | **−51.73** | b4 |
| Fold RMS into `gate_sp`, keep the pre-norm (modes W/N) | faster, but not because of the fusion | +46.33 / +51.96 | see §2 |
| …of which pure threadgroup geometry (mode S) | **83% of it** | **+43.23** | [+37.06, +58.00] |
| …of which the fusion itself (S→N) | **not distinguishable from zero** | +8.73 | [−14.19, +22.77] |

Sign convention throughout: **positive = candidate faster than the shipped
control**. Every arm is bit-exact (`0 divergences` on teacher-forced greedy
tokens in all 25 b5 slots and all 19 b4 slots), so none of this is an accuracy
trade.

## 1. Why the arm was plausible, and the census claim it rested on

Arm G was commissioned against the decode-dispatch census: `rmsbfloat16` is 41
dispatches and 142.3 µs/step of pool, moves only 8 KB, and at 3.47 µs/dispatch
is launch-bound rather than work-bound. `research/maple-fern-r105d-decode-dispatch-census.md:229`
states H4: "the 41 `rmsbfloat16` dispatches are a 95.9 µs/step launch tax."

**That claim is arithmetically true and causally false, and it overstates the
recoverable amount by 21.7×.** Rule 65's 2.3403 µs/dispatch is an *addition*
price. The removal direction had already failed once: Rule 68 / PR #527 removed
78 prefill dispatches and *cost* +0.639 ms. And PR #483
(`research/maple-fern-r91-input-norm-fusion-price.md`, W&B `ubjfsywa`) *added*
80 redundant input-RMSNorm dispatches — the same kernel family — for only
**+8.61 µs/step busy, CI [−17.71, +35.02] = 0.108 µs/dispatch**, i.e. 21.7×
below the 2.34 µs sticker. Mode C is the first measurement in the *removal*
direction on this kernel, and it agrees: removing 41 dispatches did not return
95.9 µs, it lost 51.7 µs.

Doctrine to bank: **"add a dispatch, pay 2.34 µs" holds; "remove a dispatch,
gain 2.34 µs" is refuted.** Census pool sizes are an upper bound on opportunity,
not an estimate of it.

## 2. What was measured

Rungs, all on the local harness (`research/decode_probe.py`, one worker process
per arm so the knob is read once at process start, position 0 discarded as
warm-up, per-slot median over 199 steps, median-of-medians across slots, 20 000
bootstrap draws over slots):

- **Rung 1a** — RMS hosted in the QKV matvec: 34.25 → 55.50 µs/dispatch, a
  1.62× regression, because each of 5120 threadgroups recomputes the same
  2048-element normalize. Recorded in `research/nezuko_armg_stage1c.md`.
- **Rung 1b/1c (b1–b3)** — the fused `gate_sp` at successive geometries:
  −344.75, −700.40, −48.04 µs/step. All slower.
- **b4** (19 slots, 6 replicates): A 8257.79, C 8309.52, W 8213.06 µs/step →
  **A−W = +44.73 [+37.08, +49.85]**, **A−C = −51.73**, **C−W = +96.46 µs =
  2.35 µs/layer**.
- **b5** (25 slots, 6 replicates per arm, full four-arm attribution) — see
  `research/nezuko-r109-armg-b5-attribution.md`. A 8256.19, S 8212.96,
  W 8209.85, N 8204.23 µs/step.

The arms are defined in `Sources/MLXFastModel/LagunaNormFusedGateSoftplus.swift`
behind `DARKBLOOM_NORM_FUSED_GATE_SP`: `0` control, `1` fused kernel is the sole
producer of `normalized` (pre-norm deleted), `2` RMS restated from the residual
with an unread `normalized` store, `3` RMS restated with no `normalized` output,
`4` shipped gate math at the fused kernel's geometry. Only mode 1 deletes a
dispatch; the call site in `LagunaRuntimeModel.swift:5949–6025` keeps
`inputNorm(input)` alive whenever the fused kernel does not publish
`normalized`. **The shipped default is `0`** — see §5.

## 3. Rule 1: a sole producer of `normalized` inherits the QKV critical path

Mode C is the arm the assignment asked for and it is 51.73 µs/step slower than
the control. The reason is structural, not a tuning failure: `gate_sp` launches
`heads / (NS·R)` = 8 threadgroups and is latency-bound (PR #683,
`N-GATESP-TG-COUNT-IRRELEVANT`, already established it is insensitive to
threadgroup *count*). The QKV matvec launches 5120. When `gate_sp` becomes the
sole producer of `normalized`, those 8 threadgroups must retire before 5120 can
start, so an 8-wide latency-bound kernel is placed in series ahead of the widest
kernel in the encoder. The dispatch saved is worth ~0.1–2.3 µs; the
serialisation costs ~1.3 µs/layer.

Generalised: **fusing a reduction into a narrow consumer is only safe if that
consumer is not the sole producer for a wide one.** The width ratio, not the
dispatch count, decides.

## 4. Rule 2: the barrier law is conditional on the consumer being on the critical path

`N-INDS-DEPENDENCY-BARRIER` prices an intra-encoder dependency edge at
~2.55 µs/layer (+102 µs/step). This arm produced both a confirmation and a
bound:

- **Confirmation, different kernel pair.** b4's `C−W = +96.46 µs/step =
  2.35 µs/layer`. C and W run identical gate arithmetic; they differ only in
  whether the QKV matvec waits on `gate_sp`. That independently reproduces the
  2.55 µs/layer price to within 8%.
- **Bound, off-critical-path consumer.** b5's `S−N = +8.73 µs/step
  [−14.19, +22.77]` removes exactly one edge, `rmsbfloat16 → gate_sp`, and does
  not clear zero. Point estimate 0.218 µs/layer, upper bound 0.35 µs/layer.

The discriminator is the downstream kernel. `gate_sp` is 96.4% nested inside a
larger co-resident command-buffer record, so nothing waits on it; the QKV matvec
is on the critical path. **Refinement: the ~2.55 µs/layer edge price applies
only when the edge's downstream kernel is itself on the critical path. For a
nested, off-critical-path consumer it is 7–10× cheaper and indistinguishable
from zero.** This matters for arm selection: "count the dependency edges and
multiply by 2.55" over-prices any edge whose consumer is nested, which is most
of the small kernels in the encoder.

## 5. Why nothing ships by default

A−N = +51.96 µs/step is a real, bit-exact, reproducible M4 decode win worth
+0.475% at τ=1. I am not proposing it, and the shipped default is mode `0`:

1. **83% of it is threadgroup geometry.** Mode S is the shipped gate arithmetic,
   byte for byte, at 8 TG × 256 threads instead of 8 TG × 64 threads. It removes
   no dispatch and no dependency edge, and it is worth +43.23 µs
   [+37.06, +58.00]. PR #7 measured +7.32% on M4 → ~0% on M5 for a threadgroup
   geometry change, so τ ≈ 0 is the prior and the honest expected M5 value of
   this share is ~0.
2. **The remaining 17% does not clear zero.** S−N = +8.73 [−14.19, +22.77].
   Even at τ = 1 the point estimate is +0.080%, marginal against the ~0.07%
   landing bar, and the interval covers both signs.
3. My preregistered ship rule was "mode 3 only if S−N's CI excludes zero." It
   does not, so mode 0 it is. The knob and the four instrument modes stay in the
   tree so the measurement is reproducible and so the geometry lever is one env
   var away if someone with an M5 wants to price it.

**Flagged for maple-fern (#686), not submitted by me.** If an M5 datapoint on
threadgroup width is wanted for its own sake, `DARKBLOOM_NORM_FUSED_GATE_SP=4`
is a zero-risk probe: bit-exact, one env var, +43.23 µs/step on M4, and it would
settle whether the "geometry does not transfer" rule from PR #7 also covers
*thread count per threadgroup for a latency-bound kernel* as opposed to tiling
shape. I did not run `senpai/submit-official.sh`.

## 6. Honest weaknesses

- `N−S`'s interval is wide because two of six N slots (p17, p22) ran while a
  helper process of mine was committing into the very directory the harness was
  writing. Both show a *widened* per-step distribution, not a shifted one, which
  is host I/O contention rather than a slower kernel. I did not drop them; the
  17/25-slot interim read of the same block said `−11.92 [−18.48, −8.52]`
  ("significant"), which is precisely why post-hoc slot exclusion is not
  available to me. §3.1 of the b5 doc records this.
- Everything is M4. τ for the geometry share is assumed ~0 from PR #7 rather
  than measured, and the direction of that assumption is conservative (it makes
  my candidate look worse, not better).
- The mode-C mechanism in §3 is inferred from the arm contrasts plus the known
  threadgroup counts. §7 tests it directly.

## 7. SPLIT=1 attribution and the encoder barrier census

_(filled in from `research/armg-runs/p1`)_
