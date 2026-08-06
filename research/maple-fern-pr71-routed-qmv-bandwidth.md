# PR #71 — Routed-expert NVFP4 QMV decode: Step 0 hard stop

```text
SENPAI-RESULT: {"terminal":true,"status":"complete","pending_arms":false,"wandb_run_ids":[],"primary_metric":{"name":"same_host_paired_estimate","available":false,"value":null},"test_metric":{"name":"passed_correctness","available":true,"value":1}}
```

- **Student / PR:** maple-fern / #71 (`maple-2026-08-06a-routed-qmv-bandwidth`, `r1`)
- **Hypothesis and target cost:** the routed gate/up NVFP4 SwiGLU QMV decode
  kernel moves 552.08 MB/step at 546.2 GB/s against a host ceiling, and closing
  the shortfall is worth up to +2.44% of score. Step 0 required reproducing the
  shortfall on M4 first, with a **hard stop if the M4 kernel already achieves
  ≥92% of the 260.2 GB/s M4 ceiling**.
- **Decision: dead hypothesis at Step 0 — hard stop triggered.** No mechanism
  was implemented; no scored-path byte was changed.
- **`BASE_SHA` / candidate commit:** base `768bb9d4adfc2baac7d74c0008afc92d010329da`
  (preflight base); branch parent `d08ddd7b2c33e9421c7c1d894c8b00071507fd31`;
  candidate = final commit on `maple-fern/routed-qmv-bandwidth`.
- **Submitted candidate files:** **none.** `Sources/` is byte-identical to the
  assignment base — `git diff --stat d08ddd7b -- Sources/` is empty. The
  temporary `DARKBLOOM_ROUTED_QMV_DUP` instrument was reverted after
  measurement.
- **Supporting test or documentation files:** `research/pr71_dup_sweep.sh`,
  `research/pr71_dup_analyze.swift`, `research/pr71-dup/score.dup{1,3,5}.json`,
  this note. All research-only.
- **Official submission `--model` value (planned or used; default `senpai`):**
  `senpai` — **planned only, not used. No official submission was dispatched.**
  A Step 0 stop with zero scored-path change has nothing rankable to submit, and
  the assignment requires advisor clearance before any `mlxfast submit`.
- **Explicit API model-value rejection, if fallback attribution was required:**
  none — no submission attempted, so no rejection occurred and no fallback
  attribution was used.
- **Assignment-scope preflight:**
  `assignment scope OK: 1 submitted path(s) against BASE_SHA=768bb9d4adfc2baac7d74c0008afc92d010329da`
- **Editable bytes / headroom / growth:**
  `editable budget OK: current=2941175/3000000 bytes headroom=58825 growth=-58809/262144 files=142 (file count is diagnostic only; base=142)`
  — identical to the pre-instrument reading, confirming the revert restored the
  submitted surface exactly.
- **Scored-path reachability evidence:** the instrument was placed inside
  `lagunaRoutedSwiGLUQMVPackedTop8` on the live `lagunaRoutedGateUpR1Enabled`
  branch, i.e. the R1 kernel actually dispatched during scored decode. Its
  reachability is proven by the measurement itself: the sweep changed decode
  time monotonically and linearly with the duplication count (below), which is
  only possible if the duplicated dispatch executes on the timed path.
- **Injection-guard pre-dispatch check** (`Sources/MLXFastModel/LagunaRuntimeModel.swift`):

  ```text
  11046:    "DARKBLOOM_INJECT_DECODE_EMPTY", 0)
  11058:    "DARKBLOOM_INJECT_EMPTY_TG", 160)
  ```

## Evidence

- **Host, memory profile, toolchain, thermal policy:** Apple M4 Pro, **20 GPU
  cores**, 48 GiB unified memory (low-memory startup profile), macOS 26.5.2,
  Metal 4, Apple GPU generation 16 (never selects `_nax`). Standard 40 °C
  thermal gate, never bypassed. **Not the ranked host** — official ranking is
  M5 Max / 128 GB.
- **No W&B on this track.** This programme reports through sealed benchmark JSON
  and ranked receipts, not Weights & Biases; `wandb_run_ids` is intentionally
  empty and no run URLs exist to cite. Evidence is the `research/` artifacts and
  the sealed per-arm JSON listed above.
- **Exact commands:**

  ```bash
  # per-arm sweep (run under run_training, id 2cd4fd9c-6c75-4ad6-bf03-859f68cd47c2)
  research/pr71_dup_sweep.sh 1 3 5
  #   -> DARKBLOOM_ROUTED_QMV_DUP=N ./benchmark.sh --local-iterate
  #   -> research/pr71-dup/score.dup<N>.json

  xcrun swiftc -O research/pr71_dup_analyze.swift -o /tmp/pr71_analyze
  /tmp/pr71_analyze research/pr71-dup/score.dup1.json \
                    research/pr71-dup/score.dup3.json \
                    research/pr71-dup/score.dup5.json

  CLANG_MODULE_CACHE_PATH="${PWD}/.build-worker/clang-module-cache" \
    swift build -c release --force-resolved-versions \
      --scratch-path .build-worker --product mlxfast-runtime-worker
  git checkout -- Package.resolved
  ```

- **Tests and risk-based checks run:** the three sweep arms each ran the full
  `--local-iterate` correctness suite; a release build of the reverted scored
  path (`Build of product 'mlxfast-runtime-worker' complete! (20.05s)`, only the
  pre-existing unrelated warning at `:9933`); scope and budget preflights; the
  injection-guard grep. `LagunaUpstreamEquivalence.swift` was **not** run and is
  not required: the final candidate changes no numerical behaviour,
  representation, dispatch, or layout on the scored path.
- **Correctness and serial-protocol verdict:** all three arms
  `passed_correctness=true`, `max_abs_diff=0`, and a single shared
  `golden_hash=b9509697c08a...`. The instrument only ever re-ran the *same*
  invocation's own dispatch and folded copies with a value-preserving
  `maximum`; it computed no logits or KV rows for unsupplied tokens, added no
  deferred cache rows, and advanced KV position by exactly the supplied input
  length. Serial non-speculative rules were not engaged. The final candidate is
  a no-op on the scored path, so the verdict carries trivially.
- **Divergent tokens or failure category:** none.
- **Peak RAM:** 21 GB, unchanged (matched baseline `peak_ram_gb=21`,
  `num_layers=40`).
- **Official ranking status versus correctness/floor status:** not submitted;
  no ranked receipt was consumed.

### Step 0 measurement — in-situ additive duplication

`DARKBLOOM_ROUTED_QMV_DUP=N` repeats the routed gate/up R1 dispatch N times per
MoE layer and folds copies with `maximum`, so the marginal cost of one dispatch
is the OLS slope in N.

| N | decode s/tok | prefill s/tok | correct | max_abs_diff | golden_hash |
|---:|---:|---:|:--|---:|:--|
| 1 | 0.013433452 | 0.001139759 | true | 0 | `b9509697c08a` |
| 3 | 0.016022539 | 0.001126075 | true | 0 | `b9509697c08a` |
| 5 | 0.018667144 | 0.001125339 | true | 0 | `b9509697c08a` |

- OLS `decode_s_per_tok = 0.012115776 + 0.001308423·N`, **slope = 1.3084 ms per
  extra pass**, **R² = 0.999962**.
- Pairwise slopes 1.2945 / 1.3084 / 1.3223 ms — linear, so MLX did not
  common-subexpression-eliminate the duplicated dispatches (the fold kept every
  copy live).
- Byte accounting for one gate/up pass: 39 MoE layers × 9 MiB per layer
  (8 experts × (1 MiB codes + 128 KiB scales)) = **368.1 MB/step**. This
  reconciles with the brief's 552.08 MB once the separate down-projection
  kernel's ≈184 MB is added.

### The instrument is inadmissible for the achieved-bandwidth question — and says so

Pre-registered admissibility test: one genuinely DRAM-served pass cannot beat
`368.1 MB / 260.2 GB/s = 1.4145 ms`.

| quantity | value |
|---|---:|
| measured marginal cost | 1.3084 ms/copy |
| analytic DRAM floor | 1.4145 ms/copy |
| measured / floor | **92.5%** |
| implied bandwidth (uncorrected) | **281.3 GB/s = 108.1% of the M4 ceiling** |
| minus 39×0.36 µs dispatch overhead | 284.3 GB/s = 109.3% |
| minus 39×2.088 µs dispatch overhead | 300.0 GB/s = 115.3% |

The slope is **below** the analytic floor and the implied rate **exceeds the
host DRAM ceiling** (and exceeds M4 Pro's 273 GB/s nominal), which is
physically impossible for cold DRAM traffic. The duplicate passes re-read the
same 9 MiB per layer that the first pass just fetched and were served from
cache. This is the exact §0.9.18 signature.

Two consequences, stated plainly:

1. **The measurement cannot establish the Step 0 achieved-bandwidth figure**, in
   either direction. `C` (cold first-pass cost) and `E` (everything else) are
   not separately identifiable from a linear response whose slope is the *warm*
   marginal cost: `T(N) = E + C + (N−1)·W` fits the data exactly for any split
   of `E` and `C`. Confirmed numerically — predicting T(3) and T(5) from T(1)
   plus the slope reproduces the measurements to 26 µs and 2 µs.
2. **It does establish a hard lower bound on the kernel's issue capability:** it
   retired 368.1 MB of logical traffic in 1.3084 ms, so its instruction-issue and
   L1/L2 path sustain **≥281 GB/s on 20 M4 cores** — above the M4 DRAM ceiling.
   On M4 this kernel is DRAM-limited, not issue-limited.

### Step 0 verdict: the gate was already answered, and it says STOP

The achieved-bandwidth question this step was asked to reproduce is already
settled in the programme's own authoritative record, by an instrument
§0.9.18 explicitly certifies as unaffected by the cache-service defect:

> `research/CURRENT_RESEARCH_STATE.md:2519-2521` — "These are the most
> byte-saturated kernels in the model (#9 isolated, ceiling 260.2 GB/s):
> `decode_nvfp4_qkv_h64_r1` 100% of ceiling, `qkv_h48` 99%, `oproj_act_h64` 95%,
> **`routed_..._swiglu_qmv` 93%**. At 100% of the DRAM ceiling there is no slack
> to absorb a byte reduction."

> `research/CURRENT_RESEARCH_STATE.md:1561-1563` (§0.9.18) — "**Unaffected: rows
> already at ≈100% of ceiling** — `qkv_h64_r1`, `lmhead_int5`, `oproj_act`,
> `down_residual`, **`routed_swiglu_qmv`**. A kernel at the ceiling is at the
> ceiling however you count the bytes."

**93% ≥ 92% ⇒ hard stop.** My own sweep corroborates it from the opposite
direction (issue capability ≥108% of ceiling ⇒ DRAM-bound on M4). The reason
§0.9.18 exempts this kernel is structural and worth recording: within one
genuine pass each expert-bank byte is read **exactly once**, so unique traffic
equals logical traffic and the "% of ceiling" column is a real measurement here
— unlike the sliding-attention row where four threadgroups re-read the same
window. My duplication probe manufactured the re-read that the real kernel does
not have, which is precisely why it fell foul of the same law.

### The prize is also smaller than the brief states

The brief prices full closure at +2.44%, which uses 651.8 GB/s as the reference.
The programme's corrected arithmetic uses the **610 GB/s M5 streaming read**,
because 651.8 GB/s is itself *107% of nominal* and therefore cache-inflated
(`research/CURRENT_RESEARCH_STATE.md:2476-2478`):

> `research/CURRENT_RESEARCH_STATE.md:1236-1250` — "Routed-expert QMV decode
> moves 552.08 MB at 546.2 ± 23.3 GB/s; the reference is the **610 GB/s M5
> streaming read**, not 651.8 GB/s. Excess = 552.08/546.2 − 552.08/610 =
> **0.10572 ms**, and 0.10572 × 14.862 %/ms = **+1.571%**."

with three caveats already on record: propagating rate 4's ±23.3 GB/s gives a
price bracket of **+0.96% to +2.24%**, whose **pessimistic end does not clear the
+1.461% P=50% promotion bar**; rate 4 rests entirely on a single R3−R2 receipt
difference (`6757de6` − `ca416f0`); and full closure "is an upper bound with no
realization estimate", part of which the existing depth-1 staging already banked.

### Mechanism review (Step 1 census + independent frontier review)

I completed the Step 1 read-pattern census before stopping. Full details are in
the census section below; the load-bearing findings:

- The scale plane's `[tile 128][k-block 4][sub 8][lane 32]` layout already
  achieves ≈100% cache-line utilisation at threadgroup granularity: a simdgroup
  consumes a contiguous 64 B and the two simdgroups of a threadgroup together
  cover exactly one full 128 B line. **Partial-line consumption is not where the
  shortfall is.**
- The mechanism I was primed to build (widening the per-thread device read of
  the *codes* to `uint4`) is **bit-exactness-hostile as literally stated**:
  it forces `values_per_lane` 16→32 and `block_width` 512→1024, re-partitioning
  which K indices each lane accumulates, hence different per-lane partial sums
  into `simd_sum`. The two k-blocks a lane needs are 256 B apart and cannot be
  merged without that re-partition.
- My bit-exact substitute — re-permuting the scale bank to
  `[tile][sub 8][lane 32][k-block 4]` so 8 one-byte scale loads per output row
  collapse to 2 hoisted `uchar4` loads — is legal and would cut memory
  instructions per row 16 → 10, but it **saves zero bytes**. On a kernel
  certified at the DRAM ceiling it has no byte headroom to convert.

An independent frontier review (no inherited context) reached the same two
conclusions from its own reading of the source and added a correction and a
better idea:

- It confirmed the existing 32 × 1 B scale loads "already reach DRAM as
  fully-utilized 128 B lines", so the permutation is an issue-side mechanism
  worth only ~2–3% of the gate/up kernel, roughly **⅛ of the shortfall**.
- It corrected my offset arithmetic: the permuted gate offset is
  `sub*256 + lane*4`, not `sub*128`.
- It independently derived the M4/M5 divergence: instruction-to-DRAM time ratio
  ≈0.74 on M4 Pro versus ≈0.89 on M5 Max, so "instruction-removal wins will
  under-measure or vanish locally while being real on the ranked host".
- **It named a mechanism 2–5× larger than mine:** the duplicated top-8 router
  extraction. `expert_slot = group % routed_experts` is threadgroup-uniform, so
  both simdgroups of every threadgroup redundantly run the entire top-8
  extraction for the same expert — 4096 extractions per layer, each reading 1 KB
  of router keys — at roughly **17% of dynamic instructions**. Deduplicating it
  through threadgroup memory is bit-exact and is the highest-EV single mechanism
  in this kernel.

### Conclusion

- **What happened and why:** Step 0's hard stop fired. The kernel this
  assignment targets is already at the M4 DRAM ceiling (93%, and the programme's
  own §0.9.18 lists it among the rows "at the ceiling however you count the
  bytes"), so M4 has no byte slack to screen a bandwidth mechanism. My in-situ
  duplication probe could not answer the question on its own — it measured a
  warm marginal cost below the analytic DRAM floor and an implied 108% of the
  host ceiling — but the pre-registered admissibility test caught that, and the
  probe's one durable positive result is a lower bound of ≥281 GB/s on the
  kernel's issue capability, which points the same way: DRAM-bound on M4.
- **Evidence for or against the mechanism:** against, on two independent
  grounds. The scale plane already achieves full line utilisation, so there is
  no coalescing defect to fix; and the mechanism saves zero bytes on a kernel
  with no byte slack. Both my census and an independent frontier review agree,
  and the review sizes the best case at ~⅛ of the shortfall — comfortably below
  the 0.278% single-receipt MDE, which puts it squarely under **§0.9.22, the
  unfalsifiable-rider rule**: preserve as a `research/` note, never merge as
  permanent scored-path code. I have therefore left the scored path untouched.
- **Uncertainty or M5 transfer risk:** the residual live hypothesis is that the
  M5 shortfall is **issue-bound, not bandwidth-bound**. On 20 M4 cores the
  kernel sustains ≥281 GB/s; the frontier review's instruction census puts M5
  Max at ~89% of instruction-issue capacity, matching the observed 546 GB/s
  against a 610 GB/s streaming ceiling. If that holds, instruction removal is
  the right lever *on M5* and M4 is structurally unable to see it — the M4
  result is not evidence either way. Note also that the 546.2 GB/s figure rests
  entirely on one R3−R2 receipt difference (±23.3 GB/s), so the shortfall's
  existence is itself a single-receipt claim.
- **Smallest useful next action:** the router-extraction dedup, *not* a
  bandwidth mechanism — but it is unrankable locally by construction, so the
  decision to spend a blind ranked receipt on an M4-invisible issue-side change
  belongs to the advisor, not to me. Before that, the free step is to re-derive
  the M5 shortfall by the §0.9.18-mandated wave/latency method with §0.9.19
  core-count matching (M4 Pro = 20 cores, M5 Max core count needed), which
  consumes no receipt and would establish whether the 0.106 ms is issue-side or
  a single-receipt artifact.
- **Recommendation: close.** The bandwidth framing of this assignment is
  refuted; the byte-reduction hypothesis is dead. The router-extraction dedup
  deserves a fresh assignment with an explicitly issue-side prediction and an
  advisor decision about local unmeasurability — it should not be smuggled in
  under this PR's bandwidth hypothesis.

---

## Appendix — Step 1 read-pattern census

Line numbers are against the assignment base `d08ddd7b`
(`Sources/MLXFastModel/LagunaRuntimeModel.swift`); the kernel declaration begins
at `:7334`, body `:7339-7446`, Swift wrapper `:7453-7489`.

1. **Format.** NVFP4 `groupSize 16`, `bits 4` — 8 B per group of 16 plus one
   uint8 E4M3 scale byte (`laguna_nvfp4_scale`, `:6485`).
2. **Two buffers.** `fused_weight` (uint32, cast to `uint8_t*`):
   `fused_expert_bytes = 1 MiB`, `fused_row_bytes = 1024`, 1024 gate/up
   interleaved rows. `packed_scales` side bank `_packedRoutedGateUpBank`
   (declared `:9739`, built `:9842-9881`, assigned `:9878`):
   `[tile 128][k-block 4][sub 8][32 B]`, `scale_row_bytes 32`,
   `scale_kblock_bytes 256`, `scale_tile_bytes 1024`,
   `packed_expert_bytes 131072`, shape `[256, 4096, 32]`. It is a pure
   init-time byte reordering via `contiguous(take(rowBlocks, order, axis: 1))`
   with the gate/up row remap baked in.
3. **Load widths.** Codes `uint2` = 8 B/lane (prologue `:7389-7392`, steady
   `:7418-7423`); scales 1 B scalar ×2 (`:7387-7388`, `:7416-7417`); activation
   `vec<bfloat,4>` ×4 = 32 B/lane (`:7396-7405`); router keys 8 × `uint`. All
   inputs are `device` — MLX sets `max_constant_array_size = 8`
   (`Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/common/metal_kernel.cpp:19`).
4. **Lane strides.** Codes `+ lane*8`, so 32 lanes cover a contiguous 256 B per
   row per k-block — ideal coalescing at half `uint4` width. Scales `+ lane`
   (32 B simdgroup transaction), gate then `+ scale_row_bytes` (adjacent 32 B);
   8 such 32 B accesses per output row (4 k-blocks × 2 planes), k-blocks 256 B
   apart.
5. **Expert base.** `expert = top8_winner` (`:7359`), addresses `:7361-7365`.
   `top8_winner` is broadcast by a 5-stage `simd_shuffle_xor` butterfly, so it
   is value-uniform but **not compiler-provably** uniform and the addresses live
   in vector registers. `expert_slot = group % routed_experts` (`:7353`) is
   threadgroup-uniform, so both simdgroups redundantly repeat the whole top-8
   extraction for the same expert; only `logical_row` differs (`:7357`).
6. **Passes and geometry.** One interleaved, software-pipelined pass with
   depth-1 staging (`:7374-7379`). Grid `(8*256*64,1,1)` = 131072 threads,
   threadgroup `(64,1,1)` ⇒ 2048 threadgroups × 2 simdgroups. **Zero
   threadgroup memory**; no `[[max_total_threads_per_threadgroup]]`. The legacy
   v1 sibling uses `8*128*64` with 2 rows/simdgroup.
7. **Tiling.** One output row per simdgroup, `logical_row = tile*2 + simd_group`;
   K = 2048 = 4 blocks × `block_width 512`; one NVFP4 group per lane per block;
   `simd_sum` (`:7434-7435`); lane 0 writes (`:7436`). Row remap
   `gate_row = (logical_row/32)*64 + logical_row%32`, `up_row = gate_row + 32`,
   so the two streamed code rows are 32 KB apart.
8. **Bytes.** Per simdgroup per expert: codes 2×1024 = 2048 B + scales
   4×2×32 = 256 B = 2304 B per row, plus a 4096 B activation re-read and 1024 B
   of router keys (both cache-served). Whole gate/up dispatch per MoE layer =
   2048 × 2 × 2304 = 9,437,184 B = 8 experts × (1 MiB codes + 128 KiB scales)
   ⇒ **368.1 MB/step across 39 layers**.
9. **Line-utilisation finding (item 6 of the brief).** With
   `sub = 2*(logical_row%4) + plane`, a simdgroup consumes a contiguous 64 B and
   the two simdgroups of a threadgroup (rows `4t'`, `4t'+1` for an even tile)
   together cover exactly one full 128 B line. Scale-plane line utilisation is
   ≈100% at threadgroup granularity, so **partial-line consumption is not the
   defect**; only instruction/issue efficiency remains.
10. **Consumer hazard for any bank re-layout.** The packed scale bank feeds
    **four** kernels: `:7030` and `:7190` (the `indices` variants, reached when
    `DARKBLOOM_ROUTER_PRECOMPUTED_KEYS=0` or when the per-call router guards at
    `:9954-9960` fail), `:7301` (legacy v1 top8keys) and `:7336` (the live R1
    top8keys). Any re-permutation must update all four plus the builder
    together; env-gating the layout would be the more fragile choice.
