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
`--local-submit`, fully thermally gated (opened at 39.69 C):

| arm | verdict | checked steps | `max_abs_diff` | golden hash |
| --- | --- | ---: | ---: | --- |
| candidate default stack | **pass** | **1025** | **0** | `f49e4c2c...02b03d2` |

`passed_correctness true`, `first_failing_*` null, `error ""`, `peak_ram_gb 21`,
weights hash `aff99430...`.

### The gate was fault-injected, because a passing gate proves nothing about its power

A pass is only evidence if the instrument can fail. I built a temporary
fault-injection hook into the lane-major kernel (six modes; the hook is fully
removed from `Sources/`, the patch is retained in `research/`) and ran the same
1025-step gate against deliberately corrupted reconstructions:

| fault mode | what it corrupts | gate verdict |
| --- | --- | --- |
| 2 | every reconstructed code `+1` (a coherent ~8.3 % scale error, addressing untouched) | **FLAGGED at step 3** |
| 3 | every fitting-row code forced to 0 | **FLAGGED at step 2** |
| 5 | the four codes in one lane's word reversed | **SILENT (passes, 1025 steps, `max_abs_diff` 0)** |

The honest three-part reading:

1. The gate is **wired** — modes 2 and 3 both trip it within three steps, so the
   candidate's pass is a live pass, not a disconnected instrument.
2. It is **sharp** — mode 2 shows a coherent one-code (~8.3 %) magnitude error
   is caught, which is well below any error this representation could produce
   accidentally.
3. It is nonetheless **blind to mode 5**, and I initially got the reason wrong.
   My first explanation was that mode 5's error was too *small*; mode 2 refutes
   that. The actual reason is **coherence**: reversing four codes inside one
   lane's word is an exact no-op wherever those four codes are equal (row spans
   are <=15 and the top seven codes carry ~97.9 % of all mass), and a zero-mean
   shuffle where they differ, so contributions partly cancel *inside a single
   dot product*. I have **not** measured the constant-quadruple fraction that
   would bound that cancellation quantitatively — the census is per-row — so
   this remains a real, disclosed residual blind spot for the zero-mean
   addressing-permutation class.

I therefore do **not** claim a complete addressing certificate for the
permutation. What I claim is: the reconstruction magnitude is certified to a
sharp floor, the permutation is exercised on 1025 real teacher-forced steps at
`max_abs_diff 0`, and the residual blind class is one where equal codes make the
fault provably inert.

### A disclosure about the upstream-equivalence oracle

`LagunaUpstreamEquivalence.swift` **structurally cannot observe this change**,
or any prepared fused decode bank. The oracle never constructs
`LagunaRuntimeWeightCache`, so `_nativeAffineQKV` is nil, the decode guard
fails, and both sides fall through to the BF16 `lagunaFusedNormQKVProjection`
path — both BF16, therefore trivially exact. This is structural, not a debug
flag.

Proven experimentally, not inferred: the two **catastrophic** fault modes (3 and
4, which the greedy probe shows produce 32 divergences in 32 steps) both report
`EQUIVALENCE_EXACT_STEPS = 8`, byte-identical to control.

I am flagging this because `AGENTS.md` mandates the oracle for changes to
"numerical behavior, representation, dispatch, or layout" — and for this entire
class of change it is a tautology. Anyone using an 8/8 oracle result as evidence
for a prepared-bank change is, as I was, reporting a null instrument. The
golden gate above is the instrument with actual reach. I retract two earlier
claims of mine that rested on the oracle.

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
4. **The permutation blind spot in the gate is real** and stated above; the
   constant-quadruple fraction that would bound it is unmeasured.
5. **Static-review headroom is thin.** The candidate's largest editable file is
   521,585 B against the 524,288 B per-file cap (~2.7 KB spare), and total
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

swift test --force-resolved-versions && git checkout -- Package.resolved
```

Full working record, including every retraction and the attempt-by-attempt
history of the thermally-aborted arms:
`research/frieren-pr35-r3-b-verification.md`.

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
