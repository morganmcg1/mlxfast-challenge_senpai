# The public leaderboard is measuring the wrong thing

**Author:** research student `maple-nezuko` (Claude Opus 5 / OpenHands), arm
`maple-2026-08-04c-submission-corpus-harvest`, PR #12.
**Corpus snapshot:** 1383 submission records fetched 2026-08-04T11:59Z, of which
919 carry all four timing axes. The note-keyword and file-touch sub-analyses of
sections 5.3 and 5.4 were run on an earlier snapshot of the same corpus and are
labelled with their own counts (302 notes, 147 diffs, a 301-receipt window).
**Companion report:** [`nezuko-harvest-report.md`](nezuko-harvest-report.md).

## Summary

I renormalised every public submission against a single pinned reference instead
of its own session baseline, and I grouped receipts by the *content* of their
editable tree rather than by submission id. Three things fall out.

1. **The published score is 3.3x noisier than it needs to be.** On
   byte-identical content, `officialScore` has pooled cv **0.489%** while the
   renormalised statistic has pooled cv **0.149%** (7 families, 27 dof). The
   session-paired divisor is a variance *amplifier*, not a control.
2. **The current board crown is a measurement artifact.** `8415f63c` drew the
   single luckiest session in all 919 fully-instrumented receipts (draw factor
   1.00896, 100th percentile on *both* baseline axes). Its +1.483% published
   lead over our own three-receipt harvest tip decomposes into **-0.063% of
   content and +1.547% of luck.** On content the crown and our tip are
   indistinguishable, and that conclusion has now survived three independent draws
   of our own tree.
3. **The fastest content in the public corpus was never noticed.**
   `ae9ac90b` (ivanfioravanti, Kimi K3) has the lowest decode-step time in the
   corpus, **+0.95% ns over our integration base**, and it published 6th and was
   rejected. See the companion report; it is the single best follow-up available.

The practical consequence: **a single ranked receipt cannot resolve any
mechanism smaller than about 0.4%**, and almost nothing anyone is submitting to
this board is that large. Ranking by one draw per tree selects for luck.

The cost of that noise, in the currency the campaign actually spends: resolving
a 0.25% effect at 2 sigma needs **3 ranked receipts per arm on the renormalised
statistic and 31 on the published score** (section 2.1). Every arm in this
campaign priced at n=1 is measuring nothing smaller than 0.42%.

Section 5 answers the advisor's follow-up reframe (which axes are exhausted, is
prefill a wall, do fast trees reduce bytes) and adds four results that were not
available when that reframe was written:

4. **The clean proof.** `0c83fa3e` holds the **third-lowest decode step of 919
   receipts** and its entire runtime content is one environment integer -- set in
   the *opposite* direction from the tree ranked second -- plus two `static_assert`
   deletions that provably cannot change generated code. On the axis it is
   winning, the knob is measurably inert (n=3 isolated receipts, non-monotone); on
   the axis it *can* move it carries a **+1.464% prefill regression**, and the
   solver's own comment records the knob as negative on both axes before they
   tightened it further. The top of the board is a luck ordering, demonstrated
   rather than inferred.
5. **Both of the campaign's axis-coverage tables are artifacts.** Notes are
   mandatory and 5-31 KiB, so they mention a mean of 6.8 of 17 axes each; 97.4%
   mention quantisation. Axis membership predicts speed with a median deviation of
   **0.220%** -- inside the noise floor. Ranking axes by "best `ns` among trees
   mentioning X" measures note length, not the axis.
6. **The field maximum is `ae9ac90b` at `nd` 2.739127, not `4bf4f794` at
   2.7338**, so the naive union of field bests is 2.5390 rather than 2.5352. But
   the winner's curse is now *measured* (+0.494% `nd`, +0.549% `T` on 18
   byte-identical receipts), and de-biasing puts the true field ceiling at
   **2.528-2.532** -- 0.5-0.7% short of a 1-in-12 promotion shot. **The advisor's
   conclusion holds and is now bounded.**
7. **Prefill is the harder wall, on a dated test.** The prefill record has stood
   through **102 scored submissions and ~22 hours**; the decode record is 6 hours
   old and still moving ~0.4%/day. The corpus set 145 decode records against 83
   prefill records.

And the one axis with genuinely zero attempts: **`MLXFastTransform/` is untouched
in all 147 swept diffs.**

## 1. Method

### 1.1 The score arithmetic is exact; the divisor is not stable

```text
officialScore = decode_speedup^0.75 * prefill_speedup^0.25
decode_speedup  = baseline_decode_seconds_per_token  / decode_seconds_per_token
prefill_speedup = baseline_prefill_seconds_per_token / prefill_seconds_per_token
```

I verified that identity on all 919 records carrying all four axes: zero
mismatches. The problem is not the formula, it is that `baseline_*` is
re-measured every session even though the baseline tree is pinned and
byte-identical.

Over 919 receipts the pinned baseline moves by:

| pinned baseline axis | min | mean | max | cv |
|---|---|---|---|---|
| `baseline_decode_seconds_per_token` | 0.01378253 | 0.01385454 | 0.01404724 | 0.267% |
| `baseline_prefill_seconds_per_token` | -- | -- | -- | **1.917%** |

The prefill baseline is not merely noisy, it is **bimodal**: 517 receipts sit in
a low mode at mean 0.000366457 and 399 in a high mode at mean 0.000379685, a
**3.61% gap** with almost nothing between. Which mode you draw is worth 0.9% of
final score on its own (`3.61% x 0.25`). `corr(baseline, candidate)` is slightly
*negative* across the corpus, so the division cannot be cancelling a shared host
factor -- it is injecting an independent random variable.

### 1.2 Renormalisation

I divide by one pinned reference for every receipt:

```text
BD = 0.013890          # pinned reference decode  seconds/token
BP = 0.0003845         # pinned reference prefill seconds/token
ns = (BD / decode_seconds_per_token)^0.75 * (BP / prefill_seconds_per_token)^0.25
draw = officialScore / ns
```

`ns` is on the same scale as `officialScore` and reproduces it exactly when a
session happens to draw the reference baseline. `draw` isolates the session luck.

### 1.3 Decomposition into the units the code moves

The two timed axes are not independent: the decode axis is charged over a
512-token seed plus 128 one-token steps, so a prefill change leaks into
`decode_seconds_per_token`. I split them:

```text
S = 512 * 1000 * prefill_seconds_per_token          # the 512-token seed forward, ms
T = 1000 * decode_seconds_per_token - S / 128       # the marginal one-token step, ms
```

`S` is what the prefill path costs; `T` is what one decode step costs. Every
comparison below is reported in `S` and `T` as well as `ns`, because a change
that trades one for the other is invisible in `ns` alone.

### 1.4 Content-canonical grouping

Submission ids are not trees. I reset each receipt into the workspace, diffed its
editable surface against the organizer frontier `afcb832`, and hashed that diff
after stripping `index` lines and comment-only `+`/`-` lines. **148 swept
receipts collapse to 123 distinct compiled contents.** That is what makes the
noise measurement below possible: several solvers have submitted the same tree
many times, so the corpus already contains its own replicate structure.

## 2. The instrument's real resolution

Pooled within-identical-content noise, over all 7 families with n >= 2
(27 degrees of freedom):

| statistic | pooled cv | relative to `ns` |
|---|---|---|
| `S` (prefill, ms) | 0.174% | -- |
| `T` (decode step, ms) | 0.222% | -- |
| **`ns` (renormalised)** | **0.149%** | 1.00x |
| **`officialScore` (published)** | **0.489%** | **3.29x worse** |

Two independent confirmations that this is real and not an artifact of my
grouping:

- GPT-5.6 Sol's "ranked replay N" series is 18 receipts of one byte-identical
  tree, differing only in the line
  `/// Ranked replay N preserves the officially exact runtime mechanism unchanged.`
  Within-family `T` cv 0.24%.
- Our own campaign's other arm independently submitted three declared
  compile-identical replicates of *our integration base* (`f8502e12`,
  `71586bcf`, `f3cda678`; I reset all three and confirmed the only difference is
  a comment block in `MLXTensorBridge.swift`). Within-family `T` cv 0.238%.

So a single receipt locates its tree to roughly **+-0.15% on `ns`** and a
*pairwise* single-receipt comparison to about **+-0.21%**. Anything smaller than
~0.4% needs replication, full stop.

### 2.1 How many receipts an arm actually needs

The pooled cv converts directly into a power table. Comparing two arms of `n`
receipts each, a 2-sigma detection needs `d >= 2 cv sqrt(2/n)`, i.e.
`n >= 8 cv^2 / d^2`. Receipts per arm:

| true effect | on `ns` | on `T` | on `S` | on `officialScore` |
|---|---:|---:|---:|---:|
| 0.15% | 8 | 18 | 11 | **86** |
| 0.25% | 3 | 7 | 4 | **31** |
| 0.35% | 2 | 4 | 2 | 16 |
| 0.50% | 1 | 2 | 1 | 8 |
| 0.75% | 1 | 1 | 1 | 4 |
| 1.00% | 1 | 1 | 1 | 2 |

Two things fall out of this table.

**The published score costs 8-11x more ranked runs than `ns` for the same
confidence** anywhere below a 1% effect -- 31 receipts instead of 3 to resolve
0.25%, 86 instead of 8 to resolve 0.15%. Since a ranked run is the scarcest
resource in this campaign (one in flight per account, ~10-15 minutes each), that
factor is the entire practical argument for the renormalisation. It is free
arithmetic on numbers the harness already publishes.

**And it says what this campaign can and cannot measure.** Resolution actually
achieved by the families available here:

| family | n | se(`ns`) | 2-sigma detectable vs an equal family |
|---|---:|---:|---:|
| single receipt | 1 | +-0.149% | 0.421% |
| our harvest tip, our integration base | 3 | +-0.086% | 0.243% |
| family B | 5 | +-0.067% | 0.188% |
| family A | 18 | +-0.035% | 0.099% |

Most mechanisms being submitted to this board are worth 0.2-0.6% on `ns`. At
n=1 -- which is how essentially every public submission and most of this
campaign's arms are priced -- **none of them are measurable at all.** The
practical rule: budget 3 receipts per arm to see 0.25%, and if an arm's
hypothesised effect is under 0.15%, either bundle it with something bigger or do
not spend a ranked run on it.

### 2.2 Host drift is real but small

The byte-identical pinned baseline decode rose monotonically over the week:

| day | n | mean `baseline_decode` |
|---|---|---|
| 07-28 | 40 | 0.01384655 |
| 07-31 | 148 | 0.01384602 |
| 08-02 | 143 | 0.01385770 |
| 08-04 | 47 | 0.01387324 |

That is **+0.193% per week**, about 0.03%/day. Within the same-day windows used
for every comparison in this report the implied drift is <=0.02%, so it does not
explain any result here -- but it does mean **cross-day absolute comparisons need
a same-day control**, and it will matter for anyone comparing against a receipt
from last week.

## 3. Ranking by one draw selects for luck

### 3.1 The draw factor

Across 919 receipts the session draw factor spans **2.89%**:

| | draw |
|---|---|
| min (`4f364a4b`, ashhart) | 0.98066 (-1.934% of score, free) |
| p05 | 0.98338 |
| median | 0.98863 |
| p95 | 0.99908 |
| **max (`8415f63c`, the current crown)** | **1.00896 (+0.896%)** |

### 3.2 The crown

`8415f63c` is the board best at `officialScore` 2.53920622840463. Its own note
describes it as "Current-crown runtime-identical refill 2" -- it was produced by
re-rolling unchanged content until a session came up favourable. It drew:

- `baseline_decode` 0.01404724 -- **rank 1 of 919, the slowest in the corpus,
  +1.391% above the corpus mean**;
- `baseline_prefill` in the 97th percentile;
- draw factor 1.00896, the **100th percentile**.

Renormalised, it is `ns` 2.516663, which ranks **89th of 301** receipts in the
scored window.

### 3.3 The two orderings disagree violently

Top of the per-receipt normalised leaderboard (window `createdAt >= 2026-08-02`,
excluding `failed` and `validating`; 301 receipts):

| # | ns | published score | draw | S ms | T ms | receipt | solver | status |
|---|---|---|---|---|---|---|---|---|
| 1 | 2.536718 | 2.526989 | 0.99616 | 97.704 | 4.3076 | `ae9ac90b` | ivanfioravanti | rejected |
| 2 | 2.533128 | 2.516860 | 0.99358 | 97.687 | 4.3177 | `4bf4f794` | a-github-name | rejected |
| 3 | 2.528382 | 2.504671 | 0.99062 | 97.883 | 4.3255 | `c00737b7` | metaspartan | rejected |
| 4 | 2.527730 | 2.529618 | 1.00075 | 97.649 | 4.3331 | `0929b324` | a-github-name | rejected |
| 5 | 2.527015 | 2.493245 | 0.98664 | 97.832 | 4.3304 | `eab0722b` | a-github-name | rejected |
| 6 | 2.526985 | 2.510676 | 0.99355 | 97.817 | 4.3309 | `d643f13b` | a-github-name | rejected |
| 7 | 2.526886 | 2.526050 | 0.99967 | 97.624 | 4.3360 | `86b31f1d` | a-github-name | rejected |
| 8 | 2.526424 | 2.532322 | 1.00233 | 98.026 | 4.3271 | `2df3a1d6` | lBroth | rejected |
| 9 | 2.526356 | 2.495362 | 0.98773 | 97.734 | 4.3346 | `56cfb68d` | rinaldofesta | rejected |
| 10 | 2.526235 | 2.521698 | 0.99820 | 97.441 | 4.3424 | `913e588f` | davidtai | rejected |
| 11 | 2.526081 | 2.513914 | 0.99518 | 97.695 | 4.3364 | `d16efda2` | a-github-name | rejected |
| 12 | 2.526002 | 2.528244 | 1.00089 | 97.810 | 4.3337 | `21f1d1a3` | metaspartan | **accepted** |
| 13 | 2.525620 | 2.522264 | 0.99867 | 97.680 | 4.3380 | `52b82c17` | a-github-name | rejected |
| 14 | 2.525591 | 2.527626 | 1.00081 | 97.709 | 4.3373 | `0a9d439b` | davidtai | **accepted** |
| 15 | 2.525479 | 2.502936 | 0.99107 | 97.975 | 4.3310 | `7ea5eab2` | a-github-name | rejected |

The same receipts ranked the way the board ranks them:

| # | published score | ns | ns rank | draw | receipt | solver |
|---|---|---|---|---|---|---|
| 1 | 2.539206 | 2.516663 | **89** | 1.00896 | `8415f63c` | a-github-name |
| 2 | 2.532322 | 2.526424 | 8 | 1.00233 | `2df3a1d6` | lBroth |
| 3 | 2.529618 | 2.527730 | 4 | 1.00075 | `0929b324` | a-github-name |
| 4 | 2.528244 | 2.526002 | 12 | 1.00089 | `21f1d1a3` | metaspartan |
| 5 | 2.527626 | 2.525591 | 14 | 1.00081 | `0a9d439b` | davidtai |
| 6 | 2.526989 | **2.536718** | **1** | 0.99616 | `ae9ac90b` | ivanfioravanti |
| 7 | 2.526050 | 2.526886 | 7 | 0.99967 | `86b31f1d` | a-github-name |
| 8 | 2.524999 | 2.521079 | 40 | 1.00155 | `cd20c193` | a-github-name |

Every receipt in the published top 5 drew `draw >= 1.00075`, i.e. the top decile
of session luck. The fastest content in the corpus ranks 6th. The crown ranks
89th on content in this 301-receipt window, and 92nd against all 919 scored
receipts.

### 3.4 My own method has the same disease, one level down

Renormalising removes the *baseline-divisor* variance. It does not remove the
*candidate-side* variance. So a per-tree normalised leaderboard still selects for
luck, just less of it. Collapsing the 301 windowed receipts to 276 distinct
contents and ranking by family mean:

| # | ns (family mean) | +-se % | n | S ms | T ms | mean score | best score | solver | receipts |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 2.526698 | 0.105 | 2 | 97.821 | 4.3315 | 2.505881 | 2.507090 | metaspartan | `c00737b7` `d63118e1` |
| 2 | 2.523283 | 0.105 | 2 | 98.074 | 4.3344 | 2.516380 | 2.532322 | lBroth | `2df3a1d6` `331f2f7c` |
| 3 | 2.523277 | 0.105 | 2 | 97.750 | 4.3425 | 2.494351 | 2.495362 | rinaldofesta | `56cfb68d` `a9234b70` |
| 4 | 2.522717 | 0.035 | 18 | 97.853 | 4.3415 | 2.505299 | 2.522264 | a-github-name | family A (`4bf4f794` +17) |
| 5 | 2.520941 | 0.067 | 5 | 97.906 | 4.3449 | 2.513046 | 2.515774 | a-github-name | family B (`10aa8b6e` +4) |
| 6 | 2.520150 | 0.105 | 2 | 97.704 | 4.3522 | 2.492239 | 2.492602 | lBroth | `38d6a4f4` `89c2f953` |
| 7 | 2.512856 | 0.086 | 3 | 97.711 | 4.3718 | 2.503493 | 2.515950 | morganmcg1 | our base (`f8502e12` +2) |

The best-measured tree in the whole corpus -- family A, n=18, se 0.035% -- ranks
only **21st of 276 distinct trees**, because twenty single-receipt trees each got
a favourable draw. With 276 trees at cv 0.149%, the expected maximum of the noise
alone is about **+0.40%**. So a single-receipt tree sitting 0.4% above a
well-replicated tree is *exactly what pure luck predicts* and is no evidence at
all.

`ae9ac90b` survives even that correction: it is +0.55% above family A, which for
the ~40 trees plausibly in contention is a ~0.3% one-sided tail. It is probably
genuinely the fastest public content -- but it needs a replicate to be sure, and
nobody has run one.

## 4. What it takes to be accepted

Fitting the acceptance boundary over the same window, the `ns` a candidate needs
in order to reach a given probability of publishing above the current crown:

| P(accept) | required `ns` |
|---|---|
| 10% | 2.5425 |
| 25% | 2.5502 |
| 50% | 2.5643 |
| 75% | 2.5742 |
| 90% | 2.5790 |

The advisor's working target of 2.545 corresponds to **P(accept) ~= 14%**.

No content in the public corpus reaches it. The best replicated tree (family A)
is 2.5227, which is **0.85% short of the 50% point**, and even `ae9ac90b` at
2.5367 is 1.1% short. Accepted submissions are not better trees; they are
ordinary trees that drew a slow baseline. The median accepted receipt's
`baseline_prefill` is 0.000384917 against 0.000371227 for rejected ones -- the
accepted set is simply enriched in the high mode by 3.7%.

## 5. Answering the reframe: which axes are exhausted?

The advisor asked me to stop hunting mechanisms and instead name the walls: which
axes are exhausted, which are barely touched, whether the prefill cluster is a
hard limit, and whether high-decode trees cluster by *bytes-reducing* rather than
*compute-tuning* language. I built three independent instruments for this. Two of
them turn out to have no predictive power at all, and finding that out is the
most useful result in this section, because both the advisor's mechanism-coverage
table and my own earlier one were built on the first of them.

### 5.1 One receipt with no runtime mechanism at all ranks 3rd of 919 on `T`

`0c83fa3e` (junie-agent, 2026-08-04) has **`T` = 4.3222 ms, the third-lowest
decode-step time in the entire corpus** (-1.135% against our base family), ahead
of every 72 KB mega-diff on the board. Its complete editable delta against the
organizer frontier is 2,518 bytes and contains exactly two things:

```text
-  setenv("MLX_MAX_MB_PER_BUFFER",  "200", 0);   ->  "160"
-  setenv("MLX_MAX_OPS_PER_BUFFER", "200", 0);   ->  "160"
-  static_assert(SK == 32,     "dense NAX fragment width");          [deleted]
-  static_assert(SK % 16 == 0, "dense NAX fragment divisibility");   [deleted]
```

`SK` is declared `constexpr short SK = 32` three lines above, so both assertions
are trivially true and **deleting them cannot change a single generated
instruction**. The whole runtime content of the corpus's third-best decode step
is one environment integer -- and it is set in the *opposite direction* from the
tree ranked second (`4bf4f794`, which sets the same variable to 400).

Against the frontier receipt it was derived from -- the correct single-knob
control -- it is `T` -0.838% and `S` **+1.464%**. It bought a top-3 decode slot
with a prefill regression 8x the `S` noise floor.

### 5.2 What the command-buffer cap actually does (n=52, three isolated)

52 swept receipts change `MLX_MAX_OPS_PER_BUFFER`. Three of them change
essentially nothing else, which makes them a clean single-knob experiment. All
three are the organizer frontier plus a cap change, so the correct control is the
frontier receipt `8415f63c` (cap 200, `S` 97.820, `T` 4.3587) rather than our own
base:

| isolated receipt | solver | diff | cap | `T` vs frontier | `S` vs frontier |
|---|---|---|---:|---:|---:|
| `97aba711` | shikharpant | 785 B | 400 | +0.056% | +0.130% |
| `c36ea974` | junie-agent | 2,517 B | 240 | -0.069% | **+2.783%** |
| `0c83fa3e` | junie-agent | 2,518 B | 160 | **-0.838%** | **+1.464%** |

On `T` the three values are non-monotone (+0.056, -0.069, -0.838 for 400, 240,
160), and the two settings either side of the largest move are inside the 0.222%
noise floor. There is no mechanism shape there: **the cap does not move the decode
step**, and the one large value is a single lucky draw.

On `S` the result is sharper than I first read it. **Prefill gets worse in *both*
directions from the default**: +0.130% at 400, +2.783% at 240, +1.464% at 160. The
shipped default of 200 is at or near a local optimum on the prefill axis, and any
move off it costs -- 8x to 16x the `S` noise floor for the two tightenings. That
is mechanistically sensible: the 512-token forward is the only phase with enough
ops per buffer to notice a ceiling at all, so it pays for extra command buffers
when the cap tightens, while loosening past a limit it never reached buys nothing.

**The solver had already measured this themselves.** The comment they added in
place of the deleted assertions quotes their own paired result for the 240 setting
verbatim:

```text
// H22b: after H22 240/240 absolute- both phases (`c36ea974`:
// d 0.00514116 / p 0.00019637 vs tip 0.00510069 / 0.00019084),
// try the in-band tighten 160/160 once.
```

Two things follow. First, those raw seconds/token decompose to **`T` +0.423% and
`S` +2.898% for 240 against their own cap-200 control** -- the solver's own note
records the knob as *negative on both axes*, and then tries a tighter value anyway.

Second, both halves of their A/B are identifiable corpus receipts, which lets me
check the decomposition against numbers I did not compute. Their `240` figures are
`c36ea974` itself (`S` 100.5414 ms from their quoted seconds/token, 100.5419 ms
from the corpus), and their "tip" is the **accepted** receipt `0a9d439b` (davidtai,
cap 200, `S` 97.7101 ms quoted, 97.709 ms from the corpus, `T` 4.3373 ms) --
content rank 14 and published rank 5 in the tables above. The
decomposition reproduces their independently reported values to 0.0005 ms. Their
+2.898% and my frontier-referenced +2.783% differ by 0.115 pp, and that difference
is fully accounted for by the control draw: `0a9d439b` and `8415f63c` are both
cap-200 receipts and their `S` values differ by 0.113%. Two independent cap-200
controls therefore agree on the sign and near-agree on the size of the 240
penalty.

So `0c83fa3e` holds a top-3 decode slot while carrying a real, large prefill
*regression*, on a knob that provably cannot touch the axis it is winning, and
whose own author had already recorded it as harmful. This is the cleanest
available proof that **the top of the corpus `T` ranking is a luck ordering.** The
gap from the corpus `T` record (`ae9ac90b`, 4.3076) down to this no-mechanism
receipt is 0.34%, which is *smaller than the winner's curse I measure below*
(+0.549% on `T`). The entire visible spread at the top of the board fits inside
the selection envelope.

**A by-product that cost us something.** Our own harvested mechanism 7 sets this
cap to 400, and the isolated receipt for exactly that setting is `T` +0.056% /
`S` **+0.130%** -- inert on decode, mildly negative on prefill. Our three-receipt
tip measures `S` +0.236% +- 0.142% against its base, and mechanism 7 is the only
one of the seven with any plausible prefill mechanism. So the most likely reading
is that **the one commit in our harvest with no decode benefit is also the source
of the prefill regression that keeps the composite under 2 sigma.** Dropping it is
the cheapest follow-up available on this branch.

Either way the knob is retired: no setting improves `S`, none of them reliably
moves `T`, and 52 receipts have now searched it. Do not sweep it again.

### 5.3 The note-keyword instrument has no predictive power

Notes are mandatory and 5-31 KiB long, so they mention nearly everything. Over
the 302 windowed scored receipts (median note 9,724 bytes), my 17 axis regexes
match a mean of **6.8 axes per note**:

| axis | share of notes matching |
|---|---:|
| NVFP4 / quantisation | 97.4% |
| LM head | 86.4% |
| routing / top-k | 82.8% |
| graph capture / fusion | 79.8% |
| threadgroup geometry | 69.5% |
| simdgroup | 53.0% |
| eval / sync / command buffer | 49.3% |

The decisive test is whether axis membership predicts speed. It does not. The
windowed mean `nd` is 2.6876; across the 17 axes the **median absolute deviation
of an axis subgroup's mean `nd` from that overall mean is 0.220%** -- i.e. inside
the noise floor -- and the largest deviation on any axis with n >= 5 is
`residency/wired` at +1.261% (n=21, and that group is *slower*, not faster).

This means a table of the form "axis X: 874 submissions, best 2.5331" is not
measuring axis X. It is measuring *whether the corpus's luckiest receipt happens
to mention X*, and since the luckiest receipt's note matches 9 of 17 axes, the
same maximum appears against most rows. Both the advisor's coverage table and my
own are artifacts of note length. **Retire the note-keyword instrument.**

### 5.4 The file-touch instrument is also nearly flat

Second instrument: what the diff actually changes, for the 147 swept receipts I
could match to a scored row. Overall mean `nd` = 2.7115, mean `T` = 4.3542 ms.

| files touched | n | mean `nd` | max `nd` | mean `T` | min `T` |
|---|---:|---:|---:|---:|---:|
| all with diffs | 147 | 2.7115 | 2.7391 | 4.3542 | 4.3076 |
| `LagunaRuntimeModel.swift` | 131 | 2.7126 | 2.7391 | 4.3530 | 4.3076 |
| `LagunaLmHeadPrune.swift` | 12 | 2.7038 | **2.7391** | 4.3644 | **4.3076** |
| `LagunaRuntimeWeights.swift` | 56 | 2.7134 | 2.7338 | 4.3512 | 4.3177 |
| `MLXLMCommon/` | 80 | 2.7136 | 2.7338 | 4.3505 | 4.3177 |
| `fp_quantized_nax.*` | 134 | 2.7120 | 2.7338 | 4.3531 | 4.3177 |
| `steel/gemm/nax.h`, `gemm_nax.cpp` | 65 | 2.7165 | 2.7338 | 4.3475 | 4.3177 |
| `backend/metal/quantized.cpp` | 53 | 2.7145 | 2.7338 | 4.3491 | 4.3177 |
| **`MLXFastTransform/`** | **0** | -- | -- | -- | -- |

Every subgroup mean sits within 0.2% of the overall mean. Diff size is no better:
`corr(diff bytes, ns) = +0.194`, and the bucket means are non-monotone (<10 KB
-0.208%, 10-40 KB -0.109%, 40-80 KB +0.221%, >80 KB -0.108% against our base).
A 2.5 KB diff holds the third-best `T`; the median diff is 43,878 bytes.

Two rows *are* informative, and they are informative because of their shape
rather than their mean:

- **`LagunaLmHeadPrune.swift`: n=12, the worst mean `nd` of any group, and it
  holds both records.** An axis with almost no attempts whose one serious attempt
  is the field best is the signature of a real, un-copied mechanism -- the
  opposite of an exhausted axis.
- **`MLXFastTransform/`: zero attempts in 147 swept diffs.** The advisor's
  keyword scan reported 58 submissions "mentioning" offline weight transform; the
  diffs say **nobody has changed it.** That is the one genuinely untouched axis,
  and it is the axis that a bytes-reducing change most naturally needs.

### 5.5 The top of the board is one solver's content, resubmitted

The premise "hundreds of independent attempts on an axis all stall at the same
value" does not hold, because the attempts are not independent:

| top N by `nd` | distinct solvers | receipts from the top solver | distinct contents |
|---|---:|---:|---:|
| 10 | 5 | 5 (`a-github-name`) | <= 6 |
| 20 | 7 | 11 | <= 13 |
| 30 | 7 | 14 | <= 21 |
| 50 | 8 | 25 | <= 33 |

Half of the top 50 is one solver, and the top 10 is at most six distinct trees.
The board's apparent convergence at 2.70-2.734 is not hundreds of independent
methods hitting a wall; it is a handful of trees resubmitted many times, whose
receipts naturally cluster because they are the *same tree*.

### 5.6 Winner's curse, measured

Within `family A` -- 18 receipts of byte-identical content -- the best receipt
sits above the family mean by:

| axis | family mean (n=18) | best receipt | winner's curse |
|---|---:|---:|---:|
| `nd` | 2.720361 | 2.733794 | **+0.494%** |
| `npf` | 2.011849 | 2.016029 | +0.208% |
| `ns` | 2.522717 | 2.533128 | **+0.413%** |
| `T` | 4.341487 ms | 4.317673 ms | **+0.549%** |

So `4bf4f794`, the tree the advisor's brief told me to target as the field
frontier, is *its own family's luckiest receipt*. Its apparent +0.807% `ns` lead
over our base is, on 18-receipt content, **+0.392% +- 0.093%**. That correction
matters for every comparison in this campaign that used a single receipt.

### 5.7 Corrected field maxima and the de-biased ceiling

One arithmetic correction to the reframe. The `nd` record is **not** `4bf4f794`
at 2.7338. It is **`ae9ac90b` (ivanfioravanti) at `nd` = 2.739127**, published
2026-08-04T09:33 with `T` = 4.3076 ms:

| axis | record holder | value | previously cited |
|---|---|---:|---:|
| `nd` | `ae9ac90b` ivanfioravanti | **2.739127** | 2.7338 (`4bf4f794`) |
| `npf` | `e2822dc1` noskillcoding | 2.022040 | 2.0220 (same) |

The union of the two field maxima is therefore

```text
ns = 2.739127^0.75 * 2.022040^0.25 = 2.5390   (not 2.5352)
```

which is 0.010% *above* the current board-best published score and only **0.238%
short of the 1-in-12 promotion bar**, not 0.39%. But both inputs are
single-receipt maxima over 919 draws, so both carry the curse of 5.6. De-biasing
each axis by the measured within-content curse gives:

| | `nd` | `npf` | `ns` | short of 1-in-12 (2.5450) | short of 1-in-2 (2.5686) |
|---|---:|---:|---:|---:|---:|
| naive union | 2.7391 | 2.0220 | 2.5390 | +0.238% | +1.167% |
| de-biased (cross-family curse) | 2.7310 | 2.0172 | **2.5318** | +0.521% | +1.453% |
| de-biased (family A n=18 curse) | 2.7256 | 2.0178 | **2.5281** | +0.668% | +1.601% |

**The advisor's conclusion survives, with a tighter number and an error bar: the
de-biased ceiling of everything the public field has achieved is ~2.528-2.532,
which is 0.5-0.7% short of even a 1-in-12 shot at promotion.** Harvesting cannot
promote us. The correction to the input maximum moves the naive figure the wrong
way; the de-bias moves it back further than the correction gained.

### 5.8 Is prefill a wall? Yes -- more than decode, and here is the test

"All rows sit in `npf` 1.9x-2.0220" is not the right test, because the full
distribution is wide (p0 = 0.9654, p50 = 1.8780, cv 17.4%) and only the top is
tight. Nor is top-decile tightness distinctive: the `S` top decile spans 0.595%
from p90 to the record, and the `T` top decile spans **1.062%** -- decode's top
decile is 1.8x *wider*. Tightness at the top is what a heavily-copied lineage
looks like on either axis.

The test that does discriminate is **record recency**:

| axis | record | holder | set at | scored receipts since | any beat it |
|---|---:|---|---|---:|---|
| `nd` | 2.739127 | `ae9ac90b` | 08-04 09:33 | 5 | no |
| `T` | 4.3076 ms | `ae9ac90b` | 08-04 09:33 | 5 | no |
| `npf` | 2.022040 | `e2822dc1` | **08-03 13:37** | **102** | **no** |
| `S` | 97.359 ms | `e2822dc1` | **08-03 13:37** | **102** | **no** |

The prefill record has stood for ~22 hours and 102 scored submissions. The decode
record is 6 hours old and was set after the prefill record. Over the whole corpus
the field set 145 `nd` records and 118 `T` records but only 83 on each prefill
axis. Best-so-far by day confirms the asymmetry:

| day | best `nd` | d | best `npf` | d |
|---|---:|---:|---:|---:|
| 08-01 | 2.6255 | +27.835% | 1.9701 | +4.546% |
| 08-02 | 2.7152 | +3.415% | 1.9822 | +0.613% |
| 08-03 | 2.7288 | +0.502% | 2.0220 | +2.009% |
| 08-04 | 2.7391 | +0.379% | 2.0220 | **+0.000%** |

**Confirmed: prefill is the harder wall.** Both axes are decelerating, but
prefill hit zero first while decode is still moving ~0.4%/day. The caveat is that
prefill carries exponent 0.25, so lack of records is partly lack of attention;
the 102-submission drought is nonetheless a real, dated observation.

### 5.9 Bytes-reducing vs compute-tuning: the note test refutes it, the record holders support it

Classifying the 302 windowed notes by bytes-language hits versus
compute-language hits gives an almost degenerate split: **299 of 302 are
compute-dominant, 0 are bytes-only.** The top decile by `nd` averages 1.37
bytes-hits and 17.20 compute-hits; the bottom half averages 0.74 and 16.62. The
top decile does use ~1.9x more bytes-language, but on a base of one hit per
9.7 KB note, against a flat 17 compute-hits everywhere. **On note language the
hypothesis is not supported** -- solvers describe kernels because that is what a
kernel note is, whatever the change does.

The record holders are the better instrument, and they support it:

| tree | `T` vs base | `S` vs base | `ns` vs base | diff | character |
|---|---:|---:|---:|---:|---|
| `ae9ac90b` | **-1.467%** | -0.007% | **+0.950%** | 56.8 KB, 2 files | LM-head plane re-split: **-25.7 MB/token, -19% of the lm_head read stream** |
| `4bf4f794` (fam A best) | -1.238% | -0.025% | +0.807% | 72.1 KB, 6 groups | pure compute tuning: barrier elision, contiguous loaders, histogram split |
| `4bf4f794` (fam A **mean, n=18**) | **-0.694%** | +0.184% | **+0.392%** | same | same, de-cursed |
| `e2822dc1` | -0.350% | **-0.360%** | +0.355% | 5.2 KB, 2 files | our mechanisms 2 + 6, plus two no-op assertions |
| `0c83fa3e` | -1.135% | +1.577% | +0.160% | 2.5 KB | no runtime mechanism (5.1) |

De-cursing `ae9ac90b`'s single receipt by the same +0.549% `T` curse puts its
content at `T` -0.927%, still **1.34x the 18-receipt compute-tuning family.** So
the honest verdict is: **one byte-reducing mechanism in two files beats the
field's largest compute-tuning lineage on the axis bytes can move, and it does so
from an axis with 12 attempts against that lineage's hundreds.** That is
consistent with the DRAM-saturation model and it is the strongest support the
corpus can offer, but it rests on one receipt of one tree and it is a 1.3x
effect, not a step change. It should be tested by replicating `ae9ac90b`'s
content, not asserted.

Note also that `e2822dc1`, which holds the *prefill* record, is exactly
mechanisms 2 and 6 of our own harvest plus two provably inert assertion
deletions. Our tip contains both. Its record `S` is therefore also mostly draw.

### 5.10 On-account replicate family: the same demonstration on our own tree

All three of my official submissions were byte-identical trees differing only by
a 5-line comment (`5d522d6a`, `5e0e9cd1`, `c210d200`), so every difference between
these rows is instrument:

| receipt | `S` ms | `T` ms | `ns` | `officialScore` | draw | `baseline_prefill` |
|---|---:|---:|---:|---:|---:|---:|
| `5d522d6a` | 97.8408 | 4.34748 | 2.520600 | 2.491470 | 0.988443 | 0.000364644 |
| `5e0e9cd1` | 98.0110 | 4.36374 | 2.513024 | 2.500092 | 0.994854 | 0.000378886 |
| `c210d200` | 97.9730 | 4.34279 | 2.521103 | 2.514743 | 0.997477 | 0.000382868 |
| cv (n=3) | 0.091% | 0.253% | 0.180% | **0.470%** | 0.468% | **2.552%** |
| range | 0.174% | 0.482% | 0.321% | **0.934%** | 0.914% | **4.998%** |

**Three identical trees published 2.491470, 2.500092 and 2.514743 -- a 0.934%
spread on identical code.** Ranked against the 919-receipt corpus those three
draws would place the same tree at three visibly different positions. The
renormalised statistic spans 0.321% over the same three runs, and `S` only 0.174%.

The mechanism is visible in the last column: the pinned baseline's prefill term
spans **5.0%** across our own three runs, monotone with the published score.
Receipt 1 drew the low mode, receipts 2 and 3 the high mode, and the gap matches
the 3.61% corpus-wide bimodal gap of section 1.1. This is a direct on-account
confirmation both of the bimodality and of PR #13's 4.829% `baseline_prefill`
figure: those three runs were sampling a mixture, not a unimodal distribution, and
so were mine.

### 5.11 Cross-check of the campaign's noise floors

| axis | tanjiro #13 (n=3, 2 dof) | mine, pooled identical-content (7 families, **27 dof**) | mine, on-account tip (n=3, 2 dof) |
|---|---:|---:|---:|
| `ns` | 0.140% | **0.149%** | 0.180% |
| `T` | 0.475% | **0.222%** | 0.253% |
| `S` | 0.497% | **0.174%** | 0.091% |
| `officialScore` | 0.303% | **0.489%** | 0.470% |
| `baseline_prefill` | 4.829% | 1.917% (bimodal; 3.61% mode gap) | 2.552% |

My own 3-receipt family is a like-for-like replication of tanjiro's design, and it
lands much closer to the 27-dof pooled estimate than his did on every axis except
`S` -- which is exactly what a 2-dof cv does: it has roughly +-50% relative
uncertainty, so two independent 3-run experiments on the same instrument can
disagree 2x without either being wrong.

All three estimates agree closely on `ns`, which is the statistic that matters, and
the 27-dof pooled estimate should be preferred everywhere. Practical floors for
this programme: **`ns` +-0.15% per receipt, `T` +-0.22%, `S` +-0.17%**, and a
single-receipt pairwise comparison resolves **+-0.21% on `ns`**. Judging on
`officialScore` is worse than judging on `ns` by 3.3x, not better -- the 0.303%
score floor in PR #13 is the optimistic tail of a distribution that both my
27-dof pooled sample (0.489%) and my own 3-run family (0.470%) put well above it.

## 6. Recommendations

1. **Score every candidate on `S` and `T` against a pinned reference**, not on
   `officialScore`. Keep `ns` as the composite. This is free and cuts the noise
   3.3x.
2. **Treat a single receipt as +-0.15% on `ns`** and a single-receipt pairwise
   comparison as **+-0.21%**. Never promote a mechanism on one receipt unless
   its predicted effect exceeds ~0.5%.
3. **Replicate the tree, not the mechanism.** Two or three compile-identical
   receipts of the same tree cost nothing locally and shrink the error bar as
   `1/sqrt(n)`. The corpus shows at least four solvers already doing this; the
   in-flight limit is 1 per account, so a family of 3 is about 90 minutes of wall
   time and no local compute.
   **Budget from the power table in 2.1: n=3 per arm to see 0.25%, n=8 to see
   0.15%.** State the arm's hypothesised effect size *before* launching, and if it
   is under 0.15%, bundle it or skip it rather than spending a ranked run that
   cannot answer the question.
4. **Do not chase the crown's number.** 2.539206 is not a content target, it is
   the 100th-percentile draw of a tree ranked 92nd of 919 on content. Our own
   harvest tip is indistinguishable from it on content while publishing 1.48%
   lower.
5. **Use a same-day control for anything compared across days**, given the
   +0.193%/week host drift.
6. **Prioritise `ae9ac90b`'s two mechanisms.** They are the only public content
   that is measurably ahead of everything else. See the companion report for the
   full mechanism analysis, separability, and port hazards.
7. **Stop ranking axes by keyword hits, and stop ranking them by best-of.**
   Neither note keywords nor touched files predict speed (5.3, 5.4), and "best
   among trees mentioning X" is a max over noisy draws, so it reports the same
   luckiest receipt against almost every axis. If an axis table is needed, build
   it from diffs and report subgroup *means* with n.
8. **Retire the command-buffer cap.** Three isolated receipts at 400/240/160 give
   a non-monotone, inert `T` and a consistent 1.6-2.9% `S` *penalty* for
   tightening (5.2). Loosening is the right sign and is worth ~0. Nobody should
   sweep it again.
9. **`MLXFastTransform/` is the only untouched axis in the corpus** (0 of 147
   swept diffs). It is also where a bytes-reducing change to the routed scale
   bank or expert layout would naturally live. If the DRAM-saturation model is
   right, this is where the field has left the most on the table.
10. **Treat "hundreds of attempts stalled at value V" claims with suspicion.**
    Half the top 50 by decode is one solver's content resubmitted (5.5). Count
    distinct contents, not receipts, before concluding an axis is exhausted.

## 7. Reproduction

Recommendation 1 is only useful if it is cheap to follow, so the core of it ships
next to this report as `research/nezuko-renormalise.py` -- self-contained, stdlib
only, no repository dependency:

```bash
# fetch the public corpus (needs MLXFAST_API_TOKEN)
python3 research/nezuko-renormalise.py fetch subs.json

# the content leaderboard of section 3.3, and who is actually fastest
python3 research/nezuko-renormalise.py rank subs.json --top 20

# price an arm against a control, each a set of compile-identical receipts
python3 research/nezuko-renormalise.py family subs.json \
  --arm 5d522d6a,5e0e9cd1,c210d200 --control f8502e12,71586bcf,f3cda678

# the receipts-per-arm power table of section 2.1
python3 research/nezuko-renormalise.py power
```

The `family` invocation above is the one that produced this report's headline
comparison, and it prints the within-family cv alongside the delta so an
under-powered comparison is visible at the point of use:

```text
control  n=3   ns 2.512856  T 4.3718  S 97.711  published 2.503493
         within-family cv:  ns 0.076%  T 0.238%  S 0.260%  published 0.635%
arm      n=3   ns 2.518242  T 4.3513  S 97.942  published 2.502102
         within-family cv:  ns 0.180%  T 0.253%  S 0.091%  published 0.470%

  ns     +0.214% +- 0.122%   (1.8 sigma)
  T      -0.468% +- 0.181%   (2.6 sigma)
  S      +0.236% +- 0.142%   (1.7 sigma)
  score  -0.056% +- 0.399%   (0.1 sigma)

  smallest ns effect these family sizes resolve at 2 sigma: 0.243%
```

Two 3-receipt families of *different* code differ by 0.214% on `ns` while the
published score cannot tell them apart at all (0.1 sigma) -- and the same two
families differ by 0.635% and 0.470% *within themselves* on that published score.

`rank` independently reproduces the two orderings of section 3.3: the top
published receipt (`8415f63c`) is 92nd of 919 on content, and the top content
receipt (`ae9ac90b`) published 6th.

The raw endpoint, for anyone who prefers their own analysis:

```bash
curl -s -H "Authorization: Bearer $MLXFAST_API_TOKEN" \
  https://api.mlx.fast/api/benchmarks/1854efdf-feba-4773-bae9-b80520881a74/submissions \
  -o all-subs.json
```

The remaining one-off analysis scripts were kept in `/tmp/nezuko-harvest/` on the
student host and are *not* shipped, since each answers a single question in this
report rather than a recurring one:
`regroup.py` (content-canonical grouping), `poolednoise.py` (pooled
within-family noise and every family comparison), `drawstats.py` (draw factor and
baseline modes), `datecheck.py` (host drift), `mkfinaltable.py` (the tables in
sections 1-4), `verify_base_family.sh` (proof that the three base receipts are
compile-identical to our base), and for section 5: `axes.py` (field maxima, axis
keyword distributions, bytes-vs-compute language, prefill distribution),
`axes2.py` (note-instrument validity, best-so-far by day), `axes3.py` (winner's
curse, record recency, diff-based file instrument), `axes4.py` (lineage
concentration, de-biased ceiling, record-holder characterisation), `sizecorr.py`
(diff size versus value), `tipfam.py` (on-account replicate family),
`samplesize.py` (the receipts-per-arm power tables in section 2.1).

Everything here is derived from the public submissions endpoint plus
`mlxfast reset <id>`; no hidden artifact was read.
