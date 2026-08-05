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

## 6. Recommended correction to the receipt (no edit made)

`research/nezuko-mbcap-up-receipt.md:139-152` should relabel its table
"arm-to-arm drift check (control arm time / candidate arm time)" and drop the
sentence claiming the legacy acceptance band would have passed. The ratio is a
*useful* statistic — a ~0.6% decode and ~2.9% prefill drift between two
supposedly-equivalent arms is exactly what one wants to see reported — it is
simply not the band. I did not edit that file; it is another student's receipt.

## 7. Honest caveats

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
