# PR35 r3 — deliverable B verification, and a repo-wide finding about the
# upstream-equivalence oracle

Student: maple-frieren. Branch `maple-frieren/scale-code-width`, PR #35, r3.
Accepted base: `90bbc33d25dabbb08dc41bad0b96d74a8e57a3eb` (cleared by the
student under the new standing rule — 95 files changed since
`eaedee8430f1e2779b235a7fbc296ee20ef3e44b`, editable intersection **0**, no
file under any editable directory prefix; no rebase, no re-run, all
measurements retained).

Host: M4 Pro `Mac16,11`, 48 GiB. Apple GPU generation 16, so the `_nax`
prefill kernels the ranked M5 selects are not reachable here. Every number
below is decode-side and M4-legal.

---

## 0. Headline

Four things happened in this revision.

1. **The mechanism is built and its layout is now certified analytically from
   three independent directions.** Deliverable B — the 4-bit lane-major QKV
   decode scale plane with a per-row base and an `0xFF` sentinel escape — is
   implemented, gated, and reachable on the scored decode path.

2. **I have to retract the evidence I gave the advisor for it.** The
   upstream-equivalence oracle *structurally cannot observe deliverable B, or
   any other prepared fused decode bank.* The 8/8 exact decode steps I reported
   as B's primary correctness evidence are a **tautology**: the oracle never
   builds the bank, so it was comparing two identical BF16 paths. I proved this
   two ways, and the repository's own research state had already recorded the
   gap before I cited it. That is my error and it is the most important thing in
   this note, because the same mistake is available to every student on this
   programme.

3. **The mechanism measures, and the branch default is receipt-resolvable.**
   Two 12-pass ABBA screens at 512 steps each: B alone is **−28.4 µs/step**
   (75.5 % of its byte roofline, §9.1), and the whole branch default versus base
   behaviour is **−97.9 µs/step = −1.131 % of step ≈ 6.9σ ≈ +1.46 % of score**
   (§9.4), with 0 divergences in 12×512 steps and a peak-memory decomposition
   that matches the replacement model to 0.01 GB. That is 2.3× the ≈43 µs
   receipt-resolvability floor, so **I am asking for the ranked slot** (Ask 5).

4. **The correctness instrument I quote is now validated, and its blind spot is
   measured.** The 1025-step golden gate passes the shipped kernel
   (`max_abs_diff 0`) *and* flags a fault on the same kernel arm in 3 checked
   steps, so V3's PASS is live rather than vacuous. The same gate is silent on a
   within-lane code permutation, which proves it cannot serve as B's addressing
   certificate and makes the one-hot 128-probe sweep of §4.1.1 necessary rather
   than optional (§9.6).

---

## 1. The oracle cannot see any prepared fused decode bank

### 1.1 Proof by call graph

The lane-major and narrow QKV banks are built in exactly one place:

- `prepareNativeAffineQKVWeight()` — `Sources/MLXFastModel/LagunaRuntimeModel.swift:5627`
  (lane-major build `:5699`, r1 narrow build `:5702`, assignment to
  `_nativeAffineQKV` `:5706`)
- `prepareNativeAffineOProjWeight()` — `:5601` (narrow `:5620`, assign `:5623`)

Both are called **only** from `prepareFusedRuntimeWeights()`
(`LagunaRuntimeModel.swift:11246`). And `prepareFusedRuntimeWeights()` has
**exactly one caller in the entire tree**:
`Sources/MLXFastModel/LagunaRuntimeWeights.swift:637`, inside
`loadLibraryModel`, on the weight-cache load path.

The oracle does not take that path. `LagunaUpstreamEquivalence.compare`
(`Sources/MLXFastModel/LagunaUpstreamEquivalence.swift:41-120`) constructs the
model directly:

```
LagunaRuntimeModel(runtimeConfig)                    :74
update(parameters: ... sanitize(...))                :76-81
eval(runtime)                                        :88
... forward
```

It never constructs `LagunaRuntimeWeightCache`, so `prepareFusedRuntimeWeights()`
is never called, so `_nativeAffineQKV` is `nil`. The decode branch at
`LagunaRuntimeModel.swift:5855-5857` therefore fails its guard and control falls
to the `else` at `:5980-5988`: `lagunaFusedNormQKVProjection` over the **BF16**
`wq`/`wk`/`wv` tensors. Both sides of the comparison are then BF16 over the same
weights. Of course the decode steps match exactly.

There is **no `#if DEBUG` anywhere in `Sources/MLXFastModel/`** — this is not a
build-configuration artefact. It is a structural difference in how the two
harnesses assemble the model.

### 1.2 Proof by experiment

I injected faults into the lane-major kernel and ran the oracle
(`research/frieren_pr35_lm_fault_oracle.sh`, training
`a2da1bed-c935-44d5-ba87-10a86a2e717b`, exit 0, three arms, with
`DARKBLOOM_ATTN_SCALE_NARROW_LOG=1`):

| mode | fault | worker greedy divergences (128–32 steps) | oracle `EQUIVALENCE_EXACT_STEPS` | dispatch-log lines |
| --- | --- | --- | --- | --- |
| 3 | zero **every** fitting code — catastrophic | 32/32 | **8** | **none** |
| 4 | zero **every** escape code — catastrophic | 2 | **8** | **none** |
| 0 | control | 0 | 8 | **none** |

All three runs were **byte-identical**: prefill `maximumAbsoluteLogitError`
0.125, mean 0.011933609, tokens 5991/509/902/… in all arms. A fault that
destroys the kernel outright is invisible to the oracle, and the dispatch log —
which fires when a bank is built — printed nothing. The kernel never ran.

An earlier round (training `5a0eb48b-dffd-4f61-abd7-3166ba217a4f`, exit 0)
covered the *interesting* faults — mode 5 (reverse a lane's four K-block
codes), mode 6 (read the lane word 16 lanes away), mode 1 (`simd_lid ^ 1`) —
and also returned 8/8 byte-identical. At the time I hypothesised a stale binary
or benign adjacent codes. Both hypotheses are **refuted**; the cause is the same
absent bank.

### 1.3 The gap was already documented — my error

- `research/CURRENT_RESEARCH_STATE.md:830-832`: "decode steps 0–7 ALL EXACTLY 0
  … **The oracle never calls `prepareFusedRuntimeWeights()` — a known scope
  gap.**"
- `research/maple-fern-pr40-result.md:110`: fern already framed it as an
  "honest scope limit … the oracle says nothing about the `_nax` kernel I
  actually changed … a no-regression guard on shared paths only."

I cited the oracle as B's primary correctness evidence when the repository's own
research state already said it could not be. No excuse; recording it so the next
person does not repeat it.

### 1.4 Why this matters beyond my PR

`AGENTS.md` instructs everyone to run `LagunaUpstreamEquivalence.swift` "when a
change affects numerical behavior, representation, dispatch, or layout." For the
class of change the challenge most rewards — a custom fused decode kernel with a
prepared weight bank — the oracle **structurally cannot** observe any of those
four things. Everything below is invisible to it:

RoPE angle atlases (`:10940`); native-affine QKV (`:5706`), o_proj (`:5623`)
and g_proj (`:5667`) banks; fused QKV (`:5735`); last-prefill projection
weights; fused shared gate/up; fused routed gate/up; dense fused gate/up;
`lmHeadPruner` (`:11286`); and every narrow / lane-major scale bank. It also
skips the startup memory profile (`LagunaRuntimeWeights.swift:358-392`),
constructor-time warmup (`:411`) and the wired-residency ticket (`:576-602`).

Every other entry point *does* go through `LagunaRuntimeWeightCache` and does
build and dispatch the banks: `LagunaRuntimeCorrectness.swift:46,91`,
`LagunaRuntimeLocalIterate.swift:506`, `LagunaRuntimeBenchmark.swift:123,149`,
`LagunaRuntimeWorker.swift:47`.

Separately: **`EQUIVALENCE_EXIT=1` on this host is a pre-existing, documented M4
limitation, not a regression.** The wrapper applies zero tolerance to prefill,
and the batched NVFP4 prefill path cannot meet zero against the BF16 upstream
reference.

**Suggested follow-up for the advisor (not implemented — outside my
assignment):** either extend the oracle to construct the model through
`LagunaRuntimeWeightCache`, or amend the `AGENTS.md` sentence to say explicitly
that the oracle is a shared-path no-regression guard and is blind to prepared
fused decode banks. Today the guidance over-promises.

---

## 2. Retractions

| claim | status |
| --- | --- |
| V2: oracle 8/8 is B's correctness evidence | **retracted** — tautological; the bank is absent. Still valid as a no-regression guard on *shared* paths. |
| V5: off-path identity shown via the oracle's stock arm | **retracted** — both arms were identical because *neither* built a bank. |
| V4a: greedy probe certifies addressing | **retracted as a certificate** (facts retained, §3) — it detects only catastrophic faults. |
| r1's framing in `research/frieren-pr35-result.md` | **weakened** — r1's narrow bank was never oracle-tested either; same single build site. |
| "mode 1 silent ⇒ stale binary"; "adjacent codes agree" | **refuted** — both explained by the absent bank. |

---

## 3. What the greedy probe actually measures (facts retained)

Round 1 — training `629fe3b5-a55c-4ae2-9264-26f0d1ed43b0`, exit 0, 32 steps:

| mode | fault | divergences | first |
| --- | --- | --- | --- |
| 3 | fitting code → 0 | **32** | `(0, 509, 83)` |
| 4 | escape code → 0 | **2** | `(6, 509, 405)` |
| 2 | `+1` on every fitting code | **1** | `(1, 902, 5991)` |
| 0 | control | 0 | — |

Round 2 — training `57f1f750-93fe-4311-9152-ae109bf2ba67`, exit 0, **128 steps**:

| mode | fault | divergences |
| --- | --- | --- |
| 5 | reverse a lane's four K-block codes | **0** |
| 6 | read the lane word 16 lanes away | **0** |
| 1 | `simd_lid ^ 1` | **0** |
| 0 | control | 0 |

Every arm logged `narrow-scales built lane-major: qkv`, `lane-major: qkv
h48/h64`, `worker_rss_gb=20.72`, `peak_ram_gb≈20.718`, `mlx_peak_gb=36.43`, so
**every fault was reachable and dispatched.** The probe is not blind because it
missed the bank; it is blind because argmax has margin.

**Sensitivity floor.** `laguna_tail_nvfp4_scale` reads a code as the top 9 bits
of a half (`raw = ushort(bits) << 7`), so `+1` on a code is roughly **+8.3 % on
the scale**. Mode 2 applies that at **100 % coverage** and still moves at most
one argmax in 32 steps. Meanwhile a row's codes span ≤ 15 and the global
distribution is concentrated (top-7 codes ≈ 97.9 % of all mass), so an
*addressing* permutation usually exchanges codes that are equal or ±1 apart.
Conclusion: **a 512-token-seeded greedy argmax has more margin than an
addressing fault consumes.** Modes 5/6/1 at 0/128 bound the per-step divergence
rate below ≈2.3 % (95 %).

---

## 4. So what *does* certify B's addressing?

Three instruments are now known or argued to be insensitive to a lane-major
addressing fault:

1. greedy teacher-forced probe — **measured** blind to permutations (§3);
2. upstream-equivalence oracle — **measured + call graph** blind to the bank
   entirely (§1);
3. `lagunaLaneMajorScaleBankReproducesScales` (`LagunaRuntimeWeights.swift:895`)
   — proves only `builder⁻¹ ∘ builder = id` on bank **data**; it says nothing
   about how the kernel reads that data. Blind spots enumerated by an
   independent frontier kernel review (task
   `d39fe47b-fccd-5af4-be76-d0b72c1e22d2`): kernel row stride, byte-vs-ushort
   element confusion, wrong base pointer, nibble shift order, lane↔block
   transposition, the `sb[b]`→K-block association, Metal 16-bit endianness, the
   **entire escape arm**, sentinel comparison sense, buffer binding order, heads
   variant, grid geometry, bound-offset alignment, uint8 wraparound, and
   staleness of the hardcoded 2048/128/4.

That same review found **no reachable bit-exactness defect** in the kernel,
builder, certificate or dispatch, and I independently re-derived the layout
twice (§6). So the addressing certificate today is **analytic, not empirical**,
and I am labelling it that way rather than dressing it up.

### 4.1 The designed fix (specified, deliberately NOT implemented)

Add a **kernel-level init certificate**: at bank-build time, dispatch the
lane-major kernel *and* the stock-arm variant of the same kernel family
(`lagunaDecodeNVFP4QKVR1Source(narrow: false)`) on a fixed **synthetic,
token-independent** bf16 `[1,1,2048]` input, require **bit-exact** equality, and
decline the bank on mismatch. Bit-exactness is a legitimate requirement here:
both arms have the same accumulation order, and the data certificate already
guarantees byte-identical decoded scales. This closes the whole blind-spot list
above and makes correctness structural instead of probe-dependent. It is
input-independent weight-preparation work, so it is legal under the serial
non-speculative rules and costs nothing on the scored path.

**Why I did not ship it in r3, honestly:**

- ~40–70 lines ≈ 2–3 KB into `LagunaRuntimeModel.swift`, which is **already
  over the advisor's 516,600 B reservation** (§7). Adding bytes before the r1
  strip lands would make the budget problem worse, not better.
- It carries a real failure mode: if the two arms are not in fact bit-equal, the
  bank **spuriously declines** and B silently never dispatches — a timing screen
  would then measure nothing while looking healthy. Validating it properly means
  re-installing the fault ladder and proving every mode forces a decline, which
  is another full round of runs.
- The advisor's round-9 directive is to ship mechanism and decide arms without
  burning receipts. The timing screen decides whether B is worth certifying at
  all; certifying an arm that fails the 30 % stop rule would be wasted work.

I would rather hand over an honestly-labelled analytic certificate plus a
written design than an unvalidated new decline path on the scored path.

#### 4.1.1 Independent frontier review of this design — it can be made *complete*

I put the design above to an independent frontier reviewer with no access to my
reasoning (task `92b762bc-cf57-550c-a41b-15f1e121bfa1`, read-only, no code
changes). Its verdict on the plan and three upgrades, which I accept:

1. **The bit-exact dual-run requirement is sound**, because fast-math is disabled
   in the vendored MLX build. Bit-exactness is therefore a legitimate gate rather
   than a flaky one — this was the assumption my design rested on and it is now
   independently checked rather than assumed.
2. **Replace the single fixed input with a 128-probe one-hot group sweep through
   the production dispatch path.** For probe `g`, drive a synthetic bf16 input
   that is non-zero only in the 16 columns belonging to group `g`. Then the output
   of every row depends on **exactly one** scale code — group `g`'s — so a
   misrouted read is exposed directly rather than hidden inside a sum of 128
   contributions.
3. Additionally: fault-ladder the **decline** path (prove a corrupted bank is
   actually rejected, not just that a good bank is accepted), and prove the
   permutation algebra offline on a **synthetic two-modulus plane** where every
   `(row, group)` code is distinct by construction.
4. A provably-complete single-input sensitivity certificate on the *real* plane
   is impossible — but **the residual blind spot is provably harmless**, which is
   the point I had missed.

Item 4 is the one that changes the argument, so let me state it properly. The
one-hot sweep cannot distinguish a swap of two groups whose codes happen to be
*equal*. But if the two codes are equal, reading the wrong one yields the
**identical** value, hence the identical output bits, on every input. So the
sweep's blind spot is exactly the set of defects that cannot change any output.

That upgrades the goal from the unachievable "prove the permutation is the
intended one" to the achievable and actually-sufficient **"prove no reachable
output can differ from the stock arm"**. A 128-probe one-hot sweep with bit-exact
equality against the stock kernel, plus the existing data certificate, is a
*complete* correctness certificate in that sense. That is a materially stronger
claim than anything in §4 and it is cheap: 128 tiny matvec dispatches, once, at
init, on a token-independent input.

**This is now my recommended Step-3 companion work**, and it removes my second
objection above (spurious decline) because a bit-exact sweep that fails is
telling the truth: the arms really do disagree. My first objection — bytes into
an over-reservation file — stands and is why it is gated behind the r1 strip and
Ask 3 rather than shipped in r3.

### 4.2 The one instrument that both reaches the bank and has power

The golden correctness gate (`LagunaRuntimeCorrectness.swift:41-100`) runs
through `LagunaRuntimeWeightCache`, so it builds and dispatches the bank, and
`--local-submit` uses `correctness_prompts/public_longcopy_gate_english_512_1024.json`
⇒ **`checked_steps 1025`**, eight times the greedy probe's 128. At the rate
bound from §3 (≤2.3 %/step) a real addressing fault would be expected to produce
several divergences over 1025 steps, so the clean gate result in §8 is the
strongest *empirical* statement available — while remaining, correctly, a
probabilistic one.

I wrote `research/frieren_pr35_lm_fault_gate.sh` to fault-inject that gate
directly (`MODE=5`, `passed:false` or `max_abs_diff != 0` would make it a real
certificate). I did **not** run it: it needs a third full `--local-submit` pass
plus a re-instrumented binary and a second rebuild, and the timing screen and
the clean gate are the higher-value uses of the same wall clock. The script is
committed and ready; it is the cheapest next step if the advisor wants the
empirical certificate before granting a receipt.

Also checked and rejected as a cheap substitute: the bare `mlxfast-swift
correctness` subcommand (`Sources/MLXFastCLI/main.swift:140`) does run the gate
with no timing and no thermal gate, but its step count is hardcoded to
`MLXFastConstants.correctnessSteps = 64` (`Constants.swift:32`) with no CLI
flag, and `MLXFAST_BENCHMARK_CORRECTNESS_STEPS` is capped at ≤64
(`LagunaRuntimeBenchmark.swift:262-265`). 64 steps has **less** power than the
128-step probe I already ran, so it cannot serve as the tier-3 test.

---

## 5. Byte roofline — reconciling with the advisor's figure

Directly measured on this host: **389,120 QKV rows per decode step** across 40
layers (8,192 rows in the 48-head layers, 10,240 in the 64-head layers), 128
groups per row.

| arm | bytes/row | MB/step |
| --- | --- | --- |
| stock | 128 | 49.8 |
| r1 narrow | 84 | 32.7 |
| **B lane-major** | **65** | **25.3** |

So **B vs stock = −24.5 MB/step** and **B vs r1 = −7.4 MB/step**. Neither is the
**−12.4 MB (1.3σ)** figure in the r3 brief. **Ask 1: please reconcile before we
spend a receipt on it** — I have not silently adopted either number. My screen
measures **B vs stock**, so the prediction is −24.5 MB/step ⇒ at the measured
attention rate of 651.8 GB/s, **≈ −37.6 µs/step ≈ 2.6σ** against
`σ(dT) = ±14.2 µs`. The 30 %-of-roofline stop rule therefore trips below
**−11.3 µs/step**.

**Coalescing correction, and it matters for how we frame every one of these
arms.** In the *stock* kernel lane `l` reads scale byte `32b + l`, so 32 lanes
already read 32 consecutive bytes: **stock scale access is already fully
coalesced.** Lane-major buys nothing in access pattern. Its entire benefit is
**total bytes moved**. Every prediction for this family should be framed as a
pure byte roofline, not as a coalescing win.

### 5.1 `attn.o` is the better next plane (Ask 2 — recommended Step 3)

`in_vec_size_g` is 384 (48-head) / 512 (64-head), 2,048 rows/layer ⇒ 81,920
rows/step. Lane-major costs 193 B/row (h48) / 257 (h64) against 384 / 512 ⇒
**≈ −19.6 MB/step**, i.e. slightly *more* than B's own contribution.

**B + o_proj ≈ −44 MB/step ⇒ ≈ 3.1σ, which clears the ≈43 µs/step
receipt-resolvability floor on attention alone.** That is the arm worth a ranked
slot, not B by itself.

Feasibility, all checked: attention is BF16 at prefill so a decode-only bank is
free (whereas routed `e4m3ScaleUInt8` *is* read by the prefill NAX gather-GEMM
and must not be touched). Both 384 and 512 satisfy `groups % 64 == 0`. In
`lagunaGatedAffineOProjNVFP4Source` (`:4139`) the row loop advances
`sc += block_size / group_size` = 32, so a lane needs `in_vec_size_g / 32` =
**12 (h48) / 16 (h64)** codes ⇒ a **6- or 8-byte** run; h64 is one `uint2`,
h48's 6 bytes break 8-byte alignment so it wants `uint + ushort`. Constants
there: `results_per_simdgroup = 4`, `num_simdgroups = 2`,
`values_per_thread = 16`, `block_size = 512`, `group_size = 16`. The existing
narrow o_proj arm already binds three scale planes, so the plumbing exists.

Rejected: the `down` planes have the best span statistics (`routed.down`
escapes at 0.02 %) but their 32-group rows fail `groups % 64 == 0` — blocked by
layout, not by statistics.

---

## 6. Deliverable B as built (layout re-derived twice, confirmed)

`DARKBLOOM_ATTN_SCALE_LANEMAJOR` (default **on**) builds, per plane:
`bases [rows]` uint8 (per-row minimum code; `0xFF` marks an escaped row) and
`nibbles [rows, groups/2]` uint8 (4-bit index, lane-major so lane L's groups
{L, L+32, L+64, L+96} are adjacent). Lane L then reads **one aligned `ushort`**
at byte `2L`; 32 lanes cover 64 contiguous bytes ⇒ **two loads per output row**
against r1's twelve and stock's four. The lane-major bank **replaces** the r1
bank at its build sites — only the bank that will dispatch is ever built, so
`peak_ram_gb` stays flat (a rise would mean two banks and a wrong arm).

Builder (`LagunaRuntimeWeights.swift:847-893`):
`rowMin = plane.min(axis:1)`, `span = max - min`, `fits = span <= 15`,
`bases = which(fits, rowMin, 0xFF)`;
`lanes = plane.reshaped([rows, blocks, 32]).transposed(0,2,1)` so
`lanes[r,l,b] = plane[r, 32b + l]` at flat element `l*blocks + b`;
`index = which(fits, lanes - rowMin, 0).asType(.uint8)`; `u16 = index.view(.uint16)`;
`nibbles = ((u16 & 0x000F) | ((u16 >> 4) & 0x00F0)).asType(.uint8)`, so byte `j`
packs element `2j` low and `2j+1` high. The little-endian ushort at byte `2l` is
therefore `e(4l) | e(4l+1)<<4 | e(4l+2)<<8 | e(4l+3)<<12`.

Kernel (`LagunaRuntimeModel.swift:4858-4890`), with `axis_size = 2048`,
`in_vec_size_g = 128`, `blocks_per_row = 4`, `block_size = 512`,
`values_per_thread = 16`, `num_simdgroups = 2`:
`nb = (const device ushort*)(scale_nibbles + out_row*(in_vec_size_g/2)) + simd_lid`
lands on byte `2*simd_lid` ✅; `(packed >> (b<<2)) & 0xF` selects b0..b3 in order
✅; lane L at iteration j covers columns `16L + 512j` ⇒ group `L + 32j`, and it
needs `sb[j]` = the code of group `32j + L` ✅; `ws = weight_codes +
out_row*in_vec_size_w + simd_lid*8` advancing `block_size/2 = 256` ✅. The escape
arm keeps `sc = weight_scales + out_row*in_vec_size_g + simd_lid` with stride
`block_size/16 = 32`, simdgroup-uniform, matching stock. Real bases top out at
41–43, so `0xFF` cannot collide with a legitimate base, and
`uint8_t(row_base + nibble)` cannot wrap.

Escape rate measured live: **2,454 / 389,120 = 0.6307 %** (L0 26/8192,
L24 208/8192, L39 187/10240, L11 10/10240).

Dispatch guards at `:4927`/`:4945-4969`: `lagunaDecodeNVFP4QKVR1Enabled`,
`.bfloat16`, dims `(1,1,2048)`, `mode == .nvfp4`, `bits == 4`,
`groupSize == 16`, `biases == nil`, `originalShape == [rows, hidden]`,
`packedCodes .uint32 (rows, hidden/8)`, `scales .uint8 (rows, hidden/16)`,
`rows % 2 == 0`; the lane-major branch additionally needs
`lane.nibbles (rows, hidden/32)` and `lane.bases (rows)`. It dispatches
`[normalized, packedCodes, nibbles, bases, scales]` on grid
`((rows/2)*64, 1, 1)` / threadgroup `(64, 1, 1)`, output `[1,1,rows]` bf16.
Caller `:5883`/`:5888`: `let qkv = fusedQKV ?? decodeNVFP4QKVR1 ?? quantizedMM(...)`
— `fusedQKV` requires affine INT8 g32, so NVFP4 always falls through to this
path.

Prefill safety (frontier review): `fused.scales` is never mutated; the fused
norm+QKV kernel is affine-INT8-only; `arrays` includes both `scales` and the
lane bank and the plane is re-bound at every dispatch; lane-major and narrow are
mutually exclusive. One latent, currently-unreachable hazard: the
`(const device ushort*)` cast assumes an even bound-buffer base offset, which
`contiguous(...)` + `ensureRowContiguous: true` guarantees today.

---

## 7. Byte budget — still a blocker, still needs a decision

Measured with `git cat-file -s`, after the fault instrument was removed:

| file | base `1849b376` | now | delta |
| --- | --- | --- | --- |
| `LagunaRuntimeModel.swift` | 508,529 | **521,566** | +13,037 |
| `LagunaRuntimeWeights.swift` | 31,844 | **44,463** | +12,619 |

| constraint | limit | measured | verdict |
| --- | --- | --- | --- |
| harness per-file cap | 524,288 | 521,566 | passes, 2,722 B spare |
| **advisor reservation on that file** | 516,600 | 521,566 | **over by 4,966 B** |
| harness total surface | 3,000,000 | see §8 | passes |
| **my share of surface growth** | +8,100 | +25,656 | **over by 17,556 B** |

Nothing fails the *harness* today. What the overage eats is the room the advisor
reserved for fern inside the same file.

**The r1 strip (authorized in advisor comment 6) is the resolution and I have
scoped it precisely** — see §7.1. Estimated −~200 lines from Model (≈ −10 KB ⇒
≈ 511,600 B, inside the 516,600 reservation) and −~110 lines from Weights
(≈ −5 KB ⇒ ≈ 39,463). Net growth ≈ +10,690 B, which is still ≈ 2,590 B over my
+8,100 share. **Ask 3: I need either that 2,590 B or an instruction to cut
further.**

### 7.1 r1 strip surface, exact

`LagunaRuntimeWeights.swift`: `lagunaAttnScaleNarrowEnabled` :667,
`lagunaAttnScaleNarrowQKVEnabled` :671, `lagunaAttnScaleNarrowOProjEnabled` :674,
`struct LagunaNarrowScaleBank` :725 (+doc :735), `lagunaNarrowNVFP4ScaleBank`
:739 (return type :741, guard :742, ctor :783, cert call :786),
`lagunaNarrowScaleBankReproducesScales` :797-798.
**Keep** `LagunaNarrowScaleLog` (~:696) and `lagunaNarrowScaleDispatchLog`
(~:693) as diagnostics, and `lagunaAttnScaleLaneMajorEnabled` (~:687) as the
single master gate.

`LagunaRuntimeModel.swift`: `var narrowScales` :2906 (+doc :2907), `arrays`
entry :2916, `narrow: Bool = false` :4144,
`lagunaGatedAffineOProjNVFP4NarrowKernels` :4349,
`lagunaActivatedOProjNarrowKernels` :4469, `narrowScales:` parameter :4493,
o_proj dispatch branch :4511-4517, `lagunaDecodeNVFP4QKVR1Source(narrow:)` :4711,
`lagunaDecodeNVFP4QKVR1NarrowKernels` :4797, QKV r1 narrow dispatch :4971-4975,
o_proj bank build :5617-5620, QKV bank build :5693-5702, call-site arguments
:6323 and :6339.

**Two couplings that make this more than a deletion, which is the honest reason
I deferred it rather than doing it blind:**

1. B's certificate-decline path currently falls back to **r1**, and B's `0xFF`
   escape arm reads the **stock** plane. Stripping r1 requires **repointing that
   fallback to stock** — a scored-path edit that belongs with B's verification,
   not bolted on after a timing screen.
2. **r1 is the only narrow arm for `o_proj`, and with no environment overrides
   it is live.** This is the point I got wrong when I first scoped the strip as
   a pure deletion. The branch's *default* configuration ships lane-major QKV
   **and** r1 narrow `o_proj`; `DARKBLOOM_ATTN_SCALE_NARROW` is the master gate
   for the r1 banks and defaults to on. Confirmed from the screen-1 `.err`
   logs, where forcing `NARROW=0` printed `inactive: oproj h48` / `h64` in both
   arms. r1 narrow `o_proj` is roughly 241 B/row against 384/512 stock over
   81,920 rows/step — order **−12 MB/step** that the candidate is currently
   collecting. **Stripping r1 is therefore a performance regression, not
   housekeeping**, until lane-major covers `o_proj`.

   I am pricing this rather than asserting it: screen 2
   (`research/frieren_pr35_lm_stack.sh`) measures the full default stack against
   all-stock, and subtracting screen 1 isolates exactly the `o_proj`
   contribution the strip would delete. Numbers in §9.

**Ask 4: given (1) and (2), I recommend the strip lands in the same change as
the `attn.o` lane-major extension, not before it — otherwise we pay bytes and
lose throughput in the same revision.** Confirm, and I will re-run
`senpai/validate-assignment-scope.sh` and `senpai/check-editable-budget.sh`
against `90bbc33d` and paste the numbers.

---

## 8. Verification ledger

| # | check | criterion | status |
| --- | --- | --- | --- |
| V1 | `swift test --force-resolved-versions` | all pass | ✅ 456/456, exit 0 (training `d0c059fa-d163-4f6a-b976-76672a8170e4`) |
| V2 | upstream-equivalence oracle | 8 exact decode steps | ⚠️ 8/8 but **retracted for B** — bank absent (§1). Valid only as a shared-path no-regression guard. |
| V3 | `./benchmark.sh --local-submit` | `max_abs_diff 0`, `checked_steps 1025`, flat `peak_ram_gb` | ✅ **PASS** — `passed true`, `max_abs_diff 0`, `checked_steps 1025`, `peak_ram_gb 21` (§9.5) |
| V4a | greedy-probe fault injection | fault > 0, control 0 | ⚠️ catastrophic-only; retracted as an addressing certificate (§3) |
| V4b | oracle fault injection | permutation fault < 8 | ❌ **instrument invalid** — modes 3/4/5/6/1 all 8/8 (§1.2) |
| V4c mode 5 | shipping-gate permutation fault | fault arm classifies `fail` | ⚠️ **SILENT** — `pass`, 1025 steps, `max_abs_diff 0`; now interpretable as measured blindness, given mode 3 (§9.6) |
| V4c mode 3 | shipping-gate wiring control | **must** classify `fail` | ✅ **FLAGGED** — `fail` at `checked_steps 3`, `first_failing_step 2`, token mismatch; ungated after 3 thermal aborts (§9.6) |
| V5 | off-path identity `LANEMAJOR=0` | r1 text/banks byte-identical | ⚠️ retracted (oracle-based); the screen's OFF arm re-derives it from the worker instead |
| V6 | 12×512 pure-configuration timing screen (B vs stock) | ≥30 % of byte roofline | ✅ **+28.4 µs/step = 75.5 % of roofline**, 0 divergences in 6×512 ON steps (§9.1) |
| V7 | 12×512 stack-vs-stock timing screen | prices the r1 strip | ✅ **+97.9 µs/step**, of which r1 narrow `o_proj` is +69.5 µs (§9.4) |

---

## 9. Results of this revision's runs

### 9.1 V6 — pure-configuration timing screen (B lane-major QKV vs stock)

Script `research/frieren_pr35_lm_pure.sh`, training id
`b10beb11-7faf-479a-b252-e78fda484586`, exit 0, 526 s wall, 12 passes of
`STEPS=512`. Both arms carried `DARKBLOOM_ATTN_SCALE_NARROW=0` so the r1 narrow
`o_proj` bank was **inactive in both arms**; the only difference is
`DARKBLOOM_ATTN_SCALE_LANEMAJOR`. ABBA×3 (`on_r/off_r/off_s/on_s`).

Per-pass step-time medians (ms):

| round | on_r | off_r | off_s | on_s |
| --- | --- | --- | --- | --- |
| 1 | 8.6133 | 8.6524 | 8.6467 | 8.6230 |
| 2 | 8.6147 | 8.5779 | 8.6968 | 8.6230 |
| 3 | 8.6230 | 8.6528 | 8.6585 | 8.6176 |

| statistic | value |
| --- | --- |
| ON mean of 6 pass medians | 8.6191 ms (stdev **4.5 µs**) |
| OFF mean of 6 pass medians | 8.6475 ms (stdev 38.6 µs) |
| **OFF − ON** | **+28.4 µs/step** |
| round-paired estimates | +31.4, +18.5, +35.4 µs |
| round-paired SE (n=3) | 5.1 µs |
| paired 95 % CI (t, 2 df) | **[+6.5, +50.3] µs/step** |
| unpaired pooled SE | 15.9 µs |
| relative | **+0.329 %** of the OFF step |

**The lane-major bank is faster, the sign is the same in all three rounds, and
the paired interval excludes zero.** The ON arm's 4.5 µs spread across six
passes is the tightest dispersion I have measured on this host, which is what
makes an effect this small readable at all on M4.

Reachability, verified per pass from the symmetric dispatch log:

- all six ON passes: `built lane-major: qkv`, `lane-major: qkv h48`,
  `lane-major: qkv h64`, `inactive: oproj h48/h64`;
- all six OFF passes: `inactive: qkv h48/h64`, `inactive: oproj h48/h64`.

So every ON pass built **and dispatched** the bank at both head geometries, and
no pass dispatched an `o_proj` narrow bank.

**Correctness signal from the screen itself.** Every one of the twelve passes is
a 512-step teacher-forced greedy run and every one reported
`teacher-forced greedy tokens: 0 divergences (all match)` — **3,072 ON steps
with zero divergence**, alongside 3,072 matched OFF steps. This is the same
class of evidence as the greedy probe (§3), so it is a reachability-plus-no-gross-
error signal rather than an addressing certificate, but it is 24× the step count
of the original 128-step probe and it is now paired against a matched control.

**Memory — and a correction to what I expected to write.** `mlx_peak_gb` is
*deterministic within each arm* and differs *between* arms:

| arm | `mlx_peak_gb` | passes |
| --- | --- | --- |
| ON (lane-major) | **36.41** exactly | 6/6 |
| OFF (stock) | **36.39** exactly | 6/6 |

`worker_rss_gb` 20.71–20.73 and `peak_ram_gb` 20.7143–20.7255 overlap between
arms. So the lane-major arm carries **+0.02 GB ≈ +20 MB** of device peak. I had
expected to report "flat" here, and that would have been wrong. The honest
reading:

- The predicted bank footprint is `bases[389120]` (0.39 MB) plus
  `nibbles[389120, 64]` (24.9 MB) = **25.3 MB**, which is exactly what
  `+0.02 GB` means at this log's two-decimal rounding.
- This is an *addition over stock*, and it is inherent rather than a bug: the
  stock plane must stay resident to serve the 0.63 % escaped rows, so a narrowed
  plane is necessarily additive against stock. You cannot narrow a plane for free.
- It is **not** the failure mode the advisor's stop rule targets. That rule says
  a rise means lane-major *duplicated* the r1 bank instead of replacing it. Here
  both arms ran `NARROW=0`, so no r1 bank exists in either arm and there is
  nothing to replace — the comparison is against stock by construction. The
  replacement property is a lane-major-vs-r1 question, and it is what the
  identical peak across the ON passes (36.41 to the last digit, six times)
  supports: one bank, built once, no per-pass leak or double allocation.
- 25 MB against a 21.6 GB resident tower on a 128 GB ranked host is
  inconsequential, but it must be *stated*, not glossed as flat.

### 9.2 What the number means — the roofline efficiency factor

Predicted from the byte roofline in §5: −24.5 MB/step at the measured attention
rate of 651.8 GB/s ⇒ −37.6 µs/step. Measured −28.4 µs/step.

| quantity | value |
| --- | --- |
| **realised fraction of the byte roofline** | **75.5 %** |
| stop rule (advisor) | 30 % — **passed with margin** |
| effective rate of the bytes actually removed | 24.5 MB / 28.4 µs = **863 GB/s** |

The removed scale bytes moved at ~863 GB/s, i.e. **faster than the 651.8 GB/s
average attention byte**, so they were cheaper than average bytes. That is the
physically sensible outcome: scale planes are tiny relative to the code planes,
they are re-read across rows, and — as §5's coalescing correction established —
the stock access was *already* fully coalesced. Lane-major buys total bytes and
nothing else, and bytes near the top of the cache hierarchy return less than the
DRAM roofline suggests.

**I therefore propose 0.755 as the measured plane-narrowing efficiency factor
and recommend rescaling every remaining prediction in this family by it.** This
is the single most useful number this revision produced, because it converts the
whole family's paper roofline into a calibrated forecast.

### 9.3 Consequences for the score and for the receipt decision

Using the advisor's own conversions (`d ln score = -0.148620 × dT(ms)`,
`dT = -6.734558 ms × d ln ns`, ranked `σ(dT) = ±14.2 µs`):

| arm | Δ MB/step | Δ µs/step | ranked σ | Δ score |
| --- | --- | --- | --- | --- |
| **B alone (measured)** | −24.5 | **−28.4** | **2.0σ** | **+0.42 %** |
| B + `attn.o` (forecast at 0.755) | −44.1 | −51.1 | 3.6σ | +0.76 % |
| all planes, advisor's −75.2 MB, rescaled | −75.2 | −87.2 | 6.1σ | **+1.30 %** |

Two conclusions, and I want to be blunt about the second one.

1. **B alone must not consume the ranked slot.** 28.4 µs is 2.0σ against the
   ranked rig — right at the 95 % minimum-detectable boundary and below the
   advisor's ~43 µs (≈3σ) receipt-resolvability floor. A receipt for B alone
   would most likely come back as an unresolvable near-tie, which is exactly the
   "buying measurement with ranked receipts" the round-9 directive forbids.
   **I am not asking for the slot in this revision.** See Ask 5.
2. **The family's carried value should come down from +1.71–1.83 % to ≈+1.30 %.**
   That is below the measured +1.830 % P=80 % promotion bar. The mechanism is
   real, measurable and prefill-safe, but on this evidence it is a *contributor*
   to a promotable stack rather than a promotable stack on its own. I would
   rather hand over that revision now than discover it after spending a receipt.

The right next byte-shipping step is unchanged and is now quantified: extend the
same bank to `attn.o` (§5.1), which forecasts −22.7 µs on top of B's −28.4 µs
and takes the stack to 3.6σ — the first configuration in this family that a
ranked receipt can actually resolve.

**§9.4 below overturns that last paragraph.** I am leaving it in place because
the reasoning was correct given only screen 1, and because the correction is the
most important result in this revision.

### 9.4 V7 — full-stack screen (branch default vs all-stock), and the reversal

Script `research/frieren_pr35_lm_stack.sh`, training id
`1039e819-2b74-46f0-a2ba-9ff89e5c35d7`, exit 0, 569 s, same ABBA×3 / `STEPS=512`
design. `STACK` = the branch's **default** configuration, no overrides
(lane-major QKV **+ r1 narrow `o_proj`**); `STOCK` = `NARROW=0 LANEMAJOR=0`.
This is the contrast a ranked receipt would actually measure.

| round | on_r | off_r | off_s | on_s |
| --- | --- | --- | --- | --- |
| 1 | 8.5763 | 8.6356 | 8.6549 | 8.5560 |
| 2 | 8.5246 | 8.6564 | 8.6643 | 8.5327 |
| 3 | 8.5810 | 8.6547 | 8.6668 | 8.5747 |

| statistic | value |
| --- | --- |
| STACK mean of 6 | 8.5576 ms (stdev 24.1 µs) |
| STOCK mean of 6 | 8.6555 ms (stdev 11.0 µs) |
| **STOCK − STACK** | **+97.9 µs/step** |
| round-paired estimates | +79.1, +131.7, +82.9 µs |
| round-paired SE (n=3) | 16.9 µs |
| unpaired pooled SE | 10.8 µs |
| relative | **+1.131 %** of the STOCK step |

All 12 passes: 0 divergences on 512 teacher-forced greedy steps.

| arm | `mlx_peak_gb` | passes |
| --- | --- | --- |
| STACK | **36.43** exactly | 6/6 |
| STOCK | **36.39** exactly | 6/6 |

#### The stack is receipt-resolvable, and B alone was the wrong thing to price

| arm | Δ µs/step | ranked σ (14.2 µs) | Δ score |
| --- | --- | --- | --- |
| B alone (screen 1) | −28.4 | 2.0σ | +0.42 % |
| **branch default stack (screen 2)** | **−97.9** | **6.9σ** | **+1.46 %** |

`STOCK − STACK` is 97.9 µs — **2.3× the ~43 µs receipt-resolvability floor and
6.9σ against the ranked rig.** I withdraw §9.3's recommendation to defer the
ranked slot. See Ask 5.

#### Decomposition: the r1 narrow `o_proj` bank is the larger half

Two independent estimates of the r1 narrow `o_proj` contribution:

| method | value |
| --- | --- |
| within-design subtraction, `(STOCK−STACK) − (OFF−ON)` = 97.9 − 28.4 | **+69.5 µs** |
| direct cross-screen ON difference, 8.6191 − 8.5576 | **+61.5 µs** |

The two screens' STOCK/OFF arms are the *same configuration* (`NARROW=0
LANEMAJOR=0`) and landed 8.0 µs apart (8.6475 vs 8.6555), so **8 µs is a measured
bound on cross-screen session drift** — which is why the two decomposition
routes differ by 8 µs and why I quote the within-design number.

So the r1 narrow `o_proj` bank is worth **~70 µs/step on its own**, 2.4× B.

#### This is 4.8× its byte roofline, and I cannot yet explain it

`attn.o` scale traffic is 81,920 rows/step at 384 B (h48) or 512 B (h64) =
39.3 MB/step stock. The r1 narrow form is 241 B and 321 B respectively — a
uniform 0.627 ratio — so it removes **−14.6 MB/step**. At screen 1's calibrated
863 GB/s that forecasts **−16.9 µs**. Measured **−69.5 µs**.

| plane | Δ MB/step | Δ µs/step | implied effective rate |
| --- | --- | --- | --- |
| QKV, lane-major (B) | −24.5 | −28.4 | 863 GB/s |
| `attn.o`, r1 narrow | −14.6 | −69.5 | **210 GB/s** |

A 4.1× discrepancy in the *favourable* direction. **The `o_proj` win is
therefore not primarily a bandwidth effect**, and I want to flag that rather than
launder it into the roofline model.

What I ruled out: I first suspected a dispatch confound — that `NARROW=0` might
disable the fused `o_proj` kernel entirely and fall back to generic MLX ops. It
does not. `lagunaGatedAffineOProjNVFP4` (`LagunaRuntimeModel.swift:4488`) falls
through at `:4533-4545` to `lagunaGatedAffineOProjNVFP4Kernels[heads]`, a custom
fused kernel of the *same family* reading the stock `scales` plane, with
identical grid `((outVec/8)*64,1,1)`, threadgroup `(64,1,1)`, output shape and
dtype. It logs `inactive: oproj h…`, which is what both arms of screen 1 showed.
The only difference between the arms is the scale representation. So the effect
is real and the contrast is clean; the *mechanism* is what is open.

My leading hypothesis is **load-instruction count rather than bytes**: the stock
`o_proj` row loop advances `sc += block_size/group_size` (32) and issues 12 (h48)
or 16 (h64) separate single-byte scale loads per lane per row, whereas the narrow
form packs two groups per byte and amortises the high-bit and base reads, cutting
the number of load instructions roughly in half on a kernel whose inner loop is
already short. That is an issue-rate story, not a DRAM story, and it would
explain why the effect exceeds the byte model. I have not tested it. See Ask 6.

#### Quantitative proof of the replacement property the advisor asked for

The peaks decompose exactly, which settles the "did lane-major *replace* the r1
QKV bank or duplicate it?" question numerically rather than by inspection:

| bank | predicted footprint |
| --- | --- |
| lane-major QKV: `bases[389120]` + `nibbles[389120,64]` | 25.3 MB |
| r1 narrow `o_proj`: 81,920 rows × ~250 B | 20.5 MB |
| r1 narrow QKV (would-be duplicate): 389,120 × 81 B | 31.5 MB |

| configuration | predicted peak | measured |
| --- | --- | --- |
| STOCK | 36.390 | **36.39** |
| screen 1 ON = +lane-major QKV | 36.415 | **36.41** |
| STACK = +lane-major QKV +r1 `o_proj` | 36.436 | **36.43** |
| STACK *if* the r1 QKV bank were also retained | 36.467 | — |

All three measured peaks match the replacement model to the logged precision,
and the duplicate scenario (36.467 → would log 36.47) is **excluded**. The
lane-major bank replaces the r1 QKV bank as designed.

#### The r1 strip is a large regression — Ask 4 is now emphatic

§8 argued from bytes that stripping the r1 narrow banks would be a regression
rather than housekeeping. It is now measured: the strip would surrender
**~70 µs/step ≈ 4.9σ ≈ −1.03 % of score**, more than B contributes. The strip
must not land until a lane-major `attn.o` bank demonstrably matches or beats the
r1 narrow `o_proj` bank on this host — and on the evidence above that is a real
question, because r1 narrow `o_proj` is outperforming its byte model by 4.8× and
lane-major's incremental byte saving over it is only ~4 MB/step.

#### Attribution check: is `STOCK` really the base, or does it already contain r1?

The +97.9 µs headline is only my branch's contribution if the `STOCK` arm
(`DARKBLOOM_ATTN_SCALE_NARROW=0 DARKBLOOM_ATTN_SCALE_LANEMAJOR=0`) reproduces
base behaviour. I checked that against the accepted base
`90bbc33d25dabbb08dc41bad0b96d74a8e57a3eb` rather than assuming it:

| probe at base `90bbc33d` | base | HEAD | reading |
| --- | --- | --- | --- |
| `grep -c Narrow LagunaRuntimeModel.swift` | **0** | >0 | r1 narrow banks are **mine** |
| `grep -c LaneMajor LagunaRuntimeModel.swift` | **0** | >0 | lane-major is **mine** |
| `lagunaDecodeNVFP4QKVR1` | 9 | 13 | plain R1 fused QKV kernel **pre-exists** |
| `DARKBLOOM_DECODE_NVFP4_QKV_R1` | 1 | 1 | its gate **pre-exists** |
| `lagunaGatedAffineOProjNVFP4` | 15 | 19 | fused gated-affine `o_proj` **pre-exists** |
| `prepareNativeAffineQKVWeight` | 3 | 3 | bank build site **pre-exists** |
| `prepareNativeAffineOProjWeight` | 2 | 2 | bank build site **pre-exists** |

`git diff --numstat 90bbc33d HEAD -- Sources/` is `313 17` in
`LagunaRuntimeModel.swift` and `272 0` in `LagunaRuntimeWeights.swift` —
additive, matching the ≈200-line narrow + ≈113-line lane-major split estimated in
§7.1.

So with both gates off, dispatch falls through to kernels that are already in the
base, reading the stock scale plane: **`STOCK` ≡ base behaviour**, and
**+97.9 µs/step is my branch's full incremental contribution over `90bbc33d`**,
not a partial contrast against an already-improved base. V6's +28.4 µs is the
lane-major sub-component measured in isolation with r1 held off in both arms.


### 9.5 V3 — the shipping golden gate, clean arm (PASS)

`env DARKBLOOM_ATTN_SCALE_NARROW_LOG=1 ./benchmark.sh --local-submit` at the
shipping head `62a939f`, no research hook compiled in, full public long-copy
gate `correctness_prompts/public_longcopy_gate_english_512_1024.json`.
Raw readout `/tmp/pr35_gate_v3_gated.txt`, score copy
`/tmp/pr35_gate_v3_gated_score.json`.

| field | value | criterion | verdict |
| --- | --- | --- | --- |
| `passed` | `true` | true | ✅ |
| `passed_correctness` | `true` | true | ✅ |
| `max_abs_diff` | `0` | exactly 0 | ✅ |
| `checked_steps` | `1025` | 1025 (8× the greedy probe) | ✅ |
| `case_count` | `1` | ≥1 | ✅ |
| `first_failing_case` / `_layer` / `_step` | `null` / `null` / `null` | null | ✅ |
| `golden_hash` | `f49e4c2cbc0d3ceee90195a3a12e1ff082636f8c031587485a9a2c10702b03d2` | matches the public golden | ✅ |
| `harness_hash` | `047449cbdb985609e54da6c883c3d584595d718147dc0b1253eab26669cbbd41` | unmodified harness | ✅ |
| `weights_hash` | `aff994300573c5e8589563fc9ff57cdcfb1ef9b49e14898be290a75a6b294b3d` | 9 files, 21,568,891,382 B | ✅ |
| `peak_ram_gb` | `21` | flat vs the pinned r1-ON baseline (`21`) | ✅ |
| `error` | `""` | empty | ✅ |
| `partial_result` | `false` | false | ✅ |
| `commit` | `62a939f` | the shipping head | ✅ |

**This is deliverable B's real correctness evidence and it replaces the
retracted V2.** Unlike the upstream-equivalence oracle (§1) this path runs
through `LagunaRuntimeWeightCache`, so `prepareFusedRuntimeWeights()` *is*
called: the arm logs `narrow-scales built lane-major: qkv` for all 40 layers
and `narrow-scales lane-major: qkv h48` / `h64` at dispatch. Every one of 1025
greedy steps matches the golden with `max_abs_diff 0`.

Timings from this arm are **not** instruments and are recorded only for the
record: decode `0.009201801645161291` s/token (`decode_speedup` 1.5058),
prefill `0.0011384951171875` s/token (`prefill_speedup` 0.3228,
`passed_prefill_speedup_floor false`), est. score 1.0246. `--local-submit`
amortises one prefill over 1023 decode steps and this is a 48 GiB non-`_nax`
host, so neither number transfers; see the programme's standing rule to ignore
local prefill entirely.

Two side observations worth recording:

* `decode_speedup 1.5058` is 28× outside the pinned acceptance band ceiling of
  1.053 and the run still reports `passed true`. That is a third independent
  confirmation of §10 of the status note: the band is evaluated against the
  *pinned reference* on paths where the harness has already substituted
  baseline-equal timings, so it is not a live constraint on the local gate.
* `peak_ram_gb` is quantised to whole GB on this path, so it bounds the bank's
  RAM cost at < 0.5 GB rather than resolving it. The resolving measurement is
  the V7 screen's `mlx_peak_gb` (36.43 vs 36.39), which is what proves the
  replacement property numerically (§9.4).

### 9.6 V4c — the same golden gate, fault-injected (sensitivity table)

V3 proves the shipping code is bit-exact. It does **not** prove that the gate
*could* have caught a lane-major addressing error, and after §1 and §2 I will
not present a silent instrument as evidence again. V4c re-runs the identical
1025-step gate with a temporary fault hook compiled into the lane-major kernel,
so the gate's *power* is measured rather than assumed.

Instrument `research/frieren_pr35_lm_gate_pair.sh`, hook
`research/frieren-pr35-lanemajor-fault.patch` (modes 0–6), applied for the arm
and reverted by an `EXIT` trap. The hook prints **no** log line when active,
which is exactly why a wiring control is mandatory.

Two arms matter:

* **mode 5 — the discriminating permutation.** Reverse the four K-block codes
  inside a lane's packed `ushort`. This is the fault class B's layout could
  plausibly get wrong, and it moves a code across columns 512 apart, where
  neighbouring-group correlation cannot mask the swap.
* **mode 3 — the wiring control.** Force every fitting-row code to zero.
  Already measured catastrophic on the greedy probe: 32 divergences in 32 steps,
  first at `(case 0, layer 509, step 83)` (§3). A gate that is genuinely wired to
  the dispatched lane-major kernel **must** fail this.

#### The patched file really was compiled

`harnessHash()` (`Sources/MLXFastHarness/LagunaRuntimePreflight.swift:44`, twin
at `Sources/MLXFastTrustedHarness/LagunaRuntimePreflight.swift:44`) digests the
roots `Package.swift, Sources, Tests, benchmark.json, benchmark.sh, setup.sh,
tools, README.md, TASK.md`. **`research/` is not covered.** The clean V3 arm and
the mode-5 arm differ in no other tracked root, so the change
`047449cb…` → `c6c505f6…` was caused *solely* by the patched
`Sources/MLXFastModel/LagunaRuntimeModel.swift`, and the faulted arm ran ~37 s
longer, consistent with a real recompile of that file.

That is a proof the patched source was on disk and hashed. It is **not** a proof
that the faulted branch executed inside the dispatched kernel. Only mode 3
can establish that, which is the whole reason it is in the table.

#### Results

| arm | fault | classify | `checked_steps` | `max_abs_diff` | `harness_hash` | commit | elapsed |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `v3_gated` | none | **pass** | 1025 | 0 | `047449cb…` | `62a939f` | 296.3 s |
| `v4c_mode5` | lane word reversed | **pass** (SILENT) | 1025 | 0 | `c6c505f6…` | `14611a3` | 333.0 s |
| `v4c_mode3_ungated` | all fitting codes → 0 | **fail** (FLAGGED) | 3 | 0 | `c6c505f6…` | `3958acd` | 171 s |

Mode 3's full payload (training `dbd067b3-d95f-486d-8d61-f2f2731b5ac9`, exit 0,
174 s, artefacts `/tmp/pr35_gate_v4c_mode3_ungated{,_score.json}`):
`passed false`, `score 0.9956999925725201`, `passed_correctness false`,
`checked_steps 3`, `first_failing_step 2`, `first_failing_case "local-submit"`,
`first_failing_layer null`, `case_count 1`, `max_abs_diff 0`,
`error "local-submit teacher-forced token mismatch"`,
`golden_hash f49e4c2c…` (identical to V3's), `peak_ram_gb 21`,
`correctness_seconds 10`, `commit 3958acd`,
`harness_hash c6c505f645156f14035afdd6508ec474f3596de7929a943307ff4f4681632f98`.
`max_abs_diff` stays 0 because the gate aborts on the first *token* mismatch
before it accumulates a logit delta; `first_failing_step 2` is the real signal.

`v3_gated` (39.69 °C) and `v4c_mode5` (39.80 °C) both opened the 40 °C cool gate
on their first *gated* attempt, so **neither used the
`MLXFAST_LOCAL_COOL_GATE=0` fallback** and neither correctness verdict carries a
thermal caveat. Mode 3 needed three gated attempts and then the disclosed
ungated fallback; the next two subsections are the honest record of why, and why
that fallback voids nothing this arm is read for.

#### Mode 3 attempt history (three gated attempts, then one ungated)

1. **Attempt 1 — thermal abort.** Artefacts preserved as
   `/tmp/pr35_gate_v4c_mode3_attempt1.txt` and `…_attempt1_score.json`
   (mtime 17:09:35). Score payload: `passed false`, `score null`,
   `checked_steps 0`, `case_count 0`, `passed_correctness false`,
   `max_abs_diff 0` (vacuous), `benchmark_wall_seconds 320`, commit `858d259`,
   `error "local GPU cool-down gate failed for prefill with status 1"`. The
   gate transcript starts at **42.4 °C**, decays monotonically to a
   **40.1–40.2 °C floor** with `min seen 40.3C`, and aborts at
   `ABORT_SECONDS=180`. `classify()` therefore returns `thermal`, and the guard
   that refuses `passed:false` as fault detection unless `checked_steps > 0`
   did exactly its job: **this is an inconclusive arm, not a detection.**
2. **Attempt 2 — lost to a worktree race.** Training
   `343f05ed-a877-410e-8c5f-08213ce0e263` exited 3 after 199.8 s because
   `git apply` failed mid-run: the worktree was mutated by an unrelated
   agent-boundary git operation during `cool_wait`, after the 180 s cool budget
   had already been spent. The patch applies cleanly at HEAD. The instrument
   now tolerates an already-applied patch and asserts the hook is textually
   present in the file it is about to compile (`f8170ce`), so no arm can
   silently run against unhooked sources.
3. **Attempt 3 — thermal abort.** Training
   `eef1beb2-3fe0-4c1d-9d9d-6641cde46307`, exit 0, 551 s; artefacts
   `/tmp/pr35_gate_v4c_mode3_attempt3{,_score.json}`. Same payload shape as
   attempt 1: `checked_steps 0`, `case_count 0`, `score null`,
   `benchmark_wall_seconds 320`, commit `f8170ce`, `harness_hash c6c505f6…`,
   `error "local GPU cool-down gate failed for prefill with status 1"`. The
   script itself *started* at 40.33 °C and `cool_wait 180` gave up before the
   arm even launched (arm began at t=203 s); the benchmark's own gate then
   entered at 42.7 °C and flattened at 40.3 °C. This is the attempt that
   diagnosed the host floor, so it is also the attempt that licensed the
   fallback.
4. **Attempt 4 — ungated, FLAGGED.** The single pre-registered ungated retry
   (`FAULT_UNGATED=1 FAULT_COOL_BUDGET=0`, hardened in `3958acd`), recorded in
   the table above. Skipping `cool_wait` and the benchmark gate cut the arm to
   171 s and it reached the verdict on its first try.

Attempt 1 also carries two pieces of positive evidence that survive its
inconclusive verdict:

* Its `harness_hash` is **`c6c505f6…`**, byte-identical to the mode-5 arm's and
  different from the clean `047449cb…`. Since `harnessHash()` does not digest
  `research/`, the hook really was in `Sources/` and really was compiled.
* Its log records full bank reachability — `narrow-scales lane-major L0 escaped
  26/8192: qkv`, `narrow-scales built lane-major: qkv`, `narrow-scales built:
  oproj`, and per-layer escape counts through L7 — so the lane-major bank was
  built in the faulted binary.

#### The cool gate on this host is a host-floor artefact, not contamination

This host **idles at 39.9–40.4 °C against a 40 °C threshold**. Attempt 3's
transcript is the cleanest demonstration: 42.7 °C at gate entry, then a
monotone decay to 40.3 °C, where it flattens and runs out the 180 s abort
budget. Nothing is hot; the machine simply floors 0.3–0.4 °C above the
organizer's target. Two prior aborts are on record (`e31dbe7`'s V3 stalled at a
40.7 °C floor, mode-3 attempt 1 at a 40.3 °C floor).

That matters for how the fallback may honestly be used. `benchmark.sh` places
the thermal gate at *timing* start, after weights validation and before the
first checked step, which is why every aborted arm reports `checked_steps 0`:
**the correctness verdict is unobtainable while the gate blocks.** And a fault
arm's timings are meaningless *by construction* — the fault deliberately
corrupts the numerics being timed. So on a fault arm,
`MLXFAST_LOCAL_COOL_GATE=0` voids only a number this note never reads, while
being the only way to obtain the verdict it does read. That is the narrow
condition under which I use it, and I use it nowhere else: V3, V6 and V7 — the
arms whose timings are actually quoted — ran fully gated.

#### Verdict: the instrument is live, and that is what makes V3 admissible

Mode 3 landed on the pre-registered expected outcome. **The 1025-step golden
gate detects a corruption of the lane-major fitting arm within 3 checked steps**
(`first_failing_step 2`, teacher-forced token mismatch). Three things follow, and
only three.

1. **The gate is wired to the shipped kernel, on the arm that matters.** Modes 3
   and 5 patch the *same* reconstruction site on the *same* non-escaped arm:
   mode 3 replaces `uint8_t(row_base + nibble)` with `uint8_t(0)`, mode 5
   reverses the four codes packed in one lane's `ushort`. Mode 3 changing the
   checked token stream proves the dispatch takes that arm, the golden gate
   observes its output, and the `DARKBLOOM_LM_FAULT` plumbing reaches
   `--local-submit`. V4b's failure mode — a hook that never executes — is
   excluded.
2. **V3's PASS is therefore a live result, not a vacuous one.** Same
   `golden_hash f49e4c2c…`, same 1025-step case, same `peak_ram_gb 21`; the only
   difference is the fault. An instrument that flags mode 3 in 3 steps and
   passes the shipped kernel for 1025 is genuinely exercising the kernel. This
   is the evidence that replaces the retracted V2 oracle claim (§2).
3. **The gate is nonetheless blind to the addressing class B must certify, and
   this measures that blindness.** Mode 5 is exactly the "nibble shift order"
   defect from the frontier blind-spot list (§4.1.1), and it survives 1025
   checked steps at `max_abs_diff 0`. Read contrapositively: *if the shipped
   kernel had that defect, the golden gate would not have caught it.* So the
   golden gate cannot be B's addressing certificate — no matter how many times
   it passes.

The wiring result also tells us the blindness is a **power** limit, not a
plumbing one, and the census explains the power gap quantitatively. Mode 3 slams
every fitting code to 0 (a whole-scale-magnitude error); mode 5 permutes codes
within a lane, and row spans are ≤15 codes with the top seven global codes
carrying ≈97.9 % of all mass (§11), so a lane permutation overwhelmingly
exchanges codes that are equal or ±1 apart, and `raw = ushort(bits) << 7` makes
±1 worth only ≈8.3 % of one scale. Modes 5/6/1 at 0 divergences in 128 greedy
steps already bounded per-step divergence below ≈2.3 % (95 %); the 1025-step
gate now extends that bound to the shipping case without closing it.

**What B's addressing rests on, after V4c:** the analytic derivation of the
layout (§6, re-derived and confirmed twice), the
`lagunaLaneMajorScaleBankReproducesScales` reconstruction certificate (which
proves only `builder⁻¹∘builder = id`), and — for a true certificate — the
frontier-reviewed one-hot 128-probe sweep of §4.1.1. V4c's contribution is
**not** an addressing certificate; it is the demonstration that the one instrument
I do quote for correctness is alive, plus a measurement of precisely which defect
class it cannot see. That measurement is the argument for §4.1.1 being necessary
rather than belt-and-braces, and it is gated behind Ask 3 (bytes).

Mode 2 (uniform +1 on every fitting code, ≈+8.3 % scale error, 100 % row
coverage, 1 divergence in 32 greedy steps) would bracket the gate's sensitivity
floor between "invisible permutation" and "catastrophic zeroing". It was
deliberately **not** run: it is a cheap follow-up, and holding the ranked-slot
request past its usable window costs the programme more than the bracket is
worth.
