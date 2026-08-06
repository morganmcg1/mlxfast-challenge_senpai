# PR #158 — decode dead time: where the gap actually goes

Student `maple-nezuko`, assignment `maple-2026-08-06n-decode-dead-time`, `r1`.
Base `codex/mlxfast-maple-20260804-advisor` @ `9dd2eec38a11d0e0bc7bcdbc5aec46e3436f284f`.
Host: Apple M4 Pro, 20 GPU cores, 48 GiB (low-memory startup profile), macOS
26.5.2. Every timing below is M4 and therefore **directional only**; the M5 is
authoritative. No submitted file is modified by this report — §1.1, §1.2 and §2
are `research/`-only.

## 0. Headline answers

1. **`gpu_busy_union` is per *command buffer*, not per dispatch.** The GPUPROF
   hook records one span per committed `MTLCommandBuffer`. At the shipped
   batching policy that is ~9 dispatches per span, so `sum == union` proves only
   that command buffers on one serial queue do not overlap each other. It is
   *vacuous* as evidence about concurrency between dispatches. §4.1's reading
   (a) ("zero concurrency") was never measured; the instrument could not see it.
2. **Measured with an instrument that *can* see it, decode really is
   ~serial.** Forcing a hard serialization boundary every 2 dispatches instead
   of every ~9 raises total GPU busy time by 0.56 %; forcing one per dispatch
   (zero possible overlap) raises it by 5.8 % net of per-buffer overhead. So
   reading (b) is right in substance, but for a different reason than claimed,
   and the honest bound on hidden work is "≤ ~0.6 %, worst case ~6 %", not zero.
3. **The quoted §1.1 row is arithmetically impossible and must be retired.**
   `9.816 / 9.492 / 9.498 / 0.322` has `union > sum` (9.498 > 9.492), which the
   instrument cannot produce, and `9.816 − 9.498 = 0.318 ≠ 0.322`. It was
   hand-transcribed. A fresh self-consistent row is in §1.1.
4. **The §1.1 answer is PROPORTIONAL, not absolute — and there is no host-side
   pool either way.** The gap is real (hook cost `+0.11 %`, inside run-to-run
   spread) and is ~265 ± 20 µs. Across 19 configurations spanning 9.2 % of
   `gpu_busy`, `gap ~ 1 + busy` has slope **+0.059 ± 0.019**, which **rejects
   the absolute model at 3.1σ** and cannot reject proportional (0.032, 1.4σ).
   A lever that adds 90 dispatches at constant busy moves the gap by
   **−0.12 ± 0.22 µs/dispatch — a null** — and the per-buffer coefficient is
   ≤0.6 µs, against the 1.33 µs/CB the assignment assumed. My earlier
   "absolute" reading came from sweeps whose busy range was only 6.8 %, where
   the two models differ by less than the ±19.5 µs replicate noise. The
   practical point survives either reading: the gap is 3.01 % of the step, the
   two models differ by 0.33 % of wall on a 10 % busy cut, and **no wall time is
   recoverable without removing GPU work.** §1.1.e.
5. **§1.2's pre-registered kill rule fires for both kernels.** `gate_sp` runs at
   100 % useful-lane fraction with no divergence; `residual_rms_router`'s idle
   half is a compile-time whole-simdgroup guard, so there is nothing for a
   ballot/ctz compaction to compact. The #137 re-geometrization does not apply.
   §1.3 is therefore not entered and §2 fires.
6. **§2's correction is not the one the assignment expected.** Because hiding is
   ~absent, the 10 HIGH-RISK rows are *not* over-attributed by overlap. They are
   over-attributed by a different mechanism: a measured **~1.9 µs per-dispatch
   GPU floor** that does not shrink when the kernel's work shrinks. Only
   *removing a dispatch* recovers the floor; making a kernel cheaper recovers
   only its work-proportional part. That floor is 771 µs, **9.6 % of the
   8007 µs step** — three times the host gap. The corrected census is in §2.

---

## Method note: the instrument

`Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/device.{cpp,h}` carry a
research-only `DARKBLOOM_GPU_PROFILE` hook (commit `1604524`, additions only).
`record()` is called from the command-buffer completion handler and prints one
`GPUPROF <gpuStart> <gpuEnd> <dispatches> <kernels>` line **per committed
`MTLCommandBuffer`**. `DARKBLOOM_GPU_PROFILE_SPLIT=k` caps dispatches per buffer
at `k` (`k=0` = shipped policy).

Both files are in `editablePaths`, so the hook is **never committed**; it is
applied, built, and reverted before the worktree is committed. The binary under
test (`.build-worker/release/mlxfast-runtime-worker`) retains it while the
source tree is clean.

The consequence that matters: at `k=0`, `gpu_busy_union` cannot see inside a
buffer. It cannot see intra-buffer idle and it cannot see intra-buffer
concurrency. `sum == union` at `k=0` is a statement about ~45 objects on one
serial queue, and it is true by construction.

Two facts about the encoder policy bound what could be hidden. MLX opens every
compute encoder with `MTL::DispatchTypeConcurrent`
(`Vendor/.../metal/device.cpp:548`) and inserts barriers only on real RAW/WAR
hazards (`device.cpp:318-375`). So dispatches inside one buffer *are* permitted
to overlap; nothing in the API forces the serial reading. That is what makes
the `SPLIT` experiment in §1.1 meaningful: raising `k` from 1 to 9 hands the
driver progressively more overlap opportunity, and if any were being taken, GPU
busy time would fall.

All GPU work ran through `run_training` with the 40 °C thermal gate, one
model-holding process at a time, cool idle 39–41 °C.

---

## 1.1 Is the host gap absolute or proportional?

### 1.1.a The two rows

Same host, same thermal policy, same profiler settings, `DARKBLOOM_GPU_PROFILE=1`,
`SPLIT=0` (shipped batching). Steady decode step, median over the profiled
window.

| row | wall | `gpu_busy_sum` | `gpu_busy_union` | gap | gap % | CBs | dispatches |
|---|---|---|---|---|---|---|---|
| original (`nezuko-decode-roofline.md:193-202`) | 9.816 | 9.492 | 9.498 | 0.322 | 3.3 % | 45 | 406 |
| **current base `9dd2eec3`, arm a1** | **8.267** | **8.016** | **8.016** | **0.251** | **3.04 %** | **45** | **406** |
| current base `9dd2eec3`, arm a2 | 8.220 | 7.985 | 7.985 | 0.235 | 2.86 % | 45 | 406 |

**First: the original row is arithmetically impossible and I am retiring it.**
It reports `union` (9.498) *greater than* `sum` (9.492). The instrument takes
`union` as the measure of a union of intervals whose total length is `sum`;
`union > sum` cannot be produced by any input. And `9.816 − 9.498 = 0.318`, not
the quoted `0.322`. The row is a hand transcription with at least two errors,
and the "6 ns agreement" repeated three times in the research state
(`CURRENT_RESEARCH_STATE.md:203-206`) descends from it. In the fresh rows above
`sum` and `union` agree **exactly, bit for bit**, which is what the code
actually produces at `SPLIT=0` — and headline answer 1 explains why that
agreement is uninformative.

### 1.1.b Verdict: the gap is PROPORTIONAL, and the additive host pool does not exist

Short answer, stated first because it is the opposite of what I believed after
the first three probes: across 19 profiled configurations spanning 9.2 % of
`gpu_busy`, the gap tracks `gpu_busy` with slope **+0.059 ± 0.019 ms per ms**,
which **excludes the absolute model (slope 0) at 3.1σ** and sits 1.4σ from the
pure-proportional prediction (0.032). The dispatch-count and buffer-count
coefficients, measured on levers that move those counts *at constant busy*, are
both statistically zero. Full evidence and the fit are in **§1.1.e**; this
subsection records the three structural probes that constrain the answer.

The operationally important part is that **this verdict does not open a pool.**
The gap is 3.01 % of the step. Under the absolute model a 10 % cut in
`gpu_busy` buys 10.74 % of wall; under the proportional model it buys 11.11 %.
The two readings of §4.1 differ by **0.33 % of wall**, and no reading of them
makes the gap a separate additive quantity that can be attacked without
reducing GPU work. The assignment's premise — "if absolute, the gap is a
separate pool worth attacking" — fails on its antecedent *and* would have been
worth at most 3.0 % if it had held.

Comparing the two rows in §1.1.a alone is not a clean test (different binaries,
and one of them is corrupt). So I measured the gap's structure directly.

**(i) It is not a profiler artifact.** Paired ABBA on one binary, hook on (A)
versus hook off (B), order a1 b1 b2 a2, 0 token divergences in every arm
(`research/nezuko-pr158-gap.log`):

| arm | a1 (A) | b1 (B) | b2 (B) | a2 (A) | A mean | B mean | hook cost |
|---|---|---|---|---|---|---|---|
| wall median (ms) | 8.265 | 8.181 | 8.283 | 8.217 | 8.241 | 8.232 | **+0.11 %** |

+0.11 % is inside run-to-run spread. The earlier working hypothesis that the
gap was an `fputs` artifact of the hook itself is **refuted**.

**(ii) It is not per-command-buffer.** Two independent sweeps move the
buffers-per-step count by 2.5× and 4.5× at fixed dispatch count:

| sweep | knob | CBs/step | gap (ms) |
|---|---|---|---|
| `MLX_MAX_MB_PER_BUFFER` | 200 / 100 / 50 / 25 / 12 | 34 / 52 / 85 / 86 / 86 | 0.255 / 0.253 / 0.253 / 0.292 / 0.284 |
| `GPU_PROFILE_SPLIT` | 8 / 0 / 0' / 4 / 2 | 53 / 45 / 45 / 103 / 204 | 0.230 / 0.265 / 0.263 / 0.269 / 0.287 |

Linear fit on the `SPLIT` arms: **0.212 µs/CB, intercept 0.2437 ms**. The
`mb` sweep independently gives 0.56 µs/CB, intercept 0.236 ms. Both agree that
at most ~10–25 % of the observed gap is per-buffer; the rest is buffer-count
invariant. The 1.33 µs/CB figure used in the assignment (45 × 1.33 = 60 µs) is
**5–6× too high**; the true per-buffer cost is 0.2–0.6 µs.

**(iii) The floor is IPC and it is small.** The worker IPC round trip measured
with a model-free unknown-request-kind probe (`LagunaRuntimeWorker.swift:474`
returns `ok:false` without touching the model) is **~16 µs median**, 0.19 % of
wall. The 38 µs readings seen in some arms belong only to arms whose worker
took ~38 s to load (cold page cache / DVFS ramp); the arm that loaded in 5.5 s
read 16.5 µs. `min(before, after)` is used.

So:

```
gap  ≈  16 µs IPC  +  ~0.2–0.6 µs × CBs  +  ~224 µs residual
     ≈  16 µs      +  ~10–25 µs          +  ~224 µs
```

Probes (i)–(iii) settle what the gap is *not*: not an artifact, not
per-command-buffer at any material size, and not IPC. They leave a **~224 µs
residual**, and at that point I wrote down the wrong conclusion — I read "no
per-CB term and no per-dispatch term" as "therefore a fixed per-step host
cost", i.e. absolute. That inference does not follow. Both sweeps held
`gpu_busy` inside a 6.8 % window, so a genuinely proportional residual would
have moved only ~17 µs across them, which is under the ±19.5 µs replicate
noise. **The absolute reading was an artifact of insufficient dynamic range on
the one variable that distinguishes the two models.** §1.1.e widens that range
and reverses the verdict.

One caveat survives either way: this is a *host*-side measurement and the M5
has a different CPU. Only the qualitative structure is portable; the 224 µs
magnitude is not.

### 1.1.c How `gpu_busy_union` is computed — and what `sum == union` proves

Posting this for the §4.1 record and for @maple-tanjiro's #157 so he does not
duplicate the read.

`gpu_busy_union` is computed **per command buffer, not per dispatch.** The
`DARKBLOOM_GPU_PROFILE` hook in
`Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/device.cpp` records one
`(gpuStart, gpuEnd)` span from the **`MTLCommandBuffer` completion handler**,
i.e. one span per committed buffer, and emits `GPUPROF <gpuStart> <gpuEnd>
<dispatches> <kernels>`. `sum` adds the span lengths; `union` merges overlapping
spans. There is no per-dispatch timestamp anywhere in the path.

Therefore at the shipped batching policy — 406 dispatches in 45 buffers, ~9
dispatches per span — `sum == union` says only that **45 command buffers on one
serial queue do not overlap each other**, which is true by construction of a
serial `MTLCommandQueue`. It is blind to everything inside a buffer. **The
"exactly zero overlap to 6 ns" claim was never a measurement of concurrency.**

### 1.1.d Ruling on §4.1 readings (a), (b), (c) — decode axis

**(a) "`union` is blind to intra-buffer overlap ⇒ zero concurrency is an
artifact ⇒ shadowing is real."** — **Half right, and the half that matters is
wrong.** Its premise is confirmed: the instrument *is* per-buffer and *is*
blind (§1.1.c). Its conclusion is refuted by direct measurement. I re-measured
with an instrument that can see intra-buffer overlap, by capping dispatches per
buffer at `k` so that every dispatch boundary becomes a hard serialization
point:

| `SPLIT=k` | CBs/step | dispatches | wall (ms) | `gpu_busy_sum` (ms) | gap (ms) |
|---|---|---|---|---|---|
| 0 (shipped, ~9/CB) | 45 | 406 | 8.277 | 8.013 | 0.265 |
| 0′ (replicate) | 45 | 406 | 8.304 | 8.041 | 0.263 |
| 8 | 53 | 406 | 8.164 | 7.934 | 0.230 |
| 4 | 103 | 406 | 8.206 | 7.937 | 0.269 |
| 2 | 204 | 406 | 8.345 | 8.058 | 0.287 |
| 1 (zero overlap possible) | 406 | 406 | 9.860 | 8.583 | 1.278 |

0 token divergences in every arm.

If real intra-buffer concurrency existed at `k=0`, then destroying it would
*lengthen* GPU busy time. Over `k ∈ {8, 4, 2, 0, 0′}` `gpu_busy_sum` is **flat
at 7.99 ± 0.06 ms** — a 1.6 % spread against 0.35 % replicate noise — and it is
**non-monotone** in buffer count. Going from ~9 dispatches per buffer to 2
removes 78 % of the possible overlap opportunity and costs **+0.56 %**. The
honest bound on hidden concurrent work in shipped decode is **≤ ~0.06 ms, under
1 % of the step.**

`k=1` costs +6.9 % but is excluded from that trend and is not evidence for
concurrency: at 406 buffers per step the host becomes the critical path (gap
1.278 ms, 5× everything else) and fixed per-buffer GPU cost is completely
unamortized. It is retained only as the per-dispatch attribution arm for §2.

**(b) "Shadowing is not real; the #48 dispatches were genuinely ~0.12 µs of GPU
work; 1.980 µs prices the added barrier."** — **Correct in substance, and now
measured rather than inferred.** Decode is execution-serial. Note the
conclusion is right for a different reason than the argument that produced it:
`sum == union` never showed this, and (b) was being defended with (a)'s vacuous
evidence. It now stands on the `SPLIT` sweep.

**(c) "M4 and M5 differ structurally."** — **Not needed to resolve the
contradiction, and not excluded either.** Decode MSL is hand-written and both
hosts execute it identically, so the serial-execution finding transfers. The
*host gap* is a CPU-side cost and its magnitude does not. Keep (c) alive for
the µs magnitude of the gap, retire it as an explanation of the overlap
question.

**Consequence for the corollary at `CURRENT_RESEARCH_STATE.md:197-199.`** The
programme's standing worry was that isolated-duration claims are inflated
because the kernel is partly hidden behind others. On the decode axis that
worry is **unfounded**: nothing is hidden. Isolated duration ≈ exposed serial
time. But the claims are still over-attributed, by a completely different
mechanism — see §2.

### 1.1.e The evidence that settles absolute vs proportional

Three levers, 19 profiled configurations, one fit. Everything below is the same
binary on the same host under the same 40 °C gate.

**Lever 1 — fusion ablation** (`research/nezuko-pr158-unfuse-sweep.log`). Each
`DARKBLOOM_FUSED_*` knob off in turn. 0 token divergences in every arm.

| arm | knob off | CBs | dispatches | wall (ms) | busy (ms) | gap (ms) |
|---|---|---|---|---|---|---|
| base | — | 45 | 406 | 8.274 | 8.001 | 0.273 |
| rrr | `FUSED_RESIDUAL_RMS_ROUTER` | 45 | 445 | 8.536 | 8.262 | 0.275 |
| rsdr | `FUSED_ROUTED_SHARED_DOWN_RESIDUAL` | 46 | 445 | 8.296 | 8.074 | 0.222 |
| ssq | `FUSED_SHARED_SWIGLU_QMV` | 46 | 601 | 8.639 | 8.374 | 0.265 |
| rsq | `FUSED_ROUTED_SWIGLU_QMV` | 45 | 601 | 8.755 | 8.474 | 0.281 |
| base2 | — (replicate) | 45 | 406 | 8.277 | 8.004 | 0.273 |

This moves dispatches 1.5× but busy only 5.9 %, so it cannot separate the
models on its own. It is what produced the misleading "flat gap" reading.

**Lever 2 — 2×2 busy-range sweep** (`research/nezuko-pr158-busy-range-sweep.log`,
harness `research/nezuko_pr158_busy_range_sweep.sh`). ABBA order
`a1 b1 c1 d1 d2 c2 b2 a2`, replicates averaged. Factor 1 is seed length
(512 → 32 via `--seed`, a free-running timing-only arm); factor 2 is all four
fusion knobs off at once. Seeded arms verified 0 divergences.

| cell | seed | fusion | CBs | dispatches | busy (ms) | gap (µs) |
|---|---|---|---|---|---|---|
| a | 512 | on | 45 | 406 | 7.931 | 246.5 |
| b | 32 | on | 45 | 496 | 7.929 | 236.0 |
| c | 512 | off ×4 | 51 | 835 | 8.604 | 274.0 |
| d | 32 | off ×4 | 51 | 925 | 8.643 | 308.5 |

The seed lever behaved differently than designed, and better. At seed 512 the
sliding layers take the capacity-filled `sliding_fused_attn_ring_v1` path; at
seed 32 they take the grow path (`sliding_qk_norm_rope` + two copies +
`sdpa_vector`). The shorter KV saves exactly as much as the extra kernels cost,
so **`b` and `a` differ by +90 dispatches at Δbusy = −1.5 µs**: a clean
*dispatch-count-only* lever.

| contrast | Δbusy | Δdispatches | ΔCBs | Δgap |
|---|---|---|---|---|
| a → b (dispatch only) | −1.5 µs | +90 | 0 | **−10.5 µs** |
| c → d (dispatch only) | +38.5 µs | +90 | 0 | +34.5 µs |
| a → c (busy) | +673.5 µs | +429 | +6 | +27.5 µs |

Replicate half-ranges are ±19.5 / ±10.0 / ±17.0 / ±31.5 µs (mean ±19.5 µs), so
`a → b` is **−0.12 ± 0.22 µs per dispatch — a null**. Adding 90 dispatches
(+22 %) at unchanged total GPU busy time does not lengthen the step's host gap.

Two things this contrast is not. It is not a claim that dispatches are free on
the GPU: busy is unchanged in `a → b` because two large effects cancel — the
+90 dispatches carry the ~1.9 µs each GPU floor of §2.a (~171 µs) while the
shorter KV removes about as much attention work. The regression conditions on
total busy, which is the correct conditioning for the *host gap*, so the null
is about host cost per dispatch and does not contradict §2.a's GPU-side floor.
Nor is it evidence about command buffers: CBs are held at 45 in both cells.

**The fit** (`research/nezuko_pr158_gap_fit.py` →
`research/nezuko-pr158-gap-fit.txt`), all 19 rows, gap mean 264.9 µs, busy
range 7.917–8.645 ms (9.2 %), dispatches 406–925, CBs 45–204. `SPLIT=1` is
excluded as a different regime (host becomes the critical path).

| model | R² | rmse | coefficients |
|---|---|---|---|
| `1 + cbs` | 0.047 | 27.9 µs | cbs = +0.00016 ± 0.00018 |
| `1 + disp` | 0.269 | 24.4 µs | disp = +0.000075 ± 0.000030 |
| `1 + busy` | **0.362** | 22.8 µs | **busy = +0.0594 ± 0.0191** |
| `1 + cbs + disp` | 0.364 | 23.5 µs | cbs = +0.00023 ± 0.00015, disp = +0.000083 ± 0.000029 |
| `1 + cbs + busy` | **0.449** | 21.9 µs | cbs = +0.00022 ± 0.00014, busy = +0.0631 ± 0.0185 |
| `1 + cbs + disp + busy` | 0.452 | 22.5 µs | disp = **−0.000023 ± 0.000074**, busy = +0.0772 ± 0.0498 |

`gpu_busy` is the only regressor that survives. Once it is in the model the
dispatch coefficient collapses to zero and flips sign, matching the direct
`a → b` contrast; the univariate `1 + disp` fit is picking up busy through the
collinearity of the fusion lever.

**The test.** Absolute predicts d(gap)/d(busy) = 0. Proportional predicts
gap/busy = 0.0324.

| model | slope | absolute | proportional | 95 % CI |
|---|---|---|---|---|
| `1 + busy` | +0.0594 ± 0.0191 | 3.10σ — **excluded** | 1.41σ — inside | [+0.022, +0.097] |
| `1 + cbs + disp + busy` | +0.0772 ± 0.0498 | 1.55σ — inside | 0.90σ — inside | [−0.020, +0.175] |

**Verdict: proportional.** The best-conditioned model rejects the absolute
branch at 3.1σ and cannot reject proportional. The saturated model is
underdetermined — busy and dispatch count are collinear across the fusion
lever — but its point estimate also sits closer to proportional. Nothing in
these data supports a fixed per-step host cost. If anything the slope is
*super*-proportional (0.059 vs 0.032), which is what you would expect if part
of the residual is command-buffer completion handling whose cost rises with
buffer occupancy, but that excess is only 1.4σ and I am not claiming it.

**Three honest limits.** (1) The busy lever is confounded: fusion ablation
raises busy *and* dispatches together, and the one unconfounded lever (seed)
happened to move busy by 0.02 %, so it constrains dispatches, not busy. The
3.1σ rejection rests on the univariate fit. (2) 9.2 % of dynamic range against
±19.5 µs noise is thin; I would not defend a slope estimate to better than a
factor of two. (3) M4 host, M4 CPU. What transfers to M5 is the qualitative
claim (the gap is not a fixed additive pool), not 0.059.

**Why this matters less than it looks.** The whole dispute is bounded by
gap/wall = **3.01 %**. For a hypothetical 10 % reduction in `gpu_busy` the
absolute model predicts 10.74 % wall speedup and the proportional model 11.11 %
— a **0.33 %** difference. Either way the conclusion for the programme is the
same and it is the one that matters: **there is no host-side pool to attack
separately.** Every µs of decode wall time must be bought by removing GPU work,
and §2 says where.

---

## 1.2 Lane audit of `gate_sp` and `residual_rms_router`

Taken before §1.3 because its pre-registered kill rule decides whether §1.3
exists. **The rule fires for both kernels. §1.3 is not entered.**

All Laguna decode MSL is generated as runtime strings inside
`Sources/MLXFastModel/LagunaRuntimeModel.swift`. Model config: hidden 2048,
head_dim 128, 40 layers = 10 full-attention layers (48 heads) + 30
sliding-window layers (64 heads), 256 experts, top-8, `moe_intermediate` 512.

### 1.2.a Naming correction

The assignment calls `gate_sp` a shared-expert kernel. It is not. `gate_sp` is
the **per-head gate projection plus softplus** (`g_proj`) inside attention. The
shared expert is `laguna_shared_nvfp4_swiglu_qmv_rows1` (a separate 293 µs/step
kernel). Every downstream claim keyed on `gate_sp` — including my own
`D-FUSE-GATESP` in PR #143 — means "fuse the per-head gate GEMV into
`oproj_act`", not anything about the shared expert. This mislabel propagated
through at least two documents and is corrected here.

### 1.2.b `laguna_gate_sp_h{48,64}_v1`

| | |
|---|---|
| MSL generator | `LagunaRuntimeModel.swift:4275-4318` |
| pipeline registry | `:4320-4331` |
| dispatch | `:4347-4352` |
| call site | `:5802` |
| constants | `K=2048, GS=32, V=8, BK=256, R=4, NS=2` |
| grid / threadgroup | `((heads/8)*64)` / `64` |
| h64 | 8 threadgroups, 512 threads, 1 wave on 20 cores |
| h48 | 6 threadgroups, 384 threads, 1 wave on 20 cores |
| threadgroup memory | 0 B |
| bytes/thread | ~256 B (one 2048-element uint8 weight row per 8 lanes) |
| measured | 241.7 µs/step over 30 calls (h64) = **8.06 µs/call**; 77.3 µs/step over 10 calls (h48) = **7.73 µs/call** |

**Useful-lane fraction: 100 %.** Every one of the 64 lanes in a threadgroup
accumulates a partial dot product and feeds `simd_sum`; only the reduction's
`lane == 0` stores. There is no `if` on lane id in the accumulation loop and no
intra-warp divergence anywhere in the kernel. Softplus is already fused into the
same kernel.

**Threadgroups are not oversubscribed — they are severely *under*subscribed.**
h64 launches 8 threadgroups onto 20 GPU cores; 12 cores are idle for the whole
dispatch. h48 launches 6. This is the opposite of the #137 condition.

⇒ **Kill rule fires.** Useful-lane fraction > 50 % and threadgroups are not
oversubscribed, so the #137 ballot/ctz compaction pattern has nothing to
compact and nothing to reclaim. Stop.

Two observations recorded for the follow-up list, deliberately **not**
implemented here:

- Weight loads are **scalar**. The inner accumulation is `a += x[i] * wl[i]`
  with `wl` a `const device uint8_t*`, i.e. 8 blocks × 4 rows × 8 = **256
  single-byte loads per lane**. All offsets are multiples of 8, so the same
  bytes could be fetched as 32 aligned `uint2` loads — 8× fewer load
  instructions with the FMA order preserved, hence bit-exact. Whether that
  helps is genuinely uncertain: achieved bandwidth is only ~16 GB/s (131 KB in
  8 µs), so the kernel is latency/occupancy-bound rather than byte-bound, and
  fewer-but-wider loads mainly reduce instruction issue, not stalls.
- The real prize is **dispatch removal, not kernel speedup** (see §2). Naive
  fusion into `oproj_act` does not work: `oproj_act` runs 256 threadgroups ×
  64 threads (`:4448-4449`) and each threadgroup reads
  `gate_values[column >> head_shift]` (`:4102`), so recomputing the gate GEMV
  per threadgroup would issue ≈32 MB of redundant weight reads to save a 131 KB
  kernel. Any real fusion needs the gate values produced once and broadcast,
  which is a different kernel structure than "merge the two bodies".

### 1.2.c `laguna_residual_rms_router_bf16_2048_rpg8_keys_v1`

| | |
|---|---|
| MSL generator | `LagunaRuntimeModel.swift:853-984` (signature `:853-872`) |
| pipeline registry | `:991-1011` |
| Swift wrapper | `:1055-1095` |
| dispatch | `:1087-1093` |
| call sites | `:10359` (decode), `:10456` |
| grid / threadgroup | `tiles*512` / `512`, `tiles = 256 / rowsPerGroup = 32` |
| occupancy | 32 threadgroups × 512 = 16,384 threads, 2 waves on 20 cores |
| threadgroup memory | 4,228 B |
| barriers | 4 |
| dispatches/step | 39 (layer 0 uses `laguna_residual_rms_bf16_2048_v1`, `:1016`) |
| measured | 319.9 µs/step over 39 calls = **8.20 µs/call** |
| bytes | 1,048,576 B of router weights read once ⇒ ~217 GB/s achieved |

**Useful-lane fraction: exactly 50.0 %, with zero intra-warp divergence.**
`rowsPerThread = 1`, `activeSimdGroups = 8`, `simdGroups = 16`. The guard is
`if (simd_group < active_simd_groups)` where `active_simd_groups` is a
`constexpr uint`. That is a **whole-simdgroup, compile-time-constant** predicate:
simdgroups 0–7 do router MACs, simdgroups 8–15 exit. No warp ever contains both
active and inactive lanes.

This is precisely the case the kill rule was written to exclude. A ballot/ctz
compaction reclaims lanes *within* a divergent warp; here there are no divergent
warps, only whole warps that retire early. The scheduler already reclaims those
slots. ⇒ **Kill rule fires. Stop.**

Supporting negatives, so the next person does not re-derive them:

- Router weight loads are **already vectorized** as `vec<bfloat,4>`, unrolled
  4-deep (`:877-892`). 8.20 µs for 1 MB is ~2.9× the byte floor.
- `DARKBLOOM_ROUTER_ROWS_PER_GROUP` (`:604-640`) already exists and was already
  swept; null. The in-source note at `:826-852` explains why: `tiles *
  rows_per_group == 256` at every legal tiling, so retiling cannot increase
  outstanding loads (64 KB stays pinned), and the `**LOADS ONLY**` constraint at
  `:844-852` forbids splitting the accumulator.

One genuinely structural waste is visible and is *not* a lane-compaction
problem: the **norm prologue is recomputed 32×**. `base = lid * n_reads`
(`:934`) has all 512 threads of *every* tile cover the full 2048-element row,
but only `tile == 0` writes the normalized output. That is 393,216 B of reads
for 12,288 B of unique data and roughly 24 % of the kernel's lane-instructions.
Fixing it means splitting the fused kernel — which adds a dispatch, and §2
explains why that trade is probably negative. Recorded as a follow-up, not
attempted.

---

## 2. Ranked exposed serial time, and the corrected census

§1.2's kill rule fired for both kernels, so §1.3 is not entered and §2 fires.

### 2.a Method: exposed serial time, and a measured per-dispatch floor

Two constants are needed and both are measured here rather than assumed.

**The SPLIT=1 inflation, 1.419 µs/dispatch.** The `SPLIT=1` arm gives the only
per-kernel breakdown available (one command buffer per dispatch, so each
GPUPROF span is one kernel), but its `µs/call` column is inflated by the
per-buffer GPU cost the shipped ~9-dispatch batching amortises. That inflation
is `(8583 − 8007) / 406 = 1.419 µs`, from the `SPLIT=1` busy sum against the
`SPLIT=0` busy sum at identical dispatch count. Earlier census work used 1.33;
the 6 % correction only matters for the smallest kernels. Note the corrected
total returning to 8007 µs is arithmetic, not evidence — it only confirms the
per-kernel `n/step` column sums to 406.

**The per-dispatch floor, ~1.9 µs.** This is the cost of *having* a dispatch,
independent of what it computes. Two independent routes agree:

- *Marginal.* The unfuse sweep ablates one fused kernel at a time into a longer
  chain computing the same result. `rsdr` adds 39 dispatches for +73 µs, `ssq`
  adds 195 for +373 µs, `rsq` adds 195 for +473 µs — **1.9, 1.9 and 2.4 µs per
  added dispatch.** (`rrr` is +6.7 µs and is excluded: it also materialises a
  2048-wide bf16 intermediate, so it prices traffic, not floor.)
- *Absolute.* The cheapest dispatches actually present in the step, corrected,
  cost `residual_rms` 1.56, `rmsbfloat16` 2.06, `gather_front` 2.16,
  `decode_embedding_rope` 2.13, `lmhead_coarse_argmax_stage1` 2.51 µs.

A marginal cost derived from ablation and an absolute cost read off unrelated
tiny kernels are different quantities, and they land on the same 1.6–2.5 µs.
I use **1.9 µs**.

**Why "exposed" is now the right word.** §1.1.d measured that decode has no
usable intra-buffer concurrency (hidden work ≤ 0.06 ms/step, under 1 % of the
step). Isolated duration therefore *is* exposed serial time. This is the
assignment's expected correction inverted: the 10 HIGH-RISK rows are not
over-attributed by overlap, because there is no overlap.

### 2.b The ranking

`research/nezuko_pr158_exposed_time.py` →
`research/nezuko-pr158-exposed-time.txt`. `floor = 1.9 µs × n`; `work =
exposed − floor`.

| exposed µs/step | share | n | µs/call | floor | work | kernel |
|---|---|---|---|---|---|---|
| 1445.4 | 18.05 % | 39 | 37.06 | 74.1 | 1371.3 | `routed_nvfp4_swiglu_qmv_packed_top8keys_r1_bf16_v2` |
| 1291.5 | 16.13 % | 30 | 43.05 | 57.0 | 1234.5 | `decode_nvfp4_qkv_h64` |
| 1074.0 | 13.41 % | 30 | 35.80 | 57.0 | 1017.0 | `oproj_act_h64` |
| 812.8 | 10.15 % | 39 | 20.84 | 74.1 | 738.7 | `routed_shared_nvfp4_down_residual_bf16_r1_v5` |
| 592.2 | 7.40 % | 30 | 19.74 | 57.0 | 535.2 | `sliding_fused_attn_ring_v1` |
| 420.4 | 5.25 % | 1 | 420.44 | 1.9 | 418.5 | `lmhead_int5_base_coarse_delta` |
| 349.8 | 4.37 % | 10 | 34.98 | 19.0 | 330.8 | `decode_nvfp4_qkv_h48` |
| 288.9 | 3.61 % | 10 | 28.89 | 19.0 | 269.9 | `oproj_act_h48` |
| 268.6 | 3.35 % | 1 | 268.59 | 1.9 | 266.7 | `dense_gate_up_swiglu` |
| 264.5 | 3.30 % | 39 | 6.78 | 74.1 | 190.4 | `residual_rms_router_rpg8_keys_v1` |
| 239.9 | 3.00 % | 10 | 23.99 | 19.0 | 220.9 | `full_fused_attn_grow_v1` |
| 237.6 | 2.97 % | 39 | 6.09 | 74.1 | 163.5 | `shared_nvfp4_swiglu_qmv_rows1` |
| 199.2 | 2.49 % | 30 | 6.64 | 57.0 | 142.2 | `gate_sp_h64` |
| 146.7 | 1.83 % | 39 | 3.76 | 74.1 | 72.6 | `decode_router_top8_ordinal_table_norm` |
| 133.6 | 1.67 % | 1 | 133.59 | 1.9 | 131.7 | `dense_down_residual` |
| 84.5 | 1.06 % | 41 | 2.06 | 77.9 | 6.6 | `rmsbfloat16` |
| 74.3 | 0.93 % | 1 | 74.31 | 1.9 | 72.4 | `lmhead_exact_fused_int5_sparse_refine` |
| 63.1 | 0.79 % | 10 | 6.31 | 19.0 | 44.1 | `gate_sp_h48` |
| 19.5 | 0.24 % | 6 | — | 11.4 | 8.1 | six kernels below 8 µs/step |

**Totals: 8006.6 µs/step, of which 771.4 µs (9.6 %) is per-dispatch floor and
7235.2 µs is work.**

Three programme-level readings follow.

1. **9.6 % of decode GPU time is the cost of having 406 dispatches, not the
   cost of computing anything.** It is recoverable only by *removing
   dispatches*. Making a kernel faster never touches it.
2. **Conversely, dispatch-removal is worth exactly 1.9 µs each and no more.**
   Any claim that fusing two kernels saves more than 1.9 µs per removed
   dispatch is claiming to remove *work* or *traffic*, and must be priced that
   way.
3. **The top four kernels are 4623.7 µs/step = 58 % of GPU busy over 138
   dispatches**, i.e. 262 µs of floor against 4362 µs of work. They are
   byte-bound projections. No dispatch-level trick reaches them; only fewer
   bytes or better achieved bandwidth does.

### 2.c Corrected census of the 10 HIGH-RISK rows

Line numbers are `research/CURRENT_RESEARCH_STATE.md` via
`research/maple-nezuko-pr143-expert-slab-dedup.md:502-529`.

**Global correction first.** All ten were flagged HIGH RISK because isolated
duration might be partly hidden behind a neighbour. **That objection is
withdrawn for the decode axis** (§1.1.d). Items 2–9 do *not* inherit an overlap
defect. They inherit a different one: they price a saving without separating
the ~1.9 µs floor from the work term.

| # | row | old verdict | new verdict |
|---|---|---|---|
| 1 | `:5789-5805` root generator | HIGH RISK | **CONFIRMED, constant corrected** |
| 2 | `:6508`/`:6782` D-FUSE-GATESP | 213 µs ⇒ score +2.28 % | **claim struck; mechanism is net-negative; a *different*, larger prize exists** |
| 3 | `:6648` router rpg | 106 µs/step | **struck; mechanism dead** |
| 4 | `:6649` shared-expert K1 | 65 µs/step | **survives, ceiling ~44 µs without dispatch removal** |
| 5 | `:6574` latency-only 76.6 µs | maximally shadowable | **objection struck; row survives** |
| 6 | `:4994` 2.2 µs/layer × 30 | HIGH RISK | **objection struck; row survives** |
| 7 | `:5056-5057` K3 843.6 / K1 −13.3 | HIGH RISK | **K3 confirmed to 4 %; K1 struck as sub-noise** |
| 8 | `:3139`/`:3486`→`:6663` 40–80 µs | struck to residue | **residue survives; price at 1.9 µs/dispatch** |
| 9 | `:537` SHARED-after-ROUTED +70 µs | no overlap explanation | **overlap excluded as the explanation; needs ABBA re-measure** |
| 10 | `:6776` D-STRAND 0.59 ms pool | already VOID | **VOID confirmed by direct measurement** |

Detail on the ones where the verdict changes the queue:

**2. D-FUSE-GATESP — the largest queued exposure, and it does not hold.**
Measured exposed serial time is `gate_sp_h64` 199.2 + `gate_sp_h48` 63.1 =
**262.3 µs/step**, *higher* than the quoted 213. But the proposed mechanism
recovers only the floor: fusing `gate_sp` into `oproj_act` removes 40
dispatches = **76 µs**, not 150. The other 186 µs is work, and fusion does not
delete it — the per-head gate weights still have to be read. §1.2.b then shows
the fusion is actively negative: `oproj_act` launches 256 threadgroups
(`LagunaRuntimeModel.swift:4448-4449`), each of which would need the gate
column block, so a naive fusion issues ≈32 MB of redundant reads per layer to
avoid a 131 KB kernel. **Strike "decode +2.95 % ⇒ score +2.28 %".**

The prize that *is* there is a different one, and the lane audit found it.
`gate_sp` is 100 % useful-lane with no divergence, but it launches 512 threads
(h64) / 384 (h48) on a 20-core GPU and moves 131 KB in 6.64 µs ≈ 20 GB/s, a few
percent of achievable bandwidth. It is **occupancy-bound, not work-bound**.
Splitting `K = 2048` across more threadgroups with a two-stage reduce attacks
the 186 µs work term rather than the 76 µs floor term. Unreachable ceiling if
driven all the way to the floor: **186 µs/step = 2.3 % of GPU busy** — larger
than the fusion prize ever was, and with a mechanism the audit supports.

**3. Router rpg — dead, with a source-level reason.** Exposed 264.5 µs/step;
floor 74.1, work 190.4. The rpg sweep already returned null and §1.2.c explains
why it had to: `tiles × rows_per_group == 256` at every legal tiling
(`:826-852`), so retiling cannot raise outstanding loads, and `**LOADS ONLY**`
(`:844-852`) forbids splitting the accumulator. The remaining structural waste
is the 32× redundant norm prologue (393,216 B read for 12,288 B unique, ~24 %
of lane-instructions); removing it costs one added dispatch, so the ceiling is
roughly 0.24 × 190.4 − 1.9 ≈ **44 µs/step**, not 106.

**7. K1 = −0.34 µs/call is not a measurable quantity.** It is below the 1.9 µs
floor, below the p10–p90 spread of its own kernel, and negative. Strike it as
noise rather than treating it as a small real cost.

**9. `:537` needs a new explanation, not a new measurement of the same thing.**
±70 µs/step is 0.9 % of busy, comfortably above the 0.35 % replicate noise, so
the magnitude is plausibly real. But both orderings issue the same dispatches
with the same bytes, and overlap is now excluded, so the only mechanisms left
are memory locality (L2 residency of the shared-expert weights across the
routed gather) and drift. It should be re-measured ABBA before anyone banks it.

**10. D-STRAND is void by direct measurement, not by inference.** The
small-kernel pool in the table above (everything at ≤ 8 µs/call) is ~1013
µs/step across 203 dispatches, so a 0.59 ms/step "hideable" pool is
numerically in range. It is nonetheless unreachable: §1.1.d bounds *all*
hidden concurrent work at ≤ 0.06 ms/step, and 386 µs of that pool is
per-dispatch floor that hiding could not remove even if concurrency existed.

**LOW-RISK byte-priced rows** (`:296`, `:483`, `:1865`, `:4903`, `:4957`,
`:6557`, `:1710`, `:2075`) are unaffected by the overlap question and remain
the trustworthy class. One adjustment in their favour: a byte-priced estimate
*under*-counts by 1.9 µs for every dispatch the change also removes.

### 2.d Follow-ups I did not implement

1. **`gate_sp` occupancy** (§2.c item 2). Largest measured, mechanism-supported
   decode opportunity in this report: ceiling ~186 µs/step. Two-stage reduce
   over `K = 2048`; bit-exactness needs care because the reduction order
   changes, so it must be validated by logit digest, not assumed.
2. **`gate_sp` scalar loads.** 256 single-byte `uint8` loads per lane could
   become 32 aligned `uint2` loads, bit-exact and independent of (1). Note the
   kernel is latency-bound, so this may do nothing on its own; it is cheap to
   test alongside (1).
3. **Router norm prologue** (§2.c item 3). ~44 µs/step ceiling, costs a
   dispatch.
4. **ABBA re-measure of `:537`.**
5. **A cleaner busy lever for §1.1.e.** The 3.1σ rejection of the absolute
   model rests on a lever (fusion ablation) that moves `gpu_busy` and dispatch
   count together. An unconfounded lever would hold the kernel graph fixed and
   change only how long each kernel runs — for example an `MLX_METAL_*` clock
   or a deliberately slowed variant of one large kernel. That would tighten the
   slope, but the result would not change any decision: the whole question is
   worth ≤3.0 % of wall, and both branches say the same thing about where to
   spend effort.

