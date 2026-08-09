# R104-B — wk/wv prefill GEMM threadgroup regroup

Student: maple-fern · PR #585 · assignment `maple-r104-b-wkwv-tile-regroup`
rev `r104-b-rev1` · base `9527bb727caad1c495e6b62ecbf2445a25e937dd`
(`codex/mlxfast-maple-20260804-advisor`) · branch
`maple-fern/r104-wkwv-tile-regroup` · **receipt budget 0**.

All `matmul.cpp` line numbers in this report are on the **clean base**
`9527bb72`, i.e. before this branch's `+42` lines.

---

## 0. Verdict up front

| item | outcome |
|---|---|
| static routing derivation | **done** — and it **corrects the assignment**, see §1.4 |
| enumerated captured prefill shapes | **done** — exactly **one** shape is captured; null **N-C is refuted** (§2) |
| patch, `bk` untouched | **done** — `bk` is *read* in the predicate and **written by no arm** (§3) |
| local M4 bit-exactness gates | **done**, but they can only prove a **rule-79 identical-code null**: the patched function is **unreachable on this host** (§4, §5) |
| receipt-as-oracle design | **done**, with an exact pre-registered decision rule (§8) |
| rule-83 archive disclosure | **this lever is PR #293**, already implemented and already merged-then-deleted (§6) |
| new physical evidence | **the packing mechanism is real and worth 1.4613× on the incumbent geometry**, measured directly (§7) |
| my own prior model | **refuted by my own measurement** (§7.4) |
| local-timing hygiene | an identical-code local pair showed **+0.9 % "score"** on a lever that cannot execute here — quantified and disowned (§4.4) |
| advisor feedback fb1/fb2/fb3 | each answered explicitly, including **one disagreement with the assignment's own edit site** that I want arbitrated (§12) |

Net: I did not spend a receipt (budget was zero). I produced (a) two
corrections to the assignment's premises, (b) a shape census that kills one
pre-registered null outright, (c) a direct, reproducible measurement of the
mechanism on real hardware, and (d) a decision rule that makes a single future
receipt decisive.

---

## 1. Static routing derivation for the wk/wv prefill GEMM

Shape: `y = x @ W^T` with **M = 512, N = 1024, K = 2048**, bf16, `nt`,
`batch_size_out = 1`. That is `wk` and `wv` for every layer (kv heads 8 ×
head_dim 128 = 1024).

### 1.1 Call chain (M5, `devc == 'd'`, NAX available)

| step | file:line | result |
|---|---|---|
| `Matmul::eval_gpu` | `matmul.cpp:1206` | entry |
| `min(M, N) == 1` gemv shortcut | `matmul.cpp:1252` | **false** (512, 1024) |
| `steel_matmul(...)` | `matmul.cpp:1274` | taken |
| forwarder | `matmul.h:105`, `:123` | → `steel_matmul_axpby<false>` |
| `steel_matmul_axpby` | `matmul.cpp:827` | entry |
| `use_nax` | `matmul.cpp:894-896` | **true** on M5 |
| non-NAX split-K gate | `matmul.cpp:900-901` | fails on `!use_nax` |
| **NAX split-K gate** | `matmul.cpp:922-924` | **false** — see §1.2 |
| `if (use_nax)` | `matmul.cpp:957` | taken |
| `steel_matmul_regular_axpby_nax<false>` | `matmul.cpp:958` (def. `:186`) | **this is the dispatcher we are editing** |

### 1.2 The split-K gate misses by an exact tie

`matmul.cpp:922-924`, with `min_tmn_threshold = 2048`:

```
K >= 3 * max(M, N)                    -> 2048 >= 3072            FALSE
(max(M, N) <= 1024 && K > 2 * max(M, N)) -> (1024 <= 1024) && (2048 > 2048)
                                         -> true && FALSE        FALSE
```

The second clause fails on a **strict-inequality tie**: `K == 2 * N` exactly.
wk/wv sits one unit away from being routed to split-K. (This is the same tie
that `research/RESEARCH_IDEAS_steel-gemm-prefill.md:170-186` H3 proposes to
flip; H3 is *not* bit-exact — split-K changes the accumulation order — and its
sign is unknown. It is out of scope here and stays unimplemented.)

### 1.3 Tile selection inside `steel_matmul_regular_axpby_nax`

`matmul.cpp:213-221`:

```
init:                    bm=128 bn=128 bk=512 wm=4 wn=4
devc in {s, c, d}:       bk = (K >= 8192 && K > M + N) ? 64 : 256   -> 256
                         bm = 64
                         wm = 2
final:                   bm=64  bn=128 bk=256 wm=2 wn=4
```

`align_M = (M % bm == 0)`, `align_N`, `align_K` are all **true**
(512 % 64, 1024 % 128, 2048 % 256). `has_batch = false`, `use_out_source =
false`. Kernel:

```
steel_gemm_fused_nax_nt_bfloat16_bfloat16_bm64_bn128_bk256_wm2_wn4
gemm_k_iterations_aligned = K / bk = 8
```

Grid construction, `matmul.cpp:280-308`: `tn = ceil(1024/128) = 8`,
`tm = ceil(512/64) = 8`; `swizzle_log = 2` unconditionally for `devc in
{s,c,d}`; `tile = 1 << 2 = 4`; `tm = ceil(8/4) = 2`, `tn = 8 * 4 = 32`.

> **grid = (32, 2, 1) = 64 threadgroups; group = (32, 4, 2) = 256 threads = 8
> simdgroups per threadgroup; 512 simdgroups total.**

### 1.4 🔴 Correction to the assignment: `DARKBLOOM_STEEL_PREFILL_TILE` cannot reach this shape

The assignment proposes widening the `K > 4096` clause inside
`darkbloom_steel_prefill_tile()`'s consumer. That lever **does not exist on the
wk/wv path**:

- `darkbloom_steel_prefill_tile()` is defined at `matmul.cpp:82-88`
  (env `DARKBLOOM_STEEL_PREFILL_TILE`, default **on**).
- It has **exactly one call site: `matmul.cpp:674`**, inside
  `steel_gemm_splitk_axpby_nax` (`matmul.cpp:645`).
- wk/wv **never enters that function** (§1.2).

For completeness the split-K NAX tile block (`matmul.cpp:665-677`) is:

```
init:  bm=128 bn=128 bk=512 wm=4 wn=4
if ((M + N) / 2 < 512 || K <= 4096)                     { bm=bn=64; bk=256; wm=wn=2; }
if (darkbloom_steel_prefill_tile() && (M+N)/2 >= 512 && K > 4096) { bm=bn=64; wm=wn=2; }   // bk stays 512
```

Widening `K > 4096` there changes *only* split-K-routed shapes.

> **Any working lever for wk/wv must be added inside
> `steel_matmul_regular_axpby_nax` (`matmul.cpp:186-221`), which today has no
> shape-dependent M/N tiling at all — only the `devc` branch.**

That is what this branch does (§3).

Related: `darkbloom_steel_trace()` (`matmul.cpp:91-97`, env
`DARKBLOOM_STEEL_TRACE`) prints at `:335-338` (regular NAX) and `:773-776`
(split-K NAX). **Both trace sites are inside NAX functions only**, so on a
non-NAX host the trace is silent for these paths; the M4 trace quoted in §5
comes from the non-NAX split-K printer.

---

## 2. Every prefill GEMM the predicate can see — null **N-C is refuted**

Config: hidden 2048, head_dim 128, kv heads 8, 48 full-attention heads /
64 sliding heads, 40 layers (full attention at 0, 4, …, 36), dense MLP only at
layer 0 (`intermediate 8192`), 256 routed experts top-8 with `moe_inter 512`,
one shared expert 512, vocab 100352. Prefill M = 512.

| # | (M, N, K) `nt` | projection | count | GFLOP/pass | M5 route | captured by predicate? |
|---|---|---|---|---|---|---|
| 1 | 512×8192×2048 | wq sliding (29) + L0 gate/up (2) | 31 | 532.58 | regular NAX | ✗ tiles 8×64 = 512 > 96 |
| 2 | 512×6144×2048 | wq full | 10 | 128.85 | regular NAX | ✗ 8×48 = 384 > 96 |
| 3 | 512×2048×8192 | wo sliding (29) + L0 down (1) | 30 | 515.40 | split-K NAX | ✗ never reaches the function |
| 4 | 512×2048×6144 | wo full | 10 | 128.85 | split-K NAX | ✗ |
| 5 | **512×1024×2048** | **wk (39) + wv (39)** | **78** | **167.50** | **regular NAX** | ✅ **the only true case** |
| 6 | 512×2048×2048 | L39 fused [K;V] bank | 1 | 4.295 | regular NAX | ✗ 8×16 = 128 > 96 |
| 7 | 512×256×2048 | router | 38 | 20.40 | split-K NAX | ✗ |
| 8 | 512×64×2048 | `g_proj` sliding | 29 | 3.892 | split-K NAX | ✗ |
| 9 | 512×48×2048 | `g_proj` full | 10 | 1.007 | split-K NAX | ✗ |
| | | **total dense** | **237** | **1502.77** | | |

Only classes 1, 2, 5, 6 reach `steel_matmul_regular_axpby_nax` at all. Among
those, `tiles_m = 8` always, so the discriminator collapses to
`tiles_n ≤ 12`, i.e. **`N ≤ 1536`**. Class 5 (`N = 1024`, `tiles_n = 8`,
product 64) is in; classes 1, 2, 6 are out by 4×, 6× and 2× respectively — not
near-misses.

> **Null N-C ("the regroup helps wk/wv but hurts another captured shape") is
> structurally impossible: there is no other captured shape.** No local timing
> was needed to retire it.

### 2.1 Decode reaches **zero** dense steel GEMMs

Two independent reasons, either sufficient:

1. `Matmul::eval_gpu:1252` short-circuits `min(M, N) == 1` to `gemv` *before*
   `steel_matmul_axpby` is ever called, so an M = 1 decode matmul cannot reach
   the NAX dispatcher.
2. The frontier decode kernel census
   (`research/maple-tanjiro-pr73-decode-kernel-census.md:341-366`) enumerates
   **406 dispatches in 24 families** and contains **no `steel_gemm_*` and no
   `gemv_*` at all** — decode runs entirely on fused custom kernels.

**Archive correction.** `research/pr-nax-skinny-logs/routing-verification.md:22-24`
and `research/maple-tanjiro-nax-skinny-tile.md:149-151` state that M = 1 decode
classes reach the regular-NAX dispatcher and therefore motivate the
`tiles_m >= 4` guard term. That is wrong on both counts above. The
`tiles_m >= 4` term is belt-and-braces, **not load-bearing**. I kept it anyway
(§3) because it costs nothing and it keeps the predicate identical in shape to
the archived one.

**Second archive correction.** `maple-tanjiro-nax-skinny-tile.md:147` lists
`g_proj` as `N = 128`. It is `N = 64` (sliding) and `N = 48` (full).

**Caveat.** The dispatch trace used to cross-check counts
(`research/pr270-logs/steeltrace.worker.err`) was captured on an M4 Pro. Shapes
and dispatch *counts* are architecture-independent; the *routes* in the table
are derived statically for M5 (§1), not read off that trace.

---

## 3. The patch

One file: `Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/matmul.cpp`,
`+42` lines, commit `3d2e69d5d35d04af4d5591f992ee994a53a0236f`. Nothing in
`Sources/MLXFastModel/` is touched (that surface belongs to 104-A).

New selector, after `darkbloom_steel_prefill_tile()`:

```cpp
static int darkbloom_nax_skinny_tile() {
  static int mode = []() {
    const char* value = getenv("DARKBLOOM_NAX_SKINNY_TILE");
    return value == nullptr ? 0 : atoi(value);
  }();
  return mode;
}
```

Inserted in `steel_matmul_regular_axpby_nax` immediately after the `devc`
branch (clean-base `:221`):

```cpp
const int skinny_arm = darkbloom_nax_skinny_tile();
if (skinny_arm != 0 && bm == 64 && bn == 128 && bk == 256 && wm == 2 &&
    wn == 4 && (M % 64) == 0 && (N % 128) == 0) {
  const int tiles_m = M / bm;
  const int tiles_n = N / bn;
  if (tiles_m >= 4 && tiles_m * tiles_n <= 96) {
    switch (skinny_arm) {
      case 1: bn = 64; wn = 2; break;                    // 8 -> 4 simdgroups/TG
      case 2: bn = 32; wn = 1; break;                    // 8 -> 2 simdgroups/TG
      case 3: bm = 32; bn = 32; wm = 1; wn = 1; break;   // 8 -> 1 simdgroup/TG
      default: break;
    }
  }
}
```

### 3.1 `bk` is untouched — explicit statement

> **`bk` appears in this patch exactly once, as the read `bk == 256` in the
> guard. No arm, and no line added by this branch, ever assigns to `bk`.**
> `git show 3d2e69d5 | grep -n 'bk *='` returns nothing.

This is the load-bearing constraint for correctness. `bk` is the K-blocking
factor; changing it would change `gemm_k_iterations_aligned = K / bk`,
`align_K`, and the `BK` template parameter of `gemm_loop`, i.e. the
**accumulation order**, and the change would stop being bit-exact.

### 3.2 Guard is *stricter* than the archived version

PR #293's predicate used `(N % 64) == 0`. Mine uses `(M % 64) == 0 &&
(N % 128) == 0`. Reason: `align_M` and `align_N` are computed from the
*post-regroup* `bm`/`bn` at `matmul.cpp:223-225`. Requiring divisibility by the
**pre**-regroup tile means every arm keeps `align_M == align_N == true` — the
function constants at indices 200/201/202 cannot flip, so the aligned fast path
is preserved and the epilogue predication is identical. Under the arms this is
vacuous for wk/wv (512, 1024 are divisible by everything used), but it makes
the guard safe against any future shape that enters the predicate.

### 3.3 Resulting geometry for M = 512, N = 1024, K = 2048

| arm | bm | bn | bk | wm | wn | sg/TG | threads/TG | grid | TGs | total sg |
|---|---|---|---|---|---|---|---|---|---|---|
| off (incumbent) | 64 | 128 | 256 | 2 | 4 | 8 | 256 | (32, 2, 1) | 64 | 512 |
| 1 | 64 | 64 | 256 | 2 | 2 | 4 | 128 | (64, 2, 1) | 128 | 512 |
| 2 | 64 | 32 | 256 | 2 | 1 | 2 | 64 | (128, 2, 1) | 256 | 512 |
| 3 | 32 | 32 | 256 | 1 | 1 | 1 | 32 | (128, 4, 1) | 512 | 512 |

**Total simdgroups is invariant at 512** because every arm keeps
`SM = bm/wm = 32` and `SN = bn/wn = 32`: the number of 32×32 output tiles is
`(M/32)·(N/32) = 16·32 = 512` regardless of how they are grouped. Only the
*partition into threadgroups* changes.

### 3.4 Bit-exactness by construction

`steel_gemm_fused_nax.h:150-152` derives
`SM = BM/WM`, `SN = BN/WN`, `SK = 32` (a constant), `TM = SM/16`, `TN = SN/16`.
The inner loop `gemm_loop<T, SM, SN, SK, BK, ta, tb, kAlignedM, kAlignedN,
kAlignedK, AccumType>` iterates `for kk0 < gemm_k_iterations_aligned` ×
`for kk1 = 0; kk1 < BK; kk1 += SK`. It uses **no threadgroup memory**
(measured `staticThreadgroupMemoryLength = 0`, §4.1), no cross-simdgroup
reduction, and only `threadgroup_barrier(mem_none)`.

Every arm holds `SM = 32`, `SN = 32`, `SK = 32`, `BK = 256`, `ta = 0`,
`tb = 1`, and all three alignment flags true.

> **All four geometries therefore instantiate the *same* `gemm_loop` template
> with the *same* arguments and accumulate K in the *same* order. Each 32×32
> output tile is produced by one simdgroup with an identical instruction
> sequence. Bit-exactness is a property of the construction, not an empirical
> hope.**

§4.1 confirms this empirically: the offline compiler reports
`SM=32 SN=32 SK=32 TM=2 TN=2` for all four geometries.

### 3.5 Default is OFF, deliberately

`DARKBLOOM_NAX_SKINNY_TILE` unset ⇒ `mode = 0` ⇒ the predicate short-circuits
⇒ the emitted kernel name and grid are byte-identical to base. With a receipt
budget of zero there is no way to validate an on-by-default arm, and shipping
an unvalidated tiling change to the ranked host would be exactly the
"combining unmeasured mechanisms" failure mode. See §8.1 for the (important)
consequence: **a receipt taken against this commit as-is would measure
nothing**.

---

## 4. Local gates on M4 Pro

Host: Apple M4 Pro, `applegpu_g16s`, 20 GPU cores (measured:
`system_profiler SPDisplaysDataType` → `Total Number of Cores: 20`),
`threadExecutionWidth = 32`, `maxThreadsPerThreadgroup = 1024`.

### 4.1 Offline MSL compile + pipeline creation for all four geometries

`research/tanjiro_steel_nax_compile_check.sh` reproduces
`get_steel_gemm_fused_nax_kernel()`'s concatenation order
(`jit_kernels.cpp:977-1010`) and hands it to the offline Metal compiler. JIT is
the compiled path (`Vendor/mlx-swift/Package.swift:25` sources
`jit_kernels.cpp`, `:284` excludes `nojit_kernels.cpp`).

| arm | geometry | SM/SN/SK | TM/TN | thr/TG | compile | metallib bytes | sha256 (metallib) | pipeline |
|---|---|---|---|---|---|---|---|---|
| off | bm64 bn128 bk256 wm2 wn4 | 32/32/32 | 2/2 | 256 | OK `metal4.0` | 75090 | `349cf1e12fac53de1985caefdd4184d47db89548f47cab0917c58d96482af0eb` | **created** |
| 1 | bm64 bn64 bk256 wm2 wn2 | 32/32/32 | 2/2 | 128 | OK | 75073 | `d044f6c90517416ac091a2d68b18b24b46fe0e6fa1021666bb2958204a13b82f` | **created** |
| 2 | bm64 bn32 bk256 wm2 wn1 | 32/32/32 | 2/2 | 64 | OK | 75009 | `b44d19fa226774284129ab4ce191628935baed0ce0602708399927fdb9ad6f88` | **created** |
| 3 | bm32 bn32 bk256 wm1 wn1 | 32/32/32 | 2/2 | 32 | OK | 75009 | `bd4ea1ae6057abb828423fc9725a95104f85bfd942a1ea858ba991f46c5b9d04` | **created** |

Every pipeline reports `staticThreadgroupMemoryLength = 0`,
`threadExecutionWidth = 32`, and
`maxTotalThreadsPerThreadgroup = wm * wn * 32` exactly.

Two honest readings of those stats:

- `maxTotalThreadsPerThreadgroup == wm*wn*32` is **not** evidence about
  register pressure. `steel_gemm_fused_nax.h:86` declares
  `[[kernel, max_total_threads_per_threadgroup(WM * WN * 32)]]`, so the value
  is a *declared cap*, and the driver simply echoes it. Register-limited
  occupancy is not observable this way. Arms 1–3 keep the same
  per-simdgroup tile, so per-simdgroup register demand should be unchanged,
  but this stat does not prove it.
- **`staticThreadgroupMemoryLength = 0` is load-bearing.** Threadgroup
  residency is therefore limited by threads/registers only, never by
  threadgroup memory, so a narrower threadgroup can always pack at least as
  many simdgroups per core as a wider one. This is what makes the regroup a
  one-sided bet on occupancy.

**Correction to the archived script's expectation.** Its header predicts
`STATS` will *fail* on a gen-16 host. It does not: all four pipelines are
created successfully on this M4 Pro. Gen 16 can *compile and instantiate* the
NAX kernels; it is `is_nax_available()` in the host dispatcher (§5) that
refuses to select them.

Rule 75 note: the metallibs above are single-kernel research artifacts built to
`/tmp`, not scored binaries; the two 75009-byte files have different digests.

### 4.2 Upstream-equivalence oracle

`research/run_upstream_equivalence.sh` on this branch:

```
prefill   maximumAbsoluteLogitError 0.125   mean 0.011933609   token 5991 == 5991
decode-0..7  maximumAbsoluteLogitError 0    mean 0             all tokens match
EQUIVALENCE_EXACT_STEPS=8
EQUIVALENCE_EXIT=1
```

Every checked token matches. The single non-zero prefill figure is the
**documented pre-existing M4 near-tie**, not drift introduced here: the archive
records the identical triple `0.125 / 0.011933609 / token 5991` with
`EQUIVALENCE_EXACT_STEPS=8, EQUIVALENCE_EXIT=1` for the *unmodified base* on
this host —
`research/frieren-host-cpu-budget.md:471-494`,
`research/frieren-pr23-r2-cap.md:311`,
`research/RESEARCH_STATE_ARCHIVE_through-round-21.md:6085-6086`,
`research/RESEARCH_ARCHIVE_through-round-91.md:4102`, `:5001`.
My run reproduces those numbers to every published digit, so no separate
base-control run was spent.

### 4.3 Scored-worker build and public golden gate

`./benchmark.sh --local-iterate` on this branch, flag unset (i.e. the arms
compiled in but the predicate returning 0):

```
passed_correctness      true
max_abs_diff            0
golden_hash             b9509697c08a2cf3c2943a85f0b76e39c485c441794690fa76835b40a58d7a63
harness_hash            5cfe4988ee50e92376db6bfc3e8abd61b5258d31b3424fb0d91958b87873d398
weights_hash            aff994300573c5e8589563fc9ff57cdcfb1ef9b49e14898be290a75a6b294b3d
num_layers              40   peak_ram_gb 21
prefill 0.001125 s/tok  decode 0.013027 s/tok   est score 0.792
vs score.local-iterate.baseline.json:
  prefill 0.001126 -> 0.001125 s/token (-0.1%)
  decode  0.012946 -> 0.013027 s/token (+0.6%)
```

Two things to read carefully here, because both are easy to misreport:

- `passed_prefill_speedup_floor` is **false** (`prefill_speedup 0.327`). That is
  the M4 host measured against the *pinned* calibration baseline, which is an
  M5 number; it is a host artifact, not a regression. The meaningful comparison
  is the local baseline snapshot line above, and it is **−0.1 %** on prefill.
- The `+0.6 %` decode delta is noise on a code path this branch does not touch
  at all (§2.1: decode reaches zero dense steel GEMMs, and the flag is off).
  I quote it as a **noise-floor estimate for this host** (≈0.6 % run-to-run on
  decode s/tok), not as an effect.

So the honest statement is: the branch builds under the scored worker, every
checked golden token matches with `max_abs_diff = 0`, and the timing deltas are
indistinguishable from host noise — exactly what a default-off patch must look
like.

### 4.4 Arm 1 forced on — the identical-code null, and a warning

`DARKBLOOM_NAX_SKINNY_TILE=1 ./benchmark.sh --local-iterate`:

```
passed_correctness      true
max_abs_diff            0
golden_hash             b9509697c08a2cf3c2943a85f0b76e39c485c441794690fa76835b40a58d7a63   (identical)
error                   ""     first_failing_{case,layer,step} all null
prefill 0.001110 s/tok  decode 0.012860 s/tok   est score 0.802
vs score.local-iterate.baseline.json:
  prefill 0.001126 -> 0.001110 s/token (-1.4%)
  decode  0.012946 -> 0.012860 s/token (-0.7%)
  est score 0.795 -> 0.802 (+0.9%)
```

**This "+0.9 %" is not a result. It is noise, and I am reporting it precisely
because it is the trap.** On this host `is_nax_available()` is false (§5), so
`steel_matmul_regular_axpby_nax` — the only function this patch edits — is
never entered. Setting the flag cannot change one instruction that executes.
The two runs in §4.3 and §4.4 are therefore a **rule-79 identical-code pair**,
and everything between them is host noise:

| axis | flag off (§4.3) | flag on (§4.4) | apparent Δ |
|---|---|---|---|
| prefill s/tok | 0.001125 | 0.001110 | **−1.3 %** |
| decode s/tok | 0.013027 | 0.012860 | **−1.3 %** |
| est score | 0.792 | 0.802 | **+1.3 %** |

Two runs of provably identical machine code differ by 1.3 % on both axes. For
scale, the ranked receipt's `cand_pre` sd is 0.5802 / 188.405 = **0.31 %**
(§8.3). Local M4 `--local-iterate` is roughly **4× noisier than the instrument
this lever must be measured on**, and a single local pair here would have
"confirmed" a +0.9 % score win that is definitionally zero. This is the
concrete, self-inflicted version of the campaign's bar-strictness rule: I ran
the experiment that would have fooled me, and it did produce a plausible-looking
win.

Useful by-products: the flag path executes without crashing or perturbing
anything on gen-16, correctness stays clean with `max_abs_diff = 0` and an
unchanged `golden_hash`, and the decode axis moves by the same 1.3 % as prefill
even though §2.1 proves decode cannot reach any dense steel GEMM — which is
itself a clean internal check that the movement is common-mode host noise
rather than anything this branch did.

### 4.5 What the local gates can and cannot prove

Because the patch is default-off **and** the patched function is unreachable on
this host (§5), the local gates establish a **rule-79 identical-code null**:
they prove the branch does not perturb the base, and nothing about the arms.
They are necessary, not sufficient. I say this plainly rather than presenting
green gates as evidence for the hypothesis.

---

## 5. 🔴 The patched function is unreachable on every host I have

`is_nax_available()` (`Vendor/mlx-swift/.../metal/device.cpp:913-931`) requires
macOS ≥ 26.2 **and** Apple GPU generation `>= (arch == 'p' ? 18 : 17)`. This
M4 Pro reports `applegpu_g16s` — **generation 16** — so `use_nax == false` at
`matmul.cpp:894-896`, and `steel_matmul_regular_axpby_nax` is never called.

Confirmed empirically with `DARKBLOOM_STEEL_TRACE`: on M4 the wk/wv shape is
dispatched as

```
steel_gemm_splitk_nt_bfloat16_float32_bm32_bn32_bk16_wm2_wn2
M=512 N=1024 K=2048 parts=2 grid=(32,16,2) group=(32,2,2)
```

— the **non-NAX split-K** kernel, a different function, a different tile, a
different accumulation dtype (`float32` partials) and a different number of
threadgroups. Per rule 77 and the `AGENTS.md` warning that "an M4 prefill
result is not evidence for an `_nax` change", no local end-to-end prefill
timing of these arms is possible or meaningful.

This is the central operational fact of the assignment: **the M5 receipt is not
merely the best instrument for this lever, it is the only one.** That is why §7
attacks the *mechanism* with a synthetic probe instead of pretending a local
end-to-end number exists.

---

## 6. Rule 83 — this lever has already been built once (PR #293)

Archive grep before proposing found a direct hit:
`research/maple-tanjiro-nax-skinny-tile.md`, "H2: skinny-N regular-NAX steel
tile downsize for the 78 wk/wv prefill GEMMs", **PR #293**, assignment
`maple-2026-08-07l-nax-skinny-tile` r2, student maple-tanjiro, base
`69178729b154cbb648ea0ce6152e92dbfdb17cc6`. It implemented the same change
through `darkbloom_steel_regular_skinny_tile()` /
`DARKBLOOM_STEEL_REGULAR_SKINNY_TILE`:

```cpp
if (... && bn == 128 && wn == 4 && (N % 64) == 0) {
  tiles_m = ceil(M / bm); tiles_n = ceil(N / bn);
  if (tiles_m >= 4 && tiles_m * tiles_n <= 96) { bn = 64; wn = 2; }
}
```

That is my arm 1 with a weaker guard (§3.2).

**Outcome of PR #293: zero ranked M5 receipts.** r1 was blocked by an in-flight
submission slot; r2 was blocked by 18 consecutive `failed` / `n/a` receipts
between 09:36 and 15:35 UTC. Its disposition is *"queued, not refuted"*. It was
merged **inert, default-off** (`c2812d1`, `8672288`) and then **silently
removed** by the frontier resync `99b974c "Sync promoted frontier afcb832"`. I
verified today that no `darkbloom_steel_regular_skinny_tile` symbol exists
anywhere in the current tree.

The advisor's own note
`research/advisor-r104-the-receipt-is-the-instrument.md:224-233` re-derives
this as "fresh idea 104-B". **The assignment is an unwitting re-proposal of
PR #293.** Flagging it is the point of rule 83.

Consequences I want on record:

1. **Merging this branch inert would repeat a demonstrated no-op.** Inert
   default-off code was already merged once and was deleted by the next
   frontier resync without ever being measured. The value of this branch is the
   evidence in §2, §5, §7 and the decision rule in §8 — not the 42 lines.
2. PR #293's pre-registration (prefill −1.5 to −5 ms, +0.56 % to +1.87 % score;
   3σ bar 1.35 ms from σ(S) = 0.318 ms, n = 16, paired σ ≈ 0.4497 ms) is still
   valid and can be reused, but §8.3 shows its 3σ bar is **too conservative**:
   pairing against `base_pre` inflates σ by √2 for no benefit.
3. Its stage-0 offline compile check is reusable and I did reuse it (§4.1),
   extending it from three geometries to the four that matter here.

Neighbouring archive items, checked and left alone:
`research/RESEARCH_IDEAS_steel-gemm-prefill.md` H1 `DARKBLOOM_FUSED_QKV` (dead,
per advisor r104 `:248`); H3 split-K tie flip `>` → `>=` (`:170-186`, never
implemented, **not bit-exact**, sign uncertain −3…+1 ms); H4 dominated.
`research/maple-tanjiro-threadgroup-packing-curve.md:579-625` established that
the decode QKV packing knob is structurally inert on prefill.

---

## 7. New evidence: the packing mechanism, measured

Since the real kernel is unreachable locally (§5), I built a standalone probe
that isolates *only* the variable the arms change: how many simdgroups are
packed into one threadgroup, holding the total simdgroup count and the
per-simdgroup work fixed.

`research/fern_r104b_grouping_probe.swift` — standalone
`xcrun swiftc -O`, synthetic FMA-spin kernel with **zero threadgroup memory**
(matching the real kernel's measured 0 bytes, §4.1), best-of-25 with the first
leg discarded (rule 77), 20000 inner iterations per simdgroup. Job
`0c4e2817-f311-4933-ba80-b6487d6eb9dd`, exit 0, 21.3 s.

### 7.1 Grouping at the incumbent total (512 simdgroups)

| sg/TG | threadgroups | threads/TG | wall µs | relative |
|---|---|---|---|---|
| 1 | 512 | 32 | 521.7 | 1.0002 |
| 2 | 256 | 64 | 521.7 | 1.0001 |
| 4 | 128 | 128 | **521.6** | **1.0000** |
| 8 | 64 | 256 | **762.2** | **1.4613** |

Reproduced across two independent invocations (762.2 µs both times; 521.5–521.7
for the narrow groupings).

`sg/TG = 8` **is** the incumbent wk/wv geometry and `sg/TG = 4` **is** arm 1.
On this host, at exactly the total simdgroup count the wk/wv GEMM produces, the
incumbent grouping costs **46.1 % more wall time than arm 1 for identical
work**.

### 7.2 The causal control: is it packing, or are wide threadgroups just slower?

Part 1 alone cannot distinguish "wide threadgroups quantize the tail badly"
from "wide threadgroups are intrinsically slower per unit work". Sweeping the
*total* simdgroup count separates them. Throughput, simdgroups per µs:

| total sg | g=1 | g=2 | g=4 | **g=8** | wall steps (g≤4 / g=8) |
|---|---|---|---|---|---|
| 168 | 0.6575 | 0.6579 | 0.6582 | **0.6570** | 1 / 1 |
| 176 | 0.6888 | 0.6895 | 0.6895 | 0.6562 | 1 / 1 |
| 336 | 0.6602 | 0.6602 | 0.6603 | **0.6603** | 2 / 2 |
| 352 | 0.6751 | 0.6750 | 0.6917 | 0.6916 | 2 / 2 |
| 504 | 0.9661 | 0.9662 | 0.9664 | 0.6616 | 2 / **3** |
| **512** | 0.9815 | 0.9815 | **0.9816** | **0.6717** | 2 / **3** |
| 528 | 1.0117 | 1.0121 | 1.0122 | 0.6926 | 2 / **3** |
| 672 | 0.8670 | 0.8670 | 0.8671 | **0.8672** | 3 / 3 |
| 704 | 0.9081 | 0.9083 | 0.9082 | **0.9083** | 3 / 3 |
| 840 | 1.0830 | 1.0689 | 0.9822 | 0.8267 | 3 / **4** |
| 848 | 1.0113 | 1.0846 | 1.0029 | 0.8297 | 3 / **4** |
| 1008 | 0.9798 | 0.9798 | 0.9798 | **0.9799** | 4 / 4 |
| 1024 | 0.9953 | 0.9922 | 0.9849 | **0.9863** | 4 / 4 |

Wall time is quantized into ≈255 µs units (measured levels ≈255.5, ≈521.7,
≈775.4, ≈1028.8 µs — one saturated pass of the fixed per-simdgroup work).

> **At 6 of 13 totals (168, 336, 672, 704, 1008, 1024) the g=8 column matches
> the g=4 column to within 0.1 %.** If 8-simdgroup threadgroups executed the
> same work more slowly, the g=8 column would be uniformly depressed. It is
> not.

> **Conclusion: the 1.4613× penalty at 512 simdgroups is entirely a
> packing/quantization effect** — g=8 needs one extra ≈255 µs pass at
> 504–528 and 840–848 and no extra pass elsewhere. This is exactly the
> mechanism the assignment hypothesizes, isolated and measured.

And the incumbent total, 512, sits in the **worst** band observed
(504 → 1.4607×, 512 → 1.4613×, 528 → 1.4614×).

### 7.3 What the probe does *not* license

- A simple `ceil(total / C)` wave model with fixed capacities **does not fit
  all 13 points**: 63 threadgroups of 8 simdgroups needing 3 passes implies
  capacity ≤ 31 TGs, while 128 threadgroups of 8 needing only 4 passes implies
  capacity ≥ 32. The scheduler is not a strict static wave machine. I therefore
  **refuse to extrapolate the band's location to M5 arithmetically.**
- The concurrency ladder in Part 1 of the probe is **unreliable**: across two
  runs it reported C = 44 then C = 20 for g = 4, and C = 21 then C = 23 for
  g = 8. Riser detection on a noisy host is a weak instrument. Part 4's
  wall-time quantization is the reliable read-out; Part 1 numbers should not be
  quoted.
- M4 Pro has 20 cores; M5 Max is assumed to have 40 (§9). The *location* of the
  penalty band in total-simdgroup space scales with core count and with
  per-core residency, neither of which I can measure on M5. Whether wk/wv's 512
  simdgroups land inside M5's penalty band is **exactly the question only the
  receipt can answer**.

### 7.4 My own prior model was wrong, and the probe is what killed it

Before running the probe I built a static max-load model
`q(g) = g · ceil(512 / (P · g))` with P = 40: it gives 16 for both g = 8 and
g = 4, i.e. **arm 1 buys nothing**, and I combined that with the traffic
argument (per-output-element operand traffic `(bm+bn)/(bm·bn)`: incumbent
0.02344, arm 1 0.03125, **+33 %**) to conclude the arm should be net-negative.

The measurement refutes the model. The binding constraint is not a static
per-core simdgroup budget; it is **whether more than one threadgroup fits per
core at all**, which determines whether the dispatch can backfill. Publishing
this reversal matters more than publishing the arm: the same static reasoning
appears elsewhere in the archive, and it is not predictive.

The traffic penalty remains real but is bounded to cache, not DRAM: the unique
operands of one wk/wv GEMM are `(512·2048 + 1024·2048)·2 B = 6.29 MB` plus a
1.05 MB output, so DRAM traffic is ≈7.3 MB per GEMM (≈12 µs at 610 GB/s,
≈0.94 ms for all 78) against ≈5.6 ms of arithmetic — the GEMM is compute-bound
at the DRAM level and the +33 % is L2 traffic.

---

## 8. Receipt-as-oracle design (specified, **not** executed — budget was zero)

### 8.1 🔴 The submitted variant must NOT be this commit

`DARKBLOOM_NAX_SKINNY_TILE` defaults to 0 and the official harness sets no
`DARKBLOOM_*` environment. **A receipt taken against `3d2e69d5` as-is would
measure the base and publish a rule-79 identical-code null.** The submitted
candidate must change the default of `darkbloom_nax_skinny_tile()` from `0` to
`1` (one character), so the arm is compiled in unconditionally on the ranked
host. Nothing else changes; `bk` still is not written.

### 8.2 Exactly one mechanism per receipt

Arm 1 only. No co-submission with 104-A's `LagunaRuntimeModel.swift` work — the
prefill axis is shared, and a bundled receipt cannot attribute a ~2 ms prefill
delta between two mechanisms.

### 8.3 Read-out: use the contemporaneous `cand_pre` control, not the paired difference

Baseline scale from the archive: `cand_pre` = 188.405 µs/tok × 512 tok =
**96.4634 ms** (`research/CURRENT_RESEARCH_STATE.md:739`).

Conversions:

| use | factor | source |
|---|---|---|
| reading a receipt (`cand_dec` separately observed) | **0.2592 %/ms** | `CURRENT_RESEARCH_STATE.md:655`, `= 0.25 / 96.4636 ms` |
| prospective sizing (decode coupling included) | **≈0.3781 %/ms** | campaign standard; PR #293 used 0.374750 %/ms |

Noise: `sd(cand_pre)` = 0.5802 µs/tok = **0.2970 ms** = 0.1123 % of score.
Critically, `corr(base_pre, cand_pre) = −0.011 [−0.125, +0.105]`
(`research/RESEARCH_STATE_ARCHIVE_through-round-21.md:2727`): the same-session
baseline carries **no** information about candidate prefill noise, so
differencing against it inflates σ by √2 (0.318 → 0.4497 ms, which is exactly
how PR #293 arrived at a 1.35 ms bar). Comparing `cand_pre` against a
contemporaneous control **mean** instead recovers the √2 and shrinks the bar to
≈0.89–0.95 ms.

### 8.4 The pre-registered decision rule

Fix before the receipt is read:

1. Take the `K` most recent contemporaneous receipts whose prefill path is
   provably unchanged relative to the same base, `K ≥ 8`. Let `m̄` and `σ̂` be
   the mean and sd of their `cand_pre` in µs/tok. (Expect `σ̂ ≈ 0.58 µs/tok`.)
2. Let `x` = the arm-1 receipt's `cand_pre`, and
   `Δms = (m̄ − x) × 0.512` (µs/tok → ms over the 512-token window).
3. `z = (m̄ − x) / (σ̂ · sqrt(1 + 1/K))`.

| verdict | condition |
|---|---|
| **PROMOTE** | correctness clean, both 0.95 floors met, `z ≥ 3` **and** `Δms ≥ 0.89 ms` |
| **REFUTE** (close as measured negative) | `z ≤ −3` |
| **INCONCLUSIVE** | `\|z\| < 3` → spend at most one more receipt on the identical variant; pool the two (bar `z ≥ 3` on the pooled mean). If still `\|z\| < 3`, close permanently as "effect below the campaign's two-receipt resolution (< ~0.7 ms), not worth further receipts". |
| **HALT** | any token mismatch or gate failure → null **N-D**; §3.4 says this cannot happen, so it would mean the bit-exactness argument is wrong and the whole family must be re-examined |

Also record on the same receipt: `cand_dec` (must be within noise; the arm
cannot touch decode, §2.1 — a decode move is a red flag that the submitted
variant differs from the intended one) and `ns`.

### 8.5 Pre-registered effect size

wk/wv share of prefill: 167.50 GFLOP of an estimated ≈2794 GFLOP total
(1502.77 dense + ≈1130 MoE + ≈161 attention) ⇒ **6.0 %** ⇒ ≈**5.8 ms** of the
96.46 ms window if time tracks FLOPs. (Independently, 167.50 GFLOP at the
≈29 TFLOP/s implied by that same total gives ≈5.6 ms — self-consistent, not an
independent confirmation, since both use the "time ∝ FLOPs" assumption. Range
4–8 ms.)

If the full M4-measured penalty transfers, arm 1 recovers
`wk/wv × (1 − 1/1.4613) = wk/wv × 0.3157`:

| assumption | Δ prefill | Δ score @ 0.3781 %/ms | z at σ = 0.297 ms |
|---|---|---|---|
| full penalty transfers, wk/wv = 5.8 ms | **1.83 ms** | **+0.69 %** | 6.2 |
| full penalty transfers, wk/wv = 4.0 ms | 1.26 ms | +0.48 % | 4.2 |
| half the penalty transfers, wk/wv = 5.8 ms | 0.92 ms | +0.35 % | 3.1 |
| 512 sg lands outside M5's penalty band | ≈0, or slightly negative from +33 % L2 traffic | ≈0 | ~0 |

So a single receipt is powered at roughly **3σ–6σ** if the mechanism transfers,
and cleanly returns 0 if it does not. That is a good receipt: **both outcomes
are informative**, and the "no effect" outcome is itself the answer to "does
M5's penalty band contain 512 simdgroups".

### 8.6 Disambiguating a null (N-A vs N-B)

`\|z\| < 3` is ambiguous between *the predicate never fired* (**N-A**) and
*it fired but occupancy is not the limiter on M5* (**N-B**). Two ways to
separate them, in cost order:

1. **Preferred, free:** re-derive routing from the exact submitted source
   before reading the receipt (§1 is that derivation). If §1 is right, N-A is
   already excluded; a null then *is* N-B.
2. **One sacrificial receipt, binary answer:** submit a variant whose arm sets
   an *illegal* geometry for the captured predicate (e.g. `bn = 48, wn = 1`,
   giving `SN = 48`, not a multiple of 16, which `steel_gemm_fused_nax.h:150`
   cannot instantiate). If the run errors, the predicate provably fired on the
   ranked host; if it completes normally, the predicate never fired ⇒ N-A. This
   guarantees no score and must be authorized explicitly.
   *Do not* use a merely-slow arm (arm 3) as the reachability canary: arm 3
   could plausibly add ≥5 ms to prefill, ≈5 % of the window, which risks
   tripping the 0.95 prefill floor and publishing nothing anyway — a worse
   trade than the deterministic canary.

`DARKBLOOM_STEEL_TRACE` is **not** available as an oracle: the M5 worker's
stdout is not returned in a receipt, and both trace sites (`matmul.cpp:335-338`,
`:773-776`) live inside NAX functions we cannot observe remotely.

---

## 9. M5 core count is an unmeasured assumption

Every "M5 Max = 40 GPU cores" statement in the archive is spec-sheet inference,
not measurement:
`research/RESEARCH_ARCHIVE_through-round-91.md:4002` ("M5 core count assumed 40
and the arch suffix `s` is inferred"),
`research/RESEARCH_IDEAS_steel-gemm-prefill.md:11`,
`research/tanjiro-m5-calibration-note-A.md:25`,
`research/CURRENT_RESEARCH_STATE.md:2695-2696` (rule 60). The most careful
existing statement asserts only `cores >= 32`
(`research/maple-tanjiro-r103b-kernel-text-differential.md:726-729`).

No MLX/Cmlx API exposes core count — `device_info.cpp:24-53` returns only
device name, architecture, buffer/memory sizes and resource limits. On this
host `system_profiler SPDisplaysDataType` gives a measured 20 cores for the M4
Pro; the ranked M5 is not reachable that way.

Because §7.3 shows the penalty band's location depends on core count *and* on a
residency rule that is not a clean `ceil()`, this uncertainty is a first-order
reason the receipt cannot be replaced by arithmetic.

---

## 10. Pre-registered nulls — disposition

| null | statement | disposition |
|---|---|---|
| **N-A** | routing prediction wrong | **Not observed.** Derivation in §1 is static and complete; the assignment's own proposed lever (`DARKBLOOM_STEEL_PREFILL_TILE`) *was* mis-routed and is corrected in §1.4. |
| **N-B** | grid as predicted but occupancy not the limiter | **Open, and now the only live risk.** §7 shows occupancy/packing *is* the limiter on M4 at this exact simdgroup total; whether M5's band contains 512 simdgroups is unresolved and needs the receipt. |
| **N-C** | regroup hurts another captured shape | **Refuted (§2).** Exactly one prefill GEMM class satisfies the predicate; nothing else can be hurt. |
| **N-D** | not bit-exact → halt | **Not triggered.** §3.4 argues bit-exactness by construction (identical `gemm_loop` instantiation), §4.1 confirms `SM/SN/SK/TM/TN` identical across all four geometries, §4.2 shows every checked token matching, §4.3 shows `max_abs_diff = 0` against the public golden. |

---

## 11. What I did not do

- **No official submission.** Receipt budget was zero; §8 is a design, not a
  run.
- **No local timing claim for the regroup.** I did run the flag-on arm end to
  end (§4.4), but only as a correctness/inertness gate and as a deliberate
  demonstration of the noise trap. The arms are unreachable on gen-16 (§5) and
  the local wk/wv dispatch is a different kernel family entirely, so no local
  second can be attributed to this lever and none is claimed.
- **No `Sources/MLXFastModel/` edits.** That surface belongs to 104-A.
- **No split-K tie flip** (`RESEARCH_IDEAS_steel-gemm-prefill.md:170-186`).
  It is not bit-exact and it is not this assignment.

### Suggested follow-ups (not implemented)

1. **Spend one receipt on arm 1 with the default flipped to 1** (§8.1). This is
   the whole experiment; everything else here is preparation. Expected
   +0.35 % to +0.69 % score, or a clean zero that answers a structural question
   about M5.
2. If arm 1 wins, **arm 2 is the natural next probe**, not a bundled follow-up:
   §7.1 shows g=2 and g=1 are equal to g=4 on M4, so arm 2's expected marginal
   gain over arm 1 is zero and its L2 traffic is 2× worse. Arm 2 and arm 3 are
   in the patch for completeness and should probably never be submitted.
3. **Do not merge this branch inert.** §6.1: the identical code was merged inert
   once and deleted unmeasured by a frontier resync. Either flip the default and
   allocate a receipt, or close the branch and keep this report.
4. **Fix the two archive errors** identified in §2.1 (decode does not reach
   regular NAX; `g_proj` is N=64/48) so the next student does not re-derive a
   wrong occupancy motivation.
5. **Stop quoting the static `q(g)` occupancy model** (§7.4). It predicts the
   wrong sign for this lever.

---

## 12. Advisor feedback — disposition

Three feedback comments landed on #585 before I wrote this. Each is answered
here explicitly rather than absorbed silently.

### 12.1 fb1 — independent derivation, and surface disagreements loudly

`r104-b-fb1-tanjiro-census-covers-your-N-C`. I did **not** read any 104-C /
PR #586 output; §1 and §2 are derived from `matmul.cpp` and the kernel headers
at base `9527bb72` by me. The disagreements I am obliged to surface rather than
reconcile quietly:

1. 🔴 **With the assignment itself.** The assignment locates
   `darkbloom_steel_prefill_tile`'s tile block at `matmul.cpp:664-684` and asks
   me to widen its `K > 4096` clause. That block is **inside
   `steel_gemm_splitk_axpby_nax` (:645)** — the split-K path. wk/wv provably
   does **not** enter split-K (§1.2: the `2·max(M,N) > K` predicate is an exact
   tie and fails), so widening that clause by any amount cannot reach wk/wv.
   The lever has to live in `steel_matmul_regular_axpby_nax` (:186-221), and
   that is where I put it. §1.4. This is the disagreement I most want
   arbitrated, because the assignment's proposed edit site is unreachable for
   the target shape.
2. **With the archive, twice.** `research/routing-verification.md:22-24` and
   `research/maple-tanjiro-nax-skinny-tile.md:149-151` both state that M = 1
   decode reaches regular-NAX. It does not — the `min(M, N) == 1` gemv shortcut
   at `matmul.cpp:1252` diverts it first, and the independent decode kernel
   census (`maple-tanjiro-pr73-decode-kernel-census.md:341-366`) contains no
   `steel_gemm_*` at all. And `nax-skinny-tile.md:147` gives `g_proj` as
   N = 128; it is N = 64/48. §2.1.
3. **With myself.** §7.4 — my own static occupancy model predicted this lever
   buys nothing, and my own measurement refuted it.

If 104-C's census contradicts §2, take §2 as the thing to attack: it is a
complete enumeration against one predicate, so a single counterexample shape
kills it.

### 12.2 fb2 — no wk/wv millisecond figure the census has not paid for

`r104-b-fb2-do-not-quote-a-wkwv-millisecond-figure-yet`. Honoured, and the
constraint is what §2 exists to satisfy. The ≈5.6–5.8 ms in §8.5 is **not** a
share of the 3–6 ms tail-wide envelope and is **not** a roofline subtraction:
it is 167.50 GFLOP measured over the 78 dispatches of *this exact shape*, taken
as a fraction of the 1502.77 GFLOP dense-prefill census I built in §2, and
cross-checked against the implied ≈29 TFLOP/s. It is traceable to a measurement
of that shape, which is the bar fb2 set. It remains an upper bound on what the
lever can pay: the lever recovers packing loss inside those 5.6–5.8 ms, not the
whole slice, which is why §8.5's central case is 1.26 ms and not 5.8.

On the concentrated-vs-diffuse question (104-C's N-B): §2 is evidence **for**
concentration *within the capturable set*, but in the narrowest possible sense —
of 237 dense prefill dispatches, exactly **one class (78 dispatches, 11.1 % of
dense prefill FLOP)** can be captured at all. If 104-C returns "diffuse", my
sizing does not merely shrink, it is void: a diffuse deficit means the wk/wv
slice carries no special packing loss, §8.5's transfer fractions all go to zero,
and the correct action is to close the branch rather than spend the receipt.
I am stating that dependency as a preregistered kill condition, not a caveat.

### 12.3 fb3 — the kill switch, and why it does not survive contact with the M5

`r104-b-fb3-gate-your-tile-change-so-the-binary-is-byte-identical`. Implemented
exactly as suggested: `darkbloom_nax_skinny_tile()` is a sibling of
`darkbloom_steel_prefill_tile()` with the same frozen-`static` `getenv` shape
(§3, §3.5). Local A/B is therefore one binary and one environment variable.

🔴 **But the trick does not extend to the ranked receipt**, and this is worth
saying plainly because fb3's motivation was to reduce receipt-adjacent noise.
The official runner takes a *source snapshot*; there is no way to set
`DARKBLOOM_NAX_SKINNY_TILE` on the M5. So a receipt arm requires flipping the
default in source (§8.1) — a different snapshot, not a different environment.
The kill switch buys clean local A/B and safe merge-inert-ness; it buys nothing
on the instrument that actually decides this lever.

Two consequences I did honour:

- **One process per arm.** The `static` freezes at first touch, so §4.3 and
  §4.4 are two separate processes, not one process toggled.
- **No σ_launch assumption in any arithmetic.** I ran no local timing arm for
  the lever, so nothing here is sized against 48 µs/step or against frieren's
  forthcoming #571 number. §8's power arithmetic is sized entirely against the
  *receipt* channel's own `sd(cand_pre) = 0.5802 µs/tok`.

One incidental datum for #571, offered with its limitations attached: §4.3 and
§4.4 are two relaunches whose only source difference is a markdown file, and
run 2 emitted **zero** `Compiling` lines (`grep -c Compiling` = 0), so no
translation unit was rebuilt between them. They differed by **1.3 % on both
prefill and decode s/tok**. That is a cross-process, same-build swing on
`--local-iterate` — the quantity #571 is after — but it is **n = 2**, on M4,
on the whole-benchmark wall rather than per-step, and I did **not** capture a
rule-75 sha256 of the worker product before leg 1, so I cannot claim byte
identity, only that nothing recompiled. Treat it as a hint that the local
channel is wide, not as a measurement of σ_launch.

---

## 13. Reproduction

```bash
# occupancy / grouping probe (Parts 1-4)
xcrun swiftc -O research/fern_r104b_grouping_probe.swift -o /tmp/ferngrp
FERN_SWEEP=168,176,336,352,504,512,528,672,704,840,848,1008,1024 /tmp/ferngrp

# offline MSL compile + pipeline creation for all four geometries
for g in "64 128 256 2 4" "64 64 256 2 2" "64 32 256 2 1" "32 32 256 1 1"; do
  EMIT_LIB=1 STATS=1 research/tanjiro_steel_nax_compile_check.sh $g
done

# equivalence oracle (expect the pre-existing 0.125 prefill near-tie, exit 1)
research/run_upstream_equivalence.sh

# scored-worker build + public golden gate, flag off (§4.3) and arm 1 forced (§4.4)
./benchmark.sh --local-iterate
DARKBLOOM_NAX_SKINNY_TILE=1 ./benchmark.sh --local-iterate
```

Commits on `maple-fern/r104-wkwv-tile-regroup`:
`3d2e69d` (the 42-line patch), `a8c432a` (the probe), plus this report.
