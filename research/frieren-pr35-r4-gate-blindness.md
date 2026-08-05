# PR #35 r4 — coherent-addressing blindness of the correctness gate

Student `maple-frieren`, assignment `maple-2026-08-04j-scale-code-width`,
branch `maple-frieren/scale-code-width`, head `b3319dfb`.

All evidence in this document is local harness output on `Mac16,11` / 48 GiB /
macOS 26.5.2. There are no W&B runs for this arm; every number below is
reproducible with the commands in [§7](#7-reproduction).

## 0. Why this document exists

Two independent ranked arms have now shipped a *faulted* kernel through the
public correctness gate and come back with `max_abs_diff 0`:

* fern's faulted run (advisor r4 note), and
* my own mode-5 lane-code reversal, silent over 1025 teacher-forced steps
  (`research/frieren-pr35-r3-b-verification.md`).

The advisor's reading is that "the gate's blindness is coherence, not
magnitude". This document tests that claim directly, and reports the three r4
deliverables: the one-hot flag rate, the exact silent subspace, and the
constant-quadruple fraction.

Two candidate explanations had to be separated:

1. **Null perturbation.** The fault did not actually change any reconstructed
   scale, so the gate had nothing to see. Under this reading the gate is fine.
2. **Coherent blindness.** The fault changed many reconstructed scales, but
   coherently — every row displaced by the same amount — and the greedy argmax
   survived. Under this reading the gate has a real, structured blind spot.

The census in [§2](#2-census-of-the-decode-qkv-scale-plane) kills (1) for mode 5.
The controls in [§3](#3-controls-the-gate-does-see-this-kernel) and the sweep in
[§4](#4-the-one-hot-coherent-addressing-sweep) establish (2).

## 1. Kernel reachability (prerequisite)

A silence result is worthless unless the faulted kernel actually runs on the
checked decode steps. Established, in order:

| Evidence | Result |
| --- | --- |
| Call-site census | `lagunaDecodeNVFP4QKVR1` has exactly one caller, `Sources/MLXFastModel/LagunaRuntimeModel.swift:5907`, inside the `lagunaFusedQKVProjectionEnabled && B == 1 && L == 1` decode block. `fusedQKV` is `nil` for the NVFP4 group-16 bank (it only fires for `.affine` 8/32), so `decodeNVFP4QKVR1` *is* the `qkv` path. |
| Probe 129 (`fatalError` on first lane-major dispatch) | Aborted: `LM_PROBE_REACH: lane-major decode QKV dispatched h48`. Branch reached. |
| Probe 130 (`fatalError` at dispatch #2000) | Aborted: `... dispatch #2000 h64`. At least 2000 lane-major dispatches occur inside the gated region; warmup alone does not plausibly reach that count. |

Both head-count specialisations dispatch, because the tower is mixed:
`LagunaConfig.swift` gives `hiddenSize 2048`, `numKeyValueHeads 8`,
`headDim 128`, `fullAttentionHeads 48`, `slidingAttentionHeads 64`. Fused QKV
bank rows are therefore 8192 for a full-attention layer and 10240 for a sliding
layer, and the census row histogram is exactly `{8192: 10, 10240: 30}` — 10 full
and 30 sliding layers, 389,120 rows total. (An earlier r3 note claimed all 40
layers had 8192 rows; that was wrong, only the 10 full-attention layers do.)

A separate and important operational finding: **worker stderr is captured into
the harness JSON `error` field.** `lagunaTrace` / `note()` output such as
`mlxfast: narrow-scales built lane-major: qkv` is observable there. This
supersedes the earlier belief that worker stderr was unavailable, and is how the
probe assertions above were read.

## 2. Census of the decode QKV scale plane

Instrument: `lagunaLaneMajorCensus(plane:fits:rows:groups:site:layer:)` in
`Sources/MLXFastModel/LagunaRuntimeWeights.swift`, called from
`lagunaLaneMajorNVFP4ScaleBank` immediately after `let fits = span .<= 15`,
guarded on `groups == 128`, output path from `DARKBLOOM_LM_CENSUS`. Raw data:
`/tmp/pr35_lm_census.csv`, 5,160 records = 40 layers × (1 `quad` + 128 `disp`).
Aggregation script: `research/frieren_pr35_census_agg.py`.

### 2.1 Shape

| Quantity | Value |
| --- | --- |
| Layers instrumented (site `qkv`) | 40 |
| Bank rows | 389,120 (`8192 × 10 + 10240 × 30`) |
| Groups per row | 128 (group-16 over 2048 inputs) |
| Scale-plane entries | 49,807,360 |
| Fitting rows (`span ≤ 15`) | 386,666 |
| Escaped rows (`span > 15`) | 2,454 = **0.6307 %** |

### 2.2 The plane is pairwise constant — effective granularity is group-32

`disp[g]` counts rows where `code[g] != code[(g+1) & 127]`.

| Group class | `disp` | Fraction of 389,120 rows |
| --- | --- | --- |
| even `g`, 2 ≤ g ≤ 126 (63 groups) | **exactly 0** | 0 |
| `g = 0` | 89 | 0.0229 % |
| all 64 odd `g` | 280,494 (min, g=87) … 293,382 (max, g=9) | **72.08 % … 75.40 %** |

The zero set is identical in the fitting arm and over all rows. No odd `g` is
anywhere near zero.

This is a structural discovery independent of the correctness question: the
group-16 NVFP4 scale plane of the fused QKV bank is **pairwise constant**, so its
effective granularity is group-32. That is a further 2× compression of the scale
plane on top of deliverable B, and it is reported as a follow-up, not
implemented here.

### 2.3 A whole-plane rotation is not a null perturbation

Summing `disp` over all `g`: 18,176,949 displaced entries of 49,807,360, i.e. a
whole-plane `g → g+1` rotation changes the reconstructed scale of **36.49 %** of
all plane entries (36.45 % restricted to fitting rows). Mode 128 in
[§3](#3-controls-the-gate-does-see-this-kernel) is that rotation.

### 2.4 Constant-quadruple fraction (r4 deliverable 3)

Mode 5 reversed the four codes a lane packs into one `ushort`, i.e. the
quadruple `{l, l+32, l+64, l+96}`. It is a null perturbation only where that
quadruple is constant.

| Quantity | Value |
| --- | --- |
| Lane words examined (fitting rows × 32 lanes) | 12,373,312 |
| Constant quadruples | 537,269 |
| **Constant-quadruple fraction** | **0.043422 = 4.3422 %** |
| Per-layer range | 2.73 % … 13.33 % |
| Per-layer, first 8 layers | 0.0903, 0.1063, 0.0412, 0.0357, 0.0425, 0.1333, 0.0634, 0.0310 |

**Mode 5 was non-null in 95.66 % of lane words.** The advisor's alternative
hypothesis — that mode 5 was silent because it did nothing — is refuted. Its
1025-step `max_abs_diff 0` is genuine gate blindness.

## 3. Controls: the gate *does* see this kernel

The mode 2/3/5 faults of r3 were measured through the *benchmark* harness
(`research/frieren_pr35_lm_gate_pair.sh`, whose `classify()` reads `.metrics`),
not through `mlxfast correctness`. Before drawing any conclusion about the
correctness gate, both directions had to be nailed down against
`mlxfast correctness` itself.

How that gate works — `compareTeacherForcedWithWorker`,
`Sources/MLXFastHarness/LagunaRuntimeCorrectnessCompare.swift:59` — is a real
single-token decode loop: one `beginTeacherForcedCorrectness(promptTokens:)`
512-token prefill, then `teacherForcedCorrectnessStep(previousToken:)` for steps
1…63. A step passes on exact match or a validated true top-logit tie within
`correctnessLogitTieTolerance`. On mismatch it returns immediately, so a
flagging probe exits after 2–3 steps.

| Probe | Perturbation | Verdict |
| --- | --- | --- |
| **131** (negative control) | force every fitting-row code to `0` | **FLAGS.** `passed false`, `checked_steps 2`, `first_failing_step 1`, `first_failing_case longcopy-gate-english-512`, `expected_token 509`, `actual_token 83`, `error "teacher-forced token mismatch"` |
| **128** (coherent control) | whole-plane `g → g+1` rotation, both arms — 36.49 % of plane entries displaced (§2.3) | **SILENT.** `passed true`, `checked_steps 64`, `first_failing_step null` |

These two lines are the core result. The gate is wired to this kernel's output
on checked decode steps — probe 131 proves it — and yet the largest possible
coherent scale-*addressing* displacement passes 64/64 checked steps. Magnitude
is not the discriminator; incoherence is.

Golden hash for both: `b9509697c08a2cf3c2943a85f0b76e39c485c441794690fa76835b40a58d7a63`.

## 4. The one-hot coherent-addressing sweep

Driver: `research/frieren_pr35_lm_probe_sweep.sh`. For probe index `L`, group
`L`'s reconstructed scale is replaced by group `(L+1) & 127`'s scale in **both**
the fitting arm (`sb[L/32]` at `simd_lid == L%32`, source nibble
`nb0[M%32] >> ((M/32)<<2)`) and the escaped arm
(`(weight_scales + out_row*in_vec_size_g)[M]`). `L` arrives through
`DARKBLOOM_LM_PROBE`, is interpolated into the JIT kernel source, and suffixes
the kernel name `_probe<L>`, so no rebuild is needed between values and
`Sources/` is byte-identical across the whole sweep. `L = -1` (unset) leaves the
shipped kernel byte-identical.

The census gives the per-probe perturbation size *a priori*: probe `L`
displaces `disp[L]` of 389,120 rows.

<!-- SWEEP_RESULTS -->

## 5. Byte budget at head `b3319dfb`

`senpai/check-editable-budget.sh 5178d452c513c61e619f4dd788185c797e065529`,
run in a clean detached worktree at `b3319dfb` (the instrumented worktree is
*not* the submission surface):

```
editable budget OK: current=2966629/3000000 bytes headroom=33371 growth=25474/262144 files=142 (file count is diagnostic only; base=142)
```

| Limit | Value | Headroom |
| --- | --- | --- |
| Total surface | 2,966,629 / 3,000,000 | **33,371 B** |
| Growth vs base `5178d452` | 25,474 / 262,144 | 236,670 B |
| `LagunaRuntimeModel.swift` per file | **521,566** / 524,288 | 2,722 B |
| `LagunaUpstreamEquivalence.swift` | 6,501 B | — inside the submitted surface (`editablePaths` lists `Sources/MLXFastModel/` as a directory), so hardening the oracle spends submission bytes |

The binding constraint for the programme is now the **33,371 B total-surface
headroom**, not the per-file cap. My contract stands: nothing new goes into
`LagunaRuntimeModel.swift`; new code goes to `LagunaRuntimeWeights.swift`;
`LagunaRuntimeModel.swift` stays ≤ 523,000 B at submission and at merge.

With the temporary probe instruments present, `LagunaRuntimeModel.swift` is
524,432 B and `mlxfast-swift` prints
`warning: editable file ... is 524432 bytes, above the per-file static review
limit 524288`. Every instrument edit in this document is reverted before any
submission, and the disappearance of that warning is the check.

## 6. Pre-dispatch inject guard (mandatory, r4)

The advisor's r4 note prices a −3.24 % landmine on the advisor integration
branch `5178d452`: `DARKBLOOM_INJECT_DECODE_EMPTY` defaults to `100` and
`DARKBLOOM_INJECT_EMPTY_TG` to `8` there, `lagunaInjectActive` is therefore
`true` with no env var set, and `lagunaInjectLayerWork(...)` is called
unconditionally from the scored per-layer loop — 100 chained empty dispatches
per single-token decode step over 40 layers.

My head is clean, verified against the exact submission commit:

```
$ git show b3319dfb5c13d7c3c669424139d50acaac044f70:Sources/MLXFastModel/LagunaRuntimeModel.swift \
    | grep -n "DARKBLOOM_INJECT_DECODE_EMPTY\|DARKBLOOM_INJECT_EMPTY_TG"
11342:    "DARKBLOOM_INJECT_DECODE_EMPTY", 0)
11354:    "DARKBLOOM_INJECT_EMPTY_TG", 160)
```

`0` and `160` as required. This check is re-run against the actual submission
commit immediately before dispatch and both lines are pasted into the
submission note. No rebase, merge, or cherry-pick from the advisor branch
happens before the receipt; the base is accepted via `accepted_base_sha`.

## 7. Reproduction

```bash
swift build -c release --force-resolved-versions \
  --scratch-path .build-worker --product mlxfast-runtime-worker
git checkout -- Package.resolved
export MLXFAST_RUNTIME_WORKER_EXECUTABLE="$PWD/.build-worker/release/mlxfast-runtime-worker"

# census (one pass)
MLXFAST_NO_SANDBOX=1 DARKBLOOM_LM_CENSUS=/tmp/pr35_lm_census.csv \
  ./.build/release/mlxfast-swift correctness --weights weights \
  --golden correctness_prompts/public_longcopy_gate_english_512_256.json
python3 research/frieren_pr35_census_agg.py

# one-hot sweep (no rebuild between values)
research/frieren_pr35_lm_probe_sweep.sh $(seq 0 127)
```

`MLXFAST_NO_SANDBOX=1` is required only for the census file write: the CLI's
Seatbelt profile (`writeRuntimeWorkerSandboxProfile`,
`Sources/mlxfast-swift/main.swift:1612-1659`) contains `(deny file-write*)` with
only `/dev/null` allowed. It is legal locally and rejected officially; no timed
or ranked number in this document depends on it. The worker environment is a
strict allowlist (`sanitizedRuntimeWorkerEnvironment`,
`LagunaRuntimeWorker.swift:~1996`): `DARKBLOOM_*`, `DYLD_*`, `LC_*`, `MTL_*`,
`METAL_*`, `MLX_*` propagate and every `MLXFAST_*` is stripped, which is why the
probe index travels as `DARKBLOOM_LM_PROBE`.

Note that `mlxfast correctness` prints a trailing non-JSON note line after the
JSON object, so parsing must `raw_decode` from the first `{` rather than
`json.loads(t[t.find('{'):])`.

## 8. Follow-ups (not implemented)

1. **Group-32 scale plane.** §2.2 shows the QKV group-16 plane is pairwise
   constant, so the scale plane can be halved again on top of deliverable B.
2. **Incoherent fault mode.** The sweep measures coherent displacement. A
   row-dependent (incoherent) displacement of the same magnitude is the natural
   next probe and would bound where the gate's sensitivity actually starts.
3. **`o_proj` instruction-issue discriminator.** Zero-byte 256-entry-LUT
   variant for the r1 narrow-`o_proj`-alone anomaly (+69.5 µs/step at 4.1× its
   byte roofline). Held until after the receipt.
4. **`attn.o` lane-major extension** (−19.6 MB/step). Held.
