# 105-A — A-fragment N-tile reuse in `fp_gather_qmm_rhs_expert_nax` (BN 64 → 128)

**Assignment:** `maple-r105-a-afrag-ntile-reuse`, revision `r105-a-rev2`, PR #592
**Base:** `5f7861c0981278929c3ef43d54a6d5bca10a8659` (rev2; rev1 was
`bad6941c8d5a9294108eb65f91e3d0cb62e0b28c`, whose submission channel was closed —
§4.1)
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

**In rev1 that ladder could not be started at all.**
`senpai/submit-official.sh` refused every submission from the rev1 base, because
`origin/main` was an *ancestor* of `BASE_SHA` and the script requires their
submitted snapshots to be identical. The advisor re-based the assignment onto
`5f7861c0`, which resolved it (§4.1a), and the ladder is now running against
`origin/main = 1bc1c895`.

**The most valuable thing the ladder has produced so far is not about this
kernel at all.** The two A0 control rungs are the first same-code ranked
replicate pair in the campaign's public history, and they show the official
instrument's within-tree per-receipt σ on candidate prefill is **0.190 ms
(0.197 %)** — about **10× tighter** than the 1,208-receipt cross-submission
spread implies. Every power calculation in this campaign that inferred σ from
that public spread, including my own §4.2, overestimated it by an order of
magnitude. See **§4.4.1**.

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

### 4.1a Resolved in rev2

The advisor took option 2. Revision `r105-a-rev2` records
`BASE_SHA = 5f7861c0981278929c3ef43d54a6d5bca10a8659`, this branch was rebased
onto it, and the wrapper now accepts the candidate. Every receipt below was
dispatched with exactly this command line, changing only the note file:

```bash
bash senpai/submit-official.sh 1bc1c8954147c9e322aad1f3b80bd9fa3c0888d7 \
  --note-file research/r105a-notes/<ARM>.md
```

Argument 1 is the recorded `origin/main` SHA, verbatim, for every arm. It is not
the candidate commit, not the PR head, and not the advisor branch SHA.

### 4.1b The channel's real throughput, and why it bounds the ladder

The ladder's cost is not compute — it is ranked receipts, and the channel that
issues them is shared and doubly limited. Both limits were measured, not assumed:

1. **One in-flight submission per account.** The `morganmcg1` account carries
   every Senpai student's submissions, so a rung waits behind whatever sibling
   currently holds the slot. Receipts must therefore be attributed by
   `submissionCommitSha` / `officialMetrics.commit`, never by `solverUsername`.
   A ranked cycle takes roughly 25 minutes, so the *ceiling* is ~2.4
   receipts/hour for all students combined.
2. **Five `mlxfast submit` attempts per clock hour, also per account.** This one
   cost me a handoff. At 04:52:03Z my watcher saw the holder go terminal and
   submitted 0 s later — the fastest handoff available — and was refused with
   `Rate limit reached. Try again in 472 seconds`. My own rung had spent *zero*
   attempts in that hour; the budget had been consumed elsewhere on the shared
   account. The reset delay pointed exactly at the top of the next clock hour,
   so the window is wall-clock aligned, not a rolling per-caller window.

The consequence for the design is concrete. A refused attempt creates no
submission, so it is a wait, not a failure — but the two limits compose badly: an
agent can win the in-flight slot and still be unable to use it, and by the time
the rate window reopens a sibling may hold the slot again. Between 04:29Z and
05:00Z the channel therefore issued me nothing at all despite my being first in
line.

So the honest planning number is **not** the eight slots §4.3 assumed. It is
"however many receipts arrive before the turn ends", and the ladder has to stay
decidable at every prefix. That is the reason the revised rule in §4.4.2 is
indexed by the dof actually in hand and the reason slot 5 is a *control*: a
ladder that only becomes interpretable at receipt 8 is a ladder that reports
nothing if the channel yields 5.

`research/r105a-dispatch.sh` encodes both limits — it watches the current holder
by id (14 KB/poll against a 17 MB feed read, because the feed fetch itself is
long enough to lose the handoff), waits out a rate refusal without charging it
against the rung's attempt cap, and re-checks the slot afterwards.

**One more trap, worth recording because it silently destroys a receipt.** At
05:00:16Z the retry submitted A2-1 successfully — and my own automation then
declared failure and exited, leaving a live ranked run with nobody watching it.
`mlxfast submit` emits SGR colour codes **even when its stdout is a pipe**, so
the id line is not `submission  <uuid>`; on the wire it is

```text
ESC[2m submission ESC[22m   <uuid>
```

and a `^submission` anchor can never match it. The id was recoverable from the
job log this once, but the failure mode is nasty in exactly the way that matters
here: the expensive, rate-limited, once-per-25-minutes action *succeeded*, and
the cheap string parse afterwards is what threw the result away. The parse now
strips CSI sequences, and — because a queued receipt that nobody watches is a
wasted ranked cycle — it will not fall through to any failure path while the CLI
is still reporting `Submission queued`: it recovers the first UUID-shaped token
from the output instead. Verified against the captured bytes of the real 05:00Z
output, not against a mock of it.


### 4.2 Instrument calibration — done before reading any treatment receipt

Stage 1 set the ship bar at **1.35 ms of prefill wall** and assumed a
per-receipt noise of about 0.16 % of score. Neither number had ever been
measured, so before spending treatment receipts I calibrated the ranked channel
from the public benchmark history: 1,208 receipts that passed correctness, all
sharing one `weights_hash`. Scripts: `research/r105a-calibrate.py` and
`research/r105a-echo-test.py`.

**The campaign has never measured its own instrument.** Grouping those 1,208
receipts by `(harness_hash, weights_hash, commit)` yields **1,208 groups of size
one — zero same-code replicates**. The archive is deduplicated byte-identically,
so no candidate has ever been measured twice. Every speedup ever published on
this benchmark, including every promotion decision, rests on a single unreplicated
paired measurement whose noise was unknown. The A0 rungs of this ladder are, as
far as the public record shows, the first same-code replicates ever dispatched.

**The pinned baseline is a free 1,208-fold replicate.** The paired baseline is
the same code in every receipt, so its spread *is* the instrument noise:

| channel | mean | SD | relative SD |
|---|---|---|---|
| baseline prefill wall | 190.674 ms | 3.691 ms | **1.936 %** |
| baseline decode per token | 13.8548 ms | 0.03413 ms | **0.246 %** |

The prefill axis is nearly **8× noisier in relative terms** than the decode axis.

**That noise is white — there is no session structure for pairing to cancel.**
A variogram of the baseline series over elapsed gap is flat from under 15
minutes to 30 days: σ(0–15 min) = 1.911 % against σ(total) = 1.926 % for
prefill, and 0.251 % against 0.246 % for decode. A level shift between harness
eras or a slow thermal drift would make short-gap pairs much tighter than
long-gap pairs. They are identical, so the variation is per-run, not per-era.

Consistently, the within-receipt covariance between a candidate and its own
baseline — which estimates the shared session factor directly, because candidate
code effects cannot enter the fixed baseline channel — is **≤ 0 on both axes**:
σ_session = 0.000 % against σ_run = 1.926 % (prefill) and 0.246 % (decode). The
point estimate says the paired ratio cancels nothing and therefore *doubles* the
variance. This estimator is noisy (candidate SD is 18.5 % on prefill, so the
2-SE upper bound on σ_session is about 1.4 %), which is precisely what the A0
replicates resolve.

**The seed prefill is charged to decode, but as an independent execution.** The
Stage-1 price f = 0.38 %/ms assumed `dec = T + 4·pre`. The harness confirms the
level: `LagunaRuntimeLocalIterate.swift:577-582` charges "prompt-specific setup,
seed prefill, cache materialization, and checked token steps" to
`decode_seconds_per_token`, and it logs `includes_seed_prefill=true`. But
regressing the baseline's decode metric on its own prefill metric across 1,208
receipts gives

```
d(base_dec)/d(base_pre) = 0.587 +/- 0.135     [4.0 if the same measurement is reused, 0.0 if prefill-free]
z vs 4.0 = -25.2      z vs 0.0 = +4.3
```

so the decode phase runs its **own** seed prefill behind its own cool gate
(`:768-772`) rather than reusing the timed prefill number. Both facts hold at
once: the decode metric's *level* contains a 512-token prefill, so a genuine
prefill saving is still worth `1/128` ms per step and **f = 0.3796 %/ms stands**;
but the decode metric's *noise* contains an independent draw of prefill noise,
4 × 1.936 % × pre, which is 0.0288 ms of its 0.0341 ms SD — about 72 % of the
decode variance is seed-prefill noise, leaving a pure-step noise near 0.148 %.

The noise is also not an outlier artifact that a median could dodge: for the
baseline prefill wall, SD = 3.691 ms, 1.4826·MAD = 2.989 ms and IQR/1.349 =
4.771 ms, with p1 = 186.2 ms and p99 = 198.7 ms. The distribution is
right-skewed but its robust core is still ~1.6 %. The decode metric is clean
(SD 0.0341, 1.4826·MAD 0.0346, IQR/1.349 0.0355).

**Resulting resolution, at this arm's operating point** (A0-1: 96.031 ms
prefill wall, 4.1617 ms pure step, f = 0.3796 %/ms), per one ms of prefill wall:

| endpoint | signal | noise | SNR per ms | SE of one receipt |
|---|---|---|---|---|
| candidate prefill | 1.041 %/ms | 1.936 % | 0.538 | 1.86 ms |
| candidate decode | 0.159 %/ms | 0.323 % | 0.495 | 2.02 ms |
| both, inverse-variance | — | — | **0.731** | **1.37 ms** |
| `prefill_speedup` (paired) | 1.041 %/ms | 2.738 % | 0.380 | 2.63 ms |
| `officialScore` (paired) | 0.3796 %/ms | 0.750 % | 0.506 | 1.98 ms |

Two consequences, both preregistered below. First, the **published paired
speedups are the worst available endpoints** — pairing against a baseline whose
noise does not cancel adds a factor √2 — so the analysis uses the candidate-only
channels and treats A0 as the reference level. Second, the best achievable
per-receipt SE on a prefill change is **1.37 ms, which is the size of the entire
1.35 ms ship bar.** With the 3/2/2 allocation the arm-versus-A0 contrast has
SE ≈ 1.37·√(1/2+1/3) = **1.25 ms**. Excluding the bar one-sided at 95 % would
need a point estimate below −0.71 ms, and declaring a win would need +2.06 ms.
**An eight-receipt ladder cannot resolve a 1.35 ms prefill effect on this
instrument;** reaching SE ≈ 0.5 ms needs roughly 15 receipts per arm.

### 4.3 Preregistered analysis plan

Written before the first treatment receipt was readable, and amended once, here,
after the calibration above and an independent methodological review.

**Endpoint.** Per receipt, estimate the prefill wall saving ΔP in ms from the
candidate channels only: `P = 512000·prefill_seconds_per_token` and the decode
echo `128·(dec − dec_ref)`, combined by inverse variance. Contrast **arm means
against the A0 mean**, never against 1.0 and never against the paired baseline,
whose session-to-session level moves by ±3.7 ms. Report the decode/prefill
consistency check on arm means; excess decode movement means a decode-side
effect, not a prefill effect.

**Allocation and order.** Keep 3 A0 / 2 A1 / 2 A2 — for two treatments against
one shared control the variance-optimal control count is n_t·√2 ≈ 3. Fix the
rev2 ladder's drift imbalance: the original order put A0 at slots {1,2,5} and
treatments at mean slot 5.0, so any linear drift in the pair asymmetry loaded
entirely onto the treatment contrasts. Slots 1–2 are already spent on A0, so the
remainder is interleaved to equalise mean slot between the two treatments:

| slot | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 |
|---|---|---|---|---|---|---|---|---|
| arm | A0-1 | A0-2 | A2-1 | A1-1 | A1-2 | A2-2 | A0-3 | adaptive |

Mean slot: A0 3.33, A1 4.5, A2 4.5 — both treatments equally offset, so a linear
drift cancels between them. Slot 8 is preregistered adaptive: the combined arm
(variant 6, both routed shapes at bn=128) if both treatments clear the bar,
because that is the variant that would actually ship and tile effects need not be
additive; otherwise a third replicate of an inconclusive arm; otherwise unused.

**No ship decision from a single receipt**, and no post-hoc selection of the
better-looking arm as if it had been the only one tested.

**Diagnostics, all of which must pass or the verdict is "invalid".**
D1: the two A0 replicates agree within 3σ√2 of the calibrated per-receipt σ.
D2: pooled within-arm SD ≤ 1.6× the calibrated σ.
D3: no receipt's paired baseline is a >2σ outlier against the 1,208-receipt
baseline distribution, and no monotone trend in it across slots.
D4: the pure-step contrast (arm versus A0) is within ±2 SE of zero, since these
arms touch only a multi-row prefill tile.
D5: the modified kernel is reachable on ranked hardware.

**Verdict rule.** WIN: Δ̂ ≥ 1.35 ms **and** Δ̂ − 1.645·SE > 0 **and** n ≥ 2 **and**
diagnostics pass; if both arms win, shipping is contingent on the slot-8 combined
receipt. NULL with the bar excluded: Δ̂ + 1.645·SE < 1.35 ms. NULL and
underpowered: anything between. Δ̂ < −1.645·SE is reported as a regression, not
folded into "null". Given §4.2's arithmetic the underpowered branch is the
*expected* outcome, and saying so in advance is the point of writing it down.

**Honesty limits.** With n = (3,2,2) the assumption-free permutation floor is
one-sided p = 0.10, attainable only if both treatment receipts beat all three
A0 receipts. Any interval quoted below is explicitly conditional on the
calibrated σ from §4.2; the pooled within-arm SD at 4 dof has a ~35 % CV and is
reported only as a cross-check.

### 4.3.1 Sequential stopping rule — recorded before the first treatment receipt

§4.2 changes what the eight-slot ladder is worth, so I am fixing the stopping
rule now, while A2-1 is committed but unsubmitted and no treatment receipt
exists to be read. The ladder was sized before the instrument was calibrated.
It cannot resolve the 1.35 ms bar at any allocation I can afford: the contrast
SE at (3,2,2) is 1.25 ms, so a "win" verdict would require an observed
Δ̂ ≥ 2.06 ms — larger than the effect the brief predicts. Spending slots 5–8 to
move the SE from ≈2.0 ms to ≈1.25 ms buys a resolution that is still coarser
than the hypothesis. That is not a good use of four ranked receipts, so the
remaining slots are conditional on the first two treatment receipts:

- **Slots 1–4 are unconditional**: A0-1, A0-2, A2-1, A1-1. Four receipts buy
  the one thing the campaign has never had — a same-code replicate pair, hence
  a *measured* σ — plus a single-receipt screen on each treatment arm at
  SE ≈ 2.0 ms per contrast.
- **Continue to slots 5–8 only if the screen is suggestive**: some arm shows
  \|Δ̂\| ≥ 3 ms (≈1.5 SE of the single-receipt contrast) on the combined
  endpoint, in either direction. A large win is worth confirming; a large
  apparent regression is worth confirming too, because a regression verdict is
  actionable at this resolution even when a win is not.
- **Stop at slot 4 otherwise** and report NULL-and-underpowered with the
  receipt count the bar actually needs. An effect the instrument cannot see is
  not made visible by three more receipts, and reporting the shortfall is more
  useful to the advisor than burning the budget to restate it with one extra
  digit.

This is a deviation from §4.3's fixed eight-slot allocation and it is a
deliberate one. It costs the drift-balanced ordering (A0 mean slot 1.5 versus
A1 4.0 and A2 3.0 under the truncated ladder, against 3.33/4.5/4.5 under the
full one), which §4.2's variogram says is harmless: the noise is white from
15 minutes to 30 days, so slot position carries no signal to be confounded
with. It is recorded here in advance precisely so it cannot be mistaken for a
post-hoc stop after an unflattering number.

### 4.3.2 Where the measurement overturned the analysis review

The plan above was reviewed by a frontier statistics agent before calibration.
Most of its advice survived contact with the data and is adopted: contrast every
arm against A0 rather than against 1.0; keep the 3/2/2 allocation (optimal at
n₀ = n_t·√k for k = 2 shared-control arms); treat n ≤ 3 as metrology against an
offline-calibrated σ rather than as small-sample inference; report the
permutation floor of one-sided p = 0.10 as the assumption-free limit; never ship
on n = 1; verify reachability and bit-exactness before spending a receipt; and
reserve the adaptive slot for the *combined* arm (variant 6) if both treatments
win, because tile-shape effects on the two projections need not be additive.

Two of its conclusions were **wrong for this instrument**, and only measurement
could tell:

1. It called the candidate-only endpoint "clearly wrong" because of session
   common mode, and put pairing ahead of it "on a shared box over a multi-hour
   session, near-certain". Measured σ_session is **≤ 0** on both axes (§4.2), so
   pairing here doubles variance instead of halving it. The paired
   `prefill_speedup` is in fact the *worst* of the five endpoints in the table.
2. Its Q2 worked example guessed the channel split as v_p ≈ 0.5 %, v_d ≈ 0.12 %
   and concluded `officialScore` beats the prefill channel by ~1.55×. The true
   split is v_p = 1.94 %, v_d = 0.25 %, and `officialScore` (SE 1.98 ms) loses
   to the inverse-variance combination of the two candidate channels
   (SE 1.37 ms) — while both are dominated by the fact that the bar and the
   per-receipt SE are the same size, which the review's power tables missed
   entirely because they inherited the unmeasured σ = 0.16 % prior. Its
   "comfortable regime, bar/σ₁ ≈ 3.2–4.5" is really bar/σ₁ ≈ 1.0.

The review's own framing is what makes this recoverable: it said the correct use
of the receipts is metrology with a calibrated instrument. Calibrating the
instrument is what showed the ladder is too short.

### 4.4 Receipts

| arm | variant | submission | commit | prefill wall | pure step | `officialScore` | correctness |
|---|---|---|---|---|---|---|---|
| A0-1 | 5 (default) | `69fb349b` | `51b6c142` | 96.031 ms | 4.16167 ms | 2.57065175986034 | pass, `max_abs_diff=0`, 1344 steps, GPQA 9/9 |
| A0-2 | 5 (default) | `c7930407` | `fdeb4561` | 96.299 ms | 4.16234 ms | 2.56976261057539 | pass, `max_abs_diff=0`, 1344 steps, GPQA 9/9 |
| A2-1 | 8 (down-proj bn=128) | `288c7025` | `b4c9b4e4` | 97.183 ms | 4.17110 ms | 2.55214102802847 | pass, `max_abs_diff=0`, 1344 steps, GPQA **8/9** |
| A0-3 | 5 (default) | `d4a86ffd` | `24ad1d2e` | 96.117 ms | 4.18290 ms | 2.57182973424995 | pass, `max_abs_diff=0`, 1344 steps, GPQA 9/9 |

Receipt budget consumed: **4 / 8**. The A0 rungs are bit-identical to each other
by construction — the only difference between them is a comment — so
`max_abs_diff = 0` is the falsifiable prediction for those, and any nonzero
value would refute the "inert by default" claim in §0. Every rung so far passed
both `0.95` floors, so the `rejected` status on each is a *ranking* verdict
(none beat the current best) and not a correctness or floor failure.

**Correction.** An earlier version of this paragraph said "all arms are
bit-identical by construction". That is wrong for the treatment arms and I
should not have written it. A0 rungs differ only in a comment, but changing the
`bn` tile changes the reduction geometry of the routed GEMM, so the
accumulation order changes and low-order bits of the output may differ from
variant 5. The correctness gate is therefore a real gate for A1 and A2 rather
than a formality, and `max_abs_diff = 0` on the checked teacher-forced tokens is
an empirical result for them, not a guarantee. §4.4.4 records where this bit.

### 4.4.1 The replicate pair overturns §4.2's resolution table

A0-1 and A0-2 are the first same-code ranked replicate pair in this campaign's
public history. §4.2 had to *assume* the per-receipt σ from the 1,208-receipt
cross-submission baseline spread, because nobody had ever paid for two receipts
of one tree. The pair says that assumption was wrong by an order of magnitude.

| channel | A0-1 | A0-2 | relative Δ | σ̂₁ = \|Δ\|/√2 | §4.2 assumed σ₁ |
|---|---|---|---|---|---|
| candidate prefill `pre` | 1.87560791e-4 | 1.88084229e-4 | **+0.279 %** | **0.197 %** = 0.190 ms | 1.936 % = 1.86 ms |
| candidate decode `dec` | 4.91191178e-3 | 4.91467741e-3 | +0.0563 % | 0.0398 % = 0.250 ms-eq | 0.246 % |
| pure step (decode less prefill) | 4.16167 ms | 4.16234 ms | +0.0161 % | 0.0114 % | — |
| baseline prefill | 3.65822592e-4 | 3.67981527e-4 | +0.588 % | 0.416 % | 1.936 % |
| baseline decode | 1.38441214e-2 | 1.38312409e-2 | −0.0931 % | 0.0658 % | 0.246 % |
| `prefill_speedup` | 1.95042146 | 1.95647200 | +0.310 % | 0.219 % | — |
| `decode_speedup` | 2.81847925 | 2.81427238 | −0.1493 % | 0.106 % | — |
| `officialScore` | 2.57065176 | 2.56976261 | −0.0346 % | 0.0245 % | — |

Four things follow, and the third is the one that matters.

1. **The instrument is ~10× tighter than assumed on its scored axis.** Candidate
   prefill moved 0.279 % between two independent official sessions of the same
   bytes. Under σ₁ = 1.936 % the difference of two receipts has SD 2.74 %, so
   P(\|Δ\| ≤ 0.279 %) = 0.081; the candidate decode channel independently gives
   0.129. Jointly ≈1 % on the two candidate channels alone. Luck is possible but
   strongly disfavoured, and the same conclusion falls out of all four channels
   agreeing at once.
2. **The historical spread is between-session/between-host, not within-tree.**
   §4.2's variogram found white noise from 15 minutes to 30 days and I read that
   as "no structure to exploit". The correct reading is that the public feed is
   not ordered by host or session, so a time-domain variogram *cannot* see a
   session/host component — it smears it into the white floor. Two back-to-back
   submissions do not sample that component, which is exactly why they agree.
   This is a real limit on the calibration method, not a lucky draw.
3. **The ladder is overpowered, not underpowered.** §4.3 combines the prefill and
   decode channels by inverse variance, but the pair shows they are **not
   independent**: both moved in the same direction by nearly the same amount
   (+0.268 ms and +0.354 ms of prefill-wall equivalent), and their difference —
   the pure-step term — moved only 0.086 ms. The decode channel is largely the
   same prefill wall measured again, so an independence-assuming combination
   (0.151 ms) understates the SE. I therefore use the **tighter single channel**,
   σ̂₁ = **0.190 ms**. A single treatment receipt against the two-receipt A0 mean
   then has SE = 0.190·√(1 + 1/2) = **0.233 ms**, and the 1.35 ms bar sits
   **5.8 SE** away. §4.3.1 stopped the ladder early because the SE was believed
   to be 1.25–2.0 ms and the bar unreachable. It is reachable at n = 1 per arm.
4. **Pairing is still the wrong endpoint, for a new reason.** §4.3 rejected the
   paired `prefill_speedup` because §4.2 measured σ_session ≤ 0. The pair shows
   there *is* positive common mode — Δln(speedup) = 0.310 % = 0.588 − 0.279
   exactly, i.e. the two levels moved the same way — but the baseline channel is
   noisier than the candidate channel (0.416 % vs 0.197 %), so dividing by it
   *adds* variance. The preregistered candidate-only endpoint survives; §4.2's
   stated reason for it does not.

The honest limit on all of this is dof. σ̂₁ rests on 1 degree of freedom, whose
CV is 76 %; the one-sided 95 % upper bound multiplies σ̂ by √(1/χ²₀.₀₅,₁) = 15.9,
giving σ₁ ≤ 3.0 ms — which does not exclude the §4.2 value on its own. The point
estimate plus the joint-improbability argument is the evidence; the interval at
1 dof is nearly vacuous. A third A0 receipt takes the multiplier from 15.9 to
4.4, which is why it is promoted in the revised plan below rather than left at
slot 7.

I am not deleting §4.2 or §4.3.1. They were the best available reasoning before
two receipts existed, and the failure mode they walked into — trusting a
cross-submission spread as a within-tree σ — is the most transferable thing in
this report.

### 4.4.2 Revised stopping rule — recorded while A2-1 is still unsubmitted

§4.3.1's screen threshold (\|Δ̂\| ≥ 3 ms) was written in absolute ms under
σ₁ = 1.37 ms. At the measured σ it is ~16 SE and would discard a true 1.35 ms
win as "not suggestive". Restating it in SE units is not optional, and it has to
happen now: A2-1 is committed and its note is written, but nothing has been
submitted, so no treatment number can be influencing this. Timestamp is the
commit that carries this paragraph.

**Binding decision rule.** Δ̂ = prefill-wall saving of the arm mean against the
A0 mean on the candidate-prefill channel `P = 512000·pre`, positive = faster,
with the decode channel reported as a consistency check rather than pooled in
(§4.4.1 point 3). Because σ is *estimated*, the interval uses Student-t at the
dof actually available when the call is made, not z:

| receipts | ν | SE | t₀.₉₅,ν | WIN needs Δ̂ > | bar-excluded needs Δ̂ < |
|---|---|---|---|---|---|
| 2 A0, 1 arm | 1 | 0.233 ms | 6.31 | 2.82 ms | −0.12 ms — **unattainable** |
| 3 A0, 1 arm | 2 | 0.219 ms | 2.92 | 1.99 ms | 0.71 ms |
| 3 A0, 2 arm | 3 | 0.173 ms | 2.35 | 1.76 ms | 0.94 ms |

The ν = 1 row is why slot 5 has to be A0-3 and not a treatment replicate: with a
single degree of freedom the t multiplier is 6.31, the bar-excluded branch is
arithmetically unreachable, and *no* observed Δ̂ could produce a null verdict —
only a win at an implausible 2.82 ms. One more control receipt turns an
undecidable ladder into a decidable one.

- **WIN**: Δ̂ − t₀.₉₅,ν·SE > 1.35 ms, with n ≥ 2 for that arm and all of D1–D5
  passing. A single receipt never ships, unchanged from §4.3.
- **NULL, bar excluded**: Δ̂ + t₀.₉₅,ν·SE < 1.35 ms.
- **REGRESSION**: Δ̂ + t₀.₉₅,ν·SE < 0.
- **NULL, underpowered**: anything else. At ν ≥ 2 this window is narrow, which
  is the whole change from §4.3.1.

**Revised slot plan.** A0-3 is promoted ahead of A1-1, because lifting ν from 1
to 2 shrinks every threshold above by more than any treatment receipt does:

| slot | 3 | 4 | 5 | 6 | 7 | 8 |
|---|---|---|---|---|---|---|
| arm | A2-1 | A0-3 | A1-1 | replicate of the larger \|Δ̂\| | replicate of the other | combined (variant 6) or 3rd replicate |

- Any arm with Δ̂ > 2·SE gets a replicate before it is called anything. n = 1 is
  a screen, never a decision.
- Slot 8 stays as §4.3 preregistered it: variant 6 if both treatments clear the
  bar at n ≥ 2, since the two projections' tile effects need not be additive;
  otherwise a third replicate of the leader.
- Mean slot under this plan: A0 {1,2,4} → 2.33, A2 {3,6 or 7}, A1 {5,7 or 6} —
  the treatments stay within two slots of each other, and A2-1 is now *bracketed*
  in time by controls (1, 2 before it; 4 after), so a linear session drift over
  the ladder is visible in the controls instead of loading onto the first
  treatment.
- Stopping early is still allowed, but only in the direction §4.3.1 could not
  reach: if both treatments are bar-excluded at ν = 2 the remaining slots buy
  nothing and the verdict is NULL-with-the-bar-excluded, which is a *stronger*
  result than the underpowered null §4.3.1 expected to report.

**Why the control moves ahead of the second treatment.** §4.1b measured the
channel at ~2.4 receipts/hour shared across all students, with a rate window that
can idle it entirely; the eight slots §4.3 assumed are not a budget I control. So
the ordering question is which *prefix* is most decidable, and the two candidate
orders reach the same 5-receipt state by different routes:

| receipts in hand | order A2-1, A1-1, A0-3 | order A2-1, A0-3, A1-1 |
|---|---|---|
| 3 | ν = 1 — no null verdict reachable | same |
| 4 | still ν = 1 for both arms — **nothing decidable** | ν = 2 for A2 — **A2 decidable** |
| 5 | ν = 2, both arms decidable | ν = 2, both arms decidable |

Promoting the control is therefore free at the end of the ladder and strictly
better at every prefix, so the ladder now returns a real verdict on one arm even
if the channel yields only four receipts. Recorded at 04:57Z, with A2-1 queued
but unread and A1-1 not yet built: this reorder cannot be a response to any
treatment number.
- Stopping early is still allowed, but only in the direction §4.3.1 could not
  reach: if both treatments are bar-excluded at ν = 2 the remaining slots buy
  nothing and the verdict is NULL-with-the-bar-excluded, which is a *stronger*
  result than the underpowered null §4.3.1 expected to report.

### 4.4.3 Auditing the rule before the data arrives

The decision rule is only worth preregistering if the code that executes it does
what the prose says. I tested `analyse()` against synthetic prefill walls before
A2-1's receipt was readable (`research/r105a-analyse-selftest.py`, all checks
pass). Three things came out of it, and two are corrections to my own work.

**A latent preregistration violation, fixed pre-data.** `analyse()` set the
per-receipt σ̂ to `min(σ_prefill, σ_decode)`. Δ̂ is measured on the candidate
prefill channel, so its standard error has to come from that same channel.
Taking whichever channel happened to be tighter would have let the
false-positive rate float with the noise draw, and because the decode channel is
a *correlated re-measurement of the same 512-token seed prefill* (§4.4.1) it is
not an independent second estimate that could be legitimately pooled either. On
the two A0 receipts in hand `min()` happens to select prefill (0.1895 vs 0.2503),
so **no number published anywhere in this log changes** — but the loophole is
closed while it still costs nothing to close, rather than after a treatment
number could make the choice look motivated. σ̂ is now `σ_prefill`
unconditionally; the decode channel stays in the output as a consistency check.

**The §4.4.2 SE table is prospective, not the analysis.** I wrote that table by
pinning σ̂ = 0.190 ms, the pair estimate. The code does not and should not do
that: it re-estimates σ̂ from every A0 receipt in hand. These disagree, and my
first version of the self-test failed precisely because I had conflated them —
placing a synthetic third control exactly at the pair mean shrinks σ̂ to
`|a−b|/2` = 0.134 ms and the SE to 0.155 ms, not the tabulated 0.219 ms. So the
table is a *planning* device answering "what effect could this design detect if
σ̂ holds", and the realized interval at analysis time is whatever the controls
say. Both properties are now asserted separately so neither can be mistaken for
the other.

**Adding A0-3 buys degrees of freedom, not precision.** This is the part I had
wrong in spirit. σ̂ at these dof is itself wildly unstable: the self-test's
spread-out third control pushed σ̂ *up* to 0.267 ms, giving SE 0.308 ms — worse
than the ν = 1 SE of 0.232 ms. A third control therefore does not reliably
tighten the SE at all. What it reliably does is collapse t₀.₉₅ from 6.31 to 2.92,
and that is where the entire gain lives. Sweeping plausible σ̂₃:

| σ̂₃ (ms) | SE at n₀=3, n=1 | WIN needs Δ̂ > |
|---|---|---|
| 0.134 (third control at the mean) | 0.155 | 1.80 ms |
| 0.190 (σ̂ holds at the pair value) | 0.219 | 1.99 ms |
| 0.267 (third control disperses σ̂) | 0.308 | 2.25 ms |

The WIN threshold lands in 1.8–2.3 ms across that whole range, against 2.82 ms
at ν = 1. So the §4.4.2 conclusion — promote A0-3 ahead of A1-1 because it makes
A2 decidable at four receipts — survives, but for the t reason rather than the
σ̂ reason, and the threshold I will actually face is not knowable until A0-3
lands. I am recording the range instead of a single number so that whichever
value materialises cannot be presented as the one I expected.

**Verdict labels.** Two branches were unreachable as written. A large positive
Δ̂ at n = 1 fell through to `NULL-underpowered`, which would have been an
actively misleading label for a strong signal that merely lacks a replicate; it
is now `WIN-pending-replicate`, and `verdict_is_shippable` still requires
n ≥ 2 no matter how large the effect (asserted with a 50 ms synthetic effect).
§4.4.2's "any arm with Δ̂ > 2·SE gets a replicate before being called anything"
was prose with no code behind it and is now the explicit
`PROMISING-needs-replicate` branch. One consequence worth stating: when σ̂ is
small, `NULL-underpowered` becomes *unreachable* — the interval cannot
simultaneously reach the bar and keep Δ̂ under 2·SE — so an underpowered null is
a symptom of a loose σ̂, not an inevitable outcome of a short ladder.

### 4.4.4 A2 (down-projection only, variant 8) is slower on both axes

A2-1 landed at 05:24:04Z. It is not a win and not an underpowered null; it is a
measurable slowdown, and the ladder returns that verdict from a single treatment
receipt.

| channel | A0 mean (n=2) | A2-1 | Δ̂ (control − arm) | σ̂₁ | SE | z |
|---|---|---|---|---|---|---|
| prefill wall | 96.16512 ms | 97.18342 ms | **−1.01829 ms** (−1.059 %) | 0.18950 | 0.23209 | **−4.39** |
| pure step | 4.162005 ms | 4.171095 ms | **−0.00909 ms** (−0.218 %) | 0.000475 | 0.000582 | **−15.6** |

Applying §4.4.2 at ν = 1, t₀.₉₅ = 6.314: CI90 = [−2.484, **+0.447**]. The upper
bound is below the 1.35 ms bar, so **A2 is `NULL-bar-excluded`** — a 1.35 ms
prefill benefit from putting the down projection on bn=128 is ruled out at
one-sided 95 %. It is not yet a *formal* regression, which needs Δ̂ + t·SE < 0,
i.e. Δ̂ < −1.466 ms at this ν.

I owe a correction to §4.4.2 here. That table says bar-exclusion at ν = 1
"needs Δ̂ < −0.12 ms — unattainable". The arithmetic was right and the word was
wrong: the condition is unattainable only for an arm that *helps*, and it is
perfectly attainable for an arm that hurts. A2 met it comfortably. What ν = 1
genuinely cannot do is declare a win.

**The step channel is the more interesting number.** I expected the bm128 staged
path to be prefill-shaped only, so the honest prediction was that the pure step
would not move. It moved at z = −15.6. That is not archive noise: the A0 rungs
differ only by a comment and their step channel scatters by 0.00048 ms, roughly
nineteen times smaller than A2-1's shift. So flipping the routed down projection
to bn=128 reaches the single-row decode GEMM as well — either the selector is
consulted on decode-shaped calls too, or the change perturbs something global
such as pipeline/kernel-cache residency. Since decode carries 75 % of the score
weight, a 0.218 % step regression costs more than the 1.06 % prefill regression
does: `decode_speedup` fell 0.439 % and `prefill_speedup` fell 1.490 %, for a
0.703 % `officialScore` drop (2.55214 vs the 2.57021 A0 mean).

**The GPQA 8/9 is a real observation, not a rounding artefact.** Both A0 rungs
scored 9/9; A2-1 scored 8/9 while still reporting `passed_correctness = true`,
`max_abs_diff = 0` over 1344 checked steps, and both floors passing. These are
consistent: `max_abs_diff` covers teacher-forced checked tokens, whereas the
semantic GPQA judge scores a *free* run, where a single near-tie argmax flip can
propagate. Because variant 8 changes the reduction geometry it is not bit-exact
against variant 5 (§4.4 correction), so a free-run divergence is a live
explanation; judge nondeterminism is the other. I cannot separate them from one
receipt and I am not going to claim the arm is bit-exact. It does not change the
verdict — the arm is slower on both timing axes — but it does mean a *winning*
tile change would have needed replicated GPQA evidence before I would trust it.

**Preregistered consequence for the remaining slots**, recorded now, while A1-1
is queued and unread:

- A0-3 is already in flight, and at ν = 2 (t = 2.92) A2's upper bound becomes
  −1.018 + 2.92·SE₃. For σ̂₃ anywhere near the pair value that is negative, so
  **A0-3 will likely upgrade A2 from bar-excluded to a formal regression without
  spending a treatment slot on it.** This is an unplanned dividend of the
  §4.4.2 reorder, which I justified purely on making A2 decidable.
- Slot 6 was reserved for "replicate of the larger |Δ̂|", which is A2. I am
  overriding that: replicating A2 would only harden a negative that is already
  bar-excluded and cannot change any shipping decision. Slot 6 goes to whichever
  arm is still live after A1-1.
- If A1-1 also comes back bar-excluded or negative, then both treatments are
  bar-excluded at ν ≥ 2 and §4.4.2's early-stop clause fires: the ladder stops
  with slots unspent and the verdict is NULL-with-the-bar-excluded for both
  routed shapes, the default stays at variant 5, and per §5.2 the PR is **not**
  merged for being harmless.

### 4.4.5 A0-3 lands, and it retracts the step-channel finding above

A0-3's receipt (05:45:44Z, `officialScore` 2.57182973424995) does two things.
The predicted one: A2's upper bound goes negative exactly as §4.4.4 said it
would, so **A2 is now a formal `REGRESSION`** rather than merely bar-excluded.
At n₀ = 3, σ̂ₚ = 0.13681 ms, SE = 0.15797 ms, t₀.₉₅(ν=2) = 2.920:
Δ̂ₚ = **−1.03421 ms**, CI90 = [−1.49548, **−0.57293**], z = −6.55. The dividend
arrived without spending a treatment slot, as designed.

The unpredicted one is that A0-3 **falsifies the "step channel is the more
interesting number" paragraph in §4.4.4, and I am retracting it.**

| step channel | value |
|---|---|
| A0-1 / A0-2 / A0-3 | 4.16167 / 4.16234 / **4.18290** ms |
| σ̂ from the A0-1/A0-2 pair | 0.000475 ms |
| σ̂ from all three A0 rungs | **0.012071 ms** — 25× larger |
| A0-3's distance from the pair mean | +0.0206 ms = **43 pair-σ̂** |

A0-3 is a comment-only, bit-identical rung of the same code, and it sits 43
pair-σ̂ away from its own twins on this channel. So the pair-based σ̂ was not a
measurement of the step channel's noise; it was one lucky-close draw. Recomputed
against the 3-rung control mean (4.168971 ms), A2's step delta is **−0.00212 ms**
with SE = σ̂·√(1+⅓) = 0.01394 ms, i.e. **z = −0.15**. There is no step-channel
effect. The claim that variant 8 "reaches the single-row decode GEMM" was an
artefact of a two-point variance estimate and nothing more.

This is precisely the failure mode §4.4.3 warned about — "σ̂ at these dof is
unstable and can rise" — and it rose on the one channel where I had drawn the
strongest conclusion. Two lessons I am writing down rather than rediscovering:

1. A two-point σ̂ has a 76 % coefficient of variation. A z built on it is not a
   test statistic, it is a ratio to an unknown. §4.4.1 said so about the prefill
   channel and I then went and did it anyway on the step channel, because there
   the number looked too big to worry about. Effect size does not rescue an
   unknown denominator.
2. The mechanism-plausibility argument ("the selector must be consulted on
   decode-shaped calls too") arrived *after* the number and made a noise draw
   feel explained. The prefill-only prediction was the preregistered one and it
   was right.

The prefill-channel conclusion in §4.4.4 is unaffected: it was already the
preregistered channel, its σ̂ moved only from 0.18950 to 0.13681 ms (a fall, and
within what 1→2 dof can do), and the verdict hardened rather than flipped.

A0-3 also scored GPQA 9/9, so the tally is three 9/9 controls against one 8/9
treatment. That nudges §4.4.4's two explanations apart slightly in favour of a
free-run argmax divergence over judge nondeterminism, but one treatment receipt
against three controls is not a test of the judge and I am not treating it as
one.

### 4.4.6 What the three controls say about which channel to measure on

With three same-code receipts every published channel can be given a replicate
noise, and they differ by 7×:

| channel | σ̂ (n=3) | CV |
|---|---|---|
| **`officialScore`** | 0.0010369 | **0.0403 %** |
| `decode_speedup` | 0.0032634 | 0.1158 % |
| candidate prefill wall | 0.13681 ms | 0.1423 % |
| `prefill_speedup` | 0.0038249 | 0.1959 % |
| candidate decode wall | 1.52721 ms | 0.2425 % |
| pure step | 0.012071 ms | 0.2895 % |

Two things follow, and the second was a surprise.

**The published speedups are exactly the raw ratios.** `decode_speedup` =
`baseline_decode_seconds_per_token` / `candidate_...` to 2 × 10⁻⁶, likewise
prefill, and `officialScore` = `decode_speedup`^0.75 · `prefill_speedup`^0.25 to
3 × 10⁻⁵ on all four receipts. Nothing is being robustified or re-measured
behind the scenes. (My own `nd`/`np` diagnostic columns are *not* these ratios —
they subtract the seed prefill from decode to get a pure-step speedup — and I
briefly misread that difference as evidence the service published a separate
measurement pass. It does not.)

**Yet the score is 2.5× tighter than propagating its own two factors as
independent predicts** — 0.0403 % observed against 0.0997 % propagated. The
reason is that the two scored axes are strongly **anti-correlated** across
same-code sessions: Pearson r = **−0.978** on the three controls. Every rung
that draws a high `decode_speedup` draws a low `prefill_speedup` and vice
versa. Feeding r back into the propagation gives 0.0403 %, matching the observed
0.0403 % to 0.06 % relative — so the anti-correlation is the whole explanation,
not a partial one.

I do not know the physical cause and three points cannot tell me; a shared
session-level factor that shifts the baseline's two axes in opposite directions
(measurement order, thermal ramp within the paired run) is the obvious candidate.
The consequence stands regardless of cause: **the weighted geometric mean the
organizers chose to rank on is a substantially quieter instrument than either
axis it is built from, and quieter than any wall clock I can read.** For a
prefill-side experiment this is the opposite of what I assumed in §4.3, where I
picked the candidate prefill wall precisely because it seemed the most direct
and least derived quantity. Directness and precision were not the same thing
here.

Note also that pairing does not always help: `prefill_speedup` (paired) is
*noisier* than the candidate prefill wall (unpaired), 0.1959 % against 0.1423 %,
because the baseline prefill contributes its own noise and the two prefills do
not co-vary enough to pay for it. It is only the two-axis combination that wins.

### 4.4.7 Amendment A — `officialScore` becomes the primary channel

Recorded at 05:58Z. A1-1 is queued but rate-limited to the 06:00Z hour boundary
and **its receipt does not exist yet**, so this is a preregistration and not a
post-hoc channel switch. The A2 verdict is unaffected either way — it is a
regression on both channels, z = −15.5 on score and −6.5 on prefill — so no
already-published decision changes.

The rule from §4.4.2 is unchanged in form. Only the channel changes:

- **Primary channel: `officialScore`**, Δ̂ = arm mean − control mean, maximize.
  σ̂ from the A0 controls' own score spread; SE = σ̂·√(1/n + 1/n₀); same t table
  and same ν = (n₀−1)+(n−1).
- **The bar is the same physical bar.** 1.35 ms off the shared 512-token prefill
  is worth `BAR_MS · price/100 · score` where price is the measured score
  sensitivity, 0.379103 %/ms on the controls. So
  **BAR_SCORE = 0.0131568** score points = 0.5117 % of 2.5707480. The code
  derives this rather than hardcoding it, and the self-test asserts that an arm
  sitting exactly on the millisecond bar scores exactly the score bar.
- **Secondary channel: the candidate prefill wall**, retained as a consistency
  check. The mechanism under test is prefill-shaped, so a score-channel win that
  the prefill wall contradicts (Δ̂ₚ ≤ 0) is not shippable; it downgrades to
  `PROMISING-channel-disagreement`. A prefill-wall win with a flat score is
  likewise not shippable — the score is what ranks.
- Each channel's SE comes from its own replicate spread. No pooling across
  channels, and never "whichever channel is tighter", which would let the
  false-positive rate float with the noise draw.

What this buys, at σ̂ = 0.0010369 and n₀ = 3, expressed back in prefill
milliseconds for comparability with §4.4.2:

| design | ν | t | SE (score) | WIN needs Δ̂ | in ms-equivalent | prior rule's ms |
|---|---|---|---|---|---|---|
| n=1 | 2 | 2.920 | 0.0011973 | 0.016653 | 1.710 ms | 1.811 ms |
| n=2 | 3 | 2.353 | 0.0009466 | 0.015384 | 1.580 ms | 1.644 ms |
| n=3 | 4 | 2.132 | 0.0008466 | 0.014962 | 1.537 ms | 1.596 ms |

A ~4 % improvement in the detectable effect, which is honest but modest: at
these σ̂ the 1.35 ms bar dominates the noise term, so no channel choice makes a
sub-bar effect detectable. The real reason to switch is not power, it is
validity — the primary channel should be the one the ranking is computed from,
and I had no good reason to put a derived diagnostic in that role.

`verdict_is_shippable` still requires `WIN`, which still requires n ≥ 2. The
early-stop clause is unchanged and now reads on the score channel.
`research/r105a-analyse-selftest.py` covers the new branches: score-primary,
prefill-only win refused, channel disagreement downgraded, and bar equivalence.

### 4.4.8 Auditing Amendment A against itself: one retraction, one real correction

Amendment A was preregistered before A1-1's receipt existed, so I audited it
while that submission was in flight rather than after seeing its number.
`research/r105a-sigma-audit.py` reproduces everything below from
`r105a-receipts-resolved.json`. Two of the three threats I went looking for
turned out to be real.

**(a) RETRACTION: §4.4.6's anti-correlation "explanation" is an algebraic
identity, not a finding.** I claimed the score channel's tightness was
*explained* by the two scored axes being anti-correlated, and offered as
evidence that re-propagating with the sample `r = −0.978` reproduced the
observed score CV (0.040309 % predicted vs 0.040335 % observed). That agreement
is worth nothing. Because

```text
ln S = 0.75 ln nd + 0.25 ln np        exactly, on every receipt
```

the sample variance of `ln S` *is* the bilinear form
`0.5625 var(ln nd) + 0.0625 var(ln np) + 0.375 cov(ln nd, ln np)` evaluated at
the sample moments. The audit confirms the ratio numerically:

```text
sample var(ln S)                    = 1.626847e-07
0.5625 vd + 0.0625 vp + 0.375 cov   = 1.626847e-07     ratio = 1.000000000001
```

Recovering the observed spread is therefore guaranteed by the bilinearity of
the covariance operator and tests nothing. At n = 3 the correlation has 1
degree of freedom and its magnitude is essentially unconstrained; a Fisher-z
interval is not even defined. What survives is much weaker and I should have
said only this: *the sample covariance is negative, and the directly measured
score spread is 2.47× tighter than independent propagation would give.* The
mechanism behind that negative covariance is identified in (c) below, and it is
not a property of the score at all.

None of this touches the σ̂ actually used. `sigma_score = 0.0010369` is measured
directly on the channel the rule reads, from three points, with 2 dof. It does
not depend on the retracted story.

**(b) The channel-selection worry is real, but it is answered by data rather
than by argument.** I compared six channels' CVs on the same three controls and
adopted the tightest. Picking the minimum-variance channel from six and then
reusing that same σ̂ as if pre-specified biases σ̂ downward, which is exactly the
kind of self-inflicted significance I should distrust at 2 dof. Two answers,
one weak and one strong.

The weak answer is a sensitivity bound. A2's regression verdict survives until
σ̂ is inflated by **5.32×**:

```text
sigma x  1.000  SE 0.001197  CI90_hi -0.015111  REGRESSION
sigma x  3.000  SE 0.003592  CI90_hi -0.008118  REGRESSION
sigma x  5.000  SE 0.005987  CI90_hi -0.001126  REGRESSION
sigma x  5.322  SE 0.006372  CI90_hi +0.000000  <-- critical
```

I will not oversell that. The noisiest of the six channels (`step_ms`,
CV 0.2895 %) has 7.18× the score channel's CV, and 7.18 > 5.32, so a sceptic
who insisted the score channel is secretly as noisy as the worst channel could
deny the verdict. The inflation bound is not sufficient on its own.

The strong answer is to stop choosing. A2 is worse on **all six** channels, and
four of the six exclude zero at 90 %:

| channel | ctrl mean | σ̂ | CV % | A2 Δ | z | verdict |
|---|---|---|---|---|---|---|
| `official_score` | 2.570748 | 0.001037 | 0.0403 | −0.018607 | −15.54 | WORSE, CI90 excludes 0 |
| `decode_speedup` | 2.817816 | 0.003263 | 0.1158 | −0.013811 | −3.67 | WORSE, CI90 excludes 0 |
| `prefill_speedup` | 1.952095 | 0.003825 | 0.1959 | −0.027753 | −6.28 | WORSE, CI90 excludes 0 |
| `prefill_ms` | 96.149208 | 0.136807 | 0.1423 | +1.034209 | +6.55 | WORSE, CI90 excludes 0 |
| `step_ms` | 4.168971 | 0.012071 | 0.2895 | +0.002124 | +0.15 | worse, not significant |
| `cand_dec` | 0.004920 | 0.000012 | 0.2425 | +0.000010 | +0.74 | worse, not significant |

No channel choice rescues A2, so for this arm the selection concern is moot.
The defensible framing going forward is also not "I picked the tightest
channel": `officialScore` is the function the competition maximizes, so it is
the a-priori correct primary channel on grounds that never mention variance.
Its tightness is a bonus, not the reason.

**(c) REAL CORRECTION: half of A2's score loss is baseline-limb session noise,
and the pairing imported it.** The table above contains a contradiction I had
not chased. `decode_speedup` fell with z = −3.67, yet the candidate's own
`step_ms` (z = +0.15) and `cand_dec` (z = +0.74) did not move. A published
speedup is `baseline / candidate` measured in the same session, and **my edit
cannot make the pinned baseline faster.** Splitting all four limbs:

| limb | ctrl mean | σ̂ | CV % | A2 Δ | z | attributable to my edit? |
|---|---|---|---|---|---|---|
| `baseline_pre` | 0.0003666 | 0.0000012 | 0.3299 | −0.0000013 | −0.95 | no — session noise |
| `cand_pre` | 0.0001878 | 0.0000003 | 0.1423 | +0.0000020 | **+6.55** | **yes** |
| `baseline_dec` | 0.0138641 | 0.0000461 | 0.3328 | −0.0000394 | −0.74 | no — session noise |
| `cand_dec` | 0.0049201 | 0.0000119 | 0.2425 | +0.0000102 | +0.74 | yes, but null |

and decomposing the score delta:

```text
decode   0.75 * -0.004913 = -0.003685   ( 50.7% of dlnS)
prefill  0.25 * -0.014319 = -0.003580   ( 49.3% of dlnS)
total dlnS = -0.007265  ->  dS = -0.0186762
```

So the decode half of the score loss — 50.7 % of it — arises because A2's
session happened to draw a baseline that was 0.74 σ *fast* while its candidate
was 0.74 σ *slow*. Neither limb is individually significant; the ratio is
significant only because the two limbs moved in opposite directions, breaking
the positive session-to-session coupling that the pairing normally exploits.
Exactly half of that ratio movement is a limb my code cannot influence.

The honest causal statement about variant 8 is therefore narrower and stronger
than §4.4.4's:

> **Routing the down-projection through `bn=128` slows prefill by 1.03 ms
> (z = +6.55 on the candidate limb, robust to every channel choice) and has no
> detectable effect on decode (z = +0.15 on `step_ms`, +0.74 on `cand_dec`).
> Its −0.0186 score delta overstates the causal harm by roughly 2× because half
> of that delta came from the baseline limb of a single session.**

This is the second time the decode side of this arm has produced a spurious
signal, and it is the second time the preregistered prefill-only prediction was
the correct one. §4.4.5 retracted a decode "effect" that was an artefact of a
2-point σ̂; (c) retracts what remained of it as an artefact of pairing. The
prefill harm has never wavered.

It also finally explains the §4.4.6 oddity that pairing *hurts* on prefill.
`baseline_pre` (CV 0.3299 %) is more than twice as noisy as `cand_pre`
(0.1423 %), and its noise is not tightly coupled to the candidate's, so
dividing by it adds variance instead of removing it: `prefill_speedup` comes out
at 0.1959 %, worse than the raw candidate limb. On decode the coupling is real
and the ratio does help, 0.1158 % against 0.2425 %. Same reason, opposite sign.
The negative covariance of (a) is a *baseline-limb* phenomenon, not a property
of the score.

**Amendment B (recorded now, before A1-1's number).** Keep `officialScore` as
the primary channel: it is the objective, the ranking is computed from it, and a
shipping decision must be made on it. Add a mandatory second reading that is
causal rather than ranked:

1. Report `cand_pre` and `cand_dec` deltas for every arm. Only these can carry
   a treatment effect.
2. If an arm's score delta is materially driven by a `baseline_*` limb, say so
   and quote the candidate-limb effect as the mechanism's true size.
3. A score **WIN** whose gain is substantially attributable to a `baseline_*`
   limb is not promoted on that receipt; it needs the replicate that Amendment A
   already requires, and the replicate must reproduce it on the candidate limbs.

Amendment B cannot rescue a losing arm and cannot manufacture a winner — it
only stops me attributing session noise to my own code in either direction.

### 4.4.9 A1-1: Amendment B fires on its first application

Slot 5 returned variant 7 (routed **gate/up** at `bn=128`, down left at 64) with
`officialScore = 2.59235893273017`. Against the n₀ = 3 control mean of
2.5707480348952267 that is **Δ = +0.0216109, SE 0.0011973, z = +18.05**, CI90
[+0.0181147, +0.0251071], comfortably clear of the bar 0.0131568. On Amendment A
alone this reads `WIN-pending-replicate`: the largest, cleanest, most
statistically overwhelming number in the whole ladder.

It is not a code win. Amendment B was written ~25 minutes before this receipt
existed, and rule 3 refuses it:

| limb / channel | control mean | A1-1 | z | reading |
|---|---|---|---|---|
| `baseline_pre` | 0.0003666 | 0.0003824 | **+11.34** | baseline 4.3 % slower — impossible for my edit |
| `cand_pre` | 0.0001878 | 0.0001900 | **+7.03** | candidate prefill **worse** |
| `baseline_dec` | 0.0138641 | 0.0138523 | −0.26 | null |
| `cand_dec` | 0.0049201 | 0.0049116 | −0.62 | null |
| `step_ms` | 4.168971 | 4.15171 | −1.24 | null |
| `decode_speedup` | 2.817816 | — | +0.67 | null |

Decomposing `dln S`, **92.0 %** of the score gain arrives through the prefill
*ratio*, and that ratio improved only because the denominator degraded:
`dln baseline_pre = +0.042195` against `dln cand_pre = +0.011646`. The candidate
prefill wall was **97.26037 ms against a control 96.149208 ms, i.e. +1.111167 ms
slower** (z = +7.03). The arm won the ranking by being handed a sicker baseline
than the controls got, while itself getting worse.

**Three score channels.** To make this reproducible rather than rhetorical, §5
of `research/r105a-sigma-audit.py` now recomputes every arm in three channels:
`official_score` (both limbs paired, the ranked objective), `hybrid_score`
= `decode_speedup^0.75 · (CAL_PRE/cand_pre)^0.25` (keeps the paired decode ratio
where pairing helps, un-pairs prefill where §4.4.8 showed pairing hurts), and
`norm_score` (both baselines replaced by pinned constants — fully
baseline-free).

| channel | control mean | σ̂ | CV % |
|---|---|---|---|
| `official_score` | 2.5707480 | 0.0010369 | 0.0403 |
| `hybrid_score` | 2.6015956 | 0.0030402 | 0.1169 |
| `norm_score` | 2.6052544 | 0.0047446 | 0.1821 |

A1 (n = 1, ν = 2, t95 = 2.920):

| channel | Δ | SE | z | CI90 | verdict | share of official Δ |
|---|---|---|---|---|---|---|
| `official_score` | +0.0216109 | 0.0011973 | +18.05 | [+0.0181, +0.0251] | WIN-pending-replicate | 100 % by construction |
| `hybrid_score` | −0.0057214 | 0.0035106 | −1.63 | [−0.0160, +0.0045] | NULL-bar-excluded | **−26.2 %** |
| `norm_score` | −0.0040778 | 0.0054786 | −0.74 | [−0.0201, +0.0119] | NULL-bar-excluded | **−18.6 %** |

Both baseline-free channels put the effect on the *wrong side of zero*. The sign
of this arm's "win" is an artefact of which baseline draw it was paired with.

> **Honest causal statement for the family: both routed shapes are harmed by the
> wide N-tile. Variant 7 (gate/up) costs +1.111 ms of prefill wall, z = +7.03;
> variant 8 (down) costs +1.034 ms, z = +6.55. Neither moves decode at all.**

That is the preregistered **N-2** outcome (occupancy / register pressure at
`bn=128`: N-tiles halve, per-threadgroup shared memory doubles), with **N-1**
(the L2/SLC already absorbs the A-fragment re-reads, so there is no re-read to
save) as co-explanation. The A-fragment reuse thesis is falsified in both routed
shapes independently.

**Numerical correction to §4.4.8(c).** (c) estimated that 50.7 % of A2's score
loss was baseline-limb noise, derived from the paired decomposition. The fully
baseline-free channel is the better instrument and disagrees: `norm_score` puts
**58.3 % of A2's loss as candidate-attributable**, so ~41.7 % — not 50.7 % — was
baseline noise. (c) was directionally right and numerically off; the A2
REGRESSION verdict is unaffected because `hybrid_score` (Δ −0.0164939,
z = −4.70, CI90 excluding zero) independently confirms it at 87.6 % attribution.

Note also that `norm_score` is **4.6× noisier** than `official_score`. Stripping
the baseline is not free: it destroys the `base_dec`/`cand_dec` pairing that
genuinely cancels decode session drift. `hybrid_score` is the best-powered
causal channel precisely because it un-pairs only the limb where pairing adds
variance — which is what discipline rule 1 of the submission note prescribed
before any receipt was spent, not a channel chosen after seeing A1-1.

**Preregistered falsifiable prediction, recorded before A1-2's receipt.** Slot 6
is the Amendment-A replicate of variant 7. If the limb analysis above is right
and A1-2 draws a normal `baseline_pre`, its `officialScore` should land near
**2.5667** (control 2.5707 plus a candidate-only effect of ≈ −0.004): a small
loss, not a win. Pooling A1-1 + A1-2 then moves the A1 official delta from
+0.0216 to ≈ **+0.0088**, with n = 2 SE 0.0009466 and ν = 3 (t95 = 2.353) giving
CI90 ≈ [+0.0066, +0.0110] — entirely **below the bar 0.0131568**, verdict
`NULL-bar-excluded`. If instead A1-2 returns ≈ +0.021 *with a `baseline_pre`
inside the control band*, then variant 7 genuinely wins, Amendment B refused a
real winner, and this entire limb analysis is wrong. Both outcomes are
distinguishable from a single receipt.

### 4.4.10 The knob is structurally prefill-only

The decode nulls in every arm are not weak evidence of a small effect; they are
an **exact structural zero**, and I should have established this before spending
receipts on the decode channel at all.

`darkbloom_stage_bm128_variant()` is read at `quantized.cpp:1376`, inside
`gather_qmm_rhs_nax` (opens :1332). That function is reachable from exactly one
call site, `quantized.cpp:1670` inside `gather_qmm_rhs`, which the outer
`GatherQMM::eval_gpu` dispatch calls only under

```cpp
const bool sorted_rhs =
    M == 1 && B >= 16 && right_sorted_ == true && B / E >= 4;   // :1901-1902
```

`B` is the number of token-expert pairs. Prefill: 512 tokens × top-k 8 = 4096
pairs, `E` = 256, so `B/E` = 16 and `sorted_rhs` holds. Decode: 1 token × top-k
8 = **8 pairs, so `B >= 16` fails**, `sorted_rhs` is false, and the dispatch
falls through to `gather_qmv` at :1958 — a GEMV path with its own hard-coded
`bn=8 / bk=32` geometry (:1043-1046) that never reads the variant selector.

Three consequences:

1. **The _marginal decode step_ is a structural placebo channel across all six
   receipts — but `cand_dec` is not.** *(Corrected after reading the harness;
   see §7.6.)* The reported `decode_seconds_per_token` is
   `(seed prefill + 128 one-token steps) / 128`
   (`LagunaRuntimeBenchmark.swift:966-968`, `:1010-1013`, whose own progress
   line says `includes_seed_prefill=true`), so a prefill-only treatment **must**
   show up in `cand_dec` at `ΔS/128`. The clean placebo statistic is therefore
   `step_ms = 1000 * cand_dec - prefill_ms / 128`, which strips the seed. It is
   null in both treatment arms, as predicted: variant 7 `z = -1.24`, variant 8
   `+0.002124 ms` on `σ = 0.012071`, `SE = 0.013940`, **`z = +0.15`** (the
   advisor independently computed `+0.15` for this arm). That is why §4.4.5's
   decode "effect" retracted and why (c)'s residual retracted.
   The `ΔS/128` leak is a *free positive control* that costs no receipt:

   | arm | `ΔS` (ms) | predicted `Δcand_dec` (ms) | observed (ms) | SE (ms) | verdict |
   |---|---|---|---|---|---|
   | A2-1 (variant 8) | +1.034209 | +0.008080 | **+0.010167** | 0.013741 | agrees, 0.15 SE |
   | A1-1 (variant 7) | +1.111167 | +0.008681 | **-0.008533** | 0.013741 | 1.25 SE short, not significant, not confirmatory |

   With `σ(cand_dec)/128`-scale effects an order of magnitude under the channel
   noise, this control can corroborate but cannot falsify at n=1; I report it
   because it is the only free cross-check of the harness model that the ladder
   generated.
2. **The ceiling on this knob family is 36.45 % of the score weight**, not the
   25 % I first wrote. Because the seed forward is charged on *both* axes, the
   elasticity of the score to the prefill wall is
   `0.75 * share + 0.25 = 0.364504` with `share = S/(S + 128 T) = 0.152672`
   (§7.6 derives this). Clearing the bar (0.5118 % of score) therefore requires
   **1.35 ms, i.e. 1.40 %, off the 96.15 ms prefill wall** — exactly the
   preregistered `BAR_MS`, because the campaign's blended `0.379103 %/ms` *is*
   the seed-forward price. Measured: +1.111 ms (variant 7) and +1.034 ms
   (variant 8) in the wrong direction, so the family is about **2.5 ms** away
   from shippable, not a tuning nudge away. For contrast, the same bar needs
   only **0.0336 ms off each decode step** (0.68 % of the 4.169 ms step) — 40×
   more score per millisecond — and this knob provably cannot reach that axis.
3. **Variant 6 (both routed shapes at `bn=128`) should not be given a receipt.**
   An independent frontier review reached the same conclusion from the same code
   and adds the mechanism check: gate/up and down are disjoint tensors each far
   larger than the SLC (no cross-GEMM cache reuse to unlock), the GLU data
   dependency serialises the two GEMMs (no occupancy coupling), the baseline
   64/64 is already shape-uniform (so uniformity confers no edge), and the
   candidate super-additive effects — PSO/spec-set uniformity, icache,
   dispatch-branch — are microseconds against a ~1.03 ms harm to overturn, two
   to three orders of magnitude short. Expect Δ(6) ≈ Δ(7) + Δ(8), dominated in
   every branch: if 7 ≤ 0 then 6 < 8 < 0, and if 7 > 0 then 7 ships alone. The
   untested 2×2 interaction cell has no shared resource to act through, so
   skipping it is a scientific judgement with a stated mechanism, not budget
   economy.

### 4.4.11 Amendment C, and one deviation from the advisor's refined stopping rule

**Amendment C — recorded now, while A1-2 is in flight and its receipt is
unread.** Advisor feedback fb2 §2 asks that the outcome variable for the
remaining leg be pre-registered prospectively. Adopting it verbatim:

1. The **primary outcome for the remaining leg is `cand_pre`** (candidate
   prefill limb), expressed as `prefill_ms = 512000 * cand_pre` so the bar is in
   the same units as `BAR_MS`.
2. `step_ms = 1000 * cand_dec - prefill_ms / 128` is the **null control**
   (§4.4.10 item 1: structurally zero at `B = 8`).
3. `officialScore`, `hybrid_score` and `norm_score` are still reported for the
   record and for continuity with Amendment A, but the **causal verdict on the
   `bn = 128` family is decided on `cand_pre`**, because A1-1 showed
   `officialScore` can move `+18σ` on a baseline-limb lottery while the
   candidate limb barely moves. `cand_pre` is the only channel whose treatment
   assignment is guaranteed by construction.
4. Decision rule on that channel, same shape as Amendment A: `Δ̂S = arm mean −
   control mean` in ms of prefill wall; `σ̂ = 0.136807` ms from the n=3 A0
   control; `SE = σ̂ * sqrt(1/n + 1/n₀)`; `ν = (n₀−1)+(n−1)`; same `T95` table.
   Lower is better, so: CI entirely `> 0` → **REGRESSION**; CI lower bound
   `> -1.35` ms → **NULL-bar-excluded**; CI upper bound `< -1.35` ms with `n ≥ 2`
   → **WIN**. At `n = 2` vs `n₀ = 3`, `SE = 0.1249` ms and the 90 % half-width is
   `2.353 * 0.1249 = 0.294` ms, so the pooled A1 prefill verdict will be
   resolvable either way.
5. Prospective prediction for A1-2 on this channel, paired with §4.4.9's score
   prediction: pooled `Δ̂S ≈ +1.1` ms, CI ≈ `[+0.82, +1.41]` → **REGRESSION and
   bar-excluded**. The falsifier is a pooled CI that reaches `-1.35` ms.

**Deviation from fb2 §6.3, owned explicitly.** fb2 §6.3 refines the stopping
rule: *if A1-1 also regresses on the prefill channel at `|z| ≥ 2`, fire N-1 on
the entire `bn = 128` family and stop at 6 receipts — do not spend A1-2*, with
the prescribed 6th receipt being A2-2. A1-1 did regress on prefill (`z = +7.03`),
so that trigger fired, and I nonetheless spent slot 6 on **A1-2**. The
chronology: fb2 was posted `2026-08-10T06:03:53Z`; the A1-2 dispatcher queued
`c52994dc` at `06:42:51Z` after an 18-minute wait on the shared submission slot;
I read fb2 at ≈`06:46Z`. So the choice was made under my own Amendment A, which
requires a replicate for an apparent `WIN-pending-replicate` at `+18σ`, and not
in defiance of a rule I had read.

Why I would still choose A1-2 having now read fb2, stated so the advisor can
disagree with the reasoning rather than the accident:

- The two channels **disagreed in sign for the first time in the ladder**
  (official `+18.05σ`, prefill `+7.03σ` the wrong way). Neither stopping rule
  anticipated that case, and an unreplicated `+0.0216` score delta left on the
  record is exactly the kind of artefact that gets promoted by a later reader.
- A1-2 is the **decisive test of §4.4.9's baseline-lottery prediction**
  (`officialScore ≈ 2.5667` with `baseline_pre` back inside the control band),
  which is falsifiable and cheap. A2-2 could only tighten a harm already at
  `z = -6.55` official / `z = -4.70` hybrid; it could not change any verdict.
- The **budget outcome is identical**: 6 receipts spent, 2 banked, stop now.
  I am not proposing to spend slots 7–8 to repair the deviation.

N-1 fires on the whole family regardless of which arm took slot 6.

---

## 5. Verdict

**Rig-invalid is _not_ the verdict.** The brief's `Rig-invalid` bucket is
reserved for "D6 fails, or `expert_aligned` drops, or the twin check disagrees."
None of those happened: D6's regression is real but **repaired** (§1 D6),
`expert_aligned` holds (§1 D1), and the twin is byte-identical (§1 D7).

### 5.1 Terminal now, independent of any receipt

1. The lever is **implementable and expert-aligned** at `BN = 128` for both
   Laguna MoE shapes (D1, D2, D3).
2. The naive edit is **broken twice over** — a silent wide-load regression (D6)
   and a wrong SwiGLU pairing (D4) — and the brief's own stated test for the
   first of those would have **passed while the regression was present**. Both
   are repaired and the repairs are proved inert at `BN = 64` by byte-identical
   AIR.
3. The prize is **materially smaller than the brief's headline**, and bounded
   by arithmetic rather than by opinion (§7.2).
4. The submitted candidate is **inert at its default** on both A0 rungs:
   `max_abs_diff = 0` over 1,344 checked greedy tokens, GPQA 9/9, both `0.95`
   floors passed, twice. Whatever the treatment rungs say, the repaired
   `BN = 128` machinery does not perturb the shipped path when it is not
   selected.
5. The ranked instrument's within-tree per-receipt σ on candidate prefill is
   **0.190 ms (0.197 %)**, ~10× tighter than the cross-submission spread implies
   (§4.4.1). That number is reusable by every future student who wants to know
   what a single official receipt can resolve, and it is the first time the
   campaign has measured rather than assumed it.

### 5.2 The three-way verdict against §4 of the brief

The brief's buckets are P (positive), N-1 (the family is closed) and N-2. I will
report exactly one of the following, by the §4.4.2 rule, and nothing stronger:

| verdict | condition | what it licenses |
|---|---|---|
| **WIN** | some arm has Δ̂ − t₀.₉₅,ν·SE > 1.35 ms at n ≥ 2 with D1–D5 passing | flip the compiled default for that arm; slot 8 tests variant 6 first if both arms win |
| **NULL, bar excluded** | every arm has Δ̂ + t₀.₉₅,ν·SE < 1.35 ms | supports N-1 *for the BN axis at these shapes*, at the measured resolution — not "no lever anywhere in the gather-GEMM" |
| **NULL, underpowered** | anything between | no claim about the family; report the shortfall and the receipts it would take |
| **REGRESSION** | Δ̂ + t₀.₉₅,ν·SE < 0 | separate finding, never folded into null |

**I am not claiming N-1 in the brief's own words.** The preregistered sentence
— *"the A-operand re-reads are already absorbed by cache, and the routed
gather-GEMM has no remaining ranked lever"* — is broader than any receipt I can
buy. Even a clean bar-excluded null bounds *this* tile change on *these* two
shapes; §7.3's unoffered arm separates halved-A-traffic from BN=128 and has not
been run.

**Merge rule, stated in advance.** If the treatments are null, the candidate is
a *research artifact*, not a shipment: the compiled default stays at variant 5,
the tree is byte-inert on the scored path, and the PR must **not** be merged
merely because it is correct and harmless. That is the PR #293 precedent —
merging inert machinery adds surface area to `editablePaths` and future review
cost for zero ranked gain. The reusable outputs in that case are §4.4.1's σ, the
two repairs, and the §7 corrections, all of which live in the report and need no
merge.

### 5.3 D5 reachability — stated honestly

D5 asks whether the modified kernel is reachable on ranked hardware. My local
host is an **M4 Pro (Apple GPU generation 16, 48 GiB)**, which does not select
the `_nax` prefill kernels the ranked M5 uses. So my reachability evidence is
**code reading plus the ranked receipts themselves**, not local dispatch:

- the selector at `quantized.cpp:1234` is compiled into the archive and its
  `s.empty()` branch is what the ranked box executes, since the harness sets no
  `DARKBLOOM_STAGE_BM128`;
- the JIT twin (`fp_quantized_nax.cpp`) is consistent with the header, checked
  by `research/nax_twin_check.py` (§1 D7);
- the A0 receipts prove the archive builds and runs on the M5 with the selector
  present.

What they do **not** prove is that variant 8's threadgroup geometry is the one
the M5 actually launches — only a treatment receipt with a nonzero Δ̂ proves
that positively. A null treatment receipt is therefore ambiguous between "the
tile change does nothing" and "the tile change was not reached", and I will say
so rather than reporting the stronger reading. §7.4's rig defect is the reason
this ambiguity exists at all: the local rig was validating a variant that never
ships.

**Update — the ambiguity is now closed, by the harm.** The escape clause above
said only a treatment receipt with a nonzero Δ̂ proves the geometry is actually
launched. Both treatment arms delivered one, on the limb that can carry it:
variant 8 moved `cand_pre` by +1.034 ms (z = +6.55) and variant 7 by +1.111 ms
(z = +7.03), each many σ outside the control band on a channel with CV 0.1423 %.
A knob that was never reached cannot slow the candidate down. **D5 is therefore
positively satisfied for the `_nax` routed prefill path from ranked evidence, not
from code reading** — and the reason is that both arms lost. Had they both
returned exact nulls I would still be unable to distinguish "no effect" from "not
reached", which is precisely the asymmetry §5.3 was written to flag. The residual
unproven part is narrow: I have not shown from the M5 which of the two *decode*
kernels executes, but §4.4.10 settles that from the dispatch predicate instead.

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

### 6.1 What the dispatch code pins down after both arms lost

Reading the launch and the kernel together explains the sign, and it explains it
in terms that were checkable before any receipt was spent.

**The grid is per-expert, not per-row.** `quantized.cpp:1629-1632` sets
`grid.y = egroups` on the `expert_aligned` path — `darkbloom_expert_gather_groups()`
returns **256** (`:1222-1232`), the expert count — and *not* `(M + bm − 1) / bm`,
which is the generic path's y-extent. So the threadgroup count is
`256 × ceil(N/bn)`, independent of `M`. `bn = 64 → 128` halves it: gate/up
4096 → 2048 TGs, down 8192 → 4096 TGs. Both arms halve their grid by exactly 2×,
which is why their harm is nearly equal (+1.111 vs +1.034 ms) despite different
`N` and `K`. 2048 TGs is still ample grid-level parallelism for a 40-core part,
so the harm is per-core **residency**, not starvation — and residency is set by
threadgroup memory, which is where the second half of the mechanism lives.

**Only the weights are staged; the activations are not.** In
`fp_gather_qmm_rhs_expert_nax` (`fp_quantized_nax.h:1714`) the sole threadgroup
allocation is `Ws_storage`, sized `kWsElems = BN × BK_padded`
(`:1768-1772`), which the fused gate/up epilogue then *aliases* as
`gate_up_stage`. There is no `Xs`. So `BN = 128` doubles the only tgmem consumer
(D5's measured 9,232 → 18,448 B) while the A fragments it is supposed to help
are read straight from device memory, i.e. served by L2/SLC on the re-reads.

Put those together and the arm's trade is explicit: **it doubles the per-TG
footprint of the DRAM-bound weight stream in order to halve the issue count of
cache-resident activation loads.** §7.2 already bounded the second term
(`r ≤ 0.698`, prize ≤ 8.76 ms and only at 100 % of DRAM peak); the ranked
receipts now price the first term at ≈ +1.07 ms, and it wins. Twice,
independently, in two different shapes.

**The deeper reason no tile geometry can win here.** Each expert's rows are
chunked *inside* the kernel: `for (chunk_start = run_start; chunk_start < run_end;
chunk_start += BM)` with `chunk_rows = min(BM, run_end − chunk_start)` and per-SIMD
row masking. The weight slab is staged *inside* that loop, so total weight
traffic is `experts × K × N × chunks` bytes: each expert's `N/bn` tiles stage
`bn × K` bytes apiece, which sums to `K × N` **whatever `bn` is**. Weight traffic
is therefore exactly invariant to `bn` — the arm's entire prize has to come out of
the activation term alone, and §7.2 already showed that term is mostly cache-served.

`bm` is different, and not in a helpful direction. With 512 prompt tokens ×
`experts_per_token = 8` (`LagunaRuntimeModel.swift:8077`) over 256 experts the
average run is **16 rows against `BM = 64`**, so most experts take one chunk and
the accumulator's M dimension is ~75 % empty. The obvious reaction — narrow `BM`
to fit the runs — is wrong: `chunks = ceil(run/BM)`, so shrinking `BM` makes the
imbalanced tail of long runs re-stream their weight slab more times, *raising*
the dominant term to save masked-off MMA work in the bandwidth-bound regime.
`BM = 64` is already at or near the weight-traffic floor, which is the honest
reason to leave it alone rather than an untested assumption.

So the routed prefill GEMM is weight-bandwidth-bound by construction, and its
dominant traffic term is invariant to `bn` and already minimised at `bm = 64` —
the advisor's own script puts that floor at 14.826 GB / 24.306 ms. The levers
that could still matter reduce weight *bytes* or raise rows per weight pass;
`(bm, bn)` does neither.

That is a stronger and more useful form of N-1 than "cache absorbs the re-reads",
and unlike the brief's wording it is a statement about the dispatch structure
rather than about my two receipts.

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

### 7.2a Reconciliation with fb1's Rule-83 update

Advisor feedback `tanjiro-r105a-fb1-receipt-coordination` (2026-08-10T02:15:33Z)
lands the #571 result: on `DARKBLOOM_ROUTER_WEIGHT_PREFETCH`, the per-kernel
`SPLIT=1` label says **−6.39 µs/step** (12/12 sign) while two independent
end-to-end instruments say **+18.50** and **+34.58 µs/step** (21/21 reps,
p = 2⁻²⁰). I am asked to state the caveat explicitly. Stating it:

> **An isolated-régime per-kernel millisecond is an upper bound on the
> overlapped-régime saving, and the router-prefetch dial is a measured
> counterexample in which the sign itself inverted.** My #586 §6A attribution
> (1146 calls / 540.394 ms) is an additive decomposition of exactly that kind of
> isolated measurement and inherits exactly that caveat.

**Does this weaken §7.2's bound? No — and it is worth being precise about why.**
§7.2 rests on two inputs and **neither is a per-kernel label**:

| input | provenance | exposed to the #571 critique? |
|---|---|---|
| 14.826 GB weight traffic | *static* count, `768 load_unsafe/chunk × 2304 B × 8379 chunks`, derived twice independently (`tanjiro-nax-kloop-pipeline.md:82-97`; `advisor_r105_gather_roofline.py`) | **No.** Static source counting has no régime. |
| 43.262 ms anchor | PR #34 *end-to-end receipt* marginal (`141.1262 − 97.8643`) | **No.** It is already end-to-end. It is rule-76-contaminated, but §7.2 uses it only as an upper bound and over-estimation moves `r`'s ceiling *down*. |

So `r ≤ 0.698` survives intact. What fb1 *does* add is a **third independent
reason** to distrust any per-kernel pricing of this arm, which is why the Stage-2
ladder in §4.3 is receipt-only end-to-end from the first arm and contains no
label→end-to-end inference step anywhere. The advisor's "add an end-to-end
confirmation before you spend a receipt" instruction therefore has no target
here: there is nothing to confirm, because nothing in the design was priced off
a label.

**But fb1 makes D5's open confound materially more dangerous, and this is the
real update.** The #571 mechanism is that `SPLIT=1` removes dispatch overlap, so
a change that helps a kernel in isolation can cost more than it saves once
neighbours overlap. `BN = 64 → 128` does something structurally similar from the
other side: it **halves the threadgroup count** (gate/up 4096 → 2048, down
8192 → 4096) while **doubling per-TG threadgroup memory** (9,232 → 18,448 B,
measured, §1 D5). Fewer, fatter threadgroups is precisely the shape of change
whose isolated-kernel accounting looks free and whose overlapped-régime
behaviour is governed by residency. Combined with `GATHER_GEMM_REGIME_DESIGN.md`
§2.1 — two unconditional barriers per k-iteration, so intra-TG overlap is
impossible by construction and only *resource reduction* can move the number,
and this arm *increases* resource use — the honest prior on this arm should
shift **down**, not up:

* the DRAM-byte mechanism (§7.2) is capped at `r ≤ 0.698` and needs `r ≥ 0.303`
  merely to clear the record bar; and
* the occupancy mechanism now has a measured campaign counterexample showing
  that this class of reasoning can invert sign end to end.

That is not a design-gate kill — fb1 §3 invites one and I decline it, because
§7.2's own arithmetic leaves the bar *reachable* at `r ≥ 0.303` and the channel
resolves `r` to ±0.033 in a single clean pair. It is an argument that **A2
(down) is the better first receipt than A1 (gate/up)**, inverting the brief's
§3.2 ordering, and I record that as an explicit dissent in §7.3.

**fb1 §1 compliance.** No decode-side dial is touched: `DARKBLOOM_ROUTER_WEIGHT_PREFETCH`
(`LagunaRuntimeModel.swift:696-704`) and the sliding-attention k-loop
(`:1638-1817`) are untouched on this branch, and the tile-variant default
remains `5`, so the branch is behaviourally identical to base until an arm
commit flips it. The §4.3 ladder already specifies distinct commit SHAs per
receipt with the SHA made to differ outside `Sources/`. Since **0 receipts were
dispatched (§4.2)**, no commit of mine can collide with nezuko (#584),
frieren (#597) or fern (#598).

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

**Dissent on arm ordering: A2 (down) should be the first receipt, not A1.** The
brief's §3.2 orders gate/up first on two grounds — four times the A operand per
layer, so least likely SLC-resident, and twice the prize. Both are correct as
stated. Three considerations that post-date the brief nevertheless invert the
ordering:

1. **A1 confounds two of this branch's own repairs; A2 confounds none.**
   `fuse_swiglu` is decided kernel-side at `fp_quantized_nax.h:1981-1982` on
   `kernel_N == 1024 && kernel_K == 2048`, i.e. **the gate/up shape only**. So A2
   exercises *only* the D6 wide-load repair, while A1 exercises the D6 repair
   **and** the D4 block-aware epilogue rewrite (§6). A null A1 is
   uninterpretable — epilogue cost, register pressure, or a genuine SLC null —
   whereas a null A2 is clean evidence about `r` alone.
2. **A2 carries the smaller occupancy risk, which fb1 just promoted to a live
   mechanism (§7.2a).** Down keeps 4096 threadgroups at `BN = 128`; gate/up drops
   to 2048. If residency is what actually binds, A1 is where it bites first, and
   a negative A1 would then be misread as N-2 register pressure.
3. **The channel does not need the bigger prize.** σ on the prefill channel is
   0.420 ms against an A2 point prediction of `4.18·r` ms, so even A2 resolves
   `r` to ±0.10 in one pair — ample to discriminate the two hypotheses the brief
   actually cares about (`r ≈ 0` vs `r ≳ 0.3`).

The cost of leading with A2 is one extra pair if `r` turns out large; the cost of
leading with A1 is an uninterpretable result in the branch of outcome space the
brief itself calls most likely. I would run **A0, A0, A2, A1, A0, A1, A2, spare**.
This is a recommendation, not a unilateral change: no receipt was dispatched, so
the advisor retains the choice.

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

### 7.6 A millisecond is not a currency until you name the axis — and my first draft of this section was wrong

I first wrote this section claiming the campaign's blended price overstates a
prefill-only saving by 1.46x, so that my 1.35 ms bar "really" needed 1.97 ms of
prefill wall, the record bar was 5.53 ms, and the brief's 8.4 ms prize was worth
2.18 % rather than 3.18 % of score. **Every one of those four numbers is wrong.**
I then read the trusted harness instead of assuming its shape, and it refutes
the premise. I am keeping the refutation in the log rather than quietly deleting
it, because the corrected version is the derivation the advisor asked for in
fb2 §7 and the error is instructive: the whole mistake was pricing an axis I had
not read the timer for.

**What the harness actually measures.** In
`Sources/MLXFastTrustedHarness/LagunaRuntimeBenchmark.swift`:

```swift
let decodePhaseStart = DispatchTime.now().uptimeNanoseconds                        // :966
progress?("decode measured start tokens=\(decodeSteps) includes_seed_prefill=true") // :967
let beginResponse = try worker.beginDecode(seedTokens: seedTokens)                  // :968  <- 512-token prefill
...
let measuredSeconds = secondsSince(decodePhaseStart)                               // :1010
let secondsPerToken = measuredSeconds / Double(decodeSteps)                         // :1013
```

The timer starts **before** the 512-token seed prefill, and the harness's own
progress line says so: `includes_seed_prefill=true`. So

```text
decode_seconds_per_token = (S + 128 * T) / 128        S = seed prefill wall, T = one decode step
prefill_seconds_per_token = S / 512                   (:772 / :837, one 512-token prefill)
```

This is the *inclusive* model my `step_ms` derivation has assumed since §2 — it
is now confirmed from source rather than inferred — and it destroys the
"prefill is only worth 0.25" premise of the draft above. A millisecond removed
from the seed forward pass is billed on **both** axes: once in the prefill
speedup and once inside the decode phase.

**The elasticities (fb2 §7).** With `cs = decode_speedup^0.75 *
prefill_speedup^0.25` and the calibration constants fixed,

```text
ln cs = const - 0.75 * ln(S + 128 T) - 0.25 * ln S
share = S / (S + 128 T)

d ln cs / d ln S      = -(0.75 * share + 0.25)
d ln cs / d ln T      = -(0.75 * (1 - share))
```

and the two magnitudes must sum to exactly 1 (scale invariance: doubling every
time halves both speedups, so `cs` halves). From my n=3 control,
`S = 96.149208 ms`, `128 T = 533.628 ms`, `T = 4.168968 ms`, decode phase
`= 629.777 ms`, so `share = 0.152672` and

| channel | elasticity | check |
|---|---|---|
| prefill wall `S` | **0.364504** | `0.75*0.152672 + 0.25` |
| per-step decode `T` | **0.635496** | `0.75*(1 - 0.152672)` |
| sum | 1.000000 | scale invariance ✓ |

My A2-1 note quoted 0.362 / 0.638 from the same argument; the corrected values
are 0.3645 / 0.6355.

**The campaign's blended price is not a blend at all — it is exactly the
seed-forward price.**

```text
100 * 0.364504 / 96.149208 = 0.379104 %/ms      (campaign constant: 0.379103)
  = 0.260014 %/ms  on the prefill limb  (0.25 / S)
  + 0.119089 %/ms  on the decode limb   (0.75 * share / S = 0.75 / 629.777)
```

The constant every recent brief and every bar in this log uses is therefore
*correct and now derived*, not a coincidence and not an overstatement. Priced
per axis:

| what actually got faster | score value |
|---|---|
| 1 ms off the seed forward pass (both axes, e.g. any prefill-compute win) | **0.379103 %/ms** |
| 1 ms off the decode phase once (e.g. one-off setup inside decode) | 0.119089 %/ms |
| 1 ms off **each** of the 128 decode steps | **15.2435 %/ms** |

Retractions, explicitly: the blended price does **not** overstate a prefill-only
saving (factor is 1.00, not 1.46); my `BAR_MS = 1.35` bar is **1.35 ms of
prefill wall**, not 1.97 (`bar_score = 0.0131568` as preregistered); the
record-beating bar stays at **3.803 ms** of prefill wall, not 5.53; and the
brief's 8.4 ms prize is worth **3.18 %** of score, exactly as the brief said.
§7.2 still disputes whether those 8.4 ms exist at all — that bandwidth argument
is untouched and is the operative objection — but the *pricing* half of my
objection was my own arithmetic error and is withdrawn.

**What survives is a real and useful asymmetry.** A millisecond off every decode
step is worth `15.2435 / 0.379103 = 40.2x` a millisecond off the seed forward
pass. Clearing my 1.35 ms bar needs either 1.35 ms of the 96.15 ms prefill wall
(1.40 %) or **0.0336 ms off one decode step** (0.68 % of 4.169 ms). A decode-side
arm with one-fortieth of the mechanical leverage of a prefill arm is still the
better bet, which is the honest reason this family was a poor place to spend six
ranked receipts and why §4.4.10's follow-ups are all decode-side.

**The honest causal size of what this ladder measured**, at the corrected price:

| arm | `ΔS` (ms of prefill wall) | % of score | score units |
|---|---|---|---|
| variant 7 (A1) | +1.111167 | -0.42125 % | **-0.010830** |
| variant 8 (A2) | +1.034209 | -0.39207 % | **-0.010078** |

Both are about 0.8x the bar in magnitude, in the wrong direction, and both are
real harms rather than pricing artefacts.

Recommendation for the campaign convention: keep `0.379103 %/ms` but rename it
from a blended price to **`price_seed_forward_ms`**, and quote decode-side work
in `%`-of-score or in `ms_per_decode_step` (15.2435 %/ms), because those two
readings differ by 40x and the ambiguity is what produced the wrong section
above.
