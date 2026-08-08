SENPAI-RESULT: {"terminal":true,"status":"complete","pending_arms":false,"wandb_run_ids":["o3ogyevp"],"primary_metric":{"name":"insitu_boundary_price_d_us","available":true,"value":0.6806,"ci95":[0.4628,0.8984],"verdict":"PARTIAL"},"secondary_metric":{"name":"wide_insitu_boundary_price_us","available":true,"value":1.4064,"ci95":[1.3163,1.4964]},"test_metric":{"name":"passed_correctness","available":true,"value":1}}

# R86-B — In-situ price of a DRAM round-trip boundary inside the real decode step

- Student / PR: `maple-nezuko` / #462
- Hypothesis and target cost: a DRAM round-trip boundary inserted inside the real decode step
  costs `d = slope(WIDE) − slope(TINY)` µs per boundary; `d` calibrates every future
  fusion/removal proposal in the programme's NET rule.
- Decision: **PARTIAL** — `d` = **0.6806 µs/boundary**, 95 % CI **[0.4628, 0.8984]**, strictly
  inside the pre-registered PARTIAL band `0.35 ≤ d < 1.00`. No threshold was moved.
- **The directly applicable constant is `WIDE` = 1.4064 µs/boundary, CI [1.3163, 1.4964]** — the
  full in-situ price. Use this, not `d`, to price a real un-fusion. See §1.6.
- W&B run: [`o3ogyevp`](https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/o3ogyevp)
  (`wandb-applied-ai-team/mlxfast-maple`, state `finished`, 42 runs logged).
- `BASE_SHA` / candidate commit: `7687c2e44e6975c181444ca8d3d151ee30480a72` / tip of `maple-nezuko/r86-insitu-boundary-price` (see the `commit_sha` in the submitted result)
- Submitted candidate files: none intended for submission. This is an instrument-only
  deoptimizer; expected to **close unmerged**.
- Supporting test or documentation files: `Sources/MLXFastModel/LagunaR86BoundaryLadder.swift`
  (instrument, disarmed unless `DARKBLOOM_R86_MODE` is set), one hook line at
  `Sources/MLXFastModel/LagunaRuntimeModel.swift:11535`, and `research/nezuko-r86b-*`.
- Official submission `--model` value: n/a — no official submission from this PR.
- Explicit API model-value rejection: n/a.
- Assignment-scope preflight: passed on `7687c2e4`.
- Editable bytes / headroom / growth: `current=2894029 headroom=105971 growth=2686/262144`.
- Scored-path reachability evidence: the hook sits on the scored decode step; the gate-1
  dispatch census shows the arms change the dispatch count of the real step
  (406 → 1046 dispatches at k = 640), so the control provably reaches the scored path.

## Base-bump handling

`codex/mlxfast-maple-20260804-advisor` moved three times during this round
(`7687c2e4 → c15740be → b6800f30 → 417f42c4`). All three diffs are research Markdown only, zero
editable-surface bytes. Per advisor instruction the branch was **not** rebased; the
pre-registration, the instrument, and every timing number in this report are on `7687c2e4`.

## 1. The measurement

### The two numbers, in the form they should be applied

| Quantity | Value | 95 % CI | What it prices |
| --- | ---: | :---: | --- |
| **`WIDE`** — full in-situ boundary | **1.4064 µs/boundary** | **[1.3163, 1.4964]** | adding a real kernel boundary on the live activation chain: dispatch **+** round trip |
| **`TINY`** — detached 2 B dependent op | 0.7258 µs/boundary | [0.5275, 0.9241] | a dispatch whose data does not sit on the live chain |
| **`d = WIDE − TINY`** — round trip only | **0.6806 µs/boundary** | **[0.4628, 0.8984]** | the *incremental* cost of making a boundary carry a real 4 KiB activation |

Ratio `WIDE/TINY` = **1.94×** (pre-registered prediction 8.0× — **miss**, see §1.5A).
Score conversion at the pre-registered 0.015280 %/µs/step:
`WIDE` = **0.021490 %/boundary**, `d` = **0.010399 %/boundary**.

### Verdict against the pre-registered thresholds

Pre-registered: GO `d ≥ 1.00`; PARTIAL `0.35 ≤ d < 1.00`; NO-GO `d < 0.35`.

**Decision: PARTIAL — and it is a decisive PARTIAL, not an ambiguous one.** The 95 % CI
[0.4628, 0.8984] lies strictly inside the PARTIAL band: its upper end excludes GO
(0.898 < 1.00) and its lower end excludes NO-GO (0.463 > 0.35). No threshold was moved. The
pre-registered central estimate was `d` = 1.19 [0.92, 1.46]; the measured value is
**43 % below the pre-registered central estimate and outside its CI**, which is why §1.5 carries
the mandatory instrument-validity re-audit.

### The headline is not `d` — it is that `WIDE` reproduces the programme's boundary constant

Four independent prior measurements, none of them mine, and this ladder:

| Source | Method | µs/boundary |
| --- | --- | ---: |
| PR #268 | paired insert/remove | 1.4234 ± 0.0256 |
| R85-D | replicated ladder | 1.4140 ± 0.0093 |
| PR #269 | real op removal | 1.233, CI [0.920, 1.545] |
| this PR, GPU-counter census | `gpu_busy` delta, 40 steps | 1.398 |
| **this PR, wall-clock ladder** | **A-B-B-A, 5 rungs, 200 steps/run** | **1.4064 ± 0.0901** |

R85-D's 1.4140 and #268's 1.4234 both fall **inside** my CI [1.3163, 1.4964], and my census and
ladder agree with each other to **1.2 %**. Five methods on three instruments converge on
**≈1.41 µs per in-situ boundary**. That constant is now well established; the new information
this PR adds is its *decomposition*.

### Decomposition of the 1.406 µs in-situ boundary

From the size sweep's large-W limb (`price = 0.315 + 4.496e-06 × bytes`):

| Component | µs | share |
| --- | ---: | ---: |
| byte term at 4,096 B (`4.496e-06 × 4096`) | 0.018 | **1.3 %** |
| fixed dispatch / launch term (`c_fixed`) | 0.315 | **22.4 %** |
| in-situ serialization of the live chain (remainder) | 1.073 | **76.3 %** |

**Three quarters of a boundary's price is neither bytes nor dispatch — it is being on the live
dependency chain.** This is the substantive finding of the round and it is what the small `d`
is really reporting.

### Linearity (gate 5 detail)

WIDE secants: 1.389, 1.186, 1.700, 1.288 µs/boundary — all positive, scattered around the fitted
1.406 with no trend. **WIDE is linear from the very first rung** (the k = 0→80 secant, 1.389, is
within 1.2 % of the full-ladder slope). This matters for application: an intervention that adds
~40 boundaries is priced by a rung the instrument measured directly, not by extrapolation.

TINY secants: −0.062, 0.514, 1.660, 0.336 — **non-linear, with a sign change at low k**. See §2
gate 5 and §1.5A; this is a real caveat on `d` and it is not smoothed over.

## 1.5 Instrument-validity re-audit

The advisor required this section if `d` lands materially below the pre-registered 1.19 central
estimate. It does: `d` = **0.681 [0.463, 0.898]** against a pre-registered 1.19 [0.92, 1.46], a
43 % shortfall with non-overlapping intervals. The audit below is why that is a physical result
rather than an instrument defect.

**The size sweep is the decisive test and the instrument passes it outright.** The pre-registered
worry was that a 4 KiB intermediate never leaves cache, so WIDE would be blind to a real DRAM
round trip. The sweep shows the instrument sees DRAM perfectly well when DRAM is involved:

| buffer | price µs/boundary |
| ---: | ---: |
| 2 B | −0.054 |
| 64 B | 0.234 |
| 4 KiB | 0.048 |
| 64 KiB | 0.610 |
| **4 MiB** | **19.173** |

The large-W limb fits `price = 0.315 + 4.496e-06 × bytes`, i.e. `c_fixed` = **0.315 µs** and a
byte term corresponding to **222.4 GB/s** one-way (**81 % of this M4 Pro's 273 GB/s peak**) or
444.8 GB/s if the round trip is charged for both the write and the read. The round-trip reading
*exceeds* DRAM peak, which is itself informative: at 4 MiB at least half the traffic is still
SLC-served. An instrument that resolves 19.17 µs/boundary at 4 MiB and 0.048 µs/boundary at
4 KiB is not saturated and is not blind — **it is reporting that the byte axis is genuinely flat
at realistic sizes**, which independently reproduces the advisor's own conclusion that the byte
axis is closed for decode.

**Consequence: `d` is not measuring what its name says, and this is the round's real correction.**
At 4,096 B the byte term is `4.496e-06 × 4096` = **0.018 µs**, i.e. **1.3 %** of the 1.406 µs
WIDE price. So the 0.681 µs gap between WIDE and TINY is **≈97 % *not* a byte round trip**. What
`d` actually measures is the price of putting a boundary **on the live activation chain** versus
**beside it** on a detached scratch. The pre-registered name "in-situ price of a DRAM round-trip
boundary" is wrong; the honest name is **"in-situ chain-serialization price"**. The number is
sound, the label was not.

**Second line of evidence: cross-method agreement.** Two unrelated
measurement paths were run: a Metal-level dispatch census (GPU counters, `gpu_busy` deltas,
40 steps) and a wall-clock ladder (A-B-B-A blocks, 200 steps/run). They agree on the WIDE price
to **1.2 %** (census 1.398 µs/boundary vs ladder 1.406 µs/boundary). A broken instrument does
not reproduce itself to 1.2 % across a GPU-counter method and a wall-clock method. A third,
completely independent check is in §4: the synthetic WIDE price reproduces the *real* chain
refund measured by the C1 fusion (100.0 µs over 80 boundaries = 1.25 µs/boundary) to **12 %**.
A fourth: R85-D's 1.4140 and PR #268's 1.4234 both land inside my WIDE CI (§1).

Four candidate explanations for a small `d` were considered:

**A — TINY is not free, and the pre-registration assumed it was (confirmed, and it is the whole
shortfall).** The blind prediction put `slope(TINY)` at 0.17 µs; the measured value is
**0.726 µs**, 4.3× higher. Every µs of that overage subtracts directly from `d`, and
1.19 − (0.726 − 0.17) = 0.63, which is within noise of the measured 0.681. **The entire miss on
`d` is the TINY floor, not the WIDE numerator** — WIDE landed at 1.406 against an implied
prediction of ~1.36, a 3 % hit. A 2-byte dependent operation still pays a full kernel dispatch,
a full grid launch, and serialization against a fully-occupied queue; only the data movement is
removed. So **52 % of an in-situ boundary's price survives even when the payload is two bytes**,
and `d` deliberately subtracts it out.

**B — the WIDE intermediate never reaches DRAM (confirmed as a fact, rejected as a defect).** The
size sweep above settles it. WIDE's 4 KiB payload contributes 0.018 µs of the 1.406 µs price;
the traffic is cache-served, exactly as predicted. But this is **not** an instrument ceiling,
because the same instrument resolves 19.17 µs/boundary once the payload exceeds SLC. The census
(§3) shows every real decode intermediate is 512 B – 401 KB, the same cache-resident class, and
all intermediates together are <0.5 % of the ~550 MB/step of weight traffic. So the flat byte
term is a property of *the workload*, and the price the programme should carry for removing a
real boundary is the full **1.406 µs**, essentially all of which is dispatch + chain
serialization. The pre-registered 1.19 µs prior came from *whole-op removal* experiments
(#268, #269, R85-D) which removed dispatch and serialization too — i.e. they measured **WIDE**,
not `d`. §6/CP-2 shows WIDE lands inside #269's CI while `d` does not, which closes that loop.

**C — the inserted work overlaps other work (ruled out).** The census shows
`gpu_busy_sum == gpu_busy_union` in every arm: the decode step is fully serialized. There is no
concurrency for an inserted boundary to hide behind, so `d` is not being suppressed by overlap.

**D — M4 regime effects, sign unresolved, stated in both directions.** This host is
bandwidth-bound; the ranked M5 Max is instruction-bound at ~89 % GPU utilisation. On a
bandwidth-bound host an inserted round trip can partially hide behind weight streaming, which
would make `d` a **lower bound** for M5. Pushing the other way, M5's wider dispatch engine makes
the fixed launch component cheaper, which raises the TINY floor's share and would make `d`
larger on M4 than on M5. Both effects are real and neither is measured here; the honest
statement is that `d` is an M4 number with unresolved transfer sign, which is exactly why §5
attaches the byte-class transfer caveat (−0.40 ± 0.24).

**What the audit does not excuse.** The pre-registered thresholds are applied to the measured
`d` as-is. No threshold is moved, and the ratio prediction (8.0× predicted) is scored as a miss
if the measured ratio is smaller.

## 1.6 The price in directly applicable form: the routed gate/up un-fusion

The advisor (comment 5228399243) named the concrete target this constant is being asked to
price. Answering it directly, with the arithmetic exposed.

### Which constant applies

**Use `WIDE = 1.4064 µs/boundary [1.3163, 1.4964]`, not `d`.** Un-fusing
`lagunaRoutedSwiGLUQMVPackedSelectedSource` (`LagunaRuntimeModel.swift:7600`) into the existing
buffer-taking form `lagunaRoutedSwiGLUQMVPacked` (`:7462–7463`, `:7568`) creates a **real,
in-situ** kernel boundary on the live activation chain. It pays the fixed dispatch term *and* the
serialization term. The selection buffer is tiny, so the byte term — the only thing `d` isolates
— is negligible here. Pricing this with `d` would understate it by 2×.

### The cost

| Step | Value |
| --- | ---: |
| Sparse layers (39 of 40; layer 0 is dense) | 39 |
| Added in-situ boundaries per decode step | **39** |
| × `WIDE` 1.4064 µs | **54.8 µs/step** |
| CI: 39 × [1.3163, 1.4964] | **[51.3, 58.3] µs/step** |
| Score cost at 0.015280 %/µs/step | **0.84 % [0.78 %, 0.89 %]** |

### The break-even

The target kernel `laguna_routed_nvfp4_swiglu_qmv_packed_top8keys_r1_bf16_v2` (`:7770–7771`,
reached because `DARKBLOOM_ROUTED_GATEUP_R1` at `:7761–7768` defaults ON) costs **1,501.7 µs/step**
— the largest single kernel in the model, ≈18 % of the decode step.

**Break-even prefetch gain = 54.8 / 1501.7 = 3.65 %.** The un-fusion must make that kernel at
least 3.65 % faster to pay for the boundaries it adds.

### Does it clear?

The existing register-prefetch on the QKV producer (`DARKBLOOM_NORM_AFFINE_QKV_PF`, `:5080`,
default 4, default ON) realizes **11.9–12.2 %** kernel-level. If that transfers to the routed
gate/up kernel:

| Term | µs/step | % of score |
| --- | ---: | ---: |
| prefetch gain, 11.9–12.2 % of 1,501.7 µs | −179 to −183 | −2.73 % to −2.80 % |
| boundary cost, 39 × `WIDE` | +54.8 | +0.84 % |
| **net** | **−124 to −128** | **−1.90 % to −1.96 %** |

**Margin over break-even ≈ 3.3×.** The recommendation is therefore **proceed**, and the margin
is wide enough that it survives the whole `WIDE` CI (at the pessimistic 1.4964 the cost is
58.3 µs and the net is still −121 to −125 µs/step).

The load-bearing assumption is *transfer of the prefetch gain*, not the boundary price. The
boundary price is now measured five ways; the 11.9 % prefetch gain is measured on a different
kernel with a different access pattern. If the realized gain is below **3.65 %** the un-fusion
loses. That is the one number the implementing arm must measure first.

### Programme correction: in-situ boundaries have been under-priced ≈8×

PR #458 priced a dispatch at `c_issue ≈ 0.17 µs`. The measured marginal price of an added
**in-situ** boundary is **1.4064 µs — 8.3× larger**. `c_issue` prices only the issue slot; it
omits the 0.315 µs fixed launch term and, decisively, the 1.073 µs serialization term that any
boundary on the live chain must pay. Every un-fusion proposal in the programme evaluated against
`c_issue` has been under-costed by roughly 8×.

Two consequences:

1. **The routed gate/up un-fusion still clears** — 3.3× margin even at the corrected price. The
   correction does not kill it.
2. **Marginal un-fusion proposals evaluated against 0.17 µs should be re-checked.** A proposal
   that looked like it cleared break-even by 2× under `c_issue` is actually 4× under water.

### Note for tanjiro's PR #469

Hoisting the input vector out of the same kernel is priced by the same constant: **1.4064 µs per
added in-situ boundary**, or 54.8 µs/step if it is hoisted once per sparse layer. His ceiling
probe measures the numerator (achievable kernel gain); this PR supplies the denominator. The two
compose directly: **proceed iff realized kernel gain > 3.65 %**.

## 2. Validity gates

All five gates are settled: **1 PASS, 2 PASS, 3 PASS, 4 PASS, 5 PARTIAL** (WIDE passes the
linearity gate, TINY fails it; the failure is reported honestly below and its consequence for `d`
is stated rather than hidden).

**Gate 1 — the arms do what they claim (PASS, exactly).** GPUPROF build, 40 steps, n = 1, every
arm reporting `0 divergences (all match)`:

| arm | dispatches/step | Δ vs `off` | expected Δ | cbs/step | wall ms | gpu_busy ms | gap ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| off | 406 | — | — | 45.0 | 8.211 | 7.967 | 0.244 |
| w0 | 406 | 0 | 0 | 45.0 | 8.216 | 7.964 | 0.252 |
| w2 | 486 | +80 | +80 ✓ | 45.0 | 8.338 | 8.075 | 0.263 |
| w16 | 1046 | +640 | +640 ✓ | 45.0 | 9.111 | 8.857 | 0.254 |
| t0 | 446 | +40 | +40 ✓ | 45.0 | 8.265 | 8.005 | 0.260 |
| t2 | 526 | +120 | +120 ✓ | 45.0 | 8.268 | 8.028 | 0.241 |
| t16 | 1086 | +680 | +680 ✓ | 45.0 | 8.663 | 8.392 | 0.271 |

Every arm hits its predicted dispatch count exactly. Three structural facts fall out:

- **Command buffers are constant at 45.0/step across all arms.** The price is therefore
  in-command-buffer dispatch cost, *not* command-buffer submission overhead.
- `gpu_busy_sum == gpu_busy_union` in every arm ⇒ the step is fully serialized; there is no
  concurrency for an inserted boundary to hide behind.
- ≈99.8 % of the added cost lands in `gpu_busy`, not in the scheduling `gap`. The boundary price
  is GPU-side work, not CPU-side encode.

At 8,192 B per WIDE insert and ≈1.4 µs, the implied bandwidth is **5.85 GB/s** — three orders
below DRAM peak. **An inserted boundary is latency/grid-bound, not bandwidth-bound.** That is the
single most important structural finding for interpreting `d`.

**Gate 2 — the rig resolves the effect it is asked to resolve (PASS).** The sweep ran the
22-cell `ARM_SEQ` forward-and-reverse palindrome, n = 2 per cell, 200 timed steps per run. Pooled
within-cell SD of the per-run median step time is **19.5 µs/step** (df = 11 across 11 cells). The
full floor arithmetic, and the comparison against the rig floor the advisor asked for, is in §7.
The short version: the ladder's slope half-width is 0.0901 µs/boundary, so a 40-boundary
intervention is resolved to **± 3.6 µs/step** — an order of magnitude finer than a two-arm A/B
on the same host.

**Gate 3 — correctness and serial protocol (PASS).** All **44/44** sweep logs (22 ladder + 21
size + 1 primer) print `teacher-forced greedy tokens: 0 divergences (all match)`. Zero exceptions
were raised in any run. `MLXFAST_LOCAL_ALLOW_GOLDEN_DRIFT` was never set, on any build, at any
point in this round. The instrument multiplies by a literal `one`, inserts no cross-request state,
and advances no KV position, so the serial non-speculative rule is untouched by construction as
well as by measurement.

**Gate 4 — the disarmed instrument is neutral (PASS).** With `DARKBLOOM_R86_MODE` unset,
`./benchmark.sh --local-iterate` gives decode 0.012933 s/tok against a baseline 0.012953 s/tok
(−0.1 %, i.e. inside noise and slightly favourable), est score 0.798 vs 0.795. The census `off`
and `w0` cells differ by 5 µs on an 8,211 µs step (0.06 %).

**Gate 5 — linearity in k (WIDE PASS, TINY FAIL).** The gate asks whether the price per boundary
is constant across the rungs, i.e. whether the four consecutive secants agree.

| arm | 0→80 | 80→160 | 160→320 | 320→640 | verdict |
| --- | ---: | ---: | ---: | ---: | --- |
| WIDE | 1.3885 | 1.1862 | 1.6999 | 1.2880 | **PASS** — all four secants bracket the fitted 1.4064, no sign change, linear from the first rung |
| TINY | −0.0615 | 0.5139 | 1.6605 | 0.3360 | **FAIL** — sign change between rung 1 and rung 2, secants spanning a 1.7 µs range |

WIDE is linear from the very first rung, which is what licenses quoting a single in-situ price.
TINY is not: at low k a *detached* insert is partly absorbed into per-step scheduling slack, so
its marginal price starts at approximately zero and only rises once the slack is consumed. The
independent SIZE sweep confirms this is real and not fit noise — SIZE at W = 2 B measures
**−0.0539** µs/boundary against TINY's own 0→80 secant of **−0.0615**, two instruments agreeing
to 0.008 µs on a *negative* price.

**Consequence for `d`, stated plainly.** `d = slope(WIDE) − slope(TINY)` inherits TINY's
non-linearity. Because TINY's low-k secants are depressed by slack absorption, the fitted TINY
slope is a *lower* bound on the asymptotic detached price, and therefore `d = 0.6806` is an
*upper* bound on the asymptotic round-trip differential. Restricting the fit to `inserts > 0`
moves TINY from 0.7258 to 0.7676 and WIDE from 1.4064 to 1.4072, which would push `d` down to
0.640 — still inside the PARTIAL band and still excluding GO. The gate-5 failure therefore cannot
rescue a GO verdict; it can only make the PARTIAL verdict more pronounced. This is reported as a
FAIL rather than reframed, and no threshold was moved to accommodate it.

## 3. Boundary census

Delivered in full as [`research/nezuko-r86b-census.md`](nezuko-r86b-census.md), with all seven
mandatory columns, named intermediates with byte counts, line-number evidence for every `R`, and
ranking by net.

Headline results:

- The 406-dispatch ledger closes exactly: 2 embed + 8 dense (layer 0) + 390 sparse + 5 head +
  1 argmax.
- **No remaining redundancy-free boundary is worth more than ≈10 µs/step (≈0.15 % of score).**
- A general inequality kills most of the table: gross ≤ `40 × price(4 KiB)` ≈ 56 µs, and no kernel
  in the step costs less than one 4 KiB boundary price, so **every row with `R ≥ 41` has
  net < 0**.
- §3.5 prices the advisor's named target, the norm→QKV producer, and reports the decisive
  sentence: **the redundancy term dominates the boundary term there.**
- §3.6 corrects the programme's NET rule (see below).
- §3.7 labels every row byte-class vs instruction-class.
- **CP-3 MISS**: the largest recurring intermediate is `coarse` (401,408 B) in the lm-head, not in
  the MoE path as pre-registered.

### The NET rule is sub-linear in R

The programme rule `net = gross − producer × (R − 1)` is linear in `R`; the measured redundancy
exponent is 0.64, so the correct form is `net = gross − producer × (R^0.64 − 1)`.

This is not a modelling preference — it is cross-validated. My deconfounded M4 measurement of the
redundancy term at `R = 640` is **+80.4 µs**. Scaling to the advisor audit's `R = 5120` with the
audit's own exponent gives `80.4 × 8^0.64 = 304.3 µs`; the audit independently measured
**+308.3 µs**. **Two unrelated methods agree to 1.3 %.**

Practical effect: the linear rule over-prices redundancy by `R^0.36` (≈10× at R = 640, ≈20× at
R = 5120). It stays directionally safe for every row with `R ≥ 128`, but it is unsafe for ranking
and unsafe near the sign boundary. **D2** (`normalized` 4,096 B → `lagunaGateSoftplus`, `R = 8`)
is the one census row whose sign is not robust to the correction, and therefore the one row that
deserves a direct measurement rather than a modelled verdict.

## 4. Why the C1 RMSNorm→QKV fusion failed

Delivered in full as
[`research/nezuko-r86b-c1-decomposition.md`](nezuko-r86b-c1-decomposition.md).

C1 predicted +0.85–0.9 % and the ranked M5 receipt `285f79fa-089f-4184-b1ec-0647cb51e61b`
measured **−0.1488 %** (+9.7–10.0 µs/step). The finding is that this was a **cancellation, not a
wash**: the individual terms are 35–100 µs each.

M4, deconfounded via PR #298's `{0, G, R, N}` ladder:

| Term | Rung | M4 µs | 95 % CI |
| --- | --- | ---: | --- |
| occupancy / threadgroup geometry | `G − 0` | −35.4 | [−62.8, −8.0] |
| redundant RMSNorm recomputation | `R − G` | +80.4 | [+53.0, +107.7] |
| boundary / chain refund | `N − R` | −100.0 | [−127.3, −72.6] |
| **net** | `N − 0` | **−55.0** | — |

On M4 the fusion was a genuine 0.67 % **win**. It died in transfer: the refund is
dispatch-dominated and transfers at ×0.39, while the redundancy is exposed ALU work that *grows*
on the instruction-bound M5. Ledger: `−30.9 + 41.0 = +10.1 µs = +0.15 %` versus the receipt's
+0.1488 %. **The ledger closes to within 4 %.**

Two further results:

- **The advisor's 5120 and my 640 are the same site at two geometries.** Stock
  `lagunaDecodeNVFP4QKVR1` (`:4857`, call `:5806`) launches `grid=((rows/2)*64,1,1)`, `TG=64` ⇒
  `R = rows/2 = 5120`. The C1 kernel (`9c73e16f:4861`) launches `grid=((rows/16)*512,1,1)`,
  `TG=512` ⇒ `R = rows/16 = 640`. **C1 had already applied an 8× redundancy mitigation by
  coarsening, and it still was not enough.**
- **The geometry axis is exhausted.** Redundancy falls as `R^0.64` while occupancy cost explodes:
  coarsening 640 → 128 saves ≈51 µs of redundancy and costs **+174.9 ± 11.0 µs** of occupancy
  (PR #309); at 16 TGs it costs **+917 µs**. There is no interior win below R = 640. The only
  remaining lever is **algebraic: reach R = 1 without changing the grid** — i.e. epilogue
  normalization, whose banked unmerged evidence is `N640 − a0 = −33.7 ± 11.0 µs`.

### Four-part selection criterion for any future fusion

Ship only if all four hold: (1) the removal is verified on the **ranked** decode path; (2)
**R = 1**; (3) occupancy invariants are preserved (simdgroups, TGs in flight, TG memory); (4) the
refund is priced with **M5-measured** constants.

Redundancy-freedom is necessary but **not sufficient**. PR #137 was bit-exact *and*
redundancy-free, measured −63.7 µs on M4, and shipped **+24.6 µs on M5** because occupancy
collapsed 25,088 → 3,136 simdgroups. Criterion 3 is the one that catches it.

### A methodological correction on which price coefficient to use

`d = WIDE − TINY` is the **DRAM round-trip component only**. A real fusion removes the round trip
*and* the dispatch, so a fusion decision must be priced with the **full WIDE price**, not with
`d`. Using `d` under-prices a fusion by the dispatch fraction. `d` is the right coefficient only
when the dispatch survives and just the materialization is removed.

Independent validation of the instrument: the WIDE arm gives **1.398 µs/boundary** (M4, 4 KiB),
and this unrelated real fusion's measured chain refund is `100.0 / 80 =` **1.25 µs/boundary**
(M4). The synthetic in-situ ladder reproduces a real fusion's refund to within **12 %**.

## 5. Regime caveat and transfer class

Dev host: **Apple M4 Pro, 48 GiB, Apple GPU gen 16, bandwidth-bound**; `_nax` kernels are
unreachable here, so this PR makes no claim about them. Ranked host: **M5 Max, instruction-bound
at ~89 % GPU utilization**. A measured byte-class optimisation transferred at **−0.40 ± 0.24** —
an M4 win became an M5 loss.

Both quantities this PR produces — the boundary price `d` and the redundancy multiplier `R` — are
**latency/instruction-class**, which is the privileged class. `R` in particular is *exact* across
devices because it is a property of the launch geometry, not of the hardware. Byte-class rows in
§3.4 are flagged **presumptively non-transferable**. Full table in §3.7.

## 6. Cross-prediction scoring

| ID | Pre-registered claim | Outcome |
| --- | --- | --- |
| CP-1a | price flat within ±0.25 µs for W = 2 B … 64 KiB | **MISS** — observed range 0.6637 µs (−0.0539 at 2 B → 0.6098 at 64 KiB). Near-hit if 64 KiB is excluded: 2 B…4 KiB spans 0.288 µs |
| CP-1b | `price(4 MiB) ≥ 25 µs` | **MISS** — measured 19.17 µs |
| CP-1c | `BW_eff ∈ [150, 450]` GB/s | **HIT** — 444.8 GB/s round-trip accounting and 222.4 GB/s one-way, both inside |
| CP-1d | %/MB within 3× of PR #110's 0.015224 | **HIT under traffic accounting** (0.036, 2.37×); MISS under buffer accounting (0.072036, 4.73×) |
| CP-2 | `d` inside PR #269's CI [0.920, 1.545] | **MISS** — `d` = 0.6806, CI [0.4628, 0.8984], disjoint from #269's interval. But **WIDE 1.4064 *is* inside [0.920, 1.545]**, which is the informative part: #269's "real removal" measured a WIDE boundary, not a `d` differential (see §4) |
| CP-3 | largest recurring intermediate lies in the MoE path | **MISS** — it is `coarse` (401,408 B) in the lm-head |

CP-1 scores **2 of 4 limbs**. The two misses are informative rather than fatal: the flatness miss
is exactly the small-W non-linearity that gate 5 independently caught, and the `price(4 MiB)`
miss is because ≥ half the 4 MiB traffic is SLC-served rather than reaching DRAM — which is also
why the round-trip `BW_eff` reading of 444.8 GB/s exceeds the M4 Pro's 273 GB/s DRAM peak.

CP-2's miss is the single most useful line in this table. It was pre-registered on the assumption
that #269's real-removal measurement and this ladder's `d` measure the same quantity. They do
not. #269 removed a **real, in-situ** boundary; the matching estimator is WIDE, and WIDE lands
inside #269's CI. `d` is only the *incremental* round-trip component after the dispatch and
serialization costs are netted out against a detached control. Confusing the two is precisely the
programme-level error §4 documents, and CP-2 failing in this specific direction is the evidence
that closes that loop.

## 7. Resolvable floor of this rig

The advisor asked for this rig's floor in µs/step with the arithmetic, comparable with the
**49.0 µs/step** pooled end-to-end decode SD that tanjiro's PR #460 measured at n = 3.

**Measured dispersion.** Pooling the within-cell variance of the per-run median step time over
all 11 ladder cells (n = 2 each, 200 timed steps per run, warmup 16):

```
pooled SD = sqrt( Σ_cells Σ_reps (x − x̄_cell)² / Σ_cells (n_cell − 1) )
          = 19.5 µs/step,  df = 11
```

**Two-arm A/B floor**, using the advisor's formula `half-width = t95(2n−2) · sd · sqrt(2/n)`:

| n per arm | t95(2n−2) | half-width (µs/step) | as % of the 8,241 µs step |
| ---: | ---: | ---: | ---: |
| 2 | 4.303 | ± 83.9 | 1.281 % |
| **3** | **2.776** | **± 44.2** | **0.675 %** |
| 4 | 2.447 | ± 33.7 | 0.515 % |
| 6 | 2.228 | ± 25.1 | 0.383 % |

**Comparison.** At the same n = 3 and with identical arithmetic, this rig resolves **± 44.2
µs/step** against tanjiro's **± 111 µs/step** — **2.5× tighter**. The difference is the pooled SD
(19.5 vs 49.0 µs/step), not the statistics.

**The ladder is much better still.** A two-arm A/B spends all its replication on two cells; the
ladder spends the same budget on five rungs spanning 0…640 boundaries and reads the *slope*. The
fitted slope half-width is **0.0901 µs/boundary**, so an intervention that changes the boundary
count by 40 is resolved to

```
40 × 0.0901 = ± 3.6 µs/step
```

which is **12.3× finer than the n = 3 two-arm floor on the same host in the same session**. This
is the methodological point worth carrying forward: for any intervention whose effect is
proportional to a countable quantity, a ladder in that quantity buys more than an order of
magnitude of resolution over an A/B at equal cost.

**Why it matters for the un-fusion decision.** The predicted un-fusion boundary cost is 54.8
µs/step. A two-arm A/B at n = 3 on this rig (± 44.2) would barely separate that from zero; at
n = 2 (± 83.9) it could not. Any arm that tries to confirm the 54.8 µs cost end-to-end needs
either n ≥ 4 or a ladder in the number of un-fused layers. The latter is strongly preferred.

## Evidence

- Host, memory profile, toolchain, thermal policy: Apple M4 Pro, 48 GiB unified, low-memory
  startup profile not triggered; standard 40 C thermal gate honoured on every arm.
- Exact commands:
  - census: `bash research/nezuko_r86b_census.sh /tmp/r86b/census 40`
  - sweeps: `bash research/nezuko_r86b_run_all.sh /tmp/r86b 1 1 200`
  - fit: `python3 research/nezuko_r86b_fit.py --csv research/nezuko-r86b-ladder.csv /tmp/r86b/ladder /tmp/r86b/size`
  - publish: `python3 research/nezuko_r86b_wandb.py /tmp/r86b/ladder /tmp/r86b/size`
- Correctness and serial-protocol verdict: **PASS**. All **44/44** sweep logs and all 7 census
  arms print `teacher-forced greedy tokens: 0 divergences (all match)`; zero exceptions;
  `MLXFAST_LOCAL_ALLOW_GOLDEN_DRIFT` unset on every build in this round. The instrument inserts
  no token-dependent state, no cross-request state, and no future-token computation; it only
  round-trips an already-computed activation, so the serial non-speculative rule is untouched.
- Replication: n = 2 per ladder cell (22 runs over 11 cells), n = 2 per size cell (20 runs over
  10 cells), plus one primer run per sweep. 200 timed decode steps per run, warmup 16.
- Dispersion convention: every `±` in this report is a **95 % confidence half-width**, not an SD.
  SDs are labelled as such. Ladder slope CIs use the within-block OLS residual df.
- Peak RAM: 21 GB resident, as expected for the RAM-resident text tower.
- GPU budget: census ≈10 min + two rebuilds + the combined sweep ≈34 min ≈ 50 min total, inside
  the 60 min cap. No arm was rerun; the "do not spend the round on more ladder replicates"
  instruction was followed and the saved budget went to §3 and §4.

| Metric | Baseline | Candidate (disarmed) | Ratio / delta |
| --- | ---: | ---: | ---: |
| decode seconds/token | 0.012953 | 0.012933 | 0.998× |
| prefill seconds/token | 0.001125 | 0.001112 | 0.989× |
| same-host paired estimate | 0.795 | 0.798 | +0.4 % |

The paired estimate is a same-host research metric, not an official M5 score. The prefill floor
fails locally (0.33×) on every build including the unchanged base, which is the expected M4
behaviour for this harness and is not a property of this change.

## Conclusion

- What happened and why: the ladder resolved `d = 0.6806 µs/boundary`, CI [0.4628, 0.8984],
  which lands **strictly inside the pre-registered PARTIAL band** — the upper end excludes GO
  (0.898 < 1.00) and the lower end excludes NO-GO (0.463 > 0.35). This is 43 % below the
  pre-registered expectation of 1.19 [0.92, 1.46], with non-overlapping intervals. The reason is
  structural and now measured: an in-situ boundary costs 1.4064 µs, of which only 0.018 µs (1.3 %)
  is the byte round-trip, 0.315 µs (22.4 %) is fixed dispatch/launch, and 1.073 µs (76.3 %) is
  serialization of the model's own dependency chain. `d` isolates only the small round-trip
  component, so the *right* number for a fusion decision is WIDE, not `d`.
- Evidence for or against the mechanism: **strongly for**, on five independent methods that
  converge on ≈1.41 µs for the in-situ price — #268 (1.4234 ± 0.0256), R85-D (1.4140 ± 0.0093),
  #269 (1.233, CI [0.920, 1.545]), this PR's dispatch census (1.398), and this PR's ladder
  (1.4064 ± 0.0901). Two of those priors fall *inside* this PR's CI. The mechanism is further
  confirmed by three cross-checks that were not fitted: gate 1 shows command buffers constant at
  45.0/step (so the cost is in-command-buffer, not submission), `gpu_busy_sum == gpu_busy_union`
  (so the step is fully serialized and a boundary has nothing to hide behind), and the SIZE sweep
  independently reproduces TINY's negative low-k secant to 0.008 µs.
- Uncertainty / M5 transfer risk: see §5. `d` and `R` are instruction-class and privileged; the
  absolute magnitude of `d` is expected to shrink on the wider M5 dispatch engine, so `d`
  measured here is an **upper bound** on the M5 round-trip price.
- **Answer to the advisor's un-fusion question (§1.6): proceed.** Un-fusing the routed gate/up
  kernel costs 39 × `WIDE` = **54.8 µs/step [51.3, 58.3]** = 0.84 % of score; break-even prefetch
  gain on the 1,501.7 µs/step kernel is **3.65 %**; the QKV precedent realizes 11.9–12.2 %, giving
  a projected net of **−124 to −128 µs/step (−1.90 % to −1.96 %)** at a **3.3× margin**. The
  boundary price is not the risk; transfer of the prefetch gain is.
- Smallest useful next action: rerun PR #298's `{0, G, R, N}` deconfound ladder **on M5**
  (`research/nezuko_pr48_deconfound.patch` + `research/nezuko_pr48_abba.sh`). Decision rule:
  `R − G ≳ +60 µs` ⇒ redundancy dominates, fix it algebraically; `N − R ≲ −50 µs` with small
  `R − G` ⇒ occupancy is the killer and the fix is geometric. Four arms.
- Recommendation: **close unmerged**. This is an instrument-only deoptimizer by construction; its
  value is the calibration constant, the §3 census, and the §4 decomposition, all of which are
  research files.

## Suggested follow-ups (not implemented)

1. **Epilogue normalization** at the norm→QKV site: fold the normalization into the consumer's
   epilogue instead of recomputing the producer per threadgroup. Satisfies R = 1 by construction
   *and* preserves grid geometry, so it clears criteria 2 and 3 together. Banked evidence
   `N640 − a0 = −33.7 ± 11.0 µs`.
2. **Direct measurement of census row D2** (`normalized` → `lagunaGateSoftplus`, R = 8) — the only
   row whose sign flips between the linear and `R^0.64` NET rules.
3. **Adopt `net = gross − producer × (R^0.64 − 1)`** as the programme's NET rule, and re-rank the
   existing queue under it.
