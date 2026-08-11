# R118-A interpretation: what the dose curve rules out, and what it does not

This file is the argument. `RESULT.md` carries the numbers and the verdict;
`METHOD.md` carries the design. Read this one for why the numbers mean what I
say they mean.

## 1. The dose arms are stronger evidence than a byte probe, and weaker in one way

Truncating the K loop from 4 blocks to 2 or 1 does not remove *bytes*. It removes
bytes **and** the FMAs that consume them **and** the loop iterations that issue
them **and** the latency those iterations expose. The arms scale the entire
interior of the kernel proportionally.

That is a weakness if the question is "is it bandwidth?" — the arms cannot
separate bandwidth from ALU from loop latency, and I will not pretend they can.

It is a strength if the question is the one I was actually charged with: **is the
68 µs/step excess addressable?** Because whatever an interior rewrite could do —
a better unpack, a wider load, more ILP, a different accumulation order, fewer
re-reads — it cannot do more than *deleting three quarters of the interior*. The
d1 arm is therefore a **strict upper bound on every possible interior
optimisation of this kernel**, and it is measured rather than modelled.

## 2. The dose curve saturates, and saturation is the whole result

The shipped kernel reads 4 K blocks. Removing 2 buys one amount of wall.
Removing 3 buys **no more, and by the median slightly less**. The response is
flat between half and three quarters removed. A kernel whose wall time were set
by its interior would show a monotone, roughly proportional curve — that is
exactly what the routed positive control shows over an 8× larger byte range
(0 / 174 / 261 MB/step against 0 / 21.7 / 32.6), linear in bytes removed. The
campaign slope with its interval is in `RESULT.md` §3; the 2.61 µs/MB quoted in
`SMOKE.md` is the n=1 shakedown prior, not a campaign result.

So the shared gate+up QMV has a **floor** that its own interior does not reach.
Extrapolating the flat segment, deleting the kernel's interior entirely would buy
about what d2 buys, and that is already below the landing bar. Stated at its
strongest and with the extrapolation flagged as an extrapolation: **even a
hypothetical rewrite that made the arithmetic and the loads free would not clear
the bar on this target.**

## 3. Which of the four pre-registered hypotheses survives

| hypothesis | prediction for d1 | observed | verdict |
|---|---|---|---|
| **H-bw** — excess is DRAM bandwidth on this kernel's own reads | −216 µs/step | see RESULT.md | **refuted**, by an order of magnitude |
| **H-ceiling** — excess is the 224–227 GB/s real streaming ceiling (R110 F2) | −145 µs/step | see RESULT.md | **refuted** |
| **H-fixed** — excess is per-dispatch fixed cost, invariant to interior work | ≈ 0 response beyond the first block | flat curve | **survives** |
| **H-hidden** — excess is already overlapped and not on the wall at all | ≈ 0 response at every dose | non-zero at d2 | partially refuted |

The surviving pair is H-fixed with a small live interior. That is the two-term
picture: a modest core-scalable interior contribution, and a residue that does
not move when the interior is deleted.

## 4. The bandwidth question, answered directly

The charge asked whether the excess is bandwidth-side or occupancy-side. Neither.

**Not bandwidth-side.** The measured marginal conversion on this kernel is far
faster than the machine can stream. R110 F2 measured the real streaming ceiling
for a ~1.18 MB dispatch at 224–227 GB/s, and the best pure-stream rate ever
measured on this host is 263 GB/s. A marginal rate above that ceiling is not a
statement about DRAM; it is a statement that these bytes were **not the thing on
the critical path**, so removing them returns time only until something else
becomes binding. That "something else" becoming binding at 2 blocks removed is
the saturation in §2.

**Not occupancy-side.** The dispatch launches **256 threadgroups on a 20-core
machine, 12.8 per core.** It is not idling the GPU. Alphonse's R114-E absorption
remedy applies to dispatches with fewer threadgroups than cores — `gate_sp` runs
**8** threadgroups, 0.4 per core — and this target is a factor of 32 away from
that cell. Printed here because the amended law now requires it next to every
null.

| kernel | threadgroups | per core | in the absorption cell? |
|---|---|---|---|
| `gate_sp` (R114-E, landed +0.45 %) | 8 | 0.4 | yes |
| **R118-A target, shared gate+up QMV** | **256** | **12.8** | **no** |
| routed gate+up QMV (positive control) | 2048 | 102.4 | no |

**It is fixed-cost-side — but the arithmetic I first used for that is wrong, and
here is the correction.** An earlier draft of this section read: *"39 dispatches
per step against the campaign's audited Rule 55 per-dispatch intercept of 3.97 µs
on M4 is 155 µs/step of floor before a single byte moves — 2.3× the entire 68 µs
excess."* Three things are wrong with it and I am retracting all three rather than
editing them out of sight.

1. **Wrong quantity.** 3.97 µs is the intercept of a *DRAM cost model* fitted to
   the three trio kernels, `t = 3.97 µs + bytes / 266.3 GB/s`
   (`research/CURRENT_RESEARCH_STATE.md:5668-5672`). It is not an audited
   per-dispatch launch tax, and multiplying it by 39 is an aggregation Rule 55
   does not license. It is also a **SPLIT=1 (GPU-busy) quantity** — nezuko's R93-C
   stall-structure census says so explicitly
   (`research/maple-nezuko-r93-c-stall-structure-census.md:293-294`) — so even
   taken at face value the 155 µs/step is *busy*, and at my measured τ band
   [0.29, 0.79] it is 45–122 µs/step of wall: a bracket around 68, not a 2.3×
   margin. Per-family intercepts also disagree with the pooled fit (qkv 2.29 µs,
   oproj 8.39 µs), so the pooled 3.97 is not a precision instrument for one family.
2. **Contradicted by the adjacent rule.** Rule 53
   (`research/CURRENT_RESEARCH_STATE.md:5661-5663`) is
   *"THERE IS NO DECODE DISPATCH RESIDUE. The 24-label ledger closes to +0.3 µs
   over 406/406 dispatches."* A 155 µs/step harvestable dispatch floor cannot
   coexist with that ledger, and I am not going to claim one.
3. **Inverts Rule 55's own conclusion.** Rule 55's headline is that these kernels
   are *bandwidth*-bound at 92.2 % of sequential-read peak and that
   "memory-latency-bound is excluded". Citing it to argue that "the excess does not
   need a bandwidth explanation" points the rule against its own finding.

What survives is the number that was actually audited at SPLIT=0: alphonse's
dispatch tax of **0.4478 µs/dispatch** (#700 §6.3), which over 39 calls is
**17.5 µs/step** — about 4× *below* the 68.7 µs/step bar, not above it. So the
honest statement is not "the excess fits inside a huge dispatch floor" but "the
realisable dispatch-structure prize here is small, and the dose curve says the
interior prize is smaller still." Both roads are under the bar; that is the
terminal negative, and it does not need the retracted 155.

## 5. The τ paragraph, in the same paragraph as the profiled claim

Every profiled number in this assignment is attribution only and is corrected
before it is priced. The target's 288.0 µs/step is **GPU-busy** measured under
`DARKBLOOM_GPU_PROFILE_SPLIT=1`, a configuration that inflates wall by ~19.6 % on
this host and mis-ranks arms; my own `L-PROFILED-BUSY-OVERPREDICTS-WALL-2X` puts
the busy→wall conversion at τ = 0.54, CI [0.29, 0.79], and cedar's #699 puts it
at [0.27, 0.43], overlapping at [0.29, 0.43]. So the target's *wall* share is
288.0 × τ ≈ **84–124 µs/step** on the overlap interval [0.29, 0.43] (or 84–228 on
my own wider [0.29, 0.79]), not 288. The campaign default τ ≈ 0.40 gives
115 µs/step. **The measured d1 saving is well under even the low end of that**,
which is the third independent statement that the interior is not where the time
is — and note that this comparison is made after the τ correction, not before it.
`evidence/profile/` measures τ for this family directly rather than importing it.

The advisor's formula `%score = 0.75·τ·D_wall/8972` double-counts when τ is
defined as ΔWall/ΔBusy, because D_wall is already wall. Every price in this
assignment uses `0.75·D_wall/8972` on `SPLIT=0` end-to-end wall, with τ used only
where a *busy* number is being converted.

## 6. What I am not claiming

* I am not claiming the 68 µs is unreachable. I am claiming it is unreachable
  **from inside this kernel**, which is what the charge asked and what the arms
  can support.
* I am not claiming a dispatch-absorption win exists. `PRICING-NOTE.md` bounds it
  at **17.5 µs/step** (39 × the audited 0.4478 µs/dispatch), ~4× below the bar,
  and gives two concrete reasons even that is optimistic. *(An earlier draft said
  75 µs/step here, from alphonse's realised rate divided by his dispatch count.
  That is retracted — #700 §6.3 refutes it himself; the surplus over the audited
  tax was grid-append absorption, which needs TG count below core count and this
  target launches 256 TGs on 20 cores.)*
* I am not quoting anything from `SPLIT=1` as a ranking.
* The extrapolation in §2 from "d1 is flat" to "a free interior would not clear
  the bar" is an extrapolation of one segment. The measured statement, which
  needs no extrapolation, is that the strongest dose I ran falls short of the bar.
