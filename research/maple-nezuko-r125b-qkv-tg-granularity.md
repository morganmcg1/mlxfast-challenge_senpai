# R125-B — decode QKV threadgroup-granularity ladder (the `ns` axis at `rps = 1`)

Student: maple-nezuko. Assignment `maple-r125-b-qkv-tg-granularity-ladder`,
revision `r125-b-rev1`, PR #730.
Branch `maple-nezuko/r125-b-qkv-tg-granularity-ladder`, base
`a9de9e8f21188715f6d80ada4b581bcd50d4ec81`.
Host: Apple M4 Pro, 20 GPU cores, 48 GiB, `applegpu_g16s`, macOS 26.5.2.
W&B (one run, all 12 rows):
[`fwgtejl5`](https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/fwgtejl5).
No official receipt was spent by this experiment.

## §0 Verdict

**REFUTED, and nothing lands. Landing branch: none — deliberately.**

The `ns` (simdgroups-per-threadgroup) axis on decode QKV at `rps = 1` does not
pay. Widening the threadgroup from 64 to 128 or 256 threads at pinned total
simdgroups is bit-identical and, at this instrument's resolution, **dead flat**:
both paired medians sit within **0.3 µs/step of zero on an 8,884 µs/step level**
(that is 3 parts in 100,000), each block splits **2 wins / 2 losses**, and both
intervals comfortably contain zero *and* every debit the fleet's `tgMem = 0` law
predicts (§4.4). The assignment's landing rule needs bit-identity **and** a
paired interval excluding zero *in the improving direction*; the second conjunct
fails, so I land nothing. **The winning rung is N2 — which is already the
compiled default — so the correct landing hunk is the empty hunk** (§7).

| arm | `ns` | threads/TG | paired median Δ vs N2, µs/step (minimize) | bootstrap CI95, µs/step | covers 0 | blocks won | bit-identical | lands? |
|---|---:|---:|---:|---|---|---:|---|---|
| N2 (ref, shipped) | 2 | 64 | — (level **8882.814**) | — | — | — | — | already default |
| N4 | 4 | 128 | **+0.23** | [−25.34, +47.05] | YES | 2 / 4 | yes (`max_abs_diff = 0`) | **no** |
| N8 | 8 | 256 | **−0.07** | [−31.58, +24.15] | YES | 2 / 4 | yes (`max_abs_diff = 0`) | **no** |

Sign-test p = **1.0000** on both contrasts (2 negative / 2 positive). Every one
of the 12 timed runs returned `passed_correctness = true` and the *same* golden
hash `f49e4c2c…702b03d2`.

Four things this episode produced that are worth more than the null:

1. **A third site consistent with `L-TG-WIDTH-IS-A-DEBIT-AT-tgMem-0`**, on a
   *different* kernel (decode NVFP4 QKV, 19.9 % of decode busy) from frieren's
   #714 and alphonse's #729. Stated precisely, because the distinction matters:
   my ladder does **not** independently confirm the debit — my interval contains
   zero *and* contains all three candidate magnitudes (§4.4 step 1). What it
   does do is **exclude the win** that the (retracted) prior demanded: the
   +50…+250 µs/step improvement the assignment pre-registered is ruled out by a
   wide margin, in the direction the law predicts.
2. **An achieved detection floor, stated as arithmetic and now as a *measured*
   paired sd** (§4.4 step 2): the paired block sd is **22.94 µs/step (N8)** and
   **34.11 µs/step (N4)**, so this instrument's CI95 half-width at B = 4 is
   **±36.5 to ±54.3 µs/step** — **1.3×–11.6× too coarse** to price the predicted
   debit (+4.7 … +27.5 µs/step). That is the number my §1.6 should have carried
   and did not; I am publishing it as the deliverable rather than pretending the
   ladder resolved something.
3. **A bound that closes the axis regardless of the debit's exact size**
   (§4.4 step 3): the most generous corner of either *measured* interval is a win
   of **31.6 µs/step** (N8's lower edge) = **0.36 % of decode** =
   **0.21 – 0.24 % of `cs`**; even the pessimistic reading — the full ±54.3
   µs/step half-width of the noisier contrast — is **0.36 – 0.41 % of `cs`**.
   Both are below σ(officialScore) = **0.49 %**. So no `ns` setting on this kernel
   can produce a receipt-visible change, and the axis needs no further blocks
   from anyone.
4. **A byte-level pre-screen that beat the ladder to the answer.** §1.8 —
   committed **before any timing and before the advisor's retraction** — killed
   the shared-L1 upside from `staticThreadgroupMemoryLength = 0 B` alone. §4.4
   step 4 generalises it into a power ratio the fleet can apply before building
   a ladder at all.

The prior that motivated the assignment (a "+0.38 % win from TG = 256") was
sign-inverted at the source; §4.0 documents the correction with units and
direction on every number and `PREDICTED` tags on every counterfactual.

*(§1 below was committed as its own earlier commit, before any code and any
measurement, exactly as required; `git log --reverse` on this branch shows the
order.)*

---

## §1 Pre-registration (written before any arm was timed)

> **Preserved verbatim.** Nothing in §1 has been edited since its own commit
> (`51c596c1`, plus amendment `4d31462c`), both of which precede every code and
> data commit on this branch. Two of §1's *inherited premises* were retracted at
> source afterwards, at 11:40:27Z: the "+0.38 % win from TG = 256" (§1.2, §1.4)
> and the "2.1 µs per saved MB" constant derived from it (§1.4, → the
> `≈ 1230 µs/token` figure, which was always tagged as a prediction and is now
> tagged `PREDICTED`). **§4.0 carries the correction.** I am deliberately not
> back-editing the pre-registration to look smarter than it was — the whole
> point of committing it first is that it records what I actually believed, and
> §1.8 is only interesting *because* §1.2 is still sitting above it unrevised.

### 1.1 The axis and the ladder

The decode QKV projection runs one output row per simdgroup (`rps = 1`, closed
at 1 by R122-B / PR #719) and today packs **2 simdgroups into a 64-thread
threadgroup**. The `ns` axis moves *threads per threadgroup* and *threadgroup
count* while holding constant:

* total simdgroups launched (`rows`: 10240 for h64, 8192 for h48),
* rows per simdgroup (1),
* every byte read from device memory (identical addressing: `out_row =
  tile * num_simdgroups + simd_gid` is a pure re-partition of the same
  `out_row` set),
* per-core simdgroup residency demand (10240 / 20 = 512 per core at C = 20;
  10240 / 40 = 256 per core at C = 40 on the ranked M5).

| arm | `ns` | threads/TG | TGs h64 | TGs h48 | role |
|---|---|---|---|---|---|
| **N2** | 2 | 64 | 5120 | 4096 | control (shipped geometry) |
| N4 | 4 | 128 | 2560 | 2048 | ladder fill |
| **N8** | 8 | 256 | 1280 | 1024 | primary (matches frieren's winner) |
| N16 | 16 | 512 | 640 | 512 | far arm, only if the first three are clean |

Weight: `decode_nvfp4_qkv_h64` = 1342.1 µs/step and `_h48` = 363.5 µs/step,
so 1705.6 µs/step ≈ **19.9 %** of the 8,567 µs decode busy budget.

### 1.2 Predicted sign and magnitude for N8 (the falsifiable claim)

Advisor's expectation on the assignment is **N8 beats N2 by 50–250 µs/token**,
N4 intermediate, N16 worse.

I pre-register a **narrower and partly contradictory** prediction, because the
two pieces of evidence I have point in opposite directions and I want the
disagreement on the record before the data:

1. **Ceiling argument (mine).** R122-B measured this same kernel at
   **94.3 % of measured peak DRAM bandwidth** for h64 and 92.8 % for h48
   (256.7 GB/s measured peak). If QKV time is bandwidth-bound, the *entire*
   headroom on this kernel is `(1 − 0.943) × 1342.1 + (1 − 0.928) × 363.5`
   ≈ **102 µs/step**. No reorganisation that keeps every byte identical can
   beat that ceiling. Therefore the advisor's window is only reachable in its
   bottom half, and its top half (150–250 µs) is *impossible* unless the
   94.3 % figure is wrong.
2. **Point prediction.** I predict
   **Δ(N8 − N2) ∈ [−100, 0] µs/token, most likely ∈ [−40, 0]**, i.e. a small
   improvement or a null, and I state up front that I expect the **null** to be
   the outcome, because a kernel at 94.3 % of measured peak has almost nothing
   left to win from L1-side reuse.
3. **N4** predicted at ⅔ of N8's effect (see 1.4), N16 predicted worse than N8
   (512 threads/TG risks crossing an occupancy tier).

Pre-registered decision rule: N8 counts as a **win** only if the paired
block-bootstrap CI95 on the median paired delta versus N2 **excludes zero** and
`max_abs_diff == 0` versus N2. Anything else lands nothing.

### 1.3 What would refute the shared-L1 account

The candidate mechanism behind frieren's PR #714 result on
`lagunaSharedSwiGLUQMV` (64 → 256 threads/TG, total simdgroups pinned at 512,
+0.38 % score, bit-identical) is **shared-L1 activation reuse**: the 4096-byte
activation row (2048 bf16) is pulled L2 → L1 once per *threadgroup* instead of
once per *simdgroup*, so raising `ns` from 2 to 8 cuts activation-row fetches
4×, at identical DRAM traffic.

The account is refuted, on this kernel, by any of:

* **R1 — flat ladder.** N4 and N8 both inside a CI95 that contains zero. Then
  either the reuse does not exist on this kernel or it is already saturated;
  in the latter case the binding constraint is DRAM, not L1 fetch count, and
  the observable that predicts it is %-of-measured-peak (see §1.5).
* **R2 — wrong ladder shape.** A non-null effect whose N4 : N8 ratio is not
  0.667 ± CI (see 1.4). Fetch-count reduction is the *only* free parameter in
  the shared-L1 story, so a ladder that moves but not as `(1 − 1/ns)` means
  something else is moving (dispatch overhead, tail quantisation, scheduler
  granularity).
* **R3 — wrong sign.** N8 slower than N2 with a CI excluding zero. Shared-L1
  reuse cannot cost time; a loss means threadgroup granularity is buying an
  occupancy or launch-tail penalty that dominates any reuse.
* **R4 — cross-kernel constant fails by >3×.** See 1.4: the shared-L1 story is
  a *quantitative* one, and its µs-per-MB-of-saved-L2-traffic constant has to
  be within a small factor across kernels or it is not a mechanism, it is a
  curve fit.

Note the confound I *cannot* remove: N16 being worse is **not** a refutation of
shared-L1, because 512-thread threadgroups may cross an occupancy tier
independently. N16 is therefore reported but not used to adjudicate R1–R4.

### 1.4 Quantitative cross-kernel prediction implied by shared-L1

Saved L2 → L1 activation fetches per kernel invocation, going from `ns = a`
to `ns = b`, with `S` total simdgroups and `A` activation bytes:

    ΔBytes = A · S · (1/a − 1/b)

**frieren, `lagunaSharedSwiGLUQMV`** (`S = 512`, `A = 4096` B, `a = 2`,
`b = 8`): ΔBytes = 4096 · 512 · (0.5 − 0.125) = **0.786 MB per invocation**.
If that kernel runs once per layer over 39 layers, 30.7 MB/token buys the
reported ≈ 65 µs/token, i.e. a constant of **≈ 2.1 µs per MB of saved L2→L1
traffic**.

**This kernel, decode QKV** (`A = 4096` B; `S = 10240` for h64 and `8192` for
h48). Per invocation, `ns` 2 → 8: h64 ΔBytes = 4096 · 10240 · 0.375 =
**15.7 MB**; h48 = 4096 · 8192 · 0.375 = **12.6 MB**. Invocation counts: the
measured per-row cost is equal across the two shapes
(1342.1/10240 = 0.1311 vs 363.5/8192 = 0.0444 µs/row … ratio 2.95), which
pins n(h64)/n(h48) ≈ 2.95, so with 39 layers n(h64) ≈ 29, n(h48) ≈ 10.
Saved traffic per token = 29 · 15.7 + 10 · 12.6 ≈ **581 MB**.

At frieren's 2.1 µs/MB that predicts **≈ 1230 µs/token**, which is **72 % of
the entire QKV busy time and 12× my own bandwidth ceiling of 102 µs**. This
is the single most useful thing in this pre-registration: **the shared-L1
account, taken literally and scaled by its own free parameter, predicts an
impossible number on this kernel.** Consequences, all registered in advance:

* If the measured N8 effect is ≲ 102 µs, the shared-L1 constant is **not**
  transferable and the mechanism is at best a bounded, saturating one — R4
  fires, and frieren's win needs a different (or additional) explanation, most
  plausibly that `lagunaSharedSwiGLUQMV` sits far from its bandwidth ceiling.
* If the measured effect is ≈ 0, R1 and R4 both fire and the *predictive*
  content of the episode collapses to the one-line gate in §1.5.
* Only a measured effect of many hundreds of µs would vindicate the literal
  shared-L1 scaling, and I predict that will not happen.

### 1.5 The gate being tested (the result I expect to land instead)

R122-B established a **selection rule** the advisor has adopted: gate geometry
assignments on **percent-of-measured-peak** bandwidth. o_proj was at
83.4–90.7 % when the R117-C geometry change won −79 µs; QKV is at
92.8–94.3 % and the `rps` axis was a monotone loss.

The pre-registered secondary hypothesis is therefore: **%-of-measured-peak
gates the `ns` axis as well as the `rps` axis.** It is confirmed if N8 is
neutral here (94.3 % of peak) while frieren's lower-utilisation kernel gained
1.6 %; it is falsified if N8 wins materially on a 94.3 %-of-peak kernel, which
would mean the gate is `rps`-specific and cannot be used to triage `ns` work.

### 1.6 Instrument, pre-committed

* One binary, env-switched arms; `research/maple-nezuko-r107j-certify.sh`
  (blocked, position-balanced, interleaved, first arm = reference, one build for
  all runs, FATAL if an arm's kernel set changes).
* `--local-submit` walls only (1023 steps, σ ≈ 5.9 %). **Never** priced from
  `--local-iterate` (σ ≈ 33.6 %, and a 1.442× prefill-amortisation scale gap).
* Warmed isolated 39-layer chain, steady tail tokens ≥ 16.
* Planned campaign: arms `N2`, `N4`, `N8`, **4 blocks = 12 runs** (~40 min at
  ~198 s/run). Mirrored orders reported separately. Bootstrap CI95 on the
  median paired delta plus the block-paired estimator. Bimodality screen ⇒ stop.
* Raw TSVs committed under `research/r125b-runs/`.
* Correctness: `max_abs_diff == 0` vs N2; golden hash
  `b9509697c08a2cf3c2943a85f0b76e39c485c441794690fa76835b40a58d7a63`;
  `research/run_upstream_equivalence.sh` with non-zero test count;
  `EQUIVALENCE_EXACT_STEPS=8` all zero; 64-step tripwire; editable-budget check
  against `1bc1c8954147c9e322aad1f3b80bd9fa3c0888d7`.
  `MLXFAST_LOCAL_ALLOW_GOLDEN_DRIFT=1` is never set.

### 1.7 Append-state discipline (hazard, pre-registered)

alphonse's merged #700 prepends `heads / 8` gate tiles onto the QKV grid and
that append assumes 64-thread threadgroups. So `ns ≠ 2` **must** take the
non-appended dispatch path. To keep every cross-arm comparison in the *same*
append state, **all three arms run with `DARKBLOOM_DECODE_QKV_GATE_FUSED=0`**,
including the N2 control. Consequence, registered now: the N2 control is the
shipped *geometry* but not the shipped *dispatch*, so a win for N8 over N2 is
**not** by itself a licence to land — landing additionally requires beating the
shipped appended configuration, which is a second, separate campaign.

### 1.8 Amendment, still before any timing: the mechanism is probably already saturated

Added after 1.1–1.7 and before the first arm ran, so it is part of the
pre-registration and not a post-hoc rescue. It sharpens the prediction from
"probably null" to "null for a stated structural reason".

R122-B's AGX forensics on this exact kernel established
`staticThreadgroupMemoryLength = 0 B`, and the source contains **no
`threadgroup` declaration and no `threadgroup_barrier`**. There is therefore no
threadgroup-scoped storage in this kernel at all: raising `ns` does not create
any explicit sharing between simdgroups. Whatever reuse exists is *implicit*,
in the per-core data cache.

That changes the arithmetic in §1.4 qualitatively. Apple GPU threadgroups are
resident on one core, so simdgroups within a threadgroup are guaranteed to share
that core's L1; simdgroups in different threadgroups are not. But at `ns = 2`
this kernel already launches **5120 threadgroups over 20 cores = 256
threadgroups per core** (h64), and every one of them reads the *same* 4096-byte
activation row. So the row is L1-resident on every core after the first
threadgroup touches it, in every arm of the ladder. The true L2 → L1 activation
traffic is on the order of *one row per core per invocation* — 20 × 4096 B =
**80 KB**, not the 15.7 MB the fetch-count model assigns to `ns = 2`.

Pre-registered consequence: the fetch-count model of §1.4 overcounts by
~200×, the shared-L1 headroom on this kernel is ~0, and the expected result is
**N8 ≈ N2 ≈ N4, all CIs containing zero**, with any residual movement
attributable to dispatch/launch-tail effects rather than cache reuse. If instead
a large win appears, this paragraph is wrong and the interesting question
becomes *what* is L1-resident that I think is.

This also predicts where frieren's win must come from: not from the shared
activation row (which is equally L1-resident at 64 and 256 threads/TG on that
kernel too), but from something `ns`-sensitive that is *not* cache reuse.

---

## §2 The code change

All five hunks are in `Sources/MLXFastModel/LagunaRuntimeModel.swift`, on this
branch at commit `eabdc5c2` (wiring) on top of `9ef00fcb` (inert declaration).
Symbol + line anchors as of that commit:

| # | symbol | line | change |
|---|---|---|---|
| 1 | `lagunaDecodeQKVSimdgroups` | 4839 | new `private let`, reads `DARKBLOOM_QKV_SIMDGROUPS`, restricted to `{1,2,4,8,16}`, default `2` |
| 2 | `lagunaDecodeNVFP4QKVLaneMajorSource(pairwise:tileOffset:simdgroups:)` | 4959, 4967 | new `simdgroups: Int = 2` parameter; `constexpr uint num_simdgroups = \(simdgroups);` |
| 3 | `lagunaDecodeNVFP4QKVLaneMajorKernels` | 5034–5035, 5043 | kernel name gains `_sg\(ns)` when `ns != 2`; source built with `simdgroups: lagunaDecodeQKVSimdgroups` |
| 4 | `lagunaDecodeNVFP4QKVR1`, lane-major branch | 5074, 5079–5087 | `rows % ns == 0` guard; `threadGroup = (32 * ns, 1, 1)`; `grid = ((rows / ns) * 32 * ns, 1, 1)`; trace line carries `sg`/`tg`/`tiles` |
| 5 | `lagunaDecodeNVFP4QKVGate` | 5180 | **hazard guard**: `lagunaDecodeQKVSimdgroups == 2` added to the entry `guard`, so `ns != 2` cannot reach the appended dispatch |

### 2.1 Why the default is byte-identical

* Hunk 2 defaults `simdgroups` to `2`, and the appended gate source at
  `lagunaDecodeNVFP4QKVGateSource` (line 5107 region) calls it without the new
  argument, so the *appended* MSL string is character-for-character unchanged.
* Hunk 3 appends `_sg…` only when `ns != 2`, so at the default the kernel name —
  and therefore MLX's Metal library cache key and the compiled MSL — are the
  shipped ones.
* Hunk 4 evaluates to `threadGroup = (64,1,1)` and
  `grid = ((rows/2) * 64, 1, 1)` at `ns = 2`, i.e. the previous literals.
* Hunk 5 is a no-op at `ns = 2`.

So `DARKBLOOM_QKV_SIMDGROUPS` unset ⇒ the shipped binary behaviour, which is
what makes the control arm a true A/A.

### 2.2 Why the non-default arms are bit-identical *in output*

The kernel writes `projected[out_row]` where
`out_row = tile * num_simdgroups + simd_gid`. Over the dispatch, `tile` ranges
over `[0, rows/ns)` and `simd_gid` over `[0, ns)`, so `out_row` ranges over
`[0, rows)` exactly once for every `ns` — the map is a bijection onto the same
row set. Each simdgroup then performs *the same* reduction over *the same* 2048
inputs with *the same* `simd_sum` tree (32 lanes, `execWidth = 32`, invariant),
so every output element is produced by an identical instruction sequence on
identical data. There is no cross-simdgroup communication to perturb (no
`threadgroup` storage, no barrier), and no atomics. Bit-identity is therefore
structural, not empirical — but it is also checked empirically in §3.

### 2.3 Append-state evidence

`ns != 2` must not reach alphonse's `heads / 8` grid-append. The observable is
the fusion trace: the appended path emits
`decode nvfp4 qkv+gate h<H> lane-major` and the non-appended path emits
`decode nvfp4 qkv r1 h<H> lane-major sg=<ns> tg=<32·ns> tiles=<rows/ns>`.
Evidence is in §3.1.

---

## §3 The ladder

### 3.0 Geometry of the rungs (arithmetic, no measurement)

Total simdgroups are **pinned** across the ladder — that is the whole point of
the axis. `ns` changes only how those simdgroups are *packaged* into
threadgroups, and therefore how many threadgroups the dispatcher has to place.

| arm | `ns` | threads/TG | TGs h64 | TGs h48 | simdgroups h64 | TGs/core C=20 | TGs/core C=40 | simdgroups/core C=20 | simdgroups/core C=40 |
|-----|-----:|-----------:|--------:|--------:|---------------:|--------------:|--------------:|---------------------:|---------------------:|
| N2 (ref, shipped) | 2 | 64 | 5120 | 4096 | 10240 | 256.0 | 128.0 | 512.0 | 256.0 |
| N4 | 4 | 128 | 2560 | 2048 | 10240 | 128.0 | 64.0 | 512.0 | 256.0 |
| N8 (primary) | 8 | 256 | 1280 | 1024 | 10240 | 64.0 | 32.0 | 512.0 | 256.0 |
| N16 | 16 | 512 | 640 | 512 | 10240 | 32.0 | 16.0 | 512.0 | 256.0 |

Two consequences worth stating before the numbers:

* **Residency is invariant along this ladder.** Simdgroups per core is 512
  (C=20) / 256 (C=40) for h64 at *every* rung. R117-C established that only
  **96 simdgroups/core** are grantable and that marginal latency-hiding stops
  paying at **~51/core**; every rung here is 5–10× past the grantable limit, so
  the ladder cannot move occupancy — it can only move *grouping*.
* Because `staticThreadgroupMemoryLength = 0 B` and the kernel contains no
  `threadgroup` declaration and no barrier (R122-B forensics, re-verified in
  §2), grouping has exactly two possible channels: (i) L1 locality between
  simdgroups that happen to share a core-local cache, and (ii) dispatch/tail
  granularity. Channel (i) is the shared-L1 story; §1.8 pre-registered why I
  expect it to be already saturated at `ns = 2`.

### 3.1 Correctness and append state, per rung

Every rung was run through `./benchmark.sh --local-iterate` with
`DARKBLOOM_TRACE_FUSION=1` by
`research/maple-nezuko-r125b-correctness.sh` (`OUT=/tmp/nezuko-r125b-correct`).
Timings from that pass are deliberately discarded
(`MLXFAST_LOCAL_COOL_GATE=0`, 128-step instrument, σ ≈ 33.6 %); the pass exists
only to establish the oracle and the append state before any arm is timed.

| arm | gates | trace line (h64) | trace line (h48) | `qkv+gate` line? | `max_abs_diff` | `passed_correctness` | golden hash |
|-----|-------|------------------|------------------|------------------|---------------:|----------------------|-------------|
| S (shipped, appended) | *none* | `decode nvfp4 qkv+gate h64 lane-major` | `decode nvfp4 qkv+gate h48 lane-major` | **yes** | 0 | true | `b9509697…a58d7a63` |
| N2 | `GATE_FUSED=0` | `… qkv r1 h64 … sg=2 tg=64 tiles=5120` | `… sg=2 tg=64 tiles=4096` | no | 0 | true | `b9509697…a58d7a63` |
| N4 | `GATE_FUSED=0, QKV_SIMDGROUPS=4` | `… qkv r1 h64 … sg=4 tg=128 tiles=2560` | `… sg=4 tg=128 tiles=2048` | no | 0 | true | `b9509697…a58d7a63` |
| N8 | `GATE_FUSED=0, QKV_SIMDGROUPS=8` | `… qkv r1 h64 … sg=8 tg=256 tiles=1280` | `… sg=8 tg=256 tiles=1024` | no | 0 | true | `b9509697…a58d7a63` |

Three things this table settles:

1. **Hazard (b) is closed by evidence, not by argument.** The `qkv+gate` trace
   line appears for S and for no other arm, so no `ns ≠ 2` arm ever reached
   alphonse's `heads/8` grid-append (§2.3). The `tiles=` field is the
   independent witness: it equals `rows/ns` exactly, i.e. the grid carries no
   prepended gate tiles.
2. **The golden hash is invariant along the whole ladder** and equals the
   required `b9509697c08a2cf3c2943a85f0b76e39c485c441794690fa76835b40a58d7a63`,
   with `max_abs_diff == 0` at every rung. Bit-identity is therefore verified
   empirically as well as structurally (§2.2).
3. **N2 is a legitimate reference for the timed ladder** — it is a
   *different kernel* from S (unfused, non-appended) but it is the same kernel
   as N4/N8 up to the one `constexpr`, which is exactly the pairing the axis
   needs (§1.7). The N2-vs-S gap is a property of the append/fusion axis that
   #719 and #700 already own, and it is **not** measured here; §1.7
   pre-registered that beating N2 is not by itself a licence to land.

### 3.2 The timed ladder

**Instrument.** `./benchmark.sh --local-submit` (1023 scored decode steps),
driven by `research/maple-nezuko-r107j-certify.sh` (the R117-C/R122-B script,
unchanged) through `research/maple-nezuko-r125b-campaign.sh`. **4 mirrored
blocks × 3 arms = 12 runs**, ~160 s/run, within-block order rotated by
`(block − 1) mod 3` so each arm occupies each slot. Thermal cool-down gate at
40 °C left **enabled** for every timed run. All three arms carry
`DARKBLOOM_DECODE_QKV_GATE_FUSED=0` so the append state is identical across the
ladder (§1.7). Raw rows: `research/r125b-runs/r125b-certify.tsv`.
**All numbers below are µs/step (minimize)** — one "step" is one decoded token,
so µs/step and µs/token are the same quantity on this instrument, and this is
the same unit frieren and alphonse report in.

Both tables below are **generated** from that TSV by
`research/maple-nezuko-r125b-table.py` (committed), so every number here traces
to a row rather than to my typing.

**Levels.** Geometry columns are §3.0 arithmetic; the level columns are
measured. Total simdgroups are pinned at 10240 (h64) across the ladder, so
simdgroups/core does not move — only the packaging does.

| arm | `ns` | threads/TG | TGs h64 | TGs/core C=20 | TGs/core C=40 | simdgroups/core C=20 | simdgroups/core C=40 | n runs | mean level, µs/step (minimize) | sd, µs/step | cv |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| N2 (ref, shipped) | 2 | 64 | 5120 | 256.0 | 128.0 | 512 | 256 | 4 | **8882.814** | 29.59 | 0.333 % |
| N4 | 4 | 128 | 2560 | 128.0 | 64.0 | 512 | 256 | 4 | **8888.359** | 14.22 | 0.160 % |
| N8 | 8 | 256 | 1280 | 64.0 | 32.0 | 512 | 256 | 4 | **8880.924** | 13.21 | 0.149 % |

**Paired contrasts.** Each block contributes one delta (same block, same
thermal state, rotated slot). Positive = candidate is SLOWER = worse;
the landing rule needs a CI strictly below zero.

| contrast | per-block Δ, µs/step (minimize) | median Δ | mean Δ | bootstrap CI95 (B=20000) | covers 0 | blocks with Δ<0 (a win) | sign-test p | Δ as % of step |
|---|---|---:|---:|---|---|---:|---:|---:|
| **N4 − N2** | +47.05, −19.22, −25.33, +19.68 | **+0.23** | +5.55 | [−25.33, +47.05] | YES | 2 / 4 | 1.0000 | +0.0026 % |
| **N8 − N2** | +24.14, +2.50, −31.58, −2.63 | **−0.07** | −1.89 | [−31.58, +24.14] | YES | 2 / 4 | 1.0000 | −0.0007 % |

Grand mean level across all 12 runs: **8884.0 µs/step (minimize)**.

**Notes, in the order a reviewer would ask for them.**

1. **Correctness and append state held across every timed run.**
   `passed_correctness = true` on 12/12; exactly **one** distinct golden hash
   observed, `f49e4c2cbc0d3ceee90195a3a12e1ff082636f8c031587485a9a2c10702b03d2`;
   the `kernels` column reads `none` for all three arms, i.e. no arm appended a
   fused `qkv+gate` kernel (§1.7's hazard held, as designed, because every arm
   carried `DARKBLOOM_DECODE_QKV_GATE_FUSED=0`).
2. **The paired sd is now measured, not inferred:** **22.94 µs/step** on the
   N8 − N2 contrast and **34.11 µs/step** on N4 − N2
   (`research/r125b-runs/paired-ci.txt`). At B = 4 (dof 3, t = 3.182) those give
   CI95 half-widths of **±36.5** and **±54.3 µs/step**. Both measured medians are
   two-plus orders of magnitude smaller than their own half-width (**234×** for
   N4, **562×** for N8), which is the signature of a null rather than of an
   under-powered near-miss.
3. **Order balance.** The rotation means each arm sat in slot 1, 2 and 3 once
   over blocks 1–3; restricting to that one complete rotation moves the N4
   median to **−19.22 µs/step** and the N8 median to **+2.50 µs/step** — i.e. the
   sign of the point estimate is set by which subset you look at, which is the
   cleanest possible statement that there is no effect here to attribute.
4. **The largest single block delta (+47.05 µs/step, N4 in block 1) is a
   reference artifact, not an N4 effect:** block 1's N2 run (8840.469) is the
   fastest of the 12 runs and 42 µs below the N2 arm mean, and it sat in slot 1
   of the first block, i.e. the coldest slot of the campaign. This is exactly the
   drift that the mirrored design is there to absorb, and it is why the median
   rather than the mean is the pre-registered point estimate (§1.6).
5. **Raw artifacts:** `research/r125b-runs/r125b-certify.tsv` (12 rows,
   14 columns), `research/r125b-runs/bootstrap.txt` (block bootstrap,
   `REF=N2 B=20000 SEED=125`), `research/r125b-runs/paired-ci.txt` (paired sd +
   power curve). Campaign head recorded in the TSV: `d8b104da0e1f`.
6. **W&B:** one run, `fwgtejl5` —
   <https://wandb.ai/wandb-applied-ai-team/mlxfast-maple/runs/fwgtejl5> — logged
   by `research/maple-nezuko-r125b-wandb.sh` (a thin env wrapper over the
   R117-C logger, unchanged), with the TSV attached as a run artifact.
   **Sign-convention warning for anyone reading that run:** the R117-C logger
   names its contrasts `reference_minus_arm`, so W&B shows
   `contrast/N2_minus_N4/median_us = −0.23` where this document's §3.2 table
   shows `N4 − N2 = +0.23`. Same measurement, opposite subtraction order. This
   document's convention is the one the assignment asks for — **arm minus
   reference, positive = candidate slower = worse, minimize.**

---

## §4 Mechanism

### 4.0 Record correction: the prior that motivated this assignment has the wrong sign

This has to come first, because it changes what the ladder is *for*.

The assignment (and my §1.2/§1.4) inherited a motivating claim that frieren's
#714 had measured a **+0.38 % win from TG = 256** on the shared SwiGLU QMV
kernel. My advisor's comment 4 on this PR (`r125-b-tg-prior-inverted-cheap-prescreen-1`,
11:40:27Z) retracts it. frieren's actual table is in **µs/step, direction =
minimize**:

| arm | frieren #714, µs/step (minimize) | Δ vs TG=64, µs/step (minimize) | reading |
|-----|---------------------------------:|-------------------------------:|---------|
| TG = 64  (2 simdgroups) | 289.83 ± 1.42 | — | reference |
| TG = 128 (4 simdgroups) | 290.38 ± 1.07 | **+0.55** (+0.19 %) | not significant |
| TG = 256 (8 simdgroups) | 294.50 ± 0.85 | **+4.67** (+1.61 %) | **cost** |

Her headline was **"REFUTED, φ = +0.065"**. The `+66.88 µs/step if φ = 1`
number that reached me as a measurement is a **`PREDICTED`** counterfactual
inside a refutation — the thing her data ruled out. Lower is better, so
TG = 256 was her *worst* arm, not her best.

Two independent replications now agree, both **µs/step (minimize)**:

| source | change | measured effect, µs/step (minimize) | agreement |
|--------|--------|------------------------------------:|-----------|
| alphonse #729 | TG 64 → 256 (2 → 8 simdgroups) | **+4.73 ± 0.52**, CI95 **[+2.50, +6.96]** | 3/3 blocks, 6/6 slot-pairs positive |
| edward #731 | TG 256 on the routed analogue | **+23.12** (wall) | regression |
| frieren #714 | TG 64 → 256 | **+4.67** (+1.61 %) | cost |

The fleet has banked this as **`L-TG-WIDTH-IS-A-DEBIT-AT-tgMem-0`**: with
`staticThreadgroupMemoryLength = 0` there is nothing for extra threadgroup
width to amortise, so width is an unconditional occupancy debit, priced at
**≈ +0.79 µs/step per extra simdgroup per threadgroup** on M4 Pro
(alphonse: 6 extra simdgroups × 0.79 ≈ +4.73).

The consequence for this write-up is not that the ladder was pointless — it is
that **the ladder's pre-registered upside never existed**, and the only
questions left are (a) does my kernel show the predicted *debit*, and (b) can
my instrument even see it. §4.4 answers both. It is also, bluntly, a vindication
of §1.8: I wrote the amendment that killed the upside mechanism from
`tgMem = 0 B` **before** timing anything and **before** the retraction landed,
by reading the kernel instead of the summary of someone else's ladder.

### 4.1 What the ladder shape says about shared-L1 reuse

Pre-registration §1.3 named four refutations. Scoring them against §3.2:

* **R1 (flat ladder)** — see the CI column in §3.2. A ladder whose rungs sit
  inside a CI that contains zero, or on the *slow* side of the reference, means
  the L1-fetch-count channel is not the binding constraint on this kernel.
* **R2 (wrong shape)** — the shared-L1 story has exactly one free parameter
  (fetches avoided), so the effect must scale as the *saved* fetch fraction
  relative to `ns = 2`: `1/2 − 1/4 = 0.25` for N4 and `1/2 − 1/8 = 0.375` for
  N8, hence **N4 = ⅔ · N8** — the ratio §1.2 pre-registered. A ladder that is
  non-monotone, or whose N4 : N8 ratio is far from 0.667, is moving on a
  different axis than fetch count.
* **R3 (wrong sign)** — N8 slower than N2. Reuse cannot cost time, so a
  reproducible loss localises the effect in dispatch/scheduling, not in L1.
* **R4 (cross-kernel constant off by >3×)** — §1.4 predicted **≈ 1230 µs/token
  (`PREDICTED`, not measured)** from a "2.1 µs per saved MB" constant I derived
  from frieren's #714. That is 12× my own bandwidth ceiling of **102 µs/token**,
  so R4 was pre-committed to fire for any measured effect ≲ 100 µs/token — and
  it fires. §4.0 now explains *why* it had to: the constant was extracted from a
  number that was (i) sign-inverted and (ii) itself a `PREDICTED`
  counterfactual inside a refutation. R4 was the right tripwire on the wrong
  premise; the pre-registration's arithmetic caught the absurdity
  (12× a hard ceiling) without needing the retraction.

Scored against the measured ladder, with the numbers rather than the intent:

| refutation | fires? | the number that decides it |
|------------|--------|----------------------------|
| **R1** flat ladder | **YES** | both medians within 0.3 µs/step of zero; both CI95 contain zero; 2 / 4 blocks each way; sign-test p = 1.0000 |
| **R2** wrong shape | **YES** | pre-registered N4 : N8 = 0.667. Measured medians are +0.23 and −0.07 µs/step, so the ratio is **−3.6** — not a number, a division of two zeros. On means (+5.55 / −1.89) it is **−2.9**. Either way, nowhere near 0.667, and non-monotone. |
| **R3** wrong sign | **partly — and it does not matter** | N8's median is nominally on the *fast* side (−0.07), N4's on the slow side (+0.23), both ≈ 0. So I cannot claim a reproducible loss *from my own data*; I also cannot claim any gain. §4.0's three external measurements are what supply the sign. |
| **R4** cross-kernel constant off by > 3× | **YES** | §1.4 predicted ≈ **1230 µs/token** `PREDICTED`; measured \|median\| ≤ 0.23 µs/token — off by **> 5000×**, and 12× my own bandwidth ceiling in the first place |

Three of the four pre-registered refutations fire outright and the fourth
(R3) is indeterminate in the only way a true null can be. The shared-L1 account
of this kernel is dead, and it is dead for the reason §1.8 and §4.2 give — there
is nothing shared to amortise when `tgMem = 0 B`.

### 4.2 Why a kernel at 94 % of measured peak has only downside left

The mechanical reading, stated in §1.8 before any timing and unchanged by it:

* `staticThreadgroupMemoryLength = 0 B`, no `threadgroup` declaration, no
  barrier. Nothing is *shared* between the simdgroups of a threadgroup by
  construction; the only sharing available is incidental L1 residency.
* The activation row is 4096 B and **every** simdgroup on the machine reads the
  same row. With 20 cores that is ≈ 20 × 4096 B = **80 KB** of real L2 → L1
  activation traffic per invocation regardless of `ns`, because the second and
  subsequent readers on a core hit in L1 whether or not they are in the same
  threadgroup. The fetch-count model of §1.4 counts *requests*, not *misses*,
  and therefore overcounts the traffic by ≈ 200×.
* Weight traffic — which is what actually saturates the kernel — is untouched:
  every simdgroup reads its own disjoint rows in both geometries.

So the byte-level model says the candidate mechanism is already saturated at
`ns = 2`, and the measured ladder is then a measurement of the residual
channels only — and those are all costs: coarser dispatch units give the
scheduler less freedom to balance 20 cores, and a bandwidth-saturated kernel
converts any perturbation of the DRAM access interleave directly into time.
That is the asymmetry worth remembering: **at 94 % of peak, geometry has no
upside left and still has downside.**

### 4.3 Does percent-of-measured-peak gate this axis?

This is the transferable deliverable, and the ladder is a real test of it
because it was pre-registered as such (§1.5). The evidence now spans three
geometry experiments on the same family of kernels:

| kernel | % of measured peak (256.7 GB/s) | geometry change | measured effect |
|--------|--------------------------------:|-----------------|-----------------|
| o_proj, R117-C (#707, merged) | 83.4 – 90.7 % | rps 4→2 **and** ns 4→2 | **−79.4 µs/token** Stage 1, −82.4 mean Stage 2, CI95 [−98.6, −66.3] |
| decode QKV, R122-B (#719) | 92.8 – 94.3 % | rps 1→2,4,8 | monotone **worse** (Q8 +205.9 µs) |
| decode QKV, R125-B (this) | 92.8 – 94.3 % | ns 2→4→8 | **null**: N4 +0.23, N8 −0.07 µs/step, both CI95 covering zero (§3.2) |

Read as a gate: **the only kernel that paid is the one with ≥ 9 points of
headroom to measured peak; the kernel at ≤ 6 points has now refused two
independent geometry axes** (`rps` in #719, `ns` here). That is a cheap,
computable pre-filter — measured
bytes ÷ measured time ÷ measured peak — and it is the thing I would apply to
the next geometry proposal before spending 40 minutes of ladder on it.

Two honest limits on that claim: (i) three points, two kernels, so it is a
gate, not a curve; (ii) it is a *necessary*-condition gate only — o_proj having
headroom did not by itself guarantee the win, it was a joint change of `rps`
and `ns`.

### 4.4 Reconciling my ladder with `L-TG-WIDTH-IS-A-DEBIT-AT-tgMem-0`, and the power arithmetic I should have done first

**Step 1 — the quantitative cross-kernel scaling, done three ways.** My QKV
kernel has `staticThreadgroupMemoryLength = 0 B` (§1.8, read out of the compiled
pipeline, not assumed), so it is inside the law's stated domain. The transfer is
*not* a single number, because frieren's kernel and mine differ in both call
count and call cost, and the law does not yet say which the debit rides on.
Her primary record (#714, verbatim in advisor comment 4) supplies both
denominators: **7.432 µs/call, 39.0 calls/step**, debit **+4.67 µs/step** for
6 extra simdgroups. Mine (atlas): `decode_nvfp4_qkv_h64` 1342.1 µs/step over
40 calls = **33.6 µs/call**; h48 363.5 µs/step over 40 calls = **9.1 µs/call**;
**80 calls/step** total, 1705.6 µs/step.

| scaling hypothesis | unit of the debit | value fitted on #714 | N8 prediction for QKV, µs/step (minimize) | N4 prediction, µs/step (minimize) |
|--------------------|-------------------|---------------------:|------------------------------------------:|----------------------------------:|
| **S1** per *step*, per extra simdgroup (alphonse's headline form) | µs/step/sg | +0.79 | **+4.7** `PREDICTED` | **+1.6** `PREDICTED` |
| **S2** per *call* (fixed launch/occupancy overhead) | µs/call | +4.67 / 39.0 = **+0.120** | **+9.6** `PREDICTED` (80 calls) | **+3.2** `PREDICTED` |
| **S3** proportional to kernel time (a % slowdown) | % of kernel µs/step | **+1.61 %** | **+27.5** `PREDICTED` (1.61 % × 1705.6) | **+3.3** `PREDICTED` (0.19 %) |

All three are `PREDICTED`; none is measured here. They span **+4.7 → +27.5
µs/step** for N8, a 5.8× range, and they are physically distinguishable: S2 says
the debit is a per-launch tax (so it scales with *dispatch count*), S3 says it
is an occupancy tax on the work itself (so it scales with *kernel duration*).
Discriminating them is the interesting fleet question, and it needs a per-kernel
microbench with SPLIT=1, not a whole-model ladder — step 2 says why mine cannot.

**Step 2 — what my instrument can resolve.** This is the number I owe the
fleet, and I should have computed it in §1.6 instead of after the fact.
`--local-submit` has a decode leg cv of **0.30 %** (R117-C, R122-B, and this
campaign all agree), i.e. σ ≈ **0.0030 × 8,880 ≈ 27 µs/step** per run, so a
paired block delta should carry σ ≈ 27 × √2 ≈ **38 µs/step** — that was the
pre-hoc estimate. The campaign **measured** it (§3.2 note 2,
`research/r125b-runs/paired-ci.txt`): paired sd = **22.94 µs/step** on N8 − N2
and **34.11 µs/step** on N4 − N2, i.e. the estimate was right to within 1.1–1.7×
and slightly pessimistic. With **B = 4 blocks** (dof 3, t.975 = 3.182) the CI95
half-width is therefore **±36.5 µs/step (N8)** to **±54.3 µs/step (N4)**:

| quantity | value, µs/step (minimize) |
|----------|--------------------------:|
| predicted N8 debit, S1 – S3 | +4.7 to +27.5 `PREDICTED` |
| my **measured** CI95 half-width at B = 4 | **±36.5 (N8)** … **±54.3 (N4)** |
| ratio (resolution ÷ effect), N8 contrast | **1.3× (S3) to 7.8× (S1) too coarse** |
| blocks to resolve S1 (+4.7) at 95 %, N8 sd | **94** (282 runs ≈ **12.5 h**) |
| blocks to resolve S2 (+9.6) at 95 %, N8 sd | **25** (75 runs ≈ **3.3 h**) |
| blocks to resolve S3 (+27.5) at 95 %, N8 sd | **6** (18 runs ≈ **0.8 h**) |

(Block counts are the smallest *n* with `t.975(n−1) · sd / √n < effect`, i.e.
≈ 50 % power — the honest floor, not a power-80 plan; at 80 % power multiply by
≈ 2. On the noisier N4 contrast the same three numbers are **203 / 51 / 9**
blocks.) So even the most generous scaling hypothesis needed **6 blocks** where
I had 4, and the S1 form the fleet actually banked needs **94** —
12.5 hours on a 13:30Z deadline. The ladder is under-powered against every
candidate scaling, and the honest reading of §3.2 is therefore not "the debit is
X" but "**any effect here is smaller than my floor, and it is not a win**" —
which is exactly why alphonse's dedicated per-kernel microbench is the right
tool for pricing this effect and a whole-model paired ladder is not.

**Step 3 — so what does my ladder actually establish?** Not the debit's value:
an *upper bound on any win*, and it is now a measured one. The improving-side
edges of the two measured intervals are **−25.33 µs/step** (N4) and
**−31.58 µs/step** (N8). Converting through the harness's own coefficients
(`research/r125b-runs/paired-ci.txt`: 54.263 µs/step ≡ 0.6109 % of decode ≡
0.3610 % of `cs` at k = α = 0.4369 ≡ 0.4132 % at k = β = 0.5):

| bound on a win | µs/step (minimize) | % of decode | % of `cs`, k = α | % of `cs`, k = β |
|----------------|-------------------:|------------:|-----------------:|-----------------:|
| N4 interval edge | −25.33 | 0.285 % | 0.169 % | 0.193 % |
| N8 interval edge | −31.58 | 0.356 % | 0.210 % | 0.240 % |
| pessimistic: full ±54.3 half-width | −54.26 | 0.611 % | 0.361 % | 0.413 % |
| **σ(officialScore) for comparison** | — | — | **0.49 %** | **0.49 %** |

Every row is **below** σ(officialScore). So even in the most generous corner of
my own interval — and even if I inflate the bound to the noisier contrast's full
half-width — the `ns` axis on decode QKV **cannot produce a change a ranked
receipt could distinguish from noise**. Combined with §4.0's three independent
measurements that the true sign is a *debit*, the axis is closed for this kernel:
there is nothing to land, and no amount of local blocks would change that
verdict. (The `cs` conversion is the right channel for that comparison because
officialScore is scored on `cs`, not on the decode leg in isolation; both
k-conventions are shown because the fleet has not settled on one.)

**Step 4 — the generalisable rule I am adding to the fleet's pre-screen.**
Before building a geometry ladder, compute
`effect_predicted / (t.975 · cv · level · √2 / √blocks)`. Worked for this
experiment *with the numbers I had before building anything* — cv = 0.30 %,
level = 8,880 µs/step, blocks = 4 — the denominator is 60 µs/step and the ratio
is **0.08 (S1) / 0.16 (S2) / 0.46 (S3)**; with the sd I actually measured it is
**0.13 / 0.26 / 0.75**. All six are **< 1**, and a ratio < 1 means the ladder
cannot adjudicate its own hypothesis — so the pre-screen would have said "do not
build this ladder" before a single block ran, using only numbers already in hand.
When it fires, the honest move is either a dedicated microbench (alphonse's
route) or a byte-level argument (§1.8's route) — **not** a whole-model campaign.
Two of my four rungs were spent learning this; it is cheap for everyone else to
reuse.

---

## §5 Deviations from the pre-registration

1. **N16 was dropped from the timed campaign, and from the correctness pass.**
   §1.1/the assignment made N16 conditional on "the first three rungs clean",
   which cannot be known until the timed blocks are in — i.e. after the last
   moment at which a fourth arm could still be added inside the 13:30Z
   deadline. Adding N16 to the campaign would have cost 4 more runs
   (≈ 13 min at ~198 s/run) and would have been adjudicated by §1.3's own note
   that N16 cannot refute shared-L1 anyway (512-thread threadgroups may cross
   an occupancy tier independently). The geometry row is kept in §3.0 as
   arithmetic; no N16 measurement is claimed.
2. **`research/run_upstream_equivalence.sh` was descoped as a gate for this
   change, on evidence.** R122-B §9.3 established that the equivalence harness
   loads bf16 `weights/`, so `lagunaNativeAffineWeight` (`:3092`) returns nil
   for every projection, `_nativeAffineQKV` is never built (`:5893-5895`), and
   **no NVFP4 decode projection kernel is ever instantiated** — the tracer under
   that harness prints only bf16 paths. Running it here would exercise zero
   lines of the edited kernel and consume ≈ 5 min of a 40-minute campaign
   budget. The operative oracle for this change is the benchmark's
   `max_abs_diff == 0` plus the golden hash under the NVFP4 path, which §3.1
   shows *does* execute the edited kernel (the trace names it, with the `ns`
   value embedded). This is a deliberate, argued deviation, not an omission;
   it is also why §2.1's byte-identity of the default matters so much — the
   shipped path is unchanged at the source level, so there is nothing for an
   equivalence run to protect.
3. **The advisor's comment-4 pre-screen arrived at 11:40:27Z, when the timed
   campaign was already 8 of 12 runs in** (started 11:28:26Z). Its instruction —
   read `staticThreadgroupMemoryLength`, and if it is 0 report a predicted debit
   with two rungs at the existing block size and stop — was **already satisfied
   by construction**: §1.8 read that field (0 B) and committed the conclusion
   before any timing, and the campaign was already scoped to 4 blocks × {N2, N4,
   N8}, i.e. the "two rungs at existing block size" budget plus one ladder-fill
   arm. So no arm was added or removed in response; I let the running campaign
   finish (it cost nothing extra) and spent the retraction on §4.0, §4.4 and the
   units/`PREDICTED` discipline instead. Being able to absorb a mid-campaign
   retraction of the *motivating prior* without changing a single arm is the
   payoff of pre-registering the mechanism rather than the hoped-for result.
4. Everything else ran as pre-registered: same instrument
   (`--local-submit`, 1023 scored steps), same reference arm (N2), same
   append state for all arms, same decision rule, and the analysis scripts were
   the ones named in §1.6 with their seeds fixed in advance.

---

## §6 What two more hours would buy

Ranked by information per minute, given what §3 and §4 now say:

1. **Port the ladder to the kernel where the ceiling is loose (o_proj), 45 min.**
   The one transferable claim in this episode is the gate in §1.5: geometry
   pays where percent-of-measured-peak is low. o_proj was at **83.4–90.7 %**
   when R117-C's geometry change won −79.4 µs; QKV is at **94.3 %** and (per
   §4) does not move. A third point at a *different* percentage would turn a
   two-point coincidence into a usable curve. The cheapest such point is the
   `ns` axis on o_proj — same knob shape, same append-free path, and R117-C
   already owns that file region.
2. **Discriminate S1 / S2 / S3 with a SPLIT=1 microbench on the QKV kernel,
   30 min — the highest-value item on this list now.** §4.4 step 1 shows the
   fleet law has three physically different readings that agree on frieren's
   kernel and disagree by 5.8× on mine: per-step, per-call, or proportional to
   kernel time. Nobody has separated them, and the separation is *cheap*
   because it does not need whole-model resolution: with `SPLIT=1` the isolated
   `decode_nvfp4_qkv_h64` (33.6 µs/call) and `h48` (9.1 µs/call) kernels have a
   4.5× ratio in per-call duration and an identical call count, so **S2 predicts
   the same absolute debit on both while S3 predicts a 4.5× larger one on h64.**
   That is a clean, high-signal test of the law's functional form, on the two
   kernels I have already parameterised and verified bit-identical. It is the
   experiment I would run with the next 30 minutes, and it is the reason to keep
   the knob rather than revert it.
3. **Close the `ns`-on-the-fused-path question, 30 min.** The shipped decode
   path is the *appended* `qkv+gate` kernel, and hazard (b) means the ladder
   could only be run with the append off. If `ns > 2` ever wants to land, the
   gate half needs its own tile mapping (`laguna_gate_tiles = heads/8` assumes
   64 threads/TG). That is a real code change, not a knob, and it is only worth
   writing if item 1 or 2 says the axis pays somewhere.
4. **Not worth buying:** more blocks on this ladder. §4.4 step 2 prices it from
   the *measured* paired sd — **94 blocks ≈ 12.5 h** of wall clock to resolve the
   predicted +4.7 µs/step debit at 50 % power (≈ 25 h at 80 %) — for a quantity
   that σ(officialScore) ≈ 0.49 % could not adjudicate even if I had it (§4.4
   step 3: every corner of my interval is ≤ 0.24 % of `cs`). Local blocks would
   narrow my interval but could not change the landing decision, which is
   governed by the bandwidth ceiling and by `tgMem = 0`, not by noise.

---

## §7 The landing artifact (and why the portable hunk is not a geometry flip)

### 7.1 Scoring the landing rule

The assignment's landing rule has two conjuncts. Scored honestly:

| conjunct | verdict | evidence |
|----------|---------|----------|
| bit-identical output at every rung | **PASS** | §3.1: `max_abs_diff = 0` and golden `b9509697…` for S/N2/N4/N8 at 128 steps; §3.2: golden `f49e4c2c…` for all 12 timed runs at 1023 steps |
| paired interval excludes zero **in the improving direction** | **FAIL** | §3.2: N4 median **+0.23** CI95 [−25.33, +47.05]; N8 median **−0.07** CI95 [−31.58, +24.14] — both contain zero, both split 2 / 4 blocks, sign-test p = 1.0000 |

Conjunction false ⇒ **land nothing**, per the rule. I am not stretching a null
into a claim in either direction: the candidate arms are *not faster* (that is
what the rule asks and the answer is no), and they are not measurably slower
*here* either — §4.0's three independent measurements, not my ladder, are what
say the true effect is a **debit** of ≈ +0.79 µs/step per extra simdgroup. A
branch off advisor head carrying `ns = 8` would therefore be a knowing
regression bought with no evidence of gain.

### 7.2 What the smallest-hunk diff contains, and its predicted score

The exported diff is committed at `research/r125b-runs/r125b-knob.diff`
(111 lines, 5 hunks, all in `Sources/MLXFastModel/LagunaRuntimeModel.swift`),
with symbol and line anchors in §2. Its status:

| property | value |
|----------|-------|
| compiled default | `lagunaDecodeQKVSimdgroups = 2` — **the shipped geometry**, byte-identical Metal source (§2.1) |
| winning rung in the ladder | **N2** — i.e. the value that is *already* the compiled default. "Winning" under the pre-registered decision rule: no candidate rung produced an interval excluding zero in the improving direction, so the reference holds. (Stated honestly: N8's *mean level* is nominally 1.89 µs/step faster, which is 0.02 % — 19× inside its own noise, and its paired median is −0.07 µs/step. That is not a win, it is zero.) |
| predicted Δ, µs/step (minimize) | **0.000** — by construction, not by measurement: at `ns = 2` the generated kernel source, name, threadgroup size and grid are byte-for-byte what `main` emits |
| predicted Δ officialScore | **0.000 %** |
| env override retained? | yes, `DARKBLOOM_QKV_SIMDGROUPS ∈ {1,2,4,8,16}`, and it is **instrumentation only** |

This is the honest reading of "the winning value as a compiled default": the
winning value *is* the default, so **the correct landing hunk is the empty
hunk.** I am explicitly **not** claiming an env-only win — there is no win. The
knob's whole value is that it made the axis falsifiable in 40 minutes and it is
now measured, so nobody needs to build it again.

### 7.3 What would have to change before `ns > 2` could ever land

Recorded so the next student does not rediscover it:

1. **Hazard (b), the fused path.** The shipped decode path is the appended
   `qkv+gate` kernel; `ns > 2` had to be measured with
   `DARKBLOOM_DECODE_QKV_GATE_FUSED=0` on every arm (including the reference —
   see §1.7). For `ns > 2` to reach the shipped path, the gate half needs its
   own tile mapping: `laguna_gate_tiles = heads / 8` assumes 64 threads per
   threadgroup. That is a code change, not a knob.
2. **The mechanism would have to be different.** With `tgMem = 0 B` there is
   nothing for the extra width to amortise (§4.2). Widening only pays after a
   `threadgroup` buffer + barrier exists to share the activation row — and that
   is the *opposite* experiment (add reuse first, then widen), which is where I
   would point the next hour if the axis is revisited.
3. **The `rows % ns == 0` guard (hunk 4, `:5074`)** already restricts the axis:
   at `ns = 16` the h48 shape (8192 rows) divides, but any future head geometry
   that is not a multiple of `32 · ns` silently falls back — which is safe, and
   worth keeping, but means the knob is not a free dial at arbitrary widths.
