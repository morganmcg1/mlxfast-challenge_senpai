# R118-A pricing note: I mis-priced my own target in PREREG, and the correction
# makes the negative *stronger* and points at the only lever left

Written after the campaign data existed, and flagged as such. The pre-registered
decision rule is untouched and is applied verbatim in `RESULT.md`; this note is
about how to *price* the answer, not about what the answer is.

## The error

`PREREG.md` priced the 68 µs/step excess by the campaign's standing Rule 105.12
conversion, "+30 µs/step on M5 = +68.7 µs/step on M4", i.e. it divided the M4
measurement by 2.29 before pricing it. That conversion exists because most decode
savings are **core-scalable**: they are bandwidth or ALU inside a kernel body, and
a machine with more cores and more bandwidth recovers proportionally less wall
from the same M4 µs.

The charge for this assignment says the opposite about *this* excess — that it is
**core-count invariant, so M5 inherits it**. Both cannot be applied at once. I
applied the core-scaling anyway and got 0.26 % at τ=1, when the charge's own
premise gives 0.75 × 68/8972 = **0.57 % at τ=1**. That is a factor of 2.2, and it
was in my pre-registration.

## Why the correction does not rescue the target

Because the campaign measured *which part* of the 68 µs is which, and they are
different parts.

The dose arms scale the entire K-loop body — bytes, FMAs, loop iterations, all of
it, proportionally. Everything they remove is therefore core-scalable by
construction. Everything they *cannot* remove — the 39 dispatches, their launch
and drain, the first K block, and whatever latency the machine does not overlap —
is what is left, and the core-count-invariant part lives there. So:

| part of the kernel | measured M4 µs/step | scales with cores? | M5 µs/step | at τ=0.70 |
|---|---|---|---|---|
| interior (what any rewrite can reach) | see `RESULT.md` d2/d1 | yes, ÷2.29 | small | below bar |
| residue (dispatch floor + first block) | the rest | no | 1:1 | the whole prize |

The correction moves value **out of** the region my arms can reach and **into**
the region they cannot. The interior is priced with the ÷2.29 and lands further
below the 30 M5 µs/step bar than the pre-registration claimed. The negative is
stronger, not weaker.

## What the correction *does* say

It says the prize on this target, if there is one, is not in the kernel interior.
It does **not** say the prize is 0.44 %.

### Correction against myself, second order: I mis-read R114-E too

An earlier draft of this note divided alphonse's realised 76.8 µs/step by his 40
removed dispatches, got **1.92 µs per dispatch**, and extrapolated 39 × 1.92 =
**75 µs/step** onto this target. I have now read #700's own terminal result
rather than the campaign summary of it, and **that extrapolation is wrong.
Alphonse explicitly refutes it in his own §6.3.**

His mechanism was not dispatch removal. It was **grid-append absorption**: he
appended `gate_sp`'s tiles onto the existing lane-major QKV grid, and 93.8 % of
`gate_sp`'s serialised busy time was absorbed into cores that were previously
idle (`N-GRIDAPPEND-ABSORBS-LATENCY`). His numbers:

- the audited **dispatch tax is 0.4478 µs/dispatch**, which over −40 dispatches
  predicts **17.9 µs/step**;
- he measured **76.8 µs/step = 4.29× the dispatch tax**;
- and the surplus is co-scheduling, not launch cost.

So 1.92 µs/dispatch is not a transferable per-dispatch price; it is 0.4478 µs of
dispatch tax plus a large absorption term that is only available to a kernel
**launching fewer threadgroups than the machine has cores**. `gate_sp` launches
**8 threadgroups on 20 cores**. That is the cell.

**The honest dispatch-structure bound for this target is therefore
39 × 0.4478 = 17.5 µs/step**, which is **~4× below the 68.7 µs/step bar** — not
75 µs/step, and not above the bar at all. The corrected number kills my own
follow-on rather than supporting it, so I am recording it in the same document
that made the error.

Two further reasons the absorption route is not available here, which I had
already stated and which the primary source now confirms:

1. **The target is not in alphonse's absorption cell.** `gate_sp` launches 8
   threadgroups on a 20-core machine (0.4 per core) and was idling the GPU; the
   shared QMV launches **256 threadgroups (12.8 per core)** and is not. Part of
   R114-E's 1.92 µs/dispatch was recovered idling, and that part is not available
   here. Only the pure intercept is.
2. **There is no free merge partner.** Absorption needs a neighbour whose grid can
   carry these tiles in the same kernel body. The natural neighbour, the routed
   gate+up QMV, is a different body with a different weight layout and 2048
   threadgroups of its own. Making that work is a kernel rewrite, not a grid edit.

So the honest form is: *the interior of this kernel is closed at the bar, and the
only remaining lever is dispatch absorption, whose upper bound is 75 µs/step
core-count-invariant and whose realistic value is unknown and probably a fraction
of that.* That is a scoping statement for a follow-on assignment, not a claim.
