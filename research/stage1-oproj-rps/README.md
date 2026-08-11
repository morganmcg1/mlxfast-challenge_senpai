# Stage 1 staged code — o_proj rows-per-simdgroup ladder

Pre-registration: `research/nezuko-r117-oproj-geometry-preregistration.md`
(design, hypotheses, decision rule, and the §8 amendment that demotes the
occupancy-starvation story in favour of **H0-inflight**).

This directory freezes the **exact code** of the Stage 1 arm on the record
*before* the ladder is measured, so the mechanism cannot be quietly reshaped
after seeing the numbers. Both files are stored with a `.staged` suffix so
SwiftPM cannot pick the Swift file up from outside a target directory.

| file | applied as |
| --- | --- |
| `LagunaOProjGeometry.swift.staged` | `Sources/MLXFastModel/LagunaOProjGeometry.swift` |
| `apply_rps_patch.py.staged` | run once against `Sources/MLXFastModel/LagunaRuntimeModel.swift` |

Apply with:

```sh
python3 research/stage1-oproj-rps/apply_rps_patch.py.staged .
cp research/stage1-oproj-rps/LagunaOProjGeometry.swift.staged \
   Sources/MLXFastModel/LagunaOProjGeometry.swift
swift build --force-resolved-versions && git checkout -- Package.resolved
```

The patch script locates its scopes by **declaration**, not by frozen line
numbers, asserts exactly one anchor hit per scope, and refuses to write if any
anchor misses. A dry run against a shadow tree produced exactly the intended
nine edits.

## Scope verification (2026-08-11 03:55Z, read-only, against `fa8e75f9`)

`results_per_simdgroup = 4` appears at **four** sites in
`Sources/MLXFastModel/LagunaRuntimeModel.swift`. Only one is in scope:

| line | enclosing declaration | in scope? |
| --: | --- | --- |
| 3991 | `lagunaGatedAffineOProjSource` (:3956) | no — affine-INT o_proj, a different kernel family with its own dicts |
| **4356** | **`lagunaGatedAffineOProjNVFP4Source` (:4222)** | **yes — the only NVFP4 o_proj source** |
| 5111 | `lagunaNormAffineQKVBody` (:5097) | no — affine QKV |
| 5292 | `lagunaNormAffineQKVPrefetchSource` (:5238) | no — affine QKV prefetch |

Two consequences worth recording:

1. **The decode NVFP4 QKV kernel is not one of these.** The atlas name
   `decode_nvfp4_qkv_h64_r1_v1_lm1_pw1_se1_sd1` carries `r1` — one row per
   simdgroup — matching the archive §4.10b census (5120 threadgroups, 2
   simdgroups, 1 row, 32 B/thread). The `rps = 4` sites at 5111/5292 belong to
   the *affine* QKV path, so the NVFP4 QKV geometry is untouched by this arm.
   The ladder therefore moves exactly one atlas kernel family and leaves the
   1342.1 µs/step QKV kernel as an internal control inside every run.
2. The affine-INT o_proj at 3991 shares the *literal text* of the grid
   expression with the NVFP4 dispatch (`grid: ((outVec / 8) * 64, 1, 1)`),
   which is why the patch must be scoped by declaration. A naive
   text substitution would have silently rewritten the affine path too.

Confirmed in the same read: the NVFP4 source hardcodes `num_simdgroups = 2`
and the dispatch uses `threadGroup: (64, 1, 1)` — 64 threads = 2 simdgroups of
32 lanes. So `rowsPerTile = num_simdgroups * results_per_simdgroup =
2 * rps`, which is what `lagunaOProjTiles(outVec:)` computes, and the shipped
`outVec / 8` is the rps = 4 special case of it. `outVec` is 2048 (h64) and
1536 (h48); both are divisible by `2 * rps` for every rung in
{1, 2, 4, 8, 16}, so the `guard` never fires in this ladder and no arm can
silently fall back to a different geometry.

## Ladder

| arm | `DARKBLOOM_OPROJ_ROWS_PER_SIMDGROUP` | rows/tile | threadgroups (outVec 2048) | threads | fn-name suffix |
| --- | --: | --: | --: | --: | --- |
| `C` | *(unset — shipped)* | 8 | 256 | 16,384 | *(none)* |
| `R1` | 1 | 2 | 1024 | 65,536 | `_rps1` |
| `R2` | 2 | 4 | 512 | 32,768 | `_rps2` |
| `R8` | 8 | 16 | 128 | 8,192 | `_rps8` |
| `R16` | 16 | 32 | 64 | 4,096 | `_rps16` |

Distinct name suffixes are mandatory, not cosmetic: MLX caches compiled
pipelines by function name (Rule 33), so a sweep whose arms share one name
measures whichever geometry was built first, five times.

## Decision rule (restated, unchanged)

Promote only if the paired CI95 upper bound on Δ(decode µs/step) is
**below −68.7 µs/step** (the Rule 105.12 slot floor, which is stricter here
than the +0.406 % crown bar). Report as positive-but-sub-floor if the upper
bound is below 0 but above −68.7. Write `N-OPROJ-GEOMETRY-FLAT` if the
interval covers zero. **Any arm whose `golden` hash moves off the baseline
value is void**, not "interesting".
