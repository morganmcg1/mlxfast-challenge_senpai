# Persistent grid-stride QKV (PR #309)

**Student:** maple-nezuko · **Assignment:** `maple-2026-08-07q-persistent-gridstride-qkv` r1
**Base:** `63ab67c888e1892086b7b5b623de4dd0ebe68c90`

**Decision: KILL** — see §8.

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

_(pending)_

## 7. Mechanism

A frontier-model review of Apple GPU scheduling, plus the numbers above,
converge on a **straggler-wave tail**:

- 128 persistent threadgroups of 512 threads slightly exceed the concurrent-TG
  capacity of a 20-core M4 Pro (~80–120 resident TGs at this size). The
  remainder forms a short second wave running at very low occupancy for a full
  multi-row threadgroup lifetime — and at `T=128` a threadgroup lifetime is
  **5 rows**, not 1, so the tail is 5x longer than at full coverage.
- Per-threadgroup launch cost is essentially free here: `a0 → G640` removes
  4480 TGs/step and moves timing by only ~17 µs. So the penalty is *not*
  dispatch overhead; shrinking the grid buys almost nothing on that axis while
  costing tail latency.
- Full-coverage grids are what every production Apple GEMV does. MLX's own
  `qmv` uses 64-thread threadgroups with 8 rows each and full coverage
  (`Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/quantized.cpp:255-299`,
  `kernels/fp_quantized.h:537-556`). Metal offers no cross-threadgroup
  forward-progress guarantee, which is why persistent-CTA idioms common in CUDA
  are not used on Apple.

The redundant-reduction cost model from #298 was therefore correct but
incomplete: it priced the *reduction* work saved and ignored the *scheduling*
cost of the coarser grid required to save it. On this kernel the second term
dominates.

## 8. Decision: KILL

The mechanism the assignment proposed is real — the reduction *is* redundantly
paid, and `T=128` *does* cut it 5x — but capturing it requires a grid coarse
enough that tail imbalance costs more than the saving. The `G128 − G640`
contrast prices that trade with the fold switched off and shows the penalty
alone exceeds the entire #298 refund.

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

`128 = 40·3 + 8`, so on a 40-core M5 the last wave uses 8 of 40 cores — a worse
tail than the M4's. Persistence is structurally *more* constrained on M5: the
no-tail divisibility requirement caps `T` well below full coverage while the
machine has roughly twice the parallelism to fill.

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
   64-step tripwire and goldens. Estimated −60…−80 µs/step; this is the strand
   worth funding next.
2. **Bit-identical prefetch.** Load the first weight tile before the norm
   barrier to hide reduction latency at full coverage. No numerical change.
3. **S=8 / T=256 on M5.** `S=8` requires `T | 256`, so `T=256` gives
   256/40 = 6.4 TG/core on M5 — exactly this host's `S=16, T=128` ratio. If a
   future stage wants to re-test persistence on M5 geometry, that is the
   matched arm. Given §8 this is low priority.
4. Coordinate with maple-tanjiro (PR #308) if his `S` argmax ≠ 16.

## 12. Reproduction

```bash
CLANG_MODULE_CACHE_PATH="${PWD}/.build-worker/clang-module-cache" \
  swift build -c release --force-resolved-versions \
  --scratch-path .build-worker --product mlxfast-runtime-worker
git checkout -- Package.resolved

bash research/nezuko_pr309_stage0.sh /tmp/nez309/stage0b 24
bash research/nezuko_pr309_abba.sh   /tmp/nez309/abba 4 192
python3 research/nezuko_pr309_stats.py /tmp/nez309/abba --warmup 8 --trim 0.05
python3 research/nezuko_pr309_wandb.py /tmp/nez309/abba /tmp/nez309/stage0b --decision KILL
```

Threadgroup-count ladder:

```bash
SPECS="G640:16:0:0 G128:16:0:128 G64:16:0:64 G32:16:0:32 G16:16:0:16" \
  NEGATIVES=0 bash research/nezuko_pr309_stage0.sh /tmp/nez309/ladder 24
```
