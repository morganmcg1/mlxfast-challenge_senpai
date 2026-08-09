# R85-B: surface reconstruction, twin audit, surface inventory

Research-only notes for PR #456. Everything referenced here lives outside
`benchmark.json` `editablePaths` and adds zero submitted bytes.

## 1. `research/reconstruct-surface.sh`

Reproduces the ranked CI sequence locally: take a *defined editable surface*,
overlay it onto trusted organizer `main`, and drive the result through the exact
CI build and the public 64-step behaviour gate. This answers "would the static
review and CI accept this candidate?" without spending a submission receipt.

Steps performed on the reconstructed tree:

1. `swift build -c release --force-resolved-versions --product mlxfast-swift`
2. same, `--scratch-path .build-worker --product mlxfast-runtime-worker`
3. `tools/build-mlx-metallib.sh`
4. `transform --reference "$MLXFAST_REFERENCE_DIR" --output weights`
5. `correctness --weights weights --golden <public 64-step golden>`

Only the 97 `editablePaths` entries are copied from the candidate, and
deletions are honoured, so anything the candidate changed outside the surface is
silently reverted — exactly as the real submission does.

Flags: `--trusted-remote`, `--trusted-ref`, `--candidate-root`, `--out`,
`--weights`, `--golden`, `--golden-sha256`, `--report-only`, `--skip-build`,
`--skip-gate`, `--no-fetch`. Default output tree is `<repo>/../mlxfast-recon`,
and `.build` / `.build-worker` are preserved between runs so a re-run is
incremental.

### Driving it for a content-level bisect (PR #460)

`--candidate-root` means the branch under test never has to be checked out in
the main worktree:

```bash
git worktree add ../probe-97a5090c 97a5090c
research/reconstruct-surface.sh --candidate-root ../probe-97a5090c \
                               --out ../mlxfast-recon-97a5090c
```

Use `--report-only` for a fast surface diff with no build. That report is the
cheap part of the bisect: it names exactly which of the 97 entries differ
between two candidates, before any timing work is spent.

### Result on the R85-B base

Trusted base `c5b0a13c5cc032b485022db41bcd745792316714`. Public gate:

```
reconstruct-surface: public gate passed=true checked_steps=64 case_count=1 \
  golden_hash=b9509697c08a2cf3c2943a85f0b76e39c485c441794690fa76835b40a58d7a63 error=""
```

Surface report: 97 entries; **16 differ** from trusted main; **124 identical
(dead)**; 1 new; **2 deleted** (`Sources/MLXFastTransform/AffineMetadataCoding.swift`,
`TiedHeadMetadataCoding.swift` — intentional, from promoted `d641df7`);
12 candidate changes outside the surface were reverted; 1 candidate-only file
outside the surface; no `editablePaths` drift.

**124 of 140 submitted files are byte-identical to trusted main.** They cost
cap budget and review surface for nothing.

### Known limits

- The host is an M4 Pro (Apple GPU generation 16). `_nax` kernels compile but
  are never selected, so this harness cannot behaviour-check them.
- Hidden gates (512-token teacher-forced cases, anchors, free runs, GPQA, TTFT,
  semantic judge) are not reproduced. This is a *necessary*, not sufficient,
  check.
- Weight reuse across the reconstruction is sound: `Package.swift:37-41,72-90`
  shows `MLXFastModel` is absent from the transform target's dependency graph,
  so a runtime-only change cannot alter transform output.
- Self-reported nit: the "fork-only files dropped by the overlay" counter is
  structurally always 0 and should be fixed or removed.

## 2. Static gap class found by the surface report

`Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/kernels/steel/gemm` is
editable **as a directory**, so `steel_gemm_masked.h`, `steel_gemm_segmented.h`
and `steel_gemm_segmented_nax.h` are submittable — but their generated twins
`mlx-generated/steel_gemm_masked.cpp`, `steel_gemm_segmented.cpp` and
`steel_gemm_segmented_nax.cpp` are **not** in `editablePaths`.

On macOS those `mlx-generated/*.cpp` files *are* the runtime kernel source
(`Vendor/mlx-swift/Package.swift:25` puts `jit_kernels.cpp` in
`noMetalCmlxExcludes`; line 284 excludes `nojit_kernels.cpp`). So a change to
those three headers **cannot reach the JIT path** in a real submission, even
though it builds and appears to work locally.

`steel/attn`, `gemm` / `gemm_nax`, `quantized*`, `reduce*`,
`gather_front` / `gather_axis` and `gemv` do **not** have this gap. 30 of the 97
entries are `mlx-generated/*.cpp`.

**Do not spend an arm on those three headers until the organizers add the
twins.**

## 3. `research/twin_audit.py` — generated-twin drift

Compares every `.h`/`.metal` kernel source against its `mlx-generated/*.cpp`
embedded twin.

```
TWIN AUDIT: 0/49 twin(s) with code drift, 48 with reordering or comment-only drift
```

Zero code drift. The one case worth naming is `steel_attention_nax`, whose two
twins differ only by declaration order: `DARKBLOOM_ATTN_QHOIST 0`,
`QBLOCK_MAJOR 1` and `QBLOCK_ZIGZAG 1` are defaulted in both and both
definitions precede all uses. `jit_kernels.cpp` (~lines 1379-1427) prepends
overrides only when the environment deviates from those defaults, so the
compiled text is equivalent.

## 4. AOT metallib currency

`tools/build-mlx-metallib.sh --print-fingerprint` →
`d90f4ee8f69f8d180e54363ca4a08b09a1c68728da9ca27859b689d3301bbb6a`, which
matches `.build-worker/arm64-apple-macosx/release/mlx.metallib.fingerprint`.
All four `mlx.metallib` copies in the tree are byte-identical
(sha256 `470f2f9dc59c64c6dc053055239dbb359741280c71f41da71be825da6ccc71e5`).

`kernels/CMakeLists.txt:49-55` fixes the AOT set: `arg_reduce`, `layer_norm`,
`random`, `rms_norm`, `rope`, `scaled_dot_product_attention`. Editing any of
those requires a metallib rebuild; the JIT families do not.

## 5. `research/surface-inventory.sh` — cap accounting

Prints to stdout; takes an optional contract path (default `benchmark.json`).
On the R85-B base: 97 entries, 140 distinct files,
**2,857,088 / 3,000,000 bytes** (headroom 142,912), per-file cap 524,288,
0 files over cap, no absent entries, no symlinks.

Largest submitted files: `Sources/MLXFastModel/LagunaRuntimeModel.swift`
475,647 B (**90.7 % of the per-file cap** before the R85-B split), then
`Vendor/.../metal/matmul.cpp` 89,940 B. Directory rollups:
`Sources/MLXFastModel` 651,065 B (9 files), `steel/gemm` 187,981 B (25),
`steel/attn` 104,529 B (10).

Re-run this after any promotion; the totals go stale as soon as the base moves.

## 6. Timing method note

`research/paired-timing-r85.sh` alternates baseline and candidate arms inside
one session, materializes each arm as a committed state on a **detached HEAD**,
and hard-asserts `git status --porcelain` is empty after each switch. Rows are
session-tagged and accumulate in `../mlxfast-r85-timing/`.

The n=8 result for the R85-B split is in PR #456. The transferable lesson:
**the sign of the paired decode difference tracked the measurement session, not
the arm** (sessions 1+2 mean +29 µs, session 3 mean −71 µs with a nominal
p≈0.042 the other way). Between-session drift on this host exceeds ~100 µs/step,
so any single-session paired result below that magnitude is not evidence.
n=8 here resolves nothing smaller than ≈39 µs/step at 80 % power.
