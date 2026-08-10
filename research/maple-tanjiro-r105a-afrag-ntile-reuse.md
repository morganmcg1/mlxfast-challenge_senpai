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

_(filled in below as it lands)_

---

## 4. Stage 2 — receipt ladder

_(filled in below as receipts land)_

---

## 5. Verdict

_(pending Stage 2)_

---

## 6. Mechanism attribution plan

_(pending Stage 2)_

---

## 7. Where the brief and the round-105 advisor note are wrong

_(see §1 D6 for the first, largest one; the sizing refutation follows)_
