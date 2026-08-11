# N-NORM-QKV-FUSION-ALREADY-SHIPPED-AND-DEAD

**Response to advisor feedback `r116-a-tau-filter-and-fusion-kill`** (2026-08-11T01:54:41Z), §3.
**Student** maple-tanjiro. **PR** #692, revision `r110-a-rev4`. **Host** Mac16,11 M4 Pro, GPU gen 16.
**Submitted surface: untouched.** A2 in `matmul.cpp` remains frozen exactly as the advisor left it.

## 0. Timing note, so the record is unambiguous

The kill notice landed at 01:54:41Z. My Stage 0 terminal result posted at 01:59:15Z, four minutes
later, and was written before I had read it. The two were produced independently. **They agree**,
and the independence is worth something: nezuko reached the kill by excavation, I reached it by
measurement, and neither of us saw the other's work.

The one thing that changes as a result of the feedback is that I am **not** building the Stage 1
NVFP4 variant. That was already my recommendation; it is now also an instruction. Nothing to unwind.

---

## 1. The three checks, exactly as requested

### (a) The guard

`Sources/MLXFastModel/LagunaRuntimeModel.swift:5926-5932`, verbatim:

```swift
if lagunaFusedNormAffineQKVEnabled,
    fusedAffine.mode == .affine, fusedAffine.bits == 8,
    fusedAffine.groupSize == 32,
    _nativeAffineQKVGateRows == nHeads,
    inputNorm.eps == Float(LagunaConstants.rmsNormEpsilon),
    let affineBiases = fusedAffine.biases
{
```

`lagunaFusedNormAffineQKVEnabled` (`:5482-5483`) is `env["DARKBLOOM_FUSED_NORM_AFFINE_QKV"] != "0"`,
so the fusion is **default ON**. The binding conditions are `mode == .affine`, `bits == 8`,
`groupSize == 32`.

### (b) The bank's actual format

`lagunaNativeAffineNVFP4From` (`:3048-3054`) returns non-nil unless
`DARKBLOOM_NATIVE_AFFINE_NVFP4 == "0"`, i.e. **non-nil by default**, which selects the NVFP4 bank
for Q/K/V. That bank is `(mode: .nvfp4, groupSize: 16, bits: 4)`.

```
guard requires   mode == .affine   bits == 8   groupSize == 32
shipped bank is  mode == .nvfp4    bits == 4   groupSize == 16
                 ^^^ fails         ^^^ fails   ^^^ fails
```

All three bind conditions fail, on **every layer of every step**. Control falls to
`let normalized = fusedQKV ?? inputNorm(input)` (`:5947`) and then `lagunaDecodeNVFP4QKVR1`.

### (c) Zero dispatches, in my own SPLIT=1 profile at shipped defaults

`research/maple-tanjiro-r110/stage0-evidence/N.log`, arm **N** = no environment overrides =
exactly the ranked configuration. 199 steady steps, 406 dispatches/step, full kernel census:

```
$ grep -ci "norm_affine_qkv\|normaffineqkv" stage0-evidence/N.log
0
```

**Zero.** The census instead shows the unfused pair the advisor predicted:

| kernel | n/step | us/step |
|---|--:|--:|
| `decode_nvfp4_qkv_h64_r1_v1_lm1_pw1_se1_sd1` | 30 | 1344.2 |
| `decode_nvfp4_qkv_h48_r1_v1_lm1_pw1_se1_sd1` | 10 | 363.8 |
| `rmsbfloat16` | 41 | 142.1 |

40 QKV projections + 40 per-layer input norms (the 41st `rmsbfloat16` is the final norm), as
separate dispatches, every step. **Confirmed: `lagunaNormAffineQKV` is shipped, default-ON, and
provably dead code on the ranked configuration.**

---

## 2. Why Stage 0 was nevertheless not void — and what it bought

The feedback's step 2 says "if it reproduces, your Stage 0 as briefed is **void**." It reproduces,
but Stage 0 was **not** void, for a reason worth recording as method.

Dead code has an unknown price, and "it never runs" does not tell you whether reviving it is worth
doing. The guard is satisfiable **without touching the submitted surface**, by flipping the bank
with `DARKBLOOM_NATIVE_AFFINE_NVFP4=0` (`:3049`), which falls through to
`quantized(source, groupSize: 32, bits: 8, mode: .affine)` at `:3115-3123` — group-32 affine INT8
for Q/K/V/O, which is precisely the permitted re-quantization envelope (`TASK.md:78-94`). So the
fusion can be made to fire, legally, and its price can be read directly.

That converts "we don't know" into a number. The measured result (32-run paired ABBA, both arms in
one binary and one bank so the bank cost cancels exactly):

| arm | us/step |
|---|--:|
| **F** fused (`NVFP4=0`) | 11638.1 |
| **U** unfused (`NVFP4=0`, `FUSED_NORM_AFFINE_QKV=0`) | 11620.9 |
| **F − U** | **+17.2** (fusion slower) |

95% CI [+9.0, +25.3] at k=4x8 blocks; Mann-Whitney U=209.0, z=+3.05, p~0.002. Bit-exact:
0 divergences over 35 independent 200-step teacher-forced runs.

So the kill is not merely "the guard fails". It is **"the guard fails, and the thing behind the
guard is slower than what replaced it, measured."** Those are different strengths of claim, and the
second one closes the axis permanently rather than leaving it as an untested lever.

---

## 3. Am I in nezuko's rung-1a family? Yes. I am not claiming a difference.

The feedback offers an escape hatch: proceed if my mechanism "does not make a narrow reduction the
sole producer for a wide consumer" (`N-SOLE-PRODUCER-WIDTH-RATIO`). **I am not taking it.** It is
the same family, and saying otherwise would be motivated reasoning.

The fused kernel computes the RMS reduction over the 2048-wide residual *inside* each QKV
threadgroup. The int8 fusion runs 8 rows/threadgroup (`:5536-5542`), so with 2048 output rows it
replicates that 2048-element reduction once per threadgroup instead of once per layer. That is
exactly a narrow reduction becoming the sole producer for a wide consumer. My §6 SPLIT=1 accounting
names it as one of two candidate explanations for the 101.6 us/step give-back and, honestly, does
**not** separate it from the alternative (that the hand-written fused matvec is simply worse than
MLX's tuned `affine_qmv_fast`). Nezuko's law supplies the missing mechanism; I supply the price.

**Conclusion: the kill stands on its merits, not merely on authority. Stage 1 is not built.**

---

## 4. Reconciling +17.2 with +560 us/step — they are not in conflict

At face value my +17.2 us/step and nezuko's ~+560 us/step (−3.9%) differ by 33x. They are measuring
**different objects**, and the gap is itself informative.

| | what it prices | bank | rows/TG | reductions/step |
|---|---|---|--:|--:|
| **mine, measured** | the *shipped* `lagunaNormAffineQKV` as written | int8 g32 | 8 | 40 x 256 TGs |
| **nezuko's** | an NVFP4 *port* of the same construction | NVFP4 g16 | 2 | 40 x 1024 TGs |

`lagunaDecodeNVFP4QKVR1` (`:5002-5064`) runs **2 rows/threadgroup** against the int8 fusion's 8, so
an NVFP4 port replicates the redundant RMS reduction **4x more often** for the same output — against
a prize (76.5 us/step) that is the same size on either bank.

My §7 predicted this from geometry alone, before I had seen her number: *"the same construction on
NVFP4 starts from a strictly worse redundancy ratio... there is no reading of these numbers under
which the NVFP4 port clears the bar."* Her measurement lands in exactly the predicted direction and
is far past the bar. **A 4x worse redundancy ratio turning a +17 us loss into a +560 us loss is
super-linear, which is what you would expect once the replicated reduction stops hiding under the
matvec and starts dominating it.** Two independent methods, same verdict, and the quantitative gap
between them is explained by the one structural parameter that differs.

---

## 5. The prize, repriced under the corrected score law

The feedback corrects the pricing to `%score = 0.75 x tau x delta_us / 8972` = **0.0084 %/us at
tau = 1**, with **tau ~ 1.06** for changes that remove real executed work. Removing 40 genuine
RMSNorm dispatches and their DRAM traffic is real work removal, so tau = 1.06 applies:

```
theoretical ceiling (all 40 norms free)  77.4 us/step -> 0.0084 x 1.06 x 77.4 = +0.69 % of score
what the shipped fusion actually does   -17.2 us/step -> 0.0084 x 1.06 x -17.2 = -0.15 % of score
Stage 1 bar (+0.25 % of score)                        -> 0.25 / (0.0084 x 1.06) = +28.1 us/step
```

Two notes. First, the bar **tightens** from the +35.7 us/step I used (which came from the older
0.0070 %/us rate) to **+28.1 us/step**. The verdict is unchanged because the observed sign is
wrong — the most fusion-favourable 95% bound at any block length is +2.7 us/step, so the arm misses
even the tightened bar by more than 10x.

Second, and worth flagging: the ceiling is **+0.69% of score**, which under the campaign's own
P@20 table would be worth more than +25pp. **This axis is valuable and the current implementation
is the thing that is broken, not the idea.** What it would take is stated in §7 of the below-bar
doc: a threadgroup-cooperative single-pass reduction, or restructuring
`lagunaDecodeNVFP4QKVR1` to 8 rows/TG — new kernels with their own correctness surface, not a port.
I am recording that as a **reopen condition**, not a live lever: reopen only if someone is prepared
to write a genuinely different reduction structure, and only with a paired ABBA interval up front.

---

## 6. One honest tension in the tau table, flagged rather than buried

The tau table assigns **tau ~ 0 to threadgroup geometry**. A2 — the arm on this PR's head, which
the advisor is firing — *is* a threadgroup-geometry change (fused-NAX `bn` 128 -> 64 for N <= 1024).
Read literally, the table prices A2 at zero.

I do not think that reading is correct, and here is the distinction, offered for the advisor to
accept or reject rather than assumed in A2's favour:

- The tau ~ 0 constant was measured on the **decode** axis, on kernels that already fill the
  machine. Retiling a saturated dispatch moves work between cores that were all busy anyway, so
  zero is the expected result and PR #7 (+7.32% M4, ~0% M5) is the canonical case.
- A2's entire rationale is that its dispatch is **under-filled** — 64 threadgroups on a 40-core M5,
  ~1.6/core, with a large second-wave tail — which is the documented exception to the geometry ban
  and a regime where occupancy, not work placement, is the binding constraint.

So the tau ~ 0 constant is, I believe, measured in the saturated regime and does not obviously bind
in the under-filled one. But this is an argument, not a measurement, and it is **unresolved on this
host by construction**: A2 is `_nax`-gated, this host is GPU gen 16, `is_nax_available()` is false,
so no local experiment can distinguish the two readings. The receipt on the raw prefill leg is the
only instrument that can. I am recording the tension so that, whichever way the receipt falls, the
tau table gets updated with a regime qualifier rather than being quietly contradicted.

**A2 remains untouched.** Preregistered read rule, restated so it is durable in-tree:

```
d = 100 x (187.8728 - p_A2) / 187.8728      # p_A2 = candidate prefill_seconds_per_token, RAW, in us
d >= +0.46 %  => confirmed
|d| <  0.46 % => inconclusive
d <= -0.46 %  => refuted, revert
```

Read on the raw candidate prefill leg only. Not on the score, and not on the paired ratio (pairing
makes the prefill instrument 9.28x worse).

---

## 7. Status against the stopping rule

| checkpoint | state |
|---|---|
| 02:15Z Stage 0 paired ABBA + SPLIT=1 kernel table | **delivered** (posted 01:59:15Z, ahead of time) |
| 05:30Z Stage 1 arm, or below-bar write-up | **closed** — `N-NORM-QKV-FUSION-BELOW-BAR` + this note. Stage 1 not built, per §3 |
| A2 on head | **frozen**, advisor fires |
| 10:30Z terminal | on track |
