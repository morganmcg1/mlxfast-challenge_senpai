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

## 2. Method note: the instrument

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
