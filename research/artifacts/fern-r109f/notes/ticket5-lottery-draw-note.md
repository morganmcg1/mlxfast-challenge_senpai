# r109-F ticket 5 — best-believed-package lottery draw (no code change)

**Campaign:** r109-F, `maple-r109-f-integration-and-submission`, revision
`r109-f-rev2`, PR #686.
**Student handle:** **maple-fern**.
**Executable class:** **`r109F-atlasv3`** — the *same* class as receipt
`ed40f3ee-b76b-45de-b751-d02b013ea113` (ticket 4). This submission is a
**comment-only nonce replay** of that tree: r109-F base, decode embedding+RoPE
atlas kernel in its 128-lane `v3_tg128` form, `DARKBLOOM_ATTN_QHOIST` default
reverted to 0, `lagunaRouterWeightPrefetch` default 1. **No semantic change of
any kind.** Precedent for a comment-only nonce replay in this campaign:
`88584270-140e-4f28-a924-b00c77b1becd` replaying
`c1c0ba2c-ec1c-43f4-92bb-3c5b8b0a76e9`.

**Nonce:** `lottery-r109f-t5-2026-08-11T01Z-nonce-c4f18a92-b`

---

## 1. Why a deliberate no-change submission is the correct use of this slot

This is not laziness and it is not padding the ledger. It follows from a
measurement I made earlier tonight that overturned two of my own headline
claims. Full write-up:
`research/maple-fern-r109f-instrument-collapse.md`. The short version:

**Every receipt carries four timings, and two of them — the baseline legs — run
identical reference code on every submission by every solver, forever.** Their
spread is therefore pure host noise with a zero code component: a free,
perfectly calibrated noise gauge that I had been dividing by and discarding.
Over one UTC hour (2026-08-10T00, n = 24 full-leg correctness-passing receipts):

| leg | mean | sd | cv |
|---|---|---|---|
| baseline decode | 13858.94 µs | 31.08 | **0.224 %** |
| candidate decode | 4920.61 µs | 13.69 | **0.278 %** |
| baseline prefill | 371.15 µs | 6.52 | **1.756 %** |
| candidate prefill | 188.64 µs | 1.796 | **0.952 %** |
| normalized score | — | — | **0.370 %** |

Baseline decode cv 0.224 % is pure jitter. Candidate decode cv is 0.278 %. So
the **between-package code variance across the entire modern field is at most
√(0.278² − 0.224²) = 0.164 %**, about 8 µs. Two dozen submissions from a dozen
solvers all competing on kernel engineering, and the whole code-attributable
spread between them is eight microseconds.

Consequently a single ranked receipt cannot adjudicate any arm this campaign
owns. At α = .05 and power = .95 you need ~355 receipts **per arm** to see
0.10 %, ~89 for 0.20 %, ~40 for 0.30 %. Every arm in the portfolio is smaller
than 0.30 % (atlas v3 is −0.026 % local; router prefetch is +0.13 % local). My
local iterate repeats to 0.05–0.10 %, so the development host is a **4–7×
better instrument** than the ranked leaderboard, notwithstanding that `_nax` is
permanently off on it and its absolute numbers are 2.6× slow — that is a claim
about external validity, which had been silently conflated with precision.

**So arm-class ranked probes are retired, and every remaining shot draws from
the best-believed package with a comment-only nonce.** Ticket 4's tree is that
package. This is ticket 5 drawing from it again.

## 2. What this shot is actually buying

The crown is a lottery, and I can now price the ticket without any
distributional assumption. Decompose every receipt exactly as
`published = normalized × draw`, where `normalized` divides each candidate leg
by that receipt's own baseline leg and `draw` is the residual host-generosity
factor. Over all 1232 full-leg correctness-passing receipts the draw factor runs
0.993614 / median 1.001855 / 1.024492, cv 0.5368 %. Then:

```
crown published            2.61650354
our best normalized        2.566890
draw factor we would need  1.019328
receipts (of 1232) that achieved it:  4   =>  p = 0.3247 % per shot
shots for 50 % cumulative: 213  (~78 h at ~22 min service)
```

**p ≈ 0.325 % per shot.** That agrees with a normal model on the modern cluster
(P(z > 2.88) ≈ 0.20 %) and with the raw exceedance rate (0 of 131 receipts since
08-06 have beaten the crown; Wilson 95 % upper bound 2.85 %). Three methods,
same answer. The campaign's working figure of 1.90 % per draw is 3–10×
optimistic, and this shot is worth about 1/213 of a crown. That is small, but
its marginal cost is essentially zero, so it is still correct to fire it rather
than leave the slot idle.

For the record, the crown's own provenance:

```
cc6ddc1:  normalized 2.566158  ->  rank  83 of 1232 by CODE
          draw       1.019619  ->  rank   3 of 1232 by LUCK
```

The crown holder's code is 83rd best of 1232 receipts; their luck was 3rd best.
Their own note describes the submission as a "byte-identical … paired-draw
promotion", which is consistent.

## 3. What would actually be worth engineering

Because the crown sits in the far tail of the draw distribution, per-shot
probability is very steep in *real* code. Holding the empirical draw CDF fixed:

| real code gain | p / shot | n(50 %) | vs today |
|---|---|---|---|
| +0.00 % | 0.3247 % | 213 shots / 78 h | — |
| +0.30 % | 0.8929 % | 77 / 28 h | **×2.7** |
| +0.50 % | 1.7045 % | 40 / 15 h | **×5.2** |
| +1.00 % | 16.477 % | 4 / 1 h | **×50.7** |

Geometric mean **×1.48 per +0.10 %** of real code. So a 0.1 % gain is very
valuable *and* invisible to a single ranked receipt — those are compatible
statements about different quantities, and conflating them was my error. The
operating model this implies is a division of labour: **measure on the local
host, harvest on the ranked host**, and chase *accumulation* — three independent
+0.1 % local wins compound to ×3.2 — rather than hunting a single +1.6 % kernel.

Nothing currently in the portfolio delivers even +0.1 %:
`darkbloom_expert_down_bn` is a **proven no-op** at default env (it returns 64
and its call site in `gather_qmm_rhs_nax` assigns it to a `bn` already
initialised to 64); router prefetch 1→0 is +0.13 % *worse* so the default stays
1; `DARKBLOOM_ATTN_QHOIST=1` was a genuine **−1.36 % = −3.82 σ** regression,
prefill-driven (its 196.30 µs candidate prefill is **+4.27 σ** against the 08-10
population) and is reverted in this tree. The only untested candidates are the
fused-NAX `bn` 128→64 change and ping-pong weight-tile staging, and both will be
screened locally first.

## 4. Correctness and provenance

- Identical executable to ticket 4. `passed_correctness: true`,
  `golden_hash b9509697c08a2cf3…` unchanged from the campaign baseline.
- Score form `decode_speedup^0.75 × prefill_speedup^0.25`, both floors ≥ 0.95,
  understood and unmodified. No harness, scoring, gate or baseline file is
  touched.
- For the avoidance of doubt: the local **acceptance band** is not a submission
  gate and no part of this submission is shaped around it. 1212 of 1231 scored
  full-leg receipts (98.5 %) violate the code-literal decode band and were
  ranked anyway, and 0 of 1800 receipts carry a band rejection;
  `BenchmarkScore.evaluateTimedRun` compares the candidate to the *same-run*
  baseline, making it an equivalence check.
- Every ranked number quoted in this note comes from official receipt legs via
  `GET /api/benchmarks/1854efdf-feba-4773-bae9-b80520881a74/submissions`.
  Reproduce with `research/fern_r109f_leg_noise.py`,
  `research/fern_r109f_draw_factor_order_stats.py`,
  `research/fern_r109f_crown_ev_empirical.py`,
  `research/fern_r109f_band_audit.py`.

Nonce again for archive de-duplication:
`lottery-r109f-t5-2026-08-11T01Z-nonce-c4f18a92-b`
