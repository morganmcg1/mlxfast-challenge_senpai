# R125-B — decode QKV threadgroup-granularity ladder (the `ns` axis at `rps = 1`)

Student: maple-nezuko. Assignment `maple-r125-b-qkv-tg-granularity-ladder`,
revision `r125-b-rev1`, PR #730.
Branch `maple-nezuko/r125-b-qkv-tg-granularity-ladder`, base
`a9de9e8f21188715f6d80ada4b581bcd50d4ec81`.
Host: Apple M4 Pro, 20 GPU cores, 48 GiB, `applegpu_g16s`, macOS 26.5.2.

> **§0 verdict** — pending. This file is committed first as a
> **pre-registration** (§1) and is filled in afterwards. The pre-registration
> commit deliberately contains no measurement and no code.

---

## §1 Pre-registration (written before any arm was timed)

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
