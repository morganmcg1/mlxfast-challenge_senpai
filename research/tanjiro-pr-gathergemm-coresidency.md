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
observed.** That commit is the audit trail: if the ruling in §5 disagrees with
what §1.6 says the ruling must be, the disagreement is visible in git history.
Sections 2 onward were written after the probe ran.

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

*(filled in after the run)*

## 3. Phase B — 128-thread threadgroup-count sweep

*(filled in after the run)*

## 4. Phase C — constant per-thread work geometry sweep

*(filled in after the run)*

## 5. Ruling

*(filled in after the run)*
