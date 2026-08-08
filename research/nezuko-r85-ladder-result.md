# R85-D result — decode dispatch-cost ladder

**Verdict in one line:** the per-dispatch cost is **not** work-independent. The
work-independent part is **0.10–0.36 µs** (pooled fit 0.17) — *roughly an order
of magnitude smaller than H's 2–3 µs* — and the 1.41 µs an on-chain dispatch
actually costs is **86 % exposed memory traffic**. Dispatch *count* is not the
lever; DRAM **round-trips** are. That single distinction explains the `cc6ddc1`
negative, the 3.00/4.70 µs "per-call floors", and the programme's six previous
null results at once.

- Assignment: PR #458, `maple-r85-d-dispatch-cost-ladder`, revision `r85-d-rev1`
- Branch: `maple-nezuko/r85-dispatch-cost-ladder`
- Base: `codex/mlxfast-maple-20260804-advisor` @ `cc5688d0` (advisor confirms the
  later `f64456dd` delta is `research/`-only, no `editablePaths` byte changed,
  so no rebase and matched-pair timing stands)
- Host: M4 Pro, 48 GiB, Apple GPU generation 16. **M4 evidence, directional for
  M5.** `_nax` is unreachable here; this arm is decode-only so that is not a gate.
- Pre-registration: `research/nezuko-r85-prereg.md`, committed `2a69afa`
  2026-08-08T19:33:27Z, **before the first ladder run**. Never edited.

---

## 1. Pre-registered prediction and decision table

Recorded before any measurement (§2–3 of the prereg):

| pre-registered quantity | predicted | 80 % interval | **measured** | hit? |
| --- | --- | --- | --- | --- |
| on-chain slope (dispatch + barrier, 4 KiB) | 1.0 µs | [0.4, 2.0] | **1.4140** | ✅ inside |
| tiny slope (dispatch + barrier, 4 B) | 0.6 µs | [0.15, 1.3] | **0.1716** | ✅ inside, at the floor |
| ratio wide : tiny | 1.5–2× | — | **8.24×** | ❌ **badly missed** |
| shape | non-linear, slack/knee | — | **wide perfectly linear** | ❌ **missed** |

The tiny row is scored with the pre-registered estimator (the all-points fit).
The step-removed refit of §3 gives **0.0989**, which falls *below* the
pre-registered 80 % interval — so on the strictest reading I missed that
prediction low as well. Both readings point the same way, so I record it rather
than choosing the estimator that keeps the prediction inside its band.

Decision table (prereg §3), read off the **on-chain** slope's 95 % CI:

| slope | verdict | mandated conclusion |
| --- | --- | --- |
| ≥ 2.0 µs | H strongly supported | propose one fusion |
| **0.5 – 2.0 µs** | **H partially supported** | **quantify the ceiling as slope × deletable boundaries, give the score-equivalent, state whether it clears the ~80 µs/step bar** |
| < 0.5 µs | H refuted | close the family loudly |

**Measured on-chain slope 1.4140, 95 % CI [1.4047, 1.4233] — entirely inside the
middle row, no boundary straddle.** The middle row is therefore mandated, and
§6 below discharges exactly what it demands.

The tie-break for a non-linear ladder ("headline = top-half secant") does not
bind for the headline arm: the wide ladder is linear, and its top-half secant
(1.4146) is indistinguishable from the full fit (1.4140).

---

## 2. Ladder data

One binary; every arm selected by environment variable, so no arm differs by
code layout, register allocation or kernel selection. Injection is the first
statement of `LagunaRuntimeDecoderLayer.callAsFunction`, gated on
`x.dims(1, 1, 2048)` so prefill is untouched. 40 decoder layers ⇒
`N_extra = 40·K`.

Design: 2 blocks, palindromic arm order within each block so session drift
cancels, one discarded primer run, 400 decode steps/run, first 16 dropped as
warmup, **run median** as the unit of replication, **n = 4 per rung**, 41 runs
total (~30 min). **All 41 runs report `teacher-forced greedy tokens: 0
divergences (all match)`.**

### WIDE — 4 KiB read + 4 KiB write per injected dispatch

| K | N_extra | n | median µs/step | sd | vs K=0 |
| --- | --- | --- | --- | --- | --- |
| 0 | 0 | 4 | 8234.1 | 15.2 | 0.0 |
| 8 | 320 | 4 | 8692.4 | 23.0 | 458.3 |
| 16 | 640 | 4 | 9139.9 | 17.6 | 905.8 |
| 32 | 1280 | 4 | 10044.2 | 23.3 | 1810.1 |
| 64 | 2560 | 4 | 11855.9 | 20.1 | 3621.8 |

### TINY — 4 B per injected dispatch, identical chain structure

| K | N_extra | n | median µs/step | sd | vs K=0 |
| --- | --- | --- | --- | --- | --- |
| 0 | 0 | 4 | 8300.6 | 16.2 | 0.0 |
| 8 | 320 | 4 | 8609.8 | 48.7 | 309.2 |
| 16 | 640 | 4 | 8724.6 | 19.5 | 424.0 |
| 32 | 1280 | 4 | 8686.0 | 20.6 | 385.4 |
| 64 | 2560 | 4 | 8875.0 | 42.3 | 574.4 |

---

## 3. Fitted slopes, intercepts, intervals, linearity

Within-block-centred OLS (block = session dir × block index), so between-session
drift cannot enter the slope.

| arm | slope (µs/dispatch) | 95 % CI | intercept (µs/step) |
| --- | --- | --- | --- |
| **wide (on-chain, headline)** | **1.4140 ± 0.0093** | **[1.4047, 1.4233]** | 8242.0 ± 12.9 |
| **tiny (work-independent)** | **0.1716 ± 0.0617** | **[0.1098, 0.2333]** | 8484.0 ± 82.1 |
| **difference (traffic term)** | **1.2425 ± 0.0624** | — | ratio **8.24×** |

**Wide is linear.** Adjacent secants are 1.4321, 1.3984, 1.4130, 1.4154 — a
±1.2 % spread around the fit across an 8× range of N. The fitted intercept
8242.0 ± 12.9 recovers the independently measured zero point 8234.1 ± 15.2 to
within 8 µs on an 8234 µs step (0.1 %). There is **no knee and no slack pool**.

**Tiny is not a line — it is a step plus a very shallow slope.** Secants 0.9662,
0.3589, −0.0603, 0.1477, and the K=16→32 cell is *non-monotonic*. Refitting each
arm on the K>0 rungs only (K=0 runs a different code path: the injected chain is
empty) separates the step from the slope:

| arm | K>0 slope (µs/dispatch) | intercept offset vs the measured K=0 cell |
| --- | --- | --- |
| wide | **1.4130 ± 0.0125** | **+9.7 µs** (0.1 % of the step) |
| tiny | **0.0989 ± 0.0318** | **+315.3 µs** |

The wide arm has *no* step: its K=0 rung lies on the same line as the rest, so
the ladder harness itself introduces no regime artifact. The tiny arm has a
**one-time +315 µs step** that appears as soon as the chain is non-empty and
then does **not grow with K** — so by construction it cannot be a per-dispatch
cost. Once it is removed, the work-independent slope drops to
**0.0989 ± 0.0318 µs/dispatch**, which lands on top of the programme's
independent barrier-free estimate of 0.1231 ± 0.0481 (`CURRENT_RESEARCH_STATE`)
without either measurement being tuned to the other.

Five independent estimators of the work-independent cost:

| estimator | µs/dispatch |
| --- | --- |
| all-points within-block fit | 0.1716 ± 0.0617 |
| K>0 fit (step removed) | 0.0989 ± 0.0318 |
| constant-CB secant K=8→16 (§7) | 0.3589 |
| top-half secant K=16→64 | 0.0783 |
| census GPU-union marginal, t0→t64 (§7) | 0.205 |

**Every one is below 0.5 µs**; the spread 0.08–0.36 is the honest uncertainty.
The verdict does not depend on which estimator is chosen, so I do not need to
argue for one.

### Why this contrast is the right instrument

Verified in `Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/device.cpp`:
`maybeInsertBarrier()` runs before **every** `dispatch_threadgroups` (~line 443)
and inserts a global `memoryBarrier(BarrierScopeBuffers)` whenever the dispatch
reads a buffer written since the last barrier (`set_input_array` sets
`needs_barrier_`, ~lines 383–396). Both ladder arms are data-dependent chains,
so **both carry identical dispatch counts and identical barrier counts.** The
only thing that varies is bytes moved. The difference therefore isolates
traffic, and the tiny arm isolates the work-independent residue.

That yields a corrected component model. The programme's previous model treated
the barrier as a constant ~1.30 µs. It is not constant — it is a *drain*, and
it costs what it has to wait for:

| component | value | refunded by a fusion? |
| --- | --- | --- |
| `c_issue` (work-independent) | **0.17 µs** | always |
| `c_drain` (wait for producer's traffic to land) | **1.24 µs per 4 KiB** | **only if the fused kernel keeps the intermediate in registers/threadgroup memory** |
| `c_CB,serialized` (a command buffer that forces a commit/wait, as in `SPLIT=1`) | ≈1.7 µs | only if the fusion removes an eval boundary |
| `c_CB,packed` (an extra command buffer inside the normal pipelined stream) | **≤ 0.14 µs — measured, §7** | nothing to refund |

**Elision control.** A saturating arm is exactly what elision would look like,
so this had to be excluded before the tiny slope could be believed. Profiled
census at K=64 wide: **2966 dispatches/step vs 406 at K=0 — a difference of
2560, exactly 40 × 64**, with `vs_Multiplybfloat16` present in the CB signature
table. Nothing is folded away. (Full per-rung census in §7.)

---

## 4. Reconciliation with the 3.00 µs and 4.70 µs per-call floors

This is the part that dissolves H's motivating observation.

Those floors come from a **`SPLIT=1` one-dispatch-per-command-buffer** probe
(`research/nezuko-pr158-decode-dead-time.md:1221-1222`), whose raw spans are
`rmsbfloat16` **3.48 µs** and router **5.21 µs**; the published 3.00/4.70 are
those spans minus a 0.480 µs/dispatch CB de-inflation. Decompose the raw span
with the component model:

```
solo dispatch in its own CB  =  c_CB + c_drain + c_issue
                             ≈  1.7  +  1.24   +  0.17   =  3.11 µs
```

- That reproduces PR #196's independent single-threadgroup floor
  `a + φ = 1.661 + 1.469 = ` **3.130 µs** to within 0.6 %.
- It accounts for **3.11 of `rmsbfloat16`'s 3.48 µs span**, leaving only ~0.37 µs
  of actual arithmetic — appropriate for an RMSNorm over one 4 KiB row.
- The router's 5.21 µs span leaves ~2.10 µs of real work, appropriate for a
  top-8 selection over 256 experts.

**The two "floors" therefore look alike because they are dominated by the same
structural overhead, not because there is a launch tax.** And critically, the
`c_CB` term in them is a **SPLIT-mode artifact**: the real decode stream packs
406 dispatches into 45 command buffers (0.111 CB/dispatch), so the in-stream
marginal cost of a 4 KiB-touching decode op is **not** 3.00 or 3.48 µs — it is
`c_issue + c_drain` = **1.41 µs, precisely the ladder slope**.

H's premise was that two kernels with wildly different arithmetic priced alike
must be paying a launch tax. They price alike because ~90 % of a SPLIT-mode
per-call measurement is command-buffer and DRAM-drain structure that the packed
decode stream does not pay per call. Answering the prereg's decisive test:
**`slope_wide` (1.414) ≪ 3.00, so most of the floor is the kernel's own work
and command buffer — not launch.**

Against the glue pool measured on this host (`research/nezuko-a2-roofline.txt`,
641 µs/step total: `residual_rms_router` 305.1, `router_top8_ordinal_table_norm`
185.7, `rmsbfloat16` 124.6, remainder 25.5): that 641 µs is **not** a recoverable
pool. It is overwhelmingly the traffic those kernels must move; a survivor
kernel inherits the reads and writes of the kernel it absorbs unless the
intermediate genuinely stays resident.

---

## 5. Resolution of the `cc6ddc1` negative

`cc6ddc1` (solver `a-github-name`, officialScore 2.6165035) built
`DARKBLOOM_MERGED_ROUTED_SHARED_GATEUP` — a one-dispatch merged routed+shared
gate/up kernel, grid 9×256 threadgroups of 64 — deleting **39 dispatch
boundaries**, and then removed it because its isolated M5 price was not positive.
Maple independently built and removed the same thing (orphans at
`LagunaRuntimeModel.swift:8504-8520`, `:10233`) and measured it directly on M4:
**ΔD = 39 dispatches removed → −0.9 µs, sd 29.7, sem 12.1, t = −0.07, p ≈ 0.94**
(`research/maple-fern-router-top8-fusion.md:267`, with a fault-injection control
at `:340-349`).

I pre-committed to resolving this as (a), (b), or (c). **The answer is (c), and
it is specific:**

> **(c) The fusion deleted the cheap axis, not the expensive one.** A merged
> gate/up fold removes 40 dispatches but only **1** barrier — the programme's own
> measured 39 : 1 asymmetry (`CURRENT_RESEARCH_STATE.md:3272-3274`). So it could
> only ever refund `c_issue`, never `c_drain`. It was implicitly priced as if it
> deleted 39 *dependent pairs*; it deleted 39 *barrier-free issues*.

The arithmetic, using this arm's measured slopes:

| pricing | predicted refund | z against the measured sd of 29.7 | visible? |
| --- | --- | --- | --- |
| as 39 dependent pairs @ 1.4140 µs | 55.1 µs/step | 1.86 | probably |
| **as 39 barrier-free issues @ 0.1716 µs** | **6.7 µs/step (0.10 % score)** | **0.23** | **no** |
| under H @ 2.5 µs | 97.5 µs/step | 3.28 | clearly |

The measured result (−0.9 µs, p ≈ 0.94) is exactly what the 0.17 µs row
predicts and is flatly inconsistent with H. **So `cc6ddc1`'s null is itself
independent evidence against H, once the slope is known.**

Note what is *not* required: **no occupancy or register-pressure penalty needs to
be invoked.** Explanation (b) is unnecessary — the null is fully accounted for by
the deletion landing on the cheap axis. Explanation (a) is also wrong as stated:
the per-dispatch cost is *not* uniformly small, because the on-chain cost is a
real and precisely measured 1.41 µs. It is small *for the kind of boundary that
fusion deleted*.

This also independently replicates the programme's barrier-free dispatch
estimate **0.1231 ± 0.0481 µs** (`CURRENT_RESEARCH_STATE.md:395-402`): my tiny
arm gives **0.1716 ± 0.0617**, agreeing within error. Two different instruments,
same number. It further explains *why* those agree: a barrier with nothing to
drain is nearly free, so "barrier-free dispatch" and "dependent dispatch moving
4 bytes" are the same physical quantity.

---

## 6. The mandated conclusion (middle row): the realistic ceiling

The middle row requires `slope × deletable boundaries`, the score-equivalent,
and whether it clears the ~80 µs/step decode bar. The answer depends entirely on
**which slope applies**, and that is the actionable finding:

| campaign type | slope | D = 40 | D = 120 | D = 240 |
| --- | --- | --- | --- | --- |
| **count-only fusion** (deletes issues, intermediate still round-trips DRAM) | 0.1716 µs | 6.9 µs<br>0.10 % | 20.6 µs<br>0.31 % | 41.2 µs<br>0.63 % |
| **true fusion** (also keeps the 4 KiB intermediate resident) | 1.4140 µs | 56.6 µs<br>0.86 % | 169.7 µs<br>2.59 % | 339.4 µs<br>5.19 % |

Score conversion is the prereg-fixed **0.015280 % per µs/step decode**.

**Sensitivity to the estimator.** The count-only row uses the pooled 0.1716 µs.
Because §3 leaves a 0.08–0.36 µs range, here is the D required to reach the
~80 µs/step bar at each end, against a decode step that issues **406 dispatches
in total**:

| work-independent estimator | D needed for 80 µs/step | as a share of the whole dispatch budget |
| --- | --- | --- |
| 0.0989 µs (step-removed fit) | 809 | 199 % |
| 0.1716 µs (pooled fit) | 466 | 115 % |
| **0.3589 µs (most conservative)** | **223** | **55 %** |

**Verdict:**

- **Count-only dispatch reduction does NOT clear the ~80 µs/step bar at any
  plausible D.** At the pooled and step-removed estimators the required D
  *exceeds the entire dispatch budget* and is arithmetically impossible. Even
  taking the single most conservative estimator, it requires deleting **more
  than half of every dispatch the decode step issues** — while the largest
  fusion the programme has actually built, `cc6ddc1`, deleted **40**, and nulled
  out. **The dispatch-count-reduction family is closed on its own terms** — not
  because the cost is unmeasurable, but because it is measured, small, and the
  required D is out of reach at every estimator in the range.
- **Round-trip elimination does clear the bar**, and is the only version of
  "fusion" worth pursuing. It needs ~57 deleted *dependent, register-resident*
  boundaries to reach 80 µs/step.

So the family should be **re-scoped, not merely closed**: stop counting
dispatches, start counting **DRAM round-trips of the 4 KiB hidden row**. A
candidate fusion is worth building only if it can state how many round-trips it
removes; if the answer is zero, its ceiling is 0.17 µs each and it will null out
exactly like `cc6ddc1`.

The upper cells of the "true fusion" column should be read with suspicion: the
survivor kernel inherits the absorbed kernel's reads and writes, so D = 240
register-resident fusions is not physically available in this decode graph.
A defensible whole-campaign expectation is **~1–3 % of the 8234 µs step**.

### M5 transfer (advisor's `25b0b722` anchor)

The advisor's control receipt `25b0b722` establishes this exact base content
measures officialScore **2.55158458026643** on M5 with decode_speedup
**2.804381**, both floors passed, `max_abs_diff = 0`. Distinct from our best-ever
`97a5090c` @ **2.58882784082067** and the leaderboard bar `cc6ddc1` @
**2.6165035**.

M5's independently measured paired per-dispatch cost is **2.088 ± 0.165 µs**
(`research/tanjiro-pr34-r2-result.md`), versus my M4 on-chain **1.414 µs** — a
ratio of 1.48×, the same order and the same sign, which is a consistency check
on the mechanism. Two honest caveats: (i) that M5 estimate is
**non-identifiable** — `(c=2.088, knee=0)` and `(c=8.35, knee=300)` fit equally
well (`:256-260`), so derived savings are **upper bounds**; and (ii) the
0.015280 %/µs conversion is already the programme's calibrated M4-µs → M5-score
bridge, so multiplying by 1.48 *as well* would double-count. I have not done so;
the table above is the M4 number passed through the fixed conversion.

One M5-specific note that *strengthens* the conclusion: M5 has essentially no
slack pool (the M4 knee was falsified there at 34.8 σ). My ladder finds no knee
on M4 either. So the "absorption" escape hatch — that removals near the current
operating point refund less than the asymptotic slope — is unavailable on both
machines, and the slopes above are directly applicable rather than optimistic.

---

## 7. Profiled census (elision and CB-repacking controls)

`DARKBLOOM_GPU_PROFILE=1`, 40 steps, all ten rungs, one run each, 0 divergences
everywhere. `busy_sum` adds up each command buffer's GPU interval; `busy_union`
merges overlapping intervals, so `sum − union` is GPU-side **concurrency**.

| arm | K | dispatches | CBs | wall ms | busy_sum | busy_union | sum−union | gap ms |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| w0  | 0  | 406  | **45** | 8.170  | 7.922  | 7.922  | 0.000 | 0.248 |
| w8  | 8  | 726  | **45** | 8.628  | 8.370  | 8.370  | 0.000 | 0.258 |
| w16 | 16 | 1046 | **45** | 9.093  | 8.843  | 8.843  | 0.000 | 0.249 |
| w32 | 32 | 1686 | **45** | 9.977  | 9.723  | 9.723  | 0.000 | 0.254 |
| w64 | 64 | 2966 | 76     | 11.818 | 11.476 | 11.476 | 0.000 | 0.343 |
| t0  | 0  | 446  | **45** | 8.227  | 7.975  | 7.975  | 0.000 | 0.252 |
| t8  | 8  | 766  | **45** | 8.553  | 8.287  | 8.287  | 0.000 | 0.266 |
| t16 | 16 | 1086 | **45** | 8.658  | 8.390  | 8.390  | 0.000 | 0.268 |
| t32 | 32 | 1726 | 50     | 8.636  | 8.789  | 8.355  | **0.434** | 0.281 |
| t64 | 64 | 3006 | 66     | 8.946  | 9.465  | 8.499  | **0.966** | 0.447 |

**No elision.** Dispatch counts are exactly `406 + 40K` (wide) and `446 + 40K`
(tiny) at every rung — the arithmetic closes to the unit. The tiny arm's
constant `+40` is its unconditional `x + t` add, present at every K including
K=0, so it cancels out of the slope; it is also the reason the tiny K=0 cell
sits 66 µs above the wide K=0 cell.

**No CB-repacking confound.** The command-buffer count is **pinned at exactly 45
while dispatches grow 4.2×** (w0 → w32, 406 → 1686). Over that constant-CB
span the wall-clock cost is `(9.977 − 8.170)/1280 = 1.412 µs/dispatch`, matching
the full-ladder fit of 1.4130 ± 0.0125. The slope is therefore a property of
dispatches, not of command buffers.

**The cost is inside GPU busy time, not CPU encode.** `gap` (wall minus GPU
union) is flat at 0.25–0.27 ms across an 8× dispatch range while `busy_union`
absorbs the entire increase. Marginal cost recomputed from GPU-internal
timestamps alone, independent of the wall clock: wide `(11.476 − 7.922)/2560 =
**1.388**`, tiny `(8.499 − 7.975)/2560 = **0.205** µs/dispatch. Two different
clocks, same two numbers.

**Extra command buffers in the packed stream are nearly free.** K=32→64 wide
adds 31 CBs, yet the secant moves by only +0.003 µs/dispatch, bounding the
marginal packed-CB cost at **≤ 0.14 µs**. This is what kills the
"45 CBs × 1.7 µs ⇒ 76 µs/step is recoverable" mirage: the 1.7 µs figure belongs
to a `SPLIT=1` commit-and-wait boundary, not to a CB inside the pipelined
stream.

**Why the tiny arm saturates — measured, not assumed.** In *every* wide rung
`busy_sum == busy_union` to the microsecond, including w64 with 76 CBs: wide
work never overlaps. In tiny at K=32 and K=64 the GPU runs 0.43 ms and 0.97 ms
of command-buffer time *concurrently*. Tiny dispatches do not occupy the machine
enough to serialize it, so their busy time is partly hidden. A genuinely fixed,
work-independent per-dispatch cost of 2–3 µs could not behave this way — it
would have to serialize by definition. This is direct timestamp-level evidence
against H, obtained from a different instrument than the ladder.

---

## 8. Predictions I got wrong, and what else could still be wrong

Recorded plainly because the prereg is worthless otherwise.

1. **Ratio.** I predicted `slope_wide / slope_tiny ≈ 1.5–2×`. It is **8.24×**. I
   substantially underestimated how completely traffic dominates. This miss is
   the most informative single number in the arm.
2. **Shape.** I predicted a soft absorption region at small N following
   `dT = max(0, N·c − slack)` with an M4 knee near 1209 extra dispatches. The
   wide ladder is **linear from N = 320 to N = 2560** with ±1.2 % secant spread —
   it crosses that predicted knee with no change of slope whatsoever. **The M4
   slack/knee model does not describe on-chain dependent dispatches.** (The
   *tiny* arm is non-linear, but saturating in the opposite direction to slack.)
3. **Slope value.** 1.4140 vs a predicted 1.0 — inside my interval, but in its
   upper half, and startlingly close to the programme's existing dependent-pair
   deletion refund of **1.4234 ± 0.0256 µs**. Agreement to 0.7 % between an
   injection experiment and a deletion experiment is the strongest cross-check
   in this result.
4. **I assumed the control arm would be a line.** It is not: the tiny arm is a
   +315 µs step plus a ~0.10 µs slope, and I only found the step because the
   K=16→32 secant came out *negative* and forced me to refit. Had I reported the
   pooled 0.1716 as "the" number without decomposing it, the intercept bias
   (+183 µs against the measured zero point) would have been an unexplained loose
   end. The wide arm's K>0 refit (+9.7 µs offset) is what proves the step belongs
   to the tiny code path and not to the harness.

Standing risks I am **not** claiming to have eliminated:

- **The work-independent constant is a range, not a point.** Five estimators
  give 0.08–0.36 µs (§3). I have not identified which is most nearly unbiased,
  and I do not need to: the decision row and the §6 verdict hold across the
  whole range. But anyone quoting a single digit from this arm should quote the
  range with it.
- **M4, not M5.** Everything here is one host. The mechanism is architectural
  (MLX's barrier insertion is host-independent source), but the constants are not.
- **The no-op is a floor.** An injected `x * 1.0` shares a PSO, donates its
  buffer, reads a resident constant and runs one wave. Real glue kernels cost
  *at least* the measured slope, so the ceilings above are conservative on that
  axis and optimistic on the round-trip axis.
- **Profiling perturbs.** Profiled 1.461 vs unprofiled 1.414 µs/dispatch (−3 %).
  I quote the unprofiled ladder; the census is used only for counts.
- **`busy_sum == busy_union` — I withdraw my earlier caveat.** I had assumed
  this equality might be tautological in the profiler and refused to cite it.
  The census falsifies that: t32 and t64 report `sum − union` of 0.434 ms and
  0.966 ms (§7). The instrument *can* report overlap, so the exact equality in
  all five wide rungs is a real measurement of non-overlap, and I now cite it.
  What it still cannot tell me is *why* tiny work overlaps — occupancy is my
  reading, but I have not isolated it.
- **CPU encode headroom.** The base step has a 207 µs GPU gap (2.6 %). The wide
  ladder's linearity implies the GPU stayed the bottleneck throughout, but a
  genuinely barrier-free variant could become CPU-encode-bound, which this
  instrument would not see.
- **The 641 µs glue pool is not a budget.** I explicitly reject the reading that
  it is recoverable; survivors inherit the work.

---

## 9. Correctness

**No emitted behaviour changes.** Both arms are exact identities in BF16
(`x * 1.0`, `x + 0.0`, with BF16 `[1]` constants so the chain is never promoted
to FP32), gated to decode-shaped tensors, and armed only by an environment
variable that is unset in every shipped configuration.

**All 41 ladder runs plus all census runs report
`teacher-forced greedy tokens: 0 divergences (all match)`**, against the golden
seed `correctness_prompts/public_longcopy_gate_english_512_256.json`.

Per the evidence contract, the equivalence oracle and the 64-step tripwire are
required *if emitted behaviour changes*. It does not: **the submitted diff for
this PR contains no `editablePaths` change at all** (§10), so there is no
runtime to re-verify. The measured configuration's correctness is carried by the
41 + 10 zero-divergence teacher-forced runs above.

---

## 10. Scope discipline

Per prereg §6 and Rule 11, the instrument is **reverted** from `Sources/` and
`Vendor/` and ships as an unapplied patch at
`research/nezuko-r85-ladder.patch` (8941 B), reproducible with:

```bash
git apply research/nezuko-r85-ladder.patch
swift build -c release --force-resolved-versions \
  --scratch-path .build-worker --product mlxfast-runtime-worker
bash research/nezuko_r85_ladder.sh /tmp/r85/ladA 2 400   # 41 runs, ~30 min
bash research/nezuko_r85_census.sh  /tmp/r85/census       # 10 runs, ~7 min
python3 research/nezuko_r85_ladder_fit.py /tmp/r85/ladA
R85_CENSUS_DIR=/tmp/r85/census \
  python3 research/nezuko_r85_ladder_wandb.py /tmp/r85/ladA
```

**W&B:** run `7ep17pqq` —
<https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/7ep17pqq>
(`ladder_table`, `census_table`, every fitted scalar, and an artifact holding
all 41 raw per-step dumps plus the 10 census logs).

**Zero `editablePaths` bytes changed. Zero submission budget consumed.** All
added files are under `research/`, outside the submitted surface. Verified after
the revert with `senpai/check-editable-budget.sh $BASE_SHA`:

```text
editable budget OK: current=2857088/3000000 bytes headroom=142912
growth=0/262144 files=140 (base=140)
```

and `git diff $BASE_SHA -- Sources Vendor` is empty.

**No fusion was implemented**, per the prereg's unconditional commitment —
including under the middle row, which invites a proposal but not a build.
**No official submission was spent.** A ladder measurement is not a candidate,
and this base (2.5516) is below both our best-ever (2.5888) and the bar (2.6165).

---

## 11. Suggested follow-ups (not implemented)

1. **Re-scope the family, don't just close it.** Add to the closed-families list:
   *"dispatch-count reduction that does not eliminate a DRAM round-trip is worth
   0.17 µs per boundary and cannot clear the decode bar — 466 deletions would be
   required from a 406-dispatch budget."* Keep round-trip elimination open.
2. **A round-trip census.** The natural successor to this arm: count how many
   times the 4 KiB hidden row makes a DRAM round-trip per decode step, and which
   adjacent pairs could keep it resident. That directly enumerates the only lever
   this result leaves standing, and it is a static analysis plus one profiled run.
3. **Do *not* chase the command-buffer count.** I nearly proposed this arm — 45
   CBs/step × the 1.7 µs SPLIT-mode figure looks like ~76 µs/step of recoverable
   structure, right at the decode bar. **This arm's own census refutes it before
   anyone spends a run:** the K=32→64 segment adds 31 command buffers and the
   secant moves by 0.003 µs/dispatch, bounding the marginal packed-stream CB cost
   at **≤0.14 µs**. Extra command buffers in the normal pipelined stream are
   essentially free; only a CB that forces a commit/wait costs 1.7 µs. Recording
   this so the 76 µs/step mirage is not re-derived.
4. **Retire the 3.00/4.70 µs per-call floor numbers** from the programme's
   working vocabulary, or re-label them "SPLIT-mode spans". They have motivated at
   least two arms (this one and H's origin) on the strength of an artifact.
