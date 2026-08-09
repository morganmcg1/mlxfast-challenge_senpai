# r98-A — Decode attention QMV in-flight-load audit and K-block prefetch

**Student:** maple-frieren · **PR:** #539 · **assignment_id:** `maple-r98-a-decode-attn-qmv-mlp` ·
**revision_id:** `r98-a-rev1` · **base_sha:** `450953e5c8287bfa1f409addf568d7851458cf94`

Companion audit: [`research/frieren-r98-inflight-audit.md`](frieren-r98-inflight-audit.md).

---

## 1. Preregistration (rule 68)

**Written and committed 2026-08-09T13:40:29Z, before any receipt was read.**
Commit that carries this text: see the commit that first adds this file
(`git log --diff-filter=A -- research/frieren-r98-decode-qmv-result.md`).

### 1.1 Rung order (re-ranked from the assignment's provisional order)

The assignment listed `o_proj` (K2) provisionally first. The static AGX/AIR audit
(§2–§7 of the companion doc) inverts that order. **Rung 1 = K1 (fused QKV),
Rung 2 = K2 (`o_proj`).** Grounds, all measured this session:

| criterion | K1 (QKV) | K2 (`o_proj`) | favours |
|---|---|---|---|
| measured M4 pool | 1702.9 µs/step | 1419.5 µs/step | K1 |
| ISA growth of the prefetch edit (g16s `__compute`) | +32 B | +160 B | K1 |
| in-flight code lines per thread per K-iter | 1 → 2 | 4 → 8 | K1 (cheaper) |
| structural match to the shipped routed twin (PR #301 pattern) | exact | approximate | K1 |

### 1.2 What is changed

Only the *issue time* of the weight-code loads moves. `values_per_thread` stays
16, the load width stays `uint2`, the lane→column mapping is untouched, and the
per-lane serial float accumulation order is untouched. This is therefore **not**
the twice-closed `uint2`→`uint4` widening idea. Bit-exactness is a hard
precondition, not a hoped-for outcome.

### 1.3 Decision rule, fixed in advance

Effects are signed as **Δdecode µs/step (negative = faster)**.

- **GO** to the next rung when the arm is bit-exact **and** the decode effect is
  at least **40 µs/step** in the fast direction with a contemporaneous-control
  confidence interval that excludes zero.
- **REVERT** the rung when the effect is in the slow direction with
  prediction-|t| ≥ 2.
- **STOP the arm** when two consecutive top-ranked rungs are null
  (|effect| < 20 µs/step).

### 1.4 Receipt plan, including the conditional revert-control leg

Six official receipts are budgeted. One rung per receipt.

- **Receipt 1 — rung 1, K1 only.** `lagunaDecodeNVFP4QKVPrefetchEnabled`
  default flipped to `!= "0"` (ON on the ranked host, which sets no env vars).
  `lagunaOProjKBlockPrefetchEnabled` stays default OFF.

- **If receipt 1 is a GO** (Δdecode ≤ −40 µs/step, CI excludes 0):
  - **Receipt 2 — revert control.** Both gates default OFF, commit otherwise
    byte-identical to receipt 1's commit (same header refactor, same generator
    plumbing, same doc). This leg exists to show the measured win is the
    prefetch and not session drift or the inert header refactor. Prediction:
    receipt 2 decode returns to within ±20 µs/step of the pre-rung baseline.
  - **Receipt 3 — rung 2 added.** Both gates default ON.

- **If receipt 1 is null** (|Δ| < 20 µs/step):
  - **Receipt 2 — rung 2 only** (K1 OFF, K2 ON).
  - If receipt 2 is also null → **STOP the arm** and report the negative.

- **If receipt 1 is a REVERT** (slower, prediction-|t| ≥ 2):
  - Rung 1 is reverted. **Receipt 2 — rung 2 only.**

### 1.5 Preregistered predictions

1. **Bit-exactness.** `maximumAbsoluteLogitError == 0` for every arm, and the
   64-step drift tripwire passes. A non-zero value falsifies the whole arm
   immediately and no timing receipt is spent on it.
2. **M4 is blind to this change.** Rule 55 measured the M4 attention trio at
   92–100 % of M4 peak bandwidth, and rule 60 established that latency-hiding
   arms are structurally M4-invisible at ≥ 2 TG/core. K1 dispatches 5120 TGs
   and K2 dispatches 256 TGs, both far above that. The M4 ABBA screen is
   therefore an **occupancy/regression screen, not a confirmation**: a null is
   expected and uninformative; a *regression* means the extra live registers
   cost occupancy and that rung is reverted before any M5 receipt is spent.
3. **M5 magnitude.** PR #301 measured this exact prefetch pattern in the shared
   gate/up QMV at −4.80 % of that kernel's time (CI [−0.495, −0.232] µs/call).
   Applying −4.80 % to the 3122.4 µs/step K1+K2 pool gives a **prior of about
   −150 µs/step** if both rungs behave like the routed twin, i.e. about
   **−82 µs/step for rung 1 alone**. At 0.015280 % score per µs/step that is
   **+1.25 %** for rung 1 and **+2.29 %** for both, against a **1.0498 %**
   deficit to the current record.
4. **Score arithmetic recomputation.** `f = 4·prefill_seconds_per_token /
   decode_seconds_per_token` is recomputed from each candidate's own score JSON
   on every receipt rather than reused from a prior round.

### 1.6 What would make me abandon the arm early

- Any non-zero `maximumAbsoluteLogitError`, or a drift-tripwire failure.
- An M4 ABBA *regression* beyond the 80 µs/step M4 detection bar (rule 63–65),
  which would indicate the extra live registers cost occupancy.
- Two consecutive null top-ranked rungs, per §1.3.

---

## 2. Static audit summary

See [`research/frieren-r98-inflight-audit.md`](frieren-r98-inflight-audit.md)
for the full eight-section audit. The load-bearing findings:

- Metal AIR is misleading: it shows `x_thread[16]` spilled to `alloca`, a rolled
  16-trip activation loop, and a rolled `j` loop. The AGX native binary shows
  none of that.
- `#pragma clang loop unroll(full)` is ignored by the Metal front end.
- Manually fully unrolling K1 repairs the AIR (alloca 2→1, devload 5→20,
  privload 12→0) yet produces a **byte-size-identical AGX binary** (3584 B
  g16s, 3664 B g17s). The backend already does SROA plus unrolling, so source
  unrolling is a no-op.
- The K loop stays rolled in ISA (axis_size 1024/2048/4096 → 3296/3584/3696 B,
  sublinear), while K2's row and `j` loops are backend-unrolled.
- **Conclusion:** within-iteration ILP is already maximal (~17 outstanding
  loads). Cross-K-iteration software pipelining is the only remaining lever,
  because the compiler cannot legally rotate a load across the back-edge
  without a guard. That is exactly what this arm adds.

### 2.1 Static verification table

| variant | g16s `__compute` | g17s `__compute` | Δ vs base |
|---|---|---|---|
| K1 base | 3584 | 3664 | — |
| K1 header refactor only | 3584 | 3664 | **0** |
| K1 + depth-1 prefetch | 3616 | 3696 | **+32** |
| K2 base | 5216 | 5408 | — |
| K2 + prefetch, codes only | 5376 | 5568 | **+160** |
| K2 + prefetch, codes + scales | 5536 | 5728 | +320 |

The header refactor is proven inert at machine-code level: base and refactored
binaries are the same size (6176/6256 B) and differ in exactly **35 bytes, max
offset 1421 < 1424**, i.e. entirely inside `__AIR_DATA` (the embedded source
blob). `__reflection`, `__compute`, and `__descriptor` are byte-identical.

**Codes-only prefetch is shipped**, not codes+scales: the scale load is 4 B
against 32 B of codes per thread per K-iteration, and its latency is already
covered by the ~32 fma of the row body, so the extra 160 B of ISA buys nothing.

---

## 3. Correctness result — both arms are bit-exact (M4 Pro, `applegpu_g16s`)

Run 2026-08-09T13:49Z, commit `bc504a7c`, three arms back to back in one
process launch through `research/run_upstream_equivalence.sh`:

| step | CONTROL (both gates off) | `DARKBLOOM_QKV_KBLOCK_PREFETCH=1` | `DARKBLOOM_OPROJ_KBLOCK_PREFETCH=1` |
|---|---|---|---|
| prefill | 0.125 | 0.125 | 0.125 |
| decode-0 … decode-7 | 0 (all 8) | 0 (all 8) | 0 (all 8) |
| `EQUIVALENCE_EXACT_STEPS` | 8 | 8 | 8 |

Every arm reported `meanAbsoluteLogitError = 0.011933609` for prefill and
`0` for all eight decode steps, and every `runtimeToken` equalled its
`upstreamToken` (5991, 509, 902, 5991, 509, 902, 5991, 509, 902). The three
JSON reports are **numerically identical to each other, field for field**.

**Reading.** The prefill 0.125 is *inherited from the base and reproduces with
both gates off*, so it is the known non-M5 near-tie divergence that AGENTS.md
describes, not an effect of this arm. Both prefetch kernels are decode-only, so
prefill cannot be reached by either change; the identical control confirms it.
The preregistered §1.5.1 bit-exactness prediction is therefore **satisfied on
the decode path this arm touches, and the arm introduces no new divergence
anywhere**. Per AGENTS.md this is the case where testing the unchanged base is
required before attributing drift, and the unchanged base was tested in the
same process launch.

`EQUIVALENCE_EXIT=1` for all three arms only because the wrapper's zero
tolerance also covers prefill.

## 4. HOLD — the research base was replaced before any timing receipt was spent

Advisor comment
[#539 (comment) 5231838968](https://github.com/morganmcg1/mlxfast-challenge_senpai/pull/539#issuecomment-5231838968),
2026-08-09T13:45:52Z: a human operator moved the Maple research base onto the
promoted organizer frontier `cc6ddc1`. Advisor branch
`codex/mlxfast-maple-20260804-advisor` went `e510bb3d` →
**`4f3108c4df3b76545a7c849de38ef7c171232d1c`**, deleting
`Sources/MLXFastModel/LagunaRuntimeLayers.swift` outright and rewriting
`LagunaRuntimeModel.swift` and the `MLXLMCommon` cache/decode stack.

**State at the moment of stopping.** No official receipt had been spent, no
local scored timing had been run, and no M4 ABBA screen had been started. The
only GPU work executed was the correctness oracle in §3. Work stopped on
instruction; no benchmark was killed and no lock was left held.

**Independent confirmation of the new byte budget.** Measured, not taken on
trust: `senpai/check-editable-budget.sh 4f3108c4…` against this worktree
reports `current=2902875 growth=-80974`, so the new base is
2 902 875 + 80 974 = **2 983 849 bytes**, i.e. **16 151 bytes of headroom** and
142 files. That reproduces the advisor's figure exactly.

**What that costs this arm.** Measured against the old base, this arm's
complete diff grows the submitted surface by **+3 399 bytes** (from
`growth=3399/262144`). Ported unchanged onto the new frontier that is about
**21 % of the entire remaining headroom** for a change whose native-code cost
is 32 bytes of ISA. Almost all of the 3 399 bytes is the Swift string-literal
plumbing that carries *both* the prefetch and the non-prefetch spelling of each
loop so the gate can select at runtime. If this arm is re-issued on
`4f3108c4`, the cheap fix is to drop the runtime gate and emit only the
prefetch spelling, which removes the duplicated loop text and should land close
to byte-neutral.

### 4.1 What transfers to the new frontier, and what does not

**Transfers — none of it depends on the old file layout.**

- The whole static AGX/AIR method and its conclusions (§2): AIR is misleading
  for these kernels, `#pragma clang loop unroll(full)` is ignored, source
  unrolling is a backend no-op, the K loop stays rolled in native ISA. These
  are properties of the Metal toolchain and the AGX backend.
- The tooling: `/tmp/air/nt.sh` (compile → `applegpu-nt` → `metal-size` for
  `applegpu_g16s` and `applegpu_g17s`) and the `cmp -l` offset test that proves
  a refactor is machine-code-inert by showing all differing bytes fall inside
  `__AIR_DATA`.
- The measured M4 dispatch ledger for the attention decode pair (K1 1702.9,
  K2 1419.5, combined 3122.4 µs/step = 63.8 % of decode) as a *prior*, to be
  re-measured on the frontier because the frontier may have restructured these
  dispatches.
- The costed conclusion that a depth-1 prefetch is +32 B of ISA on K1 and
  +160 B on K2, and that codes-only beats codes+scales.
- The verified bit-exactness of the transformation itself (§3), which is a
  property of the arithmetic, not of the surrounding file.

**Does not transfer.**

- Every line anchor and every symbol name in the brief and in
  `research/frieren-r98-inflight-audit.md`.
- The claim that these two kernels are still the top-two decode consumers. The
  frontier is the `cc6ddc1` solver that holds the record 2.61650354381456; it
  may already prefetch, may have restructured the QMV schedule, or may have
  replaced these dispatches. **Re-run `research/r94_ledger_build.py` on
  `4f3108c4` before re-proposing anything.**
- The `1.0498 %` deficit figure, which was computed against the old base.

### 4.2 First check if this arm is re-issued

Before writing any Metal on the new base, grep the frontier's QKV and `o_proj`
decode QMV loops for an existing depth-1 pipeline (a `pf`/`cur` pair, or a
guarded next-block load of the form `if (k + block_size < …)`). If the
frontier already does this, the honest disposition is to close the arm rather
than re-measure it — which is exactly the audit the advisor said he is running.

---

## 5. Independent adversarial critique of the arm's own thesis

While the HOLD was in force I put the arm's physics — not its layout — to a
context-free frontier reviewer, precisely because those conclusions survive a
base swap. It was given the dispatch ledger, the static verification table, the
kernel geometries, rule 32 and rule 55, and asked six questions plus one
prediction. Its verdict is **negative for this arm and positive for a
different one**, so it is recorded here in full rather than filed away.

### 5.1 The prefetch thesis is weaker than the assignment assumed

- **Roof check, independently recomputed.** K1 h64 moves 10.49 MB of codes +
  1.31 MB of FP8 scales + 4 KB of `x` ≈ 11.8 MB per call, ×30 calls =
  354 MB/step ÷ 1340.1 µs = **264 GB/s ≈ 97 % of the M4 Pro 273 GB/s spec**.
  K2 lands at 254–263 GB/s (93–96 %). Rule 55's "at the roof" is therefore a
  real physical statement, not a bookkeeping artifact.
- **At the roof, memory-level parallelism relocates waiting; it does not create
  bandwidth.** Little's law on M4 Pro: 273 GB/s ÷ 20 cores × ~400 ns ≈ 5–7 kB
  of in-flight bytes needed per core; 1024 threads/core × 8 B (`uint2`) ≈ 8 kB
  supplied. Saturated, but with only a **~1.2–1.5× margin**. Depth-1 prefetch
  can only pay where that margin has already been lost.
- **The M5 is the only channel through which this arm can win.** 614 GB/s ÷ 40
  cores = 15.4 GB/s/core, i.e. **+12 % per-core in-flight demand** against an
  unknown G17 memory subsystem. A ~1.2× margin does not survive a 1.12×
  demand increase with much room to spare. That is the whole story of the arm.
- **The PR #301 prior does not transfer.** −4.80 % on K1's 264 GB/s would imply
  >280 GB/s, above the M4 Pro spec. The shared gate/up QMV where #301 won must
  therefore have been sitting **below** its roof — different in exactly the
  variable that decides this arm. My −150 µs/step extrapolation in §1.5 was
  built on that prior and should be treated as retired.
- **Depth-1 is the wrong depth for a 4-trip loop.** With load latency L and
  per-trip compute C, C ≪ L here: depth-1 saves ≈ 3·min(L,C) = 3C, roughly
  **10–20 % of what a full depth-4 hoist would save** (L + 4C versus 4(L + C)).
  Amendment A already reserved receipt 4 for the depth-4 hoist; this says the
  depth-4 hoist should have been rung 1, not rung 4, *if* one credits a
  latency-bound story at all.
- **Calibrated prediction: P(depth-1 K1 prefetch ≥ 40 µs/step on M5) ≈ 12 %
  [10–15 %], expected effect ≈ 0 ± 10 µs/step.** For +32 B of ISA and ~+2
  registers it remains a cheap ticket, but it is a lottery ticket.

### 5.2 Rung 2 (K2 prefetch) is worse than rung 1, for a reason I had missed

K2 already holds ≈ 819 threads/core × 32 B ≈ 26 kB in flight per core, 4–5×
the Little's-law requirement — its per-core load-return queues are already
oversubscribed, so 4→8 outstanding loads lengthens a queue rather than hiding
anything. It also costs **+160 B of ISA and ~+8 registers** versus K1's +32 B
and +2. Rung 2 should be dropped outright, not merely demoted.

### 5.3 The register cliff, which the arm never priced

Mesa's AGX table (`agx_performance.c`, ~208 KiB register file per core) maps
half-register footprint to threads/core: 104 → 1024, 112 → 896, 128 → 832,
144 → 704, 160 → 640, 208 → 512. **The first cliff is at > 52 32-bit registers:
1024 → 896 threads/core, −12.5 % residency.** Depth-1 (+2 regs) is safe by
inspection; the depth-4 hoist (+6 regs) crosses at most one step but only near
a boundary — and given K1's thin saturation margin, one residency step-down is
exactly the kind of thing rule 32 shows costs far more than the mechanism
could refund. Static recovery of the count is possible via a peak-live /
max-register-index scan of the `applegpu` disassembly; the cheap authoritative
check is to read `MTLComputePipelineState.maxTotalThreadsPerThreadgroup`
on-box and watch for a 1024 → 896 drop. **G17's table is unpublished, so this
must be a dynamic check on the M5.** This closes the occupancy question I left
open in §2 with a method rather than a number.

### 5.4 Rule 32 read the other way round

The +174.9 µs/step coarsening penalty **corroborates the bandwidth roof and
undercuts the latency-bound reading**. At 640 TGs the kernel runs ~2 residency
waves with 8×-longer dependent chains; during the drain fraction the resident
in-flight bytes fall below the per-core requirement and bandwidth sags. In
other words K1 hides latency by **thread-level** parallelism with a thin
margin: removing threads hurts immediately, while at 5120 TGs it sits on the
flat roof where extra per-thread MLP is redundant. **The hazard for these
kernels is occupancy loss, not missing MLP.**

## 6. The follow-up I am not implementing: K2 is under-parallelized for a 40-core M5

The reviewer's highest-value alternative is a *different mechanism* on the same
kernel pool, and my own arithmetic against the programme's residency-ceiling
law (rule from `RESEARCH_ARCHIVE_through-round-91.md:2905-2910`: ~480
concurrent TGs on a 20-core M4 Pro = 24 TG/core; ~960 on a 40-core M5 Max)
makes it stronger than the reviewer stated:

| machine | K2 TGs | TGs/core | vs 24 TG/core ceiling |
|---|---|---|---|
| M4 Pro, 20 cores | 256 | 12.8 | **53 % residency** |
| M5 Max, 40 cores | 256 | 6.4 | **27 % residency** |

K2 launches `(out_vec_size / 8) × 64` threads = **256 threadgroups**, fixed by
`results_per_simdgroup = 4` × `num_simdgroups = 2` = 8 output rows per TG over
`out_vec_size = 2048`. It is a **single sub-capacity wave on both machines**,
with no second wave to hide the tail, and it is *twice as under-parallelized on
the ranked M5 as on the host where it was measured at 93–96 % of roof*. The
integer split is also uneven on M5 — 7 versus 6 TGs per core, a ~9 % straggler
tail that no amount of prefetch can touch.

The bit-exact lever is to reduce `results_per_simdgroup` from 4 to 2 (→ 512
TGs) or to 1 (→ 1024 TGs). This is **row splitting, not split-K**, and I
checked it against the actual kernel body rather than asserting it
(`Sources/MLXFastModel/LagunaRuntimeModel.swift:3992-4062` on `e510bb3d`):
`column = simd_lid * values_per_thread`, the k-loop stride `block_size`, the
`result[row] += scale * accum + sum * bias` order, and the closing
`simd_sum(result[row])` are all **independent of `results_per_simdgroup`**.
Only `out_row = tile * (num_simdgroups * results_per_simdgroup) + simd_gid *
results_per_simdgroup` changes, i.e. *which* threadgroup owns a row, never how
that row is summed. DRAM traffic is essentially unchanged — weight rows are
still read exactly once; the extra cost is re-reading the 8–16 kB `x` vector
(L2) and redoing the per-block gate multiply, which is ALU on a kernel that is
at 93–96 % of its memory roof.

This is the exact **inverse of rule 32**. Rule 32 measured *coarsening* K1
(5120 → 640 TGs) at +174.9 µs/step. The refinement direction on the one decode
kernel that is demonstrably below residency has never been tested.

**The trap, stated up front:** the M4-optimal and M5-optimal tilings differ.
480 TGs fills a 20-core M4 Pro; 960 fills a 40-core M5 Max. So
`results_per_simdgroup = 2` (512 TGs) is near-ideal on M4 but still only 53 %
on M5, while `= 1` (1024 TGs) is optimal on M5 but ~2.1 waves on M4. This is
precisely the "threadgroup geometry can change sign across core counts" case
`AGENTS.md` warns about, and it means **an M4 A/B on this lever is close to
worthless** — the arm has to be written as a paired M5 receipt with the M4 run
used only for correctness. Estimated ceiling ≈ the 4 % roof gap ≈ 45 µs/step;
reviewer's odds of ≥ 20 µs on M5 ≈ 35–45 %, versus 12 % for this arm's rung 1.

Two cheaper things worth doing before either: (a) an **on-box M5 roofline
audit** — achieved GB/s for K1 and K2 against a saturating pure-read
microbench, which would settle whether K1 is provably finished; and (b)
**Σ(kernel GPU time) versus decode-step wall time**, which prices inter-dispatch
gaps that per-kernel GB/s cannot see.

**Every number in §5 and §6 was derived on the `e510bb3d` base and must be
re-derived on `4f3108c4` before it is acted on** — starting with whether the
promoted frontier already re-tiled K2. The reasoning is machine physics and
survives the base swap; the geometry constants may not.

---

## 11. Reply

**To the advisor's HOLD, 2026-08-09T13:45:52Z.**

Acknowledged and complied with. Concretely:

1. **Stopped.** No official receipt was spent, so nothing measured on
   `e510bb3d` will be pushed as a result. No local scored timing and no M4 ABBA
   screen were started. The only GPU work that ran was the correctness oracle,
   which was already in flight; it completed normally, so no lock was wedged
   and no model-holding process was orphaned.
2. **Did not rebase.** I fetched `4f3108c4` read-only to confirm your byte
   figure and did not touch the working tree's base.
3. **Notes committed**, as you asked, in this file and in
   `research/frieren-r98-inflight-audit.md`.

**Four findings that are worth having before you decide (a) or (b).**

- **The transformation is bit-exact, and that is now measured rather than
  argued** (§3). Control and both arms produce field-for-field identical
  equivalence reports on this M4 host. The prefill 0.125 you may see in the log
  is present with both gates off, so it is the base's known non-M5 near-tie
  divergence, not this arm. If you re-issue on `4f3108c4`, the bit-exactness
  question is already answered for the transformation; only reachability has to
  be re-established.
- **I independently reproduce your headroom number: 16 151 bytes.** My arm's
  diff is +3 399 bytes against the old base — about 21 % of that headroom for
  32 bytes of actual ISA. The overhead is entirely the runtime gate carrying
  two spellings of the loop. If you re-issue, please let me emit only the
  prefetch spelling and drop `DARKBLOOM_QKV_KBLOCK_PREFETCH`; that should be
  close to byte-neutral and removes the byte objection.
- **The strongest static result of the round is a negative one that changes how
  future arms should be written**: for these kernels the AGX backend already
  does SROA and unrolls the inner loops, `#pragma clang loop unroll(full)` is
  silently ignored by the Metal front end, and manual source unrolling produces
  a byte-size-identical native binary. Metal AIR is actively misleading here.
  Any future arm reasoning from AIR — on this base or the frontier — is
  reasoning from a fiction, and should be checked with `applegpu-nt` first.
  That holds no matter which disposition you choose.
- **I used the hold to attack my own thesis, and it lost** (§5). A
  context-free frontier review of the arm's physics puts
  P(rung 1 ≥ 40 µs/step on M5) at ≈ 12 %, expected ≈ 0 ± 10 µs/step; shows the
  PR #301 −4.80 % prior cannot transfer, because −4.8 % on K1 would imply
  >280 GB/s, above the M4 Pro spec, so #301's kernel must have been below its
  roof; shows depth-1 captures only 10–20 % of a depth-4 hoist on a 4-trip
  loop; and shows rung 2 should be dropped outright, not demoted. It also reads
  rule 32 against me: the coarsening penalty is evidence the kernel hides
  latency by **thread-level** parallelism at the roof, so the hazard here is
  occupancy loss, not missing MLP. §5.3 closes my open occupancy question with
  a method — the first AGX residency cliff is at > 52 32-bit registers
  (1024 → 896 threads/core), and the cheap authoritative probe is
  `MTLComputePipelineState.maxTotalThreadsPerThreadgroup` read on-box.

**On disposition, my honest read — which the critique changed.** I no longer
think rung 1 deserves a receipt on its own merits. If your audit shows the
`cc6ddc1` frontier already pipelines these loops, close the arm. If it does
not, I would still close it, and I would rather you spend the slot on §6.

**§6 is the thing I would ask for instead.** K2 launches **256 threadgroups**,
which is 12.8 TG/core on this 20-core M4 Pro and only **6.4 TG/core — 27 % of
the ~24 TG/core residency ceiling — on the 40-core ranked M5**. It is a single
sub-capacity wave with no second wave to hide its tail, and it is twice as
under-parallelized on the machine that scores us as on the machine where I
measured it at 93–96 % of roof. The bit-exact lever is `results_per_simdgroup`
4 → 2 or 4 → 1 (row splitting, not split-K: lane→element mapping and the FP32
`simd_sum` tree are untouched, weight rows are still read exactly once). That
is the exact inverse of rule 32, and the refinement direction has never been
tested. Ceiling ≈ 45 µs/step, odds of ≥ 20 µs on M5 ≈ 35–45 %. The honest
caveat is in §6: M4-optimal and M5-optimal tilings differ (480 vs 960 TGs), so
this must be written as a paired M5 receipt with M4 used only for correctness —
an M4 A/B would be close to worthless. Cheapest precursor is an on-box M5
roofline audit plus Σ(kernel GPU time) versus decode-step wall time.

I will wait for your revision or close rather than act on my own initiative.
§4.1 lists what I would re-verify first on `4f3108c4`, starting with rebuilding
the dispatch ledger rather than trusting the old one; every constant in §5 and
§6 was derived on `e510bb3d` and needs the same treatment.
