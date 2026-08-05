# PR #57 T1 — gather-GEMM threadgroup co-residency: is co-residency a currency?

Assignment `maple-2026-08-05f-gathergemm-coresidency`, revision `r1`, student
`maple-tanjiro`. Base `codex/mlxfast-maple-20260804-advisor` @
`5178d452c513c61e619f4dd788185c797e065529`. Zero submitted bytes: nothing in
this PR touches `benchmark.json`'s 97 `editablePaths`.

Primary metric: `coresidency_throughput_gain_128t_1_to_24x`, direction
`maximize`, assignment baseline `1.13`.

---

## 0. Status of this document

**Section 1 (pre-registration) was committed before any 128-thread timing was
observed** (commit `caaae05`; it was `8e5c5b0` before the §8.1 rebase, and the two
carry a byte-identical patch — `git diff <sha>^ <sha>` hashes to
`f894cfaa0b36785026f21d4df95d70026a26f794` for both). That commit is the audit
trail: the ruling in §7 does disagree with what §1.6 says the ruling must be, and
§7.2 says so in the open rather than moving a threshold. Sections 2 onward were
written after the probe ran.

Result in one line: the pre-registered metric fires the "hypothesis survives"
row, and the controls in the same run falsify the hypothesis. §7.2 explains why
the metric was the wrong instrument; §7.3 is the recommendation.

---

## 1. Pre-registration (committed before the 128t result)

### 1.1 Host

| fact | value | how obtained |
| --- | --- | --- |
| chip | Apple M4 Pro | `system_profiler SPDisplaysDataType` |
| GPU cores | **20** | `system_profiler SPDisplaysDataType` → `Total Number of Cores` |
| unified memory | 48 GiB (`hw.memsize = 51539607552`) | `sysctl` |
| macOS | 26.5.2 | `kern.osproductversion` |
| `maxThreadgroupMemoryLength` | 32,768 B | `MTLDevice` |
| `maxThreadsPerThreadgroup` | 1024 × 1024 × 1024 | `MTLDevice` |
| Apple GPU family | generation 16 (`applegpu_g16s`) | `Vendor/mlx-swift/.../backend/metal/device.cpp:913-931` |

This is the same host class nezuko used for PR #56, which is what makes her
1024-thread numbers a usable control rather than a cross-machine comparison.

Generation 16 means the `_nax` kernel family **cannot execute** here: selection
needs generation ≥ 17 and macOS ≥ 26.2 (`device.cpp:913-931`). Everything below
is therefore a *scheduling-model* measurement using a footprint-matched
synthetic, plus a static/compile-time reading of the real kernel. It is not a
measurement of the ranked M5 kernel running.

### 1.2 The metric as written does not have the baseline the brief gives it

The brief defines the gain as

```
G = (K_hi / t(K_hi)) / (1 / t(1)),      K_hi = 24 * cores
```

and states the 1024-thread baseline for the same quantity is `1.13`.

Those two statements are inconsistent. Applying the brief's formula to nezuko's
published PR #56 Phase E data (1024 threads, 18,432 B threadgroup memory, real
sliding-window body; `t(1) = 9.23 µs`, `t(240) = 98.19 µs`, `cores = 20`) gives

```
G_lone = (240 / 98.19) / (1 / 9.23) = 2.4442 / 0.10834 = 22.56
```

not 1.13. The value near 1.13 comes from the **per-core** form, whose
denominator is one threadgroup per core rather than one threadgroup on the whole
GPU:

```
G_percore = (K_hi / t(K_hi)) / (cores / t(cores))
          = (240 / 98.19) / (20 / 9.45) = 2.4442 / 2.1164 = 1.1549
```

So the pre-registered thresholds (≤ 1.25 / 1.25–2.00 / ≥ 2.00) can only have
been written for `G_percore`. Two further notes on the baseline itself:

* The brief says `1.13`. Nezuko's own numbers give `1.1549`. Her "13%" figure is
  the µs-per-threadgroup drop from `0.4725` (K = 20) to `0.40913` (K = 240),
  which is a **15.5% throughput ratio**, not 13%. The advisor's standing
  §0.9.11/§0.9.13 warning to re-derive every quoted number applies to `1.13`
  too. I keep `1.13` as the declared `primary_metric.baseline` because that is
  the assignment contract, and report `1.1549` as the re-derived value.
* Nezuko's `K_hi = 240` at 1024 threads is **12 threadgroups per core** against
  a residency limit of 3 per core, i.e. 4× oversubscribed. Her 1.155 is
  therefore not a pure co-residency gain; it also contains amortisation of
  per-dispatch ramp over four sequential waves. The 128-thread `K_hi = 24 ×
  cores` is *exactly* the residency limit, so it is a different animal. I report
  both the at-residency and the oversubscribed points for every geometry so the
  two effects can be separated.

**Pre-registered decision:** the ruling in §1.6 is applied to `G_percore`.
`G_lone` is reported alongside it for completeness.

### 1.3 The metric as written cannot discriminate the hypothesis it is aimed at

The question behind T1 is whether *threadgroup co-residency* is a currency that
§0.9.8's "recoverable overlap" can spend. But at the shipped geometry:

| threads/TG | 1 TG per core | 24 TGs per core |
| --- | --- | --- |
| 128 | **4 warps/core** | 96 warps/core |
| 1024 | 32 warps/core | (not resident; 3/core is the limit) |

"One threadgroup per core" at 128 threads is 4 warps per core, which is deeply
under-occupied on any Apple GPU core. A large `G` at 128 threads is therefore
the *expected* result under the null hypothesis that only warp-level occupancy
matters, and it would say nothing about threadgroups. Conversely nezuko's small
1024-thread gain is expected under the same null, because her denominator
already had 32 warps per core.

In other words: as specified, T1's discriminator is confounded with warp
occupancy, and both competing hypotheses predict a large 128-thread number.

**Pre-registered addition (Table B in §1.6).** I add a geometry sweep at
**constant per-thread work** over threads/TG ∈ {128, 256, 512, 1024} and plot
aggregate work rate against *warps in flight per core*. This is the unconfounded
form of the question:

* if the simdgroup/warp is the scheduling unit, the four curves collapse onto a
  single function of warps per core;
* if the threadgroup is an independent scheduling unit, the curves separate,
  with small threadgroups systematically better at matched warps per core.

A `threadgroup_barrier` costs more as simdgroups per threadgroup grows, which is
one legitimate mechanism by which the threadgroup could be the unit. To keep
that mechanism attributable rather than hidden, the same sweep is repeated with
`simdgroup_barrier`, whose cost does not scale with threadgroup size.

### 1.4 Instrument

`research/tanjiro_gathergemm_occupancy_probe.swift`.

* **Phase A** builds the *real* shipped `_nax` expert kernel by shelling out to
  `research/nax_msl_compile_check.sh` (which extracts the JIT preamble bodies
  straight from `Vendor/mlx-swift/Source/Cmlx/mlx-generated/*.cpp`), links the
  result with `xcrun metallib`, loads it with `device.makeLibrary(URL:)`, and
  reads `staticThreadgroupMemoryLength` off the compiled
  `MTLComputePipelineState`. No kernel source is hand-copied into the probe.
  This is the no-drift analogue of nezuko's label-slicing.
* **Phases B/C/D** use a synthetic kernel footprint-matched to the T2 census:
  **9,224 B** static threadgroup memory (576 × 16 B staging chunks + an 8 B
  bounds pair) and 128 threads (4 simdgroups) per threadgroup, with a
  per-iteration dependency chain of device load → threadgroup staged store →
  barrier → four threadgroup loads feeding a serial FMA chain → barrier.
* Device reads come from a 256 KiB buffer, deliberately cache resident. Nezuko
  PR #56 §4.3 showed the real sliding-window kernel issues ≈443 GB/s at K = 32,
  i.e. 170% of the 260.2 GB/s M4 DRAM ceiling, so the regime under test is
  cache-served and latency bound. A DRAM-bound synthetic would be measuring a
  different machine.
* Timing follows nezuko's method exactly: 200 serial dispatches in one command
  buffer, `cb.gpuEndTime - cb.gpuStartTime` divided by the dispatch count, best
  of 3 command buffers.
* `reps` is auto-calibrated once so a lone 128-thread threadgroup lands near
  10 µs, then held **fixed** across every geometry, which is what makes
  per-thread work constant.
* A dead-code-elimination guard checks that doubling and quadrupling `reps`
  doubles and quadruples the time.

### 1.5 Pre-registered instrument-validity gates

The 128-thread number is only reportable if the instrument first passes:

* **C0 — DCE guard.** `t(2·reps)/t(reps) ∈ [1.65, 2.35]` and
  `t(4·reps)/t(reps) ∈ [3.3, 4.7]`.
* **C1 — literal replication.** `research/nezuko_occupancy_probe.swift` run
  unmodified on this host must reproduce her Phase E staircase with
  `a/t(1) ∈ [0.80, 0.96]` (she reported 0.884) and a K = 20 → 240 per-core gain
  in `[1.08, 1.24]` (she reported 1.155).
* **C2 — instrument transfer.** My synthetic at 1024 threads / 9,224 B must show
  a staircase whose fitted wave width `W` is within ±25% of `3 × cores = 60`
  threadgroups, confirming the 3072-threads-per-core residency invariant holds
  at my footprint and in my kernel.

If C1 or C2 fails, T1 is reported as **instrument-invalid** and no ruling is
issued on the primary metric.

### 1.6 Pre-registered decision tables

**Table A — the assignment's ruling, applied to `G_percore` at 128 threads,
`K_hi = 24 × cores = 480`.** Executed exactly as specified, whatever I think of
the confound.

| `G_percore` | ruling |
| --- | --- |
| **≤ 1.25** | §0.9.8's co-residency-as-currency claim is **STRUCK**. The gather-GEMM overlap family is **closed**. The 15.4 ms recoverable-overlap figure is **withdrawn**. The axis moves to byte reduction only. |
| **1.25 – 2.00** | **Ambiguous.** Report the full curve; the advisor decides. No family is closed and no figure is withdrawn on my authority. |
| **≥ 2.00** | §0.9.8 **survives** on this axis. Threadgroup count is the scheduling unit and I state that plainly. |

**Table B — the unconfounded discriminator.** Let `S` be the maximum relative
spread of normalised work rate across geometries at matched warps-per-core, over
the warps-per-core values attained by at least three of the four geometries.

| `S` | ruling on "is the threadgroup the scheduling unit?" |
| --- | --- |
| **≤ 0.15** | **No.** The curves collapse; warps in flight per core explains the throughput, and Table A's 128-thread gain is an occupancy artefact rather than evidence about threadgroups. |
| **0.15 – 0.40** | **Partly.** Report the residual and attribute what the `simdgroup_barrier` control removes. |
| **≥ 0.40**, small threadgroups faster | **Yes.** Threadgroup count carries independent scheduling value. |

Table B does not override Table A. Both are reported. Where they conflict, §5
says so and leaves the disposition to the advisor.

### 1.7 Pre-registered contextual fact that bears on the ruling either way

Established under T2 before this document was committed, from source:
`Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/quantized.cpp:1914-1940`
dispatches the expert kernel as `dispatch_threadgroups(grid_dims, group_dims)`
with `group_dims = (32, 1, 4) = 128` threads and `grid_dims = (N/64, 256, 1)`,
i.e. **4096 threadgroups** for the gate/up shape (N = 1024) and **8192** for the
down shape (N = 2048). On 20 cores that is 205 / 410 threadgroups per core; on
the ranked 40-core M5 Max it is 102 / 205 per core. Both are far beyond the
24-per-core residency limit.

Pre-registered implication: **whatever gain exists between 1 and 24
threadgroups per core, the shipped dispatch is already past it.** A large
Table A number would therefore be a statement about the shape of the occupancy
curve, not about unclaimed headroom in the shipped kernel. I commit to saying
this in §5 regardless of which Table A row fires.

---

## 2. Phase A — the real kernel's compiled footprint

The probe builds the real metallib through `research/nax_msl_compile_check.sh`
and asks the driver, not the source, for the footprint of two shipped
instantiations:

| pipeline | staticThreadgroupMemoryLength | maxTotalThreadsPerThreadgroup | threadExecutionWidth |
|---|---|---|---|
| `fp_gather_qmm_rhs_expert_nax_check_2048x1024` | 9232 B | 1024 | 32 |
| `fp_gather_qmm_rhs_expert_nax_check_512x2048` | 9232 B | 1024 | 32 |

Two things follow.

**The census is confirmed.** `research/tanjiro-gathergemm-d2-census.md` predicts
9,224 B from source (9,216 B of `NAXWsChunk16<bfloat> Ws_storage[576]` plus 8 B
of `int bounds[2]`). The driver reports 9,232 B — the census total rounded up to
the 16-byte allocation granularity. There is no fourth hidden array and no
incidental slack: `Ws_storage` alone is 99.91% of the footprint.

**The kernel can launch at its dispatch geometry.** The advisor asked me to read
`maxTotalThreadsPerThreadgroup` and flagged that a value below 128 would be a
finding in itself, because the shipped dispatch is `group_dims = (32,1,4) = 128
threads` (`quantized.cpp:1914`). It reports 1024, eight times the requirement.
No occupancy story here is a launch-failure story.

All three synthetic kernels used in Phases B–D also report 9,232 B, so every
geometry and residency sweep below is footprint-matched to the shipped kernel
rather than to an empty threadgroup.

Local reachability caveat, stated once and carried through: this host is Apple
GPU generation 16, and `_nax` variants require generation ≥ 17 with macOS ≥ 26.2
(`Vendor/mlx-swift/.../backend/metal/device.cpp:913-931`). MLX would not *select*
these kernels at runtime here. I obtain the pipelines by compiling the shipped
MSL directly, so the footprint and launch limits are the real ones, but no
end-to-end `_nax` timing claim can be made from this host.

## 3. Phase B — 128-thread threadgroup-count sweep

Calibration chose `reps = 24` from `t(K=1, 128t, reps=64) = 26.301 µs`. Gate C0
(dead-code elimination) **passed**: doubling the loop count scaled time by
2.346× and quadrupling it by 3.623×, inside the pre-registered `[1.65, 2.35]`
and `[3.3, 4.7]` windows, so the timed body is really executing.

| K | µs | K | µs | K | µs | K | µs |
|---|---|---|---|---|---|---|---|
| 1 | 6.768 | 40 | 8.163 | 161 | 18.376 | 480 | 35.473 |
| 4 | 6.831 | 48 | 8.150 | 168 | 18.471 | 481 | 36.437 |
| 10 | 7.449 | 80 | 9.044 | 240 | 21.222 | 520 | 38.241 |
| 20 | 7.026 | 120 | 12.262 | 320 | 27.000 | 640 | 45.466 |
| 24 | 8.147 | 160 | 15.459 | | | 960 | 64.587 |
| | | | | | | 1920 | 121.720 |

**Primary metric, `K_hi = 480 = 24 threadgroups/core:**

```
G_percore = (480/35.473) / (1/6.768)  / 20  =  4.7533
G_lone    = (480/35.473) / (1/6.768)        = 91.5854
```

Staircase fit at 128 threads/TG: **`W = 20` threadgroups per wave (1.00 per
core), step `a = 1.2154 µs`, offset `b = 6.0043 µs`, rms relative residual
7.46%, `a/t(1) = 0.1796`.**

Two features of this table matter more than the headline number.

**There is no discontinuity where a residency limit would put one.** Between
K = 480 and K = 481 — the point where nezuko's binary search says a 128-thread
threadgroup stops being co-resident — time goes 35.473 → 36.437 → 38.241 µs at
K = 520. That is the same marginal slope as everywhere above K ≈ 640. A hard
residency cliff at 480 would show a step of roughly one full wave (`a`); it
shows 0.96 µs, which is under one step.

**The curve saturates long before 480.** From K = 640 to K = 1920 the marginal
cost is a constant 0.0594 µs per threadgroup. Per-threadgroup cost is already
within 8% of that asymptote by K = 240. So the large `G_percore` is not
"co-residency being bought" up to 24/core; it is the fixed launch overhead
`b = 6.0 µs` being amortised, which any K ≫ 1 achieves.

## 4. Phase C — constant per-thread work geometry sweep

§1.3 pre-registered the confound: at one threadgroup per core, 128 threads/TG
gives 4 warps/core and 1024 threads/TG gives 32, so comparing geometries at
equal *threadgroup* count compares two different warp occupancies. Phase C fixes
total thread-iterations and compares at matched warps per core, and runs the
whole sweep twice — once with `threadgroup_barrier` and once with
`simdgroup_barrier` — so barrier cost can be separated from scheduling.

**Normalised throughput at matched warps/core (thread-iterations/µs, 128t = 1.000):**

| warps/core | scope | 128t | 256t | 512t | 1024t | spread |
|---|---|---|---|---|---|---|
| 32 | tg | 1.000 | 0.943 | 0.847 | 0.719 | 0.281 |
| 64 | tg | 1.000 | 0.997 | 0.855 | 0.690 | 0.310 |
| 96 | tg | 1.000 | 0.982 | 0.862 | 0.722 | 0.278 |
| 192 | tg | 1.000 | 0.971 | 0.846 | 0.706 | 0.294 |
| 384 | tg | 1.000 | 0.975 | 0.872 | 0.714 | 0.286 |
| 32 | sg | 1.000 | 0.933 | 0.849 | 0.796 | 0.204 |
| 64 | sg | 1.000 | 1.017 | 1.000 | 0.905 | 0.112 |
| 96 | sg | 1.000 | 0.978 | 0.964 | 0.854 | 0.146 |
| 192 | sg | 1.000 | 0.981 | 0.959 | 0.895 | 0.105 |
| 384 | sg | 1.000 | 0.993 | 0.980 | 0.917 | 0.083 |

Max spread: **0.310 with `threadgroup_barrier`, 0.204 with `simdgroup_barrier`.**

**Saturated marginal throughput** — the asymptotic slope, which removes launch
overhead entirely:

| scope | 128t | 256t | 512t | 1024t |
|---|---|---|---|---|
| tg (Gthread-iter/s) | 51.751 | 50.707 | 46.811 | 37.441 |
| tg (relative) | 1.000 | 0.980 | 0.905 | **0.723** |
| sg (Gthread-iter/s) | 58.625 | 59.019 | 58.894 | 55.289 |
| sg (relative) | 1.000 | 1.007 | 1.005 | **0.943** |

**Per-geometry staircase fits — `W = 20 = 1.00 × cores` for every one of the
four geometries in both barrier scopes:**

| scope | geom | a (µs) | b (µs) | rms | a/t(1) |
|---|---|---|---|---|---|
| tg | 128 | 1.2087 | 6.1906 | 5.47% | 0.1781 |
| tg | 256 | 2.4697 | 6.6540 | 2.61% | 0.2880 |
| tg | 512 | 5.4637 | 9.1221 | 4.73% | 0.3898 |
| tg | 1024 | 13.5098 | 9.1780 | 4.30% | 0.6457 |
| sg | 128 | 1.0562 | 4.6439 | 6.20% | 0.2103 |
| sg | 256 | 2.1347 | 4.6349 | 9.98% | 0.3820 |
| sg | 512 | 4.3260 | 4.8353 | 12.25% | 0.5810 |
| sg | 1024 | 9.0716 | 6.9295 | 4.90% | 0.6313 |

Three readings.

**The scheduling unit is the core, not the threadgroup-count-times-something.**
Every geometry has the same wave width of 20 = one threadgroup per core, and the
step cost `a` scales almost exactly with threads per threadgroup (1.21 / 2.47 /
5.46 / 13.51 against a 1 / 2 / 4 / 8 thread ratio). A wave is "one threadgroup
on each core", whatever size that threadgroup is.

**Nearly all of the geometry penalty is barrier cost.** Under
`threadgroup_barrier` a 1024-thread threadgroup retains only 72.3% of the
128-thread saturated throughput. Swap the barrier for `simdgroup_barrier` and
the same comparison recovers to 94.3%, and 256t/512t become
indistinguishable from 128t (1.007 / 1.005). A `threadgroup_barrier` must
synchronise 32 simdgroups at 1024 threads versus 4 at 128, and that — not any
occupancy or residency effect — is what the raw spread of 0.310 is measuring.
The residual 5.7% at 1024t is the only part that survives the control.

**Table B verdict.** Raw spread 0.310 lands in the pre-registered
`0.15 < S < 0.40` "partly" row; the `simdgroup_barrier` spread of 0.204 lands in
the same row. But the pre-registered question behind Table B was whether
*smaller threadgroups are intrinsically faster at equal work*, and the
saturated-throughput columns answer that directly: with the barrier confound
removed they collapse to within 5.7% across an 8× range of threadgroup size.
The honest reading is "partly, and almost entirely because of barrier width".

## 5. Phase D — is anything actually co-resident?

Phases B and C measure throughput. Neither can tell a residency limit from a
throughput knee. Phase D measures residency directly: K threadgroups each
increment a counter and then spin until they observe all K arrivals. A
threadgroup that cannot see all arrivals within the spin budget was not
co-resident with the others.

**Positive controls first.** A `fails == 0` reading only means something if the
instrument can report a failure at all.

| control | variant | thr/TG | K | target | fails | wall ms | expected | verdict |
|---|---|---|---|---|---|---|---|---|
| P1 | retire | 128 | 40 | 41 | 40 | 264.97 | fails==40 | PASS |
| P1 | retire | 1024 | 40 | 41 | 40 | 264.97 | fails==40 | PASS |
| P2 | retire | 1024 | 4096 | 4096 | 3936 | 23197.05 | fails>0 | PASS |
| P2 | retire | 128 | 4096 | 4096 | 2496 | 19946.80 | fails>0 | PASS |
| P1 | live | 128 | 40 | 41 | 40 | 265.02 | fails==40 | PASS |
| P1 | live | 1024 | 40 | 41 | 40 | 264.97 | fails==40 | PASS |
| P2 | live | 1024 | 4096 | 4096 | 4050 | 23417.06 | fails>0 | PASS |
| P2 | live | 128 | 4096 | 4096 | 4080 | 24529.36 | fails>0 | PASS |

P1 asks for one more arrival than exists, and every threadgroup times out as it
must. P2 oversubscribes far past any plausible limit and does strand early waves.
Eight of eight controls pass, so the instrument can report both outcomes in both
variants. The spin budget resolves to ≈ 265 ms, which is the yardstick every wall
time below is compared against.

**Residency at the shipped 9,232 B footprint.** Two variants of the rendezvous
kernel differ only in what the non-spinning simdgroups do: `retire` lets them
`return`, freeing 3 of 4 simdgroup slots; `live` parks them at a barrier so all
four stay resident for the whole spin, which is what the shipped kernel does and
what nezuko's instrument does (`research/nezuko_occupancy_probe.swift:418-434`).

| variant | thr/TG | K | TG/core | fails | wall ms | co-resident? |
|---|---|---|---|---|---|---|
| retire | 128 | 240 | 12 | 0 | 32.04 | YES |
| retire | 128 | 480 | 24 | 0 | 131.06 | YES |
| retire | 128 | 481 | 24.05 | 0 | 367.05 | YES |
| retire | 128 | 520 | 26 | 0 | 150.05 | YES |
| retire | 128 | 640 | 32 | 0 | 184.05 | YES |
| retire | 1024 | 40 | 2 | 0 | 0.00 | YES |
| retire | 1024 | 60 | 3 | 0 | 0.00 | YES |
| retire | 1024 | 61 | 3.05 | 0 | 0.00 | YES |
| retire | 1024 | 80 | 4 | 0 | 0.00 | YES |
| **live** | **128** | **480** | **24** | **0** | 136.07 | **YES** |
| **live** | **128** | **481** | **24.05** | **252** | 2848.06 | **no** |
| live | 128 | 240 | 12 | 0 | 32.04 | YES |
| live | 128 | 520 | 26 | 441 | 3096.02 | no |
| live | 128 | 640 | 32 | 564 | 4183.17 | no |
| live | 1024 | 40 | 2 | 0 | 0.00 | YES |
| **live** | **1024** | **60** | **3** | **0** | 0.03 | **YES** |
| **live** | **1024** | **61** | **3.05** | **19** | 334.84 | **no** |
| live | 1024 | 80 | 4 | 57 | 398.26 | no |

**This is the cleanest result in the assignment.** The `live` variant places the
residency cliff between K = 480 and K = 481 at 128 threads, and between K = 60
and K = 61 at 1024 threads. Those are *exactly* nezuko's `maxK` values, obtained
by a completely different method: she binary-searches a pass/fail predicate, I
measure a spin rendezvous at single-threadgroup resolution. Two independent
instruments agreeing to one threadgroup is much stronger evidence than either
alone.

**And the retire/live contrast identifies the resource.** A single ceiling of
**96 simdgroups per core** predicts every row:

| variant | thr/TG | live simdgroups/TG | 96 ÷ that = TG/core | × 20 cores = predicted maxK | measured |
|---|---|---|---|---|---|
| live | 128 | 4 | 24 | **480** | 480 / fails at 481 |
| live | 1024 | 32 | 3 | **60** | 60 / fails at 61 |
| retire | 128 | 1 | 96 | 1920 | ≥ 640 (not probed higher) |
| retire | 1024 | 1 | 96 | 1920 | ≥ 80 (not probed higher) |

The two `live` predictions are exact. The two `retire` rows are consistent but
untight, because retiring three of four simdgroups raises the predicted limit to
1,920 and I only swept to 640 and 80. The point of the retire arm is not its
absolute value, it is that **freeing simdgroup slots moves the limit while
changing no bytes at all** — the retire and live kernels have byte-identical
9,232 B footprints and differ by one `return` statement.

**The byte model is decisively falsified at the shipped footprint.** If
threadgroup memory were the binding resource against the API's
`maxThreadgroupMemoryLength = 32768`, then:

| bytes/TG | naive 32768 ÷ bytes | measured TG/core (128t) | implied B/core |
|---|---|---|---|
| 9,232 (shipped) | 3.55 | **24.00** | 221,568 |
| 9,984 | 3.28 | **24.00** | 239,616 |
| 18,432 | 1.78 | **24.00** | 442,368 |
| 32,768 | 1.00 | 18.60 | 609,485 |

The naive model is wrong by 6.8× at the shipped footprint, and the implied
per-core byte total is not even constant across rows, so no fixed byte pool
explains the data either. `maxThreadgroupMemoryLength` is a limit on what one
threadgroup may *declare*, not a per-core capacity that resident threadgroups
divide up. Residency is flat in bytes from 16 B to 18,432 B and only degrades at
the declaration maximum itself.

**Phase B and Phase D disagree, and Phase D is right about which is which.**
Phase B showed no timing discontinuity at K = 480 → 481 (35.473 → 36.437 µs,
under one wave step), yet Phase D shows a genuine residency cliff at exactly that
point. Both are true: crossing the residency limit costs one extra wave of
serialisation, which is small relative to a curve that has already saturated.
The knee in the Phase B *throughput* curve near 32 warps/core is a throughput
knee, not this residency limit. Conflating the two is the specific error the
primary metric invites.

## 6. Gate C1 — nezuko's own instrument, unmodified, on this host

§1.5 pre-registered that I would not reason about her numbers without first
reproducing them. I compiled `research/nezuko_occupancy_probe.swift` byte for
byte (md5 `b11b1d1d528f0465e043f56e85881cbd`, clean worktree) and ran it here.

Her Phase E, the real sliding-attention body (`K → µs/call`): 1→9.00, 2→9.29,
4→9.11, 8→9.37, 16→9.46, 20→9.18, 24→18.89, 32→18.68, 40→18.59, 48→25.94,
56→26.29, 60→26.63, 64→33.65, 72→34.86, 96→42.65, 120→50.75, 128→58.01,
240→99.05. Step boundaries fall at 20/24, 40/48 and 60/64, so `W ≈ 20` = one
threadgroup per core, with step `a ≈ 8–9.5 µs` and `a/t(1) ≈ 0.89`.

| C1 leg | requirement | measured | verdict |
|---|---|---|---|
| `a/t(1)` | ∈ [0.80, 0.96] | 0.89 | PASS |
| K=20→240 per-core gain | ∈ [1.08, 1.24] | (240/99.05)/(20/9.18) = 1.11217 | PASS |

**C1 passes on both legs.** Her instrument reproduces here, so the disagreements
below are real differences in what is being measured, not host noise.

**Her residency binary search, run here** (`maxK`, and threadgroups per core):

| threads/TG | 16 B | 9,984 B | 18,432 B | 32,768 B |
|---|---|---|---|---|
| 1024 | 60 (3.00) | 60 (3.00) | 60 (3.00) | 60 (3.00) |
| 512 | 120 (6.00) | 120 (6.00) | 120 (6.00) | 120 (6.00) |
| 256 | 240 (12.00) | 240 (12.00) | 240 (12.00) | **135 (6.75)** |
| 128 | 480 (24.00) | 480 (24.00) | 480 (24.00) | **372 (18.60)** |

Every unsaturated row is **exactly 96 simdgroups per core** (60×32/20,
120×16/20, 240×8/20, 480×4/20). And her search cap is
`min(okSlots, max(4*cores*(1024/threads), 64))`
(`nezuko_occupancy_probe.swift:303-305`) = 640/320/160/80 for 128/256/512/1024
threads, with no `+` marker printed, so 480 is a **measured limit, not the
search ceiling**.

**This is the load-bearing result of the whole assignment, and it is hers first.**
At 128 threads per threadgroup, residency is *identical* at 16 B, 9,984 B and
18,432 B. Three orders of magnitude of threadgroup memory buy exactly zero
additional co-residency. The limit only moves at 32,768 B, which is the entire
per-core allocation (`maxThreadgroupMemoryLength = 32768`). Her Phase C repeats
this on the real attention body: 4 planes at 18,448 B gives maxK 60, and 2 planes
at 10,000 B also gives maxK 60.

The binding constraint at the shipped footprint is **simdgroup slots — 96 per
core — not threadgroup-memory bytes.**

My §5 `live` arm reaches the same two `maxK` values — 480 at 128 threads, 60 at
1024 — from a spin rendezvous rather than a binary search, so the ceiling is now
confirmed by two independent instruments rather than asserted by one. What my
instrument adds is the `retire` contrast, which names the resource: the two
kernels are byte-identical and differ by one `return`, and freeing simdgroup
slots moves the limit.

## 7. Ruling

### 7.1 The pre-registered table, executed as written

`G_percore = 4.7533`. That is above 2.00, so **Table A fires the bottom row:
"§0.9.8 survives; threadgroup count is the scheduling unit."**

I am reporting that because I pre-registered it and I will not move a threshold
after seeing the data. But the same run contains three controls that contradict
the conclusion that row asserts, and the reason is that the metric I
pre-registered does not measure what §0.9.8 needs measured. Both statements are
in this report and the advisor should weigh the controls, not the row.

### 7.2 Two pre-registration defects, disclosed rather than reinterpreted

**Defect 1 — gate C2 is wrong as written.** §1.5 required the fitted wave width
`W` to be within ±25% of `3 × cores = 60`. Every fit in this report gives
`W = 20 = 1 × cores`: all four geometries, both barrier scopes, and nezuko's own
Phase E on this host. The "3 × cores" figure came from her Phase B *residency*
result (3 threadgroups per core at 1024 threads), which is a different physical
quantity from the throughput wave width. A wave is one threadgroup per core;
three can be resident while only one advances per step. So C2 as literally
written **fails**, while the check it was trying to express — does the instrument
recover the same wave structure as hers, with a comparable step ratio — **passes**
(`W = 20` in both instruments, `a/t(1) = 0.89` on hers replicated exactly). I am
recording the literal failure and the corrected check side by side. C0 and C1
pass on their literal wording.

**Defect 2 — the primary metric conflates two effects.** `G_percore` compares
K = 480 against K = 1. At K = 1, nineteen of twenty cores are idle and the whole
6.0 µs launch overhead is charged to one threadgroup. Any K ≫ 1 recovers most of
that ratio: by K = 240 the per-threadgroup cost is already within 8% of its
asymptote. So `G_percore = 4.75` is mostly "20 cores beat 1 core, and fixed
overhead amortises", which was never in doubt, and only marginally about
co-residency. The brief's own thresholds show the same trouble from the other
side: as §1.2 recorded before the run, the literal formula yields 22.56 on
nezuko's data against a stated baseline of 1.13.

### 7.3 What the controls actually establish

Three independent results in this report point the same way, and none of them
depends on the defective metric.

1. **Bytes do not buy residency, and the resource is simdgroup slots.** Nezuko's
   unmodified probe, on this host, measures identical residency at 16 B, 9,984 B
   and 18,432 B (§6). My own rendezvous instrument independently lands the cliff
   at her exact `maxK` values, 480 at 128 threads and 60 at 1024, and its
   `retire`/`live` contrast moves that limit with a one-`return` change at a
   byte-identical 9,232 B footprint (§5). A single 96-simdgroups-per-core ceiling
   predicts both `live` rows exactly; the naive byte model is wrong by 6.8× at
   the shipped footprint and no fixed byte pool fits either.
2. **Threadgroup size barely matters once the barrier confound is removed.**
   Saturated throughput collapses to within 5.7% across a 8× range of
   threadgroup size under `simdgroup_barrier`, versus a 27.7% spread under
   `threadgroup_barrier` (§4). The geometry effect is barrier width, not
   occupancy.
3. **The scheduling unit is one threadgroup per core, independent of size.**
   `W = 20` in eight independent fits, with step cost `a` scaling as threads per
   threadgroup (§4).

**Therefore the §0.9.8 currency claim does not survive.** §0.9.8 held that
reducing the gather-GEMM's threadgroup-memory footprint buys co-residency and
that co-residency is worth something. Result 1 falsifies the first half directly
at the footprint in question: the shipped kernel's 9,232 B and a 16 B kernel are
equally resident, so there is nothing to buy by shrinking 9,232 B. Since
`Ws_storage` is 99.91% of that footprint (§2 and the T2 census), even a heroic
reduction would have to remove the weight staging array itself, and it would
still land on the same 96-simdgroup ceiling.

My recommendation is that the byte-reduction axis be closed on the same evidence
that Table A's literal row would keep open, and that the 15.4 ms figure attached
to §0.9.8 be withdrawn rather than re-derived.

### 7.4 The pre-committed context that decides this either way

§1.7 pre-committed to stating this regardless of which row fired. The shipped
dispatch is `grid_dims = (N/64, 256, 1)` threadgroups
(`quantized.cpp:1920-1923`, dispatched as threadgroups at `:1940`):

| projection | K × N | threadgroups | per core, 20-core M4 Pro | per core, 40-core M5 Max |
|---|---|---|---|---|
| gate / up | 2048 × 1024 | 4,096 | 205 | 102 |
| down | 512 × 2048 | 8,192 | 410 | 205 |

Every one of those is an order of magnitude past the 24-per-core point where the
primary metric is evaluated, and well past the K ≈ 240 where the throughput curve
has already saturated. **Whatever the occupancy curve does between 1 and 24
threadgroups per core, production never operates there.** A large `G_percore`
describes the shape of a curve in a region the shipped kernel has already left.

### 7.5 The kernel under test does not run at decode

This is the finding with the largest bearing on how much any of the above is
worth, and it is independent of every measurement in this report.

`fp_gather_qmm_rhs_expert_nax` **is prefill-only**. It cannot be reached at
single-token decode:

- `quantized.cpp:1663` gates the fused path on `M >= 64`, where
  `M = tokens × top_k`. At decode `M = 1 × 8 = 8`.
- The alternate entry at `:2213` is reachable only under `:2209`, which requires
  `M == 1 && B >= 16 && right_sorted_ && B/E >= 4`. At decode `B = 8` and
  `E = 256`, so `B >= 16` fails and `B/E = 0.03`.
- The in-tree comment at `quantized.cpp:1192-1196` says so outright: "PREFILL-ONLY.
  Decode never dispatches this kernel."

Decode instead uses `lagunaRoutedSwiGLUQMVPackedTop8` / `...Packed` / `...QMV`
(`LagunaRuntimeModel.swift:9954`, `:9963`, `:9976`; builder `:6996-7028`;
threadgroup `(64,1,1)` at `:7021-7022`) plus `lagunaRoutedSharedDownResidual`
(`:10023`) and `lagunaRoutedDownReduce` (`:10050`). The `MLX.gatherQuantizedMM`
call at `:9986` is the fallback arm only (`sortedIndices: false`, `:9995`).
Shapes from `LagunaConfig.swift`: `numExperts = 256` (`:30`),
`numExpertsPerTok = 8` (`:31`), `moeIntermediateSize = 512` (`:32`),
`hiddenSize = 2048` (`:17`), `sharedExpertIntermediateSize = 512` (`:33`).
`DARKBLOOM_TRACE_FUSION=1` (`quantized.cpp:1693-1706`) can confirm this
empirically on a host that can select the kernel.

So this entire axis lives inside prefill, which carries **25% of the score
weight** at exponent 0.25. And the counterfactual is worse than the weighting
suggests: if the kernel *did* run at decode, only 8 of 256 experts are non-empty,
so 128 of 4,096 and 256 of 8,192 threadgroups would carry work — **3.125%
occupancy of the launched grid**. A co-residency argument would then be an
argument about mostly-empty threadgroups.

### 7.6 Caveats

- **Generation.** This host is Apple GPU gen 16 and cannot *select* `_nax` at
  runtime. I compile the shipped MSL directly, so footprints, launch limits and
  the scheduler behaviour are real, but nothing here is an `_nax` end-to-end
  timing claim.
- **Core count.** The ranked M5 Max has 40 cores. Wave width scales with cores
  (`W = 1 × cores` here), and `AGENTS.md` warns that threadgroup geometry can
  change sign across core counts. The 96-simdgroups-per-core ceiling is the
  number I would expect to transfer; the absolute `maxK` values are not.
- **`retire` vs `live`.** `live` is the variant that models the shipped kernel and
  hers, and it is the one whose numbers I rely on. `retire` exists only to move
  the limit at constant bytes; its own `maxK` is a lower bound because I swept
  only to 640 and 80, well short of the 1,920 the 96-simdgroup model predicts.
- **P2 stranding counts are not residency bounds.** I earlier read
  `4096 − fails` as a lower bound on simultaneously live threadgroups. That is
  wrong: a timed-out threadgroup retires and lets a successor launch, so the
  count reflects drain dynamics over a 265 ms budget, not peak co-residency. P2
  is a validity control — it establishes that the instrument reports failures
  under oversubscription — and nothing more should be extracted from it. The
  residency numbers in this report all come from the single-threadgroup-
  resolution sweep, not from P2.
- **No ranked receipt.** Per the assignment I dispatched nothing. Everything here
  is local instrumentation on a non-ranked host; the M5 remains authoritative.

### 7.7 Suggested follow-ups (not implemented)

- The 96-simdgroups-per-core ceiling is the real occupancy currency on this host,
  and it is a *register/simdgroup-slot* budget rather than a byte budget. If any
  occupancy axis is worth reopening, it is register pressure per simdgroup in the
  gather-GEMM, not threadgroup bytes. That is a different experiment and I have
  not run it.
- A per-threadgroup arrival-timestamp buffer would show wave structure directly
  instead of inferring it from a pass/fail rendezvous. That would also settle the
  drain dynamics under oversubscription that P2 cannot speak to.
- The `retire` arm's true `maxK` is unmeasured. Sweeping it to 1,920 at 128
  threads would test the 96-simdgroup model where it makes its boldest
  prediction, rather than only where it is already confirmed.
- `research/CURRENT_RESEARCH_STATE.md:544-547` and
  `research/GATHER_GEMM_REGIME_DESIGN.md:239-241` misread `tg_expert_groups` as
  an expert-partition count when it is grid.y = 256; the corrections are itemised
  at the end of the T2 census. I did not edit those files.

## 8. Base advance, the injection hazard, and the standing pre-measurement check

Added after the advisor notice
[`5196932438`](https://github.com/morganmcg1/mlxfast-challenge_senpai/pull/57#issuecomment-5196932438)
(`feedback_id base-advance-clearance-f722c2d7-and-inject-hazard-2026-08-05T2030Z`).
Still revision `r1`; the brief is unchanged and T4 remains defunded.

### 8.1 Base accepted and rebased

The assignment marker recorded base `5178d452`. The advisor branch has since
moved to `720c13ff` (#48 merge) and then to `f722c2d7` (revert the
dispatch-injection defaults). The advisor cleared `f722c2d7` explicitly, so I
rebased onto it rather than only recording an accepted advance. The rebase was
clean, all nine commits replayed including the empty assignment marker commit,
and the worktree is clean.

I recomputed the submitted-surface intersection by code rather than by recall,
per the advisor's own new rule. Parsing the 97 `editablePaths` entries out of
`benchmark.json` and matching each changed file (directory entries by prefix,
file entries by exact match):

```
editablePaths entries: 97
changed files: 4
  research/tanjiro-band-ratio-reconciliation.md       -> not submitted
  research/tanjiro-gathergemm-d2-census.md            -> not submitted
  research/tanjiro-pr-gathergemm-coresidency.md       -> not submitted
  research/tanjiro_gathergemm_occupancy_probe.swift   -> not submitted
INTERSECTION: NONE
```

Rebasing also made the T3 §6 citations resolve in my own tree: fern's receipt
file `research/maple-fern-pr48-fused-norm-qkv-gate.md` arrived with the #48
merge, and `:951-953` and `:981-983` contain exactly the `officialScore` and
session-baseline lines that section quotes. Before the rebase those line
references pointed at a file this branch did not contain.

### 8.2 Standing pre-measurement check, run on my own head

```
$ grep -n -A1 'DARKBLOOM_INJECT_DECODE_EMPTY"\|DARKBLOOM_INJECT_EMPTY_TG"' \
    Sources/MLXFastModel/LagunaRuntimeModel.swift
11046:    "DARKBLOOM_INJECT_DECODE_EMPTY", 0)
11058:    "DARKBLOOM_INJECT_EMPTY_TG", 160)
```

`0` and `160` — the check passes at my head. For the record it did *not* pass
before the rebase: at `afd8902` the same grep returned `100` and `8`, i.e. my
branch was carrying the on-by-default instrument.

### 8.3 Why no number in this report is affected

The hazard is a runtime instrument inside the Laguna forward pass. Every number
in this report comes from a standalone Swift binary
(`research/tanjiro_gathergemm_occupancy_probe.swift`, built with `xcrun swiftc
-O` into `/tmp/tjocc`) that links Metal directly, compiles its own synthetic MSL
at run time, and never constructs a Laguna model or executes
`LagunaRuntimeModel.swift`. Phase A is the only part that touches real kernel
sources at all, and it does so by shelling out to
`research/nax_msl_compile_check.sh` to *compile* the `_nax` pipelines and read
back their static threadgroup-memory length — a compile-time property, not a
timed forward pass. The gate C1 replication in §6 is nezuko's probe, which is
standalone on the same terms.

So the exposure is real at the source level and nil at the evidence level. I
have no `--local-iterate` or `--local-submit` timing from this round to mark
dead, because I took none: this assignment is receipt-free and I dispatched
nothing.

### 8.4 One consequence for §7.7

The advisor's notice closes the dispatch-count-reduction axis programme-wide and
replaces it with a barrier-count currency, on the strength of fern's #48 result
(Reading A refuted, Reading B confirmed). Nothing in §7 argues for fewer
dispatches, so no claim here is withdrawn. It does sharpen the §7.7 follow-up
list: of the four items, the register/simdgroup-slot pressure item is the only
one that proposes a *mechanism*, and it is a per-simdgroup resource argument, not
a dispatch-count argument. The other three are instrument improvements. If any of
them is ever funded, the thing to measure alongside it is barriers.

