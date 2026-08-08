# R86-B §4 — Arithmetic decomposition of the C1 RMSNorm→QKV fusion failure

Site: fused `decode nvfp4 norm+qkv(+gate)` kernel, branch `maple-fern/fused-norm-qkv-gate`,
kernel retrievable at `9c73e16f:Sources/MLXFastModel/LagunaRuntimeModel.swift`, branch tip
`f4c86e44d40c305d850fb30092a0d62d0bbff606` (which strips the kernel back out).

Author's prediction: **+0.85–0.9 %**. Ranked M5 receipt `285f79fa-089f-4184-b1ec-0647cb51e61b`
measured `ns=2.540575` against control `c3ce66ec` `ns=2.544360` = **−0.1488 %**, i.e.
**+9.7–10.0 µs/step slower**.

The interesting fact is not that it lost. It is that it lost *by a little* while its
individual terms are *large*. This is a **cancellation, not a wash**: three effects of
±35–100 µs each summed to −55 µs on M4 and to +10 µs on M5.

## 4.1 The redundancy multiplier R, with line-number evidence

Verified in this checkout (`git show 9c73e16f:Sources/MLXFastModel/LagunaRuntimeModel.swift`):

| Fact | Line | Text |
| --- | --- | --- |
| thread grid | `:4861` | `let grid = ((rows / 16) * 512, 1, 1)` |
| threadgroup | `:4867`, `:4885` | `threadGroup: (512, 1, 1)` |
| simdgroups per TG | `:4769` | `constexpr uint num_simdgroups = 16;` |
| full per-TG reduction | `:4787–4793` | each TG reads `residual[base + i]` and accumulates `acc += fv * fv` over the **whole** `axis_size = 2048` row |
| reduction width | `:4766` | `constexpr uint axis_size = 2048;` |

Threadgroups per dispatch = `grid.x / threadGroup.x` = **`rows / 16`**.

`rows` is the QKV bank output width. For the h64 layers `rows = 10240` ⇒ **R = 640**; for the
h48 layers `rows = 8192` ⇒ **R = 512**. Every one of those threadgroups independently computes
the *same* 2048-element sum-of-squares for the *same* single decode row.

**R = 640 (h64) / 512 (h48).** Stock does the reduction once per layer, so the step goes from
40 row-reductions to ≈24,320, a ≈608× instruction-side redundancy on that operation.

### The advisor's 5120 and my 640 are the same site at two different geometries

The byte-census audit reports this site at **5120 threadgroups** / **+308.3 µs/step** gross
redundant work, redundancy exponent ≈0.64. That is not a contradiction — it is the **stock**
consumer geometry:

| Kernel | grid | TG | threadgroups = R (h64) |
| --- | --- | --- | ---: |
| stock `lagunaDecodeNVFP4QKVR1` (`:4857`, call `:5806`) | `((rows/2)*64,1,1)` | 64 | `rows/2` = **5120** |
| C1 fused `norm+qkv(+gate)` (`9c73e16f:4861`) | `((rows/16)*512,1,1)` | 512 | `rows/16` = **640** |

So C1 did **not** fuse at stock geometry. It first coarsened the consumer 8× (5120 → 640 TGs)
*specifically to cut the redundancy it was about to introduce*, and only then fused. The `G` rung
of §4.2 is exactly that geometry change.

This lets the two independent audits be checked against each other. Take my deconfounded M4
measurement at R = 640 and scale it to R = 5120 with the audit's own exponent:

```text
80.4 µs × (5120 / 640)^0.64  =  80.4 × 8^0.64  =  80.4 × 3.785  =  304.3 µs
```

The audit measured **308.3 µs**. Agreement to **1.3 %**, from two entirely independent methods.

Three things are established by that agreement:

1. the redundancy exponent **0.64 is real**, and cost scales as `R^0.64`, not as `R`;
2. my R = 640 rung and the audit's R = 5120 figure are the **same physical effect**; and
3. **C1 had already applied an 8× redundancy mitigation and it still was not enough.**

## 4.2 The M4 ledger (measured, deconfounded)

PR #298's deconfound ladder isolates the three effects by building four rungs:

- `0` = stock (unfused, separate RMSNorm and QKV dispatches)
- `G` = fused *geometry* only (new grid/threadgroup shape, no redundancy, no boundary removal)
- `R` = `G` + the redundant per-TG norm reduction
- `N` = `R` + the actual boundary removal (the real fused kernel)

| Term | Rung difference | M4 value (µs/step) | 95 % CI | Class |
| --- | --- | ---: | --- | --- |
| Occupancy / threadgroup geometry | `G − 0` | **−35.4** | [−62.8, −8.0] | instruction |
| Redundant RMSNorm recomputation | `R − G` | **+80.4** | [+53.0, +107.7] | instruction |
| Boundary / chain refund | `N − R` | **−100.0** | [−127.3, −72.6] | mixed |
| **Net** | `N − 0` | **−55.0** | — | — |

`_nax` exposure at this site is ≈0 (the M4 host reports Apple GPU gen 16 and never selects the
`_nax` prefill variants; this is a decode kernel).

**On M4 the fusion was a genuine 0.67 % win.** The author's prediction was not wrong about the
refund; it was wrong because it modelled only the refund. The two terms the prediction never
contained net to `+80.4 − 35.4 = ` **+45.0 µs**, and that omission is the entire M4-side error.

## 4.3 The M5 reconciliation

| Term | M4 (µs) | M4 (% of 8216 µs step) | transfer | M5 (% of 6519 µs step) | M5 (µs) |
| --- | ---: | ---: | ---: | ---: | ---: |
| Boundary refund | −100.0 | −1.22 % | ×0.39 | −0.47 % | **−30.9** |
| Redundancy + geometry | +45.0 | +0.55 % | ×1.15 | +0.63 % | **+41.0** |
| **Sum** | −55.0 | −0.67 % | — | **+0.15 %** | **+10.1** |

Predicted +10.1 µs / +0.15 %; the ranked receipt measured +9.7–10.0 µs / +0.1488 %. The ledger
closes to within 4 %.

The transfer coefficients are the whole story and they move in **opposite directions**:

- The refund is dominated by dispatch/launch cost, which is *cheaper* on the wider M5, so it
  shrinks. ×0.39 sits at the low end of the programme's measured 0.4–0.5 dispatch-refund
  transfer band.
- The redundancy is exposed ALU/reduction work. On the **bandwidth-bound M4** a large part of
  those 24,320 redundant reductions hide behind memory stalls. On the **instruction-bound M5 at
  ~89 % GPU utilization** there is nothing to hide behind, so the same instructions bill closer
  to 1:1 and the term *grows*.

### The geometry axis is exhausted — proof

Because cost scales as `R^0.64`, coarsening the consumer grid *does* reduce redundancy. That is
why C1 coarsened 5120 → 640 in the first place, and it worked: it converted a 308 µs bill into an
80 µs one. The question is whether coarsening further can finish the job. It cannot, and the
bracket is measured on both sides:

| Geometry | R (h64) | redundancy cost | occupancy cost vs `G640` |
| --- | ---: | ---: | ---: |
| stock | 5120 | +308.3 µs (audit) | 0 (reference geometry) |
| C1 as shipped | 640 | +80.4 µs (this ledger) | −35.4 µs (a *win* on M4) |
| PR #309 `G128` | 128 | ≈ +29 µs (80.4 × (128/640)^0.64) | **+174.9 ± 11.0 µs** |
| PR #309 16 TGs | 16 | ≈ +9 µs | **+917 µs** |

Coarsening from 640 to 128 saves ≈51 µs of redundancy and costs ≈175 µs of occupancy. Coarsening
to 16 saves ≈71 µs and costs ≈917 µs. The redundancy term falls sub-linearly (`R^0.64`) while the
occupancy term explodes super-linearly, so the trade-off has **no interior win below R = 640**.
R = 640 is already at or past the optimum, and it still costs +80.4 µs on M4 and more on M5.

**Therefore the only remaining lever at this site is algebraic: get to R = 1 without changing the
grid.** That is precisely the advisor's instruction, and this table is the quantitative reason
for it. The standing rule of 32 simdgroups holds.

## 4.4 The NET column for this site, in the advisor's requested form

`NET = (barriers removed × d) − (producer cost × (R − 1))`

Barriers removed = 2 per layer × 40 layers = **80**.
`producer cost × (R − 1)` is not modelled here; it is *measured* as the `R − G` rung: **+80.4 µs**.

| Coefficient used for the barrier term | Barrier term | Redundancy term | NET |
| --- | ---: | ---: | ---: |
| in-situ round-trip price `d ≈ 0.78 µs` (this PR, preliminary) | +62.4 | −80.4 | **−18.0 µs** |
| in-situ full WIDE boundary price `1.398 µs` (this PR, preliminary) | +111.8 | −80.4 | **+31.4 µs** |
| M4-measured real chain refund `N − R` = 100.0 µs | +100.0 | −80.4 | **+19.6 µs** |

Two things follow.

**(a) A methodological correction the programme should adopt.** `d` is defined as
`WIDE − TINY`, i.e. the **DRAM round-trip component only**. A real fusion removes the round trip
*and* the dispatch, so a fusion decision must be priced with the **full WIDE price**, not with
`d`. Using `d` under-prices a fusion by the dispatch fraction (~44 % on M4). `d` is the correct
coefficient only when the dispatch survives and just the materialization is removed.

Independent validation of the instrument: the WIDE arm predicts **1.398 µs/boundary** (M4,
4 KiB), and this real, unrelated fusion's measured chain refund is `100.0 / 80 =` **1.25
µs/boundary** (M4). The synthetic in-situ ladder reproduces a real fusion's refund to within
12 %. That is the strongest available evidence that the instrument measures the physical
quantity it claims to.

**(b) The sentence the advisor asked for.** At the price coefficient that is actually correct
for a fusion, the M4 NET is *positive* (+19.6 to +31.4 µs) — yet the ranked M5 result was
**negative**. The barrier term is the one that shrinks ×0.39 across the transfer and the
redundancy term is the one that grows. So:

> **At the norm→QKV site the redundancy term dominates the boundary term on the ranked
> machine.** Re-fusing cannot win there, because the boundary refund is capped by the M5
> dispatch price (≈0.4× of M4's ≈1.4 µs/boundary ⇒ ≈0.55 µs × 80 ≈ 44 µs) while the redundancy
> it introduces is unbounded in `R`. The redundancy must be attacked **algebraically at full
> grid coverage** — not by re-fusing, and not by coarsening the grid.

Grid coarsening is independently dead: PR #309 measured `G128 − G640 = +174.9 ± 11.0 µs`
(coarsening is *worse*), rising to **+917 µs** at 16 threadgroups. The standing rule of 32 holds.

## 4.5 The one measurement that closes the remaining gap

Rerun PR #298's deconfound ladder `{0, G, R, N}` **on the ranked M5**, using
`research/nezuko_pr48_deconfound.patch` with the A/B/B/A driver `research/nezuko_pr48_abba.sh`.
It costs four arms and resolves the only live ambiguity — whether the M5 penalty is redundancy
or occupancy:

- If **`R − G` ≳ +60 µs on M5** ⇒ redundancy dominates. Fix it algebraically (§4.6).
- If **`N − R` ≲ −50 µs on M5 with a small `R − G`** ⇒ occupancy, not redundancy, is the killer,
  and the fix is a threadgroup-geometry change, not an algebraic one.

## 4.6 The four-part selection criterion for any future fusion

The programme has now paid for this twice. A fusion candidate should ship only if **all four**
hold:

1. the removal is verified to occur on the **ranked** decode path;
2. **R = 1** — the producer is computed once, not once per consumer threadgroup;
3. **occupancy invariants are preserved** (simdgroup count, threadgroups-in-flight, threadgroup
   memory per TG);
4. the refund is priced with **M5-measured** constants, never M4 ones.

Redundancy-freedom is necessary but **not sufficient**. Counterexample PR #137: bit-exact *and*
redundancy-free, measured **−63.7 µs on M4**, shipped **+24.6 µs on M5**, because occupancy
collapsed from 25,088 to 3,136 simdgroups (transfer coefficient −0.40 ± 0.24 — an M4 win became
an M5 loss). Criterion 3 is the one that catches it.

**Recommended direction: epilogue normalization.** Fold the normalization into the *consumer's*
epilogue rather than recomputing the *producer* per threadgroup. It satisfies R = 1 by
construction and preserves the grid geometry, so it clears criteria 2 and 3 simultaneously. The
banked, unmerged evidence for it is `N640 − a0 = −33.7 ± 11.0 µs`.

## 4.7 Regime caveat and class labelling (advisor-requested)

The dev host is an **M4 Pro, 48 GiB, Apple GPU gen 16, bandwidth-bound**. The ranked host is an
**M5 Max, instruction-bound at ~89 % GPU utilization**. A measured **byte-class** optimisation
transferred at **−0.40 ± 0.24** (sign flip). Byte-class results from this host are therefore
presumptively **non-transferable**.

Both quantities this PR produces are **latency/instruction-class**, which is the privileged
class:

| Quantity | Class | Transfer expectation |
| --- | --- | --- |
| in-situ boundary price `d` (round trip) | instruction/latency | privileged; magnitude may shrink with M5's wider dispatch |
| WIDE full boundary price | instruction/latency (dispatch-dominated) | privileged; ×0.39–0.5 on the refund |
| redundancy multiplier `R` | instruction (pure count) | exact — `R` is a property of the grid, not the device |
| cost *of* redundancy at fixed `R` | instruction | grows M4→M5 (nothing to hide behind) |
| any DRAM-bandwidth row in §3 | **byte-class** | **presumptively non-transferable** |

Consistent with this, §3's census concludes the byte axis is closed for decode: intermediates
are <0.5 % of the ≈550 MB/step of weight traffic. Every remaining fusion opportunity is therefore
an **instruction-class** play — it buys dispatch count and latency, never bandwidth. §4.4(a) is
the quantitative version of that: on M4, ~44 % of a boundary's in-situ price is irreducible
dispatch/launch cost with no DRAM component at all.
