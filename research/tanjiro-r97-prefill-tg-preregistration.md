# R97-B preregistration — prefill threadgroup-count remedies for the M5 `steel_gemm_bf16` pool

Assignment `maple-r97-b-prefill-tg-count`, revision `r97-b-rev1`, PR #527,
branch `maple-tanjiro/r97-prefill-tg-count`, base
`codex/mlxfast-maple-20260804-advisor` @ `b78e7cdb80b5ae5f1cb1fdd39803322fb283ae5e`.

This document is committed **before** any timed run. Everything below —
reachability, kernel-selection analysis, go/no-go bars, receipt plan, and the
corrections to the assignment's cited prior art — is registered in advance.

Host for all local work: Apple **M4 Pro**, 20 GPU cores, 48 GiB, macOS 26.5.2
(25F84), Apple GPU generation **16**. This host **never selects `_nax`**
(proof in §3). Local prefill timing is therefore *not* evidence for the ranked
M5; local decode timing and local dispatch counts are.

---

## 1. What this arm attacks

`research/maple-tanjiro-nonmoe-prefill-census.md` puts the M5 prefill
`steel_gemm_bf16` pool at **A = 37.93 ms** of the **S = 97.895 ms** prefill
window (38.7%), against a modelled steel floor of 25.63 ms — i.e. **12.30 ms
of headroom = 4.61% of score**. Our current deficit to the top of the board is
**1.0498%** (best on board 2.61650354381456; our best normalised 2.589321,
receipt `7ce1262d`). At **0.373% score per ms of prefill** we need roughly
**2.8 ms** of prefill to take the lead outright.

Two independent mechanisms are registered here, to be measured **in sequence,
never summed**:

- **P2 — fused QKV bank.** Turn on the row-concatenated `[Wq;Wk;Wv]` BF16
  weight so the three prefill projections become one GEMM.
- **P3 — skinny-N NAX tile.** Reduce the host-side NAX regular tile from
  `bn=128, wn=4` to `bn=64, wn=2`, doubling threadgroup count for the same
  total thread count.

## 2. P2 reachability — verified in this tree, with one undocumented blocker

All line numbers are against `a30aa9381546e2f0cd30ac75bc744ccdab5867c1`.

| step | location | fact |
|---|---|---|
| env parse | `Sources/MLXFastModel/LagunaRuntimeModel.swift:113-114` | `DARKBLOOM_FUSED_QKV`, compared `== "1"` ⇒ **default OFF** |
| doc | `…:108` | comment describing the bank |
| build | `…:5778` `prepareFusedQKVWeight()` | concatenates `[Wq;Wk;Wv]` along rows |
| storage | `…:5625` decl, `…:5796` assignment | `_fusedQKVWeight` |
| prep call | `…:9257` inside `prepareFusedRuntimeWeights()` | runs off the hot path |
| **consumption** | `…:6069` | `if let fusedQKVWeight = _fusedQKVWeight, L > 1 { let qkv = matmul(normalizedInput, fusedQKVWeight.T) … }` |
| slices | `…:6079-6084` | three last-axis slices of `[512, 10240]` back into q/k/v |

The consumption site is guarded on `L > 1`, so the bank is **prefill-only** by
construction. That is exactly the control this arm wants.

**Blocker (undocumented in the assignment and in the prior-art docs).** The
*shipping* decode-side fusion at `…:5897` is guarded on
`_fusedQKVWeight == nil`. Merely flipping the env default therefore **disables
the INT8 fused norm+QKV decode path**, dropping decode to stock BF16 separate
projections. That is the mechanism behind the previously measured
**+39.99% µs/step and `decode_speedup` 0.7705** — a hard failure of the 0.95
decode floor, and the reason a naive env flip is unshippable.

The fix is one line: drop `_fusedQKVWeight == nil` from the `:5897` guard. It
is safe because the two consumers are mutually exclusive by shape — `:6069`
requires `L > 1`, the decode block requires `L == 1`. **Registered claim:**
with that guard fix, decode is bit-identical and time-neutral versus base.
Decode behaviour is host-independent, so this claim is falsifiable **on M4**
and I will test it locally before spending any receipt.

Do not confuse `DARKBLOOM_FUSED_QKV` with `DARKBLOOM_FUSED_QKV_PROJECTION`
(`…:338`, `!= "0"`, default **ON**, already shipping). They are different
switches.

## 3. Static `_nax` kernel-selection check for the fused shape — PASSES

This is the pre-clearance the assignment asks for, and it is terminal: it can
be published without any timed run.

Dispatch chain: Swift `matmul` → `Vendor/mlx-swift/Source/MLX/Ops+Array.swift:990`
→ `…/mlx/mlx/ops.cpp:3264`, where `…/ops.cpp:3310-3311` flattens
`A[1,512,2048]` → `[512,2048]` with `batch_size_out=1` → `Matmul::eval_gpu` →
`steel_matmul` → `steel_matmul_regular_axpby_nax`.

- `use_nax` is decided at `…/backend/metal/matmul.cpp:957-959` from
  `metal::is_nax_available()`.
- `…/backend/metal/device.cpp:913-931`, gate at `:927`:
  `can_use_nax &= gen >= (arch == 'p' ? 18 : 17)`. M4 Pro reports `g16g` ⇒
  **off**; M5 Max reports `g17s` ⇒ **on**. This is the proof that local
  prefill timing cannot speak for the ranked host.
- NAX regular tile selection, `matmul.cpp:227-238`: for `devc == 's'` the tile
  is **bm=64, bn=128, bk=256, wm=2, wn=4**, 256 threads/threadgroup,
  `swizzle_log=2`.

For M=512, K=2048 the per-shape threadgroup counts are:

| N | meaning | TGs = ceil(512/64)·ceil(N/128) | kernel |
|---|---|---|---|
| 1024 | wk, wv (separate) | 8·8 = **64** | `steel_gemm_fused_nax_nn_bfloat16_bfloat16_bm64_bn128_bk256_wm2_wn4` |
| 2048 | wo | 8·16 = **128** | same |
| 6144 | wq, full layers | 8·48 = **384** | same |
| 8192 | fused QKV, full layers | 8·64 = **512** | same |
| 10240 | **fused QKV, sliding layers** | 8·80 = **640** | same |

Every fused shape selects the **identical** kernel as the unfused shapes. No
split-K is introduced: Case-1 (`matmul.cpp:965-966`) requires `!use_nax`, and
Case-2 (`:989-991`) requires `K ≥ 3·max(M,N)`, false here. `align_N` is true
for every N above (all `N % 128 == 0`). Kernels are JIT
(`jit_kernels.cpp:979-1010`), so the N=10240 instantiation is legal and needs
no AOT rebuild.

**Conclusion: the fused N=10240/8192 shapes stay on the `_nax` path on Apple
GPU generation ≥ 17 with no accept-gate divergence.** The assignment's NO-GO
condition "fused shape leaves `_nax` on gen ≥ 17" is therefore already
resolved in the negative, statically, before any receipt is spent. Optional
runtime ground truth is available via `DARKBLOOM_STEEL_TRACE=1`
(`matmul.cpp:99-105`, printed `:358-364`) and will **never** be enabled inside
a timed window.

Model geometry backing the table (`Sources/MLXFastModel/LagunaConfig.swift:9-21`):
hidden 2048, 40 layers, headDim 128, 8 KV heads (kvDim 1024), sliding layers 64
heads (qDim 8192), full layers 48 heads (qDim 6144). Fused N = 10240 sliding,
8192 full.

## 4. Corrections to the cited prior art (registered before measuring)

**(a) `research/maple-tanjiro-pr270-r2-f1-preclearance.md` is inadmissible as
an M5 prefill prediction.** It measured a pure env flip on this same M4 gen-16
host, i.e. the *non*-NAX kernel family. Its headline dispatch delta
(1222→1144, −78) decomposes as `steel_gemm_bf16` −156 (78 split-K GEMMs plus
78 accumulate passes) **and `qk_norm_rope` +78**. The −156 is **entirely an
M4 artefact**: on M4 the wk/wv shape (512, 1024, 2048) takes the split-K path,
whereas the M5 Case-2 test is the exact tie `2048 > 2048` = **false**, so on M5
wk/wv are already regular. Projected M5 dispatch delta ≈ **0**
(−117 fused-away, +39 fused-in, +78 copies). Any M5 gain must come from
somewhere other than dispatch count.

**(b) `research/RESEARCH_IDEAS_steel-gemm-prefill.md:100-137` overstates the
prize by ~2×.** It claims −3 ms central (−4 with `g_proj` rows). The census it
cites predicts Step-0 central **−1.6 ms** and F1 total **−2.2 ms**
(`research/maple-tanjiro-nonmoe-prefill-census.md:543,558`). The two commits
are 39 s apart and the ideas doc was informed only by the r1 census; it also
never accounts for the +78 slice copies. I register the **census** number, not
the ideas-doc number.

**(c) The +78 `qk_norm_rope` dispatches are `g2_copy` general-strided copies**
produced by slicing the `[512, 10240]` fused output on its last axis. On M4
they cost **+1.516 ms/request**. They are not removable by reordering — a
last-axis slice is inherently strided. Removing them requires teaching
`laguna_prefill_{sliding,full}_qk_norm_*` to read the bank directly with a row
offset and stride. That is **out of scope** for this arm and is registered as
the primary follow-up.

**(d) Finding B — the equivalence oracle is structurally blind to this flag.**
`Sources/MLXFastModel/LagunaUpstreamEquivalence.swift:74-90` bypasses
`prepareFusedRuntimeWeights()` (single caller
`Sources/MLXFastModel/LagunaRuntimeWeights.swift:637`), so the oracle never
constructs `_fusedQKVWeight`. An oracle pass is **not** correctness evidence
for P2. Correctness evidence must come from `./benchmark.sh --local-iterate`
token match plus the 64-step drift tripwire, and ultimately from the official
M5 gates. This caveat applies to any teammate testing this flag.

**(e) Standing rules 63, 64, 65 and 66 cited in the assignment do not exist.**
`research/CURRENT_RESEARCH_STATE.md` numbers standing rules **24→59 only**
(highest is rule 59 at `:436`). Rule 58 (`:421-434`) does exist and is used
below. Rule 47 (`:374-377`) gives σ(score) = 0.6172%; rule 48 (`:379-380`)
gives per-submission raw-timing σ ≤ 0.2924% decode and ≤ 0.2573% prefill,
which differ from the σ values quoted in the assignment. I use the
`CURRENT_RESEARCH_STATE.md` values and flag the discrepancy rather than
silently picking one.

## 5. My own mechanism model (registered prediction)

The assignment's framing is "dispatch count". Per §4(a) that framing predicts
**zero** M5 gain. I register a different mechanism, which is what I actually
expect to be tested:

**P2 is a wave-quantisation play, not a dispatch-count play.** A 64-threadgroup
dispatch on a 40-core M5 Max has a makespan of 2 scheduling rounds for 1.6
rounds of work — roughly 20-25% of the machine idle in the tail. The 78 wk/wv
dispatches are exactly this shape. Folding them into the wq dispatch grows it
from 512 to 640 threadgroups, where the same quantisation waste is amortised
over 10× the work.

Central estimate: gross ≈ **−2 ms** if wk/wv occupy ≈ 9 ms of the 37.93 ms
pool, minus ≈ **1.0 ms** of `g2_copy` on M5 (M4 measured 1.516 ms; M5 is
faster) ⇒ **net ≈ −1 to −2 ms**, i.e. **+0.37% to +0.75%** score. This is
below the assignment's suggested 1.5 ms GO bar. I register the bar anyway (see
§6) — the point of the receipt is to discriminate between "≈0, dispatch-count
framing was right", "−1 to −2 ms, wave-quantisation framing is right", and
"−3 ms, the ideas doc was right".

**P3's theoretical basis is weaker than `research/maple-tanjiro-nax-skinny-tile.md`
claims.** Halving `bn` 128→64 also halves `wn` 4→2, so threads/threadgroup
falls 256→128. Total thread count is unchanged, and so is the makespan in
rounds: 64 full threadgroups on 40 cores = 2 rounds; 128 half-threadgroups on
40 cores = 4 rounds of half-size = the same 2 rounds of work. Any P3 gain must
therefore come from *within-core* concurrency (more resident threadgroups per
core hiding more latency), not from load balance. The doc's own roofline note
is the main risk: achieved arithmetic intensity is 43 FLOP/byte, not 293, and
the extra A-matrix re-read costs **+2.4 ms if it misses cache**. P3 is
plausibly a *regression*.

## 6. Registered go/no-go bars

The assignment's suggested bars are adopted **unchanged and unloosened**:

- **P2 GO** — a matched M5 receipt shows **≥ 1.5 ms** prefill gain, correctness
  green, **both** floors passed.
- **P2 NO-GO** — the fused shape leaves `_nax` on gen ≥ 17 (already resolved
  negative in §3), **or** prefill regresses, **or** the prefill move is
  **< 0.3 ms**.
- **P3 GO** — **≥ 1.0 ms** *incremental* prefill gain measured on top of
  whatever state P2 leaves behind.

Between 0.3 ms and 1.5 ms is the registered **inconclusive-but-informative**
band: it does not clear the GO bar, and I will report it as such rather than
promoting it. Because §5 puts my own central estimate inside that band, I
expect the most likely honest outcome of this arm to be a *characterisation*
of the fused-QKV mechanism plus a quantified follow-up, not a promotion.

Hard prerequisite for any P2 receipt, registered now: **local M4 evidence that
the `:5897` guard fix leaves decode time-neutral** (|Δ µs/step| within run
noise) and token-identical. If decode is not neutral on M4, P2 is abandoned
without spending a receipt, because the decode floor is 0.95 and prior art
already recorded 0.7705 for the unfixed flip.

## 7. Receipt plan (budget: 6 M5 receipts, expect to use ≤ 3)

1. **R1 — P2** (env default ON + `:5897` guard fix). Compare against the
   recorded byte-identical base 3-receipt control `f8502e12`, `71586bcf`,
   `f3cda678`.
2. **R2 — P3 on top of P2** if P2 is GO, else P3 against plain base.
3. **R3** — one repeat of whichever of R1/R2 lands closest to a decision
   boundary, to separate a real move from σ.

Receipts are dispatched with `mlxfast submit --model "senpai"` per the campaign
attribution rule, with a note ≥ 5 KiB, and watched via
`senpai/watch-submission.py` under `run_job`.

Every receipt is read as **four independent verdicts**: correctness, decode
floor, prefill floor, ranking. A `rejected` receipt still publishes full
`officialMetrics` and can be a scientific success
(`research/PREFILL_LEDGER_INSTRUMENT.md`); a floor or correctness failure
publishes nothing.

Metric normalisation used throughout (unchanged from prior arms):

```
norm_decode_su  = 0.013890  / decode_spt
norm_prefill_su = 0.0003845 / prefill_spt
ns              = norm_decode_su^0.75 * norm_prefill_su^0.25
S (prefill ms)  = 512000 * prefill_spt
T (decode ms)   = 1000 * decode_spt - S/128      # rule 58: D = 4P + T
```

Rule 58 is why prefill's *effective* weight is **0.365**, not 0.25: the seed
prefill sits inside the decode timer, contributing 4P = 752.2 µs/step = 15.4%
of the decode number.

## 8. W&B logging contract

Runs go to `wandb-applied-ai-team/mlxfast-maple`. Each receipt logs at minimum:

- `prefill_ms_fused_qkv` and/or `prefill_ms_skinny_tile` (the S values above),
- `decode_us_per_step`, `norm_decode_su`, `norm_prefill_su`, `ns`,
- dispatch counts by kernel family for candidate and base,
- `receipt_id`, `correctness`, `decode_floor_pass`, `prefill_floor_pass`,
  `ranking_status` as four separate fields.

## 9. Files this arm may touch

Submitted surface (all inside `benchmark.json` `editablePaths`):

- `Sources/MLXFastModel/LagunaRuntimeModel.swift` (P2: env default + `:5897`
  guard).
- `Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/matmul.cpp` (P3: skinny
  tile, env-gated, default OFF).

Research-only: this file and `research/tanjiro-r97-prefill-tg-result.md`.

Budget at registration time: `current=2899476/3000000, headroom=100524,
growth=0/262144, files=141`. P3 is measured at +1,631 B in
`research/maple-tanjiro-nax-skinny-tile.md`; P2 is a net-zero edit. Both fit.

## 10. Amendment 1 (2026-08-09) — P2b, copy-free fused-QKV consumption

Registered **before** any timed M5 run and before any receipt is spent. This
amendment adds one mechanism and *lowers* my own P2 prediction; it does not
loosen any go/no-go bar in §6.

### 10.1 What §4(c) got wrong

§4(c) listed "the fused bank's Q/K slices may not be row-contiguous" as an
out-of-scope follow-up. Local M4 measurement plus vendor source now show it is
not a follow-up but the dominant cost of P2 as shipped in `64fa273`, large
enough to cancel the whole mechanism.

Proof, in order:

1. `Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/custom_kernel.cpp:39-47`
   — a `MLXFast` custom kernel input declared `ensure_row_contiguous` is passed
   through `copy_gpu(..., CopyType::General, s)` whenever
   `!x.flags().row_contiguous`.
2. All four prefill QK-norm+RoPE kernels declare `ensureRowContiguous: true`.
3. With `DARKBLOOM_FUSED_QKV` on, Q and K reach those kernels as last-axis
   slices of the `[1, L, qDim+2*kvDim]` bank, so both are strided.
4. Therefore the flip adds exactly `2 * 39 = 78` general strided copies per
   request, one per tensor per layer, which is precisely the `+78 qk_norm_rope`
   / `g2_copy` delta already recorded in
   `research/maple-tanjiro-pr270-r2-f1-preclearance.md:140-175`, and **+1.516 ms
   per request** on this M4 host.

### 10.2 Sharpened M5 cost model

The prior art's M4 census showed the split-K subtotal falling 155 to 77 when
the flip is on, i.e. the 78 `wk`/`wv` N=1024 GEMMs disappearing from the
split-K pool. That is an **M4-only** accounting. On M5 the same N=1024, M=512,
K=2048 shape is **regular**, not split-K: the Case-2 predicate needs
`K >= 3*max(M,N)` = 3072 > 2048, and the older `K > 2*max(M,N)` form is the
exact tie `2048 > 2048` = false. The router (N=256) and `g_proj` (N=64/48)
shapes do stay split-K on M5, so this correction is specific to `wk`/`wv`.

Net M5 dispatch delta for P2 alone is therefore **minus 78 regular
64-threadgroup GEMMs, plus 78 `g2_copy`**, i.e. approximately zero dispatches
and approximately zero gain:

| quantity | P2 alone | P2 + P2b |
| --- | --- | --- |
| gross wave-quantisation gain | -1.4 ms | -1.4 ms |
| added strided copies | +1.0 to +1.5 ms | 0 |
| **registered central estimate** | **0 to -0.4 ms** | **-1.4 ms** |
| score at 0.373 %/ms | 0 to 0.15 % | ~0.52 % |

So **P2 alone is predicted to land below the §6 0.3 ms NO-GO bar**. Spending a
receipt on it would buy a null with no diagnostic value beyond what M4 already
shows. P2b is the change that makes the arm worth a receipt.

### 10.3 P2b mechanism

Give the four prefill QK-norm+RoPE kernels an explicit
`[q_row_stride, q_col_offset, k_row_stride, k_col_offset]` layout descriptor
(elements, int32[4]) and hand them the wide bank directly instead of a slice.
Addressing becomes

```
input = raw_queries + t * uint(layout[0]) + uint(layout[1]) + head * head_dim;
input = raw_keys    + t * uint(layout[2]) + uint(layout[3]) + khead * head_dim;
```

With the unfused descriptor `[qDim, 0, kvDim, 0]` these reproduce the previous
addresses element for element, so the unfused path is bit-exact by
construction; with the fused descriptor `[width, 0, width, qDim]` they read the
same values the copy would have produced. The kernels are renamed `_v2` to
`_v3` so no stale compiled variant can be picked up.

The layout array is built once per attention module and cached
(`_prefillQKLayout`). The precheck deliberately validates **shapes only** and
never reads the layout's element values on the hot path, because reading an
`MLXArray` element forces a stream synchronisation every layer.

### 10.4 Registered predictions for P2b

- Prefill dispatch census, `on` arm: **zero** `g2_copy` / general-copy
  dispatches attributable to the QK-norm inputs (78 to 0).
- Local M4 prefill: **-1.3 to -1.7 ms** for `on+P2b` versus `on` alone, and
  **-0.2 to -0.6 ms** versus `off`. M4 prefill wall clock is directional only;
  it is admissible here because P2b removes copies in a kernel family that is
  identical on both architectures, and the claim being tested is a *dispatch
  count*, not an `_nax` tile effect.
- Decode: unchanged. P2b touches only prefill kernels.
- Correctness: `max_abs_diff = 0`, golden hash `b9509697...`, with the flag
  both ON and OFF.

### 10.5 Scope and budget

P2b touches only `Sources/MLXFastModel/LagunaRuntimeModel.swift`, already
declared in §9. Budget after P2b: `current=2903134/3000000, headroom=96866,
growth=3658/262144, files=141` — PASS, and P3's measured +1,631 B still fits.

### 10.6 Amended receipt plan

R1 now carries **P2 + P2b together**, not P2 alone. They are not separable in a
way that is worth a receipt: §10.2 predicts P2 alone is a null, and P2b without
P2 is a no-op because the unfused descriptor reproduces the current addresses
exactly. The separation is instead carried by the local dispatch census, which
attributes the copy removal directly. If R1 lands in the §6
inconclusive-but-informative band, R3 repeats it before anything is promoted.

## 11. Amendment 2 — R1 downgraded from a score bid to a calibration probe

Filed **before** R1 is spent. This amendment retracts the §10.2 M5 point
prediction of `-1.4 ms`. Two independent frontier code audits of the vendored
MLX dispatch layer converged on the same refutation, and I accept it.

### 11.1 Completed local evidence (M4, admissible for what it claims)

4-rep paired ABBA, 8 arms, `research/r97-logs/ab.{1..4}.{off,on}.json`:

| axis | paired delta | sem | reps favouring `on` |
|---|---:|---:|---:|
| prefill | **-11.216 ms** | 2.755 | 4/4 |
| decode | **-0.1504 ms** | 0.0154 | 4/4 |

Correctness green in all 8 arms: `max_abs_diff = 0`, single golden digest
`b9509697c08a`. The effect survives order reversal — `on` wins from first
position (reps 2, 4: `-8.10`, `-12.80`) and from second position (reps 1, 3:
`-5.75`, `-18.21`) — so it is not a warm-up or drift artifact.

Of the decode delta, `-11.216/128 = -0.088 ms` is the mechanical seed-prefill
amortisation implied by `decode_spt = per_step + S/128`. The residual
`-0.063 ms` is **not attributed** and I do not claim it.

### 11.2 Why the M4 magnitude must not be extrapolated to M5

The M4 gain is real but is produced by a mechanism that **does not exist on
M5**. On M4 (gen 16) `Wk`/`Wv` at `(M=512, N=1024, K=2048)` fall into the
non-`_nax` split-K branch (`matmul.cpp:960-966`), so each is two dispatches
plus an internal accumulate barrier; fusion deletes 4 dispatches per layer and
the split-K partial buffers entirely. The census measured exactly this:
`steel_gemm_bf16` 392 -> 236 records, `MIXED:splitk_accum+splitk_nt` 310 -> 154.

On M5 the split-K admission test (`matmul.cpp:988-990`) fails for `Wk`/`Wv` by
an exact tie (`K > 2*max(M,N)` is `2048 > 2048` = false), so all three
projections already take the same regular `_nax` kernel. Fusion there changes
**zero** FLOPs, zero bytes and zero threadgroups: per sliding layer
`512 + 64 + 64 = 640` threadgroups before and `640` after; per full layer
`384 + 64 + 64 = 512` before and `512` after. Only the dispatch count drops.

### 11.3 Retracted prediction and its replacement

The `-1.4 ms` figure assumed `Wq`/`Wk`/`Wv` serialise, so that each dispatch
pays its own partially-empty tail wave. They do not have to. MLX encodes into
one encoder with `MTL::DispatchTypeConcurrent` (`device.cpp:547-548`) and
inserts a barrier only on a real RAW/WAR/WAW hazard (`device.cpp:323-348`,
`363-375`). Read-after-read is never checked, and the barrier resets the
tracked set — so the RMSNorm that writes `A` costs **one** barrier before `Wq`,
after which `Wk` and `Wv` are barrier-free and the hardware is free to overlap
them. The tail-wave term is therefore unsupported by the code.

**Replacement prediction: `-0.16 ms` (range `-0.05` to `-0.30 ms`)**, being
~80 removed dispatches times the M5 per-dispatch encode cost measured in
`research/r93-runs/RESULTS.md` — `1.9823 us` by OLS over the dispatch ladder
(line 110) and `2.3403 us` by the independent Arm B estimate (line 389), giving
`0.159` to `0.187 ms`. It is plausibly smaller still because prefill is
GPU-bound and that cost is CPU-side.

At `0.373 %` score per ms of prefill this is `+0.06 %`, versus `+0.52 %` under
the retracted model. **This is below the §5 GO bar of 1.5 ms and below the
§6 informative floor of 0.3 ms.** I am spending R1 anyway, and reclassifying
it: R1 is no longer a bid to promote P2+P2b, it is a **calibration probe** for
the one unknown that gates this entire arm and every future dispatch-count
experiment on this track.

### 11.4 Registered read-out thresholds for R1

M5 paired prefill sigma is `0.1027 %` (`research/r93-runs/RESULTS.md` line 243,
n=5 null candidate) on a candidate prefill of `187.872 us/token` = `96.19 ms`,
i.e. sigma ~= `0.099 ms`. The predicted `0.16 ms` is therefore only ~`1.6
sigma` on a single receipt: R1 can bound the effect but cannot on its own
resolve it, which is why the thresholds below are coarse.

| observed M5 prefill delta | reading | consequence |
|---|---|---|
| `<= -1.0 ms` (>= ~1 %) | dispatches serialise; tail-wave model was right | promote P2+P2b, and P3's occupancy premise is live |
| `-0.3` to `-1.0 ms` | partial overlap | keep P2+P2b, repeat on R3 per §10.6 before promotion |
| `> -0.3 ms` | overlap confirmed, encode cost hidden | **close the dispatch-count family**; do not spend further receipts on removing dispatches, and treat P3 strictly on its occupancy merits |
| `> +0.3 ms` | unmodelled regression | revert, report negative |

Correctness must be green and both `0.95` floors held in every case; a
correctness failure voids the reading rather than producing one.

### 11.5 Honest statement of expected value

I expect R1 to land in the third row. I am spending the receipt because the
change is bit-exact by construction, carries no floor risk, and is the cleanest
available instrument for the serialisation question — not because I expect it
to move the ranking. If it lands as expected, the correct outcome of this arm
is a **negative result that closes a family**, and I will report it as such.

