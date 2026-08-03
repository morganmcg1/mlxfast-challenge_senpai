# Quality-proxy calibration from accepted leaderboard snapshots

Status: **complete for the frozen quick-profile contract** (2026-08-03)

This note answers whether the current local `97%` retention rule should be
loosened to resemble the competition's private acceptance gate. Its PPL limit
is exactly `baseline / 0.97`, a 3.0928% allowance rather than exactly 3%.
It uses the already completed evaluations of all 15 accepted ranks 112–126,
the three selected official-failure controls, the extended AIME diagnostics,
and the rank-126-relative recomparison. The full provenance and per-arm audit
are in [REPORT.md](REPORT.md).

## Answer

Do **not** infer a larger acceptable quality loss or retune the percentages
from this cohort. The current July-30-baseline composite is useful as an
advisory drift panel, but it is not a valid M5 submission veto:

- all 11 formally comparable accepted snapshots fail it;
- four other accepted snapshots reach the frozen AIME response ceiling and
  correctly produce no decision;
- the only formally comparable known failure scores at least as well as
  accepted ranks 120–126 on every predeclared component; and
- all 12 formal success/control comparisons reject, so no false-accept rate or
  replacement threshold can be estimated.

The local tasks can remain—they expose behavioral changes—but a percentage
threshold cannot make the current feature set discriminate official acceptance.
Use a fresh same-host current-frontier baseline for drift detection, exact
matched-reference checks as hard local stops, and the official M5 gates as the
rankability authority.

## What the current 97% rule actually requires

The frozen July-30 M4 baseline is `26/53` correct with PPL `13.954858`.
The composite requires:

- downstream score at least `ceil(0.97 × 26) = 26/53`—despite its name, this
  permits no question loss at this baseline size;
- PPL no worse than `13.954858 / 0.97 = 14.386452`;
- at least `7/9` exact ranked-GPQA response-prefix matches;
- the exact public first token; and
- identical evaluated row sets.

An incomplete or length-bounded arm is an **abstention**, never a retain or
regression.

## Accepted submissions measured by our proxy

| Accepted ranks | Arms | Downstream | PPL | Prefixes vs July-30 baseline | Public token | Proxy outcome |
|---|---:|---:|---:|---:|---|---|
| 112–115 | 4 formal | 23/53 | 14.613699 | 0/9 | exact (`5991`) | reject |
| 116–119 | 4 bounded | diagnostic only | diagnostic only | no formal comparison | exact (`5991`) | abstain |
| 120–122 | 3 formal | 22/53 | 14.903492 | 0/9 | exact (`5991`) | reject |
| 123–126 | 4 formal | 22/53 | 14.970700 | 0/9 | exact (`5991`) | reject |

Observed acceptance of an officially accepted snapshot is therefore `0/11`
conditional on a formal comparison, with `4/15` accepted snapshots censored by
the declared 2,048-token AIME limit. The four accepted censored arms still hit
the same item limit at 6,144 tokens in the isolated extended diagnostic; that
does not turn them into failures or formal comparisons.

These 15 rows are connected source overlays, not independent samples. The 11
formal rows collapse to three metric signatures, one pass per arm gives no
variance estimate, M4 requires a compatibility override, and the rank-111
quality anchor remains pending. The table proves proxy discordance; it does not
prove that the accepted models lost this much real quality or that the private
M5 gate tolerates it.

## Why loosening the bar cannot calibrate it

To admit the worst observed accepted formal signature against the old baseline
would require approximately:

- `22/26 = 84.6%` downstream retention;
- a `14.970700 / 13.954858 = 1.0728`, or about `7.3%`, PPL allowance; and
- no exact ranked-prefix requirement (`0/9`).

That rule would also admit known official failure control 202, which records
`24/53`, PPL `14.903492`, `0/9` prefixes, and the exact public token. It
componentwise dominates accepted ranks 120–126. Any monotone threshold over
the present components that admits those accepted rows must admit control 202.

Controls 201 and 203 are bounded abstentions. Control 201 is especially useful:
it failed the official 64-step public behavior gate but still matched our
single public token, proving that the one-token probe is too shallow. The
selected controls are small and non-random, so they calibrate a failure mode,
not population sensitivity or specificity.

## Operational policy for our campaign

1. Keep the historical July-30 comparison for cumulative diagnostics, but do
   not let its composite verdict automatically veto M5 validation.
2. For each research round, freeze a fresh same-host current-frontier baseline
   (rank 126 until we promote our own successor). Keep `>=97%` downstream,
   `<= baseline / 0.97` PPL, `>=7/9` response identity, and the public token as
   an **amber drift alarm**, not proof of correctness.
3. For the current rank-126 baseline (`22/53`, PPL `14.970700`), those numeric
   alarms are `>=22/53` and PPL `<=15.433712`. Historical ranks 120–122 retain
   at exactly `7/9`; ranks 123–125 retain at `9/9`; ranks 112–115 regress only
   on response identity; ranks 116–119 remain abstentions. This identifies a
   lineage boundary, not official validity.
4. Hard-stop integrity/protocol failures and new exact matched-reference
   divergences: use the full 64-step public drift-tripwire trajectory, upstream
   equivalence, and teacher-forced correctness traces.
   On M4, first run the unchanged frontier to separate generation drift from a
   candidate regression.
5. Send amber cases to measured M5 validation rather than silently accepting
   or rejecting them. The complete official M5 gate stack—public and hidden
   exact-token behavior, GPQA/semantic checks, timed oracle, thermal validity,
   and timing acceptance—remains the authority for official acceptance.

## Next calibration work

- Complete the isolated rank-111 quality anchor to locate inherited drift.
- Repeat matched rank-126/current-frontier baselines to measure proxy variance.
- Recompare formal control 202 against rank 126.
- Replace the one-token probe with the full public checked trajectory.
- Add more locally completing near-frontier negative controls, stratified by
  official failure category, and retain a holdout before designing a new rule.

Until a feature separates accepted and rejected controls, changing `97%` to a
lower number is not calibration—it is only choosing a different false-accept /
false-reject tradeoff without evidence.
