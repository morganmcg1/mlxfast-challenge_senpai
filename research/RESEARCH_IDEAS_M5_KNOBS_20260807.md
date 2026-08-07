# M5 Knob & Dispatch Audit — 2026-08-07

Subagent report: M5-specific optimization opportunities via runtime knobs,
dispatch count, and `_nax` kernel tiling. All findings cite line numbers.
`rg` unavailable; `grep` used throughout.

---

## 1. DARKBLOOM_STAGE_BM128 — DEAD END (confirmed by prior research)

**Mechanism**: `DARKBLOOM_STAGE_BM128` selects the gather-GEMM M-tiling for the
expert-aligned prefill path (`gather_qmm_rhs_nax`).
- **Host**: `quantized.cpp:1494-1524` `darkbloom_stage_bm128_variant()` reads the
  env var. Default (unset) → **variant 5** (BM=64, WM=4, WN=1; SM=16, 128 thr/TG).
- **Values**: unset/5 = BM64/WM4/WN1 (shipped), 4 = BM64/WM4/WN2, 0 = upstream
  BM64/WM2/WN2, 1 = BM128/WM4, 2 = BM128/WM2 (regression), 3 = BM128/WM8.
- **Ranked behavior**: ranked runner sets NO DARKBLOOM_* env vars, so unset =
  shipped default = variant 5 (confirmed `quantized.cpp:1489-1493`).
- **Swift gate**: `LagunaRuntimeModel.swift:234-245` `lagunaExpertAlignedStageEnabled`
  accepts `["", "4", "5"]` and gates `lagunaExpertAlignedGatherEnabled` (the
  halved-scales prefill path). Empty/unset passes the gate. The Swift and C++
  defaults are independent but both resolve unset → variant 5.
- **Changeable in source?**: YES — changing `return 5` → `return 4` at
  `quantized.cpp:1504` is a ~2-byte source change (not env var).

**The +17.47% kernel-level measurement** (`quantized.cpp:1477-1487`):
variant 4 vs 5 = +17.47% (4/4 pairs, M4 kernel-level ABBA). This is the MMA
phase only.

**WHY IT'S DEAD**: `fp_quantized_nax.h:1863-1864` — the register-local SwiGLU
epilogue (`DARKBLOOM_SWIGLU_REGLOCAL`, default ON) is gated on `WN == 1`:
```
constexpr bool kSwigluRegLocal = (WN == 1) && (BN == 64) && ((BM / WM) == 16);
```
Variant 4 (WN=2) **disables reglocal** → falls back to the staged epilogue
(`fp_quantized_nax.h:2213-2240`): 2 threadgroup barriers + threadgroup memory
round-trip per column tile. The MMA gain is more than canceled by losing the
zero-barrier register-local epilogue.

**Confirmed DEAD by team**: commit `cb2bf36` (2026-08-06):
> "prefill variant 5→4 switch is DEAD — variant 5 won end-to-end on 2026-08-01
> (198.00 µs fastest). Variant 4 loses reglocal SwiGLU fusion."

The 198.00 µs fastest record was variant 5 (with reglocal), NOT variant 4.
Variant 4 was also bundled with toxic QHOIST and rejected at -11.48% (commit
`7b0f3a9`, submission 89521f6, score 2.4822). Never tested alone on M5, but the
reglocal loss makes it a net regression end-to-end regardless.

| | Value |
|---|---|
| Estimated gain | **NEGATIVE** (loses reglocal SwiGLU; confirmed DEAD) |
| Byte cost | ~2 bytes (return 5→4) |
| Bit-exact | YES (`quantized.cpp:1448-1457`: max_abs_diff=0) |
| Status | DO NOT pursue |

---

## 2. Decode Dispatch Count Per Step

Tracing the decode call chain (`LagunaRuntimeModel.swift`):

**Per attention layer** (39 layers, `callAsFunction` at L5827):
1. Fused norm+QKV+g_proj (1 dispatch, L5882/5907/5915 — affine INT8 or NVFP4 R1)
2. Fused QK-norm+RoPE+cache-write+SDPA (1 dispatch, L6132/6158 — sliding or full)
3. Fused gate+O-proj (1 dispatch, L6316/6346/6415 — gated affine or NVFP4)
= **3 dispatches/attention-layer**

**Per MoE layer** (39 layers, `forward` at L10446):
1. Router gate + RMSNorm (1 fused dispatch, residual_rms_router)
2. Routed SwiGLU QMV + top-8 (1 dispatch, L10505/10514/10525/10539)
3. Routed+shared down + residual (1 fused dispatch, L10589 — `lagunaRoutedSharedDownResidual`)
= **3 dispatches/MoE-layer**

**Layer 0** (dense MLP, not MoE): ~3-4 dispatches (norm+gate/up, SwiGLU, down+residual).

**Final**: 1 dispatch for final RMSNorm + lm_head pruner (certified two-pass, L11445).

**Total per decode step** (40 layers): ~3×39 (attn) + 3×39 (MoE) + ~3 (layer 0) + 1 (norm+head)
≈ **~240 dispatches/step**, with `asyncEval` fires at 7 boundaries (`at:0,1,7,15,23,31,39`,
L683) to overlap GPU execution with CPU graph construction.

**Eliminable dispatches**: The decode path is **fully fused**. No standalone
residual-add, separate Q/K/V, separate SwiGLU, or separate top-8 dispatches
remain in the default path. The asyncEval schedule is already near-optimal
(L663-672: ladder1=1.0178 vs at:7=1.0170, essentially tied, 66-run Latin square).
**No obvious dispatch to eliminate on the decode path.**

| | Value |
|---|---|
| Dispatches/step | ~240 (3/layer × 40 + final head) |
| Eliminable | NONE identified — decode is fully fused |
| asyncEval | Near-optimal (7 fires, +9.7% over off already captured) |

---

## 3. Vendor `_nax` Kernel Tiling (`fp_quantized_nax.h`)

**Template params** (`fp_quantized_nax.h:664-678`): `BM=64, BK=64, BN=64, WM=2, WN=2`
(defaults; overridden by host `darkbloom_stage_bm128_variant()`).

**Derived constants** (L751-759):
- `SM = BM/WM`, `SN = BN/WN`, `SK = 32` (fixed, `static_assert`)
- `TM = SM/16`, `TN = SN/16`, `TK = SK/16`
- For shipped variant 5: SM=16, SN=64, TM=1, TN=4, TK=2

**Tunable constants**:
- `SIMD_SIZE = 32`, `QUAD_SIZE = 4` (L30-31, fixed)
- `SK = 32` (L753, `static_assert` — cannot change without kernel rewrite)
- Threadgroup size: `WM * WN * SIMD_SIZE` (L712) = 128 for variant 5, 256 for variant 4
- `BK_padded = BK + 16/sizeof(Wtype)` (L703) = 80 for BF16 — padding for alignment

**Function constants** (L9-24): `align_M/N/K` (200-202), `gather_run_skip` (203),
`stage_widest/wideld/runbar/novol` (204-207). All resolved once per process.

**Byte budget**: `fp_quantized_nax.h` ~78K/524,288 = **~446KB headroom**.
`quantized.cpp` ~84K/524,288 = **~440KB headroom**. Both in `editablePaths`.

**Key constraint**: The reglocal SwiGLU epilogue (`kSwigluRegLocal`, L1863-1864)
is locked to `WN==1 && BN==64 && BM/WM==16`. Any tiling change that moves WN away
from 1 loses this optimization. This is the binding constraint that makes variant
4 a net loss. A tiling change that keeps WN=1 but adjusts BM/WM (e.g. BM=128/WM=8
= variant 3, SM=16) would preserve reglocal but was measured as a regression
(`quantized.cpp:1427`: "SM=16 both mechanisms" — variant 3 untested in the
ABBA table but listed; variant 1 BM128/WM4 SM=32 "less expert re-staging").

| | Value |
|---|---|
| Tunable | BM/BK/BN/WM/WN via host `darkbloom_stage_bm128_variant()` |
| Constraint | `kSwigluRegLocal` requires WN==1 (binding) |
| Byte budget | 446KB (nax.h) + 440KB (quantized.cpp) — ample |
| Actionable | Variant 3 (BM128/WM8, SM=16, WN=1) UNTESTED — preserves reglocal |

**UNTESTED: Variant 3** (`quantized.cpp:1428`: BM=128, WM=8, WN=1). This is the
ONLY variant that both reaches SM=16 (the proven winning band) AND preserves
WN=1 (reglocal). It was never measured in the ABBA table (only variants 0/4/5
were). The comment says "SM=16 both mechanisms" but no measurement data is
recorded. This is a genuinely untested 0-byte (source-default) prefill knob.
**Risk**: BM=128 doubles the M-tile, which may reduce occupancy on M5's 40-core
GPU (fewer threadgroups in the M dimension). Needs M5 measurement.

---

## 4. Runtime Environment Knobs (Complete Inventory)

### Swift-side (`LagunaRuntimeModel.swift` + `LagunaLmHeadPrune.swift`)
**89 total** `ProcessInfo.processInfo.environment` reads. Key defaults (all
`!= "0"` = default ON unless noted):

| Knob | Default | Effect | Line |
|---|---|---|---|
| `DARKBLOOM_FUSED_QKV` | OFF (`== "1"`) | Row-concat QKV bank (prefill only) | L114 |
| `DARKBLOOM_FUSED_SHARED_GATE_UP` | ON | Shared expert fused gate/up | L122 |
| `DARKBLOOM_FUSED_SHARED_SWIGLU_QMV` | ON | Shared SwiGLU QMV fusion | L129 |
| `DARKBLOOM_FUSED_SHARED_DOWN_RESIDUAL` | ON | Shared down + residual | L137 |
| `DARKBLOOM_FUSED_ROUTED_SHARED_DOWN_RESIDUAL` | ON | Routed+shared down+residual | L144 |
| `DARKBLOOM_FUSED_ROUTED_SWIGLU_QMV` | ON | Routed SwiGLU QMV | L150 |
| `DARKBLOOM_PACKED_SCALES` | ON | Scale-interleaved side copy | L166 |
| `DARKBLOOM_ROUTER_PRECOMPUTED_KEYS` | ON | Router keys precomputed | L172 |
| `DARKBLOOM_FUSED_ROUTED_DOWN_REDUCE` | ON | Routed down + reduce | L199 |
| `DARKBLOOM_FUSED_ROUTED_GATE_UP` | ON | Routed fused gate/up (decode) | L217 |
| `DARKBLOOM_PREFILL_FUSED_GATE_UP` | ON | Prefill fused gate/up | L222 |
| `DARKBLOOM_PREFILL_FUSED_GATE_UP_HALVED` | ON | Prefill halved scales | L225 |
| `DARKBLOOM_FUSED_RESIDUAL_RMS` | ON | Decode residual+RMSNorm | L257 |
| `DARKBLOOM_QMV_R1` | ON | 1-row QMV split | L271 |
| `DARKBLOOM_NATIVE_AFFINE_QKV` | ON | INT8 affine QKV | L300 |
| `DARKBLOOM_NATIVE_AFFINE_OPROJ` | ON | INT8 affine O-proj | L373 |
| `DARKBLOOM_NATIVE_AFFINE_GPROJ` | ON | INT8 affine g_proj | L412 |
| `DARKBLOOM_ROUTER_ROWS_PER_GROUP` | 8 | Router TG rows (sub-8 = null) | L634 |
| `DARKBLOOM_DECODE_ASYNC_STAGE` | `at:0,1,7,15,23,31,39` | asyncEval schedule | L683 |
| `DARKBLOOM_PREFILL_ASYNC_LADDER` | 1 (stride 1) | Prefill asyncEval | L736 |
| `DARKBLOOM_NVFP4_SCALE_DEFER` | ON | 2^14 scale fold | L6721 |
| `DARKBLOOM_LM_HEAD_PRUNE` | ON | Two-pass lm_head | LmHeadPrune:79 |
| `DARKBLOOM_EXPERT_ALIGNED_GATHER` | ON (NAX) | Expert-aligned gather | L245 |
| `DARKBLOOM_PREFILL_QK_NORM_ROPE` | ON | Prefill QK-norm+RoPE fusion | L497 |

### C++-side (`quantized.cpp`) — `_nax` kernel selection

| Knob | Default | Effect | Line |
|---|---|---|---|
| `DARKBLOOM_STAGE_BM128` | 5 (variant 5) | Gather-GEMM M-tiling | L1494 |
| `DARKBLOOM_EXPERT_ALIGNED_GATHER` | ON | Expert-aligned path | L1356 |
| `DARKBLOOM_EXPERT_GATHER_GROUPS` | **256** | Threadgroups/experts | L1408 |
| `DARKBLOOM_EXPERT_STAGE_WIDEST` | ON | Wide 16B TG stores | L1372 |
| `DARKBLOOM_EXPERT_STAGE_WIDELD` | ON | Wide 8B device loads | L1387 |
| `DARKBLOOM_STAGE_WIDEST` | OFF (`stage_flag`) | Non-expert wide stores | L1335 |
| `DARKBLOOM_STAGE_WIDELD` | OFF (`stage_flag`) | Non-expert wide loads | L1340 |
| `DARKBLOOM_STAGE_RUNBAR` | OFF (`stage_flag`) | Barrier tuning | L1345 |
| `DARKBLOOM_STAGE_NOVOL` | OFF (`stage_flag`) | Volatility tuning | L1350 |
| `DARKBLOOM_STAGE2_GATHER` | 1 | Weight staging overlap | L1641 |
| `DARKBLOOM_GATHER_XMAJOR` | 0 (OFF) | X-tile fold (arms removed) | L1592 |
| `DARKBLOOM_SWIGLU_REGLOCAL` | ON | Register-local SwiGLU | L1609 |
| `DARKBLOOM_PREFILL_GATHER_RUNSKIP` | ON (100%) | Dead-run elision | L1271 |
| `DARKBLOOM_STATIC_NVFP4_SHAPES` | ON (`!= "0"`) | Static expert shape | L518/L1726 |
| `DARKBLOOM_BSEARCH_HOIST` | ON | Hoisted slot bounds | L1615 |
| `DARKBLOOM_TRACE_FUSION` | OFF (`== "1"`) | Debug trace | L1789 |

**Critical note**: `DARKBLOOM_EXPERT_GATHER_GROUPS` comment (L1391) says "default
128" but the **code returns 256** for empty (L1409). The comment is stale. The
comment (L1400-1404) says 256 "measures closer to the acceptance ceiling in the
single-shot harness regime." Since AGENTS.md confirms the wrapper does NOT cap
gains, 256 should be safe, but this is already the shipped default.

---

## 5. Actionable Findings Summary

### HIGH PRIORITY — Variant 3 (BM128/WM8/WN1) — UNTESTED
- **Mechanism**: `quantized.cpp:1428` variant 3 = BM=128, WM=8, WN=1.
  Reaches SM=16 (proven winning band) AND preserves WN=1 (reglocal SwiGLU).
- **Why unique**: The only variant that satisfies BOTH `kSwigluRegLocal` guard
  (`fp_quantized_nax.h:1864`: WN==1) AND the SM=16 band that the RUNSKIP elision
  model proved optimal (`quantized.cpp:1439-1440`: SM=16 elision 60.7% vs 40.5%).
- **Estimated gain**: Unknown — never measured. Theoretical: SM=16 gives the
  RUNSKIP elision prize (60.7% vs 40.5%), and reglocal is preserved. BM=128 may
  reduce M-dim occupancy (fewer threadgroups: M/128 vs M/64). On M5 with 40 cores
  and the prefill M=512, that's 4 vs 8 threadgroups in M — may underutilize.
- **Byte cost**: ~2 bytes (change `return 5` → add case for 3 / change default).
  Actually: change the default `return 5` at L1504 to `return 3`, and the switch
  at L1699-1706 already maps case 3 → `bm=128; wm=8`. The Swift gate at L235
  accepts `["", "4", "5"]` — would need to add "3" OR rely on empty string
  (which it accepts). Since ranked runner sets no env var, the C++ default
  controls; the Swift gate accepts "" regardless. **But** the Swift gate
  `lagunaExpertAlignedGatherEnabled` (L245) is used for halved-scales; variant 3
  has WN=1 which satisfies the C++ `expert_aligned` guard (L1723: wn==2||wn==1).
  So the Swift gate just needs "" in its accepted set — it already is.
- **Bit-exact**: YES — same argument as variant 4 (`quantized.cpp:1448-1457`:
  BM/BN/BK/SK/WN unchanged except BM/WM; SN=32, TN=2, TK=2 identical; only row
  ownership changes). **CAUTION**: BM=128 changes TM=SM/16=1 (same as variant 5
  since SM=16), but BM=128 means y_row stride doubles. Need to verify the
  `align_M` and `M >= 64` guards still pass. M=512 prefill: `align_M = (512%128)==0`
  = true. Should be fine.
- **Risk**: M-dim occupancy halving. Needs M5 measurement. The AGENTS.md warning
  about geometry flipping across core counts applies.
- **RECOMMENDATION**: This is the single most promising untested 0-byte knob.
  Test variant 3 alone on M5.

### MEDIUM — `DARKBLOOM_EXPERT_GATHER_GROUPS` 256→128
- **Mechanism**: `quantized.cpp:1408`. Default 256 (one expert per TG). 128 =
  two experts per TG, "captures roughly two-thirds of the 256 gain while keeping
  speedup comfortably mid-band" (L1401-1403).
- **Estimated gain**: NEGATIVE vs current (256 is faster per the comment). But
  256 "measures closer to acceptance ceiling" — if the official wrapper truly
  doesn't cap, 256 is correct. Reverting to 128 would be a safety play, not a win.
- **Status**: Current default is 256. No action unless 256 causes rejection.

### LOW — Non-expert STAGE_WIDEST/WIDELD (currently OFF)
- **Mechanism**: `quantized.cpp:1335-1350`. These apply to the NON-expert
  gather-QMM path (function constants 204-207). Currently OFF (default).
  The expert path already has WIDEST/WIDELD ON (L1372/1387).
- **Estimated gain**: Low — the non-expert path is the fallback; the scored
  prefill uses the expert-aligned path (M5 selects _nax, EXPERT_ALIGNED_GATHER
  default ON). Non-expert STAGE flags only help if the expert guard declines.
- **Byte cost**: 0 (env var) or ~2 bytes (change `stage_flag` default).
- **Status**: Not actionable for the scored M5 path.

---

## 6. Key Risks & Constraints

1. **Reglocal binding**: `kSwigluRegLocal` (WN==1) is the binding constraint on
   all tiling experiments. Any WN≠1 variant is DEAD.
2. **M5 vs M4 transfer**: The +17.47% was M4 kernel-level. M5 absolute API data
   (198 vs 201.64 µs) showed variant 5 (with reglocal) fastest. M4 gains do NOT
   reliably transfer to M5 (`_nax` kernels differ across GPU gen per AGENTS.md).
3. **Byte budget**: LRM 1,832B headroom. Total surface 24,608B. The tiling
   changes are ~2 bytes (trivially within budget).
4. **No env vars in ranked runs**: All DARKBLOOM_* defaults are the shipped
   path. Source-default changes are the only way to affect ranked runs.
5. **Geometry flips**: AGENTS.md warns threadgroup geometry can change sign
   across core counts. M5 has 40 GPU cores; M4 Pro has different count.
