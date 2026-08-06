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
4. **The gap is real, not a profiler artifact, and it is not per-command-buffer.**
   A paired ABBA run of the same binary with the hook on and off puts the hook's
   cost at `+0.11 %` (indistinguishable from run-to-run spread). Two independent
   sweeps that vary buffers per step 2.5× and 4.5× leave the gap flat. The gap
   decomposes as **16 µs IPC + ~0.56 µs × buffers + ~220 µs step-fixed host
   cost**, i.e. ~0.54 µs per MLX dispatch of host-side work.
5. **§1.2's pre-registered kill rule fires for both kernels.** `gate_sp` runs at
   100 % useful-lane fraction with no divergence; `residual_rms_router`'s idle
   half is a compile-time whole-simdgroup guard, so there is nothing for a
   ballot/ctz compaction to compact. The #137 re-geometrization does not apply.
   §1.3 is therefore not entered and §2 fires.
6. **§2's correction is not the one the assignment expected.** Because hiding is
   ~absent, the 10 HIGH-RISK rows are *not* over-attributed by overlap. They are
   over-attributed by a different mechanism: a fixed ~5–8 µs per-dispatch floor
   that does not shrink when the kernel's work shrinks. Only *removing a
   dispatch* recovers the floor; making a kernel cheaper recovers only its
   work-proportional part. The corrected census is in §2.

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
actually produces at `SPLIT=0` — and §0.1 explains why that agreement is
uninformative.

### 1.1.b Verdict: the gap is ABSOLUTE, and I can decompose it

Comparing the two rows alone is not a clean test (different binaries, and one
of them is corrupt). So I measured the gap's structure directly, three ways.

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

**None of those three terms references GPU busy time.** The gap does not
contain a term proportional to how long the GPU worked. It is a host-side
absolute cost. **§4.1's "absolute" branch is the correct one for the decode
axis**, and the assignment's framing follows: as `gpu_busy` falls, this cost is
a *growing* share of the step. On this host it is 3.04 % of an 8.27 ms step
where it was ~3.3 % of a 9.8 ms step.

Two caveats I will not paper over. First, the residual is **~224 µs and 406
dispatches came out at 0.55 µs each** — both sweeps held dispatch count fixed
at 406, so I cannot separate "fixed per step" from "0.55 µs per dispatch" from
these data. That distinction decides whether the pool is reachable at all, and
it is measured in §1.1.d. Second, this is a *host* cost and the M5 has a
different CPU: the **structure** (absolute, not proportional) transfers; the
**224 µs magnitude** does not.

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
the absolute µs value, retire it as an explanation of the overlap question.

**Consequence for the corollary at `CURRENT_RESEARCH_STATE.md:197-199.`** The
programme's standing worry was that isolated-duration claims are inflated
because the kernel is partly hidden behind others. On the decode axis that
worry is **unfounded**: nothing is hidden. Isolated duration ≈ exposed serial
time. But the claims are still over-attributed, by a completely different
mechanism — see §2.

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
