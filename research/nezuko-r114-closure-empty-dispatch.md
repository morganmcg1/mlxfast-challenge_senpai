# R114 CLOSURE — I was wrong to escalate. The empty-dispatch speed-up is a confound.

*maple-nezuko · written on the R117-C branch because that is where I now am · the
escalation this retracts is commit `8a7d9ebb` on `maple-nezuko/r109-router-hybrid-selector`,
which was **never pushed** and therefore never reached anyone. This note is the public
record of both the claim and its refutation.*

## What I claimed

Injecting **empty, no-op GPU dispatches** into the decode loop made decode measurably
**faster** — 0.91 % to 1.22 % over 8 blocks, CI95 excluding zero, `golden_hash` identical
at every rung. I wrote that up as an escalation because a free 1 % is not a thing one sits
on, and because it appeared to contradict `N-DISPATCH-REMOVAL-NOT-SYMMETRIC` (my own law,
from #682: adding a dispatch costs ~2.34 µs, removing one refunds nothing).

## The falsification I designed against it, and what it returned

If empty dispatches genuinely buy time, then (a) an unrelated intervention that changes
nothing about dispatch count should *not* reproduce the effect, and (b) the effect should
scale with dose. I ran a 16-run, 4-arm, position-balanced campaign
(`/tmp/r107j-certify-20260811T022107Z.tsv`, `research/maple-nezuko-r107j-certify.sh`):

- `C` — shipped default, reference.
- `S1` — a **falsifier**: a single injected empty dispatch (dose 1 of 40).
- `A1` — a **falsifier**: 8 threadgroups, no chaining, no spread.
- `L1` — a **second, structurally unrelated intervention** (`DARKBLOOM_DECODE_ASYNC_STAGE=ladder1`)
  which injects no dispatches at all.

The campaign completed all 16 runs at 03:05Z. Paired decode differences vs the block's own
control (negative = *faster* than the shipped default):

| block | `C` (µs/token) | `S1` | `A1` | `L1` |
|---|--:|--:|--:|--:|
| 1 | 8979.278 | −67.90 | −49.23 | −54.94 |
| 2 | 8961.357 | −66.08 | −29.39 | −19.34 |
| 3 | 8969.410 | −59.59 | −39.08 | −38.25 |
| 4 | 8978.889 | −83.37 | −54.87 | −43.21 |
| **mean** | **8972.233** | **−69.24** | **−43.14** | **−38.94** |
| CI95 | | [−85.27, −53.21] | [−61.05, −25.23] | [−62.51, −15.36] |
| paired sd | | 10.08 | 11.26 | 14.82 |

All 16 runs returned `passed=true` and the identical `golden_hash f49e4c2cbc0d3ceee9…`, so
nothing here is a correctness difference. All 12 paired differences are negative. Every
interval excludes zero on normal theory; the exact sign-flip test returns p = 0.125 for each
arm, which is simply the floor at n = 4 (2/16), so the intervals are the stronger statement
and I report both rather than quoting whichever is friendlier.

**Both falsifiers fired.**

1. **`L1` is as fast as the injection arms.** An intervention that adds *no* dispatches
   reproduces most of the effect. Whatever is happening is not "empty dispatches".
2. **The dose-response is violently sublinear.** One injected empty dispatch (`S1`) buys
   about as much as forty did. A mechanism that acted through dispatch count would scale
   with dispatch count. This one does not scale at all.

The signature — any perturbation of the launch stream helps, by roughly the same amount,
regardless of size — is an allocator/cadence artefact of the harness, not a property of the
GPU workload.

## The part of this that is worth more than the retraction: an OFFSET CLASS

The three arms are not three doses of one thing. `S1` is 1 empty dispatch, `A1` is a
different injection shape, `L1` is an unrelated async-staging change with no dispatches at
all — and they land at −69, −43, −39 µs. What they have in common is not a mechanism. It is
that **each is an arm that is not the reference arm.**

I cannot presently name the cause. The one structural asymmetry I *can* point at is that the
harness invokes a no-gate arm as `./benchmark.sh` and every gated arm as
`env VAR=val ./benchmark.sh` (`maple-nezuko-r107j-certify.sh:203-208`). `env` costs
microseconds once, outside the 1023-step decode timing loop, so it cannot mechanically buy
40 µs *per step*; I record it because it is the only difference I can see, not because I
believe it. The honest statement is: **on this instrument, an arm can sit ~40 µs/step off the
no-gate reference for reasons unrelated to what it changes.**

That is a bigger result than the one I set out to get, and it is a caution for anyone using
this harness — including me, tonight, and including the other students who have adopted
paired local certification. Concretely:

- A **single-rung** A/B against a no-gate control has a floor on what it can resolve that is
  set by this offset, not by its CI. My R114 intervals were ±16 to ±24 µs and all excluded
  zero. They were tight, correct, reproducible, and measuring the wrong thing.
- The defence is a **dose ladder with a free intercept**: the offset is common to all rungs,
  so it lands in the intercept and leaves the slope clean. A ladder also *estimates* the
  offset instead of assuming it away.
- The cheap prophylactic for anyone who wants one: give the reference arm a harmless gate
  (`SOMETHING=1` that the runtime ignores) so that every arm, control included, is invoked
  through `env`. I have not done this yet — my R117 ruler was already running when I worked
  this out — and I am flagging it rather than quietly fixing it, because the fix is untested
  and the ladder already immunises the number I care about.

## Why it would have been unshippable even if it were real

τ for the dispatch/launch/cadence class is **≈ 0.01** (advisor's §0P.15 table; frieren's
100 % harvest of the entire 413 µs/step host gap was worth **+0.035 % of score**). A
0.91–1.22 % *local decode* effect in that class converts to on the order of **+0.01 % of
score**. So even the version of this result I believed was worth roughly nothing on a
receipt. The escalation was wrong on the mechanism *and* mispriced on the conversion.

## What I am taking from it

- **`N-EMPTY-DISPATCH-SPEEDUP-IS-CONFOUND`.** Paired, position-balanced, CI-excluding-zero,
  golden-hash-identical, reproducible across blocks — and still not a mechanism. Interval
  discipline bounds *noise*; it does not bound *confounding*. The only thing that caught
  this was a pre-planned falsifier and a dose ladder.
- I have carried that lesson straight into R117: the byte-dose ruler I am running tonight
  is pre-registered (`research/nezuko-r117-byte-dose-ruler-preregistration.md`) with four
  rungs over a 6.75× byte range and an additivity check (`AN = ON + QN`), specifically so
  that an R114-shaped confound cannot masquerade as a byte effect. The offset class found
  here is the reason that pre-registration was amended at 03:07Z — before any ruler row was
  read — to make **the free-intercept OLS slope** the primary estimator of τ rather than any
  single rung's ratio. Without R114 I would have read `c/Δbytes` bias on the small rungs as
  cache saturation and reported a confidently wrong sub-unity τ.
- **Escalate after the falsifier, not before it.** I published the claim and then tested
  it. The correct order is the other one. That the escalation never actually left my
  workstation is luck, not process, and I am recording it here rather than deleting it.
