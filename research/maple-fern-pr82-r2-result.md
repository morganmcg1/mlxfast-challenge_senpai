# PR #82 r2 — profiled mechanism measurement of Variant A

Assignment `maple-2026-08-06f-routed-qmv-router-dedup`, revision `r2`.
Student: maple-fern. Pre-registration: `research/maple-fern-pr82-r2-prereg.md`,
committed at `8b383a2` **before** the profiler was applied and before any run.

**Headline.** The edited kernel really did get faster — by 3.15 % corrected,
far outside noise — and *no* structural quantity named by the decision rule
moved. The pre-registered rule therefore reads "ship". **It should not be
shipped**, and r2 says why with a measurement rather than a null: the arm
difference in total GPU busy time **flips sign** between the profiler
configuration in which the rule's clause (a) is measurable and the batching
that actually ships, and the shipped-batching sign reproduces r1's end-to-end
regression. The structural cause is a quantity the rule does not name:
**Variant A deterministically reorders decode dispatches** without changing
their count.

**Recommendation: close the Variant A arm, with the mechanism below.** A
concrete successor arm that would keep the win is named in §8.

---

## 0. Provenance and hygiene

| item | value |
|---|---|
| base (advisor head) | `6a19fd74bf64e6bde9d2a3c5d7f7970588803cab` |
| candidate tree measured | `361a649ac66e97145cf10c165af2f5173f4e48eb` (r1, unchanged) |
| pre-registration commit | `8b383a2` |
| profiler applied (local-only) | `bb08f01` (cherry-pick of `a8a269d`) |
| **profiler reverted** | **`239cd1a`** |
| submitted surface after revert | `Sources/MLXFastModel/LagunaRuntimeModel.swift` only, +19/−9 |
| byte-identical to r1 | yes (`git diff --quiet 361a649 HEAD -- <that file>` → clean) |
| `Vendor/` vs advisor head | clean (0 files) |
| scope check | `assignment scope OK: 1 submitted path(s)` |
| budget check | `OK: current=2930746/3000000 headroom=69254 growth=662/262144` |
| growth vs r1 | 0 bytes |

The submitted surface was frozen for the whole of r2, as instructed. Nothing
outside `research/` and the two reverted vendor files was touched.

Host: Mac16,11 M4 Pro, 20 GPU cores, 48 GiB unified (low-memory startup
profile). Apple GPU generation 16 → no `_nax` kernels; all 406 decode
dispatches are hand-written `laguna_*` kernels, so decode is fully M4
screenable. Prefill is not touched by this arm and is not measured here.

Instrument: MLX dispatch profiler restored verbatim from `a8a269d`, 98
insertions in `device.cpp` (+93) and `device.h` (+5). Neither path is in
`editablePaths`. Driver `research/decode_probe.py --steps 200 --profile
--profile-top 44`; step 0 discarded, 199 steady steps.

**Standing caveat (#73 §1.3).** The per-command-buffer `fputs` inflates *wall*.
No profiled wall number below is compared to a non-profiled run. Every
conclusion is drawn from `gpu_busy_*` (GPU-side timestamps, unaffected) or from
ratios inside one run.

**Thermal-gate substitution (declared in the pre-registration).**
`decode_probe.py` has no 40 °C gate. It is replaced by ABBA counterbalancing at
the arm-block level, a quiet host with no other GPU load, and the within-arm
replicate spread reported as the noise band. Temporal tree order was **B B C C
C C B B**, as pre-registered, so monotonic thermal or clock drift cancels to
first order in the arm difference.

---

## 1. All eight runs

Every run: **0 divergences over 200 teacher-forced golden tokens**, exit 0.
Order is temporal.

| # | arm | SPLIT | wall ms | `gpu_busy_sum` ms | `gpu_busy_union` ms | sum−union µs | cbs/step | disp/step |
|--:|---|--:|--:|--:|--:|--:|--:|--:|
| 1 | BASE | 1 | 9.998 | 8.654 | 8.653 | 1 | 406.0 | 406.0 |
| 2 | BASE | 0 | 8.382 | 8.108 | 8.108 | 0 | 45.0 | 406.0 |
| 3 | CAND | 1 | 9.966 | 8.607 | 8.606 | 1 | 406.0 | 406.0 |
| 4 | CAND | 0 | 8.460 | 8.182 | 8.182 | 0 | 45.0 | 406.0 |
| 5 | CAND | 1 | 9.888 | 8.639 | 8.638 | 1 | 406.0 | 406.0 |
| 6 | CAND | 0 | 8.384 | 8.133 | 8.133 | 0 | 45.0 | 406.0 |
| 7 | BASE | 1 | 10.116 | 8.687 | 8.684 | 3 | 406.0 | 406.0 |
| 8 | BASE | 0 | 8.383 | 8.094 | 8.094 | 0 | 45.0 | 406.0 |

Raw logs: `research/pr82-r2-logs/run{1..8}_*.txt`.

Supervised-run handles. This campaign has no W&B runs, so the durable handle
for each run is its `run_training` ID. All eight reached terminal state
`finished` with exit code 0; none was cancelled, killed, or truncated, so no
pending run can change the conclusion.

| # | arm | SPLIT | `run_training` ID | terminal state |
|--:|---|--:|---|---|
| 1 | BASE | 1 | `9007d5b8-bed8-4001-b7f9-fe0c85427705` | finished (0) |
| 2 | BASE | 0 | `eca0c95c-5f7b-42a5-b294-ff2dedc98a1d` | finished (0) |
| 3 | CAND | 1 | `921c2988-0966-4ae3-8df0-9859752b0870` | finished (0) |
| 4 | CAND | 0 | `ef990b7a-e165-407d-80de-3b230cca6546` | finished (0) |
| 5 | CAND | 1 | `cc8970c2-7c58-4dc5-8661-ce42d51b2d12` | finished (0) |
| 6 | CAND | 0 | `88bd7747-8907-4cc0-8d49-a8371522c300` | finished (0) |
| 7 | BASE | 1 | `45b5d167-8dcb-4b6e-a5a1-f8234e8c02de` | finished (0) |
| 8 | BASE | 0 | `d152ad03-6807-4cd6-b4c5-5637179b9530` | finished (0) |

The divergence certificate is the literal line `teacher-forced greedy tokens:
0 divergences (all match)`, present once in each of the eight logs and nowhere
contradicted; no log contains any `error`, `fail`, or `mismatch` line.

Command-buffer totals are also bit-identical across arms: 9666 total / 8955
inside the window in *both* SPLIT=0 arms, and 89042 / 80794 in *both* SPLIT=1
arms.

---

## 2. The five requested quantities, per arm

### (1) Per-kernel true time of the routed gate/up R1 family

Families matched by **role**, not name — same dispatch slot, 39 calls/step, one
per MoE layer. BASE `…top8keys_r1_bf16_v2`; CAND `…top8idx_r1_bf16_v1`.

Raw, from the SPLIT=1 runs (the only configuration with per-kernel
attribution):

| arm | run | µs/call | µs/step |
|---|---|--:|--:|
| BASE | 1 | 38.22 | 1490.7 |
| BASE | 7 | 38.43 | 1498.6 |
| CAND | 3 | 36.79 | 1434.6 |
| CAND | 5 | 36.97 | 1441.8 |

| | BASE | CAND | Δ |
|---|--:|--:|--:|
| raw mean µs/call | 38.325 | 36.880 | −1.445 |
| raw mean µs/step | 1494.65 | 1438.20 | **−56.45** |
| within-arm half-range µs/step | 3.95 | 3.60 | — |
| **δ-corrected true µs/step** | **1433.15** | **1388.03** | **−45.12 (−3.15 %)** |
| noise band Δ_noise µs/step | — | — | 4.10 |

`|Δ| = 45.12 ≫ Δ_noise = 4.10`, so this is a **measured reduction**, not a
tie. Clause (a) passes.

### (2) Command buffers per step

**45.0 in both arms**, all four SPLIT=0 runs, to the probe's 0.1-cb print
resolution. This reconciles exactly with the shipped structure quoted in the
brief: **30 + 9 + 6 = 45**. SPLIT=1 forces 406.0 in both arms, as designed
(one dispatch per command buffer). Unchanged between arms in both modes →
clause (b) passes.

### (3) `gpu_busy_sum` vs `gpu_busy_union`

Per-step gap, all runs: BASE {1, 0, 3, 0} µs; CAND {1, 0, 1, 0} µs. Against
`gpu_busy_sum ≈ 8100–8690 µs` this is 0.00 %–0.035 %. **Decode is strictly
serial with no dispatch concurrency in either arm**, which is what licenses the
per-kernel additivity that the whole of §2(1) rests on.

**Honest exception.** My pre-registered numeric proxy for clause (d) was
`|sum − union| ≤ 2 µs/step in every run`. Run 7 measures **3 µs**, one
microsecond over the bar, at the probe's 1 µs print resolution. I report the
exceedance rather than widening the bar after the fact. Two things about it:
it is in the **BASE** arm, so it cannot be an effect of the candidate; and the
candidate arm is at or below the baseline arm on this quantity in every matched
position. The assigned question — "is the sum-versus-union *relationship*
unchanged between arms" — is answered *unchanged*, but the reader should know
the proxy was not met exactly.

### (4) Total dispatches per step

**406.0 in all eight runs**, both arms, both split modes — exactly equal, not
merely within resolution. Clause (c) passes.

Note this is the axis #48 already closed (−40 dispatches / −39 barriers bought
−0.1488 %, receipt `285f79fa`), which is why the r2 brief rejected F2. Variant
A does not move it at all.

### (5) The correction ratio used

**δ-subtraction, re-derived independently per arm** from that arm's own runs:

```
δ    = (busy_sum[SPLIT=1] − busy_sum[SPLIT=0]) / (cbs[SPLIT=1] − cbs[SPLIT=0])
true = n × (raw µs/call − δ)
```

| arm | busy_sum SPLIT=1 | busy_sum SPLIT=0 | Δcb | **δ (µs/cb)** | per-replicate-pair δ |
|---|--:|--:|--:|--:|---|
| BASE | 8670.5 µs | 8101.0 µs | 361 | **1.5776** | 1.5125 / 1.6427 |
| CAND | 8623.0 µs | 8157.5 µs | 361 | **1.2895** | 1.1773 / 1.4017 |

Both bracket #73's 1.681 µs/cb on this host. The two arms' δ differ by
0.288 µs/cb against within-arm half-ranges of 0.065 and 0.112 — marginally
distinguishable at n=2. The difference works **against** the candidate (CAND
receives the smaller subtraction), so the corrected Δ = −45.12 is the
*conservative* number; raw is −56.45.

**Invariance check, as pre-registered.** With a single shared δ = 1.4336 in
both arms the corrections cancel and Δ = **−56.36 µs/step** — same sign, larger
magnitude. The sign of Δ does not depend on the correction.

**§A4, as the brief requires it to be stated.** §A4 is not a section of #73; it
is the duplication / serialised-first-touch ratio table quoted at #73 lines
80–91, in which `routed_swiglu` = **0.958**. Its role in #73 is an
anti-duplication argument and an ordering cross-check, not a numeric correction
to profiler output — the profiler does not duplicate anything, so multiplying
its per-kernel time by a duplication-bias ratio would be a category error. This
deviation was declared in the pre-registration (§5) before any number existed.
Applied literally anyway, for completeness: BASE 1494.65 × 0.958 = 1431.87,
CAND 1438.20 × 0.958 = 1377.79, **Δ = −54.08 µs/step (−3.78 %)** — same sign
again. All three corrections agree.

---

## 3. Pre-registered decision rule — verdict

> **Ship iff the R1 kernel's own corrected true time does not increase, AND
> command-buffer count, dispatch count, and the sum-versus-union relationship
> are all unchanged between arms. Otherwise the arm is closed with a mechanism,
> not with a null.**

| clause | verdict | evidence |
|---|---|---|
| (a) corrected true time does not increase | **PASS** (measured reduction) | −45.12 µs/step vs Δ_noise 4.10 |
| (b) command-buffer count unchanged | **PASS** | 45.0 / 45.0 (SPLIT=0), 406.0 / 406.0 (SPLIT=1) |
| (c) dispatch count unchanged | **PASS** | 406.0 in all 8 runs, exactly |
| (d) sum-versus-union relationship unchanged | **PASS**, proxy exceeded once | serial in both arms; run 7 (BASE) 3 µs vs a 2 µs bar |
| correctness precondition | **PASS** | 0 divergences, 8/8 runs |

**The rule as assigned reads "ship".** §4 explains why acting on that would be
a mistake, and §5 gives the structural quantity the rule does not name.

---

## 4. Why the rule is not sufficient: the split-mode sign flip

Total `gpu_busy_sum` per steady step, by configuration:

| config | BASE mean (hr) | CAND mean (hr) | Δ | Δ % |
|---|--:|--:|--:|--:|
| SPLIT=1 (1 dispatch / cb) | 8670.5 µs (16.5) | 8623.0 µs (16.0) | **−47.5** | **−0.548 %** |
| SPLIT=0 (**shipped batching**) | 8101.0 µs (7.0) | 8157.5 µs (24.5) | **+56.5** | **+0.698 %** |

`hr` = within-arm replicate half-range. Both deltas sit outside their noise
bands (2.9× and 2.3× respectively).

The same candidate, same build, same session, same host: **0.55 % less GPU busy
time under one-dispatch-per-command-buffer, 0.70 % more under the batching that
actually ships.**

The SPLIT=1 total is internally consistent with §2(1): the R1 family alone
accounts for −56.5 µs and the total moves −47.5 µs, the +9 µs remainder being
noise across 43 other families. So under SPLIT=1 the kernel win is real and it
does show up in the total.

**Cross-check against r1's end-to-end result.** r1's paired decode measurement
was −0.896 % (paired_estimate 0.992096884), which the r1 report called
inconclusive against an A/A spread of +1.447 % / +1.764 % / +2.299 %. The
SPLIT=0 profiled busy time implies −0.693 % decode speed. **Same sign, same
order of magnitude, from a completely different instrument.** The mechanism
instrument in shipped-batching configuration reproduces the end-to-end result
that the end-to-end instrument could not resolve on this host.

The consequence for the decision rule is direct. Clause (a) is *only*
measurable under SPLIT=1, because the profiler emits per-command-buffer records
and the per-kernel table is a Python-side aggregation keyed on the `|`-joined
kernel-name list — with batching on, a "kernel" row is a whole command buffer.
So the rule's central clause is evaluated in the one configuration this session
has shown does not predict the shipped one. That is a limitation of the rule
discovered by executing it, and I report it rather than reinterpreting the rule
to suit the numbers.

---

## 5. The structural quantity the rule does not name: dispatch **order**

Dispatch count is identical (406). Dispatch **order inside the command buffer
is not**. From the 5-kernel MoE command-buffer group, deterministic in both
replicates of both arms:

```
BASE:  residual_rms_router…keys_v1
    →  shared_nvfp4_swiglu_qmv_rows1_bf16_v1
    →  decode_router_top8_ordinal_table_norm_v1
    →  routed_nvfp4_swiglu_qmv_packed_top8keys_r1_bf16_v2
    →  routed_shared_nvfp4_down_residual_bf16_r1_v5

CAND:  residual_rms_router…keys_v1
    →  decode_router_top8_ordinal_table_norm_v1      ← hoisted
    →  shared_nvfp4_swiglu_qmv_rows1_bf16_v1         ← displaced
    →  routed_nvfp4_swiglu_qmv_packed_top8idx_r1_bf16_v1
    →  routed_shared_nvfp4_down_residual_bf16_r1_v5
```

**Why.** In BASE the routed kernel reads `router_keys`, produced by
`residual_rms_router…keys_v1` — the *first* kernel of the block — so the
ordinal-table kernel sits off the critical path. Variant A repoints that edge
to `indices`, produced by `decode_router_top8_ordinal_table_norm_v1`. The
dependency chain lengthens to
`rms_router → ordinal_table → routed_R1`, and MLX's topological scheduler
responds by hoisting the ordinal-table kernel ahead of the shared-expert QMV.

**Where the +56.5 µs lands.** Comparing SPLIT=0 command-buffer groups with
order-insensitive keys (`research/pr82-r2-logs/split0_group_compare.py`), every
group containing the MoE block is slower in the candidate and every group
without it is flat:

| group | BASE mean µs/step | CAND mean µs/step | Δ | contains MoE? |
|---|--:|--:|--:|:-:|
| `[10] sliding_attn … qmv_rows1` (n=10) | 1826.7 | 1842.9 | **+16.2** | yes |
| `[10] residual_rms_router … sliding_attn` (n=8) | 1468.0 | 1476.9 | **+9.0** | yes |
| `[12] rms … qmv_rows1` (n=5) | 1117.5 | 1123.8 | **+6.3** | yes |
| `[5] residual_rms_router … qmv_rows1` (n=4) | 291.0 | 297.6 | **+6.6** | yes |
| `[10] rms … sliding_attn` (n=3) | 538.8 | 545.3 | **+6.5** | yes |
| `[11] sliding_attn … full_attn_grow` (n=4) | 811.1 | 816.8 | **+5.7** | yes |
| `[12] gate_sp_h48 … sliding_attn` (n=4) | 892.5 | 894.8 | **+2.3** | yes |
| `[8] sliding_attn … qmv_rows1` (n=1) | 131.6 | 133.6 | **+1.9** | yes |
| `[5] full_attn_grow … dense_down_residual` (n=1) | 457.2 | 459.0 | +1.8 | no (dense) |
| `[4] rms … lmhead` (n=1) | 433.4 | 433.7 | +0.3 | no |
| `[3] rms \| gate_sp_h48 \| qkv_h48` (n=1) | 40.8 | 40.9 | +0.1 | no |
| `lmhead_exact_fused_int5_sparse_refine_v1` (n=1) | 76.2 | 75.9 | −0.2 | no |
| `[2] gather \| argmax` (n=1) | 13.0 | 12.7 | −0.3 | no |
| `decode_embedding_rope_atlas_bf16_2048_v2` (n=1) | 3.6 | 3.6 | 0.0 | no |
| **TOTAL** | **8101.2** | **8157.4** | **+56.2** | |

MoE-containing groups sum to **+54.5 µs/step**; the non-MoE remainder is
+1.7 µs, essentially the dense group's +1.8. Across 39 MoE blocks that is
**+1.40 µs per MoE block per step**.

Against **−1.45 µs/call** for the R1 kernel measured in isolation, the two
almost exactly cancel — and the batching penalty is the slightly larger of the
two. That is the whole result in one line: *Variant A makes the kernel cheaper
by 1.45 µs and makes the command buffer around it more expensive by 1.40 µs,
and the second effect is invisible to any per-kernel instrument because
measuring per-kernel requires destroying the batching that creates it.*

Kernels whose behaviour should not change indeed did not:
`residual_rms_router_bf16_2048_rpg8_keys_v1` 320.5 / 319.6 / 321.0 / 318.8
µs/step and `decode_router_top8_ordinal_table_norm_v1` 206.4 / 206.0 / 205.2 /
205.8 µs/step, flat across both arms. The candidate still *produces* router
keys; Variant A only stops one consumer reading them.

---

## 6. What r2 answers that r1 could not

r1 asked "is the candidate faster end to end?" and got −0.896 % against a
±2.3 % A/A spread — a number with no mechanism attached, which is why it was
correctly filed inconclusive. r2 answers three separable questions:

1. **Did the edited kernel get faster?** Yes, −3.15 % corrected, 11× the noise
   band. The optimisation hypothesis behind Variant A is *correct*.
2. **Does that survive the shipped batching?** No. Total busy moves +0.70 % the
   wrong way, agreeing with r1's end-to-end sign.
3. **Why?** A deterministic dispatch reordering forced by the new dependency
   edge, costing +1.40 µs per MoE block — slightly more than the kernel saves.

So r1's inconclusive is upgraded to a *negative with a named cause*, and the
arm closes on mechanism rather than on a noise floor.

---

## 7. Honest limitations

- **n=2 per arm × split mode.** The two decisive deltas clear their noise bands
  by 2.3× and 2.9×, not by 10×. The CAND SPLIT=0 replicates (8.182 / 8.133) are
  the noisiest pair in the session; its half-range of 24.5 µs is 43 % of the
  +56.5 µs effect. A third replicate per cell would tighten this materially and
  is the cheapest possible follow-up (~45 s per run).
- **M4 Pro, not the ranked M5.** Apple GPU generation 16, 20 cores, 48 GiB.
  Decode is 100 % hand-written `laguna_*` kernels here so no `_nax` reachability
  problem exists, but the *scheduler's* reordering decision and the size of the
  batching penalty are both plausibly core-count- and generation-dependent. The
  reordering itself is a graph-topology consequence and should reproduce; its
  µs cost need not.
- **Clause (d) proxy exceeded once** (§2(3)), in the baseline arm.
- **δ differs between arms** by 0.288 µs/cb, marginally outside the within-arm
  spread. Handled by reporting all three corrections, which agree in sign.
- **Profiled wall is inflated** by the per-command-buffer `fputs` and is never
  compared across instruments; only `gpu_busy_*` is.
- The SPLIT=0 group table matches groups by kernel *multiset*, which is exactly
  what makes the ordering change visible — but it also means the +1.40 µs/block
  is attributed to "the MoE command buffer", not to a specific kernel inside
  it. Localising it further would need a profiler that timestamps within a
  command buffer.

---

## 8. Follow-ups — reported, not implemented

**Directly suggested by this mechanism (highest value):**

- **Variant A′ — keep the cheap read, keep the order.** If the reordering is
  the cause, a variant that lets the routed R1 kernel read the small `indices`
  buffer *without* lengthening the chain past `shared_nvfp4_swiglu_qmv_rows1`
  should keep the −1.45 µs/call and drop the +1.40 µs/block. Two routes:
  produce the 8-entry index vector in `residual_rms_router_bf16_2048_rpg8_keys_v1`
  itself (already upstream of everything in the block, already writing router
  state), or make the routed kernel depend on both so the scheduler's existing
  order remains valid. This is the arm r2 makes testable, and it is now a
  *predicted* win rather than a hopeful one.
- **Third replicate per cell** before acting on either sign (~6 min total).

**Carried forward from r1, unchanged:**

- **Dead `router_keys` production.** Variant A makes `router_keys` dead work on
  the default path (`lagunaRoutedGateUpR1Enabled` defaults true, `:7511`;
  consumers at `:7645` R1 and `:7656` non-R1; producer
  `lagunaResidualRMSNormRouterKernels` `:991-1010`, `routerStore` `:861-871`,
  wrapper `:1055-1096`). Removing it is a separate arm — and note it would also
  change the dependency graph again, so it must be measured with this same
  instrument. Worth ~318 µs/step of `residual_rms_router` work at most, though
  only the keys-specific fraction is recoverable.
- **Stale R1-selection guard** at `:10028`.
- **Stale `routerKeys` preconditions** at `:7640-7641`.
- `DARKBLOOM_ROUTER_PRECOMPUTED_KEYS=0` is **not** a clean control — it
  switches kernel family.

**Instrument note for the campaign.** Any future arm that changes a kernel's
*inputs* can change MLX's topological dispatch order even when it changes
neither dispatch count nor command-buffer count. Per-kernel profiling under
`SPLIT=1` cannot see this by construction. The cheap detector is the SPLIT=0
group name-list: compare the `|`-joined order between arms. That check costs
one 45 s run per arm and would have flagged this arm before r1 spent an
end-to-end measurement on it.

---

## 9. Reproduction

```bash
# profiler (local only; revert before any submission)
git cherry-pick a8a269d

# per-arm worker build
CLANG_MODULE_CACHE_PATH="${PWD}/.build-worker/clang-module-cache" \
  swift build -c release --force-resolved-versions \
  --scratch-path .build-worker --product mlxfast-runtime-worker
git checkout -- Package.resolved

# one run (SPLIT=1 for per-kernel attribution, SPLIT=0 for shipped batching)
DARKBLOOM_GPU_PROFILE=1 DARKBLOOM_GPU_PROFILE_SPLIT=1 \
  python3 research/decode_probe.py --steps 200 --profile --profile-top 44

# group comparison across the four SPLIT=0 logs
python3 research/pr82-r2-logs/split0_group_compare.py
```

Arm order B B C C C C B B; three builds (BASE, CAND, BASE); one model-holding
process at a time; all runs launched through `run_training`.

**No W&B runs.** This campaign's W&B project has no runs; evidence is the
committed logs under `research/pr82-r2-logs/` and this report.
