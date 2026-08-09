# r99-D — Re-anchor the instrument on the rebased frontier

PR #541, revision `r99-d-rev1`, student maple-tanjiro.
Base `c6c66344d9848d95158edc31f31943aabe4de079` (advisor branch head).
Host: Apple M4 Pro, 48 GiB, macOS 26.5.2. **M4 — not admissible for `_nax`
prefill ranking claims; decode census only.**

---

## 0. Branch re-anchor

The previous assignment (`maple-r98-c-prefill-loader-pipeline`, double-buffer
the routed gather-GEMM weight stage) is superseded. Its submitted-surface edits
were dropped; the research record is preserved in
`research/maple-tanjiro-r98-prefill-loader-pipeline.md` and
`research/r97-logs/`.

```
git reset --hard c6c66344d9848d95158edc31f31943aabe4de079
git diff c6c66344 HEAD -- Sources/ Vendor/ benchmark.json   # empty
senpai/check-editable-budget.sh c6c66344d9848d95158edc31f31943aabe4de079
  -> editable budget OK: current=2983849/3000000 headroom=16151
     growth=0/262144 files=142 (base=142)
```

---

## 1. Correction on the record: the `_nax` surface did NOT move

The HOLD notice stated that the frontier sync "rewrote ... **`fp_quantized_nax.h`/`.cpp`
(±585/584), `steel/gemm/nax.h` (+147), `gemm_nax.cpp` (+147), `quantized.cpp`
(±92)**", and concluded that every line anchor in the r98-C brief was stale.

That is true of commit `7181803` **relative to its own parent**, and false of
the base move that actually affects this branch. Blob identity for
`fp_quantized_nax.h`:

| rev | blob |
|---|---|
| `e510bb3d` (old base) | `8b1738272ae4` |
| `7181803^` (sync branch parent) | `0fdf46fea5ae` |
| `7181803` (sync commit) | `8b1738272ae4` |
| `c3a85ac`, `4f3108c`, `c6c66344` | `8b1738272ae4` |

The frontier-sync branch was cut from an older point, so its diff restored these
files *from* an older state *to* the organizer's version — which our advisor
branch already carried verbatim at `e510bb3d`.

Verified for all four files by blob hash: `fp_quantized_nax.h`,
`mlx-generated/fp_quantized_nax.cpp`, `quantized.cpp`,
`kernels/steel/gemm/nax.h` are **IDENTICAL** at `e510bb3d` and `c6c66344`.

Net submitted-surface diff `e510bb3d -> c6c66344` (13 files, +4697/-2875):

```
Sources/MLXFastModel/LagunaConfig.swift                 7 +-
Sources/MLXFastModel/LagunaRuntimeLayers.swift       2597 ----   (deleted)
Sources/MLXFastModel/LagunaRuntimeModel.swift        2928 ++++
Sources/MLXFastTransform/AffineMetadataCoding.swift   438 +++    (new)
Sources/MLXFastTransform/TiedHeadMetadataCoding.swift  401 +++   (new)
Sources/MLXFastTransform/Transform.swift               64 +-
Vendor/.../MLXLMCommon/BaseConfiguration.swift         37 +-
Vendor/.../MLXLMCommon/BatchKVCache.swift             109 +-
Vendor/.../MLXLMCommon/CompilableKVCache.swift         57 +-
Vendor/.../MLXLMCommon/CompilableRotatingKVCache.swift 61 +-
Vendor/.../MLXLMCommon/CompiledDecode.swift            85 +-
Vendor/.../MLXLMCommon/Evaluate.swift                 534 +-
Vendor/.../MLXLMCommon/KVCache.swift                  254 +-
```

**Zero bytes of `Vendor/mlx-swift` MLX kernel or dispatch source changed.** The
base move is entirely a Laguna-runtime + `MLXLMCommon` cache/decode-stack move.

Consequences:

1. Rule 68's `_nax` geometry premise **survives** the frontier move; it was
   derived on kernel sources that are byte-identical to the ones now shipping.
2. The r98-C line anchors into `fp_quantized_nax.h` are **not stale**.
3. The `[Wk;Wv]`-only SLC/read-overlap discriminator does **not** need
   re-derivation on new geometry.
4. Prefill-side audit numbers (loader 50 LSU vs ~40 compute, loader ≈68 % of LSU
   traffic, routed gather-QMM ≈54 % of prefill) rest on unchanged kernel source
   and unchanged host tiling; they are only as stale as the Laguna-side dispatch
   pattern that feeds them.
5. Anything **decode-side** is genuinely suspect, because that is exactly where
   all 4697 changed lines live. Part 1 is therefore aimed at the right axis.

---

## 2. Verified: the sliding-attention ring lost half its load pipeline

Advisor's audit confirmed independently.

| | old `e510bb3d` | new `c6c66344` |
|---|---|---|
| block anchor | `LagunaRuntimeModel.swift:1508-2027` | `:1416-1864` |
| main loop | `for (; i + 3 * BN < N; i += 4 * BN)` | `for (; i + BN < N; i += 2 * BN)` |
| K/V staging registers | `U pipe_kc[4]; U pipe_kd[4];` | `pair_planes = 2` |
| KV blocks in flight | **4** | **2** |

Kernel name literal `laguna_sliding_fused_attn_ring_v1` is unchanged
(`:1417`), so the census label is directly comparable across bases.

Under the round-98 thesis (decode/attn load streams are latency-bound and want
bytes in flight), halving the in-flight KV depth should make this kernel
**slower**, not faster.

---

## 3. Preregistration (committed before any result was read)

### 3.1 Instrument

Local-only GPUPROF dispatch-timing hook
(`research/nezuko-pr158-gpuprof-hook.patch`, `device.{cpp,h}`), built to
`.build-worker`, driven by `research/decode_probe.py`. Identical instrument and
identical driver to the old-base census (PR #488) that produced the reference
column, so the comparison is instrument-controlled.

```
swift build -c release --force-resolved-versions \
    --scratch-path .build-worker --product mlxfast-runtime-worker
env DARKBLOOM_GPU_PROFILE=1 DARKBLOOM_GPU_PROFILE_SPLIT=1 \
    python3 research/decode_probe.py --steps 80 --profile --profile-top 250
```

The hook is committed as an explicitly labelled TEMP INSTRUMENT commit only
because `run_job` refuses a dirty worktree; it is reverted before Part 3, and
the final head carries an empty submitted-surface diff against the base.

**Rule 43 applies:** `SPLIT=1` serialises command buffers, so per-kernel
attribution from a `SPLIT=1` census is valid but its **total** is inflated
(old base: 8528.3 µs/step `SPLIT=1` vs 7993.1 µs/step busy pool). Part 2's
wall−busy gap therefore comes from a **`SPLIT=0`** run, never from `SPLIT=1`.

### 3.2 Noise floor

Three `SPLIT=1` censuses in one session before any interpretation. Per-kernel
pooled σ from the old rig is 3.51 µs/step (this rig 3.34). The measured spread
of the three runs is the floor actually used; no threshold is fixed before that
spread is in hand (standing rule from fern's PR #543).

### 3.3 The prediction under test

Advisor's preregistered prediction: the sliding fused-attention pool must have
**changed** from its old-base value of **636.0 µs/step** (21.20 µs × 30 layers,
`SPLIT=1`, M4).

Declared decision rule, fixed now:

| outcome | reading |
|---|---|
| pool > 636.0 by more than 3σ | ring-depth regression is real and costly; quantify headroom for Frieren's #539 restoration |
| pool < 636.0 by more than 3σ | the 2-deep rewrite is *faster*; #539 is chasing negative headroom |
| \|pool − 636.0\| ≤ 3σ | one of: (a) advisor's audit wrong, (b) the 4-deep ring never mattered, (c) the instrument is not resolving this kernel — **and the assignment's stopping rule fires: report and do not spend the receipt** |

Discriminating (c) from (a)/(b) if the null occurs: the census reports
dispatch counts per label. If `laguna_sliding_fused_attn_ring_v1` appears with
30 calls/step and a plausible µs/call, the instrument *is* resolving it and (c)
is excluded — leaving (a) or (b), which the verified source diff in §2 already
makes hard to sustain for (a).

I am not tuning the instrument to agree with the audit. The §2 source diff was
established by blob/AST inspection *before* the first census and is reported
separately from the timing.

### 3.4 Part 2 observable

`wall − Σ(kernel busy)` per steady decode step, `SPLIT=0`, M4. Old-base
reference **249 µs/step**. Reported as a decomposition (wall, busy sum, gap,
gap %), never wall alone.

---

## 4. Results

### 4.1 Part 1 — the prediction is CONFIRMED

Three `SPLIT=1` censuses on unmodified `c6c66344`, M4, 80 steps,
`cbs=406 dispatches=406`, `0 divergences` each:

| rep | wall ms/step | busy ms/step | gap ms/step | gap % |
|---|---|---|---|---|
| 1 (warm-up outlier) | 9.905 | 8.629 | 1.278 | 12.9 |
| 2 | 9.772 | 8.545 | 1.228 | 12.6 |
| 3 | 9.765 | 8.543 | 1.222 | 12.5 |

Rep 1 is discarded as the warm-up outlier by the preregistered rule; analysis
uses the reps 2–3 mean. Logs: `research/r99d-logs/`.

Common-mode normalization (`research/tanjiro-r99d-commonmode.py`): reference
set n=18 kernels at ≥50 µs/step on the old base, common mode **×0.99950**,
robust σ **0.491 %** of each kernel's own time. Pool total moved
8528.3 → 8544.2 µs/step; the raw **+15.9 µs/step** decomposes into common mode
**−4.3** and per-kernel excess **+20.17 µs/step**.

| kernel | calls/step | old µs | new µs | excess µs | excess % | z |
|---|---|---|---|---|---|---|
| `sliding_fused_attn_ring_v1` | 30 | 636.0 | 648.4 | **+12.67** | +1.99 | 4.0 |
| `full_fused_attn_grow_v1` | 10 | 229.7 | 239.6 | **+9.97** | +4.34 | 8.5 |
| `residual_rms_router_…keys_v1` (was `…_pf1`) | 39 | 312.8 | 319.5 | **+6.91** | +2.21 | 4.4 |
| `gate_sp_h64_v1` | 30 | 248.0 | 241.8 | −6.03 | −2.43 | −5.1 |
| `shared_nvfp4_swiglu_qmv_rows1_halved_bf16_v1` | 39 | 287.1 | 285.6 | −1.41 | −0.49 | −1.0 |
| `gate_sp_h48_v1` | 10 | 80.2 | 79.2 | −0.91 | −1.13 | −2.3 |
| `argmax_bfloat16` | 1 | 9.0 | 9.6 | +0.55 | +6.16 | 11.8 |

`sliding_fused_attn_ring_v1` moved **off 636.0 by +12.67 µs/step, z = 4.0**.
The preregistered prediction **holds**, in the predicted direction and with the
predicted rough magnitude. The stopping rule does not fire.

The instrument resolved the kernel at 30 calls/step and 21.6 µs/call, so
branch **(c)** of the §3.3 decision table ("the instrument is not resolving
this kernel") is excluded on its own preregistered criterion.

Score translation at the M4→M5 wall ratio (M4 8223 µs/step → M5 4893.7
µs/step, 0.015280 %/µs·step): sliding **0.1152 %**, grow **0.0906 %**, router
**0.0628 %**; all excess **0.1835 %**.

### 4.2 Provenance correction — the 636.0 anchor is *older* than r96-a

Chasing the anchor before interpreting the delta changed the conclusion. The
636.0 number traces to `research/maple-nezuko-r92-barrier-hoist-generalization.md:81`
and was re-used verbatim by the r94 ledger, whose base was **`d549d318`** —
**not** `e510bb3d`. The census "old" column is therefore a `d549d318`-era
number, one frontier older than I had assumed in §2.

Sliding-ring MSL source, extracted from the kernel name line to the next
`MLXFast.metalKernel(` and hashed:

| revision | lines | sha (12) | main loop |
|---|---|---|---|
| `9d9da08^` ≡ `d549d318` | 431 | `fad5dc8345d7` | **2-deep** (`i + BN < N; i += 2*BN`) |
| `9d9da08` ≡ `e510bb3d` | 519 | `1327d3939ef6` | **4-deep** (`i + 3*BN < N; i += 4*BN`) |
| `c6c66344` (frontier) | 448 | `3542134ce2fe` | **2-deep**, a *third* distinct variant |

`9d9da08` is nezuko's "r96-a R2: 4-deep software pipeline in sliding fused
attention". So the 636.0 baseline is a **pre-r96-a, 2-deep** measurement, and
my +12.67 µs/step excess is measured *against a 2-deep ring*. It therefore
cannot be the cost of losing r96-a — losing r96-a is **invisible** in this
census by construction.

What *is* different between `d549d318`'s ring and the frontier's ring is the
epilogue: `threadgroup float4 outputs4[BN*BDP]` was replaced by
`threadgroup U outputs[4*BN*BDP]` (scalar 4-plane staging). Counting
occurrences of `float4 outputs4`: `e510bb3d` = 2, `74e89d7` = 2,
**`c6c66344` = 0** — dropped from *both* decode attention kernels.

`74e89d7` is "R85-C: re-port the float4 merge epilogue onto the adopted
frontier" and `6ada66c` is "Adopt organizer promoted frontier c5b0a13c". The
pattern is structural: **each organizer frontier adoption drops our Laguna
kernel wins, and they have to be re-ported.**

### 4.3 The four-kernel signature identifies the loss exactly

`research/maple-r85-c-epilogue-result.md` recorded a paired ABBA measurement on
M4 of *applying* the float4 merge epilogue (sign = candidate − base):

| kernel | r85-C base | Δ from applying epilogue | my measured excess |
|---|---|---|---|
| `sliding_fused_attn_ring_v1` | 649.3 | **−20.98** [−22.76, −19.19] | **+12.67** |
| `full_fused_attn_grow_v1` | 254.9 | **−5.55** [−6.74, −4.36] | **+9.97** |
| `gate_sp_h64_v1` (give-back) | 242.9 | **+8.14** [+7.42, +8.86] | **−6.03** |
| `shared_nvfp4_swiglu_qmv_rows1_halved` | 285.9 | +1.55 | −1.41 |
| four-kernel total | 904.2 | **−15.43** | **+15.20** |

**Every sign is reversed, including the counter-intuitive `gate_sp_h64_v1`
give-back**, and the totals agree to 1.5 %. My measured sliding time 648.4 also
sits on top of r85-C's pre-epilogue baseline 649.3 and r88-A's 649.6. This is
as close to a fingerprint as a decode census gets: the frontier is running the
**pre-r85-C** attention epilogue.

### 4.4 Three separable regressions in `c6c66344`

| # | lost work | evidence | price |
|---|---|---|---|
| 1 | r85-C float4 merge epilogue, **both** attention kernels | 4-kernel sign fingerprint above; `float4 outputs4` count 2→0 | my census **+15.20 µs/step**; r85-C's own paired price **+0.2358 %** [+0.1347, +0.3368] |
| 2 | r96-a 4-deep sliding software pipeline | source hash/loop-shape diff, §4.2 | **≈+0.13 %** (r96-a: −3.0 % of kernel at K≤20, ~12σ vs a ±0.25 % null, −8.25 µs/step on `attn_us_per_step_sliding`; runs `uajdq8yu`, `ehbvlnva`, `pe8zt12k`, `skkt1pyq`, `zvycfimy`) — **invisible in my census**, which is anchored pre-r96-a |
| 3 | router weight prefetch: `lagunaResidualRMSNormRouterSource(rowsPerGroup:prefetch:)` with `armSuffix="_pf\(groups)"` collapsed to `(rowsPerGroup:)`; `DARKBLOOM_ROUTER_WEIGHT_PREFETCH` gone | label changed `…_pf1` → `…`, +6.91 µs/step at z=4.4 | **+0.0628 %** |

Re-port prize: **≈0.31 %** using my census plus r96-a, or **≈0.43 %** using
r85-C's own paired price plus r96-a plus the router. Against the **1.0498 %**
deficit to the record this is large but not sufficient alone. All three were
bit-exact by construction when they originally landed, which makes this an
unusually low-risk arm: known code, known correctness history, known price.

### 4.5 Part 2 — the gap is unchanged; the regression is pure GPU busy time

`SPLIT=0`, 3 reps, `0 divergences` each, `cbs=45 dispatches=406`:

| rep | wall ms/step | busy ms/step | gap ms/step | gap % | decode mean ms |
|---|---|---|---|---|---|
| 1 (warm-up) | 8.295 | 7.983 | 0.312 | 3.8 | 8.309 (max 12.819) |
| 2 | 8.223 | 7.975 | 0.247 | 3.0 | 8.237 (max 9.389) |
| 3 | 8.309 | 8.052 | 0.257 | 3.1 | 8.500 (max 23.597, one outlier step) |

**Gap = 252 µs/step (reps 2–3) versus the old-base reference 249 µs/step.**
Within noise: unchanged.

Combined with §4.1, this is the load-bearing structural result of Part 2. The
rebase regression is **entirely inside GPU kernel busy time**; host-side
scheduling, command-buffer construction, and encode overhead did not move.
Any explanation of the frontier's decode deficit that routes through dispatch
or host overhead is excluded.

Two derived quantities worth keeping:

- Per-command-buffer gap: **5.6 µs** at `SPLIT=0` (252/45) versus **3.02 µs**
  at `SPLIT=1` (1225/406). Splitting does not simply multiply the gap.
- `SPLIT=1` inflates measured busy by **(8.545 − 7.975)/(406 − 45) = 1.58 µs
  per extra command buffer**. So `SPLIT=1` *shares* are inflated, but
  *deltas* between two `SPLIT=1` censuses at identical call counts are not —
  which is exactly how §4.1 uses them.

Under `SPLIT=0` the census rows are merged multi-kernel command buffers (labels
joined with `|`), so per-kernel attribution genuinely requires `SPLIT=1`
(Rule 43 confirmed, not assumed).

Nearest comparable old log is `research/nezuko-pr158-gap.log` (wall 8.267/8.220,
busy 8.016/7.985, gap 0.251/0.235, `cbs=45`). Its provenance is PR158-era, not
a matched base, so I cite it only as a family-level consistency reference.

### 4.6 Re-scoring rule 68's surviving explanations

Rule 68 left two live explanations for the decode deficit: SLC capacity
pressure, and lost read-after-read overlap. §4.5 removes host overhead from
contention entirely. §4.3/§4.4 then show that at least
**0.31–0.43 %** of the deficit is not a *phenomenon* at all — it is three
identified pieces of our own code that a frontier adoption silently discarded.
Both rule-68 explanations should be re-scored downward by that amount before
anyone spends a receipt probing them: the residual they need to explain is
**≈0.6–0.7 %**, not 1.05 %.

### 4.7 Part 3 — one official receipt on the unmodified surface

Per the stopping rule (Part 1 changed ⇒ proceed), the receipt is spent on the
**unmodified `c6c66344` submitted surface**: an anchor for the rebased
frontier, a soundness check on operator commit `4f3108c4`, and a free draw
against the record. Result recorded in the reply below.

---

## Reply

**Prediction confirmed.** `sliding_fused_attn_ring_v1` moved off 636.0 to
**648.4 µs/step, +12.67, z = 4.0** (§4.1). The instrument resolved the kernel
at 30 calls/step, so decision-table branch (c) is excluded on its own
preregistered criterion. The stopping rule did not fire and I proceeded to
Part 3.

**But the headline is not the delta — it is what the anchor turned out to
be.** The 636.0 number is a `d549d318`-era measurement, one frontier older
than assumed, and therefore *pre-r96-a and 2-deep* (§4.2). My +12.67 is
measured against a 2-deep ring, so it cannot be the price of losing the 4-deep
pipeline; that loss is real (source-hash verified) but **invisible** in this
census.

What the census did catch is a fingerprint. The four kernels r85-C moved when
it *applied* the float4 merge epilogue are the same four kernels my census
flags, **with every sign reversed — including the counter-intuitive
`gate_sp_h64_v1` give-back — and totals matching to 1.5 %** (−15.43 vs
+15.20 µs/step, §4.3). The frontier is running the pre-r85-C epilogue;
`float4 outputs4` occurrences went 2 → 0 across both decode attention kernels.

So `c6c66344` has **three separable, independently-priced regressions** (§4.4),
all of which are *our own previously-landed, bit-exact work* dropped by an
organizer frontier adoption:

1. r85-C float4 merge epilogue — r85-C's own paired price **+0.2358 %**
   [+0.1347, +0.3368];
2. r96-a 4-deep sliding pipeline — **≈+0.13 %**;
3. router weight prefetch (`…_pf1` → `…`) — **+0.0628 %**.

**Re-port prize ≈0.31 % (conservative, my census + r96-a) to ≈0.43 %
(r85-C's paired price + r96-a + router)** against a **1.0498 %** deficit.
Known code, known correctness history, known price — the lowest-risk
0.3–0.4 % on the board. It does not close the gap alone, and I want to be
explicit about that.

The structural lesson is worth a rule: `74e89d7` ("re-port the float4 merge
epilogue onto the adopted frontier") after `6ada66c` ("adopt organizer
promoted frontier") is the same event happening twice. **Every organizer
frontier adoption should be followed by a mechanical re-port audit of our
Laguna kernel wins**, not by a fresh optimization arm.

**Part 2:** gap is **252 µs/step** vs the old-base reference **249** —
unchanged (§4.5). The rebase regression is **entirely GPU kernel busy time**.
Host-side scheduling and command-buffer overhead are excluded as explanations.
Rule 68's two surviving hypotheses (SLC capacity, lost read-after-read
overlap) now only need to explain **≈0.6–0.7 %**, not 1.05 % (§4.6).

**Part 3:** receipt spent on the unmodified surface; verdicts reported
separately (correctness, both floors, ranking status) as required.

**Follow-ups I did not implement** (not in scope for arm D, which must not
touch the submitted surface):

- A re-port arm restoring all three losses on top of `c6c66344`, measured as
  three separable commits so attribution survives if one no longer pays.
- A standing post-adoption diff check over our Laguna kernel sources, so the
  next frontier adoption reports its own dropped wins instead of needing a
  census to rediscover them.
- Re-measuring the sliding ring against a *matched* `c6c66344` anchor, so the
  r96-a loss becomes visible instead of inferred from source.
