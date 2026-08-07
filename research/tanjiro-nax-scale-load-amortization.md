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

- **Cheaper fallback formulations** if the M5 shows register pressure: merge only
  the two adjacent 1 B scale loads into a single 2 B `ushort` load — 2 loads/iter
  (−33 %), **no cross-iteration state, no extra live registers, no `mutable`, no
  template plumbing**. Or an 8 B window over 2 iterations — 1.5 loads/iter with
  2 extra registers. Given the unresolved register confound, the `ushort` variant
  is the best risk-adjusted alternative and is a much smaller diff.
- The execution-equivalence harness generalizes. Any future `_nax` change can now
  get a real bitwise correctness receipt on a non-M5 host instead of relying on
  an argument, and the mutant driver is the template for keeping such a receipt
  honest.
