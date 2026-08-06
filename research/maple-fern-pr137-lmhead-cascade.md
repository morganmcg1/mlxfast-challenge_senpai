# PR #137 — lm-head cascade: fusion STOPs, S4 row-major restructure ships

Assignment `maple-2026-08-06m-lmhead-cascade-fusion` r1, student `maple-fern`.
Base `2443984f8de7544170a256ad854a22fcf18c8460`
(`codex/mlxfast-maple-20260804-advisor`).
Host for all local numbers: Apple **M4 Pro, 20 GPU cores, 48 GiB, macOS
26.5.2**, Apple GPU generation 16 (`applegpu_g16s`) — no `_nax` kernels.

Two results, in the order they were produced:

1. The pre-registered fusion hypothesis **fails its own Step-0 falsifier**. The
   removable dispatch-boundary budget in the lm-head cascade is ~5.2 µs (M4),
   five times below the 25 µs STOP threshold. Reported here with the
   critical-path map that the assignment named as the fallback deliverable.
2. The census produced while falsifying (1) exposed a different, larger defect
   in the *same* region: the final cascade stage S4 burns 77 µs of GPU time for
   803 KB of traffic. A one-thread-per-row restructure removes **63.7 µs of GPU
   busy time (M4, per-kernel census)** with **bit-identical logits**. r1 also
   quoted 110–114 µs of *wall* saving; §6 retracts that — a balanced 2×2 shows
   the wall saving equals the busy saving and there is no host-gap component.

---

## 1. The cascade map (Step 0 deliverable)

Decode lm-head is a four-dispatch custom-Metal cascade in
`Sources/MLXFastModel/LagunaLmHeadPrune.swift`, entered from
`Sources/MLXFastModel/LagunaRuntimeModel.swift:10969`:

```swift
pruner.logits(..., useFusedRefinement: inputs.dims(1, 1))
```

`useFusedRefinement` is true only when the input is a single row, so **the
refine path is decode-only and prefill can never reach it**. That was confirmed
structurally and empirically: a deliberate 1-ULP fault injected into the refine
store left the prefill digest untouched.

| # | kernel | grid / TG | TGs | produces |
|---|--------|-----------|-----|----------|
| S1 | `laguna_lmhead_int5_base_coarse_delta_bf16_v1` | 3,211,264 / 512 | 6272 | `coarse[100352]` f32, `delta[100352]` bf16; reads 109.18 MB |
| S2 | `laguna_lmhead_coarse_argmax_stage1_v5` | (224,128) / 224 | 128 | `partial_max[128]`, `partial_idx[128]` |
| S3 | `laguna_lmhead_exact_winner_bf16_midpoint_threshold_v1` | 32 / 32 | 1 | `thr[1]` |
| S4 | `laguna_lmhead_exact_fused_int5_sparse_refine_v1` | 802,816 / 256 | 3136 | `assembled[100352]` bf16 |

Dependency graph: `S1 → S2 → S3 → S4`, a pure chain. Every boundary is a **true
RAW** edge on a buffer the next stage reads in its first instruction, so
spin-injection slope tests are ≈1 by construction and carry no information; the
absolute per-kernel census below is the strictly stronger instrument and is what
the decision rests on.

Per-kernel GPU census, `SPLIT=1`, 200 decode steps (profiler hook
`research/pr91-gpuprof-hook.patch`, applied for measurement then reverted):

| stage | µs/step (M4) |
|---|---|
| S1 | 419.8 |
| S2 | 2.3 |
| S3 | 2.9 |
| S4 | 77.4 |

### Why fusion cannot pay

A dispatch boundary can only be *removed* if the two stages can legally live in
one kernel. Taking each boundary in turn:

- **S1→S2.** S2 is a grid-wide argmax over S1's whole 100,352-element output. To
  fold it into S1 you need an order-preserving 64-bit max-with-index atomic
  across 6272 threadgroups, and MLX output buffers are not zero-initialised, so
  there is no safe identity to seed. Rejected.
- **S2→S3.** Collapsible in principle (S3 is a single 32-thread threadgroup
  reducing S2's 128 partials). Worth at most S2+S3 = 5.2 µs, and the collapsed
  kernel measured ~10–16 µs, i.e. break-even to negative.
- **S3→S4.** Legal and bit-exact: recompute `thr` in an S4 prologue. Worth
  2.9 µs.
- **inside S4.** No internal boundary exists. S4 is one dispatch.

So the *entire* removable-boundary budget is **S2 (2.3 µs) + S3 (2.9 µs) =
5.2 µs on M4 ≈ 3.9 µs on M5 ≈ +0.060 % of score**, against a pre-registered
GO gate of 40 µs and a STOP gate of 25 µs. **STOP.**

The "89.2 µs small-kernel pool" that motivated the assignment is real, but
**84 % of it is S4 alone** — a single dispatch, not a pile of fusable ones. The
hypothesis mis-attributed a kernel-internal cost to dispatch overhead.

Command-buffer batching is already shipped and already optimal here: `rms | S1 |
S2 | S3` share one command buffer (432.99 µs) and S4 is alone (76.55 µs); only
3 CB boundaries exist in the whole head region (522.16 µs = 6.31 % of the step).
There is no CB-level headroom either.

---

## 2. S4 row-major restructure (the shipped change)

### Diagnosis

S4 moves ~803 KB (`assembled`, bf16, 100,352 rows) in 74.9–77.4 µs = **10.7 GB/s
= 4 % of the M4 Pro's ~260 GB/s ceiling**. It is not bandwidth-bound; it is
thread-count- and latency-bound.

The shipped kernel dispatches **802,816 threads — 8 lanes per output row** — so
each simdgroup covers 4 rows and every lane pays the full per-row prologue
regardless of whether the row is live. The survivor census from PR #105 puts the
mean at **534 live base rows per step, i.e. 0.53 %**. The kernel is therefore
running an 8-wide-per-row layout to serve a workload where 99.5 % of rows only
need `bfloat(c0)` stored.

### Change

All in `Sources/MLXFastModel/LagunaLmHeadPrune.swift` (+195/−8):

1. New flag `lagunaLmHeadRowMajorRefineEnabled`, env
   `DARKBLOOM_LMHEAD_ROWMAJOR_REFINE`, **default ON**; `="0"` selects the
   shipped four-row arm *in the same binary* (lines 98–107). Both arms are
   compiled and reachable, which is what makes the ABBA below a same-binary
   comparison.
2. New kernel `laguna_lmhead_exact_fused_int5_sparse_refine_rowmajor_v1`
   (lines ~855–974): **one thread per row**,
   `r0 = tgid*256 + sgid*32 + lane`. Each lane evaluates its own liveness,
   `live_mask = simd_ballot(base_live)` is taken **before** the divergent store,
   non-live lanes store `bfloat(c0)`, then a simdgroup-uniform
   `while (live_mask)` loop uses `ctz` + `simd_shuffle` to broadcast one live
   row at a time to all 32 lanes and runs the **verbatim** residual refine, the
   **verbatim** `0x1.005p-1f` mask-and-bump BF16 round-UP, and a **verbatim**
   `gemv_al` replica (`bn = lane*4`, 16 iterations stride 128, then
   16/8/4/2/1 `simd_shuffle_down`). Every row is stored exactly once.
3. Dispatch switch in `logits()` (lines ~1136–1160): grid `(100352,1,1)`,
   threadgroup `(256,1,1)`.

Geometry is exact: `100352 = 392 × 256 = 3136 × 32`. No partial threadgroup, no
bounds guard.

### Geometry, both arms

Neither S4 arm declares any `threadgroup` storage (see the comment at line 659),
so threadgroup memory is 0 B in both and cannot be the occupancy limiter. The
only geometry levers are thread count and TG count.

| | shipped | row-major |
|---|---|---|
| threads dispatched | 802,816 | 100,352 |
| threads / TG | 256 | 256 |
| threadgroups | 3136 | 392 |
| threadgroup memory | 0 B | 0 B |
| lanes per output row | 8 | 1 (32 when the row is live) |
| rows per simdgroup | 4 | 32 |
| TGs / core @ 20 cores (M4 Pro, this host) | 156.8 | 19.6 |
| TGs / core @ 40 cores (M5 Max, ranked) | 78.4 | 9.8 |

### Why this should hold on M5, and how it could fail

This is **not** a pure re-tiling. It is an **8× reduction in dispatched threads**
plus a coalescing repair: in the shipped arm the 8 lanes assigned to one row
each own a strided slice, whereas in the row-major arm 32 consecutive lanes hold
32 consecutive rows on the cold path and a full 32-lane simdgroup runs the
`gemv_al` on the hot path. Work removed does not need a particular core count to
stay removed, so the sign should be host-independent for the mechanism itself.

The part that *is* core-count sensitive is whether 392 TGs still fill the
machine. At 40 cores that is 9.8 TGs/core, versus 19.6 here. That is fewer waves
but still ≥1 TG per core with room for multiple resident TGs (256 threads,
0 B threadgroup memory), so I expect the sign to hold and the magnitude to be
somewhat smaller than the 0.75 M4→M5 scale factor would naively suggest. The
honest failure mode is the opposite of the usual one: the *shipped* kernel's
3136 TGs may be closer to right on a 40-core part than on a 20-core part, which
would compress the win rather than invert it.

There is also a genuine data-dependent crossover. The old kernel gives each live
row 8 lanes covering K/8 = 256 elements with 4 rows in flight per simdgroup; the
new one gives a live row all 32 lanes covering K/32 = 64 elements but serialises
live rows inside a 32-row window. The new arm is faster while live rows per
32-row window < 4, i.e. below **≈12.5 % live**. Observed is **0.53 %** — a ~24×
margin. A workload that pushed survivors past ~12.5 % would regress, and nothing
in the kernel detects that.

Programme queue item #9 already flags `sparse_refine` as an M5-only geometry
question. This result is the M4 half of that answer.

---

## 3. Evidence

### 3.1 Per-kernel GPU census (SPLIT=1, 200 steps, profiler hook)

| row | control | candidate | Δ |
|---|---|---|---|
| `lmhead_exact_fused_int5_sparse_refine*` | 77.4 µs | 13.7 µs | **−63.7 µs** |
| `gpu_busy_sum` | 8.540 ms | 8.478 ms | −62 µs |
| step mean | 9.939 ms | 9.867 ms | −72 µs |
| S1 | 419.8 µs | 420.2 µs | ns |

Every other census row is unchanged, so the saving is localised to S4.

### 3.2 decode_probe ABBA + BAAB, 8 runs × 300 steps, no profiler

| stat | control (`=0`) | candidate (`=1`) | Δ | 95 % CI |
|---|---|---|---|---|
| p10 | 8212.0 ± 54.1 µs | 8099.5 ± 26.1 µs | **112.5 µs** | [29, 196] |
| median | 8284.3 ± 14.0 µs | 8175.0 ± 40.9 µs | **109.3 µs** | [49, 169] |
| mean | 8298.5 µs | 8184.5 µs | 114.0 µs | — |

The wall saving exceeds the GPU-busy saving. At r1 I read that as removing 7/8
of the dispatched threads also shortening the tail that the next dependent
encoder waits on. **§6 retracts that reading**: under a balanced design the gap
does not survive, and the honest point estimate is the census number.

`research/decode_probe.py:160-167` was made tolerant of both 4-field and
5-field `GPUPROF` lines (research-only fix, no runtime effect).

### 3.3 `./benchmark.sh --local-iterate` ABBA (A = candidate, B = control)

| run | s/token |
|---|---|
| A₁ | 0.012768 |
| B₁ | 0.013081 |
| B₂ | 0.013065 |
| A₂ | 0.013027 |

Perfect rank separation (max candidate < min control), Δ ≈ 175 µs, but n = 2 per
arm is underpowered against the ±0.73 % local MDE — cited for sign agreement
only, not for magnitude. All four runs: `passed: true`,
`passed_correctness: true`, `max_abs_diff: 0`, identical
`golden_hash b9509697c08a2cf3c2943a85f0b76e39c485c441794690fa76835b40a58d7a63`.

Caveats recorded so they are not mis-read later: the `prefill_speedup 0.32x` /
`passed_prefill_speedup_floor: false` lines are the standard local-M4
pinned-calibration artifact, and the stored `score.local-iterate.baseline*.json`
files are 17 h stale from commit `ede561b` — neither is citable evidence.

### 3.4 Bitwise logits certificate

`research/frieren_pr80_logit_bitwise.py`, `top_k = 100352`, SHA-256 over exact
logit bits, 64 decode steps.

| case | digest | verdict |
|---|---|---|
| control vs candidate, natural | `3447204b58f5192f772df1a064f0fc87dd59fe41f4720b51f7e6f103403b4928` (both) | **identical**, 65/65 step digests, 0 token mismatches |
| **fault control**: 1-ULP XOR in the row-major store | `da56c419…` | **fires** — 64/65 step digests differ |
| forced `thr − 1e30` (100 % live, all 32 iterations, `live_mask = 0xFFFFFFFF`) | `a546dc68…` (both) | **identical** |
| forced `thr − 5.0` (partial, arbitrary masks) | `3ef12de1…` (both) | **identical** |

Two things matter here. First, the fault control **fires**, so the instrument is
not silently passing everything. Second, that same fault produced
`token_mismatches: 0` — the greedy-token gate is blind to a 1-ULP logit change
in this region, which is exactly why the bitwise digest and not the token gate
is the correctness instrument for this PR.

The forced-threshold stress cases matter because the natural workload only
exercises 0.53 % liveness; the `while (live_mask)` loop's multi-live and
full-live paths would otherwise be untested. Both forced digests differ from the
natural digest, proving the patch took effect, and both arms agree under each.

All temporary patches were reverted and the post-revert digest re-verified
identical; `git diff --stat` is clean against `60b0079`.

### 3.5 Upstream equivalence

`research/run_upstream_equivalence.sh`, both arms, bit-identical results:
prefill `maxAbsErr 0.125` / `mean 0.011933609`, all 8 decode steps exactly
`0.0`, all tokens match. The prefill figure is the pre-existing M4-Pro gen-16
artifact and is unchanged by this PR.

### 3.6 Independent review

A frontier review of the kernel returned **SHIP-WITH-TEST** (the requested test
is §3.4 and is now done). It confirmed that bit-identity is *textually forced* —
identical lane→column map, identical shuffle-reduction tree, and MLX compiles
runtime kernels with `fastMathEnabled(false)`
(`Vendor/mlx-swift/.../device.cpp:631`) so no reassociation is possible — that
the write-once coverage over the uninitialised output buffer is complete, that
there are no races, and that alignment is unchanged. Two residual notes were
recorded rather than fixed: loop uniformity is value-derived (sound today,
fragile against future edits to the liveness predicate), and a NaN activation
would take opposite branches in the two arms (unreachable with finite
activations).

---

## 4. Projection to the ranked M5 score

Using the assignment's elasticity, −1 µs of M5 `T` = +0.01464 % of score, and
the M4→M5 scale factor 0.75:

| basis | M4 Δ | M5 Δ | score |
|---|---|---|---|
| conservative (per-kernel census floor) | 63.7 µs | 47.8 µs | **+0.70 %** |
| optimistic (decode wall, ABBA) | 110 µs | 82 µs | +1.21 % |

Both clear the 40 µs pre-registered GO gate. The conservative figure is the one
I would plan against.

Prefill is untouched by construction: the refine path is gated on
`inputs.dims(1,1)` and cannot be entered during a 512-token prefill.

---

## 5. Programme-level finding: the greedy-token gate is blind to 1-ULP logit drift

This is not a fact about this arm. It is a fact about our **instruments**, and it
was produced as a by-product of §3.4's fault control. Promoted here at the
advisor's request so it can be cited programme-wide.

**Observation.** A deliberate one-ULP perturbation of every value stored by the
lm-head refine kernel changed **64 of 65 logit digests** — i.e. essentially every
decode step produced a different logit vector — and the same run reported
**`token_mismatches: 0`**. The greedy argmax never moved.

| instrument | control (unfaulted) | 1-ULP fault | discriminates? |
|---|---|---|---|
| SHA-256 over exact logit bits, `top_k = 100352`, 64 steps | `3447204b…` | `da56c419…`, 64/65 step digests differ | **yes** |
| greedy token match (`token_mismatches`) | 0 | **0** | **no** |

**Why this happens.** The gap between the argmax logit and the runner-up is
enormous compared with one ULP of bf16 (or of the f32 accumulator), so the
argmax is stable under perturbations many orders of magnitude larger than the
smallest representable change. The token gate therefore certifies *ranking
stability*, not *numerical identity*. Those are different claims, and only the
second one is what "bit-exact" means.

This composes with `research/frieren-pr35-r4-gate-blindness.md`, which found the
same blindness at the *other* end of the scale: a coherent attention-scale
displacement faulting 72–75 % of 389,120 rows at mean relative error **0.2311**
also produced zero token changes. Between the two results the token gate is
demonstrably blind from 1 ULP up to ~23 % relative error on at least two
distinct planes.

**Consequences, stated as rules.**

1. `max_abs_diff: 0` and `token_mismatches: 0` from the harness are **necessary
   and not sufficient** for a bit-exactness claim. Do not write "bit-exact" on
   the strength of a token gate.
2. Any PR whose claim is bit-identity must carry a **logit digest with a fault
   control that fires**. An oracle that has not been shown to fail is not
   evidence.
3. This raises the evidentiary bar on the open H1 bit-exactness question
   specifically: prior arms that rested on token agreement have *not* been shown
   to be bit-identical, only argmax-stable.
4. It also cuts the other way and is worth saying plainly: a change that fails a
   digest is **not** thereby shown to fail the official gates, which are token
   gates. Digest failure is a reason to escalate to the quality panel, not an
   automatic veto.

**Reproduction.** Two runs of the same driver, differing only by the injected
fault. Both are model-holding runs; run them one at a time on a quiet host.

```bash
# 1. reference digest, unfaulted candidate arm
python3 research/frieren_pr80_logit_bitwise.py --label ref --steps 64 \
    --out /tmp/pr137_cert/ref.json

# 2. apply the 1-ULP fault to the row-major store in
#    Sources/MLXFastModel/LagunaLmHeadPrune.swift, inside
#    laguna_lmhead_exact_fused_int5_sparse_refine_rowmajor_v1:
#
#        if (lane == 0) {
#            assembled[r] = bfloat(result);          // <- original
#        }
#
#    becomes
#
#        if (lane == 0) {
#            bfloat _v = bfloat(result);
#            assembled[r] = as_type<bfloat>(ushort(as_type<ushort>(_v) ^ 1));
#        }
#
#    (also apply the same XOR to the non-live `bfloat(c0)` store so every row
#    is perturbed, not only the 0.53 % live ones)

./benchmark.sh --local-iterate          # rebuild the worker with the fault
python3 research/frieren_pr80_logit_bitwise.py --label fault --steps 64 \
    --out /tmp/pr137_cert/fault.json

# 3. compare: the whole-run digest differs (3447204b… vs da56c419…) and 64/65
#    per-step digests differ, while both JSONs report token_mismatches: 0.
#    Revert the patch and re-run step 1 to confirm the digest returns.
```

The driver is `research/frieren_pr80_logit_bitwise.py`; it drives the runtime
worker's teacher-forced `correctness_begin` / `correctness_step` protocol with
`top_k = 100352`, so each step's digest covers the exact bit pattern of the full
vocabulary, not a truncated top-k.

---

## 6. GPU-busy versus wall: the r1 gap does not survive a balanced design

r1 reported a −63.7 µs S4 census saving (§3.1) but a −112.5 µs p10 wall saving
(§3.2), and I attributed the ~49 µs surplus to host/dispatch dead time. The
advisor asked whether that surplus is (i) a real host-gap component — which
would make decode dead time a promotable programme target — or (ii)/(iii) an
artifact of comparing a profiler-instrumented census against profiler-free wall
timing. **The answer is (iii): the discrepancy dissolves. There is no host-gap
component. The win is GPU-busy time, ~64.5 µs.**

### 6.1 Design

The r1 comparison was unbalanced: the census ran with the `GPUPROF` hook
compiled in and the wall ABBA ran without it. This experiment crosses the two
factors so the profiler cannot confound the arm contrast.

Balanced 2×2 ABBA over {profiler on, off} × {arm 1 = new row-major, arm 0 = old
cascade}, 2 replicates per cell, 400 steps per cell, driven by
`research/decode_probe.py --steps 400 [--profile]` with `DARKBLOOM_GPU_PROFILE`
and `DARKBLOOM_LMHEAD_ROWMAJOR_REFINE`. The hook is
`research/pr91-gpuprof-hook.patch` applied to
`Vendor/mlx-swift/.../metal/device.{cpp,h}`; it is **local-only research
instrumentation and is not part of the submitted surface** — the branch was
`git reset --hard`ed back to the research HEAD before submission, and
`git diff BASE_SHA --stat` shows `Sources/MLXFastModel/LagunaLmHeadPrune.swift`
as the only scored file touched.

Every one of the eight cells reported `0 divergences (all match)`.

### 6.2 Result

µs per decode step; `busySum` is Σ per-command-buffer GPU busy and
`wall−busySum` the host gap. (The `gpu_busy_union` column this table originally
carried has been removed — see conclusion 1.)

| cell | p10 ms | median | mean | wall | busySum | wall−busySum |
|---|---|---|---|---|---|---|
| profoff arm0 a | 8.197 | 8.245 | 8.256 | — | — | — |
| profoff arm0 b | 8.143 | 8.302 | 8.272 | — | — | — |
| profoff arm1 a | 8.172 | 8.233 | 8.235 | — | — | — |
| profoff arm1 b | 8.169 | 8.225 | 8.240 | — | — | — |
| profon arm0 a | 8.217 | 8.273 | 8.289 | 8.286 | 8.016 | 270.0 µs |
| profon arm0 b | 8.144 | 8.285 | 8.266 | 8.263 | 8.003 | 260.0 µs |
| profon arm1 a | 8.069 | 8.212 | 8.194 | 8.191 | 7.933 | 258.0 µs |
| profon arm1 b | 8.163 | 8.221 | 8.226 | 8.223 | 7.957 | 266.0 µs |

Arm deltas (old − new, n = 2 per arm):

| statistic | profiler on | profiler off |
|---|---|---|
| p10 | **+64.5 µs** | −0.5 µs |
| median | +62.5 µs | +44.5 µs |
| mean | +67.5 µs | +26.5 µs |
| wall | +67.5 µs | — |
| `gpu_busy_sum` | **+64.5 µs** | — |
| host gap (wall − busySum) | 265.0 → 262.0 = **+3.0 µs** | — |

### 6.3 Three conclusions

1. **Retracted: I cannot claim the queue is serialised, and I do not need to.**
   My first draft read `gpu_busy_union == gpu_busy_sum` — which held to the digit
   in all four profiled cells — as independent proof of full serialisation. It is
   no such thing. The union is merged over *command-buffer* intervals recorded by
   a CB completion handler (`research/decode_probe.py:175-190`), and MLX packs
   every op onto one queue, so command buffers cannot overlap and the identity
   holds by construction, whatever the kernels inside them do. tanjiro settled it
   with a positive control: two kernels hiding almost perfectly (`overlap_eff`
   1.0024) while the CB-derived overlap statistic read exactly 0.000000
   (`research/tanjiro-pr157-result.md` §2, merged as `f4bfa59`, which retires the
   statistic programme-wide; it postdates my base, so I cite rather than
   re-verify it). The column is gone from §6.2.
   This does put a caveat on §3.1: if kernels *can* overlap, a per-kernel census
   cannot by itself prove that a per-kernel saving reaches the frame. What
   licenses §3.1 here is not serialisation but the agreement in this very table —
   census −64.5 µs against wall −67.5 µs. Wall time cannot hide a saving that
   never happened, so the shipped claim rests on the measurement that is immune
   to the retraction.
2. **No host-gap component.** Under identical profiler settings the wall saving
   (+67.5 µs) equals the GPU-busy saving (+64.5 µs) inside noise, and the host
   gap itself is flat at 262–265 µs — 3.2 % of an 8.2 ms step, matching the
   0.322 ms already on record. Its arm delta is +3.0 µs, i.e. nothing. Removing
   7/8 of the dispatched threads does not shorten dispatch overhead. The encoder
   accounting is also *exactly* unchanged — 45.0 command buffers and 406.2
   dispatches per step in all four profiled cells — so the arm did not alter the
   graph's commit structure either. §6.5 goes further and shows the gap is not
   per-buffer elastic in the first place.
3. **The r1 −112.5 µs was never distinguishable from the census number.** Its
   95 % CI was [29, 196], which contains 64.5. The apparent "1.8× wall
   amplification" was a point estimate read as if it were a measurement. The
   profiler-off half here is likewise noise-dominated at n = 2 (p10 −0.5, median
   +44.5, mean +26.5, with ±60 µs of scatter between replicates of the *same*
   cell), so it neither confirms nor refutes anything on its own — which is the
   point. Note also that the profiler hook costs nothing systematic: profon
   minus profoff is +10.5 µs on arm 0 and −54.5 µs on arm 1, i.e. smaller than
   the replicate scatter, so instrumentation bias is not the explanation either;
   the r1 gap was simply sampling noise.

### 6.4 What this changes

- The honest headline for this change is **−64.5 µs of GPU-busy time on M4**,
  not −112.5 µs of wall. §4's M5 projection should be read off the census, which
  is what it already does.
- **Decode host dead time should not be promoted as a programme target on this
  evidence.** 262 µs/step of host gap is real and is 3.2 % of decode, but it is
  invariant to a change that deletes 87.5 % of one kernel's threads, so it is
  not thread- or occupancy-elastic. I first guessed that attacking it would mean
  reducing the *number of encoders*; §6.5 retracts that guess — the gap is not
  encoder-count elastic either, and I have no mechanism for it.
- Methodological rule for the programme: never contrast a profiled census
  against unprofiled wall timing. Cross the instrumentation factor, or quote the
  census alone.

Scripts and raw cell outputs: `/tmp/pr137_gpuprof/{run_arms.sh,run_off.sh,aggregate.py}`
and `/tmp/pr137_gpuprof/prof{on,off}_arm{0,1}_r{a,b}.out`. (Local scratch, not
committed; the hook patch and the probe are in `research/`.)

### 6.5 Retraction: encoder count is not the host-gap lever

§6.4's closing suggestion — that attacking the gap "would require reducing the
number of encoders" — is wrong, and the arithmetic behind it is spurious. Three
findings, then the consequence.

1. **Per-command-buffer host cost is measured at ~0 in this repo.** nezuko
   varied the byte cap and found the host gap flat, 0.249 ms at 200 versus
   0.250 ms at 50, while command buffers per step tripled from ~48 to ~140
   (`research/nezuko-mb50-mechanism.md:1-10`). Ninety-two extra buffers cost
   1 µs in total, i.e. ≤ 0.01 µs per buffer. So `262 / 45 = 5.8 µs per command
   buffer` is a division I performed, not a coefficient anyone measured, and it
   is off by roughly three orders of magnitude. The 262 µs is a fixed per-step
   cost that happens to be divisible by 45.
2. **My own 2×2 says the same thing from the other side.** Across all four
   profiled cells — both arms, both replicates — the encoder accounting is
   *exactly* identical: 45.0 command buffers and 406.2 dispatches per step
   (17955/399 steady). Thread count changed drastically, buffer count did not
   move, gap did not move. On its own that is consistent with any per-buffer
   coefficient; combined with nezuko's varying-buffer experiment the
   coefficient is pinned near zero. It does, though, kill the alternative story
   that the arm somehow changed the graph's commit structure.
3. **What the byte cap actually moves is GPU-busy, not host time.** nezuko's
   mechanism: the cap converts in-encoder `memoryBarrier` drains, which are
   booked inside `[GPUStartTime, GPUEndTime]`, into buffer seams, which measure
   free — ~2 µs each, with an interior optimum near 50 rather than a monotone
   trend. frieren prices the ranked profile at 48 buffers/step at cap 200 and
   78 at 128, and confirms the op cap never binds
   (`research/frieren-pr23-result.md:163-175`).

Mechanism, verified in source, recorded so nobody re-derives it:

- the only cap predicate is `CommandEncoder::needs_commit()`,
  `Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/device.cpp:484-487`,
  evaluated once per array eval at `metal/eval.cpp:59-64`;
- `buffer_sizes_` accumulates `a.data_size()`, which is **elements, not bytes**
  (`mlx/array.h:345-348`), deduplicated by buffer pointer
  (`device.cpp:315-321`) and reset only in `commit()` (`device.cpp:528-529`) —
  frieren's "Mi-elements, not MB" correction, independently confirmed;
- ~182 Mi elements per layer against the 200 cap trips roughly one cut per
  layer; add the 7 `asyncEval` finalizes at `LagunaRuntimeModel.swift:680`
  (layers 0, 1, 7, 15, 23, 31, 39) and you get ~45 buffers and 406/45 ≈ 9
  dispatches each, which is what the probe reports;
- the op cap cannot bind: 406 dispatches against a 200 cap permits at most 2
  cuts.

**Host-class trap, cost me one scan.** On this 48 GiB box
`RuntimeStartupMemoryPolicy.apply()` sets both caps with `setenv(..., 1)` —
overwrite — at `Sources/MLXFastModel/RuntimeStartupMemoryPolicy.swift:170-182`,
so an exported `MLX_MAX_MB_PER_BUFFER` is silently discarded on any sub-64 GiB
host. The >= 64 GiB branch uses `setenv(..., 0)` at
`LagunaRuntimeWeights.swift:385-387` and *would* honour an export unless
`DARKBLOOM_POST_WIRE_COMMAND_BUFFER=0`. My env scan (300 steps per cell, arm
pinned to 1, `0 divergences` throughout) returned **45.0 buffers/step and 406.3
dispatches/step in every cell that ran**: null by construction, not by physics.
frieren hit the identical trap and burned a 6-arm run on it
(`research/frieren-pr23-result.md:163-166`). Nobody should run the cap env
screen on a sub-64 GiB host; vary the constant instead, or run it on the M5.

**Correction to an earlier draft of this paragraph, and what the wreckage is
worth.** I first described that scan as three cells including an unmodified
`base` control. Re-reading the log, it was six planned cells of which **three
never executed**: `base_on`, `base_off` and `mb1000_off` each died on
`caps[@]: unbound variable` / `extra[@]: unbound variable`. Bash 3.2 under
`set -u` treats the expansion of an *empty* array as unbound, so the script
killed exactly the cells that set no cap override and the cell that passed no
`--profile` flag — i.e. precisely the controls. **The scan contained no
baseline cell at all.** The "null by construction" conclusion does not depend on
it (it follows from the `setenv` overwrite plus the identical counts), but the
design description was wrong and is corrected here.

The three cells that did run are worth more as an accident than as a scan.
`mb200_on`, `mb1000_on` and `both_on` (ops=500, mb=1000) requested three
different configurations, and the overwrite makes all three **physically the
same configuration**, confirmed by identical `cbs=45.0` and
`dispatches=406.3`. So they are three unreplicated 300-step runs of one config —
a free negative control:

| cell | wall (ms) | `gpu_busy_sum` (ms) | gap (ms) |
| --- | --- | --- | --- |
| `mb200_on` | 8.204 | 7.966 | 0.238 |
| `mb1000_on` | 8.118 | 7.890 | 0.228 |
| `both_on` | 8.210 | 7.949 | 0.260 |
| **spread** | **92 µs** | **76 µs** | **32 µs** |

Identical configurations differ by up to **92 µs of wall and 76 µs of GPU-busy**
across single 300-step cells. That spread is *larger than the −64.5 µs arm
effect this PR ships*. It is the cleanest local justification for why §6.1 used a
balanced, replicated, profiler-crossed ABBA rather than cell-vs-cell
comparison: on this host a single 300-step cell cannot resolve the effect at
all, and any unreplicated A-vs-B here would have been noise with a sign.

**Consequence.** Encoder-count reduction is not a host-gap lever. The ground
the cap does control — in-encoder barrier cost, inside GPU-busy — is already
held by nezuko and frieren, and the shipped 200 is their tuned point. Decode
host dead time is real at 262 µs/step and 3.2 % of wall, but it is neither
occupancy-elastic (§6.2) nor encoder-count-elastic (nezuko), and I have no
mechanism for it. frieren's decomposition further attributes 122 µs of it to
the trusted harness, which is not ours to remove.

### 6.6 Outside review, and where it lost

I put the per-buffer question to an independent frontier reviewer with no
repository context, deliberately feeding it the 5.8 µs/buffer premise. It
judged 5.8 µs/buffer plausible and near the hardware floor, bracketing it with
measured 27–50 µs commit→completion round trips.

That endorsement is **superseded by nezuko's direct measurement**. I record the
exchange because the failure mode is the instructive part: 5.8 µs/buffer is
entirely plausible *a priori* for Metal, which is exactly why the division
looked like a finding. An outside-view plausibility argument lost to an in-repo
controlled experiment, and it should have.

Three things it contributed that do survive, all flagged as unverified by me:

- it re-derived the mega-elements (not megabytes) accounting from source
  independently, agreeing with frieren;
- it checked `benchmark.json` and observed that `metal/quantized.cpp` and
  `metal/matmul.cpp` are inside the submitted surface (lines 26 and 61) while
  `metal/device.cpp` and `metal/eval.cpp` are not — so any future cap work must
  move the call sites, never the predicate. Recorded for whoever picks it up;
  it is not my assignment, and §6.5 argues the payoff is not there anyway;
- it argues from a bandwidth roofline (~1.5 GB of weight traffic per token)
  that GPU-busy sits several times above the achievable floor, leaving multiple
  milliseconds of headroom, against at most 0.26 ms in the gap. I have not
  checked the traffic figure, but the ratio is the same argument §6.4 makes
  from the other direction, and it is the reason to spend campaign effort on
  kernel efficiency rather than on dispatch overhead.

---

## 7. Queue wait as a programme datum

The advisor asked me to record the official-queue wait rather than treat it as
dead time, because the campaign has been planning against an assumed ~35 min per
receipt. That assumption does not survive this observation.

### 7.1 What was observed

The account allows **one** submission in flight per benchmark. When I became
ready to dispatch, the slot was held by submission `57d8f082-b303-4a63-8301-
3ad8219db272`, which is **not mine**.

| time (UTC) | source | state of `57d8f082` |
| --- | --- | --- |
| 18:26:05 | `mlxfast submissions` `createdAt` | created |
| before 20:48 | three direct `mlxfast submit` attempts | in-flight conflict; nothing created |
| 20:58:50 | poller `295ce1ce` poll 1 | `validating` |
| 21:09:23 | poller `295ce1ce` poll 2 | `validating` |

That is **2 h 43 min in `validating` with zero state transitions**, and the
figure is a *lower bound*: the submission had not cleared when the observation
window ended. Whatever the true service time is, it is at least 4.7× the ~35 min
planning number, and I never saw the transition that would let me quote an
actual mean.

The three direct attempts are worth recording separately because they establish
the failure mode is clean: each returned `account already has 1 submission(s) in
flight for this benchmark (limit 1)` and **created nothing**. A busy slot is not
a rejection and carries no information about the candidate — which is exactly
why the rule now forbids re-dispatching into it.

### 7.2 Why this matters more than it looks

The slot is a **single server shared across the whole campaign**, not a
per-student resource. That converts receipt planning from a per-student budget
into a queueing problem:

- With one server and a service time of `T_s`, the programme retires at most
  `24 / T_s` receipts per day *in total*, no matter how many students are active.
  At `T_s ≈ 3 h` that is ~8/day for everyone combined; at the assumed 35 min it
  would have been ~41/day.
- Adding students does not add throughput. It only lengthens the queue, so the
  marginal value of a parallel student is in *evidence quality per receipt*, not
  in receipts per hour.
- My own poll cadence adds up to one further poll interval (10.5 min) of
  detection latency on top of the true clear time. That is small against a
  multi-hour service time and is the correct trade against the rule, but it is
  not zero and it should be counted when someone models the pipeline.

### 7.3 What I would change in planning

Treat a receipt as a **multi-hour, serialised, campaign-level resource**. Two
practical consequences for how work is assigned:

1. A candidate should not be dispatched until its local evidence is strong
   enough that a *ranking-only* rejection would still be informative. A receipt
   spent to discover something a local ABBA would have shown is expensive in
   programme hours, not just in the student's budget.
2. Kill rules should be fixed **before** dispatch, as they were here
   (GO `ns ≥ 2.6045`, KILL `ns < 2.5919`). If the interpretation is still open
   when the receipt lands, the queue time bought nothing but a number.

I have not measured a completed service time, so I am not offering a mean. The
honest datum is: **one observation, ≥ 2 h 43 min, still running.**

---

## 8. What I did not do

- Did not touch routed/shared MoE gather-GEMM or any `_nax` kernel (tanjiro,
  frieren) or `Sources/MLXFastTransform` (nezuko).
- Did not implement the S3→S4 prologue fold. It is bit-exact and legal but worth
  only ~2.9 µs on M4, and it would couple two stages whose separation currently
  makes the census readable. Worth revisiting only if it can be bundled with
  another S4 change.
- Did not add a liveness-adaptive dispatch that would pick the old geometry when
  survivors exceed ~12.5 %. The 24× margin does not justify the branch today,
  but it is the natural guard if the pruner's threshold policy ever loosens.
