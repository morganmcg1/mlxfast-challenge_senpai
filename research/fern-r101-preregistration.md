# r101-A preregistration — decode pool model rebuild

Assignment `maple-r101-a-decode-pool-model-rebuild`, PR #561, revision `r101-a-rev1`.
Base `3567695bb196e92c37e940aaafcbfb9c2b6d61b9` (`codex/mlxfast-maple-20260804-advisor`).
Host: this student's AWS M4 Pro, 20 GPU cores, `applegpu_g16s`, Apple GPU generation 16.

This file is committed **before any measurement in this arm**. It exists so that
every number in `research/fern-r101-decode-pool-model.md` can be checked against
what I said I expected, per rule 72 (preregister the *explanation* for a
possible null, not only the threshold).

What I have read before writing this: the assignment body, and existing
programme documents only —
`research/maple-fern-decode-marginal-cost-ledger.md`,
`research/maple-frieren-r94-decode-residue-ledger.md`,
`research/CURRENT_RESEARCH_STATE.md`,
`research/RESEARCH_STATE_ARCHIVE_through-round-21.md`,
`research/fern_r100_attn_probe.swift`.
No new measurement, no new byte derivation, and no fit has been run.

---

## 0. Zero-delta commitment

Submitted-surface byte delta of this arm is exactly **0**. Everything lands
under `research/`. `LagunaRuntimeModel.swift` has 13,324 B of per-file headroom
reserved for two pending restorations and this arm will not touch it. No
official receipt is authorised or will be dispatched from this arm.

## 1. What the assignment claims, restated as testable propositions

The advisor's §1 asserts a dichotomy:

> Every rate derived by duplicate injection or receipt differencing exceeds its
> host's peak DRAM bandwidth. Every rate derived from a GPU timer census does not.

I will test the two halves separately, because they can fail independently.

## 2. Registered predictions

### P0-1 (the advisor's own registered prediction, adopted)

**At least three of the eight rows in §1 exceed 100 % of their host's peak DRAM
bandwidth under my own independent byte accounting.**
Falsifier: if my byte accounting puts all eight at ≤ 100 %, P0 fails and the
assignment collapses to a bookkeeping correction. I will report that outcome as
a success and say so plainly.

### P0-2 — I predict the *second* half of the dichotomy is false

**At least one census-derived rate in the r94 24-row ledger also exceeds 100 %
of this host's peak.** Named candidate: `T1c lmhead_int5_base_coarse_delta`,
which `research/maple-frieren-r94-decode-residue-ledger.md:186` already
publishes at **306.6 GB/s = 112 % of 273 GB/s** and already resolves by revising
its byte count down, not its timing.

Why this matters and why I register it: it means "> 100 % of peak" does **not**
diagnose the instrument. It diagnoses an inconsistent triple
`(bytes, time, peak)`, and the analyst still has to say which leg is wrong.
There are exactly three admissible faults and they have different fixes:

| fault | mechanism | signature |
|---|---|---|
| **F1 bytes inflated** | the logical byte count is not the DRAM traffic | over-peak on *both* hosts, for *both* instruments |
| **F2 time under-attributed** | the marginal excludes fixed per-call cost the census includes | marginal < census with no cache story |
| **F3 traffic cache-served** | the differenced work re-reads lines still resident | over-peak only for the instrument that re-reads |

### P0-3 — the T2d byte split

The advisor is unsure whether T2d should carry 184.0 MB (routed down third
only) or more. I predict **the correct r94-epoch figure is 207.0 MB**, already
published at `research/maple-frieren-r94-decode-residue-ledger.md:173-194`,
because r94 already charged T2d the shared-expert down weights and the residual.

Consequences I register now:
- the T2d **census** rate rises from the advisor's 204.7 GB/s to ≈230 GB/s,
  which removes the apparent census outlier and means **the routed pool has no
  internal census anomaly**;
- the T2d **injection** rate rises from the advisor's 331.6 GB/s to ≈373 GB/s,
  i.e. ≈137 % of 273 GB/s — the impossibility gets *worse*, not better.

### P0-4 — the mechanism behind `E < 1`, stated as a quantitative prediction

I predict F3, and I predict it is **not** a vague "warm cache" story but a
monotone function of the **per-call** unique footprint, because duplicate
injection re-issues one *dispatch*, so the footprint that can be reused is the
per-call footprint, not the per-step family total.

**Registered prediction: over the seven priced rows of
`research/maple-fern-decode-marginal-cost-ledger.md:432-440`, `E` is monotone
increasing in per-call unique MB, with Spearman ρ ≥ 0.80.**

The ordering I expect (per-call MB from the r94 byte column ÷ calls):
`T0a` ≈ 0.001 MB < `T1a` ≈ 1.05 < `T2a` ≈ 1.18 < `T2d` ≈ 5.3 < `T2c` ≈ 9.4 <
`T0b` ≈ 11.2 << `T1c` ≈ 128.5 MB, against published
`E` = −0.045, 0.349, 0.311, 0.617, 0.754, 0.741, 1.111.

If ρ < 0.80, F3 is not the whole story and I must decompose F2 as well.
I will also report the implied reusable capacity `C = F·(1 − E)` per row and
state whether it is constant; if it is not constant, I will say so rather than
inventing a capacity.

### P0-5 — why the 610 GB/s receipt differential is valid when the other two are not

Registered answer, written before I re-read the archive derivation, so it can be
scored: a difference in time between two runs is a **byte rate** only if the
differenced bytes are *compulsory* DRAM misses and the differenced time is the
*isolated* cost of moving them. A streaming sweep whose Δ footprint is ~1.6 GB
read once has no reuse available to it, so its miss fraction is 1 by
construction. A per-family ablation differential removes compute, dispatches and
occupancy along with bytes, and leaves the remaining work free to reuse lines the
ablated work would have evicted, so its Δtime is not the isolated cost of its
Δbytes. `T1c_lmhead` at `E = 1.111` is the empirical demonstration inside our own
data: a 131072 × 2048 plane cannot be resident, so its duplicate gets no help.

### P1 — layout epoch

I predict the routed-expert per-step byte count at the **current frontier** is
**521,404,416 B**, i.e. 5.56 % below the 552,076,800 B on which rules 70 and 76
were written, the difference being `lagunaHalvedGroup32ScalePlane` from #72.
I predict I will find **at least one further epoch trap** in the 24-row ledger
beyond the routed one.

### P2 — the measured M4 peak

Three different M4 peaks are in live use in this repository: 273 GB/s
(theoretical, r94), 260.6 GB/s ("roofline-measured", the marginal ledger), and
266.3 GB/s (hardcoded in `research/fern_r100_attn_probe.swift:71`). I will
measure my own.

**Registered prediction: achievable streaming GPU read bandwidth on this host
lies in [230, 273] GB/s, point estimate 250 ± 15 GB/s.**

Registered falsifier for the whole of P0: **if the measured achievable read
bandwidth exceeds 310.9 GB/s, the three injection rows become physically
possible and P0 collapses.** I commit to reporting that if it happens.

Per rule 71 as I amended it in #553, the sweep will publish `regime` from
`achieved_GB_s` and `slc_fit` from capacity as two independent columns, and will
report requested vs unique bytes so amplification is explicit rather than
assumed.

### P3 — the M4→M5 map and its residual

Two parameters, fixed priors before fitting:
`α` = bandwidth scale = measured_M4_peak / 610 (prior ≈ 0.427);
`β` = issue scale = 20/40 cores = 0.5.
Applied to the r94 pool decomposition (bytes-bound 6090.4 µs, latency-bound
attention 813.0, partly bytes-bound 497.1 split half and half, launch/ramp
592.9), validated against steady-state M5 decode **4141.5 µs/step** (rule 58).

**Registered prediction: the residual is negative — the naive map predicts M5
faster than it is — and lies in [−20 %, −5 %], point estimate −14.6 %.**

**Registered explanation for the null (rule 72).** The advisor's registered null
is that per-family achieved efficiency is not M4→M5 transferable. I sharpen it
into a direction: M5 Max has 2.0× the cores but ≈2.34× the bandwidth
(610 / 260.6), so each M5 core must sustain ≈15.3 GB/s against an M4 core's
≈13.0 GB/s to saturate. I therefore expect **achieved efficiency to fall on M5**,
and I predict the single physically interpretable correction that closes the gap
is an M5 achieved-efficiency term of **≈0.82** of its own peak, not a third
scaling ratio.

I commit in advance: **I will not add a third or fourth parameter to make the
residual vanish.** If two parameters plus one efficiency term do not close it to
within 15 %, I will report the residual as a number, state which receipt
experiment resolves it, and stop.

### P3b — the two validations will disagree, and I predict where

Second validation is the E-corrected M5 receipt differentials. Registered
prediction:

- **routed** family: the map and the receipt differential agree to within 15 %.
  My pre-fit arithmetic gives M4 routed gate+up+down = 552.1 MB in ≈2164 µs
  (nat) = 255 GB/s = 97.9 % of 260.6; the M5 differential is 552.1 MB in
  1010.67 µs = 546.3 GB/s = 89.6 % of 610; implied measured ratio 0.467 against
  the 0.427 prior, i.e. an efficiency drop of 0.915. Self-consistent.
- **qkvo** family: they **disagree**, and the fault is F1, not F3. M4 qkvo by
  census is ≈802.3 MB in ≈3017 µs = 265.9 GB/s = **102 % of 260.6**, while the
  M5 differential is 651.8 GB/s = **107 % of 610**. A quantity that is over-peak
  on *both* hosts under *both* instruments cannot be a cache artifact.
  **I predict the qkvo byte count of 802.2 MB is overstated.**

If P3b is right, the headline of the report is not "marginals are invalid" but
"one family's byte count is wrong and it is the largest family in the step".

### P4 — the rule 70 verdict

Registered prediction: **TRUE on M4, and the cited M5 support is invalid but
replaceable.** Specifically I expect to rule that rule 70's *conclusion* stands
while its *stated evidence* (546.2 GB/s treated as a rate, and a ≈600 µs pool
that was never measured) must be replaced by: M5 routed = 1010.67 µs/step at
89.6 % of a measured 610 GB/s peak.

I would rather contradict the advisor than agree cheaply, so I register the two
observations that would flip me to FALSE:
1. if the measured M4 peak is materially above 273 GB/s, the M4 census rows fall
   well below saturation and the pool reopens;
2. if the corrected routed byte count (521.4 MB) against the M5 differential puts
   routed below ≈80 % of the measured M5 peak, there is ≥10 pp of efficiency
   headroom and rule 70 is FALSE on M5.
Corrected arithmetic I can already do: 521.4 MB / 1010.67 µs = 515.9 GB/s =
**84.6 %** of 610. That is between the two thresholds, so P4 is genuinely open
and turns on P2's measured peak.

### P5 — conditional follow-on bar

Only a family with ≥10 pp of efficiency headroom against the *measured* peak and
≥30 µs/step of M5 value (0.457 % score at 0.015228 %/µs-step) earns a named
mechanism. I predict **at most one** family clears it, and I predict it is one of
the two attention kernels (M4 census 105–109 GB/s = 39–40 % of peak), not a
routed family. I will not build the probe in this PR.

## 3. Rules in force for this arm

Rule 71 as amended in #553 (two independent columns), rule 72 (this file), rule
77 (faithful dispatch geometry, and I will state threadgroup count,
threads/threadgroup and bytes written for every probe rung), rule 78 (a null gate
is `|d%| ≤ 0.25 × smallest reported dose`).

**Correction registered now, before measuring:** the assignment cites a "new rule
79" from #555. There is no rule 79 in `research/CURRENT_RESEARCH_STATE.md` at
base `3567695b`; the highest rule in the file is 78 at `:2051`. I will honour the
*content* the advisor describes — publish a same-session identical-code null
alongside any per-kernel census contrast — and will flag the numbering gap in the
report rather than silently inventing the rule.

## 4. Stop rule

The arm ends when P0–P4 have answers, whether or not the map closes. It ends
early if P2 measures a peak above 310.9 GB/s (P0 collapses) or if my byte
re-audit puts all eight §1 rows at ≤ 100 % of peak (same). It does not end with a
receipt, a submitted-surface change, or a parameter added to remove a residual.

---

*Preregistration written by an AI agent (OpenHands) acting as research student
maple-fern on behalf of the Senpai campaign.*
