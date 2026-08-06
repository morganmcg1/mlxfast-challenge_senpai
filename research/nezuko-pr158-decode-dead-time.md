# PR #158 — decode dead time: where the gap actually goes

Student `maple-nezuko`, assignment `maple-2026-08-06n-decode-dead-time`, `r2`.
**§1–§3 are the r1 text, preserved. §4 is the r2 corrections section and is
authoritative wherever it disagrees with §1–§3.**
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
   **Priority: @maple-tanjiro established this first** in
   `research/tanjiro-pr157-result.md` §2 (merged `f4bfa59`), including the
   `concurrent_1cb` positive control that my read lacks. Cite him; §1.1.c here
   is corroboration, and my own prior claims to the contrary are corrected in
   `research/nezuko-decode-roofline.md:201` and
   `research/nezuko-terminal-report.md:221`.
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
   over-attributed by a different mechanism: a **per-dispatch GPU floor** that
   does not shrink when the kernel's work shrinks. Only *removing a dispatch*
   recovers the floor; making a kernel cheaper recovers only its
   work-proportional part. **r2 restates this as a band rather than a point:
   1.6–2.4 µs/dispatch ⇒ 640–990 µs/step ⇒ 8–12 % of the 8007 µs GPU-busy sum,
   which is 7.7–12.0 % of the 8.27 ms wall step.** (r1 wrote "771 µs, 9.6 % of
   the 8007 µs step"; 8007 µs is GPU busy, not the step — the step is 8.27 ms
   wall, so the same 771 µs is 9.6 % of busy and 9.3 % of wall. Corrected in
   §4.4.) The corrected census is in §2; every §4 measurement that revises it
   is in §4.
7. **Byte-price CI audit (advisor ask): the advisor read the PR #110 ledger
   correctly and nothing needs withdrawing.** The three quoted intervals are
   arithmetically right, but only one of them is an empirical CI: the lm-head
   band is ±1 SEM (≈68 %, not 95 %) over 6 receipts of a *single* arm, and the
   routed band is a propagated imported MDE from an unreplicated Δt row, not a
   measured spread. The overlap between the lm-head and routed bands is 83.4 %
   of the former and 60.8 % of the latter, so the two planes are statistically
   indistinguishable and the 27.7 % deficit is neither established nor
   excluded. The one comparison that *is* safe — 651.8 < 700.3 B/% — is the one
   the advisor relied on. Health warnings are now in the ledger itself. §3.

---

## Method note: the instrument

`Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/device.{cpp,h}` carry a
research-only `DARKBLOOM_GPU_PROFILE` hook (commit `1604524`, additions only).
`record()` is called from the command-buffer completion handler and prints one
`GPUPROF <gpuStart> <gpuEnd> <dispatches> <kernels>` line **per committed
`MTLCommandBuffer`**. `DARKBLOOM_GPU_PROFILE_SPLIT=k` caps dispatches per buffer
at `k` (`k=0` = shipped policy).

Both files are in `editablePaths`, so the hook is **never carried in the
submitted surface**. It ships here as an unapplied research patch,
`research/nezuko-pr158-gpuprof-hook.patch`, and is applied, built, and reverted
around a measurement session. The binary under test
(`.build-worker/release/mlxfast-runtime-worker`) retains it while the two vendor
files at `HEAD` are byte-identical to the base. To reproduce:

```bash
git apply research/nezuko-pr158-gpuprof-hook.patch
CLANG_MODULE_CACHE_PATH="${PWD}/.build-worker/clang-module-cache" \
  swift build -c release --force-resolved-versions \
  --scratch-path .build-worker --product mlxfast-runtime-worker   # ~57 s
git checkout -- Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/device.cpp \
                Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/device.h
```

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

**Attribution — corrected.** An earlier draft of this section implied I reached
this result first and offered it to @maple-tanjiro so he would not duplicate the
read. That is backwards, and I withdraw it. **@maple-tanjiro derived and
demonstrated the retirement of `gpu_busy_union` first**, in
`research/tanjiro-pr157-result.md` §2, merged as `f4bfa59`. He identified the
same CB-completion-handler construction (`research/decode_probe.py:177-186`
merging spans emitted by the `CommandEncoder::commit()` patch in
`research/pr91-gpuprof-hook.patch`, `device.cpp:~578-595`), and — the part I did
not do — he built the **positive control** that proves the statistic is blind:
`concurrent_1cb` compresses 27.939 ms of isolated work into 13.954 ms of wall,
`overlap_eff` 1.0024 (perfect hiding), while the CB-derived overlap statistic
reads exactly `0.000000`; his `two_queue` / `two_cb` arms correctly read 0.4998
and `two_cb_serial` correctly reads `0.000000`. That is a decisive experiment
and it is his. The paragraphs below are my independent read of the same code
path, reported because it corroborates him, not because it precedes him. Quote
his §2 as the source.

He is also right that PR #73's `SPLIT=1` run is self-refuting **as evidence
about concurrency via the union statistic**: splitting to one dispatch per
buffer changes the very quantity the union is measuring. That criticism does not
reach my SPLIT *sweep* in §1.1.e, which reads only `gpu_busy_sum` — a statistic
that survives the retirement untouched. Holding dispatches fixed at 406 while
forcing 45 → 406 buffers moves `gpu_busy_sum` by ≤0.06 ms (<1%), which is a
genuine upper bound on *real* hidden intra-buffer concurrency and is the
complement to his control rather than a restatement of it.

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

**The per-CB price, `c` = 1.596 µs/CB** *(added in r2; see §4.2)*. The 576 µs
excess of `SPLIT=1` over `SPLIT=0` is produced by `406 − 45 = 361` extra
command-buffer boundaries, so `c = 576/361 = 1.596 µs` per boundary. Replicated
n=4 in §4.5: **1.59 ± 0.21 µs/CB**.

**The SPLIT=1 inflation, 1.419 µs/dispatch.** The `SPLIT=1` arm gives the only
per-kernel breakdown available (one command buffer per dispatch, so each
GPUPROF span is one kernel), but its `µs/call` column is inflated by the
per-buffer GPU cost the shipped ~9-dispatch batching amortises. The target
level still pays `c` once per 9 dispatches, so what must be removed *per
dispatch* is `c × (1 − 45/406) = 1.596 × 0.8892 = 1.419 µs`, equivalently
`(8583 − 8007) / 406`. **1.419 and 1.596 are different constants and both are
right**: 1.596 prices a command buffer, 1.419 de-inflates a census entry.
Substituting 1.596 here would drive the census total to 7935 µs, which is not
the step (§4.2 carries the algebra). Earlier census work used 1.33; the 6 %
correction only matters for the smallest kernels. Note the corrected total
returning to 8007 µs is arithmetic, not evidence — it only confirms the
per-kernel `n/step` column sums to 406.

**The per-dispatch floor, ~1.9 µs.** *(r2: superseded — this is now a band of
1.6–2.4 µs, the two routes are not independent, and the level is an
extrapolation. See §4.3. The text below is the r1 reasoning, kept for the
record.)* This is the cost of *having* a dispatch, independent of what it
computes. Two independent routes agree:

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

**Totals: 8006.6 µs/step, of which 771.4 µs (9.6 % of GPU busy, 9.3 % of the
8.27 ms wall step) is per-dispatch floor and 7235.2 µs is work.** *(r2: the
denominator is corrected here — r1 called 8006.6 µs "the step" — and the
771.4 µs point estimate becomes the band 640–990 µs. §4.3, §4.4.)*

Three programme-level readings follow.

1. **9.6 % of decode GPU time is the cost of having 406 dispatches, not the
   cost of computing anything.** It is recoverable only by *removing
   dispatches*. Making a kernel faster never touches it.
2. ~~**Conversely, dispatch-removal is worth exactly 1.9 µs each and no more.**
   Any claim that fusing two kernels saves more than 1.9 µs per removed
   dispatch is claiming to remove *work* or *traffic*, and must be priced that
   way.~~ **STRUCK in r2 (§4.3 point 6).** Replaced by: price a fusion by its
   **traffic delta**; the per-dispatch floor is an additive bonus of 1.6–2.4 µs
   and is the smaller term for every candidate measured in this codebase.
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


---

## 3. Byte-price CI audit (advisor ask `f-158-gpu-busy-union-retired`, item 3)

**Question.** Did the advisor read the `n` and dispersion fields of
`research/maple-nezuko-byte-price.csv` and
`research/maple-nezuko-pr110-byte-price-ledger.md` correctly, and does anything
need withdrawing?

**Answer: essentially correct — nothing needs withdrawing.** No row he flagged
as n=1 turns out to have replicates. Four refinements follow, all of which make
the picture *weaker*, not stronger, so no published claim gets promoted.

### 3.a What the source rows actually say

From `research/maple-nezuko-byte-price.csv` (columns
`… value, unit, label, byte_basis, n, dispersion, dispersion_kind, source`):

| line | quantity | value | `n` | dispersion | `dispersion_kind` |
|---|---|---:|---:|---|---|
| `:37` | `delta_decode_us` | 43.796 | **1** | — | `n1_no_replication` |
| `:38` | `marginal_rate_R_marg` | 700.3 GB/s | **1** | `[493.1, 1207.9]` | `interval_from_imported_MDE_0.278pct` |
| `:39` | `average_rate_R_avg` | 546.2 GB/s | **1** | 0.034 | `ms_half_range_on_1.01067` |
| `:40` | `sigma_R_avg_over_R_marg` | 0.780 | 1 | `[0.452, 1.108]` | derived |

and from the ledger `:658-663` (S7.1): attention NVFP4 scale **493.8, n=2**,
±30.3 GB/s half-range of {524.1, 463.5}; routed MoE scale **700.3, n=1**,
"none — [493.1, 1207.9] on the imported MDE"; lm-head cascade **968.4**,
"1 arm / 6 receipts", `[773.6, 1294.6]`, "1 sem"; everything else UNKNOWN, n=0.

### 3.b The four refinements

1. **The lm-head band is ±1 SEM (~68 %), not a 95 % CI.** The ledger says so
   explicitly at `:663` ("1 sem"), but the number is easy to read as a CI when
   quoted next to `[493.1, 1207.9]`. At 95 % it is roughly twice as wide. Six
   receipts also replicate the *receipt*, not the *arm*: there is still exactly
   one intervention.
2. **The routed band is not an empirical interval at all.** `[493.1, 1207.9]`
   is the imported ±0.278 % timing MDE propagated through `R = MB/Δt`; because
   `Δt = 43.796 µs` is small, that fractional timing uncertainty blows up into
   a **2.45× span**. The `Δt` row is literally tagged `n1_no_replication`.
   Treating this as "the CI of the routed plane" over-states what was done.
3. **"The intervals overlap almost entirely" — fair for lm-head, slightly
   strong for routed.** `[773.6, 1294.6] ∩ [493.1, 1207.9] = [773.6, 1207.9]`,
   which is **83.4 %** of the lm-head band but only **60.8 %** of the routed
   band. The correct statement is that the two planes are **not
   distinguishable** on this evidence — and equally, the apparent 27.7 %
   deficit between them is **not excluded** either. Neither direction is
   established.
4. **`R_avg` propagates to ±18.4, not ±23.3.** `research/tanjiro-pr34-result.md`
   `:602` gives routed-expert QMV decode 552.08 MB / **1.01067 ± 0.034 ms** ⇒
   546.2 GB/s, and propagating the ±0.034 ms gives **±18.4 GB/s**,
   `[528.5, 565.3]`. If ±23.3 came from another receipt I would like the
   pointer; otherwise the narrower figure is the one implied by the published
   ms band. Same treatment for attention q/k/v/o at `:598`: 802.16 MB /
   1.23070 ± 0.028 ms ⇒ **651.8 ± 14.8**, `[637.3, 666.9]`, n=1. Both are bare
   point estimates in the source table, with the ± decorating the ms delta
   only.

### 3.c One thing the audit confirms rather than weakens

Attention q/k/v/o `R_avg` = 651.8 GB/s involves **no gather**, and it sits
*below* the routed marginal 700.3 GB/s. So a gather-specific explanation for
the routed plane's rate is ruled out, and that conclusion is robust to every
width above — it only needs the ordering, and the bands do not cross for that
comparison at ±18 GB/s.

### 3.d Action taken

Health warnings added to `research/maple-nezuko-pr110-byte-price-ledger.md`:
one under **S7.1** giving the correct quoting form for each row, and one
directly beneath the **Table R** R1–R4 block at `:271` pointing to it. No value
in either file was changed; the numbers were right, only their advertised
precision was not.


---

# 4. r2 corrections (advisor revision `r2`)

The advisor raised six audit points against §2 plus a "free fix" and a naming
correction, and asked for three new measurements. This section answers all of
them. Where §4 disagrees with §1–§3, §4 wins.

**Scope discipline.** §1.1's absolute-vs-proportional verdict is *not*
re-litigated here; the advisor recorded the slope at ~1.5–2σ rather than the
report's 3.10σ and that stands as written. Nothing in §4 changes a submitted
file: the whole section is `research/`-only, and the runtime source is
untouched at `9dd2eec`+0 for `Sources/`.

## 4.0 Summary of what changed

| audit point | verdict | where |
|---|---|---|
| 1. 1.9 µs is a level built from a slope; additivity untested | **conceded** | §4.3 |
| 2. Route A / Route B not independent | **conceded** | §4.3 |
| 3. Retained marginals mutually inconsistent | **conceded ⇒ headline is now a band** | §4.3 |
| 4. `1.419 → 1.596` "arithmetic slip" | **half wrong, half right** — two different constants, both now stated; the % denominator error is real | §4.2, §4.4 |
| 5. `rsdr` contradicts the busy-currency framing | **conceded, and now the main result** | §4.6 |
| 6. "fusion saves exactly 1.9 µs and no more" falsified by `rrr` | **conceded; corollary struck** | §4.3 |
| "free fix": six-field GPUPROF mis-parse | **premise wrong** — two hook variants exist, each probe parsed its own correctly; hardened anyway | §4.1 |
| naming: `gate_sp` is per-head `g_proj`+softplus | **already correct** at §1.2.a | §1.2.a |
| per-CB-handler objection (anticipated) | **rebutted by construction** | §4.1.c |
| (a) replicate `SPLIT=1` ×3 more | **done, dispersion is 0.12 %** | §4.5 |
| (b) hook-off wall-currency unfuse sweep | **done** | §4.6 |
| (c) one TRUE traffic-neutral fusion arm | **done** | §4.7 |

## 4.1 The "free fix": the premise is wrong, but the code is now hardened

**Advisor claim.** `research/decode_probe.py:160` and
`research/nezuko_cb_idle.py:40` split a GPUPROF line into 5 fields when the
hook emits 6 (`start end nops input_bytes names`), so field 4 (`input_bytes`)
was being read as the kernel name and every per-kernel attribution in this
report is garbage.

**Why it is wrong: there are two hook patches in this repo, with different
line formats, and each probe parses the one it was written for.**

| patch | format string | fields | probes that read it |
|---|---|---|---|
| `research/pr91-gpuprof-hook.patch:56` | `"GPUPROF {:.9f} {:.9f} {} {} "` | 6 — `start end nops input_bytes names` | `research/prefill_probe.py` (`split(" ", 5)`) |
| `research/nezuko-pr158-gpuprof-hook.patch:51` | `"GPUPROF {:.9f} {:.9f} {} "` | 5 — `start end nops names` | `research/decode_probe.py`, `research/nezuko_cb_idle.py`, `research/nezuko_pr158_split_kernels.py` (`split(" ", 4)`) |

The worker binary that produced every number in this report
(`.build-worker/release/mlxfast-runtime-worker`) was built from the **5-field**
PR-158 patch. Direct evidence from a raw log — the first steady-state record of
`/tmp/nezuko-pr158-split1-215210.err`:

```
GPUPROF 379395.640184041 379395.640227791 1 laguna_decode_embedding_rope_atlas_bf16_2048_v2_int32_tc_bfloat16_t
```

Field 4 is `1` (nops) and field 5 onwards is the kernel name. `split(" ", 4)`
is exactly right. **No kernel name in §2 was ever corrupted**, and no number in
§2 moves because of this.

**Cheap falsification that would have shown the opposite.** If the mis-parse
had been real, every "kernel" in the §2 census would have been a decimal
integer, `kernels=24` would instead have been in the thousands (one bucket per
distinct byte count), and the `n/step` column could not have summed to 406.
§2's table shows 24 named kernels summing to 406.

**Hardened anyway.** The hazard the advisor is pointing at is real as a *latent*
hazard: the two patches are one `git apply` apart, and a future run with the
PR-91 patch would silently produce the corruption he described.
`research/decode_probe.py` now carries a single `parse_gpuprof_line()` helper
that auto-detects the layout (`parts[4].isdigit()` ⇒ 6-field), and
`research/nezuko_cb_idle.py` and `research/nezuko_pr158_split_kernels.py`
import it instead of re-implementing the split. Committed in
`f790af0` / `1a41b36`.

**Regression check.** Re-running the §2 census through the new shared parser on
`/tmp/nezuko-pr158-split1-204214.err` reproduces r1 exactly:
`records=88482 window=80794 window_span=9.859 ms/step gpu_busy_sum=8583.0 us/step kernels=24`,
with clean kernel names. Unit-tested on synthetic lines in both layouts.

### 4.1.c Anticipated objection: is the hook itself manufacturing the floor?

The GPUPROF hook is **one `addCompletedHandler` per `MTLCommandBuffer`**, not
per dispatch (`research/nezuko-pr158-gpuprof-hook.patch`, in
`CommandEncoder`/`Device::end_encoding` commit path). It records
`GPUStartTime`/`GPUEndTime`, which are driver-reported *GPU* timestamps, not
host-side wall reads.

That construction rules the hook out as the source of the Route-A floor:

- Across the whole unfuse sweep the **command-buffer count per step is
  unchanged at 45–46** while dispatches per step move 406 → 601. The number of
  completion handlers is therefore essentially constant across the arms whose
  difference defines the marginal. A per-CB instrument cost cancels in the
  subtraction.
- Route A's differences are in `gpu_busy_sum`, which is a sum of driver GPU
  timestamps. Host-side handler execution happens after `GPUEndTime` and cannot
  enter it.
- The independent check: the hook's total cost measured end-to-end is
  **+0.11 % of wall** (§ "Method note: the instrument"), i.e. ~9 µs/step, which
  is smaller than the 259–473 µs marginals it would have to explain.
- §4.6 re-runs the identical sweep with the hook **off entirely** and the arms
  keep their ordering, which closes the question empirically rather than by
  argument.

The one place a per-CB instrument cost *does* bite is the `SPLIT` sweep, where
CB count is the swept variable (45 → 406). §4.5 treats that explicitly.

## 4.2 Audit point 4: `1.419` and `1.596` are two different constants, both correct

**Advisor claim.** §2.a computes the SPLIT=1 inflation as `(8583 − 8007)/406 =
1.419`, but the 576 µs excess is produced by `406 − 45 = 361` *extra command
buffers*, so the per-CB price is `576/361 = 1.596`, and 1.419 is an arithmetic
slip that must be propagated.

**Verdict: the advisor found a real defect, but it is a missing constant, not a
wrong one. Both numbers are correct and they answer different questions.**

Let `c` be the marginal GPU cost of an extra command-buffer boundary and `W` the
pure kernel time of the 406 dispatches.

- `SPLIT=0`: 406 dispatches in **45** CBs ⇒ `busy₀ = W + 45c`.
- `SPLIT=1`: 406 dispatches in **406** CBs ⇒ `busy₁ = W + 406c`.

Therefore:

- **Per-CB price** `c = (busy₁ − busy₀)/361`. This is the advisor's 1.596, and
  **§2.a never states it. That is the real defect.**
- **Per-dispatch de-inflation of the SPLIT=1 census** is not `c`. The SPLIT=1
  `µs/call` column already contains `c` once per dispatch, but the target
  (SPLIT=0) still contains `c` once per 9 dispatches. What must be removed per
  dispatch is `c × (1 − 45/406) = 1.596 × 0.8892 = 1.419`. This is §2.a's
  number and it is right.

Consistency proof, using the r1 single-run values:

```
W        = 8583 − 406 × 1.596 = 7935 µs      (pure kernel time)
W + 45c  = 7935 +  45 × 1.596 = 8007 µs  ✔   (= measured SPLIT=0 busy)
8583 − 406 × 1.419            = 8007 µs  ✔   (= the census total §2.b reports)
```

Propagating 1.596 into the per-kernel census, as the revision request asks,
would make the census total **7935 µs**, which is the SPLIT=0 busy sum *minus
its own 45 command buffers* — i.e. a quantity that is not the step. So
**1.419 is retained in the census and 1.596 is now stated as the per-CB
price.** §2.a is amended in place to say both.

**Replicated values (§4.5).** With four `SPLIT=1` and four `SPLIT=0`
replicates instead of one each, `c = (8572.8 − 7999.4)/361 = 1.588 µs/CB`
(r1 single-run: 1.596) and the census de-inflation is `1.412 µs/dispatch`
(r1: 1.419). Both r1 constants survive replication to within 0.5 %.

## 4.3 Audit points 1, 2, 3, 6: the floor is a band, and the corollary is struck

All four are conceded. Taken together they replace one number with an interval.

**Point 1 — a level built from a slope.** Route A ("marginal") measures
`Δbusy/Δdispatch` over arms that add 39–195 dispatches. §2.b then multiplies
that *slope* by 406 to get a *level*, which assumes the floor is additive over
every dispatch in the step including the 138 large byte-bound ones that are
58 % of busy. That assumption was never tested and is not testable by any arm
in this report, because no available lever removes a dispatch from the top four
kernels. **Conceded: the 771 µs level is an extrapolation, not a measurement.**

**Point 2 — Route A and Route B are not independent.** Route B ("absolute",
the cheapest kernels' corrected `µs/call`) is computed from a single
unreplicated `SPLIT=1` run minus the 1.419 constant, and 1.419 is itself
derived from the same `SPLIT=1`/`SPLIT=0` pair that anchors the sweep. The two
routes share the instrument, the run, and the constant. **Conceded: "two
independent routes agree" is withdrawn.** §4.5 at least gives Route B a
replicated input; it does not make it independent of Route A.

**Point 3 — the retained marginals are mutually inconsistent.** `ssq` gives
1.91 µs/dispatch, `rsq` gives 2.42 over the same 195-dispatch delta, and the
joint four-knob arm gives 1.57 over 429. Against the ±0.12 % replicate
dispersion of `gpu_busy_sum` (§4.5) these differ far outside noise. There is no
single per-dispatch floor; there is a per-dispatch cost that depends on what
the dispatch does.

> **Headline restated as a band: 1.6–2.4 µs/dispatch ⇒ 640–990 µs/step ⇒
> 8–12 % of GPU busy (7.7–12.0 % of wall).** The band's endpoints are the
> extreme retained marginals, not a confidence interval.

**Point 6 — the corollary is falsified by my own table.** §2.b reading 2 says
"dispatch-removal is worth exactly 1.9 µs each and no more. Any claim that
fusing two kernels saves more than 1.9 µs per removed dispatch is claiming to
remove work or traffic." `rrr` removes 39 dispatches for 259.5 µs = **6.65 µs
each**, and §2.a excludes it precisely *because* it also removes traffic. So
the corollary is not falsified as physics — it is falsified as a *usable rule*,
because in this codebase every real fusion candidate also moves traffic, and
the traffic term dominates the floor term by 3.5×. **Reading 2 is struck and
replaced by the fusion pricing rule already promoted to
`research/CURRENT_RESEARCH_STATE.md` §4.1a: price a fusion by its traffic
delta, and treat the per-dispatch floor as a small additive bonus inside a
1.6–2.4 µs band.**

## 4.4 Audit point 4b: the percentage denominator

r1 headline item 6 and §2.b both report the floor as "9.6 % of the 8007 µs
step". 8007 µs is `gpu_busy_sum`, not the step. The step is the wall decode
time, 8.27 ms.

| quantity | value |
|---|---|
| per-dispatch floor total (r1 point estimate) | 771.4 µs/step |
| `gpu_busy_sum` | 8006.6 µs/step |
| **share of GPU busy** | **9.6 %** |
| wall decode step (median, hook on) | 8270.5 µs |
| **share of wall** | **9.3 %** |

Corrected in the headline. With the §4.3 band the honest statement is
**8–12 % of busy, 7.7–12.0 % of wall.**

## 4.5 Measurement (a): `SPLIT=1` replicated ×4, per-kernel median and half-range

**Ask.** Replicate the `SPLIT=1` census at least two more times; report per-kernel
median and half-range; flag any kernel whose half-range exceeds 10 % of its
median.

**Design.** `SPLITS='0 1 1 1 0' STEPS=200 PINGS=20 PROFILE_TOP=44` through
`research/nezuko_pr158_split_sweep.sh` — three fresh `SPLIT=1` runs bracketed by
two fresh `SPLIT=0` runs so a monotone drift over the 4-minute sweep would show
up as a split in the brackets. Each run is a separate worker process (cold
start, 200 steps, 199 steady). Combined with the r1 runs this gives n=4 per
level. Log `research/nezuko-pr158-r2-split-replicate.log`; analysis
`research/nezuko_pr158_r2_replicate_stats.py`. **0 token divergences on all
five runs.**

### 4.5.a Run-level dispersion

| level | per-run `gpu_busy_sum` (µs/step) | median | half-range |
|---|---|---|---|
| `SPLIT=1` (406 CBs) | 8583.0, 8565.7, 8580.0, 8562.4 | **8572.8** | **10.3 (0.12 %)** |
| `SPLIT=0` (45 CBs) | 8012.7, 8041.0, 7909.6, 7986.1 | **7999.4** | **65.7 (0.82 %)** |

| level | per-run wall median (ms) | median | half-range |
|---|---|---|---|
| `SPLIT=1` | 9.799, 9.807, 9.930, 9.773 | **9.803** | 0.079 (0.80 %) |
| `SPLIT=0` | 8.275, 8.287, 8.154, 8.266 | **8.271** | 0.067 (0.80 %) |

The `SPLIT=0` bracket runs (8012.7 first, 7986.1 last) differ by 0.3 %, well
inside the level's own 0.82 % spread, so no drift correction is warranted.

Two things follow that r1 could not state.

1. **The `SPLIT=1` census is far more reproducible than r1 assumed.** ±0.12 %
   on `gpu_busy_sum` means the 1.9-vs-2.4 disagreement in §4.3 point 3 is not
   instrument noise. It is real structure.
2. **The per-CB price now has an error bar.** Propagating both half-ranges
   worst-case, `c = (573.4 ± 76.0)/361 = **1.59 ± 0.21 µs/CB**`, i.e. [1.38,
   1.80]. r1's single-run 1.596 sits at the centre.

### 4.5.b Per-kernel median and half-range, n=4

Median and half-range of each kernel's total µs/step across the four `SPLIT=1`
runs. `µs/call` is the median total divided by `n/step`; it still carries the
1.412 µs/dispatch CB inflation (§4.2) and is *not* the corrected census.

| median µs/step | half-range | hr % | n/step | µs/call | kernel |
|---|---|---|---|---|---|
| 1498.4 | 2.30 | 0.2 % | 39 | 38.42 | `routed_nvfp4_swiglu_qmv_packed_top8keys_r1_bf16_v2` |
| 1330.9 | 2.39 | 0.2 % | 30 | 44.36 | `decode_nvfp4_qkv_h64` |
| 1114.0 | 1.76 | 0.2 % | 30 | 37.13 | `oproj_act_h64` |
| 865.8 | 1.48 | 0.2 % | 39 | 22.20 | `routed_shared_nvfp4_down_residual_bf16_r1_v5` |
| 635.1 | 1.72 | 0.3 % | 30 | 21.17 | `sliding_fused_attn_ring_v1` |
| 421.0 | 0.61 | 0.1 % | 1 | 421.01 | `lmhead_int5_base_coarse_delta` |
| 362.6 | 0.95 | 0.3 % | 10 | 36.26 | `decode_nvfp4_qkv_h48` |
| 319.7 | 0.70 | 0.2 % | 39 | 8.20 | `residual_rms_router_rpg8_keys_v1` |
| 302.9 | 0.70 | 0.2 % | 10 | 30.29 | `oproj_act_h48` |
| 293.4 | 0.44 | 0.1 % | 39 | 7.52 | `shared_nvfp4_swiglu_qmv_rows1` |
| 268.8 | 1.00 | 0.4 % | 1 | 268.77 | `dense_gate_up_swiglu` |
| 253.9 | 0.31 | 0.1 % | 10 | 25.39 | `full_fused_attn_grow_v1` |
| 243.1 | 1.46 | 0.6 % | 30 | 8.10 | `gate_sp_h64` |
| 203.0 | 0.64 | 0.3 % | 39 | 5.21 | `decode_router_top8_ordinal_table_norm` |
| 142.8 | 0.71 | 0.5 % | 41 | 3.48 | `rmsbfloat16` |
| 134.2 | 0.94 | 0.7 % | 1 | 134.17 | `dense_down_residual` |
| 77.3 | 0.26 | 0.3 % | 10 | 7.73 | `gate_sp_h48` |
| 76.1 | 0.36 | 0.5 % | 1 | 76.05 | `lmhead_exact_fused_int5_sparse_refine` |
| 9.3 | 0.15 | 1.6 % | 1 | 9.26 | `argmax_bfloat16` |
| 4.6 | 0.06 | 1.3 % | 1 | 4.61 | `lmhead_exact_winner_bf16_midpoint_threshold` |
| 3.9 | 0.10 | 2.4 % | 1 | 3.94 | `lmhead_coarse_argmax_stage1_v5` |
| 3.6 | 0.19 | 5.3 % | 1 | 3.55 | `gather_front` |
| 3.5 | 0.09 | 2.7 % | 1 | 3.52 | `decode_embedding_rope_atlas_bf16_2048_v2` |
| 2.9 | 0.04 | 1.5 % | 1 | 2.92 | `residual_rms_bf16_2048_v1` |

**Kernels with half-range > 10 % of median: 0 of 24.** The largest is
`gather_front` at 5.3 %, and it is 3.6 µs/step. Every kernel that carries
weight in the census is reproducible to better than 1 %.

**What this does and does not rescue.** It rescues the *precision* of Route B
(§4.3 point 2): the cheapest-kernel `µs/call` figures are stable to ~2–5 %, so
the 1.56–2.51 µs range r1 quoted is not a sampling artefact. It does **not**
rescue Route B's *independence*, because those figures are still `SPLIT=1`
values minus a constant derived from the same pair of levels. Replication
narrows the error bar on a quantity whose bias is unchanged.

### 4.5.c The same experiment prices a command buffer in three currencies

The `SPLIT` contrast changes exactly one thing — 45 command buffers per step
become 406 — with byte traffic, kernel set, and kernel call counts held fixed.
Dividing each replicated median excess by the 361 extra command buffers gives
three prices for the *same* event, and the three together are the honest answer
to "what is a command buffer worth":

| currency | `SPLIT=0` median | `SPLIT=1` median | excess / step | ÷ 361 CBs |
| --- | --- | --- | --- | --- |
| `gpu_busy_sum` (per-CB device time) | 7999.4 µs | 8572.8 µs | 573.4 µs | **1.59 ± 0.21 µs/CB** |
| wall (probe `decode_step`) | 8271 µs | 9803 µs | 1532 µs | **4.25 µs/CB** |
| wall − busy_sum ("gap") | 272 µs | 1230 µs | 958 µs | **2.66 µs/CB** |

Three consequences, all of which cut against r1's framing:

1. **The busy-sum price is the smallest of the three.** `gpu_busy_sum` is a sum
   of per-command-buffer device intervals; it sees the *device-side* cost of
   one more buffer and nothing else. r1 quoted only this column.
2. **Wall costs ~2.7× more than busy.** The extra 2.66 µs/CB is submission and
   completion work that is not inside any command-buffer interval. It is real
   and it is the currency the score is denominated in — but it is also the
   currency in which a *dispatch* (not a command buffer) may cost far less,
   because MLX already batches many dispatches into one buffer.
3. **A command buffer is not a dispatch.** Nothing in this table licenses
   pricing a *dispatch* at 1.59 µs, let alone 4.25 µs. That inference —
   "removing a dispatch saves a per-CB constant" — is precisely what §4.6 and
   §4.7 test directly, in wall currency, by removing real dispatches.

## 4.6 Measurement (b): the unfuse sweep re-run in wall currency

### 4.6.a Why this run exists

r1's unfuse table was reported in `gpu_busy_sum`. Audit point 5 objected that
one arm — `rsdr` (`DARKBLOOM_FUSED_ROUTED_SHARED_DOWN_RESIDUAL=0`) — showed a
busy-sum cost far larger than its wall cost, which is not something a genuine
per-dispatch cost can do: if a dispatch really costs the machine time, that
time has to appear in the wall clock. **I concede audit point 5 without
qualification**, and it is now the organising result of this section rather
than a footnote. Busy-sum is an instrument reading; wall is what the score
pays. Where they disagree, wall wins.

### 4.6.b Design, and the one disclosable deviation

Six arms, run as a **palindrome** (`base, rrr, rsdr, ssq, rsq, base2` then the
exact reverse) so that any monotone thermal or clock drift across the session
cancels in the pass-average. Each arm: 200 teacher-forced decode steps on
`correctness_prompts/public_longcopy_gate_english_512_256.json`, first step
discarded, `decode_step` wall median over the remaining 199. The probe hook is
**off** (`HOOK=0`) so the wall figures carry no instrument overhead at all.

Command:

```bash
HOOK=0 PASSES=2 PALINDROME=1 STEPS=200 \
  OUT=research/nezuko-pr158-r2-unfuse-wall.log \
  bash research/nezuko_pr158_unfuse_sweep.sh
```

**Disclosable deviation.** These are *probe* walls, not `--local-iterate`
scored walls. I did not use `--local-iterate` because it rebuilds the worker and
would have discarded the GPUPROF-instrumented binary that measurements (a) and
(c) depend on. The probe wall is a strictly tighter instrument for this purpose
— it reports a median over 199 individually-timed steady steps rather than one
aggregate rate — but it is not the ranked number, and no arm here is proposed
for submission. Nothing in `Sources/` changed for this run; every arm is an
environment-variable ablation of an already-default-on fusion.

**The base drift is the reason the palindrome exists.** In pass 1 alone,
`base` (21:54) and `base2` (21:58) — the identical unmodified configuration,
four minutes apart — differed by 111 µs (1.3 %), which is the same order as the
arm effects being measured. Any single-pass reading of this sweep is therefore
uninterpretable, including r1's. The pass-averaged baseline below is the only
one I will quote.

<!-- TABLE-4.6.c -->

## 4.7 Measurement (c): a traffic-neutral unfusion, the cleanest test available

### 4.7.a Why the four arms in §4.6 cannot settle the question

Every arm in §4.6 removes a fusion that also *moves bytes*. Unfusing
`routed_swiglu_qmv` does not just add 5 dispatches per layer; it materialises
intermediates that the fused kernel kept in registers. So each arm's wall cost
is `n_dispatch × (per-dispatch floor) + Δbytes × (byte price)`, and with four
arms that all vary both terms together, the two coefficients are not separable.
That is the real reason r1's "≈1.9 µs/dispatch" is not identified — not
sampling noise, but confounding.

The router fusion flags give a way out, because the runtime already ships two
*independent* sinks on the same code path
(`Sources/MLXFastModel/LagunaRuntimeModel.swift`, branch at the decode router
top-8 site):

- `DARKBLOOM_FUSED_ROUTER_CAST` sinks the BF16→FP32 cast of the 256-element
  router GEMV output into the top-8 kernel's first instruction.
- `DARKBLOOM_FUSED_ROUTER_NORM` sinks the top-k renormalization — the sum over
  the eight selected scores and the broadcast divide — into the same kernel.

Turning the **norm** sink off alone (`nonorm`) keeps the cast sink, so the arm
stays on the identical kernel and identical inputs; the only change is that
`weights = weights / weights.sum(axis: -1, keepDims: true)` now runs as two
standalone MLX dispatches per sparse layer. Those two dispatches touch **eight
FP32 elements**: a 32 B read for the sum, then a 32 B read plus 32 B write for
the divide. Call it ~100 B per layer, ~4 KB per step against a step that already
moves gigabytes. **This is a dispatch-count change with essentially zero traffic
change** — exactly the traffic-neutral unfusion the audit asked for.

Turning the **cast** sink off (`nocast`) additionally forces
`logits = projectedLogits.asType(.float32)`, a third dispatch per layer that
reads 512 B and writes 1024 B. `nocast − nonorm` therefore isolates *one*
dispatch per layer carrying ~1.5 KB, giving a byte-slope measured inside the
same tiny-dispatch regime.

<!-- TABLE-4.7 -->


