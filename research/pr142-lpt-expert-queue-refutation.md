# PR #142 Round 22 H3 — device-compacted LPT expert queue: Step 0 gate → DEMOTE

Assignment `maple-2026-08-06m-lpt-expert-queue` r1, base `2443984f`.
Student maple-frieren. No GPU allocation consumed; no official receipt spent.

**Verdict: DEMOTE at the Step 0 gate.** Best simulated saving in the physically
plausible regime is **0.18–0.46 ms** (≈ **+0.06 % … +0.17 %** score), tightening
to **0.07–0.35 ms** once the marginal-occupancy correction in §5d.4 is applied,
against a **1.0 ms** GO floor. Uncharged prep-kernel cost (§5e) is 0.1–0.3 ms
and could consume the entire remaining margin. **LPT reordering specifically
contributes ≈ 0 ms**, for a structural reason (§5b), so the "ship the simpler
half" test fails too. The briefed indirect-dispatch mechanism is additionally
unreachable inside `editablePaths` (§2).

Break-even `ε` is **423 ns at C = 40 and 846 ns at C = 80** for the 1.0 ms gate;
realistic marginal `ε` is 30–150 ns. The single input with enough leverage to
overturn this is `T_gather`, which is asserted rather than measured (§5f).

Two deliverables land regardless of the verdict, per advisor instruction:

- `research/artifacts/route-histogram-prefill512.csv` + `-stats.json`
- `research/artifacts/README-route-histogram.md` (schema)
- generator/simulator: `research/lpt_expert_queue_sim.py`

---

## 1. The assignment premise is factually wrong

The assignment assumes the routed-MoE gather-GEMM launches a **dense grid sized
by the worst-case rows-per-expert**, so that skipping empty experts recovers the
`max/mean` ratio (15.19× on this workload). That is not what the code does.

`Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/quantized.cpp:1917-1923`:

```cpp
MTL::Size grid_dims = MTL::Size(
    xmajor_ct > 1 ? (N / bn) / xmajor_ct : (N + bn - 1) / bn,
    expert_aligned ? egroups : (M + bm - 1) / bm,
    1);
MTL::Size group_dims = MTL::Size(32, wn, wm);
```

- **Non-`_nax` path** (`expert_aligned == false`): grid y is `ceil(M/bm)` over
  the *already gathered and sorted* row block — this is the compact form
  already. There is nothing to compact.
- **`_nax` path** (`expert_aligned == true`, the ranked M5 path): grid y is the
  **constant** `egroups = 256` (`:1379`), i.e. one threadgroup per expert slot
  per column tile — *not* `max_rows/bm × 256`. An expert with zero rows costs
  two binary searches plus threadgroup launch/retire, then exits.

So the recoverable quantity is **not** `(max − mean)/mean = 15.19×`. It is the
**empty-threadgroup fraction**, 20.26 %, multiplied by the per-empty-launch
cost `ε`. That is a fundamentally smaller number, and it is the whole reason
this arm fails the gate.

Geometry confirmed: `xmajor_ct` pinned 0 (`:1563`), `expert_aligned` default ON
(`:1328`), tiling variant 5 ⇒ `bm=64, wm=4, wn=1`, 128 threads/TG, `Ws` 9.2 KB.

## 2. The mechanism *as briefed* is unimplementable; a workaround exists but loses on cost

The briefed mechanism needs `dispatchThreadgroupsWithIndirectBuffer`. That exact
call cannot be reached:

| Requirement | Reality |
| --- | --- |
| Indirect dispatch entry point | `backend/metal/device.h:56` declares only `void dispatch_threadgroups(MTL::Size, MTL::Size)`. No indirect overload exists anywhere in the vendored tree. |
| Raw encoder to call Metal directly | `MTL::ComputeCommandEncoder* get_command_encoder()` is **private** (`device.h:105`, under `private:` at `:104`). |
| Add the overload ourselves | `device.h` / `device.cpp` are **not** in `benchmark.json` `editablePaths` (97 entries; from this subtree only `backend/metal/quantized.cpp` and `backend/metal/kernels/*` are listed). |

A device-side compacted queue whose length is only known on the GPU therefore
has no way to size a dispatch. In-surface fallbacks:

- **Host-side readback of the queue length** — a full pipeline stall per layer,
  catastrophically worse than the 0.36 ms it is trying to save. Dead.
- **Keep the 256-wide grid, self-select from the compacted queue** — does not
  remove the launches, so saves nothing. Dead.
- **Persistent worker-pool kernel** — fixed grid sized to fill the machine plus
  an atomic task counter, entirely inside `quantized.cpp` +
  `kernels/fp_quantized_nax.h`. This *does* emulate both compaction and dynamic
  load balance within the editable surface.

So I must retract "unimplementable regardless": the persistent-worker-pool
variant is reachable. **It is rejected on cost-benefit, not impossibility** —
it is a substantial rewrite of the `_nax` kernel's outer structure, it lands
squarely in maple-tanjiro's fenced region (#138), and its ceiling is the same
0.18–0.46 ms computed in §5, against which §5e's uncharged prep cost of
0.1–0.3 ms is a large fraction. The briefed indirect-dispatch mechanism
specifically remains impossible.

## 3. Prior art: already on the Forbidden list

`research/RESEARCH_STATE_ARCHIVE_through-round-21.md:4793-4796` lists
*"skip-empty-expert dispatch surgery (empty TGs already exit at the binary
search)"* as Forbidden. The Step 0 measurement below is the quantitative
backing for that entry rather than a new result, and it is now reproducible.

## 4. Artifact (delivered)

Source probe: `research/prefill-512-route-histogram.txt`, 76 layer records from
a 512-token prefill. Forward 0 and forward 1 are **bit-identical** (verified),
so the warmup drop is a no-op and any consumer may use either.

Pooled statistics reproduce the archive exactly:

| stat | value |
| --- | --- |
| n (layer × expert cells) | 9728 |
| sum rows | 155648 |
| zero cells | 1971 (**20.26 %**) |
| min / median / mean | 0 / 7 / 16.00 |
| p90 / p99 / max | 39 / 142 / 505 |
| stdev / mean(nonzero) | 28.77 / 20.07 |
| `chunks_bm64` | 8379 (weight re-read factor **1.0802** over 7757 nonzero) |
| max/mean per layer | **15.19×** |

Dispatch tiles per forward:

| call | K | N | col tiles | dense TGs | compact TGs | ratio | chunk DRAM B |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `gate_up` | 512 | 2048 | 32 | 311296 | 248224 | 1.2541× | 18432 |
| `down` | 2048 | 1024 | 16 | 155648 | 124112 | 1.2541× | 73728 |
| **total** | | | | **466944** | **372832** | | |

Empty threadgroups per forward: **94608**.

Schema and regeneration instructions: `research/artifacts/README-route-histogram.md`.
Regenerate with `python3 research/lpt_expert_queue_sim.py`.

## 5. Step 0b — makespan simulation

40 GPU cores, `R` concurrently resident threadgroups per core, greedy list
scheduling; task cost = `ceil(rows/64)` chunks weighted by the call's
`chunk_dram_bytes`. Note the kernel's K-loop sits **inside** the chunk loop
(`kernels/fp_quantized_nax.h:1568`), so an expert's `BN×K` weight slice is
re-read once per 64-row chunk and per-chunk wall time is roughly constant —
which is what makes chunk-count a valid cost unit.

### 5a. `M_compact` — removing empty threadgroups

Closed form, exact: `M_compact = 94608 × ε / C`. It does not depend on the
distribution at all, only on the empty count.

Break-even `ε` required to reach the gate:

| cores × R = C | ε for ≥ 1.0 ms | ε for ≥ 3.0 ms |
| --- | --- | --- |
| 40 | 423 ns | 1268 ns |
| 80 | 846 ns | 2537 ns |
| 160 | 1691 ns | 5074 ns |
| 240 | 2537 ns | 7610 ns |

Physically, `ε` for an empty `_nax` threadgroup is two 12-step binary searches
over a hot shared 16 KB array plus launch/retire: **200–400 ns**. Even the most
favourable configuration (`ε = 400 ns`, `C = 40`) gives 0.95 ms — still under
the floor, and `C = 40` (one resident TG per core) is unrealistic for a
128-thread, 9.2 KB-shared-memory kernel.

At the realistic `ε = 300 ns`: **0.355 ms at C = 80**, **0.177 ms at C = 160**.

### 5b. `M_lpt` — longest-processing-time reordering

Reported separately as instructed:

| R | `M_lpt` |
| --- | --- |
| 1 | **0.000 ms** (greedy natural order already attains the makespan lower bound: 20186 vs LB 20109.6 work units) |
| 2 | 0.07 – 0.11 ms |
| 4 | 0.40 – 0.63 ms |
| 6 | 0.90 – 2.53 ms |

**LPT is worth nothing at R = 1 and almost nothing at R = 2.** The advisor's
"if compaction is 90 % of the win, ship the simpler change" test resolves the
other way: **compaction is ~100 % of the win at low R, and LPT only becomes
material at R ≥ 6, which the 9.2 KB shared-memory footprint rules out.**

To be precise about *why*, since "greedy already hits the lower bound" is a
property of this trace and not a theorem — Graham's bounds are
`list ≤ (2 − 1/m)·OPT` and `LPT ≤ (4/3 − 1/(3m))·OPT`, but the tighter
additive form is what binds here:

```
makespan(list) ≤ Σp/m + p_max·(1 − 1/m)
```

With `p_max ≈ 32` work units against `Σp/m ≈ 353` units per core, the worst-case
headroom any reordering can recover is ≈ **9 %** of the tail term, and the
natural x-major emission order is already close to round-robin across experts.
That is the structural reason LPT measures 0.000 ms at R = 1 rather than a lucky
trace: the task count (9728) swamps the slot count (40–160), so there is almost
no tail to reorder. This bound is distribution-independent, so it also holds if
the routing histogram shifts on another workload.

### 5c. Combined, plausible regime

Best physically plausible total (`ε = 300 ns`, `C = 80`, `T_gather = 40 ms`):
**Δ 0.458 ms → +0.166 %**. At `C = 160`: ≈ 0.6–0.8 ms → ≈ +0.22–0.29 %.

Both are below the 1.0 ms GO floor and below the advisor's 0.61 % acceptance
bar. Applying the advisor-supplied `−1 ms of S = +0.362 %`. (Cross-check: the
naive score-formula exponent alone, `0.25 / 97.89 ms`, gives +0.255 %/ms. Using
+0.362 %/ms is therefore the *generous* choice and the verdict holds either way.)

### 5d. Four ways the model is biased *in favour* of the arm

1. **Roofline.** Charging `ε` as exclusive slot occupancy assumes an empty
   threadgroup consumes the bottleneck resource. The kernel runs near the DRAM
   roofline. An empty TG issues no loads; it occupies a scheduler slot but not
   bandwidth, so the true saving is strictly below `94608 × ε / C`.
   *(Correction to my first pass: the 1.0802 chunk re-read is within-TG and
   L2-resident, so DRAM traffic is ≈ 13.7–14.3 GB, not 15.2 GB, and achieved
   bandwidth ≈ 560–575 GB/s rather than 610 GB/s. The conclusion is unchanged.)*
2. **`R` and `T_gather` are anti-correlated** (Little's law). Higher residency
   raises achieved bandwidth and therefore *lowers* `T_gather`. The favourable
   corner of the sweep (`R = 6`, `T_gather = 60 ms`) is self-contradictory and
   should be discarded; the coherent corners are the low ones already reported.
3. **Independent full-speed slots.** Modelling `C = cores × R` as independent
   machines each running at full rate overstates both the compaction and the
   LPT/tail terms, since co-resident threadgroups contend for the same LSU and
   L2 ports.
4. **`ε` is a lifetime, not a marginal cost.** ~12 dependent L1 loads at
   30–60 ns each plus barrier and launch/retire puts an empty threadgroup's
   *lifetime* at 0.5–1.0 µs — so my 200–400 ns figure is 2–3× low as a lifetime.
   But the quantity that actually matters is **post-overlap marginal
   occupancy**, which is only ~30–150 ns because the empty TG's latency hides
   behind neighbouring resident work. Net of both errors, the realistic saving
   is **0.07–0.35 ms**, i.e. *below* the range in §5c.

All four mean the honest number is at or below the **bottom** of the
0.18–0.46 ms range.

### 5e. Costs the model never charges at all

- **Prep and indirect-args kernels: ≈ 0.1–0.3 ms** on the GPU critical path.
  This is a large fraction of a 0.18–0.46 ms ceiling and could make the scheme
  **net-negative on its own**.
- **Activation L2 reuse.** An unstable LPT ordering scatters an expert's 32
  (`gate_up`) / 16 (`down`) column tiles across the schedule, forfeiting L2
  reuse of its activation rows. A stable sort avoids this, but only by
  constraining the very reordering freedom LPT depends on.

### 5f. The one input that could overturn this

`T_gather ≈ 25 ms` is **asserted, not measured**. It is the weakest link in the
whole analysis. If a GPU trace showed `T_gather ≫ 25 ms` with genuinely low
occupancy, the empty + imbalance terms would rise toward 1–2.4 ms and the arm
would re-enter contention. Nothing else in the model has that leverage. A
Metal GPU capture on M5 is the correct instrument; I do not have one (§6).

## 6. Why this could not be measured locally

Host is an Apple **M4 Pro**, 48 GiB, macOS 26.5.2. `is_nax_available()`
requires GPU generation ≥ 17; M4 Pro reports generation 16. **The entire
`expert_aligned` `_nax` path is never executed on this host**, so no local A/B
of this arm is possible even in principle. Separately, local prefill A/A noise
is ≈ 1.30 % ≈ ±7.6 ms on `S`, which could not resolve a 0.3–1.5 ms effect
regardless. Hence: simulation on the real measured route histogram, plus source
verification, plus an explicit break-even statement — rather than a
non-informative local timing run or a spent official receipt.

## 7. Correction to an earlier follow-up idea

I initially flagged `DARKBLOOM_EXPERT_GATHER_GROUPS` (`quantized.cpp:1379`) as
a zero-code alternative that "dominates" the proposed scheme, because lowering
`egroups` collapses the empty fraction (one TG is empty only if *all* the
expert slots it owns are empty):

| egroups | slots/TG | TGs/fwd | empty | empty % | max chunks/TG |
| --- | --- | --- | --- | --- | --- |
| 256 (default) | 1 | 466944 | 94608 | 20.26 % | 8 |
| 128 | 2 | 233472 | 11136 | 4.77 % | 9 |
| 64 | 4 | 116736 | 384 | 0.33 % | 11 |
| 32 | 8 | 58368 | 0 | 0.00 % | 14 |

**Simulating it refutes the idea.** Coarsening trades empty-TG cost for worse
load balance, and the imbalance term grows faster than the empty term shrinks
(`ε = 300 ns`, `T_gather = 40 ms`, excess over the ideal 40.0 ms):

| egroups | C=80 makespan | = empty + imbalance | all-TG-charged |
| --- | --- | --- | --- |
| 256 | 40.777 | 0.355 + 0.422 | 42.173 |
| 128 | 40.838 | 0.042 + 0.796 | **41.672** |
| 64 | 41.386 | 0.001 + 1.385 | 41.823 |
| 32 | 42.344 | 0.000 + 2.344 | 42.563 |

| egroups | C=160 makespan | = empty + imbalance | all-TG-charged |
| --- | --- | --- | --- |
| 256 | 41.501 | 0.177 + 1.324 | **42.200** |
| 128 | 42.079 | 0.021 + 2.058 | 42.496 |
| 64 | 43.752 | 0.001 + 3.752 | 43.970 |
| 32 | 46.386 | 0.000 + 6.386 | 46.495 |

Under the model as specified (`ε` charged only to empty launches) the **current
default `egroups = 256` is optimal**. Under a stricter model that charges `ε`
to *every* launch — defensible since low `egroups` also cuts total launches 4–8×
— `egroups = 128` wins by 0.50 ms at C = 80 but loses at C = 160. So the knob is
**ambiguous, not dominant**, worth at most ~0.5 ms, and sign-uncertain in `C`.

I am not changing it: `tg_expert_groups` is a kernel template parameter and sits
in maple-tanjiro's `_nax` inner-loop region (#138). Flagging for advisor routing
only. Its one real virtue is that it is an **env knob**, so it is the cheapest
available *empirical* probe of `ε` on real M5 hardware — one paired run would
replace this entire simulation's weakest parameter with a measurement.

## 8. Region fence

No edits were made to `Vendor/mlx-swift/.../quantized.cpp` or
`Sources/MLXFastModel/LagunaRuntimeModel.swift`. The `_nax` inner loop / tile
geometry / accept gate at `:1634-1671` (maple-tanjiro, #138) was read but not
touched. Byte budget impact of this PR: **0** — everything landed is under
`research/`, which is research-only and outside the submitted surface.

## 9. Suggested follow-ups (not implemented)

1. **Measure `T_gather` and `ε` instead of assuming them.** Per the advisor's
   19:18Z standby notice I am spending **no receipts** and starting nothing
   unilaterally, so this is a routing suggestion only. Two candidates, in
   priority order:
   (a) a Metal GPU capture of one M5 prefill, which settles §5f — the single
   input with enough leverage to overturn the verdict — at zero receipt cost;
   (b) a paired `DARKBLOOM_EXPERT_GATHER_GROUPS=128` vs `256` run, which turns
   `ε` into a measured constant and settles §7's sign ambiguity at zero code and
   zero review-surface cost. Both are better spent on the
   `research/PREFILL_LEDGER_INSTRUMENT.md` programme (maple-nezuko primary)
   than on resurrecting this arm.
2. **Reuse the artifact for maple-nezuko (#143).** The CSV/JSON is stable,
   schema-versioned, and reproduces the archive's pooled numbers exactly; #143
   can join against `layer_index,expert_id,rows,chunks_bm64` directly.
3. **The promoted strongest prefill arm remains BN 64→32 (C2)**, not dispatch
   surgery. The 1.0802 weight re-read factor measured here (§4) is the quantity
   that arm attacks, and it is a real DRAM cost rather than a scheduler-slot
   cost — a much better target than the 20.26 % empty fraction.
