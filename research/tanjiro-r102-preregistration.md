# R102-B preregistration — the composed R1∘R2 restoration tree

**Written before any measurement commit on this branch.** PR #565,
assignment `maple-r102-b-composed-restoration-receipt`, revision `r102-b-rev1`.

Branch base `aba31ba9e461c8a4f7a0ba7086b417f0868fcad9`;
`origin/main` = submit base `1bc1c8954147c9e322aad1f3b80bd9fa3c0888d7`.

## What is being tested

Two independently measured restorations now sit in the same file, and the
composed artefact has never been compiled, checked, or timed by anyone:

- **R1** — r85-C float4 merge epilogue (#555): `threadgroup float4
  outputs4[BN*BDP]` in **both** decode attention kernels. −454 B. Solo effect
  **+0.2358 %** of score, CI [+0.1347, +0.3368], measured on a base without R2.
- **R2** — r96-a 4-deep sliding load pipeline (#539): 2-deep → 4-deep ring in
  the **sliding** main loop only. +4,086 B. Solo effect **≈0.13 %**, measured
  on a base without R1.

Published prediction under strict additivity:
`cs ≈ 2.575633 × (1 + 0.002358 + 0.00130) = 2.58506`, i.e. **+0.366 %** over
control receipt `59bd72a3` (`cs` 2.575633). The interaction term `I` has never
been estimated.

Design: 2×2 factorial in the two hunk sets.

| arm | R1 epilogue | R2 4-deep ring |
|---|---|---|
| 00 | off | off |
| 10 | on | off |
| 01 | off | on |
| 11 | on | on |

Estimator on the **sliding** decode-attention kernel pool:

```
I = (t11 − t01) − (t10 − t00)
```

Internal control: R2 does not touch the **full** attention kernel, so on the
full pool `(t11 − t01)` and `(t10 − t00)` must both reproduce R1-alone and
agree with each other. If they do not, the instrument is lying and no
interaction claim may be made.

## Preregistered null explanations

### N-A — clean additivity

The composition is the sum of its parts. `|I| ≤ 0.05 %` of score; the composed
tree's merit is `2.58506 ± session noise`.

*Arm-level signature:* on the sliding pool, `t10 − t00 ≈ t11 − t01` and
`t01 − t00 ≈ t11 − t10`, each within the same-session identical-code null
spread. Static codegen: arm 11's register count, occupancy and spill bytes are
consistent with the union of the two arms' individual deltas, with no new
threshold crossed.

*Falsifier:* a 2×2 interaction estimate whose 95 % CI excludes 0 by more than
the rule-79 same-session null spread at the same slot positions.

### N-B — register-pressure sub-additivity

R2 raises live register pressure in the sliding main loop (four blocks in
flight, not two); R1 changes the epilogue's register footprint and
vectorisation. The compiler allocates registers across the whole function, so
the composed kernel can cross an occupancy threshold neither arm crosses alone.
Then `I < 0`, and the composed tree can be worth **less than R1 alone**.

*Arm-level signature:* arm 11's static register count is strictly higher than
both 10 and 01 **and** its computed occupancy (simdgroups resident) is strictly
lower than both, and/or arm 11 shows spill bytes that neither 10 nor 01 shows.
Sliding-pool `t11` ≥ `t10` while the full pool still shows R1's gain.

*Falsifier / decisive cheap test:* per-arm static register count, occupancy and
spill bytes from `xcrun metal -S` + `metal-objdump` on all four arms. **This is
run first, before any GPU time.** If arm 11's occupancy equals arms 10 and 01
and no arm spills, N-B is dead without spending a single duplex.

### N-C — R2 was never real

#539's ≈0.13 % is within its own error bars of zero on M4, and its M5 half is
inferred, not measured. The composed tree may simply reproduce R1 alone
(+0.2358 %), with R2 contributing nothing and `I` undefined-because-null.

*Arm-level signature:* on the sliding pool `t01 − t00` is inside the rule-79
null band, while `t10 − t00` is outside it and reproduces R1-alone; and the
full-pool R1 contrast matches the sliding-pool R1 contrast.

*Falsifier:* the 01-vs-00 contrast in my own 2×2, on my own host, in the same
session as its own identical-code null.

### N-D — M4 cannot see it

Both effects are ~0.1–0.24 % of score ⇒ ~9–16 µs/step against an M4
end-to-end detection bar of ~80 µs/step. The whole 2×2 may sit inside the noise
floor, in which case **no arm contrast is resolvable end to end**.

*Arm-level signature:* every pairwise end-to-end contrast, including the
identical-code null, has a 95 % CI that contains zero and a null band as wide as
the largest dose.

*Falsifier / discriminator:* the per-kernel census contrast, not end-to-end
timing. The census resolves per-pool µs/step at far finer granularity than the
end-to-end step. If the census contrasts are also inside their null, N-D
stands.

*If N-D is what happens, that is the reported result:* an honest bound on `|I|`
plus the M5 receipt, not a fabricated point estimate.

## Decision rules fixed in advance

- **Rule 78 null gate:** a contrast is null iff `|d%| ≤ 0.25 × smallest
  reported dose`. Never a bare t-statistic.
- **Rule 79:** every reported contrast is published beside a same-session
  identical-code null **at the same slot positions** for the same kernels. A
  contrast the null reproduces is not a result.
- **Probe hygiene (from #539):** the first leg of every campaign is discarded as
  warm-up; `K ≥ 16` for any quoted figure; ABBA order-flipped duplexes,
  `n ≥ 12`; per-rep signs, paired mean, 95 % CI, sign agreement, and thermal
  gate state reported per rep.
- **Rule 75:** sha256 digest of the sorted `Sources/` + `Vendor/` working set
  immediately before build and immediately after the timed phase, published for
  every paired run.
- **Scope:** nothing under `Sources/`, `Vendor/` or `benchmark.json` is modified
  by this PR. `git diff --name-only aba31ba9 HEAD -- Sources/ Vendor/
  benchmark.json` must be empty in the final state. Arms 00/10/01 are built in
  **scratch working trees outside the repository checkout**, never as commits on
  this branch.

## Submission policy fixed in advance

P3 is **not** conditional on P2's sign. The receipt is spent on the composed
tree regardless of the measured interaction, unless P1 fails (non-zero
`max_abs_diff`, an upstream-equivalence failure, or a drift-tripwire failure),
in which case nothing is submitted and the failure is reported immediately as a
blocking finding for the whole advisor branch.

If P2 measures a negative interaction, the note says so explicitly, and the
receipt then measures how much of the composed effect survives to M5.

## What would change the programme's mind

- `I` significantly negative ⇒ the "three reverted wins are additive" model
  that round 102's plan rests on is wrong, and #558 (R3) must be re-planned as
  a measured composition rather than an assumed sum.
- `I ≈ 0` and the receipt lands near `cs 2.585` ⇒ additivity holds on this
  tree, and the remaining restoration can be planned on the additive model.
- Receipt materially below `2.5806` (= control × 1.002, i.e. less than R1 alone)
  ⇒ M5 disagrees with M4 about the composition, and the geometry-transfer
  caveat applies to epilogue/pipeline composition too, not just threadgroup
  counts.
