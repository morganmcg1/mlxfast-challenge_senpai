# The CLI's `diff` percentage is not a relative gap, and the bar is not fixed

Status: supplementary, read-only, derived from `mlxfast submissions` output captured at
15:05Z on 8/11 (107 scored receipts: 106 rejected + 1 promoted). No fires. Tool:
`research/tools/diff_column_semantics.py`. This changes endgame arithmetic, so it is
worth checking before it is used.

## 1. The printed percentage has a constant denominator of 1.0034

The CLI prints, per scored receipt, an absolute diff and a percentage, e.g. for
`5fae2f1`: score `2.57521511`, diff `-0.044338 (-4.42%)`. But
`0.044338 / 2.575215 = 1.72%` and `0.044338 / 2.619553 = 1.69%`. Neither is 4.42%.

Solving for the implied denominator on every scored row, `diff / (pct/100)`:

    n=107   min 1.00175   median 1.00345   max 1.00551   mean 1.00354

The printed percentage is rounded to 2 dp, so each row only constrains the denominator
to an interval. Intersecting all 107 intervals:

    single constant consistent with EVERY row: YES
    feasible interval [1.003396, 1.003414], width 1.8e-05, midpoint 1.003405
    binding rows: lower 4f546a8, upper 6757de6

Mean |error| in percentage points for candidate denominators:

| denominator                   | mean err | max err |
|-------------------------------|----------|---------|
| ~1.0034 (a constant)          | tiny, all rows within display rounding |  |
| 1.0 exactly                   | 0.033 pp | 0.33 pp |
| the receipt's own score        | 5.06 pp  | 37.05 pp |
| the bar (`score - diff`)      | 5.86 pp  | 58.90 pp |

So the CLI percentage is **`|diff| / 1.003405 x 100`** and carries *no* information
about the receipt's score. Most plausible reading: 1.003405 is the reference solver's
own measured score (nominally 1x), so the column expresses the gap in **points of
baseline speed**, not as a fraction of our 2.6x score. It holds for the positive
direction too: the promoted receipt shows `+0.03652 (+3.64%)`, and
`0.03652 / 1.003405 = 3.640%`.

**Correction to make:** to convert a CLI percentage into a true score-relative gap,
divide by `bar / 1.003405` = **2.611** at today's bar. Worked examples:

| sub      | score    | diff      | CLI pct | true gap vs bar |
|----------|----------|-----------|---------|-----------------|
| 5fae2f1  | 2.575215 | -0.044338 | -4.42%  | **-1.69%**      |
| 4be372f  | 2.576714 | -0.042839 | -4.27%  | **-1.64%**      |
| f2b2345  | 2.593280 | -0.023224 | -2.31%  | **-0.89%**      |
| f8502e1  | 2.485577 | -0.053630 | -5.34%  | **-2.11%**      |

Anyone who reads `-4.42%` as "we need 4.4% more speed" is overstating the required
engineering by ~2.6x. Any table mixing CLI percentages with score-relative percentages
is internally inconsistent by that factor.

## 2. `score - diff` reconstructs the bar, and the bar moves

Because diff is signed against the target, `score - diff` recovers the bar in force
when that receipt was adjudicated. Independent validation: the account's single
`promoted` receipt `97a5090` (8/6 05:04) scored 2.588828 with diff **+0.03652**, giving
a then-bar of 2.552308 - exactly the value reconstructed from the receipts around it -
and from 8/6 12:11 onward the reconstructed bar is **2.588828**, i.e. the promoted score
itself. The mechanism is confirmed: the bar is the incumbent best, and it steps up.

Note also that this row is the one that a `-?`-only sign pattern silently drops, since
it is the only receipt whose diff prints with a leading `+`. My first pass did exactly
that and reported "0 of 106 fires ever cleared the bar", which was wrong; the correct
statement is 1 of 107. The parser now accepts both signs.

Trajectory (clustered at 1e-5; `n` = receipts observed at that bar):

| bar      | step      | first seen      | n  |
|----------|-----------|-----------------|----|
| 2.539206 |           | 8/4 07:53       | 9  |
| 2.552308 | +0.013102 | 8/4 15:10       | 21 |
| 2.588828 | +0.036520 | 8/6 12:11       | 3  | <- our own promotion
| 2.590186 | +0.001359 | 8/6 22:09       | 2  |
| 2.597383 | +0.007197 | 8/6 23:29       | 7  |
| 2.597874 | +0.000491 | 8/7 03:27       | 7  |
| 2.604024 | +0.006149 | 8/7 07:57       | 3  |
| 2.606306 | +0.002282 | 8/7 18:51       | 1  |
| 2.616504 | +0.010198 | 8/8 19:38       | 52 |
| 2.619553 | +0.003050 | 8/11 09:20      | 2  |

* monotone non-decreasing: **True** (10 distinct levels, no reversal);
* total rise +0.080348 (**+3.16%**) over 169.4 h = +0.011380/day;
* most recent step +0.003050 over 61.7 h = **+0.001186/day** - the bar was flat for
  ~62 h and then moved this morning;
* only **1 of the 9 steps is ours** (the 8/6 promotion); the other 8 came from outside
  this account, so the bar is an external incumbent that other entrants keep raising.
  It is definitely not "our own best so far": the very first observed bar (2.539206) was
  already above our first score, and today's bar is above our best ever.

Sampling caveat that matters: **the bar is only observed when this account fires.**
Every "first seen" is an upper bound on when the bar actually changed, and the bar may
already be above 2.619553 now. The `validating` receipt `c06b1b6` (fired 13:51Z) will,
when it adjudicates, be the freshest reading available - a reason to wait for it rather
than fire beside it.

## 3. Where the account actually stands

| quantity                                   | value |
|--------------------------------------------|-------|
| latest observed bar (sampled 12:16Z, 8/11) | 2.619553 |
| account best ever (`e27f1ce`, 8/10 08:18)  | 2.606650 |
| absolute shortfall                         | **0.012903** |
| shortfall as % of score                    | **0.50%** |
| best relative approach while behind (`4058d0b`, 8/5)| -0.25% |
| scored fires that ever cleared the bar     | 1 of 107 (`97a5090`, 8/6, +1.43%) |

The needed improvement is **half a percent**, not the ~4% a CLI percentage suggests.
That reframes what kind of change is worth shipping: a 0.5% win is inside the range of
the small-constant work already on the table, whereas a 4% ask would argue for
something structural.

## 4. The race: we were ahead on 8/6 and lost the lead during the failure burst

We held the bar on 8/6 at +1.43%. We are now 0.49% behind it. Measured over the whole
window since that promotion:

    since the last promotion (97a5090, 8/6 05:04, 127.2 h)
      our best   2.588828 -> 2.606650  = +0.003363/day
      the bar    2.552308 -> 2.619553  = +0.012688/day
      gap        +1.43% -> -0.49%
      net closure -0.009325/day -> LOSING GROUND at this rate

That window contains the 8/7-8/8 failure burst documented in
`research/r129g_failure_clustering.md`: **63 fires in 31.6 h of which 62 returned
nothing**, while the bar advanced. The burst is the most plausible proximate cause of
the lost lead - a third of the account's entire fire budget produced zero information
during the exact interval in which the bar rose +0.0125.

Restricting to the window in which fires actually score:

    since the last FAILED receipt (4121270, 8/8 17:38)
      54 scored fires over 64.6 h, 4 new best-so-far records
      our rate +0.012382/day (records span 30.8 h)
      bar rate +0.001132/day
      net +0.011249/day -> gap 0.012903 closes in 1.1 days if this holds

So the two defensible readings are:

* over the whole post-promotion window, we are losing at -0.0093/day;
* over the productive post-burst window, we are winning at +0.0112/day and parity is
  ~1.1 days away.

Caveats I will not paper over: record-setting rates decelerate by construction; **no new
best in the last 28 h** despite ~24 fires, so the post-burst rate is already optimistic;
the bar's future steps are set by other entrants and are not forecastable from our
receipts; and the trailing-48 h figure the tool prints (+0.30/day) is a divide-by-0.8 h
artifact that the tool itself flags. The defensible statement is that the remaining gap
is the same order as one to two days of this account's *productive* progress - close,
and dependent on fires continuing to return scores.

## 5. Reproduce

```sh
COLUMNS=4000 mlxfast submissions > /tmp/subs.txt     # read-only
python3 research/tools/diff_column_semantics.py --dump /tmp/subs.txt
```

The script prints the interval-intersection test, the candidate-denominator errors, the
bar trajectory, the closest approaches, and the race section, so every number above is
re-derivable from one read-only command.
