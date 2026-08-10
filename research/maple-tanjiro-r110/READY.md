# R110-A — prefill `_nax` arm queue, ready to fire

**For: maple-fern (sole submission driver).**
From: maple-tanjiro, PR #692, branch
`maple-tanjiro/r110-prefill-nax-arm-factory`.
Assignment base_sha: `9fe371909ee7ffa66a345cf3c42c21141096f388`.
Campaign submission BASE_SHA: `1bc1c8954147c9e322aad1f3b80bd9fa3c0888d7`.

This deliverable is a **queue of arms**, not a timing result. No local timing
number here is evidence for or against any arm — see "Read this first".

## Rebase provenance — why the gate evidence below still binds

This branch was rebased from `adfca1e5` onto the live base `9fe37190` after the
arms were built and gated. **The gates were not re-run, and do not need to be**,
for a checkable reason rather than an assurance:

```
$ git diff --numstat adfca1e5 9fe37190 -- Sources Vendor benchmark.json Package.swift
(empty)                       # the base moved by documentation commits only

$ git ls-tree -r <rev> -- Sources Vendor benchmark.json Package.swift | shasum -a 256
b8c8a395 (gated tree): 165121fe3d9d94e5e1baae54396b36fae9b9129c6f9ed9204ec21d51948cecd4
HEAD     (this tree):  165121fe3d9d94e5e1baae54396b36fae9b9129c6f9ed9204ec21d51948cecd4
```

The whole submitted surface is **byte-identical** before and after the rebase,
so job `1dce4167` measured this exact tree and a rebuild would be reproducing a
known-identical binary. GATES.md and `A1-expert-down-bn32.md` still cite the old
base `32665a6b` in their command transcripts; that is deliberate historical
record of what was actually executed, and it is equivalent because of the empty
diff above.

Note the rebase also dropped a stale copy of `research/CURRENT_RESEARCH_STATE.md`
that the pre-rebase branch would have reverted three advisor commits' worth of
edits to. Nothing on the submitted surface was involved.

## Read this first — why there is no local number

All three arms target **M5-only `_nax` kernels**. This host is `Mac16,11`
(M4 Pro, 48 GB, Apple GPU generation 16) and `is_nax_available()` returns
`false`, so none of the three retiled kernels is ever dispatched locally.

Every local gate below therefore proves exactly three things — **build
soundness, harness health, and that the non-NAX path is unperturbed** — and
nothing else. Local `prefill_seconds_per_token` and `decode_seconds_per_token`
must be read as "no regression on the path this host can reach", never as
evidence about the arm.

To correct an assumption made when this work was assigned: the local gates are
**not** more meaningful for A2 than for A1 or A3. A2's
`steel_matmul_regular_axpby_nax` sits behind the same `use_nax` gate
(`matmul.cpp:894-898`), and on M4 its target shape additionally takes the
split-k path. All three arms are equally M5-only.

`MLX_METAL_GPU_ARCH` was **not** set at any point. Forcing `_nax` on M4 is
forbidden by the assignment and was not attempted.

## Firing order

Fire in this order, **one arm per official run, never composed**:

| # | Arm | Surface | Expected leverage | Priority |
|---|-----|---------|-------------------|----------|
| 1 | **A1** — expert down `bn` 64 -> 32 | `quantized.cpp:1242` | primary | fire first |
| 2 | **A2** — fused-NAX `bn` 128 -> 64, prefill `N <= 1024` | `matmul.cpp:213-235` | 11.1 % of prefill dense GEMM at 1.6 -> 3.2 TG/core | fire second |
| 3 | **A3** — expert gather groups 256 -> 128 | `quantized.cpp:1225` | uncertain sign; informative either way | droppable |

Each arm is a **single knob**. Do not compose them, and do not bundle any of
them with maple-edward's R110-B work.

## Landing bar

The 0.378 % bar is **withdrawn**. Any arm that is non-negative and removes
**>= 0.3 ms of S** is worth landing.

Reference numbers to judge each receipt against:

- candidate `prefill_seconds_per_token` reference:
  **1.87812e-4 ± 2.607e-7 s/token** (n = 14, sd 0.103 %);
- 3 sd win threshold: **below 1.87030e-4 s/token**;
- prefill elasticity **0.362**; S ≈ **97.9 ms**, so **1 ms ≈ 0.37 % of score**;
- crown **2.61650354381456** vs our best **2.60664969895906** (`e27f1ce`),
  short by **0.378 %**;
- both speedup floors must stay **>= 0.95**.

For A2 specifically, `decode_seconds_per_token` must be **unchanged** — the arm
is guarded to `M >= 64`, so any decode movement is a red flag rather than a
result.

## Arm A1 — live on this branch

**Nothing to apply.** Commit `b8c8a395` on
`maple-tanjiro/r110-prefill-nax-arm-factory` already contains A1 and only A1:

```
Sources/... none
Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/quantized.cpp   1 +, 1 -
```

`darkbloom_expert_down_bn()` default `64` -> `32` at `quantized.cpp:1242`.

Fire this branch head directly. Details: `A1-expert-down-bn32.md`.

## Arm A2 — apply patch, then fire

A2 touches **`matmul.cpp` only**, and A1 touches **`quantized.cpp` only**, so
the A2 patch applies cleanly either to the assignment base or to this branch.
To keep one knob per run, apply it to a **clean base branch**:

```bash
git checkout -b maple-fern/r110-a2 9fe371909ee7ffa66a345cf3c42c21141096f388
git apply --check research/maple-tanjiro-r110/A2-fused-nax-bn64-n1024.patch
git apply           research/maple-tanjiro-r110/A2-fused-nax-bn64-n1024.patch
git commit -am "R110-A2: fused-NAX bn 128->64 for prefill N<=1024"
```

Verify the isolation before firing:

```bash
git --no-pager diff --numstat 9fe371909ee7ffa66a345cf3c42c21141096f388 HEAD
# expect exactly: 14  0  Vendor/mlx-swift/.../metal/matmul.cpp
```

Details: `A2-fused-nax-bn64-n1024.md`.

## Arm A3 — apply patch, then fire

A3 touches **`quantized.cpp`**, the same file as A1 but a different function.
It **must** be branched from the base, not stacked on A1:

```bash
git checkout -b maple-fern/r110-a3 9fe371909ee7ffa66a345cf3c42c21141096f388
git apply --check research/maple-tanjiro-r110/A3-expert-gather-groups-128.patch
git apply           research/maple-tanjiro-r110/A3-expert-gather-groups-128.patch
git commit -am "R110-A3: expert gather groups 256->128"
```

Verify:

```bash
git --no-pager diff --numstat 9fe371909ee7ffa66a345cf3c42c21141096f388 HEAD
# expect exactly: 1  1  Vendor/mlx-swift/.../metal/quantized.cpp
```

> **Trap worth knowing.** The A3 hunk is at `quantized.cpp:1223` and the A1
> hunk is at `quantized.cpp:1239`, so `git apply` of the A3 patch **succeeds
> on the A1 branch too** — silently producing a two-knob A1+A3 build with no
> error. `git apply --check` will not catch this. The `--numstat` step above
> is the real guard: a stacked build shows `2  2`, not `1  1`. Always run it.

Details: `A3-expert-gather-groups-128.md`.

> The patch files live on this branch under `research/maple-tanjiro-r110/`.
> When branching from the base (which does not contain them), copy them out
> first, e.g.
> `git show maple-tanjiro/r110-prefill-nax-arm-factory:research/maple-tanjiro-r110/A2-fused-nax-bn64-n1024.patch > /tmp/A2.patch`.

## Build notes that apply to all three arms

- All three are **JIT-only**. No `tools/build-mlx-metallib.sh` rebuild is
  needed, and **no kernel body is edited**, so no `mlx-generated/*.cpp` twin
  needs to be resynced.
- Use `./benchmark.sh --local-iterate` for the scored worker build; a bare
  `swift build -c release` writes a different build directory.
- Any direct `swift build` / `swift test` needs `--force-resolved-versions`,
  followed by `git checkout -- Package.resolved`.

## Scope and budget

Both checks pass for every arm; each arm submits exactly one path.

- A1 / A3 (`quantized.cpp`): `assignment scope OK: 1 submitted path(s)`;
  `editable budget OK: current=2681206/3000000 headroom=318794
  growth=-302643/262144 files=142`.
- A2 (`matmul.cpp`): `assignment scope OK: 1 submitted path(s)`;
  `editable budget OK: current=2681625/3000000 headroom=318375
  growth=-302224/262144 files=142`.

Growth is **negative** for all arms, so there is no submission-review byte risk.

## Gate evidence

All three arms are green on `./benchmark.sh --local-iterate`, each validated
**in isolation** (one knob in the tree at a time), and all three against the
identical `golden_hash` / `harness_hash` / `weights_hash` triple:

| Arm | Job | Worker commit | `passed` | `passed_correctness` | `max_abs_diff` |
|---|---|---|---|---|---|
| A1 | `1dce4167` | `b8c8a395` | true | true | 0 |
| A2 | `050988cf` | `38152ae8` | true | true | 0 |
| A3 | `2602e169` | `67f7d830` | true | true | 0 |

A1 additionally has an upstream-equivalence run plus a
`DARKBLOOM_EXPERT_DOWN_BN=64` control proving its lone prefill near-tie is
pre-existing and not caused by the arm.

Read the caveat at the top of this file before giving any of this weight: these
gates prove build soundness and non-NAX-path integrity, not `_nax` behaviour.

Full detail in `GATES.md`.

## Follow-up arms identified but deliberately not implemented

1. **A2 decode twin** — `M < 64 && N <= 1024` -> `bn = 64`, taking the decode
   wk/wv dispatch from 32 to 64 threadgroups. Decode is 75 % of the score, so
   this is the higher-leverage half of the A2 idea. It must be its own arm on
   its own branch.
2. **A2 next shape** — the single `N = 2048` layer-39 `[K;V]` bank dispatch
   (3.2 TG/core) if A2 wins.
3. **A3 inversion** — if A3 loses, `512` (more expert groups) is indicated, not
   `64`.
