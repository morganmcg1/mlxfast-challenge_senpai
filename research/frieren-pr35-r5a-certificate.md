# PR #35 r5-A — lane-major NVFP4 scale-bank bitwise certificate

Assignment `maple-2026-08-04j-scale-code-width`, revision r5, deliverable A.
Experiment base `768bb9d4adfc2baac7d74c0008afc92d010329da`.
Harness log: [`research/frieren-pr35-r5a-bitwise.log`](frieren-pr35-r5a-bitwise.log).

**Verdict: PASS.** `R5A_VERDICT: PASS (P0-P3 bit-identical on every geometry,
plane and lane; every P4 power control flagged)` — 1782 pairs compared,
max ULP diff over P0–P3 = 0, uncovered rows = 0, mismatch failures = 0,
silent power controls = 0.

This is the instrument the advisor asked for in r5: an adversarial
plane-by-plane proof that `lagunaDecodeNVFP4QKVLaneMajorSource()` computes
bit-identical output to the shipping wide arm
`lagunaDecodeNVFP4QKVR1Source(narrow:)`, with a power control proving the
harness is actually wired to the bank it claims to test. It replaces the r4
gate whose precondition was unsatisfiable.

---

## 1. What the instrument is

The runtime's two QKV decode kernels are MLX `custom_kernel` sources: the text
is generated in Swift, then compiled by MLX at runtime. r5-A tests **the exact
compiled kernel text**, not a re-implementation:

1. `research/frieren-pr35-r5a-dump.patch` instruments the runtime to (a) dump
   the real `plane_/nibbles_/bases_r{rows}_g{groups}_L{NN}.bin` for `site ==
   "qkv"` under `DARKBLOOM_DUMP_PLANE_DIR`, and (b) re-apply both kernels with
   `verbose: true`, with fd 1 duplicated to `$DARKBLOOM_DUMP_GEN_DIR/gen_h{heads}.txt`.
   The redirect is required because the worker's **stdout is the JSON protocol
   channel** (`research/decode_probe.py:69,77`).
2. `research/frieren_pr35_r5a_dump.sh` drives one instrumented decode
   (`run_training` `8ca86fe1-57cf-4747-9c49-7ae23d5ca547`, exit 0, 46.1 s,
   `peak_ram_gb=20.79`, `mlx_peak_gb=36.43`, 0 divergences), producing 122
   artifacts in `/tmp/pr35_r5a` (72 MB, deliberately not committed).
3. `research/frieren_pr35_r5a_split_gen.py` splits the captured `verbose` text
   into `research/r5a_kernels/{lanemajor,wide}_h{48,64}.metal` — the four exact
   generated kernels.
4. `research/frieren_pr35_lanemajor_bitwise.swift` is a standalone Swift/Metal
   executable that compiles those four texts with MLX's own compile options and
   preamble, synthesizes each adversarial plane, builds the lane-major bank with
   a hand port of `lagunaLaneMajorNVFP4ScaleBank`, dispatches both kernels, and
   compares output **bit-for-bit**.

The hand-ported bank builder was validated against the runtime's own dumped
`nibbles`/`bases` **byte-for-byte for all 40 layers**, so the plane synthesis
path and the shipping path agree before any adversarial plane is introduced.

Venue: a standalone executable under `research/`, following the §0.9.21
precedent. `Tests/` is byte-free but AGENTS.md lists trusted test files under
"What Not To Change". **r5-A cost zero submitted bytes** — `research/` is not in
`editablePaths`.

## 2. Fidelity of the test bed

Reported verbatim by the harness:

```
host          : Version 26.5.2 (Build 25F84)
device        : Apple M4 Pro
compile opts  : mathMode=safe languageVersion=262144
preamble      : 47412 bytes from Vendor/mlx-swift/.../mlx-generated/utils.cpp
call-site geom: 3 occurrence(s) of `grid: ((rows / 2) * 64, 1, 1)`
call-site geom: 16 occurrence(s) of `threadGroup: (64, 1, 1)`
harness geom  : dispatchThreads(width: rows/2*64) tg(64,1,1)  [matches call site]
```

`languageVersion=262144` is `MTLLanguageVersion4_0`; `mathMode=safe` is the
modern spelling of MLX's `fastMathEnabled=false`
(`Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/device.cpp:622-638`). The
preamble is the `R"preamble(...)"` literal MLX itself prepends
(`backend/metal/custom_kernel.cpp:71`). Dispatch is `dispatch_threads`
(non-uniform threadgroups, grid expressed in threads), matching the runtime.

All four pipelines report identical occupancy-relevant properties, so no
geometry or spill difference is hiding a divergence:

```
staticThreadgroupMemoryLength=0 maxTotalThreadsPerThreadgroup=1024 threadExecutionWidth=32
```

**Correction to the assignment text, and to our own r4 note.** The advisor asked
us to confirm the harness geometry matches the call site "at
`LagunaRuntimeModel.swift:5907`". That line number is wrong, and the error is
ours: `research/frieren-pr35-r4-gate-blindness.md:84` asserted a call-site census
at `:5907`, which is where the advisor took it from. Verified now:

- `lagunaDecodeNVFP4QKVR1` is **defined** at `:4902-4962`, and its **sole call
  site** is **`:5858`** (`? lagunaDecodeNVFP4QKVR1(`), inside the
  `lagunaFusedQKVProjectionEnabled && B == 1 && L == 1` decode block. `:5907` is
  in the *gate* projection, not QKV.
- The geometry the harness must match is specified in the callee, at **`:4930`,
  `:4946` and `:4957`** — the three `grid: ((rows / 2) * 64, 1, 1)` /
  `threadGroup: (64, 1, 1)` dispatches. That is exactly the "3 occurrences /
  16 occurrences" the harness census counts above.
- Kernel bodies: `lagunaDecodeNVFP4QKVR1Source(narrow:)` at `:4711`,
  `lagunaDecodeNVFP4QKVLaneMajorSource()` at `:4823`.

The call-site census conclusion in the r4 note still holds — there is exactly
one caller, and `fusedQKV` is `nil` for the NVFP4 group-16 bank, so
`decodeNVFP4QKVR1` *is* the `qkv` path. Only the line number was wrong.

### Activation passes

Each plane is exercised over `passCount = 33` activation vectors: one **dense**
vector, plus **32 lane-isolated** vectors where only lane `l`'s four 16-element
segments (`v[b*512 + l*16 + i]`, `b < 4`) are non-zero. Because the kernel gives
lane `l` exactly the four scale reads at `g = b*32 + l`, a lane-isolated
activation exercises exactly one lane's four scale blocks and nothing else. This
is what turns a pass/fail into a **lane-resolved** result.

## 3. The planes

The advisor specified P0–P4 literally. P0, P3 and P4 were implemented as
specified. **P1 and P2 required a stated generalization**, for a reason that is
the whole point of r5:

> The advisor's literal P1 (`code[r][g] = base(r) + (g mod 16)`) and P2
> (`base(r) + ((7*g) mod 16)`) are **constant across a lane's four blocks**. The
> kernel's four scale reads for lane `l` are at `g = b*32 + l`, and
> `32 ≡ 0 (mod 16)`, so `g mod 16 = l mod 16` for every `b`. A plane that is
> constant in `b` cannot discriminate a displacement in `b` — the same
> unsatisfiable-precondition class that voided r4.

Implemented, and reported as a deviation:

| plane | definition | intent |
|---|---|---|
| `P0-real-Lnn` | the real dumped plane for each of the 40 layers | real-data smoke test |
| `P1-injective` | `base(r) + ((b + l) mod 16)` | injective in the *(lane, block)* pair actually addressed |
| `P1H-onehot` | `base(r) + (15 if l == r%32 && b == (r/32)%4 else 0)` | one-hot in `(l,b)`: a single displaced read moves one row only |
| `P2-stride` | `base(r) + ((12*l + 7*b) mod 16)` | coprime strides in both axes; catches nibble-order swaps inside the packed word that P1 could alias through |
| `P3-mixed-escape` | escaped rows `8 + ((7*g) mod 239)` on `r % 7 == 3`, mixed into the same tensor as fitting rows | the only plane covering the escaped arm's `sc[b * (block_size/16)]` stride |
| `P4a/b/c` | power controls (see §5) | prove the harness is wired to the bank |

`base(r) = 8 + (r % 190)`. All plane bytes are constrained to **[8, 247]**
because `laguna_tail_nvfp4_scale` builds a half from `bits << 7`: bits ≥ 248
give inf and bits < 8 give a denormal. Real codes top out at 41, so this range
strictly contains the shipping distribution.

## 4. Results

Every P0–P3 cell is `diffPasses=0/33 diffRows=0 maxUlp=0 bit-identical`, on both
geometries.

| geometry | rows | layers | P0 layers | P1 | P1H | P2 | P3 |
|---|---|---|---|---|---|---|---|
| h48 | 8192 | 10 | 10/10 bit-identical (esc 14–208) | ✅ esc=0 | ✅ esc=0 | ✅ esc=0 | ✅ esc=1170 |
| h64 | 10240 | 30 | 30/30 bit-identical (esc 10–187) | ✅ esc=0 | ✅ esc=0 | ✅ esc=0 | ✅ esc=1463 |

Geometry derivation (`LagunaConstants`: `hiddenSize=2048`,
`numKeyValueHeads=8`, `headDim=128`, `fullAttentionHeads=48`,
`slidingAttentionHeads=64`): rows = `(heads + 16) * 128`, so h48 → 8192 rows
(10 layers) and h64 → 10240 rows (30 layers); 389,120 rows total, of which 2,454
escape (0.6307 %).

P3 is the load-bearing cell. §3.6's shipping certificate
(`lagunaLaneMajorScaleBankReproducesScales`,
`Sources/MLXFastModel/LagunaRuntimeWeights.swift:898-920`) does **not** cover
the escaped arm's `sc[b * (block_size/16)]` stride; P3 puts 1170 / 1463 escaped
rows in the same tensor as fitting rows and finds zero bit differences.

**Honest note on h48 vs h64.** The two lane-major kernel texts are
**byte-identical apart from the generated kernel name** (`diff` differs only on
line 54); the geometry difference is purely the dispatched row count. So the two
geometry columns are a dispatch-shape replication, not two independent code
paths. They are still worth running — the row count changes tile/grid coverage —
but the table should not be read as double the code coverage it is.

## 5. Power control — the lesson of probe 132

The advisor made this non-negotiable: if a deliberate corruption of the
lane-major bank does not produce a bit difference, the harness is not wired to
the thing it claims to test and the certificate is void.

| control | perturbation | h48 | h64 |
|---|---|---|---|
| `P4a-rotate-nibbles` | every lane `ushort` rotated by one nibble | FLAGGED `33/33` passes, 267,529 rows, maxUlp 38828 | FLAGGED `33/33`, 334,492 rows, maxUlp 38713 |
| `P4b-flip-base-bit` | `bases[0]` and `bases[rows/2]` xor 1 | FLAGGED `33/33`, 65 rows, maxUlp 198 | FLAGGED `33/33`, 66 rows, maxUlp 168 |
| `P4c-single-nibble` | row 3, lane 7, block 0 nibble xor 1 | FLAGGED **`2/33`**, 2 rows, maxUlp 4 | FLAGGED **`2/33`**, 2 rows, maxUlp 3 |

`silent power controls : 0`.

`P4c` is the strongest evidence in the whole run. A single flipped nibble flags
**exactly 2 of 33 passes** — the dense pass and the `lane7` pass — and exactly
one row in each. That is not a smoke alarm; it is proof that the harness
resolves a corruption to the correct lane, block and row, so the zeros in §4 are
measured absences and not blind spots.

`P4a` diffRows counts are out of `passes × rows` (h48: 267,529 / 270,336 =
98.96 %; h64: 334,492 / 337,920 = 98.99 %), not out of rows.

## 6. P0 is *proven* non-discriminating, not merely suspected

P0 is a real-data smoke test only. **P1/P2/P3 carry the entire certificate.**
The reason is structural, and it is why r4's gate was vacuous:

`Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/kernels/fp_quantized.h:2186-2205`,
`fp_quantize`, `group_size == 16` branch: lines **`2192-2194`** predicate on
**`tidx.x` — the global grid x — not the SIMD lane id**. The dispatch is 1-D
with `per_thread = 1` and `grid_dims = (nthreads,1,1)`
(`backend/metal/quantized.cpp:2455-2478`). Therefore every simdgroup except the
first of a dispatch has all 32 lanes with `tidx.x >= 16`, `w_max_r` is reduced
over the full 32-element span, and

```
scale[2k] == scale[2k+1]   bit-exactly, for any weights
```

Real scale planes are **pairwise constant by construction**, so P0 cannot
discriminate a ±1 group-index displacement *at all*. The 89 measured exceptions
all sit at `g = 0`: q/k/v are quantized separately
(`LagunaRuntimeModel.swift:5311-5354`, concatenated at `:5354`) → 120
independent dispatches, so at most 120 rows can carry the first-span exception.
This is a property of the quantizer, not of this checkpoint: the transform never
computes scales (`Sources/MLXFastTransform/Transform.swift:69`,
`LagunaCheckpointValidation.swift:33`), attention NVFP4 is manufactured at load
time (`LagunaRuntimeModel.swift:2961-2985`, `quantized(..., groupSize: 16,
bits: 4, mode: .nvfp4)` at `:2974-2975`), the JIT twins agree
(`mlx-generated/fp_quantized.cpp:2349-2351`,
`mlx-generated/metal/fp_quantized.h:1850-1852`), and there is **no `_nax`
override of `fp_quantize`**.

**P0 alone is exactly the trap r4 fell into.** Reporting P0 green without
P1/P2/P3 would have reproduced the r4 error with more decimal places.

## 7. Harness defect found and fixed (disclosed)

The first harness run (`run_training` `fc5f65d4-daa1-4089-a460-3328c521147a`)
**FAILED**, and the failure was in the harness, not the kernel.

The original coverage check pre-filled the output buffer with `0xCD` and treated
a surviving `0xCDCD` as "row never written". Under P3, escaped scales are large
enough that a legitimate output can have the bf16 bit pattern `0xCDCD`
(≈ −4.35e8). The check false-positived on correct results.

Fix: a **two-fill coverage + determinism check**. Each kernel is dispatched
twice over two *different* pre-fills (`0xCD` and `0x37`,
`frieren_pr35_lanemajor_bitwise.swift:468-471`). A row left unwritten keeps its
fill byte and therefore *cannot* agree across the two fills, while a row that is
written agrees — which simultaneously gives a run-to-run determinism check. A
fill-pattern collision with a legitimate value cannot mask an unwritten row
because the two fills differ. `uncovered rows : 0` is reported under this
stronger check.

This is recorded as a harness bug found by the escaped-arm plane. It is not a
kernel finding, and it does not weaken the P0–P3 zeros — it strengthens the
coverage claim behind them.

## 8. Line-number corrections owed to the record

The advisor's audit (comment 17) asked for these to be fixed rather than
inherited. Verified in this session:

| location | says | correct |
|---|---|---|
| `research/frieren-pr35-r4-gate-blindness.md:84`, inherited by the assignment text | sole call site of `lagunaDecodeNVFP4QKVR1` at `:5907` | **`:5858`**; the function is defined at `:4902-4962` and its dispatches are at `:4930`, `:4946`, `:4957` |
| audit item (d) | lane-major guard at `:5003` | **`:4921`** (`if let lane = bank.laneMajorScales,`) |
| `research/frieren-pr35-r4-gate-blindness.md:438` | `prepareNativeAffineQKVWeight()` at `:5683` | `:5683` is `guard _fusedQKVWeight == nil,` inside `prepareFusedQKVWeight`; the correct symbol is at **`:5592`** (body `:5592-5672`) |

Both r4-note defects are fixed in place in this revision.

Two further findings from that audit, recorded because they change how the
programme should describe its own safety net:

- The **first blocking guard** for the oracle is not the lane-major guard at
  all: it is `let fusedAffine = _nativeAffineQKV` at **`:5822`**, which is nil
  under `LagunaUpstreamEquivalence` because the field's sole writer (`:5664`,
  inside `prepareNativeAffineQKVWeight()`) is reached only from
  `prepareFusedRuntimeWeights` (`:11216`), which the oracle never calls
  (`LagunaUpstreamEquivalence.swift:41` `compare`, `:74`
  `LagunaRuntimeModel(runtimeConfig)`, `:88` `eval(runtime)`, `:91` `newCache`;
  zero `LagunaRuntimeWeightCache` occurrences). The oracle also skips
  `narrowScales` (`:4936`), fused-norm INT8 (`:5831`) and NVFP4 `quantizedMM`
  QKV (`:5864`), falling through to BF16 `lagunaFusedNormQKVProjection`
  (`:5947`).
- The correct general statement is therefore stronger than "the lane-major path
  is unguarded": **`LagunaUpstreamEquivalence` has never covered a single
  derived or fused runtime layout.** The same single-caller-from-
  `prepareFusedRuntimeWeights` structure holds for `prepareRoPEAngleAtlases`
  (`:10578`), `prepareNativeAffineOProjWeight` (`:5291`),
  `prepareLastPrefillProjectionWeights` (`:5415`), `prepareFusedSharedGateUp`
  (`:8048`), `prepareFusedDenseGateUp` (`:8086`), `prepareFusedRoutedGateUp`
  (`:9740`) and `LagunaLmHeadPruner` (`:10916-10958`).

Per the advisor, the previously proposed "one-line oracle repair" is
**withdrawn**: r5-A is the correct instrument, not a stopgap.

## 9. Scope — what this certificate does and does not cover

Covers:

- bitwise equality of the lane-major and wide QKV decode arms, over both
  shipping geometries, all 40 real planes, three synthetic addressing planes,
  and a mixed escaped/fitting plane, resolved per lane;
- the escaped arm's `sc[b * (block_size/16)]` stride, which §3.6 does not;
- coverage and determinism of every dispatched row under two pre-fills;
- discrimination power, proven at single-nibble/single-lane resolution.

Does **not** cover:

- the M5 `_nax` kernel family — this is an M4 Pro host (Apple GPU generation
  16). The lane-major QKV kernels here are MLX `custom_kernel` sources with no
  `_nax` variant, so the extracted text is the ranked text; but no claim is made
  about any `_nax` prefill kernel;
- routed-expert pairwise structure (assigned to another student — zero time
  spent here);
- the 4-bit lane-major scale-width win implied by §6's pairwise constancy
  (89.1 → 23.1 MB/step). **Explicitly not in r5.**

## 10. Reproduction

```bash
# 1. dump real planes + generated kernel texts (needs a pre-built worker)
git apply research/frieren-pr35-r5a-dump.patch
bash research/frieren_pr35_r5a_dump.sh          # -> /tmp/pr35_r5a
python3 research/frieren_pr35_r5a_split_gen.py  # -> research/r5a_kernels/*.metal
git checkout -- Sources/

# 2. build + run the bitwise harness (from repo root)
PR35_PLANES=/tmp/pr35_r5a bash research/frieren_pr35_r5a_bitwise_run.sh
```

The committed `research/r5a_kernels/*.metal` let step 2 run without step 1.
Step 2 is GPU-only, holds no model, and completed in **2.525 s**
(`run_training` `9b57e616-9773-4920-b859-94da9fea62fc`, exit 0).

## 11. Contract state at r5

Re-verified this session at `HEAD = 98e2872`:

```
editable budget OK: current=2966629/3000000 bytes headroom=33371 growth=-33355/262144 files=142 (file count is diagnostic only; base=142)
```

- `git diff --stat b3319dfb5c13d7c3c669424139d50acaac044f70 HEAD -- Sources/ Vendor/` → **empty**; the submitted surface is byte-identical to the submission commit.
- `wc -c Sources/MLXFastModel/LagunaRuntimeModel.swift` → **521566** ≤ 523,000 B.
- Inject knobs present at the submission commit:

```
b3319dfb5c13d7c3c669424139d50acaac044f70:Sources/MLXFastModel/LagunaRuntimeModel.swift:11342:    "DARKBLOOM_INJECT_DECODE_EMPTY", 0)
b3319dfb5c13d7c3c669424139d50acaac044f70:Sources/MLXFastModel/LagunaRuntimeModel.swift:11354:    "DARKBLOOM_INJECT_EMPTY_TG", 160)
```

`Sources/MLXFastModel`, `Sources/MLXFastTransform`, `Vendor/.../steel/gemm` and
`Vendor/.../steel/attn` are **directory** entries in `editablePaths` (97 entries
expanding to 142 files), so any claim that a `steel/*` file is outside the
surface is false.
