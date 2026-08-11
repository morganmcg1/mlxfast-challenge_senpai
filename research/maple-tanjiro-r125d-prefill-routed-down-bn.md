# R125-D — Prefill: N-tile width (BN) for the routed/shared **down** gather GEMM

Student: `maple-tanjiro` · PR #732 · assignment `maple-r125-d-prefill-routed-down-bn`
(revision `r125-d-rev1`) · base `codex/mlxfast-maple-20260804-advisor`
@ `a9de9e8f21188715f6d80ada4b581bcd50d4ec81`.

---

## §0 Verdict

**Verdict: do not ship `BN = 128`. The default stays 64.** This is a negative /
inconclusive result, and the reason is a static finding this experiment produced,
not a timing measurement.

The occupancy case for a wider N tile is real and reproduces (§1). What the
census missed on the first pass is that **`BN` is not a single lever**: it also
selects the *width of the device weight load* inside `QuantizedBlockLoader`.
`n_reads = (BCOLS_PACKED · BROWS)/tgp_size = BN/4` and
`kSrcBytes = n_reads · bytes_per_pack`, and the loader's vectorized load bodies
exist only for `kSrcBytes == 16` and `kSrcBytes == 8`
(`fp_quantized_nax.h:438,444`), both behind `if constexpr`. At BN=128
`kSrcBytes = 32`, so **neither body is emitted** and the 5.74 GB/forward routed
+shared down weight stream is staged with per-byte device loads while the kernel
name still advertises `_ws_1_wl_1`. The emitted AIR confirms it: BN=64 has one
16 B `memcpy` from `addrspace(1)`, BN=32 an 8 B `i64` load, BN=128 **none**, plus
a 32-byte `sb[]` scratch array and 8 scalar threadgroup stores where 64 has one
16 B store (§2b, `research/artifacts/tanjiro-r125d/wide-load-census.txt`).

That is a first-order, unmeasured loss on *exactly the stream the hypothesis
targets*. The predicted gain was **+0.53 %**, only ≈0.3 σ above the +0.378 %
that a crown-beating draw needs and about 1.1 σ of receipt noise; netting an
unquantified narrowing of the weight-load width against it makes the sign of the
draw unknown. Spending an official draw on that would be spending it on a
confound, so the code change is reverted to `64` and the lever is handed back as
a **two-part follow-up** (§7): fix the loader to do a chunked 2 × 16 B load at
`kSrcBytes == 32`, *then* re-run the rung with load width held fixed.

| item | value |
| --- | --- |
| branch | `maple-tanjiro/r125-d-prefill-routed-down-bn` |
| base SHA | `a9de9e8f21188715f6d80ada4b581bcd50d4ec81` |
| assignment commit | `ff51ac2c705e830ae9bb2871939f6fe65be147b9` |
| submitted path (1) | `Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/quantized.cpp` |
| behavioural diff vs base | **none** — `darkbloom_expert_down_bn()` still defaults to 64; only the env ladder gained `128` as a reachable rung, plus the comment recording why it is off |
| research-only paths | `research/maple-tanjiro-r125d-*.{py,sh,swift,md}`, `research/artifacts/tanjiro-r125d/**` |
| scope gate | `assignment scope OK: 1 submitted path(s)` |
| editable budget | `current=2700206/3000000 headroom=299794 growth=561/262144 files=143 (base=143)` |
| W&B run | [`1nd4yw9s`](https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/1nd4yw9s) (census tables, occupancy ladder, score prediction, paired A/B) |

**What is worth keeping from this experiment**

1. The AIR/occupancy census of the three rungs, and the arithmetic that shows the
   down shape runs at ≈398 GB/s against a 546 GB/s ceiling — a **3.91 ms**
   addressable pool on weights alone, or **≈2.4 ms** once the kernel's own `y`
   stores and unique `x` reads are added to the floor (§2, §8 item 5). All of it
   is prefill.
2. The `kSrcBytes` finding itself, which retires the "BN is a free knob"
   assumption for **every** rung of this loader and also explains why the
   `BN = 32` falsifier arm was never clean (32 → 8 B, 64 → 16 B: two levers).
3. The redirect: `SM = 16` row fragments against ≈16 real rows per expert puts
   ≈31.3 % of this shape's MMA work on padding, ≈**11 ms** — ≈3× the 3.91 ms BN
   pool, ≈4.5× the corrected one. That is a BM/WM experiment (R107-C §8), and it
   is the better next draw.

`bn32.patch` under `research/artifacts/tanjiro-r125d/` is retained only as a
reproduction aid for the census; it is **not** a candidate arm.

---

## §1 Lever choice and census arithmetic

### The shape

`gather_qmm_rhs_nax` serves three Laguna MoE shapes. The **down** projection is
the only one whose BN is *free*:

* down: `K=512, N=2048`, plain BN-wide `Dtile` slices in the epilogue;
* fused gate/up: `K=2048, N=1024`, the SwiGLU epilogue pairs column `c` with
  `c + BN/2` and writes `N/2` columns — its `BN == 64` is a **correctness lock**
  (`kSwigluRegLocal`), not a tuning knob.

The override at `quantized.cpp:1392-1399` is restricted to the down shape
(`K == 512 && N == 2048`), so raising the down BN cannot touch the locked shape.

### Census (M4 AIR, three instantiations)

`research/maple-tanjiro-r125d-air-census.py` reads
`xcrun air-objdump --disassemble` output for the JIT source that
`darkbloom_expert_down_bn()` selects (`research/maple-alphonse-r107c-jit-air.sh`
emits the exact instantiations). Rows per layer = 512 prefill tokens × 8 routed
experts = **4 096** (`experts_per_token = 8`,
`LagunaRuntimeModel.swift:8306`). Artifact:
`research/artifacts/tanjiro-r125d/air-census.json`.

| quantity | BN=32 | BN=64 | BN=128 |
| --- | --- | --- | --- |
| `ir_lines` | 2 351 | 3 635 | 5 808 |
| `mma_run` (non-empty MMA) | 3 | 3 | **3** |
| `mma_getptr` | 12 | 12 | 12 |
| `fmul` | 12 | 12 | 12 |
| `TN_frags` | 2 | 4 | **8** |
| `SM` (row frags) | 16 | 16 | 16 |
| `alloca` (reg-pressure hint) | 45 | 74 | **120** |
| `store_slice_spec` | 14 | 28 | 56 |
| TG memory (AIR) | 4 616 B | 9 224 B | **18 440 B** |
| TG memory (Metal pipeline probe) | 4 624 B | 9 232 B | **18 448 B** |
| threadgroups / layer | 16 384 | 8 192 | **4 096** |
| grid dims | (64, 256, 1) | (32, 256, 1) | (16, 256, 1) |
| staged **w** bytes / layer | 150.99 MB | 150.99 MB | 150.99 MB |
| **x** re-read / layer | 268.44 MB | 134.22 MB | **67.11 MB** |
| **x** re-read, all 38 MoE layers | 10.20 GB | 5.10 GB | **2.55 GB** |
| staged bytes per SK step | 576 B | 1 152 B | 2 304 B |

### The arithmetic that picks 128

*Weight traffic is BN-invariant.* Each layer touches all 256 routed experts plus
the shared expert; each expert's down weight is
`2048 × 512` 4-bit values + group-16 scales ≈ 0.590 MB, and with ≈16 rows per
expert (`≤ bm = 64`) there is exactly one row-tile per expert, so every expert's
columns are read exactly once whatever BN is:
`256 × 0.590 MB = 150.99 MB` per layer, `× 38 = 5.74 GB` per forward. **BN cannot
reduce the weight bytes; it can only change how many are in flight at once.**

*Activation traffic is BN-linear.* Each row's `x` is re-read once per N-tile,
i.e. `N/BN` times: `4.194 MB × 2048/BN`. Going 64 → 128 removes
`67.11 MB × 38 = 2.55 GB` of re-reads per forward — but `x` per layer is only
4.194 MB unique, so most of that traffic is SLC-resident and should **not** be
scored as saved DRAM bytes. It is counted here only as an upper bound
(§2 "pessimistic-cache view").

*Occupancy is sub-linear in TG memory.* `research/maple-tanjiro-r125d-occupancy-census.swift`
(8 reps, dynamic-TG-memory probe, 128-thread groups, 20-core M4 Pro) measures
peak co-resident threadgroups:

| static TG bytes | resident TGs (mean ± sd) | per core | staged **w** bytes in flight / core |
| --- | --- | --- | --- |
| 4 624 | 173.2 ± 29.2 | 8.66 | 9 976 B |
| 9 232 | 160.6 ± 21.5 | 8.03 | 18 505 B |
| 18 448 | **115.4 ± 1.77** | 5.77 | **26 588 B** |

(in-flight staged bytes per core = resident TGs per core × `staged_bytes_per_sk_step`
× 2, since the stage ring keeps two SK steps in flight.)

Doubling the footprint 9 232 → 18 448 B costs only **28 %** of co-residency, not
50 %, so bytes of weight in flight per core rise **+44 %**. That is the whole
thesis: on a shape whose cost is `w` streaming at 398 GB/s against a 546 GB/s
DRAM ceiling (§2), more bytes in flight is the only lever that converts to time,
and BN=128 is the largest rung that still fits.

BN=256 is not a rung: TG memory would be 36 880 B > the 32 768 B limit measured
by the pipeline probe (`research/artifacts/tanjiro-r125d/pipeline-probe.txt`).

---

## §2 Code change and tile derivation

Single hunk, `Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/quantized.cpp`
(`darkbloom_expert_down_bn`, lines 1234-1250). The arm that was built and
censused set the default `64 → 128`; **what is committed keeps the default at
64** and only widens the env ladder to `(n == 32 || n == 64 || n == 128) ? n : 64`
so the 128 rung stays reachable for reproduction (§8 item 0). The derivation
below describes the 128 arm as measured statically; §2b is why it is not the
default. No other line in the tree changes.

**What the host-side `bn` argument moves.** `bn` feeds exactly three host-side
things, and only the first is BN-shaped:

1. `grid_dims((N + bn - 1)/bn, egroups, 1)` (dispatch, ~line 1628-1650) —
   4 096 TGs/layer instead of 8 192.
2. `darkbloom_stage_wide_load_ok(..., bn)` → `col_step = bn * (K/2) = bn * 256`,
   a multiple of 16 for 32/64/128 alike, so `expert_wideld` is unchanged and the
   kernel name keeps `_ws_1_wl_1` for all three rungs.
3. `align_N = (N % bn) == 0` — true for all three rungs, so `expert_aligned`
   (and with it the whole `fp_gather_qmm_rhs_expert_nax` fast path) still holds.
   A non-divisor rung such as 192 would silently drop the branch; 128 does not.

I first wrote this list as a "single-lever proof". **That claim was wrong**, and
§2b below is the correction: item 2 only shows that the host still *requests*
the widened staging path (`_ws_1_wl_1`); it does not show that the device
template still *emits* it. It does not, and that is the finding of this
experiment.

The one remaining bn-sensitive dispatch term is the x-major split:
`grid.x = xmajor_ct > 1 ? (N/bn)/xmajor_ct : ceil(N/bn)`. Here
`darkbloom_gather_xmajor_ct()` returns a hard-coded `0` (line 1308-1310), so the
`ceil` branch is taken and 2048/128 = 16 divides exactly — no tail tile and no
divisibility hazard. If a future experiment turns x-major on, its `ct` must
divide 16 rather than 32.

`bn` also enters the kernel *name* via `get_template_definition(...)`, so BN=128
is a new instantiation compiled from the same embedded source at runtime; the AIR
census compiled that exact instantiation cleanly (§1), so this is not an
AOT-metallib dependency.

`group_dims(32, wn, wm)` is BN-independent; the default geometry variant is 5
(`bm=64, wm=4, wn=1, bk=64`) and is untouched.

**Bit-exactness.** BN partitions output columns across threadgroups. The K loop
(`SK=32` staged steps), the accumulate order inside each fragment, and the
epilogue `Dtile.store` / `store_slice` are all BN-agnostic. The AIR census is
the mechanical check: `mma_run = 3` and `fmul = 12` are **identical** at BN
32/64/128, i.e. per-fragment arithmetic is the same program; only the number of
`store_slice` specialisations and the TG tile extent scale. There is no
cross-column reduction anywhere in the down epilogue, so no reassociation is
possible.

**Time budget it acts on.** PR170's ledger on control `3e165fa` (S = 97.895 ms)
attributes **W = 43.26 ± 0.40 ms** (~44 % of the whole scored window
S ≈ 97.9 ms, not 44 % of the prefill axis alone) to the routed gather-GEMM
family. The down shape is one of three shapes and exactly one third of the
family's weight bytes (17.2 GB over 38 layers), so I *assume* its time share is
byte-proportional at **≈ 14.42 ms** — that split is arithmetic on the weight
bytes, not a measured per-shape timing, and it is the weakest number in the
chain. It implies an effective 5.74 GB / 14.42 ms = **398 GB/s**. At the
M5 DRAM ceiling of 546.2 GB/s the same bytes take **10.51 ms**, so the
addressable pool is **3.91 ms** — that is the hard cap on any BN win.

**Harvest model (Little's law on the +44 % bytes in flight).**

| efficiency η | ΔS |
| --- | --- |
| 0.25 | −1.44 ms |
| 0.50 | −2.61 ms |
| 0.75 | −3.57 ms |
| 1.00 | −3.91 ms (capped by the DRAM floor) |

The η = 1.00 rung is **unreachable in principle**, not merely optimistic: the
10.51 ms floor it assumes counts only the 5.74 GB of down weights. The same
kernel also stores ≈ 0.64 GB of `y` and reads ≈ 0.16 GB of unique `x` per
window, so a true DRAM floor is ≈ 11.98 ms and the honest cap on the pool is
≈ 2.4 ms rather than 3.91 ms. I left the table as originally computed and note
the correction here rather than silently improving my own prediction.

The pessimistic-cache view is an independent sanity check and lands in the same
band: if every `x` re-read were a DRAM miss, total down traffic falls
10.84 → 8.29 GB (−23.5 %), i.e. −3.39 ms on a 14.42 ms budget. I report the
**conservative η = 0.25 point, −1.44 ms**, as central and do **not** add the `x`
term on top of it (same memory system — adding both double counts).

**Downside branch.** `TN_frags` 4 → 8 doubles the register-resident `Dtile`
(~64 floats/lane, plus `Btile`/`Atile`: ≈140+ registers/lane). This host offers
no spill detector — `maxTotalThreadsPerThreadgroup = 1024` for all three
pipelines, which R107-C §6.3 already showed is uninformative — and `alloca`
45 → 74 → 120 is only a hint. If the M5 spills, the extra bytes in flight never
materialise and only the TG-count and `x` terms survive (≈ −0.3 ms); if spilling
costs traffic, up to **+2.0 ms** is possible. Hence the reported interval
**ΔS ∈ [−3.91, +2.00] ms**.

---

## §2b The blocker: BN=128 statically disables the widened weight staging

This section is the reason the experiment lands negative, and it invalidates the
prediction above rather than merely widening its error bar.

`QuantizedBlockLoader` in
`Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/kernels/fp_quantized_nax.h`
does not take a vector width as a parameter. It *derives* one from the tile
shape:

```
:215-216   static constexpr short n_reads = (BCOLS_PACKED * BROWS) / tgp_size;   // = BN/4 here
:428       static constexpr int kSrcBytes = n_reads * bytes_per_pack;
:438       static constexpr bool kWideLoadShapeOk  = ... && kSrcBytes == 16;
:444       static constexpr bool kWideLoad8ShapeOk = ... && kSrcBytes == 8;
:502       if constexpr (kWideLoadShapeOk)  { /* 16-byte vector load */ }
:512       else if constexpr (kWideLoad8ShapeOk) { /* 8-byte load */ }
:522-527   else { for (b) sb[b] = src[b * bytes_per_pack]; }   // scalar byte loop
```

So the emitted load width is a *function of BN*, and only two widths have a
vectorised body:

| BN | `n_reads` | `kSrcBytes` | vectorised body emitted? |
| --- | --- | --- | --- |
| 32 | 8 | 8 | yes (8-byte) |
| 64 | 16 | 16 | yes (16-byte) |
| **128** | **32** | **32** | **no — scalar byte loop** |

The AIR/IR for the three instantiations confirms this mechanically
(`research/artifacts/tanjiro-r125d/wide-load-census.txt`; occurrence counts):

| rung | `Wide*` symbols | dev→priv 16 B `memcpy` | priv→tg 16 B `memcpy` | 8 B (`i64`) device load | 32 B `sb[]` `alloca` |
| --- | --- | --- | --- | --- | --- |
| 32 | 21 | 0 | 1 | 1 | no |
| 64 | 27 | 1 | 1 | 0 | no |
| **128** | **0** | **0** | **0** | 0 | **yes** |

Key lines: `down-bn64.ir:63` types `WideSrc` as `[16 x i8]`; `:715` is a 16-byte
`llvm.memcpy.p0i8.p1i8` straight out of `addrspace(1)`; `:935` is the matching
16-byte `memcpy.p3i8.p0i8` into threadgroup memory. At BN=128,
`down-bn128.ir:693` is `llvm.lifetime.start(i64 32)` — the 32-byte `sb[]`
staging buffer — followed at `:695/:697` by per-byte `load i8 addrspace(1)` /
`store i8`, and `:880-894` by eight scalar `store bfloat ... addrspace(3)` with
alignments 16,2,4,2,8,2,4,2. All three `.metal` instantiations request
`_ws_1_wl_1`, i.e. the host asked for the wide path in every case.

Two honest caveats on this evidence:

- The **store** side is not statically disabled. `kWidenShapeOk` still holds at
  BN=128, and `dst_byte_off() = 144 * bi` is 16-byte aligned because `bj == 0`
  at that shape. The loss of the widened threadgroup stores is therefore an
  observation about what this compiler actually emitted, not a proof from the
  `if constexpr` conditions.
- I did not measure the cost of the scalar loop on an M5. What is proven is
  that BN=128 changes a second, independent mechanism (staging load width), so
  the +0.53 % prediction from §2 is no longer a single-lever prediction and
  cannot be shipped as one.

**Consequence for the ladder.** "BN is a free knob" is retired. It also
retroactively explains the BN=32 rung: 32 is not simply "smaller tiles", it is
also an 8-byte staging load, so any BN=32 counter-arm is confounded the same way.

---

## §3 Kernel-selection evidence (why this is not locally measurable)

```
quantized.cpp:1671   if (metal::is_nax_available() && transpose && ...)
                       return gather_qmm_rhs_nax(...);          // sole caller
quantized.cpp:1398       bn = darkbloom_expert_down_bn();       // inside that callee
device.cpp:913-929   can_use_nax &= gen >= (arch == 'p' ? 18 : 17);
```

`research/artifacts/tanjiro-r125d/pipeline-probe.txt` records this host as
**Apple M4 Pro**, which reports Apple GPU generation **16**. Therefore
`is_nax_available()` is false, `gather_qmm_rhs_nax` is never entered, and
`darkbloom_expert_down_bn()` is never called on this box. Consistent with the
programme's earlier finding that 94.2 % of M4 prefill GPU time sits in kernels
the M5 never runs.

What *is* verifiable locally, and was verified:

* all three instantiations compile clean via the JIT-AIR harness
  (`air_bytes` 26 096 / 35 968 / 52 064;
  `research/artifacts/tanjiro-r125d/down-bn{32,64,128}.compile.log`);
* the surface digest of the generated kernel source is stable
  (`c4608572a5…`), and the `mlx-generated/*.cpp` twin differs from the header
  only by inlined `fp4.h`/`fp8.h` bodies and `PRAGMA-VARIANT` comment lines
  (`research/artifacts/tanjiro-r125d/twin-diff.txt`, 175 lines) — the header was
  not edited, so **no twin edit is required**;
* real Metal pipelines build for all three rungs with static TG memory
  4 624 / 9 232 / 18 448 B against `maxThreadgroupMemoryLength = 32 768`.

---

## §4 Correctness certificate

| gate | command | result |
| --- | --- | --- |
| release build | `swift build -c release --force-resolved-versions` (then `git checkout -- Package.resolved`) | **exit 0**, 57.9 s (job `9728a7d2`) |
| assignment scope | `senpai/validate-assignment-scope.sh $BASE_SHA Vendor/.../quantized.cpp` | **OK**, 1 submitted path |
| editable budget | `senpai/check-editable-budget.sh 1bc1c895…` | **OK** `current=2699804/3000000 headroom=300196 growth=-284045/262144 files=143` |
| upstream equivalence | `EQUIVALENCE_EXACT_STEPS=8 research/run_upstream_equivalence.sh` | see below (job `9c25baf4`) |
| local checked-token gate (both arms, 2 reps each) | `./benchmark.sh --local-iterate` | **`passed_correctness = true`, `checked_steps = 130`, `max_abs_diff = 0`**, and `golden_hash = b9509697c08a2cf3c2…` **identical** for candidate and baseline arms |
| standalone 64-step drift fixture | `correctness_golden.json` | not present under that name in this checkout (same as R121-A); the equivalent local coverage is the 130-checked-token row above |

Equivalence detail (candidate tree, `quantized.cpp` recompiled in the debug
bundle — see `[5/11] Compiling quantized.cpp` in the job log):

```
promptTokenCount 512, decodeTokenCount 8
prefill    runtimeToken 5991 == upstreamToken 5991   maxAbsLogitError 0.125   meanAbs 0.011933609
decode-0..7 all runtimeToken == upstreamToken        maxAbsLogitError 0
EQUIVALENCE_EXACT_STEPS=8
EQUIVALENCE_EXIT=1
```

**9 / 9 greedy tokens match** (prefill argmax plus all eight decode steps), and
all eight decode steps are bit-exact. The non-zero exit is the single prefill
`maximumAbsoluteLogitError = 0.125`, which is the documented pre-existing
gen-16 property of this **unchanged base** on this host, not a candidate
regression: the changed code is unreachable here (§3), so the candidate cannot
have produced it. `MLXFAST_LOCAL_ALLOW_GOLDEN_DRIFT` was **never** set.

**Scope of the certificate.** Because the edited path is unreachable on gen-16
(§3), the equivalence run proves that the candidate tree still builds and still
matches the vendored oracle on the paths this host *does* execute; it cannot
exercise BN=128 itself. The exactness argument for BN=128 is the structural one
in §2 plus the AIR-level evidence that the arithmetic program is identical
across BN. The official M5 run is the only place the claim can be observed, and
it is gated by the hidden 512-token teacher-forced cases and token validation.

---

## §5 Decode neutrality

Decode is 75 % of the score, so neutrality must be argued at the code level, not
just timed:

1. Decode is `M = 1`. The override gate requires `M >= 64`
   (`quantized.cpp:1396`), so a decode step can never take the branch even on
   the M5. `bn` for decode stays whatever the generic NAX path chooses.
2. The gate additionally requires `bm == 64 && wm == 4 && (wn == 2 || wn == 1)`,
   i.e. the prefill geometry variant. Decode's single row never selects it.
3. `darkbloom_expert_down_bn()` has no other caller
   (`grep -n darkbloom_expert_down_bn` → definition at 1240, one use at 1398).
4. `bn` does not feed any host-side allocation, cache-shape, or metadata
   decision, so no decode-visible state changes.

A paired local `--local-iterate` A/B was then run anyway, as a **regression
check, not as the neutrality evidence**. The base already exposed
`DARKBLOOM_EXPERT_DOWN_BN` (rungs 32/64; this change adds 128 to the ladder), so
both arms run the *same* candidate binary with the env var pinned,
alternating `128, 64, 128, 64` behind the same thermal gate
(`research/maple-tanjiro-r125d-paired-ab.sh`, 612 s, 2 reps per arm):

| metric | `BN=128` (env-pinned arm) | `BN=64` (default, = base) | cand/base |
| --- | --- | --- | --- |
| decode s/token (mean of 2) | 0.012 843 459 | 0.012 869 360 | **0.997 99** |
| prefill s/token (mean of 2) | 0.001 123 482 | 0.001 116 801 | 1.005 98 |
| decode_speedup | 1.0789 | 1.0767 | — |
| prefill_speedup | 0.3271 | 0.3291 | — |
| `passed_correctness` / `checked_steps` | true / 130 | true / 130 | — |
| `max_abs_diff` | 0 | 0 | — |
| `golden_hash` | `b9509697c08a2cf3c2…` | `b9509697c08a2cf3c2…` | identical |

Read this correctly: on a gen-16 host the two arms execute *identical machine
code* on the scored path (§3), so the ±0.2 % decode and ±0.6 % prefill spreads
are the host's paired-noise floor, and they bracket 1.0 — i.e. the run shows no
host-side, allocation, or dispatch-shape side effect from raising the rung, and
no correctness change (130/130 checked steps, byte-identical golden hash in both
arms). It is **not** evidence about the kernel's speed, which is why (1)-(4)
above carry the neutrality claim. The local prefill_speedup floor failure
(≈0.33) reproduces in **both** arms and is structural to this box, independent of
this change.

Decode neutrality on the official host is asserted from (1)-(4) and is
falsifiable there: any decode_speedup below 1.00 − noise on the M5 receipt
contradicts the argument and should trigger the §7 revert.

---

## §6 Transfer reasoning (one constant, applied once)

The programme's single calibrated constant: **1.022 ms off S ⇒ +0.378 % score**,
i.e. **0.3699 % per ms** at the operating point **S = 97.863 ms**. That constant
already contains the score's decode/prefill weighting and the harness's
window composition, so a millisecond estimate is multiplied by it exactly once —
no second deflation for "prefill is only 25 % of the score", which is the double
count this campaign has made before.

> **This prediction is void.** It is kept verbatim because it was written before
> §2b was known and because the arithmetic (not the premise) is reusable. §2b
> shows BN=128 also replaces a 16-byte vector staging load with a scalar byte
> loop, so the bytes-in-flight model no longer describes the candidate. Nothing
> below should be quoted as a live estimate for BN=128, and no submission was
> made on it.

* central **−1.44 ms × 0.3699 = +0.53 %**;
* interval **−3.91 ms → +1.45 %**, **+2.00 ms → −0.74 %**;
* receipt noise **σ(officialScore) = 0.489 %**, so the central prediction is
  **1.09 σ** — a favourable but genuinely uncertain single draw;
* the crown `c5b0a13` = 2.616 503 54 sits **+0.378 %** above the best receipt
  `e27f1ce` = 2.606 649 70; central A1 predicts **2.620 46**, i.e. it clears the
  crown by ≈0.15 % if the central case holds.

The transfer constant itself is unaffected by §2b and remains the right way to
price any *future* millisecond estimate on this shape.

**Where the value actually is.** Independent of BN, the census already names the
bigger prize:
`SM = 16` row fragments against ≈16 rows per expert means the row dimension is
padded, ≈31.3 % of the MMA work on this shape is on padding, worth ≈11 ms —
roughly 4.5× the corrected addressable pool of this whole BN lever. That is a
BM/WM experiment (R107-C §8), not a BN one.

---

## §7 Follow-up gating (replaces the pre-draw abort criteria)

The original §7 listed abort criteria for an official BN=128 draw. That draw was
never taken, because §2b removed its premise before submission. What replaces it
is the order in which a follow-up should be attempted — **one lever at a time**:

1. **Fix the loader first, with BN unchanged at 64.** Add a chunked branch to
   `QuantizedBlockLoader::load_unsafe` for `kSrcBytes == 32`: two 16-byte
   `WideSrc` copies instead of one, keeping the existing 16-byte device→private
   and private→threadgroup `memcpy` pair. This is a device-side change with no
   host-side dispatch effect, so it is verifiable by the same AIR/IR census:
   the acceptance test is `Wide*` symbol count > 0 and two 16-byte
   `memcpy.p0i8.p1i8` in `down-bn128.ir`, with `mma_run`/`fmul` unchanged.
2. **Only then re-run the BN rung.** With the loader emitting the same load
   width at 64 and 128, BN=128 becomes the single-lever experiment this
   assignment intended, and the §2 harvest model applies again (with the
   corrected ≈2.4 ms pool, not 3.91 ms).
3. **Do not raise a BN=32 counter-arm as a sign test.** §2b shows 32 also
   changes the staging width (8-byte body), so it cannot isolate tile width.
   `bn32.patch` remains in the artifacts only as a reproduction aid.
4. **Preferred use of the next allocation is not BN at all.** The `SM=16`
   row-padding lever (§6, ≈11 ms) is a BM/WM experiment worth roughly 4.5×
   the corrected addressable pool of this whole BN lever.
5. **Any interpretation from a non-M5 host stays out of bounds for this lever**:
   gen-16 cannot execute `_nax` at all (§3).

---

## §8 Deviations from the assignment

0. **The assigned change is not shipped.** The assignment asked for BN=128 as the
   default for the routed/shared down gather GEMM. `darkbloom_expert_down_bn()`
   is committed with the default back at **64**; only the env ladder is widened
   to accept 128 for reproduction, and an 8-line comment records the
   `fp_quantized_nax.h:438-444` constraint. With the env var unset the submitted
   surface is **behaviourally identical to base `a9de9e8`**. The reason is §2b:
   BN=128 silently changes a second mechanism, and shipping it would be exactly
   the "combining several unmeasured mechanisms" failure AGENTS.md warns about.
1. **The local timing arm is a regression check, not neutrality evidence.** The
   assignment anticipated a paired `--local-iterate` A/B for decode neutrality.
   I ran it (§5: 2 reps per arm, alternating, env-pinned rungs on one binary) and
   it is clean — decode ratio 0.997 99, correctness 130/130, identical golden
   hash — but on this gen-16 host both arms execute identical machine code on the
   scored path, so the neutrality claim rests on the structural argument (§5
   (1)-(4)). Recording the local numbers as a *speed* result would be the
   "evidence-shaped noise" failure this campaign has hit before.
2. **A2 (`BN=32`) shipped as a patch artifact, not a second commit** — and it is
   now known to be *not* a valid counter-arm at all: §2b shows BN=32 changes the
   staging load width too (8-byte body), so it could not have isolated tile
   width. The patch stays as a reproduction aid only.
3. **64-step drift tripwire not run**: the fixture is absent from this checkout,
   as previously recorded for R121-A. The gate remains available on the official
   stack.
4. **Occupancy numbers differ from R107-C's run** (115.4 here vs 127.8 there at
   18 448 B; 173.2 vs 160.2 at 4 624 B). The instrument is noisy at small
   footprints and uses a trivial kernel, so it does not model register pressure.
   Only the **monotone, sub-linear** ordering is claimed, and that reproduces.
5. **Two soft spots in the §2 arithmetic, flagged rather than buried.** The
   14.42 ms down-shape budget is a byte-proportional *assumption* off PR170's
   43.26 ms family total, not a measured per-shape time; and the η = 1.0 row of
   the harvest table is unreachable because its DRAM floor omits the ≈0.64 GB of
   `y` stores and ≈0.16 GB of unique `x` reads, which lifts the floor to
   ≈11.98 ms and shrinks the honest pool to ≈2.4 ms.

### Reproduction

```bash
# 1. instantiate and census the three BN rungs (no GPU, no model)
OUT_DIR=research/artifacts/tanjiro-r125d \
  bash research/maple-alphonse-r107c-jit-air.sh 32 64 128
for b in 32 64 128; do
  xcrun air-objdump --disassemble \
    research/artifacts/tanjiro-r125d/down-bn$b.air \
    > research/artifacts/tanjiro-r125d/down-bn$b.ir
done
python3 research/maple-tanjiro-r125d-air-census.py 32 64 128

# 1b. the §2b blocker: wide-load presence per rung.
#     (grep -c counts matching *lines*; the §2b table quotes occurrence counts,
#      hence Wide_lines 12/16/0 here vs Wide 21/27/0 there. Same conclusion.)
D=research/artifacts/tanjiro-r125d
for b in 32 64 128; do
  printf 'bn%s Wide_lines=%s mc16_dev=%s mc16_tg=%s sb32_alloca=%s\n' "$b" \
    "$(grep -c Wide $D/down-bn$b.ir)" \
    "$(grep -c 'memcpy.p0i8.p1i8.*i64 16, i1' $D/down-bn$b.ir)" \
    "$(grep -c 'memcpy.p3i8.p0i8.*i64 16, i1' $D/down-bn$b.ir)" \
    "$(grep -c 'lifetime.start.*i64 32,' $D/down-bn$b.ir)"
done   # -> bn32 0/1, bn64 1/1, bn128 0/0 + sb32_alloca=1; see wide-load-census.txt

# 2. real Metal pipeline TG-memory probe
swiftc -O research/maple-alphonse-r107c-pipeline-probe.swift -o /tmp/pipeprobe && /tmp/pipeprobe

# 3. occupancy census (8 reps)
swiftc -O research/maple-tanjiro-r125d-occupancy-census.swift -o /tmp/occ && \
  /tmp/occ 4624 9232 18448

# 4. gates
swift build -c release --force-resolved-versions && git checkout -- Package.resolved
EQUIVALENCE_EXACT_STEPS=8 research/run_upstream_equivalence.sh

# 5. paired local A/B regression check (~10 min; one model process at a time)
REPS=2 bash research/maple-tanjiro-r125d-paired-ab.sh

# 6. publish census + prediction + A/B to W&B
python3 research/maple-tanjiro-r125d-wandb.py

# 7. raise the A2 counter-arm if §7 criterion 3 fires
git apply research/artifacts/tanjiro-r125d/bn32.patch
```
