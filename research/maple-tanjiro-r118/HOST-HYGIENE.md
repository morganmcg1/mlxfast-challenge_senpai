# Host hygiene during the R118-A campaign — a disclosure

Recording this because it is the kind of thing that is invisible in the artifacts
and would quietly weaken the result if a reader found it later instead of here.

## What happened

While the campaign was measuring, I twice ran the analyser on the *partial*
orderA directory from the same host, to check the rig was behaving before
committing three more hours to it:

| time (UTC) | what | cost |
|---|---|---|
| ~04:34 | `analyze-dose.py --boot 20000` on partial orderA | a few seconds of multi-core CPU |
| ~04:37 | same, `--boot 4000`, second partial read | a few seconds of multi-core CPU |

Both landed **inside the orderA measurement window**. Neither touched the GPU and
neither started a second model-holding process, so the 21 GB/40 °C constraints
were respected — but they were not zero-cost, and they were not symmetric across
arms, because they happened at particular moments and therefore during whichever
arm was executing then.

## Why the design already absorbs it, and how it is checked rather than assumed

This is exactly the failure mode mirrored ordering exists for. ORDER_B is the
**exact time-reversal** of ORDER_A, so a perturbation that favours the arm running
at a given offset in order A disfavours the corresponding arm in order B. The
check is therefore available in the data rather than by argument:

- **If orderA and orderB agree**, no transient during orderA moved the estimate,
  and the disclosure is a footnote.
- **If they disagree**, that disagreement is itself the finding and I report both
  separately and claim neither — which is why the charge required both orders
  reported separately in the first place, and why I did not pool them.

The control block was run *between* the two orders and no analysis was run during
it or during orderB.

## Second disclosure: order B was interrupted and resumed

The campaign ran as one supervised job with a wall-clock deadline. **The deadline
fired at 05:16:05Z, in the middle of order B's run 23 of 40**, after order A had
completed 40/40 (04:12:56–04:41:47Z) and the control block 24/24
(04:41:47–04:59:34Z). The kill was a `SIGTERM` to the process group from the job
supervisor, not a crash of the measurement: the last completed run, 22, is
`d2 8.214 / 8.203`, entirely ordinary. Run 23 left a `.log` and a `.err` and **no
`.steps` file**, so no partial or truncated run entered the data; the analyser
keys on `.steps` files only.

What I did about it: `resume-orderB.sh` continues the **same pre-registered
`ORDER_B` string from position 23**, with the run index offset so the files land
under the names the analyser expects. No order was re-drawn, no arm was
re-assigned, and runs 1–22 were not touched. The cost is a gap of roughly ten
minutes in the middle of order B's session, between run 22 and run 23.

Why I judge it harmless, and what would show it was not:

- The block contrast is *within* a block of four consecutive runs. The gap falls
  between blocks 5 and 6 of order B (runs 1–20 are five complete blocks; runs 21
  and 22 open block 6), so at most one block straddles it, and that block is
  re-run in full by the resume because runs 21–22 are `ship` and `d2` and the
  resume supplies `d1` and `ctl` for the same block a few minutes later.
- Order B's mirror property is a property of the *sequence*, which is unchanged.
- The falsifier is the same one as above: order A and order B are reported
  separately and their agreement (or not) is the check.

Had I to do it again I would have sized the job's deadline from the measured
44 s/run rather than from an optimistic estimate, and split it into stages —
which is what `finish-r118a.sh part1|part2` now does.

## Standing rule I am adopting for myself

No analysis, no builds, and no other CPU-heavy work on the measuring host while a
timing campaign is live. Read the `.tsv` progress file (a `tail`, which is free)
and wait. The five minutes of reassurance I bought were not worth the disclosure
I now have to write.
