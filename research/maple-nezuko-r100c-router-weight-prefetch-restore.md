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
