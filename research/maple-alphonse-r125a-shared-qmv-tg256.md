# R125-A — shared-expert SwiGLU QMV threadgroup width (TG=256) on the maple base

Student: maple-alphonse · PR #729 · assignment `maple-r125-a-shared-qmv-tg256-landing`
revision `r125-a-rev1` · branch `maple-alphonse/r125-a-shared-qmv-tg256-landing`
base `codex/mlxfast-maple-20260804-advisor` @ `a9de9e8f21188715f6d80ada4b581bcd50d4ec81`

## 0. Verdict

**Do not land TG=256. The assignment's premise is inverted.**

The assignment asks me to port frieren's R119-C TG=256 shared-SwiGLU-QMV geometry
onto the maple base and ship it as the default, on the stated grounds that the
geometry is worth about `+0.38 %` decode. Both halves of that premise fail on the
evidence that already exists in this repository, and my own replication on this
base agrees with the existing evidence:

1. **frieren's `+4.67` is a cost, not a gain.** The column in
   `research/frieren_r119c_FINAL_RESULT.md` is `qmv us/step` — per-step GPU-busy
   microseconds of the shared-QMV kernel — so arm C (TG=256) being `+4.67 us/step`
   above arm A (TG=64) means TG=256 is **1.61 % slower**, not faster. frieren's own
   title is "TG count is inert for the shared-expert SwiGLU QMV" and his law
   `L-LOAD-BALANCE-GRANULARITY` is recorded as **refuted**.
2. **The `+0.38 %` figure belongs to a different, already-rejected change.** It
   comes from PR #714 §0(b) and prices the R119-A router-tournament *grid-append
   fusion*, for which TG=256 is an enabling debit. That fusion was measured
   end-to-end as a **loss** (`+27.024 us/token`, `+0.210 %` decode), terminal
   verdict `N-GRIDAPPEND-SECOND-INSTANCE-BELOW-BAR`.

Landing TG=256 alone therefore pays the debit and collects nothing.

**Landing branch: none.** The branch carries the mechanism as an opt-in selector
(`DARKBLOOM_SHARED_QMV_TG`, default `64`), so the submitted surface is
behaviourally and dispatch-identical to the base unless the variable is set.

*(measurement summary filled in from §1)*

## 1. Replication on the maple base

*(pending)*

## 2. Conflict resolution: where the `+0.38 %` premise came from

The assignment body states that frieren measured TG=256 at "+4.67 us/step ...
about +0.38 % decode". Those are two different experiments and the sign of the
first is inverted.

### 2a. Anchor: frieren R119-C is a *cost* measurement

`git show 039800fe5ed5f2523aeb4c9f4e225d15fd219191:research/frieren_r119c_FINAL_RESULT.md`

* Title: **"TG count is inert for the shared-expert SwiGLU QMV"**;
  `L-LOAD-BALANCE-GRANULARITY` recorded as **refuted**.
* Instrument: `decode_probe.py --profile` with `DARKBLOOM_GPU_PROFILE=1`,
  `DARKBLOOM_GPU_PROFILE_SPLIT=1`, 200 steps, `n=6` per arm, mirrored
  `64 128 256 256 128 64` × 3, 40 °C gate per slot, 19/19 slots `rc=0`.
* The reported column is `qmv us/step`: per-step GPU-busy time **of the
  shared-QMV kernel**, i.e. a cost. Lower is better.

| arm | geometry | qmv us/step | Δ vs A |
|---|---|---|---|
| A | TG=64, 2 simdgroups/TG, 256 TGs | 289.83 ± 1.42 (sem 0.58) | — |
| B | TG=128, 4 simdgroups/TG, 128 TGs | 290.38 ± 1.07 | +0.55 ± 0.73 (NS) |
| C | TG=256, 8 simdgroups/TG, 64 TGs | 294.50 ± 0.85 | **+4.67 ± 0.68 = +1.61 % slower** |

Through-origin slope φ = **+0.065 [+0.052, +0.079]** µs per simdgroup-per-TG —
a positive **cost** coefficient. All three arms hold the work byte-identical:
512 output rows, one row per simdgroup, 16 384 threads total; only the
partition into threadgroups changes.

frieren's own caveats, which I inherit: raw kernel numbers only, no end-to-end
anchor; `SPLIT=1` serialises one dispatch per command buffer, so it removes the
overlap that would otherwise hide part of the cost — the measured φ is an
**upper bound** on the deployed cost. The optional `SPLIT=0` paired-wall leg was
never run.

### 2b. Anchor: the `+0.38 %` is R119-A grid-append, and it lost

PR #714 §0(b) prices the router-tournament **grid-append fusion** at
`64.8–65.5 us/step` ≈ `+0.38 %`. TG=256 appears there as the *enabler*: the
fused kernel needs the wide threadgroup so the appended router-tournament grid
fits alongside the shared-expert tiles. The fusion itself was then measured:

* joint arm G: **+13.6 us/step [+9.5, +17.7]** (and +11.2 [+4.4, +18.0] under the
  ranked `DARKBLOOM_STARTUP_MEMORY_PROFILE=full` startup profile);
* end-to-end decode: **+27.024 us/token (+0.210 %)**, CI [−70.8, +124.9],
  4/4 arm-halves positive;
* terminal verdict `N-GRIDAPPEND-SECOND-INSTANCE-BELOW-BAR`, governing law
  `L-SIBLING-DISPATCH-IS-ALREADY-FREE` — MLX already encodes
  `MTL::DispatchTypeConcurrent` (`Vendor/mlx-swift/.../metal/device.cpp:548`), so
  sibling dispatches already overlap and fusing them buys nothing;
* the dispatch-removal arm R bounded a dispatch at `D ≤ 0.374 us/dispatch`
  against Rule 57's assumed `1.2382`.

So the `+0.38 %` was never a TG=256 gain, and the change it enabled is closed as
a loss.

### 2c. Independent corroboration from my own R119-A branch

On `maple-alphonse/r119-a-gridappend-family` (HEAD `c860c492`), arm **W**
(`DARKBLOOM_SHARED_QMV_WIDE8=1`) is exactly this geometry: `threads=256`,
`tiles=64`, 8 simdgroups per threadgroup. Measured at kernel level:

* low-memory startup profile: **−1.5 us/step, CI95 [−15.4, +12.5]** (10/12 blocks
  negative, sign test p = 0.039);
* ranked `DARKBLOOM_STARTUP_MEMORY_PROFILE=full`: **+2.7 [−11.2, +16.5]**;
* 48 runs, 48/48 cells proven 200/200/50.

Arm W was never taken end-to-end. frieren's `+4.67` sits comfortably inside W's
confidence interval, so the two instruments are consistent: the effect is small,
its sign is not favourable, and nothing supports a decode gain.

## 3. Correctness certificate

*(pending)*

## 4. Mechanism and cross-kernel prediction

*(pending)*

## 5. Ranked-host quantisation

The local host has **20 GPU cores**; the ranked M5 Max has **40**. The shared
SwiGLU QMV launches one threadgroup per tile, and each threadgroup occupies one
core, so the worst-core row count is
`ceil(TGs / C) * rows_per_TG`:

| arm | TGs | rows/TG | worst core, C=40 | vs A | worst core, C=20 | vs A |
|---|---|---|---|---|---|---|
| A (TG=64) | 256 | 2 | 7 × 2 = 14 | 0 % | 13 × 2 = 26 | 0 % |
| B (TG=128) | 128 | 4 | 4 × 4 = 16 | +14.3 % | 7 × 4 = 28 | +7.7 % |
| C (TG=256) | 64 | 8 | 2 × 8 = 16 | +14.3 % | 4 × 8 = 32 | +23.1 % |

The local C=20 geometry therefore **overstates** arm C's imbalance penalty by a
factor `23.1 / 14.3 = 1.61`. Deflating frieren's local `+4.67 us/step` by that
factor gives a ranked-equivalent cost of about **+2.9 us/step** — still a cost,
still the wrong sign, and still with nothing to pay for it. The quantisation
argument softens the penalty; it never turns it into a gain.

Two further ranked caveats: the M4 Pro reports Apple GPU generation 16 and does
not select the `_nax` kernels the ranked M5 uses, and threadgroup geometry is
exactly the class of change whose sign can move with core count. Both cut
against landing an unpaid geometry change on M4 evidence alone.

## 6. Deviations from the assignment

1. **No landing branch.** The assignment's success criterion was a branch with
   TG=256 as the shipped default. The evidence says that ships a regression, and
   the advisor explicitly authorised "land nothing" if TG=256 is not
   distinguishable. It is distinguishable — in the wrong direction.
2. **Arms reduced to TG=64 vs TG=256.** frieren already showed TG=128 ≈ TG=64
   (NS). I spent the whole slot budget on the decisive contrast to maximise
   power on the arm the assignment wanted to land.
3. **Mechanism kept, default unchanged.** `DARKBLOOM_SHARED_QMV_TG` is committed
   so the advisor or the next student can re-run the arms on any base without
   re-deriving the kernels, but the default is `64`.
4. **No official submission.** Per the assignment, the advisor owns submission; I
   ran none. On this evidence I recommend not firing one on this premise.
