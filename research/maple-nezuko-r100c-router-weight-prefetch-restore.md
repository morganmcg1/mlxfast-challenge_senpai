# R100-C — Router weight prefetch restoration (`DARKBLOOM_ROUTER_WEIGHT_PREFETCH`)

PR #558 · assignment `maple-r100-c-router-weight-prefetch-restoration` · revision
`r100-c-rev1` · base `2e490fa36ee58820dff636b63513d667fd019049`
(`codex/mlxfast-maple-20260804-advisor`).

## What this is

A **restoration**, not a new idea. The router-weight prefetch hoist existed on
this lineage and was lost to a rebase; the source of truth is commit
`e510bb3d094a59ae2d4285d6da4d1ba5361a2b23`. Its only prior measurement was on an
**M4 Pro** (`applegpu_g16s`, 48 GiB), which is weak evidence for the ranked M5.
The deliverable is a **decision about the lever**, not necessarily a win. A
clean, well-instrumented null that closes the lever is a fully successful
outcome.

Honest prior EV is ≈0.06 % of score. The circulating "+0.0628 %" is the M4
number rescaled by 0.5951; it has never been measured on M5.

## Hypothesis

**H-R3.** In the router GEMV, the first four-load group of `router_weight`
device reads depends only on `tile` / `simd_group` / `simd_lane` — never on the
norm. Unhoisted, those loads are issued *after* four `threadgroup_barrier`s, so
their memory latency cannot overlap the RMS reduction ladder. Hoisting that
group above the reduction tail recovers ≈4 µs/step of decode on M5, bit-exactly.

## Arms

Selected as the **minimal discriminating set** `{0, 1, 5}` rather than the
original `{0,1,2,3,4,5}`, which the brief explicitly permits, to protect the
editable byte budget.

| Arm | Env value | Meaning |
| --- | --- | --- |
| A0 = `pf0` | `0` | Unhoisted. Character-identical to HEAD's emitted source. |
| A1 = `pf1` | `1` | **Candidate.** One four-load group hoisted above the RMS reduction tail. |
| A1c = `pf1c` | `5` | **Placement control.** The character-identical peel emitted *below* the normalize barrier. |

`pf1` minus `pf1c` isolates *cross-barrier overlap* from the *peel itself*.
Default is `1`, matching the original lineage, so every end-to-end baseline leg
must set `DARKBLOOM_ROUTER_WEIGHT_PREFETCH=0` explicitly.

Only the `rows_per_thread == 1` accumulate shape has a prefetchable peel, so all
other shapes collapse to arm 0's source *and* arm 0's kernel name. Kernel
dictionary keys are `rowsPerGroup * 8 + prefetch`; collision-checked across
`{1,2,4,8,16,32,64} × {0,1,5}` (→ 8,9,13 / 16,17,21 / 32,33,37 / 64,65,69 /
128,129,133 / 256,257,261 / 512,513,517), which matters because
`uniqueKeysWithValues` traps on a duplicate.

Loads only: the accumulation order into `router_result[0]` is untouched, so
every arm is **bit-exact** with arm 0.

## Preregistered decision table

| Observation | Verdict |
| --- | --- |
| `pf1 < pf1c ≈ pf0` | Ship `pf1`. Cross-barrier overlap is real. |
| `pf1 ≈ pf1c < pf0` | Ship, **and fix the doc comment** — the gain is the peel, not the hoist. |
| `pf1 ≈ pf1c ≈ pf0` | Close the lever (see N-A / N-B below). |
| `pf1 > pf0` | Codegen tax. Close the lever (N-C; cross-ref #540). |

## Preregistered null explanations (written before any timing number exists)

These are committed **in advance** so that a null cannot be retro-fitted to
whichever story the data happens to suggest.

**N-A — Regime.** The router GEMV is not latency-bound at this size on M5, so
there is no exposed latency for the hoist to hide. M5's larger core count and
different memory hierarchy can move a kernel that was latency-bound on M4 Pro
into a bandwidth- or occupancy-bound regime.
*Falsifier:* achieved GB/s at or near the M5 roofline for this kernel. If the
kernel is already saturating bandwidth, N-A is confirmed and no scheduling
change can help. I will report achieved GB/s explicitly for this purpose.

**N-B — The compiler already does it.** The Metal compiler already hoists the
loads above the barriers in arm 0, making arms 0 and 1 the same machine code.
*Falsifier:* arm 0's ISA shows the four `router_weight` loads issued *before*
the first `threadgroup_barrier`. This is checked **statically, with no GPU
time**, in Step 1. **Stopping rule: if pf0's ISA already hoists the loads, N-B
is confirmed and the lever is closed with no timing work at all.**

**N-C — Codegen tax.** The hoist increases live registers across the reduction
ladder, cutting occupancy or forcing spills, and the scheduling win is smaller
than that cost. This is the mechanism behind #540.
*Falsifier:* per-arm register count, occupancy, and spill bytes from Step 1;
`pf1 > pf0` in timing with a matching register/occupancy regression.

## Measurement plan

Escalating cost; each step may terminate the experiment.

1. **Static codegen (no GPU).** `xcrun metal -S` + `metal-objdump` per arm:
   registers, occupancy, spill bytes, instruction count, and the **ISA position
   of the four `router_weight` loads relative to each `threadgroup_barrier`**.
   Closes N-B outright if pf0 already hoists.
2. **Zero-receipt A/B kernel probe**, run in **both** cache modes — default and
   SLC-defeat (≥128 MB unique footprint per round). A ±0.5 % null control
   (arm 0 vs arm 0) runs first and must pass. **A sign flip between the two
   cache modes is itself the headline result**, because it identifies the
   effect as an SLC-residency artifact rather than a scheduling win.
3. **In-situ per-kernel ABBA census**, n ≥ 12, on the
   `laguna_residual_rms_router_bf16_2048_rpg8_*` pool. Known σ = 3.34 µs/step.
   Achieved GB/s reported as N-A's falsifier.
4. **End-to-end `--local-iterate` A/B**, plus a **BASE-vs-BASE revert-control
   leg**. The revert control is a sanity check only and carries no preregistered
   threshold.

Local M4 timing is **directional evidence only**. Per the challenge guide, an
M4 Pro reports Apple GPU generation 16 and does not select the `_nax` prefill
kernels the ranked M5 uses; threadgroup geometry can also change sign across
core counts. No M4 result will be presented as an M5 verdict.

## Amended decision rule — recorded before any timing number exists

The research host is an **Apple M4 Pro, 20-core GPU, 48 GiB** — the same family
as the original R89 measurement. **This box cannot produce M5 evidence**, which
is precisely what the assignment asks the decision to rest on.

Re-running the M4 measurement as a *reproduction* would therefore add nothing:
it would restate the prior in the prior's own terms. So the M4 legs are
explicitly repurposed as a **survival test**. The original measurement was taken
on a much older lineage, many merged optimizations ago; the question that M4 can
still answer is whether the lever *survived the frontier*, not how big it is on
M5.

| M4 outcome | Verdict |
| --- | --- |
| Lever is **dead on M4 now** | **Close it.** The lever's entire evidential basis was a single M4 measurement. If it no longer pays on the very machine that once showed it, no surviving evidence from any machine supports it, and spending an official M5 slot is unjustified. |
| Lever is **alive on M4 now** | Hand the advisor a **live candidate**, reported as "alive on M4, M5 unknown". Only an official M5 run decides. No win is claimed from M4 data. |

This asymmetry is deliberate: M4 can *falsify* the lever outright but cannot
*confirm* it for the ranked machine.

## Step 1 results — static codegen, no GPU time

Generator dumped verbatim from the working tree via
`research/maple-nezuko-r100c-dump-msl.sh`; wrapped in MLX's exact kernel
signature and compiled by `research/maple-nezuko-r100c-isa.sh`.

**Control.** Arm `pf0` is **character-identical** to the generator on
`BASE_SHA`, so A0 is a valid control and later numbers are interpretable.
`pf1` and `pf1c` are both 4,391 B / 123 lines — the moved block is byte-identical,
so they differ *only* in placement.

**Emitted MSL** (rpg8, the default; 4 `threadgroup_barrier`s in every arm):

| Arm | Device `router_weight` load vs. the four barriers |
| --- | --- |
| `pf0` | body line 42-equivalent load sits **after** all four barriers |
| `pf1` | peel at body line 42, **before** all four barriers (48/52/59/71) |
| `pf1c` | peel at body line 70, **after** all four barriers (36/40/47/59) |

**Compiled AIR** (`-O3`, `air64_v28`), position of `load <4 x bfloat>
addrspace(1)` against `air.wg.barrier`:

| Arm | Barriers at IR line | Device vec4 loads at IR line | Hoisted? |
| --- | --- | --- | --- |
| `pf0` | 62, 73, 91, 96 | 152 | **no** |
| `pf1` | 94, 105, 123, 128 | **75**, 218 | **yes** |
| `pf1c` | 63, 74, 92, 97 | 147, 206 | **no** |

### N-B is refuted

The Metal compiler does **not** hoist these loads on its own. In `pf0` the load
remains behind all four barriers after full `-O3` optimization; in `pf1` it
moves to IR line 75, ahead of every barrier. The three arms are genuinely
different code, so the stopping rule for N-B does not fire and timing is
required.

This finding is **more than M4-local**: AIR is target-independent LLVM IR
produced by the Metal frontend, so "the compiler declines to hoist" holds for
any Apple GPU built by this toolchain. The caveat is that the per-generation AGX
backend scheduler is not visible here; it could in principle reorder further on
M5. That is unlikely for a load that in `pf0` sits *inside a loop* behind
barriers, but it is not proven, and I do not claim it as proven.

### N-C is not supported at the granularity available

Per-arm pipeline reflection (`research/maple_nezuko_r100c_pipeline_stats.swift`,
pipelines created only — no kernel run, no timing) on Apple M4 Pro:

| Arm | maxTotalThreadsPerThreadgroup | threadExecutionWidth | static threadgroup memory | launchable @512 |
| --- | --- | --- | --- | --- |
| `pf0` | 1024 | 32 | 4240 B | yes |
| `pf1` | 1024 | 32 | 4240 B | yes |
| `pf1c` | 1024 | 32 | 4240 B | yes |

All three arms are identical and sit at the **maximum** threadgroup size, so
register pressure does not limit occupancy in any arm and no codegen tax is
visible at this granularity. AIR instruction-proxy line counts are 369 / 438 /
426.

**Tooling limit, stated honestly:** exact register counts and spill bytes are
*not* obtainable. `metal-objdump --disassemble` on the `.metallib` returns AIR
(LLVM IR), not AGX ISA — the ISA is generated at pipeline-creation time on
device and no public tool dumps it. So N-C is *unsupported*, not *excluded*;
occupancy is a coarse proxy and these numbers are M4 backend numbers.

## Step 4a — pilot leg, and why the end-to-end axis is underpowered

One `./benchmark.sh --local-iterate` leg on the candidate arm `pf1`
(job `ec696126`, HEAD `a24b939`, `Sources`+`Vendor` digest identical before and
after: `58ab3978…97527`):

| field | value |
| --- | --- |
| `passed_correctness` | `true` |
| `max_abs_diff` | **0** |
| `checked_steps` | 130 |
| `decode_seconds_per_token` | 0.013063 |
| `prefill_seconds_per_token` | 0.001124 |
| `timed_benchmark_seconds` | **2.2** |
| leg wall time | 306 s |

Two things follow, and both are recorded **before** any census number exists.

**The shipping arm is bit-exact through the harness.** The JIT'd hoisted
pipeline reproduces every checked greedy token. That is the gate the
restoration had to clear to remain a candidate at all.

**The end-to-end axis cannot resolve this lever, by construction.** Decode is
≈12,956–13,063 µs/step here, so the historical 5.7 µs/step router effect is
**≈0.044 %** of a decode step. This also reconciles a tension in the prior
record: "1.8 % of the router kernel" and "≈0.06 % of score" are the *same*
number at two different grains, not two competing claims. With
`timed_benchmark_seconds = 2.2`, no realistic number of `--local-iterate` legs
gets near 0.04 %. The end-to-end A/B is therefore preregistered here as a
**no-regression sanity leg only**; it carries no threshold and cannot adjudicate
the hypothesis in either direction. Any conclusion must come from the in-situ
per-kernel estimator, which is the same estimator R89 showed had resolving power
on this host.

The locally reported `prefill_speedup 0.327` and its failed floor are a
**host artifact, not a regression**: `--local-iterate` divides by the official
M5 runner constant `baseline_prefill_seconds_per_token = 0.000368`, while this
M4 Pro prefills at 0.001124 s/token. Against the local baseline file, prefill
moves `0.001124 → 0.001124` (−0 %).

## Correctness gates

`--local-submit` (`max_abs_diff: 0`), `research/run_upstream_equivalence.sh`
(reporting the test count, refusing to call a zero-test invocation a pass), the
64-step drift tripwire, and `swift test`. The known-unrelated failure at
`SenpaiOperationalContractTests.swift:190` (sandbox git-push hook) is expected.

Rule 75: a sha256 digest over sorted `Sources/` + `Vendor/` is taken before the
build and again after the timed phase of **every** paired run.

## Byte budget

`LagunaRuntimeModel.swift` 511,418 → **515,604 B** (+4,186), against a per-file
cap of 524,288 B and this experiment's hard ceiling of +5,000 B
(≤ 516,418 B). The minimal `{0,1,5}` arm set is what keeps it there.

## Scope discipline

The edit is confined to HEAD LRM lines 676-705, 872-880, 900-1013, 1038-1058,
and 1129-1133. PR #539 owns 1548-1638; PR #555 owns 1639-1709 and 2140-2210.
The regions are disjoint. The comment-strip rung 2 is **not** applied in this
PR.

## Process finding (recorded up front)

During implementation, a concurrently-running **read-only `explore` subagent ran
`git checkout -- Sources/MLXFastModel/LagunaRuntimeModel.swift` and destroyed a
complete, verified set of working-tree edits** (515,604 B, +4,186 B, 102
insertions / 11 deletions). "Read-only" in an agent's description constrains its
*intent*, not its shell.

**Rule: never run any subagent, including `explore`, while the parent holds
uncommitted working-tree changes. Commit first.** This belongs alongside rule 75
in the standing process guidance.

## Step 4b: census pilot (REPS=2 STEPS=100 SPLIT=1, head 918136b)

A deliberately cheap validation of the whole census chain before committing an
hour of GPU time. `/tmp/r100c-census-pilot`, rc=0.

Integrity: `git status --porcelain` empty afterwards and
`digest_after == digest_before == 58ab3978…`, so the hook apply/build/sweep/
revert cycle provably leaves the submitted surface untouched.

Each arm selects a *distinct* pipeline — `…keys_v1`, `…keys_v1_pf1`,
`…keys_v1_pf1c` — which rules out the failure mode where the env knob silently
collapses onto one shared kernel. `divergences` 0 in all four slots.

Router µs/step, paired within-rep:

| arm | R89 (PR #488) | pilot |
| --- | --- | --- |
| pf0 | 318.5 | 319.40 |
| pf1 | 312.8 | 313.55 |
| pf1c | 323.5 | 319.75 |
| 0b null control | — | 319.45 (d = +0.05) |

`pf1 − pf0 = −5.85`, `pf1 − pf1c = −6.05` µs/step, against R89's −5.7 and
−6.85. The historical effect reproduces on this host.

### Resolvable floors, measured on this rig (null control, n=2)

| estimator | ±95% µs/step |
| --- | --- |
| per-kernel router label | **±9.9** |
| census absolute busy | ±228.7 |
| census union busy | ±228.7 |
| census wall | ±266.8 |
| end-to-end median | ±317.7 |

Only the per-kernel estimator is within an order of magnitude of a ~6 µs/step
effect; the end-to-end floor is 54× too coarse. This confirms the preregistered
end-to-end power limit **from this host's own data rather than from the prior**.

Consequence for reporting: a "no effect" reading from any of the four coarse
estimators must **not** be reported as a null. They are blind at this scale, and
their flat result is uninformative, not negative evidence.

## Hook lifetime (design note)

The gpuprof hook is needed only at *build* time; the sweep runs the linked
binary and never re-reads those sources. The census wrapper nevertheless holds
the Vendor working-tree edit for the entire run and reverts it in the EXIT trap,
so a ~30-minute sweep leaves the tree dirty throughout.

During the 12-rep census the hook was therefore reverted by hand immediately
after the build completed (worker `5e811560…` already linked and its sha
recorded), restoring the digest to `58ab3978…` mid-run. The trap later finds
nothing to reverse and prints a cosmetic `WARNING: hook revert failed`; the
integrity check that matters, `digest_after == digest_before`, still passes.

The wrapper should revert the hook right after `build_worker` instead, keeping
the tree clean for all but ~90 s. That edit is deliberately deferred until no
census is running: bash reads a script incrementally by file offset, so editing
a running script in place can corrupt its execution.
