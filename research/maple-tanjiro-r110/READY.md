# R110-A — prefill `_nax` arm queue

**For: maple-fern (sole submission driver).**
From: maple-tanjiro, PR #692, branch
`maple-tanjiro/r110-prefill-nax-arm-factory`.
Assignment base_sha: `9fe371909ee7ffa66a345cf3c42c21141096f388`.
Campaign submission BASE_SHA: `1bc1c8954147c9e322aad1f3b80bd9fa3c0888d7`.

This deliverable is a **queue of arms**, not a timing result. No local number in
this directory is evidence for or against any arm — see §2.

---

## 0. Bottom line, revised

The queue shipped four candidate arms. After a prior-art and magnitude audit,
**two survive as things to run, one is dropped, one is recorded as a dead end.**

| Arm | Disposition | Why |
|---|---|---|
| **A1** — expert down `bn` 64 → 32 | **FIRE. Live on this branch head.** | Genuinely never measured; the only arm here with an un-audited hypothesis. |
| **A2** — fused-NAX `bn` 128 → 64 **+ `wn` 4 → 2**, prefill `N ≤ 1024` | **Patch delivered; do NOT spend a standalone M5 slot.** | Ceiling ≈ 0.93 ms ≈ +0.35 % score. Third visit to this site. Ride along only. |
| **A3** — expert gather groups 256 → 128 | **DROPPED.** | Prior art already measured 256 as optimal. Firing it re-runs a closed experiment. |
| **A4** — split-K `partition_size` halving for narrow `N` | **DEAD END, documented so nobody re-derives it.** | Not bit-exact; 0.42 ms analytic floor; already ranked last as H5; Rule 99.6 forbids assigning it. |

If fern has exactly one slot for this queue: **fire A1, ignore the rest.**

## 1. Rebase provenance — why the A1 gate evidence still binds

This branch was rebased from `adfca1e5` onto the live base `9fe37190` after the
arms were built and gated. The A1 gate was not re-run and does not need to be:

```
$ git diff --numstat adfca1e5 9fe37190 -- Sources Vendor benchmark.json Package.swift
(empty)                       # the base moved by documentation commits only

$ git ls-tree -r <rev> -- Sources Vendor benchmark.json Package.swift | shasum -a 256
b8c8a395 (gated tree): 165121fe3d9d94e5e1baae54396b36fae9b9129c6f9ed9204ec21d51948cecd4
HEAD     (this tree):  165121fe3d9d94e5e1baae54396b36fae9b9129c6f9ed9204ec21d51948cecd4
```

The submitted surface is **byte-identical** before and after the rebase, so job
`1dce4167` measured this exact tree. GATES.md and `A1-expert-down-bn32.md` still
cite the old base `32665a6b` in their command transcripts; that is deliberate
historical record and is equivalent because of the empty diff above.

A2 **was** re-gated after its correction (§5), because its source actually
changed.

## 2. Read this first — why there is no local number

Every arm here targets **M5-only `_nax` kernels**. This host is `Mac16,11`
(M4 Pro, 48 GB, Apple GPU generation 16) and `is_nax_available()` returns
`false`, so none of the retiled kernels is ever dispatched locally.

Every local gate therefore proves exactly three things — **build soundness,
harness health, and that the non-NAX path is unperturbed** — and nothing else.

The sharpest demonstration of this limit: the **wrong** version of A2 (§5) gated
green here, bit-exact, `max_abs_diff: 0`, indistinguishable from the corrected
version. The local gate had no way to see the defect.

To correct an assumption made when this work was assigned: the local gates are
**not** more meaningful for A2 than for A1. A2's
`steel_matmul_regular_axpby_nax` sits behind the same `use_nax` gate
(`matmul.cpp:894-898`).

`MLX_METAL_GPU_ARCH` was **not** set at any point. Forcing `_nax` on M4 is
forbidden by the assignment and was not attempted.

## 3. Landing bar

Any arm that is non-negative and removes **≥ 0.3 ms of S** is worth landing.

- candidate `prefill_seconds_per_token` reference:
  **1.87812e-4 ± 2.607e-7 s/token** (n = 14, sd 0.103 %);
- 3 sd win threshold: **below 1.87030e-4 s/token**;
- prefill elasticity **0.362**; S ≈ **97.9 ms**, so **1 ms ≈ 0.37 % of score**;
- maple's deficit to the crown is **~1.4 % of real speed ≈ 3.8 ms of prefill**;
- both speedup floors must stay **≥ 0.95**.

For A2, `decode_seconds_per_token` must be **unchanged**; see §4 for why that is
now a tautology rather than a check.

## 4. Prefill dense-GEMM census — the map both surviving arms are read against

Traced dispatch counts, per forward pass, `M = 512` throughout. M5 has 40 cores,
so "TG/core" is the occupancy-quantization column that matters.

| count | shape | entry point | TGs | TG/core |
|---|---|---|---|---|
| 78 | wk/wv `N=1024 K=2048` | regular nax | 64 | **1.60** |
| 31 | wq `N=8192 K=2048` | regular nax | 512 | 12.8 |
| 10 | wq `N=6144 K=2048` | regular nax | 384 | 9.6 |
| 1 | layer-39 `[K;V] N=2048 K=2048` | regular nax | 128 | 3.2 |
| 38 | router `N=256 K=2048` | **splitk** nax | 64 | 1.60 |
| 29 | g_proj `N=64 K=2048` | **splitk** nax | 16 | **0.40** |
| 10 | g_proj `N=48 K=2048` | **splitk** nax | 16 | **0.40** |
| 30 | wo `N=2048 K=8192` | **splitk** nax | 512 | 12.8 |
| 10 | wo `N=2048 K=6144` | **splitk** nax | 512 | 12.8 |

**Σ 237 steel dispatches + 117 split-K accumulations, 48,368 threadgroups.**

Three structural facts that repeatedly mislead people, including me:

1. **`N ≤ 1024` in `steel_matmul_regular_axpby_nax` reaches only the 78 wk/wv
   dispatches.** Router and g_proj are also narrow but leave through
   `steel_gemm_splitk_axpby_nax`, whose tile block is separate code at
   `matmul.cpp:665-684`. A2's coverage is **78, not 155**.
2. **Decode reaches zero dense steel GEMMs.** `Matmul::eval_gpu` short-circuits
   at `matmul.cpp:1269-1270` with `if (std::min(M, N) == 1) return gemv(...)`,
   and teacher-forced decode is 128 one-token steps, so `M = 1` always. Any arm
   in `matmul.cpp`'s steel tile selection is **structurally prefill-only**.
   This kills the "A2 decode twin" follow-up that an earlier version of this
   file proposed — there is no decode steel dispatch to retile.
3. **Prefill dense GEMM already runs at ~52.5 TFLOP/s ≈ 87.5 % of reference
   peak** on ~1.5 TFLOP of work. There is roughly 0.2 ms of total slack in the
   whole dense-GEMM budget at realistic efficiencies. Any brief whose premise is
   "prefill matmul is inefficient" is refuted before it starts.

The corollary is the most useful thing in this document: **~27.88 ms (28.5 %) of
prefill is unattributed to dense GEMM at all.** That block — norms, RoPE, SDPA,
routing top-k/sort, gather/scatter, casts, copies, transposes, sync points — is
the only target on the map large enough to cover a 3.8 ms deficit. Every arm in
this queue is fishing in the 87.5 %-efficient pond.

## 5. Arm A1 — FIRE. Live on this branch head.

**Nothing to apply.** The branch head `35575f28` contains A1 and only A1:

```
$ git --no-pager diff --numstat 9fe371909ee7ffa66a345cf3c42c21141096f388 HEAD \
    -- Sources Vendor benchmark.json Package.swift
1  1  Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/quantized.cpp
```

`darkbloom_expert_down_bn()` default `64` → `32` at `quantized.cpp:1242`.
Prefill-only via the existing `M >= 64` accept gate at `quantized.cpp:1404-1407`.
JIT-only; no metallib rebuild. `DARKBLOOM_EXPERT_DOWN_BN=64` restores the
incumbent for a one-binary paired A/B.

**Why A1 is the one worth a slot.** The expert-gather-GEMM floor study
(`research/maple-alphonse-r107c-expert-gather-gemm-floor.md`, Q4) explicitly
records `bn` 64 → 32 as *genuinely never measured*. Unlike A2 and A3 it is not
re-treading a closed or previously-queued experiment.

Fire this branch head directly. Details: `A1-expert-down-bn32.md`.

## 6. Arm A2 — patch delivered, but do not spend a standalone slot

A2 was **corrected after its first gate**. The original set `bn = 64` alone,
leaving `wn = 4`, which drives `SN` 32 → 16: +50 % per-simdgroup operand traffic,
1024 total simdgroups instead of 512, an emitted tuple `(64,64,256,2,4)` that is
**not AOT-instantiated**, and the less-travelled `TN == 1` branch of
`tile_matmad_nax`. The shipped form sets `bn = 64; wn = 2;` — `SM×SN` stays
32×32, total simdgroups stays 512, the tuple `(64,64,256,2,2)` **is** AOT
(`steel_gemm_fused_nax.metal:23-29`), the matmad branch is unchanged, and the
change is **bit-exact by construction**. It is a pure repacking: 64 TG × 8 sg →
128 TG × 4 sg.

```bash
git checkout -b maple-fern/r110-a2 9fe371909ee7ffa66a345cf3c42c21141096f388
git show maple-tanjiro/r110-prefill-nax-arm-factory:research/maple-tanjiro-r110/A2-fused-nax-bn64-n1024.patch > /tmp/A2.patch
git apply --check /tmp/A2.patch && git apply /tmp/A2.patch
git commit -am "R110-A2: fused-NAX bn 128->64, wn 4->2 for prefill N<=1024"
git --no-pager diff --numstat 9fe371909ee7ffa66a345cf3c42c21141096f388 HEAD
#   expect exactly: 17  0  Vendor/mlx-swift/.../metal/matmul.cpp
```

**Rule-83 disclosure — this is the third visit to this site.** PR #293
(`DARKBLOOM_STEEL_REGULAR_SKINNY_TILE`, same `bn=64, wn=2`) was merged inert and
deleted by resync `99b974c` with **zero M5 receipts**; PR #585 / fern R104-B
(`DARKBLOOM_NAX_SKINNY_TILE`) self-retracted a priori, also unmeasured. The
campaign replacement rule (`research/CURRENT_RESEARCH_STATE.md:4120-4130`)
rejects narrow-`_nax`-tile briefs on the measured **+0.639 ms M5 regression from
PR #527 (Rule 68)** and on magnitude. A2 is inside the class that rule names.

**Magnitude.** wk/wv is 167.5 GFLOP = 11.1 % of prefill dense GEMM. Ceiling
**≈ 0.93 ms ≈ +0.35 % score**; realistic ≈ 0.29 ms ≈ +0.11 %.

**The one piece of positive evidence.** Fern's M4 probe (fern §7, job
`0c4e2817-f311-4933-ba80-b6487d6eb9dd`) measured that at a fixed total of 512
simdgroups, **8 sg/TG costs 1.4613× what 4 sg/TG costs**, with a §7.2 causal
control isolating it as pure packing/occupancy quantization, and 512 sitting in
the worst band fern observed. A2 moves exactly that variable on a dispatch family
at 1.60 TG/core. **Fern refuses to extrapolate the band location to M5 and so do
I** — M4 never selects `_nax`, so this measures the mechanism, not the kernel.

**Recommendation: ride-along only.** If a wk/wv-family M5 slot is ever scheduled
for another reason, A2 is the cheapest possible passenger — one env var
(`DARKBLOOM_FUSED_NAX_NARROW_BN`), one binary, bit-exact, AOT-instantiated.
Details and the full geometry table: `A2-fused-nax-bn64-n1024.md`.

## 7. Arm A3 — DROPPED, do not fire

`darkbloom_expert_gather_groups()` 256 → 128 at `quantized.cpp:1225`.
The patch file `A3-expert-gather-groups-128.patch` remains in this directory for
provenance only.

**It is a closed experiment.** `research/maple-alphonse-r107c-expert-gather-gemm-floor.md:86-91`
records the group-count sweep with **256 already optimal** and notes "Stage A
arm 3 dropped" for exactly this reason. The same conclusion appears in
`research/nezuko-r99b/rung1-comment-strip.patch:7381-7394` and
`research/PREFILL_NAX_ANALYSIS.md:56-60`. Firing A3 would spend an M5 slot
re-measuring a known answer.

I did not find this before building and gating it. That is my error, and the
correction is worth more to fern than the arm was.

> **Trap that survives the drop.** If anyone revives A3: its hunk is at
> `quantized.cpp:1223` and A1's is at `:1239`, so `git apply` of the A3 patch
> **succeeds on the A1 branch**, silently producing a two-knob build.
> `git apply --check` does **not** catch this. Only `--numstat` does —
> a stacked build shows `2  2`, a clean one shows `1  1`.

## 8. Arm A4 — designed, then refuted. Recorded as a dead end.

`DARKBLOOM_SPLITK_NARROW_N`: halve `split_k_partition_size` for `M >= 64 &&
N <= 512` split-K nax shapes, targeting the router (`N=256`, 38×) and g_proj
(`N=64/48`, 39×) dispatches that sit at **0.40–1.60 TG/core** — by far the worst
occupancy on the map, and the obvious next move once §4 shows A2 cannot reach
them.

**It is dead for four independent reasons, any one sufficient:**

1. **Not bit-exact.** Changing the partition size changes the grouping of the
   fp32 split-K reduction. Correctness is a hard gate; this is disqualifying on
   its own.
2. **Magnitude.** The analytic floor for router + g_proj combined is **0.42 ms**
   (`research/RESEARCH_IDEAS_steel-gemm-prefill.md:45-46`) — below the landing
   bar even at 100 % capture.
3. **Already enumerated.** It exists as hypothesis **H5** at
   `research/RESEARCH_IDEAS_steel-gemm-prefill.md:200-207`, ranked **last**.
4. **Explicitly forbidden as an experiment.** Rule 99.6
   (`research/CURRENT_RESEARCH_STATE.md:6218-6231`) says do not assign it as a
   timed experiment.

I am recording it in full because the reasoning chain that produces it —
"g_proj is at 0.40 TG/core, that is terrible, split-K partition size is the
knob" — is short, correct-looking, and will be re-derived by the next person who
reads the census in §4. It ends here.

One genuinely open observation from the same investigation, offered without a
brief attached: the split-K path has **no M5 swizzle override** (grid setup
`matmul.cpp:740-766`) where the regular path has `swizzle_log = 2`
(`matmul.cpp:280-308`). That asymmetry is unexplained and is bit-exact to change.
It is not an arm in this queue.

## 9. Build notes that apply to A1 and A2

- Both are **JIT-only**. No `tools/build-mlx-metallib.sh` rebuild is needed, and
  **no kernel body is edited**, so no `mlx-generated/*.cpp` twin needs resyncing.
- Use `./benchmark.sh --local-iterate` for the scored worker build; a bare
  `swift build -c release` writes a different build directory.
- Any direct `swift build` / `swift test` needs `--force-resolved-versions`,
  followed by `git checkout -- Package.resolved`.
- One knob per official run. Never compose A1 with A2, and never bundle either
  with maple-edward's R110-B work.

## 10. Scope and budget

Each arm submits exactly one path; both checks pass.

- A1 (`quantized.cpp`): `assignment scope OK: 1 submitted path(s)`;
  `editable budget OK: current=2681206/3000000 headroom=318794
  growth=-302643/262144 files=142`.
- A2 (`matmul.cpp`): `assignment scope OK: 1 submitted path(s)`;
  `editable budget OK: current=2681625/3000000 headroom=318375
  growth=-302224/262144 files=142`.

Growth is **negative** for both, so there is no submission-review byte risk.

## 11. Gate evidence

See `GATES.md` for full transcripts. Read §2 before giving any of it weight.

A1 additionally has an upstream-equivalence run with a confirmed non-zero test
count, plus a `DARKBLOOM_EXPERT_DOWN_BN=64` control proving its lone prefill
near-tie is pre-existing and not caused by the arm.

## 12. A live trap in the kernel, for anyone sweeping tiles after us

`tile_matmad_nax` (`kernels/steel/gemm/nax.h:972-1029`) has a
`TN == 1 && TM % 2 == 0` arm and a `TN % 2 == 0` arm and **no else branch**.
With `TM = 1`, any odd `TN` emits **no MMA at all and writes zeros** — a silent
wrong-answer, not a compile error or a crash.

Any future `BN` sweep must be validated **jointly with `WN`**, with the standing
requirement `(BN / WN) % 32 == 0`. This is why A2 moves `wn` with `bn`.

Related, and unexplored: the expert-path `BK` is hardcoded to `64` at
`quantized.cpp:1378` and, unlike `bm`/`wm`/`wn`, is **never re-checked by the
accept gate** at `quantized.cpp:1404-1407`. Its constraints are `BK >= 56` and
`BK % 32 == 0`. Nobody in the campaign appears to have touched it.
