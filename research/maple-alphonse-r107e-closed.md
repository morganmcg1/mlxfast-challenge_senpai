# R107-E — family A (T3b gated-affine oproj) amortisation: CLOSED

**Verdict: `N-T3B-CLOSED-BY-CENSUS`.**

PR #644, assignment `maple-r107-e-decode-oproj-amortisation`, revision
`r108-p-rev1`, base `705484b9`. Host: M4 Pro (Apple GPU generation 16), not the
ranked M5. Zero official receipts consumed.

This note closes family A on the instruction/amortisation axis and records why
the roofline falsifier the earlier revision asked for was **not** run: two
merged independent censuses had already reduced the available budget below the
smallest effect any instrument on this host can resolve, and my own in-situ
measurement agrees with them in sign.

---

## §1 The three independent closures

### §1.1 frieren #597/#107-F — the per-call decomposition

`research/maple-frieren-r107f-t2d-down-residual-amortisation.md` (merged at
`d3045bd8`), verdict `N-T2D-ISSUE-BOUND`. For the same kernel family, of
**22.07 µs/call**:

| component | share | line |
|---|---|---|
| unique-byte DRAM floor | **86.6 %** | `:17`, `:503` (5,013,504 B / 22.07 µs = 227.1 GB/s = **87.15 %** of achievable) |
| barrier drain | **14.0 %** | `:17` |
| residual available to amortisation | **≤ 2.5 %** | `:681`, `:838` |

Her direct amortisation arm A1 (`outputs_per_simd` 4 → 8, i.e. exactly the
lever R107-E was chartered to pull) came back **+1.012 µs/call slower**, and
eleven further efficiency arms paid zero-or-negative.

### §1.2 tanjiro #648/#107-G — the family regime census

`research/maple-tanjiro-r107g-decode-family-regime-census.md` (merged at
`705484b9`) classifies family A as **BYTES** and states the closure directly at
`:45`, `:69` and `:583`:

```text
A  T3b oproj h64   37.26 µs dispatch   32.492 ALU   36.462 DRAM floor
                   0.794 µs non-byte slack   23.8 M4 µs/step   0.159 %cs   0.40 bars
```

87.2 % of peak, **91.3 % of geometry-achievable**. The *entire* non-byte budget
— all exposed ALU, all latency, all glue — is **0.79 µs/dispatch = 23.8 M4
µs/step = 0.159 % of `cs` = 0.40 of one bar**. An instruction-side change that
removed *every* instruction in the kernel still could not clear 0.4 %. Its
`#644 alphonse` row reads **"STOP on the instruction axis; RE-AIM to bytes or
stand down"**, confidence high.

### §1.3 my own in-situ anchor — agrees in sign, and is worse than a null

I did not stand down on assertion alone. I ran the amortisation lever end to end
in the scored decode path, 36 `--local-iterate` runs across three ABBA sessions
(`screen1` ×4, `abba1` ×16, `abba2` ×16), all `rc=0`, all
`passed_correctness: true`, artifacts in
`research/artifacts/maple-alphonse-r107e/insitu/`, stats in
`research/artifacts/maple-alphonse-r107e/insitu-stats.json`.

Design: a 2×2 over amortisation (A: results-per-simdgroup) and threadgroup
shape (B), driven by `DARKBLOOM_OPROJ_GEOM` ∈ {`g0` = shipped, `g1`, `g2`,
`g3`}, one binary, env-switched arms, 120 s precool plus the harness cool gate
before every run.

Arm means, decode s/token (M4, lower is better):

| arm | decode s/token | vs g0 |
|---|---|---|
| **g0 (shipped)** | **0.01308061** | — (fastest) |
| g1 | 0.01323032 | +1.147 % |
| g2 | 0.01318400 | +0.959 % |
| g3 | 0.01311252 | +0.573 % |

Contrasts, 8 ABBA halves, forward/reverse split reported to expose drift:

| contrast | % | CI | µs/step M4 | CI | sign | p |
|---|---|---|---|---|---|---|
| **A_amortisation** | **+0.766 %** | [+0.353, +1.179] | **+99.96** | [+46.03, +153.89] | **8/8** | **0.008** |
| g1 vs g0 | +1.147 % | [+0.409, +1.885] | +149.65 | [+53.36, +245.94] | 8/8 | 0.008 |
| g2 vs g0 | +0.959 % | [+0.372, +1.545] | +125.10 | [+48.56, +201.63] | 7/8 | 0.070 |
| g3 vs g0 | +0.573 % | [−0.379, +1.526] | +74.83 | [−49.46, +199.12] | 7/8 | 0.070 |
| B_threadgroup_shape | +0.381 % | [−0.313, +1.074] | +49.69 | [−40.79, +140.18] | 6/8 | 0.289 |
| AB_interaction | −0.193 % | [−0.744, +0.359] | −25.14 | [−97.08, +46.80] | 2/8 | 0.289 |

The prefill placebo axis shows no matching structure (all six prefill contrasts
straddle zero), so this is not a whole-host drift artefact.

**Does my anchor disagree with either closure? No — it is stronger than both.**
frieren and tanjiro bound the amortisation lever's *upside* at ≤2.5 % of a call
and 0.40 bars respectively; both are statements that the lever cannot **win**.
My in-situ measurement says the lever actively **loses** `+99.96 µs/step`
(`+0.665 %cs`) with 8/8 sign consistency and `p = 0.008`. Amortising this kernel
is not a null, it is a regression, which is exactly what a kernel already at
91.3 % of geometry-achievable bandwidth should do when you trade issue slots for
per-thread register and scale-bank pressure.

One honest caveat on magnitude: this instrument's own MDE at 8 halves is
0.41–0.95 % depending on the contrast, i.e. ±54 to ±124 µs/step. The **sign** of
`A_amortisation` is solid (8/8, p = 0.008); its **magnitude** is only resolved to
roughly a factor of two. That is sufficient to close the lever and insufficient
to publish `+99.96` as a precise constant.

---

## §2 Why the roofline falsifier was not run

The R107-E revision would have had me build a roofline falsifier to test whether
family A is byte-bound. Two merged reports had already answered that on this
same host family with better instruments (a per-call decomposition and a
five-family regime census with an ALU-ceiling calibration), and my end-to-end
number agrees in sign. Re-running the falsifier could only have re-derived a
verdict already in the rulebook, at a cost of roughly two hours of exclusive
model-holding host time. The advisor withdrew it in `r108-p-rev1` and re-aimed
me at R108-P; that re-aim is the correct call and this note is the receipt.

## §3 What carries forward

- Family A / T3b gated-affine oproj is **closed on the instruction and
  amortisation axes**. Do not re-open it without a *bytes*-side mechanism worth
  ≥15.10 MiB/step (5.8 % of the family's own traffic).
- The R107-E geometry instrument
  (`DARKBLOOM_OPROJ_GEOM`, `LagunaOProjGeometry`, parameterised
  `lagunaGatedAffineOProjNVFP4Source(numSimdgroups:resultsPerSimdgroup:)`) is
  **reverted**; the submitted surface on this branch is byte-identical to
  `705484b9`. It is recoverable from this branch's history if a bytes-side
  successor ever needs the same 2×2 harness.
- The ABBA runner `research/maple-alphonse-r107e-insitu.sh` and analyser
  `research/maple-alphonse-r107e-analyse.py` are reusable and are the direct
  ancestors of the R108-P ladder tooling.
- **Reusable negative result for the programme:** on a kernel already above
  ~87 % of achievable DRAM rate, increasing results-per-simdgroup is not
  neutral, it is a measurable regression. Two of the four R107-E arms were
  significant regressions on their own.
