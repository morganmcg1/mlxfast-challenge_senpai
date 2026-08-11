# R114 closure — correction to the closure note (arm labels were swapped; the ladder is monotone)

*maple-nezuko. Amends `research/nezuko-r114-closure-empty-dispatch.md`. The retraction of the
headline stands. Two of the three sentences that justify it do not, and the replacement
justification points at a different and more consequential open question.*

## 1. The arm labels in the closure note are swapped

From the campaign header (job `7bb5b097`, session `20260811T022107Z`, rows preserved at
`/Users/ec2-user/r114-preserve/r107j-certify-20260811T022107Z.tsv`):

| arm | actual gates | what it actually is |
|---|---|---|
| `C` | *none* | reference, invoked as bare `./benchmark.sh` |
| `S1` | `INJECT_DECODE_EMPTY=40, EMPTY_TG=8, EMPTY_CHAIN=0, EMPTY_SPREAD=1` | **40** empty dispatches, one per layer, + one extra `asyncEval` per layer, + the 256 MB `LagunaInjectStore.scratch` |
| `A1` | `INJECT_DECODE_EMPTY=1, EMPTY_TG=8, EMPTY_CHAIN=0, EMPTY_SPREAD=0` | **1** empty dispatch at layer 0, + **one** extra `asyncEval` per step, + the same 256 MB scratch |
| `L1` | `DECODE_ASYNC_STAGE=ladder1` | **0** dispatches, **0** scratch; 40 `asyncEval(h)` fires instead of the shipped 7 |

The closure note describes `S1` as "a single injected empty dispatch (dose 1 of 40)" and `A1`
as a shape variant. It is the other way round: `A1` is the dose-1 arm and `S1` is the dose-40
arm. `A1` was designed as the *allocator* falsifier (same 256 MB scratch, minimal disturbance),
not as a dose rung.

## 2. Consequence: the dose response is monotone, not flat

Pooling this session with the 8-block session `20260810T192206Z` (same script, same host,
same mode; levels are not directly comparable across sessions but signs and slopes are):

| empty dispatches / step | arm | Δ decode µs/token vs that session's `C` |
|---:|---|---:|
| 0 (cadence only) | `L1` | −38.9 |
| 1 | `A1` | −43.1 |
| 40 (all at layer 0) | `S0` | −52.2 |
| 40 (one per layer) | `S1` | −69.2 (this session) / −81.7 (8-block session) |
| 400 (ten per layer) | `N400` | −109.8 |

Every ×10 in dose buys a further ≈ −26 to −28 µs. That is a **large intercept plus a real
log-linear slope**, not the flat ladder that "any perturbation helps by the same amount"
predicts. So closure-note falsifier #2 ("the dose-response is violently sublinear — one
injected empty dispatch buys about as much as forty did") is an artefact of the swapped
labels and should be withdrawn. Falsifier #1 — *`L1` adds no dispatches at all and still
recovers −38.9 µs* — survives untouched, and it is sufficient on its own to kill the headline
claim that the mechanism is "empty dispatches".

**The retraction is therefore correct, but the finding underneath it is the intercept, not the
absence of a slope.**

## 3. What the ≈ −40 µs intercept could be — two live explanations, one unrun arm

The closure note attributes the intercept to "an arm that is not the reference arm", and
points at the harness asymmetry in `maple-nezuko-r107j-certify.sh:203-208`: gated arms run as
`env VAR=val ./benchmark.sh`, the no-gate reference runs as bare `./benchmark.sh`. That is a
real structural asymmetry and it is worth testing. But it is not the only thing the three arms
share. Every one of them adds **at least one extra async commit boundary per decode step**:

- `L1` — 33 extra `asyncEval(h)` fires;
- `A1` — one extra `asyncEval(pending)` at layer 0;
- `S1` — 40 extra `asyncEval(pending)`.

So there are two competing explanations of the same ≈ −40 µs, with opposite implications:

- **(i) harness/invocation artefact.** Every number this script has produced from a
  single-rung A/B against a no-gate control is biased by ≈ 0.45 % of decode *in favour of the
  gated arm*. This would need broadcasting to every student who has adopted paired local
  certification.
- **(ii) one extra async commit per decode step, saturating immediately.** Not an artefact at
  all — a real effect on frieren's cadence axis (#681), reachable as a one-line change to the
  `DARKBLOOM_DECODE_ASYNC_STAGE` default at `LRM:746`, which is frieren's declared region and
  not mine to edit.

**The single most informative unrun arm separates them in one shot:**

```
bash research/maple-nezuko-r107j-certify.sh --blocks 6 \
  C: \
  P1:DARKBLOOM_INJECT_PREFILL_EMPTY=1 \
  L1:DARKBLOOM_DECODE_ASYNC_STAGE=ladder1
```

`P1` is *gated* (so it carries the full invocation asymmetry) and allocates the same 256 MB
`LagunaInjectStore.scratch` (so it carries the allocator term), but during single-token decode
`lagunaInjectLayerWork` computes `empties = 0`, leaves `pending` empty, and returns **before**
`asyncEval` — zero extra decode dispatches, zero extra decode commits
(`LagunaRuntimeModel.swift:12125-12190`). Therefore:

- `P1 ≈ −40 µs` ⇒ explanation (i) or the allocator ⇒ the instrument is biased; fix it before
  trusting any single-rung result from it.
- `P1 ≈ 0` ⇒ explanations (i) and *allocator* are both dead, and the intercept is (ii): one
  extra commit per step, saturating. Real, and frieren's to ship.

A pure sham gate (`G0:DARKBLOOM_R114_SHAM_UNREAD=1`; zero occurrences in `Sources/`) is the
cleaner test of (i) alone and costs the same 6 blocks. I queued the `P1` version at 04:03Z and
could not start it: the mutable workspace was already held by the R117 ruler, and the
checkout had been moved to `maple-nezuko/r117-attn-scale-plane-byte-floor`. Recording it
rather than leaving it implied.

## 4. Two things this changes elsewhere

- **My published R109 arm-G negative is safe.** Arm G was a *gated* arm measured against a
  no-gate control and came back **+51.73 µs/step** (slower). If gated arms carry a ≈ −40 µs
  bias in their own favour, arm G's true cost is nearer **+92 µs**. The refutation is
  conservative under this confound, not threatened by it.
- **The R117 free-intercept amendment is sufficient, and for a sharper reason than stated.**
  Whichever of (i) or (ii) is true, the term is common to all four gated rungs
  (`OP`/`ON`/`QN`/`AN`) and absent only from `C`, so it lands entirely in the OLS intercept
  and leaves the byte slope unbiased. Under (ii) it is *also* absent from the gated rungs —
  `DARKBLOOM_ATTN_SCALE_*=0` adds no commits — in which case the intercept is simply zero.
  Either way the slope is clean; the amendment does not depend on knowing which.

## 5. Economics are unchanged

τ ≈ 0.01 for the dispatch/launch/cadence class. −40 µs/step ≈ −0.45 % of decode ≈ **+0.003 %
of score** on a receipt, against a 0.07 % landing bar. R114 stays closed on cost grounds
regardless of which explanation wins. What is *not* closed on cost grounds is item (i): a
biased shared instrument is expensive no matter how cheap the effect that revealed it.

## 6. Rule, restated

`N-EMPTY-DISPATCH-SPEEDUP-IS-CONFOUND` holds, with the mechanism clause corrected:

> A paired, position-balanced, CI-excluding-zero, golden-hash-identical, block-reproducible
> effect can still be entirely intercept. Interval discipline bounds noise, not confounding.
> A dose ladder is what separates them — **and the rungs must be labelled correctly, because
> a ladder read with two rungs transposed produces a flat curve out of a monotone one and
> then argues from the flatness.** Both errors in this episode were bookkeeping, not physics:
> escalating before the falsifier, and reading the falsifier off a mislabelled table.
