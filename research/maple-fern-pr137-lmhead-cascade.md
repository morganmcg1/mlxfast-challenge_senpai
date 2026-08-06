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
   busy time (M4, per-kernel census)** / **110–114 µs of decode wall time (M4,
   ABBA)** with **bit-identical logits**.

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

The wall saving exceeds the GPU-busy saving, which is consistent with removing
7/8 of the dispatched threads also shortening the tail that the next dependent
encoder waits on.

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

## 6. What I did not do

- Did not touch routed/shared MoE gather-GEMM or any `_nax` kernel (tanjiro,
  frieren) or `Sources/MLXFastTransform` (nezuko).
- Did not implement the S3→S4 prologue fold. It is bit-exact and legal but worth
  only ~2.9 µs on M4, and it would couple two stages whose separation currently
  makes the census readable. Worth revisiting only if it can be bundled with
  another S4 change.
- Did not add a liveness-adaptive dispatch that would pick the old geometry when
  survivors exceed ~12.5 %. The 24× margin does not justify the branch today,
  but it is the natural guard if the pruner's threshold policy ever loosens.
