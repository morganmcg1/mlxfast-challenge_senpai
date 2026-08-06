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

Re-verified at the shipped commit `HEAD = 97457fc` (the note-only commit on top
of `592bd14`; the submitted surface is unchanged from `b3319dfb`):

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

## 12. Dispatch and queue authorization (internal record)

The r5-B grant was conditional on r5-A being bit-identical on P0–P3 with the P4
controls flagging. It is, so this section records the six preconditions I
checked before dispatching, because one of them is easy to get wrong.

**1. Host rule.** The `senpai/program.md` copy *on this branch* is unrebased and
still carries the old prohibition ("must never run `mlxfast submit` from a
private AWS host", line 462). That copy is **stale**. The live rule is on the
integration base `origin/codex/mlxfast-maple-20260804-advisor` =
`d08ddd7b2c33e9421c7c1d894c8b00071507fd31`, `senpai/program.md:458-470`, which
reads that an authorized advisor, student, or human operator may dispatch an
official submission, that a student must first commit the candidate and
coordinate its queue entry with the advisor, and that an authorized campaign
role **may** submit from a provisioned AWS host but must never print or commit
its credentials. The rule change landed in
`279b6e2409a2ca92f7b874e08a3dabc2c6ff4a0b` (2026-08-05T09:32:45+02:00). Anyone
auditing this dispatch against the on-branch file will see the wrong rule; that
is why it is written down here.

**2. Advisor coordination.** r5-B is an explicit binding conditional grant
("P0–P3 all bit-identical AND P4 flags ⇒ dispatch the ranked receipt
immediately, unprompted. You hold the channel and it is idle. Do not wait for
me."), reaffirmed in PR #35 comment 17 at 2026-08-05T23:34:54Z, which
post-dates the rule-change commit.

**3. Channel idle, verified rather than assumed.** `mlxfast submissions` listed
27 submissions immediately before dispatch, **every one terminal** (26
`rejected`, 1 `failed`), most recent `7f6fe89` at 8/5 11:15 PM. The account
limit is one submission in flight, not one per student, so this check is a hard
precondition and not a formality.

**4. r5-A PASS** — sections 1–10 above.

**5. Candidate committed, surface byte-identical.**
`git diff --stat b3319dfb..97457fc -- Sources/ Vendor/` is empty, and the
fault-injection defaults are at their required values at the shipped commit
(`DARKBLOOM_INJECT_DECODE_EMPTY 0`, `DARKBLOOM_INJECT_PREFILL_EMPTY 0`,
`DARKBLOOM_INJECT_EMPTY_TG 160`).

**6. `--local-submit` preflight passed** on the exact submitted tree
(`run_training` `68123fbc-21f5-4f31-8f7e-035332a979ee`, exit 0, 428.867 s):
`passed_correctness true`, `passed_decode_speedup_floor true`, `passed true`.
`passed_prefill_speedup_floor` is **false**, which is the expected sub-64 GiB
M4 artifact and not ranked evidence — the local baseline
`prefill_seconds_per_token 0.000368` is an official-M5 constant and the
assignment directs me to ignore local prefill entirely.

### Baseline-advance clearance

The advisor cleared the `baseline_advanced` move `eaedee84` →
`d08ddd7b2c33e9421c7c1d894c8b00071507fd31` with "Accept `current_base_sha
d08ddd7b…`. Do NOT rebase." Unlike the three earlier clearances in this span,
the intersection was **not** empty: of 188 changed files, exactly one is on the
submitted surface — `Sources/MLXFastModel/LagunaRuntimeModel.swift`, 21
insertions / 16 deletions in 7 hunks, all inside the #27 M5 hardware-constant
instrument block (tanjiro's `DARKBLOOM_INJECT_EMPTY_CHAIN` lever from #47, read
only under `if empties > 0`). It is cleared because the controlling defaults are
identical on all three trees. If the typed submission reports a
`baseline_advanced` conflict, `accepted_base_sha` is
`d08ddd7b2c33e9421c7c1d894c8b00071507fd31`.

### Dispatch

```
mlxfast submit --model "senpai" --note-file research/frieren-pr35-receipt-note.md
```

Queued 2026-08-06 as submission `0d123661-66d8-4b8c-962d-28dac448fa21`, status
`validating`, note 26.8 KiB. **The literal model value `senpai` was accepted**,
so the single permitted provider/model fallback was not used and the public note
carries no fallback disclosure. No credential was printed or committed at any
point (`mlxfast config` was never invoked).

### Scoring pre-registration this receipt is read against

Reported per receipt as `submission id, officialScore, ns, S, T`, with

```
ns = (0.013890/decode_spt)^0.75 * (0.0003845/prefill_spt)^0.25
S  = 512000 * prefill_spt        (ms)
T  = 1000 * decode_spt - S/128   (ms)
```

Never ranked by `officialScore`, and no `*_speedup` field quoted as evidence.
Baseline frontier receipt `0c21dc18`: **T 4.3181 ms, S 98.029 ms, ns 2.52973**.
Elasticities `d ln score / d ln T = 0.638`, `d ln S = 0.362`. The mechanism is
priced at **+0.58 % to +0.67 %** on `ns`; single-receipt MDE is **±0.278 %**.

| observed Δ`ns` vs `0c21dc18` | reading |
| --- | --- |
| ≥ +0.60 % | strong confirmation |
| +0.15 % … +0.60 % | report only; do **not** resubmit |
| −0.28 % … +0.15 % | inside single-receipt noise |
| < −0.28 % | report immediately |

### Which commit the upload actually carried

The upload ran at `2026-08-06T00:11:58Z`. Local commit times are
`592bd14 2026-08-05T23:59:43Z`, `97457fc 2026-08-06T00:11:24Z`, and
`03b2c04 2026-08-06T00:13:35Z`,
so branch `HEAD` at upload time was **`97457fc`**, not `03b2c04`. This does not
weaken the receipt, because none of those three commits touches the submitted
surface:

```
git show --stat 592bd14 | grep -E 'Sources/|Vendor/'   -> (none)
git show --stat 97457fc | grep -E 'Sources/|Vendor/'   -> (none)
git show --stat 03b2c04 | grep -E 'Sources/|Vendor/'   -> (none)
git diff --stat 97457fc 03b2c04 -- Sources/ Vendor/    -> (empty)
```

All three commits changed only `research/` prose. The uploaded scored surface is
therefore byte-identical to the surface at the final result commit.

**Amendment after reading the receipt.** The receipt reports
`submissionCommitSha 4bdeaae6a85a5269951edc3b2338ba0ff6d07adf`, and
`git cat-file -t 4bdeaae6…` fails locally, so that SHA is **not** any local
commit — the service synthesises its own commit from the uploaded surface. The
local-`HEAD` question above is therefore informative about provenance but is not
what the receipt records, and no local SHA should be claimed to "be" the
submitted commit.

### Receipt (terminal)

Read with `research/frieren_pr35_receipt_read.py` against a fresh feed dump, so
the numbers below are the raw `officialMetrics` fields rather than any
`*_speedup` convenience field:

```
status                : 'rejected'
officialScore         : 2.52045366445076
improved              : False
rejectionReason       : 'score did not improve current best'
submissionCommitSha   : '4bdeaae6a85a5269951edc3b2338ba0ff6d07adf'
createdAt             : '2026-08-06T00:11:58.043Z'
updatedAt             : '2026-08-06T00:33:28.616Z'

passed_correctness           : True
passed_prefill_speedup_floor : True
passed_decode_speedup_floor  : True
error                        : ''
first_failing_case/layer/step: None / None / None

decode_seconds_per_token          : 0.005011932296875
prefill_seconds_per_token         : 0.000191656169921875
baseline_decode_seconds_per_token : 0.013843359703125
baseline_prefill_seconds_per_token: 0.000367052978515625
peak_ram_gb                       : 21
golden_hash   : be7738fccd6a28807ae7d18c038cbbc9e1b05dab26b99b2f247358fdc67fcf71
harness_hash  : 9d8f03583db140897adc2d247556f1dd3980bf9217303e6b8ae0fd5baab28c33
weights_hash  : aff994300573c5e8589563fc9ff57cdcfb1ef9b49e14898be290a75a6b294b3d

derived: ns 2.556325618   S 98.127959 ms   T 4.2453076 ms
vs paired baseline 0c21dc18: ns +1.0512 %, T -1.6869 %, S +0.1006 %
PREREG READING: STRONG CONFIRMATION (>= +0.60 %)
```

`officialScore` reproduces exactly from the paired baseline, which confirms the
field is a same-session paired score and not a normalised one:

```
(0.013843359703125/0.005011932296875)^0.75
  * (0.000367052978515625/0.000191656169921875)^0.25
  = 2.52045366445076   (reported: 2.52045366445076)
```

### Where this candidate stands, and why it was still rejected

`research/frieren_pr35_ns_leaderboard.py` ranks every gate-passing receipt on
the normalised `ns` plane, which is the only cross-session comparable:

```
rank of 0d123661 by ns : 1 of 1046 gate-passing receipts
this receipt ns        : 2.556326
best other receipt ns  : 2.547641  (b6032aeb)
margin over field      : +0.3409 %
```

The `officialScore` record holder `46eeccf0` (off 2.552308) has `ns` of only
**2.524190**, so on the normalised plane this candidate is **+1.27 %** faster
than the receipt that currently defines the leaderboard.

The reason is that `officialScore` inherits the noise of the baseline it was
paired against, and the two baseline axes are wildly unequal
(`research/frieren_pr35_baseline_modes.py`):

| baseline axis | stdev/mean | max/min spread | weight | contribution to score noise |
| --- | ---: | ---: | ---: | ---: |
| `baseline_decode`  | 0.247 % | +1.921 % | 0.75 | 0.185 % |
| `baseline_prefill` | 1.933 % | +9.290 % | 0.25 | 0.483 % |

So baseline **prefill** dominates, despite carrying only a quarter of the
weight. Re-scoring this exact candidate against all 1046 observed baseline
*pairs* gives median 2.527385, p90 2.549877, max 2.584802, and it exceeds
2.552308 under **72 of 1046 draws (6.9 %)** — 4/4 within the small slow-prefill
tail (n=4, mean 0.000394668, separated by 6.01 %) versus 68/1042 in the main
mass. This candidate drew the **fast** prefill mode (0.000367053).

**Correction to an intermediate analysis.** A first pass
(`research/frieren_pr35_baseline_drift.py`) resampled only `baseline_decode`,
holding this receipt's `baseline_prefill` fixed, and concluded that *no* draw
could promote the candidate (0/1046). That conclusion was an artifact of
varying the low-noise axis alone, and the joint resampling above supersedes it.
The script is kept so the error is visible rather than quietly deleted.

Two honest consequences:

1. The mechanism is confirmed. `+1.0512 %` on `ns` is ~3.8x the `±0.278 %`
   single-receipt MDE and above the priced `+0.58 %..+0.67 %` band, and all
   three official gates pass with an empty `error`.
2. Promotion of *this* candidate is now mostly a baseline-draw lottery at about
   a 7 % hit rate per submission. Resubmitting the unchanged surface to catch a
   favourable draw would be noise-mining, not evidence, so it is deliberately
   **not** done here and is left as an explicit advisor decision.
