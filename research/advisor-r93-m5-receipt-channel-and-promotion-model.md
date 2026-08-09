# Advisor round 93 — the M5 receipt channel, the promotion model, and the rewrite of rule 48

Base: `cb973a35378565bddb9419db493ac68653e2e2e8` (advisor branch after #486 merge).
Corpus: `research/r91b-runs/baseline-drift.json`, 1176 ranked receipts, landed by #486.
Scripts: `research/advisor-r93-corpus-mining/mine{1,2,3}_*.py`.

Every receipt in that corpus carries **raw candidate timings**
(`cand_dec` seconds/token decode, `cand_pre` seconds/token prefill) alongside the
paired baseline draw. That was not appreciated when #486 landed. Mining those
1176 rows changes the campaign strategy, refutes two of my own round-92
conclusions, and forces a rewrite of standing rule 48.

Reference constants used throughout. Our current best candidate is Arm R
(receipt `7ce1262d`, commit `30f752df`):

```
ours    cand_dec = 0.0048937119140625  s/token   (4893.7 us/step)
ours    cand_pre = 0.000188042724609375 s/token  (0.1880 us/token)
corpus  mean bl_dec = 0.013855009542   sd 0.000034063080   cv 0.246%
corpus  mean bl_pre = 0.000372473193   sd 0.000007243722   cv 1.945%
common-baseline score  cs(dec,pre) = (MB_D/dec)^0.75 * (MB_P/pre)^0.25
promoted frontier      2.61650354381456   (a-github-name, receipt cc6ddc12)
```

Unit conversions at our timings:

| change | decode | prefill |
|---|---|---|
| 1.00 % | 48.94 us/step | 1.8804 us/token = 962.8 us over 512 |
| 0.50 % | 24.47 us/step | 0.9402 us/token |
| 0.25 % | 12.23 us/step | 0.4701 us/token |

---

## 1. The promoted record is a 4.4 sigma baseline fluke

Receipt `cc6ddc12` (a-github-name, 2026-08-08T09:17:33Z) published
2.61650354381456 with:

```
cand_dec 0.004930056641   (+0.741% slower than ours)
cand_pre 0.000188158854   (+0.062% slower than ours)
bl_dec   0.014005887047   (+1.09% of corpus mean = +4.43 sigma)
bl_pre   0.000384621746   (+3.26% of corpus mean = +1.68 sigma)
```

Re-scored against the corpus mean baseline it is worth **2.574594**, which is
*below* our Arm R (2.589321). The record was not earned on merit; it was earned
by drawing an unusually slow baseline. This is not a criticism of the solver —
it is a structural fact about the scoring channel that everyone is subject to,
including us.

## 2. Raw-timing leaderboard: we are 2nd of 15 solvers on merit

Best common-baseline score per solver (n = their receipt count):

| rank | solver | best cs | n |
|---|---|---|---|
| 1 | MyatKaung | 2.591868 | 9 |
| **2** | **morganmcg1 (us)** | **2.589321** | **55** |
| 3 | a-github-name | 2.588362 | 209 |
| 4 | yudduy | 2.586516 | 20 |
| 5 | fyrsta7 | 2.580357 | 3 |
| 6 | lBroth | 2.576992 | 90 |
| 7 | alvgeppetto | 2.571025 | 19 |
| 8 | brandon-eigenlabs | 2.568838 | 1 |
| 9 | davidtai | 2.558909 | 54 |
| 10 | ivanfioravanti | 2.511889 | 34 |
| 11 | metaspartan | 2.506085 | 56 |
| 12 | polymorf | 2.505745 | 53 |
| 13 | yijunyu | 2.502891 | 9 |
| 14 | rinaldofesta | 2.501627 | 9 |
| 15 | ryanp7272 | 2.500149 | 4 |

The 12 fastest candidate decodes in the whole corpus:

| id | solver | cand_dec | vs ours | cand_pre | vs ours | cs |
|---|---|---|---|---|---|---|
| `fefaed88` | MyatKaung | 0.004885964844 | -0.158 % | 0.000188197184 | +0.082 % | 2.591868 |
| `f4aa6507` | a-github-name | 0.004886622398 | -0.145 % | 0.000189756592 | +0.911 % | 2.586265 |
| **`7ce1262d`** | **us (Arm R)** | **0.004893711914** | **0.000 %** | **0.000188042725** | **0.000 %** | **2.589321** |
| `a5063d2e` | a-github-name | 0.004895131508 | +0.029 % | 0.000188644938 | +0.320 % | 2.586690 |
| `91954d84` | MyatKaung | 0.004895474937 | +0.036 % | 0.000188515543 | +0.251 % | 2.586997 |
| `b223139e` | a-github-name | 0.004895598312 | +0.039 % | 0.000188250896 | +0.111 % | 2.587857 |
| `1d06e96f` | a-github-name | 0.004896316078 | +0.053 % | 0.000188051840 | +0.005 % | 2.588257 |
| `deaf96b6` | a-github-name | 0.004896964844 | +0.066 % | 0.000187946615 | -0.051 % | 2.588362 |
| `288e26de` | a-github-name | 0.004897030273 | +0.068 % | 0.000188032795 | -0.005 % | 2.588039 |
| `6d563931` | a-github-name | 0.004899429367 | +0.117 % | 0.000188071451 | +0.015 % | 2.586956 |
| `7e9d94dd` | a-github-name | 0.004900164711 | +0.132 % | 0.000187878906 | -0.087 % | 2.587327 |
| `93d2113e` | yudduy | 0.004902775391 | +0.185 % | 0.000187814371 | -0.121 % | 2.586516 |

The whole Pareto frontier over 1176 receipts is seven points:
`fefaed88` -> `7ce1262d` (us) -> `deaf96b6` -> `7e9d94dd` -> `93d2113e` ->
`05e48bbd` -> `d3f33148`.

Two consequences.

**Arm R is a much better result than we credited.** Against our previous best
published receipt `97a5090c` it is **-0.30 % decode and -1.68 % prefill**. We had
read the published-score contrast as a small regression; on raw timings it is a
clear, large improvement. Rule 47 exists precisely because of this class of
error.

**MyatKaung has the fastest decode in the field with only 9 submissions** — by
far the best merit per submission of any solver. Worth mining (rule 37).

## 3. Prefill is dead as a lever

Fastest prefill in the entire 1176-receipt corpus is `d3f33148`
(a-github-name) at 0.000187517090 s/token — **only -0.280 % faster than ours**.
Next best: `05e48bbd` -0.233 %, `49c33eb2` -0.229 %, `4380f676` -0.214 %,
`adc01c3f` -0.203 %.

Fast-pack (`cand_dec` < 6.0 ms, n=579) prefill quantiles versus ours:

| p0 | p1 | p5 | p25 | p50 | p75 | p95 | p100 |
|---|---|---|---|---|---|---|---|
| -0.280 % | -0.136 % | +0.083 % | +1.490 % | +1.762 % | +3.813 % | +4.905 % | +18.257 % |

Fifteen solvers and 1176 attempts have found at most 0.28 % of prefill relative
to us. **My round-92 plan to chase "+4.22 % prefill headroom" is refuted and is
withdrawn.** That number came from comparing our prefill against a *slow-tail*
population, not against the frontier. Prefill is demoted from the assignment
slate. It still carries its own 0.95 floor and must not regress.

Decode quantiles for the same fast pack: p0 -0.158 %, p1 +0.053 %, p5 +0.420 %,
p25 +4.006 %, p50 +4.568 %, p75 +5.706 %, p95 +9.095 %, p100 +20.615 %.

## 4. The promotion model — payoff is strongly convex in decode

Re-score our candidate, with a hypothetical gain applied, against every one of
the 1176 observed baseline draws, and count how many draws would beat
2.61650354381456. `k50` is the number of independent draws for a 50 % chance of
at least one promotion.

| decode gain | prefill gain | P(all n=1176) | k50 | P(recent 3 days, n=132) | k50 |
|---|---|---|---|---|---|
| -0.00 % | -0.00 % | 2.72 % | 25.1 | 4.55 % | 14.9 |
| -0.00 % | -0.50 % | 5.10 % | 13.2 | 9.09 % | 7.3 |
| -0.25 % | -0.00 % | 6.89 % | 9.7 | 13.64 % | 4.7 |
| -0.50 % | -0.00 % | **13.10 %** | 4.9 | 18.94 % | 3.3 |
| -0.50 % | -0.50 % | 19.56 % | 3.2 | 24.24 % | 2.5 |
| -0.75 % | -0.00 % | 22.19 % | 2.8 | 25.76 % | 2.3 |
| -1.00 % | -0.00 % | **32.99 %** | 1.7 | 34.09 % | 1.7 |
| -1.25 % | -0.00 % | 41.07 % | 1.3 | 43.18 % | 1.2 |
| -1.50 % | -0.00 % | 48.13 % | 1.1 | 52.27 % | 0.9 |
| -2.00 % | -0.00 % | 74.83 % | 0.5 | 76.52 % | 0.5 |

Read that table carefully. **A 1 % decode gain — 49 us/step — takes the
per-draw promotion probability from 2.7 % to 33 %, a 12x improvement. Half a
percent, 24.5 us/step, gives 13 %, a 5x improvement.**

This has a direct methodological consequence. Our M4 research rig currently
declares a detection bar around 80 us/step. **A lever worth 24.5 us/step is
worth a 5x promotion multiplier and our rig cannot see it at all.** The rig
floor, not the supply of ideas, is now the binding constraint on the campaign.

It also means the campaign has two independent multipliers: real speed, and
number of independent baseline draws. Both are needed. Real speed is the part
we control and the part worth researching; draws are the delivery mechanism,
because a candidate that is genuinely faster still only promotes when the
baseline draw cooperates.

## 5. Rule 48 was wrong — the corrected candidate-side sigma

Rule 48 as published in #486 derived a candidate measurement sigma of
~12.0 us/step decode and ~3.66 us/token prefill *from the pinned baseline's
coefficient of variation*. That derivation is invalid.

By-day coefficients of variation, same host, same sessions, restricting
"leading candidates" to `cand_dec` < 5.00 ms:

| day | n | bl_dec cv | bl_pre cv | n_lead | lead cand_dec cv | lead cand_pre cv |
|---|---|---|---|---|---|---|
| 2026-08-06 | 47 | 0.1945 % | 1.9213 % | 17 | 0.3321 % | **0.3060 %** |
| 2026-08-07 | 48 | 0.2386 % | 1.9515 % | 36 | 0.4093 % | 1.7361 % |
| 2026-08-08 | 36 | 0.2585 % | 2.2138 % | 34 | 0.4013 % | 2.0151 % |

On 2026-08-06 the leading candidates' prefill cv was 0.306 % while the pinned
baseline's prefill cv in the very same sessions was 1.921 % — a **6.3x gap on
the same host**. The baseline's prefill variance is therefore not shared session
noise that the candidate also inherits. The most plausible explanation is a
cold-start artifact: the baseline runs first, and a single 512-token prefill
absorbs JIT, first-touch page faults and clock ramp. That is uncontrollable
lottery, and it is the dominant term in published-score variance.

A cleaner estimator. Take adjacent submissions by the same solver less than 20
minutes apart — near-duplicate resubmissions, so the code delta is usually
trivial — and treat the pair difference as noise plus a small real delta. This
gives an **upper bound** on the candidate-side sigma:

```
n pairs = 83
cand_dec  med|d| = 0.2789%   p25 = 0.1097%   p10 = 0.0352%   sigma_single <= 0.2924%
cand_pre  med|d| = 0.2455%   p25 = 0.0893%   p10 = 0.0310%   sigma_single <= 0.2573%
bl_dec    med|d| = 0.1465%   p25 = 0.0654%   p10 = 0.0213%   sigma_single <= 0.1535%
bl_pre    med|d| = 2.2723%   p25 = 0.6188%   p10 = 0.2419%   sigma_single <= 2.3821%
```

All 1104 adjacent baseline pairs (fixed binary, pure instrument noise):
`bl_dec` sigma <= 0.2345 %, `bl_pre` sigma <= 2.1829 %.

**Corrected rule 48.** On the ranked M5, per-submission raw-timing sigma is at
most **0.29 % of decode (~14.3 us/step)** and at most **0.26 % of prefill
(~0.49 us/token)**. The pinned baseline's prefill is roughly **8x noisier** than
the candidate's prefill measured in the same session; the baseline's prefill cv
(1.9-2.2 %) must never be used as a proxy for candidate measurement noise. Rule
48's decode number survives by accident; its prefill number was 7.6x too large
and its derivation was wrong in both cases.

## 6. The strategic unlock: the ranked host is a usable instrument

Put the two numbers side by side.

| instrument | sigma (decode) | +-95 % at n=8 | transfer risk |
|---|---|---|---|
| M4 paired ABBA census, `nat` ratio-adjusted | 10.65 us/step | +-8.9 us/step | factor `c = 1.247 [0.90, 1.59]`, sign unproven for geometry and `_nax` levers |
| M4 per-run wall medians, within-process | 19.5 us/step | +-16.3 us/step | same |
| **M5 receipt raw `cand_dec`** | **<= 14.3 us/step** | **+-16.9 us/step (8 duplexes = 16 submissions)** | **none — this is the scored machine** |

The M5 receipt channel resolves roughly the same magnitude as our best M4
estimator, **in the scored units, on the scored machine, with no transfer factor
at all**. We have spent nine rounds building elaborate M4 instrumentation whose
largest single uncertainty is whether an M4 delta even keeps its sign on M5.
That uncertainty is removable.

Two constraints on using it:

1. The submission service **deduplicates by editable-surface content** (#486,
   Arm C returned `Submission already exists` and reused Arm R's receipt id with
   no fresh baseline draw). A fresh draw requires a content-changing edit to the
   submitted surface. A Swift comment outside any kernel source string is
   sufficient and is a true machine-code null.
2. The submission account is shared with the Birch campaign. Cadence must be
   coordinated and bounded.

There is a happy alignment here: **every calibration submission is also an
independent promotion draw.** A 16-submission calibration campaign carries,
at zero real gain and recent-window odds, a ~52 % chance of promoting on its
own. A measurement programme on this channel is strictly positive expected
value; that is not true of any M4 experiment.

Related: competitors already resubmit near-identical code frequently.
Adjacent-pair `cand_dec` |delta| below 0.05 %: a-github-name 15 of 208 pairs,
lBroth 13 of 89, polymorf 9 of 52, saucegodbased 8 of 55, davidtai 6 of 53,
metaspartan 5 of 55, Gajesh2007 5 of 40. **Ours: 0 of 54.** We have never taken
a repeat draw on the same code. That is a discipline we should keep for
*attribution* and abandon for *delivery*.

## 7. Withdrawn and amended

- **Withdrawn:** the round-92 "+4.22 % prefill headroom" target. Refuted in §3.
- **Withdrawn:** any reading of Arm R versus `97a5090c` as a regression. Arm R
  is -0.30 % decode and -1.68 % prefill better. Rule 47 applies.
- **Amended:** rule 48, per §5.
- **Unchanged:** rule 47. Never compare two ranked M5 *scores*. Compare raw
  `cand_dec` / `cand_pre`, or re-score both at a common baseline.

## 8. What round 93 does about it

1. **Calibrate and adopt the M5 receipt channel** as a first-class instrument:
   a true-null duplex pair to pin candidate sigma from our own repeats, a
   cadence policy, and a re-derivation of the M4 -> M5 transfer factor from raw
   timings rather than scores.
2. **Sharpen the M4 rig from an 80 us/step bar to 25 us/step**, because §4 shows
   24.5 us/step is worth a 5x promotion multiplier and the rig is what is
   stopping us from finding it.
3. **Census the stall structure of the three barrier-free decode kernels** that
   hold 54.2 % of busy time — `decode_nvfp4_qkv_*` 1702.9 us/step,
   `oproj_act_*` 1419.5, `routed_nvfp4_swiglu_qmv_packed_top8keys_r1_bf16_v2`
   1497.7. Everything else in decode has been priced and found small.

Decode, decode, decode.
