# In 926 public receipts, nobody has moved prefill. Decode has moved 6 sigma.

Reproduce with `python3 research/field-axis-asymmetry.py` (needs
`MLXFAST_API_TOKEN`; the endpoint is
`GET /api/benchmarks/{ref}/submissions`, which returns the **whole public
field's** receipts with full `officialMetrics`, not just our own).

## Method

The ruler is our own three byte-identical receipts (`f8502e12`, `71586bcf`,
`f3cda678`). They are the same archive measured three times, so their spread is
the *instrument's* 1-sigma and nothing else:

```
S 97.711 +- 0.254 ms (0.260%)      T 4.3718 +- 0.0104 ms (0.238%)
```

Then ask, of all 926 public receipts carrying metrics: how many beat that
unchanged tree on each axis, in units of that sigma?

### What the 926 actually are

Status partitions the field exactly, and it is worth knowing which population
this is measured over:

```
status      count   carries officialMetrics
accepted      140   yes
rejected      786   yes
failed        467   no
validating      3   no        (in flight at fetch time)
```

`140 + 786 = 926`, with no exceptions in either direction. So `rejected` means
**rejected on the ranking/calibration band, not on correctness** — those runs
cleared every hidden gate and were fully measured. `failed` is the correctness
bucket and carries no metrics at all.

The 926 is therefore precisely "every submission that passed all gates and got
timed on the ranked host". That is the right denominator for this question: it
excludes broken trees without excluding unlucky ones, and it means a null on
prefill is a null over every *correct* attempt the field has made.

Our own three control receipts are 3 of the 926 (0.3%). They cannot beat
themselves by 2 sigma, so they do not affect any count below.

## Result

```
S (prefill) -- receipts beating our unchanged tree
  < mean -  1 sigma (97.4566):     2 / 926  ( 0.22%)
  < mean -  2 sigma (97.2022):     0 / 926  ( 0.00%)
  < mean -  3 sigma (96.9478):     0 / 926  ( 0.00%)
  best public value 97.3591 = 1.38 sigma better

T (decode) -- receipts beating our unchanged tree
  < mean -  1 sigma (4.3614):    138 / 926  (14.90%)
  < mean -  2 sigma (4.3509):     74 / 926  ( 7.99%)
  < mean -  3 sigma (4.3405):     34 / 926  ( 3.67%)
  < mean -  5 sigma (4.3197):      3 / 926  ( 0.32%)
  best public value 4.3076 = 6.15 sigma better
```

**Not one receipt in 926 beats our prefill by even two sigma. The best is 1.38
sigma, i.e. inside noise. On decode, 74 receipts clear two sigma, 34 clear
three, and the best clears six.**

The asymmetry is the whole point, and it is self-controlling: it is the *same
population*, measured on the *same instrument*, in the *same sessions*. A
population that demonstrably produced 6-sigma decode wins produced zero prefill
wins. So "prefill is untouched" cannot be explained by the instrument being too
coarse, by the population being uncompetitive, or by our tree being unusually
good — the decode column rules out each of those in turn.

## Frontier spread: the top of the leaderboard is noise

```
top-K by ns    S sigma   vs ctl    T sigma   vs ctl
   10           0.153%    0.59x     0.215%    0.90x
   20           0.159%    0.61x     0.200%    0.84x
   50           0.161%    0.62x     0.218%    0.92x
  100           0.230%    0.88x     0.246%    1.03x
  200           0.993%    3.81x     0.346%    1.45x
  926          21.532%   82.70x    33.318%  139.75x
```

Among the top 100 receipts, the spread of **both** axes is at or below the
byte-identical control's own 1-sigma. The top of the public field is
statistically indistinguishable from one tree measured a hundred times.

Two consequences:

1. **The public leaderboard's ordering at the top is noise-dominated**, which
   independently corroborates the earlier finding that `officialScore` is 3.3x
   noisier than renormalised `ns` on identical content. Ranking movement in the
   top 100 is mostly baseline draw, not code.
2. **A screening receipt on prefill is well-powered.** A genuine 0.5% S
   improvement would put a candidate outside the entire 926-receipt
   distribution, so the screen cannot mistake noise for a win — and, symmetrically,
   a null screen is real information rather than an underpowered shrug.

## Caveat, stated plainly

Part of the frontier's flatness is that `mlxfast sync` restores editable paths
from the best promoted submission, so many top receipts are near-copies of one
tree and were never independent attempts at prefill. That is exactly why the
decode column matters: it is drawn from the same partly-cloned population and
still shows 74 two-sigma wins. Cloning suppresses *variance*, not the ability of
the population to produce a win on an axis people are actually attacking.

What this does **not** show is *why* prefill has not moved — whether it is hard,
unfashionable, or structurally protected. It only establishes that it has not.

## Where our own tree sits

```
best-S receipt e2822dc1: S 97.359  T 4.3565  ns 2.52177
best-T receipt ae9ac90b: S 97.704  T 4.3076  ns 2.53672
```

Our unchanged base is effectively tied for best-in-field on prefill. So prefill
work here is not catch-up; any real gain is new ground for the whole field, and
it is the axis with 25% of the score exponent behind it.
