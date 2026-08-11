# R129-G follow-up: what the 70 `failed` receipts actually are

Status: supplementary evidence for PR #746, whose typed result is already posted. No
fires, no model-source edits, no submissions. Everything below is read-only analysis
of receipts that already exist.

The advisor's open question on #746 was: *is the clean 0/40 packaging record because
packaging is easy, or because it is being watched?* The honest answer is **neither**,
and the record contains a much larger effect that the packaging framing hides.

## 1. The failures are one time-local burst, not a learning curve

Corpus: 177 terminal receipts from `mlxfast submissions` (read-only), 70 of them
`failed` (39.5%), 106 scored-and-rejected, 1 promoted; plus 1 still `validating`.

If the 70 failures were independent per-candidate packaging mistakes at a 39.5% rate,
they would be scattered. They are not. Contiguous blocks of failures have sizes

    [41, 21, 2, 2, 1, 1, 1, 1]

with 91.4% of all failures inside the three largest blocks. The Wald-Wolfowitz runs
test gives **17 runs against 85.3 +- 6.3 expected, z = -10.78** - independence is
rejected about as hard as a 176-sample test can reject it.

Per calendar day (UTC):

| day  | n  | failed | rate |
|------|----|--------|------|
| 8/4  | 17 | 1      | 6%   |
| 8/5  | 14 | 0      | 0%   |
| 8/6  | 23 | 4      | 17%  |
| 8/7  | 37 | 26     | 70%  |
| 8/8  | 27 | 26     | 96%  |
| 8/9  | 18 | 0      | 0%   |
| 8/10 | 17 | 0      | 0%   |
| 8/11 | 17 | 0      | 0%   |

Split into regimes at the block edges:

| regime      | window                | n  | span   | mean spacing | failed     |
|-------------|-----------------------|----|--------|--------------|------------|
| pre-burst   | .. 8/7 09:59          | 60 | 73.7 h | 75.0 min     | 8          |
| **burst**   | 8/7 09:59 - 8/8 17:38 | 63 | 31.6 h | 30.6 min     | **62 (98.4%)** |
| post-burst  | 8/8 17:38 ..          | 53 | 61.7 h | **0**        | 0          |

The last failure is `4121270` at 8/8 17:38. Since then **53 consecutive fires over
63.7 h have all come back scored**, so by the rule of three the current per-fire
failure risk is **<= 5.7%** (tighter than the <= 7.5% previously quoted).

A "being watched" story predicts a gradual improvement. What happened instead is a
rate that climbed to 96-98% and then collapsed to exactly zero within one fire. That
is a switch, not a learning curve.

## 2. It is not per-candidate content either

`research/tools/receipt_commit_forensics.py`:

* the 70 failed receipts carry **70 distinct commits**; nothing was retried blindly;
* **no commit ever appears in both a failed and a scored receipt**, so tree content and
  wall-clock time are perfectly confounded in this record - the data cannot separate
  them, and any claim that the trees were at fault is unfalsifiable from receipts alone;
* exactly **one** fire scored inside the burst window (8/7 18:51, score 2.52126, the
  lowest of its whole neighbourhood - consistent with an older base), which argues
  slightly against "the service returned nothing regardless of content".

The weakest hypothesis that fits: a **time-local condition shared by essentially every
tree fired in that window** (a common inherited base or harness state, or service-side
handling), not 62 independent packaging mistakes.

## 3. Hard limitation: failed receipts carry no diagnosis

For `failed` rows the CLI prints `metrics = n/a` and `diff = n/a`. There is no error
string anywhere in the account's own view, so the cause can only be inferred from
timing. Two traps found the hard way:

* the metrics cell stays truncated even at `COLUMNS=4000`, so the embedded JSON of
  scored rows is only partially readable;
* **the CLI colours the status column** (`\x1b[31mfailed\x1b[39m`). A naive `split()`
  or `awk` pipeline silently parses **zero** rows and every derived count comes out 0.
  All tools here strip ANSI first.

## 4. What this is worth: the decision rule

Conditioning the next fire on the previous terminal receipt (first-order Markov, same
corpus):

| condition                       | P(next fire fails) |
|---------------------------------|--------------------|
| previous terminal was scored    | 8/106 = **7.5%**   |
| previous terminal `failed`      | 62/70 = **88.6%**  |
| previous **two** `failed`       | 58/62 = **93.5%**  |
| unconditional                   | 70/176 = 39.5%     |

Retrospectively applying "do not fire while the newest terminal receipt is `failed`"
to this record: it blocks 70 fires, of which **62 would have returned nothing** (88.6%
precision) and 8 would have scored. That is **~35% of all draws ever spent by this
account** recovered for the cost of delaying 8 fires.

So the ranking of pre-fire guards is:

1. **one read of the account's newest terminal receipt** - worth up to ~35% of draws;
2. static packaging gates (`research/tools/preflight_gates.sh`, the #746 deliverable) -
   worth at most 5.7% of a draw in the current regime, and probably less.

I am not walking back the #746 gates; they are cheap, 3-4 s, and they caught real
stale numbers in the brief. I am saying they are the second-order guard, and #746's
own framing ("packaging is the risk") over-weights them.

## 5. The gate

`research/tools/epoch_gate.py` implements the rule in the same grammar as
`preflight_gates.sh` (`GATE <name>: PASS|FAIL`, nonzero exit on any FAIL) and
recomputes its own justification statistics from the dump it is given, so the numbers
it quotes can never go stale. `preflight_gates.sh` was deliberately **not** modified -
it is already verified in the #746 result.

Both directions are demonstrated without spending a fire.

Live dump, 15:05Z today - and it says HOLD, for a reason nobody had flagged:

    GATE epoch_dump_parsed: PASS - 178 receipts parsed
      P(fail | prev scored) = 8/106 = 7.5%
      P(fail | prev failed) = 62/70 = 88.6%
    GATE epoch_last_terminal_scored: PASS - newest terminal 5fae2f1 is rejected (12:16 PM)
    GATE epoch_last_two_not_both_failed: PASS - 4be372f=rejected, 5fae2f1=rejected
      consecutive clean terminal receipts: 54 over 66.6 h
    GATE epoch_slot_free: FAIL - c06b1b6 validating since 8/11/26, 1:51 PM
    1 epoch gate(s) FAILED - do not fire.        exit=1

Negative control, the same dump truncated so its newest rows land inside the burst:

    GATE epoch_last_terminal_scored: FAIL - newest terminal 4121270 is failed (8/8 5:38 PM)
    GATE epoch_last_two_not_both_failed: FAIL - 4ac7ad5=failed, 4121270=failed
      consecutive clean terminal receipts: 0
    2 epoch gate(s) FAILED - do not fire.        exit=1

Honest cost of the rule: at 8/8 17:38 it would have said HOLD while the burst had in
fact just ended, so it does buy safety with delay. With draws this scarce that trade
is worth taking, but it is a trade, not a free win.

## 6. Reproduce

```sh
COLUMNS=4000 mlxfast submissions > /tmp/subs.txt     # read-only
python3 research/tools/epoch_gate.py            --dump /tmp/subs.txt
python3 research/tools/receipt_commit_forensics.py --dump /tmp/subs.txt
python3 research/tools/failure_clustering.py        # advisor-branch TSV dump
python3 research/tools/failure_burst_detail.py --lo 55 --hi 130
```

A second, independent finding fell out of the same dump - the CLI's `diff` percentage
is not what it looks like, and the bar is not fixed. See
`research/r129g_bar_and_diff_semantics.md`; that one changes the endgame arithmetic.
