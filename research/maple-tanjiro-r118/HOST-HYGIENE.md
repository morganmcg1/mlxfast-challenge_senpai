# Host hygiene during the R118-A campaign — a disclosure

Recording this because it is the kind of thing that is invisible in the artifacts
and would quietly weaken the result if a reader found it later instead of here.

## What happened

While the campaign was measuring, I twice ran the analyser on the *partial*
orderA directory from the same host, to check the rig was behaving before
committing three more hours to it:

| time (UTC) | what | cost |
|---|---|---|
| ~04:37 | `analyze-dose.py --boot 4000` on partial orderA | a few seconds of multi-core CPU |
| ~04:34 | same, `--boot 20000`, earlier partial read | a few seconds of multi-core CPU |

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

## Standing rule I am adopting for myself

No analysis, no builds, and no other CPU-heavy work on the measuring host while a
timing campaign is live. Read the `.tsv` progress file (a `tail`, which is free)
and wait. The five minutes of reassurance I bought were not worth the disclosure
I now have to write.
