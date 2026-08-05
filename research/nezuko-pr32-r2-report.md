SENPAI-RESULT: {"terminal":true,"status":"complete","pending_arms":true,"wandb_run_ids":[],"primary_metric":{"name":"same_host_paired_estimate","available":false,"value":null},"test_metric":{"name":"passed_correctness","available":true,"value":1}}

- Student / PR: maple-nezuko / #32 (`maple-nezuko/shared-qmv-staging`), revision `r2`
- Hypothesis and target cost: r1 assigned hypothesis was that hoisting the
  shared-expert QMV loads above their cross-lane reductions would convert a
  measured `-4.5%` kernel-body win into decode time. r2 was assigned two
  *measurement* deliverables instead: (A) a ranked `MLX_MAX_MB_PER_BUFFER`
  receipt triple, and (B) a per-family dispatch-elasticity census.
- Decision: **dead hypothesis** for the r1 shared-QMV mechanism (now closed with
  a positive explanation, not just a null). Deliverable B is **complete and
  green as evidence**. Deliverable A is **blocked on a shared external
  resource**, see the blocker section.
- `BASE_SHA` / candidate commit: base `0b45de2261ee31b2f7fb46b6ddc3245775a02941`,
  candidate = branch HEAD (the commit that adds this report; exact SHA in the
  machine-readable result).
- Submitted candidate files: **none**. `git diff --stat <base>..HEAD -- Sources
  Vendor` is empty. This revision is receipts-and-research only; the editable
  surface is byte-identical to base, so editable bytes and headroom are
  unchanged and the growth budget check is trivially net-zero.
- Supporting test or documentation files: `research/nezuko-dispatch-elasticity.md`
  (census, 541 lines), `research/nezuko-mbpb-submission-note.md` (shared receipt
  note body), `research/make_mbpb_arm.py`, `research/make_mbpb_note.py`,
  `research/sweep_mb_per_buffer.sh`, `research/sweep_dispatch_elasticity.sh`,
  `research/nezuko_elasticity_table.py`, `research/nezuko_serial_budget.py`
  (recomputes the round-3 serialised budget and every number in the ranking
  table below from the run's own constants, no arguments).
- Assignment-scope preflight: all changed paths are under `research/`.
- Scored-path reachability evidence: not applicable — no scored-path change is
  proposed in this revision. Reachability *findings* about the scored path are
  reported below and are the deliverable.

---

# Narrative A — the `MLX_MAX_MB_PER_BUFFER` receipt triple

## Blocker: the official submission channel is serialised per account

`mlxfast submit` refused every attempt with:

```text
{"error":{"code":"conflict","message":"account already has 1 submission(s) in flight for this benchmark (limit 1)"}}
```

All students share account `morganmcg1`, so the limit is **one in-flight
submission across the whole cohort**, not one per student. The slot was occupied
by a sibling on every check I made: `0411779` (10:01 AM) held it while
`validating` for most of the turn, and the moment it resolved (rejected, 2.29070,
-26.07%) another sibling's `cdf71fa` (10:25 AM) took it. So **none of my three
arms was sent** and zero receipts were consumed.

There is no queue: the slot is claimed by whoever calls `mlxfast submit` in the
instant it frees, so a student who politely defers can be starved indefinitely
by siblings who retry more often. That is a property of the cohort's shared
account, not of my arms.

This is a scheduling fact the advisor needs, and it is the single most
actionable thing in this report: any plan that hands N students "go get a ranked
receipt" serialises them behind each other with no queue and no notification.
Receipt-bearing work has to be dispatched by one scheduler, or students have to
be told to expect a `conflict` and defer.

The three arms are fully prepared and reproducible on demand; nothing needs to
be re-derived to fire them. The pipeline is verified end to end short of the
server: `python3 research/make_mbpb_arm.py low` applies exactly 7 insertions and
1 deletion in one file, `make_mbpb_note.py low` writes a 14788-byte note, and
`mlxfast submit` gets as far as `Pushing traces before submission` before the
server returns `conflict`. The refusal is purely the shared-account limit.

Note for whoever fires them: `mlxfast submit` packages **editable paths from the
working tree**, not a git commit, so an arm does not need to be committed. The
`commit` column on the leaderboard will therefore label the receipt with base's
SHA; the arm itself is identified by the one literal documented in the note.

## What the triple would settle

Three byte-distinct, behaviour-identical trees differing only in the integer
literal at `Sources/MLXFastModel/LagunaRuntimeWeights.swift:386`, with
`MLX_MAX_OPS_PER_BUFFER` held at 200:

| arm | `MLX_MAX_MB_PER_BUFFER` | command buffers / decode step |
| --- | ---: | ---: |
| `low` | 50 | 85 |
| `control` | 200 (+ cosmetic comment only) | 34 |
| `high` | 400 | 19 |

All three emit 406 dispatches per step, so the token stream is bit-identical by
construction. Pre-registered submission order, `random.seed(32)`:
**`low, high, control`**. Generators: `research/make_mbpb_arm.py <arm>` then
`research/make_mbpb_note.py <arm>`; reset with `git checkout HEAD --
Sources/MLXFastModel/LagunaRuntimeWeights.swift`.

## A correction to the command-buffer table in circulation

The figures `50 -> 127, 200 -> 45, 400 -> 19` are wrong. Measured on this host
with the profiler build:

- full profile, 50 MB -> **85** command buffers/step (4.8 dispatches each)
- full profile, 200 MB -> **34** (11.9 each)
- full profile, 400 MB -> **19** (21.4 each)
- the **45** in circulation is the *low-memory* 128 MB / 64 ops profile (9.0 each)

The 45 is a real number attached to the wrong arm. Anyone reasoning about
"dispatches per command buffer" from the circulating table is off by ~2.5x on
the 50 MB arm.

## Local sweep of exactly this knob — and a refutation of my own model

Run `4db9908a-75de-4630-8a35-d13436c63cb1`, exit 0, 270 s. `DARKBLOOM_STARTUP_
MEMORY_PROFILE=full` forced so the ranked literal actually executes on this
48 GiB host. All arms: 0 divergences, 406 dispatches.

| arm | wall ms | GPU union ms | gap ms | cbs | disp/cb |
| --- | ---: | ---: | ---: | ---: | ---: |
| full 50 | **8.400** | 8.151 | 0.249 | 85 | 4.8 |
| full 200 (r1) | 8.603 | 8.349 | 0.254 | 34 | 11.9 |
| full 200 (r2) | 8.518 | 8.267 | 0.251 | 34 | 11.9 |
| full 200 (r3) | 8.591 | 8.346 | 0.245 | 34 | 11.9 |
| full 400 | **8.785** | 8.218 | 0.566 | 19 | 21.4 |
| low profile (128/64) | 8.528 | 8.268 | 0.260 | 45 | 9.0 |

`full 200` n=3: wall 8.5707 +/- 0.0460 ms (sem 0.0266), union 8.3207 +/- 0.0465.

- **50 MB: -0.171 ms wall (-1.99%), t = -3.2**; union -2.04%.
- **400 MB: +0.214 ms wall (+2.50%), t = +4.0**; union -1.23%.

This **agrees in sign and magnitude with frieren's suspended M5 datum**
(+1.696% +/- 0.175% decode gain for `50`, t = -9.71). Two hosts, two
instruments, same direction.

It also **refutes the per-command-buffer host-dispatch cost model I proposed in
my own #9 note.** If shrinking command buffers helped by paying less host
submit cost, the CPU/GPU gap would grow with fewer, larger buffers and shrink
with more, smaller ones. Instead the gap is *flat* at 0.249 vs 0.250 ms between
50 and 200 while the GPU union itself shrinks 2.0%, and at 400 the gap balloons
0.25 -> 0.57 ms. The win is inside GPU execution, not in host submission. My #9
"recoverable ~1.38 ms" column should not be used; the census below replaces it
with a measured number.

## `device.cpp` is off-surface — the env literal is the only legal lever

Answering the advisor's question directly:
`Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/device.cpp` is **not** in
`benchmark.json`'s `editablePaths` (97 entries, zero contain `device`). So MLX's
`needs_commit()` policy cannot be edited in a submission, and setting the
environment literal from `LagunaRuntimeWeights.swift` is the only legal way to
move this knob. That file *is* on the surface, via the directory entry
`Sources/MLXFastModel`.

## Two further corrections while establishing the harness

- The full-profile gate is **>= 64 GiB**, not 96 GiB:
  `RuntimeStartupMemoryPolicy.fullProfileMinimumPhysicalMemoryBytes = 64 << 30`.
- The full-profile branch calls `setenv(..., 0)` so an external environment
  value wins, but the low-memory `apply()` calls `setenv(..., 1)`, force-pinning
  128 MB / 64 ops. **On any host below 64 GiB the ranked literal never executes**
  unless `DARKBLOOM_STARTUP_MEMORY_PROFILE=full` is set. Anyone who "tested the
  MB knob" on a small host without that override measured nothing. Forcing the
  full profile on 48 GiB does not OOM.

---

# Narrative B — per-family dispatch-elasticity census

Separate work, separate conclusion. Instrument: an off-surface profiler build of
`device.cpp` that can duplicate (`dup`) or skip (`skip`) all dispatches of a
named pipeline family.

Round 1: run `3fb91a20-3111-4185-8964-5271b16108a1`, exit 0, 901 s, 20 arms x
150 steps. Round 2: run `c9893c28-fe05-457b-a56b-56c84c51f8e1`, exit 0, 531 s,
14 arms x 150 steps, **all 14 arms 0 divergences**. Round 2 base n=5: wall
8522.2 +/- 9.7 us, union 8272.4 +/- 7.8 us, gap 249.6 +/- 13.1 us, 45 command
buffers, 406 dispatches; base spread of 19 us resolves a single-arm delta to
+/- 16 us at 2 sigma.

Instrument validity: every `skip` arm produced 147-150 divergent tokens (it
removes real work, so its timing is data-confounded); every `dup` arm produced
**0** divergences. At the time I read this as "`dup` is the clean instrument and
`skip` deltas are upper bounds on removable time". Round 3 below shows both
halves of that reading were wrong: `skip` deltas are **lower** bounds, and `dup`
measures the cost of an *additional cache-warm* call rather than the cost of the
family. Both columns survive, but only with those corrected meanings — read the
round-3 section before using either.

## I built a recovery-ratio table, then a third instrument refuted it

I first combined `skip` and `dup` into a "recovery ratio" and concluded that
only 46.7% of the step was family-attributable, with a 53.3% unattributable
shared floor, and that isolated per-call timing overstates prizes ~2x. **That
conclusion was wrong and I am retracting it.** The superseded table is kept in
`research/nezuko-dispatch-elasticity.md` behind a DO-NOT-RANK banner, because the
`dup` column in it turned out to be valid and reusable. What follows replaces it.

## The correct result: the decode step is ~93% serial

Round 3, run `1c8aded9-029b-461e-95bb-9570606f7c47`, exit 0, 45 s, 250 steps,
**0 divergences**. With `SPLIT=1` every dispatch gets its own command buffer, so
each kernel runs alone on the whole GPU and the profiler reports a serialised
per-kernel time. Per steady step: wall 10.154 ms, `gpu_busy_sum` 8.850 ms,
`gpu_busy_union` 8.849 ms (sum == union confirms full serialisation), 406
command buffers, 406 dispatches.

| quantity | us/step |
| --- | ---: |
| `SPLIT=1` serialised sum (each kernel alone, whole machine) | 8850.3 |
| `SPLIT=0` real overlapped union | 8272.4 |
| excess | 577.9 = **6.99%**, i.e. 1.423 us/dispatch |

Running every kernel alone, one at a time, costs only **7.0%** more than the
real overlapped step — and command-buffer overhead is inside that 7.0% too. So
**inter-kernel overlap and command-buffer overhead together account for at most
7% of decode.** The step is ~93% one-kernel-at-a-time execution, which means
per-kernel serialised time is very nearly an honest ranking metric after all.

### Why the `skip` instrument was lying

The censused families have a serialised total of 7358 us, but their `skip` deltas
sum to only 3860 us — **52%**. In a 93%-serial step, removing a family's
dispatches should return nearly its full serialised cost. It does not.

Likely mechanism: every `skip` arm corrupts the residual stream (147-150
divergent tokens), so the router's top-8 choice downstream becomes effectively
random across 256 experts instead of correlated between layers. That destroys
expert-gather locality and makes the *surviving* MoE kernels slower, partly
cancelling the work removed. The confound hits every family in the same
direction.

Two corrections to my own earlier text: `skip` deltas are **lower** bounds, not
upper bounds as I wrote; and there is **no large unattributable floor** — the
serialised budget accounts for 106.8% of the step across 16 families with only
18.8 us unlisted.

### The ranking table, and a new signal: first-touch cost

`true us/call` is serialised per-call minus the 1.33 us command-buffer floor.
`dup/ser` divides the (still valid) round-2 duplicate cost by it.

| family | calls | serialised us/step | % of step | true us/call | dup/ser |
| --- | ---: | ---: | ---: | ---: | ---: |
| `routed_nvfp4_swiglu_qmv` | 39 | 1561.5 | 18.88% | 38.71 | 0.958 |
| `decode_nvfp4_qkv_h64` | 30 | 1402.3 | 16.95% | 45.41 | 0.770 |
| `oproj_act_h64` | 30 | 1183.1 | 14.30% | 38.11 | **0.601** |
| `down_residual` | 39 | 894.8 | 10.82% | 21.61 | 0.872 |
| `sliding_fused_attn` | 30 | 637.7 | 7.71% | 19.93 | 0.971 |
| `lmhead_int5` (4 kernels) | 4 | 505.0 | 6.10% | — | — |
| `decode_nvfp4_qkv_h48` | 10 | 378.7 | 4.58% | 36.54 | — |
| `gate_sp` h64+h48 | 40 | 325.6 | 3.94% | 6.76 | **0.659** |
| `residual_rms_router` | 39 | 319.2 | 3.86% | 6.85 | **0.605** |
| `oproj_act_h48` | 10 | 317.6 | 3.84% | 30.43 | — |
| `shared_nvfp4_swiglu_qmv` | 39 | 295.0 | 3.57% | 6.23 | 0.721 |
| `dense_gate_up_swiglu` | 1 | 267.4 | 3.23% | 266.02 | — |
| `full_fused_attn` | 10 | 259.9 | 3.14% | 24.66 | 0.785 |
| `decode_router_top8_ordinal` | 39 | 205.4 | 2.48% | 3.94 | — |
| `rmsbfloat16` | 41 | 143.3 | 1.73% | 2.17 | — |
| `dense_down_residual` | 1 | 135.0 | 1.63% | 133.65 | — |
| sum of listed | | 8831.5 | 106.76% | | |

A duplicate call costs 60-97% of the first, and **the spread is the actionable
signal**:

- `dup/ser` near 1 (`routed_nvfp4_swiglu_qmv` 0.958, `sliding_fused_attn` 0.971,
  `lmhead_int5` 0.970): a second call costs as much as the first, so the kernel
  is bandwidth- or occupancy-bound with nothing left to reuse. These need a
  better kernel.
- `dup/ser` well below 1 (`oproj_act_h64` **0.601**, `residual_rms_router` 0.605,
  `gate_sp` 0.659, `shared_nvfp4_swiglu_qmv` 0.721): the *first* call pays a
  large first-touch weight-streaming cost the duplicate does not repeat. For
  these, **fusing with a neighbour so the weights are touched once** is the
  lever, not faster arithmetic.

**`oproj_act_h64` is the standout target: 14.3% of the step, and ~40% of its
per-call cost is first-touch.** That is the strongest fusion candidate in the
model and it is not what anyone is currently working on.

Also worth noting: two independent refutations of a per-dispatch *host* cost
model. `delta gap` vs `delta n` has R^2 = 0.5083 in round 1 and **R^2 = 0.0405
with a negative slope** in round 2, while `delta wall = 1.0002 * delta union +
43.2` with **R^2 = 0.9990** (rms 12.6, n=7).

## This closes the r1 hypothesis of this PR, on arithmetic alone

`shared_nvfp4_swiglu_qmv` is 295.0 us/step = **3.57% of decode**. The `-4.5%`
kernel-body win measured in r1 is therefore worth `0.045 x 295.0 = 13.3 us`, or
**0.160% of decode** — below the `+/- 16 us` resolution of the instrument that
measured it. r1's `+8.3 +/- 7.6 us` is exactly what a 13 us win looks like
through a 16 us aperture.

This closure does not depend on the discredited `skip` deltas at all, and it
supersedes my "negative recovery ratio" reading. The shared QMV is not *free* —
it is simply too small a share of the step for a 4.5% body win to be measurable,
let alone rankable. The mechanism was sound; the target was too small.
**Recommend closing this PR's hypothesis.**

## Sliding attention: geometry, and two claims I am retracting

Measured geometry (`Sources/MLXFastModel/LagunaRuntimeModel.swift`), both
kernels: grid `((heads/2)*1024, 1, 1)`, threadgroup `(1024, 1, 1)` -> 32
simdgroups per threadgroup.

- sliding `ring_v1` (`:1382`, dispatch `:1793`, grid `:1799`): 64 heads -> **32
  threadgroups**, `constexpr N = 512` (`:1406`), `gqa = 8`.
- full `grow_v1` (`:1857`, dispatch `:2310`): 48 heads -> **24 threadgroups**,
  runtime `N = writeIdx + 1` (`:1886`), `gqa = 6`.
- Threadgroup memory is **18432 B, identical** in both: `outputs[4*BN*BDP]`
  float 16896 B + four bfloat[128] staging buffers at 256 B + `max_scores` 256 +
  `sum_exp_scores` 256.
- Work is already decomposed three ways: head-pair per threadgroup, 32
  simdgroups partitioning kv by residue mod `BN`, 32 lanes splitting `head_dim`
  four wide. Each simdgroup visits 16 of 512 slots in 8 trips of 2, no tail.
- Phase 1 uses only simdgroups 0-3, so **28 of 32 are idle in that phase**.
- Both kernels hardcode their head count as `constexpr`, so the "other" head
  count implied by `heads/2` is unreachable.

**Retraction 1:** the circulating "~8 threadgroups" figure is wrong; it is 32
(sliding) and 24 (full). **Retraction 2:** "kv-position parallelism is missing"
is wrong; it is already 32-way.

## And a correction to my own mechanism, from an independent review

I commissioned an independent frontier review of my sliding-attention analysis
and it corrected me on the causal story. I accept the correction:

- The "36% of bandwidth" figure is **real but not causal**. The DRAM floor is
  ~8.1 us/call against ~19-22 us measured; the system-level cache absorbs the 4x
  K/V re-read. The actual binder is the ~18 KiB threadgroup memory -> about one
  resident threadgroup per core -> a two-wave latency/occupancy limit.
- My claim that "a small machine understates the win" is **mostly wrong for
  sliding attention** (32 threadgroups on both 20-core and 40-core parts, both
  ~2x above the packed floor). It is directionally right only for the
  **full-attention twin**, where 24 threadgroups leave 16 of 40 M5 cores
  provably idle on the 10 full-attention layers per step.
- Realistic recoverable time for sliding attention on this host is **~250-330
  us/step**, not the ~428 us my bandwidth arithmetic implied.

Priced bit-exact restructurings, in order:
**(a) shrink threadgroup memory via per-plane combine staging (~4.2 KB, zero FP
risk) — price this first**; (b) chain-split 64x512 with a character-identical
*relocated* combine through f32 scratch plus one tiny extra dispatch per layer;
(c) 4-deep load pipeline (zero risk, small); (d) un-pairing (diagnostic only).
Rejected: any simd-width or lane-mapping change, the stock two-pass kernel, slot
re-chunking, wider loads, expression respellings.

(b) **overturns the blanket "split-K is not bit-exact" claim** recorded at
`research/maple-occupancy-quantization.md:183-186`: the split is exact when
chains and the combine tree are *relocated* rather than re-partitioned.
Floating-point order is pinned by the intra-chain slot walk, expression
spellings (FMA-contraction hazard, `sdpa_vector.h` ~140-160), butterfly widths
and the lane-to-chain mapping; threadgroup placement and combine *timing* are
not semantically pinned.

These are notes for fern (#30/#36), who owns attention kernel edits. I have not
touched those files. Gate any of them with
`research/run_upstream_equivalence.sh` plus the 64-step tripwire, and port
winners to `grow_v1`.

---

### Evidence

- Host, memory profile, toolchain, thermal policy: `Mac16,11` M4 Pro, 20 GPU
  cores, 48 GiB unified memory -> **low-memory startup profile**; Swift 6.3.3;
  standard 40C gate for `benchmark.sh` paths. Census and sweep runs use the
  profiler worker build and the shared 40C-quiet-host discipline.
- Exact reproduction:

```bash
# Narrative A: the knob sweep
research/sweep_mb_per_buffer.sh 150 full50 full200 full200 full200 full400 low
# Narrative A: build one receipt arm (then reset)
python3 research/make_mbpb_arm.py low && python3 research/make_mbpb_note.py low
mlxfast submit --note-file /tmp/note.low.md --model "Claude Opus 5"
git checkout HEAD -- Sources/MLXFastModel/LagunaRuntimeWeights.swift

# Narrative B: the census (requires the off-surface profiler build)
research/sweep_dispatch_elasticity.sh 150 0 base: dup:routed_nvfp4_swiglu_qmv \
    dup:down_residual dup:oproj_act_h64 dup:sliding_fused_attn \
    dup:lmhead_int5 dup:full_fused_attn dup:gate_sp
python3 research/nezuko_elasticity_table.py /tmp/elastic.*.split0.err

# Narrative B round 3: the serialised per-kernel budget (SPLIT=1, ~45 s)
research/sweep_shared_qmv_staging.sh 1 250 base
python3 research/nezuko_serial_budget.py
```

- Tests and risk-based checks: the editable surface is byte-identical to base,
  so there is no numerical change to gate. Correctness evidence is instead the
  divergence counter inside every measurement arm: **all 14 round-2 arms and
  every round-1 `dup` arm emitted 0 divergent tokens** against
  `correctness_prompts/public_longcopy_gate_english_512_256.json`, as did the
  round-3 SPLIT=1 base arm. All `skip` arms diverged by construction and are used
  only as lower bounds, with the caveat established in round 3.
- Correctness and serial-protocol verdict: **pass, trivially** — no scored-path
  change. No caching, no cross-request state, no lookahead was introduced.
- Divergent tokens or failure category: none in any arm used for a conclusion.
- Official ranking status: **not submitted** — channel conflict, see the blocker
  section. No receipt was consumed.

| Metric | Baseline | Candidate | Ratio / delta |
| --- | ---: | ---: | ---: |
| decode seconds/token | — | — | no candidate (surface byte-identical) |
| prefill seconds/token | — | — | unusable on this host, see caveat |
| same-host paired estimate | — | — | not applicable |

Caveat on local scoring: `./benchmark.sh --local-iterate` reports a bogus
`prefill_speedup` of ~0.327x on this host **even for byte-identical builds**, so
its prefill and score fields are unusable here. All timing in this report is
decode wall/GPU-union microseconds from the direct probe, which is internally
consistent and paired.

### Conclusion

- What happened and why: the assigned receipt triple could not be fired because
  the official channel allows one in-flight submission per *account* and the
  cohort shares one account; the arms and notes are generated and waiting. The
  census deliverable completed over three rounds, and round 3 replaced my own
  round-1/2 headline. The result the roadmap actually needed is the bracket:
  **serialised per-kernel time sums to 8850 us against a concurrent union of
  8272 us, so overlap plus command-buffer overhead together are only 7.0% of the
  decode step (1.42 us per dispatch).** Decode is ~93% one-kernel-at-a-time, and
  therefore per-kernel serialised time is very nearly an honest ranking metric —
  which is the opposite of the "isolated timing overstates prizes ~2x" claim I
  filed in round 2 and am now retracting. The serialised budget accounts for
  106.8% of the step across 16 families with 18.8 us unlisted, so there is no
  large unattributable shared floor either.
- Evidence for or against the mechanism: against my own #9 per-command-buffer
  host-cost model (flat gap 0.249 vs 0.250 ms across a 2.5x command-buffer-count
  change while GPU union moved 2.0%; R^2 = 0.04 on dispatch count, R^2 = 0.999
  on GPU union); for frieren's `MLX_MAX_MB_PER_BUFFER = 50` direction
  (independent host, same sign, -1.99% wall, t = -3.2, union -2.04%); against my
  own `skip` instrument, which under-reports removable time about 2x because
  skipping corrupts the residual stream, randomises router top-8 across 256
  experts, destroys expert-gather locality and slows the *surviving* MoE
  kernels; and decisively against this PR's own r1 hypothesis, now on arithmetic
  rather than on a null: `shared_nvfp4_swiglu_qmv` is 295.0 us = **3.57% of
  decode**, so the measured -4.5% kernel-body win is worth 13.3 us = 0.160% of
  decode, four times below the +/- 16 us aperture of the best instrument I have.
  r1's `+8.3 +/- 7.6 us` is exactly what a 13 us win looks like through that
  aperture. The mechanism was sound; the target was too small to ever pay.
- New lead this produced: the `dup/serialised` ratio separates
  bandwidth/occupancy-bound families (ratio ~= 1: routed swiglu 0.958, sliding
  attention 0.971, lmhead 0.970 — these need a genuinely better kernel) from
  families whose first call pays large first-touch weight streaming (ratio << 1:
  **`oproj_act_h64` 0.601**, `residual_rms_router` 0.605, `gate_sp` 0.659,
  shared QMV 0.721 — these want *fusion with a neighbour*). **`oproj_act_h64` is
  the strongest unclaimed target on the board: 14.3% of the decode step, ~40% of
  its cost is first-touch, and nobody in the cohort is working on it.**
- Uncertainty and M5 transfer risk: 20 vs 40 GPU cores changes occupancy
  conclusions, and the full-attention twin is the case where this host most
  understates a win. The `400` arm may fall outside the calibration band's low
  edge. Sliding-attention occupancy reasoning depends on undocumented per-core
  threadgroup-memory residency limits; the ALU-floor estimate carries about
  +/- 30%; cache behaviour is inferred from aggregate rates, not counters.
- Smallest useful next action: have **one** scheduler fire the receipt triple in
  the pre-registered order `low, high, control`, one at a time, since the arms
  and notes are already generated. In parallel, assign `oproj_act_h64` fusion to
  someone, and price restructuring **(a)** for sliding attention, which is
  zero-FP-risk.
- Recommendation: **close** this PR's r1 hypothesis as a dead end with a known,
  quantified cause; **merge** the research artefacts, in particular the ~93%
  serial bracket, which changes how every remaining prize on the board should be
  priced; **re-dispatch** deliverable A through a single submission scheduler
  rather than per-student; and **open** an `oproj_act_h64` fusion assignment.

_This report was generated by an AI agent (OpenHands) on behalf of the
maple-nezuko research student role._
