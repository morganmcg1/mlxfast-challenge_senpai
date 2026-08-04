SENPAI-RESULT: {"terminal":true,"status":"complete","pending_arms":false,"wandb_run_ids":[],"primary_metric":{"name":"official_ns","available":true,"value":2.51083},"test_metric":{"name":"passed_correctness","available":true,"value":1}}

- **Student / PR:** maple-fern / #24 (`maple-fern/stage-dbuf`)
- **Hypothesis and target cost:** the expert gather-GEMM alternates weight staging and MMA instead of overlapping them; software-pipelining the weight read should hide 16.75–22.69 ms of MMA behind the irreducible ~28.17 ms DRAM stream of the routed-expert block (45–50% of `S`).
- **Decision:** **dead hypothesis.** Prefill regressed +0.651% (+2.501σ, ~p99 of the comparable near-clone distribution); `ns` −0.081%. The candidate is *valid* — bit-exact, every hidden gate passed on the ranked host — so this is a measured negative, not an invalid candidate. §9 explains why the mechanism cannot work and retires the whole family.
- **`BASE_SHA` / candidate commit:** `cddee1e7c91f8bb09d4efb07669105929acf5711` (assignment base; advisor confirmed later base moves were `research/`-only) / `183f8f0`, which is the commit the official receipt was taken at. Branch HEAD is later, but **every commit after `183f8f0` touches only `research/`**, so the submitted surface is byte-identical to branch HEAD — `git diff 183f8f0 HEAD --stat` lists no `editablePaths` file. The later commits are the compile-gate `kSwigluRegLocal` pin and the §8/§9 write-ups.
- **Submitted candidate files:** 10 source files, all inside `benchmark.json`'s 97 `editablePaths` (4 kernel headers, `quantized.cpp`, `jit_kernels.cpp`, 4 `mlx-generated/*.cpp` twins). 800 insertions / 56 deletions vs base.
- **Supporting test or documentation files:** `research/nax-compile-gate.py` (offline compile gate, 14/14, not submitted), `research/maple-stage-dbuf-note.md` (public note as uploaded), `research/maple-barrier-flags-kill-device-prefetch.md` (**§9, the main finding**), `research/field-axis-asymmetry.py` + `research/maple-field-axis-asymmetry.md` (§8).

---

## 1. Headline

**The arm is a negative, and I think I know why: the overlap it was built to
create already existed, for free, because every barrier in that k-loop is
`mem_flags::mem_threadgroup` and therefore never fenced device memory at all.**

The receipt (`7a5a1e08`, all gates passed, `max_abs_diff 0`, GPQA 9/9):

```
S  98.347 ms   vs control 97.711 +- 0.254   =  +0.651%  (+2.501 sigma)   SLOWER
T  4.3612 ms   vs control 4.3718 +- 0.0104  =  -0.242%  (-1.014 sigma)   null
ns 2.51083     vs control 2.51286           =  -0.081%
```

Prefill got **slower**, at roughly the **p99** of the comparable near-clone
distribution (1 of the top-100 receipts by `ns` is that slow, and it is not
mine). Decode is a clean null, which is the right control for a prefill-shape
kernel. **Do not promote.**

Three things I want to put on the record, in descending order of how much I think
they are worth to the programme:

1. **§9 — the mechanism.** Manual software pipelining of *device* reads in this
   k-loop cannot pay, because the two barriers bracketing the stage are
   `mem_threadgroup`-only. They impose no ordering on device memory, so the
   compiler was already free to hoist the next tile's device load above the WAR
   barrier into the previous iteration's MMA. I did not add overlap; I added
   register live-range and control flow to a loop that was already overlapped.
   **The 16.75–22.69 ms prize does not exist in the form the brief priced it.**
2. **§8 — nobody in 926 measured receipts has moved prefill by 2σ, while decode
   has moved 6σ.** I found this before the receipt landed, and §9 is a candidate
   explanation for it rather than a coincidence.
3. **§4 — your C1+C2 revision would have been actively harmful.** `BN=32`
   silently flips `kSwigluRegLocal` false and reactivates the staged epilogue,
   which is also the sole source of the `gate_up_stage` aliasing hazard you were
   worried about. Proven by compilation, not by reading. At the shipped geometry
   `gate_up_stage` is dead code and there was never an aliasing question.

The one thing this receipt cannot settle is *how much* of the +0.651% is register
pressure versus lost scheduling freedom; see "smallest useful next action".

---

## 2. Part 0 — the tiling closure is confirmed, and three things strengthen it

I reproduced your table exactly from `research/prefill-512-route-histogram.txt`
(76 records × 256 experts = 311,296 assignments, 20.26% zero-row, mean nonzero
20.07, median 11): `BM=64/WM=4/SM=16` → **453,120 MMA rows = 1.456× ideal**,
16,758 stagings. `sum ceil(n/16)*16 = 453120` and `sum ceil(n/32)*32 = 640000`
(**+41.2%**). Confirmed, arithmetic in `/tmp/part0.py`.

Three strengthenings:

1. **It is an identity, not an empirical finding.** Whenever `BM % SM == 0`,
   `sum_chunks ceil(chunk_rows/SM)*SM = ceil(n/SM)*SM`. So MMA row padding
   depends **only on `SM`**; `BM` is fully decoupled and affects only the
   staging count. That removes the need to re-measure any `(BM, SM)` pair.
2. `SM=16` is the hardware floor because `kFragRows = 16` (`steel/gemm/nax.h:28`).
   `SM=8` gives `TM = SM/16 = 0` and emits **no MMA at all** — see §4.
3. **Structural kill.** `expert_aligned` (`quantized.cpp:1659-1665`) requires
   `bm == 64 && wm == 4 && (wn == 2 || wn == 1)`. Every `DARKBLOOM_STAGE_BM128`
   variant with `bm=128` (cases 1, 2, 3 at `:1638-1646`) therefore falls off the
   expert path entirely and silently dispatches the **non-expert**
   `fp_gather_qmm_rhs_nax`. **Variants 1/2/3 are dead levers** — the same
   self-control bug class as `STAGE_WIDEST`/`WIDELD`. They could never have
   measured what their names claim.

Both prose/code mismatches you flagged are confirmed:
`darkbloom_expert_gather_groups()` comments "default 128" (`:1365`) but returns
**256** (`:1383`); `case 4:` says "SHIPPED DEFAULT" (`:1642`) while the function
defaults to **5** (`:1478`).

---

## 3. What I built, and why it is not your C1

I did **not** double-buffer `Ws` in threadgroup memory. I split the fused
`load → decode → store` weight stage into two halves and moved only the device
read across the barrier:

- **`prefetch<wide_store, wide_load>(StageRegs& r, tiles_ahead)`** — device reads
  only, into a per-thread register struct
  `StageRegs { uint8_t sb[kSrcBytes]; uint8_t sc[kScaleRegs]; bool staged; }`.
- **`commit<wide_store, wide_load>(StageRegs& r)`** — NVFP4 decode + threadgroup
  store, from those registers.

```
prefetch(stage_regs, 0)                    # tile 0, before the loop
for k in 0..K_it:
    Atile load
    threadgroup_barrier                    # WAR
    commit(stage_regs)                     # decode + store tile k
    threadgroup_barrier                    # RAW
    if (k + 1 < K_it) prefetch(stage_regs, 1)   # tile k+1 read, in flight across MMA
    MMA over kk1
    loader_w.next()
```

**The second buffer lives in registers, so threadgroup memory is unchanged at
9,224 B.** That is the whole point, and it is why your occupancy analysis — which
I agree with — does not apply to this build:

| `Ws` footprint | TGs/core | `f(m) = 1 + 0.365(m-1)` |
| --- | ---: | ---: |
| 9,224 B (shipped **and this candidate**) | 7 | 3.56 |
| 18,440 B (your C1) | 3 | 2.10 |

Bit-exactness is structural: only *when* bytes are read changes, never which
bytes, which addresses, the decode arithmetic, or the accumulation order. Two
details that make it safe:

- The NAX loader is **stateless** (no `group_step_cnt`, unlike the non-NAX
  loader), so `prefetch`'s `src + tiles_ahead*tile_stride` and
  `scales + tiles_ahead*(reduction_dim == 1 ? n_groups : n_groups*group_stride)`
  are verbatim its own `next()` (`fp_quantized_nax.h:582`) with no hidden counter
  to desynchronise.
- `fp4nv_pack4(const thread uint8_t*)` is **pre-existing** and little-endian, so
  the register byte round-trip is exact. `kScaleRegs = ((kWideChunks-1)*kSrcBytesPerChunk)/n_reads_per_scale + 1 = 2`,
  and `store_chunks` indexes `r.sc[k0/n_reads_per_scale]` whose max is exactly
  `kScaleRegs-1`.

I also ported the split to the **non-NAX** twin (`fp_quantized.h`,
`quantized_utils.h`) because that is what executes on my M4 — otherwise the arm
would have been unmeasurable and ungateable locally. There I left `stage()`
byte-for-byte untouched and duplicated the decode, so non-opted-in callers
generate identical code, and added a **separate** `gemm_loop_aligned_stage2`
rather than a flag inside `gemm_loop_aligned` (which is shared with the affine
path).

`DARKBLOOM_STAGE2_GATHER` is a process-constant `static const bool` read as
`!= "0"`, injected at JIT assembly. **Never a function constant** — the tree's
15–24% mid-process recompile regression (`quantized.cpp:1214-1220`) is exactly
that mistake.

---

## 4. Your C1+C2 revision: I think `BN=32` is the wrong enabling condition, and here is why

Your threadgroup arithmetic is right — `BK_padded` depends on `BK` not `BN`, so
`BN=32` double-buffered is `2 × 4,608 = 9,216 B`, exactly the shipped
single-buffered footprint, and `grid.x = (N + bn - 1)/bn` really does double
(`quantized.cpp:1920-1923`). But `BN=32` is not free, for a reason I do not think
is anywhere in the tree:

```cpp
// fp_quantized_nax.h:1741-1742
constexpr bool kSwigluRegLocal =
    (WN == 1) && (BN == 64) && ((BM / WM) == 16);
```

`BN == 64` is a **hard term in the predicate that enables the shipped
register-local SwiGLU epilogue**, and `DARKBLOOM_SWIGLU_REGLOCAL` is
shipped-default ON (`quantized.cpp:1583`, `!= "0"`). At `BN=32` that constant
silently becomes `false`, `if constexpr (kSwigluRegLocal)` (`:1931`) is
discarded, and the kernel falls back to the stock epilogue at `:1964-1990` that
round-trips the whole `Dtile` through `gate_up_stage` in threadgroup memory plus
an extra barrier per chunk.

So **C2 does not isolate the `grid.x`/occupancy change — it also turns off a
shipped, measured optimization**, and any C2 measurement is confounded by that
loss rather than being the clean control step 1 needs.

It is worse for your landmine 2, which inverts:

- On the **shipped** geometry (`BN=64`, `WN=1`, `BM/WM=16`), `kSwigluRegLocal` is
  `true`, so the `!kSwigluRegLocal` block is discarded at compile time and
  **`gate_up_stage` is dead code** — never written, never read. There is exactly
  one live consumer of `Ws_storage`, which is why my build has no aliasing
  question to answer at all.
- Drop to `BN=32` and `gate_up_stage` becomes **live** again, storing `Dtile`
  into `Ws_storage` and reading it back with a single barrier between. Combine
  that with a double-buffered `Ws` carrying an in-flight prefetch and you have
  precisely the silent-corruption hazard you warned about.

**So `BN=32` is not the enabling condition that makes threadgroup double
buffering safe; it is the sole cause of the hazard that makes it dangerous.**
My build keeps `BN=64`, one `Ws`, `kSwigluRegLocal` true, `gate_up_stage`
compile-time dead, and grid/occupancy bit-identical to shipped — which is the
outcome C1+C2 was reaching for, without the confound.

Two smaller facts for the record: `bn` is hard-coded 64 (`quantized.cpp:1634`)
and **no** `STAGE_BM128` case changes it, so C2 needs a new host lever, not an
existing knob; and `expert_aligned` does not test `bn`, so C2 stays on the expert
path and fails *silently in the epilogue* rather than loudly at dispatch.

I did not want to hand you this on a source reading, so I **proved it by
compilation**. Injecting `static_assert(kSwigluRegLocal, ...)` immediately after
the constexpr and compiling both geometries with the shipped defines:

```
BN64_shipped    kSwigluRegLocal = TRUE  (compiles)
BN32_proposed   kSwigluRegLocal = FALSE (assert fires)
      fp_quantized_nax.h:1735:3: error: static_assert failed due to
      requirement 'kSwigluRegLocal' "..."
```

Both cases are now **permanent gate cases** (`reglocal_bn64_shipped`,
`reglocal_bn32_disabled`), so the next person who touches `BN` gets a red gate
instead of a silent epilogue swap.

Your landmine 1 is clear, and I checked that empirically too:
`TN = SN/16 = BN/(WN*16)`, so `BN=32, WN=1` gives **`TN = 2`**, which is even and
legal — and all four `BN=32` instantiations (`stock`/`stage2` ×
`gate_up`/`down`) **compiled cleanly**. That is the point worth keeping: a clean
compile at `BN=32` is *not* evidence of correctness, because what breaks is a
`constexpr bool` quietly flipping, not a diagnostic.

---

## 5. The `static_assert` you asked for, and a compile gate for M5-only kernels

`tile_matmad_nax` had two branches — `TN == 1 && TM % 2 == 0` and `TN % 2 == 0`
— and **no `else`**, so any other shape compiled cleanly and performed no MMA,
returning zeros. Added at `steel/gemm/nax.h:993`:

```cpp
static_assert(TM > 0 && TN > 0 && ((TN == 1 && TM % 2 == 0) || (TN % 2 == 0)),
              "MXU tile matmul: no MMA form exists for this (TM, TN); "
              "need TN == 1 with even TM, or even TN");
```

I verified the trap was real, not theoretical: in a throwaway `git worktree` at
base `cddee1e` the out-of-shape instantiation **compiled without any
diagnostic**. Under the assert it is rejected.

**`research/nax-compile-gate.py` — the campaign's first compile gate for M5-only
kernels.** The NAX family is unreachable on M4 (`quantized.cpp:1959`), so the
ported kernel would otherwise ship never having been compiled anywhere. The gate
reassembles the same source `jit_kernels.cpp` assembles from the
`mlx-generated` raw-string twins and runs `xcrun metal -std=metal4.0` over it
(3.1 fails). **14/14 cases behave as required:** 8 expert NAX instantiations
(stock and stage-2 × `gate_up_static`, `down_static`, `dynamic_scalar`,
`gate_up_store_only`), `nonexpert`, `stock_nonnax`, `stage2_nonnax`, the negative
control `trap_tm1_tn1`, and the two `kSwigluRegLocal` pinning cases from §4. Two
of the fourteen are **expect-fail** cases, so the gate is a gate.

I also verified the four `mlx-generated/*.cpp` twins really do mirror their
headers, since a stale twin would mean the runtime compiles something other than
what the header says. Hunk-level check against base: **44 added runs, 44
mirrored, 0 stale** across all four pairs. (Whole-file comparison is useless
here — each twin concatenates several headers.)

That NAX arms are otherwise *structurally blind* on M4 is itself a budgeting
fact: it changes how many receipts a NAX change should cost before anyone looks
at a number.

---

## 6. The most transferable finding: my local instrument cannot resolve this effect

Three `--local-iterate` arms, same host, same thermal gate:

| arm | S (ms) | T (ms) | prefill s/tok | decode s/tok | max_abs_diff |
| --- | ---: | ---: | ---: | ---: | ---: |
| base `cddee1e`, define absent | 575.311 | 8.9866 | 0.001123655 | 0.013481240 | 0 |
| cand `4d0191a`, `STAGE2_GATHER=0` | 568.897 | 9.1237 | 0.001111127 | 0.013568180 | 0 |
| cand `4d0191a`, stage-2 **ON** | 576.591 | 9.0436 | 0.001126153 | 0.013548197 | 0 |

Candidate-ON vs base: `dS = +0.222%`, `dT = +0.634%`.

Now the middle row. With `DARKBLOOM_STAGE2_GATHER=0` the guarded blocks
preprocess away, so **that arm compiles the same JIT source as base** — it is a
compile-identical control whose true effect is exactly zero. It measured
`dS = −1.115%`, `dT = +1.525%`.

**This host's single-receipt noise floor is therefore ≥1.1% on `S` and ≥1.5% on
`T` — 5× and 2.4× the effect I was trying to resolve.** My local measurement of
this mechanism is not weak evidence, it is *no* evidence; any of the three
orderings could have arisen by chance. I am reporting it rather than the tidier
"candidate-ON vs base" row because a compile-identical control is the only thing
that measures the instrument instead of the change, and in this case it
invalidated my own result.

The banked official control is a far better instrument: from the three
byte-identical receipts, **`S` 1σ = 0.260%, `T` 1σ = 0.238%, `ns` 1σ = 0.076%**
(mean `S` 97.711 ms, `T` 4.3718 ms, `ns` 2.51286). That is ~4× tighter on `S`
than my host and is why this arm went to an official receipt rather than a local
verdict.

### Reachability — the `WIDEST`/`WIDELD` confound is excluded

The `=0` arm printed:

```
mlxfast: fusion inactive: stage2_gather (dispatch non-nax mode=nvfp4 align_MNK=111 N=1024 K=2048 M=4096)
mlxfast: fusion inactive: stage2_gather (expert gather-QMM JIT source)
```

The first line is emitted only where `metal::is_nax_available()` is false, so the
op genuinely dispatches `fp_gather_qmm_rhs` here; `align_MNK=111` proves the
**aligned** loop — the one I modified — is the one that runs. `M = 4096` because
the gather flattens rows across experts: another structural way the M4 stand-in
differs from the per-expert NAX schedule (128 threads / `kSrcBytes=16` there vs
64 threads / 8 B per lane here).

### `DARKBLOOM_STAGE2_GATHER` was dead scaffolding

The JIT injection (`jit_kernels.cpp:1147`) and the dispatch trace both already
existed with **zero consumers in any kernel source** (harvested from public
submission `4bf4f794`, per `research/nezuko-harvest-report.md`). Flipping it
changed the assembled source string but could not change compiled semantics, so
every prior measurement of that flag necessarily measured its own control. This
change gives it a real consumer for the first time. I also added the missing
non-NAX dispatch trace after `align_K` in `gather_qmm_rhs`.

---

## 7. Your LSU motivation is stale, which changes the widening lever

The brief's "16 scalar 1 B device loads + 32 scalar 2 B threadgroup stores, ~50
LSU ops" describes **variant 4**, not what ships. Shipped variant 5 already does
four 4-byte device loads (16 B/lane) + 2 scale bytes + four 16 B threadgroup
stores ≈ **7 LSU ops**. Stale comments at `fp_quantized_nax.h:350-357` and
`:1751-1753`; the "staging = 39.5% of prefill" figure
(`quantized.cpp:1445-1450`) is variant-4-era too.

So load *width* is already done. The remaining version of your 32-B-in-flight
point would be **prefetch depth**: `tiles_ahead` 1 → 2, taking in-flight bytes per
lane 16 B → 32 B at a cost of ~9 more registers.

**I recommended that as the next arm while this receipt was in flight, and I am
now withdrawing it.** §9 kills it for the same reason it killed this arm: with no
barrier fencing the device read, there is nothing to prefetch *past*, so deeper
prefetch buys the same zero overlap at a higher register cost. Read this section
as evidence that the brief's LSU motivation is stale — which stands — and not as a
live proposal.

---

## 8. Unassigned finding: in 926 public receipts, nobody has moved prefill — decode has moved 6σ

This was not in the brief. I found it while banking the control and it bears
directly on how you price this arm, so I am reporting it here rather than sitting
on it. Committed as `research/field-axis-asymmetry.py` +
`research/maple-field-axis-asymmetry.md` (`ad81c43`).

`mlxfast submissions` truncates the metrics column and has no JSON flag, but the
endpoint behind it returns **the whole public field**, not just our own rows:

```
GET https://api.mlx.fast/api/benchmarks/{urlencoded-ref}/submissions
Authorization: Bearer $MLXFAST_API_TOKEN
```

**What the population is.** Status partitions the field exactly, with no
exceptions in either direction:

| status | count | metrics? |
| --- | ---: | --- |
| `accepted` | 140 | yes |
| `rejected` | 786 | yes |
| `failed` | 467 | no |
| `validating` | 3 | no (in flight) |

`140 + 786 = 926`. So **`rejected` is the ranking/calibration band, not
correctness** — those runs cleared every hidden gate and were fully timed;
`failed` is the correctness bucket and carries no metrics. The 926 is therefore
precisely "every submission that passed all gates and got timed on the ranked
host", which is the right denominator: it excludes broken trees without
excluding unlucky ones, so a null on prefill is a null over every *correct*
attempt the field has made. (Our own three controls are 3 of the 926; they cannot
beat themselves by 2σ so they do not affect any count.)

Scoring every one against those three byte-identical control receipts — a
*self-controlling* comparison, since it is the same population on the same
instrument in the same sessions:

```
S (prefill) beating our unchanged tree     T (decode) beating our unchanged tree
  1σ:   2 / 926  (0.22%)                     1σ: 138 / 926  (14.90%)
  2σ:   0 / 926  (0.00%)                     2σ:  74 / 926  ( 7.99%)
  3σ:   0 / 926  (0.00%)                     3σ:  34 / 926  ( 3.67%)
  best 97.3591 = 1.38σ better                5σ:   3 / 926  ( 0.32%)
                                             best 4.3076 = 6.15σ better
```

**Not one receipt in 926 beats our prefill by even 2σ.** The best is 1.38σ, i.e.
inside noise. The decode column is what makes this a finding rather than a shrug:
a population that demonstrably produced 6σ decode wins produced *zero* prefill
wins, which rules out "the instrument is too coarse", "the field is
uncompetitive", and "our tree is unusually good" in turn.

Frontier spread, top-K by `ns`, in units of the control's own σ:

| top-K | S σ | vs ctl | T σ | vs ctl |
| ---: | ---: | ---: | ---: | ---: |
| 10 | 0.153% | 0.59× | 0.215% | 0.90× |
| 20 | 0.159% | 0.61× | 0.200% | 0.84× |
| 50 | 0.161% | 0.62× | 0.218% | 0.92× |
| 100 | 0.230% | 0.88× | 0.246% | 1.03× |
| 200 | 0.993% | 3.81× | 0.346% | 1.45× |
| 926 | 21.532% | 82.70× | 33.318% | 139.75× |

Among the top 100, the spread on **both** axes is at or below the byte-identical
control's 1σ. The top of the public leaderboard is statistically
indistinguishable from one tree measured a hundred times — which independently
corroborates your `officialScore`-is-3.3×-noisier finding, and means ranking
movement up there is mostly baseline draw.

Where we sit:

```
best-S e2822dc1: S 97.359  T 4.3565  ns 2.52177
best-T ae9ac90b: S 97.704  T 4.3076  ns 2.53672   (top of field on ns, +0.949% vs our control)
4bf4f794: ns 2.53313 (#2) — the tree our STAGE2_GATHER scaffolding was harvested from
```

**Caveat, stated plainly:** part of the frontier's flatness is that `mlxfast
sync` restores editable paths from the best promoted submission, so many top
receipts are near-copies of one tree and were never independent prefill attempts.
That is exactly why the decode column carries the claim — same partly-cloned
population, still 74 two-σ wins. Cloning suppresses *variance*, not the
population's ability to win on an axis people are attacking. And this shows only
that prefill *has not* moved, not *why*.

Two consequences for your ranking:

1. **This screen is well-powered.** A genuine 0.5% S gain would land outside the
   entire 926-receipt distribution, so the screen cannot mistake noise for a win
   — and symmetrically, a null is real information.
2. **Our prefill is effectively tied for best-in-field.** So prefill work here is
   not catch-up; any real gain is new ground for the whole field, on the axis
   with 25% of the score exponent. That argues for keeping a prefill arm funded
   even though decode carries 75% of the weight.

---

## 9. Why it lost: the barriers never fenced device memory, so the compiler already had the overlap

This is the part I most want you to check, because if it is right it retires a
whole family of arms rather than just mine. Committed standalone as
`research/maple-barrier-flags-kill-device-prefetch.md` (`542569e`) so it survives
closing this branch.

### The observation

Every barrier in the routed-expert k-loop — all 21 of them in
`fp_quantized_nax.h` — is `threadgroup_barrier(mem_flags::mem_threadgroup)`.
**Not one is `mem_device`.** The shipped stage sits between two of them
(`:1851` and `:1872`):

```
threadgroup_barrier(mem_flags::mem_threadgroup);   // WAR: last MMA done with Ws
loader_w.load_unsafe_wide<wide_store, wide_load>();  //  <-- device load + decode + tg store
threadgroup_barrier(mem_flags::mem_threadgroup);   // RAW: publish Ws
    ... MMA over Ws ...
loader_w.next();
```

`mem_flags::mem_threadgroup` fences **threadgroup** memory. It puts no ordering
constraint on device-address-space loads. So the device read inside
`load_unsafe_wide` was already free to be hoisted *above the WAR barrier* — that
is, into the previous iteration's MMA region. The overlap I set out to construct
was already legal for the compiler to construct, one iteration earlier than my
version even placed it.

### Why the measurement supports this rather than merely being consistent with it

The discriminating evidence is the **magnitude**, not the sign.

- If the overlap had genuinely been absent, my arm implemented it correctly and
  bit-exactly, and the prize was 16.75–22.69 ms on a 98.153 ms prefill — a
  **17–23% win**. I measured **−0.65%**.
- If instead I had collapsed occupancy through register pressure, the cost would
  be a large fraction of the block, not 0.65%.

A **0.651%** change is the signature of "I added a little bookkeeping to a loop
whose structure did not otherwise move". That is what the hoisting story
predicts, and neither of the two alternatives can produce it. What my split
actually did was:

1. force the staged bytes into a named `StageRegs` (`kSrcBytes = 16` + `sc[2]` +
   `bool staged` ≈ 19 B/lane ≈ 5 registers) whose **live range now spans the RAW
   barrier and the whole MMA region**, where the MMA accumulators are already
   live — the byte count is unchanged from the fused version, the *live range* is
   not; and
2. add a `staged` flag and a `k + 1 < K_it` guard branch per iteration,

while **constraining** the scheduler instead of freeing it. Strictly more cost,
no new overlap.

### The general rule this yields

> Manual software pipelining of device reads across a Metal barrier is a no-op
> at best whenever that barrier is `mem_flags::mem_threadgroup`-only, because the
> barrier never fenced the thing being prefetched. It can only pay where the
> barrier actually orders the prefetched access — `mem_device`, or a value
> consumed *through* threadgroup memory that the barrier does order.

Corollary for the programme: the "staging and MMA are serialised, so overlap
them" framing is wrong for this kernel, and the roofline's
`cmp + dram -> max(cmp, dram)` step was already largely taken by the compiler.
That does **not** invalidate the roofline's *ceiling* (14.09 GB still has to
cross the bus, so ~28.17 ms is still the floor) — it invalidates the claim that
the gap between 98.153 ms and that floor is recoverable *by overlap*. It has to
be recovered by removing work, not by rescheduling it.

This is also a candidate explanation for §8: if overlap on the prefill path is
already being harvested by the compiler, then the most obvious class of prefill
optimisation returns nothing, which is one coherent reason 926 receipts have not
moved that axis.

### How to falsify it cheaply

I could not close this loop on my host and I am flagging it rather than papering
over it. `metal-objdump` exists locally but disassembles pre-register-allocation
AIR, so it cannot report physical register counts; the real number comes from the
driver at pipeline creation. Two cheap falsification routes, in order:

1. Read `MTLComputePipelineState.maxTotalThreadsPerThreadgroup` for the stock and
   stage-2 pipelines. If it drops, register pressure is a real contributor; if it
   is 1024 in both, the regression is scheduling freedom and the hoisting story
   is the whole explanation.
2. Change one bracketing barrier to `mem_flags::mem_threadgroup | mem_flags::mem_device`
   in a *throwaway* local build and re-measure the stock path. If the hoisting
   story is right, adding the device fence should make the **stock** kernel
   slower by about the amount my arm lost. **This is a diagnostic only — never
   submit it**, since it can only remove performance.

---

## Evidence

- **Host / profile / toolchain / thermal:** AWS Apple M4 Pro, 20 GPU cores, 48 GB
  unified memory, macOS 26.5.2, Metal 4.0; repo `setup.sh` toolchain; standard
  40 °C quiescence gate on every timed run; one model-holding process at a time.
  Every GPU execution via the supervised training tool, never the terminal.
- **Exact commands:**
  ```bash
  ./setup.sh
  swift test --force-resolved-versions && git checkout -- Package.resolved
  ./benchmark.sh --local-iterate                             # candidate (default ON)
  DARKBLOOM_STAGE2_GATHER=0 ./benchmark.sh --local-iterate   # compile-identical control
  python3 research/nax-compile-gate.py                       # 14/14 offline
  MLXFAST_API_TOKEN=… python3 research/field-axis-asymmetry.py  # §8
  ./benchmark.sh --local-submit
  bash research/run_upstream_equivalence.sh
  mlxfast submit --note-file research/maple-stage-dbuf-note.md --model "Claude Opus 5"
  ```
- **Tests and risk-based checks:** `swift test --force-resolved-versions`
  **453/454**. The one failure,
  `top15RunnerPinsStrictThermalToolsAndRejectsUnboundGateLogs`, **passes in
  isolation**; it exercises
  `senpai/competition_notes/top15_replication_2026-08-02/run-study.sh`, which
  `git diff cddee1e HEAD -- senpai/` shows is **byte-identical to base**, and its
  own `self-test` passes standalone. Pre-existing parallel-run flake, unrelated.
- **Correctness and serial-protocol verdict:** `--local-iterate`
  **`max_abs_diff = 0`**, `checked_steps = 130`, identical `golden_hash
  b9509697c08a` and `weights_hash aff9943005…` in all three arms.
  `LagunaUpstreamEquivalence` clean: prefill max_abs **0.125** / mean
  **0.011933609** (exactly the base profile), all 8 decode steps exactly **0**,
  every `runtimeToken == upstreamToken`. `--local-submit` **passed = true**
  (score 1.0010026, prefill 0.001127 s/tok, decode 0.009525 s/tok). No change to
  supplied tokens, logits, KV advancement, cache contents, precision, or serial
  non-speculative behaviour: the diff moves only the *timing* of device reads.
- **Divergent tokens / failure category:** none.
- **Peak RAM:** `peak_ram_gb = 21` on the ranked host, identical to the control triple and well inside the 25 GiB cap. The change allocates no new buffer and adds no threadgroup memory, so RAM was never at risk.
- **Surface audit:** all 10 changed source files inside `editablePaths`. Caveat
  for anyone scripting this: `editablePaths` contains bare **directory** entries
  with no trailing slash (e.g. `…/kernels/steel/gemm`), so a naive prefix matcher
  falsely reports `steel/gemm/nax.h` as outside. Match
  `f == p or f.startswith(p.rstrip("/") + "/")`.
- No JIT **disk** cache exists (`Device::get_library`, `device.cpp:770`, is an
  in-memory `library_map_` only), so there is no stale-library confound between
  arms.

### Official receipt — `7a5a1e08-aebb-4123-aed6-ce83ee3936bc`

Submitted 15:10Z at commit `183f8f0`, resolved ~15:35Z, status `rejected`.
That is the **ranking band, not correctness** — see the status partition in
§8: `rejected` receipts cleared every hidden gate and were fully timed.

| Metric | Baseline (banked 3-receipt control mean) | Candidate | Delta |
| --- | ---: | ---: | ---: |
| decode seconds/token | 0.005141 | 0.005129566 | −0.22% |
| prefill seconds/token | 0.00019084 | 0.000192085 | **+0.651%** |
| `S` (ms) | 97.711 ± 0.254 | **98.347** | **+0.651% (+2.501σ)** |
| `T` (ms) | 4.3718 ± 0.0104 | 4.3612 | −0.242% (−1.014σ) |
| `ns` | 2.51286 ± 0.00192 | **2.51083** | **−0.081%** |
| `decode_speedup` | — | 2.70814 | floor 0.95 ✓ |
| `prefill_speedup` | — | 1.98899 | floor 0.95 ✓ |
| `officialScore` | — | `None` | rejected on the ranking band |

Correctness on the ranked host: **`max_abs_diff = 0`**, `checked_steps = 1344`,
**GPQA 9/9**, `peak_ram_gb = 21`, `error = ''`. Every hidden gate passed — this is
a *measured* receipt, not a failure.

Baseline is the mean of the byte-identical triple `f8502e12` / `71586bcf` /
`f3cda678`, which cost nothing because the service dedupes identical archives.

### The regression is real, and it does not rest on a 3-sample σ

"+2.5σ" against a σ estimated from 3 points is a weak claim, so I replaced it
with a distribution-free one (`/tmp/regcheck.py` arithmetic, reproducible from
`research/field-axis-asymmetry.py`'s fetch). Against the near-clone frontier —
the top-100 receipts by `ns`, which are the population whose prefill is
genuinely comparable to ours:

```
top-100 S distribution     p0 97.359 (-0.360%)   p50 97.786 (+0.077%)
                           p75 97.883 (+0.176%)  p95 98.062 (+0.360%)
                           sigma 0.230%
candidate                  98.347         (+0.651%)
receipts with S >= 98.347:  top-10 0/10   top-20 0/20   top-50 0/50
                            top-100 1/100
```

**One receipt in the top 100 is as slow as my candidate on prefill, and it is not
mine** (`0c83fa3e`, S = 99.252; my receipt ranks 128th so it is not in the
window). The candidate sits at roughly the **p99** of the comparable prefill
distribution. The slowdown is real.

Decode moved −1.014σ, i.e. nothing, which is the correct control: the routed
gather-**GEMM** I edited is a prefill-shape kernel, so a decode null is what a
correctly-scoped change should produce. It also means the regression is localised
to the block I touched rather than a session-wide thermal or baseline artifact.

---

## Conclusion

The hypothesis was that staging and MMA are serialised in the routed-expert
gather-GEMM and that overlapping them recovers 16.75–22.69 ms of prefill. **It is
wrong, and it is wrong at the premise rather than in the implementation.** The
implementation is bit-exact and the receipt is clean; it made prefill 0.651%
slower, which is only explicable if the overlap was already present. §9 gives the
reason: every barrier bracketing the stage is `mem_flags::mem_threadgroup`, which
never ordered device memory, so the compiler was already free to hoist the read
into the previous iteration's MMA. I paid the register live-range and control-flow
cost of a transformation the compiler had already performed.

What I got wrong, plainly: I spent the arm on a mechanism whose *precondition* I
never checked. The brief handed me a serialisation claim and I verified that the
code looked serial in source order without asking whether the barriers actually
enforced that order. Checking the memory flags would have cost one `grep` and
would have killed the arm before a single line was written. I would rather report
that than bury it, because the same omission is available to every other arm on
this board.

What I think is genuinely worth keeping:

- **§9's general rule.** Manual device-read pipelining across a
  `mem_threadgroup`-only barrier cannot pay. This retires a family of arms, not
  just mine, and it comes with two cheap falsification routes.
- **§8's field asymmetry.** 0/926 receipts have moved prefill by 2σ; decode has
  moved 6σ. §9 is a coherent explanation for that pattern rather than a
  coincidence, which raises my confidence in both.
- **§4's compile-proven kill of C1+C2.** `BN=32` silently disables
  `kSwigluRegLocal` and reactivates the staged epilogue — the very thing that
  creates the `gate_up_stage` aliasing hazard the revision was designed to avoid.
  At shipped geometry that block is dead code. This one is proven by
  compilation, and it means the revision would have been a regression on two
  independent counts (lost shipped optimisation, plus the hazard).
- **§2's structural kill of `STAGE_BM128` cases 1/2/3.** `expert_aligned`
  requires `bm == 64`, so those variants never reached the expert kernel and
  could never have measured what their names claim.
- **§6's noise-floor result.** My M4 instrument's single-receipt floor is ≥1.1% on
  `S` and ≥1.5% on `T`, measured with a compile-identical control — 5× and 2.4×
  the effect I was chasing. Local iteration cannot screen this class of change on
  this host, and the compile-identical control is the trick that shows it.

The programme-level consequence I would draw: for prefill, **stop trying to
reschedule work and start trying to remove it.** The roofline's ~28.17 ms DRAM
floor still stands, but the gap between 98.153 ms and that floor is not
recoverable by overlap, because overlap is already being harvested. That reframes
`routed_experts` from "badly scheduled" to "genuinely doing this much work".

### Uncertainty / M5 transfer risk

1. **M4 geometry verdicts have inverted on M5 in this tree.** Variant 4 beat
   variant 5 by **+17.47%, 4/4 pairs, zero distributional overlap** locally
   (342–371 µs vs 414–434 µs) and the official M5 receipts **reversed** it
   (204.90 → 201.64 µs/token), which is what ships
   (`quantized.cpp:1440-1462`, `:1478-1484`). My local numbers establish that the
   mechanism exists and is bit-exact; they establish neither its magnitude nor
   its **sign**.
2. Per §6, my local numbers do not establish magnitude even on my own host.
3. The NAX port is **compile-verified, not execution-verified**. No hardware I
   have can run it.
4. The prize was a **range** (16.75–22.69 ms) resting on an unmeasured vendor
   constant; our own receipt bounds M5 matrix throughput only from below at
   **≥44.3 TFLOP/s**. §9 makes this moot for *this* arm — the prize was not
   recoverable by overlap at any value of that constant — but tanjiro's #27 still
   matters for pricing work-removal arms.
5. `S` and `T` are reported separately because RUNSKIP/prefill changes move
   `decode_seconds_per_token` through the 512-token seed forward.
6. **§9 is a leading explanation, not a measurement.** It rests on (a) the barrier
   flags, which are certain, (b) the Metal semantics of
   `mem_flags::mem_threadgroup`, which I believe are certain but did not verify
   against a disassembly, and (c) an argument from the *smallness* of the measured
   regression, which is inference. The competing explanation — pure register
   pressure with the overlap genuinely absent — is inconsistent with a 0.65%
   effect where 17–23% was predicted, but I could not rule it out directly because
   `metal-objdump` only exposes pre-register-allocation AIR. Both §9's two
   falsification routes are cheap and I would run them before treating the general
   rule as settled.
7. Because the effect is a **regression**, M5-vs-M4 sign inversion (item 1) is a
   *weaker* concern than usual here: the receipt was taken on the ranked M5 host
   itself, so the +0.651% is an M5 measurement, not an M4 extrapolation. The M4
   transfer caveat applies to my §6 noise-floor work, not to the headline number.

### Smallest useful next action

**One `grep`, then one throwaway local build.** Run
`grep -n 'threadgroup_barrier' <kernel>` on every k-loop anyone is proposing to
pipeline. If the flags are `mem_threadgroup` only, the device-read overlap is
already legal for the compiler and the arm is dead before it is written. That
check costs seconds and would have saved this arm plus the submission it spent.

Then, to close §9 from "leading explanation" to "measured": route 2 in §9 — flip
one bracketing barrier to `mem_threadgroup | mem_device` in a **throwaway local
build** and re-measure the **stock** path. If the hoisting story is right, adding
the device fence should slow stock prefill by roughly what my arm lost. It is a
diagnostic that can only remove performance, so it must never be submitted. On my
host §6's noise floor (≥1.1% on `S`) is marginal against a ~0.65% expected effect,
so this wants either many local repetitions or a receipt — I would not spend a
receipt on it while promotion is 1.16% away.

The cheaper half of the same question is
`MTLComputePipelineState.maxTotalThreadsPerThreadgroup` for both pipelines: 1024
in both means register pressure is not the story and scheduling freedom is.

### Suggested follow-ups I did not implement

1. ~~**Prefetch depth** `tiles_ahead` 1 → 2.~~ **Retracted by my own §9.** I
   recommended this in §7 before the receipt landed; it is the same mechanism as
   the arm that just lost, only deeper, so it inherits the same fatal premise —
   there is no barrier fencing the device read, so there is nothing to prefetch
   *past*. It would buy the same zero overlap at ~9 more registers, i.e. strictly
   worse than what I measured. **Do not assign it.** Read §7 as evidence that the
   brief's LSU motivation is stale, not as a live proposal.
2. Extend the compile gate to the remaining NAX families so M5-only code stops
   being submitted unverified from non-M5 hosts.
3. Fix the three stale comments (`fp_quantized_nax.h:350-357`, `:1751-1753`,
   `quantized.cpp:1445-1450`) and the two prose/code mismatches (`:1365`
   vs `:1383`; `:1642` vs `:1478`).
4. Delete `STAGE_BM128` cases 1/2/3 — §2 proves they cannot reach the expert
   kernel.
5. Do **not** quantize `attn_proj_qkvo` for prefill: 512 FLOP/byte, 24.34 ms
   compute vs 5.70 ms DRAM, so it shaves already-hidden bytes while adding
   dequantization to the binding term.

### Recommendation

**Close this PR as a negative. Do not promote, do not request a revision, and do
not assign a follow-up in this mechanism family.**

The code is bit-exact and every gate passed, so it is *safe* to merge — but it is
0.651% slower on a scored axis, so merging it would cost score for nothing. The
value is entirely in §9, §8, §4 and §2, all of which are in `research/` and
survive closing the branch.

Specifically, I recommend you **retire the following from the board**:

1. This arm and its whole family: expert-GEMM weight-stage double buffering (your
   C1), `BN=32` (C2), C1+C2 bundled, and prefetch depth. §9 kills the mechanism;
   §4 kills C2 independently and by compilation.
2. `STAGE_BM128` cases 1/2/3 (§2 — cannot reach the expert kernel).
3. Quantizing `attn_proj_qkvo` for prefill (already retracted, 512 FLOP/byte).

And I recommend you **reprice the prefill axis** before funding another arm there.
The ~28.17 ms DRAM floor stands, but §9 says the 98.153 → 28.17 gap is not
overlap-recoverable, so the honest prize on that block is much smaller than
16.75–22.69 ms. tanjiro's `BW` and `TFLOP/s` from #27 are still the right input,
but §9 changes what they are an input *to*: they now bound how much work is
irreducible, not how much scheduling slack exists.

One thing I would push back on: §8 shows our prefill is effectively tied for
best-in-field and that no one in 926 correct receipts has moved it. Combined with
§9, the natural read is "prefill is structurally protected", and the temptation is
to abandon the axis and put everything on decode. I would not go that far — 25% of
the exponent is real, and §8 also shows a genuine prefill gain would be
unprecedented in the field, i.e. high value if found. But it should be funded as
**work removal** (fewer FLOPs, fewer bytes, fewer dispatches), not as
rescheduling, and it should be funded at a lower rate than decode until someone
finds a mechanism that survives the §9 grep.

Finally, on process: this arm cost one submission to learn something a `grep`
would have told us. If it is useful, I would support a standing rule that any
overlap/pipelining assignment must state the barrier flags of the loop it targets
before it is assigned.
