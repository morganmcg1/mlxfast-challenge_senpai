# R125-C — threads-per-threadgroup granularity for the routed expert QMV

Assignment `maple-r125-c-expert-qmv-tg-granularity`, revision `r125-c-rev1`, PR #731.
Base `codex/mlxfast-maple-20260804-advisor` @ `a9de9e8f21188715f6d80ada4b581bcd50d4ec81`.
Branch `maple-edward/r125-c-expert-qmv-tg-granularity`.
Host: Apple M4 Pro, 20 GPU cores, Apple GPU generation 16 (not the ranked M5).

## 0. Verdict

**Hypothesis REFUTED. Land nothing.**

36 runs × 512 decode steps, six palindromic slot-balanced blocks, median block
bootstrap (B=20000, seed 125).

| arm | threads/TG | median Δ vs A | bootstrap CI95 | verdict |
|---|---|---|---|---|
| B | 128 | **−3.77 µs/token** | [−11.26, +23.40] covers zero | **NULL** |
| D | 256 | **+23.12 µs/token** | [+15.77, +38.31] excludes zero | **regression, −0.282 % decode** |
| same-arm null (A vs A) | 64 | −3.21 µs/token | [−43.00, +3.50] | instrument noise floor |

The decisive number is the last row: **the same-arm null, measuring
byte-identical work against itself, produces −3.21 µs — statistically the same
"win" as B's −3.77 µs.** B is indistinguishable from the instrument's own noise.
D is a real, reproducible loss (slower in all 6 blocks, sign test p = 0.0312).

Correctness: **0 nonzero divergences across all 36 runs × 512 checked greedy
tokens**, plus bit-identical teacher-forced logits and free-run token streams
across all three widths in the standalone quickcheck.

**Nothing is proposed for landing.** The compiled default is 64 (unchanged); the
env guard accepts only `128`/`256`; with the variable unset the **default build
is byte-identical to the base**. The advisor's "a winning rung must flip the
compiled default" rule was implemented and then reverted, because no rung won.

The durable output of R125-C is the mechanism in §4 and the precondition in
§4.4: **threadgroup widening pays on a DRAM-bound QMV only when all rows in a
threadgroup map to one contiguous weight region.** The routed expert QMV
interleaves expert slots modulo 8, so widening multiplies concurrent
1-MiB-separated DRAM streams per threadgroup while only saving non-bottleneck
L2→L1 activation traffic. That is why frieren's and alphonse's shared-QMV wins
do not transfer here.

### 0.1 N1-orthogonality verdict — **ORTHOGONAL** (blocking deliverable)

This work does not touch, depend on, or perturb N1 (the promoted leader's fused
sorter sidecar, organizer commit `4ea72c3`, score 2.6195531094824), on four
independent source-cited grounds. **(a) Different dispatch mechanism.** The
routed gate/up QMV is a hand-written `MLXFast.metalKernel` dispatch, not an MLX
quantized-matmul primitive; its call site
`Sources/MLXFastModel/LagunaRuntimeModel.swift:8330-8343` passes exactly four
buffers `[input, fusedWeight, packedScales, routerKeys]` with
`grid: (numExpertsPerTok*256*64, 1, 1)` = 131,072 and
`threadGroup: (threads, 1, 1)` — **no** expert-prefix/bounds sidecar, sort
output, expert-index carrier, pairwise-scale layout, gather geometry, or warmup
is read or written, and `routerKeys` is the pre-existing 256-entry
(`numExperts`) uint32 router input, *not* N1's 257-entry prefix sidecar.
**(b) Structurally unobservable on this host.** N1 lives in the NAX gather-QMM
path gated by `metal::is_nax_available()`
(`Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/quantized.cpp:728, 951,
1669, 1906`; N1's `GatherQMM::eval_gpu` hunk at ~`:1906`/`:1991` sits inside
`sorted_rhs && metal::is_nax_available() && transpose_ && …`), defined at
`.../metal/device.cpp:913-932` and declared at `device.h:246`. This M4 Pro
reports Apple GPU generation 16 and never selects `_nax`, so no measurement here
could have been contaminated by N1 in either direction. **(c) No textual
overlap.** `git diff a9de9e8f 18ac6015 -- .../LagunaRuntimeModel.swift` is 24
insertions / 3 deletions with hunks at lines **230, 10789, 12431** — over 2,400
lines away from this work's 8056–8343 region. **(d) Clean rebase confirmed.**
`git apply --check --3way /tmp/r125c-hunk.patch` against the new Maple advisor
head `18ac6015c6c2c52ae2fa8830b23d249b35b6f448` reports "Applied patch to
'Sources/MLXFastModel/LagunaRuntimeModel.swift' cleanly." **Since the verdict is
"land nothing", the rebase is moot in practice — but it was verified anyway so
the negative result is portable to the new base without re-measurement.**

Corroborating audit, cited with attribution as the advisor permitted: frieren's
static audit of the shipped decode path found that the only `_nax` gate in the
model sources — `lagunaNAXAvailable` (LRM `:242-247`) via
`lagunaExpertAlignedGatherEnabled` (`:253-265`) — is read only at `:10807`,
`:10982`, `:10995`, all **prefill** sorted-gather sites, none on the decode MoE
gate or up. The narrower claim that remains mine is (a) above: the specific
generator and dispatch lines this hunk changes read no 257-entry prefix/bounds
sidecar and make no EG256 selection.

Base-drift note: the advisor branch has since moved to
`9ef3bfcbcd81fc7fd41db7608c8c8adba0a98123`, but
`git diff --name-only 18ac6015 9ef3bfcb -- Sources Vendor benchmark.json` is
empty (manifest and tools only), so every source anchor above holds unchanged on
that head too.

### 0.2 Collision flag vs alphonse PR #729 — **NO COLLISION**

Explicitly flagged as the advisor required. alphonse's TG=256 landing (+0.38 %,
18 runs, bit-identical) edits the **shared** expert QMV; this work edits the
**routed** expert QMV. Same file, disjoint regions, no semantic interaction:

| | alphonse #729 (shared QMV) | R125-C (routed QMV) |
|---|---|---|
| Swift symbols | `lagunaSharedSwiGLUQMVHeader`, `lagunaSharedSwiGLUQMVRows1Source`, `…Rows1Kernel` / `…HalvedKernel` / `…WideKernel` | `lagunaRoutedSwiGLUQMVPackedTop8R1Source`, its pipelines, `lagunaRoutedSwiGLUQMVPackedTop8` |
| LRM lines | `:295`, `:6900`, `:7042`, `:7118`, `:7131`, `:7215-7229`, `:7239` | `:8056-8105`, `:8205-8230`, `:8271-8274`, `:8330-8340` |
| env knob | `DARKBLOOM_SHARED_QMV_TG` (untouched here) | `DARKBLOOM_ROUTED_QMV_TG` (new) |
| generated Metal source | shared-expert source string | routed-expert source string |

Different Swift functions, different generated Metal source strings, different
pipeline constants, different dispatch call sites, ~800+ lines apart. The one
place the two families could meet is `lagunaSharedRoutedSwiGLUQMV`
(`:8271-8274`), and the grid-append added there is guarded by
`lagunaRoutedQMVThreadsPerThreadgroup == 64`; that fused path is itself opt-in
via `DARKBLOOM_SHARED_ROUTED_QMV_FUSED == "1"` (`:8231`) and **off by default**
(held at `0` throughout this campaign, as instructed). alphonse's
`DARKBLOOM_SHARED_QMV_TG` and nezuko's `DARKBLOOM_QKV_ROWS_PER_SIMDGROUP` were
never read or written. **Risk to #729 from R125-C: zero — and zero regardless,
since R125-C lands nothing.**

## 1. Bandwidth census and candidate admissibility

The advisor gate asks for achieved bandwidth divided by the measured streaming
peak, per candidate kernel, *before* choosing a target. All numbers below come
from an earlier same-host census, not from new measurements.

Source: `research/maple-edward-r110/STAGE0-QMV-BANDWIDTH.md`, captured on base
`ad3773a0a188cad3e4ac97479dd7da31341d41ab` on this same M4 Pro. The streaming
peak table at `:139-144` gives a median of **256.7 / 256.9 GB/s** over the two
sweep directions (best 259.2 / 260.0).

| kernel | bytes/dispatch | real µs/call | achieved GB/s | % of 256.7 GB/s peak | % of own short-dispatch ceiling |
|---|---|---|---|---|---|
| K1 routed gate/up `..._top8keys_r1_bf16_v2` | 8,912,896 | 38.44 | 232.0 | **90.4 %** | 93.5 % |
| K4 routed+shared down/residual `..._sh_stage4_v6` | 5,013,504 | 22.09 | 227.6 | 88.7 % | **96.7 %** |
| K2 decode qkv h64 | 10,823,680 | 44.73 | 242.1 | 94.3 % | 95.4 % |
| K3 oproj qmv h64 | 8,652,800 | 37.15 | 233.4 | 90.9 % | 93.9 % |

Byte derivations at `STAGE0-QMV-BANDWIDTH.md:118-123`, per-call timings at
`:94-97`, achieved GB/s at `:173`, short-dispatch ceilings at `:146-173`.

A second, independent capture agrees: `research/maple-alphonse-r109e-bwatlas.txt`
rows 7/8/20/29 (that script assumes a 273.0 GB/s peak,
`research/maple-alphonse-r109e-bwatlas.py:38`, so its percentages are lower by
construction but the *ordering* is the same).

**Reading of the gate.** The two reference points on this host are K2 decode qkv
(94.3 % of peak, 95.4 % of its own ceiling), where nezuko's threadgroup ladder
returned a null, and K3 oproj (90.9 % / 93.9 %), where the equivalent ladder
won. K1 routed gate/up sits at 90.4 % / 93.5 % — on the *winning* side of both
reference points, and it is the least bandwidth-saturated of the four. It is
therefore admissible under the advisor's ">~93 % of measured peak ⇒ expect a
null" rule, and it is the best available candidate in this family.

The fused routed+shared down/residual kernel (K4) looks attractive on raw
%-of-peak (88.7 %, the lowest of the four) but it is at **96.7 % of its own
short-dispatch ceiling** — the least headroom in the table. That kernel is a
worse candidate than the raw column suggests, which is why the ladder below
targets K1 only and the K4 tiles-per-threadgroup arm was deprioritised.

### Verified kernel arithmetic

The model has **39 MoE layers** out of 40: `mlp_only_layers=[0]` and
`decoder_sparse_step=1` (`Sources/MLXFastModel/LagunaConfig.swift:544-548`,
`:855-865`). hiddenSize 2048, numExperts 256, numExpertsPerTok 8,
moeIntermediateSize 512.

Routed gate/up QMV per decode token, per layer:

- grid **131,072 threads** = 4,096 simdgroups = 8 expert slots × 512 rows;
- per row: 1,024 B gate + 1,024 B up + 128 B scales = 2,176 B;
- × 4,096 rows = **8,912,896 B/dispatch**, matching the census;
- × 39 layers = **347.6 MB/token** of routed gate/up weight traffic alone.

The activation row is 2,048 bf16 = **4,096 B** and is bit-identical for every
simdgroup in the dispatch. It is read once per *threadgroup* out of L2 into L1:

| threads/TG | simdgroups/TG | TGs/dispatch | L2→L1 activation fills/dispatch | per token (×39) |
|---|---|---|---|---|
| 64 (shipped) | 2 | 2,048 | 8.39 MB | 327 MB |
| 128 | 4 | 1,024 | 4.19 MB | 164 MB |
| 256 | 8 | 512 | 2.10 MB | 82 MB |

DRAM traffic for that row is 4,096 B once — it lives in L2 — so the saving is
**L2→L1**, exactly the mechanism frieren reported for `lagunaSharedSwiGLUQMV`
in R119-C. Weight traffic (the 347.6 MB/token) is untouched by the ladder.

### Wave arithmetic

| threads/TG | TGs | TGs/core @ C=20 (this host) | tail | TGs/core @ C=40 (M5 Max) | tail |
|---|---|---|---|---|---|
| 64 | 2,048 | 102.4 → 103 | 0.6 % | 51.2 → 52 | 1.6 % |
| 128 | 1,024 | 51.2 → 52 | 1.6 % | 25.6 → 26 | 1.5 % |
| 256 | 512 | 25.6 → 26 | 1.5 % | 12.8 → 13 | 1.5 % |
| 512 | 256 | 12.8 → 13 | 1.5 % | 6.4 → 7 | 8.6 % |

512 threads/TG is excluded from the ladder: on a 40-core M5 it would leave an
8.6 % tail-imbalance, which is why 256 tops the ladder on both core counts and
why the ladder stops there.

## 2. Code change

All edits are in `Sources/MLXFastModel/LagunaRuntimeModel.swift`, an
`editablePaths` entry.

1. **`lagunaRoutedQMVThreadsPerThreadgroup` (`:8059`)** reads
   `DARKBLOOM_ROUTED_QMV_TG` and accepts only `128` or `256`; anything else
   (including unset) yields **64**, the shipped value. The default build is
   therefore byte-identical to base.

2. **`lagunaRoutedSwiGLUQMVPackedTop8R1Source(simdgroupsPerThreadgroup:)`
   (`:8067`)** emits the original source text unchanged when `S == 2`. For
   `S > 2` it recovers the shipped *global* simdgroup ordinal:

   ```metal
   uint laguna_simd_ordinal = groupExpr * S + simdgroup_index_in_threadgroup;
   uint group      = laguna_simd_ordinal / 2;
   uint simd_group = laguna_simd_ordinal % 2;
   ```

   Every simdgroup therefore computes exactly the same `(group, simd_group)`
   pair, and hence the same output row, as it did at 64 threads/TG. The grid is
   unchanged at 131,072 threads, so the set of ordinals is unchanged. This is
   the bit-identity argument; it is confirmed empirically in §3.

3. **Name-suffixed pipelines.** The factory
   `lagunaRoutedSwiGLUQMVPackedTop8R1Kernel(threadsPerThreadgroup:)` (`:8207`)
   builds `..._r1_bf16_v2_tg128` / `_tg256`, and
   `lagunaRoutedSwiGLUQMVPackedTop8R1WideKernel` (`:8224-8228`) is `nil` at 64.
   Distinct names matter: MLX keys its per-process library and PSO cache on the
   generated kernel name (`Vendor/mlx-swift/.../metal_kernel.cpp:289-316`), and
   a same-name-different-source pair triggers `clear_library` and a recompile on
   *every* alternation (`custom_kernel.cpp:56-69`). Threadgroup size itself is
   **not** part of any cache key (`fast_primitives.h:418`; it is used only at
   encode time, `custom_kernel.cpp:102-115`).

4. **Dispatch (`:8330-8340`)** selects `(Wide ?? base)`, sets
   `threadGroup: (threads, 1, 1)`, leaves the grid at 131,072, and emits
   `lagunaTrace("routed gate/up QMV r1 tg\(threads)")` for reachability proof.

5. **`lagunaSharedRoutedSwiGLUQMV` grid-append is guarded** by
   `lagunaRoutedQMVThreadsPerThreadgroup == 64` (`:8274`) so the wide arms never
   silently fall into a different fusion. That fused path is itself opt-in
   (`DARKBLOOM_SHARED_ROUTED_QMV_FUSED == "1"`, `:8231`) and is **off by
   default**, so all arms share the same append state without any extra
   environment variable. Verified in the trace, §3.

### Reachability correction to the assignment

The assignment's priorities #2 `lagunaSharedDownResidual` and #3
`lagunaRoutedDownReduce` are **fallback paths only** on this base.
`DARKBLOOM_FUSED_ROUTED_SHARED_DOWN_RESIDUAL != "0"` (LRM ~`:144`) makes the
288-thread fused routed+shared down kernel
(`lagunaRoutedSharedDownResidualSource` `:8506`, dispatch `:8875-8880`) the live
default: it is tried at `:11144-11177` and the unfused pair is only reached at
`:11179`. A threadgroup knob on #2/#3 would not have been on the scored path.

## 3. Measurements

### 3.1 Campaign shape

`research/edward_r125c_ladder.sh`, 36 runs × 512 decode steps, six palindromic
slot-balanced blocks, `ORDER=ABDDBABDAADBDABBADADBBDADBAABDBADDAB`, first 16
steps trimmed per run. Arms:

| arm | `DARKBLOOM_ROUTED_QMV_TG` | effective threads/TG | simdgroups/TG |
|---|---|---|---|
| A | *unset* (compiled default) | 64 | 2 |
| B | `128` | 128 | 4 |
| D | `256` | 256 | 8 |
| N | *unset* (negative control, identical to A) | 64 | 2 |

`DARKBLOOM_SHARED_ROUTED_QMV_FUSED` was held at `0` for every run, so all arms
share one append state. That is now evidence-backed rather than merely prudent:
frieren's #733 measured the fused path as a **loss** (+55.2 µs/step, 95 %
[+18.9, +85.9], score −0.323 %, W&B `6r8i5rcg`). No part of this work is
designed to pay off only under the fused path.

Raw: `research/maple-edward-r125c/ladder_raw.csv` (18,396 per-step samples,
36 runs × steps 1–511), `research/maple-edward-r125c/ladder_runs.tsv` (36 rows),
`research/maple-edward-r125c/bootstrap_report.txt`. Analysis:
`research/edward_r125c_bootstrap.py` (percentile block bootstrap, B=20000,
seed=125, statistic = **median** paired per-block delta).

W&B: run `lv9kmuzw`,
<https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/lv9kmuzw> — every
per-step sample, per-run/per-block/contrast tables, the same-arm null, and the
raw artifacts. Publication script: `research/edward_r125c_wandb.py`, which
re-derives all statistics from the raw CSV so the run and this memo cannot
drift.

### 3.2 Correctness

**36 / 36 runs, 512 checked greedy tokens each, 0 nonzero divergences.**
`awk` over the `divergences` column of `ladder_runs.tsv` sums to exactly 0 for
every run id. The earlier standalone identity check
(`research/edward_r125c_quickcheck.sh`) independently confirmed bit-identical
teacher-forced logits *and* free-run token streams across tg 64/128/256, with
the reachability traces `routed gate/up QMV r1 tg64|tg128|tg256` firing and the
fused shared+routed append absent in all three. Threadgroup width does not
change a single output bit, as expected: each simdgroup owns one logical row
and reduces over it independently, so widening only changes how many rows ride
in one threadgroup.

### 3.3 Arm levels

Mean of per-run medians: **A 8.1982, B 8.2005, D 8.2246 ms/step**. Mean of
per-block medians (the aggregation logged to W&B, which weights blocks rather
than runs): **A 8199.68, B 8202.47, D 8225.41 µs/token**. Both orderings agree;
neither is the inferential statistic, which is the paired per-block median delta
below. Per-block medians (µs/token):

| block | A | B | D |
|---|---|---|---|
| 1 | 8209.42 | 8197.52 | 8225.67 |
| 2 | 8201.92 | 8191.29 | 8225.67 |
| 3 | 8171.33 | 8219.15 | 8223.67 |
| 4 | 8206.54 | 8200.33 | 8221.83 |
| 5 | 8205.21 | 8204.19 | 8227.71 |
| 6 | 8203.65 | 8202.31 | 8227.94 |

### 3.4 B (128 threads/TG) — NULL

| statistic | value |
|---|---|
| per-block B−A (µs/token) | −11.90, −10.62, **+47.81**, −6.21, −1.02, −1.33 |
| median Δ (point estimate) | **−3.77 µs/token** |
| bootstrap CI95 | **[−11.26, +23.40]** — **covers zero** |
| sign test | 5 neg / 1 pos, exact two-sided p = 0.2188 |
| relative decode | +0.0460 % |
| implied φ (decode-only) | 1.000345 |

### 3.5 D (256 threads/TG) — REPRODUCIBLE REGRESSION

| statistic | value |
|---|---|
| per-block D−A (µs/token) | +16.25, +23.75, +52.33, +15.29, +22.50, +24.29 |
| median Δ (point estimate) | **+23.12 µs/token** |
| bootstrap CI95 | **[+15.77, +38.31]** — **excludes zero** |
| sign test | 0 neg / 6 pos, exact two-sided p = 0.0312 |
| relative decode | **−0.2820 %** |
| implied φ (decode-only) | **0.997890** |

D is slower in **every** block. This is the cleanest signal in the campaign and
it points the wrong way.

### 3.6 Same-arm null — the instrument's own noise floor

The decisive control. Two byte-identical A runs inside each block, contrasted
against each other:

| block | early A | late A | Δ (µs/token) |
|---|---|---|---|
| 1 | run 1 = 8219.46 | run 6 = 8200.58 | −18.87 |
| 2 | run 9 = 8203.75 | run 10 = 8200.12 | −3.62 |
| 3 | run 14 = 8202.83 | run 17 = 8135.71 | **−67.13** |
| 4 | run 19 = 8205.83 | run 24 = 8207.17 | +1.33 |
| 5 | run 27 = 8203.00 | run 28 = 8208.67 | +5.67 |
| 6 | run 32 = 8205.58 | run 35 = 8202.79 | −2.79 |

median null Δ = **−3.21 µs/token**, null CI95 = **[−43.00, +3.50]**,
max |null Δ| = **67.13 µs/token**.

**B's point estimate (−3.77 µs) is numerically indistinguishable from the
same-arm null's point estimate (−3.21 µs).** The instrument, measuring
identical work against itself, produces the same "win" B produces. B is a null,
not a small win. D (+23.12) lies outside the null band on the slow side, which
is why D survives as a real effect.

Block 3 is the campaign's one anomalous block: run 17 (arm A) has median 8.1357
with mean 8.1210 — mean below median, i.e. a burst of unusually fast steps
rather than the usual slow tail. It contaminates block 3 for *both* contrasts
(B−A = +47.81, D−A = +52.33, and the same-arm null = −67.13), which is exactly
the signature of an arm-independent host event. The median-of-blocks statistic
absorbs it; the mean does not — the mean B−A is +2.79 µs, entirely driven by
this one block. That divergence between mean and median is itself the reason
the pre-registered statistic was the median.

### 3.7 Step-0 excess is not arm-correlated

Earlier quickcheck raised the worry that a wider threadgroup pays a larger
first-dispatch JIT/PSO penalty. Step-0 wall per arm across runs:
A 9.31 / 9.36 / 9.53 / 12.41 ms, B 9.32 / 9.36 / 9.55 ms, D 9.33 / 9.36 / 25.40
ms. The distributions overlap; the two outliers (A 12.41, D 25.40) are one per
arm and are host events, not a width effect. **Resolved as noise — no warmup
mitigation is needed and none was added.**

### 3.8 Process lesson: the early read was drift-aliased

At n = 5 runs/arm the arms looked *perfectly rank-separated* in B's favour:
max(B) = 8.197 < min(A) = 8.199, i.e. every B run beat every A run. That
ordering **inverted by n = 8**. The apparent separation was slow host drift
aliasing onto an incompletely balanced order. Only the six-block palindromic
design plus the median block bootstrap plus the same-arm null exposed it.
Recording this explicitly because the failure mode is silent: a five-run
"clean sweep" on this host is not evidence, and would have shipped a null as a
+0.05 % win.

### 3.9 What was *not* measured, and why

No `--local-iterate` scored-harness run and no upstream-equivalence run were
executed for the final state, because **the final state's default build is
byte-identical to the base**: the compiled default remains 64 and the guard at
`:8059-8065` accepts only `128`/`256` from the environment, so with the
variable unset the generated Metal source, pipeline set, and dispatch are the
base's. There is nothing new to gate. (On this host the scored prefill speedup
lands near 0.33 on *every* arm including unmodified base — a structural gen-16
property of this box, not an arm effect — and
`research/run_upstream_equivalence.sh` exits 1 on a pre-existing prefill
`maximumAbsoluteLogitError` of 0.125 on the unchanged base. Neither is caused
by this work. `MLXFAST_LOCAL_ALLOW_GOLDEN_DRIFT=1` was never set.)

## 4. Mechanism — why widening *this* kernel cannot pay

### 4.1 The expert-slot interleaving

`Sources/MLXFastModel/LagunaRuntimeModel.swift:8078-8079` (mirrored at
`:7521-7525`):

```
constexpr uint routed_experts = 8;
uint expert_slot = group % routed_experts;
uint tile        = group / routed_experts;
uint logical_row = tile * 2 + simd_group;
```

with `fused_expert_bytes = 1024 * fused_row_bytes` = **1 MiB** per expert slot.

Expert slots are **interleaved modulo 8 across consecutive `group` values**.
That single fact decides the experiment. A threadgroup of `S` simdgroups spans
`S/2` consecutive `group` values, hence:

| threads/TG | simdgroups S | `group` values per TG | **distinct expert weight regions per TG** |
|---|---|---|---|
| 64 | 2 | one | **1** (contiguous) |
| 128 | 4 | two | **2**, 1 MiB apart |
| 256 | 8 | four | **4**, 1 MiB apart |

Widening the threadgroup therefore multiplies the number of *concurrent,
1-MiB-separated DRAM streams* a single threadgroup must keep in flight.

### 4.2 Why the intended benefit is off the critical path

The intended win is activation reuse: a wider threadgroup fetches the 4,096-byte
bf16 activation row once for more consumer rows. Per dispatch that reduces
L2→L1 activation fill from 8.39 MB (64) to 4.19 MB (128) to 2.10 MB (256);
across 39 MoE layers, 327 → 164 → 82 MB per token.

But that traffic is **L2→L1**, not DRAM. The kernel is DRAM-bound *on weights*:
K1 runs at **232.0 GB/s = 90.4 % of this host's 256.7 GB/s streaming peak** and
93.5 % of its own short-dispatch ceiling (§1). Weight bytes dominate: per
logical row 1024 B gate + 1024 B up + 128 B scales = 2,176 B, ×4,096 simdgroups
= 8,912,896 B per dispatch, 347.6 MB/token over 39 layers. The activation row is
4,096 B *total* per dispatch — three orders of magnitude smaller.

So the benefit lands on a resource that is not the bottleneck, and the cost —
2× / 4× more simultaneous far-apart DRAM streams per threadgroup, degrading
per-threadgroup access locality and prefetch behaviour — lands directly on the
one that is. The measured outcome follows exactly: **128 buys nothing
measurable (null), 256 pays the locality cost twice over and loses 0.28 %.**

Occupancy is not the explanation. Threadgroup counts are 2048 / 1024 / 512 for
64 / 128 / 256 threads; at 20 cores that is 102.4 / 51.2 / 25.6 waves — all
comfortably above the tail-quantisation regime (this is why 512 threads/TG was
excluded from the ladder in the first place: 6.4 → 7 waves is an 8.6 % tail on
an M5's 40 cores).

### 4.3 Why frieren's shared-QMV win does not transfer

frieren's threadgroup widening won on the **shared** expert QMV. The shared
expert has a **single** weight matrix. Widening its threadgroup adds **zero**
extra weight streams while still buying the activation reuse — benefit without
the cost. The routed QMV is the same kernel *shape* with a different *memory
map*, and the memory map is what decides it.

### 4.4 The general precondition this establishes

> **Threadgroup widening pays on a DRAM-bound QMV only when all rows inside a
> threadgroup map to one contiguous weight region.** Where row→weight mapping is
> interleaved, widening trades a non-bottleneck saving (activation L2→L1 fill)
> for a bottleneck cost (concurrent DRAM stream count), and the trade is
> negative.

This predicts frieren's shared-QMV win (contiguous → pays), alphonse's shared
TG=256 landing in PR #729 (contiguous → pays), nezuko's decode-qkv null
(already at 94.3 % of peak, no headroom), and this routed null/regression
(interleaved → does not pay). It is the reusable output of R125-C.

## 5. Deviations from the assignment

1. **Priorities #2 and #3 were not measured.** `lagunaSharedDownResidual` and
   `lagunaRoutedDownReduce` are fallback-only on this base; the 288-thread fused
   routed+shared down kernel is the live default (see the reachability
   correction in §2). A threadgroup knob there would not have reached the scored
   path, which the assignment itself forbids.
2. **Arm A is *unset* environment, not `DARKBLOOM_ROUTED_QMV_TG=64`.** This is
   deliberate: it makes the reference arm the literal shipped default build,
   including the `nil` wide-kernel slot, rather than a nominally-equal env
   configuration.
3. **512 threads/TG was excluded** by design (wave-tail quantisation on the
   ranked M5, §4.2).
4. **No compiled default was flipped, because no rung won.** The advisor's rule
   that a winning rung must flip the compiled default was implemented and then
   fully reverted: I did flip the default to 128 at one point, then reverted it
   once the completed ladder showed B is a null. Current shipped state: compiled
   default 64, guard accepts only `128`/`256` from the environment, **default
   build byte-identical to base**. Nothing is proposed for landing.
5. **No official submission was fired**, per the advisor's instruction.

## 6. Next steps (flagged, not implemented)

1. **Reindex, then widen — the primary follow-up.** Change the routed QMV
   mapping so a threadgroup's rows fall inside *one* expert:
   `expert_slot = group / tiles; tile = group % tiles` (blocked instead of
   interleaved), then widen to 128/256. This preserves the activation reuse
   *and* restores weight locality, and remains bit-identical per row because
   each simdgroup still reduces over exactly one logical row — only the
   row↔group assignment changes. Deliberately **not** implemented here: it
   would combine two unmeasured mechanisms in one candidate, which AGENTS.md
   explicitly warns against, and there was no time left to measure them
   separately. It needs its own assignment with the reindex measured alone at
   64 threads first.
2. **Do not land threadgroup widening on the routed QMV** in its current
   layout, at any width. 128 is a null on a 36-run ladder; 256 is a
   reproducible −0.28 % regression.
3. **Reuse the same-arm null control** in every future timing ladder on this
   host. It cost four extra runs and was the single control that prevented
   shipping a null as a win (§3.6, §3.8).
4. **Apply the §4.4 precondition as a triage filter** before spending a ladder:
   check the row→weight map for contiguity first. It is a five-minute source
   read that would have predicted this result.
