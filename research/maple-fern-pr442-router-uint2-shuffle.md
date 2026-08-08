# PR #442 — Q12b: `uint2 simd_shuffle_xor` in the routed-QMV router Top-8 prologue

Assignment `maple-2026-08-08b-router-uint2-shuffle` r1, BASE_SHA
`730e9c2be89a4ed8cf860e52f930f7ff222d4c95`, host **Apple M4 Pro / 20-core GPU /
Apple GPU generation 16 / 48 GiB** (low-memory startup profile).

Replication target: external promoted submission `b9ccb0b` (fyrsta7), reported
≈ +0.24…0.31 % ranked-M5 decode from packing the two scalar `simd_shuffle_xor`
calls of the Top-8 butterfly into one `uint2` shuffle per offset.

## Mechanism

`laguna_router_top8_extract_round` selects the round-`r` winner out of 256
routed-expert scores with a 5-stage XOR butterfly over a 32-lane simdgroup.
Each stage exchanges a `(key, value)` pair, i.e. two 32-bit words:

```metal
for (uint offset = 16; offset >= 1; offset >>= 1) {
    uint ok = simd_shuffle_xor(bk, offset);
    uint ov = simd_shuffle_xor(bv, offset);
    ...
}
```

The candidate packs the pair into a `uint2` so the compiler can emit one
`air.simd_shuffle_xor.u.v2i32` instead of two `air.simd_shuffle_xor.u.i32`:

```metal
for (uint offset = 16; offset > 0; offset >>= 1) {
    uint2 other = simd_shuffle_xor(uint2(bk, bv), offset);
    ...
}
```

Bit-exact by construction: the same two words are exchanged with the same lane
partner, only the transport is packed.

## Shipped guard

`Sources/MLXFastModel/LagunaRuntimeModel.swift`, inside the permitted region
(base lines 7592–7623). `DARKBLOOM_ROUTER_UINT2_SHUFFLE`, default OFF:

| value | arm | butterfly body |
| --- | --- | --- |
| unset / other | `off` (default) | two scalar shuffles, `offset >= 1` |
| `1` | `on` | one `uint2` shuffle, `offset > 0` |
| `control` | `ctl` | two scalar shuffles, `offset > 0u` |

`ctl` is the rule-3 / rule-36 **invariant control**: source-byte-different from
`off`, IR-identical to it, numerically identical to both. It measures the slot
effect (kernel-source-hash, library-build, process-order) that any real effect
must exceed. All three arm bodies differ textually from the unguarded base text,
so no arm can accidentally share a shader cache entry with the base.

Rule 33 note: the arm-selected text is a *body* substring interpolated into
`lagunaRouterTop8PrologueHeader`; the kernel-name literals live at
`LagunaRuntimeModel.swift:7638` / `:7661`, outside the permitted edit region, so
they were not suffixed. This is safe because
`Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/device.cpp:770`
(`Device::get_library(name, builder)`) is an in-process `std::map` keyed on name
with no on-disk cache, `custom_kernel.cpp:71` calls it with `name_`, exactly one
arm's source text exists per process, and Apple's own shader cache is
content-addressed on source text.

## Stage 0 — reachability

* Prologue header `lagunaRouterTop8PrologueHeader` at base lines 7594–7622;
  butterfly loop at 7608–7616.
* Interpolated only at `:7645` and `:7771`. It is **not** textually shared with
  `lagunaDecodeRouterOrdinalKernelSource` (maple-nezuko #441's region), so no
  cross-assignment re-scope was needed. The genuinely shared
  `lagunaDecodeRouterOrdinalHeader` (`laguna_router_key_ordinal`,
  `laguna_router_ordinal_before`, ~:8912–8933) was not touched.
* Consumer: `lagunaRoutedSwiGLUQMVPackedTop8R1Kernel` →
  `laguna_routed_nvfp4_swiglu_qmv_packed_top8keys_r1_bf16_v2`.
* Guard chain to defaults, all default-ON:
  `lagunaRoutedGateUpR1Enabled` (`DARKBLOOM_ROUTED_GATEUP_R1 != "0"`),
  `lagunaFusedRoutedSwiGLUQMVEnabled` (~:149), `lagunaPackedScalesEnabled`
  (~:165), `lagunaRouterPrecomputedKeysEnabled` (~:171).
* Dispatch ~`:10208–10218`: grid `(8*256*64, 1, 1)`, threadgroup 64 ⇒ 2048
  threadgroups × 2 simdgroups; **39 calls/decode step**.
* Cost anchor (`research/nezuko-a2-roofline.txt`): 39 × 38.00 µs =
  **1501.7 µs/step**, 9.437 MB/call, 248.3 GB/s = 91.0 % of peak — the largest
  single decode consumer, and memory-bound.

## Stage 1 — offline IR census

`research/maple-fern-router-probe/render.py` extracts the three *shipped* Swift
arm bodies directly out of `LagunaRuntimeModel.swift` (so the census cannot
drift from the shipped text) and compiles each rendered kernel with
`xcrun metal -S -emit-llvm`.

```
shipped_on       {'air.simd_shuffle_xor.u.v2i32': 1}
shipped_ctl      {'air.simd_shuffle_xor.u.i32': 2}
shipped_off      {'air.simd_shuffle_xor.u.i32': 2}
scalar           {'air.simd_shuffle_xor.u.i32': 2}
uint2            {'air.simd_shuffle_xor.u.v2i32': 1}
faultA_offset8   {'air.simd_shuffle_xor.u.v2i32': 1}
faultB_swapped   {'air.simd_shuffle_xor.u.v2i32': 1}
faultC_control   {'air.simd_shuffle_xor.u.i32': 2}
cf_half_shuffles {'air.simd_shuffle_xor.u.i32': 1}
cf_no_shuffles   {}
```

Counts are per butterfly-loop body (the loop is not unrolled at `-S -emit-llvm`),
i.e. per offset ∈ {16, 8, 4, 2, 1}. The **before** census shows 2 × `i32`, so the
compiler does *not* already vectorise the pair — Stage 0's STOP condition does
not fire — and the **after** census shows exactly the intended 1 × `v2i32`.

`diff` of `router_shipped_off.ll` against `router_shipped_ctl.ll` (after
normalising the embedded source-file-name token) is **0 lines**: the invariant
control really is IR-identical.

## Stage 2 — exactness

Offline harness, 2048 cases × 256 keys × 8 extract rounds = 16 384 winners,
reference = the `off` arm (256 distinct winner values, so the test is not
degenerate):

```
off:    mismatch = 0
on:     mismatch = 0
ctl:    mismatch = 0
```

### In-runtime gates

**64-step drift tripwire**
(`correctness --golden correctness_prompts/public_longcopy_gate_english_512_256.json`),
all three arms, on the freshly built worker:

```
off:  "checked_steps" : 64, "passed" : true, "error" : "",
      "golden_hash" : "b9509697c08a2cf3c2943a85f0b76e39c485c441794690fa76835b40a58d7a63"
on:   "checked_steps" : 64, "passed" : true, "error" : "",
      "golden_hash" : "b9509697c08a2cf3c2943a85f0b76e39c485c441794690fa76835b40a58d7a63"
ctl:  "checked_steps" : 64, "passed" : true, "error" : "",
      "golden_hash" : "b9509697c08a2cf3c2943a85f0b76e39c485c441794690fa76835b40a58d7a63"
```

`first_failing_case` / `first_failing_step` / `actual_token` / `expected_token`
are `null` in all three, and the golden hash is identical, so the fused
packed-Top-8 family really did run and really did agree.

**Upstream-equivalence oracle** (`research/run_upstream_equivalence.sh`),
both arms, non-zero selected test count (`EQUIVALENCE_EXACT_STEPS=8` proves the
report marker was reached — the wrapper forces status 3 on a zero-test run):

```
off:  EQUIVALENCE_EXACT_STEPS=8   EQUIVALENCE_EXIT=1
on:   EQUIVALENCE_EXACT_STEPS=8   EQUIVALENCE_EXIT=1
```

Both arms emit a **byte-identical** report:

| step | maxAbsLogitErr | meanAbsLogitErr | runtime tok | upstream tok |
| --- | --- | --- | --- | --- |
| prefill | 0.125 | 0.011933609 | 5991 | 5991 |
| decode-0..7 | 0.0 | 0.0 | 509/902/5991… | identical |

`EQUIVALENCE_EXIT=1` is the **pre-existing, documented M4-Pro-host limitation**,
not a regression: the oracle applies zero tolerance to prefill and the batched
NVFP4 prefill path cannot meet it against the BF16 upstream reference. The exact
same `0.125` / `0.011933609` / token `5991 == 5991` triple is recorded for the
unchanged base in `research/frieren-host-cpu-budget.md:471`,
`research/maple-fern-pr40-result.md:381`,
`research/maple-fern-pr48-fused-norm-qkv-gate.md:462-467` and
`research/CURRENT_RESEARCH_STATE.md:2579`. All eight decode steps are exactly 0
in both arms.

**Rule 35 caveat.** `LagunaUpstreamEquivalence.swift` compares against the
vendored `Laguna.swift` oracle, which does not build the fused packed-Top-8
weight family; the oracle path therefore never reaches
`laguna_routed_nvfp4_swiglu_qmv_packed_top8keys_r1_bf16_v2`. A pass there is
necessary (it proves the guard did not disturb anything else) but is **not**
evidence about this kernel. The evidence that the kernel itself is unchanged is
(a) the offline 16 384-winner exactness table, (b) the IR census, and (c) the
64-step drift tripwire, which does run the fused family.

## Stage 3 — fault injection (mandatory)

| arm | injected fault | detected? |
| --- | --- | --- |
| A | `offset` starts at 8 (drops the 16-lane stage) | **yes**, mismatch = 9 324, first at case 0 round 1 (ref 209, got 67) |
| B | `.x`/`.y` swapped on unpack | **yes**, mismatch = 16 384, first at case 0 round 0 (ref 109, got 1 083 344 912) |
| C | invariant control (`offset > 0u`, scalar) | **no mismatch (0)**, as required |

Non-detections: **none**. Every arm behaved as specified; there is no fault the
harness failed to catch.

## Stage 4 — timing

### In-situ per-kernel ABBA (the decisive measurement)

Instrumentation: `research/nezuko-pr158-gpuprof-hook.patch` (Vendor-side
per-dispatch GPU timing) applied as a temporary commit and reverted before
submission. `DARKBLOOM_GPU_PROFILE_SPLIT=1` puts one dispatch per command
buffer, which is what makes a sub-microsecond per-call effect resolvable;
end-to-end decode wall time (`--local-iterate` MDE ±0.73 % ≈ ±60 µs/step) cannot
see it.

Design: one worker process per slot, three arms, **both** ABBA orders, three
reps each = 36 slots, 33 decode steps per slot, 1 248 profiled calls of
`laguna_routed_nvfp4_swiglu_qmv_packed_top8keys_r1_bf16_v2` per slot. All 36
slots reported `teacher-forced greedy tokens: 0 divergences (all match)`.

Profiler share table from a representative slot — this is also the runtime
confirmation of Stage 0 reachability:

```
  us/step   share  n/step  us/call  kernel
   1494.7  17.55%   39.00    38.33  routed_nvfp4_swiglu_qmv_packed_top8keys_r1_bf16_v2
   1328.1  15.59%   30.00    44.27  decode_nvfp4_qkv_h64_r1_v1_lm1_pw1_se1_sd1
   1111.3  13.05%   30.00    37.04  oproj_act_h64_v1_lm1_pw1_sc1_se1
    863.3  10.14%   39.00    22.14  routed_shared_nvfp4_down_residual_bf16_r1_v5
```

Exactly 39.00 calls/step as predicted, 17.55 % of an 8.52 ms GPU-busy step.

| order | arm | n | mean µs/call | sd | Δ vs `off` (µs/call) | 95 % CI | Δ µs/step |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `off on ctl ctl on off` | `on` | 6 | 38.386 | 0.079 | −0.010 | [−0.098, +0.078] | **−0.4** |
| `off on ctl ctl on off` | `ctl` | 6 | 38.402 | 0.127 | +0.007 | [−0.128, +0.141] | +0.3 |
| `on ctl off off ctl on` | `on` | 6 | 38.444 | 0.198 | −0.011 | [−0.277, +0.256] | **−0.4** |
| `on ctl off off ctl on` | `ctl` | 6 | 38.446 | 0.149 | −0.010 | [−0.247, +0.228] | −0.4 |
| pooled | `on` | 12 | 38.415 | 0.147 | −0.010 | [−0.136, +0.115] | **−0.4** |
| pooled | `ctl` | 12 | 38.424 | 0.134 | −0.001 | [−0.121, +0.118] | −0.1 |

Both orders give the identical point estimate, so process order and thermal
drift are not carrying the result. The **invariant control moves as much as the
candidate** (−0.1 vs −0.4 µs/step, both inside each other's CI): whatever the
`on` arm shows is slot noise, not mechanism.

Score conversion at 0.015280 % decode per µs/step:

* point estimate −0.4 µs/step → **+0.006 % decode score**;
* the most optimistic end of the pooled 95 % CI, −5.3 µs/step → **+0.081 %**;
* the promotion bar of ≈80 µs/step → +1.22 %.

The confidence interval **excludes the bar by a factor of ~15**, so this is a
decisive negative, not an underpowered one.

### Offline isolated probe (kernel-level, 32 repeats, 4.194 M butterfly rounds/step)

```
off      min 3844.9 us/step  median 3849.8  0.917 ns/round  +0.000%
on       min 3846.4 us/step  median 3850.0  0.917 ns/round  +0.040%
ctl      min 3847.1 us/step  median 3858.1  0.917 ns/round  +0.059%
faultA   min 3584.9 us/step  median 3592.1  0.855 ns/round  -6.761%
faultB   min 3855.3 us/step  median 3860.8  0.919 ns/round  +0.271%
```

Independent earlier probe runs on the same rendered kernels:

```
run 1:  scalar +0.000%  uint2 +0.078%  faultA -6.607%  faultB +0.169%  faultC -0.125%
run 2:  scalar +0.000%  uint2 +0.020%  faultC +0.106%  cf_half -0.255%  cf_none -1.098%
```

`cf_half` (one shuffle per stage instead of two — the *ideal* outcome if a
`v2i32` shuffle really were a single hardware op) and `cf_none` (no shuffles at
all) are deliberately wrong counterfactuals used only to bound the mechanism.

### Interpretation

* Removing **all** butterfly shuffle traffic buys **−1.10 %** of the isolated
  prologue's cost. That is the absolute ceiling of this mechanism.
* Halving the shuffle count — the best case the packing could achieve — buys
  **−0.255 %**.
* The real `uint2` arm measures **+0.02 … +0.078 %**, i.e. no gain, and it sits
  inside the invariant control's own band (`ctl` spans −0.125 … +0.106 %).
* `faultA`, which deletes one of five butterfly stages, moves −6.8 %, so the
  probe is demonstrably sensitive to real butterfly work.

Two non-exclusive explanations: (a) `air.simd_shuffle_xor.u.v2i32` is lowered to
two hardware shuffles on Apple GPU generation 16, so the IR win is not a
hardware win; and/or (b) the butterfly is **latency-bound rather than
issue-bound** — the two scalar shuffles are independent and already dual-issued
/ pipelined, so merging them removes no critical-path cycle.

Rule 25 applies in our favour for the *negative* conclusion: a stripped-down
proxy overstates the isolated share of a mechanism, so the in-situ effect can
only be smaller than the numbers above.

## Reproduction

```bash
# preflight
senpai/validate-assignment-scope.sh 730e9c2be89a4ed8cf860e52f930f7ff222d4c95 \
  Sources/MLXFastModel/LagunaRuntimeModel.swift
senpai/check-editable-budget.sh 730e9c2be89a4ed8cf860e52f930f7ff222d4c95

# IR census + exactness + fault injection + offline timing (no GPU lock needed)
python3 research/maple-fern-router-probe/render.py

# correctness (worker must be built first)
CLANG_MODULE_CACHE_PATH="${PWD}/.build-worker/clang-module-cache" \
  swift build -c release --force-resolved-versions \
  --scratch-path .build-worker --product mlxfast-runtime-worker
git checkout -- Package.resolved
research/run_upstream_equivalence.sh
MLXFAST_NO_SANDBOX=1 \
MLXFAST_RUNTIME_WORKER_EXECUTABLE="$PWD/.build-worker/release/mlxfast-runtime-worker" \
  .build/release/mlxfast-swift correctness --weights weights \
  --golden correctness_prompts/public_longcopy_gate_english_512_256.json
# repeat both with DARKBLOOM_ROUTER_UINT2_SHUFFLE=1 and =control

# in-situ per-kernel ABBA (needs the temporary gpuprof hook)
git apply research/nezuko-pr158-gpuprof-hook.patch
# ...rebuild worker...
ORDER="off on ctl ctl on off" bash research/maple_fern_router_uint2_kernel_abba.sh
ORDER="ctl off on on off ctl" bash research/maple_fern_router_uint2_kernel_abba.sh
python3 research/maple_shared_qmv_kernel_stats.py --steps 33 \
  --kernel routed_nvfp4_swiglu_qmv_packed_top8keys_r1_bf16_v2 --per-step 39 \
  --arm-regex '-(off|on|ctl)\.err$' --baseline-arm off \
  /tmp/maple-fern-router-uint2/*.err
git checkout -- Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/device.cpp \
  Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/device.h
```

## Files

* `Sources/MLXFastModel/LagunaRuntimeModel.swift` — the only submitted change.
* `research/maple-fern-router-probe/render.py` — renders the shipped arms plus
  fault/counterfactual variants, runs the IR census, the 16 384-winner exactness
  table, and the isolated GPU timing.
* `research/maple_fern_router_uint2_kernel_abba.sh` — in-situ per-kernel ABBA
  driver.
* `research/maple_shared_qmv_kernel_stats.py` — added `--arm-regex` so the
  three-arm tags parse.
