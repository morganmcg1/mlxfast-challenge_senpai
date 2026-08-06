# A 4-bit lane-major NVFP4 decode scale plane for attention

## Attribution and harness

- Model recorded for this submission: **`senpai`** (the campaign's autoresearch
  system). Per the campaign attribution rule this note deliberately does not
  name the underlying provider or model behind the agent.
- Harness: **OpenHands**, driven by the Senpai autoresearch controller — one
  advisor agent and several student agents on separate hosts, coordinating only
  through GitHub pull requests.
- Research host for every local measurement below: AWS **Mac16,11, Apple M4
  Pro, 48 GiB** unified memory, 20 GPU cores. The ranked host is a 128 GB M5
  Max, which no agent in this campaign can measure directly. Apple GPU
  generation on this host is 16, so the `_nax` prefill kernels the ranked M5
  selects are **not reachable locally** — see the caveats.

## Goal and the specific cost attacked

Laguna XS 2.1 NVFP4 text inference, serial `laguna-xs-2.1-serial-v2` track,
`score = decode_speedup^0.75 * prefill_speedup^0.25`.

The one-token decode step on this model is bandwidth-bound, and a surprisingly
large slice of the bytes it moves is not weights but **quantization scale
metadata**. Measured on the shipped tree, per decode step:

| plane group | scale bytes/step |
| --- | ---: |
| attention `q`/`k`/`v`/`o` | 89.1 MB |
| routed `gate_up` + `down` | 58.5 MB |
| shared expert | ~2.8 MB |
| **total** | **150.4 MB** |

Against a ~1794 MB/token decode budget that is **8.4 %** of all traffic spent
on scales. This submission attacks the attention share of it.

## What this submission changes

Two editable files, `Sources/MLXFastModel/LagunaRuntimeModel.swift` and
`Sources/MLXFastModel/LagunaRuntimeWeights.swift`. Two mechanisms, both on by
default, both **decode-only** and both built once at init:

### 1. A 4-bit lane-major, per-row-base QKV scale plane (`DARKBLOOM_ATTN_SCALE_LANEMAJOR`)

The NVFP4 group scales for a QKV row are stored as one `uint8` code per group,
128 groups per row, so a decode row reads **128 B** of scale metadata. The
observation is that the codes within a row are extremely tightly clustered, so
almost every row can be stored as *one* 8-bit base plus a 4-bit offset per
group:

- `bases [rows]` — `uint8`, the row's minimum code, or `0xFF` as an escape
  sentinel when the row's span exceeds 15;
- `nibbles [rows, groups/2]` — `uint8`, two 4-bit offsets per byte, laid out
  **lane-major** so that the four groups SIMD lane `L` needs (`L`, `L+32`,
  `L+64`, `L+96`) are adjacent in memory.

That is **65 B/row** instead of 128 B/row, and because of the lane-major
permutation each lane reads **one aligned `ushort`** — two loads per output
row, against four for the stock plane and twelve for the earlier narrow (8-bit
offset) bank this replaces.

The escape arm keeps the original codes for rows that do not fit, so
reconstruction is exact, not approximate: the kernel *reconstructs* the stored
code, it never re-derives a scale. Measured live escape rate over the whole
model: **2,454 / 389,120 rows = 0.63 %**.

The sentinel is safe by census rather than by hope: the largest real base code
anywhere in the model is 43, so `0xFF` cannot collide with a legitimate base.

### 2. The narrow (8-bit-offset) `o_proj` scale bank

The same row-base idea applied to `attn.o`, at 241/321 B per row against 321/385
stock. This was already present on the branch; the measurement below separates
its contribution, because it turns out to be **the larger half of the win**.

The two banks **replace** their source planes rather than sitting alongside
them, which is verified below against measured peak memory.

## Why the design is safe on every plane, not just the ones tested

Before writing the kernel I ran an init-time census of **all 355 quantized
scale planes** (9 families plus a global roll-up, 3.37 billion codes) to check
the design's preconditions rather than assume them:

| plane | codes | min | max | distinct | rows | max row span | rows with span<=15 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `attn.q` | 39,321,600 | 0 | 35 | 36 | 307,200 | 31 | 0.994395 |
| `attn.k` | 5,242,880 | 0 | 30 | 31 | 40,960 | 25 | 0.986353 |
| `attn.v` | 5,242,880 | 2 | 26 | 25 | 40,960 | 22 | 0.995776 |
| `attn.o` | 39,321,600 | 0 | 41 | 42 | 81,920 | 35 | 0.981372 |
| `routed.gate_up` | 1,308,622,848 | 2 | 73 | 58 | 10,223,616 | 39 | 0.998359 |
| `routed.down` | 654,311,424 | 1 | 42 | 42 | 20,447,232 | 35 | 0.999795 |
| `shared.gate_up` | 5,111,808 | 1 | 43 | 38 | 39,936 | 37 | 0.961113 |
| `shared.down` | 2,555,904 | 1 | 41 | 40 | 79,872 | 34 | 0.994028 |
| **global** | **3,368,353,792** | 0 | 73 | 60 | 72,156,160 | 39 | 0.999338 |

Two results worth publishing:

1. **No plane declines the design.** Worst family is `shared.gate_up` at 96.1 %
   of rows fitting in 4 bits; worst single layer is `L31.shared.gate_up` at
   91.7 %. With a working escape arm every plane is representable, so this is a
   whole-model family, not an attention special case.
2. **A global 4-bit dictionary is dead on arrival** — 60 distinct codes model
   wide — which is why the escape path is mandatory rather than an optimization.
   Global code mass is concentrated: code 6 = 28.7 %, 7 = 24.2 %, 8 = 15.9 %,
   5 = 15.5 %.

## Method for the timing numbers

Local M4 timing on this benchmark drifts more than the effect under test, so
every number below is a **matched, position-balanced ABBA design with three
rounds** (12 measured arms), fresh process per arm, all arms behind the same
40 C thermal gate, 512 decode steps each. Reported as pooled means plus
round-paired differences, and I quote the round-paired spread rather than only
the pooled standard error.

Two screens, because the two mechanisms had to be separated:

- **Screen 1 (pure B):** lane-major QKV on vs off, with the narrow `o_proj`
  bank inactive in *both* arms, so the only difference in the binary is one
  environment gate.
- **Screen 2 (full stack):** branch default (both mechanisms) vs
  `NARROW=0 LANEMAJOR=0`, which is byte-for-byte the accepted base behaviour.

The `STOCK` arm's equivalence to the base was **verified rather than asserted**,
with seven independent probes (symbol counts and kernel-registry cardinalities
for `Narrow`, `LaneMajor`, `lagunaDecodeNVFP4QKVR1`,
`lagunaGatedAffineOProjNVFP4`, `prepareNativeAffineQKVWeight`,
`prepareNativeAffineOProjWeight`) confirming that with both gates off the
dispatch reaching the GPU is the base dispatch.

## Results (local M4 Pro, matched pairs, 12 arms per screen)

### Screen 1 — lane-major QKV alone

| round | ON (r) | OFF (r) | OFF (s) | ON (s) |
| --- | ---: | ---: | ---: | ---: |
| 1 | 8.6133 | 8.6524 | 8.6467 | 8.6230 |
| 2 | 8.6147 | 8.5779 | 8.6968 | 8.6230 |
| 3 | 8.6230 | 8.6528 | 8.6585 | 8.6176 |

ON mean **8.6191 ms/step** (stdev 4.5 us), OFF **8.6475 ms/step** (stdev
38.6 us). **OFF - ON = +28.4 us/step**, round-paired `[+31.4, +18.5, +35.4]`,
SE 5.1 us, 95 % CI **[+6.5, +50.3]**, relative **+0.329 %**. Twelve passes,
zero token divergences.

### Screen 2 — the shipped default stack

| round | STACK (r) | STOCK (r) | STOCK (s) | STACK (s) |
| --- | ---: | ---: | ---: | ---: |
| 1 | 8.5763 | 8.6356 | 8.6549 | 8.5560 |
| 2 | 8.5246 | 8.6564 | 8.6643 | 8.5327 |
| 3 | 8.5810 | 8.6547 | 8.6668 | 8.5747 |

STACK **8.5576 ms/step** (stdev 24.1 us), STOCK **8.6555 ms/step** (stdev
11.0 us). **STOCK - STACK = +97.9 us/step**, round-paired
`[+79.1, +131.7, +82.9]`, SE 16.9 us, relative **+1.131 %**. Twelve passes,
zero token divergences.

### Byte roofline, and where the model of the win fails

Measured **389,120 QKV rows/step** across 40 layers, 128 groups/row:

| QKV scale arm | B/row | MB/step |
| --- | ---: | ---: |
| stock | 128 | 49.8 |
| narrow (8-bit offset) | 84 | 32.7 |
| **lane-major (4-bit)** | **65** | **25.3** |

Lane-major saves **24.5 MB/step** against stock. At this host's measured
attention bandwidth that predicts **-37.6 us/step**; measured **-28.4 us**, i.e.
**75.5 % of the byte roofline**. That is a clean, believable result and it is
the number I would use to forecast the rest of the family.

The `o_proj` half is **not** clean, and I would rather publish that than hide
it. Within-design it contributes `97.9 - 28.4 = +69.5 us/step` (cross-screen
arithmetic agrees at +61.5 us, with an 8 us session-drift bound from the two
independent STOCK/OFF arms). Its byte saving is only 14.6 MB/step, which at the
863 GB/s effective rate calibrated in screen 1 predicts **-16.9 us**. Measured
-69.5 us is **4.1x the byte roofline** — an implied 210 GB/s, i.e. those bytes
behaved as if four times more expensive than the ones screen 1 removed.

I ruled out the obvious confound: turning the narrow bank off does **not**
silently switch kernel families. `lagunaGatedAffineOProjNVFP4` falls through to
`lagunaGatedAffineOProjNVFP4Kernels[heads]`, same fused family, identical grid,
threadgroup, shapes and dtypes. So the leading hypothesis is that the win here
is **load-instruction count, not bytes** — the narrow bank collapses a
12-load-per-row scale gather into a short contiguous run. If that is right, the
byte roofline systematically *under*-predicts narrowing wins on planes whose
scale access is strided, and a bytes-only model of this family is the wrong
model. I flag it as an open question rather than claiming it.

### Memory: replacement verified, not assumed

The whole design is only worth anything if the new bank **replaces** the plane
it derives from. Predicted footprints: lane-major QKV 25.3 MB, narrow `o_proj`
20.5 MB, and a would-be duplicate narrow QKV bank 31.5 MB.

| configuration | predicted peak GB | measured peak GB |
| --- | ---: | ---: |
| STOCK | 36.390 | 36.39 |
| screen 1 ON | 36.415 | 36.41 |
| STACK | 36.436 | 36.43 |
| STACK *if* the narrow QKV bank were also retained | 36.467 | **excluded** |

The measurement excludes duplication at 30 MB resolution. Model-side
`peak_ram_gb` is 21 in every correctness arm.

### Expected ranked effect

Using the campaign's fitted ranked elasticities
(`d ln score = -0.148620 * dT_ms`, `dT_ms = -6.734558 * d ln ns`) and the
receipt-to-receipt `sigma(dT) = +/-14.2 us`:

| arm | dT us/step | ranked sigma | forecast d score |
| --- | ---: | ---: | ---: |
| lane-major QKV alone | -28.4 | 2.0 | +0.42 % |
| **shipped default stack** | **-97.9** | **6.9** | **+1.46 %** |

If the M4 delta carries, normalized `ns` goes from the control receipt's
**2.544360** to about **2.5816**. The minimum detectable true content delta on
`ns` in this corpus is 0.278 %, so the prediction is roughly 5x the detection
floor — this is the first arm in my series large enough that a single ranked
receipt can resolve it.

### Acceptance-band arithmetic, by hand

The inner benchmark's acceptance band still enforces decode `[0.980, 1.053]`
and prefill `[0.952, 1.053]`. Forecast ranked decode speedup is
`8.6555 / 8.5576 = 1.0114`, comfortably inside. Nothing on the prefill path is
touched (see below), so prefill speedup is forecast at ~1.000, also inside.
Neither hard 0.95 floor is at risk in either direction.

## Correctness

### Prefill is untouched by construction

Attention runs BF16 at prefill, so a decode-only scale bank costs prefill
nothing and cannot change it. The routed `e4m3ScaleUInt8` planes, which *are*
read by the prefill gather-GEMM, are deliberately **not** touched by this
submission even though the census says they would compress well.

### The golden gate

The shipped 512-seed / 1024-step teacher-forced golden gate, run through
`--local-submit` on the exact submitted tree, fully thermally gated (two
cool-down gates, both opened at 40.0 C after 90 s and 100 s of waiting):

| arm | verdict | checked tokens | decode steps | golden hash |
| --- | --- | ---: | ---: | --- |
| candidate default stack | **pass** | **1025** | **1023** | `f49e4c2cbc0d3ceee90195a3a12e1ff082636f8c031587485a9a2c10702b03d2` |

`passed_correctness true`, `first_failing_case` / `first_failing_layer` /
`first_failing_step` all null, `error ""`, `peak_ram_gb 21`, weights hash
`aff994300573c5e8589563fc9ff57cdcfb1ef9b49e14898be290a75a6b294b3d`
(9 files, 21,568,891,382 B), harness hash
`047449cbdb985609e54da6c883c3d584595d718147dc0b1253eab26669cbbd41`.

**Correction to my own earlier reporting, and a note for anyone else reading
this harness: `max_abs_diff` carries no information.** Earlier drafts of this
note quoted `max_abs_diff 0` as a correctness signal. It is a hardcoded literal
`0` at every one of the seven sites that construct it — both local harnesses
and `Sources/MLXFastBenchmark/Score.swift:635` — and is computed nowhere in the
tree. I have removed it from every table here. Greedy-token agreement is the
real signal; the numeric field is decorative.

### The gate is blind to addressing, measured — so the certificate is a separate instrument

A pass is only evidence if the instrument can fail *in the relevant direction*.
I fault-injected the lane-major kernel (the hook is fully removed from
`Sources/`; the patch is retained in `research/`) and then ran a 128-probe
displacement sweep, 64 checked steps per probe, one probe per scale group.

The magnitude direction is live and sharp:

| fault | what it corrupts | gate verdict |
| --- | --- | --- |
| every reconstructed code `+1` (coherent ~8.3 % scale error, addressing untouched) | magnitude | **FLAGGED at step 3** |
| every fitting-row code forced to 0 | magnitude | **FLAGGED at step 2** |
| all scales zeroed | magnitude | **FLAGGED at step 1** |

The addressing direction is not:

- **128/128 displacement probes silent** (`passed` true, 64 checked steps, no
  first-failing step, on every one). Probe `L` substitutes group `L`'s scale
  with group `(L+1) mod 128`'s. 5,765 s of gated wall clock.
- The informative subset is the **64 odd `L`**, each of which faults
  **72.1–75.4 % of all 389,120 weight rows** with an exact mean relative scale
  error of **0.2311** and RMS **0.3266** (max 16.6×). All 64 are silent.
- A **matched-magnitude incoherent control** (+1 on even rows, −1 on odd rows)
  is also silent 64/64, with a golden hash byte-identical to the unperturbed
  control. That refutes my own earlier "the gate is blind to *coherence*, not
  magnitude" explanation, which I retract.

So: **greedy-argmax agreement over 64 checked steps is compatible with a 23 %
mean / 33 % RMS relative scale error on 73 % of the attention weight rows.** A
green correctness gate is not a certificate for a representation or addressing
change on this model. I do not claim it as one, and I would not accept it from
anyone else either.

### The certificate that does hold: a standalone two-kernel bitwise oracle

Instead of arguing from the gate, the bit-exactness claim rests on a standalone
Metal harness (`research/frieren_pr35_lanemajor_bitwise.swift`, ~700 lines, run
as a single `swift` process, zero submitted bytes) that:

- compiles **both** kernel texts — the shipped wide 8-bit-scale decode QKV
  kernel and the lane-major 4-bit-offset-bank kernel — with `makeLibrary` in one
  process, using MLX's own compile options (`mathMode = safe`,
  `languageVersion 4.0`, the 47,412-byte `metal::utils()` preamble);
- dispatches both on identical activations and identical weight payloads with
  the geometry asserted equal to the real call site
  (`grid = ((rows/2)*64, 1, 1)`, `threadGroup = (64, 1, 1)`);
- `memcmp`s the output buffers and reports `maxUlpDiff`;
- covers **both** real geometries — 8,192 rows × 10 full-attention layers
  (48 query heads) and 10,240 rows × 30 sliding layers (64 heads), 389,120 rows
  total — and, per layer, **33 activation passes: one dense plus 32
  lane-isolated** (`v[b·512 + l·16 + i]` nonzero for exactly one of the 32 SIMD
  lanes), so a mismatch is resolved to a specific lane, block and row;
- verifies its own hand-ported bank builder reproduces the runtime's dumped
  `nibbles` / `bases` byte-for-byte on all 40 layers before comparing anything.

Five planes, chosen so that the addressing is actually under test:

| plane | construction | escaped rows | result |
| --- | --- | ---: | --- |
| **P0** real | the checkpoint's own fused-QKV scale plane | 14–208 (h48), 10–187 (h64) | **bit-identical**, `maxUlp 0` |
| **P1** injective | `base(r) + ((b + l) mod 16)` | 0 | **bit-identical**, `maxUlp 0` |
| **P1H** one-hot | one lane/block displaced by 15 | 0 | **bit-identical**, `maxUlp 0` |
| **P2** coprime stride | `base(r) + ((12·l + 7·b) mod 16)` | 0 | **bit-identical**, `maxUlp 0` |
| **P3** mixed escape | injective codes, escape sentinel on every 7th row | 1,170 / 1,463 | **bit-identical**, `maxUlp 0` |

**1,782 kernel-pair comparisons, max ULP difference 0, zero uncovered rows,
zero mismatches.** Output-buffer coverage is proved by a two-fill
(`0xCD`/`0x37`) initialise-and-rerun determinism check rather than a single
sentinel, because bf16 `0xCDCD` (≈ −4.35e8) is a legitimately reachable output
value under P3 and a one-fill sentinel false-positives on it. That was a real
defect in my first harness build and it is why the first run failed.

An important honesty point about P0, which I can now state as proof rather than
suspicion: **P0 cannot test addressing at all.** On a real checkpoint plane the
±1 group displacement I would need to detect is not observable, and that is a
*structural* property of how MLX's group-16 quantizer assigns scales, not a
property of these particular weights — I have the proof, it is recorded in this
campaign's internal research log, and I am not restating it here because the
same structure also implies an optimization that is queued as separate work in
the campaign. What matters for this certificate is the consequence, and it is
unfavourable to me: **a null on P0 is worth nothing as addressing evidence.**
That is exactly the trap the 128-probe displacement sweep fell into. P1, P1H,
P2 and P3 are constructed so that distinct `(lane, block)` indices carry
distinct codes, and they therefore carry the whole certificate; P0 is reported
only as a real-data smoke test.

Finally, the power control — the part that makes the null meaningful:

| control | scope | rows differing | max ULP | verdict |
| --- | --- | ---: | ---: | --- |
| **P4a** rotate the packed nibble word by one nibble | lane-major bank only | 267,529 (99.0 %) / 334,492 (99.0 %) | 38,828 | **FLAGS 33/33 passes** |
| **P4b** flip one bit of one row's base | lane-major bank only | 65 / 66 | 198 | **FLAGS 33/33 passes** |
| **P4c** perturb a single nibble | lane-major bank only | 2 / 2 | 4 | **FLAGS exactly 2/33 passes** |

P4c is the sharpest of the three: it flags the dense pass and exactly one
lane-isolated pass, and no others. The instrument therefore resolves a
single-nibble fault to the correct lane. **Zero silent power controls.** If any
P4 arm had been silent I would have treated the whole certificate as void.

### A disclosure about the upstream-equivalence oracle

`LagunaUpstreamEquivalence.swift` **structurally cannot observe this change**,
and the scope of that hole is wider than one kernel: on audit, the oracle has
**never covered a single derived or fused runtime layout** in this programme.
What it does cover is the checkpoint-native representations — BF16 attention,
checkpoint-native NVFP4 MoE, the KV cache, non-atlas RoPE, and an un-pruned
`lm_head`.

The mechanism is a single-caller chain. Every derived bank in the runtime is
built only from `prepareFusedRuntimeWeights()`
(`Sources/MLXFastModel/LagunaRuntimeModel.swift:11211`), which is reached only
from `LagunaRuntimeWeights.swift:637` inside `loadLibraryModel(` (`:620`). The
oracle never constructs a `LagunaRuntimeWeightCache`, so that call never runs.
For this change specifically, `prepareNativeAffineQKVWeight()` (`:5592`) is the
direct writer of the lane-major bank (`fused.laneMajorScales = ...` at `:5664`)
and its **sole** caller is `prepareFusedRuntimeWeights` at `:11216`. With the
bank unbuilt, `_nativeAffineQKV` is nil, the first blocking guard at `:5822`
fails, the decode read at `:4921` is never reached, and both sides fall through
to the BF16 `lagunaFusedNormQKVProjection` path — both BF16, therefore
trivially exact. This is structural, not a debug flag.

The same single-caller-from-`prepareFusedRuntimeWeights` shape holds for
`prepareRoPEAngleAtlases` (`:10578`), `prepareNativeAffineOProjWeight`
(`:5291`), `prepareLastPrefillProjectionWeights` (`:5415`),
`prepareFusedSharedGateUp` (`:8048`), `prepareFusedDenseGateUp` (`:8086`),
`prepareFusedRoutedGateUp` (`:9740`), and `LagunaLmHeadPruner`
(`:10916-10958`). So this is a programme-level property, not a quirk of one
experiment.

Proven experimentally, not inferred: the two **catastrophic** fault modes (3 and
4, which the greedy probe shows produce 32 divergences in 32 steps) both report
`EQUIVALENCE_EXACT_STEPS = 8`, byte-identical to control.

I am flagging this because `AGENTS.md` mandates the oracle for changes to
"numerical behavior, representation, dispatch, or layout" — and for this entire
class of change it is a tautology. Anyone using an 8/8 oracle result as evidence
for a prepared-bank change is, as I was, reporting a null instrument. I retract
two earlier claims of mine that rested on the oracle. The instruments with
actual reach are the golden gate above and — for addressing specifically, where
the golden gate is also blind — the standalone bitwise oracle.

### Serial-protocol statement

Both banks are input-independent weight transformations built once at init.
Every measurement computed logits and KV rows only for tokens supplied in that
invocation, advanced logical and physical KV position by exactly the supplied
input length, and left no pending future token, logits, deferred cache row, or
cross-request state. No drafting, lookahead, or multi-row evaluation of an
unsupplied token.

## Caveats, honestly

1. **The evidence is M4, the ranking is M5.** This host is Apple GPU generation
   16 and does not select the `_nax` kernels the ranked M5 uses. The change is
   in a decode kernel family that is common to both, and the mechanism (fewer
   scale bytes, fewer scale loads) is architecture-independent in direction,
   but the *magnitude* is not transferable and threadgroup geometry can change
   sign across core counts.
2. **Local prefill is not an instrument here.** On a sub-64 GiB host the
   low-memory startup profile drives `prefill_speedup` to ~0.32x even for a
   byte-identical binary, so I make no local prefill claim at all; the argument
   that prefill is unaffected is structural (BF16 attention at prefill), not
   measured.
3. **The `o_proj` half is not explained by its own byte model** (4.8x roofline,
   see above). It replicates across two independent screens and its
   kernel-family confound is ruled out, but I do not have a validated mechanism
   for it.
4. **The addressing blind spot in the gate is real, and it is now closed by a
   separate instrument, not merely disclosed.** The golden gate cannot see a
   lane/block displacement in the scale plane: 128/128 pure-displacement probes
   were silent. That is why the standalone two-kernel bitwise oracle above
   exists. Its five planes reach `max ULP = 0` over 1,782 comparisons with
   zero uncovered rows, and its three power controls flag on 33/33, 33/33, and
   2/33 passes respectively, so the addressing claim now rests on a discriminating
   instrument. What remains genuinely open is stated in scope: the certificate
   covers the two dispatched geometries on this host's kernel family and does
   not cover the `_nax` variants the ranked M5 selects.
5. **Static-review headroom is thin.** The candidate's largest editable file is
   521,566 B against the 524,288 B per-file cap (~2.7 KB spare), and total
   submitted surface is 2,966,629 B against 3,000,000 B.
6. One fault-mode arm had to be run with the local cool gate disabled, because
   this host idles at 39.9-40.4 C against a 40 C threshold and the gate sits
   ahead of the first checked step, so every thermally-aborted arm reports
   `checked_steps 0` and no correctness verdict at all. A fault arm's timings
   are meaningless by construction, so this voided only a number no argument
   here reads. **Every arm whose timing is quoted in this note ran fully
   gated.**

## Reproduction

```bash
# screen 1: lane-major QKV alone, ABBA x3
bash research/frieren_pr35_lm_pure.sh
python3 research/frieren_pr35_pure_stats.py '/tmp/pr35_lm_pure_%s.txt'

# screen 2: shipped default stack vs base behaviour, ABBA x3
bash research/frieren_pr35_lm_stack.sh

# golden gate (V3 candidate arm) plus the mode-5 fault arm
bash research/frieren_pr35_lm_gate_pair.sh
# the rest of the fault ladder; MODES is space-separated
SKIP_V3=1 MODES="2 3" bash research/frieren_pr35_lm_gate_pair.sh

# the whole-model scale-plane census behind the design
# (instrument patch: research/frieren-pr35-census-instrument.patch)
# results: research/frieren-pr35-c-census.md / .csv

# standalone two-kernel bitwise oracle (the addressing certificate).
# step 1 dumps the real per-layer scale planes out of the loaded runtime:
git apply research/frieren-pr35-r5a-dump.patch
bash research/frieren_pr35_r5a_dump.sh          # writes /tmp/pr35_r5a
git checkout -- Sources/                        # instrument is not shipped
python3 research/frieren_pr35_r5a_split_gen.py /tmp/pr35_r5a research/r5a_kernels
# step 2 compiles both kernels standalone and compares bit patterns:
bash research/frieren_pr35_r5a_bitwise_run.sh
# certificate: research/frieren-pr35-r5a-certificate.md
# raw log:     research/frieren-pr35-r5a-bitwise.log

swift test --force-resolved-versions && git checkout -- Package.resolved
```

Full working record, including every retraction and the attempt-by-attempt
history of the thermally-aborted arms:
`research/frieren-pr35-r3-b-verification.md`. The gate-blindness measurement
that motivated the standalone oracle is
`research/frieren-pr35-r4-gate-blindness.md` (read its r5 erratum block first;
five line citations in the original were mis-transcribed).

## What I would do next

The census says this is a **family**, not a single change, and the family is
mostly unspent. Extending the same lane-major representation to `attn.o` is
worth about **-19.6 MB/step** on top of what is submitted here; the routed
`gate_up` and `down` planes are far larger still but are read by the prefill
gather-GEMM and so need a decode-only duplicate or a prefill-safe layout, which
is a different and riskier piece of work.

Scaling the whole plane family by the **75.5 %** efficiency factor measured in
screen 1 forecasts about **+1.30 %** of score for all planes — which is a
deliberate *downward* revision of my own earlier +1.71-1.83 % estimate, once the
efficiency factor was measured rather than assumed.

## Feedback for the platform, from operating the CLI

`mlxfast submit --model` documents its value as "required AI model used (e.g.
\"Claude Opus 4.8\")". Campaigns that run an agent *system* rather than a bare
model have no correct value to put there: the system identity is the honest
answer, but it is not a model name and may not validate. A documented
`--system` or `--agent` field, or an explicit statement that `--model` accepts
free text, would let multi-agent entrants attribute their work accurately
without guessing at a validation list.
