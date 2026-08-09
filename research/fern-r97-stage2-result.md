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
branch the preregistration names as a publishable measurement that the layer-0
dense stream is not purely bandwidth-limited at decode
(`research/fern-r97-stage2-preregistration.md:443-447`).**

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
(+70.3), S2b 8288.9 (+62.3). On those unpaired medians S2b is 0.757% slower per
decode step; the matched blocked estimate (+61.96) gives 0.753%. At the 0.75
decode weight that is about **−0.57% on score** against the preregistration's
model-predicted **+0.31%** gain — a comparison between an M4 Pro measurement and
a prediction made for a different host and base, so only its sign transfers
(see §9.3).

Two estimators appear in this table and they are deliberately not merged. Rows 1
and 2 are the **preregistered** analyser `research/fern_r93_ladder.py`, which
takes paired within-block contrasts against the rung-0 cell (`+69.60` and
`+61.96`). Row 3 comes from `research/fern_r97_decompose.py`, which fits the
same block cell medians as a two-plane decomposition; its own S2a estimate is
`+69.47` CI `[+67.67, +71.14]`, i.e. 0.13 us from the preregistered one and
comfortably inside its interval. Wherever this document states a headline
contrast it uses the preregistered analyser; the decompose numbers are used only
for the down marginal, the placebo arm and the byte/op fit, and are labelled as
such (see §8 deviation 4).

### 2.2 Validity of the instrument

Four checks. Three pass cleanly; the fourth agrees on the headline sign but
disagrees on the sign of the small down marginal, and that disagreement is
recorded rather than buried.

- **Placebo.** 440 placebo blocks execute rung 0 on every step while carrying
  the assigned rung labels. Under the **preregistered** analyser
  (`fern_r93_ladder.py --placebo`, 438 blocks after censoring) the contrasts are
  `K=1: +0.14 us` CI `[−4.52, +4.88]` and `K=2: +0.79 us` CI `[−3.91, +5.41]`;
  both include 0 and neither resolves. `fern_r97_decompose.py` agrees on the same
  blocks (`d1 = +0.61` CI `[−3.54, +4.95]`, `d2 = +0.66` CI `[−2.57, +4.03]`).
  The rig attributes nothing to a rung label when the rung does not change.
- **No carryover.** Regressing step time on own rung and previous rung with
  block fixed effects gives a previous-rung coefficient of `+0.0101 us/dispatch`
  CI `[−0.0161, +0.0375]`, which includes 0 (design correlation −0.174, VIF
  1.03). Rung switching inside a process does not contaminate the contrast.
- **A switching-free per-run design agrees on all three contrasts.** See §2.5:
  a separate 8-process session with the rung held fixed for a whole
  `decode_begin` run reproduces +68.79, +59.83 and −7.98 us, and contains all
  three ladder point estimates inside its intervals. This is the load-bearing
  replication.
- **The two cheap diagnostic sessions agree on the headline sign but not on the
  down marginal.** The §3b rung-control session (`const:0;const:1;const:2`,
  3 processes, 1 run, 32 steps, dispatch logging on, no warmup discard, no CI)
  gave +64.1 us for S2a and +67.1 us for S2b — so its implied down marginal is
  **+3.0 us, i.e. the opposite sign** to the ladder's −7.66 and the per-run
  arm's −7.98. The 48-step smoke session (median over all 48 steps of
  `/tmp/r97/smoke/{stock,gateup,both}.json`: 8212.2 / 8252.3 / 8252.9) gives
  **+40.1 and +40.7**, implied down marginal **+0.6 us**, again not negative.
  Neither session is a valid estimator of a ~8 us effect: both ran with
  `NARROW_LOG=1` (an `NSLock` per dispatch, §7), no thermal gate on the smoke
  arm, no warmup discard, single-run per rung, and no interval. They are
  instrument checks, not measurements, and they cannot overturn two independent
  thermally gated sessions that each resolve the down marginal below zero. The
  honest reading is that the down marginal is small enough that only the gated,
  many-replicate designs can sign it, which is why §9.4 items 3 and 4 are
  proposed as new measurements rather than extrapolations.

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

Two equations in two unknowns: the system is exactly determined and has zero
residual degrees of freedom, so it *always* fits both design points perfectly
and the bootstrap intervals above only propagate the noise in `d1` and `d2`.
They are not evidence that the model is right. The refutation does not rest on
goodness of fit — it rests on the fitted coefficients having a sign that no
physical realisation of the model can produce.

The refutation has a direction worth recording. The two planes' added-op counts
differ by only 1.4x (293.6 vs 209.7 Mop) while their non-bandwidth penalties
differ by roughly 15x. No scalar cost model in bytes and ops can fit that, which
is why §3d goes looking at the loop structure instead.

### 2.5 Switching-free replication: the ladder is not a switching artefact

The ladder changes rung between adjacent decode steps. That is what makes it
sharp, but it also means every ladder delta is measured on a step whose
predecessor ran a different kernel set. A second, independent session
(`MODE=perrun`, `P=8 R=8 S=248`, `SCHEDULE=perrun:0,1,2`) holds the rung fixed
for an entire `decode_begin` run and alternates only *between* runs, so it
shares no per-step ordering artefact with the ladder at all. Adjacent runs
inside one process are paired, and the bootstrap is clustered on process.

| Contrast | Ladder (blocked randomised) | Per-run (switching-free) | Ladder inside per-run CI? | Signs agree? |
|---|---|---|---|---|
| S2a − base (K=40) | **+69.60** [+67.54, +71.58] | **+68.79** [+56.98, +75.78], se 4.97 | yes | yes |
| S2b − base (K=80) | **+61.96** [+60.17, +63.74] | **+59.83** [+44.87, +69.49], se 6.62 | yes | yes |
| down marginal (K=80 − K=40) | **−7.66** [−9.84, −5.39] | **−7.98** [−18.11, −0.87], se 4.52 | yes | yes |

8 processes, 16 run-pairs per contrast, 1984 records per process. The pairing
rule is `research/fern_r93_perrun.py:81-97`: within each process the warmup run
is dropped, leaving 7 scored runs at rungs 40, 80, 0, 40, 80, 0, 40; only
*adjacent* run pairs whose rung set matches the requested contrast are kept,
which is 2 per process for each of the three contrasts, hence 16.

Three things follow.

1. **No switching artefact.** All three ladder point estimates land inside the
   corresponding per-run interval, and no sign disagrees. Per decision rule 56
   (`research/fern-r96-stage2-kernel-design.md:139`, honoured literally at
   `research/fern-r97-stage2-preregistration.md:376`)
   the two instruments keep their separate jobs — the ladder is the ranking
   instrument, the per-run arm the absolute-saving check — and I do **not**
   average them. The rule's inconclusive branch (sign disagreement, or a ladder
   estimate outside the per-run CI) did not trigger.
2. **The per-run arm is ~5x wider, as designed.** It spends about two thirds of
   the ladder's GPU time (8x8x248 = 15,872 timed steps against the ladder's
   12x8x248 = 23,808) and spends it on 16 run-pairs instead of 3,099 blocks, so
   it cannot resolve the sign of a small effect. It does not need to: the effect
   here is large, and both arms exclude zero on the same side. This is why the
   ladder, not the per-run arm, carries the verdict.
3. **The down plane's sign survives the harder test.** The down marginal is the
   one genuinely small effect in the experiment, and it is the one most at risk
   of being an ordering artefact of the ladder. The switching-free arm
   reproduces it at −7.98 µs with an interval that still excludes zero. The
   only plane that converted bytes into time did so under both instruments.

Bit-exactness also replicates across sessions: all 8 per-run processes emit
token-stream hash `082682744836a553` with 0 teacher-forced mismatches — the
same hash as all 12 ladder processes, from a separately launched session.

Three different hashes appear in this document — `082682744836a553` (ladder and
per-run), `004d82089b71b300` (§3b rung control) and `2a8b3751fd45e06d` (§3
smoke). They are **not** a correctness signal. The probe hashes the token stream
that a session actually generates, and the sessions use different step counts,
run counts and seeds, so they decode different token sequences. What matters is
that within every session all rungs produce the *same* hash and zero
teacher-forced mismatches, which is the invariance the experiment tests. The
absolute correctness statement comes from §4, not from these hashes.

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

The same 48-step smoke session (job `f3fc3222`, exit 0) that produced this
census also ran all three states and emitted token-stream hash
`2a8b3751fd45e06d` with 0 teacher-forced mismatches in every state.

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
roughly 3.8-4.0 T simple-int-ops/s. Dividing by the preregistration's byte price
of ~266 GB/s (`research/fern-r97-stage2-preregistration.md:392-393`) gives a
nominal break-even near **14-15 added integer ops per byte removed**. (The core
count, lane count and clock are nameplate figures for this part, not measured
here; only the bandwidth term is traceable to the preregistration. The break-even
is therefore an order-of-magnitude screen, and it would have to move by more than
3x to change the conclusion below.) Before any timing this audit therefore
predicted that both planes were unprofitable, with gate/up (18.3) marginal and
down (50.0) roughly 3x over.

**The measurement in §2 refutes that ordering, and I am recording the refutation
rather than the rule.** The plane the audit called 3x-hopeless (down, 50.0
ops/byte) is the one that converted, and the plane the audit called marginal
(gate/up, 18.3 ops/byte) is the one that lost far more time than its bytes could
ever have been worth. A scalar ops-per-byte screen does not rank these two
kernels, so §9 does not promote it to a standing rule. §3d develops what does
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

| | loads | bytes loaded | of which weight bytes | data-dependent branches |
|---|---|---|---|---|
| stock gate/up | 9 | 72 | 64 | 0 |
| bexp gate/up | 19 (**2.11x**) | 64 (**0.89x**) | 56 (**0.875x**) | **8** |
| stock down | 5 | 40 | 32 | 0 |
| bexp down | 13 (**2.60x**) | 36 (**0.90x**) | 28 (**0.875x**) | **0** |

The "bytes loaded" column includes the 8-byte activation load that both kernels
in a pair issue identically; the "weight bytes" column strips it out. These are
*issued* per-thread load bytes, and on that axis the two planes are compacted by
exactly the same factor, 0.875. That equality is a coincidence of two different
mechanisms, and it is worth separating from the DRAM axis:

| | stored weight bytes | vs stock | issued weight bytes/K-iter | vs stock |
|---|---|---|---|---|
| gate/up | 51,037,952 | **0.760** | 56 | 0.875 |
| down | 29,362,176 | **0.875** | 28 | 0.875 |

For down the two agree: `d=6` stores 8 payload + 4 deltaLo + 2 deltaHi = 14 bits
per weight, and its 2,048 B of row-major bases are hoisted out of the K loop, so
stored and issued coincide at 14/16 = 0.875. For gate/up they diverge: `d=4`
stores only 8 + 4 = 12 bits per weight, but the `uchar4` base pair is re-loaded
inside the K loop by **every one of the 32 lanes in the simdgroup**
(`LagunaRuntimeModel.swift:8918-8920`, inside `for (uint block …)`), so the
262,144 B of unique base data is issued 32x and the issued figure rises back to
14 bits. Stored gate/up traffic is 12 bits per weight plus bases plus the
444,160 B escape table, i.e. 0.760.

The direction of that gap matters for the argument. **Gate/up removed the larger
share of unique DRAM traffic — 24.0% against down's 12.5% — and still lost far
more time.** Reading the contrast on stored bytes therefore makes the refutation
of the bandwidth ordering stronger, not weaker; reading it on issued bytes makes
the two planes matched. The conclusion below survives either reading.

This table is the useful result of the whole experiment, because it kills three
plausible explanations at once. The byte multiplier does not order the planes on
either axis: it is identical (0.875) on issued weight bytes, and on stored bytes
it *favours* the plane that lost. The
added-op counts are within 1.4x of each other (293.6 vs 209.7 Mop, §3c). The
load-instruction multiplier is actually **worse** for the plane that won (2.60x
for down against 2.11x for gate/up). None of bytes, ops, or load count orders
these two planes the way the measurement does.

Exactly one structural axis does: the eight data-dependent branches. The
compacted gate/up guards every payload load with `if (base == 0xFF)`, once per
row per plane, because `d=4` cannot represent every block's exponent range and
0.66% of blocks escape (§3). The compacted down plane is escape-free by
construction, so all thirteen of its loads are unconditional.

The cost is very unlikely to be divergence — at 1735/262144 the branch is
essentially uniform across any simdgroup. The candidate mechanism is **loss of
memory-level parallelism through a load-to-branch dependency**. Concretely, in
`LagunaRuntimeModel.swift:8922-8942`:

- The branch *condition* is `gate_bases[row] == 0xFF`, a lane of the `uchar4`
  `gate_bases` value loaded from `bases` at the top of the same loop iteration
  (line 8919). The condition is therefore not known until that load returns.
- The *not-taken* (common) side loads `payload + gate_row * in_vec_size +
  column`. That address is loop-invariant arithmetic and does not depend on any
  value loaded in this iteration.
- The *taken* (escape) side loads `escapes + uint(gd) * block_width +
  escape_column`, whose address depends on `gd`, the delta value loaded two
  lines earlier.

So the payload load itself is cheap to address, but it is gated behind a branch
that cannot resolve until the `bases` load lands, and the compiler cannot
if-convert the branch away because the alternative side's address is itself
load-dependent (and speculating it would read out of the escape table at an
arbitrary offset). The result is a per-iteration chain `bases load -> branch
resolve -> payload load` where the down kernel has `-> payload load` issued
immediately. Eight such chains per iteration is the one structural difference
that runs the right way.

This is a source-level argument, not a counter measurement, and it is stated as
the leading hypothesis rather than a demonstrated fact. Three confounds survive
it: gate/up uses 512-thread groups against down's 128, runs 16 loop trips
against down's 64, and keeps 12 live accumulators against down's 8. §9 gives
the experiment that would separate them, and it is cheap: the hypothesis
predicts that an **escape-free** gate/up plane converts at roughly the down
plane's efficiency, while the confounds predict it stays negative.

## 4. Equivalence and correctness

Both preregistered correctness gates (`:431-433`) were run on the shipped
candidate commit `6842946` with both planes at their default-on setting.

### 4.1 The 64-step drift tripwire — PASS

`./benchmark.sh --local-iterate`, job `b5c6d4cb-5d38-4c8a-81bc-525a686e832d`,
exit 0, 87.5 s wall.

| field | value |
|---|---|
| `max_abs_diff` | **0** |
| `passed_correctness` | **true** |
| `passed` (document root) | **true** |
| `first_failing_case` / `_layer` / `_step` | null / null / null |
| `checked_steps` | 130 (`decode_steps` 128, `repeats` 1) |
| `num_layers` | 40 |
| `golden_hash` | `b9509697c08a2cf3c2943a85f0b76e39c485c441794690fa76835b40a58d7a63` |
| `harness_hash` | `12fef70c6f5a217728f6056c8910cacfda51480edac44726173df027636ef943` |
| `weights_hash` | `aff994300573c5e8589563fc9ff57cdcfb1ef9b49e14898be290a75a6b294b3d` |
| `commit` | `6842946` |
| `peak_ram_gb` | 21 |
| `timestamp` | `2026-08-09T10:54:45Z` |

The thermal gate passed twice on the way in (39.1 °C, then 38.2 °C). Both
planes are confirmed live in the startup notes: `narrow-scales built
block-exponent: dense gate/up` and the matching `dense down` note. This is the
assignment's `max_abs_diff = 0` clause and it is met.

The harness also reprints the token stream; it is identical to the golden, which
is the same statement the ladder makes 24 times over with the
`082682744836a553` hash (§2.5). The two are independent: the tripwire checks
against the organizer's stored golden, the ladder checks self-consistency across
rungs.

### 4.2 Speed fields from the same run, and why they are only directional

| | stored baseline | this candidate | change |
|---|---|---|---|
| prefill s/token | 0.001126 | 0.001125 | −0.1 % |
| decode s/token | 0.012946 | **0.013015** | **+0.5 % slower** |
| est. local score | 0.7954 | 0.7923 | −0.4 % |

The stored file is `score.local-iterate.baseline.json`, commit `ede561b`,
timestamp `2026-08-06T02:29:13Z`. It shares this run's `golden_hash` and
`weights_hash` but **not** its `harness_hash` (`56ba8b02…` versus `12fef70c…`),
and it was taken three days earlier on a different thermal history. It is
therefore an *unmatched* baseline: the correct reading is that its decode
number is consistent in sign and rough magnitude with the ladder's matched
+0.75 %/step regression (§2.1, paired blocked estimator), not that it
independently measures it. The
ladder is the estimator; this is a coarse cross-check that happens to agree.

Both runs price their speedups against the same pinned official-runner
constants (`baseline_decode_seconds_per_token` 0.01385621216015625,
`baseline_prefill_seconds_per_token` 0.00036751938916015626), so
`passed_prefill_speedup_floor` is **false** in *both* — the stored base fails it
too, at prefill speedup 0.32644 against my 0.32658. That floor failure is a
property of running a pinned M5 constant on a 20-core M4 Pro, not a property of
this change. `passed_decode_speedup_floor` is true in both (1.07032 stored,
1.06463 candidate).

### 4.3 The upstream-equivalence oracle — exact on decode, pre-existing host divergence on prefill

`bash research/run_upstream_equivalence.sh`, job
`e0a50587-9cb3-46d3-a922-cfffa062ba41`, exit 1, 73 s.

- All **8 decode steps** report `maximumAbsoluteLogitError = 0`. Exact.
- The **512-token prefill** reports `maximumAbsoluteLogitError = 0.125`, mean
  `0.011933609`, with `runtimeToken == upstreamToken == 5991` (the argmax is
  unchanged; the divergence is sub-token).
- `EQUIVALENCE_EXACT_STEPS=8`, `EQUIVALENCE_EXIT=1`. The non-zero exit is raised
  by the prefill assertion at `LagunaCorrectnessTests.swift:249`.

A non-zero exit on a preregistered gate needs to be attributed, not explained
away, so I ran a control that isolates my change from the host.

**Control:** `bash research/fern_r97_equivalence_control.sh` (job
`6b5ba65f-96b8-4e00-b848-38137bc2239b`, exit 1, 16 s) is the identical test with
`DARKBLOOM_DENSE_BEXP_GATE_UP=0` and `DARKBLOOM_DENSE_BEXP_DOWN=0`, i.e. both
planes forced back to stock BF16 on the same binary. Its report is
**bit-identical in every field**: prefill `maximumAbsoluteLogitError = 0.125`,
mean `0.011933609`, token 5991; all 8 decode steps exactly 0;
`EQUIVALENCE_EXACT_STEPS=8`; same exit 1.

So the prefill divergence is present with my change disabled and identical with
it enabled. **Zero of it is attributable to this experiment.** Two independent
facts corroborate that:

1. `LagunaRuntimeLayers.swift:316` guards the fused dense path with
   `guard x.dim(1) == 1`, making both block-exponent planes decode-only. Neither
   can execute during a 512-token prefill, so neither can move a prefill logit.
2. The test is named `lagunaRuntimeMatchesVendoredUpstreamOnM5WhenEnabled`, and
   `agents.md` records that M4 Pro reports Apple GPU generation 16 and does not
   select the `_nax` prefill kernels the ranked M5 uses. A prefill-only
   near-tie divergence on this host is exactly the failure mode that document
   warns about.

I did **not** set `MLXFAST_LOCAL_ALLOW_GOLDEN_DRIFT=1`. The control establishes
the same thing that flag would have asserted, and does it with evidence rather
than an override.

**Reading for the advisor.** On the axis this experiment touches — the decode
path — the oracle is exact, 8/8 steps at zero error, and the tripwire is exact
at `max_abs_diff = 0` over 130 checked tokens. The prefill exit is a host
artefact reproduced on unmodified code. I am reporting it rather than
suppressing it because the ranked M5 is authoritative for near-ties and I
cannot clear a prefill assertion from this host; an M5 rerun would settle it in
73 s. It does not change the verdict, which is NO-GO on speed regardless.

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

Entity `wandb-applied-ai-team`, project `mlxfast-maple`, group **`r97a-stage2`**,
tags `maple`, `student:maple-fern`, `pr525`, `r97-a`, `stage2`, plus one state
tag per run. One run per timed state, all `finished`.

| state | run | id | `dense_mlp_us_per_step` | bytes/step | MB removed | ladder Δ vs base | efficiency |
|---|---|---|---|---|---|---|---|
| base | [`r97a-stage2-base`](https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/0qxy2siw) | `0qxy2siw` | **8226.583** | 100,663,296 | 0 | — | — |
| S2a | [`r97a-stage2-s2a-gate-up`](https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/meyn9djo) | `meyn9djo` | **8296.917** | 84,592,384 | 16.071 | **+69.598** [67.536, 71.575] | **−1.154** |
| S2b | [`r97a-stage2-s2b-gate-up-plus-down`](https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/0us1weqj) | `0us1weqj` | **8288.854** | 80,400,128 | 20.263 | **+61.962** [60.166, 63.744] | **−0.814** |

`ladder_resolved` is `true` for both candidate states. Sign convention: the
logged `ladder_delta_us` is candidate minus base, so **positive is slower**;
`ladder_saved_us` is its negation and is negative for both, i.e. nothing was
saved. `conversion_efficiency` is `ladder_saved_us` divided by the
preregistered prediction (60.3 µs for S2a, 76.1 µs for S2b).

Every run carries `token_stream_hashes = ["082682744836a553"]` and
`teacher_forced_mismatches = 0`, so the bit-exactness claim is visible on the
runs themselves and not only in this document. Each run also logs a `steps`
table (6277, 6277 and 6282 post-drop timed steps respectively) so the
distributions can be re-examined without the raw files.

The full analysis set is attached to the S2b run as artifact
**`r97a-stage2-raw:v1`** (26 files, type `timing`): `ladder/p00..p11.json` (the
12 raw ladder process files), `ladder/ladder.json`,
`ladder/ladder_placebo.json`, `ladder/decompose.json`, `perrun/p00..p07.json`
(the 8 raw per-run process files), and `perrun/perrun01.json`, `perrun02.json`,
`perrun12.json`. Every number in §2 can be recomputed from `v1` alone with the
§7 commands. `v0` is an incomplete earlier upload written by the logger's own
default file list (15 files: the ladder processes, `ladder.json` and two per-run
JSONs); `v1` supersedes it and is what `:latest` resolves to. All runs
additionally carry the §2–§5 supporting scalars as summary keys —
`decompose_d1_us_gate_up` (+69.465, CI [67.666, 71.145]),
`decompose_d2_us_down` (−7.662, CI [−9.839, −5.387]),
`decompose_byte_value_us_per_mb` (−7.861),
`decompose_op_cost_us_per_mop` (−0.1937),
`perrun_down_marginal_us` (−7.980, CI [−18.112, −0.873]),
`prereg_placebo_k1_us` (+0.14) and `prereg_placebo_k2_us` (+0.79),
`escapes_gate_up` (1735 of 262144) and `escapes_down` (0 of 2048),
`growth_bytes` (26,383), `local_iterate_max_abs_diff` (0),
`equivalence_exact_decode_steps` (8), and `verdict` (`NO-GO`).

Note that the three runs share one physical session; they are three states of a
single interleaved ladder, not three independent training runs. The per-run
`dense_mlp_us_per_step` values are unpaired medians and differ slightly from the
paired ladder contrasts, which are the estimator (§2.1).

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

Analysis. The preregistered analyser produces the §2.1 headline rows:

```bash
python3 research/fern_r93_ladder.py '/tmp/r97/ladder/p*.json' \
  --block 6 --drop-steps 24 --mad-mult 8 --bootstrap 4000 --seed 97 \
  --json-out /tmp/r97/ladder/ladder.json
```

The headline run above reports `"placebo": false` because it was not asked to
split the placebo arm out; that is a second invocation of the same preregistered
analyser, and it is the source of the §2.2 placebo numbers:

```bash
python3 research/fern_r93_ladder.py '/tmp/r97/ladder/p*.json' \
  --block 6 --drop-steps 24 --mad-mult 8 --bootstrap 4000 --seed 97 \
  --placebo --json-out /tmp/r97/ladder/ladder_placebo.json
```

Note `--placebo`, not `--placebo-assign`. `--placebo` selects the blocks the
probe already marked as placebo (rung 0 on every step) and contrasts them by
slot label. `--placebo-assign` instead imposes a fresh random slot order on
*all* blocks, which on a three-rung file mixes real rung effects into the null
arm and does not terminate cleanly; it is the wrong flag for this design.

The decomposition analyser produces the down marginal and the byte/op fit, and
independently reproduces the placebo arm, in one pass:

```bash
python3 research/fern_r97_decompose.py '/tmp/r97/ladder/p*.json' \
  --drop-steps 24 --bootstrap 4000 --seed 97 \
  --json-out /tmp/r97/ladder/decompose.json
```

The per-run analyser must be told which two depths to pair; its defaults
(`--lo 0 --hi 240`) match no pair in a three-rung file. Depths are `rung * 40`,
so the three §2.5 rows are three separate invocations:

```bash
python3 research/fern_r93_perrun.py '/tmp/r97/perrun/p*.json' \
  --label-contains perrun --drop-steps 24 --bootstrap 4000 --seed 97 \
  --lo 0 --hi 40  --json-out /tmp/r97/perrun/perrun01.json   # S2a − base
python3 research/fern_r93_perrun.py '/tmp/r97/perrun/p*.json' \
  --label-contains perrun --drop-steps 24 --bootstrap 4000 --seed 97 \
  --lo 0 --hi 80  --json-out /tmp/r97/perrun/perrun02.json   # S2b − base
python3 research/fern_r93_perrun.py '/tmp/r97/perrun/p*.json' \
  --label-contains perrun --drop-steps 24 --bootstrap 4000 --seed 97 \
  --lo 40 --hi 80 --json-out /tmp/r97/perrun/perrun12.json   # down marginal
```

Rung-control verification (§3b) — three single-rung processes with per-dispatch
logging on, no timing claim attached:

```bash
bash research/fern_r97_ladder_session.sh OUT=/tmp/r97/rungcheck SKIP_BUILD=1 \
  NARROW_LOG=1 P=3 R=1 S=32 SCHEDULE="const:0;const:1;const:2"
```

Smoke check of the three states plus the escape census (48 steps):

```bash
OUT=/tmp/r97/smoke STEPS=48 bash research/fern_r97_smoke.sh
```

Equivalence oracle, candidate and stock-plane control (§4):

```bash
bash research/run_upstream_equivalence.sh
bash research/fern_r97_equivalence_control.sh
```

W&B publication (§6) — one run per rung, raw files attached to the S2b run:

```bash
python3 research/fern_r97_wandb_log.py \
  --ladder /tmp/r97/ladder/ladder.json \
  --perrun /tmp/r97/perrun/perrun01.json /tmp/r97/perrun/perrun02.json \
  --records '/tmp/r97/ladder/p*.json' --group r97a-stage2 \
  --extra "$(cat /tmp/r97/extra.json)"
```

`--extra` carries the §2.4, §3, §4 and §5 scalars that the logger does not
derive itself. The logger's built-in artifact list omits `ladder_placebo.json`,
`decompose.json`, the per-run process files and `perrun12.json`; `v1` of
`r97a-stage2-raw` was logged separately to the same run id to complete it.

`NARROW_LOG=1` turns on per-dispatch logging. It takes an `NSLock` per dispatch.
It was **off** for both estimator sessions that carry a timing verdict (the
ladder and the per-run arm) and **on** for the two diagnostic sessions in §3b
and §3 whose numbers are explicitly not used as measurements (§2.2, bullet 4).

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
4. **An unpreregistered second analyser was written, and two headline quantities
   come from it.** The preregistration (`:353`, `:361-362`) names
   `fern_r93_ladder.py` as *the* analyser and places the placebo gate on it. I
   additionally wrote `research/fern_r97_decompose.py` to obtain the down
   marginal `d2` and the two-parameter byte/op fit, which the preregistered
   analyser does not produce. Two consequences, both recorded rather than papered
   over:
   - The §2.1 down marginal (−7.66) and the whole of §2.4 rest on the new script.
     They are cross-checked by the independent per-run session (§2.5, −7.98 from
     `fern_r93_perrun.py`), which is a different design analysed by a different,
     pre-existing tool.
   - The preregistered placebo gate is nevertheless satisfied *by the
     preregistered analyser*: `fern_r93_ladder.py --placebo` was run on the same
     session and returns `+0.14` and `+0.79 us`, both unresolved (§2.2, §7). I
     did not discover the right invocation until after the decompose script
     already had the placebo numbers, which is why both appear.
   A placebo-analysis bug in the new script was also found and fixed during
   analysis: it initially keyed placebo cells on the *executed* rung, and since a
   placebo block executes rung 0 on every step this collapsed every placebo block
   to one level and reported `placebo_blocks = 0`. Keying on the *assigned* slot
   fixes it; the fix is in the committed script and predates any conclusion drawn
   from the placebo arm. `fern_r93_ladder.py` was never affected.
5. **§3d is exploratory and was not preregistered.** It is a source-level audit
   written after seeing the sign, and it is labelled as the leading hypothesis
   rather than a demonstrated mechanism.
6. **The assigned estimator's hinge model is reported but unused.** `fern_r93_ladder.py`
   prints an `EXPLORATORY hinge` fit; it was motivated by an earlier smoke run,
   is not preregistered here, and no conclusion in this document rests on it.
7. **R2 was not attempted**, per the assignment scoping R97-A to R1 only.
8. **The preregistered early-stop rule was not honoured.** The preregistration
   (`:454-456`) says: "if S2a alone converts at efficiency < 0.5, stop there. Do
   not build S2b." S2a converts at **−1.154**, so by the letter of that rule S2b
   should not have been built. It was, and it was timed.

   The rule was unimplementable as written, and that is my error for writing it.
   The assignment requires "three timed states (base, S2a, S2b) in one blocked
   randomised ladder", and the three-rung ladder measures all three states inside
   a single session from a single binary. S2a's efficiency therefore does not
   exist until S2b has already been built and run; honouring the stop rule would
   have required an extra, separate two-state session first, which the
   preregistration did not budget and the assignment did not ask for. The earliest
   S2a-only signal available was the 48-step smoke run (§2.2), and that is
   explicitly not an estimator.

   I did not stop after seeing the smoke sign either, and I would make the same
   call again: S2b is not "more of S2a", it is a second and structurally different
   plane, and its marginal contrast is the only thing in this experiment that
   distinguishes "bytes do not pay on this path" from "this particular kernel
   shape does not pay". Without it there is no §2.4 refutation, no §3d
   discriminator, and no §9.4 follow-up worth running. But a reader should treat
   §2.4 and §3d as post-hoc analysis of data the preregistration told me not to
   collect, and weight them accordingly.
9. **Two mechanical renamings in the per-run analysis.** `fern_r93_perrun.py`
   pairs on the probe's *depth* field, which is `rung * 40`, so the three rung
   pairs (0,1), (0,2), (1,2) are invoked as `--lo/--hi` 0/40, 0/80 and 40/80. The
   preregistration (`:368-371`) names only two per-run pairings, (0,1) and (0,2);
   I ran the third, (1,2), because the down marginal is the contrast most at risk
   of being a ladder ordering artefact and it is free once the session exists.

## 9. Verdict against the go/no-go bar

### 9.1 Bar by bar

The assignment's GO bar had five conjunctive clauses. Two pass, two fail, one
passes with a caveat recorded below, and one of the two explicit NO-GO triggers
fired.

| # | Bar clause | Required | Measured | Verdict |
|---|---|---|---|---|
| 1 | S2b removes census-verified traffic | ≥ 19.0 MB/step | 20.263 MB/step (§2.3) | **PASS** |
| 2 | Ladder shows S2b faster than base | ≥ 55 µs/step faster, 95 % CI excludes 0 | **+61.96 µs/step slower**, CI [+60.17, +63.74] | **FAIL** |
| 3 | Conversion efficiency (measured ÷ 76.1 µs) | ≥ 0.72 | **−0.814** | **FAIL** |
| 4 | Correctness | `max_abs_diff = 0` on the 64-step drift tripwire; `research/run_upstream_equivalence.sh` green with a verified nonzero test count; identical single token-stream hash for base, S2a and S2b | tripwire `max_abs_diff = 0`, `passed_correctness = true` over 130 checked tokens (§4.1); all 12 ladder processes hash `082682744836a553` with 0 teacher-forced mismatches (§2.1, §2.5); oracle exact on all 8 decode steps but **exit 1** on the 512-token prefill assertion (§4.3) | **PASS with caveat** |
| 5 | Submitted-surface growth | ≤ 60,000 B | 26,383 B (§5) | **PASS** |

Clause 4 has three sub-requirements and only two are unconditionally green. The
oracle suite did **not** exit 0. §4.3 attributes that exit to the host rather
than to this change, using a control in which both planes run stock code and the
suite emits a bit-identical failure in every field — so the attributable
contribution of this branch to the prefill divergence is zero, and every decode
step the oracle checked is exact. That attribution is sound but it is an
attribution, not a green gate: formally clearing clause 4 needs a rerun on the
ranked M5. Since clauses 2 and 3 fail outright and the efficiency NO-GO trigger
fired, this caveat does not change the verdict, and it is recorded here rather
than resolved because resolving it would cost an M5 run on a branch that will
not be promoted.

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

The result is not a null: it is a *resolved* negative, and the NO-GO branch of
the preregistration explicitly anticipated it as "a publishable measurement that
the layer-0 dense stream is not purely bandwidth-limited at decode, i.e. that
this kernel sits above the ALU knee"
(`research/fern-r97-stage2-preregistration.md:443-446`). The publishable content
is §2.4 and §3d. Because the mechanism story
is the part most likely to be over-read, each of the four claims below is
tagged by how it was established — **measured** (a contrast, CI, census, or
static count), **inferred by elimination** (measured facts rule out the
alternatives), or **speculation** (a plausible account with no direct evidence
on this host).

1. **The byte claim was met.** *(measured)* The census (§3) confirms the preregistered
   footprint exactly — 1735/262144 gate/up escapes, 0/2048 down escapes — so
   20.263 MB/step really does leave the memory system. The failure is entirely
   in conversion, not in the compaction.
2. **The additive byte + ALU model is refuted.** *(measured)* Fitting the two timed contrasts
   to `bytes` and `ops` yields `byte_value = −7.861 µs/MB`
   (CI [−8.294, −7.406]) and `op_cost = −0.1937 µs/Mop`
   (CI [−0.2126, −0.1739]). Both coefficients are negative. A negative byte
   value is physically impossible under the model, so the model — not the
   measurement — is what broke. Removing bytes from the *fused gate/up* kernel
   at this arithmetic intensity does not buy time on this host; the down plane
   (item 3) shows the same removal can still pay elsewhere, just nowhere near
   the bandwidth-model price.
3. **The two planes disagree in the informative direction.** *(measured)* Gate/up costs
   +69.60 µs (CI [+67.54, +71.58]) on the preregistered analyser — +69.47
   (CI [+67.67, +71.15]) on the unpreregistered decompose fit, §8 dev. 4 —
   while the *marginal* down plane returns
   −7.66 µs (CI [−9.84, −5.39]) — the only positive conversion in the
   experiment, 0.485. Neither bytes removed (16.07 vs 4.19 MB), added integer
   ops (293.6 vs 209.7 Mop, only 1.4× apart), nor load count (2.11× vs 2.60×,
   *worse* for the plane that won) orders the two planes correctly (§3c, §3d).
4. **The surviving discriminator is structural, not volumetric.** This claim has
   three layers and they are not equally supported:
   - *(measured)* The volumetric axes do not order the planes. Bytes removed,
     added integer ops, and load-count inflation are all static counts from §3c,
     and none of them puts gate/up on the losing side. The escape census is 1735
     in 262144 blocks for gate/up and 0 in 2048 for down (§3), and the two
     kernels' geometry — 512 vs 128 threads per group, 16 vs 64 loop trips, 12
     vs 8 live accumulators, conditional vs unconditional addressing — is read
     directly from the sources cited in §3d.
   - *(inferred by elimination)* Of the axes I audited, the `if (base == 0xFF)`
     escape branch is the only one that orders the planes in the observed
     direction. This is an elimination argument over a finite audited list, so
     it is only as strong as that list is complete; §3d names three confounds
     (threadgroup width, trip count, accumulator count) that it does **not**
     eliminate.
   - *(speculation)* The account of *why* the branch costs what it does — that
     the penalty is lost memory-level parallelism from a dependent-address
     chain (`bases` load → branch resolve → payload load) rather than warp
     divergence, since 1735 escapes in 262144 blocks is near-uniformly rare — is
     a source-level story with no counter data behind it on this host. Nothing
     in this experiment measures stall cycles, occupancy, or issued loads.
     §9.4 items 1 and 3 are the two experiments that would test it.

### 9.3 Confidence and transfer

The instrument is sound (§2.2): 3112 blocks with 0.4 % censoring, carryover
coefficient +0.0101 µs/dispatch with CI [−0.0161, +0.0375] spanning zero, and
both placebo arms centred on zero (d1 +0.61 CI [−3.54, +4.95]; d2 +0.66
CI [−2.57, +4.03]). The rung-control run (§3b) proves the mmap control word is
read live and that each rung dispatches exactly the intended kernels.

This host is an M4 Pro (Apple GPU generation 16), not the ranked M5 Max, so per
`agents.md` the *magnitude* does not transfer and I make no claim about the
number the M5 would print. What transfers is the size of the gap relative to
the instrument's resolution.

The measured regression is +61.96 µs/step against a base of 8226.6 µs/step —
0.75 %/step — with a 95 % CI half-width of 1.78 µs. The gap between the observed
result and the bar's requirement is even larger: the bar wanted ≥ 55 µs
*faster*, so the candidate misses by roughly 117 µs, about 66 CI half-widths.
An M5 would have to change the sign of a contrast that is resolved to two
significant figures on this host, and move it by about 66 CI half-widths
(≈130 standard errors, se 0.92 µs), for the verdict to flip. Both timed states
are on the wrong side, and the switching-free per-run session (§2.5) reproduces
all three contrasts with a completely different schedule, so this is not a
ladder-ordering artefact either.

I deliberately do **not** rest this argument on the fitted `byte_value` of
−7.861 µs/MB or the implied −127 GB/s. Those are outputs of the very model §2.4
refutes; quoting a refuted model's coefficient as evidence would be circular.
The robust statement is the one above: the contrast itself, not any coefficient
derived from it.

I also do not have a citation for the M4 Pro versus M5 Max bandwidth-per-core
ratio and have not measured it, so I am not going to put a number on it. The
argument does not need one — no plausible per-core bandwidth ratio between two
Apple Silicon generations turns a −0.814 conversion efficiency into +0.72, since
that requires the change to stop costing time and start saving it. I would not
spend M5 time on this candidate.

**Weakest sufficient hypothesis (post-hoc framing).** `senpai/program.md`
gained a "weakest sufficient hypotheses" section on this branch after the
measurements were taken, so this paragraph is interpretation added afterwards,
not a preregistered claim. Applied here it separates two hypotheses that both
fit the same three contrasts:

- **Weak (broad extension, few commitments):** at decode on the layer-0 dense
  shapes, a bit-exact transform that trades DRAM bytes for per-element integer
  unpack work is not reliably profitable, and its outcome is dominated by
  kernel-structural effects that neither bytes removed nor added op counts
  predict. This commits to nothing about branches, escapes, occupancy, block
  width, or GPU generation, and it already accounts for all three contrasts,
  including the fact that the plane with *more* ops per byte removed (down,
  50.0) is the one that won while gate/up (18.3) lost badly (§3c).
- **Strong (narrow extension, extra commitments):** the specific penalty is the
  `if (base == 0xFF)` escape branch's dependent-address chain. This is §9.2
  item 4's *(speculation)* layer and is the only one that names a mechanism.

The weak hypothesis is sufficient for the NO-GO and transfers to every future
compaction proposal on this kernel family; the strong one buys a named fix but
costs an unsupported commitment. That distinction is what makes §9.4 item 1 the
first follow-up: its two readings fall on opposite sides of the split. A neutral
`d=8` rung falsifies the weak hypothesis and leaves the strong one standing with
a named, fixable cause; a still-slow `d=8` rung — which removes no bytes at all —
confirms the weak one directly. §9.4 item 3 is the independent check on the same
question, since memory-stall and issued-load counters say whether this kernel is
memory- or issue-limited without relying on either story. Those two, not another
byte-removal rung, are what should decide whether any further compaction here is
worth a GPU hour.

### 9.4 Suggested follow-ups (not implemented)

Listed in decreasing information-per-GPU-hour. None of these is in scope for
this assignment.

1. **A `d=8` branchless gate/up rung — the decisive control.** Widen the gate/up
   delta field to a full byte at `B=128`. That removes escapes by construction
   (any 8-bit delta covers the full exponent range within a block), so the
   `if (base == 0xFF)` branch and its hypothesized dependent-address stall
   disappear, while
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
   argument in §3d is source-level and leaves three confounds live (gate/up
   versus down in each case): threadgroup 512 vs 128, trip count 16 vs 64, and
   12 vs 8 live accumulators. Counter data
   on occupancy, memory-stall cycles, and issued-load counts would collapse
   those three and confirm or kill the memory-level-parallelism explanation
   directly, rather than by elimination.
4. **Retarget the technique at a plane with the down plane's shape.** Down was
   the only plane that converted (+0.485). If block-exponent compaction is worth
   revisiting anywhere, it is on unconditional, escape-free, low-trip-count,
   low-accumulator kernels — not on wide fused gate/up projections. This is a
   redirection of the idea rather than a repair of this candidate.
