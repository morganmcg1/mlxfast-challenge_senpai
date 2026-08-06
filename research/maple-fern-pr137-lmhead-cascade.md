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

S4 moves at most ~803 KB in 74.9–77.4 µs = **10.4 GB/s = 4 % of the M4 Pro's
~260 GB/s ceiling**. It is not bandwidth-bound; it is thread-count- and
latency-bound.

The 803 KB is deliberately the *generous* end of the accounting: the bf16
`assembled[100352]` store alone is only 200,704 B, which would put the kernel at
2.6 GB/s (1 % of ceiling), and 803 KB assumes roughly four times that in
combined read and write traffic. Over-stating traffic over-states achieved
bandwidth and so makes the kernel look *closer* to the roof than it is, which is
the conservative direction for every claim built on this number.

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
| 21:23:25 | poller `aa5bea7f` poll 1 | `validating` |
| 21:33:1x | poller `aa5bea7f` poll 2 | **`failed`** (commit `b52831e`) |

So the wait resolved, and the resolution is worse than a long wait: the
submission occupied campaign-wide validation capacity for **up to 3 h 07 min and
then terminated as `failed`**, publishing no score. The elapsed figure is an
upper bound on its service time and a lower bound on the capacity it consumed;
either way roughly **five times** the ~35 min planning number was spent on a
submission that returned nothing.

The three direct attempts are worth recording separately because they establish
the conflict response is clean: each returned `account already has 1
submission(s) in flight for this benchmark (limit 1)` and **created nothing**.
A busy slot is not a rejection and carries no information about the candidate.

### 7.1b The rule changed mid-wait, and the old cadence immediately cost me the slot

At **21:28:52Z**, `senpai/program.md` commit `f13d659` ("Let submitters manage
validation retries") replaced the coordinated queue with self-managed retry:
there is no central queue owner, any authorized submitter with a committed,
preflighted candidate owns its own lifecycle and must not wait for another
agent's permission, and on a busy slot the submitter preserves the exact commit
and note and rechecks "periodically without a tight polling loop and no sooner
than server retry guidance". The earlier ten-minute single-owner cadence is
repealed, so the sentence this section originally ended on — that the rule
forbids re-dispatching into a busy slot — no longer holds and has been removed.

The consequence was immediate and measurable:

| time (UTC) | event |
| --- | --- |
| 21:28:52 | `f13d659` lands; retry becomes self-managed |
| ~21:30 | `57d8f082` fails, freeing capacity |
| 21:30 | **`4b06e93` created by another submitter** |
| 21:33:1x | my poller's next scheduled poll observes the slot already retaken |

I lost the slot by roughly three minutes, to a cadence that the rule governing
it had been repealed two minutes earlier. That is worth stating plainly because
it is a *design* failure, not bad luck: under a single-owner queue the cadence
was mandated and detection latency was free, but the moment admission became
first-come, detection latency became the competitive variable.

There is a second, sharper flaw in the design I had been running. Polling
`mlxfast submissions` and *then* dispatching leaves a race window between the
observation and the submit call; whoever submits inside that window wins. The
fix is to stop polling and retry `mlxfast submit` directly on a periodic
cadence, which is also exactly what the new rule prescribes: the server itself
arbitrates capacity, and the in-flight conflict response is verified to create
nothing, so a rejected retry is free. My replacement dispatcher does that at a
180 s interval, still honouring any larger server retry guidance, and treats
**only** the explicit in-flight conflict as retryable — any other non-zero
response stops the script, since it might have created a submission and the
rule forbids duplicating one that is queued or validating.

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

## 9. Wave analysis across 20 and 40 cores (required by the softened geometry rule)

Organizer commit `f30bd49` ("Soften Maple research heuristics") changed the
status of this arm's evidence, so this section is not optional bookkeeping.

Under the previous wording, thread re-tiling — explicitly including *grid
divisors* — "does **not** transfer; an M4 measurement is not evidence and must
not be reported as if it were." The shipped change is exactly a grid-divisor
change, so under that rule my entire local case was inadmissible by
construction. The new wording reclassifies it as "core-count sensitive;
interpret M4 timing with wave analysis rather than presenting it as sufficient
M5 evidence", and requires that any M4→M5 geometry prediction report the
threadgroup count, threads per threadgroup, threadgroup memory, and wave count
`ceil(TGs / cores)` for both 20 and 40 cores, with a predicted sign per host.
That is the analysis below. I am flagging the dependency openly: my evidence is
reportable because the rule was softened, not because the measurement changed.

### 9.1 Launch geometry, both arms

Read from the dispatch site in `Sources/MLXFastModel/LagunaLmHeadPrune.swift`
(MLX's `grid` argument is *total threads*, not threadgroups):

| | control (`..._sparse_refine_v1`) | shipped (`..._sparse_refine_rowmajor_v1`) |
|---|---|---|
| grid expression | `vocab / 32 * 256` | `vocab` |
| total threads | 802,816 | 100,352 |
| threads / threadgroup | 256 | 256 |
| **threadgroups** | **3,136** | **392** |
| threads per output row | 8 | 1 |
| threadgroup memory | 0 B | 0 B |
| partial threadgroup | none (3136 × 256 exact) | none (392 × 256 exact) |

Threadgroup memory is zero in both arms, so occupancy cannot be the hidden
confounder in either direction.

### 9.2 Wave counts

| cores | control waves | shipped waves | ratio |
|---|---|---|---|
| 20 (M4 Pro, this host) | `ceil(3136/20)` = **157** | `ceil(392/20)` = **20** | 7.85× |
| 40 (M5 Max, ranked) | `ceil(3136/40)` = **79** | `ceil(392/40)` = **10** | 7.90× |

The wave *ratio* is essentially identical on both hosts, which is the useful
part: the relative speedup should transfer even though the absolute saving
should not.

### 9.3 Predicted sign, per host

**Negative (faster) on both, high confidence.** The inversion mode for a
geometry change is under-occupancy — the threadgroup count falling toward or
below the core count, leaving cores idle. At 40 cores the shipped arm still
launches 392 TGs, i.e. 9.8 TGs per core, so every core is ~10× oversubscribed
and no core idles. There is no mechanism here for the sign to flip.

This is the structural difference from the `MLX_MAX_MB_PER_BUFFER` precedent
(receipt `3e6fdcb`), where two balanced M4 confirmations of −1.76% and −1.99%
inverted to `ns` −1.608% on M5. That was a global allocator knob whose effect
was mediated by machine-wide scheduling; this is a local removal of 7/8 of the
dispatched threads for a fixed amount of output.

### 9.4 Predicted magnitude — this revises my own projection **downward**

Per-wave cost implied by the M4 census (200 steps): control 77.4 µs / 157 waves
= 0.493 µs/wave; shipped 13.7 µs / 20 waves = 0.685 µs/wave. The shipped arm's
waves are individually heavier, as expected, since one thread now carries a
whole row.

Holding per-wave latency fixed and halving the wave count at 40 cores:

- control: 79 × 0.493 = **38.9 µs**
- shipped: 10 × 0.685 = **6.9 µs**
- **predicted M5 saving ≈ 32 µs, transfer factor ≈ 0.50**

My r1 submission assumed a transfer factor of **0.75** (47.8 µs, +0.70%). That
0.75 was never derived — it was a round conservatism margin. The wave model says
**0.50 is the better central estimate**, because the dominant term is
wave-proportional and the M5's extra cores halve the wave count for both arms
together.

Honest band: **0.50–0.75, i.e. 32–48 µs, i.e. +0.47% to +0.70%**. The upper end
requires a component of the control arm's cost that is *not* wave-proportional
(e.g. memory-latency exposure that the M5 cannot hide any better than the M4);
the lower end is the pure throughput model.

**This band straddles the advisor's 40 µs GO gate**, which the r1 projection did
not. I am recording that before the receipt rather than after, because a
prediction stated only once the answer is known is worth nothing. It also makes
the measured transfer factor the most valuable number on the receipt: it is a
direct test of a 0.50 wave model against a 0.75 guess, on a kernel both hosts
genuinely execute.

### 9.5 A bounded counterexample to the byte-roofline prior

`f30bd49` also softened "a decode change that neither removes bytes nor improves
bytes/second is worth approximately nothing … do not reopen [dispatch count,
kernel fusion, threadgroup occupancy] without new evidence about bandwidth" to
"starts with low expected value … revisit one when a proposal identifies a new
mechanism or new evidence".

This arm is that new evidence, and it is worth stating precisely because the
prior is otherwise well supported:

- S4 moved at most 803 KB in 77.4 µs = **10.4 GB/s**, about **4 % of the M4
  ceiling**, and 1 % if only the bf16 store is counted (see §"Diagnosis" for the
  accounting, which is deliberately generous). The kernel was nowhere near the
  bandwidth roof; it was thread-count/latency bound.
- The shipped change removes **no bytes at all**. Every one of the 100,352
  output rows is still written. It removes 7/8 of the *threads* dispatched to
  write them, and wins 63.7 µs on M4.

The reconciliation is that the 1794 MB / 260.2 GB/s roofline is a *step
aggregate*. Individual kernels can sit far below it, and when one does, thread
count rather than bytes is the binding constraint for that kernel. The prior
should be read as "bytes bind for the kernels that dominate the step", not as
"nothing but bytes can ever pay". The practical filter I would suggest: before
dismissing an occupancy or dispatch proposal, price the target kernel's achieved
GB/s. At 4 % of ceiling the byte prior simply does not apply.

It is worth pricing the aggregate too, because doing so shows the prior is
well founded rather than merely convenient. 1794 MB against the candidate's
8.478 ms `gpu_busy_sum` is **211.6 GB/s, or 81 % of the 260.2 GB/s ceiling**.
The decode step really is close to the roof. So both statements are true at
once, and the distribution across kernels is what reconciles them:

| | achieved | % of ceiling | share of step |
|---|---|---|---|
| decode step, aggregate | 211.6 GB/s | 81 % | 100 % |
| S4 sparse refine (control) | 10.4 GB/s | 4 % | 0.91 % |

The asymmetry has a consequence that cuts both ways, and I would rather state
it against my own result than let it be discovered later. Because the aggregate
already sits at 81 %, the entire pool available to pure bandwidth work is
bounded by the remaining ~19 % of step time. Kernels far below the roof have a
much larger *relative* headroom — S4 went 5.65× faster — but each holds only a
small *absolute* share, and S4 held 0.91 %. Byte-bound work therefore has a
capped but broad pool; latency-bound work has huge multiples on narrow slices.
Neither class dominates a priori, which is precisely why the target kernel has
to be priced individually instead of inheriting the step-level number.

What I did **not** do is size the latency-bound pool. That needs per-kernel byte
accounting across the whole census, not just the one stage I instrumented, and I
did not collect it. So this section establishes that the byte prior admits
counterexamples and shows how to test for one; it does not establish that there
are enough of them to matter. Treating it as the latter would be exactly the
over-reading I retracted in §6.

### 9.6 Reporting consequences of the softening

- **Receipt count.** "Every official submission must be reported … in a family
  of at least three" became "match repetition to the decision: one receipt can
  justify a clear win, while a marginal effect near observed variance benefits
  from repeated receipts." My projected +0.47 % to +0.70 % sits above the
  0.243 % 2σ noise floor at the top of the band and near it at the bottom, so a
  single clear receipt can settle a win, while a result landing near +0.25 %
  would need repetition. Budget unchanged at 3; I still expect to spend 1.
- **Thresholds.** The programme-wide "advisor's acceptance bar is 2× that,
  0.61 %" line was deleted, and the 0.243 % floor is now "noise context, not a
  universal submission or promotion threshold". I am nonetheless still reporting
  against the advisor's explicitly pre-registered r2 bars — **GO `ns ≥ 2.6045`,
  KILL `ns < 2.5919`** — because those were set for this arm in this assignment
  and a pre-registered bar that is relaxed after the fact is not a bar.
- **`S`/`T` decomposition** softened from "must, for every official run" to
  "when identifying where the gain came from". I am reporting it regardless;
  this arm's whole claim is a `T`-only change with `S` flat by construction.
- **Attention precision** (`ccaa555`, a third organizer commit that landed while
  this arm was queued) softened "the envelope is a dead lever here, and it points
  the wrong way" to "a low-priority direction … revisit only when a mechanism
  stays inside the accepted envelope and shows a net byte or math advantage".
  I am recording it only so that nobody later assumes I leaned on it: this arm
  changes no representation and is bit-identical (§3.4), so the attention
  envelope is orthogonal to it in both directions. The clause that stayed hard —
  "do not propose taking any other class below its current representation" — is
  also untouched by anything here.

### 9.7 Why the receipt's recorded commit will not match the PR head

Two organizer commits (`f30bd49`, `ccaa555`) landed on this branch while the
submission sat in the queue, and I reconciled each by merge rather than rebase.
(`f13d659` was already an ancestor before the dispatcher armed, so it needed no
reconciliation.) A rebase transiently checks out trees in which
`research/maple-fern-pr137-submission-note.md` does not yet exist, and the armed
dispatcher reads that path from the *working tree* via `--note-file`; an attempt
firing inside that window would have failed on a non-whitelisted error and
halted the retry loop.

The consequence is that the receipt will record whichever commit was HEAD when
the accepted attempt fired, and that will not be the final PR head. This is
cosmetic, and provably so: the submitted surface is one file, and its git blob
is `6e8bde5eee12f095b7642ce3ee6a48e551aa81b7` at **every** commit from
`1a1153d` (dispatcher start) through `cfd60f7`, `06aceb7`, `1821996` and
`1b0abba`. The packaged note is likewise `8c3c553b…` throughout. Every
intervening commit is research-only or `senpai/program.md`, and
`senpai/program.md` is outside `editablePaths` — re-running
`check-editable-budget.sh` after the merges returns the identical
`current=2929907/3000000 growth=8160/262144`. So whatever commit the receipt
names, it describes the same measured editable content.

## 10. Reading the public submission feed as data

`mlxfast submissions` is backed by a feed that returns the full
`officialMetrics` block of every terminal submission from every solver
account, not just ours (1,577 rows at 2026-08-06T22:33Z). I had been using it
only as a status check. Read as data it settles a question this branch could
not otherwise answer — how much the *official M5* paired baseline moves between
sessions — and it changes how this receipt should be read.

### 10.1 The v1 dispatcher was halted by a server rate limit, and created nothing

Attempts 1–17 (21:35:58Z → 22:25:02Z, one every ~185 s) each returned the one
whitelisted retryable response, `{"error":{"code":"conflict","message":"account
already has 1 submission(s) in flight for this benchmark (limit 1)"}}`. Attempt
18 at 22:28:04Z returned `Rate limit reached. Try again in 1914 seconds.`, which
is not that conflict, so the script stopped rather than risk duplicating a
candidate it could not prove had failed to be created. Supervised run
`afe1a668` therefore terminated `failed` (exit 1) after 3,135 s.

The rule for an ambiguous response is to check before retrying, so I listed the
feed first. Nothing of mine exists: the only in-flight row for this account is
`0e43085` (`validating`, created 22:09:25.005Z), whose note identifies it as
`mlxfast-cedar-20260806-tanjiro-qkv-r1-sg4`, PR #151 — a different Senpai
campaign. The rate-limited call was refused before it created anything, as its
wording implies, and now that is evidence rather than an assumption.

The cost is self-inflicted and worth naming: 18 upload attempts in 52 minutes
is what tripped the limit. v1 deliberately retried `submit` directly because
polling-then-submitting had already lost me one slot to a 180 s race window
(§7.1b). That fix was right about the race and wrong about the price.

### 10.2 Dispatcher v2 separates *when to try* from *trying*

v2 (`/tmp/pr137_submit/retry_submit.sh`, helper `inflight.py`) polls the
read-only feed every 120 s and calls `submit` only when this account has no
in-flight row, plus one forced attempt every 900 s so a status I classify
wrongly cannot stall the dispatcher forever. Submit calls drop from ~20/hour to
at most ~4/hour while the poll-to-submit race window shrinks from 180 s to a few
seconds. A rate limit is now retryable: the stated seconds are parsed and
honoured with a 30 s margin instead of halting the loop. Terminal statuses are
enumerated positively, so an unknown status delays a submit rather than
duplicating one, and the forced attempt covers the opposite error. Only the
in-flight conflict and an explicit rate limit are retried; anything else still
stops immediately.

### 10.3 The in-flight limit is per solver account, and the account is shared

The conflict message says *account*, and the feed confirms the scope: at
22:34Z `davidtai` and this account (`morganmcg1`) each had one submission
validating concurrently. Other solvers are not the constraint — the single slot
is shared only among Senpai campaigns dispatching under one account, which is
why a Cedar candidate at 22:09Z blocks a Maple candidate at 22:34Z. v1's
in-flight check counted *any* solver's row and would have deferred to
`davidtai` for no reason; v2 filters on the account.

### 10.4 The official paired baseline moves by more than this arm's whole effect

Every receipt reports both a speedup and an absolute seconds-per-token, so the
session's own baseline is recoverable as `speedup × candidate`:

| receipt | timestamp (UTC) | baseline decode | baseline prefill |
|---|---|---|---|
| `97a5090` | 05:14:29Z | 13.844966 ms | 382.68 µs |
| `4b06e93` | 21:57:41Z | 13.918368 ms | 375.67 µs |
| `db8b4df` | 22:18:30Z | 13.881933 ms | 381.75 µs |

Across ~17 hours the pinned baseline spans **73.4 µs of decode (0.53 %)** and
**7.0 µs of prefill (1.87 %)**. Two consequences.

First, this is why the harness pairs. My arm's entire predicted M5 decode
saving is 32–48 µs (§9.4) — *smaller than the drift of the thing it is measured
against*. An absolute seconds-per-token comparison across sessions could not
resolve this arm at all; only the same-session ratio can.

Second, and less comfortably: pairing cancels drift only to the extent that
drift is common-mode between baseline and candidate. I cannot estimate the
residual from these rows, because all three ran different code. What I can say
is that the prefill baseline alone varies by 1.87 %, prefill carries 25 % of the
score weight, and 0.25 × 1.87 % ≈ 0.47 % of score is the same size as this
arm's whole predicted effect. If that variance is not common-mode, one receipt
does not settle a 0.5 % decode change. The softened rule (§9.6) says a marginal
effect benefits from repetition; this is the quantitative reason it does here.

### 10.5 The ranked contest is currently decided at ~0.05 %

`db8b4df` (another account) was **accepted** at 2.59018571539341, ahead of our
promoted 2.58882784082067 by **+0.0525 %**. The decomposition is instructive:
its decode speedup was slightly *worse* (2.818909 vs 2.820684, −0.06 %) and the
entire gain came from prefill (2.009465 vs 2.001471, +0.40 % ⇒ +0.0997 % of
score at quarter weight). A candidate can take the frontier while losing ground
on the 75 %-weighted axis.

Two things follow. The acceptance bar is now 2.59019, not 2.58883, so the
band between my pre-registered KILL (2.5919) and that bar is a region where a
receipt reports a real `ns` improvement and is still `rejected` for ranking —
exactly the case the programme warns to read separately from correctness and
the floors. And every rejection I can see in the feed is below the *global*
best of the moment rather than the submitting account's own best
(`5d086d0` at 2.58416 from the same account that later won with 2.59019), which
is consistent with a single global bar.

### 10.6 Composing fifteen PRs cost 234 µs of decode

`4b06e93`, "Composed 15-PR Decode + QHOIST Prefill Optimization", is a direct
measurement of the programme's warning against combining unmeasured mechanisms.
Against our promoted frontier it is **+233.8 µs/token on decode (+4.76 %)** and
**+16.1 µs/token on prefill (+8.43 %)**, for −5.43 % of score — while passing
correctness. The composite lost five to seven times this arm's entire predicted
effect. Whatever the individual PRs did apart, together they interfered.

### 10.7 How to read my receipt after this

Unchanged: the advisor's pre-registered bands (GO `ns ≥ 2.6045`, KILL
`ns < 2.5919`) decide the arm, and a bar relaxed after the fact is not a bar.
Added: report ranking status separately from `ns`, because the ranking bar
moved to 2.59019 while I was queued; and treat a single receipt inside the band
as provisional against the 1.87 % prefill-baseline variance above, rather than
as a settled 0.5 % decode result.

## 11. Status report against advisor comment 7 (self-managed dispatch)

Comment 7 (2026-08-06T22:40:46Z) retires the queue-owner model, hands the
submission lifecycle to the submitter, and asks four direct questions. It also
states that this branch "has had no new work commits since `a8d4936`". That is
true of the *remote* branch and false of the work: at the time it was written I
had twelve unpushed commits locally.

I tried to fix that by pushing, and could not. Both student-side channels are
closed by the harness itself:

- `respond_to_issue` refuses a pull request;
- `push_branch` returns `student cannot perform this advisor-owned transition`.

So a student's only durable channel to the advisor is the terminal
`submit_result`, and until that fires the branch is genuinely invisible. This is
structural, not an oversight on my part, and it is the first inheritable lesson
of this section: **an advisor reading a student's remote branch mid-assignment
is reading a stale artefact by construction.** The corollary for the next three
students is that anything the advisor must know before the terminal result has
to be small enough to survive being unsaid, or the assignment has to be revised
to carry it.

### 11.1 The four questions

**Is the candidate committed?** Yes. The submitted surface is exactly one file,
`Sources/MLXFastModel/LagunaLmHeadPrune.swift` (+195/-8), blob
`6e8bde5eee12f095b7642ce3ee6a48e551aa81b7`, unchanged in every commit since
`1a1153d`. The packaged note is blob `8c3c553b54ef187d7af309180f58bde949b84210`
(15,254 B). Both are re-verified at `23a128c` in section 9.7.

**Is it preflighted?** Yes. `senpai/validate-assignment-scope.sh` reports one
submitted path; `senpai/check-editable-budget.sh` reports
`current=2929907/3000000 headroom=70093 growth=8160/262144 files=142`.

**Has it been dispatched?** Yes, repeatedly, and it has not yet been admitted.
Dispatch has been continuously armed since 21:35:58Z. See 11.2.

**If it is waiting, on what?** On the shared solver account's single validation
slot, which was held from 22:09:25Z by `0e43085` -- a *different* Senpai
campaign's candidate (`mlxfast-cedar-20260806-tanjiro-qkv-r1-sg4`, PR #151) --
and before that by my own attempts colliding with it. Section 10.3 establishes
the limit is per solver account, not per campaign or per agent.

### 11.2 Dispatch history, and the cost of the rule I was operating under

I was already operating the self-managed retry model comment 7 now mandates; the
retirement of the queue owner changes nothing about my posture. What it does
change is the interpretation of the wait: the slot contention is real and
mechanical, not a permission I was waiting on.

| what | when (UTC) | outcome |
|---|---|---|
| dispatcher v1 armed | 21:35:58Z | 18 attempts, ~185 s apart |
| attempts 1-17 | 21:35:58Z - 22:25:02Z | `conflict`: 1 submission in flight (limit 1) |
| attempt 18 | 22:28:04Z | `Rate limit reached. Try again in 1914 seconds.` |
| v1 halted | 22:28:26Z | not a whitelisted retryable, stopped |
| feed audited | 22:33Z | **nothing of mine was created** -- verified, not assumed |
| dispatcher v2 armed | 22:34:36Z | running, budget to 01:24:36Z |

Comment 7's point 3 -- check before retrying after an ambiguous response -- is
exactly the failure this audit was run to exclude, and it is the one place a
retry can hurt. I did it by listing the feed and filtering on our account rather
than by trusting the error string.

The self-inflicted part is worth stating plainly: **eighteen blind attempts in
fifty-two minutes bought a 1,914 s rate-limit penalty and no submission.**
A blind retry loop against a capacity limit converts a queue wait into a
strictly longer queue wait. Dispatcher v2 therefore reads the feed first and
only calls `submit` when our account is actually free:

- poll the read-only feed every 120 s; submit only when `morganmcg1` has no
  in-flight row, so submit calls fall from ~20/hour to <=4/hour;
- a forced attempt every 900 s, so a status I failed to classify cannot stall
  dispatch forever;
- rate limits are parsed and honoured (`Try again in N seconds`, plus 30 s);
- unknown statuses count as in-flight, so misclassification delays rather than
  duplicates;
- everything except the in-flight conflict and an explicit rate limit exits
  immediately for inspection.

Both files are committed (`research/maple-fern-submit-dispatcher.sh`,
`research/maple-fern-submit-inflight.py`) so the next three students inherit the
mechanism and not just the anecdote.

### 11.3 What "waiting must not block useful work" actually bought

Comment 7's point 4 is the right rule and I had been following it. The wait has
been spent on work that does not touch the frozen candidate surface -- the
constraint is real, because `mlxfast submit` uploads the working tree, so any
edit to an editable path while dispatch is armed would silently change what gets
submitted. Research-only files are safe; `Sources/` is not. What the wait
produced:

- section 6: the balanced 2x2 profiler-crossed ABBA that **retracts my own r1
  1.8x wall-vs-busy claim** and replaces the headline with -64.5 us of GPU-busy
  and no host-gap component;
- section 9: the wave analysis the softened geometry rule requires, which
  **revised my own M5 prediction down** from 48 us to a 32-48 us band that
  straddles the advisor's 40 us GO gate -- recorded before the receipt, on
  purpose;
- section 10: the public submission feed read as data, which produced three
  programme-level findings I could not have obtained by measuring my own arm
  (baseline drift larger than my effect, the ranking bar moving to 2.59019, and
  a 15-PR composition costing 234 us/token of decode).

### 11.4 One correction to the transfer-factor expectation

Comment 7 predicts the M4->M5 transfer factor "should be close to 1.0" because
the steady decode step is host-independent and every decode dispatch is
hand-written. The dispatch-reachability half of that is right, and I verified it
independently: no decode kernel in this path sits behind a NAX or `#available`
gate, so the M5 runs the same kernel family.

But reachability is not magnitude. Section 9.4 derives the expectation from
occupancy rather than from kernel identity. The control launches 3,136
threadgroups and the shipped arm launches 392; waves are `ceil(TGs/cores)`, so
the saving scales with the *core count*, which is exactly the thing that differs
between the 20-core M4 Pro and the ~40-core M5 Max. Per-wave costs of 0.493 us
(control) and 0.685 us (shipped) give 38.9 us vs 6.9 us at 40 cores, i.e. a
predicted M5 saving near 32 us against 63.7 us measured on M4:

**predicted transfer factor ~ 0.50, not ~ 1.0.**

The reason is not that the kernel changes but that at 40 cores the shipped arm's
392 threadgroups are ~9.8 per core -- still oversubscribed, so it keeps most of
its benefit -- while the control's 3,136 threadgroups drain roughly twice as
fast as they do at 20 cores. A more parallel host shrinks the *absolute* saving
available from removing parallel work it never struggled to schedule.

This is pre-registered here so the receipt adjudicates between two stated
numbers rather than confirming a single one. If the measured factor comes back
near 1.0, my occupancy model is wrong in a way worth more than the arm. If it
comes back near 0.5, the programme should stop reading M4 decode savings as M5
decode savings and start dividing by two. Either way the advisor's framing --
that this number is worth more than the arm itself -- is correct.

### 11.5 The GO gate is eleven times stricter than the contest

Section 10.5 established that the acceptance bar moved to
`ns = 2.59018571539341` (receipt `db8b4df`). Section 4's elasticity is
0.01464 % of score per microsecond removed from `T`. Putting those together
converts every threshold in this arm into microseconds of M5 decode, and into
the M4->M5 transfer factor each one demands against the 63.7 us measured here:

| threshold | ns | over promoted 2.58883 | us of T needed | transfer factor needed |
|---|---|---|---|---|
| ranking acceptance bar | 2.590186 | +0.0525 % | 3.58 | **0.056** |
| advisor KILL boundary | 2.591900 | +0.1187 % | 8.11 | 0.127 |
| advisor GO gate | 2.604500 | +0.6054 % | 41.35 | **0.649** |

The GO gate independently reproduces the advisor's own "40 us" framing to within
1.35 us, which is a useful check that the elasticity constant and the two
thresholds were derived consistently.

Three things follow.

**The arm clears the contest almost regardless of transfer.** Taking the ranking
lead needs 3.58 us on M5 -- a transfer factor of 0.056. My pessimistic
occupancy model predicts 0.50. Even if the wave model is wrong by an order of
magnitude in the unfavourable direction, the receipt still beats the field.

**The GO gate is a different question from winning.** It needs 0.649, which sits
*above* my pre-registered 0.50-0.75 band's midpoint. So the most likely single
outcome of receipt #1 is a submission that takes the ranking lead and lands in
the advisor's ADJUDICATE band rather than clearing GO:

| transfer | us saved | score | ranking | advisor verdict |
|---|---|---|---|---|
| 0.50 (my model) | 31.9 | 2.60090 | beats bar | ADJUDICATE |
| 0.75 (r1 figure) | 47.8 | 2.60693 | beats bar | GO |
| 1.00 (comment 7) | 63.7 | 2.61297 | beats bar | GO |

This is exactly why section 10.7 asks for ranking status and `ns` to be reported
as two separate facts. A `rejected` receipt would mean the score did not beat
the current best; an ADJUDICATE `ns` means the advisor's gate was not cleared.
They can disagree, and under my own prediction they probably will.

**There is a narrow window where the two verdicts invert.** For
`ns` in `[2.59019, 2.59190)` -- 0.066 % of score, 4.52 us of `T`, about 7 % of
the M4 saving -- the submission beats every other solver in the field and the
advisor's pre-registered rule closes the arm as a KILL. I am not asking for the
band to move: it was pre-registered, I accepted it, and a bar relaxed after the
fact is not a bar. I am flagging that the band was calibrated against a
programme-wide "is this worth carrying" standard, while the contest is now being
decided at 0.05 %, and those are no longer the same question. If the receipt
lands in that window I will report it as a KILL by the stated rule and say
plainly that it also took the lead.

## 12. The submission slot is contested, and 120 s of latency loses it

Section 11 reported that the dispatcher was armed and waiting on the shared
account slot. It then lost that slot. This section is the post-mortem, the
measurement that explains the loss, and the fix, because the failure is not
specific to this PR: every Senpai campaign on this account is racing for the
same resource, and a slow submitter can be locked out indefinitely by fast
ones no matter how good its candidate is.

### 12.1 The race, measured

The in-flight limit is one submission per *solver account* (§10.3), and several
campaigns share `morganmcg1`. Two consecutive rows from the feed:

| id | status | createdAt | updatedAt (terminal) |
| --- | --- | --- | --- |
| `0e430857` | rejected | 2026-08-06T22:09:25.005Z | 2026-08-06T23:08:00.367Z |
| `2278bd85` | validating | 2026-08-06T23:08:38.310Z | - |

`2278bd85` is not mine; its note titles it "Clean Ops-Per-Buffer 800: Isolate
MLX_MAX_OPS_PER_BUFFER 200->800 on Promoted Code". The slot was free for
**38.0 s** and another campaign took it.

My v2 dispatcher could not have won. It polled the feed every 120 s, so its
mean detection latency was 60 s, and `mlxfast submit` itself takes ~11 s of
which the "Pushing traces before submission (up to 60 seconds)" banner is only
a small part. Reaction time ~71 s against a 38 s window: the loss was
structural, not bad luck. At a ~60 min mean holding time and a handful of
transitions left in the budget, staying at 120 s meant an expectation of
roughly one win in twelve tries.

### 12.2 Why the feed cannot just be polled faster

I measured the feed rather than guessing at it. `GET
/api/benchmarks/eigenlabs%2Fmlxfast-challenge/submissions`:

- 1,578 rows, **17.3 MB** uncompressed, 1-3 s per request;
- `Accept-Encoding: gzip` is honoured: **8.26 MB in 0.91 s**, a 2.1x saving;
- `?limit=5`, `?status=validating`, `?solver=...`, `?id=...` are all **ignored**
  - each returns the full 1,578 rows;
- `Range: bytes=0-20000` is **ignored** - HTTP 200 with the whole body;
- the feed is **oldest-first**, so aborting the stream early (0.41 s for the
  first 20 KB) never reaches the live rows, which are at the end.

So the obvious "poll harder" fix costs 8.26 MB per tick. At 120 s that is
already **248 MB/hour**; at 15 s it would be 2.0 GB/hour. That is not a
reasonable thing to do to someone else's API for a scoreboard read.

### 12.3 A single-row endpoint exists, and it is 1/1270th the size

Rather than accept the trade, I probed for a cheaper read. Five candidates,
one of them useful:

| path | result |
| --- | --- |
| `benchmarks/<bench>/submissions/<id>` | 404 |
| **`submissions/<id>`** | **200, 13.6 KB, 0.63 s, `{"submission": {...}}`** |
| `benchmarks/<bench>/submissions?id=<id>` | 200, 17.3 MB (filter ignored) |
| `benchmarks/<bench>/leaderboard` | 404 |
| `benchmarks/<bench>` | 200, 11.4 KB, 0.61 s |

`GET /api/submissions/<id>` returns exactly the same 21-key record as a feed
row, including `status`, for **13.6 KB**. That is 1/1270th of the feed, and it
is all the dispatcher needs once it knows *which* row is blocking the account.

`GET /api/benchmarks/<bench>` is a second useful cheap read and worth recording
for the programme: it carries `currentBestScore`, `currentBestMetrics`,
`baselineScore`, `baselineMetrics`, `editablePaths`, `maxSubmissionBytes`, and
`sourceRef`. It independently confirms the numbers §10.5 had to derive by
scanning the whole feed - `currentBestScore = 2.59018571539341` and
`sourceRef = 26b465352561f2fb18d0e7734353650ec94a9417` - at 11.4 KB instead of
17.3 MB. Future work that needs the acceptance bar should read this, not the
feed.

### 12.4 Two-tier dispatch: 25x lighter *and* 24x faster

v3 splits reads by purpose. Discovery still reads the feed, but only to learn
the id of the row blocking this account. That row is then watched through the
single-row endpoint every 5 s. Discovery repeats only when the watch goes
terminal, when a submit conflicts, or every 900 s as a staleness guard.

| | v2 (feed @ 120 s) | v3 (watch @ 5 s) |
| --- | --- | --- |
| bytes per tick | 8.26 MB gzipped | 13.6 KB |
| bytes per hour | 248 MB | 9.8 MB |
| requests per hour | 30 | 720 |
| mean detection latency | 60 s | 2.5 s |
| reaction time (detect + upload) | ~71 s | ~14 s |
| vs the observed 38 s window | loses | wins |

This is the rare case where the polite option and the fast option are the same
option: v3 is **~25x lighter on the server** and **~24x more responsive**. The
request count rises, but each request is small and served from what is
evidently a single-row lookup rather than a full table scan.

### 12.5 Keeping submit attempts rare

Detection got cheap; uploads did not. §11.2 records that 18 blind `submit`
retries in 52 min tripped a server rate limit and cost 1,914 s of enforced
silence, so v3 keeps uploads bounded independently of poll rate:

- at most one attempt per observed transition;
- a 45 s floor between attempts triggered by a *detected* free slot;
- a 240 s floor for the blind forced attempt, which fires every 1,800 s so a
  misread status cannot stall the dispatcher;
- a 900 s cooldown after three consecutive "feed said free, server said busy"
  responses, which is the only state that could otherwise spin;
- during any hold window with a free account the loop naps instead of
  re-reading the feed, so a cooldown cannot quietly spend 249 MB doing nothing.

Worst case is ~10 attempts/hour, comfortably below the ~18-21/hour that tripped
the limit. Steady state is far lower: one attempt per transition.

### 12.6 The stub test earned its keep

I tested the state machine against a stub helper before arming it, and the
first run failed in a way no amount of re-reading would have caught quickly.
The discovery branch was written as

```bash
status_out=$("$INFLIGHT" 2>&1)
last_discover=$now
fi
status_rc=$?
```

so `$?` reported the *assignment's* exit status, not the helper's. Discovery
therefore always returned 0, "account blocked", and the dispatcher would have
watched forever and never submitted - a silent failure whose only symptom is
budget exhaustion three hours later. Capturing `status_rc` inside each branch
fixes it. Both helper modes were then verified against live rows (`2278bd85`
validating -> in flight, `0e430857` rejected -> terminal) and the loop against
stubs for the watch-then-fire path, the lost-race streak, the cooldown, and the
hold-window nap.

The general lesson for this programme: a dispatcher that fails *closed* looks
exactly like a dispatcher that is patiently waiting. Anything that waits should
be exercised against a forced transition before it is trusted with a budget.

## 13. How noisy is the official instrument, and what should we adjudicate on

Written and committed *before* the receipt for `99b71258` landed. Everything
below is derived from the public submission feed alone, using the cached copy
fetched at 2026-08-06T23:2xZ (1,579 rows, of which 1,088 carry populated
`officialMetrics` and an `officialScore`, spanning 07-24 to 08-06). It is
recomputed end to end by `sec13_numbers.py`; every figure quoted here is one
of its printed lines.

Section 11.5 pre-registered a merge decision on a single number from a single
official run. That is only sound if the run-to-run spread of that number is
small compared with the band. Nobody in this programme had measured that
spread. This section measures it, and the answer changes which statistic the
decision should be read from.

### 13.1 Finding replicates in a feed that hides them

The obvious approach - group by `submissionCommitSha` and treat a repeated SHA
as a replicate - does not work. Every submission is given a **unique**
`submissionCommitSha`, because the value is a server-side snapshot of the
uploaded surface, not the solver's commit. Grouping 1,088 rows by SHA yields
zero groups of size 2.

What does work is to cluster on **(solver, calendar day)** and keep clusters of
at least four rows whose candidate decode seconds span less than 1.5 %. A
solver iterating within one day submits near-identical trees; a candidate
decode spread under 1.5 % means no arm in the cluster moved the clock much.
Within such a cluster the spread is dominated by the instrument, not by the
code. This yields **27 clusters covering 253 rows**.

This over-estimates noise slightly - real (small) code differences remain
inside a cluster - so every sigma below is an upper bound. That is the safe
direction for a merge decision.

### 13.2 The noise table

Median across-cluster CV, and the pooled within-cluster CV:

| quantity | median cluster CV | pooled CV |
|---|---|---|
| candidate decode s/tok | 0.294 % | 0.302 % |
| baseline decode s/tok | 0.249 % | 0.275 % |
| candidate prefill s/tok | 0.912 % | 3.001 % |
| baseline prefill s/tok | 1.949 % | 1.974 % |
| `decode_speedup` | 0.334 % | 0.420 % |
| `prefill_speedup` | 2.263 % | 3.755 % |
| **`officialScore`** | **0.753 %** | **1.076 %** |

The baseline rows are the cleanest possible replicate: the harness runs the
*same pinned baseline* in every session, so its 0.249 % / 1.949 % is the
instrument with the code held exactly constant. The candidate rows agree with
it. The measurement is therefore about a quarter of a percent on decode and
about two percent on prefill, and the published score inherits both.

### 13.3 The same-session pairing cancels nothing

The whole point of running baseline and candidate back to back is supposed to
be that a slow session slows both and the ratio survives. It does not happen.
Within a cluster, the correlation between the candidate's deviation from the
cluster mean and its own paired baseline's deviation is

```text
rho(candidate, baseline) decode  = -0.059      (n = 253)
rho(candidate, baseline) prefill = -0.082      (n = 253)
```

Zero, and if anything slightly negative. The paired baseline is a
statistically independent second draw. Dividing by it therefore **adds**
variance rather than removing it: `decode_speedup` has CV 0.334 %, which is
almost exactly `sqrt(0.294^2 + 0.249^2) = 0.385 %` of independent draws rather
than the near-zero a working pairing would give.

The practical consequence is immediate and useful: a statistic built with
**fixed** normalisers is strictly better than the published ratio. Defining

```text
ns  = (0.013890 / decode)^0.75 * (0.0003845 / prefill)^0.25
nsd = (0.013890 / decode)^0.75
```

and re-measuring the same 27 clusters gives

| statistic | median cluster CV |
|---|---|
| `officialScore` | 0.753 % |
| `ns` (fixed normalisers) | 0.425 % |
| `nsd` (decode term only) | 0.220 % |

`ns` is 1.8x quieter than the published score and `nsd` is 3.4x quieter, purely
by refusing to divide by a noisy independent draw. Nothing is lost: the
baseline is pinned code, so a fixed normaliser measures the same physical
quantity.

### 13.4 Where the score's variance actually comes from

Propagating the four component CVs through `d^0.75 * p^0.25`:

| component | share of score variance |
|---|---|
| **baseline prefill** | **63.6 %** |
| candidate prefill | 13.9 % |
| candidate decode | 13.0 % |
| baseline decode | 9.4 % |

(predicted total sd 0.611 %, against the 0.753 % measured directly - the gap is
the small real code variation left inside clusters.)

Almost two thirds of the noise in a decode-weighted score comes from the
*baseline's prefill*, a quantity that has nothing to do with the candidate and
which the candidate cannot influence. Prefill carries only a quarter of the
exponent, but its baseline is 8x noisier than the decode baseline, and
`1.949 % * 0.25` beats `0.249 % * 0.75` comfortably.

### 13.5 Retraction: section 10's baseline drift

Section 10 reported that "the official baseline drifts 73.4 us / 0.53 % over
17 h" and suggested treating cross-session comparisons with suspicion on that
basis. **That claim is withdrawn.** It was inferred from two draws. With 764
draws over seven days:

```text
2026-07-31  n=148  13.84602 ms  sd 0.229 %
2026-08-01  n=142  13.85142 ms  sd 0.262 %
2026-08-02  n=143  13.85770 ms  sd 0.276 %
2026-08-03  n=111  13.86639 ms  sd 0.267 %
2026-08-04  n=113  13.86526 ms  sd 0.253 %
2026-08-05  n= 64  13.85558 ms  sd 0.233 %
2026-08-06  n= 43  13.85921 ms  sd 0.176 %
```

The standard deviation of the daily means is **0.052 %**, against a median
within-day sd of 0.253 %. Under pure white noise the daily means would scatter
by 0.024 %, so there is a real day-to-day component - but it is 0.05 %, an
order of magnitude below the 0.53 % section 10 claimed, and small enough to
ignore next to the 0.25 % single-draw noise. The lag-1 autocorrelation of the
whole ordered series is **+0.060**. The instrument is essentially white.

This retraction matters in our favour: it licenses comparing our candidate's
raw seconds against a receipt from a *different* session, which is exactly what
section 13.7 needs.

### 13.6 The bar we must clear is an inflated order statistic

A score is promoted only if it exceeds the running best. That is a maximum, so
the accepted rows are systematically the lucky draws. Against the median
`prefill_speedup` of the last 300 scored rows (1.94756), the last eight
accepted rows all drew prefill in the 77th-100th percentile:

| accepted row | score | its `pspd` (pct) | score at the median draw | inflation |
|---|---|---|---|---|
| `6da9f031` | 2.51015 | 1.99157 (p77) | 2.49616 | +0.56 % |
| `2ca10d56` | 2.51381 | 2.01232 (p93) | 2.49333 | +0.82 % |
| `0a9d439b` | 2.52763 | 2.01222 (p93) | 2.50707 | +0.82 % |
| `21f1d1a3` | 2.52824 | 2.02068 (p97) | 2.50506 | +0.93 % |
| `8415f63c` | 2.53921 | 2.01635 (p96) | 2.51727 | +0.87 % |
| `46eeccf0` | 2.55231 | 2.06341 (p100) | 2.51570 | +1.46 % |
| `97a5090c` | 2.58883 | 2.00147 (p84) | 2.57121 | +0.69 % |
| `db8b4df1` | 2.59019 | 2.00947 (p91) | 2.57000 | +0.79 % |

Eight for eight above the median is not a coincidence; it is the definition of
a running maximum on a noisy instrument. The bar we are asked to clear is
therefore roughly **0.8 % higher than the underlying code deserves**, and the
excess is drawn from the one axis with 2 % noise.

The sharpest illustration is the current record itself. `db8b4df1` displaced
our own `97a5090c` by +0.052 % of score while being **slower on decode**:

```text
             score      dspd       pspd       candidate decode
db8b4df1   2.59019   2.81891   2.00947      4.92458 ms
97a5090c   2.58883   2.82068   2.00147      4.90837 ms
delta      +0.052 %  -0.063 %  +0.399 %     +16.2 us (worse)
```

It won the crown on a +0.399 % prefill draw, comfortably inside the 2.263 %
noise of that axis, while losing on the axis that carries three quarters of the
weight. On the decode-only statistic `nsd`, `97a5090c` (2.18184) is still
**+0.247 % ahead** of the row that displaced it.

### 13.7 The pre-registered band lies inside one sigma

Expressing section 11.5's thresholds as multiples of the 0.753 % single-draw
sd of `officialScore`:

| threshold | value | vs bar | sigma |
|---|---|---|---|
| ranking bar | 2.59019 | +0.000 % | 0.00 |
| KILL | 2.5919 | +0.066 % | 0.09 |
| GO | 2.6045 | +0.553 % | 0.73 |

The entire GO/KILL band is 0.73 sigma wide and sits inside the first sigma of
the instrument. Worse, the *reference* (the bar) is itself a single draw, so
the relevant sd for the comparison is `0.753 % * sqrt(2) = 1.065 %` and the
whole band shrinks to half a sigma.

Section 11.4 predicted a transfer factor near 0.50 and the advisor predicted
near 1.00. A full-transfer effect is 63.7 us * 0.01464 %/us = **0.933 %** of
score. So:

| transfer | score effect | in sigma of one paired comparison |
|---|---|---|
| 0.50 | +0.467 % | 0.44 |
| 0.75 | +0.700 % | 0.66 |
| 1.00 | +0.933 % | 0.88 |

**A single receipt read on `officialScore` cannot separate our hypothesis from
the advisor's, and cannot reliably separate GO from KILL.** The standard error
on the transfer factor from one score receipt is +-1.14. That is not a
measurement; it is a coin flip with extra steps.

### 13.8 Pre-registration: adjudicate on the decode axis

The fix does not need another run. It needs a better statistic from the same
run. The mechanism under test is a decode-path change with a deliberately flat
prefill, so the 2 %-noise prefill axis contributes nothing but variance. Read
the same receipt on the decode axis instead:

| statistic | 1 sd | sd of a paired difference | t=0.50 | t=0.75 | t=1.00 | sd on t |
|---|---|---|---|---|---|---|
| `officialScore` | 0.753 % | 1.065 % | 0.44 | 0.66 | 0.88 | **1.14** |
| `ns` (fixed norms) | 0.425 % | 0.601 % | 0.78 | 1.16 | 1.55 | 0.64 |
| `decode_speedup` | 0.334 % | 0.472 % | 1.32 | 1.97 | 2.63 | 0.38 |
| candidate decode / `nsd` | 0.294 % | 0.416 % | 1.50 | 2.24 | 2.99 | **0.33** |

A full-transfer effect is 1.243 % of decode. The decode axis therefore
estimates the transfer factor to **+-0.33** where the score axis manages
**+-1.14** - a 3.5x tighter measurement from the identical run, obtained purely
by not dividing by two noisy quantities that the change does not touch.

I am therefore pre-registering, before the receipt exists, a **secondary
adjudication**:

- The **primary** verdict stays exactly as section 11.5 set it: GO if
  `officialScore >= 2.6045`, KILL if `< 2.5919`. It is not moved, widened, or
  reinterpreted, and it is what determines ranking.
- The **secondary** statistic is the candidate's own decode seconds per token,
  equivalently `nsd`, compared against `97a5090c`'s receipt
  (`4.9083720703125 ms`, `nsd = 2.18184340`). The point estimate of the
  transfer factor is `(nsd_ours / 2.18184340 - 1) / 1.243 %`, with a 1-sigma
  interval of +-0.33.
- Where the two disagree, both are reported. The score axis decides ranking;
  the decode axis decides what we believe about the mechanism.

`analyze_receipt.py` computes all of these and prints them side by side. Its
stale `BEST_NS` has been corrected to the authoritative
`currentBestScore = 2.59018571539341` (source ref
`26b465352561f2fb18d0e7734353650ec94a9417`, confirmed against the benchmark
endpoint), and it now uses the cheap single-row endpoint instead of pulling the
17 MB feed.

### 13.9 Which generation is our base, and the confound in the reference

Before trusting any cross-session reference I had to settle a worry: our recent
account rows cluster at `decode_speedup` 2.67-2.73 while the frontier sits at
2.82. If our fork's base were a 2.70-generation tree, the section 11.5 band
would be unreachable by construction and the receipt would be rejected on
ranking whatever the mechanism did.

It is not. Three independent lines agree:

1. `97a5090c` - the 2.82068 accepted row - is **ours**. Its note carries this
   campaign's attribution block and our exact research host (M4 Pro, 48 GiB, 20
   GPU cores), and its mechanism is the attention scale-plane halving merged
   here as `62ca3a9` (PR #80, `maple-frieren/attn-scale-pairwise`), which is an
   ancestor of our base `2443984`.
2. A third-party submission states it outright: `2278bd85`'s note says "the
   current leaderboard #1 score is 2.5888 (maple campaign, submission
   97a5090)".
3. The low rows are other campaigns. `c95b4e49` (dspd 2.71183) names campaign
   `mlxfast-birch-20260805`; `0e430857` (2.67122) is a cedar experiment;
   `db8b4df1` (the current record) is attributed to a different model entirely
   and says it starts from "Morgan's promoted frontier `3e165fa5`", which is
   `97a5090c`'s snapshot. Several Senpai campaigns share one solver account, so
   an account-level view of `decode_speedup` mixes forks.

So our base is on the 2.82 generation and the band is reachable.

The reference does, however, carry a confound that must be stated plainly.
`97a5090c` is 6 promoted maple merges behind our base: `#82`, `#85`, `#104`,
`#105`, `#110`, `#101`, `#103`. None of those has an M5 receipt - `97a5090c`
at 05:14Z is the campaign's most recent one. Our receipt is therefore the first
M5 datum for the current maple frontier, and any transfer factor computed
against `97a5090c` is

```text
t_measured = t_ours + (M5 effect of six promoted merges) / 63.7 us
```

This inflates or deflates the estimate by an unknown amount and it is not
something a tighter statistic can fix. It is an attribution problem, not a
noise problem. The clean resolution is cheap and available: the shipped code
keeps both arms behind `DARKBLOOM_LMHEAD_ROWMAJOR_REFINE`, so **a second
submission of the identical tree with the compiled default flipped to the old
arm isolates our mechanism exactly**, with the six merges present in both arms
and therefore differenced away. On the decode axis that A/B pair has an effect
of `1.243 % * t` against a paired sd of 0.416 %, i.e. 1.5 sigma at t=0.50 and
3.0 sigma at t=1.00. That is the experiment worth the second receipt, and I
recommend it over any further single-arm submission.

### 13.10 What this says about the programme

Three habits should change, and none of them costs a run.

1. **Stop reading `officialScore` as if it were exact.** One draw is +-0.75 %.
   Two of this campaign's calibration sets already showed it - `f8502e12` /
   `71586bcf` / `f3cda678` at 2.48558 / 2.51595 / 2.50895, and `5d522d6a` /
   `5e0e9cd1` / `c210d200` at 2.49147 / 2.50009 / 2.51474, both identical trees
   submitted three times, both spreading about 1.2 %. Those replicates were
   collected and then not used as a noise model. This section is that model.
2. **Prefer fixed normalisers.** The paired baseline is an independent draw
   (rho = -0.06), so dividing by it is strictly harmful for internal
   comparisons. Rank on `officialScore` because the organiser does; reason on
   `ns` or `nsd`.
3. **Design submissions as differences, not as single points.** The instrument
   is white and stable to 0.05 % across days, so a matched A/B pair of
   submissions on the same tree is a far better use of two receipts than two
   different candidates measured against a moving, order-statistic-inflated
   bar. The GO/KILL band in section 11.5 was written before this was known; it
   is honoured as pre-registered, but a band 0.7 sigma wide should not have
   been set on a single point, and the next one should not be.

### 13.11 Correction, before the receipt: the band is on `ns`, and my sigma was three times too large

Written after 13.1-13.10 and still before the receipt for `99b71258` landed.
Re-reading the advisor's authorisation comment against my own arithmetic
turned up two errors in the section above, one of which inverts its main
recommendation. Both are corrected here rather than edited into the text
above, so the order in which I knew things stays auditable.

**Error 1: I put the GO/KILL band in the wrong units.** The advisor wrote
"judge by `ns`, never `officialScore`", gave the anchor as
`ns = 2.5982163` for receipt `97a5090`, and set GO and KILL at `+-0.243 %` of
it. My fixed-normaliser statistic evaluated on that receipt is

```
ns(97a5090c) = (0.013890/d)^0.75 * (0.0003845/p)^0.25 = 2.5982163
```

which reproduces his anchor to every digit he quoted, so his `ns` and mine are
the same quantity. The thresholds then check out exactly:

| anchor | GO 2.6045 | KILL 2.5919 |
|---|---|---|
| **`ns`(97a5090c) = 2.5982163** | **+0.242 %** | **-0.243 %** |
| `officialScore`(97a5090c) = 2.5888278 | +0.605 % | +0.119 % |
| `currentBestScore` = 2.5901857 | +0.553 % | +0.066 % |

Only the first row is the symmetric `+-0.243 %` he described. The band lives
on `ns`. Section 13.8's sentence "the primary verdict stays exactly as section
11.5 set it: GO if `officialScore >= 2.6045`" is therefore wrong, and so is
the 13.7 table that measures those thresholds against the ranking bar. The
near-coincidence that `KILL = 2.5919` sits 0.066 % from `currentBestScore =
2.5901857` is what let the mistake survive; they are different quantities that
happen to land close together.

This matters. On the `ns` axis the two thresholds are symmetric about our own
promoted receipt and say something clean - "did we move `ns` by more than a
quarter of a percent in either direction". Read as `officialScore` thresholds
they are lopsided and mostly a statement about a bar set by another campaign.

**Error 2: my cluster CVs are contaminated, and the contamination is entirely
on the candidate axes.** The advisor's noise numbers, "pooled cv 0.149 % vs
0.553 %", reproduce as the two documented identical-tree replicate triplets:
mean per-triplet CV 0.553 % on `officialScore` and 0.128 % on `ns`, pooled
over 4 dof 0.559 % and 0.138 %. Those six rows are the gold standard - the
notes say so in as many words ("an identical tree, submitted twice, to measure
the official run-to-run noise floor"), and all six share `golden_hash
be7738fccd6a` and `weights_hash aff99430`. I dismissed them in 13.10 as
"collected and then not used"; in fact they were used, by him, correctly.

Both estimates on the same statistics:

| statistic | triplets (identical trees) | my 27 clusters | ratio |
|---|---|---|---|
| baseline decode s/tok | 0.243 % | 0.249 % | 1.02 |
| baseline prefill s/tok | 2.457 % | 1.949 % | 0.79 |
| candidate decode s/tok | 0.197 % | 0.294 % | 1.49 |
| candidate prefill s/tok | 0.195 % | 0.912 % | 4.68 |
| `officialScore` | 0.559 % | 0.753 % | 1.35 |
| `ns` | 0.138 % | 0.425 % | 3.08 |
| `nsd` | 0.148 % | 0.220 % | 1.49 |

The **baseline** rows agree between the two methods to within 20 %, which they
must, because no candidate code can move the baseline arm. The **candidate**
rows do not, and candidate prefill disagrees by 4.7x. That is the signature of
exactly the bias my clustering rule allows: I required candidate *decode* to
span under 1.5 % within a cluster and put no constraint at all on candidate
prefill, so a cluster of a solver's day happily contains arms with genuinely
different prefill. My candidate-side CVs are upper bounds containing real
code differences; the triplets measure the instrument. **The triplet numbers
supersede mine wherever they disagree, and `analyze_receipt.py` now carries
them.**

**What this does to the conclusions above.**

Strengthened:

- The variance budget argument gets stronger, not weaker. On identical trees
  the candidate prefill measurement is quiet (0.195 %) while the *baseline*
  prefill is wild (2.457 %). Propagating through
  `score = dspd^0.75 * pspd^0.25`, the baseline prefill draw alone accounts
  for about 84 % of the variance of `officialScore`, against the 64 % I
  estimated in 13.4.
- The pairing result survives and sharpens: within-triplet
  `rho(candidate, baseline)` is **-0.346** on decode and **+0.076** on
  prefill. Dividing by the paired baseline still adds variance rather than
  cancelling it, and the measured `decode_speedup` CV of 0.361 % is exactly
  what `sqrt(0.197^2 + 0.243^2 - 2*(-0.346)*0.197*0.243)` predicts.
- 13.6 is untouched: the bar being an inflated order statistic is arithmetic
  on published rows, not a noise estimate.
- 13.5's retraction of the drift claim is untouched, and now matters more:
  the triplets all sit inside two hours of 2026-08-04, so on their own they
  bound only short-timescale noise. The 0.052 % day-to-day figure is what
  licenses using them for a comparison against a receipt from 08-06.

Reversed:

- **13.8's central recommendation is withdrawn.** I argued that the decode
  axis was 3.4x tighter than `ns` and should be the statistic of record. On
  identical trees `ns` (0.138 %) and `nsd` (0.148 %) are indistinguishable -
  ratio 0.94x - because dropping a candidate prefill term that is itself only
  0.195 % noisy buys nothing. The 3.4x I measured was 3.4x less contamination,
  not 3.4x less noise. The real and large gain, 4.05x, is `officialScore` ->
  `ns`, which is precisely the substitution the advisor prescribed.
- **13.7's "the band is a coin flip" is withdrawn.** Against the correct axis
  and the correct sigma the pre-registered band is a real threshold:

| | vs sd | sd of paired difference | GO in sigma | full transfer in sigma |
|---|---|---|---|---|
| `ns`, triplet sd 0.138 % | 0.138 % | 0.195 % | **+1.24** | **+4.78** |
| `ns`, my cluster sd 0.425 % | 0.425 % | 0.601 % | +0.40 | +1.55 |
| `officialScore`, triplet sd 0.559 % | 0.559 % | 0.791 % | +0.31 | +1.18 |

  A full-transfer effect is `0.933 %` of `ns`, so a single receipt read on
  `ns` estimates the transfer factor with **sd 0.209** - better than the 0.33
  I claimed for the decode axis and five times better than reading
  `officialScore`. The advisor's instrument choice was right and my proposed
  replacement was a step sideways at best.

**The pre-registration, restated correctly and still before the fact.**

- **Primary, unchanged from the advisor's r2 authorisation:** GO if
  `ns >= 2.6045`, KILL if `ns < 2.5919`, adjudicate the middle on the transfer
  factor. `ns` is the fixed-normaliser statistic above, referenced to
  `ns(97a5090c) = 2.5982163`.
- **Transfer factor:** `t = (ns/2.5982163 - 1) / 0.933 %`, with 1 sigma
  **+-0.21** from the identical-tree replicates. Section 11.4 predicted
  `t ~ 0.50`; the advisor predicted `t ~ 1.00`. Those are 2.4 sigma apart on
  this axis, so one receipt genuinely does discriminate them.
- **Corroborating:** `nsd` and the raw candidate decode microseconds against
  `97a5090c`'s `4.9083720703125 ms`, 1 sigma 0.197 %. Reported alongside, not
  instead.
- **Ranking:** `officialScore` against `currentBestScore = 2.59018571539341`
  decides whether the receipt is accepted and promoted. It is reported and it
  is what the leaderboard sees, but per the advisor it does not decide the
  arm.
- Unchanged: the six-merge confound in 13.9 still applies to every
  cross-receipt comparison here, and the flipped-default A/B remains the way
  to remove it. On the corrected `ns` axis that A/B separates `t = 0.5` from
  `t = 1.0` by 2.4 sigma, so it is worth the second receipt for a sharper
  reason than I gave in 13.9.

13.10's third habit stands, with its first two rewritten by this section:
prefer fixed normalisers because the *baselines* are the noisy part, not
because pairing is theoretically impure; and stop reading `officialScore` as
exact, because one draw is +-0.56 %, not +-0.75 %. The honest summary of
sections 13.1 to 13.10 is that clustering was a reasonable way to look for
replicates in a feed that hides them, that it recovered the baseline-side
noise correctly, and that it should have been checked against the six rows
where the answer was already known before it was used to argue with the
advisor's band.
