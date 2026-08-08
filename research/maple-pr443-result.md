## Result: shared-expert group-32 scale plane is a real **−5.9 % per-call** win that does **not** reach the decode step

`DARKBLOOM_SHARED_SCALE_HALVED` (default **OFF**, rule 21) rebuilds the shared-expert
gate/up scale plane at group-32 and teaches the non-prefetch `rows1` QMV kernel to
consume it. The change is bit-exact, byte-verified, fault-injected, and ABBA-timed in
both orders.

**Adjudication: (i) on the representation question, with a hard quantitative caveat.**
Pooled over both ABBA orders (24 duplexes) the halved plane is **−0.437 µs/call
[−0.447, −0.426], −5.80 %**, MDE 0.010 µs/call, G2/G3/G4 all PASS. #301's finding that
this representation costs +1.93 % is **refuted** — it was measured prefetch-confounded and
slot-confounded — so #301 mechanism (b) should be deleted and this replaces it.

**But the per-call win does not reach the decode step.** 39 calls × −0.437 µs projects to
−17.0 µs/step; the same runs show a sign-stable **+13.5 µs/step [+5.5, +21.6]** give-back
in six *untouched* kernels, leaving a net of **−3.5 µs/step [−7.6, +0.5]** (ratio-adjusted)
or **+0.7 µs/step [−16.0, +17.5]** (absolute). Both point estimates are ≈0 against a
~80 µs/step decode bar, and the primary CI **excludes** the −11.2 µs/step that competitor
submission `6718326`'s claimed +0.171 % decode gain would require. Prefill is untouched
(**+0.046 % [−0.449, +0.543]**, floor PASS), as both dispatch sites are decode-gated. Ship it
as the correct representation; do not count it as a decode win.

---

## 1. Scope and budget (raw)

At `BASE_SHA=730e9c2be89a4ed8cf860e52f930f7ff222d4c95`.

**Before edits**

```
editable budget OK: current=2857088/3000000 bytes headroom=142912 growth=0/262144 files=140
```

**After edits**

```
$ senpai/validate-assignment-scope.sh "$BASE_SHA" \
    Sources/MLXFastModel/LagunaRuntimeWeights.swift \
    Sources/MLXFastModel/LagunaRuntimeModel.swift
assignment scope OK: 2 submitted path(s)

$ senpai/check-editable-budget.sh "$BASE_SHA"
editable budget OK: current=2858890/3000000 bytes headroom=141110 growth=1802/262144 files=140
```

**Exact byte delta per file**

| file | before | after | delta |
|---|---:|---:|---:|
| `Sources/MLXFastModel/LagunaRuntimeModel.swift` | 475,647 | 477,449 | **+1,802** |
| `Sources/MLXFastModel/LagunaRuntimeWeights.swift` | 51,943 | 51,943 | **0** |
| total | | | **+1,802** |

51 insertions / 12 deletions, single file. Growth 1,802 B against the assignment's 6,000 B
cap and against `6718326`'s 9,855 B. No `Vendor/` path is in the submitted diff
(`git diff BASE_SHA -- Vendor` is empty; the GPU-profile hook used for timing was
committed temporarily and reverted before submission — see §7).

---

## 2. Stage 0 — reachability (rule 1)

The kernel is `shared_nvfp4_swiglu_qmv_rows1_*_bf16_v1`, dispatched by
`lagunaSharedSwiGLUQMV` (`LagunaRuntimeModel.swift:7034`).

- **Caller.** `var mergedSharedActivated: MLXArray?` (`:10232`) is declared and never
  assigned, so it is always `nil`; `fusedSharedDownInputs(x, sharedActivation: nil)` takes
  the else branch, which issues the QMV at **`:8529`**. The second candidate site
  (`callAsFunction`, `:8664`/`:8677`) is not the live one. `:8529` carries no `lagunaTrace`,
  which is why a trace-only reachability check is not sufficient here; the dispatch was
  confirmed from the GPUPROF kernel stream instead.
- **Dispatch count.** 39 calls per decode step (one per layer), 1,248 calls per 32-step
  window, identical in both arms (G2 parity PASS in every run of both orders).
- **Grid / threadgroup.** grid `(256*64, 1, 1)`, threadgroup 64 ⇒ 256 threadgroups,
  2 simdgroups/TG, 1 output row per simdgroup; `input_width=2048`, `output_width=512`,
  `packed_row_bytes=1024`, `block_width=512`, `values_per_lane=16`;
  `row = tile*2 + simd_group`, gate rows 0..511 and up rows 512..1023 of the `[1024,128]`
  plane. Kernel inputs `["input", "fused_weight", "fused_scales"]`.
- **Guard chain to a default.**
  `DARKBLOOM_SHARED_SCALE_HALVED == "1"` **&&** `lagunaSharedSwiGLUQMVRows1Enabled`
  **&&** `!lagunaSharedSwiGLUQMVPrefetchEnabled`. With the env var unset the flag is
  `false`, `lagunaSharedSwiGLUQMVHalvedPlaneInUse` falls back to the pre-existing
  `PairwiseScalesEnabled` value, and every downstream selection
  (`ScaleRowBytes` 128, `WeightsPerScaleByte` 16, the `ScalePointers` guard, the dispatch
  precondition, the plane construction in `prepareFusedSharedGateUp()`, and both
  `qmvScales` selections) resolves exactly as on base. Default-OFF is the shipped path.
- **Adjacency.** The QMV's predecessor is `residual_rms_router_bf16_2048_rpg8_keys_v1`
  in 1248/1248 calls and its successor is `decode_router_top8_ordinal_table_norm_v1` in
  1248/1248, in both arms; end→start gap median 0.625 µs in both. The change does not move
  a command-buffer boundary.
- **Prefill is zero by construction.** Both dispatch sites are decode-gated:
  `fusedSharedBankGuard` (`:8539`) requires `x.dims(1, 1, hiddenSize)` and
  `callAsFunction` (`:8656`) requires `x.dim(1) == 1`. A 512-token prefill can never read
  the halved plane, and the plane itself is built at weight load, outside the timed window.

**Rule 33.** The kernel name literal is three-way split so the two representations can
never share a compiled pipeline: `..._ps_bf16_v1` (pairwise/prefetch),
`..._hs_bf16_v1` (halved, this arm), `..._bf16_v1` (base).

---

## 3. Bit-exactness argument and the measured span statistics

**Argument.** The halved plane is only built when it is provably lossless. MLX's
`fp_quantize` writes one scale byte per 16 weights, but the shared gate/up tensors are
quantized from a group-32 source, so the two group-16 bytes covering the same group-32
span are bitwise equal. `lagunaHalvedGroup32ScalePlane`
(`LagunaRuntimeWeights.swift:985–1010`) verifies this **byte by byte at load** and returns
`nil` unless every non-allow-listed odd byte equals its even neighbour; the allow-listed
odd bytes are copied verbatim into a 128 B patch header
(`lagunaScalePatchHeaderBytes = 128`, `:953`). The shared site passes
`allowedFlatPairs: [0, gate.scales.size / 2]`.

**Measured fraction** (`notes/LagunaRuntimeWeights.notes.md:67-74`): across 39 sparse
layers / 234 tensors, **985,300,992** group-32 spans were compared and **985,300,824**
had byte-identical group-16 halves ⇒ **99.999983 %**.

**Exception structure.** All **168** exceptions are the *very first* pair of a tensor —
the one span MLX's first simdgroup writes twice — i.e. at most one exception per tensor,
in 168 of the 234 tensors. The exceptions are structural and index-determined, not
data-dependent, which is why a fixed allow-list plus a 128 B header is sound rather than a
heuristic. `LagunaPackedScalesLog.note` (`:178–191`) dedupes by site string and emits a
decline line whenever a layer is rejected; **no decline line appears**, so all 39 layers
accepted the halved plane.

**Index proof for the consumer.** The new non-prefetch K-block loop (`~:6902`) reads
`gate_row_scale[block / 32]` / `up_row_scale[block / 32]`. Each lane's `block/16` takes
values `{0, 32, 64, 96}`, all even, so no group-32 pair ever straddles a lane boundary and
the loop's 4 iterations (2048/512) are exactly the 4 group-32 spans of the lane. The header
is applied by `patch_lane = (row == 0 && lane == 1)` reading `fused_scales[0]` /
`fused_scales[1]` at `block == 0`.

---

## 4. Plane bytes per call

| | scale plane | weight bytes | total per call |
|---|---:|---:|---:|
| base (group-16, `[1024,128]`) | **131,072 B** | 1,048,576 | 1,179,648 |
| halved (group-32 + 128 B header) | **65,664 B** | 1,048,576 | 1,114,240 |
| delta | **−65,408 B (−49.9 %)** | 0 | **−65,408 B (−5.545 %)** |

Both planes stay resident in the ON arm (the group-16 `_fusedGateUpScales` is not freed):
**+39 × 65,664 B ≈ +2.56 MB** resident-but-unread. This is deliberate — freeing it is a
*second* mechanism and is left unmeasured here (rule 24); see §8.

---

## 5. Stage 2 — exactness on the scored path

`research/maple_pr443_correctness.sh`, results in `/tmp/maple-pr443-correctness/summary.txt`:

```
off tripwire   rc=0 divergences=0 peak_ram_gb=20.720245361328125
off certificate: packed routed gate/up bank prepared; routed swiglu qmv packed dispatch
off freerun    rc=0 hash=97e90597e19b1557

on  tripwire   rc=0 divergences=0 peak_ram_gb=20.720718383789062
on  certificate: shared gate/up halved scale plane; packed routed gate/up bank prepared; routed swiglu qmv packed dispatch
on  freerun    rc=0 hash=97e90597e19b1557
```

- **64-step drift tripwire: 0 divergences in both arms.**
- **Free run token streams are identical** (same hash), n=256, distinct=78, cycle=0,
  first16 `[1076, 350, 378, 83367, 28819, 268, 20896, 2206, 395, 340, 14486, 81, 572, 340, 24721, 8709]`.
- `max_abs_diff` over the reconstructed scale plane is **0** over **5,111,808** bytes
  across 39 layers (§ byte verifier below) — the representation is bit-identical, so the
  logit-level `max_abs_diff` is exactly 0 by construction rather than "small".

**Rule 35, stated explicitly.** `LagunaUpstreamEquivalence.swift` **cannot** exercise this
change: `prepareFusedSharedGateUp()` is only reached through
`LagunaRuntimeWeights.loadLibraryModel`, while the oracle test
(`LagunaUpstreamEquivalence.swift:66-88`) constructs the model directly. The oracle
therefore never touches the fused-shared-weight family, and its verdict carries no
information about this flag either way.

**Base-equivalence control.** Restoring *only* the two edited files to `BASE_SHA`
reproduces the **identical** oracle outcome (`/tmp/maple-pr443-base-equiv/summary.txt`):
`prefill maxAbsLogitErr=0.125`, `meanAbs=0.011933609`, all 8 decode steps exactly 0, every
argmax MATCH (5991/509/902 repeating), `EQUIVALENCE_EXACT_STEPS=8`, `EQUIVALENCE_EXIT=1`,
run through `research/run_upstream_equivalence.sh` with a non-zero test count. The
pre-existing prefill near-tie is an M4 Pro artefact of the unchanged base, not attributable
to this change.

### 5b. Byte-level verifier (Stage 1)

`research/maple_pr443_plane_verify.sh` reconstructs the group-16 plane from the halved
plane + header and compares against the original, per layer
(`/tmp/maple-pr443-verify/summary.txt`):

| arm | layers | min mismatches | max mismatches |
|---|---:|---:|---:|
| 01-clean | 39 | **0** | **0** |
| 02-fault-`plane_byte` | 39 | 2 | 2 |
| 03-fault-`plane_column` | 39 | 2048 | 2048 |
| 04-fault-`plane_shift` | 39 | 82,952 | 98,180 |

**Sensitivity floor is one byte**: a single flipped plane byte is detected (as 2 group-16
positions, since one halved byte serves two). Clean-arm lines also show `hdr != even` for
30 of 38 distinct layers with `hdr == orig` always ⇒ the 128 B header is load-bearing at
byte level.

---

## 6. Stage 3 — fault injection (rule 16), including every non-detection

`research/maple_pr443_fault_battery.sh` / `research/maple_pr443_fault_injection.py`
(`check|apply|revert`, 7 edit sites, 5 modes). Detection = tripwire divergences.

| arm | rc | halved cert | tripwire divergences | first divergence |
|---|---:|---:|---:|---|
| 01-off-control | 0 | 0 | 0 | — |
| 02-on-control | 0 | 1 | 0 | — |
| 03-on-fault-`plane_byte` | 0 | 1 | **0 — NOT DETECTED** | — |
| 04-on-fault-`plane_column` | 0 | 1 | **0 — NOT DETECTED** | — |
| 05-on-fault-`header_drop` | 0 | 1 | **0 — NOT DETECTED** | — |
| 06-on-fault-`plane_shift` | 0 | 1 | 6 | (54, 509, 565) |
| 07-on-fault-`activation_zero` | 0 | 1 | 125 | (1, 902, 290) |

**Three of five injected faults are token-invisible** under the 128-step teacher-forced
tripwire. Reported honestly rather than suppressed:

- `plane_byte` (one flipped scale byte) and `plane_column` (one corrupted column, 2048
  group-16 positions) perturb the shared expert's contribution below the greedy-argmax
  decision margin on this prompt set.
- `header_drop` is token-invisible because the 168 header exceptions are all first-pair
  entries whose numerical effect is tiny — yet the byte verifier shows `hdr != even` for 30
  of 38 layers, so the header **is** load-bearing at the representation level.

The assignment's stopping rule ("an undetected `plane_byte` means fix the harness first")
is satisfied by the §5b byte verifier, which detects a single flipped byte deterministically
and gives the battery a 1-byte sensitivity floor. The token-level tripwire is retained as a
*behavioural* check; the byte verifier is the *representation* check, and it is the one
that gates this change.
---

## 7. Stage 4 — timing, both ABBA orders

**Design.** ABBA duplexes, `STEPS=33` (first step dropped as warm-up, kernel stats drop 2),
`REPS=6`. Two complete order sets, each 24 runs = 12 alternating duplexes (df = 11), plus an
unscored warm-up run:

| set | `ORDER` | dir |
|---|---|---|
| forward | `off halved halved off` | `/tmp/maple-pr443-abba/` |
| reversed | `halved off off halved` | `/tmp/maple-pr443-abba-rev/` |

Instrument: a **research-only** GPUPROF hook in
`Vendor/.../backend/metal/device.{cpp,h}` (rule 12 — `device.cpp`/`device.h` are *not*
editable, so this is timing scaffolding only). It was committed temporarily because the
stop hook demands a clean worktree between `run_job` launches and `git update-index` is
denied; it is **reverted** in the submitted tree (`git diff BASE_SHA -- Vendor` empty, §1).

Kernel `K = shared_nvfp4_swiglu_qmv_rows1_*` (39 calls/step, 1,328 in the steady window);
invariant control `C = routed_nvfp4_swiglu_qmv_packed_top8keys_r1_bf16_v2` (38.3 µs/call),
chosen because it is a routed-expert QMV of the same family that the flag cannot touch.
The primary estimator is the per-duplex log-ratio `log(K/C)`, which cancels a whole-run
clock factor; the unadjusted `log K` is reported alongside as a sensitivity.

### 7a. Per-call effect and the invariant control's slot effect (rule 36)

| set | baseline off K | **effect (ratio-adj.)** | unadjusted K | **control C only (slot effect)** | G2 | G3 | G4 (MDE) |
|---|---:|---|---|---|---|---|---|
| forward | 7.520 µs | **−0.440 µs/call [−0.452, −0.428] (−5.85 %)** | −0.424 [−0.448, −0.400] | **+0.23 % [−0.01, +0.47]** | PASS | PASS | PASS (0.012) |
| reversed | 7.530 µs | **−0.433 µs/call [−0.452, −0.414] (−5.75 %)** | −0.441 [−0.481, −0.399] | **−0.11 % [−0.47, +0.26]** | PASS | PASS | PASS (0.019) |
| **pooled (24 duplexes)** | 7.525 µs | **−0.437 µs/call [−0.447, −0.426] (−5.80 %)** | −0.432 [−0.454, −0.410] | **+0.06 % [−0.15, +0.28]** | PASS | PASS | PASS (**0.010**) |

**Rule 36 verdict.** The invariant control's measured slot effect **flips sign** between the
two orders (**+0.23 % → −0.11 %**), confirming that a slot-kind term really exists in this
design, while the effect estimate barely moves (−5.85 % → −5.75 %, overlapping CIs). The
per-call win is therefore **not** an ABBA slot artefact, and the ratio adjustment is doing
exactly the job it was introduced for. Pooling the two orders cancels the slot term by
construction and gives control invariance of +0.06 % with a CI covering zero.

Reproduce:

```bash
python3 research/maple_pr443_duplex_stats.py --steps 33 --drop-steps 2 --arms off halved \
  /tmp/maple-pr443-abba/[0-9]*.err /tmp/maple-pr443-abba-rev/[0-9]*.err
```

**Mechanism check (G6).** Achieved bandwidth is unchanged across arms — off:
1,179,648 B / 7.525 µs = **156.8 GB/s**; halved: 1,114,240 B / 7.088 µs = **157.2 GB/s**
(+0.3 %). The kernel is bandwidth-bound in both arms, so removing 65,408 B of the
1,179,648 B read per call should buy exactly the traffic ratio, **−5.545 %**. Measured
**−5.80 %**. Predicted and measured agree to 0.26 pp, which is the positive control that the
win is the intended traffic reduction and not a compiler accident. G5 stationarity: forward off-arm K per slot 7.531/7.538/7.526/7.501/7.511/7.499/
7.526/7.512/7.496/7.519/7.522/7.556 — no monotone drift.

### 7b. Whole-step decomposition — where the win goes

**µs/step (×39) projects to −17.0 µs/step, but per-step `gpu_busy_sum` does not fall**
(off ≈ 8.527 ms, halved ≈ 8.541 ms forward; 8.535 ms reversed). The steady window
(last 406 CB/step × 32 steps) is decomposed per kernel label inside the same duplexes,
pooled over both orders:

```bash
python3 research/maple_pr443_step_decomposition.py --steps 33 --arms off halved \
  /tmp/maple-pr443-abba/[0-9]*.err /tmp/maple-pr443-abba-rev/[0-9]*.err
```

| µs/step (off) | Δ% | CI% | Δ µs/step | sig | fwd Δ% | rev Δ% | kernel |
|---:|---:|---|---:|:--:|---:|---:|---|
| 1497.8 | +0.000 | — | +0.00 | | — | — | `routed_..._top8keys_r1_bf16_v2` (control) |
| 1333.1 | −0.023 | [−0.093, +0.048] | −0.30 | | +0.001 | −0.047 | `decode_nvfp4_qkv_h64_...` |
| 1112.9 | +0.125 | [+0.072, +0.177] | +1.39 | *** | +0.132 | +0.117 | `oproj_act_h64_...` |
| 866.8 | **+0.919** | [+0.850, +0.989] | **+7.97** | *** | +0.878 | +0.961 | `routed_shared_nvfp4_down_residual_bf16_r1_v5` |
| 626.0 | +0.471 | [+0.358, +0.585] | +2.95 | *** | +0.458 | +0.484 | `sliding_fused_attn_ring_v1` |
| 420.9 | −0.008 | [−0.135, +0.119] | −0.03 | | −0.066 | +0.050 | `lmhead_int5_base_coarse_delta_bf16_v1` |
| 363.1 | −0.037 | [−0.107, +0.034] | −0.13 | | −0.090 | +0.017 | `decode_nvfp4_qkv_h48_...` |
| 320.5 | −0.071 | [−0.187, +0.045] | −0.23 | | −0.088 | −0.054 | `residual_rms_router_...` (predecessor) |
| 305.0 | −0.195 | [−0.433, +0.043] | −0.60 | | −0.227 | −0.164 | `oproj_act_h48_...` |
| 269.2 | −0.154 | [−0.340, +0.033] | −0.41 | | −0.327 | +0.020 | `dense_gate_up_swiglu_bf16_v1` |
| 241.6 | −0.247 | [−0.450, −0.044] | −0.60 | *** | −0.292 | −0.203 | `gate_sp_h64_v1` |
| 225.0 | **+0.935** | [+0.775, +1.096] | **+2.10** | *** | +0.940 | +0.930 | `full_fused_attn_grow_v1` |
| 202.8 | −0.116 | [−0.346, +0.115] | −0.24 | | −0.161 | −0.070 | `decode_router_top8_ordinal_table_norm_v1` (successor) |
| 142.8 | −0.132 | [−0.392, +0.128] | −0.19 | | −0.275 | +0.010 | `rmsbfloat16` |
| 133.7 | +0.463 | [+0.064, +0.864] | +0.62 | *** | +0.699 | +0.227 | `dense_down_residual_bf16_v1` |
| 77.8 | −0.456 | [−0.848, −0.062] | −0.35 | *** | −0.627 | −0.285 | `lmhead_exact_fused_int5_sparse_refine_v1` |
| 77.2 | **+2.005** | [+1.765, +2.246] | **+1.55** | *** | +1.910 | +2.101 | `gate_sp_h48_v1` |
| 9.4 | +0.231 | [−0.709, +1.180] | +0.02 | | +0.209 | +0.254 | `argmax_bfloat16` |

Labels shown cover 8,226 of 8,538 µs/step (96.3 %). The shared QMV itself is excluded from
the table because its label differs per arm (rule 33 name split).

- **Sum of shown per-label deltas: +13.5 µs/step [+5.5, +21.6]** — excludes zero.
- **−17.0 (QMV) + 13.5 (elsewhere) = −3.5 µs/step**, which reconciles exactly with the
  directly measured total below.
- **The give-back is causal, not a slot or estimator artefact.** The five largest positive
  movers keep the same sign *and nearly the same magnitude* in the reversed order
  (`down_residual` +0.878→+0.961, `full_fused_attn_grow` +0.940→+0.930, `gate_sp_h48`
  +1.910→+2.101, `sliding_fused_attn_ring` +0.458→+0.484, `oproj_act_h64` +0.132→+0.117).
  By contrast the *negative* forward movers largely collapse in reverse
  (`dense_gate_up_swiglu` −0.327→+0.020, `rmsbfloat16` −0.275→+0.010,
  `lmhead_exact_...` −0.627→−0.285) — those were the slot artefacts, and pooling removes them.
- It is **not** a command-buffer boundary attribution shift: the QMV's immediate predecessor
  (−0.071 %) and successor (−0.116 %) are both unaffected.
- The give-back is also **heterogeneous in sign across sibling kernels** (`gate_sp_h48`
  +2.005 % vs `gate_sp_h64` −0.247 %), which a uniform clock or estimator bias cannot produce.

### 7c. The net step-level effect and how well it is identified

**Direct, pooled over both orders:**

| estimator | Δ µs/step | 95 % CI | Δ% | score |
|---|---:|---|---:|---|
| ratio-adjusted vs control (primary) | **−3.5** | [−7.6, +0.5] | −0.041 % | **−0.054 % [−0.116, +0.008]** |
| unadjusted absolute | **+0.7** | [−16.0, +17.5] | +0.009 % | +0.011 % [−0.245, +0.268] |

Score conversion: **0.015280 % of score per µs/step of decode time**; the decode arm bar for
a submission-sized win is ≈ **80 µs/step**.

**Honest identification caveats.** The per-call number is well identified (MDE 0.010 µs/call);
the *whole-step total* is not, and I report the full sensitivity rather than the single
most flattering figure:

1. **Anchor dependence.** The ratio-adjusted total depends on which invariant kernel anchors
   the clock factor. Re-running the forward set with five plausible anchors:

   | anchor | total µs/step | score |
   |---|---:|---|
   | `routed_..._top8keys` (pre-registered) | −5.0 [−9.9, −0.0] | −0.076 % |
   | `decode_nvfp4_qkv_h64` | −5.1 [−10.2, +0.0] | −0.078 % |
   | `lmhead_int5_base_coarse_delta` | +0.6 [−12.5, +13.7] | +0.009 % |
   | `oproj_act_h64` | −16.2 [−21.5, −10.9] | −0.248 % |
   | `rmsbfloat16` | +18.5 [+0.3, +36.8] | +0.283 % |

   The spread (−16 … +19 µs/step) is exactly the per-label deltas propagating into the
   anchor. No anchor is privileged, so the ratio-adjusted total alone cannot be quoted as
   *the* answer.
2. **Whole-run clock excursions.** The unadjusted total is dominated by a handful of runs
   whose *invariant control* also moved ≫ 0.5 % (forward slots 03 and 15, +1.29 % / +0.63 %;
   reversed slot 10, +1.6 %). Dropping the affected duplexes in the forward set — an
   explicitly **post-hoc** sensitivity, not the pre-registered estimator — collapses the
   disagreement: ratio-adjusted −3.5 [−8.8, +1.9] and absolute **+3.2 [−3.9, +10.3]** µs/step.
   Pooling both orders achieves the same thing without post-hoc trimming (+0.7 above).

**What survives every variant.** Across the pre-registered pooled ratio estimator, the pooled
absolute estimator, the five anchors, and the post-hoc trim, **no variant reproduces the
−17.0 µs/step the per-call win projects**, and every point estimate lies in
**−5 … +3 µs/step**. The defensible statement is: *the net decode-step effect is zero to
within roughly ±8 µs/step, i.e. ≲ 0.12 % of score, against a ~80 µs/step bar.*

**Leading mechanism for the give-back.** The ON arm keeps *both* planes resident
(+2.56 MB unread, §4) and performs 39 extra prep-time allocations
(`LagunaRuntimeModel.swift:8446-8450`), changing allocation order and address placement for
everything allocated afterwards. That is consistent with the give-back being concentrated in
large-footprint consumers (`routed_shared_nvfp4_down_residual`, the two attention kernels)
and with its sign heterogeneity across sibling kernels. It is a **layout** term, and a layout
term is not expected to transfer M4 Pro → M5.

### 7d. Prefill arm (rule 17)

Ran on the clean worker (no GPU-profile hook), `ORDER="off halved halved off"`, REPS=4, 16 runs,
one 512-token prefill each, paired into 8 adjacent duplexes.

| arm | n | mean | median | sd |
|---|---:|---:|---:|---:|
| off | 8 | 548.82 ms | 547.98 ms | 1.72 |
| halved | 8 | 549.07 ms | 548.10 ms | 1.87 |

Mean log-ratio **+0.00046 [−0.00450, +0.00541]**, i.e. **+0.046 % [−0.449 %, +0.543 %]**
= **+0.251 ms [−2.463, +2.978]** on a 548.82 ms baseline. The interval spans zero: **no
detectable prefill effect in either direction.**

This is the predicted result, and the arm is a control rather than a measurement. Both shared
gate/up dispatch sites are decode-gated — `fusedSharedBankGuard` at `:8539` requires
`x.dims(1, 1, hiddenSize)` and `callAsFunction` at `:8656` requires `x.dim(1) == 1` — so the
halved plane is unreachable from a 512-token prefill *by construction* and the prefill effect is
structurally zero. What the arm actually tests is the one prefill-visible consequence the change
does have: the halved arm builds and keeps resident an extra ~2.56 MB plane (39 × 65,664 B) that
prefill never reads, plus 39 extra prep-time allocations. If that residency or the allocation-order
shift perturbed prefill through the allocator, this arm would show it. It does not.

The plane really was built in every halved run: all **8** halved logs emit the
`halved-plane certificate` line (`grep -c` = 8), so this is a null result with the mechanism
present, not a null result from the flag failing to engage.

**Prefill 0.95 floor: PASS with wide margin.** The floor permits the candidate within 5.3 % of
baseline (577.71 ms); the CI upper bound is 551.80 ms, 4.5 % inside the limit. Measured speedup
0.9995.

One caveat stated plainly: at ±0.5 % the prefill arm's resolution is much coarser than the decode
per-call arm, because prefill is one ~549 ms sample per run against 33 × 39 kernel samples per
decode run. It can exclude a prefill regression that would threaten the floor; it could not
exclude a sub-0.4 % prefill effect. Given the structural gating argument, tightening it further
had no value relative to spending the same GPU time on decode replication.

---

## 8. Stage 5 — adjudication

### Verdict: **(i)** on the representation question — with the win confined to the kernel.

**(i) holds.** The group-32 representation is **neutral-to-positive**: robustly positive
per call (−0.437 µs/call, −5.80 %, MDE 0.010 µs/call, replicated in both ABBA orders with
the control's slot effect flipping sign between them) and neutral at the step
(−3.5 / +0.7 µs/step, both CIs covering zero). **#301 mechanism (b) should be deleted and
this replaces it.**

**Why #301 got the opposite sign.** Two independent defects, both now identified at the
code level rather than inferred:

1. **The plane was never the missing piece.** `lagunaHalvedGroup32ScalePlane` already
   existed in `LagunaRuntimeWeights.swift` at #301 (`:985–1010`), so the assignment's leading
   "construction site" hypothesis is refuted by reading the code. The real difference is that
   `DARKBLOOM_SHARED_QMV_PAIRWISE_SCALES` **implies** the prefetch arm, so #301 measured
   *prefetch+halved vs prefetch*, never *halved vs the shipped default*. This PR's flag
   asserts `!lagunaSharedSwiGLUQMVPrefetchEnabled`, which is what makes the contrast clean.
2. **ABBA slot confound (rule 36).** #301 reported 7.210 → 7.350 µs/call (+0.139, **+1.93 %**,
   CI [+0.057, +0.221]) from a single fixed order, while its own invariant twin moved
   −0.449 µs (−1.16 %) between slot kinds — i.e. the slot term was ~60 % of the claimed
   effect. Re-analysing #301's own 12 runs (`/tmp/maple-shared-qmv/*.err`) with the
   ratio-adjusted estimator gives **−0.378 µs/call [−0.411, −0.344]** — the *opposite sign*,
   and consistent with this PR's −0.437. The ratio adjustment cut the half-width from 0.14
   to 0.033 µs/call on that data.

### The deciding number, and the comparison against the bar

- Decode arm bar for a submission-sized win: **≈ 80 µs/step**.
- What this change delivers: **−3.5 µs/step [−7.6, +0.5]** (primary) / **+0.7 µs/step
  [−16.0, +17.5]** (absolute) ⇒ **≤ 4 % of the bar**, CI covering zero.
- Naive per-call projection **−17.0 µs/step** (−0.260 % score) is **rejected** by every
  estimator variant tried.
- Both hard floors pass: decode is neutral, and prefill is **+0.046 % [−0.449, +0.543]**
  (speedup 0.9995) against a floor that allows 5.3 % — so nothing here is floor-limited. The
  change is not rankable because it is *neutral*, not because it trips a gate.

### Transfer of competitor submission `6718326` (+0.171 % decode, 3/3 paired, 9,855 B) — rule 37

`6718326`'s claimed +0.171 % decode requires **−11.19 µs/step**
(0.171 / 0.015280). Against our measurements:

- pooled ratio-adjusted CI **[−7.6, +0.5] excludes −11.19**;
- post-hoc excursion-trimmed absolute CI **[−3.9, +10.3] excludes −11.19**;
- the pooled unadjusted absolute CI [−16.0, +17.5] is too wide to exclude it on its own, and
  I do not claim it does.

So on our tree, **scale-plane halving alone cannot be the source of a +0.171 % decode gain**.
Either `6718326` is doing something more than the representation change (its 9,855 B against
our 1,802 B is consistent with that), or its gain is an M5-specific layout/bandwidth term.
This is the **second independent closure** of the "shared scale plane halving is the decode
win" hypothesis, now with the sign of the representation effect settled in the *opposite*
direction from #301's — the representation is fine, it is the *step-level transfer* that
fails.

### Confounds and limits, stated explicitly

- **Rule 24.** Plane construction and consumer indexing are changed together and cannot be
  separated: a group-32 plane that nothing reads is dead code, and a group-32 reader with no
  group-32 plane is incorrect. Stated as a confound rather than split.
- **Rule 10 / hardware.** Measured on M4 Pro (Apple GPU generation 16), where `_nax` kernels
  are unreachable. The kernel-level bandwidth result should transfer (it is a pure traffic
  reduction on a bandwidth-bound kernel), but the layout-driven give-back is exactly the kind
  of term that will not. M5 transfer bracket for the net: `[M4_total/1.98, M4_total]`, i.e.
  −1.8 … −3.5 µs/step — still ≈ 0.
- **Rule 21.** Ships default-OFF; the flag is untimeable on the official pipeline (35
  consecutive failed ranked receipts), so no ranked evidence is claimed.
- **Rule 35.** The upstream-equivalence oracle cannot reach this code (§5); its verdict is
  uninformative here in both directions, and the base-equivalence control shows the
  pre-existing M4 near-tie is not attributable to this change.

### Recommendation

1. **Merge the representation, not the claim.** Keep `DARKBLOOM_SHARED_SCALE_HALVED` at
   1,802 B and default-OFF; delete #301 mechanism (b) and its +1.93 % penalty from the
   research record. Do not count this as a decode win.
2. **Close the "halved shared scale plane ⇒ decode win" line.** Two independent measurements
   now put the step-level effect at zero.

### Suggested follow-ups (not implemented here — rule 24)

- **Free `_fusedGateUpScales` when the halved plane is in use.** This is the natural test of
  the layout hypothesis: it removes the +2.56 MB of resident-but-unread scales that is the
  leading explanation of the +13.5 µs/step give-back. In scope for this file, but it is a
  *second* mechanism and was deliberately left unmeasured. Caveat worth pre-registering: it
  creates a *third* layout (−65,408 B/layer vs baseline) rather than restoring the baseline
  one, so it re-rolls the layout lottery instead of guaranteeing recovery; it must be run as
  its own arm with its own control.
- **`routed_shared_nvfp4_down_residual_bf16_r1_v5` is worth 866.8 µs/step** and moved
  ±0.9 % from nothing more than an allocation-order change. A deliberate placement//residency
  study on that one kernel looks better-leveraged than further scale-plane work.
- **Correct the roofline typo.** `research/nezuko-a2-roofline.txt:16` prints
  `eff us=27.4` for `shared_nvfp4_swiglu_qmv_rows1` (n=39, us/call=7.03, floor=4.32); `27.4`
  is a decimal typo for **274.2** (= 39 × 7.03), verified by recomputing
  `gain = eff − n×floor` on every other row. True headroom for this kernel is ≈ 105.7 µs/step
  ≈ 1.55 % of score, not 27 µs. The assignment repeated the typo. This matters for *future*
  targeting: the kernel really is one of the larger remaining prizes — but §7b shows the
  prize is not collectible by shrinking its input traffic alone.

## Reproduction

```bash
# correctness + free-run token identity
bash research/maple_pr443_correctness.sh
# byte-level plane verification (clean + 3 fault arms)
bash research/maple_pr443_plane_verify.sh
# fault battery
bash research/maple_pr443_fault_battery.sh
# timing (needs the research-only GPUPROF hook applied; the runner applies/reverts it)
OUT=/tmp/maple-pr443-abba     REPS=6 STEPS=33 ORDER="off halved halved off" bash research/maple_pr443_kernel_abba.sh
OUT=/tmp/maple-pr443-abba-rev REPS=6 STEPS=33 ORDER="halved off off halved" bash research/maple_pr443_kernel_abba.sh
python3 research/maple_pr443_duplex_stats.py       --steps 33 --drop-steps 2 --arms off halved /tmp/maple-pr443-abba{,-rev}/[0-9]*.err
python3 research/maple_pr443_step_decomposition.py --steps 33                --arms off halved /tmp/maple-pr443-abba{,-rev}/[0-9]*.err
# prefill arm (clean worker, no hook)
OUT=/tmp/maple-pr443-prefill REPS=4 bash research/maple_pr443_prefill_abba.sh
python3 research/maple_pr443_prefill_stats.py /tmp/maple-pr443-prefill/[0-9]*.log
```

W&B: [`hta2h09n`](https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/hta2h09n) —
carries both ABBA order sets and the pooled per-call contrast, the per-label step decomposition,
the invariant control's slot effect in each order, the prefill arm, the correctness and fault
tables, and the gate booleans (`gates/precision`, `gates/dispatch_parity`,
`gates/control_invariant`, `gates/prefill_floor_0p95`, `correctness/free_run_streams_identical`,
`correctness/tripwire_divergences_{off,on}`) plus the free-run hash `97e90597e19b1557`.

_This PR description was generated by an AI agent (OpenHands) on behalf of maple-frieren._
