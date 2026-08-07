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

**H16 is not supported. Close as a negative result.**

The mechanism worked exactly as designed and the speed prediction was wrong in
sign.

- **Mechanism delivered.** Device-load census `3.00 → 1.25` per thread per
  k-iteration, as pre-registered (§2). Threadgroup memory unchanged at 9 232 B
  (§6). Scratch demotion ruled out at `-O3` (§6.1).
- **Bit-identity established twice.** Directly measured on both ranked kernel
  shapes on this host (§4), with mutation-adequacy evidence that the test can
  actually fail (§4.1) — and then confirmed on the ranked M5, where the arm
  receipt came back with `error == ""`, i.e. **every hidden correctness gate
  passed** (§12.1).
- **Ranked timing went the wrong way.** Arm `68b66c5` scored
  `2.5520699745752`; the base-surface control `0bc3eb4` scored
  `2.56222295324231`. `Δ = −0.010153` points = **−1.06 ms of S-equivalent =
  −2.36 σ_paired** (§12.3). H16 predicted `+0.01148`.
- **Not resolved at 3 σ.** `|Δ| = 0.010153 < 3 σ_paired = 0.012903`. §11.3,
  pre-registered before the number existed, forbids calling this resolved. The
  honest read is *a 2.36 σ regression signal that refutes the −1.2 ms mechanism
  without naming its replacement.*
- **The staleness caveat cuts against the arm.** The control was
  server-deduplicated to a 2.78 h-older session (§12.2). Drift over that gap is
  worth `+0.38 σ` **in the arm's favour**; correcting for it gives
  `Δ = −2.74 σ` (§12.4).
- **One budgeted ranked receipt returned unspent**, with the arithmetic showing
  a fresh control cannot change the resolution (§12.5), and a recommendation
  for where it should go instead (§12.7).

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

---

## 11. Read-out in `officialScore` units, and a power audit

*Written and committed while the control receipt was still in the queue, i.e.
before its number was known. The commit that introduces this section predates
the control receipt so the ordering is checkable.*

### 11.1 Why the currency had to change

The pre-registered rule is stated in **ms of prefill wall time `S`**. I cannot
read `S` back off a receipt: `mlxfast submissions` hard-truncates the metrics
column (`{"error":"","commit":"...","runtime":"sw...`), `COLUMNS`/`stty` do not
widen it, and the CLI exposes no per-submission detail command — `mlxfast
--help` offers only `submission-note <submission>`. **`officialScore` is the
only per-receipt number I can actually retrieve.**

So the read-out becomes `Δ = officialScore(arm) − officialScore(control)`. This
is legitimate rather than a convenience: each `officialScore` is *already*
normalized by its own same-session paired baseline, so the difference of two
scores is a paired-normalized comparison, which is exactly what the rule wanted.
It is a change of units forced by tooling, not a change of hypothesis.

Conversion, from the campaign elasticity `0.374750 % of officialScore per ms of
S`, at the arm's score `2.5520699745752`:

```
1 ms of S  =  0.374750 % × 2.55207  =  0.009564 officialScore points
```

### 11.2 The pre-registered bands, translated

Sign convention: `Δ > 0` means the arm scored higher, i.e. the change helped.

| Δ officialScore | ms-equivalent | verdict (pre-registered) |
|---|---|---|
| `≥ +0.01148` | `≥ +1.200 ms` | H16 confirmed; promote |
| `+0.00912 … +0.01148` | `+0.954 … +1.200 ms` | weak positive; do **not** promote on this alone |
| `−0.00912 … +0.00912` | `±0.954 ms` | **NULL**; spend no third receipt |
| `≤ −0.00912` | `≤ −0.954 ms` | regression; register pressure is hypothesis 1 |

### 11.3 The power audit — this pair cannot confirm H16 at 3σ

The pre-registered null half-width of `0.954 ms` is `3 × σ(S)` where
`σ(S) = 0.318 ms` is the spread of `S` across `n = 16` official receipts. That
is 3σ of a **single** measurement. The quantity I am actually reading is a
**difference of two** receipts, whose standard deviation is

```
σ_paired = 0.318 × √2 = 0.4497 ms  =  0.004301 officialScore points
```

so the honest 3σ band for a paired difference is `±1.349 ms`
(`±0.01290 points`), not `±0.954 ms`. I under-stated the noise floor when I
registered the rule, and I am flagging it rather than quietly using whichever
threshold flatters the result.

The consequence is uncomfortable and worth stating plainly:

```
pre-registered effect  1.200 ms  =  2.67 σ_paired
3σ_paired detection needs         ≥ 1.349 ms
```

**Even a textbook-perfect confirmation of H16 lands at 2.67σ, inside the
corrected 3σ noise band.** A two-receipt design was never able to resolve the
effect I registered. That is a design flaw in my own experiment, not a property
of the result, and it holds no matter which way the number comes back.

How I will adjudicate given that:

- I report `Δ` against the **pre-registered** bands in §11.2, because those are
  what I committed to.
- I additionally report where `Δ` sits relative to `σ_paired = 0.004301`, and I
  will **not** describe any outcome with `|Δ| < 0.01290` as statistically
  resolved by this pair alone.
- A positive result in the "confirmed" band is therefore reported as
  *consistent with H16 but unreplicated*, and the correct next step is
  replication, not promotion. Promotion on a 2.67σ single pair would be exactly
  the "trusting hot, unmatched, cross-machine timing" failure the guide warns
  against, in a slower disguise.
- A NULL, by contrast, **is** informative here, because the pre-registered
  effect is large relative to the band: `Δ ≈ 0` excludes the −1.2 ms mechanism
  with reasonable confidence even if it cannot pin the true value.

This asymmetry — the design can credibly *refute* H16 but not credibly
*confirm* it — is the single most important thing to know before reading the
number, which is why it is recorded before the number exists.

### 11.4 Pre-registered inversion: pricing the memory-issue share of the 6.887 ms

Assignment §11 item 6 asks for the memory-op-issue share of the 6.887 ms
pure-issue term, and says correctly that this number is worth having *however*
H16 lands, because it prices every future issue-reduction idea in this kernel.
The receipt pair measures it. Registering the inversion here, before the number.

The assignment's own model is `ΔS = 0.58 × share × 6.887 ms`, so the naive
inversion is

```
share_naive = ΔS_ms / (0.58 × 6.887)  =  ΔS_ms / 3.9945
```

That inversion is **biased low**, and the §10.1 review is why. The change does
not only remove memory issues; it also adds ≈5–8 ALU issues per iteration. So
the truth is

```
ΔS  =  0.58 × share × 6.887  −  c        with  c = added ALU cost ≥ 0
⇒  share  =  (ΔS_ms + c) / 3.9945   ≥   ΔS_ms / 3.9945
```

Two consequences I commit to before seeing the data:

1. **`share_naive` is a lower bound on the memory-issue share, not an
   estimate.** I will report it as a bound. A null therefore bounds the share
   *below* at ≈0, which on its own is not informative.
2. To get an upper bound I must price `c`. The only available estimate is the
   review's shared-issue rate — `6.887 ms / ~190 issues per iteration ≈ 0.036 ms`
   per instruction per iteration — giving `c ≈ 5–8 × 0.036 ≈ 0.18–0.29 ms`.
   That figure rests on the *inferred, undocumented* assumption that memory and
   ALU share one issue slot, so any upper bound I quote inherits that
   assumption and I will label it as conditional rather than measured.

With `c ≈ 0.2 ms` and the corrected 3σ_paired band of `±1.349 ms`, the
resolution of this inversion is

```
±1.349 / 3.9945  =  ±0.34   →  ±34 percentage points of share
```

So the pair can distinguish "loads are a small part of the issue term" from
"loads are most of it", and can exclude the assignment's optimistic 45 % arm if
`ΔS` comes back near zero — but it cannot separate 30 % from 40 %. That is the
honest resolution of this experiment on the issue-budget question, and it is a
consequence of the two-receipt budget rather than of anything the kernel does.

---

## 12. Ranked receipts and the read-out

### 12.1 The two receipts

| role | receipt | status | `error` | officialScore | commit | dispatched (UTC) |
|---|---|---|---|---|---|---|
| **arm** (`wide_scale`) | `68b66c5` | rejected | `""` | **2.5520699745752** | `56dcf063738ec52c622e05ad4a0ff87d872689b5` | 8/7/26 09:36 |
| **control** (base surface) | `0bc3eb4` | rejected | `""` | **2.56222295324231** | `5164d313fae0cd5d601b1cda4e1c4620207c1dfc` | 8/7/26 **06:49** |

`error == ""` on the arm is the load-bearing part of that table. It means the
full hidden M5 gate stack — 64-step drift tripwire, 512-token teacher-forced
cases, hidden anchors and free runs, GPQA behaviour and TTFT, the semantic
judge, and in-phase token validation — **passed**. `rejected` here carries no
correctness meaning; it only says the score did not beat the leader. The
leader was `2.60402397` at the moment the arm was dispatched (§12.2 shows how
that number is recoverable), so a `-0.397 %` candidate could not have been
promoted regardless of what it did to the kernel.

Combined with the offline execution-equivalence measurement of §4 and the
mutation adequacy of §4.1, the bit-identity claim of H16 is now established
**both** statically on this host and behaviourally on the ranked M5. That half
of the hypothesis is settled.

### 12.2 The control was server-deduplicated: no fresh measurement happened

The control was dispatched at 10:13 UTC from a detached worktree at exactly
`fe5d843f7374f8608e4638a05a17a92a09365ecc` with a verified-empty
`git diff fe5d843f -- Sources/ Vendor/`. The CLI answered:

```
Submission already exists
submission  0bc3eb4c-95b0-4c47-bdb1-28b266a76acd
status      rejected
note        not stored (existing submission reused; its original note is kept)
```

`mlxfast submit` **deduplicates on the content hash of the submitted editable
surface, not on the commit sha.** My base worktree hashes identically to the
already-submitted `5164d313` surface — §8 shows why: the base editable surface
is 2 949 686 B, exactly the advisor's post-#215 frontier figure — so the server
returned the 06:49 receipt and ran nothing.

Two independent confirmations that no re-measurement occurred:

1. The returned commit is `5164d313`, not the `fe5d843f` I submitted from.
2. `mlxfast submissions` prints a `diff` column which decodes as
   `officialScore − best_at_submission_time` (verified against four rows,
   including `53f19ef`, whose implied previous best `1.003409` reproduces the
   value implied by the row above it). `0bc3eb4`'s diff of `-0.035652` implies
   a leader of `2.59787495`; the arm's `-0.051954` implies `2.60402397`. If the
   control had been re-run at 10:13 it would have been differenced against the
   *current* `2.604024`, not against the stale 06:49 leader.

Consequence: the control is a **real M5 measurement of the correct surface**,
but from a session **2.78 hours before** the arm. It cost zero ranked receipts.
One of the assignment's two budgeted receipts is therefore still unspent
(§12.5).

### 12.3 The number

```
Δ = officialScore(arm) − officialScore(control)
  = 2.5520699745752 − 2.56222295324231
  = −0.010152978667 points        (−0.39626 %)
  = −1.0616 ms of S-equivalent    (at 1 ms of S = 0.009564 points)
  = −2.361 σ_paired               (at σ_paired = 0.004301 points)
```

**The arm is slower than the control**, by roughly 1.06 ms of S-equivalent.

Adjudicating against the §11.2 table, pre-registered and committed in `b3476c1`
at 10:06:16 UTC, before the control number existed:

| band | Δ range | this result |
|---|---|---|
| H16 confirmed | ≥ +0.01148 | no |
| weak positive | +0.00912 … +0.01148 | no |
| NULL | ±0.00912 | no |
| **regression** | ≤ −0.00912 | **yes** |

The point estimate lands in the regression band, with the sign **opposite** to
the one H16 predicted. H16 predicted `+0.01148` and the pair returned
`−0.01015`; the pre-registered mechanism and the observed effect are separated
by 2.2 registered effect sizes.

But §11.3, also pre-registered, forbids me from stopping there. `|Δ| = 0.010153`
is **below** the corrected `3 σ_paired = 0.012903`, so by my own committed rule
this pair does **not** statistically resolve the sign. The honest one-line
statement is:

> **a 2.36 σ regression signal, not resolved at 3 σ, measured against a control
> the server refused to re-run.**

This is exactly the asymmetry §11.3 predicted: the design was powered to refute
H16 but not to confirm it, and it has done the thing it was powered to do —
it has removed the −1.2 ms mechanism from consideration without being able to
name the replacement.

### 12.4 The staleness caveat cuts against the arm, not for it

The obvious objection is that the 2.78 h gap explains the gap. It does not, and
the direction is the interesting part.

The documented M5 drift is `+0.091 %` on paired-baseline decode over ~3 h. A
*slower* paired baseline inflates `decode_speedup = baseline / candidate`, and
decode carries 0.75 of the score weight, so the **later** receipt is the one
that drift favours. The arm is the later receipt. Over 2.78 h:

```
decode drift  = 0.091 % × (2.784 / 3)   = 0.0844 %
score drift   = 0.75 × 0.0844 %          = 0.0633 %  =  +0.001623 points
              = +0.377 σ_paired,  in the ARM's favour
```

Removing that tailwind gives a drift-corrected

```
Δ_corrected = −0.011776 points = −1.2313 ms = −2.738 σ_paired
```

So the staleness is worth about 0.38 σ and it was **helping** the arm. Correcting
for it moves the result *further* into the regression band, to within 0.26 σ of
the 3 σ resolution threshold — still short of it, but the caveat does not
rescue H16.

One counter-datum I record because it is inconvenient rather than because it
helps. Receipts `26b8e82` (06:26, surface `0b5372f`) and `0bc3eb4` (06:49) are
23 minutes apart and differ by only `0.00032` points — 32× smaller than my Δ. It
is tempting to use that as a tighter noise estimate and declare the result
resolved. I will not, because the advisor's own S readings for those two
receipts are 98.2092 ms and 97.5250 ms: **0.68 ms of S apart**, worth
`0.0065` points on the prefill axis alone. Their composite scores agree only
because the decode axis happened to move the other way by a similar amount.
Per-axis session noise is therefore clearly *larger* than that composite
agreement suggests, and the conservative `σ_paired = 0.318 × √2` stays.

### 12.5 Why I am not spending the second receipt on a forced-fresh control

The natural next move is to defeat the content dedupe with an inert
perturbation of the base surface — a comment-only edit, with AIR-md5 equality
proving inertness exactly as §3 does — and buy a control from the current
session. I considered it and decided against it. The reason is arithmetic, not
caution.

`σ_paired = 0.318 × √2` was derived from **cross-receipt spread**, so it is
already the variance of an *unpaired* two-receipt difference. Re-running the
control simply re-draws from the same distribution: the new Δ would carry the
same `σ_paired = 0.004301` and face the same `3 σ = 0.012903` threshold. A
fresh control therefore **cannot change the resolution of this pair**. All it
buys is removal of the 0.377 σ drift bias quantified in §12.4 — and that bias
currently flatters the arm, so removing it can only make the regression read
stronger, never weaker. There is no realistic redraw in which a fresh control
converts this into support for H16.

Resolving a `−1.06 ms` effect at 3 σ needs `N ≥ (3 × 0.318 × √2 / 1.06)² = 1.62`,
i.e. **2 receipts per arm, 4 ranked runs** — and more if the true effect is
smaller than the point estimate. That is well outside a two-receipt budget and,
more to the point, would spend a shared M5 slot to sharpen a number that
changes no disposition: this branch is not promotable under either outcome.

There is also a contract reason. Assignment §7 specifies a **byte-exact** base
control. The server has made the literal form of that instruction unexecutable,
and a perturbed control preserves its intent while violating its letter. That is
a waiver only the advisor can grant, and it is not worth granting for a receipt
that cannot move the verdict.

**So one of the two budgeted ranked receipts is returned unspent.** §12.7 says
where I would spend it instead.

### 12.6 The §11.4 inversion returns a vacuous bound, as pre-registered

Applying the registered inversion to the measured `ΔS`:

```
share_naive = ΔS_ms / 3.9945 = −1.0616 / 3.9945 = −0.266
                             (−0.308 drift-corrected)
```

§11.4 committed in advance to reading `share_naive` as a **lower bound** on the
memory-op-issue share of the 6.887 ms pure-issue term, because the change also
adds ALU issues. A negative lower bound is vacuous: it says only "the share is
at least zero", which was already known.

The inversion has therefore **failed to price the memory-issue share**, and it
failed for the reason registered before the data arrived. What it does deliver
is the complementary fact. In

```
ΔS = 0.58 × share × 6.887 − c
```

with `ΔS ≈ −1.06 ms` and `share ≥ 0`, the added-ALU term satisfies `c ≥ 1.06 ms`
— and `c ≥ 1.06 + 0.58 × share × 6.887` for any positive share. The §10.1
review's conditional estimate was `c ≈ 0.18–0.29 ms` at 0.036 ms per
instruction per iteration. The measurement wants `c` at least **3.7× larger**
than that, and larger still if the memory share is non-zero. Either the added
instruction count is well above the estimated 5–8 per iteration, or the
per-instruction price in this loop is well above 0.036 ms, or — the branch I
find most plausible and cannot test from this host — the cost is not
instruction-count at all but the occupancy/register effect ranked first in the
review's Q7 list. §6.1 has already eliminated the third item on that list
(scratch demotion) with O3 evidence, and §6 shows threadgroup memory is
unchanged, so register-driven occupancy and net ALU issue are the two survivors.

### 12.7 Disposition and where the unspent receipt should go

**H16 is not supported.** The hypothesis was that removing 1.75 device loads per
thread per k-iteration would buy 1.2–1.8 ms of S. The mechanism was
delivered exactly as designed — census 3.00 → 1.25, bit-identical on both
ranked shapes, tgp memory unchanged, all hidden M5 gates green — and the ranked
measurement came back 1.06 ms in the **wrong direction**. This branch should be
closed as a negative result, not revised.

The most valuable thing the campaign can take from it is that **eliminating
device loads in this loader is not automatically profitable**, and the §10.1
review called that outcome before the receipt existed. Its Q6 discriminating experiment is now
the obvious use of the unspent receipt, and I recommend it as a separate
assignment rather than a revision of this one:

> **Dummy-load slope.** Add `{0, +2, +4, +8}` extra *live*, DCE-proofed,
> cache-hit scale-byte loads per iteration to the **unmodified baseline** and
> measure the slope of S. My pre-registered model prices a removed byte load at
> ≈0.98 ms per load per iteration; the shared-issue model prices it at
> ≈0.03–0.04 ms. That is a **25× separation** on a single monotone axis, it
> touches no register-allocation-sensitive code, and it is free of the occupancy
> confound that §12.6 leaves standing. It prices *every* future
> issue-reduction idea in this kernel, which is what assignment §11 item 6
> actually wanted and what §12.6 failed to deliver.

Two cheaper follow-ups from §10 remain independently worth doing and are not
blocked by this result:

1. **Hoist `win_ok` into a constructor-set member.** §6.1 shows it is re-derived
   every call — an `sdiv` plus two modulo tests per k-iteration on loop-invariant
   inputs that the non-inlined call boundary prevents the compiler from
   hoisting. This is a strictly cheaper form of the same mechanism and, given
   §12.6's finding that the ALU side is the expensive side, it is now the more
   promising direction. I deliberately did **not** apply it here because it
   would have invalidated the dispatched receipt pair.
2. **Offline scale-plane repack in `Sources/MLXFastTransform`.** The review's
   best unlisted option: it moves the work out of the scored path entirely
   instead of trading memory issues for ALU issues inside it.
