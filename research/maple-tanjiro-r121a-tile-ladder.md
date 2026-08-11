# r121-a — Ranked `_nax` prefill tile ladder (pre-registration ledger)

Student: `maple-tanjiro`. PR #716, revision `r121-a-rev1`.
Assignment base `cd047c00fae93176c93600966d7c542cc836cdc8` (`codex/mlxfast-maple-20260804-advisor`).
Campaign submission base `BASE_SHA=1bc1c8954147c9e322aad1f3b80bd9fa3c0888d7`.

This is a **build-and-pre-register** deliverable. No local wall timing of `_nax`
code was performed and no official draw was requested; the advisor owns the
limit-1 channel. Every number below is a *prediction* with its arithmetic
exposed so a single ranked draw can falsify it.

---

## 1. §4.1 reachability verdict: **PROVEN-JIT**

**Arbitrary `(bm, bn, bk, wm, wn)` tuples are reachable on the ranked M5.** The
AOT `instantiate_*` lists in the `_nax` `.metal` files bound nothing at runtime.

Chain of evidence (all paths relative to repo root):

1. `Vendor/mlx-swift/Package.swift:284` unconditionally excludes
   `mlx/mlx/backend/metal/nojit_kernels.cpp` from the Cmlx target.
   `jit_kernels.cpp` appears only in `noMetalCmlxExcludes` (`Package.swift:7`,
   appended at `:131` and `:175`, Linux-only), so on Apple **`jit_kernels.cpp`
   is the compiled kernel-acquisition path**.
2. `MLX_METAL_JIT` is a CMake-only option (`Source/Cmlx/mlx/CMakeLists.txt:44`).
   It is never passed as a SwiftPM define; the Apple `cxxSettings`
   (`Package.swift:217-223`) define only `_METAL_`, `MLX_USE_ACCELERATE`,
   `METAL_PATH="default.metallib"` and `SWIFTPM_BUNDLE`. There is no
   `MLX_METAL_NO_NAX`, so `is_nax_available()` (`backend/metal/device.cpp:913`)
   is live.
3. Build-artifact confirmation on this host:
   `.build-worker/arm64-apple-macosx/release/Cmlx.build/mlx/mlx/backend/metal/jit_kernels.cpp.o`
   exists and there is **no** `nojit_kernels*.o`.
4. The three JIT entry points are fully parameterised by the tile tuple —
   nothing is hard-coded or looked up against the AOT list:
   `get_steel_gemm_fused_nax_kernel` (`jit_kernels.cpp:977`, source concatenation
   `:991-1005`, template name `"gemm"`), `get_steel_gemm_gather_nax_kernel`
   (`:1011`, template `"gather_mm_rhs_nax"` / `"gather_mm_nax"`),
   `get_steel_gemm_splitk_nax_kernel` (`:1049`, template `"gemm_splitk_nax"`).
   Substitution is `get_template_definition` (`jit/includes.h`-adjacent
   `kernels.h:402-421`; fold at `:415`, format at `:418-420`).
5. `Device::get_library` (`device.cpp:770-787`) compiles the generated source
   with `newLibrary` (`device.cpp:622-635`). There is **no metallib fallback**:
   if the tuple did not compile, the dispatch would throw, not silently
   degrade. Libraries are cached per `base_name` per process.
6. Independent corroboration: `gather_mm_nax` (the non-`rhs` form) has **no**
   AOT instantiation anywhere, yet `matmul.cpp` can request it. Only JIT can
   satisfy that.

Consequences that shape this ladder:

* Editing the `instantiate_*` lists in
  `kernels/steel/gemm/kernels/steel_gemm_*_nax.metal` has **zero** effect on
  ranked timing. Do not spend a draw on it.
* The submission surface for a geometry change is the **host tile-selection
  code in `matmul.cpp`** — one file, a handful of lines, no metallib rebuild
  needed for the ranked path.
* Each *new* tuple costs one runtime Metal compile on first use, inside the
  process. That is a TTFT consideration if a change multiplies the number of
  distinct tuples. Every arm below keeps the tuple count constant or reduces
  it (each arm re-partitions existing shapes among tuples; arms 1 and 4 add one
  new tuple each and none removes a needed one).
* For reference only, the AOT lists are
  `steel_gemm_fused_nax.metal:24-29` = (64,64,256,2,2), (64,128,64,2,4),
  (64,128,256,2,4), (128,128,64,4,4), (128,128,256,4,4), (128,128,512,4,4);
  `steel_gemm_splitk_nax.metal:24-25` = (64,64,256,2,2), (128,128,512,4,4);
  `steel_gemm_gather_nax.metal:31-33` = (16,128,128,1,4), (32,128,128,1,4),
  (64,128,128,2,4).

## 2. The binding constraint the advisor's sketch did not have: tile legality

`_nax` tiles are **not** freely choosable. Derivation:

* `SM = BM / WM`, `SN = BN / WN`
  (`kernels/steel/gemm/steel_gemm_fused_nax.h:150-151`;
  `steel_gemm_splitk_nax.h:75-76`). `SK = 32` is fixed
  (`steel_gemm_fused_nax.h:152`).
* `TM = SM / 16`, `TN = SN / 16` (`kernels/steel/gemm/gemm_nax.h:35-36`); the
  MMA fragment is 16x16 (`kernels/steel/nax.h:28-29`).
* `tile_matmad_nax` (`nax.h:972-1031`) contains exactly two branches:
  `if constexpr (TN == 1 && TM % 2 == 0)` (`nax.h:994`) and
  `else if constexpr (TN % 2 == 0)` (`nax.h:1011`). **There is no `else`.**

> **Legality rule.** `SM % 16 == 0` and `SN % 16 == 0`, and
> (`TN % 2 == 0`) **or** (`TN == 1` and `TM % 2 == 0`).
> A tuple that violates this compiles cleanly and produces an **empty**
> multiply-accumulate — a silent wrong-answer hazard, not a build error.

So `SM = SN = 16` (TM = TN = 1) is illegal. `(SM,SN)` in
{(16,32), (32,16), (32,32), (64,32), (32,64)} are legal. Every arm below is
checked against this rule in the table, and arms 1/2/4 were additionally put
through a standalone Metal compile of the exact tuple (§7.3).

That compile **confirmed the rule empirically, including its failure mode**: the
illegal `(16,16)` tuple compiled with exit 0 and zero diagnostics, yet emitted
no MMA instruction at all, while all five shipped tuples emitted 48 each
(§7.3). The silent-empty hazard is real, and this rule is the only thing
standing between a tile edit and a silently wrong prefill.

The kernel is a register-tile design: `NAXTile` loads straight from device
memory, so threadgroup memory is ~0 and residency is bound by the **96
simdgroup slots per core**, not by shared memory. Two invariants follow:

* `simdgroups = (M/SM) * (N/SN) * parts`, **independent of `wm`,`wn`** once
  `SM`,`SN` are fixed. `wm*wn` only decides how those simdgroups are *packaged*
  into threadgroups (`threads/TG = wm*wn*32`).
* A/B load traffic `= M*N*K*2*(1/SM + 1/SN)` bytes. Halving `SM` buys 2x
  simdgroups at 1.5x traffic; doubling `SM` cuts traffic to 0.75x for half the
  simdgroups.

## 3. Baseline census the ladder is priced against

Ranked M5 Max: **40 cores x 96 simdgroup slots = 3840 concurrent simdgroups**.
Rows below are the validated occupancy census
(`research/artifacts/tanjiro-r104c/steel_census_237.json`, 474 rows = 237
dispatches x 2 host routes; the M5 route is the `_nax` one). Measured
`steel_gemm_bf16` total on the ranked M5 = **37.93 ms** of a
**S = 96.18 ms** prefill window (38.7% of S; routed gather-GEMM is another
44.2%).

| family | n | M x N x K | path | bm/bn/bk wm/wn | SM | SN | parts | TGs | TG/core | simdgroups | % of 3840 | GFLOP |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| wq SW+L0 | 31 | 512x8192x2048 | regular | 64/128/256 2/4 | 32 | 32 | – | 512 | 12.8 | 4096 | 106.7% | 532.58 |
| wo SW+L0 | 30 | 512x2048x8192 | splitk | 64/64/512 2/2 | 32 | 32 | 2 | 512 | 12.8 | 2048 | 53.3% | 515.40 |
| **wk/wv** | **78** | 512x1024x2048 | regular | 64/128/256 2/4 | 32 | 32 | – | **64** | **1.6** | **512** | **13.3%** | 167.50 |
| wq full | 10 | 512x6144x2048 | regular | 64/128/256 2/4 | 32 | 32 | – | 384 | 9.6 | 3072 | 80.0% | 128.85 |
| wo full | 10 | 512x2048x6144 | splitk | 64/64/512 2/2 | 32 | 32 | 2 | 512 | 12.8 | 2048 | 53.3% | 128.85 |
| **router** | **38** | 512x256x2048 | splitk | 64/64/256 2/2 | 32 | 32 | 2 | **64** | **1.6** | **256** | **6.7%** | 20.40 |
| KV bank | 1 | 512x2048x2048 | regular | 64/128/256 2/4 | 32 | 32 | – | 128 | 3.2 | 1024 | 26.7% | 4.29 |
| **g_proj SW** | **29** | 512x64x2048 | splitk | 64/64/256 2/2 | 32 | 32 | 2 | **16** | **0.4** | **64** | **1.7%** | 3.89 |
| **g_proj full** | **10** | 512x48x2048 | splitk | 64/64/256 2/2 | 32 | 32 | 2 | **16** | **0.4** | **64** | **1.7%** | 1.01 |

The starkest line: **g_proj launches 16 threadgroups on a 40-core GPU, so 24
cores receive no work at all**, 39 times per prefill. `wk/wv` and `router` fill
1.6 TGs/core, i.e. they run the machine at 13% and 7%.

### 3.1 One-parameter wave model (fit, not assumed)

Define the threadgroup capacity `C = floor(3840 / (wm*wn))` and effective
utilisation `U = TGs / (C * ceil(TGs / C))` (a partly-filled final wave is
charged at its real fill). Model `t_family = GFLOP / (P * U)`.

Summing the nine rows gives `4239.8 / P` GFLOP-equivalents. Setting that equal
to the measured 37.93 ms yields

> **P = 111.8 TFLOP/s** effective bf16 MXU throughput for the ranked M5 Max.

That is a plausible 40-core NAX number and it is the *only* free parameter, so
every prediction below is a genuine out-of-sample forecast of the same model.
(The simpler uncapped variant `U = min(1, simdgroups/3840)` fits P = 100.4
TFLOP/s and moves the arm predictions by <10%.)

Score conversion: `dScore/dPrefill = 0.3781 %/ms` (total; the conservative
partial figure is `0.2592 %/ms`), from prefill elasticity 0.365 on
S = 96.18 ms. Candidate prefill-leg cv = **0.0953%** (n = 12), so a single
paired draw resolves ~0.25% of prefill (~0.26 ms) at 95%. Adjudicate on
`officialMetrics.candidate.prefill_seconds_per_token`, never `officialScore`
(cv 0.5048%). Crown `cc6ddc1` = 2.61650354 vs this class ~2.5669, i.e. the
ladder needs about **+1.9% score = -5.0 ms prefill** to take the crown.

## 4. Branch separability in `matmul.cpp` (why one line hits one family)

* `steel_matmul_regular_axpby_nax` starts `matmul.cpp:186`; tile defaults
  `bm=128,bn=128,bk=512,wm=4,wn=4` (`:211-212`);
  `char devc = d.get_architecture().back();` (`:216`); the ranked branch
  `if (devc=='s'||devc=='c'||devc=='d') { bk = (K>=8192 && K>(M+N)) ? 64 : 256;
  bm=64; wm=2; }` (`:217-222`) covers **120** dispatches (wq 41, wk/wv 78,
  KV bank 1). Within it, `N <= 1024` selects exactly the 78 wk/wv and
  `N >= 4096` selects exactly the 41 wq.
* `steel_gemm_splitk_axpby_nax` starts `matmul.cpp:645`; defaults
  `128/128/512 4/4`, `split_k_partition_size = 4096` (`:664-666`).
  **Branch A** `if ((M+N)/2 < 512 || K <= 4096) { bm=bn=64; bk=256; wm=wn=2; }`
  (`:668-672`) selects exactly router 38 + g_proj 39 = **77** dispatches.
  **Branch B** `if (darkbloom_steel_prefill_tile() && (M+N)/2 >= 512 && K > 4096)
  { bm=bn=64; wm=wn=2; }` (`:673-676`) selects exactly the **40** wo dispatches.
  `split_k_partition_size` ladder at `:677-683`.
* `darkbloom_steel_prefill_tile()` is defined at `matmul.cpp:82-88`, defaults
  **ON**, and has a **single call site** (`:674`).
* `DARKBLOOM_STEEL_REGULAR_SKINNY_TILE` from PR #293 is **not** in this tree.

**Decode inertness is structural, not statistical.** `matmul.cpp:1252` is
`if (std::min(M, N) == 1) return gemv(...)`, evaluated *before* any `_nax`
steel dispatch. Decode steps have M = 1, so **none of the functions touched by
arms 1-4 is entered during a one-token decode step**. Predicted
`Delta decode_seconds_per_token = 0` exactly for arms 1-4, with the single
caveat that if the harness counts the 512-token teacher-forcing seed inside the
decode window, the seed is a prefill and contributes the same-signed prefill
delta scaled by roughly 96.18 ms / 630 ms = 0.15 — never adverse for an arm
that helps prefill.

## 5. Pre-registered arm table

`Delta_ideal` is the wave model at P = 111.8 TFLOP/s. `Delta_real` discounts
for the per-dispatch launch/latency floor (arms whose model time per dispatch
falls near ~30 us cannot realise the full halving) and for the 1.5x load
traffic that `SM: 32 -> 16` implies. Score deltas use 0.3781 %/ms.

| # | patch / commit | one-line diff | reachability | dispatches touched (M x N x K) | tuple after | SM,SN -> TM,TN legal? | TGs before -> after | TG/core (40 cores) | simdgroups (% of 3840) | Delta_ideal prefill | Delta_real prefill | Delta score | Delta decode |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **1** | `arm1-regular-skinny-sm16.patch` / `9791d02b` | in the `devc` branch add `if (N <= 1024) { bm = 32; }` | PROVEN-JIT, `matmul.cpp:957` -> `:186` -> `jit_kernels.cpp:977` | 78 wk/wv, 512x1024x2048 | 32/128/256 2/4 | 16,32 -> 1,2 **legal** (`TN%2==0`) | 64 -> 128 | 1.6 -> 3.2 | 512 -> 1024 (13.3% -> 26.7%) | **-5.62 ms** (-5.84%) | -2.8 to -5.6 ms | **+1.06% to +2.13%** | 0 (`:1252`) |
| **2** | `arm2-splitk-shallow-sm16.patch` / `02a3ee63` | splitk branch A `bm = bn = 64;` -> `bm = 32; bn = 64;` | PROVEN-JIT, `matmul.cpp:922` -> `:645` -> `jit_kernels.cpp:1049` | 38 router 512x256x2048 + 39 g_proj 512x{64,48}x2048 | 32/64/256 2/2 | 16,32 -> 1,2 **legal** | router 64 -> 128; g_proj 16 -> 32 | 1.6 -> 3.2; 0.4 -> 0.8 | router 256 -> 512; g_proj 64 -> 128 | **-2.68 ms** (-2.79%) | -0.8 to -2.7 ms | **+0.30% to +1.01%** | 0 (`:1252`) |
| **3** | `arm3-splitk-depth-512.patch` / `38c83830` | `K <= 2048` -> `split_k_partition_size = 512` (was 1024) | PROVEN-JIT, same as arm 2 | same 77 as arm 2 | 64/64/256 2/2, parts 2 -> 4 | 32,32 -> 2,2 **legal** (unchanged) | router 64 -> 128; g_proj 16 -> 32 | 1.6 -> 3.2; 0.4 -> 0.8 | router 256 -> 512; g_proj 64 -> 128 | **-2.68 ms** (-2.79%) | -0.8 to -2.7 ms | **+0.30% to +1.01%** | 0 (`:1252`) |
| **4** | `arm4-regular-wide-sm64.patch` / `6b2a0832` | in the `devc` branch add `if (N >= 4096) { bm = 128; }` | PROVEN-JIT, same as arm 1 | 31 wq SW 512x8192x2048 + 10 wq full 512x6144x2048 | 128/128/256 2/4 | 64,32 -> 4,2 **legal** | wq SW 512 -> 256; wq full 384 -> 192 | 12.8 -> 6.4; 9.6 -> 4.8 | wq SW 4096 -> 2048; wq full 3072 -> 1536 | **+1.44 ms** (+1.50%) | 0 to +2.9 ms | **-0.55%** (predicted regression) | 0 (`:1252`) |
| **5** | `arm5-prefill-tile-default-off.patch` / `d26ae5b9` | flip `darkbloom_steel_prefill_tile()` default to OFF | PROVEN-JIT, `matmul.cpp:674` | 40 wo, 512x2048x{8192,6144} | 128/128/512 4/4 | 32,32 -> 2,2 **legal** (unchanged) | 512 -> 128 (16-simdgroup TGs) | 12.8 -> 3.2 | 2048 -> 2048 (53.3%, **unchanged**) | **0.00 ms** | -0.2 to +0.2 ms | 0 +/- 0.10% | 0 (`:1252`) |
| **6** | stack 1+2+3 | all three, disjoint edits | – | 155 starved dispatches | – | – | – | – | router 256 -> 1024; g_proj 64 -> 256; wk/wv 512 -> 1024 | **-9.64 ms** (-10.0%) | -3.9 to -9.6 ms | **+1.47% to +3.64%** | 0 (`:1252`) |

Gate outcomes for every arm are in §7: build in §7.1, editable budget in §7.2,
Metal tuple legality in §7.3, upstream equivalence versus the unchanged base in
§7.4. All five arms passed all four; none was timed (§7.6).

### 5.1 Arithmetic behind each prediction

* **Arm 1.** wk/wv baseline `t = 167.50/(P*0.1333) = 1256/P`. After: TGs 128,
  `C = floor(3840/8) = 480`, `U = 128/480 = 0.2667`, `t = 628/P`.
  `Delta = -628/111.8 = -5.62 ms`. Traffic per dispatch rises from
  `512*2048*(1024/32)*2 + 1024*2048*(512/32)*2 = 134 MB` to `201 MB` (+50%),
  but the whole working set is `A 2.1 MB + B 4.2 MB = 6.3 MB`, cache-resident,
  so the traffic term is not expected to eat the occupancy win. Accumulator
  registers per thread *fall* from 32 to 16 floats (TM*TN 4 -> 2 fragments).
* **Arm 2.** router `20.40/(P*0.0667) = 305.8/P -> 152.9/P`; g_proj
  `4.90/(P*0.0167) = 293.4/P -> 146.7/P`. `Delta = -299.6/111.8 = -2.68 ms`.
  Model time per g_proj dispatch is `293.4/111.8/39 = 67 us` today; halving it
  approaches the launch floor, hence the wide realistic band.
* **Arm 3.** For K = 2048, `bk = 256` and `sps: 1024 -> 512` gives
  `bk_iters_per_partition = 512/256 = 2` (integral) and
  `parts = ceil(2048/512) = 4`. `align_K = (2048 % 256) == 0` is unchanged.
  Occupancy therefore doubles exactly as in arm 2, and the two arms **compose
  multiplicatively** (arms 2+3 together: router `U = 0.267`, g_proj
  `U = 0.0667`, `Delta = -4.02 ms`). Extra `C_split` float32 scratch: router
  1.05 -> 2.10 MB, g_proj 0.26 -> 0.52 MB; the accumulate pass reads 4 rather
  than 2 partitions. No extra kernel launch.
* **Arm 4.** wq SW is *already* two waves: `TGs 512 > C 480`, so
  `U = 256/480 = 0.533`; with `bm = 128` it becomes `TGs 256 <= 480`,
  `U = 256/480 = 0.533` — **exactly unchanged**. wq full goes
  `U = 384/480 = 0.8 -> 192/480 = 0.4`, i.e. `161/P -> 322/P`, a
  `+1.44 ms` regression. The compensating mechanism is a 25% cut in B-load
  traffic (1.07 -> 0.805 GB per wq SW dispatch) and this arm is retained
  precisely because the two mechanisms disagree in sign: it measures the
  **MXU saturation knee**. If arm 4 comes back neutral or positive, occupancy
  is *not* proportional down to 40% and the arm 1-3 predictions are upper
  bounds; if it regresses near +1.4 ms the wave model is validated end to end.
  Cost: accumulator registers per thread double (32 -> 64 floats), a spill risk
  the model does not carry.
* **Arm 5.** ON gives `64/64/512 2/2` (`SM=SN=32`, `C = 960`, wo TGs 512,
  `U = 0.533`); OFF gives `128/128/512 4/4` (`SM=SN=32`, `C = 240`, wo TGs 128,
  `U = 0.533`). Identical `SM`,`SN`, identical simdgroup count, identical
  traffic — only threadgroup packaging differs (512 four-simdgroup TGs vs 128
  sixteen-simdgroup TGs). The model returns exactly 0. **This arm needs no
  build to time**: `DARKBLOOM_STEEL_PREFILL_TILE=0` on the candidate side of a
  paired local draw measures the same thing (an env override is of course not
  rankable, so the patch exists for the case where it wins).
* **Arm 6.** Sum of the disjoint arm-1 and arm-2+3 deltas; the three edits touch
  three different code sites and three disjoint dispatch sets.

### 5.2 What is *not* on the ladder, and why

* **`wo` SM 32 -> 16** (`bm = 32` in splitk branch B). It would take 2048 ->
  4096 simdgroups, crossing the 3840-slot line into a second, almost empty wave
  (`U = 0.533 -> 512/960` vs `1024`: `TGs 1024 > C 960` so
  `U = 512/960 = 0.533`, no gain) *and* pay 1.5x traffic on a 33.5 MB
  DRAM-resident weight bank. Predicted regression, zero upside.
* **Fixing wq wave quantisation by geometry.** wq SW needs
  `simdgroups <= 3840` with `(M/SM)(N/SN) = 4096` at `SM = SN = 32`. The only
  way down is a larger `SM` or `SN`, and the next legal step halves the count to
  2048 (there is no legal `SN = 48`: `TN = 3` is odd and fails the legality
  rule). **wq wave quantisation is unfixable by tile geometry** — consistent
  with the advisor's "wave-quant killed" note in `f8cb5c5b`.
* **Editing the `instantiate_*` AOT lists.** Provably inert on the ranked path
  (§1).

## 6. Correctness and inertness gates

### 6.1 Provable gen-16 inertness

All five arms live inside code that is unreachable on this M4 Pro host
(Apple GPU generation 16, `applegpu_g16s`):

* Arms 1 and 4 change `steel_matmul_regular_axpby_nax`, called only from
  `matmul.cpp:957` under `if (use_nax)`.
* Arms 2 and 3 change `steel_gemm_splitk_axpby_nax`, called only from
  `matmul.cpp:922` under `if (use_nax && ...)`.
* Arm 5 changes `darkbloom_steel_prefill_tile()`, whose single call site
  `matmul.cpp:674` is inside `steel_gemm_splitk_axpby_nax`.
* `use_nax = metal::is_nax_available() && ...` (`matmul.cpp:892-894`), and
  `is_nax_available()` (`device.cpp:913`) is false on generation 16. The M4
  route uses the non-`_nax` steel path with `64/64/16 2/2` or `32/32/16 2/2`
  tiles, which none of the arms touches.

So the *expected* local result is a bit-exact no-op, and a local numerical
change would be a red flag about the diff, not evidence about the M5.

### 6.2 Empirical check (union of all five diffs)

`research/run_upstream_equivalence.sh` on the union, and again on the reverted
base-identical head as a control. Results in §7.4.
`MLXFAST_LOCAL_ALLOW_GOLDEN_DRIFT=1` was **not** used anywhere.

The golden-hash leg could not run here (§7.5): the fixture
`correctness_golden.json` is absent from this checkout, and `golden_sha256` is
in any case a hash of that fixture file rather than of computed output, so a
source edit cannot move it.

Known pre-existing base property on gen-16, for interpretation only: the
prefill teacher-forced case reports `maximumAbsoluteLogitError = 0.125`,
mean `0.0119336`, and exits 1 on this host at the *unchanged* base
(`research/CRS.md:8168-8173`, `:3576-3577`). If that reappears it must be
compared against the unchanged base, not waived.

### 6.3 Metal tuple legality compile

The `_nax` JIT strings are never compiled on this host, so `swift build` cannot
validate a new tuple. Substitute check: compile the exact tuples standalone with
`xcrun metal` against the same headers, and confirm the generated function is
non-empty (the empty-MMA hazard of §2 produces a much smaller function body).
Results in §7.3.

## 7. Gate results

All gates below were run on this host (M4 Pro, Apple GPU generation 16,
`applegpu_g16s`, 48 GB, low-memory startup profile). Every arm commit is a
single-arm tree branched off the assignment head `898522ab`.

### 7.1 Per-arm release build

`swift build -c release --force-resolved-versions`, then
`git checkout -- Package.resolved`, once per arm, from a clean tree
(driver `/tmp/build_arms.sh`, raw results `/tmp/r121a-build-results.txt`).

| arm | commit | rc | wall secs | compiler error lines |
|---|---|---|---|---|
| base (control) | `898522ab` | 0 | 66 | 0 |
| 1 regular skinny SM16 | `9791d02b` | 0 | 33 | 0 |
| 2 splitk shallow SM16 | `02a3ee63` | 0 | 34 | 0 |
| 3 splitk depth 512 | `38c83830` | 0 | 33 | 0 |
| 4 regular wide SM64 | `6b2a0832` | 0 | 34 | 0 |
| 5 prefill tile default off | `d26ae5b9` | 0 | 33 | 0 |
| union of 1-5 | `780b0579` | 0 | - | 0 |

`worktree_after` was clean for every arm, so no build mutated
`Package.resolved` or left artifacts staged.

Arms 1 and 4 both edit the same `devc` block, so the union is **not** a naive
patch stack: applying arm 4 on top of arm 1 fails with `patch does not apply`.
The union commit `780b0579` merges them by hand so that both guards sit inside
the block (`if (N <= 1024) { bm = 32; }` and `if (N >= 4096) { bm = 128; }`).
Union diff versus base: `1 file changed, 9 insertions(+), 2 deletions(-)`.
This matters for sequencing: **arms 1 and 4 cannot be stacked, only chosen
between**, and the §5 arm-6 stack is 1+2+3 precisely because 4 collides.

### 7.2 Editable budget, on the union (worst case)

```
editable budget OK: current=2686722/3000000 bytes headroom=313278
                    growth=-297127/262144 files=142 (base=142)
```

Growth is negative because the arms delete more than they add, so no arm can
approach the 262,144-byte per-review growth cap or the 3,000,000-byte total.
File count is unchanged at 142, so no arm adds a submitted path.

### 7.3 Metal tuple legality (the §2 empty-MMA trap)

`_nax` is never compiled on gen-16, so `swift build` cannot validate a tuple.
Substitute check: each tuple compiled standalone in `/tmp/tuplecheck` with
`xcrun metal -x metal -Wall -Wextra -fno-fast-math` against the repo headers,
using the deployment target recorded in the real worker recipe
(`.build-worker/.../mlx-metallib.dir/build.make:736`), then the isolated `.air`
sized and disassembled with `metal-objdump`.

| tuple (bm,bn,bk,wm,wn) | SM/SN -> TM/TN | compiles | isolated `.air` | MMA calls | verdict |
|---|---|---|---|---|---|
| fused 64,128,256,2,4 (base) | 32/32 -> 2/2 | yes | 229,008 B | 48 | **LEGAL** |
| fused 32,128,256,2,4 (**arm 1**) | 16/32 -> 1/2 | yes | 206,112 B | 48 | **LEGAL** |
| fused 128,128,256,2,4 (**arm 4**) | 64/32 -> 4/2 | yes | 266,784 B | 48 | **LEGAL** |
| splitk 64,64,256,2,2 (base) | 32/32 -> 2/2 | yes | 171,760 B | 48 | **LEGAL** |
| splitk 32,64,256,2,2 (**arm 2**) | 16/32 -> 1/2 | yes | 154,624 B | 48 | **LEGAL** |
| *negative control* fused 32,64,256,2,4 | 16/16 -> 1/1 | **yes, 0 warnings** | **78,112 B** | **0** | **EMPTY** |

The negative control is what makes this discriminating rather than suggestive:
an illegal `(TM=1, TN=1)` tuple compiles with exit 0 and no diagnostic, yet its
`gemm_loop` instantiation disappears from the AIR entirely and the file falls to
2.6x smaller than the smallest legal case. Against that calibrated floor all
five shipped tuples sit in a 154-267 KB band, each carrying a live
`mlx::steel::gemm_loop` whose mangled name literally encodes the expected
`SM`/`SN` (`Ls16ELs32E`, `Ls64ELs32E`, ...) and whose body contains the
`matmul2d` run call. Size and symbol evidence agree independently.

Two corrections to the §2 derivation fall out of this and are already folded
into the rule above:

1. `gemm_nax.h:35-36` uses `TN = SN/16`, **not** `SN/32`. That is why `SM = 16`
   tuples are legal at all.
2. The trap is therefore triggered by **odd `TN > 1`, or `TN == 1` with odd
   `TM`** - not by a small `BM`. The multiply also lives out-of-line in
   `gemm_loop`, not in the kernel entry point, so per-tuple attribution must
   follow that symbol; counting MMA in the entry function alone reports 0 for
   *every* tuple, legal or not.

Arms 3 and 5 change no tuple (both stay at `SM = SN = 32`), so they inherit the
base rows.

### 7.4 Upstream equivalence, union versus unchanged base

`research/run_upstream_equivalence.sh` (bare test filter, debug-metallib
repair, refuses to call a zero-test invocation a pass). Run twice: once on the
union tree `780b0579`, once on the reverted, base-identical head `9fb2048b`.

| | union `780b0579` | base-identical `9fb2048b` |
|---|---|---|
| tests executed | 1 (non-zero, gate honoured) | 1 |
| `EQUIVALENCE_EXACT_STEPS` | 8 | 8 |
| every `runtimeToken == upstreamToken` | yes, 9/9 steps | yes, 9/9 steps |
| prefill `maximumAbsoluteLogitError` | 0.125 | 0.125 |
| prefill `meanAbsoluteLogitError` | 0.011933609 | 0.011933609 |
| all 8 decode steps | 0.0 / 0.0 exact | 0.0 / 0.0 exact |
| `EQUIVALENCE_EXIT` | 1 | 1 |

The two reports are **identical to every printed digit**, including the failing
prefill tolerance and the exit code. That is the empirical form of the §6.1
proof: on generation 16 the five arms are inert, because `use_nax` is false and
the `_nax` host functions at `matmul.cpp:922` and `:957` are never entered.

The exit 1 is a pre-existing base property, not a regression introduced here:
the strict gate demands `maximumAbsoluteLogitError` tolerance `0.0`, and the
unchanged base already reports `0.125` on this host
(independently recorded at `research/CRS.md:8168-8173`, `:3576-3577`).
**`MLXFAST_LOCAL_ALLOW_GOLDEN_DRIFT=1` was not set anywhere in this
experiment**, and no gate was relaxed; the base control is what discharges the
finding instead. Note that all tokens match, so this is a logit-tolerance
artefact of gen-16 arithmetic rather than a behaviour difference.

### 7.5 Golden-hash gate: not runnable here, and cheaper than assumed

`correctness_golden.json` does not exist in this checkout, so the hash gate
could not be executed. Worth recording *why* that is not a gap: the
`golden_sha256` emitted at `benchmark.sh:2266-2288` is literally
`shasum -a 256` of the golden **fixture file** (path default
`correctness_golden.json`, override `MLXFAST_CORRECTNESS_GOLDEN_PATH`,
`benchmark.sh:149`) - it hashes the checked-in expectation, not any computed
output. A source edit therefore cannot move it, and verifying it needs no
benchmark run at all. `benchmark.sh:2294-2301` separately warns that the public
goldens were generated on M5, so a near-tie token mismatch is expected on
another generation.

### 7.6 What is still unmeasured

No timing gate was run and none is claimable on this host: the M4 Pro reports
Apple GPU generation 16 and never selects `_nax`, which `AGENTS.md` calls out
directly ("an M4 prefill result is not evidence for an `_nax` change"). Every
millisecond in §5 is a model prediction with one fitted parameter, not a
measurement. The ladder is ready to draw on M5; it has not been drawn.

One arm is an exception worth flagging to the advisor: **arm 5 needs no build
at all.** `darkbloom_steel_prefill_tile()` reads an environment variable, so
`DARKBLOOM_STEEL_PREFILL_TILE=0` reproduces the arm-5 tree on an unmodified
binary. Its predicted effect is exactly 0.00 ms (both settings land on
`SM = SN = 32`, 2048 simdgroups, `U = 0.533`), so it is the cheapest possible
falsification test of the wave model itself: if a free env-var flip moves
prefill measurably, the model in §3.1 is wrong and the rest of the ladder
should not be trusted.

## 8. Pre-registered interpretation

Fixed before any draw, so no arm can be re-narrated after the fact. All
thresholds are on `officialMetrics.candidate.prefill_seconds_per_token` from a
same-session paired draw; one draw resolves ~0.25% at 95%.

| observation | verdict | action |
|---|---|---|
| arm 1 or arm 2/3 improves prefill by **>= 0.6%** (>= 2 sigma of one draw) | the occupancy model has directional power on starved `_nax` dispatches | promote that arm; then draw the stack (arm 6) |
| improvement **>= 3.0%** on arm 1 | wave model quantitatively confirmed | promote and submit; stack only if headroom to the crown remains |
| `\|Delta\| < 0.27%` (null) | the starved families are **not** occupancy-limited: they are launch-latency- or dependency-limited, and the entire "raise simdgroups" family is dead for prefill | close arms 1-3 *and* the census's 11.40 ms starvation estimate as an over-attribution; pivot the r121 line to dispatch-count reduction / fusion instead of geometry |
| **+2% regression** on arm 1 or 2/3 | the 1.5x A/B load traffic from `SM: 32 -> 16` dominates the occupancy gain | close the `SM -> 16` mechanism; the surviving lever on starved dispatches is arm 3 (depth), which adds parallelism at **constant** traffic, so arm 3 must then be drawn separately before the family is abandoned |
| arm 4 regresses by ~+1.4% | saturation knee is above 40% occupancy; wave model validated out-of-sample | no code action; raises confidence in the arm 1-3 magnitudes and in future census pricing |
| arm 4 neutral or better | knee is at or below 40%; occupancy is *not* proportional in that range | treat arm 1-3 ideal numbers as loose upper bounds; re-price the census with a knee term |
| arm 5 not within +/- 0.2% of zero | the `SM`,`SN` invariance argument of §2 is wrong, or `wm`,`wn` matter through a channel this analysis does not model (scheduler, instruction cache, launch cost per TG) | stop the ladder and re-derive; every other arm's prediction shares the same invariance assumption |
| any arm fails a hidden correctness gate | the legality rule of §2 is incomplete | revert immediately and treat every non-AOT tuple as unproven until a stronger legality proof exists |

Note the asymmetry that makes this ladder worth its draws: arms 1-3 are cheap
one-line host changes with **no** weight, layout, precision or dispatch-count
change, so a win is directly promotable, and a null is a *strong* negative that
retires a whole family of census-derived ideas including the 11.40 ms
starvation estimate.

## 9. Deviation from the assignment to report

The assignment asked for one branch per arm
(`maple-tanjiro/r121a-tile-<label>`). `git push` is blocked by this role's
terminal policy and `submit_experiment_result` publishes only the assignment
branch head, so five remote branches are not creatable from here. Instead:

* every arm exists as a standalone patch under
  `research/artifacts/tanjiro-r121a/` that applies cleanly to `cd047c00`; and
* every arm also exists as its **own commit** on
  `maple-tanjiro/r121-a-ranked-prefill-tile-ladder`, where commit *n* reverts
  arm *n-1* and applies arm *n*, so each recorded SHA is a single-arm tree that
  can be checked out and timed directly.

Single-arm trees, ready to check out and time:

| arm | commit | patch |
|---|---|---|
| 1 regular skinny SM16 | `9791d02b` | `arm1-regular-skinny-sm16.patch` |
| 2 splitk shallow SM16 | `02a3ee63` | `arm2-splitk-shallow-sm16.patch` |
| 3 splitk depth 512 | `38c83830` | `arm3-splitk-depth-512.patch` |
| 4 regular wide SM64 | `6b2a0832` | `arm4-regular-wide-sm64.patch` |
| 5 prefill tile default off | `d26ae5b9` | `arm5-prefill-tile-default-off.patch` |
| union of all five (inertness control only) | `780b0579` | - |

The branch head is left at the ledger commit with **no** code change, so the PR
diff is research-only and the advisor chooses which arm to draw. The submitted
surface at the head is byte-identical to base: `git diff cd047c00 HEAD --
Vendor/ Sources/` is empty.

Two further deviations, both deliberate:

1. **Draw order changed.** The assignment listed the arms in the advisor's
   sketch order; §5 reorders them so **arm 1 is drawn first**, because it is the
   only arm whose predicted gain (-5.62 ms) exceeds the estimated resolution of
   a single paired draw by more than 20x. Arm 4 is deliberately kept even though
   it is predicted to *regress* (+1.44 ms): it is the only opposite-sign arm, so
   it is the ladder's control against the wave model being a coincidence.
2. **Arms 1 and 4 are mutually exclusive**, not stackable — they edit the same
   `devc` block and arm 4 fails to apply on top of arm 1 (§7.1). The assignment
   implied a stackable ladder; it is stackable only as 1+2+3.

## 10. The two questions the assignment asked me to answer directly

### 10.1 "Is your Arm 3 the same thing as the closed `_nax` N-tile arm?" (§5)

**Your Arm 3 is exactly the closed arm. Mine is not your Arm 3.** Two separate
answers, because the label collided.

Your Arm 3 as written (`bn=128, wn=4` → `bn=64, wn=2`) is *literally* the lever
named in your own closed list: "**narrowing an `_nax` N-tile**"
(`CURRENT_RESEARCH_STATE.md:6053-6055`). Same dimension, same function, same
`matmul.cpp` site. So I dropped it and did **not** put an N-tile arm on the
ladder. Verified mechanically: across all five patches the only tile symbol any
arm assigns is `bm`. `bn` and `wn` are never written. (Arm 2's diff *mentions*
`bn = 64` only because it splits the shipped `bm = bn = 64;` into two statements
to change `bm` alone; `bn` keeps its pre-existing value.) The rung I labelled
"arm 3" is `split_k_partition_size` — a K-depth change, a different mechanism at
a different line.

**But your closure rationale is stale, and that matters more than the label.**
The parenthetical in the closed list is "(both dead by construction, rule 68)".
That justification was **struck as factually false** in round 104
(`CURRENT_RESEARCH_STATE.md:6337-6345`, Rule 85, fern #585 §4.1/§14.4): bn=64 is
already in the AOT list, and the compiled path is JIT so the AOT list bounds
nothing. My §1 (PROVEN-JIT) re-derives that independently and from different
evidence, so treat the strike as confirmed twice.

Net effect: the N-tile arm is still **closed, but only on measurement**, never
by construction — rule 68 / #527's paired M5 receipt is **+0.639 ms, CI
[+0.325, +0.953], t = 4.43 on 12 dof, −0.242 % of score**, i.e. a real
regression; and swizzle depth at the same site measured a no-op (−0.0141 ms,
t = −0.098). One caveat worth holding: #527 is confounded by a weight-bank size
change (33.55 → 41.94 MB), so it is suggestive rather than decisive *as evidence
that occupancy is irrelevant*. It is still decisive that **this** edit lost.

### 10.2 "Verify the admissibility reasoning" (§5, Forbidden)

Your reasoning was: a tile change is admissible because
`darkbloom_steel_prefill_tile` proves tile changes already pass ranked
correctness. **It is correct for four of my five arms and wrong for one — and
the one it is wrong about is mine, not yours.**

Correct part, and it is stronger than "it passed once": a change to
`bm`/`bn`/`wm`/`wn` only reassigns *which* simdgroup computes which output tile.
The K-reduction stays a single sequential fp32 accumulation in increasing `k`,
so the result is **bit-identical by construction**, not merely
empirically-passing. That covers arms 1, 2, 4 and 5 (arm 5 is the
`darkbloom_steel_prefill_tile` default itself). `bk` is also safe for the same
reason: it changes the block count of that sequential loop, not its order.

Where it breaks: **split-K partition count is not a tile parameter.**
`matmul.cpp:691` allocates `C_split({split_k_partitions, M, N}, float32)` and a
second kernel sums those partials. Changing the partition count changes the
*association* of an fp32 reduction — `(p0+p1)` becomes `((p0+p1)+(p2+p3))` — so
the output is **not bit-identical**. My arm 3 raises the K ≤ 2048 partition
count from 2 to 4 and therefore sits in a different correctness class from every
other rung. `darkbloom_steel_prefill_tile` is *not* precedent for it, because
that override leaves `bk` and the partition count untouched.

**Consequence for the draw order, which I am flagging against my own arm:**
arms 1, 2, 4, 5 cannot fail ranked correctness through numerics, so they are
safe on a lottery ticket. Arm 3 carries a nonzero (small, un-quantified) risk of
flipping a greedy token, and §7.4's equivalence pass does **not** retire that
risk, because `_nax` is dead on gen-16 — the union test exercised none of it.
Given `passed_correctness: false` forfeits the whole ticket, **draw arm 3 last,
and never bundle it with a rung you actually want measured.** Its −2.68 ms is
also the most substitutable prediction on the ladder.

## 11. Bit-identity classification for every arm (advisor request, 09:12Z)

All line citations are
`Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/matmul.cpp` at `cd047c00`.

Decision rule used: an arm may ride a lottery ticket **iff, for every output
element, the ordered sequence of fp32 accumulation events on the ranked host is
unchanged.** This is strictly stronger than mathematical equivalence.

| arm | what the patch writes | verdict | deciding line |
|---|---|---|---|
| 1 | `bm` 64 → 32 when `N <= 1024`, regular `_nax` | **BIT-IDENTICAL** | `:242` — `align_K` is a function of `bk` alone, and `bk` is untouched |
| 2 | `bm` 64 → 32 (`bn` stays 64), splitk small-shape branch | **BIT-IDENTICAL** | `:687` — `split_k_partitions = ceil(K / split_k_partition_size)`, and `:667`,`:679-684` make `split_k_partition_size` a function of **K alone** ⇒ independent of `bm`/`bn`/`bk`/`wm`/`wn` |
| 3 | `split_k_partition_size` 1024 → 512 | **NOT BIT-IDENTICAL** | `:687-691` — partitions 2 → 4, so `C_split` gains two slices and the second reduction kernel sums four partials instead of two |
| 4 | `bm` 64 → 128 when `N >= 4096`, regular `_nax` | **BIT-IDENTICAL** | same as arm 1; the regular path has no `C_split` at all, so each element is one sequential register accumulation |
| 5 | darkbloom default ON → OFF ⇒ `bm`/`bn` 64 → 128, `wm`/`wn` 2 → 4 | **BIT-IDENTICAL** | `:665` sets `bk = 512` and the darkbloom branch `:675-678` does **not** write `bk`; `split_k_partition_size` is untouched, so both `split_k_partitions` (`:687`) and `bk_iters_per_partition` (`:688`) are unchanged |
| 6 | 1 + 2 + 3 | **NOT BIT-IDENTICAL** | inherits arm 3 |

**The load-bearing mechanical fact: no arm in this ladder writes `bk`.** `bk` is
assigned at exactly three sites — `:213` / `:218` (regular) and `:665` / `:673`
(splitk) — and no arm patch touches any of them. `bk` is the only axis that can
re-segment the per-element K loop, so it is untouched everywhere.

### 11.1 Your arms 1/2 derivation is correct. I checked all three paths you named, and one you did not.

1. **Swizzling — real bm dependence, but dead on the ranked host.** `:283` is
   `int swizzle_log = tm <= 3 ? 0 : 1;` with `tm = ceil(M/bm)` (`:281`), so
   `swizzle_log` genuinely *is* bm-dependent. But `:284-286` then overrides it to
   `2` unconditionally when `devc ∈ {'s','c','d'}`, which is the ranked M5. So on
   the ranked host arms 1 and 4 cannot move `swizzle_log` at all. And even where
   it does vary, `:303-305` uses it only to remap tid → tile; each output tile is
   still computed by one threadgroup running the same K loop.
2. **`align_K` — cannot be reached by `bm`.** `:242` (regular) and `:697`
   (splitk) are both `(K % bk) == 0`. Function of `bk` alone. Likewise
   `gemm_k_iterations_aligned = (K / bk)` at `:298`.
3. **The axpby epilogue — no.** `:238-239` derives `use_out_source` and
   `do_axpby` from `alpha`/`beta` only, and the epilogue applies once per output
   element after the K loop closes.
4. **The path you did not name: `align_M` / `align_N` DO flip with `bm`/`bn`.**
   Function constants 200/201 at `:240-241`,`:246-247` (regular) and
   `:695-696`,`:699-701` (splitk). Changing `bm` therefore changes which compiled
   specialization runs — an arm can switch kernel variant silently. It is still
   bit-identical, because that masking is on the **M and N axes**: it decides
   which output elements exist, never which K terms enter a valid element, so
   zero-padded rows/columns produce outputs that are discarded. For our shapes
   `M = 512` and every `bm ∈ {32, 64, 128}` divides it, so `align_M` stays true
   regardless.

**Consequence for what you have loaded.** Arms 1+2 on `7bef942f` are safe to
ride. Arm 4 is safe to swap in **for** arm 1 (not with it — §7.1). Arm 5 is safe
to compose with arms 1 or 2. **Arms 3 and 6 must never ride a ticket.** If arm
3's −2.68 ms is ever wanted, it needs a draw where forfeiting the ticket is
priced in, or an M5 correctness-only run first.

### 11.2 Concession: my Finding 3 was wrong; your §7 correction stands.

`darkbloom_steel_prefill_tile()` has one call site, inside
`steel_gemm_splitk_axpby_nax`, which gen-16 never enters because `use_nax` is
false. So `DARKBLOOM_STEEL_PREFILL_TILE=0` is **inert on this host** and a null
result from it is evidence that nothing ran, not evidence about the wave model.
The "free falsification test" is withdrawn. What survives is narrower: the env
var means arm 5's *ranked* behaviour is reproducible without a code edit, and the
shipped existence of the override is evidence that a tile change on this exact
path has already passed ranked correctness.

### 11.3 Correction to my own §10.2

§10.2 said `bk` changes are "bit-identical by construction". Withdraw that: no
arm here changes `bk`, so the claim was never tested, and it is not obviously
true. A `bk` change flips `align_K` (`:242`,`:697`), changes
`gemm_k_iterations_aligned` (`:298`) and `bk_iters_per_partition` (`:688`), and
re-segments the K loop. **Any future `bk` arm needs its own bit-identity
argument before it may ride a ticket.** The correct general statement is: only
`bm`, `bn`, `wm`, `wn` are safe by construction; `bk` and
`split_k_partition_size` are not.

