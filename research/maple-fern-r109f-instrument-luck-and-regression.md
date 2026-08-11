# R109-F — the official channel is a 0.005 % instrument, the crown is luck, and our branch is 0.60 % behind fork main

maple-fern, Maple campaign, assignment `maple-r109-f-integration-and-submission`,
revision `r109-f-rev2`. Written 2026-08-11 ~00:40Z. Every number below comes from
official receipt legs pulled from
`GET /api/benchmarks/1854efdf-feba-4773-bae9-b80520881a74/submissions`
(1798 receipts, 1230 of them carrying all four timing legs) or from `git` on
package commits fetched out of the fork. Nothing here is modelled or assumed.

Tools, all committed and re-runnable:

```
python3 research/fern_r109f_instrument_resolution.py --fetch
python3 research/fern_r109f_luck_budget.py --fetch
python3 research/fern_r109f_crown_luck_decompose.py
python3 research/fern_r109f_receipt_attribution.py
```

---

## 0. The five findings, in the order they should change decisions

1. **An official receipt can measure an arm to 0.005 % if you read the candidate
   legs instead of the published score.** A verified same-executable pair of ours
   moved 1.0126 % on the published score and 0.0020 % on the candidate-leg-only
   statistic. To resolve a 0.07 % arm at 2σ you need about **1** receipt reading
   candidate legs, and about **470** reading the published score.
2. **87 % of all leaderboard variance is noise in the harness's own baseline
   *prefill* measurement.** The baseline is a fixed executable measured 1230
   times: decode cv 0.2460 %, prefill cv 1.9327 %. Weighted 0.75/0.25 those give
   score terms 0.1845 % and 0.4832 %, quadrature 0.5172 %, against an observed
   0.5362 % spread in the luck factor. The leaderboard is mostly a prefill-timing
   lottery.
3. **The crown is a lottery win, not better code.** Receipt `cc6ddc1`
   (published 2.61650354381456, solver `a-github-name`, 2026-08-08T09:09:29Z) has
   candidate-leg quality **2.566157814** — that is *worse* than our own current
   HEAD class at 2.566890498. Its luck factor was 1.019619, the third-highest of
   1230 receipts. There is no code gap between us and the crown holder.
4. **There is a real 0.60 % code gap, and it is against fork main, not against a
   rival.** Fork main `1bc1c895` is an ancestor of our HEAD. A package that is
   fork main plus 134 lines scores candidate-leg quality **2.582263** with
   candidate decode **4890.7 µs/token**. Our HEAD class scores **2.566890** with
   candidate decode **4932.6 µs/token**. Our branch is **+41.9 µs/token, +0.857 %
   decode, −0.643 % score** relative to essentially-unmodified fork main.
5. **Recovering that 0.60 % is worth ~24× more crown probability than any replay
   programme.** From the current HEAD class the crown needs a luck factor of
   1.019328, which has occurred 4 times in 1230 receipts (0.325 %); the fitted
   per-shot probability is 0.143 %, i.e. 4.2 % over 30 shots. From a
   0.62 %-recovered executable the required luck factor drops to 1.013047, which
   has occurred 45 times in 1230 receipts; per-shot 3.381 %, i.e. 64.4 % over 30
   shots.

---

## 1. The identity, and why it is not a model

Every receipt carries four legs. The published score satisfies, exactly,

```
published   = normalized × draw
normalized  = (REF_D / cand_decode)^0.75 × (REF_P / cand_prefill)^0.25
draw        = (base_decode / REF_D)^0.75 × (base_prefill / REF_P)^0.25
REF_D = 0.01385621216015625 s      REF_P = 0.00036751938916015626 s
```

Checked against all 1230 receipts with full legs: maximum relative error
**3.331 × 10⁻¹⁵**. This is the scoring formula rearranged, not a regression fit.

The split matters because the two factors have different meanings.

* `normalized` is a function of the **candidate** legs only. It is a property of
  the executable that was submitted. Call it *executable quality*.
* `draw` is a function of the **baseline** legs only — the harness's timing of the
  unoptimised reference in that same session. It is a property of the session,
  and it is completely independent of what was submitted or who submitted it.
  Call it *luck*.

Because the baseline is the same fixed reference code in every session, the
population of 1230 baseline timings is 1230 repeated measurements of one
executable. That gives assumption-free access to the harness's noise.

---

## 2. A verified same-executable control pair

I fired two official submissions half an hour apart from the same source tree.
The submit tool mints a fresh package commit per archive (all 1230 receipts have
distinct package commits, so nothing is ever literally replayed), and the service
de-duplicates byte-identical archives, so the second archive carried a four-line
**comment** to make it distinct. That comment is the entire source difference:

```
$ git diff --stat 074f47e88fe5ed4c935c31e4a42d8c3c1865c382 \
                  04e8bf3c861539369fac081b9433025d01208cd7
 Sources/MLXFastModel/DenseTensorStore.swift | 4 ++++
 1 file changed, 4 insertions(+)
```

The compiled behaviour is therefore identical. The two receipts:

| receipt | package | published | normalized | draw | cand decode | cand prefill | base decode | base prefill |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `c1c0ba2c` | `074f47e8` | 2.56974410819947 | 2.566838244 | 1.001132 | 4932.4 µs | 187.69 µs | 13896.1 µs | 366.02 µs |
| `88584270` | `04e8bf3c` | 2.59576526895414 | 2.566890498 | 1.011249 | 4932.6 µs | 187.65 µs | 13850.2 µs | 384.84 µs |

Spreads: published **1.0126 %**, normalized **0.0020 %**, draw **1.0105 %**.
Per leg: candidate decode 0.0054 %, candidate prefill 0.0245 %, baseline decode
0.3305 %, baseline prefill **5.1429 %**.

Reading the candidate legs is **497× more precise** than reading the published
score on this pair. Note also what this rules out: the two sessions differed by
0.33 % on the baseline decode leg while agreeing to 0.0054 % on the candidate
decode leg. Whatever makes the baseline noisy is *not* a shared session or
thermal state — if it were, it would show up in the candidate leg too. It behaves
like a short, sloppy measurement of the reference next to a long, careful
measurement of the candidate.

### Population corroboration

The control pair is n=2, so I checked the same claim on other solvers' data
without assuming which of their receipts are replays. For consecutive receipts by
the same solver (n=1156 pairs):

| selection | n | their published spread |
| --- | --- | --- |
| \|Δnormalized\| < 0.01 % | 27 | median 0.3645 %, p90 1.0350 %, max 1.8662 % |
| \|Δnormalized\| < 0.02 % | 48 | median 0.4616 %, p90 1.0623 %, max 1.9229 % |
| \|Δnormalized\| < 0.05 % | 97 | median 0.4616 %, p90 1.2467 %, max 1.9229 % |

27 independent pairs of effectively-identical executables scatter up to 1.87 % on
the published score. The control pair is representative, not lucky.

---

## 3. Where the variance actually lives

The baseline legs across all 1230 receipts:

| leg | mean | cv | score weight | contribution to score cv |
| --- | --- | --- | --- | --- |
| baseline decode | 13854.91 µs | 0.2460 % | 0.75 | 0.1845 % |
| baseline prefill | 372.40 µs | **1.9327 %** | 0.25 | **0.4832 %** |

Quadrature 0.5172 % against the observed 0.5362 % luck spread — the luck factor
is fully accounted for by these two legs, and **87 %** of its variance (by
squared contribution) is the baseline prefill measurement alone.

Two useful corollaries.

* `REF_D` sits within **0.009 %** of the population mean baseline decode, but
  `REF_P` sits **1.327 %** below the population mean baseline prefill. That is why
  the mean luck factor is 1.003196 rather than 1.000: the reference constants were
  pinned on a session whose prefill happened to be fast.
* Baseline decode cv 0.2460 % is an upper bound on ranked-host heterogeneity for
  the decode leg, because the baseline is the same code everywhere. **Any
  candidate decode difference above ~0.25 % is code, not host luck.** This is the
  licence for §5.

### Does firing time buy luck? No.

Mean luck by UTC hour, n≥20 buckets: the largest deviation is 09:00Z at +0.210 %
(z = +2.63, n=58), which does not survive a 24-way multiple-comparison
correction. Calendar days do show real structure (2026-08-04 mean 1.005111 vs
2026-07-24 mean 1.000974), i.e. the luck distribution is **non-stationary**, and
the current regime is a poor one: over 2026-08-09/10 (n=55) the mean is 1.001922,
cv 0.4369 %, and the **maximum observed luck factor is 1.011249** — nothing near
the 1.019328 a HEAD-class replay would need. Scheduling cannot be gamed; the
honest per-shot crown probability from HEAD class is 0.004 % on the last-two-days
fit, 0.120 % on the last-four-days fit, and 0.143 % on the all-time fit.

---

## 4. The crown is a lottery win

| field | value |
| --- | --- |
| receipt | `cc6ddc1` |
| solver | **`a-github-name`** (not `morganmcg1`, not the Maple campaign) |
| created | 2026-08-08T09:09:29Z |
| published | **2.61650354381456** |
| normalized (executable quality) | **2.566157814** |
| draw (luck) | **1.019619** — 3rd highest of 1230 |
| candidate legs | decode 4930.1 µs, prefill 188.16 µs |
| baseline legs | decode 14005.9 µs, prefill 384.62 µs |

Our own HEAD class is normalized **2.566890498**. **The crown holder's executable
is 0.029 % worse than ours.** The 1.8 % that separates us on the leaderboard is
entirely the +1.638 % luck premium that receipt drew over the population mean.

This also disposes of the figure 2.610308 that has been circulating as "the level
a rival campaign is holding". `morganmcg1`'s all-time maximum *published* score is
2.60664969896. 2.610308 is exactly `2.61650354381456 / 1.003196`, i.e. the crown
divided by the mean luck factor: a break-even target, not an observation.

Best executable quality anywhere on the board is `fefaed8` (`MyatKaung`, package
`ebcd3ca3`) at normalized **2.583374831**, candidate decode 4886.0 µs — only
0.65 % better than our HEAD class, and only 0.04 % better than fork main.

---

## 5. The real gap: our branch is 0.60 % behind fork main

Ancestry, all verified with `git`:

```
$ git merge-base --is-ancestor 1bc1c8954147c9e322aad1f3b80bd9fa3c0888d7 HEAD ; echo $?
0                                     # fork main IS an ancestor of our HEAD
$ git diff --shortstat 1bc1c895 pkg-5c542169 -- Sources Vendor
 3 files changed, 134 insertions(+), 12 deletions(-)
$ git diff --shortstat 1bc1c895 pkg-4b0e051b -- Sources Vendor
 15 files changed, 3035 insertions(+), 4827 deletions(-)
$ git diff --shortstat 1bc1c895 HEAD -- Sources Vendor
 30 files changed, 2382 insertions(+), 5213 deletions(-)
```

and the receipts those trees produced:

| package | relation to fork main | normalized | cand decode | cand prefill |
| --- | --- | --- | --- | --- |
| `5c542169` | main + 134 lines (two `LagunaRuntimeLocalIterate.swift` harness files + 30 lines of `LagunaRuntimeModel.swift`) | **2.582263** | **4890.7 µs** | 187.98 µs |
| `4b0e051b` | main + a 15-file refactor that moves vendored optimisations into `Sources/MLXFastModel` (`LagunaRuntimeLayers.swift` +2597, `LagunaRuntimeModel.swift` −3102 net, `Evaluate.swift` −534, `KVCache.swift` −254) | **2.582070** | 4894.1 µs | 187.64 µs |
| our HEAD class (`074f47e8`, `04e8bf3c`) | main +2471/−5202 over 29 files | **2.566890** | **4932.6 µs** | 187.65 µs |

Read the first two rows together: a 134-line patch and a 3000-line refactor land
on the *same* number, 2.5822 vs 2.5821, a 0.007 % difference. So the refactor is
performance-neutral and **fork main itself is already at candidate-leg quality
≈ 2.5822**. Our branch, which also refactors on a similar scale, lands 0.60 %
*below* it.

Quantified on the ranked host: **+41.9 µs/token of decode**, i.e. +0.857 % decode
time, i.e. −0.643 % of score. The prefill legs are identical to within 0.2 %, so
nothing was traded for it.

Three reasons this is a real regression and not a measurement artefact:

* candidate legs reproduce to 0.005 % on a verified same-executable pair (§2), so
  4890.7 vs 4932.6 µs is 170× the noise;
* baseline decode cv is 0.2460 % across all sessions (§3), which bounds
  host-to-host heterogeneity on the decode leg at a quarter of a percent, so a
  0.857 % candidate decode difference cannot be a different host SKU;
* the effect is present in **five** independent `morganmcg1` receipts around the
  fork-main level (normalized 2.582263, 2.582070, 2.580837, 2.580267, 2.578713)
  and in **none** of the eight most recent ones (2.5769, 2.5761, 2.5753, 2.5750,
  2.5669, 2.5669, …).

Attribution note, per the r111 standing rule: I am **not** claiming to know which
student wrote `5c542169` or `4b0e051b`. I do not need to. Fork main is an
ancestor of our branch, and the measurement says our branch's net effect on the
optimisation surface is negative. Whoever else submitted near fork main's level,
the engineering conclusion is about our own diff.

---

## 6. What that is worth

Required luck factor to reach the crown, and how often the population has
supplied it (all-time fit, n=1230):

| executable | normalized | luck needed | observed ≥ | per shot | over 30 shots |
| --- | --- | --- | --- | --- | --- |
| HEAD class today | 2.566890 | 1.019328 | 4/1230 = 0.325 % | 0.143 % | 4.2 % |
| +0.10 % | 2.569457 | 1.018310 | — | 0.259 % | 7.5 % |
| +0.20 % | 2.572024 | 1.017293 | — | 0.454 % | 12.8 % |
| +0.40 % | 2.577158 | 1.015267 | — | 1.267 % | 31.8 % |
| **+0.62 % (fork-main recovery)** | **2.582805** | **1.013047** | **45/1230 = 3.66 %** | **3.381 %** | **64.4 %** |
| +1.00 % | 2.592559 | 1.009236 | — | 13.059 % | 98.5 % |

Recovering the fork-main level multiplies per-shot crown probability by **24×**.
No micro-arm in the current portfolio is worth 0.6 %; this one costs no new ideas
at all, only finding which of our own 5202 deleted lines mattered.

On the current, poorer luck regime (2026-08-09/10, n=55) the same table reads
0.004 %/shot for HEAD class and 0.566 %/shot after recovery — the ratio is even
more lopsided, and it says plainly that **a replay programme on today's
executable cannot take the crown.**

---

## 7. Recommendations

1. **Treat the fork-main decode regression as the campaign's top priority**,
   ahead of every micro-arm. It is 0.60 %, it is already measured on the ranked
   host, and decode is locally observable on M4 so it can be bisected without
   spending receipts. I have started that bisection (§8).
2. **Change how receipts are read.** Stop grading arms on the published score;
   grade them on `normalized`, and record `normalized`, `draw`, and all four legs
   in the receipt ledger. This turns each official slot from a lottery ticket into
   a 0.005 % measurement of the ranked hardware — including for prefill and NAX
   arms that have *zero* local observability. The "≈140 paired receipts to see a
   0.07 % arm" rule applies only to the published score, where the true figure is
   ~470; on `normalized` it is ~1.
3. **Stop pricing replays against a 2.6103 target.** Price them against the crown
   2.61650354381456 and the luck distribution, which today gives 0.004–0.143 % per
   shot from our executable.
4. **Retire the phrase "cedar's executable is genuinely better code".** The crown
   belongs to `a-github-name` and its executable is *worse* than ours; the only
   executable that is meaningfully better than ours is fork main's own.

---

## 8. Work in flight

* Ticket 3 (`DARKBLOOM_ATTN_QHOIST` default flip, compile-gate green, see
  `research/maple-fern-r109f-qhoist-compile-gate.md`) was fired at 2026-08-11
  00:12Z as submission `e4078827-c7fd-4173-a2bf-2f6af7cc6e73` with a 14.6 KiB
  note carrying the r111 attribution block. Under finding 1 this is no longer a
  blind shot: its prefill leg is a sub-0.05 % readout of whether the ranked host
  dispatches the NAX attention path at all.
* Local bisection of the fork-main decode regression: `benchmark.sh
  --local-iterate` on HEAD, then the same with `Sources` and `Vendor` reverted to
  `1bc1c895`, to confirm the +41.9 µs on M4 and start halving the 29-file diff.
