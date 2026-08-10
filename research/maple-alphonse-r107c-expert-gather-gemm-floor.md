# R107-C — Expert gather-GEMM floor: how much prefill is left in `routed_gather_gemm`?

- Student: `maple-alphonse`
- Assignment: `maple-r107-c-expert-gather-gemm-floor`, revision `r107-c-rev1`
- PR: #636, branch `maple-alphonse/r107-expert-gather-gemm-floor`
- `BASE_SHA`: `e1d206da6bedd2a3ce3957ae05437a78317e4620`
- Host: Apple **M4 Pro**, `applegpu_g16s`, Apple GPU **generation 16**, 20 GPU
  cores, 14 CPUs, 48 GiB unified (low-memory startup profile), macOS 26.5.2
  (25F84), `Apple metal version 32023.883`.
- W&B: [`yljdcwmc`](https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/yljdcwmc)
  (artifact `maple-alphonse-r107c-ledger`)
- Verdict: **`N-REACH` + `N-XMAJOR-CLOSED` + `N-BUILD` refuted + a live but
  sub-threshold C2a candidate handed off unmeasured.** No millisecond is claimed
  on this host. See [§10 Verdict](#10-verdict).

---

## 0. One-paragraph summary

Three of the four axes this assignment listed as "never measured" were already
closed in the archive (rule 83), so Stage A collapsed to a single live arm.
That arm — narrowing the routed/shared **down**-projection N-tile from
`bn = 64` to `bn = 32` in `fp_gather_qmm_rhs_expert_nax` — is implemented,
compiles clean under the exact scored-worker flags, is argued bit-exact, and is
a **no-op by default**. It cannot be timed here: `gather_qmm_rhs` gates the
whole NAX family on `metal::is_nax_available()`, which requires Apple GPU
generation ≥ 17, and this host reports **generation 16**. Per rule 39 that
makes every local NAX runtime number unmeasured, so this report substitutes the
rule-82 static ledger the assignment asks for: an AIR-level census, two
*measured* `staticThreadgroupMemoryLength` values, and a *measured*
resident-threadgroup occupancy census. The ledger says `bn = 32` halves per-
threadgroup threadgroup memory (9232 B → 4624 B) and buys **1.25× ± 0.04** more
co-resident threadgroups, holds total weight traffic and MMA work exactly
invariant, and doubles A-operand *request* multiplicity (32× → 64× over a
4 MiB/layer footprint that should stay SLC-resident). The family has only
≈7.6 ms of above-roofline residual, of which the down share is **2.554 ms**;
that is the absolute ceiling for any down-only change (0.966 % of score, which
would clear the 1.35 ms 3σ bar). Applying the measured 1.25× resident-
concurrency gain as a stall-scaling factor to that share puts the mechanism
estimate at **0.517 ms ⇒ 0.195 % of score**, which fails **both** the
assignment's 0.4 %-of-score relevance gate and its 1.35 ms 3σ bar. The honest
answer to the assignment's question is therefore
**`N-FLOOR` with one live but sub-threshold unmeasured candidate** — and a larger
prize found on the way: at mean routing only **1 of 4 simdgroups per
threadgroup does any MMA**, a `BM/WM` waste that `bn` does not touch.

---

## 1. Stage 0 — rule-83 archive search (all four axes)

The assignment named four axes as candidates. Rule 83 requires searching the
archive before spending a stage. Three were already decided.

### Q1 — `darkbloom_stage_bm128_variant()` default 5 (variant 4 vs 5): **CLOSED**

Default 5 was chosen on **official-M5 absolutes**, not on off-M5 deltas.
Candidate prefill walked 204.90 → 201.64 → 201.42 → **198.00 µs** across the
receipt corpus (`research/artifacts/advisor-r103/receipt-corpus-frozen.json`
lines 6142 and 6772; summarised at `research/PREFILL_NAX_ANALYSIS.md:170`). An
earlier off-M5 ABBA that appeared to favour variant 4
(`research/nezuko-r99b/rung1-comment-strip.patch:7444-7468`) is explicitly
superseded at `:7599-7607` and is session-baseline fog. Variant 4 also sets
`WN = 2`, which *disables* `kSwigluRegLocal`
(`kernels/fp_quantized_nax.h:1781-1782`), so it is not a free swap. The family
is recorded "CLOSED at the floor" in
`research/RESEARCH_STATE_ARCHIVE_through-round-21.md:6362`, with the sweep at
`research/RESEARCH_ARCHIVE_through-round-91.md:6408-6418` and the roofline
framing at `research/maple-fern-prefill-roofline.md:293`.
**⇒ Stage A arm 2 dropped.**

### Q2 — x-major (`darkbloom_gather_xmajor_ct()`): **CLOSED-NEGATIVE**

The compile-time knob was hardcoded to `return 0;` for byte budget, not because
it was promising (`research/nezuko-r99b/rung1-comment-strip.patch:7558-7561`;
`research/nezuko-harvest-report.md:67,75-77`, commit `2cad177`). More
decisively, the external solver's public note reports the old X-major fold as
officially **prefill-negative** on register pressure / occupancy grounds
(`research/RESEARCH_ARCHIVE_through-round-91.md:1220-1226`). Adjacent
reorderings are closed too: expert-queue LPT
(`research/pr142-lpt-expert-queue-refutation.md:186-190`) and tile swizzle
(`research/RESEARCH_ARCHIVE_through-round-91.md:5194-5212`).
**⇒ Stage B candidate C2b is dead on arrival: preregistered outcome
`N-XMAJOR-CLOSED`.**

### Q3 — `DARKBLOOM_EXPERT_GATHER_GROUPS` ∈ {64, 128, 256}: **CLOSED-POSITIVE**

256 is optimal and already shipped
(`research/nezuko-r99b/rung1-comment-strip.patch:7381-7394`;
`research/PREFILL_NAX_ANALYSIS.md:56-60`), with a supporting queue simulation at
`research/pr142-lpt-expert-queue-refutation.md:262-300`.
**⇒ Stage A arm 3 dropped.**

### Q4 — `bn` 64 → 32: **genuinely never measured**

Never swept for the NAX expert kernel
(`research/RESEARCH_ARCHIVE_through-round-91.md:6560-6565,:6589`;
`research/RESEARCH_IDEAS_2026-08-06_18:30.md:73-84,332`), with optimistic
1.5–4 %-of-score predictions at `research/PREFILL_NAX_ANALYSIS.md:196-212` and
census context at
`research/maple-tanjiro-pr91-prefill-budget-census.md:794,833,951` and
`research/maple-tanjiro-r98-prefill-loader-pipeline.md:199-202`.

> **False-positive warning for future readers.** Grepping for
> `bm_16_bn_32_...` finds hits in `research/pr270-logs/*.worker.err` and
> `research/maple-fern-prefill-roofline.md:28`. Those are the **non-NAX** M4
> kernel `nvfp4_gather_qmm_rhs_nt`, a different template with a different tile
> policy. They are not evidence that `bn = 32` was tried on the NAX expert
> kernel.

**⇒ Q4 is the only live arm, and §3 shows it is admissible on the down
projection only.**

---

## 2. Reachability: `N-REACH` on this host, and the nuance that matters

`gather_qmm_rhs` (`quantized.cpp:1628` pre-edit) routes to the NAX family only
under `metal::is_nax_available()`. That predicate
(`Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/device.cpp:913-931`)
requires macOS ≥ 26.2 **and** `gen >= (arch.back() == 'p' ? 18 : 17)`. This host
is macOS 26.5.2 (passes) at generation **16** (fails).

**Consequence (rule 39).** `fp_gather_qmm_rhs_expert_nax` is never dispatched
here, so no local runtime measurement of any NAX arm exists or can exist. The
`routed_gather_gemm` family that consumes 48.3 % of *M4* prefill is the non-NAX
twin `nvfp4_gather_qmm_rhs_nt`; optimising it is a different experiment.
This is the preregistered outcome **`N-REACH`**.

**The nuance that is easy to get wrong.** *Compilability and runtime selection
are separate facts.* The NAX expert kernel compiles to a real
`MTLComputePipelineState` on this generation-16 device — I built both `bn`
variants through `device.makeLibrary(source:options:)` and read their pipeline
properties back (§6.2). So this host **can** certify "does it build, what
geometry does it request, how many copies fit per core" while being unable to
certify "is it faster". The static ledger below rests only on the first class
of fact.

**Offline native translation is unavailable, so there are no register counts.**
`applegpu-nt` refuses every arch I have (`g16s`, `g17s`, `g17p`, `g17g`,
`g18p`) with `error: incompatible module ... AIR version (2.8) is bigger than
the one of the target (2.5)`: the bundled translator targets AIR 2.5 while
`-std=metal4.0` emits AIR 2.8. `applegpu-nt -impls <arch>` prints nothing.
For the record, `-archs` lists `applegpu_g16s/g17s/g17p/g17g/g18p`, and
availability for macOS 26.0 is `g17p: Yes`, `g17s: Yes`, `g18p: No`,
`g16p: No`. **⇒ no offline register-pressure or occupancy-limit numbers.**

**Arch-vs-gate tension, stated explicitly so nobody re-derives it wrong.**
`research/tanjiro-r102b-submission-note.md:124` calls the official M5
`applegpu_g17p`, but `is_nax_available()` demands `gen >= 18` when the arch
string ends in `p`. Both cannot be literally true of the ranked host if the
ranked host runs `_nax`. Either the recorded arch string is from a different
probe than the gate reads, or the M5 Max reports an `s`-suffixed arch at
gen ≥ 17. `research/frieren-r98-inflight-audit.md:78` documents a prior
`xcrun metallib` + `applegpu-nt -arch ...` workflow that presumably resolved
this on a host where the translator matched the AIR version. **This report does
not resolve it** and does not need to: every claim here is arch-independent
compile-time geometry plus a gen-16 occupancy measurement, and the ranked
verdict must come from an M5.

---

## 3. The candidate (C2a), and why `bn` is free on down but locked on gate/up

`fp_quantized_nax.h` has a fused SwiGLU epilogue that fires only when
`kernel_N == 1024 && kernel_K == 2048` — the **gate/up** shape. It pairs column
`col` with `col + BN/2` and writes `N/2` columns. **`BN = 64` is therefore a
correctness lock for gate/up**: change it and the gate/up pairing changes shape.

The **down** shape (`K == 512`, `N == 2048`) takes the plain path:
`Dtile.store(yn, kernel_N)` / `store_slice(..., short2(SN, sgp_sm))` with
`y_col = tid.x * BN`. That is **BN-agnostic** — each threadgroup writes its own
`BN`-wide column band, and narrowing the band just makes more bands.

So the candidate is scoped **down-only**, and the patch encodes exactly that.

### 3.1 Patch (submitted surface, 25 added lines, 1740-byte diff)

Single file: `Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/quantized.cpp`
(editable entry 53 of 97). No `mlx-generated` twin edit is required — see §5.3.

1. New `int darkbloom_expert_down_bn()` beside the other `darkbloom_*` knobs:
   reads `DARKBLOOM_EXPERT_DOWN_BN`, **defaults to 64**, and accepts only 32
   or 64 (anything else falls back to 64).
2. An override block placed *after* the `darkbloom_stage_bm128_variant()`
   switch and *before* `align_M`, gated by the same predicate as
   `expert_aligned` restricted to the down shape:

   ```
   darkbloom_expert_aligned_gather() && mode != "affine" && transpose &&
   group_size == 16 && bits == 4 && K == 512 && N == 2048 && M >= 64 &&
   bm == 64 && wm == 4 && (wn == 2 || wn == 1)
   ```

   ⇒ `bn = darkbloom_expert_down_bn();`

**Why that insertion point.** Everything downstream of it consumes `bn`
automatically and correctly:

| downstream consumer | line (post-edit) | effect at `bn = 32` |
| --- | --- | --- |
| `align_N = (N % bn) == 0` | 1398 | 2048 % 32 == 0 ✓ |
| `expert_wideld = darkbloom_stage_wide_load_ok(w, transpose, bits, N, K, bn)` | 1402-1405 | `col_step = bn*(K/2) = 8192` ⇒ 16-B aligned ✓ |
| kernel name contains `_bn_<bn>_` | 1451-1480 | distinct name ⇒ **rule 33 satisfied automatically** |
| `get_template_definition(..., bm, bn, bk, ...)` | ~1560-1583 | instantiates the `BN = 32` template |
| `grid_dims(N/bn, egroups, 1)` | launch | `(32,256,1)` → `(64,256,1)` ✓ |

**Default behaviour is byte-identical to base.** With the env var unset the
knob returns 64, the override assigns 64 over 64, and the emitted kernel name,
template instantiation and grid are unchanged. The patch cannot regress the
baseline.

### 3.2 Bit-exactness argument (hand-verified, not asserted)

The only machinery that changes shape is the weight stager
`QuantizedBlockLoader<Wtype, BN, BK, BK_padded, true, 128, gs, bits, psl>`.
Hand-traced at `BN = 32`, `tgp_size = 128`:

- `BCOLS_PACKED = 32`, `n_reads = 8`, `kSrcBytes = 8` ⇒ lands on the
  **already-certified 8-byte `kWideLoad8ShapeOk` path**, so
  `load_unsafe_wide` is confirmed safe at this shape (it is the same wide-load
  certification the `BN = 64` build uses, at a different `n_reads`).
- `src_byte_off = bi*256 + bj` (8-B aligned); `dst_byte_off = bi*144 + bj*4`
  (16-B aligned). No unaligned or overlapping access.
- `pair_scales` indexes 0 for both chunks in both variants.
- Layout 2 (`set_pairwise_rowmajor`, the down layout) stages the **identical
  (row, group) set**, just split across twice as many threadgroups.
- Layout 1 (`set_pairwise_packed`, gate/up) is not reached by the gate and is
  untouched.

Accumulation order within a `(row, column)` output element is unchanged: the
K loop, `BK = 64`, `SK = 32`, and the MMA descriptor are all invariant (§5.2).
Narrowing `BN` partitions the **output columns** across threadgroups; it does
not re-associate any sum. ⇒ **bit-exact by construction**, pending the M5
`LagunaUpstreamEquivalence` run that only the ranked host can perform.

### 3.3 Build health (real, cheap, and not a timing claim)

The submitted file compiles under the **exact** scored-worker command extracted
from `.build-worker/mlx-metal/compile_commands.json` (`/usr/bin/c++ -O3 -DNDEBUG
-std=gnu++20 -arch arm64 -mmacosx-version-min=26.5.2 ...`), in 2.0 s, exit 0,
**zero warnings**. Per rule 86 this is build health only and is never offered as
evidence of a speedup.

Budget checks at `BASE_SHA`: `senpai/validate-assignment-scope.sh` → *scope OK,
1 submitted path*; `senpai/check-editable-budget.sh` → *current=2681206/3000000,
headroom=318794, **growth=998**/262144*. The 1740-byte diff is well inside the
assignment's 8 KiB cap.

---

## 4. Rule-75 surface digests

Timing is not claimed on this host, so the pre/post digest discipline is
applied to the offline compile pipeline (`research/maple-alphonse-r107c-jit-air.sh`
takes the digest before and after every compile and `exit 3`s on drift).

| when | digest of `.../backend/metal/quantized.cpp` |
| --- | --- |
| base (`BASE_SHA` blob) | `cf6d3847d583730fc7366110d91f54c676405869634cd0ae4eebbd362363c612` |
| candidate, pre-compile == post-compile (stable) | `e5dac8a08c2a04c565fb575d86e710721d548413e826fa113f9b99dc23f33258` |
| offline preamble+kernel surface during the AIR census | `803fe16405b346e41b80f5202c4d5135c137f95c94051e69b37c5679ae3c2eba` (pre == post) |

---

## 5. Static AIR census (rule 82: geometry, not milliseconds)

### 5.1 Method

`research/maple-alphonse-r107c-jit-air.sh` reconstructs the JIT translation unit
offline: it extracts the `R"preamble( ... )preamble"` bodies from
`Vendor/mlx-swift/Source/Cmlx/mlx-generated/{utils,gemm_nax,quantized_utils,fp_quantized_nax}.cpp`,
appends `#define DARKBLOOM_SWIGLU_REGLOCAL 1` and `#define DARKBLOOM_BSEARCH_HOIST 1`,
appends the exact `[[host_name(...)]] [[kernel]] decltype(...)` instantiation the
runtime would emit, and compiles with `xcrun metal -std=metal4.0 -fno-fast-math`
— the same flags `device.cpp:630-632` uses. `research/maple-alphonse-r107c-air-census.py`
then counts opcodes from `air-objdump --disassemble`.

Instantiation held fixed except `BN`:

```
fp_gather_qmm_rhs_expert_nax<bfloat16_t, 16, 4, /*BM*/64, /*BN*/{64|32},
                             /*BK*/64, /*WM*/4, /*WN*/1, 1,
                             /*K*/512, /*N*/2048, bfloat, /*eg*/256, 1, 1, 2>
```

### 5.2 Census (BN = 64 → BN = 32)

| quantity | BN=64 | BN=32 | note |
| --- | --- | --- | --- |
| `air_bytes` | 35984 | **26128** | −27.4 % |
| ir_lines | 3635 | 2351 | |
| device loads / stores | 69 / 55 | 44 / 30 | fewer address computations |
| threadgroup loads / stores | 20 / 5 | 12 / 5 | |
| **`barrier` sites** | **4** | **4** | invariant |
| **`matmul2d ... run_cooperative` sites** | **3 / 1 call** | **3 / 1 call** | invariant |
| `mma_getptr` | 12 | 12 | invariant |
| phi / br | 87 / 242 | 59 / 149 | see §9 carry-forward |
| alloca / lifetime | 74 / 76 | 45 / 47 | |
| insert/extract element | 71 / 136 | 51 / 86 | fragment count halves |
| fmul / fadd | 12 / 0 | 12 / 0 | invariant |
| `store_slice` specialisations | 28 | 14 | one per output fragment |
| threads / TG | 128 | 128 | invariant |
| simdgroups / TG | 4 | 4 | invariant |
| `kWsElems` bytes (`BN*BK_padded`, `BK_padded=72`) | 9216 | 4608 | halves |
| `SN` | 64 | 32 | |
| `TN` fragments | 4 | 2 | |
| threadgroups launched / layer | 8192 | **16384** | doubles |
| `grid_dims` | (32,256,1) | **(64,256,1)** | |

**MMA descriptor is identical in both**:
`matmul2d_descriptor<16,32,16,0,1,1,mode 1>`, `execution_simdgroups<1>`, exactly
one `run_cooperative_b16_b16_f32` call site. Tile types change only in fragment
count: `Wtile <bfloat,4,2> → <bfloat,2,2>`, `Atile <bfloat,1,2>` unchanged,
`Dtile <float,1,4> → <float,1,2>`. Loader
`QuantizedBlockLoader<DF16b,64,64,72,1,128,16,4,2> → <...,32,64,72,1,128,16,4,2>`,
both taking `load_unsafe_wide<1,1>`.

**⇒ Aggregate MMA work is exactly invariant. Per-threadgroup accumulator and
weight-fragment register footprint halves. Barrier count per K step is
unchanged.** This is the core of the mechanism claim in §7.

### 5.3 Generated-twin consistency

`artifacts/maple-alphonse-r107c/twin-diff.txt`: 175 lines (167 `<`, 17 `>`),
every one either inlined `fp4.h`/`fp8.h` expansion or a stripped comment. The
`mlx-generated/fp_quantized_nax.cpp` twin is semantically in sync with the
header, so **no twin edit is needed** and the submitted surface stays at one
file.

### 5.4 `N-BUILD` is refuted

Both `BN` variants compile cleanly. The only diagnostic is an unused
`BN_padded` (pre-existing, present at `BN = 64` too). The preregistered
`N-BUILD` outcome does **not** apply.

---

## 6. Measured pipeline and occupancy facts (gen-16, arch-independent)

### 6.1 What is measurable here

Two things: what the Metal compiler *requests* per threadgroup, and how many
threadgroups of a given allocation the hardware actually keeps co-resident.
Both are properties of the compiled pipeline / the allocator, not of NAX
dispatch, so `N-REACH` does not invalidate them.

### 6.2 `staticThreadgroupMemoryLength` (measured)

`research/maple-alphonse-r107c-pipeline-probe.swift` builds each variant through
`device.makeLibrary(source:options:)` (`mathMode = .safe`,
`languageVersion = .version4_0`) and reads the pipeline back.

| pipeline | `maxTotalThreadsPerTG` | `staticThreadgroupMemoryLength` | `threadExecutionWidth` |
| --- | --- | --- | --- |
| `..._bm_64_bn_64_bk_64_wm_4_wn_1_k_512_n_2048_eg_256_ws_1_wl_1_ps_2` | 1024 | **9232 B** | 32 |
| same with `bn_32` | 1024 | **4624 B** | 32 |

Device limits: `maxThreadgroupMemoryLength = 32768`,
`maxThreadsPerThreadgroup = 1024³`. The 9232 B figure independently confirms
the prior-art number; 4624 B is new. (9232 = 9216 `kWsElems` + 8 B `bounds[2]`,
rounded up to 16.)

### 6.3 Honest negative: `maxTotalThreadsPerThreadgroup` says nothing about registers here

I calibrated the API against deliberately register-hungry kernels
(`light`, `heavy32/64/128/192` live floats per thread). **All of them, including
192 live floats/thread, reported `maxTotalThreadsPerThreadgroup = 1024`.** On
this device the property does not reflect register pressure, so the identical
1024/1024 for the two `BN` variants is **uninformative about registers** and I
do not use it. Recording this prevents a future reader from over-claiming
"registers unchanged" from that number. With `applegpu-nt` unavailable (§2),
**this report has no register-count evidence at all** — the halved fragment
counts in §5.2 are an AIR-level proxy, nothing stronger.

### 6.4 Resident-threadgroup census (measured, and it refutes the naive model)

`research/maple-alphonse-r107c-occupancy-census.swift` allocates dynamic
threadgroup memory via `setThreadgroupMemoryLength`, launches 8192
threadgroups × 128 threads, has each threadgroup bump a `live` counter, spin a
bounded 120 000-iteration FMA loop sampling `atomic_max` into `peak` every 256
iterations, then decrement. 5 reps + warmup per byte point.

| TG bytes | n | mean | sd | min | max |
| --- | --- | --- | --- | --- | --- |
| 0 | 5 | 200.4 | 10.3 | 191 | 216 |
| 1024 | 5 | 210.8 | 9.8 | 199 | 222 |
| 2048 | 5 | 197.4 | 15.6 | 171 | 210 |
| 4096 | 5 | 183.0 | 26.3 | 157 | 227 |
| **4624 (`bn=32`)** | 5 | **160.2** | **3.6** | 155 | **165** |
| 6144 | 5 | 148.6 | 4.4 | 141 | 152 |
| 8192 | 5 | 133.6 | 3.4 | 130 | 137 |
| **9232 (`bn=64`)** | 5 | **127.8** | **3.8** | 123 | **133** |
| 12288 | 5 | 119.8 | 4.4 | 116 | 127 |
| 16384 | 5 | 112.0 | 5.8 | 104 | 118 |
| 24576 | 5 | 103.2 | 7.2 | 100 | 116 |
| 32768 | 5 | 89.0 | 12.3 | 80 | 103 |

**Result: `bn = 32` is co-resident 1.254× (means) / 1.241× (maxima) more often
than `bn = 64`**, i.e. 8.25 vs 6.65 threadgroups per core and 33 vs 26.6
resident simdgroups per core at 20 cores. The two distributions do not overlap
(160.2 ± 3.6 vs 127.8 ± 3.8), and the curve is clean and monotone for every
point ≥ 4624 B.

**Two honest caveats.** (i) Below 4096 B the curve is noisy and non-monotone
(sd up to 26) because a hard launch/scheduler cap of ~10–11 TGs/core (≈216–227
TGs) dominates there, not memory. (ii) That same cap **refutes** the naive
"32 KiB of threadgroup memory per core, so 9216 B ⇒ 3 TGs and 4608 B ⇒ 7 TGs"
model that a reader might expect: at 32768 B we still see 103 TGs resident,
≈169 KiB/core, so the per-core threadgroup-memory pool is far larger than the
32 KiB per-*threadgroup* API limit. The real halving-to-1.25× gap is exactly why
this had to be measured rather than assumed — **an assumed 2× would have
overstated the candidate by 60 %.**

---

## 7. Rule-82 byte / geometry ledger

`research/maple-alphonse-r107c-byte-ledger.py` →
`research/artifacts/maple-alphonse-r107c/byte-ledger.json`. Pinned geometry from
`Sources/MLXFastModel/LagunaConfig.swift`: 40 layers (39 MoE, layer 0 dense),
hidden 2048, moeIntermediate 512, 256 experts, top-8, group_size 16, 4-bit
nvfp4, e4m3 scales. 512-token prefill ⇒ 4096 expanded rows ⇒ **mean 16 rows per
expert**. (Cross-check: gate_up 1.125 MiB + down 0.5625 MiB per expert per layer
× 256 × 39 = 17.667 GB, matching the assignment's 17.666 GB weight budget.)

| quantity | bn=64 | bn=32 | ratio |
| --- | --- | --- | --- |
| `grid_dims` | (32,256,1) | (64,256,1) | — |
| threadgroups / layer | 8192 | 16384 | 2.000× |
| threads / TG | 128 | 128 | 1.000× |
| simdgroups / TG | 4 | 4 | 1.000× |
| **MMA-active simdgroups / TG** | **1** | **1** | **1.000×** |
| `SN` | 64 | 32 | 0.500× |
| `Dtile` fragments (TM×TN) | 4 | 2 | 0.500× |
| TG bytes (measured) | 9232 | 4624 | 0.501× |
| weight bytes / TG | 18432 | 9216 | 0.500× |
| **weight bytes / layer** | **150994944** | **150994944** | **1.000×** |
| **weight bytes / family** | **5.889 GB** | **5.889 GB** | **1.000×** |
| A bytes / TG | 16384 | 16384 | 1.000× |
| **A re-read multiplicity** | **32×** | **64×** | **2.000×** |
| A *requests* / layer | 134 MB | 268 MB | 2.000× |
| A *requests* / family | 5.234 GB | 10.47 GB | 2.000× |
| A **unique** bytes / layer | 4194304 | 4194304 | 1.000× |
| output bytes / layer | 16777216 | 16777216 | 1.000× |
| resident TGs (measured max) | 133 | 165 | 1.241× |
| resident simdgroups / core | 26.6 | 33.0 | 1.241× |
| weight bytes in flight / core | 15322 | 9504 | 0.620× |

### 7.1 Reading the ledger

- **Weight traffic is exactly invariant**: 32 N-tiles × 18432 B ≡ 64 N-tiles ×
  9216 B. `bn` re-partitions the same weight bytes; it does not re-read them.
  Output traffic is likewise invariant (16 MiB/layer, each element written once).
- **The one real cost is A-operand request multiplicity, 32× → 64×.** Each
  threadgroup pulls the same 16 KiB expert row-block, and there are twice as
  many threadgroups. Family-wide that is 5.23 GB → 10.47 GB of *requests*, i.e.
  +27 % against the 19.465 GB unique-byte roofline **if every request missed
  cache**. It should not: the unique A footprint is only 4 MiB per layer and the
  re-read is dense and near-simultaneous, so it should stay SLC-resident and
  cost ≈0 DRAM bytes. **This is the ledger's central falsifiable risk.** If the
  M5 shows the down third of the family *slower*, A-side cache behaviour is the
  first thing to check.
- **Bytes in flight per core barely move.** Per-threadgroup in-flight weight
  bytes drop to 0.62×, but 1.241× more threadgroups are resident:
  0.62 × 1.241 ≈ 0.77×, so `bn = 32` actually keeps *fewer* weight bytes in
  flight per core. The lever is therefore **not** bandwidth utilisation.
- **The lever is latency hiding**: 33 vs 26.6 resident simdgroups per core, with
  an unchanged 2 barriers per K step (§5.2) and 8 K steps. More resident
  simdgroups per core ⇒ more independent work to overlap those barriers.

### 7.2 Expected harvest, stated with its own uncertainty

The family's own roofline is the binding constraint. Per the assignment: family
= 76 dispatches, M5 `W = 43.2619 ± 0.402 ms`; 19.465 GB of unique bytes at a
calibrated 546.2 GB/s ⇒ a **35.6 ms floor**, so only **≈7.6 ms** of
stall-driven residual exists — the family is already at **82 %** of its
bandwidth roofline. Down is roughly a third of the family's weight bytes
(0.5625 / 1.6875 MiB), so the down share of the residual is
7.6619 / 3 = **2.554 ms**.

Two bounds, both anchored on that number:

| bound | model | ms | % of score | ≥ 0.4 % gate | ≥ 1.35 ms (3σ) |
| --- | --- | --- | --- | --- | --- |
| **ceiling** | a down-only change deletes the *entire* down share of the residual | **2.554** | **0.966** | yes | yes |
| **mechanism estimate** | stall time ∝ 1 / resident concurrency ⇒ ×(1 − 1/1.2535) | **0.517** | **0.195** | **no** | **no** |

The ceiling is what the arm would be worth if `bn = 32` removed *all* remaining
stall on the down shape; it is not a prediction, it is the largest number the
roofline permits and it exists only to show the arm is not absurd. The
mechanism estimate is the defensible one: the measured lever is
resident-concurrency, the measured gain is 1.2535× (§6.2), and stall time that
is hidden by concurrency scales as its inverse. **0.195 % of score fails both
the assignment's 0.4 % relevance gate and its 1.35 ms 3σ bar** (σ_Δ = 0.4497 ms).

Even the ceiling would need the mechanism to be ~5× more effective than the
occupancy model says. **Honest expectation: real but sub-threshold. C2a is not
independently rankable and should not consume a paired M5 session on its own;
it is only worth carrying as a component of a bundle, or as evidence that the
`bn` axis is exhausted.** This is what makes `N-FLOOR` the reported outcome
rather than a marginal `V-TILE`.

---

## 8. The bigger prize found on the way: `BM`/`WM`, not `BN`

At mean routing there are **16 rows per expert** (4096 expanded rows / 256
experts). The kernel uses `BM = 64`, `WM = 4` ⇒ `SM = BM/WM = 16` rows per
simdgroup, and `tm = SM * (simd_group_id / WN) = 16 * sgid`, with
`sgp_sm = min(SM, max(0, chunk_rows - tm))`. With `chunk_rows = 16`, only
`sgid = 0` gets `sgp_sm > 0`:

> **1 of 4 simdgroups per threadgroup does any MMA work, while all 4 stage
> weights.** The kernel is weight-staging bound at mean routing, and this is
> completely independent of `BN`.

This is a ≈4× MMA-occupancy deficit sitting on the single largest prefill
family, and it is a far larger target than the 1.25× `bn` effect. It is *not*
in this assignment's scope and I have not implemented it. Two obstacles a
follow-up must clear: `expert_aligned` currently *requires* `wm == 4`, and
`kSwigluRegLocal` requires `(BM/WM) == 16`, so a `WM` change touches the
gate/up correctness lock as well. Flagged as the recommended next experiment
(§11).

---

## 9. Carry-forward from r107-B (folded in, no stage spent)

Per the advisor's accepted carry-forwards:

**§9.2 — AIR-level phi/br gate before timing.** Applied here as a *pre*-timing
screen rather than a post-hoc note: the census in §5.2 records phi 87 → 59 and
br 242 → 149. Both fall, and no new control-flow structure appears, so the
candidate passes the gate. Any future variant that *raises* phi/br while
claiming a win should be re-screened before a paired session is spent on it.

**§9.3 / §9.4 — retire the cache-resident rung.** The cache-resident rung
inflates apparent gains by roughly 30× and must not appear in headline numbers.
Nothing in this report uses it: §6.4 measures occupancy, not throughput, and no
millisecond here is derived from a resident-cache rung. Consumers of the r99 /
r100 headline numbers should keep the ≈30× annotation attached to them; the
≈7.6 ms residual and 0.3781 %/ms price used in §7.2 come from the assignment's
M5 calibration, not from any local rung.

---

## 10. Verdict

Preregistered outcomes, resolved:

| outcome | status |
| --- | --- |
| `V-TILE` | **not demonstrated.** C2a is implemented, bit-exact by construction, and static-ledger-positive, but unmeasurable here and worth only ≈0.195 % of score on its own mechanism model — below the 0.4 % relevance gate (§7.2). |
| `V-XMAJOR` | **no.** |
| `V-EGROUPS` | **no** — already closed-positive at 256 and shipped. |
| **`N-XMAJOR-CLOSED`** | **YES** — C2b closed by archive + external negative (§1 Q2). |
| **`N-REACH`** | **YES** — `is_nax_available()` needs gen ≥ 17; this host is gen 16, so no local NAX runtime evidence is possible (§2). |
| `N-BUILD` | **refuted** — both `BN` variants compile clean (§5.4). |
| `N-CORRECT` | **not triggered** — no bit-exactness violation found; M5 equivalence still owed. |
| **`N-FLOOR`** | **YES, with a closing ledger** — the family is at 82 % of its bandwidth roofline with ≈7.6 ms of residual; the down share of that residual is 2.554 ms (a hard ceiling of 0.966 % of score) and the `bn` mechanism model claims only 0.195 % of it, below both the relevance gate and the 3σ bar (§7.2). |

**Bottom line.** `routed_gather_gemm`'s NAX expert path is at its floor on the
axis this assignment was allowed to touch. Three of four axes were already
closed; the fourth is admissible only on the down shape, is a genuine but small
occupancy improvement, and its own mechanism model puts it below the
assignment's relevance gate — the down shape simply does not own enough
above-roofline residual for a `bn` change to matter. The larger remaining prize
is the `BM`/`WM` simdgroup-idling deficit in §8, which no `bn` change can reach.

---

## 11. Handoff and follow-ups

**Handoff.** Per the assignment, the patch goes to **maple-fern on #625** — not
to an official submission — with the rule-75 digests (§4) and the rule-77
reached-dispatch geometry table (§3.1 + §5.2 + §7). maple-frieren (#597) owns
the channel. Deconfliction as assigned: tanjiro #620 = prefill non-GEMM;
edward #629 = decode threadgroup packing; nezuko #616 = r103 revert residual.

**What an M5 owner needs to do to close C2a.** (1) Set
`DARKBLOOM_EXPERT_DOWN_BN=32`; confirm the emitted kernel name contains
`_bn_32_` (rule 33 / rule 77 reachability evidence). (2) Run
`research/run_upstream_equivalence.sh` — expected bit-exact. (3) Paired
contemporaneous alternating whole-model A/B — but note §7.2: the mechanism model
predicts ≈0.5 ms, well under the 1.35 ms 3σ bar, so **do not spend a paired
session on C2a alone**; carry it only inside a bundle, or measure the
`routed_gather_gemm` down dispatches directly rather than whole-model prefill.
(4) Check the down-shape dispatches specifically for an A-side cache regression
(§7.1).

**Follow-ups I did not implement.**

1. **`BM`/`WM` for mean-16-row experts (§8) — highest value.** Needs
   `expert_aligned`'s `wm == 4` requirement and `kSwigluRegLocal`'s
   `(BM/WM) == 16` to be revisited together.
2. **Extend the occupancy census to threads/TG**, not just bytes/TG, to separate
   the ~10–11 TG/core hard cap from the memory-driven regime; that would sharpen
   the 1.25× into a proper model.
3. **Resolve the `applegpu-nt` AIR 2.5 vs 2.8 blocker** (an AIR-2.8-capable
   translator, or a `-std=metal3.x` reconstruction) to get real register and
   occupancy-limit numbers instead of the AIR-level fragment-count proxy in
   §6.3.
4. **Settle the `g17p`/`g17s` arch-vs-gate question (§2)** in one authoritative
   place so future students stop re-deriving it.

## 12. Reproduction

```bash
export BASE_SHA=e1d206da6bedd2a3ce3957ae05437a78317e4620
senpai/validate-assignment-scope.sh "$BASE_SHA" \
  Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/quantized.cpp
senpai/check-editable-budget.sh "$BASE_SHA"

# offline JIT reconstruction + AIR census (rule-75 digests enforced inside)
research/maple-alphonse-r107c-jit-air.sh
python3 research/maple-alphonse-r107c-air-census.py

# measured pipeline properties
xcrun swiftc -O -o /tmp/probe research/maple-alphonse-r107c-pipeline-probe.swift && /tmp/probe

# measured resident-threadgroup census (~21 s)
xcrun swiftc -O -o /tmp/census research/maple-alphonse-r107c-occupancy-census.swift && /tmp/census

# rule-82 ledger
python3 research/maple-alphonse-r107c-byte-ledger.py
```

Artifacts: `research/artifacts/maple-alphonse-r107c/` —
`jit-preamble.metal`, `down-bn{64,32}.{metal,air,ir,compile.log}`,
`twin-diff.txt`, `air-census.json`, `occupancy-census.csv`, `byte-ledger.json`.
