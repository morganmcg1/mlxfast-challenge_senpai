# SENPAI Research State

- **2026-08-04 15:10 UTC (round 5 landed in part; round 6 opening)** — advisor
  `meridian`, campaign `mlxfast-maple-20260804`
- **Newest and most load-bearing section is §10**: both decode budgets now close
  with zero residual, three candidates I briefed are dead, and fern's double
  buffering has to be done at `BN=32`. Read it before §4b, which it supersedes
  in part.
- Most recent human research direction: operator authorised the advisor and all
  four students to dispatch official `mlxfast submit` runs from the AWS Macs.
- Base branch: `codex/mlxfast-maple-20260804-advisor`. Round-5 assignments
  branch from `011b64838878962e870a247be5b9adfac3736915`; advisor HEAD has since
  advanced with `research/`-only commits, so there is nothing to rebase.
- Students: `maple-frieren`, `maple-fern`, `maple-tanjiro`, `maple-nezuko`
  (M4 Pro / 48 GB / 20-core GPU). Official host: M5 Max / 128 GB / ~40 cores.
- Goal: maximise `score = decode_speedup^0.75 * prefill_speedup^0.25`.
- Companion documents: `research/FIELD_MECHANISM_MAP.md` (public corpus,
  session-draw distribution, promotion arithmetic),
  `research/nezuko-decode-roofline.md` (byte budget),
  `research/tanjiro-m5-instrument-calibration.md` and
  `research/nezuko-harvest-report.md` (measurement floors).

> **This target has no W&B integration.** Every `runs` array in every result is
> empty by design; the `runs` URLs we do record are mlxfast submission API
> endpoints. Evidence is code, matched local harness pairs, and official M5
> submission metrics.

---

## THE FOUR THINGS TO READ FIRST

### 1. Decode is DRAM-saturated. Score is a byte budget.

Two independent derivations (nezuko `research/nezuko-decode-roofline.md`, plus an
independent audit) agree to within rounding: one steady decode step reads

| stream | MB/token | share |
| --- | ---: | ---: |
| attention q/k/v/o (NVFP4 g16) + per-head `g_proj` (INT8 g32) | 807.7 | 45.0% |
| routed experts, top-8 of 256 (NVFP4 g16) | 552.1 | 30.8% |
| lm_head int5 coarse screening plane | 134.9 | 7.5% |
| layer-0 dense MLP (BF16, intermediate 8192) | 100.7 | 5.6% |
| KV cache (BF16) | 84–89 | 4.7% |
| routers (BF16, 40 × 2048 × 256) | 40.9 | 2.3% |
| embeddings, norms, activations | ~3.6 | 0.2% |
| **total** | **~1794** | |

```
1794 MB / 8.769 ms (M4 --local-iterate step) = 204.6 GB/s
measured M4 Pro DRAM ceiling                 = 260.2 GB/s
                                    ratio    = 78.6%
```

The steady step runs at **78.6% of the measured hardware bandwidth ceiling**.
Nothing else in the campaign is close to its ceiling. Therefore the operative
conversion for the 75%-weighted axis is:

```
score gain  =  0.638 * (MB removed per token) / 1794
```

(0.638 is the measured M5 steady-step elasticity; see finding 2.)

| bytes removed | score gain | promotion odds |
| ---: | ---: | --- |
| 10 MB | 0.36% | — |
| 25 MB | 0.89% | — |
| **33 MB** | **1.17%** | **~1-in-12 shot** |
| **59 MB** | **2.10%** | **~coin flip** |
| 105 MB | 3.73% | promotes |

**Consequences that should govern every assignment:**

- A decode change that does not remove bytes, or does not improve bytes/second,
  is worth approximately nothing. Dispatch counts, host CPU, fusion, occupancy
  and instruction mix have all now been individually falsified (below), and the
  roofline explains why: they were never the binding constraint.
- The remaining decode levers are exactly two: **remove logical bytes** and
  **close the 21.4% efficiency gap** (finding 4).
- Precision is *not* a lever. `AGENTS.md` forbids precision changes outside the
  attention INT8 envelope, and that envelope is **backwards for us**: the
  frontier already runs Q/K/V/O at NVFP4 g16 (0.5625 B/param) where the envelope
  permits group-32 INT8 (1.125 B/param). Adopting the envelope would *add*
  ~802 MB/step. This is a compliance oddity inherited from organizer frontier
  commit `99b974c`, not something we introduced, and it has passed official
  gates repeatedly. Leave it alone and do not treat it as headroom.

### 2. The exact score decomposition, and the M4→M5 transfer factors

```
D = decode_seconds_per_token       P = prefill_seconds_per_token
S = 512 * P                        (seed 512-token forward wall time)
T = D - S/128                      (marginal steady 1-token step)
sigma = (S/128) / D                (seed share of the decode measurement)

d ln score / d ln S = -(0.25 + 0.75 * sigma)
d ln score / d ln T = -0.75 * (1 - sigma)        # the two sum to -1
```

| context | S | T | sigma | elasticity on S | elasticity on T |
| --- | ---: | ---: | ---: | ---: | ---: |
| **official M5 (ours)** | 98.153 ms | 4.3530 ms | 14.98% | **0.362** | **0.638** |
| official M5 (pinned baseline) | 193.544 ms | 12.3206 ms | | | |
| M4 `--local-iterate` | 585.6 ms | 8.769 ms | 33.6% | 0.502 | 0.498 |
| M4 `--local-submit` (1023 steps) | | | ~5.9% | 0.294 | 0.706 |

**Transfer corrections a student must apply to M4 `--local-iterate` numbers:**

- a pure steady-step (T) win is **under-reported by 1.28×**;
- a pure seed-forward (S) win is **over-reported by 1.385×** — multiply forward
  deltas by 0.72 before quoting a score effect.

### 3. Rank by renormalised `ns`, never by `officialScore`. Three receipts.

Canonical normalisation, mandatory for every cross-session comparison:

```
norm_decode_su  = 0.013890  / decode_seconds_per_token
norm_prefill_su = 0.0003845 / prefill_seconds_per_token
ns              = norm_decode_su**0.75 * norm_prefill_su**0.25
draw            = officialScore / ns
```

nezuko's #12 measured, on **byte-identical content across 7 families, 27 dof**:

| quantity | pooled cv | runs to resolve 0.25% at 2σ |
| --- | ---: | ---: |
| renormalised `ns` | **0.489%** → 0.149% | **3** |
| `officialScore` | 0.489% | **31** |

`officialScore` is **3.3× noisier than `ns` on identical content**, because it
carries the session baseline draw. The 2σ floor for comparing two n=3 families
is **0.243% on `ns`**; the advisor's 2× bar for accepting a claim is therefore
**0.61%**.

Per-axis floors (tanjiro #13, 3 byte-identical official runs — superseded for
`ns` by the 27-dof numbers above, still the best we have per-axis):

| axis | floor |
| --- | ---: |
| `ns` | 0.140% |
| candidate `D` | 0.330% |
| candidate `T` | 0.475% |
| candidate `S` | 0.497% |
| `baseline_decode` | 0.493% |
| `baseline_prefill` | **4.829%** (bimodal, 3.61% gap between the two modes) |
| `prefill_speedup` | 4.946% |
| `decode_speedup` | 0.599% |
| conservative score floor | 0.303% |

Rules:

- **Never rank by `officialScore`.** Never use a *ratio's* apparent stability as
  a noise floor: tanjiro's A/B pair alone gave `decode_speedup` 0.010% purely by
  numerator/denominator cancellation luck, a 60× underestimate.
- Report per receipt: submission id, `officialScore`, `ns`, and
  `S = 512000 * prefill_s_per_tok` ms, `T = 1000 * decode_s_per_tok - S/128` ms.
- The service **dedupes byte-identical archives** ("Submission already exists"),
  so our base already ships a free 3-receipt control: `f8502e12`, `71586bcf`,
  `f3cda678`.

### 4. RESOLVED: the decode step is bandwidth-closed with zero unexplained slack

**tanjiro #21, merged 2026-08-04. `research/tanjiro-pr21-result.md`.** This was
the largest unpriced quantity in the campaign. It is now fully decomposed and
almost none of it is recoverable.

```
M4 --local-iterate step                                   8.769 ms
  byte-only roofline, 1794 MB at 260.2 GB/s              -6.895 ms
  ------------------------------------------------------------------
  excess                                                  1.874 ms
    per-dispatch structure                                1.414 ms
      406 x 2.46 us launch ramp (independently derived)     0.999
      cache-served GQA KV re-read                           0.375
    inter-dispatch dead band (nezuko #9 bound was <=0.38)  0.269 ms
    named per-stream shortfalls  <-- THE ONLY RECOVERABLE   0.191 ms
    ACCESS PATTERN                                          0.000 ms
  ------------------------------------------------------------------
  unexplained                                             +0.000 ms
```

**Access pattern is worth exactly zero.** A standalone Metal probe
(`senpai/tools/bandwidth-pattern-probe`, sequential control 262.5 GB/s,
reproducing nezuko's 260.2) found that at equal bytes/dispatch *every* real
pattern reaches **87–94% of the sequential control**: scattered 1.77 MB expert
blocks 94%, scattered 16 KB blocks 92%, KV ring 87–89% **and insensitive to
stride**, code rows at 2048/1024/256 B 90/93/92%. Both surviving suspects
(gathered expert blocks, ring KV) are cleared. 13 of 19 dispatches have gap
exactly zero; every large well-shaped dispatch runs at 100–109% of its modelled
ceiling.

What *does* cost: **bytes per dispatch** (22.9 GB/s at 0.125 MB rising to 262.5
at 64 MB) and **in-flight device bytes per lane** (~32 B to saturate). Empty
dispatch costs 2.46 us at 160 threadgroups, 0.87 us at one.

**Two standing rules from this arm:**

1. *Issued vs unique bytes.* The sliding attention kernel maps 32 threadgroups
   over 64 query heads but only 8 KV heads
   (`LagunaRuntimeModel.swift:1400-1402`), so 4 threadgroups each read the same
   KV head's full 512-slot ring: **8.389 MB issued for 2.097 MB unique.** On
   issued bytes it runs at 381 GB/s (and `full_fused_attn_grow` at 446), i.e.
   1.45x and 1.70x the DRAM ceiling — impossible unless cache-served, therefore
   **no DRAM slack.** Any roofline row measuring above the DRAM ceiling on issued
   bytes is a cache-hit report, not a bandwidth problem. Every new row must state
   which numerator it uses.
2. *`nezuko-decode-roofline.md` Interim 8 is stale and now carries a header
   warning.* Its worst row (`routed_shared_nvfp4_down_residual` 809 us / 42% of
   ceiling) is the pre-#7 `_v4` kernel; Interim 9 ships `_v5` at 22.96 us/call
   and 231.3 GB/s, which HEAD carries. Correcting it validated tanjiro's probe: a
   reads-only ceiling of 212.0 GB/s against the real kernel's 231.3 — within 9%,
   from above, the correct direction for a reads-only bound.

**Re-pricing (supersedes my 10.9%-of-score claim in the #21 brief).** Recoverable
on M5 is **1.4–2.8% of score**, in five small dispatches:

| dispatch | M4 us/step | GB/s | owner |
| --- | ---: | ---: | --- |
| `lmhead_exact_inline_mask_block` | 74 | **6.5 — worst in the step** | nezuko #20 |
| `gate_sp_h64` + `gate_sp_h48` | 83 | ~66 | unassigned |
| `residual_rms_router` | 27 | — | unassigned |
| `dense_gate_up` | 12 | — | unassigned |

The 122 us that is not nezuko's is ~1.39% of the M4 step ≈ **0.89% of score** —
above the 0.61% bar, and it is the cheapest remaining decode work.

**Cross-generation invariance is now explained without access pattern.** M4 runs
at 78.6% of its ceiling and M5 at 78–85% of its (485–530 GB/s) ceiling because
**byte time halves across generations while latency does not.** tanjiro's
latency-like terms (0.460 ms) cover 48–70% of the M5 excess (0.654–0.968 ms), and
the model closes only if the M5 per-dispatch cost is **0.48–1.25 us** — near his
measured 0.87 us single-threadgroup floor rather than 2.46 us. That is a
falsifiable prediction and it is the subject of the next arm (§8).

**Budget reconciliation: tanjiro's launch ramp is 0.699 ms, not 0.999 ms.** His
four terms sum to 1.874 ms, the *whole* wall excess, and all four are GPU-side —
so there is no room in his budget for frieren's 0.29–0.32 ms exposed **host**
head term, which #14 established two independent ways. The soft term is the
launch ramp, because its 2.46 us coefficient comes from an *empty* dispatch,
which has no memory traffic to overlap the threadgroup ramp against. In situ the
coefficient must be lower:

```
GPU-side terms must total  1.874 - 0.300 = 1.574 ms
launch ramp                0.999 - 0.300 = 0.699 ms
in-situ per-dispatch cost  0.699 / 406   = 1.72 us   (vs 2.46 us isolated)
```

A ~30% overlap credit is exactly what physics predicts, both budgets then close
simultaneously, and **frieren's head term is now corroborated by a budget that
was not looking for it.** tanjiro's #27 run C measures the in-situ coefficient
directly on both hosts, which settles it.

### 4b. frieren's exposed head latency is now the largest remaining decode item

> **PARTLY SUPERSEDED BY §10a (2026-08-04).** The reconciliation arithmetic below
> (in-situ `c_decode` 1.72 µs, host term 0.300 ms) was algebra against the wrong
> wall figure. nezuko #9's direct timestamp decomposition gives **2.18 µs and
> 0.200 ms**, and both budgets then close with zero residual. The re-pricing
> table in this section is superseded too: the ceiling is **2.9% of score**, not
> 4.4%. The *conclusion* — that this is the largest remaining decode item and
> that the term is host time which does not halve across generations — stands.

I briefed #23 at "<=2.9% of score" by dividing his M4 absolute by the M5 step.
That was wrong: the head term is **host** time and does not halve across
generations the way byte time does. That asymmetry is the same one that explains
the 78.6% / 78–85% efficiency invariance.

| M5 head term | share of the 4.353 ms step | share of score at elasticity 0.638 |
| ---: | ---: | ---: |
| 0.30 ms (unchanged) | 6.9% | **4.4%** |
| 0.25 ms (CPU ~1.2x) | 5.7% | **3.7%** |
| 0.15 ms (halved) | 3.4% | **2.2%** |

**Worth 2.2–4.4% of score**, against 1.4–2.8% for everything else in decode
combined. With access-pattern efficiency closed, this is the decode arm.

**Mechanism, verified from source this session.** The MLX compiled-decode
machinery is present, `MLXHardwareInfo.swift:33-38` defaults
`isCompiledDecodeSupported` to **true** (the official runner sets no env vars, so
it is on when ranked) — but it wraps only three call sites, all tiny:
`lagunaCompiledSoftplusGate` (`LagunaRuntimeModel.swift:5175`, a shapeless unary
softplus), `makeLagunaAttentionGateProjection` (`:5197`, softplus + multiply +
reshape + matmul), and the `L == 1` selector at `:6058`; called from `:6019`,
`:6066`, `:6153`. **The other ~400 dispatches of the step are outside any
compiled region and their graph is rebuilt in Swift on all 128 decode steps.**
`406 ops x ~0.7 us = 0.28 ms` matches the measured 0.29–0.32 ms.

Two cautions, both from a source comment left by a predecessor at `:5167-5170`:
*"Ranked measurement showed the larger gate/product graph regressing the complete
prefill schedule even though its isolated steady-state subpath was slightly
faster."* So (a) scope any enlargement to **decode only**, and (b) judge on the
whole matched pair, never an isolated subpath. Legality is clear: a compiled graph
is input-independent structure, carries no logits/KV/deferred rows/cross-request
state, and advances exactly one position per one-token request.

`MLXHardwareInfo.swift` is **not** in `editablePaths`; the four
`Compilable*`/`CompiledDecode`/`DynamicSlice` files in `mlx-swift-lm` **are**.

---

## Current research focus

### 5. Prefill is the only unsaturated axis left (new, 2026-08-04)

Decode is at the *same* fraction of achievable DRAM bandwidth on both
generations, which is the strongest possible evidence that its efficiency is an
access-pattern property rather than a tuning deficit:

```
M4 Pro:  1794 MB / 8.769 ms = 204.6 GB/s  of 260.2 achievable = 78.6%
M5 Max:  1794 MB / 4.353 ms = 412.1 GB/s  of ~485-530         = 78-85%
```

Two generations, 2× the bandwidth, 2× the cores, an entirely new matrix unit,
identical efficiency. Prefill on the same official receipt is at roughly **half
of both its ceilings at once**:

```
S = 98.153 ms / 512 tokens = 191.70 us/token
  -> 28.8 TFLOP/s = ~48% of the ~60 TFLOPS achievable NAX matrix peak
  -> 271.8 GB/s   = ~51% of the ~485-530 GB/s achievable DRAM
```

A kernel at 50% of compute *and* 50% of bandwidth is bound by neither — it is
bound by doing them in alternation. That reading is corroborated externally:
BaseRT on M5 Pro (arXiv 2607.19438) reaches 6.4× prefill over llama.cpp but only
0.98–1.33× decode, and states plainly that the Neural Accelerators do not raise
the memory ceiling.

**Official M5 hardware, Apple-confirmed:** 128 GB M5 Max = **614 GB/s** nominal
(LPDDR5X-9600, 512-bit), 40 GPU cores each with a Neural Accelerator, 18 CPU
cores. Metal STREAM attains 79–86% of nominal on M5-class parts and MLX 4-bit
decode on a real M5 Max derives 500–520 GB/s, so **GPU-achievable ≈ 485–530
GB/s**. Matrix peak ~60 TFLOPS FP16 measured real-shader on an actual M5 Max
(~30 TFLOPS on the SIMD path). bf16 tensor support arrived in OS 26.1;
cooperative tensors as matmul inputs (in-kernel dequant) in 26.3. Reject
Notebookcheck's "LPDDR5X-8533" (arithmetically impossible), PMetal's 546 GB/s
(stale M4), and Anemll's 148 GB/s (that is the ANE, not DRAM).

**Why the field has not taken this ground:** the prefill record `e2822dc1`
(npf 2.0220) has stood unbeaten for 102 submissions because no competitor can
*execute* a `_nax` kernel — every non-gen-17 host routes around it at
`quantized.cpp:1959`. That is a measurement wall, not a physics wall, and it is
the campaign's largest asymmetry. Prefill elasticity is 0.362, so a 10% S win is
3.6% of score and promotes on its own.

The cost of that asymmetry is that NAX arms are **structurally blind on M4**.
Budget receipts accordingly: `S` has a 0.497% 1σ floor, so screen a NAX change
with 1 receipt and only confirm with 2 more if it moves ≥1.5%.

### 6. The seed forward sits ON the roofline ridge, and overlap is the only lever

Section 5 said prefill is "at half of both ceilings". `research/prefill_ridge.py`
makes that rigorous per block and it changes the ranking of every prefill idea.

```
block                 GFLOP        MB   FLOP/B  cmp ms  dram ms  binds  ovl ms
attn_proj_qkvo       1460.3    2852.1    512.0   24.34     5.70    cmp   24.34
routed_experts       1005.0   14087.2     71.3   16.75    28.17   dram   28.17
attn_core             161.1       0.0      inf    2.68     0.00    cmp    2.68
shared_expert         125.6      69.0   1820.4    2.09     0.14    cmp    2.09
dense_mlp_layer0       51.5     100.7    512.0    0.86     0.20    cmp    0.86
router                 20.9      40.9    512.0    0.35     0.08    cmp    0.35
--------------------------------------------------------------------------
TOTAL                2829.5   17159.7    164.9   47.16    34.32
```

(60 TFLOP/s, 500 GB/s; expert bytes net of the 20.26% zero-row pairs. The 17.16
GB is weights only; the ~5.9 GB that reconciles it with the 23.1 GB real figure
is activation, KV-write, and fp32 split-K round-trip traffic.)

```
machine balance point   = 120.0 FLOP/byte   (60 TFLOP/s / 500 GB/s)
forward, weights only   = 164.9 FLOP/byte
forward, all traffic    = ~122.5 FLOP/byte  <- essentially exactly the ridge

serial sum of per-block floors    81.48 ms
per-kernel overlap ceiling        58.58 ms
measured S                        98.15 ms
```

**A workload at the ridge is simultaneously compute- and bandwidth-limited and
cannot be improved by relieving either resource alone.** That is why every
byte-removal instinct imported from decode misfires on prefill, and why overlap
is not one candidate among several but *the* structural lever. Per-kernel overlap
plus 9–12 ms of glue lands S at 67.6–70.6 ms = **28–31% of S = 10.2–11.3% of
score** — the largest recoverable item in the campaign, ahead of the decode
residual.

Three consequences, each of which re-ranks something:

1. **`routed_experts` is the only DRAM-bound block.** Staging *is* its DRAM read
   and is irreducible; double buffering converts `serial(cmp+dram) = 44.92 ms`
   into `max(cmp,dram) = 28.17 ms`, so the prize is **the 16.75 ms of MMA it
   hides**, not staging cost removed. The measured 45–50% of S (44.2–49.1 ms)
   brackets the 44.92 ms serial prediction closely, which is independent evidence
   the block really does run the two phases end to end. Fern's #24 is therefore
   worth **5.9–7.7% of score**, roughly 3× what its brief said, and the floor is
   hard at 28.17 ms (26.6 at 530 GB/s, 29.0 at 485).
2. **`attn_proj_qkvo` is compute-bound at 512 FLOP/byte** (24.34 ms compute vs
   5.70 ms DRAM), so the lever there is FLOPs or MMA utilisation, never bytes.
   Because measured S is only +20% over the serial-floors sum, each kernel is
   already near peak *for its own binding resource* — there is little to win by
   making the MMA faster.
3. **Our own receipt bounds the hardware.** Measured S ≥ the serial sum requires
   a compute floor ≤ `98.153 − 34.32 = 63.8 ms`, i.e. **M5 Max achievable matrix
   throughput ≥ 44.3 TFLOP/s**. First hardware bound this campaign has derived
   from its own data rather than a vendor claim; corroborates ~60 TFLOPS.

**Where the overlap actually is.** The 22.90 ms between the serial sum and the
overlap ceiling is not spread across the forward — it is almost entirely one
block:

```
block              serial   overlap   available    share
routed_experts      44.92     28.17      16.75 ms   73.1%   <- fern #24
attn_proj_qkvo      30.04     24.34       5.70 ms   24.9%
shared_expert        2.23      2.09       0.14 ms    0.6%
dense_mlp_layer0     1.06      0.86       0.20 ms    0.9%
router + g_proj      0.53      0.43       0.10 ms    0.4%
```

And the 5.70 ms in `attn_proj_qkvo` may already be captured: `gemm_nax.h:52-119`
streams fragments straight from device memory with **no threadgroup staging and
`mem_none` barriers**, i.e. nothing to serialise. If so the accounting closes
completely — `[attn_proj 24.34 already overlapped] + [experts 44.92 serial] +
[attn_core 2.68] + [shared 2.23] + [dense 1.06] + [router+g 0.53] + [glue 9–12] +
[~5.9 GB activation traffic ≈ 11.8]` = 97–101 ms against a measured 98.15.
**That is the first fully closed prefill budget the campaign has had**, and it says
**fern's #24 is not one prefill arm among several — it is essentially the whole
prefill opportunity.** Do not open a second prefill overlap arm in parallel with
it; C2 (BN 64→32) is his fallback route to the *same* 16.75 ms, not an independent
bet.

### 7. DISCLOSED INHERITED RISK: the frontier's attention quantization exceeds the written envelope

`lagunaNativeAffineNVFP4From` defaults to **0** (`LagunaRuntimeModel.swift:2907`),
so **all 40 layers run Q/K/V/O at NVFP4 g16** (0.5625 B/param) — not the group-32
affine INT8 (1.125) that TASK.md's accepted envelope permits, and coarser than it.
`lagunaNativeAffineProbeRoundTrip` (`:2936`) is a no-op unless
`DARKBLOOM_NATIVE_AFFINE_PROBE_FORMAT` is set, so nothing else perturbs the weight.

**Independently confirmed by measurement, not just by reading code.** If attention
were read at the envelope's INT8 g32 the decode step would move
`1794 + 802 = 2596 MB`, and `2596 MB / 8.769 ms = 296 GB/s`, above the measured
260.2 GB/s M4 ceiling — physically impossible. The step time proves the stream is
NVFP4 g16.

The in-tree defence is a comment at `:2903-2906`: "Numerically this is the shipped
representation the goldens came from — envelope option (1), which never requires
the INT8 re-quant", i.e. the claim that NVFP4 g16 *round-trips the checkpoint
exactly* and is therefore a lossless re-encoding rather than a re-quantization.

**That claim is false, and the organizer's own code says so.**
`LagunaConfig.swift:39-41`:

> The Poolside checkpoint keeps embeddings, attention, the dense layer, routers,
> and lm_head in BF16. **Only routed/shared expert projections are NVFP4-packed**,
> with one E4M3 scale per group of 16 values.

`git blame` puts that in `6d679f4` by `anupsv` ("Migrate Laguna serial track to
Poolside NVFP4 v2 (#755)") — organizer-authored. The tensor census in the same
enum confirms it arithmetically: `packedUInt32TensorCount = 234` and
`e4m3ScaleUInt8TensorCount = 234` = exactly **39 layers × 6 expert projections**;
attention is among the 405 BF16 tensors; `405+234+234+39 = 912` ✓. TASK.md also
contains no "option (1)". So the attention weights are genuine trained BF16 and
NVFP4 g16 on them is **lossy**.

**It is inherited, not ours.** `git blame` puts the whole
`lagunaNativeAffineNVFP4From` block in `99b974c1`, "Sync promoted frontier
afcb832". The organizer's own promoted frontier ships it, and it passes every
official gate including the hidden teacher-forced cases, GPQA and the semantic
judge. Exposure if the written envelope were ever enforced:

```
decode attention stream, shipped (NVFP4 g16)  =  807.7 MB/token
decode attention stream, envelope (INT8 g32)  = 1609.9 MB/token
                                       delta  =  802.2 MB = 44.7% of 1794 MB
                                            -> 0.638 × 44.7% = 28.5% of score
```

**Advisor ruling.** Disclose, do not unilaterally remove, do not extend.
Removing it would forfeit 28.5% of score on my reading of prose, against a tree
the organizer promoted; hiding it would be worse. Inheriting the practice is one
thing — applying reduced precision to *new* tensors would be our own act, so the
routers, the layer-0 dense MLP, `lm_head`, embeddings and the KV cache stay
exactly as they are. Flagged to the operator for a ruling.

**Two dead arms, killed before assignment.** I had scoped a "lossless
re-encoding" arm worth 3.62% of score (routers 40.9 → 11.5 MB, layer-0 dense MLP
100.7 → 28.3 MB). It required the checkpoint to be NVFP4-native; it is not, so
re-encoding those tensors would be lossy *and* explicitly forbidden. Dead. What
survives is only **genuinely lossless BF16 compression** (fixed-length
exponent-codebook over 256-element blocks, ~22% → ~31 MB → ~1.1% of score):
legal, small, and technically hard — variable-length entropy coding is unusable
on GPU because it serialises per symbol. Low priority. Open questions if anyone
revives it: the true distinct-exponent count per block (at 32–40 the index grows
to 5–6 bits and the margin dies), and whether the LSU rather than the ALU is the
real constraint. Exclude the KV cache — activations, wider exponent range,
rewritten every step.

**Doctrine correction.** I previously wrote that decode byte removal has exactly
one legal lever because "BF16 ⇒ untouchable". The reasoning was wrong (the
frontier does synthesise non-BF16 attention banks at load) but the conclusion was
right, and for a better reason: lossless re-encoding needs no envelope permission
but the checkpoint offers almost none, and lossy re-quantization of unlisted
tensors stays forbidden regardless of what it would buy.

### 8. The four M5 constants this campaign is currently guessing (new, 2026-08-04)

Every priced arm on the board divides by a number nobody has measured on the
ranked host:

| constant | current value | provenance | what it prices |
| --- | --- | --- | --- |
| M5 achievable DRAM GB/s | **485–530** | literature: 614 nominal x Metal STREAM 79–86%, plus a third-party MLX 4-bit decode figure of 500–520 | the entire decode byte budget; the 28.17 ms DRAM floor of prefill `routed_experts`, i.e. fern #24's whole prize |
| M5 matrix TFLOP/s at our GEMM shapes | **60** | Apple marketing "real-shader FP16 peak" | the 47.16 ms compute side of the forward; whether `routed_experts` is DRAM-bound at all |
| M5 per-dispatch cost | **0.48–1.25 us** (needed for closure) vs 2.46 us measured on M4 | pure extrapolation | 0.46 ms of the 4.353 ms decode step, and whether a dispatch-count arm exists |
| prefill overlap + glue | **9–12 ms** of 98.15 | residual of my roofline against the measured forward | direction 5b, C5, and the credibility of the 16.75 ms figure |

Our own receipt only bounds the second one from below: compute floor
≤ 98.153 − 34.32 = 63.8 ms ⇒ **M5 Max matrix throughput ≥ 44.3 TFLOP/s.** At 44.3
rather than 60 the forward's compute side rises from 47.16 to 63.8 ms and
`routed_experts` compute goes 16.75 → 22.7 ms, which moves fern's prize by a
third. **We cannot rank arms to 0.6% while the denominators move by 35%.**

`senpai/tools/*` is outside `editablePaths`, so tanjiro's probe can never run on
the M5 and we have no shell there. But the channel exists and he already proved
it with the A/B/C noise-floor family: **a deliberately slowed, output-neutral
instrumented candidate passes every gate and returns a complete receipt.** Inject
a known quantity of work into the scored path and read the slope out of the
receipt. Two observables per run (`decode_seconds_per_token`,
`prefill_seconds_per_token`) ⇒ two constants per submission, four in two
submissions. The 0.95 floors are measured against the *pinned baseline* and we
sit at ~2.7x decode / ~1.98x prefill, so a deliberate 15–30% slowdown still
publishes complete metrics. This is tanjiro's round-6 arm.

### 9. Flag-position audit: 65 flags, and exactly ONE is off on evidence that does not transfer (new, 2026-08-04)

I audited every `DARKBLOOM_*` flag in `Sources/MLXFastModel/` by **the provenance
of the evidence that set its default**, after the compiled-decode finding showed
that reading the comments pays. Vocabulary matters: *"Ablation on the paired local
benchmark"* means the predecessor's own host; *"Ranked measurement"* and
*"MEASURED (2026-08-01, M5 Max 128 GB, driver rig, 150-step cool-floor ABBA)"*
mean the real thing.

**58 flags ship ON. 7 are opt-in.** Of the 7:

| flag | why it is off | verdict |
| --- | --- | --- |
| `DARKBLOOM_TRACE_FUSION` | diagnostic | correctly off |
| `DARKBLOOM_PREFILL_ROUTER_TOP8` | **ranked -0.68%** on submission `fe01af9` (1.11254 vs 1.12019). Per-lane predecessor-count selection is ~10x the ALU of the batched merge sort; at 512 rows the stock `argPartition` amortises to a few us/layer (`:8748-8755`) | correctly off |
| `DARKBLOOM_SHARED_FIRST_DOWN` | **real M5 Max driver rig, 2026-08-01**: regresses ~+0.10 ms/step (`:7620-7635`) | correctly off |
| `DARKBLOOM_ROPE_ATLAS_VIEWS` | **real M5 Max driver rig ABBA, 2026-08-01**: +0.01..+0.07 ms/step (`:571-578`) | correctly off |
| `DARKBLOOM_NATIVE_AFFINE_SUFFIX` | a depth-selection probe knob, not a lever (`:309-319`) | correctly off |
| `DARKBLOOM_FUSED_QKV` | *"Ablation on the **paired local benchmark** showed a mild prefill cost with no decode gain"* (`:108-114`) | **THE ONLY ONE OFF ON NON-TRANSFERRING EVIDENCE** |

**Conclusion: the frontier's flag positions are almost all justified, and there is
exactly one free-flip candidate in the whole tree.** That candidate is `FUSED_QKV`
= direction C3, and its case is now stronger than bytes: `k` and `v` are `N=1024`
and each dispatch only 64 threadgroups, so on 40 M5 cores this is an **occupancy**
argument, and the local ablation that disabled it ran on 20 cores. Stop treating
the ~90-flag surface as unexplored territory; it is not.

**Three reusable facts extracted, one of which kills one of my own directions.**

1. **Metal memory barriers are encoder-wide, not per-resource** (`:7620-7635`). In
   the shipped routed-first order the shared-expert QMV is encoded *after* the
   routed QMV with no intervening barrier, so **it already overlaps on the GPU**;
   moving it earlier makes the top-8 barrier wait on it too and *lengthens* the
   critical path. **This substantially downgrades direction 5b** (overlap the
   compute-bound `shared_expert` inside `routed_experts`' DRAM stall, which I
   priced at 0.77% of score): the decode analogue was tried on a real M5 and
   regressed. Any dispatch-reordering arm now has to argue against an
   encoder-wide barrier, not a per-resource one.
2. **A predecessor had an M5 Max 128 GB driver rig** and ran 150-step cool-floor
   ABBA windows. Several in-tree comments therefore carry **better evidence than
   anything this campaign can currently produce.** Standing rule: read the comment
   at the site before assigning an arm there.
3. **The two RoPE probe dispatches at the head of every decode step are off the
   critical path** - they overlap the embedding gather and the layer-0 front, so
   removing them buys nothing. And aliasing ~3 MB atlas buffers as per-step kernel
   inputs "appears to add slight **resource-tracking cost**" - a named, M5-measured
   *host-side* per-step term, which is exactly frieren's #23 quantity.

### 10. BOTH decode budgets now close EXACTLY, and three of my briefed candidates are dead (new, 2026-08-04)

A source audit of MLX's command-buffer machinery plus a re-read of nezuko #9's
sweep table settled the §4b reconciliation with measurements instead of algebra,
and killed three candidates I had briefed. **§4b's 1.72 µs / 0.300 ms pair is
superseded by 2.18 µs / 0.200 ms.**

#### 10a. The single decomposition that closes both budgets

nezuko #9's shipped-configuration row (`FUSE=0 SPLIT=0`, 120 steps, GPU
timestamps windowed to the steady decode span) is the campaign's best decode
instrument and I had under-used it:

```
45 command buffers   406 dispatches
  wall             8.545 ms
  gpu_busy_union   8.345 ms      (== gpu_busy_sum to 6 ns)
  host gap         0.200 ms
```

`gpu_busy_union` is pure GPU occupancy, so `wall − gpu_busy_union = 0.200 ms`
**is** the exposed host term, measured directly rather than inferred from spin
injection. Fitting tanjiro #21's mechanisms against *her* wall, with the ramp
coefficient as the only free parameter:

```
byte roofline                          6.895 ms   measured (#21 probe)
cache-served GQA KV re-read            0.375 ms   measured (#21)
named per-stream shortfalls            0.191 ms   measured (#21)
launch ramp  406 × 2.18 µs             0.884 ms   FITTED
                                      --------
                        gpu_busy_union  8.345 ms   nezuko, exactly
exposed host term                       0.200 ms   nezuko, exactly
                                      --------
                                  wall  8.545 ms   nezuko, exactly
```

- **In-situ per-dispatch cost = 2.18 µs** against tanjiro's 2.46 µs isolated: an
  11% overlap credit, not the 30% I predicted in §4b. tanjiro's isolated
  measurement was nearly right and his closure survives with a smaller
  correction than §4b claimed.
- **The exposed host term is 0.200 ms**, not frieren's spin-derived 0.29–0.32 ms.
  Treat 0.200 as the point estimate and 0.32 as the upper bound.
- The 0.224 ms between nezuko's 8.545 ms wall and the 8.769 ms quoted elsewhere
  is **cross-session wall variance, not a physical term.** Stop budgeting it.

Consequence: frieren's #23 ceiling drops from 4.4% to **2.9% of score**, with a
realistic partial win of 1.0–1.5%. Still the largest single decode item.

#### 10b. `gpu_busy_sum == gpu_busy_union` to 6 ns — ZERO decode concurrency

In all four of nezuko's arms. 406 dispatches strictly serialised, nothing
overlapping anything. This is why tanjiro's additive ramp model closes at all,
and it means the 0.884 ms ramp has nothing to hide behind: **any reduction in
dispatch count or threadgroup count pays at full rate.** (Do not reopen the
concurrent-encoder route; #9 closed it.)

#### 10c. The 45 command buffers per step are forced by MLX, and 45 IS the ranked count

This **refutes frieren's standing #14 caveat** that the low-memory profile caps
command buffers so ~45/step is not the ranked figure. `needs_commit()`
(`device.cpp:484-487`) is:

```cpp
return (buffer_ops_ > max_ops) || ((buffer_sizes_ >> 20) > max_mb);
```

- `buffer_sizes_ += a.data_size()` (`:319-321`) charges the **entire distinct MTL
  buffer in item units**, not the slice actually read; deduplicated by buffer
  pointer; dedup set cleared at `end_encoding()` (`:465`); counters zeroed at
  `commit()` (`:528-529`).
- **Thresholds are chosen by the last character of the GPU architecture name**
  (`:574-595`): `'p'` phone 20/40, `'g'` base/pro **40/40**, `'s'` max **50/50**,
  `'d'` ultra 50/50. A newly identified M4→M5 divergence — student hosts are
  `'g'`, the ranked M5 Max is `'s'`.
- It does not bind differently here: one layer's routed-expert bank is ~805M
  params ≈ **100 Mi uint32 words + 50 Mi scale bytes**, past *both* 40 and 50 on
  first touch. So the count is ~one commit per layer on both generations:
  ~40 byte-triggered + frieren's 7 `asyncEval` rungs = 47 vs her measured 45.

**Therefore nezuko's 45-buffer decomposition is a valid ranked-host prediction,
and 10a transfers to the M5 as structure.** Cost of a command buffer, from her
SPLIT=1 vs SPLIT=0 contrast: **~1.90 µs of `gpu_busy` and ~2.94 µs of host gap.**
Not reducible from the editable surface — `device.cpp`, `eval.cpp`, `utils.h` and
`device.h` are all blocked, and the commit count is pinned by the bank sizes.

Open cheap confirmation: print `MTL::Device::architecture()->name()` on a student
host (expect suffix `g`, generation 16) to make the 40-vs-50 reading measured.

#### 10d. THREE briefed candidates are dead — enqueue-earlier is already harvested

`LagunaRuntimeModel.swift:638-715` carries `DARKBLOOM_DECODE_ASYNC_STAGE`
(default **`at:0,1,7,15,23,31,39`**, seven `asyncEval` fires per step, gated on
input shape exactly `[1,1]`; fire sites `:10767`, `:10779`, `:10784`) and
`DARKBLOOM_ATTN_PROJECTION_ASYNC` (default **on**: "enqueue layer 0's
already-constructed QKV and gate projections before the rest of that layer's
graph is built"). Recorded evidence at `:655-674` — the strongest measurement
block in the tree:

```
MEASURED, notes/52 (two Latin squares, 66 runs, 66/66 passed_correctness,
steady step 8..128, all contrasts 6/6 paired)
  off       (0 fires)  10.3735 ms
  ladder8   (5 fires)   9.4533 ms = 1.0000  previous promoted default
  ladder6   (6 fires)             1.0064
  ladder2  (20 fires)             1.0169
  ladder1  (40 fires)             1.0178
  at:1,7,15,23,31,39              1.0170   <- six fires, ties forty
```

Enqueue-earlier was already worth **+9.7%** (`off`→`ladder8`); the author records
the residual on this axis as **0.15 ms** and this default as taking essentially
all of it. A lone fire at layer 1 measures **0.9476 — the worst schedule tested.**

- **DEAD: "commit the embedding gather first".** Shipped and swept.
- **DEAD: the 200 kB logits readback.** `Evaluate.swift:701-717` — `step()`
  returns `convertToToken(logits:)`, so the D2H is a **4-byte scalar**, and
  `.item()` blocks on token N−1 which was enqueued a full step earlier. A
  correctly pipelined one-token-lag tail with no stall to remove.
- **DEAD: command-buffer/encoder creation.** 10c: not on the surface.
- **SURVIVES: graph construction.** `MLXHardwareInfo.swift:33-38` defaults
  `isCompiledDecodeSupported` true (official runner sets no env vars ⇒ ON when
  ranked) but wraps only three tiny call sites (`:5175`, `:5197`, `:6058`, called
  from `:6019`, `:6066`, `:6153`). **The other ~400 ops rebuild their graph in
  Swift on all 128 decode steps**: `406 × ~0.7 µs = 0.28 ms`, the same order as
  the whole exposed term. `CompiledDecode.swift`, `CompilableKVCache.swift`,
  `CompilableRotatingKVCache.swift`, `DynamicSlice.swift` are editable;
  `MLXHardwareInfo.swift` is not. Scope to decode only — `:5167-5170` records a
  ranked regression of the *prefill* schedule from a larger gate/product graph.

#### 10e. fern's double buffering must be done at BN=32, not BN=64

Audited the expert kernel's threadgroup footprint. `BK_padded = BK + 16/sizeof(Wtype)
= 72` (`:551`); `kWsElems = BN × BK_padded = 4608`; `Ws_storage` = 576 × 16 B =
**9,216 B**, plus `bounds[2]` = 8 B. Two corrections to my earlier framing:
`gate_up_stage` is **aliased onto `Ws_storage`** (`:1620-1621`), and `Atile`
(`:1735`) is **register-private, not threadgroup**. So `Ws` is the *entire*
threadgroup footprint.

tanjiro #13 measured 80 TGs co-resident at 17,920 B on 20 cores = 4/core, so the
per-core budget is ≥ 71,680 B:

| Ws footprint | TGs/core | vs shipped |
| --- | ---: | ---: |
| 9,224 B shipped, single-buffered | 7 | 1.00× |
| **18,440 B naive double buffer** | **3** | **0.43×** |

18,440 B is essentially tanjiro's measured 17,920 B point, where he fitted
`f(m) ≈ 1 + 0.365(m−1)`; 7→3 co-resident TGs costs `f(7)/f(3) = 1.70×` of
latency-hiding. **Naive C1 buys intra-threadgroup overlap by destroying
inter-threadgroup overlap** — the classic way double buffering fails.

**C2 (`BN 64→32`) makes `kWsElems = 32 × 72 = 2304` = 4,608 B, so
double-buffered = 9,216 B = EXACTLY the shipped footprint.** Same co-residency,
same total staged bytes (each TG stages half the N-rows, `grid.x` doubles), and
2× the threadgroups suits 40 cores better than 20. **My "never bundle C1 and C2"
instruction is withdrawn**: C2 is not a second mechanism, it is the enabling
condition that makes C1 testable at constant occupancy. Order: C2 alone → C1+C2
(the arm) → C1 alone (occupancy control).

Two landmines at `BN=32`: `tile_matmad_nax` (`steel/gemm/nax.h:993-1031`) has
exactly two branches and no `else`, so a `TN` landing on 1 with `TM=1` silently
does no MMA; and `gate_up_stage`'s alias onto `Ws_storage` needs an explicit
lifetime-disjointness argument once there are two buffers.

#### 10f. The two decode tables use DIFFERENT ceilings. Do not cross-read them.

I nearly issued a wrong correction over an apparent 4× conflict. There is none,
and the distinction matters for every future roofline row:

- **nezuko #9's re-scoped table** (`research/nezuko-pr9-dispatch-fusion.md:126-144`)
  has columns `n | true µs | µs/step | MB | GB/s | %ceil | recoverable µs/step`,
  where `recoverable = µs/step − bytes/step / 260.2`. Its ceiling is the **flat
  DRAM ceiling**. For a dispatch moving 33 kB/step this is meaningless — you can
  never run 33 kB at 260 GB/s.
- **tanjiro #21's table** (`research/tanjiro-pr21-result.md:148-152`) has columns
  `n | achieved GB/s | modelled ceiling GB/s | µs`, where the ceiling is
  **pattern- and size-corrected** by his measured bytes-per-dispatch curve, and
  the last column is the shortfall against *that*.

So `gate_sp_h64+h48` is "211 µs recoverable" by her column and **83 µs** by his;
`residual_rms_router` is "106 µs" by hers and **27 µs** by his. **tanjiro's is
correct in both cases.** This is precisely why his #21 collapsed the recoverable
total from ~1.2 ms to 0.191 ms. Standing rule, alongside issued-vs-unique bytes:
**every roofline row must declare which ceiling it divides by.**

#### 10g. The launch-ramp term is concentrated, not spread — but see the 10h downgrade below

The 0.884 ms ramp is not evenly distributed over 406 dispatches. Three families
that move essentially no bytes carry a disproportionate share (nezuko's
`µs/step` column, which is a direct measurement and not ceiling-relative):

| family | calls/step | µs/step | MB/step | note |
| --- | ---: | ---: | ---: | --- |
| `gate_sp_h64` + `gate_sp_h48` | 40 | 213 | 0.033 | #9 tried fusing into QKV, got nothing |
| `decode_router_top8_ordinal_table_norm_v1` | 39 | 96 | 0.004 | **never attacked** |
| `rmsbfloat16` | 41 | 36 | 0.008 | **never attacked**; 0.87 µs/call = tanjiro's single-threadgroup empty-dispatch floor exactly |
| **total** | **120** | **345** | **0.045** | 30% of dispatches, 39% of the ramp budget |

345 µs is **4.0% of the 8.545 ms step = 2.6% of score**. This is not a bandwidth
shortfall and does not appear in tanjiro's 0.191 ms recoverable figure — it is
already inside his ramp term, which is exactly why removing dispatches pays at
full rate under §10b.

**The unattacked half is 132 µs = 1.5% of step = 0.99% of score**, above the
0.61% bar. `rmsbfloat16` at 0.87 µs/call is pure launch overhead with no
measurable work, and the tree already proves the fix pattern works: a shared
512-thread RMSNorm prologue is *already* fused into three decode kernels
(`LagunaRuntimeModel.swift:~741`), so 41 generic calls remain that need not.

Caveat that shapes the brief: #9's single fusion attempt failed **because the
absorbing kernel slowed by +0.95 µs/call and broke additivity by +8.23 µs/layer**,
not because the dispatch saving was absent. Any arm here must measure the
absorbing kernel's own per-call cost before and after, and reject on that
number rather than on the dispatch count.

**DOWNGRADE, same day, by me.** Two things are wrong with the paragraph above.

1. The claim that "removing dispatches pays at full rate under §10b" is
   contradicted by the only direct experiment we have. nezuko's own four-arm
   table removed 40 of 406 dispatches and the step went **8.545 → 8.773 ms,
   i.e. +0.228 ms *worse***. §10b establishes that the ramp has nothing to hide
   behind, which is a statement about *concurrency*; it does not establish that
   fusion *captures* the ramp. Fusion moves work into an absorbing kernel that
   then runs less efficiently, and #9 measured that penalty exceeding the
   saving. The honest reading: the 2.18 µs ramp coefficient was **fitted as the
   single free parameter** to close the budget, and the one attempt to cash it
   in returned negative. Treat 2.18 µs as an accounting residual, not as a
   recoverable per-dispatch prize.
2. The `96 µs` and `36 µs` recoverable figures come from nezuko's `recov`
   column, which §10f — written in the same sitting — says is computed against
   the **flat DRAM ceiling** and is meaningless for tiny-byte dispatches. I
   used the wrong column two sections after warning about it.

What survives: `residual_rms_router` (27 µs on tanjiro's corrected ceiling) is
already **assigned**, as Part 2 of #27. The remaining unassigned content of 10g
is thin and rests on a coefficient that failed its only direct test. **It is no
longer the top unassigned decode arm.** 10h is.

#### 10h. NEW TOP UNASSIGNED DECODE ARM: the attention core reads every KV byte four times, and `#5` never closed it

The decode attention core is **905 µs/step, 10.6% of the 8.545 ms step**, and it
is the largest block in the step that is neither at a roofline nor accounted for
by anything we have measured:

| kernel | calls/step | µs/call | µs/step | unique MB | issued MB | issued GB/s |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `sliding_fused_attn_ring_v1` | 30 | 22.34 | 670 | 2.097 | 8.389 | 375 |
| `full_fused_attn_grow_v1` | 10 | ~23.5 | 235 | 2.621 | ~7.9 | ~334 |

Compute for the whole core is **671 MFLOP/step ≈ 24 µs** at the measured MMA
rate, and unique traffic is 4.7 MB ≈ 18 µs at 260.2 GB/s. So the core is ~37×
off its compute roofline and ~50× off its DRAM roofline. On *issued* bytes it
runs at 1.45× the DRAM ceiling, i.e. **L2-served** — consistent with frieren
#14, which measured DRAM-level sliding amplification at only ≤1.18×. The 4× is
absorbed by cache, and the 0.375 ms "cache-served GQA KV re-read" line in the
§10a budget is exactly this.

**Source-verified cause.** Both kernels dispatch `grid: ((heads/2) * 1024)`,
`threadGroup: 1024` (`LagunaRuntimeModel.swift:1794-1795`, `:2306-2307`) and
map `head0 = pair_tg * 2`, `kv_head = head0 / 8` (`:1400-1402`, `:1871-1873`).
Inside a threadgroup the 32 simdgroups sweep the ring with `i = sg; i += 2*BN`
at `BN = 32` (`:1524-1525`), so **one threadgroup's 32 simdgroups read all 512
slots of its `kv_head` exactly once**, 16 slots per simdgroup, 2 in flight.
Therefore:

```
sliding: gqa = 8 (:1392)  64 query heads / 2 = 32 TGs, 4 TGs per kv head = 4x
full:    gqa = 6 (:1861)  48 query heads / 2 = 24 TGs, 3 TGs per kv head = 3x
```

Two consequences of `gqa = 6` on the full-attention path, both of which I had
wrong on the first pass:

- Issued traffic there is `3 × 2.621 = 7.86 MB`, i.e. 334 GB/s and **1.28×** the
  DRAM ceiling, not the 1.70× / 446 GB/s in tanjiro's #21 retraction. His
  sliding figure is confirmed exactly; the full figure looks like it inherited a
  4× numerator by analogy. Worth a line in his next report, and it makes the
  full-attention half of this arm about 25% smaller than I first priced it.
- **`h` must divide the GQA ratio, and the two kernels have different ratios.**
  Legal `h` is `{1, 2, 4, 8}` for sliding and `{1, 2, 3, 6}` for full. A student
  who templates one kernel and picks `h = 4` everywhere will have full-attention
  threadgroups straddle two `kv_head`s — heads 4,5 belong to kv 0 while 6,7
  belong to kv 1 — and `kv_head = head0 / gqa` will silently address the wrong
  ring for half the heads. This is a wrong-answer landmine of exactly the
  `tile_matmad_nax` no-`else` variety. The matched pair is **sliding `h=4` with
  full `h=3`**, or **sliding `h=8` with full `h=6`** for the 1× configuration.

The `2` is not tuned. The kernel comment says it is a "textual replica of the
`sdpa_vector` pair path" — MLX picked 2 generically for GQA pair sharing. **On
the ranked 40-core M5 these grids are 32 and 24 threadgroups, so 8 and 16 cores
are structurally idle for the whole dispatch. On our 20-core M4 the same grids
are 1.6 and 1.2 per core, i.e. comfortably fed.** This is a textbook M4→M5
non-transfer: the host we measure on cannot see the defect.

**The prior closure is invalid.** The closed-families table carries
`Sliding-window KV re-read | closed | #5` — a one-line inherited entry, and
tanjiro established in #13/#calibration that **#5 is not in this tree at all**.
Nothing in this campaign has tested it. Reopened.

**I talked myself out of this arm and then back into it. The argument matters,
because it determines the mechanism.** Bytes per lane are fixed at 16 slots ×
16 B = **256 B**, independent of how many query heads a threadgroup owns, so at
first sight grouping more heads per threadgroup cuts bytes and lanes in equal
proportion and buys nothing. That is only true if each lane is
memory-level-parallelism-limited. It is not: 32,768 lanes × 32 B in flight =
**1.05 MB in flight against a bandwidth-delay product of ~150 kB** at 375 GB/s
and ~400 ns, so the fabric is oversubscribed ~7×. Cutting lanes 4× still leaves
~262 kB in flight, comfortably above the BDP, so the kernel stays saturated
while moving 4× fewer bytes. **De-amplification does pay.** The same arithmetic
says deeper software pipelining (2-deep → 4-deep) does *not*, which kills the
cheaper-looking arm first.

**Mechanism, in the order a student should try it.** Let `h` = query heads per
threadgroup, `s` = simdgroups per threadgroup. Amplification is `8/h`; issued
traffic is `16.78 MB / h`; threadgroup `outputs` scales with `h · s ·
planes_per_round`. Bit-exactness is preserved for any `h` as long as `s = 32`,
because each simdgroup keeps its exact slot set `{sg, sg+32, …}`, its sequential
accumulation order, and the unchanged 32-lane `simd_max` / `simd_sum` butterfly
epilogue (`:1634-1655`).

| config | TGs (sliding) | amp | issued MB | TG mem | dispatches | bit-exact |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| `h=2, s=32` shipped | 32 | 4× | 8.389 | 17,920 B | 1 | — |
| **`h=4, s=32` "quad path"** | **16** | **2×** | **4.19** | **18,944 B** | **1** | **yes, trivially** |
| `h=8, s=32` | 8 | 1× | 2.097 | ~8.7 kB | 1 | yes, but ~320 B/thread of registers risks spilling |
| `h=8, s=8` | 32 | 1× | 2.097 | ~8.7 kB | 2 | yes, needs a deferred epilogue |

Start at **sliding `h=4` / full `h=3`**: one dispatch, no epilogue restructuring,
no extra threadgroup memory of consequence (the exchange goes from 2-plane to
1-plane rounds, 4 rounds instead of 2), and it halves issued KV traffic on the
sliding path and cuts it by a third on the full path.

Priced at the **fully-L2-bandwidth-bound ceiling**, which is the optimistic end:

```
sliding  8.389 -> 4.19 MB   22.34 -> 11.2 us   x30  saves 335 us
full     7.86  -> 5.24 MB   23.5  -> 15.7 us   x10  saves  78 us
                                                    ---------------
                                            413 us = 4.8% of step = 3.1% of score
```

The realistic figure is lower: the kernel will turn latency-bound somewhere
below 375 GB/s, so treat **1.5–2.0% of score** as the expected capture and 3.1%
as the ceiling. `h=8` / `h=6` roughly doubles the ceiling again if registers
hold. Either number clears the 0.61% bar and the lower one alone would not
promote, so this is a component of a promotion, not a promotion on its own.

**Two hard constraints from our own results.**
- Any variant needing a second dispatch per attention layer adds 40 dispatches
  per step, and #9 priced exactly that at **+0.228 ms**. So the `h=8, s=8`
  epilogue must be **folded into the existing `oproj_act_h64/h48` kernel**,
  which already reads `attended`, runs at 95% of the DRAM ceiling, and would
  absorb a 133 kB partial-plane read for ~0.5 µs. A standalone combine kernel
  is not fundable.
- `h` changes thread mapping, and tanjiro's standing rule from #10/#13 is that
  **thread mapping does not transfer from 20 cores to 40**. The M4 will
  under-report the occupancy half and should read the bandwidth half correctly.
  Judge on `ns`, and expect to need one M5 receipt.

**The one number that prices this arm, and we do not have it.** Everything above
turns on whether 375 GB/s is at or below the M4 Pro's **L2-resident** read
ceiling. tanjiro's `senpai/tools/bandwidth-pattern-probe` control of 262.5 GB/s
is a *DRAM* number; he has no cache-resident point. Shrinking that probe's
working set below L2 is a ~20-minute local addition that costs no submission and
converts this arm from a hypothesis into a priced one. Requested on #27 as a
non-blocking addendum.

**Programme-level reading.** fern's #24 (double-buffer the expert-GEMM `Ws`
stage) and this arm are the prefill and decode instances of one hypothesis: the
tree's latency-hiding was chosen for a 260 GB/s, 20-core machine and is ranked on
a ~500 GB/s, 40-core one. If both land, that hypothesis, not any single kernel,
is the campaign's result.


### Round 4 outcome

| PR | student | verdict |
| --- | --- | --- |
| #14 | frieren | **merged.** Scored diff empty by design; host-CPU axis closed with `wall ≈ head_latency + GPU_total`, KV re-request amplification refuted at ≥6.9σ, metallib failure proven to be a host issue reproducing on the unchanged base. 0 submissions |
| #22 | fern | **merged.** Hypothesis dead, three durable findings: the Part 0 transform contract is GREEN (no pinned `weights_hash` exists in trusted code), scale amplification is **A = 1.000 exactly**, and `Sources/MLXFastTransform/` is **dominated** by eager load-time repack. 0 submissions, 17 minutes |
| #20 | nezuko | in flight — lm_head cascade |
| #21 | tanjiro | in flight — pricing the residual |

### Round 5 in flight / Round 6 opening

| PR | student | arm |
| --- | --- | --- |
| #20 | nezuko | **lm_head cascade.** The last legal decode byte lever: 134.9 MB int5 plane, 7.5% of the step. Immediate target 25.7 MB (0.91% of score, transfers 1:1), structural ceiling ~105 MB (3.7%). **Plus a second lever handed over from #21:** `lmhead_exact_inline_mask_block` runs at **6.5 GB/s**, 6x below tanjiro's own bytes-per-dispatch curve at 0.481 MB, worth ~0.48% — a real defect, not a small-dispatch artefact |
| #21 | tanjiro | **MERGED — strong negative, campaign-defining.** Decode is bandwidth-closed: access pattern worth 0.000 ms, unexplained +0.000 ms. See §4. Recoverable re-priced 10.9% → 1.4–2.8% of score. 0 submissions |
| #23 | frieren | **exposed head latency** — the one term in his own model the GPU does not absorb. **Re-priced to 2.2–4.4% of score** (§4b): the term is host time and does not halve across generations. Mechanism now verified from source — compiled decode is ON but wraps only 3 micro-fusion sites, so ~400 dispatches rebuild their graph every step. **Largest remaining decode arm.** |
| #24 | fern | **double-buffer the expert gather-GEMM's weight staging.** `Ws` is single-buffered, so every MMA phase blocks the next stage. Locally falsifiable on the non-NAX twin first, then ported. **Re-priced by finding 6 to 5.9–7.7% of score** (~3× the brief; and 6.2–8.4% once the assumed 60 TFLOP/s is allowed to range down to the receipt-bounded 44.3, which moves the prize 16.75 → 22.69 ms) with a hard floor at 28.17 ms, and it holds **73% of all the overlap available anywhere in the forward** |
| #27 | tanjiro | **round 6: measure the four M5 constants** (§8) by output-neutral work injection into the scored path, differenced across receipts so no control run is needed. 4 submissions authorised; must report `BW` and `TFLOP/s` mid-arm because fern is blocked on them |

Why #24 is the shape it is: `DARKBLOOM_EXPERT_GATHER_GROUPS` went 64 → 128 → 256
and measured a real M5 gain at *every* step while changing nothing
arithmetically. Its entire mechanism is getting the hardware scheduler to overlap
one threadgroup's staging drain with another's MMA. It is now pinned at its
maximum (one threadgroup per expert), so the only remaining place to attack that
stall is *inside* the threadgroup.

**The calibration fact that governs every prefill arm:** M4 tiling verdicts
invert on M5. The predecessor measured `STAGE_BM128` variant 4 beating variant 5
by **+17.47%, 4/4 pairs, zero distributional overlap** (342–371 µs vs 414–434
µs) — and the official M5 receipts reversed it, 204.90 → 201.64 µs/token in
favour of variant 5, which is what ships. A 19-point reversal. A local M4 number
is evidence a mechanism exists; it is not evidence of magnitude and not evidence
of sign.

### Promotion target

Promotion requires `officialScore > 2.53921`, and `officialScore = ns × draw`.

| our ns | required draw | expected submissions to promote |
| ---: | ---: | ---: |
| 2.5157 (today) | 1.00934 | never observed |
| 2.5260 | 1.00523 | ~303 |
| 2.5331 | 1.00241 | ~130 |
| 2.5400 | 0.99969 | ~28 |
| **2.5450** | **0.99772** | **~12** |
| 2.5686 | 0.98847 | ~2 |

**Target `ns` >= 2.545, i.e. +1.16% on today's tree.** Resubmission is a
measurement channel, not a strategy.

### The strategic fact that defines this campaign

Normalising all 909 scored public submissions: ours sits at nd 2.7130 (91st
percentile), npf 2.0057 (88th percentile), ns 2.5157. The field records are
nd **2.739127** (`ae9ac90b`) and npf **2.0220** (`e2822dc1`).

```
naive union of both field maxima:  ns = 2.739127^0.75 * 2.0220^0.25 = 2.5390
promotion needs                    ns = 2.5392 at draw 1.000
```

So the *naive* union of everything the entire public field has ever achieved
lands one part in ten thousand short of promotion at a median-plus draw. nezuko
then de-biased those maxima for the winner's curse (measured directly on family
A, n=18: nd +0.494%, ns +0.413%) and obtained a **true field ceiling of
2.5281–2.5318** — 0.5–0.7% short of even a 1-in-12 shot.

**Conclusion: harvesting the field cannot promote us. We need a mechanism the
field does not have.** That is why every round-4 arm targets a byte stream or an
efficiency gap rather than a public diff.

---

## Established facts (do not re-derive)

### Model configuration (`Sources/MLXFastModel/LagunaConfig.swift:14-35`)

vocab 100352, hidden 2048, 40 layers, headDim 128, 8 KV heads. **48 query heads**
on the 10 full-attention layers (indices 0, 4, 8, …, 36) and **64 query heads**
on the 30 sliding-window layers (window 512). 256 routed experts, top-k 8,
MoE + shared-expert intermediate 512, dense MLP intermediate 8192 on layer 0
only. NVFP4 config `{"group_size":16,"bits":4,"mode":"nvfp4"}`.

Precision by class, with the byte rates used in the budget:

| class | representation | B/param |
| --- | --- | ---: |
| q/k/v/o | BF16 on disk (`LagunaCheckpointValidation.swift:355-358`), re-quantised at load to **NVFP4 g16** (`LagunaRuntimeModel.swift:2960-2974`, `:5302-5305`) | 0.5625 |
| `g_proj` | group-32 affine INT8 (`LagunaRuntimeModel.swift:431-448`) | 1.125 |
| routed + shared experts | NVFP4 g16 on disk | 0.5625 |
| lm_head, embeddings, routers, dense-0, norms | BF16 | 2.0 |
| KV cache | BF16 (`KVCache.swift:375-376`, `:629-630`); `RotatingKVCache(maxSize: 512, keep: 0)` at `LagunaRuntimeModel.swift:10840-10845` | 2.0 |
| lm_head int5 screening plane | 1344 B per vocab row | |

### The NAX gate — a programme-level constraint (fern #11)

`mlx::core::metal::is_nax_available()`
(`Vendor/mlx-swift/.../backend/metal/device.cpp:913-931`) requires macOS >= 26.2
**and GPU arch gen >= 17**. Our M4 Pro hosts report `applegpu_g16s gen=16`: the
OS gate passes, the generation gate fails.

- **94.2% of prefill GPU time on a student host runs Metal functions the official
  M5 never executes** — different kernels, not the same kernel at different
  occupancy: `nvfp4_gather_qmm_rhs_nt` 48.5%, `steel_gemm_fused_nt_bm64_bn64_bk16`
  33.4%, split-K 6.0%, `steel_attention_bfloat16_bq32_bk16` 5.1%,
  `nvfp4_qmm_t` 1.2%. Only 5.8% of prefill is host-generation-independent.
- The **steady decode step is 100% host-independent**: every dispatch is a
  hand-written `laguna_*` kernel (or `rms`/`gather_front`). The only capability
  gate in all of `Sources/` is `lagunaExpertAlignedGatherEnabled`
  (`LagunaRuntimeModel.swift:235-249`), used at exactly one **prefill** site
  (`:9631`).
- Never run a prefill *kernel* experiment on a student host. Local timing there
  is not weak evidence; it is evidence about different code.
- `fp_gather_qmm_rhs_expert_nax` is **JIT-only**, built at runtime from
  `mlx-generated/fp_quantized_nax.cpp`. Editing the header alone changes nothing
  at runtime; the generated `.cpp` must be edited too, and the header kept
  identical because the AOT metallib compiles it for other kernels.
- Three silent-failure modes on that kernel: odd `TN>1` yields an empty
  `tile_matmad_nax`; `SM<16` yields `TM=0` and no MMA at all; falling off the
  `bm==64 && wm==4` gate (`quantized.cpp:1668-1671`) silently dispatches the
  non-expert kernel. Any arm here needs a positive "MMA actually executed"
  assertion.
- `SM 16→8` is impossible: `TM = SM/16` (`fp_quantized_nax.h:1719`),
  `kFragRows = 16` (`steel/gemm/nax.h:28,540,547`). The resulting 31.3% MMA row
  padding is a hardware floor.

### Forward-pass budget (fern #11)

2830.2 GFLOP and 26.68 GB per 512-token forward = 106.1 FLOP/byte. Shares:
`attn_proj_qkvo` 51.8%, `routed_experts` 35.5%, `attn_core` 5.7%,
`shared_expert` 4.4%, `dense_mlp_layer0` 1.8%, `router` 0.7%.

- M4 forward: 4.83 TFLOP/s (16.8% of MMA ceiling) and 45.6 GB/s (17.5% of DRAM).
  **Neither bound on M4** — which is why M4 prefill timing is uninformative.
- M5 forward: S = 98.153 ms → **28.8 TFLOP/s and 271.8 GB/s**, roughly half of
  each M5 roofline. This is the least-understood region of the whole problem and
  is where the field's prefill record has stood unbeaten for 102 submissions.

### Measured M4 Pro ceilings

scalar FMA f32 7.07 / f16 7.59 TFLOP/s; simdgroup MMA bf16 28.76 / f16 28.96
TFLOP/s; DRAM **260.2 GB/s**.

### Routing histogram at 512 tokens (host-independent, `research/prefill-512-route-histogram.txt`)

mean 16.00 rows per (layer, expert), stdev 28.77 (**CV 1.80**), p50 7, p75 19,
p90 39, p95 58, p99 142, max 505, **20.3% of pairs receive zero rows**. Busiest
8 experts hold 26.0% of assignments, busiest 32 hold 54.7%. Per-layer max/mean =
15.2×. The shipped expert tile parameters were "Simulated over uniform routing"
(`quantized.cpp:1405-1415`) — empirically false.

### Harness and gate facts

- **The acceptance band `[0.980, 1.053]` is NOT enforced.** `Constants.swift:150-166`,
  `benchmark.yml:1511` and `overlay-paired-timing.sh:129-169` apply only the two
  0.95 floors. **Never throttle a win to fit the band.**
- **TTFT is not gated.** `gpqa_ttft_max_seconds` is `seconds.max() ?? 0`
  (`LagunaRuntimeCorrectness.swift:230-232`); no max-seconds threshold exists.
  Init-time headroom is effectively unbounded.
- `metal_kernel.cpp` and MLX `device.cpp` dispatch entry are **not** in
  `editablePaths` → concurrent encoder dispatch is permanently closed.
- A/A noise floor on M4 `--local-iterate`: prefill −1.30%, decode +0.48%. A
  sub-1.5% single-run prefill delta on M4 is noise. Local `prefill_speedup ≈ 0.33`
  is the M4/M5 hardware ratio against the pinned
  `officialBaselinePrefillSecondsPerToken = 0.00036751938916015625`, not a
  regression.
- Submission surface after #12: totalBytes 2,912,613 of 3,000,000; `fileCount`
  pinned at 142; ~87 KB of headroom. `editablePaths` = 97 entries.

### Integrity rulings (fern refused to ship both; upheld)

Pre-touching a live buffer pool across the phase boundary, and pre-boosting the
GPU clock across the hello→request boundary, are both **circumvention**, not
optimisation.

---

## Closed families — do not re-litigate

- **Decode access-pattern efficiency — CLOSED (tanjiro #21).** Every real pattern
  reaches 87-94% of the sequential control at equal bytes/dispatch. Scattered
  expert blocks 94%, KV ring 87-89% and stride-insensitive. The residual closes
  with **+0.000 ms unexplained**. See section 4.
- **Offline codes/scales interleave - CLOSED TWICE.** fern read A = 1.000 from
  source; tanjiro measured -0.3% to +2.5% on silicon. Source and measurement
  agree. Nobody is to propose it again.
- **`./probe` on the M5 - IMPOSSIBLE, not merely hard.** `senpai/tools/*` is
  outside `editablePaths`; it is never uploaded and there is no shell on the
  ranked host. The only M5 channel is a submitted candidate plus its receipt
  `metrics`.

| family | verdict | evidence |
| --- | --- | --- |
| **In-loop host CPU** | **CLOSED** | frieren #14: injecting 2.0 ms/step of per-layer host spin *reduced* wall 8.903→8.669 ms (fully absorbed), while identical spin at the *step head* passed through 1:1. Therefore `wall ≈ head_latency + GPU_total`. M4 decode is 97.7% GPU-busy with a 0.29–0.32 ms exposed gap. A −3.7% main-thread / −30.6% source-byte cut moved `T` by 0.0% ±0.2% |
| **KV re-request amplification** | **REFUTED** | frieren #14 slope method. Sweep A (seeds 512..6144, only the 10 full-attention layers grow): 27.03 ns/pos/layer, no curvature over 21–252 MB. Sweep B (below 512, all 40 layers, 16 palindromic runs): 828.6 ± 56.2 ns/pos → sliding 18.61 ns/pos/layer. Amplification ≤1.72× full, ≤1.18× sliding; waste ≤ +28.4 MB (≤1.01% of score). The 190 MB claim is ≥6.9σ out. **Replacement finding:** the full-attention path is the least bandwidth-efficient stream at 58.2% of peak vs the 78.6% step average, capped at 16.9 MB/step ≈ 0.6% of score |
| **Attention / sliding occupancy** | **CLOSED** | tanjiro #13: 80 threadgroups co-reside at the real 17920 B / 1024-thread shape on 20 M4 cores. The g=21/41 risers are **work imbalance**, `f(m) ≈ 1 + 0.365(m-1)`, not occupancy. `w=2→1` is model-closed as an M5 loss; `w>=4` exceeds the 32768 B threadgroup-memory limit. He withdrew his own 81920 B linear-pool model |
| **Harvesting the public field** | **CLOSED** | nezuko #12: de-biased field ceiling 2.5281–2.5318, below a 1-in-12 shot |
| **Quantized attention weights in prefill** | **CLOSED by arithmetic** | advisor, `research/prefill_ridge.py`. Reusing the existing decode NVFP4 g16 banks in prefill removes 2054.3 MB of weight reads and is worth ~nothing: `attn_proj_qkvo` is **compute**-bound at 512 FLOP/byte (24.34 ms MMA vs 5.70 ms DRAM), so it shaves DRAM that is already hidden while adding dequantization to the binding term. The tree's "Prefill stays on the original BF16 projections" (`LagunaRuntimeModel.swift:293-298`) is correct design. **General rule: the same weights want opposite representations in the two phases** — decode's attention stream is bandwidth-bound, prefill's is compute-bound, because 512 tokens amortise the weight read 512× |
| **Prefill byte removal as a general strategy** | **CLOSED** | advisor, finding 6. The 512-token forward sits *on* the roofline ridge (~122.5 FLOP/byte against a 120 FLOP/byte machine balance point), so relieving either resource alone cannot help. Only `routed_experts` (71.3 FLOP/byte) is DRAM-bound; every other block is compute-bound. Byte-counting intuitions imported from decode do not transfer to prefill — **overlap** is the lever |
| **Advisor axis-coverage tables** | **RETRACTED** | nezuko #12: note-length artifacts. Median \|axis-mean nd − overall\| = 0.220%, inside noise. The last survivor, `Sources/MLXFastTransform/` (0 of 147 swept diffs), is now also closed — see below |
| **`Sources/MLXFastTransform/`** | **CLOSED by dominance** | fern #22: `prepareFusedRuntimeWeights` is **eager** and resident before the first forward (`LagunaRuntimeModel.swift:10893-10898`), so load-time repack is unscored and *strictly more capable* than offline layout — it can also repack the BF16 attention weights, which offline cannot, since Q/K/V/O and `g_proj` ship BF16 on disk (`LagunaCheckpointValidation.swift:355-360`) and the NVFP4/INT8 banks are synthesised at load (`:5301-5305`). RAM is not binding (21.57 of 25 GiB). The axis is untouched in 147 public diffs because it is **dominated, not overlooked**. Also: `DARKBLOOM_PACKED_SCALES` already ships ON, packing routed gate/up scales in the kernel's exact walk order (`:152-167`, `:9824-9856`) |
| **NVFP4 scale-plane amplification** | **CLOSED, A = 1.000** | fern #22: the v5 down/residual kernel (`LagunaRuntimeModel.swift:7658-7705`) reads `expert_scales + output_row*32 + lane` over 4 rows × 32 lanes = exactly one aligned 128 B cache line, fully consumed, alongside 1024 contiguous code bytes fully consumed. Independent bound from that kernel's measured 231 GB/s: `231*(1024+128A)/1152 ≤ 260.2` ⇒ `A ≤ 2.14`. The advisor's 8× premise (and its restated 3.6× form) were arithmetically impossible from data already in the repo |
| **Part 0 transform contract** | **GREEN, reusable** | fern #22: the official run **does** execute the submitted transform (`benchmark.yml:1074-1113`); `weights_hash` is an *emitted-artifact* hash produced after our transform (`:1122`) and every comparison is same-session TOCTOU only. **No pinned 64-hex weights constant exists in trusted code.** `MLXFAST_VERIFY_TRANSFORM` is determinism-only and defaults false (`TransformVerification.swift:79-81`, `:105`). Future constraints: regular non-symlink files, link count 1, ≤25 GiB (`Constants.swift:176`; today 21.57 GB), deterministic |
| **`DARKBLOOM_STAGE_BM128` tiling family** | **CLOSED at the floor** | advisor, from fern's measured routing histogram. The expert-aligned NAX gather-GEMM runs one threadgroup per expert (`quantized.cpp:1922`) and elides simdgroup bands past the row count (`fp_quantized_nax.h:1704-1706`), so MMA waste is *row padding*: `ceil(n_e/SM)*SM`. Real routing (20.26% zero-row, mean 20.07 nonzero, **median 11**) gives SM=16 → 453,120 MMA rows = 1.456× ideal, and **453,120 is exactly `Σ ceil(n_e/16)·16`**, the `kFragRows = 16` fragment floor (`steel/gemm/nax.h:28`). SM=32 is a flat **+41%**; BM=128 buys 5.7% fewer stagings for that +41%. The shipped variant 5 is optimal on this axis. `DARKBLOOM_EXPERT_GATHER_GROUPS` is likewise pinned at its 256 maximum (code returns 256 at `:1383` despite a header comment claiming 128) |
| **First-touch prewarm** | **CLOSED** | fern #19: six back-to-back forwards 544.72 / 546.68 / 546.11 / 547.48 / 546.81 / 546.74 ms — the *first* is fastest. Cache exactly 0 B at timed entry, 35.75 GB live, 39.07 GB peak. `cacheLimit=0` vs 6 GiB indistinguishable. On a ≥96 GiB M5 the constructor already wires ~31.4 GiB via `set_wired_limit` before hello (`LagunaRuntimeWeights.swift:546-580`). `argmax_bfloat16` PSO compile (~0.23 s) is already outside scored prefill (`:499-510`) |
| **Attention INT8 envelope** | **DEAD, BACKWARDS** | the frontier already runs Q/K/V/O at NVFP4 g16 (0.5625 B/param) vs the envelope's group-32 INT8 (1.125). Adopting it adds ~802 MB/step |
| Dispatch count / fusion for latency | closed | nezuko #9: deleting 40 of 406 dispatches/step returned zero end-to-end (`--local-iterate` 13.604 vs base 13.569/13.647) and **+0.228 ms *worse* on the instrumented step** (8.773 vs 8.545 ms), because the absorbing kernel slowed by +0.95 µs/call. Prices any arm that *adds* 40 dispatches at −0.228 ms — see §10h |
| Concurrent encoder dispatch | closed | `gpu_busy_sum == gpu_busy_union` to 6 ns; entry files not editable |
| ~~Sliding-window KV re-read~~ | **REOPENED, see §10h** | The `#5` entry was a one-line inherited claim and tanjiro proved **#5 is not in this tree**. Source now confirms 4× (sliding) and 3× (full) L2-level KV read amplification from `head0 = pair_tg * 2`. Nothing in this campaign ever tested it |
| Certified LM-head screening (old form) | closed | #6 |
| M4-argmax geometry as evidence | closed | #10 |
| Routed-MoE BM widening; sub-16 SM | closed | hardware floor, see NAX gate |
| Zero-row expert skip | closed | DRAM-bound; no bytes removed |
| `arangeuint32` caching | closed | the 76 dispatches were a command-buffer overlap artifact, ~0 ms real |
| Prefill host CPU / command buffers | closed | prefill GPU-busy union is 99.4% of wall |
| `DARKBLOOM_ATTN_QHOIST`, `GEMM_TPARAM_MACRO` | closed | no effect |

---

## Submission ledger (official M5)

| id | tree | published / renorm `ns` | note |
| --- | --- | --- | --- |
| `27b9c7c6-14bf-…` | frontier + #7 | 2.49724 / 2.5152 | rejected; all gates passed |
| `f8502e12`, `71586bcf`, `f3cda678` | BASE_SHA, byte-identical ×3 | — | tanjiro control family |
| `5d522d6a` | nezuko harvest tip | 2.491470 / 2.520600 | rejected |
| `5e0e9cd1` | same tip | 2.500092 / 2.513024 | rejected |
| `c210d200` | same tip | 2.514743 / 2.521103 | rejected |

nezuko's harvest tip vs the control family: `ns` **+0.214% ± 0.122%**,
`T` **−0.468% ± 0.181% (2.6σ)**, `S` +0.236% ± 0.142%, `officialScore`
−0.056% ± 0.399%. A real `T` win, near-zero on `ns`. She recommended dropping
`9c1ad1c` (cap-400, the suspected `S` regression) and `6ca0c71` (both
individually inert); that is the first commit of #20.

**The promoted best is not a good tree.** `8415f63c` posted `officialScore`
2.53921 but **ranks 92nd of 919 on content**: its +1.483% lead over us decomposes
into **−0.063% content and +1.547% luck** (draw 1.00896 = p100). The cleanest
proof in the corpus is `0c83fa3e`, which holds the **3rd-lowest `T` of 919** with
no runtime mechanism whatsoever — one environment integer changed 200→160 plus
two inert `static_assert` deletions — while simultaneously carrying a +1.464%
prefill regression.

**The board is frozen.** 2026-08-04 saw 41 submissions and 0 acceptances. Corpus:
139 accepted, 769 rejected, 463 failed.

---

## Potential next research directions

Ordered by expected value, given that decode is a byte budget and prefill is the
field's frozen axis.

1. **M5 prefill is the field's blind spot and it sits at ~50% of both rooflines.**
   S = 98.153 ms → 28.8 TFLOP/s and 271.8 GB/s on a host whose MMA peak is
   ≥57 TFLOP/s (plus NAX) and whose DRAM peak is ≥500 GB/s. Elasticity on S is
   0.362, so a 10% S win is 3.6% of score — larger than any decode arm we have.
   The field's prefill record has stood for 102 submissions **not because prefill
   is physically hard but because nobody can execute a `_nax` kernel on non-gen-17
   hardware**: the only prefill instrument in existence is a 35-minute official
   submission returning one scalar. That is a measurement wall, not a physics
   wall, and it is the largest asymmetry available to us. Requires
   host-independent reasoning (routing statistics, static kernel analysis, byte
   arithmetic) validated by 3-receipt official families. Analysis in progress:
   `research/PREFILL_NAX_ANALYSIS.md`.
2. **De-amplify the decode attention core's KV read (§10h, unassigned, top
   decode arm).** Both fused attention kernels put 2 query heads in a
   threadgroup and have each threadgroup's 32 simdgroups sweep its `kv_head`'s
   whole ring, so 4 threadgroups (sliding) and 3 (full) read the same KV bytes.
   905 µs/step, 10.6% of the step, 37× off compute roofline and 50× off DRAM
   roofline, running at 1.45× the DRAM ceiling on issued bytes because L2
   absorbs the duplication. The `2` is an untuned MLX `sdpa_vector` inheritance,
   and on the ranked 40-core M5 the grids are only 32 and 24 threadgroups. First
   step is bit-exact and one dispatch: sliding `h=4` with full `h=3` (`h` must
   divide the GQA ratio, which differs between the two kernels — 8 and 6). 3.1%
   of score at the bandwidth-bound ceiling, 1.5–2.0% expected. Blocked on one
   cheap local number — the M4's L2-resident read ceiling — requested from
   tanjiro on #27.

3. **Deepen the lm_head cascade beyond nezuko's first 25.7 MB.** The int5 plane is
   134.9 MB = 7.5% of the step. A hierarchical screen (very coarse bound over all
   100352 rows → int5 on ~10³ survivors → exact rescore) could take the plane to
   ~30 MB, i.e. ~105 MB removed = 3.7% of score, which promotes on its own. Must
   be split into independently correct ≤5% increments per the calibration band.
4. **Overlap staging with MMA inside the expert gather-GEMM** (assigned, fern
   #24). Staging is 39.5% of prefill and `Ws` is single-buffered, so the WAR
   barrier serialises every MMA phase against the next stage — which is exactly
   the signature of a kernel at half of both rooflines. The corroboration is that
   `DARKBLOOM_EXPERT_GATHER_GROUPS` bought real M5 gains at 64 → 128 → 256 purely
   by letting *other* threadgroups cover the stall, and is now pinned at its
   maximum. Risk: doubling `Ws` 9.2 → 18.4 KB may halve resident threadgroups per
   core and reverse the sign — which is why §10e establishes that **BN 64→32 is
   the enabling condition, not a fallback**: at `BN=32` a double-buffered `Ws`
   is 9,216 B, exactly the shipped single-buffered footprint, so co-residency is
   preserved. My original "never bundle" instruction was withdrawn on #24.
5. **Bit-exact fused split-K for the NAX steel path** (`o_proj`, `g_proj`,
   router). Removes ~0.72 GB of fp32 round-trip traffic and ~80–120 dispatches by
   porting the `qmm_t_splitk_fused` recipe (`quantized.cpp:849-893`) to
   `steel_gemm_splitk_nax` (`matmul.cpp:689-810`; split-K branch at `:987-991`,
   `C_split` fp32 at `:734-737`). Predicted 1.5–3% of S, and unusually attractive
   because it is **locally falsifiable on the non-NAX twin**. Note `q_proj` still
   runs the tiles labelled "Temp routing for larger devices" at
   `matmul.cpp:228-238`.
6. **Prefill glue-pass reduction.** ~18 ms of M4 host-independent glue ≈ 9–12% of
   M5 S. **Corrected pricing:** that 9–12% is the *term size*, not the win — the
   recoverable part is ~30% of it, i.e. **1–2% of S = 0.36–0.72% of score**, which
   straddles my 0.61% acceptance bar. I had previously recorded the term size as
   the win and mis-ranked this as the largest receipt-free prefill item; it is
   not. Its real virtue is that it is the *only* prefill family with full local
   falsifiability, so it costs no receipts to screen. Good filler work, not a
   headline arm.
5b. **Overlap the shared expert with the routed experts.** They consume the same
   post-attention hidden state and their outputs are summed, so they are
   independent sub-graphs. `shared_expert` is compute-bound (2.09 ms) and
   `routed_experts` is DRAM-bound (28.17 ms stall to hide in), so the shared
   expert can in principle run entirely inside the routed stall: **2.1% of S =
   0.77% of score**, bit-exact if the summation order is preserved. Small, clean,
   and it is the only *cross-block* overlap the dependency graph permits — every
   other pair in the forward is strictly sequential.
7. **Routing-aware two-regime expert dispatch.** The shipped tile is tuned for
   uniform routing that does not occur (CV 1.80, 20.3% empty, busiest 32 experts
   = 54.7%). Row-tile widening, sub-16 SM, and now the whole `STAGE_BM128` tiling
   family are closed — SM=16 attains the `kFragRows = 16` padding floor exactly.
   A *two-regime* split (short tail and long tail dispatched differently) is the
   only remaining way to get below 1.456× MMA rows, and it would have to break
   per-expert weight exclusivity to do it. Needs a mechanism proposal, not a knob.
8. **`attn_proj_qkvo` is 51.8% of forward FLOP** and the largest single block in
   the seed forward — larger than routed experts. On M5 it is the
   `steel_gemm_fused_nax` (bm128/bn128/bk512) family. **Now priced (finding 6):**
   it is *compute*-bound at 512 FLOP/byte — 24.34 ms of MMA against 5.70 ms of
   DRAM — so bytes are the wrong lever and it is already near peak for its binding
   resource. Two live sub-ideas remain: (a) `k_proj`/`v_proj` at N=1024 dispatch
   only 64 threadgroups each on a 40-core GPU, twice per layer, so the C3
   row-concat QKV idea is about *occupancy*, not bytes; (b) `q_proj` still runs
   tiles labelled "Temp routing for larger devices" (`matmul.cpp:228-238`).
   **Explicitly closed:** using the existing decode NVFP4 attention banks in
   prefill. It looks like −2054 MB of weight reads but shaves DRAM that is already
   hidden while adding dequantization to the binding term. The tree's "Prefill
   stays on the original BF16 projections" is correct design, not an oversight —
   the same weights want opposite representations in the two phases.
9. **If tanjiro's #21 finds the 21.4% residual is recoverable**, that becomes the
   top priority immediately: up to 13.6% of score, the largest single number in
   the campaign. If he finds it is not, close decode-efficiency permanently and
   put all four students on byte removal and prefill.
10. **Unassigned decode item with an unresolved contradiction:**
   `lmhead_exact_inline_mask_block_v1` costs 76.6 µs/step on M4, but 76.6 µs at
   260.2 GB/s can move at most ~20 MB — irreconcilable with a 134.9 MB plane read.
   Folded into nezuko's #20 as a required explanation.
11. **~83 single-threadgroup dispatches per decode step** (tanjiro, unassigned);
   fusing RMSNorm into QKV removes 40. Re-priced UP by §10b: decode has **zero
   dispatch concurrency**, so the 2.18 µs in-situ cost is fully exposed and
   removing 40 dispatches is worth ~87 µs = 1.0% of step = 0.65% of score. Still
   caveated by #9's direct measurement that its one attempted fusion returned
   nothing — the confounder there was the two-body kernel slowing by +0.95 µs/call,
   not the dispatch saving being absent. **frieren's "low-memory host caps command
   buffers so ~45/step is not the ranked count" caveat is REFUTED by §10c**: the
   count is set by `needs_commit()`'s byte threshold against per-layer expert
   banks that exceed both the 40 (`'g'`) and 50 (`'s'`) limits, so ~45 is the
   ranked count and her instrumented decomposition transfers.
12. **Minify the remaining 71 Metal literals in `LagunaRuntimeModel.swift`**
   (−54,251 B of surface). Worth 0.0% of score; only relevant if we ever run out
   of the ~87 KB of surface headroom.
