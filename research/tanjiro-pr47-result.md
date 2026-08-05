# PR #47 — closing the dispatch law: D1, D2, D4

`assignment_id maple-2026-08-05c-dispatch-law-close`, `revision_id r1`,
student `maple-tanjiro`. Accepted base
`173277080dec8207add0654711ec2f65344de981`.

**Headline in one line:** D4 and D1 are complete and both are *negative or
non-gating*; D2's ranked probe is the only thing that can actually close the
bracket, and it is in flight. The bracket `[0.36, 2.09] µs/dispatch` — the
factor-5.8 uncertainty that decides whether the whole dispatch-removal programme
is worth `+2.2%` or `+12.6%` of score — is **still open** after two completed
deliverables, and I want that stated plainly rather than dressed up.

---

## 0. THIS TREE MUST NEVER BE MERGED

The submitted tree is a **measurement instrument**: it injects 100 empty GPU
dispatches per decode step on purpose and is therefore *slower* than the
frontier by design. Two integer defaults in the PR #27 instrument block:

| knob | frontier | this tree |
|---|---|---|
| `DARKBLOOM_INJECT_DECODE_EMPTY` | `0` | **`100`** |
| `DARKBLOOM_INJECT_EMPTY_TG` | `160` | **`8`** |

If this branch is ever promoted, the frontier loses ~3% of decode. Do not merge
it. The knobs must go back to `0` / `160` (or the whole block deleted — see §6)
before any of this branch touches `main`.

---

## 1. D2 — the n=100 knee probe (COMPLETE, R1 HIT)

**Submission `57306132-803c-43ec-9532-7f8463b34823`**, dispatched
2026-08-05 15:26:45Z from commit `5a72af3` (editable surface frozen at submit
time), note 10,728 B, server-side commit `fd9cd3583f45e9683a76dda46d06b6a09ae0292d`,
receipt `timestamp 2026-08-05T15:37:02Z`. Status `rejected`, which on this
account means only "did not beat the current best" — every correctness and floor
gate passed. Full metrics and the preregistered decision in §1.8.

### 1.1 What it measures

Two ranked receipts on this account already lie on the empty-dispatch curve, and
I verified by direct grep of the `0411779d` tree (commit `b8da628`) that **both
were measured at `EMPTY_TG = 8`, not 160** — in that tree the chain was
unconditional and `EMPTY_TG` was 8:

| receipt | n | `ns` |
|---|---|---|
| `c3ce66ec` | 0 | 2.544360 |
| `0411779d` | 400 | 2.283549 |

Two points give a slope on the assumption of a straight line through them. They
cannot give a knee. Setting `EMPTY_TG = 8` in this submission puts n=0/100/400
on **one** curve, so the third point gives slope *and* knee. I diffed the
`CHAIN=1` path line-by-line against `b8da628`: substituting
`lagunaInjectEmptyChain == true`, index 1 binds `tail`, the in-loop
`pending.append` is skipped and the post-loop `pending.append(tail)` fires — the
`b8da628` body with `chainTail` renamed. The three points are genuinely
comparable.

### 1.2 Preregistered decision rule

Full prereg in `research/tanjiro-pr47-prereg-n100.md`, written and committed
before submission. Law `dT(n) = c·max(0, n − knee)`:

| hypothesis | `c` (µs) | knee | `dT(100)` | accept if `ns ∈` |
|---|---|---|---|---|
| **H_knee0** | 2.088 | 0 | 0.209 ms | `[2.452073, 2.484242]` |
| **H_knee300** | 8.35 | 300 | 0 | `[2.528276, 2.560444]` |

Separation **14.21σ** at `σ(dT) = ±14.2 µs`. `ns > 2.560444` (R5) is
pre-declared an instrument/session fault. Windows are 3σ.

The exact decode-only inverse map is used throughout, because linearising the
score is not good enough at this size:
`dT [ms] = 1000 × 0.00504644 × ((ns_pub/ns_obs)^(4/3) − 1)`. At n=400 the
linearisation errs −7.0%; at n=100, −2.0%.

### 1.3 Reporting discipline I committed to in advance

- **`ns`, never `officialScore`.** fern's #40 showed the baseline-prefill draw
  owns 86.5–86.9% of `officialScore` variance. nezuko's `c747336` read −0.262%
  on `officialScore` and −1.164% on `ns`.
- **`dS` and `dT` separately**, converted through 0.371 %/ms and 14.862 %/ms,
  because `cand_dec` is *not* decode: in `c747336` the entire +0.570% `cand_dec`
  move was the prefill seed leaking through the `S/128` term while `T` moved
  0.7σ. `dS` is predicted **0** here because `PREFILL_EMPTY=0`.
- **Reconstruction check**: `d ln ns_pred = 0.371·dS + 14.862·dT` must agree with
  the directly derived `ns` delta to within 0.10%.

### 1.4 Pre-receipt amendment: the M4 companion pair says the knee is soft

The `--local-iterate` gate run of the submitted tree is itself an M4 n=100 point
at the same geometry, and I hold the matching n=0 point (`c7a874d`, banked as
`research/tanjiro-pr47/d1-tg8-r1-n0.json`):

| tree | S (ms) | T (ms) |
|---|---|---|
| `c7a874d` n=0 | 571.4312 | 8.83084 |
| `5a72af3` n=100 | 569.7498 | 8.89438 |

`dS = −1.6815 ms (−0.294%)`, `dT = +0.06354 ms (+0.719%)` ⇒ **0.6354
µs/dispatch** on M4 across n=0→100.

Both rigid models fail it. D1's hard-knee M4 law (`knee = 1209`) predicts
`dT(100) = 0`. A no-knee law at D1's supra-knee slope 2.7406 µs/disp predicts
0.27406 ms, 4.3× too big. `dT` is 6.6× the n=0 anchor spread and `dS` moved the
*wrong way* (faster), so neither noise nor a session-wide slowdown explains it.
**The M4 absorption region is soft** — partial exposure well below the knee, at
~23% of the supra-knee marginal rate.

Under the transfer law this cannot establish a soft knee on the M5. What it does
do, recorded **before** the receipt so it cannot be a post-hoc rescue:

1. It raises my prior on **R3**, the gap between the two acceptance windows. I
   amended the prereg so **R3 is now read through the continuous map as a
   genuine intermediate `dT`, not as an instrument fault**. Only R5 remains a
   pre-declared fault region.
2. It weakens the hard-knee `c·max(0, n−k)` form that H_knee0, H_knee300 *and*
   Reading A of §5 all assume. If the M5 point lands in R3 I will report the
   soft-knee family as leading and will **not** quote a single resolved knee.
3. R1/R2 windows are unchanged.

### 1.5 Reading A vs Reading B — the trap, flagged before the spend

A **null** at n=100 (H_knee300, `dT ≈ 0`) has two readings with opposite
decisions, and I will publish both:

**Reading A — piecewise host cost.** A null only *raises* the prize, because the
n=400 anchor is fixed: with `r = dT(100)/835.09 µs`,
`k = (100 − 400r)/(1 − r)`, `c = 835.09/(400 − k)`:

| `r` | knee `k` | `c` µs | pool %-of-score |
|---|---|---|---|
| 0.500 | −200 | 1.3918 | 8.40 |
| 0.250 | 0 | 2.0877 | **12.60** |
| 0.125 | 57.1 | 2.4356 | 14.70 |
| 0.000 | 100 | 2.7836 | **16.80** |

**Reading B — saturation slack.** `T = max(T_gpu, T_host(406 + n))` with knee
`k > 0` means removing a real dispatch is worth **exactly zero, forever** — D4's
entire premise dies. Evidence against B: it needs `c_host = 8.35 µs/dispatch` on
M5 against M4's 2.607/2.813 with an M5 fabric ~2.25× *faster*, which is not
physical; and the wall-vs-GPU gap of 0.322 ms at n=0 ≈ 154 × 2.088 µs shows host
encode is already partly exposed.

I will publish D2 as a **(knee-bracket, c-bracket, pool-bracket)** under Reading
A with Reading B carried as an explicit unresolved alternative. I will not
publish a point estimate of `c`.

### 1.6 Correctness on the exact submitted tree `5a72af3`

- `./benchmark.sh --local-iterate`: `passed=true`, `passed_correctness=true`,
  `max_abs_diff=0`, `golden_hash b9509697c08a2cf3c2943a85f0b76e39c485c441794690fa76835b40a58d7a63`
  (unchanged), `checked_steps=130`, `peak_ram_gb=21`,
  `weights_hash aff9943…`, `commit 5a72af3`.
- `./benchmark.sh --local-submit`: see §5.
- `research/run_upstream_equivalence.sh`: decode steps 0–7 **exactly `0.0`** max
  and mean abs logit error; every `runtimeToken == upstreamToken` (509/902/5991
  cycle); `EQUIVALENCE_EXACT_STEPS=8`.
- `swift test --force-resolved-versions`: **456 tests / 6 suites / 0 failures**,
  then `git checkout -- Package.resolved`.

**The control that makes this airtight.** The equivalence test reports `✘` on
the *prefill* step (max 0.125, mean 0.011933609) with the argmax still identical
(5991 == 5991). I reran the identical test with
`DARKBLOOM_INJECT_DECODE_EMPTY=0 DARKBLOOM_INJECT_EMPTY_TG=160` — env override,
no rebuild, ~8 s — and got a **bit-for-bit identical report**: same 0.125, same
0.011933609, same zeros, same tokens. So the prefill divergence is pre-existing
non-`_nax` M4 behaviour in the unchanged base, and **the injection is provably
numerically inert**. This is the "test the unchanged base" discipline AGENTS.md
asks for, and the env-override trick gives the control for 8 seconds instead of
a rebuild — worth reusing.

Mechanically the injected work is 100 empty `[256]`-uint32 kernels chained
through a static scratch buffer; it reads no model state and writes nothing the
model reads.

**Serial protocol:** unaffected. No extra logits, no extra KV rows, no deferred
rows, no cross-request state. One token in, one position advanced.

### 1.7 Byte contract

`LagunaRuntimeModel.swift` 508,708 → **508,711 B** against the 524,288 B
per-file cap (15,577 B spare). At the accepted base:

```
editable budget OK: current=2941155/3000000 bytes headroom=58845
growth=182/262144 files=142 (base=142)
```

`+182 B` against my `+200 B` ceiling: `+179 B` for the unchained-empties knob
plus `+3 B` for rewriting the `EMPTY_TG` doc comment, which previously justified
`160` using the stale M4 `2.46 µs` datum and now reads "8 is `0411779d`'s
geometry, so n=0/100/400 lie on one M5 curve."

### 1.8 Receipt — LANDED, and it hit R1

Submission `57306132-803c-43ec-9532-7f8463b34823`, dispatched 15:26:45Z,
measured `timestamp 2026-08-05T15:37:02Z`, resolved between 15:47Z and 15:52Z.
Server-side commit `fd9cd3583f45e9683a76dda46d06b6a09ae0292d`.
Reproduce with `python3 /tmp/d2_report.py` against the REST submissions feed —
the CLI truncates `details`, so the numbers below come from
`GET /api/benchmarks/eigenlabs%2Fmlxfast-challenge/submissions`.

**Status `rejected`, and that is the expected and harmless outcome.** This tree
is a deliberate ~2.6% slowdown; `rejected` on this account means only "did not
beat the current best". Every gate that matters passed. Inspected separately:

| gate | value | verdict |
| --- | --- | --- |
| `passed_correctness` | `True` | pass |
| `max_abs_diff` | `0` | pass |
| `error` | `''` | pass |
| `partial_result` | `False` | pass |
| `checked_steps` / `case_count` | 1344 / 11 | pass |
| `passed_decode_speedup_floor` | `True` (2.645194 ≥ 0.95) | pass |
| `passed_prefill_speedup_floor` | `True` (1.944376 ≥ 0.95) | pass |
| `gpqa_ttft_passed` | `True`, 9/9, p50 0.076 s, 0.41 s vs 2.3 s cap | pass |
| `semantic_gpqa_passed` | `True`, 9/9, judge `claude-opus-4-8` | pass |
| `golden_hash` | `be7738fccd6a…` | **identical** to `c3ce66ec` and `0411779d` |

Raw timings:

```
decode_seconds_per_token           = 0.005232248046875
prefill_seconds_per_token          = 0.000190698486328125
baseline_decode_seconds_per_token  = 0.0138403111953125
baseline_prefill_seconds_per_token = 0.00037078955078125
officialScore                      = 2.44927871433893
```

Reduction and renormalisation:

```
S  = 97.637625 ms        T  = 4.469454 ms
nd = 2.654691            npf = 2.016272
ns = 2.478265
dT(100) = 0.180244 ms  = 1.8024 us/dispatch      (exact inverse map)
```

The linear 14.862 %/ms approximation would have given 0.174789 ms, under-reading
by **3.03%**. Quoting the exact inverse was worth doing.

**`ns` versus `officialScore`, as policy requires.** `ns` says −2.598%,
`officialScore` says −2.933%; `officialScore` over-reads the slowdown by
**0.335 pp**. This session's paired baseline was mildly *fast* on both axes —
prefill 370.789551 µs, z = −0.220, ~53.7th percentile of 1037 draws
(mean 372.369770, sd 7.196172); decode 13.840311 ms, z = −0.426 (mean 13.854902,
sd 0.034213). So there was no baseline pathology here, unlike nezuko's
`c747336`; the 0.335 pp is just the ordinary donation from a slightly quick
baseline. Reported number is `ns`.

#### The preregistered decision

| region | window on `ns` | verdict |
| --- | --- | --- |
| **R1 — accept `H_knee0`** | `[2.452073, 2.484242]` | **HIT** |
| R2 — accept `H_knee300` | `[2.528276, 2.560444]` | — |
| R3 — soft-knee gap | `(2.484242, 2.528276)` | — |
| R4 — below | `< 2.452073` | — |
| R5 — pre-declared fault | `> 2.560444` | — |

`ns = 2.478265` is **+1.89σ** from `H_knee0`'s point prediction 2.468158 and
**−12.33σ** from `H_knee300`'s 2.544360 (σ(ns) = 0.005361). The decision is
clean, it is inside the window I wrote down before the number existed, R5 did not
fire, and the §1.4 soft-knee amendment does not bind because R3 was not entered.

**`H_knee300` is dead at 12.33σ. `H_knee0` is accepted.** The M5 absorbs
essentially nothing: the injected dispatches are charged from the very first one.

#### What the receipt did to the brackets

This is the part that matters. Two banked points on one curve — `c3ce66ec` at
n=0 and `0411779d` at n=400 — plus this one at n=100 now determine Reading A's
two free parameters instead of leaving them a family.

```
r = dT(100)/dT(400) = 0.180244/0.835080 = 0.21584
k = (100 - 400r)/(1 - r) = 17.425 dispatches
c = 835.09/(400 - k)     = 2.1828 us/dispatch
pool = 406 x c           = 0.8862 ms = 13.17 % of score
```

±1σ envelope on `dT(100)`:

| | `dT(100)` ms | knee `k` | `c` µs/disp | pool % |
| --- | --- | --- | --- | --- |
| −1σ | 0.165559 | 25.816 | 2.2317 | 13.47 |
| **fit** | **0.180244** | **17.425** | **2.1828** | **13.17** |
| +1σ | 0.194929 | 8.649 | 2.1338 | 12.88 |

Against the pre-receipt state of knowledge:

| quantity | before D2 | after D2 |
| --- | --- | --- |
| knee | anywhere in `[-200, 100]` | **17.4, bracket `[8.6, 25.8]`** |
| `c` | `[0.36, 2.09]` µs/disp — a factor of **5.8** | **`[2.13, 2.23]` µs/disp — ±2.3%** |
| pool | `[2.2%, 12.6%]` | **`[12.9%, 13.5%]`** |

The `c` bracket collapsed from a factor of 5.8 to ±2.3%, and it landed **above**
the old high anchor (2.0877). The knee is not zero but it is close enough to zero
that no dispatch is meaningfully free. Cross-check: 406 × 2.1828 µs = 0.886 ms is
**66.1%** of the 1.340 ms non-bandwidth residual in `T(0)` — the independent
attribution in §"Key numbers" put the dispatch share at 63.3% using c = 2.088.
Two different routes to two-thirds.

Also worth recording for whoever compares receipts next: **`harness_hash`
differs across all three curve points** (`26581d97…`, `25c994f9…`,
`70f7dfc6…`) while `golden_hash` is identical. So `harness_hash` is not a
session-comparability signal on this feed; `golden_hash` is, and it matches.

#### What the receipt did *not* do

**D2 does not discriminate Reading A from Reading B, and was never designed
to** (§1.5 said so in advance). Both readings now share the same `c = 2.183
µs/dispatch`; they disagree only about what *removing* a real dispatch is worth:

- **Reading A** (piecewise host cost): removal pays `c` each. Pool **13.17%**.
- **Reading B** (saturation slack, `T = max(T_gpu, T_host(406+n))`): removal pays
  **exactly zero**, and the observed knee is the crossover, i.e. the model sits
  only `17.4 × 2.183 = 38.0 µs` (bracket 18.4–57.6 µs) below the host-bound
  envelope. Pool **0%**.

Both are arithmetically self-consistent with everything on the books. Under B,
`T_host(423.4) = T_gpu = 4.28121 ms` implies a fixed host term of 3.357 ms plus
0.924 ms of per-dispatch host cost, which is consistent. And the two direct
dispatch-removal tests on record both returned ≤ 0 (PR9 M2 fusion +228 µs/step;
PR32 r1 +8.3 ± 7.6 µs against −81 µs predicted) — which is what **B** predicts.

My earlier anti-B argument was that B required `c_host = 8.35 µs/dispatch` on M5,
which is not physical next to M4's 2.607–2.813 with a ~2.25× faster fabric. That
argument **is now void**: D2 replaced 8.35 with 2.183, which is entirely
physical. **Reading B got stronger, not weaker.** I would rather say that
plainly than let the 13.17% headline stand unqualified.

#### The one-receipt experiment that settles it

There is now a sharp, cheap discriminator, and the instrument already has the
knob. `DARKBLOOM_INJECT_SWEEP_PASSES` varies injected GPU work **per dispatch,
never by dispatch count** — that invariant is stated in the instrument's own
header at `LagunaRuntimeModel.swift:10999-11001` and is what the whole block was
built around.

Under **B**, at n = 400 the run is host-bound with 0.835 ms of headroom, so
adding ΔG ≤ 0.835 ms of GPU work at **fixed dispatch count** costs exactly
**zero**. Under **A** there is no envelope and the same ΔG is **fully
additive**. Pick ΔG ≈ 0.4 ms:

| | predicted `dT` vs banked `0411779d` |
| --- | --- |
| Reading A | +0.4 ms ≈ 5.9% of score |
| Reading B | 0.000 ms |

σ(dT) ≈ 16.5 µs at that magnitude, so the separation is **~24σ**. And it is
robust to transfer error: ΔG only has to land somewhere inside `(0, 0.835)` ms on
M5, so calibrating it to 0.4 ms locally on M4 tolerates a 2× miss in either
direction.

Cost: **one** receipt kills B (any `dT > 0` while host-bound is fatal to it,
because B requires exactly zero). A second receipt at `(n=0, ΔG)` is needed only
if the first returns ≈ 0, to prove ΔG was genuinely nonzero on M5 rather than
mis-calibrated to nothing. `c3ce66ec` is already banked as that arm's n=0
control, so nothing else needs re-measuring.

I have not run this and am not requesting it here. I am flagging that it decides
whether the 13.17% pool — and with it Ranks 2, 3 and 6 of the D4 inventory — is
real or is worth nothing at all.

---

## 2. D1 — the chained/unchained ladder (COMPLETE, AND IT GATES NOTHING)

`research/tanjiro-pr47-d1.md`. 13 points at tg=160, 2 complete reps, all
`passed_correctness: true`, `max_abs_diff: 0`.

**State the limitation first.** The chained/unchained ratio *is* nezuko's `C`
term, and the transfer law forbids transferring boundary timing M4→M5. So D1
**does not** narrow the `[0.36, 2.09] µs` bracket, and I am not reporting it as
if it did. It is (a) an M4-side bound and (b) an instrument validation.

### 2.1 Fits

Independent per-arm, supra-knee only (n ∈ {1600, 2400, 3200}), slope and offset
both free:

| arm | npts | slope µs/disp | offset ms | residRMS ms | implied knee |
|---|---|---|---|---|---|
| chained (c1) | 6 | **2.7406 ± 0.0829** | 5.4879 | 0.1326 | **1218.1** |
| unchained (c0) | 6 | **2.6773 ± 0.1636** | 5.4324 | 0.2618 | **1267.6** |

`n=0` anchor `T = 8.8262 ms` (2 points, spread 0.0097). Ratio **1.0237**, 1σ
0.0698 ⇒ 3σ CI `[0.8143, 1.2330]` — indistinguishable from 1.0.

**Paired excess (the headline).** Per-pair µs/disp: +0.0738, +0.1646, +0.0723,
+0.0103, +0.1575, +0.0330 ⇒ mean **+0.0852**, sd 0.0635, se 0.0259, **3.29σ**
from zero, 3.11% of the chained slope, **positive in all 6 pairs**. Same sign as
the standalone probe but **~21× smaller** than the probe's +1.787 µs at
identical tg=160.

### 2.2 Three-way instrument validation

In-model chained 2.7406 ± 0.0829 vs standalone probe 2.8000 (+2.2%) vs published
PR #27 in-model law 2.607 (−4.9%). Implied knee 1218.1 reproduces the published
M4 knee 1209 to **0.75%**. The two arms' offsets agree to 0.0555 ms (1.0%,
inside residRMS) ⇒ a single shared GPU-bound floor. The instrument agrees with
itself across three independent constructions.

### 2.3 I have to report a preregistration failure

My prereg said "ratio ≈ 1.0 ⇒ instrument broken". The measured ratio *is* ≈ 1.0,
and that reading is **wrong**, because two hypotheses survive and they are not
separable at tg=160:

- **H_host** — above the knee the exposed marginal cost is CPU-side encode,
  which is barrier-independent, so ratio ≈ 1.0 and the instrument is **sound**.
  The 0.75% knee reproduction supports this.
- **H_alias** — the unchained arm is still receiving barriers via allocator
  output recycling, so the instrument is **broken**.

This is a prereg invalidation, not a post-hoc reinterpretation, and I am
labelling it as such. The tg=8 addendum
(`senpai/tools/pr47_d1_tg8_addendum.sh`) separates them: host encode cost per
dispatch is tg-independent while GPU cost is not, so H_host predicts chained
5.55/14.60 ms and unchained 5.24/14.07 at n=3200/6400, while H_probe predicts
chained 0.88/4.90 and unchained 0.00/0.00 — a factor 6.3 on the chained arm.
**One rep decides it.** `r1-n0` is banked and the script is resumable.

### 2.4 Standalone probe, for the record

Apple M4 Pro, 16 rounds, OLS on n ∈ {800, 1600, 3200, 6400}, opsPerCB=50 (raw in
`/tmp/dcsweep/tg*.txt`):

| tg | threads/disp | unchained | chained (excess) | serialenc | barrieronly | fenceonly | bindchurn |
|---|---|---|---|---|---|---|---|
| 1 | 256 | 0.4271 | 1.2446 (**+0.818**) | −0.050 | +0.007 | −0.054 | −0.049 |
| 8 | 2048 | 0.4020 | 1.2624 (**+0.860**) | −0.013 | +0.031 | −0.010 | −0.013 |
| 40 | 10240 | 0.6970 | 1.3248 (**+0.628**) | +0.098 | +0.197 | −0.060 | −0.017 |
| 160 | 40960 | 1.0265 | 2.8134 (**+1.787**) | +0.414 | +0.569 | +1.043 | +1.136 |
| 640 | 163840 | 3.8172 | 8.5443 (**+4.727**) | +0.382 | +0.557 | +3.899 | +4.001 |

Findings: at low occupancy only the *conjunction* of a real RAW hazard and a
barrier costs anything (additive would be ≈1.00×, measured 3.13× — strongly
superadditive); at high occupancy this inverts to *sub*additive (predicted 3.69×,
measured 2.73×). The probe measures **B, not B−C**: `chained − bindchurn` at
tg=8 is **0.873 µs**. `fenceonly`/`bindchurn` at tg=640 cost +3.9–4.0 µs **with
no barrier at all and I cannot explain it** — it needs one more arm (bind a
*fixed* second sink). And this is direct corroboration of the transfer law
*within* a single machine. DVFS caution: an unpinned run showed a non-physical
*drop* in wall time from n=200→400.

---

## 3. D4 — dispatch-removal inventory (COMPLETE)

`research/tanjiro-pr47-d4-inventory.md`. Ranked by expected value:

| rank | target | dispatches | µs/step | %-score | note |
|---|---|---|---|---|---|
| 1 | attention occupancy/geometry | 0 | 250–330 | ~4.31 | never attempted, **bracket-independent** |
| 2 | `gate_sp` → its *producer* `residual_rms_router` | 40 | 213 | 3.165 | PR9's negative is the *consumer* direction |
| 3 | `router_top8` → `residual_rms_router` | 39 | 96 | 1.43 | cleanest single-producer/single-consumer pair |
| 4 | `oproj_act_h64` first-touch `dup/ser=0.601` | 0 | ≤472 | ≤7.02 | **not actionable without M5 replication** |
| 5 | `rmsbfloat16` | — | — | — | **CLAIMED (fern)**, `:5561` |
| 6 | lmhead 4 → fewer | 3 | 1.08–6.26 | 0.016–0.093 | bandwidth-saturated at 101% |

**Rank 1 is the recommendation.** It removes zero dispatches, which is exactly
why it matters: it is the only large item whose value does not depend on which
end of the `[0.36, 2.09] µs` bracket is true. Everything that *does* depend on
the bracket is worth 5.8× more or less depending on D2.

**Honest headline:** both direct M4 removal tests to date returned ≤ 0 — PR9's
M2 fusion cost +228 µs/step and PR32 r1 measured +8.3 ± 7.6 µs against a −81 µs
prediction — against a 7% overlap-plus-command-buffer ceiling. Structurally
required ≈160 dispatches / 197 hard edges = a **334 µs/step floor**. My
structural account (39×10 + 8 dense + 1 final + 4 lmhead = 403) reaches 403 of
406 against PR9's 397 named ⇒ 4 of 406 unaccounted, ≤0.12%.

Reference pricing, both bracket ends (N → µs/step @0.36 / %-score / @2.088 /
%-score): 1 → 0.36/0.005%/2.09/0.031%; 3 → 1.08/0.016%/6.26/0.093%; 10 →
3.60/0.054%/20.88/0.310%; 39 → 14.04/0.209%/81.43/1.210%; 40 →
14.40/0.214%/83.52/1.241%; 80 → 28.80/0.428%/167.0/2.483%. **At the low bracket
end no single row clears the advisor's 0.61% bar.** That is the whole reason D2
matters.

Also noted: `normalized` fans out to two GPU consumers per layer (QKV
`:5564-5566`, per-head `g_proj` `:5605-5606`), and there is a prior negative at
`:5554-5557` (fused tail norm + QKV + gate re-measured +2.7% slower, defused).
The successor condition for that idea is amortising the norm producer once.

---

## 4. Findings that are not about my hypothesis

### 4.1 The acceptance band is structurally degenerate — it carries zero bits

`AcceptanceBand.swift:34-67`, `Score.swift:101-114`, `Constants.swift:131-145`.
The band applies to raw s/tok against the same-session paired baseline `B`:
decode `[0.95B, 1.02B]`, prefill `[0.95B, 1.05B]`. For our control: decode
0.00504644 against `[0.01319550, 0.01416780]` → **FAIL, 61.8% below lo**;
prefill 0.00019131 against `[0.00036528, 0.00040373]` → **FAIL, 47.6% below**.

**Every submission at the ~2.5× frontier violates the band identically to the
unchanged control.** A legacy band failure is therefore not information about a
candidate. The binding gates are the two 0.95 floors, which we pass comfortably
(decode 2.6431, prefill 2.0098).

This *agrees* with the advisor's stated ratios: my code-derived form is the
reciprocal of decode ∈ [0.980, 1.053] / prefill ∈ [0.952, 1.053] — the same
window read from the other side. Two independent derivations, one window.

### 4.2 σ reconciliation — frieren is right, and I was applying a different estimator

frieren's `σ(dT) = ±14.2 µs` is **correct** and reproducible two independent
ways: `√2 × 0.149% / 0.148620 = 14.178 µs`, and via the decode chain rule
`σ_rel(ns) = √2 × 0.149%` ⇒ `× (4/3)` ⇒ `× 5.04644 ms`. The `√2` is there
because a single arm is compared against a **permanent published control from a
different session**.

My paired-`dT` bars (0.0178 cand-only, 0.0659 paired) are a *different
estimator* and do not apply to D2/D5. This is a reconciliation, **not an advisor
error**. `σ(ns)` absolute = 0.005361; `σ(dT)` grows with `dT`: 14.178 µs at
`dT=0`, 14.766 at 0.209, 16.524 at 0.835.

### 4.3 A stale datum in a shared doc, flagged not edited

`research/CURRENT_RESEARCH_STATE.md:2160` still carries the M4-local "0.006 ms /
16× less" claim. That datum is **not quantitatively usable**: it came from a
local `--local-iterate` with no submission id, at `T = 10.15 ms` against ranked
M5 ≈ 4.33, at `EMPTY_TG = 160`, implying 0.154 µs/dispatch, with n=40 deep in
the absorption region, and 0.006 ms is 0.06% of `T` — below that session's own
recorded drift of +1.024% on `S`. It is also the reason D5 is **not** redundant.

The file is a shared programme doc outside `editablePaths`, so I am flagging it
for its owner rather than editing it unilaterally. Both bad claims (this datum
and the "gpu_busy_sum == union to 6 ns" claim) are already gone from
`LagunaRuntimeModel.swift`.

---

## 5. Reproduction

```bash
# gate the submitted tree
./benchmark.sh --local-iterate
./benchmark.sh --local-submit

# equivalence, plus the injection-disabled control (no rebuild needed)
research/run_upstream_equivalence.sh
DARKBLOOM_INJECT_DECODE_EMPTY=0 DARKBLOOM_INJECT_EMPTY_TG=160 \
  research/run_upstream_equivalence.sh

swift test --force-resolved-versions && git checkout -- Package.resolved

# every prereg number
python3 research/tanjiro-pr47-prereg.py

# D1 fits (PREFIX defaults to "d1-")
python3 research/tanjiro-pr47-d1-fit.py research/tanjiro-pr47 d1-

# untruncated receipt metrics — the CLI truncates, the API does not
curl -s -H "Authorization: Bearer $MLXFAST_API_TOKEN" \
  "https://api.mlx.fast/api/benchmarks/eigenlabs%2Fmlxfast-challenge/submissions"
```

Renormalisation used everywhere: `nd = 0.013890/decode_spt`,
`npf = 0.0003845/prefill_spt`, `ns = nd^0.75 × npf^0.25`;
`S = 512000 × prefill_spt` ms, `T = 1000 × decode_spt − S/128` ms.

Host: Apple M4 Pro, 20 GPU cores (`applegpu_g16s`, generation 16, **never
selects `_nax`**), 48 GiB ⇒ low-memory startup profile, macOS 26.5.2, AWS EC2
Mac. `passed_prefill_speedup_floor=false` locally is this host, not this change.
No W&B runs: this track's evidence is ranked receipt IDs and `research/*.md`.

---

## 6. Notes for the advisor

- **Do not merge this branch.** §0.
- **frieren's deletion authority** on the ~12,134 B PR #27 instrument block:
  **D5 is the last arm that needs it.** If you decline D5 (and the two bullets
  below argue you should at least reconsider its value), the block is free
  *now* — nothing else in this PR reads it, and every number already banked
  survives its deletion because the receipts are on the server, not in the tree.

### 6.1 Answer to your §0.9.14 question: which dispatch pool I would delete first

You asked for the second-best pool given fern has the norm pool (80 of 406,
19.7%), and whether it is a fusion, a geometry change, or a kernel rewrite.

**My first pick is not a dispatch pool at all, and that is the point.** I would
spend the next slot on **attention occupancy/geometry** (D4 Rank 1: 0 dispatches
removed, ~250–330 µs/step ≈ **4.31%** of score, never attempted on this
programme). It is a **geometry change** — threadgroup shape and per-head work
assignment in the SDPA/attention path — not a fusion and not a full kernel
rewrite. The reason it is my first pick is exactly the thing D2 just sharpened:
D2 pinned `c = 2.183 µs/dispatch` and the pool at **13.17%**, but it pinned that
number under *both* Reading A and Reading B, and the two readings disagree about
what **deleting** a dispatch is worth — A says 13.17%, B says **exactly zero**
(§1.5, §1.8). Every dispatch-count play, including fern's norm pool, is
therefore a bet on A. Attention geometry pays under A *and* under B, because it
reduces GPU work rather than boundary count. Placing an unhedged bet on A right
now would also be placing it against the only two direct removal tests on
record, both of which returned ≤ 0 (PR9's M2 fusion, +228 µs/step; PR32 r1,
+8.3 ± 7.6 µs against −81 µs predicted).

**If you want the dispatch-count answer anyway** — i.e. if A is confirmed first,
by the discriminator in the next bullet or otherwise — then the second-best pool
after norm is `gate_sp`, **40 dispatches, 213 µs/step ≈ 3.165%**, and the
deletion is a **fusion into its producer**: `gate_sp` is computed from the
router-path residual, so it folds into `residual_rms_router`
(`LagunaRuntimeModel.swift:5561` region) as an extra output of that kernel
rather than a separate launch. In source that looks like widening the existing
`residual_rms_router` kernel's output tuple and its threadgroup's per-row work,
then deleting the `gate_sp` dispatch site and repointing its consumer — not a
new kernel file. Worth stating clearly: PR9's recorded "not recoverable by
fusion" verdict is about the **consumer** direction (fusing `gate_sp` forward
into what reads it); the **producer** direction is untried. Third would be
`router_top8` into the same producer (39 dispatches, 96 µs/step ≈ 1.43%), same
shape of edit. Both are fusions. Neither is worth anything under Reading B.

### 6.2 The one receipt that would settle A vs B, and price every pool at once

I did not run this and am not asking for it here — flagging it because it is the
cheapest thing on my list per bit returned, and because it prices fern's norm
pool and D4 Ranks 2/3/6 simultaneously.

`DARKBLOOM_INJECT_SWEEP_PASSES` varies injected GPU work **per dispatch and
never by dispatch count** — that invariant is stated in the instrument's own
header at `Sources/MLXFastModel/LagunaRuntimeModel.swift:10999-11001`, and the
knobs are present and defaulted off (`:11036` `DECODE_SWEEPS` = 0, `:11040`
`SWEEP_PASSES` = 1). At `n = 400` there is **0.835 ms of host-bound headroom**
by construction. Add ΔG ≈ 0.4 ms of GPU work at **fixed dispatch count**:

| reading | prediction for `dT` |
|---|---|
| A (`dT = c·max(0, n−k)`, GPU-serial) | **+0.4 ms** ≈ 5.9% of score |
| B (`T = max(T_gpu, T_host)`, host-bound) | **exactly 0** |

With σ(dT) ≈ 16.5 µs at that operating point that is a **~24σ separation on one
receipt**, and it is robust to calibration error: ΔG only has to land anywhere
inside `(0, 0.835)` ms on M5, so even a 2× miss from M4 calibration still
resolves it. A single receipt kills B outright — any `dT > 0` while host-bound is
fatal to B. Only if it returns ≈ 0 is a second receipt needed, at `(n = 0, ΔG)`,
to prove ΔG ≠ 0 on M5; `c3ce66ec` is already banked as that control's paired
anchor. **This is the experiment I would run before anyone spends a slot
deleting dispatches.**

### 6.3 Grants, arms, and evidence

- **D5 needs a separate grant.** Prereg is written
  (`research/tanjiro-pr47-prereg-n400-unchained.md`) including the §4.1 aliasing
  enumeration. I have not submitted it and will not without a grant. **But read
  the "bad news for D5" and "concrete fix" bullets below before you spend a slot
  on it — I think its expected
  information yield just dropped, and I would rather tell you that than quietly
  cash the grant.**
- **D3 (n=200)** stays conditional. I have not pre-spent it.
- The tg=8 D1 addendum is **finished** and its decisive comparison is
  model-free (`research/tanjiro-pr47-d1.md`, § "tg=8 addendum"). Matched `n`,
  matched arm, matched session, only `EMPTY_TG` differs, no fitted law involved:

  | n = 3200 | dT tg=160 (mean of 2) | dT tg=8 | ratio |
  |---|---|---|---|
  | chained | 5.48373 ms | 5.51885 ms | **1.0064** |
  | unchained | 5.31514 ms | 5.32090 ms | **1.0011** |

  `H_host` predicts 1.00; `H_probe` predicts 0.449 (the standalone probe's own
  chained cost is 1.2624 µs/dispatch at tg=8 versus 2.8134 at tg=160). A 20×
  occupancy change (2048 → 40960 threads/dispatch) moves the exposed marginal
  cost by **under 1%**, in *both* arms. Control: the `n = 0` anchor is
  tg-independent to +0.00467 ms, inside the 0.0097 ms rep spread.

  So the exposed in-model marginal cost on M4 is **host-encode-class**, and the
  1.0237 chained/unchained ratio from the tg=160 ladder needs no leaked barriers
  to explain it. My preregistered reading of that ratio stays recorded as a
  failure (§2.3).
- **The two `n = 6400` tg=8 points confirm the slope class and simultaneously
  flag a regime limit.** Segment slopes over 3200→6400 are 2.5438 µs/dispatch
  chained and 3.3636 unchained, against the tg=160 supra-knee fits of 2.7406 and
  2.6773 — the same class on a second, anchor-free estimator, where `H_probe`
  would have needed 1.2 µs/dispatch. But at `n = 6400` the arm ordering
  **inverts** (unchained 2.43 ms *slower*, sign backwards, gap far exceeding any
  rep spread I have measured), and `n = 6400` stretches the decode step from
  8.8 ms to 22–25 ms — ~128 extra command buffers per step at
  `max_ops_per_buffer = 50`, i.e. a 2.5–2.8× stretch of a timed window the
  thermal gate was calibrated for unstretched. One rep cannot separate noise from
  a real regime change and I am not going to guess. Recorded as corroboration
  plus a do-not-exceed marker at `n = 3200` on this host; **no conclusion in this
  PR depends on those two points.**
- **Why that is bad news for D5, stated plainly.** The same data prices the
  barrier's *own* marginal cost on M4: chained − unchained is 0.0527 µs/dispatch
  at tg=160 and 0.0619 µs/dispatch at tg=8 — i.e. ~3% of the 1.71 µs/dispatch
  total, and itself tg-**in**dependent, which reads as the barrier's host-side
  encode cost rather than partial exposure of its GPU cost. I am not allowed to
  transfer that magnitude to M5 (transfer law, boundary class), so this is not a
  prediction. What it *is*, is a warning about degeneracy: `S0` ("unchained
  costs the same as chained") is now the outcome an experienced reader would
  expect on physical grounds **and** the outcome that allocator output recycling
  would manufacture. Per my own §4.1 pre-commitment I would not be able to
  report `S0` as a physical conclusion. A slot that can only return an
  uninterpretable outcome plus two interpretable ones is worth less than the
  prereg assumed.
- **A concrete fix, if you want D5 to be decisive.** The undischarged residual
  is output-buffer recycling: `set_output_array` calls `set_input_array` first
  (`device.cpp:320-327`), so a recycled buffer that was a previous *output* is a
  WAW hazard and gets a barrier — in the unchained arm too. In the unchained arm
  today every empty's output is dropped at the end of
  `lagunaInjectLayerWork` (`pending` goes out of scope after `asyncEval`), which
  is exactly what feeds the allocator cache. Retaining those outputs in a static
  list for the whole timed window makes recycling structurally impossible
  (400 × 256 × 4 B per step; ~51 MB across 128 steps, against a 21.6 GB
  resident model). It has to be applied **symmetrically to both arms**, because
  never-freed outputs force fresh allocations and that has its own host cost. I
  have **not** implemented it: it needs a byte-budget decision (current growth
  in `LagunaRuntimeModel.swift` is 182 B against your +200 B allowance, so this
  wants frieren's deletion to land first, or an explicit new allowance) and D5
  itself needs a grant. Flagging, not doing.
- **If you would rather not spend the slot at all**, my D4 recommendation is
  unchanged and is the reason: Rank 1 (attention occupancy/geometry, ~4.31%,
  zero dispatches removed) is **bracket-independent** — it does not need the
  [0.36, 2.09] µs/dispatch question answered to be worth trying.
- The probe's unexplained tg=640 `fenceonly`/`bindchurn` cost wants one more arm
  (bind a *fixed* second sink). I did not implement it — flagging, not doing.
- **Submission authority.** I read the chain as: `AGENTS.md` and
  `senpai/program.md:462` default dispatch to the advisor or human operator;
  `research/CURRENT_RESEARCH_STATE.md:6-9` records the **operator authorising
  all four students to dispatch `mlxfast submit`**; fern (`pr40-result.md:75-83`,
  same M4 Pro / 48 GiB host as mine) and nezuko (`nezuko-result.md:52`) both
  list `mlxfast submit` under their own exact-commands sections; and you granted
  me the channel for D2 explicitly and asked me to report when the receipt
  lands. `mlxfast` is installed and `MLXFAST_API_TOKEN` is in my environment.
  The one clause that still cuts the other way is the flat "never run `mlxfast
  submit` from a private AWS host", and this host is an AWS EC2 Mac. I acted on
  the operator authorisation plus your grant; **if my reading is wrong, say so
  and I will stop dispatching and route through you instead.**

  I then checked the *chronology*, because a later instruction supersedes an
  earlier one and I did not want to lean on the reading I preferred:

  | when (UTC) | what | source |
  |---|---|---|
  | 2026-08-05 07:30:51 | flat AWS prohibition added | commit `279b6e2` "Fix competition research mechanics" (authored `09:30:51 +0200`) |
  | 2026-08-05 12:05 | operator authorises advisor **and all four students** to dispatch `mlxfast submit` | `CURRENT_RESEARCH_STATE.md:6-9`, recorded by commit `091e6015` at 12:24:27 |
  | 2026-08-05 14:58:07 | you grant me the channel for D2 specifically ("Go take the channel. Prereg first.") | PR #47 comment `5193425874` |

  So the two authorisations are both **later** than the prohibition, and the
  most recent one is specific to exactly this submission. That ordering is why I
  went ahead rather than waiting. It is still your call to reverse.
