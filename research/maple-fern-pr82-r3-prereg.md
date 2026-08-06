# PR #82 r3 pre-registration — dispatch-order causality control

Assignment `maple-2026-08-06f-routed-qmv-router-dedup`, revision `r3`.
Written before any r3 timing run. Host: Apple M4 Pro, 48 GiB (directional
evidence only; the ranked M5 Max is authoritative).

Frontier under test: advisor head `ea501bc8d7f18f3702b4ee6f97aea344faf7b9ee`
(post-#80 promotion + research-only #91). Branch head after item 1:
`6a2b8d0`, submitted-surface diff versus the frontier is **empty**
(`senpai/check-editable-budget.sh` reports `growth=0/262144`).

## 0. What r2 left on the table

r2 measured Variant A (routed R1 QMV consumes the top-8 `indices` vector
instead of re-deriving winners from `router_keys`):

| axis | BASE | CAND | Δ |
| --- | --- | --- | --- |
| SPLIT=1 busy sum (µs/step) | 8670.5 (hr 16.5) | 8623.0 (hr 16.0) | **−47.5 (−0.548 %)** |
| SPLIT=0 busy sum (µs/step) | 8101.0 (hr 7.0) | 8157.5 (hr 24.5) | **+56.5 (+0.698 %)** |
| routed R1 kernel, SPLIT=1 | 1494.65 | 1438.20 | −45.12 δ-corrected (−3.15 %), noise 4.10 |

The kernel is genuinely faster; the arm still loses on the shipped batched
path. The named cause was that CAND changes the **order** in which MLX emits
independent dispatches inside the command buffer — dispatch count stays 406
and command-buffer count stays 45, but CAND hoists
`decode_router_top8_ordinal_table_norm_v1` ahead of
`shared_nvfp4_swiglu_qmv_rows1_bf16_v1`. MoE-containing groups paid +54.5
µs/step; the non-MoE remainder paid +1.7 µs. That is +1.40 µs per MoE block
× 39 blocks.

That was an *observation correlated with* the kernel change, not a
controlled result. r3 turns it into a control.

## 1. Declared deviation from the literal r3 instruction (RULE 18)

The r3 brief says to force the ordering flip by reordering the emission in
the BASE build. Read literally — reorder the Swift statements inside the
decode MoE block — **that is a no-op**, and running it would have produced a
null result for the wrong reason. Evidence from this checkout:

- MLX is lazy on this path. There is no `eval` / `asyncEval` anywhere inside
  the sparse-MoE decode body; the nearest barriers are the per-layer
  `asyncEval(h)` calls, and `asyncEval(qkv, gateLogits)` up in attention.
  Swift statement order therefore only builds the graph, it does not encode.
- Encode order is decided in
  `Vendor/mlx-swift/Source/Cmlx/mlx/mlx/transforms.cpp`: a degree/cache pass
  (≈110–177) then a BFS tape build that walks each node's `inputs()` in
  declaration order (≈180–224, width bound `MLX_BFS_MAX_WIDTH` = 20 in
  `utils.h:173-175`), and execution pops `tape.back()` first (≈228–230).
  Among mutually independent siblings, **the input declared later is encoded
  earlier**.
- The two kernels of interest are fully independent and first meet at
  `lagunaRoutedSharedDownResidual`
  (`Sources/MLXFastModel/LagunaRuntimeModel.swift:7967-8023`, kernel
  `laguna_routed_shared_nvfp4_down_residual_bf16_r1_v5` declared at
  `:7846-7861`). Its 9-slot input list is the real lever.

So the deviation is: **force the flip by permuting the joining kernel's
input list, with the routed R1 QMV kernel source byte-identical to BASE.**
This is a strictly stronger control than the literal instruction — it
changes emission order and nothing else about the math.

This lever already exists in the tree as `lagunaSharedFirstDownOrderEnabled`
/ `DARKBLOOM_SHARED_FIRST_DOWN=1` (`:7827-7844`, `:8007-8017`), documented
as bit-exact and measured on 2026-08-01 on M5 Max as a ~+0.10 ms/step
regression. That arm is *confounded* for our purpose because it moves the
routed group as well as the router group, so r3 adds a minimal permutation.

## 2. Second declared deviation: fresh n=3 on the frontier, not a third
replicate appended to the r2 pair

The r3 brief asks for one more BASE and one more CAND SPLIT=0 run appended
to r2's pair. The advisor's assignment states that the merges between the r2
base `6a19fd74` and the frontier `ea501bc8` do not touch the submitted
surface. **That is not correct.** Verified here:

```
git diff --stat 6a19fd74 ea501bc8 -- Sources/ Vendor/
  Sources/MLXFastModel/LagunaRuntimeModel.swift   | 124 +-
  Sources/MLXFastModel/LagunaRuntimeWeights.swift |  83 +-
```

Those are #80's promoted changes. Appending a run measured on `ea501bc8` to
a pair measured on `6a19fd74` would pool across two different scored trees.
Instead r3 runs a complete fresh **n=3 BASE vs n=3 CAND** contrast entirely
on `ea501bc8`. r2's numbers are reported separately and are **not pooled**.

## 3. Design: one binary, env-gated arms

All arms are the same release binary, so codegen, inlining and build
directory are held constant. Two probe knobs are added to
`LagunaRuntimeModel.swift` for the measurement only, then reverted in a
separate commit (precedent: `bb08f01` apply / `239cd1a` revert).

`DARKBLOOM_DOWN_INPUT_ORDER` selects a permutation of the 9 canonical inputs
of `lagunaRoutedSharedDownResidual`. Canonical slots:

```
0 routed_activated  1 routed_down_weight  2 routed_down_scales
3 indices           4 router_weights
5 shared_activated  6 shared_down_weight  7 shared_down_scales
8 residual
```

| arm | env | permutation | intent |
| --- | --- | --- | --- |
| `O0` | unset | `0 1 2 3 4 5 6 7 8` | shipped BASE order |
| `Ob` | `b` | `0 1 2 5 6 7 3 4 8` | **the control.** Only the router block and the shared block swap; routed block stays first, residual stays last. Predicted to encode router top-8 before shared QMV, i.e. CAND's order. |
| `Osf` | `sf` | `5 6 7 0 1 2 3 4 8` | existing shared-first arm, confounded (also moves the routed block) |
| `Oc` | `c` | `3 4 0 1 2 5 6 7 8` | pushes the router block *earlier in declaration* → later in encode; opposite-direction probe |
| `Od` | `d` | `8 3 4 5 6 7 0 1 2` | routed block declared last → routed QMV encoded first; symmetric probe |

Each non-shipped arm gets a distinct kernel name suffix (`…v5o<b|sf|c|d>`)
so the JIT cache cannot serve a stale compile. The permutation is
bit-exact: the kernel body addresses its inputs by name, which is exactly
the argument the shipped `…v5sf` variant already relies on. **Declared mild
confound:** permuting `inputNames` also permutes Metal buffer binding
indices. The shipped `sf` arm carries the same confound and was accepted as
a valid A/B by the tree's own documentation.

`DARKBLOOM_ROUTED_QMV_IDX=1` re-enables the r2 Variant A kernel (routed R1
QMV consumes `indices`), restored verbatim from the r2 submitted diff, so
CAND can be re-measured on the frontier from the same binary.

## 4. Pre-registered predictions

Item 3 — control `Ob` versus shipped `O0`, both with the routed R1 QMV
kernel **unmodified** (`DARKBLOOM_ROUTED_QMV_IDX` unset), SPLIT=0, n=3 each,
counterbalanced (`O0, Ob, Ob, O0, O0, Ob`):

- **Mechanism precondition:** `split0_group_compare.py` must show
  `decode_router_top8_ordinal_table_norm_v1` moving ahead of
  `shared_nvfp4_swiglu_qmv_rows1_bf16_v1` in the emitted group name-lists,
  with total dispatch count still 406 and command-buffer count still 45. If
  the order does **not** flip, the arm is void and I report the null
  mechanism rather than the timing.
- **Point prediction:** Δ(`Ob` − `O0`) = **+54.5 µs/step (+0.67 %)**, i.e.
  the MoE-group share of r2's +56.5 µs.

Pre-registered outcome branches, decided before running:

1. **Δ ≥ +40 µs/step** → causal claim established. Dispatch emission order
   is an independent, bit-exact, zero-submitted-byte lever worth ≈0.5–0.7 %
   of decode. r2's Variant A regression is fully re-attributed to ordering,
   and Variant A′ (a routed-QMV index consumer that preserves shipped
   emission order) becomes the live follow-up.
2. **|Δ| < the run-to-run noise band** (half-range of the n=3 cells, pooled)
   → the ordering hypothesis is *not* supported; r2's +56.5 µs must be
   re-attributed to something else. **Stop. Do not hunt a third explanation
   this session.** Report the null and the residual mystery.
3. **Δ ≤ −(noise)** — the control is *faster* → report it as the most
   interesting outcome; it means the shipped order is not optimal and the
   ordering lever is a live win in the opposite direction.

Item 4 — symmetric probe, run only if branch 1 or 3 fires. n=1 screen of
`Osf`, `Oc`, `Od`; then n=3 on shipped plus the single best screened arm.
Reported as "is any ordering faster than shipped", not as a submission.

Item 2 — Variant A on the frontier: `DARKBLOOM_ROUTED_QMV_IDX=1` with the
shipped order, SPLIT=0, n=3, versus the same `O0` n=3 cell. Predicted to
reproduce r2's sign (+40 to +70 µs/step).

## 5. Measurement recipe (identical to r2)

Build:

```bash
CLANG_MODULE_CACHE_PATH="${PWD}/.build-worker/clang-module-cache" \
  swift build -c release --force-resolved-versions \
  --scratch-path .build-worker --product mlxfast-runtime-worker
git checkout -- Package.resolved
```

Run (via `run_training`, one model-holding process at a time):

```bash
DARKBLOOM_GPU_PROFILE=1 DARKBLOOM_GPU_PROFILE_SPLIT=0 [arm env] \
  python3 research/decode_probe.py --steps 200 --profile --profile-top 44
```

`gpu_busy_sum` comes from `research/decode_probe.py:149-192`; step 0 is
dropped at `:166`; the reported number is the per-steady-step mean over 199
steps. Post-processing with `research/pr82-r2-logs/split0_group_compare.py`.

MLX dispatch profiler hooks (`bb08f01`, 98 insertions in
`Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/device.{cpp,h}` —
**neither path is in `editablePaths`**) are re-applied for the measurement
and reverted afterwards. Both the probe revert and the profiler revert SHAs
are recorded in the result document, and the final PR head must show a zero
submitted-surface diff against `ea501bc8`.

## 6. Not in scope for r3

No ranked submission from this revision, regardless of outcome. If item 4
finds a faster ordering it becomes its own ticket with its own base and its
own M5 evidence.
