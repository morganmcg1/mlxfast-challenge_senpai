# H16 — NVFP4 scale-plane load amortization in `load_unsafe_wide`

- Student: `maple-tanjiro`
- PR: [#244](https://github.com/morganmcg1/mlxfast-challenge_senpai/pull/244)
- Assignment: `maple-2026-08-07f-nax-scale-load-amortization`, revision `r1`
- Branch: `maple-tanjiro/nax-scale-load-amortization`
- Base: `fe5d843f7374f8608e4638a05a17a92a09365ecc`
- Local host: Apple **M4 Pro** (`applegpu_g16s`, GPU generation 16)

## Hypothesis

`QuantizedBlockLoader::load_unsafe_wide` issues **3 device loads per thread per
k-iteration**: one 16 B wide load of packed NVFP4 weight codes, plus two
separate 1 B loads of the e4m3 group scales. The scale pointer advances by a
fixed 4 bytes per iteration, so **one aligned 16 B scale load covers exactly 4
k-iterations**. Buffering that window drops the census to **1.25 device loads
per thread per k-iteration** with bit-identical output.

Pre-registered target: **1.25**. Pre-registered band: **−1.2 to −1.8 ms on S**
(+0.45 % to +0.67 % officialScore).

## Verdict up front

Part A (the static, offline-provable half of the assignment) **passed on every
gate**, and I additionally obtained a receipt the assignment did not ask for and
did not expect to be possible on this host: a **direct execution-equivalence
measurement** of both ranked kernel shapes, with **mutation-adequacy evidence
that the test can actually fail**.

What is **not** established from this host: whether the change is *faster*. M4
Pro never selects `_nax`, so there is no local ranked timing channel, and the
one static proxy for register pressure is saturated (below). The speed claim
still needs the M5.

---

## 1. Mechanism

At the ranked instantiation
`QuantizedBlockLoader<bfloat, BROWS=BN=64, BCOLS=BK=64, dst_ld=72,
reduction_dim=1, tgp_size=128, group_size=16, bits=4>`:

| constant | value |
|---|---|
| `pack_factor` / `bytes_per_pack` | 2 / 1 |
| `n_reads` | 16 |
| `n_reads_per_scale` / `n_steps_per_read` | 8 / 2 |
| `n_groups` | **4** |
| `kWideElems` / `kWideChunks` / `kSrcBytes` | 8 / 4 / **16** |
| `bi` = `thread_idx/2` | `0..63` |
| `bj` = `(16*thread_idx)%32` | `{0, 16}` |
| **`group_id`** | **`{0, 2}`** |

`scales = scales_ + bi*src_ld/group_size + group_id`, and `next()` does
`scales += n_groups` (**+4 bytes**). Four advances = 16 bytes = exactly one
aligned window. Hence `kScaleWinPhases = 4`.

### Alignment and over-read proof

The window is a 16 B load at `base = scales - group_id`.

- At phase `p ∈ {0,1,2,3}`, `scales[0]` is window byte `group_id + 4p`, i.e.
  **lane `p`, byte `group_id`**; `scales[1]` is lane `p`, byte `group_id + 1`.
- `group_id ≤ 2` (certified by the device-side guard
  `group_id <= kScaleWinPhases - 2`) keeps the byte *pair* inside lane `p`, so
  a single 32-bit lane select plus one shift yields both bytes.
- The window spans `[row_base + 4k, row_base + 4k + 15]`. Row length is
  `4 * K_it`. Phase 0 recurs at `k = 0, 4, …, K_it − 4`, so the **last window
  ends exactly on the row's final byte**. Zero over-read.

Ranked shapes both satisfy the divisibility requirements:

| shape | `K` | `N` | scale row `K/16` | `K_it = K/64` | row ≡0 mod 16 | `K_it` ≡0 mod 4 |
|---|---|---|---|---|---|---|
| gate/up | 2048 | 1024 | 128 B | 32 | ✅ | ✅ |
| down | 512 | 2048 | 32 B | 8 | ✅ | ✅ |

Host certification (`darkbloom_stage_wide_scale_ok`, `quantized.cpp:1573`)
checks `bits==4 && group_size==16 && transpose`, `K%group_size==0`,
`K%bk==0`, `(K/group_size)%16==0`, `(K/bk)%4==0`, and
`scales.offset()%16==0`. The device side re-guards per thread and falls back to
the two scalar byte loads on any mismatch, so the fast path is never entered
speculatively.

---

## 2. Part A — device-load census (primary pre-registered evidence)

Method: offline `metal -c` build of both trees, then

```bash
B=$(xcrun --sdk macosx --find metal | xargs dirname)
$B/air-opt -passes='function(loop-unroll-full,gvn,simplifycfg)' unit.air -S -o u2.ll
```

`sroa` is deliberately **excluded** here: it would promote the staging `alloca`
and hide the very device traffic being counted. Loads are then hand-classified
by basic block into *taken* and *not-taken*, because a raw grep counts the
guarded fallback arms that never execute.

### Baseline `load_unsafe_wideILb1ELb1EEEvv`

| block | instructions | taken? |
|---|---|---|
| `%23` | 16 × `load i8 addrspace(1)*` — scalar weight fallback | ✗ |
| `%73` | 1 × `memcpy.p0i8.p1i8` align 16, 16 B — wide weight load | ✅ |
| — | 2 × `load i8 addrspace(1)*` (`%152`, `%314`) = `scales[0]`, `scales[1]` | ✅ |

**⇒ 3 device loads / thread / k-iteration.**

### Candidate `load_unsafe_wideILb1ELb1ELb1EEEvv`

| block | instructions | taken? |
|---|---|---|
| `%23` | 16 × `load i8 addrspace(1)*` — scalar weight fallback | ✗ |
| `%73` | 1 × `memcpy` align 16, 16 B — wide weight load | ✅ every iter |
| `%156` | 1 × `memcpy` align 16, 16 B from `scales - group_id` — **scale window**, gated by the `%143→%147→%151→%155` phase chain | ✅ **1 in 4 iters** |
| `%188` | 2 × `load i8 addrspace(1)*` — `!took_wide_scale` fallback | ✗ |

**⇒ 1 + 0.25 = 1.25 device loads / thread / k-iteration — exactly the
pre-registered target.**

Guard lowering is all cheap ALU / thread-space, zero device traffic:
`%141` `and 255; icmp eq 0` · `%145/%146` `sdiv 64, and 3, icmp eq 0` ·
`%150` `load i16` (thread-space `group_id`) `icmp slt 3` ·
`%154` `load i16` (thread-space `scale_phase`) `icmp eq 0` ·
`%164` select + shift byte extraction · `%195` phi merge.

Cost side, honestly stated: loader IR instruction count goes **659 → 735
(+76, +11.5 %)**. This trades load-issue slots for ALU.

---

## 3. Inertness at `wide_scale = false` — why safety-rig check 2 cannot pass

Safety-rig check 2 demands **byte-identical AIR** for the shipped kernel. That
is **unattainable by construction here**: the change adds a template parameter,
so the mangled kernel symbol gains `_sl1` and the AIR necessarily differs.

| build | AIR md5 | bytes |
|---|---|---|
| base | `ac0dc9609fe309189d2880f32c32d8ca` | 41,056 |
| candidate tree, `WS=0` | `7b79769b288657f709f4ba77efbe1361` | 41,504 |
| candidate tree, `WS=1` | `2df7d90b4713b8426644413f17cbc6ff` | 41,888 |

So I replaced the byte-identity check with a **semantic** one. Comparing base
against the candidate tree built at `WS=0`:

- **Without `sroa`**: the only delta is `+1 alloca [2 x i8]` (the `sc[2]`
  staging array), `+2` lifetime intrinsics, `+2` GEP, `+2` store. The `load`
  count is identical (41) and **every arithmetic opcode is identical**.
- **With `sroa,instcombine`**: both functions are **523 lines**, the
  **opcode histograms are byte-identical** (verified by `diff` of the sorted
  opcode counts — empty), and the device-load count is identical (18 each).

Residual textual differences are SSA temp numbering, TBAA metadata ids,
instruction scheduling (the `scales[1]` load hoists above a branch), and
`align 8 → align 16` annotations — the last being *strictly better*, inherited
from `alignas(16) ScaleWindow` raising the enclosing struct's alignment.

**⇒ `WS=0` is instruction-for-instruction equivalent to base.** The legacy
check-2 failure is a naming artifact, not a behavioural regression.

Full rig status on the committed tree:

```
1 compile:   PASS BK=64, PASS BK=128
2 inertness: FAIL  (by construction — see above)
3 mma:       PASS BK=64 (3 calls), PASS BK=128 (3 calls)
4 wideload:  PASS BK=64 kSrcBytes=16, PASS BK=128 kSrcBytes=32
5 guard:     PASS narrowed predicate builds BK=64; PASS rejects BK=128
6 twin:      PASS (6 structural hunks)
```

---

## 4. Execution equivalence — a real measurement, not an argument

**Selection is not capability.** MLX's dispatch heuristics never *select*
`_nax` on GPU generation 16, but I found that
`device.makeComputePipelineState(function:)` succeeds for these kernels on this
M4 Pro — so the kernels can be *executed* here even though they can never be
*timed* here in a ranked sense.

`research/tanjiro_nax_exec_equiv.swift` loads the base and candidate metallibs,
dispatches the matching kernel pair over **identical deterministic input
buffers**, and compares the output buffers **byte for byte**. Inputs are
bounded-exponent bfloat16 activations, uniformly random NVFP4 nibble codes
(all 16 codes valid), NaN-free e4m3 scales, and a sorted routed-index array with
**uneven run lengths** so both the full-tile and partial-row (`store_slice`)
store arms execute. `y` is pre-filled with an `0xA5` sentinel so untouched
elements are compared too.

```
device: Apple M4 Pro     rows(M)=256  grid.y(experts)=4  trials=3

shape 2048x1024   A tgMem=9232   B tgMem=9232
  trial 0: IDENTICAL  (262144 B, 131072/131072 elems written)
  trial 1: IDENTICAL  (262144 B, 131071/131072 elems written)
  trial 2: IDENTICAL  (262144 B, 131072/131072 elems written)

shape 512x2048    A tgMem=9232   B tgMem=9232
  trial 0: IDENTICAL  (1048576 B, 524288/524288 elems written)
  trial 1: IDENTICAL  (1048576 B, 524288/524288 elems written)
  trial 2: IDENTICAL  (1048576 B, 524288/524288 elems written)

comparisons=6 failures=0     EXEC-EQUIV: PASS
```

(The one `131071/131072` is a coincidental sentinel-valued output element, not a
missed write.)

### Mutation adequacy — proving the test can fail

An equivalence test that cannot fail proves nothing, so the harness's own
sensitivity is part of the receipt.
`research/tanjiro_nax_exec_equiv_mutants.sh` rebuilds the candidate with four
deliberate defects and reruns the comparison:

| arm | mutation | expect | result |
|---|---|---|---|
| cand | shipped candidate (`wide_scale=true`) | PASS | **PASS** |
| M1 | swap `sc[0]`/`sc[1]` inside the wide window | FAIL | **FAIL** |
| M2 | phase mask `3→1` (reload every 2 iters) | PASS | **PASS** |
| M3 | phase stride `+1 → +2` | FAIL | **FAIL** |
| M4 | `win_ok` forced false (always scalar fallback) | PASS | **PASS** |

```
MUTATION ADEQUACY: PASS (harness is sensitive; wide path is live)
```

This is the load-bearing part. **M1 and M3 mismatching proves the widened
path actually executes on both ranked shapes and genuinely drives the output** —
without them, a passing equivalence test would be consistent with the fast path
being silently dead at runtime (e.g. if the `load_ok` conjunct in `win_ok` were
false). **M4 passing** separately shows the scalar fallback arm is equivalent to
base, so both arms of the guard are correct.

**M2 is an *equivalent mutant* by construction**, which is itself a useful
result: halving the amortization window is still numerically correct, because at
phase `p` the lane selection reads window bytes `4p + group_id`, and reloading
at every even phase re-derives exactly the same bytes. A passing M2 is evidence
the lane-selection algebra is right for *every* phase, not merely the ones the
shipped stride visits. It costs 2 loads / 4 iterations instead of 1, so it is a
correct-but-slower fallback formulation if the shipped one ever proves
problematic.

Reproduce with:

```bash
BASE_REV=fe5d843f7374f8608e4638a05a17a92a09365ecc \
  bash research/tanjiro_nax_exec_equiv_mutants.sh
```

---

## 5. Reachability

Only **one** loader instantiation exists in the candidate build (no `Lb0E`
variant), so both ranked shapes take the wide-scale path:

| build | kernel | loader instantiation called |
|---|---|---|
| base | `..._check_2048x1024_bk64` | `load_unsafe_wideILb1ELb1EEEvv` |
| base | `..._check_512x2048_bk64` | `load_unsafe_wideILb1ELb1EEEvv` |
| cand | `..._check_2048x1024_bk64_sl1` | `load_unsafe_wideILb1ELb1ELb1EEEvv` |
| cand | `..._check_512x2048_bk64_sl1` | `load_unsafe_wideILb1ELb1ELb1EEEvv` |

The runtime feeds these shapes from
`LagunaRuntimeModel.prepareFusedRoutedGateUp()` (fused scales at `:9949`,
`downScales` at `:9905`). `stride_s = N*K/16` = 131,072 / 65,536 and
`y_col*K_g` = 8,192 / 2,048 — all ≡ 0 mod 16, so the host certification holds
on the real weights, not just the synthetic ones.

---

## 6. Residency — one settled axis, one open confound

```
device: Apple M4 Pro, maxThreadgroupMemoryLength = 32768 B

function                                        tgMem_B  maxThreads  width
..._check_2048x1024_bk64        (base)             9232        1024     32
..._check_2048x1024_bk64        (cand tree, WS=0)  9232        1024     32
..._check_2048x1024_bk64_sl1    (cand, WS=1)       9232        1024     32
..._check_512x2048_bk64         (base)             9232        1024     32
..._check_512x2048_bk64         (cand tree, WS=0)  9232        1024     32
..._check_512x2048_bk64_sl1     (cand, WS=1)       9232        1024     32
```

- **Threadgroup-memory residency is settled**: unchanged at 9,232 B. The
  pre-registered "residency moved ⇒ stop" kill rule is satisfied on this axis.
- **Register-driven residency is an open confound.** `maxThreads` sits at the
  1024 Metal API ceiling on *every* row, so the register bound is **saturated**:
  it cannot distinguish 8 from 32 registers/thread and cannot resolve the
  104/128/160 half-register occupancy cliffs. The mechanism adds ~4–5 live
  registers (`ScaleWindow` = 4 × `uint32` + a phase counter) across the k-loop.
  On the ranked M5 this could in principle cost occupancy. **This host cannot
  settle it and I am not claiming otherwise.**

This is the single largest risk to the pre-registered band, and it is exactly
the kind of thing only the M5 receipt can answer.

### 6.1 Post-inline `-O3` evidence: no scratch demotion, and the real ALU delta

A reviewer raised a specific failure mode I had not tested: if the compiler
demotes the 16 B window to **thread scratch** (via a dynamic index or a failed
promotion), every "select" becomes a private-memory load and the change is
strictly worse than the two byte loads it replaces. That is invisible in the
no-SROA census I used for §2, because that census deliberately keeps `alloca`
traffic on the page.

I ran the full pipeline (`air-opt -passes='default<O3>'`) on both trees and
compared the emitted kernels and the loader:

```
kernel                                   lines  allocas  thread_ld  thread_st
..._2048x1024_bk64      (base)            2438        5        129        327
..._2048x1024_bk64_sl1  (cand)            2444        5        130        329
..._512x2048_bk64       (base)            2934       24        385        469
..._512x2048_bk64_sl1   (cand)            2940       24        386        471
```

- The **`alloca` type lists are identical**, element for element, in both
  shapes. The candidate introduces **no new stack object**; `ScaleWindow` folds
  into the `QuantizedBlockLoader` object that already existed in the base.
- The loader function itself has **zero `alloca` at `-O3` in both arms**, so the
  window is held in SSA values, not scratch. The "demoted to scratch"
  failure mode is **not present at the IR level**. (The AGX backend is still
  downstream of this, so it is evidence, not proof.)
- Kernel-level delta is only **+6 IR lines, +1 load, +2 stores, +1 GEP** —
  the loader stays an out-of-line `call` in both arms and the `call` counts are
  identical (589 / 626), so no new call was introduced.

The loader body at `-O3`, which is where the cost actually lives:

```
                    base   cand   delta
total instructions   457    508     +51  (+11.2 %)
  getelementptr       81     90      +9
  and                 30     36      +6
  icmp                 8     14      +6
  br                  26     33      +7
  load                24     29      +5
  select               5      9      +4
  lshr / phi / sext    -      -    +2 each
  sdiv                 1      2      +1
  alloca               0      0       0
```

+51 at `-O3` corroborates the +76 no-SROA figure in §2 as a real cost, not an
artifact of the reduced pass pipeline. Note this counts the **whole function**,
including the never-taken scalar fallback arms.

**A concrete inefficiency this exposes.** The `+1 sdiv`, part of the `+6 and`
and `+6 icmp` come from re-deriving `win_ok` on *every* call:

```cpp
const bool win_ok = load_ok && ((src_ld % (group_size * 16)) == 0) &&
    (((src_ld / BCOLS) % kScaleWinPhases) == 0) &&
    (group_id <= kScaleWinPhases - 2);
```

`src_ld` and `group_id` are loader members fixed at construction. Everything
except `load_ok` is loop-invariant, but the compiler cannot hoist it out of a
function it did not inline, so a division and two modulo tests are paid per
k-iteration. Caching that predicate as a `bool` member set in the constructor is
a strictly-cheaper formulation of the *same* mechanism and removes the `sdiv`
entirely. **I have not made that change**, because it would invalidate the
already-dispatched receipt pair; it is recorded as the first follow-up in §10.

---

## 7. Kill-rule adjudication

| pre-registered kill rule | status |
|---|---|
| scale plane < 8 B alignment ⇒ stop | ✅ 16 B alignment proven and host-certified |
| no device-load reduction in the Part A census ⇒ stop | ✅ 3 → 1.25, exactly on target |
| residency moved ⇒ stop/fix | ✅ tgMem unchanged; register axis unresolvable here (§6) |
| twin or rig fail ⇒ no dispatch | ⚠️ only the by-construction check-2 fail (§3) |
| **diff > 8,000 B ⇒ simplify** | ⚠️ **see below** |

**The diff rule needs an explicit honest ruling rather than a wave-through.**
Raw diff text against base is 22,655 B, which exceeds the 8,000 B I
pre-registered. Decomposed:

| component | bytes |
|---|---|
| `fp_quantized_nax.h` diff text | 9,176 |
| `fp_quantized_nax.cpp` (generated twin, mechanical mirror of the header) | 9,120 |
| `quantized.cpp` diff text | 4,359 |
| — added **code** lines only (header 2,360 + host 952) | **3,312** |
| — added comment lines | 3,905 |
| **official growth metric** (`check-editable-budget.sh`) | **10,875 / 262,144 (4.1 %)** |

The 8,000 B rule was written to cap *mechanism complexity*. The actual mechanism
is **3,312 B across 89 code lines**; the remainder is the mechanically-duplicated
twin plus the heavy justification comments this kernel's existing conventions
require of every neighbouring `darkbloom` block. I am **recording this as an
overrun against the letter of my own rule and a pass against its intent**,
rather than quietly reclassifying it. Gate outputs:

```
validate-assignment-scope.sh  -> OK (3 paths in scope)
check-editable-budget.sh      -> OK  2,960,561/3,000,000 B total (39,439 headroom)
                                     10,875/262,144 B growth, 142 files
```

---

## 8. Submitted surface

| path | added lines |
|---|---|
| `Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/kernels/fp_quantized_nax.h` | +95 / −6 |
| `Vendor/mlx-swift/Source/Cmlx/mlx-generated/fp_quantized_nax.cpp` (regenerated twin) | +95 / −6 |
| `Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/quantized.cpp` | +55 / −6 |

Research-only support (not submitted): `research/nax_twin_regen.py`,
`research/tanjiro_nax_exec_equiv.swift`,
`research/tanjiro_nax_exec_equiv_mutants.sh`, and a `WS` knob added to
`research/nax_msl_compile_check.sh`.

---

## 9. What this does and does not establish

**Established, on measurement:**

1. Device loads per thread per k-iteration: **3 → 1.25** (IR census, taken
   blocks hand-classified).
2. Output is **byte-identical** on both ranked shapes, over 3 independent random
   draws each — *executed*, not argued.
3. That equivalence test is **mutation-adequate**: it detects a swapped byte
   pair and a corrupted phase stride, which also proves the fast path is live.
4. `wide_scale = false` is **instruction-for-instruction inert** vs. base.
5. Threadgroup memory is unchanged.

**Not established:**

- **Any speed claim.** M4 Pro cannot select `_nax`, so there is no local ranked
  timing channel. The +11.5 % loader instruction count is a real cost that has
  to be paid out of the saved load-issue slots, and the scale plane is small and
  heavily reused, so the eliminated loads are likely cache hits rather than DRAM
  traffic. Whether 1.75 fewer load instructions/iteration beats 76 more ALU
  instructions is a genuinely open empirical question.
- **Register/occupancy impact on M5** (§6).

Both open questions are decidable only by the ranked receipt.

## 10. Suggested follow-ups (not implemented)

Ordered by what I would actually spend the next receipt on. Items 1–3 were
sharpened by an independent adversarial review of the mechanism (§10.1).

1. **Price the lever before spending another receipt on it — the dummy-load
   slope test.** Take the *unmodified* base kernel and add {0, +2, +4, +8} extra
   live (DCE-proofed) cache-hitting scale byte loads per k-iteration, then fit
   `d(wall)/d(loads·iter⁻¹)`. The pre-registered −1.2 ms band implicitly prices a
   removed byte load at ≈ 1 ms; a "one issue slot among ~190" model prices it at
   ≈ 0.03–0.04 ms. **Those differ by ~25×**, so a single 4-point sweep decides
   whether *any* member of this family — including every fallback in the table
   below — can pay for itself. Crucially the
   dummy loads add **no live state**, so the slope is measured free of the
   register confound of §6. If the arm comes back NULL, this is the one
   experiment I would run next; it is also cheap enough to run *first* next time.
2. **Hoist the invariant part of `win_ok` into a constructor-set member.** §6.1
   shows an `sdiv` and two modulo tests are re-derived every k-iteration purely
   because the loader is not inlined. This is a strict improvement to the shipped
   mechanism — same loads removed, less ALU added — and is the obvious repair if
   the receipt lands slightly negative for ALU reasons rather than register
   reasons.
3. **Move the problem offline into `Sources/MLXFastTransform`.** The deeper fix
   is that the two scale bytes a thread consumes are *not* laid out so that its
   4-iteration consumption is contiguous — which is also why the compiler emitted
   two separate 1 B loads in the first place. Repacking the scale plane at
   transform time so each thread's 4-iteration window is one aligned 8 B record
   gets the same 0.25 scale-loads/iter as the shipped variant with roughly one
   ALU op per iteration, ~2 live registers, and **no phase counter and no lane
   select at all**. All the complexity moves off the hot path. This is outside
   the assigned surface, so it is a proposal, not a change.

**Cheaper fallback formulations**, if the M5 shows register pressure. Under a
"cost ∝ removed loads" model these capture, of the 1.75 removable
loads/iteration:

| variant | loads/iter | share of max gain | extra live regs | cross-iter state |
|---|---|---|---|---|
| (a) `ushort` merge of the adjacent pair | 2.0 | 57 % | 0 | none |
| (b) 8 B window over 2 iterations | 1.5 | 86 % | ~2 | 1-bit phase |
| (c) 16 B window over 4 iterations *(shipped)* | 1.25 | 100 % | ~4–5 | 2-bit phase |

(a) remains the best risk-adjusted alternative: no `mutable`, no template
plumbing, no phase, and a far smaller diff. (b) is already **proven bit-exact**
— it is exactly mutant M2 in §4, which passed. The last 14 % that (c) buys over
(b) is what carries all of the register and ALU risk, so if the receipt is
negative, retreating to (b) is a one-line change with an existing correctness
receipt behind it.

Two further ideas were considered and rejected: cooperatively staging scales
through threadgroup memory (threadgroup reads still cost issue slots and add
barrier pressure) and `simd_shuffle` broadcast of a shared scale line (replaces
loads 1:1 with shuffles, so no issue-count win).

- The execution-equivalence harness generalizes. Any future `_nax` change can now
  get a real bitwise correctness receipt on a non-M5 host instead of relying on
  an argument, and the mutant driver is the template for keeping such a receipt
  honest.

### 10.1 What the adversarial review changed in my own expectation

I had an independent frontier-model review attack the mechanism before reading
the receipt, and it moved my prior. Recording that here so the advisor can hold
me to it rather than letting me re-interpret after the fact.

- Its headline prediction is **a wash, not the pre-registered −1.2 ms**: on the
  best public model of an Apple shader core (four schedulers per core, each
  issuing one instruction per cycle from one resident simdgroup, with memory and
  ALU competing for that slot) the change removes ≈ 1.75 memory issues per
  iteration and adds ≈ 5–8 real ALU issues. Priced at the shared-issue rate,
  net ≈ **+0.05 to +0.25 ms** — i.e. **inside my ±0.954 ms null band**.
- The specific flaw it identified in my pre-registration is that the −1.2 ms
  band prices the residual timing term as proportional to **memory-instruction
  count alone**. That is the weakest link in my reasoning and I did not flag it
  as an assumption when I registered the band. It is ~25× the shared-issue price.
- It also flagged that whether memory and ALU share one issue slot on Apple GPUs
  is **inferred, not documented**, and that no public measurement of LSU-vs-ALU
  per-issue cost exists. That unmeasured quantity is precisely what this
  experiment turns on, which is the argument for follow-up 1.
- On the §6 register confound it partly *reduced* my concern: M5 is family-9+
  with Dynamic Caching, where occupancy is hardware-modulated against actual
  usage rather than hitting a hard static cliff. It expects a marginal
  occupancy trim, not a −14 % step. It nonetheless ranks that trim as the
  **most likely cause if the receipt is a regression**, with a net ALU-issue
  increase second and scratch demotion third — and §6.1 was run specifically to
  test that third one, which came back clean.

I am **not** revising the pre-registered read-out rule after the fact. The band
and the null rule stay exactly as written; this section records that I now
expect the NULL branch to be the likely one, and why.
