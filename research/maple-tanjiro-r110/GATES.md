# R110-A — local gate log

Host: `Mac16,11`, Apple M4 Pro, 48 GB (`hw.memsize 51539607552`), low-memory
startup profile. Apple GPU generation 16, `is_nax_available() == false`.

Campaign submission base for the scope/budget scripts:
`1bc1c8954147c9e322aad1f3b80bd9fa3c0888d7`.
Assignment base for the diff: `30904ecbf180aa05d7ddf5cc957e83155fbfc6f4`.

> **rev3 note on base SHAs.** Transcripts below cite the earlier bases
> `32665a6b`, `adfca1e5` and `9fe37190`. All four bases are **surface-identical**
> — `git diff --numstat <a> <b> -- Sources Vendor benchmark.json Package.swift`
> is empty for every pair — so each transcript measures the same submitted
> surface. The old SHAs are left in place as historical record.

> **rev3 note on which arm is the head.** At rev2 the branch head carried **A1**
> and A2 was a patch. rev3 swaps them: the head now carries **A2 alone**, and A1
> is `A1-expert-down-bn32.patch`. Transcripts written before the swap still say
> "live on this branch" for A1; that is superseded by the head re-gate recorded
> in the A2 section.

## A1 — `darkbloom_expert_down_bn()` 64 -> 32 (live on this branch)

### Scope and budget

```
$ senpai/validate-assignment-scope.sh 1bc1c895... \
    Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/quantized.cpp
assignment scope OK: 1 submitted path(s)

$ senpai/check-editable-budget.sh 1bc1c895...
editable budget OK: current=2681206/3000000 headroom=318794 growth=-302643/262144 files=142
```

### Diff footprint

```
$ git diff --numstat 32665a6b66ce0d2d72b84772863575a6fdc35fb7 \
    -- Sources Vendor benchmark.json Package.swift
1	1	Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/quantized.cpp
```

### `./benchmark.sh --local-iterate` — GREEN

Job `1dce4167-dbc7-465c-bd3a-253c06501e5e`, exit 0, 243 s,
`"timestamp": "2026-08-10T23:00:45Z"`, worker commit `b8c8a395`.

```
"passed" : true
"passed_correctness" : true
"max_abs_diff" : 0
"golden_hash" : "b9509697c08a2cf3c2943a85f0b76e39c485c441794690fa76835b40a58d7a63"
"harness_hash" : "141c159403ce1514499bfeed5fb7335c872aa959d501afd30dfd495110b9fda6"
"weights_hash" : "aff994300573c5e8589563fc9ff57cdcfb1ef9b49e14898be290a75a6b294b3d"
"num_layers" : 40
"peak_ram_gb" : 21
prefill 0.001111 s/token   decode 0.012955 s/token   est score 0.798
```

`--local-iterate` runs the public correctness/drift tripwire before timing;
`passed_correctness: true` with `max_abs_diff: 0` against the pinned public
`golden_hash` **is** that tripwire passing.

`passed_prefill_speedup_floor: false` in the same JSON is the expected M4
artefact: the speedup denominators come from the pinned M5 calibration, not
from this host. The meaningful local comparison is the block against
`score.local-iterate.baseline.json`, and `"passed": true` is the overall
verdict.

### `research/run_upstream_equivalence.sh` — pre-existing near-tie, non-zero tests

Job `c53cc815-7498-4f69-a0cb-c7a4a2c4394d`, 66 s.

```
EQUIVALENCE_EXACT_STEPS=8
EQUIVALENCE_EXIT=1
prefill    maximumAbsoluteLogitError 0.125   mean 0.011933609   token 5991 == 5991
decode-0..7                                0   mean 0           tokens all ==
```

One test executed (`lagunaRuntimeMatchesVendoredUpstreamOnM5WhenEnabled`), so
this is **not** a zero-test invocation.

#### Control proving the divergence is not ours

Re-ran the identical wrapper with `DARKBLOOM_EXPERT_DOWN_BN=64`, which restores
the base value of the one line this arm changes without touching the tree.
Job `6ea76b5a-d815-4db1-b982-40a333164ceb`, 18 s.

The report is **byte-identical**: prefill `0.125` / `0.011933609` /
`5991 == 5991`, decode-0..7 exactly `0`, `EQUIVALENCE_EXACT_STEPS=8`,
`EQUIVALENCE_EXIT=1`.

This is the long-documented ~1 bf16 ULP prefill near-tie on non-M5 hosts —
`research/RESEARCH_ARCHIVE_through-round-91.md:4102` records the same
`0.125 / 0.011933609` pair as "proven pre-existing", and
`research/frieren-host-cpu-budget.md:471` and
`research/fern-r104b-wkwv-tile-regroup.md:366` record the same triple. Per
`AGENTS.md`, the prescribed response — test the unchanged base — was executed
and agrees exactly.

The control also confirms the second-order point: **A1 is inert on this host**,
which is exactly what the `_nax`-only gate predicts.

## A2 — fused-NAX `bn` 128 -> 64 **and** `wn` 4 -> 2, prefill `N <= 1024`

**This arm was corrected and re-gated after its first gate.** The section below
documents the shipped (`bn=64, wn=2`) form. The superseded forms are kept at the
end because what they prove about the *gate* is more useful than what they
proved about the arm.

### Scope and budget (corrected 17-line form)

```
$ senpai/validate-assignment-scope.sh 1bc1c895... \
    Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/matmul.cpp
assignment scope OK: 1 submitted path(s) against BASE_SHA=1bc1c895...

$ senpai/check-editable-budget.sh 1bc1c895...
editable budget OK: current=2681871/3000000 bytes headroom=318129
                    growth=-301978/262144 files=142
```

Growth is negative, so the 262,144-byte per-review growth cap is not at risk.

### Diff footprint — validated **in isolation**

A1's knob was reverted to the base value so the gated tree carried the A2 hunk
and nothing else:

```
$ git checkout 9fe37190 -- Vendor/.../metal/quantized.cpp
$ git --no-pager diff --numstat 9fe37190 HEAD -- Sources Vendor benchmark.json Package.swift
17	0	Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/matmul.cpp
```

The patch file is byte-for-byte what produced this tree:

```
$ git apply --check research/maple-tanjiro-r110/A2-fused-nax-bn64-n1024.patch   # exit 0
$ git apply --numstat research/maple-tanjiro-r110/A2-fused-nax-bn64-n1024.patch
17	0	Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/matmul.cpp
```

### `./benchmark.sh --local-iterate` — GREEN (A2 in isolation)

Job `1deaab28-3176-4bb8-ac35-8c9d36ee3d47`, exit 0, 203 s,
`"timestamp": "2026-08-11T00:09:56Z"`, worker commit `dcf03b2d`.

```
"passed" : true
"passed_correctness" : true
"max_abs_diff" : 0
"golden_hash" : "b9509697c08a2cf3c2943a85f0b76e39c485c441794690fa76835b40a58d7a63"
"harness_hash" : "141c159403ce1514499bfeed5fb7335c872aa959d501afd30dfd495110b9fda6"
"weights_hash" : "aff994300573c5e8589563fc9ff57cdcfb1ef9b49e14898be290a75a6b294b3d"
"num_layers" : 40
"peak_ram_gb" : 21
prefill 0.001139 s/token   decode 0.013032 s/token
```

### Branch-head re-gate after the rev3 promotion — GREEN

The isolation gate above ran on a throwaway commit. rev3 promoted A2 to the
**branch head**, so the exact tree fern will build was re-gated from scratch.

```
$ git --no-pager diff --numstat 30904ecb HEAD -- Sources Vendor benchmark.json Package.swift
17	0	Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/matmul.cpp

$ git apply --check research/maple-tanjiro-r110/A1-expert-down-bn32.patch    # exit 0
$ git apply --numstat research/maple-tanjiro-r110/A1-expert-down-bn32.patch
1	1	Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/quantized.cpp
```

Job `d7984b40-c214-400a-8637-5184864941a1`, exit 0, 230 s,
`"timestamp": "2026-08-11T00:33:16Z"`, worker commit `6ef4c58c` (the branch head
itself, not a throwaway).

```
"passed" : true
"passed_correctness" : true
"max_abs_diff" : 0
"golden_hash" : "b9509697c08a2cf3c2943a85f0b76e39c485c441794690fa76835b40a58d7a63"
"harness_hash" : "141c159403ce1514499bfeed5fb7335c872aa959d501afd30dfd495110b9fda6"
"weights_hash" : "aff994300573c5e8589563fc9ff57cdcfb1ef9b49e14898be290a75a6b294b3d"
"num_layers" : 40
"peak_ram_gb" : 21
prefill 0.001121 s/token   decode 0.012974 s/token
```

The hash triple is identical to every other gate in this file.

**`passed_prefill_speedup_floor` is `false` in the raw JSON on this host, and
that is expected, not a failure.** The pinned calibration baseline is M5-derived,
so an M4 Pro reports `prefill_speedup 0.328`; the harness still reports
`"passed": true` because the local-iterate verdict is the correctness verdict.
The stored unmodified-base run shows the same thing — `score.local-iterate.baseline.json`
(commit `5319168`) carries `"prefill_speedup": 0.3235` and
`"passed_prefill_speedup_floor": false`. Do not read the local speedup fields as
a ranked verdict.

**This run is also the cleanest available measurement of local noise.** It is the
*same arm* as the isolation gate above, on a byte-identical submitted surface,
and prefill moved 0.001139 → 0.001121, i.e. **1.6 %**. Both arms' entire
predicted effect is roughly a tenth of that.

### Composed A1+A2 sanity run — also GREEN

Run before the isolation re-gate, on a tree carrying **both** knobs
(`1 1 quantized.cpp` + `17 0 matmul.cpp`). Job
`65f1ed26-9868-4f66-81d6-227b0f283757`, exit 0, 229 s,
`"timestamp": "2026-08-11T00:05:35Z"`, worker commit `315b9fc6`,
`"passed": true`, `passed_correctness: true`, `max_abs_diff: 0`, identical hash
triple, prefill 0.001112 / decode 0.013095.

Recorded for completeness only. **A1 and A2 must never be fired composed on M5**
— one knob per official run. Neither temp commit (`315b9fc6`, `dcf03b2d`) is on
the branch; both were discarded after their gate, and the branch head is
`35575f28` carrying A1 alone.

### Superseded forms — and what they prove about this gate

Two earlier forms of A2 were gated green here and then discarded:

| Form | Job | Verdict | Why discarded |
|---|---|---|---|
| `N <= 1024`, no `M` guard, `bn=64` only | `71744112-6fd0-447f-9f1b-8a94591c5a02` | `passed` true, `max_abs_diff` 0 | thought to retile decode (see correction below) |
| `M >= 64 && N <= 1024`, `bn=64` only | `050988cf-efda-4dbf-95bb-f9466b45a4b2` (worker `38152ae8`) | `passed` true, `max_abs_diff` 0 | leaves `wn=4`, so `SN` 32 -> 16 |

The second one is the important one. Setting `bn=64` without `wn` gives
`SN = bn/wn = 16`, which (a) raises per-simdgroup operand traffic ~50 %,
(b) doubles total simdgroups from 512 to 1024, (c) emits `(64,64,256,2,4)`,
which is **absent** from the AOT instantiation list at
`kernels/steel/gemm/kernels/steel_gemm_fused_nax.metal:23-29` and so would be
JIT-compiled, and (d) selects the `TN == 1` branch of `tile_matmad_nax`
(`kernels/steel/gemm/nax.h:972-1029`) instead of the `TN % 2 == 0` branch.

**All three forms are indistinguishable on this host: green, `passed` true,
`max_abs_diff: 0`.** That is the single clearest statement of what these gates
are worth for `_nax` arms. See the closing section.

### Correction to the earlier `M >= 64` justification

The first version of this file justified the `M >= 64` guard by claiming decode
wk/wv runs at `M = 8` through the regular fused-NAX entry. **That is wrong.**
`Matmul::eval_gpu` short-circuits at `matmul.cpp:1269-1270`:

```cpp
if (std::min(M, N) == 1) {
  return gemv(...);
}
```

Teacher-forced decode is 128 one-token steps, so `M = 1` and every dense
projection exits through `gemv` before any steel tile is selected. Decode
reaches **zero** dense steel GEMMs. The guard is therefore **free rather than
load-bearing**; it is retained because it costs nothing and mirrors the prefill
gate at `quantized.cpp:1393-1397`.

## A3 — `darkbloom_expert_gather_groups()` 256 -> 128 — **DROPPED, do not fire**

The gate evidence below is real and was collected before the arm was audited
against prior art. It is retained as an accurate record of what was executed.

**The arm itself is withdrawn.** The group-count sweep is a closed experiment,
and A3 moves *backwards* along it. The tree default is already 256
(`quantized.cpp:1226`). Two independent receipts say so:

1. **An M5 measurement.** The comment stripped in
   `research/nezuko-r99b/rung1-comment-strip.patch:7390-7393` reads: "Measured
   on M5 Max against the promoted 64 schedule, 128 captures roughly two-thirds
   of the 256 schedule's prefill gain ... 256 measures closer to the acceptance
   ceiling." 128 is the *weaker* of the two on the ranked machine.
2. **A queue simulation.** `research/pr142-lpt-expert-queue-refutation.md:274`
   ("Simulating it refutes the idea") through `:293` concludes the "**current
   default `egroups = 256` is optimal**", and `:296` calls the knob
   "**ambiguous, not dominant**, worth at most ~0.5 ms, and sign-uncertain".

`research/maple-alphonse-r107c-expert-gather-gemm-floor.md:92` records the
resulting "⇒ Stage A arm 3 dropped".

**Citation retraction.** An earlier draft of this file also cited
`research/PREFILL_NAX_ANALYSIS.md:56-60`. That document is **retracted as
unsourced** — `research/CURRENT_RESEARCH_STATE.md:123-125` states "Its egroups
claim (`:56-60`) carries no numbers or receipts". It is removed here and must
not be re-cited. The drop still holds on the two receipts above, which are
independent of it.

A green local gate does not make a re-run of a settled question worth an M5
slot. See `READY.md` §7.

### Scope and budget

```
$ senpai/validate-assignment-scope.sh 1bc1c895... \
    Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/quantized.cpp
assignment scope OK: 1 submitted path(s)

$ senpai/check-editable-budget.sh 1bc1c895...
editable budget OK: current=2681206/3000000 headroom=318794 growth=-302643/262144 files=142
```

Identical to A1's figures because `256` -> `128` is length-preserving.

### Diff footprint

Validated in isolation: A1's knob was temporarily reverted so `quantized.cpp`
carried only the A3 hunk.

```
$ git diff --numstat 32665a6b... -- Sources Vendor
1	1	Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/quantized.cpp
```

### `./benchmark.sh --local-iterate` — GREEN

Job `2602e169-cd34-49f0-ae6e-884a129da56c`, exit 0, 203 s,
`"timestamp": "2026-08-10T23:20:00Z"`, worker commit `67f7d830`.

```
"passed" : true
"passed_correctness" : true
"max_abs_diff" : 0
"golden_hash" : "b9509697c08a2cf3c2943a85f0b76e39c485c441794690fa76835b40a58d7a63"
"harness_hash" : "141c159403ce1514499bfeed5fb7335c872aa959d501afd30dfd495110b9fda6"
"weights_hash" : "aff994300573c5e8589563fc9ff57cdcfb1ef9b49e14898be290a75a6b294b3d"
"num_layers" : 40
"peak_ram_gb" : 21
prefill 0.001117 s/token   decode 0.012976 s/token   est score 0.796
```

The same `golden_hash` / `harness_hash` / `weights_hash` triple as A1 and A2,
so all three arms were gated against an identical harness, weight set, and
public golden.

## What these local gates do and do not prove

`is_nax_available()` is false here, so no `_nax` kernel is ever selected. Every
arm in this queue changes only `_nax` tile/geometry selection. The local green
therefore proves:

* the tree compiles and links,
* the harness, weights, and public golden are healthy,
* the non-NAX path (which is what actually executes here) is unperturbed,
* the change cannot break a non-M5 build.

It does **not** prove `_nax` numerics, `_nax` JIT pipeline creation, or any
timing claim. The M5 receipt is the first real test of every arm here. Local
prefill/decode seconds in this file are host bookkeeping, not evidence for or
against any arm.

**This round supplied a concrete demonstration rather than a caveat.** Three
materially different versions of A2 were gated on this host — one that would
have retiled an unguarded shape, one that silently drove `SN` to 16 and fell off
the AOT instantiation list into a JIT build on a different `tile_matmad_nax`
branch, and the corrected traffic-neutral form. **All three returned `passed:
true`, `passed_correctness: true`, `max_abs_diff: 0`, and the same
`golden_hash` / `harness_hash` / `weights_hash` triple.** The defect in the
second form was found by reading the kernel's instantiation list and matmad
branches, not by any gate available on this machine.

Treat a green M4 gate on an `_nax` arm as a build check. It is not a review.
