# R117-C Stage 1 pre-registration — the o_proj rows-per-simdgroup ladder

*maple-nezuko, PR #707, written 2026-08-11 ~03:55Z.*
*Written before the patch was applied to the working tree, before any build,
and before a single timing sample of this arm existed. The byte-dose ruler of
Stage 0 was still running on the GPU when this file was committed; the ladder
had not started.*

---

## 1. Why this arm exists at all

The assignment asked me to transplant edward's nibble-delta scale plane into
the attention projections. Stage 0
(`research/nezuko-r117-stage0-attn-byte-floor.md`) established that **the
mechanism is already shipped** — `_lm1_pw1` in the atlas kernel names *is*
lane-major plus pairwise, both default-ON, certified byte-exact at init — and
that after it ships the family's byte budget is **96.7 % irreducible NVFP4
payload**. Even a scale plane that vanished entirely returns
**101.8 µs/step = 0.855 %**, and every residual encoding arm (3-bit, 2-bit,
quad-wise) prices below the **68.7 µs/step** Rule 105.12 slot floor. The byte
envelope of this family is closed; that is the finding
`N-ATTN-BYTE-FLOOR`.

What Stage 0 also found is that the family has **one unpinned term left, and
it is not bytes**. `o_proj` is the geometric outlier of the decode GEMV pool:

| kernel | threadgroups | bytes/thread | GB/s | % of 256.7 GB/s peak |
|---|--:|--:|--:|--:|
| `qkv_h64` | 5120 | 32 | 242.1 | 94.3 % |
| `qkv_h48` | 3840 | 32 | 240.6 | 93.7 % |
| `oproj_h64` | 256 | 512 | 233.4 | 90.9 % |
| `oproj_h48` | 256 | 384 | 214.1 | 83.4 % |

`results_per_simdgroup = 4` and `num_simdgroups = 2` mean a 2048-row
projection dispatches **256 threadgroups**, twenty times fewer than its QKV
sibling, on a machine with 20 GPU cores. Closing `o_proj` to the QKV pool's
241.9 GB/s is worth **76.5 µs/step = 0.643 %** — above the 68.7 µs slot floor
and above the 0.406 % crown bar.

## 2. The change

New file `Sources/MLXFastModel/LagunaOProjGeometry.swift` exposes
`DARKBLOOM_OPROJ_ROWS_PER_SIMDGROUP ∈ {1, 2, 4, 8}`, default **4** = shipped.
`Sources/MLXFastModel/LagunaRuntimeModel.swift` takes nine scoped edits: the
`results_per_simdgroup` constant and the `result[]` initialiser inside
`lagunaGatedAffineOProjNVFP4Source`, a name suffix on each of the four kernel
dictionaries, and both dispatch grids in `lagunaGatedAffineOProjNVFP4`.

Scope verification completed before writing this file, by dry-running the
patcher against a shadow copy of the tree and reading the diff:

* All four o_proj NVFP4 kernel dictionaries — `…NVFP4Kernels`,
  `…NVFP4LaneMajorKernels`, `lagunaActivatedOProjKernels`,
  `lagunaActivatedOProjLaneMajorKernels` — are built from the **single**
  source `lagunaGatedAffineOProjNVFP4Source`, so one source edit covers all
  four, and all four are selected inside the **same** dispatch function, so
  the two grid edits cover all four dispatches.
* The interpolated fragments `scaleSetup`, `scaleRead`, `scaleAdvance`,
  `scaleDecode`, `accumDecl`, `firstAccum`, `extract`, `gateSetup`,
  `loadInput` were read line by line. Every scale pointer is indexed as
  `base + row * stride` with `row` running `0 ..< results_per_simdgroup`, and
  `scaleAdvance` moves only the per-k-block pointers. **No fragment contains
  an rps=4 assumption.** The kernel body is otherwise fully parametric.
* Two further `((outVec / 8) * 64)` grids exist at lines 4200 and 4209. They
  belong to `lagunaGatedAffineOProj`, the *affine INT* o_proj, which is built
  from different kernel dictionaries and a different source. They are **out of
  scope and are not touched**, and the patcher's line-range scoping proves it.
* Rule 33: MLX caches compiled pipelines by function name, so the ladder bakes
  `_rps1` / `_rps2` / `_rps8` into the Metal function name. The default keeps
  the shipped name **byte-for-byte**, so the control arm is the shipped
  kernel and not a renamed twin.
* Boundary check: this file touches nothing edward owns
  (`lagunaLaneMajorNVFP4ScaleBank`, `lagunaHalvedGroup32ScalePlane`, K1/K4)
  and nothing on the prefill path, so `lagunaPackedPrefillScaleView` stays
  bit-identical.

## 3. Why it should be bit-exact, and what happens if it is not

`results_per_simdgroup` decides only **which simdgroup owns which output
row**. For a fixed output row the accumulation is unchanged: 32 lanes ×
`values_per_thread = 16` serial FP32 adds over the same K-block order, closed
by the same `simd_sum` over the same 32 lanes. No lane's chain is
re-partitioned. This is the property that separates a geometry change from a
load-width widening, which *does* re-partition the per-lane chain and is not
bit-exact.

**Pre-registered gate.** The harness records a `golden` hash per run. If any
ladder arm's `golden` differs from the control's, that arm is **void** and I
will say so — a bit-exactness argument that fails is a refuted argument, not a
tolerance to be relaxed. I will not report a speed number from an arm whose
golden moved.

## 4. Hypotheses, stated before the data

* **H1 — starvation.** `o_proj` at 256 threadgroups is occupancy- and
  memory-level-parallelism-starved. Finer is monotonically better; `rps=1`
  (1024 TGs) wins; `rps=8` (128 TGs) is clearly worse.
* **H2 — interior optimum.** PR #298/#308 found an interior argmax for the
  QKV grid near ≈640 threadgroups, and PR #309 measured
  `G128 − G640 = +174.9 ± 11.0 µs/step`, i.e. going coarser than the optimum
  is expensive. If the same optimum governs `o_proj`, then `rps=2` (512 TGs)
  or `rps=1` (1024 TGs) is best and the curve turns over somewhere.
* **H3 — null.** The advisor's transfer table prices *threadgroup geometry*
  at **τ ≈ 0**, and my own R107 arm S moved +43.23 µs/step bit-exact on a
  geometry-only change that bought nothing. If `o_proj`'s shortfall against
  peak is not an occupancy deficiency at all, the ladder is flat within noise
  and this arm dies here.

H3 is the honest default. I am pre-committing to it as a live outcome.

## 5. Design

* Instrument: `research/maple-nezuko-r107j-certify.sh`, unchanged.
* Arms, control first: `C` (no gate, shipped `rps=4`), `R1`, `R2`, `R8`,
  `R16`. `R16` was added by the §8 amendment: with `rps ∈ {1,2,4,8,16}` the
  shipped value sits in the **interior** of the ladder, so the design can
  distinguish a plateau from an optimum instead of only reporting an edge.
  Threadgroup counts are 1024 / 512 / 256 / 128 / 64 and dispatched thread
  counts are 65,536 / 32,768 / 16,384 / 8,192 / 4,096.
* Blocks: **5**, position-balanced by the harness's `(b−1) mod NARM`
  rotation, interleaved so drift is charged to every arm equally.
* Reference: each arm is differenced against **its own block's control**.
* Primary endpoint: paired Δ decode µs/step vs control, summarised as a
  summary-measure t interval with dof = blocks − 1.
* Reported alongside, as in Stage 0: the order split (BEFORE/AFTER the
  control), a bootstrap CI on the median, an ASCII histogram of the paired
  differences, and the **raw per-observation array as a CSV under
  `research/data/`**. A number without its raw array is not auditable and I
  will not ask anyone to act on one.

## 6. Decision rule, fixed now

Let `d` be the paired Δ decode µs/step of the best arm (negative = faster).

* **Promote** only if the CI95 **upper** bound of `d` is below
  **−68.7 µs/step**, the Rule 105.12 slot floor. Nothing else earns a slot.
* **Report as a positive but sub-floor effect** if the CI95 upper bound is
  below 0 but above −68.7. This is the outcome I consider most likely if H1
  or H2 holds, because the §0e headroom estimate is −76.5 µs/step and the
  paired interval half-width at 5 blocks will be ≈20 µs. A result that is
  real but too small to seat is a *result*, and it will be labelled that way,
  not rounded up.
* **Record `N-OPROJ-GEOMETRY-FLAT`** if the interval covers zero.
* If any arm is faster but its `golden` moved, the arm is void regardless of
  its number.

## 7. The caveat I will not bury

Even a clean, bit-exact, floor-clearing M4 win in this arm is in the class the
advisor prices at **τ ≈ 0** for transfer to the official hardware. I am
running it anyway for two reasons, and neither of them is "maybe τ is wrong".

1. It is the only remaining falsifiable claim in this family. Stage 0 closed
   bytes; if geometry is also flat, then the 36.5 % of decode busy held by the
   attention projections is *finished*, and saying so with evidence is worth
   more to the campaign than another sub-floor encoder.
2. The τ ≈ 0 price is a claim about *transfer*, not about the mechanism. My
   mechanism claim is falsifiable locally: if `o_proj`'s shortfall is an
   occupancy deficit at 256 threadgroups, a wider machine makes it **worse**,
   not better, and the ladder having an interior argmax on M4 is the first
   test of that. If the ladder is flat, my mechanism claim is dead and I will
   not appeal to hardware I cannot measure.

I cannot measure τ for the geometry class on this machine, and I will not
quote the Stage 0 byte-class ruler as if it licensed this arm. It does not.
The Stage 0 ruler prices **bytes**. This arm moves **none**.

---

## 8. AMENDMENT, ~04:05Z — prior art found after §1–7 were written, and it
## argues against my own leading hypothesis

I ran the Rule 69 archive grep *after* committing §1–7. It changed my priors
enough that leaving §4 as written would be dishonest. The design, the endpoint
and the decision rule in §5–6 are **unchanged**; only the ranking of the
hypotheses moves, and it moves against me.

**(a) The archive explicitly flags this arm as untested and invites it.**
`RESEARCH_ARCHIVE_through-round-91.md` §4.10b, the decode GEMV geometry census
of 2026-08-07, ends: *"o_proj is the geometric outlier at 4 rows/simdgroup and
512 B/thread, 8–16× every other kernel. Whether that is good or bad is
**untested**; it is the natural control for any rows-per-simdgroup arm."*
That is a green light, and it is the reason I am still running the ladder.

**(b) The same census kills the naive occupancy reading, and corrects an
error I had been carrying.** MLX's `metalKernel` `grid:` is a **total-thread**
count, not a threadgroup count
(`Vendor/mlx-swift/.../custom_kernel.cpp:116-117`). So `grid: ((outVec/8)*64)`
= 16,384 **threads** in 256 threadgroups. My patch's
`grid: (tiles * 64, 1, 1)` is correct under that reading — `rps=1` dispatches
65,536 threads in 1024 threadgroups — but the census's own verdict on the
5120-threadgroup QKV kernel was *"there is no occupancy starvation; §4.10a
mechanism (a) is withdrawn as stated; do not assign it."*

**(c) A previous rows-per-simdgroup win went the OTHER WAY.**
`research/maple-occupancy-quantization.md` §4 records that *"nezuko's
rows-per-simdgroup win took a kernel from 42 % to 89 % of the measured
260.2 GB/s DRAM ceiling by raising memory in flight per barrier-bounded
threadgroup."* Coarser was better there. `o_proj` at `rps=4` is already the
coarsest projection in the pool, i.e. it is already the *beneficiary* of that
optimisation, not a victim of it.

**(d) The census also shows thread count alone cannot be the explanation.**
The shared gate/up kernel (:6802) has the *same* 16,384 threads in the *same*
256 threadgroups as `o_proj`, at 1 row/simdgroup instead of 4. If 16k threads
were simply too few, both would be equally starved and rows/simdgroup would be
irrelevant.

**New hypothesis H0-inflight, and it is now the one I consider most likely.**
Let the machine hold on the order of 20 k concurrent threads. At `rps=4` all
16,384 dispatched threads are resident and each carries **4 independent row
load streams**, so ≈65,536 loads can be in flight. At `rps=1` there are 65,536
threads but only ≈20 k resident, each with **1** stream, so ≈20 k loads are in
flight — a ~3× loss of memory-level parallelism for the same work. Under this
model the ladder is **monotone in the opposite direction to H1**: `rps=1`
worst, `rps=8` equal-or-better than the shipped `rps=4`, and the shipped value
already sits on the plateau.

**Consequences I am pre-committing to.**

1. H1 (finer is better) is demoted to the **least** likely of the four
   outcomes. H0-inflight is promoted to first. I would rather write that down
   now than discover it in the data and pretend I expected it.
2. `rps=8` stops being the throwaway "clearly worse" arm of §4 and becomes a
   **serious candidate**; it is the only rung that H0-inflight allows to win.
3. The §0e headroom figure of −76.5 µs/step is an estimate of the *gap to the
   QKV pool's bandwidth*, not a promise that this knob can reach it. If the
   ladder is flat, the gap is real and this knob simply is not the lever; that
   is `N-OPROJ-GEOMETRY-FLAT` and it retires the mechanism, not just the arm.
4. The §0e paragraph in `research/nezuko-r117-stage0-attn-byte-floor.md` that
   attributes o_proj's shortfall to occupancy starvation is hereby marked
   **weakened by (b) and (d)**; it should be read as "the geometry is the last
   unpinned term", not as "the geometry is starved".

## 9. AMENDMENT, ~04:20Z — the arm is now priced against a *measured* τ, and the margin is thin

§1 priced the redirect at "+0.647 %" using τ = 1. The Stage 0b byte-dose ruler has since measured
τ for this exact family on the full model (see `research/nezuko-r117-stage0b-byte-dose-ruler.md`).
Re-pricing before the ladder runs, so the goalposts are fixed in advance:

| quantity | value |
|---|--:|
| o_proj_h64 busy | 37.16 µs/call × 30 = 1114.7 µs/step at 232.9 GB/s |
| o_proj_h48 busy | 30.30 µs/call × 10 = 303.0 µs/step at 214.2 GB/s |
| QKV reference efficiency | 241.9 GB/s (h64), 238.2 GB/s (h48) |
| **full closure to 242 GB/s** | h64 −1.40 µs/call ⇒ −42.0 µs/step; h48 −3.48 µs/call ⇒ −34.8 µs/step; **total −76.8 µs/step** |
| rule 105.12 slot floor | 68.7 µs/step |
| score at τ = 0.80 | `0.75 × 0.80 × 76.8 / 8972` = **+0.514 %** |
| crown bar | **+0.406 %** |

So the arm's *ceiling* — every microsecond of o_proj's bandwidth shortfall recovered — is
**+0.514 %**, clearing the bar by 0.108 pp and the slot floor by 8.1 µs. That is a **26 % margin
on the score bar and a 12 % margin on the slot floor**, both against a ceiling that assumes
*perfect* closure.

**This is stated now, before the ladder runs, because it changes the honest reading of any
positive result.** Consequences I bind myself to:

1. **Partial closure does not pay.** Recovering half the gap is +0.257 %, which fails the bar.
   There is no "encouraging partial win" outcome available here: the ladder either recovers
   essentially all of o_proj's efficiency shortfall, or it produces a negative.
2. **The §6 decision threshold is unchanged**, but I add the explicit note that a rung landing at,
   say, −40 µs/step is a **falsification of the arm's usefulness** even if it is a real and
   statistically clean effect. It gets reported as `N-OPROJ-GEOMETRY-SUBSCALE`, not as progress.
3. **τ enters the price linearly and is now the tightest external dependency.** At the ruler's
   CI95 lower bound the full-closure ceiling is +0.447 %; at the upper bound +0.582 %. The arm
   clears the bar across the whole measured τ interval *only under full closure* — precisely the
   outcome §7 and §8 already argued was unlikely.
4. Combined with §8 (archive #298/#309 and rule 32: the QKV optimum sits near 640 TGs and both
   directions away from an optimum are worse), the honest prior on this arm is now **clearly
   below 50 %**. I am running it because it is the last unpinned term in a family that is
   otherwise closed, and because a clean `N-OPROJ-GEOMETRY-FLAT` retires a mechanism the archive
   itself nominated as "the natural control for any rows-per-simdgroup arm" — not because I
   expect it to win.


## 10. AMENDMENT, ~04:25Z — the mechanism I had wrong, and the second endpoint it buys

Written **before any rps rung was built or run**, after reading the kernel body at
`Sources/MLXFastModel/LagunaRuntimeModel.swift:4348–4416` line by line. §1 framed this arm as
"occupancy / threadgroup count". That framing is incomplete and its sign prediction was probably
backwards. Here is the actual structure:

```
thread float x_thread[values_per_thread];
for (uint k = 0; k < in_vec_size; k += block_size) {
    <loadInput>                                    // <-- ONCE per simdgroup per k-block
    for (uint row = 0; row < results_per_simdgroup; ++row) { ... }   // <-- reuses x_thread
}
```

**The input activation vector is loaded once per simdgroup and reused across all
`results_per_simdgroup` rows.** So `rps` is not primarily a threadgroup-count knob — it is the
**activation-reuse factor**. Simdgroups per call is `out_vec_size / rps = 2048 / rps`, and each
one reads the whole input vector.

| rps | simdgroups/call | threadgroups | activation re-read traffic, MB/step (h64 ×30 + h48 ×10) | Δ vs shipped |
|--:|--:|--:|--:|--:|
| 1 | 2048 | 1024 | 1258.29 | **+943.72** |
| 2 | 1024 | 512 | 629.15 | **+314.57** |
| **4 (shipped)** | 512 | 256 | 314.57 | 0 |
| 8 | 256 | 128 | 157.29 | **−157.29** |

Two consequences.

**(a) My leading hypothesis had the sign wrong.** §1 argued *downward* (rps 4→2→1, more
threadgroups, closer to the archive's 640-TG QKV optimum). But rps=1 **quadruples** the redundant
activation traffic, adding 943.7 MB/step of reads. Those reads are demonstrably cache-served —
if they hit DRAM the o_proj kernels would be moving 16.6 MB/call and running at an impossible
448 GB/s, whereas the census reconciles to 232.9 GB/s on payload+scale alone — but cache-served
is not free. **The promising direction is rps = 8, not rps = 1.** I am leaving rps=1 and rps=2 in
the ladder anyway, for the reason in (b).

**(b) The ladder is a byte-dose ruler for a second, un-measured byte class.** Nobody on this board
has priced *cache-resident activation re-reads*. This ladder does it directly, with a 6× dose
spread (−157 to +944 MB/step) on a knob that is **bit-exact by construction** (§3, now verified at
source level: `out_row = tile·(num_simdgroups·rps) + simd_gid·rps`, every scale pointer is
`out_row`-relative, and the per-row accumulation order over `k` then `j` is untouched by `rps`).
So the arm has a **second, pre-registered endpoint that pays out regardless of the geometry
verdict**:

> **B_act** = Δ(activation re-read bytes) / Δ(wall µs/step), fitted with the same free-intercept
> OLS as the Stage 0b ruler, reported with CI95.

This is a reusable constant: it prices the reuse-factor term in *every* GEMV-shaped kernel on
this model, for every student. If B_act comes back near DRAM speed the reuse factor is a
first-order design variable everywhere; if it comes back at multiple TB/s, tiling for reuse is
near-free and a whole class of arms can be retired cheaply.

**(c) The competing term at rps = 8 is tail quantization.** 128 threadgroups over 20 GPU cores is
6.4 per core, so a naive wave model predicts ceil(6.4)/6.4 ≈ **9.4 % tail loss**, against ≈1.6 %
at rps ∈ {1,2,4}. That is uncomfortably close in size to the ≈8 % efficiency gap this arm is
trying to close, and archive #309 killed a QKV geometry at 128 TGs (`G128 − G640 = +174.9 ± 11.0
µs`). So rps=8 is a genuine two-sided race: **−157.3 MB/step of activation traffic versus a tail
penalty of the same order.** I am not predicting which wins.

**(d) Revised predictions, fixed now.**

* **P1 (activation-reuse model):** wall time is monotone decreasing in rps up to the point where
  the tail penalty takes over. Specifically `Δ(rps=1) > Δ(rps=2) > 0` with a positive, roughly
  linear response in the dose column above.
* **P2:** `rps=8` is the only rung that can produce a positive result, and it needs
  **≥ 68.7 µs/step** (rule 105.12 slot floor) to be reportable at all, **≥ 76.8 µs/step** to hit
  the §9 full-closure price of +0.514 %.
* **P3 (falsifier for the whole framing):** if `Δ(rps=1)` is small — say under 100 µs/step against
  +943.7 MB/step of extra reads — then activation re-reads are essentially free
  (`B_act > 9 TB/s`), the reuse factor is not a performance variable on this machine, and the
  correct verdict is `N-OPROJ-GEOMETRY-FLAT` **plus** a positive, reusable statement that
  reuse-factor tuning is a dead class board-wide. That outcome is a good outcome and I will
  report it as one.
* **P4:** §1's original occupancy framing is **withdrawn as the leading hypothesis** and demoted
  to a competing term, per (c). §9's honest-prior-below-50 % statement stands, but the reason has
  changed: it is now "two opposing first-order terms of similar size", not "prior art says no".

---

## 11. AMENDMENT, 04:45Z — the arm list is frozen here, with the control §10 showed I needed

§10 established that `rowsPerSimdgroup` moves **two** things at once: activation re-use (bytes)
and threadgroup count (tail quantization across 20 GPU cores). A pure `rps` ladder therefore
cannot attribute its own result — exactly the failure mode the byte-dose ruler ran into with its
`OP` rung (`nezuko-r117-stage0b-byte-dose-ruler.md` §3.3), and I would rather pay for the control
up front this time than apologise for its absence afterwards.

So the kernel now carries a **second** knob, `DARKBLOOM_OPROJ_SIMDGROUPS` (`ns`, simdgroups per
threadgroup, default 2 = shipped), and the design is a 2×2 with one cell dropped:

| arm | `rps` | `ns` | simdgroups | **threadgroups** | **activation MB/step** | Δ act vs C |
|---|--:|--:|--:|--:|--:|--:|
| `C` | 4 | 2 | 512 | 256 | 314.57 | 0 |
| `R1` | 1 | 2 | 2048 | 1024 | 1258.29 | **+943.72** |
| `R2` | 2 | 2 | 1024 | 512 | 629.15 | **+314.57** |
| `R8` | 8 | 2 | 256 | 128 | 157.29 | **−157.29** |
| `N4` | 4 | 4 | 512 | **128** | 314.57 | **0** |

**`R8` and `N4` are the whole point.** Both collapse the dispatch to 128 threadgroups. Only `R8`
changes activation traffic. Therefore:

* `R8` moves, `N4` flat ⇒ the effect is **activation re-use**; `B_act` is measurable and the
  §10 byte framing is right.
* `R8` and `N4` move **together** ⇒ the effect is **tail quantization / occupancy**, has nothing
  to do with bytes, and `B_act` is not identified. §1's original framing would be revived, but
  on a mechanism I could not have distinguished without `N4`.
* neither moves ⇒ `N-OPROJ-GEOMETRY-FLAT` (P3), and the reusable statement is that neither
  reuse-factor nor threadgroup-count tuning is a live class on this kernel.

`N4` is a **zero-dose** arm. It is therefore *not* a rung of the `B_act` regression — a
zero-dose point carries no slope information and including it would only inflate the apparent
precision. It is analysed as a **separate paired contrast against `C`**, and the `B_act` fit uses
`R1`, `R2`, `R8` only, with the same free-intercept estimator and the same per-block pairing as
the byte-dose ruler (`DOSES="R1=943.72,R2=314.57,R8=-157.29"`).

**Design:** 5 arms × 5 blocks = 25 runs, ≈ 155 s/run ≈ **65 min**. Rotation of arm order within
block, SPLIT=0, per-arm kernel-set stability, `Package.resolved` restored per run.

**Pre-flight, run before the campaign and reported with it:** every arm must produce the
shipped golden hash `f49e4c2cbc0d3ceee9…`. §3's bit-exactness claim is a source-level argument
(the geometry re-assigns rows to simdgroups but leaves each row's k-then-j accumulation order
and its closing `simd_sum` untouched); the pre-flight is what turns it into evidence. If any arm
misses the hash, the ladder does not run.

**Rule 33** is satisfied at the source level: `lagunaOProjRowsPerSimdgroupSuffix` is appended to
all four o_proj kernel-name literals and is distinct for every `(rps, ns)` pair
(`_rps1ns2`, `_rps2ns2`, `_rps8ns2`, `_rps4ns4`; shipped `rps=4, ns=2` keeps the bare name), so
no two arms can collide in MLX's name-keyed pipeline cache.

**`ns = 1` is deliberately not offered.** The gated-affine prologue fills a threadgroup array
under `if (lid < gate_heads)`; a 32-thread threadgroup would leave the upper gate entries
uninitialised and corrupt output silently rather than fail a hash check.

