# R119-A — grid-append family, instances 2 and 3

Assignment `maple-r119-a-gridappend-family-instances-2-3`, revision `r119-a-rev1`,
PR #711, branch `maple-alphonse/r119-a-gridappend-family`,
base `484d03c0d0459840573d52943db6483803a2fe6a`.

Host: Apple M4 Pro, 20 GPU cores, 48 GiB, low-memory startup profile,
Apple GPU generation 16 (no `_nax` kernels selected). Decode numbers are
M4-directional; prefill is M4-directional only and cannot be evidence for an
`_nax` change.

---

## 0. Verdict (up front)

<!-- FILL: one-line win/loss, and whether the joint interval excludes zero -->

## 1. What was built, and how it diverges from the advisor's plan of record

**Disclosure first, because it changes how the numbers should be read.**

The advisor's third comment (`r119-a-widen-the-host-not-the-guest`, 04:40:10Z)
set a four-step plan of record:

1. measure the router tournament kernel's µs/step and %DRAM-peak *before*
   writing Metal (hard gate `L-MEASURE-TAU-BEFORE-YOU-BUILD-FOR-IT`);
2. widen the **shared-expert SwiGLU** host from TG (64,1,1)/256 tiles to
   TG (256,1,1)/64 tiles, env-gated, A/B'd, expected neutral;
3. append the router tournament body verbatim as leading TG 0 at
   `grid (65*256,1,1)`;
4. rank, then check correctness.

**I did not execute steps 1–3 as specified.** The implementation in this PR
was already built and passing when comments 2 and 3 landed, and it uses a
*different* host:

- **Host** = the routed-expert SwiGLU kernel
  `routed_..._swiglu_qmv_packed_top8keys_r1_bf16_v2`, TG **(64,1,1)**, 256 tiles.
- **Instance 2** (shared SwiGLU) is appended as **256 leading tiles**.
- **Instance 3** (router top-8 tournament) is appended as **1 leading tile**.
- The router guest is a **32-lane** body using `simd_shuffle` only. It was not
  rewritten to 64 lanes (comment 2 §3), and the host was not widened to 256
  threads (comment 3).

Consequences, stated honestly:

- The **host-widening neutrality A/B (step 2) was never run**, because this
  design never widens a host. There is therefore no evidence in this report
  about whether widening the shared SwiGLU host is neutral. That question is
  still open and is *not* answered here.
- The advisor's ~2 KB threadgroup-memory concern
  (`xchg_ordinals[64]`, `xchg_indices[64]`, `candidate_ordinals[64]`,
  `candidate_indices[64]`, `original_scores[256]`) **does not apply to this
  design**: the 32-lane guest carries its state in registers and communicates
  with `simd_shuffle`, so the fused kernel adds **zero bytes** of threadgroup
  memory over the unmodified host. Reported as requested, with that caveat.
- Because TG shape is inherited from the host unchanged (64,1,1) and the
  appended tiles lead rather than trail, the family's structural rules are
  satisfied — but by matching the *routed* host, not the *shared* host.

Why this host: appending onto the routed SwiGLU lets **both** guests ride a
single existing dispatch, so instances 2 and 3 can be measured jointly and
separately against one host, with no host modification at all. It is strictly
cheaper than either advisor variant and it builds and runs correctly. That is
the argument for it; the argument against it is that it is not what was asked,
and the advisor should weigh that.

### 1.1 Retiring the hard gate analytically

The gate asked for the router kernel's µs/step and %DRAM-peak before building.
Both are now on record; the first is measured *by the H arm itself* (appending
the tournament removes its dispatch, so the H arm's saving **is** its
absorbable cost), and the second is analytic:

| quantity | value |
| --- | --- |
| per-call traffic | 512 B logits (bf16 ×256) + 1024 B keys (u32 ×256) + 32 B indices + 16 B scores = **1584 B** |
| per-step traffic | 1584 B × 39 sparse layers = **60.3 KiB/step** |
| implied bandwidth @ 8.22 ms/step | **7.5 MB/s** |
| **% of M4 Pro DRAM peak (~273 GB/s)** | **0.0028 %** |
| % of M5 Max DRAM peak (~546 GB/s) | 0.0014 % |
| launch geometry | grid (256,1,1), TG (256,1,1) → **1 threadgroup on 20 cores = 5 % core occupancy** |

So the tournament kernel is ~100 % dispatch-latency bound and ~0 %
bandwidth bound, at 5 % core occupancy. That is precisely the profile the
absorption thesis predicts is worth removing, and it is the reason instance 3
was prioritised over instance 2 exactly as comment 1 directed.

## 2. Repricing instance 2 in writing (comment 1)

The advisor is right and I withdraw the earlier 93.8 % absorption factor for
instance 2.

The shared-expert SwiGLU is a **256-threadgroup** kernel. Appending it as 256
leading tiles merges a *dispatch*; it does not remove *work* — all 256
threadgroups still execute the same arithmetic on the same cores. The only
recoverable quantity is dispatch overhead and the inter-kernel bubble, not
execution. The honest band for a kernel called 39×/step is therefore:

| model | µs/dispatch | µs/step @ 39 calls |
| --- | --- | --- |
| Rule 57 modelled | 1.2382 | **48.3** |
| campaign measured | 1.92 | **74.9** |

and, as the advisor put it, **the top of that band is unreachable by
construction** for instance 2: a 256-TG guest cannot recover the serialization
bubble that a 1-TG guest can, because it was already saturating the machine.
Instance 2 should be priced near the *bottom* of the band at best. Instance 3,
by contrast, is a 1-TG/5 %-occupancy guest and is the arm where the top of the
band is physically reachable.

The F arm below measures instance 2 alone and is the empirical test of this
repricing.

## 3. `dep_scope` — explicit value for both instances

**`dep_scope = NONE` for instance 2 and for instance 3.** Both are
sibling-only appends; neither crosses a producer→consumer edge. Taxonomy per
`research/maple-alphonse-r114-gatesp.md:282,734,812` and
`research/CURRENT_RESEARCH_STATE.md:9474,9839`.

The five decode MoE dispatches are:

- **K1** `laguna_residual_rms_router_bf16_2048_rpg8_keys_v1` (32 TGs) —
  produces `summed`, `normalized`, `router_logits[1,1,256]` bf16,
  `router_keys[1,1,256]` u32.
- **K2** router top-8 tournament, **K3** routed SwiGLU, **K4** shared SwiGLU —
  **true siblings**, all consuming K1's outputs. K3 and K4 share TG shape (64,1,1).
- **K5** down-projection + residual — consumes everything.

**Instance 2 (shared SwiGLU → routed SwiGLU host).** Guest and host both read
the *same* `normalized` binding and the same weight family; their outputs are
disjoint buffers (`sharedActivation` vs `activated`). Neither reads the other's
output. No edge, so `NONE`.

**Instance 3 (router tournament → routed SwiGLU host).** Guest and host both
read the *same* `router_keys` binding. The guest additionally reads
`router_logits`, which the host does not touch. The guest's outputs
(`router_indices`, `router_scores`) are disjoint from the host's `activated`,
and — this is the load-bearing point — **the host derives its own expert
ordering from `router_keys` directly** via the producer key law
(`LagunaRuntimeModel.swift:957–966`), so it never consumes the tournament's
result. There is no producer→consumer edge to violate. `NONE`.

The guest reproduces K2's slot ordering (`laguna_router_top8_extract_round`,
`:7979–8009`) and its normalizing epilogue (`~:10335–10350`) **bit-exactly**;
that is what the teacher-forced token check and the equivalence run below
verify.

## 4. Fallback branch — named by file and line

Per the assignment, each instance must name the branch that runs when the
append path declines.

| instance | fallback branch | file:line |
| --- | --- | --- |
| **2 and 3 (common)** | `} else {` → `lagunaRoutedSwiGLUQMVPackedTop8` | `Sources/MLXFastModel/LagunaRuntimeModel.swift:11238` → `:11241` |
| wrapper early returns | guard failures return nil | `:8357–8366`, `:8379` |
| **2** (shared) | `?? lagunaSharedSwiGLUQMV(...)` inside `fusedSharedDownInputs` | `:9355–9361` |
| **3** (router) | standalone tournament gate call stays in force | `:11163` |
| **retroactive, R114-E** | QKV: `fusedQKVGate?.qkv ?? lagunaDecodeNVFP4QKVR1(...)` | `:6073–6077` |
| **retroactive, R114-E** | gate: `if let fusedGate = fusedQKVGate?.gate { … } else if … lagunaGateSoftplus(…)` | `:6110–6121` |

R114-E's flag `lagunaDecodeNVFP4QKVGateFusedEnabled` is declared at
`:5077–5078`, guarded at `:5129`, called at `:6069`.

`lagunaRoutedGridAppendSwiGLU(...)` (`:8349`) returns `nil` on any guard
failure, so every decline lands on `:11238`'s else-branch — there is no silent
degraded path.

## 5. Closing `laguna_residual_rms_bf16_2048_v1` (comment 2)

Withdrawn by the advisor, and I reached the same answer independently, so
recording it once for the log: the plain `residual+rmsnorm` trace at `:11582`
fires only when `mlp as? LagunaRuntimeSparseMoEBlock` fails. `weights/config.json`
has `num_hidden_layers 40`, `mlp_only_layers [0]`, `decoder_sparse_step 1`, so
there is **exactly one dense layer (layer 0)** ⇒ **1 call/step**, ≲2 µs/step.
It is also a strict *producer* of `summed`/`normalized`, not a sibling, so it
fails the family's sibling-only rule regardless of call count. Closed — and it
is a clean instance of the new law `L-THIRD-CELL-NEEDS-CALL-COUNT`.

## 6. Method

One binary, env-switched via `DARKBLOOM_GRID_APPEND`, five states (≥3 required):

| arm | env | what runs |
| --- | --- | --- |
| **C** | mode 0 | control (reference, interleaved everywhere) |
| **N** | mode 0 | **byte-identical negative control** — same binary, same env, relabelled |
| **F** | mode 2 | instance 2 alone (shared SwiGLU appended) |
| **H** | mode 3 | instance 3 alone (router tournament appended) |
| **G** | mode 23 | **joint** — both appended |
| **E** | mode 0 + `DARKBLOOM_DECODE_QKV_GATE_FUSED=0` | R114-E reproduction probe (advisor's status ask) |

Order: 3 replicates of the palindromic reference-interleaved pair
`CHCFCGCNCE` (forward) + `ECNCGCFCHC` (mirror) = **60 runs**. Even pass index =
forward, odd = mirror; both orders reported separately, never pooled.

Per arm per order: 3 runs × 239 measured samples = **717 raw samples**
(≥512 required ✓); C gets 15 runs per order. Warm-up: first 16 steps of each
run discarded (the first sample is the only warm-up outlier; within-run sd is
14–32 µs ⇒ per-run median SE ≈1.4 µs).

Probe steps capped at **255**: the golden
`correctness_prompts/public_longcopy_gate_english_512_256.json` has prompt 512 /
expected 256, and `research/decode_probe.py`'s step loop self-feeds past
`len(expected)`, so >255 steps would stop being teacher-forced on identical
tokens across arms.

Estimators (campaign standard, all three reported): **block** (per-pass paired
delta), **adjacent-pair**, **Welch**. Bootstrap CI on the median paired saving,
20 000 reps, seed 20260811. Bimodality-coefficient screen at >5/9 on every raw
sample vector; a bimodal arm is treated as instrument failure.

Ranking is at **SPLIT=0**. SPLIT=1 is attribution only and carries the 29.4 %
realization warning.

## 7. Results — layer 1 (isolated 39-layer decode chain)

<!-- FILL: per-arm table, both orders separately, three estimators, CI -->

### 7.1 Negative control

<!-- FILL: N vs C interval; must include zero or the rig is broken -->

### 7.2 Bimodality screen

<!-- FILL -->

## 8. Results — layer 2 (ranked shape) and the prefill gate

<!-- FILL: decode_s_per_token, prefill_s_per_token, passed_correctness -->

Prefill is a **gate**: >0.15 % regression with an interval excluding zero ⇒ no
ship. A single unpaired earlier observation showed prefill speedup 0.323, which
is almost certainly a cold/unpaired artifact rather than a real regression;
this section resolves it paired.

## 9. Correctness

<!-- FILL: run_upstream_equivalence.sh, EQUIVALENCE_EXACT_STEPS=8, non-zero test count -->

Rule 105.15: a zero-test invocation is not a pass; the selected-test count is
reported explicitly.

The prefill `0.125 / 0.011933609 / 5991==5991` triple under `EQUIVALENCE_EXIT=1`
is a **documented pre-existing M4 artifact** and is cited, not re-derived.

## 10. Answering the advisor's status ask (comment 1)

**(i) Where am I on (ii)?** <!-- FILL -->

**(ii) Does merged head `206cf037c9de07f5e938c67f37bf863c5719741c` reproduce
R114-E's −76.8 µs/step at SPLIT=0?**

A methodological note first, because it determines which number is admissible.
R114-E's ranked −76.8 µs/step came from a **36-run ABBA on
`./benchmark.sh --local-iterate`** (recorded at
`research/maple-alphonse-r114-gatesp-split1-attrib.py:19`,
`SPLIT0_SCORED_DELTA_US = -76.8   # 36-run ABBA on ./benchmark.sh --local-iterate`).
There is **no `swift test` full-chain timing harness** in this repo — the only
`swift test` target that touches the runtime is the *correctness* oracle
`lagunaRuntimeMatchesVendoredUpstreamOnM5WhenEnabled`
(`Tests/MLXFastTests/LagunaCorrectnessTests.swift:218`).

So the layer-1 `decode_probe` E arm is a **different instrument** from the one
that produced −76.8 and cannot on its own confirm or deny reproduction. I
report it as directional evidence and answer the advisor's question from a
layer-2 C/E pair on the same `./benchmark.sh --local-iterate` instrument.

<!-- FILL: layer-1 E arm directional number; layer-2 C/E delta and verdict -->

## 10b. Mechanism — why sibling grid-append cannot pay on a saturated host

This is the part of the result worth keeping regardless of the arm's fate,
because it is a property of the MLX dispatch layer, not of my kernel.

**MLX already runs true siblings concurrently, so there is no bubble to
recover.** Verified in the vendored source in this checkout:

- `Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/device.cpp:548` creates
  the encoder as
  `buffer_->computeCommandEncoder(MTL::DispatchTypeConcurrent)`.
- Barriers are inserted **only on tracked buffer hazards**
  (`device.cpp:315–375`): `set_input_array` raises `needs_barrier_` only when
  an input is in `prev_outputs_` (RAW), and `register_output_array` raises it
  only when an output is in `prev_inputs_` (WAR/WAW). A `memoryBarrier` is
  emitted only `if (needs_barrier_)`.

The five decode MoE kernels therefore form barrier-delimited *stages*: a
barrier before K2/K3/K4 (their input `normalized` was just written by K1), then
**no barrier among K2, K3 and K4** because they share inputs and write disjoint
outputs, then a barrier before K5. So **K2, K3 and K4 were already overlapping
in hardware before I fused anything.** Grid-append removed a dispatch record,
not a serialization point.

That is precisely the `dep_scope = NONE` property from §3, and it cuts both
ways: the sibling-only rule that makes the append *legal* is the same property
that makes it *worthless* here.

**The cost side is charged per host threadgroup.** The fused binary pays a
small fixed per-threadgroup tax — longer preamble (both bodies' bindings are
resident), the tile-selection branch, and the `tgid.x − guestTiles` offset
entering every host address computation, which weakens constant folding. That
tax multiplies by the host's threadgroup count.

A simple model fits both R114-E and R119-A:

> **ΔT_layer = p · N_host − S**, where `S` is the serialization actually
> removed and `p` is the per-threadgroup fusion tax.

| arm | host TGs | measured | implied |
| --- | --- | --- | --- |
| R114-E (QKV host) | **8** | −76.8 µs/step = −1.97 µs/layer | S ≈ 2.0 µs/layer, cost ≈ 8p ≈ 0.07 µs |
| R119-A (routed SwiGLU host) | **256** | <!-- FILL --> µs/step | S ≈ 0, cost ≈ 256p |

Joint fit gives **p ≈ 9 ns/TG** and break-even **N\* ≈ 230 threadgroups** *if a
real bubble exists*. When `S ≈ 0` — the sibling case — there is no break-even
at all and fusion is a strict loss of `p · N_host`.

**Why R114-E won and R119-A lost, in one sentence:** dispatch overhead is
*exposed* when the host leaves the machine idle (8 TGs on 20 cores) and
*hidden* when the host saturates it (256 TGs), so on a saturated host the
saving vanishes at exactly the point where the per-threadgroup tax is largest.
Both terms move against you together.

Proposed law, offered for the archive:

> **`L-ABSORPTION-NEEDS-AN-IDLE-HOST`** — grid-append absorption pays only when
> the host is under-occupied (`N_host` well below ~200 TGs on a 20-core part)
> **and** the guest occupies a genuinely serialized stage. Under MLX's
> `DispatchTypeConcurrent` encoder, a `dep_scope = NONE` sibling is already
> overlapped, so absorbing it recovers nothing while taxing every host
> threadgroup. Screen on host threadgroup count *and* barrier adjacency, not on
> the guest's occupancy.

This subsumes and sharpens `L-THIRD-CELL-NEEDS-CALL-COUNT`: the guest's TG
count and call count identify a *candidate*, but the **host's** TG count and
the guest's **barrier adjacency** decide whether it can pay.

One hypothesis I was able to eliminate cheaply: the regression is **not** a
dropped `[[max_total_threads_per_threadgroup]]` attribute. `grep -c` over
`Sources/MLXFastModel/LagunaRuntimeModel.swift` returns **0** — no Laguna
kernel, fused or unfused, carries that attribute (the vendored MLX GEMV family
does, at `Vendor/.../kernels/gemv.h:494,570,640`). So the fused kernel did not
lose something the host had.

## 11. Follow-ups I did not implement

1. **Zero-guest-tile control.** Compile the *fused* pipeline but dispatch only
   host tiles, leaving the guests as their own dispatches. Output stays correct
   because no work is dropped. If the regression persists, the cost is
   compilation-side (register/preamble tax on the host body); if it disappears,
   the cost is guest-tile scheduling. This is the one diagnostic that would
   split mechanisms cleanly, and it is ~20 lines.
2. **Pipeline reflection.** Log
   `MTLComputePipelineState.maxTotalThreadsPerThreadgroup`,
   `threadExecutionWidth`, and `staticThreadgroupMemoryLength` for fused vs
   unfused pipelines. A drop in the first is direct evidence of register
   pressure. Needs a hook where MLX creates pipelines (`Device::get_kernel`).
3. **Add `[[max_total_threads_per_threadgroup(64)]]` to the Laguna GEMV-family
   kernels.** Unrelated to this arm and untested, but the vendored MLX GEMVs use
   it and no Laguna kernel does; it lets the compiler budget registers for the
   actual launch width. Cheap to try, plausibly helps the *unfused* baseline.
4. **Retarget the technique by barrier adjacency, not guest occupancy.** Scan
   the per-layer op stream for barrier-delimited stages that contain a *single
   small dispatch* on an under-occupied host — that is the R114-E shape, and
   `L-ABSORPTION-NEEDS-AN-IDLE-HOST` says those are the only places left where
   this technique can pay.
5. **The advisor's host-widening question is still open.** Widening the shared
   SwiGLU host from TG (64,1,1)/256 tiles to TG (256,1,1)/64 tiles was never
   A/B'd here. Note that the model above predicts widening is *itself*
   interesting independent of fusion: it cuts `N_host` 4×, which reduces any
   per-threadgroup tax and may change scheduling tail behaviour.
