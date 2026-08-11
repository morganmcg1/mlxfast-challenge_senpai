# The one thing my instrument cannot see, and why the negative survives it

R118-A, maple-tanjiro. Written after reading PR #700's terminal result in full
rather than the campaign's summary of it.

## The warning

Alphonse's R114-E result contains a section (§6.1) titled *"the proposed ruler
would have closed this family by mistake"*. It is about an instrument that is
structurally identical to mine, and I have to answer it before my own negative
can be trusted.

His Stage 2 did what my dose arms do:

> "I cut `gate_sp` memory instructions **3.7× bit-exactly at fixed dispatch
> count, grid and TG shape**. Wall moved **3.98 µs/step** (2.3 % of the kernel)
> — flat, which under the proposed binary writes
> `N-GATESP-SLACK-IS-DISPATCH-SHAPED` and closes the family. Stage 3 then
> measured **−76.8 µs/step, 19× larger**."

So: a dose ruler held at fixed geometry read *flat*, and the family was
nonetheless worth 19× the ruler's reading — because the recoverable time was
recoverable **only by co-scheduling**, i.e. by appending the kernel's tiles onto
a neighbour's grid so idle cores absorb them. His diagnosis:

> "The binary has no cell for real in-kernel latency recoverable only by
> CO-SCHEDULING. Before pointing this ruler at edward/nezuko, add a third
> outcome gated on: **does the kernel launch fewer TGs than the machine has
> cores?** `gate_sp` launches 8 TGs on 20 cores: its work is neither slack nor
> dispatch, it is occupancy the machine absorbs once given neighbours."

**My d1/d2 arms vary in-kernel work at fixed dispatch count, fixed grid and fixed
threadgroup shape. They are that ruler. So my saturation result inherits exactly
this blind spot, and I should say so plainly rather than let a reader discover
it.**

## Precisely what my negative does and does not close

**Closed by my data:** no rewrite of this kernel's *interior* — fewer bytes,
fewer FMAs, fewer iterations, shorter dependent chains — reaches the bar, because
deleting 75 % of the work does not. That is a genuine strict upper bound and it
is unaffected by the blind spot, since co-scheduling is not an interior change.

**Not closed by my data:** appending this kernel's tiles onto another kernel's
grid. My instrument is blind to it by construction.

## Why the target still fails, on the blind-spot route, from someone else's data

I did not measure the co-scheduling route, so I will not claim a measurement.
But it is not unpriced, and both available prices are below the bar.

**1. The target is not in the absorption cell.** Alphonse's own gate is TG count
below core count. Measured on this host:

| kernel | threadgroups | per core (20 cores) | in the cell? |
|---|---:|---:|---|
| `gate_sp` (his target) | 8 | 0.4 | yes |
| **shared gate+up QMV (mine)** | **256** | **12.8** | **no** |
| routed gate+up QMV | 2048 | 102.4 | no |

His stated proxy rule — "a kernel launching fewer TGs than the machine has cores
is already mostly hidden at SPLIT=0" — runs the other way for me: at 12.8 TG/core
the machine is already saturated by this kernel alone, so there are no idle cores
for a neighbour to donate. The absorption term that supplied 4.29× his dispatch
tax has no source here.

**2. Alphonse priced this exact route on this exact target, and it is under the
bar.** His follow-up list, already discounted by his own measured 29.4 %
realisation factor:

> "FOLLOW-UPS (apply the 29.4 % discount): (1) **shared-expert SwiGLU into the
> routed SwiGLU grid** (plumbing half-exists at :10958) **~25–30 µs/step**;
> (2) router top-8 retiled onto that grid, similar. Together **~−60**, not −215:
> run ONE assignment with a shared ABBA, not two noise-level arms."

*(The bare `:10958` is alphonse's own citation, quoted verbatim [sic]. For a
reader: it resolves to `Sources/MLXFastModel/LagunaRuntimeModel.swift:10958`,
inside the `lagunaRoutedSwiGLUQMV(` call that begins at :10954.)*

Follow-up (1) *is* my target. **25–30 µs/step against a 68.7 µs/step bar**, and
even bundled with the router retile the pair reaches only ~60 µs/step — still
short, and that bundle is no longer one kernel's excess.

So the two routes are priced independently and neither clears:

| route | instrument | bound | bar | verdict |
|---|---|---:|---:|---|
| interior rewrite | my dose ruler, measured here | **≤ +41.7 µs/step** (95 % UB) | 68.7 | fails |
| dispatch tax | 39 × 0.4478 µs, audited | 17.5 µs/step | 68.7 | fails |
| co-scheduling / grid append | alphonse #700, discounted | 25–30 µs/step | 68.7 | fails |

The interior bound is mine and measured. The other two are other people's
numbers, cited as theirs, and I flag them as *not measured by me*.

## What I am asking be recorded

Not "the kernel is optimal". The claim is narrower and it is the one my rig
actually supports:

> **`N-SHARED-QMV-INTERIOR-CANNOT-PAY`** — for
> `laguna_shared_nvfp4_swiglu_qmv_rows1_halved_bf16_v1`, deleting 75 % of the
> kernel's weight traffic at fixed dispatch count, grid and threadgroup shape
> saves ≤ +41.7 µs/step (95 % UB, byte-identical negative control passing), and
> the dose response saturates between 50 % and 75 % removal. No interior rewrite
> can reach the 68.7 µs/step bar. **This says nothing about co-scheduling**, which
> this instrument cannot see; that route is separately priced at 25–30 µs/step by
> #700 and also fails, but not by my measurement.

## Instrument note for whoever runs the next dose ruler

Adopt alphonse's third outcome. A flat dose response has two readings, and only
the TG-per-core ratio distinguishes them:

- TG/core **< 1** → flat means *"the machine was idling; go find a neighbour"*.
  Do **not** close the family. This was `gate_sp`, and closing it would have cost
  the campaign +0.45 %.
- TG/core **≫ 1** → flat means *"the work is genuinely fixed-cost"*. Closing is
  safe. This is my target at 12.8 TG/core.

Reporting a threadgroup count next to every null is not bookkeeping; it is the
sign bit on the conclusion.
