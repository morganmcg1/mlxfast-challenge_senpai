#!/usr/bin/env python3
"""Render the submission note for one R106-E replication draw.

Every draw of the ladder ships the same compiled tree, so the notes differ only
in the draw index and the commit SHA. Rendering them from one template keeps
that guarantee mechanical instead of relying on six hand edits, and it embeds
the unique marker the ladder analysis uses to attribute receipts.

Usage: maple-frieren-r106e-note.py REP TOTAL COMMIT_SHA > note.md
"""
import sys

TEMPLATE = """# {marker} — Maple campaign replication ladder, rep {rep} of {total}

Marker for receipt attribution: `{marker}`

| field | value |
|---|---|
| campaign | Maple campaign |
| student | maple-frieren |
| assignment | maple-r105-b-router-prefetch-adjudication |
| revision | r105-b-rev3 |
| experiment | R106-E — replication of one fixed tree |
| draw index | rep {rep} of {total} |
| submitted commit | {sha} |
| research base | 7491001264832c2566de65c5cab9f363c6426e09 |
| integration base passed to the wrapper | 1bc1c8954147c9e322aad1f3b80bd9fa3c0888d7 |

## What this submission is

This is **not** a mechanism experiment. It is draw {rep} of the first deliberate
replication this campaign has ever attempted.

Grouping all 82 of the campaign's prior receipts by full compiled-tree identity
yields **zero** groups with n >= 2. In 106 rounds the same program has never
been submitted twice. Every sigma, every z, and every confidence interval in
the campaign's research state is therefore inferred from non-replicates. Three
different estimators of the channel's 1-vs-1 spread currently disagree by a
factor of 4.9x:

- 0.2494 % of `cs`, from near-replicate groups (identical Sources, comment-only
  Vendor deltas; 5 groups, 15 receipts);
- 0.5393 % of `cs`, from a session-lottery fit;
- 1.2244 % of `cs`, pooled across those same near-replicate groups.

Which of those is right decides the strategy for the rest of the campaign. The
gap from the campaign's best draw (2.590559) to the standing record
(2.61650354381456) is +0.9965 % in log-`cs`. At the tight end that gap costs on
the order of 31,000 draws to close by luck and mechanism work is the only path.
At the loose end it costs about 5 draws and mechanism work is close to
irrelevant. No other measurement available to this campaign has that decision
value, and it cannot be obtained any way other than by submitting one fixed
tree several times.

## The tree

The submitted tree is the **live research base** at
`7491001264832c2566de65c5cab9f363c6426e09`, unmodified in every path that
enters the compiled program:

```
git diff --numstat 74910012 {short} -- Sources Vendor
    (empty)
```

That tree was chosen for three reasons and it buys all three with one slot:

1. it is the tree the campaign would actually ship, composing all three
   round-100 restorations;
2. it had **never been measured on M5 at all** before this ladder, so the first
   draw doubles as the long-deferred frontier receipt;
3. it is a genuine record attempt at the campaign's best-known merit.

Every draw in this ladder carries a **distinct commit SHA** whose difference
from its predecessor lies **entirely outside** `Sources/` and `Vendor/` — in
practice the appended per-draw record in the write-up. The empty
`git diff --numstat` between consecutive draws is published for every pair. If
any two draws ever fail that check, the experiment is declared void and said to
be so.

## What is deliberately absent

No router-weight-prefetch arm is present. The lever this PR was originally
opened to adjudicate was closed as a ranked-hardware null by an anchor-pair
analysis of receipts the campaign already held (delta = +0.0478 % of `cs`,
z = +0.19), at a cost of zero receipts. `DARKBLOOM_ROUTER_WEIGHT_PREFETCH`
therefore compiles to its shipped default of `1` here, exactly as at the base.
The M4 end-to-end effect measured at +34.58 us/step in #571 does not transfer
to ranked hardware at any usable magnitude; that non-transfer is recorded as a
first-class finding about the M4-to-M5 transfer menu rather than as a lever.

No retry loop is present either. The submission that produced this receipt was
gated on a read-only channel watcher that exits only when the account has no
non-terminal submission, and it fired exactly once. The channel is a
single-server validation queue with roughly 22 minutes of service time and at
most one non-terminal submission at any instant; a submit issued while it is
busy fails on conflict and still consumes the limiter. The script that
previously retried into that queue has been deleted from the branch.

## Correctness posture

The tree is byte-identical to the research base in every compiled path, so it
carries exactly the base's correctness properties. No numerical behaviour,
representation, dispatch, or layout is altered by this submission relative to
the base. The submitted surface is unchanged from the base within the 97
`editablePaths`; the only differences anywhere in the commit are research
documents, which are not part of the compiled program.

## What will be reported from the ladder

For every draw: `submissionCommitSha`, candidate decode and prefill, baseline
decode and prefill, `cs`, `L`, `officialScore`, status, rejection reason,
submit timestamp, and validation-complete timestamp.

From the ladder as a whole:

- `sd(ln cs)`, `sd(ln decode)`, `sd(ln prefill)`, each with a confidence
  interval, plus the **1-vs-1 difference sigma** (sd times sqrt 2), which is
  the number the rest of the campaign actually consumes;
- a decomposition of whether the spread is session-correlated or independent,
  obtained by regressing the candidate leg on the baseline leg across draws.
  `cs` is supposed to strip the session draw; if the legs are correlated then
  the normalisation is not doing its job, and that is a larger finding than the
  sigma itself;
- the same discrimination applied to `officialScore`, which is the quantity
  that is actually ranked, alongside `cs`. Earlier work in this PR measured the
  ranked score to be roughly four times noisier than the candidate-only `cs`
  proxy, because the paired normalisation divides by a same-session baseline
  whose prefill leg is itself far noisier than the candidate's. If that holds
  up under true replication, every draw-count estimate computed on `sd(cs)` is
  optimistic and needs recomputing on the ranked sigma.

The relative standard error of a sigma estimate is `1/sqrt(2(n-1))`: about
40.8 % at n = 4 and 31.6 % at n = 6. That is genuinely poor precision and it is
stated up front rather than discovered later. It is nonetheless sufficient to
separate 0.25 % from 1.22 %, which is the decision that matters here.

## Preregistered discrimination

Let s1 be the measured 1-vs-1 sd of `ln cs` across the ladder.

- s1 <= 0.35 % — the channel is a precise instrument, the lottery is not
  winnable by volume, and mechanism work is the only path forward.
- s1 >= 0.80 % — essentially every effect this campaign has claimed is
  unresolvable at n = 1, and the correct policy is to draw on the best tree
  rather than to keep building.
- between — report the number and the implied draw count to a record.

Overriding both: if the candidate and baseline legs prove correlated across
draws, the normalisation itself is broken, and that result stops the ladder and
is published immediately.
"""


def main():
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    rep, total, sha = sys.argv[1], sys.argv[2], sys.argv[3]
    marker = f"R106E-DRAW-{int(rep):02d}-{sha[:8]}"
    sys.stdout.write(TEMPLATE.format(marker=marker, rep=rep, total=total,
                                     sha=sha, short=sha[:8]))


if __name__ == "__main__":
    main()
