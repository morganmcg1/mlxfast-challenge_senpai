# r99-D — Re-anchor the instrument on the rebased frontier

PR #541, revision `r99-d-rev1`, student maple-tanjiro.
Base `c6c66344d9848d95158edc31f31943aabe4de079` (advisor branch head).
Host: Apple M4 Pro, 48 GiB, macOS 26.5.2. **M4 — not admissible for `_nax`
prefill ranking claims; decode census only.**

---

## 0. Branch re-anchor

The previous assignment (`maple-r98-c-prefill-loader-pipeline`, double-buffer
the routed gather-GEMM weight stage) is superseded. Its submitted-surface edits
were dropped; the research record is preserved in
`research/maple-tanjiro-r98-prefill-loader-pipeline.md` and
`research/r97-logs/`.

```
git reset --hard c6c66344d9848d95158edc31f31943aabe4de079
git diff c6c66344 HEAD -- Sources/ Vendor/ benchmark.json   # empty
senpai/check-editable-budget.sh c6c66344d9848d95158edc31f31943aabe4de079
  -> editable budget OK: current=2983849/3000000 headroom=16151
     growth=0/262144 files=142 (base=142)
```

---

## 1. Correction on the record: the `_nax` surface did NOT move

The HOLD notice stated that the frontier sync "rewrote ... **`fp_quantized_nax.h`/`.cpp`
(±585/584), `steel/gemm/nax.h` (+147), `gemm_nax.cpp` (+147), `quantized.cpp`
(±92)**", and concluded that every line anchor in the r98-C brief was stale.

That is true of commit `7181803` **relative to its own parent**, and false of
the base move that actually affects this branch. Blob identity for
`fp_quantized_nax.h`:

| rev | blob |
|---|---|
| `e510bb3d` (old base) | `8b1738272ae4` |
| `7181803^` (sync branch parent) | `0fdf46fea5ae` |
| `7181803` (sync commit) | `8b1738272ae4` |
| `c3a85ac`, `4f3108c`, `c6c66344` | `8b1738272ae4` |

The frontier-sync branch was cut from an older point, so its diff restored these
files *from* an older state *to* the organizer's version — which our advisor
branch already carried verbatim at `e510bb3d`.

Verified for all four files by blob hash: `fp_quantized_nax.h`,
`mlx-generated/fp_quantized_nax.cpp`, `quantized.cpp`,
`kernels/steel/gemm/nax.h` are **IDENTICAL** at `e510bb3d` and `c6c66344`.

Net submitted-surface diff `e510bb3d -> c6c66344` (13 files, +4697/-2875):

```
Sources/MLXFastModel/LagunaConfig.swift                 7 +-
Sources/MLXFastModel/LagunaRuntimeLayers.swift       2597 ----   (deleted)
Sources/MLXFastModel/LagunaRuntimeModel.swift        2928 ++++
Sources/MLXFastTransform/AffineMetadataCoding.swift   438 +++    (new)
Sources/MLXFastTransform/TiedHeadMetadataCoding.swift  401 +++   (new)
Sources/MLXFastTransform/Transform.swift               64 +-
Vendor/.../MLXLMCommon/BaseConfiguration.swift         37 +-
Vendor/.../MLXLMCommon/BatchKVCache.swift             109 +-
Vendor/.../MLXLMCommon/CompilableKVCache.swift         57 +-
Vendor/.../MLXLMCommon/CompilableRotatingKVCache.swift 61 +-
Vendor/.../MLXLMCommon/CompiledDecode.swift            85 +-
Vendor/.../MLXLMCommon/Evaluate.swift                 534 +-
Vendor/.../MLXLMCommon/KVCache.swift                  254 +-
```

**Zero bytes of `Vendor/mlx-swift` MLX kernel or dispatch source changed.** The
base move is entirely a Laguna-runtime + `MLXLMCommon` cache/decode-stack move.

Consequences:

1. Rule 68's `_nax` geometry premise **survives** the frontier move; it was
   derived on kernel sources that are byte-identical to the ones now shipping.
2. The r98-C line anchors into `fp_quantized_nax.h` are **not stale**.
3. The `[Wk;Wv]`-only SLC/read-overlap discriminator does **not** need
   re-derivation on new geometry.
4. Prefill-side audit numbers (loader 50 LSU vs ~40 compute, loader ≈68 % of LSU
   traffic, routed gather-QMM ≈54 % of prefill) rest on unchanged kernel source
   and unchanged host tiling; they are only as stale as the Laguna-side dispatch
   pattern that feeds them.
5. Anything **decode-side** is genuinely suspect, because that is exactly where
   all 4697 changed lines live. Part 1 is therefore aimed at the right axis.

---

## 2. Verified: the sliding-attention ring lost half its load pipeline

Advisor's audit confirmed independently.

| | old `e510bb3d` | new `c6c66344` |
|---|---|---|
| block anchor | `LagunaRuntimeModel.swift:1508-2027` | `:1416-1864` |
| main loop | `for (; i + 3 * BN < N; i += 4 * BN)` | `for (; i + BN < N; i += 2 * BN)` |
| K/V staging registers | `U pipe_kc[4]; U pipe_kd[4];` | `pair_planes = 2` |
| KV blocks in flight | **4** | **2** |

Kernel name literal `laguna_sliding_fused_attn_ring_v1` is unchanged
(`:1417`), so the census label is directly comparable across bases.

Under the round-98 thesis (decode/attn load streams are latency-bound and want
bytes in flight), halving the in-flight KV depth should make this kernel
**slower**, not faster.

---

## 3. Preregistration (committed before any result was read)

### 3.1 Instrument

Local-only GPUPROF dispatch-timing hook
(`research/nezuko-pr158-gpuprof-hook.patch`, `device.{cpp,h}`), built to
`.build-worker`, driven by `research/decode_probe.py`. Identical instrument and
identical driver to the old-base census (PR #488) that produced the reference
column, so the comparison is instrument-controlled.

```
swift build -c release --force-resolved-versions \
    --scratch-path .build-worker --product mlxfast-runtime-worker
env DARKBLOOM_GPU_PROFILE=1 DARKBLOOM_GPU_PROFILE_SPLIT=1 \
    python3 research/decode_probe.py --steps 80 --profile --profile-top 250
```

The hook is committed as an explicitly labelled TEMP INSTRUMENT commit only
because `run_job` refuses a dirty worktree; it is reverted before Part 3, and
the final head carries an empty submitted-surface diff against the base.

**Rule 43 applies:** `SPLIT=1` serialises command buffers, so per-kernel
attribution from a `SPLIT=1` census is valid but its **total** is inflated
(old base: 8528.3 µs/step `SPLIT=1` vs 7993.1 µs/step busy pool). Part 2's
wall−busy gap therefore comes from a **`SPLIT=0`** run, never from `SPLIT=1`.

### 3.2 Noise floor

Three `SPLIT=1` censuses in one session before any interpretation. Per-kernel
pooled σ from the old rig is 3.51 µs/step (this rig 3.34). The measured spread
of the three runs is the floor actually used; no threshold is fixed before that
spread is in hand (standing rule from fern's PR #543).

### 3.3 The prediction under test

Advisor's preregistered prediction: the sliding fused-attention pool must have
**changed** from its old-base value of **636.0 µs/step** (21.20 µs × 30 layers,
`SPLIT=1`, M4).

Declared decision rule, fixed now:

| outcome | reading |
|---|---|
| pool > 636.0 by more than 3σ | ring-depth regression is real and costly; quantify headroom for Frieren's #539 restoration |
| pool < 636.0 by more than 3σ | the 2-deep rewrite is *faster*; #539 is chasing negative headroom |
| \|pool − 636.0\| ≤ 3σ | one of: (a) advisor's audit wrong, (b) the 4-deep ring never mattered, (c) the instrument is not resolving this kernel — **and the assignment's stopping rule fires: report and do not spend the receipt** |

Discriminating (c) from (a)/(b) if the null occurs: the census reports
dispatch counts per label. If `laguna_sliding_fused_attn_ring_v1` appears with
30 calls/step and a plausible µs/call, the instrument *is* resolving it and (c)
is excluded — leaving (a) or (b), which the verified source diff in §2 already
makes hard to sustain for (a).

I am not tuning the instrument to agree with the audit. The §2 source diff was
established by blob/AST inspection *before* the first census and is reported
separately from the timing.

### 3.4 Part 2 observable

`wall − Σ(kernel busy)` per steady decode step, `SPLIT=0`, M4. Old-base
reference **249 µs/step**. Reported as a decomposition (wall, busy sum, gap,
gap %), never wall alone.

---

## 4. Results

_(filled in below as runs complete)_

---

## Reply

_(to advisor, at end)_
