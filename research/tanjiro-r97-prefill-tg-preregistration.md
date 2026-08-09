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

## 12. Amendment 3 — P3 (skinny-N retile) is dead by construction once P2 is live

Registered 2026-08-09, after R1 (`b3b6457f-25b6-40f8-8ebf-a417ba11b1a0`) was
dispatched and **before** its receipt returned, so nothing below is fitted to a
ranked number.

### 12.1 The arithmetic

P3 as specified in the assignment retiles the regular-`_nax` GEMM from
`bn=128, wn=4` to `bn=64, wn=2` under the guard

```
bn == 128 && wn == 4 && N % 64 == 0 && tiles_m >= 4 && tiles_m * tiles_n <= 96
```

Its entire target population is the 78 `wk`/`wv` prefill projections at
`M=512, N=1024, K=2048`, which give `tiles_m * tiles_n = 8 * 8 = 64` and are the
only prefill class under the 96-tile ceiling.

P2 deletes that population. `LagunaRuntimeModel.swift:6143-6182` replaces the
three projections with one GEMM over the row-concatenated bank, so the shape
becomes `M=512, N = queryDim + 2*kvDim = 10240, K=2048`. There is no layer
exclusion: the gate is `if let fusedQKVWeight = _fusedQKVWeight, L > 1`.
`tiles_m * tiles_n` is then `8 * 80 = 640`, six and a half times the ceiling.

Every other prefill class was already excluded, and remains so:

| class after P2 | M | N | K | route | tiles | P3 guard |
|---|---:|---:|---:|---|---:|---|
| fused `[Wq;Wk;Wv]` bank | 512 | 10240 | 2048 | regular-`_nax` | 640 | exclude |
| dense `gate`/`up` | 512 | 8192 | 2048 | regular-`_nax` | 512 | exclude |
| layer-39 `[K;V]` bank | 512 | 2048 | 2048 | regular-`_nax` | 128 | exclude |
| `wo`, `down`, router, `g_proj` | 512 | <=2048 | >=6144 | `_nax` split-K | — | never reached |
| every decode projection | 1 | — | 2048 | regular-`_nax` | — | `tiles_m < 4` |

Both banked shapes stay on the regular path: the `_nax` split-K admission at
`matmul.cpp:1015-1017` needs `K >= 3*max(M,N)` or
`max(M,N) <= 1024 && K > 2*max(M,N)`, and `N=10240` fails both.

**P3 stacked on P2 is a literal no-op on the scored window and on every
off-window prefill.** Submitting it would spend a receipt re-measuring R1.

### 12.2 Why this is not merely a scheduling accident

P3's premise was an occupancy deficit: 64 threadgroups on a 40-core M5 Max is
1.6 waves, with no second wave to hide the tail. P2 fixes that deficit by a
different and strictly better route — it folds those 64 threadgroups into a
640-threadgroup launch (16 waves) instead of splitting them into 128
threadgroups (3.2 waves), and it does so without the +33% A re-read that P3
would have paid.

This makes R1 a joint test of both arms, and the outcome is decisive either way:

- If R1 shows a material prefill gain, the occupancy/serialisation premise is
  real **and P2 has already captured it**; P3 is redundant.
- If R1 shows a null, the premise is false; P3 has nothing left to exploit.

So R1's receipt closes P3 in both branches. **P3 will not be submitted.**

### 12.3 Consequence for §11.2's predicted magnitude

Amendment 2 predicted `-0.16 ms` for R1 from dispatch-launch overhead alone
(78 dispatches x ~2.0 us). Section 12.2 identifies a second mechanism inside
the same change that Amendment 2 did not price: the wk/wv class was the one
prefill class running at 1.6 waves per core, and P2 removes it. If the original
occupancy argument for this class was worth anything, that value now accrues to
R1 rather than to P3.

I am **not** revising the registered `-0.16 ms` point prediction or the §11.3
read-out thresholds — they were registered first and R1 must be scored against
them. I am registering that a result in the first row (`<= -1.0 ms`) is now
explainable by occupancy rather than by dispatch serialisation, and that in
that case the correct follow-up is **not** P3 but a mechanism that improves
the fused bank's own tiling.

### 12.4 Replacement for the third receipt

P3's slot is released. The successor under evaluation is a *tall-M* retile in
the opposite direction (`bm 64 -> 128`, `wm 2 -> 4`), which holds
`SM = bm/wm = 32` and `SN = bn/wn = 32` and therefore the same `gemm_loop`
instantiation, but halves `tiles_m` and hence halves the number of times the
weight matrix is streamed. For the fused bank that is `8 * 10240 * 2048` down to
`4 * 10240 * 2048` BF16 elements per layer, i.e. 335 MB -> 168 MB of B traffic
per layer against a 42 MB per-layer weight that cannot be cache-resident.

That candidate is under independent review at the time of writing and is not
yet registered with a prediction. It will get its own amendment with its own
bars before any receipt is spent on it, or it will be dropped.

## 13. Amendment 4 — P4, swizzle depth for tall-tile prefill GEMMs

Registered 2026-08-09, still **before** the R1 receipt returned. P3's released
slot goes to P4, not to the tall-M retile of §12.4. Reasons for the swap are in
§13.5.

### 13.1 Mechanism

`steel_matmul_regular_axpby_nax` (`matmul.cpp:200-360`) launches the grid

```
tile = 1 << swizzle_log
grid = ( tiles_n * tile , ceil(tiles_m / tile) , batch )
```

and the kernel un-swizzles with (`steel_gemm_fused_nax.h:98-101`)

```
tid_y = (tid.y << swizzle_log) + (tid.x & ((1 << swizzle_log) - 1));
tid_x =  tid.x >> swizzle_log;
```

so `2^swizzle_log` threadgroups that share one B column slab are **adjacent in
dispatch order**. `matmul.cpp:303-305` pins `swizzle_log = 2` on the M5 device
class, so only 4 of them are co-scheduled.

Every surviving regular-`_nax` prefill class has `tiles_m = 512 / 64 = 8`:

| class | M | N | K | count | tiles_m x tiles_n |
|---|---:|---:|---:|---:|---|
| fused `[Wq;Wk;Wv]` bank (sliding) | 512 | 10240 | 2048 | 29 | 8 x 80 |
| fused `[Wq;Wk;Wv]` bank (full) | 512 | 8320 | 2048 | 10 | 8 x 65 |
| layer-39 `[K;V]` bank | 512 | 2048 | 2048 | 1 | 8 x 16 |
| dense-0 `gate`/`up` | 512 | 8192 | 2048 | 2 | 8 x 64 |

With `swizzle_log = 2` the eight row-tiles sharing a B slab are split across two
grid-row passes. The second pass arrives only after all `tiles_n * 4`
threadgroups of the first pass, by which time that layer's ~42 MB of B has
cycled out of cache, so **B is fetched from DRAM twice per layer**. With
`swizzle_log = 3` all eight become adjacent and B is fetched once.

P4 is therefore a pure **scheduling** change: same kernel, same geometry, same
thread count, same dispatch count. It is orthogonal to P2/P2b, which changed
dispatch count and left scheduling alone.

### 13.2 Bit-exactness (proof, not heuristic)

For `tiles_m = 8` and `2^swizzle_log = 8`, the map
`(tid.x, tid.y) -> (tid_x, tid_y)` is a bijection onto
`[0, tiles_n) x [0, tiles_m)`, exactly as it is for `swizzle_log = 2`. Each
output tile is still computed by exactly one threadgroup. `swizzle_log` enters
**only** the tile-to-threadgroup assignment: `c_row = tid_y * BM`,
`c_col = tid_x * BN` (`steel_gemm_fused_nax.h:137-138`), after which every
threadgroup runs the identical `gemm_loop<T, SM=32, SN=32, SK=32, BK=256, ...>`
(`steel_gemm_fused_nax.h:150-155, 183-195`) over the same A and B pointers.

`gemm_k_iterations_aligned = K / bk` (`matmul.cpp:320`) and the `align_M` /
`align_N` / `align_K` function constants are all untouched, because `bm`, `bn`
and `bk` are untouched. The kernel's out-of-range guard
(`steel_gemm_fused_nax.h:103-105`) is unchanged and still correct.

Consequently P4 changes **no output bit**, on any shape, and carries no
correctness or floor risk. Its only possible effect is wall time.

### 13.3 Guard

Inside the existing `devc == 's' || devc == 'c' || devc == 'd'` branch:

```cpp
swizzle_log = (tm >= 8 && (tm % 8) == 0) ? 3 : 2;
```

`tm % 8 == 0` keeps the mapping an exact bijection and avoids launching dead
threadgroups. Every decode projection has `tm = 1` and is excluded, so decode —
which carries 75 % of the score — is provably untouched. The guard is expressed
purely in terms of GEMM shape, contains no prompt, token, layer or fixture
constant, and would apply to any model with these shapes.

### 13.4 Prediction and read-out bars

B traffic saved is about 42 MB per layer for the fused bank, roughly 1.6 GB per
prefill over 39 layers. At ~500 GB/s that is ~3.3 ms **if fully exposed**.
It is almost certainly not fully exposed: the fused-bank GEMM has arithmetic
intensity `2*512*10240*2048 FLOP / 84 MB ~= 256 FLOP/byte`, so it is strongly
compute-bound and most DRAM latency is already overlapped with compute.

Registered point prediction: **-0.4 ms prefill (~ +0.15 % score)**, 80 %
interval `[-1.5, +0.2] ms`. A null is the single most likely outcome.

| observed M5 prefill delta (R2 minus R1) | reading | consequence |
|---|---|---|
| <= -1.0 ms | B re-fetch was a real exposed cost | promote; consider `swizzle_log = 4` and revisit §12.4 tall-M |
| -0.3 to -1.0 ms | partially exposed | promote, but the family is nearly exhausted |
| -0.3 to +0.2 ms | GEMM is compute-bound as modelled | close the prefill memory-traffic family; report negative |
| > +0.2 ms | scheduling regression (A-side thrash) | revert, report negative |

Because P4 is bit-exact, R2 = P2 + P2b + P4 and `R2 - R1` isolates P4 exactly.
No receipt is spent on P4 until R1 has returned.

### 13.5 Why P4 rather than the §12.4 tall-M retile

Independent review corrected §12.4's traffic model. The `_nax` kernel stages
**nothing** in threadgroup memory: each simdgroup loads its own A and B
fragments straight from device memory (`gemm_nax.h:56-93`), and the
simdgroup-to-tile map is `tm = SM * (simd_group_id / WN)`,
`tn = SN * (simd_group_id % WN)` (`steel_gemm_fused_nax.h:157-158`). Issue-level
traffic is therefore geometry-invariant, and §12.4's "335 MB -> 168 MB per
layer" overstated the effect: the only real win from `bm = 128` is the same
DRAM de-duplication of the second swizzle pass that P4 obtains directly.

`bm=128, bn=128, bk=256, wm=4, wn=4` was separately confirmed to be
dispatchable — it is in the AOT instantiation list
(`steel_gemm_fused_nax.metal:28`), and `max_total_threads_per_threadgroup` is
`WM*WN*32 = 512` (`steel_gemm_fused_nax.h:86`) — and bit-exact for the same
`SM/SN/SK` reason as §13.2. It is not wrong; it is simply a more invasive way
(512-thread threadgroups, 16 simdgroups, doubled register-file pressure per
threadgroup) to buy the same de-duplication that a one-line scheduling change
buys. It also contradicts Apple's own deliberate `s/c/d` override to `bm = 64`,
which is a prior against it that P4 does not have to argue with.

The two are substitutes, not complements. They will not be stacked in one
receipt. If P4 lands in the top row of §13.4, the tall-M retile is redundant;
if P4 lands in the third row, the tall-M retile has nothing left to buy either.

### 13.6 Honest scope statement

P4's registered point value is `+0.15 %` against a deficit to the leader of
`1.0498 %`. It cannot close that gap, and neither could P3 or the tall-M
retile. The prefill axis carries 25 % of the score weight and this arm has now
enumerated its remaining mechanisms: dispatch count (P2/P2b, spent on R1),
tile geometry (P3 dead, tall-M a substitute for P4), and scheduling (P4). After
R2 I expect the honest recommendation to be that further ranked progress has to
come from the decode axis, and I will say so in the result rather than
manufacturing a fourth prefill mechanism.

## 14. Amendment 5 — R1 read-out, and a correction to the measuring instrument

Registered **after** the R1 receipt returned and **before** any R2 run. It
records what R1 said, retracts the instrument §11.4 assumed, and re-registers
the R2 bars against the corrected instrument.

### 14.1 R1 receipt

Submission `b3b6457f-25b6-40f8-8ebf-a417ba11b1a0`, commit `a4d7450`,
2026-08-09T11:24Z. Full official metrics recovered with
`research/tanjiro_r97_fetch_submission.py`; the `mlxfast submissions` table
truncates the metrics column at ~75 characters and hides every per-axis number.

| field | value |
|---|---|
| `passed_correctness` | `true` |
| `max_abs_diff` | `0` |
| `checked_steps` | `1344` |
| `passed_decode_speedup_floor` | `true` |
| `passed_prefill_speedup_floor` | `true` |
| `semantic_gpqa_pass_count` | `9 / 9` |
| `gpqa_ttft_pass_count` | `9 / 9` |
| `rejectionReason` | `score did not improve current best` |
| `officialScore` | `2.55810946477023` |
| baseline prefill | `187.976 ms` (`0.0003671414 s/tok`) |
| candidate prefill | `96.797 ms` (`0.00018905583 s/tok`) |
| `prefill_speedup` | `1.941974` |
| baseline decode | `13.8089 ms/tok` |
| candidate decode | `4.92433 ms/tok` |
| `decode_speedup` | `2.804213` |

No gate failed. The rejection is purely ranking.

### 14.2 The instrument §11.4 assumed is not usable

§11.4 registered its bars against "observed M5 prefill delta", implicitly to be
read off the published score or the paired speedup. Both are unusable, for a
reason that is visible only now that the per-axis metrics have been recovered.

Across the 15 scored receipts on this track from 2026-08-08T19:38 to
2026-08-09T11:24, the **same-session baseline** prefill ranges over

```
186.821  186.899  187.030  187.720  187.926  187.976  188.095  188.440
190.001  190.434  190.970  192.850  195.079  195.886  196.395     (ms)
```

a spread of `9.6 ms`, about `5 %`. The **candidate** prefill over the same
receipts is stable to `0.14 ms`. So `prefill_speedup`, and therefore the
published score, is dominated by which baseline draw the session happened to
get, not by the candidate. A score difference of `0.03` between two sessions
carries almost no information about a prefill change of a few tenths of a
millisecond.

The low-noise observable is the **candidate prefill milliseconds** itself.

### 14.3 The control population

Candidate prefill (ms) for the 13 contemporaneous scored receipts on this
account and track, excluding R1 and excluding `25b0b722` (an older frontier at
`97.782 ms`):

```
96.278  96.055  96.070  96.120  96.198  96.193  96.328
96.316  95.870  96.253  96.184  95.953  96.236
```

`mean 96.158`, `sd 0.139`, `n = 13`.

These are different candidates by different students, not byte-identical
replicates. That is a real weakness and it is stated rather than hidden. It is
nevertheless usable here because (a) they branch from the same or an adjacent
promoted frontier, (b) most were decode-directed so their prefill is the
unmodified frontier prefill, and (c) the observed dispersion of `0.139 ms` is
an *upper* bound on pure session noise, since it also contains whatever real
prefill differences those candidates carried. Using an upper bound on the noise
makes the test conservative.

### 14.4 R1 read-out

- Candidate prefill `96.797` vs `96.158 ± 0.139` ⇒ **`+0.639 ms`, `+4.6 σ`.**
- Candidate decode `4.9243` vs `4.9140 ± 0.0176` (n = 10 healthy) ⇒ `+0.59 σ`,
  **unchanged**, which confirms P2 stayed prefill-only exactly as designed.

`+0.639 ms` is in the fourth row of the §11.3 table: `> +0.3 ms` ⇒ *unmodelled
regression ⇒ revert, report negative*. **P2 + P2b are reverted.**

Score attribution, so the size of the finding is not overstated: at the
population prefill the same session would have scored
`2.804213^0.75 · (187.976/96.158)^0.25 = 2.56238`, against the observed
`2.55811`. The prefill regression cost `0.00427` score points, i.e. `−0.166 %`.
The remaining gap to our promoted best `2.58883` is baseline-draw noise, not
candidate regression. R1 is a **−0.17 % regression**, not the `−1.19 %` that a
naive score-to-score comparison suggested.

> **Superseded by Amendment 7 (§16).** The `−0.166 %` above is wrong: it holds
> `decode_speedup` fixed while moving prefill, but the decode timer contains the
> 512-token seed forward, so a prefill change is charged twice. The corrected
> cost of R1's `+0.639 ms` is **`−0.242 %`**. The sign, the magnitude class and
> the revert decision are unchanged.

### 14.5 Why the registered −0.16 ms did not appear

The registered model said fusion removes 78 kernel dispatches at ≈2.0 µs and
changes nothing else, because the tile geometry is provably identical
(640 threadgroups fused, `512 + 64 + 64 = 640` unfused). That part of the model
is not contradicted; something else costs ≈0.8 ms and was not modelled. The
leading candidate is the one the §11.2 hazard audit already established and
§11.4 failed to carry through: `device.cpp:547-548` uses one encoder per
command buffer with `MTL::DispatchTypeConcurrent`, and read-after-read is never
hazard-tracked, so the three baseline `Wq`/`Wk`/`Wv` GEMMs are free to overlap
each other and to overlap their neighbours. Fusing them into a single dispatch
removes overlap opportunity at the dispatch boundary rather than removing
serial work. On M4 this was invisible because M4 routes `Wk`/`Wv` to split-K,
so P2 there deletes real dispatches and a reduction, which is the whole of the
`−11.2 ms` M4 result. This is recorded as the most plausible explanation, not
as a demonstrated one; no receipt will be spent to confirm it.

### 14.6 R2 and its re-registered bars

R2 carries **base + P4 only**. `LagunaRuntimeModel.swift` is restored to the
exact base revision `b78e7cdb`, so the whole diff against base is the six lines
of `matmul.cpp`. The receipt therefore does double duty: it measures P4, and it
confirms the revert by returning candidate prefill to the population mean.

Read-out, registered now, against **candidate prefill ms** and the
`96.158 ± 0.139` population — not against the score:

| candidate prefill | reading | consequence |
|---|---|---|
| ≤ 95.75 ms (≤ −0.4 ms, ≥ 3 σ) | B-slab reuse real | promote; test swizzle_log 4 on R3 |
| 95.75 – 96.02 ms (−0.4 to −0.14 ms) | weak effect | keep, but the family is nearly exhausted |
| 96.02 – 96.30 ms (within ±1 σ) | null; also confirms the P2 revert | close the prefill arm, report negative, recommend decode |
| ≥ 96.30 ms (> +1 σ) | P4 harmful, or revert incomplete | revert P4, report negative |

Registered point prediction for P4 is unchanged from §13.4: **−0.4 ms**, 80 %
interval `[−1.5, +0.2]`, **null called as the single most likely outcome**. The
one thing that improved is the power of the test: against `sd = 0.139 ms` a
`−0.4 ms` effect is a `3 σ` signal, so R2 can actually resolve the registered
prediction, which the score-based instrument of §11.4 could not have done.

Receipt budget after R2: 4 remaining, and §13.6's expectation stands — if R2 is
null I will recommend moving to the decode axis rather than inventing a fourth
prefill mechanism.


---

## 15. Amendment 6 — control-population audit, corrected R1 statistics

Registered before the R2 run. An independent frontier review criticised the
`+4.6 σ` headline of §14 as an overstatement and asked for three specific
audits of the control population. All three are now done in
`research/tanjiro_r97_control_audit.py`. The R2 bars of §14.6 are **unchanged**;
this amendment only corrects how R1 is reported.

### 15.1 The `4.6 σ` headline was wrong and is withdrawn

`+0.639 / 0.139 = 4.6` treats the population sd as if it were the sd of the
R1 estimate. R1 is a *single new observation*, so the correct denominator is the
prediction standard error `s·sqrt(1 + 1/n) = 0.1441`, giving:

- prediction-`t` = **4.43** on 12 dof (not 4.6 σ),
- effect **+0.639 ms**, 95 % CI **[+0.325, +0.953] ms**,
- 95 % prediction interval for one healthy new receipt **[95.844, 96.472] ms**;
  R1 at 96.797 is outside it.

A distribution-free reading that assumes nothing about the shape of the
population — R1 being the largest of 14 exchangeable draws — bounds the p-value
only at `1/14 = 0.071`. I therefore report the effect as **+0.64 ms
[+0.33, +0.95], prediction-t 4.43, distribution-free p ≤ 0.07**. The §11.3
consequence (`> +0.3 ms` ⇒ revert, report negative) is triggered under both the
parametric and the distribution-free reading, so the decision does not depend
on the choice.

### 15.2 Chronological drift is not the explanation

R1 ran 10.43 h after the first control and 4.2 h after the last, so a drifting
host was a live confound. OLS of candidate prefill on time gives slope
**−0.0059 ms/h** (se 0.0218, `t = −0.27`, 11 dof): no drift, and what little
there is points the *wrong way*. Extrapolating the fitted line to R1's timestamp
predicts 96.117 ms, i.e. drift accounts for **−0.041 ms** of a **+0.639 ms**
effect. Re-testing R1 against the regression line with its wider prediction
error still gives **t = +3.18**. Drift is excluded.

### 15.3 Do the controls really share unmodified prefill code?

I cannot read other students' branches, so this is tested by an internal
signature instead. Four of the 13 controls have visibly broken decode
(5.08–6.78 ms/token versus a 4.914 ms/token frontier). If their edits had
touched prefill, their prefill would scatter. It does not:

| subgroup | n | mean candidate prefill | distance below R1 |
|---|---|---|---|
| decode-damaged (> 5.0 ms/tok) | 4 | 96.087 ms | 0.710 ms |
| decode-healthy (≤ 5.0 ms/tok) | 9 | 96.189 ms | 0.608 ms |

Both subgroups are tight and both sit far below R1. Arms that demonstrably
changed decode left prefill in the same narrow cluster, which is the signature
expected when the prefill path is untouched. This does not prove byte-identical
prefill code, and it remains the weakest link in the inference.

### 15.4 Bookkeeping reconciliation

15 scored receipts exist on this account between the promoted frontier and R1.
They decompose as **13 controls + `25b0b722` + R1**. `25b0b722` (2026-08-08T19:38,
candidate prefill 97.782 ms) is excluded because it predates the promoted
frontier `3e165fa` and sits 1.6 ms — 11 sd — off the cluster, i.e. it is a
different prefill code base, not an outlier draw. The 15-value baseline list of
§14.2 is the same 15 receipts read on the baseline axis. No receipt is
double-counted or silently dropped.

### 15.5 Scope: why R2 is still P4 and not a decode candidate

The review's strongest recommendation was to spend R2 on a decode candidate,
since decode carries 75 % of the weight and closing the 1.05 % gap to the leader
needs either **−4.0 ms** of prefill or **−0.069 ms/token** of decode, whereas
P4's registered −0.4 ms is worth only about **+0.10 %** (Amendment 7 corrects
this to **+0.151 %**; the conclusion is unchanged). I accept the arithmetic
and I am *not* acting on the recommendation, because this assignment
(`maple-r97-b-prefill-tg-count`) is the prefill arm and no decode candidate is
implemented on this branch. Inventing one here would be a different experiment.
The recommendation is recorded as the arm's primary follow-up for the advisor.

Two further review points are accepted and recorded rather than acted on:

- The confound that R2 cannot separate "revert restored base" from "P4 exactly
  cancels a revert error" is real but not practical: the revert is a literal
  `git checkout` of the base file and `git diff` against the base now shows
  **only** the 6 lines of `matmul.cpp`, so base behaviour is restored by
  construction, not by measurement.
- P4's ceiling is capped by arithmetic intensity. The Wq GEMM is compute-bound
  (AI ≈ 221 FLOP/B against a machine balance of 55–125), so halving B traffic
  mostly hides under compute and −0.4 ms can only arrive through second-order
  cache/DVFS effects. This is why null was, and remains, the registered most
  likely outcome.


---

## 16. Amendment 7 — prefill is priced twice; every score figure restated

Registered while R2 was in flight, in response to advisor feedback
`r97-b-fb1-prefill-price-confirmed` (PR #527 comment `5231447437`,
2026-08-09T12:11:02Z), which reports that merged PR #531 established that the
512-token seed forward runs **inside** the decode timer. I accept the
correction. Every prefill-to-score conversion earlier in this document is wrong
in the same direction and is restated here. **No measurement changes; only the
exchange rate does.**

### 16.1 Independent source confirmation

I did not take this on assertion. In
`Sources/MLXFastTrustedHarness/LagunaRuntimeBenchmark.swift` the serial decode
phase is:

| line | statement |
|---|---|
| 966 | `let decodePhaseStart = DispatchTime.now().uptimeNanoseconds` |
| 967 | prints the literal `includes_seed_prefill=true` |
| 968 | `try worker.beginDecode(seedTokens:)` — the 512-token seed forward |
| 1010 | `secondsSince(decodePhaseStart)` — the timer closes *after* the seed |

The parallel region repeats the pattern at lines 877/878/932. The seed forward
is unambiguously inside the decode clock. **Confirmed.**

### 16.2 The corrected model

Let `CP` be candidate prefill seconds per *token* and `CD` candidate decode
seconds per *step*. Because the seed is 512 tokens and the timed decode is 128
steps, the seed contributes `512·CP/128 = 4·CP` to every reported decode step:

```
CD = 4·CP + Tbar          (Tbar = the true per-step decode cost)
f  = 4·CP / CD            (the share of the decode metric that is prefill)
d log score = -(0.25 + 0.75·f)·u - 0.75·(1-f)·w
```

where `u` is fractional prefill change and `w` fractional change in `Tbar`. The
forward-pass exponent is therefore `0.25 + 0.75·f`, **not** `0.25`.

**Standing rule, adopted from the advisor and applied from here on: `f` is
recomputed from the candidate's own score JSON every time. A stored `f` is never
carried across receipts.** In particular the `0.330` exponent in
`research/frieren-r97-rule58-result.md` must not be reused — it is derived from
the pinned-baseline `f`, not a candidate `f`.

### 16.3 R1 re-priced from its own JSON

| quantity | value | source |
|---|---|---|
| candidate prefill wall | 96.797 ms | R1 `officialMetrics` |
| `CP` | 189.057 µs/token | 96.797 / 512 |
| `CD` | 4924.33 µs/step | R1 `officialMetrics` |
| `f` | **0.153570** | `4·CP/CD` |
| forward exponent `0.25 + 0.75f` | **0.365178** | — |
| price of 1 ms of prefill | **0.3773 %** | `0.365178 / 96.797` |

Exact counterfactual, moving prefill to the control mean 96.158 ms **and**
propagating the mandatory `4·ΔCP = +4.99 µs/step` out of decode
(`CD → 4919.34 µs/step`):

```
score(counterfactual) = 2.564298      score(observed) = 2.558109
cost of the +0.639 ms regression = -0.242 %
```

The linear price agrees: `0.639 × 0.3773 = 0.241 %`. The earlier naive
counterfactual, which held `decode_speedup` fixed, gives `2.562349` and the
wrong answer `−0.166 %`.

### 16.4 Everything restated

| figure | old (wrong) | corrected |
|---|---|---|
| cost of R1's `+0.639 ms` | −0.166 % | **−0.242 %** |
| value of P4's registered −0.4 ms | +0.10 % | **+0.151 %** |
| prefill needed to close the 1.05 % leader gap | ≈ −4.0 ms | **≈ −2.8 ms** |

The revert decision (§11.3, `> +0.3 ms`) is stated in **milliseconds**, so no
GO/NO-GO bar in this document moves. Only the reported score consequences do.
The correction makes the regression *worse*, so it strictly reinforces the
NO-GO.

### 16.5 What this does to the decode read-out — and its honest limits

A `+0.639 ms` prefill regression **necessarily** injects
`0.639 ms / 128 steps = +4.99 µs/step` into the decode metric. R1's decode
sat `+10.3 µs/step` above the healthy control mean, with a prediction se of
about `18.5 µs`. The injected term is therefore fully consistent with the
observation, and §14.4's claim that "decode is unchanged, so P2 stayed
prefill-only" is *weaker* than stated: part of the observed decode excess is
mechanically the prefill regression, not evidence of gating.

I am explicit that **this arm has no power to test rule 58.** The injected
signal is 0.27 of the decode prediction sd, and the healthy controls span only
0.26 ms of prefill wall (≈ 2.0 µs/step of induced decode), so no regression of
decode on prefill within this population could resolve a slope of 4 with any
useful error bar. I report the relationship as *consistent with, and unable to
test*, and I accept the advisor's M4 measurement as the evidence.

### 16.6 Direction of travel

The advisor also notes that `f` grows as decode improves: at `CD = 4000 µs/step`
the forward exponent rises to about `0.391`. Prefill work therefore
**appreciates** as the decode axis is optimised. This does not rescue P2 — P2 is
a measured regression, not a small win — but it does mean a future prefill win
should be re-priced at the `f` of the receipt that carries it, not at today's.

