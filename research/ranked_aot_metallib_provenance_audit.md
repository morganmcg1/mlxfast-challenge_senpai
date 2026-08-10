# Ranked AOT metallib provenance audit

## Verdict

**AOT provenance NO-GO.** Static review found no participant-reachable provenance
failure that admits one editable, scored correction. The official path has a
source-only sidecar gap—the record does not hash `mlx.metallib`—but the trusted
workflow owns the cache and build, and then pins the exact worker and metallib
bytes before every scored phase. Fixing the residual trust gap belongs to the
organizer/trusted-harness owner, not the submitted surface. No source correction
or timing run is justified.

Scope: current branch and direct `HEAD` ancestry only. This was a static audit;
no metallib build, model execution, benchmark, cache mutation, environment
mutation, or official submission was performed. W&B: N/A.

## 1. Scored AOT census

The frozen window is one 512-token prefill, one 512-token decode seed, and 128
single-token decode steps. Current Laguna invariants are 40 layers, hidden 2048,
48/64 query heads, 8 KV heads, head dimension 128, and vocabulary 100352
(`Sources/MLXFastModel/LagunaConfig.swift:5-29`). Ranked defaults fuse nearly all
per-layer decode attention work into JIT kernels, so the AOT census is much
smaller than a naive 40-layer count.

| AOT symbol | Scored use | prefill / seed / 128 decode |
|---|---|---:|
| `rmsbfloat16` | 40 multi-token input norms; terminal-layer Q/K norms; final last-row norm | 43 / 43 / 128 |
| `rope_single_bfloat16` | terminal last-query RoPE | 1 / 1 / 0 |
| `rope_bfloat16` | terminal 512-row key RoPE | 1 / 1 / 0 |
| `sdpa_vector_bfloat16_t_128_128` | terminal prefill/seed SDPA; first decode step in each of 10 full-attention layers | 1 / 1 / 10 |
| `argmax_bfloat16` | greedy reduction over the final 100352-logit row | 1 / 1 / 128 |
| **Total dispatches** | five names, four families | **47 / 47 / 266 = 360** |

Evidence: ordinary Q/K norm, RoPE, and SDPA fallbacks are
`LagunaRuntimeModel.swift:6104-6138`; the specialized terminal attention path is
`:6382-6400`; final last-row RMSNorm is `:11630-11636`. Full decode attention is
fused from step two while the first growth concat stays stock (`:6033-6058`).
Host registries construct RMS names in
`Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/normalization.cpp:52-65`,
RoPE names in `.../metal/rope.cpp:94-120`, SDPA vector names in
`.../metal/scaled_dot_product_attention.cpp:329-382,684-752`, and arg-reduce
names in `.../metal/primitives.cpp:87-124`. Exports are in
`kernels/rms_norm.metal:445-454`, `rope.metal:227-244`,
`scaled_dot_product_attention.metal:17-30,67-79`, and
`arg_reduce.metal:220-238`.

Two load-time `rope_float32` atlas calls are outside all scored phases
(`LagunaRuntimeModel.swift:11347-11384,11694-11699`). The runtime JIT
`mlx-generated/*.cpp` families are not AOT merely because the provenance hash
also covers them.

## 2. Canonical build closure

`kernels/CMakeLists.txt:1-55` compiles the always-AOT units with `xcrun metal`,
`-fno-fast-math`, project includes, base headers, and declared per-unit
dependencies. The four scored source units are:

- `arg_reduce.metal` plus `utils.h` and shared base headers;
- `rms_norm.metal` plus `utils.h` and shared base headers;
- `rope.metal` plus `utils.h` and shared base headers;
- `scaled_dot_product_attention.metal` plus `sdpa_vector.h`, `utils.h`, and
  shared base headers.

System Metal headers and the pinned compiler/SDK are also inputs. The builder
selects the vendored `Source/Cmlx/mlx` CMake tree, rejects/regenerates foreign or
stale CMake caches, uses fixed CMake options, builds only `mlx-metallib`, and
requires exactly one result (`tools/build-mlx-metallib.sh:572-695`). This is the
canonical ranked build path, not a bare Swift build.

The source fingerprint deliberately over-approximates this closure by hashing
every regular file under both `Source/Cmlx/mlx` and `mlx-generated`
(`tools/build-mlx-metallib.sh:33-68`). Therefore an undeclared project-local
header or CMake-input edit still invalidates the ranked cache; unrelated files
may force harmless extra rebuilds.

## 3. Shell/Swift fingerprint parity

For every nonempty valid checkout the implementations are bit-for-bit aligned:

1. enumerate regular files under `mlx` and `mlx-generated` (symlinks excluded);
2. sort relative paths by raw UTF-8 bytes / `LC_ALL=C`;
3. emit `sha256  relative/path\n` for each file;
4. SHA-256 the complete listing; and
5. record prefix `mlxfast-metallib-fingerprint-v1`.

Shell: `tools/build-mlx-metallib.sh:43-67`. Swift:
`VendoredMetalFingerprint.swift:19-67`. Parity tests cover both trees, edits,
and symlink exclusion (`Tests/MLXFastTests/SetupScriptTests.swift:2325-2395`).
One formal edge differs: shell rejects zero total files while Swift hashes an
empty listing. Both source directories being present but empty is a broken,
non-ranked checkout, so this is not a viable scored correction.

The sidecar binds source paths and bytes only. It does **not** bind metallib
bytes, toolchain, SDK, architecture, build flags outside the hashed tree,
permissions, ownership, or mtimes.

## 4. Official artifact and trust chain

1. The workflow's base cache fingerprint includes architecture/CPU, OS and
   Xcode, pinned Metal toolchain identifier, SDK build, `metal -v`, CMake
   version, `Package.swift`, `Package.resolved`, and the build-script hash.
   The final cache key adds the vendored-source fingerprint
   (`.github/workflows/benchmark.yml:550-622`).
2. A restored pair must contain a nonempty artifact and sidecar whose line
   exactly matches current source; otherwise both are discarded (`:624-645`).
3. The participant worker is built in a controlled environment. It receives a
   trusted cached pair or invokes the canonical builder, and must end with both
   files present (`:963-990`). Submission runs cannot publish this cache;
   staging/saving is restricted to trusted main workflow dispatch (`:1000-1021`).
4. The trusted CLI recomputes source and fails closed in official mode on
   missing or mismatched records before worker spawn
   (`Sources/MLXFastCLI/main.swift:1322-1360`;
   `VendoredMetalFingerprint.swift:110-149`).
5. The private harness pin hashes the exact participant worker and its colocated
   `mlx.metallib`; phase checks reject later byte changes
   (`.github/scripts/pin-trusted-harness.sh:53-86`; workflow checks at
   `benchmark.yml:1130-1131,1460-1461,1773-1774`).
6. The MLX loader prefers an internal API override, then the worker-sibling
   `mlx.metallib`, before resource/default fallbacks
   (`Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/device.cpp:164-217`).
   No tracked scored caller sets that API override. The official bridge does not
   pass `MLXFAST_MLX_METALLIB`, so preflight and execution select the same
   colocated artifact.

The builder atomically publishes the artifact and then the sidecar separately
(`tools/build-mlx-metallib.sh:697-742`), not as one atomic pair. Interruption
normally leaves a missing/stale record and fails closed. A same-source old
record cannot distinguish artifact generations, but the official workflow
waits for build completion and then pins the artifact bytes before scoring.

Residual boundary: a malicious trusted-cache artifact paired with a valid
source-only sidecar could pass restore and then be blessed by the later pin.
That is an organizer/cache compromise, not a participant-controlled path. A
cryptographic source-to-binary attestation is therefore absent, while ranked
participant isolation remains intact.

## 5. In-memory counterfactual controls

These controls were reasoned over hashes and branches only; no files were
mutated.

| Control | Expected trusted response | Result |
|---|---|---|
| Edit an AOT source/header byte | source hash and cache key change; stale pair rejected | detects |
| Edit an undeclared file/CMake input under `mlx` | broad source hash changes | detects conservatively |
| Change compiler/SDK/toolchain only | sidecar unchanged; official base cache namespace changes | official detects |
| Swap metallib bytes, preserve valid sidecar, before pin | sidecar/cache restore cannot detect; later pin blesses selected bytes | trusted-cache residual |
| Swap metallib bytes after pin | phase pin verification fails | detects |
| Remove or corrupt sidecar | restore rejects; official CLI fails closed | detects |
| Mutate source during build and leave mutation | captured record/current source mismatch | detects |
| Interrupt artifact-before-sidecar publication | missing/old record usually rejects; official build is joined before pin | fail closed operationally |
| Set local `MLXFAST_MLX_METALLIB` | local CLI may verify override, but loader still prefers sibling absent internal API call | local-only mismatch, not ranked |
| Change only mtime/owner/mode, preserving bytes | all content identities remain stable | correct negative control |

## 6. History, ownership, and correction gate

Direct ancestry shows the trust layers evolved deliberately:

- `e23fe1` introduced the M5 metallib cache.
- `c77760a` added source fingerprinting, sidecars, cache-key binding, restore
  validation, and the trusted Swift verifier.
- `4367dee` regenerated relocated/stale CMake caches; `9dca557` hardened
  foreign-owned restored trees.
- `bd1b9f9` added local mtime rebuilds; `ae9831f` exempted explicit local
  metallib overrides.
- `b92c03e`/`c1c3648` evolved exact participant worker pinning around track
  migrations.

The dominant owner is organizer/trusted harness (`anupsv` in reachable history),
not submitted kernel code. `benchmark.json` permits the four AOT kernel files
and `sdpa_vector.h`, but not the builder, workflow, verifier, pin script, loader,
or registry code.

**Single correction returned: none.** The only meaningful hardening would be an
organizer change: atomically publish a manifest/pair that binds source record,
build-recipe/toolchain identity, and metallib SHA-256 before cache admission,
then pin that manifest and artifact together. It fails the assignment's strict
correction gate because it is trusted/non-editable, addresses an operator-cache
compromise rather than a participant-reachable scored defect, and has no
credible timing benefit. The ranked AOT research direction is therefore a
provenance **NO-GO**, with future ownership assigned to the organizer security
layer rather than another solver experiment.

_This audit was prepared by an OpenHands AI agent on behalf of the assigned
research student._
