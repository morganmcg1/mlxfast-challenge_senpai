# R118-A — RESULT

Target: `laguna_shared_nvfp4_swiglu_qmv_rows1_halved_bf16_v1`
(39 calls/step, 288.0 us/step profiled busy, 7.39 us/call in situ vs 5.637 us/call
standalone-cold, i.e. the ~68 us/step "excess" the charge asked me to adjudicate).

Verdict: **TERMINAL NEGATIVE — do not land.** The negative control passes, the rig
is clean, and the excess is *not* addressable from inside the kernel.

W&B run (every number below is in its summary, read out of the analyser JSON, not
retyped): <https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/9siru9ak>

Three numbers carry it:

1. **Deleting three quarters of the kernel's reads is worth at most
   +56.7 us/step** (95 % upper bound on the paired block-median saving, the worse
   of two mirrored orders; medians +38.7 / +51.9). Every published landing bar —
   68.7, 67.4, 61.2, 60.0 — is above that, though the margin against the loosest
   one is only 3.3 us/step and I say so in §3 rather than rounding it away.
2. **The dose curve has saturated.** The 1.5x dose buys −11.0 us/step in order A
   and +2.6 in order B against the 1.0x dose, where linearity would demand
   +24.8. The same instrument, same host, same session, sees the routed family
   respond **linearly** at 2.5162 us per MB/step over an 8x larger byte range.
3. **The excess is fixed cost, and the charge's own 68 us/step is a busy
   number.** SPLIT=1 attribution splits the target's 7.430 us/call into
   1.210 us per K block and **2.590 us/call that does not scale with bytes**
   (34.9 %). The in-situ excess reproduces at 69.9 us/step of *busy*, which at
   the tau I measured for this same family from this same arm (0.367) is
   **25.6 us/step of wall** — below every bar before any arm is considered, and
   the same 25-30 us/step that alphonse priced this target at independently.

The one route this instrument cannot see is co-scheduling; that blind spot is
stated, sized, and left open in `CO-SCHEDULING-BLIND-SPOT.md`.

---

## 0. Two answers the advisor asked for out of band

These are the answers to the two questions that were attached to this assignment
but are not about R118-A itself. They are restated here because
`submit_experiment_result` is the only channel I have.

**D0 — is the branch-head A2 the same binary as receipt `be958bcd-eac1-4a0c-92e6-d41f699b2ec7`?**
**Yes. Byte-for-byte the same binary, same tuple `(64,64,256,2,2)`.**
A2 is therefore already spent: drawing it again buys a second copy of a receipt we
own. **Fire A1.** Full derivation in `D0-A2-IS-THE-SAME-BINARY.md`; the
consequence is written up as `N-FUSED-NAX-NARROW-BN-BELOW-BAR`.

**D0b — is prefill adjudicable at all?**
**A1-A4 can be closed; prefill cannot.** The NAX-gated code in A1-A4 never
executes on this host (`is_nax_available()` is false on `applegpu_g16s`), so those
are *deterministically* unmeasurable, not merely noisy. Prefill as a whole is a
different matter: it is locally adjudicable to ~0.1 % with a paired single-binary
contrast at n=16, and the only region worth spending a draw on is the ~27.88 ms
(28.5 %) of prefill not attributed to dense GEMM. Proposed clause for the closure
rule: *"...and the edited code must execute on the measuring host."*
Full argument in `D0b-IS-PREFILL-ADJUDICABLE.md`.

---

## 1. What was measured

One binary, switched by `DARKBLOOM_SHARED_QMV_ARM`. At the default arm (`ship`)
the MSL text and the kernel name are byte-identical to the shipped kernel; the
instrument cannot perturb the shipped path. `lagunaPackedPrefillScaleView` was
not touched.

| arm | what it is | weight bytes removed |
|---|---|---|
| `ship` | shipped kernel, byte-identical | 0 |
| `ctl` | **negative control**: identical MSL, name suffix `_r118ctl` only | 0 |
| `d2` | dose 2 on the shared family | 21.72 MB/step |
| `d1` | dose 1 on the shared family | 32.58 MB/step (75 % of its traffic) |
| `rctl`/`rd2`/`rd1` | same three on the routed family (positive control) | 0 / 174 / 261 MB/step, an 8x larger range |

Design (pre-registered in `PREREG.md` before any of this data existed, method in
`METHOD.md`): mirrored orders, both reported **separately**, block-bootstrap CI on
the **median** paired saving with the mean reported alongside, byte-identical
negative control with a stop rule, raw samples dumped to CSV, and a bimodality
check that would have condemned the rig.

### As-run vs pre-registered, with the deviations named

| item | pre-registered (`PREREG.md`, 04:08:02Z, `a9b41336`) | as run | note |
|---|---|---|---|
| blocks per shared order | 6 | **10** | fixed in `run-r118a.sh` at `b0d6bec0`, **04:12:49Z — 7 s before the first run at 04:12:56Z**, so the block count was frozen in code before any data existed. Not optional stopping. `METHOD.md` (04:31:40Z) merely records it. |
| order construction | Latin-square-ish randomised blocks | 10 independent random permutations of the 4 arms (seed 118), and **order B is the exact time-reversal of order A** | the mean run index of every arm over the pair is identical (19.5), so monotone session drift cancels across the pair |
| steps per run | 400 | **160** | 8 discarded as warm-up ⇒ **1520 measured steps/arm/order**, ~3x the >=512 raw-sample floor |
| positive control | 6 blocks, routed family | 6 blocks of {`ship`,`rctl`,`rd2`,`rd1`}, run **between** the two shared orders | this "control block" is named in `run-r118a.sh` but was not named in `PREREG.md`; its position between the orders is deliberate (it dates the rig at the campaign midpoint) |
| "mirrored ABBA" | — | the design is a **mirrored randomised-block** design, not a literal ABBA | earlier drafts of this file said ABBA; that was loose language and is corrected here |
| ">=64 measured cycles per order" | asked by the charge | **10 blocks/order, 20 across the pair** | **this is a shortfall against a literal reading and I am not going to paper over it.** A "cycle" here is one block = one run of each arm, and one run costs a 41 s model load for 1.3 s of decode, so 64 blocks/order is 3 h/order — outside the window. What I bought instead is depth: 1520 measured steps per arm per order. The block-level analysis is therefore backed by an exact sign test on the 10 paired block differences as well as the bootstrap (§2), and the effect the control has to resolve is ~450-680 µs/step against a block-to-block spread of a few µs. |

One more as-run deviation, recorded in `HOST-HYGIENE.md` rather than buried: the
supervised job running the campaign hit its wall-clock deadline at **05:16:05Z,
mid-run-23 of order B**. Order A (40/40) and the control block (24/24) were
already complete. Run 23 wrote no `.steps` file, so no partial run entered the
data, and `resume-orderB.sh` continued the **same** `ORDER_B` string from position
23 about ten minutes later. Nothing was re-drawn; the cost is a ten-minute gap
between order B's runs 22 and 23, which straddles one block (block 6: `ship`,
`d2` before the gap, `d1`, `ctl` after).

Every number below comes from the as-run design, not the pre-registered one.

---

## 2. Headline numbers

Paired saving vs `ship`, positive = arm is faster, ms/step, 95 % CI from a block
bootstrap on the median (20 000 resamples). **Both mirrored orders separately:**

### order A — shared family, 10 blocks, 1520 measured steps/arm

| arm | what it deletes | median saving (ms/step) | mean saving | 95 % CI | excludes 0? |
|---|---|---|---|---|---|
| `ctl` | nothing (byte-identical, renamed) | +0.0038 | +0.0032 | [−0.004532, +0.007646] | **no — passes** |
| `d1` | 3/4 of the interior (dose 1) | **+0.038656** | +0.031998 | [+0.020302, **+0.041198**] | yes |
| `d2` | 1/2 of the interior (dose 2) | +0.049687 | +0.041881 | [+0.035177, +0.057167] | yes |

per-arm pooled per-step sd (ms, over all measured steps; `analyze-dose.py:214` uses `pstdev`): `ship` 0.04427, `ctl` 0.04540, `d2` 0.07229, `d1` 0.14855.

### order B (exact time-reversal of order A) — 10 blocks, 1520 measured steps/arm

| arm | median saving (ms/step) | mean saving | 95 % CI | excludes 0? |
|---|---|---|---|---|
| `ctl` | +0.000948 | +0.000927 | [−0.005896, +0.007896] | **no — passes** |
| `d1` | **+0.051917** | +0.037483 | [+0.024250, **+0.056698**] | yes |
| `d2` | +0.049302 | +0.042471 | [+0.044542, +0.057479] | yes |

per-arm pooled per-step sd (ms, over all measured steps; `analyze-dose.py:214` uses `pstdev`): `ship` 0.04904, `ctl` 0.03736, `d2` 0.06337, `d1` 0.15092.

### control block — routed family, 6 blocks, run between the two shared orders

| arm | median saving (ms/step) | mean saving | 95 % CI | exact sign test (6 blocks) |
|---|---|---|---|---|
| `rctl` | +0.001813 | +0.015941 | [−0.003052, +0.049063] | 4/6 positive, +2.00 us/step, **p = 0.6875** |
| `rd2` | +0.443166 | +0.432920 | [+0.400115, +0.455479] | 6/6, +442.50 us/step, **p = 0.0312** |
| `rd1` | **+0.654500** | +0.655021 | [+0.645052, +0.665511] | 6/6, +654.50 us/step, **p = 0.0312** |

per-arm pooled per-step sd (ms, over all measured steps; `analyze-dose.py:214` uses `pstdev`): `ship` 0.07261, `rctl` 0.05873, `rd2` 0.05631, `rd1` 0.04137.

p = 0.0312 is the smallest two-sided p an exact sign test on 6 pairs can return
(2 x 2^-6), i.e. both routed doses are as significant as this design permits.
The sign test is run on `confound-check.py`, which reads the per-run log medians
over all 160 steps rather than the warmup-trimmed CSV the bootstrap uses; the two
statistics therefore differ in the third significant figure (`rd1` +654.50 vs
+0.654500 ms is a coincidence of rounding, not the same arithmetic). See §8.

**Negative control: it passes, in all three blocks, on both estimators.** `ctl` is
the same MSL text as `ship` with
`_r118ctl` appended to the kernel name, so its true saving is exactly zero. Its
95 % interval is reported per order above; the criterion is that **each order's
`ctl` interval contains zero** (one interval per order, not per block — a block
holds one run per arm and supports no interval of its own). Per the pre-registered
stop rule, had either excluded zero I would have stopped and reported the rig
instead of the result. The routed byte-identical arm `rctl` is a second, independent
instance of the same check in the control block.

**Positive control, and how it failed its pre-registered band.** `PREREG.md:109-112`
set P0 at *"rd2 saves 700-900 us/step and rd1 saves 1050-1350 us/step"*, and said
that if it did not hold "nothing else in the report counts". **It did not hold.**
The shakedown measured −456 / −678 us/step, 0.60x the band, and that miss is
recorded in `SMOKE.md:30-46` at the time rather than quietly retuned. What the
prereg got wrong was the *level*, not the *shape*: it priced the routed doses at a
DRAM-only streaming rate and ignored that part of the removed traffic is
cache-resident. The two registered outcomes were "in band ⇒ valid" and "null ⇒
blind"; the observed outcome — **large, highly significant, and linear in bytes
removed, at 0.60x the predicted slope** — was a third one, and I am adjudicating it
post hoc. My reason for calling the rig valid anyway is that the *inference the
rig has to support is a null on the shared family*, and for that the only thing
P0 must establish is that the ruler is not blind to bytes. A 456 us/step response
that is linear in dose over an 8x range establishes exactly that, whatever its
absolute slope. If you disagree, the honest reading is "P0 failed as written; the
shared-family null is supported by a recalibrated positive control", and the
verdict is unchanged because a *smaller*-than-expected byte response makes the
shared family's flatness easier, not harder, to explain away — which is why I also
report the routed slope and its interval rather than only its sign.

**No arm is bimodal** in any block; histograms are in the analyser output and the
raw per-step samples are in `raw-steps-<label>.csv`.

### Both estimators, honestly

Pooled sample contrast (all measured steps of an arm against all measured steps
of `ship`, i.e. unpaired at the block level), us/step:

| arm | order A d-median | order A d-mean | order B d-median | order B d-mean |
|---|---|---|---|---|
| `ctl` | +2.75 | +2.52 | +0.62 | +3.31 |
| `d1` | +36.29 | **−18.31** | +31.08 | **−13.99** |
| `d2` | +46.21 | +39.34 | +46.85 | +44.03 |
| `rctl` | — | — | +3.35 | +17.24 (control block) |
| `rd2` | — | — | +439.06 | +437.87 (control block) |
| `rd1` | — | — | +653.40 | +660.63 (control block) |

The two `d1` d-means are **negative in both mirrored orders** while every median
is positive and every block-bootstrap interval excludes zero. That is not a
sign flip in the effect; it is the signature of a heavy right tail in `d1`'s
step-time distribution (per-step sd 0.149/0.151 ms against `ship`'s
0.044/0.049 — three times the spread of any other arm), which is exactly what
the extra 118 re-routed steps per run would produce. It is reported here rather
than buried because a reader who prefers means should see that on this arm the
mean is dominated by the tail the confound creates, and should read the
divergence-free subset below instead.

### The confound this creates, and why it does not rescue the target

A dose arm changes the shared expert's output numerically, so the router's logits
change, so on some steps the MoE top-8 *selection* differs. This is the one way my
arms are not a clean ablation, and it cuts **against** the candidate's own upper
bound: if re-routing costs time, `d1`'s measured saving *understates* the value of
deleting the interior, and the 95 % UB I am comparing to the bar is biased low.
That has to be bounded, not waved at.

Five things bound it.

1. **The trajectory is identical across arms by construction.** `decode_probe.py`
   is teacher-forced (`decode_probe.py:175`, `token = expected[i+1]`), so every arm
   decodes the same token sequence for the same number of steps. The `diverg` column
   in `abba.tsv` counts steps where the arm's *greedy argmax* differed from golden;
   it does not mean the arm walked a different path.
2. **Dispatch shapes are identical.** Top-8 is top-8 whichever experts win, so the
   arm-to-arm difference is *which* expert rows are gathered, not how many kernels
   run or at what shape. `PREREG.md:77-78` ("identical dispatch shapes; only the
   bytes differ") is therefore still true as written; what it did not anticipate is
   a change of *addresses*, which is a cache-locality effect.
3. **Divergence is not necessary for a large, clean response.** In the control
   block `rd2` removes 174 MB/step, saves ~456 us/step, and records **zero**
   divergences, while `rd1` records some. The ruler's headline sensitivity is
   demonstrated on an arm with no routing perturbation at all.
4. **Direct test.** My first plan was to regress each run's median step time on
   that run's divergence count *within* an arm. **That test does not exist**: the
   divergence count is deterministic and constant within an arm — `ship` 0,
   `ctl` 0, `rctl` 0, `rd2` 0, `rd1` 53, `d2` 60, `d1` 118, identical in all ten
   runs of every arm (`confound-check.py`, which reports zero within-arm variance
   in the regressor). The regressor has no variance, so the slope is not
   identified and I am not going to report a fitted number for it. What replaces
   it is a **paired per-step-index** contrast (`divergence-cost.sh`,
   `divergence-cost.py`): run `ship` and `d1` with per-step times *and* per-step
   tokens in a palindromic `ship,d1,d1,ship` order, label each step index
   divergent or not by comparing the two token streams, and compare the paired
   difference `ship − d1` on divergent vs non-divergent step indices. Pairing by
   index removes the fact that divergent steps are not randomly located in the
   sequence. The per-step cost of a divergence is then
   `median(Δ | non-divergent) − median(Δ | divergent)`, and the worst-case
   correction to `d1`'s saving is `max(0, upper 95 % bound) × (divergent
   fraction)`. **Measured** (`evidence/diverg`, 4 runs `ship,d1,d1,ship` at 160
   steps, warmup 8, so 152 measured steps per run):

   | pair | steps | divergent | med(Δ\|non) us | med(Δ\|div) us | c_hat us |
   |---|---|---|---|---|---|
   | run1_ship ↔ run3_d1 | 152 | 115 | 48.04 | 34.37 | +13.67 |
   | run4_ship ↔ run2_d1 | 152 | 115 | 35.54 | 29.83 | +5.71 |
   | **pooled** | 304 | 230 (f = 0.757) | 38.79 | 32.10 | **+6.69, 95 % CI [−40.12, +49.06]** |

   **The interval contains zero: there is no measurable re-routing cost**, and the
   pre-registered comparison stands as run. The point estimate says a divergent
   step costs `d1` about 6.7 us, which at f = 0.757 would add +5.1 us/step — well
   inside the gap to every published bar.

5. **The divergence-free subset, which needs no correction at all.** The cleanest
   answer is to throw the divergent steps away and measure the dose only where
   both arms emitted the same token; on those steps no re-routing difference can
   be carrying anything (`divfree.py`, moving-block bootstrap, L = 8 steps, so
   serial correlation is preserved rather than assumed away):

   | subset | n | median saving | 95 % moving-block CI |
   |---|---|---|---|
   | same-token steps only | 74 | **+38.79 us/step** | [−6.50, +62.60] |
   | all steps | 304 | +35.31 us/step | [+10.83, +47.33] |

   Removing every divergent step **does not raise** the saving beyond noise
   (+38.79 vs +35.31), which is the same statement as `c_hat ≈ 0` from a
   different direction. And the confound-free subset's own 95 % upper bound,
   **+62.6 us/step**, is still below the 68.7 us/step bar.

**The one construction under which the target survives, and why I do not believe
it.** If you take the 95 % *upper* end of `c` (+49.06 us), multiply by f = 0.757
to get +37.1 us/step, and add that to the 95 % *upper* end of `d1`'s block
bootstrap (+56.7 us/step), you reach ≈ +93.8 us/step, which clears 68.7. I am
stating that explicitly rather than letting a reader find it. I do not report it
as a result, for five reasons: (a) it is not the pre-registered comparison, and
compounding two independent 97.5th percentiles is not a 95 % statement about
anything; (b) it requires `c` to be seven times its point estimate, on an
interval that straddles zero; (c) `divergence-cost.py:50-51` resamples steps
i.i.d. and therefore **understates** the width — its tails are the least
trustworthy part of it (§8, caveat 2), so leaning on its upper tail is
leaning on the weakest number in this report; (d) the divergence-free subset
above answers the question directly, without any correction, and lands at +38.8
with an upper bound of +62.6; and (e) the magnitude is implausible on its own
terms — at the routed family's *measured* marginal byte rate (2.5162 us per
MB/step, §3), +49 us/step is 19.5 MB/step of extra effective traffic, 5.6 % of
the routed family's entire 347.6 MB/step (4 x 86.9), produced by a permutation
that moves **the same number of bytes** from different addresses. The point
estimate, +6.69 us, is 2.7 MB/step (0.8 %) and is entirely plausible as a
gather-locality effect; the upper tail is not. The structural check that settles
it is `d2`: half the divergences, and a **larger** median saving.

Finally, the arithmetic of the escape route. `d2` (fewer bytes removed, and the
lower-divergence arm) shows the *larger* median saving of the two doses. For the
confound to rescue the target it would have to be costing `d1` **more than
(60.0 − 56.7) us/step at the median** against the most permissive published
bar, and more than (68.7 − 56.7) against the standard one — i.e. an effect
comparable to everything the dose itself buys, while leaving `d2` almost
untouched. And even granting that, the corrected `d1` would land near `d2`'s
saving, which is itself under the bar.

The **mean disagrees with the median at `d1`** and I am not going to hide that.
The dose arms perturb the numerics, which changes MoE top-8 routing on some
steps, which produces a right tail (sd 3.0-3.3x `ship`). The median is robust to
that tail and the mean is not. This is why the CI was pre-registered on the
median. It does not rescue the target either way: the mean is *worse* for the
candidate, not better.

---

## 3. Why this is a terminal negative and not a null

The dose arms are not a proposed optimisation. They scale bytes, FMAs, loop
iterations and latency down **together**, so any arm's saving is an **upper bound
on every correctness-preserving rewrite of the kernel interior at fixed dispatch
count, fixed grid and fixed threadgroup shape**.

That scope is deliberate and I state its premises rather than assume them, because
"deleting work bounds every rewrite" is not a theorem:

1. A rewrite that raises *per-work efficiency* (better effective bandwidth, more
   ILP) on all four K-blocks could in principle beat deleting three of them. It is
   excluded here only by an external measurement, not by logic: R110 F5b found this
   kernel's text already at the sibling frontier and the in-situ excess *not* in the
   kernel text (`PREREG.md:19-22`). If you reject that premise, my bound weakens to
   "no rewrite that only removes work".
2. Geometry changes (split-K, other TG shapes) are neither interior-at-fixed-grid
   nor co-scheduling, so they are outside this ruler. They were closed separately by
   R110 F1 (eight geometry arms → `N-SHARED-QMV-GEOMETRY-IS-OPTIMAL`), but that
   campaign was **standalone-cold**, and the excess is by construction an *in-situ*
   phenomenon. An in-situ-only geometry effect is therefore closed by neither
   experiment, and I am not claiming it is.
3. The dose scales *reads*, FMAs and iterations. It does not scale output writes.
   This is a **rows=1 QMV**: each output element costs 2 B written against K/2 B of
   NVFP4 weight read, so the write side is smaller than the read side by the
   reduction depth — three orders of magnitude here. A write-side rewrite has
   nothing to win. That is a structural argument, not something the arms measured.
4. Co-scheduling is outside the ruler entirely; see the blind-spot section below.

**The dose curve saturates.** `d1` removes 1.5x the bytes of `d2` and saves no
more:

| order | `d2` removes 21.72 MB/step | `d1` removes 32.58 MB/step | `d1` − `d2` |
|---|---:|---:|---:|
| A | +49.69 us/step | +38.66 us/step | **−11.03** |
| B | +49.30 us/step | +51.92 us/step | +2.62 |

In order A the 1.5x dose is *slower* than the 1.0x dose; in order B it is
+2.6 us/step faster, against a `d1` CI that is 32 us wide. Neither order shows
the +24.8 us/step that linearity through `d2` would require. Averaged over the
mirrored pair the dose-response from `d2` to `d1` is **−4.2 us/step**: flat, with
the sign of the residual slope not even stable across the two orders.

If the excess were bandwidth-side, saving would be linear in bytes removed. On
the routed family — same instrument, same host, same campaign, run in the block
*between* the two shared-family orders — it *is* linear (k = **2.5162 us per
MB/step**, an ordinary least-squares slope over three points — the origin as an
anchor plus the two routed doses, `analyze-dose.py:300-305`;
`rd2` −173.8 MB/step → +443.17 us implies k = 2.550, `rd1` −260.7 MB/step →
+654.50 us implies k = 2.511, so the two doses agree to 1.5 %). That is a
marginal 397 GB/s, which is a sane fraction of this part's bandwidth and is
within 4 % of the independent n=1 smoke prior (2.61 us/MB, 383 GB/s). The routed
doses remove 174 / 261 MB/step against the shared doses' 21.7 / 32.6, an **8x
larger** byte range. So the instrument can see a byte effect when there is one.
On the shared family the same fit gives k = **1.34 us/MB (order A) / 1.69 us/MB
(order B)** — roughly half the routed slope, and then a plateau: the first dose
buys about what half-rate bytes would buy, and the second buys nothing.

*(Provenance note: an earlier draft quoted k = 2.61 +/- 0.02 us/MB and called it
"same session". That number came from the two n=1 shakedown runs in `SMOKE.md`,
which `SMOKE.md` itself says are "not the campaign" and "nothing here is quoted as
a result", and the +/-0.02 was the half-spread of two point estimates, not an
interval. The number above is the campaign control block with a bootstrap
interval, and the smoke value is retained only as the prior it was.)*

The pre-registered decision rule therefore fires: **`d1`'s 95 % upper bound
(56.7 us/step, the worse of the two mirrored orders) is below the
68.7 us/step landing bar.** Deleting three quarters of this kernel's reads does
not reach the bar, so no **interior** rewrite at fixed dispatch/grid/threadgroup
shape can — which is the scope stated above, not a claim about the kernel's
neighbourhood.

### The verdict does not depend on the disputed core-scaling constant

The bar is the arm-sizing rule (`CURRENT_RESEARCH_STATE.md:3850-3854`): an arm
whose best case is under **+30 M5 us/step (0.46 %)** does not justify a slot.
Rule 105.12 (`:3856-3859`) is the *units* clause on top of it: in locally measured
M4 units the threshold is **68.7 us/step bytes-bound** or **60.0 us/step
latency-bound**, because applying the M5 number to an M4 estimate is too
permissive by 2.29x (bytes) / 2.00x (latency).

That 2.29 is `1/alpha` with `alpha = 0.4369`, and the campaign's own Rule 105.19
(`:9439-9446`) marks alpha **not identified** — "the defensible statement is
alpha < 0.4454" — while the direct whole-decode measurement gives
`k_steady = 4141.5/8448 = 0.4902`, i.e. a divisor of 2.04. So the bar is not a
single agreed number. It does not matter here:

| divisor used | source | resulting M4 bar | d1 95 % UB | clears? |
|---|---|---:|---:|---|
| 2.29 | alpha = 0.4369, bytes-bound | 68.7 | +56.7 | no |
| 2.245 | alpha = 0.4454, the 105.19 upper bound | 67.4 | +56.7 | no |
| 2.04 | k_steady whole-decode, most permissive | 61.2 | +56.7 | no |
| 2.00 | beta = 0.5, latency-bound floor | 60.0 | +56.7 | no |

**The candidate fails against every published conversion**, including the most
permissive one — but I want to be exact about how much room is left, because it
is not much. The margin is **12.0 us/step** against the standard 68.7 bar,
10.7 against 67.4, **4.5 against 61.2 and 3.3 against 60.0**. On the two most
permissive conversions the verdict is therefore *carried by a few microseconds of
a bootstrap upper tail*, and an honest reader should treat "fails at 60.0" as
much weaker than "fails at 68.7". Three things keep me from softening the
verdict anyway: the decision quantity is the **worse** of two mirrored orders
(order A's UB is +41.2, order B's is +56.7, and I am using the latter); the
median point estimates, which are what the pre-registration named, are +38.7 and
+51.9, i.e. 8-21 us under even the 60.0 floor; and the dose curve has already
**saturated**, so the missing microseconds are not recoverable by removing more
work. If the campaign's alpha dispute later settles at the permissive end, the
right summary of this experiment is "the interior is worth at most ~57 us/step
and the loosest bar is 60" — still a do-not-land, but a thin one, and I would
rather say that than round it into a comfortable margin.

*(Units note, since I got this wrong once already: 8972 is an **M4** decode-wall
denominator (`:2127-2128`), not an M5 one, and the campaign price
0.75 x tau x delta_M4_wall_us / 8972 = 0.0084 %/wall-us at tau=1 is built on it.
Its own provenance is contested — the rival M4 controls are 8448 and 8984.5 — but
nothing in this result rests on it, because I adjudicate in us/step against the
M4-unit bar rather than in percent.)*

Per the landing rule I ship only on a verified positive interval excluding zero.
There is none here that clears the bar. **Do not land.**

### The blind spot in my own instrument (read this before trusting the negative)

My dose arms vary in-kernel work at **fixed dispatch count, fixed grid, fixed
threadgroup shape**. Alphonse's R114-E result (#700, §6.1) shows that exact ruler
reading *flat* on `gate_sp` — 3.7x fewer memory instructions moved wall only 3.98
us/step — while the family was in fact worth **-76.8 us/step, 19x larger**,
because the time was recoverable **only by co-scheduling** (appending tiles onto
a neighbour's grid so idle cores absorb them). A ruler like mine would have closed
his family by mistake.

So my result closes the kernel **interior** and does not close **co-scheduling**.
I did not measure that route and I do not claim it. It is, however, priced by
others, and both prices are under the bar:

| route | instrument | bound | bar | verdict |
|---|---|---:|---:|---|
| interior rewrite | my dose ruler, **measured here** | **<= +56.7 us/step** (95 % UB) | 68.7 | fails |
| dispatch tax | 39 x 0.4478 us/dispatch, audited (not mine) | 17.5 us/step | 68.7 | fails |
| co-scheduling / grid append | #700 follow-up (1), his 29.4 % discount (not mine) | 25-30 us/step | 68.7 | fails |

Alphonse's absorption gate is *TG count below core count*: `gate_sp` launches 8
threadgroups on 20 cores (0.4/core) and was idling the machine; **this target
launches 256 (12.8/core)** and is not, so the absorption term that supplied 4.29x
his dispatch tax has no source here. And his own follow-up list prices
"shared-expert SwiGLU into the routed SwiGLU grid" — which *is* this target — at
**25-30 us/step**, under the bar even before it is bundled.

Full argument, with the instrument rule I recommend adopting, in
`CO-SCHEDULING-BLIND-SPOT.md`.

---

## 4. The advisor's question (b): bandwidth-side or occupancy-side?

**Neither. It is fixed-cost-side.**

- **H-bw (bandwidth-side): refuted** by the saturation above.
- **H-ceiling (occupancy/ceiling-side): refuted.** Threadgroup counts, printed
  next to the null as asked: shared QMV **256** threadgroups (12.8/core), routed
  QMV **2048** (102.4/core), alphonse's `gate_sp` **8** (0.4/core). The shared
  family is not in an occupancy-starved regime, and the routed family at 8x the
  threadgroup count shows the *linear* byte response, not a flat one.
- **H-fixed (fixed per-dispatch cost): survives, but only as a direction, and I
  have withdrawn the number I first attached to it.** An earlier draft multiplied
  39 dispatches/step by Rule 55's 3.97 us intercept and called the product a
  "155 us/step dispatch floor", 2.3x the whole excess. **That is retracted**, in
  this document and in `INTERPRETATION.md`, for three independent reasons: (i)
  3.97 us is the intercept of a *DRAM-bytes* regression and a SPLIT=1 busy
  quantity, not a per-dispatch wall cost — its source says so
  (`research/maple-nezuko-r93-c-stall-structure-census.md:293-294`); (ii) Rule 53
  (`research/CURRENT_RESEARCH_STATE.md:5661-5663`) measured the opposite directly,
  "THERE IS NO DECODE DISPATCH RESIDUE ... closes to +0.3 us over 406/406
  dispatches"; and (iii) reading a bandwidth-bound model's intercept as a launch
  tax inverts that model's own conclusion. The number that survives audit is the
  SPLIT=0 dispatch tax alphonse measured, **0.4478 us/dispatch = 17.5 us/step**
  over this family's 39 calls — which is ~4x *below* the bar. So the honest form
  of H-fixed is: the excess is not in the kernel interior (measured here) and not
  in bytes or occupancy (measured here), and what is left is dispatch *structure*
  — but structure in the co-scheduling sense of `CO-SCHEDULING-BLIND-SPOT.md`, not a launch-tax
  arithmetic that I can no longer defend. The attribution capture below measures
  the fixed part directly and does not have to assume it: **c = 2.590 us/call,
  34.9 %% of the shipped per-call cost, 101.0 us/step of busy** — 144 %% of the
  entire in-situ excess.
- **H-hidden: partly refuted** — see `INTERPRETATION.md`.

This also answers (c): the family does carry `lagunaSharedSwiGLUQMVHeader`, which
makes the prior pessimistic, and the measurement agrees with the prior.

### Attribution capture (SPLIT=1) and the tau correction

Six SPLIT=1 captures, palindromic `ship, d1, rd1, rd1, d1, ship`, 200 steps each
(`evidence/profile`, `analyze-profile.py`). This is attribution only and is never
a ranking number. Splitting each family's per-call busy cost into a part that
scales with K blocks and a part that does not:

| family | busy/call, 4 blocks | busy/call, 1 block | marginal `m` per K block | **fixed `c`** | fixed share |
|---|---:|---:|---:|---:|---:|
| shared gate+up QMV (the target) | 7.430 us | 3.800 us | 1.210 us (0.2785 MB/call ⇒ **230.1 GB/s**) | **2.590 us/call** | **34.9 %** |
| routed gate+up QMV (control) | 38.565 us | 23.115 us | 5.150 us (2.2282 MB/call ⇒ **432.7 GB/s**) | 17.965 us/call | 46.6 % |

`4m + c` reproduces the shipped per-call cost exactly in both families, which is
the internal consistency check on the split. Over 39 calls/step the target's
cost decomposes into **101.0 us/step that does not scale with bytes** and
188.8 us/step that does — and the marginal rate that the byte part runs at,
230 GB/s, is **half** the routed family's 433 GB/s on the same host in the same
capture. A kernel whose per-byte rate is half its sibling's and whose per-call
cost is a third fixed is not a kernel whose interior is the prize.

**The tau correction, in the same paragraph as required.** Both dose arms give a
*direct* busy-to-wall ratio, because the same arm was measured both ways:

| family | delta busy (SPLIT=1) | delta wall (SPLIT=0 campaign) | **measured tau** |
|---|---:|---:|---:|
| shared, `d1` | 141.6 us/step | 51.9 us/step (order B median) | **0.367** |
| shared, `d1` | 141.6 us/step | 38.7 us/step (order A median) | 0.273 |
| routed, `rd1` | 602.5 us/step | 654.5 us/step | 1.086 |

My own two mirrored orders therefore bracket the target at **tau in [0.27, 0.37]**,
and every conversion below uses the **larger** value, which makes every busy-side
number convert to the **larger** wall number — the conservative direction for a
negative result. tau = 0.367 sits inside my published
`L-PROFILED-BUSY-OVERPREDICTS-WALL-2X` band (0.54, CI [0.29, 0.79]), inside
cedar's #699 band [0.27, 0.43], and next to the campaign default ~0.40 — three
independent estimates agreeing on this family. The routed tau of 1.086 is
*above* one and I am not going to quietly drop it: for a bandwidth-dominated
kernel the SPLIT=1 serialisation removes the overlap that was hiding part of the
cost, so busy can understate rather than overstate wall. That is a warning about
using a single campaign-wide tau, and it cuts in the conservative direction here
— the family I am adjudicating is the one with the *small* tau.

**And this reprices the charge's own 68 us/step.** The ~68 us/step "excess" this
assignment was written around is a profiled-busy quantity. My capture reproduces
it independently: the same kernel text costs 5.637 us/call in R110 F1's
standalone-cold rig and **7.430 us/call in situ**, an excess of 1.793 us/call =
**69.9 us/step of busy** — within 3 % of the charge's number, from a different
rig. Converted at the tau I measured for this exact family, that is
**69.9 x 0.367 = 25.6 us/step of wall**. Two things follow. First, the excess is
**already below every published bar before any of my arms are considered** — the
whole prize, if it were perfectly harvested, is 37 %% of the way to 68.7 in the
units that score, and 43 %% of the way to the most permissive 60.0. Second, 25.6 us/step is where alphonse's independent
pricing of this exact target landed (**25-30 us/step**, `CO-SCHEDULING-BLIND-SPOT.md`),
by a completely different route. I did not know that when I designed this
campaign, and it is the single strongest corroboration in this report.

The fixed part is also where the excess lives: `c` = 2.590 us/call x 39 =
101.0 us/step of busy, i.e. **144 % of the 69.9 us/step in-situ excess**. The
excess is entirely inside the non-byte-scaling part of the per-call cost, which
is exactly what a dose ruler cannot reach and exactly what §4 concluded from the
wall-clock arms alone.

All of section 2 is **wall-clock**, unprofiled, and needs no tau.

---

## 5. A correction against myself

`PRICING-NOTE.md` records that **I mis-priced my own target in `PREREG.md` by a
factor of 2.2.** I applied the Rule 105.12 core-scaling divisor (/2.29) to an
excess that the charge itself calls core-count invariant. The correct tau=1 price
of the whole 68 us/step is 0.75 x 68 / 8972 = **0.57 %**, not the 0.26 % I
pre-registered.

The correction makes the negative *stronger*, not weaker: the dose arms only ever
reach the core-scalable interior, and the prize moves entirely into dispatch
structure. Note also that the pre-registered P0 band of 700-900 us was 0.60x too
generous, recorded in `SMOKE.md` at the time rather than quietly retuned.

**And a second error inside the correction.** An earlier draft of `PRICING-NOTE.md`
divided alphonse's 76.8 us/step by his 40 removed dispatches, got 1.92
us/dispatch, and extrapolated 39 x 1.92 = **75 us/step** as an above-bar follow-on
for this target. Having now read #700's terminal result rather than the campaign's
summary of it, **that extrapolation is wrong and he refutes it himself** (§6.3):
the audited dispatch tax is **0.4478 us/dispatch** (17.9 us/step over his 40), and
his measured 76.8 was **4.29x** that — the surplus being grid-append absorption
available only to a kernel launching fewer threadgroups than the machine has
cores. Corrected, the dispatch-structure bound here is 39 x 0.4478 =
**17.5 us/step, ~4x below the bar**. The correction destroys my own follow-on, and
it is recorded in the document that made the error.

---

## 6. Correctness gate

`research/run_upstream_equivalence.sh` at the default arm (`DARKBLOOM_SHARED_QMV_ARM`
unset ⇒ `ship`, which is byte-identical MSL to the shipped kernel), on the clean
tree, 43.0 s, log at `evidence/equivalence.log`:

| what the oracle checked | result |
|---|---|
| tests selected and run | **1** (non-zero) |
| greedy token IDs, 9 tokens | **all match**: 5991, 509, 902, 5991, 509, 902, 5991, 509, 902 |
| teacher-forced decode steps (`EQUIVALENCE_EXACT_STEPS=8`) | **8/8 with `maximumAbsoluteLogitError = 0`** — bit-exact |
| prefill logits | deviates: max abs 0.125, mean abs 0.011933609, against a 0.0 tolerance |
| `EQUIVALENCE_EXIT` | 1 |

**The non-zero exit is the documented pre-existing gen-16 base property, not a
regression from this branch, and I did not relax the tolerance to hide it.** The
campaign has recorded this exact pair before, on an *untouched* tree:
`research/CURRENT_RESEARCH_STATE.md:8168-8173` — "all 9 greedy tokens match;
bit-exact on all 8 teacher-forced decode steps; prefill diverges 0.125 against a
0.0 tolerance — a **pre-existing gen-16 property of the base**, reproduced on the
untouched tree" — and `:3576-3577` records the identical numeric pair
"(0.125 / 0.011933609)". The wrapper's own comment says to compare the unchanged
`BASE_SHA` on a non-M5 host before attributing drift, which is what those two
entries are. `MLXFAST_LAGUNA_EQUIVALENCE_MAX_ABS_ERROR` was **not** touched.

Two things make this a clean gate for *this* branch specifically. First, the
decode side — the only side this experiment measures or changes — is bit-exact,
0.0 logit error on all 8 steps. Second, at the default arm `lagunaR118Dose()`
returns `(4, "")` for every kernel, so the emitted MSL text and the kernel name
are byte-identical to the shipped ones; the dose arms exist only under an
explicitly-set env var and cannot be reached by the scorer or by any test.

A zero selected-test count is not a pass; the count above is non-zero.

*Citation correction.* The campaign (and an earlier draft of this document) says
"Rule 105.15" for the non-zero-test-count gate. That is shorthand and it is not
what 105.15 says. The gate is official and lives in `AGENTS.md:108-110` — the
wrapper "refuses to call a zero-test invocation a pass". Rule 105.15
(`research/CURRENT_RESEARCH_STATE.md:9223-9236`) is the *narrower* and equally binding point
that `max_abs_diff` is a hard-coded schema constant and `golden_hash` is the input
digest, so **neither is correctness evidence and neither is cited here**. I claim
exact token-ID equality from the equivalence oracle and nothing else.

The research profiling patch to `device.cpp`/`device.h` is applied and reverted
inside `qmv-dose-profile.sh`; `git status` on both files is empty at the end of
the closing sequence, and the clean release worker was rebuilt so the branch is
left rankable.

---

## 7. What I am NOT claiming

- Not that the kernel is optimal — only that its *interior* cannot yield 68
  us/step, because deleting 75 % of it does not.
- Not that a dispatch-structure follow-on is available for this family. The
  audited realisable rate is 0.4478 us/dispatch = **17.5 us/step**, ~4x below the
  bar. The larger "39 x 3.97 us = 155 us/step" figure is **retracted** (S4); it
  read a DRAM-model intercept as a launch tax. Section 5 records the separate
  75 us/step error and why it was wrong too.
- Not any two-build comparison anywhere: one binary, one env var, everything
  paired within a session.
- No unaudited numbers: every figure here traces to a committed CSV or log.

## 8. Methods caveats, from an audit of my own analysis code

I had the analysis scripts read line by line against what this document claims
they compute. **No bug was found that changes a confidence interval or a
verdict** — block pairing is keyed by arm and verified at 10/10/6 complete blocks
(`analyze-dose.py:246-247`, numeric sort at `:47`), the bootstrap resamples
*blocks* and takes medians with 2.5/97.5 percentiles (`:63-65`, `:259`), the sign
convention is `ship − arm` throughout (`:235`, `:256`), and the warm-up drop is
exact. Five things did come out of it that a reader is entitled to know:

1. **The sign test and the bootstrap are not the same statistic.**
   `confound-check.py` reads each run's log-reported median over all 160 steps;
   the bootstrap reads the warm-up-trimmed per-step CSV. They agree to within a
   microsecond on every arm, but they are not identical arithmetic and I have not
   pretended otherwise (§2).
2. **`divergence-cost.py`'s interval is anti-conservative.** `:50-51` resamples
   steps i.i.d., which throws away serial correlation between neighbouring decode
   steps, so the true interval on `c_hat` is *wider* than [−40.12, +49.06]. The
   point estimate and the structural arguments around it stand; **its tails are
   the weakest numbers in this report** and I have argued explicitly against
   leaning on the upper one (§2). `divfree.py` uses a moving-block bootstrap
   (L = 8) for exactly this reason.
3. **The divergence label is a proxy.** It compares each arm's greedy argmax
   against the golden stream rather than instrumenting the router's top-8
   selection. A step whose argmax agrees but whose expert set differs is
   mislabelled "non-divergent", which biases `c_hat` **toward zero**. That is a
   real limitation of the confound bound and it is the main reason I lean on
   `d2`'s structure (more saving, fewer divergences) rather than on `c_hat` alone.
4. **A stale comment.** `divergence-cost.py:70-73` describes the pairing as
   "run 1 with run 4 and run 2 with run 3"; the code as written pairs run1↔run3
   and run4↔run2. Both are valid palindromic pairings and the printed table names
   the actual pair, so the numbers are right and the comment is wrong.
   `:64-65` also sorts run files lexically, which is harmless at 4 runs and would
   not be at 10+.
5. **A percentile bootstrap of a median on 10 blocks (6 in the control block) is
   coarse.** Nominal 95 % coverage is approximate at that block count. This is
   precisely why every headline is reported with an **exact sign test** beside it,
   and why the decision quantity is the worse of two independently-run mirrored
   orders rather than a pooled interval.

## 9. Files

- `PREREG.md` — pre-registration, written before the data existed
- `METHOD.md` — design in the form the charge asked for
- `SMOKE.md` — positive-control calibration, including where the pre-registration was wrong
- `INTERPRETATION.md` — the four hypotheses and their adjudication
- `PRICING-NOTE.md` — the mis-pricing correction against myself
- `CO-SCHEDULING-BLIND-SPOT.md` — the one route this instrument cannot see, and its independent pricing
- `HOST-HYGIENE.md` — two host-hygiene violations during orderA, disclosed, with the falsifier
- `D0-A2-IS-THE-SAME-BINARY.md`, `D0b-IS-PREFILL-ADJUDICABLE.md` — the out-of-band asks
- `divfree.py` — the divergence-free subset estimate, moving-block bootstrap
- `evidence/` — raw logs, per-step CSVs, analyser JSON, equivalence log, profile capture
- `evidence/profile/attribution.json`, `evidence/diverg/divfree.json` — the derived
  quantities from `analyze-profile.py --json` and `divfree.py --json`; the W&B run
  reads these files rather than re-typing the numbers, so the run, this document
  and the raw logs cannot disagree
