# R87-A pre-registration — routed gate/up QMV head latency

Assignment `maple-r87-a-routed-qmv-head-latency`, revision `r87-a-rev1`, PR #469.
Branch `maple-tanjiro/r87-routed-qmv-head-latency`, base
`417f42c4167344afd2156b6f5d8ab76e2bf419f3` (`codex/mlxfast-maple-20260804-advisor`).

**Committed before any timing run.** Every number below is a prediction, not a
measurement. The result file scores each line HIT / MISS.

Written against the assignment body **plus** advisor comments 5228399317 (AGX
occupancy table) and 5228439746 (Correction 1: the mandated positive control is
dead code; Correction 2: the routed kernel already software-pipelines its weight
stream, so the arms become a three-point ladder). Priors below are the **revised**
ones from 5228439746.

## 0. Independent confirmation of both corrections

I verified both before writing this, because the assignment asks me to challenge
the brief rather than run a dead knob.

**Correction 1 confirmed.** `LagunaRuntimeModel.swift:5781–5788` gates
`lagunaNormAffineQKV` on `fusedAffine.mode == .affine, fusedAffine.bits == 8,
fusedAffine.groupSize == 32`. `:2903–2907` shows `DARKBLOOM_NATIVE_AFFINE_NVFP4`
defaults ON with `..._FROM` defaulting `"0"`, so every layer is NVFP4 g16
(`mode == .nvfp4, bits == 4, groupSize == 16`). The guard is false on all 40
layers, `fusedQKV` is always `nil`, and `:5805` always takes the
`?? inputNorm(input)` fallback. `DARKBLOOM_NORM_AFFINE_QKV_PF` is unreachable.
**It is not used as a control here.**

**Correction 2 confirmed — and I reached the same conclusion independently before
the comment arrived.** `:7839–7856` copies the current block's codes and scales
into `cur_*`, then issues the *next* block's scale and weight loads inside
`if (next_block < input_width)`, and only then runs the two `qdot` calls. The
weight stream is already software-pipelined across blocks 1..3. The exposed
serial head is the **loop preamble** only: the routing prelude (`:7795`) plus the
block-0 weight/scale load (`:7815–7825`).

## 1. Host and reachability (verified)

| property | value |
| --- | --- |
| chip | Apple M4 Pro, 20 GPU cores |
| unified memory | 48 GiB (low-memory startup profile) |
| macOS | 26.5.2 |
| GPU family | `applegpu_g16s` (Apple GPU generation 16) |
| `_nax` selected? | **no** — gen 16 does not select `_nax` |
| decode kernel family reachable? | **yes**, decode is 100% `laguna_*` |

This host is a legitimate screen for the **decode** axis because
`laguna_routed_nvfp4_swiglu_qmv_packed_top8keys_r1_bf16_v2` is the same kernel the
ranked M5 dispatches. It is **not** evidence for any `_nax` prefill change, and
this arm touches none. Occupancy-mediated results remain directional only: the
AGX table in comment 5228399317 is a G13 static model and this is G16.

## 2. What actually runs, and the mechanism

`DARKBLOOM_ROUTED_GATEUP_R1` (`:7767–7768`) is **default ON**, so the inline
literal at `:7770–7883` is the kernel that runs; the `:7600` generator produces
the off-by-default `_v1` twin. **All measured work goes into the `:7770` literal.**
See §7 for my position on also editing `:7600`.

Structure of the running kernel:

1. `:7789–7794` — ids, `lane`, `logical_row`. No memory dependency.
2. `:7795` `\(lagunaRouterTop8PrecomputedPrelude)` — 8 `router_keys` loads then
   `expert_slot+1` rounds of `laguna_router_top8_extract_round` (simd shuffles).
   **No threadgroup barriers**, so hoisted registers survive trivially.
3. `:7796–7805` — `expert = top8_winner` and every weight/scale base address.
4. `:7815–7825` — block-0 weight/scale prologue.
5. `:7827–7864` — 4-trip k-loop: input load, weight staging for `block+1`, qdots.

The only operand whose address is independent of the router is `input`
(`:7828–7830`, a pure function of `block` and `lane`). That is the A1 target.

### Roofline context I computed for this prereg (it drives my priors)

Per dispatch the grid is `8 slots * 256 tiles * 64 threads = 131072` threads =
**2048 threadgroups**. Weight bytes read per dispatch:

```
512 logical rows * 8 expert slots * (1024 B gate row + 1024 B up row) = 8.39 MB
```

PR #73 measured 39 R1 gate/up dispatches per decode step, so
`39 * 8.39 MB = 327 MB/step`. The advisor quotes 1501.7 µs/step for this kernel:

```
327 MB / 1501.7 us = 218 GB/s   vs ~273 GB/s peak on M4 Pro  =>  80% of peak
```

**This kernel is bandwidth-bound at ~80% of peak.** That matters for the priors:

- The **input** vector is 2048 bfloat = **4 KB total**, and all 2048 threadgroups
  in a dispatch read the same 4 KB. It is cache-resident after the first touch
  and contributes ~0% of DRAM traffic. So **A1 has no bandwidth lever** — it can
  only buy latency/MLP, and the machine already has ~7.9 waves of occupancy
  (832 threads/core ÷ 64 = 13 threadgroups/core × 20 cores = 260 resident of
  2048) with which to hide it.
- The **weights** are pure DRAM traffic. A2 issues the block-0 weight load before
  the router, raising memory-level parallelism on the one stream that actually
  limits the kernel. A2 is where the physics says the money is.

### A second reason I expect A1 to be small (mine, not the brief's)

Nothing stops the Metal compiler from doing A1 already. The k-loop has constant
bounds (4 trips) so it is very likely fully unrolled; `input` is a read-only
device pointer and the only write in the kernel is to `activated` at `:7876`, so
there is no aliasing barrier; and there is no `threadgroup_barrier` anywhere in
the kernel to block code motion. A sufficiently aggressive scheduler is already
free to sink the router and hoist the input loads. If it is doing so, A1 measures
exactly zero, and the honest reading of that null is "the compiler got there
first", not "latency hiding does not help".

## 3. Arms

| arm | knob | what changes | correctness gates |
| --- | --- | --- | --- |
| **A0** stock | none | unmodified `BASE_SHA` | yes (reference) |
| **P0/P2/P4** barrier control | `DARKBLOOM_PROBE_ROUTED_GATEUP_BARRIERS=0/2/4` | `B` extra `threadgroup_barrier(mem_flags::mem_none)` per k-loop trip | inert; timing only |
| **A1-steady** | `DARKBLOOM_ROUTED_GATEUP_INPUT_PF=1` | next block's input staged in the existing `:7844–7856` staging block | yes |
| **A1-preamble** | `=2` | block-0 input load hoisted **above** the routing prelude | yes |
| **A1-both** | `=3` | both | yes |
| **A2** ceiling probe | `DARKBLOOM_PROBE_ROUTED_EXPERT0_PF=1` | block-0 weight/scale address computation + loads hoisted above the prelude with `expert` hardcoded 0 | **NO — deliberately incorrect, timing only, never submitted** |

Implementation constraints I fix now:

- The `:7770` literal becomes a generator function whose **default output is byte
  identical to today's source**, so A0 and the unset-knob build are the same
  binary and there is no recompilation confound.
- Rule 33: any non-default configuration gets a distinct kernel-name suffix
  (`_pfin<mode>`, `_b<B>`, `_e0`). I will prove from the GPUPROF trace that the
  suffixed name is the one dispatched; if the stock name appears, the arm is void.
- Staged input is kept packed as `vec<bfloat,4> pf_in[4]` = 8 GPRs, not 16 floats,
  to minimise occupancy risk.
- A2 keeps the router **live** for free: blocks 1..3 staging at `:7850–7855` still
  uses `expert`, so no artificial dependency is needed to prevent dead-code
  elimination. Only the block-0 loads are replaced.
- Rule 24: one mechanism per arm; A1 and A2 are separate binaries and are never
  measured together.

## 4. Rig and its resolvable floor

End-to-end cannot see this. From my own PR #460 (same host, same harness): decode
12,960.20 µs/step with pooled decode SD **49.00 µs/step** at n=3/arm, so a
two-arm difference at 95% is

```
1.96 * 49.00 * sqrt(1/3 + 1/3) = 1.96 * 49.00 * 0.8165 = 78.4 us/step
```

(the advisor's ±111 µs uses a t-multiplier; either way −10 to −25 µs is
invisible). **Kernel-level timing is the primary discriminator.**

Rig: MLX dispatch profiler, local-only commit `a8a269d` (restores `64509eb`
verbatim) patching
`Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/device.{cpp,h}`. Neither file
is in `editablePaths`; **this commit is reverted before submission** (PR #73
precedent). Env `DARKBLOOM_GPU_PROFILE=1`, `DARKBLOOM_GPU_PROFILE_SPLIT=1` (one
dispatch per command buffer ⇒ per-kernel attribution). Driver
`research/decode_probe.py --steps 200 --profile`; step 0 discarded, 199 steady
steps retained.

Pre-declared caveats: `fputs` inflates **wall**, so only `gpu_busy_*` and
within-run ratios are admissible; `SPLIT=1` adds ≈1.681 µs per command buffer
(δ fitted in PR #73), which cancels in a same-family A/B but dilutes percentage
shares. PR #73 also measured `gpu_busy_sum == gpu_busy_union` in decode ⇒ **zero
dispatch concurrency**, so per-kernel deltas transfer 1:1 to step deltas.

**Resolvable floor, with the arithmetic.** Let `s` be the per-step SD (µs/step) of
the summed R1 gate/up busy time over the 199 steady steps of one run. SEM of a
run mean is `s/sqrt(199) = s/14.107`. For a difference of two independent runs at
95%:

```
floor_95 = 1.96 * sqrt(2) * s / sqrt(199) = 2.7719 * s / 14.107 = 0.19648 * s
```

I report measured `s` and `floor_95` from an **A/A** run (same binary, two
launches) before interpreting any A/B; the A/A also exposes run-to-run offset
that the formula does not capture, and I will report the A/A difference itself
against `floor_95` as a false-positive check.

Pre-registered usability bar: **`floor_95` ≤ 10 µs/step**, i.e. `s ≤ 50.9
µs/step` (3.4% of the 1501.7 µs/step family total). If not met I raise `--steps`
(floor scales `1/sqrt(N)`) and report the final N, before touching any code.

## 5. Positive control (replaces the dead QKV knob)

**Barrier-injection bloat arm**, built into the kernel under test:
`B ∈ {0, 2, 4}` extra `threadgroup_barrier(mem_flags::mem_none)` per k-loop trip,
i.e. `4B` extra barriers per threadgroup. Barriers are side-effecting so they
cannot be eliminated; the sign is known; the magnitude is dialable.

Prediction: **monotone increasing, roughly linear in B**. Point estimate for the
`B=0 → B=4` step: **+120 µs/step**, 80% interval **[+30, +400]**. Arithmetic:
16 extra barriers per threadgroup at a guessed ~25 cycles of synchronisation each
≈ 400 cycles ≈ 0.29 µs per threadgroup; with 79,872 threadgroups/step over 260
resident slots that is `0.29 * 79872 / 260 ≈ 89 µs/step` if fully exposed, less
if it overlaps stalls this bandwidth-bound kernel already has. The wide interval
is honest: I do not know the AGX barrier cost.

**Gate: the control passes if the `B=0 → B=4` step is positive and its magnitude
exceeds `floor_95` by at least 3×, with `B=2` falling between.** If the rig cannot
resolve `B=0 → B=4`, it cannot resolve A1 and I report rig failure with that as
the reason. This control tests exactly the kernel, grid, and rig used for A1,
which the QKV knob never would have.

## 6. Predictions — the actual pre-registration

Score conversion: **0.015280 % score per µs/step of decode**; a reduction of X
µs/step is +0.015280·X % score.

| arm | advisor prior (µs/step) | **my prediction** | my 80% interval | Δ score at my point estimate |
| --- | --- | --- | --- | --- |
| A1-steady | −25, [0, −70] | **−6** | [+8, −30] | +0.092 % |
| A1-preamble | −10, [0, −35] | **−4** | [+5, −20] | +0.061 % |
| A1-both | (composes) | **−9** | [+8, −38] | +0.138 % |
| A2 ceiling | −60, [−15, −180] | **−45** | [−5, −150] | (+0.688 %, **not a candidate**) |
| P: B=0→B=4 | n/a | **+120** | [+30, +400] | n/a |

I am **more pessimistic than the advisor on both A1 variants** and want that on
record with its reason: the input is 4 KB and cache-resident so A1 has no
bandwidth lever (§2 roofline), and the compiler is already unobstructed from
performing the same code motion (§2). I am close to the advisor on A2 because the
`expert` data dependency is one the compiler genuinely cannot break, and A2 acts
on the DRAM stream that actually limits this kernel.

Further pre-registered claims:

1. **A1-steady ≥ A1-preamble** in magnitude (3 of 4 iterations vs 1 of 4).
2. **A1-both ≈ A1-steady + A1-preamble** to within `floor_95` — they act on
   disjoint iterations, so they should compose additively.
3. **`maxTotalThreadsPerThreadgroup` unchanged** for every A1 variant (+8 GPRs
   packed). 75% confidence. If a variant drops a tier on the comment-5228399317
   table (832 → 768 → 704 …) I will name the tier and use it to explain a
   non-monotone curve rather than reporting the curve as a mystery.
4. **A1 is bit-exact**: `max_abs_diff = 0` vs A0 on decode. It hoists pure reads
   of an immutable buffer, consumed in stock order with an unchanged FP schedule.
   Anything non-zero is a bug in my hoist and I will fix it, not report it as a
   tolerance.
5. The known M4/gen-16 **prefill-only** equivalence artefact (max 0.125, mean
   ≈0.0119, argmax 5991 == 5991, decode steps 0..7 exactly zero) reproduces
   **digit-for-digit identical** to unmodified base.
6. **A2 exceeds the best A1 variant by ≥ 4×.** If it does not, the head-latency
   family is nearly exhausted by A1 alone and I will say so plainly — that
   finding would also lower the expected value of the un-fusion arm gated on #462.

## 7. Position on also editing `:7600` — stated early, as asked

The brief says twice that I must edit both `:7600` and `:7770–7771`. I will edit
`:7770–7771` for certain — that is the kernel that runs. I am **deferring**
`:7600` and flagging it now rather than silently:

- `DARKBLOOM_ROUTED_GATEUP_R1` is default ON, so a prefetch knob in the `:7600`
  generator is a knob on a fallback that never executes. It cannot be measured
  here, and AGENTS.md is explicit that such a knob is not a timing experiment.
- The binding constraint on this arm is **12,870 B of per-file headroom**.
  Duplicating the mechanism into the `_v1` twin spends that headroom on
  unmeasurable code.

Plan: implement and measure in `:7770` only. **If A1 clears the MERGE bar and byte
headroom remains, I port the winning variant to `:7600` for consistency before
submitting**, and report the exact byte cost. If A1 is null, porting a null
mechanism into a dead path is pure byte waste and I will not do it. If the
advisor disagrees, the port is a small follow-up.

## 8. GO / NO-GO, fixed now

- **Rig failure** ⇒ no A1 verdict is published. Triggers: barrier control fails
  its §5 gate; or `floor_95` still > 10 µs/step after raising N; or the GPUPROF
  trace shows the stock kernel name where a suffixed name was expected.
- **A1 MERGE** requires all of: (a) barrier control passed; (b) best A1 variant's
  reduction exceeds `floor_95` and its 95% interval excludes 0; (c)
  `max_abs_diff = 0` vs A0; (d) `research/run_upstream_equivalence.sh` passes with
  a stated **non-zero** test count; (e) 64-step tripwire passes with
  `MLXFAST_LOCAL_ALLOW_GOLDEN_DRIFT` **unset**; (f) byte budget green under
  `senpai/check-editable-budget.sh 417f42c4…` on the branch head.
- **A1 NULL** otherwise, reported plainly with the measured interval. A null is an
  acceptable outcome; I will not reach for a second mechanism to rescue it.
- **Recommended default**: OFF (`0`) unless the best variant clears the MERGE bar,
  in which case I recommend that mode as default and say so explicitly.
- **A2 is reported as `ceiling_us_per_step` only.** No correctness gate is run
  against it, no golden hash from it is reported, and it is never a candidate.

## 9. Byte budget, pre-declared

Base: `current=2891343/3000000 headroom=108657 growth=0/262144 files=140`.
`Sources/MLXFastModel/LagunaRuntimeModel.swift` = **511,418 B** of the 524,288 B
per-file cap ⇒ **12,870 B per-file headroom**. Allocation: ≈1.3 KB for A1
(generator conversion + fragments + doc comments), ≈0.8 KB for A2, ≈0.2 KB for the
barrier control, ≈2.3 KB total. If A1 + A2 would exceed the cap, **A2 is compacted
or dropped, never A1**, because only A1 can be submitted. Exact before/after sizes
and the `check-editable-budget.sh` output go in the result.

## 10. Out of scope (restated so I do not drift)

Routed down-reduce prefetch (`:7924`), the `patch_lane` peel, any real un-fusion
of routing (waits on #462), loop-invariant hoisting of
`logical_row`/`gate_row`/`up_row`/`sub`, and the `bfeil` dequant idea
(`laguna_nvfp4_qdot_16` is not touched in this PR).
