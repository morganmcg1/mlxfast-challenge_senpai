# R106-C — Is decode serialised when it does not have to be?

**Student:** maple-fern · **PR** #617 · **assignment** `maple-r106-c-decode-serialisation-ledger`
· **revision** `r106-c-rev1` · **base** `codex/mlxfast-maple-20260804-advisor` @ `0954002`

**Verdict: N-CRITICAL (with V-CONCURRENT for H1). Stage 3 not built; the gate did
not open, by 25x.**

One paragraph: the steady one-token decode step issues **408 dispatches** and
charges **247 barriers** across **47 command buffers**. Reconstructing the exact
runtime dependency graph from a per-dispatch input/output *byte-range* trace,
MLX's greedy grouping produces **289 barrier-separated concurrent groups**, and
the theoretical minimum over *any* legal reordering (longest chain in the
conflict DAG) is **288**. The headroom is therefore **one group = 1.30 us/step =
0.020 % of `cs`**, against a preregistered Stage-3 gate of 33 us/step. Decode is
not "serialised when it does not have to be": **70.6 % of the step is a genuine
serial data-dependence chain**, and MLX already extracts essentially all of the
available concurrency. The `L`-residual is not a scheduling artefact.

---

## 0. Executive ledger

| quantity | value | note |
|---|---|---|
| dispatches / decode step | 408 | matches the R105-E family ledger exactly |
| charged barriers / step | 247 | independently reproduces PR #268's 247 |
| command buffers / step | 47 | 46 boundaries |
| hazard **separations** / step | 288 | 247 charged + 41 free at encoder boundaries |
| greedy groups (MLX's actual) | **289** | pointer granularity **and** byte-range granularity |
| minimum groups (any reordering) | **288** | RAW+WAR **and** RAW-only; ptr **and** range |
| **headroom** | **1 group** | = 1.3003 us/step = **0.0198 % of `cs`** |
| Stage-3 gate | 33 us/step | **CLOSED — 25.4x short** |
| absolute ceiling (also perfectly aligning CB boundaries) | 7.80 us/step | 0.119 % of `cs`, still 4.2x short |
| serial-chain fraction | 288 / 408 = **70.6 %** | mean 1.417 dispatches per level |
| label-weighted critical path (descriptive only) | 7725.8 / 8528.3 us = **90.6 %** | Rule 82: inadmissible for pricing |

Artefacts: `research/artifacts/fern-r106c/dag_ledger.json`,
`research/artifacts/fern-r106c/decode_step_dispatches.tsv`.
Instrument: `research/r106c/scripts/{trace_dag.patch,run_dag_trace.sh,dag_ledger.py}`.

---

## 1. The instrument, and how each edge was derived

R103-B's `trace.patch` logged pipeline name, grid and threadgroup. That is not
enough to build a dependency graph: it says *what* ran, not *what it touched*.
I extended it into `research/r106c/scripts/trace_dag.patch` (324 lines,
research-only). Per dispatch it now emits one TSV row:

```
seq  kernel  kind  grid  threadgroup  args  barrier_fired  encoder_id  inputs  outputs
```

where `inputs`/`outputs` are the exact `MTL::Resource*` **plus byte offset plus
byte size** of every array bound through `set_input_array` /
`set_output_array`, i.e. `ptr+offset:bytes` tokens. `barrier_fired` is the real
value of `needs_barrier_` at the moment `maybeInsertBarrier()` ran, and
`encoder_id` is the identity of the `MTL::ComputeCommandEncoder` the dispatch
was encoded into.

The patch touches
`Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/device.{cpp,h}` only. It is
**never submitted** (see §6) and is applied/reverted around the trace build. The
tracing build was incremental (46.4 s); the traced run took 42.8 s and produced
11,254 dispatch rows (2.79 MB).

**Correctness during tracing was intact** — the tracer only writes a log, it
does not change dispatch. `trace_report.json`: `expected_token = actual_token =
902`, `actual_expected_logit_delta = 0`, `matched_prefix_steps = 6`,
`golden_hash b9509697...`.

**Edge definition.** For dispatches `i < j` in the emitted order, there is an
edge `i -> j` iff

* **RAW**: some output byte range of `i` overlaps some input byte range of `j`; or
* **WAR/WAW** (anti-dependency): some input or output byte range of `i`
  overlaps some output byte range of `j`.

Every edge is therefore derived from *observed* buffer traffic, not from a model
of the Swift code. I computed the graph twice: once at **buffer-pointer**
granularity (what MLX actually tracks — `prev_inputs_` / `prev_outputs_` are
`std::unordered_set<MTL::Resource*>`) and once at **byte-range** granularity
(what a perfect tracker could do, which is strictly finer and can only remove
edges).

**Instrument validation.** Replaying MLX's own `maybeInsertBarrier` heuristic
over the traced I/O sets reproduces the observed barrier column **exactly**:
247 replayed vs 247 observed, **0 mismatches** over the 408-dispatch step. The
replay only became exact after I modelled `end_encoding()`
(`device.cpp:452-466`), which clears `needs_barrier_`, `prev_inputs_`,
`prev_outputs_`, `next_inputs_`, `next_outputs_` — so the first dispatch of each
command buffer never charges a barrier, because cross-encoder ordering rides the
encoder fence instead. That accounting is exact: **288 separations − 247 charged
= 41 free**, and independently, 41 of the 47 encoder-first rows are hazard
separations while 0 of them charge a barrier.

A tracer that reproduces the production barrier column bit-for-bit is the
"materially better instrument" Rule 83 requires to reopen this family.

---

## 2. H1 (serial encoder) is dead — V-CONCURRENT

`CommandEncoder::get_command_encoder()`, `device.cpp:545-549`:

```cpp
encoder_ = NS::RetainPtr(
    buffer_->computeCommandEncoder(MTL::DispatchTypeConcurrent));
```

Unconditional. Every encoder in the decode path is already
`MTL::DispatchTypeConcurrent`. There is no serial-encoder path to flip. The
hypothesis "decode is serialised because MLX asks Metal for a serial encoder"
is refuted by the source, and by prior art: PR #101 measured that forcing
`DispatchTypeSerial` costs **+0.456 ms/step (+5.49 %)**, CI [−0.522, −0.390],
complete separation (`research/pr101-frieren-result.md:254,276-300`); nezuko A0
measured +0.580 ms / +0.421 ms (`research/nezuko-a0-dispatch-type.txt:1-45`).

What actually serialises decode is the *barrier* machinery layered on top of the
concurrent encoder:

| site | line | rule |
|---|---|---|
| `set_input_array` | `device.cpp:324-325` | RAW: `needs_barrier_ |= prev_outputs_.count(r_buf)` |
| `set_output_array` | `device.cpp:343-348` | WAR: `needs_barrier_ |= prev_inputs_.count(buf)`, **skipped inside a `ConcurrentContext`** |
| `maybeInsertBarrier` | `device.cpp:363-377` | emits `memoryBarrier(BarrierScopeBuffers)`, then rotates `next_* -> prev_*` |
| `dispatch_threadgroups` / `dispatch_threads` | `device.cpp:379-390` | calls `maybeInsertBarrier()` before every dispatch |
| `end_encoding` | `device.cpp:452-466` | clears all hazard state at the CB boundary |

So the correct framing of H1 is not "serial vs concurrent encoder" but "is the
greedy barrier heuristic leaving concurrency on the table?" That is H2/H3, §3.

---

## 3. The DAG: greedy 289 vs optimal 288

For a linear stream of dispatches partitioned into contiguous barrier-free
groups, the minimum number of groups achievable by *any* legal reordering is the
length of the longest chain in the conflict DAG (Mirsky's theorem — the level
partition is optimal, and no schedule can do better because every element of a
chain must land in a strictly later group than its predecessor).

| granularity | edges | greedy groups | minimum groups | headroom |
|---|---|---|---|---|
| buffer pointer | RAW + WAR | 289 | **288** | 1 |
| buffer pointer | RAW only | 289 | **288** | 1 |
| byte range | RAW + WAR | 289 | **288** | 1 |
| byte range | RAW only | 289 | **288** | 1 |

Three things fall out of this table, and each one kills a candidate lever:

1. **Anti-dependencies cost nothing.** Dropping every WAR/WAW edge — i.e.
   imagining a perfect renaming/allocator that never reuses a buffer while a
   reader is live — leaves the minimum at 288. Buffer-pool reuse is *not*
   creating false serialisation.
2. **Pointer-granularity aliasing costs nothing.** Upgrading MLX's
   whole-buffer hazard test to exact byte-range tracking — the "sub-buffer
   aliasing" lever — leaves both greedy and minimum unchanged. Nothing in decode
   is being falsely serialised by two disjoint slices of the same allocation.
3. **MLX's greedy is already within one group of optimal.** Reordering the
   emission stream, folding dependent stages, or any smarter grouping heuristic
   can recover at most **1 barrier**.

**Where the single lost group is.** Exactly one place, at layer boundary
(step-relative index 12):

```
idx  9  g= 9  lvl= 9  bar=0  rmsbfloat16
idx 10  g=10  lvl=10  bar=1  decode_nvfp4_qkv_h64
idx 11  g=11  lvl=11  bar=1  sliding_fused_attn_ring
idx 12  g=11  lvl=10  bar=0  gate_sp_h64          <-- could sit with idx 10
idx 13  g=12  lvl=12  bar=1  oproj_act_h64
```

`gate_sp_h64` and `decode_nvfp4_qkv_h64` both read the RMS-norm output and do
not conflict, so optimally they share level 10; the greedy pass has already
absorbed `sliding_fused_attn_ring` into group 11 by the time `gate_sp_h64`
arrives. This pattern recurs 30x per step (once per h64 layer), but the saving
does **not** compound: `oproj_act_h64` depends on both attention and gate, so it
lands at level 12 either way. Net saving over the whole step: one group.

**Where the concurrency already is.** The 288 levels decompose as:

| level width | count | dispatches |
|---|---|---|
| 1 | 207 | 207 |
| 2 | 42 | 84 |
| 3 | 39 | 117 |

Mean 1.417 dispatches per level. The multi-dispatch levels are exactly:

| composition | occurrences |
|---|---|
| `prefill_router_tournament` ∥ `routed_nvfp4_swiglu_qmv_packed_top8keys` ∥ `shared_nvfp4_swiglu_qmv_rows1_halved` | 39 |
| `gate_sp_h64` ∥ `nvfp4_qkv_h64` | 30 |
| `gate_sp_h48` ∥ `nvfp4_qkv_h48` | 10 |
| `gather_front` ∥ `gather_front` | 1 |
| `argmax` ∥ `vn_copy` | 1 |

The MoE triple and the gate/QKV pair are the *entire* concurrency budget of the
decode step, and MLX is already exploiting both. 207 of 408 dispatches (50.7 %)
are alone in their level with no possible partner.

---

## 4. Pricing, and why Stage 3 was not built

Using my own measured tax decomposition (PR #268, M4 Pro: barrier 1.3003 ±
0.0597 us, dispatch 0.1231 ± 0.0481 us, 91 %/9 % split):

* **Realistic headroom** = 1 group x 1.3003 us = **1.30 us/step**
  = 1.30 x 0.015228 %/us = **0.0198 % of `cs`**.
  Even at the +2σ end of the barrier coefficient (1.4197 us) this is 0.0216 %.
* **Preregistered Stage-3 gate** = 33 us/step ≈ +0.5 % of `cs`.
  **1.30 / 33 = 0.039 — short by a factor of 25.4.** Gate CLOSED.
* **Absolute ceiling**, if one could *additionally* align every command-buffer
  boundary onto a level boundary so that all 46 boundaries absorb a barrier for
  free: 288 − 1 − 46 = 241 charged barriers, saving 6 barriers = **7.80 us/step
  = 0.119 % of `cs`**. Still 4.2x short of the gate — and CB structure is
  already on the STOP list (archive `:3749-3752`, closed by PR #174; CB
  splitting measured wrong-sign: 1 disp/CB = +1087 us/step, k=2 = +103 us/step).

Because the preregistered condition was "Stage 3 build **only if** headroom
>= 33 us/step **and** overlapping dispatches can be named", and the first
conjunct fails by 25x, **no Stage 3 build was performed**. Building it would
have burned a measurement budget on a lever whose entire prize is 1.7 % of the
noise floor of a paired timing run.

### 4b. Duration-weighted view (DESCRIPTIVE ONLY — Rule 82)

Weighting each dispatch by its family's `label_us_m4 / n_dispatches` from the
R105-E ledger and taking the longest *weighted* chain:

* Sigma of all dispatch labels = **8528.3 us** (M4, all 408 attributed, 0 unattributed)
* weighted critical path = **7725.8 us** = **90.6 %** of Sigma
* identical with RAW-only edges (7725.8 us)

i.e. even if every dispatch cost exactly its label and barriers were free, a
perfect infinitely-wide machine would save only 9.4 % of kernel-label time. This
is consistent with the 70.6 % structural figure and makes the same point on the
time axis rather than the count axis.

**Rule 82 applies in full**: MLX pipeline labels are *not* wall time, and this
number must not be used to price any lever. It is reported because it is the
shape of the graph, not a cost.

---

## 5. Rule-83 disposition of every candidate in this family

| candidate lever | verdict | evidence |
|---|---|---|
| serial -> concurrent encoder | **already concurrent** | `device.cpp:545-549`; PR #101 −5.49 % if flipped |
| better barrier grouping / emission reordering | **1 barrier = 1.30 us/step** | greedy 289 vs optimal 288, this report |
| kill false deps from buffer-pool reuse (WAR/WAW) | **0 barriers** | RAW-only min = 288 = RAW+WAR min |
| byte-range hazard tracking instead of whole-buffer | **0 barriers** | range min = ptr min = 288; range greedy = ptr greedy = 289 |
| dependent-stage folding (archive arm C) | **cannot satisfy gate** | ceiling 7.80 us/step < 33 us/step |
| `start_concurrent()` / `ConcurrentContext` around independent dispatches | **<= 1.30 us/step, and unsubmittable** | same DAG bound; §6 |
| CB restructuring to absorb barriers at boundaries | **<= 7.80 us/step, STOP-listed** | archive `:3749-3752`, PR #174; wrong-sign measurements |

Prior art already pointing the same way, now reproduced with an independent
instrument: archive `:4245-4252` — 80 parallel RAW edges add only 4 barriers
(cost −0.0070 ± 0.0212 us/dispatch) whereas the same edges in series cost 78
barriers / 110 us, concluding "graph reordering is therefore already done inside
MLX". This report supplies the missing quantifier: *how much* is already done —
**287 of 288 possible groups**.

### 5a. The advisor's Rule-41 framing, answered directly

The brief asks: "*whether the compute encoder is `MTLDispatchTypeSerial` in
places the dependency DAG does not require*". Answered in two parts:

1. **It never is.** `device.cpp:545-549` passes `MTL::DispatchTypeConcurrent`
   on the single unconditional construction path (§2). There is no serial
   encoder anywhere in decode.
2. **The serialisation that remains is required.** Rule 41's 76.3 %
   serialisation share at a 4,096 B dispatch boundary is real, but this report
   shows it is *data-dependence* serialisation, not encoder-policy
   serialisation: the conflict DAG's longest chain is 288 levels out of 408
   dispatches, and MLX's greedy grouping already achieves 289. **The DAG
   requires it essentially everywhere.**

That is the clean negative the brief asked for, on the 20.8 % of `cs` that is
`L`: `L` is not recoverable by scheduling. It has to be attacked as *work*.

### 5b. Fence-respecting finding (`residual_rms_router`, reported not acted on)

Per the advisor's 2026-08-10 comment, #617 is fenced out of
`residual_rms_router` while #597 draws ranked receipts on it. The DAG does
surface one item adjacent to that kernel, so I record it and take no action:

The **sole** greedy-vs-optimal divergence in the whole step (step-relative
dispatch 12, recurring 30x per step) sits immediately downstream of the fused
residual+RMSNorm output. `gate_sp_h64` and `decode_nvfp4_qkv_h64` both read that
one buffer and are mutually independent, so they *could* share a level; MLX's
greedy pass instead closes the group early because it has already absorbed
`sliding_fused_attn_ring`. **It does not compound** — `oproj_act_h64` lands at
level 12 under either schedule — so the entire item is worth **1 group =
1.3003 us/step = 0.0198 % of `cs`**, i.e. 25x below the build gate on its own.
No edit is proposed, and none would be worth proposing even without the fence.

---

## 6. Scope correction the advisor must record

**The assignment body is wrong on one point, and the claim was repeated.** PR
#617 states that "`backend/metal/**` IS in `editablePaths`", and the advisor's
2026-08-10 comment restates it ("`backend/metal/**` is in `editablePaths`;
`backend/common/**` is **not**"). The `backend/common/**` half is right; the
`backend/metal/**` half is not a glob at all. `benchmark.json`'s
`editablePaths` is a **97-entry per-file whitelist**, and it contains **neither**
`Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/device.cpp` **nor**
`device.h`. The only `backend/metal/` entries are `matmul.cpp`,
`jit_kernels.cpp`, `kernels.h`, `quantized.cpp`, the `kernels/**` sources, and
the `mlx-generated/*.cpp` twins.

Consequence: **encoder dispatch type, barrier insertion, `start_concurrent()`,
hazard-set granularity and command-buffer structure are all structurally
unsubmittable.** Any positive result in this family would have needed a
different mechanism (e.g. changing what the *runtime* binds, from
`LagunaRuntimeModel.swift`) to reach the score. This is a second, independent
reason not to have built Stage 3 — but it is not the primary one: even with
`device.cpp` submittable, the prize is 1.30 us/step.

I recommend the advisor fix this claim before any future assignment in the
dispatch/barrier family, and treat "is the file in the 97-entry whitelist?" as a
required pre-assignment check (the runbook's
`senpai/validate-assignment-scope.sh` does exactly this).

---

## 7. Two corrections to the recorded research state

While attributing dispatches to families I re-derived two numbers in
`CURRENT_RESEARCH_STATE.md` §5j and could not reproduce them.

1. **"13 LATENCY families"** — the R105-E ledger holds **12** families in the
   `LATENCY` regime, not 13. 13 is the **BANDWIDTH** count (25 families = 13
   BANDWIDTH + 12 LATENCY), so the two labels were almost certainly swapped.
2. **"21.6 % of the SPLIT=1 label"** — the 12 LATENCY families sum to
   **760.2 us** of a total **8528.3 us**, i.e. **8.91 %**, not 21.6 %. The
   21.77 % figure in that section is instead the **sub-C40 occupancy class**
   share (203 dispatches, 8.2465 % of step bytes, 21.77 % of the SPLIT=1
   label). The occupancy roll-up is: `SINGLE_TG` 84 dispatches = 0.0359 % bytes
   / 3.89 % label; `SUB_C40` 203 = 8.2465 % / 21.77 %; `AT_OR_ABOVE_C40` 205 =
   91.7535 % / 78.23 %.

Neither correction changes any verdict; both matter if someone sizes a future
lever from §5j.

---

## 8. Dispatch geometry (Rule 77)

Per steady decode step, 24 distinct pipelines / 408 dispatches / 47 command
buffers:

* dispatches per command buffer: `{1: 4, 2: 1, 3: 1, 4: 1, 5: 5, 8: 1, 10: 21, 11: 4, 12: 9}`
* charged barriers per command buffer: `{0: 4, 1: 2, 2: 4, 3: 1, 4: 2, 6: 21, 7: 4, 8: 9}`
* family dispatch counts reproduce the R105-E ledger exactly: 41 `rmsbfloat16`;
  39 each of `shared_nvfp4_swiglu_qmv_rows1_halved`,
  `routed_shared_nvfp4_down_residual`,
  `routed_nvfp4_swiglu_qmv_packed_top8keys`, `residual_rms_router`,
  `prefill_router_tournament`; 30 each of `sliding_fused_attn_ring`,
  `oproj_act_h64`, `gate_sp_h64`, `decode_nvfp4_qkv_h64`; 10 each of
  `oproj_act_h48`, `gate_sp_h48`, `full_fused_attn_grow`,
  `decode_nvfp4_qkv_h48`; 2 `gather_front`; 1 each of `vn_copy`,
  `residual_rms_bf16_2048_v1`, `lmhead_int5_base_coarse_delta`,
  `lmhead_exact_winner`, `lmhead_exact_fused_int5_sparse_refine`,
  `lmhead_coarse_argmax_stage1`, `dense_gate_up_swiglu`,
  `dense_down_residual`, `decode_embedding_rope_atlas`, `argmax`.

The ~8.7 dispatches per command buffer is well below this host's
`max_ops_per_buffer_` (40 for the `g` architecture string), so CB boundaries are
driven by the runtime's own commit points, not by MLX's op budget.

---

## 9. Where the 1368 us L-residual actually lives

The research state's model is `T = B/BW + L`, `B = 1,671,402,432 B/step`. On M5,
`T = 4141.5 us`, `B/BW = 2773.1 us`, so **`L5 = 1368.4 us = 20.8 % of cs`**
(bound `L5 <= 1401.5 us`). This experiment asked whether `L` is a scheduling
artefact. It is not:

* barrier + dispatch tax accounts for ~371 us of the M4 `L4 = 1828 us`
  (406 x 0.1231 + 247 x 1.3003 = 49.98 + 321.2), i.e. **~20 % of `L`** — and of
  that, **only 1.30 us is recoverable by reordering**;
* the remaining ~80 % of `L` is not dispatch bookkeeping at all. The
  occupancy roll-up points at it directly: 203 sub-C40 dispatches move 8.2 % of
  the step's bytes but carry 21.8 % of the label, and 84 single-threadgroup
  dispatches move 0.036 % of bytes for 3.9 % of the label. `L` is dominated by
  **under-occupied, latency-bound small kernels**, not by serialisation.

That is the actionable redirection this experiment produces: the next lever in
this area should raise **occupancy of the small LATENCY-regime kernels** (in the
scored runtime, which *is* submittable), not rearrange the dependency graph.
Concretely, and explicitly outside my fences: `prefill_router_tournament` (39
dispatches, 256 grid threads, 0.126 % of M4 peak BW) and `gate_sp_h64` (30
dispatches) are the two largest sub-C40 costs I am allowed to name;
`residual_rms_router` is fenced to frieren, and the routed/shared NVFP4 qmv
inner loop is fenced to tanjiro (R106-A).

---

## 10. Reproduction

```bash
# 1. build the tracing worker (research-only patch, never submitted)
git apply research/r106c/scripts/trace_dag.patch
mkdir -p .build-worker/clang-module-cache
CLANG_MODULE_CACHE_PATH="${PWD}/.build-worker/clang-module-cache" \
  swift build -c release --force-resolved-versions \
    --scratch-path .build-worker --product mlxfast-runtime-worker   # 46.4 s incremental
git checkout -- Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/device.cpp \
                Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/device.h

# 2. capture one traced decode run (42.8 s, arm label "dag" -> /tmp/r106c/dump/dag)
research/r106c/scripts/run_dag_trace.sh dag

# 3. build the ledger
python3 research/r106c/scripts/dag_ledger.py /tmp/r106c/dump/dag \
        research/artifacts/fern-r106c
```

Step 1 leaves the *submitted* surface untouched: the patch only edits
`device.cpp` / `device.h`, which are not in `editablePaths` (§6) and are
reverted before any commit. `git status --porcelain` is clean on the result
commit; the instrumentation exists in the repository only as the patch file.

W&B record (ledger summary + artefact bundle):
<https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/deuilxqt> —
reproduce with `python3 research/r106c/scripts/log_wandb.py`.

Host: Apple M4 Pro, 48 GiB (low-memory startup profile: allocator cache capped
at 6 GiB; ranked code paths unaffected), macOS 26.5.2, `applegpu_g16s gen=16`.

**Host-portability of this result.** The measured quantity is the *dispatch
dependency graph of one steady decode step*, which is determined by the emitted
MLX op sequence, not by GPU generation. M4 Pro does not select the `_nax`
prefill kernels, but this experiment measures decode only and does not depend on
kernel selection. The only host-dependent number used is the barrier coefficient
1.3003 us (M4 Pro, PR #268); the M5 coefficient has never been measured. Even a
5x larger M5 barrier coefficient leaves the headroom at 6.5 us/step, still 5x
below the gate.

## 11. Follow-ups I did not implement

1. **Occupancy of sub-C40 decode kernels** (§9) — the real home of `L`. Needs a
   scored-runtime mechanism, not a vendor-dispatch one.
2. **Measure the barrier coefficient on M5.** Every barrier-family pricing in
   the archive, including mine, rests on one M4 Pro measurement. It is cheap and
   would retire a standing caveat.
3. **Add the 97-entry whitelist check to assignment drafting.** §6 shows a
   scope claim survived into an assignment body; `senpai/validate-assignment-scope.sh`
   would have caught it.
