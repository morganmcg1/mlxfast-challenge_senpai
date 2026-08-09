# R97-A Stage 2 result — layer-0 dense-MLP block-exponent compaction

Assignment `maple-r97-a-dense-mlp-stage2`, revision `r97-a-rev1`, PR #525.
Base `b78e7cdb80b5ae5f1cb1fdd39803322fb283ae5e`.
Preregistration: `research/fern-r97-stage2-preregistration.md`, committed as
`1e683e5` before any timing datum was collected.

Host: M4 Pro, 48 GiB, low-memory startup profile. **Directional only.** The M4
Pro reports Apple GPU generation 16 and does not select the `_nax` prefill
kernels the ranked M5 uses; every number below is a decode-side measurement on
the shipped dense-MLP path, which is the same kernel family on both machines,
but the official M5 remains authoritative.

## 1. What shipped

Three submitted files:

| path | role |
|---|---|
| `Sources/MLXFastModel/LagunaRuntimeWeights.swift` | `LagunaDenseBlockExponentBank`, packer, bit-exactness certificate |
| `Sources/MLXFastModel/LagunaRuntimeModel.swift` | two block-exponent kernels, their wrappers, the two selection flags |
| `Sources/MLXFastModel/LagunaRuntimeLayers.swift` | bank construction at load time and the dispatch preference |

Both banks are built once outside the scored hot path and are installed only
after a certificate rebuilds every BF16 pattern of the plane bit-for-bit; a
plane that fails the certificate is declined and the stock path runs.

## 2. Timed states

| state | gate/up plane | down plane |
|---|---|---|
| base | stock BF16 | stock BF16 |
| S2a | block-exponent `B=128, d=4`, escapes allowed | stock BF16 |
| S2b | block-exponent `B=128, d=4`, escapes allowed | block-exponent `B=row(8192), d=6`, no escapes |

### 2.1 Headline

**Both compacted states are slower than base. The experiment is a NO-GO, and it
is the "conversion efficiency below 0.5" branch of the go/no-go bar, i.e. the
branch the assignment names as a publishable bandwidth finding.**

One blocked randomised ladder, 12 processes x 8 timed runs x 248 steps,
`rand:0,1,2` with a placebo every 8 blocks, 40 C gate, seed 97. All three states
are one binary and one process image selected per step through a shared `mmap`
control word (§3b). 3,112 complete blocks; the assigned estimator censors 13
(0.4%) at median + 8*MAD and reports 3,099.

Every one of the 12 process files carries the single token-stream hash
`082682744836a553` and 0 teacher-forced mismatches.

| contrast | measured us/step | 95% CI | preregistered prediction | conversion efficiency |
|---|---|---|---|---|
| S2a − base (gate/up compaction) | **+69.60 slower** | [+67.54, +71.58] | −60.3 (faster) | **−1.154** |
| S2b − base (both planes) | **+61.96 slower** | [+60.17, +63.74] | −76.1 (faster) | **−0.814** |
| S2b − S2a (down plane, marginal) | **−7.66 faster** | [−9.84, −5.39] | −15.8 (faster) | **+0.485** |

Unpaired medians over the same records agree: base 8226.6 us/step, S2a 8296.9
(+70.3), S2b 8288.9 (+62.3). S2b is 0.757% slower per decode step, which at the
0.75 decode weight is about **−0.57% on score** against a preregistered
**+0.31%** gain.

### 2.2 Validity of the instrument

Four checks, all passing, so the sign above is a property of the change and not
of the rig:

- **Placebo.** 440 placebo blocks execute rung 0 on every step while carrying
  the assigned rung labels. Their contrasts are `d1 = +0.61 us`
  CI `[−3.54, +4.95]` and `d2 = +0.66 us` CI `[−2.57, +4.03]`; both include 0.
- **No carryover.** Regressing step time on own rung and previous rung with
  block fixed effects gives a previous-rung coefficient of `+0.0101 us/dispatch`
  CI `[−0.0161, +0.0375]`, which includes 0 (design correlation −0.174, VIF
  1.03). Rung switching inside a process does not contaminate the contrast.
- **A second, switch-free design agrees.** The §3b rung-control session assigned
  one fixed rung per process (`const:0;const:1;const:2`, no switching at all)
  and produced +64.1 us for S2a and +67.1 us for S2b against base — same sign,
  same order of magnitude, from between-process rather than within-process
  contrasts.
- **The 48-step smoke run agrees** in sign (+38.8 / +40.5) with no thermal
  control.

### 2.3 The byte claim was met; the conversion was not

The bytes really were removed, and exactly as preregistered — the load-time
census in §3 reproduces the predicted escape counts to the block, and the two
banks are installed only after a bit-exactness certificate. S2b removes
**20,263,168 B = 20.263 MB per step**, clearing the bar's ≥19.0 MB requirement.

So this experiment does not fail because the compaction failed. It fails because
**a removed byte on this path is not worth the bandwidth-model price**, and on
one of the two planes it is worth a large negative amount. The preregistration
priced a byte at ~266 GB/s assuming zero ALU cost and flagged that as the
optimistic bound; the outcome is far outside even a pessimistic reading of that
bound, because the mechanism is not ALU cost (§3c, §3d).

### 2.4 The additive model is refuted, informatively

Solving the two planes' design points for a byte value (us/MB) and an op cost
(us/Mop) returns `byte_value = −7.861 us/MB` CI `[−8.294, −7.406]` and
`op_cost = −0.1937 us/Mop` CI `[−0.2126, −0.1739]`. **Both coefficients are
negative, which is physically impossible**: it would require that moving bytes
and issuing integer ops each *save* time. An additive bytes-plus-ALU model
cannot describe these two kernels.

The refutation has a direction worth recording. The two planes' added-op counts
differ by only 1.4x (293.6 vs 209.7 Mop) while their non-bandwidth penalties
differ by roughly 15x. No scalar cost model in bytes and ops can fit that, which
is why §3d goes looking at the loop structure instead.

<!-- PERRUN -->

## 3. Escape census, confirmed at load time

The packer prints one census line per plane. Observed with
`DARKBLOOM_ATTN_SCALE_NARROW_LOG=1`:

```
block-exponent B128 d4 escaped 1735/262144: dense gate/up
block-exponent B8192 d6 escaped 0/2048: dense down
```

Both match the preregistration exactly. The preregistration predicted 1735
escaped gate/up blocks (858 gate + 877 up) out of 262,144 and zero escaped
down rows out of 2,048; the bytes/step arithmetic in §5 of the preregistration
was computed from those counts, so the byte predictions carry no census risk.
Both certificates passed, so neither plane was declined.

## 3b. Rung-control verification

Before any timed comparison the instrument itself was checked. The ladder
patch replaces the two `*Active()` predicates with a read of a shared mmap
control word, so a silent mmap failure would fall back to the static default
(rung 2) and dispatch both kernels in every process — an instrument that
reports "no effect" for the wrong reason. Three single-rung processes were run
with `SCHEDULE="const:0;const:1;const:2"` and dispatch logging on:

| process | rung | `block-exponent kernel:` notes | token-stream hash | teacher-forced mismatches |
|---|---|---|---|---|
| p00 | 0 (base) | none | `004d82089b71b300` | 0 |
| p01 | 1 (S2a) | `dense gate/up` | `004d82089b71b300` | 0 |
| p02 | 2 (S2b) | `dense gate/up`, `dense down` | `004d82089b71b300` | 0 |

The control word is therefore read live, each rung selects exactly the intended
kernel set, and all three rungs produce the identical token stream.

## 3c. Unpack-ALU audit: added integer ops per byte removed

The preregistration priced a removed byte at ~266 GB/s **assuming zero ALU
cost**, and flagged that assumption as the optimistic bound. Counting the
integer ops actually emitted by the two shipped kernels turns that assumption
into a number that can be checked before a change is built.

Counted from the kernel bodies in `LagunaRuntimeModel.swift`, per 4 elements
handled by one thread for one weight row:

| term | gate/up (`bexp128d4`) | down (`bexp_row_d6`) |
|---|---|---|
| delta load addressing | 3 | 4 (two delta streams) |
| escape-base compare | 1 | 0 (no escapes) |
| payload load addressing | 2 | 2 |
| base shift | 1 | 0 (hoisted, row-invariant) |
| delta extract + assemble, 4 elem | 16 | 32 |
| rotate back to BF16, 4 elem | 12 | 12 |
| **total per 4 elements** | **35** | **50** |
| **per element** | **8.75** | **12.5** |

Cross-check against the preregistered per-thread figures: gate/up handles
`4 rows x 2 planes x 4 elements = 32` elements per K-iteration, giving 280 ops
against the preregistered "≈240"; down handles `4 rows x 4 elements = 16`,
giving 200 against "≈160". The audit is 15-25% **higher** than the
preregistered estimate in both cases, i.e. the preregistration understated the
ALU cost. That is recorded as a deviation in §8.

Converting to the quantity that generalises:

| plane | elements | added int ops | bytes removed | **ops per byte removed** |
|---|---|---|---|---|
| gate/up (S2a) | 33,554,432 | 293.6 M | 16,070,912 | **18.3** |
| down (S2b − S2a, marginal) | 16,777,216 | 209.7 M | 4,192,256 | **50.0** |
| S2b combined | — | 503.3 M | 20,263,168 | **24.8** |

The obvious quantity to compare against is the machine's integer-throughput to
DRAM-bandwidth ratio. On this M4 Pro, ~20 cores x 128 lanes x ~1.5 GHz gives
roughly 3.8-4.0 T simple-int-ops/s against a measured 260.2 GB/s ceiling, i.e.
a nominal break-even near **15 added integer ops per byte removed**. Before any
timing this audit therefore predicted that both planes were unprofitable, with
gate/up (18.3) marginal and down (50.0) roughly 3x over.

**The measurement in §2 refutes that ordering, and I am recording the refutation
rather than the rule.** The plane the audit called 3x-hopeless (down, 50.0
ops/byte) is the one that converted, and the plane the audit called marginal
(gate/up, 18.3 ops/byte) is the one that lost far more time than its bytes could
ever have been worth. A scalar ops-per-byte screen does not rank these two
kernels, so §9 does not promote it to a standing rule. §2 develops what does
separate them; the audit survives only as an accounting of what the unpack
actually costs, not as a predictor.

## 3d. What actually separates the two planes

The two planes disagree so sharply (§2) that the first thing to rule out is that
I simply wrote a worse GEMM for one of them. I did not: **each compacted kernel
is geometry-matched to the stock kernel it replaces.**

| | stock gate/up (8700) | bexp gate/up (8887) | stock down (8793) | bexp down (9018) |
|---|---|---|---|---|
| `rows_per_thread` | 4 | 4 | 4 | 4 |
| `values_per_thread` | 4 | 4 | 4 | 4 |
| `rows_per_group` | 64 | 64 | 16 | 16 |
| threadgroup | 512 | 512 | 128 | 128 |

Accumulator layout, the simd-shuffle reduction, and the epilogue are unchanged
in both pairs. The only thing that differs inside each pair is how a row's four
BF16 weights are obtained. So `d1` and `d2` are clean contrasts on the weight
load, not on the matmul.

Counting the inner loop of each kernel, per K-iteration per thread:

| | loads | weight bytes | data-dependent branches |
|---|---|---|---|
| stock gate/up | 9 | 72 | 0 |
| bexp gate/up | 19 (**2.11x**) | 64 (**0.89x**) | **8** |
| stock down | 5 | 40 | 0 |
| bexp down | 13 (**2.60x**) | 36 (**0.90x**) | **0** |

This table is the useful result of the whole experiment, because it kills three
plausible explanations at once. The byte multiplier is the same for both planes
(0.89 vs 0.90). The added-op counts are within 1.4x of each other (293.6 vs
209.7 Mop, §3c). The load-instruction multiplier is actually **worse** for the
plane that won (2.60x for down against 2.11x for gate/up). None of bytes, ops,
or load count orders these two planes the way the measurement does.

Exactly one structural axis does: the eight data-dependent branches. The
compacted gate/up guards every payload load with `if (base == 0xFF)`, once per
row per plane, because `d=4` cannot represent every block's exponent range and
0.66% of blocks escape (§3). The compacted down plane is escape-free by
construction, so all twelve of its loads are unconditional with addresses known
before the loop body starts.

The cost is very unlikely to be divergence — at 1735/262144 the branch is
essentially uniform across any simdgroup. The cost is **memory-level
parallelism**. In the down kernel every load in an iteration is independent and
can be issued back to back. In the gate/up kernel each payload load sits behind
a branch whose condition is a register value, and the not-taken side's address
depends on `gd`, a value loaded in that same iteration — so the eight payload
loads serialise behind eight delta loads instead of overlapping them. A kernel
that was comfortably bandwidth-bound becomes latency-bound, and once it is
latency-bound the bytes it saved are worth nothing.

This is a source-level argument, not a counter measurement, and it is stated as
the leading hypothesis rather than a demonstrated fact. Three confounds survive
it: gate/up uses 512-thread groups against down's 128, runs 16 loop trips
against down's 64, and keeps 12 live accumulators against down's 8. §9 gives
the experiment that would separate them, and it is cheap: the hypothesis
predicts that an **escape-free** gate/up plane converts at roughly the down
plane's efficiency, while the confounds predict it stays negative.

## 4. Equivalence and correctness

<!-- CORRECTNESS -->

## 5. Byte budget

`senpai/check-editable-budget.sh b78e7cdb80b5ae5f1cb1fdd39803322fb283ae5e`:

| | current | headroom | growth | files |
|---|---|---|---|---|
| base | 2,899,476 | 100,524 | 0 | 141 |
| this branch | 2,925,859 | 74,141 | **26,383** | 141 |

Growth is 26,383 B against the assignment's 60,000 B cap and the contract's
262,144 B per-review cap. No file was added or removed, and no submitted file
approaches the 524,288 B per-file cap.

## 6. W&B evidence

<!-- WANDB -->

## 7. Reproduction

All research tooling lives under `research/` and is not part of the submitted
surface. The submitted surface is the three files in §1.

Build the three-rung worker and run the blocked randomised ladder:

```bash
bash research/fern_r97_ladder_session.sh OUT=/tmp/r97/ladder MODE=block
```

`MODE=block` expands to `P=12 R=9 S=248 SCHEDULE=rand:0,1,2 PLACEBO_EVERY=8
WARMUP_RUNS=1 GATE_C=40 SEED=97`. The driver applies
`research/fern-r97-rung-ladder.patch` on top of the pristine-Sources commit
`55edbc77b2441c6fa84d6930503c9cc7518b8ec8`, builds
`mlxfast-runtime-worker` into `.build-worker`, restores the worktree, then
delegates to `research/fern_r93_nested_session.sh`. Re-apply the patch by hand
with:

```bash
git checkout 55edbc77b2441c6fa84d6930503c9cc7518b8ec8 -- \
  Sources/MLXFastModel/LagunaRuntimeModel.swift
git apply research/fern-r97-rung-ladder.patch
```

The patch replaces the bodies of `lagunaDenseBlockExponentGateUpActive()` and
`...DownActive()` with a read of a shared `mmap` control word named by
`DARKBLOOM_R97_RUNG_MAP`, so all three states are one binary and one process
image. Gate/up is active at rung >= 1, down at rung >= 2. §3b is the evidence
that the control word is genuinely read per step.

The per-run companion reuses that binary:

```bash
bash research/fern_r97_ladder_session.sh OUT=/tmp/r97/perrun MODE=perrun \
  SKIP_BUILD=1
```

Analysis:

```bash
python3 research/fern_r93_ladder.py '/tmp/r97/ladder/p*.json' \
  --block 6 --drop-steps 24 --mad-mult 8 --bootstrap 4000 --seed 97 \
  --json-out /tmp/r97/ladder/ladder.json
python3 research/fern_r97_decompose.py '/tmp/r97/ladder/p*.json' \
  --drop-steps 24 --bootstrap 4000 --seed 97 \
  --json-out /tmp/r97/ladder/decompose.json
python3 research/fern_r93_perrun.py '/tmp/r97/perrun/p*.json' \
  --drop-steps 24 --bootstrap 4000 --seed 97 \
  --json-out /tmp/r97/perrun/perrun.json
```

Smoke check of the three states plus the escape census (48 steps):

```bash
OUT=/tmp/r97/smoke STEPS=48 bash research/fern_r97_smoke.sh
```

`NARROW_LOG=1` turns on per-dispatch logging. It takes a lock per dispatch and
was off for every timed run reported here.

## 8. Deviations from the preregistration

The preregistration (`1e683e5`) was committed before the first timing datum and
has not been edited. Everything below is recorded here instead.

1. **The ALU audit came in above the preregistered op estimate.** §3c counts 280
   added integer ops per thread per K-iteration for gate/up against a
   preregistered "≈240", and 200 for down against "≈160" — 15-25% higher in
   both planes. The preregistration understated the unpack cost.
2. **The preregistration's cost model is refuted, not merely missed.** It priced
   a removed byte at ~266 GB/s with zero ALU cost and flagged that as the
   optimistic bound. The measured outcome is outside even a pessimistic reading
   of that bound, and the two-parameter generalisation of it returns physically
   impossible negative coefficients for both parameters (§2.4).
3. **§3c originally proposed a screening rule and I withdrew it.** The audit was
   written before timing and predicted that down (50.0 ops/byte) would be far
   worse than gate/up (18.3). The measurement inverts that ordering, so §3c
   records the refutation instead of promoting an ops-per-byte screen.
4. **A placebo-analysis bug was found and fixed during analysis.** My decomposition
   script initially keyed placebo cells on the *executed* rung. A placebo block
   executes rung 0 on every step, so this collapsed every placebo block to one
   level and reported `placebo_blocks = 0`. Keying on the *assigned* slot fixes
   it; the fix is in the committed `research/fern_r97_decompose.py` and was made
   before any conclusion was drawn from the placebo arm. The assigned estimator
   `fern_r93_ladder.py` was never affected.
5. **§3d is exploratory and was not preregistered.** It is a source-level audit
   written after seeing the sign, and it is labelled as the leading hypothesis
   rather than a demonstrated mechanism.
6. **The assigned estimator's hinge model is reported but unused.** `fern_r93_ladder.py`
   prints an `EXPLORATORY hinge` fit; it was motivated by an earlier smoke run,
   is not preregistered here, and no conclusion in this document rests on it.
7. **R2 was not attempted**, per the assignment scoping R97-A to R1 only.

## 9. Verdict against the go/no-go bar

### 9.1 Bar by bar

The assignment's GO bar had five conjunctive clauses. Three pass, two fail, and
one of the two explicit NO-GO triggers fired.

| # | Bar clause | Required | Measured | Verdict |
|---|---|---|---|---|
| 1 | S2b removes census-verified traffic | ≥ 19.0 MB/step | 20.263 MB/step (§2.3) | **PASS** |
| 2 | Ladder shows S2b faster than base | ≥ 55 µs/step faster, 95 % CI excludes 0 | **+61.96 µs/step slower**, CI [+60.17, +63.74] | **FAIL** |
| 3 | Conversion efficiency (measured ÷ 76.1 µs) | ≥ 0.72 | **−0.814** | **FAIL** |
| 4 | Bit-exactness | `max_abs_diff = 0`, identical token-stream hash | all 12 ladder processes hash `082682744836a553`, 0 teacher-forced mismatches (§2.2) | **PASS** |
| 5 | Submitted-surface growth | ≤ 60,000 B | 26,383 B (§5) | **PASS** |

NO-GO triggers:

| Trigger | Fired? | Evidence |
|---|---|---|
| Ladder CI cannot exclude 0 | no | CI excludes 0 decisively, but on the wrong side |
| Conversion efficiency < 0.5 | **yes** | S2a −1.154, S2b −0.814, both far below 0.5 |

### 9.2 Verdict

**NO-GO.** Do not promote this branch to the frontier and do not spend an
official M5 submission on it. Both timed states are slower than base, the
regression is resolved to well outside its confidence interval, and the sign is
the opposite of the one the bar required.

The result is not a null. It is a resolved negative with a mechanism, and the
NO-GO branch of the preregistration explicitly anticipated it as "a publishable
bandwidth finding". The publishable content is §2.4 and §3d:

1. **The byte claim was met.** The census (§3) confirms the preregistered
   footprint exactly — 1735/262144 gate/up escapes, 0/2048 down escapes — so
   20.263 MB/step really does leave the memory system. The failure is entirely
   in conversion, not in the compaction.
2. **The additive byte + ALU model is refuted.** Fitting the two timed contrasts
   to `bytes` and `ops` yields `byte_value = −7.861 µs/MB`
   (CI [−8.294, −7.406]) and `op_cost = −0.1937 µs/Mop`
   (CI [−0.2126, −0.1739]). Both coefficients are negative. A negative byte
   value is physically impossible under the model, so the model — not the
   measurement — is what broke. Removing bytes from this kernel at this
   arithmetic intensity does not buy time on this host.
3. **The two planes disagree in the informative direction.** Gate/up costs
   +69.47 µs (CI [67.67, 71.14]) while the *marginal* down plane returns
   −7.66 µs (CI [−9.84, −5.39]) — the only positive conversion in the
   experiment, 0.485. Neither bytes removed (16.07 vs 4.19 MB), added integer
   ops (293.6 vs 209.7 Mop, only 1.4× apart), nor load count (2.11× vs 2.60×,
   *worse* for the plane that won) orders the two planes correctly (§3c).
4. **The surviving discriminator is structural, not volumetric.** §3d isolates
   the `if (base == 0xFF)` escape branch in gate/up as the only audited axis
   that orders the planes. Its cost is not warp divergence — 1735 escapes in
   262144 blocks is near-uniformly rare — but loss of memory-level parallelism:
   the payload load's address depends on the just-loaded delta word, so the
   two streams serialise instead of overlapping. Down's 12 loads are
   unconditional with statically computable addresses, and down is the plane
   that converted.

### 9.3 Confidence and transfer

The instrument is sound (§2.2): 3112 blocks with 0.4 % censoring, carryover
coefficient +0.0101 µs/dispatch with CI [−0.0161, +0.0375] spanning zero, and
both placebo arms centred on zero (d1 +0.61 CI [−3.54, +4.95]; d2 +0.66
CI [−2.57, +4.03]). The rung-control run (§3b) proves the mmap control word is
read live and that each rung dispatches exactly the intended kernels.

This host is an M4 Pro (Apple GPU generation 16), not the ranked M5 Max, so
per `agents.md` the *magnitude* does not transfer. But the failure here is not a
marginal timing call that a faster host might flip: the regression is roughly
0.76 %/step, and the byte-per-second price implied by the fit is negative.
Bandwidth-per-core differences between M4 Pro and M5 Max are on the order of
10 %, which is nowhere near enough to move a −0.814 conversion efficiency above
+0.72. I would not spend M5 time on this candidate.

### 9.4 Suggested follow-ups (not implemented)

Listed in decreasing information-per-GPU-hour. None of these is in scope for
this assignment.

1. **A `d=8` branchless gate/up rung — the decisive control.** Widen the gate/up
   delta field to a full byte at `B=128`. That removes escapes by construction
   (any 8-bit delta covers the full exponent range within a block), so the
   `if (base == 0xFF)` branch and its dependent-address stall disappear, while
   the byte saving collapses to approximately zero — the payload plus a
   full-byte delta is the same width as the original bf16. It keeps the same
   three-stream split, the same trip count, and the same register pressure. It
   is bit-exact and inside the existing legal envelope, so it costs one rung and
   no new correctness argument. Reading: if `d=8` is roughly *neutral* versus
   base, the escape branch was the whole story and a branchless narrow-`d`
   variant is worth building. If `d=8` is still ~+60 µs slower with no bytes
   saved, the cost is stream-splitting and load-issue inflation itself, and the
   entire block-exponent family is dead on this kernel — a much stronger and
   more general negative than the present one.
2. **A load-time census sweep over `d ∈ {5,6,7}` at `B=128`** to find the
   smallest escape-free `d` for the gate/up plane. This is nearly free: the
   census already runs at load time and needs no timed run. Note the arithmetic
   is discouraging before it starts — at `d=6` the gate/up saving falls to
   ~8.4 MB, and even at the down plane's *best observed* conversion of 0.485
   that is ≈ +15 µs/step of benefit against a +69.6 µs/step observed cost. Run
   it only to parameterise follow-up 1, not as a candidate in its own right.
3. **Metal GPU counters for per-plane mechanism isolation.** The present
   argument in §3d is source-level and leaves three confounds live: threadgroup
   512 vs 128, trip count 64 vs 16, and 12 vs 8 live accumulators. Counter data
   on occupancy, memory-stall cycles, and issued-load counts would collapse
   those three and confirm or kill the memory-level-parallelism explanation
   directly, rather than by elimination.
4. **Retarget the technique at a plane with the down plane's shape.** Down was
   the only plane that converted (+0.485). If block-exponent compaction is worth
   revisiting anywhere, it is on unconditional, escape-free, low-trip-count,
   low-accumulator kernels — not on wide fused gate/up projections. This is a
   redirection of the idea rather than a repair of this candidate.
