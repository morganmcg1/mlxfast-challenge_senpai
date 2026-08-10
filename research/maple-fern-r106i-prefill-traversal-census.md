# R106-I — The prefill traversal-byte census

**Student** maple-fern · **PR** #625 · **assignment** `maple-r106-i-prefill-traversal-byte-census`
· **revision** `r106-i-rev1` · **base** `f5f0e00268df6867f5a16db252ba813e5711a55b`
· **W&B** run `ozb0177l` —
https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/ozb0177l

**Scope fence.** This is a *bytes* census of the 512-token prefill forward. It
makes no claim on prefill *time* attribution (tanjiro, R106-H), decode bytes
(#619/#615), #597, or #616. No candidate change, no mechanism arm, zero
official receipts.

**Tag key.** `[STRUCT]` = read off a captured dispatch ledger or MLX source.
`[PROJ]` = model output. `[M4-WALL]` = wall-clock on this M4 Pro host.
`[M5-RCPT]` = number that came back on an official M5 receipt. Every byte
figure is labelled **BINDING** (bytes an operand occupies, charged once per
dispatch that binds it) or **TRAVERSAL** (bytes actually pulled across the
memory interface, i.e. footprint × multiplicity). The two are never mixed in
one sum.

---

## 0. Verdict

**V-FLOORS-INFLATED.**

The prefill DRAM floors that the standing prior art quotes are too high, and
the two largest errors are arithmetic, not physical:

1. The routed-expert weight floor of **35.64 ms** [PROJ] is built from
   `1,769,472 × 256 × 39` bytes. It uses *all 256* expert slots per layer and
   *39* MoE layers. The trace shows **38** gather-GEMM layer pairs, and the
   routing histogram shows **20.26 %** of `(layer, expert)` pairs receive zero
   rows. Correct M5 above-SLC cost is **29.06 ms** [PROJ] — **−6.58 ms
   (−18.5 %)**.
2. The "glue class runs at 99 % of its floor" verdict is **refuted twice
   over**: its byte sum and its time sum use *inconsistent class membership*
   (both self-consistent repairs are physically impossible), and its true
   above-SLC floor is **4.19 ms** [PROJ] against **8.04 ms** [PROJ] of
   projected time — roughly **1.9× over floor**, i.e. ≈ 3.85 ms of headroom,
   not 1 %.

**V-REREAD is refuted** for the routed *weight* pool on M5: the expert-aligned
`_nax` gather kernel never lets a threadgroup straddle two experts, so weight
traversal multiplicity is **0.8613× < 1**. The routed *activation* n-tile
re-read is real (≈ 15.2 GB, 8.5× multiplicity) but its working set is
per-expert row slices of a few KB, so it is absorbed and contributes ~0 DRAM
bytes.

**N-FLOORS-STAND and N-INSTRUMENT are both rejected.** N-INSTRUMENT is
rejected on the strongest possible ground: the assignment's premise of a
"hard tracer quota" is factually wrong (§2.2).

Headline: **B_pre = 31.3640 GB BINDING**, **61.258 MB/token** [STRUCT].
Prefill read-multiplicity **TRAVERSAL/BINDING = 1.90–2.67× on M5** [PROJ]
(3.40–4.39× on M4 [STRUCT]); **above-SLC/BINDING = 0.729–1.186×**; M5
above-SLC floor **41.86–68.09 ms** [PROJ] against `S = 97.89475 ms` [M5-RCPT].

---

## 1. Preregistered outcomes (rule 72)

Registered before the model was run, in the order the assignment lists them:

| outcome | fires when | fired? |
|---|---|---|
| **N-FLOORS-STAND** | traversal ≈ binding (T/B ≤ ~1.15) and the published per-stage floors survive re-derivation | no |
| **V-FLOORS-INFLATED** | a published floor is materially higher than the traversal-based floor for the same stage | **YES** |
| **V-REREAD** | traversal ≫ binding because a scored kernel re-reads a large operand from DRAM | no (weights); partially yes but absorbed (activations) |
| **N-INSTRUMENT** | the instrument cannot resolve the question (quota, truncation, missing operands) | no |

Falsification conditions I committed to: V-FLOORS-INFLATED requires a *named*
arithmetic or physical defect in the published floor, not merely a different
model; V-REREAD requires the re-read to survive the SLC.

---

## 2. Method and provenance

### 2.1 Capture

No new capture was needed. The committed R106-G dispatch ledger already
contains **two complete 512-token prefill forwards**.

| artefact | bytes | sha256 |
|---|---|---|
| `research/artifacts/fern-r106g/dispatch_raw.tsv` | 2,792,366 | `0a82cc1ac9b156c9242b40da888613d105beabbea96a57e4262ef46314fc2834` |
| `research/r106c/scripts/trace_dag.patch` | 10,114 | `d28789841b5933dfb44d310d320a1387fb69d84647421bee7ad36f8ce6c248fc` |

Capture command (`research/r106c/scripts/run_dag_trace.sh:34-41`):

```
MLX_TRACE_DUMP_DIR=$DUMP mlxfast-swift correctness-trace \
  --weights "$ROOT/weights" \
  --golden  "$ROOT/correctness_prompts/public_longcopy_gate_english_512_256.json" \
  --step "$STEP" --top-k 5
```

`Sources/MLXFastCLI/main.swift:30-31,175-218` routes that to
`LagunaRuntime.traceCorrectness`. The ledger spans the whole worker process,
so it holds **(1)** the untimed constructor-time warmup — one 512-token
constant-BOS prefill plus a decode step, `Sources/MLXFastModel/LagunaRuntimeWeights.swift:471-483`
invoked at `:417-418` — and **(2)** the real `correctness_begin` 512-token
prefill, `Sources/MLXFastTrustedHarness/LagunaRuntimeWorker.swift:291-303`.
Both are 512 tokens, which is exactly the scored frozen prefill window
(`AGENTS.md:117`); the golden fixture's `prompt_tokens` has 512 entries.

I census **prefill forward #1 = rows 6115…7334 inclusive**: 1220 dispatches,
81 encoders, 671 barriers [STRUCT]. Row 6115 is the `gather_front` embedding
lookup, row 7334 is the last lm_head stage, row 7335 begins decode. Forward #2
(≈ rows 7910…9070) reproduces it. Prior art independently measured 1222
dispatches / 81 command buffers, so the window is reproduced to ±2 dispatches
(the two extras are the classifier's `other` bucket, absent from my window —
see §5).

Ledger columns: `seq  kernel  kind  grid(WxHxD)  group(WxHxD)  args  barrier
enc  ins  outs`, with `ins`/`outs` entries formatted `ptr+offset:bytes`.

### 2.2 Proof of no truncation — the assignment's "hard quota" premise is wrong

The assignment asks me to work around a tracer byte quota. **There is no
quota.** `research/r106c/scripts/trace_dag.patch` contains no `limit`, `cap`,
`max`, `quota`, or `truncat` token anywhere; the *only* match for that whole
class of terms in the patch is `out.flush()` at **`trace_dag.patch:202`**,
which flushes the `ofstream` after **every** dispatch row. The 1,671,168 B
figure that motivated the premise was page-flush truncation in the *older*
R103-B patch, and it was already corrected by the advisor at
`research/maple-tanjiro-r103b-kernel-text-differential.md:1174-1187`.

Positive checks that the window is complete, not clipped:

- the file's last byte is a newline terminating a well-formed 10-column row;
- the window's dispatch count (1220) matches prior art's independent count
  (1222) to ±2, and the encoder count (81) matches exactly;
- every structural invariant of the architecture is present at full
  multiplicity: 76 = 38 × 2 routed gather GEMMs, 38 `sorted_moe_tail`, 39
  router tournaments, 39 `steel_attention`, 40 layers of QKV projection;
- forward #2 in the same file reproduces forward #1's kernel histogram.

This is `[STRUCT]`, not inference. **N-INSTRUMENT does not fire.**

### 2.3 Dispatch geometry (rule 77)

Every family's geometry is regular across the window. Read directly from the
`grid`/`group`/`args` columns:

| kernel | n | grid (W×H×D) | group | shapes |
|---|---|---|---|---|
| `steel_gemm_splitk_nt … bm32_bn32_bk16_wm2_wn2` | 78 | 32×16×2 | 32×2×2 | `[512,2048]×[2048,1024]` → K/V proj |
| " | 38 | 8×16×2 | 32×2×2 | `[2048,256]` router logits |
| " | 29 / 10 | 2×16×4 | 32×2×2 | `[2048,64]` / `[2048,48]` per-head `g_proj` |
| `steel_gemm_fused_nt … bm64_bn64_bk16_wm2_wn2` | 31 / 30 | 128×8×1 / 32×8×1 | 32×2×2 | `[2048,8192]` Q proj (incl. 2 dense-MLP layer-0) / `[8192,2048]` O proj |
| " | 10 / 10 | 96×8×1 / 32×8×1 | 32×2×2 | `[2048,6144]` / `[6144,2048]` (48-head layers) |
| " | 1 | 32×8×1 | 32×2×2 | `[2048,2048]` |
| `steel_gemm_splitk_accum` | 155 | — | — | float32 partials → bf16 |
| `nvfp4_gather_qmm_rhs_nt … bm_16_bn_32` | 38 | 32×256×1 | 32×2×1 | x`[4096,1,2048]`, wq uint32`[256,1024,256]`, sc uint8`[256,1024,128]` → gate/up |
| " | 38 | 64×256×1 | 32×2×1 | x`[4096,1,512]`, wq uint32`[256,2048,64]`, sc uint8`[256,2048,32]` → down |
| `nvfp4_qmm_t_splitk_fused` (bm=bn=32) | 76 | 16×16×1 | 32×2×2 | shared gate & up, N=512, K=2048 |
| `nvfp4_qmm_t … batch_0` (bm=bn=32) | 38 | 64×16×1 | 32×2×2 | shared down, N=2048, K=512 |
| `steel_attention … bq32_bk16_bd128_wm4_wn1` | 29 / 10 | 16×64×1 / 16×48×1 | 32×4×1 | causal, Hkv=8, Lq=Lk=512 |
| `gemv_al` | 2 | 258×1 / 128×1 | — | `[2048,8256]`, `[8192,2048]` |

For the steel GEMMs the grid is `(N/bn, M/bm, split_k)` (`matmul.cpp:591`,
`:308`), which is the whole basis of the multiplicity rules in §3.

### 2.4 Artefacts and hashes (rule 75)

Everything below is research-only (outside `benchmark.json`'s `editablePaths`),
so submitted-surface byte cost is **zero**.

| path | bytes | sha256 |
|---|---|---|
| `research/r106i/window.py` | 809 | `8793fbbf19b5cf38e31a83c57b706baefab6778383f7764fe5d9a74a888d22b8` |
| `research/r106i/census.py` | 3,815 | `dd9aaefab27be9e410e921ec2d677301d40b7942f552e1cf15d3507b3145041d` |
| `research/r106i/traversal.py` | 10,972 | `592ae4f7e61e283c1f7a7091e6cb16685545d4b6b920419d36ebf0ecbdf3ee1c` |
| `research/r106i/wandb_log.py` | 2,996 | `44c26969017d6ba0525cb3f367f549852b6d95773690970efe896a8bde29ca53` |
| `research/r106i/binding.json` | 657 | `0bdd12016377850d5a74d12257c3e927a0640d5851d80d2a83d62b1acd9c7426` |
| `research/r106i/traversal.json` | 11,246 | `5767ec10cbc8cfb16429310e35e03e0adc85d346eb26c83db2d0c96ab341a6f9` |

Reproduce:

```
python3 research/r106i/census.py      # BINDING  -> research/r106i/binding.json
python3 research/r106i/traversal.py   # TRAVERSAL-> research/r106i/traversal.json
```

Per rule 58 the census *extends* the existing tracer: `traversal.py` imports
`FAMILIES`, `family`, `parse_args`, `parse_bufs` from `census.py` rather than
re-deriving the classifier, and both read the committed R106-G ledger.

### 2.5 The PR91 "bound bytes" convention is neither BINDING nor TRAVERSAL

Worth stating up front because the 30.961 GB number is quoted widely.
`research/pr91-gpuprof-hook.patch:89-94,145-148` accumulates
`profile_nbytes_ += a.nbytes()` inside `set_input_array`, guarded by
`all_inputs_.insert(a.buffer().ptr()).second`, and resets in `commit()`.
So the published 30.961 GB is **inputs only, outputs excluded, deduplicated
per command buffer** — 81 command buffers for 1220 dispatches. It is neither
of my two quantities and it systematically undercounts. My BINDING figure
(31.3640 GB) charges inputs **and** outputs per dispatch, which is why it is
slightly larger despite counting the same physical operands.

---

## 3. The traversal model

For each dispatch, every distinct bound pointer is one *operand* with a
*footprint* (its bound byte length) and a *multiplicity*. BINDING charges
footprint × 1; TRAVERSAL charges footprint × multiplicity. Read-modify-write
is charged once on both sides, so **TRAVERSAL/BINDING is a pure read
multiplicity ratio** with no convention drift.

Default multiplicity is 1. Rules that override it, each read out of MLX
source, not fitted:

**steel GEMM** — grid `(N/bn, M/bm, sk)`. Every n-tile column re-reads the
whole A panel and every m-tile row re-reads the whole B panel, so
`mult(A) = grid.x`, `mult(B) = grid.y`, `mult(out) = 1`. Split-K does not
change either: block `(tn,tm,sk)` touches `A/(grid.y·grid.z)` and
`B/(grid.x·grid.z)` bytes, and the products telescope back to `grid.x` and
`grid.y`.

**M5 substitution** — the ranked M5 selects `steel_matmul_regular_axpby_nax`
with `bm=64, bn=128` (`matmul.cpp:212-221`), and **never runs split-K**
(`matmul.cpp:899-901` requires `!use_nax`). So on M5 I recompute
`mult(A) = ceil(N/128)`, `mult(B) = ceil(M/64) = 8`, discarding the traced M4
grid. `is_nax_available()` needs macOS ≥ 26.2 *and* GPU generation ≥ 17
(`device.cpp:913-931`); this host reports `applegpu_g16s`, generation 16, so
every M5 row in this report is `[PROJ]`, never `[M4-WALL]`.

**gather GEMM** — `mult(x) = N/bn`; `mult(weight) = incidences / 256`, where
an *incidence* is one (threadgroup, expert) pair that must fetch weight bytes.
Derivation in §7.

**`nvfp4_qmm_t`** — same tile logic as steel: `mult(weight) = ceil(M/bm)`,
`mult(x) = ceil(N/bn)`, with `bm=bn=32` measured on M4 and `64` projected for
M5.

**causal `steel_attention`** — with `bq=32`, q-tile `j` reads
`min((j+1)·32, Lk)` key rows, so `krows = Σ_j min((j+1)·32, Lk) = 4352` for
`Lq=Lk=512`. Each of the `H` query heads walks its own KV head, and the bound
KV buffer holds `Hkv·Lk` rows, giving `mult(K) = mult(V) = H·krows/(Hkv·Lk)` =
**68.0** for the 64-head layers and **51.0** for the 48-head layers.
`mult(Q) = mult(out) = 1`.

**`gather_front`** — only gathered rows are read:
`mult(table) = out_bytes / table_bytes`.

**final-layer fused decode-form kernels**
(`routed_nvfp4_swiglu_qmv_packed_top8keys`,
`routed_shared_nvfp4_down_residual`) — they *bind* the whole 256-expert routed
tensors but touch top-8, so large inputs get `mult = 8/256`.

**lm_head exact rescore** (`lmhead_exact_winner`,
`lmhead_exact_inline_mask_block_delta`) — they bind the full
`bfloat16[100352,2048]` head but visit only surviving rows, so
`mult = rows·2048·2 / 411,041,792` with `rows = 128`. §9 brackets `rows` to the
whole vocabulary as the rule-79 null cell.

**Reuse bracket.** `ordered` assumes x-fastest threadgroup issue, so a GEMM
weight panel is re-fetched once per m-tile — the **upper** bound. `coresident`
assumes the whole grid is in flight and the weight panel is fetched once — the
**lower** bound. Activation multiplicity is retained in both, because the A
panel is genuinely re-walked per n-tile column under either schedule.

**Above-SLC.** A buffer-granular LRU of capacity `SLC` (24 MiB default) sits in
front of DRAM. A buffer larger than the cache is streamed and charged in full
at every traversal; smaller buffers are charged only on a miss. The streamed
buffer is assumed **not** to flush the resident set, because the routed weight
stream is consumed tile-by-tile with expert-local reuse far below buffer
granularity. §8 sweeps the capacity from 8 to 96 MiB as the sensitivity
bracket for that assumption.

---

## 4. B_pre — the BINDING census

**B_pre = 31.3640 GB** for one 512-token prefill forward, **61.258 MB/token**
[STRUCT]. At 546.2 GB/s that is a **57.42 ms** [PROJ] compulsory-read floor if
nothing were ever re-read and nothing were ever cached — a useful anchor
against `S = 97.89475 ms` [M5-RCPT].

BINDING is host-independent: it is a property of the operands the graph binds,
not of which kernel variant consumes them.

---

## 5. Per-family census — all twelve families

Classifier: the twelve-family ordered regex of
`research/prefill_probe.py:109-124` (the ordering is load-bearing — `rope`
must beat `rms`), with the `other` fallback at `:127-132`.

**M5 [PROJ], SLC 24 MiB.** `TRAV` and `T/B` show `ordered | coresident` where
the two differ.

| family | n | BIND GB | TRAV GB | T/B | aSLC GB | S/B |
|---|---:|---:|---:|---:|---:|---:|
| routed_gather_gemm | 76 | 18.9679 | 30.9964 | 1.634 | 15.8717 | 0.837 |
| steel_gemm_bf16 | 394 | 5.0056 | 39.2079 \| 16.0932 | 7.833 \| 3.215 | 18.2404 \| 3.9127 | 3.644 \| 0.782 |
| elementwise | 235 | 1.6500 | 1.6500 | 1.000 | 0.6426 | 0.389 |
| sort_scatter | 153 | 1.1347 | 1.2836 | 1.131 | 0.6448 | 0.568 |
| lm_head | 4 | 0.9588 | 0.1377 | **0.144** | 0.1367 | 0.143 |
| moe_tail | 38 | 0.8779 | 0.8779 | 1.000 | 0.2403 | 0.274 |
| nvfp4_dense_qmm | 117 | 0.7956 | 2.4103 \| 1.5212 | 3.029 \| 1.912 | 0.3059 | 0.384 |
| qk_norm_rope | 41 | 0.7676 | 0.7676 | 1.000 | 0.4299 | 0.560 |
| attention_core | 40 | 0.6973 | 5.8207 | **8.347** | 0.3471 | 0.498 |
| rms_norm | 83 | 0.4974 | 0.4974 | 1.000 | 0.3307 | 0.665 |
| router | 39 | 0.0112 | 0.0112 | 1.000 | 0.0013 | 0.114 |
| **other** | **0** | **0** | **0** | **—** | **0** | **—** |
| **TOTAL** | **1220** | **31.3640** | **83.6607 \| 59.6570** | **2.667 \| 1.902** | **37.1915 \| 22.8638** | **1.186 \| 0.729** |

`other` is an explicit **null cell**: with the trace's exact kernel names every
dispatch in the window classifies, so the fallback bucket is empty. Prior art
reports `other` with n=3 / 0.211 GB / 0.309 ms because its window is the full
1222-dispatch command-buffer span rather than my 1220-dispatch forward. That
three-dispatch difference is small in bytes but it is the hinge of the
re-adjudication in §6.

**M4 [STRUCT] geometry, same operands.**

| family | n | BIND GB | TRAV GB (ord \| cores) | T/B |
|---|---:|---:|---:|---:|
| routed_gather_gemm | 76 | 18.9679 | 62.0518 | 3.271 |
| steel_gemm_bf16 | 394 | 5.0056 | 59.9099 \| 30.8467 | 11.969 \| 6.162 |
| nvfp4_dense_qmm | 117 | 0.7956 | 4.7014 \| 2.7963 | 5.909 \| 3.515 |
| all others | 633 | 6.5949 | 10.9462 | 1.660 |
| **TOTAL** | **1220** | **31.3640** | **137.7093 \| 106.7409** | **4.391 \| 3.403** |

M4 above-SLC total is 51.8208 \| 37.4930 GB. The **2.03× M4/M5 divergence on
the largest byte pool** (routed_gather_gemm 62.05 GB vs 31.00 GB) is exactly
why an M4 prefill wall-clock is not evidence for an `_nax` change, and why
every ranked-relevant row here is `[PROJ]`.

---

## 6. Re-adjudication (a): the glue-class "99 % of floor" verdict

Prior art (`research/maple-tanjiro-nonmoe-prefill-census.md:448-455`, SPLIT=1
trace `research/pr270-logs/split1.worker.err`) sums a "glue class" of
4.34 GB, divides by 546.2 GB/s to get a **7.94 ms** floor, compares with an
**8.04 ms** projected time, and concludes the class already runs at 99 % of
its DRAM floor — i.e. nothing to win.

**Defect 1 — the byte sum and the time sum use different class membership.**
The 4.34 GB is elementwise 1.60 + sort/scatter (in-forward) 0.687 + moe_tail
0.837 + qk_norm_rope 0.730 + rms_norm 0.472 + router 0.011. The 8.04 ms is the
sum of the per-family times at `:377-384`, which **includes** `other`
(0.15 ms), per the class definition at `:362-364`. So `other` is excluded from
the bytes and included in the time. Repair it either way and the claim breaks:

- Drop `other` from the time: 8.04 − 0.15 = **7.89 ms**, which is *below* the
  7.94 ms floor the same document computes. Physically impossible.
- Add `other`'s bytes (0.211 GB, `research/pr91_byte_crosscheck.py:47`):
  floor becomes 4.551/546.2 = **8.33 ms**, which is *above* the 8.04 ms
  projected time. Also physically impossible.

There is no membership choice under which the published pair is consistent, so
the 99 % figure is not a measurement of anything.

Three further unresolved defects in the same passage: the "(in-forward)"
sort/scatter figure of 0.687 GB is never reconciled with PR91's 1.135 GB for
the same family; the cited source table `PREFILL_NAX_ANALYSIS.md §6.2`
(`:429`) **does not exist** — the real table is
`research/maple-tanjiro-pr91-prefill-budget-census.md:618-637`; and the class
total is quoted as 8.34 ms at `:363/406/497` but 8.04 ms at `:438/569`.

**Defect 2 — the floor itself is wrong, because binding ≠ traversal ≠ DRAM.**
On my per-dispatch accounting the same six families are:

| quantity | GB | ms @546.2 GB/s |
|---|---:|---:|
| BINDING | 4.9388 | 9.04 |
| TRAVERSAL (M5) | 5.0877 | 9.31 |
| **above-SLC (M5, 24 MiB)** | **2.2896** | **4.19** |

The glue class is almost entirely small, short-lived activation buffers. Its
traversal multiplicity is 1.030 — it genuinely does not re-read anything — but
**more than half of its bytes never reach DRAM at all**, because the buffers
are produced and consumed inside the SLC. Its true DRAM floor is **4.19 ms**
[PROJ] (bracket 3.99–7.25 ms over 8–96 MiB, §8; identical under both reuse
modes, since the class contains no large GEMM panel), against **8.04 ms**
[PROJ] of projected time.

**Verdict: the glue class runs at ≈ 1.9× its DRAM floor, with ≈ 3.85 ms of
headroom — not 1 %.** The prior verdict was an artefact of charging BINDING
bytes as if they were DRAM bytes.

This does *not* say the 3.85 ms is recoverable: at 235 + 153 + 83 + 41 + 38 +
39 = 589 dispatches for 4.94 GB of bound operands, the class is dispatch- and
latency-bound, and that is tanjiro's time-side question, not mine. What the
census establishes is only that **a DRAM floor is not the reason it is
slow**, so "glue is already at its floor" must be retired as a reason to stop
looking.

---

## 6b. Re-adjudication (b): the `lm_head` M/A = 2.333 outlier

`lm_head` shows measured-over-analytic 2.333 — the largest ratio in the
crosswalk — which has been read as evidence of hidden traffic. It is a
**pure binding artefact**. The four dispatches are rows 7331–7334:

| row | kernel | binds | reads |
|---|---|---|---|
| 7331 | `lmhead_int5_inline_coarse_ratio_bound_delta` | uint8`[100352,1024]` 102.76 MB + uint8`[100352,256]` 25.69 MB + uint8`[100352,64]` 6.42 MB + float32`[100352]` 0.40 MB ≈ **134.9 MB** | hierarchical INT5 bound tables, 1344 B/row vs 4096 B/row for BF16 |
| 7332 | `lmhead_coarse_argmax_stage1` | 0.40 MB | reduction |
| 7333 | `lmhead_exact_winner` | bfloat16`[100352,2048]` = **411,041,792 B** | grid 32×1×1 — **one 32-thread threadgroup** |
| 7334 | `lmhead_exact_inline_mask_block_delta` | the same 411 MB head | surviving rows only |

Rows 7333 and 7334 each *bind* the whole 411 MB BF16 head, which is where the
0.9588 GB of binding comes from, but 7333 launches a **single threadgroup**:
it cannot read 411 MB. Charging traversal instead gives **0.1377 GB, T/B =
0.144** — *below* even the 0.411 GB A-side estimate, which is why the ratio
looked anomalous in the first place. The INT5 hierarchy already replaced the
BF16 head; the crosswalk was still comparing against a BF16 head that is bound
but not read.

**M/A = 2.333 is an accounting artefact of binding-based measurement, not
hidden traffic. There is no lm_head byte problem in prefill.**

## 6c. Re-adjudication (c): the `shared_expert` M/A = 2.218 outlier

Also an artefact, of *family attribution* rather than of binding. The 2.218 is
the `nvfp4_dense_qmm` M-side (0.652 GB) divided by the A-side `shared_expert`
stage (0.069 GB weights + 0.225 GB activations = 0.294 GB). But the
`nvfp4_dense_qmm` family contains two dispatches that have nothing to do with
the shared expert: rows 7328 and 7329 are the **final layer's decode-form
fused routed kernels**
(`routed_nvfp4_swiglu_qmv_packed_top8keys`, `routed_shared_nvfp4_down_residual`),
binding 285,225,112 B and 143,181,120 B respectively — together **428.4 MB, or
54 % of my whole 0.7956 GB `nvfp4_dense_qmm` binding** — while traversing only
the top-8 of 256 experts (3.1 %).

They land in the dense/shared bucket because the classifier keys on
`nvfp4_qmm`/`swiglu_qmv`/`nvfp4_down_residual`, and they exist because prefill
only needs the *last* token's logits, so the final MoE layer is executed at
M = 1 in decode form (§7). **M/A = 2.218 is 54 % misattributed routed
binding.** The shared expert itself is unremarkable.

---

## 7. Expert-weight-set traversal multiplicity

The single largest byte pool in prefill. Per-layer full expert set is
`1,769,472 × 256 = 452,984,832 B`, confirmed operand-by-operand against trace
row 6155/6164: gate/up `wq` 268,435,456 + `sc` 33,554,432, down `wq`
134,217,728 + `sc` 16,777,216 [STRUCT].

**The layer count is 38, not 39.** Config has 40 layers with layer 0 dense, so
39 MoE layers — but the trace shows `routed_gather_gemm` n = **76 = 38 × 2**
and `moe_tail` n = **38**, while `router` n = 39. Rows 7325–7329 show the final
MoE layer executed in decode form at M = 1, because prefill only needs the last
token's logits. Prior art's `× 39`
(`research/maple-tanjiro-pr91-prefill-budget-census.md:548,575`) therefore
inflates by 39/38 = **+2.6 %** before any other correction.

Resident set actually bound across the window: `452,984,832 × 38` =
**17.2134 GB**.

**M5 traversal.** `GatherQMM::eval_gpu` takes the sorted path
(`quantized.cpp:1878-1880`) → `gather_qmm_rhs_nax` (`:1644-1662`) →
`fp_gather_qmm_rhs_expert_nax`. Tiles at `:1361-1372` with
`darkbloom_stage_bm128_variant()` defaulting to 5 (`:1234-1240`) give
**BM=64, BN=64, BK=64, WM=4, WN=1**. All `expert_aligned` preconditions hold
(`:1379-1383`), and `DARKBLOOM_EXPERT_ALIGNED_GATHER` is ON by default
(`Sources/MLXFastModel/LagunaRuntimeModel.swift:255`,
`quantized.cpp:1204-1207`). The grid at `:1603-1609` is
`group(32, wn, wm)`, `grid(N/bn, egroups=256, 1)` — **`grid.y` is the expert
id**. With `experts/expert_groups == 1` there is exactly one expert per
threadgroup (`fp_quantized_nax.h:1789-1795`); the row interval comes from
`laguna_sorted_lower_bound` (`:1804-1806`) and the chunk loop is at
`:1815-1823`. **No threadgroup ever spans two experts**
(`fp_quantized_nax.h:1663-1673`), and an expert with zero rows costs zero
weight traffic. There is no split-K on the gather path (`grid.z` is always 1).

So weight incidences per layer are `Σ_e ceil(rows_e / 64)`. From the committed
routing histogram (`research/artifacts/route-histogram-prefill512.json`;
38 MoE layers × 256 experts, 4096 rows/layer) that sum is **8379 over 38
layers = 220.50 per layer**, against 256 slots:

```
mult_M5 = 220.50 / 256 = 0.8613
        = 0.7974 (non-zero-row fraction) × 1.0802 (BM=64 chunk rounding)
```

Weight traversal = `8379 × 1,769,472` = **14.8264 GB** [PROJ], i.e. **0.8613×**
the resident 38-layer set and **0.8392×** prior art's 17.666 GB. Whole-family
above-SLC cost is **15.8717 GB = 29.06 ms** [PROJ] against the published
**35.64 ms** (`…pr91-prefill-budget-census.md:617,623`): **−6.58 ms,
−18.5 %**. At the campaign's 0.3781 %/ms that is ≈ 2.5 points of score that the
published floor was pricing as already spent.

**M4 traversal, for contrast.** `nvfp4_gather_qmm_rhs_nt` uses `bm=16` and its
`grid.y` is not an expert id, so threadgroups straddle expert boundaries:
`incid = ceil(4096/16) + (204.13 − 1) × 15/16 = 446.44`, i.e. **1.7439×**.
Weight traversal 62.05 GB against 31.00 GB on M5 — a 2.0× gap on the same
weights, from the kernel alone.

**Routing histogram provenance and its caveat.** `README-route-histogram.md:86-94`
(probe PR #11, since reverted): zero-row `(layer, expert)` pairs =
**1971 / 9728 = 20.26 %**; chunk histogram `0:1971, 1:7336, 2:301, 3:71, 4:32,
5:10, 6:2, 7:2, 8:3`; `rows_e > 64` for 421/9728 = 4.328 % of pairs holding
31.91 % of rows. `:106-108` records the caveat I carry forward: **M4 Pro,
single prompt, one draw**, and there is a provenance conflict between commit
`3e8e435` and `ceff917`/`research/maple-fern-prefill-roofline.md:216`. Only
`research/prefill_ridge.py:112-117` currently applies the `(1 − 0.2026)`
discount; the budget census does not. **A second draw on a different prompt
would tighten the −6.58 ms, and I recommend it before anyone spends
engineering on the residual.**

**V-REREAD, weight side: refuted on M5.** Multiplicity is *below* 1. A
`pairwise_scale_layout` bracket makes it slightly better still: it is on by
default and halves M5 scale reads (`fp_quantized_nax.h:314-318`), worth a
further ≈ −5.6 %; I keep the 0.5625 B/element headline and flag it rather than
bank it.

**V-REREAD, activation side: real but absorbed.** `mult(x)` is 16 for gate/up
and 32 for down, i.e. **15.2 GB of activation re-reads per forward at 8.5×
multiplicity**. But the co-scheduled threadgroups for one expert share a row
slice of only `rows_e × 2048 × 2 B` ≈ 64 KB (grid.x is fastest-varying, so all
n-tiles of one expert are in flight together), and the whole `x` buffer is
4–17 MB against a 24 MiB SLC. Its above-SLC contribution is **0**. This is the
one place where the buffer-granular model would be badly wrong if the routed
weight stream flushed the cache; §8 brackets it.

---

## 8. Above-SLC bracket and sensitivity

M5, above-SLC floor in ms at 546.2 GB/s, `ordered | coresident`:

| SLC MiB | total | glue class | routed experts |
|---:|---:|---:|---:|
| 8 | 97.61 \| 64.93 | 7.25 \| 7.25 | 47.70 \| 47.70 |
| 16 | 76.04 \| 43.36 | 4.56 \| 4.56 | 30.23 \| 30.23 |
| **24** | **68.09 \| 41.86** | **4.19 \| 4.19** | **29.06 \| 29.06** |
| 48 | 42.00 \| 42.00 | 4.04 \| 4.04 | 29.38 \| 29.38 |
| 96 | 41.72 \| 41.72 | 3.99 \| 3.99 | 29.38 \| 29.38 |

Both conclusions are robust across the whole sweep: the routed-expert floor
never approaches 35.64 ms above 8 MiB, and the glue floor never approaches
8.04 ms at any capacity. The `ordered`/`coresident` split collapses at 48 MiB
because a 33.55 MB BF16 weight panel becomes cache-resident and the re-read
stops reaching DRAM — which is itself the clearest statement of why prefill
GEMM weight re-reads are a *cache* question, not a *DRAM* question, on M5.

Summary brackets for the whole prefill forward, M5 [PROJ]:

| quantity | value | per token |
|---|---|---|
| BINDING | 31.3640 GB | 61.258 MB |
| TRAVERSAL | 59.6570 – 83.6607 GB | 116.518 – 163.400 MB |
| above-SLC | 22.8638 – 37.1915 GB | 44.656 – 72.640 MB |
| **TRAV / BIND** | **1.902 – 2.667×** | |
| **aSLC / BIND** | **0.729 – 1.186×** | |
| above-SLC floor | 41.86 – 68.09 ms | |
| measured `S` | 97.89475 ms [M5-RCPT] | |

The floor sits strictly below the measured prefill wall in every cell of the
bracket, as it must; the model is not producing an impossible number anywhere.

---

## 9. Null cells and brackets (rule 79)

1. **`other` family, n = 0** (§5). Reported explicitly rather than dropped,
   because its absence from my window versus its presence in prior art's is
   the hinge of §6.
2. **lm_head exact-rescore survivors.** The 128-row assumption is a model
   input, so I bracket it to the whole vocabulary:

   | surviving rows | lm_head TRAV | TOTAL TRAV |
   |---:|---:|---:|
   | 128 | 0.1377 GB | 83.6607 GB |
   | 100352 (all) | 0.9588 GB | 84.4818 GB |

   The total moves by 0.98 %, so no conclusion in this report depends on it.
3. **SLC capacity**: §8, 8–96 MiB.
4. **`pairwise_scale_layout`**: a further ≈ −5.6 % on M5 routed scale reads,
   flagged and *not* banked.
5. **Reuse schedule**: `ordered`/`coresident`, reported as a bracket in every
   table rather than collapsed to a point estimate.

---

## 10. Unattributed share

Naming it precisely, because the assignment asks for it:

- **Byte-side unattributed: 0.** Every one of the 1220 dispatches in the
  window classifies into one of the twelve families, and every bound pointer
  of every dispatch is charged. There is no residual byte bucket.
- **Time-side unattributed: 22.9 – 37.9 ms, central 27.88 ms** [PROJ] — the
  gap between `S = 97.89475 ms` [M5-RCPT] and the prior-art per-stage floor
  sum of 70.07 ms. My census *widens* it: against my above-SLC floor of
  41.86–68.09 ms the unattributed share becomes **29.8 – 56.0 ms**, i.e. 30 %
  to 57 % of measured prefill is not explained by DRAM traffic of any kind.
- **The named cause of that widening is not new traffic; it is that two
  published floors were too high** (§6, §7). Together the two corrections move
  **6.58 ms (routed experts) + 3.85 ms (glue)** of previously-"spent" budget
  into the unattributed pool.

The census cannot say what fills that pool. Structural evidence already on
record points away from bandwidth: non-GEMM work is 8.5 % of M4 busy time,
prefill runs 81 command buffers with 671 barriers for 1220 dispatches, and the
glue class needs 589 dispatches to move 4.94 GB. Attribution of that time is
tanjiro's R106-H scope, and I deliberately stop here.

---

## 11. Caveats carried forward from #619, re-signed for prefill

1. **The tracer drops the `offset` argument, hiding sub-buffer slicing.**
   `write_ranges` emits `ptr+offset:bytes`, but `parse_bufs` keys on `ptr` and
   takes `max(bytes)`, so two disjoint slices of one allocation are merged into
   the larger. **Sign for prefill: BINDING is over-stated, TRAVERSAL/BINDING is
   under-stated.** Magnitude is small here — the routed weights, the BF16 GEMM
   panels and the attention KV blocks are all whole allocations — but the
   split-K partial buffers (`float32[2,512,1024]`, 155 dispatches) are exactly
   the kind of operand that gets sliced. Worst case this misprices ≈ 0.8 GB of
   the 31.36 GB BINDING total, or 2.6 %, and it does not touch M5 at all
   because M5 never runs split-K. Fixing it is a one-line change to
   `trace_dag.patch` (key on `(ptr, offset)`); I did not make it because it
   would invalidate the committed ledger's hash for a 2.6 % worst-case effect
   on a number that is not load-bearing for any verdict here.
2. **The MLX allocator recycles pointers.** Two logically distinct buffers can
   share a pointer across the window. BINDING and TRAVERSAL are immune (they
   charge per dispatch), but the above-SLC LRU keys on `(ptr, nbytes)` and will
   therefore score a *recycled* pointer as a cache hit when it is really new
   data. **Sign for prefill: the above-SLC column is a lower bound.** This
   pushes in the *conservative* direction for both of my verdicts — a higher
   glue floor and a higher expert floor would both weaken V-FLOORS-INFLATED —
   so both survive the caveat. The 8 MiB row of §8 is the practical stress
   test: even there the glue floor is 7.25 ms against 8.04 ms projected, and
   the expert floor is 47.70 ms, which exceeds 35.64 ms only because a 8 MiB
   cache cannot hold anything at all.

---

## 12. Prior art (rule 83)

- `research/maple-tanjiro-pr91-prefill-budget-census.md:548,575,617,623,618-637`
  — the A-side stage budget and the per-stage floors, including the 35.64 ms
  routed-expert floor and the `× 39` layer count corrected in §7.
- `research/maple-tanjiro-nonmoe-prefill-census.md:362-364,377-384,406,429,438,448-455,497,569`
  — the glue-class verdict re-adjudicated in §6, and the dangling
  `PREFILL_NAX_ANALYSIS.md §6.2` citation.
- `research/maple-tanjiro-r103b-kernel-text-differential.md:1174-1187` — the
  advisor's correction of the page-flush truncation that produced the
  "tracer quota" premise (§2.2).
- `research/pr91-gpuprof-hook.patch:89-94,145-148` and
  `research/pr91_byte_crosscheck.py:47` — the bound-bytes convention (§2.5).
- `research/artifacts/route-histogram-prefill512.{csv,json}`,
  `research/README-route-histogram.md:86-94,106-108` — the routing histogram
  and its single-draw caveat (§7).
- `research/prefill_probe.py:109-124,127-132` — the twelve-family classifier.
- `research/prefill_budget.py`, `research/prefill_ridge.py:29,112-117`,
  `weights/config.json:38-53` — model constants and the only existing use of
  the 20.26 % discount.
- `research/maple-fern-prefill-roofline.md:216` — the histogram provenance
  conflict.

Standing negatives this census does **not** disturb: N-axis weight re-read is
refuted; expert pruning ≈ 0; MMA row inflation ≈ 0 ms; `egroups = 256` is
optimal; the 20.26 % zero-row fraction is a scheduler-slot cost, not (by
itself) a byte cost — §7 shows it *is* a byte cost only because the M5 kernel
is expert-aligned.

---

## 13. What this does and does not license

- It **does** retire "the glue class is at 99 % of its DRAM floor" and "the
  routed-expert weight floor is 35.64 ms" as reasons to stop looking.
- It **does not** identify a mechanism, and no mechanism arm was run. Turning
  either correction into score requires a separate assignment with its own
  revision.
- Every M5 number is `[PROJ]` from source-read geometry. This host is
  generation 16, so no `_nax` kernel is reachable and no M4 wall-clock in this
  report is offered as an M5 cost. Rule 86 applies: no `--local-iterate` delta
  appears here as evidence, because none was run.

**Suggested follow-ups (not implemented):**

1. Re-draw the routing histogram on a second prompt and a second seed to
   retire the single-draw caveat before anyone prices the −6.58 ms.
2. Key the tracer on `(ptr, offset)` and re-capture, which would also let a
   future census separate KV-cache slices from their backing allocation.
3. Ask whether the 589-dispatch glue class can be fused: the census now says
   its DRAM floor is 4.19 ms against 8.04 ms of time, so the headroom is real
   even though the mechanism is dispatch overhead rather than bandwidth. That
   is a time-side question and belongs with R106-H.
