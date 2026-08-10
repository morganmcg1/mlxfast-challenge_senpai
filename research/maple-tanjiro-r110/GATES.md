# R110-A — local gate log

Host: `Mac16,11`, Apple M4 Pro, 48 GB (`hw.memsize 51539607552`), low-memory
startup profile. Apple GPU generation 16, `is_nax_available() == false`.

Campaign submission base for the scope/budget scripts:
`1bc1c8954147c9e322aad1f3b80bd9fa3c0888d7`.
Assignment base for the diff: `32665a6b66ce0d2d72b84772863575a6fdc35fb7`.

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

## A2 — fused-NAX `bn` 128 -> 64 for prefill `N <= 1024` (delivered as patch)

### Scope and budget

```
$ senpai/validate-assignment-scope.sh 1bc1c895... \
    Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/matmul.cpp
assignment scope OK: 1 submitted path(s)

$ senpai/check-editable-budget.sh 1bc1c895...
editable budget OK: current=2681625/3000000 headroom=318375 growth=-302224/262144 files=142
```

### Diff footprint

```
$ git diff --numstat 32665a6b... 38152ae8 -- Sources Vendor
14	0	Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/matmul.cpp
```

`matmul.cpp` is byte-identical between the assignment base and the A1 head, so
`A2-fused-nax-bn64-n1024.patch` (generated against the base) contains the A2
knob and nothing else. Verified with `git apply --check` against a base-state
`matmul.cpp` after the A2 source was reverted from this branch:

```
A2 PATCH APPLIES CLEANLY TO BASE-STATE matmul.cpp
```

### `./benchmark.sh --local-iterate` — GREEN

Job `050988cf-efda-4dbf-95bb-f9466b45a4b2`, exit 0, 203 s,
`"timestamp": "2026-08-10T23:14:47Z"`, worker commit `38152ae8`.

```
"passed" : true
"passed_correctness" : true
"max_abs_diff" : 0
"golden_hash" : "b9509697c08a2cf3c2943a85f0b76e39c485c441794690fa76835b40a58d7a63"
"harness_hash" : "141c159403ce1514499bfeed5fb7335c872aa959d501afd30dfd495110b9fda6"
"weights_hash" : "aff994300573c5e8589563fc9ff57cdcfb1ef9b49e14898be290a75a6b294b3d"
"num_layers" : 40
"peak_ram_gb" : 21
prefill 0.001127 s/token   decode 0.012973 s/token   est score 0.794
```

### Note on the guard

An earlier, **unguarded** form of this arm (`N <= 1024` with no `M` condition)
also ran green here — job `71744112-6fd0-447f-9f1b-8a94591c5a02`, exit 0,
`"timestamp": "2026-08-10T23:10:49Z"`, `"passed": true`,
`passed_correctness: true`, `max_abs_diff: 0`. It was **discarded anyway**,
because decode wk/wv (`M=8, N=1024, K=2048`) does not divert to split-k at
`matmul.cpp:922-925` and therefore reaches the same regular fused-NAX entry as
prefill. The unguarded form would have silently retiled a decode GEMM carrying
75 % of the score. The shipped form adds `M >= 64`, mirroring the existing
gate at `quantized.cpp:1393-1397`.

That this host cannot tell the two forms apart (both green, both bit-exact) is
itself a demonstration of the caveat below: the local gate has no visibility
into `_nax` geometry at all.

## A3 — `darkbloom_expert_gather_groups()` 256 -> 128 (delivered as patch)

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

`is_nax_available()` is false here, so no `_nax` kernel is ever selected. All
three arms (A1, A2, A3) change only `_nax` tile/geometry selection. The local
green therefore proves:

* the tree compiles and links,
* the harness, weights, and public golden are healthy,
* the non-NAX path (which is what actually executes here) is unperturbed,
* the change cannot break a non-M5 build.

It does **not** prove `_nax` numerics, `_nax` JIT pipeline creation, or any
timing claim. The M5 receipt is the first real test of every arm in this queue.
Local prefill/decode seconds in this file are host bookkeeping, not evidence
for or against any arm.
