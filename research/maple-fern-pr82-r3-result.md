# PR #82 r3 — routed QMV router dedup: ordering causality control

Student: `maple-fern`. Assignment `maple-2026-08-06f-routed-qmv-router-dedup`,
revision `r3`. Branch `maple-fern/routed-qmv-router-dedup`.

Base (advisor head under test): `ea501bc8d7f18f3702b4ee6f97aea344faf7b9ee`.
Host: **Apple M4 Pro, 48 GiB** — directional only. The ranked M5 Max is
authoritative and no ranked submission was dispatched from r3.

Pre-registration: [`research/maple-fern-pr82-r3-prereg.md`](maple-fern-pr82-r3-prereg.md),
committed as `38b0c91` **before any r3 measurement ran**.

---

## Headline

**The r2 causal story is falsified.** r2 attributed a +56.5 µs/step SPLIT=0
regression to Variant A hoisting the router top-8 ordinal kernel ahead of the
shared-expert QMV. r3 reproduced that exact emission-order flip in the BASE
build with the routed R1 QMV kernel **unmodified**, and measured
**−14.3 ± 34.5 µs/step** against a pre-registered point prediction of
**+54.5 µs/step**. Dispatch order is not the mechanism.

PR #82 carries **zero submitted bytes**. Every probe in this revision is
local-only and reverted; the final head is byte-identical to `ea501bc8` across
the entire submitted surface.

---

## Item 1 — submitted surface reverted to the frontier

`6a2b8d0` restores `Sources/MLXFastModel/LagunaRuntimeModel.swift` to
`ea501bc8`. Verification at the final head:

```
$ git diff --stat ea501bc8 -- Sources/ Vendor/
(empty)
$ senpai/check-editable-budget.sh ea501bc8
editable budget OK: current=2934331/3000000 bytes headroom=65669 growth=0/262144 files=142
```

`senpai/validate-assignment-scope.sh` requires at least one submitted path
argument, so it cannot express an empty submitted set; emptiness is instead
shown by the empty `git diff` and `growth=0`.

### Correction to the r3 assignment text

The assignment states that the merges carrying r2's base `6a19fd74` up to
`ea501bc8` do not touch the submitted surface. **They do.** #80's promotion
changed two submitted files:

| file | lines changed |
| --- | --- |
| `Sources/MLXFastModel/LagunaRuntimeModel.swift` | 124 |
| `Sources/MLXFastModel/LagunaRuntimeWeights.swift` | 83 |

This is why r3 re-measured both cells fresh on `ea501bc8` rather than appending
a replicate to the stale r2 pair (declared deviation 2 below).

---

## Declared deviations from the literal r3 instructions

### Deviation 1 (critical) — the literal item 3 instruction is a no-op

The assignment asks for a *Swift statement reorder* inside the decode MoE
block. That cannot change dispatch order: MLX is lazy there, and the sparse-MoE
body contains no `eval`/`asyncEval`. Encode order is decided later by the tape
build in `Vendor/mlx-swift/Source/Cmlx/mlx/mlx/transforms.cpp`:

| what | where |
| --- | --- |
| degree/cache accounting | `transforms.cpp` ≈110–177 |
| BFS over `inputs()` in declaration order | `transforms.cpp` ≈180–224 |
| `MLX_BFS_MAX_WIDTH = 20` | `utils.h:173-175` |
| execution pops `tape.back()` first | `transforms.cpp` ≈228–230 |

Consequence: **among independent siblings, the input declared *later* is
encoded *earlier*.** The real lever is therefore the 9-slot input list of
`lagunaRoutedSharedDownResidual`, not statement order. r3 permutes that list.

Canonical slots: `0 routed_activated, 1 routed_down_weight, 2 routed_down_scales,
3 indices, 4 router_weights, 5 shared_activated, 6 shared_down_weight,
7 shared_down_scales, 8 residual`.

### Deviation 2 — fresh cells instead of a third replicate on the stale pair

Item 2 asked for a third SPLIT=0 replicate appended to the r2 BASE/CAND pair.
Because the frontier moved and touched the submitted surface (above), r2 and r3
cells are not poolable. r3 measures fresh n=3 cells on `ea501bc8`. r2 numbers
are reported separately and **never pooled**.

### Deviation 3 — one env-gated build, interleaved A/B (item 2)

r2 compared two separately built binaries measured at different times, so
build-to-build layout and session drift were confounded with the effect. r3
gates Variant A behind `DARKBLOOM_ROUTED_QMV_INDICES` in a **single build** and
runs `ABABAB`, which cancels drift between cells. The unset arm is the shipped
path; the gate costs one `Bool` test per MoE block per step.

---

## Item 3 ★ — decisive ordering control

**Design.** Local-only probe adds `DARKBLOOM_DOWN_INPUT_ORDER`, which permutes
the `lagunaRoutedSharedDownResidual` input list. The routed R1 QMV kernel is
**unmodified** in every arm, so any timing difference is attributable to
emission order alone. Arm `Ob` = permutation `[0,1,2,5,6,7,3,4,8]`, chosen to
reproduce r2 CAND's emission order exactly.

**Mechanism precondition — satisfied.** Observed MoE emission order per arm
(`KEYS` = `residual_rms_router_..._keys_v1`, `SHARED` =
`shared_nvfp4_swiglu_qmv_rows1_bf16_v1`, `ORDINAL` =
`decode_router_top8_ordinal_table_norm_v1`, `ROUTED` = routed gate/up QMV,
`DOWN` = `routed_shared_nvfp4_down_residual_...`):

| arm | emission order | n | µs/step | half-range | Δ vs O0 |
| --- | --- | --: | --: | --: | --: |
| `O0` shipped | `KEYS·SHARED·ORDINAL·ROUTED·DOWN` | 3 | 7986.3 | 10.0 | — |
| `Ob` **control** | `KEYS·ORDINAL·SHARED·ROUTED·DOWN` | 3 | 7972.0 | 24.5 | **−14.3** |
| `Oc` screen | `KEYS·SHARED·ROUTED·ORDINAL·DOWN` | 1 | 7985.0 | — | −1.3 |
| `Osf` screen | `KEYS·ORDINAL·ROUTED·SHARED·DOWN` | 1 | 8063.0 | — | +76.7 |
| `Od` screen | `KEYS·ROUTED·SHARED·ORDINAL·DOWN` | 1 | 8053.0 | — | +66.7 |

`Ob` moves `ORDINAL` ahead of `SHARED` — the r2 CAND order — with
`dispatches=406` and `cbs=45` unchanged in all nine arms, and
`0 divergences (all match)` on teacher-forced greedy tokens in all nine.

**Verdict — pre-registered branch 2: NULL.**

```
CONTROL  Ob - O0 = -14.3 us/step (-0.179 %)  pooled half-range noise 34.50
pre-registered prediction +54.5 us/step (+0.67 %)
=> branch 2: NULL, re-attribute and stop
```

The observation sits 68.8 µs from the point prediction and on the **opposite
side of zero**. The r2 attribution — "CAND hoists router top-8 ahead of shared
QMV, costing +54.5 µs/step in the MoE groups" — does not survive its own
control.

### Bonus: the dependency structure r2 assumed is confirmed

Arm `Od` encodes `ROUTED` *before* `ORDINAL`. That is only legal because the
routed R1 QMV consumes `router_keys` from `residual_rms_router_..._keys_v1`
directly and does **not** depend on `ORDINAL`. `ORDINAL` produces the
normalized router weights consumed by `DOWN`. So the two are genuine
independent siblings, and the top-8 selection really is computed twice — the
duplication PR #82 set out to remove is real. Only its *cost attribution* was
wrong.

### Item 4 — symmetric probe (descriptive only)

Per pre-registration, item 4's confirmatory arm runs **only** on branch 1 or 3.
Branch 2 fired, so the following is **hypothesis-generating only, n=1, not a
claim**, reported because the screens were already collected in the same batch.

The five arms separate perfectly on one rule: **`SHARED` encoded after
`ROUTED` costs ~+70 µs/step; otherwise ~0.**

| `SHARED` vs `ROUTED` | arms | Δ vs O0 |
| --- | --- | --- |
| SHARED first | `O0`, `Ob`, `Oc` | 0, −14.3, −1.3 |
| ROUTED first | `Osf`, `Od` | +76.7, +66.7 |

This is corroborated by an independent prior measurement: the existing
`lagunaSharedFirstDownOrderEnabled` flag (2026-08-01, M5 Max) regressed
~+0.10 ms/step, and `Osf` is exactly that arm, at +76.7 µs/step here.

**This is a guard rail, not an opportunity.** The shipped order is already in
the fast class. The actionable content is negative: future work that reorders
the down-residual input list must not push `SHARED` behind `ROUTED`.

---

## Item 2 — Variant A replication (interleaved, n=3 per cell)

<!--ITEM2-->

---

## r2 reference numbers (reported separately, never pooled)

| axis | BASE | CAND | Δ |
| --- | --: | --: | --: |
| SPLIT=1 µs/step | 8670.5 (hr 16.5) | 8623.0 (hr 16.0) | −47.5 (−0.548 %) |
| SPLIT=0 µs/step | 8101.0 (hr 7.0) | 8157.5 (hr 24.5) | **+56.5 (+0.698 %)** |
| routed R1 kernel, SPLIT=1 | 1494.65 | 1438.20 | −45.12 (−3.15 %), δ-corrected, noise 4.10 |

r2's two axes already disagreed in sign. r3 shows the SPLIT=0 arm was the
unreliable one.

---

## Reproduction

```bash
# build (scored worker build directory)
CLANG_MODULE_CACHE_PATH="${PWD}/.build-worker/clang-module-cache" \
  swift build -c release --force-resolved-versions \
  --scratch-path .build-worker --product mlxfast-runtime-worker
git checkout -- Package.resolved

# item 3 (nine arms, one supervised process)
bash research/pr82-r3-logs/run_arms.sh
python3 research/pr82-r3-logs/order_compare.py

# item 2 (interleaved ABABAB)
bash research/pr82-r3-logs/run_variantA.sh
python3 research/pr82-r3-logs/variantA_compare.py
```

Each arm: `DARKBLOOM_GPU_PROFILE=1 DARKBLOOM_GPU_PROFILE_SPLIT=0` with
`research/decode_probe.py --steps 200 --profile --profile-top 44`.

## Probe commits and their reverts

| probe | applied | reverted |
| --- | --- | --- |
| MLX dispatch profiler (`device.cpp`/`device.h`, **not** in `editablePaths`) | `d66c36b` | <!--REVERT-PROF--> |
| `DARKBLOOM_DOWN_INPUT_ORDER` ordering probe | `068bd6c` | `b0444d0` |
| `DARKBLOOM_ROUTED_QMV_INDICES` Variant A | `4ef8abc` | <!--REVERT-VA--> |

## Suggested follow-ups (not implemented)

1. **Re-price the duplication on M5 before any further Variant A work.** The
   M4 Pro null does not transfer: M5 selects `_nax` kernels and has a different
   core count. The r2 SPLIT=1 routed-kernel win (−45.12 µs, −3.15 %) is the
   only surviving positive signal and deserves an M5 paired check.
2. **Variant A′ / Route 1** — produce the 8-entry index vector inside
   `residual_rms_router_..._keys_v1` so `ORDINAL` can be dropped entirely. Must
   be priced against the ~206 µs/step `ordinal_table` cost it would remove.
3. **Dead `router_keys` production.** If a future variant stops consuming
   `router_keys`, its producer becomes dead and should be removed with it.
4. **Hygiene, independent of this experiment:** the stale R1-selection guard
   and the stale `routerKeys` preconditions in
   `lagunaRoutedSwiGLUQMVPackedTop8`; and `mergedSharedActivated` is declared
   `var` but never mutated (build warning).
5. **Order guard rail** — if the `SHARED`-after-`ROUTED` rule is worth
   trusting, confirm it at n=3 on M5 and record it as a constraint on the
   down-residual input list.
