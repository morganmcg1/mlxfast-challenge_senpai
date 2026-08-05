# T3 — Reconciling the "legacy acceptance band" ratio in `research/nezuko-mbcap-up-receipt.md`

PR #57 (`maple-2026-08-05f-gathergemm-coresidency`), task T3. Research-only note;
zero submitted bytes. Every number below is re-derived from the cited source
line, not copied from a prior research note.

## 0. One-paragraph answer

`nezuko-mbcap-up-receipt.md:139-152` reports a "hand-computed legacy acceptance
band" whose ratio is **candidate time divided by a *sibling research arm's*
time**. The band in the source code is a check on **raw seconds-per-token
against the paired baseline**. Those are different quantities with different
denominators, so the receipt's two ratios (0.994332 decode, 0.970647 prefill)
are not the band statistic and the receipt's conclusion "the legacy band would
also have passed" does not follow. Applied as the source defines it, the
canonical band **fails both axes** on that receipt — on the *low* ("too fast")
side, because a 2.7x decode speedup is far outside `[0.980, 1.053]`. This is
moot for ranking: the deployed ranked path applies **no** band at all, only the
two `0.95` floors. Nezuko's two quoted band *literals* are correct; only the
statistic they were applied to is wrong.

Section 6 works the second denominator dispute the advisor asked for — fern's
receipt `285f79fa` on #48. Her renormalisation reproduces exactly, but the
advisor's diagnosis of the residual gap does not: inverting the receipt's own
`*_speedup` fields recovers a paired prefill baseline that drifted only
**-0.0228%** from pinned, so session variance cannot explain a 4.6% gap. The gap
is **99.5% the choice of normaliser** — `research/nezuko-normalised-leaderboard.md`
uses the programme constants at `senpai/program.md:130-131`, not the pinned
`Constants.swift:167-172` pair, while labelling them "pinned". The T4 defunding
arithmetic is unaffected because a fixed normaliser cancels in an `ns` ratio.

## 1. What the band actually is, from source

### 1.1 The check

`Sources/MLXFastCore/AcceptanceBand.swift`

```
:43   guard reference > 0 else { ... }
:49   let hi = reference * (1 + upTolerance)
:50   let lo = reference * (1 - downTolerance)
:5x   fail if value > hi || value < lo
```

(the exact comparison is at `:49-58`).

### 1.2 What is fed to it

`Sources/MLXFastCore/Score.swift:101-114` calls it twice:

| axis | `value` | `reference` |
|---|---|---|
| prefill | `prefillSecondsPerToken` | `baselinePrefillSecondsPerToken` |
| decode | `decodeSecondsPerToken` | `baselineDecodeSecondsPerToken` |

So the band operates on **raw seconds-per-token**, and its reference is **the
paired baseline of the same session**. It never sees a speedup, a score, or a
ratio between two candidate arms.

### 1.3 The tolerances

`Sources/MLXFastCore/Constants.swift:145-148`

```
prefillBandUp   = 0.05
prefillBandDown = 0.05
decodeBandUp    = 0.02
decodeBandDown  = 0.05
```

There is **no separate `tolerances` file**; these four literals are the whole
configuration.

### 1.4 Where `[0.980, 1.053]` / `[0.952, 1.053]` come from

Speedup is `Score.swift:15`:

```
speedup = baselineSecondsPerToken / candidateSecondsPerToken
```

Mapping the seconds-per-token interval `[reference*(1-down), reference*(1+up)]`
through that reciprocal gives the speedup image

```
s in [ 1/(1+up), 1/(1-down) ]
decode : [1/1.02, 1/0.95] = [0.980392, 1.052631]
prefill: [1/1.05, 1/0.95] = [0.952380, 1.052631]
```

Both literals nezuko quotes are therefore **correct as derived values**. They
are not stored anywhere in code: a repo-wide search finds them only in prose —
`TASK.md:46`, `senpai/program.md:35-36`,
`docs/benchmark-window-freeze.md:142`, and a comment at
`Sources/MLXFastModel/LagunaRuntimeWeights.swift:535`.

### 1.5 How the reference is resolved

`Sources/MLXFastTrustedHarness/LagunaRuntimeBenchmark.swift:153-157` (mirrored
at `Sources/MLXFastHarness/LagunaRuntimeBenchmark.swift:148-152`, `:429-433`,
trusted `:443-445`; golden field at `Sources/MLXFastCore/Golden.swift:224-226`):

```
B = PairedBaselineOverride.fromEnvironment()
    ?? goldenField
    ?? pinned constant
```

The environment keys are
`MLXFAST_PAIRED_BASELINE_{PREFILL,DECODE}_SECONDS_PER_TOKEN`
(`Sources/MLXFastCore/BenchmarkSupport.swift:38-39`). They are set **nowhere**
under `.github/` — only in tests. **The band's reference is therefore never a
sibling research arm on any real path.** That is the single structural fact that
invalidates the receipt's statistic.

The pinned fallbacks (`Constants.swift:167-172`) are

```
officialBaselinePrefillSecondsPerToken = 0.00036751938916015625   (367.51939 us)
officialBaselineDecodeSecondsPerToken  = 0.01385621216015625      ( 13.85621 ms)
```

with provenance at `:149-156` (mean of four ranked M5 runs 30011903540 /
30015338806 / 30022640438 / 30027994180 against pinned baseline commit
`15852ee52858def42ddd4f32bca7e59d275e020e`; decode CV 0.26%, prefill CV 0.65%)
and an explicit comment at `:158-166` that these are **"NOT the ranked scoring
denominator"**.

## 2. What the receipt computed

`research/nezuko-mbcap-up-receipt.md:139-152` labels its table:

> "Hand-computed legacy acceptance band (**ratio = control time / candidate
> time**)"

The inputs, read from the same receipt:

| quantity | control `c3ce66e` | candidate `c747336` |
|---|---|---|
| `cand_pre` | 191.308 us | 197.093424 us |
| `cand_dec` | 5.04644 ms | 5.0752060 ms |

Paired baseline that session: `385.178873 us` prefill, `13.895972 ms` decode.
Reported `prefill_speedup 1.954295914930016`,
`decode_speedup 2.7380116305445217`, `officialScore 2.51665710865438`,
`status rejected`, `max_abs_diff 0`, both `0.95` floors true.

Reproducing her two numbers exactly:

```
5.04644 / 5.0752060 = 0.9943317...   -> receipt 0.994332   OK
191.308 / 197.093424 = 0.9706466...  -> receipt 0.970647   OK
```

So the statistic is unambiguous: **candidate arm vs. sibling control arm**.

### 2.1 A hypothesis I tested and refuted

I first suspected the ratios were a baseline-health check,
`B_measured / B_pinned`. They are not:

```
0.994332 x 13.85621216 ms = 13.7777 ms   vs measured 13.895972 ms  (off 0.86%)
0.970646 x 367.51939 us  =  356.70 us    vs measured 385.178873 us (off 7.4%)
```

Both miss. The sibling-arm reading is the only one that reproduces to six
digits.

## 3. Applying the canonical band to that receipt

Canonical band, decode, against the session's own paired baseline:

```
lo = 13.895972 ms x 0.95 = 13.20117 ms
hi = 13.895972 ms x 1.02 = 14.17389 ms
value = 5.0752060 ms  ->  value < lo  ->  FAIL (low side)
```

Prefill:

```
lo = 385.178873 us x 0.95 = 365.9199 us
hi = 385.178873 us x 1.05 = 404.4378 us
value = 197.093424 us  ->  value < lo  ->  FAIL (low side)
```

Against the pinned constants instead of the session baseline the verdict is
identical (`13.85621216 x 0.95 = 13.16340 ms`;
`367.51939 x 0.95 = 349.1434 us`; both still above the candidate values).
Equivalently in speedup space: `2.738` and `1.954` both sit far above the
`1.052631` ceiling.

So the receipt's arm-to-arm ratios pass a `+-5%` window while the actual band
statistic fails by a factor of ~2.7. The entire divergence is the
**denominator**: hers is a sibling receipt's candidate time, the source's is
the paired baseline. The ratio between those two denominators *is* the speedup
(`385.178873/191.308 = 2.013`, `13.895972/5.04644 = 2.753`), which is exactly
why the two statistics cannot agree.

## 4. Is the ranked verdict affected?

No — the ranked path applies no band whatsoever.

`.github/scripts/overlay-paired-timing.sh` merges the paired candidate verdict
using only the two floors:

```
:131-135, :141-146, :161-168   -> tests only  $ds >= 0.95  and  $ps >= 0.95
:37-38                         -> floors read from arguments
```

fed by `.github/workflows/benchmark.yml:262-263`, and re-asserted in
`.github/scripts/validate-benchmark-artifacts.sh:188-190`. `$ds` and `$ps` come
from the `.paired` block of the external on-box `measure-job` `results.json`
(`benchmark.yml:1814`). No `AcceptanceBand` symbol appears anywhere in that
chain.

The local-iterate band notice is also gone: `emitLocalAcceptanceBandNotice` no
longer exists, both `LagunaRuntimeLocalIterate.swift` files have zero
`Band`/`acceptance` matches, and the only tracked reference is the **negative**
assertion at
`Tests/MLXFastTests/SenpaiOperationalContractTests.swift:125`. Organizer commit
`8341756` removed it (it was added by `279b6e2`).

`AcceptanceBand` therefore still exists and is still exercised by tests
(`AcceptanceBandTests.swift:109-112`, `BenchmarkWindowFreezeTests.swift:67-70`
and `:85-88`, `ScoreTests.swift:75-87`, `BenchmarkSafetyTests.swift:781-799`,
`SenpaiOperationalContractTests.swift:124-131`) and inside the inner benchmark
binary, but it is not the ranked gate. Score assembly is `Score.swift:46-47`,
the `0.95` floors are `:63`, `passesAcceptanceBands` is `:142`, and failure
ordering is `:145-158`.

## 5. What the band does and does not bound

**It bounds:** the candidate's *absolute* seconds-per-token staying within
`-5% / +2%` (decode) or `-5% / +5%` (prefill) of the **paired baseline measured
in the same session**. Its purpose is to detect a session in which the two arms
are not comparable — a mis-set window, a wrong build, a harness that skipped
work — by catching a candidate that is implausibly *fast* as well as one that is
too slow. It is a sanity interval around "candidate is doing the same amount of
work as the baseline", not a performance target.

**It does not bound:** (a) any ratio between two research arms — nothing in the
resolution chain can make the reference a sibling arm, since the override
environment keys are unset on every real path; (b) the ranked verdict, which is
the two `0.95` floors only; (c) a genuine large speedup, which the deployed
wrapper treats as a win rather than a band violation — the wrapper reads these
invocations as timing probes and checks baseline health separately. A large
speedup will always trip the low side of the legacy band; that is a property of
the band, not a defect in the candidate.

## 6. The second denominator dispute: fern's #48 renormalisation

The advisor's #57 comment §3 added fern's receipt `285f79fa-089f-4184-b1ec-0647cb51e61b`
as a worked case and flagged that her `npf = 2.013145` and the receipt's reported
`prefill_speedup = 1.9238` differ by −4.4%, attributing the gap to same-session
paired-baseline variance ("the receipt's own `*_speedup` fields use the
same-session paired baseline, whose prefill draw is the single largest variance
source we have measured"). **That attribution is wrong, and the arithmetic says
so cleanly.**

The receipt payload is not in my tree (#48 is unmerged at my base), so the four
inputs below are the ones quoted in that comment. All derived figures are mine.

First, her renormalisation reproduces exactly:

| quantity | formula | computed | advisor quoted |
|---|---|---|---|
| `nd` | `0.013890 / 0.00505923275` | 2.745476 | 2.745476 |
| `npf` | `0.0003845 / 0.000190994708984375` | 2.013145 | 2.013145 |
| `ns` | `nd^0.75 · npf^0.25` | 2.540575 | 2.540575 |

**The key step is inverting the reported `*_speedup` fields to recover her actual
paired baseline.** `Score.swift:15` defines speedup as `baseline / candidate`, so
`base = reported_speedup × cand`:

| axis | implied paired baseline | pinned constant | drift |
|---|---|---|---|
| decode | 13.83548 ms | 13.85621 ms (`Constants.swift:167-172`) | **−0.1496%** |
| prefill | 367.43562 µs | 367.51939 µs (`Constants.swift:167-172`) | **−0.0228%** |

Fern's paired prefill draw was within **0.023%** of the pinned constant. It was
one of the quietest prefill draws in the programme, not a large variance
excursion. So the −4.4% gap cannot be paired-baseline variance.

**Where the gap actually comes from.** `0.013890` and `0.0003845` are *not* the
pinned constants. They are programme normalisers defined at
`senpai/program.md:130-131` (and restated identically at `:438-439`), and they
sit above the pinned pair:

| axis | gap `n/reported` | attributable to normaliser choice | residual paired drift |
|---|---|---|---|
| decode | +0.3940% | **+0.2438%** | +0.1498% |
| prefill | +4.6442% | **+4.6203%** | +0.0228% |

`0.0003845 / 0.00036751938916015625 = 1.046203`. The prefill gap is **99.5%
explained by the choice of normaliser** and 0.5% by baseline drift. Renormalising
the same receipt against the pinned constants gives `npf_pinned = 1.924239`,
which agrees with the reported `prefill_speedup = 1.9238` to +0.023% — i.e. to
the paired drift and nothing else.

**Why this does not invalidate any `ns` comparison.** A fixed normaliser cancels
exactly in a ratio of two `ns` values, which is the only way `ns` is ever used.
Checking against the number that defunded my own T4:

```text
ns_cand / ns_ctl = 2.540575 / 2.544360 = 0.998512  =>  -0.1488%
```

That reproduces the advisor's −0.1488% to four decimals. The T4 defunding stands
on arithmetic that is unaffected by the normaliser choice.

**What it does invalidate is putting `ns` on the `officialScore` scale.**
Renormalising fern's receipt with the pinned pair gives `ns_pinned = 2.507464`
against her `ns = 2.540575`, a **−1.30%** level shift. So an `ns` value is a
comparison coordinate, not a score estimate, and quoting one next to a receipt's
`decode_speedup` or `officialScore` invites exactly the −4.4% confusion above.

**The labelling defect that caused this.**
`research/nezuko-normalised-leaderboard.md:108-109` calls `0.013890` / `0.0003845`
the "**pinned** reference decode/prefill seconds/token". That word collides with
the genuinely pinned `Constants.swift:167-172` pair, which are different numbers
with a documented four-run provenance at `Constants.swift:149-156` and an
explicit in-source disclaimer at `:158-166` that they are "NOT the ranked scoring
denominator". `research/maple-fern-pr40-result.md:537-538` gets the label right:
"fixed normalisers, **not** the session baseline". I recommend the leaderboard
wording be brought into line with fern's. I did not edit either file.

## 7. Recommended correction to the receipt (no edit made)

`research/nezuko-mbcap-up-receipt.md:139-152` should relabel its table
"arm-to-arm drift check (control arm time / candidate arm time)" and drop the
sentence claiming the legacy acceptance band would have passed. The ratio is a
*useful* statistic — a ~0.6% decode and ~2.9% prefill drift between two
supposedly-equivalent arms is exactly what one wants to see reported — it is
simply not the band. I did not edit that file; it is another student's receipt.

## 8. Honest caveats

- Only **low-side** band failures were exercised here. I did not construct a
  candidate that trips the high side, so the `hi` comparison at
  `AcceptanceBand.swift:49` is verified by reading and by the existing unit
  tests, not by a run of mine.
- `AcceptanceBand.check`'s exact comparison operators were read at
  `:49-58`; I did not execute the function, so a strict-vs-inclusive boundary
  case (`value == lo`) is asserted from source text only.
- The `[0.980392, 1.052631]` / `[0.952380, 1.052631]` intervals are my
  derivation from the four tolerance literals. No source file stores them, so
  any future change to `Constants.swift:145-148` silently invalidates every
  prose copy of those numbers, including this note.
- Section 6's four inputs (`cand_pre`, `cand_dec`, `decode_speedup`,
  `prefill_speedup` for receipt `285f79fa`) were taken from the advisor's #57
  comment because #48 is unmerged at my base, so the receipt payload is not in
  my tree. Every derived figure is mine, but if any of those four quoted inputs
  is itself mistranscribed, the decomposition inherits the error. The one
  internal consistency check available — that inverting the two `*_speedup`
  fields lands within 0.15% of the independently-pinned `Constants.swift`
  baselines on both axes — passes, which makes a transcription error unlikely.
