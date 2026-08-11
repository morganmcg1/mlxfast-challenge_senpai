# R111 read-out: the `TN==1` NAX MMA path is wrong, and the staging ceiling is the same pool I priced in r107c

_Campaign: **maple**. Student handle: **maple-alphonse**. PR #685, branch
`maple-alphonse/r109-full-attn-qk-mma`, base
`9fe371909ee7ffa66a345cf3c42c21141096f388`. Executable class: **source
inspection only — no build, no timing, no submitted-surface change.**_

This answers the two questions the advisor put to me in the
`r111-e-gap-recalibration-and-staging-axis` comment. My own r109-E arm is
already terminal (`failed`, nothing lands); this document is the follow-on
read-out, not a new arm.

---

## A. `TN == 1` codegen: the path is **unsound as written**, and the fix is one argument

**Verdict: `N-TN1-BROKEN`. Do not ship any arm that drives `TN` to 1 without
also correcting the descriptor. With the correction the arm is clean.**

### A.1 How `TN` is produced

`Vendor/mlx-swift/Source/Cmlx/mlx-generated/metal/fp_quantized_nax.h:249-254`
(and the same block at `:395-400`, `:856-861`):

```
constexpr short SM = BM / WM;
constexpr short SN = BN / WN;
constexpr short TM = SM / 16;
constexpr short TN = SN / 16;
```

`BN 128 -> 64` at fixed `WN = 4` gives `SN = 16` and therefore `TN = 1`. This
is exactly maple-tanjiro's A2 arm. `TM` for the reached geometries is even, so
the dispatch lands in the first branch of `tile_matmad_nax`
(`.../steel/gemm/nax.h:994`):

```
if constexpr (TN == 1 && TM % 2 == 0) { ... M-pair mma ... }
else if constexpr (TN % 2 == 0)       { ... N-pair mma ... }
```

All 237 tier-1 census dispatches run `TN = 2`, i.e. exclusively the **second**
branch. The first branch is dead code in every shipped configuration.

### A.2 The two `mma` overloads use the *same* descriptor for *mirror-image* work

`BaseNAXFrag`: `kFragRows = kFragCols = 16`, `kElemsPerFrag = 256/32 = 8`.

Both overloads open with the identical line
(`gemm/nax.h:503` and `gemm/nax.h:575`; `attn/nax.h:401` and `attn/nax.h:473`;
editable twins `mlx-generated/gemm_nax.cpp:725` and `:797`,
`mlx-generated/steel_attention_nax.cpp:659` and `:731`):

```
matmul2d_descriptor(16, 32, 16, transpose_a, transpose_b, true, multiply_accumulate)
```

Apple's header fixes the argument order beyond doubt —
`MetalPerformancePrimitives.framework/Headers/MPPTensorOpsMatMul2d.h:357-376`:

```
int m, n, k;
constexpr matmul2d_descriptor(int __m, int __n, int __k = dynamic_extent,
                              bool __transpose_left = false, ...)
```

So the descriptor is **m = 16, n = 32, k = 16** in both overloads. Per-lane
cooperative-tensor capacities for a 32-thread simdgroup follow directly:

| operand | logical shape | elems/lane |
| --- | --- | --- |
| left  | `m x k` = 16x16 | **8** |
| right | `k x n` = 16x32 | **16** |
| dest  | `m x n` = 16x32 | **16** |

Now compare against what each overload actually writes:

| overload | `ct_a` writes | `ct_b` writes | `ct_c` writes | descriptor it *needs* |
| --- | --- | --- | --- | --- |
| N-pair (`Cn0,Cn1 / A / Bn0,Bn1`) | `[0..7]` | `[0..15]` | `[0..15]` | **(16, 32, 16)** ✅ matches |
| M-pair (`Cm0,Cm1 / Am0,Am1 / B`) | `[0..15]` | `[0..7]` | `[0..15]` | **(32, 16, 16)** ❌ mismatch |

The N-pair overload is exactly self-consistent with `(16, 32, 16)`: one 16x16 A
fragment, two 16x16 B fragments side by side (16x32), two 16x16 C fragments side
by side (16x32). That is also the only path production exercises, so its
"two fragments concatenated in lane storage" convention is empirically
validated by every correct token the ranked binary has ever produced.

The M-pair overload is its mirror image — two A fragments stacked (32x16), one B
fragment (16x16), two C fragments stacked (32x16) — but it was given the
**N-pair descriptor**. It is the only place in either file where the fill
pattern and the descriptor disagree.

### A.3 Three concrete defects

Working through `run(ct_a, ct_b, ct_c)` under the actual `(16, 32, 16)`:

1. **Out-of-bounds thread-memory write.** `ct_a[kElemsPerFrag + i]` for
   `i in [0,8)` writes indices 8..15 of an 8-element left tensor.
   `__operand_layout::thread_storage_size()`
   (`__impl/MPPTensorOpsMatMul2dImpl.h:2612-2631`) is per-operand only when
   `__TENSOR_OPS_SUPPORT_DEPLOYMENT_TARGET_26_2` is set
   (`__impl/MPPTensorOpsAvailability.h:10`,
   `__ENVIRONMENT_OS_VERSION_MIN_REQUIRED__ >= 260200`); below that target every
   operand is sized as the destination and the write is in-bounds-but-ignored.
   So this particular defect is **deployment-target dependent** — which makes it
   worse, not better: the same source is memory-safe or not depending on the
   min-OS the metallib is built against.
2. **Half the right operand is never initialised.** `ct_b[8..15]` (columns
   16..31 of the 16x32 right tensor) is read by `run` but never written.
3. **The result is semantically transposed.** `run` computes
   `C[16x32] += A[16x16] . B[16x32]`. Under the concatenation convention
   validated in A.2, `ct_c[0..7]` is C columns 0..15 and `ct_c[8..15]` is C
   columns 16..31 — but the caller copies them back into `Cm0` (rows 0..15) and
   `Cm1` (rows 16..31).

Net numerical effect, tracing defect 3 with defect 2: `ct_c[0..7]` receives
`Cm0 + Am0 . B`, which is **accidentally the correct answer for the `mm`
fragment**; `ct_c[8..15]` receives `Cm1 + Am0 . (uninitialised)`, i.e. garbage
written into the `mm+1` fragment. `Am1` never participates. Half of every
`TN==1` output tile is wrong.

This is a loud failure, not a silent one — it would be caught by the hidden
correctness gates. The cost is a burned submission and measurement cycle on a
**0.94 %–2.52 %** arm, not a scoring integrity risk.

### A.4 The fix, and why it is cheap

`(32, 16, 16)` is a legal descriptor. The impl header's validation for the
both-inputs-cooperative case is
`__impl/MPPTensorOpsMatMul2dImpl.h:4249-4252`:

```
static_assert(descriptor.m == 32 || descriptor.n == 32 || descriptor.k == 32, ...);
static_assert(descriptor.m == 16 || descriptor.m == 32, ...);
static_assert(descriptor.n == 16 || descriptor.n == 32, ...);
static_assert(descriptor.k == 16 || descriptor.k == 32, ...);
```

`(32, 16, 16)` satisfies all four. And under `(32, 16, 16)` **every existing
fill loop in the M-pair overload becomes exactly right**: left `32x16` = 16
elems/lane (`Am0 -> [0..7]`, `Am1 -> [8..15]`), right `16x16` = 8 (`B -> [0..7]`),
dest `32x16` = 16 (`Cm0 -> [0..7]`, `Cm1 -> [8..15]`). Nothing else in the
overload changes.

**Submittable patch (two files, two tokens each).** Only the
`mlx-generated/*.cpp` embedded twins are in `editablePaths`; the
`mlx/backend/metal/kernels/...` headers and the `mlx-generated/metal/...`
copies are **not**, and the `.cpp` is what is compiled at runtime.

| file | line | `16,` -> | line | `32,` -> |
| --- | --- | --- | --- | --- |
| `Vendor/mlx-swift/Source/Cmlx/mlx-generated/gemm_nax.cpp` | 798 | `32,` | 799 | `16,` |
| `Vendor/mlx-swift/Source/Cmlx/mlx-generated/steel_attention_nax.cpp` | 732 | `32,` | 733 | `16,` |

(The non-editable header copies at `steel/gemm/nax.h:576-577`,
`steel/attn/nax.h:474-475`, `mlx-generated/metal/steel/{gemm,attn}/nax.h:474-475`
carry the same defect and should be kept consistent for anyone reading them,
but they are not part of the submission.)

**This patch is a strict no-op for the binary as it stands today** — nothing
dispatches `TN == 1` — so it cannot win score on its own and should ride with
tanjiro's A2 arm rather than land alone.

### A.5 Residual assumption, and a strictly safer alternative

The one thing inspection cannot settle is whether a `32x16` cooperative tensor
lays out per-lane as *frag(rows 0-15) then frag(rows 16-31)*. The
column-concatenation convention is production-validated for the `16x32` case
(A.2); row-stacking is inferred by symmetry, and it is the same inference the
original author made. It needs one M5 numerical check.

If that check is not worth a cycle, there is a **strictly safer** route to
`BN = 64` that touches no unexercised codegen: hold `SN` at 32 by taking
`WN 4 -> 2` alongside `BN 128 -> 64`, and give the freed simdgroups to `WM`.
`TN` stays 2, the N-pair path stays the only path, and the arm's tiling
hypothesis is tested with 100 % production-validated MMA code. The usual
caveat applies — that is a threadgroup-geometry change and geometry sign has
flipped across core counts before (PR #7: +7.32 % M4, ~0 % M5).

### A.6 Attribution

`git show 2ebae10d:.../steel/gemm/nax.h` already contains the M-pair overload
with `(16, 32, 16)` at line 473 and the branch at line 847. The defect came in
with the original vendored MLX pin; the harvest commit `aecc470e` only added
`load_contig`/`load_rows_contig`. **This is upstream MLX code, untouched by the
campaign** — which is precisely why it survived: nothing upstream dispatches
`TN == 1` either.

---

## B. The `noload` / staging ceiling versus my r107c DRAM-bound argument

**Verdict: they do not conflict. They are the same pool of time measured from
opposite sides, and my `N-FLOOR` verdict never claimed the pool was empty.**

### B.1 What r107c actually claimed

`research/maple-alphonse-r107c-expert-gather-gemm-floor.md:604-647`:

> the family is at **82 %** of its bandwidth roofline with ≈**7.6 ms** of
> residual; the down share of that residual is 2.554 ms (a hard ceiling of
> 0.966 % of score) and the `bn` mechanism model claims only **0.195 %** of it
> ... robust in **0.19 %–0.30 %** across all four resident-bytes × bandwidth
> conventions ... the M5 being DRAM-bound (51.6 FLOP/B measured vs an M5 balance
> of 63.5–104) is a second, independent argument against **the arm's
> latency-hiding lever**.

Two things that claim does **not** say. It does not say the above-roofline
residual is zero — it says the residual is 18 % of the family window and
explicitly sizes it at 7.6 ms. And it does not say *no* lever can reach that
residual — it says the **`bn` tiling lever** prices at 0.195 % of it, below the
round's 0.4 % relevance gate.

### B.2 S3 measures the residual; r107c bounds it

S3 (ranked-M5, bit-exact perturbation of `nvfp4_gather_qmm_rhs_nax`): extra
staging with **zero extra DRAM bytes** costs **18.2 %** of window W (17.5σ).

An 82 %-of-roofline family has, by construction, `1 - 0.82 = 18 %` of its
runtime that is *not* explained by DRAM traffic. S3 adds work to exactly that
component and finds it worth 18.2 % of W. **18 % and 18.2 % are the same
number.** r107c estimated the non-DRAM component by subtracting the bandwidth
floor from total time; S3 estimated it by adding to it. The agreement across
two machines, two methods, and two measurement directions is the strongest
cross-validation either result has.

Sizing it on the advisor's units (`W ≈ 0.44 S`, `1 ms of S ≈ 0.37 %` ⇒
`S ≈ 68 ms`, `W ≈ 30 ms`): 18.2 % of W ≈ **5.4 ms ≈ 2.0 % of score** if the
entire staging component were removed. That sits in the same bucket as my 7.6 ms
residual (0.966 % of score for the down share alone). Both are far above the
0.07 % landing bar. **The pool is real and it is large.** No fraction of it is
reachable by `bn`, which is all r107c ever tested.

So the correct reading is: r107c is a **ceiling** on the staging axis
(≈18 % of the family window, no more, because the other 82 % is hard DRAM
floor), not a denial of it. Any staging arm must be judged against that
ceiling, and must not add DRAM bytes — the moment it does, it is spending
against the 82 % that has no give at all.

### B.3 Why 15.10 % (edward, M4) and 18.2 % (S3, M5) are consistent

They are not the same quantity and the ordering is the expected one:

1. **Different quantities.** "Exposed load chain" is latency that failed to be
   hidden. "Staging cost" is everything S3's extra staging adds: address
   arithmetic, threadgroup stores, the barriers that order them, and the
   register pressure that shrinks occupancy. Exposed-load ⊂ staging, so
   `15.10 % ≤ 18.2 %` is the direction the definitions predict.
2. **Different machines, and the direction is right.** The family measures
   51.6 FLOP/B. The M5 balance is 63.5–104 FLOP/B, so the kernel is below
   balance and DRAM-bound there. A higher machine balance means more of the
   window is spent waiting on the memory pipeline rather than on the MXU, so
   the non-compute share should be *larger* on M5 than on M4. It is.

Neither number refutes the other, and edward's 15.10 % should be read as a
**lower bound on the M4 shadow of the same pool**, not as a ceiling that
contradicts the ranked measurement.

### B.4 What I would want measured next on this axis

Ordered by evidence-per-cycle, all ranked-M5 because gen-16 hosts never select
`_nax` (`N-REACH`, r107c §2):

1. **Split S3.** S3 bundles threadgroup-store traffic, barrier count, and
   register pressure. Perturb barrier count alone at fixed staging to separate
   "the stores cost 18.2 %" from "the ordering costs 18.2 %". Those two have
   completely different fixes.
2. **Price the ceiling directly.** If the staging component is ≈5.4 ms of S,
   the arm that removes half of it is worth ≈1 % of score — an order of
   magnitude above the landing bar and comparable to the whole 1.35 % gap. That
   is worth a dedicated assignment, not a rider.
3. **Re-derive `bn` against the corrected residual.** r107c priced `bn 64->32`
   at 0.195 % against a residual it attributed to occupancy. If S3 says the
   residual is staging-shaped rather than occupancy-shaped, the `bn` price
   should be re-derived on the staging mechanism model before A2 is finally
   ranked or dropped. I expect it to stay sub-gate, but the model it was priced
   against has changed.

---

## C. Status of my own arm

r109-E is terminal and below bar: the submitted surface is byte-identical to
base, nothing lands. The three published negatives stand
(`N-FULL-QK-MMA-NEGATIVE`, `N-FULL-PARAMS-ALLOC-IRRELEVANT`, and the
instrument negative on the PR-91 GPUPROF hook), together with the SPLIT=1
bandwidth atlas (8,165 µs/step over 29 decode kernels; nine levers ≥50 µs/step
totalling ≈1,480 µs/step, none of them in my kernel) and the exposure
recalibration to 1.06 (CI [0.78, 1.34]).

Per the advisor's note — my arm has resolved below bar, so **the staging axis
is where I want to go next.** Section B.4 is my proposed shape for it.

---

_Prepared by an AI agent (OpenHands) on behalf of maple-alphonse._
