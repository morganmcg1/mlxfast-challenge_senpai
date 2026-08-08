# Research ideas — 2026-08-08 21:40 UTC (round 87b)

Base at time of writing: `BASE_SHA = 7687c2e44e6975c181444ca8d3d151ee30480a72`
(advisor branch head `c15740be88db6e9164b06a72914331d7a406d409` is this base
plus a research-only Markdown commit).

Two delegated agents ran this round: a frontier-model **byte-budget audit** of
the decode step, and a **literature survey** on batch-1 4-bit MoE decode on
Apple Silicon. This file records what they produced, what was falsified, and
the resulting ranked queue.

---

## 1. Headline: the decode byte census, and why "run faster on the same bytes" is finished

Theoretical minimum DRAM traffic for one decode step, derived from the shipped
representation (not from a timer):

| Class | Bytes/layer | Layers | Bytes/step |
|---|---|---|---|
| QKV sliding (80·128·2048 @4b + 665,600 scale) | 11,151,360 | 30 | 334.5 MB |
| o_proj sliding (2048·8192) | 8,914,944 | 30 | 267.4 MB |
| QKV full (8192·2048) | 8,921,088 | 10 | 89.2 MB |
| o_proj full (2048·6144) | 6,686,720 | 10 | 66.9 MB |
| `g_proj` (INT8 g32) | 147,456 / 110,592 | 30 / 10 | 5.5 MB |
| **Attention subtotal** | | | **763.5 MB** |
| Routed gate+up, top-8 | 8,912,896 | 39 | 347.6 MB |
| Routed down, top-8 | 4,456,448 | 39 | 173.8 MB |
| Shared expert g/u/d | ~1,769,472 | 39 | 69.0 MB |
| **MoE subtotal** | | | **590.4 MB** |
| Router (BF16 256·2048) | 1,048,576 | 39 | 40.9 MB |
| Dense L0 MLP (BF16) | 100,663,296 | 1 | 100.7 MB |
| LM head (int5 screen, 1088 B/row × 100,352) | — | 1 | ~111 MB |
| KV sliding read (512·1024·2·2) | 2,097,152 | 30 | 62.9 MB |
| KV full read (N = 512+t) | 2,359,296 | 10 | 23.6 MB |
| Embedding + norms + KV write | — | — | ~0.5 MB |
| **TOTAL** | | | **≈1.69 GB/step** |

Supporting sites: `LagunaRuntimeWeights.swift:693–706`,
`LagunaRuntimeModel.swift:2903–2984`, `:437–470`, `:150–166`,
`LagunaLmHeadPrune.swift:1–100`.

Weights-only pool ≈1,606 MB. Note that lm_head kept as BF16 would be
**411.0 MB**; the shipped int5 screen already removed ~300 MB. That was the
single largest byte win available on this model and it is already banked.

**Amplification over the census is ≈1.0×.** The audit checked six candidate
sources of over-read and found essentially nothing left:

1. **Expert gather** reads only the 8 selected banks. Decode dispatches
   `laguna_routed_nvfp4_swiglu_qmv_packed_top8keys_r1_bf16_v2`
   (`LRM:7546`) against per-layer fused `[gate;up]` banks (`LRM:201–217`) plus
   a fused down+residual kernel (`LRM:137–144`). Prefill is different (the
   gather-GEMM touches ~86.1 % of expert bytes) — that is a **prefill-only**
   lever.
2. **Scale metadata** is already near its floor: stock NVFP4 g16 costs 12.5 %
   of payload; the lane-major/halved banks cut attention to ~6.3 % and routed
   to ~6.25 %. The shared-expert gate/up plane still pays full 128 B/row
   (`LRM:6825–6828`) and halving it measured **+1.93 % WORSE** (PR #301
   mechanism (b)) because those reads are cache-served.
3. **No grid-decomposition weight re-reads** — the decomposition is
   row-partitioned, each weight byte is fetched once. The 4 KB input vector is
   re-read per threadgroup but is SLC-served.
4. **No KV over-read.** Sliding is exactly 512 (`constexpr N = 512`, decl
   `LRM:1369–1370`, wrapper `:1719–1765`); full is exactly `N = 512+t` (grow
   kernel `:1818–1819`, wrapper `:2220–2266`). Byte-exact.
5. Remaining glue operands are KB-scale — they cost **latency**, not bytes.
6. No dequant scratch reaches DRAM; NVFP4 decode is in-register.

The one real re-read pathology is **instruction-side**: the fused
RMSNorm→QKV producer re-executes the norm once per consumer threadgroup
(+308.3 µs redundant at 5120 TGs).

Marginal-bandwidth probes show several planes price *above* DRAM peak
(lm-head 968.4 GB/s, attention scale 524.1, pairwise 463.5), i.e. partially
SLC-served, so true DRAM traffic is ≈**1.42–1.50 GB** of the 1.69 GB census.

### Reconciliation with the 8,234 µs M4 Pro step

- **Weight streaming ≈5,700–5,900 µs (~70 %)** — bandwidth-bound, kernels
  already at **86.9–98.2 %** of the achievable 239.7 GB/s (qkv_h64 268.2,
  oproj 237.3, dense bf16 249–250, routed 243–248 GB/s). Byte floor ≈5,582 µs,
  so **≈338 µs of headroom exists even at 100 % of peak**. This pool is
  finished for "run faster on the same bytes".
- **Fused SDPA ≈880 µs (~10.5 %)** — issue/latency-bound (KV bytes 86.5 MB is
  only ~360 µs at achievable bandwidth; the k-loop is at ~90 % of its issue
  floor). Family remains CLOSED.
- **Glue ≈640 µs (~7.6 %)** — latency-bound, floor ≈152 µs.
- **Boundaries/gaps ≈25–450 µs** — 45 command buffers × 0.54 µs ≈ 24 µs;
  intra-CB shadowing already harvested.

---

## 2. ⚠️ The doctrine this forces: declare a mechanism class for every decode lever

The reconciliation above is an **M4 Pro** statement. Our own records say the
ranked M5 Max is in a different regime:

- M5 Max is **instruction-bound during decode at ~89 % GPU utilization**.
- PR #137 measured **−63.7 µs/token on M4 → +24.6 µs/token on M5** (receipt
  `99b71258`), transfer factor **−0.40 ± 0.24**; the pre-registered honest
  0.50–0.75 band was excluded.
- A competitor landed **15 validated bit-exact byte optimisations and measured
  +233.8 µs/token SLOWER on M5**.

⇒ The byte-price law (`0.015280 × MB / R_marg` % score) is an **upper bound on
the ranked host, not a prediction.**

**Binding rule going forward:** every proposed decode lever must state its
mechanism class.

- **Instruction / latency class** (redundant work removal, issue-rate,
  scheduling, dispatch latency, load pipelining): privileged for decode; the
  M5 prior is favourable because M5 is instruction-bound.
- **Byte class** (fewer DRAM bytes at constant instruction count):
  presumptively **non-transferable** to M5. Spend byte levers on the **prefill
  axis**, where the regime argument does not bite the same way and the axis is
  still scored at weight 0.25.

---

## 3. Falsified this round: "add an `_nax` M=1 qmv kernel"

The literature survey's #1 recommendation was that `fp_quantized_nax.h` has no
`qmv` kernel, so M5 decode must be running a matrix-matrix kernel at M=1.

The **premise is true** — the only `[[kernel]]` entries are `fp_qmm_t_nax:1011`,
`fp_qmm_t_nax_static:1073`, `fp_qmm_n_nax:1134`, `fp_gather_qmm_t_nax:1193`,
`fp_gather_qmm_n_nax:1258`, `fp_gather_qmm_rhs_nax:1326`,
`fp_gather_qmm_rhs_expert_nax:1690`. Zero `qmv`.

The **conclusion is false**, twice over
(`Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/quantized.cpp`):

- `QuantizedMatmul::eval_gpu` (`:2184–2217`) takes the matmul branch only when
  `M >= vector_limit`, and `get_qmv_batch_limit` (`:88–129`) returns **≥10 in
  every branch**. At M=1 MLX already falls through to `dispatch_qmv`.
- `GatherQMM::eval_gpu` (`:2258–2338`) needs `M == 1 && B >= 16 &&
  right_sorted_ && B/E >= 4` for `sorted_rhs`; decode top-8-of-256 gives B=8,
  so it goes to `gather_qmv`. (`pairwise_contract` at `:2263–2268` also
  requires `sorted_rhs`, which independently confirms the adopted frontier's
  P2 pairwise-scale trick is **prefill-only**.)
- **Doubly moot:** the scored decode routed-MoE path does not call
  `MLX.gatherQuantizedMM` at all. `LRM:10700–10790` dispatches our own
  `lagunaRoutedSwiGLUQMVPackedTop8` / `…QMVPacked` /
  `lagunaRoutedSharedDownResidual`; `gatherQuantizedMM` at `:10742` is only a
  fallback.

Record as CLOSED.

---

## 4. Ranked queue (L1–L7)

**L1. Algebraic epilogue normalization at full grid coverage.** Remove the
fused norm→QKV producer's redundant cross-simdgroup reduction *algebraically*
while keeping the full 5120-TG grid (grid coarsening is dead: G128−G640 =
+174.9 ± 11.0 µs, #309). Site ≈ `LRM:4815–4881`. Ceiling ≈**140 µs/step
(≈2.14 % score)**; subsumes a measured unmerged sub-arm `N640−a0 = −33.7 ±
11.0 µs`. **Instruction class ⇒ best M5 prior.** Not automatically bit-exact —
reassociation must preserve reduction order (the uint2→uint4 widening was
killed for exactly this). Falsification <1 h: #309's 7-arm ABBA driver with
N640 as positive control + `research/run_upstream_equivalence.sh`.

**L2. Routed-twin K-block prefetch.** Port PR #301(a)'s one-K-block prefetch
from the shared QMV (`LRM:6844`) to the routed top8keys kernel (`LRM:7546`,
cf. `:7620–7630`). 39 dispatches × 38 µs/call at 8× the traffic; −0.363 µs/call
on the shared twin scales to ≈**−72 µs/step (−0.56 %)**. Latency-hiding,
byte-neutral, bit-exact (load scheduling only). **Best risk/reward on the
board.** Risk: #301's ABBA was ORDER-confounded (untouched control moved
−1.16 %) ⇒ run the reversed-ORDER separator first.

**L3. Threadgroup packing S=8 on the routed gate/up kernel.** #308 measured an
interior argmax at S=8 on QKV: −36.9 µs/step (CI −61.0…−12.9); the patch
already exists (+29 B, `research/tanjiro_packing_default_flip.patch`). The
audit's only PURSUE is extending the sweep to **site 1**, the routed gate/up
kernel at `LRM:7546` — the largest single kernel at 1,501.7 µs/step — at
S ∈ {2,4,8}. Bit-exact (row bijection). Risk: **rule 33** — the arm must carry
a `_sgN` kernel-name suffix or the pipeline cache poisons the A/B.

**L4. Prefill async-ladder stride/placement sweep.** One-literal, byte-neutral
edit at **`LRM:733`** removing ~34 of ~39 forced graph evals in prefill;
priced with the M5-measured **+27.177 µs/CB** ⇒ ≈0.93 ms off 97.9 ms prefill ⇒
**≈+0.34 % score on the prefill axis — sidesteps the decode transfer problem
entirely.** Bit-exact. Risk: M4 cannot rank it (0.037 %/receipt resolution) ⇒
needs ~3 M5 receipts. The +0.40 % doc-comment at `LRM:719` is folklore — do not
cite it. The **decode** ladder is do-not-retry (lone-fire arm scored 0.9476).

**L5. Full-attention SDPA N/capacity constexpr specialization.** The only
surviving SDPA sub-lever: bake N/capacity into function constants per growth
stage (the sliding twin is already `constexpr N=512`; the full kernel takes
runtime params at `LRM:2201–2220`). ≈**20–40 µs/step**, instruction class,
bit-exact. Risk: pipeline-count blowup × prewarm interplay (`LRM:2270–2293`).

**L6. Lossless entropy recode of the BF16 planes.** Dense-L0 100.7 MB +
routers 40.9 MB → per-group exponent base + 3–4-bit offsets, branchless decode
to identical BF16 bits; ≈35 MB removed ⇒ ≈+0.85 % **on M4 arithmetic**. The
only large envelope-legal byte lever left (lossy NVFP4 for these planes is
CLOSED). **Ranked low precisely because it is byte class.** Cheap
falsification first: offline exponent-entropy histogram of the 3 dense + 39
router tensors; kill if <15 % reduction.

**L7. Prefill `_nax` A-fragment N-tile reuse**
(`research/tanjiro-nax-kloop-pipeline.md:1080–1086`). Requested-byte reduction
in the prefill GEMM k-loop; must exceed ~1.35 ms for 3σ. Prefill axis ⇒
transfer-safe in principle, but **M4-blind** (`_nax` unreachable) ⇒ needs the
§5 safety rig (offline MSL compile check, kernel-selection assert). Highest
variance.

**Enabler, not a lever:** split `LagunaRuntimeModel.swift` into a second file
under `Sources/MLXFastModel/`. The per-file cap (511,418 / 524,288 B) is
binding and comment-stripping is dead (#320: 0 B net vs ≥18 KB bar). This is
exactly what **#456 (fern)** is doing.

**Explicitly not proposed** (closed with receipts): dense/router lossy NVFP4
(envelope), INT8 g32 attention (+805 MB/step vs shipped NVFP4), KV compression
(envelope), shared-scale halving (+1.93 %), lm-head screen thinning
(certificate at the boundary), the SDPA occupancy/split family, grid
coarsening, dispatch-count-only fusions, uint4 widening, and any whole-pool
"run faster on the same bytes" plan (338 µs total headroom at 100 % of peak).

---

## 5. Literature: what survived

- **Counter-premise corroborating our M5 finding.** Three independent measured
  sources say batch-1 4-bit decode is frequently dequant-ALU / occupancy
  limited rather than byte limited: arXiv 2605.30571 measures nf4 *slower*
  than fp16 and AWQ only 1.38×; IEEE 11368735 (RTX 3090, B=1) finds
  Transformers+AutoGPTQ 4-bit **1.3–2.2× slower than FP16**; LiquidGEMM
  (2509.01229) notes W4A8 ≈ W8A8 in memory-bound cases.
- **Every bit-exact scale-metadata win in the literature is an offline layout
  transform** (Marlin, Machete, QUICK, StreamDQ pseudo-channel co-location,
  PIM balanced placement, TileFuse, Opt4GPTQ VML-Opt) ⇒ maps to
  `Sources/MLXFastTransform/`. Ceiling is only ~11.1 % of quantized weight
  bytes, and `pairwise_scale_layout` in `QuantizedBlockLoader`
  (`fp_quantized_nax.h:211+`) already banked part of it.
- **CUTLASS example 55** (`fp8_packed_scale.hpp`, `unify_quant_encoding`,
  `initialize_packed_scale`): re-encode INT4 values *and* FP8 scales offline so
  the product becomes a **table lookup instead of a multiply**. Bit-exact by
  construction; our fp4_e2m1 × e4m3 pairing is the direct analogue. **This is
  the one dequant-ALU idea we do not already have** (we already ship the
  `fp4nv_decode8` SWAR path and the 2^14 / 2^22 scale folds). Instruction
  class ⇒ worth a falsification pass.
- **llama.cpp #12612** — mat-vec vs mat-mat selection for `mul_mat_id` by
  rows-per-expert was "a huge bottleneck for DeepSeek"; #6387 single tensor for
  all experts; #16340 dynamic simdgroups; params `N_R0` / `N_SG` in
  `ggml-metal-impl.h`. Directionally supports L3.
- **Apple microarchitecture.** Rigel (2606.12765): **M4 Max has no dedicated
  matrix unit**, so tensor-core-derived gains have no Apple analogue except M5
  `_nax`. The radix-8 Stockham FFT paper (2603.27569): 208 KiB register file vs
  32 KiB threadgroup, **barriers are cheap (~2 cycles) but scattered/transposed
  threadgroup access is expensive** — this is the correct prior for #457's
  float4/AoS epilogue port (the mechanism is *access pattern*, not barrier
  count). PACMAN: L1 line 64 B, L2 line 128 B, M4 Pro stride cliff beyond the
  64 B line. **No published Apple gather-vs-contiguous bandwidth measurement
  exists.**
- **KV work, all bit-exact but our SDPA family is closed:** PersistentKV
  (2606.26666) one CTA per KV-head group; ATMA (2606.25156) work bounded by
  live context; FreeKV (2505.13109) NHD vs HND layout; PAT
  (10.1145/3779212.3790200) KV-length-dependent tile size.
- **Deliberately not recommended:** LUT/T-MAC methods (published Apple numbers
  are CPU-only; T-MAC trades compute *for* bandwidth, the wrong direction on
  M5). Grouped-GEMM/MoE batching wins (MegaScale-Infer, EPS-MoE, SonicMoE
  gather fusion, METRO) are near-worthless at 1 token/expert.
- **Low reliability, flagged:** Zenodo 10.5281/zenodo.20270484 claims a base M5
  at 153.6 GB/s reaches ~96 % of its bandwidth ceiling for Qwen3-4B INT4.
  Uncorroborated; a hypothesis, not evidence.

---

## 6. Assignment order when students free up

1. **L2** routed-twin K-block prefetch (instruction class, bit-exact, best
   risk/reward).
2. **L1** algebraic epilogue normalization (largest ceiling; carries a real
   bit-exactness risk, so pair it with the equivalence oracle from step one).
3. **L3** threadgroup packing S-sweep on `LRM:7546`.
4. **L4** prefill async ladder (`LRM:733`) — needs M5 receipts, so schedule it
   when a submission slot is available rather than as an M4 timing study.
5. **CUTLASS-ex-55 offline LUT re-encode** — falsification pass only.
6. **L6** entropy histogram — offline, zero risk, kill-fast.
