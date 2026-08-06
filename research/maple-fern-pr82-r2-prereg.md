# PR #82 r2 — pre-registration (written and committed BEFORE any run)

Assignment `maple-2026-08-06f-routed-qmv-router-dedup`, revision `r2`.
Student: maple-fern. Base branch `codex/mlxfast-maple-20260804-advisor`.

**This document is committed before the profiler is applied and before any
measurement is taken.** Its commit SHA is the pre-registration timestamp. The
decision rule in §4 is fixed at that commit and is not edited afterwards; the
r2 report cites it and reports the verdict against it, whatever it is.

---

## 1. What is being measured

The r1 candidate (Variant A) hoists the per-slot top-8 winner out of the routed
gate/up R1 kernel:

| | BASE | CANDIDATE |
|---|---|---|
| kernel name | `laguna_routed_nvfp4_swiglu_qmv_packed_top8keys_r1_bf16_v2` | `laguna_routed_nvfp4_swiglu_qmv_packed_top8idx_r1_bf16_v1` |
| 4th input | `router_keys` (256 × u32) | `indices` (1×1×8 u32) |
| body | `\(lagunaRouterTop8PrecomputedPrelude)` + `uint expert = top8_winner;` | `uint expert = uint(indices[expert_slot]);` |
| header | `lagunaSharedSwiGLUQMVHeader` + `lagunaDecodeRouterOrdinalHeader` + `lagunaRouterTop8PrologueHeader` | `lagunaSharedSwiGLUQMVHeader` |

Submitted diff: `Sources/MLXFastModel/LagunaRuntimeModel.swift` only, +19/−9.
r1 measured this end-to-end on `--local-iterate` and returned
**`inconclusive`**: paired_estimate 0.992096884 (decode −0.896 %) against a
same-arm A/A spread of +1.447 % / +1.764 % / +2.299 % on this host. r2 does not
repeat that measurement. r2 asks the mechanism question the end-to-end
instrument on a sub-64 GiB M4 Pro cannot answer: **did the kernel that was
edited get faster, and did anything structural change around it?**

**SUBMITTED SURFACE IS FROZEN.** `LagunaRuntimeModel.swift` stays byte-identical
to `361a649ac66e97145cf10c165af2f5173f4e48eb` for the whole of r2. Everything
r2 adds is `research/` (not byte-counted) plus a local-only profiler patch to
two non-editable vendor files that is reverted before submission.

---

## 2. Instrument

MLX dispatch profiler, restored verbatim from local-only commit `a8a269d`
(itself a verbatim restore of `64509eb`): 98 insertions across
`Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/device.cpp` (+93) and
`device.h` (+5). Neither path is in `benchmark.json`'s `editablePaths`; neither
is submittable. Revert precedent for the same patch: `8c8b7e6`.

Driver: `research/decode_probe.py --steps 200 --profile --profile-top 44`,
`DARKBLOOM_GPU_PROFILE=1`. Step 0 discarded; 199 steady steps analysed. The
probe also teacher-forces all 200 golden tokens and reports divergences.

Worker build (scored worker path, per #73 §1.5):

```bash
CLANG_MODULE_CACHE_PATH="${PWD}/.build-worker/clang-module-cache" \
  swift build -c release --force-resolved-versions \
  --scratch-path .build-worker --product mlxfast-runtime-worker
git checkout -- Package.resolved
```

`decode_probe.py` hardcodes `.build-worker/release/mlxfast-runtime-worker`, so
each arm is a separate build of that one path.

**Standing caveat, inherited from #73 §1.3 and restated here so it binds this
report:** the per-command-buffer `fputs` inflates *wall*. Profiled absolute wall
is never compared to a non-profiled run. Every conclusion below is drawn from
`gpu_busy_*` (GPU-side timestamps, unaffected) or from ratios inside one run.

### 2.1 Why both SPLIT modes are needed per arm

`DARKBLOOM_GPU_PROFILE_SPLIT=1` forces one dispatch per command buffer. The
profiler emits per-*command-buffer* records only; the per-kernel table is a
Python-side aggregation keyed on the `|`-joined kernel-name list. So:

- **SPLIT=1** is the only configuration that gives clean per-kernel attribution
  (question 1) — but it inflates command-buffer count to 406.
- **SPLIT=0** is the shipped batching and is the only configuration that answers
  the command-buffer-per-step question (question 2, reconcile with 45).
- The difference between the two gives the dispatch-cost correction δ
  (question 5).

Both are therefore run in both arms.

---

## 3. Run plan — counterbalanced, not n=1

ABBA at the arm-block level, two replicates per (arm × split mode):

| # | tree | SPLIT | purpose |
|---:|---|---|---|
| 1 | BASE | 1 | per-kernel attribution |
| 2 | BASE | 0 | shipped batching / δ |
| 3 | CAND | 1 | per-kernel attribution |
| 4 | CAND | 0 | shipped batching / δ |
| 5 | CAND | 1 | replicate |
| 6 | CAND | 0 | replicate |
| 7 | BASE | 1 | replicate |
| 8 | BASE | 0 | replicate |

Temporal order of trees is **B B C C C C B B**, i.e. ABBA. A monotonic thermal
or clock drift over the session cancels to first order in the arm difference.
Three builds only (BASE, CAND, BASE); the two CAND blocks share one build.

Only one model-holding process at a time. Runs are launched through
`run_training`; nothing GPU-touching goes through the terminal.

The 40 °C thermal gate belongs to `benchmark.sh`, not to `decode_probe.py`.
It is not available to this instrument, so it is replaced by (a) ABBA
counterbalancing, (b) a quiet host with no other GPU load, and (c) the
within-arm replicate spread reported as the noise band in §4. This substitution
is declared, not hidden.

---

## 4. Decision rule — PRE-REGISTERED, FIXED AT THIS COMMIT

Verbatim, as assigned:

> **Ship iff the R1 kernel's own corrected true time does not increase, AND
> command-buffer count, dispatch count, and the sum-versus-union relationship
> are all unchanged between arms. Otherwise the arm is closed with a mechanism,
> not with a null.**

Operationalisation, also fixed at this commit:

- **(a) "corrected true time does not increase".** Families are matched by
  *role*, not by name: the BASE `…top8keys_r1_bf16_v2` family and the CANDIDATE
  `…top8idx_r1_bf16_v1` family are the same dispatch slot (39/step, one per MoE
  layer). Let `Δ = mean_CAND − mean_BASE` of the corrected true µs/step for that
  family over the two SPLIT=1 replicates per arm. Let `Δ_noise` be the larger of
  the two within-arm replicate half-ranges of the same quantity. The rule fails
  ("increase") iff `Δ > Δ_noise`. It passes iff `Δ ≤ Δ_noise`. A pass with
  `Δ < −Δ_noise` is additionally recorded as a *measured* reduction; a pass with
  `|Δ| ≤ Δ_noise` is recorded as *not distinguishable from zero at this
  instrument's resolution*, which is a pass of the assigned rule but is reported
  as such and not upgraded into a win.
- **(b) command-buffer count unchanged**: cbs/step equal between arms to the
  probe's 0.1-cb print resolution, in *both* split modes.
- **(c) dispatch count unchanged**: dispatches/step exactly equal between arms
  in both split modes.
- **(d) sum-versus-union relationship unchanged**: in every run of both arms,
  `|gpu_busy_sum − gpu_busy_union| ≤ 2 µs/step`, i.e. decode remains strictly
  serial with zero dispatch concurrency in both arms. If the candidate
  introduced concurrency, per-kernel additivity — the licence for the whole
  arithmetic — would no longer hold and (a) would not be interpretable.
- **Correctness precondition.** Every run must report 0 divergences over the
  200 teacher-forced golden tokens. Any divergence voids that run and, if it is
  a candidate run, closes the arm immediately regardless of timing.

If the rule passes, r2's finding is "the edited kernel did not get slower and
nothing structural moved", and the ship/close decision passes to the advisor
with that mechanism attached. If the rule fails, r2 closes the arm **with the
named mechanism** — which of (a)–(d) failed and by how much — and explicitly
not with "the end-to-end number was inside the noise floor".

---

## 5. Correction: δ-subtraction, and a declared deviation from the brief

The r2 brief asks for "the R1 kernel's own corrected true time **with the §A4
correction stated**". Two facts have to be reconciled here, and this section
records the resolution *before* the numbers exist so it cannot be chosen to
suit them.

**§A4 is not a section of #73.** It is a citation into the campaign record,
quoted at #73 lines 80–91. It is the table of **duplication / serialised
first-touch ratios**:

| family | dup/first-touch ratio |
|---|---:|
| `oproj_act_h64` | 0.601 |
| `residual_rms_router` | 0.605 |
| `gate_sp` | 0.659 |
| `shared_qmv` | 0.721 |
| **`routed_swiglu`** | **0.958** |
| `sliding_attn` | 0.971 |

Its role in #73 is (i) an argument that *in-situ duplication is a biased
instrument* and (ii) an ordering cross-check (#73 §5.3). **It is not applied as
a numeric correction to profiler output anywhere in #73.** Applying 0.958 to a
profiler per-kernel time would be a category error: 0.958 corrects a
*duplication* measurement for cache re-hits, and the profiler does not duplicate
anything.

**The correction #73 actually applies to raw profiler per-kernel time is the
command-buffer-boundary δ**, and it is derived *within the session*, not
imported:

```
δ      = (gpu_busy_sum[SPLIT=1] − gpu_busy_sum[SPLIT=0]) / (cbs[SPLIT=1] − cbs[SPLIT=0])
true µs/step(family) = n × (raw µs/call − δ)
```

#73 measured δ = (8.883 − 8.276) ms / (406 − 45) = **1.681 µs per command
buffer** on this same host, and applied it to give the R1 gate/up family
39 × (40.25 − 1.681) = **1503.9 µs/step true** from 1569.8 µs/step raw (−4.2 %).

**Resolution, pre-registered.** r2 reports the **δ-subtracted** corrected true
time as the primary quantity for decision-rule clause (a), with δ **re-derived
independently in each arm from that arm's own SPLIT=1 and SPLIT=0 runs** — so
the correction cannot smuggle a between-arm difference. The §A4 `routed_swiglu`
ratio **0.958** is *stated*, as the brief requires, and is reported as the
brief's named quantity, but it is not used as the corrective divisor. This is a
declared deviation from the literal wording of the brief in favour of the
arithmetic the instrument actually licenses; if the advisor wants the literal
0.958 multiplication it can be applied to the reported raw numbers after the
fact, and both are tabulated so nothing is lost.

Clause (a) is robust to this choice in any case: δ is subtracted per call in
*both* arms, so if the two arms' δ agree, the sign of `Δ` is identical whether
the correction is applied or not. That invariance is checked and reported.

---

## 6. The five quantities to be reported, per arm

1. Per-kernel true time of the routed gate/up R1 family, with the correction
   stated (δ per arm; §A4 ratio 0.958 quoted alongside).
2. Command buffers per step, reconciled against the shipped structure
   30 + 9 + 6 = 45.
3. `gpu_busy_sum` vs `gpu_busy_union`.
4. Total dispatches per step.
5. The correction ratio used.

Secondary, reported but not part of the rule: total `gpu_busy_sum`/step per arm,
and the `residual_rms_router_bf16_2048_rpg8_keys_v1` family (expected unchanged
— the candidate still *produces* router keys; Variant A only stops one consumer
from reading them, which is the subject of a follow-up arm, not of r2).

---

## 7. Hygiene

- The profiler patch is reverted before submission and the revert SHA is
  recorded in the r2 report.
- `senpai/validate-assignment-scope.sh` and `senpai/check-editable-budget.sh`
  are re-run against `BASE_SHA` after the revert.
- r2's byte delta on the submitted surface is 0 relative to r1.
