# R116-A premise correction: the assignment's headroom figure is M4 data and
# is further overstated by the un-applied SPLIT correction

This is a correction to the *framing* of assignment `maple-r116-a-shipped-
defaults-audit`, not to its executable instruction. The audit itself (screen +
confirmation over the shipped compiled defaults) proceeds unchanged. The
correction matters because the assignment justifies the round with a prize
estimate that is roughly an order of magnitude too large, and because the
mechanism it points at is already staffed on another PR.

## What the assignment claims

> `shared_nvfp4_swiglu_qmv_rows1_halved_bf16_v1` runs at 284.9 us/step and
> 153.1 GB/s = 58 % of the bandwidth ceiling, leaving ~119 us/step of slack,
> worth about +1.0 % of score.

## Correction 0 (2026-08-11 04:45Z): I mislabelled the comparison, and the
## real error is bigger than the one I first reported

The first revision of this file called the 230.0 us row "ranked-M5 evidence"
and concluded that the assignment had quoted M4 numbers against an M5 truth.
**That label was wrong and I retract it.** Both numbers are M4 Pro.

The atlas denominator is a literal in the generator:

> `research/maple-alphonse-r109e-bwatlas.py:38`
> `M4_PRO_PEAK_GB_S = 273.0`
> `# M4 Pro spec DRAM bandwidth. ... treat >=95% as "at the ceiling".`

`191.7 / 273.0 = 70.2 %` and `153.1 / 273.0 = 56.1 %` both reproduce against
that constant, so every "% of peak" figure in the atlas -- the assignment's and
mine alike -- is denominated against **M4 Pro**, and the label sums it is built
from are M4 Pro captures (`research/fern_r105e_ledger.py:31`, "M4 Pro
(applegpu_g16s, 20 GPU cores) per-step label sums"). The 284.9-vs-230.0 gap is
a within-host capture/correction difference, not a host difference.

The actual defect in the assignment's premise is therefore **not** that it used
the wrong host's numbers. It is that it applied **no host map at all**, and the
digest makes carrying one mandatory:

> `research/CURRENT_RESEARCH_STATE.md:3229-3239` (B.0.2, the two-pool M4->M5 map)
> `alpha = 266.80 / 610.6 = 0.4369` for **bytes**-regime families,
> `beta = 0.5` for **latency**-regime families, residual -6.63 %.
> "**Mandatory label for every M5 figure derived from this:** *M4 x0.4369
> bandwidth-pool / x0.5 latency-pool two-pool map, residual -6.63 %, #561*."

Neither the assignment nor my first revision carried that label. This one does.

Full M4 row for the kernel: 230.0 us/step, 2.8 % of decode, 39.4 calls/step,
5.84 us/call, 1.119 MB/call, **191.7 GB/s = 70.2 % of M4 Pro peak**, raw
headroom **68.5 us/step** (`research/maple-alphonse-r109e-qk-ceiling.md:~1451`,
digest `:590-593`). The memo's own fusion estimate is **20-40 us/step**.

Correction 1: the assignment's ~119 us/step of M4 slack is 68.5 us/step on the
same host once the atlas row is read correctly.

## Correction 2: the SPLIT=1 deflation has not been applied

`research/CURRENT_RESEARCH_STATE.md:594-596` and `:601-606`:

> **The atlas is uncorrected for SPLIT inflation.** Deflate every row by
> `1.554 us x calls/step` before ranking.
> **SPLIT inflation = +1.554 busy us per command buffer.** Under SPLIT=1 every
> dispatch is its own command buffer, so this is a *pool correction that scales
> with calls/step*.

For this kernel: `1.554 us x 39.4 calls/step = 61.2 us/step` of pure
instrumentation artifact. The 68.5 us of raw headroom therefore deflates to
roughly **7 us/step of real in-kernel headroom**.

The remaining recoverable quantity is dispatch removal, not bandwidth. Fusing
the gate/up half into the already-fused down half removes ~39.4 dispatches per
step. The measured removal price is **0.108 us/dispatch**
(`research/CURRENT_RESEARCH_STATE.md:1775-1782`, PR #483: +80 dispatches/step
cost +8.61 us/step, CI [-17.71, +35.02], family declared "terminal - the family
is dead"), i.e. ~4.3 us/step. That price is also why the *dispatch-count* story
alone cannot fund this round.

## Reconciled prize

All rows are M4 us/step. The score column carries the mandatory B.0.2 label:
*M4 x0.4369 bandwidth-pool / x0.5 latency-pool two-pool map, residual -6.63 %,
#561*, converted against the mapped M5 step of **4141.5 us** (`:3245-3254`) at
the 0.75 decode weight.

| source | M4 us/step | mapped M5 us/step | % of score |
| ------ | ---------: | ----------------: | ---------: |
| assignment framing (M4, no host map) | ~119 | — | claimed ~1.0 % |
| research state's own fusion estimate | 20-40 | 8.7-17.5 (bytes) | 0.16-0.32 % |
| SPLIT-corrected in-kernel + dispatch | ~7 + ~4.3 = ~11 | ~5.2 (latency beta) | 0.09 % |

The assignment's ~1.0 % is unreachable under the digest's own map by every
route: the optimistic route (take the memo's fusion estimate at face value)
lands at **+0.16-0.32 %**, and the corrected route lands at **+0.09 %**.

## Correction 3: tau and alpha may be the same quantity, and several memos
## apply both

This is the part I want the advisor to rule on, because it is worth a factor of
~2.4 on every M4-sourced estimate in the campaign, including the three rows
above.

The campaign carries two conversion constants that were derived independently:

| constant | value | what it maps | source |
| -------- | ----: | ------------ | ------ |
| `tau` | ~0.4 (cedar [0.27, 0.43]; tanjiro 0.54 [0.29, 0.79]) | local measured wall saving -> ranked score | receipts, advisor comment 2026-08-11T03:50Z |
| `alpha` / `beta` | 0.4369 / 0.5 | M4 busy us -> M5 busy us | digest B.0.2 `:3229-3239` |

They are conceptually different -- one is an end-to-end receipt-measured
conversion, the other a host-to-host ceiling ratio -- but they are numerically
almost identical, and `tau`'s measured interval brackets `alpha` at its top end.
tanjiro's alpha-free bound is `alpha < 0.4454`
(`research/maple-tanjiro-r107g-decode-family-regime-census.md:73`), which sits
inside cedar's tau interval.

That coincidence has a practical consequence. A memo that takes an M4 atlas row,
maps it to M5 with `alpha`, and *then* prices the result at `tau = 0.4` has
discounted the same host difference twice. Worked on the middle row above:

- host map only: 20-40 M4 us -> **+0.16-0.32 %** of score
- host map then tau: -> **+0.06-0.13 %** of score

The advisor's +0.25 % screening threshold falls *between* those two answers, so
this is not bookkeeping -- it decides whether the shared-expert fusion lever is
carried or dropped, and the same question applies to every other M4-sourced
estimate now in flight.

I cannot resolve it here: measuring `tau` needs ranked receipts and measuring
`alpha` needs the official M5, and this host is an M4 Pro with no `_nax` kernels
(`is_nax_available()` is false). I am flagging it, not asserting an answer.

**And the resolving experiment for the alpha half is already written, free, and
has been named three times without being run**: `research/fern_r101_bw_probe.swift`
on the official M5. ~7 seconds, zero submitted-surface change, no receipt
consumed. The digest calls it "the highest value per second of any experiment
currently nameable" (`:3336-3345`), fern re-proposes it at
`research/fern-r101-decode-pool-model.md:646`, and tanjiro re-proposes it at
`research/maple-tanjiro-r107g-decode-family-regime-census.md:1214`. Until it
runs, B.0.6's degeneracy stands: `alpha = 0.389` (M5 ceiling 686, "per-family
efficiency work pays") and `alpha = 0.437` (M5 ceiling 610.6, "only bytes pay")
fit equally well and **imply opposite research programmes**, and every
headroom-derived ranking in B.0.3 is provisional.

## The mechanism is already staffed

`research/CURRENT_RESEARCH_STATE.md:597-600`:

> **Assigned:** lever A (+C as fallback) -> maple-alphonse, PR **#700**
> (`maple-r114-e-gate-sp-latency-excavation`). **Shared-expert QMV fusion and
> the routed gate/up QMV family -> maple-edward, #693 `r110-b-rev4`.**

Shared-expert SwiGLU-QMV fusion is edward's assignment, not this one. R116-A
should not be justified by that kernel's headroom.

## Do NOT redirect this round to attention

An earlier internal suggestion (from a support agent, now retracted) proposed
redirecting to `laguna_sliding_fused_attn_ring_v1` (373.4 us/step, nominally
38.8 % of peak) or `full_fused_attn_grow_v1`. That is closed:
`research/CURRENT_RESEARCH_STATE.md:4624` — round 107, PR #642,
**`N-ISSUE-BOUND`**: both `laguna_sliding_fused_attn_ring_v1` and
`full_fused_attn_grow_v1` are at **97.7 % of peak instruction issue**
(`:3217`, `:3656`), so the apparent bandwidth headroom is not purchasable and
the whole above-floor pool including geometry changes is closed. Sliding QK-MMA
is doubly closed at `:1191` (`N-ISSUE-BOUND` + `N-QK-MMA-PADDING-BOUND`).
The `full_fused_attn_grow_v1` number is also 233.9 us/step at 135.6 GB/s =
**49.7 % of peak**, not the ~38 % that circulates from uncorrected SPLIT=1
timing (`:593`).

## What this means for R116-A

R116-A's executable content — auditing whether the shipped compiled defaults of
the NVFP4 SwiGLU-QMV header family and the o_proj QMV family are the fastest
settings — is independent of the kernel-headroom framing and is still worth
running: the header family is spliced into three decode kernels totalling
**2,647 us/step = 31 % of decode busy**, and a default flip is a one-line,
zero-build, bit-exact change. That is the round this student ran. The framing
paragraph should simply not be reused to size a future round.
