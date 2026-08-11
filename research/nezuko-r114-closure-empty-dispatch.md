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

Paired decode s/token differences vs the block's own control:

| block | `C` (s/token) | `S1` | `A1` | `L1` |
|---|---|---|---|---|
| 1 | 0.00897928 | −67.9 µs | −49.2 µs | −54.9 µs |
| 2 | 0.00896136 | −66.1 µs | −29.4 µs | −19.3 µs |

**Both falsifiers fired.**

1. **`L1` is as fast as the injection arms.** An intervention that adds *no* dispatches
   reproduces most of the effect. Whatever is happening is not "empty dispatches".
2. **The dose-response is violently sublinear.** One injected empty dispatch (`S1`) buys
   about as much as forty did. A mechanism that acted through dispatch count would scale
   with dispatch count. This one does not scale at all.

The signature — any perturbation of the launch stream helps, by roughly the same amount,
regardless of size — is an allocator/cadence artefact of the harness, not a property of the
GPU workload.

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
  is pre-registered (`research/nezuko-r117-byte-dose-ruler-preregistration.md`) with five
  rungs over a 6.8× byte range and an additivity check (`AN = ON + QN`), specifically so
  that an R114-shaped confound cannot masquerade as a byte effect.
- **Escalate after the falsifier, not before it.** I published the claim and then tested
  it. The correct order is the other one. That the escalation never actually left my
  workstation is luck, not process, and I am recording it here rather than deleting it.
