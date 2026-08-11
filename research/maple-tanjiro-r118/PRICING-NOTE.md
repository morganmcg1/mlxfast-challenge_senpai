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

It says the prize on this target is real and it is all in the dispatch structure,
where R114-E has just demonstrated a working remedy. Alphonse removed 40
dispatches (406 → 366) and realised 76.8 µs/step for +0.45 %; that is **1.92 µs
per dispatch actually realised**, against the campaign's audited Rule 55
per-dispatch intercept of 3.97 µs — a 48 % realisation, which is itself a useful
number and is consistent with my τ.

The shared gate+up QMV issues **39 dispatches per step**. If the same realised
rate transferred, absorbing them is worth 39 × 1.92 = **75 µs/step,
core-count invariant**, i.e. 0.75 × 75/8972 = 0.63 % at τ=1 and ≈ 0.44 % at
alphonse's realised τ. That is above the bar with room.

Two reasons to hold that estimate at arm's length, stated here so nobody quotes
the 0.44 % without them:

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
