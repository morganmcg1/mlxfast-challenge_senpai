# PR #47 D2 — PREREGISTRATION: ranked chained `n=100` arm

Committed **before** the ranked submission. Nothing below is revised after the
receipt lands; the receipt section is appended, not edited.

Arm: one ranked submission of `maple-tanjiro/dispatch-law-close` with these four
values **baked into the `lagunaInjectEnvInt` defaults in the submitted tree**,
not passed as environment variables (the ranked runner sets no `DARKBLOOM_*`
variable, so a default is the only way an injected knob reaches the M5):

| knob | D2 default | `0411779d` default | `c3ce66ec` default |
|---|---|---|---|
| `DARKBLOOM_INJECT_DECODE_EMPTY` | **100** | 400 | 0 |
| `DARKBLOOM_INJECT_EMPTY_TG` | **8** | 8 | 8 (inert at `n=0`) |
| `DARKBLOOM_INJECT_EMPTY_SPREAD` | 1 | 1 | 1 |
| `DARKBLOOM_INJECT_EMPTY_CHAIN` | 1 | (knob absent ⇒ chained) | 1 |

No control arm. Judged against the permanent published control receipt
`c3ce66ec` (`n=0`; the `CHAIN` path is identical because `CHAIN=1` is the
default and `n=0` executes no empties).

### `EMPTY_TG` must be 8, not the current HEAD default of 160

`0411779d` is the tree at commit `b8da628` ("PR34 r2 L1: inject 400 empty
decode dispatches at 8 threadgroups"). Verified directly:

```
$ git show b8da628:Sources/MLXFastModel/LagunaRuntimeModel.swift | grep -n DARKBLOOM_INJECT
11046:    "DARKBLOOM_INJECT_DECODE_EMPTY", 400)
11058:    "DARKBLOOM_INJECT_EMPTY_TG", 8)          <-- eight, not 160
```

Current HEAD's default is `EMPTY_TG=160`. Submitting D2 at 160 would put the
new point on a **different cost curve** from the only tg-bearing anchor, and
the degeneracy solve in §1 would be arithmetic on three points that do not lie
on one line. The dependence is not second-order: my M4 standalone probe
(`research/tanjiro-pr47-d1.md`) measures a chained per-dispatch slope of
1.258 µs at `tg=8` versus 2.800 µs at `tg=160` — a factor of 2.2 for the same
mechanism. `c3ce66ec` is `n=0`, so `tg` never executes there and that anchor is
`tg`-free. **The submitted D2 tree therefore carries `EMPTY_TG` default = 8.**

Reproduction of every number below and in the D5 prereg:
`python3 research/tanjiro-pr47-prereg.py`. That script is research-only support
outside `editablePaths`; it is not part of the challenge runtime.

## 1. What is degenerate, and why one point breaks it

Two existing ranked points, both from the same instrument:

| receipt | n | S (ms) | T (ms) | ns |
|---|---|---|---|---|
| `c3ce66ec` | 0 | 97.9496 | 4.28121 | 2.544360 |
| `0411779d` | 400 | 97.6165 | 5.07320 | — |

`dT(400) = 0.83509 ms` paired (0.79199 ms cand-only). Fit a piecewise-linear
injected-dispatch cost `dT(n) = c · max(0, n − k)`. Two points constrain one
combination of `(c, k)`, so an entire one-parameter family survives:

```
c(k) = 835.09 µs / (400 − k),   k ∈ [0, 400)
```

`k ≥ 400` is dead (it forces `dT(400)=0`); that is how the earlier `H_gpu`
(k≈461) and `H_cpu` (k≈1200) hypotheses died at 34.8σ. The two named survivors
are the endpoints the advisor picked:

- **H_knee0**: `c = 2.0877 µs`, `k = 0` → **`dT(100) = 0.20877 ms`**
- **H_knee300**: `c = 8.3509 µs`, `k = 300` → **`dT(100) = 0.00000 ms`**

`n = 100` is the maximally separating single point inside the surviving family:
it splits `k ∈ [0,100)` from `k ∈ [100,400)`.

## 2. σ — reconciliation, not a correction

I previously objected that `σ(dT) = ±14.2 µs` "exists nowhere in the repo".
That objection was about the literal string. **The derivation is correct and I
reproduce it exactly**; I withdraw the objection.

```
σ(ns)/ns = √2 × 0.149 %          = 0.210718 %      (two independent ns reads)
σ(dT)    = 0.00210718 / 0.148620 = 14.178 µs       (exchange rate 14.862 %/ms)
σ(ns)    = 0.00210718 × 2.544348 = 0.005361  ns units
```

The `√2` is the whole point: this arm is compared against a **permanent
published control measured in a different session**, so the statistic is a
difference of two independent `ns` reads, each with per-family cv 0.149 %.

My own bars — 0.0178 ms cand-only, 0.0659 ms paired — are a **different
estimator** (paired same-session `dT`, where the session term cancels and there
is no `√2`). They are not the applicable σ for this design. Both are right for
their own design.

**Robustness.** Cross-session drift (thermal policy, host firmware, OS
scheduler) is not in the 0.149 % per-family cv, so the true cross-session σ
could be inflated. I therefore also report every verdict at **3 × σ**
(42.5 µs). The design survives that stress: separation 0.20877 ms is 14.21σ at
face value and **4.74σ at 3 × σ**.

**σ(dT) is not a constant — it grows with `dT`.** The 0.149 % cv is
*multiplicative* on `ns`, so a fixed `ns` fraction maps to a larger absolute
`dT` the further the arm sits from the control. 14.178 µs is the value **at
`dT = 0`** and is therefore the right number for the R2/H_knee300 branch only.

| operating point `dT` (ms) | σ(dT) (µs) | which branch uses it |
|---|---|---|
| 0.000 | 14.178 | R2 / H_knee300 |
| 0.209 | 14.766 | R1 / H_knee0 (D2) |
| 0.306 | 15.038 | D5 M4-ratio prediction |
| 0.835 | 16.524 | D5 high anchor (`0411779d`) |

Using the flat 14.178 µs everywhere overstates significance by up to 17 % at
`dT = 0.835`. Every σ quoted below is evaluated **at its own operating point**;
the headline separations are unaffected at these magnitudes (14.21σ, not 14.7σ)
because the two-hypothesis separation is divided by the σ of the hypothesis
being tested.

## 3. Predictions in the judged quantity

`ns = (0.013890/decode_spt)^0.75 × (0.0003845/prefill_spt)^0.25`.
Injection is decode-only, so `prefill_spt` and `S` are unchanged and
`np = 2.009809` for both hypotheses.

| | decode_spt (s/tok) | T (ms) | nd | **ns** |
|---|---|---|---|---|
| control `c3ce66ec` | 0.00504644 | 4.28119 | 2.752435 | **2.544348** |
| H_knee0 (n=100) | 0.00525521 | 4.48997 | 2.643090 | **2.468156** |
| H_knee300 (n=100) | 0.00504644 | 4.28119 | 2.752435 | **2.544348** |

(My recomputed control `ns` is 2.544348 vs the published 2.544360 — a 5e-6
relative rounding difference in the receipt's reported s/tok, 0.002σ. I use the
published **2.544360** as the control in the decision rule.)

Separation **0.076192 ns units = 14.21σ**.

## 4. Decision rule (binding)

Let `ns_obs` be the derived `ns` of the arm, `σ = 0.005361`.
`z0 = (ns_obs − 2.468156)/σ`, `z300 = (ns_obs − 2.544360)/σ`.

| region | `ns_obs` | verdict |
|---|---|---|
| R1 | `[2.452072, 2.484241]` (`|z0| ≤ 3`) | **accept H_knee0, reject H_knee300.** `k ∈ [0,100)`, `c ∈ [2.088, 2.784) µs` |
| R2 | `[2.528264, 2.560432]` (`|z300| ≤ 3`) | **accept H_knee300, reject H_knee0.** `k ∈ [100,400)`, `c ≥ 2.784 µs` — but see §5 |
| R3 | `(2.484241, 2.528264)` | both rejected → intermediate knee; report the **continuous readout** of §6, no named hypothesis accepted |
| R4 | `< 2.452072` | `dT(100) > 0.2088 ms + 3σ` → knee is negative-equivalent, i.e. `c < 2.088 µs` with superlinear onset, or a session/instrument fault. Report continuous readout **and** flag |
| R5 | `> 2.560432` | arm **faster** than the control by >3σ. Not producible by adding work. Declared in advance as **an instrument or cross-session fault, not evidence for either hypothesis** |

At `3 × σ` the two windows widen to `[2.42, 2.52]` and `[2.42, 2.67]` and stop
being disjoint; in that stress case I report the continuous readout only. The
face-value rule above is the primary.

Regions are fixed now. I will not re-centre them on the observed value.

## 5. The interpretation trap in R2 — flagged BEFORE the spend

A null at `n=100` does **not** mean "the dispatch pool is small". It has two
physically distinct readings and they give **opposite** decisions:

**Reading A — piecewise host cost.** `dT(n) = c·max(0, n−k)` is the true cost
function; the 406 real dispatches each pay the supra-knee `c`. Then a *smaller*
`dT(100)` implies a *larger* `c` and a **larger** pool:

| `r = dT(100)/835.09 µs` | knee `k` | `c` (µs) | pool = 14.862 × 406 × c/1000 |
|---|---|---|---|
| 0.500 | −200 | 1.3918 | 8.40 % of score |
| 0.250 (**H_knee0**) | 0 | 2.0877 | **12.60 %** |
| 0.125 | 57 | 2.4357 | 14.70 % |
| 0.000 (**H_knee300**) | ≥100 | ≥2.7836 | **≥16.80 %** |

Under Reading A the removal programme (D4) is **never** killed by this
experiment — a null only raises the prize.

**Reading B — saturation slack.** `T = max(T_gpu, T_host(406+n))`. A knee at
`k>0` means host encode has `k` dispatches of headroom, so `T = T_gpu` and
**removing a real dispatch is worth exactly zero, forever**. Under Reading B a
null kills D4's premise outright.

One point at `n=100` cannot separate A from B. What can, and already partly
does:

1. **Reading B needs `c_host = 8.35 µs/dispatch` on M5.** My D1 in-model M4 fit
   is 2.607 µs and the independent standalone probe 2.813 µs at the same
   `tg=160` (7.4 % agreement, two instruments sharing no code). M5's fabric is
   ~2.25× faster than M4's. An M5 host-encode cost 3.2× *larger* than M4's is
   not physical. This is a strong prior against H_knee300 **under either
   reading**, and it is a prior, not a measurement.
2. **Wall-vs-GPU gap 0.322 ms** at `n=0` (against GPU-busy union 9.498 ms over
   45 command buffers / 406 dispatches). Pure Reading B predicts a zero gap.
   0.322 ms ≈ 154 × 2.088 µs, i.e. host encode is *partly* exposed — consistent
   with A, or with a small non-zero-slack hybrid, not with `k=300`.

**Recommendation to the advisor:** publish the D2 verdict as
`(knee-bracket, c-bracket, pool-bracket)` under Reading A, with Reading B
carried as an explicit unresolved alternative, rather than as "the pool is
X %". I will write it that way unless told otherwise.

## 6. Continuous readout (reported in every region)

The inverse map `ns_obs → dT` must use the **exact** closed form, not the
14.862 %/ms exchange rate. The rate is the derivative of `ns` at the operating
point; it is only a first-order expansion and it drifts by several percent over
the `dT` range this design spans. Since injection is decode-only, `np` cancels
and the exact inverse is algebraic:

```
ns ∝ nd^0.75 = (0.013890 / decode_spt)^0.75,  decode_spt = d0 + dT/1000
⇒ dT_obs [ms] = 1000 × d0 × ( (2.544360 / ns_obs)^(4/3) − 1 ),   d0 = 0.00504644
r             = dT_obs(100) × 1000 / 835.09
k             = (100 − 400 r) / (1 − r)
c             = 835.09 / (400 − k)               [µs]
pool          = 14.862 × 406 × c / 1000          [% of score, Reading A]
```

Linear-vs-exact, on the two points where I can check it against a published
`T`-difference:

| point | `ns` | `dT` linearised | `dT` exact | published `dT` |
|---|---|---|---|---|
| `0411779d` (n=400) | 2.283549 | 0.72768 ms | **0.78277 ms** | 0.79199 cand-only |
| D2 H_knee0 (n=100) | 2.468156 | 0.20460 ms | **0.20881 ms** | (prediction 0.20877) |

The linearised form is 7.0 % low at `n=400` and 2.0 % low at `n=100`; the exact
form reproduces the H_knee0 forward prediction to 4e-5 ms and closes to within
0.0092 ms of the published `0411779d` `T`-difference. That residual is the
prefill move (`S` 97.9496 → 97.6165 ms), which the decode-only algebra above
deliberately does not model; I report it as a residual rather than absorbing it.
`pool` keeps the 14.862 %/ms rate because there it *is* used correctly — as a
local derivative on a small (≤ 1 µs) perturbation.

This generalises the two-hypothesis rule — H_knee0 and H_knee300 are just its
`r = 0.25` and `r = 0` endpoints — and it returns a usable answer in R3/R4
where the two-point rule returns "no decision". I report it regardless of
region.

### Convention: paired vs candidate-only `dT`

`dT(400)` is **0.83509 ms paired** and **0.79199 ms candidate-only** — a 5.4 %
spread, larger than every σ in this design. The two differ because the paired
form also differences the same-session baselines (`bT` 12.41494 → 12.37185 ms).
Mixing them silently would move a verdict. Rule, fixed here:

- **Primary throughout D2 and D5: paired**, matching the advisor's
  `dT_chained(400) = 0.83509 ms` and the degeneracy family `c(k)` in §1.
- Candidate-only is reported alongside, never substituted.
- The ranked receipt publishes `bS`/`bT`, so both are computable for my arm and
  I will state which is which on every line.

## 7. Acceptance-band arithmetic — degenerate at this frontier

The advisor asked for a hand-computed band check. `Sources/MLXFastCore/`
`AcceptanceBand.swift:34-67` + `Score.swift:101-114` + `Constants.swift:131-145`
apply the band to the **raw seconds-per-token against the same-session paired
baseline `B`**, not to any renormalised quantity:

- decode: `decode_spt ∈ [0.95·B_d, 1.02·B_d]` ⇔ `decode_speedup ∈ [0.9804, 1.0526]`
- prefill: `prefill_spt ∈ [0.95·B_p, 1.05·B_p]` ⇔ `prefill_speedup ∈ [0.9524, 1.0526]`

With `B_d = 0.013890` and `B_p = 0.0003845` s/tok:

| | decode window (s/tok) | actual | verdict |
|---|---|---|---|
| control `c3ce66ec` | [0.01319550, 0.01416780] | 0.00504644 | **FAIL** (63.7 % below `lo`) |
| this arm (H_knee0) | [0.01319550, 0.01416780] | 0.00525521 | **FAIL** (62.2 % below `lo`) |

Prefill window `[0.00036528, 0.00040373]`, actual `0.00019131` → **FAIL**, both.

So: **the legacy band is structurally unsatisfiable for any submission at the
current ~2.5× frontier**, because its down-side exists to cap a single
submission's gain at 5 % and our cumulative gain against the pinned baseline is
165 %. It returns *the same verdict for my arm and for the unchanged control*,
i.e. **zero bits about this experiment**. That is exactly why the deployed
wrapper silences it. A "legacy band failure" line in my receipt must not be
read as evidence about the arm.

The gates that do bind are the two 0.95 floors, and both pass with enormous
margin: decode `2.6431 ≥ 0.95` ✓, prefill `2.0098 ≥ 0.95` ✓ (unchanged).
Predicted floor margin loss from the injection: decode 2.7524 → 2.6431, still
2.78× the floor.

## 8. What I will report from the receipt

`S`, `T`, raw `decode_spt` / `prefill_spt`, `decode_speedup`,
`prefill_speedup`, both floor verdicts, correctness status, `max_abs_diff`,
derived `nd`/`np`/`ns`, `dT_obs(100)`, the region (R1–R5) the observation lands
in, the §6 continuous readout, the §7 band arithmetic re-done on the actual
numbers, and both the face-value and 3 × σ verdicts.

If the arm lands in R5, or correctness fails, I report that as loudly as a win
and do **not** request a retry slot without advisor direction.

## 9. Cost and constraints

One ranked submission. Two earlier L2 submissions were refused at 10:30:11Z and
10:35:52Z; **those are not retried** and this is not a resubmission of either.
The #27 instrument block in `LagunaRuntimeModel.swift` (~11049-11232) must stay
alive until this receipt lands; frieren's deletion authority unblocks the moment
I say so in my result.

Editable-path budget at base `1849b376d73f69f9a6b9018619ac665ae4bceb33`:
`current=2940973/3000000 headroom=59027 growth=0/262144 files=142`. This file
and its script live in `research/`, outside `editablePaths`: **0 submitted
bytes**. The only submitted change is the `+179 B` unchained-empties knob
already counted against the `+200 B` ceiling.
