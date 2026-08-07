# Persistent grid-stride QKV (PR #309)

**Student:** maple-nezuko · **Assignment:** `maple-2026-08-07q-persistent-gridstride-qkv` r1
**Base:** `63ab67c888e1892086b7b5b623de4dd0ebe68c90`
**W&B:** [`b624rd0b`](https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/b624rd0b)
(arm means, all 10 contrasts, the ladder, Stage 0 validity gates, and the raw
per-step traces as artifact `pr309-persistent-gridstride-qkv`)

**Decision: KILL** — see §8.

**Headline.** The candidate is `+63.2 ± 11.0 µs/step` (t = 5.76, n = 8/arm)
*slower* than the stock anchor and `+96.9 µs/step` slower than the merged PR #48
arm it was meant to extend. Both halves of the assignment's cost model check
out — the redundant reduction is real and `T=128` does amortise it — but
abandoning full grid coverage costs `+174.9 ± 11.0 µs/step`, measured with the
fold switched off on both sides, which is 5x the amortisation it buys. A
threadgroup-count ladder (§6.3) shows that penalty is flat across an 8x range of
grid coarseness and then cliffs by `+917 µs` once the grid drops below the GPU
core count, so no choice of `T` rescues the idea. The M5's usable `T` set is
strictly smaller than this host's (§9), so this will not reverse on the ranked
machine.

## 1. Hypothesis

PR #298 established that folding the RMSNorm reduction into the decode QKV
kernel refunds the dispatch it removes (`N - 0 = -55.0 µs/step`), but that the
fold itself is paid `rows / (T*S)` times over because every threadgroup redoes
the same 2048-element reduction. At the stock geometry that redundancy factor
is 640 (h64) and 512 (h48).

The proposal: make the grid *persistent*. Launch a fixed `T` threadgroups, give
each simdgroup `rows / (T*S)` output rows via a grid-stride loop, and hoist the
folded-norm prologue **outside** that loop. The redundant reduction is then paid
`T*S` times instead of `rows` times — a 5x cut at `T=128, S=16` — while the
dispatch refund is retained.

Predicted from #298's redundancy exponent (≈0.64): ≈ **−106 µs/step** ≈ 1.6% of
decode score.

**Result: the prediction is wrong, and wrong in an instructive way.** The
persistent grid introduces a cost that is larger than the reduction it saves.

## 2. What was built

All in `Sources/MLXFastModel/LagunaRuntimeModel.swift`, behind env knobs that
default to off (research-only tip; the patch is not proposed for promotion).

| knob | env | values |
|---|---|---|
| `lagunaDecodeNVFP4QKVTotalThreadgroups` | `DARKBLOOM_DECODE_NVFP4_QKV_TOTAL_THREADGROUPS` | `0` (off/full coverage), `16,32,64,128,256,512,1024` |
| `lagunaDecodeNVFP4QKVRowFaultInject` | `DARKBLOOM_DECODE_NVFP4_QKV_ROW_FAULT` | `1` = corrupt store row (negative control) |
| geometry log | `DARKBLOOM_DECODE_NVFP4_QKV_GEOMETRY_LOG` | `1` |

`lagunaDecodeNVFP4QKVLaneMajorSource` gains a grid-stride row loop:

```metal
constexpr uint total_simdgroups = T*S;
constexpr uint rows_per_simdgroup = rows / (T*S);
uint global_sg = tile * num_simdgroups + simd_gid;
for (uint row_step = 0; row_step < rows_per_simdgroup; ++row_step) {
uint out_row = global_sg + row_step * total_simdgroups;
  ... unchanged per-row body ...
}
```

The folded-norm prologue stays above the loop. Nothing else moved: `x_thread`,
`sb` and `result` stay inside the loop, so register pressure is unchanged and
there is deliberately no hoisting or software pipelining.

### Divisibility

Both head shapes must divide exactly — a tail threadgroup would change the
reduction participation set and break bit-exactness. `rows = (heads + 16)*128`,
so h64 sliding = 10240 and h48 full = 8192. At `S=16`:

`T*16 | 10240` and `T*16 | 8192` ⇒ `T | 640` and `T | 512` ⇒ **`T | 128`**.

Valid `T ∈ {16, 32, 64, 128}`. `T=256` is invalid for h64 (10240/4096 = 2.5) and
is guarded by a `precondition` in the kernel builder.

## 3. Bit-exactness argument

Each output row's dot product stays entirely within one simdgroup, with an
unchanged lane→K mapping and an unchanged accumulation order, for any `T`.
Only *which* simdgroup computes a given row changes. So the matmul is
bit-identical by construction.

The one genuine numerical change is the folded-norm reduction's participation
set (64 → 512 threads), which is inherited from #298/#300 and licensed there.

Note the corollary that invalidated the first negative control (§5).

## 4. Threadgroup and occupancy accounting (M4 Pro, 20 GPU cores, `low` profile)

Measured from `DARKBLOOM_DECODE_NVFP4_QKV_GEOMETRY_LOG`:

| arm | S | fuse | T req | h64 TGs | h48 TGs | thr/TG | rows/sg h64 | rows/sg h48 | tg bytes |
|---|---|---|---|---|---|---|---|---|---|
| `a0` | 2 | 0 | 0 | 5120 | 4096 | 64 | 1 | 1 | 0 |
| `G640` | 16 | 0 | 0 | 640 | 512 | 512 | 1 | 1 | 0 |
| `R640` | 16 | 3 | 0 | 640 | 512 | 512 | 1 | 1 | 4228 |
| `N640` | 16 | 1 | 0 | 640 | 512 | 512 | 1 | 1 | 4228 |
| `G128` | 16 | 0 | 128 | 128 | 128 | 512 | 5 | 4 | 0 |
| `R128` | 16 | 3 | 128 | 128 | 128 | 512 | 5 | 4 | 4228 |
| `N128` | 16 | 1 | 128 | 128 | 128 | 512 | 5 | 4 | 4228 |

Threadgroup memory is 4228 B with the fold (`local_inv_mean[1]` +
`local_sums[32]` + `bfloat norm_row[2048]`), far under the 32 KB limit, so
occupancy is not threadgroup-memory limited at either geometry.

## 5. Negative controls

Both are mandatory: a stage whose correctness probe cannot fail proves nothing.

**(a) Divisibility hard-fail.** `neg_tg256` (`T=256`, `S=16`) → worker
`exit=1` at kernel construction. The `precondition` is live in Swift `-O`.

**(b) Store-row fault.** *The first attempt was invalid and this is the most
transferable lesson of the stage.* The original fault rotated `out_row` by one.
But `out_row` indexes **both** the weight row read and the `projected[]` store,
so rotating it is a **bijection over the row set** — a pure re-schedule that is
bit-exact by construction. It duly reported `0 divergences`, which I initially
mistook for a broken probe.

The corrected fault offsets the **store index only**
(`projected[(out_row + 1) % rows]`), breaking the read/store correspondence:

| control | geometry | result |
|---|---|---|
| `neg_fault` | `S=16, fuse=1, T=128` | **24 divergences**, first `(0, 509, 405)` |
| `neg_fault_a0` | `S=2, fuse=0, T=0` (reference) | **24 divergences**, first `(0, 509, 405)` |

The probe is therefore sensitive to a wrong QKV output at both the persistent
and the reference geometry. Stage 0 is valid.

`research/persistent-qkv-logs/stage0a-bijective-fault-invalid.log` is retained
deliberately as the record of the invalid control.

## 6. Timing

### 6.1 Stage 0 (n=1/arm, 24 steps, two independent replicates)

Medians are quoted because two replicate runs caught scheduler outliers
(max 29.0 ms, 18.9 ms) that inflate the mean; medians agree to ~5 µs.

| arm | s0a mean | s0b mean | s0a median | s0b median |
|---|---|---|---|---|
| `a0` | 8.206 | 8.214 | 8.152 | 8.155 |
| `G640` | 8.189 | 9.169 | 8.137 | 8.140 |
| `R640` | 8.251 | 8.345 | 8.198 | 8.300 |
| `N640` | 8.176 | 8.168 | 8.107 | 8.107 |
| `G128` | 8.382 | 9.082 | 8.330 | 8.311 |
| `R128` | 8.393 | 8.471 | 8.341 | 8.406 |
| `N128` | 8.215 | 8.925 | 8.155 | 8.215 |

The decisive contrast is `G128 − G640`: both arms are `fuse=0`, so **no norm is
folded in either** and the difference prices the persistent multi-row grid
*alone*, with the reduction-amortisation benefit held at zero.

`G128 − G640 = +193 µs` (s0a medians), `+171 µs` (s0b medians).

The persistent grid is **slower**, and it is slower by more than the entire
fused-norm refund it was supposed to preserve.

### 6.2 ABBA campaign

4 blocks × 14 runs, palindromic arm order, one warm-up run discarded ⇒ 56 timed
runs, **n = 8 per arm**. Each run is 192 decode steps, first 8 dropped, per-run
estimator = upper-5%-trimmed mean of the remaining 184. Two-way (block × arm)
fixed effects: **residual sd 21.9 µs over 46 df, se of every contrast 11.0 µs.**

Arm means:

| arm | S | fuse | T | mean µs/step | sd of run means | within-run sd |
|---|---|---|---|---|---|---|
| `a0` | 2 | 0 | 0 | 8166.9 | 19.3 | 62.3 |
| `G640` | 16 | 0 | 0 | 8160.0 | 9.7 | 42.7 |
| `R640` | 16 | 3 | 0 | 8216.5 | 13.3 | 37.9 |
| `N640` | 16 | 1 | 0 | 8133.2 | 37.5 | 64.0 |
| `G128` | 16 | 0 | 128 | 8334.8 | 21.6 | 51.3 |
| `R128` | 16 | 3 | 128 | 8356.7 | 6.8 | 36.7 |
| `N128` | 16 | 1 | 128 | 8230.1 | 28.3 | 41.8 |

Contrasts (fixed effects; se = 11.0 µs, 46 df throughout):

| contrast | µs/step | t | 95% CI | meaning |
|---|---|---|---|---|
| `G640-a0` | −6.9 | −0.63 | [−28.9, +15.0] | fused geometry alone: free |
| `R640-G640` | +56.5 | 5.15 | [+34.5, +78.4] | redundant reduction at 640 TGs |
| `N640-R640` | −83.3 | −7.59 | [−105.2, −61.3] | dispatch refund at 640 TGs |
| `N640-a0` | −33.7 | −3.07 | [−55.6, −11.8] | PR #48 reproduced on this binary |
| `G128-G640` | **+174.9** | 15.93 | [+152.9, +196.8] | **multi-row confound priced alone** |
| `R128-G128` | +21.9 | 1.99 | [−0.1, +43.8] | redundant reduction amortised 5x |
| `N128-R128` | −126.6 | −11.53 | [−148.5, −104.6] | dispatch refund at 128 TGs |
| `N128-N640` | **+96.9** | 8.83 | [+75.0, +118.9] | **assignment claim refuted** |
| `G128-a0` | +167.9 | 15.30 | [+146.0, +189.9] | persistent geometry vs stock |
| `N128-a0` | **+63.2** | 5.76 | [+41.3, +85.2] | **HEADLINE: candidate is slower** |

Per-block arm means were stable to within ~30 µs across all four blocks; no run
exceeded 4× the median within-run sd, so no block was thermally compromised.

**Estimator robustness.** Re-running the same 56 traces with the trim disabled
(plain mean of the 184 kept steps) moves the headline from +63.2 to +60.7 µs and
`G128-G640` from +174.9 to +176.0, with residual sd 21.6 instead of 21.9. Every
contrast keeps its sign, magnitude and significance, so the conclusion does not
depend on the choice of per-run estimator. Both tables are in
`research/persistent-qkv-logs/abba-campaign-stats.txt` (trimmed) and reproducible
by dropping `--trim 0.05`.

**Reading of the two mechanism terms.** Both halves of the assignment's cost
model are confirmed on their own axis:

- The redundant reduction *is* real and *is* amortised. It costs +56.5 µs at
  640 threadgroups (1 row per simdgroup) and only +21.9 µs at 128 threadgroups
  (5 rows per simdgroup) — a 2.6x reduction, close to the predicted ~+29 µs.
- The fused-norm dispatch refund *is* preserved and in fact grows, from
  −83.3 µs at 640 threadgroups to −126.6 µs at 128.

The hypothesis fails on a term the assignment did not price: the grid geometry
itself. `G128 − G640` is **+174.9 µs with the fold switched off on both sides**,
so it cannot be a fold artefact — it is the pure cost of running the same total
row-work through 128 threadgroups instead of 640. That single term is 5x the
saving it enables (+21.9 → the amortisation is worth only ~34.6 µs) and roughly
2x the entire PR #298/#48 refund it was meant to protect.

Net: `N128 − a0 = +63.2 µs/step`, i.e. the candidate is **0.77% slower** than
stock decode (8166.9 µs/step anchor), and `N128 − N640 = +96.9 µs/step` means it
also destroys the already-merged #48 win rather than adding to it.

### 6.3 Threadgroup-count ladder (mechanism falsification)

The `G128 − G640` penalty is the whole result, so it deserves its own
falsification. `S=16` admits `T ∈ {16, 32, 64, 128}` (§2 divisibility), and
**total row-work is identical at every rung** — only the grid shape changes. A
pure per-row loop-overhead explanation therefore predicts a *flat* ladder; a
scheduling explanation predicts structure. Ten runs, 192 steps each, fold off
everywhere, palindromic order `G640 G128 G64 G32 G16 | G16 G32 G64 G128 G640`
so the anchor brackets the session.

| T | TGs | TG/core (20) | rows/sg (h64) | median A | median B | mean | Δ vs full coverage |
|---|---|---|---|---|---|---|---|
| full | 640 | 32 | 1 | 8.159 | 8.163 | 8.161 | — |
| 128 | 128 | 6.4 | 5 | 8.340 | 8.346 | 8.343 | **+182 µs** |
| 64 | 64 | 3.2 | 10 | 8.349 | 8.363 | 8.356 | **+195 µs** |
| 32 | 32 | 1.6 | 20 | 8.317 | 8.311 | 8.314 | **+153 µs** |
| 16 | 16 | **0.8** | 40 | 9.076 | 9.080 | 9.078 | **+917 µs** |

Drift control: the two `G640` anchors, run first and last, differ by 4 µs, so
the session had no thermal drift. Replicate pairs differ by ≤ 14 µs while the
effects are 153–917 µs. All ten runs reported `0 divergences`.

Cross-session replication: the ladder's full-coverage → `T=128` step is
**+182 µs**, against the ABBA campaign's `G128 − G640 = +174.9 ± 11.0 µs`
measured on a different day. Inside one standard error.

**Three things follow.**

1. **Per-row loop overhead is ruled out.** Total row-work is constant across
   rungs, and the ladder is *non-monotone* in rows/simdgroup: `T=32`
   (20 rows/sg) is 42 µs **faster** than `T=64` (10 rows/sg). Overhead that
   scaled with the row loop could not produce that ordering.
2. **The penalty is close to a step function, not a gradient.** For every rung
   that still has at least one threadgroup per core, the cost of abandoning
   full coverage sits on a ~+150…+195 µs plateau — an 8x change in grid
   coarseness moves it by 42 µs. Whatever full coverage buys, it is bought all
   at once and is not recovered by tuning `T`.
3. **There is a hard cliff exactly at the core count.** `T=16` on a 20-core
   part leaves 4 cores idle for the entire kernel and costs **+917 µs**, 5x the
   plateau and 4.7x more than `T=32`. The boundary lands precisely where the
   grid can no longer occupy every core, which is direct evidence that the
   dominant term is occupancy/scheduling rather than arithmetic.

## 7. Mechanism

Two things the data settles, and one it does not.

**Settled: the penalty is scheduling, not work.** Per-threadgroup launch cost is
essentially free here — `a0 → G640` removes 4480 TGs/step and moves timing by
`−6.9 ± 11.0 µs`, i.e. nothing. So shrinking the grid buys almost nothing on the
dispatch axis. Meanwhile total row-work, total activation loads, total weight
traffic and total simdgroup reductions are all identical across the §6.3 ladder,
yet the ladder spans 917 µs. The cost therefore lives entirely in how the work
is *scheduled*, not in how much of it there is.

**Settled: occupancy is the dominant term.** The `T=16` cliff is the cleanest
evidence in this report. Sixteen threadgroups on a twenty-core part leaves four
cores idle for the whole kernel, and that alone costs +917 µs — 5x the plateau
that every other rung sits on. Nothing about the kernel body changes at that
rung; only the grid's ability to reach every core does.

**Refuted: my own first explanation.** I initially expected a straggler-wave
tail whose cost scales with threadgroup *lifetime*, since a `T=128` threadgroup
lives 5 rows rather than 1. That model predicts monotone worsening as `T` falls
and lifetimes grow. The ladder says otherwise: `T=32` (20 rows/simdgroup) is
*faster* than `T=64` (10 rows/simdgroup), and the whole `T ∈ {32, 64, 128}`
range is a 42 µs-wide plateau. Tail-lifetime scaling is not what is happening.

**Unresolved: what full coverage actually buys.** The plateau's shape — a
~+170 µs step taken the moment you leave one-row-per-simdgroup, then near
indifference to how coarse you go — looks like the loss of a property that
full coverage has and every persistent configuration lacks equally. The leading
candidate is memory-level parallelism: at full coverage each simdgroup issues
one independent NVFP4 weight stream and the scheduler has 10240 of them to
interleave, whereas persistence serialises the same rows into at most 2048
dependent chains, so far fewer independent loads are in flight per core to hide
weight-fetch latency in a bandwidth-bound GEMV. I did not instrument this, so I
am labelling it a hypothesis rather than a finding. It is testable with a
Metal capture of memory-stall cycles at `G640` vs `G128`, which I did not run.

**Context.** Full-coverage grids are what every production Apple GEMV uses.
MLX's own `qmv` runs 64-thread threadgroups with 8 rows each at full coverage
(`Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/quantized.cpp:255-299`,
`kernels/fp_quantized.h:537-556`). Metal offers no cross-threadgroup
forward-progress guarantee, which is why persistent-CTA idioms common in CUDA
are not used on Apple. The ladder is consistent with that being a considered
choice rather than an oversight.

The redundant-reduction cost model from #298 was therefore correct but
incomplete: it priced the *reduction* work saved and ignored the *scheduling*
cost of the coarser grid required to save it. On this kernel the second term
dominates by 5x.

## 8. Decision: KILL

The mechanism the assignment proposed is real — the reduction *is* redundantly
paid, and `T=128` *does* amortise it — but capturing it requires abandoning
full coverage, and that costs more than the saving. The `G128 − G640`
contrast prices that trade with the fold switched off on both sides:
**+174.9 ± 11.0 µs/step**, versus a redundant-reduction saving of only
**34.6 µs** (`R640−G640 = +56.5` falling to `R128−G128 = +21.9`). The grid
penalty is 5x the saving it enables.

Headline: the candidate `N128` is **+63.2 ± 11.0 µs/step (t = 5.76, 95% CI
[+41.3, +85.2])** *slower* than the stock `a0` anchor — 0.77% of decode — and
**+96.9 µs/step slower than the already-merged PR #48 arm it was meant to
extend**. There is no configuration of this idea worth submitting: the sign is
wrong by ~6 standard errors and the effect is ~1.2x the ranked M5's ~80 µs/step
resolution floor, so it is not a measurement artefact either.

This is unlikely to reverse on the ranked M5 Max, and the M5 geometry is
*worse*, not better (§9).

## 9. M4 → M5 transfer

This host is M4 Pro / 20 GPU cores / Apple GPU generation 16 / `low` memory
profile (48 GiB), 247 charged barriers vs 258 on the ranked M5 `full` profile;
406 dispatches on both. No `_nax` kernel is selected here, but this family is a
runtime-compiled `MLXFastKernel`, not an AOT `_nax` variant, so kernel
reachability transfers.

Threadgroups per GPU core:

| arm | TGs (h64) | TG/core M4 Pro (20) | TG/core M5 Max (40) |
|---|---|---|---|
| `a0` | 5120 | 256 | 128 |
| `G640` | 640 | 32 | 16 |
| `G128` | 128 | **6.4** | **3.2** |

The §6.3 ladder makes the M5 prediction sharper than a tail argument would.
Divisibility admits only `T ∈ {16, 32, 64, 128}` at `S=16`. On a 40-core M5,
**`T=16` and `T=32` fall at or below the core count** — the cliff regime that
cost +917 µs here — leaving `T=64` (= 40 + 24) and `T=128` (= 40·3 + 8) as the
only candidates, and both sit on the plateau whose cost is already measured at
+153…+195 µs. The M5 therefore has *fewer* usable persistent points than this
host, not more, and its best one is the configuration measured here as the
losing arm. Doubling the core count doubles the parallelism that full coverage
must fill while the divisibility constraint keeps `T` fixed, so the penalty
should if anything grow.

Directional-evidence caveat: PR #48's arm `N` measured −55.0 µs/step on M4 and
**+10.0 µs/step on M5**. Any M4 result in this family is directional only.
Here that caveat cuts *against* the proposal rather than for it.

## 10. Correctness coverage and its limits

Every timed arm ran a teacher-forced greedy probe against
`correctness_prompts/public_longcopy_gate_english_512_256.json`; all reported
`0 divergences`.

**`LagunaUpstreamEquivalence.swift` is structurally blind to this family.** Its
setup (`:74-90`) bypasses the weight cache and never reaches
`prepareFusedRuntimeWeights()` (`:11016`), so the lane-major decode QKV kernel
is never constructed under that test. A passing equivalence run is **not**
evidence for this change and is not presented as such.

The prefill axis is unreachable by construction: the caller gates `fuseMode` on
`B == 1 && L == 1` (`:5924`) and the R1 wrapper additionally requires
`normalized.dims(1,1,2048)` (`:4999-5000`).

## 11. Suggested follow-ups (not implemented)

1. **Algebraic epilogue normalization at full coverage.** Accumulate `Σ w·γ·x`
   and `Σ x²` in the same loop and divide by the RMS after `simd_sum`, keeping
   the 640/512-TG full-coverage grid. This removes the redundant reduction
   *without* coarsening the grid — the opposite trade to this stage. It changes
   rounding order, so it needs `research/run_upstream_equivalence.sh`, the
   64-step tripwire and goldens. This campaign prices its ceiling directly:
   `R640 − G640 = +56.5 µs/step` [95% CI +34.5, +78.4] is the whole redundant
   reduction at full coverage, so a perfect algebraic removal is worth up to
   ~56 µs/step *on top of* the −83.3 µs fold refund. That is the strand worth
   funding next, and unlike this stage it does not trade grid geometry away.
2. **Bit-identical prefetch.** Load the first weight tile before the norm
   barrier to hide reduction latency at full coverage. No numerical change.
3. **Do not re-test persistence on M5.** I previously planned an `S=8, T=256`
   matched arm (256/40 = 6.4 TG/core, this host's ratio). The §6.3 ladder makes
   that redundant: the penalty is flat across an 8x range of grid coarseness, so
   matching the TG/core ratio would not change the answer, and §9 shows the M5's
   usable `T` set is strictly smaller. Recommend dropping this line entirely
   rather than deprioritising it.
4. **Reusable finding for other kernels in this family.** Any future stage that
   proposes a coarser grid to amortise per-threadgroup work now has a measured
   price for that trade on this kernel: ~+170 µs/step to leave full coverage,
   plus a cliff if the grid drops below the core count. That is a large budget
   to beat and should be checked before, not after, the mechanism is built.
5. Coordinate with maple-tanjiro (PR #308) if his `S` argmax ≠ 16.

## 12. Reproduction

```bash
CLANG_MODULE_CACHE_PATH="${PWD}/.build-worker/clang-module-cache" \
  swift build -c release --force-resolved-versions \
  --scratch-path .build-worker --product mlxfast-runtime-worker
git checkout -- Package.resolved

bash research/nezuko_pr309_stage0.sh /tmp/nez309/stage0b 24
bash research/nezuko_pr309_abba.sh   /tmp/nez309/abba 4 192
python3 research/nezuko_pr309_stats.py /tmp/nez309/abba --warmup 8 --trim 0.05
python3 research/nezuko_pr309_wandb.py /tmp/nez309/abba /tmp/nez309/stage0b \
  --decision KILL --ladder-dir /tmp/nez309/ladder
```

The publisher refuses to present the campaign as interpretable unless Stage 0's
own gates pass: it logs `stage0/valid` as the conjunction of "the injected
store-row fault diverged at *both* the persistent and the reference geometry"
and "the non-divisible `T=256` grid was refused at kernel construction". All
three were `True` for run `b624rd0b`, along with `ladder/all_clean`.

Threadgroup-count ladder (§6.3), palindromic so the anchor brackets the session:

```bash
SPECS="G640:16:0:0 G128:16:0:128 G64:16:0:64 G32:16:0:32 G16:16:0:16 \
       G16b:16:0:16 G32b:16:0:32 G64b:16:0:64 G128b:16:0:128 G640b:16:0:0" \
  NEGATIVES=0 bash research/nezuko_pr309_stage0.sh /tmp/nez309/ladder 192

for f in G640 G128 G64 G32 G16 G16b G32b G64b G128b G640b; do
  printf '%-6s ' "$f"; grep -h '^decode steps=' "/tmp/nez309/ladder/$f.log"
done
```

The ladder driver reports the worker's own `median=` summary rather than
per-step dumps (`--dump-steps` is only wired into the ABBA driver); the effects
there are 153–917 µs against ≤14 µs replicate spread, so summary medians are
sufficient.

Raw logs for every stage are committed under `research/persistent-qkv-logs/`.
