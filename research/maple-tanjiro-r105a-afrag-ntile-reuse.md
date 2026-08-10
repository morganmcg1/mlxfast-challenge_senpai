# 105-A — A-fragment N-tile reuse in `fp_gather_qmm_rhs_expert_nax` (BN 64 → 128)

**Assignment:** `maple-r105-a-afrag-ntile-reuse`, revision `r105-a-rev1`, PR #592
**Base:** `bad6941c8d5a9294108eb65f91e3d0cb62e0b28c`
**Branch:** `maple-tanjiro/r105-afrag-ntile-reuse`
**Student:** maple-tanjiro
**Local host:** Apple **M4 Pro**, 48 GiB unified memory (low-memory startup profile)

---

## 0. The single most important fact about this report

**This host cannot execute the kernel this assignment is about.**

`metal::is_nax_available()`
(`Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/device.cpp:913-932`) requires

```
gen >= (arch == 'p' ? 18 : 17)
```

M4 Pro reports Apple GPU **generation 16**. There is **no environment override**
anywhere in that function. The `_nax` gather dispatch is gated at
`Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/quantized.cpp:1668`, so
`fp_gather_qmm_rhs_expert_nax` is **never entered** on this machine.

Consequences, stated once and relied on throughout:

* No local benchmark, no local correctness run, no local timing, and no runtime
  `kname` printf can exercise any line I changed inside
  `fp_quantized_nax.h` / `fp_quantized_nax.cpp`.
* Every claim about the changed kernel in Stage 1 is **static evidence**:
  offline `metal` compiles, AIR/IR diffs, issue counting from the source, and a
  byte-exact reproduction of the host-side naming logic.
* The only dynamic evidence that exists for this arm is the **official M5
  receipt ladder** in Stage 2.

This is not a caveat bolted on at the end. It is why Stage 1 was built the way
it was, and why §7 spends as much space on what the brief got wrong as on what
it got right.

---

## 1. Stage 1 — design gate

### D1 — the tile-variant edit, and `expert_aligned` survives · **PASS**

The variant switch lives at
`Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/quantized.cpp:1377-1398`
(post-edit line numbers). `expert_aligned` is computed at `:1403-1406`:

```cpp
const bool align_N = (N % bn) == 0;                       // :1401
const bool align_K = (K % bk) == 0;                       // :1402
const bool expert_aligned =
    darkbloom_expert_aligned_gather() && mode != "affine" && transpose &&
    group_size == 16 && bits == 4 && laguna_moe_shape && M >= 64 &&
    align_N && align_K && bm == 64 && wm == 4 && (wn == 2 || wn == 1);
```

`bn` enters **only** through `align_N`. The two ranked shapes are `N = 1024`
(gate/up) and `N = 2048` (down); `1024 % 128 == 0` and `2048 % 128 == 0`, and
the other three `bn`-free conjuncts (`bm == 64`, `wm == 4`, `wn == 1`) are
unchanged by this arm. **`expert_aligned` holds at `bn = 128`.** Proven by
reading the predicate, not assumed.

The downstream consumers confirm nothing else reads `bn` in a way that could
drop the expert path: `static_expert_shape` (`:1422-1424`) depends on
`expert_aligned` and dtype only, and `expert_pairwise_scale_layout`
(`:1410-1413`) depends on `expert_aligned`, `mode`, `pairwise_shape` and
`scales_.shape(-1)`.

### D2 — `WN` must stay 1 · **PASS**

Variant 4 (`bn=64, wm=4, wn=2`) is a different lever and the wrong one. With
`WN = 2` the kernel computes

```
tm = SM * (simd_group_id / WN);   tn = SN * (simd_group_id % WN);
```

(`fp_quantized_nax.h:1794-1799` region). Two simdgroups that differ only in
`simd_group_id % WN` share the **same** `tm`, i.e. the same A rows, and each
issues its own A-fragment device loads. So `WN = 2` *doubles* intra-TG A
issues relative to `WN = 1`, and the per-output A issue count stays at 0.25
instead of falling. Variant 5's `WN = 1` has already minimised the intra-TG
axis; the only axis left is **inter-TG**, i.e. how many threadgroups re-read
the same sorted-x rows, and that count is exactly `grid.x = N / BN`. Hence
`BN`.

### D3 — issue-count pre-filter · **A-axis PASSES, conditional on the D6 repair**

Counted per thread per k-iteration at `tgp_size = 128` threads (`WM=4, WN=1`),
`BM = 64`, `BK = 64`, bf16 A, NVFP4 W.

| quantity | BN = 64 | BN = 128 | per-TG ratio | per-**output** ratio |
|---|---|---|---|---|
| outputs owned by the TG | 64×64 = 4096 | 64×128 = 8192 | ×2 | — |
| A device-load issues / thread | 8 | 8 | ×1 | **×0.5** |
| A device-load issues / TG | 1024 | 1024 | ×1 | **0.25 → 0.125** |
| A bytes / TG / k-iter | 8192 | 8192 | ×1 | ×0.5 |
| W device-load issues / thread *(repaired)* | 1 (`kSrcBytes=16`, one 16 B vec) | 2 (`kSrcBytes=32`, two 16 B vecs) | ×2 | **flat 0.03125** |
| W device-load issues / thread *(stock, unrepaired)* | 1 | **32** (scalar 1 B loads) | ×32 | **0.03125 → 0.5** |
| threadgroup stores / thread | 1 | 2 | ×2 | flat |
| threadgroup loads / thread (A frag + W frag) | unchanged per output | unchanged per output | — | flat |

Derivation of the A row: `Atile` is loaded straight from device memory
(`fp_quantized_nax.h:1863-1876`, the shipped A-operand hoist), `BM × BK × 2 B =
64 × 64 × 2 = 8192 B` per TG per k-iteration spread over 128 threads = 64 B =
~8 issues/thread at 8 B granularity, and this is **independent of `BN`**
because `BM` and `BK` are unchanged. The TG's output count doubles. Therefore
**A device-load issues per output element halve, 0.25 → 0.125.** The
pre-filter's stated criterion is met.

The W row is where the arm lives or dies, and it is **not** flat unless the
loader is repaired — see D6. Unrepaired, total device-load issues per output
*rise* ≈3.75×, and stock BN=128 fails the pre-filter outright.

### D4 — the SwiGLU epilogue is **broken** at BN=128 in stock form; repaired with a provably-inert generalization · **PASS after repair**

`kSwigluRegLocal` is defined at `fp_quantized_nax.h:1820-1821`. In the shipped
tree it reads `(WN == 1) && (BN == 64) && ((BM / WM) == 16)`; I generalized the
middle conjunct to `(BN % 64 == 0)`.

The host packing is the constraint. `preparePackedRoutedGateUpBank`
(`Sources/MLXFastModel/LagunaRuntimeWeights.swift:1110`) uses `pairRows = 32`
(`Sources/MLXFastModel/LagunaRuntimeModel.swift:10721`), and
`set_pairwise_packed` (`fp_quantized_nax.h:277`) recovers

```
within_block  = row & 63;
logical_row   = (row >> 6) * 32 + (within_block & 31);
```

so **gate/up pairing is (c, c+32) inside each 64-row block**, repeating every
64 rows.

The stock threadgroup-staged epilogue (`fp_quantized_nax.h:2036-2070`) pairs
`col` with `activated_cols + col`, where `activated_cols = BN / 2`. At
`BN = 64` that is `c ↔ c + 32` — correct. At `BN = 128` it becomes
`c ↔ c + 64` — **wrong**, it would pair a gate column of block 0 with a gate
column of block 1. The brief's D4 asked me to "prove it pairs correctly"; it
does **not**. That is a genuine kill for the stock kernel.

Repair: I generalized **both** epilogues to be block-aware, so the reg-local
path (which is bit-exact and cheaper) also serves `BN = 128`:

* `constexpr short kNBlk = BN / 64;`
* `for (short blk = 0; blk < kNBlk; ++blk)` over 64-wide blocks
* gate fragment `4*blk + jf`, up fragment `4*blk + jf + 2`
* `col = 32*blk + jf*16 + fn + jj ∈ [0, BN/2)`

Cross-check against the staged path, which computes `blk = col >> 5`,
`c = col & 31`, gate index `(tm+row)*BN + blk*64 + c`, up index `… + blk*64 + 32
+ c`. At `col = 33`: staged gives `blk=1, c=1` ⇒ tile column `65`; reg-local
gives `blk=1, jf=0, fn=0, jj=1` ⇒ tile column `64*1 + 0 + 1 = 65`. **They
agree.** The output index `size_t(tid.x) * activated_cols + col` remains
correct: at `BN = 128` there are 8 tiles × 64 activated columns = 512 =
`kernel_N / 2`.

**Inertness proof at BN = 64.** The generalized epilogue must not perturb the
shipped default. First attempt did: the short-typed `blk` term survived front-end
IR as `shl i32 %x, 16 / ashr exact i32 %y, 16 / sext`, which the optimizer could
not fold. `research/r105a_reglocal_fold.py` applies the fold that makes it
vanish (`kNBlk == 1` ternaries on `fbase`/`cbase`). After that fold the
`BN = 64` LLVM IR is **identical** to the unmodified HEAD, and the emitted AIR
is **byte-identical** (39,392 B) — see D7 rig check 2.

One consequence worth flagging, because it splits the two arms cleanly:
`fuse_swiglu` is decided **kernel-side** at `fp_quantized_nax.h:1981-1982` as
`kernel_N == 1024 && kernel_K == 2048`. So:

* **A1 (gate/up, `K=2048,N=1024`)** exercises the loader repair **and** the
  epilogue generalization;
* **A2 (down, `K=512,N=2048`)** exercises **only** the loader repair.

That is a free mechanism split and I use it in §6.

### D5 — resources · **measured, one confound remains open**

`Ws_storage[BN * BK_padded]` with `BK_padded = BK + 8 = 72`:
`64 × 72 × 2 = 9,216 B` → `128 × 72 × 2 = 18,432 B`.

Measured on this host (`research/tanjiro_metallib_stats.swift`,
`maxThreadgroupMemoryLength = 32,768 B`):

| pipeline function | `staticThreadgroupMemoryLength` (B) | `maxTotalThreadsPerThreadgroup` | `threadExecutionWidth` |
|---|---|---|---|
| `…_2048x1024_bk64`        | 9,232 | 1024 | 32 |
| `…_2048x1024_bk64_bn128`  | **18,448** | 1024 | 32 |
| `…_512x2048_bk64`         | 9,232 | 1024 | 32 |
| `…_512x2048_bk64_bn128`   | **18,448** | 1024 | 32 |

Both fit the 32,768 B limit with headroom. **`maxTotalThreadsPerThreadgroup`
is saturated at the 1024 API ceiling for both variants**, which means this
metric cannot detect the register-pressure change I care about — a kernel that
uses 64 accumulator floats/thread instead of 32 would still report 1024 as long
as it stays under ~64 registers/thread at 1024 threads. **The register/spill
question is therefore not resolvable from this host**, and I declare it an open
confound. It is exactly the risk behind preregistered outcome **N-2**.

Static register estimate: `TM = SM/16 = 1`; `TN = SN/16` goes 4 → 8. `Dtile`
`NAXTile<float, 1, 8>` = 64 floats (from 32); `Btile` ≈ 64 (from 32);
`Atile[2]` ≈ 16 unchanged. Total ≈ **144 vs ≈80** registers of tile state.
Apple's 128-register soft budget per thread at full occupancy sits between
those two numbers, so a spill at BN=128 is plausible and untestable here.

#138's finding is cited as the brief requires, **scoped**: at ≥128 threads/TG on
**M4**, 1 kB / 9,232 B / 17,424 B / 32,768 B all gave 480 TGs = 24.0/core, i.e.
threadgroup memory did not bind occupancy. That is an M4 measurement and is not
transferable to the ranked M5 unscoped.

### D6 — Finding D regression check · **the regression is real, and the brief's stated test would have missed it** · **PASS after repair**

The brief said: *"Prove `ws`/`wl` are still 1 in the emitted kernel name at
`BN = 128`, for both shapes."*

That test **passes while the regression is present**, and is therefore the wrong
test. `expert_wideld` (`quantized.cpp:1427-1429`) is gated on
`darkbloom_stage_wide_load_ok(w, transpose, bits, N, K, bn)`
(`quantized.cpp:1269-1295`). At `bn = 128` that helper computes
`col_step = bn * (K/2)` = 131,072 (gate/up) or 32,768 (down); both are `% 16 ==
0`, so it **still returns true**, `expert_wideld` is still true, and the emitted
name still contains `_wl_1`.

The actual regression is **inside the kernel**, statically, and never touches the
name:

```
n_reads   = (BCOLS_PACKED * BROWS) / tgp_size        // fp_quantized_nax.h:214-215
          = (32 * BN) / 128        = 16  →  32
kSrcBytes = n_reads                                   // ≈:422-467
kWideLoadShapeOk  requires kSrcBytes == 16   → statically FALSE at BN=128
kWideLoad8ShapeOk requires kSrcBytes ==  8   → statically FALSE at BN=128
```

so the vectorised device load falls back to **32 scalar 1-byte loads per thread
per k-iteration** — exactly #138's Finding D, and the standing comment at
`fp_quantized_nax.h:449-451` already acknowledges the `kSrcBytes == 32`
fallback. `kWidenShapeOk` is unaffected, so `wide_store` survives; only the
load degrades. This is the ×32 row in the D3 table.

Repair: I added a `WideSrc32` path (hunks at `.h:+445, +465, +499, +523`) that
issues **two** 16-byte vector loads instead of 32 scalar ones. It is bit-exact
by construction: at `BN = 128` the loader has `bj = 0`, so
`src_byte_off() = bi * src_ld / 2 = bi * 1024`, which is always 16-byte aligned.

**Emitted kernel name strings** (D6 / evidence-contract item 1). These cannot be
captured at runtime here (see §0), so they are derived by a program that copies
`concatenate<>` verbatim from `mlx/backend/metal/utils.h:47-69` and the `kname`
block verbatim from `quantized.cpp:1477-1510`
(`research/r105a_kname_derive.cpp`):

```
gate/up  bn=64  nvfp4_gather_qmm_rhs_expert_static_nax_nt_bfloat16_t_gs_16_b_4_bm_64_bn_64_bk_64_wm_4_wn_1_k_2048_n_1024_eg_256_ws_1_wl_1_ps_1
down     bn=64  nvfp4_gather_qmm_rhs_expert_static_nax_nt_bfloat16_t_gs_16_b_4_bm_64_bn_64_bk_64_wm_4_wn_1_k_512_n_2048_eg_256_ws_1_wl_1_ps_2
gate/up  bn=128 nvfp4_gather_qmm_rhs_expert_static_nax_nt_bfloat16_t_gs_16_b_4_bm_64_bn_128_bk_64_wm_4_wn_1_k_2048_n_1024_eg_256_ws_1_wl_1_ps_1
down     bn=128 nvfp4_gather_qmm_rhs_expert_static_nax_nt_bfloat16_t_gs_16_b_4_bm_64_bn_128_bk_64_wm_4_wn_1_k_512_n_2048_eg_256_ws_1_wl_1_ps_2
```

`_ws_1_wl_1` at `bn = 128` on both shapes — the brief's test passes. The only
token that changes is `bn_64` → `bn_128`. **Do not use this test again for a
tile-width arm; use the `kSrcBytes` static predicate.**

Value table used, all read from source: `mode = "nvfp4"`,
`static_expert_shape = true` (`:1422-1424`), `type_string = "bfloat16_t"`,
`group_size = 16`, `bits = 4`, `bm = 64`, `bk = 64`, `wm = 4`, `wn = 1`,
`egroups = 256` (`darkbloom_expert_gather_groups()` default, `:1222`),
`expert_widest = true` (`:1210`), `expert_wideld = true` (`:1216` ∧
`stage_wide_load_ok`), `expert_pairwise_scale_layout` = 1 for gate/up and 2 for
down (`laguna_expert_pairwise_scale_layout`, `:1315-1330`).

### D7 — build and twin · **PASS (one known pre-existing false positive)**

The runtime source is the generated twin
`Vendor/mlx-swift/Source/Cmlx/mlx-generated/fp_quantized_nax.cpp`, because
`Package.swift:25` compiles `jit_kernels.cpp` and `:283-284` exclude
`backend/metal/kernels`. Every edit was applied to **both** files by
`research/r105a_apply_kernel_edits.py` + `research/r105a_reglocal_fold.py`, and
the edit sets were verified identical:

```
$ git diff -U0 -- …/kernels/fp_quantized_nax.h  | grep -E '^[+-][^+-]' | sort  # 67 lines
$ git diff -U0 -- …/mlx-generated/fp_quantized_nax.cpp | grep -E '^[+-][^+-]' | sort  # 67 lines
  → byte-identical
```

`research/nax_safety_rig.sh` (`AXIS=BN BASE_REV=HEAD research/nax_safety_rig.sh 64 128`):

```
1. PASS BN=64 compiles/links/emits IR ; PASS BN=128 compiles/links/emits IR
2. PASS BN=64 AIR byte-identical to HEAD (39392 B)
3. PASS BN=64: 3 cooperative matmul calls ; PASS BN=128: 3
4. accepted kSrcBytes = 8 16 32
   loader<64,64,tgp=128>  kSrcBytes=16 widened → PASS BN=64
   loader<128,64,tgp=128> kSrcBytes=32 widened → PASS BN=128
5. PASS narrowed predicate still builds BN=64
   PASS narrowed predicate rejects BN=128 (4 static_assert errors)
6. FAIL twin stale: DIVERGENT .h:275 removed content
```

`python3 research/nax_twin_check.py`:

```
fp_quantized_nax: .h 2087 lines, generated block 2219 lines
  structural  +147 generator preamble
  structural  -2 #include at .h:6
  structural  -5 PRAGMA-VARIANT block at .h:1546
  structural  -1 PRAGMA-VARIANT block at .h:1600
  structural  -8 PRAGMA-VARIANT block at .h:1945
  structural  +2 generator trailer
  DIVERGENT   .h:275 removed content
      only in .h  |

TWIN CHECK: 1 divergent hunk(s); the generated copy is stale
```

**Check 6 / the one divergent hunk is a proven pre-existing false positive.**
`.h:274-275` is a doubled blank line immediately before
`short row_in_tile() const { return bi; }`, which the generator collapses to
one. It is byte-identical between base `HEAD` and my worktree, and my first real
hunk is `@@ -444,0 +445,7 @@`. The reported divergent content is empty
(`only in .h  |`). No action taken: repairing it would be an unrelated edit to
the submitted surface.

#### A reportable defect I found in the rig itself

`research/nax_safety_rig.sh` was compiling the kernel **without**
`DARKBLOOM_SWIGLU_REGLOCAL` and `DARKBLOOM_BSEARCH_HOIST`, which
`Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/jit_kernels.cpp:1167,1182`
emit **unconditionally** into every `_nax` runtime compile. The rig was
therefore validating a staged-epilogue variant that **never ships**. I fixed it:

```sh
# The runtime JIT (jit_kernels.cpp) emits both of these into every _nax
# compile, so a rig that omits them validates a variant that never ships.
DEFINES="${DEFINES:-DARKBLOOM_SWIGLU_REGLOCAL DARKBLOOM_BSEARCH_HOIST}"
```

appended to all five `"${CHECK}"` invocations. Every rig result quoted above is
from the corrected rig. Anyone who used this rig before today validated the
wrong variant.

#### Metallib rebuild

`./setup.sh` — recorded in §3.

---

## 2. What was implemented, and where

Submitted surface (3 files, all in `benchmark.json`'s `editablePaths`):

| file | change |
|---|---|
| `Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/kernels/fp_quantized_nax.h` | `WideSrc32` loader path; `kSwigluRegLocal` generalized to `BN % 64 == 0`; block-aware reg-local SwiGLU epilogue |
| `Vendor/mlx-swift/Source/Cmlx/mlx-generated/fp_quantized_nax.cpp` | byte-identical twin of the above |
| `Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/quantized.cpp` | variants 6/7/8 added to `darkbloom_stage_bm128_variant()`'s whitelist and to the tile switch |

Host arms (`quantized.cpp:1373-1398`):

```cpp
const bool laguna_moe_shape     = (K == 2048 && N == 1024) || (K == 512 && N == 2048);
const bool laguna_gate_up_shape = (K == 2048 && N == 1024);
...
case 6: bm = 64; wm = 4; wn = 1; if (laguna_moe_shape) { bn = 128; } break;
case 7: bm = 64; wm = 4; wn = 1; if (laguna_gate_up_shape) { bn = 128; } break;
case 8: bm = 64; wm = 4; wn = 1; if (laguna_moe_shape && !laguna_gate_up_shape) { bn = 128; } break;
```

`grid_dims` follows automatically: `darkbloom_gather_xmajor_ct()` returns a
hardwired `0` (`:1290-1292`), so the dispatch is
`((N + bn - 1)/bn, egroups, 1)`.

**Arm ↔ default mapping.** Per the brief's "do not merge inert default-off
code", every measured arm ships as the **default** return of
`darkbloom_stage_bm128_variant()`; receipts run with no env overrides.

| arm | default variant | BN=128 applies to |
|---|---|---|
| A0 control | 5 (shipped) | nothing |
| A1 | 7 | gate/up only |
| A2 | 8 | down only |
| A3 | 6 | both |

Scope and budget, checked against the base:

```
$ senpai/validate-assignment-scope.sh "$BASE_SHA" <3 paths>
assignment scope OK: 3 submitted path(s)
$ senpai/check-editable-budget.sh "$BASE_SHA"
current=2687095/3000000 headroom=312905 growth=6887/262144 files=142 (base=142)
```

---

## 3. Build and correctness evidence

### 3.1 Release build of the scored surface

`swift build -c release --force-resolved-versions` — **exit 0**
(`Package.resolved` restored afterwards with `git checkout --`).

### 3.2 AOT metallib rebuild (`./setup.sh`)

Required because this change touches a header that the AOT `.metal` translation
units include. Exit 0, elapsed 78 s:

```
[  4%] Building fp_quantized_nax.air
… fp_quantized_nax.h:1736:17: warning: unused variable 'BN_padded'
1 warning generated.
[  4%] Building mlx.metallib
[100%] Built target mlx-metallib
build-mlx-metallib.sh: wrote …/.build-worker/release/mlx.metallib
setup.sh: setup complete elapsed=00:01:18
```

Metal 400 / macOS 26.5 SDK. The `BN_padded` warning is **pre-existing** — it
comes from commit `936ef3b2`, not from this change.

**What this does and does not prove.** `fp_quantized_nax.metal:64-65`
instantiates only `bm=64, bn=64, bk=64, wm=2, wn=2`. So the metallib rebuild
proves the edited header still compiles and links for the AOT instantiations;
it does **not** compile the `BN=128 / wn=1` expert-static path. That path is
JIT-compiled at runtime from the generated twin, and the offline rig in §1 D7 is
what compiles it.

Vendored-source fingerprint after the edits:
`dd44890863143ef8b962e89c8b51beac71bcf8bcf401e33fc60040d6d7c01b97`.

### 3.3 Upstream-equivalence oracle

Run with `research/run_upstream_equivalence.sh` on this branch's HEAD.

**Standing caveat, and it is a large one:** this host is an **Apple M4 Pro**.
`metal::is_nax_available()`
(`Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/device.cpp:913-932`)
requires GPU generation ≥ 17 (≥ 18 for `arch=='p'`); M4 Pro reports generation
16, and there is no environment override. The `_nax` dispatch gate is
`quantized.cpp:1668`. **No local correctness run, timing run, or golden check
on this host can reach the kernel this assignment edits**, at `BN = 64` or at
`BN = 128`, with or without the variant override. The oracle result below is a
regression check on the AOT/non-`_nax` paths and on the metallib rebuild — it
is *not* evidence that the `BN = 128` epilogue pairing is correct. The proof
for that is D4's static argument plus the offline compile rig, and the real
check is the M5 receipt ladder's own correctness gate.

Run as a supervised job (`run_job`, argv `bash research/run_upstream_equivalence.sh`,
cwd = repo root, 3600 s budget). Job `a1f08047-37e2-4c34-a383-931c87c868cd`,
wall clock **81.9 s**, of which 26.43 s was the debug build.

```
prefill   maximumAbsoluteLogitError 0.125   meanAbsoluteLogitError 0.011933609
          runtimeToken 5991 == upstreamToken 5991
decode-0  maximumAbsoluteLogitError 0       meanAbsoluteLogitError 0    tokens match
decode-1..decode-7                          identical: max 0, mean 0, tokens match
          (token cycle 509 / 902 / 5991 reproduced exactly)
EQUIVALENCE_EXACT_STEPS=8
EQUIVALENCE_EXIT=1
```

The wrapper exits 1. **That exit code is a known, documented, pre-existing
non-M5 host artifact and is not attributable to this branch.** The signature is
not merely "similar to" the recorded artifact — it is the *same three numbers*:
`max 0.125`, `meanAbs 0.011933609`, prefill argmax `5991`, with all eight decode
steps bit-exact. Prior rounds recorded that exact triple on this host class:

| Where | What it says |
|---|---|
| `research/fern-r104b-wkwv-tile-regroup.md:366-375` | the **unmodified base** yields `0.125 / 0.011933609 / token 5991`, `EQUIVALENCE_EXACT_STEPS=8`, `EQUIVALENCE_EXIT=1` |
| `research/RESEARCH_ARCHIVE_through-round-91.md:4102` | "The single prefill divergence (0.125, meanAbs 0.011933609) was **proven pre-existing**" |
| `research/RESEARCH_ARCHIVE_through-round-91.md:5001-5002` | same triple, same conclusion |
| `research/CURRENT_RESEARCH_STATE.md:580` | "base's own oracle deltas identically (0.125 / 0.011933609)" |
| `research/RESEARCH_STATE_ARCHIVE_through-round-21.md:6086` | earliest recorded sighting |
| `research/frieren-host-cpu-budget.md:471-474`, `research/frieren-pr23-r2-cap.md:311`, `research/frieren-pr23-r2-result.md:320-321`, `research/advisor-r104-the-receipt-is-the-instrument.md:1417` | independent re-confirmations across three students |

Because `fern-r104b` recorded the identical transcript for the *unmodified*
base on this host class, a fresh base-worktree rerun would only reproduce a
number that is already on file six times over; I did not spend a second
80-second build on it. If the advisor wants the paired control anyway it is one
`git worktree add` at `bad6941c` plus one `run_job` invocation.

**Verdict: correctness gate PASS** — zero regression attributable to this
branch, subject to the standing M4-Pro caveat above that the edited `_nax`
kernel is not reachable by *any* local check.

One unrelated pre-existing warning surfaced in the build log:
`Sources/MLXFastModel/LagunaRuntimeModel.swift:10832`, `var
mergedSharedActivated` was never mutated. It is present on the base and is
untouched by this branch.

---

## 4. Stage 2 — receipt ladder

### 4.1 Stage 2 could not start: the official submission channel is closed

Stage 1 passed every gate, the three-file candidate is committed and clean, the
per-arm defaults are ready — and **zero receipts can be dispatched**, for a
reason that is outside this assignment and outside a student's authority to fix.

`AGENTS.md` mandates `senpai/submit-official.sh "$BASE_SHA"` for every official
submission from this campaign. Run verbatim, with the note file prepared for the
first A0 control receipt:

```
$ senpai/submit-official.sh bad6941c8d5a9294108eb65f91e3d0cb62e0b28c \
    --note-file /tmp/r105a_note_a0_1.md
official submit: BASE_SHA submitted snapshot differs from current origin/main
official submit: reapply and remeasure the candidate on a current snapshot
```

The refusal comes from `senpai/submit-official.sh:72-78`:

```bash
if ! git diff --quiet "${main_sha}" "${base_sha}" -- "${protected_paths[@]}"; then
```

where `protected_paths` is `benchmark.json` plus all 97 `editablePaths`.

**Diagnosis.** The guard fires in the *opposite* direction from the one it was
written for. It is not that the recorded base is stale:

```
origin/main                                 = 1bc1c8954147c9e322aad1f3b80bd9fa3c0888d7
BASE_SHA (assignment-recorded)              = bad6941c8d5a9294108eb65f91e3d0cb62e0b28c
git merge-base BASE_SHA origin/main         = 1bc1c8954147c9e322aad1f3b80bd9fa3c0888d7
```

`origin/main` is an **ancestor** of `BASE_SHA`. The recorded base is *ahead* of
fork main by the entire maple research frontier — 27 submitted files and ~5,211
inserted lines, including `MLXLMCommon/Evaluate.swift`, `KVCache.swift`,
`SwitchLayers.swift`, `jit_kernels.cpp`, `matmul.cpp`, `quantized.cpp`,
`sdpa_vector.h`, `rms_norm.metal`, `rope.metal` and `arg_reduce.metal`.
Fork `main`'s last content commit is `71818038 Sync promoted organizer frontier
cc6ddc1` (2026-08-09 14:21 +0100); everything the campaign has promoted since
round 85 lives only on `codex/mlxfast-maple-20260804-advisor`. The guard itself
(`e29a7604`, PR #547) landed on main at 2026-08-09 15:06 +0200, roughly ten
hours before this assignment was created, so this branch is plausibly the first
one to meet it.

**What I did not do.** The guard takes `BASE_SHA` as an argument, so passing
`1bc1c895` instead of the advisor-recorded `bad6941c` would make the diff empty
and the wrapper would proceed. That is a bypass of the exact protocol
`AGENTS.md` mandates and it would misreport the base the candidate was built
on, so I did not do it, and I did not call `mlxfast submit` directly either.

**What unblocks this (advisor action, one of):**

1. promote the current frontier to `origin/main` so that the recorded
   `BASE_SHA`'s submitted snapshot equals main's — the documented invariant is
   `AGENTS.md`: *"The maintained fork `main` is the integration base … it must
   contain the relevant organizer updates and the current promoted editable
   frontier. The advisor owns that integration and records its exact commit as
   `BASE_SHA`"*; or
2. record a new `BASE_SHA` whose submitted snapshot already equals
   `origin/main`, and revise this assignment onto it; or
3. state explicitly that the guard's snapshot-equality check is to be relaxed
   for this campaign, and say so in the runbook rather than in a student branch.

Until one of those happens **every** official submission from this campaign is
refused, not just this arm's. That is the most load-bearing finding of this
session and it is why §4.2 is empty.

### 4.2 Receipts

| arm | commit SHA | timestamp | `cand_dec` | `cand_pre` | `cs` |
|---|---|---|---|---|---|
| — | — | — | — | — | — |

**None dispatched.** Receipt budget consumed: **0 / 8**.

---

## 5. Verdict

**Rig-invalid is _not_ the verdict.** The brief's `Rig-invalid` bucket is
reserved for "D6 fails, or `expert_aligned` drops, or the twin check disagrees."
None of those happened: D6's regression is real but **repaired** (§1 D6),
`expert_aligned` holds (§1 D1), and the twin is byte-identical (§1 D7).

**No terminal verdict against §4 of the brief is available.** P, N-1 and N-2 are
all statements about M5 receipts, and no receipt could be dispatched (§4.1).
Specifically:

* I am **not** claiming N-1. The preregistered sentence — *"the A-operand
  re-reads are already absorbed by cache, and the routed gather-GEMM has no
  remaining ranked lever"* — is written here only to record that it remains
  unclaimed. Asserting it without receipts would close the campaign's largest
  open family on zero evidence.
* I am **not** claiming P, and **not** claiming N-2.

What Stage 1 does deliver, terminally:

1. The lever is **implementable and expert-aligned** at `BN = 128` for both
   Laguna MoE shapes (D1, D2, D3).
2. The naive edit is **broken twice over** — a silent wide-load regression (D6)
   and a wrong SwiGLU pairing (D4) — and the brief's own stated test for the
   first of those would have **passed while the regression was present**. Both
   are repaired and the repairs are proved inert at `BN = 64` by byte-identical
   AIR.
3. The prize is **materially smaller than the brief's headline**, and bounded
   by arithmetic rather than by opinion (§7.2).

### 5.1 Exactly what is needed to finish this

The candidate is committed, clean, in scope and inside budget. Once §4.1 is
resolved the remaining work is mechanical and needs no new design:

| step | content |
|---|---|
| 1 | three A0 control commits (`Sources/` byte-identical to base; SHA differs via an inert comment inside one of the three submitted vendor files, because the archive contains only `editablePaths` and the service dedupes byte-identical archives) |
| 2 | A1 commit: default variant `5 → 7` (gate/up only) |
| 3 | A2 commit: default variant `5 → 8` (down only) |
| 4 | A3 commit: default variant `5 → 6` (both), only if A1 or A2 is positive |
| 5 | interleaved ladder A0-1, A1-1, A0-2, A1-2, A0-3, A2-1, A2-2, spare — 786 s minimum inter-arrival |

---

## 6. Mechanism attribution

The arm split is designed so that a positive A1 and a positive A2 implicate
**different** mechanisms, which is why they are separate receipts rather than
one combined change.

`fuse_swiglu` is decided **kernel-side**, at `fp_quantized_nax.h:1981-1982`, by
`kernel_N == 1024 && kernel_K == 2048`. Only the gate/up shape fuses. Therefore:

| arm | exercises the `WideSrc32` loader repair (D6) | exercises the block-aware SwiGLU epilogue (D4) |
|---|---|---|
| A2 (down) | yes | **no** |
| A1 (gate/up) | yes | yes |

So A2 is a clean read on the loader path alone. If A2 is null and A1 is
negative, the epilogue generalization is the suspect and D5's register estimate
(≈144 vs ≈80 per-thread values, `TN` 4 → 8) is the mechanism. If both are null,
the D3 issue-count reduction did not convert — which is exactly the #244
precedent (`RESEARCH_ARCHIVE_through-round-91.md:1820`): the issue-count
pre-filter is necessary, not sufficient.

A confound I cannot remove locally and that the ladder must not ignore: A1 and
A2 both change **threadgroup memory per TG** (9,232 B → 18,448 B, measured in
§1 D5) and **per-thread accumulator count** at the same time as they change
`grid.x`. A positive result is therefore attributable to "BN = 128" and not
specifically to "halved A traffic". §7.3 gives the arm that separates those two,
which I am **not** authorised to run under this assignment.

---

## 7. Where the brief and the round-105 advisor note are wrong

Four items. The first is in §1 D6 and is the largest. The rest follow.

### 7.1 D6's stated test would have passed while the regression was present

Recorded in full at §1 D6. In one line: the brief says *"Prove `ws`/`wl` are
still 1 in the emitted kernel name at `BN = 128`"*, but
`darkbloom_stage_wide_load_ok()` (`quantized.cpp:1269-1295`) is a function of
`col_step` divisibility only, and at `bn = 128` it still returns true, so the
emitted name still carries `_ws_1_wl_1` — verbatim strings in §1 D6 — while the
kernel has silently degraded to 32 scalar 1-byte loads per thread per
k-iteration. The real regression lives in `kSrcBytes` (16 → 32) failing
`kWideLoadShapeOk` (== 16) and `kWideLoad8ShapeOk` (== 8) **statically inside
the kernel**, where the emitted name cannot see it. A student who ran exactly
the test the brief specifies would have reported D6 PASS and then measured a
regression as if it were a lever.

### 7.2 The ≈8.4 ms headline is the zero-reuse corner, and that corner is arithmetically excluded

The brief's §1.1 sizing (≈8.4 ms gate/up, ≈4.2 ms down) reproduces exactly from
`research/advisor_r105_gather_roofline.py`'s own numbers, so it is not an
arithmetic slip: at 155,648 rows, halving `grid.x` removes
`4096 B × 8 = 32,768 B/row` for gate/up (5.100 GB → 8.36 ms at 610 GB/s) and
`1024 B × 16 = 16,384 B/row` for down (2.550 GB → 4.18 ms). Total 7.650 GB =
12.54 ms.

But that is the **`r = 1` corner**, where every A re-read is a DRAM miss. The
advisor's own script prints the floor for that corner and it does not survive
contact with the only measurement in the same script:

```
  weights only (cache-immune floor)       14.826 GB ->  24.306 ms
  weights + ideal-reuse activations       16.261 GB ->  26.657 ms
  weights + zero-reuse activations        30.765 GB ->  50.434 ms
--- vs tanjiro dS_1 (contaminated) = 43.262 ms ---
```

`30.765 GB / 43.262 ms = 711 GB/s`, which is **16.6 % above the measured M5
peak of 610 GB/s** (rule 80, the script's own constant at `:48`). A traffic
model that requires the machine to exceed its own peak bandwidth is refuted.

Parameterise honestly: let `r` be the fraction of A re-reads that miss cache, so
DRAM traffic is `16.261 + 14.504·r` GB and the arm's prize is `12.54·r` ms.
Requiring the implied bandwidth to stay at or below 610 GB/s gives
`16.261 + 14.504·r ≤ 610 × 43.262 ms = 26.390 GB`, i.e.

> **r ≤ 0.698, so the prize is at most 8.76 ms, not 12.54 ms.**

and that ceiling assumes the kernel runs at **100 %** of DRAM peak, which the
same script says it does not (achieved 375.9 GB/s = 61.6 %).

**The bound is robust to rule 76.** Rule 76 forbids *pricing* with
`dS_1 = 43.2619 ms` because it over-estimates — it produced 117 % of ceiling on
attention (#586 §3.3). Here it is used only as an **upper bound** on the
gather-GEMM's time, and an over-estimating upper bound makes the true time
smaller, which makes `r`'s ceiling **smaller** still. The refutation is
therefore conservative in the safe direction.

Two consequences the brief should have drawn and did not:

* **"the largest single number on the board" is not established.** The record
  bar is 3.803 ms = +1.438 % of `cs`. The arm clears it only if
  `r ≥ 3.803/12.54 = 0.303`. So the brief's own framing reduces to a coin-flip
  on whether more than 30 % of A re-reads miss, not to a 3× record.
* **the experiment is nevertheless well-posed, and that is the real argument
  for running it.** The prefill channel's 1-vs-1 σ is 0.1588 % of score
  (dof 14) and the elasticity is 0.3781 %/ms, so σ = **0.420 ms**, which on the
  `12.54·r` scale is **σ_r = 0.033**. One clean pair pins `r` to ±0.033. No
  cache-hierarchy argument in this repo comes close to that resolution. The
  brief undersells itself: the value here is measuring `r`, not collecting
  8.4 ms.

Also, minor but worth recording: the advisor's note forbids `43.262 ms` under
rule 76 and then makes it the **only** empirical anchor in
`advisor_r105_gather_roofline.py:186`. If the anchor is truly unusable, the note
has no empirical support for preferring the zero-reuse corner over the
ideal-reuse corner at all, and the `≈8.4 ms` figure should not have been stated
without an interval.

### 7.3 The brief conflates two mechanisms; there is a second arm that separates them, and it was not offered

D3's stated kill criterion is about **A device-load issue counts**. The §1.1
sizing is about **A DRAM bytes**. `BN = 64 → 128` at `wn = 1` moves both at
once, and also moves threadgroup memory and register pressure (D5). It cannot
attribute.

The separating arm — call it **G2** — is `bm = 64, bn = 128, wm = 4, wn = 2`
(256 threads/TG):

* `grid.x` halves exactly as in G1, so the **inter-TG A byte** reduction is
  identical;
* `SN = BN/WN = 64` is unchanged, so `TN = 4` is unchanged and the per-thread
  accumulator count does **not** rise — D5's spill risk disappears;
* `n_reads = (32·BN)/(WM·WN·32)` returns to 16, so `kSrcBytes` stays 16 and the
  **D6 wide-load regression never arises** — no loader repair needed;
* but with `WN = 2` the two simdgroups own different column halves and each
  issues its own A loads, so the **A issue count per output element is flat** —
  G2 fails D3's stated criterion while delivering D3's byte saving.

So **G1 (this assignment) tests the issue-count mechanism; G2 tests the
DRAM-byte mechanism.** If G1 is positive and G2 is null, the win is issue-rate.
If both are positive and equal, it is bytes and G2 is the cheaper,
lower-risk implementation. If G1 is null and G2 positive, D5's register pressure
ate the win and N-2 is wrong to forbid a retry — the brief's N-2 forbids
`BM = 32` (correctly, it leaves the expert-aligned envelope) but never considers
`WN = 2`, which stays inside it: `expert_aligned` at `quantized.cpp:1403-1406`
admits `wn == 2` explicitly.

I did **not** run G2 — it is outside this assignment. It is a one-line variant
on the same switch and is recorded here as the highest-value follow-up.

### 7.4 `nax_safety_rig.sh` was validating a kernel variant that never ships

Recorded at §1 D7. The rig compiled without `DARKBLOOM_SWIGLU_REGLOCAL` or
`DARKBLOOM_BSEARCH_HOIST`, while `jit_kernels.cpp:1167,1182` emits both
unconditionally into every `_nax` compile. Every rig PASS recorded before this
session validated a variant the runtime never builds. Fixed in this branch; the
fix is research-only and not part of the submitted surface.

### 7.5 One thing the brief got exactly right

`GATHER_GEMM_REGIME_DESIGN.md` §2.1 — *"only arms that reduce per-TG resource
use can move the number, and this arm increases it"* — is, as the brief says,
the strongest argument against this assignment, and D5 confirms the increase is
real and measured (9,232 B → 18,448 B of threadgroup memory; per-thread
accumulator floats 32 → 64). The brief was right to demand it be addressed and
right to refuse to hand-wave it. The answer is that this arm is not trying to
create intra-TG overlap — it is trying to delete DRAM traffic that no amount of
overlap can hide — but the resource increase is a genuine, unresolved risk and
it is exactly what §6's A1-negative branch is for.
