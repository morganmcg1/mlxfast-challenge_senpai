# Decode QKV-GEMV threadgroup-packing curve

PR #308 · branch `maple-tanjiro/threadgroup-packing-curve` ·
base `63ab67c888e1892086b7b5b623de4dd0ebe68c90`

Host: Apple **M4 Pro**, 14 CPU, 48 GiB (low-memory startup profile),
macOS 26.5.2, Apple GPU generation **16** (no `_nax` kernels).
Every number below is an **M4 Pro** number. Nothing here is a ranked-M5 claim.

---

## 0. Two corrections to the assignment before any measurement

These matter because they change what the experiment *is*.

### 0.1 The knob does not exist in `Sources/`. Stage 0/1 is not a zero-source-edit sweep.

The assignment says to sweep `DARKBLOOM_DECODE_NVFP4_QKV_R1_SIMDGROUPS`, and
describes it as an existing control. It is not:

```
$ grep -rn "SIMDGROUPS" Sources/
(no output)
```

The identifier appears at the assignment base only inside an **unapplied**
research patch, `research/nezuko_pr48_deconfound.patch` (369 lines, 16,815 B),
which PR #298 used and never landed. So the −35.4 µs/step PR #298 result was
measured through a patched worker, and reproducing or extending it *requires*
applying a patch and rebuilding. Any plan that treats this sweep as
"flip an env var against the shipped binary" is wrong.

I did not reuse nezuko's patch. It bundles the packing knob together with the
folded-norm prologue (`DARKBLOOM_DECODE_NVFP4_NORM_QKV_FUSE`), which is exactly
the confound PR #298 spent eight runs per arm untangling, and the fold is also
the thing that would make threadgroup memory scale with `S`. Instead I wrote a
78-line single-axis knob, `research/tanjiro_packing_geometry.patch`, that
changes nothing but the packing geometry.

### 0.2 `S=1` is a real arm here; under nezuko's patch it was a silent no-op.

nezuko's validator accepts only `[2, 4, 8, 16]`, so `S=1` silently falls back to
`2`. The assignment lists `1/2/4/8/16` as the sweep. My knob accepts
`[1, 2, 4, 8, 16, 32]`, and Stage 0 below proves that `S=1` and `S=32` both
reach the kernel with the encoded geometry they claim. Had I inherited
nezuko's patch, the `S=1` arm would have produced a perfect statistical tie
with the default for the uninteresting reason that it *was* the default.

### 0.3 Minor: the fold flag's real name

The assignment writes `DARKBLOOM_DECODE_NVFP4_QKV_R1_NORM_QKV_FUSE`. The actual
variable in nezuko's patch is `DARKBLOOM_DECODE_NVFP4_NORM_QKV_FUSE`. My driver
pins the correct name to `0`.

---

## 1. Stage 0 — reachability, guard chain, and encoded geometry

### 1.1 Guard chain down to a default value

All line numbers are at the assignment base,
`Sources/MLXFastModel/LagunaRuntimeModel.swift`.

1. **Decode call site, `:5735-5790`.** The step first tries `fusedQKV`, which
   requires `lagunaFusedNormAffineQKVEnabled` (`:5295`) *and*
   `fusedAffine.mode == .affine, bits == 8, groupSize == 32`. The runtime
   quantizes QKV as `.nvfp4 / 16 / 4` at `:2914` because
   `lagunaNativeAffineNVFP4From` (`:2861-2867`) **defaults to `0`**. So
   `fusedQKV` is unconditionally `nil` on the default configuration and control
   falls through to `lagunaDecodeNVFP4QKVR1(normalized:bank:heads:)` at `:5766`.

2. **`lagunaDecodeNVFP4QKVR1`, `:4815`.** Requires
   `lagunaDecodeNVFP4QKVR1Enabled` (`:4620`), which is
   `environment[...] != "0"` — i.e. **default `true`**. Then shape guards; note
   `normalized.dims == (1, 1, hidden)` at `:4823`, which is why prefill is
   structurally excluded from this kernel (rule-17 note, §4).

3. **Lane-major branch, `:4834`.** Requires `bank.laneMajorScales` non-nil and
   `lane.pairwise == lagunaAttnScalePairwiseQKVEnabled`
   (`Sources/MLXFastModel/LagunaRuntimeWeights.swift:686`). The bank is
   populated at `:5571` under
   `lagunaAttnScaleNarrowQKVEnabled && mode == .nvfp4 && bits == 4 && groupSize == 16`,
   all of which hold by default. **This is the branch that runs.**

4. Fallbacks that must *not* fire: narrow branch `:4852`, plain R1 `:4867`,
   generic `quantizedMM` last. The Stage 0 probe emits a `PACKPROBE FALLBACK`
   line from each of these, so a silent fallback cannot be mistaken for a
   timing null.

### 1.2 Why the repack is bit-exact by construction

Inside `lagunaDecodeNVFP4QKVLaneMajorSource` the only statement that reads
`num_simdgroups` is

```metal
uint out_row = tile * num_simdgroups + simd_gid;
```

Every statement below it is simdgroup-local (`simd_lid`-indexed loads, a
register K-loop, one `simd_sum`, one `projected[out_row]` store). With `grid.x =
rows * 32` and `threadGroup.x = S * 32`, the set of `(out_row)` values covered
is exactly `[0, rows)` for any `S` that divides `rows`, each visited by exactly
one simdgroup, with one row per simdgroup in every arm. Total simdgroups,
arithmetic, and bytes read are therefore invariant; only the packing changes.

The shipped dispatch is `grid: ((rows/2)*64, 1, 1)`, `threadGroup: (64, 1, 1)`.
My parameterized dispatch at `S=2` is `grid: (rows*32, 1, 1)`,
`threadGroup: (2*32, 1, 1)` — **bit-identical**, so the `S=2` arm is the
unpatched stock path and is a legitimate reference.

### 1.3 Divisibility — and why the curve can be pushed to S=32

`LagunaConfig.swift`: `hiddenSize=2048`, `numKeyValueHeads=8`, `headDim=128`,
`fullAttentionHeads=48`, `slidingAttentionHeads=64`. Fused QKV row counts:

| layer type | heads | rows | factorization |
|---|---|---|---|
| full attention | 48 | `(48+16)*128 = 8192` | `2^13` |
| sliding window | 64 | `(64+16)*128 = 10240` | `2^11 · 5` |

`8192` caps the usable powers of two, so the sweep is
`S ∈ {1, 2, 4, 8, 16, 32}`. `S=32` is `1024` threads/threadgroup, the Metal
maximum. **Because the fold is pinned off, the prologue is empty and no
threadgroup memory scales with `S`** — the >32 KB pipeline-build failure the
assignment warns about cannot occur in this sweep, which is what lets me
extend the curve two points past PR #298's `S=16` and answer "does it keep
improving?".

### 1.4 Encoded geometry actually observed

`research/tanjiro_packing_probe.patch` (unapplied at the PR tip) adds a
`PACKPROBE` line per distinct `(heads, S)` tuple, printed from the dispatch site
*after* the guard chain, plus `PACKPROBE FALLBACK` from all three fallbacks.
Raw logs: `research/packing-curve-logs/stage0/`.

<!-- STAGE0_TABLE -->

Invariants held in every arm: `grid_threads` = 262144 (full) / 327680 (sliding),
`total_sg` = 8192 / 10240, `rows_per_sg` = 1. **No `PACKPROBE FALLBACK` line was
emitted by any arm**, so all six arms are genuine timing arms.

---

## 2. Stage 1 — the packing curve

<!-- STAGE1 -->

---

## 3. Fault injection — is the tripwire load-bearing?

<!-- FAULT -->

---

## 4. Rule 17 — the prefill axis

<!-- PREFILL -->

---

## 5. M4 → M5 transfer

<!-- TRANSFER -->

---

## 6. Stage 2 — generalizing the repack

<!-- STAGE2 -->

---

## 7. Verdicts

<!-- VERDICTS -->
